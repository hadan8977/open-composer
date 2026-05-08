from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from open_composer.models.journal import TradeJournalEntry, journal_id
from open_composer.storage import write_json


def add_journal_entry(
    root: Path,
    signal_id: str,
    action: str,
    notes: str = "",
    outcome: str = "",
) -> TradeJournalEntry:
    created_at = datetime.now(UTC)
    entry = TradeJournalEntry(
        id=journal_id(signal_id, created_at),
        signal_id=signal_id,
        action=action,  # type: ignore[arg-type]
        notes=notes,
        outcome=outcome,
        created_at=created_at,
    )
    path = root / "journal" / f"{created_at.date().isoformat()}-{signal_id}.json"
    write_json(path, entry)
    return entry
