from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from open_composer.config import ensure_dir, project_root
from open_composer.research.factor_library import get_factor


def append_lineage(
    factor_id: str,
    spec_path: str | Path,
    *,
    added_by: str = "cli",
    creation_thesis: str = "",
    root: Path | None = None,
) -> Path:
    base = root or project_root()
    factor = get_factor(factor_id)
    out_dir = ensure_dir(base / "reports" / "factors" / factor_id)
    out_path = out_dir / "lineage.json"
    now = datetime.now(UTC).isoformat()
    if out_path.exists():
        data = json.loads(out_path.read_text(encoding="utf-8"))
    else:
        data = {
            "factor_id": factor_id,
            "created_at": now,
            "definition_source": _definition_source(factor_id),
            "creation_thesis": creation_thesis,
            "source_card_ids": list(factor.source_card_ids),
            "parent_factor_ids": [],
            "used_in_specs": [],
        }
    if creation_thesis and not data.get("creation_thesis"):
        data["creation_thesis"] = creation_thesis
    rel_spec = _relpath(Path(spec_path), base)
    used = data.setdefault("used_in_specs", [])
    if not any(isinstance(item, dict) and item.get("spec_path") == rel_spec for item in used):
        used.append({"spec_path": rel_spec, "added_at": now, "added_by": added_by})
    out_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


def _definition_source(factor_id: str) -> str:
    if factor_id.startswith("alpha101_"):
        return "alpha101"
    if factor_id.startswith("alpha158_"):
        return "alpha158"
    return "tactical_router"


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
