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
    *,
    refresh_data: bool = False,
) -> StrategyEvidenceResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    if _has_optimized_research_design(spec):
        brief = validate_research_brief(spec_path, base, require_for_optimization=True)
        if not brief.ok:
            msg = "research brief validation failed: " + ", ".join(brief.blocked)
            raise ValueError(msg)
    if spec.portfolio.mode in LIGHTWEIGHT_EVIDENCE_PORTFOLIO_MODES:
        research_report = build_lightweight_router_evidence_report(
            spec_path,
            base,
            refresh_data=refresh_data,
        )
    else:
        research_report = build_strategy_research_report(spec_path, base, refresh_data=refresh_data)
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
    *,
    refresh_data: bool = False,
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

    promotion = build_promotion_report(spec_path, base, refresh_data=refresh_data)
    promotion_payload = _read_json(Path(promotion.json_path))
    paper = assess_paper_strategy_readiness_for_spec(spec, base, spec_path=spec_path)
    verify = _read_json(base / "reports" / "harness" / "verify" / f"{spec.name}.json")
    router_artifacts = _router_artifacts(base, spec.name, spec.portfolio.mode)
    checklist = _router_checklist(
        promotion_status=promotion.status,
        promotion_ready=promotion.ready,
        promotion_payload=promotion_payload,
        paper_status=paper.status,
        verify=verify,
        artifacts=router_artifacts,
    )
    status = _report_status(checklist)
    blocked_items = _check_items(checklist, status="blocked")
    warning_items = _check_items(checklist, status="warning")

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
            "blocked_checks": _list(
                _dict(promotion_payload.get("gate_summary")).get("blocked_checks")
            ),
            "warning_checks": _list(
                _dict(promotion_payload.get("gate_summary")).get("warning_checks")
            ),
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
    promotion_payload: dict[str, Any],
    paper_status: str,
    verify: dict[str, Any],
    artifacts: dict[str, str | None],
) -> list[dict[str, Any]]:
    verify_status = str(verify.get("overall") or verify.get("status") or "missing")
    gate_summary = _dict(promotion_payload.get("gate_summary"))
    promotion_blocked = [str(item) for item in _list(gate_summary.get("blocked_checks"))]
    promotion_warnings = [str(item) for item in _list(gate_summary.get("warning_checks"))]
    blocked_details = _promotion_check_details(promotion_payload, status="blocked")
    warning_details = _promotion_check_details(promotion_payload, status="warning")
    promotion_message = f"router promotion status is {promotion_status}"
    if promotion_blocked:
        promotion_message = "router promotion blocked by: " + ", ".join(promotion_blocked)
    return [
        {
            "name": "promotion",
            "status": promotion_status,
            "message": promotion_message,
            "details": {
                "blocked_checks": promotion_blocked,
                "warning_checks": promotion_warnings,
                "blocked_check_details": blocked_details,
                "warning_check_details": warning_details,
                "next_actions": _promotion_next_actions(blocked_details),
            },
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


def _check_items(checklist: list[dict[str, Any]], *, status: str) -> list[str]:
    items: list[str] = []
    for item in checklist:
        if item.get("status") != status:
            continue
        name = str(item.get("name") or "unknown")
        details = _dict(item.get("details"))
        checks = (
            details.get("blocked_checks") if status == "blocked" else details.get("warning_checks")
        )
        nested = [str(value) for value in _list(checks)]
        if nested:
            items.extend(f"{name}:{value}" for value in nested)
        else:
            items.append(name)
    return _dedupe(items)


def _promotion_check_details(
    promotion_payload: dict[str, Any],
    *,
    status: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for check in _list(promotion_payload.get("checks")):
        if not isinstance(check, dict) or check.get("status") != status:
            continue
        details = _dict(check.get("details"))
        rows.append(
            {
                "name": check.get("name"),
                "message": check.get("message"),
                "blocked_reasons": _list(details.get("blocked_reasons")),
                "warnings": _list(details.get("warnings")),
                "next_actions": _list(details.get("next_actions")),
            }
        )
    return rows


def _promotion_next_actions(blocked_details: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for detail in blocked_details:
        actions.extend(str(item) for item in _list(detail.get("next_actions")))
    return _dedupe(actions)[:5]


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


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
