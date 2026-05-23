from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research import llm_materialize


def _materializable_spec(sample_workspace: Path) -> Path:
    prompt = sample_workspace / "prompts" / "examples" / "news_regime_score.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text("Return score and confidence as JSON.\n", encoding="utf-8")
    source = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw["name"] = "qqq_news_regime_15m"
    raw["factors"] = {
        "news_regime_score": {
            "source": "llm_feature",
            "field": "score",
            "default": 0.0,
            "description": "Materialized LLM score.",
            "input_view": "news_window_v1",
            "input_view_version": 1,
            "prompt_template_path": "prompts/examples/news_regime_score.md",
            "output_schema": {
                "type": "object",
                "required": ["score", "confidence"],
                "properties": {
                    "score": {"type": "number"},
                    "confidence": {"type": "number"},
                },
            },
            "model_ref": "local_test_stub",
        }
    }
    raw["entry"] = {"all": ["news_regime_score > 0"]}
    raw["exit"] = {"any": ["news_regime_score < 0"]}
    target = sample_workspace / "strategy_specs" / "drafts" / "qqq_news_regime_15m.yaml"
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return target


def test_feature_materialize_command_writes_packets_and_uses_cache(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    spec_path = _materializable_spec(sample_workspace)
    runner = CliRunner()

    first = runner.invoke(
        app,
        ["feature", "materialize", str(spec_path), "--backend", "local_test_stub"],
        catch_exceptions=False,
    )
    second = runner.invoke(
        app,
        ["feature", "materialize", str(spec_path), "--backend", "local_test_stub"],
        catch_exceptions=False,
    )

    packet_path = (
        sample_workspace
        / "reports"
        / "features"
        / "qqq_news_regime_15m"
        / "news_regime_score"
        / "packets.jsonl"
    )
    run_path = packet_path.parent / "materialization-run.json"
    ledger_path = packet_path.parent / "prompt-trial-ledger.jsonl"
    assert first.exit_code == 0
    assert second.exit_code == 0
    assert packet_path.exists()
    assert run_path.exists()
    assert ledger_path.exists()
    assert "misses=16" in first.output
    assert "hits=16 misses=0" in second.output
    row = json.loads(packet_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["schema_version"] == "2"
    assert row["prompt_hash"].startswith("sha256:")
    assert row["input_hash"].startswith("sha256:")
    assert row["features"]["score"] is not None
    assert row["evidence"]["marginal_lift_metric"]


def test_feature_materialize_prompt_change_misses_cache(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    spec_path = _materializable_spec(sample_workspace)
    runner = CliRunner()

    first = runner.invoke(
        app,
        ["feature", "materialize", str(spec_path), "--backend", "local_test_stub"],
        catch_exceptions=False,
    )
    prompt = sample_workspace / "prompts" / "examples" / "news_regime_score.md"
    prompt.write_text(prompt.read_text(encoding="utf-8") + "\nUse stricter scoring.\n")
    second = runner.invoke(
        app,
        ["feature", "materialize", str(spec_path), "--backend", "local_test_stub"],
        catch_exceptions=False,
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "misses=16" in second.output


def test_feature_materialize_input_view_version_change_misses_cache(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    spec_path = _materializable_spec(sample_workspace)
    runner = CliRunner()

    first = runner.invoke(
        app,
        ["feature", "materialize", str(spec_path), "--backend", "local_test_stub"],
        catch_exceptions=False,
    )
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["factors"]["news_regime_score"]["input_view_version"] = 2
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    second = runner.invoke(
        app,
        ["feature", "materialize", str(spec_path), "--backend", "local_test_stub"],
        catch_exceptions=False,
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "misses=16" in second.output


def test_feature_materialize_schema_version_change_misses_cache(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    spec_path = _materializable_spec(sample_workspace)
    runner = CliRunner()

    first = runner.invoke(
        app,
        ["feature", "materialize", str(spec_path), "--backend", "local_test_stub"],
        catch_exceptions=False,
    )
    monkeypatch.setattr(llm_materialize, "SCHEMA_VERSION", "schema-test-bump")
    second = runner.invoke(
        app,
        ["feature", "materialize", str(spec_path), "--backend", "local_test_stub"],
        catch_exceptions=False,
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "misses=16" in second.output
