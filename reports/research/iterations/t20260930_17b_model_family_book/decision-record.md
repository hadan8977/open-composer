# Decision Record: t20260930_17b_model_family_book

## Path

model_family_sweep_stage2_book: the three stage-1 cells XGB/LGBM/CAT_WX_H63 as long-only monthly books, V1 (top 50 of the whole pool) and V2 (top 50 inside the least liquid tercile), 21 offsets, fixed 10/20 bp per side, K1/K2, 20-seed random-rank placebo, DSR with 30 trials. Run on Modal by the 2026-09-30 22:07 exec round.

## Decision

Stop. Verdict `refuted` (lead review, 2026-10-01 01:07 UTC round). Pure price-volume ranking gets no more cells, as preregistered in `hypotheses.md`.

The run returned `parity_failed`, and `hypotheses.md` leaves that case to the lead. The lead rules that the parity miss cannot change the verdict:

- The book engine reproduces T-28-30 exactly: B0 stress 0.4621 vs 0.462, anchor 0.3266 vs 0.327.
- The RankIC misses are LGBM_WX_H63 0.0037 and CAT_WX_H63 0.0051 against a 0.002 tolerance. In all four cells stage 2 is higher than stage 1, so the stage-2 models are, if anything, slightly better than the ones that were selected.
- The books miss K1 on the anchor window by at least 0.77 Sharpe and miss K2 on the anchor window by at least 0.44. A RankIC difference of 0.005 cannot close either gap.
- Likely cause (inferred, not verified): stage 2 has two more boundary formation dates (2023-07-31 and 2023-08-31: 74 against 72), and the real run used a different core count after the 20-minute smoke timeout. LightGBM and CatBoost sum histograms in an order that depends on the thread count; XGBoost hist does not, and XGB is the cell that passed. On the 72 shared dates the mean gap is 0.0008-0.0021.
- No rerun. A rerun would cost Modal credit and could only move a verdict that is not close.

## Reason

All numbers are from `results.json`. Each was checked by the lead against the preregistered rules.

- K1: no book passes. Anchor flat10 offset-median Sharpe is XGB V1 0.163 / V2 -0.172, LGBM V1 0.333 / V2 0.267, CAT V1 0.239 / V2 0.422; the bar is 1.19. On the stress window only XGB V2 (0.662) clears 0.65, which is expected because the cells were selected on stress t.
- K2: every book is positive on the stress window (+0.003 to +0.192) and strongly negative on the anchor window (-0.389 to -0.664). Adding any of them to S3 lowers the 2024-26 Sharpe.
- Placebo: every book beats all 20 random-rank books on the stress window. On the anchor window the beat rates are LGBM V2 1.00, CAT V2 1.00, LGBM V1 0.80, CAT V1 0.30, XGB V1 0.05, XGB V2 0.00. Inside the pool the ranking skill is real, but the pool itself, illiquid small caps, earned little in 2024-26. A good rank within a weak pool is not enough.
- DSR (30 trials): 0.009-0.083.
- 2026 holdout (contaminated, reference only): -0.760 to 0.386.
- Known biases favour the books, so they do not rescue them. The cells were selected on the stress window, delisting returns are recorded as 0, and the fixed 10 bp per side is low for the least liquid tercile.

## Cause of death

The ranking is fine. The money is not there. The model separates good from bad illiquid small caps better than chance (stress RankIC about 0.05, anchor placebo beat 0.8-1.0 for three books). But in 2024-26 the whole illiquid pool trails the leveraged semiconductor momentum that S3 holds, so the long-only book reaches Sharpe 0.42 at best. Changing the model family cannot fix that, because it is a property of the universe in the recent regime, not of the learner. A better execution method cannot fix it either, since the loss is not a cost problem: flat20 is only 0.03 Sharpe below flat10.

## Rejected variants

None added. No tuning and no extra cells. The rank-mean ensemble is not run as a book because the preregistered selection was by t.

## Next iteration suggestion

None on this line. Main line D stays parked: pure price-volume ranking gets no new cells, whatever the model family, window or horizon. Reopening needs new data (paid option quotes or DeepSeek-scored text), with the difference from T-28-30, T-17 and T-19 written down. The owner's 2026-09-29 question ("XGBoost 等其他模型不行吗") is answered: other families change RankIC by at most +0.007 for a single family and +0.012 for an ensemble, and none of the resulting books comes close to K1 or K2.
