from __future__ import annotations

import ast
import json
import math
from bisect import bisect_right
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date
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
    rsi_simple,
    sma,
    stddev,
    zscore,
)
from open_composer.market_calendar import NEW_YORK

OHLCV_NAMES = {"open", "high", "low", "close", "volume"}
SERIES_WINDOW_FUNCTIONS = {
    "sma": sma,
    "ema": ema,
    "rsi": rsi,
    "rsi_simple": rsi_simple,
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
ALLOWED_AST_NODES = frozenset(
    {
        ast.Expression,
        ast.Load,
        ast.Constant,
        ast.Name,
        ast.Call,
        ast.Compare,
        ast.BoolOp,
        ast.UnaryOp,
        ast.BinOp,
        ast.UAdd,
        ast.USub,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Not,
        ast.And,
        ast.Or,
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
        ast.Eq,
        ast.NotEq,
    }
)
ALLOWED_FUNCTIONS = frozenset(
    {
        *SERIES_WINDOW_FUNCTIONS,
        *CROSS_FUNCTIONS,
        "atr",
        *STATISTICAL_FUNCTIONS,
    }
)
FORBIDDEN_NAMES = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "eval",
        "exec",
        "getattr",
        "globals",
        "input",
        "locals",
        "open",
        "os",
        "requests",
        "setattr",
        "socket",
        "subprocess",
        "sys",
        "urllib",
        "vars",
    }
)


class ExpressionError(ValueError):
    pass


class ExpressionSafetyError(ExpressionError):
    pass


