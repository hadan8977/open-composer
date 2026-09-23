"""Direction registry and search log: the durable record of what has been
searched, found, confirmed, tested, and ruled out (2026-09-23).

The owner's instruction on 2026-09-23: search much more widely -- posts,
forums, code, and papers, not only a few platforms -- keep good records and
confirm each direction, so nothing gets searched or tested twice.

Three append-only JSONL files under ``reports/research/harvest/``:

* ``directions.jsonl`` -- one row per candidate direction (factor, intraday
  rule, model, ETF rule, event, ...). Rows are keyed by ``id``; when a
  direction changes status a new row with the same ``id`` is appended and the
  last row wins, so the file keeps its own history.
* ``search-log.jsonl`` -- one row per search pass (channel, tool, query), so
  coverage is visible and a later session does not rerun the same queries.
* ``channels.jsonl`` -- the places worth searching (owner, 2026-09-23: also
  search for search routes -- forums, groups, newsletters, projects -- in
  several levels, and record them). Level 0 is a seed already in use, level 1
  was found by searching for channels, level 2 was found inside a level-1
  channel (a blogroll, a wiki, a curated list, who an account follows). Same
  last-row-wins rule as directions.

``check_direction`` is the "have we done this before?" query: run it before
opening any new direction. It also reads the hypothesis cards and
``trial-families.json`` so directions tested before this registry existed
still surface.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

HARVEST_DIR = Path("reports") / "research" / "harvest"
DIRECTIONS_FILE = "directions.jsonl"
SEARCH_LOG_FILE = "search-log.jsonl"
CHANNELS_FILE = "channels.jsonl"

DirectionStatus = Literal[
    "harvested",  # found, not yet confirmed
    "triaged",  # direction confirmed: goal fit, executable subset, cheapest test, stop
    "queued",  # scheduled into a test batch
    "testing",
    "passed",  # cleared the frozen gates
    "partial",  # useful only as an overlay / under a narrower claim
    "refuted",  # tested under our protocol and failed
    "not_executable",  # effect is real but outside our execution envelope
    "evidence_too_weak",  # dropped at triage on source quality, never tested
    "parked",  # deliberately deferred (budget, data, hardware, owner decision)
    "duplicate",  # same mechanism as another direction
]
Category = Literal[
    "factor",
    "hf_factor",
    "intraday",
    "etf_rule",
    "levered_etf",
    "event",
    "alt_data",
    "text_llm",
    "model",
    "sizing",
    "crypto",
    "options",
    "other",
]
SourceKind = Literal[
    "paper",
    "post",
    "repo",
    "platform",
    "live_record",
    "dataset",
    "docs",
    "internal",
]

#: Statuses that end a direction's life until something new appears; each
#: needs a verdict, evidence, and the concrete condition that would reopen it.
TERMINAL_STATUSES = frozenset(
    {"passed", "partial", "refuted", "not_executable", "evidence_too_weak", "parked"}
)
#: Statuses that need a direction confirmation before compute is spent.
CONFIRMED_STATUSES = frozenset({"triaged", "queued", "testing"})
TRIAGE_KEYS = ("goal_fit", "executable_subset", "cheapest_test", "stop_condition")


class DirectionSource(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str = Field(min_length=4)
    kind: SourceKind
    title: str = ""
    accessed_at: str | None = None
    source_card_id: str | None = None

    @field_validator("accessed_at")
    @classmethod
    def _iso_date(cls, value: str | None) -> str | None:
        if value:
            date.fromisoformat(value)
        return value


class Direction(BaseModel):
    """One candidate direction. ``family_key`` names the economic mechanism
    (e.g. ``levered_sector_trend``) so two sources describing the same thing
    collapse onto one line of work."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(pattern=r"^dir:[a-z0-9_]+$")
    name: str = Field(min_length=3)
    category: Category
    family_key: str = Field(pattern=r"^[a-z0-9_]+$")
    status: DirectionStatus
    updated: str
    aliases: list[str] = Field(default_factory=list)
    sources: list[DirectionSource] = Field(default_factory=list)
    claim: str = ""
    data_needs: str = ""
    executable_for_us: str = ""
    triage: dict[str, str] = Field(default_factory=dict)
    verdict: str = ""
    evidence: list[str] = Field(default_factory=list)
    reopen_if: str = ""
    duplicate_of: str | None = None
    found_by: list[str] = Field(default_factory=list)

    @field_validator("updated")
    @classmethod
    def _iso_updated(cls, value: str) -> str:
        date.fromisoformat(value)
        return value


class SearchLogEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(pattern=r"^search:[A-Za-z0-9_.:-]+$")
    date: str
    channel: str = Field(min_length=1)  # "x" is a channel
    tool: str = Field(min_length=2)
    query: str = Field(min_length=2)
    results_seen: int | None = None
    new_directions: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("date")
    @classmethod
    def _iso_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value


ChannelKind = Literal[
    "forum",
    "subreddit",
    "chat_group",
    "x_account",
    "x_list",
    "newsletter",
    "blog",
    "aggregator",
    "paper_feed",
    "data_library",
    "backtest_database",
    "code_hub",
    "curated_list",
    "video_podcast",
    "search_tool",
    "other",
]
ChannelStatus = Literal[
    "candidate",  # found, not yet read
    "active",  # in the regular search rotation
    "watch",  # worth an occasional pass
    "rejected",  # read, low signal for our goal
    "blocked",  # cannot be read from this server
]
ChannelAccess = Literal["open", "login", "invite", "paid", "blocked_from_server"]


class Channel(BaseModel):
    """A place to search. ``parent`` names the channel (``chan:...``) or search
    (``search:...``) it was found through; together with ``level`` it keeps
    the discovery tree."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(pattern=r"^chan:[a-z0-9_]+$")
    name: str = Field(min_length=2)
    kind: ChannelKind
    url: str = Field(min_length=4)
    level: int = Field(ge=0, le=3)
    status: ChannelStatus
    access: ChannelAccess
    updated: str
    parent: str | None = None
    read_via: str = ""
    topics: list[str] = Field(default_factory=list)
    activity: str = ""
    signal: str = ""
    verdict: str = ""
    found_by: list[str] = Field(default_factory=list)

    @field_validator("updated")
    @classmethod
    def _iso_updated(cls, value: str) -> str:
        date.fromisoformat(value)
        return value


def harvest_dir(root: Path) -> Path:
    return root / HARVEST_DIR


def _read_jsonl(path: Path) -> list[tuple[int, dict[str, Any] | None, str]]:
    rows: list[tuple[int, dict[str, Any] | None, str]] = []
    if not path.is_file():
        return rows
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            rows.append((number, None, f"invalid JSON: {exc}"))
            continue
        if not isinstance(payload, dict):
            rows.append((number, None, "row is not a JSON object"))
            continue
        rows.append((number, payload, ""))
    return rows


def load_directions(root: Path) -> dict[str, Direction]:
    """Current state per direction id (the last row for an id wins).
    Rows that fail validation are skipped here; ``validate_registry``
    reports them."""
    current: dict[str, Direction] = {}
    for _, payload, error in _read_jsonl(harvest_dir(root) / DIRECTIONS_FILE):
        if error or payload is None:
            continue
        try:
            direction = Direction(**payload)
        except ValidationError:
            continue
        current[direction.id] = direction
    return current


def load_channels(root: Path) -> dict[str, Channel]:
    """Current state per channel id (the last row for an id wins)."""
    current: dict[str, Channel] = {}
    for _, payload, error in _read_jsonl(harvest_dir(root) / CHANNELS_FILE):
        if error or payload is None:
            continue
        try:
            channel = Channel(**payload)
        except ValidationError:
            continue
        current[channel.id] = channel
    return current


def _channel_problems(root: Path) -> list[str]:
    problems: list[str] = []
    for number, payload, error in _read_jsonl(harvest_dir(root) / CHANNELS_FILE):
        where = f"{CHANNELS_FILE}:{number}"
        if error or payload is None:
            problems.append(f"{where}: {error}")
            continue
        try:
            Channel(**payload)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(part) for part in first.get("loc", ()))
            problems.append(f"{where}: {loc}: {first.get('msg')}")
    current = load_channels(root)
    for channel in current.values():
        where = f"{channel.id} (status={channel.status})"
        if channel.level > 0 and not (channel.parent or channel.found_by):
            problems.append(f"{where}: level {channel.level} needs parent or found_by")
        if channel.parent and channel.parent.startswith("chan:") and channel.parent not in current:
            problems.append(f"{where}: parent {channel.parent} is unknown")
        if channel.status in ("active", "watch") and not channel.read_via.strip():
            problems.append(f"{where}: needs read_via (how we read it)")
        if channel.status in ("rejected", "blocked") and not channel.verdict.strip():
            problems.append(f"{where}: needs a verdict")
    return problems


def load_search_log(root: Path) -> list[SearchLogEntry]:
    entries: list[SearchLogEntry] = []
    for _, payload, error in _read_jsonl(harvest_dir(root) / SEARCH_LOG_FILE):
        if error or payload is None:
            continue
        try:
            entries.append(SearchLogEntry(**payload))
        except ValidationError:
            continue
    return entries


def validate_registry(root: Path) -> list[str]:
    """Every problem found in both files; an empty list means valid."""
    problems: list[str] = []
    directions_path = harvest_dir(root) / DIRECTIONS_FILE
    for number, payload, error in _read_jsonl(directions_path):
        where = f"{DIRECTIONS_FILE}:{number}"
        if error or payload is None:
            problems.append(f"{where}: {error}")
            continue
        try:
            Direction(**payload)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(part) for part in first.get("loc", ()))
            problems.append(f"{where}: {loc}: {first.get('msg')}")
    current = load_directions(root)
    for direction in current.values():
        where = f"{direction.id} (status={direction.status})"
        if direction.status in TERMINAL_STATUSES:
            if not direction.verdict.strip():
                problems.append(f"{where}: terminal status needs a verdict")
            if not direction.evidence:
                problems.append(f"{where}: terminal status needs evidence links")
            if not direction.reopen_if.strip():
                problems.append(f"{where}: terminal status needs reopen_if")
        if direction.status in CONFIRMED_STATUSES:
            missing = [key for key in TRIAGE_KEYS if not direction.triage.get(key, "").strip()]
            if missing:
                problems.append(f"{where}: direction confirmation missing {missing}")
        if direction.status == "duplicate":
            if not direction.duplicate_of:
                problems.append(f"{where}: duplicate needs duplicate_of")
            elif direction.duplicate_of not in current:
                problems.append(f"{where}: duplicate_of {direction.duplicate_of} is unknown")
        if direction.status != "harvested" and not direction.sources and not direction.evidence:
            problems.append(f"{where}: needs at least one source or evidence link")
    search_ids: Counter[str] = Counter()
    for number, payload, error in _read_jsonl(harvest_dir(root) / SEARCH_LOG_FILE):
        where = f"{SEARCH_LOG_FILE}:{number}"
        if error or payload is None:
            problems.append(f"{where}: {error}")
            continue
        try:
            entry = SearchLogEntry(**payload)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(part) for part in first.get("loc", ()))
            problems.append(f"{where}: {loc}: {first.get('msg')}")
            continue
        search_ids[entry.id] += 1
        unknown = [ref for ref in entry.new_directions if ref not in current]
        if unknown:
            problems.append(f"{where}: new_directions not in the registry: {unknown}")
    problems.extend(
        f"{SEARCH_LOG_FILE}: duplicate search id {search_id}"
        for search_id, count in sorted(search_ids.items())
        if count > 1
    )
    problems.extend(_channel_problems(root))
    return problems


_TOKEN = re.compile(r"[a-z0-9]+|[一-鿿]+")
# Function words would otherwise make "leverage for the long run" a likely repeat of
# any direction whose name contains "for" and "the".
_STOPWORDS = frozenset(
    "an and are as at be by for from in into is it its of on or over than the their "
    "to via vs with without".split()
)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN.findall(text.lower())
        if len(token) > 1 and token not in _STOPWORDS
    }


@dataclass(frozen=True)
class DirectionMatch:
    kind: str  # "registry" | "hypothesis_card" | "trial_family" | "channel"
    ref: str
    title: str
    status: str
    verdict: str
    score: float


def _direction_text(direction: Direction) -> str:
    parts = [direction.id, direction.name, direction.family_key, direction.claim]
    parts.extend(direction.aliases)
    for source in direction.sources:
        parts.extend([source.url, source.title])
    return " ".join(parts)


def _score(query: set[str], text: str) -> float:
    if not query:
        return 0.0
    return len(query & _tokens(text)) / len(query)


def check_direction(root: Path, terms: str, *, limit: int = 10) -> list[DirectionMatch]:
    """Best prior matches for ``terms`` across the registry, the hypothesis
    cards, and ``trial-families.json``. Anything scoring 0.5 or above is a
    likely repeat and must be read before new work starts."""
    query = _tokens(terms)
    matches: list[DirectionMatch] = []
    for direction in load_directions(root).values():
        score = _score(query, _direction_text(direction))
        if score > 0:
            matches.append(
                DirectionMatch(
                    kind="registry",
                    ref=direction.id,
                    title=direction.name,
                    status=direction.status,
                    verdict=direction.verdict,
                    score=score,
                )
            )
    cards_dir = root / "reports" / "research" / "hypotheses"
    for card in sorted(cards_dir.glob("H-*.md")) if cards_dir.is_dir() else []:
        text = card.read_text(encoding="utf-8")
        head = "\n".join(text.splitlines()[:12])
        score = _score(query, card.stem.replace("-", " ") + " " + head)
        if score > 0:
            status_line = next(
                (
                    line.strip()
                    for line in text.splitlines()[:15]
                    if "状态" in line or line.lower().startswith("status")
                ),
                "",
            )
            matches.append(
                DirectionMatch(
                    kind="hypothesis_card",
                    ref=card.stem,
                    title=text.splitlines()[0].lstrip("# ").strip() if text else card.stem,
                    status=status_line[:160],
                    verdict="",
                    score=score,
                )
            )
    families_path = cards_dir / "trial-families.json"
    if families_path.is_file():
        families = json.loads(families_path.read_text(encoding="utf-8")).get("families", {})
        for key, family in families.items():
            note = str(family.get("note", ""))
            score = _score(query, key.replace("_", " ") + " " + note)
            if score > 0:
                matches.append(
                    DirectionMatch(
                        kind="trial_family",
                        ref=key,
                        title=key,
                        status=f"budget_remaining={family.get('budget_remaining')}",
                        verdict=note[:200],
                        score=score,
                    )
                )
    matches.sort(key=lambda match: (-match.score, match.kind, match.ref))
    return matches[:limit]


def check_channel(root: Path, terms: str, *, limit: int = 10) -> list[DirectionMatch]:
    """Recorded channels matching ``terms`` (name, URL, topics, kind): run before
    adding a channel so the same place is not recorded twice."""
    query = _tokens(terms)
    matches = []
    for channel in load_channels(root).values():
        text = " ".join([channel.id, channel.name, channel.url, channel.kind, *channel.topics])
        score = _score(query, text)
        if score > 0:
            matches.append(
                DirectionMatch(
                    kind="channel",
                    ref=channel.id,
                    title=f"{channel.name} <{channel.url}>",
                    status=f"{channel.status} level={channel.level}",
                    verdict=channel.verdict or channel.signal,
                    score=score,
                )
            )
    matches.sort(key=lambda match: (-match.score, match.ref))
    return matches[:limit]


def registry_summary(root: Path) -> dict[str, Any]:
    directions = load_directions(root)
    log = load_search_log(root)
    channels = load_channels(root)
    by_category: dict[str, Counter[str]] = {}
    for direction in directions.values():
        by_category.setdefault(direction.category, Counter())[direction.status] += 1
    return {
        "direction_count": len(directions),
        "by_status": dict(Counter(d.status for d in directions.values())),
        "by_category": {key: dict(value) for key, value in sorted(by_category.items())},
        "search_count": len(log),
        "searches_by_channel": dict(Counter(entry.channel for entry in log)),
        "channel_count": len(channels),
        "channels_by_status": dict(Counter(c.status for c in channels.values())),
        "channels_by_level": dict(Counter(str(c.level) for c in channels.values())),
        "channels_by_kind": dict(Counter(c.kind for c in channels.values())),
    }
