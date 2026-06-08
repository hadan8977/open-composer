from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.factor_lab import run_factor_lab
from open_composer.research.factor_library import (
    ALL_FACTORS,
    FactorDefinition,
    get_factor,
    list_factors,
)
from open_composer.research.factor_lineage import append_lineage


@dataclass(frozen=True)
class AutoResearchResult:
    run_id: str
    thesis: str
    selected_factors: list[str]
    spec_path: Path
    evidence_status: str
    report_path: Path
    raw_evidence_status: str = "not_run"
    promotion_status: str | None = None
    paper_readiness_status: str | None = None
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _AutoEvidenceSummary:
    research_status: str
    raw_status: str
    promotion_status: str | None = None
    paper_readiness_status: str | None = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_FAMILY_KEYWORDS: dict[str, list[str]] = {
    "trend_momentum": ["trend", "uptrend", "momentum", "rally", "continuation"],
    "relative_strength": ["relative", "rs", "leader", "leadership", "ranking"],
    "momentum_short": ["reversal", "mean revert", "mean-revert", "bounce", "oversold"],
    "risk_regime": ["regime", "risk", "risk off", "risk-off", "vix", "calm", "quiet"],
    "volatility_rank": ["volatility", "vol", "quiet", "calm", "range"],
    "drawdown_guard": ["drawdown", "crash", "guard", "protect", "defensive"],
    "overnight_gap": ["overnight", "gap", "open gap"],
    "kline_shape": ["candle", "kbar", "k-bar", "body", "shadow"],
    "breadth_canary": ["breadth", "canary", "participation"],
    "volume_momentum": ["volume", "liquidity", "participation"],
}

_COMPLEMENT_RULES: dict[str, str] = {
    "trend_momentum": "risk_regime",
    "momentum_short": "risk_regime",
    "relative_strength": "risk_regime",
    "overnight_gap": "risk_regime",
    "kline_shape": "risk_regime",
    "volume_momentum": "risk_regime",
    "risk_regime": "trend_momentum",
    "drawdown_guard": "trend_momentum",
    "volatility_rank": "trend_momentum",
    "breadth_canary": "trend_momentum",
}

_THESIS_FAMILY_ASSERTIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("overnight", "gap", "open gap"), "overnight_gap"),
    (("drawdown", "crash"), "drawdown_guard"),
    (("volatility", " vol "), "volatility_rank"),
)


def run_auto_research(
    thesis: str,
    universe: list[str],
    *,
    timeframe: str = "daily",
    data_source: str = "sample",
    data_path: str | None = None,
    max_factors: int = 5,
    use_llm: bool = False,
    root: Path | None = None,
) -> AutoResearchResult:
    base = root or project_root()
    symbols = [symbol.upper().strip() for symbol in universe if symbol.strip()]
    if not symbols:
        raise ValueError("universe must include at least one symbol")
    if max_factors < 1:
        raise ValueError("max_factors must be at least 1")

    run_id = _make_run_id(thesis)
    run_dir = ensure_dir(base / "reports" / "research" / "auto" / run_id)
    (run_dir / "thesis.md").write_text(thesis.rstrip() + "\n", encoding="utf-8")

    candidates = (
        _select_with_llm(thesis, symbols) if use_llm else _select_with_keyword_heuristic(thesis)
    )
    candidates = [factor for factor in candidates if factor.expression]
    if not candidates:
        candidates = list_factors(family="trend_momentum", expression_only=True)[:5]
    _write_json(run_dir / "candidates.json", [factor.id for factor in candidates])

    ic_scores = _run_single_factor_ic(
        candidates=candidates,
        thesis=thesis,
        universe=symbols,
        timeframe=timeframe,
        data_source=data_source,
        data_path=data_path,
        base=base,
        run_dir=run_dir,
    )
    _write_json(run_dir / "ic_scores.json", ic_scores)

    selected = _select_top_k(ic_scores, candidates, max_factors)
    if not selected:
        selected = candidates[: min(max_factors, max(1, len(candidates)))]
    _write_json(run_dir / "selected_factors.json", [factor.id for factor in selected])

    spec_path = _draft_spec(
        thesis=thesis,
        run_id=run_id,
        selected=selected,
        universe=symbols,
        timeframe=timeframe,
        data_source=data_source,
        data_path=data_path,
        base=base,
    )

    evidence_summary = _AutoEvidenceSummary(
        research_status="not_run",
        raw_status="not_run",
    )
    try:
        from open_composer.research.evidence import build_strategy_evidence
        from open_composer.research.research_brief import init_research_brief

        init_research_brief(spec_path, base, search_budget=max(1, len(selected)), overwrite=True)
        evidence = build_strategy_evidence(spec_path, base)
        evidence_summary = _summarize_auto_evidence(evidence)
    except Exception as exc:  # noqa: BLE001
        evidence_summary = _AutoEvidenceSummary(
            research_status="failed",
            raw_status="failed",
            blockers=[str(exc)],
        )

    report_path = _write_final_report(
        run_dir=run_dir,
        thesis=thesis,
        candidates=candidates,
        ic_scores=ic_scores,
        selected=selected,
        spec_path=spec_path,
        evidence_summary=evidence_summary,
    )
    return AutoResearchResult(
        run_id=run_id,
        thesis=thesis,
        selected_factors=[factor.id for factor in selected],
        spec_path=spec_path,
        evidence_status=evidence_summary.research_status,
        raw_evidence_status=evidence_summary.raw_status,
        promotion_status=evidence_summary.promotion_status,
        paper_readiness_status=evidence_summary.paper_readiness_status,
        report_path=report_path,
        warnings=evidence_summary.warnings,
        blockers=evidence_summary.blockers,
        next_actions=[
            f"Review {spec_path}",
            f"Read {report_path}",
            f"Run oc strategy evidence {spec_path}",
        ],
    )


