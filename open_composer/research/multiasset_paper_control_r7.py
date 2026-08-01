from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.research.multiasset_forward_multimodal_r5 import (
    RANKABLE_SYMBOLS,
    RESERVE_SYMBOL,
    PanelData,
    _canonical_json_bytes,
    _target_from_symbols,
    _top_symbols,
    build_monthly_feature_dataset,
    build_point_in_time_features,
    canonical_target_bytes,
    canonical_target_hash,
    simulate_exact_target_portfolio,
)
from open_composer.research.multiasset_forward_multimodal_r6 import (
    SPEC_PATHS as R6_SPEC_PATHS,
)
from open_composer.research.multiasset_forward_multimodal_r6 import (
    build_candidate_targets_for_segment as build_r6_candidate_targets,
)
from open_composer.research.multiasset_forward_multimodal_r6 import (
    load_r6_panels,
)
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_multiasset_paper_control_r7"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
DATA_DIR = Path("data/research/alpaca_multiasset_forward_pc_r7")
ADAPTER_PATH = Path(
    "open_composer/adapters/execution/multiasset_paper_control_r7_target_weights.py"
)
RESEARCH_PATH = Path("open_composer/research/multiasset_paper_control_r7.py")
R7_TO_R6 = {
    "R7D01": "R6D01",
    "R7D02": "R6D02",
    "R7M01": "R6M01",
    "R7M02": "R6M02",
    "R7L01": "R6L01",
    "R7C01": "R6C01",
    "R7F01": "R6F01",
    "R7P01": "R6P01",
}
SPEC_PATHS = {
    candidate_id: Path(
        "strategy_specs/drafts/"
        f"us_multiasset_paper_control_r7_{candidate_id.removeprefix('R7').lower()}.yaml"
    )
    for candidate_id in R7_TO_R6
}
SHADOW_IDS = frozenset(set(SPEC_PATHS) - {"R7D01"})
TRAIN_START_SESSION = "2018-02-01"
EVALUATION_START_SESSION = "2021-01-04"
PRIMARY_COST_BPS = 10.0
STRESS_COST_BPS = 20.0
SEVERE_COST_BPS = 35.0


@dataclass(frozen=True)
class R7FamilyComputation:
    targets: dict[str, pd.DataFrame]
    target_records: list[dict[str, Any]]
    model_records: list[dict[str, Any]]
    target_series_sha256: dict[str, str]

    @property
    def latest_records(self) -> dict[str, dict[str, Any]]:
        return {
            candidate_id: max(
                (row for row in self.target_records if row["candidate_id"] == candidate_id),
                key=lambda row: str(row["execution_session"]),
            )
            for candidate_id in SPEC_PATHS
        }


@dataclass(frozen=True)
class R7FreezeResult:
    preregistration_lock_path: Path
    runner_lock_path: Path
    lock_anchor_path: Path
    lock_anchor_sha256: str


@dataclass(frozen=True)
class R7EvaluationResult:
    evaluation_path: Path
    receipt_path: Path
    payload: dict[str, Any]


def load_r7_specs(root: Path) -> dict[str, StrategySpec]:
    base = root.resolve()
    return {
        candidate_id: load_strategy_spec(base / path) for candidate_id, path in SPEC_PATHS.items()
    }


def load_r6_source_specs(root: Path) -> dict[str, StrategySpec]:
    base = root.resolve()
    return {
        candidate_id: load_strategy_spec(base / path)
        for candidate_id, path in R6_SPEC_PATHS.items()
    }


def validate_r7_specs(
    specs: dict[str, StrategySpec],
    source_specs: dict[str, StrategySpec],
    *,
    root: Path | None = None,
) -> None:
    if set(specs) != set(SPEC_PATHS) or set(source_specs) != set(R6_SPEC_PATHS):
        raise ValueError("R7 requires exactly eight R7 specs and eight frozen R6 source specs")

    expected_universe = {RESERVE_SYMBOL, *RANKABLE_SYMBOLS}
    for candidate_id, spec in specs.items():
        notes = spec.notes.model_dump(mode="json")
        expected_top_n = 13 if candidate_id == "R7D01" else 3
        checks = {
            "candidate_id": notes.get("candidate_id") == candidate_id,
            "daily": spec.timeframe == "daily",
            "draft": spec.lifecycle == "draft",
            "long_only": spec.position_direction == "long_only",
            "universe": set(spec.universe) == expected_universe,
            "portfolio_mode": spec.portfolio.mode == "cross_sectional_momentum",
            "execution_profile": spec.portfolio.cross_sectional_execution_profile
            == "monthly_equal_weight_bil_reserve",
            "entry_only": spec.portfolio.position_weight_enforcement == "entry_only",
            "month_end": spec.portfolio.rebalance_schedule == "calendar_month_end",
            "equal_weight": spec.portfolio.weighting == "equal_weight",
            "reserve": spec.portfolio.reserve_symbol == RESERVE_SYMBOL,
            "top_n": spec.portfolio.max_symbols_per_day == expected_top_n,
            "manual_signal": spec.execution.mode == "manual_signal",
            "broker_none": spec.execution.broker == "none",
            "decision_close": spec.execution.signal_on == "bar_close",
            "next_open": spec.execution.fill_assumption == "next_bar_open",
            "primary_cost": spec.costs.slippage_bps == PRIMARY_COST_BPS,
            "snapshot": spec.data_assumptions is not None
            and spec.data_assumptions.snapshot_manifest_path
            == (DATA_DIR / "snapshot-manifest.json").as_posix(),
            "no_order_authority": notes.get("order_authority") is False,
            "no_broker_writes": notes.get("broker_writes") is False,
        }
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            raise ValueError(f"R7 StrategySpec contract mismatch for {candidate_id}: {failed}")

        source = source_specs[R7_TO_R6[candidate_id]]
        source_model = source.model.model_dump(mode="json") if source.model else None
        current_model = spec.model.model_dump(mode="json") if spec.model else None
        source_factors = {
            name: factor.model_dump(mode="json") for name, factor in source.factors.items()
        }
        current_factors = {
            name: factor.model_dump(mode="json") for name, factor in spec.factors.items()
        }
        if source_model != current_model or source_factors != current_factors:
            raise ValueError(f"R7 frozen R6 method parity failed for {candidate_id}")

    if specs["R7F01"].model != specs["R7M01"].model:
        raise ValueError("R7F01 must declare the exact R7M01 model contract")
    if specs["R7M02"].model is None or specs["R7M02"].model.selection.threshold != 0.55:
        raise ValueError("R7M02 must retain the frozen 0.55 threshold")

    if root is not None:
        manifest = _load_json(root.resolve() / ITERATION_DIR / "candidate-manifest.json")
        hashes = manifest.get("spec_hashes")
        if not isinstance(hashes, dict) or len(hashes) != len(SPEC_PATHS):
            raise ValueError("R7 candidate manifest spec inventory is incomplete")
        for candidate_id, path in SPEC_PATHS.items():
            if hashes.get(path.as_posix()) != strategy_content_hash(specs[candidate_id]):
                raise ValueError(f"R7 candidate manifest semantic hash mismatch: {candidate_id}")


