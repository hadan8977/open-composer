"""Genetic-programming driver over ``expression_trees.py`` (Work Item P2b).

This module owns *evolution* (random generation, mutation, crossover, and
the generation-by-generation loop); ``expression_trees.py`` owns the
*grammar* (node types, depth/size limits, operators, the causality check).
The split mirrors ``parameter_search.py`` (grid/mutation) vs
``layered_search.py`` (selection loop) elsewhere in this package.

Where this search is legitimate (plan section 6.4)
----------------------------------------------------
:func:`run_expression_gp_search` is Layer 1 discovery: it evolves and scores
every individual **only on the development partition** (the region strictly
before the first ``rolling_origin_folds`` test window -- see
``mechanism_eval.Candidate.development_returns``'s docstring for why that
region, specifically, is the only one safe to select on). It reuses
``layered_search.select_layer1_survivors``/``development_quality`` (quality)
and ``layered_search.build_layer2_archive`` (diversity) verbatim, every
generation, exactly as ``scripts/search_daily_momentum_p2a.py`` does once for
its Generation-0 grid -- the only difference is that this module repeats the
cycle for several generations, breeding the next generation's population
from the previous generation's Layer-2 elites instead of drawing a fresh
grid.

This function never reads a fold's test window, and it has no access to one:
it is only ever given ``development_start``/``development_end`` bounds and a
signal function; it is the caller's responsibility (see
``scripts/search_expression_trees_p2b.py``) to derive those bounds from
``rolling_origin_folds`` and to run the resulting candidate pool through
``nested_walk_forward.run_nested_walk_forward`` for the actual (per-fold,
training-window-only) selection and the out-of-sample gate.

Two return values matter for different reasons (plan section 6.2, "the DSR
trial count is charged for the whole search, not the survivors"):

* ``all_individuals`` -- every distinct (by formula) expression this run
  ever constructed and admitted (causal and non-degenerate; see
  ``expression_trees.validate_expression_is_causal``/
  ``validate_expression_is_informative``), across every generation. This is
  what the caller must cluster (via
  ``effective_trials.effective_independent_trials``) to calibrate
  ``dsr_trial_count`` before calling ``run_nested_walk_forward`` -- a GP run
  evaluates far more expressions than a grid does, so trusting
  ``mechanism_eval.DEFAULT_DSR_TRIAL_COUNT`` (32) blindly would understate
  the multiple-testing penalty whenever more than 32 distinct expressions
  were ever tried.
* ``final_elite_ids`` -- the last generation's Layer-2 QD-archive elites: a
  small, diversified pool. This is the ``param_space`` the caller should
  actually hand to ``run_nested_walk_forward``.

Determinism: every random draw in this module goes through the single
``numpy.random.default_rng(seed)`` instance threaded through the whole run,
in a fixed, seed-independent order of operations -- no module-level RNG
state, no wall-clock, no unseeded ``random`` calls. The same seed always
reproduces the same sequence of populations and the same final report.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from open_composer.research.kernel.datamodel import ResearchDataModel
from open_composer.research.kernel.expression_trees import (
    BINARY_OPS,
    CONSTANT_CHOICES,
    MAX_NODE_COUNT,
    MAX_TREE_DEPTH,
    TERMINAL_BUILDERS,
    UNARY_OPS,
    BinaryNode,
    ConstantNode,
    DegenerateExpressionError,
    ExpressionNode,
    TerminalNode,
    UnaryNode,
    formula_string,
    validate_expression_is_causal,
    validate_expression_is_informative,
)
from open_composer.research.kernel.layered_search import (
    DevelopmentView,
    LookaheadError,
    build_layer2_archive,
    development_quality,
    select_layer1_survivors,
)

DEFAULT_POPULATION_SIZE = 30
DEFAULT_GENERATION_COUNT = 6
DEFAULT_ELITE_CARRY = 8
#: How many candidate trees / breeding attempts to try before giving up on
#: filling a population slot. ``validate_expression_is_causal`` should
#: essentially never actually reject anything real (every registered
#: operator is provably causal); ``validate_expression_is_informative`` does
#: reject a non-trivial fraction in practice (degenerate/constant
#: expressions are common enough in a randomly-generated population that
#: this is not a rare-path budget for that check), so this is generous
#: enough to absorb both and still terminate deterministically.
_MAX_ATTEMPTS_PER_SLOT = 25

_TERMINAL_NAMES: tuple[str, ...] = tuple(sorted(TERMINAL_BUILDERS))
_UNARY_NAMES: tuple[str, ...] = tuple(sorted(UNARY_OPS))
_BINARY_NAMES: tuple[str, ...] = tuple(sorted(BINARY_OPS))

MECHANISM_FAMILY = "EXPR_GP"


@dataclass(frozen=True)
class GpGenerationSummary(ResearchDataModel):
    """One generation's population/selection counts, for the search report."""

    generation: int
    population_size: int
    layer1_survivor_count: int
    layer2_elite_count: int
    elite_expression_ids: list[str] = field(default_factory=list)
    elite_formulas: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GpSearchResult(ResearchDataModel):
    """The full evolutionary run's report (formulas only -- no tree objects,
    so this is always JSON-serializable via ``model_dump``)."""

    seed: int
    population_size: int
    generation_count: int
    elite_carry: int
    total_individuals_evaluated: int
    rejected_lookahead_count: int
    rejected_degenerate_count: int
    development_start: str
    development_end: str
    generations: list[GpGenerationSummary]
    final_elite_expression_ids: list[str]
    final_elite_formulas: list[str]


