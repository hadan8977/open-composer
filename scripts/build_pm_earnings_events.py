#!/usr/bin/env python3
"""Polymarket earnings-beat event table for h20261004_pm_earnings_beat_odds (T-20261004-51).

One row per resolved "Will X beat quarterly earnings?" event, with the contract fields,
the 8-K announcement time, the NYSE signal day S and reaction day R, and the Yes-token
prices P (last print at or before 15:00 ET on S) and P7 (same, seven calendar days
earlier). No stock return is read here: the table is the frozen design's input only.

Public Gamma and CLOB endpoints, no key, no wallet, nothing is written to a broker.
Output (not committed): data/research/prediction_markets/polymarket_earnings/events.parquet
and the coverage funnel in the iteration's ``data-feasibility.json`` (merged in place).

Usage::

    uv run python scripts/build_pm_earnings_events.py [--limit N] [--no-coverage]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.market_sessions import (  # noqa: E402
    next_us_equity_session,
    previous_us_equity_session,
    us_equity_session_close,
)

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
ET = "America/New_York"
ITER_DIR = ROOT / "reports/research/iterations/h20261004_pm_earnings_beat_odds"
OUT_DIR = ROOT / "data/research/prediction_markets/polymarket_earnings"
EARNINGS_DIR = ROOT / "data/features/earnings_events"
PAGE = 100
HOURLY = 60
FINER_FIDELITIES = (10, 1)
LOOKBACK_DAYS = 8
STALE_HOURS = 24.0
MIN_VOLUME_USD = 5000.0
MIN_PRICE_USD = 5.0
MATCH_DAYS = 2
#: The terms page was not fetched; the facts below are what the API and docs show.
POLYMARKET_DATA_TERMS = (
    "Public Gamma and CLOB read endpoints, no key; rate limits per "
    "docs.polymarket.com/api-reference/rate-limits (/prices-history 1000 per 10 s, /events 500 "
    "per 10 s, IP level). Terms of use not re-read for this build; research use only, "
    "no redistribution of the raw table (never committed)."
)

_SLUG_NEW = re.compile(
    r"^(?P<prefix>.+?)-quarterly-earnings-(?P<basis>gaap|nongaap)-eps-"
    r"(?P<m>\d\d)-(?P<d>\d\d)-(?P<y>\d{4})-(?P<eps>.+)$"
)
_TITLE_TICKER = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,6})\)")


def _load_http_class() -> Any:
    path = ROOT / "scripts/collect_prediction_markets.py"
    spec = importlib.util.spec_from_file_location("collect_prediction_markets", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("collect_prediction_markets", module)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ parsing


def parse_eps(text: str) -> float | None:
    """'0pt76' -> 0.76, 'neg5pt28' -> -5.28, '2' -> 2.0."""
    s = text.strip().lower()
    sign = -1.0 if s.startswith("neg") else 1.0
    s = s.removeprefix("neg").replace("pt", ".")
    try:
        return sign * float(s)
    except ValueError:
        return None


def parse_event_identity(title: str, slug: str) -> dict[str, Any]:
    """Ticker from the title "(TICKER)", checked against the slug prefix (new slugs only)."""
    out: dict[str, Any] = {
        "ticker": None,
        "ticker_slug_check": "none",
        "slug_date": None,
        "eps_basis": None,
        "consensus_eps": None,
    }
    t = _TITLE_TICKER.search(title or "")
    m = _SLUG_NEW.match(slug or "")
    if m:
        out["eps_basis"] = m.group("basis")
        out["consensus_eps"] = parse_eps(m.group("eps"))
        try:
            out["slug_date"] = date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
        except ValueError:
            out["slug_date"] = None
    if not t:
        return out
    ticker = t.group(1)
    if m:
        norm = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())  # noqa: E731
        if norm(m.group("prefix")) != norm(ticker):
            out["ticker_slug_check"] = "mismatch"
            return out
        out["ticker_slug_check"] = "ok"
    else:
        out["ticker_slug_check"] = "title_only"
    out["ticker"] = ticker
    return out


def _jl(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, list) else None


def event_row(event: dict[str, Any]) -> dict[str, Any] | None:
    """One flat row per event with exactly one Yes/No market; None otherwise."""
    markets = event.get("markets") or []
    if len(markets) != 1:
        return None
    m = markets[0]
    outcomes = _jl(m.get("outcomes")) or []
    tokens = _jl(m.get("clobTokenIds")) or []
    prices = _jl(m.get("outcomePrices")) or []
    if "Yes" not in outcomes or len(tokens) != len(outcomes) or len(prices) != len(outcomes):
        return None
    yes = outcomes.index("Yes")
    try:
        yes_final = float(prices[yes])
    except (TypeError, ValueError):
        yes_final = float("nan")
    beat: int | None = 1 if yes_final == 1.0 else 0 if yes_final == 0.0 else None
    title = event.get("title") or m.get("question") or ""
    slug = event.get("slug") or m.get("slug") or ""
    row = {
        "slug": slug,
        "title": title,
        "event_id": str(event.get("id")),
        "yes_token_id": str(tokens[yes]),
        "volume_usd": _num(
            event.get("volume") if event.get("volume") is not None else m.get("volume")
        ),
        "end_utc": _ts(m.get("endDate") or event.get("endDate")),
        "start_utc": _ts(m.get("startDate") or event.get("startDate")),
        "created_utc": _ts(event.get("creationDate") or event.get("createdAt")),
        "closed_utc": _ts(event.get("closedTime") or m.get("closedTime")),
        "beat": beat,
    }
    row.update(parse_event_identity(title, slug))
    return row


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ts(value: Any) -> pd.Timestamp | None:
    if not value:
        return None
    try:
        return (
            pd.Timestamp(value).tz_convert("UTC")
            if pd.Timestamp(value).tzinfo
            else (pd.Timestamp(value).tz_localize("UTC"))
        )
    except (ValueError, TypeError):
        return None


# ------------------------------------------------------------------ fetching


def fetch_events(http: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
    """All closed earnings events from Gamma, paginated until a short page."""
    events: list[dict[str, Any]] = []
    offset = 0
    while True:
        body = http.get(
            f"{GAMMA_BASE}/events",
            {"tag_slug": "earnings", "closed": "true", "limit": PAGE, "offset": offset},
        )
        if not isinstance(body, list):
            raise RuntimeError("unexpected Gamma response shape")
        events.extend(body)
        if len(body) < PAGE or (limit is not None and len(events) >= limit):
            break
        offset += PAGE
    return events[:limit] if limit is not None else events


def price_history(
    http: Any, token: str, start_ts: int, end_ts: int
) -> tuple[list[tuple[int, float]], int | None]:
    """Hourly history for a window; finer fidelity only if hourly is empty."""
    for fidelity in (HOURLY, *FINER_FIDELITIES):
        body = http.get(
            f"{CLOB_BASE}/prices-history",
            {"market": token, "startTs": start_ts, "endTs": end_ts, "fidelity": fidelity},
            allow_404=True,
        )
        hist = (body or {}).get("history") or []
        points = sorted((int(h["t"]), float(h["p"])) for h in hist if "t" in h and "p" in h)
        if points:
            return points, fidelity
    return [], None


def last_at_or_before(
    points: list[tuple[int, float]], cut_ts: int
) -> tuple[float | None, int | None]:
    eligible = [(t, p) for t, p in points if t <= cut_ts]
    if not eligible:
        return None, None
    t, p = eligible[-1]
    return p, t


# ------------------------------------------------------------------ timing


def eastern_wall_clock(acceptance: pd.Series) -> pd.Series:
    """Treat acceptance_utc as US/Eastern wall-clock time (the T-03 finding)."""
    wall = pd.to_datetime(acceptance, utc=True).dt.tz_convert(None)
    return wall.dt.tz_localize(ET, ambiguous=False, nonexistent="shift_forward")


def reaction_and_signal_day(acceptance_et: pd.Timestamp) -> tuple[date, date, str]:
    """(S, R, kind) for an announcement at an Eastern wall-clock instant.

    Before 09:30 ET or on a non-session day: R is the next session at or after the
    date, S the session before R. Between 09:30 and 16:00: R is that session, entry the
    previous close. At or after 16:00: S is that session, R the next one.
    """
    d = acceptance_et.date()
    clock = acceptance_et.time()
    is_session = us_equity_session_close(d) is not None
    if not is_session:
        r = next_us_equity_session(d)
        return previous_us_equity_session(r), r, "non_session_day"
    if clock < dtime(9, 30):
        return previous_us_equity_session(d), d, "pre_market"
    if clock < dtime(16, 0):
        return previous_us_equity_session(d), d, "intraday"
    return d, next_us_equity_session(d), "after_close"


def match_announcements(events: pd.DataFrame, earnings: pd.DataFrame) -> pd.DataFrame:
    """Nearest 8-K item 2.02 within +/-2 calendar days of the slug date, by ticker."""
    items = earnings[earnings["items"].astype(str).str.contains(r"(?:^|,)2\.02(?:,|$)")].copy()
    items["acceptance_et"] = eastern_wall_clock(items["acceptance_utc"])
    items["acc_date"] = items["acceptance_et"].dt.tz_localize(None).dt.normalize()
    by_ticker = {k: g for k, g in items.groupby("ticker")}
    rows: list[dict[str, Any]] = []
    for ev in events.itertuples():
        out = {"accession": None, "acceptance_et": pd.NaT, "timing_source": "none"}
        g = by_ticker.get(ev.ticker) if ev.ticker else None
        anchor = ev.slug_date
        if g is not None and anchor is not None:
            anchor_ts = pd.Timestamp(anchor)
            diff = (g["acc_date"] - anchor_ts).abs()
            near = g[diff <= pd.Timedelta(days=MATCH_DAYS)]
            if len(near):
                best = near.loc[(near["acc_date"] - anchor_ts).abs().idxmin()]
                out = {
                    "accession": best["accession"],
                    "acceptance_et": best["acceptance_et"],
                    "timing_source": "8k_2.02",
                }
        rows.append(out)
    return pd.DataFrame(rows, index=events.index)


def add_sessions(events: pd.DataFrame) -> pd.DataFrame:
    s_list, r_list, k_list = [], [], []
    for acc in events["acceptance_et"]:
        if pd.isna(acc):
            s_list.append(pd.NaT)
            r_list.append(pd.NaT)
            k_list.append(None)
            continue
        s, r, kind = reaction_and_signal_day(acc)
        s_list.append(pd.Timestamp(s))
        r_list.append(pd.Timestamp(r))
        k_list.append(kind)
    events = events.copy()
    events["S"] = s_list
    events["R"] = r_list
    events["timing_kind"] = k_list
    return events


def cut_ts(day: date, days_back: int = 0) -> int:
    """Epoch seconds of 15:00 ET on ``day`` minus ``days_back`` calendar days (same wall clock)."""
    wall = pd.Timestamp(datetime.combine(day - timedelta(days=days_back), dtime(15, 0)))
    return int(wall.tz_localize(ET, nonexistent="shift_forward").timestamp())


def attach_prices(events: pd.DataFrame, http: Any, log: Any = print) -> pd.DataFrame:
    cols = {
        k: []
        for k in (
            "P",
            "P_print_utc",
            "P_age_h",
            "P_stale",
            "P7",
            "P7_print_utc",
            "P7_age_h",
            "P7_stale",
            "price_fidelity",
            "n_points",
            "price_error",
        )
    }
    total = int(events["S"].notna().sum())
    done = 0
    for ev in events.itertuples():
        rec: dict[str, Any] = dict.fromkeys(cols)
        if pd.isna(ev.S):
            rec["price_error"] = "no_timing"
        else:
            day = ev.S.date()
            end_ts = cut_ts(day)
            start_ts = cut_ts(day, LOOKBACK_DAYS)
            try:
                points, fid = price_history(http, ev.yes_token_id, start_ts, end_ts)
            except (RuntimeError, TimeoutError) as exc:
                points, fid = [], None
                rec["price_error"] = str(exc)[:80]
            rec["price_fidelity"] = fid
            rec["n_points"] = len(points)
            for name, back in (("P", 0), ("P7", 7)):
                cut = cut_ts(day, back)
                p, t = last_at_or_before(points, cut)
                rec[name] = p
                if t is not None:
                    age = (cut - t) / 3600.0
                    rec[f"{name}_print_utc"] = pd.Timestamp(t, unit="s", tz="UTC")
                    rec[f"{name}_age_h"] = age
                    rec[f"{name}_stale"] = bool(age > STALE_HOURS)
                else:
                    rec[f"{name}_stale"] = True
            done += 1
            if done % 100 == 0:
                log(f"prices {done}/{total}")
        for k in cols:
            cols[k].append(rec[k])
    out = events.copy()
    for k, v in cols.items():
        out[k] = v
    return out


# ------------------------------------------------------------------ coverage


def coverage_funnel(df: pd.DataFrame) -> dict[str, Any]:
    """Counts at each filter step. Close-at-least-$5 is checked in the test script (needs bars)."""
    steps: list[tuple[str, pd.Series]] = []
    mask = pd.Series(True, index=df.index)
    steps.append(("all_events", mask))
    mask = mask & df["ticker"].notna() & df["beat"].notna()
    steps.append(("ticker_parsed_and_resolved", mask))
    mask = mask & df["sip_bars_ok"].fillna(False)
    steps.append(("sip_bars", mask))
    mask = mask & df["R"].notna()
    steps.append(("timing_matched_8k", mask))
    mask = mask & df["P"].notna()
    steps.append(("p_valid", mask))
    mask = mask & ~df["P_stale"].fillna(True).astype(bool)
    steps.append(("not_stale", mask))
    mask = mask & (df["volume_usd"].fillna(0) >= MIN_VOLUME_USD)
    steps.append(("volume_ge_5k", mask))
    funnel = {name: int(m.sum()) for name, m in steps}
    primary = df[mask].copy()
    week = pd.to_datetime(primary["R"]).dt.isocalendar()
    keys = week["year"].astype(str) + "-W" + week["week"].astype(str).str.zfill(2)
    per_week = keys.value_counts().sort_index()
    return {
        "funnel": funnel,
        "primary_events": int(len(primary)),
        "iso_weeks_with_events": int(len(per_week)),
        "weeks_with_ge_6_events": int((per_week >= 6).sum()),
        "events_per_week": {k: int(v) for k, v in per_week.items()},
    }


# ------------------------------------------------------------------ main


def sip_symbols_with_bars() -> set[str]:
    import duckdb

    con = duckdb.connect()
    try:
        con.execute("SET memory_limit='400MB'")
        rows = con.execute(
            "SELECT DISTINCT symbol FROM read_parquet('data/sip/daily/2026/*.parquet')"
        ).fetchall()
    finally:
        con.close()
    return {r[0] for r in rows}


def build(
    *, limit: int | None, http: Any, earnings: pd.DataFrame, sip_symbols: set[str], log: Any = print
) -> pd.DataFrame:
    raw = fetch_events(http, limit=limit)
    log(f"gamma events: {len(raw)}")
    rows = [r for r in (event_row(e) for e in raw) if r is not None]
    events = pd.DataFrame(rows).drop_duplicates("slug").reset_index(drop=True)
    events["slug_date"] = pd.to_datetime(events["slug_date"])
    end_date = pd.to_datetime(events["end_utc"], utc=True).dt.tz_localize(None).dt.normalize()
    events["date_source"] = events["slug_date"].notna().map({True: "slug", False: "end_utc"})
    events["slug_date"] = events["slug_date"].fillna(end_date)
    events["slug_date"] = events["slug_date"].dt.date
    events["sip_bars_ok"] = events["ticker"].map(lambda t: bool(t) and t in sip_symbols)
    matched = match_announcements(events, earnings)
    events = pd.concat([events, matched], axis=1)
    events = add_sessions(events)
    events = attach_prices(events, http, log=log)
    return events


def merge_feasibility(path: Path, coverage: dict[str, Any], extra: dict[str, Any]) -> None:
    doc = json.loads(path.read_text()) if path.exists() else {}
    doc["data_build"] = {
        "script": "scripts/build_pm_earnings_events.py",
        "built_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **coverage,
        **extra,
        "polymarket_data_terms": POLYMARKET_DATA_TERMS,
    }
    path.write_text(json.dumps(doc, indent=2, default=str) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="pilot: first N events only")
    ap.add_argument("--no-coverage", action="store_true")
    ap.add_argument("--budget-min", type=float, default=40.0)
    args = ap.parse_args(argv)

    collect = _load_http_class()
    http = collect.Http(budget_s=args.budget_min * 60.0, min_interval_s=0.21)
    earnings = pd.concat(
        [
            pd.read_parquet(
                EARNINGS_DIR / f"{y}.parquet",
                columns=["ticker", "accession", "acceptance_utc", "items"],
            )
            for y in (2025, 2026)
        ],
        ignore_index=True,
    )
    df = build(limit=args.limit, http=http, earnings=earnings, sip_symbols=sip_symbols_with_bars())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / ("events.pilot.parquet" if args.limit else "events.parquet")
    df.to_parquet(out, index=False)
    print(f"wrote {len(df)} rows -> {out}")
    if not args.no_coverage and not args.limit:
        cov = coverage_funnel(df)
        extra = {
            "earnings_events_table_max_acceptance": str(
                pd.to_datetime(earnings["acceptance_utc"], utc=True).max()
            ),
            "eps_basis_counts": df["eps_basis"].fillna("unknown").value_counts().to_dict(),
            "ticker_slug_check_counts": df["ticker_slug_check"].value_counts().to_dict(),
            "timing_kind_counts": df["timing_kind"].fillna("none").value_counts().to_dict(),
            "date_source_counts": df["date_source"].value_counts().to_dict(),
            "p7_available": int(df["P7"].notna().sum()),
            "price_fidelity_counts": df["price_fidelity"]
            .fillna(-1)
            .astype(int)
            .value_counts()
            .to_dict(),
            "price_error_counts": df["price_error"].fillna("none").value_counts().to_dict(),
            "notes": [
                "Hourly CLOB points are bucket samples; print time is the point time.",
                "S and R use the repo NYSE calendar; 16:00 ET cutoff holds on early closes too.",
                "GAAP-basis contracts are kept; the basis is recorded per event.",
            ],
        }
        merge_feasibility(ITER_DIR / "data-feasibility.json", cov, extra)
        print(json.dumps(cov["funnel"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
