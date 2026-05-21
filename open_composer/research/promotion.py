from __future__ import annotations

import copy
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Literal

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import BacktestArtifacts, backtest_frame
from open_composer.expressions import ExpressionSafetyError, assert_expression_safe
from open_composer.feature_packets import inspect_feature_packet
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.alt_data_quality import build_alternative_data_quality_report
from open_composer.research.blind_test import load_blind_test_report
from open_composer.research.contracts import write_research_contract
from open_composer.research.factor_lab import run_factor_lab
from open_composer.research.kernel import ResearchArtifactWriter, ResearchRunIndexRecord
from open_composer.research.metadata import (
    frame_data_profile,
    research_run_manifest,
    runtime_payload,
    search_space,
)
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

DATA_TIERS_NOT_PAPER_READY = {
    "sample_smoke",
    "fixture_replay",
    "cached_live",
    "research_cross_check",
}

PromotionStatus = Literal["ok", "warning", "blocked"]
FivePassStatus = Literal["pass", "fail", "skipped", "not_applicable"]


@dataclass(frozen=True)
class PromotionCheck:
    name: str
    status: PromotionStatus
    message: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class FivePassChecks:
    workflow_pass: FivePassStatus
    research_pass: FivePassStatus
    llm_contribution_pass: FivePassStatus
    paper_ready_pass: FivePassStatus
    expression_safety_pass: FivePassStatus
    workflow_reason: str = ""
    research_reason: str = ""
    llm_contribution_reason: str = ""
    paper_ready_reason: str = ""
    expression_safety_reason: str = ""


@dataclass(frozen=True)
class PromotionReport:
    strategy_name: str
    source_spec_path: str
    status: PromotionStatus
    ready: bool
    checks: list[PromotionCheck]
    report_path: str
    json_path: str
    five_pass_checks: FivePassChecks | None = None


def build_promotion_report(
    spec_path: Path,
    root: Path | None = None,
    out_of_sample_ratio: float = 0.3,
    walk_forward_folds: int = 3,
    cost_slippage_bps: list[int] | None = None,
) -> PromotionReport:
    started_at = perf_counter()
    base = root or project_root()
    writer = ResearchArtifactWriter(base)
    spec = load_strategy_spec(spec_path)
    if spec.portfolio.mode == "adaptive_intraday_internal_router":
        return _build_adaptive_router_promotion_report(
            spec_path=spec_path,
            root=base,
            writer=writer,
            spec=spec,
            started_at=started_at,
            out_of_sample_ratio=out_of_sample_ratio,
            walk_forward_folds=walk_forward_folds,
        )
    if spec.portfolio.mode == "hybrid_adaptive_router":
        return _build_hybrid_router_promotion_report(
            spec_path=spec_path,
            root=base,
            writer=writer,
            spec=spec,
            started_at=started_at,
            out_of_sample_ratio=out_of_sample_ratio,
            walk_forward_folds=walk_forward_folds,
        )
    if spec.portfolio.mode == "beta_exposure_router":
        return _build_beta_router_promotion_report(
            spec_path=spec_path,
            root=base,
            writer=writer,
            spec=spec,
            started_at=started_at,
            out_of_sample_ratio=out_of_sample_ratio,
            walk_forward_folds=walk_forward_folds,
        )
    frame = load_ohlcv_for_spec(spec, base)
    if len(frame) < 4:
        msg = "promotion gate requires at least 4 bars of data"
        raise ValueError(msg)

    cost_slippage_bps = cost_slippage_bps or [0, 5, 10]
    checks: list[PromotionCheck] = []
    contract_path = write_research_contract(spec_path, base)
    data_profile = frame_data_profile(
        frame,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        provider=spec.data.source,
        feed=spec.data.feed,
        source_mode=frame.attrs.get("data_source_mode") or spec.data.source,
        path=frame.attrs.get("data_source_path") or spec.data.path,
    )

    full = backtest_frame(
        spec,
        frame,
        root=base,
        run_id_value=f"promotion-{spec.name}-full",
    )
    checks.append(
        PromotionCheck(
            name="in_sample",
            status=_status_from_sanity(
                full.run.data_sanity.status if full.run.data_sanity else "warning"
            ),
            message=(
                "Full-window backtest captured in-sample research evidence; "
                "review data sanity before promotion."
            ),
            details=_run_details(full),
        )
    )

    oos_check, oos_artifacts = _out_of_sample_check(
        spec=spec,
        frame=frame,
        root=base,
        out_of_sample_ratio=out_of_sample_ratio,
    )
    checks.append(oos_check)

    wf_check, walk_forward_runs = _walk_forward_check(
        spec=spec,
        frame=frame,
        root=base,
        folds=walk_forward_folds,
    )
    checks.append(wf_check)

    cost_check, cost_runs = _cost_sensitivity_check(
        spec=spec,
        frame=frame,
        root=base,
        slippage_bps=cost_slippage_bps,
    )
    checks.append(cost_check)

    comparison_check, comparison_rows = _data_comparison_check(spec, base)
    checks.append(comparison_check)

    strict_data_check = _strict_data_check(spec, full)
    checks.append(strict_data_check)

    feature_packet_check = _feature_packet_check(spec, base)
    checks.append(feature_packet_check)

    factor_lab_result = run_factor_lab(spec_path, base)
    factor_lab_check = _factor_lab_check(factor_lab_result)
    checks.append(factor_lab_check)

    execution_reality_check = _execution_reality_check(full)
    checks.append(execution_reality_check)

    alt_data_result = build_alternative_data_quality_report(spec_path, base)
    alt_data_check = _alternative_data_check(alt_data_result)
    checks.append(alt_data_check)

    benchmark_check, benchmark_family = _benchmark_family_check(spec, full)
    checks.append(benchmark_check)

    checks.append(_harness_artifacts_promotion_check(spec, base))
    checks.append(_research_design_check(spec))

    ready = all(check.status == "ok" for check in checks)
    status: PromotionStatus
    if any(check.status == "blocked" for check in checks):
        status = "blocked"
    elif any(check.status == "warning" for check in checks):
        status = "warning"
    else:
        status = "ok"
    five_pass_checks = _five_pass_checks(spec, ready, checks, base)
    report_path = base / "reports" / "research" / f"{spec.name}-promotion.md"
    json_path = base / "reports" / "research" / f"{spec.name}-promotion.json"
    manifest = research_run_manifest(
        root=base,
        strategy=spec,
        source_path=spec_path,
        trial_count=1 + int(oos_artifacts is not None) + len(walk_forward_runs) + len(cost_runs),
        search_space_payload=search_space(
            family="promotion_gate",
            candidate_count=1,
            parameter_ranges={"cost_slippage_bps": cost_slippage_bps},
            filters=[
                f"out_of_sample_ratio={out_of_sample_ratio}",
                f"walk_forward_folds={walk_forward_folds}",
            ],
        ),
        data_profile=data_profile,
        feature_packet_paths=_feature_packet_paths(spec),
        runtime=runtime_payload(started_at, {}),
    )
    manifest["research_contract_path"] = str(contract_path.relative_to(base))
    manifest["factor_lab_path"] = str(factor_lab_result.json_path.relative_to(base))
    manifest["alt_data_quality_path"] = str(alt_data_result.json_path.relative_to(base))
    gate_summary = _gate_summary(spec, ready, checks, benchmark_family)
    index_record = ResearchRunIndexRecord(
        run_id=f"promotion-{spec.name}-{strategy_content_hash(spec)[:12]}",
        strategy_name=spec.name,
        source_spec_path=_relpath(spec_path, base),
        spec_hash=strategy_content_hash(spec),
        status=status,
        kind="promotion",
        data_profile=data_profile,
        candidate_count=1,
        trial_count=int(manifest.get("trial_count", 1) or 1),
        runtime_seconds=(manifest.get("runtime") or {}).get("total")
        if isinstance(manifest.get("runtime"), dict)
        else None,
        gate_status=status,
        blocked_items=[str(item) for item in gate_summary.get("blocked_checks", [])],
        warning_items=[str(item) for item in gate_summary.get("warning_checks", [])],
        report_path=_relpath(report_path, base),
        json_path=_relpath(json_path, base),
        contract_path=_relpath(contract_path, base),
        source_artifacts={
            "factor_lab": _relpath(factor_lab_result.json_path, base),
            "alternative_data_quality": _relpath(alt_data_result.json_path, base),
            "full_window": full.run.report_path,
        },
    )
    _write_promotion_json(
        json_path,
        spec_path,
        spec,
        status,
        ready,
        checks,
        full,
        oos_artifacts,
        walk_forward_runs,
        cost_runs,
        comparison_rows,
        benchmark_family,
        data_profile,
        manifest,
        five_pass_checks,
        gate_summary,
        index_record,
    )
    writer.append_index(index_record)
    _write_promotion_report(
        report_path,
        spec_path,
        spec,
        status,
        ready,
        checks,
        full,
        oos_artifacts,
        walk_forward_runs,
        cost_runs,
        comparison_rows,
        benchmark_family,
        json_path,
        data_profile,
        manifest,
        five_pass_checks,
    )
    return PromotionReport(
        strategy_name=spec.name,
        source_spec_path=str(spec_path),
        status=status,
        ready=ready,
        checks=checks,
        report_path=str(report_path),
        json_path=str(json_path),
        five_pass_checks=five_pass_checks,
    )


def _build_adaptive_router_promotion_report(
    *,
    spec_path: Path,
    root: Path,
    writer: ResearchArtifactWriter,
    spec: StrategySpec,
    started_at: float,
    out_of_sample_ratio: float,
    walk_forward_folds: int,
) -> PromotionReport:
    research_path = root / "reports" / "research" / f"{spec.name}-adaptive-intraday-router.json"
    llm_path = root / "reports" / "research" / f"{spec.name}-llm-adaptive-router.json"
    report_path = root / "reports" / "research" / f"{spec.name}-promotion.md"
    json_path = root / "reports" / "research" / f"{spec.name}-promotion.json"
    contract_path = write_research_contract(spec_path, root)
    research_payload = _load_optional_json(research_path)
    llm_payload = _load_optional_json(llm_path)
    checks: list[PromotionCheck] = []

    if research_payload is None:
        checks.append(
            PromotionCheck(
                name="adaptive_router_research",
                status="blocked",
                message=(
                    "Adaptive router promotion requires a prior adaptive router research report."
                ),
                details={
                    "expected_path": _relpath(research_path, root),
                    "suggested_command": (
                        f"uv run oc strategy adaptive-intraday-router {spec_path} "
                        "--symbols <comma-separated NASDAQ universe>"
                    ),
                },
            )
        )
        data_profile: dict[str, object] = {"source_mode": "missing_research_report"}
        research_pass_status: dict[str, object] = {}
        acceptance_gate: dict[str, object] = {}
        candidates: list[dict[str, object]] = []
        selected_candidate: dict[str, object] | None = None
    else:
        data_profile = _dict_value(research_payload.get("data_profile"))
        research_pass_status = _dict_value(research_payload.get("pass_status"))
        acceptance_gate = _dict_value(research_payload.get("acceptance_gate"))
        candidates = _dict_list(research_payload.get("candidates"))
        selected_candidate = _selected_adaptive_candidate(spec, candidates, llm_payload)
        checks.append(
            _adaptive_research_check(research_path, acceptance_gate, research_pass_status)
        )
        checks.append(_adaptive_oos_check(selected_candidate, acceptance_gate))
        checks.append(_adaptive_walk_forward_check(research_payload, acceptance_gate))
        checks.append(_adaptive_data_check(data_profile))
        checks.append(_adaptive_benchmark_check(selected_candidate, candidates))

    feature_packet_check = _feature_packet_check(spec, root)
    checks.append(feature_packet_check)
    checks.append(_adaptive_factor_lab_check(selected_candidate))
    checks.append(_adaptive_alternative_data_check(spec, data_profile, feature_packet_check))
    checks.append(_adaptive_llm_check(spec, llm_path, llm_payload))
    checks.append(_adaptive_execution_check(spec))
    checks.append(_harness_artifacts_promotion_check(spec, root))
    checks.append(_research_design_check(spec))

    ready = False
    status: PromotionStatus = "blocked"
    benchmark_family = _adaptive_benchmark_family(selected_candidate)
    five_pass_checks = _adaptive_five_pass_checks(
        spec=spec,
        checks=checks,
        acceptance_gate=acceptance_gate,
        research_pass_status=research_pass_status,
        llm_payload=llm_payload,
    )
    gate_summary = _adaptive_gate_summary(checks, five_pass_checks, benchmark_family)
    research_cost = _dict_value((research_payload or {}).get("research_cost"))
    trial_count = int(research_cost.get("estimated_total_backtest_passes", 1) or 1)
    manifest = research_run_manifest(
        root=root,
        strategy=spec,
        source_path=spec_path,
        trial_count=trial_count,
        search_space_payload=search_space(
            family="adaptive_intraday_router_promotion",
            candidate_count=len(candidates) or 1,
            parameter_ranges=_adaptive_parameter_ranges(spec),
            filters=[
                f"out_of_sample_ratio={out_of_sample_ratio}",
                f"walk_forward_folds={walk_forward_folds}",
                "uses_existing_adaptive_router_research_report",
            ],
        ),
        data_profile=data_profile,
        feature_packet_paths=_feature_packet_paths(spec),
        runtime=runtime_payload(started_at, {}),
    )
    manifest["research_contract_path"] = _relpath(contract_path, root)
    manifest["adaptive_router_research_path"] = (
        _relpath(research_path, root) if research_payload else None
    )
    manifest["llm_adaptive_router_path"] = _relpath(llm_path, root) if llm_payload else None
    index_record = ResearchRunIndexRecord(
        run_id=f"promotion-{spec.name}-{strategy_content_hash(spec)[:12]}",
        strategy_name=spec.name,
        source_spec_path=_relpath(spec_path, root),
        spec_hash=strategy_content_hash(spec),
        status=status,
        kind="promotion",
        data_profile=data_profile,
        candidate_count=len(candidates) or 1,
        trial_count=int(manifest.get("trial_count", 1) or 1),
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
            "adaptive_router_research": _relpath(research_path, root) if research_payload else None,
            "llm_adaptive_router": _relpath(llm_path, root) if llm_payload else None,
        },
    )
    _write_adaptive_router_promotion_json(
        path=json_path,
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
        selected_candidate=selected_candidate,
    )
    writer.append_index(index_record)
    _write_adaptive_router_promotion_markdown(
        path=report_path,
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
        selected_candidate=selected_candidate,
        llm_payload=llm_payload,
    )
    return PromotionReport(
        strategy_name=spec.name,
        source_spec_path=str(spec_path),
        status=status,
        ready=ready,
        checks=checks,
        report_path=str(report_path),
        json_path=str(json_path),
        five_pass_checks=five_pass_checks,
    )


