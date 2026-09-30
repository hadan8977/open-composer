# Decision Record: t20260930_17_model_family_sweep

## Path

model_family_sweep_stage1: 24 cells ({LGBM, XGB, CAT, RIDGE, MLP, ENS} x {W3, WX} x {H21, H63}), walk-forward RankIC on the stress window 2016-05-02..2023-08-31 only, cached T-20260928-10 monthly panel.

## Decision

Continue to stage 2 in a separate dossier, `t20260930_17b_model_family_book` (lead review, 19:07 UTC round, 2026-09-30). The lightweight-dossier rule allows one path and at most 24 candidates, and stage 1 used all 24.

## Reason

`results_stage1.json`, checked by the lead against the preregistered rules:

- `b0_parity` true: LGBM_W3_H21 RankIC 0.020001; h21 target check max diff 0.0; h63 NW lag 2.
- Family effect per (window, horizon), best non-LGBM minus LGBM: W3_H21 +0.0065 (ENS), W3_H63 +0.0089 (ENS), WX_H21 +0.0082 (ENS), WX_H63 +0.0121 (ENS, t 4.47).
- `answer_family` is `material` only through the rank-mean ensemble. The best single family is CAT_WX_H63 at +0.0072.
- Horizon matters more than family: H63 is about twice H21.
- Ranking skill sits in the illiquid terciles. The selected cells score T3 0.070-0.093, while T1 (most liquid) is at most 0.012 with t < 1.
- `stage2_cells`, by stress NW t: XGB_WX_H63 (5.65), LGBM_WX_H63 (5.40), CAT_WX_H63 (5.21).

## Rejected variants

None added. No hyperparameter tuning, no extra cells. The ensemble (highest RankIC, t 4.47) is not a stage-2 cell because the preregistered selection is by t.

## Next iteration suggestion

Stage 2: V1/V2 books at fixed 10/20 bp, K1/K2, placebo, DSR 30. Preregistered in `t20260930_17b_model_family_book/hypotheses.md` (pre-backtest ok 19:22 UTC); brief `reports/research/control/briefs/T-20260930-19.md`. Prior for any K1 pass is under 5%. ML-round entry conditions for other signals are not met by this step.
