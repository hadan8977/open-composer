from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.new_lightweight_iteration import config_from_ledger


def _write_ledger(root: Path, rows: list[dict[str, object]]) -> None:
    ledger_path = root / "reports" / "research" / "ledger" / "experiments.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


_SAMPLE_ROW = {
    "experiment_id": "step11_b1_momentum_top50",
    "config_hash": "abc123",
    "family": "step11_baseline_chain",
    "model_kind": "b1_momentum",
    "feature_set": "daily_only",
    "label_horizon_days": 5,
    "top_k": 50,
    "hedge": "spy_beta_hedge",
    "long_only": {
        "gate_results": {
            "cagr_excess_vol_matched_benchmark": False,
            "sharpe_excess_bil": False,
            "dsr_probability": True,
            "max_drawdown": False,
            "mar": False,
            "positive_fold_fraction": True,
            "benchmark_vm_capture_ratio": True,
            "benchmark_vm_downside_capture": True,
        },
        "all_gates_pass": False,
    },
    "tearsheet_path": "reports/research/tearsheets/step11_b1_momentum_top50.html",
    "mlflow_run_id": "f419b76199f24f9fb2159b5caf4f48ac",
    "recorded_at": "2026-09-07T14:16:58.713430+00:00",
}


def test_config_from_ledger_derives_real_fields_not_fabricated(tmp_path: Path) -> None:
    _write_ledger(tmp_path, [_SAMPLE_ROW])

    config = config_from_ledger(
        root=tmp_path,
        experiment_id="step11_b1_momentum_top50",
        iter_id="step11_wavec_model_ranking_top50",
        strategy_name="us_model_ranking_portfolio_top50",
        representative_spec_path="strategy_specs/drafts/us_model_ranking_portfolio_top50.yaml",
        sources=None,
        topic_coverage=None,
        source_cards_path=None,
    )

    assert config["iter_id"] == "step11_wavec_model_ranking_top50"
    candidate = config["candidates"][0]
    assert candidate["candidate_id"] == "step11_b1_momentum_top50"
    # Every candidate parameter traces back to the real ledger row, not a guess.
    assert candidate["parameters"]["top_k"] == 50
    assert candidate["parameters"]["hedge"] == "spy_beta_hedge"
    assert candidate["parameters"]["config_hash"] == "abc123"
    assert "4/8" in config["decision"]["reason"] or "gates 4/8" in config["decision"]["reason"]
    # sources/topic_coverage are never fabricated -- absent input stays empty,
    # forcing build_dossier's own "config missing required key" failure later.
    assert config["sources"] == []
    assert config["topic_coverage"] == []
    assert config["source_cards_path"] == ""


def test_config_from_ledger_passes_through_supplied_sources(tmp_path: Path) -> None:
    _write_ledger(tmp_path, [_SAMPLE_ROW])
    sources = [
        {"claim_id": f"c{i}", "url": "https://example.com", "source_type": "paper"}
        for i in range(8)
    ]

    config = config_from_ledger(
        root=tmp_path,
        experiment_id="step11_b1_momentum_top50",
        iter_id="step11_wavec_model_ranking_top50",
        strategy_name="us_model_ranking_portfolio_top50",
        representative_spec_path="strategy_specs/drafts/us_model_ranking_portfolio_top50.yaml",
        sources=sources,
        topic_coverage=["a", "b", "c", "d", "e", "f"],
        source_cards_path="reports/harness/source_cards/us_model_ranking_portfolio_top50.jsonl",
    )

    assert len(config["sources"]) == 8
    assert config["topic_coverage"] == ["a", "b", "c", "d", "e", "f"]
    assert config["source_cards_path"].endswith(".jsonl")


def test_missing_experiment_id_fails_closed(tmp_path: Path) -> None:
    _write_ledger(tmp_path, [_SAMPLE_ROW])

    with pytest.raises(SystemExit, match="no ledger row"):
        config_from_ledger(
            root=tmp_path,
            experiment_id="does_not_exist",
            iter_id="x",
            strategy_name="x",
            representative_spec_path="x.yaml",
            sources=None,
            topic_coverage=None,
            source_cards_path=None,
        )


def test_duplicate_experiment_id_fails_closed_rather_than_pick_one(tmp_path: Path) -> None:
    _write_ledger(tmp_path, [_SAMPLE_ROW, _SAMPLE_ROW])

    with pytest.raises(SystemExit, match="2 rows"):
        config_from_ledger(
            root=tmp_path,
            experiment_id="step11_b1_momentum_top50",
            iter_id="x",
            strategy_name="x",
            representative_spec_path="x.yaml",
            sources=None,
            topic_coverage=None,
            source_cards_path=None,
        )


def test_missing_ledger_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no experiment ledger"):
        config_from_ledger(
            root=tmp_path,
            experiment_id="anything",
            iter_id="x",
            strategy_name="x",
            representative_spec_path="x.yaml",
            sources=None,
            topic_coverage=None,
            source_cards_path=None,
        )
