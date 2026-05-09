from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from open_composer.expressions import ExpressionError, validate_expression
from open_composer.models.strategy_spec import StrategySpec

CapabilityStatus = Literal["supported", "partial", "blocked", "unsupported"]


@dataclass(frozen=True)
class CapabilityFinding:
    capability: str
    status: CapabilityStatus
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StrategyCapabilityReport:
    strategy_name: str
    lifecycle: str
    findings: list[CapabilityFinding]
    expression_functions: list[str]
    expression_names: list[str]

    def finding(self, capability: str) -> CapabilityFinding:
        for item in self.findings:
            if item.capability == capability:
                return item
        raise KeyError(capability)


def assess_strategy_capabilities(spec_path: Path | str) -> StrategyCapabilityReport:
    spec = _load_strategy_for_assessment(spec_path)
    expression_inventory = _inventory_expressions(spec)
    expression_errors = _expression_errors(spec)
    findings = [
        _python_mvp_backtest(spec, expression_errors),
        _tradingview_pine_strategy(spec, expression_errors),
        _alpaca_paper_execution(spec, expression_errors),
        _llm_quant_workflow(spec),
    ]
    return StrategyCapabilityReport(
        strategy_name=spec.name,
        lifecycle=spec.lifecycle,
        findings=findings,
        expression_functions=sorted(expression_inventory.functions),
        expression_names=sorted(expression_inventory.names),
    )


def _load_strategy_for_assessment(spec_path: Path | str) -> StrategySpec:
    path = Path(spec_path)
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        msg = f"{path} must contain a YAML mapping"
        raise ValueError(msg)
    return StrategySpec.model_validate(raw)


def _python_mvp_backtest(spec: StrategySpec, expression_errors: list[str]) -> CapabilityFinding:
    reasons: list[str] = []
    if expression_errors:
        return CapabilityFinding("python_mvp_backtest", "unsupported", expression_errors)
    if spec.data.source not in {"sample", "alpaca"}:
        return CapabilityFinding(
            "python_mvp_backtest",
            "unsupported",
            [f"unsupported data source: {spec.data.source}"],
        )
    non_market = _non_market_required_capabilities(spec)
    if spec.llm_review.enabled or non_market:
        reasons.append(
            "deterministic entry/exit rules can be backtested, but LLM/event/news/macro "
            "context is not replayed as trade logic"
        )
        if non_market:
            reasons.append(f"context capabilities are advisory only: {', '.join(non_market)}")
        return CapabilityFinding("python_mvp_backtest", "partial", reasons)
    return CapabilityFinding("python_mvp_backtest", "supported", ["v1 OHLCV rules are supported"])


def _tradingview_pine_strategy(
    spec: StrategySpec, expression_errors: list[str]
) -> CapabilityFinding:
    reasons: list[str] = []
    if expression_errors:
        return CapabilityFinding("tradingview_pine_strategy", "unsupported", expression_errors)
    if spec.llm_review.enabled:
        reasons.append("LLM review is not representable inside Pine; only entry/exit rules export")
    non_market = _non_market_required_capabilities(spec)
    if non_market:
        reasons.append(
            "event/news/macro capabilities are not exported to Pine: " + ", ".join(non_market)
        )
    if len(spec.universe) > 1:
        reasons.append(
            "Pine strategy export trades the primary symbol only; multi-symbol universe logic "
            "is not represented"
        )
    if reasons:
        return CapabilityFinding("tradingview_pine_strategy", "partial", reasons)
    return CapabilityFinding(
        "tradingview_pine_strategy",
        "supported",
        ["deterministic OHLCV rules can be exported for Strategy Tester"],
    )


def _alpaca_paper_execution(spec: StrategySpec, expression_errors: list[str]) -> CapabilityFinding:
    reasons: list[str] = []
    if expression_errors:
        return CapabilityFinding("alpaca_paper_execution", "unsupported", expression_errors)
    if spec.lifecycle != "active":
        reasons.append("strategy must be promoted to lifecycle=active")
    if spec.execution.mode != "paper_auto":
        reasons.append("execution.mode must be paper_auto")
    if spec.execution.broker != "alpaca_paper":
        reasons.append("execution.broker must be alpaca_paper")
    if spec.data.source != "alpaca":
        reasons.append("live paper runs should use data.source=alpaca, not offline fixtures")
    if reasons:
        return CapabilityFinding("alpaca_paper_execution", "blocked", reasons)
    if spec.llm_review.enabled:
        return CapabilityFinding(
            "alpaca_paper_execution",
            "partial",
            ["paper order execution is supported; LLM review remains an advisory or gating layer"],
        )
    return CapabilityFinding(
        "alpaca_paper_execution",
        "supported",
        ["active paper_auto Alpaca strategy can submit paper orders with explicit allow flag"],
    )


def _llm_quant_workflow(spec: StrategySpec) -> CapabilityFinding:
    if not spec.llm_review.enabled:
        return CapabilityFinding(
            "llm_quant_workflow",
            "blocked",
            ["llm_review.enabled is false; this is a deterministic quant-only spec"],
        )
    return CapabilityFinding(
        "llm_quant_workflow",
        "partial",
        [
            "structured LLM review cards are supported after signals",
            "LLM outputs are not yet replayable features in backtests",
        ],
    )


def _expression_errors(spec: StrategySpec) -> list[str]:
    errors: list[str] = []
    for expression in spec.all_expressions():
        try:
            validate_expression(expression)
        except ExpressionError as exc:
            errors.append(f"{expression}: {exc}")
    return errors


def _non_market_required_capabilities(spec: StrategySpec) -> list[str]:
    return sorted(
        capability
        for capability in spec.required_capabilities
        if not capability.startswith("market.")
    )


@dataclass(frozen=True)
class _ExpressionInventory:
    names: set[str]
    functions: set[str]
    unsupported_nodes: set[str]


def _inventory_expressions(spec: StrategySpec) -> _ExpressionInventory:
    names: set[str] = set()
    functions: set[str] = set()
    unsupported_nodes: set[str] = set()
    for expression in spec.all_expressions():
        try:
            parsed = ast.parse(expression, mode="eval")
        except SyntaxError:
            continue
        for node in ast.walk(parsed):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                functions.add(node.func.id)
            elif isinstance(node, ast.Subscript):
                unsupported_nodes.add("Subscript")
    return _ExpressionInventory(
        names=names - functions,
        functions=functions,
        unsupported_nodes=unsupported_nodes,
    )
