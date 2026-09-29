# Report: h20260929_33_crypto_trend (T-20260929-33)

Question: can published crypto trend/momentum rules (Alpaca spot, long-only) reach
the 2026-09-28 relaxed keep bar K1 (standalone, ~=S3) or K2 (S3 diversifier), reopening
`dir:crypto_trend_btc` and `dir:crypto_xs_momentum`.

Source: `reports/research/screens/h20260929_33_crypto_trend/leaderboard.json` and
`reports/research/iterations/h20260929_33_crypto_trend/results.json` (derived from the
same leaderboard, adds the K1/K2 pass/fail computation against the frozen bars).

## Verdict: not kept -- no candidate clears K1 or K2

13 candidates run (12 mechanism + 1 internal placebo, `n_trials=13`). K1 needs judged
(median-offset for M-freq, single value for D-freq) net-10bp Sharpe >=1.19 anchor and
>=0.65 stress; K2 needs a diversifier edge (63-session inverse-vol blend with S3 vs a
vol-matched S3+SHY control) >=0.05 in BOTH anchor and stress. None of the 12 mechanism
candidates reach either bar. The 30bp crypto-fee re-check preregistered in
`direction-review.json` was therefore never triggered (it only applies to candidates
that clear K1/K2 at 10bp).

| candidate | freq | anchor Sharpe | stress Sharpe (yrs) | select Sharpe | K2 anchor edge | K2 stress edge | DSR (anchor) |
|---|---|---|---|---|---|---|---|
| BTC_BUYHOLD | D | 0.621 | 1.125 (7.4) | 1.279 | -0.261 | +0.530 | 0.2331 |
| BTC_SMA200 | D | 0.485 | 0.928 (6.8) | 0.962 | -0.427 | +0.375 | 0.1604 |
| BTC_TSMOM_1M | M | 0.382 | 1.035 (7.2) | 1.027 | -0.364 | +0.447 | 0.1366 |
| BTC_TSMOM_3M | M | 0.526 | 1.184 (7.1) | 1.046 | -0.578 | +0.440 | 0.1785 |
| BTC_TSMOM_6M | M | 0.688 | 1.077 (6.9) | 0.988 | -0.392 | +0.386 | 0.2807 |
| BTC_DONCHIAN_ENSEMBLE | D | 0.886 | 0.600 (6.6) | 1.342 | +0.101 | -0.086 | 0.3282 |
| **BTC_DONCHIAN_ENSEMBLE_VT40** | D | **0.906** | 0.706 (6.6) | 1.372 | **+0.164** | -0.064 | 0.3529 |
| CRYPTO_DONCHIAN_TOP3 | M | 0.345 | 0.422 (4.5) | 0.672 | -0.480 | -0.225 | 0.1252 |
| BTC_ETH_DUAL_MOM | M | 0.407 | 1.214 (7.0) | 0.840 | -0.579 | +0.379 | 0.1313 |
| CRYPTO_XS_TOP3_EW | M | 0.039 | 1.391 (7.0) | 0.736 | -0.660 | +0.578 | 0.0504 |
| CRYPTO_XS_TOP3_IVOL | M | 0.115 | 1.418 (7.0) | 0.742 | -0.608 | +0.613 | 0.0646 |
| CRYPTO_XS_TOP3_EW_VT40 | M | 0.024 | 1.478 (7.0) | 0.950 | -0.612 | +0.531 | 0.0475 |
| BTC_RAND_PLACEBO (control) | D | 0.004 | 0.048 (7.4) | 0.033 | -0.567 | -0.261 | 0.0448 |

