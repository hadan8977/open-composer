"""P2a: bounded parameter grids and bounded mutation.

Acceptance criteria from
``docs/plan-sip-migration-and-wide-search-2026-09-01.zh.md`` section 6.1:
``bounded_parameter_mutation`` previously existed only as a ``Literal``
string with zero implementation (``campaign.py:218``); tests must cover
out-of-bounds rejection, mutation never escaping bounds under many seeds,
seed determinism, and that grid subsampling reports what it dropped.
"""

from __future__ import annotations

import pytest

from open_composer.research.kernel.parameter_search import (
    ParameterSpace,
    ParameterSpec,
    bounded_grid,
    bounded_parameter_mutation,
)


def _sample_space() -> ParameterSpace:
    return ParameterSpace(
        specs=(
            ParameterSpec(name="lookback", kind="int", low=10, high=50, step=10),
            ParameterSpec(name="threshold", kind="float", low=0.0, high=0.05, step=0.01),
            ParameterSpec(name="sleeve", kind="categorical", choices=("QQQ", "BIL")),
        )
    )


# ---------------------------------------------------------------------------
# ParameterSpec / ParameterSpace construction
# ---------------------------------------------------------------------------


def test_numeric_spec_requires_a_step() -> None:
    with pytest.raises(ValueError, match="step"):
        ParameterSpec(name="x", kind="float", low=0.0, high=1.0)


def test_categorical_spec_rejects_low_high_step() -> None:
    with pytest.raises(ValueError):
        ParameterSpec(name="x", kind="categorical", choices=("a", "b"), low=0.0)


def test_categorical_spec_requires_nonempty_choices() -> None:
    with pytest.raises(ValueError):
        ParameterSpec(name="x", kind="categorical", choices=())


def test_categorical_spec_rejects_duplicate_choices() -> None:
    with pytest.raises(ValueError):
        ParameterSpec(name="x", kind="categorical", choices=("a", "a"))


def test_numeric_spec_rejects_low_above_high() -> None:
    with pytest.raises(ValueError):
        ParameterSpec(name="x", kind="float", low=1.0, high=0.0, step=0.1)


def test_int_spec_rejects_non_integer_bounds() -> None:
    with pytest.raises(ValueError):
        ParameterSpec(name="x", kind="int", low=0.5, high=10, step=1)


def test_parameter_space_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError):
        ParameterSpace(
            specs=(
                ParameterSpec(name="x", kind="int", low=0, high=1, step=1),
                ParameterSpec(name="x", kind="int", low=0, high=1, step=1),
            )
        )


def test_parameter_space_requires_at_least_one_spec() -> None:
    with pytest.raises(ValueError):
        ParameterSpace(specs=())


# ---------------------------------------------------------------------------
# validate(): out-of-bounds rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"lookback": 60, "threshold": 0.02, "sleeve": "QQQ"},
        {"lookback": 5, "threshold": 0.02, "sleeve": "QQQ"},
        {"lookback": 20, "threshold": 0.10, "sleeve": "QQQ"},
        {"lookback": 20, "threshold": -0.01, "sleeve": "QQQ"},
        {"lookback": 20, "threshold": 0.02, "sleeve": "TQQQ"},
        {"lookback": 20.5, "threshold": 0.02, "sleeve": "QQQ"},
    ],
)
def test_validate_rejects_out_of_domain_vectors(params: dict) -> None:
    space = _sample_space()
    with pytest.raises(ValueError):
        space.validate(params)


def test_validate_rejects_missing_keys() -> None:
    space = _sample_space()
    with pytest.raises(ValueError, match="missing"):
        space.validate({"lookback": 20, "threshold": 0.02})


def test_validate_rejects_undeclared_keys() -> None:
    space = _sample_space()
    with pytest.raises(ValueError, match="undeclared"):
        space.validate({"lookback": 20, "threshold": 0.02, "sleeve": "QQQ", "extra": 1})


def test_validate_accepts_every_declared_grid_point() -> None:
    space = _sample_space()
    grid = bounded_grid(space, max_points=10_000)
    assert grid.subsampled is False
    for point in grid.points:
        space.validate(point)  # must not raise


def test_spec_clamp_stays_within_bounds() -> None:
    spec = ParameterSpec(name="x", kind="float", low=0.0, high=1.0, step=0.1)
    assert spec.clamp(5.0) == 1.0
    assert spec.clamp(-5.0) == 0.0
    assert spec.clamp(0.5) == 0.5


# ---------------------------------------------------------------------------
# bounded_parameter_mutation: never escapes bounds, deterministic given seed
# ---------------------------------------------------------------------------


