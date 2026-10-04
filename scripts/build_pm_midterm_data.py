"""Build the daily probability tables for h20261004_pm_midterm_odds_leadlag (T-20261004-53).

Reads only public endpoints without keys: Polymarket Gamma and CLOB, Kalshi market data. No wallet,
login or order. Writes under ``data/research/prediction_markets/midterms/`` (never committed) and
replaces the measured parts of ``data-feasibility.json``. No strategy return is computed here.

Daily probability rule (frozen in hypotheses.md): the last price at or before 16:00 America/New_York
on each NYSE session, from hourly CLOB history (14-day windows, the API rejects longer ones) and
hourly Kalshi candlesticks.

Placebo-3 rule, fixed before any return exists: among Gamma events whose tags include ``sports`` or
``crypto`` and none of the political tags, take their markets by descending market volume; the first
whose Yes token is alive on at least 80 percent of the backtest-window sessions is the placebo
market (alive = a CLOB point exists at or before the session cut and the history has not ended).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, date, datetime
from datetime import time as dtime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.market_sessions import us_equity_session_dates  # noqa: E402

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
ET = "America/New_York"
ITER_ID = "h20261004_pm_midterm_odds_leadlag"
ITER_DIR = ROOT / "reports/research/iterations" / ITER_ID
OUT_DIR = ROOT / "data/research/prediction_markets/midterms"
CUT_TIME = dtime(16, 0)
WINDOW_DAYS = 14
FINER_FIDELITIES = (10, 1)
END_DATE = date(2026, 10, 2)
BURN_IN = 60
MIN_OBS = 120
MIN_ASSET_COVERAGE = 0.80
PLACEBO_COVERAGE = 0.80

POLY_HOUSE_R_TOKEN = "65139230827417363158752884968303867495725894165574887635816574090175320800482"
POLY_SENATE_R_TOKEN = (
    "51939490109676186832507970701169130490548061087912630009168726706475001411420"
)
POLY_START = datetime(2025, 7, 11, tzinfo=UTC)
KALSHI_SERIES = {
    "kalshi_house_r": ("CONTROLH", "CONTROLH-2026-R"),
    "kalshi_senate_r": ("CONTROLS", "CONTROLS-2026-R"),
}
KALSHI_START = datetime(2024, 11, 6, tzinfo=UTC)
KALSHI_WINDOW_DAYS = 40

CATEGORIES: dict[str, list[str]] = {
    "stock_etf": ["SPY", "QQQ", "IWM", "MAGS", "DIA", "XLF", "KRE", "XLI", "XLE", "XAR"],
    "bond": ["SHY", "IEI", "IEF", "TLH", "TLT", "GOVT", "TIP"],
    "bank": ["GS", "MS", "JPM", "C", "BAC", "WFC"],
    "dollar": ["UUP"],
    "connected": ["DJT", "PHUN", "TSLA"],
}
#: Paper Internet Appendix Table A.1 (snapshot in the intel folder): bonds short, all others long.
DIRECTION = {"stock_etf": 1, "bond": -1, "bank": 1, "dollar": 1, "connected": 1}
ASSETS = [t for tickers in CATEGORIES.values() for t in tickers]

POLITICAL_TAGS = {
    "politics",
    "geopolitics",
    "elections",
    "world-elections",
    "global-elections",
    "us-presidential-election",
    "economic-policy",
    "trump",
    "foreign-policy",
}
PLACEBO_TAGS = {"sports", "crypto"}


def _load_http_module() -> Any:
    path = ROOT / "scripts/collect_prediction_markets.py"
    spec = importlib.util.spec_from_file_location("collect_prediction_markets", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("collect_prediction_markets", module)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ sessions and cuts


def sessions_between(start: date, end: date) -> list[date]:
    return list(us_equity_session_dates(start, end))


def cut_epoch(day: date) -> int:
    """Epoch seconds of 16:00 America/New_York on ``day``."""
    wall = pd.Timestamp(datetime.combine(day, CUT_TIME)).tz_localize(ET)
    return int(wall.timestamp())


def windows(start_ts: int, end_ts: int, days: int = WINDOW_DAYS) -> list[tuple[int, int]]:
    step = days * 86400
    out = []
    t = start_ts
    while t < end_ts:
        out.append((t, min(t + step, end_ts)))
        t += step
    return out


# ------------------------------------------------------------------ fetching


def fetch_poly_history(
    http: Any, token: str, start_ts: int, end_ts: int
) -> list[tuple[int, float]]:
    """Hourly points over many 14-day windows; a finer fidelity only for an empty window."""
    seen: dict[int, float] = {}
    for lo, hi in windows(start_ts, end_ts):
        for fidelity in (60, *FINER_FIDELITIES):
            body = http.get(
                f"{CLOB_BASE}/prices-history",
                {"market": token, "startTs": lo, "endTs": hi, "fidelity": fidelity},
                allow_404=True,
            )
            hist = (body or {}).get("history") or []
            if hist:
                for h in hist:
                    seen[int(h["t"])] = float(h["p"])
                break
    return sorted(seen.items())


def fetch_kalshi_hourly(
    http: Any, series: str, ticker: str, start_ts: int, end_ts: int
) -> list[tuple[int, float]]:
    """Hourly candlestick closes (last trade price); empty candles carry nothing here."""
    seen: dict[int, float] = {}
    for lo, hi in windows(start_ts, end_ts, KALSHI_WINDOW_DAYS):
        body = http.get(
            f"{KALSHI_BASE}/series/{series}/markets/{ticker}/candlesticks",
            {"start_ts": lo, "end_ts": hi, "period_interval": 60},
            allow_404=True,
        )
        for c in (body or {}).get("candlesticks") or []:
            close = (c.get("price") or {}).get("close_dollars")
            if close is None:
                continue
            seen[int(c["end_period_ts"])] = float(close)
    return sorted(seen.items())


def daily_at_cut(points: list[tuple[int, float]], sessions: list[date]) -> pd.DataFrame:
    """Last point at or before 16:00 ET per session; sessions before the first point are absent."""
    rows = []
    idx = 0
    last: tuple[int, float] | None = None
    ordered = sorted(points)
    for day in sessions:
        cut = cut_epoch(day)
        while idx < len(ordered) and ordered[idx][0] <= cut:
            last = ordered[idx]
            idx += 1
        if last is None:
            continue
        rows.append(
            {
                "session": pd.Timestamp(day),
                "price": last[1],
                "point_ts": last[0],
                "age_hours": (cut - last[0]) / 3600.0,
            }
        )
    return pd.DataFrame(rows, columns=["session", "price", "point_ts", "age_hours"])


# ------------------------------------------------------------------ placebo selection


def _tags(event: dict[str, Any]) -> set[str]:
    return {
        str(t.get("slug") or "").lower() for t in (event.get("tags") or []) if isinstance(t, dict)
    }


def placebo_candidates(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Markets of sports or crypto events without political tags, by descending market volume."""
    rows = []
    for event in events:
        tags = _tags(event)
        if not (tags & PLACEBO_TAGS) or tags & POLITICAL_TAGS:
            continue
        for m in event.get("markets") or []:
            tokens = m.get("clobTokenIds")
            if isinstance(tokens, str):
                tokens = json.loads(tokens)
            if not tokens:
                continue
            try:
                volume = float(m.get("volumeNum") or m.get("volume") or 0.0)
            except (TypeError, ValueError):
                volume = 0.0
            rows.append(
                {
                    "event_id": event.get("id"),
                    "event_title": event.get("title"),
                    "market_id": m.get("id"),
                    "question": m.get("question"),
                    "token": tokens[0],
                    "start": m.get("startDate") or event.get("startDate"),
                    "end": m.get("closedTime") or m.get("endDate") or event.get("endDate"),
                    "volume": volume,
                    "tags": sorted(tags),
                }
            )
    return sorted(rows, key=lambda r: -r["volume"])


