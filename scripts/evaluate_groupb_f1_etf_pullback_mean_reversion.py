"""Step 12 Group B F1: ETF pullback mean reversion, real SIP daily bars.

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 2 (F1) and section 3 (Wednesday 2026-09-09 22:00 UTC deadline for
F1's ledger entry).

Loads SPY/QQQ/IWM/XLK/SMH/XLF/XLE/XLV/XLY/XLI + BIL daily bars from
``data/sip/daily`` (``open_composer.adapters.data.sip_parquet.load_sip_bars``),
runs the 12-cell preregistered grid
(``open_composer.research.regime.etf_pullback_mean_reversion``), walk-
forward selects one cell per calendar quarter by trailing 24-month daily
Sharpe over the *entire* available history (not only the recent gated
window -- the earlier quarters become the 2018-2023 disclosure evidence),
scores the resulting composite against
``config/promotion/recent-regime-high-hit-rate-gates.json``
(``open_composer.research.regime.gates``), appends one row to
``reports/research/ledger/experiments.jsonl`` (family
``groupb_recent_regime_high_hit_rate``), and prints the verdict.

Memory: run via ``./scripts/run_capped.sh --mem 0.6G -- uv run python
scripts/evaluate_groupb_f1_etf_pullback_mean_reversion.py`` -- Step 12's
current constraint while Group A's LightGBM grid is running (data volume
here is 11 symbols of daily bars, a few MB, well inside the cap).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.research.regime import etf_pullback_mean_reversion as f1
from open_composer.research.regime import gates as regime_gates
from open_composer.research.regime import metrics as regime_metrics

EXPERIMENT_ID = "groupb_f1_etf_pullback_mean_reversion_v1"
ROOT = Path(__file__).resolve().parents[1]
#: Weight-turnover contribution of one round-trip trade at a fixed 1/10
#: slot: entry (0 -> 1/10) plus exit (1/10 -> 0) = 0.2 of "loop.py-style"
#: sum(|delta weight|) turnover, the same convention
#: returns_from_weight_schedule uses for its own cost accounting.
TURNOVER_PER_TRADE = 2.0 / len(f1.SYMBOLS)


def _config_hash() -> str:
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "symbols": list(f1.SYMBOLS),
        "cash_symbol": f1.CASH_SYMBOL,
        "grid": [f1.cell_id(i) for i in range(len(f1.PARAMETER_SPACE))],
        "parameter_space": f1.PARAMETER_SPACE,
        "cost_bps_per_side": f1.COST_BPS_PER_SIDE,
        "stress_cost_bps_per_side": f1.STRESS_COST_BPS_PER_SIDE,
        "lookback_months": f1.LOOKBACK_MONTHS,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def main() -> None:
    all_symbols = [*f1.SYMBOLS, f1.CASH_SYMBOL]
    print(f"loading SIP daily bars for {all_symbols}...", flush=True)
    raw = load_sip_bars(all_symbols, frequency="daily")
    aligned = f1.load_common_bars(raw, all_symbols)
    bars = {symbol: aligned[symbol] for symbol in f1.SYMBOLS}
    bil_frame = aligned[f1.CASH_SYMBOL]
    print(
        f"common index: {bil_frame.index.min().date()}..{bil_frame.index.max().date()}, "
        f"{len(bil_frame)} rows",
        flush=True,
    )

    warmup_complete_date = f1.compute_warmup_complete_date(bars)
    print(f"SMA200 warmup complete: {warmup_complete_date.date()}", flush=True)

    cell_returns: dict[str, pd.Series] = {}
    cell_stress_returns: dict[str, pd.Series] = {}
    cell_trades: dict[str, list[f1.TradeRecord]] = {}
    cell_stress_trades: dict[str, list[f1.TradeRecord]] = {}
    for i, params in enumerate(f1.PARAMETER_SPACE):
        cell = f1.cell_id(i)
        base_returns, base_trades = f1.simulate_cell_portfolio(
            cell, bars, bil_frame, params, cost_bps_per_side=f1.COST_BPS_PER_SIDE
        )
        stress_returns, stress_trades = f1.simulate_cell_portfolio(
            cell, bars, bil_frame, params, cost_bps_per_side=f1.STRESS_COST_BPS_PER_SIDE
        )
        cell_returns[cell] = base_returns
        cell_stress_returns[cell] = stress_returns
        cell_trades[cell] = base_trades
        cell_stress_trades[cell] = stress_trades
        print(f"  {cell} {params}: {len(base_trades)} trades (base cost)", flush=True)

    selection_log = f1.select_cells_by_quarter(
        cell_returns,
        warmup_complete_date=warmup_complete_date,
        lookback_months=f1.LOOKBACK_MONTHS,
    )
    if not selection_log:
        raise SystemExit("no eligible quarter -- insufficient history for a 24-month lookback")
    print(
        f"{len(selection_log)} quarters selected, "
        f"{selection_log[0].quarter_start}..{selection_log[-1].quarter_end}",
        flush=True,
    )
    for selection in selection_log:
        print(
            f"  {selection.quarter_start}..{selection.quarter_end}: "
            f"{selection.selected_cell} (trailing daily Sharpe "
            f"{selection.trailing_daily_sharpe})",
            flush=True,
        )

    composite_returns, composite_trades = f1.materialize_composite(
        cell_returns, cell_trades, selection_log
    )
    composite_stress_returns, _ = f1.materialize_composite(
        cell_stress_returns, cell_stress_trades, selection_log
    )

    # Standard close-to-close benchmark convention (same mismatch already
    # accepted between run_experiment's next_open candidates and its
    # close-based bil_returns -- see loop.py's module docstring).
    bil_returns = bil_frame["close"].pct_change().dropna()

    recent_cutoff = pd.Timestamp(regime_gates.RECENT_WINDOW_START, tz="UTC")
    recent_trades = [
        trade
        for trade in composite_trades
        if pd.Timestamp(trade.exit_fill_date, tz="UTC") >= recent_cutoff
    ]
    disclosure_trades = [
        trade
        for trade in composite_trades
        if pd.Timestamp(trade.exit_fill_date, tz="UTC") < recent_cutoff
    ]
    if not recent_trades:
        raise SystemExit(
            "no completed trades in the recent gated window -- cannot compute hit rate"
        )

    recent_slice = composite_returns.loc[composite_returns.index >= recent_cutoff]
    recent_years = regime_metrics.window_years(recent_slice)
    turnover_annualized_recent = TURNOVER_PER_TRADE * regime_metrics.annualized_trade_count(
        len(recent_trades), years=recent_years
    )

    config_hash = _config_hash()
    verdict = regime_gates.evaluate_regime_candidate(
        experiment_id=EXPERIMENT_ID,
        config_hash=config_hash,
        full_returns=composite_returns,
        full_stress_returns=composite_stress_returns,
        bil_returns=bil_returns,
        holding_period="daily_or_intraday",
        holding_period_net_returns_recent=[trade.net_return for trade in recent_trades],
        holding_period_net_returns_disclosure=(
            [trade.net_return for trade in disclosure_trades] if disclosure_trades else None
        ),
        trade_count_recent=len(recent_trades),
        turnover_annualized_recent=turnover_annualized_recent,
        family=regime_gates.LEDGER_FAMILY,
    )

    print(json.dumps(verdict.model_dump(), indent=2, default=str), flush=True)
    print(
        f"all_gates_pass={verdict.all_gates_pass} promotion_eligible={verdict.promotion_eligible}"
    )

    record = {
        "experiment_id": verdict.experiment_id,
        "config_hash": verdict.config_hash,
        "family": verdict.family,
        "mechanism": "etf_pullback_mean_reversion",
        "symbols": list(f1.SYMBOLS),
        "holding_period": verdict.holding_period,
        "is_ml": verdict.is_ml,
        "reference_only": verdict.reference_only,
        "cost_bps_per_side": f1.COST_BPS_PER_SIDE,
        "stress_cost_bps_per_side": f1.STRESS_COST_BPS_PER_SIDE,
        "grid": [f1.cell_id(i) for i in range(len(f1.PARAMETER_SPACE))],
        "parameter_space": f1.PARAMETER_SPACE,
        "selection_log": [selection.model_dump() for selection in selection_log],
        "trade_count_disclosure_pre_2024": len(disclosure_trades),
        "dsr_trial_count": verdict.dsr_trial_count,
        "metrics": verdict.metrics,
        "disclosure": verdict.disclosure,
        "gate_results": verdict.gate_results,
        "gates_not_applicable": list(verdict.gates_not_applicable),
        "all_gates_pass": verdict.all_gates_pass,
        "promotion_eligible": verdict.promotion_eligible,
        "gates_provenance": verdict.gates_provenance,
        "gate_contract": verdict.gate_contract,
        "recorded_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    appended = regime_gates.append_ledger(record)
    print(f"ledger appended: {appended} -> {regime_gates.LEDGER_PATH}")


if __name__ == "__main__":
    main()
