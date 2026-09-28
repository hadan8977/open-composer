# Search Space: h20260928_20_recent_regime_opt

One path, `recent_regime_opt_screen`, with 20 preregistered candidates: the
E family (base E0 plus 7 formation-window/threshold/symbol/holding/weighting
variants, 8 total), the S family (base S0 plus 9 top-N/lookback/shift/
universe/weighting/filter variants, 10 total), and the C family (2 static
cross-family combinations, C1 and C2). Every candidate is a calendar-anchored
"D"-frequency rule (single version, no monthly/weekly offset sweep) evaluated
via `scripts/screen_batch.py --batch h20260928_20_recent_opt --iteration
h20260928_20_recent_regime_opt`, reusing screen_lane's frozen select/anchor/
holdout/stress windows and 10bp/20bp cost convention unchanged from batch-2.

Cost assumptions: `cost-contract.json` -- sum(|delta weight|) * slippage_bps
at 10bp primary / 20bp stress, next-bar-open fill. Benchmark family: each
variant is judged against its own family's base (E0 or S0), not against a
buy-and-hold or S3 proxy directly (those are reported for context only). This
round does not use the Wave 9.2 go/no-go bands; it uses the owner's own
2026-09-28 literal three-part per-family replacement rule (see
candidate-manifest.json's `adoption_rule`), which is stricter in the sense of
requiring a contaminated-2026-window guard and a 20bp cost survival check on
top of the raw select-window Sharpe improvement.

Total candidate budget: 20, within the 24-per-path / 80-total Wave 9.2 cap.
