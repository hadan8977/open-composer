"""T-20260929-33: build a US-equity-session-aligned crypto price panel with
no API keys.

For every date the local SPY SIP daily panel has a bar (used as the US
trading calendar), this script finds the 15-minute crypto bar whose open
time equals 09:30 America/New_York (the `open` price) and the 15-minute bar
whose open time equals 16:00 America/New_York (the `close` price), for each
symbol in `SYMBOLS`. No forward fill: a date with no matching 15m bar (data
gap, or before the symbol's own history starts) is left NaN.

Two public, keyless sources, both resumable (already-downloaded files are
reused, not re-fetched):

  1. Binance public monthly klines archive (primary, all symbols):
     https://data.binance.vision/data/spot/monthly/klines/<SYM>USDT/15m/<SYM>USDT-15m-YYYY-MM.zip
     Raw zips cached under data/research/crypto/raw/binance/<SYM>USDT/.

  2. Coinbase Exchange public candles (BTC and ETH only, to reach the
     2016-05 stress-window start -- Binance's own BTCUSDT history only
     starts 2017-08-17): https://api.exchange.coinbase.com/products/<SYM>-USD/candles
     capped at 300 candles/request, rate-limited to <=3 req/s. Cached as one
     parquet per symbol under data/research/crypto/raw/coinbase/.

Output: data/research/crypto/session_prices.parquet, columns
symbol/date/open/close, symbol values like "BTCUSD" (Alpaca-style, no
"/" or "-").

Usage:
    uv run python scripts/fetch_crypto_session_prices.py
    uv run python scripts/fetch_crypto_session_prices.py --symbols BTC ETH
"""

from __future__ import annotations

import argparse
import sys
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "research" / "crypto" / "raw"
BINANCE_DIR = RAW_DIR / "binance"
COINBASE_DIR = RAW_DIR / "coinbase"
OUT_PATH = ROOT / "data" / "research" / "crypto" / "session_prices.parquet"

ET = ZoneInfo("America/New_York")

# Alpaca-listed coins (per alpaca.markets/support/what-are-the-supported-coins-pairs,
# source card h20260929_33_crypto_trend.jsonl:alpaca_crypto_supported_coins) that also
# have a BTCUSDT-analog USDT spot pair on Binance with usable history.
SYMBOLS: list[str] = [
    "BTC",
    "ETH",
    "LTC",
    "BCH",
    "LINK",
    "DOGE",
    "AVAX",
    "UNI",
    "AAVE",
    "DOT",
]
# Coinbase back-fill (pre-Binance-listing history) only for the two symbols
# the brief calls out for stress-window (2016-05) depth.
COINBASE_SYMBOLS: list[str] = ["BTC", "ETH"]
COINBASE_BACKFILL_START = "2016-05-01"

KLINE_COLUMNS = [
    "open_time_ms",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time_ms",
    "quote_volume",
    "n_trades",
    "taker_base_vol",
    "taker_quote_vol",
    "ignore",
]

REQUEST_TIMEOUT = 30
COINBASE_MIN_INTERVAL_S = 0.4  # <= 3 req/s


def _month_range(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Period]:
    return list(pd.period_range(start=start.to_period("M"), end=end.to_period("M"), freq="M"))


def spy_trading_dates() -> list[pd.Timestamp]:
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT DISTINCT timestamp::DATE AS d FROM read_parquet"
            "('data/sip/daily/**/*.parquet') WHERE symbol='SPY' ORDER BY d"
        ).fetchall()
    finally:
        con.close()
    return [pd.Timestamp(r[0]) for r in rows]


