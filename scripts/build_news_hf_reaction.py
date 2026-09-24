"""H-20260923-14: signed high-frequency news-return, per (symbol, trade_date).

Direction ``dir:high_freq_news_return_underreaction_drift``
(``reports/research/harvest/directions.jsonl``), evidence
``reports/research/intel/I-20260923-07-owner-five-directions-wave.md`` section 4.
Construction follows Jiang, Li and Wang, "Pervasive underreaction: evidence from
high-frequency data" (Journal of Financial Economics 141, 2021), read from the
authors' own 2019-08-06 SSRN/conference draft "News Momentum" (the pre-JFE
title; same construction, same authors, same M=26 decomposition -- the paper
that was actually opened for this build; see
``reports/research/iterations/h20260923_14_news_hf_reaction/sources/``).
Quotes below are from that draft unless noted.

Paper construction, pinned
---------------------------
* Sample: NYSE/NASDAQ/AMEX common stocks (share code 10/11) with at least one
  Dow Jones Newswire story (RavenPack, relevance score 100, event novelty
  score 100 -- i.e. fresh news only), March 2000-October 2012, price >= $1 at
  formation. "A typical day has an average of 3,781 firms covered by news
  stories" but "only firms with news arrivals on day t enter into portfolio
  formation" (~280 firms/day).
* High-frequency window: "we compute intraday returns as every 15-minute
  return between 9:45 a.m. and 4:00 p.m. and the overnight return as the
  return between 4:00 p.m. on the previous trading day and 9:45 a.m. on the
  current trading day" -- footnote: "We use the price at 9:45 a.m. for
  overnight returns to ensure that most stocks have traded at least once after
  the market open." That is M=26 intervals/day: 1 overnight + 25 intraday
  15-minute intervals (9:45-10:00, ..., 15:45-16:00).
* News-to-interval classification: "For news occurring within regular trading
  hours, the news return is simply the 15-minute return over the same period
  that the news occurs. For news occurring during the weekend, holiday, or
  overnight, the news return is the nearest subsequent overnight return ... For
  example, the return for news events during the weekend is the return over the
  period of 4:00 p.m. of the surrounding Friday and 9:45 a.m. of the
  surrounding Monday."
* Daily aggregation (their eq. 1): "we aggregate all news and non-news returns
  within each day starting from 4:00 p.m. on day t-1 to 4:00 p.m. on day t to
  form daily news and non-news returns" by compounding: R_news = prod(1+r_j :
  j has news) - 1, R_nonnews = prod(1+r_j : j has no news) - 1, over the day's
  26 intervals; R_overall = (1+R_news)(1+R_nonnews) - 1 by construction (the
  intervals partition the day exactly once).
* Sort/holding/weighting: "At the 4:00 p.m. market close of each trading day
  t, we sort stocks into decile portfolios based on their news returns on day
  t ... equal-weighted returns for each decile portfolio and a self-financing
  strategy that buys stocks in the top decile ... and sells stocks in the
  bottom decile ... with a one-week holding period until market close of day
  t+5", overlapping cohorts (Jegadeesh-Titman 1993 style, 1/5 revised daily).
* Reported magnitude (their sample, gross of costs): decile 1 (losers)
  -0.78%/month, decile 10 (winners) +2.55%/month, high-low spread 3.34%/month
  (t=11.72), four-factor (FFC4) alpha 3.37%/month (t=11.76), ~40%/yr,
  Sharpe ~3.29. This draft's text does not itself state a transaction-cost
  scenario; the ~18bp/~1.37%-net-of-cost figure carried in
  ``reports/research/harvest/directions.jsonl`` for this direction is the
  registry's own prior characterization (from the published JFE abstract/
  citing sources), not re-verified against a page of this draft -- flagged
  here rather than silently repeated as directly read.

What our data forces us to change
----------------------------------
* No TAQ tick data / RavenPack relevance-100 filter: we use Alpaca/Benzinga
  ``data/features/news_packets`` (~685k articles, 2024+), which already has
  one story per event (no explicit novelty/relevance score); we reuse this
  project's own fanout filter (:data:`MAX_SYMBOL_FANOUT` from
  ``news_attention.py``, articles naming 0 or >10 symbols dropped as
  roundups/unattributable) rather than RavenPack's ENS/relevance fields, which
  we do not have.
* 15-minute intervals here are built from 1-minute SIP bars (not TAQ ticks
  cleaned per Barndorff-Nielsen et al. 2009): an interval's anchor price is the
  close of the last available 1-minute bar at or before that interval's right
  boundary (a discrete analog of "the price at 9:45am"), forward-carried
  across any bar gaps within the session. No microstructure/kernel cleaning is
  applied.
* News-item timestamp used is ``visible_at`` (this project's PIT visibility
  timestamp: first moment the article was publicly retrievable), not a
  RavenPack recorded time; see ``news_attention.py`` for why this is the only
  visibility timestamp this archive supports.
* SIP minute closes were checked empirically (NVDA 2024-06-07 -> 2024-06-10,
  its 10:1 split date) and are continuous across the split, i.e. this archive
  is already split-adjusted; no separate CRSP-style adjustment is applied.
* Point-in-time cutoff: a stock-day's ``news_return`` here is exactly the
  paper's day-t bundle (previous close 16:00 -> today's 16:00), which is fully
  known by today's regular-session close -- a signal card enters at the next
  session's open, one session later, never on the news day itself.

Output
------
``data/features/news_hf_reaction/{year}.parquet``, one row per
(symbol, trade_date) that had >= 1 attributed news item that day (sparse,
matching the paper's "only firms with news arrivals ... enter"):
``symbol, trade_date, news_return, non_news_return, overall_return, n_news,
n_windows, visible_at``. ``visible_at`` is the latest (max) visible_at among
the news items attributed to that row -- a diagnostic, not a timing input
(``trade_date`` already encodes the point-in-time cutoff).

Runs month by month; ``data/features/news_hf_reaction/_checkpoints/
{year}-{month:02d}.parquet`` is the per-month checkpoint, and each year's
output file is rebuilt from whatever checkpoints exist for that year after
every month, so a stopped run resumes (re-running a month whose checkpoint
exists is a no-op unless ``--force``) and partial years are always inspectable
on disk::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/build_news_hf_reaction.py build \\
        --start 2025-01 --end 2026-09 \\
        > /tmp/news_hf_reaction.log 2>&1 &
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.market_calendar import us_equity_session_dates  # noqa: E402
from open_composer.research.features.news_attention import (  # noqa: E402
    MAX_SYMBOL_FANOUT,
    NEWS_PACKETS_ROOT,
)

NEW_YORK = ZoneInfo("America/New_York")

OUT_ROOT = ROOT / "data" / "features" / "news_hf_reaction"
CHECKPOINT_DIRNAME = "_checkpoints"
SIP_MINUTE_ROOT = ROOT / "data" / "sip" / "minute"

#: Regular session, matching ``sip_parquet.py`` / ``intraday_daily.py``.
REGULAR_SESSION_START = "09:30:00"
REGULAR_SESSION_END = "16:00:00"

#: Clock-minute-of-day (ET, 0..1439) constants for the paper's grid.
SESSION_OPEN_MINUTE = 9 * 60 + 30  # 09:30
OVERNIGHT_ANCHOR_MINUTE = 9 * 60 + 45  # 09:45 -- end of the overnight interval
SESSION_CLOSE_MINUTE = 16 * 60  # 16:00 -- end of the last intraday interval
INTERVAL_MINUTES = 15
N_INTRADAY_BUCKETS = (SESSION_CLOSE_MINUTE - OVERNIGHT_ANCHOR_MINUTE) // INTERVAL_MINUTES  # 25
OVERNIGHT_BUCKET = -1
LAST_BUCKET = N_INTRADAY_BUCKETS - 1  # 24
BUCKET_COUNT = N_INTRADAY_BUCKETS + 1  # 26, i.e. paper's M

OUTPUT_COLUMNS = (
    "symbol",
    "trade_date",
    "news_return",
    "non_news_return",
    "overall_return",
    "n_news",
    "n_windows",
    "visible_at",
)

FORWARD_LOOKAHEAD_DAYS = 10  # enough calendar days to cross any weekend+holiday
BACKWARD_LOOKBACK_DAYS = 10  # enough to find the prior trading session

DEFAULT_MEMORY_LIMIT = "1400MB"


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


# --------------------------------------------------------------------------- calendar


def bucket_for_minute_of_day(minute_of_day: int) -> int:
    """Half-open, left-closed 15-minute bucket for a minute-of-day in
    ``[OVERNIGHT_ANCHOR_MINUTE, SESSION_CLOSE_MINUTE)`` -- ``0`` is
    ``[9:45, 10:00)``, ``24`` is ``[15:45, 16:00)``. Callers must range-check;
    this is undefined (and not range-checked) outside that domain.
    """
    return min(LAST_BUCKET, (minute_of_day - OVERNIGHT_ANCHOR_MINUTE) // INTERVAL_MINUTES)


def price_bucket_for_minute_of_day(minute_of_day: int) -> int:
    """Which anchor-price bucket a *bar* at this minute-of-day contributes to.

    Right-inclusive, unlike :func:`bucket_for_minute_of_day`: bucket ``-1``
    (the 9:45 anchor) is anything in ``(-inf, 9:45]``, bucket ``k`` is
    ``(9:45+15k, 9:45+15(k+1)]`` -- a bar trading exactly on a boundary (e.g.
    10:00:00) belongs to the bucket *ending* there, not the one starting
    there, because each bucket's anchor price is the *last* bar's close at or
    before its right edge (see :func:`anchor_prices_from_minute_bars`), and a
    trade at exactly 10:00:00 is a valid "price at or before 10:00" anchor.
    News-interval classification is the mirror-image left-closed convention
    (:func:`bucket_for_minute_of_day`) because there a timestamp is being
    placed *into* the interval it starts, not used to anchor the interval's
    end.
    """
    if minute_of_day <= OVERNIGHT_ANCHOR_MINUTE:
        return OVERNIGHT_BUCKET
    offset = minute_of_day - OVERNIGHT_ANCHOR_MINUTE
    bucket = -(-offset // INTERVAL_MINUTES) - 1  # ceiling division
    return min(LAST_BUCKET, bucket)


def session_anchor_utc(trade_date: pd.Timestamp, minute_of_day: int) -> pd.Timestamp:
    """UTC timestamp of a given ET minute-of-day on ``trade_date``."""
    local = pd.Timestamp(trade_date.date()).tz_localize(NEW_YORK) + pd.Timedelta(
        minutes=minute_of_day
    )
    return local.tz_convert("UTC")


def session_calendar(start: date, end: date) -> pd.DataFrame:
    """One row per US equity session in ``[start, end]``: ``trade_date`` (tz
    -naive midnight Timestamp), ``anchor_945_utc`` and ``anchor_1600_utc``
    (both tz-aware UTC) -- the two boundary instants every interval in the
    grid is built from.
    """
    sessions = us_equity_session_dates(start, end)
    trade_dates = pd.DatetimeIndex([pd.Timestamp(d) for d in sessions])
    return pd.DataFrame(
        {
            "trade_date": trade_dates,
            "anchor_945_utc": [session_anchor_utc(d, OVERNIGHT_ANCHOR_MINUTE) for d in trade_dates],
            "anchor_1600_utc": [session_anchor_utc(d, SESSION_CLOSE_MINUTE) for d in trade_dates],
        }
    )


# --------------------------------------------------------------------------- news attribution


def attribute_news(visible_at: pd.Series, calendar: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """For each ``visible_at`` (tz-aware UTC), the ``(trade_date, bucket)`` it
    belongs to under the paper's rule.

    Regular-hours news (ET minute-of-day in ``[9:45, 16:00)`` on a session
    day) attributes to that session's own intraday bucket. Everything else
    (before 9:45 on a session day, at/after 16:00, a weekend, or a holiday)
    is "the nearest subsequent overnight return": the first session in
    ``calendar`` whose 9:45 anchor is strictly after ``visible_at``, bucket
    ``OVERNIGHT_BUCKET``. Rows for which ``calendar`` has no session far
    enough forward (or, for same-day intraday attribution, no matching
    session at all) get ``pd.NaT`` / ``-99`` and must be dropped by the
    caller -- this is a calendar-coverage gap (not enough lookahead), not a
    valid overnight attribution.
    """
    visible_at = pd.to_datetime(visible_at, utc=True).reset_index(drop=True)
    et = visible_at.dt.tz_convert(NEW_YORK)
    minute_of_day = (et.dt.hour * 60 + et.dt.minute).astype("int64")
    et_date = pd.DatetimeIndex(et.dt.tz_localize(None).dt.normalize())

    session_index = pd.DatetimeIndex(calendar["trade_date"])
    session_dates = session_index.to_numpy()
    # position of the session sharing today's calendar date, if any (-1 if
    # today is not itself a session, e.g. a weekend/holiday timestamp).
    same_session_pos = session_index.get_indexer(et_date)
    is_intraday = (
        (same_session_pos >= 0)
        & (minute_of_day.to_numpy() >= OVERNIGHT_ANCHOR_MINUTE)
        & (minute_of_day.to_numpy() < SESSION_CLOSE_MINUTE)
    )

    # First session whose 9:45 anchor is strictly after visible_at: searching
    # with side="right" gives the count of anchors <= visible_at, i.e. the
    # index of the first anchor strictly greater -- exactly "the nearest
    # subsequent overnight return"'s owning session.
    anchors_945 = pd.DatetimeIndex(calendar["anchor_945_utc"])
    overnight_pos = anchors_945.searchsorted(pd.DatetimeIndex(visible_at), side="right")
    overnight_in_range = overnight_pos < len(calendar)
    overnight_pos_safe = np.where(overnight_in_range, overnight_pos, 0)

    chosen_pos = np.where(is_intraday, np.clip(same_session_pos, 0, None), overnight_pos_safe)
    valid = is_intraday | overnight_in_range
    trade_date = pd.Series(session_dates[np.clip(chosen_pos, 0, len(session_dates) - 1)])
    trade_date[~valid] = pd.NaT

    intraday_bucket = np.array(
        [bucket_for_minute_of_day(m) for m in minute_of_day.to_numpy()], dtype=np.int64
    )
    bucket = np.where(
        is_intraday, intraday_bucket, np.where(overnight_in_range, OVERNIGHT_BUCKET, -99)
    )
    return trade_date.to_numpy(), bucket.astype(np.int64)


def explode_news_events(news: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """``news`` (``id, symbols, visible_at``) exploded one row per (article,
    symbol), attributed to ``(trade_date, bucket)``. Articles with 0 or more
    than :data:`MAX_SYMBOL_FANOUT` symbols are dropped (roundups /
    unattributable, matching ``news_attention.py``'s own rule). Rows with no
    calendar coverage (see :func:`attribute_news`) are dropped.
    """
    fanout = news["symbols"].map(len)
    kept = news[(fanout >= 1) & (fanout <= MAX_SYMBOL_FANOUT)]
    if kept.empty:
        return pd.DataFrame(columns=["article_id", "symbol", "visible_at", "trade_date", "bucket"])
    exploded = kept[["id", "visible_at", "symbols"]].explode("symbols")
    exploded = exploded.rename(columns={"id": "article_id", "symbols": "symbol"})
    trade_date, bucket = attribute_news(exploded["visible_at"], calendar)
    exploded = exploded.assign(trade_date=trade_date, bucket=bucket)
    return exploded[exploded["trade_date"].notna() & (exploded["bucket"] != -99)][
        ["article_id", "symbol", "visible_at", "trade_date", "bucket"]
    ].reset_index(drop=True)


# --------------------------------------------------------------------------- price anchors


def minute_shard_paths(year: int, month: int) -> list[str]:
    """Shard files for one (year, month). ``sip_parquet.py``'s own docstring
    documents two layouts: ``{year}/shard-NNNN.parquet`` ("legacy whole-year
    layout") and ``{year}/{month}/shard-NNNN.parquet`` ("current
    month-sharded layout"), and its own ``_finalize`` explicitly dedupes
    because "the whole-year and month-sharded minute layouts overlap" -- i.e.
    the two layouts hold the *same* bars, not complementary halves. An
    earlier version of this function unconditionally read both and combined
    them, which is correct for correctness but was measured (2026-09-23, a
    2024-01 build run) to pull in the *entire* legacy 2023 archive --
    301.7M rows / 8,227 symbols spanning all of Jan-Dec 2023 -- merely to
    resolve December 2023's overnight anchor for a January build, instead of
    December's own 19.09M-row / 6,120-symbol per-month shard set; that 15x
    over-read is what drove the memory-capped build's OOM-kill (cgroup
    anon-rss hit the 1.8GB MemoryMax after 11+ minutes of CPU with zero
    checkpoints written). This function therefore prefers the month
    directory and only falls back to the (expensive, whole-year) legacy glob
    when no month directory exists at all for that year.

    CORRECTION 2026-09-24: the 2023 month directories do NOT duplicate the
    legacy shards. They are missing roughly a quarter to 40% of 2023
    symbol-days; for example, AAPL and AMD have no rows in any September-2023
    month shard but are in the legacy ``2023/shard-0001.parquet``. This was
    found by the h20260923_13 ORB engine, which now unions the two layouts
    per (symbol, session). For builds from 2024-01 on, 2023 is read only
    for the overnight anchor of the first 2024 session, so the loss is a
    handful of 2024-01-02 events. Do not build 2023 months with this
    function until it unions the legacy shards (date- and symbol-filtered,
    then deduplicated).
    """
    year_dir = SIP_MINUTE_ROOT / str(year)
    month_dir = year_dir / f"{month:02d}"
    if month_dir.is_dir():
        if year == 2023:
            log(
                "WARNING minute_shard_paths: 2023 month shards are incomplete (legacy "
                f"whole-year shards hold symbols they lack); {year}-{month:02d} may miss symbols"
            )
        return sorted(str(p) for p in month_dir.glob("shard-*.parquet"))
    if year_dir.is_dir():
        return sorted(str(p) for p in year_dir.glob("shard-*.parquet"))
    return []


def anchor_prices_from_minute_bars(
    shard_paths: list[str],
    symbols: list[str],
    *,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """One row per ``(symbol, trade_date, price_bucket)`` with the close of
    the last regular-session 1-minute bar in that bucket -- see
    :func:`price_bucket_for_minute_of_day`. Restricted to ``symbols`` so the
    caller only ever reads the slice of the archive it needs.

    Runs as a single DuckDB aggregation query (mirrors
    ``intraday_daily.py``'s memory-safety pattern: capped ``memory_limit``,
    ``threads=2``, ``preserve_insertion_order=false``, optional spill
    ``temp_directory``) so raw minute rows are never materialized in pandas;
    only the aggregated (small) result is.
    """
    columns = ["symbol", "trade_date", "price_bucket"]
    if not shard_paths or not symbols:
        return pd.DataFrame(columns=[*columns, "close"])
    owns_connection = con is None
    connection = con or duckdb.connect()
    try:
        connection.execute(f"SET memory_limit='{memory_limit}'")
        connection.execute("SET threads=2")
        connection.execute("SET preserve_insertion_order=false")
        if temp_directory is not None:
            Path(temp_directory).mkdir(parents=True, exist_ok=True)
            connection.execute(f"SET temp_directory='{temp_directory}'")
        connection.register("_symbols", pd.DataFrame({"symbol": symbols}))
        query = f"""
            WITH raw AS (
                SELECT symbol, timestamp, close
                FROM read_parquet({shard_paths!r}, union_by_name=true)
                WHERE symbol IN (SELECT symbol FROM _symbols)
            ),
            timed AS (
                SELECT
                    symbol,
                    timestamp,
                    CAST((timestamp AT TIME ZONE 'America/New_York') AS DATE) AS trade_date,
                    date_part('hour', timestamp AT TIME ZONE 'America/New_York') * 60
                        + date_part('minute', timestamp AT TIME ZONE 'America/New_York')
                        AS minute_of_day,
                    close
                FROM raw
            ),
            session_bars AS (
                SELECT *
                FROM timed
                WHERE minute_of_day >= {SESSION_OPEN_MINUTE}
                  AND minute_of_day < {SESSION_CLOSE_MINUTE}
            ),
            bucketed AS (
                SELECT
                    symbol,
                    trade_date,
                    -- Right-inclusive (ceiling-division) bucketing, mirroring
                    -- price_bucket_for_minute_of_day exactly: a bar trading
                    -- precisely on a 15-minute boundary (e.g. 10:00:00)
                    -- belongs to the bucket ending there, not the next one.
                    -- ``(a + b - 1) // b`` is integer ceiling division for
                    -- positive a, b.
                    CASE
                        WHEN minute_of_day <= {OVERNIGHT_ANCHOR_MINUTE} THEN -1
                        ELSE LEAST(
                            {LAST_BUCKET},
                            (CAST(minute_of_day AS BIGINT) - {OVERNIGHT_ANCHOR_MINUTE}
                                + {INTERVAL_MINUTES} - 1) // {INTERVAL_MINUTES} - 1
                        )
                    END AS price_bucket,
                    timestamp,
                    close
                FROM session_bars
            )
            SELECT
                symbol,
                trade_date,
                price_bucket,
                arg_max(close, timestamp) AS close
            FROM bucketed
            GROUP BY symbol, trade_date, price_bucket
            ORDER BY symbol, trade_date, price_bucket
        """
        frame = connection.execute(query).fetchdf()
    finally:
        if owns_connection:
            connection.close()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame


def session_anchor_table(bucket_prices: pd.DataFrame) -> pd.DataFrame:
    """Pivot :func:`anchor_prices_from_minute_bars` output to one row per
    ``(symbol, trade_date)`` with all 26 anchors (``bucket_-1`` .. ``bucket_24``),
    forward-filled across buckets within the session for any bar gaps (an
    empty bucket's anchor is the last known price at-or-before it, per the
    paper's own 9:45-anchor footnote reasoning extended to every boundary).
    A session with zero regular-session bars anywhere is dropped -- there is
    no anchor to start filling from.
    """
    if bucket_prices.empty:
        return pd.DataFrame(columns=["symbol", "trade_date", *range(-1, N_INTRADAY_BUCKETS)])
    wide = bucket_prices.pivot_table(
        index=["symbol", "trade_date"], columns="price_bucket", values="close"
    )
    wide = wide.reindex(columns=range(-1, N_INTRADAY_BUCKETS))
    wide = wide.ffill(axis=1)
    wide.columns = list(range(-1, N_INTRADAY_BUCKETS))
    return wide.reset_index()


def interval_returns_table(anchor_table: pd.DataFrame) -> pd.DataFrame:
    """Long ``symbol, trade_date, bucket, ret`` frame: ``bucket=-1`` is the
    overnight interval (today's 9:45 anchor vs the *previous available
    session in this table*'s 16:00 anchor, i.e. bucket 24 shifted by one row
    within each symbol -- callers must supply enough lookback sessions for
    the first session of interest to have a valid predecessor, else it is
    correctly ``NaN``, the same "first day has no overnight return"
    convention as ``intraday_daily.py``); ``bucket=0..24`` are the intraday
    15-minute returns.
    """
    if anchor_table.empty:
        return pd.DataFrame(columns=["symbol", "trade_date", "bucket", "ret"])
    t = anchor_table.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    prior_close = t.groupby("symbol")[LAST_BUCKET].shift(1)
    rows = [
        pd.DataFrame(
            {
                "symbol": t["symbol"],
                "trade_date": t["trade_date"],
                "bucket": OVERNIGHT_BUCKET,
                "ret": t[-1] / prior_close - 1.0,
            }
        )
    ]
    for k in range(N_INTRADAY_BUCKETS):
        base = t[-1] if k == 0 else t[k - 1]
        rows.append(
            pd.DataFrame(
                {
                    "symbol": t["symbol"],
                    "trade_date": t["trade_date"],
                    "bucket": k,
                    "ret": t[k] / base - 1.0,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


# --------------------------------------------------------------------------- aggregation


def aggregate_news_return(
    interval_returns: pd.DataFrame, news_events: pd.DataFrame
) -> pd.DataFrame:
    """Compound each ``(symbol, trade_date)``'s 26 interval returns into
    ``news_return`` (product over buckets with >=1 attributed article) and
    ``non_news_return`` (product over the rest); ``overall_return`` is their
    product-of-(1+x), which must equal the plain 16:00-to-16:00 return by
    construction. Only rows with at least one finite interval return AND at
    least one attributed news bucket are kept -- a stock-day with news but no
    tradable bars (or vice versa) is correctly absent, not a zero.
    """
    if interval_returns.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "trade_date",
                "news_return",
                "non_news_return",
                "overall_return",
                "n_windows",
            ]
        )
    news_buckets = news_events[["symbol", "trade_date", "bucket"]].drop_duplicates()
    news_buckets = news_buckets.assign(is_news=True)
    merged = interval_returns.merge(news_buckets, on=["symbol", "trade_date", "bucket"], how="left")
    # The merge only ever introduces True (matched) or NaN (unmatched) into
    # this column, so "not NaN" is exactly "flagged news" without a
    # fillna-driven dtype downcast.
    merged["is_news"] = merged["is_news"].notna()
    merged = merged[merged["ret"].notna()]

    def _compound(group: pd.DataFrame, mask: pd.Series) -> float:
        sub = group.loc[mask, "ret"]
        if sub.empty:
            return np.nan
        return float(np.prod(1.0 + sub.to_numpy()) - 1.0)

    out = []
    for (symbol, trade_date), group in merged.groupby(["symbol", "trade_date"], sort=False):
        n_windows = int(group["is_news"].sum())
        if n_windows == 0:
            continue
        news_ret = _compound(group, group["is_news"])
        nonnews_ret = _compound(group, ~group["is_news"])
        nonnews_component = nonnews_ret if not pd.isna(nonnews_ret) else 0.0
        overall = (1.0 + news_ret) * (1.0 + nonnews_component) - 1.0
        out.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "news_return": news_ret,
                "non_news_return": nonnews_ret,
                "overall_return": overall,
                "n_windows": n_windows,
            }
        )
    return pd.DataFrame(
        out,
        columns=[
            "symbol",
            "trade_date",
            "news_return",
            "non_news_return",
            "overall_return",
            "n_windows",
        ],
    )


def attach_news_counts(agg: pd.DataFrame, news_events: pd.DataFrame) -> pd.DataFrame:
    """Adds ``n_news`` (article count, not window count) and ``visible_at``
    (max, i.e. latest, contributing article timestamp) per (symbol,
    trade_date)."""
    if agg.empty:
        return agg.assign(n_news=pd.Series(dtype="int64"), visible_at=pd.Series(dtype="object"))
    counts = (
        news_events.groupby(["symbol", "trade_date"])
        .agg(n_news=("article_id", "count"), visible_at=("visible_at", "max"))
        .reset_index()
    )
    out = agg.merge(counts, on=["symbol", "trade_date"], how="left")
    return out[list(OUTPUT_COLUMNS)]


# --------------------------------------------------------------------------- orchestration


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end - timedelta(days=1)


def load_news_for_window(start: date, end: date) -> pd.DataFrame:
    """News with ``visible_at`` in ``[start, end]`` (UTC calendar bound,
    padded by the caller), across every ``news_packets`` year file that could
    contain it."""
    glob = str(NEWS_PACKETS_ROOT / "*.parquet")
    con = duckdb.connect()
    try:
        con.execute("SET memory_limit='600MB'")
        con.execute("SET threads=2")
        frame = con.execute(
            f"""
            SELECT id, symbols, visible_at
            FROM read_parquet('{glob}', union_by_name=true)
            WHERE visible_at >= TIMESTAMP '{start.isoformat()}'
              AND visible_at < TIMESTAMP '{(end + timedelta(days=1)).isoformat()}'
            """
        ).fetchdf()
    finally:
        con.close()
    frame["visible_at"] = pd.to_datetime(frame["visible_at"], utc=True)
    frame["symbols"] = frame["symbols"].apply(lambda arr: list(arr) if arr is not None else [])
    return frame


def process_month(
    year: int,
    month: int,
    *,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
) -> pd.DataFrame:
    """Full pipeline for one output month: news attribution -> price anchors
    -> interval returns -> aggregation, filtered to rows whose ``trade_date``
    falls in ``(year, month)``. Reads a padded window of news and minute bars
    (see module constants) so boundary news/sessions resolve correctly."""
    target_start, target_end = month_bounds(year, month)
    calendar_start = target_start - timedelta(days=BACKWARD_LOOKBACK_DAYS)
    calendar_end = target_end + timedelta(days=FORWARD_LOOKAHEAD_DAYS)
    calendar = session_calendar(calendar_start, calendar_end)
    if calendar.empty:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS))

    news_start = target_start - timedelta(days=BACKWARD_LOOKBACK_DAYS)
    news_end = target_end + timedelta(days=FORWARD_LOOKAHEAD_DAYS)
    news = load_news_for_window(news_start, news_end)
    events = explode_news_events(news, calendar)
    target_mask = (events["trade_date"] >= pd.Timestamp(target_start)) & (
        events["trade_date"] <= pd.Timestamp(target_end)
    )
    events_in_month = events[target_mask]
    if events_in_month.empty:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS))

    symbols_needed = sorted(events_in_month["symbol"].unique())
    sessions_needed = calendar[
        (
            calendar["trade_date"]
            >= pd.Timestamp(target_start) - pd.Timedelta(days=BACKWARD_LOOKBACK_DAYS)
        )
        & (calendar["trade_date"] <= pd.Timestamp(target_end))
    ]

    shard_paths = list(minute_shard_paths(year, month))
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    shard_paths += minute_shard_paths(prev_year, prev_month)
    if not shard_paths:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS))

    bucket_prices = anchor_prices_from_minute_bars(
        shard_paths, symbols_needed, memory_limit=memory_limit, temp_directory=temp_directory
    )
    anchors = session_anchor_table(bucket_prices)
    # Restrict to sessions we actually need before computing returns -- keeps
    # the frame small and, more importantly, means "previous row per symbol"
    # in interval_returns_table is the previous *needed* session, which is
    # the immediately preceding trading session as long as BACKWARD_LOOKBACK
    # covers at least one prior session with bars (true whenever the prior
    # month's shards were loaded, i.e. always here except a symbol's very
    # first trading session on record).
    anchors = anchors[anchors["trade_date"].isin(sessions_needed["trade_date"])]
    intervals = interval_returns_table(anchors)
    agg = aggregate_news_return(intervals, events_in_month)
    agg = agg[
        (agg["trade_date"] >= pd.Timestamp(target_start))
        & (agg["trade_date"] <= pd.Timestamp(target_end))
    ]
    out = attach_news_counts(agg, events_in_month)
    return out.sort_values(["trade_date", "symbol"]).reset_index(drop=True)


def checkpoint_path(year: int, month: int) -> Path:
    return OUT_ROOT / CHECKPOINT_DIRNAME / f"{year}-{month:02d}.parquet"


def rebuild_year_file(year: int) -> Path | None:
    parts = sorted((OUT_ROOT / CHECKPOINT_DIRNAME).glob(f"{year}-*.parquet"))
    if not parts:
        return None
    frame = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    frame = frame.sort_values(["trade_date", "symbol"]).reset_index(drop=True)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = OUT_ROOT / f"{year}.parquet"
    frame.to_parquet(out_path, index=False)
    return out_path


def run_build(
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    *,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
    force: bool = False,
) -> None:
    (OUT_ROOT / CHECKPOINT_DIRNAME).mkdir(parents=True, exist_ok=True)
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        ckpt = checkpoint_path(year, month)
        if ckpt.exists() and not force:
            log(f"{year}-{month:02d}: checkpoint exists -- skipping")
        else:
            t0 = time.monotonic()
            frame = process_month(
                year, month, memory_limit=memory_limit, temp_directory=temp_directory
            )
            frame.to_parquet(ckpt, index=False)
            log(
                f"{year}-{month:02d}: {len(frame)} rows, "
                f"{frame['symbol'].nunique() if len(frame) else 0} symbols "
                f"({time.monotonic() - t0:.0f}s)"
            )
        rebuild_year_file(year)
        month += 1
        if month == 13:
            month = 1
            year += 1
    log("done")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="run (or resume) the month-by-month build")
    build.add_argument("--start", required=True, help="YYYY-MM, inclusive")
    build.add_argument("--end", required=True, help="YYYY-MM, inclusive")
    build.add_argument("--memory-limit", default=DEFAULT_MEMORY_LIMIT)
    build.add_argument("--temp-directory", default=None)
    build.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build":
        sy, sm = (int(x) for x in args.start.split("-"))
        ey, em = (int(x) for x in args.end.split("-"))
        run_build(
            sy,
            sm,
            ey,
            em,
            memory_limit=args.memory_limit,
            temp_directory=args.temp_directory,
            force=args.force,
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
