
Which of the 191 GTJA alphas still work in 2026? | Vibe-Trading Research Lab
Vibe-Trading
中文
Star
--
RESEARCH LAB · ALPHA ZOO · OUT-OF-SAMPLE STUDY
Which of the 191 GTJA alphas still work in 2026?
In 2014, Guotai Junan Securities published a research report cataloguing 191 short-horizon
        alpha factors for the Chinese A-share market. Twelve years later, with T+1 settlement still in place,
        sector rotation regimes flipped twice, and retail flow at a multi-decade peak — how many of those
        formulas still produce reliable signal? We benchmarked all 191 on CSI 300, 2018–2025, and the
        answer turns out to be more interesting than a single number.
Revised 2026-09-29.
 The first version of this post (2026-05-17) ran on Tushare prices that were not adjusted for splits and dividends — a return across an ex-date read the mechanical price gap, always downward — and applied today's CSI 300 roster to the whole window. Both were fixed on 2026-08-04, and since 2026-09 an alpha emits no value on a bar where one of its inputs is missing, instead of a signal built on it. That version reported 10 alive, 15 reversed and 165 dead; every number below comes from a re-run on the current code.
TL;DR
Of the 191 short-horizon alphas published by GTJA in 2014, only 8 (4%) still pass our
        alive filter — positive mean IC above 0.02, t-stat above 2, and at least 55% of days with
        positive IC — on CSI 300 over 2018–2025. A further 14 (7%) have 
reversed sign
        with statistical significance and now act as contrarian signals. Another 168 (88%) no longer clear
        the significance filter in either direction, and one (
gtja191_138
) could not be tested
        at all: 99% of its output is NaN. Half of the 8 survivors carry the microstructure /
        shape-of-the-bar tag, the best survival rate of any theme, rather than the raw volume-price
        interaction family we expected. Exact counts below; the methodology is deliberately conservative
        and the caveats are non-trivial.
Alive
8
of 191 alphas
Reversed
14
of 191 alphas
Dead
168
of 191 alphas
Numbers below are from a bench run on 2026-09-29 (Vibe-Trading 0.1.16: CSI 300 with point-in-time membership and split-adjusted prices, 2018–2025) — reproducible via the CLI snippet at the end of the post.
Background
The 2014 Guotai Junan research report — titled "191 个短周期交易型 alpha 因子"
        (
191 Short-Period Transactional Alpha Factors
) — landed at a particular moment in
        Chinese quant. The market had just emerged from a multi-year sideways grind, retail participation
        was climbing back, and the "formulaic alpha" template would be popularised internationally a
        year later by Kakushadze's 2015 arXiv preprint, 
101 Formulaic Alphas
. The GTJA team produced what is,
        in retrospect, one of the most systematic public catalogues of short-horizon factors ever published
        for the A-share universe: 191 numbered formulas, each a few lines of operator algebra over daily
        OHLCV plus turnover.
The formulas in that report read like first-principle hypotheses about market microstructure
        translated into pandas-friendly arithmetic. Some are obvious in hindsight (rank-based reversal over
        five days; correlation between volume and close); others are exotic (the report's
SUMIF
 / 
FILTER
 / 
REGBETA
        compositions reach four or five operators deep). They are, in the language of modern quant, a
library of priors
: each one encodes someone's belief about which microstructure regularity
        is exploitable on a 1–5 day horizon.
The reason this matters in 2026 is simple: short-horizon alphas decay faster than any other
        category. A long-horizon value or quality factor can plausibly survive a decade with no
        adjustment; a 1–5 day formula built on volume-price interactions probably cannot. Twelve
        years out-of-sample is, in factor-research terms, a near-eternity. The A-share market itself has
        changed: T+1 settlement remains, but the institutional/retail mix has flipped, the STAR Board and
        ChiNext registration-system reform have re-priced small-cap risk, and high-frequency-flavoured
        execution by mutual funds has compressed many obvious mean-reversion windows.
So we ran the test: method first, then the numbers.
Method
The test is deliberately a 
cross-sectional information-coefficient (IC) study
, not a
        full backtest. The goal is to ask: 
does this alpha rank stocks in a way that correlates with
        next-day return, on average, robustly across the window?
 A higher-fidelity strategy backtest
        (with t-cost, position limits, sector neutralisation, decay-multiplied portfolios) is a separate
        question and is out of scope for this post.
Universe
CSI 300: the 300 most liquid A-shares, rebalanced semi-annually by the index provider. Each
        day's cross-section is the index membership in force on that day, from Tushare's month-end
        rosters, so a stock counts only while it is in the index — 348 names were members at some
        point in the window. Prices are forward-adjusted for splits and dividends.
