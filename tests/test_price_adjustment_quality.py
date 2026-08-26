from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from open_composer.research.price_adjustment_quality import (
    audit_price_adjustment_snapshot,
    write_price_adjustment_quality_report,
)


def test_legacy_adjusted_only_bundle_blocks_split_discontinuity(tmp_path: Path) -> None:
    manifest = _write_bundle(
        tmp_path,
        {"all": [10.0, 10.2, 101.0]},
    )

    report = audit_price_adjustment_snapshot(tmp_path, manifest)

    assert report["status"] == "blocked"
    codes = {row["code"] for row in report["blocking_issues"]}
    assert "incomplete_adjustment_bundle" in codes
    assert "split_like_discontinuity_in_adjusted_series" in codes


def test_complete_bundle_accepts_raw_split_when_adjusted_series_is_continuous(
    tmp_path: Path,
) -> None:
    manifest = _write_bundle(
        tmp_path,
        {
            "raw": [100.0, 102.0, 10.4],
            "split": [10.0, 10.2, 10.4],
            "dividend": [100.0, 102.0, 10.4],
            "all": [10.0, 10.2, 10.4],
        },
    )

    report = audit_price_adjustment_snapshot(tmp_path, manifest)

    assert report["status"] == "ok"
    assert report["blocking_issue_count"] == 0
    assert report["research_eligible"] is True


def test_complete_bundle_blocks_contaminated_adjusted_mode(tmp_path: Path) -> None:
    manifest = _write_bundle(
        tmp_path,
        {
            "raw": [10.0, 10.2, 102.0],
            "split": [10.0, 10.2, 10.4],
            "dividend": [10.0, 10.2, 102.0],
            "all": [10.0, 10.2, 102.0],
        },
    )

    report = audit_price_adjustment_snapshot(tmp_path, manifest)

    assert report["status"] == "blocked"
    assert any(
        row["code"] == "split_like_discontinuity_in_adjusted_series" and row["adjustment"] == "all"
        for row in report["blocking_issues"]
    )


def test_snapshot_item_hash_is_verified_before_analysis(tmp_path: Path) -> None:
    manifest = _write_bundle(
        tmp_path,
        {
            "raw": [10.0, 10.2, 10.4],
            "split": [10.0, 10.2, 10.4],
            "dividend": [10.0, 10.2, 10.4],
            "all": [10.0, 10.2, 10.4],
        },
    )
    path = tmp_path / "spy_all.csv"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        audit_price_adjustment_snapshot(tmp_path, manifest)


def test_quality_report_writer_refuses_accidental_overwrite(tmp_path: Path) -> None:
    manifest = _write_bundle(
        tmp_path,
        {
            "raw": [10.0, 10.2, 10.4],
            "split": [10.0, 10.2, 10.4],
            "dividend": [10.0, 10.2, 10.4],
            "all": [10.0, 10.2, 10.4],
        },
    )
    output = Path("quality.json")

    write_price_adjustment_quality_report(tmp_path, manifest, output)

    with pytest.raises(ValueError, match="already exists"):
        write_price_adjustment_quality_report(tmp_path, manifest, output)


def _write_bundle(root: Path, modes: dict[str, list[float]]) -> Path:
    items = []
    for adjustment, closes in modes.items():
        path = root / f"spy_{adjustment}.csv"
        frame = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    ["2026-01-02T05:00:00Z", "2026-01-05T05:00:00Z", "2026-01-06T05:00:00Z"]
                ),
                "open": closes,
                "high": [value * 1.01 for value in closes],
                "low": [value * 0.99 for value in closes],
                "close": closes,
                "volume": [1000.0, 1100.0, 1200.0],
            }
        )
        frame.to_csv(path, index=False)
        items.append(
            {
                "symbol": "SPY",
                "timeframe": "daily",
                "adjustment": adjustment,
                "output_path": path.name,
                "output_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "iter_id": "quality_test_r1",
                "provider": "alpaca",
                "feed": "sip",
                "items": items,
            }
        ),
        encoding="utf-8",
    )
    return manifest
