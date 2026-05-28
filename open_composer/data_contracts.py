from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from open_composer.config import project_root
from open_composer.models.market_data import (
    DepthSnapshotRow,
    MarketDataKind,
    MarketDataManifest,
    OrderBookDeltaRow,
    QuoteTickRow,
    TradeTickRow,
)
from open_composer.storage import write_json


def validate_market_data_rows(path: Path, kind: MarketDataKind) -> list[Any]:
    records = _load_json_records(path)
    model = _row_model(kind)
    return [model.model_validate(record) for record in records]


def build_market_data_manifest(
    path: Path,
    kind: MarketDataKind,
    *,
    root: Path | None = None,
    symbol: str | None = None,
    venue: str = "",
    source: str = "local_fixture",
    paper_ready: bool = False,
) -> MarketDataManifest:
    base = root or project_root()
    resolved = path if path.is_absolute() else base / path
    rows = validate_market_data_rows(resolved, kind)
    if not rows:
        raise ValueError("market data fixture contains no rows")
    symbols = sorted({str(row.symbol) for row in rows})
    if symbol is not None and symbol not in symbols:
        raise ValueError(f"manifest symbol {symbol} not present in rows")
    quality_flags: list[str] = []
    if len(symbols) > 1:
        quality_flags.append("multi_symbol_file")
    timestamps = [row.timestamp for row in rows]
    if timestamps != sorted(timestamps):
        quality_flags.append("timestamps_not_monotonic")
    if kind in {"order_book_delta", "depth_snapshot"}:
        sequences = [getattr(row, "sequence", None) for row in rows]
        if any(sequence is None for sequence in sequences):
            quality_flags.append("sequence_missing")
        elif sequences != sorted(sequences):
            quality_flags.append("sequence_not_monotonic")
    return MarketDataManifest(
        kind=kind,
        path=_relative_label(resolved, base),
        symbol=symbol or symbols[0],
        venue=venue,
        first_timestamp=min(timestamps),
        last_timestamp=max(timestamps),
        row_count=len(rows),
        timezone="UTC",
        source=source,
        quality_flags=quality_flags,
        sha256=_sha256(resolved),
        paper_ready=paper_ready,
    )


def write_market_data_manifest(
    output_path: Path,
    manifest: MarketDataManifest,
) -> Path:
    return write_json(output_path, manifest)


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise ValueError(f"line {line_number}: expected object")
                rows.append(raw)
        return rows
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("rows"), list):
            return [row for row in raw["rows"] if isinstance(row, dict)]
        if isinstance(raw, list):
            return [row for row in raw if isinstance(row, dict)]
    raise ValueError("market data contracts support jsonl/json fixtures")


def _row_model(kind: MarketDataKind):
    if kind == "trade_tick":
        return TradeTickRow
    if kind == "quote_tick":
        return QuoteTickRow
    if kind == "order_book_delta":
        return OrderBookDeltaRow
    if kind == "depth_snapshot":
        return DepthSnapshotRow
    raise ValueError(f"unsupported market data contract kind: {kind}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_label(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
