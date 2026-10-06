"""P6 stage 0 (T-20261005-33): store one Alpaca option-chain snapshot per trading day.

Read-only.  Only data-API GETs, ``GET /v2/calendar`` and (``--check-accounts``) ``GET /v2/account``
are issued; no order endpoint is touched.  Credentials stay inside the request session and are
never printed, logged or written.

What one run stores under ``data/options/`` (zstd parquet; ``date=D`` is the ET trade date):

* ``chains/date=D/<UNDERLYING>.parquet``  SPY/QQQ/IWM + 20 most liquid stocks: every expiry within
  60 days, strikes within +-20% of the underlying price, calls and puts.
* ``stock_chains/date=D/part.parquet``    ~200 stocks: the nearest monthly expiry with >= 20 days to
  go and the next monthly expiry, strikes within +-25%, calls and puts.
* ``iv_points/date=D/part.parquet``       derived: per underlying and expiry the ATM call/put IV,
  25-delta call/put IV and a 30-day interpolated ATM IV.
* ``vix_term/vix_term.parquet``           VIX / VIX3M / VIX9D daily closes (Cboe CSV), merged.
* ``universe/<YYYY-MM>.json``             the monthly stock list (20-day dollar volume).
* every ``date=D`` partition holds ``_manifest.json`` (run kind, times, row counts, request and 429
  counts, universe file).

Run kinds: ``scheduled`` (cron; only inside 15:30-15:55 ET on a trading day and only if no scheduled
run stored that day) and ``manual`` (``--force-now``: skips the time window, still needs a trading
day, never replaces a scheduled day).  A scheduled run replaces a manual day atomically.

    scripts/run_capped.sh --mem 600M -- uv run python scripts/record_option_chains.py [--force-now]
    uv run python scripts/record_option_chains.py --check-accounts
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sys
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from io import StringIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NY = ZoneInfo("America/New_York")
DATA_ROOT_URL = "https://data.alpaca.markets"
OPTIONS_DIR = ROOT / "data" / "options"
FEED = "indicative"
INDEX_SYMBOLS = ("SPY", "QQQ", "IWM")
N_TOP_STOCKS = 20
N_STOCK_CHAINS = 200
N_UNIVERSE_CANDIDATES = 240  # ranked list kept so names without options can be skipped
CHAIN_MAX_DTE = 60
CHAIN_STRIKE_PCT = 0.20
STOCK_CHAIN_STRIKE_PCT = 0.25
STOCK_CHAIN_MIN_DTE = 20
WINDOW_START = dtime(15, 30)
WINDOW_END = dtime(15, 55)
MAX_REQUESTS_PER_MINUTE = 150
PAGE_LIMIT = 1000
MAX_PAGES = 200
SIZE_LIMIT_MB = 50
CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{index}_History.csv"
VIX_INDICES = {"VIX": "vix", "VIX3M": "vix3m", "VIX9D": "vix9d"}
OCC_RE = re.compile(r"^(?P<root>.{1,6}?)(?P<yymmdd>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")

ROW_COLUMNS = [
    "snapshot_ts_utc",
    "trade_date",
    "underlying",
    "underlying_price",
    "underlying_price_ts",
    "contract",
    "root",
    "expiration",
    "strike",
    "type",
    "bid",
    "ask",
    "bid_size",
    "ask_size",
    "bid_exch",
    "ask_exch",
    "quote_ts",
    "last_price",
    "last_size",
    "last_trade_ts",
    "day_volume",
    "iv",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "feed",
    "expiry_role",
]


class RateLimitedClient:
    """Paced (<= 150 requests/minute) GET client with exponential 429 back-off.

    Headers are held only by the ``requests`` session and are never logged.
    """

    def __init__(
        self,
        headers: dict[str, str],
        *,
        max_per_minute: int = MAX_REQUESTS_PER_MINUTE,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        import requests

        self._session = requests.Session()
        self._session.headers.update(headers)
        self._min_gap = 60.0 / max_per_minute
        self._sleep = sleep
        self._clock = clock
        self._last = -1e9
        self.requests = 0
        self.n_429 = 0
        self.errors: list[dict[str, Any]] = []

    def get_json(self, url: str, params: dict | None = None, max_retries: int = 7) -> Any | None:
        for attempt in range(max_retries):
            wait = self._min_gap - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = self._clock()
            self.requests += 1
            try:
                resp = self._session.get(url, params=params, timeout=30)
            except Exception as exc:  # noqa: BLE001 - network error: back off and retry
                self.errors.append({"url": url.split("?")[0], "error": type(exc).__name__})
                self._sleep(min(2**attempt, 30))
                continue
            if resp.status_code == 429:
                self.n_429 += 1
                retry_after = resp.headers.get("Retry-After")
                self._sleep(float(retry_after) if retry_after else min(2**attempt, 60))
                continue
            if resp.status_code != 200:
                self.errors.append({"url": url.split("?")[0], "status": resp.status_code})
                return None
            try:
                return resp.json()
            except ValueError:
                self.errors.append({"url": url.split("?")[0], "error": "bad_json"})
                return None
        return None


def build_client() -> RateLimitedClient:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=ROOT / ".env")
    from open_composer.config import alpaca_api_key_id, alpaca_api_secret_key

    key_id, secret = alpaca_api_key_id(), alpaca_api_secret_key()
    if not key_id or not secret:
        raise SystemExit("ALPACA_API_KEY_ID/ALPACA_API_SECRET_KEY not set (check .env)")
    return RateLimitedClient({"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret})


def trading_root() -> str:
    from open_composer.config import alpaca_api_base_url

    base = alpaca_api_base_url().rstrip("/")
    return base if base.endswith("/v2") else base + "/v2"


# --------------------------------------------------------------------------
# Time and calendar logic
# --------------------------------------------------------------------------


def in_snapshot_window(now_utc: datetime) -> bool:
    """True inside 15:30-15:55 America/New_York (DST handled by zoneinfo)."""
    local = now_utc.astimezone(NY)
    return WINDOW_START <= local.time() <= WINDOW_END


def should_run(
    now_utc: datetime,
    *,
    trading_days: set[date],
    force_now: bool,
    existing_run_kind: str | None,
) -> tuple[bool, str]:
    """Decide whether this invocation stores a snapshot; returns (run, reason)."""
    today = now_utc.astimezone(NY).date()
    if today not in trading_days:
        return False, "not_a_trading_day"
    if not force_now and not in_snapshot_window(now_utc):
        return False, "outside_15:30-15:55_ET_window"
    if force_now:
        if existing_run_kind == "scheduled":
            return False, "scheduled_data_exists_manual_never_overwrites"
        return True, "manual_force_now"
    if existing_run_kind == "scheduled":
        return False, "scheduled_snapshot_already_stored"
    return True, "scheduled_replaces_manual" if existing_run_kind == "manual" else "scheduled"


def third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    first_friday = first + timedelta(days=(4 - first.weekday()) % 7)
    return first_friday + timedelta(days=14)


def monthly_expiry(year: int, month: int, trading_days: set[date]) -> date:
    """Third-Friday expiry, rolled back to the previous trading day on a holiday."""
    day = third_friday(year, month)
    for _ in range(5):
        if day in trading_days:
            return day
        day -= timedelta(days=1)
    return third_friday(year, month)


def select_stock_expiries(
    today: date, trading_days: set[date], min_dte: int = STOCK_CHAIN_MIN_DTE
) -> tuple[date, date]:
    """Nearest monthly expiry with >= ``min_dte`` days to go, and the next monthly expiry."""
    year, month = today.year, today.month
    found: list[date] = []
    for _ in range(8):
        expiry = monthly_expiry(year, month, trading_days)
        if (expiry - today).days >= min_dte:
            found.append(expiry)
            if len(found) == 2:
                break
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return found[0], found[1]


def strike_bounds(price: float, pct: float) -> tuple[float, float]:
    return round(price * (1 - pct), 2), round(price * (1 + pct), 2)


def load_trading_days(client: RateLimitedClient, start: date, end: date) -> set[date]:
    body = client.get_json(
        trading_root() + "/calendar", {"start": start.isoformat(), "end": end.isoformat()}
    )
    if not body:
        raise SystemExit("trading calendar unavailable")
    return {date.fromisoformat(item["date"]) for item in body}


# --------------------------------------------------------------------------
# Universe (monthly, from local SIP daily bars)
# --------------------------------------------------------------------------


def rank_universe(
    daily: pd.DataFrame, eligible: set[str], window: int = 20, min_days: int = 15
) -> list[str]:
    """Rank eligible symbols by mean dollar volume over their last ``window`` sessions."""
    frame = daily[daily["symbol"].isin(eligible)].copy()
    frame["date"] = pd.to_datetime(frame["timestamp"], utc=True).dt.date
    frame = frame.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "date"], keep="last")
    frame = frame.groupby("symbol").tail(window)
    frame["dollar_volume"] = frame["close"] * frame["volume"]
    grouped = frame.groupby("symbol")["dollar_volume"].agg(["mean", "count"])
    grouped = grouped[grouped["count"] >= min_days].sort_values("mean", ascending=False)
    return [str(s) for s in grouped.index]


def eligible_stocks() -> set[str]:
    meta = pd.read_parquet(ROOT / "data" / "features" / "universe" / "_asset_metadata.parquet")
    keep = (meta["status"] == "active") & meta["tradable"] & ~meta["is_probable_fund_or_etf"]
    symbols = set(meta.loc[keep, "symbol"].astype(str))
    return {s for s in symbols if re.fullmatch(r"[A-Z]{1,5}", s)}  # no classes/warrants/units


def read_recent_daily(days_back: int = 45) -> tuple[pd.DataFrame, date]:
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    root = ROOT / "data" / "sip" / "daily"
    year_dir = sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit())[-1]
    frames = []
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days_back)
    for shard in sorted(year_dir.glob("*.parquet")):
        table = pq.read_table(shard, columns=["symbol", "timestamp", "close", "volume"])
        table = table.filter(pc.greater_equal(table["timestamp"], pd.Timestamp(cutoff)))
        if table.num_rows:
            frames.append(table.to_pandas())
    daily = pd.concat(frames, ignore_index=True)
    last = pd.to_datetime(daily["timestamp"], utc=True).max().date()
    return daily, last


def ensure_universe(trade_date: date, directory: Path = OPTIONS_DIR / "universe") -> dict:
    path = directory / f"{trade_date:%Y-%m}.json"
    if path.is_file():
        return json.loads(path.read_text())
    daily, last = read_recent_daily()
    ranked = rank_universe(daily, eligible_stocks())[:N_UNIVERSE_CANDIDATES]
    payload = {
        "month": f"{trade_date:%Y-%m}",
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "daily_last_date": last.isoformat(),
        "method": "mean(close*volume) over the last 20 sessions of data/sip/daily, "
        "stocks only (is_probable_fund_or_etf=False, tradable, active, 1-5 letters)",
        "index_symbols": list(INDEX_SYMBOLS),
        "top_stocks": ranked[:N_TOP_STOCKS],
        "stock_chain_candidates": ranked,
        "stock_chain_target": N_STOCK_CHAINS,
    }
    directory.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1))
    os.replace(tmp, path)
    return payload


# --------------------------------------------------------------------------
# Alpaca fetch and parsing
# --------------------------------------------------------------------------


def underlying_prices(
    client: RateLimitedClient, symbols: list[str]
) -> dict[str, tuple[float, str]]:
    """Latest IEX trade price per symbol (the free plan has no recent SIP)."""
    body = client.get_json(
        DATA_ROOT_URL + "/v2/stocks/snapshots", {"symbols": ",".join(symbols), "feed": "iex"}
    )
    out: dict[str, tuple[float, str]] = {}
    for symbol, snap in (body or {}).items():
        trade = (snap or {}).get("latestTrade") or {}
        if trade.get("p"):
            out[symbol] = (float(trade["p"]), str(trade.get("t", "")))
        else:
            for key in ("minuteBar", "dailyBar", "prevDailyBar"):
                bar = (snap or {}).get(key) or {}
                if bar.get("c"):
                    out[symbol] = (float(bar["c"]), str(bar.get("t", "")))
                    break
    return out


def parse_snapshot_rows(
    snapshots: dict[str, dict],
    *,
    underlying: str,
    price: float,
    price_ts: str,
    snapshot_ts: str,
    trade_date: date,
    expiry_role: str | None = None,
) -> list[dict]:
    rows = []
    for contract, snap in snapshots.items():
        match = OCC_RE.match(contract)
        if not match:
            continue
        yymmdd = match["yymmdd"]
        expiration = date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:]))
        quote = snap.get("latestQuote") or {}
        trade = snap.get("latestTrade") or {}
        greeks = snap.get("greeks") or {}
        daily_bar = snap.get("dailyBar") or {}
        rows.append(
            {
                "snapshot_ts_utc": snapshot_ts,
                "trade_date": trade_date.isoformat(),
                "underlying": underlying,
                "underlying_price": price,
                "underlying_price_ts": price_ts,
                "contract": contract,
                "root": match["root"],
                "expiration": expiration.isoformat(),
                "strike": int(match["strike"]) / 1000.0,
                "type": "call" if match["cp"] == "C" else "put",
                "bid": quote.get("bp"),
                "ask": quote.get("ap"),
                "bid_size": quote.get("bs"),
                "ask_size": quote.get("as"),
                "bid_exch": quote.get("bx"),
                "ask_exch": quote.get("ax"),
                "quote_ts": quote.get("t"),
                "last_price": trade.get("p"),
                "last_size": trade.get("s"),
                "last_trade_ts": trade.get("t"),
                "day_volume": daily_bar.get("v"),
                "iv": snap.get("impliedVolatility"),
                "delta": greeks.get("delta"),
                "gamma": greeks.get("gamma"),
                "theta": greeks.get("theta"),
                "vega": greeks.get("vega"),
                "rho": greeks.get("rho"),
                "feed": FEED,
                "expiry_role": expiry_role,
            }
        )
    return rows


FRONT_MIN_DTE = 7
FRONT_MAX_DTE = 30  # exclusive: the front expiry must be < 30 days out


def front_expiry_needed(m1_expiry: date, trade_date: date) -> bool:
    """A front expiry is only fetched when m1 is >= 30 days out (else m1 + m2 bracket 30 days)."""
    return (m1_expiry - trade_date).days >= FRONT_MAX_DTE


def select_front_rows(rows: list[dict], trade_date: date) -> list[dict]:
    """Rows of the expiry with the largest DTE in [7, 30); empty if none exists."""
    eligible = [
        r
        for r in rows
        if FRONT_MIN_DTE <= (date.fromisoformat(r["expiration"]) - trade_date).days < FRONT_MAX_DTE
    ]
    if not eligible:
        return []
    chosen = max(r["expiration"] for r in eligible)
    return [dict(r, expiry_role="front") for r in eligible if r["expiration"] == chosen]


def fetch_chain(
    client: RateLimitedClient,
    underlying: str,
    *,
    price: float,
    price_ts: str,
    trade_date: date,
    strike_pct: float,
    expiration: date | None = None,
    expiration_lte: date | None = None,
    expiration_gte: date | None = None,
    expiry_role: str | None = None,
) -> list[dict]:
    lo, hi = strike_bounds(price, strike_pct)
    params: dict[str, Any] = {
        "feed": FEED,
        "limit": PAGE_LIMIT,
        "strike_price_gte": lo,
        "strike_price_lte": hi,
    }
    if expiration:
        params["expiration_date"] = expiration.isoformat()
    if expiration_gte:
        params["expiration_date_gte"] = expiration_gte.isoformat()
    if expiration_lte:
        params["expiration_date_lte"] = expiration_lte.isoformat()
    rows: list[dict] = []
    url = f"{DATA_ROOT_URL}/v1beta1/options/snapshots/{underlying}"
    for _ in range(MAX_PAGES):
        body = client.get_json(url, params)
        if not body:
            break
        stamp = datetime.now(UTC).isoformat(timespec="milliseconds")
        rows.extend(
            parse_snapshot_rows(
                body.get("snapshots") or {},
                underlying=underlying,
                price=price,
                price_ts=price_ts,
                snapshot_ts=stamp,
                trade_date=trade_date,
                expiry_role=expiry_role,
            )
        )
        token = body.get("next_page_token")
        if not token:
            break
        params["page_token"] = token
    return rows


# --------------------------------------------------------------------------
# Derived IV points
# --------------------------------------------------------------------------


def _nearest_delta_iv(side: pd.DataFrame, target: float, tol: float = 0.10):
    side = side.dropna(subset=["delta", "iv"])
    if side.empty:
        return float("nan"), float("nan")
    gap = (side["delta"].abs() - target).abs()
    idx = gap.idxmin()
    if gap.loc[idx] > tol:
        return float("nan"), float("nan")
    return float(side.loc[idx, "iv"]), float(side.loc[idx, "strike"])


def interpolate_iv_30d(
    points: list[tuple[float, float]], target_days: float = 30.0
) -> tuple[float, str]:
    """ATM IV at ``target_days``: linear in total variance between the bracketing expiries.

    ``points`` are (dte, atm_iv).  Returns (iv, method): ``interp`` when 30 days is bracketed,
    ``nearest_flat`` (IV of the nearest expiry, no extrapolation of the slope) when it is not,
    ``none`` without any usable ATM IV.
    """
    pts = sorted((d, v) for d, v in points if d > 0 and v is not None and math.isfinite(v))
    for (d0, v0), (d1, v1) in zip(pts, pts[1:], strict=False):
        if d0 <= target_days <= d1:
            w0, w1 = v0 * v0 * d0, v1 * v1 * d1
            w = w0 + (w1 - w0) * (target_days - d0) / (d1 - d0)
            return math.sqrt(max(w, 0.0) / target_days), "interp"
    if pts:
        return min(pts, key=lambda p: abs(p[0] - target_days))[1], "nearest_flat"
    return float("nan"), "none"


def derive_iv_points(chain: pd.DataFrame, source: str) -> pd.DataFrame:
    """One row per (underlying, expiry); ATM = nearest strike that has both a call and a put."""
    if chain.empty:
        return pd.DataFrame()
    out = []
    for underlying, grp in chain.groupby("underlying", sort=False):
        price = float(grp["underlying_price"].iloc[0])
        trade_date = date.fromisoformat(str(grp["trade_date"].iloc[0]))
        per_expiry: dict[str, dict] = {}
        for expiration, exp_grp in grp.groupby("expiration", sort=True):
            dte = (date.fromisoformat(str(expiration)) - trade_date).days
            calls = exp_grp[exp_grp["type"] == "call"]
            puts = exp_grp[exp_grp["type"] == "put"]
            both = sorted(set(calls["strike"]) & set(puts["strike"]), key=lambda k: abs(k - price))
            atm_strike = both[0] if both else float("nan")
            atm_call = atm_put = float("nan")
            if both:
                c = calls.loc[calls["strike"] == atm_strike, "iv"].dropna()
                p = puts.loc[puts["strike"] == atm_strike, "iv"].dropna()
                atm_call = float(c.iloc[0]) if len(c) else float("nan")
                atm_put = float(p.iloc[0]) if len(p) else float("nan")
            c25_iv, c25_k = _nearest_delta_iv(calls, 0.25)
            p25_iv, p25_k = _nearest_delta_iv(puts, 0.25)
            atm_iv = (
                (atm_call + atm_put) / 2
                if math.isfinite(atm_call) and math.isfinite(atm_put)
                else float("nan")
            )
            per_expiry[str(expiration)] = {
                "snapshot_ts_utc": exp_grp["snapshot_ts_utc"].max(),
                "trade_date": trade_date.isoformat(),
                "underlying": underlying,
                "underlying_price": price,
                "expiration": str(expiration),
                "dte": dte,
                "source": source,
                "expiry_role": exp_grp["expiry_role"].iloc[0] if "expiry_role" in exp_grp else None,
                "n_contracts": len(exp_grp),
                "atm_strike": atm_strike,
                "atm_call_iv": atm_call,
                "atm_put_iv": atm_put,
                "atm_iv": atm_iv,
                "call25_iv": c25_iv,
                "call25_strike": c25_k,
                "put25_iv": p25_iv,
                "put25_strike": p25_k,
            }
        iv30, method = interpolate_iv_30d([(r["dte"], r["atm_iv"]) for r in per_expiry.values()])
        for rec in per_expiry.values():
            rec["atm_iv_30d"] = iv30
            rec["atm_iv_30d_method"] = method
            out.append(rec)
    return pd.DataFrame(out)


# --------------------------------------------------------------------------
# VIX term structure (Cboe public CSV)
# --------------------------------------------------------------------------


def parse_cboe_csv(text: str, column: str) -> pd.DataFrame:
    frame = pd.read_csv(StringIO(text))
    frame.columns = [c.strip().upper() for c in frame.columns]
    frame["date"] = pd.to_datetime(frame["DATE"], format="%m/%d/%Y").dt.date.astype(str)
    return frame[["date", "CLOSE"]].rename(columns={"CLOSE": column})


def merge_vix_term(
    existing: pd.DataFrame | None, fresh: dict[str, pd.DataFrame], before: date, fetched: str
) -> pd.DataFrame:
    """Append dates (< ``before``) that are not stored yet; stored rows are never rewritten."""
    wide: pd.DataFrame | None = None
    for frame in fresh.values():
        wide = frame if wide is None else wide.merge(frame, on="date", how="outer")
    if wide is None:
        return existing if existing is not None else pd.DataFrame()
    wide = wide[wide["date"] < before.isoformat()].copy()
    wide["fetched_utc"] = fetched
    if existing is not None and len(existing):
        wide = wide[~wide["date"].isin(set(existing["date"]))]
        wide = pd.concat([existing, wide], ignore_index=True)
    return wide.sort_values("date").reset_index(drop=True)


def update_vix_term(path: Path, before: date) -> int:
    import requests

    fresh = {}
    for index, column in VIX_INDICES.items():
        resp = requests.get(
            CBOE_URL.format(index=index), timeout=60, headers={"User-Agent": "Mozilla/5.0"}
        )
        resp.raise_for_status()
        fresh[column] = parse_cboe_csv(resp.text, column)
    existing = pd.read_parquet(path) if path.is_file() else None
    fetched = datetime.now(UTC).isoformat(timespec="seconds")
    merged = merge_vix_term(existing, fresh, before, fetched)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    merged.to_parquet(tmp, index=False, compression="zstd")
    os.replace(tmp, path)
    return len(merged)


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------


def to_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=ROW_COLUMNS)


def read_manifest(root: Path, trade_date: date) -> dict | None:
    path = root / "chains" / f"date={trade_date.isoformat()}" / "_manifest.json"
    return json.loads(path.read_text()) if path.is_file() else None


def publish_day(root: Path, trade_date: date, staging: Path, manifest: dict) -> None:
    """Atomically move ``staging/<kind>`` into ``root/<kind>/date=D`` (old day set aside first)."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    for kind in ("chains", "stock_chains", "iv_points"):
        src = staging / kind
        if not src.is_dir():
            continue
        (src / "_manifest.json").write_text(json.dumps({**manifest, "kind": kind}, indent=1))
        final = root / kind / f"date={trade_date.isoformat()}"
        final.parent.mkdir(parents=True, exist_ok=True)
        old = None
        if final.exists():
            old = final.with_name(f"_replaced_{final.name}_{stamp}")
            os.rename(final, old)
        os.rename(src, final)
        if old is not None:
            shutil.rmtree(old, ignore_errors=True)