def _parse_ts(text: Any) -> int | None:
    if not text:
        return None
    try:
        return int(pd.Timestamp(str(text)).tz_convert("UTC").timestamp())
    except (ValueError, TypeError):
        try:
            return int(pd.Timestamp(str(text)).tz_localize("UTC").timestamp())
        except (ValueError, TypeError):
            return None


def listed_span_covers(cand: dict[str, Any], window: list[date], share: float = 0.7) -> bool:
    """Cheap prefilter on the Gamma start and end dates (looser than the 80 percent rule)."""
    lo, hi = _parse_ts(cand.get("start")), _parse_ts(cand.get("end"))
    if lo is None or hi is None or not window:
        return True  # unknown dates: let the CLOB history decide
    alive = sum(1 for d in window if lo <= cut_epoch(d) <= hi + 86400)
    return alive / len(window) >= share


def alive_coverage(points: list[tuple[int, float]], window: list[date]) -> float:
    """Share of window sessions on which the market has started and its history has not ended."""
    if not points or not window:
        return 0.0
    first, last = points[0][0], points[-1][0]
    alive = sum(1 for d in window if cut_epoch(d) >= first and cut_epoch(d) <= last + 86400)
    return alive / len(window)


def fetch_gamma_events(http: Any, closed: bool, pages: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for page in range(pages):
        body = http.get(
            f"{GAMMA_BASE}/events",
            {
                "order": "volume",
                "ascending": "false",
                "limit": 100,
                "offset": page * 100,
                "closed": "true" if closed else "false",
            },
        )
        if not isinstance(body, list):
            raise RuntimeError("unexpected Gamma response shape")
        events.extend(body)
        if len(body) < 100:
            break
    return events


def select_placebo(
    http: Any, window: list[date], events: list[dict[str, Any]], max_checked: int = 400
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """First candidate by volume whose Yes token is alive on >= 80 percent of the window."""
    log: list[dict[str, Any]] = []
    checked = 0
    for cand in placebo_candidates(events):
        if checked >= max_checked:
            break
        if not listed_span_covers(cand, window):
            continue
        checked += 1
        body = http.get(
            f"{CLOB_BASE}/prices-history",
            {"market": cand["token"], "interval": "max", "fidelity": 1440},
            allow_404=True,
        )
        hist = (body or {}).get("history") or []
        pts = sorted((int(h["t"]), float(h["p"])) for h in hist)
        cov = alive_coverage(pts, window)
        log.append({**cand, "alive_coverage": round(cov, 4), "n_points": len(pts)})
        if cov >= PLACEBO_COVERAGE:
            return cand, log
    return None, log


# ------------------------------------------------------------------ signal window and bars


def signal_start_index(n_sessions: int) -> int | None:
    """Index of the first return session: signal valid after 60 burn-in sessions, lagged one."""
    first = BURN_IN + 1
    return first if first < n_sessions else None


def load_bars(symbols: list[str], start: date, end: date) -> dict[str, pd.Series]:
    """Adjusted daily closes per symbol indexed by the Eastern session date (read-only)."""
    import duckdb

    quoted = ",".join(f"'{s}'" for s in sorted(symbols))
    con = duckdb.connect()
    try:
        con.execute("SET memory_limit='300MB'")
        df = con.execute(
            "SELECT symbol, timestamp, close FROM read_parquet('data/sip/daily/**/*.parquet') "
            f"WHERE symbol IN ({quoted}) AND timestamp >= TIMESTAMPTZ '{start} 00:00:00+00' "
            f"AND timestamp <= TIMESTAMPTZ '{end} 23:59:59+00' ORDER BY symbol, timestamp"
        ).fetchdf()
    finally:
        con.close()
    ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(ET)
    df["date"] = pd.to_datetime(ts.dt.date)
    return {s: g.set_index("date")["close"] for s, g in df.groupby("symbol")}


def asset_coverage(
    bars: dict[str, pd.Series], window: list[date]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Per-asset share of window sessions with a close, and the assets that pass 80 percent."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in window])
    report: dict[str, dict[str, Any]] = {}
    kept = []
    for ticker in ASSETS:
        s = bars.get(ticker)
        n = int(idx.isin(s.index).sum()) if s is not None else 0
        share = n / len(window) if window else 0.0
        ok = share >= MIN_ASSET_COVERAGE
        report[ticker] = {
            "sessions_with_bar": n,
            "window_sessions": len(window),
            "coverage": round(share, 4),
            "kept": ok,
        }
        if ok:
            kept.append(ticker)
    return report, kept


# ------------------------------------------------------------------ build


def build(out_dir: Path = OUT_DIR, *, log: Any = print) -> dict[str, Any]:
    module = _load_http_module()
    http = module.Http(budget_s=3000.0)
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions = sessions_between(POLY_START.date(), END_DATE)
    end_ts = cut_epoch(END_DATE)
    hourly: list[pd.DataFrame] = []
    daily: dict[str, pd.DataFrame] = {}

    def keep(name: str, pts: list[tuple[int, float]], sess: list[date]) -> None:
        hourly.append(
            pd.DataFrame({"series": name, "t": [p[0] for p in pts], "p": [p[1] for p in pts]})
        )
        daily[name] = daily_at_cut(pts, sess)
        log(f"{name}: {len(pts)} points, {len(daily[name])} daily observations")

    keep(
        "polymarket_house_r",
        fetch_poly_history(http, POLY_HOUSE_R_TOKEN, int(POLY_START.timestamp()), end_ts),
        sessions,
    )
    keep(
        "polymarket_senate_r",
        fetch_poly_history(http, POLY_SENATE_R_TOKEN, int(POLY_START.timestamp()), end_ts),
        sessions,
    )
    kalshi_sessions = sessions_between(KALSHI_START.date(), END_DATE)
    for name, (series, ticker) in KALSHI_SERIES.items():
        keep(
            name,
            fetch_kalshi_hourly(http, series, ticker, int(KALSHI_START.timestamp()), end_ts),
            kalshi_sessions,
        )

    both = sorted(
        set(daily["polymarket_house_r"]["session"]) | set(daily["polymarket_senate_r"]["session"])
    )
    start_idx = signal_start_index(len(both))
    window = [d.date() for d in both[start_idx:]] if start_idx is not None else []
    log(
        f"backtest window sessions: {len(window)} "
        f"({window[0] if window else None} .. {window[-1] if window else None})"
    )

    events = fetch_gamma_events(http, False, 8) + fetch_gamma_events(http, True, 8)
    placebo, placebo_log = select_placebo(http, window, events)
    placebo_info: dict[str, Any] = {"selected": None, "checked": len(placebo_log)}
    if placebo is not None:
        pts = fetch_poly_history(http, placebo["token"], int(POLY_START.timestamp()), end_ts)
        keep("placebo_market", pts, sessions)
        cov = alive_coverage(pts, window)
        obs_in_window = int(
            daily["placebo_market"]["session"].isin([pd.Timestamp(d) for d in window]).sum()
        )
        placebo_info["selected"] = {
            k: placebo[k]
            for k in ("event_id", "event_title", "market_id", "question", "token", "volume", "tags")
        } | {"alive_coverage": round(cov, 4), "daily_observations_in_window": obs_in_window}
    placebo_info["candidate_log_top10"] = placebo_log[:10]

    pd.concat(hourly, ignore_index=True).to_parquet(out_dir / "hourly.parquet", index=False)
    pd.concat([d.assign(series=n) for n, d in daily.items()], ignore_index=True).to_parquet(
        out_dir / "daily.parquet", index=False
    )

    bars = load_bars(ASSETS, sessions[0], END_DATE)
    cov_report, kept = asset_coverage(bars, window)
    result = {
        "built_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "markets": {
            name: {
                "daily_observations": int(len(d)),
                "first_session": str(d["session"].iloc[0].date()) if len(d) else None,
                "last_session": str(d["session"].iloc[-1].date()) if len(d) else None,
                "max_age_hours": round(float(d["age_hours"].max()), 2) if len(d) else None,
            }
            for name, d in daily.items()
        },
        "polymarket_signal_rule": polymarket_rule(daily),
        "backtest_window": {
            "sessions": len(window),
            "first": str(window[0]) if window else None,
            "last": str(window[-1]) if window else None,
        },
        "placebo_3": placebo_info,
        "assets": {
            "tickers_tested": len(ASSETS),
            "kept": kept,
            "dropped": [t for t in ASSETS if t not in kept],
            "coverage": cov_report,
        },
        "out_dir": str(out_dir.relative_to(ROOT)),
    }
    return result


def polymarket_rule(daily: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Frozen fallback: a market with fewer than 120 observations before 2026-10-02 is dropped."""
    obs = {k: int(len(daily[k])) for k in ("polymarket_house_r", "polymarket_senate_r")}
    used = [k for k, v in obs.items() if v >= MIN_OBS]
    return {
        "observations": obs,
        "min_required": MIN_OBS,
        "markets_used": used,
        "fallback_applied": len(used) < 2,
    }


def merge_feasibility(result: dict[str, Any]) -> None:
    path = ITER_DIR / "data-feasibility.json"
    payload = json.loads(path.read_text())
    payload["data_build"] = result
    payload["generated_at"] = result["built_at_utc"]
    payload["notes"] = (
        str(payload.get("notes", "")).split(" PHASE 2")[0]
        + " PHASE 2 (measured), written by scripts/build_pm_midterm_data.py before any strategy"
        " return was computed."
    )
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument(
        "--no-feasibility", action="store_true", help="do not rewrite data-feasibility.json"
    )
    args = ap.parse_args(argv)
    result = build(args.out_dir)
    if not args.no_feasibility:
        merge_feasibility(result)
    print(json.dumps({k: v for k, v in result.items() if k != "placebo_3"}, indent=1)[:3000])
    print(json.dumps(result["placebo_3"].get("selected"), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
