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

## Result (2026-09-24) -- stop

The feature was built for 2024-01..2026-09 (33 monthly checkpoints; `data/features/news_hf_reaction/`). The preregistered cards ran with `signal_card.py --batch reports/research/signal-cards/news-hf-v1-manifest.json` (top-3000 PIT universe, 20 bp). The summary is in `reports/research/signal-cards/news-hf-v1-summary.md`.

| card | mode | primary h | result | verdict |
|---|---|---|---|---|
| NHF01 `news_hf_reaction_raw` | rank | 5d | IC -0.005, t -0.9; T1 top-30 book -13.9%/yr excess | reject |
| NHF02 `news_hf_reaction_5d_sum` | rank | 5d | IC -0.003, t -2.5 (wrong sign vs the preregistered continuation); T1 book -6.3% full / -18.0% 2024+ | reject |
| NHF03 `news_hf_reaction_event_p90` | event | 5d | CAR -0.29%, t -1.9 over 20,448 events; calendar-time book -34.8%/yr | reject |

**Decision: stop.**
- The signed intraday news reaction does not predict continuation in the 2024-2026 US top-3000 universe at 1-60 day horizons. At 5 days the weak sign is reversal, not drift.
- This matches the direction-review risk, which found no 2023-2025 independent replication of the Jiang-Li-Wang mechanism.
- It does not raise the prior for `dir:ml_ranking_broad_universe_custom`. That row's reopen condition (text features) is still unmet in substance: the features exist but carry no standalone signal.

**Caveats.**
- The sample covers 2024+ only.
- The news source is Alpaca/Benzinga headlines.
- The 2024-01-02 overnight anchors used the incomplete 2023 month shards (see the `minute_shard_paths` docstring); this affects a handful of events.
- A reversal variant (direction -1) was not preregistered and is not claimed. Running it now would be a new trial after seeing these results.

**Reopen if:** a different news source with earlier timestamps (e.g. a PR-wire feed) or a published 2024+ replication of HF news drift appears.
