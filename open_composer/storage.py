from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from open_composer.config import ensure_dir, project_root
from open_composer.json_utils import json_safe_payload
from open_composer.models.signal import Signal


def model_to_record(model: Any) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    if is_dataclass(model) and not isinstance(model, type):
        return asdict(model)
    return dict(model)


def append_jsonl(path: Path, rows: Iterable[BaseModel | dict | Any]) -> Path:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            record = row if isinstance(row, dict) else model_to_record(row)
            record = json_safe_payload(record)
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def write_json(path: Path, model: BaseModel | dict | Any) -> Path:
    ensure_dir(path.parent)
    record = model if isinstance(model, dict) else model_to_record(model)
    record = json_safe_payload(record)
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
