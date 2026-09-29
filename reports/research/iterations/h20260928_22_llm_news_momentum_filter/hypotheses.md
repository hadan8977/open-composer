# H-20260928-22: LLM news-conditioned momentum re-ranking (Anic et al. 2025 replication)

## Hypothesis

A DeepSeek score (0-1, from anonymized firm-specific news headlines of the prior 30 days,
capped at the 20 most recent) applied to the top-2 deciles (~100 names) of a 12-1 momentum
ranking on Open Composer's PIT largest-500 universe, then used to re-rank and re-weight
down to m=50 names via the paper's own `Wi = E * eta^score_i` tilt (eta=5, 15% per-stock
cap), raises the book's Sharpe ratio over the plain rule baseline B (top decile, equal
weight, ~50 names) after 10bp and 20bp round-trip costs, in a CLEAN evaluation window that
starts strictly after the scoring model's own disclosed knowledge cutoff (DeepSeek V4
Flash, April 2026) — mirroring the mechanism, prompt and weighting Anic, Barbon, Seiz and
Zarattini (2025, arXiv:2510.26228) report (OOS Sharpe 1.06 vs 0.79, Jan2024-Mar2025, 2bp
costs).

## Failure mode

The most likely failure mode is that any apparent Sharpe lift from L over B is not driven
by genuine news content but by (a) broadening the candidate pool from decile-1-only to
decile-1+2 before re-weighting down to 50, or (b) the LLM's re-ranking/tilt acting as
noise that happens to reduce concentration risk regardless of what the headlines say. The
headline-shuffle placebo P (identical mechanism, but each stock scored on a different,
randomly matched candidate's headlines) and the random-selection control R (50 names drawn
uniformly from the same top-2-decile pool, 5 seeds, no LLM call) are designed to catch
exactly this: if P captures most of L's lift, or if L does not beat R's median, the
apparent effect is not attributable to the LLM reading real, relevant news.

## Measurement

Monthly-formed cohorts via `open_composer.research.signal_card` (`load_market`,
`topk_cohorts`, `hold`, `book_returns`): B, L, P and R books' Sharpe, CAGR and max drawdown
at 10bp and 20bp per side, computed separately for the CLEAN window (formations
2026-05-29, 2026-06-30, 2026-07-31, 2026-08-31) and the contaminated (pre-cutoff) window,
which is reported but never counted toward the verdict. Also reported: the t-stat of the
L-B monthly return difference, and L's Sharpe against S3 (date-neutral 1.49,
2024-01→2026-09) and K1 (bar 1.19) for information only.

## Stop/Pivot criterion

Superseded by AMEND-4 (`candidate-manifest.json` `amendments[1]`), applied because the
original CLEAN window has only 5 monthly formations, too few for the Sharpe(L) >=
Sharpe(B)+0.10 threshold to be informative on its own. The revised, 3-way rule:

- **Refuted** if either window shows L failing to beat B: CLEAN-window (10bp)
  Sharpe(L) <= Sharpe(B), OR the contaminated-refutation14 window (the 14 most recent
  pre-cutoff month-ends, scored newest-first, look-ahead-exposed) shows L's CAGR <= B's
  CAGR. Look-ahead can only flatter L, so a non-positive gain even with look-ahead
  exposure is decisive negative evidence on its own.
- **Promising -> forward shadow** if both windows show a positive L-over-B gain, AND the
  headline-shuffle placebo P reproduces less than 50% of L's CLEAN-window gain over B, AND
  L's CLEAN-window Sharpe beats R's median Sharpe (5 seeds).
- **Inconclusive -> forward shadow** otherwise (both windows positive but the placebo or
  random-control condition is not met).

If the verdict is refuted, no LLM news-conditioned re-ranking is added to any live or
forward-tracked book on this evidence, and the autonomous queue is not touched.
