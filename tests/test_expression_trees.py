"""Expression-tree grammar tests (Work Item P2b, plan sections 6.2/6.3).

Three things are load-bearing here and get their own section:

* structural limits (depth <= 4, node count <= 12) are enforced at
  construction, not merely checked after the fact;
* the restricted operator/terminal catalogue is a declared, tested set (a
  regression guard against silently widening the grammar);
* :func:`validate_expression_is_causal` actually rejects a contaminated
  expression, and does not falsely reject a legitimate one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel import expression_trees
from open_composer.research.kernel.expression_trees import (
    BINARY_OPS,
    CONSTANT_MAX,
    CONSTANT_MIN,
    MAX_NODE_COUNT,
    MAX_TREE_DEPTH,
    TERMINAL_BUILDERS,
    UNARY_OPS,
    BinaryNode,
    ConstantNode,
    DegenerateExpressionError,
    TerminalNode,
    UnaryNode,
    evaluate,
    formula_string,
    validate_expression_is_causal,
    validate_expression_is_informative,
)
from open_composer.research.kernel.layered_search import LookaheadError

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _synthetic_frame(*, n: int = 300, seed: int = 0) -> pd.DataFrame:
    index = pd.bdate_range("2020-01-02", periods=n, tz="UTC")
    rng = np.random.default_rng(seed)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.01, n))
    open_ = close * (1.0 + rng.normal(0.0, 0.001, n))
    high = np.maximum(close, open_) * (1.0 + np.abs(rng.normal(0.0, 0.003, n)))
    low = np.minimum(close, open_) * (1.0 - np.abs(rng.normal(0.0, 0.003, n)))
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


def _full_binary_tree(depth: int) -> BinaryNode | TerminalNode:
    """A full (every internal node has two children) binary tree of the
    given node-depth, built from ``add``/``ret1`` -- used to probe the node
    count limit independently of the depth limit."""
    if depth == 1:
        return TerminalNode(name="ret1")
    return BinaryNode(
        op="add", left=_full_binary_tree(depth - 1), right=_full_binary_tree(depth - 1)
    )


# ---------------------------------------------------------------------------
# Structural limits: enforced at construction (plan section 6.2)
# ---------------------------------------------------------------------------


def test_terminal_node_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown terminal"):
        TerminalNode(name="close_level_does_not_exist")


def test_constant_node_rejects_out_of_bounds_value() -> None:
    with pytest.raises(ValueError, match="outside declared bounds"):
        ConstantNode(value=CONSTANT_MAX + 0.5)
    with pytest.raises(ValueError, match="outside declared bounds"):
        ConstantNode(value=CONSTANT_MIN - 0.5)


def test_constant_node_rejects_non_finite_value() -> None:
    with pytest.raises(ValueError, match="finite"):
        ConstantNode(value=float("nan"))
    with pytest.raises(ValueError, match="finite"):
        ConstantNode(value=float("inf"))


def test_depth_at_the_limit_is_constructible() -> None:
    tree = UnaryNode(
        op="neg", child=UnaryNode(op="neg", child=UnaryNode(op="neg", child=TerminalNode("ret1")))
    )
    assert tree.depth == MAX_TREE_DEPTH


def test_depth_one_past_the_limit_cannot_be_constructed() -> None:
    """An over-limit tree must be *impossible to build*: the exact
    constructor call that would exceed ``MAX_TREE_DEPTH`` raises, rather than
    succeeding and being caught by some later validation pass."""
    one_below_limit = UnaryNode(
        op="neg", child=UnaryNode(op="neg", child=UnaryNode(op="neg", child=TerminalNode("ret1")))
    )
    assert one_below_limit.depth == MAX_TREE_DEPTH
    with pytest.raises(ValueError, match="exceeds MAX_TREE_DEPTH"):
        UnaryNode(op="neg", child=one_below_limit)


def test_node_count_at_the_limit_is_constructible() -> None:
    # A full binary tree of node-depth 3 has 2**3 - 1 = 7 nodes; grafting one
    # more depth-2 (3-node) subtree under a fresh root gives 1 + 7 + 3 = 11.
    left = _full_binary_tree(3)
    right = _full_binary_tree(2)
    tree = BinaryNode(op="add", left=left, right=right)
    assert tree.size == 11
    assert tree.size <= MAX_NODE_COUNT
    assert tree.depth <= MAX_TREE_DEPTH


def test_node_count_one_past_the_limit_cannot_be_constructed() -> None:
    """Depth stays legal (4) while size alone crosses the ceiling -- proving
    the two limits are independently enforced, not just depth standing in
    for both."""
    left = _full_binary_tree(3)  # 7 nodes, depth 3
    right = _full_binary_tree(3)  # 7 nodes, depth 3
    assert left.depth == 3
    with pytest.raises(ValueError, match="exceeds MAX_NODE_COUNT"):
        BinaryNode(op="add", left=left, right=right)  # would be 15 nodes, depth 4


def test_unknown_operator_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown unary operator"):
        UnaryNode(op="does_not_exist", child=TerminalNode("ret1"))
    with pytest.raises(ValueError, match="unknown binary operator"):
        BinaryNode(op="does_not_exist", left=TerminalNode("ret1"), right=TerminalNode("ret5"))


# ---------------------------------------------------------------------------
# The restricted operator/terminal catalogue is a declared, tested set.
# ---------------------------------------------------------------------------


def test_terminal_catalogue_is_the_declared_restricted_set() -> None:
    assert set(TERMINAL_BUILDERS) == {
        "ret1",
        "ret5",
        "ret20",
        "vol10",
        "vol20",
        "volchg5",
        "hl_range",
        "oc_gap",
    }


def test_operator_catalogues_are_the_declared_restricted_sets() -> None:
    assert set(UNARY_OPS) == {
        "neg",
        "abs",
        "sign",
        "roll_mean_5",
        "roll_mean_20",
        "roll_std_10",
        "roll_zscore_20",
        "roll_rank_20",
        "delta_5",
    }
    assert set(BINARY_OPS) == {"add", "sub", "mul", "div_safe", "min2", "max2", "gt"}


def test_no_terminal_exposes_a_raw_price_level() -> None:
    """Every terminal must be a ratio/return/rolling-statistic, never a raw
    OHLC level (plan section 6.3's SIP back-adjustment hazard). Proven here
    by construction: feed a frame whose close is a huge, distinctive
    constant level and confirm every terminal's output stays in a small
    range around zero (a level would instead reproduce ~that huge number).
    """
    frame = _synthetic_frame()
    inflated = frame.copy()
    inflated["close"] = 12_345.0
    inflated["open"] = 12_345.0
    inflated["high"] = 12_346.0
    inflated["low"] = 12_344.0
    for name, builder in TERMINAL_BUILDERS.items():
        output = builder(inflated)
        finite = output.dropna()
        assert not finite.empty, name
        assert finite.abs().max() < 10.0, (
            f"terminal {name!r} produced a value near the injected price level; "
            "it may be leaking a raw level rather than a ratio"
        )


# ---------------------------------------------------------------------------
# evaluate / formula_string
# ---------------------------------------------------------------------------


def test_evaluate_matches_manual_composition() -> None:
    frame = _synthetic_frame()
    tree = BinaryNode(
        op="gt",
        left=UnaryNode(op="roll_mean_5", child=TerminalNode("ret1")),
        right=ConstantNode(value=0.0),
    )
    actual = evaluate(tree, frame)
    ret1 = frame["close"].pct_change(1).shift(1)
    expected = (ret1.rolling(5, min_periods=5).mean() > 0.0).astype(float) * 2.0 - 1.0
    pd.testing.assert_series_equal(actual, expected, check_names=False)


def test_formula_string_renders_nested_structure() -> None:
    tree = BinaryNode(
        op="gt",
        left=UnaryNode(op="roll_mean_5", child=TerminalNode("ret1")),
        right=ConstantNode(value=0.0),
    )
    assert formula_string(tree) == "gt(roll_mean_5(ret1), 0)"


def test_evaluate_rejects_a_frame_missing_columns() -> None:
    frame = _synthetic_frame().drop(columns=["volume"])
    with pytest.raises(ValueError, match="missing required OHLCV column"):
        evaluate(TerminalNode("volchg5"), frame)


# ---------------------------------------------------------------------------
# Anti-lookahead integration (plan section 6.3): reject, do not warn.
# ---------------------------------------------------------------------------


def test_legitimate_causal_expressions_are_not_falsely_rejected() -> None:
    frame = _synthetic_frame(n=400)
    legitimate_trees = [
        TerminalNode("ret1"),
        UnaryNode(op="roll_mean_5", child=TerminalNode("ret1")),
        UnaryNode(op="roll_zscore_20", child=TerminalNode("ret5")),
        UnaryNode(op="roll_rank_20", child=TerminalNode("vol20")),
        BinaryNode(
            op="gt",
            left=UnaryNode(op="roll_mean_5", child=TerminalNode("ret1")),
            right=UnaryNode(op="roll_mean_20", child=TerminalNode("ret1")),
        ),
        BinaryNode(
            op="mul",
            left=UnaryNode(op="sign", child=TerminalNode("ret1")),
            right=UnaryNode(op="roll_rank_20", child=TerminalNode("vol10")),
        ),
    ]
    for tree in legitimate_trees:
        validate_expression_is_causal(tree, frame)  # must not raise


def test_contaminated_expression_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Construct an expression that *is* lookahead-contaminated and assert it
    is rejected -- the required regression test for plan section 6.3.

    A fake, test-only unary operator (never part of the real, provably
    causal ``UNARY_OPS`` catalogue) is injected via ``monkeypatch`` so this
    proves the *integration point*
    (``validate_expression_is_causal`` -> ``assert_causal_transform`` over a
    composed tree) actually catches contamination introduced anywhere in the
    tree, without permanently widening the production operator set.
    """
    frame = _synthetic_frame(n=400)
    monkeypatch.setitem(
        expression_trees.UNARY_OPS,
        "future_leak_test_only",
        lambda x: x.shift(-3),  # reads 3 sessions into the future: not causal
    )
    contaminated = UnaryNode(op="future_leak_test_only", child=TerminalNode("ret1"))
    with pytest.raises(LookaheadError):
        validate_expression_is_causal(contaminated, frame)


def test_contaminated_expression_deep_in_the_tree_is_still_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The contamination need not be at the root to be caught."""
    frame = _synthetic_frame(n=400)
    monkeypatch.setitem(
        expression_trees.UNARY_OPS,
        "future_leak_test_only",
        lambda x: x.shift(-3),
    )
    contaminated = BinaryNode(
        op="gt",
        left=UnaryNode(
            op="roll_mean_5",
            child=UnaryNode(op="future_leak_test_only", child=TerminalNode("ret1")),
        ),
        right=ConstantNode(value=0.0),
    )
    with pytest.raises(LookaheadError):
        validate_expression_is_causal(contaminated, frame)


# ---------------------------------------------------------------------------
# Degenerate (constant / no-variance) expressions -- found on a real SIP run,
# not hypothesized: a candidate built entirely from constants trivially
# mimics "always hold the cash sleeve", which has a structural advantage
# under a raw-Sharpe Layer 1 quality metric.
# ---------------------------------------------------------------------------


def test_all_constant_expression_is_rejected_as_degenerate() -> None:
    frame = _synthetic_frame(n=400)
    # Exactly the formula that broke a real run:
    # mul(roll_mean_5(roll_mean_20(0.2)), neg(max2(-0.02, 0.05))) == -0.01
    # on every date, forever -- no terminal anywhere in the tree.
    constant_tree = BinaryNode(
        op="mul",
        left=UnaryNode(
            op="roll_mean_5", child=UnaryNode(op="roll_mean_20", child=ConstantNode(0.2))
        ),
        right=UnaryNode(
            op="neg",
            child=BinaryNode(op="max2", left=ConstantNode(-0.02), right=ConstantNode(0.05)),
        ),
    )
    with pytest.raises(DegenerateExpressionError):
        validate_expression_is_informative(constant_tree, frame)


def test_numerically_constant_expression_is_rejected_as_degenerate() -> None:
    """A tree that *does* reference a terminal can still be numerically
    constant given the data's sign pattern -- a rolling standard deviation
    (``vol20``) is never negative, so ``sign(vol20)`` is always ``+1.0``.
    """
    frame = _synthetic_frame(n=400)
    tree = UnaryNode(op="sign", child=TerminalNode("vol20"))
    with pytest.raises(DegenerateExpressionError):
        validate_expression_is_informative(tree, frame)


def test_data_dependent_expression_is_not_falsely_rejected_as_degenerate() -> None:
    frame = _synthetic_frame(n=400)
    tree = BinaryNode(
        op="gt",
        left=UnaryNode(op="roll_mean_5", child=TerminalNode("ret1")),
        right=UnaryNode(op="roll_mean_20", child=TerminalNode("ret1")),
    )
    validate_expression_is_informative(tree, frame)  # must not raise
