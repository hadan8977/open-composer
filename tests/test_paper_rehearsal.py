from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copyfile
from types import SimpleNamespace

import pytest

from open_composer import paper_rehearsal
from open_composer.adapters.broker import alpaca_paper
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_controls import enable_paper_kill_switch
from open_composer.paper_rehearsal import (
    RehearsalError,
    cancel_open_rehearsal_orders,
    load_rehearsal_authorization,
    plan_rehearsal_orders,
    reconcile_rehearsal_fills,
    run_portfolio_paper_rehearsal,
    write_rehearsal_authorization,
)

REPO_SPEC = Path(__file__).resolve().parents[1] / (
    "strategy_specs/drafts/us_recent_high_return_top50.yaml"
)
# Wednesday 2026-09-16 23:15 UTC == 19:15 ET: inside Alpaca's opening-auction window
SUBMIT_TIME = datetime(2026, 9, 16, 23, 15, tzinfo=UTC)
LIMITS = {
    "max_gross_exposure": 1.0,
    "max_symbol_weight": 0.05,
    "max_orders_per_session": 150,
    "max_session_notional_usd": 150_000.0,
    "max_total_notional_usd": 750_000.0,
}


class FakeClient:
    def __init__(self, *, account_id: str = "PA-TEST-0001", positions=None):
        self.account_id = account_id
        self.positions = list(positions or [])
        self.orders: list[SimpleNamespace] = []
        self.submissions: list = []
        self._base_url = alpaca_paper.ALPACA_PAPER_ORIGIN
        self._sandbox = True
        alpaca_paper._mark_verified_paper_client(self)

    def get_account(self):
        return SimpleNamespace(
            id=self.account_id,
            equity="100000",
            cash="100000",
            buying_power="200000",
            portfolio_value="100000",
            status="ACTIVE",
        )

    def get_all_positions(self):
        return list(self.positions)

    def get_orders(self, filter=None):  # noqa: A002 - alpaca-py keyword
        return list(self.orders)

    def cancel_order_by_id(self, order_id):
        for order in self.orders:
            if order.id == order_id:
                order.status = "canceled"

    def submit_order(self, request):
        self.submissions.append(request)
        order = SimpleNamespace(
            id=f"ord-{len(self.orders) + 1}",
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            qty=request.qty,
            side=request.side,
            status="accepted",
            order_type=getattr(request, "type", "market"),
            time_in_force=request.time_in_force,
            limit_price=getattr(request, "limit_price", None),
            filled_qty=0,
            filled_avg_price=None,
            submitted_at=SUBMIT_TIME,
            accepted_at=SUBMIT_TIME,
        )
        self.orders.append(order)
        return order


def _rows(*items: tuple[str, float, float]) -> list[dict]:
    return [
        {
            "rebalance_id": "reb-2026-09-11",
            "symbol": symbol,
            "target_weight": weight,
            "reference_price": price,
            "selected": True,
            "leg": "top_k",
        }
        for symbol, weight, price in items
    ]


def _write_targets(root: Path, name: str, rows: list[dict], *, generated_at: datetime) -> None:
    path = root / "reports" / "execution" / f"{name}-target-weights.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "strategy_name": name,
                "generated_at": generated_at.isoformat(),
                "portfolio_mode": "model_ranking_portfolio",
                "summary": {"account_equity": 100_000.0},
                "target_weights": rows,
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def rehearsal_workspace(sample_workspace: Path) -> tuple[Path, Path]:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / REPO_SPEC.name
    copyfile(REPO_SPEC, spec_path)
    name = load_strategy_spec(spec_path).name
    _write_targets(
        sample_workspace,
        name,
        _rows(("AAPL", 0.05, 200.0), ("MSFT", 0.05, 400.0), ("NVDA", 0.04, 100.0)),
        generated_at=SUBMIT_TIME - timedelta(hours=1),
    )
    return sample_workspace, spec_path


