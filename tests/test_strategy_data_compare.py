from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_composer.adapters.data.comparison import OhlcvComparison
from open_composer.research.strategy_data_compare import run_strategy_data_compare


def test_strategy_data_compare_writes_blocker_safe_artifact(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    result = run_strategy_data_compare(
        spec_path,
        sample_workspace,
        primary="sample",
        secondary="sample",
    )

    assert result.status == "ok"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["strict_data_status"] == "ok"
    assert payload["compared_symbols"] == ["QQQ"]
    assert result.report_path.exists()


def test_strategy_data_compare_captures_missing_secondary_as_blocked(
    sample_workspace: Path,
) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    result = run_strategy_data_compare(
        spec_path,
        sample_workspace,
        primary="sample",
        secondary="missing_source",
    )

    assert result.status == "blocked"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["strict_data_status"] == "blocked"
    assert payload["blockers"]


def test_strategy_data_compare_reports_real_percentiles(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    def fake_compare_ohlcv_sources(
        root, symbol, timeframe, left_source, right_source, left_feed, right_feed
    ):
        index = {"AAA": 0, "BBB": 1, "CCC": 2}[symbol]
        mean_close = [10.0, 20.0, 30.0][index]
        max_close = [100.0, 200.0, 300.0][index]
        volume_ratio = [0.05, 0.15, 0.25][index]
        return OhlcvComparison(
            symbol=symbol,
            timeframe=timeframe,
            left_source=left_source,
            right_source=right_source,
            left_feed=left_feed,
            right_feed=right_feed,
            left_rows=10,
            right_rows=10,
            matched_rows=10,
            missing_left_rows=0,
            missing_right_rows=0,
            matched_coverage_pct=100.0,
            max_abs_close_diff=max_close,
            mean_abs_close_diff=0.0,
            max_abs_close_diff_bps=max_close,
            mean_abs_close_diff_bps=mean_close,
            max_abs_volume_diff=0.0,
            max_volume_diff_ratio=volume_ratio,
            first_matched_timestamp="2026-01-01T14:30:00+00:00",
            last_matched_timestamp="2026-01-01T15:00:00+00:00",
            sample_missing_left_timestamps=[],
            sample_missing_right_timestamps=[],
            left_manifest_path=None,
            right_manifest_path=None,
            caveats=[],
            report_json_path=f"reports/data/comparisons/{symbol}.json",
            report_markdown_path=f"reports/data/comparisons/{symbol}.md",
        )

    monkeypatch.setattr(
        "open_composer.research.strategy_data_compare.compare_ohlcv_sources",
        fake_compare_ohlcv_sources,
    )

    result = run_strategy_data_compare(
        spec_path,
        sample_workspace,
        primary="alpaca:iex",
        secondary="alpaca:sip",
        symbols=["AAA", "BBB", "CCC"],
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["close_drift_bps_p50"] == 20.0
    assert payload["close_drift_bps_p95"] == 290.0
    assert payload["volume_drift_pct_p50"] == 15.0
    assert payload["volume_drift_pct_p95"] == pytest.approx(24.0)
