"""Harness spec diff — compare two StrategySpec versions by content hash."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from open_composer.config import project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.strategy_versions import load_strategy_versions, strategy_content_hash


def spec_diff(
    spec_path: Path,
    vs_hash: str,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Compare the current spec at spec_path against a previously recorded version hash.

    Returns a dict with:
        current_hash: hash of the current spec
        vs_hash: the comparison hash
        found: whether the comparison version was found in the version ledger
        changed_fields: list of top-level spec fields that changed (shallow diff)
        diff: field-by-field before/after values for changed fields
        summary: human-readable change summary
    """
    base = root or project_root()
    current_spec = load_strategy_spec(spec_path)
    current_dict = current_spec.model_dump(mode="json")
    current_hash = strategy_content_hash(current_spec)

    if current_hash == vs_hash:
        return {
            "current_hash": current_hash,
            "vs_hash": vs_hash,
            "found": True,
            "changed_fields": [],
            "diff": {},
            "summary": "No changes detected; spec hashes are identical.",
        }

    versions = load_strategy_versions(base, current_spec.name)
    vs_version = next(
        (v for v in versions if v.content_hash == vs_hash),
        None,
    )
    if vs_version is None:
        return {
            "current_hash": current_hash,
            "vs_hash": vs_hash,
            "found": False,
            "changed_fields": [],
            "diff": {},
            "summary": (
                f"Version hash {vs_hash!r} not found in version ledger for "
                f"strategy {current_spec.name!r}."
            ),
        }

    snapshot_path_str = vs_version.snapshot_path
    if not snapshot_path_str:
        return {
            "current_hash": current_hash,
            "vs_hash": vs_hash,
            "found": True,
            "changed_fields": [],
            "diff": {},
            "summary": "Version record found but snapshot_path is missing; cannot diff content.",
        }

    snapshot_path = Path(snapshot_path_str)
    if not snapshot_path.is_absolute():
        snapshot_path = base / snapshot_path

    if not snapshot_path.exists():
        return {
            "current_hash": current_hash,
            "vs_hash": vs_hash,
            "found": True,
            "changed_fields": [],
            "diff": {},
            "summary": f"Snapshot file not found at {snapshot_path}.",
        }

    vs_spec = load_strategy_spec(snapshot_path)
    vs_dict = vs_spec.model_dump(mode="json")

    changed = _shallow_diff(current_dict, vs_dict)
    summary_parts = [f"{field}: {v['before']!r} → {v['after']!r}" for field, v in changed.items()]
    summary = (
        "Changed fields: " + "; ".join(summary_parts)
        if summary_parts
        else "No top-level field changes detected."
    )

    return {
        "current_hash": current_hash,
        "vs_hash": vs_hash,
        "found": True,
        "changed_fields": sorted(changed),
        "diff": changed,
        "summary": summary,
        "vs_version_id": vs_version.version_id,
        "vs_created_at": vs_version.created_at.isoformat() if vs_version.created_at else None,
    }


def _shallow_diff(
    current: dict[str, Any],
    vs: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return a dict of field → {before, after} for fields that differ."""
    all_keys = set(current) | set(vs)
    return {
        key: {"before": vs.get(key), "after": current.get(key)}
        for key in all_keys
        if _serialize(current.get(key)) != _serialize(vs.get(key))
    }


def _serialize(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)
