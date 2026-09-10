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

``feature_set`` (``m1-single-cell``'s ``--feature-set``, e.g. ``daily27`` or
``alpha158``) is a named option resolved through
``open_composer.research.features.feature_sets.resolve_feature_set`` --
Track F's real registry (commit ``85761b2``), never a hard-coded column list
threaded through grid-cell code -- coordinator instruction, 2026-09-09.
``resolve_feature_set`` returns ``(columns, roots)``; ``roots`` is passed
straight through to ``panel.load_feature_panel(extra_feature_roots=...)``, so
a new Track F feature set (``data/features/alpha158/`` etc., read-only input
to this script, never built here) needs no changes in this file at all, only
a new name on the ``--feature-set`` flag. M0/M0b's rule cells do not go
through this registry (they each score a single, explicitly named column
such as ``momentum_252_21``, not a whole feature set).

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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.adapters.data.sip_parquet import load_sip_bars  # noqa: E402
from open_composer.research.features import universe as universe_mod  # noqa: E402
from open_composer.research.features.panel import load_feature_panel, load_price_panel  # noqa: E402
from open_composer.research.kernel import mechanism_eval  # noqa: E402
from open_composer.research.kernel.baseline_strategies import MomentumFactorStrategy  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    LEDGER_PATH,
    ExperimentConfig,
    build_weight_schedule,
    returns_from_weight_schedule,
    universe_as_of_calendar_month,
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

M0_SCORE_COLUMNS = ("momentum_252_21", "ret_126_rel", "ret_63_rel")
#: M0b (coordinator relay, 2026-09-10): M0's top1500/top20 momentum cells
#: clear CAGR/activity/DSR but fail badly on max_drawdown and vol-matched-
#: SPY excess -- an independent close-to-close/no-cost check the
#: coordinator ran directly off data/features/daily + universe adv_rank
#: found universe size and risk-adjusted scoring are the real levers on
#: drawdown, not the trend gate alone. universe_top_n x score x top_k x
#: trend_gate = 2*2*2*2 = 16 cells, preregistered in
#: reports/research/control/step13-2026-09-09-progress.md before launch;
#: ledger family unchanged (step13_recent_high_return) so the DSR
#: multiple-testing count grows honestly across M0+M0b.
M0B_UNIVERSE_TOP_N_OPTIONS = (500, 200)
M0B_TOP_K_OPTIONS = (20, 50)
#: "momentum_252_21_over_vol_63" is a derived column (not a raw panel
#: column): risk-adjusted momentum, plan's second M0b lever.
M0B_SCORE_COLUMNS = ("momentum_252_21", "momentum_252_21_over_vol_63")
#: The 5 regime columns build_step13_regime_daily_features.py builds,
#: broadcast onto every symbol row for M1/M2 (plan section 3.1).
REGIME_FEATURE_COLUMNS = (
    "spy_ret_20",
    "spy_gap_200sma",
    "vix_close",
    "cs_dispersion_21",
    "breadth_50d",
)


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


@dataclasses.dataclass
class _CommonData:
    universe_panel: pd.DataFrame
    price_panel: pd.DataFrame
    weekly_dates: list[pd.Timestamp]
    spy_returns: pd.Series
    bil_returns: pd.Series
    regime_daily: pd.DataFrame
    trend_gate_series_by_date: pd.Series


def _load_common_data() -> _CommonData:
    """Universe, price panel (+cash/benchmarks), regime_daily/trend-gate, and
    SPY/BIL benchmark returns -- shared by every M0/M1/M2 stage so the
    "regime_daily lags the equity panel by up to a day" clipping (see
    inline comment below) happens exactly once, consistently.
    """
    _log("loading universe panel ...")
    universe_panel = universe_mod.load_universe_panel(UNIVERSE_ROOT)

    _log(f"loading price panel (years {DATA_YEARS}) ...")
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

    trading_calendar = pd.DatetimeIndex(sorted(price_panel["trade_date"].unique()))
    weekly_dates = weekly_rebalance_dates(trading_calendar)

    _log("loading SPY/BIL benchmark returns ...")
    _, spy_returns = _spy_close_and_returns()
    bil_returns = _bil_returns()
    trend_gate_series_by_date = _trend_gate_series(regime_daily, weekly_dates)

    return _CommonData(
        universe_panel=universe_panel,
        price_panel=price_panel,
        weekly_dates=weekly_dates,
        spy_returns=spy_returns,
        bil_returns=bil_returns,
        regime_daily=regime_daily,
        trend_gate_series_by_date=trend_gate_series_by_date,
    )


