from __future__ import annotations

from open_composer.models.strategy_spec import StrategySpec


def evaluation_policy_warnings(spec: StrategySpec) -> list[str]:
    if spec.evaluation_policy is None:
        return ["evaluation_policy_missing"]
    warnings: list[str] = []
    policy = spec.evaluation_policy
    if policy.edge_type is None:
        warnings.append("edge_type_missing")
    if policy.edge_half_life_days is None:
        warnings.append("edge_half_life_days_missing")
    return warnings


def require_recent_positive(spec: StrategySpec) -> bool:
    return bool(
        spec.evaluation_policy is None or spec.evaluation_policy.require_recent_oos_positive
    )
