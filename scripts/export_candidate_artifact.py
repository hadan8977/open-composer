"""Step 11 Wave B item 5: export a candidate's fitted model + metadata for the
product-side consumer (``open_composer/adapters/execution/`` -- owned by a
different executor this round, not touched here).

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 4/5. The interface
this script writes is defined in
``reports/research/control/step11-2026-09-06-progress.md``'s "Wave B item 5"
section *before* this script existed -- read that section first if the two
ever appear to disagree; the ledger section is authoritative and paths/field
names there are not to change once a consumer depends on them.

Usage::

    uv run python scripts/export_candidate_artifact.py step11_b1_momentum_top50
    uv run python scripts/export_candidate_artifact.py step11_b3_lightgbm_grid_daily_only

Exports whichever ``experiment_id`` you name, regardless of whether it passed
its gates (plan: "无论过不过门槛都要导出当前最好的那个" -- the "is this the
best one" judgment call is made by the caller / the Wave B report, not by
this script, which is a dumb, generic exporter for any already-ledgered
experiment_id).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import joblib  # noqa: E402
import pandas as pd  # noqa: E402
import run_b3_grid as b3  # noqa: E402 -- flat scripts/ dir, no package __init__

from open_composer.research.features.panel import load_feature_panel  # noqa: E402
from open_composer.research.kernel import loop  # noqa: E402
from open_composer.research.kernel.b3_grid_strategy import (  # noqa: E402
    DEFAULT_GRID,
    GridSelectedLightGBMStrategy,
)
from open_composer.research.kernel.baseline_strategies import (  # noqa: E402
    EqualWeightUniverseStrategy,
    MomentumFactorStrategy,
    RidgeRankStrategy,
)
from open_composer.research.kernel.loop import ExperimentConfig, RankingStrategy  # noqa: E402

LEDGER_PATH = ROOT / "reports" / "research" / "ledger" / "experiments.jsonl"
CANDIDATES_ROOT = ROOT / "reports" / "research" / "candidates"

# Reuse run_b3_grid.py's already-defined column blocks rather than a third
# copy -- it mirrors run_baseline_chain.py's B2_FEATURE_COLUMNS exactly (see
# that module's own docstring), and its label-read set (label_rank_5/10/21)
# is a strict superset of what any B0-B2 candidate needs (label_rank_5
# alone), so one loader covers every experiment_id below.
B2_FEATURE_COLUMNS = b3.B2_FEATURE_COLUMNS
B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY = b3.B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY
LABEL_COLUMN_H5 = "label_rank_5"


@dataclasses.dataclass(frozen=True)
class _RegistryEntry:
    family: str
    model_kind: str
    feature_set: str
    feature_columns: tuple[str, ...]
    label_column: str
    extra_train_columns: tuple[str, ...]
    top_k: int | None
    hedge: str
    strategy_factory: Callable[[], RankingStrategy]


def _b3_factory(feature_columns: tuple[str, ...]) -> Callable[[], GridSelectedLightGBMStrategy]:
    return lambda: GridSelectedLightGBMStrategy(feature_columns, grid=DEFAULT_GRID)


# One entry per experiment_id this round's baseline chain / B3 grid can
# produce (see run_baseline_chain.py / run_b3_grid.py's own config lists --
# this mirrors those, it does not invent new ones). A "_next_open" suffix on
# the CLI arg is stripped before this lookup (next_open only changes
# ExperimentConfig.execution, never the model/features/label).
_REGISTRY: dict[str, _RegistryEntry] = {
    "step11_b0_equal_weight_universe": _RegistryEntry(
        family="step11_baseline_chain",
        model_kind="b0_equal_weight",
        feature_set="daily_only",
        feature_columns=("momentum_252_21",),
        label_column=LABEL_COLUMN_H5,
        extra_train_columns=(),
        top_k=None,
        hedge="spy_beta_hedge",
        strategy_factory=EqualWeightUniverseStrategy,
    ),
    "step11_b1_momentum_top50": _RegistryEntry(
        family="step11_baseline_chain",
        model_kind="b1_momentum",
        feature_set="daily_only",
        feature_columns=("momentum_252_21",),
        label_column=LABEL_COLUMN_H5,
        extra_train_columns=(),
        top_k=50,
        hedge="spy_beta_hedge",
        strategy_factory=MomentumFactorStrategy,
    ),
    "step11_b2_ridge_top50": _RegistryEntry(
        family="step11_baseline_chain",
        model_kind="ridge_regressor",
        feature_set="daily_only",
        feature_columns=B2_FEATURE_COLUMNS,
        label_column=LABEL_COLUMN_H5,
        extra_train_columns=(),
        top_k=50,
        hedge="spy_beta_hedge",
        strategy_factory=lambda: RidgeRankStrategy(B2_FEATURE_COLUMNS, LABEL_COLUMN_H5, alpha=1.0),
    ),
    "step11_b2_ridge_top50_daily_plus_intraday": _RegistryEntry(
        family="step11_baseline_chain",
        model_kind="ridge_regressor",
        feature_set="daily_plus_intraday",
        feature_columns=B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY,
        label_column=LABEL_COLUMN_H5,
        extra_train_columns=(),
        top_k=50,
        hedge="spy_beta_hedge",
        strategy_factory=lambda: RidgeRankStrategy(
            B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY, LABEL_COLUMN_H5, alpha=1.0
        ),
    ),
    "step11_b2_ridge_top50_rebalance_dates": _RegistryEntry(
        family="step11_baseline_chain",
        model_kind="ridge_regressor",
        feature_set="daily_only",
        feature_columns=B2_FEATURE_COLUMNS,
        label_column=LABEL_COLUMN_H5,
        extra_train_columns=(),
        top_k=50,
        hedge="spy_beta_hedge",
        strategy_factory=lambda: RidgeRankStrategy(B2_FEATURE_COLUMNS, LABEL_COLUMN_H5, alpha=1.0),
    ),
    "step11_b2_ridge_top50_daily_plus_intraday_rebalance_dates": _RegistryEntry(
        family="step11_baseline_chain",
        model_kind="ridge_regressor",
        feature_set="daily_plus_intraday",
        feature_columns=B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY,
        label_column=LABEL_COLUMN_H5,
        extra_train_columns=(),
        top_k=50,
        hedge="spy_beta_hedge",
        strategy_factory=lambda: RidgeRankStrategy(
            B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY, LABEL_COLUMN_H5, alpha=1.0
        ),
    ),
    "step11_b3_lightgbm_grid_daily_only": _RegistryEntry(
        family="step11_baseline_chain",
        model_kind="lightgbm_grid_selected",
        feature_set="daily_only",
        feature_columns=B2_FEATURE_COLUMNS,
        label_column=b3.PRIMARY_LABEL_COLUMN,
        extra_train_columns=b3.EXTRA_LABEL_COLUMNS,
        top_k=50,
        hedge="spy_beta_hedge",
        strategy_factory=_b3_factory(B2_FEATURE_COLUMNS),
    ),
    "step11_b3_lightgbm_grid_daily_plus_intraday": _RegistryEntry(
        family="step11_baseline_chain",
        model_kind="lightgbm_grid_selected",
        feature_set="daily_plus_intraday",
        feature_columns=B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY,
        label_column=b3.PRIMARY_LABEL_COLUMN,
        extra_train_columns=b3.EXTRA_LABEL_COLUMNS,
        top_k=50,
        hedge="spy_beta_hedge",
        strategy_factory=_b3_factory(B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY),
    ),
}


def _base_experiment_id(experiment_id: str) -> str:
    """Strip the "_next_open" suffix run_b3_grid.py's --execution next_open
    adds (see its module docstring) -- next_open only changes
    ExperimentConfig.execution, never which model/features/label the
    registry above looks up.
    """
    return (
        experiment_id[: -len("_next_open")]
        if experiment_id.endswith("_next_open")
        else experiment_id
    )


def _find_ledger_record(experiment_id: str) -> dict[str, Any]:
    if not LEDGER_PATH.exists():
        raise SystemExit(f"ledger not found: {LEDGER_PATH}")
    matches = []
    for line in LEDGER_PATH.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("experiment_id") == experiment_id:
            matches.append(record)
    if not matches:
        raise SystemExit(
            f"no ledger record for experiment_id={experiment_id!r} in {LEDGER_PATH} "
            "-- run the experiment first (run_baseline_chain.py / run_b3_grid.py)"
        )
    # Last write wins if an id was ever (re)recorded under a different
    # config_hash (_append_ledger only dedups identical config_hash+family
    # pairs -- see loop.py); most recent is the most likely intent.
    return matches[-1]


def _build_config(
    experiment_id: str, record: dict[str, Any], entry: _RegistryEntry
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=experiment_id,
        family=record.get("family", entry.family),
        model_kind=record.get("model_kind", entry.model_kind),
        feature_set=record.get("feature_set", entry.feature_set),
        label_horizon_days=record["label_horizon_days"],
        feature_columns=entry.feature_columns,
        top_k=record.get("top_k", entry.top_k),
        hedge=record.get("hedge", entry.hedge),
        # Older ledger records predate these two fields (added 2026-09-08);
        # loop.py's ExperimentConfig defaulted to "all"/"close_marked" then,
        # so a missing key means exactly that, not an unknown value.
        train_row_dates=record.get("train_row_dates", "all"),
        execution=record.get("execution", "close_marked"),
        hyperparameters=record.get("hyperparameters", {}),
        test_years=tuple(record["test_years"]),
    )


def _build_full_history_train_frame(
    panel: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    label_column: str,
    extra_train_columns: Sequence[str],
    train_row_dates: str,
) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Same narrow-column-mask approach as loop.py::build_weight_schedule
    (see its comment for why: avoid a full-width ``panel.loc[mask]`` copy),
    but for a single "deploy" window covering *all* history in ``panel``
    rather than one anchored+embargoed walk-forward year. No explicit
    embargo cutoff is needed: rows near the end of the panel that don't yet
    have a resolved forward label already come back NaN from the label
    builder (label_rank_h needs h future trading days that don't exist yet
    for the most recent h-1 days), and the same ``notna()`` mask every
    walk-forward fit already applies drops them here too -- this is not a
    separate mechanism, it is the existing one applied to a window with no
    upper date bound instead of an embargoed one.
    """
    trading_calendar = pd.DatetimeIndex(sorted(panel["trade_date"].unique()))
    required_columns = [*feature_columns, label_column]
    train_mask = pd.Series(True, index=panel.index)
    if train_row_dates == "rebalance_dates":
        rebalance_dates = pd.DatetimeIndex(loop.weekly_rebalance_dates(trading_calendar))
        train_mask &= panel["trade_date"].isin(rebalance_dates)
    elif train_row_dates != "all":
        raise ValueError(f"unknown train_row_dates {train_row_dates!r}")
    for column in required_columns:
        train_mask &= panel[column].notna()
    train_columns = [*required_columns, *extra_train_columns]
    train_frame = panel.loc[train_mask, ["trade_date", *train_columns]]
    if train_frame.empty:
        raise ValueError("full-history train frame is empty -- check feature/label coverage")
    refit_through_date = pd.Timestamp(train_frame["trade_date"].max())
    return train_frame, refit_through_date


