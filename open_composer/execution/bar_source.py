"""``BarSource``: one bar-fetch contract for every timeframe and provider.

Step 14 plan (``docs/plan-step-14-timeframe-agnostic-bar-cycle-runner-2026-09-11.zh.md``
section 1). ``SignalEngine`` and ``BarCycleRunner`` (``scripts/run_bar_cycle.py``)
never special-case a data source or a timeframe: every ``BarSource`` returns
the same schema (:data:`BAR_COLUMNS`), and point-in-time (PIT) truncation
(``as_of``) is enforced identically for both implementations below.

* :class:`ArchiveBarSource` -- the historical/backfilled path: SIP daily bars
  from ``data/sip/daily`` directly, SIP minute bars from ``data/sip/minute``
  aggregated through :func:`open_composer.research.bars.hourly.aggregate_regular_session`
  for every intraday timeframe (**reused**, not reimplemented -- see that
  module). This is what ``--as-of`` historical replay reads.
* :class:`AlpacaBarSource` -- the live tail: today's session, before the
  nightly archive update lands. Always fetches Alpaca's native 1-minute bars
  and daily bars, never Alpaca's native "1Hour"/"4Hour" bars directly -- so
  the *exact same* :func:`aggregate_regular_session` bucket convention
  (09:30-anchored, DST-safe) applies to both the archive and the live tail,
  and a 1h/4h bucket never silently means two different things depending on
  which source produced it. The account's configured feed
  (``open_composer.config.data_feed()``, default ``sip`` since Step 10 --
  never assume ``iex``) is disclosed in the output's ``feed`` column either
  way.

Both sources refuse ``session`` values other than ``"regular"`` (extended
hours are out of scope, matching this repo's existing Reversal Trend/hourly
bar convention).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.config import data_feed, project_root
from open_composer.market_calendar import NEW_YORK, us_equity_session_close
from open_composer.research.bars.hourly import (
    TIMEFRAME_BUCKET_MINUTES,
    aggregate_regular_session,
)

#: The BarSource protocol's required output columns (Step 14 plan section 1:
#: "DataFrame[symbol, bar_close_ts(UTC), open, high, low, close, volume]").
#: Implementations may append extra informational columns (this module keeps
#: ``timestamp``=bucket start, ``feed``, ``trade_count``, ``vwap`` when
#: available) but these seven, in this order, are always present first.
BAR_COLUMNS = ("symbol", "bar_close_ts", "open", "high", "low", "close", "volume")


class BarSourceError(RuntimeError):
    """Raised when a BarSource cannot satisfy a request."""


class BarSource(Protocol):
    """``get_bars(symbols, timeframe, start, end, *, session="regular",
    as_of) -> DataFrame[symbol, bar_close_ts(UTC), open, high, low, close,
    volume]``, sorted by ``(symbol, bar_close_ts)``. Every bar with
    ``bar_close_ts > as_of`` is excluded (point-in-time truncation): a bar is
    never visible before it has actually closed, regardless of how far
    ``end`` reaches.
    """

    def get_bars(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime | date | pd.Timestamp,
        end: datetime | date | pd.Timestamp,
        *,
        session: str = "regular",
        as_of: datetime | date | pd.Timestamp | None = None,
    ) -> pd.DataFrame: ...


@dataclass(frozen=True)
class ArchiveBarSource:
    """Reads the local SIP archive (``data/sip/daily``, ``data/sip/minute``)
    via :func:`open_composer.adapters.data.sip_parquet.load_sip_bars`.
    ``timeframe="daily"`` reads the daily shard directly; every intraday
    timeframe in :data:`open_composer.research.bars.hourly.TIMEFRAME_BUCKET_MINUTES`
    (1m/5m/15m/30m/1h/4h) aggregates the minute shard through
    :func:`open_composer.research.bars.hourly.aggregate_regular_session`.
    ``weekly`` is not supported (no session-anchoring rule defined for it
    yet; out of scope for this generalization).

    A window whose ``start``/``end`` falls mid-session (rather than on a
    session boundary) can produce a partial first/last bucket, exactly like
    :func:`aggregate_regular_session` itself -- this source never fabricates
    a full bucket from partial data. Callers that need whole-session buckets
    (every caller in this codebase today) should request from a date
    boundary, not a mid-day timestamp.
    """

    root: Path | None = None

    def _sip_root(self) -> Path:
        return self.root if self.root is not None else project_root() / "data" / "sip"

    def get_bars(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime | date | pd.Timestamp,
        end: datetime | date | pd.Timestamp,
        *,
        session: str = "regular",
        as_of: datetime | date | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        _require_regular_session(session)
        symbol_list = _normalize_symbols(symbols)
        start_ts = _to_utc_timestamp(start)
        end_ts = _to_utc_timestamp(end)
        as_of_ts = _to_utc_timestamp(as_of) if as_of is not None else end_ts
        root = self._sip_root()

        if timeframe == "daily":
            frame = self._daily_bars(root, symbol_list, start_ts, end_ts)
        elif timeframe in TIMEFRAME_BUCKET_MINUTES:
            frame = self._intraday_bars(root, symbol_list, timeframe, start_ts, end_ts)
        else:
            supported = ", ".join([*sorted(TIMEFRAME_BUCKET_MINUTES), "daily"])
            raise BarSourceError(
                f"ArchiveBarSource does not support timeframe={timeframe!r}; supported: {supported}"
            )
        frame["feed"] = "sip"
        return _apply_pit_and_schema(frame, as_of_ts)

    def _daily_bars(
        self, root: Path, symbols: list[str], start_ts: pd.Timestamp, end_ts: pd.Timestamp
    ) -> pd.DataFrame:
        raw = load_sip_bars(
            symbols,
            frequency="daily",
            start=start_ts,
            end=end_ts,
            root=root,
            allow_missing=True,
        )
        if raw.empty:
            return pd.DataFrame(columns=[*BAR_COLUMNS, "timestamp"])
        working = raw.copy()
        # Matches the existing convention in
        # open_composer.adapters.execution.model_ranking_target_weights.
        # _sip_closes_on_or_before: the SIP daily archive's own ``timestamp``
        # is stored at local midnight America/New_York, so its UTC calendar
        # date is already the trading day -- no NY tz-conversion needed to
        # recover it.
        trade_dates = pd.to_datetime(working["timestamp"], utc=True).dt.date
        working["bar_close_ts"] = [_daily_close_utc(day) for day in trade_dates]
        return working

    def _intraday_bars(
        self,
        root: Path,
        symbols: list[str],
        timeframe: str,
        start_ts: pd.Timestamp,
        end_ts: pd.Timestamp,
    ) -> pd.DataFrame:
        minute_bars = load_sip_bars(
            symbols,
            frequency="minute",
            start=start_ts,
            end=end_ts,
            root=root,
            allow_missing=True,
        )
        if minute_bars.empty:
            return pd.DataFrame(columns=[*BAR_COLUMNS, "timestamp", "trade_count", "vwap"])
        return aggregate_regular_session(minute_bars, timeframe)


#: Injected-fetch signature used by :class:`AlpacaBarSource` (also the shape
#: of :func:`_fetch_alpaca_raw_bars`, the real implementation) -- tests
#: substitute a synthetic callable here instead of hitting the network.
RawAlpacaFetch = Callable[[list[str], str, pd.Timestamp, pd.Timestamp, str], pd.DataFrame]


@dataclass(frozen=True)
class AlpacaBarSource:
    """Live-tail bars from Alpaca market data v2, always fetched as native
    1-minute (intraday timeframes) or native daily bars, then run through
    the exact same session-aggregation :class:`ArchiveBarSource` uses --
    see the module docstring for why. ``feed`` defaults to
    ``open_composer.config.data_feed()`` (``sip`` unless the environment
    overrides it); the resolved feed is always disclosed in the output.
    """

    root: Path | None = None
    feed: str | None = None
    #: Test injection point; defaults to :func:`_fetch_alpaca_raw_bars` (a
    #: real Alpaca SDK call) when ``None``.
    fetch_raw_bars: RawAlpacaFetch | None = None

    def get_bars(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime | date | pd.Timestamp,
        end: datetime | date | pd.Timestamp,
        *,
        session: str = "regular",
        as_of: datetime | date | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        _require_regular_session(session)
        symbol_list = _normalize_symbols(symbols)
        start_ts = _to_utc_timestamp(start)
        end_ts = _to_utc_timestamp(end)
        as_of_ts = _to_utc_timestamp(as_of) if as_of is not None else end_ts
        resolved_feed = self.feed or data_feed()
        fetch = self.fetch_raw_bars or _fetch_alpaca_raw_bars

        if timeframe == "daily":
            raw = fetch(symbol_list, "1Day", start_ts, end_ts, resolved_feed)
            frame = _daily_frame_from_alpaca_raw(raw)
        elif timeframe in TIMEFRAME_BUCKET_MINUTES:
            raw = fetch(symbol_list, "1Min", start_ts, end_ts, resolved_feed)
            minute_frame = _minute_frame_from_alpaca_raw(raw)
            frame = (
                aggregate_regular_session(minute_frame, timeframe)
                if not minute_frame.empty
                else pd.DataFrame(columns=[*BAR_COLUMNS, "timestamp", "trade_count", "vwap"])
            )
        else:
            supported = ", ".join([*sorted(TIMEFRAME_BUCKET_MINUTES), "daily"])
            raise BarSourceError(
                f"AlpacaBarSource does not support timeframe={timeframe!r}; supported: {supported}"
            )
        frame["feed"] = resolved_feed
        return _apply_pit_and_schema(frame, as_of_ts)


def _fetch_alpaca_raw_bars(
    symbols: list[str],
    alpaca_timeframe: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    feed: str,
) -> pd.DataFrame:
    """Real Alpaca market-data v2 fetch (lazy SDK import, matching the
    lazy-import convention already used by
    ``open_composer.adapters.data.alpaca._alpaca_timeframe``). Deliberately
    does not reuse ``fetch_alpaca_bars`` from that module: this source needs
    the SDK's raw ``trade_count``/``vwap`` columns (dropped by that
    function's OHLCV-only cache/manifest path) and a genuine multi-symbol
    batch request, not that function's single-symbol CSV-cache contract.
    """
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    from open_composer.config import alpaca_api_key_id, alpaca_api_secret_key

    timeframe_map = {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "1Day": TimeFrame(1, TimeFrameUnit.Day),
    }
    if alpaca_timeframe not in timeframe_map:
        raise BarSourceError(f"unsupported Alpaca timeframe: {alpaca_timeframe}")
    request = StockBarsRequest(
        symbol_or_symbols=list(symbols),
        timeframe=timeframe_map[alpaca_timeframe],
        start=start.to_pydatetime(),
        end=end.to_pydatetime(),
        feed=DataFeed(feed),
    )
    client = StockHistoricalDataClient(
        api_key=alpaca_api_key_id(),
        secret_key=alpaca_api_secret_key(),
    )
    response = client.get_stock_bars(request)
    frame = response.df
    if frame is None or frame.empty:
        return pd.DataFrame()
    return frame.reset_index()


def _minute_frame_from_alpaca_raw(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(
            columns=[
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
        )
    working = raw.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
    for column in ("open", "high", "low", "close", "volume"):
        working[column] = pd.to_numeric(working[column], errors="raise")
    # Alpaca's bar schema carries trade_count/vwap; fall back to a disclosed
    # approximation (0 trades, vwap=close) only if a caller's SDK/response
    # genuinely lacks them -- aggregate_regular_session requires the columns
    # to exist, but nothing downstream of it (compute_reversal_trend, the
    # admission/cost machinery) reads this source's vwap/trade_count values,
    # only its own recomputed bucket vwap for disclosure.
    if "trade_count" not in working.columns:
        working["trade_count"] = 0.0
    if "vwap" not in working.columns:
        working["vwap"] = working["close"]
    return working[
        ["symbol", "timestamp", "open", "high", "low", "close", "volume", "trade_count", "vwap"]
    ]


def _daily_frame_from_alpaca_raw(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=[*BAR_COLUMNS, "timestamp"])
    working = raw.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
    for column in ("open", "high", "low", "close", "volume"):
        working[column] = pd.to_numeric(working[column], errors="raise")
    trade_dates = working["timestamp"].dt.tz_convert(NEW_YORK).dt.date
    working["bar_close_ts"] = [_daily_close_utc(day) for day in trade_dates]
    return working[
        ["symbol", "timestamp", "bar_close_ts", "open", "high", "low", "close", "volume"]
    ]


def _daily_close_utc(trade_date: date) -> pd.Timestamp:
    close_time = us_equity_session_close(trade_date)
    if close_time is None:
        return pd.NaT
    return pd.Timestamp(datetime.combine(trade_date, close_time, tzinfo=NEW_YORK)).tz_convert("UTC")


def _require_regular_session(session: str) -> None:
    if session != "regular":
        raise BarSourceError(
            f"only session='regular' is supported (extended hours are out of scope), got "
            f"{session!r}"
        )


def _normalize_symbols(symbols: Sequence[str]) -> list[str]:
    normalized = [str(symbol).strip().upper() for symbol in symbols]
    normalized = [symbol for symbol in normalized if symbol]
    if not normalized:
        raise BarSourceError("get_bars requires at least one symbol")
    # De-dupe, preserve order.
    return list(dict.fromkeys(normalized))


def _to_utc_timestamp(value: datetime | date | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _apply_pit_and_schema(frame: pd.DataFrame, as_of_ts: pd.Timestamp) -> pd.DataFrame:
    """Drop every bar whose ``bar_close_ts`` is strictly after ``as_of_ts``
    (a bar is never visible before it has closed), then order columns with
    :data:`BAR_COLUMNS` first.
    """
    if frame.empty:
        return pd.DataFrame(columns=list(BAR_COLUMNS))
    working = frame.dropna(subset=["bar_close_ts"]).copy()
    working = working.loc[working["bar_close_ts"] <= as_of_ts]
    working = working.sort_values(["symbol", "bar_close_ts"], kind="mergesort").reset_index(
        drop=True
    )
    ordered = [c for c in BAR_COLUMNS if c in working.columns]
    extra = [c for c in working.columns if c not in BAR_COLUMNS]
    return working.loc[:, [*ordered, *extra]]
