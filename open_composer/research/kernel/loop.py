"""Step 11 Wave A 3.4: the model-first experiment loop.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.4. One candidate
configuration -> one call to :func:`run_experiment` -> one entry in
``reports/research/ledger/experiments.jsonl`` -> one QuantStats tearsheet ->
one MLflow run -> a same-day, cost-adjusted, out-of-sample verdict from
``mechanism_eval.evaluate_candidate``. Research-stage runs through this
module do **not** write iteration dossiers, source cards, or go through
``oc research iteration validate`` -- plan section 1's explicit exemption for
this round; the ledger is the record.

Three non-compressible honesty requirements, enforced here rather than by
policy (plan section 3.4):

1. **PIT features and universe**: guaranteed upstream by
   ``open_composer.research.features.{universe,daily_features,labels}``; this
   module additionally reconstructs the PIT universe *as of each rebalance
   date* from monthly cohorts (never a static/current universe) and requires
   every feature value used for scoring to already exist on that date (no
   forward- or same-bar fill).
2. **Year-by-year expanding-window walk-forward**: :func:`build_weight_schedule`
   retrains (or, for parameter-free rules, simply re-applies) the strategy
   once per test year on an anchored, embargoed training window
   (``embargo_days = label_horizon_days``), matching plan section 3.4's
   "训练 2016-2017 → 测试 2018, ..., 直到 2026". A test year's weights never
   depend on a training fit that saw that year's data.
3. **Cost-adjusted, auto DSR trial count**: every experiment is scored net of
   ``cost_bps_per_side`` (and, separately, a stress cost for the mechanism-
   eval stress-return gate); :func:`_dsr_trial_count_for_family` counts
   distinct configs already in the ledger for the same family so the trial
   count is never hand-typed.

**Execution-path simplification, recorded per the plan's own "如实记录"
practice** (also flagged in this round's review, see the Step 11 ledger):
daily mark-to-market during a holding period uses **close-to-close** returns
starting the trading day after the Friday signal date, not a separately
modeled Monday-open OPG execution -- the same fixed-weight-until-next-
rebalance, close-marked convention already used and accepted in
``scripts/evaluate_cross_sectional_momentum_liquid500.py`` (Step 10 Wave 2).
This is a roughly one-trading-day timing approximation, not a look-ahead: the
Friday close used for the signal is real, already-observed data, and Monday's
close-to-Friday's-close is a return no later data than Monday's own close
enters. Modeling true next-bar-open execution (the product spec's
``execution.order_style=opg_limit``) is a next-iteration item, not something
this research-stage evaluation loop depends on for its verdicts.

**Cross-sectional statistics scope, recorded per the same review**: the
median-subtraction and percentile-rank in ``daily_features.py``/``labels.py``
are computed over the full historical PIT-universe *union* present in the
feature/label tables for a given date, not the exact monthly PIT cohort for
that date (a symbol admitted to the universe in a different month than the
current one, but still carrying a feature row on this date, is included in
that date's cross-sectional median/rank). ``build_weight_schedule`` applies
the *stricter*, correct PIT filter (this function's own
``universe_as_of_calendar_month``) when selecting which symbols may actually
be scored and held each week -- the wider population only affects the
market-relative feature values and label statistics, not portfolio
membership. Tightening the feature/label cross-section to the exact monthly
cohort is a next-iteration item.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import pandas as pd

from open_composer.research.kernel.datamodel import ResearchDataModel
from open_composer.research.kernel.gate_contract import (
    UNLEVERED_FAMILY_GATE_KEYS,
    load_preregistered_gates,
)
from open_composer.research.kernel.mechanism_eval import (
    Candidate,
    CandidateVerdict,
    evaluate_candidate,
)

ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = ROOT / "reports" / "research" / "ledger" / "experiments.jsonl"
TEARSHEET_DIR = ROOT / "reports" / "research" / "tearsheets"
MLFLOW_TRACKING_DIR = ROOT / "reports" / "research" / "mlruns"
NEW_GATE_CONTRACT_PATH = ROOT / "config" / "promotion" / "unlevered-family-paper-tier-gates.json"

#: 2018..2026 inclusive -- plan section 3.4's expanding-window test sequence
#: ("训练 2016-2017 → 测试 2018, ..., 直到 2026").
DEFAULT_TEST_YEARS: tuple[int, ...] = tuple(range(2018, 2027))
DEFAULT_TOP_K = 50
DEFAULT_COST_BPS_PER_SIDE = 10.0
DEFAULT_STRESS_COST_BPS_PER_SIDE = 25.0
#: DSR requires trial_count >= 2 (deflated_sharpe_probability); a brand-new
#: family's first experiment still needs a defined value.
_MIN_DSR_TRIAL_COUNT = 2


class RankingStrategy(Protocol):
    """Common interface for B0/B1/B2/B3: fit (optionally a no-op) once per
    test year on an embargoed, anchored training window; score once per
    weekly rebalance date on that date's PIT-eligible rows.
    """

    def fit(self, train_frame: pd.DataFrame) -> None: ...

    def score(self, asof_frame: pd.DataFrame) -> pd.Series: ...


@dataclass(frozen=True)
class ExperimentConfig:
    """A single, hashable candidate configuration (plan section 3.4: "一个候选配置").

    ``feature_set`` and ``model_kind`` are metadata for the ledger/tearsheet
    only -- the actual behavior comes entirely from the ``strategy_factory``
    and ``feature_columns`` passed to :func:`run_experiment`.
    """

    experiment_id: str
    family: str
    model_kind: str
    feature_set: str
    label_horizon_days: int
    feature_columns: tuple[str, ...]
    top_k: int | None = DEFAULT_TOP_K
    hedge: Literal["none", "spy_beta_hedge"] = "none"
    train_row_dates: Literal["all", "rebalance_dates"] = "all"
    #: Wave B item 4. ``"close_marked"`` (default, unchanged) is the
    #: close-to-close, one-trading-day-lagged approximation this module has
    #: used since 3.4 (see the module docstring's "execution-path
    #: simplification" note) -- every already-recorded B0-B3 experiment used
    #: this and its config_hash/results stay exactly reproducible.
    #: ``"next_open"`` instead fills at the following trading day's *open*
    #: (plan's "周五收盘信号 → 周一开盘成交 → 下一个周一开盘换仓"), via
    #: :func:`returns_from_weight_schedule`'s ``execution=`` argument.
    #: Recorded here (not a silent constant) because it enters config_hash
    #: and the ledger -- the two paths are different candidates, not the
    #: same candidate reported two ways, so comparing them means running
    #: both. See ``scripts/run_b3_grid.py``'s ``--execution`` flag and the
    #: Step 11 ledger's Wave B section for why only the winning candidate is
    #: ever run both ways rather than doubling the whole grid.
    execution: Literal["close_marked", "next_open"] = "close_marked"
    rebalance: str = "weekly_friday_signal_next_session_close_marked"
    weighting: str = "equal_weight"
    cost_bps_per_side: float = DEFAULT_COST_BPS_PER_SIDE
    stress_cost_bps_per_side: float = DEFAULT_STRESS_COST_BPS_PER_SIDE
    test_years: tuple[int, ...] = DEFAULT_TEST_YEARS
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def config_hash(self) -> str:
        payload = {
            "family": self.family,
            "model_kind": self.model_kind,
            "feature_set": self.feature_set,
            "label_horizon_days": self.label_horizon_days,
            "feature_columns": sorted(self.feature_columns),
            "top_k": self.top_k,
            "hedge": self.hedge,
            "train_row_dates": self.train_row_dates,
            "execution": self.execution,
            "rebalance": self.rebalance,
            "weighting": self.weighting,
            "cost_bps_per_side": self.cost_bps_per_side,
            "stress_cost_bps_per_side": self.stress_cost_bps_per_side,
            "test_years": list(self.test_years),
            "hyperparameters": self.hyperparameters,
        }
        blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


@dataclass(frozen=True)
class RebalanceEvent(ResearchDataModel):
    date: str
    universe_size: int
    selected: dict[str, float]
    portfolio_beta: float | None


@dataclass(frozen=True)
class ExperimentVerdict(ResearchDataModel):
    experiment_id: str
    config_hash: str
    family: str
    long_only: CandidateVerdict
    market_neutral: CandidateVerdict
    dsr_trial_count: int
    tearsheet_path: str | None
    mlflow_run_id: str | None
    ledger_appended: bool
    #: The walk-forward weight schedule run_experiment built internally, for
    #: callers that need turnover/capacity/holdings reporting beyond what
    #: .metrics carries (Wave B's step11-w2-model-ranking-2026-09.md report:
    #: "换手、容量（每只持仓的成交额占比）") without a second, redundant
    #: build_weight_schedule() call (B3's LightGBM refit-per-year is not
    #: cheap on this box). Never written to the ledger record dict below --
    #: that stays exactly as small as before; this is an in-memory-only field
    #: on the returned dataclass.
    schedule: list[RebalanceEvent]


def weekly_rebalance_dates(trading_dates: Sequence[pd.Timestamp]) -> list[pd.Timestamp]:
    """The last trading date of every ISO calendar week present in
    ``trading_dates`` -- plan section 3.5's "周五收盘出信号" (a short holiday
    week's last session stands in for a missing Friday, which is the
    intended behavior: the book still rebalances once that week).
    """
    index = pd.DatetimeIndex(sorted(trading_dates))
    if index.empty:
        return []
    iso = index.isocalendar()
    frame = pd.DataFrame({"date": index, "iso_year": iso["year"], "iso_week": iso["week"]})
    last_per_week = frame.groupby(["iso_year", "iso_week"])["date"].max()
    return sorted(last_per_week.tolist())


def universe_as_of_calendar_month(universe_panel: pd.DataFrame, date: pd.Timestamp) -> set[str]:
    """The PIT universe cohort in effect on ``date``: the most recent
    calendar-month cohort whose ``month_end`` is ``<= date`` (see
    ``universe.py``'s ``UNIVERSE_PANEL_COLUMNS`` docstring for why this must
    group by calendar month, not the exact ``month_end`` value).
    """
    eligible = universe_panel.loc[universe_panel["month_end"] <= date]
    if eligible.empty:
        return set()
    latest_month = eligible["month_end"].dt.to_period("M").max()
    cohort = eligible.loc[eligible["month_end"].dt.to_period("M") == latest_month]
    return set(cohort["symbol"])


def _embargo_cutoff(
    trading_calendar: pd.DatetimeIndex, first_test_date: pd.Timestamp, embargo_days: int
) -> pd.Timestamp:
    position = trading_calendar.searchsorted(first_test_date, side="left")
    cutoff_position = position - embargo_days
    if cutoff_position < 1:
        raise ValueError(
            f"not enough trading history before {first_test_date.date()} to embargo "
            f"{embargo_days} day(s)"
        )
    return trading_calendar[cutoff_position - 1]


def build_weight_schedule(
    *,
    panel: pd.DataFrame,
    universe_panel: pd.DataFrame,
    strategy_factory: Callable[[], RankingStrategy],
    feature_columns: Sequence[str],
    label_column: str,
    label_horizon_days: int,
    test_years: Sequence[int],
    top_k: int | None,
    hedge: Literal["none", "spy_beta_hedge"],
    beta_column: str = "beta_252_spy",
    extra_train_columns: Sequence[str] = (),
    train_row_dates: Literal["all", "rebalance_dates"] = "all",
) -> list[RebalanceEvent]:
    """Walk-forward weight schedule: retrain once per ``test_years`` entry on
    an anchored, embargoed window, then score every weekly rebalance date
    within that year using that year's frozen fit. See module docstring for
    the three honesty requirements this enforces.

    ``train_row_dates`` selects which rows of the embargoed window a fit
    sees. ``"all"`` uses every trading day (the original behavior, kept as the
    default so already-recorded results stay reproducible).
    ``"rebalance_dates"`` uses only the weekly rebalance days -- the days the
    model is actually applied on. That is a fivefold reduction in training
    rows, which is what makes the wide daily+intraday panel fit in memory on
    this box at all, but it is not only a memory trick: daily rows carry
    ``h``-day overlapping forward labels, so their nominal count badly
    overstates the independent sample, and training on the same cross-sections
    the model is served on removes a train/serve mismatch. Which one predicts
    better is an empirical question, so this is a recorded config field (it
    enters ``ExperimentConfig.config_hash`` and the ledger) rather than a
    silent constant -- run both and compare.

    ``extra_train_columns`` (Wave B, B3's grid): columns to carry into
    ``train_frame`` in addition to ``feature_columns``/``label_column``,
    without requiring them to be non-null. B3's ``GridSelectedLightGBMStrategy``
    needs all three label horizons (``label_rank_5/10/21``) available in one
    ``fit()`` call (one grid cell per horizon), but this function's outer
    ``label_column`` is a single, official column -- callers pass the other
    horizons here. Deliberately excluded from the row-level ``notna`` mask
    below (unlike ``feature_columns``/``label_column``): a strategy that
    needs several label columns at once already does its own per-column
    ``dropna`` internally (one cell at a time), so requiring every extra
    column to be simultaneously non-null here would wrongly drop rows a
    shorter-horizon cell could have used just because a longer-horizon label
    is unresolved near a symbol's last trading day. Defaults to ``()``, so
    every existing caller (B0-B3's single-label strategies) is unaffected.
    """
    trading_calendar = pd.DatetimeIndex(sorted(panel["trade_date"].unique()))
    # Every weekly rebalance day in the whole history, computed once; the
    # per-year embargoed cutoff below restricts it to the training window.
    # Same weekly grid the schedule itself trades on.
    training_row_dates = (
        pd.DatetimeIndex(weekly_rebalance_dates(trading_calendar))
        if train_row_dates == "rebalance_dates"
        else pd.DatetimeIndex([])
    )
    events: list[RebalanceEvent] = []
    for year in test_years:
        year_dates = trading_calendar[trading_calendar.year == year]
        if len(year_dates) == 0:
            continue
        rebalance_dates = [date for date in weekly_rebalance_dates(year_dates) if date.year == year]
        if not rebalance_dates:
            continue
        train_cutoff = _embargo_cutoff(trading_calendar, rebalance_dates[0], label_horizon_days)
        # Memory, not style: ``panel.loc[mask].dropna(subset=...)`` made two
        # full-width copies of a multi-GB panel for every test year -- the
        # mask copy carries every column, then ``dropna`` copies its result
        # again. Building the mask column by column (each ``notna`` is a 6M
        # -element bool, ~6MB) and selecting only the columns a fit actually
        # consumes leaves exactly one narrow copy. Same rows as before.
        # ``fit`` therefore receives feature columns, the label column and
        # ``trade_date`` (kept for any future time-weighted fit); it does not
        # receive ``symbol``, whose object dtype is the panel's single
        # largest column and which no B0-B3 strategy reads during training.
        required_columns = [*feature_columns, label_column]
        train_mask = panel["trade_date"] <= train_cutoff
        if train_row_dates == "rebalance_dates":
            train_mask &= panel["trade_date"].isin(training_row_dates)
        for column in required_columns:
            train_mask &= panel[column].notna()
        train_columns = [*required_columns, *extra_train_columns]
        train_frame = panel.loc[train_mask, ["trade_date", *train_columns]]
        del train_mask
        strategy = strategy_factory()
        strategy.fit(train_frame)

        for date in rebalance_dates:
            universe_symbols = universe_as_of_calendar_month(universe_panel, date)
            asof_frame = panel.loc[
                (panel["trade_date"] == date) & (panel["symbol"].isin(universe_symbols))
            ].dropna(subset=feature_columns)
            if asof_frame.empty:
                events.append(
                    RebalanceEvent(
                        date=date.isoformat(), universe_size=0, selected={}, portfolio_beta=None
                    )
                )
                continue
            scores = strategy.score(asof_frame)
            selected_ids = scores.nlargest(top_k).index if top_k is not None else scores.index
            selected_ids = [symbol for symbol in selected_ids if symbol in scores.index]
            weight = 1.0 / len(selected_ids) if selected_ids else 0.0
            weights = dict.fromkeys(selected_ids, weight)

            portfolio_beta = None
            if hedge == "spy_beta_hedge" and weights:
                beta_by_symbol = asof_frame.set_index("symbol")[beta_column]
                betas = beta_by_symbol.reindex(list(weights)).fillna(0.0)
                portfolio_beta = float(sum(betas[symbol] * w for symbol, w in weights.items()))
                weights["__SPY_HEDGE__"] = -portfolio_beta

            events.append(
                RebalanceEvent(
                    date=date.isoformat(),
                    universe_size=len(universe_symbols),
                    selected=weights,
                    portfolio_beta=portfolio_beta,
                )
            )
    return events


def returns_from_weight_schedule(
    schedule: Sequence[RebalanceEvent],
    price_wide: pd.DataFrame,
    spy_returns: pd.Series,
    *,
    cost_bps_per_side: float,
    include_hedge: bool,
    execution: Literal["close_marked", "next_open"] = "close_marked",
    open_wide: pd.DataFrame | None = None,
) -> pd.Series:
    """Fixed-weight-until-next-rebalance daily returns, generalized to an
    optional SPY hedge leg and (Wave B item 4) a choice of execution price.

    ``execution="close_marked"`` (default, byte-for-byte unchanged from this
    function's original implementation -- every already-recorded B0-B3
    experiment used exactly this path and stays reproducible) marks to
    market with **close-to-close** daily returns starting the trading day
    after the Friday signal date -- see module docstring's "execution-path
    simplification" note; the same convention as
    ``scripts/evaluate_cross_sectional_momentum_liquid500.py``'s
    ``_cohort_daily_returns``.

    ``execution="next_open"`` instead fills the Friday close signal at the
    *following* trading day's **open** (plan's "周五收盘信号 → 周一开盘成交 →
    下一个周一开盘换仓"), requiring ``open_wide`` (same shape/index/columns
    contract as ``price_wide``, priced off ``open`` instead of ``close``).
    An order filled at Monday's open cannot capture Monday's own open-to-
    close move for the *new* weights -- that session's move is still the old
    position's exposure right up to the fill -- so the earliest full trading
    day of realized P&L under the new weights is the day *after* the fill.
    Concretely this is the identical event-window logic as
    ``close_marked``, shifted by exactly one trading day, using
    **open-to-open** daily returns (``open_wide.pct_change()``) instead of
    close-to-close ones; the two modes share one code path below via
    ``window_lag`` (0 for close_marked, 1 for next_open), which is why
    close_marked's output is provably unchanged by this generalization.

    Trading cost is charged on the day the order actually executes
    (``dates[entry_pos]``, the trading day right after the Friday signal --
    the first day of the close_marked return window, but the day *before*
    the next_open return window starts) in both modes: written as a
    get-or-create update to ``all_returns`` after the window is filled,
    rather than being special-cased to "day zero of this iteration's
    window" the way the original close_marked-only implementation did --
    for close_marked those two descriptions name the same day (so the
    output is identical), but only writing it this way makes next_open's
    cost land on the fill day rather than a day late.
    """
    if execution == "next_open":
        if open_wide is None:
            raise ValueError("execution='next_open' requires open_wide")
        mark_prices = open_wide
        window_lag = 1
    elif execution == "close_marked":
        mark_prices = price_wide
        window_lag = 0
    else:
        raise ValueError(f"unknown execution {execution!r}, expected 'close_marked' or 'next_open'")

    daily_returns = mark_prices.pct_change()
    dates = daily_returns.index
    # turnover (Sigma|delta w|) is already two-sided -- one rebalance that
    # sells $x of A and buys $x of B has turnover 2x, correctly reflecting
    # two trades' worth of cost. Multiplying by 2*cost_bps_per_side on top of
    # that double-counts: a steady-state weekly turnover of f was being
    # charged 2f * 2*cost_bps_per_side instead of 2f * cost_bps_per_side, and
    # a fresh 100% initial allocation was charged 20bps instead of 10bps.
    # Found in review 2026-09-07; see the Step 11 ledger for the real-ledger-
    # entry cleanup this required and the Step 10 caveat it implies (
    # scripts/evaluate_cross_sectional_momentum_liquid500.py shares this same
    # formula, so its already-negative conclusions were evaluated at
    # effectively double the stated cost, not understated).
    cost_rate = cost_bps_per_side / 10_000.0
    all_returns: dict[pd.Timestamp, float] = {}
    previous_weights: dict[str, float] = {}
    active = [event for event in schedule if event.selected]
    for i, event in enumerate(active):
        weights = dict(event.selected)
        if not include_hedge:
            weights.pop("__SPY_HEDGE__", None)
        symbols_touched = set(weights) | set(previous_weights)
        turnover = sum(
            abs(weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0))
            for symbol in symbols_touched
        )
        cost = turnover * cost_rate

        event_date = pd.Timestamp(event.date)
        # entry_pos: the trading day the order executes on, regardless of
        # execution mode -- the day right after the Friday signal.
        entry_pos = dates.searchsorted(event_date, side="right")
        start = entry_pos + window_lag
        end = (
            dates.searchsorted(pd.Timestamp(active[i + 1].date), side="right") + window_lag - 1
            if i + 1 < len(active)
            else len(dates) - 1
        )
        if start > end:
            previous_weights = weights
            continue

        stock_weights = {s: w for s, w in weights.items() if s != "__SPY_HEDGE__"}
        held_columns = [s for s in stock_weights if s in mark_prices.columns]
        window = daily_returns.iloc[start : end + 1]
        stock_contribution = (
            window[held_columns].fillna(0.0).mul(pd.Series(stock_weights)[held_columns], axis=1)
            if held_columns
            else pd.DataFrame(0.0, index=window.index, columns=[])
        )
        day_returns = stock_contribution.sum(axis=1)
        if "__SPY_HEDGE__" in weights:
            hedge_weight = weights["__SPY_HEDGE__"]
            aligned_spy = spy_returns.reindex(window.index).fillna(0.0)
            day_returns = day_returns + hedge_weight * aligned_spy

        for date, value in day_returns.items():
            all_returns[date] = all_returns.get(date, 0.0) + float(value)

        cost_date = dates[entry_pos]
        all_returns[cost_date] = all_returns.get(cost_date, 0.0) - cost
        previous_weights = weights

    if not all_returns:
        raise ValueError("no holding period produced any returns")
    index = pd.DatetimeIndex(sorted(all_returns))
    return pd.Series([all_returns[ts] for ts in index], index=index, name="portfolio_return")


def _oos_fold_returns_by_year(returns: pd.Series, test_years: Sequence[int]) -> list[list[float]]:
    folds = []
    for year in test_years:
        year_returns = returns.loc[returns.index.year == year]
        if not year_returns.empty:
            folds.append(year_returns.tolist())
    return folds


def _build_candidate(
    candidate_id: str, oos_returns: pd.Series, stress_returns: pd.Series, test_years: Sequence[int]
) -> Candidate:
    aligned_stress = stress_returns.reindex(oos_returns.index)
    if aligned_stress.isna().any():
        raise ValueError(f"{candidate_id}: stress returns missing rows the primary stream has")
    return Candidate(
        candidate_id=candidate_id,
        mechanism_family="model_ranking_portfolio",
        param_vector={},
        oos_return_stream=[float(v) for v in oos_returns.tolist()],
        oos_dates=[ts.isoformat() for ts in oos_returns.index],
        oos_fold_returns=_oos_fold_returns_by_year(oos_returns, test_years),
        development_returns=[],
        development_dates=[],
        stress_return_stream=[float(v) for v in aligned_stress.tolist()],
    )


def _dsr_trial_count_for_family(family: str, current_config_hash: str) -> int:
    """DSR trial count = count of distinct config hashes already recorded in
    the ledger for ``family`` (including the current one) -- plan section
    3.4: "DSR 的试验数自动取账本里同一族的实验数,不用人手填". Deliberately
    simpler than ``effective_trials.effective_independent_trials``'s
    correlation clustering (which the older kernel path uses): with a
    handful of experiments per family this round, a plain count is what the
    plan asks for and is easy to audit by reading the ledger file directly.
    """
    hashes = {current_config_hash}
    if LEDGER_PATH.exists():
        for line in LEDGER_PATH.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("family") == family:
                hashes.add(record["config_hash"])
    return max(len(hashes), _MIN_DSR_TRIAL_COUNT)


def _append_ledger(record: dict[str, Any]) -> bool:
    """Append ``record`` unless its ``config_hash`` is already present for
    that family (plan: "同一配置哈希重复运行只记一次"). Returns whether a new
    line was written.
    """
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LEDGER_PATH.exists():
        for line in LEDGER_PATH.read_text().splitlines():
            if not line.strip():
                continue
            existing = json.loads(line)
            if (
                existing.get("config_hash") == record["config_hash"]
                and existing.get("family") == record["family"]
            ):
                return False
    with LEDGER_PATH.open("a") as handle:
        handle.write(json.dumps(record, default=str) + "\n")
    return True


def _write_tearsheet(experiment_id: str, returns: pd.Series, benchmark: pd.Series) -> str | None:
    try:
        import quantstats as qs
    except ImportError:
        return None
    TEARSHEET_DIR.mkdir(parents=True, exist_ok=True)
    output_path = TEARSHEET_DIR / f"{experiment_id}.html"
    aligned_benchmark = benchmark.reindex(returns.index).fillna(0.0)
    qs.reports.html(
        returns,
        benchmark=aligned_benchmark,
        output=str(output_path),
        title=f"{experiment_id} vs SPY",
    )
    return str(output_path)


def _log_mlflow_run(
    config: ExperimentConfig,
    long_only: CandidateVerdict,
    market_neutral: CandidateVerdict,
) -> str | None:
    try:
        import mlflow
    except ImportError:
        return None
    MLFLOW_TRACKING_DIR.mkdir(parents=True, exist_ok=True)
    # mlflow>=3 refuses the classic per-run-directory file store ("maintenance
    # mode") unless explicitly opted back in. The plan asks for exactly that
    # store (plan section 3.4: "本地文件后端"; section 6: "mlflow ui
    # --backend-store-uri reports/research/mlruns" expects a directory of run
    # folders, not a sqlite URI), so opt in rather than switch backends.
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    mlflow.set_tracking_uri(f"file://{MLFLOW_TRACKING_DIR}")
    mlflow.set_experiment(config.family)
    with mlflow.start_run(run_name=config.experiment_id) as run:
        mlflow.log_params(
            {
                "model_kind": config.model_kind,
                "feature_set": config.feature_set,
                "label_horizon_days": config.label_horizon_days,
                "top_k": config.top_k,
                "hedge": config.hedge,
                "train_row_dates": config.train_row_dates,
                "execution": config.execution,
                "cost_bps_per_side": config.cost_bps_per_side,
                **{f"hp_{k}": v for k, v in config.hyperparameters.items()},
            }
        )
        for prefix, verdict in (("long_only", long_only), ("market_neutral", market_neutral)):
            for key, value in verdict.metrics.items():
                if isinstance(value, (int, float)) and math.isfinite(float(value)):
                    mlflow.log_metric(f"{prefix}_{key}", float(value))
            mlflow.log_metric(f"{prefix}_all_gates_pass", float(verdict.all_gates_pass))
        return run.info.run_id


def run_experiment(
    config: ExperimentConfig,
    *,
    panel: pd.DataFrame,
    universe_panel: pd.DataFrame,
    label_column: str,
    strategy_factory: Callable[[], RankingStrategy],
    spy_returns: pd.Series,
    qqq_returns: pd.Series,
    tqqq_returns: pd.Series,
    bil_returns: pd.Series,
    write_ledger: bool = True,
    write_tearsheet: bool = True,
    write_mlflow: bool = True,
    extra_train_columns: Sequence[str] = (),
) -> ExperimentVerdict:
    """Run one candidate configuration end to end: walk-forward weight
    schedule -> long-only and market-neutral daily return streams (base and
    stress cost) -> ``mechanism_eval.evaluate_candidate`` against the
    volatility-matched-SPY unlevered-family contract -> ledger append ->
    QuantStats tearsheet -> MLflow run.

    ``extra_train_columns`` is forwarded to :func:`build_weight_schedule`
    unchanged (see its docstring) -- B0-B2 never pass this; Wave B's B3 grid
    (``scripts/run_b3_grid.py``) passes the two label horizons not already
    named by ``label_column`` so ``GridSelectedLightGBMStrategy.fit`` can see
    all three at once.
    """
    config_hash = config.config_hash()
    price_wide = panel.pivot(index="trade_date", columns="symbol", values="close")
    # "open" is only present once daily_features.py's passthrough (Wave B
    # item 4, 2026-09-08) has been (re)built for the years panel covers --
    # older/partial panels without it can still run close_marked (the
    # default and the only path every already-recorded B0-B3 experiment
    # used); asking for next_open without it fails fast inside
    # returns_from_weight_schedule rather than silently falling back.
    open_wide = (
        panel.pivot(index="trade_date", columns="symbol", values="open")
        if "open" in panel.columns
        else None
    )

    schedule = build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=strategy_factory,
        feature_columns=list(config.feature_columns),
        label_column=label_column,
        label_horizon_days=config.label_horizon_days,
        test_years=config.test_years,
        top_k=config.top_k,
        hedge=config.hedge,
        extra_train_columns=extra_train_columns,
        train_row_dates=config.train_row_dates,
    )

    long_base = returns_from_weight_schedule(
        schedule,
        price_wide,
        spy_returns,
        cost_bps_per_side=config.cost_bps_per_side,
        include_hedge=False,
        execution=config.execution,
        open_wide=open_wide,
    )
    long_stress = returns_from_weight_schedule(
        schedule,
        price_wide,
        spy_returns,
        cost_bps_per_side=config.stress_cost_bps_per_side,
        include_hedge=False,
        execution=config.execution,
        open_wide=open_wide,
    )
    neutral_base = returns_from_weight_schedule(
        schedule,
        price_wide,
        spy_returns,
        cost_bps_per_side=config.cost_bps_per_side,
        include_hedge=True,
        execution=config.execution,
        open_wide=open_wide,
    )
    neutral_stress = returns_from_weight_schedule(
        schedule,
        price_wide,
        spy_returns,
        cost_bps_per_side=config.stress_cost_bps_per_side,
        include_hedge=True,
        execution=config.execution,
        open_wide=open_wide,
    )

    long_candidate = _build_candidate(
        f"{config.experiment_id}-long", long_base, long_stress, config.test_years
    )
    neutral_candidate = _build_candidate(
        f"{config.experiment_id}-neutral", neutral_base, neutral_stress, config.test_years
    )

    gates = load_preregistered_gates(
        NEW_GATE_CONTRACT_PATH, required_keys=UNLEVERED_FAMILY_GATE_KEYS
    )
    dsr_trial_count = _dsr_trial_count_for_family(config.family, config_hash)

    long_verdict = evaluate_candidate(
        long_candidate,
        qqq_returns=qqq_returns,
        tqqq_returns=tqqq_returns,
        bil_returns=bil_returns,
        gates=gates,
        dsr_trial_count=dsr_trial_count,
        benchmark_returns=spy_returns,
        benchmark_name="SPY",
    )
    neutral_verdict = evaluate_candidate(
        neutral_candidate,
        qqq_returns=qqq_returns,
        tqqq_returns=tqqq_returns,
        bil_returns=bil_returns,
        gates=gates,
        dsr_trial_count=dsr_trial_count,
        benchmark_returns=spy_returns,
        benchmark_name="SPY",
    )

    tearsheet_path = None
    if write_tearsheet:
        tearsheet_path = _write_tearsheet(config.experiment_id, long_base, spy_returns)

    mlflow_run_id = None
    if write_mlflow:
        mlflow_run_id = _log_mlflow_run(config, long_verdict, neutral_verdict)

    ledger_appended = False
    if write_ledger:
        record = {
            "experiment_id": config.experiment_id,
            "config_hash": config_hash,
            "family": config.family,
            "model_kind": config.model_kind,
            "feature_set": config.feature_set,
            "label_horizon_days": config.label_horizon_days,
            "top_k": config.top_k,
            "hedge": config.hedge,
            "train_row_dates": config.train_row_dates,
            "execution": config.execution,
            "hyperparameters": config.hyperparameters,
            "test_years": list(config.test_years),
            "dsr_trial_count": dsr_trial_count,
            "long_only": {
                "metrics": long_verdict.metrics,
                "gate_results": long_verdict.gate_results,
                "all_gates_pass": long_verdict.all_gates_pass,
            },
            "market_neutral": {
                "metrics": neutral_verdict.metrics,
                "gate_results": neutral_verdict.gate_results,
                "all_gates_pass": neutral_verdict.all_gates_pass,
            },
            "tearsheet_path": tearsheet_path,
            "mlflow_run_id": mlflow_run_id,
            "recorded_at": pd.Timestamp.now(tz="UTC").isoformat(),
        }
        ledger_appended = _append_ledger(record)

    return ExperimentVerdict(
        experiment_id=config.experiment_id,
        config_hash=config_hash,
        family=config.family,
        long_only=long_verdict,
        market_neutral=neutral_verdict,
        dsr_trial_count=dsr_trial_count,
        tearsheet_path=tearsheet_path,
        mlflow_run_id=mlflow_run_id,
        ledger_appended=ledger_appended,
        schedule=schedule,
    )