def _select_with_keyword_heuristic(thesis: str) -> list[FactorDefinition]:
    text = thesis.lower()
    matched_families: list[str] = []
    for family, triggers in _FAMILY_KEYWORDS.items():
        if any(trigger in text for trigger in triggers):
            matched_families.append(family)
    if not matched_families:
        matched_families = ["trend_momentum", "risk_regime"]

    extended_families = list(matched_families)
    for family in matched_families:
        complement = _COMPLEMENT_RULES.get(family)
        if complement and complement not in extended_families:
            extended_families.append(complement)
    matched_families = extended_families

    candidates: list[FactorDefinition] = []
    seen: set[str] = set()
    for family in matched_families:
        added = 0
        for factor in _factors_for_family_or_alias(family):
            if factor.id not in seen and factor.expression:
                candidates.append(factor)
                seen.add(factor.id)
                added += 1
            if added >= 5:
                break

    for triggers, required_family in _THESIS_FAMILY_ASSERTIONS:
        if not any(trigger in text for trigger in triggers):
            continue
        if any(_factor_matches_required_family(factor, required_family) for factor in candidates):
            continue
        for factor in _factors_for_family_or_alias(required_family)[:3]:
            if factor.id not in seen and factor.expression:
                candidates.append(factor)
                seen.add(factor.id)
        if not any(
            _factor_matches_required_family(factor, required_family) for factor in candidates
        ):
            raise ValueError(
                f"thesis requires {required_family} factors, but no expressionable catalog "
                "factor was available"
            )
    return candidates[:15]


def _select_with_llm(thesis: str, universe: list[str]) -> list[FactorDefinition]:
    from open_composer.config import default_openai_model, openai_api_key, openai_base_url

    if not openai_api_key():
        return _select_with_keyword_heuristic(thesis)
    try:
        from openai import OpenAI
    except ImportError:
        return _select_with_keyword_heuristic(thesis)

    catalog = [
        {"id": factor.id, "family": factor.family, "description": factor.description}
        for factor in ALL_FACTORS
        if factor.expression
    ]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["selected_factor_ids", "reasoning"],
        "properties": {
            "selected_factor_ids": {
                "type": "array",
                "minItems": 1,
                "maxItems": 15,
                "items": {"type": "string", "enum": [item["id"] for item in catalog]},
            },
            "reasoning": {"type": "string"},
        },
    }
    try:
        client = OpenAI(api_key=openai_api_key(), base_url=openai_base_url())
        response = client.responses.create(
            model=default_openai_model(),
            input=[
                {
                    "role": "system",
                    "content": (
                        "Select factor IDs from the provided catalog for a single-symbol "
                        "research thesis. Return only existing IDs."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "thesis": thesis,
                            "universe": universe,
                            "catalog": catalog,
                        },
                        indent=2,
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "factor_selection",
                    "strict": True,
                    "schema": schema,
                }
            },
        )
        payload = json.loads(response.output_text)
        return [get_factor(factor_id) for factor_id in payload["selected_factor_ids"]]
    except Exception:  # noqa: BLE001
        return _select_with_keyword_heuristic(thesis)


