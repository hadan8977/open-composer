from __future__ import annotations

import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def project_root() -> Path:
    override = os.getenv("OPEN_COMPOSER_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path.cwd().resolve()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}"


def optional_env_status(name: str) -> str:
    return "set" if os.getenv(name) else "missing"


def codex_config_path() -> Path:
    return Path(os.getenv("CODEX_HOME", "~/.codex")).expanduser() / "config.toml"


def codex_model_provider_config() -> dict[str, Any]:
    path = codex_config_path()
    if not path.exists():
        return {}
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    provider_name = config.get("model_provider")
    providers = config.get("model_providers", {})
    provider = providers.get(provider_name, {}) if provider_name else {}
    if not isinstance(provider, dict):
        provider = {}
    result = dict(provider)
    if config.get("model"):
        result["model"] = config["model"]
    if provider_name:
        result["provider_name"] = provider_name
    return result


def default_openai_model() -> str:
    return os.getenv("OPENAI_MODEL") or str(codex_model_provider_config().get("model") or "gpt-5.5")


def openai_api_key_env_name() -> str:
    return str(codex_model_provider_config().get("env_key") or "OPENAI_API_KEY")


def openai_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY") or os.getenv(openai_api_key_env_name())


def openai_base_url() -> str | None:
    return os.getenv("OPENAI_BASE_URL") or _codex_responses_base_url()


def openai_base_url_source() -> str:
    if os.getenv("OPENAI_BASE_URL"):
        return "env"
    if _codex_responses_base_url():
        return "codex"
    return "missing"


def _codex_responses_base_url() -> str | None:
    provider = codex_model_provider_config()
    base_url = provider.get("base_url")
    if not base_url:
        return None
    wire_api = provider.get("wire_api")
    if wire_api and wire_api != "responses":
        return None
    return str(base_url)


def alpaca_paper_enabled() -> bool:
    return os.getenv("ALPACA_PAPER", "true").strip().lower() == "true"


def alpaca_api_key_id() -> str | None:
    return os.getenv("ALPACA_API_KEY_ID")


def alpaca_api_secret_key() -> str | None:
    return os.getenv("ALPACA_API_SECRET_KEY")


def alpaca_api_base_url() -> str:
    return os.getenv("ALPACA_API_BASE_URL", "https://paper-api.alpaca.markets/v2")


def data_feed() -> str:
    return os.getenv("ALPACA_DATA_FEED", "iex")
