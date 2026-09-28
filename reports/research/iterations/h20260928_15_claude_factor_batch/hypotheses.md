# Hypotheses: h20260928_15_claude_factor_batch

T-20260928-15: does an LLM (Claude) that proposes hypotheses, writes formulaic
cross-sectional factor code, and revises once from SELECT-window IC feedback
beat the existing Alpha101/Alpha191/OSAP-price/rank-card factor zoo on our own
broad U.S. equity data. Round 1 below is written once, before any IC is
computed; Round 2 (up to 4 factors) is added after SELECT-only feedback,
before the TEST window is ever computed, with the same fields.

## H1 -- F01 insider_short_confluence

- Hypothesis: Insider net buying (insider_broad.net_buy_usd_60d) confirmed by
  a fall in short interest (short_interest.dtc_change_vs_prior negative, i.e.
  short covering) is a stronger bullish signal than either alone, because two
  independently-informed trader groups (Cohen/Malloy/Pomorski 2012 on
  opportunistic insiders; Christophe/Ferri/Hsieh 2010 on informed short
  sellers) are converging on the same direction. Formula:
  `0.5*pctrank(net_buy_usd_60d) + 0.5*pctrank(-dtc_change_vs_prior)`,
  cross-sectional percentile ranks per trade_date. Sign +1. Confidence 0.50.
- Failure mode: the two components are simply noisy and uncorrelated with
  forward returns; SELECT-window rank IC near zero or unstable in sign across
  years.
- Measurement: 21d (primary) and 5d (secondary) rank IC, SELECT window
  2016-06-01..2023-12-29 (short_interest coverage begins 2018-01-11, so this
  factor's SELECT sample is 2018-2023, not the full window -- disclosed).
- Stop/Pivot criterion: dropped from the batch's SELECT-chosen candidate if
  |SELECT rank ICIR| is not among the top of the 8; not revised mid-round.

## H2 -- F02 opportunistic_insider_signal

- Hypothesis: The opportunistic-minus-routine insider buy count
  (insider_broad.opportunistic_buy_60d - routine_buy_60d, cross-sectionally
  ranked) isolates Cohen/Malloy/Pomorski's (2012) informative component,
  which the project's existing insider_cluster_buy card (simple buyer
  count>=2 event rule) does not isolate -- the "new element" versus the
  refuted-as-standalone insider-cluster mechanism. Formula:
  `pctrank(opportunistic_buy_60d) - pctrank(routine_buy_60d)`. Sign +1.
  Confidence 0.60.
- Failure mode: routine and opportunistic buys are not cleanly separated by
  our own classification logic, or the distinction adds no incremental IC
  over raw net_buy_usd_60d.
- Measurement: 21d/5d rank IC, SELECT window (full 2016+ coverage).
- Stop/Pivot criterion: same as H1.

## H3 -- F03 trading_activity_surge

- Hypothesis: A recent surge in trade count relative to its own baseline
  (daily_broad.trade_count_5d_mean / trade_count_21d_mean) predicts one-month
  continuation, per Gervais/Kaniel/Mingelgrin's (2001) high-volume return
  premium (visibility/investor-recognition channel) and consistent with
  Chordia/Subrahmanyam/Anshuman (2001) on trading-activity dynamics. This is
  a genuinely new construction (trade COUNT ratio, not $ volume level which
  is already a control, and not the refuted overnight/intraday return
  decomposition). Sign +1. Confidence 0.50.
- Failure mode: trade-count surges mostly reflect algorithmic
  microstructure noise post-2010, not investor-recognition shocks, so the
  premium does not replicate on this universe/period.
- Measurement: 21d/5d rank IC, SELECT window (full 2016+ coverage).
- Stop/Pivot criterion: same as H1.

## H4 -- F04 sue_short_confirmation

- Hypothesis: A positive standardized unexpected earnings (sec_fundamentals_
  daily.sue_eps) that is NOT accompanied by elevated short-volume pressure
  (short_volume_broad.short_volume_ratio_zscore_21) is a stronger drift
  signal than SUE alone, since informed short sellers not opposing the good
  news confirms rather than contradicts it (Diether/Lee/Werner 2009). This
  differs from the already-refuted T-14 mechanism (SUE re-dated to the 8-K
  acceptance timestamp) -- no redating here, SUE stays at its existing
  sec_fundamentals_daily visibility date; the new element is the
  short-volume confirmation gate. Formula:
  `pctrank(sue_eps) - pctrank(short_volume_ratio_zscore_21)`. Sign +1.
  Confidence 0.50.
- Failure mode: short-volume-ratio has no incremental information over SUE
  alone on this universe, or the interaction cancels out the (already weak,
  per sue_eps_rank_recent card) standalone SUE signal.
- Measurement: 21d/5d rank IC, SELECT window (short_volume_broad coverage
  begins 2018-08-03, so 2018-2023 sample -- disclosed).
