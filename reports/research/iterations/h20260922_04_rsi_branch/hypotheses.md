# Hypotheses: h20260922_04_rsi_branch

Round 1 of brief B-1. Replication of the published Composer RSI-extreme branch
family under the frozen H-20260918-05 windows, costs, fill assumption and
placebo machinery.

## Hypothesis h_rsi_extreme_branch_carries_the_return

On US sector ETFs between 2023-09 and today, a daily branch tree that (a) moves
the whole book to a long-volatility ETF or to cash when RSI(10) on the reference
index is above 80, (b) moves it to TQQQ when RSI(10) is below 30, and (c)
otherwise holds the single strongest 21-day performer of a fixed menu, earns a
higher anchor-window Sharpe and CAGR than holding that same menu equal-weighted,
and the advantage comes from the branch signal rather than from the menu or from
the bull market.

The RSI window (10), the overheat threshold (80) and the oversold threshold (30)
are not free parameters: they are values the source strategy publishes in plain
English on its own page, and the snapshot binding that quote is in
`sources/composer-sector-rotator-ms.html`.

## Failure mode

Three ways this fails, in descending order of likelihood.

1. **The menu did it.** The 3x sector menu (TECL, FAS, ERX, CURE, DUSL) rose
   hard over the whole evaluation window. Any branch tree layered on top of it
   inherits that. The random-single-pick placebo (60 seeds from the same menu,
   same calendar) is the control: if a meaningful share of random picks match
   the true cell, the ranking contributes nothing.
2. **The branch signal is decoration.** L-20260918-05 already showed that a
   single moving-average gate on leveraged ETFs does not survive a calendar
   shift in this window. If shifting the RSI signal by 1-20 sessions leaves the
   result intact, the branch tree is the same illusion and the family is
   refuted.
3. **The hedge leg is a tax.** UVXY targets 1.5x daily and decays across
   multi-day holds by the issuer's own statement. The overheat branch may be
   paying for protection it never collects in a window with no sustained bear
   market. The BIL arm of the grid is the matched control that isolates this.

A fourth, quieter failure: daily rebalancing on a 1-of-11 or 1-of-5 rotation can
turn over the book often enough that 20 bp per side removes the edge even when
the signal is real.

## Measurement

- Rank cells on selection-window Sharpe only (2023-09-18..2025-12-31). The
  holdout (2026-01-02..2026-09-17) is never used to choose anything.
- Report every cell on the anchor window (2024-01-08..2026-09-16) so the numbers
  are directly comparable to SPMO's 35.8% / -20.3% / 1.28.
- Benchmarks: SPY, MTUM, SPMO, QQQ, TQQQ, the live S1 sleeve
  (rot_A2_sector_lb252_top2_weekly) and equal-weight holdings of both menus.
- Volatility-matched excess return against SPY, so a leveraged cell cannot claim
  credit for simply sliding up the same risk-return line.
- Placebo 1: RSI signal calendar-shifted by a random 1-20 sessions, 20 seeds.
- Placebo 2: random single pick from the same menu on the same calendar, 60
  seeds.
- Costs at 10 bp and 20 bp per side, charged on the execution session.
- Diagnostics: annual turnover, days held in each branch, and the realized
  return contribution of each of the three branches.

## Stop/Pivot criterion

Stop after this single round and write `reports/research/lessons/L-20260922-04.md`
if any of the following holds:

- no cell reaches anchor CAGR >= 50% with max drawdown <= 35%, and none reaches
  Sharpe >= 2.0 with CAGR >= 30%;
- the best surviving cell has holdout Sharpe < 1.0 or a negative holdout return;
- either placebo beats the true cell in more than 10% of seeds;
- 20 bp per side breaks the gate the cell passed at 10 bp.

Pivot (round 2, only with variations already named in brief B-1) is allowed only
if a cell clears G1/G1' and G2 but fails on cost or turnover, because that is the
one failure mode with a preregistered remedy (weekly rebalance, already in the
grid).
