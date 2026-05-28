from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Literal

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import BacktestArtifacts, backtest_frame
from open_composer.expressions import ExpressionSafetyError, assert_expression_safe
from open_composer.feature_packets import (
    feature_packet_path_for_factor,
    feature_packet_path_label,
    inspect_feature_packet,
)
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.alpha_decay import build_alpha_decay_report
from open_composer.research.alt_data_quality import build_alternative_data_quality_report
from open_composer.research.blind_test import load_blind_test_report
from open_composer.research.contracts import write_research_contract
from open_composer.research.factor_lab import run_factor_lab
from open_composer.research.kernel import GateResult, ResearchArtifactWriter, ResearchRunIndexRecord
from open_composer.research.metadata import (
    frame_data_profile,
    research_run_manifest,
    runtime_payload,
    search_space,
)
from open_composer.research.pbo import build_overfit_risk_report
from open_composer.research.regime_performance import build_regime_performance_report
from open_composer.research.research_brief import validate_research_brief
from open_composer.research.universe_audit import assess_universe_audit
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
PassSummary = dict[str, str]


def _pass_summary(
    *,
    workflow_pass: FivePassStatus,
    research_pass: FivePassStatus,
    llm_contribution_pass: FivePassStatus,
    paper_ready_pass: FivePassStatus,
    expression_safety_pass: FivePassStatus,
    workflow_reason: str = "",
    research_reason: str = "",
    llm_contribution_reason: str = "",
    paper_ready_reason: str = "",
    expression_safety_reason: str = "",
) -> PassSummary:
    return {
        "workflow_pass": workflow_pass,
        "research_pass": research_pass,
        "llm_contribution_pass": llm_contribution_pass,
        "paper_ready_pass": paper_ready_pass,
        "expression_safety_pass": expression_safety_pass,
        "workflow_reason": workflow_reason,
        "research_reason": research_reason,
        "llm_contribution_reason": llm_contribution_reason,
        "paper_ready_reason": paper_ready_reason,
        "expression_safety_reason": expression_safety_reason,
    }


def _pass_value(summary: PassSummary, name: str) -> str:
    return str(summary.get(name, "fail"))


def _pass_reason(summary: PassSummary, name: str) -> str:
    return str(summary.get(name, ""))


ROUTER_PROMOTION_MODES = {
    "adaptive_intraday_internal_router",
    "hybrid_adaptive_router",
    "beta_exposure_router",
}


