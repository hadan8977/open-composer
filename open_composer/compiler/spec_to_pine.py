from __future__ import annotations

import ast
from pathlib import Path

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.reports.writer import write_parity_report

OHLCV_NAMES = {"open", "high", "low", "close", "volume"}
PINE_FUNCTION_NAMES = {
    "atr",
    "bollinger_lower",
    "bollinger_mid",
    "bollinger_upper",
    "crossunder",
    "crossover",
    "ema",
    "highest",
    "lag",
    "lowest",
    "macd",
    "macd_hist",
    "macd_signal",
    "roc",
    "rsi",
    "sma",
    "stddev",
    "zscore",
}


def compile_pine(spec_path: Path, root: Path | None = None) -> Path:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    pine_path = base / "strategies_pine" / "generated" / f"{spec.name}.pine"
    ensure_dir(pine_path.parent)
    pine_path.write_text(render_pine(spec), encoding="utf-8")
    parity_path = base / "reports" / "parity" / f"{spec.name}-checklist.md"
    write_parity_report(parity_path, spec, pine_path)
    return pine_path


def compile_pine_strategy(spec_path: Path, root: Path | None = None) -> Path:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    pine_path = base / "strategies_pine" / "generated" / f"{spec.name}.strategy.pine"
    ensure_dir(pine_path.parent)
    pine_path.write_text(render_pine_strategy(spec), encoding="utf-8")
    parity_path = base / "reports" / "parity" / f"{spec.name}-strategy-checklist.md"
    write_parity_report(parity_path, spec, pine_path)
    return pine_path


def render_pine(spec: StrategySpec) -> str:
    factor_lines = _factor_declarations_to_pine(spec)
    entry_expr = _rule_block_to_pine(spec.entry.all, spec.entry.any)
    exit_expr = _rule_block_to_pine(spec.exit.all, spec.exit.any)
    title = spec.name.replace("_", " ").title()
    return "\n".join(
        [
            "//@version=6",
            f'indicator("{title}", overlay=true)',
            "",
            *factor_lines,
            "",
            f"entryCondition = barstate.isconfirmed and ({entry_expr})",
            f"exitCondition = barstate.isconfirmed and ({exit_expr})",
            "",
            'plotshape(entryCondition, title="Entry", style=shape.triangleup, '
            "location=location.belowbar, color=color.new(color.green, 0), size=size.tiny)",
            'plotshape(exitCondition, title="Exit", style=shape.triangledown, '
            "location=location.abovebar, color=color.new(color.red, 0), size=size.tiny)",
            "",
            f'alertcondition(entryCondition, title="{spec.name} entry", '
            f'message="{spec.name} entry {{ticker}} {{interval}} close={{close}}")',
            f'alertcondition(exitCondition, title="{spec.name} exit", '
            f'message="{spec.name} exit {{ticker}} {{interval}} close={{close}}")',
            "",
            "// Assumptions: bar-close signals; Python backtests fill on next bar open.",
        ]
    )


