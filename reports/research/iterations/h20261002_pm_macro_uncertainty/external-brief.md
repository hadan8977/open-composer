# External Brief: h20261002_pm_macro_uncertainty

Structured entries are in `external-brief.json` (8 sources, 6 of them papers). Summary:

1. **Diercks, Katz and Wright (FEDS 2026-010, Feb 2026)**: Kalshi distributions for FOMC, CPI, payrolls and GDP are well behaved, react to news and their variance falls after releases; Kalshi beat the Bloomberg consensus on headline CPI. No asset-return test. This is why the standard deviation of the implied distribution the afternoon before a release is a usable, release-specific uncertainty measure, and why a Kalshi-minus-consensus gap (H2) is worth one test.
2. **Ai, Bansal and Guo (NBER w31923, Dec 2023)**: 10.68 bp per announcement day versus 0.93 bp otherwise (1961-2023), non-FOMC 8.65 bp (t 3.71), 16.33 bp in 2020-2023. The premium is the prior; whether it scales with uncertainty in 2023-2026 is the open question. The 15 bp bar for D sits above the unconditional non-FOMC premium on purpose.
3. **WillBtK/macro_kalshi (MIT, fork of the FEDS replication package)**: the middle-out monotone cleaning of threshold markets that this iteration ports; no consensus data in the repository.
4. **Amburgey (arXiv 2504.02731) and ForesightFlow (arXiv 2605.00493)**: equities react to prediction-market shocks contemporaneously and documented informed trading sits in deadline markets with no traded-asset link. Both argue against a generic lead-lag use of odds, so the registry row `dir:prediction_market_crypto_as_equity_signal` stays `evidence_too_weak` and this iteration tests a risk-compensation mechanism instead.
5. **Polymarket-v1 (arXiv 2606.04217) and Forecasting Economy datasets (arXiv 2604.20421)**: possible Polymarket history sources for later steps, not used here.
6. **Kalshi API probe (2026-10-02)**: KXCPI 67 events, KXPAYROLLS 45, KXGDP 25, KXFED 52, KXU3 65; KXPCE does not exist; historical cutoff 2026-08-03; data-release markets close 08:25 ET.

The evidence changed the design in four ways (see `candidate_matrix_revisions`): U_rel at 15:00 ET on T-1 as the conditioning variable, FOMC days reported apart from the primary statistic, no generic lead-lag candidates, and a sample that starts in mid-2023 because pre-2023 Kalshi events are bracket markets.
