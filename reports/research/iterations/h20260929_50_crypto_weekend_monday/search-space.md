# Search Space: h20260929_50_crypto_weekend_monday

One path, three candidate rows (signal BTC, ETH, EW10), one analysis per row; no parameter search.

- Signal W: crypto return from Friday 16:00 America/New_York to Sunday 24:00 UTC (no crypto price at or after Monday 00:00 UTC).
- Groupings: W<0 vs W>=0 (gating), W<-3% vs rest (informational).
- ETFs: SPY, QQQ (gating), IWM (informational).
- Segments: gap (Friday close to Monday open, control), oc and o2o (gating).
- Samples: 2016-05+ (context), 2022-06+ and 2024-01-08+ (gating).
- Statistics: mean difference in bp, Welch t, group sizes; placebo 500 shuffles of W among weeks, seed 20260929.
- Continue rule frozen in candidate-manifest.json before any result; total budget 3.
