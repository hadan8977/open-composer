from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

from open_composer.capabilities import load_registry
from open_composer.config import ensure_dir, project_root
from open_composer.expressions import ExpressionError, validate_expression
from open_composer.feature_packets import inspect_feature_packet
from open_composer.models.execution_backend import (
    ExecutionBackendPlan,
    NautilusBacktestPlan,
    NautilusCustomDataBinding,
    NautilusPaperPlan,
)
from open_composer.models.strategy_spec import StrategySpec
from open_composer.storage import write_json
from open_composer.timeframes import supported_timeframes, timeframe_supported


def nautilus_trader_available() -> bool:
    return importlib.util.find_spec("nautilus_trader") is not None


def build_nautilus_trader_plan(
    spec_path: Path | str,
    root: Path | None = None,
) -> ExecutionBackendPlan:
    path = Path(spec_path)
    base = root or _infer_spec_root(path)
    spec = _load_strategy_for_plan(path)
    registry = load_registry(base)
    expression_errors = _expression_errors(spec, base)
    llm_feature_factors = _llm_feature_factors(spec)
    feature_packet_factors = _feature_packet_factors(spec)
    required_capabilities = list(spec.required_capabilities)
    reasons: list[str] = []

    if expression_errors:
        reasons.extend(expression_errors)
        status = "blocked"
    elif not timeframe_supported("nautilus_trader", spec.timeframe):
        supported = ", ".join(supported_timeframes("nautilus_trader"))
        reasons.append(
            f"unsupported NautilusTrader timeframe {spec.timeframe}; supported: {supported}"
        )
        status = "blocked"
    elif not nautilus_trader_available():
        reasons.append("nautilus_trader package is not installed")
        status = "unavailable"
    else:
        status = "supported"
        capability_issues = _capability_issues(spec, registry)
        if capability_issues:
            reasons.extend(capability_issues)
            status = "partial"
        if len(spec.universe) > 1:
            reasons.append(
                "multi-symbol universes need a portfolio or target-weight mapping before "
                "full backend parity"
            )
            status = "partial"
        if spec.llm_review.enabled:
            reasons.append("LLM review stays advisory and is replayed outside the backend loop")
            status = "partial"
        if llm_feature_factors:
            reasons.append(
                "LLM feature factors must be replayed from saved packets, not generated in "
                f"the backend loop: {', '.join(llm_feature_factors)}"
            )
            status = "partial"
        if feature_packet_factors:
            reasons.append(
                "feature_packet factors are replayed from saved point-in-time packets: "
                + ", ".join(feature_packet_factors)
            )
            status = "partial"

    selected_backend = spec.execution.backend
    if selected_backend == "nautilus_trader":
        if len(spec.universe) > 1:
            selected_backend = "python_reference"
        elif status in {"supported", "partial"} and nautilus_trader_available():
            selected_backend = "nautilus_trader"
        else:
            selected_backend = "python_reference"

    if not reasons:
        reasons.append("deterministic OHLCV rules can be mapped to the NautilusTrader backend")

    return ExecutionBackendPlan(
        strategy_id=spec.name,
        strategy_name=spec.name,
        selected_backend=selected_backend,
        execution_mode=spec.execution.mode,
        broker=spec.execution.broker,
        data_source=spec.data.source,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        supported=status in {"supported", "partial"},
        status=status,
        reasons=reasons,
        factor_names=sorted(spec.factors),
        llm_feature_factor_names=llm_feature_factors,
        feature_packet_factor_names=feature_packet_factors,
        required_capabilities=required_capabilities,
        nautilus_installed=nautilus_trader_available(),
    )