All figures are 10bp, close-signal -> next-open-fill, per screen_lane's frozen contract.
"stress Sharpe (yrs)" is the judged stress-window Sharpe and the number of years of
history the judged offset actually covers within the 2016-05-02..2023-09-15 stress
window (all candidates clear the project's 2-year minimum; no candidate needed a
"stress sample short" or "stress period pending" label). Every candidate comfortably
beats BTC_RAND_PLACEBO's anchor Sharpe (0.004) and stress Sharpe (0.048) -- the negative
result is not explained by "the whole approach is indistinguishable from random BTC
exposure"; the mechanisms do produce real, positive risk-adjusted returns, just not at
the bar S3 sits at.

**Best standalone candidate**: BTC_DONCHIAN_ENSEMBLE_VT40 (the 40%-vol-targeted version
of the Donchian-ensemble approximation of Zarattini/Pagani/Barbon 2025's mechanism).
Anchor Sharpe 0.906 is the highest of the 12, but still 24% short of the 1.19 K1 bar;
stress Sharpe 0.706 actually clears the 0.65 K1 stress bar on its own, so this candidate
fails K1 only on the anchor leg. It also has the best K2 anchor edge (+0.164, above the
0.05 bar) but its K2 stress edge is -0.064 (adding it to S3 would have *hurt* the
stress-window Sharpe of the combination) -- K2 requires both windows, so it fails.

**Reconciliation with the source paper's own reported Sharpe 1.56** (BTC-only,
2015-2025, per `reports/research/intel/I-20260923-02-hf-crypto-model-verification.md`'s
cross-check of the Concretum Group pages): that figure is a full-sample (2015-2025)
number under the paper's own cost/rebalance convention, not this project's specific
2024-01-08..2026-09-17 anchor window under a strict close-signal/next-open-fill 10bp
contract. BTC_DONCHIAN_ENSEMBLE's own *select*-window Sharpe (2023-09-18..2025-12-31,
1.342) is much closer to the paper's headline number than its anchor-window Sharpe
(0.886) -- consistent with 2024-2026 specifically being a weaker regime for BTC trend
than the paper's longer sample, not with an implementation error (the select-window
number shows the mechanism can reach paper-like Sharpe in-sample-ish; the anchor window,
which is what K1 is judged on, is harder). This is reported as the likely explanation,
not independently confirmed against the paper's own year-by-year breakdown (still
403-blocked).

**Cross-sectional momentum (CRYPTO_XS_TOP3_*)**: consistently the *worst* anchor-Sharpe
group (0.024-0.115) despite the *best* stress-Sharpe group (1.391-1.478) -- the 10-coin
altcoin universe's 2024-2026 cross-sectional momentum signal degraded sharply relative
to its 2016-2023 stress-window behavior. This is a genuinely different (weaker) result
than Liu-Tsyvinski-Wu's own long-short findings would suggest, consistent with
`dir:crypto_xs_momentum`'s original "stale sample" concern -- the long-only
reinterpretation tested here does not rescue it.

**CRYPTO_DONCHIAN_TOP3** is the weakest candidate overall (anchor 0.345, stress 0.422,
select 0.672) and has the shortest stress sample (4.5yr, since several of its 10-coin
universe listed after 2016-05) -- multi-coin rotation performed worse than the BTC-only
version in every window, opposite of the paper's own claim that the Top-20 rotation
reduces drawdown (we did not test drawdown-based promotion, only Sharpe).

## Registry disposition

`dir:crypto_trend_btc` and `dir:crypto_xs_momentum` remain **evidence_too_weak**. The
2026-09-28 relaxed keep bar and 2026-09-29 full-Alpaca-scope ruling motivated reopening
them (see `direction-review.json`), but the actual local test under the frozen contract
still falls short -- this is a genuine negative result on the *current* test, not an
artifact of the old bar. `reopen_if` is updated to require either (a) a mechanism that
clears anchor Sharpe >=1.19 under this project's specific 10bp/next-open-fill contract
(not just the source paper's own reported full-sample number), or (b) the keep bar
changing again.

## Not done

The preregistered 30bp crypto-fee check was not run (no candidate reached the 10bp gate
that would trigger it) -- reported as designed, not a gap.