def load_r7_panels(
    root: Path,
    manifest_path: Path,
    *,
    expected_manifest_sha256: str,
) -> dict[str, PanelData]:
    return load_r6_panels(
        root.resolve(),
        manifest_path,
        expected_manifest_sha256=expected_manifest_sha256,
    )


def compute_r7_family_targets(
    panel: PanelData,
    specs: dict[str, StrategySpec],
    source_specs: dict[str, StrategySpec],
    *,
    execution_start: str | None = None,
    execution_end: str | None = None,
    train_start_session: str = TRAIN_START_SESSION,
    provenance: dict[str, str] | None = None,
) -> R7FamilyComputation:
    validate_r7_specs(specs, source_specs)
    features = build_point_in_time_features(
        panel.close,
        panel.volume,
        formula_spec=specs["R7C01"],
    )
    dataset = build_monthly_feature_dataset(
        panel,
        features,
        placebo_spec=specs["R7P01"],
        rebalance_schedule="calendar_month_end",
    )
    latest_panel_session = pd.Timestamp(panel.close.index.max()).date().isoformat()
    points = (
        dataset[dataset["execution_session"] <= latest_panel_session][
            ["execution_position", "execution_session"]
        ]
        .drop_duplicates()
        .sort_values("execution_position")
    )
    if execution_start is not None:
        points = points[points["execution_session"] >= execution_start]
    if execution_end is not None:
        points = points[points["execution_session"] <= execution_end]
    if points.empty:
        raise ValueError("R7 panel has no completed monthly execution point")
    if execution_start is None and execution_end is None:
        points = points.tail(2)

    start = str(points["execution_session"].iloc[0])
    end = str(points["execution_session"].iloc[-1])
    source_frames, source_target_records, source_model_records, _ = build_r6_candidate_targets(
        dataset,
        segment_id="R7_FIXED_REPLAY",
        execution_start=start,
        execution_end=end,
        train_start_session=train_start_session,
        columns=panel.open.columns,
        specs=source_specs,
        provenance=provenance or {},
    )
    source_records = {
        (str(row["candidate_id"]), str(row["execution_session"])): row
        for row in source_target_records
    }
    target_rows: dict[str, list[pd.Series]] = {candidate_id: [] for candidate_id in SPEC_PATHS}
    target_records: list[dict[str, Any]] = []
    target_index = source_frames["R6D01"].index

    for execution_timestamp in target_index:
        execution_session = pd.Timestamp(execution_timestamp).date().isoformat()
        source_d01 = source_records[("R6D01", execution_session)]
        decision_session = str(source_d01["decision_session"])
        current = dataset[dataset["decision_session"] == decision_session].sort_values("symbol")
        if set(current["symbol"]) != set(RANKABLE_SYMBOLS):
            raise ValueError(f"R7 rankable symbol coverage failed: {decision_session}")

        d01 = pd.Series(0.0, index=panel.open.columns, dtype=float)
        d01.loc[list(RANKABLE_SYMBOLS)] = 1.0 / len(RANKABLE_SYMBOLS)
        d01_symbols = list(RANKABLE_SYMBOLS)

        eligible_d02 = current[
            np.isfinite(current["raw_mom_126_skip21"])
            & np.isfinite(current["raw_trend_gap_252"])
            & (current["raw_trend_gap_252"] > 0.0)
        ]
        d02_symbols = _top_symbols(eligible_d02, "raw_mom_126_skip21", 3)
        if len(d02_symbols) == 3:
            d02 = _target_from_symbols(d02_symbols, panel.open.columns)
            d02_fallback = None
        else:
            d02 = d01.copy()
            d02_symbols = d01_symbols
            d02_fallback = "fewer_than_three_positive_trend_symbols"

        def source_target(
            candidate_id: str,
            current_timestamp: pd.Timestamp = execution_timestamp,
            current_session: str = execution_session,
        ) -> tuple[pd.Series, dict[str, Any]]:
            source_id = R7_TO_R6[candidate_id]
            return (
                source_frames[source_id].loc[current_timestamp].astype(float).copy(),
                source_records[(source_id, current_session)],
            )

        m01_source, m01_record = source_target("R7M01")
        if m01_record.get("fallback_reason"):
            m01 = d01.copy()
            m01_symbols = d01_symbols
            m01_fallback = str(m01_record["fallback_reason"])
        else:
            m01 = m01_source
            m01_symbols = list(map(str, m01_record["selected_symbols"]))
            m01_fallback = None

        l01_source, l01_record = source_target("R7L01")
        if l01_record.get("fallback_reason"):
            l01 = d01.copy()
            l01_symbols = d01_symbols
            l01_fallback = str(l01_record["fallback_reason"])
        else:
            l01 = l01_source
            l01_symbols = list(map(str, l01_record["selected_symbols"]))
            l01_fallback = None

        derived: dict[str, tuple[pd.Series, list[str], str | None]] = {}
        for candidate_id in ("R7M02", "R7C01", "R7P01"):
            source, record = source_target(candidate_id)
            reason = record.get("fallback_reason")
            if reason:
                target = m01.copy()
                symbols = m01_symbols
                reason_text = str(reason).replace("R6M01", "R7M01")
            else:
                target = source
                symbols = list(map(str, record["selected_symbols"]))
                reason_text = None
            derived[candidate_id] = (target, symbols, reason_text)

        candidates = {
            "R7D01": (d01, d01_symbols, None),
            "R7D02": (d02, d02_symbols, d02_fallback),
            "R7M01": (m01, m01_symbols, m01_fallback),
            "R7M02": derived["R7M02"],
            "R7L01": (l01, l01_symbols, l01_fallback),
            "R7C01": derived["R7C01"],
            "R7F01": (m01.copy(), m01_symbols, "intentional_missing_modality_identity"),
            "R7P01": derived["R7P01"],
        }
        for candidate_id, (target, selected_symbols, fallback_reason) in candidates.items():
            _validate_target(target, candidate_id)
            weights = {symbol: float(target[symbol]) for symbol in sorted(target.index)}
            target_rows[candidate_id].append(target)
            target_records.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "candidate_id": candidate_id,
                    "segment_id": "R7_FIXED_REPLAY",
                    "decision_session": decision_session,
                    "execution_session": execution_session,
                    "selected_symbols": list(map(str, selected_symbols)),
                    "weights": weights,
                    "target_sha256": _target_hash(weights),
                    "fallback_reason": fallback_reason,
                    "unexpected_model_fallback": bool(
                        candidate_id in {"R7M01", "R7M02", "R7C01", "R7P01"}
                        and fallback_reason
                        and fallback_reason
                        not in {
                            "fewer_than_three_survival_eligible_symbols",
                            "upstream_R7M01_fallback",
                        }
                    ),
                    "order_eligible_in_r7": False,
                    "broker_writes": False,
                }
            )

    targets = {
        candidate_id: pd.DataFrame(
            rows,
            index=pd.DatetimeIndex(target_index),
            columns=panel.open.columns,
        )
        for candidate_id, rows in target_rows.items()
    }
    if canonical_target_bytes(targets["R7F01"]) != canonical_target_bytes(targets["R7M01"]):
        raise ValueError("R7F01 target identity with R7M01 failed")
    expected_d01 = 1.0 / len(RANKABLE_SYMBOLS)
    if not np.allclose(
        targets["R7D01"].loc[:, list(RANKABLE_SYMBOLS)].to_numpy(dtype=float),
        expected_d01,
        atol=1e-15,
        rtol=0.0,
    ) or not np.allclose(targets["R7D01"][RESERVE_SYMBOL], 0.0, atol=1e-15, rtol=0.0):
        raise ValueError("R7D01 exact equal-weight identity failed")

    model_records = [_map_model_record(row) for row in source_model_records]
    return R7FamilyComputation(
        targets=targets,
        target_records=target_records,
        model_records=model_records,
        target_series_sha256={
            candidate_id: canonical_target_hash(frame) for candidate_id, frame in targets.items()
        },
    )