def _gate_summary(record: dict[str, Any], key: str) -> str:
    section = record.get(key) or {}
    gate_results = section.get("gate_results") or {}
    passed = sum(1 for v in gate_results.values() if v)
    total = len(gate_results)
    verdict = "PASS" if section.get("all_gates_pass") else "fail"
    return f"{passed}/{total} gates ({verdict})"


def _write_readme(
    out_dir: Path,
    *,
    experiment_id: str,
    record: dict[str, Any],
    refit_through_date: pd.Timestamp,
) -> None:
    long_gate = _gate_summary(record, "long_only")
    neutral_gate = _gate_summary(record, "market_neutral")
    long_cagr_excess = (record.get("long_only", {}).get("metrics") or {}).get(
        "cagr_excess_vol_matched_benchmark"
    )
    honest_line = (
        f"Long-only cleared {long_gate}; market-neutral cleared {neutral_gate}. "
        + (
            f"Out-of-sample cost-adjusted excess CAGR vs. vol-matched SPY: {long_cagr_excess:.2%}. "
            if isinstance(long_cagr_excess, (int, float))
            else ""
        )
        + (
            "NOT promotion-approved -- do not route live/paper orders from this "
            "artifact without a human decision and the full promotion checklist "
            "(benchmark family, OOS/walk-forward evidence, costs, data-source "
            "sensitivity)."
        )
    )
    readme = f"""# {experiment_id}

Exported by `scripts/export_candidate_artifact.py` from
`reports/research/ledger/experiments.jsonl` (family
`{record.get("family")}`, model_kind `{record.get("model_kind")}`,
feature_set `{record.get("feature_set")}`).

- Long-only: {long_gate}
- Market-neutral: {neutral_gate}
- Refit-through date (last training row's `trade_date` in this artifact's
  full-history refit): {refit_through_date.date().isoformat()}
- Ledger record: `reports/research/ledger/experiments.jsonl`
  (`experiment_id={experiment_id}`, `config_hash={record.get("config_hash")}`)
- Tearsheet: `{record.get("tearsheet_path")}`

## One-sentence honest conclusion

{honest_line}

## Interface

`model.joblib` is a `loop.RankingStrategy`-protocol object: call
`.score(asof_frame)` with a features `DataFrame` (must include a `symbol`
column and every column named in `features.json`'s `feature_columns`) to get
back a `symbol`-indexed `pandas.Series` of scores. Caller does its own top-K
selection (`features.json`'s `top_k`) and, if `hedge == "spy_beta_hedge"`,
its own SPY beta-hedge leg sizing -- this artifact does not embed portfolio
construction, only ranking.
"""
    (out_dir / "README.md").write_text(readme)


