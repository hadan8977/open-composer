# Decision record: h20260928_14_sue_8k_timestamp

## Path

`pead_sue_8k_timestamp_signal_screen` -- build a new visible_at join
(`scripts/build_sue_8k_visible.py`, new file, does not modify any existing
lane/batch/signal_card file) that moves the refuted `pead_sue_eps_event`
card's event timestamp from the first NYSE session after the 10-Q/10-K
filing date to the first NYSE session after the matching 8-K Item-2.02
exhibit's EDGAR `acceptanceDateTime`, then run the unmodified
`open_composer/research/signal_card.py` event mode against it (SUE8K01),
through `scripts/run_capped.sh --mem 1.8G` with duckdb `memory_limit<=1200MB`.

## Decision

Proceed: build the join, run the one preregistered candidate, and report the
result against the admission rule already frozen in
`reports/research/signal-cards/fundamentals-v1-manifest.json`. This is the
exact reopen condition the refuted card's own amendment note named for
itself (2026-09-24T05:20:00Z): "usable session = first NYSE session after
the 10-Q/10-K filing date, which usually lags the earnings press release
(8-K item 2.02) by days to weeks; the card measures drift after the XBRL
filing, the tradeable version with free data."

## Reason

Both required data ingredients already exist locally: `sue_eps` (unchanged,
`data/features/sec_fundamentals_daily`) and 8-K/2.02 acceptance timestamps
(`data/features/earnings_events`, built under a separate, already-sourced
task). No new mechanism, admission rule, or cost convention is introduced --
only the single variable the refuted card itself flagged as the fix. The
main disclosed risk -- the 8-K timestamp table only covers 2024-01-02 to
2026-09-17, so this test cannot reproduce the refuted card's full 2016-2026
sample and is a smaller, more recent-only test by construction -- is carried
in `direction-review.json`'s `remaining_evidence_gap`, not treated as
resolved.

## Next iteration suggestion

Main session: build `data/features/sue_8k_visible/{year}.parquet` via the
new `scripts/build_sue_8k_visible.py`, run `signal_card.py` for SUE8K01
through `scripts/run_capped.sh --mem 1.8G`, then judge against the admission
rule and write `results.json`/`report.md`. If SUE8K01 passes, append a new
queue block at the end of `reports/research/control/autonomous-queue.md`
for the DeepSeek-read guidance/tone overlay second stage (2 quarters pilot,
per Job B's plan for `dir:pead_xbrl_8k_llm`); if it fails any leg, leave the
queue untouched and record the refuted verdict in the registry.

## Result (2026-09-28) -- stop

Join build: `scripts/build_sue_8k_visible.py` matched 11,556 of 77,480
sue_eps event rows to a preceding 8-K/2.02 filing (1,211 symbols,
2024-01-03 to 2026-09-15). Signal card SUE8K01 (top_n=3000, threshold=2.0,
h=20): 1,032 events, 570 symbols. `t_dates=1.064` (needs >=3),
`beats_redated=False` (real 20bp book excess -0.14%/yr vs the redated
placebo's 20-seed range +3.9% to +17.8%/yr), `book_positive_20bp=False` in
both the full and 2024+ windows (both -0.14%/yr, identical because the 8-K
coverage window bounds both to 2024-2026). Full numbers:
`reports/research/signal-cards/sue_8k_event.json` / `.md`, `results.json`,
`report.md`.

**Decision: stop.** All three required legs of the event_long admission
rule fail, not borderline. Compared with the refuted filing-date card
(t_dates 3.564, 2024+ book excess +1.5%/yr), moving `visible_at` to the 8-K
announcement time made the signal weaker on the t-statistic and flipped the
one leg the filing-date version had passed (2024+ book excess) negative.
The reopen condition the refuted card named for itself does not recover a
tradable effect in this project's data, costs, and universe.

`dir:pead_xbrl_sue_filing_date` / `dir:pead_xbrl_8k_llm`'s accounting half
stays refuted. Per T-20260928-14's own `done_when`, no second-stage
DeepSeek guidance/tone overlay is queued, and
`reports/research/control/autonomous-queue.md` is left untouched.

**Caveat.** The 8-K/2.02 acceptance-timestamp table only covers
2024-01-02 to 2026-09-17, so this test cannot reproduce the refuted card's
full 2016-2026 sample; it is a smaller, more recent-only test by
construction (disclosed in `direction-review.json`'s
`remaining_evidence_gap`), not a like-for-like rerun.

**Reopen if:** the 8-K/2.02 timestamp coverage is extended back to 2016+
and the test is rerun on the full sample, or a materially different SUE
construction (not just the timestamp) is proposed with new evidence.