def freeze_multiasset_paper_control_r7(root: Path) -> R7FreezeResult:
    base = root.resolve()
    iteration = base / ITERATION_DIR
    lock_dir = iteration / "lock-set"
    if lock_dir.exists():
        raise ValueError("R7 lock set already exists")
    if (iteration / "evaluation-run").exists():
        raise ValueError("R7 evaluation exists before the implementation lock")
    dossier = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not dossier.ok:
        raise ValueError("R7 pre-backtest dossier is blocked: " + ", ".join(dossier.blocked))
    specs = load_r7_specs(base)
    source_specs = load_r6_source_specs(base)
    validate_r7_specs(specs, source_specs, root=base)
    if not (base / ADAPTER_PATH).is_file():
        raise ValueError("R7 target-weight adapter must exist before locking")

    iteration_artifacts = [
        _binding(path, base) for path in sorted(iteration.iterdir()) if path.is_file()
    ]
    source_cards = base / "reports/harness/source_cards/us_multiasset_paper_control_r7.jsonl"
    preregistration = {
        "schema_version": 1,
        "lock_contract": "multiasset_paper_control_r7_preregistration_v1",
        "iter_id": ITER_ID,
        "status": "contracts_locked_before_first_r7_target_calculation",
        "created_at": datetime.now(UTC).isoformat(),
        "forward_epoch": "2026-08-03",
        "forward_count_start": 0,
        "backfill_allowed": False,
        "iteration_artifacts": iteration_artifacts,
        "source_cards": _binding(source_cards, base),
        "specs": [
            {
                "candidate_id": candidate_id,
                **_binding(base / path, base),
                "semantic_sha256": strategy_content_hash(specs[candidate_id]),
            }
            for candidate_id, path in SPEC_PATHS.items()
        ],
        "source_method_specs": [
            {
                "candidate_id": candidate_id,
                **_binding(base / path, base),
                "semantic_sha256": strategy_content_hash(source_specs[candidate_id]),
            }
            for candidate_id, path in R6_SPEC_PATHS.items()
        ],
        "baseline_snapshot_manifest": _binding(base / DATA_DIR / "snapshot-manifest.json", base),
        "candidate_count": 8,
        "order_candidate_ids": ["R7D01"],
        "shadow_only_candidate_ids": sorted(SHADOW_IDS),
    }
    lock_dir.mkdir(parents=True, exist_ok=False)
    prereg_path = lock_dir / "preregistration-lock.json"
    _write_json(prereg_path, preregistration)

    runner = _runner_lock_payload(base)
    runner_path = lock_dir / "runner-lock.json"
    _write_json(runner_path, runner)
    anchor_subject = {
        "iter_id": ITER_ID,
        "preregistration_lock_sha256": _sha256(prereg_path),
        "runner_lock_sha256": _sha256(runner_path),
    }
    anchor = {
        "schema_version": 1,
        "lock_contract": "multiasset_paper_control_r7_lock_anchor_v1",
        **anchor_subject,
        "lock_anchor_sha256": hashlib.sha256(_canonical_json_bytes(anchor_subject)).hexdigest(),
    }
    anchor_path = lock_dir / "lock-anchor.json"
    _write_json(anchor_path, anchor)
    return R7FreezeResult(
        preregistration_lock_path=prereg_path,
        runner_lock_path=runner_path,
        lock_anchor_path=anchor_path,
        lock_anchor_sha256=_sha256(anchor_path),
    )