def _authorize(root: Path, spec_path: Path, client: FakeClient, **overrides) -> Path:
    kwargs = dict(
        authorized_by="pytest",
        confirm_paper_only=True,
        acknowledge_below_contract=True,
        gate_status_note="gate v2 FAIL: step13 rule momentum top50, +33%/-28% dd since 2024",
        duration_days=14,
        client=client,
        now=SUBMIT_TIME - timedelta(days=1),
    )
    kwargs.update(overrides)
    return write_rehearsal_authorization(spec_path, root, **kwargs)


def test_authorization_requires_explicit_acknowledgements(rehearsal_workspace) -> None:
    root, spec_path = rehearsal_workspace
    client = FakeClient()
    with pytest.raises(RehearsalError, match="confirm-paper-only"):
        _authorize(root, spec_path, client, confirm_paper_only=False)
    with pytest.raises(RehearsalError, match="confirm-paper-only"):
        _authorize(root, spec_path, client, acknowledge_below_contract=False)
    with pytest.raises(RehearsalError, match="duration_days"):
        _authorize(root, spec_path, client, duration_days=90)
    with pytest.raises(RehearsalError, match="leverage"):
        _authorize(root, spec_path, client, limits={"max_gross_exposure": 1.5})


def test_dry_run_plans_orders_and_logs_signals_without_submitting(rehearsal_workspace) -> None:
    root, spec_path = rehearsal_workspace
    client = FakeClient()
    path = _authorize(root, spec_path, client)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["paper_only"] is True and payload["below_contract_acknowledged"] is True

    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
    )
    assert result.status == "dry_run"
    assert result.session == "2026-09-17"
    assert result.counts() == {"would_submit": 3}
    assert client.submissions == []
    by_symbol = {plan.symbol: plan for plan in result.plans}
    # floor(0.05 * 100000 / 200) = 25 shares of AAPL
    assert by_symbol["AAPL"].qty == 25 and by_symbol["AAPL"].side == "buy"
    assert by_symbol["MSFT"].qty == 12
    assert by_symbol["NVDA"].qty == 40
    signal_log = root / "signal_logs" / f"paper-rehearsal-{result.strategy_name}.jsonl"
    signals = [json.loads(line) for line in signal_log.read_text().splitlines() if line.strip()]
    assert {row["symbol"] for row in signals} == {"AAPL", "MSFT", "NVDA"}
    assert all("rehearsal=below_contract" in row["conditions"] for row in signals)
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    assert report["rehearsal"] == "below_contract" and report["broker_writes"] is False
    assert (
        root / "reports" / "paper" / "rehearsal" / f"{result.strategy_name}-latest.md"
    ).is_file()


def test_submit_then_rerun_is_idempotent(rehearsal_workspace) -> None:
    root, spec_path = rehearsal_workspace
    held = SimpleNamespace(symbol="META", qty="10", current_price="500", market_value="5000")
    client = FakeClient(positions=[held])
    _authorize(root, spec_path, client)

    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=SUBMIT_TIME
    )
    assert result.status == "submitted"
    assert result.counts() == {"submitted": 4}
    # the held name that is no longer a target is sold first
    assert result.plans[0].symbol == "META" and result.plans[0].side == "sell"
    assert result.plans[0].qty == 10
    assert len(client.submissions) == 4
    assert all(str(req.time_in_force).lower().endswith("day") for req in client.submissions)
    assert all(req.client_order_id.startswith("reh-20260917-") for req in client.submissions)
    ledger = root / "reports" / "paper" / "rehearsal" / f"{result.strategy_name}-orders.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert len(rows) == 4 and all(row["paper"] is True for row in rows)
    assert all(row["broker_order_id"].startswith("ord-") for row in rows)

    rerun = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=SUBMIT_TIME
    )
    assert len(client.submissions) == 4
    assert "submitted" not in rerun.counts()
    assert set(rerun.counts()) <= {"skip_open_order", "already_submitted"}


def test_kill_switch_blocks_every_submission(rehearsal_workspace) -> None:
    root, spec_path = rehearsal_workspace
    client = FakeClient()
    _authorize(root, spec_path, client)
    enable_paper_kill_switch(root, reason="test", updated_by="pytest")
    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=SUBMIT_TIME
    )
    assert result.status == "blocked_by_kill_switch"
    assert client.submissions == [] and result.plans == []


