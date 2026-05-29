from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_readiness import assess_paper_strategy_readiness_for_spec
from open_composer.research.contracts import build_research_contract
from open_composer.research.control import ResearchControlResult, update_research_control
from open_composer.research.metadata import workspace_relative_path
from open_composer.research.promotion import build_promotion_report
from open_composer.research.research_brief import validate_research_brief
from open_composer.research.research_report import (
    StrategyResearchReportResult,
    build_strategy_research_report,
)
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

LIGHTWEIGHT_EVIDENCE_PORTFOLIO_MODES = {
    "adaptive_intraday_internal_router",
    "hybrid_adaptive_router",
    "beta_exposure_router",
}


@dataclass(frozen=True)
class StrategyEvidenceResult:
    strategy_name: str
    status: str
    research_report: StrategyResearchReportResult
    control: ResearchControlResult


def build_strategy_evidence(
    spec_path: Path,
    root: Path | None = None,
) -> StrategyEvidenceResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    if _has_optimized_research_design(spec):
        brief = validate_research_brief(spec_path, base, require_for_optimization=True)
        if not brief.ok:
            msg = "research brief validation failed: " + ", ".join(brief.blocked)
            raise ValueError(msg)
    if spec.portfolio.mode in LIGHTWEIGHT_EVIDENCE_PORTFOLIO_MODES:
        research_report = build_lightweight_router_evidence_report(spec_path, base)
    else:
        research_report = build_strategy_research_report(spec_path, base)
    control = update_research_control(spec_path, base)
    return StrategyEvidenceResult(
        strategy_name=research_report.strategy_name,
        status=research_report.status,
        research_report=research_report,
        control=control,
    )


def _has_optimized_research_design(spec) -> bool:
    if spec.research_design and spec.research_design.parameter_space:
        return True
    notes = spec.notes.model_dump(mode="json")
    legacy = notes.get("research_design") if isinstance(notes, dict) else None
    return isinstance(legacy, dict) and bool(legacy.get("parameter_ranges"))


def build_lightweight_router_evidence_report(
    spec_path: Path,
    root: Path | None = None,
) -> StrategyResearchReportResult:
    """Build evidence for router specs without running generic single-symbol research.

    Router families already produce dedicated artifacts: router research, target
    weights, data evidence, cost stress, promotion, and harness verification. The
    generic research report path runs a reference backtest and single-symbol
    Factor Lab, which is both slow and misleading for intraday/portfolio routers.
    """

    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    contract = build_research_contract(spec_path, base)
    contract_path = base / "reports" / "research" / f"{spec.name}-research-contract.json"
    write_json(contract_path, contract)

    promotion = build_promotion_report(spec_path, base)
    paper = assess_paper_strategy_readiness_for_spec(spec, base, spec_path=spec_path)
    verify = _read_json(base / "reports" / "harness" / "verify" / f"{spec.name}.json")
    router_artifacts = _router_artifacts(base, spec.name, spec.portfolio.mode)
    checklist = _router_checklist(
        promotion_status=promotion.status,
        promotion_ready=promotion.ready,
        paper_status=paper.status,
        verify=verify,
        artifacts=router_artifacts,
    )
    status = _report_status(checklist)
    blocked_items = [item["name"] for item in checklist if item["status"] == "blocked"]
    warning_items = [item["name"] for item in checklist if item["status"] == "warning"]

    report_path = base / "reports" / "research" / f"{spec.name}-research-report.md"
    json_path = base / "reports" / "research" / f"{spec.name}-research-report.json"
    payload = {
        "schema_version": "1",
        "strategy_name": spec.name,
        "status": status,
        "kind": "router_research_report",
        "generated_at": datetime.now(UTC).isoformat(),
        "contract_path": workspace_relative_path(contract_path, base),
        "source_spec_path": workspace_relative_path(spec_path, base),
        "spec_hash": strategy_content_hash(spec),
        "portfolio_mode": spec.portfolio.mode,
        "checklist": checklist,
        "blocked_items": blocked_items,
        "warning_items": warning_items,
        "promotion": {
            "status": promotion.status,
            "ready": promotion.ready,
            "research_pass": promotion.research_pass,
            "workflow_pass": promotion.workflow_pass,
            "llm_contribution_pass": promotion.llm_contribution_pass,
            "paper_ready_pass": promotion.paper_ready_pass,
            "report_path": promotion.report_path,
            "json_path": promotion.json_path,
        },
        "paper_readiness": paper.model_dump(mode="json"),
        "harness_verify": verify,
        "router_artifacts": router_artifacts,
        "notes": [
            (
                "Router evidence uses dedicated router artifacts instead of generic "
                "single-symbol backtests."
            ),
            "Paper readiness remains separate from workflow and research pass status.",
        ],
    }
    write_json(json_path, payload)
    _write_lightweight_router_markdown(report_path, payload)
    return StrategyResearchReportResult(
        strategy_name=spec.name,
        status=status,
        report_path=report_path,
        json_path=json_path,
        contract_path=contract_path,
    )