def dir_size_mb(paths: list[Path]) -> float:
    total = 0
    for base in paths:
        for f in base.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    return round(total / 1e6, 3)


# --------------------------------------------------------------------------
# One run
# --------------------------------------------------------------------------


def run_snapshot(
    client: RateLimitedClient,
    *,
    root: Path,
    trade_date: date,
    trading_days: set[date],
    run_kind: str,
    universe: dict,
    stock_strike_pct: float = STOCK_CHAIN_STRIKE_PCT,
    log: Callable[[str], None] = print,
) -> dict:
    started = datetime.now(UTC)
    staging = root / f".staging_{trade_date.isoformat()}_{started:%H%M%S}"
    (staging / "chains").mkdir(parents=True)
    (staging / "stock_chains").mkdir(parents=True)
    (staging / "iv_points").mkdir(parents=True)
    counts = {"chains": 0, "stock_chains": 0, "iv_points": 0}
    empty: list[str] = []
    iv_frames: list[pd.DataFrame] = []

    # 1. index + top-20 stock chains: all expiries <= 60 days, +-20%
    chain_symbols = list(INDEX_SYMBOLS) + [
        s for s in universe["top_stocks"] if s not in INDEX_SYMBOLS
    ]
    for i in range(0, len(chain_symbols), 10):
        chunk = chain_symbols[i : i + 10]
        prices = underlying_prices(client, chunk)
        for symbol in chunk:
            if symbol not in prices:
                empty.append(f"{symbol}:no_price")
                continue
            price, price_ts = prices[symbol]
            rows = fetch_chain(
                client,
                symbol,
                price=price,
                price_ts=price_ts,
                trade_date=trade_date,
                strike_pct=CHAIN_STRIKE_PCT,
                expiration_gte=trade_date,
                expiration_lte=trade_date + timedelta(days=CHAIN_MAX_DTE),
            )
            if not rows:
                empty.append(f"{symbol}:no_options")
                continue
            frame = to_frame(rows)
            frame.to_parquet(
                staging / "chains" / f"{symbol}.parquet", index=False, compression="zstd"
            )
            counts["chains"] += len(frame)
            iv_frames.append(derive_iv_points(frame, "chains"))
            log(f"chains {symbol}: {len(frame)} rows")

    # 2. ~200 stocks, two monthly expiries, +-25%
    e1, e2 = select_stock_expiries(trade_date, trading_days)
    need_front = front_expiry_needed(e1, trade_date)
    front_found = 0
    front_missing: list[str] = []
    stock_rows: list[dict] = []
    done = 0
    candidates = universe["stock_chain_candidates"]
    for i in range(0, len(candidates), 10):
        if done >= universe["stock_chain_target"]:
            break
        chunk = candidates[i : i + 10]
        prices = underlying_prices(client, chunk)
        for symbol in chunk:
            if done >= universe["stock_chain_target"]:
                break
            if symbol not in prices:
                empty.append(f"{symbol}:no_price")
                continue
            price, price_ts = prices[symbol]
            symbol_rows: list[dict] = []
            for expiry, role in ((e1, "m1"), (e2, "m2")):
                symbol_rows += fetch_chain(
                    client,
                    symbol,
                    price=price,
                    price_ts=price_ts,
                    trade_date=trade_date,
                    strike_pct=stock_strike_pct,
                    expiration=expiry,
                    expiry_role=role,
                )
            if not symbol_rows:
                empty.append(f"{symbol}:no_options")
                continue
            if need_front:
                front = select_front_rows(
                    fetch_chain(
                        client,
                        symbol,
                        price=price,
                        price_ts=price_ts,
                        trade_date=trade_date,
                        strike_pct=stock_strike_pct,
                        expiration_gte=trade_date + timedelta(days=FRONT_MIN_DTE),
                        expiration_lte=trade_date + timedelta(days=FRONT_MAX_DTE - 1),
                    ),
                    trade_date,
                )
                if front:
                    symbol_rows += front
                    front_found += 1
                else:
                    front_missing.append(symbol)
            stock_rows += symbol_rows
            done += 1
        log(f"stock_chains: {done} symbols, {len(stock_rows)} rows")
    stock_frame = to_frame(stock_rows)
    del stock_rows
    if len(stock_frame):
        stock_frame.to_parquet(
            staging / "stock_chains" / "part.parquet", index=False, compression="zstd"
        )
        iv_frames.append(derive_iv_points(stock_frame, "stock_chains"))
    counts["stock_chains"] = len(stock_frame)

    iv_frames = [f for f in iv_frames if len(f)]
    if iv_frames:
        iv = pd.concat(iv_frames, ignore_index=True)
        iv.to_parquet(staging / "iv_points" / "part.parquet", index=False, compression="zstd")
        counts["iv_points"] = len(iv)

    finished = datetime.now(UTC)
    manifest = {
        "run_kind": run_kind,
        "trade_date": trade_date.isoformat(),
        "started_utc": started.isoformat(timespec="seconds"),
        "finished_utc": finished.isoformat(timespec="seconds"),
        "row_counts": counts,
        "requests": client.requests,
        "http_429": client.n_429,
        "request_errors": len(client.errors),
        "stock_expiries": [e1.isoformat(), e2.isoformat()],
        "front_expiry": {
            "fetched": need_front,
            "reason": "m1 DTE >= 30" if need_front else "m1 DTE < 30: m1 and m2 bracket 30 days",
            "found": front_found,
            "no_expiry_in_7_29_dte": len(front_missing),
            "no_expiry_symbols": front_missing,
        },
        "stock_strike_pct": stock_strike_pct,
        "stock_chain_symbols": int(stock_frame["underlying"].nunique()) if len(stock_frame) else 0,
        "skipped": empty,
        "universe_file": str(root / "universe" / f"{trade_date:%Y-%m}.json"),
        "universe_daily_last_date": universe["daily_last_date"],
        "feed": FEED,
        "underlying_price_source": "alpaca stocks snapshot feed=iex latestTrade",
    }
    publish_day(root, trade_date, staging, manifest)
    shutil.rmtree(staging, ignore_errors=True)
    final_dirs = [root / k / f"date={trade_date.isoformat()}" for k in counts]
    manifest["day_size_mb"] = dir_size_mb([d for d in final_dirs if d.exists()])
    for d in final_dirs:
        if (d / "_manifest.json").exists():
            (d / "_manifest.json").write_text(
                json.dumps({**manifest, "kind": d.parent.name}, indent=1)
            )
    return manifest


