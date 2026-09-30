from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "run_h20260929_80_dat_ic",
    Path(__file__).resolve().parents[1] / "scripts/run_h20260929_80_dat_ic.py",
)
assert _SPEC and _SPEC.loader
mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = mod
_SPEC.loader.exec_module(mod)


def test_log_price_ratio_is_nan_before_dat_leg_starts() -> None:
    idx = pd.bdate_range("2025-01-01", periods=10)
    r_dat = pd.Series([np.nan] * 4 + [0.01] * 6, index=idx)
    r_coin = pd.Series(0.005, index=idx)
    ratio = mod.log_price_ratio(r_dat, r_coin)
    assert ratio.iloc[:3].isna().all()
    # cumulative: 6 * 0.01 (DAT) - 10 * 0.005 (coin over all sessions); constant offsets cancel in z
    assert abs(ratio.iloc[-1] - 0.01) < 1e-12


def test_newey_west_t_and_spearman_sign() -> None:
    x = np.arange(100, dtype=float)
    assert mod.spearman(x, x) > 0.999
    assert mod.spearman(x, -x) < -0.999
    assert mod.newey_west_t(np.ones(50) + np.arange(50) % 2 * 0.01, 5) > 10


def test_count_episodes_requires_twenty_session_gap() -> None:
    cal = pd.bdate_range("2024-01-01", periods=100)
    active = np.zeros(100, dtype=bool)
    active[[5, 6, 7, 30, 31, 40]] = True
    # starts at 5, then 30 (gap 25 >= 20), then 40 is only 10 after 30 -> not counted
    assert mod.count_episodes(cal, active, cal) == 2


def test_rolling_beta_is_clipped_and_needs_min_obs() -> None:
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2024-01-01", periods=200)
    coin = pd.Series(rng.normal(0, 0.02, 200), index=idx)
    dat = 5.0 * coin + rng.normal(0, 0.001, 200)
    beta = mod.rolling_beta(dat, coin)
    assert beta.iloc[:39].isna().all()
    assert beta.dropna().max() <= 3.0 + 1e-12
    assert beta.dropna().min() >= 0.5 - 1e-12


def test_state_machine_z_and_m() -> None:
    screen_spec = importlib.util.spec_from_file_location(
        "run_h20260929_80_dat_screen",
        Path(__file__).resolve().parents[1] / "scripts/run_h20260929_80_dat_screen.py",
    )
    assert screen_spec and screen_spec.loader
    scr = importlib.util.module_from_spec(screen_spec)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    screen_spec.loader.exec_module(scr)
    z = np.array([0.0, 1.2, 0.8, 0.1, -1.3, -0.5, -0.1])
    rows = list(range(len(z)))
    sym = scr.state_at_signal_dates(z, "Z", "SYM", rows)
    assert [sym[i] for i in rows] == [0, -1, -1, 0, 1, 1, 0]
    short = scr.state_at_signal_dates(z, "Z", "SHORT", rows)
    assert [short[i] for i in rows] == [0, -1, -1, 0, 0, 0, 0]
    m = np.array([0.02, -0.15, 0.2, np.nan])
    mm = scr.state_at_signal_dates(m, "M", "SYM", [0, 1, 2, 3])
    assert [mm[i] for i in range(4)] == [0, -1, 1, 0]
    ms = scr.state_at_signal_dates(m, "M", "SHORT", [0, 1, 2, 3])
    assert [ms[i] for i in range(4)] == [0, -1, 0, 0]


def test_book_vector_signs_short_dat_is_negative_dat_weight() -> None:
    screen_spec = importlib.util.spec_from_file_location(
        "run_h20260929_80_dat_screen2",
        Path(__file__).resolve().parents[1] / "scripts/run_h20260929_80_dat_screen.py",
    )
    assert screen_spec and screen_spec.loader
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    scr = importlib.util.module_from_spec(screen_spec)
    screen_spec.loader.exec_module(scr)
    idx = pd.bdate_range("2025-07-01", periods=5)
    pc = pd.DataFrame(1.0, index=idx, columns=["MSTR", "FBTC", "BTCSPOT", "ETHSPOT"])
    series = {"P1": {"beta": pd.Series(1.0, index=idx)}}
    book = scr.Book(pc, pc.copy(), series, idx)
    short_dat = book.vector("P1", -1, 2)
    assert short_dat[book.ix["MSTR"]] == -0.5 and short_dat[book.ix["FBTC"]] == 0.5
    long_dat = book.vector("P1", +1, 2)
    assert long_dat[book.ix["MSTR"]] == 0.5 and long_dat[book.ix["FBTC"]] == -0.5
    assert not book.vector("P1", 0, 2).any()