class _SafetyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[str] = []

    def generic_visit(self, node: ast.AST) -> None:
        if type(node) not in ALLOWED_AST_NODES:
            self.violations.append(
                f"forbidden AST node: {type(node).__name__} at line {getattr(node, 'lineno', '?')}"
            )
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id not in OHLCV_NAMES and (node.id in FORBIDDEN_NAMES or node.id.startswith("__")):
            self.violations.append(f"forbidden name: {node.id!r}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_NAMES or node.func.id.startswith("__"):
                self.violations.append(f"forbidden function call: {node.func.id!r}")
            elif node.func.id not in ALLOWED_FUNCTIONS:
                self.violations.append(f"forbidden function call: {node.func.id!r}")
        else:
            self.violations.append("forbidden function call form")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in FORBIDDEN_NAMES or node.attr.startswith("__"):
            self.violations.append(f"forbidden attribute: {node.attr!r}")
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        self.violations.append("import is not allowed in expressions")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.violations.append("import is not allowed in expressions")
        self.generic_visit(node)


def assert_expression_safe(expression: str) -> None:
    """Raise ExpressionSafetyError when an expression leaves OC's safe subset."""
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionSafetyError(f"expression is not valid Python: {exc}") from exc
    visitor = _SafetyVisitor()
    visitor.visit(parsed)
    if visitor.violations:
        raise ExpressionSafetyError(
            "expression failed AST safety check:\n  - " + "\n  - ".join(visitor.violations)
        )


def validate_expression(
    expression: str,
    factors: Mapping[str, Any] | None = None,
    root: Path | None = None,
) -> None:
    factor_map = factors or {}
    referenced = _referenced_factor_names(expression, factor_map)
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
    executable_factors: dict[str, Any] = {}
    for name in referenced:
        factor = factor_map[name]
        if getattr(factor, "source", "expression") in {"llm_feature", "feature_packet"}:
            # Spec validation is static. External packets may legitimately be
            # materialized only after the spec has loaded; runtime evaluation
            # still resolves the real packet and fails closed when it is invalid.
            dummy[name] = getattr(factor, "default", 0.0)
        else:
            executable_factors[name] = factor
    frame = prepare_factor_frame(
        dummy,
        executable_factors,
        root=root,
    )
    evaluate_expression(expression, frame)


def _referenced_factor_names(
    expression: str,
    factors: Mapping[str, Any],
) -> set[str]:
    """Return the transitive factor dependencies used by one rule expression."""
    assert_expression_safe(expression)
    pending = [
        node.id
        for node in ast.walk(ast.parse(expression, mode="eval"))
        if isinstance(node, ast.Name) and node.id in factors
    ]
    referenced: set[str] = set()
    while pending:
        name = pending.pop()
        if name in referenced:
            continue
        referenced.add(name)
        factor_expression = getattr(factors[name], "expression", None)
        if not factor_expression:
            continue
        assert_expression_safe(str(factor_expression))
        pending.extend(
            node.id
            for node in ast.walk(ast.parse(str(factor_expression), mode="eval"))
            if isinstance(node, ast.Name) and node.id in factors and node.id not in referenced
        )
    return referenced


def required_history_bars(
    expressions: list[str],
    factors: Mapping[str, Any] | None = None,
) -> int:
    """Return the minimum rows needed to evaluate the latest expression value."""
    factor_map = factors or {}
    required = 1
    for expression in expressions:
        assert_expression_safe(expression)
        parsed = ast.parse(expression, mode="eval")
        required = max(required, _required_history_node(parsed, factor_map, set()))
    return required


def _required_history_node(
    node: ast.AST,
    factors: Mapping[str, Any],
    resolving: set[str],
) -> int:
    if isinstance(node, ast.Expression):
        return _required_history_node(node.body, factors, resolving)
    if isinstance(node, ast.Name):
        factor = factors.get(node.id)
        expression = getattr(factor, "expression", None) if factor is not None else None
        if not expression or node.id in resolving:
            return 1
        parsed = ast.parse(str(expression), mode="eval")
        return _required_history_node(parsed, factors, {*resolving, node.id})
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        child_required = max(
            (_required_history_node(arg, factors, resolving) for arg in node.args),
            default=1,
        )
        windows = [
            arg.value
            for arg in node.args
            if isinstance(arg, ast.Constant)
            and isinstance(arg.value, int)
            and not isinstance(arg.value, bool)
            and arg.value > 0
        ]
        if name in {"lag", "roc"} and windows:
            return child_required + int(windows[-1])
        if (
            name
            in {
                "sma",
                "ema",
                "rsi",
                "rsi_simple",
                "highest",
                "lowest",
                "stddev",
                "zscore",
                "bollinger_mid",
                "bollinger_upper",
                "bollinger_lower",
            }
            and windows
        ):
            return child_required + int(windows[-1]) - 1
        if name == "atr" and windows:
            return int(windows[-1]) + 1
        if name == "macd" and len(windows) >= 2:
            return child_required + max(int(windows[0]), int(windows[1])) - 1
        if name in {"macd_signal", "macd_hist"} and len(windows) >= 3:
            return child_required + max(int(windows[0]), int(windows[1])) + int(windows[2]) - 2
        if name in CROSS_FUNCTIONS:
            return child_required + 1
        return child_required
    children = list(ast.iter_child_nodes(node))
    if not children:
        return 1
    return max(_required_history_node(child, factors, resolving) for child in children)


def evaluate_expression(expression: str, frame: pd.DataFrame) -> pd.Series:
    result = evaluate_raw_expression(expression, frame)
    if isinstance(result, pd.Series):
        return result.fillna(False).astype(bool)
    if isinstance(result, bool):
        return pd.Series([result] * len(frame), index=frame.index)
    raise ExpressionError(f"expression must evaluate to a boolean series: {expression}")


def evaluate_raw_expression(expression: str, frame: pd.DataFrame) -> Any:
    assert_expression_safe(expression)
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid expression syntax: {expression}") from exc
    return _eval_node(parsed, frame)


def prepare_factor_frame(
    frame: pd.DataFrame,
    factors: Mapping[str, Any] | None,
    root: Path | None = None,
    symbol: str | None = None,
    require_feature_symbol: bool = False,
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
                if source in {"expression", "factor_library"}:
                    params = getattr(factor, "params", {}) or {}
                    transform = params.get("transform")
                    if transform == ("weighted_sum_of_component_cross_sectional_percentile_ranks"):
                        raise ExpressionError(
                            f"factor {name} requires a panel-aware cross-sectional transform"
                        )
                    if transform is not None:
                        raise ExpressionError(
                            f"factor {name} declares unsupported transform: {transform}"
                        )
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
                            symbol,
                            require_feature_symbol,
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
    symbol: str | None = None,
    require_feature_symbol: bool = False,
) -> pd.Series:
    frame = prepare_factor_frame(
        frame,
        factors or {},
        root=root,
        symbol=symbol,
        require_feature_symbol=require_feature_symbol,
    )
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
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand = _eval_node(node.operand, frame)
        return -operand if isinstance(node.op, ast.USub) else operand
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
    symbol: str | None,
    require_feature_symbol: bool,
) -> pd.Series:
    default = getattr(factor, "default", 0.0)
    if "timestamp" not in frame.columns:
        raise ExpressionError(f"{source_label} factors require timestamp column")

    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    records = _load_feature_packet_records(
        name,
        factor,
        root=root,
        source_label=source_label,
        symbol=symbol,
        require_feature_symbol=require_feature_symbol,
        strategy_name=frame.attrs.get("strategy_name"),
        decision_timestamps=timestamps,
    )
    values: list[Any] = []
    cursor = 0
    current = default
    for timestamp in timestamps:
        while cursor < len(records) and records[cursor].visible_at <= timestamp:
            current = records[cursor].value
            cursor += 1
        values.append(current)
    return pd.Series(values, index=frame.index)


