# Report: h20260928_42_opex_week

Batch-screening pass for T-20260928-42: 20 candidates (8 primary
option-expiration-week calendar candidates on SPY/QQQ/DIA/IWM + 12 internal
placebo controls anchored to non-expiration Friday weeks). Run via
`scripts/screen_batch.py --batch h20260928_42_opex_week --iteration
h20260928_42_opex_week`; raw output at
`reports/research/screens/h20260928_42_opex_week/leaderboard.json`. Every
number below is read directly from that file and this iteration's own
`results.json`, checked candidate-by-candidate against
`candidate-manifest.json`'s preregistered K1/K2/watch_recent/strong_keep
thresholds and the placebo internal-falsification rule -- no candidate,
grid point, or threshold was changed after seeing a result.

## S3 reference (from `h20260928_01_s3_rebalance_tranching/results.json`)

Anchor median Sharpe (net10) 1.4853, K1 anchor bar (80%) 1.1882. Stress
median Sharpe (net10) 0.8059, K1 stress bar (80%) 0.6447.

## Result: 0/8 primary kept, 0 watch_recent, 8/8 primary refuted

All 8 primary candidates were refuted outright -- none came close to
clearing K1, K2, or even the anchor-only watch_recent bar. Full numbers
(anchor/stress judged Sharpe at 10bp, both from `leaderboard.json`):

| id | anchor Sharpe | stress Sharpe | K1 anchor bar (1.1882) | K1 stress bar (0.6447) | K2 edge anchor/stress | DSR anchor |
|---|---|---|---|---|---|---|
| OPEX_SPY_WEEK | -0.632 | -0.719 | fail | fail | -0.56 / -0.68 | 0.001 |
| OPEX_SPY_WEEKMON | -0.480 | -0.426 | fail | fail | -0.54 / -0.53 | 0.003 |
| OPEX_QQQ_WEEK | -0.643 | -0.308 | fail | fail | -0.74 / -0.46 | 0.001 |
| OPEX_QQQ_WEEKMON | -0.573 | 0.038 | fail | fail | -0.77 / -0.26 | 0.002 |
| OPEX_DIA_WEEK | -0.661 | -0.799 | fail | fail | -0.48 / -0.75 | 0.001 |
| OPEX_DIA_WEEKMON | -0.476 | -0.499 | fail | fail | -0.43 / -0.60 | 0.003 |
| OPEX_IWM_WEEK | -0.283 | -0.785 | fail | fail | -0.37 / -0.71 | 0.009 |
| OPEX_IWM_WEEKMON | -0.176 | -0.527 | fail | fail | -0.37 / -0.56 | 0.014 |

Every primary candidate's anchor-window Sharpe is negative (best:
OPEX_IWM_WEEKMON at -0.176), so none clears even the anchor-only
watch_recent bar (>=1.1882), let alone full K1. K2 fails just as badly:
every primary candidate's diversifier edge is negative in BOTH windows
(anchor -0.18 to -0.77, stress -0.26 to -0.75) -- adding this rule to S3
would make the combined portfolio worse, not better, in every case. 20bp
CAGR is also negative for all 8 in the stress window and for 6/8 in the
anchor window (only OPEX_SPY_WEEKMON has positive net10 anchor CAGR at
+0.5%, but its net20 anchor CAGR is -4.2%; no candidate has positive net20
CAGR in both windows). No candidate clears any tier; the placebo demotion
rule is therefore moot (nothing to demote) but is reported below for the
record, since it independently corroborates the refutation.

### Placebo comparison (internal falsification, not itself a keep tier)

The 12 placebo candidates (`PLACEBO_W{1,2,4}_{TICKER}`, anchored to the
1st/2nd/4th Friday's week instead of the 3rd/expiration week) show that the
expiration week is, if anything, WORSE than an arbitrary Friday-anchored
week under this cost/fill contract, not special in a positive direction:

| ticker | OPEX_*_WEEK anchor Sharpe | best same-ticker placebo | placebo id |
|---|---|---|---|
| SPY | -0.632 | +0.860 | PLACEBO_W2_SPY |
| QQQ | -0.643 | +1.152 | PLACEBO_W2_QQQ |
| DIA | -0.661 | +0.273 | PLACEBO_W2_DIA |
| IWM | -0.283 | +0.684 | PLACEBO_W2_IWM |

For all four tickers, the 2nd-Friday-week placebo has a materially HIGHER
anchor Sharpe than the actual expiration (3rd Friday) week. Had any primary
candidate cleared a keep tier, this would have triggered the preregistered
placebo-demotion rule; since none did, this is reported as independent,
additional evidence against the mechanism (an arbitrary non-expiration
week outperforms the expiration week on this universe/window/cost
contract), not as the deciding criterion. `PLACEBO_W2_QQQ` also has this
batch's highest DSR (0.4926), still well short of a normal significance
threshold and itself ineligible for any keep tier by design.

## DSR

Full 20-candidate family, n_trials=20 (conservative), per the queue task's
instruction. Maximum DSR overall: 0.4926 (`PLACEBO_W2_QQQ`, a placebo,
never keep-eligible). Maximum DSR among the 8 primary candidates: 0.0142
(`OPEX_IWM_WEEKMON`) -- vanishingly low, consistent with candidates whose
own Sharpe is negative.

## Interpretation

Two independent, mechanism-grounded academic sources (Stivers & Sun 2013;
Garcia-Ares & Muravyev 2025) support a real historical option-expiration-
week / rollover-Monday price-pressure effect, and the official Cboe rule
(cboe_2013_third_friday_official_expiration_rule) confirms this iteration's
calendar construction is faithful to the exchange's own expiration
definition, including the holiday-shift case. Despite that, under this
project's frozen 2024-2026 anchor and 2016-2023 stress windows and 10bp/
20bp next-open-fill cost contract, none of the four large-cap/index-ETF
proxies (SPY/QQQ/DIA/IWM) shows a usable edge in either the WEEK or the
WEEKMON (Monday-rollover-capturing) variant. This is consistent with (a)
the counter-evidence found on request (quantifiedstrategies.com's
fetch-blocked claim of recent decay), (b) this project's own precedent for
calendar-anchored D-frequency rules under the identical contract
(TOM_SPY anchor Sharpe -0.69, FOMC_DRIFT_SPY -0.84 in
h20260928_05_batch2), and (c) the 0DTE-driven change in options-market
microstructure documented by the Cboe 2023 gamma-squeeze research, which
provides a plausible mechanism for why an effect detectable through 2010
(Stivers & Sun) or even 2021 (Garcia-Ares & Muravyev, on OPTION returns,
not stock returns) may not translate into a tradable STOCK/ETF-level edge
in 2024-2026 once this project's specific fill-timing and cost assumptions
are applied.
