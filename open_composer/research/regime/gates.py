"""Preregistered gate evaluation for Step 12 Group B (recent-regime,
high-hit-rate) candidates.

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 1. Wraps
``open_composer.research.kernel.gate_contract.load_preregistered_gates``
(the same git-blob-proof-of-preregistration machinery Group A's kernel path
uses) with Group B's own key set and its own contract file --
``config/promotion/recent-regime-high-hit-rate-gates.json`` -- instead of
Group A's ``config/promotion/unlevered-family-paper-tier-gates.json``. The
two contracts are independent; passing or failing one says nothing about
the other (plan section 5: "两组并行...互不套用门槛").

Reuses ``mechanism_eval.annualized_cagr``/``max_drawdown`` and
``campaign_statistics.annualized_sharpe``/``deflated_sharpe_probability``
directly (plan section 4: "可以调用 mechanism_eval.evaluate_candidate 拿基础
指标再叠加自己的" -- here via its sibling free functions, since Group B's
candidates are not ``mechanism_eval.Candidate`` objects with rolling-origin
fold structure; they are one continuous quarterly walk-forward stream sliced
into a recent-gated window and a disclosure-only window). Does not import
anything from ``loop.py`` other than the shared, already-existing
``LEDGER_PATH`` constant (read-only reuse of the one ledger file both groups
append to); the family-scoped DSR trial-count helper below is a fresh,
Group-B-owned reimplementation of the same idea
(``loop._dsr_trial_count_for_family``), not an import of that private
function, per the plan's file-ownership rule (section 4: file ownership is
by directory, not by which module happens to have a matching helper).
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from open_composer.research.campaign_statistics import (
    annualized_sharpe,
    deflated_sharpe_probability,
)
from open_composer.research.kernel.datamodel import ResearchDataModel
from open_composer.research.kernel.gate_contract import (
    PreregisteredGates,
    load_preregistered_gates,
)
from open_composer.research.kernel.loop import LEDGER_PATH
from open_composer.research.kernel.mechanism_eval import annualized_cagr, max_drawdown
from open_composer.research.regime import metrics as regime_metrics

ROOT = Path(__file__).resolve().parents[3]
GATE_CONTRACT_PATH = ROOT / "config" / "promotion" / "recent-regime-high-hit-rate-gates.json"

#: One shared ledger family for every Group B experiment (F1-F5), mirroring
#: Group A's ``step11_baseline_chain`` convention: each F-item is its own
#: ``experiment_id`` under this one family, so the DSR trial count grows
#: honestly as more Group B experiments are recorded rather than resetting
#: per F-item.
LEDGER_FAMILY = "groupb_recent_regime_high_hit_rate"

RECENT_REGIME_GATE_KEYS: tuple[str, ...] = (
    "hit_rate_weekly_minimum",
    "hit_rate_daily_or_intraday_minimum",
    "cagr_recent_net_minimum",
    "max_drawdown_recent_minimum",
    "sharpe_excess_bil_recent_minimum",
    "profit_factor_minimum",
    "positive_quarter_fraction_minimum",
    "dsr_probability_minimum",
    "stress_cost_recent_cagr_minimum",
    "ml_placebo_rank_ic_abs_maximum",
)

DEFAULT_DSR_HAC_LAG = 21
#: DSR requires trial_count >= 2 (deflated_sharpe_probability); a brand-new
#: family's first experiment still needs a defined value -- same rationale
#: and same value as loop.py's own ``_MIN_DSR_TRIAL_COUNT``.
_MIN_DSR_TRIAL_COUNT = 2
RECENT_WINDOW_START = "2024-01-02"
DISCLOSURE_WINDOW_START = "2018-01-01"
DISCLOSURE_WINDOW_END = "2023-12-31"
REPLAY_YEAR = 2022

HoldingPeriodKind = Literal["weekly", "daily_or_intraday"]


def load_recent_regime_gates(path: Path | str = GATE_CONTRACT_PATH) -> PreregisteredGates:
    """Load the Group B recent-regime contract (see module docstring)."""
    return load_preregistered_gates(path, required_keys=RECENT_REGIME_GATE_KEYS)


def dsr_trial_count_for_family(
    family: str,
    current_config_hash: str,
    *,
    ledger_path: Path = LEDGER_PATH,
) -> int:
    """Distinct config hashes recorded under ``family`` in the shared ledger,
    including ``current_config_hash`` -- plan section 1: "DSR 的试验数自动取
    账本里 groupb_ 同族实验数,不用人手填". Mirrors
    ``loop._dsr_trial_count_for_family`` exactly (same shared ledger file,
    same "count distinct config hashes for this family" definition,
    same minimum-2 clamp); reimplemented here because that function is
    private to ``loop.py``, a file Group B does not own or modify.
    """
    hashes = {current_config_hash}
    if ledger_path.exists():
        for line in ledger_path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("family") == family:
                config_hash = record.get("config_hash")
                if config_hash:
                    hashes.add(config_hash)
    return max(len(hashes), _MIN_DSR_TRIAL_COUNT)


@dataclass(frozen=True)
class RegimeVerdict(ResearchDataModel):
    """One Group B candidate's recent-regime metrics, gate results, and
    disclosure-only figures."""

    experiment_id: str
    family: str
    config_hash: str
    holding_period: HoldingPeriodKind
    is_ml: bool
    #: True for F5 (the leveraged beta-exposure-router reference item):
    #: metrics/gates are still computed for side-by-side comparison, but
    #: ``promotion_eligible`` is forced False regardless of gate outcomes
    #: (plan section 2: "F5 参考项（不参与晋级）").
    reference_only: bool
    dsr_trial_count: int
    metrics: dict[str, float | int | str | None]
    disclosure: dict[str, float | int | str | None]
    gate_results: dict[str, bool]
    gates_not_applicable: tuple[str, ...]
    all_gates_pass: bool
    gates_provenance: str
    gate_contract: dict[str, str]

    @property
    def evaluated_gate_count(self) -> int:
        return len(self.gate_results) - len(self.gates_not_applicable)

    @property
    def promotion_eligible(self) -> bool:
        if self.reference_only:
            return False
        return self.all_gates_pass and self.gates_provenance == "preregistered"


def _slice_from(returns: pd.Series, start: str, end: str | None = None) -> pd.Series:
    start_ts = pd.Timestamp(start)
    if returns.index.tz is not None and start_ts.tzinfo is None:
        start_ts = start_ts.tz_localize(returns.index.tz)
    mask = returns.index >= start_ts
    if end is not None:
        end_ts = pd.Timestamp(end)
        if returns.index.tz is not None and end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize(returns.index.tz)
        mask &= returns.index <= end_ts
    return returns.loc[mask]


def _disclosure_block(
    full_returns: pd.Series,
    holding_period_net_returns_disclosure: Sequence[float] | None,
) -> dict[str, float | int | str | None]:
    disclosure_slice = _slice_from(full_returns, DISCLOSURE_WINDOW_START, DISCLOSURE_WINDOW_END)
    if disclosure_slice.empty:
        return {
            "cagr_2018_2023": None,
            "max_drawdown_2018_2023": None,
            "hit_rate_2018_2023": None,
            "return_skewness_2018_2023": None,
            "worst_single_week_return_2018_2023": None,
            "disclosure_2018_2023_unavailable_reason": (
                "no return data in the 2018-01-01..2023-12-31 window"
            ),
        }
    block: dict[str, float | int | str | None] = {
        "cagr_2018_2023": annualized_cagr(disclosure_slice),
        "max_drawdown_2018_2023": max_drawdown(disclosure_slice),
        "hit_rate_2018_2023": (
            regime_metrics.hit_rate(holding_period_net_returns_disclosure)
            if holding_period_net_returns_disclosure
            else None
        ),
        "return_skewness_2018_2023": regime_metrics.return_skewness(disclosure_slice),
        "worst_single_week_return_2018_2023": regime_metrics.worst_single_week_return(
            disclosure_slice
        ),
    }
    return block


def evaluate_regime_candidate(
    *,
    experiment_id: str,
    config_hash: str,
    full_returns: pd.Series,
    full_stress_returns: pd.Series,
    bil_returns: pd.Series,
    holding_period: HoldingPeriodKind,
    holding_period_net_returns_recent: Sequence[float],
    holding_period_net_returns_disclosure: Sequence[float] | None = None,
    trade_count_recent: int | None = None,
    turnover_annualized_recent: float | None = None,
    family: str = LEDGER_FAMILY,
    is_ml: bool = False,
    placebo_rank_ic_abs: float | None = None,
    reference_only: bool = False,
    gates: PreregisteredGates | None = None,
    dsr_hac_lag: int = DEFAULT_DSR_HAC_LAG,
) -> RegimeVerdict:
    """Score one Group B candidate's recent-window (2024-01-02..latest)
    return stream against the preregistered recent-regime contract, and
    compute the mandatory, non-gated 2018-2023/skew/turnover/quarterly/2022-
    replay disclosure block (plan section 1).

    ``full_returns``/``full_stress_returns`` are the candidate's complete
    available-history daily net-return streams (base and 25bp-stress cost
    respectively) -- this function slices the recent-gated and disclosure-
    only windows out of them itself, so every candidate is sliced
    identically. ``holding_period_net_returns_recent`` must already be
    restricted to holding periods realized within the recent-gated window
    and must already exclude flat/no-position periods (see
    ``regime_metrics.hit_rate``).
    """
    resolved_gates = gates or load_recent_regime_gates()
    thresholds = resolved_gates.values
    gates_provenance = "preregistered"
    gate_contract = resolved_gates.as_provenance()

    recent = _slice_from(full_returns, RECENT_WINDOW_START)
    if recent.empty:
        raise ValueError(f"{experiment_id}: no returns on/after {RECENT_WINDOW_START}")
    recent_stress = _slice_from(full_stress_returns, RECENT_WINDOW_START)
    if recent_stress.empty:
        raise ValueError(f"{experiment_id}: no stress returns on/after {RECENT_WINDOW_START}")
    recent_bil = bil_returns.reindex(recent.index)
    if recent_bil.isna().any():
        raise ValueError(f"{experiment_id}: BIL benchmark alignment produced missing rows")

    cagr_recent_net = annualized_cagr(recent)
    max_drawdown_recent = max_drawdown(recent)
    excess_bil = (recent - recent_bil).to_numpy()
    sharpe_excess_bil_recent = annualized_sharpe(excess_bil)
    dsr_trial_count = dsr_trial_count_for_family(family, config_hash)
    dsr_probability = deflated_sharpe_probability(
        excess_bil, trial_count=dsr_trial_count, hac_lag=dsr_hac_lag
    )
    hit = regime_metrics.hit_rate(holding_period_net_returns_recent)
    pf = regime_metrics.profit_factor(holding_period_net_returns_recent)
    pqf = regime_metrics.positive_quarter_fraction(recent)
    stress_cagr_recent = annualized_cagr(recent_stress)

    hit_rate_key = (
        "hit_rate_weekly_minimum"
        if holding_period == "weekly"
        else ("hit_rate_daily_or_intraday_minimum")
    )
    gate_results: dict[str, bool] = {
        "hit_rate_by_holding_period": hit >= thresholds[hit_rate_key],
        "cagr_recent_net": cagr_recent_net >= thresholds["cagr_recent_net_minimum"],
        "max_drawdown_recent": max_drawdown_recent >= thresholds["max_drawdown_recent_minimum"],
        "sharpe_excess_bil_recent": (
            sharpe_excess_bil_recent >= thresholds["sharpe_excess_bil_recent_minimum"]
        ),
        "profit_factor": pf >= thresholds["profit_factor_minimum"],
        "positive_quarter_fraction": pqf >= thresholds["positive_quarter_fraction_minimum"],
        "dsr_probability": dsr_probability >= thresholds["dsr_probability_minimum"],
        "stress_cost_still_positive": (
            stress_cagr_recent > thresholds["stress_cost_recent_cagr_minimum"]
        ),
    }
    gates_not_applicable: tuple[str, ...] = ()
    if is_ml:
        if placebo_rank_ic_abs is None:
            raise ValueError("is_ml=True requires placebo_rank_ic_abs")
        gate_results["ml_placebo_rank_ic"] = (
            abs(placebo_rank_ic_abs) < thresholds["ml_placebo_rank_ic_abs_maximum"]
        )
    else:
        # Declared, not silently omitted -- mirrors mechanism_eval's
        # gates_not_applicable pattern for the QQQ-capture gates on an
        # orthogonal candidate: a gate that could not have failed for a
        # structural reason (this candidate fits no model at all) must not
        # be allowed to inflate an "N of N gates passed" headline count.
        gate_results["ml_placebo_rank_ic"] = True
        gates_not_applicable = ("ml_placebo_rank_ic",)

    all_gates_pass = all(gate_results.values())

    metrics: dict[str, float | int | str | None] = {
        "cagr_recent_net": cagr_recent_net,
        "max_drawdown_recent": max_drawdown_recent,
        "sharpe_excess_bil_recent": sharpe_excess_bil_recent,
        "hit_rate_by_holding_period": hit,
        "profit_factor": pf,
        "positive_quarter_fraction": pqf,
        "dsr_probability": dsr_probability,
        "stress_cost_recent_cagr_net": stress_cagr_recent,
        "recent_window_start": recent.index.min().date().isoformat(),
        "recent_window_end": recent.index.max().date().isoformat(),
        "recent_window_row_count": int(len(recent)),
        "holding_period_count_recent": len(holding_period_net_returns_recent),
    }
    if is_ml:
        metrics["ml_placebo_rank_ic_abs"] = (
            abs(placebo_rank_ic_abs) if placebo_rank_ic_abs is not None else None
        )

    disclosure = _disclosure_block(full_returns, holding_period_net_returns_disclosure)
    disclosure["return_skewness_recent"] = regime_metrics.return_skewness(recent)
    disclosure["worst_single_week_return_recent"] = regime_metrics.worst_single_week_return(recent)
    disclosure["quarterly_returns_2024_2026"] = regime_metrics.quarterly_returns(recent)
    disclosure["replay_2022_full_year_return"] = regime_metrics.replay_year_return(
        full_returns, REPLAY_YEAR
    )
    disclosure["trade_count_recent"] = trade_count_recent
    disclosure["trade_count_annualized_recent"] = (
        regime_metrics.annualized_trade_count(
            trade_count_recent, years=regime_metrics.window_years(recent)
        )
        if trade_count_recent is not None
        else None
    )
    disclosure["turnover_annualized_recent"] = turnover_annualized_recent

    return RegimeVerdict(
        experiment_id=experiment_id,
        family=family,
        config_hash=config_hash,
        holding_period=holding_period,
        is_ml=is_ml,
        reference_only=reference_only,
        dsr_trial_count=dsr_trial_count,
        metrics=metrics,
        disclosure=disclosure,
        gate_results=gate_results,
        gates_not_applicable=gates_not_applicable,
        all_gates_pass=all_gates_pass,
        gates_provenance=gates_provenance,
        gate_contract=gate_contract,
    )


#: Step 13 Track M/L (docs/plan-step-13-recent-high-return-ml-and-llm-tracks-
#: 2026-09-09.zh.md; config/promotion/recent-regime-high-return-gates-v2.json).
#: Independent of Group B's v1 contract/family above -- v2 does not
#: retroactively change F1-F5's verdicts, and this module's v1 machinery is
#: untouched by anything below.
GATE_CONTRACT_V2_PATH = ROOT / "config" / "promotion" / "recent-regime-high-return-gates-v2.json"
LEDGER_FAMILY_V2 = "step13_recent_high_return"

RECENT_HIGH_RETURN_GATE_KEYS: tuple[str, ...] = (
    "cagr_recent_net_minimum",
    "cagr_excess_vol_matched_spy_minimum",
    "hit_rate_weekly_minimum",
    "max_drawdown_recent_minimum",
    "sharpe_excess_bil_recent_minimum",
    "positive_quarter_fraction_minimum",
    "dsr_probability_minimum",
    "stress_cost_recent_cagr_minimum",
    "activity_floor_rebalances_with_change_per_year_minimum",
    "ml_placebo_rank_ic_abs_maximum",
    "ml_must_beat_rule_baseline_cagr_margin_minimum",
    "llm_marginal_lift_cagr_minimum",
    "llm_marginal_lift_rank_ic_minimum",
)


def load_recent_high_return_gates(path: Path | str = GATE_CONTRACT_V2_PATH) -> PreregisteredGates:
    """Load the Step 13 v2 contract (see module-level constants above)."""
    return load_preregistered_gates(path, required_keys=RECENT_HIGH_RETURN_GATE_KEYS)


@dataclass(frozen=True)
class RecentHighReturnVerdict(ResearchDataModel):
    """One Step 13 Track M/L candidate's v2-contract metrics, gate results,
    and disclosure-only figures. A separate dataclass from :class:`RegimeVerdict`
    (Step 12's v1) rather than a shared base: the two contracts' gate key
    sets, activity-floor semantics, and disclosure items are different
    enough (v2 has no profit_factor/daily-or-intraday-hit-rate gates at all,
    and adds activity_floor/ml_must_beat_rule_baseline/llm_marginal_lift)
    that sharing a base class would mean more conditional fields than a
    plain, independent dataclass costs.
    """

    experiment_id: str
    family: str
    config_hash: str
    track: Literal["M", "L"]
    is_ml: bool
    reference_only: bool
    dsr_trial_count: int
    metrics: dict[str, float | int | str | None]
    disclosure: dict[str, float | int | str | None]
    gate_results: dict[str, bool]
    gates_not_applicable: tuple[str, ...]
    all_gates_pass: bool
    gates_provenance: str
    gate_contract: dict[str, str]

    @property
    def evaluated_gate_count(self) -> int:
        return len(self.gate_results) - len(self.gates_not_applicable)

    @property
    def promotion_eligible(self) -> bool:
        if self.reference_only:
            return False
        return self.all_gates_pass and self.gates_provenance == "preregistered"


def evaluate_recent_high_return_candidate(
    *,
    experiment_id: str,
    config_hash: str,
    full_returns: pd.Series,
    full_stress_returns: pd.Series,
    spy_returns: pd.Series,
    bil_returns: pd.Series,
    weekly_holding_period_net_returns_recent: Sequence[float],
    rebalances_with_change_per_year: dict[int, int],
    family: str = LEDGER_FAMILY_V2,
    track: Literal["M", "L"] = "M",
    is_ml: bool = False,
    placebo_rank_ic_abs: float | None = None,
    rule_baseline_cagr_recent_net: float | None = None,
    reference_only: bool = False,
    gates: PreregisteredGates | None = None,
    dsr_hac_lag: int = DEFAULT_DSR_HAC_LAG,
) -> RecentHighReturnVerdict:
    """Score one Step 13 Track M/L candidate's recent-window
    (2024-01-02..latest) return stream against the preregistered v2
    contract, and compute the mandatory disclosure block.

    ``full_returns``/``full_stress_returns``/``spy_returns``/``bil_returns``
    are complete available-history daily streams -- this function slices
    the recent-gated and disclosure-only windows out of them itself, exactly
    like v1's :func:`evaluate_regime_candidate`, so every candidate is
    sliced identically.

    ``weekly_holding_period_net_returns_recent`` must already be restricted
    to weeks the candidate was actually invested (all-cash/BIL weeks
    excluded -- gate contract's own ``hit_rate_weekly`` note).
    ``rebalances_with_change_per_year`` is ``{calendar_year: count}`` for
    every year with at least one rebalance date in the recent window; the
    activity-floor gate uses the *minimum* year, not the average, so a
    candidate must clear the floor in every year it is scored over, not
    merely on average across them.

    ``rule_baseline_cagr_recent_net`` is required when ``is_ml=True`` (the
    best M0 rule cell's own ``cagr_recent_net``, chosen by the identical
    trailing-validation protocol) -- raises ``ValueError`` if missing, the
    same "declare, don't silently skip" discipline v1 uses for
    ``placebo_rank_ic_abs``.
    """
    resolved_gates = gates or load_recent_high_return_gates()
    thresholds = resolved_gates.values
    gates_provenance = "preregistered"
    gate_contract = resolved_gates.as_provenance()

    recent = _slice_from(full_returns, RECENT_WINDOW_START)
    if recent.empty:
        raise ValueError(f"{experiment_id}: no returns on/after {RECENT_WINDOW_START}")
    recent_stress = _slice_from(full_stress_returns, RECENT_WINDOW_START)
    if recent_stress.empty:
        raise ValueError(f"{experiment_id}: no stress returns on/after {RECENT_WINDOW_START}")
    recent_bil = bil_returns.reindex(recent.index)
    if recent_bil.isna().any():
        raise ValueError(f"{experiment_id}: BIL benchmark alignment produced missing rows")
    recent_spy = spy_returns.reindex(recent.index)
    if recent_spy.isna().any():
        raise ValueError(f"{experiment_id}: SPY benchmark alignment produced missing rows")

    cagr_recent_net = annualized_cagr(recent)
    max_drawdown_recent = max_drawdown(recent)
    excess_bil = (recent - recent_bil).to_numpy()
    sharpe_excess_bil_recent = annualized_sharpe(excess_bil)
    dsr_trial_count = dsr_trial_count_for_family(family, config_hash)
    dsr_probability = deflated_sharpe_probability(
        excess_bil, trial_count=dsr_trial_count, hac_lag=dsr_hac_lag
    )
    hit_rate_weekly = regime_metrics.hit_rate(weekly_holding_period_net_returns_recent)
    pqf = regime_metrics.positive_quarter_fraction(recent)
    stress_cagr_recent = annualized_cagr(recent_stress)

    # Vol-matched-SPY excess CAGR: same construction as
    # mechanism_eval.evaluate_candidate's benchmark_returns path (candidate
    # volatility-scaled blend of SPY + BIL), applied directly to the
    # recent-window slice rather than through that function's rolling-origin
    # Candidate/fold machinery, which this continuous-stream contract does
    # not use (see gate contract's walkforward.scheme).
    candidate_vol = float(recent.std())
    spy_vol = float(recent_spy.std())
    if not math.isfinite(spy_vol) or spy_vol <= 0.0:
        raise ValueError(f"{experiment_id}: SPY has non-positive realized volatility in this window")
    vol_match_weight = candidate_vol / spy_vol
    vol_matched_spy = vol_match_weight * recent_spy + (1.0 - vol_match_weight) * recent_bil
    cagr_excess_vol_matched_spy = cagr_recent_net - annualized_cagr(vol_matched_spy)

    if not rebalances_with_change_per_year:
        raise ValueError(f"{experiment_id}: rebalances_with_change_per_year must be non-empty")
    activity_floor_value = min(rebalances_with_change_per_year.values())

    gate_results: dict[str, bool] = {
        "cagr_recent_net": cagr_recent_net >= thresholds["cagr_recent_net_minimum"],
        "cagr_excess_vol_matched_spy": (
            cagr_excess_vol_matched_spy >= thresholds["cagr_excess_vol_matched_spy_minimum"]
        ),
        "hit_rate_weekly": hit_rate_weekly >= thresholds["hit_rate_weekly_minimum"],
        "max_drawdown_recent": max_drawdown_recent >= thresholds["max_drawdown_recent_minimum"],
        "sharpe_excess_bil_recent": (
            sharpe_excess_bil_recent >= thresholds["sharpe_excess_bil_recent_minimum"]
        ),
        "positive_quarter_fraction": pqf >= thresholds["positive_quarter_fraction_minimum"],
        "dsr_probability": dsr_probability >= thresholds["dsr_probability_minimum"],
        "stress_cost_still_high": (
            stress_cagr_recent >= thresholds["stress_cost_recent_cagr_minimum"]
        ),
        "activity_floor": (
            activity_floor_value
            >= thresholds["activity_floor_rebalances_with_change_per_year_minimum"]
        ),
    }

    gates_not_applicable: list[str] = []
    if is_ml:
        if placebo_rank_ic_abs is None:
            raise ValueError("is_ml=True requires placebo_rank_ic_abs")
        gate_results["ml_placebo_rank_ic"] = (
            abs(placebo_rank_ic_abs) < thresholds["ml_placebo_rank_ic_abs_maximum"]
        )
        if rule_baseline_cagr_recent_net is None:
            raise ValueError("is_ml=True requires rule_baseline_cagr_recent_net")
        gate_results["ml_must_beat_rule_baseline"] = (
            cagr_recent_net - rule_baseline_cagr_recent_net
            >= thresholds["ml_must_beat_rule_baseline_cagr_margin_minimum"]
        )
    else:
        gate_results["ml_placebo_rank_ic"] = True
        gate_results["ml_must_beat_rule_baseline"] = True
        gates_not_applicable += ["ml_placebo_rank_ic", "ml_must_beat_rule_baseline"]

    # Track L's llm_marginal_lift_* gates are evaluated by the L-track
    # executor's own script (it has the quant-only-twin comparison this
    # module has no data to compute) -- declared not-applicable here for
    # every Track M candidate and for any Track L candidate this function is
    # asked to score before that comparison exists, never silently omitted.
    gate_results["llm_marginal_lift"] = True
    gates_not_applicable.append("llm_marginal_lift")

    all_gates_pass = all(gate_results.values())

    metrics: dict[str, float | int | str | None] = {
        "cagr_recent_net": cagr_recent_net,
        "cagr_excess_vol_matched_spy": cagr_excess_vol_matched_spy,
        "vol_match_weight_vs_spy": vol_match_weight,
        "hit_rate_weekly": hit_rate_weekly,
        "max_drawdown_recent": max_drawdown_recent,
        "sharpe_excess_bil_recent": sharpe_excess_bil_recent,
        "positive_quarter_fraction": pqf,
        "dsr_probability": dsr_probability,
        "stress_cost_recent_cagr_net": stress_cagr_recent,
        "activity_floor_rebalances_with_change_per_year_min": activity_floor_value,
        "recent_window_start": recent.index.min().date().isoformat(),
        "recent_window_end": recent.index.max().date().isoformat(),
        "recent_window_row_count": int(len(recent)),
    }
    if is_ml:
        metrics["ml_placebo_rank_ic_abs"] = (
            abs(placebo_rank_ic_abs) if placebo_rank_ic_abs is not None else None
        )
        metrics["rule_baseline_cagr_recent_net"] = rule_baseline_cagr_recent_net
        metrics["ml_cagr_margin_over_rule_baseline"] = (
            cagr_recent_net - rule_baseline_cagr_recent_net
            if rule_baseline_cagr_recent_net is not None
            else None
        )

    disclosure = _disclosure_block(full_returns, None)
    disclosure["return_skewness_recent"] = regime_metrics.return_skewness(recent)
    disclosure["worst_single_week_return_recent"] = regime_metrics.worst_single_week_return(recent)
    disclosure["quarterly_returns_2024_2026"] = regime_metrics.quarterly_returns(recent)
    disclosure["replay_2022_full_year_return"] = regime_metrics.replay_year_return(
        full_returns, REPLAY_YEAR
    )
    disclosure["rebalances_with_change_per_year"] = dict(rebalances_with_change_per_year)

    return RecentHighReturnVerdict(
        experiment_id=experiment_id,
        family=family,
        config_hash=config_hash,
        track=track,
        is_ml=is_ml,
        reference_only=reference_only,
        dsr_trial_count=dsr_trial_count,
        metrics=metrics,
        disclosure=disclosure,
        gate_results=gate_results,
        gates_not_applicable=tuple(gates_not_applicable),
        all_gates_pass=all_gates_pass,
        gates_provenance=gates_provenance,
        gate_contract=gate_contract,
    )


def append_ledger(record: dict[str, object], *, ledger_path: Path = LEDGER_PATH) -> bool:
    """Append ``record`` unless its ``config_hash`` is already present for
    that family -- same "same config hash only recorded once" rule as
    ``loop._append_ledger``, reimplemented here for the same file-ownership
    reason as :func:`dsr_trial_count_for_family`.
    """
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    if ledger_path.exists():
        for line in ledger_path.read_text().splitlines():
            if not line.strip():
                continue
            existing = json.loads(line)
            if existing.get("config_hash") == record.get("config_hash") and existing.get(
                "family"
            ) == record.get("family"):
                return False
    with ledger_path.open("a") as handle:
        handle.write(json.dumps(record, default=str) + "\n")
    return True
