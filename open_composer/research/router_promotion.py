from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.contracts import write_research_contract
from open_composer.research.kernel import GateResult, ResearchArtifactWriter, ResearchRunIndexRecord
from open_composer.research.metadata import research_run_manifest, runtime_payload, search_space
from open_composer.research.promotion import (
    PassSummary,
    PromotionReport,
    PromotionStatus,
    _evidence_acquisition_tier,
    _feature_packet_check,
    _feature_packet_paths,
    _five_pass_markdown_rows,
    _harness_artifacts_promotion_check,
    _pass_summary,
    _promotion_pass_fields,
    _relpath,
    _research_design_check,
)
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash


@dataclass(frozen=True)
class RouterPromotionConfig:
    mode: str
    report_mode: str
    research_suffix: str
    research_check_name: str
    research_manifest_key: str
    target_weights_suffix: str | None = None
    llm_suffix: str | None = None
    llm_manifest_key: str | None = None


ROUTER_PROMOTION_CONFIGS: dict[str, RouterPromotionConfig] = {
    "adaptive_intraday_internal_router": RouterPromotionConfig(
        mode="adaptive_intraday_internal_router",
        report_mode="adaptive_intraday_router_promotion",
        research_suffix="adaptive-intraday-router",
        research_check_name="adaptive_router_research",
        research_manifest_key="adaptive_router_research_path",
        llm_suffix="llm-adaptive-router",
        llm_manifest_key="llm_adaptive_router_path",
    ),
    "hybrid_adaptive_router": RouterPromotionConfig(
        mode="hybrid_adaptive_router",
        report_mode="hybrid_adaptive_router_promotion",
        research_suffix="hybrid-adaptive-router",
        research_check_name="hybrid_router_research",
        research_manifest_key="hybrid_router_research_path",
        target_weights_suffix="target-weights",
    ),
    "beta_exposure_router": RouterPromotionConfig(
        mode="beta_exposure_router",
        report_mode="beta_exposure_router_promotion",
        research_suffix="beta-exposure-router",
        research_check_name="beta_router_research",
        research_manifest_key="beta_router_research_path",
        target_weights_suffix="beta-target-weights",
    ),
}


