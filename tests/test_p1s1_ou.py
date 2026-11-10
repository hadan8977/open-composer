from __future__ import annotations

import numpy as np

from scripts.p1s1_ou import fit_ar1, path_signal, update_position


def test_ou_fit_rejects_non_mean_reverting_path() -> None:
    fit = fit_ar1(np.arange(30, dtype="float64"))
    assert not fit.valid


def test_ou_state_machine_thresholds() -> None:
    assert update_position(0, -1.26) == 1
    assert update_position(1, -0.50) == 1
    assert update_position(1, -0.49) == 0
    assert update_position(0, 1.26) == -1
    assert update_position(-1, 0.75) == -1
    assert update_position(-1, 0.74) == 0


def test_path_signal_is_deterministic() -> None:
    x = np.sin(np.arange(80) / 5.0)
    first = path_signal(x)
    second = path_signal(x)
    assert first[0] == second[0]
    assert np.isclose(first[2], second[2], equal_nan=True)