def expression_id(formula: str) -> str:
    """Deterministic, content-addressed id: identical formulas always get
    the identical id, both within one run and across separate runs with the
    same grammar -- which is what lets ``all_individuals`` dedupe correctly.
    """
    digest = hashlib.sha256(formula.encode("utf-8")).hexdigest()
    return f"expr-{digest[:16]}"


# ---------------------------------------------------------------------------
# Random generation: bounded-budget "grow" so the result can never exceed
# MAX_TREE_DEPTH/MAX_NODE_COUNT (belt-and-suspenders on top of the
# construction-time enforcement in expression_trees.py itself).
# ---------------------------------------------------------------------------


def _random_leaf(rng: np.random.Generator) -> ExpressionNode:
    if rng.random() < 0.5:
        return TerminalNode(name=str(rng.choice(_TERMINAL_NAMES)))
    return ConstantNode(value=float(rng.choice(CONSTANT_CHOICES)))


def _grow(rng: np.random.Generator, *, remaining_depth: int, remaining_size: int) -> ExpressionNode:
    if remaining_depth <= 1 or remaining_size <= 1:
        return _random_leaf(rng)

    options = ["leaf"]
    if remaining_size >= 2:
        options.append("unary")
    if remaining_size >= 3:
        options.append("binary")
    choice = str(rng.choice(options))

    if choice == "leaf":
        return _random_leaf(rng)
    if choice == "unary":
        op = str(rng.choice(_UNARY_NAMES))
        child = _grow(rng, remaining_depth=remaining_depth - 1, remaining_size=remaining_size - 1)
        return UnaryNode(op=op, child=child)

    op = str(rng.choice(_BINARY_NAMES))
    high = remaining_size - 1  # exclusive upper bound for rng.integers
    left_budget = int(rng.integers(1, high)) if high > 1 else 1
    right_budget = remaining_size - 1 - left_budget
    left = _grow(rng, remaining_depth=remaining_depth - 1, remaining_size=left_budget)
    right = _grow(rng, remaining_depth=remaining_depth - 1, remaining_size=right_budget)
    return BinaryNode(op=op, left=left, right=right)


def random_expression_tree(
    rng: np.random.Generator,
    *,
    max_depth: int = MAX_TREE_DEPTH,
    max_size: int = MAX_NODE_COUNT,
) -> ExpressionNode:
    """A random tree within ``[1, max_depth]`` depth and ``[1, max_size]`` size.

    Every node ``_grow`` returns is itself constructed through
    ``expression_trees.py``'s dataclasses, so the belt-and-suspenders budget
    bookkeeping here is backed by the hard, construction-time enforcement
    those dataclasses already do (see that module's docstring) -- a bug in
    this function's budget arithmetic would raise ``ValueError`` at the
    offending constructor call, not silently produce an oversized tree.
    """
    if not 1 <= max_depth <= MAX_TREE_DEPTH:
        raise ValueError(f"max_depth must be in [1, {MAX_TREE_DEPTH}]")
    if not 1 <= max_size <= MAX_NODE_COUNT:
        raise ValueError(f"max_size must be in [1, {MAX_NODE_COUNT}]")
    return _grow(rng, remaining_depth=max_depth, remaining_size=max_size)


# ---------------------------------------------------------------------------
# Structural helpers: enumerate/replace subtrees by path, for mutation and
# crossover. Trees are immutable, so "replace a subtree" means rebuilding
# every ancestor on the path from the root -- which re-runs each ancestor's
# ``__post_init__`` depth/size validation on the way back up.
# ---------------------------------------------------------------------------