def build_nautilus_backtest_plan(
    spec_path: Path | str,
    root: Path | None = None,
    *,
    run_id_value: str,
    version_id: str | None = None,
    spec_hash: str | None = None,
) -> NautilusBacktestPlan:
    path = Path(spec_path)
    base = root or _infer_spec_root(path)
    spec = _load_strategy_for_plan(path)
    compatibility = build_nautilus_trader_plan(
        path,
        base,
    )
    custom_data_bindings = _custom_data_bindings(spec, base)
    factor_expressions = _expression_factors(spec)
    data_path = _resolved_data_path(spec, base)
    bar_type = f"{spec.timeframe}-ohlcv"
    reasons = list(compatibility.reasons)
    if data_path is None:
        reasons.append("data path is not declared on the StrategySpec")
    if custom_data_bindings and any(
        not Path(binding.path).exists() for binding in custom_data_bindings
    ):
        reasons.append("one or more custom data packets are missing on disk")
    for binding in custom_data_bindings:
        if binding.point_in_time_status != "complete":
            reasons.append(
                f"custom data binding {binding.factor_name} is "
                f"{binding.point_in_time_status}: " + "; ".join(binding.replay_warnings[:3])
            )
    status = compatibility.status
    if reasons and status == "supported":
        status = "partial"
    return NautilusBacktestPlan(
        strategy_id=spec.name,
        strategy_name=spec.name,
        run_id=run_id_value,
        version_id=version_id,
        spec_hash=spec_hash,
        selected_backend=compatibility.selected_backend,
        execution_mode=spec.execution.mode,
        broker=spec.execution.broker,
        data_source=spec.data.source,
        data_path=str(data_path) if data_path else None,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        bar_type=bar_type,
        fill_assumption=spec.execution.fill_assumption,
        supported=compatibility.supported,
        status=status,
        reasons=reasons or ["NautilusTrader-compatible OHLCV strategy plan"],
        factor_names=sorted(spec.factors),
        expression_factor_names=sorted(factor_expressions),
        llm_feature_factor_names=sorted(
            binding.factor_name
            for binding in custom_data_bindings
            if binding.source == "llm_feature"
        ),
        factor_expressions=factor_expressions,
        custom_data_bindings=custom_data_bindings,
        feature_packet_factor_names=_feature_packet_factors(spec),
        required_capabilities=list(spec.required_capabilities),
        nautilus_installed=nautilus_trader_available(),
    )


def build_nautilus_paper_plan(
    spec_path: Path | str,
    root: Path | None = None,
    *,
    run_id_value: str,
    version_id: str | None = None,
    spec_hash: str | None = None,
) -> NautilusPaperPlan:
    path = Path(spec_path)
    base = root or _infer_spec_root(path)
    spec = _load_strategy_for_plan(path)
    compatibility = build_nautilus_trader_plan(path, base)
    custom_data_bindings = _custom_data_bindings(spec, base)
    reasons = list(compatibility.reasons)
    status = compatibility.status
    selected_backend = "nautilus_paper"

    if spec.execution.mode != "paper_auto":
        reasons.append("Nautilus paper runtime requires execution.mode=paper_auto")
        status = "partial"
    if spec.execution.broker != "alpaca_paper":
        reasons.append("Nautilus paper runtime currently targets broker=alpaca_paper")
        status = "partial"
    if len(spec.universe) > 1:
        reasons.append("Nautilus paper runtime is single-symbol until portfolio routing exists")
        status = "partial"
        selected_backend = "python_reference"
    if not nautilus_trader_available():
        selected_backend = "python_reference"
    if custom_data_bindings and any(
        binding.point_in_time_status != "complete" for binding in custom_data_bindings
    ):
        status = "partial"
        reasons.append("one or more Nautilus paper custom data bindings are not PIT-complete")
    if selected_backend == "nautilus_paper":
        reasons.append(
            "Nautilus paper runtime emits latest-bar signals and delegates paper orders to "
            "the Alpaca Paper safety gate."
        )
    elif status == "supported":
        status = "partial"

    return NautilusPaperPlan(
        strategy_id=spec.name,
        strategy_name=spec.name,
        run_id=run_id_value,
        version_id=version_id,
        spec_hash=spec_hash,
        selected_backend=selected_backend,
        execution_mode=spec.execution.mode,
        broker=spec.execution.broker,
        data_source=spec.data.source,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        supported=compatibility.supported,
        status=status,
        reasons=reasons,
        required_capabilities=list(spec.required_capabilities),
        custom_data_bindings=custom_data_bindings,
        nautilus_installed=nautilus_trader_available(),
    )