_MISSING = object()


@dataclass(frozen=True)
class FeaturePacketRecord:
    value: float
    visible_at: pd.Timestamp
    fetched_at: pd.Timestamp


def _load_feature_packet_records(
    name: str,
    factor: Any,
    *,
    root: Path | None,
    source_label: str,
    symbol: str | None,
    require_feature_symbol: bool,
    strategy_name: str | None = None,
    decision_timestamps: Any | None = None,
) -> list[FeaturePacketRecord]:
    field = getattr(factor, "field", None)
    if not field:
        raise ExpressionError(f"{source_label} factor {name} missing field")
    path = _resolve_feature_packet_path(
        name,
        factor,
        root=root,
        source_label=source_label,
        strategy_name=strategy_name,
    )

    records: list[FeaturePacketRecord] = []
    row_count = 0
    previous_visible_at: pd.Timestamp | None = None
    for raw, context in _iter_feature_packet_rows(path):
        row_count += 1
        packet_symbol = _feature_packet_symbol(raw, context=context)
        if require_feature_symbol and not packet_symbol:
            raise ExpressionError(f"{context} is missing required symbol")
        if symbol and packet_symbol not in {symbol.upper(), "*", ""}:
            continue
        visible_at = _feature_packet_effective_visible_at(raw, context=context)
        if previous_visible_at is not None:
            if visible_at == previous_visible_at:
                raise ExpressionError(f"{context} duplicates visible_at {visible_at.isoformat()}")
            if visible_at < previous_visible_at:
                raise ExpressionError(f"{context} is out of visible_at order")
        previous_visible_at = visible_at
        records.append(
            FeaturePacketRecord(
                value=_feature_packet_numeric_value(raw, field, context=context),
                visible_at=visible_at,
                fetched_at=_feature_packet_fetched_at(raw, context=context),
            )
        )
    if row_count == 0:
        raise ExpressionError(f"{source_label} factor {name} packet {path} is empty")
    if not records:
        target = symbol.upper() if symbol else "requested stream"
        raise ExpressionError(
            f"{source_label} factor {name} packet {path} has no records matching {target}"
        )
    _validate_feature_packet_contract(
        name,
        factor,
        records,
        source_label=source_label,
        decision_timestamps=decision_timestamps,
    )
    return records


def _resolve_feature_packet_path(
    name: str,
    factor: Any,
    *,
    root: Path | None,
    source_label: str,
    strategy_name: str | None,
) -> Path:
    path_value = getattr(factor, "path", None)
    if not path_value and source_label == "llm_feature" and strategy_name and root is not None:
        path_value = f"reports/features/{strategy_name}/{name}/packets.jsonl"
    if not path_value:
        raise ExpressionError(f"{source_label} factor {name} missing packet path")
    path = Path(path_value)
    if not path.is_absolute() and root is not None:
        path = root / path
    if not path.is_file():
        raise ExpressionError(f"{source_label} factor {name} packet does not exist: {path}")
    return path