- Stop/Pivot criterion: same as H1.

## H5 -- F05 quality_liquidity_trend

- Hypothesis: Profitable firms (sec_fundamentals_daily.gross_profitability,
  Novy-Marx 2013, already a locally-tested standalone factor) whose intraday
  illiquidity is recently improving (daily_broad.amihud_intraday_5d_mean /
  amihud_intraday_21d_mean falling) are being "discovered" by the market,
  predicting continued outperformance (investor-recognition/liquidity-
  discovery channel, Merton 1987; Amihud 2002). Formula:
  `0.5*pctrank(gross_profitability) + 0.5*pctrank(-(amihud_intraday_5d_mean/amihud_intraday_21d_mean))`.
  Sign +1. Confidence 0.40 (the interaction itself is exploratory; each
  ingredient is separately well-grounded but their combination is not a
  literature result we found).
- Failure mode: the liquidity-trend component is dominated by mean-reverting
  noise (illiquidity ratios are mechanically mean-reverting), swamping any
  quality signal.
- Measurement: 21d/5d rank IC, SELECT window (full 2016+ coverage).
- Stop/Pivot criterion: same as H1.

## H6 -- F06 momentum_short_confirmation

- Hypothesis: 12-1 month momentum winners (daily_broad.momentum_252_21, an
  existing control) with LOW relative short-volume pressure (few informed
  bears opposing the trend) have more durable momentum than winners with
  high short pressure (Diether/Lee/Werner 2009; Christophe/Ferri/Hsieh
  2010). Formula: `pctrank(momentum_252_21) - pctrank(short_volume_ratio_
  zscore_21)`. Sign +1. Confidence 0.50.
- Failure mode: the interaction is dominated by the momentum component alone
  (i.e. no incremental value over the existing momentum_12_1 card), which
  the max-rank-corr-with-controls info-only check will reveal directly.
- Measurement: 21d/5d rank IC, SELECT window (short_volume_broad coverage
  2018-2023 -- disclosed).
- Stop/Pivot criterion: same as H1.

## H7 -- F07 accruals_cashflow_confirmation

- Hypothesis: Low accruals (Sloan 1996, already a locally-tested standalone
  factor) confirmed by a high cash-conversion ratio (sec_fundamentals_daily.
  operating_cash_flow / abs(net_income)) identifies higher-quality earnings
  than accruals alone. Formula: `0.5*pctrank(-accruals) +
  0.5*pctrank(operating_cash_flow/abs(net_income))`. Sign +1. Confidence
  0.55.
- Failure mode: dividing by abs(net_income) creates extreme outliers when
  net_income is near zero, swamping the signal; winsorization/clipping is
  applied in the builder and this is disclosed as a design choice, not
  discovered after seeing results.
- Measurement: 21d/5d rank IC, SELECT window (full 2016+ coverage).
- Stop/Pivot criterion: same as H1.

## H8 -- F08 earnings_recency_gated_insider_buying

- Hypothesis: Insider net buying (insider_broad.net_buy_usd_60d) that occurs
  within 10 trading days after a fundamentals report (sec_fundamentals_
  daily.days_since_report<=10) is a stronger signal than unconditional
  insider buying, since insiders have just seen the full near-term earnings
  picture (Ke/Huddart/Petroni 2003 -- disclosed as a one-sided extrapolation
  from that paper's own tested direction, which is pre-decline SELLING, not
  post-report BUYING). Formula: `net_buy_usd_60d` where
  `days_since_report<=10`, else NaN. Sign +1. Confidence 0.50.
- Failure mode: the recency gate simply shrinks the sample without adding
  informativeness (i.e. no better than unconditional net_buy_usd_60d, which
  the max-rank-corr-with-controls check will also reveal).
- Measurement: 21d/5d rank IC, SELECT window (full 2016+ coverage).
- Stop/Pivot criterion: same as H1.

## Round 2 (4 factors, preregistered from Round-1 SELECT feedback only)

Round-1 SELECT 21d rank ICIR (full window, sign not yet applied): F01 -0.145,
F02 0.015, F03 0.129, F04 0.002, F05 0.164, F06 0.019, F07 0.149, F08 -0.215
(source: `select-results.json`, generated before any TEST number existed).
The strongest signals (by |ICIR|) are F08, F05, F07, F01, F03; the weakest are
F02, F04, F06. No Round-1 formula is edited; Round 2 adds four new formulas
motivated by this ranking.

## H9 -- F09 insider_short_confluence_dollar_weighted

