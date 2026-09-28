# Decision Record: h20260928_04_s3_alt_div_batch1

## P1

- Path: `s3_alt_div_batch1_screen` (19 candidates: F1 managed-futures ETFs
  held outright -- DBMF, KMLM, CTA, WTMF, FMF; F2 Keller/Antonacci/Faber
  tactical-allocation rules -- VAA-G4, DAA-G12, PAA-CPR, HAA, GPM, GEM,
  GTAA-5, ADM, BAA-Balanced; F3 other alt-diversifier ETFs held outright --
  RPAR, UPAR, NTSX, QAI, TRTY).
- Decision: **stop** (all 19 refuted; 0 kept, 0 watch_recent).
- Reason: Per `results.json`'s `adoption` block, checked against
  candidate-manifest.json's adoption_rule (K1 anchor >=1.1882 / stress
  >=0.6447 with positive 20bp CAGR both windows; K2 combination edge >=0.05
  both windows): no candidate reaches the K1 anchor-Sharpe bar (closest:
  F2_GEM 0.9570, F3_TRTY 0.9203, F2_GTAA 0.9019, all below 1.1882). No
  candidate clears K2 in both windows -- every positive anchor-window
  combination edge (F1_DBMF +0.091, F1_CTA +0.204, F1_FMF +0.081, F2_GTAA
  +0.145, F3_TRTY +0.136) turns negative in the stress window
  (2016-05..2023-09). F1_CTA (1.46yr) and F3_UPAR (1.62yr) have under 2 years
  of stress-window data (marked "待补压力期" per the runbook rule) but both
  already fail on anchor Sharpe alone, so this does not change their
  verdict. No candidate reaches even the anchor-only `watch_recent` bar.
- Next iteration suggestion: do not re-tune these 19 candidates' published or
  round-number parameters inside this manifest (per each family's
  stop_condition in direction-review.json). If this direction area is
  revisited, it needs either a longer/more-diversified live trend record (F1
  family), a published rule with documented negative correlation
  specifically in the 2022 regime (F2 family), or a mechanism that does not
  carry embedded equity beta into drawdowns (F3 family) -- not a parameter
  sweep of the same 19 rules.
