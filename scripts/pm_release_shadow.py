#!/usr/bin/env python3
"""Forward shadow log for the parked H1 (Kalshi release uncertainty and the announcement premium).

T-20261002-45. The first preregistered test (iteration h20261002_pm_macro_uncertainty,
T-20261002-44) was inconclusive: D = +13.9 bp over 79 non-FOMC release days. This script
accumulates forward evidence under the same frozen definitions (hypotheses.md), without
changing any of them. It places no order and reads no account: Kalshi public API (no key)
and SIP daily bars, read-only.

Subcommands
  signal   On the afternoon before a release day T (US/Eastern 15:00-15:50 on T-1, the
           previous NYSE session) compute U and U_rel for every Kalshi macro event released on
           T from the hourly candles ending at or before 15:00 ET, and append them to
           ``data/features/prediction_markets/h1_shadow/signals.jsonl`` (append-only; an
           event or day already logged is never written again). Outside the window: exit 0,
           write nothing.
  realize  For each logged release day with T at or before the last SIP daily bar, append
           QQQ, SPY and IWM R_cc and R_co (raw and in excess of BIL) to ``realized.jsonl``.
  summary  Forward-only count of release days, D (would_hold minus not) and the count still
           needed to reach 60. Labelled ``forward_only_no_decision``: it decides nothing.

Definitions mirror the builder (scripts/build_kalshi_release_uncertainty.py), imported, not
copied: U_rel divides U by the median U of the previous 12 events of the series, taken from
``release_uncertainty.parquet`` plus earlier forward rows. ``would_hold`` is candidate U1: day
U_rel > 1 on a day that is not an FOMC day (the frozen choice treats a CPI, payrolls or GDP
release on an FOMC decision day as an FOMC day too). ``would_hold_incl_fomc`` is U7.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from dateutil.easter import easter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import build_kalshi_release_uncertainty as bk  # noqa: E402
import fetch_kalshi_macro as fk  # noqa: E402
import run_h20261002_pm_macro_uncertainty as h1  # noqa: E402

ET = ZoneInfo("America/New_York")
SHADOW_DIR = ROOT / "data/features/prediction_markets/h1_shadow"
SIGNALS = "signals.jsonl"
REALIZED = "realized.jsonl"
RELEASE_UNCERTAINTY = bk.OUT_PATH
WINDOW_START = (15, 0)
WINDOW_END = (15, 50)
TARGET_DAYS = 60
SERIES = tuple(bk.PRIMARY_SERIES) + tuple(bk.FOMC_SERIES)
SHADOW_SYMBOLS = ("QQQ", "SPY", "IWM")
LABEL = "forward_only_no_decision"

# --------------------------------------------------------------- NYSE calendar

_EXTRA_CLOSURES = {date(2025, 1, 9)}  # National Day of Mourning (President Carter)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(d: date) -> date | None:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def nyse_holidays(year: int) -> set[date]:
    """Full-day NYSE closures in ``year`` (rule-based, 2022+ includes Juneteenth)."""
    out: set[date] = set()
    new_year = date(year, 1, 1)
    if new_year.weekday() != 5:  # a Saturday New Year's Day is not observed on Friday
        obs = _observed(new_year)
        if obs:
            out.add(obs)
    out.add(_nth_weekday(year, 1, 0, 3))  # Martin Luther King Jr. Day
    out.add(_nth_weekday(year, 2, 0, 3))  # Washington's Birthday
    out.add(easter(year) - timedelta(days=2))  # Good Friday
    out.add(_last_weekday(year, 5, 0))  # Memorial Day
    if year >= 2022:
        obs = _observed(date(year, 6, 19))  # Juneteenth
        if obs:
            out.add(obs)
    obs = _observed(date(year, 7, 4))
    if obs:
        out.add(obs)
    out.add(_nth_weekday(year, 9, 0, 1))  # Labor Day
    out.add(_nth_weekday(year, 11, 3, 4))  # Thanksgiving
    obs = _observed(date(year, 12, 25))
    if obs:
        out.add(obs)
    return out | {d for d in _EXTRA_CLOSURES if d.year == year}


def is_session(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    return d not in nyse_holidays(d.year) and d not in nyse_holidays(d.year + 1)


def next_session(d: date) -> date:
    n = d + timedelta(days=1)
    while not is_session(n):
        n += timedelta(days=1)
    return n


def sessions_between(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if is_session(d):
            out.append(d)
        d += timedelta(days=1)
    return out


# ------------------------------------------------------------------ window guard


def window_status(now: datetime) -> tuple[bool, date | None, str]:
    """(in window, release day T, message). T is the next NYSE session after today (ET)."""
    local = now.astimezone(ET)
    today = local.date()
    if not is_session(today):
        return False, None, f"{today} is not an NYSE session; no signal window"
    t = next_session(today)
    hm = (local.hour, local.minute)
    if not (WINDOW_START <= hm < WINDOW_END):
        return (
            False,
            t,
            f"outside the 15:00-15:50 ET window on T-1 (now {local:%Y-%m-%d %H:%M} ET); "
            "nothing written",
        )
    return True, t, f"in window; release day T = {t}"


# ------------------------------------------------------------------ small helpers


def code_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _clean(value: Any) -> Any:
    if isinstance(value, (np.floating, float)):
        v = float(value)
        return None if not np.isfinite(v) else v
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if value is pd.NaT:
        return None
    if isinstance(value, datetime):  # pd.Timestamp is a datetime
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:  # append only, earlier lines untouched
        for row in rows:
            fh.write(json.dumps({k: _clean(v) for k, v in row.items()}, sort_keys=False) + "\n")


# ----------------------------------------------------------------- Kalshi events


def list_open_events(client: Any, series: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cursor = ""
    while True:
        params: dict[str, Any] = {
            "series_ticker": series,
            "status": "open",
            "with_nested_markets": "true",
            "limit": 200,
        }
        if cursor:
            params["cursor"] = cursor
        body = client.get("events", params) or {}
        events.extend(body.get("events") or [])
        cursor = body.get("cursor") or ""
        if not cursor:
            return events


def event_release_date(event: dict[str, Any]) -> date | None:
    closes = sorted(
        m["close_time"]
        for m in event.get("markets") or []
        if m.get("strike_type") == "greater" and m.get("close_time")
    )
    return bk.release_date_et(closes[-1]) if closes else None


def events_for_release_day(client: Any, t: date) -> list[tuple[str, dict[str, Any]]]:
    found = []
    for series in SERIES:
        if client.get(f"series/{series}") is None:
            continue
        for event in list_open_events(client, series):
            if event_release_date(event) == t:
                found.append((series, event))
    return found


def fetch_event_candles(
    client: Any, series: str, event: dict[str, Any], end_ts: int, cutoff_ts: int
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Hourly candles per threshold market, never past ``end_ts`` (the signal instant)."""
    end_iso = datetime.fromtimestamp(end_ts, UTC).isoformat().replace("+00:00", "Z")
    rows: list[dict[str, Any]] = []
    metas = []
    for m in event.get("markets") or []:
        metas.append(fk.market_meta(m))
        if m.get("strike_type") != "greater" or m.get("floor_strike") is None:
            continue
        capped = {**m, "close_time": end_iso, "settlement_ts": None}
        candles, _ = fk.fetch_market_candles(client, series, capped, cutoff_ts)
        rows.extend(r for r in candles if r["end_period_ts"] <= end_ts)
    meta = {
        "event_ticker": event["event_ticker"],
        "title": event.get("title"),
        "sub_title": event.get("sub_title"),
        "markets": metas,
    }
    return (pd.DataFrame(rows) if rows else pd.DataFrame()), meta