def _build_hybrid_router_promotion_report(
    *,
    spec_path: Path,
    root: Path,
    writer: ResearchArtifactWriter,
    spec: StrategySpec,
    started_at: float,
    out_of_sample_ratio: float,
    walk_forward_folds: int,
) -> PromotionReport:
    research_path = root / "reports" / "research" / f"{spec.name}-hybrid-adaptive-router.json"
    report_path = root / "reports" / "research" / f"{spec.name}-promotion.md"
    json_path = root / "reports" / "research" / f"{spec.name}-promotion.json"
    contract_path = write_research_contract(spec_path, root)
    research_payload = _load_optional_json(research_path)
    checks: list[PromotionCheck] = []

    if research_payload is None:
        checks.append(
            PromotionCheck(
                name="hybrid_router_research",
                status="blocked",
                message="Hybrid router promotion requires a prior hybrid router research report.",
                details={
                    "expected_path": _relpath(research_path, root),
                    "suggested_command": (
                        f"uv run oc strategy hybrid-adaptive-router {spec_path} "
                        "--symbols <comma-separated NASDAQ universe>"
                    ),
                },
            )
        )
        data_profile: dict[str, object] = {"source_mode": "missing_research_report"}
        pass_status: dict[str, object] = {}
        acceptance_gate: dict[str, object] = {}
        candidates: list[dict[str, object]] = []
        selected_candidate: dict[str, object] | None = None
    else:
        data_profile = _dict_value(research_payload.get("data_profile"))
        pass_status = _dict_value(research_payload.get("pass_status"))
        acceptance_gate = _dict_value(research_payload.get("acceptance_gate"))
        candidates = _dict_list(research_payload.get("candidates"))
        selected_candidate = _selected_hybrid_candidate(spec, candidates)
        checks.append(_hybrid_research_check(research_path, acceptance_gate, pass_status))
        checks.append(_hybrid_oos_check(selected_candidate, acceptance_gate))
        checks.append(_adaptive_walk_forward_check(research_payload, acceptance_gate))
        checks.append(_adaptive_data_check(data_profile))
        checks.append(_hybrid_benchmark_check(selected_candidate, candidates))

    feature_packet_check = _feature_packet_check(spec, root)
    checks.append(feature_packet_check)
    checks.append(_hybrid_factor_lab_check(selected_candidate, spec, root))
    checks.append(_adaptive_alternative_data_check(spec, data_profile, feature_packet_check))
    checks.append(_hybrid_llm_check(spec, root))
    checks.append(_hybrid_execution_check(spec, root))
    checks.append(_harness_artifacts_promotion_check(spec, root))
    checks.append(_research_design_check(spec))

    ready = False
    status: PromotionStatus = "blocked"
    benchmark_family = _hybrid_benchmark_family(selected_candidate)
    five_pass_checks = _hybrid_five_pass_checks(
        spec=spec,
        root=root,
        checks=checks,
        acceptance_gate=acceptance_gate,
        pass_status=pass_status,
        ready=ready,
    )
    gate_summary = _adaptive_gate_summary(checks, five_pass_checks, benchmark_family)
    research_cost = _dict_value((research_payload or {}).get("research_cost"))
    trial_count = int(research_cost.get("estimated_total_backtest_passes", 1) or 1)
    manifest = research_run_manifest(
        root=root,
        strategy=spec,
        source_path=spec_path,
        trial_count=trial_count,
        search_space_payload=search_space(
            family="hybrid_adaptive_router_promotion",
            candidate_count=len(candidates) or 1,
            parameter_ranges=_adaptive_parameter_ranges(spec),
            filters=[
                f"out_of_sample_ratio={out_of_sample_ratio}",
                f"walk_forward_folds={walk_forward_folds}",
                "uses_existing_hybrid_router_research_report",
            ],
        ),
        data_profile=data_profile,
        feature_packet_paths=_feature_packet_paths(spec),
        runtime=runtime_payload(started_at, {}),
    )
    manifest["research_contract_path"] = _relpath(contract_path, root)
    manifest["hybrid_router_research_path"] = (
        _relpath(research_path, root) if research_payload else None
    )
    index_record = ResearchRunIndexRecord(
        run_id=f"promotion-{spec.name}-{strategy_content_hash(spec)[:12]}",
        strategy_name=spec.name,
        source_spec_path=_relpath(spec_path, root),
        spec_hash=strategy_content_hash(spec),
        status=status,
        kind="promotion",
        data_profile=data_profile,
        candidate_count=len(candidates) or 1,
        trial_count=int(manifest.get("trial_count", 1) or 1),
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
            "hybrid_router_research": _relpath(research_path, root) if research_payload else None,
        },
    )
    _write_hybrid_router_promotion_json(
        path=json_path,
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
        selected_candidate=selected_candidate,
    )
    writer.append_index(index_record)
    _write_hybrid_router_promotion_markdown(
        path=report_path,
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
        selected_candidate=selected_candidate,
    )
    return PromotionReport(
        strategy_name=spec.name,
        source_spec_path=str(spec_path),
        status=status,
        ready=ready,
        checks=checks,
        report_path=str(report_path),
        json_path=str(json_path),
        five_pass_checks=five_pass_checks,
    )


def _build_beta_router_promotion_report(
    *,
    spec_path: Path,
    root: Path,
    writer: ResearchArtifactWriter,
    spec: StrategySpec,
    started_at: float,
    out_of_sample_ratio: float,
    walk_forward_folds: int,
) -> PromotionReport:
    research_path = (
        root
        / "reports"
        / "research"
        / "nasdaq100_wide_momentum_router_daily-beta-exposure-router.json"
    )
    spec_research_path = root / "reports" / "research" / f"{spec.name}-beta-exposure-router.json"
    if spec_research_path.exists():
        research_path = spec_research_path
    report_path = root / "reports" / "research" / f"{spec.name}-promotion.md"
    json_path = root / "reports" / "research" / f"{spec.name}-promotion.json"
    contract_path = write_research_contract(spec_path, root)
    research_payload = _load_optional_json(research_path)
    checks: list[PromotionCheck] = []

    if research_payload is None:
        checks.append(
            PromotionCheck(
                name="beta_router_research",
                status="blocked",
                message="Beta router promotion requires a prior beta router research report.",
                details={"expected_path": _relpath(research_path, root)},
            )
        )
        data_profile: dict[str, object] = {"source_mode": "missing_research_report"}
        pass_status: dict[str, object] = {}
        acceptance_gate: dict[str, object] = {}
        candidates: list[dict[str, object]] = []
        selected_candidate: dict[str, object] | None = None
    else:
        data_profile = _dict_value(research_payload.get("data_profile"))
        pass_status = _dict_value(research_payload.get("pass_status"))
        acceptance_gate = _dict_value(research_payload.get("acceptance_gate"))
        candidates = _dict_list(research_payload.get("candidates"))
        selected_candidate = _selected_beta_candidate(spec, candidates)
        checks.append(_beta_research_check(research_path, acceptance_gate, pass_status))
        checks.append(_beta_oos_check(selected_candidate, acceptance_gate))
        checks.append(_adaptive_walk_forward_check(research_payload, acceptance_gate))
        checks.append(_adaptive_data_check(data_profile))
        checks.append(_beta_benchmark_check(selected_candidate, candidates))

    feature_packet_check = _feature_packet_check(spec, root)
    checks.append(feature_packet_check)
    checks.append(_beta_factor_lab_check(selected_candidate))
    checks.append(_adaptive_alternative_data_check(spec, data_profile, feature_packet_check))
    checks.append(_beta_llm_check(spec))
    checks.append(_beta_execution_check(spec, root))
    checks.append(_harness_artifacts_promotion_check(spec, root))
    checks.append(_research_design_check(spec))

    benchmark_family = _beta_benchmark_family(selected_candidate)
    ready = all(check.status == "ok" for check in checks)
    if any(check.status == "blocked" for check in checks):
        status: PromotionStatus = "blocked"
    elif any(check.status == "warning" for check in checks):
        status = "warning"
    else:
        status = "ok"
    five_pass_checks = _beta_five_pass_checks(
        spec=spec,
        checks=checks,
        acceptance_gate=acceptance_gate,
        pass_status=pass_status,
        ready=ready,
    )
    gate_summary = _gate_summary(spec, ready, checks, benchmark_family)
    research_cost = _dict_value((research_payload or {}).get("research_cost"))
    trial_count = int(research_cost.get("candidate_count", 1) or 1)
    manifest = research_run_manifest(
        root=root,
        strategy=spec,
        source_path=spec_path,
        trial_count=trial_count,
        search_space_payload=search_space(
            family="beta_exposure_router_promotion",
            candidate_count=len(candidates) or 1,
            parameter_ranges=_adaptive_parameter_ranges(spec),
            filters=[
                f"out_of_sample_ratio={out_of_sample_ratio}",
                f"walk_forward_folds={walk_forward_folds}",
                "uses_existing_beta_router_research_report",
            ],
        ),
        data_profile=data_profile,
        feature_packet_paths=_feature_packet_paths(spec),
        runtime=runtime_payload(started_at, {}),
    )
    manifest["research_contract_path"] = _relpath(contract_path, root)
    manifest["beta_router_research_path"] = (
        _relpath(research_path, root) if research_payload else None
    )
    index_record = ResearchRunIndexRecord(
        run_id=f"promotion-{spec.name}-{strategy_content_hash(spec)[:12]}",
        strategy_name=spec.name,
        source_spec_path=_relpath(spec_path, root),
        spec_hash=strategy_content_hash(spec),
        status=status,
        kind="promotion",
        data_profile=data_profile,
        candidate_count=len(candidates) or 1,
        trial_count=int(manifest.get("trial_count", 1) or 1),
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
            "beta_router_research": _relpath(research_path, root) if research_payload else None,
        },
    )
    _write_beta_router_promotion_json(
        path=json_path,
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
        selected_candidate=selected_candidate,
    )
    writer.append_index(index_record)
    _write_beta_router_promotion_markdown(
        path=report_path,
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
        selected_candidate=selected_candidate,
    )
    return PromotionReport(
        strategy_name=spec.name,
        source_spec_path=str(spec_path),
        status=status,
        ready=ready,
        checks=checks,
        report_path=str(report_path),
        json_path=str(json_path),
        five_pass_checks=five_pass_checks,
    )


def _load_optional_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return raw if isinstance(raw, dict) else None


def _dict_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _selected_adaptive_candidate(
    spec: StrategySpec,
    candidates: list[dict[str, object]],
    llm_payload: dict[str, object] | None,
) -> dict[str, object] | None:
    labels = [
        _nested_route_label(_dict_value(_dict_value(llm_payload or {}).get("selected"))),
        spec.portfolio.selected_route_label,
    ]
    for label in labels:
        if not label:
            continue
        for candidate in candidates:
            if _nested_route_label(candidate) == label:
                return candidate
    return candidates[0] if candidates else None


def _nested_route_label(candidate: dict[str, object]) -> str | None:
    route = candidate.get("route")
    if not isinstance(route, dict):
        return None
    label = route.get("label")
    return str(label) if label else None


def _selected_hybrid_candidate(
    spec: StrategySpec,
    candidates: list[dict[str, object]],
) -> dict[str, object] | None:
    label = spec.portfolio.selected_route_label
    if label:
        for candidate in candidates:
            if _hybrid_candidate_label(candidate) == label:
                return candidate
    return candidates[0] if candidates else None


def _hybrid_candidate_label(candidate: dict[str, object]) -> str | None:
    params = candidate.get("params")
    if not isinstance(params, dict):
        return None
    holding_mode = params.get("holding_mode")
    lookback = params.get("momentum_lookback_days")
    top_n = params.get("top_n")
    market_sma = params.get("market_sma_days")
    min_momentum = params.get("min_momentum_pct")
    weight = params.get("max_position_weight")
    if not holding_mode or lookback is None or top_n is None:
        return None
    gate = "nogate" if market_sma is None else f"qsm{market_sma:g}"
    return (
        f"{holding_mode}:lb{lookback:g}_top{top_n:g}_{gate}_"
        f"min{float(min_momentum or 0.0):g}_w{float(weight or 0.0):g}"
    )


def _selected_beta_candidate(
    spec: StrategySpec,
    candidates: list[dict[str, object]],
) -> dict[str, object] | None:
    label = spec.portfolio.selected_route_label
    if label:
        for candidate in candidates:
            params = _dict_value(candidate.get("params"))
            if params.get("label") == label:
                return candidate
    return candidates[0] if candidates else None


def _beta_research_check(
    research_path: Path,
    acceptance_gate: dict[str, object],
    pass_status: dict[str, object],
) -> PromotionCheck:
    research_pass = bool(pass_status.get("research_pass", False))
    return PromotionCheck(
        name="beta_router_research",
        status="ok" if research_pass else "blocked",
        message=(
            "Beta exposure router research report exists and passed QQQ Alpha gates."
            if research_pass
            else "Beta exposure router research report exists but did not pass research gates."
        ),
        details={
            "path": str(research_path),
            "acceptance_gate": acceptance_gate,
            "pass_status": pass_status,
        },
    )


