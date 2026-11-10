"""Present published paper valuations alongside current operating metadata.

This adapter has no file, broker or runner access. Runtime records identify
strategies and their state; only the published overview supplies money.
"""

from __future__ import annotations

import math
import re
import threading
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

if TYPE_CHECKING:
    from open_composer.cockpit.data.paper import PaperAccountReport

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*(?:/[A-Za-z0-9][A-Za-z0-9_.:-]*)*")
_STATES = {
    "authorized": ("已授权", "ok"),
    "running": ("运行中", "ok"),
    "operating": ("运行中", "ok"),
    "current": ("已记账", "ok"),
    "starting": ("启动中", "unknown"),
    "waiting_market_open": ("待开盘", "ok"),
    "ready_waiting_rth": ("待开盘", "ok"),
    "closed_market_carrying": ("休市持仓", "ok"),
    "closed_market_carrying_order_uncertain": ("订单待核", "warn"),
    "stale": ("待更新", "stale"),
    "expired": ("授权到期", "stale"),
    "paused_or_expired": ("已暂停", "warn"),
    "paused": ("已暂停", "warn"),
    "halted": ("已暂停", "warn"),
    "stopped": ("已停止", "unknown"),
    "failed": ("运行异常", "warn"),
    "blocked": ("待处理", "warn"),
    "needs_attention": ("待处理", "warn"),
    "observation_only": ("观察中", "unknown"),
    "not_started": ("未启动", "unknown"),
}

_REPORT_TTL_SECONDS = 30
_REPORT_CACHE: dict[Path, tuple[float, Any]] = {}
_REPORT_LOCK = threading.Lock()


def _read_dashboard_report(root: Path) -> PaperAccountReport:
    from open_composer.cockpit.data.paper import build_paper_report

    return build_paper_report(root)


def get_dashboard_report(root: Path) -> PaperAccountReport:
    """Share one local report for 30 seconds across native pages and the API.

    The lock covers construction so simultaneous requests cannot reconstruct
    the same report twice. Cached reports retain their original timestamps.
    """
    identity = root.resolve()
    with _REPORT_LOCK:
        cached = _REPORT_CACHE.get(identity)
        if cached is not None and monotonic() < cached[0]:
            return cached[1]
        report = _read_dashboard_report(identity)
        if len(_REPORT_CACHE) >= 8 and identity not in _REPORT_CACHE:
            del _REPORT_CACHE[next(iter(_REPORT_CACHE))]
        _REPORT_CACHE[identity] = (monotonic() + _REPORT_TTL_SECONDS, report)
        return report


