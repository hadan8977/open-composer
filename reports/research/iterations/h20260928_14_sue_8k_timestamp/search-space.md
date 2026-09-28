# Search space: h20260928_14_sue_8k_timestamp

One path, `pead_sue_8k_timestamp_signal_screen`, ONE preregistered candidate
(SUE8K01; see `candidate-manifest.json` for the full parameter set). This is
a lightweight, single-mechanism iteration (no campaign contract;
`single_mechanism_no_campaign_attestation: true`), matching the same pattern
as `h20260923_14_news_hf_reaction`.

No strategy backtest is run in this iteration. The "search space" here is
the single signal-card specification preregistered before
`open_composer/research/signal_card.py` is run against
`data/features/sue_8k_visible/*.parquet` -- not a parameter sweep over a
trading rule, and not a re-tuning of the refuted card's own parameters
(threshold, top_n, horizon, costs are all unchanged from
`reports/research/signal-cards/pead_sue_eps_event.json`).

## Windows

- Left feature (sue_eps): `data/features/sec_fundamentals_daily`, 2016-01-29
  through latest, unchanged from the refuted card.
- Right feature (8-K/2.02 acceptance time): `data/features/earnings_events`,
  2024-01-02 through 2026-09-17 only -- this bounds the joined result's
  usable window regardless of the left table's longer history. The refuted
  card's 2016-2026 "full" window cannot be reproduced under the 8-K
  timestamp; this is disclosed in `direction-review.json`, not hidden.
- Signal-card evaluation windows: the tool's own fixed convention, full
  sample plus a 2024-01-01+ "recent" window (`RECENT_START`), reported
  separately even though they now largely coincide given the right-table
  coverage limit above.

## Controls

Reused unchanged from the signal-card tool itself and from the refuted
card, not reinvented for this reopen:

- **Event mode (SUE8K01)**: redated-event placebo (20 seeds, each event
  moved to a random session of the same stock within +/-126 sessions).

## Admission rule

Reused verbatim from `reports/research/signal-cards/fundamentals-v1-manifest.json`
(`admission_rule.event_long`), not redefined here: `beats_redated AND
t_dates >= 3 at the primary horizon AND calendar-time book positive excess
at 20bp in both the full and 2024+ windows`.

K1/K2 (`docs/runbook-autonomous-round.zh.md` section 5) are computed and
reported in `results.json` for information only -- they compare a full
sleeve to S3 and do not formally apply to a single signal card.

## Fallback if the candidate fails

`dir:pead_xbrl_sue_filing_date` / `dir:pead_xbrl_8k_llm`'s accounting half
stays refuted. No second-stage DeepSeek guidance/tone overlay is queued (per
T-20260928-14's own `done_when` in
`reports/research/control/autonomous-queue.md`), and the queue is not
touched.
