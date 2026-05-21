from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from open_composer.capabilities import evaluate_capabilities
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import run_backtest
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.paper_readiness import assess_paper_strategy_readiness_for_spec
from open_composer.research.alt_data_quality import build_alternative_data_quality_report
from open_composer.research.contracts import build_research_contract
from open_composer.research.factor_lab import run_factor_lab
from open_composer.research.kernel import (
    EvaluationBundle,
    GateResult,
    MetricSummary,
    ResearchArtifactWriter,
    ResearchRunIndexRecord,
    build_default_research_brief,
    search_space_from_spec,
)
from open_composer.research.kernel.gates import summarize_gates
from open_composer.research.kernel.workflow import research_run_id
from open_composer.research.promotion import build_promotion_report
from open_composer.strategy_capabilities import assess_strategy_capabilities
from open_composer.strategy_versions import strategy_content_hash


@dataclass(frozen=True)
class StrategyResearchReportResult:
    strategy_name: str
    status: str
    report_path: Path
    json_path: Path
    contract_path: Path


def build_strategy_research_report(
    spec_path: Path,
    root: Path | None = None,
) -> StrategyResearchReportResult:
    started_at = perf_counter()
    base = root or project_root()
    writer = ResearchArtifactWriter(base)
    spec = load_strategy_spec(spec_path)
    contract = build_research_contract(spec_path, base)
    contract_path = base / "reports" / "research" / f"{spec.name}-research-contract.json"
    writer.json(contract_path, contract)

    capability_report = assess_strategy_capabilities(spec_path)
    capability_evaluation = evaluate_capabilities(base)
    backtest = run_backtest(spec_path, root=base)
    factor_lab = run_factor_lab(spec_path, base)
    alt_data = build_alternative_data_quality_report(spec_path, base)
    promotion = build_promotion_report(spec_path, base)
    paper_readiness = assess_paper_strategy_readiness_for_spec(spec, base, spec_path=spec_path)
    promotion_json_path = _relpath(Path(promotion.json_path), base) if promotion.json_path else None
    paper_readiness_json_path = (
        _relpath(Path(paper_readiness.report_json_path), base)
        if paper_readiness.report_json_path
        else None
    )

    checklist = _research_checklist(
        spec=spec,
        backtest=backtest.run.model_dump(mode="json"),
        factor_status=factor_lab.status,
        alt_data_status=alt_data.status,
        promotion_status=promotion.status,
        paper_status=paper_readiness.status,
    )
    status = "ok" if all(item["status"] == "ok" for item in checklist) else "blocked"
    blocked_items = [str(item["name"]) for item in checklist if item["status"] == "blocked"]
    warning_items = [str(item["name"]) for item in checklist if item["status"] == "warning"]
    report_path = base / "reports" / "research" / f"{spec.name}-research-report.md"
    json_path = base / "reports" / "research" / f"{spec.name}-research-report.json"
    research_brief = build_default_research_brief(spec)
    search_space = search_space_from_spec(spec)
    gate_summary = summarize_gates(
        [
            GateResult(
                name=str(item["name"]),
                status=str(item["status"]),  # type: ignore[arg-type]
                message=str(item["evidence"]),
                evidence=item["evidence"],
            )
            for item in checklist
        ]
    )
    evaluation_bundle = _evaluation_bundle(
        spec.name,
        status,
        backtest=backtest.run.model_dump(mode="json"),
        factor_status=factor_lab.status,
        factor_path=_relpath(factor_lab.json_path, base),
        alt_data_status=alt_data.status,
        alt_data_path=_relpath(alt_data.json_path, base),
        promotion_status=promotion.status,
        promotion_path=promotion_json_path,
        paper_status=paper_readiness.status,
        paper_path=paper_readiness_json_path,
        blocked_items=blocked_items,
        warning_items=warning_items,
    )
    runtime_seconds = round(perf_counter() - started_at, 6)
    index_record = ResearchRunIndexRecord(
        run_id=research_run_id(spec.name, spec),
        strategy_name=spec.name,
        source_spec_path=_relpath(spec_path, base),
        spec_hash=strategy_content_hash(spec),
        status=status,  # type: ignore[arg-type]
        kind="research_report",
        data_profile=backtest.run.data_sanity.model_dump(mode="json")
        if backtest.run.data_sanity
        else {},
        candidate_count=search_space.candidate_count,
        trial_count=1,
        runtime_seconds=runtime_seconds,
        gate_status=gate_summary.status,
        blocked_items=blocked_items,
        warning_items=warning_items,
        report_path=_relpath(report_path, base),
        json_path=_relpath(json_path, base),
        contract_path=_relpath(contract_path, base),
        source_artifacts={
            "backtest": _relpath(Path(backtest.run.report_path), base)
            if backtest.run.report_path
            else None,
            "factor_lab": _relpath(factor_lab.json_path, base),
            "alternative_data_quality": _relpath(alt_data.json_path, base),
            "promotion": promotion_json_path,
            "paper_readiness": paper_readiness_json_path,
        },
    )
    payload = {
        "strategy_name": spec.name,
        "status": status,
        "kind": "research_report",
        "contract_path": _relpath(contract_path, base),
        "source_spec_path": _relpath(spec_path, base),
        "spec_hash": strategy_content_hash(spec),
        "research_brief": research_brief.model_dump(mode="json"),
        "search_space": search_space.model_dump(mode="json"),
        "default_research_controls": _default_research_controls(),
        "trial_count": 1,
        "candidate_count": search_space.candidate_count,
        "runtime_seconds": runtime_seconds,
        "checklist": checklist,
        "gate_summary": gate_summary.model_dump(mode="json"),
        "evaluation_bundle": evaluation_bundle.model_dump(mode="json"),
        "research_run_index_record": index_record.model_dump(mode="json"),
        "capability_findings": [
            {
                "capability": item.capability,
                "status": item.status,
                "reasons": item.reasons,
            }
            for item in capability_report.findings
        ],
        "capability_evaluation": [item.model_dump(mode="json") for item in capability_evaluation],
        "backtest": backtest.run.model_dump(mode="json"),
        "factor_lab": {
            "status": factor_lab.status,
            "report_path": _relpath(factor_lab.report_path, base),
            "json_path": _relpath(factor_lab.json_path, base),
            "quality_flags": factor_lab.quality_flags,
        },
        "alternative_data_quality": {
            "status": alt_data.status,
            "report_path": _relpath(alt_data.report_path, base),
            "json_path": _relpath(alt_data.json_path, base),
            "warnings": alt_data.warnings,
        },
        "promotion": {
            "status": promotion.status,
            "ready": promotion.ready,
            "report_path": promotion.report_path,
            "json_path": promotion.json_path,
        },
        "paper_readiness": paper_readiness.model_dump(mode="json"),
    }
    writer.json(json_path, payload)
    writer.append_index(index_record)
    _write_markdown(report_path, payload)
    return StrategyResearchReportResult(
        strategy_name=spec.name,
        status=status,
        report_path=report_path,
        json_path=json_path,
        contract_path=contract_path,
    )


