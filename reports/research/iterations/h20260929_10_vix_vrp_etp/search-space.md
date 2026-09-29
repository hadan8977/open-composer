# Search Space: h20260929_10_vix_vrp_etp

One path, `vix_vrp_etp_screen`, 12 candidates total (<=24, well inside the
single-path cap; total round budget 12, inside the <=80 cap):

- 6 = 3 RV-window variants (5d, 10d, 20d) x 2 remainder legs (SPY, SHY) of
  the full 2-signal combo (`VVRP_COMBO_RV{5,10,20}_{SPY,SHY}`).
- 2 = signal-1-only (eVRP sign, RV window 10) x 2 remainder legs
  (`VVRP_SIG1ONLY_{SPY,SHY}`).
- 2 = signal-2-only (VIX vs VIX3M term structure) x 2 remainder legs
  (`VVRP_SIG2ONLY_{SPY,SHY}`).
- 1 = `VVRP_RAND_PLACEBO`, a deterministic pseudo-random short-vol day
  frequency-matched to `VVRP_COMBO_RV10_SHY`'s own real trigger rate --
  internal falsification control, never keep-eligible.
- 1 = `STATIC5050_SMH_QQQ`, a fixed monthly 50/50 SMH/QQQ blend with no VIX
  signal at all -- owner-requested external benchmark, never keep-eligible.

Cost assumptions: `cost-contract.json` (10bp primary / 20bp stress per
side, close-signal -> next-session-open fill, no financing/borrow cost
beyond SVXY's own built-in structural leverage). Benchmark family:
SPY buy-and-hold, SHY buy-and-hold, the static 50/50 SMH/QQQ control, and
S3 (this project's reference sleeve) for the K1/K2 gate.

Go/no-go band: this project's own frozen K1/K2/strong_keep/watch_recent
keep rule (`candidate-manifest.json`'s `keep_rule`, identical structure to
every prior screen_lane batch since h20260928_01), not a separate Wave-9.2
band -- this iteration is a single-mechanism batch screen, not a breadth
campaign, so `single_mechanism_no_campaign_attestation: true` in
`search-space.json`.
