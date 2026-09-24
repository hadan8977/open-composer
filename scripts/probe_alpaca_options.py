"""I-20260924-01 feasibility probe: can Alpaca's free historical options data
measure the two option-implied signals arXiv:2608.26115 finds survive 2023-2026
on paid OPRA EOD data?

  - IV spread: ATM call IV minus ATM put IV, same strike/expiry
    (Cremers & Weinbaum 2010, put-call parity deviation)
  - risk-neutral skewness (Bakshi-Kapadia-Madan style)

Go/no-go probe only -- no full ingest, no strategy test. Budget ~90 minutes.
See reports/research/intel/I-20260924-01-alpaca-options-feasibility.md for
the write-up this script's output feeds.

Usage::

    uv run python scripts/probe_alpaca_options.py --quick     # 1 symbol x 1 month smoke test
    uv run python scripts/probe_alpaca_options.py             # full 20 x 3 probe

Credentials come from ``.env`` via ``load_dotenv()`` -- this script loads it
once at startup and never reads, prints, or logs its contents; HTTP calls
read ``ALPACA_API_KEY_ID``/``ALPACA_API_SECRET_KEY`` out of ``os.environ``
through ``open_composer.config`` (same pattern as
``scripts/collect_alpaca_news_packets.py``).

Method
------
1. Universe/months: liquid-name list x {2024-03, 2025-04, 2026-06}.
2. Window: first N (default 10) US trading days of the sample month, per
   symbol, read from the local SIP daily archive.
3. Expiry: nearest *monthly* (3rd Friday) expiry to (window midpoint + 30
   calendar days). A smoke test during design showed weeklies ~30-45 days
   out are often not listed yet that early (empty bars/trades for a
   2024-04-05 weekly queried from 2024-03-01), while a 2024-04-19 monthly
   already had a full month of March bars -- so monthlies are used as the
   30-DTE proxy instead of "whatever is nearest on the day," which would
   conflate "not tradable yet" with "no free-tier data."
4. Contracts: ``GET {trading_root}/v2/options/contracts`` with
   ``root_symbol=<SYM>`` set explicitly. Alpaca returns adjusted-root
   duplicates for the same underlying (observed: ``1AAPL...`` rows mixed in
   with ``AAPL...`` rows for the same underlying_symbols query) -- without
   the explicit root_symbol filter those get double-counted.
5. Per trading day: ATM strike = nearest listed strike to that day's SIP
   daily close.
6. IV per (symbol, day, method) via European Black-Scholes + Brent's method
   (American early-exercise premium is ignored -- noted limitation), q=0
   (noted caveat: no point-in-time dividend series was wired up for this
   probe), r = a fixed rough per-month approximation (noted caveat; being
   common to both legs it mostly cancels out of the *spread*, which is the
   quantity this probe cares about).

   Methods compared:
     (a) daily bar close: ``/v1beta1/options/bars``, timeframe=1Day
     (b) VWAP of the last 30 minutes of trades: ``/v1beta1/options/trades``,
         15:30-16:00 America/New_York
     (c) historical quotes: probed once against ``/v1beta1/options/quotes``;
         returned HTTP 404 on this account (see http_evidence.json), so this
         method is not run in the main loop.
7. Underlying price, time-matched: SIP daily close for method (a); SIP
   minute-bar VWAP over the same last-30-minutes window for method (b), via
   ``open_composer.adapters.data.sip_parquet.load_sip_bars``.
8. Skew-wing density: on the window's last day, pull bars for every strike
   in the fetched chain (not just ATM) once per (symbol, month) and count
   strikes with a valid close, bucketed by moneyness, to answer whether
   BKM-style risk-neutral skewness is computable at all from what the chain
   returns.

Rate limiting: paces off the ``X-Ratelimit-Remaining`` response header and
backs off (``Retry-After``, else exponential with jitter) on HTTP 429.

Outputs (gitignored under ``data/raw/alpaca_options_probe/``):
  iv_rows.parquet       per (symbol, month, day, method) IV rows
  wing_density.csv      per (symbol, month) strike-wing coverage
  http_evidence.json    status codes / field names / one sample shape, no secrets
  run_log.jsonl         per-call log (endpoint, params, status, item count)
  stats_summary.json    aggregate coverage/noise stats used by the brief
"""

from __future__ import annotations