def _evaluation_bundle(
    strategy_name: str,
    status: str,
    *,
    backtest: dict[str, Any],
    factor_status: str,
    factor_path: str,
    alt_data_status: str,
    alt_data_path: str,
    promotion_status: str,
    promotion_path: str | None,
    paper_status: str,
    paper_path: str | None,
    blocked_items: list[str],
    warning_items: list[str],
) -> EvaluationBundle:
    execution_reality = backtest.get("execution_reality") or {}
    data_sanity = backtest.get("data_sanity") or {}
    execution_status = (
        execution_reality.get("status", "missing")
        if isinstance(execution_reality, dict)
        else "missing"
    )
    data_status = (
        data_sanity.get("status", "missing") if isinstance(data_sanity, dict) else "missing"
    )
    return EvaluationBundle(
        strategy_name=strategy_name,
        status=status,  # type: ignore[arg-type]
        performance=MetricSummary(
            name="performance",
            status="ok",
            metrics={
                "total_return_pct": backtest.get("total_return_pct"),
                "buy_hold_return_pct": backtest.get("buy_hold_return_pct"),
                "alpha_vs_buy_hold_pct": backtest.get("alpha_vs_buy_hold_pct"),
                "annualized_return_pct": backtest.get("annualized_return_pct"),
                "sharpe_ratio": backtest.get("sharpe_ratio"),
                "signals": backtest.get("signals"),
                "trades": backtest.get("trades"),
            },
            path=_registered_path(backtest.get("report_path")),
        ),
        factor=MetricSummary(name="factor", status=factor_status, path=factor_path),  # type: ignore[arg-type]
        execution=MetricSummary(
            name="execution",
            status=execution_status,
            metrics=execution_reality if isinstance(execution_reality, dict) else {},
            warnings=list(execution_reality.get("warnings", []))
            if isinstance(execution_reality, dict)
            else [],
        ),
        data=MetricSummary(
            name="data",
            status=data_status,
            metrics=data_sanity if isinstance(data_sanity, dict) else {},
            warnings=list(data_sanity.get("warnings", [])) if isinstance(data_sanity, dict) else [],
        ),
        alternative_data=MetricSummary(
            name="alternative_data",
            status=alt_data_status,  # type: ignore[arg-type]
            path=alt_data_path,
        ),
        promotion=MetricSummary(
            name="promotion",
            status=promotion_status,  # type: ignore[arg-type]
            path=promotion_path,
        ),
        paper_readiness=MetricSummary(
            name="paper_readiness",
            status=paper_status,  # type: ignore[arg-type]
            path=paper_path,
        ),
        blockers=blocked_items,
        warnings=warning_items,
    )


