"""Tests for open_composer.research.features.manifest."""

from __future__ import annotations

from pathlib import Path

from open_composer.research.features.manifest import (
    read_feature_table_manifest,
    write_feature_table_manifest,
)


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "alpha158"
    write_feature_table_manifest(
        root,
        table="alpha158",
        source_library="microsoft/qlib (MIT)",
        formula_version="v1",
        columns=["symbol", "trade_date", "KMID"],
        skipped=[],
        rows_by_year={"2024": 100},
        build_seconds_by_year={"2024": 1.5},
        notes="test",
    )
    manifest = read_feature_table_manifest(root)
    assert manifest["table"] == "alpha158"
    assert manifest["column_count"] == 3
    assert manifest["rows_by_year"] == {"2024": 100}
    assert manifest["row_count_total"] == 100
    assert manifest["skipped_count"] == 0


def test_write_merges_rows_by_year_across_calls_instead_of_overwriting(tmp_path: Path) -> None:
    root = tmp_path / "alpha101"
    common = dict(
        table="alpha101",
        source_library="lib",
        formula_version="v1",
        columns=["symbol", "trade_date", "alpha001"],
        skipped=[{"id": "alpha056", "reason": "needs cap"}],
    )
    write_feature_table_manifest(
        root, rows_by_year={"2023": 10}, build_seconds_by_year={"2023": 1.0}, **common
    )
    write_feature_table_manifest(
        root, rows_by_year={"2024": 20}, build_seconds_by_year={"2024": 2.0}, **common
    )
    manifest = read_feature_table_manifest(root)
    assert manifest["rows_by_year"] == {"2023": 10, "2024": 20}
    assert manifest["row_count_total"] == 30
    assert manifest["skipped_count"] == 1
    assert manifest["skipped"][0]["id"] == "alpha056"


def test_read_missing_manifest_raises(tmp_path: Path) -> None:
    try:
        read_feature_table_manifest(tmp_path / "does_not_exist")
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")
