"""T-20261004-55 helpers: archive pointing, S3 policy variants, perturbation, parity option."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_eom_sector_blend_parity as parity  # noqa: E402
import paper_consistency_t55 as t55  # noqa: E402
import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402

GROWTH = {
    "TQQQ": 0.003,
    "SOXL": -0.001,
    "UPRO": -0.002,
    "USD": -0.003,
    "TECL": -0.004,
    "SHY": 0.0001,
    "QQQ": 0.001,
    "BIL": 0.0001,
}


def synthetic_panel(n: int = 420) -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.bdate_range("2020-01-01", periods=n)
    close = pd.DataFrame(
        {s: 100.0 * np.exp(g * np.arange(n)) for s, g in GROWTH.items()}, index=index
    )
    return close, close.shift(1).fillna(close.iloc[0])


def test_archive_globals_points_and_restores():
    saved = (base.DAILY_GLOB, base.WARMUP_START, base.HOLD_END)
    with t55.archive_globals("data/some-archive", "2015-01-02", "2026-09-17"):
        assert base.DAILY_GLOB.endswith("data/some-archive/*/*.parquet")
        assert Path(base.DAILY_GLOB).is_absolute()
        assert (base.WARMUP_START, base.HOLD_END) == ("2015-01-02", "2026-09-17")
    assert (base.DAILY_GLOB, base.WARMUP_START, base.HOLD_END) == saved


def test_cash_policy_keeps_dropped_slot_in_shy_and_renormalize_does_not():
    close, _ = synthetic_panel()
    renorm, dates = salvage.sleeve_weights(close, "s3")
    cash, cash_dates = t55.cash_policy_weights(close)
    assert dates == cash_dates
    late = close.index[-5]
    assert renorm.loc[late].to_dict()["TQQQ"] == 1.0
    assert cash.loc[late, "TQQQ"] == 0.5
    assert cash.loc[late, "SHY"] == 0.5
    assert np.allclose(cash.sum(axis=1), 1.0)
    # the two policies agree wherever both slots survive or none does
    both = renorm.index[(renorm.drop(columns="SHY") > 0).sum(axis=1) != 1]
    assert np.allclose(
        renorm.loc[both].reindex(columns=cash.columns, fill_value=0.0), cash.loc[both]
    )


def test_s3_book_matches_engine_run_cell():
    close, open_ = synthetic_panel()
    run = t55.s3_book(close, open_)
    leg_open, leg_close = salvage.legs(close, open_)
    boost = salvage.boost_window(salvage.dip_signal(close), t55.S3_BOOST_HOLD)
    ref, _ = salvage.run_cell(
        close,
        leg_open,
        leg_close,
        "s3",
        t55.S3_TARGET,
        base.COST_BPS_PRIMARY,
        boost=boost,
        boost_target=t55.S3_BOOST_TARGET,
    )
    assert np.allclose(run["ret"], ref)


def test_perturb_close_is_seeded_and_keeps_nan():
    close, _ = synthetic_panel(50)
    close.iloc[3, 2] = np.nan
    a = t55.perturb_close(close, 5.0, 7)
    b = t55.perturb_close(close, 5.0, 7)
    c = t55.perturb_close(close, 5.0, 8)
    assert a.equals(b) and not a.equals(c)
    assert np.isnan(a.iloc[3, 2])
    rel = (a / close - 1.0).stack()
    assert abs(rel.std() - 5e-4) < 1.5e-4


def test_parity_lane_returns_default_unchanged_and_option_parses():
    assert parity.parse_args([]).lane_returns == parity.LANE_RETURNS
    args = parity.parse_args(["--lane-returns", "x.parquet", "--out", "o.json"])
    assert (args.lane_returns, args.out) == ("x.parquet", "o.json")


def test_stored_window_sharpe_matches_lane_metrics():
    index = pd.bdate_range("2023-01-02", periods=300)
    rng = np.random.default_rng(1)
    ret = pd.Series(rng.normal(0.001, 0.01, len(index)), index=index)
    rf = pd.Series(0.00005, index=index)
    stored = pd.DataFrame({"C2__o00__net10": ret})
    window = ("2023-03-01", "2023-12-01")
    got = parity.stored_window_sharpe(stored, rf, pd.Timestamp("2023-01-02"), window)
    sub = ret.loc[window[0] : window[1]]
    excess = sub - rf.loc[sub.index]
    assert abs(got - excess.mean() / excess.std(ddof=1) * np.sqrt(252.0)) < 1e-12
