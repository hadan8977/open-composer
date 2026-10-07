# Amendment A2 — rehedge formula and platform (written 2026-10-07T20:07:13Z, before any full-length result)

Written by the 2026-10-07 19:37 UTC lead round (Opus) on the executor's question (a) in the queue note of T-20261005-37. State at writing: only the 300-session identity gate (identity.json) and a 100-session timing run exist; no candidate, sensitivity or placebo series has been completed or read (the 10-07 G_REF run was killed at 2000/2240 sessions and wrote no parquet). Nothing in sections 5-9 of hypotheses.md (candidates, thresholds, classification, K* rule) changes.

## A2.1 Rehedge: use the direct form

Contract section 3 wrote the SPY hedge as "original aggregate hedge x (beta exposure of the modified stock book / beta exposure of the original aggregate book), no scaling when the denominator is 0". The brief and the code use the direct form: SPY hedge value = −Σ_i q_i · P_ref,i · β_i over the stock positions after concentration and rounding, β = the per-name beta the tranche target used on the refresh day.

The direct form is adopted for every method other than "orig":

1. Same intent: both set the hedge so that the stock book that is actually held is beta-neutral. When the original engine's hedge equals minus the original book's beta exposure, the two are algebraically identical.
2. The ratio form is unstable exactly where F1 lives: F1 is beta-neutral by design, so the original stock book's beta exposure can be near 0 on some days, and the "no scaling at 0" rule is a discontinuity.
3. Production checks the direct quantity: the live v1.2 plan gate `beta_neutral` is Σ β·w over the stock overlay plus the hedge weight (10-07 plan: 0.0108 against the 0.05 limit).

Consequence for the identities: I2 stays defined with rehedge=False (bit-for-bit, unchanged). Added diagnostic I2b (reported, not a gate): R1 with K = None, capital 1e6, whole shares, rehedge=True against I1; report the max abs daily return difference and the mean abs difference of the hedge weight. It measures how far the direct form is from the tranche-level hedge when nothing is dropped.

## A2.2 Platform

The owner's 2026-10-07 memory rule caps any local job at 1.2 GB (`config/memory-budget.json`); G_REF alone peaked at 1,326 MB. The run and evaluate stages move to Modal (brief addendum B), one container per config group, so each group's parquets come back as soon as it finishes. Same code, same configs, same outputs; the identity tolerance stays 1e-12 for I1/I2 within one container, and the I3 check (A1 files vs account-summary.json) is unchanged.
