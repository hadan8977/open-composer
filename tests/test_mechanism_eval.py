"""P1b: mechanism -> candidate -> gate evaluation harness.

Acceptance criteria from
``docs/plan-sip-migration-and-wide-search-2026-09-01.zh.md`` section 5.4:
candidate identity/lineage fields, a one-point parameter space and a
multi-point search sharing one code path, and the VOL02 numerical regression.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.adapters.data.sip_parquet import default_sip_root
from open_composer.research.campaign import recompute_candidate_promotion_metrics
from open_composer.research.campaign_statistics import (
    annualized_sharpe,
    deflated_sharpe_probability,
)
from open_composer.research.kernel.mechanism_eval import (
    Candidate,
    Mechanism,
    evaluate_family,
    expand_mechanism,
)
from open_composer.research.kernel.rolling_origin import rolling_origin_folds

SIP_DAILY_ROOT = default_sip_root() / "daily"


def _years_index(years: list[int]) -> pd.DatetimeIndex:
    parts = [pd.bdate_range(f"{year}-01-01", f"{year}-12-31", tz="UTC") for year in years]
    return pd.DatetimeIndex(np.concatenate([part.values for part in parts])).sort_values()


def _random_returns(
    years: list[int], *, seed: int, drift: float = 0.0003, vol: float = 0.01
) -> pd.Series:
    index = _years_index(years)
    values = np.random.default_rng(seed).normal(drift, vol, len(index))
    return pd.Series(values, index=index)


# ---------------------------------------------------------------------------
# Candidate identity / lineage
# ---------------------------------------------------------------------------


def test_expand_mechanism_assigns_identity_and_lineage_fields() -> None:
    param_space = [{"a": 1}, {"a": 2}, {"a": 3}]
    mechanism = Mechanism(
        family="synthetic_fam",
        signal_fn=lambda params: _random_returns([2020, 2021, 2022], seed=params["a"]),
        param_space=param_space,
    )
    candidates = expand_mechanism(mechanism, fold_count=2, generation=3, parent_id="parent-xyz")

    assert [candidate.candidate_id for candidate in candidates] == [
        "synthetic_fam-000",
        "synthetic_fam-001",
        "synthetic_fam-002",
    ]
    for candidate, params in zip(candidates, param_space, strict=True):
        assert isinstance(candidate, Candidate)
        assert candidate.mechanism_family == "synthetic_fam"
        assert candidate.param_vector == params
        assert candidate.generation == 3
        assert candidate.parent_id == "parent-xyz"
        assert len(candidate.oos_return_stream) > 0
        assert len(candidate.oos_dates) == len(candidate.oos_return_stream)
        assert len(candidate.development_fold_returns) == 2
        assert len(candidate.stress_return_stream) == len(candidate.oos_return_stream)


def test_expand_mechanism_defaults_generation_zero_and_no_parent() -> None:
    mechanism = Mechanism(
        family="fam",
        signal_fn=lambda params: _random_returns([2020, 2021, 2022], seed=1),
        param_space=[{"a": 1}],
    )
    (candidate,) = expand_mechanism(mechanism, fold_count=2)
    assert candidate.generation == 0
    assert candidate.parent_id is None


def test_mechanism_rejects_empty_param_space() -> None:
    with pytest.raises(ValueError, match="param_space"):
        Mechanism(family="fam", signal_fn=lambda params: pd.Series(dtype=float), param_space=[])


def test_mechanism_rejects_blank_family() -> None:
    with pytest.raises(ValueError, match="family"):
        Mechanism(family="   ", signal_fn=lambda params: pd.Series(dtype=float), param_space=[{}])


# ---------------------------------------------------------------------------
# One-point and multi-point parameter spaces share one code path
# ---------------------------------------------------------------------------


def _benchmark_bundle(years: list[int]) -> dict[str, pd.Series]:
    return {
        "qqq": _random_returns(years, seed=101, drift=0.0004, vol=0.012),
        "tqqq": _random_returns(years, seed=102, drift=0.0006, vol=0.03),
        "bil": _random_returns(years, seed=103, drift=0.00005, vol=0.0005),
    }


def _evaluate(param_space: list[dict[str, int]], years: list[int]):
    mechanism = Mechanism(
        family="fam",
        signal_fn=lambda params: _random_returns(years, seed=params["seed"]),
        param_space=param_space,
    )
    candidates = expand_mechanism(mechanism, fold_count=2)
    benchmarks = _benchmark_bundle(years)
    # Deliberately loose gates/DSR settings: this test is about code-path
    # uniformity (does a 1-point and an N-point space both come out the far
    # side of the SAME function with a well-formed verdict?), not about
    # whether any particular candidate happens to pass promotion.
    return evaluate_family(
        candidates,
        qqq_returns=benchmarks["qqq"],
        tqqq_returns=benchmarks["tqqq"],
        bil_returns=benchmarks["bil"],
        dsr_trial_count=2,
        dsr_hac_lag=3,
        min_dsr_stream_rows=1,
    )


def test_one_point_param_space_is_the_degenerate_case_of_a_search() -> None:
    years = [2020, 2021, 2022]
    single = _evaluate([{"seed": 7}], years)
    multi = _evaluate([{"seed": 7}, {"seed": 8}, {"seed": 9}], years)

    # Same function (_evaluate -> evaluate_family), same fields populated,
    # regardless of param_space length.
    assert single.raw_candidate_count == 1
    assert single.effective_n == 1
    assert single.breadth_ratio == pytest.approx(1.0)
    assert len(single.candidates) == 1

    assert multi.raw_candidate_count == 3
    assert 1 <= multi.effective_n <= 3
    assert multi.breadth_ratio == pytest.approx(multi.effective_n / 3)
    assert len(multi.candidates) == 3

    for verdict in [*single.candidates, *multi.candidates]:
        assert isinstance(verdict.all_gates_pass, bool)
        assert set(verdict.gate_results) == {
            "cagr_excess_qqq",
            "sharpe_excess_bil",
            "dsr_probability",
            "max_drawdown",
            "mar",
            "positive_fold_fraction",
            "qqq_capture_ratio",
            "qqq_downside_capture",
        }


def test_identical_candidates_collapse_to_one_effective_trial() -> None:
    years = [2020, 2021, 2022]
    # Two distinct parameter vectors that happen to bind to the same signal
    # (a MA50-vs-MA51-style situation): the harness must not treat this as
    # two independent trials just because the raw candidate count is two.
    mechanism = Mechanism(
        family="fam",
        signal_fn=lambda params: _random_returns(years, seed=99),
        param_space=[{"variant": "a"}, {"variant": "b"}],
    )
    candidates = expand_mechanism(mechanism, fold_count=2)
    benchmarks = _benchmark_bundle(years)
    family = evaluate_family(
        candidates,
        qqq_returns=benchmarks["qqq"],
        tqqq_returns=benchmarks["tqqq"],
        bil_returns=benchmarks["bil"],
        dsr_trial_count=2,
        dsr_hac_lag=3,
        min_dsr_stream_rows=1,
    )
    assert family.raw_candidate_count == 2
    assert family.effective_n == 1
    assert family.breadth_ratio == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# VOL02 numerical regression
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not SIP_DAILY_ROOT.is_dir(),
    reason="local SIP daily archive (data/sip/daily) is not present",
)
def test_vol02_harness_matches_manual_primitive_pipeline() -> None:
    """P1b acceptance criterion 1: extraction into the harness must not change
    VOL02's numbers relative to calling the same underlying primitives directly.

    There is no pre-existing committed ``vol02-recalibrated-evaluation.json``
    to diff against on SIP data: the only file at that historical filename was
    computed against the now-retired IEX cache (``data/cache/``), which this
    repo's SIP migration decision deprecates outright (see
    ``scripts/evaluate_vol02_recalibrated.py``'s module docstring) and which
    this task is explicitly barred from reading. So the regression this test
    proves is the one the plan actually cares about: the harness-based call
    sequence (``expand_mechanism`` + ``evaluate_family``) must reproduce, bit
    for bit, a hand-written call sequence against the same primitives
    (``rolling_origin_folds``, ``recompute_candidate_promotion_metrics``,
    ``annualized_sharpe``, ``deflated_sharpe_probability``) -- i.e. the
    refactor changed *where the code lives*, not *what it computes*.
    """
    from scripts.evaluate_vol02_recalibrated import (
        DSR_HAC_LAG,
        DSR_TRIAL_COUNT,
        FOLD_COUNT,
        PRIMARY_COST_BPS,
        SIGNAL_PARAMETERS,
        STRESS_COST_BPS,
        _load_price_bundles,
        simulate_vol02,
    )

    closes, opens, benchmark_returns = _load_price_bundles()
    params = {**SIGNAL_PARAMETERS, "cost_bps": PRIMARY_COST_BPS}

    mechanism = Mechanism(
        family="VOL02",
        signal_fn=lambda p: simulate_vol02(closes, opens, p),
        stress_signal_fn=lambda p: simulate_vol02(
            closes, opens, {**p, "cost_bps": STRESS_COST_BPS}
        ),
        param_space=[params],
    )
    (candidate,) = expand_mechanism(mechanism, fold_count=FOLD_COUNT)
    family = evaluate_family(
        [candidate],
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=benchmark_returns["TQQQ"],
        bil_returns=benchmark_returns["BIL"],
        annualization_sessions=SIGNAL_PARAMETERS["annualization_sessions"],
        dsr_trial_count=DSR_TRIAL_COUNT,
        dsr_hac_lag=DSR_HAC_LAG,
    )
    (harness_verdict,) = family.candidates

    # Manual, unrefactored primitive call sequence -- what the pre-extraction
    # script did inline in its main().
    raw_returns = simulate_vol02(closes, opens, params)
    stress_raw = simulate_vol02(closes, opens, {**params, "cost_bps": STRESS_COST_BPS})
    folds, stitched = rolling_origin_folds(raw_returns, fold_count=FOLD_COUNT)
    stitched_stress = stress_raw.reindex(stitched.index)
    fold_returns = [
        stitched.loc[
            pd.Timestamp(fold.train.test_start) : pd.Timestamp(fold.train.test_end)
        ].tolist()
        for fold in folds
    ]
    aligned_qqq = benchmark_returns["QQQ"].reindex(stitched.index)
    aligned_tqqq = benchmark_returns["TQQQ"].reindex(stitched.index)
    aligned_bil = benchmark_returns["BIL"].reindex(stitched.index)
    assert not stitched_stress.isna().any()
    assert not aligned_qqq.isna().any()

    manual_metrics = recompute_candidate_promotion_metrics(
        candidate_returns=stitched.tolist(),
        qqq_returns=aligned_qqq.tolist(),
        tqqq_returns=aligned_tqqq.tolist(),
        stress_returns=stitched_stress.tolist(),
        development_fold_returns=fold_returns,
        annualization_sessions=SIGNAL_PARAMETERS["annualization_sessions"],
    )
    excess_bil = (stitched - aligned_bil).to_numpy()
    manual_sharpe = annualized_sharpe(excess_bil)
    manual_dsr = deflated_sharpe_probability(
        excess_bil, trial_count=DSR_TRIAL_COUNT, hac_lag=DSR_HAC_LAG
    )

    assert harness_verdict.candidate.oos_return_stream == pytest.approx(
        stitched.tolist(), rel=1e-15, abs=1e-15
    )
    assert set(harness_verdict.metrics) == set(manual_metrics)
    for key, value in manual_metrics.items():
        assert harness_verdict.metrics[key] == pytest.approx(value, rel=1e-12, abs=1e-12)
    assert harness_verdict.sharpe_excess_bil == pytest.approx(manual_sharpe, rel=1e-12)
    assert harness_verdict.dsr_probability == pytest.approx(manual_dsr, rel=1e-12)
    assert harness_verdict.positive_fold_fraction == pytest.approx(
        manual_metrics["positive_fold_count"] / len(fold_returns)
    )
