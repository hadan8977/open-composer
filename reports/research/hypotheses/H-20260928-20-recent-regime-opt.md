---
card_id: H-20260928-20
status: executed, no replacement (round 1, 2026-09-28) -- E0 and S0 both stand unchanged
lane: preregistered, batch screen, optimization round
previous: H-20260928-05
direction_id: dir:end_of_month_reversal_effect, dir:front_running_sector_seasonality
iteration: h20260928_20_recent_regime_opt
criteria:
  - name: e_family_select_10bp_sharpe_vs_base
    threshold: 0.10
    direction: ">= base +"
  - name: e_family_holdout_2026_sharpe_guard_vs_base
    threshold: -0.10
    direction: ">= base +"
  - name: e_family_select_20bp_sharpe_vs_base
    threshold: 0.10
    direction: ">= base +"
  - name: s_family_select_10bp_sharpe_vs_base
    threshold: 0.10
    direction: ">= base +"
  - name: s_family_holdout_2026_sharpe_guard_vs_base
    threshold: -0.10
    direction: ">= base +"
  - name: s_family_select_20bp_sharpe_vs_base
    threshold: 0.10
    direction: ">= base +"
---
# H-20260928-20 recent-regime optimization: EOM reversal and sector seasonality vs their own batch-2 bases

- Status: **executed, no replacement** (round 1) -- hypothesis family: bounded,
  source-grounded parameter variant search over two owner-liked batch-2
  candidates -- layer: standalone rule optimization -- data tier: **tier 3**
  (OHLCV-derived quantities only)
- Previous link: H-20260928-05 (batch-2: EOM_REVERSAL_SPY and
  FRONT_RUN_SECTOR_TOP2 both landed `watch_recent` -- anchor-clearing,
  stress-failing)
- Iteration dossier: `reports/research/iterations/h20260928_20_recent_regime_opt/`
  (direction-review, external-brief, candidate-manifest with 20 candidates,
  search-space, cost-contract, data-feasibility, results.json, report.md;
  passed `oc research direction-check` and `oc research iteration validate
  --stage pre-backtest` and `--stage final`)
- One-line hypothesis: does any preregistered E-family variant (E1-E7) beat
  EOM_REVERSAL_SPY (E0), or any S-family variant (S1/S2/S_AVG3/S_AVG5/
  S_SHIFT0/S_SHIFT2/S_11SECTORS/S_INVVOL/S_ABSFILTER) beat
  FRONT_RUN_SECTOR_TOP2 (S0), under the owner's literal three-part
  replacement rule?

## Why

The owner explicitly asked (2026-09-28) for optimization of these two
specific batch-2 candidates after seeing they were strong in 2024-2026 but
weak in 2016-2023. `oc research directions check` found both mechanisms
registered (queued, batch-2 verdict recorded) with no local
variant/optimization search yet. The primary Graziani (2024) PDF (opened
directly this round, not just a secondary summary) and Quantpedia's live
front-running-sector-seasonality page each publish their own robustness
checks (alternate formation windows and a magnitude-scaled variant for
Graziani; 1-7-ETF-count and shift-0-vs-1 for Quantpedia), directly grounding
several of the 20 preregistered variants. Allocate Smartly's two
independent extended-out-of-sample tests of the closely related
front-running mechanism (country ETFs, commodities) both found the effect
failed extension before the original author's sample -- negative evidence
motivating a conservative three-part replacement rule rather than a raw
select-window-only bar.

## Design

Machine (frozen, not searched): 20 candidates, each a single preregistered
parameter change from its family's base (E0 or S0), or a static combination
of the two (C1, C2). All are calendar-anchored `freq: "D"` rules (single
version, no offset sweep) with an explicit `signal_dates_fn` covering every
entry and exit date, extending (not editing) `h20260928_05_batch2.py`'s
functions. Cost 10bp/side primary, 20bp/side stress, next-open fill,
unchanged from batch-2.

