from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from open_composer.config import ensure_dir
from open_composer.storage import append_jsonl, write_json

RESEARCH_INDEX_PATH = Path("reports/research/index.jsonl")


class ResearchArtifactWriter:
    def __init__(self, root: Path) -> None:
        self.root = root

    def json(self, path: Path, payload: BaseModel | dict[str, Any]) -> Path:
        return write_json(path, payload)

    def markdown(self, path: Path, text: str) -> Path:
        ensure_dir(path.parent)
        path.write_text(text, encoding="utf-8")
        return path

    def append_index(self, record: BaseModel | dict[str, Any]) -> Path:
        return append_research_run_index(self.root, record)


def research_report_paths(root: Path, strategy_name: str, stem: str) -> tuple[Path, Path]:
    base = root / "reports" / "research"
    return base / f"{strategy_name}-{stem}.md", base / f"{strategy_name}-{stem}.json"


def append_research_run_index(root: Path, record: BaseModel | dict[str, Any]) -> Path:
    path = root / RESEARCH_INDEX_PATH
    return append_jsonl(path, [record])


def load_research_run_index(root: Path) -> list[dict[str, Any]]:
    path = root / RESEARCH_INDEX_PATH
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                records.append(raw)
    return records
