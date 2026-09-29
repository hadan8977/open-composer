# H-20260928-22: LLM news-conditioned momentum re-ranking (Anic et al. 2025 replication)

Backtest: `scripts/run_h20260928_22_news_momentum.py`, scoring:
`scripts/score_h20260928_22_news_momentum.py --scope clean_plus_refutation14`. Raw output:
`reports/research/iterations/h20260928_22_llm_news_momentum_filter/results.json`.
Preregistration: `direction-review.json`, `candidate-manifest.json` (amendments[0]
AMEND-1..3, amendments[1] AMEND-4).

## Verdict

**Refuted.** Both look-ahead-free evidence windows show L (DeepSeek-scored re-rank/
re-weight of the top-2-decile momentum pool) underperforming B (plain 12-1 momentum top
decile, equal weight) after 10bp round-trip costs:

- CLEAN window (5 month-end formations strictly after the scoring model's disclosed
  knowledge cutoff): Sharpe(L) = -1.072 < Sharpe(B) = -0.833.
- Contaminated-refutation14 window (14 most recent pre-cutoff month-ends, scored
  newest-first; look-ahead here can only flatter L): CAGR(L) = 78.1% < CAGR(B) = 117.7%.

Either condition alone is decisive under the preregistered AMEND-4 rule
(`candidate-manifest.json` `amendments[1]`); both fired, so the placebo (P) and
random-control (R) checks were not needed to reach the verdict, though they are reported
below for completeness.

## Model and cutoff

Scoring model: `Deepseek-v4-flash` (the only model id accepted by the configured
text-scoring endpoint; a `/models`-style discovery probe found no older-model alternative
served). Disclosed knowledge cutoff: April 2026, per the Puter model-aggregator page
(`puter-deepseek-v4-flash.html`, claim `deepseek_v4_flash_knowledge_cutoff_puter`); the
official DeepSeek docs confirm the 2026-04-24 release and parameters
(`deepseek-api-docs-news260424.html`) but do not themselves state an explicit cutoff date.
CLEAN window = first month-end after April 2026 (2026-05-29) through the last panel date
(2026-09-17): 5 formations. Contaminated window = all remaining pre-cutoff month-ends back
to 2016; the refutation-only subset used here is the 14 most recent
(2025-03-31..2026-04-30).

## Calls made

1451 DeepSeek scoring calls completed (`data/features/h20260928_22_news_momentum_scores/items.parquet`,
variant=L only; P is derived from L via a seeded within-month permutation, zero extra
calls, per AMEND-2). Coverage: the 5 CLEAN formations plus the 14-month refutation window
(1450 target items) plus one earlier throwaway probe call outside both windows. Runs took
4 attempts across roughly 5.5 hours due to shared-endpoint rate limiting (HTTP 429 at
20:48:25Z and again at 21:19:02Z UTC 2026-09-28, escalating to a 2-hour backoff per the
coordinator's policy before the final successful attempt at 02:29:31Z UTC 2026-09-29).

## Results

### CLEAN window (5 formations, next-open fill)

| book | Sharpe 10bp | CAGR 10bp | MaxDD 10bp | Sharpe 20bp | CAGR 20bp |
|---|---:|---:|---:|---:|---:|
| B (rule baseline) | -0.833 | -56.9% | -36.2% | -0.841 | -57.1% |
| L (LLM re-rank) | -1.072 | -53.9% | -31.3% | -1.096 | -54.5% |
| P (headline-shuffle placebo) | -0.817 | -45.9% | -31.3% | -0.842 | -46.6% |
| R (median of 5 seeds) | -0.749 | -44.3% | -30.2% | -0.771 | -44.9% |

L-B Sharpe = -0.239 (fails the original Sharpe(L)>=Sharpe(B)+0.10 bar outright, and fails
AMEND-4's weaker "> 0" bar too). P-B Sharpe = +0.016 (the placebo does *not* reproduce a
positive L gain, because there is no positive L gain to reproduce).

### Contaminated-refutation14 window (14 most recent pre-cutoff month-ends, 2025-03-31..2026-04-30)

| book | Sharpe 10bp | CAGR 10bp | MaxDD 10bp |
|---|---:|---:|---:|
| B | 1.688 | 117.7% | -29.5% |
| L | 1.583 | 78.1% | -20.7% |
| R (median of 5 seeds) | 1.683 | 89.2% | -21.3% |

L-B CAGR = -39.6 pp, L-B Sharpe = -0.105. Look-ahead exposure in this window can only
flatter L (the scoring model has already seen these headlines' outcomes during training),
so a negative gain here is decisive refutation evidence on its own, independent of the
CLEAN-window result.

### Informational: full period (2016-01-04..2026-09-17, includes both windows plus older history)

| book | Sharpe 10bp | CAGR 10bp | MaxDD 10bp |
|---|---:|---:|---:|
| B | 0.483 | 9.6% | -39.7% |
| L | 0.421 | 6.9% | -35.0% |

t-stat of the L-B monthly return difference (129 months): mean = -0.27%/mo, t = -1.84
(`results.json` `l_minus_b_monthly_return_diff_full_period`). |t| < 2, so not
independently significant, but directionally consistent with both look-ahead-free windows
(L underperforms B), not supportive of L.

### Informational: S3 / K1 comparison

L's full-period Sharpe (0.421, 10bp) is far below both the S3 date-neutral benchmark
(1.49, 2024-01..2026-09, supplied by the task brief) and the K1 promotion bar (1.19). This
comparison was requested for information only; it does not change the verdict, which was
already decided by the CLEAN and contaminated-refutation14 windows above.

## Known deviations from Anic et al. (2025) and disclosed limitations

- **E (baseline weight)**: set to equal-weight rather than the paper's value-weighted
  optimum, because this repo lacks a reliable PIT market-cap feature; this isolates the
  LLM re-weighting effect on top of the same base weighting B already uses.
- **Lookback / headline cap**: 30 days, capped at the 20 most recent headlines, vs. the
  paper's reported 1-day-lookback optimum; used because this repo's non-mega-cap news
  coverage is much sparser than the paper's universe.
- **Weighting formula**: `Wi = E * eta^score_i` (eta=5) is an interpretation of the
  paper's formula, whose superscript was lost in PDF text extraction; justified in source
  card `anic2025_weighting_formula` from the surrounding prose (eta described as a
  "scaling"/"multiplier" parameter, long-only, described dynamic range).
- **Anonymization coverage gap**: the SEC `company_tickers.json` map used for
  name-swap anonymization does not include every historical ticker (e.g. IMGN /
  ImmunoGen, likely delisted/acquired before the snapshot was taken), so a small number of
  headlines that name a company by name rather than ticker were not anonymized for those
  specific tickers. This is a partial-coverage limitation of the local anonymization step,
  not a look-ahead issue (headline dates are still PIT-filtered), and does not change the
  sign or the verdict of the result, but is disclosed here for completeness.

## Placebo and random-control checks (not decisive here, reported for completeness)

Because L did not show a positive gain over B in either look-ahead-free window, the
placebo-reproduction and beats-random conditions are moot (there is no positive L-over-B
gain for the placebo to reproduce, and L does not beat R's median Sharpe in the CLEAN
window: -1.072 vs -0.749). `results.json` `stop_continue_rule` records all five boolean
conditions explicitly.