def test_mutation_never_escapes_bounds_across_many_seeds() -> None:
    space = _sample_space()
    parent = {"lookback": 30, "threshold": 0.02, "sleeve": "QQQ"}
    for seed in range(500):
        child = bounded_parameter_mutation(parent, space, seed=seed, mutation_rate=0.9)
        space.validate(child)  # must not raise


def test_mutation_never_escapes_bounds_from_a_boundary_parent() -> None:
    space = _sample_space()
    parent = {"lookback": 10, "threshold": 0.0, "sleeve": "BIL"}
    for seed in range(200):
        child = bounded_parameter_mutation(parent, space, seed=seed, mutation_rate=1.0)
        space.validate(child)


def test_mutation_rejects_an_invalid_parent() -> None:
    space = _sample_space()
    invalid_parent = {"lookback": 999, "threshold": 0.02, "sleeve": "QQQ"}
    with pytest.raises(ValueError):
        bounded_parameter_mutation(invalid_parent, space, seed=1, mutation_rate=0.5)


def test_mutation_rejects_an_out_of_range_mutation_rate() -> None:
    space = _sample_space()
    parent = {"lookback": 30, "threshold": 0.02, "sleeve": "QQQ"}
    with pytest.raises(ValueError):
        bounded_parameter_mutation(parent, space, seed=1, mutation_rate=1.5)


def test_mutation_is_deterministic_given_the_same_seed() -> None:
    space = _sample_space()
    parent = {"lookback": 30, "threshold": 0.02, "sleeve": "QQQ"}
    first = bounded_parameter_mutation(parent, space, seed=42, mutation_rate=0.5)
    second = bounded_parameter_mutation(parent, space, seed=42, mutation_rate=0.5)
    assert first == second


def test_mutation_differs_across_seeds_at_least_sometimes() -> None:
    space = _sample_space()
    parent = {"lookback": 30, "threshold": 0.02, "sleeve": "QQQ"}
    children = {
        tuple(
            sorted(bounded_parameter_mutation(parent, space, seed=seed, mutation_rate=1.0).items())
        )
        for seed in range(20)
    }
    assert len(children) > 1


def test_zero_mutation_rate_always_returns_the_parent() -> None:
    space = _sample_space()
    parent = {"lookback": 30, "threshold": 0.02, "sleeve": "QQQ"}
    for seed in range(10):
        child = bounded_parameter_mutation(parent, space, seed=seed, mutation_rate=0.0)
        assert child == parent


# ---------------------------------------------------------------------------
# bounded_grid: deterministic enumeration and honest subsampling
# ---------------------------------------------------------------------------


def test_bounded_grid_returns_full_grid_when_under_budget() -> None:
    space = _sample_space()
    result = bounded_grid(space, max_points=1000, seed=1)
    assert result.full_grid_size == 60  # 5 lookbacks * 6 thresholds * 2 sleeves
    assert result.returned_point_count == 60
    assert result.dropped_point_count == 0
    assert result.subsampled is False


def test_bounded_grid_enumeration_order_matches_cartesian_product() -> None:
    space = _sample_space()
    result = bounded_grid(space, max_points=1000, seed=1)
    assert result.points[0] == {"lookback": 10, "threshold": 0.0, "sleeve": "QQQ"}
    assert result.points[1] == {"lookback": 10, "threshold": 0.0, "sleeve": "BIL"}


def test_bounded_grid_subsamples_and_reports_drops() -> None:
    space = _sample_space()
    max_points = 20
    result = bounded_grid(space, max_points=max_points, seed=7)
    assert result.full_grid_size == 60
    assert result.returned_point_count == max_points
    assert result.dropped_point_count == 60 - max_points
    assert result.subsampled is True
    for point in result.points:
        space.validate(point)
    unique_points = {tuple(sorted(point.items())) for point in result.points}
    assert len(unique_points) == max_points


def test_bounded_grid_subsampling_is_deterministic_given_the_same_seed() -> None:
    space = _sample_space()
    first = bounded_grid(space, max_points=15, seed=99)
    second = bounded_grid(space, max_points=15, seed=99)
    assert first.points == second.points
    assert first.dropped_point_count == second.dropped_point_count


def test_bounded_grid_subsampling_differs_across_seeds() -> None:
    space = _sample_space()
    first = bounded_grid(space, max_points=15, seed=1)
    second = bounded_grid(space, max_points=15, seed=2)
    assert first.points != second.points


def test_bounded_grid_rejects_nonpositive_max_points() -> None:
    space = _sample_space()
    with pytest.raises(ValueError):
        bounded_grid(space, max_points=0)
