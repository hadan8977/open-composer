"""Publish close-time market state and SIP earnings-gap features."""

import argparse
import io
from datetime import UTC, date, datetime, timedelta

import duckdb
import httpx
import numpy as np
import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.market_sessions import (
    NEW_YORK,
    us_equity_session_close,
    us_equity_session_dates,
)
from open_composer.research.features.price_hygiene import (
    DEFAULT_MAX_ONE_DAY_PRICE_RATIO,
    drop_ghost_bars,
    sanitize_price_matrices,
)
from scripts.build_research_events import DERIVED, START, publish

FRED_SERIES = {
    "vix": "VIXCLS",
    "vix3m": "VXVCLS",
    "high_yield_spread": "BAMLH0A0HYM2",
    "treasury_10y_2y": "T10Y2Y",
}
BENCHMARKS = ("SPY", "QQQ")
PRICE_FIELDS = ["open", "high", "low", "close", "source_version"]
UNIVERSE_PATH = DERIVED / "daily-us-stock-universe.parquet"


def fred_at_close(sessions):
    result = pd.DataFrame(index=sessions)
    with httpx.Client(timeout=30) as client:
        for name, series in FRED_SERIES.items():
            response = client.get(
                "https://fred.stlouisfed.org/graph/fredgraph.csv",
                params={"id": series, "cosd": "2015-12-01"},
            )
            response.raise_for_status()
            data = pd.read_csv(io.BytesIO(response.content), index_col=0, parse_dates=True)[
                series
            ].dropna()
            # Daily FRED CSV has observation dates and no release times. Use
            # the prior observation at close, and keep its date for auditing.
            available = data.index.get_indexer(sessions - pd.Timedelta(days=1), method="pad")
            result[name] = data.iloc[available].set_axis(sessions).where(available >= 0)
            result[f"{name}_observation_date"] = data.index[available].where(available >= 0)
    return result


def daily_bars(start, end, *, adjustment="all"):
    start_utc = pd.Timestamp(start, tz=NEW_YORK).tz_convert(UTC)
    end_utc = pd.Timestamp(end + timedelta(days=1), tz=NEW_YORK).tz_convert(UTC) - pd.Timedelta(
        microseconds=1
    )
    columns = ["symbol", "timestamp", "trade_count", "volume", *PRICE_FIELDS]
    bars = load_sip_bars(None, start=start_utc, end=end_utc, adjustment=adjustment)[columns]
    bars["session_date"] = (
        bars.pop("timestamp").dt.tz_convert(NEW_YORK).dt.tz_localize(None).dt.normalize()
    )
    return (
        drop_ghost_bars(bars)
        .drop(columns="trade_count")
        .drop_duplicates(["symbol", "session_date"])
    )


def trailing_history(close, source):
    """Age since the latest break observable by each close, using repository defaults."""
    positions = np.arange(len(close))[:, None]
    previous_source = source.ffill().shift()
    switched = source.notna() & previous_source.notna() & source.ne(previous_source).fillna(False)
    resets = np.where(switched, positions, 0).astype("int32")
    _, _, report = sanitize_price_matrices(close, preserve_history=True)
    for event in report.breaks:
        if event.masked:
            row = close.index.get_loc(event.first_session_after)
            resets[row, close.columns.get_loc(event.symbol)] = row
    return pd.DataFrame(
        positions - np.maximum.accumulate(resets, axis=0), index=close.index, columns=close.columns
    )


