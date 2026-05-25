from __future__ import annotations

from pathlib import Path

import pytest

import open_composer.agent_backend.codex_sdk as codex_sdk
from open_composer.agent_backend.codex_sdk import CodexAgentBackend
from open_composer.models.project import StrategyProjectCreate
from open_composer.projects import create_project, read_trace_tail


def test_codex_backend_reports_missing_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codex_sdk, "CodexAppServerClient", None)

    with pytest.raises(RuntimeError, match="OPEN_COMPOSER_AGENT_BACKEND=file_queue"):
        CodexAgentBackend()


def test_codex_backend_rejects_incompatible_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    class IncompleteClient:
        def start_session(self, **_: object) -> str:
            return "session"

    monkeypatch.setattr(codex_sdk, "CodexAppServerClient", IncompleteClient)

    with pytest.raises(RuntimeError, match="missing methods"):
        CodexAgentBackend()


def test_codex_backend_minimal_session_loop(
    sample_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeClient:
        def start_session(self, **kwargs: object) -> str:
            calls.append(("start_session", dict(kwargs)))
            return "codex-session-1"

        def send_user_message(self, **kwargs: object) -> None:
            calls.append(("send_user_message", dict(kwargs)))

        def is_session_alive(self, session_id: str) -> bool:
            calls.append(("is_session_alive", {"session_id": session_id}))
            return True

        def cancel_session(self, session_id: str) -> None:
            calls.append(("cancel_session", {"session_id": session_id}))

    monkeypatch.setattr(codex_sdk, "CodexAppServerClient", FakeClient)
    project, _ = create_project(
        StrategyProjectCreate(
            name="Codex Backend",
            thesis="Exercise Codex backend.",
            idea="Continue this project.",
        ),
        sample_workspace,
    )

    backend = CodexAgentBackend(model="gpt-test")
    command_id = backend.send_command(
        project.project_id,
        kind="advice",
        body="continue research",
        root=sample_workspace,
    )
    status = backend.status(project.project_id, sample_workspace)
    backend.stop(project.project_id, sample_workspace)

    assert command_id.startswith("q_")
    assert status.session_id == "codex-session-1"
    assert status.status == "idle"
    assert (sample_workspace / "projects" / project.project_id / "session-binding.yaml").exists()
    assert any(name == "send_user_message" for name, _ in calls)
    assert read_trace_tail(project.project_id, 5, sample_workspace)[-1].operation == (
        "codex_sdk_send_user_message"
    )
