from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from open_composer.capabilities import evaluate_capabilities
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import run_backtest
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_readiness import assess_paper_strategy_readiness_for_spec
from open_composer.research.alt_data_quality import build_alternative_data_quality_report
from open_composer.research.contracts import build_research_contract
from open_composer.research.factor_lab import run_factor_lab
from open_composer.research.promotion import build_promotion_report
from open_composer.storage import write_json
from open_composer.strategy_capabilities import assess_strategy_capabilities


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
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    contract = build_research_contract(spec_path, base)
    contract_path = base / "reports" / "research" / f"{spec.name}-research-contract.json"
    write_json(contract_path, contract)

    capability_report = assess_strategy_capabilities(spec_path)
    capability_evaluation = evaluate_capabilities(base)
    backtest = run_backtest(spec_path, root=base)
    factor_lab = run_factor_lab(spec_path, base)
    alt_data = build_alternative_data_quality_report(spec_path, base)
    promotion = build_promotion_report(spec_path, base)
    paper_readiness = assess_paper_strategy_readiness_for_spec(spec, base, spec_path=spec_path)

    checklist = _research_checklist(
        backtest=backtest.run.model_dump(mode="json"),
        factor_status=factor_lab.status,
        alt_data_status=alt_data.status,
        promotion_status=promotion.status,
        paper_status=paper_readiness.status,
    )
    status = "ok" if all(item["status"] == "ok" for item in checklist) else "blocked"
    report_path = base / "reports" / "research" / f"{spec.name}-research-report.md"
    json_path = base / "reports" / "research" / f"{spec.name}-research-report.json"
    payload = {
        "strategy_name": spec.name,
        "status": status,
        "contract_path": _relpath(contract_path, base),
        "source_spec_path": _relpath(spec_path, base),
        "checklist": checklist,
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
    write_json(json_path, payload)
    _write_markdown(report_path, payload)
    return StrategyResearchReportResult(
        strategy_name=spec.name,
        status=status,
        report_path=report_path,
        json_path=json_path,
        contract_path=contract_path,
    )


def _research_checklist(
    *,
    backtest: dict[str, Any],
    factor_status: str,
    alt_data_status: str,
    promotion_status: str,
    paper_status: str,
) -> list[dict[str, object]]:
    execution_reality = backtest.get("execution_reality") or {}
    data_sanity = backtest.get("data_sanity") or {}
    return [
        {
            "name": "leakage_defaults",
            "status": "ok",
            "evidence": "bar-close signals, next-bar-open fills, visible_at feature replay",
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


def _write_markdown(path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Strategy Research Report: {payload['strategy_name']}",
        "",
        f"- Status: `{payload['status']}`",
        f"- Contract: `{payload['contract_path']}`",
        f"- Source spec: `{payload['source_spec_path']}`",
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
        return str(path.relative_to(base))
    except ValueError:
        return str(path)