def _default_research_controls() -> dict[str, Any]:
    return {
        "leakage_controls": [
            "bar_close_signal_next_bar_open_fill_assumption",
            "feature_packets_require_visible_at_before_trading_use",
            "event_news_macro_context_filters_published_at_before_signal",
        ],
        "overfit_controls": [
            "bounded_search_space_required_for_adjustable_parameters",
            "trial_ledger_required_for_parameter_selection",
            "promotion_requires_oos_walk_forward_cost_and_benchmark_review",
        ],
        "live_gap_controls": [
            "execution_reality_required_in_research_report",
            "paper_readiness_blocks_sample_fixture_fallback_and_trial_only_evidence",
            "llm_or_alternative_data_requires_pit_packets_and_marginal_lift_evidence",
        ],
    }


def _leakage_gate(spec: StrategySpec) -> tuple[str, dict[str, object]]:
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
        evidence["warning"] = (
            "llm_review.enabled but no feature_packet factors; "
            "ensure LLM calls are replayed from PIT packets"
        )
        return "warning", evidence
    return "ok", evidence


def _research_checklist(
    *,
    spec: StrategySpec,
    backtest: dict[str, Any],
    factor_status: str,
    alt_data_status: str,
    promotion_status: str,
    paper_status: str,
) -> list[dict[str, object]]:
    execution_reality = backtest.get("execution_reality") or {}
    data_sanity = backtest.get("data_sanity") or {}
    leakage_status, leakage_evidence = _leakage_gate(spec)
    return [
        {
            "name": "leakage_defaults",
            "status": leakage_status,
            "evidence": leakage_evidence,
        },
        {
            "name": "overfit_controls",
            "status": "ok" if promotion_status == "ok" else "blocked",
            "evidence": f"promotion_status={promotion_status}",
        },
        {
            "name": "factor_diagnostics",
            "status": "ok" if factor_status == "ok" else "blocked",
            "evidence": f"factor_lab_status={factor_status}",
        },
        {
            "name": "execution_reality",
            "status": "ok" if execution_reality.get("status") == "ok" else "blocked",
            "evidence": execution_reality,
        },
        {
            "name": "data_quality",
            "status": "ok" if data_sanity.get("status") == "ok" else "blocked",
            "evidence": data_sanity,
        },
        {
            "name": "alternative_data",
            "status": "ok" if alt_data_status == "ok" else "blocked",
            "evidence": f"alt_data_status={alt_data_status}",
        },
        {
            "name": "paper_gap",
            "status": "ok" if paper_status == "ok" else "blocked",
            "evidence": f"paper_readiness_status={paper_status}",
        },
    ]


def _registered_path(value: object) -> str | None:
    return str(value) if value else None


def _write_markdown(path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Strategy Research Report: {payload['strategy_name']}",
        "",
        f"- Status: `{payload['status']}`",
        f"- Contract: `{payload['contract_path']}`",
        f"- Source spec: `{payload['source_spec_path']}`",
        f"- Research run: `{payload['research_run_index_record']['run_id']}`",
        f"- Candidate count: `{payload['candidate_count']}`",
        f"- Trial count: `{payload['trial_count']}`",
        f"- Runtime seconds: `{payload['runtime_seconds']}`",
        "",
        "## Research Brief",
        "",
        f"- Objective: {payload['research_brief']['objective']}",
        f"- Hypothesis: {payload['research_brief']['hypothesis']}",
        "",
        "## Search Space",
        "",
        f"- Family: `{payload['search_space']['family']}`",
        f"- Candidate count: `{payload['search_space']['candidate_count']}`",
        f"- Parameter ranges: `{payload['search_space']['parameter_ranges']}`",
        f"- Method variants: `{payload['search_space']['method_variants']}`",
        f"- Factor variants: `{payload['search_space']['factor_variants']}`",
        "",
        "## Checklist",
        "",
    ]
    for item in payload["checklist"]:
        lines.append(f"- `{item['name']}`: `{item['status']}` - `{item['evidence']}`")
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Backtest: `{payload['backtest'].get('report_path')}`",
            f"- Factor Lab: `{payload['factor_lab']['report_path']}`",
            f"- Alternative data quality: `{payload['alternative_data_quality']['report_path']}`",
            f"- Promotion: `{payload['promotion']['report_path']}`",
            f"- Paper readiness: `{payload['paper_readiness'].get('report_json_path')}`",
            f"- Research run index: `{payload['research_run_index_record']['json_path']}`",
            "",
            "## Capability Findings",
            "",
        ]
    )
    for item in payload["capability_findings"]:
        lines.append(f"- `{item['capability']}`: `{item['status']}` {item['reasons']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()
