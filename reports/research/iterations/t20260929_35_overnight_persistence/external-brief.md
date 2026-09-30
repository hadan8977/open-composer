# External Brief: t20260929_35_overnight_persistence

## Objective

T-20260929-35 (C2a): in 2024-01-08..2026-09-29, do top-1500 dollar-volume US common stocks ranked by past overnight return (ON_5/21/63/252, TOW_21) keep a next-night close-to-open long/short edge of at least 16 bp/night gross, with Newey-West t >= 2 and a same-pool random placebo beat >= 0.90, so that two auction legs with no quoted spread can pay the cost?

## Sources

11 source cards recorded in `external-brief.json`
(9 paper-type). Source card records: `reports/harness/source_cards/t20260929_35_overnight_persistence.jsonl`.
Topic coverage: overnight_persistence_lou_polk_skouras, weekly_overnight_persistence_aboody, tug_of_war_future_returns_akbas, overnight_borrow_margin_arbitrageur_constraint_bogousslavsky, intraday_periodicity_contrast_heston, open_close_flow_periodicity_haendler, closing_and_opening_auction_price_impact_goyal_jegadeesh_wu, alpaca_cls_opg_order_deadlines, alpaca_etb_borrow_fee, overnight_daytime_etf_cost_sensitivity_salotra, past_year_overnight_predictor_lachance.

## Scope

This brief supports the single-mechanism lightweight path (search-space
`single_mechanism_no_campaign_attestation: true`). Its evidence backs the
preregistered candidate grid for path `overnight_persistence_auction` only, not any other
mechanism family or promotion decision.
