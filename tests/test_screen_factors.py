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


def test_chunked_splits_into_consecutive_slices_of_at_most_size() -> None:
    assert sf._chunked(["a", "b", "c", "d", "e"], 2) == [["a", "b"], ["c", "d"], ["e"]]
    assert sf._chunked(["a", "b"], 40) == [["a", "b"]]
    assert sf._chunked([], 40) == []


@pytest.fixture
def synthetic_archive_two_factors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Same shape as ``synthetic_archive`` but with two factor columns, so a
    ``FACTOR_CHUNK_SIZE`` of 1 actually forces multiple chunks -- needed to
    exercise the chunk-boundary-doesn't-change-results property below."""
    features_root = tmp_path / "features"
    labels_root = features_root / "labels"
    lib_root = features_root / "toylib2"
    labels_root.mkdir(parents=True)
    lib_root.mkdir(parents=True)

    dates = pd.bdate_range("2024-01-02", periods=15)
    symbols = [f"SYM{i}" for i in range(20)]
    rng = np.random.default_rng(11)

    lib_rows = []
    label_rows = []
    for date in dates:
        for symbol in symbols:
            factor1 = rng.normal()
            factor2 = rng.normal()
            lib_rows.append(
                {"symbol": symbol, "trade_date": date, "factor1": factor1, "factor2": factor2}
            )
            label_rows.append(
                {
                    "symbol": symbol,
                    "trade_date": date,
                    "label_excess_5": factor1 * 0.02 + rng.normal(scale=0.01),
                    "label_excess_10": factor2 * -0.02 + rng.normal(scale=0.01),
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
    return {"universe_panel": universe_panel}


def test_process_library_year_column_chunking_matches_unchunked_result(
    synthetic_archive_two_factors: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A chunk size smaller than the factor count must still accumulate the
    exact same IC/missing totals as one big chunk -- chunking is a memory
    optimization, not a change in what gets counted (autocorrelation is
    exempted: the 8-week sampling is a separate, disclosed approximation
    that does not depend on chunk size, so it is not compared here)."""
    columns = ["factor1", "factor2"]

    monkeypatch.setattr(sf, "FACTOR_CHUNK_SIZE", 1)  # forces 2 chunks (one factor each)
    ic_chunked: dict = defaultdict(sf._FactorAccumulator)
    missing_chunked: dict = defaultdict(sf._MissingAccumulator)
    sf._process_library_year(
        "toylib2",
        2024,
        columns,
        synthetic_archive_two_factors["universe_panel"],
        ic_chunked,
        defaultdict(sf._RankAutocorrAccumulator),
        missing_chunked,
    )

    monkeypatch.setattr(sf, "FACTOR_CHUNK_SIZE", 40)  # both factors in one chunk
    ic_unchunked: dict = defaultdict(sf._FactorAccumulator)
    missing_unchunked: dict = defaultdict(sf._MissingAccumulator)
    sf._process_library_year(
        "toylib2",
        2024,
        columns,
        synthetic_archive_two_factors["universe_panel"],
        ic_unchunked,
        defaultdict(sf._RankAutocorrAccumulator),
        missing_unchunked,
    )

    for factor in columns:
        for label in sf.LABEL_COLUMNS:
            key = ("toylib2", factor, label)
            assert ic_chunked[key].dates == ic_unchunked[key].dates
            assert ic_chunked[key].ic_values == pytest.approx(ic_unchunked[key].ic_values)
        missing_key = ("toylib2", factor)
        assert missing_chunked[missing_key].total == missing_unchunked[missing_key].total
        assert missing_chunked[missing_key].missing == missing_unchunked[missing_key].missing


def test_checkpoint_roundtrip_preserves_ic_autocorr_missing(tmp_path: Path) -> None:
    ic_acc: dict = defaultdict(sf._FactorAccumulator)
    ic_acc[("lib", "f1", "label_excess_5")].dates = [
        pd.Timestamp("2024-01-05"),
        pd.Timestamp("2024-01-12"),
    ]
    ic_acc[("lib", "f1", "label_excess_5")].ic_values = [0.1, -0.2]
    ic_acc[("lib", "f2", "label_excess_10")].dates = [pd.Timestamp("2024-01-05")]
    ic_acc[("lib", "f2", "label_excess_10")].ic_values = [0.05]

    autocorr_acc: dict = defaultdict(sf._RankAutocorrAccumulator)
    autocorr_acc[("lib", "f1")] = sf._RankAutocorrAccumulator(corr_sum=1.5, n_pairs=3)

    missing_acc: dict = defaultdict(sf._MissingAccumulator)
    missing_acc[("lib", "f1")] = sf._MissingAccumulator(total=100, missing=4)
    missing_acc[("lib", "f2")] = sf._MissingAccumulator(total=50, missing=0)

    frame = sf._serialize_checkpoint(ic_acc, autocorr_acc, missing_acc)
    checkpoint_path = tmp_path / "2024_lib.parquet"
    sf._write_checkpoint(checkpoint_path, frame)
    assert checkpoint_path.exists()

    ic_acc2: dict = defaultdict(sf._FactorAccumulator)
    autocorr_acc2: dict = defaultdict(sf._RankAutocorrAccumulator)
    missing_acc2: dict = defaultdict(sf._MissingAccumulator)
    sf._load_checkpoint_into_accumulators(
        checkpoint_path, "lib", ic_acc2, autocorr_acc2, missing_acc2
    )

    key1 = ("lib", "f1", "label_excess_5")
    assert list(ic_acc2[key1].dates) == ic_acc[key1].dates
    assert ic_acc2[key1].ic_values == pytest.approx(ic_acc[key1].ic_values)

    key2 = ("lib", "f2", "label_excess_10")
    assert list(ic_acc2[key2].dates) == ic_acc[key2].dates
    assert ic_acc2[key2].ic_values == pytest.approx(ic_acc[key2].ic_values)

    assert autocorr_acc2[("lib", "f1")].corr_sum == pytest.approx(1.5)
    assert autocorr_acc2[("lib", "f1")].n_pairs == 3

    assert missing_acc2[("lib", "f1")].total == 100
    assert missing_acc2[("lib", "f1")].missing == 4
    assert missing_acc2[("lib", "f2")].total == 50
    assert missing_acc2[("lib", "f2")].missing == 0


def test_write_checkpoint_is_atomic_no_leftover_tmp_file(tmp_path: Path) -> None:
    frame = pd.DataFrame({"record_type": ["missing"], "factor": ["f1"]})
    checkpoint_path = tmp_path / "2024_lib.parquet"
    sf._write_checkpoint(checkpoint_path, frame)
    assert checkpoint_path.exists()
    assert not (tmp_path / "2024_lib.parquet.tmp").exists()


def test_run_year_library_writes_checkpoint_and_second_call_skips(
    tmp_path: Path, synthetic_archive: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoints_root = tmp_path / "checkpoints"
    ic_acc: dict = defaultdict(sf._FactorAccumulator)
    autocorr_acc: dict = defaultdict(sf._RankAutocorrAccumulator)
    missing_acc: dict = defaultdict(sf._MissingAccumulator)

    status1 = sf._run_year_library(
        "toylib",
        2024,
        ["factor1"],
        synthetic_archive["universe_panel"],
        ic_acc,
        autocorr_acc,
        missing_acc,
        checkpoints_root=checkpoints_root,
    )
    assert status1 == "computed"
    checkpoint_path = checkpoints_root / "2024_toylib.parquet"
    assert checkpoint_path.exists()

    key = ("toylib", "factor1", "label_excess_5")
    missing_key = ("toylib", "factor1")
    first_dates = list(ic_acc[key].dates)
    first_values = list(ic_acc[key].ic_values)
    first_autocorr = (autocorr_acc[missing_key].corr_sum, autocorr_acc[missing_key].n_pairs)
    first_missing = (missing_acc[missing_key].total, missing_acc[missing_key].missing)
    assert len(first_dates) >= 2  # sanity: the first run actually found IC observations

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("_process_library_year must not run when a checkpoint exists")

    monkeypatch.setattr(sf, "_process_library_year", _boom)

    ic_acc2: dict = defaultdict(sf._FactorAccumulator)
    autocorr_acc2: dict = defaultdict(sf._RankAutocorrAccumulator)
    missing_acc2: dict = defaultdict(sf._MissingAccumulator)
    status2 = sf._run_year_library(
        "toylib",
        2024,
        ["factor1"],
        synthetic_archive["universe_panel"],
        ic_acc2,
        autocorr_acc2,
        missing_acc2,
        checkpoints_root=checkpoints_root,
    )
    assert status2 == "skipped"
    assert list(ic_acc2[key].dates) == first_dates
    assert ic_acc2[key].ic_values == pytest.approx(first_values)
    assert (
        autocorr_acc2[missing_key].corr_sum,
        autocorr_acc2[missing_key].n_pairs,
    ) == pytest.approx(first_autocorr)
    assert (missing_acc2[missing_key].total, missing_acc2[missing_key].missing) == first_missing