Period
2018-01-02 through 2025-12-31. Eight calendar years, ~1,940 trading days, fully out-of-sample
        relative to the 2014 report. The window deliberately spans 2018's bear market, the 2020–2021
        liquidity-driven rally, the 2022 drawdown, and the 2024–2025 sideways regime — so the
        average IC is regime-averaged, not regime-cherry-picked.
Signal definition
For each alpha and each trading day 
t
, we compute the alpha value for every stock in
        the universe, then cross-sectionally rank-transform it to 
[0, 1]
.
        Forward return is the 1-day simple return from close 
t
 to close 
t+1
, also
        cross-sectionally rank-transformed. The Spearman IC for day 
t
 is the Pearson correlation
        of the two ranked series. We report the mean IC across all valid days, the t-statistic of the IC
        series, and the fraction of days with positive IC.
Categorisation
Alive.
 Mean IC > 0.02, t-stat(IC) > 2, and ≥ 55% of days with
          IC > 0. All three conditions must hold.
Reversed.
 Mean IC < −0.02 and t-stat(IC) < −2 (sign-flipped
          version of the above). The original report intended the alpha to predict with one sign; we
          observe it predicting with the opposite sign at statistical significance.
Dead.
 Everything else that could be computed: |mean IC| ≤ 0.02, or
          |t-stat| ≤ 2, or a positive IC on fewer than 55% of days. An alpha whose output is more than
          95% NaN is not tested at all and is reported separately.
