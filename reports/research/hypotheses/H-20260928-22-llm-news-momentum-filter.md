---
card_id: H-20260928-22
status: executed, refuted (round 1, 2026-09-29)
lane: preregistered
previous: H-20260916-04
direction_id: dir:owner_chatgpt_systematic_investing_news_momentum_2026
iteration: h20260928_22_llm_news_momentum_filter
criteria:
  - name: clean_window_sharpe_L_minus_B
    threshold: 0
    direction: ">"
  - name: contaminated_refutation14_cagr_L_minus_B
    threshold: 0
    direction: ">"
---
# H-20260928-22 LLM news-conditioned momentum re-ranking (Anic et al. 2025 replication)

- Status: **executed, refuted** (round 1) -- hypothesis family: llm_news_score_reweight_momentum --
  layer: candidate re-ranking / re-weighting within an already-passing momentum book -- data tier:
  **tier 2** (LLM-scored text features on top of OHLCV-derived momentum)
- Previous link: H-20260916-04 (LLM acceptance judge, keep/half/skip, not yet executed; awaited a
  cheaper mechanistic test of "does an LLM reading news improve a momentum book at all" first)
- Iteration dossier: `reports/research/iterations/h20260928_22_llm_news_momentum_filter/`
  (direction-review, external-brief, candidate-manifest with 4 candidates and 2 rounds of
  preregistered amendments, search-space, data-feasibility, trial-ledger, results.json,
  report.md; passed `oc research direction-check`, `oc research iteration validate
  --stage pre-backtest` and `--stage final`)
- One-line hypothesis: does scoring the top-2-decile candidates of a 12-1 momentum book with a
  DeepSeek model reading anonymized, PIT-filtered news headlines, then re-ranking/re-weighting down
  to m=50 via the paper's `Wi = E * eta^score_i` exponential tilt (eta=5, 15% cap), raise the book's
  Sharpe over the plain rule baseline B (top decile, equal weight) after 10bp/20bp costs, in a
  look-ahead-free evaluation window?

## Why

Anic, Barbon, Seiz and Zarattini (2025, arXiv:2510.26228) report OOS Sharpe 1.06 (LLM re-ranked)
vs 0.79 (plain baseline), Jan2024-Mar2025, 2bp costs -- one independent published confirmation of
the mechanism. `dir:llm_acceptance_judge_forward_shadow` (H-20260916-04) proposes a richer, more
expensive local design (weekly keep/half/skip judge, adds insider/8-K data, budget 2, used 0);
this round is the cheapest decisive test of the underlying mechanism itself (does an LLM reading
recent firm-specific news improve re-ranking of an already-passing momentum book at all) before
spending the larger H-20260916-04 budget. `dir:news_attention_features` (refuted) tested a
different mechanism (raw attention/volume features from news counts, not LLM-scored content) and
does not bear directly on this question. Registry dedup
(`oc research directions check "LLM news score momentum reweight"`, 2026-09-28) found no exact
prior local test.

## Design

Universe: PIT largest-500 (`open_composer.research.signal_card.load_market(top_n=500)`). Baseline
B: 12-1 momentum top decile, monthly, equal weight (~50 names). Candidate pool for L: top-2
deciles (~100 names). L's score: DeepSeek-v4-flash reads anonymized headlines (Glasserman & Lin
2023 method -- company name/ticker replaced with "the company") from the prior 30 days (capped at
the 20 most recent, PIT-filtered via `visible_at`), returns a 0-1 score; no-news stocks default to
0 (raw 0.5, per the paper's own rule). Weights: `Wi = E * eta^score_i` (E = equal-weight baseline,
eta = 5, 15% per-stock cap with iterative renormalization), m = 50 selected. Placebo P: identical
mechanism, each stock's score swapped for a different, randomly matched candidate's score via a
seeded within-month derangement (zero extra DeepSeek calls, since the prompt carries no
stock-specific numeric content -- verified). Random control R: 50 names drawn uniformly from the
same top-2-decile pool, 5 seeds, no LLM call. Signal at month-end close, fill at next open, 10bp
and 20bp round-trip costs.

