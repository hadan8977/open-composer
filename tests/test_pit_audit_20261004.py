from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_sec_xbrl_fundamentals as b  # noqa: E402
import pit_audit_20261004 as pa  # noqa: E402


def _ladder(n: int = 16, late: dict[int, str] | None = None):
    """qidx -> (usable_session, period_end, eps); quarter q is usable 40 days after its end, an
    entry in ``late`` is usable on the given date instead."""
    out = {}
    rng = np.random.default_rng(3)
    base = pd.Timestamp("2018-03-31")
    for q in range(n):
        end = base + pd.DateOffset(months=3 * q)
        use = end + pd.Timedelta(days=40)
        if late and q in late:
            use = pd.Timestamp(late[q])
        out[100 + q] = (use, end, float(rng.normal(1.0, 0.3) + 0.05 * q))
    return out


def test_in_order_ladder_matches_final():
    ladder = _ladder()
    final = b.sue_series(ladder)
    ev = pa.pit_ladder_events(ladder, b.sue_series)
    assert [(u, v) for _, u, v in ev] == [(u, v) for u, v in final]
    assert all(eff == own for eff, own, _ in ev)


def test_late_quarter_delays_every_sue_that_needs_it():
    # quarter 3 (a lag input of every t in 7..15 via t-4/k-4 chains) arrives a year late
    late_day = "2022-06-15"
    ladder = _ladder(late={3: late_day})
    final = b.sue_series(ladder)
    ev = pa.pit_ladder_events(ladder, b.sue_series)
    assert len(ev) == len(final)
    delayed = [e for e in ev if e[0] > e[1]]
    assert delayed, "a late input must delay at least one SUE"
    assert all(e[0] == pd.Timestamp(late_day) for e in delayed)
    # values are unchanged, only their effective date moves
    assert sorted(v for _, _, v in ev) == sorted(v for _, v in final)


def test_asof_values_latest_own_session_wins():
    d = pd.Timestamp
    events = [(d("2020-01-10"), d("2020-01-05"), 1.0), (d("2020-03-01"), d("2019-12-01"), 9.0)]
    idx = [d("2020-01-09"), d("2020-01-10"), d("2020-02-01"), d("2020-03-02")]
    got = pa.asof_values(idx, events)
    assert np.isnan(got[0])
    assert list(got[1:]) == [1.0, 1.0, 1.0]


def test_pit_asset_growth_waits_for_prior_year():
    d = pd.Timestamp
    rows = []
    for fy, usable, val in ((2019, "2020-03-01", 100.0), (2020, "2021-03-01", 120.0)):
        rows.append(
            {
                "concept": "total_assets",
                "fp": "FY",
                "fy": float(fy),
                "restated": False,
                "filed": d(usable) - pd.Timedelta(days=1),
                "usable_session": d(usable),
                "val": val,
            }
        )
    frame = pd.DataFrame(rows)
    ev = pa.pit_asset_growth_events(frame, b.asset_growth_events)
    assert len(ev) == 1 and abs(ev[0][2] - 0.2) < 1e-12 and ev[0][0] == d("2021-03-01")
    # the earlier year arrives after the later one: growth is computable only then
    frame.loc[0, "usable_session"] = d("2021-09-01")
    frame.loc[0, "filed"] = d("2021-08-31")
    ev = pa.pit_asset_growth_events(frame, b.asset_growth_events)
    assert len(ev) == 1 and ev[0][0] == d("2021-09-01")


def test_bucket_of_matches_sql_rounding():
    # boundaries observed in the snapshot (round half to even): 125 -> 0, 126 -> 1, 375 -> 2,
    # 625 -> 2, 626 -> 3, 875 -> 4
    got = pa.bucket_of(np.array([1, 125, 126, 249, 250, 375, 625, 626, 875, 4000]))
    assert list(got) == [0, 0, 1, 1, 1, 2, 2, 3, 4, 16]


