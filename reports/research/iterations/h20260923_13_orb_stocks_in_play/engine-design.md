# Engine design: h20260923_13_orb_stocks_in_play

No engine code is written in this pass (task hard rule). This is a design note for whoever writes
`scripts/run_h20260923_13_orb_stocks_in_play.py` next: the minute-data loading plan within 2GB RAM
(the box has 3.9GB total; heavy jobs run through `scripts/run_capped.sh`), which functions of
`scripts/run_h20260918_02_orb_etf.py` to reuse, and the expected runtime.

## 1. Why this is a harder data problem than the ETF cousin

`scripts/run_h20260918_02_orb_etf.py` (the already-refuted ETF-ORB study, H-20260918-02) has it
easy: 4 fixed symbols, whose shard numbers were hand-verified once and hardcoded
(`_SHARD_BY_SOURCE`). Stocks-in-Play needs the opposite: **every eligible stock's** first-5-minute
volume, every day, to compute the relative-volume ranking and find the top 20 -- there is no fixed
symbol list. `data/sip-hist/minute` (2016-2022) has ~1,118 shard files per month, `data/sip/minute`
(2023+) has up to 1,266 per year; a naive "glob the whole archive" read is exactly what the ETF
script's own docstring warns times out. The design below never does that.

## 2. Three-stage, resumable pipeline (mirrors the ETF script's load/backtest/report split)

### Stage 0: symbol-to-shard index (one-time per archive, cached to disk)

