"""Step 10 Wave 2 item 2: survivorship-bias magnitude check restricted to the
point-in-time liquid-500 universe, extending
scripts/duckdb_survivorship_bias_comparison.py (W6) the same way Wave 2's
official candidate extends scripts/duckdb_cross_sectional_feasibility.py:
each month-end t's tradable universe is the top 500 symbols by trailing
60-trading-day dollar ADV (``close * volume``, ``close > 5``) *as measured at
t*, not one fixed window applied to the whole 2016-2026 history (using 2026
liquidity to pick the 2016 universe would be look-ahead).

Per docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 5
item 2: this reruns the ACTIVE-vs-ACTIVE+removed-S&P-500-constituents
comparison (fja05680's former-constituent list is a reasonable large-cap
proxy) *inside* the liquid-500 filter, and the conclusion is scoped to "the
liquid-500 momentum family" only -- it is not a claim about survivorship bias
for cross-sectional momentum in general (that broader, unfiltered-universe
question was already answered by the W6 script: not material, see
reports/research/data-quality/survivorship-bias-comparison-2026-09.json).

Two INDEPENDENT top-500 rankings are computed, not one ranking with the
delisted rows spliced on afterward: "active_only" ranks active names alone
(what a real-time trader restricted to today's live universe would have
seen); "active_plus_removed" re-ranks the UNION of active and genuinely-
delisted rows jointly for every month, so a former large/liquid name can
displace a smaller active name from the top 500 exactly as it would have at
the time. Splicing two independently-filtered top-500 lists together could
let the combined universe balloon past 500 names in months with little
overlap, silently loosening the filter this script exists to test.

Same decision rule as W6: CAGR difference > 2pp/year or Sharpe difference >
0.2 means this sub-family's cross-sectional work must wait for a full data
foundation before promotion; otherwise "ACTIVE + removed list, liquidity-
filtered" is a cheap enough stand-in to proceed with.

DuckDB is not a pyproject.toml dependency -- run with:
    uv run --with duckdb python scripts/duckdb_survivorship_bias_comparison_liquid500.py
"""

from __future__ import annotations

import csv
import json
import resource
import time
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_GLOB = str(ROOT / "data" / "sip" / "daily" / "*" / "*.parquet")
DELISTED_GLOB = str(ROOT / "data" / "sip-delisted" / "daily" / "*.parquet")
MEMBERSHIP_CSV = ROOT / "data" / "sip-delisted" / "sp500_ticker_start_end_fja05680.csv"
OUTPUT_PATH = (
    ROOT
    / "reports"
    / "research"
    / "data-quality"
    / "survivorship-bias-comparison-liquid500-2026-09.json"
)
LOOKBACK_DAYS = 252
SKIP_DAYS = 21
ADV_LOOKBACK_DAYS = 60
ADV_TOP_N = 500
TOP_DECILE = 0.10
COST_BPS_PER_REBALANCE = 20.0
MEMORY_LIMIT = "900MB"

_RAW_SOURCE_COLUMNS = "symbol, timestamp, close, volume"


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _removed_ticker_end_dates() -> dict[str, str]:
    """symbol -> S&P 500 membership end_date, for tickers removed since 2016."""
    end_dates: dict[str, str] = {}
    with MEMBERSHIP_CSV.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            end = row["end_date"].strip()
            if end and end >= "2016-01-01":
                existing = end_dates.get(row["ticker"])
                if existing is None or end > existing:
                    end_dates[row["ticker"]] = end
    return end_dates


def _liquid_momentum_panel(con: duckdb.DuckDBPyConnection, raw_source_sql: str) -> pd.DataFrame:
    """Monthly panel of (symbol, trade_date, close, momentum_12_1), restricted
    to each month's own point-in-time top-``ADV_TOP_N`` by trailing
    ``ADV_LOOKBACK_DAYS`` dollar ADV -- computed with a ROWS-based trailing
    window (trading days, not calendar days) ending at that same row, so a
    symbol's liquidity rank at month t never uses data after t.

    ``raw_source_sql`` is a full ``SELECT symbol, timestamp, close, volume
    FROM ...`` expression (parenthesized if it is itself a UNION), letting
    the caller choose the active-only universe or the active+delisted union
    as the single source this whole ranking pipeline runs over -- so a joint
    top-500 rank is computed once, not two independent rankings spliced
    together after the fact.
    """
    query = f"""
        WITH raw AS (
            {raw_source_sql}
        ),
        priced AS (
            SELECT
                symbol,
                CAST(timestamp AS DATE) AS trade_date,
                close,
                LAG(close, {SKIP_DAYS}) OVER w AS close_skip,
                LAG(close, {LOOKBACK_DAYS}) OVER w AS close_lookback,
                AVG(close * volume) OVER (
                    PARTITION BY symbol ORDER BY timestamp
                    ROWS BETWEEN {ADV_LOOKBACK_DAYS - 1} PRECEDING AND CURRENT ROW
                ) AS dollar_adv
            FROM raw
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
                  AND dollar_adv IS NOT NULL
        ),
        month_end AS (
            SELECT * FROM monthly WHERE rank_in_month = 1
        ),
        ranked AS (
            SELECT *,
                   RANK() OVER (
                       PARTITION BY date_trunc('month', trade_date) ORDER BY dollar_adv DESC
                   ) AS adv_rank
            FROM month_end
        )
        SELECT symbol, trade_date, close, (close_skip / close_lookback - 1.0) AS momentum_12_1
        FROM ranked
        WHERE adv_rank <= {ADV_TOP_N}
        ORDER BY trade_date, symbol
    """
    return con.execute(query).fetchdf()


