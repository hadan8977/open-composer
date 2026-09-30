# Decision Record: h20260929_80_dat_vs_coin

## P1 dat_vs_coin_spread (P1 MSTR/BTC, P2 miner basket/BTC, P3 BMNR+SBET/ETH x Z120/Z250/M20/M60 x symmetric / short-DAT-only, 24 candidates)

- Path: beta-hedged DAT/miner stock vs coin spread, mean reversion (Z) and continuation (M).
- Decision: stop, verdict evidence_too_weak (P1 and P2 refuted in the anchor window). No keeper, no kept.jsonl entry.
- Reason: stage 1 (`results.json` gate_checks): P1 anchor IC has the wrong sign for Z (+0.073 t 0.53 at Z120; +0.151 t 1.08 at Z250), P2 best anchor |t| 1.19 (M20 +0.138), so both fail c2 (|t| >= 2.0) in every cell. Only P3_Z120 passed all four frozen conditions (anchor IC -0.572, NW t -4.29, 8 episodes, stress N/A) on 197 valid sessions of a single ETH-treasury premium-collapse regime. Stage 2 (`screen-results.json`): 23 reject, 1 reject_placebo; P3_Z120_SYM anchor Sharpe 1.39 fails placebo (17.5% at or above, limit 10%), K2 edge -0.49, DSR 0.21, stress window unavailable; no candidate reaches K1 or K2.
- Rejected variants: none added after results; first IC run (padding bug) and first screen launch (reversed weight signs) were corrected before results were used, disclosed in report.md and stage2-protocol-preregistration.md.
- Next iteration suggestion: reopen P3 only after roughly 2027-06 (about two years of BMNR/SBET data, a stress period or a second premium cycle), or with a holdings/mNAV series and confirmed borrow on DAT names. P1/P2 price-only relative value: do not reopen without a new information source. ML and AI-information round entry conditions are not met.