def refreeze_r7_runner_lock_after_nonsemantic_fix(root: Path) -> R7FreezeResult:
    base = root.resolve()
    iteration = base / ITERATION_DIR
    lock_dir = iteration / "lock-set"
    prereg_path = lock_dir / "preregistration-lock.json"
    if not prereg_path.is_file():
        raise ValueError("R7 preregistration lock is missing")
    if (iteration / "evaluation-run").exists():
        raise ValueError("archive the failed R7 evaluation before refreezing the runner")
    forward_ledger = base / "reports/forward/us_multiasset_paper_control_r7_family/decisions.jsonl"
    if forward_ledger.exists() and forward_ledger.read_text(encoding="utf-8").strip():
        raise ValueError("R7 runner cannot be refrozen after forward receipts exist")

    prereg = _load_json(prereg_path)
    for group in ("iteration_artifacts", "specs", "source_method_specs"):
        rows = prereg.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R7 preregistration group is missing: {group}")
        for row in rows:
            _verify_binding(base, row, label=group)
    _verify_binding(base, prereg.get("source_cards"), label="source cards")
    _verify_binding(base, prereg.get("baseline_snapshot_manifest"), label="baseline snapshot")

    runner_path = lock_dir / "runner-lock.json"
    _write_json(runner_path, _runner_lock_payload(base, reset_reason="receipt_role_compatibility"))
    subject = {
        "iter_id": ITER_ID,
        "preregistration_lock_sha256": _sha256(prereg_path),
        "runner_lock_sha256": _sha256(runner_path),
    }
    anchor_path = lock_dir / "lock-anchor.json"
    _write_json(
        anchor_path,
        {
            "schema_version": 1,
            "lock_contract": "multiasset_paper_control_r7_lock_anchor_v1",
            **subject,
            "lock_anchor_sha256": hashlib.sha256(_canonical_json_bytes(subject)).hexdigest(),
            "runner_reset_reason": "receipt_role_compatibility",
            "forward_count_at_reset": 0,
        },
    )
    return R7FreezeResult(
        preregistration_lock_path=prereg_path,
        runner_lock_path=runner_path,
        lock_anchor_path=anchor_path,
        lock_anchor_sha256=_sha256(anchor_path),
    )


