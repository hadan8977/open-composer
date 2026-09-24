# Report: h20260924_02_momentum_crash_guard
Card `reports/research/hypotheses/H-20260924-02-momentum-crash-guard.md`. Full evidence: `direction-review.json`, `external-brief.md/json`, `candidate-manifest.json`, `search-space.json/md`, `results.json` (machine-readable), `cache/*.parquet` (daily book returns, guard multipliers, per-candidate trial results).
## Step 2a: base T1 book reproduction
Full window (2017-01-04..2026-09-17, 2439 sessions), 20bp, no rf subtraction (matching `signal_card.py`'s own `perf()`):
| metric | reproduced | signal card (T1, h20, 20bp) | diff | within ~1pp |
|---|---:|---:|---:|---|
| CAGR | 26.5% | 26.5% | -0.0% | yes |
| max DD | -50.2% | -50.2% | 0.0% | yes |
Sharpe (no-rf convention): 0.76. **Confirmed within ~1pp on both CAGR and max DD -- not a stop condition.**

Anchor window (2024-01-08..2026-09-16), the window our notes' 59.8%/-41.6% figure refers to:
| cost | CAGR | max DD | Sharpe (excess of BIL) |
|---|---:|---:|---:|
| 10bp | 63.1% | -41.5% | 1.09 |
| 20bp | 62.2% | -41.6% | 1.08 |
| notes claim | 59.8% | -41.6% | -- |
Max DD is confirmed almost exactly (+0.1pp from the notes' -41.6%). CAGR reproduces +3.3pp higher than the notes' "roughly 59.8%" (63.1% at 10bp, 62.2% at 20bp) -- same order of magnitude and same direction, but not a tight match. Because (a) the task's explicit hard-stop condition is tied to the card's own **full-window** numbers (confirmed above, essentially exact) and (b) the drawdown side of the anchor claim -- the actually decision-relevant number for this whole card -- matches to within 0.1pp, this is reported as a disclosed, unresolved minor gap (the notes' CAGR figure was explicitly hedged as "roughly"), not treated as a reproduction failure or a reason to stop.

## Step 2b: development-window thresholds (fit once, never touched again)
| threshold | value | source |
|---|---:|---|
| CG-DM high-vol cutoff | 14.1% annualized | development-window median of SPY's own trailing-126-session realized vol |
| CG-BSC-daily target vol | 29.3% annualized | development-window median of the base book's own trailing-126-session realized vol (NOT BSC's own 12%, which is WML-specific -- see external-brief.md) |
| CG-STOP drawdown trigger | -30.0% | 1.5x(dev-window book max DD)x0.5, clipped to [12%,30%] -- clipped at the 30% ceiling (the raw development-window book max drawdown exceeded 40%) |
| CG-MKT-STOP re-entry | 17 sessions | median recovery time across development-window SPY single-day >=7% declines (>=3 such events found; data-derived, not hand-picked) |

## Step 2c: per-candidate results
| candidate | anchor CAGR (10/20bp) | anchor DD (10/20bp) | anchor Sharpe (10bp) | holdout Sharpe / return | placebo beat-frac | stress-window CAGR/DD (10bp) | G1 | G1' | G2 | G3 | G4 |
|---|---|---|---:|---|---:|---|---|---|---|---|---|
| CG-DM (Daniel-Moskowitz bear/panic) | 63.1% / 62.2% | -41.5% / -41.6% | 1.09 | 0.87 / 47.3% | 100% | 11.0% / -49.7% | FAIL | FAIL | FAIL | FAIL | FAIL |
| CG-BSC-daily (Barroso-Santa-Clara vol scaling) | 37.0% / 36.4% | -27.4% / -27.5% | 0.98 | 0.74 / 23.7% | 70% | 7.9% / -36.4% | FAIL | FAIL | FAIL | FAIL | FAIL |
| CG-STOP (book-level drawdown stop) | 32.1% / 30.5% | -41.9% / -42.2% | 0.74 | 0.15 / -3.4% | 70% | 5.3% / -52.1% | FAIL | FAIL | FAIL | FAIL | FAIL |
| CG-DM-BSC (DM x BSC combination) | 37.0% / 36.4% | -27.4% / -27.5% | 0.98 | 0.74 / 23.7% | 70% | 7.1% / -36.4% | FAIL | FAIL | FAIL | FAIL | FAIL |
| CG-MKT-STOP (SEC 7% market circuit breaker) | 63.1% / 62.2% | -41.5% / -41.6% | 1.09 | 0.87 / 47.3% | 100% | 12.5% / -49.7% | FAIL | FAIL | FAIL | FAIL | FAIL |

G1: anchor CAGR>=50% and max DD<=35%. G1': anchor Sharpe>=2.0 and CAGR>=30%. G2: holdout Sharpe>=1.0 and holdout return>0. G3: <=10% of 20 calendar-shifted (1-20 session) multiplier placebos match or beat the real guard's anchor Sharpe (at 10bp). G4: G1 or G1' still holds at 20bp. G5 (long-only, Alpaca-executable): true for all 5 by construction, not separately tabulated. A candidate needs (G1 or G1') and G2 and G3 and G4 to pass.

## Findings
**0 of 5 candidates pass.** Every candidate fails at least G2 (holdout Sharpe never reaches 1.0; best is CG-DM/CG-MKT-STOP at 0.87) and G3 (every candidate's placebo beat-fraction is 0.70 or 1.00, far above the 10% ceiling) simultaneously; no candidate needs G4 evaluated as a tie-breaker.
- **CG-DM and CG-MKT-STOP are numerically identical to the unguarded base book over the anchor and holdout windows** (multiplier is exactly 1.0 throughout, confirmed directly from `cache/guard_multipliers.parquet`). This is not a bug: both guards DO trigger elsewhere in the full 2016-2026 history (CG-DM: 12 sessions, first 2020-03-13, the week of the COVID panic; CG-MKT-STOP: 24 sessions, all within 2020-03-10..2020-04-13, the week actual real-world Level-1/2/3 market-wide circuit breakers fired) -- they simply found no session in 2024-2026 meeting their published trigger criteria. SPY's trailing 24-month return never went negative in this window, and no single SPY session fell 7% or worse. This directly confirms the external-brief's pre-registered honest expectation, and Joseph Pach's account (claim `josephpach2025_march_crash_scale`) that the real March 2025 momentum crash was a fast, multi-day, forced-deleveraging event concentrated in momentum-basket names, not a single-day, broad-market >=7% shock -- exactly the kind of event a published, market-wide crash indicator calibrated to 2020-style crashes does not catch. Because the multiplier is trivially constant, G3's placebo is meaningless by construction here (every shift ties the real series exactly), which is why beat-frac is 1.00 for both -- reported honestly, not treated as a separate failure mode from 'never triggered.'
- **CG-BSC-daily (and CG-DM-BSC, identical to it here since CG-DM's leg is a no-op) does cut anchor max DD to -27.4%, comfortably under the 35% gate**, but CAGR falls to 37.0%, under G1's 50% floor. G1's alternate 30% CAGR floor is met, but Sharpe 0.98 misses G1's alternate 2.0 Sharpe bar by a wide margin, so G1' also fails. This is the exact same 'volatility targeting slides along the same risk-return line instead of improving it' pattern L-20260918-01 already found on a different book at a different (monthly) cadence -- reproduced here on a new book at daily cadence, strengthening rather than reopening that prior conclusion. Its calendar-shift placebo beat-fraction is 0.70: 70% of arbitrary 1-20-session shifts of its own multiplier match or beat its real anchor Sharpe, meaning the apparent risk reduction is statistically indistinguishable from an arbitrary on/off schedule with the same average exposure -- the same placebo failure mode that refuted L-20260918-01's trend gate.
- **CG-STOP makes the anchor max drawdown slightly WORSE than the unguarded book** (-41.9% vs. -41.5% unguarded) **and severely damages holdout performance** (holdout Sharpe 0.15, holdout return -3.4%, versus the unguarded book's own holdout Sharpe 0.87). Diagnosis (see `cache/guard_multipliers.parquet` and the walk-through in decision-record.md): whenever the book's drawdown hovers close to the -30% trigger while its equity happens to already sit above its own 50-session SMA (a real, observed pattern in January 2024 and again near the holdout window), the rule whipsaws -- triggering and re-entering within a session or two, repeatedly -- adding turnover without avoiding the eventual larger drawdown legs (2025-03..2025-04, 2025-11..2026-01, 2026-07..2026-09) that this design's slow, reactive, already-in-a-30%-hole trigger is too late to prevent and whose SMA-based re-entry is too early relative to DM's own finding that crashes are 'contemporaneous with market rebounds' (the guard tends to step out only after most of the damage, then risks re-entering before the rebound is secure). A genuinely harmful result, reported as such rather than reframed.

## Verdict
Per card H-20260924-02's preregistered stop condition: **0 of 5 candidates pass; the direction is refuted for this parameterization.** No daily [0,1]-exposure guard built from these three published mechanism families -- at the published or development-window-only thresholds used here -- brings the T1 12-1 momentum book to anchor max DD<=35% while keeping CAGR>=50% and beating its own calendar-shift placebo. See `decision-record.md` for the formal continue/pivot/stop call and `reopen_if` condition.