# ------------------------------------------------------------------- U_rel logic


def history_frame(series: str, before: date, forward: Sequence[dict[str, Any]]) -> pd.DataFrame:
    """Prior events of a series: the builder's parquet plus earlier forward event rows."""
    cols = ["series", "release_date", "event_ticker", "U"]
    parts: list[pd.DataFrame] = []
    if RELEASE_UNCERTAINTY.exists():
        base = pd.read_parquet(RELEASE_UNCERTAINTY, columns=cols)
        parts.append(base[base["series"] == series])
    parts.append(
        pd.DataFrame(
            [
                {
                    "series": r["series"],
                    "release_date": r["release_date"],
                    "event_ticker": r["event_ticker"],
                    "U": r.get("U"),
                }
                for r in forward
                if r.get("record_type") == "event" and r.get("series") == series
            ],
            columns=cols,
        )
    )
    parts = [p for p in parts if not p.empty]
    hist = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)
    hist["release_date"] = pd.to_datetime(hist["release_date"])
    hist = hist[hist["release_date"] < pd.Timestamp(before)]
    hist = hist.drop_duplicates("event_ticker", keep="first")
    return hist[hist["U"].notna()]


def u_rel_for(series: str, release: date, event_ticker: str, u: float, hist: pd.DataFrame) -> dict:
    """U_rel of one new event against strictly earlier events only (builder's add_u_rel)."""
    new = pd.DataFrame(
        [
            {
                "series": series,
                "release_date": pd.Timestamp(release),
                "event_ticker": event_ticker,
                "U": u,
            }
        ]
    )
    frame = pd.concat([hist[hist["series"] == series], new], ignore_index=True)
    scored = bk.add_u_rel(frame)
    row = scored[scored["event_ticker"] == event_ticker].iloc[-1]
    return {
        "U_rel": None if pd.isna(row["U_rel"]) else float(row["U_rel"]),
        "n_prior_events": int(row["n_prior_events"]),
        "median_prior_U": None if pd.isna(row["median_prior_U"]) else float(row["median_prior_U"]),
    }


