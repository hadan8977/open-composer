# Search Space: mom_multiasset_r1

The round contains five method paths and at most 60 deterministic candidates. It intentionally spends budget across economically distinct methods rather than dense tuning of one ROC rule. P1 covers ETF absolute/relative trend; P2 covers investable risk-adjusted sector rotation; P3 covers classic and blended long-only stock momentum; P4 tests 52-week-high and trend quality; P5 tests market-residual and sector-relative momentum.

All decisions use prior-session data. Monthly labels and ML work use a 21-trading-day purge and embargo. One-way cost scenarios are 5, 10 and 20 basis points. Capacity checks use current median dollar volume and maximum intended virtual capital. Every path includes equal-weight, market, sector/theme, cash and ex-post-best benchmarks.

Current-universe historical stock results are exploratory because PIT membership is unavailable. ETF history can support method comparison; stock promotion evidence starts at the frozen 2026-07-14 universe snapshot and accumulates in isolated virtual paper.