def _run_single_factor_ic(
    *,
    candidates: list[FactorDefinition],
    thesis: str,
    universe: list[str],
    timeframe: str,
    data_source: str,
    data_path: str | None,
    base: Path,
    run_dir: Path,
) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    mini_dir = ensure_dir(run_dir / "mini_specs")
    for factor in candidates:
        if not factor.expression:
            scores[factor.id] = {"skipped": True, "reason": "no expression"}
            continue
        spec_path = _mini_spec_path(
            factor=factor,
            thesis=thesis,
            universe=universe,
            timeframe=timeframe,
            data_source=data_source,
            data_path=data_path,
            base=base,
            mini_dir=mini_dir,
        )
        try:
            result = run_factor_lab(spec_path, base, forward_bars=5, quantiles=5)
            metric = result.factor_metrics[0] if result.factor_metrics else None
            scores[factor.id] = {
                "status": result.status,
                "rank_ic": metric.rank_ic if metric else None,
                "rolling_rank_ic_mean": metric.rolling_rank_ic_mean if metric else None,
                "stability_score": metric.stability_score if metric else None,
                "coverage_pct": metric.coverage_pct if metric else None,
                "observations": metric.observations if metric else 0,
                "top_bottom_spread_pct": metric.top_bottom_spread_pct if metric else None,
                "flags": metric.flags if metric else ["missing_metric"],
                "spec_path": _relpath(spec_path, base),
                "json_path": _relpath(result.json_path, base),
            }
        except Exception as exc:  # noqa: BLE001
            scores[factor.id] = {"status": "failed", "error": str(exc), "rank_ic": None}
    return scores


def _select_top_k(
    ic_scores: dict[str, dict[str, Any]],
    candidates: list[FactorDefinition],
    k: int,
) -> list[FactorDefinition]:
    scored: list[tuple[FactorDefinition, float]] = []
    for factor in candidates:
        score = ic_scores.get(factor.id, {})
        rank_ic = _float_or_none(score.get("rank_ic"))
        coverage = _float_or_none(score.get("coverage_pct")) or 0.0
        observations = int(score.get("observations") or 0)
        stability = _float_or_none(score.get("stability_score")) or 0.0
        if rank_ic is None or observations < 30 or coverage < 70:
            continue
        scored.append((factor, abs(rank_ic) * max(stability, 0.1) * (coverage / 100.0)))
    scored.sort(key=lambda item: item[1], reverse=True)
    return [factor for factor, _ in scored[:k]]