def stage_m0() -> None:
    common = _load_common_data()
    _log("loading M0 feature panel (rebalance dates only) ...")
    panel = load_feature_panel(
        list(M0_SCORE_COLUMNS), ["label_rank_5"], dates=common.weekly_dates, include_prices=False
    )

    results = []
    for score_column in M0_SCORE_COLUMNS:
        for gate_on in (True, False):
            result = run_m0_cell(
                score_column=score_column,
                gate_on=gate_on,
                panel=panel,
                price_panel=common.price_panel,
                universe_panel=common.universe_panel,
                spy_returns=common.spy_returns,
                bil_returns=common.bil_returns,
                trend_gate_series_by_date=common.trend_gate_series_by_date,
            )
            results.append(result)
    _log(f"M0 complete: {len(results)} cells processed")
    return results


def reconcile_m0_close_marked_no_cost() -> dict[str, Any]:
    """Coordinator ask, 2026-09-10: rerun M0's momentum_252_21 gate-off
    cell (top-1500 universe, top-20, quarterly refit) with raw
    close-to-close marking (``execution="close_marked"``, the same
    convention ``scripts/evaluate_cross_sectional_momentum_liquid500.py``
    uses) and zero cost, to reconcile against an independent close-to-
    close/no-cost check the coordinator ran directly off
    ``data/features/daily`` + universe ``adv_rank`` (134 weeks from
    2024-01 onward). M0's own cell used ``execution="next_open"`` (Friday
    close signal -> Monday open fill) and 10bps/side cost -- both are
    legitimate modeling choices but neither matches the coordinator's
    from-scratch check, so this is the one-line-diff comparison needed to
    confirm the two machineries agree before trusting either. Not a gated
    candidate: no ledger write, just a printed CAGR/MDD for comparison.
    """
    common = _load_common_data()
    _log("loading M0 feature panel for reconciliation (momentum_252_21 only) ...")
    panel = load_feature_panel(
        ["momentum_252_21"], ["label_rank_5"], dates=common.weekly_dates, include_prices=False
    )
    trading_calendar = pd.DatetimeIndex(sorted(common.price_panel["trade_date"].unique()))
    schedule = build_weight_schedule(
        panel=panel,
        universe_panel=common.universe_panel,
        strategy_factory=lambda: MomentumFactorStrategy(factor_column="momentum_252_21"),
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=TEST_YEARS,
        top_k=TOP_K,
        hedge="none",
        trading_calendar=trading_calendar,
        train_window_months=TRAIN_WINDOW_MONTHS,
        refit_frequency="quarterly",
        universe_top_n=UNIVERSE_TOP_N,
        trend_gate_series=None,
        trend_gate_cash_symbol=CASH_SYMBOL,
    )
    price_wide = common.price_panel.pivot(index="trade_date", columns="symbol", values="close")
    returns = returns_from_weight_schedule(
        schedule,
        price_wide,
        common.spy_returns,
        cost_bps_per_side=0.0,
        include_hedge=False,
        execution="close_marked",
    )
    recent_start = pd.Timestamp(regime_gates.RECENT_WINDOW_START)
    recent_returns = returns.loc[returns.index >= recent_start]
    cagr = mechanism_eval.annualized_cagr(recent_returns)
    mdd = mechanism_eval.max_drawdown(recent_returns)
    _log(
        "RECONCILIATION step13_m0_momentum_252_21_gate_off close_marked/cost0 "
        f"(top20-of-top1500, 2024-01 onward): cagr_recent={cagr:.4f} mdd_recent={mdd:.4f} "
        "-- coordinator's independent check: ~0.235 CAGR for the same slice"
    )
    return {"cagr_recent": cagr, "mdd_recent": mdd}


