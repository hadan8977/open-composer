from __future__ import annotations

import pytest
from typer.testing import CliRunner

from open_composer.agent_requests import (
    AgentRequestCreate,
    complete_agent_request,
    create_agent_request,
    list_agent_requests,
)
from open_composer.cli import app


def test_agent_request_file_lifecycle(sample_workspace) -> None:
    request = create_agent_request(
        AgentRequestCreate(
            task_type="research",
            title="Review sweep",
            prompt="Review reports/research/example.json",
            related_paths=["strategy_specs/drafts/qqq_pullback_15m.yaml"],
        ),
        sample_workspace,
    )

    completed = complete_agent_request(
        request.request_id,
        result_links=["reports/research/example.md"],
        root=sample_workspace,
    )

    assert request.request_id.startswith("agentreq_")
    assert list_agent_requests(sample_workspace)[0].request_id == request.request_id
    assert completed.status == "completed"
    assert completed.result_links == ["reports/research/example.md"]
    assert (sample_workspace / "reports" / "agent_requests" / f"{request.request_id}.json").exists()


def test_agent_request_rejects_path_traversal(sample_workspace) -> None:
    with pytest.raises(ValueError, match="workspace-relative"):
        create_agent_request(
            AgentRequestCreate(
                title="Bad path",
                prompt="Bad path",
                related_paths=["/etc/passwd"],
            ),
            sample_workspace,
        )
    with pytest.raises(ValueError, match="stay within"):
        create_agent_request(
            AgentRequestCreate(
                title="Bad path",
                prompt="Bad path",
                related_paths=["../outside"],
            ),
            sample_workspace,
        )


def test_agent_request_cli_creates_request(sample_workspace, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        [
            "agent",
            "request-create",
            "--title",
            "Review sweep",
            "--prompt",
            "Review reports/research/example.json",
            "--related-path",
            "strategy_specs/drafts/qqq_pullback_15m.yaml",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "agent request written" in result.output
    assert len(list_agent_requests(sample_workspace)) == 1
