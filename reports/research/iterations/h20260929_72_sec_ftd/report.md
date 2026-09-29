# h20260929_72_sec_ftd report

Question: do high SEC fails-to-deliver balances (FTDSH = fails / PIT shares outstanding, FTDADV = fails x price / 21-session dollar ADV) rank lower next-open returns in the ADV top-1500 pool (price >= 5), PIT-lagged by the SEC publication schedule, in 2024+ and 2019+?

Result: refuted at the stage-1 IC gate; no book built. Source files: `ic_table.json`, `results.json`, `reports/research/signal-cards/ftd_ftdsh{,_h60}.json`, `ftd_ftdadv{,_h60}.json`, `ftd_dummy_control.json`.

RankIC of -signal (positive = preregistered direction), Newey-West t with lag = horizon:

| signal | horizon | full 2019+ IC (NW t) | 2024+ IC (NW t) |
|---|---|---|---|
| FTDSH | 20d | -0.0022 (-0.69) | 0.0003 (0.05) |
| FTDSH | 60d | 0.0011 (0.19) | 0.0050 (0.51) |
| FTDADV | 20d | 0.0054 (1.39) | 0.0013 (0.25) |
| FTDADV | 60d | 0.0131 (1.74) | 0.0057 (0.63) |
| FTD>0 dummy (control) | 20d | 0.0029 (0.84) | -0.0001 (-0.02) |
| FTD>0 dummy (control) | 60d | 0.0105 (1.59) | 0.0068 (0.81) |

Continue conditions (per signal, at 20d or 60d): 2024+ sign positive (met for all four pairs), 2024+ NW |t| >= 2.5 (not met by any pair, max 0.63), full-sample same sign (fails for FTDSH 20d only). The |t| condition fails everywhere, so the gate fails.

Data: 176 of 186 expected half-month files 2019-01..2026-09 downloaded (10 answered HTTP 404: 2019-10a, 2020-02a..2020-04b, 2026-05a/b, 2026-09b); 175 used. Of 932,390 rows at the files' last settlement dates 37.8% match any SIP symbol, 29.7% the ADV<=3000 / price>=5 universe; of those 26.0% are dropped by the 20% price rule (reverse splits, reused tickers); FTDSH is valid for 66.7% of price-consistent rows (the rest lack cover-page shares), FTDADV for 99.3%. Unmatched rows are mostly ETFs, OTC and foreign tickers.
