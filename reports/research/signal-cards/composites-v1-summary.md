# composites-v1: summary

Admission rule (preregistered 2026-09-23T13:44:11+00:00): rank: the library-v1 rank rule (stable_years AND beats_shuffle AND a T1 or T2 top-30 book positive at 20 bp in the full and 2024+ windows AND max |t| >= 2.5); beats_reference: the T1 top-30 book held 20 sessions at 20 bp has a higher Sharpe AND a shallower max drawdown than mom_12_1's in the full window; strategy_screen: report the T1 20-session book's 2024+ CAGR and max drawdown against G1 (>= 50%/yr, max DD >= -35%); a pass here only earns a preregistered strategy iteration with the exact anchor window and costs, not a promotion

| signal | mode | h | IC or excess | t | 2024+ | best book tier: excess/yr full / 2024+ (20 bp) | verdict |
|---|---|---|---|---|---|---|---|
| comp_c1_mom_quality | rank | 20d | 0.050 | 2.9 | 0.050 | t2: -3.4% / -1.5% | reject |
| comp_c2_mom_quality_insider | rank | 20d | 0.049 | 2.9 | 0.049 | t3: -3.9% / -2.2% | reject |
| comp_c3_mom_52w | rank | 20d | 0.033 | 2.1 | 0.043 | all: 1.8% / 12.2% | admit |
