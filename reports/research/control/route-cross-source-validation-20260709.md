# Route Cross-Source Validation

- Strategy: `nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate`
- Status: `blocked`
- route_cross_source_pass: `False`
- Route: `defensive_overlay:transition_TQQQ_replacement_mom_positive_lb20_min0_delay30_base[pdr:semi_light_harddd6_v0.65_breadth1_softQQQ_defGLD_rec104_mom60max20_ext35_cool5QLD_confirm5_melt6040x25_detdd8m10]`

## Blocker

- alternate source overlap does not cover required windows

## Coverage Gaps

| window | start | end | reason |
| --- | --- | --- | --- |
| q4_2018 | 2018-10-01 | 2018-12-31 | no evaluated sessions in required crisis window |
| covid_crash | 2020-02-19 | 2020-03-23 | no evaluated sessions in required crisis window |
