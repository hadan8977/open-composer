from __future__ import annotations

import ast
from functools import reduce
from operator import and_, or_
from typing import Any

import pandas as pd

from open_composer.indicators import ema, rsi, sma

OHLCV_NAMES = {"open", "high", "low", "close", "volume"}
FUNCTIONS = {"sma": sma, "ema": ema, "rsi": rsi}


class ExpressionError(ValueError):
    pass


def validate_expression(expression: str) -> None:
    dummy = pd.DataFrame(
        {
            "open": range(1, 40),
            "high": range(2, 41),
            "low": range(0, 39),
            "close": range(1, 40),
            "volume": range(1_000, 1_039),
        }
    )
    evaluate_expression(expression, dummy)


def evaluate_expression(expression: str, frame: pd.DataFrame) -> pd.Series:
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid expression syntax: {expression}") from exc
    result = _eval_node(parsed, frame)
    if isinstance(result, pd.Series):
        return result.fillna(False).astype(bool)
    if isinstance(result, bool):
        return pd.Series([result] * len(frame), index=frame.index)
    raise ExpressionError(f"expression must evaluate to a boolean series: {expression}")


def evaluate_rule_block(
    frame: pd.DataFrame, all_rules: list[str], any_rules: list[str]
) -> pd.Series:
    pieces: list[pd.Series] = []
    if all_rules:
        pieces.append(reduce(and_, [evaluate_expression(rule, frame) for rule in all_rules]))
    if any_rules:
        pieces.append(reduce(or_, [evaluate_expression(rule, frame) for rule in any_rules]))
    if not pieces:
        return pd.Series([False] * len(frame), index=frame.index)
    return reduce(and_, pieces).fillna(False).astype(bool)


def _eval_node(node: ast.AST, frame: pd.DataFrame) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, frame)
    if isinstance(node, ast.Name):
        if node.id not in OHLCV_NAMES:
            raise ExpressionError(f"unsupported name: {node.id}")
        return frame[node.id]
    if isinstance(node, ast.Constant):
        if isinstance(node.value, int | float | bool):
            return node.value
        raise ExpressionError(f"unsupported constant: {node.value!r}")
    if isinstance(node, ast.Call):
        return _eval_call(node, frame)
    if isinstance(node, ast.Compare):
        return _eval_compare(node, frame)
    if isinstance(node, ast.BoolOp):
        values = [_eval_node(value, frame) for value in node.values]
        if isinstance(node.op, ast.And):
            return reduce(and_, values)
        if isinstance(node.op, ast.Or):
            return reduce(or_, values)
        raise ExpressionError("unsupported boolean operator")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return ~_eval_node(node.operand, frame)
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, frame)
        right = _eval_node(node.right, frame)
        return _eval_binop(node.op, left, right)
    raise ExpressionError(f"unsupported expression element: {node.__class__.__name__}")


def _eval_call(node: ast.Call, frame: pd.DataFrame) -> pd.Series:
    if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
        raise ExpressionError("only sma(), ema(), and rsi() calls are supported")
    if len(node.args) != 2 or node.keywords:
        raise ExpressionError(f"{node.func.id}() requires exactly two positional arguments")
    series = _eval_node(node.args[0], frame)
    window = _eval_node(node.args[1], frame)
    if not isinstance(series, pd.Series):
        raise ExpressionError(f"{node.func.id}() first argument must be an OHLCV series")
    if not isinstance(window, int) or window <= 0:
        raise ExpressionError(f"{node.func.id}() window must be a positive integer")
    return FUNCTIONS[node.func.id](series.astype(float), window)


def _eval_compare(node: ast.Compare, frame: pd.DataFrame) -> pd.Series:
    if len(node.ops) != 1 or len(node.comparators) != 1:
        raise ExpressionError("chained comparisons are not supported")
    left = _eval_node(node.left, frame)
    right = _eval_node(node.comparators[0], frame)
    op = node.ops[0]
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.GtE):
        return left >= right
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    raise ExpressionError("unsupported comparison operator")


def _eval_binop(op: ast.operator, left: Any, right: Any) -> Any:
    if isinstance(op, ast.Add):
        return left + right
    if isinstance(op, ast.Sub):
        return left - right
    if isinstance(op, ast.Mult):
        return left * right
    if isinstance(op, ast.Div):
        return left / right
    raise ExpressionError("unsupported arithmetic operator")
