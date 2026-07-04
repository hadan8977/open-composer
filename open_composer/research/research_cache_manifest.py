from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.config import ensure_dir, project_root
from open_composer.storage import write_json

DEFAULT_LONGBRIDGE_SYMBOLS = [
    "QQQ",
    "TQQQ",
    "QLD",
    "SOXL",
    "USD",
    "SMH",
    "SOXX",
    "XLK",
    "IGV",
    "GLD",
    "BIL",
]
DEFAULT_RESEARCH_CACHE_DIR = Path("data/research/longbridge_adjusted_daily")
DEFAULT_MANIFEST_NAME = "manifest.json"


def manifest_path_for(output_dir: Path, root: Path | None = None) -> Path:
    base = root or project_root()
    resolved = output_dir if output_dir.is_absolute() else base / output_dir
    return resolved / DEFAULT_MANIFEST_NAME


def build_longbridge_research_cache_manifest(
    root: Path,
    *,
    output_dir: Path = DEFAULT_RESEARCH_CACHE_DIR,
    symbols: list[str] | None = None,
    requested_start: str | None = None,
    requested_end: str | None = None,
    source_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_dir = output_dir if output_dir.is_absolute() else root / output_dir
    source_by_symbol = {
        str(row.get("symbol", "")).upper(): row for row in source_rows or [] if row.get("symbol")
    }
    selected_symbols = symbols or sorted(_symbols_from_directory(resolved_dir))
    rows = []
    for raw_symbol in selected_symbols:
        symbol = raw_symbol.upper()
        path = resolved_dir / f"{symbol.lower()}_daily_longbridge_adjusted.csv"
        stats = price_csv_stats(path)
        source = source_by_symbol.get(symbol, {})
        rows.append(
            {
                "symbol": symbol,
                "path": str(path),
                "records": stats["records"],
                "first_timestamp": stats["first_timestamp"],
                "last_timestamp": stats["last_timestamp"],
                "sha256": sha256_file(path),
                "source_mode": source.get("source_mode", "existing_cache_manifest_only"),
                "chunks": source.get("chunks", []),
            }
        )
    return {
        "provider": "longbridge",
        "feed": "nasdaq_basic",
        "adjusted": True,
        "generated_at": datetime.now(UTC).isoformat(),
        "requested_start": requested_start,
        "requested_end": requested_end,
        "output_dir": str(resolved_dir),
        "comparison_discipline": (
            "Run oc data verify-research-cache before comparing historical artifacts; "
            "adjusted-cache refreshes can restate the full history."
        ),
        "symbols": rows,
    }


def write_longbridge_research_cache_manifest(
    root: Path,
    *,
    output_dir: Path = DEFAULT_RESEARCH_CACHE_DIR,
    symbols: list[str] | None = None,
    requested_start: str | None = None,
    requested_end: str | None = None,
    source_rows: list[dict[str, Any]] | None = None,
    manifest_path: Path | None = None,
) -> Path:
    resolved_dir = output_dir if output_dir.is_absolute() else root / output_dir
    payload = build_longbridge_research_cache_manifest(
        root,
        output_dir=resolved_dir,
        symbols=symbols,
        requested_start=requested_start,
        requested_end=requested_end,
        source_rows=source_rows,
    )
    path = manifest_path or resolved_dir / DEFAULT_MANIFEST_NAME
    path = path if path.is_absolute() else root / path
    ensure_dir(path.parent)
    write_json(path, payload)
    return path


def verify_longbridge_research_cache_manifest(
    root: Path,
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    path = manifest_path or manifest_path_for(DEFAULT_RESEARCH_CACHE_DIR, root)
    path = path if path.is_absolute() else root / path
    manifest = json.loads(path.read_text(encoding="utf-8"))
    drift = []
    checked = []
    for row in manifest.get("symbols", []):
        expected_path = Path(row["path"])
        if not expected_path.is_absolute():
            expected_path = root / expected_path
        symbol = str(row["symbol"]).upper()
        if not expected_path.exists():
            drift.append(
                {"symbol": symbol, "field": "path", "expected": str(expected_path), "actual": None}
            )
            continue
        stats = price_csv_stats(expected_path)
        actual_sha = sha256_file(expected_path)
        checks = {
            "records": stats["records"],
            "first_timestamp": stats["first_timestamp"],
            "last_timestamp": stats["last_timestamp"],
            "sha256": actual_sha,
        }
        for field, actual in checks.items():
            expected = row.get(field)
            if expected != actual:
                drift.append(
                    {
                        "symbol": symbol,
                        "field": field,
                        "expected": expected,
                        "actual": actual,
                    }
                )
        checked.append(symbol)
    return {
        "report_type": "longbridge_research_cache_verify",
        "manifest_path": str(path),
        "provider": manifest.get("provider"),
        "output_dir": manifest.get("output_dir"),
        "checked_symbols": checked,
        "drift": drift,
        "passed": not drift,
        "comparison_discipline": manifest.get("comparison_discipline"),
    }


def price_csv_stats(path: Path) -> dict[str, Any]:
    frame = pd.read_csv(path)
    if "timestamp" not in frame.columns:
        raise ValueError(f"research cache file missing timestamp column: {path}")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    return {
        "records": int(len(frame)),
        "first_timestamp": timestamps.min().isoformat() if not frame.empty else None,
        "last_timestamp": timestamps.max().isoformat() if not frame.empty else None,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _symbols_from_directory(path: Path) -> list[str]:
    symbols = []
    for item in path.glob("*_daily_longbridge_adjusted.csv"):
        symbols.append(item.name.split("_daily_longbridge_adjusted.csv", maxsplit=1)[0].upper())
    return symbols
