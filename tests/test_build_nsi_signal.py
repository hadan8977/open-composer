from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_nsi_signal import clean_pairs  # noqa: E402


def _panel(cols: list[list[float]]) -> np.ndarray:
    return np.array(cols, dtype=np.float64).T


def test_plain_pair_kept() -> None:
    s = _panel([[100.0] * 5 + [110.0] * 5])
    out, d = clean_pairs(s, np.zeros(s.shape, dtype=bool), 5)
    assert np.isclose(out[5, 0], np.log(1.1))
    assert d["kept"] == 5 and np.isnan(out[:5, 0]).all()


def test_split_scale_pair_dropped() -> None:
    s = _panel([[100.0] * 4 + [200.0] * 6])
    out, d = clean_pairs(s, np.zeros(s.shape, dtype=bool), 4)
    assert d["b_scale"] > 0 and np.isnan(out[4:8, 0]).all()


def test_price_break_in_window_dropped() -> None:
    s = _panel([[100.0] * 4 + [110.0] * 6])
    flag = np.zeros(s.shape, dtype=bool)
    flag[6, 0] = True
    out, d = clean_pairs(s, flag, 4)
    assert d["c_price_break"] > 0
    assert np.isnan(out[6:10, 0]).all()
    assert np.isfinite(out[4, 0])


def test_swing_and_return_dropped() -> None:
    # 100 -> 140 -> 105 within the window: excursion ln(1.4) >= ln(1.3), final 5%.
    s = _panel([[100.0, 100.0, 140.0, 140.0, 105.0, 105.0, 105.0]])
    out, d = clean_pairs(s, np.zeros(s.shape, dtype=bool), 4)
    assert d["d_swing_back"] >= 1
    assert np.isnan(out[4, 0])


def test_missing_end_is_not_a_pair() -> None:
    s = _panel([[np.nan] * 3 + [100.0] * 4])
    out, d = clean_pairs(s, np.zeros(s.shape, dtype=bool), 3)
    assert d["valid_pairs"] == 1 and np.isfinite(out[6, 0])


def test_newey_west_t_matches_plain_t_at_lag_zero_scale() -> None:
    from nsi_ic_test import newey_west_t

    rng = np.random.default_rng(0)
    x = rng.normal(0.02, 0.1, 400)
    t = newey_west_t(x, 1)
    plain = x.mean() / (x.std(ddof=0) / np.sqrt(len(x)))
    assert t is not None and abs(t - plain) < 0.5
    assert newey_west_t(x[:5], 20) is None
