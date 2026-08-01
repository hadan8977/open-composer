from __future__ import annotations

from typing import Any

from open_composer.models.strategy_spec import StrategySpec

_BINDING_FIELDS = {
    "candidate_manifest_path",
    "data_feasibility_path",
    "iter_id",
    "knowledge_contract",
    "universe_contract_path",
}

_ITERATION_FIELDS = _BINDING_FIELDS | {
    "candidate_budget",
    "factor_variants",
    "method_variants",
    "parameter_ranges",
    "parameter_space",
    "universe_variants",
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
        for field in _BINDING_FIELDS
        if _meaningful(top_level.get(field))
        and _meaningful(legacy.get(field))
        and top_level[field] != legacy[field]
    )
    if conflicts:
        raise ValueError(
            "conflicting top-level and notes.research_design bindings: " + ", ".join(conflicts)
        )
    return {**legacy, **top_level}


def research_design_requires_iteration_gate(design: dict[str, Any]) -> bool:
    return any(_meaningful(design.get(field)) for field in _ITERATION_FIELDS)


def _meaningful(value: Any) -> bool:
    return value not in {None, "", False} if not isinstance(value, (dict, list)) else bool(value)