def refreeze_r7_runner_lock_before_forward(root: Path) -> R7FreezeResult:
    base = root.resolve()
    iteration = base / ITERATION_DIR
    lock_dir = iteration / "lock-set"
    prereg_path = lock_dir / "preregistration-lock.json"
    runner_path = lock_dir / "runner-lock.json"
    anchor_path = lock_dir / "lock-anchor.json"
    for path in (prereg_path, runner_path, anchor_path):
        if not path.is_file():
            raise ValueError(f"R7 lock file is missing: {path}")
    forward_ledger = base / "reports/forward/us_multiasset_paper_control_r7_family/decisions.jsonl"
    if forward_ledger.exists() and forward_ledger.read_text(encoding="utf-8").strip():
        raise ValueError("R7 runner cannot be refrozen after forward receipts exist")

    prereg = _load_json(prereg_path)
    for group in ("iteration_artifacts", "specs", "source_method_specs"):
        rows = prereg.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R7 preregistration group is missing: {group}")
        for row in rows:
            _verify_binding(base, row, label=group)
    _verify_binding(base, prereg.get("source_cards"), label="source cards")
    _verify_binding(base, prereg.get("baseline_snapshot_manifest"), label="baseline snapshot")

    evaluation = _load_json(iteration / "evaluation-run/evaluation-receipt.json")
    if (
        evaluation.get("iter_id") != ITER_ID
        or evaluation.get("workflow_pass") is not True
        or evaluation.get("research_pass") is not True
        or evaluation.get("paper_ready_pass") is not False
        or evaluation.get("paper_order_authorization") is not False
        or evaluation.get("broker_writes") is not False
    ):
        raise ValueError("R7 final evaluation receipt is not eligible for a pre-forward relock")

    old_anchor = _load_json(anchor_path)
    old_subject = {
        "iter_id": ITER_ID,
        "preregistration_lock_sha256": _sha256(prereg_path),
        "runner_lock_sha256": _sha256(runner_path),
    }
    if (
        any(old_anchor.get(key) != value for key, value in old_subject.items())
        or old_anchor.get("lock_anchor_sha256")
        != hashlib.sha256(_canonical_json_bytes(old_subject)).hexdigest()
    ):
        raise ValueError("R7 existing lock anchor is stale before pre-forward relock")

    attempt_dir = iteration / "lock-attempts/attempt-002"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    for source in (runner_path, anchor_path):
        destination = attempt_dir / source.name
        destination.write_bytes(source.read_bytes())
        destination.chmod(0o400)

    reason = "forward_snapshot_contract_binding"
    _write_json(
        runner_path,
        _runner_lock_payload(
            base,
            reset_reason=reason,
            reset_scope="pre_forward_snapshot_contract_hardening",
        ),
    )
    subject = {
        "iter_id": ITER_ID,
        "preregistration_lock_sha256": _sha256(prereg_path),
        "runner_lock_sha256": _sha256(runner_path),
    }
    _write_json(
        anchor_path,
        {
            "schema_version": 1,
            "lock_contract": "multiasset_paper_control_r7_lock_anchor_v1",
            **subject,
            "lock_anchor_sha256": hashlib.sha256(_canonical_json_bytes(subject)).hexdigest(),
            "previous_runner_lock_sha256": old_subject["runner_lock_sha256"],
            "previous_lock_anchor_sha256": _sha256(attempt_dir / "lock-anchor.json"),
            "runner_reset_reason": reason,
            "reset_scope": "pre_forward_snapshot_contract_hardening",
            "forward_count_at_reset": 0,
        },
    )
    return R7FreezeResult(
        preregistration_lock_path=prereg_path,
        runner_lock_path=runner_path,
        lock_anchor_path=anchor_path,
        lock_anchor_sha256=_sha256(anchor_path),
    )


def verify_r7_lock(root: Path) -> dict[str, Any]:
    base = root.resolve()
    lock_dir = base / ITERATION_DIR / "lock-set"
    prereg_path = lock_dir / "preregistration-lock.json"
    runner_path = lock_dir / "runner-lock.json"
    anchor_path = lock_dir / "lock-anchor.json"
    prereg = _load_json(prereg_path)
    runner = _load_json(runner_path)
    anchor = _load_json(anchor_path)
    if (
        prereg.get("iter_id") != ITER_ID
        or prereg.get("status") != "contracts_locked_before_first_r7_target_calculation"
    ):
        raise ValueError("R7 preregistration lock identity is invalid")
    if (
        runner.get("iter_id") != ITER_ID
        or runner.get("status") != "implementation_locked_before_first_r7_target_calculation"
    ):
        raise ValueError("R7 runner lock identity is invalid")
    for group in ("iteration_artifacts", "specs", "source_method_specs"):
        rows = prereg.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R7 preregistration binding group is missing: {group}")
        for row in rows:
            _verify_binding(base, row, label=group)
    _verify_binding(base, prereg.get("source_cards"), label="source cards")
    _verify_binding(base, prereg.get("baseline_snapshot_manifest"), label="baseline snapshot")
    files = runner.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("R7 runner file inventory is missing")
    for row in files:
        _verify_binding(base, row, label="runner file")
    subject = {
        "iter_id": ITER_ID,
        "preregistration_lock_sha256": _sha256(prereg_path),
        "runner_lock_sha256": _sha256(runner_path),
    }
    if (
        any(anchor.get(key) != value for key, value in subject.items())
        or anchor.get("lock_anchor_sha256")
        != hashlib.sha256(_canonical_json_bytes(subject)).hexdigest()
    ):
        raise ValueError("R7 lock anchor is stale")
    return {
        "preregistration": prereg,
        "runner": runner,
        "anchor": anchor,
        "hashes": {
            "preregistration_lock": _sha256(prereg_path),
            "runner_lock": _sha256(runner_path),
            "lock_anchor": _sha256(anchor_path),
        },
    }


