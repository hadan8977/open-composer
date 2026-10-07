"""Point-in-time minute bars for one session: providers, aggregation, history."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.execution.bar_source import _minute_frame_from_alpaca_raw
from open_composer.market_calendar import (
    NEW_YORK,
    previous_us_equity_session,
    us_equity_session_close,
)
from open_composer.research.bars.hourly import aggregate_regular_session

MINUTE_COLUMNS = [
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
]


class MinuteProvider(Protocol):
    feed: str

    def fetch(self, symbols: Sequence[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """1-minute bars with ``timestamp`` = bar start (UTC) in ``[start, end)``."""
        ...


def session_bounds(day: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    close = us_equity_session_close(day)
    if close is None:
        raise ValueError(f"{day} is not a US equity session")
    start = pd.Timestamp(datetime.combine(day, time(9, 30), tzinfo=NEW_YORK)).tz_convert("UTC")
    end = pd.Timestamp(datetime.combine(day, close, tzinfo=NEW_YORK)).tz_convert("UTC")
    return start, end


class ArchiveMinuteProvider:
    """SIP minute archive (``data/sip/minute``).  A scan costs ~20-30 s on this box, so a
    request covered by an earlier one (same or more symbols, wider range) is served from memory."""

    feed = "sip"

    def __init__(self, root: Path | None = None):
        self.root = root
        self._cache: list[tuple[frozenset[str], pd.Timestamp, pd.Timestamp, pd.DataFrame]] = []

    def fetch(self, symbols, start, end):
        wanted = frozenset(s.upper() for s in symbols)
        day_start, day_end = start.normalize(), end.normalize() + pd.Timedelta(days=1)
        frame = None
        for cached_symbols, c_start, c_end, cached in self._cache:
            if wanted <= cached_symbols and c_start <= day_start and day_end <= c_end:
                frame = cached
                break
        if frame is None:
            frame = load_sip_bars(
                sorted(wanted),
                frequency="minute",
                start=day_start,
                end=day_end,
                root=self.root,
                allow_missing=True,
            )
            self._cache.append((wanted, day_start, day_end, frame))
        if frame.empty:
            return frame
        ts = pd.to_datetime(frame["timestamp"], utc=True)
        keep = frame["symbol"].isin(wanted) & (ts >= start) & (ts < end)
        return frame[keep].reset_index(drop=True)


class AlpacaMinuteProvider:
    incremental = True  # SessionBars asks only for the minutes it does not have yet

    """Alpaca market-data minute bars with an explicit feed (``iex`` live, ``sip`` for rechecks).

    ``fetch_raw`` is injectable (tests); the default builds a data client from the book
    account's credentials by variable name (``ALPACA_<ACCOUNT>_API_KEY_ID`` /
    ``..._API_SECRET_KEY`` in the 600 env file) -- no value is ever printed."""

    def __init__(
        self,
        feed: str,
        *,
        account: str | None = None,
        fetch_raw: Callable[[list[str], pd.Timestamp, pd.Timestamp, str], pd.DataFrame]
        | None = None,
        limiter: Any | None = None,
    ):
        self.feed = feed
        self.account = account
        self.limiter = limiter
        self._fetch_raw = fetch_raw or self._default_fetch

    def _default_fetch(self, symbols, start, end, feed):
        from alpaca.data.enums import DataFeed
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        from open_composer.book_paper.accounts import load_account_credentials

        creds = load_account_credentials(self.account or "quant2")
        client = StockHistoricalDataClient(api_key=creds.key_id, secret_key=creds.secret_key)
        request = StockBarsRequest(
            symbol_or_symbols=list(symbols),
            timeframe=TimeFrame(1, TimeFrameUnit.Minute),
            start=start.to_pydatetime(),
            end=end.to_pydatetime(),
            feed=DataFeed(feed),
        )
        frame = client.get_stock_bars(request).df
        return pd.DataFrame() if frame is None or frame.empty else frame.reset_index()

    def fetch(self, symbols, start, end):
        if self.limiter is not None:  # one call per page of ~10k rows
            minutes = max(1, int((end - start) / pd.Timedelta(minutes=1)))
            self.limiter.acquire(max(1, -(-len(symbols) * minutes // 10_000)))
        raw = self._fetch_raw(list(symbols), start, end, self.feed)
        frame = _minute_frame_from_alpaca_raw(raw)
        if frame.empty:
            return frame
        ts = pd.to_datetime(frame["timestamp"], utc=True)
        return frame[(ts >= start) & (ts < end)].reset_index(drop=True)


class SessionBars:
    """Minute bars of one session, visible only up to the current decision time."""

    def __init__(self, provider: MinuteProvider, symbols: Sequence[str], session: date):
        self.provider = provider
        self.symbols = tuple(dict.fromkeys(symbols))
        self.session = session
        self.open_ts, self.close_ts = session_bounds(session)
        self.minute = pd.DataFrame(columns=MINUTE_COLUMNS)
        self.as_of: pd.Timestamp | None = None

    @property
    def feed(self) -> str:
        return self.provider.feed

    def refresh(self, as_of: pd.Timestamp) -> None:
        """Load bars whose minute has fully closed by ``as_of`` (bar start + 1 min <= as_of)."""
        end = min(as_of, self.close_ts)
        start = self.open_ts
        keep = self.minute.iloc[0:0]
        if getattr(self.provider, "incremental", False) and not self.minute.empty:
            # re-read the last 5 minutes (late or corrected bars), keep everything older
            start = max(
                self.open_ts,
                pd.to_datetime(self.minute["timestamp"], utc=True).max() - pd.Timedelta(minutes=5),
            )
            old = pd.to_datetime(self.minute["timestamp"], utc=True)
            keep = self.minute[old < start]
        frame = self.provider.fetch(self.symbols, start, end)
        if not frame.empty:
            ts = pd.to_datetime(frame["timestamp"], utc=True)
            frame = frame[(ts >= self.open_ts) & (ts + pd.Timedelta(minutes=1) <= as_of)]
        if not keep.empty:
            frame = pd.concat([keep, frame], ignore_index=True) if not frame.empty else keep
        self.minute = frame.reset_index(drop=True) if not frame.empty else self.minute.iloc[0:0]
        self.as_of = as_of

    def aggregated(self, timeframe: str, symbols: Sequence[str]) -> pd.DataFrame:
        frame = self.minute[self.minute["symbol"].isin(list(symbols))]
        if frame.empty or self.as_of is None:
            return pd.DataFrame(
                columns=["symbol", "bar_close_ts", "open", "high", "low", "close", "volume", "feed"]
            )
        out = aggregate_regular_session(frame, timeframe)
        out = out[out["bar_close_ts"] <= self.as_of].copy()
        out["feed"] = self.feed
        return out.sort_values(["symbol", "bar_close_ts"], kind="mergesort").reset_index(drop=True)

    def last_prices(self) -> dict[str, float]:
        if self.minute.empty:
            return {}
        last = self.minute.sort_values("timestamp").groupby("symbol").tail(1)
        return {str(r.symbol): float(r.close) for r in last.itertuples()}

    def price_at_or_after(self, symbol: str, ts: pd.Timestamp) -> float | None:
        """Open of the first minute bar starting at/after ``ts`` (replay fills; reads the
        provider, i.e. the future of the decision -- only the simulator may call this)."""
        frame = self.provider.fetch([symbol], self.open_ts, self.close_ts)
        if frame.empty:
            return None
        stamps = pd.to_datetime(frame["timestamp"], utc=True)
        later = frame[stamps >= ts]
        if later.empty:
            return float(frame.iloc[-1]["close"])
        return float(later.sort_values("timestamp").iloc[0]["open"])

    def latest_minute(self) -> dict[str, pd.Timestamp]:
        """Start of the newest completed minute bar per symbol."""
        if self.minute.empty:
            return {}
        ts = pd.to_datetime(self.minute["timestamp"], utc=True)
        return {str(k): v for k, v in ts.groupby(self.minute["symbol"]).max().items()}

    def counts(self) -> dict[str, int]:
        if self.minute.empty:
            return {}
        return {str(k): int(v) for k, v in self.minute.groupby("symbol").size().items()}


def load_history(
    provider: MinuteProvider, symbols: Sequence[str], session: date, days: int
) -> pd.DataFrame:
    """Regular-session minute bars of the ``days`` sessions strictly before ``session``."""
    if days <= 0:
        return pd.DataFrame(columns=MINUTE_COLUMNS)
    day = session
    for _ in range(days):
        day = previous_us_equity_session(day)
    start = pd.Timestamp(datetime.combine(day, time(0, 0), tzinfo=NEW_YORK)).tz_convert("UTC")
    end = pd.Timestamp(datetime.combine(session, time(0, 0), tzinfo=NEW_YORK)).tz_convert("UTC")
    frame = provider.fetch(list(symbols), start, end)
    if frame.empty:
        return frame
    local = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert(NEW_YORK)
    minutes = local.dt.hour * 60 + local.dt.minute
    keep = (minutes >= 570) & (minutes < 960) & (local.dt.date < session)
    return frame[keep].reset_index(drop=True)


class FrameMinuteProvider:
    """Minute provider over an in-memory frame (recorded live bars, simulated feeds, tests)."""

    def __init__(self, frame: pd.DataFrame, feed: str):
        self.frame = frame
        self.feed = feed

    def fetch(self, symbols, start, end):
        if self.frame.empty:
            return self.frame
        ts = pd.to_datetime(self.frame["timestamp"], utc=True)
        keep = self.frame["symbol"].isin(list(symbols)) & (ts >= start) & (ts < end)
        return self.frame[keep].reset_index(drop=True)
