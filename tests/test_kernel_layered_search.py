"""P2a: the three-layer discovery -> QD archive -> gate loop (plan section 6.4)
and the anti-lookahead causal-invariance check (plan section 6.3).

The central correctness rule under test: Layer 1 (discovery) and Layer 2 (QD
archive) must never see ``Candidate.oos_return_stream`` -- only Layer 3 (the
gate) may. These tests prove that three independent ways:

1. :class:`DevelopmentView` -- the only type Layer 1/2 code operates on --
   has no ``oos_return_stream``/``stress_return_stream`` field at all
   (structural, not conventional).
2. A "tripwire" candidate whose ``oos_return_stream``/``stress_return_stream``
   raise on access is run through the full Layer 1/2 path; no exception
   means those fields were never read.
3. Two candidates identical in ``development_returns`` but with wildly
   different (poisoned) ``oos_return_stream`` content produce byte-identical
   Layer 1 quality scores and Layer 2 descriptors.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

from open_composer.research.campaign import MAX_FAMILY_EFFECTIVE_TRIAL_COUNT
from open_composer.research.kernel.behavioral_descriptors import behavioral_descriptors
from open_composer.research.kernel.layered_search import (
    LAYER2_DESCRIPTOR_NAMES,
    DevelopmentView,
    LookaheadError,
    assert_causal_transform,
    build_layer2_policy,
    development_quality,
    development_view,
    run_layered_search,
    select_layer1_survivors,
)
from open_composer.research.kernel.mechanism_eval import Candidate

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _dates(n: int, *, start: str = "2020-01-02") -> list[str]:
    index = pd.bdate_range(start, periods=n, tz="UTC")
    return [timestamp.isoformat() for timestamp in index]


def _make_candidate(
    candidate_id: str,
    *,
    seed: int,
    n_per_fold: int = 60,
    fold_count: int = 3,
    mechanism_family: str = "fam",
    oos_override: list[float] | None = None,
) -> Candidate:
    rng = np.random.default_rng(seed)
    folds = [rng.normal(0.0006, 0.01, n_per_fold).tolist() for _ in range(fold_count)]
    flattened = [value for fold in folds for value in fold]
    # Development and OOS are disjoint calendars, as expand_mechanism enforces.
    all_dates = _dates(len(flattened) * 2)
    development_dates = all_dates[: len(flattened)]
    dates = all_dates[len(flattened) :]
    oos = oos_override if oos_override is not None else flattened
    return Candidate(
        candidate_id=candidate_id,
        mechanism_family=mechanism_family,
        param_vector={"seed": seed},
        oos_return_stream=oos,
        oos_dates=dates,
        oos_fold_returns=folds,
        development_returns=flattened,
        development_dates=development_dates,
        stress_return_stream=oos,
    )


def _benchmark_for(candidate: Candidate, *, seed: int = 7) -> pd.Series:
    # Must span both calendars: selection reads the development window, the
    # gate reads the out-of-sample window, and they are disjoint.
    dates = sorted({*candidate.development_dates, *candidate.oos_dates})
    index = pd.DatetimeIndex(dates)
    values = np.random.default_rng(seed).normal(0.0003, 0.008, len(dates))
    return pd.Series(values, index=index)


class _TripwireCandidate:
    """Duck-types ``Candidate`` but raises if OOS fields are ever read.

    Used to prove -- as an executable test, not just a code-review claim --
    that the Layer 1/2 code path in ``layered_search.py`` never touches
    ``oos_return_stream``/``stress_return_stream``.
    """

    def __init__(
        self,
        *,
        candidate_id: str,
        mechanism_family: str,
        param_vector: dict,
        generation: int,
        parent_id: str | None,
        development_returns: list[float],
        development_dates: list[str],
        oos_dates: list[str],
    ) -> None:
        self.candidate_id = candidate_id
        self.mechanism_family = mechanism_family
        self.param_vector = param_vector
        self.generation = generation
        self.parent_id = parent_id
        self.development_returns = development_returns
        self.development_dates = development_dates
        self._oos_dates = oos_dates

    @property
    def oos_dates(self) -> list[str]:
        return self._oos_dates

    @property
    def oos_return_stream(self) -> list[float]:
        raise AssertionError("Layer 1/2 selection code touched oos_return_stream")

    @property
    def stress_return_stream(self) -> list[float]:
        raise AssertionError("Layer 1/2 selection code touched stress_return_stream")


# ---------------------------------------------------------------------------
# Structural firewall: DevelopmentView cannot carry OOS data
# ---------------------------------------------------------------------------


def test_development_view_has_no_oos_fields() -> None:
    names = {field.name for field in dataclasses.fields(DevelopmentView)}
    assert "oos_return_stream" not in names
    assert "stress_return_stream" not in names


def test_layer1_layer2_path_never_reads_oos_fields_even_when_offered() -> None:
    folds = [[0.01, -0.02, 0.03, 0.01, -0.005], [0.02, 0.01, -0.01, 0.015, -0.02]]
    flattened_len = sum(len(fold) for fold in folds)
    dates = _dates(flattened_len)
    benchmark = pd.Series(
        np.random.default_rng(40).normal(0.0002, 0.01, flattened_len),
        index=pd.DatetimeIndex(dates),
    )
    tripwire = _TripwireCandidate(
        candidate_id="tripwire-000",
        mechanism_family="fam",
        param_vector={},
        generation=0,
        parent_id=None,
        development_returns=[v for fold in folds for v in fold],
        development_dates=_dates(sum(len(f) for f in folds)),
        oos_dates=dates,
    )

    # None of the following may raise -- if any of them read oos_return_stream
    # or stress_return_stream, the tripwire property raises AssertionError.
    view = development_view(tripwire, benchmark)
    quality = development_quality(view)
    assert math.isfinite(quality) or quality == float("-inf")
    descriptors = behavioral_descriptors(
        view.flattened_returns, benchmark_returns=view.flattened_benchmark_returns
    )
    assert set(descriptors) == set(LAYER2_DESCRIPTOR_NAMES) - {"mechanism_family"}


def test_layer1_and_layer2_outputs_are_invariant_to_oos_return_stream_content() -> None:
    """Poisoning oos_return_stream alone must not change any Layer 1/2 output."""
    candidate_a = _make_candidate("cand-a", seed=1)
    poisoned = [999.0] * len(candidate_a.oos_return_stream)
    candidate_b = _make_candidate("cand-a", seed=1, oos_override=poisoned)

    assert candidate_a.development_returns == candidate_b.development_returns
    assert candidate_a.oos_return_stream != candidate_b.oos_return_stream

    benchmark = _benchmark_for(candidate_a)
    view_a = development_view(candidate_a, benchmark)
    view_b = development_view(candidate_b, benchmark)
    assert view_a.development_returns == view_b.development_returns
    assert development_quality(view_a) == development_quality(view_b)

    descriptors_a = behavioral_descriptors(
        view_a.flattened_returns, benchmark_returns=view_a.flattened_benchmark_returns
    )
    descriptors_b = behavioral_descriptors(
        view_b.flattened_returns, benchmark_returns=view_b.flattened_benchmark_returns
    )
    assert descriptors_a == descriptors_b


# ---------------------------------------------------------------------------
# Layer 1 selection
# ---------------------------------------------------------------------------


def test_select_layer1_survivors_drops_degenerate_candidates() -> None:
    good = _make_candidate("good-000", seed=1)
    degenerate_folds = [[0.0] * 60, [0.0] * 60]
    degenerate = Candidate(
        candidate_id="degenerate-000",
        mechanism_family="fam",
        param_vector={},
        oos_return_stream=[0.0] * 120,
        oos_dates=_dates(120),
        development_returns=[v for fold in degenerate_folds for v in fold],
        development_dates=_dates(sum(len(f) for f in degenerate_folds)),
        stress_return_stream=[0.0] * 120,
    )
    benchmark_good = _benchmark_for(good)
    benchmark_bad = pd.Series(
        np.zeros(120), index=pd.DatetimeIndex(_dates(120))
    ) + 0.0001 * np.arange(120)
    views = [
        development_view(good, benchmark_good),
        development_view(degenerate, benchmark_bad),
    ]
    qualities, survivors = select_layer1_survivors(views)
    assert qualities["degenerate-000"] == float("-inf")
    assert [view.candidate_id for view in survivors] == ["good-000"]


def test_build_layer2_policy_rejects_empty_survivor_list() -> None:
    with pytest.raises(ValueError):
        build_layer2_policy([], campaign_id="p2a-test")


# ---------------------------------------------------------------------------
# End-to-end: run_layered_search
# ---------------------------------------------------------------------------


def test_run_layered_search_rejects_an_explicit_dsr_trial_count_override() -> None:
    candidate = _make_candidate("only-000", seed=1)
    benchmark = _benchmark_for(candidate)
    with pytest.raises(ValueError, match="dsr_trial_count"):
        run_layered_search(
            [candidate],
            benchmark_returns=benchmark,
            campaign_id="p2a-test",
            qqq_returns=benchmark,
            tqqq_returns=benchmark,
            bil_returns=benchmark,
            dsr_trial_count=5,
        )


def test_run_layered_search_rejects_duplicate_candidate_ids() -> None:
    candidate = _make_candidate("dup-000", seed=1)
    benchmark = _benchmark_for(candidate)
    with pytest.raises(ValueError, match="unique"):
        run_layered_search(
            [candidate, candidate],
            benchmark_returns=benchmark,
            campaign_id="p2a-test",
            qqq_returns=benchmark,
            tqqq_returns=benchmark,
            bil_returns=benchmark,
        )


def test_run_layered_search_handles_zero_layer1_survivors() -> None:
    n = 60
    dates = _dates(n)
    index = pd.DatetimeIndex(dates)
    flat = [0.0] * n
    candidate = Candidate(
        candidate_id="degenerate-000",
        mechanism_family="degenerate",
        param_vector={},
        oos_return_stream=flat,
        oos_dates=dates,
        development_returns=list(flat),
        development_dates=_dates(len(flat)),
        stress_return_stream=flat,
    )
    benchmark = pd.Series(np.random.default_rng(50).normal(0.0002, 0.01, n), index=index)

    verdict = run_layered_search(
        [candidate],
        benchmark_returns=benchmark,
        campaign_id="p2a-degenerate",
        qqq_returns=benchmark,
        tqqq_returns=benchmark,
        bil_returns=benchmark,
    )
    assert verdict.raw_candidate_count == 1
    assert verdict.layer1_survivor_count == 0
    assert verdict.layer2_elite_count == 0
    assert verdict.effective_n_gate_passed is False
    assert verdict.family_verdict is None
    assert verdict.qd_archive.elite_count == 0


def test_run_layered_search_end_to_end() -> None:
    candidates = [
        _make_candidate(f"fam_a-{i:03d}", seed=100 + i, mechanism_family="fam_a") for i in range(4)
    ] + [
        _make_candidate(f"fam_b-{i:03d}", seed=200 + i, mechanism_family="fam_b") for i in range(4)
    ]
    dates = candidates[0].oos_dates
    for candidate in candidates[1:]:
        assert candidate.oos_dates == dates
    # Benchmarks must span the development calendar as well: selection reads
    # the development window and the gate reads the disjoint OOS window.
    all_dates = sorted({*candidates[0].development_dates, *dates})
    index = pd.DatetimeIndex(all_dates)
    rng = np.random.default_rng(999)
    qqq = pd.Series(rng.normal(0.0004, 0.01, len(all_dates)), index=index)
    tqqq = pd.Series(rng.normal(0.0008, 0.03, len(all_dates)), index=index)
    bil = pd.Series(rng.normal(0.00005, 0.0002, len(all_dates)), index=index)

    verdict = run_layered_search(
        candidates,
        benchmark_returns=qqq,
        campaign_id="p2a-test-campaign",
        qqq_returns=qqq,
        tqqq_returns=tqqq,
        bil_returns=bil,
    )

    assert verdict.raw_candidate_count == 8
    assert 0 < verdict.layer1_survivor_count <= 8
    assert 0 < verdict.layer2_elite_count <= verdict.layer1_survivor_count
    assert verdict.qd_archive.elite_count == verdict.layer2_elite_count
    for elite in verdict.qd_archive.elites:
        assert set(elite.cell_descriptors) == set(LAYER2_DESCRIPTOR_NAMES)
    assert verdict.max_effective_n == MAX_FAMILY_EFFECTIVE_TRIAL_COUNT
    if verdict.effective_n_gate_passed:
        assert verdict.family_verdict is not None
        assert verdict.family_verdict.effective_n <= verdict.max_effective_n
        assert len(verdict.family_verdict.candidates) == verdict.layer2_elite_count
    else:
        assert verdict.family_verdict is not None
        assert verdict.family_verdict.effective_n > verdict.max_effective_n


def test_run_layered_search_is_deterministic_given_the_same_inputs() -> None:
    def build() -> list[Candidate]:
        return [_make_candidate(f"fam-{i:03d}", seed=10 + i) for i in range(5)]

    candidates_first = build()
    candidates_second = build()
    benchmark = _benchmark_for(candidates_first[0])

    first = run_layered_search(
        candidates_first,
        benchmark_returns=benchmark,
        campaign_id="p2a-determinism",
        qqq_returns=benchmark,
        tqqq_returns=benchmark,
        bil_returns=benchmark,
    )
    second = run_layered_search(
        candidates_second,
        benchmark_returns=benchmark,
        campaign_id="p2a-determinism",
        qqq_returns=benchmark,
        tqqq_returns=benchmark,
        bil_returns=benchmark,
    )
    assert first.model_dump() == second.model_dump()


# ---------------------------------------------------------------------------
# Anti-lookahead: assert_causal_transform (plan section 6.3)
# ---------------------------------------------------------------------------


def _raw_series(seed: int, *, n: int = 300) -> pd.Series:
    index = pd.bdate_range("2020-01-02", periods=n, tz="UTC")
    return pd.Series(np.random.default_rng(seed).normal(0.0, 1.0, n), index=index)


def test_causal_lagged_rolling_mean_passes() -> None:
    raw = _raw_series(31)
    causal = lambda series: series.rolling(5, min_periods=5).mean().shift(1)  # noqa: E731
    assert_causal_transform(causal, raw)  # must not raise


def test_centered_rolling_mean_is_rejected_as_lookahead() -> None:
    raw = _raw_series(32)
    contaminated = lambda series: series.rolling(5, center=True, min_periods=5).mean()  # noqa: E731
    with pytest.raises(LookaheadError):
        assert_causal_transform(contaminated, raw)


def test_full_sample_zscore_is_rejected_as_lookahead() -> None:
    raw = _raw_series(33)
    contaminated = lambda series: (series - series.mean()) / series.std()  # noqa: E731
    with pytest.raises(LookaheadError):
        assert_causal_transform(contaminated, raw)


def test_causal_transform_requires_a_datetime_index() -> None:
    raw = pd.Series(np.arange(10, dtype=float))
    with pytest.raises(ValueError):
        assert_causal_transform(lambda series: series, raw)


# ---------------------------------------------------------------------------
# Anti-lookahead: probe coverage (regression for a real blind spot)
# ---------------------------------------------------------------------------


def _date_anchored_leak(cutoff: pd.Timestamp, *, before: bool):
    """A transform that is causal everywhere except one absolute date range.

    Anchoring the leak to absolute dates rather than to a fraction of the
    series is what makes it dangerous: the contaminated region does not move
    when the series is truncated, so it can hide from any probe that never
    lands inside it.
    """

    def transform(series: pd.Series) -> pd.Series:
        out = series.shift(1).rolling(5, min_periods=5).mean()
        mask = series.index <= cutoff if before else series.index >= cutoff
        out.loc[mask] = series.loc[mask].shift(-1)
        return out

    return transform


def _probe_series(length: int = 400) -> pd.Series:
    index = pd.date_range("2020-01-01", periods=length, freq="B")
    values = np.linspace(1.0, 2.0, length) + np.sin(np.arange(length) / 7.0) * 0.05
    return pd.Series(values, index=index)


def test_lookahead_probes_cover_the_tail_of_the_series() -> None:
    """A leak confined to the last 10% must not survive.

    The probe window used to be a fixed [40%, 90%] slice, so a leak anchored
    past the 90% mark went undetected -- and raising ``probe_count`` did not
    help, because the extra probes landed inside the same window. The tail is
    the most recent data, which is where an accidental leak is most likely.
    """
    raw = _probe_series()
    leak = _date_anchored_leak(pd.Timestamp("2021-06-01"), before=False)
    with pytest.raises(LookaheadError):
        assert_causal_transform(leak, raw)
    with pytest.raises(LookaheadError):
        assert_causal_transform(leak, raw, probe_count=40)


def test_lookahead_probes_cover_the_head_of_the_series() -> None:
    raw = _probe_series()
    leak = _date_anchored_leak(pd.Timestamp("2020-06-01"), before=True)
    with pytest.raises(LookaheadError):
        assert_causal_transform(leak, raw)


def test_widened_probe_window_does_not_flag_legitimate_causal_transforms() -> None:
    """The widened window must not trade a blind spot for false positives."""
    raw = _probe_series()
    assert_causal_transform(lambda s: s.shift(1).rolling(5, min_periods=5).mean(), raw)
    assert_causal_transform(lambda s: s.shift(1).ewm(span=10, adjust=False).mean(), raw)
    assert_causal_transform(lambda s: s.shift(1).rolling(60, min_periods=60).std(), raw)


# ---------------------------------------------------------------------------
# The DSR must be charged for the whole search, not for the survivors
# ---------------------------------------------------------------------------


def test_dsr_trial_count_reflects_every_candidate_not_just_the_elites() -> None:
    """Regression: clustering only the gated elites understates the trial count.

    ``campaign.py``'s ``_effective_trial_clustering_blockers`` rejects exactly
    this on the campaign path -- clustering a hand-picked subset. The kernel
    search screens many candidates down to a few elites, so charging the DSR
    for the elite-level cluster count would price in the diversity of the
    survivors while ignoring the selection pressure of the whole search.
    """
    candidates = [
        _make_candidate(f"fam_a-{i:03d}", seed=300 + i, mechanism_family="fam_a") for i in range(6)
    ] + [
        _make_candidate(f"fam_b-{i:03d}", seed=400 + i, mechanism_family="fam_b") for i in range(6)
    ]
    dates = candidates[0].oos_dates
    all_dates = sorted({*candidates[0].development_dates, *dates})
    index = pd.DatetimeIndex(all_dates)
    rng = np.random.default_rng(4242)
    qqq = pd.Series(rng.normal(0.0004, 0.01, len(all_dates)), index=index)
    tqqq = pd.Series(rng.normal(0.0008, 0.03, len(all_dates)), index=index)
    bil = pd.Series(rng.normal(0.00005, 0.0002, len(all_dates)), index=index)

    verdict = run_layered_search(
        candidates,
        benchmark_returns=qqq,
        campaign_id="dsr-trial-count-test",
        qqq_returns=qqq,
        tqqq_returns=tqqq,
        bil_returns=bil,
        min_dsr_stream_rows=1,
    )
    assert verdict.effective_n_gate_passed
    assert verdict.family_verdict is not None
    # Fewer elites survive than candidates searched, so the search-wide count
    # is the larger one and is what the DSR is charged for.
    assert verdict.layer2_elite_count < verdict.raw_candidate_count
    assert verdict.search_effective_n >= verdict.family_verdict.effective_n
    assert verdict.dsr_trial_count >= verdict.search_effective_n
    assert verdict.dsr_trial_count >= verdict.family_verdict.effective_n
