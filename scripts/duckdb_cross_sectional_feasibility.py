"""W6 feasibility probe: can this machine do cross-sectional research at all?

Three timed, memory-bounded queries against the full SIP daily archive via
DuckDB, per docs/plan-goal-first-verification-2026-09-02.zh.md Wave W6:

  (a) a full-market single-day cross-section,
  (b) a single symbol's full 10-year history,
  (c) a 12-1 cross-sectional momentum monthly portfolio, 2016-2026.

DuckDB is not a pyproject.toml dependency (that file is in the goal-first
plan's do-not-edit list) -- run this with:

    uv run --with duckdb python scripts/duckdb_cross_sectional_feasibility.py

Query (c) uses DuckDB only for the expensive full-table scan and the daily
momentum-signal window function; the small resulting month-end panel is
pulled into pandas for the rank/select/forward-return backtest loop, which
is far easier to get right there than as nested SQL window functions.
"""

from __future__ import annotations

import json
import resource
import time
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DAILY_GLOB = str(ROOT / "data" / "sip" / "daily" / "*" / "*.parquet")
OUTPUT_PATH = (
    ROOT / "reports" / "research" / "data-quality" / "cross-sectional-feasibility-2026-09.json"
)
MEMORY_LIMIT = "800MB"
LOOKBACK_DAYS = 252
SKIP_DAYS = 21
TOP_DECILE = 0.10
COST_BPS_PER_REBALANCE = 20.0


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute("SET temp_directory='/tmp/duckdb_w6'")
    return con


def query_a_single_day_cross_section(con: duckdb.DuckDBPyConnection, as_of: str) -> dict:
    started = time.time()
    result = con.execute(
        f"""
        SELECT symbol, close, volume
        FROM read_parquet('{DAILY_GLOB}')
        WHERE CAST(timestamp AS DATE) = DATE '{as_of}'
        """
    ).fetchdf()
    elapsed = time.time() - started
    return {
        "as_of": as_of,
        "row_count": len(result),
        "elapsed_seconds": round(elapsed, 3),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
    }


def query_b_single_symbol_history(con: duckdb.DuckDBPyConnection, symbol: str) -> dict:
    started = time.time()
    result = con.execute(
        f"""
        SELECT MIN(CAST(timestamp AS DATE)) AS first_date,
               MAX(CAST(timestamp AS DATE)) AS last_date,
               COUNT(*) AS row_count
        FROM read_parquet('{DAILY_GLOB}')
        WHERE symbol = '{symbol}'
        """
    ).fetchdf()
    elapsed = time.time() - started
    row = result.iloc[0]
    return {
        "symbol": symbol,
        "first_date": str(row["first_date"]),
        "last_date": str(row["last_date"]),
        "row_count": int(row["row_count"]),
        "elapsed_seconds": round(elapsed, 3),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
    }


