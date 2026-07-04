# Next Iteration Readiness - 2026-07-03

Scope: Step 7.S Wave S.3 design note only. This document records the minimum
capabilities needed before the next strategy/ML iteration. It does not implement
training, change `ml_backend`, edit any active spec, or run a new backtest.

## 1. Path-Dependent Defensive Re-Entry Labels

Conclusion:

The next PDR ML gate attempt should not use a terminal-return label such as
`future h-day TQQQ return > tau`. It should use a path-survival label that
answers the actual trading question: "is it safe enough to leave GLD and hold
leveraged TQQQ through the next window?"

Basis:

- Step 7.R's selected gate used a cheap rebound label and failed:
  `ml_gate_beats_fixed_route=False`.
- The gated route increased total return but worsened full-window MaxDD from
  `-43.24%` to `-66.70%` and reduced Sharpe from `1.014` to `0.931`.
- The gate released during crash rebounds and the 2022 slow bear, exactly when
  GLD defense was valuable. Non-hard-stress route drift was `0`, so the failure
  was the label, not plumbing.

Candidate label:

```python
for decision_index in hard_stress_defensive_decision_rows:
    # Features for decision i must use only i-1 or earlier observations.
    feature_row = features_at_or_before(decision_index - 1)

    # Label window starts after the decision timestamp.
    forward_returns = tqqq_open_to_open_returns[
        decision_index + 1 : decision_index + 1 + horizon
    ]
    path = (1 + forward_returns).cumprod()
    terminal_return = path[-1] - 1
    drawdown_path = path / path.cummax() - 1
    forward_max_drawdown = drawdown_path.min()

    label = (
        terminal_return >= min_terminal_return
        and forward_max_drawdown >= -max_allowed_drawdown
    )
```

Minimum implementation range:

- Add a PDR-gate-specific label builder, not a generic strategy ML rewrite.
- Keep intervention limited to baseline state `hard_stress_defensive`.
- Reuse `open_composer/research/ml_backend/windows.py` purged/embargo windows.
- Enforce feature rows at `index-1`; labels may look forward only from the
  decision timestamp.
- Require `embargo_bars >= horizon_bars` for this gate family.
- Keep the first search space small, for example:
  `horizon={10,20}`, `max_allowed_drawdown={8%,12%}`,
  `min_terminal_return={0%}`, `theta={0.6,0.7}`. That is eight combinations,
  below the Step 7.R 12-combination ceiling.

Acceptance before any promotion:

- Trial ledger records every combination and no extras.
- Same-data baseline and gated runs are evaluated together.
- Gate passes only if drawdown protection does not degrade versus baseline.
- Failure writes a negative result and keeps the strategy draft.

## 2. Regime / Macro Feature Capability Assessment

Conclusion:

Regime and macro features are useful candidates for safe re-entry, but they
must be capability-gated before they affect trading. The next iteration should
first harden the data path, then decide whether those features enter the model.

Basis:

- Current `capabilities/registry.yaml` has `macro.fred_series` approved, but
  strategy-affecting macro features still need point-in-time replay packets with
  `visible_at`, `published_at`, `fetched_at`, `source`, `input_hash`, and
  `prompt_hash` when LLM/news/macro text is involved.
- `market.longbridge_bars` remains trial and Nasdaq Basic based; it is useful
  for research replay, not sufficient paper-ready evidence by itself.
- Step 7.R used only existing router quantities. That kept leakage risk low,
  but the failed label suggests the model lacked regime context about whether a
  rebound was a bear-market trap or a safe transition.

Data candidates:

- Rates and curve: FRED Treasury yields / curve spreads through
  `macro.fred_series`.
- Credit stress: FRED credit spread series, if freshness and release timing can
  be represented point-in-time.
- Volatility proxy: market-derived VIX/VIXY-style symbols only if the chosen
  market data provider has adequate history and same-source manifest evidence.
- Breadth: market-derived breadth from a defined ETF/stock panel; this needs a
  declared panel source and stale-membership caveat before it becomes a required
  capability.

Minimum implementation range:

- Run capability evaluation before adding any required capability to a spec.
- For macro/rates/credit, build replay packets with release-time metadata rather
  than using revised series as if they were known intraday.
- For breadth, prefer a small declared ETF/sector panel first. Full index
  constituent breadth is a later data-engineering task because membership is
  time-varying.
- Keep LLM advisory only unless a separate marginal-lift and missing-modality
  robustness report proves independent value.

Recommended pre-flight checks:

```bash
uv run oc capability test
uv run oc data verify-research-cache
uv run oc spec capabilities strategy_specs/drafts/<candidate>.yaml --json
```

## 3. Queue Decisions

Conclusion:

Do not resume broad strategy/ML iteration immediately. The next productive work
is a small harness-backed design loop: path-dependent label first, then regime
capability, then router asset-selection fixes. Cross-sectional ML should remain
queued until the route-level defensive task is better specified.

Basis:

- Step 7.R explicitly left `risk_on_ranked` for later: fold2 gap `-14.9pp`,
  fold3 gap `-23.6pp`, with USD/QLD selections hurting in choppy bull regimes.
- The QQQ daily ML champion remains research-only: good Sharpe and strict-data
  status, but only 20 trades, benchmark-family gaps, and factor warnings.
- Step 7.A.2 cross-sectional ML is broader than the current problem. It needs
  universe definition, PIT features, benchmark family, purged group-aware
  validation, and capacity/execution review.

Queue:

1. **PDR defensive label redesign**  
   Use `oc strategy router-attribution` and the existing Step 7.R artifacts to
   target only `hard_stress_defensive` release decisions. Implement the
   path-dependent label builder only after the above capability constraints are
   accepted.

2. **Regime/macro capability gate**  
   Decide whether the first path-dependent label iteration uses only existing
   router features or adds `macro.fred_series` / breadth features. If adding a
   capability, produce PIT replay evidence before training.

3. **`risk_on_ranked` asset-selection review**  
   Use attribution to isolate `risk_on_ranked` days and compare the current
   ranked choice against fixed TQQQ, QLD, QQQ, GLD/BIL, and a smoothed rank rule
   on the same data. This is a bounded router rule review, not ML first.

4. **7.A.2 cross-sectional ML**  
   Keep queued. Start only after the single-route PDR gate has a clean label
   contract and the data/capability path can support a multi-symbol model
   without future leakage.

Current readiness verdict:

- Ready to continue product-harness work: yes.
- Ready to run another PDR ML training iteration today: no, not until the label
  contract and capability decision are accepted.
- Ready to promote or paper-enable a new strategy from this line: no.
