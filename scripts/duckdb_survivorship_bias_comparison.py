"""W6 survivorship-bias magnitude check: same 12-1 cross-sectional momentum
computation on the ACTIVE-only universe (data/sip/daily/, what
scripts/duckdb_cross_sectional_feasibility.py already measured) versus
ACTIVE + the 247 S&P 500 constituents removed since 2016
(data/sip-delisted/daily/, fetched by scripts/fetch_symbol_list.py from the
tickers in data/sip-delisted/removed_since_2016_tickers.txt).

Each removed ticker's price history is truncated to its recorded S&P 500
membership end_date (data/sip-delisted/sp500_ticker_start_end_fja05680.csv).
Without this, a ticker that was later reused by an unrelated company (this
project's own pitfall #6 -- "ticker recycling" -- confirmed empirically here:
AABA, delisted 2017-06-19, has price rows through 2026 in the raw fetch)
would silently splice a different company's returns onto the removed name's
history.

Decision rule, per docs/plan-goal-first-verification-2026-09-02.zh.md Wave
W6: CAGR difference > 2pp/year or Sharpe difference > 0.2 means cross-
sectional work must wait for a full data foundation; otherwise "ACTIVE +
removed list" is a cheap enough stand-in to proceed with.
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
    ROOT / "reports" / "research" / "data-quality" / "survivorship-bias-comparison-2026-09.json"
)
LOOKBACK_DAYS = 252
SKIP_DAYS = 21
TOP_DECILE = 0.10
COST_BPS_PER_REBALANCE = 20.0


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _removed_ticker_end_dates() -> dict[str, str]:
    """symbol -> S&P 500 membership end_date, for tickers removed since 2016."""
    end_dates: dict[str, str] = {}
    with MEMBERSHIP_CSV.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            end = row["end_date"].strip()
            if end and end >= "2016-01-01":
                # A ticker can appear more than once (re-added then re-removed);
                # keep the LATEST end_date it actually traded under S&P 500 membership.
                existing = end_dates.get(row["ticker"])
                if existing is None or end > existing:
                    end_dates[row["ticker"]] = end
    return end_dates


def _momentum_panel(
    con: duckdb.DuckDBPyConnection, glob: str, *, ticker_cutoffs_sql: str
) -> pd.DataFrame:
    query = f"""
        WITH raw AS (
            SELECT symbol, timestamp, close
            FROM read_parquet('{glob}')
            WHERE close > 5.0 AND symbol NOT LIKE '%.%' AND symbol NOT LIKE '%/%'
            {ticker_cutoffs_sql}
        ),
        priced AS (
            SELECT
                symbol,
                CAST(timestamp AS DATE) AS trade_date,
                close,
                LAG(close, {SKIP_DAYS}) OVER w AS close_skip,
                LAG(close, {LOOKBACK_DAYS}) OVER w AS close_lookback
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
        )
        SELECT symbol, trade_date, close, (close_skip / close_lookback - 1.0) AS momentum_12_1
        FROM monthly
        WHERE rank_in_month = 1
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
        "cagr": cagr,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "total_return": total_return,
    }


def main() -> None:
    end_dates = _removed_ticker_end_dates()
    con = duckdb.connect(":memory:")
    con.execute("SET memory_limit='800MB'")

    started = time.time()
    active_panel = _momentum_panel(con, ACTIVE_GLOB, ticker_cutoffs_sql="")
    active_result = _backtest_monthly_top_decile(active_panel)
    active_elapsed = time.time() - started

    # "Removed from the S&P 500" is not the same as "no longer tradable": 114 of
    # the 247 names in the membership file (e.g. AAL, DOW, EMC) were dropped
    # from the index for size/relevance but are still in Alpaca's ACTIVE
    # universe today, i.e. already present in active_panel. Adding them again
    # from the delisted fetch would double-count that symbol for the overlap
    # period and corrupt price_by_symbol_month's uniqueness (this crashed the
    # first version of this script: a duplicate (symbol, month) index turns
    # a scalar .loc[] lookup into a Series, and the whole return list
    # silently became object-dtype instead of float). Only genuinely-gone
    # tickers belong in the delisted supplement.
    active_symbols = (
        con.execute(f"SELECT DISTINCT symbol FROM read_parquet('{ACTIVE_GLOB}')")
        .fetchdf()["symbol"]
        .tolist()
    )
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
    delisted_raw = con.execute(
        f"""
        SELECT r.symbol, r.timestamp, r.close
        FROM read_parquet('{DELISTED_GLOB}') r
        JOIN cutoffs c ON r.symbol = c.symbol
        WHERE CAST(r.timestamp AS DATE) <= c.end_date
        """
    ).fetchdf()
    con.register("delisted_raw_view", delisted_raw)

    started = time.time()
    combined_panel_parts = [active_panel]
    # Recompute momentum for the delisted-only rows using the SAME window logic,
    # then union with the active panel's already-computed rows. Delisted names
    # only ever contribute observations up to their membership end_date, so no
    # symbol appears in both panels for overlapping dates.
    delisted_momentum = con.execute(
        f"""
        WITH priced AS (
            SELECT symbol, CAST(timestamp AS DATE) AS trade_date, close,
                   LAG(close, {SKIP_DAYS}) OVER w AS close_skip,
                   LAG(close, {LOOKBACK_DAYS}) OVER w AS close_lookback
            FROM delisted_raw_view
            WHERE close > 5.0
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
        SELECT symbol, trade_date, close, (close_skip / close_lookback - 1.0) AS momentum_12_1
        FROM monthly WHERE rank_in_month = 1
        """
    ).fetchdf()
    combined_panel_parts.append(delisted_momentum)
    combined_panel = pd.concat(combined_panel_parts, ignore_index=True)
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
        "removed_from_sp500_index_count": len(end_dates),
        "still_actively_tradable_count": len(end_dates) - len(genuinely_delisted),
        "genuinely_delisted_count": len(genuinely_delisted),
        "delisted_raw_row_count_after_cutoff": len(delisted_raw),
        "active_only": {**active_result, "elapsed_seconds": round(active_elapsed, 2)},
        "active_plus_removed": {**combined_result, "elapsed_seconds": round(combined_elapsed, 2)},
        "cagr_difference_pp": cagr_diff_pp,
        "sharpe_difference": sharpe_diff,
        "decision_rule": "material if |cagr_diff| > 2pp or |sharpe_diff| > 0.2",
        "survivorship_bias_material": material,
        "peak_rss_mb": round(_peak_rss_mb(), 1),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
