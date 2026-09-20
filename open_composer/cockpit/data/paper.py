"""Pure data for the cockpit's paper-trading screen (Step 18, screen 4).

Nothing in this module renders HTML or touches Jinja2 -- ``open_composer.cockpit.app``
is the only thing that imports both this module and the template engine,
mirroring ``open_composer.cockpit.data.health`` and
``open_composer.cockpit.data.hypotheses``. Every function here is read-only.

The single most important fact this screen must get right (measured against
the real repo on 2026-09-19): five strategies write a
``reports/paper/rehearsal/<name>-latest.json`` cycle report, but only four of
them also have a ``<name>-authorization.json`` on file. The fifth,
``us_insider_buy_broad_monthly``, computes signals and would-be orders every
cycle but has never been authorized to submit a single real paper order --
``dry_run_unauthorized`` in its own status field. An unauthorized,
observation-only strategy must never be rendered as if it were trading, and
an authorization whose ``expires_at`` has passed must be visually
unmistakable, because that is exactly the moment its orders silently stop
without anything else in the system raising an alarm. Every dataclass and
loader below carries that distinction through explicitly (``AuthorizationState``)
rather than inferring "is it authorized" from some other proxy (e.g.
"does it have an orders.jsonl") that could quietly go stale.

"Strategy" is the organising dimension everywhere on this screen (the OpenAlgo
multi-bot pattern referenced by the plan) -- nothing here groups or indexes by
symbol. Positions and orders are looked up *by* strategy and only
cross-referenced against the shared broker-account snapshot
(``reports/paper/positions.json``) for market value / unrealized P&L context,
never the other way around.

Every file read degrades to a recorded warning on this module's dataclasses
rather than raising: a missing, empty, or corrupt artifact is a normal state
for a strategy that just joined the account (or was never authorized to begin
with), not a bug in this reader.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from open_composer.cockpit.data.health import Status
from open_composer.cockpit.security import secret_scrub
from open_composer.config import project_root

AuthorizationState = Literal["authorized", "observation_only", "expired"]

#: Display labels for `AuthorizationState`, in the English UI vocabulary
#: (plan section 3.5: "observation only" / "expired").
AUTH_STATE_LABELS: dict[AuthorizationState, str] = {
    "authorized": "authorized",
    "observation_only": "observation only",
    "expired": "expired",
}

REHEARSAL_DIR = ("reports", "paper", "rehearsal")
DAILY_CYCLE_DIR = ("reports", "paper", "daily_cycle")

#: Plan section 4 top bar: "warn under 7 days, stale when expired".
_WARN_DAYS = 7.0

#: Mirrors the size caps in `hypotheses.py`/`health.py` -- purely defensive on
#: this 3.9GB box; every real file here is well under 100KB as of 2026-09-19.
MAX_JSON_BYTES = 5_000_000
#: Bytes of an append-only `*-orders.jsonl` log read from the end, never the
#: whole file -- same pattern as `health._read_log_tail` applied to cron logs.
_ORDERS_TAIL_BYTES = 2_000_000
MAX_ORDER_RECORDS = 200


# --------------------------------------------------------------------------
# Small shared helpers
# --------------------------------------------------------------------------


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(UTC)


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _short_hash(value: Any, *, keep: int = 12) -> str | None:
    """A short, display-safe prefix of an already-hashed identifier.

    ``broker_account_id_hash`` is a hash, not a live secret, but the plan's
    security rules (section 6) say to never render a full broker account
    identifier and to run everything through `secret_scrub` regardless -- so
    this both truncates and scrubs, defense in depth over a value that
    should be harmless either way.
    """
    if not isinstance(value, str) or not value:
        return None
    scrubbed = secret_scrub(value)
    return scrubbed if len(scrubbed) <= keep else f"{scrubbed[:keep]}…"


def _read_json_object(path: Path, warnings: list[str]) -> dict[str, Any] | None:
    """Read one JSON object file, degrading to a recorded warning.

    Returns ``None`` when the file is absent (silently -- an optional
    artifact simply not existing yet is a normal state most callers check
    for separately) and also when it exists but cannot be parsed as a JSON
    object, in which case a warning is appended. Callers that must
    distinguish "does not exist" from "corrupt" check ``path.exists()``
    themselves before calling this.
    """
    if not path.exists():
        return None
    try:
        size = path.stat().st_size
    except OSError as exc:
        warnings.append(f"{path}: could not stat ({exc})")
        return None
    if size > MAX_JSON_BYTES:
        warnings.append(f"{path}: skipped, {size} bytes exceeds the {MAX_JSON_BYTES} byte cap")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        warnings.append(f"{path}: corrupt or unreadable JSON ({exc})")
        return None
    if not isinstance(data, dict):
        warnings.append(f"{path}: top level is not a JSON object, skipped")
        return None
    return data


# --------------------------------------------------------------------------
# Strategy discovery
# --------------------------------------------------------------------------


def discover_strategy_names(root: Path | None = None) -> tuple[str, ...]:
    """Every strategy with a ``<name>-latest.json`` under the rehearsal dir.

    This -- not a hardcoded list -- is the source of truth for which
    strategies exist. The route layer validates a requested strategy name
    against this set before touching the filesystem again for anything else
    (plan section 6, rule 4: validate a path input before it is used).
    """
    base = root or project_root()
    rehearsal_dir = base.joinpath(*REHEARSAL_DIR)
    if not rehearsal_dir.is_dir():
        return ()
    suffix = "-latest.json"
    return tuple(sorted(p.name[: -len(suffix)] for p in rehearsal_dir.glob(f"*{suffix}")))


# --------------------------------------------------------------------------
# Authorization
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthorizationInfo:
    """One strategy's rehearsal authorization state -- see module docstring.

    ``state`` is ``"observation_only"`` when no ``<name>-authorization.json``
    exists at all (the strategy has never been permitted to submit an order),
    ``"expired"`` when one exists but its ``expires_at`` has passed, and
    ``"authorized"`` otherwise. ``status`` reuses `health.Status` so this
    screen's chip uses the same four-word palette as every other screen:
    ``ok`` (authorized, 7+ days left), ``warn`` (authorized, <7 days left),
    ``stale`` (expired), ``unknown`` (observation-only, or a malformed file).
    """

    strategy_name: str
    state: AuthorizationState
    status: Status
    authorization_id: str | None
    authorized_at: datetime | None
    expires_at: datetime | None
    days_remaining: float | None  # negative once expired
    limits: dict[str, Any] | None
    scope: str | None
    paper_only: bool | None
    below_contract_acknowledged: bool | None
    broker_account_id_hash_prefix: str | None
    gate_status_note: str | None
    warnings: tuple[str, ...]


def _empty_authorization(
    strategy_name: str, *, state: AuthorizationState, status: Status, warnings: tuple[str, ...]
) -> AuthorizationInfo:
    return AuthorizationInfo(
        strategy_name=strategy_name,
        state=state,
        status=status,
        authorization_id=None,
        authorized_at=None,
        expires_at=None,
        days_remaining=None,
        limits=None,
        scope=None,
        paper_only=None,
        below_contract_acknowledged=None,
        broker_account_id_hash_prefix=None,
        gate_status_note=None,
        warnings=warnings,
    )


def load_authorization(
    root: Path | None = None, strategy_name: str = "", *, now: datetime | None = None
) -> AuthorizationInfo:
    """Load ``<strategy_name>-authorization.json`` (the current one, not the
    timestamped historical copies also written alongside it) and classify it.

    A missing file is the normal, expected shape of an observation-only
    strategy and is not a warning. A present-but-unparseable file *is* a
    warning -- and deliberately still classified as ``"authorized"`` with
    ``status="unknown"`` rather than falling back to ``"observation_only"``,
    because silently downgrading a strategy that really is authorized (just
    behind an unreadable file) to "not trading" would be exactly the kind of
    misclassification this screen exists to avoid.
    """
    base = root or project_root()
    reference = _now(now)
    warnings: list[str] = []
    path = base.joinpath(*REHEARSAL_DIR, f"{strategy_name}-authorization.json")

    if not path.exists():
        return _empty_authorization(
            strategy_name, state="observation_only", status="unknown", warnings=()
        )

    data = _read_json_object(path, warnings)
    if data is None:
        return _empty_authorization(
            strategy_name, state="authorized", status="unknown", warnings=tuple(warnings)
        )

    expires_at = _parse_dt(data.get("expires_at"))
    days_remaining = (expires_at - reference).total_seconds() / 86400.0 if expires_at else None

    state: AuthorizationState
    status: Status
    if expires_at is None:
        warnings.append(f"{path}: missing or unparseable expires_at")
        state, status = "authorized", "unknown"
    elif days_remaining is not None and days_remaining < 0:
        state, status = "expired", "stale"
    elif days_remaining is not None and days_remaining < _WARN_DAYS:
        state, status = "authorized", "warn"
    else:
        state, status = "authorized", "ok"

    limits = data.get("limits")
    return AuthorizationInfo(
        strategy_name=strategy_name,
        state=state,
        status=status,
        authorization_id=data.get("authorization_id")
        if isinstance(data.get("authorization_id"), str)
        else None,
        authorized_at=_parse_dt(data.get("authorized_at")),
        expires_at=expires_at,
        days_remaining=days_remaining,
        limits=limits if isinstance(limits, dict) else None,
        scope=secret_scrub(data["scope"]) if isinstance(data.get("scope"), str) else None,
        paper_only=data.get("paper_only") if isinstance(data.get("paper_only"), bool) else None,
        below_contract_acknowledged=(
            data.get("below_contract_acknowledged")
            if isinstance(data.get("below_contract_acknowledged"), bool)
            else None
        ),
        broker_account_id_hash_prefix=_short_hash(data.get("broker_account_id_hash")),
        gate_status_note=(
            secret_scrub(data["gate_status_note"])
            if isinstance(data.get("gate_status_note"), str)
            else None
        ),
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class RehearsalCountdown:
    """The single soonest-relevant authorization expiry, for the top bar."""

    status: Status
    label: str


def build_rehearsal_countdown(
    root: Path | None = None, *, now: datetime | None = None
) -> RehearsalCountdown:
    """Roll every strategy's authorization into the one top-bar countdown.

    Cheap on purpose: reads only each strategy's ``<name>-authorization.json``
    (never orders/fills/equity), because this renders on every screen, not
    just ``/paper`` (plan section 4: "this is the one number the owner should
    see on every screen"). The soonest *absolute* ``expires_at`` wins --
    an already-expired authorization dominates every still-valid one, since
    "expired" is the state the plan says must be visually unmistakable.
    """
    base = root or project_root()
    authorizations = [
        load_authorization(base, name, now=now) for name in discover_strategy_names(base)
    ]
    with_expiry = [a for a in authorizations if a.expires_at is not None]
    if not with_expiry:
        return RehearsalCountdown(status="unknown", label="no rehearsal authorizations on file")

    soonest = min(with_expiry, key=lambda a: a.expires_at)  # type: ignore[arg-type,return-value]
    days = soonest.days_remaining
    if soonest.state == "expired":
        label = (
            f"{soonest.strategy_name} expired {abs(days):.1f}d ago"
            if days is not None
            else f"{soonest.strategy_name} expired"
        )
    elif days is not None:
        label = f"{soonest.strategy_name}: {days:.1f}d"
    else:
        label = soonest.strategy_name
    return RehearsalCountdown(status=soonest.status, label=label)


# --------------------------------------------------------------------------
# Broker-account positions (whole account, shared by every strategy)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    qty: float | None
    market_value: float | None
    unrealized_pl: float | None
    current_price: float | None


def load_broker_positions(
    root: Path | None = None,
) -> tuple[dict[str, BrokerPosition], tuple[str, ...]]:
    """Index ``reports/paper/positions.json`` by symbol.

    This file is whole-account, not per-strategy -- every sleeve currently
    shares one Alpaca Paper account. Callers use this purely to annotate a
    strategy's own believed positions with market value / unrealized P&L,
    never as the source of "which strategy owns this symbol".
    """
    base = root or project_root()
    warnings: list[str] = []
    path = base / "reports" / "paper" / "positions.json"
    if not path.exists():
        return {}, (f"{path}: not found, cannot attribute broker positions",)
    data = _read_json_object(path, warnings)
    if data is None:
        return {}, tuple(warnings)
    rows = data.get("positions")
    if not isinstance(rows, list):
        warnings.append(f"{path}: no 'positions' list, cannot attribute broker positions")
        return {}, tuple(warnings)
    index: dict[str, BrokerPosition] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol")
        if not isinstance(symbol, str):
            continue
        index[symbol] = BrokerPosition(
            symbol=symbol,
            qty=_num(row.get("qty")),
            market_value=_num(row.get("market_value")),
            unrealized_pl=_num(row.get("unrealized_pl")),
            current_price=_num(row.get("current_price")),
        )
    return index, tuple(warnings)


# --------------------------------------------------------------------------
# Target weights vs actual positions ("side by side", plan section 4)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionRow:
    """One symbol's target vs actual, for one strategy's most recent cycle.

    ``ledger_qty`` comes from that cycle's own ``strategy_ledger_positions``
    and is only ever populated for a strategy with a *dedicated* ledger
    (``position_scope == "strategy_ledger"``); for a strategy without one
    (as of 2026-09-19, only the unauthorized ``us_insider_buy_broad_monthly``)
    it is always ``None`` -- that strategy has no isolated attribution to
    show, and pretending otherwise would misrepresent the real risk that an
    unauthorized strategy without its own ledger would act on *other*
    strategies' positions if it were ever allowed to submit orders.
    ``broker_qty``/``market_value``/``unrealized_pl`` come from the shared
    account snapshot, matched by symbol only.
    """

    symbol: str
    action: str | None
    decision: str | None
    reason: str | None
    target_weight: float | None
    target_qty: float | None
    current_qty: float | None
    ledger_qty: float | None
    broker_qty: float | None
    market_value: float | None
    unrealized_pl: float | None

    @property
    def agrees_with_broker(self) -> bool | None:
        """``None`` when there is nothing to compare (no ledger qty or no
        matching broker position), else whether the two are the same qty."""
        if self.ledger_qty is None or self.broker_qty is None:
            return None
        return abs(self.ledger_qty - self.broker_qty) < 1e-6


def _build_position_rows(
    orders: list[Any],
    ledger_positions: dict[str, Any] | None,
    broker_positions: dict[str, BrokerPosition],
) -> tuple[PositionRow, ...]:
    rows: list[PositionRow] = []
    for order in orders:
        if not isinstance(order, dict):
            continue
        symbol = order.get("symbol")
        if not isinstance(symbol, str):
            continue
        ledger_qty = _num(ledger_positions.get(symbol)) if ledger_positions is not None else None
        broker = broker_positions.get(symbol)
        reason = order.get("reason")
        rows.append(
            PositionRow(
                symbol=symbol,
                action=order.get("action") if isinstance(order.get("action"), str) else None,
                decision=order.get("decision") if isinstance(order.get("decision"), str) else None,
                reason=secret_scrub(reason) if isinstance(reason, str) and reason else None,
                target_weight=_num(order.get("target_weight")),
                target_qty=_num(order.get("target_qty")),
                current_qty=_num(order.get("current_qty")),
                ledger_qty=ledger_qty,
                broker_qty=broker.qty if broker else None,
                market_value=broker.market_value if broker else None,
                unrealized_pl=broker.unrealized_pl if broker else None,
            )
        )
    rows.sort(key=lambda r: r.symbol)
    return tuple(rows)


# --------------------------------------------------------------------------
# Submitted orders (<name>-orders.jsonl)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderRecord:
    recorded_at: datetime | None
    session: str | None
    symbol: str
    side: str | None
    qty: float | None
    notional: float | None
    order_style: str | None
    broker_status: str | None
    broker_order_id: str | None


def _tail_jsonl_records(
    path: Path, *, max_records: int, warnings: list[str]
) -> tuple[tuple[dict[str, Any], ...], bool]:
    """Up to the last ``max_records`` JSON objects in an append-only JSONL log.

    Reads only the last `_ORDERS_TAIL_BYTES` of the file (a `seek()` from the
    end, never the whole file) -- the same bounded-tail pattern as
    `health._read_log_tail` applied to cron logs, so this order log can grow
    for months without this ever costing more than a bounded slice of memory
    on this 3.9GB box. Returns the parsed records (oldest first) plus whether
    the window may have missed older records.
    """
    if not path.exists():
        return (), False
    try:
        size = path.stat().st_size
    except OSError as exc:
        warnings.append(f"{path}: could not stat ({exc})")
        return (), False
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            total = handle.tell()
            read_from = max(0, total - _ORDERS_TAIL_BYTES)
            handle.seek(read_from)
            chunk = handle.read()
    except OSError as exc:
        warnings.append(f"{path}: could not read ({exc})")
        return (), False

    lines = chunk.decode("utf-8", errors="replace").split("\n")
    truncated = read_from > 0
    if truncated:
        lines = lines[1:]  # drop a possibly-truncated first line

    records: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"{path}: skipped a corrupt JSONL line")
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return tuple(records[-max_records:]), truncated or size > _ORDERS_TAIL_BYTES


def load_orders(
    root: Path | None = None, strategy_name: str = "", *, limit: int = MAX_ORDER_RECORDS
) -> tuple[tuple[OrderRecord, ...], bool, tuple[str, ...]]:
    """The most recent ``limit`` submitted orders for ``strategy_name``.

    A missing ``<name>-orders.jsonl`` is not a warning -- it is exactly the
    normal, expected state for an unauthorized/observation-only strategy
    that has never submitted an order (``us_insider_buy_broad_monthly`` as of
    2026-09-19 has no such file at all, by design).
    """
    base = root or project_root()
    warnings: list[str] = []
    path = base.joinpath(*REHEARSAL_DIR, f"{strategy_name}-orders.jsonl")
    if not path.exists():
        return (), False, ()

    raw_records, truncated = _tail_jsonl_records(path, max_records=limit, warnings=warnings)
    orders: list[OrderRecord] = []
    for raw in raw_records:
        symbol = raw.get("symbol")
        if not isinstance(symbol, str):
            continue
        orders.append(
            OrderRecord(
                recorded_at=_parse_dt(raw.get("recorded_at")),
                session=raw.get("session") if isinstance(raw.get("session"), str) else None,
                symbol=symbol,
                side=raw.get("side") if isinstance(raw.get("side"), str) else None,
                qty=_num(raw.get("qty")),
                notional=_num(raw.get("notional")),
                order_style=raw.get("order_style")
                if isinstance(raw.get("order_style"), str)
                else None,
                broker_status=raw.get("broker_status")
                if isinstance(raw.get("broker_status"), str)
                else None,
                broker_order_id=raw.get("broker_order_id")
                if isinstance(raw.get("broker_order_id"), str)
                else None,
            )
        )
    orders.sort(key=lambda o: o.recorded_at or datetime.min.replace(tzinfo=UTC))
    return tuple(orders), truncated, tuple(warnings)


# --------------------------------------------------------------------------
# Fills / slippage (<name>-fills-summary.json) -- read, never recomputed
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FillSessionStats:
    """One trading session's fill statistics, copied verbatim from
    ``fills-summary.json`` -- fill rate and slippage are already computed
    there; this module never recomputes them from the raw fills log."""

    session: str
    orders: int | None
    filled_full: int | None
    filled_partial: int | None
    unfilled: int | None
    cancelled_before_open: int | None
    fill_rate_by_notional: float | None
    median_slippage_vs_reference_bps: float | None
    order_styles: tuple[str, ...]


@dataclass(frozen=True)
class FillsSummary:
    """``available`` is True whenever ``<name>-fills-summary.json`` exists and
    parses as expected -- *even if* it records zero sessions so far (a real,
    observed state as of 2026-09-19 for a freshly authorized ETF sleeve that
    has not yet had a fill-recording cycle run). A missing or corrupt file is
    a different situation from a present-but-empty one and is kept distinct
    via ``available=False`` plus a warning, rather than collapsing both into
    one "no data" bucket.
    """

    strategy_name: str
    available: bool
    generated_at: datetime | None
    sessions: tuple[FillSessionStats, ...]  # chronological ascending
    warnings: tuple[str, ...]

    @property
    def latest(self) -> FillSessionStats | None:
        return self.sessions[-1] if self.sessions else None


def load_fills_summary(root: Path | None = None, strategy_name: str = "") -> FillsSummary:
    base = root or project_root()
    warnings: list[str] = []
    path = base.joinpath(*REHEARSAL_DIR, f"{strategy_name}-fills-summary.json")

    if not path.exists():
        return FillsSummary(
            strategy_name=strategy_name,
            available=False,
            generated_at=None,
            sessions=(),
            warnings=(f"{path}: not found -- no fills recorded for this strategy yet",),
        )

    data = _read_json_object(path, warnings)
    if data is None:
        return FillsSummary(
            strategy_name=strategy_name,
            available=False,
            generated_at=None,
            sessions=(),
            warnings=tuple(warnings),
        )

    sessions_raw = data.get("sessions")
    if not isinstance(sessions_raw, dict):
        warnings.append(f"{path}: no 'sessions' object, cannot show fill statistics")
        return FillsSummary(
            strategy_name=strategy_name,
            available=False,
            generated_at=_parse_dt(data.get("generated_at")),
            sessions=(),
            warnings=tuple(warnings),
        )

    sessions: list[FillSessionStats] = []
    for session_key in sorted(sessions_raw):
        row = sessions_raw[session_key]
        if not isinstance(row, dict):
            warnings.append(f"{path}: session {session_key!r} is not an object, skipped")
            continue
        styles = row.get("order_styles")
        sessions.append(
            FillSessionStats(
                session=session_key,
                orders=row.get("orders") if isinstance(row.get("orders"), int) else None,
                filled_full=row.get("filled_full")
                if isinstance(row.get("filled_full"), int)
                else None,
                filled_partial=row.get("filled_partial")
                if isinstance(row.get("filled_partial"), int)
                else None,
                unfilled=row.get("unfilled") if isinstance(row.get("unfilled"), int) else None,
                cancelled_before_open=(
                    row.get("cancelled_before_open")
                    if isinstance(row.get("cancelled_before_open"), int)
                    else None
                ),
                fill_rate_by_notional=_num(row.get("fill_rate_by_notional")),
                median_slippage_vs_reference_bps=_num(row.get("median_slippage_vs_reference_bps")),
                order_styles=tuple(s for s in styles if isinstance(s, str))
                if isinstance(styles, list)
                else (),
            )
        )

    return FillsSummary(
        strategy_name=strategy_name,
        available=True,
        generated_at=_parse_dt(data.get("generated_at")),
        sessions=tuple(sessions),
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------
# Equity history -- real points only, never interpolated or back-filled
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EquityPoint:
    at: datetime
    equity: float
    source: str  # "daily_cycle_observation" | "rehearsal_cycle_snapshot"


_EQUITY_NOTE = (
    "Shared Alpaca Paper account equity, sampled at this strategy's own cycle times -- "
    "all sleeves currently share one broker account, so this is not an isolated "
    "per-strategy P&L curve."
)


@dataclass(frozen=True)
class EquitySeries:
    """A strategy's equity history, or the honest absence of one.

    ``reports/paper/account.json`` is a single snapshot, not a series (see
    module/plan docs). Two other sources turned out to carry real,
    timestamped equity observations instead: the observation-only daily
    cycle logs under ``reports/paper/daily_cycle/<name>-observation-*.json``
    (``target_weights_summary.account_equity``) and the per-cycle historical
    snapshots already sitting next to ``-latest.json`` in the rehearsal dir
    (``<name>-YYYY-MM-DD-HHMMSS.json``, each carrying its own ``equity``).
    Neither ``sync.jsonl`` (a raw broker order/fill sync log with no equity
    field) nor ``rotation_baselines.jsonl`` (per-session benchmark returns
    for a hypothetical equal-weight portfolio, not this account's own equity)
    contains anything usable here.

    Every point in ``points`` is one of those real observations -- nothing is
    interpolated or back-filled between them. ``has_history`` requires at
    least two distinct real points; with zero or one, the caller must render
    the single latest snapshot with a "no history yet" flag instead of a
    chart (plan section 7, T5: "do not interpolate, back-fill, or draw a
    two-point line pretending to be a curve").
    """

    strategy_name: str
    points: tuple[EquityPoint, ...]  # sorted ascending by `at`, deduplicated
    has_history: bool
    note: str
    warnings: tuple[str, ...]

    @property
    def latest(self) -> EquityPoint | None:
        return self.points[-1] if self.points else None


def _collect_daily_cycle_points(
    base: Path, strategy_name: str, warnings: list[str]
) -> list[EquityPoint]:
    directory = base.joinpath(*DAILY_CYCLE_DIR)
    if not directory.is_dir():
        return []
    points: list[EquityPoint] = []
    for path in sorted(directory.glob(f"{strategy_name}-observation-*.json")):
        data = _read_json_object(path, warnings)
        if data is None:
            continue
        summary = data.get("target_weights_summary")
        equity = _num(summary.get("account_equity")) if isinstance(summary, dict) else None
        at = _parse_dt(data.get("ended_at")) or _parse_dt(data.get("started_at"))
        if equity is not None and at is not None:
            points.append(EquityPoint(at=at, equity=equity, source="daily_cycle_observation"))
        else:
            warnings.append(f"{path}: no usable account_equity/timestamp, skipped")
    return points


def _rehearsal_snapshot_pattern(strategy_name: str) -> re.Pattern[str]:
    escaped = re.escape(strategy_name)
    return re.compile(rf"^{escaped}-\d{{4}}-\d{{2}}-\d{{2}}-\d{{6}}\.json$")


def _collect_rehearsal_cycle_points(
    base: Path, strategy_name: str, warnings: list[str]
) -> list[EquityPoint]:
    directory = base.joinpath(*REHEARSAL_DIR)
    if not directory.is_dir():
        return []
    pattern = _rehearsal_snapshot_pattern(strategy_name)
    points: list[EquityPoint] = []
    for path in sorted(directory.glob(f"{strategy_name}-*.json")):
        if not pattern.match(path.name):
            continue
        data = _read_json_object(path, warnings)
        if data is None:
            continue
        equity = _num(data.get("equity"))
        at = _parse_dt(data.get("generated_at"))
        if equity is not None and at is not None:
            points.append(EquityPoint(at=at, equity=equity, source="rehearsal_cycle_snapshot"))
        else:
            warnings.append(f"{path}: no usable equity/generated_at, skipped")
    return points


def build_equity_series(root: Path | None = None, strategy_name: str = "") -> EquitySeries:
    base = root or project_root()
    warnings: list[str] = []
    raw_points = _collect_daily_cycle_points(
        base, strategy_name, warnings
    ) + _collect_rehearsal_cycle_points(base, strategy_name, warnings)
    deduped = sorted({(p.at, p.equity, p.source) for p in raw_points})
    points = tuple(
        EquityPoint(at=at, equity=equity, source=source) for at, equity, source in deduped
    )
    return EquitySeries(
        strategy_name=strategy_name,
        points=points,
        has_history=len(points) >= 2,
        note=_EQUITY_NOTE,
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class EquityChartBar:
    x: float
    y: float
    width: float
    height: float
    title: str
    value: float


@dataclass(frozen=True)
class EquityChartLayout:
    bars: tuple[EquityChartBar, ...]
    width: float
    height: float
    min_value: float
    max_value: float


def compute_equity_chart_layout(
    series: EquitySeries,
    *,
    width: float = 320.0,
    height: float = 90.0,
    gap: float = 3.0,
    margin: float = 6.0,
) -> EquityChartLayout | None:
    """Pure numeric layout for a server-rendered inline-SVG bar chart.

    Returns ``None`` when `series.has_history` is False: the caller must fall
    back to a plain stat-card snapshot rather than drawing anything from
    fewer than two real points. Bars, not a connecting line, on purpose --
    every bar is one real, independently observed equity reading, and a line
    would visually imply the (unobserved) equity path between two cycles.
    """
    if not series.has_history:
        return None
    values = [p.equity for p in series.points]
    min_v, max_v = min(values), max(values)
    span = (max_v - min_v) or 1.0
    n = len(series.points)
    plot_w = max(width - 2 * margin, 1.0)
    plot_h = max(height - 2 * margin, 1.0)
    bar_w = max((plot_w - gap * (n - 1)) / n, 1.0)

    bars: list[EquityChartBar] = []
    for index, point in enumerate(series.points):
        frac = (point.equity - min_v) / span
        bar_h = max(frac * plot_h, 2.0)
        x = margin + index * (bar_w + gap)
        y = margin + (plot_h - bar_h)
        bars.append(
            EquityChartBar(
                x=x,
                y=y,
                width=bar_w,
                height=bar_h,
                title=f"{point.at.isoformat()}: {point.equity:,.2f} ({point.source})",
                value=point.equity,
            )
        )
    return EquityChartLayout(
        bars=tuple(bars), width=width, height=height, min_value=min_v, max_value=max_v
    )


# --------------------------------------------------------------------------
# Account level: equity snapshot, kill switch, open order count
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AccountSnapshot:
    generated_at: datetime | None
    equity: float | None
    cash: float | None
    buying_power: float | None
    portfolio_value: float | None
    age_hours: float | None
    status: Status
    broker_account_id_hash_prefix: str | None
    warnings: tuple[str, ...]


#: `reports/paper/account.json` is refreshed roughly once per daily cycle;
#: warn well before a full weekend gap (~72h) would look the same as a
#: genuinely stuck sync job, stale beyond that.
_ACCOUNT_OK_HOURS = 26.0
_ACCOUNT_WARN_HOURS = 72.0


def load_account_snapshot(
    root: Path | None = None, *, now: datetime | None = None
) -> AccountSnapshot:
    base = root or project_root()
    reference = _now(now)
    warnings: list[str] = []
    path = base / "reports" / "paper" / "account.json"

    def _empty(status: Status, extra_warnings: tuple[str, ...]) -> AccountSnapshot:
        return AccountSnapshot(
            generated_at=None,
            equity=None,
            cash=None,
            buying_power=None,
            portfolio_value=None,
            age_hours=None,
            status=status,
            broker_account_id_hash_prefix=None,
            warnings=extra_warnings,
        )

    if not path.exists():
        return _empty("unknown", (f"{path}: not found",))

    data = _read_json_object(path, warnings)
    if data is None:
        return _empty("unknown", tuple(warnings))

    generated_at = _parse_dt(data.get("generated_at"))
    age_hours = (reference - generated_at).total_seconds() / 3600.0 if generated_at else None
    status: Status
    if age_hours is None:
        status = "unknown"
    elif age_hours <= _ACCOUNT_OK_HOURS:
        status = "ok"
    elif age_hours <= _ACCOUNT_WARN_HOURS:
        status = "warn"
    else:
        status = "stale"

    return AccountSnapshot(
        generated_at=generated_at,
        equity=_num(data.get("equity")),
        cash=_num(data.get("cash")),
        buying_power=_num(data.get("buying_power")),
        portfolio_value=_num(data.get("portfolio_value")),
        age_hours=age_hours,
        status=status,
        broker_account_id_hash_prefix=_short_hash(data.get("broker_account_id_hash")),
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class KillSwitchStatus:
    enabled: bool | None
    reason: str | None
    updated_at: datetime | None
    status: Status  # warn: enabled (trading halted) / ok: explicitly disabled / unknown: unreadable
    warnings: tuple[str, ...]


def load_kill_switch(root: Path | None = None) -> KillSwitchStatus:
    base = root or project_root()
    warnings: list[str] = []
    path = base / "reports" / "paper" / "kill_switch.json"

    if not path.exists():
        return KillSwitchStatus(
            enabled=None,
            reason=None,
            updated_at=None,
            status="unknown",
            warnings=(f"{path}: not found",),
        )

    data = _read_json_object(path, warnings)
    if data is None:
        return KillSwitchStatus(
            enabled=None, reason=None, updated_at=None, status="unknown", warnings=tuple(warnings)
        )

    enabled = data.get("enabled")
    status: Status
    if not isinstance(enabled, bool):
        warnings.append(f"{path}: 'enabled' is missing or not a boolean")
        status = "unknown"
        enabled = None
    else:
        status = "warn" if enabled else "ok"

    reason = data.get("reason")
    return KillSwitchStatus(
        enabled=enabled,
        reason=secret_scrub(reason) if isinstance(reason, str) else None,
        updated_at=_parse_dt(data.get("updated_at")),
        status=status,
        warnings=tuple(warnings),
    )


def load_open_order_count(root: Path | None = None) -> tuple[int | None, tuple[str, ...]]:
    base = root or project_root()
    warnings: list[str] = []
    path = base / "reports" / "paper" / "open_orders.json"
    if not path.exists():
        return None, (f"{path}: not found",)
    data = _read_json_object(path, warnings)
    if data is None:
        return None, tuple(warnings)
    orders = data.get("orders")
    if not isinstance(orders, list):
        warnings.append(f"{path}: no 'orders' list")
        return None, tuple(warnings)
    return len(orders), tuple(warnings)


# --------------------------------------------------------------------------
# Per-strategy detail and summary
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategyDetail:
    name: str
    authorization: AuthorizationInfo
    generated_at: datetime | None  # this strategy's most recent cycle time
    session: str | None
    cycle_status: str | None  # e.g. "submitted", "no_orders", "dry_run_unauthorized"
    equity_at_last_cycle: float | None
    has_dedicated_ledger: bool  # position_scope == "strategy_ledger" on the latest cycle
    decision_counts: dict[str, int]
    positions: tuple[PositionRow, ...]
    positions_agreement: str  # human summary of ledger-vs-broker agreement
    orders: tuple[OrderRecord, ...]
    orders_window_truncated: bool
    fills: FillsSummary
    equity_series: EquitySeries
    warnings: tuple[str, ...]

    @property
    def last_order_at(self) -> datetime | None:
        return self.orders[-1].recorded_at if self.orders else None


def _positions_agreement_summary(
    positions: tuple[PositionRow, ...], *, has_dedicated_ledger: bool
) -> str:
    if not has_dedicated_ledger:
        return "no dedicated position ledger (not authorized to hold isolated positions)"
    comparable = [row for row in positions if row.agrees_with_broker is not None]
    if not comparable:
        return "no comparable positions (ledger and/or broker side empty)"
    matched = sum(1 for row in comparable if row.agrees_with_broker)
    return f"{matched}/{len(comparable)} symbols match the broker account"


def build_strategy_detail(
    root: Path | None = None, strategy_name: str = "", *, now: datetime | None = None
) -> StrategyDetail:
    """Assemble the full per-strategy detail view.

    Each section degrades independently -- a missing/corrupt
    ``-latest.json`` still returns a `StrategyDetail` with empty cycle
    fields and a warning rather than raising, mirroring
    `health.build_health_report`'s per-section isolation.
    """
    base = root or project_root()
    warnings: list[str] = []

    authorization = load_authorization(base, strategy_name, now=now)

    latest_path = base.joinpath(*REHEARSAL_DIR, f"{strategy_name}-latest.json")
    if not latest_path.exists():
        warnings.append(f"{latest_path}: not found -- cycle fields will be empty")
        latest: dict[str, Any] = {}
    else:
        latest = _read_json_object(latest_path, warnings) or {}

    generated_at = _parse_dt(latest.get("generated_at"))
    session = latest.get("session") if isinstance(latest.get("session"), str) else None
    cycle_status = latest.get("status") if isinstance(latest.get("status"), str) else None
    equity = _num(latest.get("equity"))
    has_dedicated_ledger = latest.get("position_scope") == "strategy_ledger"
    ledger_positions_raw = latest.get("strategy_ledger_positions")
    ledger_positions = (
        ledger_positions_raw
        if has_dedicated_ledger and isinstance(ledger_positions_raw, dict)
        else None
    )
    counts_raw = latest.get("counts")
    decision_counts = (
        {str(k): v for k, v in counts_raw.items() if isinstance(v, int)}
        if isinstance(counts_raw, dict)
        else {}
    )
    orders_raw = latest.get("orders")
    order_rows = orders_raw if isinstance(orders_raw, list) else []

    broker_positions, broker_warnings = load_broker_positions(base)
    warnings.extend(broker_warnings)

    positions = _build_position_rows(order_rows, ledger_positions, broker_positions)
    positions_agreement = _positions_agreement_summary(
        positions, has_dedicated_ledger=has_dedicated_ledger
    )

    orders, orders_truncated, orders_warnings = load_orders(base, strategy_name)
    warnings.extend(orders_warnings)
    if not orders:
        orders_path = base.joinpath(*REHEARSAL_DIR, f"{strategy_name}-orders.jsonl")
        if not orders_path.exists():
            warnings.append(
                f"no {strategy_name}-orders.jsonl on file -- "
                "this strategy has never submitted a paper order"
            )

    fills = load_fills_summary(base, strategy_name)
    equity_series = build_equity_series(base, strategy_name)

    return StrategyDetail(
        name=strategy_name,
        authorization=authorization,
        generated_at=generated_at,
        session=session,
        cycle_status=cycle_status,
        equity_at_last_cycle=equity,
        has_dedicated_ledger=has_dedicated_ledger,
        decision_counts=decision_counts,
        positions=positions,
        positions_agreement=positions_agreement,
        orders=orders,
        orders_window_truncated=orders_truncated,
        fills=fills,
        equity_series=equity_series,
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class StrategySummary:
    """One row of the `/paper` overview table -- the FreqUI multi-bot rollup
    pattern the plan calls for: one row per strategy, drill into one."""

    name: str
    authorization: AuthorizationInfo
    generated_at: datetime | None
    session: str | None
    cycle_status: str | None
    positions_agreement: str
    latest_fill_rate: float | None
    latest_fill_session: str | None
    last_order_at: datetime | None
    warnings: tuple[str, ...]


def summarize_strategy(detail: StrategyDetail) -> StrategySummary:
    latest_fill = detail.fills.latest
    return StrategySummary(
        name=detail.name,
        authorization=detail.authorization,
        generated_at=detail.generated_at,
        session=detail.session,
        cycle_status=detail.cycle_status,
        positions_agreement=detail.positions_agreement,
        latest_fill_rate=latest_fill.fill_rate_by_notional if latest_fill else None,
        latest_fill_session=latest_fill.session if latest_fill else None,
        last_order_at=detail.last_order_at,
        warnings=detail.warnings,
    )


# --------------------------------------------------------------------------
# Aggregate account-level report (the `/paper` index)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperAccountReport:
    generated_at: datetime
    account: AccountSnapshot
    kill_switch: KillSwitchStatus
    open_order_count: int | None
    strategies: tuple[StrategySummary, ...]
    warnings: tuple[str, ...]


def build_paper_report(
    root: Path | None = None, *, now: datetime | None = None
) -> PaperAccountReport:
    """Assemble the full `/paper` index: every discovered strategy's summary
    row plus the shared account snapshot. A single broken strategy degrades
    to a warning and is skipped from the row list rather than blanking the
    whole board, mirroring `hypotheses.build_hypotheses_report`."""
    base = root or project_root()
    warnings: list[str] = []

    summaries: list[StrategySummary] = []
    for name in discover_strategy_names(base):
        try:
            detail = build_strategy_detail(base, name, now=now)
        except Exception as exc:  # defensive: one broken strategy must not blank the board
            warnings.append(f"{name}: failed to build strategy report ({exc!r})")
            continue
        summaries.append(summarize_strategy(detail))

    account = load_account_snapshot(base, now=now)
    kill_switch = load_kill_switch(base)
    open_order_count, open_order_warnings = load_open_order_count(base)
    warnings.extend(open_order_warnings)

    return PaperAccountReport(
        generated_at=_now(now),
        account=account,
        kill_switch=kill_switch,
        open_order_count=open_order_count,
        strategies=tuple(summaries),
        warnings=tuple(warnings),
    )


__all__ = [
    "AUTH_STATE_LABELS",
    "AccountSnapshot",
    "AuthorizationInfo",
    "AuthorizationState",
    "BrokerPosition",
    "EquityChartBar",
    "EquityChartLayout",
    "EquityPoint",
    "EquitySeries",
    "FillSessionStats",
    "FillsSummary",
    "KillSwitchStatus",
    "OrderRecord",
    "PaperAccountReport",
    "PositionRow",
    "RehearsalCountdown",
    "StrategyDetail",
    "StrategySummary",
    "build_equity_series",
    "build_paper_report",
    "build_rehearsal_countdown",
    "build_strategy_detail",
    "compute_equity_chart_layout",
    "discover_strategy_names",
    "load_account_snapshot",
    "load_authorization",
    "load_broker_positions",
    "load_fills_summary",
    "load_kill_switch",
    "load_open_order_count",
    "load_orders",
    "summarize_strategy",
]
