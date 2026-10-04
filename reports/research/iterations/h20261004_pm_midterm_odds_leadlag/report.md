# Report: h20261004_pm_midterm_odds_leadlag

Verdict (mechanical, pending lead review): **stop_refuted**.

## Numbers

- Window: 2025-10-08 to 2026-10-02, 248 sessions (0.984 years), 27 assets (dropped: none).
- H-M net: Sharpe -1.201, NW(5) t -1.239, annual return -8.54%, vol 7.11%, mean -3.39 bp/day.
- H-M gross: Sharpe -0.906, NW t -0.940; costs doubled: Sharpe -1.497.
- Circular shifts (1000, seed 20261004): real mean -3.39 bp/day, p95 2.95 bp/day, real at the 16.7th percentile.
- Continue rule: Sharpe >= 0.5 False; NW t >= 2.0 False; above p95 of shifts False; stop (Sharpe <= 0) True.
- Predictive regression, next-session direction-signed return in bp on dP(t) in pp (pooled, Driscoll-Kraay): backtest window beta 4.99 (t 0.91, 247 sessions); full sample beta 3.12 (t 1.32, 307 sessions). The paper reports +13 bp per 1 pp.
- Basket-level NW regression, backtest window: beta 4.99 (t 0.91).
- Day-2 coefficient (backtest window): -10.84 bp per pp (t -1.95). Same-day coefficient (descriptive, not tradable): -0.72 (t -0.14).

## Categories (report only)

- stock_etf: net Sharpe -0.823, NW t -0.846, gross Sharpe -0.623, shift percentile 30.5.
- bond: net Sharpe -1.040, NW t -1.035, gross Sharpe -0.499, shift percentile 31.9.
- bank: net Sharpe -1.572, NW t -1.724, gross Sharpe -1.450, shift percentile 11.3.
- dollar: net Sharpe -0.667, NW t -0.673, gross Sharpe -0.196, shift percentile 51.5.
- connected: net Sharpe -0.195, NW t -0.195, gross Sharpe 0.052, shift percentile 51.4.

## Kalshi signal (robustness, same window)

- Net Sharpe -1.536, NW t -1.718, gross Sharpe -1.182, shift percentile 13.8; correlation with the Polymarket signal 0.62.

## Placebos

- Sign flip: net Sharpe 0.612, gross Sharpe 0.906 (gross should mirror H-M gross -0.906).
- Unrelated Polymarket market (144 valid sessions from 2026-03-10): net Sharpe -0.633, NW t -0.473, shift percentile 6.0.
- Constant-position baseline (direction-signed basket held long): Sharpe 0.675, NW t 0.808.

## Power

- Window 0.984 years. Expected t is 0.99 at a true Sharpe of 1.0 and 1.93 at the paper's 1.95; a Sharpe of 2.02 is needed for t = 2. hypotheses.md said about 1.4 years and expected t 1.2 / 2.3; the realised window is shorter.

## Caveats

- Directions are the paper's Table A.1 and map a Republican-Congress probability to the Trump-win exposure; this is the assumption under test.
- Short legs carry no borrow charge; DJT and PHUN shorts are costed at 10 bp per side only.
- The daily 16:00 ET price is the last hourly CLOB point at or before the cut; thin periods carry the last price (max gap in the data build: see data-feasibility.json).
- Forward shadow to 2026-11-04 is preregistered and runs regardless; the verdict here covers the backtest window only.
