# Hypotheses: h20260930_01_rebalancing_front_run

## H1 (T-20260930-01)

- Hypothesis: when the simulated 60/40 portfolio is equity-overweight (Threshold above zero, Calendar in the last week of the month) SPY earns lower returns in the next session's open-to-close leg, and the reverse when underweight, because balanced funds and pensions sell (buy) equities on predictable schedules (Harvey, Mazzoleni, Melone, NBER w33554; Parker, Schoar, Sun).
- Failure mode: (a) the effect sits in the overnight leg that a next-open fill cannot capture; (b) it decayed after the 2016 start of the local sample as crowding grew (Daniel; Bloomberg); (c) it exists only in the bond leg or the spread; (d) 10 bp per side on a daily flip eats a sub-20 bp effect; (e) a small number of crisis days drive the Sharpe.
- Measurement: scripts/run_h20260930_01_rebalancing.py regress: HC3 regressions, three return segments, three windows, 500 date-shift placebos; results.json gate_checks.
- Stop/Pivot criterion: stop unless G1-G3 of preregistration.md pass; then continue only if an equity-leg candidate reaches net Sharpe >= 0.8 full and anchor. Bond-leg spreads never advance without an owner decision. No variants after results.
