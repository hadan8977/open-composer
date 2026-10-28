"""Exact current recent-SIP window capture; no latest-after-cutoff substitution."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from open_composer.adapters.broker.alpaca_paper import _atomic_write_text
from open_composer.intraday_runner.source_dispatch_journal import _ensure_durable_directory
from open_composer.intraday_runner.source_method_bindings import quote_metadata, source_module


def receive_window(
    root: Path,
    transport,
    *,
    symbols,
    universe,
    cutoff: datetime,
    metadata_bindings,
    prior_references,
    directory: Path,
    clock=lambda: datetime.now(UTC),
):
    if not set(symbols) <= set(universe) or cutoff.tzinfo is None or cutoff.microsecond:
        raise ValueError("fixed symbols and aware wave required")
    if not cutoff <= clock() <= cutoff + timedelta(seconds=5):
        raise ValueError("outside actual frozen capture/dispatch interval")
    _ensure_durable_directory(directory.parent.absolute())
    directory.mkdir(exist_ok=False)
    # Include an event exactly at the integer-second cutoff without accepting a
    # later quote; the accepted parser retains its <=cutoff nanosecond rule.
    end = cutoff.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S") + ".000000001Z"
    params = dict(
        symbols=",".join(symbols),
        feed="sip",
        start=(cutoff - timedelta(seconds=5)).isoformat(),
        end=end,
        limit=10000,
        sort="asc",
        asof="-",
    )
    all_quotes = {s: [] for s in symbols}
    pages = []
    seen = set()
    token = None
    while True:
        now = clock()
        if now > cutoff + timedelta(seconds=5):
            raise ValueError("quote capture late/partial; no order")
        request = {**params, **({"page_token": token} if token else {})}
        prefix = directory / f"page-{len(pages):03d}"
        _atomic_write_text(
            prefix.with_suffix(".started.json"),
            json.dumps(dict(request=request, started_at=now.isoformat())) + "\n",
        )
        remaining = (cutoff + timedelta(seconds=5) - clock()).total_seconds()
        if remaining <= 0:
            raise ValueError("actual quote source deadline elapsed")
        response = transport.fetch(
            "https://data.alpaca.markets/v2/stocks/quotes",
            request,
            remaining,
        )
        with prefix.with_suffix(".raw").open("xb") as raw:
            raw.write(response.entity_bytes)
            raw.flush()
            os.fsync(raw.fileno())
        _atomic_write_text(
            prefix.with_suffix(".http.json"),
            json.dumps(
                dict(
                    status=response.status_code,
                    headers=response.headers,
                    received_at=clock().isoformat(),
                    bytes=len(response.entity_bytes),
                    sha256=hashlib.sha256(response.entity_bytes).hexdigest(),
                )
            )
            + "\n",
        )
        if response.status_code != 200:
            raise ValueError("required current SIP source unavailable")
        body = json.loads(response.entity_bytes)
        if not isinstance(body.get("quotes"), dict):
            raise ValueError("unknown quote response schema")
        for symbol, rows in body["quotes"].items():
            if symbol not in all_quotes or not isinstance(rows, list):
                raise ValueError("unexpected quote identity/schema")
            all_quotes[symbol].extend(rows)
        pages.append(str(prefix.with_suffix(".raw")))
        token = body.get("next_page_token")
        if not token:
            break
        if token in seen:
            raise ValueError("quote pagination loop")
        seen.add(token)
    parser = source_module(root, "quotes")
    conditions, venues = quote_metadata(root, metadata_bindings)
    ns = parser.timestamp_ns(cutoff.isoformat())
    parsed = {}
    from open_composer.research.features.price_hygiene import DEFAULT_MAX_ONE_DAY_PRICE_RATIO

    for s, rows in all_quotes.items():
        q = parser.select_quote(rows, ns, cutoff.date().isoformat(), conditions, venues)
        prior = prior_references.get(s)
        if prior is None:
            q = {**q, "valid": False, "reason": "missing_prior_reference"}
        else:
            q = parser.prior_unit_guard(
                q,
                prior["close"],
                prior["hygiene_valid"] is True,
                prior["split_session"] is True,
                DEFAULT_MAX_ONE_DAY_PRICE_RATIO,
            )
        parsed[s] = q
    if clock() > cutoff + timedelta(seconds=5):
        raise ValueError("quote capture completed after fixed window")
    return dict(status=200, feed="sip", quotes=all_quotes), parsed, pages