def evaluate_multiasset_paper_control_r7(root: Path) -> R7EvaluationResult:
    base = root.resolve()
    iteration = base / ITERATION_DIR
    destination = iteration / "evaluation-run"
    if destination.exists():
        raise ValueError("R7 evaluation was already published")
    lock = verify_r7_lock(base)
    dossier = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not dossier.ok:
        raise ValueError("R7 dossier changed after lock: " + ", ".join(dossier.blocked))

    specs = load_r7_specs(base)
    source_specs = load_r6_source_specs(base)
    validate_r7_specs(specs, source_specs, root=base)
    data_contract = _load_json(iteration / "data-contract.json")
    manifest_path = base / str(data_contract["snapshot_manifest_path"])
    panels = load_r7_panels(
        base,
        manifest_path,
        expected_manifest_sha256=str(data_contract["snapshot_manifest_sha256"]),
    )
    adjusted = panels["all"]
    latest_session = pd.Timestamp(adjusted.open.index.max()).date().isoformat()
    feature_contract = _load_json(iteration / "feature-contract.json")
    computation = compute_r7_family_targets(
        adjusted,
        specs,
        source_specs,
        execution_start=EVALUATION_START_SESSION,
        execution_end=latest_session,
        provenance={
            "data_manifest_sha256": _sha256(manifest_path),
            "feature_contract_sha256": _sha256(iteration / "feature-contract.json"),
            "label_contract_sha256": _sha256(iteration / "label-contract.json"),
            "prompt_hash": str(feature_contract["llm_formula_provenance"]["prompt_hash"]),
        },
    )
    target_start = min(frame.index.min() for frame in computation.targets.values())
    target_end = pd.Timestamp(adjusted.open.index.max())
    costs = {
        "primary_10bps": PRIMARY_COST_BPS,
        "stress_20bps": STRESS_COST_BPS,
        "severe_35bps_report_only": SEVERE_COST_BPS,
    }
    candidate_metrics: dict[str, dict[str, Any]] = {}
    for candidate_id, targets in computation.targets.items():
        candidate_metrics[candidate_id] = {
            view: simulate_exact_target_portfolio(
                adjusted.open,
                targets,
                cost_bps=cost_bps,
                start=target_start,
                end=target_end,
            ).metrics
            for view, cost_bps in costs.items()
        }

    benchmark_targets = _benchmark_targets(
        computation.targets["R7D01"].index, adjusted.open.columns
    )
    benchmark_metrics = {
        benchmark_id: simulate_exact_target_portfolio(
            adjusted.open,
            targets,
            cost_bps=PRIMARY_COST_BPS,
            start=target_start,
            end=target_end,
        ).metrics
        for benchmark_id, targets in benchmark_targets.items()
    }
    single_symbol_metrics = {
        symbol: simulate_exact_target_portfolio(
            adjusted.open,
            _single_symbol_target(
                computation.targets["R7D01"].index[0], adjusted.open.columns, symbol
            ),
            cost_bps=PRIMARY_COST_BPS,
            start=target_start,
            end=target_end,
        ).metrics
        for symbol in RANKABLE_SYMBOLS
    }
    best_symbol = min(
        RANKABLE_SYMBOLS,
        key=lambda symbol: (
            -float(single_symbol_metrics[symbol]["total_return_pct"]),
            symbol,
        ),
    )
    benchmark_metrics["ex_post_best_symbol_report_only"] = {
        "selected_symbol": best_symbol,
        **single_symbol_metrics[best_symbol],
    }
    exact_d01 = all(
        math.isclose(value, 1.0 / len(RANKABLE_SYMBOLS), abs_tol=1e-15, rel_tol=0.0)
        for value in computation.targets["R7D01"].loc[:, list(RANKABLE_SYMBOLS)].to_numpy().ravel()
    ) and bool((computation.targets["R7D01"][RESERVE_SYMBOL] == 0.0).all())
    f01_identity = canonical_target_bytes(computation.targets["R7F01"]) == canonical_target_bytes(
        computation.targets["R7M01"]
    )
    fallback_counts = {
        candidate_id: sum(
            bool(row.get("fallback_reason"))
            for row in computation.target_records
            if row["candidate_id"] == candidate_id
        )
        for candidate_id in SPEC_PATHS
    }
    unexpected_fallback_counts = {
        candidate_id: sum(
            bool(row.get("unexpected_model_fallback"))
            for row in computation.target_records
            if row["candidate_id"] == candidate_id
        )
        for candidate_id in SPEC_PATHS
    }
    workflow_pass = bool(exact_d01 and f01_identity and len(computation.targets) == 8)
    research_pass = workflow_pass
    payload = {
        "schema_version": 1,
        "report_type": "multiasset_paper_control_r7_implementation_evaluation",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "decision": "continue",
        "candidate_count": 8,
        "trial_count": 8,
        "selection_scope": "preselected_D01_execution_control_no_historical_selection",
        "evaluation_scope": "implementation_replay_and_risk_context_only",
        "alpha_claim": False,
        "window": {
            "start_session": target_start.date().isoformat(),
            "end_session": target_end.date().isoformat(),
            "session_count": int(
                len(
                    adjusted.open.loc[
                        (adjusted.open.index >= target_start) & (adjusted.open.index <= target_end)
                    ]
                )
            ),
            "monthly_target_count": len(computation.targets["R7D01"]),
        },
        "cost_views_bps": costs,
        "candidate_metrics": candidate_metrics,
        "benchmark_metrics_primary_10bps": benchmark_metrics,
        "implementation_checks": {
            "candidate_count": len(computation.targets),
            "D01_exact_equal_weight_identity": exact_d01,
            "F01_exact_M01_identity": f01_identity,
            "all_specs_match_frozen_R6_methods": True,
            "all_shadows_order_prohibited": True,
            "same_snapshot_for_all_candidates": True,
            "D01_equal_weight_benchmark_identity": canonical_target_bytes(
                computation.targets["R7D01"]
            )
            == canonical_target_bytes(benchmark_targets["equal_weight_universe"]),
            "fallback_counts": fallback_counts,
            "unexpected_model_fallback_counts": unexpected_fallback_counts,
        },
        "target_series_sha256": computation.target_series_sha256,
        "forward_observation": {
            "epoch_not_before": "2026-08-03",
            "count": 0,
            "minimum_required": 20,
            "credit_from_this_evaluation": 0,
        },
        "matched_tca": {"count": 0, "minimum_required": 30, "minimum_sessions": 10},
        "workflow_pass": workflow_pass,
        "research_pass": research_pass,
        "research_pass_scope": "D01 execution-control implementation only; not Alpha",
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "paper_order_authorization": False,
        "broker_writes": False,
        "limitations": [
            "The historical window is not pristine and cannot select or promote a shadow.",
            "R6 remains stopped negative evidence.",
            "The LLM-derived inputs are frozen static formulas with no live inference.",
            "Paper readiness still requires genuine forward sessions and matched Alpaca Paper TCA.",
        ],
    }

    destination.mkdir(parents=True, exist_ok=False)
    evaluation_path = destination / "evaluation-report.json"
    _write_json(evaluation_path, payload)
    _write_json(destination / "benchmark-report.json", benchmark_metrics)
    _write_jsonl(
        destination / "trial-ledger.jsonl",
        [
            {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "trial_number": index,
                "candidate_id": candidate_id,
                "status": "completed",
                "selection_eligible": candidate_id == "R7D01",
                "order_eligible": False,
                "metrics": candidate_metrics[candidate_id],
                "target_series_sha256": computation.target_series_sha256[candidate_id],
            }
            for index, candidate_id in enumerate(SPEC_PATHS, start=1)
        ],
    )
    _write_jsonl(destination / "target-ledger.jsonl", computation.target_records)
    _write_jsonl(destination / "model-ledger.jsonl", computation.model_records)
    markdown = _evaluation_markdown(payload)
    (destination / "evaluation-report.md").write_text(markdown, encoding="utf-8")
    decision_path = destination / "decision-record.md"
    decision_path.write_text(
        f"# Decision Record: {ITER_ID}\n\n"
        "- Path: `D01 bounded execution control with seven fixed shadows`\n"
        "- Decision: continue\n"
        "- Reason: implementation replay and all fixed identity checks passed; forward "
        "and TCA gates remain outstanding.\n"
        "- Next iteration suggestion: retain the frozen family and begin genuine forward "
        "observation no earlier than 2026-08-03.\n",
        encoding="utf-8",
    )
    child_paths = {
        "evaluation": evaluation_path,
        "evaluation_markdown": destination / "evaluation-report.md",
        "decision_record": decision_path,
        "trial_ledger": destination / "trial-ledger.jsonl",
        "target_ledger": destination / "target-ledger.jsonl",
        "model_ledger": destination / "model-ledger.jsonl",
        "benchmark_report": destination / "benchmark-report.json",
    }
    children = {role: _binding(path, base) for role, path in child_paths.items()}
    receipt = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "evidence_publication_status": "complete",
        "decision": "continue",
        "workflow_pass": workflow_pass,
        "research_pass": research_pass,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "paper_order_authorization": False,
        "broker_writes": False,
        "preregistration_lock_sha256": lock["hashes"]["preregistration_lock"],
        "runner_lock_sha256": lock["hashes"]["runner_lock"],
        "lock_anchor_sha256": lock["hashes"]["lock_anchor"],
        "children": children,
    }
    receipt_path = destination / "evaluation-receipt.json"
    _write_json(receipt_path, receipt)
    return R7EvaluationResult(
        evaluation_path=evaluation_path,
        receipt_path=receipt_path,
        payload=payload,
    )