def _get(record: Any, name: str, default: Any = None) -> Any:
    return (
        record.get(name, default) if isinstance(record, Mapping) else getattr(record, name, default)
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _identifier(value: Any) -> str | None:
    return value if isinstance(value, str) and len(value) <= 240 and _ID.fullmatch(value) else None


def _time(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value if isinstance(value, datetime) and value.tzinfo is not None else None


def _trial_record(item: Any) -> Any:
    return _get(item, "trial", item)


def _trial_items(report: Any, trials: Iterable[Any] | None) -> list[Any]:
    return list(trials if trials is not None else _get(report, "validation_trials", ()) or ())


def _trial_ledger_id(item: Any, known_ids: set[str]) -> str:
    """Prefer explicit identity; match older task IDs only at token boundaries.

    Registry policy and ledger_id fields persist through ValidationTrial.
    Older records can use longest unique token matching, which avoids
    assigning BASE_STATE_BUDGET to BASE. Wrapper metadata can override either.
    """
    trial = _trial_record(item)
    explicit = _identifier(_get(item, "ledger_id") or _get(trial, "ledger_id"))
    if explicit:
        return explicit
    policy = _identifier(_get(item, "policy") or _get(trial, "policy"))
    if policy:
        return "six/" + policy
    task_id = str(_get(trial, "task_id", ""))
    tokens = re.findall(r"[A-Z0-9]+", task_id.upper())
    candidates = []
    for ledger_id in known_ids:
        if not ledger_id.startswith("six/"):
            continue
        name = ledger_id.split("/", 1)[1]
        part = re.findall(r"[A-Z0-9]+", name.upper())
        if part and any(tokens[i : i + len(part)] == part for i in range(len(tokens))):
            candidates.append((len(part), ledger_id))
    if candidates:
        longest = max(length for length, _ in candidates)
        matches = [identity for length, identity in candidates if length == longest]
        if len(matches) == 1:
            return matches[0]
    return "trial/" + task_id


def _has_actual_record(kind: str, record: Any) -> bool:
    status = _get(record, "status")
    if status == "configuration_only":
        return False
    if kind == "sleeve":
        return _get(_get(record, "authorization"), "state") in {"authorized", "expired"} or bool(
            _get(record, "last_order_at") or _get(record, "latest_fill_session")
        )
    if kind == "account_book":
        return status != "observation_only" and bool(
            _get(record, "observed_at") or _get(record, "filled") or _get(record, "orders")
        )
    phase = _get(record, "service_phase")
    return bool(
        status in {"running", "starting", "failed", "halted", "stopped"}
        or phase
        or _get(record, "last_fill_at")
        or _get(record, "filled")
    )


def _sources(report: Any, trials: Iterable[Any] | None, known_ids: set[str]) -> list[dict]:
    sources = []
    for item in _trial_items(report, trials):
        trial = _trial_record(item)
        sources.append(
            dict(
                id=_trial_ledger_id(item, known_ids),
                kind="trial",
                source_id=_get(trial, "task_id"),
                record=trial,
            )
        )
    for sleeve in _get(report, "strategies", ()) or ():
        name = _get(sleeve, "name")
        sources.append(dict(id=f"legacy/{name}", kind="sleeve", source_id=name, record=sleeve))
    books = list(_get(report, "account_books", ()) or ())
    aliases: dict[str, int] = {}
    for book in books:
        alias = str(_get(book, "book_id", "")).rsplit(":", 1)[-1]
        aliases[alias] = aliases.get(alias, 0) + 1
    for book in books:
        alias = str(_get(book, "book_id", "")).rsplit(":", 1)[-1]
        account = _get(book, "account")
        identity = alias if alias in known_ids and aliases[alias] == 1 else f"book/{account}"
        sources.append(dict(id=identity, kind="account_book", source_id=account, record=book))
    return [s for s in sources if _identifier(s["id"]) and isinstance(s["source_id"], str)]


def _runtime_metadata(source: dict | None) -> dict:
    if source is None:
        return {}
    record = source["record"]
    kind = source["kind"]
    state = (
        _get(_get(record, "authorization"), "state")
        if kind == "sleeve"
        else _get(record, "service_phase") or _get(record, "status")
    )
    label, tone = _STATES.get(state, ("状态待核", "unknown"))
    metadata = dict(
        source_kind=kind,
        source_id=source["source_id"],
        status_label=label,
        status_tone=tone,
        runtime_status=state,
        runtime_observed_at=_json_value(
            _get(record, "service_observed_at")
            or _get(record, "observed_at")
            or _get(record, "generated_at")
        ),
    )
    if kind == "sleeve":
        metadata["source_href"] = "/paper/" + quote(source["source_id"], safe="")
    return metadata


def build_paper_dashboard(
    overview: dict,
    report: PaperAccountReport | Mapping | None = None,
    trials: Iterable[Any] | None = None,
    *,
    now: datetime | None = None,
) -> dict:
    """Return JSON-ready rows without recalculating or expanding published totals.

    A new operating strategy appears with null money until the accounting
    publisher includes it. ``observed_at`` dates its displayed valuation;
    ``runtime_observed_at`` separately dates the current operating metadata.
    """
    snapshot = _json_value(overview.get("snapshot", {})) if overview.get("available") else {}
    original_rows = snapshot.get("rows", [])
    known_ids = {r["id"] for r in original_rows if _identifier(r.get("id"))}
    sources = _sources(report, trials, known_ids)
    grouped: dict[str, list[dict]] = {}
    for source in sources:
        grouped.setdefault(source["id"], []).append(source)
    # An ambiguous runtime identity cannot replace a known accounting identity.
    by_id = {identity: items[0] for identity, items in grouped.items() if len(items) == 1}
    snapshot_at = snapshot.get("at_end")
    stamp = _time(snapshot_at)
    clock = now or datetime.now(UTC)
    stale = stamp is not None and clock - stamp > timedelta(hours=36)
    snapshot_status = "stale" if stale else "current" if stamp else "unknown"
    market_as_of = overview.get("through_session")
    rows = []
    seen = set()
    for original in original_rows:
        identity = _identifier(original.get("id"))
        if not identity or identity in seen:
            continue
        seen.add(identity)
        row = {
            **original,
            "href": "/paper/ledger/" + quote(identity, safe="/"),
            "source_kind": "ledger",
            "source_id": identity,
            "status_label": "已估值",
            "status_tone": "unknown",
            "market_as_of": market_as_of,
            "observed_at": snapshot_at,
            **_runtime_metadata(by_id.get(identity)),
        }
        if original.get("status") == "已退出":
            row.update(status_label="已退出", status_tone="unknown")
        elif original.get("pnl_usd") is None:
            row.update(status_label="等待估值", status_tone="unknown")
        rows.append(row)
    for identity, source in by_id.items():
        record = source["record"]
        if identity in seen or not _has_actual_record(source["kind"], record):
            continue
        rows.append(
            dict(
                id=identity,
                label=_get(record, "label") or source["source_id"],
                pnl_usd=None,
                return_pct=None,
                capital_usd=None,
                href="/paper/ledger/" + quote(identity, safe="/"),
                market_as_of=None,
                observed_at=None,
                **_runtime_metadata(source),
            )
        )
        rows[-1].update(status_label="等待估值", status_tone="unknown")
    return dict(
        available=bool(overview.get("available")),
        snapshot=snapshot,
        rows=rows,
        snapshot_at=snapshot_at,
        snapshot_label=stamp.astimezone(UTC).strftime("%m-%d %H:%M UTC") if stamp else "暂无估值",
        snapshot_status=snapshot_status,
        snapshot_status_label="待更新" if stale else "已估值" if stamp else "等待估值",
        market_as_of=market_as_of,
        stale=stale,
    )


def find_ledger_detail(
    dashboard: dict,
    ledger_id: str,
    report: PaperAccountReport | Mapping | None = None,
    trials: Iterable[Any] | None = None,
) -> dict | None:
    """Find a displayed ledger and optional native objects for a Jinja detail page.

    The returned runtime objects are not part of the JSON dashboard contract.
    Unknown IDs return None so a route can return its normal 404 response.
    """
    row = next((r for r in dashboard.get("rows", []) if r["id"] == ledger_id), None)
    if row is None:
        return None
    result = dict(row=row, trial=None, book=None, sleeve=None)
    kind, source_id = row["source_kind"], row["source_id"]
    if kind == "trial":
        candidates = [_trial_record(item) for item in _trial_items(report, trials)]
        result["trial"] = next((r for r in candidates if _get(r, "task_id") == source_id), None)
    elif kind == "account_book":
        result["book"] = next(
            (r for r in _get(report, "account_books", ()) or () if _get(r, "account") == source_id),
            None,
        )
    elif kind == "sleeve":
        result["sleeve"] = next(
            (r for r in _get(report, "strategies", ()) or () if _get(r, "name") == source_id),
            None,
        )
    return result
