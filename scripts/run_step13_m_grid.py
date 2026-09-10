"""Step 13 Track M: M0 (rule baselines) and M1/M2 (ML) grid runner.

docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md
section 3. Uses ``open_composer.research.features.panel``'s memory-lean
loaders (``load_price_panel`` + ``load_feature_panel``) and
``open_composer.research.kernel.loop``'s Step 13 extensions
(``train_window_months``, ``refit_frequency``, ``trend_gate``,
``universe_top_n``). Calls ``build_weight_schedule``/
``returns_from_weight_schedule`` directly (not ``loop.run_experiment``,
which scores against Group A's kernel gate contract, not this contract) --
same pattern Step 12 Group B's ``evaluate_groupb_*.py`` scripts already
used -- then scores the resulting return streams against
``config/promotion/recent-regime-high-return-gates-v2.json`` via
``open_composer.research.regime.gates.evaluate_recent_high_return_candidate``.

``feature_set`` is a named option (``--feature-set daily27``, the only one
defined today) resolved through ``FEATURE_SET_REGISTRY`` below, never a
hard-coded column list threaded through grid-cell code -- coordinator
instruction, 2026-09-09, anticipating a separate Track F agent's forthcoming
open-factor-library tables (``data/features/alpha158/`` etc., read-only
input to this script, never built here) landing as a new
``panel.load_feature_panel(extra_feature_roots=...)`` parameter. Adding
"alpha158"/"both" later should only need a new registry entry plus passing
that entry's ``extra_feature_roots`` through once ``panel.py`` defines it.

**Checkpointing**: every cell's ``ExperimentConfig.config_hash`` is checked
against the shared ledger (family ``step13_recent_high_return``) before
running; an already-recorded hash is skipped (loaded back from the ledger
for the printed summary) rather than recomputed -- required so a detached,
possibly-interrupted run can be relaunched with the same ``--cells`` and
pick up where it left off, per the 2026-09-10 00:55 UTC coordinator
operating rules (no wait loops; launch detached, resume on restart).

Usage::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_step13_m_grid.py --stage m0
    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_step13_m_grid.py --stage m1-single-cell
    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_step13_m_grid.py --stage m1-single-cell --placebo
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from open_composer.adapters.data.sip_parquet import load_sip_bars  # noqa: E402
from open_composer.research.features import universe as universe_mod  # noqa: E402
from open_composer.research.features.panel import load_feature_panel, load_price_panel  # noqa: E402
from open_composer.research.kernel.baseline_strategies import MomentumFactorStrategy  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    LEDGER_PATH,
    ExperimentConfig,
    build_weight_schedule,
    returns_from_weight_schedule,
    weekly_rebalance_dates,
)
from open_composer.research.regime import gates as regime_gates  # noqa: E402

UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
REGIME_DAILY_ROOT = ROOT / "data" / "features" / "regime_daily"
FAMILY = regime_gates.LEDGER_FAMILY_V2  # "step13_recent_high_return"
DATA_START = "2016-01-04"
PRIMARY_COST_BPS = 10.0
STRESS_COST_BPS = 25.0
TOP_K = 20
UNIVERSE_TOP_N = 1500
#: Years actually walked forward as test periods -- must equal the v2
#: contract's gated window (2024Q1..2026Q3-to-date), never wider: passing an
#: earlier year (e.g. 2022) to build_weight_schedule's test_years makes it a
#: real test period needing its *own* embargoed training window before it,
#: which the panel has no data for if DATA_YEARS' warm-up years are its
#: first years loaded -- there is nothing "extra" about a warm-up year from
#: build_weight_schedule's point of view, it is just another test year with
#: no history (observed directly: this crashed the first two M0 launches).
TEST_YEARS = (2024, 2025, 2026)
#: Years to load into the price/feature/regime panels -- wider than
#: TEST_YEARS so the first test quarter (2024Q1) has a real trailing
#: 24-month training window (2022-01..2023-12) to draw from.
DATA_YEARS = (2022, 2023, 2024, 2025, 2026)
TRAIN_WINDOW_MONTHS = 24
CASH_SYMBOL = "BIL"

#: Named feature sets, resolved through the panel loader -- see module
#: docstring. Only "daily27" exists today.
FEATURE_SET_REGISTRY: dict[str, tuple[str, ...]] = {
    "daily27": (
        "ret_1",
        "ret_5",
        "ret_21",
        "ret_63",
        "ret_126",
        "ret_252",
        "momentum_252_21",
        "vol_21",
        "vol_63",
        "beta_252_spy",
        "idio_vol_63",
        "max_ret_1_21",
        "dollar_adv_21",
        "dollar_adv_63",
        "dollar_adv_21_over_63",
        "amihud_21",
        "dist_from_252d_high",
        "ret_1_rel",
        "ret_5_rel",
        "ret_21_rel",
        "ret_63_rel",
        "ret_126_rel",
        "ret_252_rel",
        "momentum_252_21_rel",
    ),
}
M0_SCORE_COLUMNS = ("momentum_252_21", "ret_126_rel", "ret_63_rel")


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _augment_price_panel_with_cash_and_benchmarks(
    price_panel: pd.DataFrame,
    years: tuple[int, ...],
    extra_symbols: tuple[str, ...] = (CASH_SYMBOL,),
) -> pd.DataFrame:
    """``load_price_panel`` only covers the (ETF-excluded) equity universe,
    already restricted to ``years``; the trend-gate cash leg needs real
    ``BIL`` open/close rows in the same ``symbol, trade_date, open, close``
    shape to be tradeable by ``returns_from_weight_schedule``. ``years`` is
    required (not inferred from ``DATA_START``) so the merged trading
    calendar cannot silently grow years earlier than the equity panel's own
    range -- that mismatch previously fed 2016-2021 dates into
    ``weekly_rebalance_dates`` that the (years-scoped)
    ``data/features/regime_daily/`` lookup had no rows for.
    """
    frames = [price_panel]
    wanted_years = set(years)
    for symbol in extra_symbols:
        raw = load_sip_bars(symbol, frequency="daily", start=DATA_START)
        rows = raw.loc[raw["symbol"] == symbol].copy()
        rows["timestamp"] = pd.to_datetime(rows["timestamp"], utc=True)
        rows = rows.sort_values("timestamp")
        rows["trade_date"] = pd.to_datetime(rows["timestamp"].dt.date)
        rows = rows.drop_duplicates("trade_date", keep="last")
        rows = rows.loc[rows["trade_date"].dt.year.isin(wanted_years)]
        frames.append(
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "trade_date": rows["trade_date"].to_numpy(),
                    "open": pd.to_numeric(rows["open"], errors="raise").to_numpy(dtype="float32"),
                    "close": pd.to_numeric(rows["close"], errors="raise").to_numpy(dtype="float32"),
                }
            )
        )
    return pd.concat(frames, ignore_index=True).sort_values(["symbol", "trade_date"])


def _spy_close_and_returns() -> tuple[pd.Series, pd.Series]:
    raw = load_sip_bars("SPY", frequency="daily", start=DATA_START)
    rows = raw.loc[raw["symbol"] == "SPY"].copy()
    rows["timestamp"] = pd.to_datetime(rows["timestamp"], utc=True)
    rows = rows.sort_values("timestamp")
    rows["trade_date"] = pd.to_datetime(rows["timestamp"].dt.date)
    rows = rows.drop_duplicates("trade_date", keep="last")
    close = pd.Series(
        pd.to_numeric(rows["close"], errors="raise").to_numpy(),
        index=pd.DatetimeIndex(rows["trade_date"]),
        name="close",
    ).sort_index()
    return close, close.pct_change(fill_method=None).dropna()


def _bil_returns() -> pd.Series:
    raw = load_sip_bars(CASH_SYMBOL, frequency="daily", start=DATA_START)
    rows = raw.loc[raw["symbol"] == CASH_SYMBOL].copy()
    rows["timestamp"] = pd.to_datetime(rows["timestamp"], utc=True)
    rows = rows.sort_values("timestamp")
    rows["trade_date"] = pd.to_datetime(rows["timestamp"].dt.date)
    rows = rows.drop_duplicates("trade_date", keep="last")
    close = pd.Series(
        pd.to_numeric(rows["close"], errors="raise").to_numpy(),
        index=pd.DatetimeIndex(rows["trade_date"]),
    ).sort_index()
    return close.pct_change(fill_method=None).dropna()


def _load_regime_daily(years: list[int]) -> pd.DataFrame:
    frames = [pd.read_parquet(REGIME_DAILY_ROOT / f"{year}.parquet") for year in years]
    frame = pd.concat(frames, ignore_index=True)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame.sort_values("trade_date")


def _trend_gate_series(
    regime_daily: pd.DataFrame, rebalance_dates: list[pd.Timestamp]
) -> pd.Series:
    """Boolean, indexed by rebalance date: True (gate open) iff SPY closed
    above its 200-day SMA as of that date (``spy_gap_200sma > 0``). Missing
    dates (should not happen once the regime table covers the schedule)
    default to closed -- ``build_weight_schedule``'s own conservative
    default for a missing key.
    """
    lookup = regime_daily.set_index("trade_date")["spy_gap_200sma"]
    aligned = lookup.reindex(pd.DatetimeIndex(rebalance_dates))
    if aligned.isna().any():
        missing = aligned[aligned.isna()].index.tolist()
        raise ValueError(f"trend gate series missing spy_gap_200sma for dates: {missing}")
    return (aligned > 0.0).astype(bool)


def _weekly_returns_excluding_cash(
    schedule,
    daily_returns: pd.Series,
    *,
    recent_start: pd.Timestamp,
    cash_symbol: str = CASH_SYMBOL,
) -> list[float]:
    """Compounded return between each pair of consecutive active rebalance
    events on/after ``recent_start``, excluding events whose entire weight
    is the cash leg (gate-closed weeks) from both the numerator and the
    denominator -- gate contract's own ``hit_rate_weekly`` note.
    """
    active = [event for event in schedule if event.selected]
    dates = daily_returns.index
    out: list[float] = []
    for i, event in enumerate(active):
        event_date = pd.Timestamp(event.date)
        if event_date < recent_start:
            continue
        is_cash_only = set(event.selected) == {cash_symbol}
        next_date = pd.Timestamp(active[i + 1].date) if i + 1 < len(active) else dates.max()
        window = daily_returns.loc[(dates > event_date) & (dates <= next_date)]
        if window.empty:
            continue
        compounded = float((1.0 + window).prod() - 1.0)
        if not is_cash_only:
            out.append(compounded)
    return out


def _rebalances_with_change_per_year(schedule) -> dict[int, int]:
    """{calendar_year: count of rebalance dates in the recent gated years
    whose selected weights differ from the immediately preceding
    rebalance's} -- a trend-gate flip to/from cash counts as a change (it
    changes every weight), matching the gate contract's activity-floor note.
    """
    counts: dict[int, int] = {year: 0 for year in TEST_YEARS}
    previous: dict[str, float] | None = None
    for event in schedule:
        date = pd.Timestamp(event.date)
        changed = previous is None or dict(event.selected) != previous
        if changed and date.year in counts:
            counts[date.year] += 1
        previous = dict(event.selected)
    return counts


def _existing_ledger_record(config_hash: str, family: str = FAMILY) -> dict[str, Any] | None:
    if not LEDGER_PATH.exists():
        return None
    for line in LEDGER_PATH.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("config_hash") == config_hash and record.get("family") == family:
            return record
    return None


def _append_v2_ledger_record(
    config: ExperimentConfig, verdict: regime_gates.RecentHighReturnVerdict
) -> bool:
    record = {
        "experiment_id": config.experiment_id,
        "config_hash": config.config_hash(),
        "family": config.family,
        "model_kind": config.model_kind,
        "hyperparameters": config.hyperparameters,
        "trend_gate": config.trend_gate,
        "universe_top_n": config.universe_top_n,
        "train_window_months": config.train_window_months,
        "refit_frequency": config.refit_frequency,
        "recency_halflife_days": config.recency_halflife_days,
        "dsr_trial_count": verdict.dsr_trial_count,
        "metrics": verdict.metrics,
        "disclosure": verdict.disclosure,
        "gate_results": verdict.gate_results,
        "gates_not_applicable": list(verdict.gates_not_applicable),
        "all_gates_pass": verdict.all_gates_pass,
        "promotion_eligible": verdict.promotion_eligible,
        "gate_contract": verdict.gate_contract,
        "recorded_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    return regime_gates.append_ledger(record)


def run_m0_cell(
    *,
    score_column: str,
    gate_on: bool,
    panel: pd.DataFrame,
    price_panel: pd.DataFrame,
    universe_panel: pd.DataFrame,
    spy_returns: pd.Series,
    bil_returns: pd.Series,
    trend_gate_series_by_date: pd.Series,
) -> dict[str, Any]:
    experiment_id = f"step13_m0_{score_column}_gate_{'on' if gate_on else 'off'}"
    config = ExperimentConfig(
        experiment_id=experiment_id,
        family=FAMILY,
        model_kind="rule_single_factor",
        feature_set="daily27",
        label_horizon_days=5,
        feature_columns=(score_column,),
        top_k=TOP_K,
        execution="next_open",
        cost_bps_per_side=PRIMARY_COST_BPS,
        stress_cost_bps_per_side=STRESS_COST_BPS,
        test_years=TEST_YEARS,
        train_window_months=TRAIN_WINDOW_MONTHS,
        refit_frequency="quarterly",
        universe_top_n=UNIVERSE_TOP_N,
        trend_gate=(
            {"benchmark": "SPY", "sma_days": 200, "cash_symbol": CASH_SYMBOL} if gate_on else None
        ),
        hyperparameters={"score_column": score_column, "gate_on": gate_on},
    )
    config_hash = config.config_hash()
    existing = _existing_ledger_record(config_hash)
    if existing is not None:
        _log(f"{experiment_id} (hash {config_hash}) already in ledger -- skipping recompute")
        return existing

    _log(f"running {experiment_id} (hash {config_hash}) ...")
    trading_calendar = pd.DatetimeIndex(sorted(price_panel["trade_date"].unique()))
    schedule = build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=lambda: MomentumFactorStrategy(factor_column=score_column),
        feature_columns=[score_column],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=config.test_years,
        top_k=config.top_k,
        hedge="none",
        trading_calendar=trading_calendar,
        train_window_months=config.train_window_months,
        refit_frequency=config.refit_frequency,
        universe_top_n=config.universe_top_n,
        trend_gate_series=trend_gate_series_by_date if gate_on else None,
        trend_gate_cash_symbol=CASH_SYMBOL,
    )
    price_wide = price_panel.pivot(index="trade_date", columns="symbol", values="close")
    open_wide = price_panel.pivot(index="trade_date", columns="symbol", values="open")
    primary_returns = returns_from_weight_schedule(
        schedule,
        price_wide,
        spy_returns,
        cost_bps_per_side=PRIMARY_COST_BPS,
        include_hedge=False,
        execution="next_open",
        open_wide=open_wide,
    )
    stress_returns = returns_from_weight_schedule(
        schedule,
        price_wide,
        spy_returns,
        cost_bps_per_side=STRESS_COST_BPS,
        include_hedge=False,
        execution="next_open",
        open_wide=open_wide,
    )

    recent_start = pd.Timestamp(regime_gates.RECENT_WINDOW_START)
    weekly_returns_recent = _weekly_returns_excluding_cash(
        schedule, primary_returns, recent_start=recent_start
    )
    rebalances_with_change = _rebalances_with_change_per_year(schedule)

    verdict = regime_gates.evaluate_recent_high_return_candidate(
        experiment_id=experiment_id,
        config_hash=config_hash,
        full_returns=primary_returns,
        full_stress_returns=stress_returns,
        spy_returns=spy_returns,
        bil_returns=bil_returns,
        weekly_holding_period_net_returns_recent=weekly_returns_recent,
        rebalances_with_change_per_year=rebalances_with_change,
        family=FAMILY,
        is_ml=False,
    )
    appended = _append_v2_ledger_record(config, verdict)
    _log(
        f"{experiment_id}: cagr_recent_net={verdict.metrics['cagr_recent_net']:.4f} "
        f"mdd={verdict.metrics['max_drawdown_recent']:.4f} "
        f"hit_rate_weekly={verdict.metrics['hit_rate_weekly']:.4f} "
        f"activity_floor_min={verdict.metrics['activity_floor_rebalances_with_change_per_year_min']} "  # noqa: E501
        f"all_gates_pass={verdict.all_gates_pass} (ledger_appended={appended})"
    )
    return dataclasses.asdict(verdict)


def stage_m0() -> None:
    _log("loading universe panel ...")
    universe_panel = universe_mod.load_universe_panel(UNIVERSE_ROOT)

    _log(f"loading price panel ({FEATURE_SET_REGISTRY['daily27']!r} years {DATA_YEARS}) ...")
    price_panel = load_price_panel(years=list(DATA_YEARS))
    price_panel = _augment_price_panel_with_cash_and_benchmarks(price_panel, years=DATA_YEARS)

    _log("loading regime_daily trend gate table ...")
    regime_daily = _load_regime_daily(list(DATA_YEARS))
    regime_daily_max_date = pd.Timestamp(regime_daily["trade_date"].max())
    # The regime table and the equity daily-feature archive are built by
    # separate jobs and can be one trading day out of sync at the very end
    # of the covered history (observed 2026-09-10: the equity panel already
    # had 2026-09-09 while regime_daily's own last build did not). Clipping
    # the whole analysis window to regime_daily's own max date, rather than
    # erroring on a single trailing date, keeps every downstream date
    # (feature panel, rebalance schedule, mark-to-market prices) mutually
    # consistent -- a disclosed, PIT-honest "as of the older table" choice,
    # not a silent gap-fill.
    price_panel = price_panel.loc[price_panel["trade_date"] <= regime_daily_max_date]

    _log("loading M0 feature panel (rebalance dates only) ...")
    trading_calendar = pd.DatetimeIndex(sorted(price_panel["trade_date"].unique()))
    weekly_dates = weekly_rebalance_dates(trading_calendar)
    panel = load_feature_panel(
        list(M0_SCORE_COLUMNS), ["label_rank_5"], dates=weekly_dates, include_prices=False
    )

    _log("loading SPY/BIL benchmark returns ...")
    _, spy_returns = _spy_close_and_returns()
    bil_returns = _bil_returns()
    trend_gate_series_by_date = _trend_gate_series(regime_daily, weekly_dates)

    results = []
    for score_column in M0_SCORE_COLUMNS:
        for gate_on in (True, False):
            result = run_m0_cell(
                score_column=score_column,
                gate_on=gate_on,
                panel=panel,
                price_panel=price_panel,
                universe_panel=universe_panel,
                spy_returns=spy_returns,
                bil_returns=bil_returns,
                trend_gate_series_by_date=trend_gate_series_by_date,
            )
            results.append(result)
    _log(f"M0 complete: {len(results)} cells processed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["m0"], default="m0")
    args = parser.parse_args()
    if args.stage == "m0":
        stage_m0()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
