"""Shared ``MANIFEST.json`` writer for the Step 13-F open-factor-library
tables (``data/features/{alpha158,alpha101,alpha191,osap_price}/``).

docs/plan-step-13f-open-factor-library-import-and-screening-2026-09-09.zh.md
discipline section: "每张表都要有 MANIFEST.json(列名、来源库、公式版本、跳过项、
构建时间、行数)". One shared writer instead of four near-identical ad-hoc
JSON dumps in each build script, so the schema cannot drift between tables.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any


def write_feature_table_manifest(
    table_root: Path,
    *,
    table: str,
    source_library: str,
    formula_version: str,
    columns: list[str],
    skipped: list[dict[str, Any]],
    rows_by_year: dict[str, int],
    build_seconds_by_year: dict[str, float],
    notes: str = "",
) -> Path:
    """Write (overwrite) ``table_root / 'MANIFEST.json'``.

    ``rows_by_year``/``build_seconds_by_year`` are merged with whatever is
    already on disk (keyed by year) so re-running a subset of years (this
    box's memory discipline processes one year at a time, sometimes across
    several separate invocations) does not erase previously recorded years.
    """
    path = table_root / "MANIFEST.json"
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    merged_rows = dict(existing.get("rows_by_year", {}))
    merged_rows.update(rows_by_year)
    merged_seconds = dict(existing.get("build_seconds_by_year", {}))
    merged_seconds.update(build_seconds_by_year)

    record = {
        "table": table,
        "source_library": source_library,
        "formula_version": formula_version,
        "columns": columns,
        "column_count": len(columns),
        "skipped": skipped,
        "skipped_count": len(skipped),
        "rows_by_year": dict(sorted(merged_rows.items())),
        "row_count_total": sum(merged_rows.values()),
        "build_seconds_by_year": dict(sorted(merged_seconds.items())),
        "last_built_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "notes": notes,
    }
    table_root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_feature_table_manifest(table_root: Path) -> dict[str, Any]:
    path = table_root / "MANIFEST.json"
    if not path.exists():
        raise FileNotFoundError(f"no MANIFEST.json under {table_root}")
    return json.loads(path.read_text(encoding="utf-8"))