def _download_binance_month(symbol_usdt: str, period: pd.Period, dest_dir: Path) -> Path | None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{symbol_usdt}-15m-{period.year:04d}-{period.month:02d}.zip"
    dest = dest_dir / fname
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol_usdt}/15m/{fname}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:  # pragma: no cover - network
        print(f"  {fname}: request failed ({exc})", flush=True)
        return None
    if resp.status_code == 404:
        return None  # symbol not listed yet, or month not yet published
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def load_binance_15m(symbol: str, *, through: pd.Timestamp) -> pd.DataFrame:
    """All available monthly klines for `<symbol>USDT`, from Binance's own
    listing month through `through` (UTC), downloading any missing months
    (cached zips are reused, never re-fetched)."""
    symbol_usdt = f"{symbol}USDT"
    dest_dir = BINANCE_DIR / symbol_usdt
    # Binance's own earliest listing dates vary by symbol; probe forward
    # from 2017-08 (BTCUSDT's own start) rather than assuming a fixed start,
    # skipping (not erroring on) months before the symbol existed (404).
    probe_start = pd.Timestamp("2017-08-01", tz="UTC")
    months = _month_range(probe_start, through)
    frames: list[pd.DataFrame] = []
    first_hit = False
    for period in months:
        path = _download_binance_month(symbol_usdt, period, dest_dir)
        if path is None:
            if first_hit:
                # Once we've seen data, a later 404 means "not published yet"
                # (current month) -- stop, don't keep probing forward.
                break
            continue
        first_hit = True
        try:
            with zipfile.ZipFile(path) as zf:
                inner = zf.namelist()[0]
                with zf.open(inner) as fh:
                    raw = pd.read_csv(fh, header=None, names=KLINE_COLUMNS)
        except (zipfile.BadZipFile, OSError, IndexError):
            print(f"  {path.name}: corrupt/unreadable, skipping", flush=True)
            continue
        # Binance's newer monthly archives (2025+) sometimes emit a header
        # row identical to KLINE_COLUMNS as data row 0 -- drop it if so.
        if isinstance(raw.iloc[0, 0], str):
            raw = raw.iloc[1:].reset_index(drop=True)
        raw["open_time_ms"] = pd.to_numeric(raw["open_time_ms"], errors="coerce")
        # Binance switched some symbols' monthly archives to microsecond
        # (not millisecond) open_time in 2025 -- a millisecond value for
        # "now" is ~13 digits (~1.7e12); a microsecond value is ~16 digits
        # (~1.7e15). Detect per-file via the first finite value's magnitude
        # and normalize to milliseconds before concatenating, rather than
        # assuming one unit for the whole symbol.
        first_val = raw["open_time_ms"].dropna().iloc[0] if raw["open_time_ms"].notna().any() else 0
        if first_val > 1e14:  # microseconds
            raw["open_time_ms"] = raw["open_time_ms"] / 1000.0
        frames.append(raw)
        time.sleep(0.05)
    if not frames:
        return pd.DataFrame(columns=["open_time_utc", "open", "close"])
    full = pd.concat(frames, ignore_index=True)
    full["open_time_utc"] = pd.to_datetime(full["open_time_ms"], unit="ms", utc=True)
    full["open"] = pd.to_numeric(full["open"], errors="coerce")
    full["close"] = pd.to_numeric(full["close"], errors="coerce")
    out = full[["open_time_utc", "open", "close"]].dropna(subset=["open_time_utc"])
    out = out.drop_duplicates(subset="open_time_utc").sort_values("open_time_utc")
    return out.reset_index(drop=True)


