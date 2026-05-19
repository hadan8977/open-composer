from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from open_composer.adapters.execution.nautilus_trader import build_nautilus_trader_plan
from open_composer.expressions import ExpressionError, validate_expression
from open_composer.models.execution_backend import ExecutionBackendPlan
from open_composer.models.strategy_spec import StrategySpec
from open_composer.timeframes import supported_timeframes, timeframe_supported

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
    backend_plan: ExecutionBackendPlan

    def finding(self, capability: str) -> CapabilityFinding:
        for item in self.findings:
            if item.capability == capability:
                return item
        raise KeyError(capability)


def assess_strategy_capabilities(spec_path: Path | str) -> StrategyCapabilityReport:
    spec = _load_strategy_for_assessment(spec_path)
    return assess_strategy_capabilities_for_spec(spec, spec_path)


def assess_strategy_capabilities_for_spec(
    spec: StrategySpec,
    spec_path: Path | str,
) -> StrategyCapabilityReport:
    expression_inventory = _inventory_expressions(spec)
    expression_errors = _expression_errors(spec)
    findings = [
        _python_mvp_backtest(spec, expression_errors),
        _tradingview_pine_strategy(spec, expression_errors),
        _nautilus_trader_backend(spec_path),
        _alpaca_paper_execution(spec, expression_errors),
        _llm_quant_workflow(spec),
    ]
    return StrategyCapabilityReport(
        strategy_name=spec.name,
        lifecycle=spec.lifecycle,
        findings=findings,
        expression_functions=sorted(expression_inventory.functions),
        expression_names=sorted(expression_inventory.names),
        backend_plan=build_nautilus_trader_plan(spec_path),
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
    if spec.data.source not in {"sample", "alpaca", "longbridge"}:
        return CapabilityFinding(
            "python_mvp_backtest",
            "unsupported",
            [f"unsupported data source: {spec.data.source}"],
        )
    if spec.data.source in {"alpaca", "longbridge"} and not timeframe_supported(
        spec.data.source, spec.timeframe
    ):
        supported = ", ".join(supported_timeframes(spec.data.source))
        return CapabilityFinding(
            "python_mvp_backtest",
            "unsupported",
            [f"unsupported {spec.data.source} timeframe: {spec.timeframe}; supported: {supported}"],
        )
    non_market = _non_market_required_capabilities(spec)
    llm_feature_factors = _llm_feature_factors(spec)
    feature_packet_factors = _feature_packet_factors(spec)
    if spec.llm_review.enabled or non_market or llm_feature_factors or feature_packet_factors:
        if spec.llm_review.enabled or non_market:
            reasons.append(
                "deterministic entry/exit rules can be backtested, but advisory "
                "LLM/event/news/macro context outside explicit feature_packet factors is "
                "not replayed as trade logic"
            )
        if non_market:
            reasons.append(f"context capabilities are advisory only: {', '.join(non_market)}")
        if llm_feature_factors:
            reasons.append(
                "LLM feature factors are replayed from saved packets, not generated during "
                f"backtest: {', '.join(llm_feature_factors)}"
            )
        if feature_packet_factors:
            reasons.append(
                "feature_packet factors are replayed from saved point-in-time packets: "
                + ", ".join(feature_packet_factors)
            )
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
    llm_feature_factors = _llm_feature_factors(spec)
    if llm_feature_factors:
        reasons.append(
            "LLM feature factors are not representable in Pine Strategy Tester: "
            + ", ".join(llm_feature_factors)
        )
    feature_packet_factors = _feature_packet_factors(spec)
    if feature_packet_factors:
        reasons.append(
            "feature_packet factors are not representable in Pine Strategy Tester: "
            + ", ".join(feature_packet_factors)
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
    if spec.data.source not in {"alpaca", "longbridge"}:
        reasons.append(
            "live paper runs should use data.source=alpaca or longbridge, not offline fixtures"
        )
    elif not timeframe_supported(spec.data.source, spec.timeframe):
        supported = ", ".join(supported_timeframes(spec.data.source))
        reasons.append(
            f"data.source={spec.data.source} does not support timeframe={spec.timeframe}; "
            f"supported: {supported}"
        )
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


def _nautilus_trader_backend(spec_path: Path | str) -> CapabilityFinding:
    plan = build_nautilus_trader_plan(spec_path)
    status_map = {
        "supported": "supported",
        "partial": "partial",
        "blocked": "blocked",
        "unavailable": "blocked",
    }
    reasons = [f"{reason}" for reason in plan.reasons]
    if plan.selected_backend == "python_reference" and plan.status == "supported":
        reasons.append("selected backend remains python_reference until the backend is enabled")
        return CapabilityFinding("nautilus_trader_backend", "partial", reasons)
    return CapabilityFinding(
        "nautilus_trader_backend",
        status_map.get(plan.status, "blocked"),
        reasons or ["backend plan did not produce any reasons"],
    )


def _llm_quant_workflow(spec: StrategySpec) -> CapabilityFinding:
    llm_feature_factors = _llm_feature_factors(spec)
    if not spec.llm_review.enabled and not llm_feature_factors:
        return CapabilityFinding(
            "llm_quant_workflow",
            "blocked",
            ["llm_review.enabled is false; this is a deterministic quant-only spec"],
        )
    if llm_feature_factors:
        return CapabilityFinding(
            "llm_quant_workflow",
            "partial",
            [
                "LLM feature factors can be replayed from saved structured packets",
                "LLM feature generation is not yet an automated live pipeline",
                "factors: " + ", ".join(llm_feature_factors),
            ],
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
            validate_expression(expression, spec.factors)
        except ExpressionError as exc:
            errors.append(f"{expression}: {exc}")
    return errors


def _non_market_required_capabilities(spec: StrategySpec) -> list[str]:
    return sorted(
        capability
        for capability in spec.required_capabilities
        if not capability.startswith("market.")
    )


def _llm_feature_factors(spec: StrategySpec) -> list[str]:
    return sorted(name for name, factor in spec.factors.items() if factor.source == "llm_feature")


def _feature_packet_factors(spec: StrategySpec) -> list[str]:
    return sorted(
        name for name, factor in spec.factors.items() if factor.source == "feature_packet"
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
        _record_expression_inventory(expression, names, functions, unsupported_nodes)
    for factor in spec.factors.values():
        if factor.expression:
            _record_expression_inventory(factor.expression, names, functions, unsupported_nodes)
    factor_names = set(spec.factors)
    return _ExpressionInventory(
        names=(names - functions) | factor_names,
        functions=functions,
        unsupported_nodes=unsupported_nodes,
    )


def _record_expression_inventory(
    expression: str,
    names: set[str],
    functions: set[str],
    unsupported_nodes: set[str],
) -> None:
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError:
        return
    for node in ast.walk(parsed):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            functions.add(node.func.id)
        elif isinstance(node, ast.Subscript):
            unsupported_nodes.add("Subscript")
