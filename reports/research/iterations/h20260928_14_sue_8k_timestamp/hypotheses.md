# H-20260928-14-followup: SUE/PEAD priced from the 8-K announcement, not the 10-Q/10-K filing

## Hypothesis

The standardized-unexpected-earnings (SUE) event card (`dir:pead_xbrl_sue_filing_date`,
`reports/research/signal-cards/pead_sue_eps_event.json`) was refuted because
its `visible_at` was the first NYSE session after the 10-Q/10-K filing date,
which lags the actual earnings announcement (8-K Item 2.02) by days to
weeks -- the card's own amendment note named this as the reopen condition.
This iteration (SUE8K01) tests the single-variable fix: same `sue_eps`
values, same universe/top_n/threshold/horizon/costs/placebo, only `visible_at`
moved to the first NYSE session after the matching 8-K Item-2.02 filing's
EDGAR `acceptanceDateTime`.

One candidate, no ranking between variants:

- **SUE8K01**: event mode, `sue_eps >= 2.0`, direction +1, primary horizon 20
  sessions, `visible_at` = 8-K/2.02 acceptance-time usable session (nearest
  preceding 8-K per CIK within a 65-day window).

## Failure mode

(1) 8-K/2.02 acceptance-timestamp data only exists locally for 2024-01-02
through 2026-09-17 (`data/features/earnings_events/`), so this test cannot
reproduce the refuted card's 2016-2026 sample -- it is a smaller, more
recent-only test by construction, not a like-for-like rerun. (2) Companies
that report results directly in the 10-Q/10-K without a standalone 2.02
exhibit have no match and are dropped, further shrinking the sample. (3)
Independent evidence (Subrahmanyam replication, already cited in the
refuted card's own rationale) found classic SUE-based PEAD ex-microcap is
not significant (t=1.43) through Dec 2024 -- any admission here should be
read as a microcap-tilted effect. (4) Moving visible_at earlier changes
which stocks are in the PIT universe on the event date and which session's
open the trade fills at -- a mechanical, not just a statistical, change from
the refuted card.

## Measurement

`open_composer/research/signal_card.py`'s standard event-mode battery: mean
excess return by horizon/year/tier, hit rate, a calendar-time long-only book
at 10 and 20bp, and the tool's own built-in redated-event placebo (20 seeds,
each event moved to a random session of the same stock within +/-126
sessions). Admission is the event_long rule already preregistered in
`reports/research/signal-cards/fundamentals-v1-manifest.json`, reused
verbatim: `beats_redated AND t_dates >= 3 at h=20 AND book positive excess at
20bp in both the full and 2024+ windows`.

## Stop/Pivot criterion

If SUE8K01 fails any leg of the admission rule, the verdict is "stays
refuted" for `dir:pead_xbrl_sue_filing_date`/`dir:pead_xbrl_8k_llm`'s
accounting half, and no second-stage DeepSeek guidance/tone overlay is
queued (per T-20260928-14's own `done_when`). If it passes, the queue gets a
new block for the DeepSeek-read tone/guidance pilot (2 quarters), per
`reports/research/control/registry-backfill-2026-09-28.md` Job B's plan for
`dir:pead_xbrl_8k_llm`.
