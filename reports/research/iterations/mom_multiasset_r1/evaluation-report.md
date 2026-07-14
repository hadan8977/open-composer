# Multi-Asset Momentum Deterministic Evaluation

- Run: `20260714T071249Z`
- Data as of: `2026-07-13T04:00:00+00:00`
- Candidates: `60`
- One-way cost: `10.0 bps`
- Research pass: `false`

## Path Decisions

| Path | Trial | Decision | OOS return | OOS Sharpe | OOS IR | Fold gate |
|---|---|---|---:|---:|---:|---|
| P1_etf_absolute_relative | p1_lb252_reb5_gate0 | continue | 168.13% | 1.00 | 0.76 | true |
| P2_sector_risk_adjusted | p2_6m_12m_vol0_top3 | diagnostic_only | 14.51% | 1.28 | -0.14 | false |
| P3_stock_cross_sectional | p3_12_1_vol0_top5 | continue | 166.50% | 2.86 | 2.36 | true |
| P4_stock_trend_quality | p4_high_52w_plus_6m_dvol0_top10 | diagnostic_only | 70.16% | 2.50 | 1.18 | false |
| P5_stock_residual_sector_relative | p5_sector_relative_126_top10_cap2 | continue | 65.32% | 2.58 | 0.95 | true |

## Interpretation

Stock history is a current-universe exploratory replay and cannot by itself earn research_pass. Accepted rows are method survivors eligible for the bounded ML round and frozen forward virtual paper, not promoted Alpha.

## Limitations

- Stock history uses a universe selected from the 2026-07-14 snapshot and is survivorship-biased.
- Historical stock results can eliminate designs but cannot independently establish research_pass.
- Longbridge Nasdaq Basic is not consolidated SIP market data.
- Virtual-paper forward evidence must remain frozen and must not be used for informal retuning.
