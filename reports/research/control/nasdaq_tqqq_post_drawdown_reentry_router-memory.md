# Research Memory: nasdaq_tqqq_post_drawdown_reentry_router
- Objective: Maintain 100% gross exposure, full-window max drawdown better than -40%, full Sharpe above 1.0, OOS/recent drawdown better than -40%, and post-2023 plus curr...
- Fix first: promotion:hybrid_router_research; promotion:out_of_sample; promotion:strict_data
- Router: substate=observation_only latest=2026-05-20 orders=1155
- Data tier: research_cross_check
- Data blocker: Router promotion requires research_strict or paper_ready data; acquisition_tier=research_cross_check is not paper-ready
- Best new direction: delayed-entry overlay on common 1m window 2024-06-03..2026-05-27; top candidate delay30 on TQQQ/QLD/SOXL/USD, ann=92.34%, Sharpe=2.061, maxDD=-20.65%, TQQQ total=119.01%.
- Next: rerun or cross-check the selected route on research_strict or paper_ready daily data before more parameter optimization; rerun `oc strategy evidence <spec>` after strict data evidence is written; pause broad parameter search until strict data evidence is no...
- Control: use evidence first, change <=2 variables, no global factor bans, warn not hard-block early diagnostics.