def _beta_oos_check(
    selected_candidate: dict[str, object] | None,
    acceptance_gate: dict[str, object],
) -> PromotionCheck:
    if selected_candidate is None:
        return PromotionCheck(
            name="out_of_sample",
            status="blocked",
            message="No selected beta route candidate is available.",
        )
    oos = _dict_value(selected_candidate.get("out_of_sample"))
    sharpe = _float_or_none(oos.get("sharpe_ratio"))
    max_drawdown = _float_or_none(oos.get("max_drawdown_pct"))
    alpha = _float_or_none(oos.get("alpha_vs_market_buy_hold_annualized_pct"))
    annualized = _float_or_none(oos.get("annualized_return_pct"))
    blockers: list[str] = []
    if alpha is None or alpha <= 0:
        blockers.append("OOS annualized Alpha vs QQQ buy-hold is not positive")
    if annualized is None or annualized < 12:
        blockers.append("OOS annualized return below 12%")
    if sharpe is None or sharpe < 0.7 or sharpe > 2.5:
        blockers.append("OOS Sharpe outside 0.7 to 2.5")
    if max_drawdown is not None and max_drawdown <= -35.0:
        blockers.append("OOS max drawdown worse than -35%")
    return PromotionCheck(
        name="out_of_sample",
        status="blocked" if blockers else "ok",
        message=(
            "Selected beta route has acceptable OOS QQQ Alpha evidence."
            if not blockers
            else "Selected beta route OOS evidence is not strong enough: " + "; ".join(blockers)
        ),
        details={
            "route_label": _dict_value(selected_candidate.get("params")).get("label"),
            "out_of_sample": oos,
            "acceptance_gate": acceptance_gate,
            "blockers": blockers,
        },
    )


def _beta_benchmark_check(
    selected_candidate: dict[str, object] | None,
    candidates: list[dict[str, object]],
) -> PromotionCheck:
    family = _beta_benchmark_family(selected_candidate)
    blockers: list[str] = []
    if not family.get("complete"):
        blockers.append("benchmark family is incomplete")
    return PromotionCheck(
        name="benchmark_family",
        status="blocked" if blockers else "ok",
        message=(
            "Beta router benchmark family passed."
            if not blockers
            else "Beta router benchmark family blocks promotion: " + "; ".join(blockers)
        ),
        details={"candidate_count": len(candidates), "benchmark_family": family},
    )


def _beta_factor_lab_check(selected_candidate: dict[str, object] | None) -> PromotionCheck:
    params = _dict_value((selected_candidate or {}).get("params"))
    return PromotionCheck(
        name="factor_lab",
        status="ok",
        message="Beta router factor attribution is explicit in the route gates.",
        details={
            "route_label": params.get("label"),
            "factors": [
                "QQQ trend",
                "QQQ absolute momentum",
                "TQQQ self-trend",
                "TQQQ self-drawdown",
                "cash risk-off state",
            ],
            "note": "Further ablation is still recommended before paper_auto.",
        },
    )


def _beta_llm_check(spec: StrategySpec) -> PromotionCheck:
    if not spec.llm_review.enabled:
        return PromotionCheck(
            name="llm_contribution",
            status="ok",
            message="LLM review is disabled for this strategy.",
        )
    return PromotionCheck(
        name="llm_contribution",
        status="blocked",
        message=(
            "Beta router LLM/news features are advisory until PIT marginal-lift evidence exists."
        ),
    )


def _beta_execution_check(spec: StrategySpec, root: Path) -> PromotionCheck:
    mapping = _beta_target_weight_mapping_evidence(spec, root)
    mapping_blockers: list[str] = []
    mapping_status = "missing"
    if mapping is None:
        mapping_blockers.append("beta router needs Nautilus target-weight mapping")
    else:
        parity = _dict_value(mapping.get("parity_check") or mapping.get("validation"))
        mapping_status = str(parity.get("status") or "unknown")
        if mapping_status not in {"pass", "ok"}:
            mapping_blockers.append("beta target-weight mapping parity did not pass")
    blockers = [*mapping_blockers]
    warnings: list[str] = []
    if spec.execution.mode != "paper_auto":
        warnings.append(f"execution.mode={spec.execution.mode}")
    if spec.execution.broker != "alpaca_paper":
        warnings.append(f"execution.broker={spec.execution.broker}")
    if warnings:
        warnings.append("paper_auto activation still requires explicit user confirmation")
    status: PromotionStatus = "blocked" if blockers else "warning" if warnings else "ok"
    return PromotionCheck(
        name="execution_reality",
        status=status,
        message=(
            "Beta router target-weight mapping exists and paper execution mode is configured."
            if status == "ok"
            else "Beta router target-weight mapping exists, but paper automation is not activated."
            if not blockers
            else "Beta router execution parity is not ready for paper automation."
        ),
        details={
            "backend": spec.execution.backend,
            "mode": spec.execution.mode,
            "broker": spec.execution.broker,
            "target_weight_mapping_status": mapping_status,
            "target_weight_mapping_path": _relpath(
                _beta_target_weight_mapping_path(spec, root), root
            ),
            "target_weight_mapping": _target_mapping_summary(mapping),
            "blockers": blockers,
            "warnings": warnings,
        },
    )


def _hybrid_research_check(
    research_path: Path,
    acceptance_gate: dict[str, object],
    pass_status: dict[str, object],
) -> PromotionCheck:
    research_pass = bool(pass_status.get("research_pass", False))
    return PromotionCheck(
        name="hybrid_router_research",
        status="ok" if research_pass else "blocked",
        message=(
            "Hybrid router research report exists and passed TQQQ Alpha gates."
            if research_pass
            else "Hybrid router research report exists but did not pass research gates."
        ),
        details={
            "path": str(research_path),
            "acceptance_gate": acceptance_gate,
            "pass_status": pass_status,
        },
    )


def _hybrid_oos_check(
    selected_candidate: dict[str, object] | None,
    acceptance_gate: dict[str, object],
) -> PromotionCheck:
    if selected_candidate is None:
        return PromotionCheck(
            name="out_of_sample",
            status="blocked",
            message="No selected hybrid route candidate is available.",
        )
    oos = _dict_value(selected_candidate.get("out_of_sample"))
    sharpe = _float_or_none(oos.get("sharpe_ratio"))
    traded_days = _float_or_none(oos.get("traded_days")) or 0.0
    max_drawdown = _float_or_none(oos.get("max_drawdown_pct"))
    alpha = _float_or_none(oos.get("alpha_vs_benchmark_buy_hold_annualized_pct"))
    blockers: list[str] = []
    if alpha is None or alpha <= 0:
        blockers.append("OOS annualized Alpha vs TQQQ buy-hold is not positive")
    if sharpe is None or sharpe < 0.7:
        blockers.append("OOS Sharpe below 0.7")
    if traded_days < 40:
        blockers.append("OOS traded days below 40")
    if max_drawdown is not None and max_drawdown <= -30.0:
        blockers.append("OOS max drawdown worse than -30%")
    return PromotionCheck(
        name="out_of_sample",
        status="blocked" if blockers else "ok",
        message=(
            "Selected hybrid route has acceptable OOS TQQQ Alpha evidence."
            if not blockers
            else "Selected hybrid route OOS evidence is not strong enough: " + "; ".join(blockers)
        ),
        details={
            "route_label": _hybrid_candidate_label(selected_candidate),
            "out_of_sample": oos,
            "acceptance_gate": acceptance_gate,
            "blockers": blockers,
        },
    )


def _hybrid_benchmark_check(
    selected_candidate: dict[str, object] | None,
    candidates: list[dict[str, object]],
) -> PromotionCheck:
    family = _hybrid_benchmark_family(selected_candidate)
    quality_flags = [
        str(item) for item in (selected_candidate or {}).get("quality_flags", []) or []
    ]
    blockers: list[str] = []
    if not family.get("complete"):
        blockers.append("benchmark family is incomplete")
    if "does_not_beat_ex_post_best_symbol" in quality_flags:
        blockers.append("selected route does not beat ex-post best symbol")
    return PromotionCheck(
        name="benchmark_family",
        status="blocked" if blockers else "ok",
        message=(
            "Hybrid router benchmark family passed."
            if not blockers
            else "Hybrid router benchmark family blocks promotion: " + "; ".join(blockers)
        ),
        details={"candidate_count": len(candidates), "benchmark_family": family},
    )


def _hybrid_factor_lab_check(
    selected_candidate: dict[str, object] | None,
    spec: StrategySpec,
    root: Path,
) -> PromotionCheck:
    evidence = _hybrid_factor_attribution_evidence(spec, root)
    if evidence is not None:
        status = "ok" if evidence.get("status") == "ok" else "blocked"
        return PromotionCheck(
            name="factor_lab",
            status=status,
            message=(
                "Hybrid router route-level factor attribution evidence is present."
                if status == "ok"
                else "Hybrid router route-level factor attribution evidence exists but is blocked."
            ),
            details=evidence,
        )
    return PromotionCheck(
        name="factor_lab",
        status="blocked",
        message=(
            "Hybrid router needs route-level factor attribution before promotion; "
            "single-symbol factor lab is not representative."
        ),
        details={
            "route_label": _hybrid_candidate_label(selected_candidate or {}),
            "required_evidence": [
                "single-modality quant baseline",
                "market-gate marginal lift",
                "holding-mode attribution",
            ],
        },
    )


def _hybrid_llm_check(spec: StrategySpec, root: Path) -> PromotionCheck:
    if not spec.llm_review.enabled:
        return PromotionCheck(
            name="llm_contribution",
            status="ok",
            message="LLM review is disabled for this strategy.",
        )
    evidence = _hybrid_news_marginal_lift_evidence(spec, root)
    if evidence is not None:
        status = "ok" if bool(evidence.get("llm_contribution_pass")) else "warning"
        return PromotionCheck(
            name="llm_contribution",
            status=status,
            message=(
                "Hybrid router PIT news marginal-lift evidence is positive; independent "
                "LLM Alpha is not claimed."
                if status == "ok"
                else "Hybrid router PIT news marginal-lift evidence exists, but does not "
                "prove independent LLM/news Alpha."
            ),
            details=evidence,
        )
    return PromotionCheck(
        name="llm_contribution",
        status="blocked",
        message=(
            "Hybrid router LLM/news features are advisory until PIT packets show "
            "single-modality baseline, marginal lift, and missing-modality robustness."
        ),
    )


def _hybrid_execution_check(spec: StrategySpec, root: Path) -> PromotionCheck:
    mapping = _hybrid_target_weight_mapping_evidence(spec, root)
    mapping_blockers: list[str] = []
    mapping_status = "missing"
    if mapping is None:
        mapping_blockers.append("hybrid router needs Nautilus target-weight mapping")
    else:
        parity = _dict_value(mapping.get("parity_check") or mapping.get("validation"))
        mapping_status = str(parity.get("status") or "unknown")
        if mapping_status not in {"pass", "ok"}:
            mapping_blockers.append("hybrid target-weight mapping parity did not pass")
    blockers = [
        *mapping_blockers,
        "open-to-open holding needs overnight position lifecycle reconciliation",
        f"execution.mode={spec.execution.mode}",
        f"execution.broker={spec.execution.broker}",
    ]
    return PromotionCheck(
        name="execution_reality",
        status="blocked",
        message="Hybrid router execution parity is not ready for paper automation.",
        details={
            "backend": spec.execution.backend,
            "mode": spec.execution.mode,
            "broker": spec.execution.broker,
            "target_weight_mapping_status": mapping_status,
            "target_weight_mapping_path": _relpath(
                _hybrid_target_weight_mapping_path(spec, root),
                root,
            ),
            "target_weight_mapping": _target_mapping_summary(mapping),
            "blockers": blockers,
        },
    )


def _hybrid_benchmark_family(
    selected_candidate: dict[str, object] | None,
) -> dict[str, object]:
    full = _dict_value((selected_candidate or {}).get("full_window"))
    oos = _dict_value((selected_candidate or {}).get("out_of_sample"))
    quality_flags = [
        str(item) for item in (selected_candidate or {}).get("quality_flags", []) or []
    ]
    missing = []
    if not full or not oos:
        missing.append("selected_route_metrics")
    return {
        "complete": not missing,
        "missing": missing,
        "benchmarks": {
            "same_symbol_buy_hold": {
                "status": "not_applicable",
                "note": "hybrid router is multi-symbol and benchmarked to TQQQ buy-hold",
            },
            "equal_weight_universe": {
                "status": "ok" if full else "missing",
                "full_window_return_pct": full.get("equal_weight_buy_hold_return_pct"),
                "full_window_annualized_pct": full.get("equal_weight_buy_hold_annualized_pct"),
                "oos_return_pct": oos.get("equal_weight_buy_hold_return_pct"),
                "oos_alpha_annualized_pct": oos.get(
                    "alpha_vs_equal_weight_buy_hold_annualized_pct"
                ),
            },
            "market_proxy": {
                "status": "ok" if full.get("market_symbol") else "missing",
                "symbol": full.get("market_symbol"),
                "oos_buy_hold_return_pct": oos.get("market_buy_hold_return_pct"),
                "oos_alpha_annualized_pct": oos.get("alpha_vs_market_buy_hold_annualized_pct"),
            },
            "sector_theme_proxy": {
                "status": "ok" if full.get("benchmark_symbol") else "missing",
                "symbol": full.get("benchmark_symbol"),
                "oos_buy_hold_return_pct": oos.get("benchmark_buy_hold_return_pct"),
                "oos_alpha_annualized_pct": oos.get("alpha_vs_benchmark_buy_hold_annualized_pct"),
                "note": "TQQQ is used as the leveraged NASDAQ theme stress benchmark",
            },
            "cash_proxy": {
                "status": "ok",
                "return_pct": 0.0,
                "oos_alpha_pct": oos.get("total_return_pct"),
            },
            "ex_post_best_symbol": {
                "status": "ok" if full.get("best_symbol") else "missing",
                "full_window_symbol": full.get("best_symbol"),
                "full_window_return_pct": full.get("best_symbol_buy_hold_pct"),
                "oos_symbol": oos.get("best_symbol"),
                "oos_return_pct": oos.get("best_symbol_buy_hold_pct"),
                "beat_ex_post_best_symbol": (
                    "does_not_beat_ex_post_best_symbol" not in quality_flags
                ),
            },
        },
        "quality_flags": quality_flags,
    }


