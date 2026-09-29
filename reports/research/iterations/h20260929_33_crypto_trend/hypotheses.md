# Hypotheses: h20260929_33_crypto_trend

## H1

- Hypothesis: At least one published crypto trend/momentum rule, expressed long-only
  on Alpaca-tradable spot crypto (BTC and the 9-coin altcoin universe in
  candidate-manifest.json), clears the 2026-09-28 relaxed keep bar (K1: judged
  Sharpe >=80% of S3's own anchor/stress Sharpe, i.e. >=1.19 anchor / >=0.65
  stress, net-20bp CAGR positive both windows; or K2: >=0.05 Sharpe edge as an
  S3 diversifier) both at 10bp and at the preregistered 30bp crypto-fee check,
  and beats the BTC_RAND_PLACEBO control. Source: Zarattini/Pagani/Barbon 2025
  (SSRN 5209907, reports/harness/source_cards/h20260929_33_crypto_trend.jsonl)
  reports BTC-only Sharpe 1.56 (per the prior intel cross-check) -- above the
  new anchor bar at face value, on a mechanism (Donchian-ensemble trend +
  vol-target sizing) independently corroborated in direction by Quantpedia's
  own from-scratch BTC trend review through Aug 2024.
- Failure mode: the paper's own reported Sharpe does not survive this
  project's specific frozen cost/fill contract (10bp next-open, not the
  paper's own cost assumption), the shorter/more volatile 2024-2026 anchor
  window, or the 30bp crypto-fee check; or the mechanism is beaten by its own
  random-timing placebo (spurious trend-following alpha from unconditional
  crypto beta exposure during a rising market, not real signal).
- Measurement: scripts/screen_batch.py --batch h20260929_33_crypto_trend
  --iteration h20260929_33_crypto_trend, judged (median-offset for M/W freq,
  single value for D freq) Sharpe/CAGR/max-DD per window, diversifier edge vs
  S3, DSR, correlation with S3, all read from
  reports/research/screens/h20260929_33_crypto_trend/leaderboard.json.
- Stop/Pivot criterion: per direction-review.json's stop_condition -- keep any
  candidate clearing K1 or K2 at both 10bp and 30bp and beating the placebo;
  write watch_recent for anchor-only clearers; otherwise record which specific
  gate failed (bar, fee check, or placebo) and do not reopen dir:crypto_trend_btc
  or dir:crypto_xs_momentum again without either new data or a further keep-bar
  change.
