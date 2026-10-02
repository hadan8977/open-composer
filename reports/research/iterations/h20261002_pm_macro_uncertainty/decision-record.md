# Decision Record: h20261002_pm_macro_uncertainty

Verdict: H1 not supported and not refuted; H2 (CPI days only) not supported. The continue rule was frozen in `candidate-manifest.json` before any return grouped by U_rel or by the gap was computed. Numbers come from `results.json` (`continue_rule`, `H1`, `H2`, `placebos`, `candidates`) and `report.md`.

## P1

- Path: release_day_overlay (U1-U7 on H1, G1-G2 on H2)
- Decision: stop for adoption (continue rule failed); no candidate is scored or promoted. The direction is parked, not refuted, because the stop rule (D < +5 bp or wrong-signed) was not triggered.
- Reason:
  - H1: D = +13.93 bp (QQQ R_cc excess BIL, 79 non-FOMC release days, 2023-07-12..2026-09-17), below the +15 bp bar; permutation p 0.413 (bar 0.10); anchor D +26.12 bp (> 0). One of three continue conditions is met. D is above the +5 bp stop line, so H1 is neither continued nor refuted.
  - Power is the problem: the within-series shuffle 90th percentile of D is 51.2 bp, so a 15 bp effect cannot be told from noise on 79 days. Dropping 2025 turns D to -48.1 bp, so the positive D depends on one year.
  - Placebos: real D is not above the shuffle p90; T+1 D is -20.2 bp; random-session placebo mean 0.04 bp, sd 31.2 bp. R_co D is +6.4 bp, FOMC days alone -9.0 bp.
  - H0: no announcement premium on QQQ in this sample (pooled non-FOMC 4.4 bp, t -0.23 against other sessions); TLT -20.5 bp (t -1.67).
  - H2: CPI days only (no free payrolls consensus). Hit rate 0.55 on 20 events with |gap| >= median (p 0.41), anchor 0.625 on 16; bars 0.60 and 0.10 not met. 77 percent of gaps are negative, consistent with the 0.05 bin-midpoint offset in the frozen construction.
  - Candidates: all `decision_eligible: false`. Best net mean per event: G2 +18.0 bp (t 1.20), U5 +36.1 bp (t 0.48); none is significant and G2's gap sign is mostly the constant offset.
- Caveats: sample 2023-07 onward because Kalshi threshold markets start in late 2022 and six prior events are needed; no 2022 stress window; U is truncated to the listed strikes; the construction cannot be tuned after seeing results.
- Next iteration suggestion: do not re-run on the same days. Use the forward collector (hourly Kalshi snapshots from 2026-10-02) to build a forward U_rel record; reopen only after about 60 further non-FOMC releases (about 2 years) or if a pre-registered variant removes the 0.05 offset in the H2 gap. Any variant needs a new contract and unseen data. The lead-lag row `dir:prediction_market_crypto_as_equity_signal` stays evidence_too_weak.
- ML or AI-information round entry conditions: not met, no model involved.