def write_nautilus_trader_plan(path: Path, plan: ExecutionBackendPlan) -> Path:
    ensure_dir(path.parent)
    write_json(path, plan)
    return path


def write_nautilus_backtest_plan(path: Path, plan: NautilusBacktestPlan) -> Path:
    ensure_dir(path.parent)
    write_json(path, plan)
    return path


def write_nautilus_paper_plan(path: Path, plan: NautilusPaperPlan) -> Path:
    ensure_dir(path.parent)
    write_json(path, plan)
    return path


def _expression_errors(spec: StrategySpec, root: Path) -> list[str]:
    errors: list[str] = []
    for expression in spec.all_expressions():
        try:
            validate_expression(expression, spec.factors, root=root)
        except ExpressionError as exc:
            errors.append(f"{expression}: {exc}")
    return errors


def _llm_feature_factors(spec: StrategySpec) -> list[str]:
    return sorted(name for name, factor in spec.factors.items() if factor.source == "llm_feature")


def _feature_packet_factors(spec: StrategySpec) -> list[str]:
    return sorted(
        name for name, factor in spec.factors.items() if factor.source == "feature_packet"
    )


def _custom_data_bindings(spec: StrategySpec, root: Path) -> list[NautilusCustomDataBinding]:
    bindings: list[NautilusCustomDataBinding] = []
    for name, factor in spec.factors.items():
        if factor.source not in {"llm_feature", "feature_packet"}:
            continue
        if not factor.path:
            continue
        path = _resolve_path(root, factor.path)
        metadata = _custom_data_metadata(path, str(factor.field or ""))
        bindings.append(
            NautilusCustomDataBinding(
                factor_name=name,
                source=factor.source,
                path=str(path),
                field=str(factor.field or ""),
                default=factor.default,
                description=factor.description,
                **metadata,
            )
        )
    return bindings


def _custom_data_metadata(path: Path, field: str) -> dict[str, object]:
    inspection = inspect_feature_packet(path, field)
    return {
        "exists": inspection.exists,
        "record_count": inspection.record_count,
        "first_timestamp": inspection.first_timestamp,
        "last_timestamp": inspection.last_timestamp,
        "point_in_time_status": inspection.point_in_time_status,
        "replay_warnings": inspection.replay_warnings,
    }


def _expression_factors(spec: StrategySpec) -> dict[str, str]:
    return {
        name: factor.expression or ""
        for name, factor in spec.factors.items()
        if factor.source == "expression" and factor.expression
    }


def _capability_issues(spec: StrategySpec, registry) -> list[str]:
    known = {capability.id: capability for capability in registry.capabilities}
    issues: list[str] = []
    missing = [capability for capability in spec.required_capabilities if capability not in known]
    if missing:
        issues.append("unknown required capabilities: " + ", ".join(sorted(missing)))
    non_market = [
        capability
        for capability in spec.required_capabilities
        if capability in known and known[capability].kind != "market"
    ]
    if non_market:
        issues.append(
            "replayable custom data adapters are required for non-market capabilities: "
            + ", ".join(sorted(non_market))
        )
    return issues


def _load_strategy_for_plan(path: Path) -> StrategySpec:
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        msg = f"{path} must contain a YAML mapping"
        raise ValueError(msg)
    return StrategySpec.model_validate(raw)


def _infer_spec_root(path: Path) -> Path:
    if len(path.parents) >= 3 and path.parents[1].name == "strategy_specs":
        return path.parents[2]
    return project_root()


def _resolved_data_path(spec: StrategySpec, root: Path) -> Path | None:
    if not spec.data.path:
        return None
    candidate = Path(spec.data.path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _resolve_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return root / candidate
