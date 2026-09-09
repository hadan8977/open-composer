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
    panel = b3._load_panel(config.feature_set)

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
    args = parser.parse_args()
    export_candidate_artifact(args.experiment_id, out_root=args.out_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
