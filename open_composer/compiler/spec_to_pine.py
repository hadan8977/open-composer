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
