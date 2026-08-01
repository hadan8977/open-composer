from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from open_composer import cli
from open_composer.adapters.data import multiasset_paper_control_r7_snapshot as forward_snapshot
from open_composer.adapters.execution import multiasset_paper_control_r7_target_weights as adapter
from open_composer.research.multiasset_forward_multimodal_r5 import (
    RANKABLE_SYMBOLS,
    RESERVE_SYMBOL,
    PanelData,
    canonical_target_hash,
)
from open_composer.research.multiasset_paper_control_r7 import (
    ADAPTER_PATH,
    ITERATION_DIR,
    SPEC_PATHS,
    R7FamilyComputation,
    compute_r7_family_targets,
    load_r6_source_specs,
    load_r7_panels,
    load_r7_specs,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def baseline_computation() -> R7FamilyComputation:
    manifest = ROOT / "data/research/alpaca_multiasset_forward_pc_r7/snapshot-manifest.json"
    panels = load_r7_panels(
        ROOT,
        manifest,
        expected_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
    )
    return compute_r7_family_targets(
        panels["all"],
        load_r7_specs(ROOT),
        load_r6_source_specs(ROOT),
        provenance={
            "data_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "feature_contract_sha256": "0" * 64,
            "label_contract_sha256": "1" * 64,
            "prompt_hash": "2" * 64,
        },
    )


def test_r7_family_computes_all_fixed_roles_on_one_snapshot(
    baseline_computation: R7FamilyComputation,
) -> None:
    result = baseline_computation
    assert set(result.targets) == set(SPEC_PATHS)
    assert len(result.target_records) == 16
    assert len(result.model_records) == 8

    d01 = result.targets["R7D01"]
    assert (d01[RESERVE_SYMBOL] == 0.0).all()
    assert all(
        value == pytest.approx(1.0 / len(RANKABLE_SYMBOLS), abs=1e-15)
        for value in d01.loc[:, list(RANKABLE_SYMBOLS)].to_numpy().ravel()
    )
    pd.testing.assert_frame_equal(result.targets["R7F01"], result.targets["R7M01"])
    assert result.target_series_sha256["R7F01"] == result.target_series_sha256["R7M01"]
    assert all(row["broker_writes"] is False for row in result.target_records)
    assert all(row["order_eligible_in_r7"] is False for row in result.target_records)


def test_r7_forward_rejects_pre_epoch_without_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_of = datetime(2026, 7, 31, 21, 0, tzinfo=UTC)
    monkeypatch.setattr(adapter, "_utc_now", lambda: as_of)
    with pytest.raises(ValueError, match="cannot begin before 2026-08-03"):
        adapter.run_multiasset_paper_control_r7_target_weight_mapping(
            Path("strategy_specs/drafts/us_multiasset_paper_control_r7_d01.yaml"),
            tmp_path,
            snapshot_manifest_path=Path("snapshot.json"),
            as_of=as_of,
        )
    assert not (tmp_path / "reports/forward/us_multiasset_paper_control_r7_family").exists()


def test_r7_first_forward_session_publishes_one_family_receipt_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs = load_r7_specs(ROOT)
    source_specs = load_r6_source_specs(ROOT)
    for candidate_id, relative in SPEC_PATHS.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
        assert specs[candidate_id].name in destination.read_text(encoding="utf-8")

    for relative in (
        ADAPTER_PATH,
        forward_snapshot.TEMPLATE_PATH,
        ITERATION_DIR / "feature-contract.json",
        ITERATION_DIR / "label-contract.json",
    ):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)

    session = date(2026, 8, 3)
    contract_payload = forward_snapshot.build_r7_forward_snapshot_contract(tmp_path, session)
    contract_path = tmp_path / forward_snapshot._contract_relative_path(session)
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps(contract_payload), encoding="utf-8")
    manifest_payload = {
        "contract_path": forward_snapshot._contract_relative_path(session).as_posix(),
        "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "output_root": forward_snapshot._snapshot_relative_dir(session).as_posix(),
        "retrieved_at": "2026-08-03T20:30:00+00:00",
        "items": [
            {
                "symbol": symbol,
                "adjustment": adjustment,
                "quality": {"complete_sessions": ["2026-08-03"]},
            }
            for adjustment in ("raw", "split", "dividend", "all")
            for symbol in (RESERVE_SYMBOL, *RANKABLE_SYMBOLS)
        ],
    }
    manifest_path = tmp_path / "snapshot.json"
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    panel_index = pd.DatetimeIndex(["2026-07-31", "2026-08-03"])
    columns = pd.Index(sorted((RESERVE_SYMBOL, *RANKABLE_SYMBOLS)))
    values = pd.DataFrame(100.0, index=panel_index, columns=columns)
    panel = PanelData(
        open=values,
        high=values,
        low=values,
        close=values,
        volume=values,
        manifest=manifest_payload,
    )
    computation = _fake_computation(columns)
    lock = {
        "hashes": {
            "preregistration_lock": "a" * 64,
            "runner_lock": "b" * 64,
            "lock_anchor": "c" * 64,
            "evaluation_receipt": "d" * 64,
        }
    }
    monkeypatch.setattr(adapter, "_require_locked_family", lambda *_: (specs, source_specs, lock))
    monkeypatch.setattr(adapter, "load_r7_panels", lambda *_args, **_kwargs: {"all": panel})
    monkeypatch.setattr(adapter, "compute_r7_family_targets", lambda *_args, **_kwargs: computation)
    as_of = datetime(2026, 8, 3, 21, 0, tzinfo=UTC)
    monkeypatch.setattr(adapter, "_utc_now", lambda: as_of)

    kwargs = {
        "snapshot_manifest_path": manifest_path,
        "as_of": as_of,
    }
    spec_path = tmp_path / SPEC_PATHS["R7D01"]
    first = adapter.run_multiasset_paper_control_r7_target_weight_mapping(
        spec_path, tmp_path, **kwargs
    )
    second = adapter.run_multiasset_paper_control_r7_target_weight_mapping(
        spec_path, tmp_path, **kwargs
    )

    assert first.receipt_path == second.receipt_path
    assert first.market_session == "2026-08-03"
    assert first.valid_session_count == 1
    assert first.forward_observation_pass is False
    ledger = first.forward_ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(ledger) == 1
    receipt = json.loads(first.receipt_path.read_text(encoding="utf-8"))
    assert set(receipt["candidate_targets"]) == set(SPEC_PATHS)
    assert (
        receipt["candidate_targets"]["R7F01"]["weights"]
        == receipt["candidate_targets"]["R7M01"]["weights"]
    )
    assert receipt["paper_order_authorization"] is False
    assert receipt["broker_writes"] is False
    assert all(path.exists() for path in first.target_weights_paths.values())


