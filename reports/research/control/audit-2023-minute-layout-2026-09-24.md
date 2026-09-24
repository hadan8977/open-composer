# Audit: 2023 minute dual-layout defect — consumer survey and blast radius

2026-09-24. Read-only audit. No code changes, no rebuilds, no commits, no deletions.

## Background (given, not re-derived)

`data/sip/minute/2023` has two overlapping layouts: a legacy whole-year layout
(`2023/shard-NNNN.parquet`, 317 files, BATCH_SIZE=40 numbering) and a per-month
layout (`2023/MM/shard-NNNN.parquet`, current BATCH_SIZE=12 numbering). The two
layouts use **unrelated shard numbering** (confirmed in
`open_composer/adapters/data/sip_parquet.py`'s module docstring), so a
month-only reader cannot be repaired by also reading "the same shard number"
one level up — it has to union both globs and dedup on `(symbol, timestamp)`.
2024-2026 (`data/sip/minute`) and 2016-2022 (`data/sip-hist/minute`) each have
**only** the month layout (verified: `ls -d data/sip/minute/{2024,2025,2026}/*/`
show 12/12/9 month dirs and 0 legacy shard files each; `data/sip-hist/minute/{2016..2022}`
likewise 0 legacy files). `data/sip/daily` has **no month subdirectories at
all**, for any year (`data/sip/daily/2023/*/` = 0 dirs) — the dual-layout
defect is structurally a 2023-minute-only problem.

The correct reader, `sip_parquet.py::load_sip_bars`, walks both the loose
`shard-*.parquet` files directly under a year directory and every
`{month}/shard-*.parquet`, concatenates, and drops duplicates on
`(symbol, timestamp)` (`_candidate_shards` + `_finalize`, lines 222-248 and
303-325). Any reader that builds its own glob instead of calling this
function is a candidate defect.

## New measurement: the gap runs in both directions, and is broader than the two originally-named tickers

Direct DuckDB queries (`memory_limit=400MB`, `threads=1`, symbol-filtered so
row-group pruning keeps every query to a handful of files) against
`data/sip/minute/2023/*/*.parquet` (month layer) vs `data/sip/minute/2023/*.parquet`
(legacy layer):

- **AAPL and AMD have zero rows in the month layer for all twelve months of
  2023**, not just September — `parquet_metadata()` shows no shard file in
  `2023/09/` even has an alphabetical range that covers `'AAPL'` or `'AMD'`;
  the gap is a missing batch in the month-layer's shard sequence, not merely
  empty/degenerate shards (the 11 known degenerate zero-row shards documented
  in `open_composer/research/features/intraday_daily.py` are a separate,
  already-handled case).
- A broader 20-name large-cap sample found the same all-year absence for
  **AMZN, BRK.B, AVGO, COST** in the month layer (present in legacy). That is
  6 of 20 sampled names, or 30% — consistent with the task's own
  6,128→8,594 symbol count (≈29% of the unioned 8,594 were month-layer-blind).
- The gap is **not one-directional**: **XOM and WMT are absent from the
  *legacy* layer for all of 2023** but present in the month layer. A
  legacy-only reader would be just as wrong as a month-only one. (No consumer
  found in this repo reads legacy-only for a year that also has month dirs,
  so this is recorded as a finding, not an active defect.)
- Conversely, the full watchlist of {SPY, QQQ, TQQQ, SPXL, IWM, SSO, UPRO,
  MSFT, NVDA, TSLA, GOOGL, GOOG, META, NFLX, JPM, V, MA, UNH, ORCL, HD, PG,
  JNJ} is present in **both** layers for all 12 months. Symbol absence looks
  batch-dependent (whichever alphabetical slice a fetch run skipped), not
  correlated with "is this a mega-cap" — AMZN/BRK.B/AVGO/COST are exactly as
  large as MSFT/NVDA/TSLA, yet only the former group is missing. This matters
  for the severity calls below: a script is safe today only because of *which
  specific tickers* it happens to hardcode, not because of any general
  immunity, and that safety must be re-verified if its symbol set ever
  changes.

`data/sip/daily`, all queried consumers, and `build_gap_panel.py`'s output
were also spot-checked and confirmed structurally out of scope (no month
split exists under `data/sip/daily` for any year).

## Consumer survey

| Consumer | How 2023 is read | Affected outputs | Measured gap | Dependent research artifacts | Severity | Recommended fix |
|---|---|---|---|---|---|---|
| `open_composer/adapters/data/sip_parquet.py::load_sip_bars` | Union of `year/shard-*.parquet` + `year/*/shard-*.parquet`, dedup on (symbol, timestamp) | all callers below marked "OK" | none (reference implementation) | — | — (correct) | none |
| `open_composer/research/features/intraday_daily.py` (`scripts/build_intraday_daily_features.py`) | `minute_shard_paths()` explicitly unions `year_dir.glob("shard-*.parquet")` + `year_dir.glob("*/shard-*.parquet")`; DuckDB `GROUP BY symbol, timestamp` CTE dedups before aggregation | `data/features/intraday_daily` | none — already correct, and the module docstring documents this exact defect (dated 2026-09-06) | — | OK | none; this is the pattern the other month-only scripts below should copy |
| `scripts/search_intraday_momentum_etf.py`, `scripts/evaluate_groupb_f3_qqq_intraday_momentum.py` | `load_sip_bars(..., frequency="minute")` | in-memory only | none | — | OK | none |
| `scripts/check_sip_freshness.py` | `load_sip_bars(symbol, frequency=<arg>)` | in-memory only | none | — | OK | none |
| `open_composer/execution/bar_source.py`, `open_composer/adapters/execution/model_ranking_target_weights.py`, `open_composer/research/kernel/benchmark_returns.py`, `open_composer/research/kernel/resample.py`, `open_composer/research/regime/etf_pullback_mean_reversion.py` | all route through `load_sip_bars` | in-memory only | none | — | OK | none |
| `scripts/build_hourly_bars.py` (`open_composer/research/bars/hourly.py` is a pure resampler, not a reader) | `_available_year_months()` and `_fetch_month_minute_bars()` glob **only** `MINUTE_ROOT/{year}/{month:02d}/shard-*.parquet`; never touches loose `shard-*.parquet` in the year dir | `data/bars/hourly/{year}.parquet` | `START_YEAR_MONTH=(2024,1)` means **2023 is never built today** — `MANIFEST.json` confirms only 2024/2025/2026 exist, so current output has no corrupted rows. But the universe is ~200 individual PIT-ADV stocks + {SPY,QQQ,IWM,TQQQ}, not just liquid ETFs — the broadest, highest-risk symbol scope of any month-only reader found here | `dir:reversal_trend_hourly_selection_alpha` (refuted) — verified its evaluation only uses `data/bars/hourly` years that exist (2024+), so today's refutation is unaffected | **Medium** (latent; no live corruption, but the shard-discovery code is wrong and the symbol scope is the one most likely to actually hit a missing name if ever extended back to 2023) | Before ever lowering `START_YEAR_MONTH` below 2024-01: mirror `intraday_daily.py::minute_shard_paths()` — union legacy + month globs in `_available_year_months` and `_fetch_month_minute_bars` |
| `scripts/cache_minute_panel.py` | `year_glob()` builds `root/{year}/*/shard-{cfg_shard:04d}.parquet` — month dirs only, fixed shard-number-per-symbol table, symbols = {SPY, QQQ, TQQQ, SPXL, IWM, SSO, UPRO} | `data/features/minute_panel/*.parquet` | **0 measured** — all 7 hardcoded symbols confirmed present in both layers, all 12 months of 2023 (direct query). Only `SPY.parquet` is actually materialized on disk today | `h20260922_07_intraday_momentum/report.md` uses `minute_panel/SPY.parquet` (2016-01→2026-09) — unaffected, SPY confirmed complete | **Low** (confirmed-safe today; same wrong code pattern as build_hourly_bars.py, silent if the symbol table is ever extended to a name outside this verified-safe set — e.g. an individual stock) | Same union fix; the docstring literally says it copies this pattern from `run_h20260918_02_orb_etf.py`, so fixing one and not the other leaves a trap |
| `scripts/run_h20260918_02_orb_etf.py` | `_year_glob()` — same month-dir-only pattern, symbols = {QQQ, TQQQ, SPY, SPXL} | `reports/research/iterations/h20260918_02_orb_etf/` cache + report | **0 measured** — all 4 hardcoded symbols confirmed present in both layers, all 12 months | `dir:orb_etf_opening_range_breakout` (**refuted**) — its stated decision basis is the 2024-01-02→2026-09-17 out-of-sample window only; the report explicitly labels the 2016→2023-02 in-sample check "confirmation only, not a basis for the conclusion" (`只用来确认实现的规则和论文对得上，不作为结论依据`), and even that window's 2023 slice (Jan-Feb) is confirmed complete | **Low** (confirmed-safe symbols; verdict is explicitly not 2023-dependent even if it weren't) | Same union fix, for hygiene — this file is the copy-paste origin of the anti-pattern (see `cache_minute_panel.py` above) |
| `scripts/run_h20260924_01_etf_dip_reversion.py` | Docstring/constants (`MINUTE_GLOB_HIST`, `MINUTE_GLOB_CURRENT = "data/sip/minute"`, comment says "2023+ per-month layout") describe a Stage B minute read | none yet | N/A — **Stage B is not implemented** (`"Stage B (T1, minute bars) is not implemented in this pass"`, stderr at line 1314); the two `MINUTE_GLOB_*` constants are declared and unused | none (Stage A is daily-only and already ran) | **Informational** | When Stage B is implemented, do not build a month-only reader from the "2023+ per-month layout" framing in the docstring — use `load_sip_bars` or the `intraday_daily.py` union pattern from the start |
| `scripts/evaluate_groupb_f1_etf_pullback_mean_reversion.py`, `evaluate_reversal_trend_hourly.py` (daily leg), `reversal_trend_parity.py`, `run_h20260917_02_ml_ranking.py`, `run_h20260916_05_13d_drift.py`, `run_h20260918_01_momentum_risk_control.py`, `run_step13_m_grid.py`, `search_daily_momentum_p2a.py`, `search_expression_trees_p2b.py`, `evaluate_vol02_recalibrated.py`, `evaluate_ma_crossover_mini_search.py`, `evaluate_groupb_f5_beta_router_reference.py`, `build_step13_regime_daily_features.py`, `run_h20260917_01_insider_independent.py` | All call `load_sip_bars(..., frequency="daily")` exclusively — no `frequency="minute"` call found in any of these 14 files | in-memory only | N/A — `data/sip/daily` has no month/legacy split for any year, so the defect cannot occur structurally | — | **N/A** | none |
| `evaluate_reversal_trend_hourly.py` (hourly leg) | Reads `data/bars/hourly/*.parquet` output, not raw minute shards | consumes build_hourly_bars.py output | N/A — that output has no 2023 file at all today (see above) | `dir:reversal_trend_hourly_selection_alpha` (refuted, unaffected — see row above) | N/A | none beyond fixing build_hourly_bars.py before any 2023 extension |
| `scripts/build_gap_panel.py` (`data/features/gap_panel.parquet`) | `DAILY_GLOB = "data/sip/daily/*/*.parquet"` only — no minute reference anywhere in the file | `data/features/gap_panel.parquet` | N/A — daily-only; spot-checked, 2023 monthly distinct-symbol counts run ~3,950-4,240/month, sourced entirely from the unaffected daily archive | (out of scope for this defect) | **N/A** | none |
| `scripts/evaluate_beta_exposure_family_sip.py`, `evaluate_champion_route_sip.py`, `evaluate_cross_asset_trend_sip.py` | Only matched on the literal string `"sip_parquet"` / `"sip_parquet_via_daily_returns_on_naive_dates"` used as a `data_source` provenance tag; no in-file glob or `load_sip_bars` call found by name | unverified | **not fully verified — lowest priority given budget**; the `..._via_daily_returns_on_naive_dates` tag name is strong (but not conclusive) evidence these are daily-only | — | **Unverified / presumed low** | Re-check data-loading path before relying on this row; not re-derived here to stay inside the time budget |
| `scripts/fetch_sip_universe.py` | Archive **writer**, not a research consumer; writes month-sharded files, iterates `months = range(1,13)` for `kind=="minute"` | writes `data/sip/minute` | N/A (out of scope: this is presumably the origin of the September-2023-and-other-months fetch gap, not re-diagnosed here per the task's framing) | — | N/A | none (root-causing the original fetch gap is out of scope for this audit) |
| `scripts/update_sip_archive.py` | Incremental updater; explicitly restricted to the **current** calendar month/year window only (2026-09 today); docstring states the loader is unmodified and already dedups | none for 2023 | N/A — does not touch 2023 | — | N/A | none |
| `scripts/build_feature_universe.py`, `scripts/detect_delisted_aliases.py`, `scripts/duckdb_cross_sectional_feasibility.py`, `scripts/duckdb_survivorship_bias_comparison.py` | Matched an initial broad grep for month-glob-shaped code, but none reference "minute" anywhere in the file | daily-derived outputs only | N/A | — | N/A | none |
| `scripts/build_news_hf_reaction.py`, `scripts/run_h20260923_13_orb_stocks_in_play.py` | **Out of scope per task** — already fixed/handled | `data/features/news_hf_reaction` | Confirmed as a side note: `data/features/news_hf_reaction/` has no 2023 file at all (2024/2025/2026 only), consistent with the cited commit fixing this | `dir:orb_stocks_in_play_relative_volume` (queued, dossier-only — no backtest yet) | (excluded) | (excluded) |

## `scripts/prune_local_archive.py` — could it delete legacy 2023 shards? (task item 5)

**Not today, but for the wrong reason, and it is a real trap for a future
"fix."**

`discover_units()` (lines 70-85) does:

```python
month_dirs = [d for d in sorted(year_dir.iterdir()) if d.is_dir() and d.name.isdigit()]
if month_dirs:
    for month_dir in month_dirs:
        units.append(PruneUnit(kind, year, int(month_dir.name), month_dir, _dir_bytes(month_dir)))
else:
    units.append(PruneUnit(kind, year, None, year_dir, _dir_bytes(year_dir)))
```

For `data/sip/minute/2023`, `month_dirs` is non-empty (12 dirs), so only the
`if` branch runs — one `PruneUnit` per month directory. The loose legacy
`shard-*.parquet` files sitting directly in `2023/` are never visited by
either branch (`_dir_bytes(month_dir)` only sums bytes inside that month
directory via `rglob`, and the `else` branch that would sweep the year
directory's loose files never fires because `month_dirs` is truthy). **The
legacy 2023 shards are structurally invisible to this script — they can be
neither pruned nor counted.** That is accidental safety, not a designed
guarantee, and it also means disk-usage accounting silently undercounts by
however much the legacy 317 files occupy.

Even in a hypothetical world where they were discovered as a whole-year unit,
they would not be expired yet: `RETENTION_DAYS["minute"] = 1278` days,
`_covered_end(2023, None) = 2024-01-01`, and `(2026-09-24 − 2024-01-01)` is
≈999 days — that crosses 1278 days around **2027-02-14**, not before.

**Forward-looking risk to flag, not fix here:** if a future change makes
`discover_units()` also emit a whole-year `PruneUnit` for the loose legacy
files whenever `month_dirs` is also present (a very natural-looking bugfix,
since right now that space can never be reclaimed at all), that unit will
start aging past the 1278-day retention threshold in ~2027-02, and applying
`--apply` at that point would permanently delete the *only* remaining copy of
the AAPL/AMD/AMZN/BRK.B/AVGO/COST-type 2023 rows that are missing from the
month layer — real data loss, exactly as the task worried. Any such change
must first confirm month-layer/legacy-layer parity (or complete the union
fix in the table above and rebuild the month layer to be a true superset)
before legacy 2023 minute shards are ever made prunable. `data/sip/daily`
has no equivalent risk (`month_dirs` is always empty there, so the `else`
branch — which is correct for a true single-layout year — always fires).

## Ranked list of fixes/rebuilds that matter most

1. **`scripts/prune_local_archive.py` — document the trap before anyone "fixes" the invisible-legacy-2023 gap.** No code or data is at risk today, but this is the one item on this list where a plausible, well-intentioned future change turns into permanent data loss. Lowest effort (a code comment plus a guard condition), highest downside if skipped.
2. **`scripts/build_hourly_bars.py` — union the legacy shard glob into `_available_year_months`/`_fetch_month_minute_bars` before `START_YEAR_MONTH` is ever moved back to include 2023.** This is the broadest individual-stock symbol scope of any month-only reader in the repo (~200 PIT-ADV names, not a handful of hardcoded ETFs), so it's the most likely to actually hit a missing name once someone extends the window — currently blocked only by a constant, which is an easy thing to change without re-reading this audit.
3. **`scripts/cache_minute_panel.py` and `scripts/run_h20260918_02_orb_etf.py` — apply the same union fix for hygiene and to stop the anti-pattern from propagating.** No currently-live gap (both scripts' hardcoded symbol sets are confirmed complete in both layers for all of 2023), but `cache_minute_panel.py`'s own docstring cites `run_h20260918_02_orb_etf.py` as the "proved safe" precedent, so leaving one unfixed keeps inviting a third copy with an unverified symbol set.
4. **No rebuild is currently justified.** Every consumer whose current output could plausibly be corrupted by this defect (`run_h20260923_13_orb_stocks_in_play.py`, `build_news_hf_reaction.py`) is already excluded from this audit as fixed/handled. Every other output checked (`data/features/intraday_daily`, `data/features/minute_panel`, `reports/research/iterations/h20260918_02_orb_etf/`, `data/features/gap_panel.parquet`, `data/bars/hourly`) is either already correct, confirmed gap-free by direct measurement, or does not yet contain 2023 data at all.
5. **When `run_h20260924_01_etf_dip_reversion.py` Stage B is eventually implemented**, point it at `load_sip_bars` or copy `intraday_daily.py::minute_shard_paths()` directly rather than building a new reader from the docstring's "2023+ per-month layout" framing — cheapest possible prevention, zero cost today.

## Coverage caveat

`scripts/evaluate_beta_exposure_family_sip.py`, `evaluate_champion_route_sip.py`,
and `evaluate_cross_asset_trend_sip.py` were matched by the initial grep but
not traced to their actual data-loading call inside the time budget; their
`data_source` tag names are consistent with daily-only reads but this is not
directly confirmed. No other gaps in coverage are known — the survey started
from the task's candidate list, was extended with a repo-wide grep for
`sip/minute|load_sip_bars|sip_parquet` across `scripts/` and `open_composer/`
(this found every file above plus the 4 daily-only scripts in the last
"matched an initial broad grep" row), and a second broad grep for the
month-only glob shape (`"*" / f"shard-...` / `str(year)... "*"...shard`)
turned up no additional minute-bar readers beyond what the first grep found.