import argparse
import calendar
import gc
import json
import math
import random
import resource
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from scipy.optimize import brentq
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from open_composer.adapters.data.sip_parquet import (  # noqa: E402
    SipParquetError,
    load_sip_bars,
)
from open_composer.config import (  # noqa: E402
    alpaca_api_base_url,
    alpaca_api_key_id,
    alpaca_api_secret_key,
)

DATA_ROOT = "https://data.alpaca.markets"
NY = ZoneInfo("America/New_York")

DEFAULT_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "TSLA",
    "AMD",
    "JPM",
    "XOM",
    "NFLX",
    "COST",
    "AVGO",
    "CRM",
    "BA",
    "DIS",
    "PLTR",
    "SMCI",
    "COIN",
    "MRNA",
]
DEFAULT_MONTHS = ["2024-03", "2025-04", "2026-06"]

# Rough fixed approximations of the ~3M T-bill rate for each sample month.
# Not point-in-time; common to both legs of a spread so its effect on
# iv_call - iv_put is second-order (see the report's caveat).
RISK_FREE_BY_MONTH = {
    "2024-03": 0.053,
    "2025-04": 0.043,
    "2026-06": 0.040,
}
DIVIDEND_YIELD = 0.0  # fixed at 0 for every name in this probe; noted caveat.

OUT_DIR = ROOT / "data" / "raw" / "alpaca_options_probe"
MEMORY_WARN_KB = 500_000  # ~500MB soft ceiling per the hard rule


# --------------------------------------------------------------------------
# HTTP session: auth headers built once from config, rate-paced, 429-aware.
# --------------------------------------------------------------------------


@dataclass
class ProbeSession:
    headers: dict[str, str]
    calls: int = 0
    log: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get(self, url: str, params: dict | None = None, max_retries: int = 6) -> requests.Response:
        last_resp: requests.Response | None = None
        for attempt in range(max_retries):
            resp = self.session.get(url, params=params, timeout=25)
            self.calls += 1
            last_resp = resp
            remaining = resp.headers.get("X-Ratelimit-Remaining")
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                sleep_s = float(retry_after) if retry_after else min(2**attempt, 30)
                sleep_s += random.uniform(0, 0.5)
                self.log.append(
                    {
                        "url": _strip_query(url),
                        "params": _safe_params(params),
                        "status": 429,
                        "attempt": attempt,
                        "sleep_s": round(sleep_s, 2),
                    }
                )
                time.sleep(sleep_s)
                continue
            try:
                n_items = _count_items(resp)
            except Exception:  # noqa: BLE001 - logging must never crash the probe
                n_items = None
            self.log.append(
                {
                    "url": _strip_query(url),
                    "params": _safe_params(params),
                    "status": resp.status_code,
                    "n_items": n_items,
                }
            )
            if remaining is not None and remaining.isdigit() and int(remaining) < 3:
                time.sleep(0.6)
            return resp
        assert last_resp is not None
        return last_resp


def _strip_query(url: str) -> str:
    return url.split("?", 1)[0]


def _safe_params(params: dict | None) -> dict:
    # Params never carry secrets (those live only in headers); this is a
    # plain passthrough kept as its own function so a future param never
    # accidentally starts carrying one without a review point.
    return dict(params or {})


def _count_items(resp: requests.Response) -> int | None:
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    for key in ("bars", "trades", "quotes", "option_contracts"):
        if key in body:
            value = body[key]
            if isinstance(value, dict):
                return sum(len(v) for v in value.values())
            if isinstance(value, list):
                return len(value)
    return None


def build_session() -> ProbeSession:
    key_id = alpaca_api_key_id()
    secret = alpaca_api_secret_key()
    if not key_id or not secret:
        raise SystemExit("ALPACA_API_KEY_ID/ALPACA_API_SECRET_KEY not set (check .env)")
    headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret}
    return ProbeSession(headers=headers)


def trading_root() -> str:
    base = alpaca_api_base_url().rstrip("/")
    return base if base.endswith("/v2") else base + "/v2"


# --------------------------------------------------------------------------
# Calendar / window helpers
# --------------------------------------------------------------------------


