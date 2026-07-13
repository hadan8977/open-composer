"""Harness gate registry — thin wrappers that map gate names to assertion functions.

Each gate is a function (spec_path: Path, root: Path) -> GateResult.
Register a gate with the @gate decorator or GATE_REGISTRY[name] = fn directly.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.kernel.gates import GateResult

GateFunction = Callable[[Path, Path], GateResult]

GATE_REGISTRY: dict[str, GateFunction] = {}


def _classify_capability_findings(
    findings, *, is_not_applicable: Callable[[object], bool] | None = None
) -> tuple[list[str], list[str], list[str]]:
    blocked: list[str] = []
    warnings: list[str] = []
    not_applicable: list[str] = []
    for finding in findings.findings:
        if is_not_applicable and is_not_applicable(finding):
            not_applicable.append(finding.capability)
            continue
        if finding.status in {"blocked", "unsupported"}:
            blocked.append(finding.capability)
        elif finding.status == "partial":
            warnings.append(finding.capability)
    return blocked, warnings, not_applicable


def gate(name: str) -> Callable[[GateFunction], GateFunction]:
    """Decorator to register a gate function by name."""

    def decorator(fn: GateFunction) -> GateFunction:
        GATE_REGISTRY[name] = fn
        return fn

    return decorator


def run_gate(name: str, spec_path: Path, root: Path) -> GateResult:
    """Run a single named gate, returning a blocked result if the gate is not registered."""
    if name not in GATE_REGISTRY:
        return GateResult(
            name=name,
            status="blocked",
            message=f"Gate '{name}' is not registered in GATE_REGISTRY.",
        )
    try:
        return GATE_REGISTRY[name](spec_path, root)
    except Exception as exc:
        return GateResult(
            name=name,
            status="blocked",
            message=f"Gate '{name}' raised an exception: {exc}",
        )


def run_gates(names: list[str], spec_path: Path, root: Path) -> list[GateResult]:
    """Run a list of gates in order, returning all results."""
    return [run_gate(name, spec_path, root) for name in names]


# ---------------------------------------------------------------------------
# Built-in gate implementations
# ---------------------------------------------------------------------------


@gate("spec_validation")
def _spec_validation(spec_path: Path, root: Path) -> GateResult:  # noqa: ARG001
    try:
        spec = load_strategy_spec(spec_path)
        return GateResult(
            name="spec_validation",
            status="ok",
            message=f"StrategySpec loaded: name={spec.name!r} lifecycle={spec.lifecycle!r}",
            evidence={"name": spec.name, "lifecycle": spec.lifecycle, "spec_path": str(spec_path)},
        )
    except Exception as exc:
        return GateResult(
            name="spec_validation",
            status="blocked",
            message=f"StrategySpec failed to load: {exc}",
            evidence={"spec_path": str(spec_path), "error": str(exc)},
        )


@gate("expression_safety")
def _expression_safety(spec_path: Path, root: Path) -> GateResult:  # noqa: ARG001
    from open_composer.expressions import ExpressionSafetyError, assert_expression_safe

    try:
        spec = load_strategy_spec(spec_path)
    except Exception as exc:
        return GateResult(
            name="expression_safety",
            status="blocked",
            message=f"Could not load spec: {exc}",
        )
    expressions = [
        *spec.all_expressions(),
        *[f.expression for f in spec.factors.values() if f.source == "expression" and f.expression],
    ]
    for expr in expressions:
        try:
            assert_expression_safe(expr)
        except ExpressionSafetyError as exc:
            return GateResult(
                name="expression_safety",
                status="blocked",
                message=f"AST safety check failed for {expr!r}: {exc}",
                evidence={"expression": expr, "error": str(exc)},
            )
    return GateResult(
        name="expression_safety",
        status="ok",
        message=(
            f"All {len(expressions)} rule and expression-factor formulas "
            "pass the AST safety whitelist."
        ),
        evidence={"expression_count": len(expressions)},
    )


@gate("leakage_check")
def _leakage_check(spec_path: Path, root: Path) -> GateResult:  # noqa: ARG001
    try:
        spec = load_strategy_spec(spec_path)
    except Exception as exc:
        return GateResult(
            name="leakage_check",
            status="blocked",
            message=f"Could not load spec: {exc}",
        )
    llm_factors = [
        name for name, f in spec.factors.items() if f.source in {"llm_feature", "feature_packet"}
    ]
    evidence: dict[str, object] = {
        "signal_on": spec.execution.signal_on,
        "fill_assumption": spec.execution.fill_assumption,
        "llm_review_enabled": spec.llm_review.enabled,
        "llm_factor_count": len(llm_factors),
        "llm_factors": llm_factors,
    }
    if spec.llm_review.enabled and not llm_factors:
        return GateResult(
            name="leakage_check",
            status="warning",
            message=(
                "llm_review.enabled but no feature_packet factors; "
                "ensure LLM calls are replayed from PIT packets"
            ),
            evidence=evidence,
        )
    return GateResult(
        name="leakage_check",
        status="ok",
        message=(
            f"Execution: signal_on={spec.execution.signal_on!r}, "
            f"fill_assumption={spec.execution.fill_assumption!r}. "
            f"LLM factors: {len(llm_factors)}."
        ),
        evidence=evidence,
    )


@gate("capability_evaluation")
def _capability_evaluation(spec_path: Path, root: Path) -> GateResult:
    from open_composer.capabilities import evaluate_capabilities
    from open_composer.strategy_capabilities import assess_strategy_capabilities

    findings = assess_strategy_capabilities(spec_path)
    registry = evaluate_capabilities(root)
    blocked, warnings, _ = _classify_capability_findings(findings)
    status = "blocked" if blocked else "warning" if warnings else "ok"
    return GateResult(
        name="capability_evaluation",
        status=status,
        message=(
            f"Capability check: {len(blocked)} blocked, {len(warnings)} warnings "
            f"of {len(findings.findings)} capabilities. Registry: {len(registry)} entries."
        ),
        evidence={
            "blocked": blocked,
            "warnings": warnings,
        },
    )


@gate("research_capability_evaluation")
def _research_capability_evaluation(spec_path: Path, root: Path) -> GateResult:
    from open_composer.capabilities import evaluate_capabilities
    from open_composer.strategy_capabilities import assess_strategy_capabilities

    spec = load_strategy_spec(spec_path)
    findings = assess_strategy_capabilities(spec_path)
    registry = evaluate_capabilities(root)
    factor_sources = {factor.source for factor in spec.factors.values()}
    has_packet_trade_logic = bool(factor_sources.intersection({"llm_feature", "feature_packet"}))
    has_llm_trade_logic = spec.llm_review.enabled or "llm_feature" in factor_sources
    has_advisory_context = any(
        not capability.startswith("market.") for capability in spec.required_capabilities
    )

    def is_research_not_applicable(finding: object) -> bool:
        capability = getattr(finding, "capability", "")
        status = getattr(finding, "status", "")
        advisory_context_only = (
            status == "partial"
            and has_advisory_context
            and not spec.llm_review.enabled
            and not has_packet_trade_logic
        )
        if capability == "alpaca_paper_execution":
            return True
        if capability == "llm_quant_workflow" and not has_llm_trade_logic:
            return True
        if capability == "nautilus_trader_backend" and spec.execution.backend != "nautilus_trader":
            return True
        if capability == "python_mvp_backtest" and advisory_context_only:
            return True
        return (
            capability == "tradingview_pine_strategy"
            and advisory_context_only
            and len(spec.universe) == 1
        )

    blocked, warnings, not_applicable = _classify_capability_findings(
        findings, is_not_applicable=is_research_not_applicable
    )
    status = "blocked" if blocked else "warning" if warnings else "ok"
    return GateResult(
        name="research_capability_evaluation",
        status=status,
        message=(
            f"Research capability check: {len(blocked)} blocked, "
            f"{len(warnings)} warnings, {len(not_applicable)} not applicable "
            f"of {len(findings.findings)} capabilities. Registry: {len(registry)} entries."
        ),
        evidence={
            "blocked": blocked,
            "warnings": warnings,
            "not_applicable": not_applicable,
        },
    )


@gate("reference_backtest")
def _reference_backtest(spec_path: Path, root: Path) -> GateResult:
    from open_composer.models.strategy_spec import load_strategy_spec

    spec = load_strategy_spec(spec_path)
    if spec.portfolio.mode == "momentum_signal_router":
        observation_path = root / "reports/execution" / f"{spec.name}-execution-observation.json"
        return GateResult(
            name="reference_backtest",
            status="warning",
            message=(
                "Generic single-symbol backtest is not applicable to momentum_signal_router; "
                "use the frozen lockbox report and target-weight observation parity."
            ),
            evidence={
                "not_applicable": True,
                "reason": "cross_symbol_signal_target_contract",
                "observation_path": str(observation_path),
                "observation_exists": observation_path.exists(),
            },
        )
    from open_composer.engines.backtest_engine import run_backtest

    try:
        result = run_backtest(spec_path, root=root)
        run = result.run
        status = "ok" if (run.signals or 0) > 0 else "warning"
        return GateResult(
            name="reference_backtest",
            status=status,
            message=(
                f"Backtest complete: signals={run.signals}, "
                f"sharpe={run.sharpe_ratio}, return={run.total_return_pct}%"
            ),
            evidence={
                "run_id": run.run_id,
                "signals": run.signals,
                "trades": run.trades,
                "sharpe_ratio": run.sharpe_ratio,
                "total_return_pct": run.total_return_pct,
                "report_path": run.report_path,
                "signal_log_path": run.signal_log_path,
            },
        )
    except Exception as exc:
        return GateResult(
            name="reference_backtest",
            status="blocked",
            message=f"Backtest failed: {exc}",
            evidence={"error": str(exc)},
        )


@gate("factor_lab")
def _factor_lab(spec_path: Path, root: Path) -> GateResult:
    from open_composer.research.factor_lab import run_factor_lab

    result = run_factor_lab(spec_path, root)
    if result.status == "blocked" and result.quality_flags == ["no_custom_factors"]:
        return GateResult(
            name="factor_lab",
            status="ok",
            message="Factor lab not applicable: strategy has no custom factors.",
            evidence={"quality_flags": result.quality_flags, "not_applicable": True},
        )
    status = result.status if result.status in {"ok", "warning", "blocked"} else "warning"
    return GateResult(
        name="factor_lab",
        status=status,  # type: ignore[arg-type]
        message=f"Factor lab status={result.status}; flags={result.quality_flags}",
        evidence={"quality_flags": result.quality_flags, "not_applicable": False},
    )


@gate("alternative_data")
def _alternative_data(spec_path: Path, root: Path) -> GateResult:
    from open_composer.research.alt_data_quality import build_alternative_data_quality_report

    result = build_alternative_data_quality_report(spec_path, root)
    status = result.status if result.status in {"ok", "warning", "blocked"} else "warning"
    return GateResult(
        name="alternative_data",
        status=status,  # type: ignore[arg-type]
        message=f"Alternative data status={result.status}; warnings={result.warnings}",
        evidence={"warnings": result.warnings},
    )


@gate("promotion_report")
def _promotion_report(spec_path: Path, root: Path) -> GateResult:
    from open_composer.research.promotion import build_promotion_report

    result = build_promotion_report(spec_path, root)
    return GateResult(
        name="promotion_report",
        status=result.status,
        message=f"Promotion report status={result.status}; ready={result.ready}",
        evidence={
            "ready": result.ready,
            "report_path": result.report_path,
            "json_path": result.json_path,
        },
    )


@gate("harness_artifacts")
def _harness_artifacts(spec_path: Path, root: Path) -> GateResult:
    """Check that all artifacts required by detected risk domains are present and complete.

    Reads harness/risk_domains.yaml and harness/artifact_contracts.yaml; does not run
    backtests. Returns ``blocked`` when any required artifact is missing or has missing
    fields, ``warning`` when only optional artifacts (none currently) are absent, ``ok``
    when no risk domains are active or every required artifact passes the contract.
    """
    from open_composer.harness.policy import (
        blocking_rules_for_domains,
        check_artifact,
        detect_risk_domains,
        required_artifacts_for_domains,
    )

    try:
        spec = load_strategy_spec(spec_path)
    except Exception as exc:
        return GateResult(
            name="harness_artifacts",
            status="blocked",
            message=f"Could not load spec: {exc}",
        )

    active = detect_risk_domains(spec, root)
    required = sorted(required_artifacts_for_domains(active))
    if not required:
        return GateResult(
            name="harness_artifacts",
            status="ok",
            message="No risk domains active; no harness artifacts required.",
            evidence={"risk_domains": active, "required_artifacts": []},
        )

    statuses = [check_artifact(name, spec.name, root) for name in required]
    missing = [s.name for s in statuses if not s.present]
    incomplete = [s.name for s in statuses if s.present and not s.schema_ok]
    rules = blocking_rules_for_domains(active)
    rule_ids = [r.rule_id for r in rules]

    if missing or incomplete:
        return GateResult(
            name="harness_artifacts",
            status="blocked",
            message=(
                f"Harness artifacts incomplete: missing={missing or '-'}, "
                f"incomplete={incomplete or '-'}, domains={active}"
            ),
            evidence={
                "risk_domains": active,
                "required_artifacts": required,
                "missing": missing,
                "incomplete": incomplete,
                "blocking_rules": rule_ids,
            },
        )
    return GateResult(
        name="harness_artifacts",
        status="ok",
        message=(f"All {len(required)} harness artifacts present for domains={active}."),
        evidence={
            "risk_domains": active,
            "required_artifacts": required,
            "blocking_rules": rule_ids,
        },
    )


@gate("paper_readiness")
def _paper_readiness(spec_path: Path, root: Path) -> GateResult:
    from open_composer.models.strategy_spec import load_strategy_spec
    from open_composer.paper_readiness import assess_paper_strategy_readiness_for_spec

    spec = load_strategy_spec(spec_path)
    result = assess_paper_strategy_readiness_for_spec(spec, root, spec_path=spec_path)
    status = result.status if result.status in {"ok", "warning", "blocked"} else "warning"
    return GateResult(
        name="paper_readiness",
        status=status,  # type: ignore[arg-type]
        message=f"Paper readiness status={result.status}",
        evidence={"status": result.status},
    )
