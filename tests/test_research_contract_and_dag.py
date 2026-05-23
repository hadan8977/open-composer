from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from open_composer.cli import app


def test_strategy_research_report_writes_default_contract_pipeline(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "research-report",
            str(sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "[DEPRECATED]" in result.output
    assert "strategy evidence complete" in result.output
    report_json = (
        sample_workspace / "reports" / "research" / "fixture_pullback_15m-research-report.json"
    )
    contract_json = (
        sample_workspace / "reports" / "research" / "fixture_pullback_15m-research-contract.json"
    )
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    contract = json.loads(contract_json.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["kind"] == "research_report"
    assert (
        payload["contract_path"] == "reports/research/fixture_pullback_15m-research-contract.json"
    )
    assert payload["research_brief"]["strategy_name"] == "fixture_pullback_15m"
    assert payload["search_space"]["family"] == "default_research_contract"
    assert payload["candidate_count"] >= 1
    assert payload["trial_count"] == 1
    assert payload["runtime_seconds"] >= 0
    assert payload["evaluation_bundle"]["strategy_name"] == "fixture_pullback_15m"
    assert "leakage_controls" in payload["default_research_controls"]
    assert "overfit_controls" in payload["default_research_controls"]
    assert "live_gap_controls" in payload["default_research_controls"]
    assert payload["research_run_index_record"]["run_id"].startswith(
        "research-fixture_pullback_15m-"
    )
    assert "factor_lab" in contract["requirements"]["workflow"]
    assert any(item["name"] == "execution_reality" for item in payload["checklist"])
    assert payload["factor_lab"]["status"] == "blocked"
    assert payload["promotion"]["status"] == "blocked"
    index_path = sample_workspace / "reports" / "research" / "index.jsonl"
    assert index_path.exists()
    index_rows = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines()]
    research_row = next(item for item in index_rows if item["kind"] == "research_report")
    assert research_row["blocked_items"]


def test_strategy_dag_validation_blocks_incomplete_llm_packets(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    packet_path = sample_workspace / "feature_logs" / "dag_llm.jsonl"
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(
        (
            '{"timestamp":"2026-01-01T00:00:00Z","source":"llm","symbol":"QQQ",'
            '"dedupe_key":"dag:1","decision_score":0.4}\n'
        ),
        encoding="utf-8",
    )
    dag_path = sample_workspace / "strategy_specs" / "drafts" / "dag_fixture.yaml"
    dag_path.write_text(
        yaml.safe_dump(
            {
                "name": "dag_fixture",
                "strategy_name": "fixture_pullback_15m",
                "nodes": [
                    {"id": "quant", "type": "quant_signal"},
                    {
                        "id": "llm",
                        "type": "llm_judge",
                        "inputs": ["quant"],
                        "packet_path": "feature_logs/dag_llm.jsonl",
                        "packet_field": "decision_score",
                    },
                    {"id": "risk", "type": "risk_gate", "inputs": ["llm"]},
                ],
                "edges": [["quant", "llm"], ["llm", "risk"]],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["strategy", "dag-validate", str(dag_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(
        (sample_workspace / "reports" / "research" / "dag_fixture-dag-validation.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["status"] == "blocked"
    llm_check = next(item for item in payload["checks"] if item["node"] == "llm")
    assert llm_check["point_in_time_status"] == "partial"


def test_strategy_dag_validation_accepts_pit_complete_llm_packet(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    packet_path = sample_workspace / "feature_logs" / "dag_llm_complete.jsonl"
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(
        (
            '{"timestamp":"2026-01-01T00:00:00Z",'
            '"published_at":"2026-01-01T00:00:00Z",'
            '"fetched_at":"2026-01-01T00:01:00Z",'
            '"visible_at":"2026-01-01T00:01:00Z",'
            '"source":"llm","symbol":"QQQ","dedupe_key":"dag:complete:1",'
            '"schema_version":"1","model":"gpt-test","input_hash":"input-1",'
            '"prompt_hash":"prompt-1","features":{"decision_score":0.4},'
            '"evidence":{"single_modality_baseline_metric":"baseline",'
            '"marginal_lift_metric":"lift","missing_modality_robustness":"robust"}}\n'
        ),
        encoding="utf-8",
    )
    dag_path = sample_workspace / "strategy_specs" / "drafts" / "dag_complete_fixture.yaml"
    dag_path.write_text(
        yaml.safe_dump(
            {
                "name": "dag_complete_fixture",
                "strategy_name": "fixture_pullback_15m",
                "nodes": [
                    {"id": "quant", "type": "quant_signal"},
                    {
                        "id": "llm",
                        "type": "llm_judge",
                        "inputs": ["quant"],
                        "packet_path": "feature_logs/dag_llm_complete.jsonl",
                        "packet_field": "decision_score",
                    },
                    {"id": "risk", "type": "risk_gate", "inputs": ["llm"]},
                ],
                "edges": [["quant", "llm"], ["llm", "risk"]],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["strategy", "dag-validate", str(dag_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(
        (
            sample_workspace / "reports" / "research" / "dag_complete_fixture-dag-validation.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["status"] == "ok"
    llm_check = next(item for item in payload["checks"] if item["node"] == "llm")
    assert llm_check["missing_prompt_hash_count"] == 0


def test_strategy_dag_validation_blocks_llm_packet_without_hashes(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    packet_path = sample_workspace / "feature_logs" / "dag_llm_no_hashes.jsonl"
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(
        (
            '{"timestamp":"2026-01-01T00:00:00Z",'
            '"published_at":"2026-01-01T00:00:00Z",'
            '"fetched_at":"2026-01-01T00:01:00Z",'
            '"visible_at":"2026-01-01T00:01:00Z",'
            '"source":"llm","symbol":"QQQ","dedupe_key":"dag:nohash:1",'
            '"schema_version":"1","features":{"decision_score":0.4},'
            '"evidence":{"single_modality_baseline_metric":"baseline",'
            '"marginal_lift_metric":"lift","missing_modality_robustness":"robust"}}\n'
        ),
        encoding="utf-8",
    )
    dag_path = sample_workspace / "strategy_specs" / "drafts" / "dag_no_hash_fixture.yaml"
    dag_path.write_text(
        yaml.safe_dump(
            {
                "name": "dag_no_hash_fixture",
                "strategy_name": "fixture_pullback_15m",
                "nodes": [
                    {"id": "quant", "type": "quant_signal"},
                    {
                        "id": "llm",
                        "type": "llm_judge",
                        "inputs": ["quant"],
                        "packet_path": "feature_logs/dag_llm_no_hashes.jsonl",
                        "packet_field": "decision_score",
                    },
                ],
                "edges": [["quant", "llm"]],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["strategy", "dag-validate", str(dag_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(
        (
            sample_workspace / "reports" / "research" / "dag_no_hash_fixture-dag-validation.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["status"] == "blocked"
    llm_check = next(item for item in payload["checks"] if item["node"] == "llm")
    assert llm_check["missing_input_hash_count"] == 1
    assert llm_check["missing_prompt_hash_count"] == 1
