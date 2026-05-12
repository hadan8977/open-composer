from __future__ import annotations

import ast
import json
from collections.abc import Mapping
from functools import reduce
from operator import and_, or_
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.indicators import (
    atr,
    bollinger_lower,
    bollinger_mid,
    bollinger_upper,
    crossover,
    crossunder,
    ema,
    highest,
    lag,
    lowest,
    macd,
    macd_hist,
    macd_signal,
    roc,
    rsi,
    sma,
    stddev,
    zscore,
)

OHLCV_NAMES = {"open", "high", "low", "close", "volume"}
SERIES_WINDOW_FUNCTIONS = {
    "sma": sma,
    "ema": ema,
    "rsi": rsi,
    "highest": highest,
    "lowest": lowest,
    "lag": lag,
    "roc": roc,
}
CROSS_FUNCTIONS = {"crossover": crossover, "crossunder": crossunder}
STATISTICAL_FUNCTIONS = {
    "stddev": stddev,
    "zscore": zscore,
    "macd": macd,
    "macd_signal": macd_signal,
    "macd_hist": macd_hist,
    "bollinger_mid": bollinger_mid,
    "bollinger_upper": bollinger_upper,
    "bollinger_lower": bollinger_lower,
}


class ExpressionError(ValueError):
    pass


def validate_expression(
    expression: str,
    factors: Mapping[str, Any] | None = None,
    root: Path | None = None,
) -> None:
    dummy = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=40, freq="15min", tz="UTC"),
            "open": range(1, 41),
            "high": range(2, 42),
            "low": range(0, 40),
            "close": range(1, 41),
            "volume": range(1_000, 1_040),
        }
    )
    frame = prepare_factor_frame(dummy, factors or {}, root=root)
    evaluate_expression(expression, frame)


def evaluate_expression(expression: str, frame: pd.DataFrame) -> pd.Series:
    result = evaluate_raw_expression(expression, frame)
    if isinstance(result, pd.Series):
        return result.fillna(False).astype(bool)
    if isinstance(result, bool):
        return pd.Series([result] * len(frame), index=frame.index)
    raise ExpressionError(f"expression must evaluate to a boolean series: {expression}")


def evaluate_raw_expression(expression: str, frame: pd.DataFrame) -> Any:
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid expression syntax: {expression}") from exc
    return _eval_node(parsed, frame)


def prepare_factor_frame(
    frame: pd.DataFrame,
    factors: Mapping[str, Any] | None,
    root: Path | None = None,
) -> pd.DataFrame:
    if not factors:
        return frame
    prepared = frame.copy()
    remaining = dict(factors)
    while remaining:
        progressed = False
        blocked: dict[str, str] = {}
        for name, factor in list(remaining.items()):
            source = getattr(factor, "source", "expression")
            try:
                if source == "expression":
                    expression = getattr(factor, "expression", None)
                    if not expression:
                        raise ExpressionError(f"factor {name} missing expression")
                    prepared[name] = _series_from_factor_value(
                        evaluate_raw_expression(expression, prepared),
                        prepared,
                    )
                elif source in {"llm_feature", "feature_packet"}:
                    if name not in prepared.columns:
                        prepared[name] = _load_feature_packet(
                            name,
                            factor,
                            prepared,
                            root,
                            source,
                        )
                else:
                    raise ExpressionError(f"unsupported factor source: {source}")
            except ExpressionError as exc:
                blocked[name] = str(exc)
                continue
            remaining.pop(name)
            progressed = True
        if not progressed:
            details = "; ".join(f"{name}: {reason}" for name, reason in blocked.items())
            raise ExpressionError(f"could not resolve factors: {details}")
    return prepared