def test_r7_cli_dispatches_family_mapper(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    result = SimpleNamespace(
        report_path=Path("reports/forward/r7/latest-observation.json"),
        market_session="2026-08-03",
        valid_session_count=1,
        forward_observation_pass=False,
    )

    def run(spec: Path, root: Path, **kwargs: object) -> SimpleNamespace:
        captured.update({"spec": spec, "root": root, **kwargs})
        return result

    monkeypatch.setattr(
        adapter,
        "run_multiasset_paper_control_r7_target_weight_mapping",
        run,
    )
    spec_path = ROOT / SPEC_PATHS["R7D01"]
    snapshot = ROOT / "data/research/alpaca_multiasset_forward_pc_r7/snapshot-manifest.json"
    cli.strategy_target_weights(
        spec=spec_path,
        symbols=None,
        data_source="alpaca",
        start=None,
        end=None,
        selected_route_label=None,
        refresh_data=False,
        snapshot_manifest=snapshot,
        custody_dir=None,
        as_of="2026-08-03T21:00:00Z",
    )
    assert captured["spec"] == spec_path
    assert captured["snapshot_manifest_path"] == snapshot
    assert captured["as_of"] == datetime(2026, 8, 3, 21, 0, tzinfo=UTC)


def _fake_computation(columns: pd.Index) -> R7FamilyComputation:
    sessions = pd.DatetimeIndex(["2026-07-01", "2026-08-03"])
    frames: dict[str, pd.DataFrame] = {}
    records: list[dict[str, object]] = []
    for candidate_id in SPEC_PATHS:
        row = pd.Series(0.0, index=columns, dtype=float)
        if candidate_id == "R7D01":
            row.loc[list(RANKABLE_SYMBOLS)] = 1.0 / len(RANKABLE_SYMBOLS)
        else:
            row.loc[["GLD", "SPY", "XLK"]] = 1.0 / 3.0
        frame = pd.DataFrame([row, row], index=sessions, columns=columns)
        frames[candidate_id] = frame
        for decision, execution in (("2026-06-30", "2026-07-01"), ("2026-07-31", "2026-08-03")):
            weights = {symbol: float(row[symbol]) for symbol in sorted(columns)}
            records.append(
                {
                    "schema_version": 1,
                    "iter_id": "mom_multiasset_paper_control_r7",
                    "candidate_id": candidate_id,
                    "segment_id": "R7_FIXED_REPLAY",
                    "decision_session": decision,
                    "execution_session": execution,
                    "selected_symbols": [
                        symbol for symbol, weight in weights.items() if weight > 0
                    ],
                    "weights": weights,
                    "target_sha256": adapter._target_hash(weights),
                    "fallback_reason": (
                        "intentional_missing_modality_identity" if candidate_id == "R7F01" else None
                    ),
                    "unexpected_model_fallback": False,
                    "order_eligible_in_r7": False,
                    "broker_writes": False,
                }
            )
    frames["R7F01"] = frames["R7M01"].copy()
    return R7FamilyComputation(
        targets=frames,
        target_records=records,
        model_records=[],
        target_series_sha256={
            candidate_id: canonical_target_hash(frame) for candidate_id, frame in frames.items()
        },
    )
