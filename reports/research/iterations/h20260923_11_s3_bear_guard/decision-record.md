# Decision record: h20260923_11_s3_bear_guard

## Path
s3_bear_regime_guard_screen, five preregistered candidates (BG00 reference plus BG01-BG04 bear
gates) run through the frozen S3 vt40+boost overlay machine, plus four exposure-matched EM-k
controls and eighty circular-shift CS-k placebos (not candidates).

## Decision
Stop (round 1 executed 2026-09-23, `report.md`, `summary.json`, `trial-ledger.jsonl`). No gate
passes the preregistered adoption rule; verdict "no guard; keep the 25% exit".

| gate | design CAGR / Sharpe / maxDD | vs BG00 30.7% / 0.83 / -48.0% | EM-k Sharpe (c) | shifts beaten | anchor G1 10/20 bp |
|---|---|---|---|---|---|
| BG01 QQQ < SMA200 | 25.6% / 0.74 / -61.1% | worse on all three | 0.81 (0.92) | 10/20 | pass/pass |
| BG02 SMH < SMA200 | 30.9% / 0.85 / -41.1% | DD +6.9 pt, Sharpe +0.02 | 0.81 (0.92) | 17/20 | pass/pass |
| BG03 HYG/IEF < SMA100 | 6.9% / 0.34 / -58.9% | worse on all three | 0.78 (0.69) | 1/20 | pass/pass |
| BG04 book equity < SMA200 | 26.6% / 0.80 / -42.6% | DD +5.4 pt, Sharpe -0.03 | 0.78 (0.71) | 14/20 | pass/pass |

The closest gate, BG02, fails (a) (needs +10 pt) and (b) (needs +0.10) and misses (d) by one
placebo; its 2018 (-9.6% vs -22.0%) help is offset by 2022 (-36.6% vs -33.6%), when semis
broke their 200-day average after the damage. The price-trend gates act after the fall and
re-enter after the rebound (BG01 2019: 3.2% vs 35.1%), so they do not beat an exposure-matched
lower volatility target. Circular-shift placebo Sharpe ranges: BG01 0.54-0.97, BG02
0.48-0.91, BG03 0.30-0.98, BG04 0.33-0.98 (medians 0.74 / 0.77 / 0.63 / 0.62).

## Reason
The overlay machine already cleared its own gates on the live S3 book and is not re-tested here;
the only open question is whether a bear-regime gate, grounded in a published and independently
live-replicated moving-average de-risking rule (Gayed and Bilello 2016; Faber 2007; Gehrman's
live r/LETFs track record), can beat an exposure-matched control and a circular-shift placebo on
the pre-select-window 2016-2023 design window without breaking the frozen anchor-window return
bar. This directly answers the reopen condition the earlier, refuted drawdown-brake experiment
(H-20260922-02, dir:drawdown_brake_overlay) left explicit: "a drawdown signal validated with an
exposure-matched control." The cheapest decisive test reuses the existing panel, the existing
frozen overlay implementation, and BG00's already-computed numbers, so the marginal compute is
88 simulations within a 30-minute budget.

## Next iteration suggestion
Round 2 does not exist yet; it is gated on round 1's actual results. If no gate passes all of
(a)-(e), the verdict is "no guard; keep the 25% exit" and this family is not reopened except with
a new gate mechanism (for example a model that forecasts regime transitions) or new, disclosed
data (for example a fully-specified macro/credit series), not by re-tuning these four gates'
windows or thresholds. If one or more gates pass, the next step is a paper-readiness review
(execution reality, PIT feature packet if any new data source is added, and an owner decision on
whether to fold the gate into the next S3 re-authorization), not an automatic promotion.
