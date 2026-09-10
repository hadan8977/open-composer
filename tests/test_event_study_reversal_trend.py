"""Tests for scripts/event_study_reversal_trend.py.

Focused on the statistical core (date-grouping/accumulation, the
date-clustered t-stat, the placebo Monte Carlo, and the informative-criterion
gate) with small hand-computable synthetic frames -- not the file-path-driven
``main()``/``_load_year_merged`` integration, which would need a fake SIP
archive and is mostly a thin composition of already-tested
``build_labels``/``reversal_trend_daily`` functions.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from scripts import event_study_reversal_trend as event_study


def _make_bucket() -> event_study._Bucket:
    return event_study._Bucket()


def test_windows_containing_membership() -> None:
    assert event_study._windows_containing(2017) == []
    assert event_study._windows_containing(2018) == ["2018_2026"]
    assert event_study._windows_containing(2023) == ["2018_2026"]
    assert event_study._windows_containing(2024) == ["2018_2026", "2024_onward"]
    assert event_study._windows_containing(2026) == ["2018_2026", "2024_onward"]
    # "2018_2026" is capped at 2026-12-31, but "2024_onward" has end=None --
    # deliberately open-ended ("2024→" per the plan), so it must still
    # include any year after 2026, not just 2024-2026.
    assert event_study._windows_containing(2027) == ["2024_onward"]


def _group_for_date(date: pd.Timestamp, rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["trade_date"] = date
    for signal in event_study.REVERSAL_TREND_SIGNAL_COLUMNS:
        if signal not in frame.columns:
            frame[signal] = 0.0
    # _process_date_group iterates every HORIZONS entry for every signal
    # (real label frames always have all of them, from one build_labels
    # call with horizons=HORIZONS) -- fill in whichever ones a test didn't
    # explicitly set as NaN, not missing, so they're skipped the same way a
    # real embargoed/edge-of-archive row would be.
    for horizon in event_study.HORIZONS:
        column = f"label_excess_{horizon}"
        if column not in frame.columns:
            frame[column] = float("nan")
    return frame


def test_process_date_group_and_summarize_match_hand_computation() -> None:
    rng = np.random.default_rng(0)
    buckets: dict = {
        ("w", "rt_bull_signal", 5): _make_bucket(),
    }
    signal = "rt_bull_signal"
    horizon = 5
    col = f"label_excess_{horizon}"

    # Date 1: two firing symbols (values 0.02, 0.04 -> mean 0.03), three
    # non-firing (pool for placebo).
    day1 = _group_for_date(
        pd.Timestamp("2024-01-02"),
        [
            {"symbol": "AAA", signal: 1.0, col: 0.02},
            {"symbol": "BBB", signal: 1.0, col: 0.04},
            {"symbol": "CCC", signal: 0.0, col: -0.01},
            {"symbol": "DDD", signal: 0.0, col: 0.00},
            {"symbol": "EEE", signal: 0.0, col: 0.01},
        ],
    )
    # Date 2: one firing symbol (value -0.02).
    day2 = _group_for_date(
        pd.Timestamp("2024-01-03"),
        [
            {"symbol": "FFF", signal: 1.0, col: -0.02},
            {"symbol": "GGG", signal: 0.0, col: 0.03},
        ],
    )

    event_study._process_date_group(day1["trade_date"].iloc[0], day1, rng, buckets, ["w"])
    event_study._process_date_group(day2["trade_date"].iloc[0], day2, rng, buckets, ["w"])

    bucket = buckets[("w", signal, horizon)]
    assert bucket.real_values == pytest.approx([0.02, 0.04, -0.02])
    assert bucket.placebo_n_dates == 2

    stats = event_study._summarize(bucket)
    assert stats["n_events"] == 3
    assert stats["n_dates"] == 2  # two distinct event dates
    assert stats["mean"] == pytest.approx((0.02 + 0.04 - 0.02) / 3)
    assert stats["median"] == pytest.approx(0.02)
    assert stats["hit_rate"] == pytest.approx(2 / 3)

    # Hand-compute the date-clustered t: per-date means are 0.03 (day1) and
    # -0.02 (day2).
    per_date_means = np.array([0.03, -0.02])
    expected_t = per_date_means.mean() / (per_date_means.std(ddof=1) / math.sqrt(2))
    assert stats["t_stat"] == pytest.approx(expected_t)
    assert stats["date_clustered_mean"] == pytest.approx(per_date_means.mean())


def test_placebo_distribution_mean_is_close_to_pool_mean() -> None:
    rng = np.random.default_rng(42)
    buckets: dict = {("w", "rt_bear_signal", 1): _make_bucket()}
    signal = "rt_bear_signal"
    horizon = 1
    col = f"label_excess_{horizon}"

    pool_values = np.linspace(-0.05, 0.05, 200)  # true mean 0.0
    rows = [{"symbol": "EVT", signal: 1.0, col: 0.10}]
    rows += [{"symbol": f"S{i}", signal: 0.0, col: float(v)} for i, v in enumerate(pool_values)]
    day = _group_for_date(pd.Timestamp("2024-06-03"), rows)

    event_study._process_date_group(day["trade_date"].iloc[0], day, rng, buckets, ["w"])
    bucket = buckets[("w", signal, horizon)]
    assert bucket.placebo_n_dates == 1
    placebo_distribution = bucket.placebo_sum / bucket.placebo_n_dates
    assert len(placebo_distribution) == event_study.N_PLACEBO_DRAWS
    # A single draw here samples 1 value (k_events=1) 1,000 times from a
    # pool with true mean 0 -- the distribution's own mean should land near
    # 0 (loose Monte Carlo tolerance, fixed seed keeps this deterministic).
    assert abs(placebo_distribution.mean()) < 0.01

    stats = event_study._summarize(bucket)
    # The real event (0.10) should sit far above the placebo's 95th
    # percentile, which is drawn from a +/-0.05 pool.
    assert stats["placebo_p95"] < 0.06
    assert stats["date_clustered_mean"] == pytest.approx(0.10)


def test_process_date_group_skips_placebo_when_no_non_firing_pool() -> None:
    rng = np.random.default_rng(1)
    buckets: dict = {("w", "rt_recl_signal", 10): _make_bucket()}
    signal = "rt_recl_signal"
    day = _group_for_date(
        pd.Timestamp("2024-02-01"),
        [
            {"symbol": "ONLY", signal: 1.0, f"label_excess_{10}": 0.01},
        ],
    )
    event_study._process_date_group(day["trade_date"].iloc[0], day, rng, buckets, ["w"])
    bucket = buckets[("w", signal, 10)]
    assert bucket.real_values == [0.01]
    assert bucket.placebo_n_dates == 0  # no non-firing symbols that date

    stats = event_study._summarize(bucket)
    assert math.isnan(stats["placebo_p95"])


def test_summarize_empty_bucket_returns_nan_safe_defaults() -> None:
    stats = event_study._summarize(_make_bucket())
    assert stats["n_events"] == 0
    assert math.isnan(stats["mean"])
    assert math.isnan(stats["t_stat"])
    assert math.isnan(stats["placebo_p95"])


def _stats(mean: float, t_stat: float, date_clustered_mean: float, placebo_p95: float) -> dict:
    return {
        "n_events": 10,
        "n_dates": 5,
        "mean": mean,
        "median": mean,
        "hit_rate": 0.6,
        "t_stat": t_stat,
        "placebo_p95": placebo_p95,
        "date_clustered_mean": date_clustered_mean,
    }


def test_is_informative_requires_every_condition_on_both_horizons() -> None:
    all_pass = {
        1: _stats(0.01, 3.0, 0.01, 0.001),
        5: _stats(0.02, 3.0, 0.02, 0.001),
        10: _stats(0.015, 3.0, 0.015, 0.001),
        21: _stats(0.01, 3.0, 0.01, 0.001),
    }
    assert event_study._is_informative(all_pass) is True

    fails_5d_mean = dict(all_pass)
    fails_5d_mean[5] = _stats(-0.01, 3.0, 0.02, 0.001)
    assert event_study._is_informative(fails_5d_mean) is False

    fails_10d_t = dict(all_pass)
    fails_10d_t[10] = _stats(0.015, 1.0, 0.015, 0.001)
    assert event_study._is_informative(fails_10d_t) is False

    fails_5d_placebo = dict(all_pass)
    fails_5d_placebo[5] = _stats(0.02, 3.0, 0.02, 0.05)  # placebo_p95 above the real mean
    assert event_study._is_informative(fails_5d_placebo) is False

    # NaN placebo_p95 (no pool ever available) must not raise and must not
    # count as "above" -- NaN comparisons are always False.
    nan_placebo = dict(all_pass)
    nan_placebo[5] = _stats(0.02, 3.0, 0.02, float("nan"))
    assert event_study._is_informative(nan_placebo) is False


def test_render_report_contains_window_and_signal_sections() -> None:
    stats_by_horizon = {h: _stats(0.01, 3.0, 0.01, 0.001) for h in event_study.HORIZONS}
    all_stats = {
        window_name: {
            signal: stats_by_horizon for signal in event_study.REVERSAL_TREND_SIGNAL_COLUMNS
        }
        for window_name, _, _ in event_study.WINDOWS
    }
    report = event_study._render_report(all_stats)
    assert "# Reversal Trend event study" in report
    assert "## Window: 2018_2026" in report
    assert "## Window: 2024_onward" in report
    for signal in event_study.REVERSAL_TREND_SIGNAL_COLUMNS:
        assert f"### {signal} -- informative: YES" in report
