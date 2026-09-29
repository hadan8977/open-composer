from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "analyze_ma_car", ROOT / "scripts" / "analyze_ma_target_car_path.py"
)
assert _spec and _spec.loader
car = importlib.util.module_from_spec(_spec)
sys.modules["analyze_ma_car"] = car
_spec.loader.exec_module(car)


def test_excess_matrix_subtracts_member_mean() -> None:
    ret = np.array([[0.10, 0.00, 0.50]])
    member = np.array([[True, True, False]])
    out = car.excess_matrix(ret, member)
    assert np.allclose(out[0, :2], [0.05, -0.05])


def test_mean_t_handles_small_and_nan() -> None:
    assert car.mean_t(np.array([1.0, np.nan]))["n"] == 1
    out = car.mean_t(np.array([1.0, 2.0, 3.0, np.nan]))
    assert out["n"] == 3 and out["mean"] == 2.0 and out["hit"] == 1.0


def test_path_stats_windows() -> None:
    T = 40
    close_ex = np.zeros((T, 1))
    close_ex[25:30, 0] = 0.01  # days -5..-1 for an event at row 30
    close_ex[30, 0] = 0.05
    fwd = {5: np.full((T, 1), 0.02)}
    gap = np.full((T, 1), 0.003)
    rows = np.array([30, 30, 30])
    cols = np.array([0, 0, 0])
    out = car.path_stats(rows, cols, close_ex, fwd, gap)
    assert abs(out["pre_m5_m1"]["mean"] - 0.05) < 1e-12
    assert abs(out["day0_close_to_close"]["mean"] - 0.05) < 1e-12
    assert abs(out["gap_close0_to_open1"]["mean"] - 0.003) < 1e-12
    assert abs(out["post_h5"]["mean"] - 0.02) < 1e-12
