# Report: h20260928_14_sue_8k_timestamp

## What was tested

SUE8K01: the refuted `pead_sue_eps_event` card (`dir:pead_xbrl_sue_filing_date`),
rebuilt with `visible_at` moved from the first NYSE session after the
10-Q/10-K filing date to the first NYSE session after the matching 8-K
Item-2.02 exhibit's EDGAR `acceptanceDateTime`. Same `sue_eps` values
(unchanged), same universe (top-3000 PIT, close>=$5), same threshold (2.0),
same primary horizon (20 sessions), same costs (10/20bp), same redated
placebo (20 seeds) -- only the timestamp join changed
(`scripts/build_sue_8k_visible.py`, new file).

## Join build

`scripts/run_capped.sh --mem 1.8G -- uv run python
scripts/build_sue_8k_visible.py --memory-limit 1000MB`:
left_rows=77,480 (all `days_since_report=0` sue_eps rows, all years, all
symbols), right_rows=16,015 (8-K/2.02 filings, 2024-01-02 to 2026-09-17),
matched_rows=11,556 (1,211 symbols), trade_date range 2024-01-03 to
2026-09-15 -- bounded by the right table's coverage, as disclosed in
`direction-review.json`.

## Signal card

`signal_card.py --mode event --source data/features/sue_8k_visible --column
value --threshold 2.0 --top-n 3000 --primary-horizon 20`, run through
`scripts/run_capped.sh --mem 1.8G` (duckdb `memory_limit` defaults to
1200MB inside `load_market`). 1,032 events, 570 symbols, 303 event days,
first 2024-01-12. Full output: `reports/research/signal-cards/
sue_8k_event.json` / `.md`.

| horizon | mean excess | t (dates) | hit | book 20bp excess/yr |
|---|---|---|---|---|
| 1d | -0.16% | -1.4 | 49% | -- |
| 5d | -0.43% | -1.9 | 50% | -41.9% |
| **20d** | **0.48%** | **1.06** | 50% | **-0.14%** |
| 60d | 2.01% | 1.8 | 48% | 2.3% |

Redated placebo (20 seeds, 20d): mean CAR 0.44%-1.95%, mean excess_ann
3.9%-17.8%/yr -- the placebo alone earns far more than the real book.

## Admission rule (reused verbatim, `fundamentals-v1-manifest.json`)

`beats_redated AND t_dates >= 3 at h=20 AND calendar-time book positive
excess at 20bp in both the full and 2024+ windows.`

| leg | required | actual | pass? |
|---|---|---|---|
| t_dates (h20) | >= 3 | 1.064 | **no** |
| beats_redated | true | false (real -0.14%/yr vs placebo +3.9% to +17.8%/yr) | **no** |
| book positive 20bp, full window | > 0 | -0.14%/yr | **no** |
| book positive 20bp, 2024+ window | > 0 | -0.14%/yr (identical to full -- 8-K coverage bounds both windows to 2024-2026) | **no** |

**Verdict: refuted.** All three required legs fail; this is not a
borderline case.

## Comparison to the refuted filing-date card

| metric | filing-date (refuted) | 8-K timestamp (this iteration) |
|---|---|---|
| t_dates (h20) | 3.564 | 1.064 |
| CAR (h20) | +0.71% | +0.48% |
| book 20bp excess/yr, full | -3.9% | -0.14% |
| book 20bp excess/yr, 2024+ | **+1.5%** | **-0.14%** |

Moving `visible_at` earlier did not recover the effect the refuted card was
missing. The t-statistic got weaker (3.56 -> 1.06, well below the 3.0 bar
both versions needed), and the one leg the filing-date version actually
passed (2024+ book positive excess) flipped negative under the 8-K timing.
The mechanism proposed by Battalio & Mendenhall (2006) -- that trading on
the exact announcement time recovers profitable PEAD -- is not confirmed in
this project's own data, cost model, and universe for classic SUE.

## K1/K2 (information only, not a gate)

This is a single signal card, not a sleeve compared to S3; K1/K2 (rebalance-
offset-median Sharpe vs S3's anchor/stress medians, thresholds 1.19/0.65)
do not formally apply. Read informally against those numeric bars: 20bp
Sharpe 0.611 and 10bp Sharpe 0.851, both below the 1.19 anchor threshold;
the 20bp Sharpe (0.611) is also below the 0.65 stress threshold. Even
informally, this candidate does not look like a K1 pass.

## Decision

`dir:pead_xbrl_sue_filing_date` / `dir:pead_xbrl_8k_llm`'s accounting half
stays **refuted** under the 8-K timestamp. Per T-20260928-14's own
`done_when`, the second-stage DeepSeek guidance/tone overlay is **not**
queued, and `reports/research/control/autonomous-queue.md` is left
untouched.
