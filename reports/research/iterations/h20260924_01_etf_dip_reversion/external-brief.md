# External brief -- h20260924_01_etf_dip_reversion

The owner asked on 2026-09-24 to evaluate the US-stock strategies inside
github.com/fmzquant/strategies. The corpus review
(`reports/research/intel/I-20260923-10-fmzquant-strategies.md`) found the
repo is a content-marketing mirror of TradingView ports with no attached
out-of-sample or live evidence, 82% of it crypto; among its 132 US-equity-
flavoured entries, its 2026-09-24 addendum narrowed to exactly one family
with a published mechanism and a multi-year post-publication public record:
short-term index-ETF dip reversion.

## Mechanism

Pagonidis (2014, NAAIM) defines Internal Bar Strength (IBS) -- the position
of a day's close within its own high-low range -- and shows it forecasts
next-day close-to-close equity ETF returns (0.35% mean return after a day
with IBS below 0.20, versus -0.13% after IBS above 0.80), attributing the
effect to intraday overreactions that are corrected the next day. This sits
inside a much older academic line: Lehmann (1990, QJE/NBER) documents
weekly-horizon "winner"/"loser" return reversals that survive transaction-
cost adjustment, and Kloßner, Becker & Friedmann (2012, Journal of Banking
& Finance) build an OHLC-based statistical test for intraday overreaction
specifically -- both cited directly in Pagonidis's own literature review.
Pandey & Joshi (2023, arXiv) extend IBS testing to country ETFs post-2013,
showing continued academic interest, though on a different, and per
Pagonidis's own finding weaker, instrument class than the US index ETFs this
iteration tests.

## Exact rules

Pagonidis's own text supplies D2 (raw IBS<0.20, one-session hold, no trend
filter) and D6 (his own IBS<=0.5 filter on a Cutler's RSI(3) rule, adapted
here with StockCharts' tighter RSI(2)<=5/SMA(200)/SMA(5) parameters and
IBS<0.20). StockCharts' ChartSchool RSI(2) writeup supplies D4's exact
entry (200-day SMA trend filter, RSI(2) buy threshold) and exit (5-day SMA)
rule, explicitly attributed to Larry Connors. The repo's own local git clone
of fmzquant/strategies (commit 7853bb2, per I-20260923-10) supplies the
literal Pine source for D1 (Algotradekit's IBS strategy, fmz.com/strategy/
484915), D3 (Connors & Alvarez 2009 "R3", fmz.com/strategy/439643) and D5
(Connors & Alvarez 2009 "3-Day High/Low", fmz.com/strategy/429146), read
directly rather than paraphrased from the repo's own marketing description
-- this reading is what surfaced that D1 measures IBS from the prior
completed bar (an extra-lag idiom this iteration deliberately does not
reproduce) and that D5's own backtest uses an unexecutable same-close fill.
The repo's `Larry-Connors-RSI2均值回归策略.md` file was read and rejected as a
source: its trend condition is inverted versus Connors' published rule.

## Prior local evidence

`dir:giants_sweep_published_etf_rules` (refuted) is the closest prior local
test: 0 of 24 published ETF/leveraged-ETF rules cleared this repo's frozen
G1-G5 bar under the identical protocol this iteration reuses. Its closest
cell, `f1_tqqq_rsi_no_hedge_ablation`, is a Composer-style RSI(10) trend/
hedge branch rule on TQQQ (anchor CAGR 15.9%, max drawdown -5.2%, anchor
Sharpe 1.37, holdout Sharpe 1.49, select Sharpe 1.13; failed G1 needing
CAGR>=50%/DD>=-35%, or the G1' alternate Sharpe>=2.0/CAGR>=30%) -- a
structurally different rule (RSI(10) branch-to-cash, not IBS or RSI(2) mean
reversion) on a different instrument focus than this round's IBS/Connors
rules on QQQ/SPY signals with 1x/3x execution. This sets an honest prior
that most or all of this round's 24 cells may also fail G1's CAGR bar,
without treating the census as a direct test of this specific mechanism.
This repo's signal-card library v1 separately rejected generic technical
indicators (RSI/MACD/Bollinger) as cross-sectional stock-ranking signals on
a broad universe -- a different claim from this round's single-instrument,
timing-based mean-reversion test on index ETFs specifically, and consistent
with the owner's own tier framework, which ranks pure technical indicators
low but not zero, and with this task's explicit instruction to justify the
family by its published mechanism rather than by pattern-fit.

## What this iteration adds beyond the published sources

Realistic T1 timing (a 15:50 ET minute-bar proxy for the official close,
market-on-close fill) in place of the same-close fill one Pine source (D5)
explicitly backtests at and the extra-lagged prior-bar-IBS/next-open reading
another (D1) implies when read literally; this repo's own frozen G1-G5
gates, costs (10/20 bp per side) and panel; a trade-level research-admission
rule (mean net return per trade, trade-level t-statistic, a random-entry-
timing placebo matched to trade count and holding-period distribution, and a
T1-vs-T0 fraction test) none of the cited sources report; and a supplementary
2016-2026 per-calendar-year persistence table across QQQ/SPY/IWM/DIA,
reported as context rather than as an admission criterion.
