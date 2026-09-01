"""Expression-tree (genetic programming) candidates for Work Item P2b.

See ``docs/plan-sip-migration-and-wide-search-2026-09-01.zh.md`` sections
6.1-6.3. An expression tree is a composable formula mapping price/volume
features to a continuous trading score; the sign of the score at session T's
close decides which sleeve (risk-on vs cash-like) is held from T+1's open.

Two structural disciplines are enforced here, by construction, not by
convention:

Depth/node-count limits (plan section 6.2, "GP bloat")
-------------------------------------------------------
Literature on genetic-programming trading rules is consistent: an
unconstrained grammar lets mutation/crossover slowly inflate tree size to
chase in-sample fit, and that fit collapses out of sample (see the module
docstring's source links, mirrored from ``layered_search.py``'s citation
style: https://arxiv.org/abs/2412.00896,
https://arxiv.org/html/2502.16789v2, https://arxiv.org/pdf/2505.11122).
``MAX_TREE_DEPTH`` (4) and ``MAX_NODE_COUNT`` (12) are enforced inside
:meth:`UnaryNode.__post_init__`/:meth:`BinaryNode.__post_init__`, which
compute the resulting subtree's depth/size from its already-constructed
children and raise ``ValueError`` immediately if either limit would be
exceeded. Because every composite node re-validates on construction, this
holds recursively for any tree built bottom-up (fresh generation), and for
any tree rebuilt top-down after a subtree replacement (mutation/crossover in
``expression_tree_search.py``): there is no code path that produces an
in-memory :class:`ExpressionNode` outside the declared limits, so "build an
over-limit tree" is not a runtime check that can be skipped -- it is a
``ValueError`` at the constructor call that would have created it.

Causality (plan section 6.3)
-------------------------------------------------------
Every terminal and operator below is a RATIO, RETURN, or ROLLING STATISTIC OF
RETURNS -- never a raw OHLC *level*. This is deliberate, not incidental: SIP
daily bars are back-adjusted for splits/dividends (``adjustment=all``), so a
historical price level is not what actually traded on that date (see
``docs/finding-iex-cache-price-adjustment-defect-2026-09-01.zh.md`` section 9
-- BIL shows as 81.74 in 2024 purely from cumulative dividend adjustment,
which makes any ``price > 100``-style absolute-level comparison meaningless
on this data). Ratio and rank features are unaffected by that adjustment (the
plan says so explicitly), so this grammar's *only* entry points into raw
OHLCV data are the eight functions in ``TERMINAL_BUILDERS``, and none of them
returns a level -- so no expression built from this grammar can ever compare
one, structurally, regardless of how deep or how it is mutated.

Every terminal also carries this project's PIT safety-buffer convention (see
``scripts/search_daily_momentum_p2a.py:_momentum_feature``): an extra
``.shift(1)`` beyond whatever lag the transform itself already has, so the
value read at session T's close was fully known at T-1's close -- never at
T's own bar. Internal (non-terminal) operators do not need a further shift of
their own; a backward-looking function of an already-causal input stays
causal by structural induction:

* every unary rolling operator (``roll_mean_5``, ``roll_zscore_20``, ...) at
  position t reads only ``x[t-w+1 .. t]`` for some fixed trailing window w
  (``pandas.Series.rolling`` without ``center=True``); if ``x`` itself is
  causal (each ``x[s]`` depends only on raw data at or before ``s-1``), the
  composed value at t depends only on raw data at or before ``t-1``;
* every binary operator (``add``, ``gt``, ...) at position t is a pointwise
  function of ``x[t]`` and ``y[t]`` alone, no window at all, so the same
  induction applies trivially.

:func:`validate_expression_is_causal` proves this for a *specific* generated
expression -- not just for the operator catalogue in the abstract -- by
reusing ``layered_search.assert_causal_transform`` verbatim (plan section
6.3: "do not write a second lookahead checker"). Every generated expression
must pass it before ``expression_tree_search.py`` allows it to become a
candidate; a failure is rejected, never warned about.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from open_composer.research.kernel.datamodel import ResearchDataModel
from open_composer.research.kernel.layered_search import assert_causal_transform

#: Plan section 6.2 hard limits. Enforced at construction (see module
#: docstring), not merely checked after the fact.
MAX_TREE_DEPTH = 4
MAX_NODE_COUNT = 12

#: Constants are drawn from a small, bounded range -- an open continuous
#: range would let mutation slowly walk a threshold toward whatever fits one
#: fold's noise, which is exactly the "GP bloat" failure mode this module is
#: built to avoid, just applied to leaf values instead of tree shape.
CONSTANT_MIN = -1.0
CONSTANT_MAX = 1.0
#: The discrete grid ``expression_tree_search.py``'s generator draws from.
#: Declared here (not derived from any run's data) so it cannot become a
#: selection leak.
CONSTANT_CHOICES: tuple[float, ...] = (
    -0.5,
    -0.2,
    -0.1,
    -0.05,
    -0.02,
    -0.01,
    0.0,
    0.01,
    0.02,
    0.05,
    0.1,
    0.2,
    0.5,
)

REQUIRED_FRAME_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")


def _require_frame(frame: pd.DataFrame) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    missing = [column for column in REQUIRED_FRAME_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"frame is missing required OHLCV column(s): {missing}")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("frame must be indexed by a DatetimeIndex")


# ---------------------------------------------------------------------------
# Terminals -- see module docstring for the causality + no-absolute-level
# discipline every one of these must satisfy.
# ---------------------------------------------------------------------------


def _terminal_ret1(frame: pd.DataFrame) -> pd.Series:
    """1-session lagged return: ``ret1[t] = close[t-1]/close[t-2] - 1``."""
    return frame["close"].pct_change(1).shift(1)


def _terminal_ret5(frame: pd.DataFrame) -> pd.Series:
    """5-session lagged trailing return."""
    return frame["close"].pct_change(5).shift(1)


def _terminal_ret20(frame: pd.DataFrame) -> pd.Series:
    """20-session lagged trailing return."""
    return frame["close"].pct_change(20).shift(1)


def _terminal_vol10(frame: pd.DataFrame) -> pd.Series:
    """Trailing 10-session realized volatility of daily returns."""
    return frame["close"].pct_change().rolling(10, min_periods=10).std().shift(1)


def _terminal_vol20(frame: pd.DataFrame) -> pd.Series:
    """Trailing 20-session realized volatility of daily returns."""
    return frame["close"].pct_change().rolling(20, min_periods=20).std().shift(1)


def _terminal_volchg5(frame: pd.DataFrame) -> pd.Series:
    """5-session relative change in traded volume (a ratio, not a level)."""
    return frame["volume"].pct_change(5).shift(1)


def _terminal_hl_range(frame: pd.DataFrame) -> pd.Series:
    """Daily ``(high - low) / close`` range: a ratio, never a level."""
    return ((frame["high"] - frame["low"]) / frame["close"]).shift(1)


def _terminal_oc_gap(frame: pd.DataFrame) -> pd.Series:
    """Overnight gap ``open / prior_close - 1``: a ratio, never a level."""
    return (frame["open"] / frame["close"].shift(1) - 1.0).shift(1)


TERMINAL_BUILDERS: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    "ret1": _terminal_ret1,
    "ret5": _terminal_ret5,
    "ret20": _terminal_ret20,
    "vol10": _terminal_vol10,
    "vol20": _terminal_vol20,
    "volchg5": _terminal_volchg5,
    "hl_range": _terminal_hl_range,
    "oc_gap": _terminal_oc_gap,
}


# ---------------------------------------------------------------------------
# Unary operators -- each is a backward-looking function of one input Series.
# ---------------------------------------------------------------------------


def _op_neg(x: pd.Series) -> pd.Series:
    return -x


def _op_abs(x: pd.Series) -> pd.Series:
    return x.abs()


def _op_sign(x: pd.Series) -> pd.Series:
    return np.sign(x)


def _op_roll_mean_5(x: pd.Series) -> pd.Series:
    return x.rolling(5, min_periods=5).mean()


def _op_roll_mean_20(x: pd.Series) -> pd.Series:
    return x.rolling(20, min_periods=20).mean()


def _op_roll_std_10(x: pd.Series) -> pd.Series:
    return x.rolling(10, min_periods=10).std()


def _op_roll_zscore_20(x: pd.Series) -> pd.Series:
    """Trailing 20-bar z-score -- **not** a full-sample z-score.

    ``x.rolling(20).mean()``/``.std()`` at position t read only
    ``x[t-19 .. t]``; truncating the series after t cannot change either
    value, which is exactly the invariance ``assert_causal_transform``
    probes for. Contrast with the pattern
    ``test_kernel_layered_search.py::test_full_sample_zscore_is_rejected_as_lookahead``
    rejects: ``(series - series.mean()) / series.std()``, which reads the
    *whole* series at every position.
    """
    mean = x.rolling(20, min_periods=20).mean()
    std = x.rolling(20, min_periods=20).std()
    safe_std = std.where(std.abs() > 1e-12)
    return (x - mean) / safe_std


def _rolling_rank_of_last(window: np.ndarray) -> float:
    last = window[-1]
    if not np.isfinite(last):
        return float("nan")
    finite = window[np.isfinite(window)]
    if finite.size == 0:
        return float("nan")
    return float(np.mean(finite <= last))


def _op_roll_rank_20(x: pd.Series) -> pd.Series:
    """Trailing 20-bar percentile rank of the current value -- **not** a
    full-sample quantile. Only ``x[t-19 .. t]`` is ever read to produce the
    value at t.
    """
    return x.rolling(20, min_periods=20).apply(_rolling_rank_of_last, raw=True)


def _op_delta_5(x: pd.Series) -> pd.Series:
    """Trailing difference: ``x[t] - x[t-5]``."""
    return x - x.shift(5)


UNARY_OPS: dict[str, Callable[[pd.Series], pd.Series]] = {
    "neg": _op_neg,
    "abs": _op_abs,
    "sign": _op_sign,
    "roll_mean_5": _op_roll_mean_5,
    "roll_mean_20": _op_roll_mean_20,
    "roll_std_10": _op_roll_std_10,
    "roll_zscore_20": _op_roll_zscore_20,
    "roll_rank_20": _op_roll_rank_20,
    "delta_5": _op_delta_5,
}


# ---------------------------------------------------------------------------
# Binary operators -- each is a pointwise (no-window) function of two input
# Series aligned on the same timestamp, so causality is trivially preserved
# by structural induction (see module docstring).
# ---------------------------------------------------------------------------


def _op_add(x: pd.Series, y: pd.Series) -> pd.Series:
    return x + y


def _op_sub(x: pd.Series, y: pd.Series) -> pd.Series:
    return x - y


def _op_mul(x: pd.Series, y: pd.Series) -> pd.Series:
    return x * y


def _op_div_safe(x: pd.Series, y: pd.Series) -> pd.Series:
    """Protected division: ``|y| < 1e-6`` is floored to ``+-1e-6`` first."""
    sign = np.sign(y).replace(0.0, 1.0)
    safe_y = y.where(y.abs() > 1e-6, sign * 1e-6)
    return x / safe_y


def _op_min2(x: pd.Series, y: pd.Series) -> pd.Series:
    return np.minimum(x, y)


def _op_max2(x: pd.Series, y: pd.Series) -> pd.Series:
    return np.maximum(x, y)


def _op_gt(x: pd.Series, y: pd.Series) -> pd.Series:
    """``+1.0`` if ``x > y`` else ``-1.0``.

    Compares two engineered ratio/return branches, pointwise, at the same
    timestamp -- never a price-level comparison, because no terminal in this
    grammar ever produces a level (see module docstring).
    """
    return (x > y).astype(float) * 2.0 - 1.0


BINARY_OPS: dict[str, Callable[[pd.Series, pd.Series], pd.Series]] = {
    "add": _op_add,
    "sub": _op_sub,
    "mul": _op_mul,
    "div_safe": _op_div_safe,
    "min2": _op_min2,
    "max2": _op_max2,
    "gt": _op_gt,
}


def _assert_within_limits(*, depth: int, size: int) -> None:
    if depth > MAX_TREE_DEPTH:
        raise ValueError(f"expression tree depth {depth} exceeds MAX_TREE_DEPTH={MAX_TREE_DEPTH}")
    if size > MAX_NODE_COUNT:
        raise ValueError(
            f"expression tree node count {size} exceeds MAX_NODE_COUNT={MAX_NODE_COUNT}"
        )


@dataclass(frozen=True)
class TerminalNode(ResearchDataModel):
    """A leaf referencing one causal, price-level-free feature by name."""

    name: str

    def __post_init__(self) -> None:
        if self.name not in TERMINAL_BUILDERS:
            raise ValueError(f"unknown terminal: {self.name!r}")

    @property
    def depth(self) -> int:
        return 1

    @property
    def size(self) -> int:
        return 1


@dataclass(frozen=True)
class ConstantNode(ResearchDataModel):
    """A leaf holding a bounded numeric literal (see ``CONSTANT_MIN/MAX``)."""

    value: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise ValueError("ConstantNode.value must be finite")
        if not (CONSTANT_MIN <= self.value <= CONSTANT_MAX):
            raise ValueError(
                f"ConstantNode.value {self.value!r} outside declared bounds "
                f"[{CONSTANT_MIN}, {CONSTANT_MAX}]"
            )

    @property
    def depth(self) -> int:
        return 1

    @property
    def size(self) -> int:
        return 1


@dataclass(frozen=True)
class UnaryNode(ResearchDataModel):
    """One operator from ``UNARY_OPS`` applied to a child subtree."""

    op: str
    child: ExpressionNode

    def __post_init__(self) -> None:
        if self.op not in UNARY_OPS:
            raise ValueError(f"unknown unary operator: {self.op!r}")
        _assert_within_limits(depth=self.depth, size=self.size)

    @property
    def depth(self) -> int:
        return 1 + self.child.depth

    @property
    def size(self) -> int:
        return 1 + self.child.size


@dataclass(frozen=True)
class BinaryNode(ResearchDataModel):
    """One operator from ``BINARY_OPS`` applied to two child subtrees."""

    op: str
    left: ExpressionNode
    right: ExpressionNode

    def __post_init__(self) -> None:
        if self.op not in BINARY_OPS:
            raise ValueError(f"unknown binary operator: {self.op!r}")
        _assert_within_limits(depth=self.depth, size=self.size)

    @property
    def depth(self) -> int:
        return 1 + max(self.left.depth, self.right.depth)

    @property
    def size(self) -> int:
        return 1 + self.left.size + self.right.size


#: The four concrete node types an expression tree can be built from.
ExpressionNode = TerminalNode | ConstantNode | UnaryNode | BinaryNode


def evaluate(node: ExpressionNode, frame: pd.DataFrame) -> pd.Series:
    """Recursively evaluate ``node`` against ``frame``'s OHLCV columns.

    ``frame`` must have the columns in :data:`REQUIRED_FRAME_COLUMNS` and be
    indexed by a sorted ``DatetimeIndex``; every terminal reads from it, so
    checking the contract once here (rather than in each terminal) keeps the
    error message actionable.
    """
    _require_frame(frame)
    return _evaluate(node, frame)


def _evaluate(node: ExpressionNode, frame: pd.DataFrame) -> pd.Series:
    if isinstance(node, TerminalNode):
        return TERMINAL_BUILDERS[node.name](frame)
    if isinstance(node, ConstantNode):
        return pd.Series(node.value, index=frame.index, dtype=float)
    if isinstance(node, UnaryNode):
        return UNARY_OPS[node.op](_evaluate(node.child, frame))
    if isinstance(node, BinaryNode):
        return BINARY_OPS[node.op](_evaluate(node.left, frame), _evaluate(node.right, frame))
    raise TypeError(f"unknown expression node type: {type(node)!r}")  # pragma: no cover


def formula_string(node: ExpressionNode) -> str:
    """A deterministic, human-readable rendering of ``node``.

    Used both for reporting (per-fold selected expression, expression
    stability across folds) and as the input to
    :func:`expression_tree_search._expression_id`'s content hash -- two
    structurally identical trees always render to the same string.
    """
    if isinstance(node, TerminalNode):
        return node.name
    if isinstance(node, ConstantNode):
        return f"{node.value:g}"
    if isinstance(node, UnaryNode):
        return f"{node.op}({formula_string(node.child)})"
    if isinstance(node, BinaryNode):
        return f"{node.op}({formula_string(node.left)}, {formula_string(node.right)})"
    raise TypeError(f"unknown expression node type: {type(node)!r}")  # pragma: no cover


def validate_expression_is_causal(
    node: ExpressionNode, frame: pd.DataFrame, *, probe_count: int = 5
) -> None:
    """Plan section 6.3: every generated expression must pass this before it
    is allowed to become a candidate. Raises
    ``layered_search.LookaheadError`` -- callers must let it propagate and
    drop the candidate; catching it to log a warning and proceeding anyway is
    exactly what the plan forbids ("reject, do not warn").

    Reuses ``layered_search.assert_causal_transform`` verbatim rather than
    writing a second lookahead checker (plan section 6.3's explicit
    instruction). That function's contract is generic over any
    ``Callable`` probed by truncating its input and re-running it; nothing in
    its implementation actually requires the input to be a single-column
    ``pandas.Series`` -- it only ever calls ``.index``, ``.iloc``, ``len()``,
    all of which a multi-column ``pandas.DataFrame`` supports identically
    (verified directly against the CPython/pandas objects, not assumed).
    Passing the whole OHLCV frame here (rather than one column) is required
    because an expression can read several raw columns at once (e.g.
    ``hl_range`` reads high/low/close) -- a single-Series probe could not
    exercise the whole tree.
    """
    _require_frame(frame)
    assert_causal_transform(
        lambda probed_frame: evaluate(node, probed_frame),
        frame,
        probe_count=probe_count,
    )


class DegenerateExpressionError(ValueError):
    """Raised when an expression's score carries no market-timing
    information on the data it was checked against.

    Three ways this happens, all real (found on real SIP runs, not
    hypothesized) -- see module docstring: "the sign of the score ... decides
    which sleeve is held". Every one of these three makes that decision
    constant, which is degenerate for the same reason an all-NaN score is
    (no information) and -- worse, specific to this search -- gives an
    "always hold the lower-volatility sleeve" candidate a structural
    advantage under ``layered_search.development_quality``'s *raw* (not
    excess-of-benchmark) Sharpe: a cash-like sleeve has very low variance and
    a small positive drift, so a trivial constant-decision expression can
    look like the best candidate in the whole population on that metric
    alone, crowding out every genuinely data-dependent one.

    1. An expression built entirely from ``ConstantNode`` leaves reduces to a
       fixed number regardless of market data, e.g.
       ``mul(roll_mean_5(roll_mean_20(0.2)), neg(max2(-0.02, 0.05)))`` is
       ``-0.01`` on every date, forever.
    2. An expression that *does* reference a terminal can still be
       numerically constant given the sign pattern of the data it reads,
       e.g. ``sign(vol20)`` is ``+1.0`` on every date, because a rolling
       standard deviation is never negative.
    3. An expression can have genuine, non-trivial numeric variance and
       *still* never cross zero, e.g.
       ``min2(delta_5(ret20), add(vol20, -0.55))``: the second branch is
       real QQQ daily-return volatility (a few percent) minus 0.55, so it is
       always deeply negative, and ``min2`` of that against anything rarely
       -- in this project's real 2016-2026 SIP history, never -- exceeds
       zero. The score genuinely moves; the *decision* it drives never does.

    Rejecting all three at admission time (like a lookahead violation) keeps
    the search honest about what it actually explored.
    """


def validate_expression_is_informative(
    node: ExpressionNode, frame: pd.DataFrame, *, min_std: float = 1e-9
) -> None:
    """Reject an expression whose score carries no market-timing signal.

    Checked against the real evaluated output, not the tree's symbolic
    structure, so it catches a provably-constant tree (no terminal anywhere),
    a tree that is numerically constant given this data's sign pattern, and
    -- the general case -- a tree whose score never crosses zero even though
    it does have real variance (see :class:`DegenerateExpressionError`).
    """
    _require_frame(frame)
    output = evaluate(node, frame)
    values = output.to_numpy(dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise DegenerateExpressionError("expression has no finite observation on this data")
    if float(np.std(finite)) < min_std:
        raise DegenerateExpressionError(
            "expression score has no meaningful variance (a degenerate/constant signal)"
        )
    # This project's grammar-level convention (module docstring): sign(score)
    # decides the sleeve. A score that never crosses zero drives a constant
    # trading decision regardless of how much the score itself fluctuates.
    if not bool(np.any(finite > 0.0)) or not bool(np.any(finite <= 0.0)):
        raise DegenerateExpressionError(
            "expression score never crosses zero (a constant trading decision)"
        )
