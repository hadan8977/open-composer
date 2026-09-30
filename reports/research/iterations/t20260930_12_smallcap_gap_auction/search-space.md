# Search Space: t20260930_12_smallcap_gap_auction

Single-mechanism lightweight path (no campaign contract). One path, `smallcap_premarket_gap_long`, with 4 preregistered
candidates (X15 caliber x K in {10, 5} x weight {equal, 1/sigma21}) sharing spec `strategy_specs/drafts/t20260930_12_smallcap_gap_auction.yaml`.
The decision cell is X15_K10_EW. Benchmark family (comparators, not candidates): the same four cells on
the X0 caliber (bars to 09:26 ET, paid real-time SIP) and on the LA caliber (daily open, the C1 look-ahead
control); the 100-seed same-pool random K-basket placebo; the same-pool equal-weight open-to-close baseline.
Family cumulative trial count for DSR (if a ledger is built): T-32 + C1 + these 12 cells.
Costs: `reports/research/iterations/t20260930_12_smallcap_gap_auction/cost-table.json` (none in the gross-edge stage).
The candidate manifest is the authoritative per-candidate binding; this file is descriptive only.
