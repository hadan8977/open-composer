# External Brief: t20260930_12_smallcap_gap_auction

## Objective

T-20260930-12 (C1b): with only information available before 09:27 ET (SIP pre-market minute bars visible on the free plan up to the 09:11 bar, or to 09:26 on paid real-time SIP), does the $5-20M dollar-volume gap-down long (K lowest z, open buy, close sell) keep >= 20 bp/day gross, and beat a same-pool random basket placebo?

## Sources

10 source cards recorded in `external-brief.json` (4 paper-type). Source card records:
`reports/harness/source_cards/t20260930_12_smallcap_gap_auction.jsonl`. Six cards (Goyal-Jegadeesh-Wu, Lou-Polk-Skouras, Nagel, Abdi-Ranaldo, UTP condition codes,
Concretum, Alpaca FAQ/forum) are reused from T-20260930-11 with unchanged snapshots; two are new and
fetched 2026-09-30 07:21Z: Alpaca market-data plans (free plan real-time IEX only, SIP history limited to the
latest 15 minutes, Algo Trader Plus $99/month) and Alpaca orders (OPG orders after 09:28 ET rejected).
Topic coverage: official_auction_price_vs_daily_bar_open_close, closing_auction_price_impact_goyal_jegadeesh_wu, opening_auction_illiquidity, cta_utp_sale_condition_codes_q_o_m_6, overnight_vs_intraday_return_split_lou_polk_skouras, short_term_reversal_as_liquidity_provision_nagel, spread_estimation_from_daily_prices_abdi_ranaldo, gap_fade_published_claim_concretum, alpaca_free_plan_iex_realtime_sip_15min_delay, alpaca_opg_order_0928_et_deadline.

## Scope

Supports the single-mechanism lightweight path `smallcap_premarket_gap_long` only. Not a promotion or paper decision.
