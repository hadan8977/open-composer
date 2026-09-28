# Decision Record: h20260928_20_recent_regime_opt

Backtest executed 2026-09-28 via `scripts/screen_batch.py --batch
h20260928_20_recent_opt --iteration h20260928_20_recent_regime_opt`. The
owner's literal three-part per-family replacement rule was applied
mechanically to `reports/research/screens/h20260928_20_recent_opt/leaderboard.json`;
see `results.json` and `report.md` for full numbers.

## P1 (E family)

- Path: recent_regime_opt_screen, E family (E0 base + E1-E7)
- Decision: **stop** (no replacement)
- Reason: No E-family variant clears all three replacement conditions. E5
  clears (a) (select10 Sharpe 2.0003 vs. E0's 1.4390 bar) and (c) but fails
  the 2026-contamination guard (b) by 0.115 (drop of 0.215 vs. the 0.10
  allowed). E1/E2 (the source's own tested formation-window robustness
  check) both underperform E0 substantially, consistent with Graziani
  (2024)'s own finding. E0 stands unchanged as the batch-2 result.
- Next iteration suggestion: do not retry this family with new parameters
  inside this manifest; a genuinely new mechanism or newly disclosed
  data/source would be required to reopen dir:end_of_month_reversal_effect
  for further optimization.

## P2 (S family)

- Path: recent_regime_opt_screen, S family (S0 base + 9 variants)
- Decision: **stop** (no replacement)
- Reason: No S-family variant clears all three replacement conditions.
  S_SHIFT0 clears (a) and (c) but fails guard (b) hard (2026 Sharpe 1.6446
  vs. a required floor of 2.9080) -- consistent with Quantpedia's own
  finding that shift-0 ("true seasonality") is "at best, comparable to"
  benchmark. S0 stands unchanged as the batch-2 result.
- Next iteration suggestion: do not retry this family with new parameters
  inside this manifest; Allocate Smartly's two independent negative-evidence
  tests of the closely related front-running mechanism (country ETFs,
  commodities) are consistent with this outcome and argue against further
  variant search on this specific mechanism without new evidence.

## P3 (C family, descriptive)

- Path: recent_regime_opt_screen, C family (C1, C2)
- Decision: **stop** (descriptive only, no promotion)
- Reason: Neither C1 nor C2 beats both component bases (E0, S0)
  simultaneously; both beat S0 alone but remain below E0 alone. Not
  eligible to replace either base per the preregistered rule.
- Next iteration suggestion: no further action; not carried into a new
  iteration on this evidence alone.
