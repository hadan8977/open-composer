"""Bounded parameter grids and bounded mutation for same-mechanism search.

Work Item P2a (``docs/plan-sip-migration-and-wide-search-2026-09-01.zh.md``
section 6.1) is "search inside one mechanism's parameter space": a grid over
that space, plus bounded mutation of parents drawn from the QD archive
(``open_composer.research.quality_diversity``). ``bounded_parameter_mutation``
previously existed only as a ``Literal["none", "bounded_parameter_mutation"]``
string on ``CampaignExplorationPolicy.mutation_mode``
(``open_composer/research/campaign.py``) with no implementation anywhere in
the codebase -- this module is that implementation.

Every parameter a mechanism can be searched over must declare a *bounded*
domain up front (:class:`ParameterSpec`). Two properties are non-negotiable:

* :meth:`ParameterSpace.validate` rejects any vector outside that domain --
  no implicit clamping on the way in.
* :func:`bounded_parameter_mutation` can *never* produce an out-of-domain
  vector: it clamps after perturbing and asserts the clamp held, so escaping
  the declared bounds is a programming error caught immediately, not a
  possibility a caller has to guard against.

Determinism: every seeded call here uses a fresh ``numpy.random.default_rng``
(or ``random.Random``) seeded exactly by the caller-supplied ``seed`` -- no
module-level RNG state, no wall-clock, no ``Math.random``-style ambient
randomness. The same seed always produces the same output.
"""

from __future__ import annotations

import itertools
import logging
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from open_composer.research.kernel.datamodel import ResearchDataModel

logger = logging.getLogger(__name__)

ParameterKind = Literal["int", "float", "categorical"]

#: Fraction of a numeric parameter's declared range used as the standard
#: deviation of the mutation perturbation before the per-parameter
#: ``mutation_rate`` scaling is applied. A declared constant, not tuned to
#: any observed search result.
_MUTATION_RANGE_FRACTION = 0.25


