"""Tests for T-20260928-15's Claude-authored factor batch
(scripts/build_h20260928_15_claude_factors.py).

Three things are checked, all against the *exact* functions the full build
runs (never a reimplementation):

1. A PIT shift test: adding a later trade_date's rows to the toy panel must
   not change an earlier trade_date's computed factor value (each formula
   ranks strictly within its own trade_date partition).
2. Each Round-1 formula produces the hand-computed value on a small toy
   panel (registered under the same view names ``register_sources`` would
   create from parquet, so the same SQL runs in the test and in the full
   build).
3. ``candidate-manifest.json``'s ``code_sha256`` per candidate matches
   ``hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()`` for the
   function it names -- catches code/manifest drift.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

build = importlib.import_module("scripts.build_h20260928_15_claude_factors")

MANIFEST_PATH = (
    ROOT
    / "reports"
    / "research"
    / "iterations"
    / "h20260928_15_claude_factor_batch"
    / "candidate-manifest.json"
)


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET memory_limit='400MB'")
    return con


def _register(con: duckdb.DuckDBPyConnection, **tables: pd.DataFrame) -> None:
    for name, df in tables.items():
        con.register(name, df)


def _toy_insider() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC", "DDD"],
            "trade_date": pd.to_datetime(["2024-01-02"] * 4),
            "net_buy_usd_60d": [100.0, -50.0, 0.0, 200.0],
            "opportunistic_buy_60d": [3.0, 0.0, 1.0, 5.0],
            "routine_buy_60d": [0.0, 2.0, 1.0, 0.0],
        }
    )


def _toy_short_interest() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC", "DDD"],
            "trade_date": pd.to_datetime(["2024-01-02"] * 4),
            "dtc_change_vs_prior": [-1.0, 0.5, 2.0, -0.2],
        }
    )


def _toy_daily() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC", "DDD"],
            "trade_date": pd.to_datetime(["2024-01-02"] * 4),
            "trade_count_5d_mean": [500.0, 100.0, 300.0, 900.0],
            "trade_count_21d_mean": [200.0, 200.0, 300.0, 300.0],
            "momentum_252_21": [0.10, -0.05, 0.20, 0.01],
            "amihud_intraday_5d_mean": [1.0, 4.0, 2.0, 0.5],
            "amihud_intraday_21d_mean": [2.0, 2.0, 2.0, 2.0],
        }
    )


def _toy_fundamentals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC", "DDD"],
            "trade_date": pd.to_datetime(["2024-01-02"] * 4),
            "sue_eps": [1.5, -0.5, 0.2, 2.0],
            "gross_profitability": [0.3, 0.1, 0.25, 0.05],
            "accruals": [-0.02, 0.05, -0.01, 0.03],
            "operating_cash_flow": [50.0, 5.0, 20.0, -10.0],
            "net_income": [40.0, 4.0, 18.0, -20.0],
            "total_assets": [1000.0, 500.0, 800.0, 300.0],
            "days_since_report": [3.0, 20.0, 8.0, 45.0],
            "roe": [0.20, 0.05, 0.15, -0.10],
        }
    )


def _toy_short_volume() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC", "DDD"],
            "trade_date": pd.to_datetime(["2024-01-02"] * 4),
            "short_volume_ratio_zscore_21": [2.0, -1.0, 0.5, -0.3],
        }
    )


# --------------------------------------------------------------- PIT shift test


def test_pit_no_future_leak_across_trade_dates() -> None:
    """Adding a later day's extreme rows must not change an earlier day's
    computed value: each formula ranks strictly within PARTITION BY
    trade_date, never across days."""
    con = _con()
    insider_day1 = _toy_insider()
    short_int_day1 = _toy_short_interest()
    _register(con, insider=insider_day1, short_interest=short_int_day1)
    before = build.f01_insider_short_confluence(con).sort_values("symbol").reset_index(drop=True)

    con2 = _con()
    future_insider = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC", "DDD"],
            "trade_date": pd.to_datetime(["2024-01-03"] * 4),
            # Deliberately extreme/reversed values on the later day.
            "net_buy_usd_60d": [-9999.0, 9999.0, -9999.0, 9999.0],
        }
    )
    future_short_int = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC", "DDD"],
            "trade_date": pd.to_datetime(["2024-01-03"] * 4),
            "dtc_change_vs_prior": [99.0, -99.0, 99.0, -99.0],
        }
    )
    insider_both = pd.concat([insider_day1, future_insider], ignore_index=True)
    short_int_both = pd.concat([short_int_day1, future_short_int], ignore_index=True)
    _register(con2, insider=insider_both, short_interest=short_int_both)
    after = build.f01_insider_short_confluence(con2)
    after_day1 = (
        after[after["trade_date"] == pd.Timestamp("2024-01-02")]
        .sort_values("symbol")
        .reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(before, after_day1)
    con.close()
    con2.close()


# ------------------------------------------------------------ toy-panel formulas


def test_f01_insider_short_confluence_toy_panel() -> None:
    con = _con()
    _register(con, insider=_toy_insider(), short_interest=_toy_short_interest())
    out = build.f01_insider_short_confluence(con).set_index("symbol")["value"]
    con.close()
    # net_buy_usd_60d ranks (pct, ascending): CCC(0)<BBB(-50) actually order by
    # value ascending: BBB(-50) < CCC(0) < AAA(100) < DDD(200)
    # PERCENT_RANK over 4 rows: positions 0,1,2,3 -> 0, 1/3, 2/3, 1
    # buy_rank: BBB=0, CCC=1/3, AAA=2/3, DDD=1
    # -dtc_change_vs_prior ascending order: CCC(-2.0) < DDD(0.2) < AAA(1.0) < BBB(-0.5)
    #   values of -dtc: AAA=1.0, BBB=-0.5, CCC=-2.0, DDD=0.2
    #   ascending: CCC(-2.0) < BBB(-0.5) < DDD(0.2) < AAA(1.0)
    #   cover_rank: CCC=0, BBB=1/3, DDD=2/3, AAA=1
    expected = {
        "AAA": 0.5 * (2 / 3) + 0.5 * 1.0,
        "BBB": 0.5 * 0.0 + 0.5 * (1 / 3),
        "CCC": 0.5 * (1 / 3) + 0.5 * 0.0,
        "DDD": 0.5 * 1.0 + 0.5 * (2 / 3),
    }
    for sym, val in expected.items():
        assert out[sym] == pytest.approx(val), sym


def test_f02_opportunistic_insider_signal_sign() -> None:
    con = _con()
    _register(con, insider=_toy_insider())
    out = build.f02_opportunistic_insider_signal(con).set_index("symbol")["value"]
    con.close()
    # DDD has the highest opportunistic_buy_60d (5) and zero routine -> highest value.
    # BBB has zero opportunistic and highest routine (2) -> lowest value.
    assert out["DDD"] > out["AAA"] > out["CCC"] > out["BBB"]


def test_f03_trading_activity_surge_ratio() -> None:
    con = _con()
    _register(con, daily=_toy_daily())
    out = build.f03_trading_activity_surge(con).set_index("symbol")["value"]
    con.close()
    assert out["AAA"] == pytest.approx(500.0 / 200.0)
    assert out["DDD"] == pytest.approx(900.0 / 300.0)
    assert out["DDD"] > out["AAA"] > out["CCC"] > out["BBB"]


def test_f04_sue_short_confirmation_high_sue_low_short_wins() -> None:
    con = _con()
    _register(con, fundamentals=_toy_fundamentals(), short_volume=_toy_short_volume())
    out = build.f04_sue_short_confirmation(con).set_index("symbol")["value"]
    con.close()
    # DDD: highest SUE (2.0) and low-ish short pressure (-0.3) -> should score highest.
    assert out["DDD"] == out.max()
    # BBB: negative SUE and negative short pressure (low) -- AAA has highest
    # SUE but also the highest short pressure (2.0, fully opposing) so AAA
    # should not be the top-ranked despite the highest raw SUE.
    assert out["AAA"] < out["DDD"]


def test_f05_quality_liquidity_trend_toy_panel() -> None:
    con = _con()
    _register(con, fundamentals=_toy_fundamentals(), daily=_toy_daily())
    out = build.f05_quality_liquidity_trend(con).set_index("symbol")["value"]
    con.close()
    # AAA: high gross_profitability (0.3) and improving liquidity (ratio 1.0/2.0=0.5, low)
    assert out["AAA"] == out.max()
    # BBB: low gross_profitability (0.1) and worsening liquidity (ratio 4.0/2.0=2.0, high)
    assert out["BBB"] == out.min()


def test_f06_momentum_short_confirmation_toy_panel() -> None:
    con = _con()
    _register(con, daily=_toy_daily(), short_volume=_toy_short_volume())
    out = build.f06_momentum_short_confirmation(con).set_index("symbol")["value"]
    con.close()
    # CCC: highest momentum (0.20) and moderate short pressure (0.5, not highest)
    assert out["CCC"] == out.max()
    # BBB: lowest momentum (-0.05) -- should not be the top even though short
    # pressure is negative (low), since momentum dominates on this toy panel.
    assert out["BBB"] < out["CCC"]


def test_f07_accruals_cashflow_confirmation_toy_panel() -> None:
    con = _con()
    _register(con, fundamentals=_toy_fundamentals())
    out = build.f07_accruals_cashflow_confirmation(con).set_index("symbol")["value"]
    con.close()
    # AAA: low (negative) accruals (-0.02) and strong cash conversion (50/40=1.25)
    assert out["AAA"] == out.max()
    # DDD has negative net_income; the divisor clip (>= 1% of total_assets)
    # must keep cash_conversion finite, not raise or produce inf/NaN.
    assert pd.notna(out["DDD"])


def test_f07_zero_net_income_does_not_divide_by_zero() -> None:
    """Guards the outlier-control design choice (fixed before any IC was
    computed): a zero net_income must not produce inf/NaN via a plain
    division; GREATEST(ABS(net_income), 0.01*total_assets) clips the
    divisor away from zero."""
    con = _con()
    toy = _toy_fundamentals().copy()
    toy.loc[toy["symbol"] == "AAA", "net_income"] = 0.0
    _register(con, fundamentals=toy)
    out = build.f07_accruals_cashflow_confirmation(con).set_index("symbol")["value"]
    con.close()
    assert pd.notna(out["AAA"]) and abs(out["AAA"]) != float("inf")


def test_f08_earnings_recency_gate_excludes_stale_reports() -> None:
    con = _con()
    _register(con, insider=_toy_insider(), fundamentals=_toy_fundamentals())
    out = build.f08_earnings_recency_gated_insider_buying(con)
    con.close()
    symbols = set(out["symbol"])
    # AAA (3d), CCC (8d) are within the 10-day gate; BBB (20d), DDD (45d) are not.
    assert symbols == {"AAA", "CCC"}


# ----------------------------------------------------------- Round-2 toy formulas


def test_f09_insider_short_confluence_dollar_weighted_toy_panel() -> None:
    con = _con()
    _register(con, insider=_toy_insider(), short_interest=_toy_short_interest())
    out = build.f09_insider_short_confluence_dollar_weighted(con).set_index("symbol")["value"]
    con.close()
    # Same ranks as F01 (buy_rank: BBB=0,CCC=1/3,AAA=2/3,DDD=1;
    # cover_rank: CCC=0,BBB=1/3,DDD=2/3,AAA=1) but reweighted 0.7/0.3 in favor
    # of the dollar-buy component. Under F01's 0.5/0.5 weights AAA and DDD
    # tie (both 0.8333); shifting weight toward buy_rank must break that tie
    # in DDD's favor (buy_rank=1 for DDD vs 2/3 for AAA).
    expected = {
        "AAA": 0.7 * (2 / 3) + 0.3 * 1.0,
        "BBB": 0.7 * 0.0 + 0.3 * (1 / 3),
        "CCC": 0.7 * (1 / 3) + 0.3 * 0.0,
        "DDD": 0.7 * 1.0 + 0.3 * (2 / 3),
    }
    for sym, val in expected.items():
        assert out[sym] == pytest.approx(val), sym
    assert out["DDD"] > out["AAA"]


def test_f10_quality_composite_roe_profitability_accruals_toy_panel() -> None:
    con = _con()
    _register(con, fundamentals=_toy_fundamentals())
    out = build.f10_quality_composite_roe_profitability_accruals(con).set_index("symbol")["value"]
    con.close()
    # roe ascending: DDD(-0.10)=0, BBB(0.05)=1/3, CCC(0.15)=2/3, AAA(0.20)=1
    # gross_profitability ascending: DDD(0.05)=0, BBB(0.1)=1/3, CCC(0.25)=2/3, AAA(0.3)=1
    # -accruals ascending: BBB(-0.05->rank of -accruals uses accruals=0.05)=0,
    #   DDD(accruals=0.03)=1/3, CCC(accruals=-0.01)=2/3, AAA(accruals=-0.02)=1
    expected = {
        "AAA": (1.0 + 1.0 + 1.0) / 3.0,
        "BBB": ((1 / 3) + (1 / 3) + 0.0) / 3.0,
        "CCC": ((2 / 3) + (2 / 3) + (2 / 3)) / 3.0,
        "DDD": (0.0 + 0.0 + (1 / 3)) / 3.0,
    }
    for sym, val in expected.items():
        assert out[sym] == pytest.approx(val), sym
    assert out["AAA"] == out.max()
    assert out["DDD"] == out.min()


def test_f11_momentum_activity_surge_confirmation_toy_panel() -> None:
    con = _con()
    _register(con, daily=_toy_daily())
    out = build.f11_momentum_activity_surge_confirmation(con).set_index("symbol")["value"]
    con.close()
    # trade_count ratio (5d/21d): AAA=2.5, BBB=0.5, CCC=1.0, DDD=3.0
    # surge_rank ascending: BBB=0, CCC=1/3, AAA=2/3, DDD=1
    # momentum_252_21 ascending: BBB=0, DDD=1/3, AAA=2/3, CCC=1
    # BBB is last on both ingredients -> unique minimum.
    assert out["BBB"] == out.min()
    assert out["AAA"] > out["BBB"]
    assert out["CCC"] > out["BBB"]
    assert out["DDD"] > out["BBB"]


def test_f12_post_earnings_insider_buying_bad_news_gate_toy_panel() -> None:
    con = _con()
    insider = pd.DataFrame(
        {
            "symbol": ["WWW", "XXX", "YYY", "ZZZ"],
            "trade_date": pd.to_datetime(["2024-01-02"] * 4),
            "net_buy_usd_60d": [10.0, 20.0, 30.0, 40.0],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "symbol": ["WWW", "XXX", "YYY", "ZZZ"],
            "trade_date": pd.to_datetime(["2024-01-02"] * 4),
            "sue_eps": [-1.0, -1.0, 1.0, -1.0],
            "days_since_report": [5.0, 20.0, 5.0, 9.0],
        }
    )
    _register(con, insider=insider, fundamentals=fundamentals)
    out = build.f12_post_earnings_insider_buying_bad_news_gate(con)
    con.close()
    symbols = set(out["symbol"])
    # WWW: bad news (sue<0) and recent (5d) -> passes.
    # XXX: bad news but stale (20d) -> excluded.
    # YYY: recent but good news (sue>0) -> excluded (gate requires bad news).
    # ZZZ: bad news and recent (9d) -> passes.
    assert symbols == {"WWW", "ZZZ"}
    out_by_symbol = out.set_index("symbol")["value"]
    assert out_by_symbol["WWW"] == pytest.approx(10.0)
    assert out_by_symbol["ZZZ"] == pytest.approx(40.0)


# ------------------------------------------------------------- manifest hash test


def test_candidate_manifest_code_sha256_matches_source() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["candidate_count"] == len(manifest["candidates"]) == 12
    for candidate in manifest["candidates"]:
        fn_name = candidate["parameters"]["code_function"].rsplit(".", 1)[-1]
        fn = getattr(build, fn_name)
        expected = hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()
        assert candidate["parameters"]["code_sha256"] == expected, candidate["candidate_id"]


def test_round1_and_round2_dicts_match_manifest_ids() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_ids = {c["candidate_id"] for c in manifest["candidates"]}
    assert set(build.ROUND1) | set(build.ROUND2) == manifest_ids
    assert set(build.ROUND1).isdisjoint(build.ROUND2)