@dataclass(frozen=True)
class PromotionReport:
    strategy_name: str
    source_spec_path: str
    status: PromotionStatus
    ready: bool
    checks: list[GateResult]
    report_path: str
    json_path: str
    workflow_pass: bool = False
    research_pass: bool = False
    llm_contribution_pass: bool | None = None
    paper_ready_pass: bool = False
    pass_reasons: dict[str, str] = field(default_factory=dict)
    five_pass_checks: PassSummary | None = None


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
    if spec.portfolio.mode in ROUTER_PROMOTION_MODES:
        from open_composer.research.router_promotion import build_router_promotion_report

        return build_router_promotion_report(
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
    checks: list[GateResult] = []
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
        GateResult(
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
    universe_audit_check = _universe_audit_promotion_check(spec, base)
    checks.append(universe_audit_check)

    feature_packet_check = _feature_packet_check(spec, base)
    checks.append(feature_packet_check)
    checks.extend(_llm_marginal_lift_checks(spec=spec, frame=frame, root=base, variant=full))

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
    checks.append(_research_brief_check(spec_path, base))
    checks.append(_overfit_risk_check(spec_path, base))
    checks.append(_regime_performance_check(spec_path, base))
    checks.append(_alpha_decay_check(spec_path, base))

    ready = all(check.status == "ok" for check in checks)
    status: PromotionStatus
    if any(check.status == "blocked" for check in checks):
        status = "blocked"
    elif any(check.status == "warning" for check in checks):
        status = "warning"
    else:
        status = "ok"
    five_pass_checks = _build_pass_summary(spec, ready, checks, base)
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
        **_promotion_pass_fields(five_pass_checks),
        five_pass_checks=five_pass_checks,
    )


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
) -> tuple[GateResult, BacktestArtifacts | None]:
    split = max(int(len(frame) * (1 - out_of_sample_ratio)), 2)
    split = min(split, len(frame) - 1)
    oos_frame = frame.iloc[split:].copy()
    if len(oos_frame) < 2:
        return (
            GateResult(
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
        GateResult(
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
) -> tuple[GateResult, list[BacktestArtifacts]]:
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
            GateResult(
                name="walk_forward",
                status="blocked",
                message="No walk-forward folds could be built from the available data.",
                details={"folds": folds},
            ),
            runs,
        )
    status = "ok" if all(item["status"] == "ok" for item in fold_details) else "warning"
    return (
        GateResult(
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
) -> tuple[GateResult, list[BacktestArtifacts]]:
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
        GateResult(
            name="cost_sensitivity",
            status=status,
            message="Backtests rerun under multiple slippage assumptions.",
            details={
                "scenarios": details,
            },
        ),
        runs,
    )


def _factor_lab_check(result) -> GateResult:
    details = {
        "status": result.status,
        "report_path": str(result.report_path),
        "json_path": str(result.json_path),
        "quality_flags": result.quality_flags,
        "factor_count": len(result.factor_metrics),
    }
    if result.status == "blocked":
        return GateResult(
            name="factor_lab",
            status="blocked",
            message="Factor Lab diagnostics are blocked: " + ", ".join(result.quality_flags),
            details=details,
        )
    if result.status == "warning":
        return GateResult(
            name="factor_lab",
            status="warning",
            message="Factor Lab diagnostics produced warnings.",
            details=details,
        )
    return GateResult(
        name="factor_lab",
        status="ok",
        message="Factor Lab diagnostics passed.",
        details=details,
    )


def _execution_reality_check(full: BacktestArtifacts) -> GateResult:
    reality = full.run.execution_reality
    if reality is None:
        return GateResult(
            name="execution_reality",
            status="blocked",
            message="Execution reality metrics are missing.",
            details={},
        )
    details = reality.model_dump(mode="json")
    if reality.status == "blocked":
        return GateResult(
            name="execution_reality",
            status="blocked",
            message="Execution reality blocks promotion: " + "; ".join(reality.warnings),
            details=details,
        )
    if reality.status == "warning":
        return GateResult(
            name="execution_reality",
            status="warning",
            message="Execution reality warnings require review.",
            details=details,
        )
    return GateResult(
        name="execution_reality",
        status="ok",
        message="Execution reality diagnostics passed.",
        details=details,
    )


def _alternative_data_check(result) -> GateResult:
    details = {
        "status": result.status,
        "report_path": str(result.report_path),
        "json_path": str(result.json_path),
        "warnings": result.warnings,
        "factor_count": len(result.rows),
    }
    if result.status == "blocked":
        return GateResult(
            name="alternative_data",
            status="blocked",
            message="Alternative data quality blocks promotion: " + ", ".join(result.warnings),
            details=details,
        )
    if result.status == "warning":
        return GateResult(
            name="alternative_data",
            status="warning",
            message="Alternative data quality produced warnings.",
            details=details,
        )
    return GateResult(
        name="alternative_data",
        status="ok",
        message="Alternative data quality passed or no alternative data is used.",
        details=details,
    )


def _harness_artifacts_promotion_check(spec: StrategySpec, root: Path) -> GateResult:
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
        return GateResult(
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
        return GateResult(
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
    return GateResult(
        name="harness_artifacts",
        status="ok",
        message=f"All {len(required)} harness artifacts present for domains {active}.",
        details={"risk_domains": active, "required_artifacts": required},
    )


def _research_design_check(spec: StrategySpec) -> GateResult:
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
        return GateResult(
            name="research_design",
            status="warning",
            message="Research design is incomplete: " + ", ".join(missing),
            details={"missing": missing, "source": source},
        )
    return GateResult(
        name="research_design",
        status="ok",
        message="Research design defines parameter space, objective, budget, and validation plan.",
        details={"source": source},
    )


def _research_brief_check(spec_path: Path, root: Path) -> GateResult:
    result = validate_research_brief(spec_path, root, require_for_optimization=False)
    details = {
        "path": str(result.path),
        "blocked": result.blocked,
        "warnings": result.warnings,
    }
    if result.blocked:
        return GateResult(
            name="research_brief",
            status="blocked",
            message="Research brief is missing, stale, or incomplete.",
            details=details,
        )
    if result.warnings:
        return GateResult(
            name="research_brief",
            status="warning",
            message="Research brief has warnings.",
            details=details,
        )
    return GateResult(
        name="research_brief",
        status="ok",
        message="Research brief is valid and bound to the current spec hash.",
        details=details,
    )


def _overfit_risk_check(spec_path: Path, root: Path) -> GateResult:
    result = build_overfit_risk_report(spec_path, root)
    details = {
        "trial_count": result.trial_count,
        "dsr_proxy": result.dsr_proxy,
        "pbo_proxy": result.pbo_proxy,
        "blockers": result.blockers,
        "warnings": result.warnings,
        "json_path": str(result.json_path) if result.json_path else None,
        "report_path": str(result.report_path) if result.report_path else None,
    }
    if result.status == "blocked":
        return GateResult(
            name="overfit_risk",
            status="blocked",
            message="Multiple-testing overfit risk blocks promotion: " + ", ".join(result.blockers),
            details=details,
        )
    if result.status == "warning":
        return GateResult(
            name="overfit_risk",
            status="warning",
            message="Multiple-testing overfit risk warnings: " + ", ".join(result.warnings),
            details=details,
        )
    if result.status == "not_applicable":
        return GateResult(
            name="overfit_risk",
            status="ok",
            message="No large parameter sweep requiring overfit-risk review was found.",
            details=details,
        )
    return GateResult(
        name="overfit_risk",
        status="ok",
        message="Multiple-testing overfit risk proxy passed.",
        details=details,
    )


def _regime_performance_check(spec_path: Path, root: Path) -> GateResult:
    result = build_regime_performance_report(spec_path, root)
    details = {
        "status": result.status,
        "min_regime_sharpe": result.min_regime_sharpe,
        "min_regime_return_pct": result.min_regime_return_pct,
        "blockers": result.blockers,
        "warnings": result.warnings,
        "json_path": str(result.json_path) if result.json_path else None,
        "report_path": str(result.report_path) if result.report_path else None,
    }
    if result.status == "blocked":
        return GateResult(
            name="regime_performance",
            status="blocked",
            message="Regime performance blocks promotion: " + ", ".join(result.blockers),
            details=details,
        )
    if result.status in {"warning", "not_applicable"}:
        return GateResult(
            name="regime_performance",
            status="warning",
            message="Regime performance needs review: "
            + ", ".join(result.warnings or [result.status]),
            details=details,
        )
    return GateResult(
        name="regime_performance",
        status="ok",
        message="Regime performance did not find a blocking worst-regime failure.",
        details=details,
    )


def _alpha_decay_check(spec_path: Path, root: Path) -> GateResult:
    result = build_alpha_decay_report(spec_path, root)
    details = {
        "status": result.status,
        "slope": result.slope,
        "recent_sharpe": result.recent_sharpe,
        "old_sharpe": result.old_sharpe,
        "pnl_concentration_old": result.pnl_concentration_old,
        "alpha_stale": result.alpha_stale,
        "blockers": result.blockers,
        "warnings": result.warnings,
        "json_path": str(result.json_path) if result.json_path else None,
        "report_path": str(result.report_path) if result.report_path else None,
    }
    if result.status == "blocked":
        return GateResult(
            name="alpha_decay",
            status="blocked",
            message="Alpha decay blocks promotion: " + ", ".join(result.blockers),
            details=details,
        )
    if result.status in {"warning", "not_applicable"}:
        return GateResult(
            name="alpha_decay",
            status="warning",
            message="Alpha decay needs review: " + ", ".join(result.warnings or [result.status]),
            details=details,
        )
    return GateResult(
        name="alpha_decay",
        status="ok",
        message="Alpha decay proxy did not find stale-edge evidence.",
        details=details,
    )


def _universe_audit_promotion_check(spec: StrategySpec, root: Path) -> GateResult:
    result = assess_universe_audit(spec, root)
    findings = [
        {
            "code": item.code,
            "severity": item.severity,
            "message": item.message,
            "evidence": item.evidence,
        }
        for item in result.findings
    ]
    details = {
        "status": result.status,
        "json_path": _relpath(result.json_path, root),
        "report_path": _relpath(result.report_path, root),
        "findings": findings,
    }
    if result.status == "blocked":
        return GateResult(
            name="universe_audit",
            status="blocked",
            message=(
                "Universe audit blocks promotion because PIT membership or "
                "survivorship controls are incomplete."
            ),
            details=details,
        )
    if result.status == "warning":
        return GateResult(
            name="universe_audit",
            status="warning",
            message="Universe audit produced warnings that should be resolved before paper.",
            details=details,
        )
    return GateResult(
        name="universe_audit",
        status="ok",
        message="Universe audit passed.",
        details=details,
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
) -> tuple[GateResult, list[dict[str, object]]]:
    comparisons_root = root / "reports" / "data" / "comparisons"
    rows: list[dict[str, object]] = []
    if not comparisons_root.exists():
        return (
            GateResult(
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
            GateResult(
                name="data_comparison",
                status="warning",
                message="No matching data comparison report found for this strategy.",
                details={},
            ),
            rows,
        )
    return (
        GateResult(
            name="data_comparison",
            status="ok",
            message="Matching data comparison reports are available.",
            details={"comparisons": rows},
        ),
        rows,
    )


def _strict_data_check(spec: StrategySpec, artifacts: BacktestArtifacts) -> GateResult:
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
        return GateResult(
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
    return GateResult(
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


def _feature_packet_check(spec: StrategySpec, root: Path) -> GateResult:
    inspected: list[dict[str, object]] = []
    missing_or_incomplete: list[str] = []
    stability_warnings: list[str] = []
    for name, factor in spec.factors.items():
        if factor.source not in {"llm_feature", "feature_packet"}:
            continue
        path = feature_packet_path_for_factor(root, spec.name, name, factor)
        path_value = feature_packet_path_label(spec.name, name, factor)
        if path is None or path_value is None:
            missing_or_incomplete.append(f"{name}: missing packet path")
            inspected.append({"factor": name, "status": "missing"})
            continue
        inspection = inspect_feature_packet(path, factor.field)
        inspected.append(
            {
                "factor": name,
                "path": path_value,
                "field": factor.field,
                "status": inspection.point_in_time_status,
                "warnings": inspection.replay_warnings,
                "evidence_count": inspection.evidence_count,
                "missing_evidence_count": inspection.missing_evidence_count,
                "prompt_hashes": inspection.prompt_hashes,
                "missing_prompt_hash_count": inspection.missing_prompt_hash_count,
            }
        )
        if not inspection.exists or inspection.point_in_time_status != "complete":
            warning_text = "; ".join(inspection.replay_warnings[:3]) or "not PIT complete"
            missing_or_incomplete.append(
                f"{name}: {inspection.point_in_time_status} at {path_value}: {warning_text}"
            )
        elif inspection.missing_evidence_count:
            missing_or_incomplete.append(
                f"{name}: {inspection.missing_evidence_count} packet row(s) at "
                f"{path_value} lack marginal-lift evidence"
            )
        if len(inspection.prompt_hashes) > 1:
            stability_warnings.append(
                f"{name}: multiple prompt_hash values in {path_value}: "
                + ", ".join(inspection.prompt_hashes[:5])
            )
        if inspection.missing_prompt_hash_count:
            stability_warnings.append(
                f"{name}: {inspection.missing_prompt_hash_count} packet row(s) at "
                f"{path_value} missing prompt_hash"
            )
    if missing_or_incomplete:
        return GateResult(
            name="feature_packets",
            status="blocked",
            message="Promotion requires PIT-complete feature packets: "
            + "; ".join(missing_or_incomplete),
            details={"inspected": inspected},
        )
    if stability_warnings:
        return GateResult(
            name="feature_packets",
            status="warning",
            message="Feature packets are PIT-complete but prompt/version stability needs review: "
            + "; ".join(stability_warnings),
            details={"inspected": inspected, "prompt_version_warnings": stability_warnings},
        )
    return GateResult(
        name="feature_packets",
        status="ok",
        message="Feature packet factors are absent or PIT-complete.",
        details={"inspected": inspected},
    )


def _llm_marginal_lift_checks(
    *,
    spec: StrategySpec,
    frame,
    root: Path,
    variant: BacktestArtifacts,
) -> list[GateResult]:
    llm_factors = sorted(
        name for name, factor in spec.factors.items() if factor.source == "llm_feature"
    )
    if not llm_factors:
        return []
    baseline_spec = copy.deepcopy(spec)
    for name in llm_factors:
        baseline_spec.factors[name].default = 0.0
        baseline_spec.factors[name].path = "__missing_llm_baseline_packet__.jsonl"
    baseline = backtest_frame(
        baseline_spec,
        frame,
        root=root,
        run_id_value=f"promotion-{spec.name}-quant-baseline",
    )
    missing_spec = copy.deepcopy(spec)
    for name in llm_factors:
        missing_spec.factors[name].path = "__missing_llm_modality_packet__.jsonl"
    missing = backtest_frame(
        missing_spec,
        frame,
        root=root,
        run_id_value=f"promotion-{spec.name}-missing-modality",
    )
    baseline_sharpe = _metric_value(baseline.run.sharpe_ratio)
    variant_sharpe = _metric_value(variant.run.sharpe_ratio)
    lift = variant_sharpe - baseline_sharpe
    jaccard = _signal_jaccard(baseline.signals, variant.signals)
    checks = [
        GateResult(
            name="llm_quant_baseline",
            status="ok",
            message="Pure quant baseline was replayed with LLM factors neutralized.",
            details={"sharpe": baseline.run.sharpe_ratio, "signals": baseline.run.signals},
        ),
        GateResult(
            name="llm_variant",
            status="ok",
            message="LLM-factor variant was replayed from saved PIT packets.",
            details={"sharpe": variant.run.sharpe_ratio, "signals": variant.run.signals},
        ),
        GateResult(
            name="llm_missing_modality_robustness",
            status="ok",
            message="Missing-modality fallback replay completed without live LLM calls.",
            details={"sharpe": missing.run.sharpe_ratio, "signals": missing.run.signals},
        ),
        GateResult(
            name="llm_marginal_lift",
            status="ok" if lift > 0 else "blocked",
            message=f"LLM variant Sharpe lift versus quant baseline is {lift:.3f}.",
            details={
                "baseline_sharpe": baseline.run.sharpe_ratio,
                "variant_sharpe": variant.run.sharpe_ratio,
                "missing_modality_sharpe": missing.run.sharpe_ratio,
                "lift": lift,
            },
        ),
        GateResult(
            name="llm_independence",
            status="ok" if jaccard < 0.95 else "warning",
            message=f"LLM variant signal Jaccard versus baseline is {jaccard:.3f}.",
            details={"signal_jaccard": jaccard},
        ),
    ]
    write_json(
        root / "reports" / "research" / f"{spec.name}-llm-marginal-evidence.json",
        {
            "strategy_name": spec.name,
            "llm_factors": llm_factors,
            "baseline": checks[0].details,
            "variant": checks[1].details,
            "missing_modality": checks[2].details,
            "marginal_lift": checks[3].details,
            "independence": checks[4].details,
        },
    )
    return checks


def _metric_value(value: float | None) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _signal_jaccard(left: list[object], right: list[object]) -> float:
    left_keys = {_signal_key(signal) for signal in left}
    right_keys = {_signal_key(signal) for signal in right}
    if not left_keys and not right_keys:
        return 1.0
    return len(left_keys & right_keys) / max(len(left_keys | right_keys), 1)


def _signal_key(signal: object) -> str:
    return (
        f"{getattr(signal, 'symbol', '')}:"
        f"{getattr(signal, 'timestamp', '')}:"
        f"{getattr(signal, 'action', '')}"
    )


def _benchmark_family_check(
    spec: StrategySpec,
    full: BacktestArtifacts,
) -> tuple[GateResult, dict[str, object]]:
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
            GateResult(
                name="benchmark_family",
                status="warning",
                message="Promotion benchmark family is incomplete: " + ", ".join(missing),
                details=family,
            ),
            family,
        )
    return (
        GateResult(
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
    checks: list[GateResult],
    full: BacktestArtifacts,
    oos: BacktestArtifacts | None,
    walk_forward_runs: list[BacktestArtifacts],
    cost_runs: list[BacktestArtifacts],
    comparison_rows: list[dict[str, object]],
    benchmark_family: dict[str, object],
    data_profile: dict[str, object],
    manifest: dict[str, object],
    five_pass_checks: PassSummary,
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
        **_promotion_pass_fields(five_pass_checks),
        "five_pass_checks": dict(five_pass_checks),
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
    checks: list[GateResult],
    full: BacktestArtifacts,
    oos: BacktestArtifacts | None,
    walk_forward_runs: list[BacktestArtifacts],
    cost_runs: list[BacktestArtifacts],
    comparison_rows: list[dict[str, object]],
    benchmark_family: dict[str, object],
    json_path: Path,
    data_profile: dict[str, object],
    manifest: dict[str, object],
    five_pass_checks: PassSummary,
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
        + ("yes" if _pass_value(five_pass_checks, "paper_ready_pass") == "pass" else "no"),
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
    checks: list[GateResult],
    benchmark_family: dict[str, object],
) -> dict[str, object]:
    blocked = {check.name for check in checks if check.status == "blocked"}
    warning = {check.name for check in checks if check.status == "warning"}
    llm_related = bool(
        spec.llm_review.enabled
        or _feature_packet_paths(spec)
        or any(factor.source == "llm_feature" for factor in spec.factors.values())
    )
    return {
        "workflow_pass": "in_sample" not in blocked,
        "research_pass": not blocked,
        "llm_contribution_pass": (
            None
            if not llm_related
            else "feature_packets" not in blocked and "llm_marginal_lift" not in blocked
        ),
        "paper_ready_pass": ready,
        "blocked_checks": sorted(blocked),
        "warning_checks": sorted(warning),
        "benchmark_family_complete": bool(benchmark_family.get("complete", False)),
    }


def _build_pass_summary(
    spec: StrategySpec,
    ready: bool,
    checks: list[GateResult],
    root: Path,
) -> PassSummary:
    by_name = {check.name: check for check in checks}
    blocked = {check.name for check in checks if check.status == "blocked"}
    warning = {check.name for check in checks if check.status == "warning"}

    workflow_failures = [
        name
        for name in ["in_sample", "feature_packets"]
        if name in blocked or by_name.get(name, GateResult(name, "ok", "")).status == "blocked"
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
        "research_brief",
        "overfit_risk",
        "regime_performance",
        "alpha_decay",
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

    llm_related = bool(
        spec.llm_review.enabled
        or _feature_packet_paths(spec)
        or any(factor.source == "llm_feature" for factor in spec.factors.values())
    )
    if not llm_related:
        llm_contribution_pass: FivePassStatus = "not_applicable"
        llm_reason = "strategy does not use LLM review or LLM/feature packet factors"
    elif "feature_packets" in blocked or "llm_marginal_lift" in blocked:
        llm_contribution_pass = "fail"
        llm_reason = "LLM factors are missing PIT-complete or marginal-lift evidence"
    elif any(factor.source == "llm_feature" for factor in spec.factors.values()):
        llm_contribution_pass = "pass"
        llm_reason = "LLM feature marginal-lift, replay, fallback, and independence checks passed"
    else:
        llm_contribution_pass, llm_reason = _blind_test_contribution_pass(spec, root)

    paper_ready_pass: FivePassStatus = "pass" if ready else "fail"
    paper_reason = (
        "all promotion checks are ok"
        if ready
        else "blocked checks: " + ", ".join(sorted(blocked or warning))
    )

    expression_safety_pass, code_reason = _expression_safety_pass(spec)

    return _pass_summary(
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


def _promotion_pass_fields(five_pass_checks: PassSummary) -> dict[str, object]:
    return {
        "workflow_pass": _pass_value(five_pass_checks, "workflow_pass") == "pass",
        "research_pass": _pass_value(five_pass_checks, "research_pass") == "pass",
        "llm_contribution_pass": (
            None
            if _pass_value(five_pass_checks, "llm_contribution_pass") == "not_applicable"
            else _pass_value(five_pass_checks, "llm_contribution_pass") == "pass"
        ),
        "paper_ready_pass": _pass_value(five_pass_checks, "paper_ready_pass") == "pass",
        "pass_reasons": {
            "workflow": _pass_reason(five_pass_checks, "workflow_reason"),
            "research": _pass_reason(five_pass_checks, "research_reason"),
            "llm_contribution": _pass_reason(five_pass_checks, "llm_contribution_reason"),
            "paper_ready": _pass_reason(five_pass_checks, "paper_ready_reason"),
            "expression_safety": _pass_reason(five_pass_checks, "expression_safety_reason"),
        },
    }


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


def _five_pass_markdown_rows(five_pass_checks: PassSummary) -> list[str]:
    rows = [
        (
            "workflow_pass",
            _pass_value(five_pass_checks, "workflow_pass"),
            _pass_reason(five_pass_checks, "workflow_reason"),
        ),
        (
            "research_pass",
            _pass_value(five_pass_checks, "research_pass"),
            _pass_reason(five_pass_checks, "research_reason"),
        ),
        (
            "llm_contribution_pass",
            _pass_value(five_pass_checks, "llm_contribution_pass"),
            _pass_reason(five_pass_checks, "llm_contribution_reason"),
        ),
        (
            "paper_ready_pass",
            _pass_value(five_pass_checks, "paper_ready_pass"),
            _pass_reason(five_pass_checks, "paper_ready_reason"),
        ),
        (
            "expression_safety_pass",
            _pass_value(five_pass_checks, "expression_safety_pass"),
            _pass_reason(five_pass_checks, "expression_safety_reason"),
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