Caveats baked into the method
Three deliberate choices that constrain how the results should be interpreted:
The IC is 
1-day forward
, no decay smoothing. Decay-3 or decay-5 IC (the original
          report's preferred horizon) will produce slightly different numbers; we'll publish those as a
          follow-up.
No t-cost adjustment. A high-IC alpha with daily-rebalance turnover near 100% is, in
          practice, unprofitable after a realistic 5–10 bps round-trip. The bench does not
          measure turnover, and the survival classification here ignores it.
No sector neutralisation. None of the GTJA 191 formulas needs sector tags, so every IC here
          is measured on the raw cross-section.
Tool used
$ vibe-trading alpha bench --zoo gtja191 --universe csi300 \
                            --period 2018-2025 --top 20
One command. It writes an HTML report to 
~/.vibe-trading/reports/
 with the top
        alphas by IR (mean IC, IC standard deviation, IR, share of positive-IC days, number of days) and
        the alphas it could not compute. Reproducibility recipe at the end of the post.
Findings
Aggregate survival
The headline counts again:
Alive
8
survive all three filters
Reversed
14
now predict with opposite sign
Dead
168
below significance threshold
What surprised us is not the dead count — everyone expects decay — but the
reversed
 count. A meaningful slice of alphas that worked in 2014 now act as contrarian
        indicators with statistically significant magnitude. The simplest reading is that a behavioural
        anomaly the formula was capturing (small-cap mean reversion, end-of-day flow from retail) has been
        crowded out by precisely the kind of systematic trading the formula represents, and what remains
        is the opposite trade.
Theme breakdown
Each alpha carries one or two theme tags in its registry metadata — the operator
        vocabulary it leans on most heavily. An alpha with two tags counts in both rows, so the counts add
        up to more than 190. Numbers below are survival rates within each theme:
Theme
Definition
Count
Survival rate
Volume-price interaction
Correlation / covariance of volume with close, high-low range
81
4% (3/81)
Short-horizon volatility
Rolling std / range over 5-20 day windows
26
8% (2/26)
Reversal
Negative-sign return signals over 1-5 day horizons
38
8% (3/38)
Momentum
Positive-sign return signals over 10-60 day horizons
63
0% (0/63)
Turnover / liquidity
Volume ratios, turnover-rate transforms
2
0% (0/2)
Microstructure / range
Open-close-high-low decompositions, intraday range proxies
18
22% (4/18)
Sentiment
Share of up days on days the market fell (one alpha, 
gtja191_075
, on a proxy benchmark)
1
0% (0/1)
The read from the re-run: 
microstructure / range
 alphas are the standout survivors
        (22%, 4 of 18). 
Reversal
 and 
short-horizon volatility
 follow at 8% (3 of 38 and
        2 of 26), raw 
volume-price interaction
 at 4% (3 of 81). 
Momentum
 keeps none of
        its 63 — five of them now predict with the opposite sign — and the small
turnover
 bucket keeps none of its 2. The pattern is consistent with what you would expect
        if a decade of systematic capital has compressed the easiest reversal/momentum trades but left
        intact the structural daily-bar geometry alphas that key on shape-of-the-bar effects.
Top 5 surviving alphas
The five alphas with the highest IR (mean IC divided by its standard deviation) across the
        window, in descending order, each with its formula as the registry stores it
        (
__alpha_meta__["formula_latex"]
 of the corresponding Python module).
gtja191_114
((RANK(DELAY(((HIGH-LOW)/(SUM(CLOSE,5)/5)),2)) * RANK(RANK(VOLUME))) / (((HIGH-LOW)/(SUM(CLOSE,5)/5))/(VWAP-CLOSE)))
Mean IC = 0.0606, IR = 0.2926 over the CSI 300 / 2018–2025 window. Formula reproduced verbatim from the registry (
__alpha_meta__["formula_latex"]
 of 
gtja191_114
).
gtja191_171
-1*((l-c)*(o^5))/((c-h)*(c^5))
Mean IC = 0.0435, IR = 0.2299 over the CSI 300 / 2018–2025 window. Formula reproduced verbatim from the registry (
__alpha_meta__["formula_latex"]
 of 
gtja191_171
).
gtja191_120
rank(vwap-close)/rank(vwap+close)
Mean IC = 0.0452, IR = 0.2119 over the CSI 300 / 2018–2025 window. Formula reproduced verbatim from the registry (
__alpha_meta__["formula_latex"]
 of 
gtja191_120
).
gtja191_111
sma(v*((c-l)-(h-c))/(h-l),11,2)-sma(v*((c-l)-(h-c))/(h-l),4,2)
Mean IC = 0.0355, IR = 0.1888 over the CSI 300 / 2018–2025 window. Formula reproduced verbatim from the registry (
__alpha_meta__["formula_latex"]
 of 
gtja191_111
).
gtja191_163
rank(((-1*ret)*mean(v,20))*vwap*(high-close))
Mean IC = 0.0342, IR = 0.1674 over the CSI 300 / 2018–2025 window. Formula reproduced verbatim from the registry (
__alpha_meta__["formula_latex"]
 of 
gtja191_163
).
Three alphas that now point the other way
The three alphas with the most negative mean IC. All three sit in the reversed bucket: they now
        predict, with statistical significance, in the direction opposite to the report's sign.
gtja191_124 (reversed)
(close-vwap)/decay_linear(rank(tsmax(close,30)),2)
Mean IC = -0.0518, IR = -0.2516. The most negative mean IC in the gtja191 zoo on CSI 300 / 2018–2025.
gtja191_178 (reversed)
(c-delay(c,1))/delay(c,1)*v
Mean IC = -0.0329, IR = -0.1644. The second most negative.
gtja191_137 (reversed)
16*((c-dc1+(c-o)/2+dc1-do1)/MAX_term) * MAX(abs(h-dc1), abs(l-dc1))
Mean IC = -0.0300, IR = -0.1464. The third most negative. 
MAX_term
 is the report's three-way piecewise denominator, built from |h − dc1|, |l − dc1|, |h − dl1| and |dc1 − do1| (dc1, do1, dl1: the previous day's close, open and low); the module carries the full definition.
One paragraph of reflection
The temptation, after a survival study like this, is to over-generalise: "decay is inevitable;
        formulaic alphas are dead." We don't think that's the right read. What this exercise teaches is
        narrower and more useful: a small part of a 12-year-old short-horizon catalogue — 8 of 190
        — still produces signal; the survivors cluster in an interpretable theme (bar geometry:
        open-close-high-low decompositions), and the losers cluster in equally interpretable ones
        (momentum, where nothing survives and five alphas flipped sign, and simple turnover transforms).
        It tells us very little about whether the Kakushadze 101 formulas, or the Qlib 158 feature set,
        will decay at the same rate — those zoos have different operator vocabularies and different
        intended universes (US equities, multi-horizon respectively). Future work, separate bench runs.
Caveats
A few constraints on how these results should be read. Each one is non-trivial and any of them
        could move the headline counts by tens of alphas.
1-day IC is not profitability
The whole study is at the IC level, not at the strategy-PnL level. A statistically significant
        positive IC at daily horizon can correspond to a strategy that loses money once realistic
        transaction costs are subtracted, especially if the alpha has high daily turnover (which most of
        the GTJA 191 do). Treat this post as a 
signal-quality scan
, not a profitability claim.
        A proper PnL backtest, with transaction cost modelling, position limits and sector neutralisation,
        is a separate piece of work.
