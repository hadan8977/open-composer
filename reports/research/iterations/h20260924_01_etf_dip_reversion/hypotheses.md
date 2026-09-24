# Hypotheses -- h20260924_01_etf_dip_reversion

## Hypothesis

Short-term index-ETF dip reversion -- Internal Bar Strength (IBS) and the
Connors/turtle RSI(2) and 3-day high/low family -- is the only US-equity
family inside github.com/fmzquant/strategies with both a published mechanism
(intraday overreaction corrected the next day: Pagonidis 2014, building on
Lehmann 1990 and Kloßner, Becker & Friedmann 2012) and a multi-year
post-publication public record (Pagonidis's sample ends 2013-05; Connors &
Alvarez's book is from 2009; our data window is entirely post-publication).
If we run the six published rules -- D1 IBS-Algotradekit, D2 IBS-Pagonidis
raw, D3 Connors R3, D4 Connors RSI(2) classic, D5 Connors 3-Day High/Low, D6
IBS-filtered RSI(2) -- on QQQ and SPY signals, executed on the 1x ETF and the
matching 3x ETF (TQQQ/UPRO), at least one of the 24 candidates clears this
repo's frozen recent-window G1-G5 gates and a stricter, trade-level
research-admission rule once a realistic T1 market-on-close fill (built from
a 15:50 ET minute-bar proxy) replaces the unexecutable same-close fill one
Pine source (D5) explicitly backtests at.

## Failure mode

The most likely failure mode, informed by the one directly comparable local
result (dir:giants_sweep_published_etf_rules, refuted: 0/24 published ETF
rules cleared the same G1-G5 bar, closest cell anchor Sharpe 1.37 still
failing G1's 50% CAGR / -35% drawdown bar), is that these rules trade too
rarely and too small per trade to produce the CAGR the G1 gate demands on a
1x underlying, and that the 3x execution variant inherits enough of the
underlying's volatility/drawdown to fail G1's drawdown leg even if its CAGR
clears the bar. A second failure mode is specific to realistic timing: a
rule's published or literally-read backtest convention (D5's same-close
fill; D1's prior-bar IBS with a next-open fill, which -- read completely
literally -- adds a full extra session of latency) may be carrying most of
the apparent edge, so that T1's real market-on-close fill erases it (the
research-admission rule's "T1 keeps >=60% of T0's gross mean per trade"
criterion is the direct test for this). A third failure mode is that the
random-entry-timing placebo, matched to the same trade count and holding-
period distribution and restricted to trend-filter-passing days, shows the
apparent edge is just "index ETFs drift up and mean-reversion entries are a
biased sample of an up-trending instrument," not a real timing edge.

## Measurement

Primary: G1-G5 (unchanged thresholds from scripts/run_giants_sweep.py) on
the anchor, select and holdout windows, at 10 bp primary and 20 bp stress
cost, for all 24 candidates at T1. Trade-level research admission (1x T1
cells only): mean net return per trade > 0 in both select and holdout;
trade-level t-statistic >= 2.0 over select+holdout; real mean-per-trade >=
the 95th percentile of the random-entry-timing placebo (60 seeds, matched to
trade count and holding-period distribution, sampled only from trend-filter-
passing days) over select+holdout; T1 keeps >= 60% of T0's gross mean per
trade. Deflated Sharpe of the best of the 24 trials is reported alongside
the raw Sharpe. T0 (same-close, unexecutable upper bound) and T2 (next-open)
are computed for every cell as diagnostics, never as admitted candidates.
A supplementary 2016-2026 per-calendar-year persistence table (daily T0/T2
only, QQQ/SPY/IWM/DIA, 10 bp) is reported as context, not as an admission
criterion.

## Stop/Pivot criterion

Stop (refute) a candidate if it fails any of G1-G5, or -- for the 12 1x T1
cells -- fails the trade-level research-admission rule. Stop the whole
direction if none of the 24 candidates passes both G1-G5 and (where
applicable) research admission; reopening requires a new published rule, a
new disclosed data source, or new evidence of a mechanism/regime shift, not
re-tuning the frozen IBS/RSI/EMA/SMA thresholds, windows, or costs. Pivot:
if the 1x cells fail primarily on G1's CAGR bar but pass G2 (holdout Sharpe)
and the trade-level research-admission rule, report that as a genuine but
sub-G1 edge (position-sizing/leverage question, not a signal question) and
route it to a follow-on sizing iteration rather than re-running this same
signal search with widened thresholds. Continue: if at least one T1 cell
passes G1-G5 and research admission, it becomes a paper-readiness candidate
subject to the usual execution-reality and paper-auto-safety review, not an
automatic promotion.