def market_block(wide, raw_dollars):
    close = wide["close"]
    age = trailing_history(close, wide["source_version"])
    eligible = close.gt(0)
    eligible.loc[:, eligible.columns.intersection(BENCHMARKS)] = False
    result = pd.DataFrame({"universe_count": eligible.sum(axis=1)})
    benchmark = pd.DataFrame(index=close.index)
    for window in (50, 200):
        slope = (close / close.rolling(window).mean() - 1).where(age >= window - 1)
        result[f"above_{window}"] = ((slope > 0) & eligible).sum(axis=1)
        result[f"valid_{window}"] = (slope.notna() & eligible).sum(axis=1)
        for symbol in slope.columns.intersection(BENCHMARKS):
            benchmark[f"{symbol.lower()}_vs_sma_{window}"] = slope[symbol]
    high, low = wide["high"], wide["low"]
    last_high, last_low = high.shift().rolling(252).max(), low.shift().rolling(252).min()
    full_year = (age >= 252) & eligible & last_high.notna() & last_low.notna()
    result["valid_52w"] = full_year.sum(axis=1)
    result["new_highs"] = ((high > last_high) & full_year).sum(axis=1)
    result["new_lows"] = ((low < last_low) & full_year).sum(axis=1)
    daily = close.pct_change(fill_method=None).where(age >= 1)
    result["advancing"] = ((daily > 0) & eligible).sum(axis=1)
    result["declining"] = ((daily < 0) & eligible).sum(axis=1)
    result["valid_ad"] = (daily.notna() & eligible).sum(axis=1)
    prior = close.shift(63)
    full_quarter = (age >= 63) & prior.notna() & eligible
    dollars = raw_dollars.reindex_like(close).shift()
    full_quarter &= dollars.notna()
    result["valid_3m"] = full_quarter.sum(axis=1)
    result["up_25pct_3m"] = ((close >= 1.25 * prior) & (dollars > 20_000_000) & full_quarter).sum(
        axis=1
    )
    return result, benchmark, age


def earnings_gaps(wide, age, filings, raw_volume):
    close = wide["close"]
    prices = wide["open"] / close.shift()
    limit = DEFAULT_MAX_ONE_DAY_PRICE_RATIO
    source = wide["source_version"]
    gap = (prices - 1).where((prices <= limit) & (prices >= 1 / limit) & source.eq(source.shift()))
    volume = raw_volume.reindex_like(close).where(lambda v: v > 0)
    relative = (volume / volume.shift().rolling(20).mean()).where(age >= 20)
    row = close.index.get_indexer(filings.session_date)
    col = close.columns.get_indexer(filings.bar_symbol)
    keep = (row >= 0) & (col >= 0)
    output = filings.loc[keep, ["cik", "accession", "symbol", "bar_symbol", "session_date"]].copy()
    selection = row[keep], col[keep]
    output["opening_gap"] = gap.to_numpy()[selection]
    output["volume_ratio_20d"] = relative.to_numpy()[selection]
    return output


