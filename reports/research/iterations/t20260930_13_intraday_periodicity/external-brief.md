# External Brief: t20260930_13_intraday_periodicity

## Objective

T-20260930-13 (C2b): in 2024-01-08..2026-09-29, do top-1500 dollar-volume US common stocks ranked by the past-20-day mean of the same half-hour return (opening 09:30-10:00, closing 15:30-16:00) keep a same-period long/short edge of at least twice the one-auction-leg round-trip cost RT1, with Newey-West t >= 2 and a same-pool random placebo beat >= 0.90?

## Sources

9 source cards recorded in `external-brief.json`
(6 paper-type). Source card records: `reports/harness/source_cards/t20260930_13_intraday_periodicity.jsonl`.
Topic coverage: same_half_hour_periodicity_heston, open_close_flow_periodicity_haendler, half_hour_window_definitions_lou_polk_skouras, closing_arbitrageur_flow_bogousslavsky, closing_and_opening_auction_price_impact_goyal_jegadeesh_wu, closing_auction_share_nyse, alpaca_cls_opg_order_deadlines, alpaca_etb_borrow_fee, abdi_ranaldo_spread_estimator.

## Scope

This brief supports the single-mechanism lightweight path (search-space
`single_mechanism_no_campaign_attestation: true`). Its evidence backs the
preregistered candidate grid for path `intraday_periodicity_one_auction_leg` only, not any other
mechanism family or promotion decision.
