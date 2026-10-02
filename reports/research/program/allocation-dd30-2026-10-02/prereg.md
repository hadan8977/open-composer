# Program allocation under a ~30% drawdown budget, return first: preregistration

T-20261002-43. Written 2026-10-02 13:14 UTC by the interactive lead (Opus). Frozen before any combined (multi-engine) return is computed.

The single-engine statistics quoted below were already known from earlier work. The weights, the frontier and the choice are computed only after this file is committed.

## Owner instruction

2026-10-02 12:45 UTC: "最大回撤30吧，你来看着配，不用很严格，追求收益优先。其他的不用问我同意，你来决定。"

The researcher's reading of that instruction:

- The **objective** is the highest recent-window return of the whole program.
- The **constraint** is a maximum drawdown of about -30% on the full history, which includes the 2018-Q4, 2020-03 and 2022 stress episodes.
- The bound is soft: "not strict". The -30% design point is primary; the -25% and -35% points are reported so the trade-off is visible.
- This follows the owner's recent-market rule: the recent window decides; old data diagnoses crash risk only.

## Engines (fixed; why these)

| id | what | series used | already known (single engine) |
|---|---|---|---|
| S3 | levered ETF rotation, vol target 0.40 / 0.60 boost (paper sleeve) | `sleeve_returns()["s3"]` from `scripts/run_h20260927_01_sleeve_combination.py`, 10 bp/side (20 bp stress), computed on `data/sip/daily` after the T-20261002-01 swap (total-return prices) | anchor CAGR 118%, anchor DD -32%, stress-window DD -48% |
| C2 | SPY + sector SPDR composite (paper sleeve since 10-01) | `C2__o00__net10` (stress `net20`), `reports/research/screens/h20260928_20_recent_opt/returns.parquet` | anchor 21.1%/yr, vol 9.6%, DD -6.6%; stress Sharpe 0.55; corr with S3 0.44 |
| F1 | v1.2 M0_U3000 market-neutral book (quant1) | `net_pnl / 1e6`, `data/research/book_v12/A1_M0_U3000_F1.parquet` | recent 9.5%/yr, vol 5.2%, DD -5.6%; full 5.0%/yr, DD -12.4% |
| F2 | v1.2 M0_U3000 index-plus book (quant2) | `net_pnl / 1e6`, `…_F2.parquet` | recent 24.0%/yr, DD -20%; full 17.3%/yr, DD -42.9% |
| CASH | T-bills | BIL daily total return from the same SIP panel | — |

S1 and S2 are excluded. H-20260927-01 showed that blending them with S3 equals delevering S3: S2/S3 correlation is 0.79–0.83 and the stress-period edge is about 0.

## Windows (common data 2017-10-02 .. 2026-09-15)

| window | dates |
|---|---|
| full | 2017-10-02..2026-09-15 |
| stress | 2017-10-02..2023-09-15 |
| select | 2023-09-18..2025-12-31 |
| anchor | 2024-01-08..2026-09-15 |
| ytd2026 | 2026-01-02..2026-09-15 |

## Mechanics

- **Rebalancing:** monthly, to target weights on the k-th session of each month, k ∈ {0, 5, 10, 15}. k = 0 is primary; all four are reported (date-neutral rule, owner 09-28). Weights drift with returns between rebalances.
- **Rebalancing cost:** 5 bp on the sum of |Δweight| at each rebalance.
- **Grid A (unlevered):** weights in steps of 0.05 on {S3, C2, F1, F2, CASH}, summing to 1. That is 10,626 points.
- **Grid B (levered):**
  - w_S3, w_C2, w_F1 and w_F2 in steps of 0.05, with Σ ≤ 1.5. CASH = max(0, 1 − Σ). The borrowed amount max(0, Σ − 1) costs 6.50%/yr, the v1.2 contract's non-elite Alpaca rate, taking the unfavourable side.
  - The approximate margin feasibility filter must hold on every session:
    - **initial:** 0.75·w_S3 + 0.50·(w_C2 + w_F1·g_F1 + w_F2·g_F2) ≤ 1.0;
    - **maintenance:** 0.75·w_S3 + 0.30·(w_C2 + w_F1·g_F1 + w_F2·g_F2) ≤ 0.9.
  - g is the engine's daily gross / 1e6 from the parquet.
  - The 0.75 requirement for 3x ETFs follows FINRA 4210's leveraged-ETF rule. The exact Alpaca requirement is **待核对 (to be checked)**.
  - Points that fail the filter are reported as infeasible and never chosen.
- **Program NAV:** compounded daily. Max drawdown is peak-to-trough on that NAV.
- **Stress costs:** S3 and C2 use their 20 bp series. F1 and F2 have no separate stress series, so the v1.2 cost sensitivity is not repeated here; this is a limitation.

## Decision rule (frozen)

1. **W\*:** in grid A and in grid B separately, the point with the highest anchor CAGR among points with full-window max DD ≥ -30% (k = 0, primary costs). Ties go to the shallower full-window DD.
2. **Control:** S3 + CASH, with w_S3 the largest grid value whose full-window DD is ≥ -30% (the "delevered S3"). Diversification has to beat this control. That is the lesson of H-20260927-01.
3. **Adopt W\*** (the grid-B one if feasible and better, else grid A) only if all three hold:
   - **(i)** anchor CAGR(W\*) ≥ anchor CAGR(control) + 3 percentage points;
   - **(ii) out-of-window sanity:** choose W_sel by the same rule on the **select** window (objective = select CAGR, same DD constraint). Its **ytd2026** CAGR must be ≥ the control's ytd2026 CAGR;
   - **(iii) stability:** every feasible ±0.05 single-coordinate neighbour of W\* has anchor CAGR within 5 points of W\*, and the four rebalance offsets move anchor CAGR by less than 5 points.
4. **If (i) fails:** the program is the control (S3 + CASH at the DD-matched weight). C2, F1 and F2 stay on paper for their own evidence and get no program weight.
5. **If (i) holds but (ii) or (iii) fails:** use the robust alternative, the plain average of the weights of the 10 best feasible points. Recheck its DD (must still be ≥ -30%) and report it.
6. Also report:
   - the -25% and -35% frontier points;
   - inverse-volatility weights (63-session trailing, monthly) over {S3, C2, F1, F2}, unlevered;
   - every chosen point's per-window CAGR, vol, Sharpe, max DD, worst month, and 2018 / 2020 / 2022 calendar returns;
   - pairwise engine correlations in stress and anchor.

## What the result changes

- **The allocation of the live-candidate program.** Paper accounts keep running each engine at its own size. Program-level forward P&L is computed from the accounts' daily returns with the chosen weights, so no paper sleeve is resized; returns do not depend on scale.
- **The 11-01 sleeve renewal** (T-20261002-30 account review) and the later live proposal.
- The expected program numbers are shown to the owner as a backtest, with the caveats below.

## Known caveats (written before results)

- **Selection bias in S3.** S3's anchor CAGR (118%) comes from a salvage iteration whose design saw part of the 2023–2025 data. Its forward record so far is about two weeks (-1.8%). A return-first weighting leans on it, so the forward stop rules matter more than the backtest number.
- **Grid search over the anchor window is in-sample.** Rule 3 (ii)–(iii) and the delevered-S3 control are the guards. DSR is not meaningful for a weight grid, so it is not reported.
- **Engines live in different accounts during paper.** Grid B assumes they share one Reg T account; the margin filter is an approximation.
