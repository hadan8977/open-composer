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
    blocked = [f for f in findings.findings if f.status == "blocked"]
    warnings = [f for f in findings.findings if f.status == "warning"]
    status = "blocked" if blocked else "warning" if warnings else "ok"
    return GateResult(
        name="capability_evaluation",
        status=status,
        message=(
            f"Capability check: {len(blocked)} blocked, {len(warnings)} warnings "
            f"of {len(findings.findings)} capabilities. Registry: {len(registry)} entries."
        ),
        evidence={
            "blocked": [f.capability for f in blocked],
            "warnings": [f.capability for f in warnings],
        },
    )


@gate("reference_backtest")
def _reference_backtest(spec_path: Path, root: Path) -> GateResult:
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
                "signals": run.signals,
                "trades": run.trades,
                "sharpe_ratio": run.sharpe_ratio,
                "total_return_pct": run.total_return_pct,
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
    status = result.status if result.status in {"ok", "warning", "blocked"} else "warning"
    return GateResult(
        name="factor_lab",
        status=status,  # type: ignore[arg-type]
        message=f"Factor lab status={result.status}; flags={result.quality_flags}",
        evidence={"quality_flags": result.quality_flags},
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