def test_trailing_median_uses_only_past_sessions():
    # one bucket, 6 sessions, two rows each; a huge ratio on the last session must not move
    # the median of any earlier session
    di = np.repeat(np.arange(6), 2)
    bk = np.zeros(12, dtype="int64")
    ratio = np.array([1, 3, 2, 4, 3, 5, 4, 6, 5, 7, 1000, 2000], dtype="float64")
    k = pa.trailing_bucket_median(di, bk, ratio, 6, trail=3)
    assert k[0, 0] == 2.0  # no past: own session (1, 3)
    assert k[1, 0] == 2.0  # session 0 only
    assert k[2, 0] == np.median([1, 3, 2, 4])  # sessions 0-1
    assert k[3, 0] == np.median([1, 3, 2, 4, 3, 5])  # sessions 0-2
    assert k[4, 0] == np.median([2, 4, 3, 5, 4, 6])  # sessions 1-3 (trail = 3)
    assert k[5, 0] == np.median([3, 5, 4, 6, 5, 7])  # sessions 2-4, excludes the 1000s


def test_year_median_includes_the_future():
    di = np.array([0, 1, 2, 3])
    bk = np.zeros(4, dtype="int64")
    ratio = np.array([1.0, 1.0, 1.0, 100.0])
    year_of = np.array([2020, 2020, 2020, 2020])
    k = pa.year_bucket_median(year_of, di, bk, ratio, 4)
    assert k[0, 0] == 1.0 and k[3, 0] == 1.0
    ratio2 = np.array([1.0, 1.0, 100.0, 100.0])
    k2 = pa.year_bucket_median(year_of, di, bk, ratio2, 4)
    assert k2[0, 0] == 50.5  # the first session's ratio is set by later sessions
    kt = pa.trailing_bucket_median(di, bk, ratio2, 4, trail=252)
    assert kt[1, 0] == 1.0


def test_fallback_mcap_cases():
    close = np.array([10.0, 10.0, 10.0, 10.0])
    shares = np.array([1e6, np.nan, 1e6, 1e6])
    adv = np.array([1e5, 1e5, 1e5, 0.0])
    k_row = np.array([100.0, 100.0, 100.0, 100.0])
    mcap, src = pa.fallback_mcap(close, shares, adv, k_row)
    # row 0: ratio 10*1e6/1e5 = 100 inside the band -> sec
    assert src[0] == "sec" and mcap[0] == 1e7
    # row 1: no shares -> adv fallback k * adv
    assert src[1] == "adv_fallback" and mcap[1] == 1e7
    # row 2: with k = 1 the ratio 100 is outside [0.1, 10] -> outlier fallback
    m2, s2 = pa.fallback_mcap(close[2:3], shares[2:3], adv[2:3], np.array([1.0]))
    assert s2[0] == "adv_fallback_outlier" and m2[0] == 1e5
    # row 3: adv == 0 with shares -> close * shares
    assert src[3] == "sec" and mcap[3] == 1e7


def test_pit_cik_table_keeps_genuine_nan_of_existing_rows():
    d = pd.Timestamp
    final = pd.DataFrame(
        {
            "usable_session": [d("2020-01-02"), d("2020-02-03"), d("2020-03-02")],
            "cik": [1, 1, 1],
            "accruals": [0.1, np.nan, 0.3],
            "sue_eps": [np.nan, np.nan, np.nan],
            "sue_rev": [np.nan, np.nan, np.nan],
            "asset_growth": [np.nan, np.nan, np.nan],
        }
    )

    class FakeB:
        @staticmethod
        def _quarterly_dict(frame, concept):
            return {}

        @staticmethod
        def sue_series(q):
            return []

        @staticmethod
        def asset_growth_events(frame):
            return []

    frame = pd.DataFrame({"concept": [], "restated": [], "fp": [], "fy": [], "usable_session": []})
    got = pa.pit_cik_table(1, frame, FakeB, final=final)
    assert got["accruals"].isna().tolist() == [False, True, False]
