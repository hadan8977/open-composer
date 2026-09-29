# Hypotheses: h20260929_20_news_nonews_drop_reversal

Sources: Chan (2003, JFE), Savor (2012, JFE), Dyl/Yuksel/Zaynutdinova (2019, JBR) --
see `direction-review.json` and `external-brief.json` for full source cards.

## H1 -- No-news drop reversal (long)

- Hypothesis: a stock in the top-1500 PIT-ADV universe with a market-adjusted
  (vs. SPY, close-to-close) one-day drop of at least D in {5%, 8%}, with NO
  identifiable public news or earnings/8-K filing that session, tends to
  reverse (positive average return) over the next h in {1, 3, 5} trading
  sessions when bought at the next session's open -- an overreaction to a
  price move with no fundamental trigger (Chan 2003; Savor 2012; corroborated
  through 2015 by Dyl/Yuksel/Zaynutdinova 2019).
- Failure mode: the observed "no-news" drops are dominated by illiquid,
  low-quality names where the apparent reversal is a bid-ask bounce / stale
  price artifact rather than a real overreaction, and does not survive
  ADV-tiered transaction costs; or the effect has decayed to economic
  insignificance in the far more liquid 2024-2026 market, consistent with
  Dyl/Yuksel/Zaynutdinova's post-decimalization decay finding.
- Measurement: calendar-time portfolio (equal-weight, <=20 concurrent
  positions, <=10% each, remainder in BIL), close-to-close returns with
  next-open fills, TEST window 2024-01-08..2026-09-17 (decisive); hit rate,
  average/median return per trade, trades per year, calendar Sharpe/CAGR/
  max DD, correlation and diversifier edge vs. S3, trade-level edge over the
  shuffled-news-label placebo (t>=2, clustered by date) and the redated-date
  placebo.
- Stop/Pivot criterion: refuted if no D/h cell reaches calendar Sharpe >=1.19
  or S3 combo edge >=+0.05 in TEST at base cost with a trade-level edge over
  the shuffled-label placebo (t>=2) surviving 2x costs; not re-tuned on the
  same universe/window without a genuinely new signal.

## H2 -- News-accompanied drop drift (short)

- Hypothesis: a stock in the top-1000 PIT-ADV tier (easy-to-borrow proxy)
  with the same market-adjusted drop trigger, but WITH an identifiable news
  headline or earnings/8-K filing that session, tends to continue drifting
  down over the next h sessions (Chan 2003's bad-news drift; Savor 2012's
  information-drift result) -- an underreaction to genuine bad news,
  tradable short with a modeled 1%/year borrow fee plus tiered spread cost.
- Failure mode: the drift documented in the source papers operates on a
  multi-month horizon (Chan: up to 12 months), so the brief's 1-5 session
  sub-test may be too short to capture any real drift, or transaction/borrow
  costs on a short book exceed the (likely small, short-horizon) drift.
- Measurement: same calendar-time book construction as H1, short-side
  weights, borrow cost accrued daily on held notional; same TEST window and
  statistics, reported as separate candidates from H1.
- Stop/Pivot criterion: reported alongside H1 using the same statistics;
  does not gate H1's verdict or vice versa, per the brief.
