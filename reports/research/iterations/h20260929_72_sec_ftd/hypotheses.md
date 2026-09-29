# Hypotheses: h20260929_72_sec_ftd

## H1: high FTD balances predict lower returns in the ADV top-1500 pool since 2024

- Hypothesis: stocks with a high fails-to-deliver balance (relative to shares outstanding or to dollar volume) underperform over the next 20-60 sessions from a next-open entry, after the SEC publication lag.
- Failure mode: (a) the ~15 day publication lag removes the short-horizon signal; (b) FTD also comes from long sales and operational fails (SEC caveat); (c) the effect lives in hard-to-borrow microcaps outside the ADV top-1500 / price >= 5 pool; (d) ticker reuse and bad prints add noise despite the 20% price rule.
- Measurement: signal_card rank cards (20d, 60d) plus scripts/ftd_ic_test.py: 2024+ and full-sample RankIC of -signal, Newey-West t.
- Benchmark family: shuffle placebo (signal_card), ftd_dummy control, universe equal weight.
- Stop/Pivot criterion: 2024+ IC positive after the sign flip with NW |t| >= 2.5 and full-sample same sign at 20d or 60d; else stop and record refuted. Nothing is relaxed after results.
