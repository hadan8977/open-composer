# Hypotheses: h20260929_70_net_share_issuance

## H1: Low net share issuance predicts higher returns in the ADV top-1500 pool since 2024

- Hypothesis: stocks that reduced or held their share count over 252 sessions outperform stocks that issued shares over the next 20-60 sessions from a next-open entry, beyond size and 12-1 momentum.
- Failure mode: (a) the published effect has decayed (QuanterLab 2026-08 tie); (b) cover-page share counts are noisy (splits, dual class) despite the cleaning rules; (c) the IC is a size or momentum proxy; (d) the edge sits in the microcap issuer tail that cannot be shorted.
- Measurement: signal_card rank cards (20d, 60d) plus scripts/nsi_ic_test.py: 2024+ Newey-West t, full-sample sign, distinct_from_controls, residual retention on log dollar ADV and 12-1 momentum.
- Benchmark family: shuffle placebo (signal_card), NSI126 control, universe equal weight.
- Stop/Pivot criterion: all four conditions at 20d or 60d, otherwise stop and record refuted. Nothing is relaxed after results.

## H2 (information only): the edge is on the issuer (short) side

- Measurement: only if H1 passes: avoid-top-quintile control on top-1500 equal weight versus long-only and long/short books.