def _find_family_ledger_record(
    experiment_id: str, family: str, *, ledger_path: Path = LEDGER_PATH
) -> dict[str, Any] | None:
    """Like ``_find_ledger_record``, scoped to a specific ``family`` (the v1
    and v2 promotion ledgers share one file; different contracts could in
    principle record a same-looking ``experiment_id`` under different
    families) -- returns ``None`` rather than raising so a rule-candidate
    export can still write an artifact (with an honest "no ledger record
    found" README note) instead of hard failing, if the source cell was
    somehow never recorded.
    """
    if not ledger_path.exists():
        return None
    matches = []
    for line in ledger_path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("experiment_id") == experiment_id and record.get("family") == family:
            matches.append(record)
    return matches[-1] if matches else None


def _render_rule_candidate_readme(
    *,
    experiment_id: str,
    source_ledger_experiment_id: str,
    record: dict[str, Any] | None,
    config_payload: dict[str, Any],
) -> str:
    """README for a rule-based (no ``model.joblib``) candidate exported by
    :func:`export_rule_candidate_artifact` -- quotes its source ledger
    record's metrics/gate results verbatim (never hand-typed, so a reader
    can trust the numbers match ``experiments.jsonl`` exactly) and is
    explicit that this exporter never decides whether a candidate is
    promotion-ready, matching :func:`_write_readme`'s v1-schema sibling for
    the registry/ML :func:`export_candidate_artifact` case.
    """
    lines = [
        f"# {experiment_id}",
        "",
        "Exported by `scripts/export_candidate_artifact.py::export_rule_candidate_artifact` "
        f"(rule-based, no `model.joblib`). Source ledger cell: `{source_ledger_experiment_id}` "
        f"(family `{config_payload.get('family')}`, `reports/research/ledger/experiments.jsonl`).",
        "",
        "## config.json summary",
        "",
        f"- `model_kind`: `{config_payload.get('model_kind')}`",
        f"- `score_expression`: `{config_payload.get('score_expression')}`",
        f"- `universe_top_n`: `{config_payload.get('universe_top_n')}`",
        f"- `top_k`: `{config_payload.get('top_k')}`",
        f"- `trend_gate`: `{config_payload.get('trend_gate')}`",
        f"- `rebalance`: `{config_payload.get('rebalance')}`",
        "- `cost_bps_per_side` / `stress_cost_bps_per_side`: "
        f"`{config_payload.get('cost_bps_per_side')}` / "
        f"`{config_payload.get('stress_cost_bps_per_side')}`",
        "",
    ]
    if record is None:
        lines += [
            "## Ledger verdict",
            "",
            f"**No ledger record found** for `{source_ledger_experiment_id}` under family "
            f"`{config_payload.get('family')}` at export time -- this artifact's config mirrors "
            "the protocol the source cell was run under, but its metrics could not be quoted "
            "here. Do not treat this as a passing or evaluated candidate.",
            "",
        ]
    else:
        metrics = record.get("metrics") or {}
        gate_results = record.get("gate_results") or {}
        gates_not_applicable = record.get("gates_not_applicable") or []
        disclosure = record.get("disclosure") or {}
        passed = sorted(name for name, ok in gate_results.items() if ok)
        failed = sorted(name for name, ok in gate_results.items() if not ok)
        lines += [
            "## Ledger verdict (verbatim from `experiments.jsonl`, config_hash "
            f"`{record.get('config_hash')}`, recorded_at `{record.get('recorded_at')}`)",
            "",
            f"- `all_gates_pass`: **`{record.get('all_gates_pass')}`**",
            f"- `promotion_eligible`: **`{record.get('promotion_eligible')}`**",
            "",
            "### Metrics",
            "",
            "| metric | value |",
            "| --- | --- |",
        ]
        for name in sorted(metrics):
            lines.append(f"| `{name}` | `{metrics[name]}` |")
        lines += [
            "",
            "### Gates",
            "",
            f"- Passed ({len(passed)}): {', '.join(f'`{name}`' for name in passed) or 'none'}",
            f"- **Failed ({len(failed)})**: {', '.join(f'`{name}`' for name in failed) or 'none'}",
            "- Not applicable: "
            f"{', '.join(f'`{name}`' for name in gates_not_applicable) or 'none'}",
            "",
        ]
        if disclosure:
            lines += ["### Disclosure-only items", "", "| item | value |", "| --- | --- |"]
            for name in sorted(disclosure):
                lines.append(f"| `{name}` | `{disclosure[name]}` |")
            lines.append("")

    lines += [
        "## One-sentence honest conclusion",
        "",
        (
            "This is a below-contract candidate (fails "
            f"`{config_payload.get('family')}`'s gates, see above) connected for **observation "
            "mode only** -- target weights and a signal log, never broker orders -- exactly like "
            "the earlier `step11_momentum_placeholder_v1` rule candidate. "
            "**NOT promotion-approved.** Do not route live/paper orders from this artifact "
            "without a human decision and the full promotion checklist (benchmark family, "
            "OOS/walk-forward evidence, costs, data-source sensitivity, sample/fallback caveats)."
        ),
        "",
        "## Interface",
        "",
        "Same candidate-artifact interface as every other export under "
        "`reports/research/candidates/` (see `config/model_ranking_candidates/"
        "step11_momentum_placeholder_v1/README.md` for the full contract): `config.json` + "
        "`features.json`, **no `model.joblib`** (nothing to fit -- a two-column ratio rule needs "
        "no training). `open_composer.adapters.execution.model_ranking_target_weights."
        "load_candidate_artifact` reads `config.json:model_kind=rule_derived_ratio_top_k` + "
        "`score_expression` to rank the universe on `numerator/denominator` directly, and, if "
        "`config.json:trend_gate` is set, routes the whole book to `trend_gate.cash_symbol` on "
        "weeks the benchmark closes below its trailing SMA.",
        "",
    ]
    return "\n".join(lines)