def _draft_spec(
    *,
    thesis: str,
    run_id: str,
    selected: list[FactorDefinition],
    universe: list[str],
    timeframe: str,
    data_source: str,
    data_path: str | None,
    base: Path,
) -> Path:
    slug = run_id.lower().replace("-", "_")
    spec_name = f"auto_{slug}"
    spec_path = base / "strategy_specs" / "drafts" / f"{spec_name}.yaml"
    ensure_dir(spec_path.parent)
    factor_names = [_factor_signal_name(factor) for factor in selected]
    factors = {
        name: {
            "source": "factor_library",
            "factor_id": factor.id,
            "params": {},
        }
        for name, factor in zip(factor_names, selected, strict=True)
    }
    parameter_space = {
        f"{name}.{param}": values
        for name, factor in zip(factor_names, selected, strict=True)
        for param, values in factor.default_parameter_space.items()
        if values and all(_is_scalar(item) for item in values)
    }
    spec_yaml: dict[str, Any] = {
        "name": spec_name,
        "description": f"Auto-generated by oc research auto. Thesis: {thesis}",
        "timeframe": timeframe,
        "universe": universe,
        "lifecycle": "draft",
        "entry": {"all": [f"{name} > 0" for name in factor_names], "any": []},
        "exit": {"all": [], "any": [f"{name} < 0" for name in factor_names]},
        "risk": {"max_trades_per_day": 1, "max_position_weight": 0.5, "stop_loss_pct": 3.0},
        "costs": {
            "commission_pct": 0.0,
            "slippage_bps": 0.0,
            "impact_model": "linear",
            "impact_eta": 0.0,
            "impact_gamma": 0.0,
        },
        "execution": {
            "backend": "python_reference",
            "mode": "manual_signal",
            "signal_on": "bar_close",
            "fill_assumption": "next_bar_open",
            "broker": "none",
        },
        "data": {"source": data_source, "symbol": universe[0], "path": data_path, "feed": None},
        "data_assumptions": {
            "source": data_source,
            "adjusted": True,
            "timezone": "America/New_York",
        },
        "factors": factors,
        "llm_review": {"enabled": False},
        "notes": {"intent": f"AI-driven research from thesis: {thesis}", "open_questions": []},
        "research_design": {
            "parameter_space": parameter_space,
            "candidate_budget": max(1, min(150, len(parameter_space) * 3 or len(selected))),
            "selection_objective": "rank_ic_stability_then_research_evidence",
            "anti_overfit_notes": [
                "Catalog candidates are selected before backtest evidence.",
                "Sample-data evidence is workflow-only and not paper-ready.",
            ],
            "validation_plan": [
                "single-factor IC screen",
                "StrategySpec validation",
                "strategy evidence report",
            ],
        },
        "required_capabilities": [_market_capability(data_source, timeframe)],
    }
    spec_path.write_text(yaml.safe_dump(spec_yaml, sort_keys=False), encoding="utf-8")
    load_strategy_spec(spec_path)
    for factor in selected:
        append_lineage(
            factor.id, spec_path, added_by="auto_research", creation_thesis=thesis, root=base
        )
    return spec_path


def _mini_spec_path(
    *,
    factor: FactorDefinition,
    thesis: str,
    universe: list[str],
    timeframe: str,
    data_source: str,
    data_path: str | None,
    base: Path,
    mini_dir: Path,
) -> Path:
    factor_name = _factor_signal_name(factor)
    spec_name = f"auto_ic_{factor.id}"
    spec_yaml = {
        "name": spec_name,
        "description": f"Auto-research single-factor IC test. Thesis: {thesis}",
        "timeframe": timeframe,
        "universe": universe,
        "lifecycle": "draft",
        "entry": {"all": [f"{factor_name} > 0"], "any": []},
        "exit": {"all": [], "any": [f"{factor_name} < 0"]},
        "risk": {"max_trades_per_day": 1, "max_position_weight": 0.5},
        "costs": {
            "commission_pct": 0.0,
            "slippage_bps": 0.0,
            "impact_model": "linear",
            "impact_eta": 0.0,
            "impact_gamma": 0.0,
        },
        "execution": {
            "backend": "python_reference",
            "mode": "manual_signal",
            "signal_on": "bar_close",
            "fill_assumption": "next_bar_open",
            "broker": "none",
        },
        "data": {"source": data_source, "symbol": universe[0], "path": data_path, "feed": None},
        "data_assumptions": {
            "source": data_source,
            "adjusted": True,
            "timezone": "America/New_York",
        },
        "factors": {
            factor_name: {
                "source": "factor_library",
                "factor_id": factor.id,
                "params": {},
            }
        },
        "llm_review": {"enabled": False},
        "notes": {
            "intent": f"Single-factor IC screen for {factor.id}",
            "open_questions": [],
        },
        "required_capabilities": [_market_capability(data_source, timeframe)],
    }
    spec_path = mini_dir / f"{spec_name}.yaml"
    spec_path.write_text(yaml.safe_dump(spec_yaml, sort_keys=False), encoding="utf-8")
    load_strategy_spec(spec_path)
    return spec_path


