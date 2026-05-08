from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path


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


def default_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5.5")


def alpaca_paper_enabled() -> bool:
    return os.getenv("ALPACA_PAPER", "true").strip().lower() == "true"


def data_feed() -> str:
    return os.getenv("ALPACA_DATA_FEED", "iex")
