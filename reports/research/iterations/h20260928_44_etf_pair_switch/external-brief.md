# External Brief: h20260928_44_etf_pair_switch

Two sources ground this batch's own mechanism and its negative-evidence
check, both opened fresh this session: the QuantConnect forum post
"QQQ/SPY Momentum Rotation System" (the direct source named in the
T-20260928-44 queue task, re-opened via WebFetch to independently confirm
its rule, numbers and the platform staff's disclosed code-bug critique) and
Robot Wealth's dual-momentum review (via WebSearch, naming the whipsaw and
recovery-lag failure modes this batch's stress window and STATIC5050 placebo
are designed to expose). Two more are reused, unmodified, from the prior
verified T-40 round's source cards without a fresh re-fetch this session:
Quantpedia's cross-sectional-momentum-across-style-ETFs mechanism
description (background grounding for the mechanism family rotation_cell
already implements) and Antonacci's dual-momentum absolute-momentum-filter
description (grounds the absolute-momentum-vs-SHY filter every PAIR
candidate reuses unedited).

No source grounds a new momentum formula, weighting scheme, or
absolute-momentum rule -- every PAIR candidate in this batch reuses
`run_h20260918_05_recent_menu.py:rotation_cell`'s mechanism unedited at menu
size 2 / top_n=1, imported directly rather than reimplemented, so the
lookback-return definition is guaranteed identical to S1-S3's own live
engine. The STATIC5050 placebo family introduces no new signal either -- it
is a fixed 0.5/0.5 book with no ranking logic. The only new degrees of
freedom in this batch are the six pairs (ticker pairs) and the
preregistered {63, 126}-day lookback grid, which was fixed before any
backtest ran.
