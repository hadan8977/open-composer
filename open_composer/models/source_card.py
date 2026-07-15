"""SourceCard — point-in-time citation record for unstable external claims.

Source cards back every claim a strategy makes about broker APIs, exchange rules,
data provider behavior, methodology papers, or recent platform docs. They are
written by the source-researcher skill and validated by the harness verifier.

One JSON object per line in ``reports/harness/source_cards/{strategy}.jsonl``.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceType = Literal[
    "broker_official_docs",
    "exchange_official_docs",
    "provider_official_docs",
    "regulatory_docs",
    "paper",
    "platform_docs",
    "industry_standard",
    "unverified",
]
VerificationStatus = Literal["source_verified", "unverified"]


class SourceCard(BaseModel):
    """A single point-in-time citation."""

    model_config = ConfigDict(extra="allow")

    claim_id: str = Field(min_length=1)
    iteration_id: str | None = None
    verification_status: VerificationStatus = "unverified"
    verified_at: str | None = None
    verification_method: str | None = None
    claim: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    source_type: SourceType
    accessed_at: str  # YYYY-MM-DD
    applies_to: list[str] = Field(default_factory=list)
    impact_on_spec: str = ""
    limitations: str = ""
    expires_at: str | None = None

    @field_validator("accessed_at")
    @classmethod
    def _validate_accessed_at(cls, value: str) -> str:
        _dt.date.fromisoformat(value)
        return value

    @field_validator("limitations", mode="before")
    @classmethod
    def _normalize_limitations(cls, value: Any) -> str:
        if isinstance(value, list):
            return "; ".join(str(item) for item in value if item is not None)
        if value is None:
            return ""
        return str(value)

    @field_validator("expires_at")
    @classmethod
    def _validate_expires_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        _dt.date.fromisoformat(value)
        return value

    @field_validator("verified_at")
    @classmethod
    def _validate_verified_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


# ---------------------------------------------------------------------------
# Loading / staleness checks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceCardStatus:
    card: SourceCard
    stale: bool
    expired: bool
    age_days: int


def load_source_cards(strategy_name: str, root: Path) -> list[SourceCard]:
    """Load every source card recorded for the strategy."""
    path = root / "reports" / "harness" / "source_cards" / f"{strategy_name}.jsonl"
    if not path.exists():
        return []
    cards: list[SourceCard] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            msg = f"{path.name}:{line_number}: invalid JSON: {exc}"
            raise ValueError(msg) from exc
        cards.append(SourceCard.model_validate(data))
    return cards


_DEFAULT_STALENESS_DAYS = {
    "broker_official_docs": 90,
    "exchange_official_docs": 180,
    "provider_official_docs": 180,
    "regulatory_docs": 365,
    "paper": 730,
    "platform_docs": 180,
    "industry_standard": 365,
    "unverified": 30,
}


def _staleness_threshold(source_type: str, root: Path) -> int:
    """Read staleness_days for a source type from harness/source_policy.yaml.

    Falls back to a sensible default if the policy file does not declare a value.
    """
    import yaml

    policy_path = root / "harness" / "source_policy.yaml"
    if policy_path.exists():
        try:
            data = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        per_type = (data.get("staleness_days") or {}) if isinstance(data, dict) else {}
        value = per_type.get(source_type) if isinstance(per_type, dict) else None
        if isinstance(value, int) and value > 0:
            return value
    return _DEFAULT_STALENESS_DAYS.get(source_type, 90)


def check_source_card(
    card: SourceCard, root: Path, today: _dt.date | None = None
) -> SourceCardStatus:
    """Classify a card as fresh / stale / expired against the policy."""
    today = today or _dt.date.today()
    accessed = _dt.date.fromisoformat(card.accessed_at)
    age = (today - accessed).days
    threshold = _staleness_threshold(card.source_type, root)
    expired = False
    if card.expires_at:
        try:
            expired = _dt.date.fromisoformat(card.expires_at) < today
        except ValueError:
            expired = False
    stale = age > threshold or expired
    return SourceCardStatus(card=card, stale=stale, expired=expired, age_days=age)


def evaluate_source_cards(
    strategy_name: str, root: Path, today: _dt.date | None = None
) -> list[SourceCardStatus]:
    """Load and classify all source cards for a strategy."""
    return [check_source_card(c, root, today) for c in load_source_cards(strategy_name, root)]