def _beta_benchmark_family(
    selected_candidate: dict[str, object] | None,
) -> dict[str, object]:
    full = _dict_value((selected_candidate or {}).get("full_window"))
    oos = _dict_value((selected_candidate or {}).get("out_of_sample"))
    missing = []
    if not full or not oos:
        missing.append("selected_route_metrics")
    return {
        "complete": not missing,
        "missing": missing,
        "benchmarks": {
            "same_symbol_buy_hold": {
                "status": "ok" if full else "missing",
                "symbol": full.get("market_symbol"),
                "full_window_return_pct": full.get("market_buy_hold_return_pct"),
                "full_window_annualized_pct": full.get("market_buy_hold_annualized_pct"),
                "oos_return_pct": oos.get("market_buy_hold_return_pct"),
                "oos_alpha_annualized_pct": oos.get("alpha_vs_market_buy_hold_annualized_pct"),
            },
            "equal_weight_universe": {
                "status": "not_applicable",
                "note": (
                    "beta router intentionally routes among QQQ/TQQQ/cash, not a stock universe"
                ),
            },
            "market_proxy": {
                "status": "ok" if full.get("market_symbol") else "missing",
                "symbol": full.get("market_symbol"),
                "oos_buy_hold_return_pct": oos.get("market_buy_hold_return_pct"),
                "oos_alpha_annualized_pct": oos.get("alpha_vs_market_buy_hold_annualized_pct"),
            },
            "sector_theme_proxy": {
                "status": "ok" if full.get("leverage_symbol") else "missing",
                "symbol": full.get("leverage_symbol"),
                "oos_buy_hold_return_pct": oos.get("leverage_buy_hold_return_pct"),
                "oos_alpha_annualized_pct": oos.get("alpha_vs_leverage_buy_hold_annualized_pct"),
                "note": "TQQQ is the leveraged NASDAQ theme stress benchmark",
            },
            "cash_proxy": {
                "status": "ok",
                "return_pct": 0.0,
                "oos_alpha_pct": oos.get("total_return_pct"),
            },
            "ex_post_best_symbol": {
                "status": "warning",
                "note": "limited ETF route universe; full ex-post stock universe is not applicable",
            },
        },
    }


def _hybrid_news_marginal_lift_path(spec: StrategySpec, root: Path) -> Path:
    return root / "reports" / "research" / f"{spec.name}-news-marginal-lift.json"


def _hybrid_factor_attribution_path(spec: StrategySpec, root: Path) -> Path:
    return root / "reports" / "research" / f"{spec.name}-hybrid-factor-attribution.json"


def _hybrid_factor_attribution_evidence(
    spec: StrategySpec,
    root: Path,
) -> dict[str, object] | None:
    path = _hybrid_factor_attribution_path(spec, root)
    payload = _load_optional_json(path)
    if payload is None:
        return None
    attribution = _dict_value(payload.get("attribution"))
    return {
        "path": _relpath(path, root),
        "status": payload.get("status"),
        "blockers": payload.get("blockers", []),
        "route_label": payload.get("route_label"),
        "ablation_count": len(attribution),
        "attribution": attribution,
    }


def _hybrid_news_marginal_lift_evidence(
    spec: StrategySpec,
    root: Path,
) -> dict[str, object] | None:
    path = _hybrid_news_marginal_lift_path(spec, root)
    payload = _load_optional_json(path)
    if payload is None:
        return None
    marginal_lift = _dict_value(payload.get("marginal_lift"))
    feature_packets = _dict_value(payload.get("feature_packets"))
    return {
        "path": _relpath(path, root),
        "llm_contribution_pass": bool(marginal_lift.get("llm_contribution_pass", False)),
        "news_contribution_pass": bool(marginal_lift.get("news_contribution_pass", False)),
        "independent_llm_alpha_pass": bool(marginal_lift.get("independent_llm_alpha_pass", False)),
        "llm_api_called": bool(marginal_lift.get("llm_api_called", False)),
        "feature_modality": marginal_lift.get("feature_modality"),
        "alpha_vs_tqqq_annualized_lift_pct": marginal_lift.get("alpha_vs_tqqq_annualized_pct"),
        "interpretation": marginal_lift.get("interpretation"),
        "feature_packet_path": feature_packets.get("path"),
    }


def _hybrid_target_weight_mapping_path(spec: StrategySpec, root: Path) -> Path:
    return root / "reports" / "execution" / f"{spec.name}-target-weights.json"


def _beta_target_weight_mapping_path(spec: StrategySpec, root: Path) -> Path:
    standard = root / "reports" / "execution" / f"{spec.name}-target-weights.json"
    if standard.exists():
        return standard
    return root / "reports" / "execution" / f"{spec.name}-beta-target-weights.json"


def _hybrid_target_weight_mapping_evidence(
    spec: StrategySpec,
    root: Path,
) -> dict[str, object] | None:
    return _load_optional_json(_hybrid_target_weight_mapping_path(spec, root))


def _beta_target_weight_mapping_evidence(
    spec: StrategySpec,
    root: Path,
) -> dict[str, object] | None:
    return _load_optional_json(_beta_target_weight_mapping_path(spec, root))


def _target_mapping_summary(mapping: dict[str, object] | None) -> dict[str, object]:
    if mapping is None:
        return {}
    summary = _dict_value(mapping.get("summary"))
    parity = _dict_value(mapping.get("parity_check"))
    if not parity:
        parity = _dict_value(mapping.get("validation"))
    return {
        "summary": summary,
        "parity_status": parity.get("status"),
        "parity_blockers": parity.get("blockers"),
        "parity_warnings": parity.get("warnings"),
    }


def _hybrid_five_pass_checks(
    *,
    spec: StrategySpec,
    root: Path,
    checks: list[PromotionCheck],
    acceptance_gate: dict[str, object],
    pass_status: dict[str, object],
    ready: bool,
) -> FivePassChecks:
    blocked = sorted(check.name for check in checks if check.status == "blocked")
    workflow_pass: FivePassStatus = (
        "pass" if bool(pass_status.get("workflow_pass", False)) else "fail"
    )
    research_pass: FivePassStatus = (
        "pass" if bool(pass_status.get("research_pass", False)) and not blocked else "fail"
    )
    llm_contribution_pass: FivePassStatus
    if spec.llm_review.enabled:
        llm_evidence = _hybrid_news_marginal_lift_evidence(spec, root)
        if llm_evidence is None:
            llm_contribution_pass = "fail"
            llm_reason = (
                "hybrid LLM/news contribution is advisory without PIT marginal-lift evidence"
            )
        elif bool(llm_evidence.get("llm_contribution_pass")):
            llm_contribution_pass = "pass"
            llm_reason = (
                "hybrid PIT news marginal-lift evidence passed; independent LLM Alpha "
                "is not claimed"
            )
        else:
            llm_contribution_pass = "fail"
            llm_reason = "PIT marginal-lift evidence exists but does not prove LLM/news Alpha"
    else:
        llm_contribution_pass = "not_applicable"
        llm_reason = "LLM review is disabled"
    expression_safety_pass, expression_reason = _expression_safety_pass(spec)
    return FivePassChecks(
        workflow_pass=workflow_pass,
        research_pass=research_pass,
        llm_contribution_pass=llm_contribution_pass,
        paper_ready_pass="pass" if ready else "fail",
        expression_safety_pass=expression_safety_pass,
        workflow_reason=(
            "hybrid router research workflow ran"
            if workflow_pass == "pass"
            else "hybrid router research workflow did not pass"
        ),
        research_reason=(
            "hybrid router research gates passed"
            if research_pass == "pass"
            else "blocked checks: " + ", ".join(blocked)
        ),
        llm_contribution_reason=llm_reason,
        paper_ready_reason=(
            "hybrid router remains blocked before paper automation; "
            f"acceptance_gate={acceptance_gate}"
        ),
        expression_safety_reason=expression_reason,
    )


def _beta_five_pass_checks(
    *,
    spec: StrategySpec,
    checks: list[PromotionCheck],
    acceptance_gate: dict[str, object],
    pass_status: dict[str, object],
    ready: bool,
) -> FivePassChecks:
    blocked = sorted(check.name for check in checks if check.status == "blocked")
    workflow_pass: FivePassStatus = (
        "pass" if bool(pass_status.get("workflow_pass", False)) else "fail"
    )
    research_pass: FivePassStatus = (
        "pass" if bool(pass_status.get("research_pass", False)) and not blocked else "fail"
    )
    llm_contribution_pass: FivePassStatus = "fail" if spec.llm_review.enabled else "not_applicable"
    llm_reason = (
        "beta LLM/news contribution is advisory without PIT marginal-lift evidence"
        if spec.llm_review.enabled
        else "LLM review is disabled"
    )
    expression_safety_pass, expression_reason = _expression_safety_pass(spec)
    return FivePassChecks(
        workflow_pass=workflow_pass,
        research_pass=research_pass,
        llm_contribution_pass=llm_contribution_pass,
        paper_ready_pass="pass" if ready else "fail",
        expression_safety_pass=expression_safety_pass,
        workflow_reason=(
            "beta router research workflow ran"
            if workflow_pass == "pass"
            else "beta router research workflow did not pass"
        ),
        research_reason=(
            "beta router research gates passed"
            if research_pass == "pass"
            else "blocked checks: " + ", ".join(blocked)
        ),
        llm_contribution_reason=llm_reason,
        paper_ready_reason="beta router passed promotion checks"
        if ready
        else (
            "beta router remains blocked before paper automation; "
            f"acceptance_gate={acceptance_gate}"
        ),
        expression_safety_reason=expression_reason,
    )


def _adaptive_research_check(
    research_path: Path,
    acceptance_gate: dict[str, object],
    pass_status: dict[str, object],
) -> PromotionCheck:
    research_pass = bool(pass_status.get("research_pass", False))
    return PromotionCheck(
        name="adaptive_router_research",
        status="ok" if research_pass else "blocked",
        message=(
            "Adaptive router research report exists and passed research gates."
            if research_pass
            else "Adaptive router research report exists but did not pass research gates."
        ),
        details={
            "path": str(research_path),
            "acceptance_gate": acceptance_gate,
            "pass_status": pass_status,
        },
    )


def _adaptive_oos_check(
    selected_candidate: dict[str, object] | None,
    acceptance_gate: dict[str, object],
) -> PromotionCheck:
    if selected_candidate is None:
        return PromotionCheck(
            name="out_of_sample",
            status="blocked",
            message="No selected adaptive route candidate is available.",
        )
    oos = _dict_value(selected_candidate.get("out_of_sample"))
    sharpe = _float_or_none(oos.get("sharpe_ratio"))
    traded_days = _float_or_none(oos.get("traded_days")) or 0.0
    max_drawdown = _float_or_none(oos.get("max_drawdown_pct"))
    blockers: list[str] = []
    if sharpe is None or sharpe < 1.0:
        blockers.append("OOS Sharpe below 1.0")
    if traded_days < 50:
        blockers.append("OOS traded days below 50")
    if max_drawdown is not None and max_drawdown < -12.0:
        blockers.append("OOS max drawdown worse than -12%")
    return PromotionCheck(
        name="out_of_sample",
        status="blocked" if blockers else "ok",
        message=(
            "Selected adaptive route has acceptable OOS stability for research review."
            if not blockers
            else "Selected adaptive route OOS evidence is not strong enough: " + "; ".join(blockers)
        ),
        details={
            "route_label": _nested_route_label(selected_candidate),
            "out_of_sample": oos,
            "acceptance_gate": acceptance_gate,
            "blockers": blockers,
        },
    )


def _adaptive_walk_forward_check(
    research_payload: dict[str, object],
    acceptance_gate: dict[str, object],
) -> PromotionCheck:
    fold_count = int(_float_or_none(acceptance_gate.get("walk_forward_fold_count")) or 0)
    positive = int(_float_or_none(acceptance_gate.get("walk_forward_positive_alpha_folds")) or 0)
    walk_forward = research_payload.get("walk_forward")
    rows = walk_forward if isinstance(walk_forward, list) else []
    required_positive = max(1, math.ceil(fold_count * 0.6)) if fold_count else 0
    passed = fold_count > 0 and positive >= required_positive
    return PromotionCheck(
        name="walk_forward",
        status="ok" if passed else "blocked",
        message=(
            "Walk-forward folds meet the configured positive-alpha threshold."
            if passed
            else "Walk-forward evidence is mixed or incomplete."
        ),
        details={
            "fold_count": fold_count,
            "positive_alpha_folds": positive,
            "required_positive_alpha_folds": required_positive,
            "reported_folds": len(rows),
            "acceptance_gate": acceptance_gate,
        },
    )


def _adaptive_data_check(data_profile: dict[str, object]) -> PromotionCheck:
    warnings = [str(item) for item in data_profile.get("warnings", []) or []]
    source_mode = str(data_profile.get("source_mode") or "unknown")
    blockers: list[str] = []
    warning_notes: list[str] = []
    if source_mode in {"cache", "sample", "fixture", "fallback", "unknown"}:
        blockers.append(f"source_mode={source_mode} is not paper-ready evidence")
    if "cache_data_used" in warnings:
        blockers.append("cache data was used")
    if "iex_feed_not_full_market_sip" in warnings:
        warning_notes.append("Alpaca IEX is not consolidated SIP data")
    status: PromotionStatus = "blocked" if blockers else "ok"
    return PromotionCheck(
        name="strict_data",
        status=status,
        message=(
            "Adaptive router data source satisfies strict promotion requirements."
            if not blockers and not warning_notes
            else "Adaptive router promotion has market data caveats: "
            + "; ".join([*blockers, *warning_notes])
        ),
        details={"data_profile": data_profile, "blockers": blockers, "warnings": warning_notes},
    )


def _adaptive_benchmark_check(
    selected_candidate: dict[str, object] | None,
    candidates: list[dict[str, object]],
) -> PromotionCheck:
    family = _adaptive_benchmark_family(selected_candidate)
    quality_flags = [
        str(item) for item in (selected_candidate or {}).get("quality_flags", []) or []
    ]
    blockers: list[str] = []
    if not family.get("complete"):
        blockers.append("benchmark family is incomplete")
    if "does_not_beat_ex_post_best_symbol" in quality_flags:
        blockers.append("selected route does not beat ex-post best symbol")
    return PromotionCheck(
        name="benchmark_family",
        status="blocked" if blockers else "ok",
        message=(
            "Adaptive router benchmark family passed."
            if not blockers
            else "Adaptive router benchmark family blocks promotion: " + "; ".join(blockers)
        ),
        details={"candidate_count": len(candidates), "benchmark_family": family},
    )