def export_rule_candidate_artifact(
    experiment_id: str,
    *,
    source_ledger_experiment_id: str,
    score_expression: dict[str, str],
    universe_top_n: int,
    top_k: int,
    trend_gate: dict[str, Any] | None,
    ledger_family: str = "step13_recent_high_return",
    feature_set: str = "daily27",
    rebalance: str = "weekly_friday_signal_next_session_open",
    cost_bps_per_side: float = 10.0,
    stress_cost_bps_per_side: float = 25.0,
    label_horizon_days: int = 5,
    out_root: Path = CANDIDATES_ROOT,
    ledger_path: Path = LEDGER_PATH,
) -> Path:
    """Rule-based (no ``model.joblib``) candidate export for a derived
    risk-adjusted score, e.g. ``momentum_252_21/vol_63`` -- the Step 13
    Track M product path
    (``open_composer/adapters/execution/model_ranking_target_weights.py``'s
    ``score_expression``/``trend_gate`` support). Unlike
    :func:`export_candidate_artifact` (registry-driven ML refit), there is
    nothing to fit: this generalizes the "a rule needs no training"
    convention ``config/model_ranking_candidates/
    step11_momentum_placeholder_v1`` already established, from a single
    ``score_column`` to a two-column ratio plus an optional trend gate.
    ``source_ledger_experiment_id`` (the research grid's own cell id, e.g.
    ``step13_m0b_mom_over_vol63_uni500_k50_gate_off``) may differ from
    ``experiment_id`` (this artifact's own, product-facing directory name)
    -- the README quotes that source cell's ledger verdict verbatim.
    """
    numerator = score_expression["numerator"]
    denominator = score_expression["denominator"]
    record = _find_family_ledger_record(
        source_ledger_experiment_id, ledger_family, ledger_path=ledger_path
    )
    feature_columns = [numerator, denominator]

    config_payload: dict[str, Any] = {
        "experiment_id": experiment_id,
        "source_ledger_experiment_id": source_ledger_experiment_id,
        "family": ledger_family,
        "model_kind": "rule_derived_ratio_top_k",
        "feature_set": feature_set,
        "label_horizon_days": label_horizon_days,
        "feature_columns": feature_columns,
        "score_expression": {"numerator": numerator, "denominator": denominator},
        "top_k": top_k,
        "universe_top_n": universe_top_n,
        "hedge": "none",
        "train_row_dates": "rule_based_no_training",
        "rebalance": rebalance,
        "weighting": "equal_weight",
        "cost_bps_per_side": cost_bps_per_side,
        "stress_cost_bps_per_side": stress_cost_bps_per_side,
        "trend_gate": trend_gate,
        "hyperparameters": {},
    }
    features_payload = {
        "experiment_id": experiment_id,
        "family": ledger_family,
        "model_kind": "rule_derived_ratio_top_k",
        "feature_set": feature_set,
        "feature_columns": feature_columns,
        "label_column": "label_rank_5",
        "label_horizon_days": label_horizon_days,
        "top_k": top_k,
        "hedge": "none",
        "train_row_dates": "rule_based_no_training",
        "execution": "next_open",
        "refit_through_date": None,
    }

    out_dir = out_root / experiment_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(config_payload, indent=2, default=str))
    (out_dir / "features.json").write_text(json.dumps(features_payload, indent=2, default=str))
    (out_dir / "README.md").write_text(
        _render_rule_candidate_readme(
            experiment_id=experiment_id,
            source_ledger_experiment_id=source_ledger_experiment_id,
            record=record,
            config_payload=config_payload,
        )
    )
    print(f"wrote {out_dir}", flush=True)
    return out_dir


