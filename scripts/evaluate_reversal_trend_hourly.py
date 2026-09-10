"""Step 13-P A3: Reversal Trend, 1h-bar strategy evaluation.

docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md
section 2 (A3) + section 4 step 4. Loads ``data/bars/hourly/{year}.parquet``
(2024-01-02 onward), computes ``compute_reversal_trend`` per symbol, and runs
the preregistered 18-cell grid (holding {6,13,26} 1h bars x exit rule
{time_stop, time_stop_or_reverse, atr_trailing_2x} x signal set {bull_only,
bull_and_recl}) through ``open_composer.research.regime.reversal_trend_hourly``,
long-only (bear/recS are disclosure-only, never candidates -- plan: "空头...
只做披露，不进候选").

Three parallel result sets per cell:
  * **real** -- the actual signal-driven grid, scored against
    ``config/promotion/recent-regime-high-return-gates-v2.json`` via
    ``regime_gates.evaluate_recent_high_return_candidate`` and appended to
    the shared ``step13_recent_high_return`` ledger (family/config_hash
    conventions -- DSR trial counting grows honestly across every Step 13
    track's cells, not just this script's own 18).
  * **placebo** -- same symbol, same per-symbol trade *count*, random entry
    dates (plan: "占位 = 同 symbol 同数量随机日期的信号"), run through the
    identical exit-rule/cost/portfolio machinery. Diagnostic only: not
    ledgered (a placebo is a negative control, not a promotion candidate,
    and ledgering it would inflate the family's DSR trial count with a
    non-candidate run).
  * **trend_gate** -- disclosure-only variant (plan: "同时给出...趋势门变体
    披露"): entries additionally require SPY's own daily close, as of the
    most recently *completed* trading day (no lookahead), to be above its
    200-day SMA. Also not ledgered.

Checkpointing: the real cells get their resumability for free from
``regime_gates.append_ledger``'s existing config_hash dedup (a cell already
in the ledger is skipped, not recomputed). Placebo/trend-gate cells write
their own small JSON checkpoint under ``RESULTS_DIR`` since they never touch
the ledger.

Run via ``./scripts/run_capped.sh --mem 1.8G -- uv run python
scripts/evaluate_reversal_trend_hourly.py``.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.research.pine_port.reversal_trend import (
    ReversalTrendParams,
    compute_reversal_trend,
)
from open_composer.research.regime import gates as regime_gates
from open_composer.research.regime import metrics as regime_metrics
from open_composer.research.regime import reversal_trend_hourly as rth

ROOT = Path(__file__).resolve().parents[1]
HOURLY_BARS_ROOT = ROOT / "data" / "bars" / "hourly"
RESULTS_DIR = ROOT / "reports" / "research" / "artifacts" / "step13_p_reversal_trend_hourly"

EXPERIMENT_PREFIX = "step13_p_rt_hourly"
WINDOW_START = "2024-01-02"
SPY_TREND_SMA_DAYS = 200
PLACEBO_SEED = 20260910


def load_hourly_panel() -> pd.DataFrame:
    years = sorted(
        int(path.stem) for path in HOURLY_BARS_ROOT.glob("*.parquet") if path.stem.isdigit()
    )
    if not years:
        raise SystemExit(f"no hourly bar parquet files under {HOURLY_BARS_ROOT}")
    frames = [pd.read_parquet(HOURLY_BARS_ROOT / f"{year}.parquet") for year in years]
    panel = pd.concat(frames, ignore_index=True)
    panel["timestamp"] = pd.to_datetime(panel["timestamp"], utc=True)
    panel = panel.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
    return panel


def compute_signals_by_symbol(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """compute_reversal_trend grouped by symbol; returns a dict for fast
    per-symbol lookup in the per-cell simulation loop."""
    result = compute_reversal_trend(panel, ReversalTrendParams())
    return {symbol: group.reset_index(drop=True) for symbol, group in result.groupby("symbol")}


def load_daily_return_series(symbol: str, *, start: str) -> pd.Series:
    """Daily close-to-close returns, indexed by NY-normalized calendar date
    -- the same date convention build_hourly_bars/reversal_trend_hourly use
    throughout, so this aligns directly against the strategy's own daily
    return series without a separate re-indexing step."""
    frame = load_sip_bars(symbol, frequency="daily", start=start)
    local_date = frame["timestamp"].dt.tz_convert("America/New_York").dt.normalize()
    close = frame.set_index(local_date)["close"].sort_index()
    return close.pct_change().dropna()


def spy_trend_gate_masks(
    signals_by_symbol: dict[str, pd.DataFrame], spy_daily_close: pd.Series
) -> dict[str, np.ndarray]:
    """Per-symbol boolean array (True = SPY was above its own 200-day SMA as
    of the most recently *completed* trading day before this bar) -- the
    disclosure-only trend gate. No lookahead: an hourly bar on date D only
    ever consults SPY daily data through D-1's close."""
    sma200 = spy_daily_close.rolling(SPY_TREND_SMA_DAYS, min_periods=SPY_TREND_SMA_DAYS).mean()
    # fill_value=False (not .shift()+.fillna()) avoids the boolean series
    # transiently upcasting to object dtype through an intermediate NaN.
    trend_on = (spy_daily_close > sma200).shift(1, fill_value=False)
    masks: dict[str, np.ndarray] = {}
    for symbol, bars in signals_by_symbol.items():
        bar_date = pd.DatetimeIndex(
            bars["timestamp"].dt.tz_convert("America/New_York").dt.normalize()
        )
        masks[symbol] = trend_on.reindex(bar_date, fill_value=False).to_numpy(dtype=bool)
    return masks


