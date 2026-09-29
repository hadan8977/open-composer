# Search Space: h20260929_33_crypto_trend

Single path `crypto_trend_screen`, 13 candidates, evaluated by
`scripts/screen_batch.py --batch h20260929_33_crypto_trend --iteration
h20260929_33_crypto_trend` (screen_lane's batch-screening harness, frozen
10bp/20bp cost contract, close-signal -> next-open fill, all rebalance-day
offsets reported for M/W-frequency candidates and judged by median).

12 mechanism candidates (BTC buy-and-hold benchmark, BTC 200-session-equivalent
SMA filter, BTC 1/3/6-month time-series momentum, a BTC Donchian-ensemble
trend rule approximating Zarattini/Pagani/Barbon 2025 in a plain and a
40%-vol-targeted version, a 10-coin Donchian/momentum rotation, a BTC+ETH
dual-momentum rule, and a 63-session cross-sectional top-3 momentum rotation
in equal-weight, inverse-vol, and 40%-vol-targeted versions) plus 1 internal
deterministic random-timing placebo (BTC_RAND_PLACEBO, never keep-eligible).
Every parameter (lookback windows, top-N, vol-target level and window) is
fixed in candidate-manifest.json before any return is computed; the 13-entry
budget is well under the 24-candidate lightweight-path cap and the project's
80-candidate per-round cap.

Cost assumptions: the unedited screen_lane 10bp/20bp-per-side contract for
the leaderboard itself, plus a preregistered secondary 30bp-per-side
crypto-fee check (25bp Alpaca lowest-tier taker + ~5bp assumed spread,
cost-contract.json) applied only to candidates that clear K1/K2 at 10bp,
reported in report.md.

Benchmark family: BTC buy-and-hold, SHY buy-and-hold, and S3 (the project's
incumbent sleeve) for the K1/K2/strong_keep/watch_recent keep-rule
comparison defined in candidate-manifest.json's `keep_rule` field.