Candidates (20): E0-E7 (EOM reversal base + formation-window/threshold/
symbol/holding-truncation/magnitude-scaling variants); S0, S1, S2, S_AVG3,
S_AVG5, S_SHIFT0, S_SHIFT2, S_11SECTORS, S_INVVOL, S_ABSFILTER (sector
seasonality base + top-N/lookback/shift/universe/weighting/filter
variants); C1, C2 (EOM-gated sector top-2; 50/50 static blend, descriptive
only).

Windows: select 2023-09-18..2025-12-31, anchor 2024-01-08..2026-09-17,
stress 2016-05-02..2023-09-15, holdout 2026-01-02..2026-09-17 (contaminated,
used only as the replacement rule's guard).

## Gates (adoption rule)

Owner's literal three-part per-family replacement rule (preregistered
before any result was computed): a variant replaces its family's base only
if (a) its 10bp select-window Sharpe >= base + 0.10, AND (b) its 2026
window Sharpe is not below the base's by more than 0.10 (guard), AND (c)
its 20bp select-window Sharpe is still >= base + 0.10. Among qualifiers,
the highest select Sharpe wins. DSR computed per family with
trial_count = that family's variant count including base (E=8, S=10, C=2),
not pooled across all 20 candidates. C1/C2 are not eligible to replace
either base; reported descriptively against both components.

## Results

Executed 2026-09-28 (`scripts/screen_batch.py --batch h20260928_20_recent_opt
--iteration h20260928_20_recent_regime_opt`; report
`reports/research/iterations/h20260928_20_recent_regime_opt/report.md`,
`results.json`; raw leaderboard
`reports/research/screens/h20260928_20_recent_opt/leaderboard.json`).
**No replacement in either family; both bases (E0, S0) stand unchanged as
the batch-2 result.**

Base reproduction confirmed first: E0 select 1.3390 / anchor 1.2406 and S0
select 0.7504 / anchor 1.4022, matching batch-2's EOM_REVERSAL_SPY (1.34 /
1.24) and FRONT_RUN_SECTOR_TOP2 (0.75 / 1.40) to 4+ decimals.

E family: E5 (hold only first 10 sessions of next month) is the only
variant clearing condition (a) (select10 Sharpe 2.0003 vs. E0's 1.3390 +
0.10 bar), but fails guard (b) -- its 2026 Sharpe (-0.7890) drops 0.215
below E0's (-0.5740), more than the 0.10 allowed. No other E variant clears
(a) at all; E1/E2 (the source's own tested formation-window robustness
check, last 5/10 sessions) both underperform E0 by a wide margin,
consistent with Graziani (2024)'s own finding that only the last week's
return predicts.

S family: S_SHIFT0 ("true seasonality", Quantpedia's own reported-failing
baseline) is the only variant clearing condition (a) (select10 Sharpe
1.2006 vs. S0's 0.7504 + 0.10 bar), but fails guard (b) hard -- its 2026
Sharpe (1.6446) is far below the 2.9080 floor required by S0's own 3.0080.

C family (descriptive): C1 select10 0.9461, C2 select10 1.0759 -- both beat
S0 alone but remain below E0 alone; neither beats both components.

SSO context (descriptive, 50%/yr gate only, not an optimization): E0
(unchanged winner) with SSO instead of SPY gives anchor Sharpe 1.496,
anchor CAGR 24.0%, anchor max drawdown -9.05% -- does not clear 50%/yr,
reported as context only.

Lesson: in both families, the one variant that clears a large select-window
Sharpe improvement (E5, S_SHIFT0) does so by concentrating performance in a
way that does not carry into the still-open 2026 window consistently with
the base -- exactly the failure mode the owner's guard condition (b) was
designed to catch. Neither family's apparent search-space improvement
survives that guard; this is a genuine, useful negative result, not a
workflow failure. Do not retry either family with new parameters inside
this same manifest without a new mechanism or newly disclosed data/source.