def build(from_date=START):
    events = pd.read_parquet(DERIVED / "earnings_releases.parquet").dropna(subset=["symbol"])
    events["session_date"] = pd.to_datetime(events.visible_date)
    with duckdb.connect(config={"threads": 2, "memory_limit": "300MB"}) as con:
        last = con.execute("SELECT max(trade_date)::DATE FROM read_parquet(?)", [str(UNIVERSE_PATH)]).fetchone()[0]
    now = datetime.now(NEW_YORK)
    sessions = us_equity_session_dates(from_date, min(now.date(), last))
    if (
        sessions
        and sessions[-1] == now.date()
        and now.time() < us_equity_session_close(sessions[-1])
    ):
        sessions = sessions[:-1]
    if not sessions:
        return
    market_parts, gap_parts = [], []
    history = raw_history = None
    warmup = max(START, date(from_date.year - 1, 1, 1))
    for boundary in pd.date_range(warmup, sessions[-1], freq="2QS-JAN"):
        first = boundary.date()
        start = max(START, first - timedelta(days=400))
        end = min((boundary + pd.DateOffset(months=6)).date() - timedelta(days=1), sessions[-1])
        index = pd.DatetimeIndex(us_equity_session_dates(start, end), name="session_date")
        fresh = daily_bars(first, end)
        bars = pd.concat([history, fresh], ignore_index=True) if history is not None else fresh
        del fresh
        history = bars.loc[bars.session_date >= pd.Timestamp(end - timedelta(days=400))]
        raw = daily_bars(first, end, adjustment="raw")[["session_date", "symbol", "volume"]]
        if raw_history is not None:
            raw = pd.concat([raw_history, raw], ignore_index=True)
        raw_history = raw.loc[raw.session_date >= pd.Timestamp(end - timedelta(days=400))]
        if end < from_date:
            del bars
            continue
        with duckdb.connect(config={"threads": 2, "memory_limit": "300MB"}) as con:
            selected = con.execute(
                """
                SELECT trade_date::TIMESTAMP_NS AS session_date, symbol, dollar_volume
                FROM read_parquet(?) WHERE is_member AND dollar_volume IS NOT NULL
                  AND trade_date BETWEEN ? AND ?
                """,
                [str(UNIVERSE_PATH), start, end],
            ).df()
        raw_dollars = selected.pivot(index="session_date", columns="symbol", values="dollar_volume")
        del selected
        symbols = pd.Index(bars.symbol.unique())
        filings = events[
            events.session_date.between(pd.Timestamp(max(first, from_date)), pd.Timestamp(end))
        ].copy()
        filings["bar_symbol"] = filings.symbol
        raw_volume = raw.loc[raw.symbol.isin(filings.bar_symbol)].pivot(
            index="session_date", columns="symbol", values="volume"
        )
        del raw
        counts, benchmarks = None, []
        grouped = bars.set_index(["symbol", "session_date"]).sort_index()
        del bars
        for offset in range(0, len(symbols), 250):
            batch = symbols[offset : offset + 250]
            wide = grouped.loc[batch, PRICE_FIELDS].unstack("symbol").reindex(index)
            stats, trend, age = market_block(wide, raw_dollars)
            counts = stats if counts is None else counts + stats
            benchmarks.append(trend)
            selection = filings[filings.bar_symbol.isin(batch)]
            if not selection.empty:
                gap_parts.append(earnings_gaps(wide, age, selection, raw_volume))
        market_parts.append(counts.join(pd.concat(benchmarks, axis=1)).loc[str(first) : str(end)])
        del grouped, raw_dollars, raw_volume
        print(f"SIP through {end}: {len(symbols):,} symbols", flush=True)

    market = pd.concat(market_parts).reindex(pd.DatetimeIndex(sessions, name="session_date"))
    for window in (50, 200):
        market[f"share_above_sma_{window}"] = (
            market.pop(f"above_{window}") / market[f"valid_{window}"]
        )
    market["new_highs_minus_lows_52w"] = (market.new_highs - market.new_lows).where(
        market.valid_52w > 0
    )
    market["advance_decline"] = (market.advancing - market.declining).where(market.valid_ad > 0)
    market["up_25pct_3m"] = market.up_25pct_3m.where(market.valid_3m > 0)
    closes = pd.to_datetime(
        [
            datetime.combine(day.date(), us_equity_session_close(day.date()), NEW_YORK)
            for day in market.index
        ],
        utc=True,
    )
    market["known_at"] = closes
    market = market.join(fred_at_close(market.index)).reset_index()
    if gap_parts:
        gaps = pd.concat(gap_parts, ignore_index=True)
    else:
        gaps = events.iloc[:0][["cik", "accession", "symbol", "session_date"]].assign(
            bar_symbol="", opening_gap=np.nan, volume_ratio_20d=np.nan
        )
    gaps = gaps.dropna(subset=["opening_gap", "volume_ratio_20d"], how="all")
    # Localize after adding the wall-clock time, including DST boundaries.
    gaps["gap_available_at"] = (
        (gaps.session_date + pd.Timedelta(hours=9, minutes=30)).dt.tz_localize(NEW_YORK)
        .dt.tz_convert(UTC).where(gaps.opening_gap.notna())
    )
    gaps["volume_available_at"] = (
        (gaps.session_date + pd.Timedelta(days=1)).dt.tz_localize(NEW_YORK)
        .dt.tz_convert(UTC).where(gaps.volume_ratio_20d.notna())
    )
    gaps["known_at"] = (gaps.session_date + pd.Timedelta(days=1)).dt.tz_localize(NEW_YORK).dt.tz_convert(UTC)
    gaps = gaps.sort_values(["session_date", "symbol", "accession"])
    for name, frame in (("market_state", market), ("earnings_gaps", gaps)):
        if from_date > START:
            prior = pd.read_parquet(
                DERIVED / f"{name}.parquet",
                filters=[("session_date", "<", pd.Timestamp(from_date))],
            )
            frame = pd.concat([prior, frame], ignore_index=True)
        publish(frame, name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=START)
    build(parser.parse_args().start)