def build_signal_rows(
    t: date,
    events: Sequence[tuple[str, dict[str, Any], pd.DataFrame, dict[str, Any]]],
    forward: Sequence[dict[str, Any]],
    *,
    now: datetime,
    commit: str,
    trading_dates: Sequence[date],
) -> list[dict[str, Any]]:
    """Event rows plus the day row for release day ``t`` (nothing is written here)."""
    logged = now.astimezone(UTC).isoformat(timespec="seconds")
    event_rows: list[dict[str, Any]] = []
    for series, _event, candles, meta in events:
        row = bk.build_event_row(series, meta, candles, trading_dates)
        u = row.get("U")
        has_u = u is not None and pd.notna(u)
        rel = {"U_rel": None, "n_prior_events": None, "median_prior_U": None}
        if has_u:
            hist = history_frame(series, t, forward)
            rel = u_rel_for(series, t, meta["event_ticker"], float(u), hist)
        event_rows.append(
            {
                "record_type": "event",
                "logged_at_utc": logged,
                "release_date": t,
                "series": series,
                "event_ticker": meta["event_ticker"],
                "n_usable_strikes": int(row.get("n_usable_strikes") or 0),
                "pmf_mean": row.get("pmf_mean"),
                "U": u if has_u else None,
                "U_rel": rel["U_rel"],
                "n_prior_events": rel["n_prior_events"],
                "median_prior_U": rel["median_prior_U"],
                "excluded": bool(row.get("excluded")),
                "flags": row.get("flags", ""),
                "signal_end_utc": row.get("signal_end_utc"),
                "is_fomc": series in bk.FOMC_SERIES,
            }
        )
    values = [r["U_rel"] for r in event_rows if r["U_rel"] is not None]
    day_u = max(values) if values else None
    fomc_day = t in bk.FOMC_DECISION_DAYS or any(r["is_fomc"] for r in event_rows)
    hold_incl = day_u is not None and day_u > 1.0
    day_row = {
        "record_type": "day",
        "logged_at_utc": logged,
        "release_date": t,
        "series": ",".join(sorted({r["series"] for r in event_rows})),
        "event_ticker": None,
        "n_usable_strikes": min((r["n_usable_strikes"] for r in event_rows), default=0),
        "pmf_mean": None,
        "U": None,
        "U_rel": None,
        "day_U_rel": day_u,
        "fomc_day": fomc_day,
        "would_hold": bool(hold_incl and not fomc_day),
        "would_hold_incl_fomc": bool(hold_incl),
        "n_events": len(event_rows),
    }
    for r in event_rows:
        r["day_U_rel"] = day_u
        r["fomc_day"] = fomc_day
        r["would_hold"] = day_row["would_hold"]
        r["would_hold_incl_fomc"] = day_row["would_hold_incl_fomc"]
    out = event_rows + [day_row]
    for r in out:
        r["code_commit"] = commit
    return out