# --------------------------------------------------------------------------
# Account option levels (read-only)
# --------------------------------------------------------------------------


def check_accounts() -> int:
    """GET /v2/account for quant1, quant2, default paper account; print option fields only."""
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=ROOT / ".env")
    from open_composer.book_paper.accounts import load_account_credentials
    from open_composer.config import alpaca_api_key_id, alpaca_api_secret_key

    targets: list[tuple[str, str, str, str]] = []
    for name in ("quant1", "quant2"):
        creds = load_account_credentials(name)
        targets.append((name, creds.base_url, creds.key_id, creds.secret_key))
    targets.append(
        (
            "default_paper",
            trading_root().removesuffix("/v2"),
            alpaca_api_key_id() or "",
            alpaca_api_secret_key() or "",
        )
    )
    for name, base, key_id, secret in targets:
        client = RateLimitedClient({"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret})
        body = client.get_json(base.rstrip("/") + "/v2/account") or {}
        fields = {k: v for k, v in body.items() if "option" in k.lower()}
        print(f"{name}: {json.dumps(fields, sort_keys=True) if fields else 'no option fields'}")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force-now", action="store_true", help="manual run: skip the time window")
    parser.add_argument("--check-accounts", action="store_true")
    parser.add_argument("--root", type=Path, default=OPTIONS_DIR)
    parser.add_argument("--stock-strike-pct", type=float, default=STOCK_CHAIN_STRIKE_PCT)
    args = parser.parse_args(argv)
    if args.check_accounts:
        return check_accounts()

    now = datetime.now(UTC)
    local_date = now.astimezone(NY).date()
    client = build_client()
    trading_days = load_trading_days(
        client, local_date - timedelta(days=7), local_date + timedelta(days=120)
    )
    existing = read_manifest(args.root, local_date)
    run, reason = should_run(
        now,
        trading_days=trading_days,
        force_now=args.force_now,
        existing_run_kind=existing["run_kind"] if existing else None,
    )
    print(f"{now.isoformat(timespec='seconds')} decision={run} reason={reason}")
    # VIX term structure: previous trading day closes (appended even when no chain run is due)
    if reason != "not_a_trading_day":
        try:
            vix_path = args.root / "vix_term" / "vix_term.parquet"
            print(f"vix_term rows: {update_vix_term(vix_path, local_date)}")
        except Exception as exc:  # noqa: BLE001 - never block the chain snapshot
            print(f"vix_term failed: {type(exc).__name__}")
    if not run:
        return 0
    universe = ensure_universe(local_date, args.root / "universe")
    manifest = run_snapshot(
        client,
        root=args.root,
        trade_date=local_date,
        trading_days=trading_days,
        run_kind="manual" if args.force_now else "scheduled",
        universe=universe,
        stock_strike_pct=args.stock_strike_pct,
    )
    print(
        json.dumps({k: manifest[k] for k in ("row_counts", "requests", "http_429", "day_size_mb")})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