def _router_checklist(
    *,
    promotion_status: str,
    promotion_ready: bool,
    paper_status: str,
    verify: dict[str, Any],
    artifacts: dict[str, str | None],
) -> list[dict[str, Any]]:
    verify_status = str(verify.get("overall") or verify.get("status") or "missing")
    return [
        {
            "name": "promotion",
            "status": promotion_status,
            "message": f"router promotion status is {promotion_status}",
        },
        {
            "name": "paper_readiness",
            "status": "ok" if promotion_ready and paper_status == "ok" else "blocked",
            "message": f"paper readiness status is {paper_status}",
        },
        {
            "name": "harness_verify",
            "status": "ok" if verify_status == "ok" else "blocked",
            "message": f"harness verify status is {verify_status}",
        },
        {
            "name": "router_artifacts",
            "status": "ok" if all(artifacts.values()) else "warning",
            "message": "dedicated router artifact paths were collected",
            "details": artifacts,
        },
    ]


def _report_status(checklist: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status")) for item in checklist}
    if "blocked" in statuses:
        return "blocked"
    if "warning" in statuses:
        return "warning"
    return "ok"


def _router_artifacts(
    base: Path,
    strategy_name: str,
    portfolio_mode: str,
) -> dict[str, str | None]:
    research_paths = {
        "adaptive_intraday_internal_router": {
            "adaptive_router_research": base
            / "reports"
            / "research"
            / f"{strategy_name}-adaptive-intraday-router.json"
        },
        "hybrid_adaptive_router": {
            "hybrid_router_research": base
            / "reports"
            / "research"
            / f"{strategy_name}-hybrid-adaptive-router.json"
        },
        "beta_exposure_router": {
            "beta_router_research": base
            / "reports"
            / "research"
            / f"{strategy_name}-beta-exposure-router.json"
        },
    }
    candidates = {
        **research_paths.get(portfolio_mode, {}),
        "target_weights": base / "reports" / "execution" / f"{strategy_name}-target-weights.json",
        "router_data_evidence": base
        / "reports"
        / "research"
        / f"{strategy_name}-router-data-evidence.json",
        "router_cost_stress": base
        / "reports"
        / "research"
        / f"{strategy_name}-router-cost-stress.json",
    }
    return {
        name: workspace_relative_path(path, base) if path.exists() else None
        for name, path in candidates.items()
    }


def _write_lightweight_router_markdown(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    lines = [
        f"# Router Research Report: {payload['strategy_name']}",
        "",
        f"- Status: `{payload['status']}`",
        f"- Portfolio mode: `{payload['portfolio_mode']}`",
        f"- Promotion: `{payload['promotion']['status']}`",
        f"- Paper ready: `{payload['promotion']['paper_ready_pass']}`",
        "",
        "## Checks",
        "",
    ]
    for item in payload["checklist"]:
        lines.append(f"- `{item['name']}`: `{item['status']}` - {item['message']}")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            (
                "- Router strategies use dedicated router artifacts; generic "
                "single-symbol backtests are skipped."
            ),
            "- Workflow, research, LLM contribution, and paper readiness remain separate gates.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