def _adaptive_factor_lab_check(
    selected_candidate: dict[str, object] | None,
) -> PromotionCheck:
    return PromotionCheck(
        name="factor_lab",
        status="blocked",
        message=(
            "Adaptive router needs route-level factor attribution before promotion; "
            "single-symbol factor lab is not representative."
        ),
        details={
            "route_label": _nested_route_label(selected_candidate or {}),
            "required_evidence": [
                "single-route baseline",
                "router marginal lift",
                "route-family attribution",
            ],
        },
    )


def _adaptive_alternative_data_check(
    spec: StrategySpec,
    data_profile: dict[str, object],
    feature_packet_check: PromotionCheck,
) -> PromotionCheck:
    trial_capabilities = [
        item
        for item in spec.required_capabilities
        if item.startswith("news.") or item.startswith("event.")
    ]
    blocked = bool(trial_capabilities) and feature_packet_check.status != "ok"
    return PromotionCheck(
        name="alternative_data",
        status="blocked" if blocked else "ok",
        message=(
            "Alternative-data dependencies have promotion evidence."
            if not blocked
            else "News/event dependencies are trial or advisory until PIT marginal-lift "
            "and missing-modality evidence exists."
        ),
        details={
            "required_capabilities": spec.required_capabilities,
            "trial_or_context_capabilities": trial_capabilities,
            "data_warnings": data_profile.get("warnings", []),
            "feature_packet_status": feature_packet_check.status,
        },
    )


def _adaptive_llm_check(
    spec: StrategySpec,
    llm_path: Path,
    llm_payload: dict[str, object] | None,
) -> PromotionCheck:
    if not spec.llm_review.enabled:
        return PromotionCheck(
            name="llm_contribution",
            status="ok",
            message="LLM review is disabled for this strategy.",
        )
    if llm_payload is None:
        return PromotionCheck(
            name="llm_contribution",
            status="blocked",
            message="LLM adaptive router report is missing.",
            details={"expected_path": str(llm_path)},
        )
    pass_status = _dict_value(llm_payload.get("pass_status"))
    contribution = _dict_value(llm_payload.get("llm_contribution"))
    llm_ok = bool(pass_status.get("llm_contribution_pass", False))
    return PromotionCheck(
        name="llm_contribution",
        status="ok" if llm_ok else "blocked",
        message=(
            "LLM made an independently different route-selection decision for research."
            if llm_ok
            else "LLM route-selection contribution is not independently evidenced."
        ),
        details={
            "path": str(llm_path),
            "pass_status": pass_status,
            "llm_contribution": contribution,
            "choice": _dict_value(llm_payload.get("choice")),
        },
    )


def _adaptive_execution_check(spec: StrategySpec) -> PromotionCheck:
    blocked = [
        "adaptive router paper parity needs Nautilus target-weight mapping",
        f"execution.mode={spec.execution.mode}",
        f"execution.broker={spec.execution.broker}",
    ]
    return PromotionCheck(
        name="execution_reality",
        status="blocked",
        message="Adaptive router execution parity is not ready for paper automation.",
        details={
            "backend": spec.execution.backend,
            "mode": spec.execution.mode,
            "broker": spec.execution.broker,
            "blockers": blocked,
        },
    )


def _adaptive_benchmark_family(
    selected_candidate: dict[str, object] | None,
) -> dict[str, object]:
    full = _dict_value((selected_candidate or {}).get("full_window"))
    oos = _dict_value((selected_candidate or {}).get("out_of_sample"))
    quality_flags = [
        str(item) for item in (selected_candidate or {}).get("quality_flags", []) or []
    ]
    missing = []
    if not full or not oos:
        missing.append("selected_route_metrics")
    missing.append("sector_theme_proxy")
    return {
        "complete": not missing,
        "missing": missing,
        "benchmarks": {
            "same_symbol_buy_hold": {
                "status": "not_applicable",
                "note": "router is multi-symbol and does not map to one same-symbol baseline",
            },
            "equal_weight_universe": {
                "status": "ok" if full else "missing",
                "full_window_return_pct": full.get("universe_equal_weight_buy_hold_pct"),
                "oos_return_pct": oos.get("universe_equal_weight_buy_hold_pct"),
                "alpha_annualized_pct": oos.get("alpha_vs_equal_weight_annualized_pct"),
            },
            "market_proxy": {
                "status": "ok" if full.get("benchmark_symbol") else "missing",
                "symbol": full.get("benchmark_symbol"),
                "oos_buy_hold_return_pct": oos.get("benchmark_buy_hold_return_pct"),
                "oos_intraday_return_pct": oos.get("benchmark_intraday_return_pct"),
            },
            "sector_theme_proxy": {
                "status": "missing",
                "note": "sector/theme proxy is not registered for this NASDAQ basket yet",
            },
            "cash_proxy": {
                "status": "ok",
                "return_pct": 0.0,
                "oos_alpha_pct": oos.get("total_return_pct"),
            },
            "ex_post_best_symbol": {
                "status": "ok" if full.get("best_symbol") else "missing",
                "full_window_symbol": full.get("best_symbol"),
                "full_window_return_pct": full.get("best_symbol_buy_hold_pct"),
                "oos_symbol": oos.get("best_symbol"),
                "oos_return_pct": oos.get("best_symbol_buy_hold_pct"),
                "beat_ex_post_best_symbol": (
                    "does_not_beat_ex_post_best_symbol" not in quality_flags
                ),
            },
        },
        "quality_flags": quality_flags,
    }


def _adaptive_five_pass_checks(
    *,
    spec: StrategySpec,
    checks: list[PromotionCheck],
    acceptance_gate: dict[str, object],
    research_pass_status: dict[str, object],
    llm_payload: dict[str, object] | None,
) -> FivePassChecks:
    blocked = sorted(check.name for check in checks if check.status == "blocked")
    workflow_pass: FivePassStatus = (
        "pass" if bool(research_pass_status.get("workflow_pass", False)) else "fail"
    )
    research_pass: FivePassStatus = (
        "pass" if bool(research_pass_status.get("research_pass", False)) and not blocked else "fail"
    )
    llm_status = _dict_value((llm_payload or {}).get("pass_status"))
    if spec.llm_review.enabled:
        llm_contribution_pass: FivePassStatus = (
            "pass" if bool(llm_status.get("llm_contribution_pass", False)) else "fail"
        )
        llm_reason = (
            "LLM selected a route different from the deterministic top candidate"
            if llm_contribution_pass == "pass"
            else "LLM route-selection contribution is missing or not independent"
        )
    else:
        llm_contribution_pass = "not_applicable"
        llm_reason = "LLM review is disabled"
    expression_safety_pass, expression_reason = _expression_safety_pass(spec)
    return FivePassChecks(
        workflow_pass=workflow_pass,
        research_pass=research_pass,
        llm_contribution_pass=llm_contribution_pass,
        paper_ready_pass="fail",
        expression_safety_pass=expression_safety_pass,
        workflow_reason=(
            "adaptive router research workflow ran"
            if workflow_pass == "pass"
            else "adaptive router research workflow did not pass"
        ),
        research_reason=(
            "adaptive router research gates passed"
            if research_pass == "pass"
            else "blocked checks: " + ", ".join(blocked)
        ),
        llm_contribution_reason=llm_reason,
        paper_ready_reason=(
            "adaptive router remains blocked before paper automation; "
            f"acceptance_gate={acceptance_gate}"
        ),
        expression_safety_reason=expression_reason,
    )


def _adaptive_gate_summary(
    checks: list[PromotionCheck],
    five_pass_checks: FivePassChecks,
    benchmark_family: dict[str, object],
) -> dict[str, object]:
    blocked = sorted(check.name for check in checks if check.status == "blocked")
    warning = sorted(check.name for check in checks if check.status == "warning")
    return {
        "workflow_pass": five_pass_checks.workflow_pass == "pass",
        "research_pass": five_pass_checks.research_pass == "pass",
        "llm_contribution_pass": (
            None
            if five_pass_checks.llm_contribution_pass == "not_applicable"
            else five_pass_checks.llm_contribution_pass == "pass"
        ),
        "paper_ready_pass": False,
        "blocked_checks": blocked,
        "warning_checks": warning,
        "benchmark_family_complete": bool(benchmark_family.get("complete", False)),
    }


def _adaptive_parameter_ranges(spec: StrategySpec) -> dict[str, list[Any]]:
    notes = spec.notes.model_dump(mode="json")
    research_design = notes.get("research_design")
    if not isinstance(research_design, dict):
        return {}
    ranges = research_design.get("parameter_ranges")
    if not isinstance(ranges, dict):
        return {}
    return {str(key): value for key, value in ranges.items() if isinstance(value, list)}


def _write_adaptive_router_promotion_json(
    *,
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[PromotionCheck],
    benchmark_family: dict[str, object],
    data_profile: dict[str, object],
    manifest: dict[str, object],
    five_pass_checks: FivePassChecks,
    gate_summary: dict[str, object],
    index_record: ResearchRunIndexRecord,
    research_payload: dict[str, object] | None,
    llm_payload: dict[str, object] | None,
    selected_candidate: dict[str, object] | None,
) -> Path:
    payload = {
        "strategy_name": spec.name,
        "source_spec_path": str(spec_path),
        "status": status,
        "ready": ready,
        "mode": "adaptive_intraday_router_promotion",
        "gate_summary": gate_summary,
        "research_run_index_record": index_record.model_dump(mode="json"),
        "five_pass_checks": asdict(five_pass_checks),
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "message": check.message,
                "details": check.details,
            }
            for check in checks
        ],
        "selected_route": selected_candidate,
        "full_window": _dict_value((selected_candidate or {}).get("full_window")),
        "out_of_sample": _dict_value((selected_candidate or {}).get("out_of_sample")),
        "walk_forward": (research_payload or {}).get("walk_forward", []),
        "benchmark_family": benchmark_family,
        "data_profile": data_profile,
        "evidence_acquisition_tier": _evidence_acquisition_tier(spec, data_profile),
        "research_manifest": manifest,
        "adaptive_router_research": {
            "acceptance_gate": _dict_value((research_payload or {}).get("acceptance_gate")),
            "pass_status": _dict_value((research_payload or {}).get("pass_status")),
            "research_cost": _dict_value((research_payload or {}).get("research_cost")),
        },
        "llm_adaptive_router": {
            "status": (llm_payload or {}).get("status"),
            "choice": _dict_value((llm_payload or {}).get("choice")),
            "pass_status": _dict_value((llm_payload or {}).get("pass_status")),
            "llm_contribution": _dict_value((llm_payload or {}).get("llm_contribution")),
        },
        "safety_note": (
            "Adaptive router promotion is blocked until research, feature-packet, "
            "benchmark, execution, and paper-readiness gates pass."
        ),
    }
    return write_json(path, payload)


def _write_adaptive_router_promotion_markdown(
    *,
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[PromotionCheck],
    benchmark_family: dict[str, object],
    json_path: Path,
    data_profile: dict[str, object],
    manifest: dict[str, object],
    five_pass_checks: FivePassChecks,
    selected_candidate: dict[str, object] | None,
    llm_payload: dict[str, object] | None,
) -> Path:
    ensure_dir(path.parent)
    oos = _dict_value((selected_candidate or {}).get("out_of_sample"))
    full = _dict_value((selected_candidate or {}).get("full_window"))
    lines = [
        f"# Promotion Report: {spec.name}",
        "",
        f"- Status: `{status}`",
        f"- Ready for paper: `{'yes' if ready else 'no'}`",
        "- Mode: `adaptive_intraday_router_promotion`",
        "- Gate taxonomy: workflow_pass, research_pass, llm_contribution_pass, "
        "paper_ready_pass, expression_safety_pass.",
        "- Safety note: promotion evidence is not a promise of live returns.",
        f"- Data source mode: `{data_profile.get('source_mode') or 'unknown'}`",
        f"- Data as-of: `{data_profile.get('data_as_of') or 'unknown'}`",
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
    llm_contribution = _dict_value((llm_payload or {}).get("llm_contribution"))
    lines.extend(
        [
            "## Selected Route",
            "",
            f"- Route: `{_nested_route_label(selected_candidate or {}) or 'none'}`",
            f"- OOS return: `{_format_optional_pct(_float_or_none(oos.get('total_return_pct')))}`",
            f"- OOS annualized: "
            f"`{_format_optional_pct(_float_or_none(oos.get('annualized_return_pct')))}`",
            f"- OOS Sharpe: `{_float_or_none(oos.get('sharpe_ratio'))}`",
            f"- OOS max drawdown: "
            f"`{_format_optional_pct(_float_or_none(oos.get('max_drawdown_pct')))}`",
            f"- Full-window return: "
            f"`{_format_optional_pct(_float_or_none(full.get('total_return_pct')))}`",
            "",
            "## LLM Route Selection",
            "",
            f"- LLM status: `{(llm_payload or {}).get('status') or 'missing'}`",
            f"- Selected prompt rank: `{llm_contribution.get('selected_prompt_rank')}`",
            "",
            "## Benchmark Family",
            "",
            f"- Complete: `{benchmark_family.get('complete')}`",
            f"- Missing: `{', '.join(benchmark_family.get('missing', [])) or 'none'}`",
            "",
            "## Research Manifest",
            "",
            f"- Git commit: `{manifest.get('git_commit') or 'unknown'}`",
            f"- Git dirty: `{manifest.get('git_dirty')}`",
            f"- Spec hash: `{manifest.get('spec_hash')}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_hybrid_router_promotion_json(
    *,
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[PromotionCheck],
    benchmark_family: dict[str, object],
    data_profile: dict[str, object],
    manifest: dict[str, object],
    five_pass_checks: FivePassChecks,
    gate_summary: dict[str, object],
    index_record: ResearchRunIndexRecord,
    research_payload: dict[str, object] | None,
    selected_candidate: dict[str, object] | None,
) -> Path:
    payload = {
        "strategy_name": spec.name,
        "source_spec_path": str(spec_path),
        "status": status,
        "ready": ready,
        "mode": "hybrid_adaptive_router_promotion",
        "gate_summary": gate_summary,
        "research_run_index_record": index_record.model_dump(mode="json"),
        "five_pass_checks": asdict(five_pass_checks),
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "message": check.message,
                "details": check.details,
            }
            for check in checks
        ],
        "selected_route": selected_candidate,
        "full_window": _dict_value((selected_candidate or {}).get("full_window")),
        "out_of_sample": _dict_value((selected_candidate or {}).get("out_of_sample")),
        "walk_forward": (research_payload or {}).get("walk_forward", []),
        "benchmark_family": benchmark_family,
        "data_profile": data_profile,
        "evidence_acquisition_tier": _evidence_acquisition_tier(spec, data_profile),
        "research_manifest": manifest,
        "hybrid_router_research": {
            "acceptance_gate": _dict_value((research_payload or {}).get("acceptance_gate")),
            "pass_status": _dict_value((research_payload or {}).get("pass_status")),
            "research_cost": _dict_value((research_payload or {}).get("research_cost")),
        },
        "safety_note": (
            "Hybrid router promotion is blocked until feature-packet, benchmark, "
            "execution parity, and paper-readiness gates pass."
        ),
    }
    return write_json(path, payload)


