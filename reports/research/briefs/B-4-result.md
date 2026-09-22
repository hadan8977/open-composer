# B-4 result (H-20260922-05), 2026-09-22

**Path A: the volatility target does not transfer as a universal improvement.** On
S1 it is a return tax (Sharpe 1.35 -> 1.05/1.13, CAGR 27.7% -> 14.7%/19.0%);
reject, S1 keeps no overlay. On S2 `s2_vt16` gives Sharpe 1.49 -> 1.80, drawdown
-20.3% -> -10.2%, CAGR 39.7% (still above SPMO 35.8%), 38.8% at 20 bp. It fails
the preregistered transfer bar only on the random-pick placebo (23.3%), which
H-20260918-05 already recorded at 20% for S2 -- inherited, not caused. Accept as a
risk overlay on a known beta basket, not as a selection edge.

**Path B: the dip boost pays.** `s3_vt40_boost60_h10` (raise the target to 60% for
10 sessions while QQQ > SMA200 and Wilder RSI(10) < 30) reaches 116.3% / -32.3% /
Sharpe 1.82 against the frozen vt40's 98.3% / -30.2% / 1.66; holdout Sharpe 2.21;
113.7% at 20 bp; calendar-shift placebo 0/20 on anchor return, 1/20 on holdout
Sharpe. All four variants improve monotonically in target and hold. Because the
multiplier is capped at 1.0, the boost can only move exposure toward the unscaled
S3 book that is already live, so it is strictly less risky than the authorized
position.

**Recommendation for the 2026-10-01 renewal.** S3 -> vt40 + dip boost 60/10. S2 ->
vt16. S1 unchanged. top50 unchanged (its book is a dynamic PIT model-ranking
portfolio and cannot be regenerated in this engine).

**Caveats.** 14 dip signals in the whole panel, 72 boosted anchor sessions; the
sample contains no real bear market and the boost adds exposure into falls.
