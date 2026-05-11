from __future__ import annotations

from pathlib import Path

from open_composer.adapters.events import fetch_capability_events
from open_composer.capabilities import evaluate_capabilities, load_registry


def test_capability_registry_loads(sample_workspace: Path) -> None:
    registry = load_registry(sample_workspace)
    ids = {capability.id for capability in registry.capabilities}
    assert "market.alpaca_bars" in ids
    assert "market.longbridge_bars" in ids
    assert "events.sec_filings" in ids
    assert "macro.fred_series" in ids
    assert "news.alpha_vantage" in ids


def test_capability_evaluation_passes_with_fixtures(sample_workspace: Path) -> None:
    evaluations = evaluate_capabilities(sample_workspace)
    assert evaluations
    assert all(evaluation.passed for evaluation in evaluations)
    assert (sample_workspace / "reports" / "capabilities" / "evaluation.md").exists()


def test_event_fetch_replays_fixture_and_dedupes(sample_workspace: Path) -> None:
    events = fetch_capability_events("sec", sample_workspace, ["QQQ"], offline=True)
    assert events
    assert all(event.source == "sec" for event in events)
    assert list((sample_workspace / "data" / "raw" / "events" / "sec").glob("*.jsonl"))