_Path = tuple[str, ...]


def _enumerate_positions(node: ExpressionNode, prefix: _Path = ()) -> list[_Path]:
    positions = [prefix]
    if isinstance(node, UnaryNode):
        positions.extend(_enumerate_positions(node.child, (*prefix, "child")))
    elif isinstance(node, BinaryNode):
        positions.extend(_enumerate_positions(node.left, (*prefix, "left")))
        positions.extend(_enumerate_positions(node.right, (*prefix, "right")))
    return positions


def _get_subtree(node: ExpressionNode, path: _Path) -> ExpressionNode:
    current: ExpressionNode = node
    for step in path:
        current = getattr(current, step)
    return current


def _replace_subtree(
    node: ExpressionNode, path: _Path, replacement: ExpressionNode
) -> ExpressionNode:
    if not path:
        return replacement
    step, rest = path[0], path[1:]
    if isinstance(node, UnaryNode):
        if step != "child":
            raise ValueError(f"invalid path step {step!r} for UnaryNode")
        return UnaryNode(op=node.op, child=_replace_subtree(node.child, rest, replacement))
    if isinstance(node, BinaryNode):
        if step == "left":
            return BinaryNode(
                op=node.op, left=_replace_subtree(node.left, rest, replacement), right=node.right
            )
        if step == "right":
            return BinaryNode(
                op=node.op, left=node.left, right=_replace_subtree(node.right, rest, replacement)
            )
        raise ValueError(f"invalid path step {step!r} for BinaryNode")
    raise ValueError(f"cannot descend into a leaf node at path step {step!r}")


def mutate_tree(
    node: ExpressionNode, rng: np.random.Generator, *, max_retries: int = 8
) -> ExpressionNode:
    """Subtree-replacement mutation.

    Picks a random position in ``node``, computes exactly how much
    depth/size budget is left at that position (``MAX_TREE_DEPTH``/
    ``MAX_NODE_COUNT`` minus what the rest of the tree already uses), and
    grows a fresh replacement sized to fit. Retried deterministically (same
    ``rng`` draws consumed either way) against redrawn positions if a
    replacement would not fit; returns ``node`` unchanged after
    ``max_retries`` failed attempts, which is expected to be rare given the
    budget is computed to fit by construction.
    """
    positions = _enumerate_positions(node)
    total_size = node.size
    for _attempt in range(max_retries):
        path = positions[int(rng.integers(0, len(positions)))]
        target = _get_subtree(node, path)
        remaining_depth = MAX_TREE_DEPTH - len(path)
        remaining_size = MAX_NODE_COUNT - (total_size - target.size)
        if remaining_depth < 1 or remaining_size < 1:
            continue
        replacement = _grow(rng, remaining_depth=remaining_depth, remaining_size=remaining_size)
        try:
            return _replace_subtree(node, path, replacement)
        except ValueError:
            continue
    return node


def crossover_trees(
    left_parent: ExpressionNode,
    right_parent: ExpressionNode,
    rng: np.random.Generator,
    *,
    max_retries: int = 8,
) -> ExpressionNode:
    """Subtree-swap crossover: graft a random subtree of ``right_parent`` onto
    a random position of ``left_parent``.

    Retried deterministically against freshly redrawn cut points until the
    graft respects ``MAX_TREE_DEPTH``/``MAX_NODE_COUNT``; returns
    ``left_parent`` unchanged if no compatible pair of cut points is found
    within ``max_retries`` attempts. That fallback is expected and correct,
    not a bug: two parents near the size/depth ceiling can have genuinely no
    legal graft point.
    """
    positions_left = _enumerate_positions(left_parent)
    positions_right = _enumerate_positions(right_parent)
    total_size_left = left_parent.size
    for _attempt in range(max_retries):
        path_left = positions_left[int(rng.integers(0, len(positions_left)))]
        path_right = positions_right[int(rng.integers(0, len(positions_right)))]
        target = _get_subtree(left_parent, path_left)
        graft = _get_subtree(right_parent, path_right)
        remaining_depth = MAX_TREE_DEPTH - len(path_left)
        remaining_size = MAX_NODE_COUNT - (total_size_left - target.size)
        if graft.depth > remaining_depth or graft.size > remaining_size:
            continue
        try:
            return _replace_subtree(left_parent, path_left, graft)
        except ValueError:
            continue
    return left_parent


# ---------------------------------------------------------------------------
# The evolutionary loop itself.
# ---------------------------------------------------------------------------