def _write_beta_router_promotion_json(
    *,
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[PromotionCheck],
    benchmark_family: dict[str, object],
    data_profile: dict[str, object],
    manifest: dict[str, object],
    five_pass_checks: FivePassChecks,
    gate_summary: dict[str, object],
    index_record: ResearchRunIndexRecord,
    research_payload: dict[str, object] | None,
    selected_candidate: dict[str, object] | None,
) -> Path:
    payload = {
        "strategy_name": spec.name,
        "source_spec_path": str(spec_path),
        "status": status,
        "ready": ready,
        "mode": "beta_exposure_router_promotion",
        "gate_summary": gate_summary,
        "research_run_index_record": index_record.model_dump(mode="json"),
        "five_pass_checks": asdict(five_pass_checks),
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "message": check.message,
                "details": check.details,
            }
            for check in checks
        ],
        "selected_route": selected_candidate,
        "full_window": _dict_value((selected_candidate or {}).get("full_window")),
        "out_of_sample": _dict_value((selected_candidate or {}).get("out_of_sample")),
        "walk_forward": (research_payload or {}).get("walk_forward", []),
        "benchmark_family": benchmark_family,
        "data_profile": data_profile,
        "evidence_acquisition_tier": _evidence_acquisition_tier(spec, data_profile),
        "research_manifest": manifest,
        "beta_router_research": {
            "acceptance_gate": _dict_value((research_payload or {}).get("acceptance_gate")),
            "pass_status": _dict_value((research_payload or {}).get("pass_status")),
            "research_cost": _dict_value((research_payload or {}).get("research_cost")),
        },
        "safety_note": (
            "Beta router promotion is blocked until paper_auto activation, broker, "
            "kill-switch, and final paper-readiness gates pass."
        ),
    }
    return write_json(path, payload)


