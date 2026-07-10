from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.iteration_dossier import (
    init_iteration_dossier,
    validate_iteration_dossier,
)


def test_iteration_dossier_init_writes_template_and_validate_blocks(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)

    assert paths.external_brief_json.exists()
    assert paths.hypotheses_md.exists()
    assert paths.search_space_json.exists()
    assert paths.decision_record_md.exists()

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert result.status == "blocked"
    assert "external_brief_sources_lt_8:0" in result.blocked
    assert "external_brief_paper_sources_lt_3:0" in result.blocked
    assert "search_space_paths_missing" in result.blocked
    assert "decision_record_still_template" in result.blocked


def test_iteration_dossier_validate_passes_complete_dossier(sample_workspace: Path) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    sources = [
        {
            "url": f"https://example.com/source-{idx}",
            "published_or_updated_at": "2026-01-01",
            "source_type": "paper" if idx < 3 else "platform_docs",
            "credibility": "high",
            "core_claim": f"claim {idx}",
            "project_applicability": "Defines a bounded minute momentum hypothesis.",
            "reflection": "May decay and is sensitive to transaction costs.",
        }
        for idx in range(8)
    ]
    paths.external_brief_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "strategy_name": "us_minute_momentum",
                "source_spec_path": None,
                "spec_hash": None,
                "objective": "US minute momentum round 1",
                "sources": sources,
                "topic_coverage": [
                    "intraday momentum",
                    "intraday reversal",
                    "cross-sectional momentum",
                    "overnight intraday decomposition",
                    "volatility-managed momentum",
                    "transaction costs",
                ],
                "candidate_matrix_revisions": [
                    {"path": "P1", "decision": "keep", "reason": "supported by sources"}
                ],
                "hypothesis_links": [{"hypothesis_id": "H1", "source_urls": [sources[0]["url"]]}],
            }
        ),
        encoding="utf-8",
    )
    paths.search_space_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "strategy_name": "us_minute_momentum",
                "source_spec_path": None,
                "spec_hash": None,
                "total_candidate_budget": 32,
                "paths": [
                    {
                        "name": "P1",
                        "candidate_count": 12,
                        "hypothesis_refs": ["H1"],
                        "parameters": {"lookback": [12, 24]},
                        "benchmark_family": ["QQQ", "BIL", "naive_momentum"],
                    },
                    {
                        "name": "P2",
                        "candidate_count": 8,
                        "hypothesis_refs": ["H2"],
                        "parameters": {"top_k": [1, 2]},
                        "benchmark_family": ["SPY", "BIL", "equal_weight_universe"],
                    },
                ],
                "trial_ledger_paths": [],
                "evaluation_report_paths": [],
                "cost_table_path": "reports/research/control/minute-momentum-feasibility.json",
                "data_feasibility_path": "reports/research/control/minute-momentum-feasibility.md",
            }
        ),
        encoding="utf-8",
    )
    paths.external_brief_md.write_text(_filled_md("External brief"), encoding="utf-8")
    paths.hypotheses_md.write_text(_hypotheses_md(), encoding="utf-8")
    paths.search_space_md.write_text(_filled_md("Search space"), encoding="utf-8")
    paths.decision_record_md.write_text(_decision_record_md("pending"), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert result.status == "ok"
    assert result.blocked == []


def test_iteration_dossier_blocks_payload_iter_id_mismatch(sample_workspace: Path) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    payload = json.loads(paths.external_brief_json.read_text(encoding="utf-8"))
    payload["iter_id"] = "other_round"
    paths.external_brief_json.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert "iteration_payload_iter_id_mismatch" in result.blocked


def test_iteration_dossier_final_stage_requires_artifact_refs(sample_workspace: Path) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    paths.decision_record_md.write_text(_decision_record_md("continue"), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace, stage="final")

    assert "search_space_trial_ledger_paths_empty_final" in result.blocked
    assert "search_space_evaluation_report_paths_empty_final" in result.blocked


def test_iteration_dossier_cli_init_and_validate(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    runner = CliRunner()

    init_result = runner.invoke(
        app,
        ["research", "iteration", "init", "mom_minute_r1"],
        catch_exceptions=False,
    )
    validate_result = runner.invoke(
        app,
        ["research", "iteration", "validate", "mom_minute_r1"],
        catch_exceptions=False,
    )

    assert init_result.exit_code == 0
    assert validate_result.exit_code == 1
    assert "external_brief_sources_lt_8:0" in validate_result.output

    json_result = runner.invoke(
        app,
        ["research", "iteration", "validate", "mom_minute_r1", "--json"],
        catch_exceptions=False,
    )
    assert json_result.exit_code == 1
    assert json.loads(json_result.output)["status"] == "blocked"


def _write_complete_pre_backtest_payload(paths) -> None:
    sources = [
        {
            "url": f"https://example.com/source-{idx}",
            "published_or_updated_at": "2026-01-01",
            "source_type": "paper" if idx < 3 else "platform_docs",
            "credibility": "high",
            "core_claim": f"claim {idx}",
            "project_applicability": "Defines a bounded minute momentum hypothesis.",
            "reflection": "May decay and is sensitive to transaction costs.",
        }
        for idx in range(8)
    ]
    paths.external_brief_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "strategy_name": "us_minute_momentum",
                "source_spec_path": None,
                "spec_hash": None,
                "objective": "US minute momentum round 1",
                "sources": sources,
                "topic_coverage": [
                    "intraday momentum",
                    "intraday reversal",
                    "cross-sectional momentum",
                    "overnight intraday decomposition",
                    "volatility-managed momentum",
                    "transaction costs",
                ],
                "candidate_matrix_revisions": [{"path": "P1", "decision": "keep"}],
                "hypothesis_links": [{"hypothesis_id": "H1", "source_urls": [sources[0]["url"]]}],
            }
        ),
        encoding="utf-8",
    )
    paths.search_space_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "strategy_name": "us_minute_momentum",
                "source_spec_path": None,
                "spec_hash": None,
                "total_candidate_budget": 24,
                "paths": [
                    {
                        "name": "P1",
                        "candidate_count": 12,
                        "hypothesis_refs": ["H1"],
                        "parameters": {"lookback": [12, 24]},
                        "benchmark_family": ["QQQ", "BIL", "naive_momentum"],
                    }
                ],
                "trial_ledger_paths": [],
                "evaluation_report_paths": [],
                "cost_table_path": "reports/research/control/minute-momentum-feasibility.json",
                "data_feasibility_path": "reports/research/control/minute-momentum-feasibility.md",
            }
        ),
        encoding="utf-8",
    )
    paths.external_brief_md.write_text(_filled_md("External brief"), encoding="utf-8")
    paths.hypotheses_md.write_text(_hypotheses_md(), encoding="utf-8")
    paths.search_space_md.write_text(_filled_md("Search space"), encoding="utf-8")
    paths.decision_record_md.write_text(_decision_record_md("pending"), encoding="utf-8")


def _filled_md(title: str) -> str:
    return (
        f"# {title}\n\n"
        "This file has been completed with enough project-specific content to move beyond "
        "the generated template. It records the hypothesis, evidence linkage, benchmark "
        "family, cost caveats, expected failure mode, and the next decision for the "
        "Open Composer minute momentum iteration.\n"
    )


def _hypotheses_md() -> str:
    return """# Hypotheses

## H1

- Hypothesis: Thirty-minute ETF momentum persists after the opening range when
  trend breadth is positive.
- Failure mode: The signal reverses after costs or only works in a single
  recent bull regime.
- Measurement: Four chronological walk-forward folds with QQQ, SPY, BIL,
  equal-weight universe, and naive momentum benchmarks.
- Stop/Pivot criterion: Stop if the last two folds are negative after baseline
  costs; pivot to lower frequency if cost stress dominates.
"""


def _decision_record_md(decision: str) -> str:
    return f"""# Decision Record

## P1

- Path: time-series ETF momentum.
- Decision: {decision}
- Reason: Pre-backtest dossier is ready when pending; final records must use
  continue, pivot, or stop with supporting evidence.
- Next iteration suggestion: Move to ML only if OOS decisions exceed the sample
  threshold and the non-ML baseline survives cost stress.
"""
