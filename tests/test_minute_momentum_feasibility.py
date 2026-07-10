from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.minute_momentum_feasibility import (
    compute_minute_quality,
    run_minute_momentum_feasibility,
)


def test_compute_minute_quality_detects_extended_hours_and_zero_volume() -> None:
    frame = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-02T13:00:00Z",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 0,
            },
            {
                "timestamp": "2026-01-02T14:30:00Z",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 10,
            },
            {
                "timestamp": "2026-01-02T14:45:00Z",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 20,
            },
            {
                "timestamp": "2026-01-02T21:30:00Z",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 30,
            },
        ]
    )

    quality = compute_minute_quality(frame, "15m")

    assert quality["extended_hours_present"] is True
    assert quality["extended_hours_ratio"] == 0.5
    assert quality["zero_volume_ratio"] == 0.25
    assert quality["rth_days"] == 1


def test_minute_feasibility_uses_isolated_research_output(sample_workspace: Path) -> None:
    cache_path = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _write_cache(cache_path, periods=30)

    result = run_minute_momentum_feasibility(
        sample_workspace,
        symbols=["QQQ"],
        representative_symbols=["QQQ"],
        timeframes=["15m"],
        report_date="20260710",
    )

    row = result.payload["rows"][0]
    assert row["status"] == "ok"
    assert row["source_mode"] == "cache_copy"
    assert row["path"].startswith("data/research/alpaca_minute/")
    assert (sample_workspace / row["path"]).exists()
    assert result.json_path.exists()
    assert result.markdown_path.exists()
    assert result.manifest_path.exists()


def test_minute_feasibility_missing_cache_records_error_without_fallback(
    sample_workspace: Path,
) -> None:
    result = run_minute_momentum_feasibility(
        sample_workspace,
        symbols=["MISSING"],
        representative_symbols=["MISSING"],
        timeframes=["15m"],
        report_date="20260710",
    )

    row = result.payload["rows"][0]
    assert row["status"] == "error"
    assert row["go"] is False
    assert "missing Alpaca cache" in row["error"]
    assert not list((sample_workspace / "data" / "research" / "alpaca_minute").glob("*.csv"))


def test_minute_feasibility_cli_writes_report(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    cache_path = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _write_cache(cache_path, periods=30)

    result = CliRunner().invoke(
        app,
        [
            "data",
            "minute-momentum-feasibility",
            "--symbols",
            "QQQ",
            "--representative-symbols",
            "QQQ",
            "--timeframes",
            "15m",
            "--report-date",
            "20260710",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(
        (
            sample_workspace
            / "reports"
            / "research"
            / "control"
            / "minute-momentum-feasibility-20260710.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["rows"][0]["symbol"] == "QQQ"


def _write_cache(path: Path, *, periods: int) -> None:
    timestamps = pd.date_range("2026-01-02T14:30:00Z", periods=periods, freq="15min")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100 + idx for idx in range(periods)],
            "high": [101 + idx for idx in range(periods)],
            "low": [99 + idx for idx in range(periods)],
            "close": [100.5 + idx for idx in range(periods)],
            "volume": [1000] * periods,
        }
    )
    frame.to_csv(path, index=False)
