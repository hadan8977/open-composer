# Research Memory: nasdaq_regime_tqqq_hybrid_router_daily
- Objective: risk_adjusted_benchmark_alpha_after_costs
- Router: substate=observation_only latest=2026-05-20 orders=557
- Data tier: paper_ready_live
- User feedback 2026-05-26: this defensive router is too close to a low-beta QQQ
  substitute and fails the desired return objective versus the original 100%
  TQQQ/iter2 idea. Keep it only as a defensive observation candidate.
- New standard: next research candidate must beat the original 100% TQQQ iter2
  baseline on OOS total return, OOS annualized return, and full-window total
  return after costs. Lower drawdown alone is not a pass.
- Next draft: strategy_specs/drafts/nasdaq_tqqq_return_enhanced_router_daily.yaml
  widens the universe and allows up to 100% gross exposure for a return-first
  router. First step is to recover the original iter2 spec or reconstruct a
  same-window 100% TQQQ baseline and label it clearly.
- Next: run a bounded parameter sweep only after defining a small search space; treat overfit, sample, and promotion warnings as diagnostics during exploration; move toward promotion diagnostics rather than broad exploration; align next trial with research design s...
- Control: use evidence first, change <=2 variables, no global factor bans, warn not hard-block early diagnostics.
