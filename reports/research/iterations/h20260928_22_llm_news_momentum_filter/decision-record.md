# Decision record: H-20260928-22 LLM news-conditioned momentum re-ranking

## Path

`llm_news_momentum_filter_vs_baseline` — four preregistered candidates (B rule baseline,
L DeepSeek-scored re-rank/re-weight, P headline-shuffle placebo, R random-selection
control, 5 seeds), evaluated with `open_composer.research.signal_card` on the PIT
largest-500 universe, monthly rebalance, 10bp/20bp costs, next-open fill.

## Decision

**Refuted** (`results.json` `stop_continue_rule.verdict`), computed under the AMEND-4
3-way rule. Both look-ahead-free evidence windows show L underperforming B:

- CLEAN window (5 formations, 10bp): Sharpe(B) = -0.833, Sharpe(L) = -1.072
  (L-B = -0.239). `condition_refuted_clean_le_b = true`.
- Contaminated-refutation14 window (14 most recent pre-cutoff month-ends,
  2025-03-31..2026-04-30, 10bp, look-ahead-exposed so can only flatter L): CAGR(B) =
  117.7%, CAGR(L) = 78.1% (L-B = -39.6 pp); Sharpe(B) = 1.688, Sharpe(L) = 1.583.
  `condition_refuted_contaminated_le_b = true`.

Either condition alone is decisive per the preregistered rule; both fired. Source:
`reports/research/iterations/h20260928_22_llm_news_momentum_filter/results.json`. This is
a **stop**: no forward-shadow tracking task is queued, and no LLM news-conditioned
re-ranking is added to any live or forward-tracked book on this evidence.

## Reason

The mechanism (LLM re-ranks/re-weights an already-passing momentum book using recent
firm-specific news) has one independent published confirmation (Anic et al. 2025) and one
local proposed-but-unexecuted forward-shadow design (H-20260916-04); this round is the
cheapest decisive local test of the mechanism itself, using a placebo and a random control
so a positive result cannot be mistaken for pool-broadening or re-weighting noise. On this
repo's data (PIT largest-500 universe, 30-day/20-headline-capped lookback, equal-weight E,
DeepSeek-v4-flash), the LLM re-rank/re-weight step did not reproduce the paper's reported
lift; it made the book worse in both the small clean sample and the larger
look-ahead-exposed sample, so the negative-control machinery (P, R) was not needed to
reach a verdict — the primary comparison against B already refutes the hypothesis.
Informational full-period comparison (`results.json` `l_minus_b_monthly_return_diff_full_period`):
mean monthly L-B return = -0.27%, t = -1.84 (n=129 months) — directionally consistent
with the two look-ahead-free windows, not independently decisive (|t|<2), but not
supportive of L either.

## Next iteration suggestion

Refuted: close this specific replication without reopening H-20260916-04 on this evidence
alone, since H-20260916-04 tests a materially different scoring scheme (3-way judge, not
continuous re-weight) and data layers (adds insider/8-K, not news-only). Per the
preregistered rule, the autonomous queue is not touched by this iteration. If a news-LLM
direction is revisited, prioritize checking whether the paper's own value-weighted E (not
this repo's equal-weight substitution) or its 1-day lookback (not this repo's 30-day/
20-headline cap, used because this repo's non-mega-cap news density is much lower) is
material to the sign of the effect before re-running the same mechanism again.

## Redaction note (2026-09-28, no design change)

`candidate-manifest.json`'s `amendments[1].changes[0].resolution` text originally named
the scoring endpoint's base URL (from the owner's private config file) while describing
the older-model-availability probe. Per a coordinator data-hygiene instruction, that text
was replaced with "the configured text-scoring endpoint" (redaction only, wording change
in the manifest's prose only). This changed the manifest file's own sha256 (old
`a2b4e9dbee7bfd4a4d769f70f60f0a6cdea927212d366b3a3d20580dd8deb138` -> new
`fee6dfe1238a7ace7ba42dd06bfcc98dfbff78c491ff5baa1e60e7676d077478`, propagated to
`search-space.json`'s `candidate_manifest_sha256`) but no candidate definition, contract,
weight, window, or the AMEND-4 verdict rule itself changed in any way; `oc research
iteration validate --stage pre-backtest` was rerun after the edit and still passes.
