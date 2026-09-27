---
card_id: H-20260927-01
status: executed, refuted (round 1, 2026-09-27)
lane: preregistered
previous: H-20260922-05
direction_id: dir:paper_sleeve_combination
iteration: h20260927_01_sleeve_combination
criteria:
  - name: anchor_g1_or_g1alt_10bp
    threshold: pass
    direction: required
  - name: anchor_g1_or_g1alt_20bp
    threshold: pass
    direction: required
  - name: sharpe_edge_vs_control_anchor
    threshold: 0.10
    direction: ">="
  - name: sharpe_edge_vs_control_stress
    threshold: 0.10
    direction: ">="
  - name: stress_max_drawdown_vs_control
    threshold: 0
    direction: "shallower"
---
# H-20260927-01 combining S1/S2/S3 vs delevering S3 alone at matched volatility

- Status: **executed, refuted** (round 1) -- hypothesis family: paper_sleeve_combination -- layer:
  portfolio construction across three already-frozen books (no sleeve internals re-tested) --
  data tier: **tier 3** (OHLCV-derived quantities only)
- Previous link: H-20260922-05 (S1/S2/S3 renewal: S2 vol target 0.156 frozen from the selection
  window's own median realized vol; S3 vt40 + QQQ oversold dip boost to 0.60/10 sessions frozen
  and unchanged here)
- Iteration dossier: `reports/research/iterations/h20260927_01_sleeve_combination/`
  (direction-review, external-brief, candidate-manifest with 7 candidates, search-space,
  cost-contract, data-feasibility; passed `oc research direction-check` and
  `oc research iteration validate --stage pre-backtest` and `--stage final`)
- One-line hypothesis: does combining the three live paper sleeves at a fixed (or trailing
  inverse-volatility) proportion beat simply delevering S3 alone to the same realized volatility,
  on Sharpe and stress-period drawdown, without breaking the frozen anchor-window return bar?

## Why

S3 alone is the highest-return sleeve but carries a pre-window (2016-2023) max drawdown of -48.0%
(H-20260923-09/11). The live-pilot decision needs to know whether combining S3 with the two lower
S1/S2 sleeves in one account genuinely reduces risk through diversification, or whether it is
equivalent to just running S3 at lower volatility -- in which case a combined account adds
operational complexity (three sleeves, three sets of fills) for no risk-adjusted benefit over a
single delevered S3 book. The registry dedup check
(`oc research directions check sleeve combination diversification portfolio`, 2026-09-27) found no
prior local test of this question; the closest hits (`dir:meta_strategy_trailing_return_rotation`,
rotating capital *between* strategies by trailing return, and `dir:defense_first_taa_carlson_concretum`,
a different asset-class tactical model) are different mechanisms.

The comparison methodology is not invented here: Newfound Research's "Portable Beta" analysis
(2017-12-04, verified quote in `reports/harness/source_cards/h20260927_01_sleeve_combination.jsonl`)
and AQR's risk-parity papers (Understanding Risk Parity; Leverage Aversion and Risk Parity) both
establish that a diversified/levered portfolio's value must be judged against a volatility-matched
levered-or-delevered version of the concentrated alternative, not against the concentrated
portfolio at its own natural risk -- otherwise "diversification benefit" is just an artifact of
running at lower average risk. This round's Ci = k*S3 + (1-k)*SHY control implements exactly that.
M3's trailing-63-session inverse-volatility weight rule follows established risk-parity/inverse-vol
combination practice (Alpha Architect, Quantpedia), rather than an invented weighting scheme.

## Design

Machine (frozen, not searched): S1 = salvage key "s1", target=None. S2 = salvage key "s2",
target=0.156 (from `strategy_specs/drafts/us_etf_growth_rotation_blend_top2_monthly.yaml`). S3 =
salvage key "s3", target=0.40, boost=`salvage.boost_window(salvage.dip_signal(close), 10)`,
boost_target=0.60. Each sleeve's daily net return is `salvage.run_cell(...)`'s first return value,
unchanged. Cost 10 bp/side primary, 20 bp/side stress on each sleeve's own turnover, reused
contract `cost_v1_10_20bps_next_open`.

