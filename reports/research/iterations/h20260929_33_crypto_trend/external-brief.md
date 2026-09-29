# External Brief: h20260929_33_crypto_trend

T-20260929-33. Question: can published crypto trend/momentum rules (Alpaca spot,
long-only) reach the 2026-09-28 relaxed keep bar K1 (standalone, ~=S3) or K2 (S3
diversifier), reopening the registry's dir:crypto_trend_btc and dir:crypto_xs_momentum
rows under the owner's relaxed keep bar and 2026-09-29 full-Alpaca-scope ruling.

Eight sources opened (three paper-level): Zarattini/Pagani/Barbon 2025 "Catching Crypto
Trends" (SSRN 5209907, Concretum Group mirror read directly, raw HTML snapshotted and
hash-bound in direction-review.json; Sharpe above 1.5, alpha 10.8% vs BTC, net of fees,
via a Donchian-channel ensemble + vol-based sizing) is the primary mechanism source; the
more precise BTC-only (CAGR 30%/Sharpe 1.56/DD -19%) and Top-20-rotation (CAGR 18%/DD
-11%) figures are carried forward from the prior 2026-09-23 intel cross-check of three
author-affiliated mirrors, not re-quoted here. Liu-Tsyvinski-Wu 2022 (NBER w25882,
already fully read in the 2026-09-23 intel round) supplies academic backing for crypto
momentum generally but is long-short and stale (sample to 2018) -- not a literal
candidate here, only a long-only reinterpretation (CRYPTO_XS_TOP3_EW/IVOL). Quantpedia's
own from-scratch BTC trend/mean-reversion revisit (Oct 2015-Aug 2024) independently
corroborates that BTC trend-following specifically "remains alive and well"
out-of-sample through Aug 2024, while mean-reversion decayed. Bitwise BTOP's own live
record (10/20-day BTC EMA trend rotation, CME futures) is adjacent cautionary evidence:
launched 2023-09-29, liquidated 2026-05-29 despite a reported positive since-inception
return -- a similar mechanism on a different venue did not survive as a product, noted
but not treated as a direct falsification of this iteration's rules. Alpaca's own crypto
fee schedule (0.15%/0.25% lowest tier, tiered down to 0.00%/0.10%) and supported-coin
list (AAVE, AVAX, BAT, BCH, BTC, CRV, DOGE, DOT, ETH, GRT, LINK, LTC, MKR, SHIB, SUSHI,
UNI, XTZ, YFI -- SOL and XRP NOT listed) were opened directly and drive this iteration's
universe (BTC, ETH, LTC, BCH, LINK, DOGE, AVAX, UNI, AAVE, DOT: the subset with usable
Binance USDT history) and its preregistered 30bp crypto-fee stress check. Binance's
public monthly-klines archive (data.binance.vision) is the primary keyless price source;
Coinbase Exchange's public candles backfill BTC/ETH to the 2016-05 stress-window start.

Candidate matrix revisions from the brief's own scope constraints: (1) crypto is sampled
only at the US equity session (09:30/16:00 ET), not continuously, and every candidate is
long-only (Liu-Tsyvinski-Wu's own long-short design is not replicated); (2) the
Donchian-ensemble candidates use a self-constructed, clearly-labeled approximate
lookback-window ladder, since SSRN 5209907's exact published windows are unrecoverable
(403-blocked). Full reasoning, stop conditions and the 30bp fee-check contract are in
direction-review.json and candidate-manifest.json; no return or Sharpe number is
computed in this brief.