def run_m0b_cell(
    *,
    score_column: str,
    universe_top_n: int,
    top_k: int,
    gate_on: bool,
    panel: pd.DataFrame,
    price_panel: pd.DataFrame,
    universe_panel: pd.DataFrame,
    spy_returns: pd.Series,
    bil_returns: pd.Series,
    trend_gate_series_by_date: pd.Series,
) -> dict[str, Any]:
    """M0b cell -- same mechanics as ``run_m0_cell``, generalized over
    ``universe_top_n``/``top_k`` (M0 fixed these at the module-level
    ``UNIVERSE_TOP_N``/``TOP_K`` constants) instead of the score-column
    sweep. Written as its own function rather than a refactor of
    ``run_m0_cell`` so the already-ledger-recorded M0 cells' code path
    (and thus their config hashes) stay untouched.
    """
    score_label = "mom" if score_column == "momentum_252_21" else "mom_over_vol63"
    experiment_id = (
        f"step13_m0b_{score_label}_uni{universe_top_n}_k{top_k}_gate_{'on' if gate_on else 'off'}"
    )
    config = ExperimentConfig(
        experiment_id=experiment_id,
        family=FAMILY,
        model_kind="rule_single_factor",
        feature_set="daily27",
        label_horizon_days=5,
        feature_columns=(score_column,),
        top_k=top_k,
        execution="next_open",
        cost_bps_per_side=PRIMARY_COST_BPS,
        stress_cost_bps_per_side=STRESS_COST_BPS,
        test_years=TEST_YEARS,
        train_window_months=TRAIN_WINDOW_MONTHS,
        refit_frequency="quarterly",
        universe_top_n=universe_top_n,
        trend_gate=(
            {"benchmark": "SPY", "sma_days": 200, "cash_symbol": CASH_SYMBOL} if gate_on else None
        ),
        hyperparameters={
            "score_column": score_column,
            "universe_top_n": universe_top_n,
            "top_k": top_k,
            "gate_on": gate_on,
            "block": "m0b",
        },
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
        test_years=TEST_YEARS,
        top_k=top_k,
        hedge="none",
        trading_calendar=trading_calendar,
        train_window_months=TRAIN_WINDOW_MONTHS,
        refit_frequency="quarterly",
        universe_top_n=universe_top_n,
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
        f"cagr_excess_vol_matched_spy={verdict.metrics.get('cagr_excess_vol_matched_spy'):.4f} "  # noqa: E501
        f"activity_floor_min={verdict.metrics['activity_floor_rebalances_with_change_per_year_min']} "  # noqa: E501
        f"all_gates_pass={verdict.all_gates_pass} (ledger_appended={appended})"
    )
    return dataclasses.asdict(verdict)


def stage_m0b() -> None:
    common = _load_common_data()
    _log("loading M0b feature panel (momentum_252_21 + vol_63, rebalance dates only) ...")
    panel = load_feature_panel(
        ["momentum_252_21", "vol_63"],
        ["label_rank_5"],
        dates=common.weekly_dates,
        include_prices=False,
    )
    ratio = panel["momentum_252_21"] / panel["vol_63"]
    panel["momentum_252_21_over_vol_63"] = ratio.replace([np.inf, -np.inf], np.nan)

    results = []
    for universe_top_n in M0B_UNIVERSE_TOP_N_OPTIONS:
        for score_column in M0B_SCORE_COLUMNS:
            for top_k in M0B_TOP_K_OPTIONS:
                for gate_on in (True, False):
                    result = run_m0b_cell(
                        score_column=score_column,
                        universe_top_n=universe_top_n,
                        top_k=top_k,
                        gate_on=gate_on,
                        panel=panel,
                        price_panel=common.price_panel,
                        universe_panel=common.universe_panel,
                        spy_returns=common.spy_returns,
                        bil_returns=common.bil_returns,
                        trend_gate_series_by_date=common.trend_gate_series_by_date,
                    )
                    results.append(result)
    _log(f"M0b complete: {len(results)} cells processed")
    return results


def _best_m0_rule_baseline_cagr() -> float:
    """The best-by-cagr_recent_net M0 cell already in the ledger -- the
    "rule baseline" M1/M2's ml_must_beat_rule_baseline gate compares
    against. Raises if M0 has not been run yet (fail fast: an ML cell
    cannot be honestly scored against a baseline that does not exist).
    """
    if not LEDGER_PATH.exists():
        raise SystemExit(
            "M0 must be run (and recorded in the ledger) before M1/M2 -- see --stage m0"
        )
    best: float | None = None
    for line in LEDGER_PATH.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("family") == FAMILY and record.get("experiment_id", "").startswith(
            "step13_m0_"
        ):
            cagr = record.get("metrics", {}).get("cagr_recent_net")
            if cagr is not None and (best is None or cagr > best):
                best = cagr
    if best is None:
        raise SystemExit("no step13_m0_* records found in the ledger -- run --stage m0 first")
    return best