def cell_id(holding_bars: int, exit_rule: str, signal_set: str) -> str:
    return f"{EXPERIMENT_PREFIX}_h{holding_bars}_{exit_rule}_{signal_set}"


def config_hash_for_cell(
    holding_bars: int, exit_rule: str, signal_set: str, *, variant: str
) -> str:
    payload = {
        "experiment_prefix": EXPERIMENT_PREFIX,
        "holding_bars": holding_bars,
        "exit_rule": exit_rule,
        "signal_set": signal_set,
        "variant": variant,
        "max_positions": rth.MAX_POSITIONS,
        "position_weight": rth.POSITION_WEIGHT,
        "stock_cost_bps": rth.STOCK_COST_BPS_PER_SIDE,
        "etf_cost_bps": rth.ETF_COST_BPS_PER_SIDE,
        "stress_multiplier": rth.STRESS_COST_MULTIPLIER,
        "window_start": WINDOW_START,
        "bar_source": "data/bars/hourly",
        "placebo_seed": PLACEBO_SEED if variant == "placebo" else None,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def simulate_cell(
    signals_by_symbol: dict[str, pd.DataFrame],
    *,
    holding_bars: int,
    exit_rule: rth.ExitRule,
    signal_set: rth.SignalSet,
    entry_masks: dict[str, np.ndarray] | None = None,
    placebo_counts: dict[str, int] | None = None,
    placebo_seed: int | None = None,
) -> list[rth.TradeCandidate]:
    """All admitted candidates (portfolio-capacity-filtered) for one cell.
    ``placebo_counts``/``placebo_seed`` switch every symbol to
    random-date entries instead of reading its real signal columns.
    """
    all_candidates: list[rth.TradeCandidate] = []
    rng = np.random.default_rng(placebo_seed) if placebo_seed is not None else None
    for symbol, bars in signals_by_symbol.items():
        signal_bar_indices = None
        if placebo_counts is not None:
            count = placebo_counts.get(symbol, 0)
            if count == 0:
                continue
            assert rng is not None
            signal_bar_indices = rth.random_signal_bar_indices(len(bars), count, rng=rng)
        entry_mask = None if entry_masks is None else entry_masks.get(symbol)
        candidates = rth.generate_symbol_candidates(
            symbol,
            bars,
            holding_bars=holding_bars,
            exit_rule=exit_rule,
            signal_set=signal_set,
            entry_mask=entry_mask,
            signal_bar_indices=signal_bar_indices,
        )
        all_candidates.extend(candidates)
    return rth.admit_by_capacity(all_candidates, max_positions=rth.MAX_POSITIONS)


def evaluate_admitted(
    admitted: list[rth.TradeCandidate],
    daily_close_by_symbol: dict[str, pd.Series],
    calendar: pd.DatetimeIndex,
) -> dict:
    base_trades = rth.trades_with_cost(admitted, stress=False)
    stress_trades = rth.trades_with_cost(admitted, stress=True)
    base_portfolio = rth.build_portfolio(base_trades, daily_close_by_symbol, calendar)
    stress_portfolio = rth.build_portfolio(stress_trades, daily_close_by_symbol, calendar)
    return {
        "admitted": admitted,
        "base_trades": base_trades,
        "stress_trades": stress_trades,
        "base_portfolio": base_portfolio,
        "stress_portfolio": stress_portfolio,
    }


def print_cell_summary(label: str, evaluated: dict) -> None:
    n = len(evaluated["admitted"])
    net_returns = [t.net_return for t in evaluated["base_trades"]]
    hit = regime_metrics.hit_rate(net_returns) if net_returns else float("nan")
    pf = regime_metrics.profit_factor(net_returns) if net_returns else float("nan")
    total_return = float((1.0 + evaluated["base_portfolio"].daily_returns).prod() - 1.0)
    print(
        f"  [{label}] trades={n} hit_rate={hit:.3f} profit_factor={pf:.3f} "
        f"cumulative_return={total_return:.4f}",
        flush=True,
    )


def already_in_ledger(config_hash: str, family: str) -> bool:
    path = regime_gates.LEDGER_PATH
    if not path.exists():
        return False
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("family") == family and record.get("config_hash") == config_hash:
            return True
    return False


def main() -> int:
    started = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("loading hourly bar panel...", flush=True)
    panel = load_hourly_panel()
    print(f"  {len(panel)} rows, {panel['symbol'].nunique()} symbols", flush=True)

    print("computing reversal-trend signals per symbol...", flush=True)
    signals_by_symbol = compute_signals_by_symbol(panel)

    print("loading daily benchmark/reference series (SPY, BIL)...", flush=True)
    spy_daily_returns = load_daily_return_series("SPY", start="2016-01-01")
    bil_daily_returns = load_daily_return_series("BIL", start="2016-01-01")
    spy_daily_frame = load_sip_bars("SPY", frequency="daily", start="2016-01-01")
    spy_daily_close = spy_daily_frame.set_index(
        spy_daily_frame["timestamp"].dt.tz_convert("America/New_York").dt.normalize()
    )["close"].sort_index()

    print("building per-symbol daily close series (for daily P&L marking)...", flush=True)
    daily_close_by_symbol = {
        symbol: rth.daily_last_close(bars) for symbol, bars in signals_by_symbol.items()
    }
    # Intersect (never fabricate/fill) the hourly-bar-derived SPY calendar
    # against the real SPY/BIL daily return series, so every day
    # build_portfolio() marks NAV on also has a real benchmark return -- a
    # dropped day here shrinks the window by one row instead of injecting a
    # fake flat 0.0% benchmark return, which would understate SPY/BIL
    # volatility and distort sharpe_excess_bil/vol-matched-SPY-excess-CAGR.
    calendar = daily_close_by_symbol["SPY"].index
    calendar = calendar.intersection(spy_daily_returns.index).intersection(bil_daily_returns.index)
    calendar = calendar[calendar >= pd.Timestamp(WINDOW_START, tz="America/New_York")]
    calendar = calendar.sort_values()

    trend_masks = spy_trend_gate_masks(signals_by_symbol, spy_daily_close)

    spy_recent = spy_daily_returns.reindex(calendar)
    bil_recent = bil_daily_returns.reindex(calendar)
    assert not spy_recent.isna().any(), "SPY benchmark misaligned after intersection (bug)"
    assert not bil_recent.isna().any(), "BIL benchmark misaligned after intersection (bug)"

    real_verdicts: dict[str, dict] = {}
    placebo_summary: dict[str, dict] = {}
    trend_gate_summary: dict[str, dict] = {}

    for holding_bars in rth.HOLDING_BARS_GRID:
        for exit_rule in rth.EXIT_RULES:
            for signal_set in rth.SIGNAL_SETS:
                cid = cell_id(holding_bars, exit_rule, signal_set)
                real_hash = config_hash_for_cell(
                    holding_bars, exit_rule, signal_set, variant="real"
                )
                print(f"\n=== {cid} ===", flush=True)

                if already_in_ledger(real_hash, regime_gates.LEDGER_FAMILY_V2):
                    print(
                        f"  [real] already in ledger (config_hash={real_hash}), skipping",
                        flush=True,
                    )
                    real_verdicts[cid] = {"skipped": True, "config_hash": real_hash}
                    admitted_real = None
                else:
                    admitted_real = simulate_cell(
                        signals_by_symbol,
                        holding_bars=holding_bars,
                        exit_rule=exit_rule,
                        signal_set=signal_set,
                    )
                    evaluated = evaluate_admitted(admitted_real, daily_close_by_symbol, calendar)
                    print_cell_summary("real", evaluated)

                    weekly_returns = rth.weekly_holding_period_net_returns(
                        evaluated["base_portfolio"]
                    )
                    rebalances = rth.rebalances_with_change_per_year(evaluated["base_trades"])
                    full_returns = evaluated["base_portfolio"].daily_returns
                    full_stress_returns = evaluated["stress_portfolio"].daily_returns

                    if not weekly_returns or not rebalances:
                        print(
                            "  [real] no trades/weekly returns -- cannot score against "
                            "the gate contract, recording as a zero-activity cell",
                            flush=True,
                        )
                        real_verdicts[cid] = {
                            "config_hash": real_hash,
                            "trade_count": len(evaluated["admitted"]),
                            "gate_evaluation": "skipped_no_trades",
                        }
                    else:
                        verdict = regime_gates.evaluate_recent_high_return_candidate(
                            experiment_id=cid,
                            config_hash=real_hash,
                            full_returns=full_returns,
                            full_stress_returns=full_stress_returns,
                            spy_returns=spy_recent,
                            bil_returns=bil_recent,
                            weekly_holding_period_net_returns_recent=weekly_returns,
                            rebalances_with_change_per_year=rebalances,
                            family=regime_gates.LEDGER_FAMILY_V2,
                            track="M",
                            is_ml=False,
                        )
                        print(
                            f"  [real] all_gates_pass={verdict.all_gates_pass} "
                            f"promotion_eligible={verdict.promotion_eligible} "
                            f"cagr={verdict.metrics['cagr_recent_net']:.4f} "
                            f"mdd={verdict.metrics['max_drawdown_recent']:.4f}",
                            flush=True,
                        )
                        record = {
                            "experiment_id": verdict.experiment_id,
                            "config_hash": verdict.config_hash,
                            "family": verdict.family,
                            "mechanism": "reversal_trend_hourly",
                            "cell": {
                                "holding_bars": holding_bars,
                                "exit_rule": exit_rule,
                                "signal_set": signal_set,
                            },
                            "track": verdict.track,
                            "is_ml": verdict.is_ml,
                            "reference_only": verdict.reference_only,
                            "trade_count": len(evaluated["admitted"]),
                            "per_trade_hit_rate": regime_metrics.hit_rate(
                                [t.net_return for t in evaluated["base_trades"]]
                            ),
                            "per_trade_profit_factor": regime_metrics.profit_factor(
                                [t.net_return for t in evaluated["base_trades"]]
                            ),
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
                        print(f"  [real] ledger appended={appended}", flush=True)
                        real_verdicts[cid] = record

                # -- placebo: same per-symbol trade count, random dates --
                placebo_checkpoint = RESULTS_DIR / f"{cid}__placebo.json"
                if placebo_checkpoint.is_file():
                    print("  [placebo] checkpoint exists, skipping", flush=True)
                    placebo_summary[cid] = json.loads(placebo_checkpoint.read_text())
                else:
                    if admitted_real is None:
                        # real cell was already ledgered in a prior run; still
                        # need a real per-symbol signal count for the placebo,
                        # so recompute just the (cheap) candidate generation.
                        admitted_real = simulate_cell(
                            signals_by_symbol,
                            holding_bars=holding_bars,
                            exit_rule=exit_rule,
                            signal_set=signal_set,
                        )
                    counts: dict[str, int] = {}
                    for symbol in signals_by_symbol:
                        counts[symbol] = sum(1 for c in admitted_real if c.symbol == symbol)
                    admitted_placebo = simulate_cell(
                        signals_by_symbol,
                        holding_bars=holding_bars,
                        exit_rule=exit_rule,
                        signal_set=signal_set,
                        placebo_counts=counts,
                        placebo_seed=PLACEBO_SEED,
                    )
                    evaluated_placebo = evaluate_admitted(
                        admitted_placebo, daily_close_by_symbol, calendar
                    )
                    print_cell_summary("placebo", evaluated_placebo)
                    placebo_net_returns = [t.net_return for t in evaluated_placebo["base_trades"]]
                    placebo_total_return = float(
                        (1.0 + evaluated_placebo["base_portfolio"].daily_returns).prod() - 1.0
                    )
                    placebo_record = {
                        "cell": cid,
                        "trade_count": len(admitted_placebo),
                        "hit_rate": (
                            regime_metrics.hit_rate(placebo_net_returns)
                            if placebo_net_returns
                            else None
                        ),
                        "profit_factor": (
                            regime_metrics.profit_factor(placebo_net_returns)
                            if placebo_net_returns
                            else None
                        ),
                        "cumulative_return": placebo_total_return,
                        "seed": PLACEBO_SEED,
                    }
                    placebo_checkpoint.write_text(json.dumps(placebo_record, indent=2))
                    placebo_summary[cid] = placebo_record

                # -- trend-gate disclosure variant --
                trend_checkpoint = RESULTS_DIR / f"{cid}__trend_gate.json"
                if trend_checkpoint.is_file():
                    print("  [trend_gate] checkpoint exists, skipping", flush=True)
                    trend_gate_summary[cid] = json.loads(trend_checkpoint.read_text())
                else:
                    admitted_trend = simulate_cell(
                        signals_by_symbol,
                        holding_bars=holding_bars,
                        exit_rule=exit_rule,
                        signal_set=signal_set,
                        entry_masks=trend_masks,
                    )
                    evaluated_trend = evaluate_admitted(
                        admitted_trend, daily_close_by_symbol, calendar
                    )
                    print_cell_summary("trend_gate", evaluated_trend)
                    trend_net_returns = [t.net_return for t in evaluated_trend["base_trades"]]
                    trend_total_return = float(
                        (1.0 + evaluated_trend["base_portfolio"].daily_returns).prod() - 1.0
                    )
                    trend_record = {
                        "cell": cid,
                        "trade_count": len(admitted_trend),
                        "hit_rate": (
                            regime_metrics.hit_rate(trend_net_returns)
                            if trend_net_returns
                            else None
                        ),
                        "profit_factor": (
                            regime_metrics.profit_factor(trend_net_returns)
                            if trend_net_returns
                            else None
                        ),
                        "cumulative_return": trend_total_return,
                    }
                    trend_checkpoint.write_text(json.dumps(trend_record, indent=2))
                    trend_gate_summary[cid] = trend_record

    summary_path = RESULTS_DIR / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "real": real_verdicts,
                "placebo": placebo_summary,
                "trend_gate": trend_gate_summary,
                "elapsed_seconds": time.time() - started,
            },
            indent=2,
            default=str,
        )
    )
    print(f"\nsummary written to {summary_path}", flush=True)
    print(f"total elapsed: {time.time() - started:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