def _write_beta_router_promotion_markdown(
    *,
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[PromotionCheck],
    benchmark_family: dict[str, object],
    json_path: Path,
    data_profile: dict[str, object],
    manifest: dict[str, object],
    five_pass_checks: FivePassChecks,
    selected_candidate: dict[str, object] | None,
) -> Path:
    ensure_dir(path.parent)
    params = _dict_value((selected_candidate or {}).get("params"))
    oos = _dict_value((selected_candidate or {}).get("out_of_sample"))
    full = _dict_value((selected_candidate or {}).get("full_window"))
    lines = [
        f"# Promotion Report: {spec.name}",
        "",
        f"- Status: `{status}`",
        f"- Ready for paper: `{'yes' if ready else 'no'}`",
        "- Mode: `beta_exposure_router_promotion`",
        "- Gate taxonomy: workflow_pass, research_pass, llm_contribution_pass, "
        "paper_ready_pass, expression_safety_pass.",
        "- Safety note: beta research evidence is not a promise of live returns.",
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
    lines.extend(
        [
            "## Selected Route",
            "",
            f"- Route: `{params.get('label') or 'none'}`",
            f"- OOS annualized: "
            f"`{_format_optional_pct(_float_or_none(oos.get('annualized_return_pct')))}`",
            f"- OOS Alpha vs QQQ annualized: "
            f"`{_format_optional_pct(_float_or_none(oos.get('alpha_vs_market_buy_hold_annualized_pct')))}`",
            f"- OOS Sharpe: `{_float_or_none(oos.get('sharpe_ratio'))}`",
            f"- OOS max drawdown: "
            f"`{_format_optional_pct(_float_or_none(oos.get('max_drawdown_pct')))}`",
            f"- Full-window annualized: "
            f"`{_format_optional_pct(_float_or_none(full.get('annualized_return_pct')))}`",
            f"- Full-window Alpha vs QQQ annualized: "
            f"`{_format_optional_pct(_float_or_none(full.get('alpha_vs_market_buy_hold_annualized_pct')))}`",
            "",
            "## Benchmark Family",
            "",
            f"- Complete: `{benchmark_family.get('complete')}`",
            f"- Missing: `{', '.join(benchmark_family.get('missing', [])) or 'none'}`",
            "",
            "## Research Manifest",
            "",
            f"- Git commit: `{manifest.get('git_commit') or 'unknown'}`",
            f"- Git dirty: `{manifest.get('git_dirty')}`",
            f"- Spec hash: `{manifest.get('spec_hash')}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_hybrid_router_promotion_markdown(
    *,
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[PromotionCheck],
    benchmark_family: dict[str, object],
    json_path: Path,
    data_profile: dict[str, object],
    manifest: dict[str, object],
    five_pass_checks: FivePassChecks,
    selected_candidate: dict[str, object] | None,
) -> Path:
    ensure_dir(path.parent)
    oos = _dict_value((selected_candidate or {}).get("out_of_sample"))
    full = _dict_value((selected_candidate or {}).get("full_window"))
    lines = [
        f"# Promotion Report: {spec.name}",
        "",
        f"- Status: `{status}`",
        f"- Ready for paper: `{'yes' if ready else 'no'}`",
        "- Mode: `hybrid_adaptive_router_promotion`",
        "- Gate taxonomy: workflow_pass, research_pass, llm_contribution_pass, "
        "paper_ready_pass, expression_safety_pass.",
        "- Safety note: hybrid research evidence is not a promise of live returns.",
        f"- Data source mode: `{data_profile.get('source_mode') or 'unknown'}`",
        f"- Data as-of: `{data_profile.get('data_as_of') or 'unknown'}`",
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
    lines.extend(
        [
            "## Selected Route",
            "",
            f"- Route: `{_hybrid_candidate_label(selected_candidate or {}) or 'none'}`",
            f"- OOS return: `{_format_optional_pct(_float_or_none(oos.get('total_return_pct')))}`",
            f"- OOS annualized: "
            f"`{_format_optional_pct(_float_or_none(oos.get('annualized_return_pct')))}`",
            f"- OOS Alpha vs TQQQ buy-hold annualized: "
            f"`{_format_optional_pct(_float_or_none(oos.get('alpha_vs_benchmark_buy_hold_annualized_pct')))}`",
            f"- OOS Sharpe: `{_float_or_none(oos.get('sharpe_ratio'))}`",
            f"- OOS max drawdown: "
            f"`{_format_optional_pct(_float_or_none(oos.get('max_drawdown_pct')))}`",
            f"- Full-window return: "
            f"`{_format_optional_pct(_float_or_none(full.get('total_return_pct')))}`",
            "",
            "## Benchmark Family",
            "",
            f"- Complete: `{benchmark_family.get('complete')}`",
            f"- Missing: `{', '.join(benchmark_family.get('missing', [])) or 'none'}`",
            "",
            "## Research Manifest",
            "",
            f"- Git commit: `{manifest.get('git_commit') or 'unknown'}`",
            f"- Git dirty: `{manifest.get('git_dirty')}`",
            f"- Spec hash: `{manifest.get('spec_hash')}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _float_or_none(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _out_of_sample_check(
    *,
    spec: StrategySpec,
    frame,
    root: Path,
    out_of_sample_ratio: float,
) -> tuple[PromotionCheck, BacktestArtifacts | None]:
    split = max(int(len(frame) * (1 - out_of_sample_ratio)), 2)
    split = min(split, len(frame) - 1)
    oos_frame = frame.iloc[split:].copy()
    if len(oos_frame) < 2:
        return (
            PromotionCheck(
                name="out_of_sample",
                status="blocked",
                message="Not enough data left for an out-of-sample slice.",
                details={"rows": len(oos_frame)},
            ),
            None,
        )
    artifacts = backtest_frame(
        spec,
        oos_frame,
        root=root,
        run_id_value=f"promotion-{spec.name}-oos",
    )
    status = _status_from_sanity(
        artifacts.run.data_sanity.status if artifacts.run.data_sanity else "warning"
    )
    return (
        PromotionCheck(
            name="out_of_sample",
            status=status,
            message=(
                "Trailing slice evaluated as out-of-sample promotion evidence; "
                "compare with in-sample before using paper."
            ),
            details=_run_details(artifacts),
        ),
        artifacts,
    )


def _walk_forward_check(
    *,
    spec: StrategySpec,
    frame,
    root: Path,
    folds: int,
) -> tuple[PromotionCheck, list[BacktestArtifacts]]:
    folds = max(folds, 1)
    fold_size = max(len(frame) // (folds + 1), 2)
    runs: list[BacktestArtifacts] = []
    fold_details: list[dict[str, object]] = []
    for index in range(folds):
        start = (index + 1) * fold_size + 1
        end = min(len(frame), start + fold_size)
        wf_frame = frame.iloc[start:end].copy()
        if len(wf_frame) < 2:
            continue
        artifacts = backtest_frame(
            spec,
            wf_frame,
            root=root,
            run_id_value=f"promotion-{spec.name}-wf-{index + 1}",
        )
        runs.append(artifacts)
        fold_details.append(
            {
                "fold": index + 1,
                "rows": len(wf_frame),
                "total_return_pct": artifacts.run.total_return_pct,
                "annualized_return_pct": artifacts.run.annualized_return_pct,
                "sharpe_ratio": artifacts.run.sharpe_ratio,
                "status": artifacts.run.data_sanity.status
                if artifacts.run.data_sanity
                else "warning",
            }
        )
    if not runs:
        return (
            PromotionCheck(
                name="walk_forward",
                status="blocked",
                message="No walk-forward folds could be built from the available data.",
                details={"folds": folds},
            ),
            runs,
        )
    status = "ok" if all(item["status"] == "ok" for item in fold_details) else "warning"
    return (
        PromotionCheck(
            name="walk_forward",
            status=status,
            message="Sequential slices evaluated as walk-forward evidence.",
            details={
                "fold_count": len(runs),
                "folds": fold_details,
                "mean_return_pct": mean(item["total_return_pct"] for item in fold_details),
                "mean_sharpe": mean(float(item["sharpe_ratio"] or 0.0) for item in fold_details),
                "validation_policy": "sequential_walk_forward",
                "purged": True,
                "embargo_bars": 1,
                "embargo_note": (
                    "A one-bar embargo separates sequential validation slices in the "
                    "lightweight promotion gate."
                ),
            },
        ),
        runs,
    )


def _cost_sensitivity_check(
    *,
    spec: StrategySpec,
    frame,
    root: Path,
    slippage_bps: list[int],
) -> tuple[PromotionCheck, list[BacktestArtifacts]]:
    runs: list[BacktestArtifacts] = []
    details: list[dict[str, object]] = []
    for bps in slippage_bps:
        candidate = _clone_spec_with_costs(spec, slippage_bps=bps)
        artifacts = backtest_frame(
            candidate,
            frame,
            root=root,
            run_id_value=f"promotion-{spec.name}-cost-{bps}",
        )
        runs.append(artifacts)
        details.append(
            {
                "slippage_bps": bps,
                "total_return_pct": artifacts.run.total_return_pct,
                "annualized_return_pct": artifacts.run.annualized_return_pct,
                "sharpe_ratio": artifacts.run.sharpe_ratio,
                "status": artifacts.run.data_sanity.status
                if artifacts.run.data_sanity
                else "warning",
            }
        )
    status = "ok" if all(item["status"] == "ok" for item in details) else "warning"
    return (
        PromotionCheck(
            name="cost_sensitivity",
            status=status,
            message="Backtests rerun under multiple slippage assumptions.",
            details={
                "scenarios": details,
            },
        ),
        runs,
    )


def _factor_lab_check(result) -> PromotionCheck:
    details = {
        "status": result.status,
        "report_path": str(result.report_path),
        "json_path": str(result.json_path),
        "quality_flags": result.quality_flags,
        "factor_count": len(result.factor_metrics),
    }
    if result.status == "blocked":
        return PromotionCheck(
            name="factor_lab",
            status="blocked",
            message="Factor Lab diagnostics are blocked: " + ", ".join(result.quality_flags),
            details=details,
        )
    if result.status == "warning":
        return PromotionCheck(
            name="factor_lab",
            status="warning",
            message="Factor Lab diagnostics produced warnings.",
            details=details,
        )
    return PromotionCheck(
        name="factor_lab",
        status="ok",
        message="Factor Lab diagnostics passed.",
        details=details,
    )


def _execution_reality_check(full: BacktestArtifacts) -> PromotionCheck:
    reality = full.run.execution_reality
    if reality is None:
        return PromotionCheck(
            name="execution_reality",
            status="blocked",
            message="Execution reality metrics are missing.",
            details={},
        )
    details = reality.model_dump(mode="json")
    if reality.status == "blocked":
        return PromotionCheck(
            name="execution_reality",
            status="blocked",
            message="Execution reality blocks promotion: " + "; ".join(reality.warnings),
            details=details,
        )
    if reality.status == "warning":
        return PromotionCheck(
            name="execution_reality",
            status="warning",
            message="Execution reality warnings require review.",
            details=details,
        )
    return PromotionCheck(
        name="execution_reality",
        status="ok",
        message="Execution reality diagnostics passed.",
        details=details,
    )


def _alternative_data_check(result) -> PromotionCheck:
    details = {
        "status": result.status,
        "report_path": str(result.report_path),
        "json_path": str(result.json_path),
        "warnings": result.warnings,
        "factor_count": len(result.rows),
    }
    if result.status == "blocked":
        return PromotionCheck(
            name="alternative_data",
            status="blocked",
            message="Alternative data quality blocks promotion: " + ", ".join(result.warnings),
            details=details,
        )
    if result.status == "warning":
        return PromotionCheck(
            name="alternative_data",
            status="warning",
            message="Alternative data quality produced warnings.",
            details=details,
        )
    return PromotionCheck(
        name="alternative_data",
        status="ok",
        message="Alternative data quality passed or no alternative data is used.",
        details=details,
    )


def _harness_artifacts_promotion_check(spec: StrategySpec, root: Path) -> PromotionCheck:
    """Promotion gate that mirrors `oc harness verify` for risk-domain artifacts.

    Strategies with no active risk domains pass. Otherwise every artifact required
    by the active domains must be present and contain the contract's required
    fields, or promotion is blocked.
    """
    from open_composer.harness.policy import (
        blocking_rules_for_domains,
        check_artifact,
        detect_risk_domains,
        required_artifacts_for_domains,
    )

    active = detect_risk_domains(spec, root)
    required = sorted(required_artifacts_for_domains(active))
    if not required:
        return PromotionCheck(
            name="harness_artifacts",
            status="ok",
            message="No risk domains active; no harness artifacts required.",
            details={"risk_domains": active},
        )

    statuses = [check_artifact(name, spec.name, root) for name in required]
    missing = [s.name for s in statuses if not s.present]
    incomplete = [
        {"name": s.name, "missing_fields": s.missing_fields}
        for s in statuses
        if s.present and not s.schema_ok
    ]
    research_blocking_rules = [
        r.rule_id for r in blocking_rules_for_domains(active) if r.blocks == "research_pass"
    ]

    if missing or incomplete:
        # Migration policy: warn by default; set OC_HARNESS_STRICT=1 to block promotion.
        import os

        strict = os.environ.get("OC_HARNESS_STRICT", "0") == "1"
        status: PromotionStatus = "blocked" if strict else "warning"
        prefix = "blocked" if strict else "legacy_harness_review_required"
        return PromotionCheck(
            name="harness_artifacts",
            status=status,
            message=(
                f"Harness artifacts {prefix}: "
                f"missing={missing or '-'}, "
                f"incomplete={[c['name'] for c in incomplete] or '-'}, "
                f"domains={active}"
            ),
            details={
                "risk_domains": active,
                "required_artifacts": required,
                "missing": missing,
                "incomplete": incomplete,
                "research_blocking_rules": research_blocking_rules,
                "strict_mode": strict,
            },
        )
    return PromotionCheck(
        name="harness_artifacts",
        status="ok",
        message=f"All {len(required)} harness artifacts present for domains {active}.",
        details={"risk_domains": active, "required_artifacts": required},
    )


def _research_design_check(spec: StrategySpec) -> PromotionCheck:
    design = spec.research_design.model_dump(mode="json") if spec.research_design else None
    notes = spec.notes.model_dump(mode="json")
    legacy = notes.get("research_design") if isinstance(notes, dict) else None
    source = design if isinstance(design, dict) else legacy if isinstance(legacy, dict) else {}
    missing: list[str] = []
    parameter_space = source.get("parameter_space") or source.get("parameter_ranges")
    objective = source.get("selection_objective") or source.get("objective")
    candidate_budget = source.get("candidate_budget") or source.get("candidate_cap")
    validation_plan = source.get("validation_plan") or source.get("default_validation")
    anti_overfit = source.get("anti_overfit_notes") or source.get("anti_overfit")
    if not isinstance(parameter_space, dict) or not parameter_space:
        missing.append("parameter_space")
    if not objective:
        missing.append("selection_objective")
    if not candidate_budget:
        missing.append("candidate_budget")
    if not validation_plan:
        missing.append("validation_plan")
    if not anti_overfit:
        missing.append("anti_overfit_notes")
    if missing:
        return PromotionCheck(
            name="research_design",
            status="warning",
            message="Research design is incomplete: " + ", ".join(missing),
            details={"missing": missing, "source": source},
        )
    return PromotionCheck(
        name="research_design",
        status="ok",
        message="Research design defines parameter space, objective, budget, and validation plan.",
        details={"source": source},
    )


def _evidence_acquisition_tier(
    spec: StrategySpec,
    data_profile: dict[str, object],
) -> str:
    if spec.data_assumptions.acquisition_tier:
        return spec.data_assumptions.acquisition_tier
    source_mode = str(data_profile.get("source_mode") or data_profile.get("data_source_mode") or "")
    if spec.data.source == "sample" or "sample" in source_mode:
        return "sample_smoke"
    if "fixture" in source_mode or "fallback" in source_mode:
        return "fixture_replay"
    if source_mode == "live_fetch":
        return "paper_ready_live"
    if source_mode == "cache":
        return "cached_live"
    return "research_cross_check"


def _data_comparison_check(
    spec: StrategySpec,
    root: Path,
) -> tuple[PromotionCheck, list[dict[str, object]]]:
    comparisons_root = root / "reports" / "data" / "comparisons"
    rows: list[dict[str, object]] = []
    if not comparisons_root.exists():
        return (
            PromotionCheck(
                name="data_comparison",
                status="warning",
                message="No data comparison reports are available yet.",
                details={},
            ),
            rows,
        )
    for path in sorted(comparisons_root.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        if raw.get("symbol", "").upper() != spec.primary_symbol.upper():
            continue
        if raw.get("timeframe") != spec.timeframe:
            continue
        rows.append(
            {
                "path": str(path),
                "left_source": raw.get("left_source"),
                "right_source": raw.get("right_source"),
                "coverage_pct": raw.get("matched_coverage_pct"),
                "max_close_diff_bps": raw.get("max_abs_close_diff_bps"),
                "missing_left_rows": raw.get("missing_left_rows"),
                "missing_right_rows": raw.get("missing_right_rows"),
            }
        )
    if not rows:
        return (
            PromotionCheck(
                name="data_comparison",
                status="warning",
                message="No matching data comparison report found for this strategy.",
                details={},
            ),
            rows,
        )
    return (
        PromotionCheck(
            name="data_comparison",
            status="ok",
            message="Matching data comparison reports are available.",
            details={"comparisons": rows},
        ),
        rows,
    )


def _strict_data_check(spec: StrategySpec, artifacts: BacktestArtifacts) -> PromotionCheck:
    sanity = artifacts.run.data_sanity
    mode = sanity.data_source_mode if sanity else None
    evidence_level = sanity.evidence_level if sanity else "unknown"
    warnings = sanity.warnings if sanity else []
    acquisition_tier = _evidence_acquisition_tier(
        spec,
        {"source_mode": mode or "", "data_source_mode": mode or ""},
    )
    blocked_reasons: list[str] = []
    if spec.data.source == "sample":
        blocked_reasons.append("sample data is workflow evidence only")
    if acquisition_tier in DATA_TIERS_NOT_PAPER_READY:
        blocked_reasons.append(f"acquisition_tier={acquisition_tier} is not paper-ready")
    mode_text = mode or ""
    if any(token in mode_text for token in ["sample", "fixture", "fallback"]):
        blocked_reasons.append(f"data_source_mode={mode_text} is not paper-ready")
    if evidence_level.startswith("E0"):
        blocked_reasons.append(f"evidence_level={evidence_level} is not paper-ready")
    if blocked_reasons:
        return PromotionCheck(
            name="strict_data",
            status="blocked",
            message="Promotion requires research_strict or paper_ready data; "
            + "; ".join(blocked_reasons),
            details={
                "data_source": spec.data.source,
                "data_source_mode": mode,
                "evidence_level": evidence_level,
                "acquisition_tier": acquisition_tier,
                "warnings": warnings,
            },
        )
    return PromotionCheck(
        name="strict_data",
        status="ok",
        message="Promotion data is not sample, fixture, or fallback evidence.",
        details={
            "data_source": spec.data.source,
            "data_source_mode": mode,
            "evidence_level": evidence_level,
            "acquisition_tier": acquisition_tier,
        },
    )


def _feature_packet_check(spec: StrategySpec, root: Path) -> PromotionCheck:
    inspected: list[dict[str, object]] = []
    missing_or_incomplete: list[str] = []
    for name, factor in spec.factors.items():
        if factor.source not in {"llm_feature", "feature_packet"}:
            continue
        if not factor.path:
            missing_or_incomplete.append(f"{name}: missing packet path")
            inspected.append({"factor": name, "status": "missing"})
            continue
        path = _resolve_path(root, factor.path)
        inspection = inspect_feature_packet(path, factor.field)
        inspected.append(
            {
                "factor": name,
                "path": factor.path,
                "field": factor.field,
                "status": inspection.point_in_time_status,
                "warnings": inspection.replay_warnings,
                "evidence_count": inspection.evidence_count,
                "missing_evidence_count": inspection.missing_evidence_count,
            }
        )
        if not inspection.exists or inspection.point_in_time_status != "complete":
            warning_text = "; ".join(inspection.replay_warnings[:3]) or "not PIT complete"
            missing_or_incomplete.append(
                f"{name}: {inspection.point_in_time_status} at {factor.path}: {warning_text}"
            )
        elif inspection.missing_evidence_count:
            missing_or_incomplete.append(
                f"{name}: {inspection.missing_evidence_count} packet row(s) at "
                f"{factor.path} lack marginal-lift evidence"
            )
    if missing_or_incomplete:
        return PromotionCheck(
            name="feature_packets",
            status="blocked",
            message="Promotion requires PIT-complete feature packets: "
            + "; ".join(missing_or_incomplete),
            details={"inspected": inspected},
        )
    return PromotionCheck(
        name="feature_packets",
        status="ok",
        message="Feature packet factors are absent or PIT-complete.",
        details={"inspected": inspected},
    )


def _benchmark_family_check(
    spec: StrategySpec,
    full: BacktestArtifacts,
) -> tuple[PromotionCheck, dict[str, object]]:
    run = full.run
    same_symbol = {
        "status": "ok" if run.buy_hold_return_pct is not None else "missing",
        "symbol": spec.primary_symbol,
        "return_pct": run.buy_hold_return_pct,
        "alpha_pct": run.alpha_vs_buy_hold_pct,
    }
    equal_weight = {
        "status": "ok" if run.buy_hold_return_pct is not None else "missing",
        "symbols": spec.universe,
        "return_pct": run.buy_hold_return_pct if len(spec.universe) == 1 else None,
        "alpha_pct": run.alpha_vs_buy_hold_pct if len(spec.universe) == 1 else None,
        "note": (
            "single-symbol universe matches same-symbol buy-and-hold"
            if len(spec.universe) == 1
            else "multi-symbol equal-weight benchmark requires synchronized universe bars"
        ),
    }
    cash = {
        "status": "ok",
        "return_pct": 0.0,
        "alpha_pct": run.total_return_pct,
        "note": "cash proxy uses 0% return until a T-bill series is registered",
    }
    ex_post_best = {
        "status": "ok" if len(spec.universe) == 1 else "missing",
        "symbol": spec.primary_symbol if len(spec.universe) == 1 else None,
        "return_pct": run.buy_hold_return_pct if len(spec.universe) == 1 else None,
        "beat_ex_post_best_symbol": (
            run.total_return_pct > run.buy_hold_return_pct
            if run.buy_hold_return_pct is not None and len(spec.universe) == 1
            else None
        ),
        "note": "ex-post best symbol is a non-tradable upper-bound benchmark",
    }
    market = {
        "status": "not_applicable",
        "proxy": None,
        "note": "market proxy (e.g. SPY, QQQ) requires manual attachment; not auto-computed",
    }
    sector = {
        "status": "not_applicable",
        "proxy": None,
        "note": "sector/theme proxy requires manual attachment; not auto-computed from spec",
    }
    benchmarks = {
        "same_symbol_buy_hold": same_symbol,
        "equal_weight_universe": equal_weight,
        "market_proxy": market,
        "sector_theme_proxy": sector,
        "cash_proxy": cash,
        "ex_post_best_symbol": ex_post_best,
    }
    missing = [name for name, item in benchmarks.items() if item.get("status") == "missing"]
    family = {
        "complete": not missing,
        "missing": missing,
        "benchmarks": benchmarks,
        "alpha_summary": {
            "alpha_vs_same_symbol": run.alpha_vs_buy_hold_pct,
            "alpha_vs_equal_weight": equal_weight.get("alpha_pct"),
            "alpha_vs_market": None,
            "alpha_vs_sector": None,
            "alpha_vs_cash": run.total_return_pct,
            "beat_ex_post_best_symbol": ex_post_best.get("beat_ex_post_best_symbol"),
        },
    }
    if missing:
        return (
            PromotionCheck(
                name="benchmark_family",
                status="warning",
                message="Promotion benchmark family is incomplete: " + ", ".join(missing),
                details=family,
            ),
            family,
        )
    return (
        PromotionCheck(
            name="benchmark_family",
            status="ok",
            message="Promotion benchmark family is complete.",
            details=family,
        ),
        family,
    )


def _clone_spec_with_costs(spec: StrategySpec, *, slippage_bps: int) -> StrategySpec:
    raw = copy.deepcopy(spec.model_dump(mode="json"))
    raw["costs"] = {**raw["costs"], "slippage_bps": slippage_bps}
    return StrategySpec.model_validate(raw)


def _run_details(artifacts: BacktestArtifacts) -> dict[str, object]:
    run = artifacts.run
    return {
        "run_id": run.run_id,
        "bars": run.bars,
        "signals": run.signals,
        "trades": run.trades,
        "total_return_pct": run.total_return_pct,
        "buy_hold_return_pct": run.buy_hold_return_pct,
        "alpha_vs_buy_hold_pct": run.alpha_vs_buy_hold_pct,
        "annualized_return_pct": run.annualized_return_pct,
        "sharpe_ratio": run.sharpe_ratio,
        "annualized_volatility_pct": run.annualized_volatility_pct,
        "max_drawdown_pct": run.max_drawdown_pct,
        "sortino_ratio": run.sortino_ratio,
        "calmar_ratio": run.calmar_ratio,
        "win_rate_pct": run.win_rate_pct,
        "profit_factor": run.profit_factor,
        "exposure_pct": run.exposure_pct,
        "turnover_ratio": run.turnover_ratio,
        "execution_reality_status": (
            run.execution_reality.status if run.execution_reality else "unknown"
        ),
        "data_sanity_status": run.data_sanity.status if run.data_sanity else "warning",
        "evidence_level": run.data_sanity.evidence_level if run.data_sanity else "unknown",
    }


def _status_from_sanity(status: str) -> PromotionStatus:
    return "ok" if status == "ok" else "warning"


def _write_promotion_json(
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[PromotionCheck],
    full: BacktestArtifacts,
    oos: BacktestArtifacts | None,
    walk_forward_runs: list[BacktestArtifacts],
    cost_runs: list[BacktestArtifacts],
    comparison_rows: list[dict[str, object]],
    benchmark_family: dict[str, object],
    data_profile: dict[str, object],
    manifest: dict[str, object],
    five_pass_checks: FivePassChecks,
    gate_summary: dict[str, object],
    index_record: ResearchRunIndexRecord,
) -> Path:
    ensure_dir(path.parent)
    payload = {
        "strategy_name": spec.name,
        "source_spec_path": str(spec_path),
        "status": status,
        "ready": ready,
        "gate_summary": gate_summary,
        "research_run_index_record": index_record.model_dump(mode="json"),
        "five_pass_checks": asdict(five_pass_checks),
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "message": check.message,
                "details": check.details,
            }
            for check in checks
        ],
        "full_window": _run_details(full),
        "out_of_sample": _run_details(oos) if oos else None,
        "walk_forward": [_run_details(item) for item in walk_forward_runs],
        "cost_sensitivity": [_run_details(item) for item in cost_runs],
        "data_comparisons": comparison_rows,
        "benchmark_family": benchmark_family,
        "data_profile": data_profile,
        "evidence_acquisition_tier": _evidence_acquisition_tier(spec, data_profile),
        "research_manifest": manifest,
        "safety_note": (
            "Promotion ready means research and paper-readiness gates passed; it is not a "
            "promise of live returns."
        ),
    }
    write_json(path, payload)
    return path


def _write_promotion_report(
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[PromotionCheck],
    full: BacktestArtifacts,
    oos: BacktestArtifacts | None,
    walk_forward_runs: list[BacktestArtifacts],
    cost_runs: list[BacktestArtifacts],
    comparison_rows: list[dict[str, object]],
    benchmark_family: dict[str, object],
    json_path: Path,
    data_profile: dict[str, object],
    manifest: dict[str, object],
    five_pass_checks: FivePassChecks,
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Promotion Report: {spec.name}",
        "",
        f"- Status: `{status}`",
        f"- Ready for paper: `{'yes' if ready else 'no'}`",
        "- Gate taxonomy: workflow_pass, research_pass, llm_contribution_pass, "
        "paper_ready_pass, expression_safety_pass.",
        "- Safety note: promotion evidence is not a promise of live returns.",
        f"- Data source mode: `{data_profile.get('source_mode') or 'unknown'}`",
        f"- Data as-of: `{data_profile.get('data_as_of') or 'unknown'}`",
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
        "**Ready to advance toward paper readiness?** "
        + ("yes" if five_pass_checks.paper_ready_pass == "pass" else "no"),
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
    lines.extend(
        [
            "## Full Window",
            "",
            *_run_lines(full),
            "",
            "## Out Of Sample",
            "",
            *(_run_lines(oos) if oos is not None else ["- No out-of-sample slice was available."]),
            "",
            "## Walk Forward",
            "",
        ]
    )
    if walk_forward_runs:
        for item in walk_forward_runs:
            lines.extend(_run_lines(item))
            lines.append("")
    else:
        lines.append("- No walk-forward runs were produced.")
    lines.extend(["## Cost Sensitivity", ""])
    if cost_runs:
        for item in cost_runs:
            lines.extend(_run_lines(item))
            lines.append("")
    else:
        lines.append("- No cost sensitivity runs were produced.")
        lines.append("")
    lines.extend(["## Data Comparisons", ""])
    if comparison_rows:
        for row in comparison_rows:
            lines.append(
                f"- `{row.get('left_source')}` vs `{row.get('right_source')}` "
                f"coverage `{row.get('coverage_pct')}` max_close_diff_bps "
                f"`{row.get('max_close_diff_bps')}`"
            )
    else:
        lines.append("- No matching data comparison reports were found.")
    lines.extend(["", "## Benchmark Family", ""])
    lines.append(f"- Complete: `{benchmark_family.get('complete')}`")
    lines.append(f"- Missing: `{', '.join(benchmark_family.get('missing', [])) or 'none'}`")
    benchmarks = benchmark_family.get("benchmarks")
    if isinstance(benchmarks, dict):
        for name, item in benchmarks.items():
            lines.append(f"- `{name}`: `{item}`")
    lines.extend(["", "## Research Manifest", ""])
    lines.append(f"- Git commit: `{manifest.get('git_commit') or 'unknown'}`")
    lines.append(f"- Git dirty: `{manifest.get('git_dirty')}`")
    lines.append(f"- Spec hash: `{manifest.get('spec_hash')}`")
    lines.append(f"- Data path hash: `{manifest.get('data_path_hash') or 'n/a'}`")
    regime_path = path.parent.parent / "regime_search" / f"{spec.name}.json"
    if regime_path.exists():
        lines.extend(["", "## Similar Regimes", ""])
        try:
            regime = json.loads(regime_path.read_text(encoding="utf-8"))
            for match in regime.get("matches", [])[:3]:
                lines.append(
                    f"- `{match.get('window_end')}` similarity "
                    f"`{float(match.get('similarity', 0.0)):.3f}`: "
                    f"{match.get('market_note')}"
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            lines.append("- Regime report exists but could not be parsed.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _gate_summary(
    spec: StrategySpec,
    ready: bool,
    checks: list[PromotionCheck],
    benchmark_family: dict[str, object],
) -> dict[str, object]:
    blocked = {check.name for check in checks if check.status == "blocked"}
    warning = {check.name for check in checks if check.status == "warning"}
    llm_related = bool(spec.llm_review.enabled or _feature_packet_paths(spec))
    return {
        "workflow_pass": "in_sample" not in blocked,
        "research_pass": not blocked,
        "llm_contribution_pass": None if not llm_related else "feature_packets" not in blocked,
        "paper_ready_pass": ready,
        "blocked_checks": sorted(blocked),
        "warning_checks": sorted(warning),
        "benchmark_family_complete": bool(benchmark_family.get("complete", False)),
    }


def _five_pass_checks(
    spec: StrategySpec,
    ready: bool,
    checks: list[PromotionCheck],
    root: Path,
) -> FivePassChecks:
    by_name = {check.name: check for check in checks}
    blocked = {check.name for check in checks if check.status == "blocked"}
    warning = {check.name for check in checks if check.status == "warning"}

    workflow_failures = [
        name
        for name in ["in_sample", "feature_packets"]
        if name in blocked or by_name.get(name, PromotionCheck(name, "ok", "")).status == "blocked"
    ]
    workflow_pass: FivePassStatus = "fail" if workflow_failures else "pass"
    workflow_reason = (
        "blocked checks: " + ", ".join(workflow_failures)
        if workflow_failures
        else "spec loaded, expressions validated, and reference backtest ran"
    )

    research_gate_names = {
        "out_of_sample",
        "walk_forward",
        "cost_sensitivity",
        "data_comparison",
        "benchmark_family",
        "factor_lab",
        "execution_reality",
        "alternative_data",
        "harness_artifacts",
        "research_design",
    }
    research_failures = sorted(name for name in research_gate_names if name in blocked)
    cost_grid_warning = _cost_grid_warning(spec, root)
    if cost_grid_warning:
        research_failures.append("cost_grid")
    research_pass: FivePassStatus = "fail" if research_failures else "pass"
    research_reason = (
        "missing or weak research evidence: "
        + ", ".join(research_failures)
        + (f"; {cost_grid_warning}" if cost_grid_warning else "")
        if research_failures
        else "OOS, walk-forward, cost, data comparison, and benchmark gates passed"
    )

    llm_related = bool(spec.llm_review.enabled or _feature_packet_paths(spec))
    if not llm_related:
        llm_contribution_pass: FivePassStatus = "not_applicable"
        llm_reason = "strategy does not use LLM review or LLM/feature packet factors"
    elif "feature_packets" in blocked:
        llm_contribution_pass = "fail"
        llm_reason = "LLM/feature packet factors are missing PIT-complete evidence"
    else:
        llm_contribution_pass, llm_reason = _blind_test_contribution_pass(spec, root)

    paper_ready_pass: FivePassStatus = "pass" if ready else "fail"
    paper_reason = (
        "all promotion checks are ok"
        if ready
        else "blocked checks: " + ", ".join(sorted(blocked or warning))
    )

    expression_safety_pass, code_reason = _expression_safety_pass(spec)

    return FivePassChecks(
        workflow_pass=workflow_pass,
        research_pass=research_pass,
        llm_contribution_pass=llm_contribution_pass,
        paper_ready_pass=paper_ready_pass,
        expression_safety_pass=expression_safety_pass,
        workflow_reason=workflow_reason,
        research_reason=research_reason,
        llm_contribution_reason=llm_reason,
        paper_ready_reason=paper_reason,
        expression_safety_reason=code_reason,
    )


def _expression_safety_pass(spec: StrategySpec) -> tuple[FivePassStatus, str]:
    expressions = [
        *spec.all_expressions(),
        *[
            factor.expression
            for factor in spec.factors.values()
            if factor.source == "expression" and factor.expression
        ],
    ]
    for expression in expressions:
        try:
            assert_expression_safe(expression)
        except ExpressionSafetyError as exc:
            return "fail", f"AST safety check failed for {expression!r}: {exc}"
    return "pass", "all rule and expression-factor formulas pass the AST safety whitelist"


def _blind_test_contribution_pass(spec: StrategySpec, root: Path) -> tuple[FivePassStatus, str]:
    report = load_blind_test_report(spec.name, root)
    if report is None:
        return (
            "fail",
            f"missing BlindTrade counterfactual report: reports/blind_test/{spec.name}.json",
        )
    by_mode = {result.mode: result for result in report.results}
    real = by_mode.get("real")
    anonymous = by_mode.get("anonymous")
    if real is None or anonymous is None:
        return "fail", "blind-test report must include real and anonymous modes"
    sharpe_diff = abs(real.sharpe - anonymous.sharpe)
    if sharpe_diff > 0.3:
        return "fail", f"anonymous Sharpe differs from real by {sharpe_diff:.2f}"
    if anonymous.correlation_with_real is not None and anonymous.correlation_with_real < 0.8:
        return (
            "fail",
            f"anonymous signal correlation with real is {anonymous.correlation_with_real:.2f}",
        )
    return "pass", "BlindTrade anonymous mode stays within Sharpe and signal-correlation thresholds"


def _cost_grid_warning(spec: StrategySpec, root: Path) -> str:
    path = root / "reports" / "cost_grid" / f"{spec.name}.json"
    if not path.exists():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "cost-grid report is not valid JSON"
    spread = raw.get("ranking_spread")
    if isinstance(spread, int | float) and float(spread) > 1.0:
        return f"cost-grid Sharpe spread {float(spread):.2f} exceeds 1.00"
    return ""


def _five_pass_markdown_rows(five_pass_checks: FivePassChecks) -> list[str]:
    rows = [
        ("workflow_pass", five_pass_checks.workflow_pass, five_pass_checks.workflow_reason),
        ("research_pass", five_pass_checks.research_pass, five_pass_checks.research_reason),
        (
            "llm_contribution_pass",
            five_pass_checks.llm_contribution_pass,
            five_pass_checks.llm_contribution_reason,
        ),
        (
            "paper_ready_pass",
            five_pass_checks.paper_ready_pass,
            five_pass_checks.paper_ready_reason,
        ),
        (
            "expression_safety_pass",
            five_pass_checks.expression_safety_pass,
            five_pass_checks.expression_safety_reason,
        ),
    ]
    return [
        f"| {name} | {_status_icon(status)} `{status}` | {reason} |"
        for name, status, reason in rows
    ]


def _status_icon(status: FivePassStatus) -> str:
    return {
        "pass": "PASS",
        "fail": "FAIL",
        "skipped": "SKIP",
        "not_applicable": "N/A",
    }[status]


def _feature_packet_paths(spec: StrategySpec) -> list[str]:
    return sorted(
        str(factor.path)
        for factor in spec.factors.values()
        if factor.source in {"llm_feature", "feature_packet"} and factor.path
    )


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _run_lines(artifacts: BacktestArtifacts | None) -> list[str]:
    if artifacts is None:
        return ["- No run."]
    run = artifacts.run
    return [
        f"- Run: `{run.run_id}`",
        f"- Return: `{run.total_return_pct:.2f}%`",
        f"- Buy/Hold: `{_format_optional_pct(run.buy_hold_return_pct)}`",
        f"- Alpha vs Buy/Hold: `{_format_optional_pct(run.alpha_vs_buy_hold_pct)}`",
        f"- Annualized: `{run.annualized_return_pct:.2f}%`"
        if run.annualized_return_pct is not None
        else "- Annualized: `n/a`",
        f"- Sharpe: `{run.sharpe_ratio:.2f}`"
        if run.sharpe_ratio is not None
        else "- Sharpe: `n/a`",
        f"- Signals: `{run.signals}`",
        f"- Trades: `{run.trades}`",
        f"- Data sanity: `{run.data_sanity.status if run.data_sanity else 'warning'}`",
        f"- Evidence level: `{run.data_sanity.evidence_level if run.data_sanity else 'unknown'}`",
    ]


def _format_optional_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def _relpath(path: Path | str, base: Path) -> str:
    candidate = Path(path)
    try:
        return candidate.relative_to(base).as_posix()
    except ValueError:
        return candidate.as_posix()
