from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from open_composer.config import default_openai_model, openai_base_url, openai_base_url_source
from open_composer.research import llm_backends


def test_openai_config_falls_back_to_codex_provider(tmp_path: Path, monkeypatch) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        """
model = "gpt-5.5"
model_provider = "ai_input"

[model_providers.ai_input]
base_url = "https://ai.input.im/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"
requires_openai_auth = false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    assert default_openai_model() == "gpt-5.5"
    assert openai_base_url() == "https://ai.input.im/v1"
    assert openai_base_url_source() == "codex"


def test_openai_env_accepts_trusted_compatible_gateway(tmp_path: Path, monkeypatch) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        """
model = "gpt-5.5"
model_provider = "ai_input"

[model_providers.ai_input]
base_url = "https://ai.input.im/v1"
wire_api = "responses"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://trusted-gateway.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "custom-model")

    assert default_openai_model() == "custom-model"
    assert openai_base_url() == "https://trusted-gateway.example/v1"
    assert openai_base_url_source() == "env"


def test_openai_backend_uses_configured_provider(monkeypatch) -> None:
    calls = {}

    class FakeResponses:
        def create(self, **kwargs):
            calls["request"] = kwargs
            return SimpleNamespace(output_text='{"score": 0.25}')

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self.responses = FakeResponses()

    monkeypatch.setattr(llm_backends, "openai_api_key", lambda: "test-key")
    monkeypatch.setattr(
        llm_backends,
        "openai_base_url",
        lambda: "https://compatible-provider.example/v1",
    )
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    result = llm_backends.OpenAIBackend().infer(
        model="test-model",
        prompt="Return a score.",
        input_payload={"headline": "Example"},
        output_schema={
            "type": "object",
            "properties": {"score": {"type": "number"}},
            "required": ["score"],
            "additionalProperties": False,
        },
    )

    assert result == {"score": 0.25}
    assert calls["client"] == {
        "api_key": "test-key",
        "base_url": "https://compatible-provider.example/v1",
    }
    assert calls["request"]["model"] == "test-model"