def build_router_promotion_report(
    *,
    spec_path: Path,
    root: Path,
    writer: ResearchArtifactWriter,
    spec: StrategySpec,
    started_at: float | None = None,
    out_of_sample_ratio: float = 0.3,
    walk_forward_folds: int = 3,
) -> PromotionReport:
    config = ROUTER_PROMOTION_CONFIGS.get(spec.portfolio.mode)
    if config is None:
        msg = f"unsupported router promotion mode: {spec.portfolio.mode}"
        raise ValueError(msg)

    started = started_at if started_at is not None else perf_counter()
    research_path = root / "reports" / "research" / f"{spec.name}-{config.research_suffix}.json"
    report_path = root / "reports" / "research" / f"{spec.name}-promotion.md"
    json_path = root / "reports" / "research" / f"{spec.name}-promotion.json"
    contract_path = write_research_contract(spec_path, root)
    research_payload = _load_optional_json(research_path)
    llm_path = (
        root / "reports" / "research" / f"{spec.name}-{config.llm_suffix}.json"
        if config.llm_suffix
        else None
    )
    llm_payload = _load_optional_json(llm_path) if llm_path else None
    target_weights_path = (
        root / "reports" / "execution" / f"{spec.name}-{config.target_weights_suffix}.json"
        if config.target_weights_suffix
        else None
    )
    target_weights_payload = (
        _load_optional_json(target_weights_path) if target_weights_path else None
    )

    data_profile = _dict_value((research_payload or {}).get("data_profile"))
    acceptance_gate = _dict_value((research_payload or {}).get("acceptance_gate"))
    research_pass_status = _dict_value((research_payload or {}).get("pass_status"))
    candidates = _dict_list((research_payload or {}).get("candidates"))
    selected_route = _selected_candidate(spec, candidates, llm_payload)
    benchmark_family = _benchmark_family(selected_route)

    checks = _router_checks(
        config=config,
        spec=spec,
        root=root,
        research_path=research_path,
        research_payload=research_payload,
        acceptance_gate=acceptance_gate,
        data_profile=data_profile,
        selected_route=selected_route,
        target_weights_path=target_weights_path,
        target_weights_payload=target_weights_payload,
        llm_path=llm_path,
        llm_payload=llm_payload,
    )
    ready = all(check.status == "ok" for check in checks)
    status: PromotionStatus = (
        "blocked"
        if any(check.status == "blocked" for check in checks)
        else "warning"
        if any(check.status == "warning" for check in checks)
        else "ok"
    )
    five_pass_checks = _router_pass_summary(
        spec=spec,
        ready=ready,
        checks=checks,
        research_payload=research_payload,
        research_pass_status=research_pass_status,
        acceptance_gate=acceptance_gate,
        llm_payload=llm_payload,
    )
    gate_summary = _router_gate_summary(checks, five_pass_checks, benchmark_family)
    research_cost = _dict_value((research_payload or {}).get("research_cost"))
    trial_count = int(
        research_cost.get("estimated_total_backtest_passes")
        or research_cost.get("candidate_count")
        or len(candidates)
        or 1
    )
    manifest = research_run_manifest(
        root=root,
        strategy=spec,
        source_path=spec_path,
        trial_count=trial_count,
        search_space_payload=search_space(
            family=config.report_mode,
            candidate_count=len(candidates) or 1,
            parameter_ranges=_parameter_ranges(spec),
            filters=[
                f"out_of_sample_ratio={out_of_sample_ratio}",
                f"walk_forward_folds={walk_forward_folds}",
                f"uses_existing_{config.research_suffix}_report",
            ],
        ),
        data_profile=data_profile,
        feature_packet_paths=_feature_packet_paths(spec),
        runtime=runtime_payload(started, {}),
    )
    manifest["research_contract_path"] = _relpath(contract_path, root)
    manifest[config.research_manifest_key] = (
        _relpath(research_path, root) if research_payload else None
    )
    if config.llm_manifest_key and llm_path:
        manifest[config.llm_manifest_key] = _relpath(llm_path, root) if llm_payload else None

    index_record = ResearchRunIndexRecord(
        run_id=f"promotion-{spec.name}-{strategy_content_hash(spec)[:12]}",
        strategy_name=spec.name,
        source_spec_path=_relpath(spec_path, root),
        spec_hash=strategy_content_hash(spec),
        status=status,
        kind="promotion",
        data_profile=data_profile,
        candidate_count=len(candidates) or 1,
        trial_count=trial_count,
        runtime_seconds=(manifest.get("runtime") or {}).get("total")
        if isinstance(manifest.get("runtime"), dict)
        else None,
        gate_status=status,
        blocked_items=[str(item) for item in gate_summary.get("blocked_checks", [])],
        warning_items=[str(item) for item in gate_summary.get("warning_checks", [])],
        report_path=_relpath(report_path, root),
        json_path=_relpath(json_path, root),
        contract_path=_relpath(contract_path, root),
        source_artifacts={
            "router_research": _relpath(research_path, root) if research_payload else None,
            "router_target_weights": _relpath(target_weights_path, root)
            if target_weights_payload and target_weights_path
            else None,
            "llm_router": _relpath(llm_path, root) if llm_payload and llm_path else None,
        },
    )

    _write_router_promotion_json(
        path=json_path,
        config=config,
        spec_path=spec_path,
        spec=spec,
        status=status,
        ready=ready,
        checks=checks,
        benchmark_family=benchmark_family,
        data_profile=data_profile,
        manifest=manifest,
        five_pass_checks=five_pass_checks,
        gate_summary=gate_summary,
        index_record=index_record,
        research_payload=research_payload,
        llm_payload=llm_payload,
        target_weights_payload=target_weights_payload,
        selected_route=selected_route,
    )
    writer.append_index(index_record)
    _write_router_promotion_markdown(
        path=report_path,
        config=config,
        spec_path=spec_path,
        spec=spec,
        status=status,
        ready=ready,
        checks=checks,
        benchmark_family=benchmark_family,
        json_path=json_path,
        data_profile=data_profile,
        manifest=manifest,
        five_pass_checks=five_pass_checks,
        selected_route=selected_route,
    )
    return PromotionReport(
        strategy_name=spec.name,
        source_spec_path=str(spec_path),
        status=status,
        ready=ready,
        checks=checks,
        report_path=str(report_path),
        json_path=str(json_path),
        **_promotion_pass_fields(five_pass_checks),
        five_pass_checks=five_pass_checks,
    )


