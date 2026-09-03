# W6: Cross-Sectional Feasibility and Survivorship-Bias Magnitude

Scripts: `scripts/duckdb_cross_sectional_feasibility.py`,
`scripts/duckdb_survivorship_bias_comparison.py`.
Full evidence: `reports/research/data-quality/cross-sectional-feasibility-2026-09.json`,
`reports/research/data-quality/survivorship-bias-comparison-2026-09.json`.
DuckDB is not a `pyproject.toml` dependency (that file is in the goal-first
plan's do-not-edit list); both scripts run via `uv run --with duckdb`.

## Part 1: is cross-sectional research computationally feasible on this machine?

Three queries against the full SIP daily archive (`data/sip/daily/`, ~13,400
active symbols, 2016-2026), timed and memory-bounded per the plan's decision
rule (`memory_limit='800MB'` set on the DuckDB connection; peak RSS measured
on the whole Python process, which also includes pandas/numpy overhead and
result materialization DuckDB's own limit does not cover).

| Query | Elapsed | Peak RSS | Verdict |
|---|---:|---:|---|
| (a) full-market single-day cross-section (12,479 symbols) | 0.6s | 291MB | well within budget |
| (b) single-symbol 10-year history (QQQ, 2,680 rows) | 0.3s | 293MB | well within budget |
| (c) 12-1 cross-sectional momentum, monthly, 2016-2026 (674,753-row panel, 115 months) | 21-25s | **1,164-1,180MB** | **time OK, memory over budget** |

**Time is not the constraint.** All three queries finish in seconds; even the
full monthly cross-sectional momentum panel scans and backtests in well under
the 60-second threshold.

**Memory is, for query (c) specifically.** Peak RSS lands 14-18% over the
plan's pre-committed 1GB threshold across two independent runs (1,163.7MB and
1,180.3MB). This is driven by DuckDB's own window-function execution memory
during a full-archive `LAG(...) OVER (PARTITION BY symbol ORDER BY timestamp)`
scan across the entire market, not by the final pandas result (dtype
downcasting the materialized panel to `category`/`float32` moved peak RSS by
less than 1%, confirming the cost is upstream of pandas). The machine was not
in danger of OOM at the time (2.4-2.5GB was free), so this is a "needs care to
make routine" finding, not a "the box falls over" finding -- but per the
plan's own decision rule as literally written (`>1GB -> 本机不做横截面`),
a full-market monthly cross-sectional panel is **over budget as naively
implemented**, not comfortably free.

**Two real bugs found and fixed while building query (c)**, both instructive
beyond this one query:

1. **Month-boundary bug (methodological, not a crash):** the first version
   grouped by exact `trade_date` rather than calendar month. `ROW_NUMBER() ...
   PARTITION BY symbol, date_trunc('month', trade_date)` picks each symbol's
   own *last available* row within a month independently, so a symbol
   delisted mid-month contributes a `trade_date` weeks earlier than a healthy
   symbol's true month-end. Treating every distinct `trade_date` as its own
   "month" shattered the ~115 real months into hundreds of near-duplicate
   dates and broke the `month[i] -> month[i+1]` adjacency the forward-return
   loop depends on, silently collapsing the backtest to **7 usable months out
   of a possible 115** with a materially different (and meaningless) return
   series. Fixed by keying on `trade_date.dt.to_period("M")` instead of the
   exact date.
2. **Ticker-recycling bug (data-quality, matches this project's own pitfall
   #6):** "removed from the S&P 500 index" is not the same as "no longer
   tradable." Of the 247 tickers in the membership-changes dataset, **114 are
   still in Alpaca's ACTIVE universe today** (e.g. AAL, DOW, EMC -- dropped
   from the index for size/relevance, not delisted). Naively unioning all 247
   names' fetched history into the "active + removed" comparison universe
   created duplicate `(symbol, month)` rows for those 114 overlapping names,
   which corrupted the price lookup index and crashed the script (a duplicate
   index turns a scalar `.loc[]` lookup into a Series, silently making the
   whole return series object-dtype). Fixed by excluding any ticker still
   present in the active archive from the delisted supplement -- only the
   **133 genuinely-delisted** names are added.

## Part 2: how large is survivorship bias, for this factor family?

Same 12-1 cross-sectional top-decile momentum computation, ACTIVE-only
universe vs. ACTIVE + the 133 genuinely-delisted S&P 500 constituents removed
since 2016 (each truncated to its actual membership `end_date`, so no
reused-ticker contamination — see the `data/sip-delisted/
sp500_ticker_start_end_fja05680.csv` source, from the `fja05680/sp500`
GitHub dataset).

| | ACTIVE-only | ACTIVE + 133 delisted | Difference |
|---|---:|---:|---:|
| CAGR | 8.06% | 8.00% | **-0.06pp** |
| Sharpe | 0.473 | 0.471 | **-0.002** |
| Max drawdown | -32.76% | -32.96% | -0.20pp |
| Months | 115 | 115 | — |

Against the plan's decision rule (material if `\|CAGR diff\| > 2pp` or
`\|Sharpe diff\| > 0.2`): **not material.** Both differences are roughly two
orders of magnitude below the threshold.

**This is not a surprising result once stated economically, and it is
specific to this factor.** A long-only, top-decile-by-trailing-return
momentum strategy structurally tends to avoid stocks in the process of being
delisted for poor performance (bankruptcy, forced removal) — those names
typically have deeply negative trailing 12-month returns and would rarely
qualify for a "top decile winners" portfolio in the first place. Survivorship
bias is well documented in the literature as a much larger problem for
value, buy-and-hold-the-index, or naive "current constituents only" backtests
than for winner-selecting momentum strategies specifically. This result is
consistent with that pattern, not a general license to skip survivorship
correction for other factor families.

## Disposition for the goal-first conclusion

- **Time is never the blocker for cross-sectional work on this machine.**
- **Memory is the blocker for a naive full-market monthly panel** (14-18%
  over the 1GB budget); the fix is architectural (restrict the universe by
  liquidity *before* building the full panel, or push more of the window
  computation into DuckDB with a lower `memory_limit` and accept slower
  spill-to-disk execution) rather than a sign cross-sectional work is
  impossible here.
- **Survivorship bias is not material for a momentum-style selection rule**,
  which means the capability-gap analysis's P0 ranking of "full survivorship
  correction before any cross-sectional work" should be read as
  factor-dependent: for a momentum family specifically, the cheap
  "ACTIVE + removed-tickers-list" fix this wave built is adequate; a factor
  that would systematically avoid recent losers less (e.g. value, low-vol, or
  any strategy that could hold names in decline) would need the full
  correction before trusting a number from it.