def month_bounds(month_key: str) -> tuple[date, date]:
    year, month = (int(x) for x in month_key.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def third_friday(year: int, month: int) -> date:
    cal = calendar.Calendar()
    fridays = [d for d in cal.itermonthdates(year, month) if d.month == month and d.weekday() == 4]
    return fridays[2]


def nearest_monthly_expiry(target: date) -> date:
    candidates = []
    for delta_months in range(-1, 3):
        y, m = target.year, target.month + delta_months
        while m > 12:
            m -= 12
            y += 1
        while m < 1:
            m += 12
            y -= 1
        candidates.append(third_friday(y, m))
    return min(candidates, key=lambda d: abs((d - target).days))


def trading_day_window(symbol: str, month_key: str, window_days: int) -> pd.DataFrame:
    start, end = month_bounds(month_key)
    try:
        frame = load_sip_bars(
            symbol,
            frequency="daily",
            start=datetime(start.year, start.month, start.day, tzinfo=UTC),
            end=datetime(end.year, end.month, end.day, 23, 59, tzinfo=UTC),
            allow_missing=True,
        )
    except SipParquetError:
        return pd.DataFrame(columns=["date", "close"])
    if frame.empty:
        return pd.DataFrame(columns=["date", "close"])
    frame = frame.sort_values("timestamp")
    frame["date"] = frame["timestamp"].dt.tz_convert(NY).dt.date
    out = frame[["date", "close"]].drop_duplicates(subset="date").reset_index(drop=True)
    return out.head(window_days)


# --------------------------------------------------------------------------
# Alpaca options endpoints
# --------------------------------------------------------------------------


def get_contracts(
    session: ProbeSession,
    symbol: str,
    expiration_date: date,
    strike_lo: float,
    strike_hi: float,
) -> list[dict]:
    url = trading_root() + "/options/contracts"
    params = {
        "underlying_symbols": symbol,
        "root_symbol": symbol,
        "status": "inactive",
        "expiration_date": expiration_date.isoformat(),
        "strike_price_gte": f"{strike_lo:.2f}",
        "strike_price_lte": f"{strike_hi:.2f}",
        "limit": 200,
    }
    out: list[dict] = []
    page_token = None
    for _ in range(5):
        if page_token:
            params["page_token"] = page_token
        resp = session.get(url, params=params)
        if resp.status_code != 200:
            break
        body = resp.json()
        out.extend(body.get("option_contracts", []))
        page_token = body.get("next_page_token")
        if not page_token:
            break
    return out


def get_bars(
    session: ProbeSession, symbols: list[str], start: date, end: date
) -> dict[str, list[dict]]:
    if not symbols:
        return {}
    out: dict[str, list[dict]] = {}
    for batch in _chunks(symbols, 90):
        url = DATA_ROOT + "/v1beta1/options/bars"
        params = {
            "symbols": ",".join(batch),
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": (end + timedelta(days=1)).isoformat(),
            "limit": 10000,
        }
        page_token = None
        for _ in range(5):
            if page_token:
                params["page_token"] = page_token
            resp = session.get(url, params=params)
            if resp.status_code != 200:
                break
            body = resp.json()
            for sym, bars in body.get("bars", {}).items():
                out.setdefault(sym, []).extend(bars)
            page_token = body.get("next_page_token")
            if not page_token:
                break
    return out


def get_trades(
    session: ProbeSession, symbols: list[str], start: date, end: date, max_pages: int = 4
) -> dict[str, list[dict]]:
    if not symbols:
        return {}
    out: dict[str, list[dict]] = {}
    for batch in _chunks(symbols, 90):
        url = DATA_ROOT + "/v1beta1/options/trades"
        params = {
            "symbols": ",".join(batch),
            "start": datetime.combine(start, dtime(0, 0), tzinfo=UTC).isoformat(),
            "end": datetime.combine(end + timedelta(days=1), dtime(0, 0), tzinfo=UTC).isoformat(),
            "limit": 10000,
        }
        page_token = None
        for _page in range(max_pages):
            if page_token:
                params["page_token"] = page_token
            resp = session.get(url, params=params)
            if resp.status_code != 200:
                break
            body = resp.json()
            for sym, trades in body.get("trades", {}).items():
                out.setdefault(sym, []).extend(trades)
            page_token = body.get("next_page_token")
            if not page_token:
                break
    return out


def probe_quotes_endpoint(session: ProbeSession, sample_symbol: str) -> dict:
    url = DATA_ROOT + "/v1beta1/options/quotes"
    resp = session.get(
        url,
        params={
            "symbols": sample_symbol,
            "start": "2024-03-01T00:00:00Z",
            "end": "2024-03-01T23:59:59Z",
            "limit": 5,
        },
    )
    return {
        "endpoint": "/v1beta1/options/quotes",
        "status": resp.status_code,
        "body": _truncate(resp.text, 400),
    }


def _chunks(items: list[str], n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "...(truncated)"


# --------------------------------------------------------------------------
# Underlying price time-matching (local SIP data)
# --------------------------------------------------------------------------


def load_underlying_minute_window(symbol: str, start: date, end: date) -> pd.DataFrame:
    try:
        frame = load_sip_bars(
            symbol,
            frequency="minute",
            start=datetime.combine(start, dtime(0, 0), tzinfo=UTC),
            end=datetime.combine(end + timedelta(days=1), dtime(0, 0), tzinfo=UTC),
            allow_missing=True,
        )
    except SipParquetError:
        return pd.DataFrame(columns=["timestamp", "close", "volume"])
    return frame


def last30_vwap(minute_frame: pd.DataFrame, day: date) -> float:
    if minute_frame.empty:
        return float("nan")
    ts_ny = minute_frame["timestamp"].dt.tz_convert(NY)
    mask = (
        (ts_ny.dt.date == day) & (ts_ny.dt.time >= dtime(15, 30)) & (ts_ny.dt.time < dtime(16, 0))
    )
    sub = minute_frame.loc[mask]
    vol_sum = sub["volume"].sum()
    if sub.empty or not vol_sum or vol_sum <= 0:
        return float("nan")
    return float((sub["close"] * sub["volume"]).sum() / vol_sum)


# --------------------------------------------------------------------------
# Black-Scholes + IV solve
# --------------------------------------------------------------------------


def bs_price(S: float, K: float, T: float, r: float, q: float, sigma: float, right: str) -> float:
    if T <= 0 or sigma <= 0:
        return float("nan")
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if right == "call":
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def implied_vol(
    price: float, S: float, K: float, T: float, r: float, q: float, right: str
) -> tuple[float, str]:
    if price is None or not math.isfinite(price) or price <= 0 or T <= 0 or not math.isfinite(S):
        return float("nan"), "no_price"
    intrinsic = max(0.0, (S - K) if right == "call" else (K - S))
    upper_bound = S * math.exp(-q * T) if right == "call" else K * math.exp(-r * T)
    if price <= intrinsic + 1e-6:
        return float("nan"), "price_at_or_below_intrinsic"
    if price >= upper_bound:
        return float("nan"), "price_above_no_arbitrage_bound"

    def f(sigma: float) -> float:
        return bs_price(S, K, T, r, q, sigma, right) - price

    try:
        lo, hi = 1e-4, 6.0
        if f(lo) * f(hi) > 0:
            return float("nan"), "no_sign_change"
        iv = brentq(f, lo, hi, xtol=1e-6, maxiter=100)
        return float(iv), "ok"
    except Exception as exc:  # noqa: BLE001
        return float("nan"), f"solver_error:{type(exc).__name__}"


# --------------------------------------------------------------------------
# Per (symbol, month) processing
# --------------------------------------------------------------------------


def bars_by_date(raw_bars: list[dict]) -> dict[date, dict]:
    out = {}
    for bar in raw_bars:
        ts = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
        out[ts.date()] = bar
    return out


def last_trade_in_window(
    trades: list[dict], day: date, window_start: dtime, window_end: dtime
) -> dict | None:
    best = None
    for tr in trades:
        ts = datetime.fromisoformat(tr["t"].replace("Z", "+00:00")).astimezone(NY)
        if ts.date() != day:
            continue
        if not (window_start <= ts.time() < window_end):
            continue
        if best is None or ts > best["_ts"]:
            best = {**tr, "_ts": ts}
    return best


def window_vwap(trades: list[dict], day: date, window_start: dtime, window_end: dtime) -> float:
    num, den = 0.0, 0.0
    for tr in trades:
        ts = datetime.fromisoformat(tr["t"].replace("Z", "+00:00")).astimezone(NY)
        if ts.date() != day or not (window_start <= ts.time() < window_end):
            continue
        num += tr["p"] * tr["s"]
        den += tr["s"]
    return num / den if den > 0 else float("nan")


def process_symbol_month(
    session: ProbeSession, symbol: str, month_key: str, window_days: int
) -> dict:
    window = trading_day_window(symbol, month_key, window_days)
    result = {"symbol": symbol, "month": month_key, "iv_rows": [], "wing_rows": [], "notes": []}
    if window.empty:
        result["notes"].append("no_local_sip_daily_data_for_window")
        return result

    mid_row = window.iloc[len(window) // 2]
    mid_date: date = mid_row["date"]
    expiry = nearest_monthly_expiry(mid_date + timedelta(days=30))
    dte_from_mid = (expiry - mid_date).days
    result["expiry"] = expiry.isoformat()
    result["dte_from_mid"] = dte_from_mid

    price_lo = float(window["close"].min()) * 0.85
    price_hi = float(window["close"].max()) * 1.15
    contracts = get_contracts(session, symbol, expiry, price_lo, price_hi)
    if not contracts:
        result["notes"].append("no_contracts_returned")
        return result

    calls = {float(c["strike_price"]): c["symbol"] for c in contracts if c["type"] == "call"}
    puts = {float(c["strike_price"]): c["symbol"] for c in contracts if c["type"] == "put"}
    strikes_sorted = sorted(set(calls) | set(puts))

    # per-day ATM assignment
    day_atm: dict[date, float] = {}
    for _, row in window.iterrows():
        day_atm[row["date"]] = min(strikes_sorted, key=lambda k: abs(k - row["close"]))

    needed_symbols = set()
    for strike in set(day_atm.values()):
        if strike in calls:
            needed_symbols.add(calls[strike])
        if strike in puts:
            needed_symbols.add(puts[strike])
    needed_symbols = sorted(needed_symbols)

    window_start_date, window_end_date = window["date"].min(), window["date"].max()
    raw_bars = get_bars(session, needed_symbols, window_start_date, window_end_date)
    raw_trades = get_trades(session, needed_symbols, window_start_date, window_end_date)
    minute_frame = load_underlying_minute_window(symbol, window_start_date, window_end_date)

    bars_indexed = {sym: bars_by_date(raw_bars.get(sym, [])) for sym in needed_symbols}

    r = RISK_FREE_BY_MONTH[month_key]
    q = DIVIDEND_YIELD

    for _, row in window.iterrows():
        day: date = row["date"]
        daily_close = float(row["close"])
        strike = day_atm[day]
        call_sym = calls.get(strike)
        put_sym = puts.get(strike)
        if call_sym is None or put_sym is None:
            result["iv_rows"].append(
                _iv_row(
                    symbol,
                    month_key,
                    day,
                    expiry,
                    strike,
                    "a",
                    None,
                    math.nan,
                    math.nan,
                    math.nan,
                    "missing_leg",
                    math.nan,
                    "missing_leg",
                    math.nan,
                )
            )
            continue
        T = (expiry - day).days / 365.0

        # method (a): daily bar close
        call_bar = bars_indexed[call_sym].get(day)
        put_bar = bars_indexed[put_sym].get(day)
        call_px_a = call_bar["c"] if call_bar else math.nan
        put_px_a = put_bar["c"] if put_bar else math.nan
        iv_call_a, reason_call_a = implied_vol(call_px_a, daily_close, strike, T, r, q, "call")
        iv_put_a, reason_put_a = implied_vol(put_px_a, daily_close, strike, T, r, q, "put")
        result["iv_rows"].append(
            _iv_row(
                symbol,
                month_key,
                day,
                expiry,
                strike,
                "a",
                daily_close,
                call_px_a,
                put_px_a,
                iv_call_a,
                reason_call_a,
                iv_put_a,
                reason_put_a,
                time_gap_s=_time_gap(
                    raw_trades.get(call_sym, []), raw_trades.get(put_sym, []), day
                ),
            )
        )

        # method (b): VWAP of last 30 minutes of trades
        call_px_b = window_vwap(raw_trades.get(call_sym, []), day, dtime(15, 30), dtime(16, 0))
        put_px_b = window_vwap(raw_trades.get(put_sym, []), day, dtime(15, 30), dtime(16, 0))
        underlying_b = last30_vwap(minute_frame, day)
        iv_call_b, reason_call_b = implied_vol(call_px_b, underlying_b, strike, T, r, q, "call")
        iv_put_b, reason_put_b = implied_vol(put_px_b, underlying_b, strike, T, r, q, "put")
        result["iv_rows"].append(
            _iv_row(
                symbol,
                month_key,
                day,
                expiry,
                strike,
                "b",
                underlying_b,
                call_px_b,
                put_px_b,
                iv_call_b,
                reason_call_b,
                iv_put_b,
                reason_put_b,
                time_gap_s=_time_gap_windowed(
                    raw_trades.get(call_sym, []), raw_trades.get(put_sym, []), day
                ),
            )
        )

    # wing density on the window's last day
    last_day_row = window[window["date"] == window_end_date].iloc[0]
    spot_last = float(last_day_row["close"])
    all_symbols = sorted(set(calls.values()) | set(puts.values()))
    wing_bars = get_bars(session, all_symbols, window_end_date, window_end_date)
    for strike in strikes_sorted:
        moneyness = strike / spot_last
        for right, table in (("call", calls), ("put", puts)):
            sym = table.get(strike)
            if sym is None:
                continue
            bars_for_sym = bars_by_date(wing_bars.get(sym, []))
            bar = bars_for_sym.get(window_end_date)
            has_valid_price = bool(
                bar and bar.get("c", 0) and bar["c"] > 0 and bar["h"] >= bar["l"]
            )
            result["wing_rows"].append(
                {
                    "symbol": symbol,
                    "month": month_key,
                    "day": window_end_date.isoformat(),
                    "right": right,
                    "strike": strike,
                    "moneyness": moneyness,
                    "has_valid_bar": has_valid_price,
                }
            )

    del raw_bars, raw_trades, minute_frame, wing_bars, bars_indexed
    gc.collect()
    return result


def _iv_row(
    symbol,
    month_key,
    day,
    expiry,
    strike,
    method,
    underlying,
    call_px,
    put_px,
    iv_call,
    reason_call,
    iv_put,
    reason_put,
    time_gap_s=math.nan,
):
    iv_spread = iv_call - iv_put if math.isfinite(iv_call) and math.isfinite(iv_put) else math.nan
    return {
        "symbol": symbol,
        "month": month_key,
        "date": day.isoformat(),
        "expiry": expiry.isoformat(),
        "method": method,
        "strike": strike,
        "underlying_price": underlying,
        "call_price": call_px,
        "put_price": put_px,
        "iv_call": iv_call,
        "iv_call_reason": reason_call,
        "iv_put": iv_put,
        "iv_put_reason": reason_put,
        "iv_spread": iv_spread,
        "usable": math.isfinite(iv_spread),
        "time_gap_s": time_gap_s,
    }


def _time_gap(call_trades: list[dict], put_trades: list[dict], day: date) -> float:
    call_last = _last_trade_ts_of_day(call_trades, day)
    put_last = _last_trade_ts_of_day(put_trades, day)
    if call_last is None or put_last is None:
        return math.nan
    return abs((call_last - put_last).total_seconds())


def _time_gap_windowed(call_trades: list[dict], put_trades: list[dict], day: date) -> float:
    call_last = last_trade_in_window(call_trades, day, dtime(15, 30), dtime(16, 0))
    put_last = last_trade_in_window(put_trades, day, dtime(15, 30), dtime(16, 0))
    if call_last is None or put_last is None:
        return math.nan
    return abs((call_last["_ts"] - put_last["_ts"]).total_seconds())


def _last_trade_ts_of_day(trades: list[dict], day: date):
    best = None
    for tr in trades:
        ts = datetime.fromisoformat(tr["t"].replace("Z", "+00:00")).astimezone(NY)
        if ts.date() != day:
            continue
        if best is None or ts > best:
            best = ts
    return best


# --------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------


def compute_stats(iv_df: pd.DataFrame) -> dict:
    stats = {}
    for method in sorted(iv_df["method"].unique()):
        sub = iv_df[iv_df["method"] == method]
        usable = sub[sub["usable"]]
        coverage = len(usable) / len(sub) if len(sub) else float("nan")
        spread = usable["iv_spread"].dropna()
        autocorr = float("nan")
        if len(spread) > 5:
            autocorrs = []
            for (_sym, _mon), grp in usable.sort_values("date").groupby(["symbol", "month"]):
                series = grp["iv_spread"].dropna()
                if len(series) > 3:
                    ac = series.autocorr(lag=1)
                    if ac is not None and math.isfinite(ac):
                        autocorrs.append(ac)
            if autocorrs:
                autocorr = float(pd.Series(autocorrs).mean())
        gap_r2 = float("nan")
        gap_sub = usable.dropna(subset=["time_gap_s", "iv_spread"])
        if len(gap_sub) > 5 and gap_sub["time_gap_s"].std() > 0:
            corr = gap_sub["time_gap_s"].corr(gap_sub["iv_spread"].abs())
            if corr is not None and math.isfinite(corr):
                gap_r2 = float(corr**2)
        stats[method] = {
            "n_name_days": int(len(sub)),
            "coverage": coverage,
            "iv_spread_mean": float(spread.mean()) if len(spread) else float("nan"),
            "iv_spread_sd": float(spread.std()) if len(spread) else float("nan"),
            "iv_spread_p10": float(spread.quantile(0.10)) if len(spread) else float("nan"),
            "iv_spread_p50": float(spread.quantile(0.50)) if len(spread) else float("nan"),
            "iv_spread_p90": float(spread.quantile(0.90)) if len(spread) else float("nan"),
            "mean_lag1_autocorr": autocorr,
            "n_symbols_with_autocorr": len(autocorrs) if len(spread) > 5 else 0,
            "time_gap_r2_vs_abs_spread": gap_r2,
            "n_used_for_gap_r2": int(len(gap_sub)),
        }
    return stats


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    parser.add_argument("--months", nargs="*", default=DEFAULT_MONTHS)
    parser.add_argument("--window-days", type=int, default=10)
    parser.add_argument("--quick", action="store_true", help="1 symbol x 1 month smoke test")
    args = parser.parse_args()

    load_dotenv(dotenv_path=ROOT / ".env")
    session = build_session()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    symbols = args.symbols[:1] if args.quick else args.symbols
    months = args.months[:1] if args.quick else args.months

    quotes_evidence = probe_quotes_endpoint(session, f"{symbols[0]}240419C00180000")

    all_iv_rows: list[dict] = []
    all_wing_rows: list[dict] = []
    notes: list[str] = []
    peak_rss_kb = 0

    for month_key in months:
        for symbol in symbols:
            t0 = time.time()
            result = process_symbol_month(session, symbol, month_key, args.window_days)
            all_iv_rows.extend(result["iv_rows"])
            all_wing_rows.extend(result["wing_rows"])
            if result["notes"]:
                notes.append(f"{symbol}/{month_key}: {result['notes']}")
            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak_rss_kb = max(peak_rss_kb, rss_kb)
            print(
                f"[{symbol} {month_key}] rows={len(result['iv_rows'])} "
                f"wing={len(result['wing_rows'])} calls_total={session.calls} "
                f"elapsed={time.time() - t0:.1f}s rss={rss_kb / 1024:.0f}MB",
                flush=True,
            )
            if rss_kb > MEMORY_WARN_KB:
                print(f"WARNING: RSS {rss_kb / 1024:.0f}MB exceeds soft ceiling", file=sys.stderr)

    iv_df = pd.DataFrame(all_iv_rows)
    wing_df = pd.DataFrame(all_wing_rows)

    if not iv_df.empty:
        iv_df.to_parquet(OUT_DIR / "iv_rows.parquet", index=False)
    if not wing_df.empty:
        wing_df.to_csv(OUT_DIR / "wing_density.csv", index=False)

    stats = compute_stats(iv_df) if not iv_df.empty else {}

    http_evidence = {
        "contracts_endpoint": f"{trading_root()}/options/contracts",
        "bars_endpoint": DATA_ROOT + "/v1beta1/options/bars",
        "trades_endpoint": DATA_ROOT + "/v1beta1/options/trades",
        "quotes_probe": quotes_evidence,
        "total_calls_made": session.calls,
        "peak_rss_mb": peak_rss_kb / 1024,
    }
    (OUT_DIR / "http_evidence.json").write_text(json.dumps(http_evidence, indent=2))
    (OUT_DIR / "run_log.jsonl").write_text("\n".join(json.dumps(entry) for entry in session.log))
    (OUT_DIR / "stats_summary.json").write_text(
        json.dumps(
            {"stats": stats, "notes": notes, "n_iv_rows": len(iv_df), "n_wing_rows": len(wing_df)},
            indent=2,
        )
    )

    print("\n=== SUMMARY ===")
    print(f"total HTTP calls: {session.calls}")
    print(f"peak RSS: {peak_rss_kb / 1024:.0f} MB")
    print(f"iv_rows: {len(iv_df)}  wing_rows: {len(wing_df)}")
    for method, s in stats.items():
        print(f"method {method}: {json.dumps(s, indent=2)}")
    if notes:
        print("notes:", notes)


if __name__ == "__main__":
    main()