def load_coinbase_15m_backfill(symbol: str, *, end_utc: pd.Timestamp) -> pd.DataFrame:
    """Coinbase Exchange public candles for `<symbol>-USD`, granularity=900s
    (15m), from `COINBASE_BACKFILL_START` through `end_utc` (exclusive).
    Cached as one parquet per symbol; resumable by re-running (only missing
    trailing chunks are re-requested -- this project's data volume here is
    small enough that a full re-fetch on any cache miss is acceptable, so
    the cache is whole-file, not per-chunk)."""
    cache_path = COINBASE_DIR / f"{symbol}-USD-15m.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    COINBASE_DIR.mkdir(parents=True, exist_ok=True)
    start = pd.Timestamp(COINBASE_BACKFILL_START, tz="UTC")
    chunk = timedelta(minutes=15 * 300)
    rows: list[list[float]] = []
    cur = start
    session = requests.Session()
    while cur < end_utc:
        chunk_end = min(cur + chunk, end_utc)
        url = f"https://api.exchange.coinbase.com/products/{symbol}-USD/candles"
        params = {
            "granularity": 900,
            "start": cur.isoformat().replace("+00:00", "Z"),
            "end": chunk_end.isoformat().replace("+00:00", "Z"),
        }
        try:
            resp = session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "oc-research/1.0"},
            )
        except requests.RequestException as exc:  # pragma: no cover - network
            print(f"  coinbase {symbol} {cur.date()}: request failed ({exc})", flush=True)
            cur = chunk_end
            time.sleep(COINBASE_MIN_INTERVAL_S)
            continue
        time.sleep(COINBASE_MIN_INTERVAL_S)
        if resp.status_code == 200:
            data = resp.json()  # [time, low, high, open, close, volume], newest first
            for row in data:
                rows.append(row)
        elif resp.status_code != 404:
            print(f"  coinbase {symbol} {cur.date()}: HTTP {resp.status_code}", flush=True)
        cur = chunk_end
    if not rows:
        out = pd.DataFrame(columns=["open_time_utc", "open", "close"])
    else:
        frame = pd.DataFrame(rows, columns=["t", "low", "high", "open", "close", "volume"])
        frame["open_time_utc"] = pd.to_datetime(frame["t"], unit="s", utc=True)
        frame["open"] = pd.to_numeric(frame["open"], errors="coerce")
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        out = (
            frame[["open_time_utc", "open", "close"]]
            .dropna(subset=["open_time_utc"])
            .drop_duplicates(subset="open_time_utc")
            .sort_values("open_time_utc")
            .reset_index(drop=True)
        )
    out.to_parquet(cache_path)
    return out


def session_prices_for_symbol(
    symbol: str, bars: pd.DataFrame, dates: list[pd.Timestamp]
) -> pd.DataFrame:
    """(date, open, close) from a 15m-bar frame keyed on the exact
    09:30/16:00 America/New_York open-time bar -- no fill, no nearest-bar
    fallback, so DST transitions and data gaps surface as NaN rather than a
    silently-wrong price."""
    if bars.empty:
        return pd.DataFrame({"date": [d.date() for d in dates], "open": np.nan, "close": np.nan})
    indexed = bars.set_index("open_time_utc")
    open_px: list[float] = []
    close_px: list[float] = []
    for d in dates:
        naive = datetime(d.year, d.month, d.day)
        open_et = naive.replace(hour=9, minute=30, tzinfo=ET)
        close_et = naive.replace(hour=16, minute=0, tzinfo=ET)
        open_utc = pd.Timestamp(open_et.astimezone(UTC))
        close_utc = pd.Timestamp(close_et.astimezone(UTC))
        open_px.append(float(indexed["open"].get(open_utc, np.nan)))
        close_px.append(float(indexed["close"].get(close_utc, np.nan)))
    return pd.DataFrame({"date": [d.date() for d in dates], "open": open_px, "close": close_px})


def build(symbols: list[str]) -> pd.DataFrame:
    dates = spy_trading_dates()
    now_utc = pd.Timestamp.now(tz="UTC")
    frames: list[pd.DataFrame] = []
    for sym in symbols:
        print(f"symbol {sym}: downloading Binance 15m klines...", flush=True)
        binance = load_binance_15m(sym, through=now_utc)
        print(f"  binance rows: {len(binance)}", flush=True)
        bars = binance
        if sym in COINBASE_SYMBOLS:
            binance_start = binance["open_time_utc"].min() if not binance.empty else now_utc
            print(f"  backfilling Coinbase through {binance_start}...", flush=True)
            cb = load_coinbase_15m_backfill(sym, end_utc=binance_start)
            print(f"  coinbase rows: {len(cb)}", flush=True)
            bars = pd.concat([cb, binance], ignore_index=True)
            bars = bars.drop_duplicates(subset="open_time_utc").sort_values("open_time_utc")
        sp = session_prices_for_symbol(sym, bars, dates)
        sp.insert(0, "symbol", f"{sym}USD")
        frames.append(sp)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    args = ap.parse_args(argv)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out = build(args.symbols)
    out.to_parquet(OUT_PATH, index=False)
    n_rows = len(out)
    coverage = out.groupby("symbol").apply(lambda g: g["close"].notna().sum(), include_groups=False)
    print(f"wrote {OUT_PATH} ({n_rows} rows)")
    print("non-null close-price coverage by symbol:")
    print(coverage.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