def _validate_feature_packet_contract(
    name: str,
    factor: Any,
    records: list[FeaturePacketRecord],
    *,
    source_label: str,
    decision_timestamps: Any | None,
) -> None:
    params = getattr(factor, "params", {}) or {}
    availability_field = params.get("availability_field")
    if availability_field not in {None, "visible_at"}:
        raise ExpressionError(
            f"{source_label} factor {name} must use visible_at availability, "
            f"got {availability_field!r}"
        )
    forward_fill_allowed = params.get("forward_fill_allowed")
    if forward_fill_allowed is not None and not isinstance(forward_fill_allowed, bool):
        raise ExpressionError(f"{source_label} factor {name} has invalid forward_fill_allowed")
    max_age_sessions = params.get("max_age_sessions")
    if max_age_sessions is not None and (
        isinstance(max_age_sessions, bool)
        or not isinstance(max_age_sessions, int)
        or max_age_sessions < 0
    ):
        raise ExpressionError(f"{source_label} factor {name} has invalid max_age_sessions")
    if decision_timestamps is None:
        return
    timestamps = pd.to_datetime(decision_timestamps, utc=True, errors="raise")
    session_dates = sorted(
        {pd.Timestamp(timestamp).tz_convert(NEW_YORK).date() for timestamp in timestamps}
    )
    if forward_fill_allowed is False:
        packet_session_dates = {record.visible_at.tz_convert(NEW_YORK).date() for record in records}
        first_packet_session = min(packet_session_dates)
        last_packet_session = max(packet_session_dates)
        missing_sessions = [
            session
            for session in session_dates
            if first_packet_session <= session <= last_packet_session
            and session not in packet_session_dates
        ]
        if missing_sessions:
            raise ExpressionError(
                f"{source_label} factor {name} has a missing session "
                f"{missing_sessions[0].isoformat()}"
            )
    if max_age_sessions is None:
        return
    cursor = 0
    current: FeaturePacketRecord | None = None
    for timestamp in timestamps:
        while cursor < len(records) and records[cursor].visible_at <= timestamp:
            current = records[cursor]
            cursor += 1
        if current is None:
            continue
        age = _observed_session_age(
            current.visible_at,
            pd.Timestamp(timestamp),
            session_dates,
        )
        if age > max_age_sessions:
            raise ExpressionError(
                f"{source_label} factor {name} packet is stale at "
                f"{pd.Timestamp(timestamp).isoformat()}: age {age} sessions exceeds "
                f"max_age_sessions={max_age_sessions}"
            )


def _observed_session_age(
    visible_at: pd.Timestamp,
    decision_at: pd.Timestamp,
    session_dates: list[date],
) -> int:
    if decision_at < visible_at:
        return 0
    start = visible_at.tz_convert(NEW_YORK).date()
    end = decision_at.tz_convert(NEW_YORK).date()
    return bisect_right(session_dates, end) - bisect_right(session_dates, start)


def _iter_feature_packet_rows(path: Path) -> Iterator[tuple[Mapping[str, Any], str]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            context = f"feature packet {path} line {line_number}"
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ExpressionError(f"{context} is not valid JSON") from exc
            if not isinstance(raw, Mapping):
                raise ExpressionError(f"{context} must be a JSON object")
            yield raw, context


def _feature_packet_symbol(raw: Mapping[str, Any], *, context: str) -> str:
    if "symbol" not in raw or raw["symbol"] is None:
        return ""
    value = raw["symbol"]
    if not isinstance(value, str):
        raise ExpressionError(f"{context} has invalid symbol")
    return value.strip().upper()


def _feature_packet_effective_visible_at(
    raw: Mapping[str, Any],
    *,
    context: str,
) -> pd.Timestamp:
    if "visible_at" in raw:
        return _feature_packet_timestamp(raw["visible_at"], field="visible_at", context=context)
    if "published_at" not in raw or "fetched_at" not in raw:
        raise ExpressionError(
            f"{context} is missing visible_at and published_at/fetched_at fallback"
        )
    published_at = _feature_packet_timestamp(
        raw["published_at"], field="published_at", context=context
    )
    fetched_at = _feature_packet_timestamp(raw["fetched_at"], field="fetched_at", context=context)
    return max(published_at, fetched_at)


def _feature_packet_fetched_at(raw: Mapping[str, Any], *, context: str) -> pd.Timestamp:
    if "fetched_at" not in raw:
        raise ExpressionError(f"{context} is missing fetched_at")
    return _feature_packet_timestamp(raw["fetched_at"], field="fetched_at", context=context)


def _feature_packet_timestamp(value: Any, *, field: str, context: str) -> pd.Timestamp:
    if value is None or isinstance(value, bool | int | float | Mapping | list | tuple):
        raise ExpressionError(f"{context} has invalid {field}")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ExpressionError(f"{context} has invalid {field}") from exc
    if pd.isna(timestamp):
        raise ExpressionError(f"{context} has invalid {field}")
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _feature_packet_numeric_value(
    raw: Mapping[str, Any],
    field: str,
    *,
    context: str,
) -> float:
    value = _feature_packet_value(raw, field)
    if value is _MISSING:
        raise ExpressionError(f"{context} is missing field {field!r}")
    if isinstance(value, bool):
        return float(value)
    if not isinstance(value, int | float):
        raise ExpressionError(f"{context} field {field!r} must be a finite numeric value")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ExpressionError(f"{context} field {field!r} must be a finite numeric value")
    return numeric


def _feature_packet_value(raw: Mapping[str, Any], field: str) -> Any:
    if field in raw:
        return raw[field]
    features = raw.get("features")
    if isinstance(features, Mapping) and field in features:
        return features[field]
    return _MISSING