Two disclosed deviations from the paper: E is equal-weight (not the paper's value-weighted
optimum -- this repo lacks a reliable PIT market-cap feature); lookback is 30 days / 20-headline
cap (not the paper's 1-day-lookback optimum -- this repo's non-mega-cap news density is much
lower). The weighting formula's exponent was reconstructed from surrounding prose after a PDF
text-extraction gap lost the original superscript (documented in source card
`anic2025_weighting_formula`).

## Windows and amendments

CLEAN window: first month-end after DeepSeek-v4-flash's disclosed knowledge cutoff (April 2026,
Puter aggregator page, official DeepSeek docs confirm release but not an explicit cutoff) through
the last panel date (2026-09-17) -- 5 formations (2026-05-29, 06-30, 07-31, 08-31, 09-17), too few
for the original Sharpe(L)>=Sharpe(B)+0.10 rule to be informative alone. AMEND-4
(`candidate-manifest.json` `amendments[1]`) added a refutation-only, look-ahead-EXPOSED check on
the 14 most recent pre-cutoff month-ends (2025-03-31..2026-04-30, scored newest-first): since
look-ahead can only flatter L, a non-positive L-vs-B gain there is decisive on its own. Revised
3-way rule: **refuted** if either window shows L <= B (CLEAN Sharpe or contaminated CAGR);
**promising -> forward shadow** if both windows show a positive gain AND the placebo reproduces
<50% of it AND L beats R's median; **inconclusive -> forward shadow** otherwise. AMEND-1..3
(ordering newest-to-oldest, placebo-needs-zero-calls derivation, checkpointing/backoff policy) were
operational, not design, changes.

## Results

Executed 2026-09-29 (`scripts/score_h20260928_22_news_momentum.py --scope
clean_plus_refutation14`, 1451 DeepSeek calls across 4 attempts over ~5.5 hours of shared-endpoint
rate limiting; `scripts/run_h20260928_22_news_momentum.py`; `results.json`, `report.md`).
**Refuted -- both decisive conditions fired.**

CLEAN window (5 formations, 10bp): Sharpe(B) = -0.833, Sharpe(L) = -1.072 (L-B = -0.239, wrong
sign and far short of the original +0.10 bar). Placebo P Sharpe = -0.817 (P-B = +0.016). Random
control R median Sharpe = -0.749 (L does not beat R either).

Contaminated-refutation14 window (14 most recent pre-cutoff month-ends, look-ahead-exposed, 10bp):
CAGR(B) = 117.7%, CAGR(L) = 78.1% (L-B = -39.6 pp); Sharpe(B) = 1.688, Sharpe(L) = 1.583. Look-ahead
here can only flatter L, so this negative gap is decisive refutation evidence independent of the
CLEAN-window result.

Full-period (129 months) informational check: mean monthly L-B return = -0.27%, t = -1.84 (|t|<2,
not independently significant, but directionally consistent with both look-ahead-free windows).
L's full-period Sharpe (0.421, 10bp) is well below both the S3 date-neutral benchmark (1.49,
2024-01..2026-09) and the K1 promotion bar (1.19) -- informational only, not the basis of the
verdict.

Lesson: on this repo's data (equal-weight E, 30-day/20-headline-capped lookback,
DeepSeek-v4-flash), the LLM news-score re-rank/re-weight step made an already-passing momentum book
worse, not better, in every window tested -- opposite of the paper's own reported direction. The
placebo and random-control checks were not needed to reach the verdict (there was no positive L
gain for either to fail to explain), but both are consistent with a null-or-negative effect (P is
statistically indistinguishable from B; R's median beats L). Reopen only with a value-weighted PIT
market-cap feature (to match the paper's own E) or a materially denser news source (to match its
1-day-lookback optimum) -- not by re-tuning eta/m/cap on the same news_packets data. Does not
itself refute `dir:llm_acceptance_judge_forward_shadow` (H-20260916-04), which uses a different
scoring scheme (discrete keep/half/skip with reasons, not continuous exponential re-weight) and a
richer data layer (adds insider/8-K), but is one more negative data point against "an LLM reading
news headlines improves a momentum book" as a mechanism before that larger budget is spent.
