from __future__ import annotations

import json
from pathlib import Path

from open_composer.data_contracts import build_market_data_manifest, write_market_data_manifest
from open_composer.research.execution_sim import run_execution_sim


def test_execution_sim_blocks_without_market_data_manifest(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    result = run_execution_sim(spec_path, None, sample_workspace)

    assert result.status == "blocked"
    assert "market_data_manifest_missing" in result.blockers
    assert result.json_path is not None and result.json_path.exists()


def test_execution_sim_records_spread_metrics_and_experiment_run(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    manifest = build_market_data_manifest(
        sample_workspace / "data" / "fixtures" / "market_data" / "quote_ticks.jsonl",
        "quote_tick",
        root=sample_workspace,
        venue="XNAS",
    )
    manifest_path = sample_workspace / "reports" / "data" / "market_data" / "qqq-quotes.json"
    write_market_data_manifest(manifest_path, manifest)

    result = run_execution_sim(spec_path, manifest_path, sample_workspace)

    assert result.status == "warning"
    assert result.average_spread_bps is not None
    assert result.market_data_kind == "quote_tick"
    index_path = sample_workspace / "reports" / "experiments" / "index.jsonl"
    assert index_path.exists()
    payloads = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines()]
    assert payloads[-1]["kind"] == "execution_sim"
    assert payloads[-1]["metrics"]["average_spread_bps"] == result.average_spread_bps
