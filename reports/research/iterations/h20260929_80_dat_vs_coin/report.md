# h20260929_80_dat_vs_coin report

Question: after 2024-01-11, does a beta-hedged spread of a bitcoin/ether treasury stock (P1 MSTR/BTC, P3 BMNR+SBET/ETH) or a miner basket (P2, eight names) versus the coin carry a tradeable mean-reversion (Z120/Z250, expected IC negative) or continuation (M20/M60, expected IC positive) signal after 10 bp per side per leg and borrow?

Verdict: stage-1 IC gate continued mechanically through one cell (P3_Z120); stage 2 found no keeper (23 reject, 1 reject_placebo). Overall: evidence_too_weak; P1 and P2 refuted in the anchor window. Sources: `results.json` (IC table, gate_checks), `screen-results.json` (24 candidates), `results-run1-padding-bug.json` (superseded first IC run, see below).

## Stage 1 (results.json ic_table, anchor 2024-01-08..2026-09-17 and stress 2020-08-11..2023-12-29, horizon 20 sessions, Newey-West lag 20, 500 placebos)

| pair | signal | anchor IC | anchor NW t | placebo pct | anchor episodes | sign as preregistered | stress IC / NW t |
|---|---|---|---|---|---|---|---|
| P1 MSTR/BTC | Z250 (largest anchor \|t\|) | +0.151 | 1.08 | 33.0 | 27 | no (expected negative) | -0.395 / -3.60 |
| P1 MSTR/BTC | Z120 | +0.073 | 0.53 | 32.0 | 25 | no | -0.292 / -2.78 |
| P2 miners/BTC | M20 (largest anchor \|t\|) | +0.138 | 1.19 | 75.6 | 33 | yes | -0.034 / -0.33 |
| P3 ETH treasuries/ETH | Z120 | -0.572 | -4.29 | 100.0 | 8 | yes | no data |
| P3 ETH treasuries/ETH | M20 | -0.432 | -2.65 | 0.0 | 10 | no (expected positive) | no data |

Continue conditions (anchor sign as preregistered, |NW t| >= 2.0, stress same sign where >= 60 valid sessions, >= 6 anchor episodes): only P3_Z120 passes all four (stress not applicable). P1 and P2 fail c1/c2 in every cell (best anchor |t| 1.19). P1's stress-window Z ICs have the preregistered negative sign with |t| 2.8-3.6, so the practitioner premium-compression story shows up in 2020-2023 with the spot-BTC leg and not in 2024+ with FBTC: the premium persisted in the anchor window (Elm Wealth's caveat).

P3 rests on 197 valid sessions (2025-11-14..2026-08-28), about ten non-overlapping 20-session windows, and one regime (ETH treasury premium collapse); Z250 for P3 has only 67 valid sessions and 2 episodes.

Data notes: results-run1-padding-bug.json is a superseded first run in which the z-score history was padded with a flat pre-listing zero for P3 (P3_Z250 also "passed" there); fixed before any stage-2 return was computed (log_price_ratio NaN before listing, tests/test_run_h20260929_80_dat_ic.py). Discards: SBET pre-2025-05-27 (1,597 rows) and two sessions with |log return| > 0.5 (2025-05-29 +100%, 2025-06-13 -126% log), CIFR pre-2021-08-30 (183 SPAC rows), WULF pre-2021-12-14 (627 rows), CORZ pre-2024-01-24 by the price-hygiene mask, IBIT/XXI/NAKA not used.

## Stage 2 (screen-results.json, 24 candidates, judged = median of 5 weekly offsets, 10 bp per leg per side, 3%/yr borrow)

- No candidate clears K1 or K2. Best anchor Sharpes: P3_Z120_SYM 1.39 (181 active days, 5% of days in position, stress unavailable, K2 edge -0.49, DSR 0.21, 17.5% of 40 random-entry placebos at or above it -> reject_placebo; 15%/yr borrow still leaves Sharpe 1.09), P2_Z120_SHORT 0.76 (stress 0.14, K2 edge -0.53), P1_Z250_SYM 0.70 (stress -1.21).
- P1 Z books have negative anchor Sharpe (-0.42..-0.84) despite stress-window Sharpes up to +1.04 (P1_Z250_SYM); every K2 edge vs S3 is negative in the anchor window except P1_Z250_SYM (+0.06 anchor, -1.02 stress).
- The short-DAT-only side (the published trade): anchor Sharpe P1_Z120_SHORT -0.41, P1_Z250_SHORT -0.75, P2_Z120_SHORT +0.76 (stress 0.14, K2 edge -0.53), P2_Z250_SHORT -0.72; every P1 and P2 M-family short-only book is negative (-0.09 to -0.69).

Not tested: dollar-holdings mNAV series (no local data), borrow availability on Alpaca for DAT names, weekend/overnight crypto effects (T-50), pre/post-market fills.
