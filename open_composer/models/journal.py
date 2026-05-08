from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TradeJournalEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    signal_id: str
    action: Literal["traded", "skipped", "watched"]
    notes: str = ""
    outcome: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def journal_id(signal_id: str, created_at: datetime) -> str:
    digest = hashlib.sha256(f"{signal_id}|{created_at.isoformat()}".encode()).hexdigest()
    return f"journal_{digest[:16]}"