def evaluate_rule_block(
    frame: pd.DataFrame,
    all_rules: list[str],
    any_rules: list[str],
    factors: Mapping[str, Any] | None = None,
    root: Path | None = None,
) -> pd.Series:
    frame = prepare_factor_frame(frame, factors or {}, root=root)
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
        if node.id in frame.columns:
            return frame[node.id]
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
    if not isinstance(node.func, ast.Name):
        raise ExpressionError("unsupported function call")
    function_name = node.func.id
    if node.keywords:
        raise ExpressionError(f"{function_name}() does not support keyword arguments")

    if function_name in SERIES_WINDOW_FUNCTIONS:
        return _eval_series_window_call(function_name, node, frame)
    if function_name in CROSS_FUNCTIONS:
        return _eval_cross_call(function_name, node, frame)
    if function_name == "atr":
        return _eval_atr_call(node, frame)
    if function_name in STATISTICAL_FUNCTIONS:
        return _eval_statistical_call(function_name, node, frame)
    supported = [
        *SERIES_WINDOW_FUNCTIONS,
        *CROSS_FUNCTIONS,
        "atr",
        *STATISTICAL_FUNCTIONS,
    ]
    raise ExpressionError("supported functions: " + ", ".join(sorted(supported)))


def _eval_series_window_call(
    function_name: str,
    node: ast.Call,
    frame: pd.DataFrame,
) -> pd.Series:
    if len(node.args) != 2:
        raise ExpressionError(f"{function_name}() requires exactly two positional arguments")
    series = _eval_node(node.args[0], frame)
    window = _eval_node(node.args[1], frame)
    if not isinstance(series, pd.Series):
        raise ExpressionError(f"{function_name}() first argument must be an OHLCV series")
    if not isinstance(window, int) or window <= 0:
        raise ExpressionError(f"{function_name}() window must be a positive integer")
    return SERIES_WINDOW_FUNCTIONS[function_name](series.astype(float), window)


def _eval_cross_call(function_name: str, node: ast.Call, frame: pd.DataFrame) -> pd.Series:
    if len(node.args) != 2:
        raise ExpressionError(f"{function_name}() requires exactly two positional arguments")
    left = _eval_node(node.args[0], frame)
    right = _eval_node(node.args[1], frame)
    if not isinstance(left, pd.Series) or not isinstance(right, pd.Series):
        raise ExpressionError(f"{function_name}() requires two series arguments")
    return CROSS_FUNCTIONS[function_name](left.astype(float), right.astype(float))


def _eval_atr_call(node: ast.Call, frame: pd.DataFrame) -> pd.Series:
    if len(node.args) != 1:
        raise ExpressionError("atr() requires exactly one window argument")
    window = _eval_node(node.args[0], frame)
    if not isinstance(window, int) or window <= 0:
        raise ExpressionError("atr() window must be a positive integer")
    return atr(
        frame["high"].astype(float),
        frame["low"].astype(float),
        frame["close"].astype(float),
        window,
    )


