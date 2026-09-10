"""Tests for the pure orchestration logic in scripts/build_hourly_bars.py --
the parts that don't need a real DuckDB connection or SIP archive: month
discovery, the "only finalize a year once every source month is checkpointed"
gate, and manifest merging. ``_fetch_month_minute_bars``/``_month_universe``
touch real DuckDB/parquet data and are exercised by actually running the
script, matching the convention of sibling ``build_*_features.py`` scripts
(no per-script unit test for their DuckDB-touching functions either).

Module-level path constants are monkeypatched to a ``tmp_path`` so these
tests never touch the real ``data/`` tree.
"""

from __future__ import annotations

import importlib
import json

import pandas as pd
import pytest

build_hourly_bars = importlib.import_module("scripts.build_hourly_bars")


@pytest.fixture
def module(tmp_path, monkeypatch):
    # REPO_ROOT is patched too: _finalize_year stores each manifest entry's
    # path via ``out_path.relative_to(REPO_ROOT)`` for readability, which
    # only resolves when OUT_ROOT is actually a descendant of REPO_ROOT (true
    # in production by construction -- OUT_ROOT = REPO_ROOT / "data" / ...).
    monkeypatch.setattr(build_hourly_bars, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(build_hourly_bars, "MINUTE_ROOT", tmp_path / "minute")
    monkeypatch.setattr(build_hourly_bars, "OUT_ROOT", tmp_path / "hourly")
    monkeypatch.setattr(build_hourly_bars, "CHECKPOINT_ROOT", tmp_path / "hourly" / "_checkpoints")
    return build_hourly_bars


def _write_checkpoint(module, year: int, month: int, rows: pd.DataFrame) -> None:
    module.CHECKPOINT_ROOT.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(module._checkpoint_path(year, month), index=False)


def _sample_frame(symbol: str, n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol] * n,
            "timestamp": pd.date_range("2024-01-02 14:30", periods=n, freq="h", tz="UTC"),
            "open": [1.0] * n,
            "high": [1.0] * n,
            "low": [1.0] * n,
            "close": [1.0] * n,
            "volume": [1.0] * n,
            "trade_count": [1.0] * n,
            "vwap": [1.0] * n,
            "minute_bar_count": [60] * n,
        }
    )


def test_available_year_months_discovers_month_dirs_above_threshold(module) -> None:
    for year, month in [(2023, 11), (2023, 12), (2024, 1), (2024, 2), (2025, 6)]:
        (module.MINUTE_ROOT / str(year) / f"{month:02d}").mkdir(parents=True)
    # a non-digit / stray file must be ignored, not crash
    (module.MINUTE_ROOT / "README.txt").write_text("x")
    pairs = module._available_year_months()
    # 2023 months are below START_YEAR_MONTH=(2024, 1) and must be excluded.
    assert pairs == [(2024, 1), (2024, 2), (2025, 6)]


def test_finalize_year_returns_none_when_checkpoints_incomplete(module) -> None:
    _write_checkpoint(module, 2024, 1, _sample_frame("AAA", 2))
    # month 2 checkpoint missing
    result = module._finalize_year(2024, [1, 2])
    assert result is None
    assert not (module.OUT_ROOT / "2024.parquet").exists()


def test_finalize_year_writes_combined_frame_when_all_checkpoints_present(module) -> None:
    _write_checkpoint(module, 2024, 1, _sample_frame("AAA", 2))
    _write_checkpoint(module, 2024, 2, _sample_frame("BBB", 3))
    entry = module._finalize_year(2024, [1, 2])
    assert entry is not None
    assert entry["row_count"] == 5
    assert entry["symbol_count"] == 2
    out_path = module.OUT_ROOT / "2024.parquet"
    assert out_path.is_file()
    combined = pd.read_parquet(out_path)
    assert len(combined) == 5
    assert set(combined["symbol"]) == {"AAA", "BBB"}


def test_finalize_year_does_not_finalize_from_a_partial_months_subset(module) -> None:
    # Simulates a source archive with 12 months for 2024, but this particular
    # invocation only processed (checkpointed) month 1 -- must not finalize.
    _write_checkpoint(module, 2024, 1, _sample_frame("AAA", 2))
    full_source_months = list(range(1, 13))
    result = module._finalize_year(2024, full_source_months)
    assert result is None
    assert not (module.OUT_ROOT / "2024.parquet").exists()


def test_write_manifest_merges_with_existing_years_rather_than_overwriting(module) -> None:
    module.OUT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = module.OUT_ROOT / "MANIFEST.json"
    manifest_path.write_text(json.dumps({"years": {"2024": {"row_count": 100, "months": [1, 2]}}}))

    module._write_manifest({2025: {"row_count": 50, "months": [1], "symbol_count": 3, "path": "x"}})

    merged = json.loads(manifest_path.read_text())
    assert set(merged["years"]) == {"2024", "2025"}
    assert merged["years"]["2024"]["row_count"] == 100
    assert merged["years"]["2025"]["row_count"] == 50


def test_write_manifest_overwrites_only_the_touched_year(module) -> None:
    module.OUT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = module.OUT_ROOT / "MANIFEST.json"
    manifest_path.write_text(json.dumps({"years": {"2024": {"row_count": 100, "months": [1]}}}))

    module._write_manifest(
        {2024: {"row_count": 999, "months": [1, 2], "symbol_count": 3, "path": "x"}}
    )

    merged = json.loads(manifest_path.read_text())
    assert merged["years"]["2024"]["row_count"] == 999
    assert merged["years"]["2024"]["months"] == [1, 2]
