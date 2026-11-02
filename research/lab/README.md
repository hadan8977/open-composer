# Shared numerical research

`open_composer.lab` owns the shared ETF return/cost ledger, cumulative trials,
batch results and metrics. Share/cash daily books and intrabar StrategySpec fills
retain their existing native engines: those are different accounting models.
Frozen scientific sources remain evidence, not templates for new private engines.

The original `scripts/screen_batch.py` now calls `lab.screening.run_screen_batch`.
The salvage, defense, volatility brake, tranching and two/three-sleeve combination
paths call `lab.accounting` for actual returns, turnover, cost and weight drift.
The source's sum/dot reduction order, initial cash fee, next-open timing and linear
return-leg convention are preserved. Results include per-offset turnover and
10/20 bp costs beside the return paths. This is calculation reuse, not just export.

The independent cross-asset scope review found that the historical sleeve-combination
formula applies new allocation weights to whole-session returns, including the
pre-fill overnight move. Its combination statistics are historical diagnostics.
New contribution studies must use `book_engine` with combined asset targets, so
old holdings earn overnight returns before the next-open fill. Preserving old
arithmetic does not certify that legacy execution convention.

```bash
scripts/run_capped.sh --mem 400M --wait-min 0 -- .venv/bin/python scripts/screen_batch.py \
  --batch <accepted_module> --iteration <accepted_iteration> \
  --direction <economic_direction> --run-id <unique_batch>
```

The original manifest still defines accepted candidates. Outputs now live under
`research/<direction>/batches/<run-id>/`, including the native leaderboard and
returns file; old reports are never overwritten. Keep the same direction across
related batches. A retained old leaderboard imports its documented trial count
once; unknown earlier searches remain a limitation, never a fabricated zero.
Every actual new start, including failed candidates, enters the same TrialLedger.
DSR in the new leaderboard uses the final cumulative inventory and exact candidate
calendar. Native evaluation-time DSR/count remain separately labeled in evidence.
The default iteration direction is for compatibility; supply the established
economic direction when another batch belongs to it.

## Entry points

- `spec_engine(spec, frame, root=..., run_id=..., backend="python_reference")`
  calls the existing `backtest_frame`, preserving its bar-close decision,
  next-open fill, fees, slippage, impact, position sizing, and warmup boundary.
  It supports daily and minute/hour bars. `backend="nautilus_trader"` calls the
  existing event engine strictly: missing dependencies fail, without fallback.
  The event adapter currently supports the native long-only single-symbol policy
  and cannot score a separate warmup boundary.
- `book_engine(close, open_, decide, config=BookConfig(...))` calls the existing
  daily equity-book engine. It applies `sanitize_price_matrices` with defaults and
  suppresses new decisions on split-like trigger sessions. Costs, borrowing,
  margin, holdings and exposures remain in the native ledger. It does not select
  names using future holding-period outcomes. Use an admitted native consumer for
  source replications whose frozen price treatment differs.
- `screen_engine(...)` calls the original `screen_lane.evaluate_candidate`.
  `screen_variants(root, batch_name, iteration=..., panel=..., trial_count=...,
  initial_equity_usd=...)` also reuses `screen_batch` candidate loading, manifest
  and calendar-anchor guards. Panel construction stays with the admitted source
  experiment. The source's 10/20 bp cost views, calendar windows, judged offsets
  and contaminated reference holdout remain unchanged. These ETF assumptions are
  not applied to other research. The supplied USD capital scales source account
  returns; it does not establish achievable capacity.
- Custom source-native programs return `EngineResult` to use the same writer.
  Supply the actual account equity, original native payload, optional native
  ledger and observed session returns. Compound returns must reconcile to account
  equity. The wrapper does not infer a return series from closed-trade PnL.

The current Martin reception adapter is
`research/martin_model_completion_20261102/lab_bridge.py`. It imports complete
saved native accounts, cash bridges and mark flags without a replay; an H/R
identity reuse requires its existing independent receipt. Such an import is an
accounting view, not a new experiment. Its known S/T selectable subset does not
convert the historical account-start floor into independent trials. Unknown
history and missing physical return paths leave DSR unavailable. The next actual
variant batch must use the same trial ledger; importing alone does not satisfy
the restructuring's real batch acceptance.

`BacktestArtifacts.equity_curve` and `NautilusBacktestArtifacts.equity_curve`
expose the account marks already computed by their engines, including initial
equity. The additive fields default to empty lists for constructor compatibility.
No fill or cost calculation changes. Intraday marks compound by the explicitly
declared session timezone (default `America/New_York`); missing dates are never
invented. Weekly bars and arbitrary session calendars need an explicit native
adapter before using these daily statistics.

## Run a batch

```python
from open_composer.lab import DSRConfig, Experiment, TrialLedger, Variant, run_batch

# Install/reconcile real research authority through the owner workflow first.
# The runner never enables research itself.
ledger = TrialLedger(root / "research/my_direction/trials.jsonl")
# Once only, if this direction has already been tried:
ledger.import_prior(
    "historical_campaign", count=actual_prior_count,
    evidence=["reports/original-trials.json"],
    note="Includes failed and rejected selectable configurations; seen windows retained",
)

batch = run_batch(
    root,
    experiment=Experiment(
        direction="my_direction",
        data_and_exposure="Exact input files, clocks, frozen windows, seen/OOS status",
        costs="Actual native fee/slippage assumptions, not a universal execution estimate",
        baseline="Matched native baseline under identical data and costs",
        baseline_net_profit_usd=measured_baseline_pnl,
    ),
    batch_id="new_batch_id",
    variants=[Variant("candidate_id", parameters, evaluate_native_engine)],
    dsr_config=DSRConfig(
        method="campaign_statistics", benchmark=aligned_daily_benchmark,
        benchmark_note="Declared benchmark and availability clock",
        hac_lag=frozen_hac_lag,
        assumptions="Cumulative selectable starts; frozen HAC and serial-dependence assumptions",
    ),
    selected_id="candidate_id",  # Explicit publication; runner does not select a winner.
)
```