def _router_checks(
    *,
    config: RouterPromotionConfig,
    spec: StrategySpec,
    root: Path,
    research_path: Path,
    research_payload: dict[str, Any] | None,
    acceptance_gate: dict[str, Any],
    data_profile: dict[str, Any],
    selected_route: dict[str, Any] | None,
    target_weights_path: Path | None,
    target_weights_payload: dict[str, Any] | None,
    llm_path: Path | None,
    llm_payload: dict[str, Any] | None,
) -> list[GateResult]:
    checks: list[GateResult] = [
        _research_check(config, research_path, research_payload, acceptance_gate),
        _out_of_sample_check(selected_route, acceptance_gate),
        _walk_forward_check(research_payload, acceptance_gate),
        _strict_data_check(spec, data_profile),
        _feature_packet_check(spec, root),
        _factor_lab_check(selected_route),
        _alternative_data_check(spec, data_profile),
        _llm_contribution_check(config, spec, llm_path, llm_payload),
        _execution_check(config, spec, target_weights_path, target_weights_payload),
        _benchmark_check(selected_route),
        _harness_artifacts_promotion_check(spec, root),
        _research_design_check(spec),
    ]
    return checks


def _research_check(
    config: RouterPromotionConfig,
    research_path: Path,
    research_payload: dict[str, Any] | None,
    acceptance_gate: dict[str, Any],
) -> GateResult:
    if research_payload is None:
        return GateResult(
            name=config.research_check_name,
            status="blocked",
            message=f"Router promotion requires {config.research_suffix} research evidence.",
            details={"expected_path": str(research_path)},
        )
    quality_flags = _string_list(acceptance_gate.get("quality_flags"))
    passed = bool(acceptance_gate.get("passed"))
    status: PromotionStatus = "ok" if passed and not quality_flags else "warning"
    return GateResult(
        name=config.research_check_name,
        status=status,
        message=(
            "Router research acceptance gate passed."
            if status == "ok"
            else "Router research exists but has acceptance warnings."
        ),
        details={"acceptance_gate": acceptance_gate, "quality_flags": quality_flags},
    )


def _out_of_sample_check(
    selected_route: dict[str, Any] | None,
    acceptance_gate: dict[str, Any],
) -> GateResult:
    if selected_route is None:
        return GateResult(
            name="out_of_sample",
            status="blocked",
            message="No selected router candidate is available for OOS review.",
            details={},
        )
    oos = _dict_value(selected_route.get("out_of_sample"))
    sharpe = _first_number(
        oos,
        acceptance_gate,
        keys=("sharpe_ratio", "oos_sharpe_ratio"),
    )
    traded_days = _first_number(oos, acceptance_gate, keys=("traded_days", "oos_traded_days"))
    quality_flags = _string_list(selected_route.get("quality_flags")) + _string_list(
        acceptance_gate.get("quality_flags")
    )
    status: PromotionStatus = "warning" if quality_flags else "ok"
    if sharpe is None and not oos:
        status = "blocked"
    return GateResult(
        name="out_of_sample",
        status=status,
        message="Selected router candidate includes out-of-sample evidence.",
        details={
            "sharpe_ratio": sharpe,
            "traded_days": traded_days,
            "quality_flags": sorted(set(quality_flags)),
            "out_of_sample": oos,
        },
    )


