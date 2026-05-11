from __future__ import annotations

import json
from pathlib import Path

from open_composer.adapters.data.comparison import compare_ohlcv_sources
from open_composer.adapters.data.longbridge import fetch_longbridge_bars, longbridge_cache_path


def test_longbridge_fetch_uses_cache_and_writes_manifest(sample_workspace: Path) -> None:
    cache = longbridge_cache_path(sample_workspace, "QQQ", "15m")
    sample = sample_workspace / "data" / "sample" / "qqq_15m.csv"
    cache.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")

    frame = fetch_longbridge_bars(
        sample_workspace,
        "QQQ",
        "15m",
        None,
        None,
        feed=None,
        use_cache=True,
    )

    manifest = (
        sample_workspace / "data" / "cache" / "manifests" / "qqq_15m_longbridge_nasdaq_basic.json"
    )
    assert len(frame) > 0
    assert manifest.exists()
    assert "longbridge" in manifest.read_text(encoding="utf-8")


def test_ohlcv_comparison_writes_reports(sample_workspace: Path) -> None:
    alpaca_cache = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    longbridge_cache = longbridge_cache_path(sample_workspace, "QQQ", "15m")
    sample = sample_workspace / "data" / "sample" / "qqq_15m.csv"
    alpaca_cache.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    longbridge_lines = sample.read_text(encoding="utf-8").splitlines()
    longbridge_lines[-1] = "2026-01-02T11:00:00-05:00,101.00,101.40,100.80,101.80,1075000"
    longbridge_cache.write_text("\n".join(longbridge_lines) + "\n", encoding="utf-8")

    report = compare_ohlcv_sources(
        sample_workspace,
        "QQQ",
        "15m",
        left_source="alpaca",
        right_source="longbridge",
        left_feed="iex",
        right_feed=None,
    )

    assert report.matched_rows > 0
    assert report.max_abs_close_diff > 0
    assert report.max_abs_close_diff_bps > 0
    assert report.matched_coverage_pct > 0
    assert report.left_manifest_path
    assert report.right_manifest_path
    assert any("Alpaca IEX" in caveat for caveat in report.caveats)
    assert any("Longbridge free US market data" in caveat for caveat in report.caveats)
    assert Path(report.report_json_path).exists()
    assert Path(report.report_markdown_path).exists()
    payload = json.loads(Path(report.report_json_path).read_text(encoding="utf-8"))
    markdown = Path(report.report_markdown_path).read_text(encoding="utf-8")
    assert payload["max_abs_close_diff_bps"] == report.max_abs_close_diff_bps
    assert payload["left_manifest_path"] == report.left_manifest_path
    assert "Matched coverage" in markdown
    assert "Caveats" in markdown
