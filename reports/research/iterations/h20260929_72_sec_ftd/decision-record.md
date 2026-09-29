# Decision Record: h20260929_72_sec_ftd

## P1 ftd_book_screen

- Path: FTDSH / FTDADV (SEC fails-to-deliver) IC gate on the ADV top-1500 pool (price >= 5), then 4 books only if it passes.
- Decision: stop. Verdict refuted; no books built, no ledger entries evaluated. The short-selling-information cell (alt_data.short_selling, fails-to-deliver) is closed: FTD shows no signal here.
- Reason: the preregistered gate needs, for a signal at 20d or 60d, 2024+ RankIC of -signal positive with Newey-West |t| >= 2.5 and the full-sample IC of the same sign. The 2024+ IC is positive (preregistered direction) for all four (signal, horizon) pairs but tiny, with NW t 0.05 (FTDSH 20d), 0.51 (FTDSH 60d), 0.25 (FTDADV 20d), 0.63 (FTDADV 60d). Full-sample 2019+ IC is -0.0022 (t -0.69), 0.0011, 0.0054 (1.39), 0.0131 (1.74). The FTD>0 dummy control is equally flat (2024+ t -0.02 and 0.81). Numbers: `results.json`, `ic_table.json`, signal cards `ftd_*.json`.
- Caveats: effect sizes in the published papers were not read; the SEC served no file for 10 half-months (windows left NaN); FTDSH lost a third of price-consistent rows to missing cover-page shares (FTDADV covers 99%); the pool is ADV top 1500, price >= 5, so a microcap effect (hard to borrow, per Autore et al.) is outside the test by design.
- Next iteration suggestion: stop. Reopen only with a new mechanism or data, for example threshold-list entries (5 consecutive days above 0.5% of shares) as an event in small caps with real borrow-fee data, or a paid securities-lending feed.
