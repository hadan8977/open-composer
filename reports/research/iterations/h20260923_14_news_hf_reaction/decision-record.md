# Decision record: h20260923_14_news_hf_reaction

## Path

`news_hf_reaction_signal_screen` -- build the signed high-frequency
news-return feature (Jiang, Li & Wang 2019/2021) on local news + SIP minute
bars, and preregister three signal-card specifications (NHF01, NHF02, NHF03)
against the admission rule already fixed in
`reports/research/signal-cards/library-v1-manifest.json`. No strategy
backtest is run in this iteration.

## Decision

Continue: build the feature at scale (month-by-month, checkpointed,
memory-capped), then hand off `reports/research/signal-cards/news-hf-v1-
manifest.json` to the main session to run through `signal_card.py --batch`.
This iteration itself does not run any signal card and makes no
profitability claim.

## Reason

Both required data ingredients (Alpaca/Benzinga news, SIP minute bars) are
already in local inventory; the mechanism is peer-reviewed and mechanistically
distinct from the already-refuted count-based `dir:news_attention_features`;
a one-month real-data validation build (2025-06, 10,073 rows, 3,279 symbols)
completed cleanly with the news+non-news=overall identity holding exactly
(max abs error 0.0) and no nulls/infs, confirming the construction is
implementable and internally consistent before committing to the full
multi-year build. The main open risk -- no 2023-2025 independent replication
of the HF mechanism found this pass, and one 2026 adaptation (day-level,
monthly, China) returning a null result -- is disclosed in
`direction-review.json` and `external-brief.json` rather than treated as
resolved, and is exactly what the deferred signal-card test (not this
iteration) will speak to.

## Next iteration suggestion

Main session: run `uv run python -m open_composer.research.signal_card
--batch reports/research/signal-cards/news-hf-v1-manifest.json` once the
feature build covers the years it needs and once the currently-running
signal-card batch job (`library-v1-manifest.json`) has finished, so the two
memory-capped jobs do not overlap on this 3.9GB box. If any of NHF01-03 is
admitted to the signal library, the next step is combining it with the
existing library (correlation, incremental Sharpe/drawdown) per
`docs/plan-research-coverage-2026-09-23.zh.md` section 6.2 -- not a standalone
strategy promotion, since a single signal is never held to the strategy bar.
