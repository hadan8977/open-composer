"""Synthetic-series tests for scripts/eval_book_v1_stage2.py (T-20261001-13)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import eval_book_v1_stage2 as e  # noqa: E402

from open_composer.research.equity_book import evaluate as ev  # noqa: E402


def _idx(n: int = 400) -> pd.DatetimeIndex:
    return pd.bdate_range("2024-01-02", periods=n)


def test_dimson_beta_sums_lagged_slope() -> None:
    idx = _idx()
    rng = np.random.default_rng(1)
    spy = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    r = 0.5 * spy + 0.3 * spy.shift(1).fillna(0.0)
    b = e.dimson_beta(r, spy, ("2024-01-02", "2030-01-01"))
    assert abs(b - 0.8) < 1e-6
    # the plain daily beta only sees the contemporaneous slope (plus a small lag leakage)
    daily = ev.window_metrics(r, spy * 0.0 + 0.0 * spy, spy, ("2024-01-02", "2030-01-01"))[
        "beta_spy"
    ]
    assert daily < 0.65


def test_cash_aligned_is_net_minus_bil_plus_shy() -> None:
    idx = _idx(10)
    net = pd.Series(np.linspace(0.001, 0.002, 10), index=idx)
    bil = pd.Series(0.0001, index=idx)
    shy = pd.Series(0.0003, index=idx)
    out = e.cash_aligned(net, bil, shy)
    assert np.allclose(out.to_numpy(), (net - bil + shy).to_numpy())


def _med(
    anchor_sharpe=1.3,
    stress_sharpe=0.7,
    c2_anchor=0.05,
    c2_stress=0.04,
    k2f=(0.0, 0.0),
    k2c=(0.0, 0.0),
    beta=0.05,
    fail=0.0,
):
    def win(s, x):
        return {"sharpe": s, "ann_excess_return": x}

    return {
        "net": {"stress": win(stress_sharpe, 0.1), "anchor": win(anchor_sharpe, 0.1)},
        "cost2x": {"stress": win(0.5, c2_stress), "anchor": win(1.0, c2_anchor)},
        "k2_frozen": {"edge": {"stress": k2f[0], "anchor": k2f[1]}},
        "k2_cash_aligned": {"edge": {"stress": k2c[0], "anchor": k2c[1]}},
        "beta": {
            "daily": {"stress": beta, "anchor": beta},
            "dimson": {"stress": beta, "anchor": beta},
        },
        "failure": {"failure_rate": fail},
    }


def test_checks_use_median_not_offset_vote() -> None:
    # five offsets: anchor Sharpe 1.4 for three offsets, 0.5 for two -> median 1.4 passes the
    # K1 anchor bound although a mean-of-pass vote over (anchor, stress) pairs would be split.
    anchors = {0: 1.4, 1: 1.4, 2: 1.4, 3: 0.5, 4: 0.5}
    stress = {0: 0.5, 1: 0.5, 2: 0.9, 3: 0.9, 4: 0.9}
    med_a = ev.median_over_offsets(anchors)
    med_s = ev.median_over_offsets(stress)
    # only offset 2 passes both bounds on its own, yet both medians pass
    per_offset_pass = [anchors[k] >= 1.19 and stress[k] >= 0.65 for k in range(5)]
    assert sum(per_offset_pass) == 1
    ck = e.variant_checks(_med(anchor_sharpe=med_a, stress_sharpe=med_s))
    assert ck["k1"] is True
    # medians fail while two single offsets would pass -> check is False
    ck2 = e.variant_checks(
        _med(anchor_sharpe=ev.median_over_offsets({0: 1.4, 1: 1.4, 2: 0.2, 3: 0.2, 4: 0.2}))
    )
    assert ck2["k1"] is False and ck2["anchor_sharpe_ge_1_19"] is False


def test_median_nested_blocks() -> None:
    items = [{"a": {"x": float(v)}, "b": True} for v in (1, 100, 3, 2, 50)]
    out = e.median_nested(items)
    assert out == {"a": {"x": 3.0}}
    items[0]["a"]["x"] = float("nan")
    assert np.isnan(e.median_nested(items)["a"]["x"])


def test_k2_requires_both_calibrations() -> None:
    ck = e.variant_checks(_med(k2f=(0.06, 0.07), k2c=(0.06, 0.02)))
    assert ck["k2_frozen"] is True and ck["k2_cash_aligned"] is False
    assert ck["k2_strong"] is False
    ck = e.variant_checks(_med(k2f=(0.12, 0.11), k2c=(0.10, 0.10)))
    assert ck["k2_strong"] is True and ck["cond1"] is True


def test_needs_placebo_logic_and_ordering() -> None:
    assert e.needs_placebo(False, False) is False
    assert e.needs_placebo(True, False) is True
    assert e.needs_placebo(False, True) is True
    # cond1 failure and anchor < 1.19 -> no placebo
    ck = e.variant_checks(_med(anchor_sharpe=1.0, stress_sharpe=0.3))
    assert ck["needs_placebo"] is False
    # anchor >= 1.19 without cond1 -> placebo, no K1/K2
    ck = e.variant_checks(_med(anchor_sharpe=1.5, stress_sharpe=0.3))
    assert ck["cond1"] is False and ck["needs_placebo"] is True
    variants = {
        "A": {
            "checks": {"needs_placebo": True, "cond1": False},
            "median": {"net": {"anchor": {"sharpe": 2.0}}},
        },
        "B": {
            "checks": {"needs_placebo": True, "cond1": True},
            "median": {"net": {"anchor": {"sharpe": 1.0}}},
        },
        "C": {
            "checks": {"needs_placebo": False, "cond1": False},
            "median": {"net": {"anchor": {"sharpe": 3.0}}},
        },
        "D": {
            "checks": {"needs_placebo": True, "cond1": False},
            "median": {"net": {"anchor": {"sharpe": 1.5}}},
        },
    }
    assert e.order_placebo_needed(variants) == ["B", "A", "D"]


def test_failure_and_beta_gates() -> None:
    assert e.variant_checks(_med(fail=0.019))["failure_ok"] is True
    assert e.variant_checks(_med(fail=0.02))["failure_ok"] is False
    assert e.variant_checks(_med(beta=0.2))["beta_ok"] is False
    wr = e.variant_checks(_med(anchor_sharpe=1.3, beta=0.1))
    assert wr["watch_recent_pre_placebo"] is True
    assert (
        e.variant_checks(_med(anchor_sharpe=1.3, c2_anchor=-0.01))["watch_recent_pre_placebo"]
        is False
    )


def test_timing_flag_and_period_stats() -> None:
    assert e.timing_flag(0.2, 1.0) is True
    assert e.timing_flag(0.5, 1.0) is False
    assert e.timing_flag(-0.2, -1.0) is False
    idx = _idx(120)
    rng = np.random.default_rng(3)
    net = pd.Series(rng.normal(0.0005, 0.01, len(idx)), index=idx)
    rf = pd.Series(0.0, index=idx)
    spy = pd.Series(0.0, index=idx)
    a, b = str(idx[10].date()), str(idx[100].date())
    st = e.period_stats(net, rf, a, b)
    m = ev.window_metrics(net, rf, spy, (a, b))
    assert abs(st["sharpe"] - m["sharpe"]) < 1e-12
    short = e.period_stats(net, rf, str(idx[0].date()), str(idx[5].date()))
    assert short["short_sample"] is True and short["sessions"] == 6
