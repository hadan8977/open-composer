# Search space: h20260928_23_s1_s2_rebalance_timing

One path, 21 candidates, no training, no parameter search, no adoption decision.

- O00..O20: live S2 with the signal close moved 0..20 sessions
  after the live rebalance date. O00 is the live rule and is asserted bit-equal to
  `salvage.run_cell`. All 21 are descriptive; none can be adopted from this run.
- Costs 10 bp per side primary, 20 bp stress; next-open fills; frozen stress/select/anchor/holdout
  windows (same as H-20260928-01, S1's stress window starts 2017-01-03 for its 252-session lookback).