def _write_final_report(
    *,
    run_dir: Path,
    thesis: str,
    candidates: list[FactorDefinition],
    ic_scores: dict[str, dict[str, Any]],
    selected: list[FactorDefinition],
    spec_path: Path,
    evidence_summary: _AutoEvidenceSummary,
) -> Path:
    selected_ids = {factor.id for factor in selected}
    lines = [
        "# AI Auto-Research Report",
        "",
        f"- Thesis: {thesis}",
        f"- Generated: `{datetime.now(UTC).isoformat()}`",
        f"- Spec: `{spec_path}`",
        f"- Research status: `{evidence_summary.research_status}`",
        f"- Raw strategy evidence status: `{evidence_summary.raw_status}`",
        f"- Promotion status: `{evidence_summary.promotion_status or 'not_available'}`",
        f"- Paper readiness status: `{evidence_summary.paper_readiness_status or 'not_available'}`",
        "",
        f"## Candidate Factors ({len(candidates)})",
        "",
        "| Factor | Family | Rank IC | Stability | Coverage | Observations | Status |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for factor in candidates:
        score = ic_scores.get(factor.id, {})
        status = "selected" if factor.id in selected_ids else str(score.get("status") or "rejected")
        lines.append(
            "| "
            f"`{factor.id}` | {factor.family} | {_fmt(score.get('rank_ic'))} | "
            f"{_fmt(score.get('stability_score'))} | {_fmt(score.get('coverage_pct'))} | "
            f"{score.get('observations') or 0} | {status} |"
        )
    lines.extend(["", f"## Selected Factors ({len(selected)})", ""])
    for factor in selected:
        lines.append(f"- `{factor.id}` ({factor.family}): {factor.description}")
    if evidence_summary.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in evidence_summary.warnings)
    if evidence_summary.blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in evidence_summary.blockers)
    lines.extend(
        [
            "",
            "## Next Actions",
            "",
            f"- Review `{spec_path}` before promotion.",
            f"- Re-run `oc strategy evidence {spec_path}` after manual edits.",
            "- Treat sample or cache-backed outputs as workflow evidence only.",
        ]
    )
    report_path = run_dir / "report.md"
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return report_path


def _summarize_auto_evidence(evidence: Any) -> _AutoEvidenceSummary:
    raw_status = str(getattr(evidence, "status", "unknown") or "unknown")
    research_report = getattr(evidence, "research_report", None)
    report_payload = _read_json(getattr(research_report, "json_path", None))
    control = getattr(evidence, "control", None)
    control_state = getattr(control, "state", None)
    control_state = control_state if isinstance(control_state, dict) else {}
    promotion_state = _dict(control_state.get("promotion_state"))
    promotion_status = _optional_str(
        promotion_state.get("status") or _dict(report_payload.get("promotion")).get("status")
    )
    paper_readiness_status = _optional_str(
        _dict(report_payload.get("paper_readiness")).get("status")
    )

    blockers: list[str] = []
    warnings: list[str] = []

    for item in _list(report_payload.get("checklist")):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown")
        name = str(item.get("name") or "unknown_check")
        if status == "ok":
            continue
        message = _auto_check_message(item)
        if status == "warning" or _auto_check_is_exploration_warning(item):
            warnings.append(f"{name}: {message}")
        else:
            blockers.append(f"{name}: {message}")

    strict_data = _dict(promotion_state.get("strict_data"))
    for check_name in [str(item) for item in _list(promotion_state.get("blocked_checks"))]:
        if check_name == "strict_data" and _strict_data_is_workflow_only(strict_data):
            warnings.append(
                "promotion: strict_data is workflow-only sample/fixture/cache evidence; "
                "not paper-ready"
            )
        else:
            blockers.append(f"promotion: {check_name}")
    for item in _list(control_state.get("blocked_items")):
        text = str(item)
        if text.startswith("promotion:strict_data") and _strict_data_is_workflow_only(strict_data):
            warnings.append(_clip(text, 180))
        elif text:
            blockers.append(text)
    warnings.extend(str(item) for item in _list(control_state.get("warning_items")) if item)

    blockers = _dedupe(blockers)
    warnings = _dedupe(warnings)
    if blockers:
        status = "blocked"
    elif warnings or raw_status != "ok":
        status = "warning"
    else:
        status = "ok"
    return _AutoEvidenceSummary(
        research_status=status,
        raw_status=raw_status,
        promotion_status=promotion_status,
        paper_readiness_status=paper_readiness_status,
        blockers=blockers,
        warnings=warnings,
    )


