"""Tests for scripts/screen_factors.py.

Covers the statistical core in isolation (window stats, sign stability,
Benjamini-Hochberg, the rank-correlation dedup) with hand-computable
synthetic data, plus one integration test of ``_process_library_year``
against tiny synthetic parquet files (monkeypatched roots) exercising the
IC accumulation, missing-rate, and rank-autocorrelation bookkeeping
together. ``main()`` itself (the full multi-year, multi-library, real-
archive run) is not exercised here -- it is mostly composition of these
already-tested pieces plus file I/O against the real, multi-GB archive.
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import screen_factors as sf


def test_window_stats_full_and_recent_slices() -> None:
    # 5 dates before, 5 on/after the 2024-01-02 recent-window boundary.
    dates = pd.DatetimeIndex(
        [
            "2023-10-06",
            "2023-10-13",
            "2023-10-20",
            "2023-10-27",
            "2023-11-03",
            "2024-01-05",
            "2024-01-12",
            "2024-01-19",
            "2024-01-26",
            "2024-02-02",
        ]
    )
    values = [0.01, 0.02, -0.01, 0.03, 0.02, 0.04, 0.05, 0.03, 0.06, 0.04]
    full = sf._window_stats(list(dates), values, start=None)
    assert full["n"] == 10
    assert full["ic_mean"] == pytest.approx(np.mean(values))
    assert full["ic_std"] == pytest.approx(np.std(values, ddof=1))
    assert full["icir"] == pytest.approx(full["ic_mean"] / full["ic_std"])
    assert full["t"] == pytest.approx(full["icir"] * math.sqrt(10))

    recent = sf._window_stats(list(dates), values, start=pd.Timestamp("2024-01-02"))
    recent_mask = dates >= pd.Timestamp("2024-01-02")
    expected_values = np.array(values)[recent_mask]
    assert recent["n"] == recent_mask.sum()
    assert recent["ic_mean"] == pytest.approx(expected_values.mean())


def test_window_stats_too_few_observations_is_nan_safe() -> None:
    stats = sf._window_stats([pd.Timestamp("2024-01-05")], [0.02], start=None)
    assert stats["n"] == 1
    assert math.isnan(stats["ic_mean"])
    assert math.isnan(stats["t"])


def test_sign_stability_matches_hand_computation() -> None:
    dates = [
        pd.Timestamp("2022-03-01"),
        pd.Timestamp("2022-09-01"),
        pd.Timestamp("2023-03-01"),
        pd.Timestamp("2023-09-01"),
        pd.Timestamp("2024-03-01"),
    ]
    # per-year means: 2022 -> (0.01-0.03)/2 = -0.01 (negative);
    # 2023 -> (0.02+0.04)/2 = 0.03 (positive); 2024 -> 0.05 (positive).
    # full_sample_sign positive -> 2/3 years match.
    values = [0.01, -0.03, 0.02, 0.04, 0.05]
    stability = sf._sign_stability(dates, values, full_sample_sign=1.0)
    assert stability == pytest.approx(2 / 3)


def test_benjamini_hochberg_matches_hand_worked_example() -> None:
    p_values = np.array([0.005, 0.01, 0.03, 0.04, 0.2])
    passing = sf._benjamini_hochberg(p_values, q=0.05)
    # thresholds = [0.01, 0.02, 0.03, 0.04, 0.05]; sorted p <= threshold for
    # the first 4 (0.005,0.01,0.03,0.04), fails at the 5th (0.2 > 0.05).
    np.testing.assert_array_equal(passing, [True, True, True, True, False])


def test_benjamini_hochberg_handles_unsorted_input_and_nan() -> None:
    p_values = np.array([0.04, np.nan, 0.005, 0.2, 0.01, 0.03])
    passing = sf._benjamini_hochberg(p_values, q=0.05)
    np.testing.assert_array_equal(passing, [True, False, True, False, True, True])


def test_benjamini_hochberg_all_fail_when_nothing_below_threshold() -> None:
    p_values = np.array([0.5, 0.6, 0.9])
    passing = sf._benjamini_hochberg(p_values, q=0.05)
    assert not passing.any()


def _wide_panel(dates: list[pd.Timestamp], symbols: list[str], values: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(values, index=pd.DatetimeIndex(dates), columns=symbols)


def test_dedupe_by_rank_correlation_drops_near_duplicate_keeps_distinct() -> None:
    dates = pd.date_range("2025-01-03", periods=6, freq="7D")
    symbols = [f"S{i}" for i in range(30)]
    rng = np.random.default_rng(0)
    base = rng.normal(size=(6, 30))
    # factor_b is a monotone (and therefore rank-identical) transform of
    # factor_a -- a textbook near-duplicate; factor_c is independent noise.
    factor_a = base
    factor_b = base * 3.0 + 1.0
    factor_c = rng.normal(size=(6, 30))

    candidates = pd.DataFrame(
        [
            {"library": "lib", "factor": "a", "icir_recent": 0.30, "fdr_pass": True},
            {"library": "lib", "factor": "b", "icir_recent": 0.25, "fdr_pass": True},
            {"library": "lib", "factor": "c", "icir_recent": 0.20, "fdr_pass": False},
        ]
    )
    value_lookup = {
        ("lib", "a"): _wide_panel(list(dates), symbols, factor_a),
        ("lib", "b"): _wide_panel(list(dates), symbols, factor_b),
        ("lib", "c"): _wide_panel(list(dates), symbols, factor_c),
    }
    kept = sf._dedupe_by_rank_correlation(candidates, value_lookup, threshold=0.9)
    kept_factors = set(kept["factor"])
    assert "a" in kept_factors  # highest icir_recent, always kept
    assert "b" not in kept_factors  # near-duplicate of a, dropped
    assert "c" in kept_factors  # independent, kept


def test_dedupe_by_rank_correlation_respects_top_n_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sf, "TOP_N", 2)
    dates = pd.date_range("2025-01-03", periods=4, freq="7D")
    symbols = [f"S{i}" for i in range(10)]
    rng = np.random.default_rng(1)
    candidates = pd.DataFrame(
        [
            {"library": "lib", "factor": f, "icir_recent": 1.0 - 0.1 * i, "fdr_pass": True}
            for i, f in enumerate(["a", "b", "c", "d"])
        ]
    )
    value_lookup = {
        ("lib", f): _wide_panel(list(dates), symbols, rng.normal(size=(4, 10)))
        for f in ["a", "b", "c", "d"]
    }
    kept = sf._dedupe_by_rank_correlation(candidates, value_lookup, threshold=0.9)
    assert len(kept) == 2


@pytest.fixture
def synthetic_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    features_root = tmp_path / "features"
    labels_root = features_root / "labels"
    lib_root = features_root / "toylib"
    labels_root.mkdir(parents=True)
    lib_root.mkdir(parents=True)

    dates = pd.bdate_range("2024-01-02", periods=15)  # 3 Fridays inside
    symbols = [f"SYM{i}" for i in range(20)]
    rng = np.random.default_rng(7)

    lib_rows = []
    label_rows = []
    for date in dates:
        for symbol in symbols:
            factor1 = rng.normal()
            lib_rows.append({"symbol": symbol, "trade_date": date, "factor1": factor1})
            label_rows.append(
                {
                    "symbol": symbol,
                    "trade_date": date,
                    "label_excess_5": factor1 * 0.02 + rng.normal(scale=0.01),
                    "label_excess_10": rng.normal(scale=0.01),
                }
            )
    pd.DataFrame(lib_rows).to_parquet(lib_root / "2024.parquet", index=False)
    pd.DataFrame(label_rows).to_parquet(labels_root / "2024.parquet", index=False)

    universe_panel = pd.DataFrame(
        {
            "month_end": [pd.Timestamp("2023-12-29")] * len(symbols),
            "symbol": symbols,
            "adv_rank": list(range(1, len(symbols) + 1)),
            "dollar_adv": [1_000_000.0] * len(symbols),
            "close": [50.0] * len(symbols),
        }
    )

    monkeypatch.setattr(sf, "FEATURES_ROOT", features_root)
    monkeypatch.setattr(sf, "LABELS_ROOT", labels_root)
    return {"universe_panel": universe_panel, "dates": dates, "symbols": symbols}


def test_process_library_year_accumulates_ic_missing_and_autocorr(synthetic_archive: dict) -> None:
    ic_acc: dict = defaultdict(sf._FactorAccumulator)
    autocorr_acc: dict = defaultdict(sf._RankAutocorrAccumulator)
    missing_acc: dict = defaultdict(sf._MissingAccumulator)

    sf._process_library_year(
        "toylib",
        2024,
        ["factor1"],
        synthetic_archive["universe_panel"],
        ic_acc,
        autocorr_acc,
        missing_acc,
    )

    key = ("toylib", "factor1", "label_excess_5")
    assert key in ic_acc
    bucket = ic_acc[key]
    assert len(bucket.ic_values) >= 2  # at least 2 Fridays in a 15-bday January window
    # factor1 was constructed to positively drive label_excess_5 -- IC should
    # skew positive on average (loose statistical check, not exact).
    assert np.mean(bucket.ic_values) > 0

    other_key = ("toylib", "factor1", "label_excess_10")
    assert (
        other_key in ic_acc
    )  # label_excess_10 is pure noise but should still produce an IC series

    missing_key = ("toylib", "factor1")
    assert missing_acc[missing_key].total > 0
    assert missing_acc[missing_key].missing == 0  # no NaNs injected in this fixture

    autocorr = autocorr_acc.get(missing_key)
    assert autocorr is not None
    assert autocorr.n_pairs >= 1  # at least one consecutive-Friday pair


def test_process_library_year_skips_years_with_no_data(synthetic_archive: dict) -> None:
    ic_acc: dict = defaultdict(sf._FactorAccumulator)
    autocorr_acc: dict = defaultdict(sf._RankAutocorrAccumulator)
    missing_acc: dict = defaultdict(sf._MissingAccumulator)
    sf._process_library_year(
        "toylib",
        2099,
        ["factor1"],
        synthetic_archive["universe_panel"],
        ic_acc,
        autocorr_acc,
        missing_acc,
    )
    assert ic_acc == {}
    assert autocorr_acc == {}
    assert missing_acc == {}
