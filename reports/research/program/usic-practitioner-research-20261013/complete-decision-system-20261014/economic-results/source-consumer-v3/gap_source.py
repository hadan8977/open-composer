"""Frozen conditional source price windows, never reconstructed signal bars."""

import calendar
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import groupby
from pathlib import Path

P = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(P / "economic-results"))
from source_clock import Observation, ns, number  # noqa: E402

SYMBOLS = frozenset({"COIN", "GME", "LMND", "SMCI", "SOFI", "SOUN"})
MAX_AGE_NS = 60 * 10**9
SYNTHETIC_DEPTH_PHYSICAL_SHARES = 100


def integer_ns(value):
    d = datetime.fromisoformat(value)
    return calendar.timegm(d.utctimetuple()) * 10**9 + d.microsecond * 1000


def utc_ns(value):
    whole, part = divmod(value, 10**9)
    return (
        datetime.fromtimestamp(whole, __import__("datetime").UTC).strftime("%Y-%m-%dT%H:%M:%S")
        + f".{part:09d}Z"
    )


def parse_quotes(body, symbol):
    assert symbol in SYMBOLS
    obj = json.loads(body, parse_float=Decimal)
    assert set(obj.get("quotes", {})) <= {symbol}
    assert "quotes" in obj and isinstance(obj["quotes"], dict), "missing_quote_schema"
    rows = obj["quotes"].get(symbol, [])
    sha = hashlib.sha256(body).hexdigest()
    token = obj.get("next_page_token")
    assert token is None or (isinstance(token, str) and 0 < len(token) <= 4096), (
        "invalid_page_token"
    )
    assert isinstance(rows, list), "invalid_quote_rows_shape"
    result = []
    for ordinal, row in enumerate(rows):
        assert isinstance(row.get("c"), list) and all(isinstance(c, str) for c in row["c"]), (
            "invalid_condition_shape"
        )
        result.append(
            Observation(
                kind="quotes",
                event_ns=ns(row["t"]),
                source_ordinal=ordinal,
                timestamp=row["t"],
                conditions=tuple(row.get("c", ())),
                tape=row.get("z"),
                source_entity_sha=sha,
                raw_message=json.dumps(row, sort_keys=True, default=str),
                bid=number(row["bp"]),
                ask=number(row["ap"]),
                bid_size_raw_units=number(row["bs"]),
                ask_size_raw_units=number(row["as"]),
                bid_exchange=row.get("bx"),
                ask_exchange=row.get("ax"),
            )
        )
    return tuple(result), token


def validate_pages(pages, symbol, start_ns, end_ns):
    """Pagination/parse/clock QA only; never firm market coverage or fill proof."""
    assert pages
    observations = []
    for page in pages:
        assert page["http_status"] == 200 and page["entity_complete"] is True
        parsed, token = parse_quotes(page["body"], symbol)
        assert token == page["next_page_token"]
        observations.extend(parsed)
    assert pages[-1]["next_page_token"] is None
    assert all(p["next_page_token"] is not None for p in pages[:-1])
    assert all(start_ns <= q.event_ns <= end_ns for q in observations), "out_of_query_clock"
    assert all(
        a.event_ns <= b.event_ns for a, b in zip(observations, observations[1:], strict=False)
    ), "unsorted_source_clock"
    return tuple(observations), dict(
        rows=len(observations),
        pages=len(pages),
        source_query_and_page_QA=True,
        source_provenance="actual_provider_current_vintage",
        source_entity_sha256=[hashlib.sha256(page["body"]).hexdigest() for page in pages],
        firm_NBBO=False,
        historical_first_visible=None,
        exact_duplicate_extra=sum(
            n - 1 for n in Counter(q.raw_message for q in observations).values()
        ),
        equal_timestamp_extra=len(observations) - len({q.event_ns for q in observations}),
        size_units="original_unmapped_provider_units",
        synthetic_depth_physical_shares=SYNTHETIC_DEPTH_PHYSICAL_SHARES,
    )


@dataclass(frozen=True)
class GapPriceWindow:
    symbol: str
    start_ns: int
    end_ns: int
    initial: Observation | None
    events: tuple[Observation, ...]
    unresolved_ns: int | None
    unresolved_reason: str | None
    source_QA: dict


def qualify_gap(symbol, start_ns, end_ns, observations, qa):
    assert symbol in SYMBOLS and start_ns < end_ns
    assert qa.get("source_query_and_page_QA") is True
    assert all(
        a.event_ns <= b.event_ns for a, b in zip(observations, observations[1:], strict=False)
    )
    before = [q for q in observations if q.event_ns < start_ns]
    initial = before[-1] if before else None
    if initial is None:
        return GapPriceWindow(
            symbol,
            start_ns,
            end_ns,
            None,
            (),
            start_ns + 2,
            "missing_causally_prior_initial_BBO",
            qa,
        )
    # Do not skip a bad most recent quote to rescue an old apparently valid one.
    prior_same = [q for q in before if q.event_ns == initial.event_ns]
    reason = initial.quote_problem()
    if len({q.raw_message for q in prior_same}) > 1:
        reason = "ambiguous_same_ns_initial_BBO"
    if start_ns - initial.event_ns >= MAX_AGE_NS:
        reason = "stale_initial_BBO"
    if reason:
        return GapPriceWindow(symbol, start_ns, end_ns, initial, (), start_ns + 2, reason, qa)
    events = []
    expiry = initial.event_ns + MAX_AGE_NS
    first = None
    why = None
    for at, group in groupby(
        (q for q in observations if start_ns <= q.event_ns < end_ns), key=lambda q: q.event_ns
    ):
        group = tuple(group)
        if at >= expiry:
            first, why = expiry, "BBO_age_limit_exceeded"
            break
        if len({q.raw_message for q in group}) > 1:
            first, why = at, "ambiguous_same_ns_quote_order"
            break
        bad = next((q.quote_problem() for q in group if q.quote_problem()), None)
        if bad:
            first, why = at, bad
            break
        events.extend(group)  # Identical messages retained; distinct ties refused.
        expiry = at + MAX_AGE_NS
    if first is None and expiry < end_ns:
        first, why = expiry, "BBO_age_limit_exceeded"
    return GapPriceWindow(symbol, start_ns, end_ns, initial, tuple(events), first, why, qa)