def _backtest_monthly_top_decile(panel: pd.DataFrame) -> dict:
    panel = panel.copy()
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel["month_key"] = panel["trade_date"].dt.to_period("M")
    month_keys = sorted(panel["month_key"].unique())
    price_by_symbol_month = panel.set_index(["symbol", "month_key"])["close"]

    monthly_returns: list[float] = []
    liquid_universe_sizes: list[int] = []
    for i in range(len(month_keys) - 1):
        this_month, next_month = month_keys[i], month_keys[i + 1]
        snapshot = panel.loc[panel["month_key"] == this_month].dropna(subset=["momentum_12_1"])
        if snapshot.empty:
            continue
        liquid_universe_sizes.append(len(snapshot))
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
        monthly_returns.append(gross - COST_BPS_PER_REBALANCE / 10_000.0)

    returns = pd.Series(monthly_returns)
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
        "month_count": len(monthly_returns),
        "median_liquid_universe_size": (
            float(pd.Series(liquid_universe_sizes).median()) if liquid_universe_sizes else None
        ),
        "cagr": cagr,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "total_return": total_return,
    }


def main() -> None:
    end_dates = _removed_ticker_end_dates()
    con = duckdb.connect(":memory:")
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute("SET temp_directory='/tmp/duckdb_w10_liquid500'")

    active_source = f"""
        SELECT {_RAW_SOURCE_COLUMNS} FROM read_parquet('{ACTIVE_GLOB}')
        WHERE close > 5.0 AND symbol NOT LIKE '%.%' AND symbol NOT LIKE '%/%'
    """

    started = time.time()
    active_panel = _liquid_momentum_panel(con, active_source)
    active_result = _backtest_monthly_top_decile(active_panel)
    active_elapsed = time.time() - started
    peak_after_active = _peak_rss_mb()

    active_symbols = (
        con.execute(f"SELECT DISTINCT symbol FROM read_parquet('{ACTIVE_GLOB}')")
        .fetchdf()["symbol"]
        .tolist()
    )
    # "Removed from the S&P 500" != "no longer tradable" (see W6's own script
    # for the AABA ticker-recycling pitfall this guards against): only names
    # genuinely absent from today's active universe get unioned in from the
    # delisted archive, truncated to their recorded membership end_date.
    genuinely_delisted = {
        symbol: end for symbol, end in end_dates.items() if symbol not in set(active_symbols)
    }
    cutoff_rows = ", ".join(
        f"('{symbol}', DATE '{end}')" for symbol, end in genuinely_delisted.items()
    )
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE cutoffs AS "
        f"SELECT * FROM (VALUES {cutoff_rows}) AS t(symbol, end_date)"
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE delisted_raw AS
        SELECT r.symbol, r.timestamp, r.close, r.volume
        FROM read_parquet('{DELISTED_GLOB}') r
        JOIN cutoffs c ON r.symbol = c.symbol
        WHERE CAST(r.timestamp AS DATE) <= c.end_date AND r.close > 5.0
        """
    )
    delisted_row_count = con.execute("SELECT COUNT(*) FROM delisted_raw").fetchone()[0]

    combined_source = f"""
        {active_source}
        UNION ALL
        SELECT {_RAW_SOURCE_COLUMNS} FROM delisted_raw
    """

    started = time.time()
    combined_panel = _liquid_momentum_panel(con, combined_source)
    combined_result = _backtest_monthly_top_decile(combined_panel)
    combined_elapsed = time.time() - started
    con.close()

    cagr_diff_pp = (
        (combined_result["cagr"] - active_result["cagr"]) * 100.0
        if combined_result["cagr"] is not None and active_result["cagr"] is not None
        else None
    )
    sharpe_diff = (
        combined_result["sharpe"] - active_result["sharpe"]
        if combined_result["sharpe"] is not None and active_result["sharpe"] is not None
        else None
    )
    material = (cagr_diff_pp is not None and abs(cagr_diff_pp) > 2.0) or (
        sharpe_diff is not None and abs(sharpe_diff) > 0.2
    )

    report = {
        "scope_caveat": (
            "This result is scoped to the liquid-500 momentum family only "
            "(top 500 by point-in-time trailing 60-day dollar ADV, close>5, "
            "jointly ranked across active+delisted for the combined case), "
            "not a general cross-sectional-momentum survivorship-bias claim."
        ),
        "adv_lookback_days": ADV_LOOKBACK_DAYS,
        "adv_top_n": ADV_TOP_N,
        "removed_from_sp500_index_count": len(end_dates),
        "still_actively_tradable_count": len(end_dates) - len(genuinely_delisted),
        "genuinely_delisted_count": len(genuinely_delisted),
        "delisted_raw_row_count_after_cutoff": int(delisted_row_count),
        "active_only": {**active_result, "elapsed_seconds": round(active_elapsed, 2)},
        "active_plus_removed": {**combined_result, "elapsed_seconds": round(combined_elapsed, 2)},
        "cagr_difference_pp": cagr_diff_pp,
        "sharpe_difference": sharpe_diff,
        "decision_rule": "material if |cagr_diff| > 2pp or |sharpe_diff| > 0.2",
        "survivorship_bias_material": material,
        "peak_rss_mb_after_active_only_pass": round(peak_after_active, 1),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