def _eval_statistical_call(
    function_name: str,
    node: ast.Call,
    frame: pd.DataFrame,
) -> pd.Series:
    if function_name in {"stddev", "zscore", "bollinger_mid"}:
        if len(node.args) != 2:
            raise ExpressionError(f"{function_name}() requires exactly two positional arguments")
        series = _eval_node(node.args[0], frame)
        window = _eval_node(node.args[1], frame)
        if not isinstance(series, pd.Series):
            raise ExpressionError(f"{function_name}() first argument must be a series")
        if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
            raise ExpressionError(f"{function_name}() window must be a positive integer")
        series = series.astype(float)
        if function_name == "stddev":
            return stddev(series, window)
        if function_name == "zscore":
            return zscore(series, window)
        return bollinger_mid(series, window)

    if function_name in {"macd", "macd_signal", "macd_hist"}:
        expected_args = {
            "macd": 3,
            "macd_signal": 4,
            "macd_hist": 4,
        }[function_name]
        if len(node.args) != expected_args:
            raise ExpressionError(
                f"{function_name}() requires exactly {expected_args} positional arguments"
            )
        series = _eval_node(node.args[0], frame)
        if not isinstance(series, pd.Series):
            raise ExpressionError(f"{function_name}() first argument must be a series")
        series = series.astype(float)
        fast = _positive_int_arg(_eval_node(node.args[1], frame), function_name, "fast")
        slow = _positive_int_arg(_eval_node(node.args[2], frame), function_name, "slow")
        if function_name == "macd":
            return macd(series, fast, slow)
        signal = _positive_int_arg(_eval_node(node.args[3], frame), function_name, "signal")
        if function_name == "macd_signal":
            return macd_signal(series, fast, slow, signal)
        return macd_hist(series, fast, slow, signal)

    if function_name in {"bollinger_upper", "bollinger_lower"}:
        if len(node.args) not in {2, 3}:
            raise ExpressionError(
                f"{function_name}() requires two positional arguments and an optional multiplier"
            )
        series = _eval_node(node.args[0], frame)
        window = _eval_node(node.args[1], frame)
        if not isinstance(series, pd.Series):
            raise ExpressionError(f"{function_name}() first argument must be a series")
        if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
            raise ExpressionError(f"{function_name}() window must be a positive integer")
        mult = 2.0
        if len(node.args) == 3:
            mult_value = _eval_node(node.args[2], frame)
            if isinstance(mult_value, bool) or not isinstance(mult_value, int | float):
                raise ExpressionError(f"{function_name}() multiplier must be numeric")
            mult = float(mult_value)
        series = series.astype(float)
        if function_name == "bollinger_upper":
            return bollinger_upper(series, window, mult)
        return bollinger_lower(series, window, mult)

    raise ExpressionError(f"unsupported function: {function_name}")


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


def _positive_int_arg(value: Any, function_name: str, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ExpressionError(f"{function_name}() {label} must be a positive integer")
    return value


def _series_from_factor_value(value: Any, frame: pd.DataFrame) -> pd.Series:
    if isinstance(value, pd.Series):
        return value
    if isinstance(value, int | float | bool):
        return pd.Series([value] * len(frame), index=frame.index)
    raise ExpressionError("factor expression must evaluate to a series or scalar")


def _load_feature_packet(
    name: str,
    factor: Any,
    frame: pd.DataFrame,
    root: Path | None,
    source_label: str,
) -> pd.Series:
    default = getattr(factor, "default", 0.0)
    field = getattr(factor, "field", None)
    path_value = getattr(factor, "path", None)
    if not field:
        raise ExpressionError(f"{source_label} factor {name} missing field")
    if not path_value:
        return pd.Series([default] * len(frame), index=frame.index)
    path = Path(path_value)
    if not path.is_absolute() and root is not None:
        path = root / path
    if not path.exists():
        return pd.Series([default] * len(frame), index=frame.index)
    if "timestamp" not in frame.columns:
        raise ExpressionError(f"{source_label} factors require timestamp column")

    records: list[tuple[pd.Timestamp, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            if not isinstance(raw, Mapping):
                continue
            value = _feature_packet_value(raw, field)
            if value is _MISSING or "timestamp" not in raw:
                continue
            records.append((pd.Timestamp(raw["timestamp"]), value))
    if not records:
        return pd.Series([default] * len(frame), index=frame.index)

    records.sort(key=lambda item: item[0])
    values: list[Any] = []
    cursor = 0
    current = default
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    normalized_records = [
        (timestamp.tz_convert("UTC") if timestamp.tzinfo else timestamp.tz_localize("UTC"), value)
        for timestamp, value in records
    ]
    for timestamp in timestamps:
        while cursor < len(normalized_records) and normalized_records[cursor][0] <= timestamp:
            current = normalized_records[cursor][1]
            cursor += 1
        values.append(current)
    return pd.Series(values, index=frame.index)


_MISSING = object()


def _feature_packet_value(raw: Mapping[str, Any], field: str) -> Any:
    if field in raw:
        return raw[field]
    features = raw.get("features")
    if isinstance(features, Mapping) and field in features:
        return features[field]
    return _MISSING