def _walk_forward_check(
    research_payload: dict[str, Any] | None,
    acceptance_gate: dict[str, Any],
) -> GateResult:
    rows = _dict_list((research_payload or {}).get("walk_forward"))
    fold_count = int(
        acceptance_gate.get("walk_forward_fold_count")
        if isinstance(acceptance_gate.get("walk_forward_fold_count"), int)
        else len(rows)
    )
    positive_folds = acceptance_gate.get("walk_forward_positive_alpha_folds")
    status: PromotionStatus = "ok" if fold_count >= 2 else "blocked"
    if positive_folds is not None and isinstance(positive_folds, int | float):
        status = "ok" if positive_folds >= max(1, fold_count // 2) else "warning"
    return GateResult(
        name="walk_forward",
        status=status,
        message=(
            "Router walk-forward evidence was found."
            if rows
            else "Router walk-forward evidence is missing."
        ),
        details={
            "fold_count": fold_count,
            "positive_alpha_folds": positive_folds,
            "folds": rows,
            "validation_policy": "router_research_artifact",
        },
    )


def _strict_data_check(spec: StrategySpec, data_profile: dict[str, Any]) -> GateResult:
    source_mode = str(data_profile.get("source_mode") or data_profile.get("data_source_mode") or "")
    tier = _evidence_acquisition_tier(spec, data_profile)
    blockers: list[str] = []
    if spec.data.source == "sample":
        blockers.append("sample data is workflow evidence only")
    if tier in {"sample_smoke", "fixture_replay", "cached_live", "research_cross_check"}:
        blockers.append(f"acquisition_tier={tier} is not paper-ready")
    if any(token in source_mode for token in ["sample", "fixture", "fallback"]):
        blockers.append(f"data_source_mode={source_mode} is not paper-ready")
    return GateResult(
        name="strict_data",
        status="blocked" if blockers else "ok",
        message=(
            "Router promotion requires research_strict or paper_ready data; " + "; ".join(blockers)
            if blockers
            else "Router data profile is not sample, fixture, or fallback evidence."
        ),
        details={
            "data_source": spec.data.source,
            "data_source_mode": source_mode,
            "evidence_acquisition_tier": tier,
            "warnings": data_profile.get("warnings", []),
        },
    )


def _factor_lab_check(selected_route: dict[str, Any] | None) -> GateResult:
    quality_flags = _string_list((selected_route or {}).get("quality_flags"))
    return GateResult(
        name="factor_lab",
        status="warning" if quality_flags else "ok",
        message=(
            "Selected router candidate has quality flags."
            if quality_flags
            else "Router candidate quality flags are clear."
        ),
        details={"quality_flags": quality_flags},
    )


def _alternative_data_check(
    spec: StrategySpec,
    data_profile: dict[str, Any],
) -> GateResult:
    uses_alt_data = bool(spec.llm_review.enabled or _feature_packet_paths(spec))
    if not uses_alt_data:
        return GateResult(
            name="alternative_data",
            status="ok",
            message="Router strategy does not use LLM/news/alternative-data factors.",
            details={},
        )
    warnings = _string_list(data_profile.get("warnings"))
    return GateResult(
        name="alternative_data",
        status="warning" if warnings else "ok",
        message=(
            "Alternative-data usage is present; review data-profile warnings."
            if warnings
            else "Alternative-data usage has no data-profile warnings."
        ),
        details={"warnings": warnings, "feature_packets": _feature_packet_paths(spec)},
    )


def _llm_contribution_check(
    config: RouterPromotionConfig,
    spec: StrategySpec,
    llm_path: Path | None,
    llm_payload: dict[str, Any] | None,
) -> GateResult:
    if not bool(spec.llm_review.enabled or _feature_packet_paths(spec)):
        return GateResult(
            name="llm_contribution",
            status="ok",
            message="LLM contribution is not applicable for this router.",
            details={"applicable": False},
        )
    status = _llm_pass_status(llm_payload)
    if llm_payload is not None and status == "pass":
        return GateResult(
            name="llm_contribution",
            status="ok",
            message="LLM/news contribution evidence exists for the router selection.",
            details={"applicable": True, "llm_path": str(llm_path), "payload_status": status},
        )
    return GateResult(
        name="llm_contribution",
        status="warning",
        message=(
            f"{config.mode} uses LLM/news inputs but independent lift evidence is incomplete."
        ),
        details={"applicable": True, "llm_path": str(llm_path) if llm_path else None},
    )


def _execution_check(
    config: RouterPromotionConfig,
    spec: StrategySpec,
    target_weights_path: Path | None,
    target_weights_payload: dict[str, Any] | None,
) -> GateResult:
    if target_weights_path is None:
        return GateResult(
            name="execution_reality",
            status="warning",
            message=f"{config.mode} has no target-weight mapping artifact configured.",
            details={"blockers": [f"{config.mode} needs target-weight mapping"]},
        )
    mapping = _target_mapping_summary(target_weights_payload)
    blockers = list(mapping["blockers"])
    status: PromotionStatus = (
        "ok" if mapping["target_weight_mapping_status"] == "pass" else "warning"
    )
    return GateResult(
        name="execution_reality",
        status=status,
        message=(
            "Router target-weight mapping artifact passed parity checks."
            if status == "ok"
            else "Router target-weight mapping artifact needs review."
        ),
        details={
            **mapping,
            "target_weight_mapping_path": str(target_weights_path),
            "blockers": blockers,
        },
    )


def _benchmark_check(selected_route: dict[str, Any] | None) -> GateResult:
    family = _benchmark_family(selected_route)
    status: PromotionStatus = "ok" if family.get("complete") else "warning"
    return GateResult(
        name="benchmark_family",
        status=status,
        message=(
            "Router benchmark family is represented in the selected candidate."
            if status == "ok"
            else "Router benchmark family is incomplete."
        ),
        details=family,
    )


def _router_pass_summary(
    *,
    spec: StrategySpec,
    ready: bool,
    checks: list[GateResult],
    research_payload: dict[str, Any] | None,
    research_pass_status: dict[str, Any],
    acceptance_gate: dict[str, Any],
    llm_payload: dict[str, Any] | None,
) -> PassSummary:
    blocked = {check.name for check in checks if check.status == "blocked"}
    warnings = {check.name for check in checks if check.status == "warning"}
    workflow_pass = (
        "pass" if research_payload is not None and "feature_packets" not in blocked else "fail"
    )
    research_pass = (
        "pass"
        if bool(research_pass_status.get("research_pass") or acceptance_gate.get("passed"))
        and not {"out_of_sample", "walk_forward"}.intersection(blocked)
        else "fail"
    )
    if not bool(spec.llm_review.enabled or _feature_packet_paths(spec)):
        llm_pass = "not_applicable"
        llm_reason = "strategy does not use LLM review or LLM/feature packet factors"
    elif _llm_pass_status(llm_payload) == "pass":
        llm_pass = "pass"
        llm_reason = "independent LLM/news contribution evidence is present"
    else:
        llm_pass = "fail"
        llm_reason = "LLM/news contribution evidence is missing or not independently positive"
    return _pass_summary(
        workflow_pass=workflow_pass,
        research_pass=research_pass,
        llm_contribution_pass=llm_pass,
        paper_ready_pass="pass" if ready else "fail",
        expression_safety_pass="pass",
        workflow_reason=(
            "router research artifact exists and feature packets are PIT-complete"
            if workflow_pass == "pass"
            else "missing router research artifact or PIT-complete feature packets"
        ),
        research_reason=(
            "router acceptance gate passed"
            if research_pass == "pass"
            else "router acceptance gate is blocked or incomplete"
        ),
        llm_contribution_reason=llm_reason,
        paper_ready_reason=(
            "all router promotion checks are ok"
            if ready
            else "blocked checks: " + ", ".join(sorted(blocked or warnings))
        ),
        expression_safety_reason="router promotion reuses StrategySpec expression safety gates",
    )


def _router_gate_summary(
    checks: list[GateResult],
    five_pass_checks: PassSummary,
    benchmark_family: dict[str, Any],
) -> dict[str, Any]:
    blocked = sorted(check.name for check in checks if check.status == "blocked")
    warning = sorted(check.name for check in checks if check.status == "warning")
    return {
        "workflow_pass": five_pass_checks.get("workflow_pass") == "pass",
        "research_pass": five_pass_checks.get("research_pass") == "pass",
        "llm_contribution_pass": None
        if five_pass_checks.get("llm_contribution_pass") == "not_applicable"
        else five_pass_checks.get("llm_contribution_pass") == "pass",
        "paper_ready_pass": five_pass_checks.get("paper_ready_pass") == "pass",
        "blocked_checks": blocked,
        "warning_checks": warning,
        "benchmark_family_complete": bool(benchmark_family.get("complete", False)),
    }


def _write_router_promotion_json(
    *,
    path: Path,
    config: RouterPromotionConfig,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[GateResult],
    benchmark_family: dict[str, Any],
    data_profile: dict[str, Any],
    manifest: dict[str, Any],
    five_pass_checks: PassSummary,
    gate_summary: dict[str, Any],
    index_record: ResearchRunIndexRecord,
    research_payload: dict[str, Any] | None,
    llm_payload: dict[str, Any] | None,
    target_weights_payload: dict[str, Any] | None,
    selected_route: dict[str, Any] | None,
) -> Path:
    payload = {
        "mode": config.report_mode,
        "strategy_name": spec.name,
        "source_spec_path": str(spec_path),
        "status": status,
        "ready": ready,
        "gate_summary": gate_summary,
        "research_run_index_record": index_record.model_dump(mode="json"),
        **_promotion_pass_fields(five_pass_checks),
        "five_pass_checks": dict(five_pass_checks),
        "checks": [check.model_dump(mode="json") for check in checks],
        "selected_route": selected_route,
        "benchmark_family": benchmark_family,
        "data_profile": data_profile,
        "evidence_acquisition_tier": _evidence_acquisition_tier(spec, data_profile),
        "research_manifest": manifest,
        "router_research": research_payload,
        "llm_router": llm_payload,
        "target_weight_mapping": target_weights_payload,
        "safety_note": (
            "Router promotion ready means workflow, research, LLM contribution, and "
            "paper-readiness gates passed; it is not a promise of live returns."
        ),
    }
    return write_json(path, payload)


def _write_router_promotion_markdown(
    *,
    path: Path,
    config: RouterPromotionConfig,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[GateResult],
    benchmark_family: dict[str, Any],
    json_path: Path,
    data_profile: dict[str, Any],
    manifest: dict[str, Any],
    five_pass_checks: PassSummary,
    selected_route: dict[str, Any] | None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Router Promotion Report: {spec.name}",
        "",
        f"- Mode: `{config.report_mode}`",
        f"- Status: `{status}`",
        f"- Ready for paper: `{'yes' if ready else 'no'}`",
        f"- Data source mode: `{data_profile.get('source_mode') or 'unknown'}`",
        f"- Trial count: `{manifest.get('trial_count')}`",
        f"- Source spec: `{spec_path}`",
        f"- JSON report: `{json_path}`",
        "",
        "## Five-Pass Checks",
        "",
        "| Pass | Status | Reason |",
        "|---|---|---|",
        *_five_pass_markdown_rows(five_pass_checks),
        "",
        "## Selected Route",
        "",
        f"- `{json.dumps(selected_route or {}, sort_keys=True)}`",
        "",
        "## Checks",
        "",
    ]
    for check in checks:
        lines.extend(
            [
                f"### {check.name}",
                f"- Status: `{check.status}`",
                f"- Message: {check.message}",
            ]
        )
        if check.details:
            lines.append(f"- Details: `{json.dumps(check.details, sort_keys=True)}`")
        lines.append("")
    lines.extend(["## Benchmark Family", ""])
    lines.append(f"- Complete: `{benchmark_family.get('complete')}`")
    lines.append(f"- Missing: `{', '.join(benchmark_family.get('missing', [])) or 'none'}`")
    lines.extend(["", "## Research Manifest", ""])
    lines.append(f"- Spec hash: `{manifest.get('spec_hash')}`")
    lines.append(f"- Git commit: `{manifest.get('git_commit') or 'unknown'}`")
    lines.append(f"- Git dirty: `{manifest.get('git_dirty')}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _selected_candidate(
    spec: StrategySpec,
    candidates: list[dict[str, Any]],
    llm_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    selected_label = spec.portfolio.selected_route_label
    if llm_payload:
        selected_label = (
            _nested_get(llm_payload, "choice", "selected_label")
            or _nested_get(llm_payload, "selected", "route", "label")
            or selected_label
        )
    for candidate in candidates:
        if selected_label and _candidate_label(candidate) == selected_label:
            return candidate
    return candidates[0] if candidates else None


def _candidate_label(candidate: dict[str, Any]) -> str | None:
    label = _nested_get(candidate, "route", "label") or _nested_get(candidate, "params", "label")
    if label:
        return str(label)
    params = _dict_value(candidate.get("params"))
    if not params:
        return None
    holding_mode = params.get("holding_mode")
    lookback = params.get("momentum_lookback_days")
    top_n = params.get("top_n")
    market_sma = params.get("market_sma_days")
    min_momentum = params.get("min_momentum_pct")
    weight = params.get("max_position_weight")
    if holding_mode is not None and lookback is not None and top_n is not None:
        gate = "nogate" if market_sma is None else f"qsm{market_sma}"
        return f"{holding_mode}:lb{lookback}_top{top_n}_{gate}_min{min_momentum:g}_w{weight:g}"
    return None


def _benchmark_family(selected_route: dict[str, Any] | None) -> dict[str, Any]:
    full = _dict_value((selected_route or {}).get("full_window"))
    oos = _dict_value((selected_route or {}).get("out_of_sample"))
    market_symbol = full.get("market_symbol") or oos.get("market_symbol")
    benchmark_symbol = full.get("benchmark_symbol") or oos.get("benchmark_symbol")
    best_symbol = full.get("best_symbol") or oos.get("best_symbol")
    benchmarks = {
        "same_symbol_buy_hold": {
            "status": "ok" if benchmark_symbol else "missing",
            "symbol": benchmark_symbol,
            "return_pct": full.get("benchmark_buy_hold_return_pct")
            or full.get("market_buy_hold_return_pct"),
        },
        "equal_weight_universe": {
            "status": "ok"
            if _any_key(
                (full, oos),
                ("equal_weight_buy_hold_return_pct", "universe_equal_weight_buy_hold_pct"),
            )
            else "missing",
            "return_pct": full.get("equal_weight_buy_hold_return_pct")
            or full.get("universe_equal_weight_buy_hold_pct"),
        },
        "market_proxy": {
            "status": "ok" if market_symbol else "not_applicable",
            "proxy": market_symbol,
            "return_pct": full.get("market_buy_hold_return_pct"),
        },
        "sector_theme_proxy": {
            "status": "not_applicable",
            "proxy": None,
        },
        "cash_proxy": {"status": "ok", "return_pct": 0.0},
        "ex_post_best_symbol": {
            "status": "ok" if best_symbol else "missing",
            "symbol": best_symbol,
            "return_pct": full.get("best_symbol_buy_hold_pct")
            or oos.get("best_symbol_buy_hold_pct"),
        },
    }
    missing = [name for name, item in benchmarks.items() if item.get("status") == "missing"]
    return {
        "complete": not missing,
        "missing": missing,
        "benchmarks": benchmarks,
        "alpha_summary": {
            "alpha_vs_benchmark": full.get("alpha_vs_benchmark_buy_hold_annualized_pct")
            or full.get("alpha_vs_market_buy_hold_annualized_pct"),
            "alpha_vs_equal_weight": full.get("alpha_vs_equal_weight_buy_hold_annualized_pct")
            or full.get("alpha_vs_equal_weight_annualized_pct"),
            "beat_ex_post_best_symbol": None,
        },
    }


def _target_mapping_summary(mapping: dict[str, Any] | None) -> dict[str, Any]:
    if mapping is None:
        return {
            "target_weight_mapping_status": "missing",
            "blockers": ["target-weight mapping artifact is missing"],
            "warnings": [],
        }
    parity = _dict_value(mapping.get("parity_check"))
    summary = _dict_value(mapping.get("summary"))
    blockers = _string_list(parity.get("blockers"))
    warnings = _string_list(parity.get("warnings"))
    status = "pass" if parity.get("status") == "pass" and not blockers else "warning"
    return {
        "target_weight_mapping_status": status,
        "blockers": blockers,
        "warnings": warnings,
        "summary": summary,
    }


def _llm_pass_status(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "missing"
    pass_status = _dict_value(payload.get("pass_status"))
    if pass_status.get("llm_contribution_pass") is True:
        return "pass"
    contribution = _dict_value(payload.get("llm_contribution"))
    if contribution.get("llm_contribution_ok") is True:
        return "pass"
    marginal_lift = _dict_value(payload.get("marginal_lift"))
    if marginal_lift.get("llm_contribution_pass") is True:
        return "pass"
    return "fail"


def _parameter_ranges(spec: StrategySpec) -> dict[str, list[Any]]:
    design = spec.research_design.model_dump(mode="json") if spec.research_design else {}
    value = design.get("parameter_space") or design.get("parameter_ranges")
    if isinstance(value, dict):
        return {
            str(key): list(raw) if isinstance(raw, list) else [raw] for key, raw in value.items()
        }
    return {}


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return raw if isinstance(raw, dict) else None


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _nested_get(value: dict[str, Any], *keys: str) -> object | None:
    cursor: object = value
    for key in keys:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def _first_number(*dicts: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for data in dicts:
        for key in keys:
            value = data.get(key)
            if isinstance(value, int | float):
                return float(value)
    return None


def _any_key(dicts: tuple[dict[str, Any], ...], keys: tuple[str, ...]) -> bool:
    return any(any(data.get(key) is not None for key in keys) for data in dicts)
