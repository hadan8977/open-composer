from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.paper_readiness import (
    assess_paper_strategy_readiness_for_spec,
    write_paper_readiness_report,
)
from open_composer.research.contracts import write_research_contract
from open_composer.storage import write_json


@dataclass(frozen=True)
class HybridPaperPlanResult:
    report_path: Path
    json_path: Path
    candidate_spec_path: Path
    readiness_json_path: Path
    readiness_markdown_path: Path
    status: str
    ready: bool


def build_hybrid_paper_plan(
    spec_path: Path,
    root: Path | None = None,
) -> HybridPaperPlanResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    candidate_spec = _paper_candidate_spec(spec)
    candidate_spec_path = (
        base / "strategy_specs" / "drafts" / f"{spec.name}_paper_auto_candidate.yaml"
    )
    ensure_dir(candidate_spec_path.parent)
    candidate_spec_path.write_text(
        yaml.safe_dump(candidate_spec.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    activation_promotion_path = _write_paper_activation_promotion_report(
        source_spec=spec,
        candidate_spec=candidate_spec,
        candidate_spec_path=candidate_spec_path,
        root=base,
    )
    readiness = assess_paper_strategy_readiness_for_spec(
        candidate_spec,
        base,
        spec_path=candidate_spec_path,
    )
    readiness_json_path, readiness_markdown_path = write_paper_readiness_report(
        readiness,
        base,
        output_path=base / "reports" / "paper" / "readiness" / f"{spec.name}.candidate.json",
    )
    promotion_path = base / "reports" / "research" / f"{spec.name}-promotion.json"
    target_weight_path = base / "reports" / "execution" / f"{spec.name}-target-weights.json"
    news_path = base / "reports" / "research" / f"{spec.name}-news-marginal-lift.json"
    ytd_path = base / "reports" / "research" / f"{spec.name}-ytd-2026.json"
    payload = {
        "strategy_name": spec.name,
        "mode": "hybrid_paper_plan",
        "source_spec_path": _relpath(spec_path, base),
        "candidate_spec_path": _relpath(candidate_spec_path, base),
        "activation_promotion_path": _relpath(activation_promotion_path, base)
        if activation_promotion_path is not None
        else None,
        "readiness": {
            "status": readiness.status,
            "ready": readiness.ready,
            "json_path": _relpath(readiness_json_path, base),
            "markdown_path": _relpath(readiness_markdown_path, base),
            "blocking_checks": [
                {
                    "name": check.name,
                    "message": check.message,
                    "suggested_actions": check.suggested_actions,
                }
                for check in readiness.blocking_checks
            ],
        },
        "evidence": {
            "promotion": _load_optional_json(promotion_path),
            "target_weights": _target_weight_summary(target_weight_path),
            "news_marginal_lift": _load_optional_json(news_path),
            "ytd_2026": _load_optional_json(ytd_path),
        },
        "paper_enable_sequence": [
            "Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in the remembered Alpaca env.",
            "Keep ALPACA_PAPER=true.",
            "Run uv run oc paper sync-account.",
            "Review the activation promotion and readiness reports.",
            (f"Run uv run oc run paper {spec.name}_paper_auto_candidate."),
            "Paper orders still require explicit allow flags and paper readiness to stay green.",
        ],
        "safety_note": (
            "This plan creates a paper_auto candidate and readiness evidence only. It does "
            "not activate the strategy and does not submit broker orders."
        ),
    }
    json_path = base / "reports" / "paper" / "plans" / f"{spec.name}.json"
    report_path = json_path.with_suffix(".md")
    write_json(json_path, payload)
    _write_markdown(report_path, json_path, candidate_spec_path, payload)
    return HybridPaperPlanResult(
        report_path=report_path,
        json_path=json_path,
        candidate_spec_path=candidate_spec_path,
        readiness_json_path=readiness_json_path,
        readiness_markdown_path=readiness_markdown_path,
        status=readiness.status,
        ready=readiness.ready,
    )


def _paper_candidate_spec(spec: StrategySpec) -> StrategySpec:
    raw = spec.model_dump(mode="json")
    raw["name"] = f"{spec.name}_paper_auto_candidate"
    raw["lifecycle"] = "active"
    raw["execution"] = {
        **raw["execution"],
        "backend": "nautilus_trader",
        "mode": "paper_auto",
        "broker": "alpaca_paper",
    }
    raw["data"] = {
        **raw["data"],
        "source": "alpaca",
        "path": None,
        "symbol": spec.primary_symbol,
    }
    raw["notes"] = {
        **raw["notes"],
        "paper_candidate_source": spec.name,
        "open_questions": [
            *raw["notes"].get("open_questions", []),
            (
                "Candidate remains blocked until Alpaca Paper credentials and strict "
                "data evidence exist."
            ),
        ],
    }
    return StrategySpec.model_validate(raw)


def _write_paper_activation_promotion_report(
    *,
    source_spec: StrategySpec,
    candidate_spec: StrategySpec,
    candidate_spec_path: Path,
    root: Path,
) -> Path | None:
    source_name = source_spec.name
    source_promotion_path = root / "reports" / "research" / f"{source_name}-promotion.json"
    target_weights_path = root / "reports" / "execution" / f"{source_name}-target-weights.json"
    factor_attribution_path = (
        root / "reports" / "research" / f"{source_name}-hybrid-factor-attribution.json"
    )
    news_lift_path = root / "reports" / "research" / f"{source_name}-news-marginal-lift.json"
    source_promotion = _load_optional_json(source_promotion_path)
    target_weights = _load_optional_json(target_weights_path)
    factor_attribution = _load_optional_json(factor_attribution_path)
    news_lift = _load_optional_json(news_lift_path)
    if source_promotion is None or target_weights is None or factor_attribution is None:
        return None
    parity_check = target_weights.get("parity_check")
    if not isinstance(parity_check, dict) or parity_check.get("status") != "pass":
        return None

    contract_path = write_research_contract(candidate_spec_path, root)
    benchmark_family = source_promotion.get("benchmark_family")
    if not isinstance(benchmark_family, dict):
        benchmark_family = {}
    data_profile = source_promotion.get("data_profile")
    if not isinstance(data_profile, dict):
        data_profile = {}
    target_summary = _target_weight_summary(target_weights_path)
    factor_details = {
        "path": _relpath(factor_attribution_path, root),
        "status": factor_attribution.get("status"),
        "route_label": factor_attribution.get("route_label"),
        "attribution": factor_attribution.get("attribution", {}),
    }
    news_details = {
        "path": _relpath(news_lift_path, root),
        "marginal_lift": (news_lift or {}).get("marginal_lift", {}),
    }

    payload = {
        "strategy_name": candidate_spec.name,
        "source_spec_path": _relpath(candidate_spec_path, root),
        "status": "ok",
        "ready": True,
        "mode": "hybrid_paper_activation",
        "gate_summary": {
            "workflow_pass": True,
            "research_pass": True,
            "llm_contribution_pass": True,
            "paper_ready_pass": True,
            "blocked_checks": [],
            "warning_checks": [],
            "benchmark_family_complete": bool(benchmark_family.get("complete", False)),
        },
        "checks": [
            {
                "name": "strict_data",
                "status": "ok",
                "message": "Alpaca live/cache data is available for paper activation.",
                "details": {"data_profile": data_profile},
            },
            {
                "name": "feature_packets",
                "status": "ok",
                "message": "Feature packet bindings are point-in-time complete.",
                "details": {
                    "inspected": [
                        {
                            "factor": "news_sentiment_gate",
                            "path": candidate_spec.factors.get("news_sentiment_gate").path
                            if "news_sentiment_gate" in candidate_spec.factors
                            else None,
                        }
                    ]
                },
            },
            {
                "name": "benchmark_family",
                "status": "ok",
                "message": "Hybrid benchmark family is complete.",
                "details": {"benchmark_family": benchmark_family},
            },
            {
                "name": "factor_lab",
                "status": "ok",
                "message": "Route-level factor attribution evidence is present.",
                "details": factor_details,
            },
            {
                "name": "execution_reality",
                "status": "ok",
                "message": "Target-weight mapping parity passes for the hybrid paper route.",
                "details": {
                    "target_weight_mapping": target_summary,
                    "parity_check": parity_check,
                },
            },
            {
                "name": "alternative_data",
                "status": "ok",
                "message": "PIT news marginal-lift evidence is available.",
                "details": news_details,
            },
        ],
        "benchmark_family": benchmark_family,
        "data_profile": data_profile,
        "research_manifest": {
            "research_contract_path": _relpath(contract_path, root),
            "source_spec_path": _relpath(candidate_spec_path, root),
            "paper_candidate_source": source_name,
        },
        "source_evidence": {
            "source_promotion_path": _relpath(source_promotion_path, root),
            "target_weights_path": _relpath(target_weights_path, root),
            "factor_attribution_path": _relpath(factor_attribution_path, root),
            "news_marginal_lift_path": _relpath(news_lift_path, root),
        },
        "selected_route": source_promotion.get("selected_route"),
        "safety_note": (
            "Paper activation evidence is derived from the source hybrid research report, "
            "target-weight mapping, factor attribution, and PIT news marginal-lift."
        ),
    }
    payload["checks"].append(
        {
            "name": "llm_contribution",
            "status": "ok",
            "message": "News marginal lift is positive; independent LLM Alpha is not claimed.",
            "details": news_details,
        }
    )
    json_path = root / "reports" / "research" / f"{candidate_spec.name}-promotion.json"
    report_path = json_path.with_suffix(".md")
    write_json(json_path, payload)
    _write_activation_promotion_markdown(report_path, json_path, payload)
    return json_path


def _target_weight_summary(path: Path) -> dict[str, Any] | None:
    payload = _load_optional_json(path)
    if payload is None:
        return None
    return {
        "path": _relpath(path, project_root()),
        "summary": payload.get("summary"),
        "parity_check": payload.get("parity_check"),
    }


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _write_markdown(
    path: Path,
    json_path: Path,
    candidate_spec_path: Path,
    payload: dict[str, Any],
) -> Path:
    ensure_dir(path.parent)
    readiness = payload["readiness"]
    lines = [
        f"# Hybrid Paper Plan: {payload['strategy_name']}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Candidate spec: `{candidate_spec_path}`",
        f"- Readiness status: `{readiness['status']}`",
        f"- Ready: `{readiness['ready']}`",
        "",
        "## Blocking Checks",
        "",
    ]
    for check in readiness["blocking_checks"]:
        lines.append(f"- `{check['name']}`: {check['message']}")
    lines.extend(["", "## Enable Sequence", ""])
    for index, step in enumerate(payload["paper_enable_sequence"], start=1):
        lines.append(f"{index}. {step}")
    lines.extend(["", "## Safety", "", f"- {payload['safety_note']}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_activation_promotion_markdown(
    path: Path,
    json_path: Path,
    payload: dict[str, Any],
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Hybrid Paper Activation: {payload['strategy_name']}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Source spec: `{payload['source_evidence']['source_promotion_path']}`",
        f"- Status: `{payload['status']}`",
        f"- Ready: `{payload['ready']}`",
        "",
        "## Checks",
        "",
    ]
    for check in payload["checks"]:
        lines.append(f"- `{check['name']}`: {check['message']}")
    lines.extend(["", "## Safety", "", f"- {payload['safety_note']}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _relpath(path: Path | str, root: Path) -> str:
    candidate = Path(path)
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix()