@dataclass(frozen=True)
class ParameterSpec:
    """One parameter's declared, bounded domain.

    ``int``/``float`` kinds declare ``low``, ``high`` (inclusive bounds) and
    ``step`` (grid resolution / mutation scale reference). ``categorical``
    declares ``choices`` instead. A spec with an empty or unbounded domain is
    rejected at construction time -- there is no such thing as an
    "unbounded" :class:`ParameterSpec`.
    """

    name: str
    kind: ParameterKind
    low: float | None = None
    high: float | None = None
    step: float | None = None
    choices: tuple[Any, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("ParameterSpec.name must be a non-empty string")
        if self.kind not in ("int", "float", "categorical"):
            raise ValueError(f"ParameterSpec.kind must be int/float/categorical: {self.kind!r}")
        if self.kind == "categorical":
            if self.low is not None or self.high is not None or self.step is not None:
                raise ValueError(
                    f"{self.name}: categorical parameters must not declare low/high/step"
                )
            if not self.choices or len(self.choices) == 0:
                raise ValueError(f"{self.name}: categorical parameters require non-empty choices")
            if len(set(self.choices)) != len(self.choices):
                raise ValueError(f"{self.name}: categorical choices must be unique")
            return

        # int / float
        if self.choices is not None:
            raise ValueError(f"{self.name}: {self.kind} parameters must not declare choices")
        if self.low is None or self.high is None:
            raise ValueError(f"{self.name}: {self.kind} parameters require low and high")
        if not math.isfinite(self.low) or not math.isfinite(self.high):
            raise ValueError(f"{self.name}: low/high must be finite")
        if self.low > self.high:
            raise ValueError(f"{self.name}: low ({self.low}) exceeds high ({self.high})")
        if self.step is None:
            raise ValueError(
                f"{self.name}: {self.kind} parameters require a step "
                "(grid resolution / mutation scale reference)"
            )
        if not math.isfinite(self.step) or self.step <= 0:
            raise ValueError(f"{self.name}: step must be a finite positive number")
        if self.kind == "int":
            if float(self.low).is_integer() is False or float(self.high).is_integer() is False:
                raise ValueError(f"{self.name}: int parameters require integer low/high")
            if float(self.step).is_integer() is False:
                raise ValueError(f"{self.name}: int parameters require an integer step")

    def in_domain(self, value: Any) -> bool:
        """Return whether ``value`` lies inside this parameter's declared bounds."""
        if self.kind == "categorical":
            return value in (self.choices or ())
        if self.kind == "int":
            if isinstance(value, bool) or not isinstance(value, int | np.integer):
                return False
        else:
            if isinstance(value, bool) or not isinstance(value, int | float | np.floating):
                return False
            if not math.isfinite(float(value)):
                return False
        return float(self.low) <= float(value) <= float(self.high)

    def grid_values(self) -> tuple[Any, ...]:
        """Enumerate this parameter's grid points in deterministic order."""
        if self.kind == "categorical":
            return tuple(self.choices or ())
        count = int(round((float(self.high) - float(self.low)) / float(self.step))) + 1
        values = [float(self.low) + index * float(self.step) for index in range(count)]
        # Clamp the last point exactly onto ``high`` to absorb float drift.
        values[-1] = float(self.high)
        if self.kind == "int":
            return tuple(int(round(value)) for value in values)
        return tuple(values)

    def clamp(self, value: Any) -> Any:
        """Coerce ``value`` back inside the declared bounds (categorical: unchanged)."""
        if self.kind == "categorical":
            return value
        clamped = min(max(float(value), float(self.low)), float(self.high))
        return int(round(clamped)) if self.kind == "int" else float(clamped)


@dataclass(frozen=True)
class ParameterSpace:
    """A named collection of :class:`ParameterSpec` -- one mechanism's search domain."""

    specs: tuple[ParameterSpec, ...]

    def __post_init__(self) -> None:
        if not self.specs:
            raise ValueError("ParameterSpace requires at least one ParameterSpec")
        names = [spec.name for spec in self.specs]
        if len(set(names)) != len(names):
            raise ValueError("ParameterSpace parameter names must be unique")

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.specs)

    def spec(self, name: str) -> ParameterSpec:
        for spec in self.specs:
            if spec.name == name:
                return spec
        raise KeyError(f"no such parameter: {name}")

    def validate(self, params: Mapping[str, Any]) -> None:
        """Raise ``ValueError`` if ``params`` is not a point in this space's domain."""
        declared = set(self.names)
        given = set(params)
        missing = sorted(declared - given)
        if missing:
            raise ValueError(f"parameter vector is missing declared parameters: {missing}")
        extra = sorted(given - declared)
        if extra:
            raise ValueError(f"parameter vector has undeclared parameters: {extra}")
        violations = [
            f"{spec.name}={params[spec.name]!r}"
            for spec in self.specs
            if not spec.in_domain(params[spec.name])
        ]
        if violations:
            raise ValueError(f"parameter vector is out of declared bounds: {', '.join(violations)}")


@dataclass(frozen=True)
class BoundedGridResult(ResearchDataModel):
    """A deterministic grid enumeration, honest about what it dropped."""

    points: tuple[dict[str, Any], ...]
    full_grid_size: int
    requested_max_points: int
    returned_point_count: int
    dropped_point_count: int
    subsampled: bool
    seed: int
    parameter_names: tuple[str, ...] = field(default_factory=tuple)


def _floyd_sample_indices(*, population: int, sample_size: int, seed: int) -> list[int]:
    """Deterministically sample ``sample_size`` unique indices from ``range(population)``.

    Floyd's algorithm (Floyd, 1980, CACM "Trans. Programming Techniques"):
    a uniform sample of a fixed size, without replacement, in O(sample_size)
    memory regardless of how large ``population`` is (never materializes the
    population). Uses Python's stdlib ``random.Random`` (not numpy) so an
    arbitrarily large ``population`` never overflows a fixed-width integer
    RNG.
    """
    if sample_size > population:
        raise ValueError("sample_size cannot exceed population")
    rng = random.Random(seed)
    selected: set[int] = set()
    for candidate_index in range(population - sample_size, population):
        draw = rng.randint(0, candidate_index)
        selected.add(candidate_index if draw in selected else draw)
    return sorted(selected)


