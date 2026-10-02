#!/usr/bin/env python3
"""Refresh config/prediction_markets/polymarket_watchlist.yaml from the public Gamma API.

T-20261002-45. Watchlist markets resolve (the October FOMC on 10-28, the September CPI on
10-14), so ids go stale. This script finds the current active markets of each group and
rewrites the watchlist:

  fed_<month>_<year>            all outcome markets of the next two Fed decision events
  recession                     "US recession by end of <year>" for this and next year
  cpi_us_monthly_<mon>_<year>   all brackets of the next US CPI MoM release
  tariff_china_rate_end_<year>  US tariff rate on China, the nearest year-end event
  government_shutdown           open "another US government shutdown" markets
  midterms_<year>               House and Senate control

Rules: existing ids that are still active (and not closed) are kept with their note; new
ones are added; resolved, closed or unlisted ones are dropped and listed in the output.
``--dry-run`` prints the diff and writes nothing. Public Gamma API only: no key, no wallet,
no order. Research input only.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import collect_prediction_markets as collect  # noqa: E402

GAMMA = collect.GAMMA_BASE
WATCHLIST = collect.WATCHLIST
MONTHS = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]
HEADER = """\
# Curated Polymarket watchlist for scripts/collect_prediction_markets.py (T-20261002-44).
# Maintained by scripts/refresh_polymarket_watchlist.py (T-20261002-45, weekly): it keeps ids
# that are still active, adds the current markets of each group and drops resolved ones.
# Market ids come from the Gamma API (https://gamma-api.polymarket.com/markets/{id}).
# Research input only: Polymarket is offshore with a US relaunch, prices are never an order
# trigger.
"""


# ------------------------------------------------------------------- API helpers


def search_events(http: collect.Http, query: str) -> list[dict[str, Any]]:
    body = http.get(
        f"{GAMMA}/public-search",
        {"q": query, "limit_per_type": 20, "events_status": "active"},
    )
    return list((body or {}).get("events") or [])


def event_end(event: dict[str, Any]) -> datetime | None:
    text = event.get("endDate")
    if not text:
        return None
    return datetime.fromisoformat(str(text).replace("Z", "+00:00"))


def live_events(events: list[dict[str, Any]], pattern: str, now: datetime) -> list[dict]:
    """Active, not closed events whose slug matches ``pattern`` and that end in the future."""
    rx = re.compile(pattern)
    out = []
    for e in events:
        end = event_end(e)
        if e.get("closed") or not e.get("active", True) or end is None or end < now:
            continue
        if rx.match(str(e.get("slug", ""))):
            out.append(e)
    return sorted(out, key=lambda e: (event_end(e), str(e.get("slug"))))


def live_markets(event: dict[str, Any]) -> list[dict[str, Any]]:
    return [m for m in event.get("markets") or [] if m.get("active") and not m.get("closed")]


def _title(m: dict[str, Any]) -> str:
    return str(m.get("groupItemTitle") or "").strip()


def _question(m: dict[str, Any]) -> str:
    return str(m.get("question") or "").strip().rstrip("?")


# ------------------------------------------------------------------- group finders
# Each finder returns [(group, market, note)] for the markets that belong on the watchlist.

Found = list[tuple[str, dict[str, Any], str]]


def find_fed(http: collect.Http, now: datetime) -> Found:
    events = live_events(
        search_events(http, "Fed decision in"), r"^fed-decision-in-[a-z]+(-\d+)?$", now
    )[:2]
    out: Found = []
    for e in events:
        end = event_end(e)
        assert end is not None
        # the meeting month is in the slug (the event can end the day after the meeting, UTC)
        slug_month = str(e["slug"]).split("-")[3]
        month = slug_month if slug_month in MONTHS else MONTHS[end.month - 1]
        year = end.year
        group = f"fed_{month}_{year}"
        for m in live_markets(e):
            item = _title(m)
            item = "no change" if item.lower() == "no change" else item
            out.append((group, m, f"Fed {item} after the {month.capitalize()} {year} meeting"))
    return out


def find_recession(http: collect.Http, now: datetime) -> Found:
    out: Found = []
    for year in (now.year, now.year + 1):
        events = live_events(
            search_events(http, f"US recession by end of {year}"),
            rf"^us-recession-by-end-of-{year}(-\d+)?$",
            now,
        )
        for e in events[:1]:
            out.extend(("recession", m, _question(m)) for m in live_markets(e))
    return out


def find_cpi(http: collect.Http, now: datetime) -> Found:
    events = live_events(
        search_events(http, "inflation us monthly"), r"^[a-z]+-inflation-us-monthly(-\d+)?$", now
    )
    if not events:
        return []
    e = events[0]  # earliest end date = the next CPI release
    month = str(e["slug"]).split("-")[0]
    end = event_end(e)
    assert end is not None
    ref_month = MONTHS.index(month) + 1 if month in MONTHS else end.month
    year = end.year - 1 if ref_month > end.month else end.year
    group = f"cpi_us_monthly_{month[:3]}_{year}"
    return [
        (group, m, f"{month.capitalize()} US CPI MoM {_title(m) or _question(m)}")
        for m in live_markets(e)
    ]


def find_tariff(http: collect.Http, now: datetime) -> Found:
    events = live_events(
        search_events(http, "tariff rate on China"),
        r"^us-tariff-rate-on-china-on-december-31-\d{4}(-\d+)?$",
        now,
    )
    if not events:
        return []
    e = events[0]
    year = int(re.search(r"december-31-(\d{4})", str(e["slug"])).group(1))  # type: ignore[union-attr]
    return [
        (
            f"tariff_china_rate_end_{year}",
            m,
            f"US tariff rate on China {_title(m) or _question(m)} on Dec 31, {year}",
        )
        for m in live_markets(e)
    ]


def find_shutdown(http: collect.Http, now: datetime) -> Found:
    events = live_events(
        search_events(http, "government shutdown"), r"^.*government-shutdown.*$", now
    )
    out: Found = []
    for e in events:
        out.extend(("government_shutdown", m, _question(m)) for m in live_markets(e))
    return out


def midterm_year(today: date) -> int:
    year = today.year + today.year % 2
    return year + 2 if today > date(year, 11, 15) else year


def find_midterms(http: collect.Http, now: datetime) -> Found:
    year = midterm_year(now.date())
    out: Found = []
    for chamber in ("house", "senate"):
        events = live_events(
            search_events(http, f"which party will win the {chamber} in {year}"),
            rf"^which-party-will-win-the-{chamber}-in-{year}(-\d+)?$",
            now,
        )
        for e in events[:1]:
            # only the two real party markets are active; placeholder parties are inactive
            out.extend((f"midterms_{year}", m, _question(m)) for m in live_markets(e))
    return out


FINDERS = (find_fed, find_recession, find_cpi, find_tariff, find_shutdown, find_midterms)


# ---------------------------------------------------------------------- refresh


def lookup_existing(http: collect.Http, ids: list[str]) -> dict[str, dict[str, Any]]:
    got: dict[str, dict[str, Any]] = {}
    for start in range(0, len(ids), 20):
        chunk = ids[start : start + 20]
        body = http.get(f"{GAMMA}/markets", {"id": chunk, "limit": len(chunk)}) or []
        for m in body:
            got[str(m.get("id"))] = m
    return got


def refresh(
    http: collect.Http,
    existing: list[dict[str, str]],
    now: datetime,
) -> dict[str, Any]:
    found: Found = []
    empty_groups: list[str] = []
    for finder in FINDERS:
        rows = finder(http, now)
        if not rows:
            empty_groups.append(finder.__name__.removeprefix("find_"))
        found.extend(rows)
    old = {m["id"]: m for m in existing}
    new_entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for group, market, note in found:
        mid = str(market["id"])
        if mid in seen:
            continue
        seen.add(mid)
        keep_note = old[mid]["note"] if mid in old and old[mid].get("note") else note
        new_entries.append({"id": mid, "group": group, "note": keep_note})
    leftovers = [m for m in existing if m["id"] not in seen]
    status = lookup_existing(http, [m["id"] for m in leftovers]) if leftovers else {}
    if leftovers and not status and existing:
        raise RuntimeError("Gamma returned none of the existing watchlist ids; refusing to wipe")
    dropped: list[dict[str, str]] = []
    for m in leftovers:
        info = status.get(m["id"])
        if info is None:
            dropped.append({**m, "reason": "not returned by Gamma"})
        elif info.get("closed") or not info.get("active"):
            dropped.append({**m, "reason": "closed" if info.get("closed") else "inactive"})
        else:
            new_entries.append({"id": m["id"], "group": m["group"], "note": m.get("note", "")})
    added = [e for e in new_entries if e["id"] not in old]
    kept = [e for e in new_entries if e["id"] in old]
    # a group counted as found but empty in this run is reported, never silently dropped
    return {
        "markets": new_entries,
        "added": added,
        "dropped": dropped,
        "kept": kept,
        "empty_finders": empty_groups,
    }


def render(markets: list[dict[str, str]], looked_up_at: str) -> str:
    lines = [HEADER + "version: 1", f'looked_up_at: "{looked_up_at}"', "markets:"]
    for m in markets:
        note = str(m["note"]).replace('"', "'")
        lines.append(f'  - {{id: "{m["id"]}", group: {m["group"]}, note: "{note}"}}')
    return "\n".join(lines) + "\n"


def format_diff(result: dict[str, Any], old_stamp: str | None, new_stamp: str) -> str:
    out = [f"looked_up_at: {old_stamp} -> {new_stamp}"]
    out += [f"+ {e['id']} [{e['group']}] {e['note']}" for e in result["added"]]
    out += [f"- {e['id']} [{e['group']}] {e['note']} ({e['reason']})" for e in result["dropped"]]
    out.append(
        f"kept {len(result['kept'])}, added {len(result['added'])}, "
        f"dropped {len(result['dropped'])}, total {len(result['markets'])}"
    )
    if result["empty_finders"]:
        out.append(f"warning: no active markets found for: {', '.join(result['empty_finders'])}")
    return "\n".join(out)


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist", type=Path, default=WATCHLIST)
    parser.add_argument("--dry-run", action="store_true", help="print the diff, write nothing")
    parser.add_argument("--now", help="ISO UTC time override (tests)")
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    payload = yaml.safe_load(args.watchlist.read_text(encoding="utf-8"))
    existing = collect.load_watchlist(args.watchlist)
    try:
        result = refresh(collect.Http(), existing, now)
    except Exception as exc:
        print(f"refresh_polymarket_watchlist failed: {exc}", file=sys.stderr)
        return 1
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(format_diff(result, payload.get("looked_up_at"), stamp))
    if args.dry_run:
        print("dry run: nothing written")
        return 0
    write_atomic(args.watchlist, render(result["markets"], stamp))
    print(f"wrote {args.watchlist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
