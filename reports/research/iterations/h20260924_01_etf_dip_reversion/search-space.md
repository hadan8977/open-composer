# Search space -- h20260924_01_etf_dip_reversion

One preregistered path, `etf_dip_reversion_screen`, 24 candidates: 6 published
rules (D1 IBS-Algotradekit, D2 IBS-Pagonidis raw, D3 Connors R3, D4 Connors
RSI(2) classic, D5 Connors 3-Day High/Low, D6 IBS-filtered RSI(2)) x 2 signal
underlyings (QQQ, SPY) x 2 execution instruments (1x = the same ETF, 3x = the
matching leveraged ETF, TQQQ for QQQ and UPRO for SPY). This is the exact
`24` candidate cap the single-mechanism lightweight path allows, and no
threshold, window or added cell exists beyond it: every IBS threshold, RSI
threshold, EMA/SMA window and exit rule is copied from the cited source
(Pagonidis 2014, StockCharts ChartSchool, and the repo's local
fmzquant/strategies git clone at commit 7853bb2), not searched or optimized.
Full candidate detail lives in `candidate-manifest.json`.

## What was narrowed, not widened

The repo's fmzquant/strategies addendum (`reports/research/intel/I-20260923-10-fmzquant-strategies.md`,
section 5) found 6 dip-reversion files in the corpus; three are direct
TradingView ports of published rules (D1, D3, D5 here) and the other three
(a "High Position IBS" short-side variant, a second IBS reversion system, and
a VIX-fix variant) were dropped because they either duplicate D1's mechanism
on the short side (out of scope: this repo is long-only) or add a VIX-based
filter with no local VIX-futures capability. D4 (classic RSI(2)) and D6
(IBS-filtered RSI(2)) are added from Pagonidis's and StockCharts' own text,
not from the repo, because they are the two simplest, most literally
"exactly as published" variants of the same mechanism and the task brief
explicitly asks for them. The repo's own `Larry-Connors-RSI2均值回归策略.md`
file was read and excluded as a source: its trend condition is inverted
relative to Connors' published rule (a quality defect noted in the corpus
review), so D4 is sourced from StockCharts ChartSchool instead.

## Timing conventions (T0/T1/T2) and why only T1 is a candidate

T0 (official close signal, same-close fill) is the unexecutable upper bound
-- no real order can be priced off a close that has not happened yet -- and
is exactly the convention one of the three ported Pine sources (D5, 3-Day
High/Low, `process_orders_on_close=true`) uses in its own backtest. T2
(official close signal, next-session official open fill) is this repo's
other standard convention, from `scripts/run_h20260918_05_recent_menu.py`.
T1 (a 15:50 ET America/New_York minute-bar proxy for the official close --
today's close = the last minute close at or before 15:50 ET; today's high/
low = the running max/min of minute bars from 09:30 to 15:50 ET; all other
indicator inputs use prior official daily closes plus this proxy -- filled
via a market-on-close order submitted before the 15:50 cutoff, at the
official close of the same session) is the only realistic, executable
convention among the three, and is therefore the only one counted as a
candidate; T0 and T2 are computed for every cell as report-only diagnostics.

A close reading of the Algotradekit Pine source (D1, `fmz.com/strategy/484915`)
found that it measures IBS from the *prior* completed bar
(`high[1]`/`low[1]`/`close[1]`) while the EMA trend filter uses the *current*
bar's own close, and pairs this with the Pine default
`process_orders_on_close=false` (next-bar-open fill). Taken completely
literally, this means the published backtest's entries fill a full session
later than a same-day-IBS/next-open reading would, because the `[1]`-
referenced IBS is already fully known the instant the next bar opens (a
common non-repainting idiom for live TradingView alerts, not a deliberate
extra-latency design choice). This engine measures IBS, RSI and the EMA/SMA
trend filters from the *same* bar whose close is being decided, for all of
T0/T1/T2 and for all six rules uniformly -- matching Pagonidis's own
definition, StockCharts' RSI(2) writeup, and the other two ported Pine
sources' (D3, D5) own conventions -- and discloses this as a deliberate,
disclosed divergence from a fully literal port of D1's extra one-session
lag, not a silent correction. Separately, the Pine source's own comment sets
SPY's max trade duration to 12 sessions (not 14); this iteration follows the
task brief's frozen "14 sessions" for both QQQ and SPY and discloses the
divergence rather than substituting 12 unasked.

## Placebos

Two families, matched per candidate: (1) random entry timing, matched to the
real candidate's trade count and holding-period distribution, sampled only
from days that satisfy the rule's own trend filter where it has one, 60
seeds; (2) the frozen calendar-shift placebo from
`scripts/run_h20260918_05_recent_menu.py`, 20 seeds. G3 (every declared
placebo beats the true cell on select Sharpe <= 10% of seeds) uses both;
the trade-level research-admission rule's percentile test uses the
random-entry-timing placebo specifically, since it is the control that
isolates timing skill from generic long-ETF drift.

## Supplementary persistence table

A 2016-2026 per-calendar-year table (daily bars only, T0/T2, 10 bp, for each
of the six rules on QQQ/SPY/IWM/DIA) is computed in Stage A and reported in
`report.md` as context: it shows whether a rule's edge (where one exists) has
been persistent, decaying, or regime-specific across years the frozen
select/holdout/anchor windows do not individually resolve. It is explicitly
not an admission criterion -- the frozen G1-G5 and research-admission rule
alone decide the verdict -- consistent with the mission's rule that a
strategy may validly work only in a recent or limited regime.