def bounded_grid(
    space: ParameterSpace,
    *,
    max_points: int,
    seed: int = 0,
) -> BoundedGridResult:
    """Deterministically enumerate ``space``'s grid, subsampling if it is too large.

    If the full cartesian product of every parameter's :meth:`ParameterSpec.grid_values`
    exceeds ``max_points``, a deterministic, seeded subsample of exactly
    ``max_points`` points is returned instead -- the drop is always reported in
    the result (``dropped_point_count``, ``subsampled``) and logged, never
    silently truncated (e.g. by taking the first ``max_points`` points, which
    would bias the sample toward one corner of the space).
    """
    if max_points < 1:
        raise ValueError("max_points must be a positive integer")
    value_lists = [spec.grid_values() for spec in space.specs]
    sizes = [len(values) for values in value_lists]
    full_grid_size = math.prod(sizes)
    if full_grid_size == 0:
        raise ValueError("parameter space grid is empty")

    if full_grid_size <= max_points:
        combinations = itertools.product(*value_lists)
        points = tuple(dict(zip(space.names, combo, strict=True)) for combo in combinations)
        result = BoundedGridResult(
            points=points,
            full_grid_size=full_grid_size,
            requested_max_points=max_points,
            returned_point_count=len(points),
            dropped_point_count=0,
            subsampled=False,
            seed=seed,
            parameter_names=space.names,
        )
    else:
        dropped = full_grid_size - max_points
        logger.warning(
            "bounded_grid: full grid has %d points, exceeds max_points=%d; "
            "deterministically subsampling and dropping %d point(s) (seed=%d)",
            full_grid_size,
            max_points,
            dropped,
            seed,
        )
        indices = _floyd_sample_indices(
            population=full_grid_size, sample_size=max_points, seed=seed
        )
        points = tuple(
            dict(zip(space.names, _unrank_combination(index, sizes, value_lists), strict=True))
            for index in indices
        )
        result = BoundedGridResult(
            points=points,
            full_grid_size=full_grid_size,
            requested_max_points=max_points,
            returned_point_count=len(points),
            dropped_point_count=dropped,
            subsampled=True,
            seed=seed,
            parameter_names=space.names,
        )

    for point in result.points:
        space.validate(point)
    return result


def _unrank_combination(
    index: int,
    sizes: Sequence[int],
    value_lists: Sequence[tuple[Any, ...]],
) -> tuple[Any, ...]:
    """Map a flat index in ``[0, prod(sizes))`` to one cartesian-product combination.

    Mixed-radix decomposition with the last parameter varying fastest, i.e.
    identical ordering to ``itertools.product(*value_lists)``.
    """
    remainder = index
    picks: list[Any] = [None] * len(sizes)
    for position in range(len(sizes) - 1, -1, -1):
        size = sizes[position]
        remainder, digit = divmod(remainder, size)
        picks[position] = value_lists[position][digit]
    if remainder != 0:
        raise ValueError("index out of range for this grid")
    return tuple(picks)


def bounded_parameter_mutation(
    parent_params: Mapping[str, Any],
    space: ParameterSpace,
    *,
    seed: int,
    mutation_rate: float,
) -> dict[str, Any]:
    """Perturb ``parent_params`` into a child that cannot escape ``space``'s bounds.

    For every parameter, with probability ``mutation_rate`` the child's value
    is redrawn: categorical parameters get a uniformly random choice (which
    may coincidentally match the parent), numeric parameters get Gaussian
    noise scaled by the parameter's declared range and then are clamped back
    into ``[low, high]``. Parameters that are not selected for mutation are
    copied verbatim from the parent.

    It is mathematically impossible for the result to leave the declared
    bounds: every numeric perturbation is clamped, and the full child vector
    is asserted against ``space.validate`` before being returned. Two calls
    with the same ``seed`` (and the same ``parent_params``/``space``/
    ``mutation_rate``) always return an identical child.
    """
    if not math.isfinite(mutation_rate) or not 0.0 <= mutation_rate <= 1.0:
        raise ValueError(f"mutation_rate must be in [0, 1]: {mutation_rate!r}")
    space.validate(parent_params)
    rng = np.random.default_rng(seed)

    child: dict[str, Any] = {}
    for spec in space.specs:
        current = parent_params[spec.name]
        if rng.random() >= mutation_rate:
            child[spec.name] = current
            continue
        if spec.kind == "categorical":
            choices = spec.choices or ()
            child[spec.name] = choices[int(rng.integers(0, len(choices)))]
            continue
        span = float(spec.high) - float(spec.low)
        sigma = max(span * _MUTATION_RANGE_FRACTION * mutation_rate, 0.0)
        perturbed = float(current) + (float(rng.normal(0.0, sigma)) if sigma > 0.0 else 0.0)
        clamped = spec.clamp(perturbed)
        if not spec.in_domain(clamped):
            raise AssertionError(
                f"bounded_parameter_mutation escaped declared bounds for {spec.name}: {clamped!r}"
            )
        child[spec.name] = clamped

    space.validate(child)
    return child
