from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel

from open_composer.config import ensure_dir, project_root
from open_composer.models.signal import Signal


def model_to_record(model: BaseModel) -> dict:
    return model.model_dump(mode="json")


def append_jsonl(path: Path, rows: Iterable[BaseModel | dict]) -> Path:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            record = model_to_record(row) if isinstance(row, BaseModel) else row
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def write_json(path: Path, model: BaseModel | dict) -> Path:
    ensure_dir(path.parent)
    record = model_to_record(model) if isinstance(model, BaseModel) else model
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def iter_signal_records(root: Path | None = None) -> Iterable[dict]:
    base = root or project_root()
    for path in sorted((base / "signal_logs").glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    record["_log_path"] = str(path)
                    yield record


def find_signal(signal_id: str, root: Path | None = None) -> Signal:
    for record in iter_signal_records(root):
        if record.get("id") == signal_id:
            record.pop("_log_path", None)
            return Signal.model_validate(record)
    raise FileNotFoundError(f"signal not found: {signal_id}")
