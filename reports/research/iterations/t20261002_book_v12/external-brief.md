# External Brief: t20261002_book_v12

## Objective

Equity book v1.2 (simple construction): preregistered after T-20261002-25 passed its mechanical rule. Test whether the T-25 R6 construction (9-theme composite M0/M1, industry-demeaned rank weights, easy-to-borrow shorts, book-level EWMA SPY beta hedge, VIX > 20.60 halving, weekly 5 tranches, fill at the close of t+1) survives an Alpaca Reg T account at $1M -- gross incl. hedge and T-bills <= 1.8x equity, whole shares and the engine minimum order, netted tranches, conservative delisting bound, borrow 0 bp on ETB per Alpaca docs, no interest on cash -- and reaches evaluation-standard v2 tier P1 under a 10-variant DSR family (111-trial program DSR disclosed, < 0.50 caps at P1), with a 100-seed placebo, so that quant1 (F1 neutral, k 0.5 plus T-bill leg) and quant2 (F2 SPY 1.0 plus a 0.3 overlay) can start paper incubation and a forward record from 2026-09-18.

## Sources

8 source cards recorded in `external-brief.json`
(5 paper-type). Source card records: `reports/harness/source_cards/t20261002_book_v12.jsonl`.
Topic coverage: professional_longshort_net_sharpe_benchmarks, anomaly_net_of_cost_decay, trading_cost_square_root_impact, factor_replication_themes, factor_timing_volatility_state, broker_margin_rules_reg_t, broker_cash_interest_and_borrow_fees, easy_to_borrow_short_constraints, recent_regime_evaluation.

## Scope

This brief supports the single-mechanism lightweight path (search-space
`single_mechanism_no_campaign_attestation: true`). Its evidence backs the
preregistered candidate grid for path `simple_construction_equity_book_v12` only, not any other
mechanism family or promotion decision.