def test_submission_window_is_enforced(rehearsal_workspace) -> None:
    root, spec_path = rehearsal_workspace
    client = FakeClient()
    _authorize(root, spec_path, client)
    midday = datetime(2026, 9, 16, 15, 0, tzinfo=UTC)  # 11:00 ET, market open
    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=midday
    )
    assert result.status == "blocked_by_submission_window"
    assert client.submissions == []


def test_expired_or_mismatched_authorization_is_refused(rehearsal_workspace) -> None:
    root, spec_path = rehearsal_workspace
    client = FakeClient()
    _authorize(root, spec_path, client, duration_days=1)
    with pytest.raises(RehearsalError, match="expired"):
        run_portfolio_paper_rehearsal(
            spec_path,
            root,
            allow_paper_orders=False,
            client=client,
            now=SUBMIT_TIME + timedelta(days=2),
        )
    _authorize(root, spec_path, client)
    other_account = FakeClient(account_id="PA-OTHER")
    with pytest.raises(RehearsalError, match="different paper account"):
        run_portfolio_paper_rehearsal(
            spec_path, root, allow_paper_orders=False, client=other_account, now=SUBMIT_TIME
        )
    text = spec_path.read_text(encoding="utf-8").replace("top_k: 50", "top_k: 40")
    spec_path.write_text(text, encoding="utf-8")
    with pytest.raises(RehearsalError, match="content hash"):
        load_rehearsal_authorization(load_strategy_spec(spec_path), root, now=SUBMIT_TIME)


def test_stale_target_weights_are_refused(rehearsal_workspace) -> None:
    root, spec_path = rehearsal_workspace
    client = FakeClient()
    _authorize(root, spec_path, client)
    name = load_strategy_spec(spec_path).name
    _write_targets(
        root, name, _rows(("AAPL", 0.05, 200.0)), generated_at=SUBMIT_TIME - timedelta(hours=40)
    )
    with pytest.raises(RehearsalError, match="old"):
        run_portfolio_paper_rehearsal(
            spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
        )


def test_planner_caps_weight_and_defers_buys_beyond_budgets() -> None:
    rows = _rows(("AAA", 0.20, 10.0), ("BBB", 0.05, 10.0), ("CCC", 0.05, 10.0), ("DDD", 0.05, 10.0))
    plans = plan_rehearsal_orders(
        target_rows=rows,
        positions={},
        position_prices={},
        open_order_symbols=set(),
        equity=100_000.0,
        limits={**LIMITS, "max_orders_per_session": 2},
    )
    assert [p.decision for p in plans] == [
        "submit",
        "submit",
        "deferred_order_budget",
        "deferred_order_budget",
    ]
    assert plans[0].qty == 500  # 0.20 capped to 0.05 -> 5,000 / 10
    plans = plan_rehearsal_orders(
        target_rows=rows,
        positions={},
        position_prices={},
        open_order_symbols=set(),
        equity=100_000.0,
        limits={**LIMITS, "max_session_notional_usd": 12_000.0},
    )
    assert [p.decision for p in plans] == [
        "submit",
        "submit",
        "deferred_notional_budget",
        "deferred_notional_budget",
    ]


def test_planner_exits_held_names_and_skips_open_orders() -> None:
    rows = _rows(("AAA", 0.05, 10.0), ("BBB", 0.05, 10.0))
    plans = plan_rehearsal_orders(
        target_rows=rows,
        positions={"ZZZ": 30.0, "AAA": 500.0},
        position_prices={"ZZZ": 20.0, "AAA": 10.0},
        open_order_symbols={"BBB"},
        equity=100_000.0,
        limits=LIMITS,
    )
    by_symbol = {p.symbol: p for p in plans}
    assert plans[0].symbol == "ZZZ" and plans[0].side == "sell" and plans[0].qty == 30
    assert by_symbol["AAA"].decision == "skip_no_change"
    assert by_symbol["BBB"].decision == "skip_open_order"