def run_expression_gp_search(
    frame: pd.DataFrame,
    *,
    raw_signal_fn: Callable[[ExpressionNode], pd.Series],
    benchmark_returns: pd.Series,
    development_start: str,
    development_end: str,
    seed: int,
    population_size: int = DEFAULT_POPULATION_SIZE,
    generation_count: int = DEFAULT_GENERATION_COUNT,
    elite_carry: int = DEFAULT_ELITE_CARRY,
) -> tuple[GpSearchResult, dict[str, ExpressionNode], list[str]]:
    """Evolve ``generation_count`` generations of expression trees.

    ``frame`` is the OHLCV frame every expression is evaluated against (and
    causality-probed against, via ``validate_expression_is_causal``);
    ``raw_signal_fn`` turns one tree into its full-history trading return
    stream (mechanism-specific: execution convention, costs, symbol choice
    -- deliberately left to the caller, exactly as
    ``mechanism_eval.SignalFn`` is elsewhere in this package).

    Returns ``(report, all_individuals, final_elite_ids)`` -- see module
    docstring for what each of the latter two is for.

    Raises ``ValueError`` if fewer than two distinct causal individuals can
    be generated for the initial population, or if any generation's entire
    population is degenerate on the development window (every candidate's
    development-only Sharpe non-finite) -- both are the same failure modes
    ``layered_search.run_layered_search``/``nested_walk_forward`` already
    raise on, surfaced here at the point they actually occur.
    """
    if population_size < 2:
        raise ValueError("population_size must be at least 2")
    if generation_count < 1:
        raise ValueError("generation_count must be at least 1")
    if elite_carry < 1:
        raise ValueError("elite_carry must be at least 1")

    rng = np.random.default_rng(seed)
    all_individuals: dict[str, ExpressionNode] = {}
    rejected_lookahead_count = 0
    rejected_degenerate_count = 0
    development_window_start = pd.Timestamp(development_start)
    development_window_end = pd.Timestamp(development_end)
    # Elites are carried into later generations verbatim (unchanged tree,
    # unchanged id), so without this cache ``_development_view`` would
    # re-run ``raw_signal_fn``'s O(rows) execution-simulation loop for the
    # same individual once per generation it survives -- wasted work that
    # scales with ``generation_count``, not with how many *new* individuals
    # that generation actually introduced.
    raw_signal_cache: dict[str, pd.Series] = {}

    def _raw_signal(candidate_id: str, tree: ExpressionNode) -> pd.Series:
        cached = raw_signal_cache.get(candidate_id)
        if cached is None:
            cached = raw_signal_fn(tree)
            raw_signal_cache[candidate_id] = cached
        return cached

    def _register(tree: ExpressionNode) -> str:
        formula = formula_string(tree)
        candidate_id = expression_id(formula)
        all_individuals.setdefault(candidate_id, tree)
        return candidate_id

    def _try_admit(tree: ExpressionNode) -> str | None:
        """Gate every candidate through both plan section 6.3's causal check
        and the (real, not hypothetical -- see ``DegenerateExpressionError``)
        informativeness check before it is allowed into the population.

        A degenerate expression (e.g. one built entirely from constants, or
        one that reduces to a numerically constant score given this data's
        sign pattern) is rejected the same way a lookahead violation is:
        never silently admitted, never warned about, just excluded and
        counted.
        """
        nonlocal rejected_lookahead_count, rejected_degenerate_count
        try:
            validate_expression_is_causal(tree, frame)
        except LookaheadError:
            rejected_lookahead_count += 1
            return None
        try:
            validate_expression_is_informative(tree, frame)
        except DegenerateExpressionError:
            rejected_degenerate_count += 1
            return None
        return _register(tree)

    def _fresh_population_member(existing: set[str]) -> str | None:
        for _ in range(_MAX_ATTEMPTS_PER_SLOT):
            tree = random_expression_tree(rng)
            candidate_id = _try_admit(tree)
            if candidate_id is not None and candidate_id not in existing:
                return candidate_id
        return None

    def _development_view(candidate_id: str, tree: ExpressionNode) -> DevelopmentView | None:
        raw = _raw_signal(candidate_id, tree)
        # A degenerate expression (e.g. a rolling z-score over a
        # zero-variance branch) can legitimately produce an all-NaN,
        # zero-length return stream -- ``raw_signal_fn`` implementations are
        # expected to return an *empty* Series rather than raise for that
        # case (mirroring how ``nested_walk_forward`` treats an empty
        # per-fold slice). Checked before slicing because an empty Series
        # built without an explicit tz can otherwise fail tz-aware slice
        # comparisons for reasons unrelated to whether it overlaps the
        # development window at all.
        if raw.empty:
            return None
        window = raw.loc[development_window_start:development_window_end]
        if window.empty:
            return None
        aligned_benchmark = benchmark_returns.reindex(window.index)
        if aligned_benchmark.isna().any():
            return None
        return DevelopmentView(
            candidate_id=candidate_id,
            mechanism_family=MECHANISM_FAMILY,
            param_vector={"expression_id": candidate_id, "formula": formula_string(tree)},
            generation=0,
            parent_id=None,
            development_returns=window.tolist(),
            development_benchmark_returns=aligned_benchmark.tolist(),
        )

    # --- Generation 0: pure random population. ------------------------------
    population_ids: list[str] = []
    seen: set[str] = set()
    while len(population_ids) < population_size:
        candidate_id = _fresh_population_member(seen)
        if candidate_id is None:
            break
        population_ids.append(candidate_id)
        seen.add(candidate_id)
    if len(population_ids) < 2:
        raise ValueError(
            "expression GP: could not generate an initial population of at least two "
            "distinct causal candidates"
        )

    generations: list[GpGenerationSummary] = []
    elite_ids: list[str] = population_ids

    for generation in range(generation_count):
        views: list[DevelopmentView] = []
        for candidate_id in population_ids:
            view = _development_view(candidate_id, all_individuals[candidate_id])
            if view is not None:
                views.append(view)
        if not views:
            raise ValueError(
                f"generation {generation}: no candidate has an observation in the "
                f"development window [{development_start}, {development_end}]"
            )
        qualities, survivors = select_layer1_survivors(views, quality_fn=development_quality)
        if not survivors:
            raise ValueError(
                f"generation {generation}: every candidate was degenerate on the "
                "development window (zero Layer 1 survivors)"
            )
        archive = build_layer2_archive(
            survivors, qualities, campaign_id=f"expr-gp-seed{seed}-gen{generation:02d}"
        )
        elite_ids = sorted({elite.candidate.candidate_id for elite in archive.elites})
        generations.append(
            GpGenerationSummary(
                generation=generation,
                population_size=len(population_ids),
                layer1_survivor_count=len(survivors),
                layer2_elite_count=len(elite_ids),
                elite_expression_ids=list(elite_ids),
                elite_formulas=[formula_string(all_individuals[eid]) for eid in elite_ids],
            )
        )

        if generation == generation_count - 1:
            break

        # --- Breed the next generation: elites carried verbatim, the rest
        # filled by crossover/mutation of elites (falling back to a fresh
        # random individual whenever breeding stalls on duplicates or
        # non-causal offspring).
        next_ids: list[str] = list(elite_ids[:elite_carry])
        next_seen: set[str] = set(next_ids)
        breed_attempts = 0
        max_breed_attempts = population_size * _MAX_ATTEMPTS_PER_SLOT
        while len(next_ids) < population_size and breed_attempts < max_breed_attempts:
            breed_attempts += 1
            parent_a = all_individuals[str(rng.choice(elite_ids))]
            if len(elite_ids) > 1 and rng.random() < 0.5:
                parent_b = all_individuals[str(rng.choice(elite_ids))]
                child = crossover_trees(parent_a, parent_b, rng)
            else:
                child = mutate_tree(parent_a, rng)
            candidate_id = _try_admit(child)
            if candidate_id is not None and candidate_id not in next_seen:
                next_ids.append(candidate_id)
                next_seen.add(candidate_id)
        while len(next_ids) < population_size:
            candidate_id = _fresh_population_member(next_seen)
            if candidate_id is None:
                break
            next_ids.append(candidate_id)
            next_seen.add(candidate_id)
        if len(next_ids) < 2:
            raise ValueError(
                f"generation {generation}: breeding could not produce a viable next population"
            )
        population_ids = next_ids

    report = GpSearchResult(
        seed=seed,
        population_size=population_size,
        generation_count=generation_count,
        elite_carry=elite_carry,
        total_individuals_evaluated=len(all_individuals),
        rejected_lookahead_count=rejected_lookahead_count,
        rejected_degenerate_count=rejected_degenerate_count,
        development_start=development_start,
        development_end=development_end,
        generations=generations,
        final_elite_expression_ids=list(elite_ids),
        final_elite_formulas=[formula_string(all_individuals[eid]) for eid in elite_ids],
    )
    return report, all_individuals, elite_ids
