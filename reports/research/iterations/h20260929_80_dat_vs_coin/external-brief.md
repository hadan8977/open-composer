# External Brief: h20260929_80_dat_vs_coin

## Objective

T-20260929-80: after 2024-01-11 (spot bitcoin ETFs), does a beta-hedged spread of bitcoin/ether treasury stocks (MSTR; BMNR+SBET) and a miner basket versus the coin they track carry a tradeable mean-reversion (Z family, premium high -> DAT underperforms) or continuation (M family) signal after 10 bp per side on both legs plus borrow on the short DAT leg? Stage 1 is a cheap IC negation test; only if it passes are 24 preregistered candidates screened (K1/K2, DSR over 24, placebo, 15%/yr borrow, 20 bp).

## Sources

10 source cards recorded in `external-brief.json`
(4 paper-type). Source card records: `reports/harness/source_cards/h20260929_80_dat_vs_coin.jsonl`.
Topic coverage: mstr_premium_to_nav_history, dat_mnav_compression_2025_2026, mstr_btc_beta_and_hedge_ratio, closed_end_fund_premium_discount_theory, gbtc_etf_conversion_regime_break, short_leg_tail_risk_and_borrow, mnav_definition_dispersion, miner_stock_vs_coin_spread.

## Scope

This brief supports the single-mechanism lightweight path (search-space
`single_mechanism_no_campaign_attestation: true`). Its evidence backs the
preregistered candidate grid for path `dat_vs_coin_spread` only, not any other
mechanism family or promotion decision.