def _benchmark_targets(index: pd.DatetimeIndex, columns: pd.Index) -> dict[str, pd.DataFrame]:
    def frame(weights: dict[str, float], *, monthly: bool) -> pd.DataFrame:
        selected_index = index if monthly else pd.DatetimeIndex([index[0]])
        rows = []
        for _ in selected_index:
            row = pd.Series(0.0, index=columns, dtype=float)
            for symbol, weight in weights.items():
                row[symbol] = weight
            rows.append(row)
        return pd.DataFrame(rows, index=selected_index, columns=columns)

    sectors = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
    return {
        "same_symbol_buy_hold_SPY": frame({"SPY": 1.0}, monthly=False),
        "equal_weight_universe": frame(
            {symbol: 1.0 / len(RANKABLE_SYMBOLS) for symbol in RANKABLE_SYMBOLS},
            monthly=True,
        ),
        "market_proxy": frame({"SPY": 1.0}, monthly=False),
        "sector_theme_proxy": frame(
            {symbol: 1.0 / len(sectors) for symbol in sectors}, monthly=True
        ),
        "balanced_proxy": frame({"SPY": 0.6, "IEF": 0.4}, monthly=True),
        "cash_proxy": frame({"BIL": 1.0}, monthly=False),
    }


def _runner_lock_payload(
    root: Path,
    *,
    reset_reason: str | None = None,
    reset_scope: str | None = None,
) -> dict[str, Any]:
    implementation_paths = [
        ADAPTER_PATH,
        RESEARCH_PATH,
        Path("open_composer/adapters/data/multiasset_paper_control_r7_snapshot.py"),
        Path("open_composer/adapters/data/alpaca_snapshot.py"),
        Path("open_composer/research/multiasset_forward_multimodal_r6.py"),
        Path("open_composer/research/multiasset_forward_multimodal_r5.py"),
        Path("open_composer/adapters/execution/router_target_weights.py"),
        Path("open_composer/models/router_execution.py"),
        Path("open_composer/market_calendar.py"),
        Path("schemas/alpaca_snapshot_contract.schema.json"),
        Path("schemas/alpaca_snapshot_manifest.schema.json"),
        Path("scripts/run_r7_forward_observation.py"),
        Path("open_composer/cli.py"),
    ]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "lock_contract": "multiasset_paper_control_r7_runner_v1",
        "iter_id": ITER_ID,
        "status": "implementation_locked_before_first_r7_target_calculation",
        "created_at": datetime.now(UTC).isoformat(),
        "files": [_binding(root / path, root) for path in implementation_paths],
    }
    if reset_reason is not None:
        payload.update(
            {
                "runner_reset_reason": reset_reason,
                "reset_scope": reset_scope or "nonsemantic_evaluation_receipt_publication_only",
                "forward_count_at_reset": 0,
            }
        )
    return payload