# ------------------------------------------------------------------ signal command


def run_signal(
    now: datetime,
    client: Any,
    out_dir: Path = SHADOW_DIR,
    *,
    commit: str | None = None,
    dry_run: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    ok, t, message = window_status(now)
    log(message)
    if not ok or t is None:
        return {"status": "outside_window", "wrote": 0, "message": message}
    path = out_dir / SIGNALS
    existing = read_jsonl(path)
    logged_events = {r["event_ticker"] for r in existing if r.get("record_type") == "event"}
    logged_days = {r["release_date"] for r in existing if r.get("record_type") == "day"}
    found = events_for_release_day(client, t)
    if not found:
        log(f"no Kalshi macro event released on {t}; nothing written")
        return {"status": "no_event", "release_date": t.isoformat(), "wrote": 0}
    todo = [(s, e) for s, e in found if e["event_ticker"] not in logged_events]
    if t.isoformat() in logged_days and not todo:
        log(f"release day {t} already logged; skipping")
        return {"status": "already_logged", "release_date": t.isoformat(), "wrote": 0}
    if t.isoformat() in logged_days:
        # the day line exists but an event was added later: never rewrite, so stop here
        log(f"day {t} already logged without {[e['event_ticker'] for _, e in todo]}; skipping")
        return {"status": "day_logged_partial", "release_date": t.isoformat(), "wrote": 0}
    prev = now.astimezone(ET).date()  # today is T-1
    end_ts = bk.signal_end_ts(prev)
    cutoff_ts = fk.fetch_cutoff(client)
    fetched = []
    for series, event in todo:  # all-or-nothing: any failure raises before a line is written
        candles, meta = fetch_event_candles(client, series, event, end_ts, cutoff_ts)
        fetched.append((series, event, candles, meta))
    trading_dates = sessions_between(t - timedelta(days=14), t + timedelta(days=7))
    rows = build_signal_rows(
        t,
        fetched,
        existing,
        now=now,
        commit=commit if commit is not None else code_commit(),
        trading_dates=trading_dates,
    )
    if not dry_run:
        append_jsonl(path, rows)
    day = rows[-1]
    log(
        f"{'dry-run, ' if dry_run else ''}{len(rows) - 1} event line(s) + 1 day line for {t}; "
        f"day_U_rel={day['day_U_rel']} would_hold={day['would_hold']}"
    )
    return {
        "status": "dry_run" if dry_run else "logged",
        "release_date": t.isoformat(),
        "wrote": 0 if dry_run else len(rows),
        "rows": [{k: _clean(v) for k, v in r.items()} for r in rows],
    }


# ------------------------------------------------------------------ realize command


def run_realize(
    prices: dict[str, pd.DataFrame],
    out_dir: Path = SHADOW_DIR,
    *,
    now: datetime | None = None,
    commit: str | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    signals = read_jsonl(out_dir / SIGNALS)
    days = sorted({r["release_date"] for r in signals if r.get("record_type") == "day"})
    done = {r["release_date"] for r in read_jsonl(out_dir / REALIZED)}
    rets = h1.return_table(
        {s: p for s, p in prices.items() if s in (*SHADOW_SYMBOLS, "BIL", "SPY")}
    )
    last = prices["SPY"].index.max()
    stamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds")
    sha = commit if commit is not None else code_commit()
    rows, skipped = [], []
    for day in days:
        ts = pd.Timestamp(day)
        if day in done:
            continue
        if ts > last or ts not in rets.index:
            skipped.append((day, "not yet in SIP daily"))
            continue
        loc = rets.index.get_loc(ts)
        row: dict[str, Any] = {
            "release_date": day,
            "prev_session": rets.index[loc - 1].date().isoformat() if loc > 0 else None,
            "logged_at_utc": stamp,
        }
        needed = []
        for sym in (*SHADOW_SYMBOLS, "BIL"):
            for kind in ("cc", "co"):
                value = rets.at[ts, f"{sym}_{kind}"]
                row[f"{sym}_R_{kind}"] = None if pd.isna(value) else float(value)
                needed.append(value)
        for sym in SHADOW_SYMBOLS:
            for kind in ("cc", "co"):
                value = rets.at[ts, f"{sym}_{kind}_ex"]
                row[f"{sym}_R_{kind}_ex"] = None if pd.isna(value) else float(value)
                needed.append(value)
        if any(pd.isna(v) for v in needed):
            skipped.append((day, "missing price or BIL for the interval"))
            continue
        row["code_commit"] = sha
        rows.append(row)
    append_jsonl(out_dir / REALIZED, rows)
    for day, why in skipped:
        log(f"{day}: not realized ({why})")
    log(f"realized {len(rows)} day(s)")
    return {"realized": len(rows), "skipped": skipped}


# ------------------------------------------------------------------ summary command


def summarize(out_dir: Path = SHADOW_DIR) -> dict[str, Any]:
    days = [r for r in read_jsonl(out_dir / SIGNALS) if r.get("record_type") == "day"]
    realized = {r["release_date"]: r for r in read_jsonl(out_dir / REALIZED)}
    valid = [d for d in days if d.get("day_U_rel") is not None]
    non_fomc = [d for d in valid if not d.get("fomc_day")]
    n = len(non_fomc)
    out: dict[str, Any] = {
        "label": LABEL,
        "days_logged": len(days),
        "days_with_valid_u_rel": len(valid),
        "fomc_days": len(valid) - n,
        "forward_non_fomc_release_days": n,
        "target_days": TARGET_DAYS,
        "days_still_needed": max(0, TARGET_DAYS - n),
        "realized_non_fomc_days": sum(1 for d in non_fomc if d["release_date"] in realized),
        "D_QQQ_R_cc_ex_bp": None,
        "n_hold": 0,
        "n_not_hold": 0,
    }
    hold = [
        realized[d["release_date"]]["QQQ_R_cc_ex"]
        for d in non_fomc
        if d["release_date"] in realized and d["would_hold"]
    ]
    rest = [
        realized[d["release_date"]]["QQQ_R_cc_ex"]
        for d in non_fomc
        if d["release_date"] in realized and not d["would_hold"]
    ]
    out["n_hold"], out["n_not_hold"] = len(hold), len(rest)
    if hold and rest:
        out["D_QQQ_R_cc_ex_bp"] = float((np.mean(hold) - np.mean(rest)) * 1e4)
    return out


def format_summary(s: dict[str, Any]) -> str:
    d = s["D_QQQ_R_cc_ex_bp"]
    d_text = "n/a (need realized days on both sides)" if d is None else f"{d:+.1f} bp"
    return "\n".join(
        [
            f"H1 forward shadow: {s['label']}",
            f"forward non-FOMC release days with U_rel: {s['forward_non_fomc_release_days']} "
            f"(FOMC days {s['fomc_days']}, logged {s['days_logged']})",
            f"realized non-FOMC days: {s['realized_non_fomc_days']} "
            f"(would_hold {s['n_hold']}, not {s['n_not_hold']})",
            f"D = mean(QQQ R_cc ex BIL | would_hold) - mean(| not): {d_text}",
            f"still needed to reach {s['target_days']} release days: {s['days_still_needed']}",
        ]
    )


# ----------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_sig = sub.add_parser("signal")
    p_sig.add_argument("--now", help="ISO UTC time override (tests / dry runs)")
    p_sig.add_argument("--dry-run", action="store_true", help="compute, print, write nothing")
    p_sig.add_argument("--out-dir", type=Path, default=SHADOW_DIR)
    p_real = sub.add_parser("realize")
    p_real.add_argument("--out-dir", type=Path, default=SHADOW_DIR)
    p_sum = sub.add_parser("summary")
    p_sum.add_argument("--out-dir", type=Path, default=SHADOW_DIR)
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    if args.cmd == "signal":
        now = (
            datetime.fromisoformat(args.now.replace("Z", "+00:00"))
            if args.now
            else datetime.now(UTC)
        )
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        result = run_signal(now, fk.KalshiClient(), args.out_dir, dry_run=args.dry_run)
        print(json.dumps({k: v for k, v in result.items() if k != "rows"}))
        return 0
    if args.cmd == "realize":
        run_realize(h1.load_prices(), args.out_dir)
        return 0
    print(format_summary(summarize(args.out_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
