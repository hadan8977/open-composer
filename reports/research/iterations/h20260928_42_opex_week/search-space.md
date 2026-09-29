# Search Space: h20260928_42_opex_week

One path, `opex_week_screen`, 20 candidates: 8 primary (4 tickers -- SPY,
QQQ, DIA, IWM -- x 2 exit variants -- WEEK, WEEKMON) plus 12 internal
placebo controls (4 tickers x 3 non-expiration Friday anchors -- 1st, 2nd,
4th). This is the full preregistered grid; no candidate is added, removed
or retuned after seeing a result.

Every candidate is a pure calendar rule computed only from `close.columns`
(ticker presence) and `close.index` (the exchange trading-day calendar) --
no price value is ever read, so there is no look-ahead by construction.
Entry: last known trading day before the Monday of the target Friday's
week, close -> next session open, buy 1.0 the ticker. WEEK/placebo exit:
last known trading day within that same week, close -> next session open,
sell to SHY. WEEKMON exit: first known trading day of the week AFTER the
target week, close -> next session open, sell to SHY. Costs are 10bp
primary / 20bp stress per side, identical to every prior batch-screening
round. Primary candidates are judged against S3's frozen anchor
(2024-01-08..2026-09-17) and stress (2016-05-02..2023-09-15) windows via K1
(own date-neutral Sharpe >= 80% of S3's in both windows) or K2 (a
63-session inverse-vol blend with S3 beats a vol-matched control by
>=0.05 Sharpe in both windows), with DSR reported at n_trials=20 (full
family). Placebo candidates are never eligible for a keep tier; they exist
only to demote a primary candidate whose apparent edge is not specific to
the 3rd Friday.
