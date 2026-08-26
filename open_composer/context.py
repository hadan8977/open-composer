from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from open_composer.config import ensure_dir, project_root
from open_composer.models.event import EventRecord, SignalContext
from open_composer.models.signal import Signal
from open_composer.storage import find_signal, write_json


def build_signal_context(
    signal_id: str,
    root: Path | None = None,
    max_records: int = 5,
) -> SignalContext:
    base = root or project_root()
    signal = find_signal(signal_id, base)
    events = _load_event_records(base / "data" / "raw" / "events")
    macro = _load_event_records(base / "data" / "raw" / "macro")
    if not events and not macro:
        events.extend(_load_fixture_context(base, include_macro=False))
        macro.extend(_load_fixture_context(base, include_macro=True))
    context = _context_from_records(signal, events, macro, max_records)
    write_json(base / "reports" / "context" / f"{signal.id}.json", context)
    _write_context_markdown(base / "reports" / "context" / f"{signal.id}.md", context)
    return context


def _context_from_records(
    signal: Signal,
    events: list[EventRecord],
    macro: list[EventRecord],
    max_records: int,
) -> SignalContext:
    eligible_events = [
        event
        for event in events
        if event.symbol in {signal.symbol, "SPY", "QQQ"}
        and _event_visible_at(event) <= signal.timestamp
    ]
    eligible_news = [
        event
        for event in eligible_events
        if event.source in {"alpha_vantage", "gdelt"} or event.event_type.endswith("news")
    ]
    eligible_macro = [
        event
        for event in macro
        if event.symbol
        in {
            "FED",
            "DGS10",
            "FEDFUNDS",
            "CPIAUCSL",
            "UNRATE",
            "NQ_COT",
            "ES_COT",
            "VX_COT",
        }
        and _event_visible_at(event) <= signal.timestamp
    ]
    return SignalContext(
        signal_id=signal.id,
        symbol=signal.symbol,
        events=_top_relevant(eligible_events, max_records),
        news=_top_relevant(eligible_news, max_records),
        macro=_top_relevant(eligible_macro, max_records),
        notes=["Context excludes records not visible by the signal timestamp."],
    )


def _top_relevant(records: list[EventRecord], max_records: int) -> list[EventRecord]:
    return sorted(
        records, key=lambda item: (item.relevance_score, _event_visible_at(item)), reverse=True
    )[:max_records]


def _event_visible_at(event: EventRecord) -> datetime:
    if event.visible_at is not None:
        return event.visible_at
    return max(event.published_at, event.fetched_at)


def _load_event_records(path: Path) -> list[EventRecord]:
    if not path.exists():
        return []
    records: list[EventRecord] = []
    files = sorted(path.rglob("*.jsonl")) if path.is_dir() else [path]
    for file_path in files:
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(EventRecord.model_validate(json.loads(line)))
    return _dedupe(records)


def _load_fixture_context(root: Path, include_macro: bool) -> list[EventRecord]:
    records: list[EventRecord] = []
    relatives = (
        ["data/fixtures/capabilities/fred_macro.jsonl"]
        if include_macro
        else [
            "data/fixtures/capabilities/sec_filings.jsonl",
            "data/fixtures/capabilities/alpha_vantage_news.jsonl",
            "data/fixtures/capabilities/gdelt_news.jsonl",
        ]
    )
    for relative in relatives:
        records.extend(_load_event_records(root / relative))
    return records


def _dedupe(records: list[EventRecord]) -> list[EventRecord]:
    seen: set[str] = set()
    output: list[EventRecord] = []
    for record in sorted(records, key=_event_visible_at):
        if record.dedupe_key in seen:
            continue
        seen.add(record.dedupe_key)
        output.append(record)
    return output


def _write_context_markdown(path: Path, context: SignalContext) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Signal Context: {context.signal_id}",
        "",
        f"- Symbol: `{context.symbol}`",
        f"- Generated at: {context.generated_at.isoformat()}",
        "",
        "## Events",
        *_format_events(context.events),
        "",
        "## Macro",
        *_format_events(context.macro),
        "",
        "## News",
        *_format_events(context.news),
        "",
        "## Notes",
        *[f"- {note}" for note in context.notes],
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _format_events(records: list[EventRecord]) -> list[str]:
    if not records:
        return ["- None"]
    return [
        f"- `{record.source}` visible={_event_visible_at(record).isoformat()} "
        f"published={record.published_at.isoformat()} "
        f"{record.symbol} {record.title} "
        f"({record.sentiment}, relevance={record.relevance_score:.2f})"
        for record in records
    ]
