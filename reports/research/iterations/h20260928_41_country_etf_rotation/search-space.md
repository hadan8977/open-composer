# Search Space: h20260928_41_country_etf_rotation

Single path (lightweight single-mechanism exemption, no campaign contract):
`country_etf_rotation_screen`, 8 candidates total, all preregistered in
`candidate-manifest.json` before any return is computed.

- lookback in {63, 252} trading days x top_n in {1, 2} x rebalance in
  {monthly, weekly} = 2 x 2 x 2 = 8. Mechanism (rank by lookback return,
  top_n, absolute-momentum filter vs SHY, equal-weight survivors) reused
  unedited from `h20260928_40_equity_etf_menus.make_rotation_fn`.

Total candidate budget: 8 (<=24, single path, lightweight exemption valid).

Cost assumptions: 10bp per side primary, 20bp per side stress, close signal
-> next session's open fill -- the frozen project contract, see
`cost-contract.json`.

Benchmark family: EWJ/EWG/EWU/EWA/EWC/EWZ/INDA/EWY/EWT/SHY buy-and-hold plus
the S3 incumbent (`benchmark_v1_country_etf_vs_s3_k1_k2`) -- K1/K2/
strong_keep/watch_recent against S3's own frozen reference Sharpe (anchor
1.4853, stress 0.8059), per the owner's 2026-09-28 "Sharpe first, not
sizing" rule.