def _ledger_cagr_for_experiment_id(experiment_id: str, family: str = FAMILY) -> float:
    """A *specific* ledger record's ``cagr_recent_net``, by
    ``experiment_id`` -- for a cell whose rule twin is one exact comparison
    cell (e.g. the two-stage ML cell vs. M0b's matching pre-filter rule
    cell), not "the best M0/M0b cell so far"
    (``_best_m0_rule_baseline_cagr``'s job).
    """
    if not LEDGER_PATH.exists():
        raise SystemExit(f"ledger does not exist -- run the twin cell {experiment_id!r} first")
    for line in LEDGER_PATH.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("family") == family and record.get("experiment_id") == experiment_id:
            return record["metrics"]["cagr_recent_net"]
    raise SystemExit(
        f"{experiment_id!r} not found in the ledger (family {family!r}) -- run it first"
    )


def _pit_cohort_symbol_union(
    universe_panel: pd.DataFrame, dates: Sequence[pd.Timestamp], *, top_n: int
) -> list[str]:
    """Union, across every date in ``dates``, of the PIT top-``top_n``
    cohort (``universe_as_of_calendar_month(..., top_n=top_n)``) -- every
    symbol that is ever in-universe at that cutoff somewhere in the
    walk-forward window, typically ~500-800 names once monthly cohort
    turnover is unioned across a multi-year window, vs. the ~2,700 symbols
    in the full daily feature table. Passed to
    ``panel.load_feature_panel(symbol_filter=...)`` so wide feature sets
    (e.g. alpha158's 154 columns) don't materialize rows for symbols the
    cell can never train or score on (coordinator decision, 2026-09-10:
    alpha158's M1 cell peaked at ~1.87 GiB for a single quarter under the
    full-universe load, over the 1.4GB bar, because the panel carried
    every symbol in the daily table instead of just the cohorts this cell
    actually uses).
    """
    symbols: set[str] = set()
    for date in dates:
        symbols.update(universe_as_of_calendar_month(universe_panel, date, top_n=top_n))
    return sorted(symbols)


