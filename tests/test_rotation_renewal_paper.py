"""The 2026-09-23 S1-S3 renewal on the paper path.

Covers the rotation adapter with a volatility target, ``sizing_basis=
sleeve_equity`` and a drawdown guard on a synthetic archive; the planner's
gross check once same-open sells are netted out (the S2 XLK buy that stayed
deferred from 09-21) and its clipping of a buy that only partly fits; and
the drawdown exit on the real S3 spec -- liquidation, the latch, and the
authorization revoked once the ledger is flat.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from open_composer.adapters.execution.rotation_target_weights import (
    run_rotation_target_weight_mapping_for_spec,
)
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_rehearsal import (
    drawdown_exit_latch_path,
    plan_rehearsal_orders,
    rehearsal_authorization_path,
    run_portfolio_paper_rehearsal,
)
from tests.test_paper_rehearsal import SUBMIT_TIME, FakeClient, _authorize
from tests.test_paper_rehearsal_strategy_ledger import _fill_row, _write_fills
from tests.test_rotation_target_weights import (
    _build_spec,
    _sip_rows,
    _spec_path,
    _write_account,
    _write_sip_daily,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
S3_SPEC = REPO_ROOT / "strategy_specs" / "drafts" / "us_etf_levered_rotation_63_top2_monthly.yaml"
LIMITS = {
    "max_gross_exposure": 1.0,
    "max_orders_per_session": 10,
    "max_session_notional_usd": 40_000.0,
    "max_symbol_weight": 1.0,
    "max_total_notional_usd": 300_000.0,
}


# ---------------------------------------------------------------------------
# adapter: volatility target + sleeve equity + drawdown guard


def _renewal_config(**overrides) -> SimpleNamespace:
    values = dict(
        menu=["AAA", "BBB"],
        cash_symbol="SHY",
        # Even, so the +-3% daily swing cancels and AAA's trend decides the rank.
        lookbacks=[20],
        top_n=1,
        rebalance="monthly_last_session",
        absolute_momentum_filter=True,
        min_history_sessions=30,
        notional_budget_usd=15_000.0,
        unfilled_slot_policy="renormalize_survivors",
        vol_target=SimpleNamespace(
            target_annual_vol=0.10, realized_vol_sessions=21, dip_boost=None
        ),
        sizing_basis="sleeve_equity",
        drawdown_exit_pct=0.15,
        rebalance_tolerance_fraction=0.05,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _renewal_archive(root: Path) -> list[date]:
    days = [d.date() for d in pd.bdate_range("2026-04-01", "2026-09-15")]
    # AAA trends up while swinging +-3% a day (realized vol ~95%); BBB falls.
    aaa = {d: 100.0 * 1.002**i * (1.03 if i % 2 else 0.97) for i, d in enumerate(days)}
    bbb = {d: 100.0 * 0.999**i for i, d in enumerate(days)}
    shy = {d: 80.0 * 1.00005**i for i, d in enumerate(days)}
    _write_sip_daily(root, _sip_rows({"AAA": aaa, "BBB": bbb, "SHY": shy}))
    _write_account(root, 100_000.0)
    return days


def test_vol_target_scales_the_book_and_sizes_on_sleeve_equity(tmp_path: Path) -> None:
    days = _renewal_archive(tmp_path)
    name = "renewal_fixture"
    spec = _build_spec(name=name)
    first = days.index(date(2026, 9, 1))
    aaa_buy = 100.0 * 1.002**first * (1.03 if first % 2 else 0.97)
    _write_fills(
        tmp_path,
        name,
        [
            {
                **_fill_row(session="2026-09-01", symbol="AAA", side="buy", filled_qty=50.0),
                "filled_avg_price": aaa_buy,
            }
        ],
    )
    result = run_rotation_target_weight_mapping_for_spec(
        spec,
        _renewal_config(),
        _spec_path(tmp_path, name),
        tmp_path,
        as_of=datetime(2026, 9, 15, 23, tzinfo=UTC),
    )
    manifest = result.manifest
    overlay = manifest["vol_target"]
    assert manifest["signal_session"] == "2026-08-31"
    assert manifest["anchor_session"] == "2026-08-31"
    assert overlay["book_weights"] == {"AAA": 1.0, "SHY": 0.0}
    assert overlay["realized_annual_vol"] > 0.5
    assert overlay["multiplier"] == pytest.approx(0.10 / overlay["realized_annual_vol"])
    rows = {row["symbol"]: row for row in json.loads(result.target_weights_path.read_text())[
        "target_weights"
    ]}  # fmt: skip
    assert rows["AAA"]["target_weight"] == pytest.approx(overlay["multiplier"])
    assert rows["SHY"]["target_weight"] == pytest.approx(1.0 - overlay["multiplier"])
    # Reference prices come from the anchor close, not the latest one.
    anchor = days.index(date(2026, 8, 31))
    assert rows["AAA"]["reference_price"] == pytest.approx(
        100.0 * 1.002**anchor * (1.03 if anchor % 2 else 0.97)
    )
    guard = manifest["sleeve_guard"]
    last = len(days) - 1
    aaa_last = 100.0 * 1.002**last * (1.03 if last % 2 else 0.97)
    assert guard["equity_latest"] == pytest.approx(15_000.0 + 50 * (aaa_last - aaa_buy))
    assert guard["first_fill_session"] == "2026-09-01"
    # The anchor close precedes the first fill, so sizing uses the starting equity.
    assert guard["equity_at_anchor"] == pytest.approx(15_000.0)
    assert manifest["sizing_equity"] == pytest.approx(15_000.0)
    assert guard["drawdown"] == pytest.approx(1.0 - guard["equity_latest"] / guard["peak_equity"])
    assert guard["drawdown_exit_breached"] is (guard["drawdown"] >= 0.15)


def test_without_overlay_the_adapter_keeps_the_signal_session_anchor(tmp_path: Path) -> None:
    _renewal_archive(tmp_path)
    name = "renewal_plain"
    result = run_rotation_target_weight_mapping_for_spec(
        _build_spec(name=name),
        _renewal_config(vol_target=None, sizing_basis="notional_budget", drawdown_exit_pct=None),
        _spec_path(tmp_path, name),
        tmp_path,
        as_of=datetime(2026, 9, 15, 23, tzinfo=UTC),
    )
    assert result.manifest["vol_target"] is None
    assert result.manifest["sleeve_guard"] is None
    assert result.manifest["anchor_session"] == result.manifest["signal_session"]
    assert result.manifest["sizing_equity"] == pytest.approx(15_000.0)


# ---------------------------------------------------------------------------
# planner: gross after same-open sells, clipping, tolerance


def _row(symbol: str, weight: float, price: float) -> dict:
    return {
        "symbol": symbol,
        "target_weight": weight,
        "reference_price": price,
        "selected": weight > 0,
        "rebalance_id": "s2:2026-08-31",
    }


def test_same_open_sell_frees_gross_for_the_rotation_buy() -> None:
    # The S2 case from 2026-09-21: SMH rose after it was bought, so held SMH
    # plus the full XLK buy exceeded the 1.0 cap every night and XLK never
    # went in. Selling part of SMH at the same open must count.
    plans = plan_rehearsal_orders(
        target_rows=[_row("SMH", 0.2577, 556.63), _row("XLK", 0.2577, 186.50),
                     _row("SHY", 0.4847, 81.65)],
        positions={"SMH": 13.0},
        position_prices={"SMH": 600.0},
        open_order_symbols=set(),
        equity=15_000.0,
        limits=LIMITS,
        churn_tolerance_fraction=0.05,
    )  # fmt: skip
    by_symbol = {plan.symbol: plan for plan in plans}
    assert by_symbol["SMH"].side == "sell" and by_symbol["SMH"].qty == 7
    assert by_symbol["SMH"].decision == "submit"
    assert by_symbol["XLK"].decision == "submit" and by_symbol["XLK"].qty == 20
    assert by_symbol["SHY"].decision == "submit"
    held_after = 6 * 600.0
    bought = sum(p.notional for p in plans if p.side == "buy" and p.decision == "submit")
    assert held_after + bought <= 15_000.0 + 1e-6


def test_buy_that_only_partly_fits_is_clipped_not_deferred() -> None:
    plans = plan_rehearsal_orders(
        target_rows=[_row("SMH", 0.5, 500.0), _row("XLK", 0.5, 100.0)],
        positions={"SMH": 15.0},
        position_prices={"SMH": 540.0},
        open_order_symbols=set(),
        equity=15_000.0,
        limits=LIMITS,
    )
    xlk = next(plan for plan in plans if plan.symbol == "XLK")
    # SMH is already at its 15-share target and worth 8,100 at today's price,
    # which leaves room for 69 of the 75 XLK shares.
    assert xlk.decision == "submit"
    assert xlk.qty == 69
    assert "clipped from 75 to 69" in xlk.reason


def test_tolerance_override_lets_a_small_multiplier_move_trade() -> None:
    kwargs = dict(
        target_rows=[_row("UPRO", 0.72, 150.0)],
        positions={"UPRO": 79.0},
        position_prices={"UPRO": 150.0},
        open_order_symbols=set(),
        equity=15_000.0,
        limits=LIMITS,
    )
    default = plan_rehearsal_orders(**kwargs)
    assert default[0].decision == "skip_below_tolerance"
    tight = plan_rehearsal_orders(**kwargs, churn_tolerance_fraction=0.05)
    assert tight[0].decision == "submit" and tight[0].side == "sell" and tight[0].qty == 7


# ---------------------------------------------------------------------------
# drawdown exit on the real S3 spec


def _s3_workspace(root: Path) -> Path:
    spec_path = root / "strategy_specs" / "drafts" / S3_SPEC.name
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(S3_SPEC.read_text(encoding="utf-8"), encoding="utf-8")
    return spec_path


def _write_s3_targets(root: Path, name: str, *, drawdown: float) -> None:
    path = root / "reports" / "execution" / f"{name}-target-weights.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "account_equity": 100_000.0,
        "sizing_equity": 15_000.0,
        "sleeve_guard": {
            "equity_latest": 15_000.0 * (1 - drawdown),
            "peak_equity": 15_000.0,
            "drawdown": drawdown,
            "marked_through": "2026-09-16",
        },
    }
    rows = [
        {**_row("UPRO", 0.79, 150.0), "shares": 79},
        {**_row("SHY", 0.21, 81.65), "shares": 38},
    ]
    path.write_text(
        json.dumps(
            {
                "strategy_name": name,
                "generated_at": (SUBMIT_TIME - timedelta(hours=1)).isoformat(),
                "portfolio_mode": "etf_rotation_portfolio",
                "summary": summary,
                "target_weights": rows,
            }
        ),
        encoding="utf-8",
    )


def test_drawdown_exit_liquidates_latches_and_revokes_once_flat(sample_workspace: Path) -> None:
    root = sample_workspace
    spec_path = _s3_workspace(root)
    name = load_strategy_spec(spec_path).name
    _write_fills(
        root,
        name,
        [_fill_row(session="2026-09-15", symbol="UPRO", side="buy", filled_qty=99.0,
                   reference_price=150.0, client_order_id="reh-upro-1")],
    )  # fmt: skip
    client = FakeClient(
        positions=[SimpleNamespace(symbol="UPRO", qty="99", current_price="110", market_value="0")]
    )
    _authorize(root, spec_path, client, limits=LIMITS)
    _write_s3_targets(root, name, drawdown=0.27)

    first = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=SUBMIT_TIME
    )
    assert first.status == "submitted"
    assert [(p.symbol, p.side, p.qty) for p in first.plans if p.decision == "submitted"] == [
        ("UPRO", "sell", 99.0)
    ]
    assert all(plan.side == "sell" for plan in first.plans)
    assert drawdown_exit_latch_path(root, name).is_file()
    # Not flat yet: the authorization stays so the next run can finish the exit.
    assert rehearsal_authorization_path(root, name).is_file()

    # The sell filled; the marked drawdown no longer matters -- the latch holds.
    _write_fills(
        root,
        name,
        [
            _fill_row(session="2026-09-15", symbol="UPRO", side="buy", filled_qty=99.0,
                      reference_price=150.0, client_order_id="reh-upro-1"),
            _fill_row(session="2026-09-17", symbol="UPRO", side="sell", filled_qty=99.0,
                      reference_price=110.0, client_order_id="reh-upro-2"),
        ],
    )  # fmt: skip
    client.positions = []
    _write_s3_targets(root, name, drawdown=0.05)
    second = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=True, client=client, now=SUBMIT_TIME
    )
    assert not [p for p in second.plans if p.decision == "submitted"]
    assert not rehearsal_authorization_path(root, name).is_file()
    assert any("revoked" in note for note in second.notes)
    events = sorted((root / "reports" / "paper" / "control_history" / "drawdown_exit").glob("*"))
    assert [path.name.split("-", 1)[1] for path in events] == [
        f"{name}-triggered.json",
        f"{name}-authorization_revoked.json",
    ]


def test_drawdown_below_the_limit_trades_normally(sample_workspace: Path) -> None:
    root = sample_workspace
    spec_path = _s3_workspace(root)
    name = load_strategy_spec(spec_path).name
    client = FakeClient()
    _authorize(root, spec_path, client, limits=LIMITS)
    _write_s3_targets(root, name, drawdown=0.10)
    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
    )
    assert {p.symbol for p in result.plans if p.side == "buy"} == {"UPRO", "SHY"}
    assert not drawdown_exit_latch_path(root, name).exists()


def test_dry_run_breach_plans_the_exit_without_latching(sample_workspace: Path) -> None:
    root = sample_workspace
    spec_path = _s3_workspace(root)
    name = load_strategy_spec(spec_path).name
    _write_fills(
        root,
        name,
        [_fill_row(session="2026-09-15", symbol="UPRO", side="buy", filled_qty=99.0,
                   reference_price=150.0, client_order_id="reh-upro-1")],
    )  # fmt: skip
    client = FakeClient(
        positions=[SimpleNamespace(symbol="UPRO", qty="99", current_price="110", market_value="0")]
    )
    _authorize(root, spec_path, client, limits=LIMITS)
    _write_s3_targets(root, name, drawdown=0.30)
    result = run_portfolio_paper_rehearsal(
        spec_path, root, allow_paper_orders=False, client=client, now=SUBMIT_TIME
    )
    assert [(p.symbol, p.side, p.decision) for p in result.plans] == [
        ("UPRO", "sell", "would_submit")
    ]
    assert not drawdown_exit_latch_path(root, name).exists()
    assert rehearsal_authorization_path(root, name).is_file()