def _single_symbol_target(session: pd.Timestamp, columns: pd.Index, symbol: str) -> pd.DataFrame:
    row = pd.Series(0.0, index=columns, dtype=float)
    row[symbol] = 1.0
    return pd.DataFrame([row], index=pd.DatetimeIndex([session]), columns=columns)


def _evaluation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {ITER_ID} implementation evaluation",
        "",
        "- Decision: continue",
        f"- Workflow pass: {str(payload['workflow_pass']).lower()}",
        f"- Research pass (execution-control scope only): {str(payload['research_pass']).lower()}",
        "- LLM contribution pass: false",
        "- Paper ready pass: false",
        "- Forward sessions: 0/20",
        "- Matched Paper TCA: 0/30 across 0/10 sessions",
        "",
        "Historical metrics below are implementation/risk context, not "
        "candidate-selection evidence.",
        "",
        "| Candidate | Annualized return | Sharpe | Max drawdown | Total return |",
        "|---|---:|---:|---:|---:|",
    ]
    for candidate_id, views in payload["candidate_metrics"].items():
        metrics = views["primary_10bps"]
        lines.append(
            f"| {candidate_id} | {metrics['annualized_return_pct']:.3f}% | "
            f"{metrics['annualized_sharpe']:.3f} | {metrics['max_drawdown_pct']:.3f}% | "
            f"{metrics['total_return_pct']:.3f}% |"
        )
    return "\n".join(lines) + "\n"


def _map_model_record(source: dict[str, Any]) -> dict[str, Any]:
    inverse = {value: key for key, value in R7_TO_R6.items()}
    candidate_id = inverse.get(str(source.get("candidate_id") or ""))
    if candidate_id is None:
        raise ValueError("R7 source model record has an unknown candidate")
    row = dict(source)
    row["iter_id"] = ITER_ID
    row["candidate_id"] = candidate_id
    if isinstance(row.get("failure_reason"), str):
        row["failure_reason"] = row["failure_reason"].replace("R6M01", "R7M01")
    row.pop("model_id", None)
    row["model_id"] = hashlib.sha256(_canonical_json_bytes(row)).hexdigest()
    return row


def _validate_target(target: pd.Series, candidate_id: str) -> None:
    values = target.to_numpy(dtype=float)
    if (
        set(target.index) != {RESERVE_SYMBOL, *RANKABLE_SYMBOLS}
        or not np.isfinite(values).all()
        or (values < -1e-12).any()
        or not math.isclose(float(values.sum()), 1.0, abs_tol=1e-9, rel_tol=0.0)
    ):
        raise ValueError(f"R7 target is incomplete: {candidate_id}")
    cap = 0.08 if candidate_id == "R7D01" else 0.34
    if any(float(target[symbol]) > cap + 1e-12 for symbol in RANKABLE_SYMBOLS):
        raise ValueError(f"R7 target exceeds the risk-asset cap: {candidate_id}")


def _target_hash(weights: dict[str, float]) -> str:
    return hashlib.sha256(_canonical_json_bytes(weights)).hexdigest()


def _binding(path: Path, root: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    relative = resolved.relative_to(root.resolve()).as_posix()
    if path.is_symlink() or not resolved.is_file():
        raise ValueError(f"R7 bound input must be a regular file: {relative}")
    content = resolved.read_bytes()
    return {
        "path": relative,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def _verify_binding(root: Path, binding: Any, *, label: str) -> None:
    if not isinstance(binding, dict):
        raise ValueError(f"R7 {label} binding is invalid")
    path = root / str(binding.get("path") or "")
    current = _binding(path, root)
    if any(current.get(key) != binding.get(key) for key in ("path", "sha256", "size_bytes")):
        raise ValueError(f"R7 {label} binding changed: {path}")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"R7 JSON artifact must be an object: {path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
