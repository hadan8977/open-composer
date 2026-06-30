from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.kernel.datamodel import ResearchDataModel
from open_composer.strategy_versions import strategy_content_hash


@dataclass(frozen=True)
class ResearchBrief(ResearchDataModel):
    strategy_name: str
    objective: str
    hypothesis: str
    target_market: str
    default_risk: str = "manual_signal_only_until_research_and_paper_readiness_pass"
    constraints: list[str] = field(default_factory=list)
    required_questions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchSpace(ResearchDataModel):
    family: str
    candidate_count: int = 1
    max_candidates: int = 1
    method_variants: list[str] = field(default_factory=list)
    factor_variants: list[str] = field(default_factory=list)
    universe_variants: list[list[str]] = field(default_factory=list)
    parameter_ranges: dict[str, list[Any]] = field(default_factory=dict)
    cost_assumptions: dict[str, Any] = field(default_factory=dict)
    filters: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchRunIndexRecord(ResearchDataModel):
    run_id: str
    strategy_name: str
    source_spec_path: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    spec_hash: str | None = None
    status: Literal["ok", "warning", "blocked"] = "warning"
    kind: str = "research_report"
    data_profile: dict[str, Any] = field(default_factory=dict)
    candidate_count: int = 1
    trial_count: int = 1
    runtime_seconds: float | None = None
    gate_status: Literal["ok", "warning", "blocked"] = "warning"
    blocked_items: list[str] = field(default_factory=list)
    warning_items: list[str] = field(default_factory=list)
    report_path: str | None = None
    json_path: str | None = None
    contract_path: str | None = None
    source_artifacts: dict[str, str | None] = field(default_factory=dict)


def build_default_research_brief(spec: StrategySpec) -> ResearchBrief:
    intent = str(getattr(spec.notes, "intent", "") or spec.description)
    return ResearchBrief(
        strategy_name=spec.name,
        objective=intent or f"Research {spec.name} with explicit promotion gates.",
        hypothesis=(
            "The StrategySpec should produce repeatable, cost-aware evidence that survives "
            "factor, execution, data, benchmark, and paper-readiness review."
        ),
        target_market=f"{spec.primary_symbol} {spec.timeframe}",
        constraints=[
            "StrategySpec remains the source of truth.",
            "Use registered capabilities only.",
            "Backtests use bar-close signals and next-bar-open fills.",
            "LLM, news, event, and macro features must be replayed from point-in-time packets.",
            "Sample, fixture, fallback, and trial-only evidence cannot satisfy paper readiness.",
        ],
        required_questions=[
            "Does OOS or walk-forward evidence support the result?",
            "Does the strategy beat the benchmark family after costs?",
            "Are factor diagnostics stable enough to trust?",
            "Are execution reality and capacity acceptable?",
            "Is any LLM or alternative-data contribution independently evidenced?",
            "What blocks promotion or paper readiness?",
        ],
    )


def search_space_from_spec(spec: StrategySpec) -> SearchSpace:
    research_design = _research_design_mapping(spec)
    parameter_ranges = _dict_of_lists(
        research_design.get("parameter_space") or research_design.get("parameter_ranges")
    )
    method_variants = _string_list(research_design.get("method_variants"))
    factor_variants = _string_list(research_design.get("factor_variants")) or sorted(spec.factors)
    universe_variants = _universe_variants(research_design.get("universe_variants"), spec)
    candidate_count = _candidate_count(parameter_ranges, method_variants, factor_variants)
    return SearchSpace(
        family=str(research_design.get("family") or "default_research_contract"),
        candidate_count=candidate_count,
        max_candidates=candidate_count,
        method_variants=method_variants,
        factor_variants=factor_variants,
        universe_variants=universe_variants,
        parameter_ranges=parameter_ranges,
        cost_assumptions={
            "commission_pct": spec.costs.commission_pct,
            "slippage_bps": spec.costs.slippage_bps,
            "impact_model": spec.costs.impact_model,
            "impact_eta": spec.costs.impact_eta,
            "impact_gamma": spec.costs.impact_gamma,
        },
        filters=[
            "manual_signal_until_promotion",
            "paper_ready_requires_research_contract_and_readiness",
        ],
    )


def research_run_id(strategy_name: str, spec: StrategySpec) -> str:
    return f"research-{strategy_name}-{strategy_content_hash(spec)[:12]}"


def _notes_mapping(spec: StrategySpec) -> dict[str, Any]:
    return spec.notes.model_dump(mode="json")


def _research_design_mapping(spec: StrategySpec) -> dict[str, Any]:
    if spec.research_design is not None:
        raw = spec.research_design.model_dump(mode="json")
        legacy = _notes_mapping(spec).get("research_design")
        if isinstance(legacy, dict):
            raw.setdefault("parameter_ranges", legacy.get("parameter_ranges"))
            raw.setdefault("method_variants", legacy.get("method_variants"))
            raw.setdefault("factor_variants", legacy.get("factor_variants"))
            raw.setdefault("universe_variants", legacy.get("universe_variants"))
            raw.setdefault("family", legacy.get("family"))
        return raw
    research_design = _notes_mapping(spec).get("research_design", {})
    return research_design if isinstance(research_design, dict) else {}


def _dict_of_lists(value: object) -> dict[str, list[Any]]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, list[Any]] = {}
    for key, raw_items in value.items():
        if isinstance(raw_items, list):
            output[str(key)] = list(raw_items)
        elif raw_items is not None:
            output[str(key)] = [raw_items]
    return output


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _universe_variants(value: object, spec: StrategySpec) -> list[list[str]]:
    if not isinstance(value, list):
        return [list(spec.universe)]
    variants: list[list[str]] = []
    for item in value:
        if isinstance(item, list):
            symbols = [str(symbol).upper() for symbol in item if symbol]
            if symbols:
                variants.append(symbols)
    return variants or [list(spec.universe)]


def _candidate_count(
    parameter_ranges: dict[str, list[Any]],
    method_variants: list[str],
    factor_variants: list[str],
) -> int:
    count = 1
    for values in parameter_ranges.values():
        count *= max(len(values), 1)
    if method_variants:
        count *= len(method_variants)
    if factor_variants:
        count *= max(len(factor_variants), 1)
    return max(count, 1)