def render_pine_strategy(spec: StrategySpec) -> str:
    factor_lines = _factor_declarations_to_pine(spec)
    entry_expr = _rule_block_to_pine(spec.entry.all, spec.entry.any)
    exit_expr = _rule_block_to_pine(spec.exit.all, spec.exit.any)
    title = f"{spec.name.replace('_', ' ').title()} Strategy"
    position_pct = spec.risk.max_position_weight * 100
    stop_expr = (
        f"close <= strategy.position_avg_price * {1 - spec.risk.stop_loss_pct / 100:.10g}"
        if spec.risk.stop_loss_pct is not None
        else "false"
    )
    take_expr = (
        f"close >= strategy.position_avg_price * {1 + spec.risk.take_profit_pct / 100:.10g}"
        if spec.risk.take_profit_pct is not None
        else "false"
    )
    return "\n".join(
        [
            "//@version=6",
            f'strategy("{title}", overlay=true, initial_capital=100000, pyramiding=0, '
            "default_qty_type=strategy.percent_of_equity, "
            f"default_qty_value={position_pct:.10g}, "
            "commission_type=strategy.commission.percent, commission_value=0)",
            "",
            *factor_lines,
            "",
            f"entrySignal = barstate.isconfirmed and ({entry_expr})",
            f"exitSignal = barstate.isconfirmed and ({exit_expr})",
            "",
            'newDay = ta.change(time("D")) != 0',
            "var int tradesToday = 0",
            "if newDay",
            "    tradesToday := 0",
            "",
            "canEnter = strategy.position_size == 0 and "
            f"tradesToday < {spec.risk.max_trades_per_day}",
            "if entrySignal and canEnter",
            f'    strategy.entry("Long", strategy.long, alert_message="{spec.name} entry")',
            "    tradesToday += 1",
            "",
            f"riskExit = strategy.position_size > 0 and (({stop_expr}) or ({take_expr}))",
            "if strategy.position_size > 0 and (exitSignal or riskExit)",
            f'    strategy.close("Long", alert_message="{spec.name} exit")',
            "",
            'plotshape(entrySignal and canEnter, title="Entry", style=shape.triangleup, '
            "location=location.belowbar, color=color.new(color.green, 0), size=size.tiny)",
            'plotshape(strategy.position_size > 0 and (exitSignal or riskExit), title="Exit", '
            "style=shape.triangledown, location=location.abovebar, "
            "color=color.new(color.red, 0), size=size.tiny)",
            "",
            "// Assumptions: bar-close signals; strategy market orders fill on the next bar open.",
            "// Risk exits mirror the Python backtest: close-confirmed stop/take, "
            "then next-bar fill.",
        ]
    )


def _rule_block_to_pine(all_rules: list[str], any_rules: list[str]) -> str:
    pieces: list[str] = []
    if all_rules:
        all_expr = " and ".join(f"({_to_pine(rule)})" for rule in all_rules)
        pieces.append(f"({all_expr})")
    if any_rules:
        any_expr = " or ".join(f"({_to_pine(rule)})" for rule in any_rules)
        pieces.append(f"({any_expr})")
    return " and ".join(pieces) if pieces else "false"


def _factor_declarations_to_pine(spec: StrategySpec) -> list[str]:
    lines: list[str] = []
    resolved = set(OHLCV_NAMES)
    pending = list(spec.factors.items())

    for name, factor in pending:
        if factor.source != "expression":
            lines.append(f"// {name}: LLM feature factor is not replayable in Pine")
            lines.append(f"{name} = {str(factor.default).lower()}")
            resolved.add(name)

    pending_expressions = [
        (name, factor)
        for name, factor in pending
        if factor.source == "expression" and factor.expression
    ]
    while pending_expressions:
        progressed = False
        next_pending: list[tuple[str, object]] = []
        for name, factor in pending_expressions:
            expression = factor.expression
            assert expression is not None
            references = _expression_references(expression)
            unknown = sorted(
                ref for ref in references if ref not in spec.factors and ref not in OHLCV_NAMES
            )
            if unknown:
                raise ValueError(
                    f"unsupported Pine expression names in factor {name}: {', '.join(unknown)}"
                )
            unresolved = sorted(
                ref for ref in references if ref in spec.factors and ref not in resolved
            )
            if unresolved:
                next_pending.append((name, factor))
                continue
            lines.append(f"{name} = {_to_pine(expression)}")
            resolved.add(name)
            progressed = True
        if not progressed and next_pending:
            unresolved_names = ", ".join(name for name, _ in next_pending)
            raise ValueError(f"cyclic or unresolved factor dependencies: {unresolved_names}")
        pending_expressions = next_pending
    return lines


def _to_pine(expression: str) -> str:
    parsed = ast.parse(expression, mode="eval")
    return _node_to_pine(parsed.body)