CSI 300 only
We benchmarked on the 300 most liquid A-shares. Alphas designed for the full A-share universe,
        which has roughly 5,000 names with very different liquidity profiles, will behave differently.
        In particular, small-cap mean-reversion alphas tend to look worse on CSI 300 than on the full
        universe (because CSI 300 is institutional-flow-dominated and short-horizon retail reversion is
        muted), and some "dead" alphas here might revive on a CSI 1000 cut.
Tushare data scope
Our data feed is Tushare end-of-day OHLCV and traded amount, forward-adjusted for splits and
        dividends, with VWAP derived from amount; it has no intraday tick or order-book data. Five GTJA 191
        formulas reference an input the panel does not carry — the benchmark index close
        (
gtja191_075
, 
_149
, 
_181
, 
_182
) or a
        multi-factor regression residual (
gtja191_030
) — and use a proxy instead: the
        cross-sectional mean close, or a weighted average of squared daily returns, as each alpha's notes
        say. Treat those five as 
not properly tested
 here, not as "dead".
8-year window is short
By academic standards an 8-year window is on the short side. The classic Fama-French papers
        use 30–90 year windows. Some of the alphas we label "dead" may revive on a longer or
        differently-positioned sample — for example, if the 2026–2030 regime returns to a
        more retail-dominated mix, mean-reversion alphas could recover. The label is "dead in this
        window", not "dead forever".
Survivorship bias in the universe
The first version of this post applied the latest CSI 300 roster to the whole 2018–2025
        window, so every name was present because it survived to the end — a hindsight-selected set,
        which biases IC upward. The re-run masks each day's cross-section to the roster in force that day
        (348 names were members at some point in the window). The 
sp500
 universe still uses
        today's constituent list, so the same caveat applies to any cross-zoo comparison run on it —
        its bench report says so — and a low alive count there should be read as "decay plus
        survivorship", not as a clean failure of the alpha family.
190 formulas, one test each
Testing 190 formulas on the same window makes some look good by chance. The bench reports how
        large the best IR would be expected to be if none of them carried any signal: 0.204 here. The best
        observed IR, 0.293 (
gtja191_114
), survives that deflation (probability 0.9999). Two
        more alive alphas are above 0.204 — 
gtja191_171
 (0.230) and
gtja191_120
 (0.212); the other five, with IRs between 0.130 and 0.189, are below it,
        so read them as candidates rather than confirmed signals.
No regime conditioning
We average IC over the full 2018–2025 window. Many of these alphas are almost certainly
        regime-dependent — they work in trending markets but fail in choppy markets, or vice versa.
        A follow-up post will slice the survival counts by regime (bull / bear / sideways, as defined by
        20-day index momentum) but the aggregate numbers in this post are regime-averaged. A regime-aware
        deployment might keep half the dead alphas as conditional signals.
Reproduce it yourself
The whole bench is one CLI command on top of an open-source install. The full source is on
        GitHub under the HKUDS organisation; the package is on PyPI as
vibe-trading-ai
.
pip install vibe-trading-ai
export TUSHARE_TOKEN=your_token_here
vibe-trading alpha bench --zoo gtja191 \
                         --universe csi300 \
                         --period 2018-2025 \
                         --top 20
You get back an HTML report saved to 
~/.vibe-trading/reports/
 with the top alphas
        by IR and the alphas that could not be computed. The same command works against
--zoo alpha101
 (Kakushadze 101 Formulaic Alphas, paper-faithful rewrite of the 2015
        arXiv preprint) and 
--zoo qlib158
 (the Microsoft Qlib feature library, used under
        Apache-2.0 with attribution). Cross-zoo comparison runs via 
alpha compare
.
View source on GitHub
Browse the alpha library
Read the docs
If you find an alpha whose survival classification surprises you — especially a survivor
        we did not flag in the top 5, or a reversed one you expected to survive — please
        open an issue with the alpha id and your reasoning. Community pull requests adding new zoos, new
        universes (CSI 1000, NASDAQ 100, crypto majors) or new validation tooling are welcome under the
CONTRIBUTING.md
        DCO process.
Source citation: Guotai Junan Securities, 
"191 个短周期交易型 alpha 因子"
        (191 Short-Period Transactional Alpha Factors), 2014. Re-implementation
agent/src/factors/zoo/gtja191/
 uses only the formula content from the report; the
        report's narrative prose, in-sample tables and figures are not reproduced. See the directory's
LICENSE.md
 for the full provenance note.

