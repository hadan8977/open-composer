"""Condition-triggering fixture checks for configuration branches."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Ablation:
    key: str
    alternative: Any
    fixture: Any
    condition: str


def check_ablations(
    config: Mapping[str, Any],
    cases: Sequence[Ablation],
    observe: Callable[[dict, Any], Mapping[str, float]],
) -> list[dict]:
    """Compare named observable numbers on fixtures designed to exercise each branch.

    Equal real-data PnL is not a failure if no condition triggered. Here a case claims
    to trigger that condition, so identical observables identify an ineffective flag
    or an invalid fixture. Choose actual signals/fills/holdings or costs as observables.
    """
    if len({case.key for case in cases}) != len(cases):
        raise ValueError("Ablation keys must be unique")
    reports = []
    for case in cases:
        if case.key not in config or config[case.key] == case.alternative:
            raise ValueError(f"Ablation must change an existing config key: {case.key}")
        if not case.condition.strip():
            raise ValueError("Explain which fixture condition triggers the branch")
        baseline = dict(observe(deepcopy(dict(config)), deepcopy(case.fixture)))
        changed_config = deepcopy(dict(config))
        changed_config[case.key] = case.alternative
        changed = dict(observe(changed_config, deepcopy(case.fixture)))
        if not baseline or baseline.keys() != changed.keys():
            raise ValueError("Ablation observables must be nonempty and comparable")
        if not np.isfinite([*baseline.values(), *changed.values()]).all():
            raise ValueError("Ablation observables must be finite numbers")
        differences = [key for key in baseline if baseline[key] != changed[key]]
        if not differences:
            raise ValueError(f"No observed effect for {case.key}: {case.condition}")
        reports.append(
            {
                "key": case.key,
                "baseline_value": config[case.key],
                "alternative_value": case.alternative,
                "condition": case.condition,
                "baseline": baseline,
                "changed": changed,
                "changed_observables": differences,
            }
        )
    return reports