def _node_to_pine(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return str(node.value).lower() if isinstance(node.value, bool) else str(node.value)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("unsupported Pine expression function")
        function_name = node.func.id
        if function_name in {"sma", "ema", "rsi", "highest", "lowest", "roc", "stddev"}:
            args = ", ".join(_node_to_pine(arg) for arg in node.args)
            pine_name = "stdev" if function_name == "stddev" else function_name
            return f"ta.{pine_name}({args})"
        if function_name in {"crossover", "crossunder"}:
            args = ", ".join(_node_to_pine(arg) for arg in node.args)
            return f"ta.{function_name}({args})"
        if function_name == "lag":
            if len(node.args) != 2:
                raise ValueError("lag() requires expression and periods")
            return f"({_node_to_pine(node.args[0])})[{_node_to_pine(node.args[1])}]"
        if function_name == "atr":
            if len(node.args) != 1:
                raise ValueError("atr() requires a window")
            return f"ta.atr({_node_to_pine(node.args[0])})"
        if function_name in {"macd", "macd_signal", "macd_hist"}:
            if function_name == "macd":
                if len(node.args) != 3:
                    raise ValueError("macd() requires series, fast, and slow")
                series = _node_to_pine(node.args[0])
                fast = _node_to_pine(node.args[1])
                slow = _node_to_pine(node.args[2])
                return f"(ta.ema({series}, {fast}) - ta.ema({series}, {slow}))"
            if len(node.args) != 4:
                raise ValueError(f"{function_name}() requires series, fast, slow, and signal")
            series = _node_to_pine(node.args[0])
            fast = _node_to_pine(node.args[1])
            slow = _node_to_pine(node.args[2])
            signal = _node_to_pine(node.args[3])
            macd_line = f"(ta.ema({series}, {fast}) - ta.ema({series}, {slow}))"
            if function_name == "macd_signal":
                return f"ta.ema({macd_line}, {signal})"
            signal_line = f"ta.ema({macd_line}, {signal})"
            return f"({macd_line} - {signal_line})"
        if function_name in {"bollinger_mid", "bollinger_upper", "bollinger_lower"}:
            if len(node.args) not in {2, 3}:
                raise ValueError(
                    f"{function_name}() requires series, window, and optional multiplier"
                )
            series = _node_to_pine(node.args[0])
            window = _node_to_pine(node.args[1])
            basis = f"ta.sma({series}, {window})"
            spread = f"ta.stdev({series}, {window})"
            if function_name == "bollinger_mid":
                return basis
            mult = _node_to_pine(node.args[2]) if len(node.args) == 3 else "2.0"
            if function_name == "bollinger_upper":
                return f"({basis} + {spread} * {mult})"
            return f"({basis} - {spread} * {mult})"
        if function_name == "zscore":
            if len(node.args) != 2:
                raise ValueError("zscore() requires series and window")
            series = _node_to_pine(node.args[0])
            window = _node_to_pine(node.args[1])
            basis = f"ta.sma({series}, {window})"
            spread = f"ta.stdev({series}, {window})"
            return f"nz(({series} - {basis}) / {spread}, 0)"
        raise ValueError("unsupported Pine expression function")
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("chained comparisons are not supported")
        left = _node_to_pine(node.left)
        operator = _op_to_pine(node.ops[0])
        right = _node_to_pine(node.comparators[0])
        return f"{left} {operator} {right}"
    if isinstance(node, ast.BoolOp):
        sep = " and " if isinstance(node.op, ast.And) else " or "
        return sep.join(f"({_node_to_pine(value)})" for value in node.values)
    if isinstance(node, ast.BinOp):
        return f"{_node_to_pine(node.left)} {_op_to_pine(node.op)} {_node_to_pine(node.right)}"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return f"not ({_node_to_pine(node.operand)})"
    raise ValueError(f"unsupported Pine expression element: {node.__class__.__name__}")


def _op_to_pine(op: ast.AST) -> str:
    mapping = {
        ast.Gt: ">",
        ast.GtE: ">=",
        ast.Lt: "<",
        ast.LtE: "<=",
        ast.Eq: "==",
        ast.NotEq: "!=",
        ast.Add: "+",
        ast.Sub: "-",
        ast.Mult: "*",
        ast.Div: "/",
    }
    for klass, symbol in mapping.items():
        if isinstance(op, klass):
            return symbol
    raise ValueError("unsupported Pine operator")


def _expression_references(expression: str) -> set[str]:
    parsed = ast.parse(expression, mode="eval")
    return {
        node.id
        for node in ast.walk(parsed)
        if isinstance(node, ast.Name)
        and node.id not in PINE_FUNCTION_NAMES
        and node.id not in OHLCV_NAMES
    }
