"""Bounded readers for account books and configured intraday strategies.

These books are independent of the legacy ETF account and must not disappear
just because they do not publish rehearsal files. A dated ledger is evidence
of that session, not proof of a currently running service or certified profit.
No broker, trading runner, refresh or valuation calculation is invoked here.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from open_composer.cockpit.security import secret_scrub
from open_composer.market_sessions import previous_us_equity_session, us_equity_session_close

MAX_BYTES = 2_000_000
NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class AccountBook:
    account: str
    book_id: str
    label: str
    status: str
    observed_at: datetime | None
    market_as_of: date | None
    expected_session: date
    latest_plan_session: date | None
    equity_usd: float | None
    net_pnl_usd: float | None
    orders: int | None
    filled: int | None
    rejected: int | None
    missing: int | None
    position_count: int | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class IntradayConfiguration:
    name: str
    account: str
    symbols: tuple[str, ...]
    status: str = "configuration_only"


def _number(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _count(value) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _time(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo is not None else None


def _date(value) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _read(path: Path, directory: Path) -> dict:
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("book path outside its directory")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("oversized book artifact")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("book artifact must be an object")
    return data


def _latest(directory: Path) -> Path | None:
    paths = [p for p in directory.glob("????-??-??.json") if _date(p.stem)]
    return max(paths, key=lambda p: p.name) if paths else None


def latest_completed_session(now: datetime) -> date:
    local = now.astimezone(NEW_YORK)
    close = us_equity_session_close(local.date())
    if close is not None and local.time() >= close:
        return local.date()
    return previous_us_equity_session(local.date())


def load_account_books(root: Path, *, now: datetime | None = None) -> tuple[AccountBook, ...]:
    now = now or datetime.now(UTC)
    expected = latest_completed_session(now)
    directory = root / "reports/paper/book"
    if not directory.is_dir():
        return ()
    result = []
    for account in sorted(directory.iterdir()):
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", account.name)
            or not account.resolve().is_relative_to(directory.resolve())
            or not (account / "daily").is_dir()
        ):
            continue
        warnings: list[str] = []
        daily: dict = {}
        path = _latest(account / "daily")
        try:
            if path:
                daily = _read(path, directory)
            if daily and daily.get("account") != account.name:
                raise ValueError("account mismatch")
        except (OSError, ValueError, TypeError):
            warnings.append("Latest account ledger unavailable or invalid")
            daily = {}
        session = _date(daily.get("execution_date"))
        observed = _time(daily.get("generated_at_utc"))
        recon = daily.get("reconciliation", {})
        pnl = daily.get("pnl", {})
        if not isinstance(recon, dict):
            recon = {}
        if not isinstance(pnl, dict):
            pnl = {}
        has_orders = _latest(account / "orders") is not None or bool(_count(recon.get("n_filled")))
        status = "current" if has_orders else "observation_only"
        if has_orders and (session is None or session < expected):
            status = "stale"
            warnings.append("No completed account ledger for the latest closed market session")
        invalid = (
            (daily and (session is None or observed is None))
            or (session is not None and session > expected)
            or (observed is not None and observed > now)
        )
        if invalid:
            status = "needs_attention"
            warnings.append("Ledger date is unavailable or ahead of completed market evidence")
        for field in ("n_missing", "n_acknowledgement_unknown", "n_position_drift_names"):
            if (_count(recon.get(field)) or 0) > 0:
                warnings.append(f"{field.removeprefix('n_').replace('_', ' ')}: {recon[field]}")
                if has_orders:
                    status = "needs_attention"
        plan_path = _latest(account / "plans")
        plan_session = _date(plan_path.stem) if plan_path else None
        position_count = None
        if session is not None and recon.get("n_position_drift_names") == 0:
            try:
                plan = _read(account / "plans" / f"{session.isoformat()}.json", directory)
                if (
                    daily.get("plan_sha256")
                    and plan.get("plan_sha256") == daily["plan_sha256"]
                    and isinstance(plan.get("post_trade_qty"), dict)
                ):
                    position_count = sum(
                        1 for q in plan["post_trade_qty"].values() if _number(q) not in (None, 0)
                    )
            except (OSError, ValueError, TypeError):
                warnings.append("Reconciled position count unavailable")
        # Legacy net_pnl includes modeled charges and unresolved cashflow issues.
        # Do not promote it to certified own-account profit by displaying it.
        net = _number(pnl.get("net_pnl")) if pnl.get("net_pnl_status") == "reconciled" else None
        if net is None:
            warnings.append("Net P&L not reconciled for cash flows and modeled costs")
        book_id = secret_scrub(str(daily.get("book_id") or account.name))[:120]
        form = book_id.rsplit(":", 1)[-1]
        description = {"F1": "Stock long/short", "F2": "SPY overlay"}.get(form)
        label = (
            f"{form} · {description} · {account.name}"
            if description
            else f"{form} · {account.name}"
        )
        result.append(
            AccountBook(
                account=account.name,
                book_id=book_id,
                label=label,
                status=status,
                observed_at=observed,
                market_as_of=session,
                expected_session=expected,
                latest_plan_session=plan_session,
                equity_usd=_number(pnl.get("equity")) if not invalid else None,
                net_pnl_usd=net if not invalid else None,
                orders=_count(recon.get("n_orders")),
                filled=_count(recon.get("n_filled")),
                rejected=_count(recon.get("n_submission_rejected")),
                missing=_count(recon.get("n_missing")),
                position_count=position_count,
                warnings=tuple(warnings),
            )
        )
    return tuple(result)


def load_intraday_configurations(root: Path) -> tuple[IntradayConfiguration, ...]:
    """Keep configured observers visible without claiming an actual paper run."""
    directory = root / "config/intraday"
    result = []
    for path in sorted(directory.glob("runner-*.yaml")):
        if "dryrun" in path.stem or not path.resolve().is_relative_to(directory.resolve()):
            continue
        try:
            with path.open("rb") as stream:
                raw = stream.read(65_537)
            if len(raw) > 65_536:
                continue
            data = yaml.safe_load(raw)
            if not isinstance(data, dict) or not isinstance(data.get("strategies"), list):
                continue
            for strategy in data["strategies"][:128]:
                if not isinstance(strategy, dict) or not isinstance(strategy.get("name"), str):
                    continue
                symbols = strategy.get("symbols", [])
                result.append(
                    IntradayConfiguration(
                        name=secret_scrub(strategy["name"][:120]),
                        account=secret_scrub(str(data.get("account", "unknown"))[:64]),
                        symbols=tuple(
                            s
                            for s in symbols[:64]
                            if isinstance(s, str) and re.fullmatch(r"[A-Z][A-Z0-9.-]{0,15}", s)
                        )
                        if isinstance(symbols, list)
                        else (),
                    )
                )
        except (OSError, ValueError, TypeError, yaml.YAMLError):
            continue
    return tuple(result)