The actual return arrays, native payload and current batch manifest are saved in
`research/<direction>/batches/<batch>/`. Every successful variant gets
`native.json`, optional `ledger.csv` and `returns.csv`, `metrics.json`, and
schema-valid `results.json`. The batch saves an immutable trial snapshot and
`batch.json`; `selected_id` also updates the direction's `results.json` atomically.
Any publication leaves the original batch result intact. Nonfinite native values
are retained as tagged `{"native_nonfinite": "nan"}`/`"inf"` objects in strict JSON.
Summary account metrics require finite values.

`trials.jsonl` appends a durable start before evaluation and a finish after native
evidence is saved. All selectable starts count, including failed and interrupted
ones. Earlier batches and explicitly imported historical trials remain counted.
Diagnostics, accounting views and null replications may declare
`counts_as_trial=False` with a reason; their events still remain in the inventory.
Do not use that field to exclude economically selectable variants. A prior import
requires original evidence and refuses a repeated import id. Failed trials are
not assigned fabricated returns or Sharpe dispersion.

A start left without a finish blocks new batches in that direction until the
operator confirms that no native/remote job remains live and appends
`ledger.finish(..., status="interrupted", evidence=[...], note=...)`. Its exposure
remains counted. Invalid ledger JSON fails closed and is not truncated. Duplicate
batch/trial ids cannot overwrite evidence. Authority is checked before the batch
and before each numerical start. No quota, paid-compute, paper or broker authority
is created by this API.

## DSR and numerical meaning

`DSRConfig` selects the existing estimator explicitly. `run_batch` also accepts a
callable from EngineResult to DSRConfig when candidates have different observed
calendars; the final cumulative trial count is applied by the writer:

| Method | Inputs and preserved meaning |
| --- | --- |
| `scorecard_v2` | Session excess returns, declared annual Sharpe variance and effective trial count. Calls `scorecard_v2.dsr` unchanged; iid moment estimator, without implicit HAC correction. |
| `campaign_statistics` | Session excess returns, cumulative `n_trials`, frozen HAC lag. Calls `deflated_sharpe_probability` unchanged; native minimum of ordinary/HAC probabilities. |
| `none` | `dsr=null` with the reason that no estimator was declared. |

The writer never estimates dispersion from only the surviving variants, resets
the count per batch, or silently zero-fills a benchmark. Benchmark timestamps must
match exactly. Missing benchmark/dispersion/assumptions, constant returns, too few
observations and the campaign estimator's single-trial limitation produce
`dsr=null` with an explicit method and reason. For scorecard mode, supplied
`n_eff` must be between one and cumulative `n_trials`; its evidence belongs in the
assumptions. The immutable metrics artifact records the complete statistical
configuration, source sample length and any native statistic detail. The Results
field `dsr_note` carries the same structured explanation.

The original screen DSR remains in `native.json` with its count at source
evaluation time. The wrapper's DSR is separately labelled and recomputed against
the completed cumulative inventory. Source results are evidence, not silently
rewritten historical acceptance criteria. Native short-sample and trading
limitations remain beside the result; synthetic/accounting checks establish
plumbing, not Alpha or paper readiness.

## Credential-free example and checks

After research authority is installed, this computes two **synthetic diagnostic**
variants using the native daily book engine with 10 bp per-side costs:

```bash
.venv/bin/python -m open_composer.lab example --root . --batch fixture_001
```

The command never writes `control.json`. Its 80 synthetic sessions and resulting
P&L have no economic interpretation. A second fresh batch id retains earlier
trial exposure; a repeated id fails. The fixture can also run in an isolated test
workspace with that workspace's explicit test authority.

The example also saves `ablations.json`: four actual pairs of native reference
runs with declared baseline/alternative configuration values and their measured
profit, fees and signal-count differences. Daily fixture shocks exercise the risk
branches; minute parity fixtures use basis-point moves to avoid annualizing
daily-size shocks as minute observations. Shared analytics behavior is unchanged.

`lab.ablation.check_ablations` checks observables on condition-triggering fixtures.
The tests trigger stop, take-profit, fee and sizing branches; an ignored switch
fails. A separate no-trigger case correctly allows equal output. This validates
the claimed behavior without requiring every real-data toggle to change profit.

Focused verification (one pytest process, coordinated by the main session):

```bash
.venv/bin/pytest tests/test_lab_ledger.py tests/test_lab_metrics.py \
  tests/test_lab_adapters.py tests/test_lab_batch.py tests/test_lab_screen.py
```

Measured on 2026-10-28 under a 900 MiB cap: all 21 focused tests passed, including
the installed Nautilus daily/minute adapter. The synthetic example then completed
in 1.91 seconds after imports. Its exported
[validation summary](validation-20261028/validation.json),
[Results contract](validation-20261028/research/lab_example/results.json),
[native metrics](validation-20261028/research/lab_example/batches/synthetic_validation/weight_60/metrics.json)
and [ablation evidence](validation-20261028/research/lab_example/batches/synthetic_validation/ablations.json)
record two trials, 80 sessions, native 10 bp per-side costs and the explicit
`campaign_statistics` DSR. The temporary test workspace's authority file was not
exported; installed research authority and historical financial research were
unchanged. These figures are fixture verification, without a market-profit claim.