- Hypothesis: F01's 0.5/0.5 blend (SELECT ICIR -0.145) underperformed F08's
  single dollar-value insider ingredient (-0.215) by a wide margin, so
  up-weighting F01's dollar-buy component (net_buy_usd_60d, weight 0.7) over
  its short-covering component (dtc_change_vs_prior, weight 0.3) tests
  whether F01's signal is mostly carried by the dollar-buy ingredient. Same
  sources as F01 (Cohen/Malloy/Pomorski 2012; Christophe/Ferri/Hsieh 2010).
  Formula: `0.7*pctrank(net_buy_usd_60d) + 0.3*pctrank(-dtc_change_vs_prior)`.
  Sign +1 (this round's hypothesis; the runner fixes the actually-used sign
  from SELECT independently, as it did for F01). Confidence 0.50.
- Failure mode: the reweighting makes no material difference to SELECT ICIR
  versus F01 (i.e. F01's short-covering ingredient was already near-irrelevant
  either way, so this is not a genuinely new test).
- Measurement: 21d/5d rank IC, SELECT window (short_interest coverage begins
  2018-01-11, same 2018-2023 sample as F01 -- disclosed).
- Stop/Pivot criterion: dropped from the batch's SELECT-chosen candidate if
  |SELECT rank ICIR| is not among the top of the 12; not revised mid-round.

## H10 -- F10 quality_composite_roe_profitability_accruals

- Hypothesis: F05 and F07 (quality diluted by a second, weaker ingredient --
  a liquidity trend and a cash-conversion ratio respectively) scored 0.164
  and 0.149 SELECT ICIR, close to this project's own strongest local cards
  (card_roe 0.233, card_gross_profitability 0.209, per prior registry runs).
  A plain three-way quality composite (ROE, gross profitability, low
  accruals; Novy-Marx 2013, Sloan 1996), equal-weighted and undiluted by a
  second theme, tests whether removing the diluting ingredient recovers more
  of the local cards' own strength. Formula: `(pctrank(roe) +
  pctrank(gross_profitability) + pctrank(-accruals)) / 3.0`. Sign +1.
  Confidence 0.55.
- Failure mode: this factor is simply a near-duplicate of card_roe /
  card_gross_profitability with no incremental value (the max-rank-corr-
  vs-zoo-cards info-only check will reveal this directly if so).
- Measurement: 21d/5d rank IC, SELECT window (full 2016+ coverage, subject to
  fundamentals quarterly sparsity).
- Stop/Pivot criterion: same as H9.

## H11 -- F11 momentum_activity_surge_confirmation

- Hypothesis: F06's short_volume_broad confirmation gate was the batch's
  weakest revision candidate (SELECT ICIR 0.019, and restricted to the
  2018-08+ sample); replacing it with F03's trading-activity-surge ratio
  (0.129, built from daily_broad only, full 2016+ coverage) tests whether the
  confirmation mechanism itself -- not specifically short-volume -- adds to
  plain 12-1 momentum, while also recovering the 2016-2018 SELECT coverage
  F06 lacked. Source: same momentum literature as F06 (Diether/Lee/Werner
  2009) plus Gervais/Kaniel/Mingelgrin (2001) for the activity-surge
  ingredient (F03's own source). Formula: `0.5*pctrank(momentum_252_21) +
  0.5*pctrank(trade_count_5d_mean/trade_count_21d_mean)`. Sign +1.
  Confidence 0.50.
- Failure mode: the interaction is dominated by the momentum component alone
  with no incremental value over the existing momentum_12_1 control, which
  the max-rank-corr-with-controls info-only check will reveal directly.
- Measurement: 21d/5d rank IC, SELECT window (full 2016+ coverage).
- Stop/Pivot criterion: same as H9.

## H12 -- F12 post_earnings_insider_buying_bad_news_gate

- Hypothesis: F08 was the batch's strongest Round-1 SELECT signal (|ICIR|
  0.215) but sign-flipped from its original hypothesis -- post-report insider
  buying predicted LOWER, not higher, future returns. Rather than silently
  flipping the sign on the same unconditional construction, this factor
  tests a sharper, directly-motivated re-hypothesis: restrict the post-report
  buying window to NEGATIVE earnings surprises only (sue_eps<0), i.e. a
  "catching a falling knife" / "insiders defending the stock" pattern, to see
  whether the negative relationship concentrates in bad-news buying rather
  than being a generic gate artifact. Source: Ke/Huddart/Petroni (2003),
  unchanged. Formula: `net_buy_usd_60d` where `days_since_report<=10 AND
  sue_eps<0`, else NaN. Sign +1 (deliberately left open to the SELECT-window
  fix rather than presumed, since even the bad-news subset could go either
  way). Confidence 0.45 (below F08's 0.50: this is a post-hoc-motivated,
  narrower re-hypothesis, not an independently pre-existing literature claim
  about the bad-news subset specifically -- disclosed, not hidden).
- Failure mode: the negative-SUE restriction merely shrinks the sample
  without changing its sign or informativeness relative to F08's
  unconditional construction.
- Measurement: 21d/5d rank IC, SELECT window (full 2016+ coverage, further
  restricted by the negative-SUE-and-recent-report double gate).
- Stop/Pivot criterion: same as H9.
