from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.control import update_research_control
from open_composer.research.parameter_sweep import parse_sweep_parameters, run_parameter_sweep
from open_composer.research.research_brief import init_research_brief


def test_research_control_reduces_sweep_into_state_and_memory(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    init_research_brief(spec_path, sample_workspace, search_budget=4)
    parameters = parse_sweep_parameters(
        [
            "risk.stop_loss_pct=0.8,1.2",
            "costs.slippage_bps=0,5",
        ]
    )
    run_parameter_sweep(
        spec_path,
        parameters,
        sample_workspace,
        min_signals=1,
        max_candidates=4,
        top_n=4,
        write_top=0,
    )

    result = update_research_control(spec_path, sample_workspace)

    assert result.state_path.exists()
    assert result.memory_path.exists()
    assert len(result.memory_packet.encode("utf-8")) <= 32 * 1024
    capped = update_research_control(
        spec_path,
        sample_workspace,
        max_memory_bytes=1024,
    )
    assert len(capped.memory_packet.encode("utf-8")) <= 1024
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["strategy_name"] == "fixture_pullback_15m"
    assert state["current_best"]["params"]
    assert state["effective_combinations"]
    assert state["source_artifacts"]["parameter_sweep"] == (
        "reports/research/fixture_pullback_15m-parameter-sweep.json"
    )
    assert "Do not globally reject a single factor" in "\n".join(state["controller_rules"])
    assert "global factor bans" in result.memory_packet


def test_research_control_prioritizes_router_strict_data_blocker(
    sample_workspace: Path,
) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    promotion_path = (
        sample_workspace / "reports" / "research" / "fixture_pullback_15m-promotion.json"
    )
    promotion_path.parent.mkdir(parents=True, exist_ok=True)
    promotion_path.write_text(
        json.dumps(
            {
                "status": "blocked",
                "ready": False,
                "gate_summary": {
                    "blocked_checks": ["strict_data"],
                    "warning_checks": [],
                    "paper_ready_pass": False,
                },
                "evidence_acquisition_tier": "cached_live",
                "checks": [
                    {
                        "name": "strict_data",
                        "status": "blocked",
                        "message": (
                            "Router promotion requires research_strict or paper_ready data; "
                            "acquisition_tier=cached_live is not paper-ready"
                        ),
                        "details": {
                            "evidence_acquisition_tier": "cached_live",
                            "warnings": ["cache_data_used", "iex_feed_not_full_market_sip"],
                            "next_actions": [
                                (
                                    "validate the IEX-derived result against full-market/SIP "
                                    "data or a second provider"
                                )
                            ],
                        },
                    }
                ],
                "selected_route": {
                    "route": {"label": "open_reversal:test_route"},
                    "quality_flags": ["does_not_beat_ex_post_best_symbol"],
                    "out_of_sample": {
                        "annualized_return_pct": 68.1,
                        "sharpe_ratio": 2.14,
                        "max_drawdown_pct": -9.6,
                        "round_trips": 56,
                    },
                    "full_window": {
                        "annualized_return_pct": 33.1,
                        "sharpe_ratio": 1.28,
                        "max_drawdown_pct": -16.2,
                        "round_trips": 141,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = update_research_control(spec_path, sample_workspace)

    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["current_best"]["candidate_name"] == "open_reversal:test_route"
    assert state["current_best"]["metrics"]["oos_sharpe_ratio"] == 2.14
    assert state["promotion_state"]["blocked_checks"] == ["strict_data"]
    assert state["promotion_state"]["strict_data"]["status"] == "blocked"
    assert state["next_actions"][0].startswith("validate the IEX-derived result")
    assert "pause broad parameter search" in "; ".join(state["next_actions"])
    assert "Data blocker" in result.memory_packet
    assert "oos_sharpe_ratio" in result.memory_packet


def test_parameter_sweep_cli_refreshes_research_control_memory(
    sample_workspace: Path,
    monkeypatch,
    preregister_iteration_dossier,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    preregister_iteration_dossier(spec_path, candidate_count=2)
    init_research_brief(spec_path, sample_workspace, search_budget=2)

    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "parameter-sweep",
            str(spec_path),
            "--param",
            "risk.take_profit_pct=1.5,2.0",
            "--max-candidates",
            "2",
            "--write-top",
            "0",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "memory:" in result.output
    payload = json.loads(
        (
            sample_workspace / "reports" / "research" / "fixture_pullback_15m-parameter-sweep.json"
        ).read_text(encoding="utf-8")
    )
    trial = payload["trial_ledger"]["trials"][0]
    assert trial["parent_trial_id"] == "fixture_pullback_15m-source"
    assert trial["change_summary"].startswith("changed ")
    assert trial["lesson_tags"]
    assert (
        sample_workspace / "reports" / "research" / "control" / "fixture_pullback_15m-memory.md"
    ).exists()


def test_research_control_cli_writes_state_and_memory(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    init_research_brief(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
        sample_workspace,
    )

    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "research-control",
            str(sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "[DEPRECATED]" in result.output
    assert "strategy evidence complete" in result.output
    assert (
        sample_workspace / "reports" / "research" / "control" / "fixture_pullback_15m-state.json"
    ).exists()


def test_claude_prompt_hook_injects_memory_from_real_paths(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available in this Windows test environment")

    memory_dir = sample_workspace / "reports" / "research" / "control"
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_path = memory_dir / "fixture_pullback_15m-memory.md"
    memory_path.write_text(
        "# Research Memory: fixture_pullback_15m\n- Next: avoid repeated stop loss grid\n",
        encoding="utf-8",
    )
    verify_dir = sample_workspace / "reports" / "harness" / "verify"
    verify_dir.mkdir(parents=True, exist_ok=True)
    (verify_dir / "fixture_pullback_15m.json").write_text(
        json.dumps({"strategy_name": "fixture_pullback_15m", "overall": "warning"}),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env["OC_ROOT"] = str(sample_workspace)
    completed = subprocess.run(
        [bash, str(repo_root / ".claude" / "hooks" / "UserPromptSubmit-harness-context.sh")],
        input=json.dumps(
            {
                "prompt": (
                    "optimize strategy_specs/drafts/fixture_pullback_15m.yaml with a bounded sweep"
                )
            }
        ),
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )

    payload = json.loads(completed.stdout)
    assert "Research memory for 'fixture_pullback_15m'" in payload["prompt"]
    assert "avoid repeated stop loss grid" in payload["prompt"]
    assert "Last harness verify for 'fixture_pullback_15m': warning" in payload["prompt"]