def test_paper_rehearsal_rejects_non_open_policy(rehearsal_workspace) -> None:
    root, spec_path = rehearsal_workspace
    text = spec_path.read_text(encoding="utf-8").replace(
        "order_style: day_market", "order_style: twap"
    )
    spec_path.write_text(text, encoding="utf-8")
    with pytest.raises(RehearsalError):
        paper_rehearsal.validate_rehearsal_spec(load_strategy_spec(spec_path), root)


def test_expired_prior_order_does_not_block_resubmission(rehearsal_workspace) -> None:
    root, spec_path = rehearsal_workspace
    client = FakeClient()
    _authorize(root, spec_path, client)
    first = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=SUBMIT_TIME
    )
    assert first.counts() == {"submitted": 3}
    for order in client.orders:  # the broker expired everything at the open
        order.status = "expired"
    second = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=SUBMIT_TIME
    )
    assert second.counts() == {"submitted": 3}
    assert len(client.submissions) == 6


def test_cancel_open_touches_only_this_strategys_ledgered_orders(rehearsal_workspace) -> None:
    root, spec_path = rehearsal_workspace
    client = FakeClient()
    _authorize(root, spec_path, client)
    run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=SUBMIT_TIME
    )
    client.orders.append(
        SimpleNamespace(
            id="ord-foreign", client_order_id="oc-sig_other", symbol="ZZZ", status="new"
        )
    )
    cancelled = cancel_open_rehearsal_orders(spec_path, root, reason="test", client=client)
    assert len(cancelled) == 3
    assert {o.status for o in client.orders if o.client_order_id.startswith("reh-")} == {"canceled"}
    assert next(o for o in client.orders if o.id == "ord-foreign").status == "new"
    assert (root / "reports" / "paper" / "rehearsal").glob("*-cancellations.jsonl")


def test_reconcile_reports_fill_rate_and_slippage(rehearsal_workspace) -> None:
    root, spec_path = rehearsal_workspace
    client = FakeClient()
    _authorize(root, spec_path, client)
    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=SUBMIT_TIME
    )
    by_symbol = {o.symbol: o for o in client.orders}
    by_symbol["AAPL"].status, by_symbol["AAPL"].filled_qty = "filled", 25
    by_symbol["AAPL"].filled_avg_price = 202.0  # +100 bp vs reference 200
    by_symbol["MSFT"].status, by_symbol["MSFT"].filled_qty = "expired", 0
    by_symbol["NVDA"].status, by_symbol["NVDA"].filled_qty = "expired", 10
    by_symbol["NVDA"].filled_avg_price = 100.0
    summary = reconcile_rehearsal_fills(spec_path, root, client=client)
    row = summary["sessions"][result.session]
    assert (row["filled_full"], row["filled_partial"], row["unfilled"]) == (1, 1, 1)
    assert (
        abs(row["fill_rate_by_notional"] - (25 * 200 + 10 * 100) / (25 * 200 + 12 * 400 + 40 * 100))
        < 1e-9
    )
    fills = (
        root / "reports" / "paper" / "rehearsal" / f"{result.strategy_name}-fills.jsonl"
    ).read_text()
    assert '"slippage_vs_reference_bps": 100.0' in fills.replace("99.99999999999", "100.0")


def test_planner_skips_whole_share_drift_below_tolerance() -> None:
    rows = _rows(("AAA", 0.02, 100.0))  # target 20 shares
    plans = plan_rehearsal_orders(
        target_rows=rows,
        positions={"AAA": 19.0},
        position_prices={"AAA": 100.0},
        open_order_symbols=set(),
        equity=100_000.0,
        limits=LIMITS,
    )
    assert plans[0].decision == "skip_below_tolerance"
    plans = plan_rehearsal_orders(
        target_rows=rows,
        positions={"AAA": 5.0},
        position_prices={"AAA": 100.0},
        open_order_symbols=set(),
        equity=100_000.0,
        limits=LIMITS,
    )
    assert plans[0].decision == "submit" and plans[0].qty == 15
