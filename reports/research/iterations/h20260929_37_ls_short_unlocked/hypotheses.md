# Hypotheses: h20260929_37_ls_short_unlocked

## Hypothesis

At least one of the 16 low-turnover candidates has an offset/delay-median Sharpe >= 1.1882 in 2024-01-08..2026-09-17 and >= 0.6447 in the stress window at 10 bp per side after ADV-tier borrow, or a K2 edge >= 0.05 over S3 in both windows; otherwise the three short-unlocked directions are refuted at low turnover.

## Failure mode

Costs (half spread plus flat bp on every flip and pair rebalance) and borrow tiers remove the gross edge; calendar and pair effects are arbitraged; mirror or random-ranking placebo is as good as the rule.

## Measurement

Median over 21 monthly / 5 weekly offsets (A, C-ablation), entry delays 0/1/2 (B), single calendar version (C composite) of the after-borrow 10 bp Sharpe in anchor 2024-01-08..2026-09-17 and stress 2016-05-02..2023-09-15; 20 bp CAGR; K2 blend edge with S3; DSR with 22 trials; mirror and 20-seed random placebo.

## Stop/Pivot criterion

K1 = anchor>=1.1882 and stress>=0.6447 and median 20 bp CAGR>0 in both windows; K2 = S3 inverse-vol edge >=0.05 in both windows; strong = K2 edge >=0.10 both or K1 with anchor>=1.4853 and stress>=0.8059; watch_recent = anchor>=1.1882 without K1. Frozen now; keep tiers also need the candidate anchor Sharpe above the max of its 20 random placebos.

## Result (recorded after the run)

H1 refuted: 0/16 candidates reach K1, K2 or watch_recent (best anchor after borrow: LL_SOXX_K3_H5 0.758 with stress -0.223; A best DC_M252_ALWAYS -0.015 / -0.065; C best SIM_ABL_LS_K3_MONTHLY 0.119 / -0.012). Gross edges exist in A and in SOXX-B but are consumed by 10 bp per side; the Quantpedia composite loses at 141.7 turnover units per year. See report.md and results.json.
