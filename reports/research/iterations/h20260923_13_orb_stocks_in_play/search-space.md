# Search space: h20260923_13_orb_stocks_in_play

One mechanism (individual-stock opening-range breakout filtered by opening relative volume,
"Stocks in Play"), three frozen candidates, written to candidate-manifest.json before any return
is computed. No backtest is run in this pass; this document (and candidate-manifest.json) is what
the next (backtest) step must execute against unchanged.

| axis | values |
|---|---|
| candidate id | SIP01 (long-only, paper's parameters), SIP02 (long-only, stricter liquidity floor), SIP03 (long-short diagnostic, never promotable) |
| opening range | 5 minutes, 09:30:00-09:34:59 ET (fixed, both paper and QuantConnect agree this is the best-performing duration tested) |
| entry | stop order at the opening range's own high (bullish range) or low (bearish range); doji (open==close) -> no order (fixed, paper's exact rule) |
| stop loss | 10% of 14-day ATR from the executed entry price (fixed) |
| profit target | none (fixed -- the paper's individual-stock section describes none; this project's own ETF-proxy script's 10R target does not apply here, a disclosed correction) |
| exit | stop, or end of session (16:00 ET) if not stopped (fixed) |
| price floor | $5 (SIP01, SIP03, paper's value) / $10 (SIP02, stricter) |
| avg volume floor | 1,000,000 sh/day (SIP01, SIP03) / 5,000,000 sh/day (SIP02) |
| ATR floor | $0.50 (SIP01, SIP03) / $1.00 (SIP02) |
| relative volume floor | 100% (SIP01, SIP03) / 150% (SIP02) |
| top-N selection | 20 by relative volume, all three candidates (fixed) |
| direction | long-only (SIP01, SIP02) / long+short (SIP03, diagnostic only) |
| sizing | 1% of equal-split slot capital (equity/20) per trade at the stop, capped at 1/20 portfolio weight (fixed, resolves the paper's own less explicit language via QuantConnect's published formula) |
| leverage cap | 1.0x (SIP01, SIP02 -- house default, disclosed departure from the paper's 4x) / 4.0x (SIP03 -- paper's own value, fidelity check only) |
| cost view | 5, 10, 20 bp per side on notional, all reported; a separate $0.0035/share commission cross-check column (not blended) |
| stop-fill variant | conservative (gap-through fills at bar open; same-bar stop-before-target) and one-bar-late (QuantConnect forum-reported backtest/live discrepancy), both reported |

3 candidates, SIP01/SIP02/SIP03, one path (`orb_stocks_in_play_screen`). No model training, no
mutation, no adaptive expansion. SIP01 and SIP02 are scored independently against the same fixed
adoption rule; neither is picked over the other based on its own result. SIP03 is permanently
excluded from promotion by construction (a diagnostic role, not a result-dependent exclusion).

Controls (preregistered, not candidates, not counted in the 3-candidate budget):

- **RD** (random direction, 10 seeds x {SIP01, SIP02} = 20 runs): the same daily top-20-by-
  relative-volume selection and the same eligibility filters as the real candidate, but the traded
  direction is drawn randomly (+-1) instead of read from the opening candle's own close-vs-open --
  isolates whether the direction call carries information versus just being in an abnormally
  active name that day. Mirrors the already-refuted ETF study's own random-direction control
  (dir:orb_etf_opening_range_breakout), which is exactly the placebo that caught that mechanism's
  failure.
- **RL** (random non-in-play liquid stocks, 10 seeds x {SIP01, SIP02} = 20 runs): the same
  breakout/stop/exit mechanics and the same price/avg-volume/ATR eligibility filters as the real
  candidate, but 20 stocks are drawn at random from the eligible-but-not-actually-top-20 set each
  day instead of ranking by relative volume -- isolates whether the "in play" (abnormal relative
  volume) selection itself carries information versus generic breakout trading on any liquid name.
  This is the one control the already-refuted ETF study could not run (it has no cross-sectional
  selection step to ablate), and is the most direct test of this mechanism's own added ingredient.
- **ETF-ORB known negative** (0 new simulations): `dir:orb_etf_opening_range_breakout`'s already-
  refuted OOS numbers, reused as a reference floor, not recomputed.

Fixed simulation budget for the next (backtest) step: 3 candidate runs (SIP01, SIP02, SIP03) + 40
placebo runs (20 RD + 20 RL) = 43 core simulations across the design and select windows. Cost
(5/10/20bp) and stop-fill variant (conservative/one-bar-late) are reporting dimensions computed
within each run, not separate manifest candidates or additional simulations, following
`scripts/run_h20260918_02_orb_etf.py`'s own load/backtest/report stage split (raw minute bars are
read once per symbol-shard/year into a cached day-record table; every cost/leverage/stop-variant
cell is then pure arithmetic over that cache, no re-read of minute data).

Windows: design 2016-01-04..2022-12-30 (`data/sip-hist/minute`, older years, mechanism sanity-
checking and data-feasibility development -- not a promotion claim on its own). Frozen select
window 2023-09-18..2025-12-31 (`data/sip/minute`), reused unchanged from this project's existing
convention (first established for the daily ETF-rotation family in H-20260918-05; see
`docs/handoff-2026-09-23.zh.md`, `docs/plan-strategy-factory-2026-09-22.zh.md`) -- the only window
that will ever rank a candidate. 2026-01-02..2026-09-17 is reported for continuity only: per
`docs/plan-research-coverage-2026-09-23.zh.md` section 1.6, this window has already been spent by
several other directions this month (including the sibling ETF-ORB study's own OOS window,
2024-01-02..2026-09-17, which overlaps it), so no out-of-sample claim is made on it here.

Adoption rule (design window, all four must hold for a candidate to be considered): (a) beats the
equal-weight-eligible-universe control, (b) beats its own RD placebo median, (c) beats its own RL
placebo median, (d) positive net of 20bp/side plus the commission cross-check. Select window
(frozen, at 10bp): (e) CAGR>=50% and max drawdown>=-35% (gate G1, this project's standing
"exploded and survived" bar), (f) beats >=90% of its own combined RD+RL placebo draws (gate G3,
<=10% placebo win rate). SIP03 is diagnostic only and is never scored against this adoption rule
for promotion purposes, even if its long+short numbers happen to clear it. If neither SIP01 nor
SIP02 passes: "keep refuted."

Where the exact rules were pinned from, and where sources differ: the primary paper (Zarattini,
Barbon & Aziz, SSRN 4729284, first version 2024-02-16) was fetched in full this pass (46KB
extracted text, all sections read) -- every rule in the table above traces to a direct quote in
`reports/harness/source_cards/h20260923_13_orb_stocks_in_play.jsonl` and
`direction-review.json`. Cross-checked against QuantConnect's independent code replication
(`orb_qc`), which agrees on the mechanism's shape (5-minute range, stop-order entry, ATR-based
stop, relative-volume ranking with the identical formula) but differs in two disclosed ways: (1)
QuantConnect substitutes "top 1,000 by dollar volume" for the paper's $1,000,000-share-volume
floor -- this iteration keeps the paper's own share-volume floor for SIP01 and adds a stricter,
independently-chosen floor for SIP02 rather than copying QuantConnect's substitution; (2)
QuantConnect's own published backtest covers only 2016 (the first year of the paper's window) on
that narrower universe, so its ~2.4 Sharpe headline is not treated as multi-year evidence. A
community-reported implementation risk (one-bar-late stop fills in minute-resolution backtests;
Alpaca-specific stop-order rejections as "wash trades") was located in the same QuantConnect page's
own comment thread and is preregistered as a reporting variant and a live-feasibility flag
respectively, not left as an unverified aside.