def query_c_twelve_one_momentum(con: duckdb.DuckDBPyConnection) -> dict:
    started = time.time()
    # DuckDB does the expensive part: one full-table scan with a window
    # function computing each (symbol, date)'s trailing lookback-minus-skip
    # return, restricted to US-listed common-stock-shaped tickers (excludes
    # obvious non-equity/derivative symbols with a "." or "/" test-share
    # suffix) and a minimum price floor to avoid penny-stock noise dominating
    # an equal-weight decile.
    panel = con.execute(
        f"""
        WITH priced AS (
            SELECT
                symbol,
                CAST(timestamp AS DATE) AS trade_date,
                close,
                LAG(close, {SKIP_DAYS}) OVER w AS close_skip,
                LAG(close, {LOOKBACK_DAYS}) OVER w AS close_lookback
            FROM read_parquet('{DAILY_GLOB}')
            WHERE close > 5.0 AND symbol NOT LIKE '%.%' AND symbol NOT LIKE '%/%'
            WINDOW w AS (PARTITION BY symbol ORDER BY timestamp)
        ),
        monthly AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY symbol, date_trunc('month', trade_date)
                       ORDER BY trade_date DESC
                   ) AS rank_in_month
            FROM priced
            WHERE close_skip IS NOT NULL AND close_lookback IS NOT NULL AND close_skip > 0
        )
        SELECT
            symbol,
            trade_date,
            close,
            (close_skip / close_lookback - 1.0) AS momentum_12_1
        FROM monthly
        WHERE rank_in_month = 1
        ORDER BY trade_date, symbol
        """
    ).fetchdf()
    scan_elapsed = time.time() - started

    # Pandas does the small part: rank within each month-end, take the top
    # decile, and chain each month's equal-weight forward return.
    #
    # Grouping key is the calendar MONTH, not the exact trade_date: rank_in_month
    # picks each symbol's own last available row within a month independently,
    # so a symbol delisted mid-month contributes a trade_date weeks earlier than
    # a healthy symbol's true month-end. Treating every distinct trade_date as
    # its own "month end" (the first version of this script did) shatters the
    # ~116 real months into hundreds of near-duplicate dates and breaks the
    # month[i]->month[i+1] adjacency the forward-return loop depends on -- this
    # silently collapsed the whole backtest to 7 months out of a possible ~114.
    panel["symbol"] = panel["symbol"].astype("category")
    panel["close"] = panel["close"].astype("float32")
    panel["momentum_12_1"] = panel["momentum_12_1"].astype("float32")
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel["month_key"] = panel["trade_date"].dt.to_period("M")
    month_keys = sorted(panel["month_key"].unique())
    price_by_symbol_month = panel.set_index(["symbol", "month_key"])["close"]
    month_end_date_by_key = panel.groupby("month_key")["trade_date"].max()

    monthly_returns: list[dict] = []
    for i in range(len(month_keys) - 1):
        this_month, next_month = month_keys[i], month_keys[i + 1]
        snapshot = panel.loc[panel["month_key"] == this_month].dropna(subset=["momentum_12_1"])
        if snapshot.empty:
            continue
        cutoff = max(1, int(len(snapshot) * TOP_DECILE))
        selected = snapshot.nlargest(cutoff, "momentum_12_1")["symbol"].tolist()
        forward_returns = []
        for symbol in selected:
            try:
                entry = price_by_symbol_month.loc[(symbol, this_month)]
                exit_price = price_by_symbol_month.loc[(symbol, next_month)]
            except KeyError:
                continue
            forward_returns.append(exit_price / entry - 1.0)
        if not forward_returns:
            continue
        gross = sum(forward_returns) / len(forward_returns)
        monthly_returns.append(
            {
                "month_end": month_end_date_by_key.loc[this_month].date().isoformat(),
                "selected_count": len(forward_returns),
                "gross_return": gross,
                "net_return": gross - COST_BPS_PER_REBALANCE / 10_000.0,
            }
        )

    total_elapsed = time.time() - started
    returns = pd.Series([row["net_return"] for row in monthly_returns])
    equity = (1.0 + returns).cumprod()
    total_return = float(equity.iloc[-1] - 1.0) if len(equity) else 0.0
    years = len(returns) / 12.0
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 and total_return > -1 else None
    sharpe = (
        float(returns.mean() / returns.std(ddof=1) * (12.0**0.5)) if returns.std(ddof=1) else None
    )
    peak = equity.cummax()
    max_drawdown = float((equity / peak - 1.0).min()) if len(equity) else None

    return {
        "panel_row_count": len(panel),
        "month_count": len(monthly_returns),
        "duckdb_scan_elapsed_seconds": round(scan_elapsed, 3),
        "total_elapsed_seconds": round(total_elapsed, 3),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "cagr": cagr,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "total_return": total_return,
        "first_month": monthly_returns[0]["month_end"] if monthly_returns else None,
        "last_month": monthly_returns[-1]["month_end"] if monthly_returns else None,
    }


def main() -> None:
    con = _connect()
    report = {
        "memory_limit": MEMORY_LIMIT,
        "query_a_single_day_cross_section": query_a_single_day_cross_section(con, "2026-06-15"),
        "query_b_single_symbol_10y_history": query_b_single_symbol_history(con, "QQQ"),
        "query_c_twelve_one_momentum_active_universe_only_caveat": (
            "This query only scans the CURRENT data/sip/daily/ archive, which is "
            "ACTIVE-universe-only (see docs/data-layer-pitfalls-and-capabilities.zh.md "
            "item 3). Its own result is therefore survivorship-biased by construction; "
            "the point of this query is feasibility (time/memory), not a trustworthy "
            "return number. The bias magnitude is measured separately by comparing "
            "against the same computation over the ACTIVE+removed-tickers universe."
        ),
        "query_c_twelve_one_momentum": query_c_twelve_one_momentum(con),
    }
    con.close()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
