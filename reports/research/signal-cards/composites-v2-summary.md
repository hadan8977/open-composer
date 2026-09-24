# composites-v2: summary

Admission rule (preregistered 2026-09-24T10:55:00+00:00): rank: the library-v1 rank rule (stable_years AND beats_shuffle AND a T1 or T2 top-30 book positive at 20 bp in the full and 2024+ windows AND max |t| >= 2.5); beats_reference: in the 2024+ window, the T1 top-30 book held 20 sessions at 20 bp has a higher Sharpe AND a shallower max drawdown than mom_12_1_roe_universe's; the full-window comparison is reported, not required, because of survivor bias; strategy_screen: report the T1 20-session book's 2024+ CAGR and max drawdown against G1 (>= 50%/yr, max DD >= -35%); a pass here only earns a preregistered strategy iteration with the exact anchor window and costs, not a promotion

| signal | mode | h | IC or excess | t | 2024+ | best book tier: excess/yr full / 2024+ (20 bp) | verdict |
|---|---|---|---|---|---|---|---|
| mom_12_1_roe_universe | rank | 20d | 0.016 | 1.1 | 0.030 | t1: 19.4% / 43.1% | admit |
| comp_c4_mom_roe | rank | 20d | 0.030 | 2.6 | 0.032 | all: 6.7% / 14.9% | admit |
| comp_c5_mom_roe_insider | rank | 20d | 0.029 | 2.7 | 0.031 | all: 6.8% / 15.4% | admit |
