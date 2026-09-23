# Search space: h20260923_14_news_hf_reaction

One path, `news_hf_reaction_signal_screen`, three preregistered candidates
(NHF01, NHF02, NHF03; see `candidate-manifest.json` for the full parameter
set of each). This is a lightweight, single-mechanism iteration (no campaign
contract; `single_mechanism_no_campaign_attestation: true`), matching the
same pattern as `h20260923_13_orb_stocks_in_play`.

No backtest is run in this iteration. The "search space" here is the set of
signal-card specifications preregistered before the main session runs
`signal_card.py --batch` against
`reports/research/signal-cards/news-hf-v1-manifest.json` -- not a
parameter sweep over a trading rule.

## Windows

- Feature coverage: 2024-01-01 through the news archive's latest date
  (2026-09-09 as of this build); SIP minute bars 2023+.
- Signal-card evaluation windows are the tool's own fixed convention: full
  sample plus a 2024-01-01+ "recent" window, reported separately (see
  `open_composer/research/signal_card.py`'s `RECENT_START`).

## Controls

Reused unchanged from the signal-card tool itself, not reinvented per
direction:

- **Rank mode (NHF01, NHF02)**: within-day shuffle placebo (10 seeds), a
  252-session-stale placebo, overlap with the four standard controls
  (momentum_12_1, reversal_5d, size, volatility).
- **Event mode (NHF03)**: redated-event placebo (20 seeds, each event moved
  to a random session of the same stock within +/-126 sessions).

## Admission rule

Reused verbatim from `reports/research/signal-cards/library-v1-manifest.json`
(`admission_rule` block), not redefined here:

- rank: `stable_years AND beats_shuffle AND (T1 or T2 top-30 book positive
  excess at 20bp in both the full and 2024+ windows) AND max |t_nonoverlap|
  >= 2.5 with the preregistered sign`
- event (long): `beats_redated AND t_dates >= 3 at the primary horizon AND
  calendar-time book positive excess at 20bp in the full and 2024+ windows`

## Fixed budget

3 candidates, no ranking between them, no multiple-comparisons adjustment
needed beyond what the shared admission rule already enforces across the
whole signal library. This iteration's own compute budget was ~75 minutes
(search, data-feasibility check, build script + tests, one validation month,
dossier); the multi-year feature build itself is launched detached/resumable
and continues outside that budget.
