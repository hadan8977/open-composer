from __future__ import annotations

import ast
from pathlib import Path

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.reports.writer import write_parity_report


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
    entry_expr = _rule_block_to_pine(spec.entry.all, spec.entry.any)
    exit_expr = _rule_block_to_pine(spec.exit.all, spec.exit.any)
    title = spec.name.replace("_", " ").title()
    return "\n".join(
        [
            "//@version=6",
            f'indicator("{title}", overlay=true)',
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


def _to_pine(expression: str) -> str:
    parsed = ast.parse(expression, mode="eval")
    return _node_to_pine(parsed.body)


def _node_to_pine(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return str(node.value).lower() if isinstance(node.value, bool) else str(node.value)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in {"sma", "ema", "rsi"}:
            raise ValueError("unsupported Pine expression function")
        args = ", ".join(_node_to_pine(arg) for arg in node.args)
        return f"ta.{node.func.id}({args})"
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
