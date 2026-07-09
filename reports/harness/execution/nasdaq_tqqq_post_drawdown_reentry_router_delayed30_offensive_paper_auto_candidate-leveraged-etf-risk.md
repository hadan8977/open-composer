# Leveraged ETF Risk Note — nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate

Generated: 2026-07-09

## Instruments
- TQQQ
- SOXL

## Path-Dependency
Daily-rebalanced leveraged ETFs compound the underlying's daily returns. Multi-day holding periods diverge from the advertised leverage factor in volatile regimes — this is rebalance decay, not tracking error.

## Gap Risk
Opening gaps are amplified by the leverage factor. A 2% underlying gap maps to ~6% on a 3× ETF. The execution policy must include a gap filter; see gap_stress_report.

## Capacity
Leveraged ETFs often have thinner opening-auction liquidity than the underlying. Participation cap should be tightened (see execution_policy.participation_cap).

## Mitigations
- Use price-protected order types (LOO/OPG limit) instead of naked market.
- Apply the gap filter from execution_policy.gap_filter.
- Recompute %ADV impact using the ETF's own ADV, not the underlying's.
- Review weekly via TCA against the official open price.
