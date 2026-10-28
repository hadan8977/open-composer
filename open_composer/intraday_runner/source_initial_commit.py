"""Concrete first-entry close/input reception for the initially empty own sleeve.

No late adoption, no synthetic account reset, no future-source replacement.
Only the first regular November entry is supported by this scope. A nonempty
precommit book requires its own fully received rights/flow evidence and refuses
here; this does not erase those holdings or extend the original authority.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from open_composer.intraday_runner.source_activity_reception import save
from open_composer.intraday_runner.source_dispatch_journal import _ensure_durable_directory, _hash
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.source_method_controls import primary_calendar
from open_composer.intraday_runner.source_state_checkpoint import restore
from open_composer.market_sessions import NEW_YORK, us_equity_session_close


def empty_initial(state):
    if (
        state.pending
        or state.consumed_ids
        or state.applied_fill_ids
        or state.cashbook.sales
        or state.cashbook.purchases
        or state.cashbook.dividends
        or any(state.cashbook.lots.values())
        or state.cashbook.cash != 20000
    ):
        raise ValueError("not the verified empty first-entry sleeve; no implicit adoption/reset")


def receive_close(runtime, transport, *, directory: Path, clock=lambda: datetime.now(UTC)):
    import pandas as pd

    from open_composer.research.features.price_hygiene import sanitize_price_matrices

    cal = primary_calendar(date(2026, 10, 31))
    closed = datetime.combine(cal["decision"], us_equity_session_close(cal["decision"]), NEW_YORK)
    if not closed <= clock() <= cal["commit_at"]:
        raise ValueError("outside actual completed-close reception window")
    revision = runtime.store.load()
    state, _, _, evidence = restore(runtime.root, revision["snapshot"])
    empty_initial(state)
    if evidence.get("held_rights_complete") is not True:
        raise ValueError("actual accepted empty-book/rights reconciliation missing")
    _ensure_durable_directory(directory.parent.absolute())
    directory.mkdir(exist_ok=False)
    obs_binding = runtime.capture_observation(quotes={}, directory=directory / "account")
    obs = json.loads(bound_bytes(runtime.root, obs_binding))
    if obs["unborrowed_new_capacity"] < 20000 or obs["own_gross"] != 0:
        raise ValueError("current unencumbered own allocation not verified")
    symbols = runtime.auth["universe"]
    # Exact two adjacent sessions: original month end and regular decision day.
    sessions = ["2026-10-30", "2026-11-02"]
    params = dict(
        symbols=",".join(symbols),
        timeframe="1Day",
        adjustment="raw",
        feed="sip",
        start="2026-10-30T00:00:00-04:00",
        end="2026-11-03T00:00:00-05:00",
        asof="-",
        sort="asc",
        limit=10000,
    )
    save(directory / "request.json", dict(params=params, started_at=clock().isoformat()))
    response = transport.fetch("https://data.alpaca.markets/v2/stocks/bars", params, 15)
    # Preserve parsed response and its exact entity hash before interpretation.
    import hashlib
    import os

    raw = directory / "bars.raw"
    with raw.open("xb") as f:
        f.write(response.entity_bytes)
        f.flush()
        os.fsync(f.fileno())
    save(
        directory / "response.json",
        dict(
            status=response.status_code,
            received_at=clock().isoformat(),
            sha256=hashlib.sha256(response.entity_bytes).hexdigest(),
            bytes=len(response.entity_bytes),
            headers=response.headers,
        ),
    )
    if response.status_code != 200:
        raise ValueError("actual raw completed-close source unavailable")
    body = json.loads(response.entity_bytes)
    if body.get("next_page_token") or not isinstance(body.get("bars"), dict):
        raise ValueError("close packet incomplete; no speculative continuation or price fill")
    if not set(body["bars"]) <= set(symbols):
        raise ValueError("unexpected close identity")
    close = pd.DataFrame(float("nan"), index=pd.to_datetime(sessions), columns=symbols)
    opened = close.copy()
    pointers = {}
    for symbol, rows in body["bars"].items():
        seen = set()
        for n, row in enumerate(rows):
            session = (
                datetime.fromisoformat(row["t"].replace("Z", "+00:00"))
                .astimezone(NEW_YORK)
                .date()
                .isoformat()
            )
            if session not in sessions or session in seen:
                raise ValueError("unexpected or duplicate raw session")
            seen.add(session)
            if not all(math.isfinite(float(row[k])) and float(row[k]) > 0 for k in ("o", "c", "v")):
                continue
            close.loc[session, symbol], opened.loc[session, symbol] = (
                float(row["c"]),
                float(row["o"]),
            )
            pointers[symbol + "/" + session] = f"/bars/{symbol}/{n}"
    clean, clean_open, report = sanitize_price_matrices(close, opened)
    trigger = {b.symbol for b in report.breaks if str(b.first_session_after)[:10] == sessions[-1]}
    # Missing prior row is explicitly invalid even if the last close exists.
    valid = {s: bool(clean[s].notna().all() and clean_open[s].notna().all()) for s in symbols}
    prices = {s: float(clean.loc[sessions[-1], s]) for s in symbols if valid[s]}
    completed = clock()
    if completed > cal["commit_at"] or runtime.store.load() != revision:
        raise ValueError("late close reception or changed applicable own state")
    q = dict(
        accepted=True,
        formation_month="2026-10",
        account_hash=runtime.auth["account_hash"],
        state_sha256=_hash(revision),
        scientific_contract=runtime.auth["bindings"]["scientific_contract"],
        received_at=completed.isoformat(),
        held_rights_complete=True,
        own_nav=20000.0,
        price_basis="raw_completed_decision_close",
        price_session=sessions[-1],
        prices=prices,
        hygiene_valid=valid,
        split_trigger={s: s in trigger for s in symbols},
        account_observation=obs_binding,
        source_entity_sha256=hashlib.sha256(response.entity_bytes).hexdigest(),
        source_pointers=pointers,
        hygiene=report.manifest(),
        limitation="current received close version; later corrections not retrospectively applied",
    )
    return save(directory / "quantity-input.json", q)


def confirm_initial(runtime, commit_binding, *, directory: Path, clock=lambda: datetime.now(UTC)):
    commit = json.loads(bound_bytes(runtime.root, commit_binding))
    nominal = datetime.fromisoformat(commit["committed_at"])
    if not nominal <= clock() < nominal + timedelta(minutes=1):
        raise ValueError("actual through-nominal continuity observation required")
    revision = runtime.store.load()
    state, _, _, _ = restore(runtime.root, revision["snapshot"])
    empty_initial(state)
    if _hash(revision) != commit["state_sha256"]:
        raise ValueError("own state changed; old early plan cannot impersonate nominal state")
    observed = runtime.capture_observation(quotes={}, directory=directory / "account")
    row = json.loads(bound_bytes(runtime.root, observed))
    if any(o["cid"].startswith("dia-base-") for o in row["orders"]):
        raise ValueError("actual own order existed during nominal continuity interval")
    if row["unborrowed_new_capacity"] < 20000 or runtime.store.load() != revision:
        raise ValueError("actual allocation/state no longer applicable")
    return save(
        directory / "continuity.json",
        dict(
            accepted=True,
            complete_own_state=True,
            account_hash=runtime.auth["account_hash"],
            state_sha256=_hash(revision),
            observed_at=clock().isoformat(),
            reconciled_through=row["completed_at"],
            observation=observed,
            scope="first-entry empty own book only; no order/cash/rights adoption",
        ),
    )


def receive_prior(root, transport, *, day, symbols, directory, clock=lambda: datetime.now(UTC)):
    """Current raw prior-session reference, default hygiene, no holding outcome filter."""
    import hashlib
    import os

    import pandas as pd

    from open_composer.research.features.price_hygiene import sanitize_price_matrices

    previous = day - timedelta(days=1)
    while us_equity_session_close(previous) is None:
        previous -= timedelta(days=1)
    earlier = previous - timedelta(days=1)
    while us_equity_session_close(earlier) is None:
        earlier -= timedelta(days=1)
    if clock().astimezone(NEW_YORK).date() != day or us_equity_session_close(day) is None:
        raise ValueError("reference reception must belong to current execution/risk session")
    _ensure_durable_directory(directory.parent.absolute())
    directory.mkdir(exist_ok=False)
    params = dict(
        symbols=",".join(symbols),
        timeframe="1Day",
        adjustment="raw",
        feed="sip",
        start=datetime.combine(earlier, datetime.min.time(), NEW_YORK).isoformat(),
        end=datetime.combine(day, datetime.min.time(), NEW_YORK).isoformat(),
        asof="-",
        sort="asc",
        limit=10000,
    )
    save(directory / "request.json", dict(params=params, started_at=clock().isoformat()))
    response = transport.fetch("https://data.alpaca.markets/v2/stocks/bars", params, 15)
    raw = directory / "bars.raw"
    with raw.open("xb") as f:
        f.write(response.entity_bytes)
        f.flush()
        os.fsync(f.fileno())
    capture = save(
        directory / "response.json",
        dict(
            status=response.status_code,
            received_at=clock().isoformat(),
            entity_sha256=hashlib.sha256(response.entity_bytes).hexdigest(),
            headers=response.headers,
        ),
    )
    if response.status_code != 200:
        raise ValueError("raw prior reference unavailable")
    body = json.loads(response.entity_bytes)
    if (
        body.get("next_page_token")
        or not isinstance(body.get("bars"), dict)
        or not set(body["bars"]) <= set(symbols)
    ):
        raise ValueError("partial/unknown raw reference packet")
    sessions = [earlier.isoformat(), previous.isoformat()]
    close = pd.DataFrame(float("nan"), index=pd.to_datetime(sessions), columns=symbols)
    opened = close.copy()
    for symbol, rows in body["bars"].items():
        seen = set()
        for row in rows:
            d = (
                datetime.fromisoformat(row["t"].replace("Z", "+00:00"))
                .astimezone(NEW_YORK)
                .date()
                .isoformat()
            )
            if d not in sessions or d in seen:
                raise ValueError("duplicate/unexpected prior session")
            seen.add(d)
            if all(math.isfinite(float(row[k])) and float(row[k]) > 0 for k in ("o", "c", "v")):
                close.loc[d, symbol], opened.loc[d, symbol] = float(row["c"]), float(row["o"])
    clean, clean_open, report = sanitize_price_matrices(close, opened)
    triggered = {b.symbol for b in report.breaks if b.first_session_after.date() == previous}
    references = {}
    for s in symbols:
        valid = bool(clean[s].notna().all() and clean_open[s].notna().all())
        references[s] = dict(
            session_date=previous.isoformat(),
            close=float(clean.iloc[-1][s]) if valid else None,
            hygiene_valid=valid,
            split_session=s in triggered,
            completed_before_execution=True,
        )
    result = save(directory / "references.json", references)
    save(
        directory / "lineage.json",
        dict(
            references=result,
            source=capture,
            hygiene=report.manifest(),
            scope="two completed adjacent sessions; no all-history completeness claim",
            limits="current provider vintage, not historical first-seen or future correction proof",
        ),
    )
    return result
