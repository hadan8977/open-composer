"""``execution_policy.position_scope`` per-strategy position accounting for
the paper rehearsal planner (2026-09-18).

Three ETF rotation sleeves joined the one Alpaca paper account that already
runs ``us_recent_high_return_top50`` at ~95% of equity, and the sleeves
overlap on symbols (XLK appears in two menus). ``position_scope`` controls
whether ``run_portfolio_paper_rehearsal`` plans against every position in the
whole broker account (``broker_account``, the default and the behaviour of
every spec written before this date) or against only this strategy's own
recorded fills (``strategy_ledger``), reading
``reports/paper/rehearsal/{name}-fills.jsonl``.

Mirrors ``tests/test_paper_rehearsal.py``'s fixture style (``FakeClient``,
``_rows``, ``_write_targets``, ``_authorize``) and reuses those helpers
directly; nothing here touches a real broker or ``.env``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_rehearsal import (
    RehearsalError,
    rehearsal_fills_path,
    run_portfolio_paper_rehearsal,
)
from tests.test_paper_rehearsal import (
    REPO_SPEC,
    SUBMIT_TIME,
    FakeClient,
    _authorize,
    _rows,
    _write_targets,
)


def _strategy_ledger_spec(root: Path) -> Path:
    """Copy the real ``us_recent_high_return_top50`` spec unchanged -- it
    already declares ``position_scope: strategy_ledger`` in production
    (four strategies now share this paper account)."""
    spec_path = root / "strategy_specs" / "drafts" / REPO_SPEC.name
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(REPO_SPEC.read_text(encoding="utf-8"), encoding="utf-8")
    return spec_path


def _broker_account_spec(root: Path) -> Path:
    """Same spec with ``position_scope`` removed, so it falls back to the
    documented default -- proves the default path is untouched."""
    text = REPO_SPEC.read_text(encoding="utf-8").replace("  position_scope: strategy_ledger\n", "")
    assert "position_scope" not in text
    spec_path = root / "strategy_specs" / "drafts" / REPO_SPEC.name
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(text, encoding="utf-8")
    return spec_path


def _write_targets_with_summary(
    root: Path, name: str, rows: list[dict], summary: dict, *, generated_at: datetime
) -> None:
    path = root / "reports" / "execution" / f"{name}-target-weights.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "strategy_name": name,
                "generated_at": generated_at.isoformat(),
                "portfolio_mode": "model_ranking_portfolio",
                "summary": summary,
                "target_weights": rows,
            }
        ),
        encoding="utf-8",
    )


def _write_fills(root: Path, name: str, rows: list[dict]) -> None:
    path = rehearsal_fills_path(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _fill_row(
    *,
    session: str,
    symbol: str,
    side: str,
    filled_qty: float,
    status: str = "filled",
    reference_price: float = 100.0,
    client_order_id: str = "reh-fixture",
) -> dict:
    """A row shaped like ``reconcile_rehearsal_fills`` actually writes
    (real example from ``{name}-fills.jsonl``)."""
    return {
        "session": session,
        "symbol": symbol,
        "side": side,
        "qty": filled_qty,
        "reference_price": reference_price,
        "order_style": "day_market",
        "client_order_id": client_order_id,
        "broker_order_id": f"ord-{client_order_id}",
        "status": status,
        "filled_qty": filled_qty if status == "filled" else 0.0,
        "filled_avg_price": reference_price if status == "filled" else None,
        "filled_at": "2026-09-15T13:30:00" if status == "filled" else "",
        "fill_fraction": 1.0 if status == "filled" else 0.0,
        "slippage_vs_reference_bps": 0.0 if status == "filled" else None,
    }


@pytest.fixture
def ledger_workspace(sample_workspace: Path) -> tuple[Path, Path]:
    spec_path = _strategy_ledger_spec(sample_workspace)
    name = load_strategy_spec(spec_path).name
    _write_targets(
        sample_workspace,
        name,
        _rows(("AAPL", 0.05, 200.0), ("MSFT", 0.05, 400.0), ("NVDA", 0.04, 100.0)),
        generated_at=SUBMIT_TIME - timedelta(hours=1),
    )
    return sample_workspace, spec_path


@pytest.fixture
def broker_account_workspace(sample_workspace: Path) -> tuple[Path, Path]:
    spec_path = _broker_account_spec(sample_workspace)
    name = load_strategy_spec(spec_path).name
    _write_targets(
        sample_workspace,
        name,
        _rows(("AAPL", 0.05, 200.0), ("MSFT", 0.05, 400.0), ("NVDA", 0.04, 100.0)),
        generated_at=SUBMIT_TIME - timedelta(hours=1),
    )
    return sample_workspace, spec_path


# ---------------------------------------------------------------------------
# default / absent position_scope: unchanged behaviour


def test_absent_position_scope_still_sells_broker_held_symbol(broker_account_workspace) -> None:
    """No ``position_scope`` key -> ``broker_account`` default: a symbol held
    in the broker account but not in current targets is still sold using the
    account's own quantity, exactly like every spec written before this
    feature -- the same scenario and assertions as
    ``test_paper_rehearsal.test_submit_then_rerun_is_idempotent``."""
    root, spec_path = broker_account_workspace
    held = SimpleNamespace(symbol="META", qty="10", current_price="500", market_value="5000")
    client = FakeClient(positions=[held])
    _authorize(root, spec_path, client)

    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=SUBMIT_TIME
    )
    assert result.position_scope == "broker_account"
    assert result.status == "submitted"
    assert result.counts() == {"submitted": 4}
    assert result.plans[0].symbol == "META" and result.plans[0].side == "sell"
    assert result.plans[0].qty == 10
    assert result.scoped_positions == {}


# ---------------------------------------------------------------------------
# strategy_ledger: ignores other strategies' broker positions


def test_strategy_ledger_does_not_sell_another_strategys_position(ledger_workspace) -> None:
    root, spec_path = ledger_workspace
    # META is held in the broker account (by some other strategy) but this
    # strategy has never traded it -- it has no fills ledger at all.
    held = SimpleNamespace(symbol="META", qty="10", current_price="500", market_value="5000")
    client = FakeClient(positions=[held])
    _authorize(root, spec_path, client)

    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=SUBMIT_TIME
    )
    assert result.position_scope == "strategy_ledger"
    assert result.status == "submitted"
    assert result.counts() == {"submitted": 3}
    assert all(plan.symbol != "META" for plan in result.plans)
    assert result.scoped_positions == {}


def test_missing_ledger_file_means_flat_book_all_buys(ledger_workspace) -> None:
    root, spec_path = ledger_workspace
    client = FakeClient()  # no broker positions, no fills ledger file at all
    _authorize(root, spec_path, client)

    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
    )
    assert result.position_scope == "strategy_ledger"
    assert result.scoped_positions == {}
    assert result.plans and all(plan.side == "buy" for plan in result.plans)
    assert result.counts() == {"would_submit": 3}


def test_strategy_ledger_sells_its_own_ledger_qty_not_account_qty(sample_workspace: Path) -> None:
    root = sample_workspace
    spec_path = _strategy_ledger_spec(root)
    name = load_strategy_spec(spec_path).name
    # AAPL has rotated out of this strategy's current targets.
    _write_targets(
        root,
        name,
        _rows(("MSFT", 0.05, 400.0), ("NVDA", 0.04, 100.0)),
        generated_at=SUBMIT_TIME - timedelta(hours=1),
    )
    _write_fills(
        root,
        name,
        [
            _fill_row(
                session="2026-09-15",
                symbol="AAPL",
                side="buy",
                filled_qty=30.0,
                client_order_id="reh-aapl-1",
            )
        ],
    )
    # The broker account shows a much larger AAPL position because another
    # strategy also holds it.
    held = SimpleNamespace(symbol="AAPL", qty="999", current_price="205", market_value="204795")
    client = FakeClient(positions=[held])
    _authorize(root, spec_path, client)

    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=SUBMIT_TIME
    )
    assert result.position_scope == "strategy_ledger"
    assert result.scoped_positions == {"AAPL": 30.0}
    assert result.counts() == {"submitted": 3}
    sell = next(plan for plan in result.plans if plan.symbol == "AAPL")
    assert sell.side == "sell" and sell.qty == 30.0
    # the account holds AAPL, so the broker's current_price is used
    assert sell.reference_price == 205.0


def test_strategy_ledger_overlap_uses_only_this_strategys_qty(sample_workspace: Path) -> None:
    """Two strategies both hold XLK. Strategy A's own ledger says 5 shares;
    the broker account shows 15 (5 + another sleeve's 10). Strategy A must
    plan its rebalance against 5, not 15 -- using 15 would flip a buy into a
    sell."""
    root = sample_workspace
    spec_path = _strategy_ledger_spec(root)
    name = load_strategy_spec(spec_path).name
    # target weight 0.008 * 100,000 account_equity / 100 price -> 8 shares
    _write_targets(
        root, name, _rows(("XLK", 0.008, 100.0)), generated_at=SUBMIT_TIME - timedelta(hours=1)
    )
    _write_fills(
        root,
        name,
        [
            _fill_row(
                session="2026-09-15",
                symbol="XLK",
                side="buy",
                filled_qty=5.0,
                client_order_id="reh-xlk-a",
            )
        ],
    )
    held = SimpleNamespace(symbol="XLK", qty="15", current_price="100", market_value="1500")
    client = FakeClient(positions=[held])
    _authorize(root, spec_path, client)

    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
    )
    assert result.scoped_positions == {"XLK": 5.0}
    plan = next(p for p in result.plans if p.symbol == "XLK")
    assert plan.current_qty == 5.0
    # correct (against 5): target 8 - current 5 = buy 3.
    # wrong (against the account's 15): target 8 - current 15 = sell 7.
    assert plan.side == "buy" and plan.qty == 3


def test_ledger_nets_buys_and_sells_across_sessions(ledger_workspace) -> None:
    root, spec_path = ledger_workspace
    name = load_strategy_spec(spec_path).name
    _write_fills(
        root,
        name,
        [
            _fill_row(
                session="2026-09-10",
                symbol="IWM",
                side="buy",
                filled_qty=10.0,
                client_order_id="reh-iwm-1",
            ),
            _fill_row(
                session="2026-09-15",
                symbol="IWM",
                side="sell",
                filled_qty=4.0,
                client_order_id="reh-iwm-2",
            ),
        ],
    )
    client = FakeClient()
    _authorize(root, spec_path, client)

    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
    )
    assert result.scoped_positions == {"IWM": 6.0}


def test_ledger_position_not_held_anywhere_in_account_uses_artifact_reference_price(
    sample_workspace: Path,
) -> None:
    root = sample_workspace
    spec_path = _strategy_ledger_spec(root)
    name = load_strategy_spec(spec_path).name
    rows = _rows(("MSFT", 0.05, 400.0))
    # GLD dropped out of the book (unselected) but the artifact still carries
    # its reference_price for this session.
    rows.append(
        {
            "rebalance_id": "reb-2026-09-11",
            "symbol": "GLD",
            "target_weight": 0.0,
            "reference_price": 180.0,
            "selected": False,
            "leg": "cash",
        }
    )
    _write_targets(root, name, rows, generated_at=SUBMIT_TIME - timedelta(hours=1))
    _write_fills(
        root,
        name,
        [
            _fill_row(
                session="2026-09-15",
                symbol="GLD",
                side="buy",
                filled_qty=4.0,
                reference_price=178.0,
                client_order_id="reh-gld-1",
            )
        ],
    )
    client = FakeClient()  # the broker account holds none of GLD at all
    _authorize(root, spec_path, client)

    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
    )
    sell = next(plan for plan in result.plans if plan.symbol == "GLD")
    assert sell.side == "sell" and sell.qty == 4.0
    assert sell.reference_price == 180.0  # fallback: the artifact's own reference_price


# ---------------------------------------------------------------------------
# fail-closed guard: unreconciled ledger rows


def test_unreconciled_earlier_session_row_fails_closed(ledger_workspace) -> None:
    root, spec_path = ledger_workspace
    name = load_strategy_spec(spec_path).name
    _write_fills(
        root,
        name,
        [
            _fill_row(
                session="2026-09-15",
                symbol="AAOI",
                side="buy",
                filled_qty=18.0,
                status="new",  # still open at the broker -- not reconciled
                client_order_id="reh-aaoi-1",
            )
        ],
    )
    client = FakeClient()
    _authorize(root, spec_path, client)

    with pytest.raises(RehearsalError, match="2026-09-15"):
        run_portfolio_paper_rehearsal(
            spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
        )


def test_unreconciled_row_with_unknown_status_also_fails_closed(ledger_workspace) -> None:
    root, spec_path = ledger_workspace
    name = load_strategy_spec(spec_path).name
    _write_fills(
        root,
        name,
        [
            _fill_row(
                session="2026-09-14",
                symbol="AAOI",
                side="buy",
                filled_qty=18.0,
                status="unknown",  # order not found at the broker at all
                client_order_id="reh-aaoi-2",
            )
        ],
    )
    client = FakeClient()
    _authorize(root, spec_path, client)

    with pytest.raises(RehearsalError, match="unreconciled"):
        run_portfolio_paper_rehearsal(
            spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
        )


def test_terminal_earlier_session_row_does_not_trigger_the_guard(ledger_workspace) -> None:
    """Sanity check: a resolved (terminal) earlier-session row is fine --
    only a still-open or unknown-status row must fail closed."""
    root, spec_path = ledger_workspace
    name = load_strategy_spec(spec_path).name
    _write_fills(
        root,
        name,
        [
            _fill_row(
                session="2026-09-15",
                symbol="AAOI",
                side="buy",
                filled_qty=0.0,
                status="expired",
                client_order_id="reh-aaoi-3",
            )
        ],
    )
    client = FakeClient()
    _authorize(root, spec_path, client)

    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
    )
    assert result.status == "dry_run"
    assert "AAOI" not in result.scoped_positions


# ---------------------------------------------------------------------------
# sizing equity: the strategy's own budget, not the whole account


def test_strategy_ledger_sizes_against_capped_sizing_equity_not_account_equity(
    sample_workspace: Path,
) -> None:
    """Mirrors an ETF-rotation sleeve: the paper account is $100k but this
    strategy's own ``notional_budget_usd`` caps its sizing equity at $15k.
    Target quantities and the gross-exposure budget must use the $15k
    ``sizing_equity``, not the $100k ``account_equity``."""
    root = sample_workspace
    spec_path = _strategy_ledger_spec(root)
    name = load_strategy_spec(spec_path).name
    _write_targets_with_summary(
        root,
        name,
        _rows(("XLK", 0.5, 100.0)),
        {"account_equity": 100_000.0, "sizing_equity": 15_000.0},
        generated_at=SUBMIT_TIME - timedelta(hours=1),
    )
    client = FakeClient()
    _authorize(root, spec_path, client)

    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
    )
    assert result.sizing_equity == 15_000.0
    plan = next(p for p in result.plans if p.symbol == "XLK")
    # weight 0.5 capped to max_symbol_weight=0.05 -> floor(0.05 * 15,000 / 100) = 7
    # (using the account's 100,000 instead would wrongly give 50)
    assert plan.qty == 7


def test_strategy_ledger_requires_a_sizing_equity_in_the_artifact(sample_workspace: Path) -> None:
    root = sample_workspace
    spec_path = _strategy_ledger_spec(root)
    name = load_strategy_spec(spec_path).name
    _write_targets_with_summary(
        root,
        name,
        _rows(("MSFT", 0.05, 400.0)),
        {},  # neither sizing_equity nor account_equity recorded
        generated_at=SUBMIT_TIME - timedelta(hours=1),
    )
    client = FakeClient()
    _authorize(root, spec_path, client)

    with pytest.raises(RehearsalError, match="sizing_equity"):
        run_portfolio_paper_rehearsal(
            spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
        )