def stage_m1_single_cell(
    *,
    universe_top_n: int,
    top_k: int,
    feature_set: str,
    placebo: bool,
    max_periods: int | None = None,
    gate_on: bool = True,
) -> dict[str, Any]:
    """M1's single smoke-test cell (h=5, no recency weight), fit via the
    leakage-safe ``ValidationSelectedLightGBMStrategy`` with a one-cell
    grid (see that module's docstring). ``universe_top_n``/``top_k``/
    ``feature_set`` are real parameters (coordinator relay, 2026-09-10:
    run on the best M0b universe/top_k, daily27 then alpha158) resolved
    through ``open_composer.research.features.feature_sets``'s registry --
    never a hard-coded column list -- so a Track F feature set such as
    ``alpha158`` needs no further wiring here once ``extra_feature_roots``
    (its ``roots``) exists. ``placebo=True`` shuffles ``label_rank_5``
    globally (same mechanism as A-group's ``run_b3_grid.py
    --placebo-only``) before fitting, and reports the resulting
    out-of-sample validation IC per quarterly refit instead of scoring
    gates -- the coordinator's explicit ask, 2026-09-09 14:10 UTC.
    ``max_periods`` (2026-09-10 memory-fix dry-run support) caps
    ``build_weight_schedule`` to the first N walk-forward periods and, like
    ``placebo``, skips the ledger checkpoint/write and gate evaluation --
    a short return stream is not meant to produce a real verdict, only to
    smoke-test peak memory under ``/usr/bin/time -v`` before committing to
    a full run. ``gate_on`` (default True, matching every cell run so far)
    toggles the 200sma trend gate the same way M0/M0b's ``gate_on`` does --
    added 2026-09-10 for the daily27 gate-off twin the coordinator asked
    for once alpha158's memory picture was known.
    """
    from open_composer.research.features import feature_sets
    from open_composer.research.regime.validated_grid_strategy import MLGridCell
    from open_composer.research.regime.validated_grid_strategy import (
        ValidationSelectedLightGBMStrategy as VSStrategy,
    )

    common = _load_common_data()
    base_columns, extra_roots = feature_sets.resolve_feature_set(feature_set)
    feature_columns = list(base_columns) + list(REGIME_FEATURE_COLUMNS)
    symbol_filter = _pit_cohort_symbol_union(
        common.universe_panel, common.weekly_dates, top_n=universe_top_n
    )
    _log(
        f"loading M1 feature panel ({feature_set}: {len(base_columns)} cols "
        f"+ {len(REGIME_FEATURE_COLUMNS)} regime cols, roots={[str(r) for r in extra_roots]}, "
        f"symbol_filter={len(symbol_filter)} symbols) ..."
    )
    daily_panel = load_feature_panel(
        list(base_columns),
        ["label_rank_5"],
        years=list(DATA_YEARS),
        dates=common.weekly_dates,
        include_prices=False,
        extra_feature_roots=extra_roots,
        symbol_filter=symbol_filter,
    )
    # Broadcast the 5 market-level regime_daily columns onto every symbol
    # row for that trade_date -- a left join, not a per-symbol feature.
    panel = daily_panel.merge(
        common.regime_daily[["trade_date", *REGIME_FEATURE_COLUMNS]], on="trade_date", how="left"
    )
    # A bare tuple indexer (``panel[REGIME_FEATURE_COLUMNS]``) asks pandas
    # for one column literally *named* by that tuple (MultiIndex-style),
    # not "select these columns" -- must be a list. Caught here 2026-09-10
    # on this function's first-ever real invocation: raised
    # ``KeyError: ('spy_ret_20', ...)`` since no such single column exists.
    if panel[list(REGIME_FEATURE_COLUMNS)].isna().any().any():
        raise ValueError("regime feature columns have missing values after the merge")

    cell_label = f"{feature_set}_uni{universe_top_n}_k{top_k}_gate_{'on' if gate_on else 'off'}"
    if max_periods is not None:
        experiment_id = f"step13_m1_single_cell_{cell_label}_DRYRUN{max_periods}"
    elif placebo:
        rng = np.random.default_rng(2026)
        panel = panel.copy()
        panel["label_rank_5"] = rng.permutation(panel["label_rank_5"].to_numpy())
        experiment_id = f"step13_m1_single_cell_{cell_label}_PLACEBO"
    else:
        experiment_id = f"step13_m1_single_cell_{cell_label}"

    fitted_strategies: list[VSStrategy] = []

    def _factory() -> VSStrategy:
        strategy = VSStrategy(feature_columns, grid=[MLGridCell(label_horizon_days=5)])
        fitted_strategies.append(strategy)
        return strategy

    config = ExperimentConfig(
        experiment_id=experiment_id,
        family=FAMILY,
        model_kind="lightgbm_validation_selected",
        feature_set=f"{feature_set}_plus_regime5",
        label_horizon_days=5,
        feature_columns=tuple(feature_columns),
        top_k=top_k,
        execution="next_open",
        cost_bps_per_side=PRIMARY_COST_BPS,
        stress_cost_bps_per_side=STRESS_COST_BPS,
        test_years=TEST_YEARS,
        train_window_months=TRAIN_WINDOW_MONTHS,
        refit_frequency="quarterly",
        universe_top_n=universe_top_n,
        trend_gate=(
            {"benchmark": "SPY", "sma_days": 200, "cash_symbol": CASH_SYMBOL} if gate_on else None
        ),
        hyperparameters={"grid": ["h5_d3"], "placebo": placebo},
    )
    config_hash = config.config_hash()
    if not placebo and max_periods is None:
        existing = _existing_ledger_record(config_hash)
        if existing is not None:
            _log(f"{experiment_id} (hash {config_hash}) already in ledger -- skipping recompute")
            return existing

    _log(f"running {experiment_id} (hash {config_hash}) ...")
    trading_calendar = pd.DatetimeIndex(sorted(common.price_panel["trade_date"].unique()))
    schedule = build_weight_schedule(
        panel=panel,
        universe_panel=common.universe_panel,
        strategy_factory=_factory,
        feature_columns=feature_columns,
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=config.test_years,
        top_k=config.top_k,
        hedge="none",
        trading_calendar=trading_calendar,
        train_window_months=config.train_window_months,
        refit_frequency=config.refit_frequency,
        universe_top_n=config.universe_top_n,
        trend_gate_series=common.trend_gate_series_by_date if gate_on else None,
        trend_gate_cash_symbol=CASH_SYMBOL,
        max_periods=max_periods,
    )

    validation_ics = [
        s.validation_ic_by_cell.get("h5_d3")
        for s in fitted_strategies
        if s.validation_ic_by_cell.get("h5_d3") == s.validation_ic_by_cell.get("h5_d3")  # drop NaN
    ]
    mean_validation_ic = float(np.mean(validation_ics)) if validation_ics else float("nan")
    _log(
        f"{experiment_id}: {len(fitted_strategies)} quarterly refits, "
        f"per-quarter validation IC={[round(v, 4) for v in validation_ics]}, "
        f"mean={mean_validation_ic:.4f}"
    )

    if max_periods is not None:
        _log(
            f"DRY RUN (max_periods={max_periods}) completed without a memory kill -- stopping here."
        )
        return {
            "experiment_id": experiment_id,
            "mean_validation_ic": mean_validation_ic,
            "per_quarter_ic": validation_ics,
        }

    if placebo:
        _log(f"PLACEBO RESULT: mean out-of-sample validation IC = {mean_validation_ic:.4f}")
        return {
            "experiment_id": experiment_id,
            "mean_validation_ic": mean_validation_ic,
            "per_quarter_ic": validation_ics,
        }

    price_wide = common.price_panel.pivot(index="trade_date", columns="symbol", values="close")
    open_wide = common.price_panel.pivot(index="trade_date", columns="symbol", values="open")
    primary_returns = returns_from_weight_schedule(
        schedule,
        price_wide,
        common.spy_returns,
        cost_bps_per_side=PRIMARY_COST_BPS,
        include_hedge=False,
        execution="next_open",
        open_wide=open_wide,
    )
    stress_returns = returns_from_weight_schedule(
        schedule,
        price_wide,
        common.spy_returns,
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
    rule_baseline_cagr = _best_m0_rule_baseline_cagr()

    verdict = regime_gates.evaluate_recent_high_return_candidate(
        experiment_id=experiment_id,
        config_hash=config_hash,
        full_returns=primary_returns,
        full_stress_returns=stress_returns,
        spy_returns=common.spy_returns,
        bil_returns=common.bil_returns,
        weekly_holding_period_net_returns_recent=weekly_returns_recent,
        rebalances_with_change_per_year=rebalances_with_change,
        family=FAMILY,
        is_ml=True,
        placebo_rank_ic_abs=abs(mean_validation_ic),
        rule_baseline_cagr_recent_net=rule_baseline_cagr,
    )
    appended = _append_v2_ledger_record(config, verdict)
    _log(
        f"{experiment_id}: cagr_recent_net={verdict.metrics['cagr_recent_net']:.4f} "
        f"mdd={verdict.metrics['max_drawdown_recent']:.4f} "
        f"hit_rate_weekly={verdict.metrics['hit_rate_weekly']:.4f} "
        f"vs_rule_baseline={rule_baseline_cagr:.4f} "
        f"all_gates_pass={verdict.all_gates_pass} (ledger_appended={appended})"
    )
    return dataclasses.asdict(verdict)


#: Coordinator-preregistered two-stage cell, 2026-09-10: pre-filter each
#: rebalance date to the top-100 of the top-500 (ADV) universe by
#: momentum_252_21/vol_63, then let the daily27 LightGBM model rank only
#: those 100 and hold the top 50 (gate on). Rule twin (the
#: ml_must_beat_rule_baseline comparison) is M0b's own matching pre-filter
#: rule cell, not the looser "best M0/M0b cell so far" -- same pre-filter
#: score, same universe/top_k, so the ML-vs-rule comparison is like for
#: like.
TWO_STAGE_UNIVERSE_TOP_N = 500
TWO_STAGE_PRE_FILTER_TOP_N = 100
TWO_STAGE_TOP_K = 50
TWO_STAGE_RULE_TWIN_EXPERIMENT_ID = "step13_m0b_mom_over_vol63_uni500_k50_gate_on"


def stage_two_stage_cell(*, placebo: bool) -> dict[str, Any]:
    """See ``TWO_STAGE_*`` constants above for the preregistered spec.
    ``fit`` trains the inner LightGBM strategy on the full window; only
    scoring/selection is restricted to the pre-filter's top-100 pool (see
    ``regime.validated_grid_strategy.TopNPreFilteredStrategy``'s own
    docstring for why that split matches the coordinator's spec).
    """
    from open_composer.research.features import feature_sets
    from open_composer.research.regime.validated_grid_strategy import (
        MLGridCell,
        TopNPreFilteredStrategy,
    )
    from open_composer.research.regime.validated_grid_strategy import (
        ValidationSelectedLightGBMStrategy as VSStrategy,
    )

    common = _load_common_data()
    base_columns, extra_roots = feature_sets.resolve_feature_set("daily27")
    feature_columns = list(base_columns) + list(REGIME_FEATURE_COLUMNS)
    _log(f"loading two-stage feature panel (daily27: {len(base_columns)} cols + regime5) ...")
    daily_panel = load_feature_panel(
        list(base_columns),
        ["label_rank_5"],
        years=list(DATA_YEARS),
        dates=common.weekly_dates,
        include_prices=False,
        extra_feature_roots=extra_roots,
    )
    panel = daily_panel.merge(
        common.regime_daily[["trade_date", *REGIME_FEATURE_COLUMNS]], on="trade_date", how="left"
    )
    if panel[list(REGIME_FEATURE_COLUMNS)].isna().any().any():
        raise ValueError("regime feature columns have missing values after the merge")
    # Same derived pre-filter score M0b uses (momentum_252_21 and vol_63
    # are both already daily27 columns): inf from a zero-vol row mapped to
    # NaN so it can never win nlargest() by accident.
    ratio = panel["momentum_252_21"] / panel["vol_63"]
    panel["momentum_252_21_over_vol_63"] = ratio.replace([np.inf, -np.inf], np.nan)

    cell_label = (
        f"two_stage_daily27_uni{TWO_STAGE_UNIVERSE_TOP_N}_"
        f"pf{TWO_STAGE_PRE_FILTER_TOP_N}_k{TWO_STAGE_TOP_K}_gate_on"
    )
    if placebo:
        rng = np.random.default_rng(2026)
        panel = panel.copy()
        panel["label_rank_5"] = rng.permutation(panel["label_rank_5"].to_numpy())
        experiment_id = f"step13_m1_{cell_label}_PLACEBO"
    else:
        experiment_id = f"step13_m1_{cell_label}"

    fitted_strategies: list[VSStrategy] = []

    def _factory() -> TopNPreFilteredStrategy:
        inner = VSStrategy(feature_columns, grid=[MLGridCell(label_horizon_days=5)])
        fitted_strategies.append(inner)
        return TopNPreFilteredStrategy(
            inner,
            pre_filter_score_column="momentum_252_21_over_vol_63",
            pre_filter_top_n=TWO_STAGE_PRE_FILTER_TOP_N,
        )

    config = ExperimentConfig(
        experiment_id=experiment_id,
        family=FAMILY,
        model_kind="lightgbm_validation_selected_two_stage_prefilter",
        feature_set="daily27_plus_regime5_prefilter_mom_over_vol63",
        label_horizon_days=5,
        feature_columns=tuple(feature_columns),
        top_k=TWO_STAGE_TOP_K,
        execution="next_open",
        cost_bps_per_side=PRIMARY_COST_BPS,
        stress_cost_bps_per_side=STRESS_COST_BPS,
        test_years=TEST_YEARS,
        train_window_months=TRAIN_WINDOW_MONTHS,
        refit_frequency="quarterly",
        universe_top_n=TWO_STAGE_UNIVERSE_TOP_N,
        trend_gate={"benchmark": "SPY", "sma_days": 200, "cash_symbol": CASH_SYMBOL},
        hyperparameters={
            "grid": ["h5_d3"],
            "placebo": placebo,
            "pre_filter_score_column": "momentum_252_21_over_vol_63",
            "pre_filter_top_n": TWO_STAGE_PRE_FILTER_TOP_N,
        },
    )
    config_hash = config.config_hash()
    if not placebo:
        existing = _existing_ledger_record(config_hash)
        if existing is not None:
            _log(f"{experiment_id} (hash {config_hash}) already in ledger -- skipping recompute")
            return existing

    _log(f"running {experiment_id} (hash {config_hash}) ...")
    trading_calendar = pd.DatetimeIndex(sorted(common.price_panel["trade_date"].unique()))
    schedule = build_weight_schedule(
        panel=panel,
        universe_panel=common.universe_panel,
        strategy_factory=_factory,
        feature_columns=feature_columns,
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=config.test_years,
        top_k=config.top_k,
        hedge="none",
        trading_calendar=trading_calendar,
        train_window_months=config.train_window_months,
        refit_frequency=config.refit_frequency,
        universe_top_n=config.universe_top_n,
        trend_gate_series=common.trend_gate_series_by_date,
        trend_gate_cash_symbol=CASH_SYMBOL,
    )

    validation_ics = [
        s.validation_ic_by_cell.get("h5_d3")
        for s in fitted_strategies
        if s.validation_ic_by_cell.get("h5_d3") == s.validation_ic_by_cell.get("h5_d3")  # drop NaN
    ]
    mean_validation_ic = float(np.mean(validation_ics)) if validation_ics else float("nan")
    _log(
        f"{experiment_id}: {len(fitted_strategies)} quarterly refits, "
        f"per-quarter validation IC={[round(v, 4) for v in validation_ics]}, "
        f"mean={mean_validation_ic:.4f}"
    )

    if placebo:
        _log(f"PLACEBO RESULT: mean out-of-sample validation IC = {mean_validation_ic:.4f}")
        return {
            "experiment_id": experiment_id,
            "mean_validation_ic": mean_validation_ic,
            "per_quarter_ic": validation_ics,
        }

    price_wide = common.price_panel.pivot(index="trade_date", columns="symbol", values="close")
    open_wide = common.price_panel.pivot(index="trade_date", columns="symbol", values="open")
    primary_returns = returns_from_weight_schedule(
        schedule,
        price_wide,
        common.spy_returns,
        cost_bps_per_side=PRIMARY_COST_BPS,
        include_hedge=False,
        execution="next_open",
        open_wide=open_wide,
    )
    stress_returns = returns_from_weight_schedule(
        schedule,
        price_wide,
        common.spy_returns,
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
    rule_baseline_cagr = _ledger_cagr_for_experiment_id(TWO_STAGE_RULE_TWIN_EXPERIMENT_ID)

    verdict = regime_gates.evaluate_recent_high_return_candidate(
        experiment_id=experiment_id,
        config_hash=config_hash,
        full_returns=primary_returns,
        full_stress_returns=stress_returns,
        spy_returns=common.spy_returns,
        bil_returns=common.bil_returns,
        weekly_holding_period_net_returns_recent=weekly_returns_recent,
        rebalances_with_change_per_year=rebalances_with_change,
        family=FAMILY,
        is_ml=True,
        placebo_rank_ic_abs=abs(mean_validation_ic),
        rule_baseline_cagr_recent_net=rule_baseline_cagr,
    )
    appended = _append_v2_ledger_record(config, verdict)
    _log(
        f"{experiment_id}: cagr_recent_net={verdict.metrics['cagr_recent_net']:.4f} "
        f"mdd={verdict.metrics['max_drawdown_recent']:.4f} "
        f"hit_rate_weekly={verdict.metrics['hit_rate_weekly']:.4f} "
        f"vs_rule_baseline={rule_baseline_cagr:.4f} "
        f"all_gates_pass={verdict.all_gates_pass} (ledger_appended={appended})"
    )
    return dataclasses.asdict(verdict)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=["m0", "reconcile", "m0b", "m1-single-cell", "two-stage"],
        default="m0",
    )
    parser.add_argument(
        "--placebo",
        action="store_true",
        help=(
            "m1-single-cell/two-stage only: shuffle label_rank_5, report "
            "validation IC instead of gates"
        ),
    )
    parser.add_argument("--universe-top-n", type=int, default=500, help="m1-single-cell only")
    parser.add_argument("--top-k", type=int, default=50, help="m1-single-cell only")
    parser.add_argument("--feature-set", default="daily27", help="m1-single-cell only")
    parser.add_argument(
        "--gate-off",
        action="store_true",
        help="m1-single-cell only: disable the 200sma trend gate (default on)",
    )
    parser.add_argument(
        "--max-periods",
        type=int,
        default=None,
        help=(
            "m1-single-cell only: cap build_weight_schedule to the first N "
            "walk-forward periods and skip the ledger/gates -- a memory "
            "dry run, e.g. --max-periods 1 for a one-quarter smoke test"
        ),
    )
    args = parser.parse_args()
    if args.stage == "m0":
        stage_m0()
    elif args.stage == "reconcile":
        reconcile_m0_close_marked_no_cost()
    elif args.stage == "m0b":
        stage_m0b()
    elif args.stage == "m1-single-cell":
        stage_m1_single_cell(
            universe_top_n=args.universe_top_n,
            top_k=args.top_k,
            feature_set=args.feature_set,
            placebo=args.placebo,
            max_periods=args.max_periods,
            gate_on=not args.gate_off,
        )
    elif args.stage == "two-stage":
        stage_two_stage_cell(placebo=args.placebo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
