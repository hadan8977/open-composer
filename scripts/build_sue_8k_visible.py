"""T-20260928-14 / h20260928_14_sue_8k_timestamp: rebuild the SUE event's
``visible_at`` from the first NYSE session after the 10-Q/10-K filing date to
the first NYSE session after the matching 8-K Item-2.02 exhibit's EDGAR
``acceptanceDateTime``.

This is a new, standalone script (does not modify
``scripts/build_sec_xbrl_fundamentals.py``, ``scripts/build_earnings_events.py``,
or ``open_composer/research/signal_card.py``). It only builds a new join
table; ``sue_eps`` itself is read unchanged.

Reopen condition (verbatim, ``reports/research/signal-cards/fundamentals-v1-
manifest.json`` amendments[0], 2026-09-24T05:20:00Z): "usable session = first
NYSE session after the 10-Q/10-K filing date, which usually lags the earnings
press release (8-K item 2.02) by days to weeks; the card measures drift after
the XBRL filing, the tradeable version with free data."

Inputs
------
Left (unchanged): ``data/features/sec_fundamentals_daily/{year}.parquet``,
rows where ``days_since_report = 0 AND sue_eps IS NOT NULL`` -- exactly the
rows the refuted ``pead_sue_eps_event`` card's event triggered on
(``symbol``, ``cik``, ``trade_date`` = the old filing-date visible_at,
``sue_eps``).

Right: ``data/features/earnings_events/{year}.parquet`` (built separately
under ``docs/plan-earnings-text-forward-test-2026-09-22.zh.md`` T1), rows
where ``items`` contains ``2.02`` (``cik``, ``acceptance_utc`` -- already a
true UTC instant per that script's own Eastern-time-aware conversion).
Coverage: 2024-01-02 to 2026-09-17 only, which bounds this join's usable
window regardless of the left table's longer 2016+ history.

Usable-session rule for the 8-K timestamp
------------------------------------------
Convert ``acceptance_utc`` to US Eastern local time. If the local calendar
date is a trading session (``open_composer.market_calendar
.us_equity_session_close``) and the local time is at or before that
session's close (16:00, or 13:00 on an early-close day), the usable session
is that same trading date; otherwise (after close, or a non-trading day) the
usable session is ``open_composer.market_calendar.next_us_equity_session``
of the local calendar date. This mirrors the existing as-first-reported PIT
convention in ``scripts/build_sec_xbrl_fundamentals.py`` (a same-day filing
is conservatively usable only from the next session unless known to be
intraday) but adds the actual intraday cutoff the 8-K acceptance timestamp
makes possible.

Match rule
----------
For each left row (symbol, cik, old_visible_at, sue_eps), find the right
row with the same ``cik`` and the largest ``usable_session`` such that
``usable_session <= old_visible_at``, within a 65-calendar-day lookback
window (covers the longest routine gap between an earnings 8-K and its
follow-on 10-Q/10-K, ~45 days, plus slack). No match within the window ->
row dropped, not substituted with the old date. Implemented as a
``pandas.merge_asof`` (direction="backward", tolerance=65 days, grouped by
``cik``).

Output
------
``data/features/sue_8k_visible/{year}.parquet``: ``symbol``, ``trade_date``
(the new visible_at), ``value`` (``sue_eps``, unchanged) -- one row per
matched event, partitioned by the new visible_at's year so
``signal_card.py``'s existing ``--source``/``--column`` event-mode path can
read it unmodified.

Usage::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/build_sue_8k_visible.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.market_calendar import (  # noqa: E402
    next_us_equity_session,
    us_equity_session_close,
)

LEFT_GLOB = str(ROOT / "data" / "features" / "sec_fundamentals_daily" / "*.parquet")
RIGHT_GLOB = str(ROOT / "data" / "features" / "earnings_events" / "*.parquet")
OUT_DIR = ROOT / "data" / "features" / "sue_8k_visible"
LOOKBACK_DAYS = 65


def usable_session_for_acceptance(acceptance_utc: pd.Timestamp) -> date:
    """First NYSE session on/after ``acceptance_utc``, per the module's cutoff rule."""
    if acceptance_utc.tzinfo is None:
        acceptance_utc = acceptance_utc.tz_localize("UTC")
    et = acceptance_utc.tz_convert("America/New_York")
    local_date = et.date()
    close = us_equity_session_close(local_date)
    if close is not None and et.time() <= close:
        return local_date
    return next_us_equity_session(local_date)


def load_left(memory_limit: str) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        con.execute(f"SET memory_limit='{memory_limit}'")
        con.execute("SET threads=2")
        df = con.execute(
            f"""
            SELECT symbol, cik, trade_date, CAST(sue_eps AS DOUBLE) AS sue_eps
            FROM read_parquet('{LEFT_GLOB}', union_by_name=true)
            WHERE days_since_report = 0 AND sue_eps IS NOT NULL AND cik IS NOT NULL
            """
        ).df()
    finally:
        con.close()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).astype("datetime64[ns]")
    df["cik"] = df["cik"].astype("int64")
    return df


def load_right(memory_limit: str) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        con.execute(f"SET memory_limit='{memory_limit}'")
        con.execute("SET threads=2")
        df = con.execute(
            f"""
            SELECT CAST(cik AS BIGINT) AS cik, acceptance_utc
            FROM read_parquet('{RIGHT_GLOB}', union_by_name=true)
            WHERE items LIKE '%2.02%' AND acceptance_utc IS NOT NULL
            """
        ).df()
    finally:
        con.close()
    df["acceptance_utc"] = pd.to_datetime(df["acceptance_utc"], utc=True)
    df["usable_session"] = df["acceptance_utc"].map(usable_session_for_acceptance)
    df["usable_session"] = pd.to_datetime(df["usable_session"]).astype("datetime64[ns]")
    return df[["cik", "usable_session"]].dropna()


def build_join(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    left_sorted = left.sort_values("trade_date").reset_index(drop=True)
    right_sorted = (
        right.sort_values("usable_session")
        .drop_duplicates(["cik", "usable_session"])
        .reset_index(drop=True)
    )
    merged = pd.merge_asof(
        left_sorted,
        right_sorted,
        left_on="trade_date",
        right_on="usable_session",
        by="cik",
        direction="backward",
        tolerance=pd.Timedelta(days=LOOKBACK_DAYS),
    )
    matched = merged.dropna(subset=["usable_session"]).copy()
    matched = matched.rename(columns={"sue_eps": "value"})
    matched["trade_date"] = matched["usable_session"]
    return matched[["symbol", "trade_date", "value"]].sort_values(["trade_date", "symbol"])


def write_output(result: pd.DataFrame) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stats: dict = {}
    result = result.copy()
    result["year"] = result["trade_date"].dt.year
    for year, group in result.groupby("year"):
        path = OUT_DIR / f"{int(year)}.parquet"
        group[["symbol", "trade_date", "value"]].to_parquet(path, index=False)
        stats[str(int(year))] = int(len(group))
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="1000MB")
    args = parser.parse_args()

    left = load_left(args.memory_limit)
    right = load_right(args.memory_limit)
    result = build_join(left, right)
    stats = write_output(result)

    print(f"left_rows={len(left)} right_rows={len(right)} matched_rows={len(result)}")
    print(f"matched_symbols={result['symbol'].nunique()}")
    if len(result):
        print(f"trade_date_range={result['trade_date'].min()}..{result['trade_date'].max()}")
    print(f"by_year={stats}")


if __name__ == "__main__":
    main()
