from __future__ import annotations

from pathlib import Path

from open_composer.config import default_openai_model, openai_base_url, openai_base_url_source


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