`data/sip/minute/_LAYOUT.json` already ships a `shard_symbols` index (1,266 shard keys, ~13,578
symbol slots) -- **reuse it directly**, but do not trust it blindly for shards `<=316` per year:
the file's own note says those were written under an earlier `batch_size=40` layout and "hold a
different symbol slice than their index implies under the current layout." Before trusting a
candidate symbol's shard number in that range, do a one-off `SELECT DISTINCT symbol FROM
read_parquet(shard_path)` against that specific file and cache the confirmed mapping -- the same
"verify by reading each file's symbol column, not just footer min/max stats" discipline the ETF
script's own docstring already applies to its 4 hardcoded symbols.

`data/sip-hist/minute` (2016-2022, the design window) has **no shard index at all** -- only
`{batch_size: 12, universe_size: 13414}` in `_LAYOUT.json`. Build one: for one representative
month (e.g. 2016-01), run a column-pruned `SELECT DISTINCT symbol FROM
read_parquet('data/sip-hist/minute/2016/01/shard-*.parquet')` per shard (or a single glob query
with a `shard_id` derived from the file path), writing a JSON manifest
(`cache/sip_hist_shard_symbols.json`) shaped like the existing `_LAYOUT.json["shard_symbols"]`.
Spot-check 2-3 more months/years (matching the ETF script's own verified years: 2016, 2019, 2022)
to confirm the mapping is stable before trusting it for the whole window. This is a narrow-column
scan (`symbol` only, no OHLCV payload), so it is cheap even at ~1,118 files/month.

### Stage 1 (`stage_load`, per year, cached under `cache/opening_bars/<year>.parquet`)

For each trading day, every eligible symbol needs only: first-5-minute (09:30:00-09:34:59 ET) open/
high/low/close/volume, to compute the opening range, the doji test, and the relative-volume ratio.
The query's `WHERE time BETWEEN 09:30 AND 09:35` clause (below) excludes pre-market prints from the
opening range regardless of whether the archive carries them -- whether it does was not directly
verified this pass (see data-feasibility.json point 6); the cheapest direct check is a single-
symbol, single-day timestamp scan for rows before 09:30 ET, cheap enough to fold into Stage 0.
This is a **tiny** slice of each day's minute bars. Per (year, shard): one DuckDB query,
`SET memory_limit='800MB'; SET threads=2` (matching the ETF script's own connection settings)
against `read_parquet(glob, ...)  WHERE symbol IN (shard's symbols) AND time BETWEEN 09:30 AND
09:35`, accumulated into a per-year "opening bar summary" table (symbol, date, open, high, low,
close, volume -- a handful of floats per symbol-day, not the full minute bar sequence). For ~7,000
symbols x ~252 days/year x ~7 fields, this is on the order of a few hundred MB per year as Parquet,
not the 60GB raw minute archive -- and once built for a year, the ranking step never touches raw
minute data again. Trailing-14-day average volume and 14-day ATR are **not** computed from minute
bars at all: pull them from `data/sip/daily` via `open_composer.adapters.data.sip_parquet.
load_sip_bars` (the same daily loader the ETF script already uses for its benchmark buy-and-hold),
which is far cheaper and matches the paper's own "14-day" (calendar trading day) convention more
directly than re-deriving it from minute data.

### Stage 2 (`stage_rank`, pure arithmetic over the Stage 1 cache, no data re-read)

Per day: apply the candidate's price/avg-volume/ATR eligibility filters (from the daily-bar table),
compute relative volume (`ORVolume[t] / mean(ORVolume[t-14..t-1])`) for every eligible symbol from
the Stage 1 cache, rank descending, take the top 20 (SIP01/SIP02) -- or, for RL, a random 20 from
the eligible-but-not-top-20 set. This step is bounded by the eligible-universe size per day (at
most a few thousand rows), not the full archive, and needs no new minute-bar I/O.

### Stage 3 (`stage_simulate`, only for the ~20 selected symbols/day)

Only after Stage 2 names the day's top 20 does the engine need each selected symbol's **full**
intraday path (09:30 through EOD) to walk the stop/EOD exit -- this is exactly the ETF script's
`build_day_records` / `_simulate_outcome` logic (see section 3), just invoked for a rotating
~20-symbol/day set instead of 4 fixed symbols across the whole window. Bounded at roughly
20 x ~252 = ~5,040 symbol-days/year (design window) versus 7,000 x 252 = ~1.76M if every eligible
name's full path were read -- a ~350x reduction. Batch by (year, shard) so a whole year of one
shard's selected-day rows are pulled in one query, same pattern as Stage 1.

Placebo controls reuse Stage 1/2's cache untouched: RD only changes which direction a trade at an
already-selected symbol takes (no new data read); RL only changes which 20 symbols are selected
from the same day's already-computed eligible set (Stage 3 then runs on a different 20 names, same
cost as a real candidate run).

## 3. What to reuse from `scripts/run_h20260918_02_orb_etf.py`

Directly reusable, unchanged or lightly parameterized:

- `_read_year_minute_bars` pattern (targeted DuckDB shard reads, `memory_limit`/`threads` caps) --
  generalize from "one hardcoded shard per symbol" to "iterate the shard list for a given year from
  the Stage 0 index."
- `build_day_records` / `_simulate_outcome` / `_outcome_fields` -- the stop/EOD path-walk logic is
  identical in shape; **drop the 10R target branch** (`TARGET_R_MULTIPLE`, `hit_target`), since the
  paper's individual-stock section has none (see hypotheses.md). Keep the doji test but change the
  threshold from the ETF script's `abs(close-open) <= 5%*(high-low)` approximation to the paper's
  exact `open == close` rule.
- `simulate_equity` -- equity compounding, cost/borrow deduction; needs extending from a
  single-symbol book to an up-to-20-name daily book (sum P&L across concurrently-held names,
  respecting the 1/20 max weight cap).
- `_metrics` (Sharpe/CAGR/max drawdown/hit-rate/avg-R/share-of-days-in-market) -- reusable as-is.
- `random_direction_trades` -- directly reusable for the RD control (same day set, direction
  redrawn).
- The overall `stage_load` / `stage_backtest` / `stage_report` resumable-cache split, `_log`
  timestamped progress printing, and `_write_json`/`_json_default` JSON-safety helpers.

New, not present in the ETF script:

- The daily universe-wide relative-volume ranking and top-20 selection (Stage 2 above) -- the ETF
  script has a fixed 4-symbol universe, nothing to rank.
- The Stage 0 symbol-to-shard manifest build for `sip-hist` (the ETF script hardcodes 4 known
  shard numbers).
- A portfolio-level (up to 20 concurrent names, weight-capped) equity simulator, versus the ETF
  script's one-book-per-symbol design.
- The 14-day trailing avg-volume/ATR eligibility filter from `data/sip/daily` (the ETF script only
  uses daily bars for its own benchmark buy-and-hold, never as a filter).
- `random_liquid_non_in_play_trades` (the RL control) -- new, no ETF-script analogue, since the ETF
  study has no selection step to ablate.

## 4. Expected runtime (all stages via `scripts/run_capped.sh`, matching the ETF script's own
   convention of `--mem 1.2G` for the full-history load stage)

| stage | scope | estimate |
|---|---|---|
| Stage 0a: verify `data/sip/minute` shard_symbols for candidate symbols in shards<=316 | ~20-50 targeted single-shard reads | minutes |
| Stage 0b: build `data/sip-hist/minute` shard index (one representative month + 2-3 spot-check months/years) | ~1,118 shards x ~4 months, symbol-column only | 20-40 min, single pass, resumable |
| Stage 1: opening-bar summary, design window (2016-2022) | 7 years x ~12 shard-batches/month, column-pruned | 1-2 hours, cached per year, resumable |
| Stage 1: opening-bar summary, select window (2023-2025) | ~2.25 years | 20-40 min |
| Stage 2: daily ranking, design + select windows | pure arithmetic over Stage 1 cache | minutes |
| Stage 3: trade-path simulation, ~20 names/day x candidates x placebo seeds | bounded symbol-day count (see section 2) | well under an hour for the whole design window once Stage 2's selections are known |
| Stage 3: 2026 report window | ~9 months | proportionally faster than the design window |

All stages are resumable/cacheable exactly as the ETF script already demonstrates (per-year Parquet
caches under `reports/research/iterations/h20260923_13_orb_stocks_in_play/cache/`), so a 429,
OOM-kill, or timeout mid-run loses at most the in-progress year, not the whole job, consistent with
`docs/research-mission.zh.md`'s requirement that long-running research jobs have checkpoints and
timeouts.

## 5. Explicit non-goals of this note

Nothing here is engine code; no query above has been executed against the full minute archive in
this pass (only the read-only, narrow-column diligence already logged in
`data-feasibility.json` and this iteration's direction-review.json -- directory listings,
`_LAYOUT.json`/`_MANIFEST.json` contents, and script source reading). Writing
`scripts/run_h20260923_13_orb_stocks_in_play.py` itself, running Stage 0-3, and producing
`trial-ledger.jsonl`/`report.md` are the next step's work, gated on this dossier's `ok` status from
`oc research iteration validate --stage pre-backtest` and on Stage 0's shard-index verification
actually succeeding before Stage 1 is allowed to run at scale.
