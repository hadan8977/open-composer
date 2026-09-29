# Decision Record: h20260929_33_crypto_trend

## P1 crypto_trend_screen

- Path: crypto_trend_screen (13 preregistered candidates, scripts/screen_batch.py
  --batch h20260929_33_crypto_trend --iteration h20260929_33_crypto_trend)
- Decision: **stop** (not kept). No candidate clears K1 (best anchor Sharpe 0.906,
  BTC_DONCHIAN_ENSEMBLE_VT40, vs the >=1.19 bar) or K2 (same candidate's best K2 anchor
  edge +0.164 clears 0.05, but its stress edge -0.064 does not -- K2 needs both
  windows). No candidate reaches watch_recent either (needs anchor Sharpe>=1.19). The
  preregistered 30bp crypto-fee check was never triggered since nothing cleared 10bp.
  Every candidate beats the BTC_RAND_PLACEBO control comfortably, so this is a genuine
  negative result on the mechanisms themselves under this project's frozen contract, not
  an artifact of noise or an unfair placebo comparison. Full numbers:
  reports/research/iterations/h20260929_33_crypto_trend/results.json and
  reports/research/screens/h20260929_33_crypto_trend/leaderboard.json.
- Reason: Zarattini/Pagani/Barbon 2025's own reported BTC Sharpe 1.56 is a 2015-2025
  full-sample number under the paper's own cost convention; this project's specific
  2024-01-08..2026-09-17 anchor window under a strict 10bp close-signal/next-open-fill
  contract is a harder, more recent test, and the mechanism's own select-window Sharpe
  (1.342, closer to the paper's headline number) versus its anchor-window Sharpe (0.886)
  suggests 2024-2026 is genuinely a weaker regime for BTC trend-following locally, not an
  implementation defect. Cross-sectional momentum (Liu-Tsyvinski-Wu-style, long-only
  reinterpretation) is the weakest group on the anchor window (Sharpe 0.024-0.115)
  despite the strongest stress-window group -- consistent with the original registry
  entry's "stale sample" concern.
- Next iteration suggestion: dir:crypto_trend_btc and dir:crypto_xs_momentum stay
  evidence_too_weak. Reopen only with (a) a mechanism independently shown to clear
  anchor Sharpe >=1.19 under this project's own 10bp/next-open-fill contract (not the
  source paper's own more favorable full-sample number), or (b) a further keep-bar
  change. Do not re-run this exact candidate family without new information.
