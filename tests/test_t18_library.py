"""Pure-function checks for the library batch-1 factors (T-20261006-18)."""

import numpy as np
import pandas as pd

from scripts import t18_factors as F


def _facts(rows):
    df = pd.DataFrame(
        rows, columns=["concept", "period_kind", "period_end", "val", "usable_session"]
    )
    df["cik"] = 1
    df["filed"] = df["usable_session"]
    for c in ("period_end", "usable_session", "filed"):
        df[c] = pd.to_datetime(df[c])
    return df


def test_org_cap_recursion():
    ends = pd.to_datetime(["2020-12-31", "2021-12-31", "2022-12-31"]).to_numpy("datetime64[D]")
    v = F.org_cap(ends, np.array([10.0, 20.0, 30.0]))
    assert abs(v - ((4 * 10 * 0.85 + 20) * 0.85 + 30)) < 1e-9


def test_seasonality_lags_and_min_obs():
    mi = np.arange(2016 * 12, 2016 * 12 + 130)
    m = np.tile(np.arange(130, dtype=float)[:, None], (1, 2))
    tgt = int(mi[-1]) + 1
    s, o = F.seasonality(m, mi, tgt)
    # same-month lags 72, 84, 96, 108, 120 -> positions 130 - lag ... only those >= 0
    pos = [130 - L for L in (72, 84, 96, 108, 120) if 130 - L >= 0]
    assert len(pos) >= 3 and abs(s[0] - np.mean(pos)) < 1e-9
    assert np.isfinite(o[0])


def test_seasonality_needs_three_years():
    mi = np.arange(2016 * 12, 2016 * 12 + 90)
    m = np.ones((90, 1))
    s, o = F.seasonality(m, mi, int(mi[-1]) + 1)
    assert np.isnan(s[0])  # only lags 72 and 84 exist


def test_beta_tail_recovers_slope():
    rng = np.random.default_rng(0)
    te = rng.normal(size=100)
    y = (2.0 * te + 0.01 * rng.normal(size=100))[:, None]
    b = F.beta_tail(y, te)
    assert abs(b[-1, 0] - 2.0) < 0.05 and np.isnan(b[10, 0])


def test_events_point_in_time_and_cash_ratio():
    rows = [
        ("total_assets", "instant", "2021-03-31", 100.0, "2021-05-05"),
        ("cash_sti", "instant", "2021-03-31", 25.0, "2021-05-05"),
        ("total_assets", "instant", "2021-06-30", 200.0, "2021-08-05"),
    ]
    ev = pd.DataFrame(F.cik_events(1, _facts(rows)))
    first = ev[ev["T"] == pd.Timestamp("2021-05-05")].iloc[0]
    assert abs(first["Cash"] - 0.25) < 1e-12
    second = ev[ev["T"] == pd.Timestamp("2021-08-05")].iloc[0]
    assert pd.isna(second.get("Cash"))  # the later total assets have no matching cash: no stale mix


def test_pctacc_and_roaq():
    rows = [
        ("net_income", "FY", "2020-12-31", 10.0, "2021-02-20"),
        ("operating_cash_flow", "FY", "2020-12-31", 4.0, "2021-02-20"),
        ("total_assets", "instant", "2020-09-30", 50.0, "2020-11-05"),
        ("net_income", "Q", "2020-12-31", 2.5, "2021-02-20"),
    ]
    ev = pd.DataFrame(F.cik_events(1, _facts(rows)))
    last = ev.iloc[-1]
    assert abs(last["PctAcc"] - 0.6) < 1e-12
    assert abs(last["roaq"] - 0.05) < 1e-12


def _lane_mod():
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "t18lane", root / "scripts/screen_batches/t20261006_18_library_lane.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_lane_rules_do_not_look_ahead():
    m = _lane_mod()
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2018-01-01", periods=600)
    px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 600))), index=idx)
    for fn in (m.dynbrk_position, m.ichimoku_position):
        full = fn(px)
        cut = fn(px.iloc[:400])
        assert (full.iloc[:400].to_numpy() == cut.to_numpy()).all()


def test_tom_dates():
    m = _lane_mod()
    idx = pd.bdate_range("2024-01-01", "2024-04-30")
    ent = m.tom_entries(idx)
    assert pd.Timestamp("2024-01-30") in ent  # session before Jan 31
    ex = m.tom_exits(idx, 4)
    assert pd.Timestamp("2024-02-06") in ex  # 4th session of February
