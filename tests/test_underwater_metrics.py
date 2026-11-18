from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from open_composer.lab.metrics import longest_underwater_sessions


@pytest.mark.parametrize(
    "equity,expected",
    [
        ([], 0),
        ([90, 89, 100], 2),
        ([100, 99, 100, 99, 98, 97], 3),
        ([100, 100 - 0.5e-8, 100 - 2e-8], 1),
        ([110, 110, 109, 108, 110], 2),
    ],
)
def test_underwater_native_initial_capital_recovery_tail_and_tolerance(equity, expected):
    assert longest_underwater_sessions(equity, 100) == expected


def test_two_native_callers_invoke_shared_calculation_and_match_independent_reference():
    project = Path(__file__).resolve().parents[1]
    paths = [
        "research/cross_asset_mechanisms_20261102/implementation/mechanisms.py",
        "research/reversal_long_side_20261102/implementation/engine.py",
    ]
    # Verify actual callers migrated; compare with an independent run segmentation
    # reference, rather than invoking the shared function twice as validation.
    for path in paths:
        tree = ast.parse((project / path).read_text())
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "longest_underwater_sessions"
        ]
        assert len(calls) == 1
    equity = np.random.default_rng(20261104).normal(0, 2, 120).cumsum() + 100
    peaks = np.maximum.accumulate(np.r_[100, equity])[1:]
    dry = np.flatnonzero(np.r_[True, ~(equity < peaks - 1e-8), True])
    independent = int(np.max(np.diff(dry) - 1))
    assert longest_underwater_sessions(equity, 100) == independent
