from __future__ import annotations

from typing import Any

from open_composer.models.strategy_spec import StrategySpec

RESEARCH_DESIGN_BINDING_FIELDS = frozenset(
    {
        "campaign_contract_path",
        "candidate_manifest_path",
        "candidate_policy_contract_path",
        "cost_contract_path",
        "cumulative_trial_contract_path",
        "data_contract_path",
        "data_feasibility_path",
        "holdout_contract_path",
        "iter_id",
        "knowledge_contract",
        "preregistration_lock_path",
        "source_card_claim_ids",
        "source_cards_path",
        "universe_contract_path",
    }
)

_ITERATION_FIELDS = RESEARCH_DESIGN_BINDING_FIELDS | {
    "candidate_budget",
    "factor_variants",
    "method_variants",
    "parameter_ranges",
    "parameter_space",
    "universe_variants",
    "workflow_only_ungated_draft",
}


def research_design_mapping(spec: StrategySpec) -> dict[str, Any]:
    """Return one fail-closed view of current and legacy research design fields."""
    top_level = (
        spec.research_design.model_dump(mode="json", exclude_unset=True)
        if spec.research_design is not None
        else {}
    )
    notes = spec.notes.model_dump(mode="json")
    legacy_raw = notes.get("research_design") if isinstance(notes, dict) else None
    legacy = legacy_raw if isinstance(legacy_raw, dict) else {}

    conflicts = sorted(
        field
        for field in RESEARCH_DESIGN_BINDING_FIELDS
        if _meaningful(top_level.get(field))
        and _meaningful(legacy.get(field))
        and top_level[field] != legacy[field]
    )
    if conflicts:
        raise ValueError(
            "conflicting top-level and notes.research_design bindings: " + ", ".join(conflicts)
        )
    merged = {**legacy, **top_level}
    for field in RESEARCH_DESIGN_BINDING_FIELDS:
        if not _meaningful(top_level.get(field)) and _meaningful(legacy.get(field)):
            merged[field] = legacy[field]
    return merged


def research_design_requires_iteration_gate(design: dict[str, Any]) -> bool:
    return any(_meaningful(design.get(field)) for field in _ITERATION_FIELDS)


def research_design_has_bindings(design: dict[str, Any]) -> bool:
    return any(_meaningful(design.get(field)) for field in RESEARCH_DESIGN_BINDING_FIELDS)


def _meaningful(value: Any) -> bool:
    return value not in {None, "", False} if not isinstance(value, (dict, list)) else bool(value)
