"""Build the event table for iteration h20260929_20_news_nonews_drop_reversal.

Event: a stock in the PIT top-1500 ADV tier (`data/features/universe_broad`)
with a market-adjusted (vs SPY, close-to-close) one-day return <= -D. Every
event is classified 'news' or 'no-news' using two PIT sources:

  - `data/features/news_packets` (Benzinga-sourced headlines, `symbols`
    array + `visible_at` timestamp), and
  - `data/features/earnings_events` (SEC 8-K item-2.02 earnings filings,
    `ticker` + `acceptance_utc`).

A news/filing item counts for trading day t iff its timestamp falls in
`(session_close(t-1), session_close(t)]`, session_close = 16:00
America/New_York (DST-aware). This is done with a single vectorized
`np.searchsorted` against the array of each trading day's 16:00 ET close,
converted to UTC -- every timestamp buckets to exactly one trading session,
with no look-ahead by construction (a timestamp after today's close buckets
to tomorrow's session, never today's).

Price data for both event detection and the downstream backtest comes from
the same source (`data/sip/daily/*/*.parquet`, via
`run_h20260918_05_recent_menu.load_panel`), so the signal and the fill use
identical prices -- avoiding a detection/execution source mismatch.

Outputs (data/research/h20260929_20_news_nonews_drop_reversal/):
  - events.parquet: symbol, event_date, adj_ret, adv_rank_prev, tier,
    has_headline, has_earnings8k, news_flag
  - panel_close.parquet, panel_open.parquet: the price panel used, for reuse
    by the backtest script (avoids re-querying data/sip/daily).

Run under scripts/run_capped.sh --mem 1.8G --.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402

OUT_DIR = ROOT / "data" / "research" / "h20260929_20_news_nonews_drop_reversal"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_N = 1500
D_LOOSE = 0.05  # loosest preregistered threshold; D=8% is filtered downstream
PANEL_START = "2023-10-16"  # buffer before TEST start (2024-01-08) for lookback/ADV joins
HOLD_END = "2026-09-17"
RANKS_MONTH_END_FLOOR = "2023-06-01"  # seed month-ends before PANEL_START for the ffill
SESSION_CLOSE_LOCAL_TIME = "16:00:00"
SESSION_CLOSE_TZ = "America/New_York"


def load_universe_ranks(memory_limit: str = "1200MB") -> pd.DataFrame:
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute("SET threads=2")
    try:
        df = con.execute(
            f"""
            SELECT month_end, symbol, adv_rank
            FROM read_parquet('{ROOT}/data/features/universe_broad/*.parquet')
            WHERE adv_rank <= {TOP_N} AND close >= 5 AND month_end >= DATE '{RANKS_MONTH_END_FLOOR}'
            """
        ).df()
    finally:
        con.close()
    df["month_end"] = pd.to_datetime(df["month_end"])
    return df


def build_adv_rank_daily(ranks: pd.DataFrame, trading_days: pd.DatetimeIndex) -> pd.DataFrame:
    """Step-function PIT ADV rank per trading day: the rank known as of the
    latest completed month-end <= that day, held constant until the next
    month-end. NaN outside the top-TOP_N tier."""
    wide = ranks.pivot(index="month_end", columns="symbol", values="adv_rank").sort_index()
    union_index = wide.index.union(trading_days)
    daily = wide.reindex(union_index).sort_index().ffill()
    return daily.reindex(trading_days)


def session_close_utc(trading_days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    naive = pd.to_datetime(trading_days.strftime("%Y-%m-%d") + " " + SESSION_CLOSE_LOCAL_TIME)
    local = naive.tz_localize(SESSION_CLOSE_TZ, nonexistent="shift_forward", ambiguous="NaT")
    return local.tz_convert("UTC")


def bucket_to_trading_day(
    timestamps_utc: pd.Series, session_close: pd.DatetimeIndex, trading_days: pd.DatetimeIndex
) -> np.ndarray:
    """For each UTC timestamp, the trading day whose (prev_close, close]
    window contains it -- i.e. the first session_close >= timestamp. Returns
    the trading-day Timestamp, or NaT if the timestamp is after the last
    known session close (out of range, dropped by the caller)."""
    ts = timestamps_utc.to_numpy(dtype="datetime64[ns]")
    closes = session_close.to_numpy(dtype="datetime64[ns]")
    idx = np.searchsorted(closes, ts, side="left")
    out = np.full(len(ts), np.datetime64("NaT"), dtype="datetime64[ns]")
    valid = idx < len(closes)
    out[valid] = trading_days.to_numpy(dtype="datetime64[ns]")[idx[valid]]
    return out


def load_news_hits(symbols: set[str]) -> pd.DataFrame:
    frames = []
    for year in ("2024", "2025", "2026"):
        path = ROOT / "data" / "features" / "news_packets" / f"{year}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=["symbols", "visible_at"])
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["symbol", "visible_at"])
    all_news = pd.concat(frames, ignore_index=True)
    exploded = all_news.explode("symbols").rename(columns={"symbols": "symbol"})
    exploded = exploded.dropna(subset=["symbol"])
    exploded = exploded[exploded["symbol"].isin(symbols)]
    return exploded[["symbol", "visible_at"]].reset_index(drop=True)


def load_earnings8k_hits(symbols: set[str]) -> pd.DataFrame:
    frames = []
    for year in ("2024", "2025", "2026"):
        path = ROOT / "data" / "features" / "earnings_events" / f"{year}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=["ticker", "acceptance_utc"])
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["symbol", "visible_at"])
    all_8k = pd.concat(frames, ignore_index=True)
    all_8k = all_8k[all_8k["ticker"].isin(symbols)]
    out = all_8k.rename(columns={"ticker": "symbol", "acceptance_utc": "visible_at"}).copy()
    out["visible_at"] = pd.to_datetime(out["visible_at"], utc=True)
    return out.reset_index(drop=True)


def main() -> None:
    ranks = load_universe_ranks()
    symbols = sorted(ranks["symbol"].unique())
    print(
        f"universe_broad top-{TOP_N} distinct symbols since {RANKS_MONTH_END_FLOOR}: {len(symbols)}"
    )

    price_symbols = sorted(set(symbols) | {"SPY", "BIL", "SHY"})
    base.WARMUP_START = PANEL_START
    base.HOLD_END = HOLD_END
    close, open_ = base.load_panel(price_symbols)
    print(
        f"price panel: {close.shape[0]} sessions x {close.shape[1]} symbols, "
        f"{close.index[0].date()}..{close.index[-1].date()}"
    )

    trading_days = close.index
    adv_rank_daily = build_adv_rank_daily(ranks, trading_days)
    adv_rank_daily = adv_rank_daily.reindex(columns=[s for s in symbols if s in close.columns])
    adv_rank_prev = adv_rank_daily.shift(1)

    ret = close.pct_change(fill_method=None)
    ret_spy = ret["SPY"]
    stock_cols = [c for c in adv_rank_prev.columns if c in ret.columns]
    adj_ret = ret[stock_cols].sub(ret_spy, axis=0)

    eligible = adv_rank_prev[stock_cols].le(TOP_N) & adv_rank_prev[stock_cols].notna()
    event_mask = (adj_ret <= -D_LOOSE) & eligible

    stacked_mask = event_mask.stack()
    hit_index = stacked_mask[stacked_mask].index
    if len(hit_index) == 0:
        raise RuntimeError("no events found -- check D_LOOSE / universe / panel range")

    event_dates = hit_index.get_level_values(0)
    event_symbols = hit_index.get_level_values(1)
    events = pd.DataFrame(
        {
            "symbol": event_symbols,
            "event_date": event_dates,
            "adj_ret": adj_ret.stack().loc[hit_index].to_numpy(),
            "adv_rank_prev": adv_rank_prev[stock_cols].stack().loc[hit_index].to_numpy(),
        }
    ).reset_index(drop=True)
    events["tier"] = np.select(
        [events["adv_rank_prev"] <= 500, events["adv_rank_prev"] <= 1000],
        [1, 2],
        default=3,
    )
    print(f"raw events (adj_ret <= -{D_LOOSE:.0%}, top-{TOP_N} tier): {len(events)}")

    closes_utc = session_close_utc(trading_days)
    news_hits = load_news_hits(set(events["symbol"].unique()))
    if not news_hits.empty:
        news_hits = news_hits.copy()
        news_hits["bucket_date"] = bucket_to_trading_day(
            news_hits["visible_at"], closes_utc, trading_days
        )
        news_hits = news_hits.dropna(subset=["bucket_date"])
        headline_flags = news_hits[["symbol", "bucket_date"]].drop_duplicates()
        headline_flags["has_headline"] = True
        headline_flags = headline_flags.rename(columns={"bucket_date": "event_date"})
    else:
        headline_flags = pd.DataFrame(columns=["symbol", "event_date", "has_headline"])

    earnings_hits = load_earnings8k_hits(set(events["symbol"].unique()))
    if not earnings_hits.empty:
        earnings_hits = earnings_hits.copy()
        earnings_hits["bucket_date"] = bucket_to_trading_day(
            earnings_hits["visible_at"], closes_utc, trading_days
        )
        earnings_hits = earnings_hits.dropna(subset=["bucket_date"])
        earnings_flags = earnings_hits[["symbol", "bucket_date"]].drop_duplicates()
        earnings_flags["has_earnings8k"] = True
        earnings_flags = earnings_flags.rename(columns={"bucket_date": "event_date"})
    else:
        earnings_flags = pd.DataFrame(columns=["symbol", "event_date", "has_earnings8k"])

    events = events.merge(headline_flags, on=["symbol", "event_date"], how="left")
    events = events.merge(earnings_flags, on=["symbol", "event_date"], how="left")
    events["has_headline"] = events["has_headline"].fillna(False).astype(bool)
    events["has_earnings8k"] = events["has_earnings8k"].fillna(False).astype(bool)
    events["news_flag"] = events["has_headline"] | events["has_earnings8k"]

    n_news = int(events["news_flag"].sum())
    print(
        f"events with news/earnings same session: {n_news} / {len(events)} "
        f"({n_news / len(events):.1%})"
    )

    events_path = OUT_DIR / "events.parquet"
    events.to_parquet(events_path, index=False)
    print(f"wrote {events_path} ({len(events)} rows)")

    close.to_parquet(OUT_DIR / "panel_close.parquet")
    open_.to_parquet(OUT_DIR / "panel_open.parquet")
    print(f"wrote panel_close.parquet / panel_open.parquet ({close.shape[0]}x{close.shape[1]})")


if __name__ == "__main__":
    main()
