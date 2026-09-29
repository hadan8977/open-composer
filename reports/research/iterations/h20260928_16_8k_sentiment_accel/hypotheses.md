# Hypotheses: h20260928_16_8k_sentiment_accel

## H1: 8-K + news sentiment-acceleration carries next-5-day cross-sectional information

- Hypothesis: `score_i,t = -1*(cs_rank(short_ma_5(polarity*magnitude) - long_ma_20(polarity*magnitude)) - 0.5)`,
  computed per ticker per day from DeepSeek-scored 8-K text + news items (visible_at <= t only),
  has a stable-signed daily cross-sectional rank IC against forward 5-trading-day returns over
  2026 Q2, on the universe of tickers with an 8-K filing that quarter.
- Source support: LLM_Alpha repo (github.com/quangkhaidataka/LLM_Alpha), OOS Sharpe +0.78 net of 5bp,
  2022-2024, S&P-100 PIT universe (see external-brief.json).
- Failure mode: IC sign flips across weeks/days (no stable cross-sectional information), or a
  shuffled-news-within-date placebo reproduces the same IC magnitude and sign (the feature is not
  distinguishing real news content from noise).
- Measurement: mean daily rank IC, t-stat, fraction of positive-IC days, real vs placebo, both sign
  conventions (accel and its negation).
- Stop/Pivot criterion: per direction-review.json `stop_condition` -- stop before any CV harness if
  IC sign is unstable (<60% of days share the mean's sign) or placebo reproduces >=50% of the real
  IC's magnitude with the same sign.
