"""Work Item P2a: a real bounded parameter search on real SIP daily bars.

Mechanism: single-symbol time-series momentum, long QQQ when its lagged
trailing ``lookback``-session return exceeds ``signal_threshold``, else BIL
(cash-like). This is deliberately the simplest honest momentum/trend rule
available -- see plan section 6.2's table: effective alpha is sparse by
design, and the point of this run is to prove the search *pipeline*
(bounded grid -> bounded mutation -> layered discovery/QD/gate -> honest
verdict), not to manufacture a pass.

Search shape (plan sections 6.1/6.4/6.5):

* Generation 0: a bounded grid over ``{lookback, signal_threshold}``
  (``open_composer.research.kernel.parameter_search``), deliberately larger
  than the retained budget so the deterministic subsampling + drop-reporting
  path is actually exercised.
* Generation 0 candidates go through Layer 1 (development-only quality) and
  Layer 2 (QD archive keyed on mechanism family + 4 behavioural dimensions,
  ``open_composer.research.kernel.behavioral_descriptors``) to pick a small
  set of elites.
* Generation 1: each Generation 0 elite spawns
  ``MUTANTS_PER_ELITE`` bounded-mutation children
  (``bounded_parameter_mutation``), recorded with ``generation=1`` and
  ``parent_id`` set to the elite that produced them.
* The full Generation 0 + Generation 1 pool is run through
  ``open_composer.research.kernel.layered_search.run_layered_search`` once,
  end to end, which re-derives Layer 1/2 on the combined pool, clusters the
  Layer 2 elites' OOS streams into an effective N (P1a), and -- only if that
  effective N is within budget -- scores every elite against the full
  paper-tier gate battery.

Per plan section 6.5, everything here runs daily-only, in one long-lived
process, against a small fixed symbol universe (QQQ/BIL/TQQQ) -- daily bars
for the whole market history are ~500MB, nothing like the ~1GB-per-10-symbols
-per-quarter minute-bar cost that this run must not incur.

Headline result: nested (anchored) walk-forward, not the global split
----------------------------------------------------------------------
The Generation 0/1 -> ``run_layered_search`` pipeline above selects **one**
parameter vector globally: every candidate is ranked once on a single
development partition and the winner(s) are then scored on a single stitched
out-of-sample stream. That is methodologically weaker than re-selecting the
parameter vector inside every walk-forward fold (see
``open_composer.research.kernel.nested_walk_forward`` module docstring for
the full argument): the global split never lets selection see recent data,
and it validates a frozen parameter vector nobody would actually deploy
unchanged for five years, rather than the periodically-re-optimising
*procedure* that is the honest object of study.

This script therefore also runs ``run_nested_walk_forward`` over the exact
same Generation 0 grid, and that nested result -- not the global-split
result above -- is the headline: it is printed first and is the primary
promotion signal. The Generation 0/1/``run_layered_search`` path is kept
running (it is inexpensive once the price data is loaded, and the QD-archive
budgeting/breadth-ratio accounting it exercises is still useful evidence
about the search pipeline) but is reported under ``global_split_reference``
in the output JSON, clearly demoted to a secondary/comparison figure -- not
because it is expected to become the deciding number, but because keeping it
gives an honest before/after comparison of the two selection procedures on
identical data.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.research.kernel.gate_contract import load_preregistered_gates
from open_composer.research.kernel.layered_search import (
    assert_causal_transform as _assert_causal_transform,
)
from open_composer.research.kernel.layered_search import (
    build_layer2_archive,
    development_view,
    run_layered_search,
    select_layer1_survivors,
)
from open_composer.research.kernel.mechanism_eval import Candidate, Mechanism, expand_mechanism
from open_composer.research.kernel.nested_walk_forward import (
    NestedWalkForwardResult,
    run_nested_walk_forward,
)
from open_composer.research.kernel.parameter_search import (
    ParameterSpace,
    ParameterSpec,
    bounded_grid,
)
from open_composer.research.kernel.parameter_search import (
    bounded_parameter_mutation as _bounded_parameter_mutation,
)
from open_composer.research.kernel.rolling_origin import returns_from_ohlcv
from open_composer.storage import write_json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "reports" / "research" / "search" / "daily-momentum-p2a-search.json"

MECHANISM_FAMILY = "TS_MOM"
SIGNAL_SYMBOLS = ("QQQ", "BIL")
BENCHMARK_SYMBOLS = ("QQQ", "TQQQ", "BIL")
PRIMARY_COST_BPS = 20.0
STRESS_COST_BPS = 40.0
FOLD_COUNT = 5

#: Generation 0's bounded grid. 13 lookbacks * 6 thresholds = 78 raw points --
#: deliberately larger than GRID_MAX_POINTS so bounded_grid's deterministic
#: subsampling (and honest drop-reporting) is exercised on a real run, not
#: just in a unit test.
PARAMETER_SPACE = ParameterSpace(
    specs=(
        ParameterSpec(name="lookback", kind="int", low=10, high=250, step=20),
        ParameterSpec(name="signal_threshold", kind="float", low=0.0, high=0.05, step=0.01),
    )
)
GRID_MAX_POINTS = 40
GRID_SEED = 20260901

MUTANTS_PER_ELITE = 5
MUTATION_RATE = 0.5
#: Thresholds must predate the result, so they come from a git-committed
#: contract rather than from a dict this script could edit afterwards.
GATE_CONTRACT_PATH = "config/promotion/kernel-paper-tier-gates.json"
CAMPAIGN_ID = "p2a-daily-momentum-2026-09-01"


def _momentum_feature(prices: pd.Series, *, lookback: int) -> pd.Series:
    """Trailing ``lookback``-session return, PIT-lagged by one session.

    ``prices.pct_change(lookback)`` at date t reads only ``prices[t-lookback:t]``
    (causal by construction); the extra ``.shift(1)`` is this project's PIT
    safety-buffer convention (see ``scripts/evaluate_vol02_recalibrated.py``),
    so the value used to *decide* at session T was fully known at T-1's
    close. Verified by :func:`_verify_feature_is_causal` below via
    ``kernel.layered_search.assert_causal_transform``.
    """
    return prices.pct_change(lookback).shift(1)


def simulate_momentum(
    closes: dict[str, pd.Series],
    opens: dict[str, pd.Series],
    params: Mapping[str, Any],
) -> pd.Series:
    """Long QQQ when its lagged trailing return clears ``signal_threshold``, else BIL.

    Same execution convention as ``scripts/evaluate_ma_crossover_mini_search.py``:
    decision confirmed at session T's close, executed at session T+1's open
    (cost charged only when the sleeve actually switches).
    """
    lookback = int(params["lookback"])
    threshold = float(params["signal_threshold"])
    cost_bps = float(params["cost_bps"])

    index = closes["QQQ"].index.intersection(closes["BIL"].index).sort_values()
    qqq_close = closes["QQQ"].reindex(index)
    trailing_return = _momentum_feature(qqq_close, lookback=lookback)
    bullish = trailing_return > threshold

    sleeve_closes = {symbol: closes[symbol].reindex(index) for symbol in SIGNAL_SYMBOLS}
    sleeve_opens = {symbol: opens[symbol].reindex(index) for symbol in SIGNAL_SYMBOLS}

    dates = list(index)
    first_valid = bullish.first_valid_index()
    if first_valid is None:
        raise ValueError("momentum signal has no valid observations")
    start = dates.index(first_valid) + 1

    current_sleeve = "BIL"
    returns: list[float] = []
    return_dates: list[pd.Timestamp] = []
    for i in range(start, len(dates) - 1):
        decision, execution = dates[i], dates[i + 1]
        target_sleeve = "QQQ" if bool(bullish.loc[decision]) else "BIL"
        if target_sleeve != current_sleeve:
            day_return = float(
                sleeve_closes[target_sleeve].loc[execution]
                / sleeve_opens[target_sleeve].loc[execution]
                - 1.0
            )
            day_return -= (cost_bps / 10_000.0) * 2.0
            current_sleeve = target_sleeve
        else:
            day_return = float(
                sleeve_closes[current_sleeve].loc[execution]
                / sleeve_closes[current_sleeve].loc[decision]
                - 1.0
            )
        returns.append(day_return)
        return_dates.append(execution)

    series = pd.Series(returns, index=pd.DatetimeIndex(return_dates), name=MECHANISM_FAMILY)
    if series.isna().any():
        raise ValueError("momentum reconstructed return series contains non-finite values")
    return series


def _verify_feature_is_causal(qqq_close: pd.Series) -> None:
    """Plan section 6.3: prove the feature this run trades on is non-anticipating.

    Checked once, against the real QQQ close series, at a representative
    mid-grid lookback -- the transform's shape (a lagged trailing-return) does
    not vary in a way that could become causal at one lookback and
    anticipating at another, so one check covers the whole grid.
    """
    _assert_causal_transform(lambda series: _momentum_feature(series, lookback=50), qqq_close)


def _mutation_seed(elite_id: str, mutant_index: int) -> int:
    """Deterministic per-(elite, mutant) seed, independent of PYTHONHASHSEED."""
    digest = hashlib.sha256(f"{CAMPAIGN_ID}:{elite_id}:{mutant_index}".encode()).hexdigest()
    return int(digest[:8], 16)


def _renamed(candidate: Candidate, *, candidate_id: str) -> Candidate:
    return dataclasses.replace(candidate, candidate_id=candidate_id)


def _load_price_bundles() -> tuple[
    dict[str, pd.Series], dict[str, pd.Series], dict[str, pd.Series]
]:
    frame = load_sip_bars(BENCHMARK_SYMBOLS, frequency="daily")
    closes: dict[str, pd.Series] = {}
    opens: dict[str, pd.Series] = {}
    benchmark_returns: dict[str, pd.Series] = {}
    for symbol in BENCHMARK_SYMBOLS:
        rows = frame.loc[frame["symbol"] == symbol].sort_values("timestamp")
        index = pd.DatetimeIndex(rows["timestamp"])
        closes[symbol] = pd.Series(
            pd.to_numeric(rows["close"], errors="raise").to_numpy(), index=index, name=symbol
        )
        opens[symbol] = pd.Series(
            pd.to_numeric(rows["open"], errors="raise").to_numpy(), index=index, name=symbol
        )
        benchmark_returns[symbol] = returns_from_ohlcv(rows)
    return closes, opens, benchmark_returns


def main() -> None:
    closes, opens, benchmark_returns = _load_price_bundles()
    _verify_feature_is_causal(closes["QQQ"])

    # --- Generation 0: bounded grid -----------------------------------------
    grid_result = bounded_grid(PARAMETER_SPACE, max_points=GRID_MAX_POINTS, seed=GRID_SEED)

    # --- HEADLINE: nested (anchored) walk-forward over the Generation 0 grid.
    # See module docstring and open_composer.research.kernel.
    # nested_walk_forward's module docstring: this re-selects the parameter
    # vector inside every rolling_origin_folds fold using only that fold's
    # training window, and evaluates the winner only on that fold's own
    # (never-before-read-during-selection) test window. This is what is
    # actually deployed -- a periodically re-optimising procedure -- not a
    # single parameter vector frozen on stale data, so this result, not the
    # Generation 0/1 global-split result below, is the primary promotion
    # signal from this script.
    nested_param_space = [{**point, "cost_bps": PRIMARY_COST_BPS} for point in grid_result.points]
    nested_result: NestedWalkForwardResult = run_nested_walk_forward(
        nested_param_space,
        mechanism_family=MECHANISM_FAMILY,
        signal_fn=lambda params: simulate_momentum(closes, opens, params),
        stress_signal_fn=lambda params: simulate_momentum(
            closes, opens, {**params, "cost_bps": STRESS_COST_BPS}
        ),
        benchmark_returns=benchmark_returns["QQQ"],
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=benchmark_returns["TQQQ"],
        bil_returns=benchmark_returns["BIL"],
        campaign_id=f"{CAMPAIGN_ID}-nested",
        gates=load_preregistered_gates(GATE_CONTRACT_PATH),
        fold_count=FOLD_COUNT,
        annualization_sessions=252,
    )

    # --- Reference only: the Generation 0/1 global-split pipeline below is
    # kept running for comparison (see module docstring) but is no longer
    # the script's headline result.
    gen0_mechanism = Mechanism(
        family=MECHANISM_FAMILY,
        signal_fn=lambda params: simulate_momentum(closes, opens, params),
        stress_signal_fn=lambda params: simulate_momentum(
            closes, opens, {**params, "cost_bps": STRESS_COST_BPS}
        ),
        param_space=[{**point, "cost_bps": PRIMARY_COST_BPS} for point in grid_result.points],
    )
    gen0_candidates_raw = expand_mechanism(gen0_mechanism, fold_count=FOLD_COUNT, generation=0)
    gen0_candidates = [
        _renamed(candidate, candidate_id=f"gen0-{candidate.candidate_id}")
        for candidate in gen0_candidates_raw
    ]

    # Layer 1 + Layer 2 on generation 0 alone, purely to pick mutation
    # parents -- development-only, same functions the final combined run uses.
    gen0_views = [
        development_view(candidate, benchmark_returns["QQQ"]) for candidate in gen0_candidates
    ]
    gen0_qualities, gen0_survivors = select_layer1_survivors(gen0_views)
    gen0_archive = build_layer2_archive(
        gen0_survivors, gen0_qualities, campaign_id=f"{CAMPAIGN_ID}-gen0"
    )
    gen0_by_id = {candidate.candidate_id: candidate for candidate in gen0_candidates}

    # --- Generation 1: bounded mutation of generation 0 elites --------------
    gen1_candidates: list[Candidate] = []
    for elite in gen0_archive.elites:
        elite_id = elite.candidate.candidate_id
        parent_candidate = gen0_by_id[elite_id]
        parent_params = {
            "lookback": parent_candidate.param_vector["lookback"],
            "signal_threshold": parent_candidate.param_vector["signal_threshold"],
        }
        mutants = [
            _bounded_parameter_mutation(
                parent_params,
                PARAMETER_SPACE,
                seed=_mutation_seed(elite_id, index),
                mutation_rate=MUTATION_RATE,
            )
            for index in range(MUTANTS_PER_ELITE)
        ]
        mutant_mechanism = Mechanism(
            family=MECHANISM_FAMILY,
            signal_fn=lambda params: simulate_momentum(closes, opens, params),
            stress_signal_fn=lambda params: simulate_momentum(
                closes, opens, {**params, "cost_bps": STRESS_COST_BPS}
            ),
            param_space=[{**mutant, "cost_bps": PRIMARY_COST_BPS} for mutant in mutants],
        )
        batch = expand_mechanism(
            mutant_mechanism, fold_count=FOLD_COUNT, generation=1, parent_id=elite_id
        )
        gen1_candidates.extend(
            _renamed(candidate, candidate_id=f"gen1-{elite_id}-{candidate.candidate_id}")
            for candidate in batch
        )

    all_candidates = gen0_candidates + gen1_candidates
    ids = [candidate.candidate_id for candidate in all_candidates]
    assert len(set(ids)) == len(ids), "candidate id collision across generations"

    # --- Full Layer 1 -> Layer 2 -> Layer 3 run on the combined pool --------
    verdict = run_layered_search(
        all_candidates,
        benchmark_returns=benchmark_returns["QQQ"],
        campaign_id=CAMPAIGN_ID,
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=benchmark_returns["TQQQ"],
        bil_returns=benchmark_returns["BIL"],
        annualization_sessions=252,
    )

    candidates_by_id = {candidate.candidate_id: candidate for candidate in all_candidates}
    family_verdict = verdict.family_verdict
    candidate_verdicts = family_verdict.candidates if family_verdict is not None else []
    gate_names = sorted({name for cv in candidate_verdicts for name in cv.gate_results})
    per_gate_pass_count = {
        name: sum(1 for cv in candidate_verdicts if cv.gate_results[name]) for name in gate_names
    }

    report: dict[str, Any] = {
        "mechanism_family": MECHANISM_FAMILY,
        "campaign_id": CAMPAIGN_ID,
        "fold_count": FOLD_COUNT,
        "primary_cost_bps": PRIMARY_COST_BPS,
        "stress_cost_bps": STRESS_COST_BPS,
        "parameter_space": {
            "lookback": {"kind": "int", "low": 10, "high": 250, "step": 20},
            "signal_threshold": {"kind": "float", "low": 0.0, "high": 0.05, "step": 0.01},
        },
        "generation0_grid": {
            "full_grid_size": grid_result.full_grid_size,
            "requested_max_points": grid_result.requested_max_points,
            "returned_point_count": grid_result.returned_point_count,
            "dropped_point_count": grid_result.dropped_point_count,
            "subsampled": grid_result.subsampled,
            "seed": grid_result.seed,
        },
        # --- Headline: nested (anchored) walk-forward. See module docstring.
        "nested_walk_forward": {
            "campaign_id": f"{CAMPAIGN_ID}-nested",
            "candidate_count": len(nested_param_space),
            "fold_count": nested_result.fold_count,
            "embargo_bars": nested_result.embargo_bars,
            "folds": [
                {
                    "fold": fold.fold,
                    "train_start": fold.train_start,
                    "train_end": fold.train_end,
                    "test_start": fold.test_start,
                    "test_end": fold.test_end,
                    "candidates_scored": fold.candidates_scored,
                    "selected_candidate_id": fold.selected_candidate_id,
                    "selected_param_vector": fold.selected_param_vector,
                    "selected_training_score": fold.selected_training_score,
                    "test_row_count": len(fold.test_returns),
                }
                for fold in nested_result.folds
            ],
            "parameter_stability": nested_result.parameter_stability.model_dump(),
            "procedure_oos_row_count": len(nested_result.procedure_candidate.oos_return_stream),
            "procedure_metrics": nested_result.procedure_verdict.metrics,
            "procedure_dsr_probability": nested_result.procedure_verdict.dsr_probability,
            "procedure_sharpe_excess_bil": nested_result.procedure_verdict.sharpe_excess_bil,
            "procedure_positive_fold_fraction": (
                nested_result.procedure_verdict.positive_fold_fraction
            ),
            "procedure_orthogonal_to_qqq": nested_result.procedure_verdict.orthogonal_to_qqq,
            "procedure_gate_results": nested_result.procedure_verdict.gate_results,
            "procedure_all_gates_pass": nested_result.procedure_verdict.all_gates_pass,
            # Passing every gate is necessary and not sufficient: eligibility
            # also requires the bar to have been committed in advance.
            "procedure_promotion_eligible": nested_result.procedure_verdict.promotion_eligible,
            "gates_provenance": nested_result.procedure_verdict.gates_provenance,
            "gate_contract": nested_result.procedure_verdict.gate_contract,
        },
        # --- Reference only (see module docstring): the Generation 0/1
        # global-split pipeline, kept for before/after comparison on
        # identical data. This is no longer the script's headline result.
        "global_split_reference": {
            "generation0_candidate_count": len(gen0_candidates),
            "generation0_layer1_survivor_count": len(gen0_survivors),
            "generation0_layer2_elite_count": gen0_archive.elite_count,
            "generation1_mutants_per_elite": MUTANTS_PER_ELITE,
            "generation1_mutation_rate": MUTATION_RATE,
            "generation1_candidate_count": len(gen1_candidates),
            "raw_candidate_count": verdict.raw_candidate_count,
            "layer1_survivor_count": verdict.layer1_survivor_count,
            "layer2_elite_count": verdict.layer2_elite_count,
            "max_effective_n": verdict.max_effective_n,
            "effective_n_gate_passed": verdict.effective_n_gate_passed,
            # Charged to the DSR: the whole search, not the surviving elites.
            "search_effective_n": verdict.search_effective_n,
            "dsr_trial_count": verdict.dsr_trial_count,
            "effective_n": family_verdict.effective_n if family_verdict is not None else None,
            # Two different denominators, both meaningful, and reporting only
            # one of them is how a search quietly overstates its honesty. The
            # gate-level ratio says how distinct the elites we actually gated
            # were; the discovery-level ratio says what the whole search cost
            # in backtests per independent trial. ``breadth_ratio`` keeps
            # P1a's gate-level meaning.
            "breadth_ratio": family_verdict.breadth_ratio if family_verdict is not None else None,
            "breadth_ratio_denominator": (
                family_verdict.raw_candidate_count if family_verdict is not None else None
            ),
            "breadth_ratio_vs_discovery": (
                family_verdict.effective_n / verdict.raw_candidate_count
                if family_verdict is not None and verdict.raw_candidate_count
                else None
            ),
            "qd_archive_cell_occupancy": [
                {
                    "cell_id": elite.cell_id,
                    "cell_descriptors": elite.cell_descriptors,
                    "candidate_id": elite.candidate.candidate_id,
                    "param_vector": candidates_by_id[elite.candidate.candidate_id].param_vector,
                    "generation": candidates_by_id[elite.candidate.candidate_id].generation,
                    "parent_id": candidates_by_id[elite.candidate.candidate_id].parent_id,
                    "quality": elite.candidate.quality,
                }
                for elite in verdict.qd_archive.elites
            ],
            "per_candidate_gate_results": [
                {
                    "candidate_id": cv.candidate.candidate_id,
                    "param_vector": cv.candidate.param_vector,
                    "generation": cv.candidate.generation,
                    "parent_id": cv.candidate.parent_id,
                    "dsr_probability": cv.dsr_probability,
                    "sharpe_excess_bil": cv.sharpe_excess_bil,
                    "positive_fold_fraction": cv.positive_fold_fraction,
                    "qqq_correlation": cv.metrics["qqq_correlation"],
                    "cagr_excess_qqq": cv.metrics["cagr_excess_qqq"],
                    "max_drawdown": cv.metrics["max_drawdown"],
                    "mar": cv.metrics["mar"],
                    "gate_results": cv.gate_results,
                    "all_gates_pass": cv.all_gates_pass,
                }
                for cv in candidate_verdicts
            ],
            "per_gate_pass_count": per_gate_pass_count,
            "candidates_passing_all_gates": sum(
                1 for cv in candidate_verdicts if cv.all_gates_pass
            ),
            "candidates_evaluated_at_gate": len(candidate_verdicts),
        },
    }
    write_json(OUTPUT_PATH, report)

    nested_report = report["nested_walk_forward"]
    print("=== HEADLINE: nested (anchored) walk-forward procedure ===")
    print(
        f"fold_count={nested_report['fold_count']}  "
        f"embargo_bars={nested_report['embargo_bars']}  "
        f"candidate_count={nested_report['candidate_count']}"
    )
    for fold in nested_report["folds"]:
        print(
            f"  fold {fold['fold']}: test=[{fold['test_start']}..{fold['test_end']}] "
            f"selected={fold['selected_param_vector']} "
            f"training_score={fold['selected_training_score']:.4f} "
            f"candidates_scored={fold['candidates_scored']} "
            f"test_rows={fold['test_row_count']}"
        )
    stability = nested_report["parameter_stability"]
    print(
        f"parameter_stability: {stability['distinct_selected_vector_count']} distinct "
        f"selected vector(s) across {stability['fold_count']} fold(s)"
    )
    for churn in stability["per_parameter_churn"]:
        print(
            f"  churn[{churn['parameter_name']}]: {churn['change_count']}/"
            f"{churn['total_transitions']} fold-to-fold transitions changed "
            f"(rate={churn['churn_rate']:.2f})"
        )
    print(f"procedure_oos_row_count={nested_report['procedure_oos_row_count']}")
    print(f"procedure_dsr_probability={nested_report['procedure_dsr_probability']:.4f}")
    print(f"procedure_sharpe_excess_bil={nested_report['procedure_sharpe_excess_bil']:.4f}")
    print(
        f"procedure_positive_fold_fraction={nested_report['procedure_positive_fold_fraction']:.4f}"
    )
    print(f"procedure_gate_results={nested_report['procedure_gate_results']}")
    print(f"procedure_all_gates_pass={nested_report['procedure_all_gates_pass']}")

    print("\n=== Reference only: Generation 0/1 global-split + run_layered_search ===")
    ref = report["global_split_reference"]
    print(f"raw_candidate_count={ref['raw_candidate_count']}")
    print(f"layer1_survivor_count={ref['layer1_survivor_count']}")
    print(f"layer2_elite_count={ref['layer2_elite_count']}")
    print(f"effective_n={ref['effective_n']}")
    print(
        f"breadth_ratio={ref['breadth_ratio']} "
        f"(= effective_n / {ref['breadth_ratio_denominator']} gated elites)"
    )
    print(
        f"breadth_ratio_vs_discovery={ref['breadth_ratio_vs_discovery']} "
        f"(= effective_n / {ref['raw_candidate_count']} candidates searched)"
    )
    print(f"effective_n_gate_passed={ref['effective_n_gate_passed']}")
    print(
        f"candidates_passing_all_gates={ref['candidates_passing_all_gates']}"
        f"/{ref['candidates_evaluated_at_gate']}"
    )
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
