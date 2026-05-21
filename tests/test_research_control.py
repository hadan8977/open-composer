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


def test_research_control_reduces_sweep_into_state_and_memory(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
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
    assert len(result.memory_packet.encode("utf-8")) <= 1024
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["strategy_name"] == "qqq_pullback_15m"
    assert state["current_best"]["params"]
    assert state["effective_combinations"]
    assert state["source_artifacts"]["parameter_sweep"] == (
        "reports/research/qqq_pullback_15m-parameter-sweep.json"
    )
    assert "Do not globally reject a single factor" in "\n".join(state["controller_rules"])
    assert "global factor bans" in result.memory_packet


def test_parameter_sweep_cli_refreshes_research_control_memory(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "parameter-sweep",
            str(sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"),
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
            sample_workspace / "reports" / "research" / "qqq_pullback_15m-parameter-sweep.json"
        ).read_text(encoding="utf-8")
    )
    trial = payload["trial_ledger"]["trials"][0]
    assert trial["parent_trial_id"] == "qqq_pullback_15m-source"
    assert trial["change_summary"].startswith("changed ")
    assert trial["lesson_tags"]
    assert (
        sample_workspace / "reports" / "research" / "control" / "qqq_pullback_15m-memory.md"
    ).exists()


def test_research_control_cli_writes_state_and_memory(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "research-control",
            str(sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "research control updated" in result.output
    assert (
        sample_workspace / "reports" / "research" / "control" / "qqq_pullback_15m-state.json"
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
    memory_path = memory_dir / "qqq_pullback_15m-memory.md"
    memory_path.write_text(
        "# Research Memory: qqq_pullback_15m\n- Next: avoid repeated stop loss grid\n",
        encoding="utf-8",
    )
    verify_dir = sample_workspace / "reports" / "harness" / "verify"
    verify_dir.mkdir(parents=True, exist_ok=True)
    (verify_dir / "qqq_pullback_15m.json").write_text(
        json.dumps({"strategy_name": "qqq_pullback_15m", "overall": "warning"}),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env["OC_ROOT"] = str(sample_workspace)
    completed = subprocess.run(
        [bash, str(repo_root / ".claude" / "hooks" / "UserPromptSubmit-harness-context.sh")],
        input=json.dumps(
            {
                "prompt": (
                    "optimize strategy_specs/drafts/qqq_pullback_15m.yaml "
                    "with a bounded sweep"
                )
            }
        ),
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )

    payload = json.loads(completed.stdout)
    assert "Research memory for 'qqq_pullback_15m'" in payload["prompt"]
    assert "avoid repeated stop loss grid" in payload["prompt"]
    assert "Last harness verify for 'qqq_pullback_15m': warning" in payload["prompt"]