def _auto_check_is_exploration_warning(item: dict[str, Any]) -> bool:
    name = str(item.get("name") or "")
    evidence = item.get("evidence")
    if name == "paper_gap":
        return True
    if name == "data_quality":
        return _data_evidence_is_workflow_only(evidence)
    if name == "factor_diagnostics":
        text = str(evidence or "")
        return "factor_lab_status=warning" in text
    return False


def _auto_check_message(item: dict[str, Any]) -> str:
    evidence = item.get("evidence")
    if isinstance(evidence, dict):
        warnings = [str(value) for value in _list(evidence.get("warnings"))]
        if warnings:
            return "; ".join(warnings[:2])
        status = evidence.get("status")
        if status:
            return f"status={status}"
    return str(evidence or item.get("status") or "no detail")


def _data_evidence_is_workflow_only(evidence: Any) -> bool:
    if not isinstance(evidence, dict):
        return False
    tokens = [
        evidence.get("data_source"),
        evidence.get("data_source_mode"),
        evidence.get("evidence_level"),
        evidence.get("acquisition_tier"),
    ]
    text = " ".join(str(item).lower() for item in tokens if item)
    return any(token in text for token in ["sample", "fixture", "fallback", "cache"])


def _strict_data_is_workflow_only(strict_data: dict[str, Any]) -> bool:
    details = _dict(strict_data.get("details"))
    message = str(strict_data.get("message") or "")
    return _data_evidence_is_workflow_only(details) or any(
        token in message.lower() for token in ["sample", "fixture", "fallback", "cache"]
    )


def _read_json(path: Any) -> dict[str, Any]:
    if path is None:
        return {}
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None and str(value) else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
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


def _clip(value: str, limit: int) -> str:
    text = str(value).strip()
    return text if len(text) <= limit else text[: max(limit - 3, 0)].rstrip() + "..."


def _factors_for_family_or_alias(family: str) -> list[FactorDefinition]:
    direct = list_factors(family=family, expression_only=True)
    if direct:
        return direct
    fallbacks = {
        "drawdown_guard": lambda factor: "drawdown" in factor.id or factor.family == "risk_regime",
        "overnight_gap": lambda factor: "overnight" in factor.id or "gap" in factor.id,
        "volatility_rank": lambda factor: (
            "volatility" in factor.id or "atr" in factor.id or "bollinger" in factor.id
        ),
        "breadth_canary": lambda factor: "breadth" in factor.id or "canary" in factor.id,
    }
    predicate = fallbacks.get(family)
    if predicate:
        return [factor for factor in list_factors(expression_only=True) if predicate(factor)]
    return []


def _factor_matches_required_family(factor: FactorDefinition, required_family: str) -> bool:
    if factor.family == required_family:
        return True
    if required_family == "drawdown_guard":
        return "drawdown" in factor.id
    if required_family == "overnight_gap":
        return "overnight" in factor.id or "gap" in factor.id
    if required_family == "volatility_rank":
        return "volatility" in factor.id or "atr" in factor.id or "bollinger" in factor.id
    return False


def _factor_signal_name(factor: FactorDefinition) -> str:
    return re.sub(r"\W+", "_", factor.id).strip("_") + "_signal"


def _market_capability(data_source: str, timeframe: str) -> str:
    if data_source == "sample" and timeframe == "daily":
        return "market.synthetic_daily_long"
    if data_source == "sample":
        return "market.sample_ohlcv"
    if data_source == "alpaca":
        return "market.alpaca_bars"
    if data_source == "longbridge":
        return "market.longbridge_bars"
    return "market.sample_ohlcv"


def _make_run_id(thesis: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", thesis.lower()).strip("_")[:48] or "research"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{slug}"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _fmt(value: Any) -> str:
    number = _float_or_none(value)
    return "n/a" if number is None else f"{number:.4f}"


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