def export_candidate_artifact(experiment_id: str, *, out_root: Path = CANDIDATES_ROOT) -> Path:
    base_id = _base_experiment_id(experiment_id)
    if base_id not in _REGISTRY:
        known = sorted(_REGISTRY)
        raise SystemExit(
            f"no registry entry for {base_id!r} (from {experiment_id!r}); known: {known}"
        )
    entry = _REGISTRY[base_id]
    record = _find_ledger_record(experiment_id)
    config = _build_config(experiment_id, record, entry)

    print(f"loading {config.feature_set} panel ...", flush=True)
    # dates=None -- every trading day, matching what the old (now-removed)
    # b3._load_panel returned; _build_full_history_train_frame below still
    # does its own train_row_dates filtering (rebalance-only vs. every day),
    # so the loader here must not pre-filter to rebalance days itself (that
    # would silently break every "all"-row candidate, i.e. every B0-B2
    # export -- see run_b3_grid.py's 2026-09-09 memory-lean rewrite, which
    # *can* pre-filter because its own caller only ever wants rebalance
    # rows). include_prices=False: this refit path never touches open/close.
    label_columns = list(dict.fromkeys([entry.label_column, *entry.extra_train_columns]))
    panel = load_feature_panel(
        list(entry.feature_columns),
        label_columns,
        dates=None,
        include_prices=False,
        daily_root=b3.DAILY_FEATURES_ROOT,
        labels_root=b3.LABELS_ROOT,
    )

    train_frame, refit_through_date = _build_full_history_train_frame(
        panel,
        feature_columns=entry.feature_columns,
        label_column=entry.label_column,
        extra_train_columns=entry.extra_train_columns,
        train_row_dates=config.train_row_dates,
    )
    print(
        f"refitting {config.model_kind} on {len(train_frame)} rows through "
        f"{refit_through_date.date()} ...",
        flush=True,
    )
    strategy = entry.strategy_factory()
    strategy.fit(train_frame)

    out_dir = out_root / experiment_id
    out_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(strategy, out_dir / "model.joblib")

    features_payload = {
        "experiment_id": experiment_id,
        "family": config.family,
        "model_kind": config.model_kind,
        "feature_set": config.feature_set,
        "feature_columns": list(entry.feature_columns),
        "label_column": entry.label_column,
        "label_horizon_days": config.label_horizon_days,
        "top_k": config.top_k,
        "hedge": config.hedge,
        "train_row_dates": config.train_row_dates,
        "execution": config.execution,
        "refit_through_date": refit_through_date.date().isoformat(),
    }
    (out_dir / "features.json").write_text(json.dumps(features_payload, indent=2))

    config_payload = dataclasses.asdict(config)
    (out_dir / "config.json").write_text(json.dumps(config_payload, indent=2, default=str))

    _write_readme(
        out_dir, experiment_id=experiment_id, record=record, refit_through_date=refit_through_date
    )

    print(f"wrote {out_dir}", flush=True)
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "experiment_id", help="a ledgered experiment_id, e.g. step11_b1_momentum_top50"
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=CANDIDATES_ROOT,
        help="override reports/research/candidates/ (mainly for tests)",
    )
    parser.add_argument(
        "--rule",
        action="store_true",
        help=(
            "export a rule-based derived-ratio candidate (no model.joblib) instead of "
            "refitting a registry ML experiment_id -- see export_rule_candidate_artifact"
        ),
    )
    parser.add_argument(
        "--source-ledger-experiment-id",
        help="--rule only: the research grid's ledger experiment_id to quote in the README",
    )
    parser.add_argument("--score-numerator", help="--rule only: score_expression.numerator")
    parser.add_argument("--score-denominator", help="--rule only: score_expression.denominator")
    parser.add_argument("--universe-top-n", type=int, help="--rule only")
    parser.add_argument("--top-k", type=int, help="--rule only")
    parser.add_argument("--ledger-family", default="step13_recent_high_return", help="--rule only")
    parser.add_argument(
        "--trend-gate", action="store_true", help="--rule only: enable the SMA trend gate"
    )
    parser.add_argument("--trend-gate-benchmark", default="SPY", help="--rule only")
    parser.add_argument("--trend-gate-sma-days", type=int, default=200, help="--rule only")
    parser.add_argument("--trend-gate-cash-symbol", default="BIL", help="--rule only")
    args = parser.parse_args()
    if args.rule:
        required = (
            ("--source-ledger-experiment-id", args.source_ledger_experiment_id),
            ("--score-numerator", args.score_numerator),
            ("--score-denominator", args.score_denominator),
            ("--universe-top-n", args.universe_top_n),
            ("--top-k", args.top_k),
        )
        missing = [name for name, value in required if value is None]
        if missing:
            parser.error(f"--rule requires {', '.join(missing)}")
        trend_gate = (
            {
                "benchmark": args.trend_gate_benchmark,
                "sma_days": args.trend_gate_sma_days,
                "cash_symbol": args.trend_gate_cash_symbol,
            }
            if args.trend_gate
            else None
        )
        export_rule_candidate_artifact(
            args.experiment_id,
            source_ledger_experiment_id=args.source_ledger_experiment_id,
            score_expression={
                "numerator": args.score_numerator,
                "denominator": args.score_denominator,
            },
            universe_top_n=args.universe_top_n,
            top_k=args.top_k,
            trend_gate=trend_gate,
            ledger_family=args.ledger_family,
            out_root=args.out_root,
        )
        return 0
    export_candidate_artifact(args.experiment_id, out_root=args.out_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
