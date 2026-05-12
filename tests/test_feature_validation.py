from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.dashboard import build_dashboard_catalog, build_feature_packet_records
from open_composer.engines.backtest_engine import run_backtest


def _context_capable_spec(sample_workspace: Path) -> Path:
    source = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    target = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_context_auto.yaml"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw["name"] = "qqq_pullback_context_auto"
    raw["description"] = "QQQ pullback strategy with auto context replay packet emission."
    raw["llm_review"] = {"enabled": True, "model": "gpt-5.5"}
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return target


def test_feature_validate_command_writes_report(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    feature_path = sample_workspace / "feature_logs" / "qqq_llm_features.jsonl"
    feature_path.write_text(
        (
            '{"timestamp":"2026-01-01T00:00:00Z","published_at":"2026-01-01T00:00:00Z",'
            '"fetched_at":"2026-01-01T00:01:00Z","source":"llm","symbol":"QQQ",'
            '"dedupe_key":"llm:1","schema_version":"1","model":"mock","llm_sentiment":0.8}\n'
            '{"timestamp":"2026-01-01T00:15:00Z","source":"llm","symbol":"QQQ",'
            '"dedupe_key":"llm:2","llm_sentiment":0.6}\n'
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["feature", "validate"], catch_exceptions=False)

    assert result.exit_code == 0
    report_path = sample_workspace / "reports" / "features" / "validation.json"
    assert report_path.exists()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["feature_packet_count"] == 1
    assert payload["packets"][0]["path"] == "feature_logs/qqq_llm_features.jsonl"
    assert payload["packets"][0]["point_in_time_status"] == "partial"
    assert build_feature_packet_records(sample_workspace)[0].point_in_time_status == "partial"


def test_feature_write_command_writes_complete_point_in_time_packet(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "feature",
            "write",
            "--symbol",
            "QQQ",
            "--timestamp",
            "2026-01-01T00:00:00Z",
            "--source",
            "llm",
            "--feature",
            "event_risk_score=0.8",
            "--feature",
            "regime=risk_on",
            "--output",
            "feature_logs/manual_features.jsonl",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    path = sample_workspace / "feature_logs" / "manual_features.jsonl"
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert row["symbol"] == "QQQ"
    assert row["source"] == "llm"
    assert row["published_at"]
    assert row["fetched_at"]
    assert row["dedupe_key"] == "llm:QQQ:2026-01-01T00:00:00+00:00"
    assert row["features"]["event_risk_score"] == 0.8
    assert row["features"]["regime"] == "risk_on"

    packet = build_feature_packet_records(sample_workspace)[0]
    assert packet.path == "feature_logs/manual_features.jsonl"
    assert packet.point_in_time_status == "complete"


def test_feature_from_context_command_writes_replayable_context_features(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    backtest = run_backtest(
        sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml",
        root=sample_workspace,
    )
    signal = backtest.signals[0]

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["feature", "from-context", signal.id],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    path = sample_workspace / "feature_logs" / f"{signal.id}_context_features.jsonl"
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")) == signal.timestamp
    assert row["source"] == "context"
    assert row["symbol"] == signal.symbol
    assert row["dedupe_key"] == f"context:{signal.id}"
    assert row["features"]["event_count"] >= 0
    assert row["features"]["news_count"] >= 0
    assert row["features"]["macro_count"] >= 0
    assert row["features"]["context_record_count"] >= 0

    packet = build_feature_packet_records(sample_workspace)[0]
    assert packet.path == f"feature_logs/{signal.id}_context_features.jsonl"
    assert packet.point_in_time_status == "complete"


def test_backtest_auto_writes_context_feature_packets_for_context_capable_strategy(
    sample_workspace: Path,
) -> None:
    spec_path = _context_capable_spec(sample_workspace)
    backtest = run_backtest(spec_path, root=sample_workspace)
    signal = backtest.signals[0]
    path = sample_workspace / "feature_logs" / f"{signal.id}_context_features.jsonl"

    assert path.exists()
    assert any(
        "auto-written for context-capable signals" in assumption
        for assumption in backtest.run.assumptions
    )

    packet = build_feature_packet_records(sample_workspace)[0]
    assert packet.path == f"feature_logs/{signal.id}_context_features.jsonl"
    assert packet.point_in_time_status == "complete"
    catalog = build_dashboard_catalog(sample_workspace)
    assert any(
        item.path == f"feature_logs/{signal.id}_context_features.jsonl"
        and item.point_in_time_status == "complete"
        for item in catalog.feature_packets
    )
