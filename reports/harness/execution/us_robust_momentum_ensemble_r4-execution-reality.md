# Execution Reality: us_robust_momentum_ensemble_r4

No execution is authorized. The reference backtest uses the next Longbridge provider-bar open, which is not evidence of a primary-exchange official open, auction queue position, partial fill, or a limit-order fill.

Three future order styles were compared. MOO/OPG offers the highest opening-auction fill certainty but no price protection. LOO/OPG bounds price but introduces missed-fill and portfolio-drift risk. A delayed five-minute limit reduces auction uncertainty but changes the signal and must be evaluated as a separate execution variant. The future reference policy is LOO/OPG with skip-and-hold fallback, not a market-order fallback.

At 10, 20, and 40 bps one-way stress, D06 returns `45.56%`, `44.29%`, and `41.76%`. These are modelled turnover costs only. They omit spread, impact, latency, auction imbalance, limit misses, and delayed official opens. Alpaca Paper explicitly omits several of these mechanisms, so paper PnL cannot close the gap.

Capacity is blocked because no portfolio notional or official-open volume ledger exists. Before any paper order, collect matched MOO/LOO/delayed-open observations with decision, submission, acceptance, official-open, and fill timestamps; enforce at most 0.1% ADV and 1% official-open volume until evidence supports otherwise.

Conclusion: `blocked`; observation files only.