Candidates (7, exactly as specified, no ranking among M1-M3 -- each judged only against its own
paired control and against the M0 reference):
- **M0** reference: S3 alone, unchanged.
- **M1**: equal-thirds S1/S2/S3.
- **M2**: 0.5 S1 / 0 S2 / 0.5 S3.
- **M3**: trailing-63-session inverse-volatility weight across S1/S2/S3 (equal weight before 63
  sessions of combination history exist).
- **C1/C2/C3**: paired volatility-matched controls, Ci = k*S3 + (1-k)*SHY, k solved by bisection
  separately per evaluation window so std(Ci) == std(Mi) in that window (capped at k=1.0).

Combination mechanics: month-end close sets target sleeve weights, effective at the next session
open; intra-month weights drift with each sleeve's own daily net return (buy-and-hold drift, no
open/close leg split at the sleeve level, since a sleeve return is already a single blended daily
number). Combo rebalancing cost = combo_cost_bps x sum(|delta weight|), charged on the effective
(next-open) session, on top of each sleeve's own internal turnover cost. Ci controls rebalance
daily at the fixed per-window k with **no cost** -- conservative in the control's favor, adverse to
the combination.

Windows: common start 2017-02-01 (first session all three sleeves hold a non-cash position: S1
2017-01-09, S2 2017-02-01, S3 2016-05-02). Stress 2017-02-01..2023-09-15 (includes the 2018 and
2022 drawdowns). Select 2023-09-18..2025-12-31 (reported only, no ranking use). Anchor
2024-01-08..2026-09-17 (frozen gate G1/G1', do-no-harm plus transfer criteria). 2026-01-02..
2026-09-17 holdout reported but flagged contaminated (all three sleeves already individually
evaluated on it).

## Gates (adoption rule)

All four must hold, per Mi, independently, against its own paired Ci:
- **(a)** Mi passes G1 (anchor CAGR >= 50%, max drawdown >= -35%) or G1' (Sharpe >= 2.0, CAGR >=
  30%) at 10 bp.
- **(b)** Mi still passes G1 or G1' at 20 bp.
- **(c)** Sharpe(Mi) - Sharpe(Ci) >= 0.10 in **both** the anchor window and the stress period.
- **(d)** Mi's stress-period max drawdown is shallower than Ci's stress-period max drawdown.

G3 (placebo) does not apply: there is no discretionary asset pick or gate-timing signal to
randomize in a fixed-proportion/inverse-vol combination; the volatility-matched control Ci is
itself the placebo-equivalent check (same risk, no diversification).

## Results

Executed 2026-09-27 (`scripts/run_h20260927_01_sleeve_combination.py`; report
`reports/research/iterations/h20260927_01_sleeve_combination/report.md`,
`results.json`). **Refuted: none of M1/M2/M3 passes.**

M0 (S3 alone) reproduces the known pre-window drawdown: stress CAGR 24.5%, Sharpe 0.70, max
drawdown -48.0%; anchor 118.2%/1.84/-32.3% (10 bp). All three combinations comfortably clear (a)
and (b) -- anchor Sharpe 1.85-2.10, well above G1'. All three also clear (d): stress max drawdown
is slightly shallower than the paired control (M1 -23.9% vs C1 -26.5%; M2 -28.6% vs C2 -30.9%; M3
-23.3% vs C3 -23.3%, a razor-thin edge). But all three fail **(c)**: the Sharpe edge over the
matched control is positive in the anchor window (M1 +0.086, M2 +0.018, M3 +0.294) but collapses to
roughly zero or negative in the stress period (M1 -0.001, M2 +0.023, M3 -0.047) -- combining the
sleeves earns essentially the same risk-adjusted return as delevering S3 alone in the historically
hard window, and the apparent edge in the anchor window is a recent-regime artifact, not a
structural diversification benefit. Sleeve pairwise correlation explains why: S2/S3 correlation is
0.83 in the stress period and 0.79 in the anchor window (S2's growth-ETF picks overlap heavily with
S3's leveraged-tech menu); S1/S3 is lower (0.48 stress, 0.60 anchor) but not low enough on its own
(M2, which drops S2, still fails). Lesson: these three specific sleeves are correlated enough,
especially in stressed regimes, that fixed-proportion or inverse-volatility combination adds no
measurable value over simply running the highest-conviction sleeve (S3) at a matched, lower
volatility. Reopen only with sleeves that have demonstrably lower stress-period correlation to S3
than S1/S2 do here, not by re-tuning these three weight rules.
