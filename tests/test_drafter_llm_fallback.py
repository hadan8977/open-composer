"""Tests for the LLM draft fallback behaviour in research.drafter."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from open_composer.research.drafter import draft_strategy_from_idea_with_status


def _failing_client(error_factory) -> SimpleNamespace:
    def parse(**_kwargs: object) -> None:
        raise error_factory()

    return SimpleNamespace(responses=SimpleNamespace(parse=parse))


def test_llm_draft_falls_back_on_502(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class GatewayError(Exception):
        status_code = 502

    client = _failing_client(lambda: GatewayError("Bad Gateway"))
    result = draft_strategy_from_idea_with_status(
        "QQQ pullback strategy",
        sample_workspace,
        use_llm=True,
        client=client,
    )

    assert result.used_llm is False
    assert result.fallback_reason is not None
    assert "GatewayError" in result.fallback_reason
    assert "Bad Gateway" in result.fallback_reason
    assert result.path.exists()

    plan_path = (
        sample_workspace / "reports" / "research" / f"{result.path.stem}-draft-research-plan.json"
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["llm_fallback_reason"] == result.fallback_reason


def test_llm_draft_records_no_fallback_when_disabled(sample_workspace: Path) -> None:
    result = draft_strategy_from_idea_with_status(
        "QQQ pullback strategy",
        sample_workspace,
        use_llm=False,
    )
    assert result.used_llm is False
    assert result.fallback_reason is None

    plan_path = (
        sample_workspace / "reports" / "research" / f"{result.path.stem}-draft-research-plan.json"
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert "llm_fallback_reason" not in plan


def test_llm_draft_skips_when_no_api_key_and_no_client(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = draft_strategy_from_idea_with_status(
        "QQQ pullback strategy",
        sample_workspace,
        use_llm=True,
    )
    # No client and no API key — _has_openai_config returns False, no LLM call attempted
    assert result.used_llm is False
    assert result.fallback_reason is None
