from __future__ import annotations

import hashlib
import inspect
import json
import shutil
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import typer
import yaml

from open_composer.adapters.execution import (
    multiasset_forward_multimodal_r5_target_weights as adapter,
)
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.evidence_custody import write_external_custody_bundle
from open_composer.research.multiasset_forward_multimodal_r5 import (
    EVALUATION_ANCHOR_CONTRACT,
    ITER_ID,
    ITERATION_DIR,
    RANKABLE_SYMBOLS,
    RESERVE_SYMBOL,
    SPEC_PATHS,
    PanelData,
    canonical_target_hash,
)
from open_composer.strategy_versions import strategy_content_hash


@pytest.fixture(scope="module")
def reference_computations() -> dict[str, adapter.R5TargetComputation]:
    repo_root = Path(__file__).resolve().parents[1]
    sessions = pd.bdate_range("2021-01-04", periods=1_200)
    symbols = sorted([*RANKABLE_SYMBOLS, RESERVE_SYMBOL])
    offset = np.arange(len(sessions), dtype=float)
    close = pd.DataFrame(
        {
            symbol: 50.0
            + index * 3.0
            + (0.015 + 0.001 * index) * offset
            + 2.0 * np.sin(offset / (15 + index))
            for index, symbol in enumerate(symbols)
        },
        index=sessions,
    )
    opening = close * pd.DataFrame(
        {
            symbol: 1.0 + 0.0005 * np.sin(offset / (7 + index))
            for index, symbol in enumerate(symbols)
        },
        index=sessions,
    )
    volume = pd.DataFrame(
        {
            symbol: 1_000_000.0 + index * 10_000.0 + 1_000.0 * np.cos(offset / (5 + index))
            for index, symbol in enumerate(symbols)
        },
        index=sessions,
    )
    panel = PanelData(
        open=opening,
        high=np.maximum(opening, close) * 1.01,
        low=np.minimum(opening, close) * 0.99,
        close=close,
        volume=volume,
        manifest={},
    )
    specs = {
        candidate_id: load_strategy_spec(repo_root / path)
        for candidate_id, path in SPEC_PATHS.items()
    }
    return {
        candidate_id: adapter.compute_selected_candidate_targets(
            panel,
            specs,
            candidate_id=candidate_id,
            train_start_session=sessions[0].date().isoformat(),
            provenance={
                "data_manifest_sha256": "a" * 64,
                "feature_contract_sha256": "b" * 64,
                "label_contract_sha256": "c" * 64,
                "prompt_hash": "d" * 64,
            },
        )
        for candidate_id in ("R5D01", "R5M01")
    }


@pytest.mark.slow
def test_reference_mapping_uses_frozen_d01_and_model_paths(
    reference_computations: dict[str, adapter.R5TargetComputation],
) -> None:
    deterministic = reference_computations["R5D01"]
    model = reference_computations["R5M01"]

    assert len(deterministic.targets) == 2
    assert deterministic.latest_model_record is None
    assert deterministic.latest_target_record["candidate_id"] == "R5D01"
    assert len(deterministic.latest_target_record["selected_symbols"]) == 3
    assert deterministic.targets.iloc[-1].sum() == pytest.approx(1.0)
    assert canonical_target_hash(deterministic.targets) == deterministic.target_series_sha256

    assert len(model.targets) == 2
    assert model.latest_model_record is not None
    assert model.latest_model_record["candidate_id"] == "R5M01"
    assert model.latest_model_record["status"] == "fit_complete"
    assert model.latest_model_record["fitted_model_sha256"]
    assert model.latest_target_record["candidate_id"] == "R5M01"
    assert model.targets.iloc[-1].sum() == pytest.approx(1.0)


def test_adapter_has_no_broker_network_or_credential_runtime_imports() -> None:
    source = inspect.getsource(adapter)
    forbidden = (
        "TradingClient(",
        "alpaca_api_key",
        "alpaca_api_secret",
        "requests.get",
        "submit_order(",
        "write_paper_canary_authorization",
    )
    assert all(item not in source for item in forbidden)


def test_spec_gate_rejects_legacy_name_and_selection_prohibited_candidates(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    root = _copy_specs_and_adapter(tmp_path, repo_root)
    d01_path = (root / SPEC_PATHS["R5D01"]).resolve()
    payload = yaml.safe_load(d01_path.read_text(encoding="utf-8"))
    payload["name"] = "us_multiasset_stock_rank_lgbm_m1"
    d01_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    legacy = load_strategy_spec(d01_path)
    with pytest.raises(ValueError, match="identity or strategy name mismatch"):
        adapter._require_observation_only_spec(legacy, "R5D01", d01_path, root)

    for candidate_id in ("R5F01", "R5P01"):
        path = (root / SPEC_PATHS[candidate_id]).resolve()
        spec = load_strategy_spec(path)
        with pytest.raises(ValueError, match="selection-prohibited"):
            adapter._require_observation_only_spec(spec, candidate_id, path, root)


def test_relative_and_absolute_spec_aliases_share_transaction_lock(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_specs_and_adapter(tmp_path, repo_root)
    captured_locks: list[Path] = []
    locked_calls: list[Path] = []
    sentinel = object()

    @contextmanager
    def capture_lock(path: Path):
        captured_locks.append(path)
        yield

    def run_locked(spec_path: Path, *_args, **_kwargs):
        locked_calls.append(spec_path)
        return sentinel

    monkeypatch.setattr(adapter, "_exclusive_file_lock", capture_lock)
    monkeypatch.setattr(
        adapter,
        "_run_multiasset_forward_multimodal_r5_target_weight_mapping_locked",
        run_locked,
    )
    relative = SPEC_PATHS["R5D01"]
    absolute = (root / relative).resolve()
    kwargs = {
        "candidate_id": "R5D01",
        "snapshot_manifest_path": Path("unused.json"),
        "custody_dir": tmp_path / "custody",
        "as_of": datetime(2026, 7, 31, 22, tzinfo=UTC),
    }

    assert (
        adapter.run_multiasset_forward_multimodal_r5_target_weight_mapping(
            relative,
            root,
            **kwargs,
        )
        is sentinel
    )
    assert (
        adapter.run_multiasset_forward_multimodal_r5_target_weight_mapping(
            absolute,
            root,
            **kwargs,
        )
        is sentinel
    )
    assert locked_calls == [absolute, absolute]
    assert len(captured_locks) == 2
    assert captured_locks[0] == captured_locks[1]


def test_final_dossier_rejects_unselected_and_research_failed_candidates(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_final_dossier(monkeypatch)
    unselected = _make_workspace(tmp_path / "unselected", repo_root, selected=["R5D01"])
    m01_path = (unselected / SPEC_PATHS["R5M01"]).resolve()
    with pytest.raises(ValueError, match="not selected"):
        adapter._require_final_dossier(
            root=unselected,
            spec=load_strategy_spec(m01_path),
            spec_path=m01_path,
            candidate_id="R5M01",
            custody_dir=_custody_dir(unselected),
        )

    failed = _make_workspace(
        tmp_path / "failed",
        repo_root,
        selected=["R5D01"],
        research_pass=False,
    )
    d01_path = (failed / SPEC_PATHS["R5D01"]).resolve()
    with pytest.raises(ValueError, match="research_pass is false"):
        adapter._require_final_dossier(
            root=failed,
            spec=load_strategy_spec(d01_path),
            spec_path=d01_path,
            candidate_id="R5D01",
            custody_dir=_custody_dir(failed),
        )


def test_final_dossier_rejects_lock_and_adapter_implementation_drift(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_final_dossier(monkeypatch)
    lock_root = _make_workspace(tmp_path / "lock", repo_root, selected=["R5D01"])
    preregistration = lock_root / ITERATION_DIR / "lock-set/preregistration-lock.json"
    preregistration.write_text(
        preregistration.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    d01_path = (lock_root / SPEC_PATHS["R5D01"]).resolve()
    with pytest.raises(ValueError, match="binding mismatch|anchor is stale"):
        adapter._require_final_dossier(
            root=lock_root,
            spec=load_strategy_spec(d01_path),
            spec_path=d01_path,
            candidate_id="R5D01",
            custody_dir=_custody_dir(lock_root),
        )

    implementation_root = _make_workspace(
        tmp_path / "implementation",
        repo_root,
        selected=["R5D01"],
    )
    implementation_path = implementation_root / adapter.ADAPTER_RELATIVE_PATH
    implementation_path.write_text(
        implementation_path.read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )
    d01_path = (implementation_root / SPEC_PATHS["R5D01"]).resolve()
    with pytest.raises(ValueError, match="runner file binding SHA-256 mismatch"):
        adapter._require_final_dossier(
            root=implementation_root,
            spec=load_strategy_spec(d01_path),
            spec_path=d01_path,
            candidate_id="R5D01",
            custody_dir=_custody_dir(implementation_root),
        )


def test_bound_file_replacement_after_resolution_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path.resolve()
    path = root / "bound.json"
    original = b'{"value":"original"}\n'
    replacement = b'{"value":"replaced"}\n'
    path.write_bytes(original)
    binding = {
        "path": "bound.json",
        "sha256": hashlib.sha256(original).hexdigest(),
        "size_bytes": len(original),
    }
    real_resolve = adapter._resolve_root_file

    def resolve_then_replace(*args, **kwargs):
        resolved = real_resolve(*args, **kwargs)
        path.write_bytes(replacement)
        return resolved

    monkeypatch.setattr(adapter, "_resolve_root_file", resolve_then_replace)
    with pytest.raises(ValueError, match="binding SHA-256 mismatch"):
        adapter._read_bound_file(root, binding, label="test binding")


def test_run_rejects_future_backfill_and_completed_session_mismatch(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    _install_forward_stubs(monkeypatch)
    session = date(2026, 7, 1)
    as_of = _after_close(session)
    manifest = _write_snapshot_manifest(root, session, as_of - timedelta(minutes=1))
    spec_path = root / SPEC_PATHS["R5D01"]

    monkeypatch.setattr(adapter, "_utc_now", lambda: as_of)
    with pytest.raises(ValueError, match="future"):
        adapter.run_multiasset_forward_multimodal_r5_target_weight_mapping(
            spec_path,
            root,
            candidate_id="R5D01",
            snapshot_manifest_path=manifest,
            custody_dir=_custody_dir(root),
            as_of=as_of + timedelta(seconds=1),
        )
    monkeypatch.setattr(adapter, "_utc_now", lambda: as_of + timedelta(minutes=6))
    with pytest.raises(ValueError, match="cannot be backfilled"):
        adapter.run_multiasset_forward_multimodal_r5_target_weight_mapping(
            spec_path,
            root,
            candidate_id="R5D01",
            snapshot_manifest_path=manifest,
            custody_dir=_custody_dir(root),
            as_of=as_of,
        )

    monkeypatch.setattr(adapter, "_utc_now", lambda: as_of)
    stale_session = date(2026, 6, 30)
    stale = _write_snapshot_manifest(
        root,
        stale_session,
        as_of - timedelta(minutes=1),
        suffix="stale",
    )
    with pytest.raises(ValueError, match="latest completed session mismatch"):
        adapter.run_multiasset_forward_multimodal_r5_target_weight_mapping(
            spec_path,
            root,
            candidate_id="R5D01",
            snapshot_manifest_path=stale,
            custody_dir=_custody_dir(root),
            as_of=as_of,
        )


def test_run_rejects_weekend_observation_more_than_twelve_hours_after_close(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    _install_forward_stubs(monkeypatch)
    friday = date(2026, 7, 10)
    saturday = _after_close(friday) + timedelta(hours=11, minutes=1)
    manifest = _write_snapshot_manifest(
        root,
        friday,
        _after_close(friday) - timedelta(hours=2, minutes=1),
    )
    monkeypatch.setattr(adapter, "_utc_now", lambda: saturday)

    with pytest.raises(ValueError, match="outside the non-backfill session window"):
        adapter.run_multiasset_forward_multimodal_r5_target_weight_mapping(
            root / SPEC_PATHS["R5D01"],
            root,
            candidate_id="R5D01",
            snapshot_manifest_path=manifest,
            custody_dir=_custody_dir(root),
            as_of=saturday,
        )
    strategy_name = "us_multiasset_forward_mm_r5_d01"
    assert not (root / "reports/forward" / strategy_name).exists()
    assert not (root / "reports/execution" / f"{strategy_name}-target-weights.json").exists()
    assert not (root / "reports/execution" / f"{strategy_name}-rebalance-intents.json").exists()
    assert not (root / "reports/execution" / f"{strategy_name}-execution-observation.json").exists()


def test_snapshot_settlement_lag_uses_actual_early_close() -> None:
    early_close_session = date(2026, 11, 27)
    session_close = adapter._session_close_utc(early_close_session)
    observed_at = session_close + timedelta(minutes=20)

    assert session_close.hour == 18
    assert (
        adapter._snapshot_observation_window_valid(
            retrieved_at=session_close + timedelta(minutes=14, seconds=59),
            session_close=session_close,
            observed_at=observed_at,
        )
        is False
    )
    assert (
        adapter._snapshot_observation_window_valid(
            retrieved_at=session_close + timedelta(minutes=15),
            session_close=session_close,
            observed_at=observed_at,
        )
        is True
    )


def test_duplicate_receipt_is_idempotent_and_different_receipt_is_rejected(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    _install_forward_stubs(monkeypatch)
    session = date(2026, 7, 1)
    as_of = _after_close(session)
    manifest = _write_snapshot_manifest(root, session, as_of - timedelta(minutes=1))

    first = _run_session(root, monkeypatch, session, manifest)
    second = _run_session(root, monkeypatch, session, manifest)

    assert first.receipt_path == second.receipt_path
    assert first.target_weights_path == second.target_weights_path
    assert first.rebalance_intents_path == second.rebalance_intents_path
    assert first.observation_path == second.observation_path
    assert first.target_weights_path.parent.name == session.isoformat()
    assert len(_ledger_rows(first.forward_ledger_path)) == 1
    assert not (root / "reports/execution").exists()
    different = _write_snapshot_manifest(
        root,
        session,
        as_of - timedelta(minutes=2),
        suffix="different",
    )
    with pytest.raises(ValueError, match="different bound contents"):
        _run_session(root, monkeypatch, session, different)


def test_retry_recovers_after_ledger_append_before_readiness_publication(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    _install_forward_stubs(monkeypatch)
    session = date(2026, 7, 1)
    manifest = _write_snapshot_manifest(
        root,
        session,
        _after_close(session) - timedelta(minutes=1),
    )
    real_write_readiness = adapter._write_readiness
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated readiness publication failure")
        return real_write_readiness(*args, **kwargs)

    monkeypatch.setattr(adapter, "_write_readiness", fail_once)
    with pytest.raises(OSError, match="simulated readiness"):
        _run_session(root, monkeypatch, session, manifest)

    ledger = root / "reports/forward/us_multiasset_forward_mm_r5_d01/decisions.jsonl"
    assert len(_ledger_rows(ledger)) == 1
    result = _run_session(root, monkeypatch, session, manifest)
    assert len(_ledger_rows(result.forward_ledger_path)) == 1
    assert result.forward_readiness_path.exists()
    assert result.report_path.exists()


def test_retry_recovers_receipt_written_before_ledger_append(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    _install_forward_stubs(monkeypatch)
    session = date(2026, 7, 1)
    first_as_of = _after_close(session)
    manifest = _write_snapshot_manifest(
        root,
        session,
        first_as_of - timedelta(minutes=1),
    )
    real_append = adapter._append_ledger_row
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated ledger append failure")
        return real_append(*args, **kwargs)

    monkeypatch.setattr(adapter, "_append_ledger_row", fail_once)
    monkeypatch.setattr(adapter, "_utc_now", lambda: first_as_of)
    with pytest.raises(OSError, match="simulated ledger append failure"):
        adapter.run_multiasset_forward_multimodal_r5_target_weight_mapping(
            root / SPEC_PATHS["R5D01"],
            root,
            candidate_id="R5D01",
            snapshot_manifest_path=manifest,
            custody_dir=_custody_dir(root),
            as_of=first_as_of,
        )

    forward = root / "reports/forward/us_multiasset_forward_mm_r5_d01"
    receipt = forward / "receipts" / f"{session.isoformat()}.json"
    ledger = forward / "decisions.jsonl"
    assert receipt.exists()
    original_receipt = receipt.read_bytes()
    assert not ledger.exists()

    retry_as_of = first_as_of + timedelta(seconds=30)
    monkeypatch.setattr(adapter, "_utc_now", lambda: retry_as_of)
    result = adapter.run_multiasset_forward_multimodal_r5_target_weight_mapping(
        root / SPEC_PATHS["R5D01"],
        root,
        candidate_id="R5D01",
        snapshot_manifest_path=manifest,
        custody_dir=_custody_dir(root),
        as_of=retry_as_of,
    )

    assert receipt.read_bytes() == original_receipt
    assert len(_ledger_rows(result.forward_ledger_path)) == 1
    assert _ledger_rows(result.forward_ledger_path)[0]["observed_at"] == first_as_of.isoformat()


@pytest.mark.parametrize(
    ("role", "mutate"),
    [
        (
            "router_cost_stress",
            lambda payload: payload["scenarios"][0].__setitem__("slippage_bps", 999.0),
        ),
        (
            "router_data_evidence",
            lambda payload: payload["data_profile"].__setitem__("provider", "forged"),
        ),
        (
            "router_validation",
            lambda payload: payload["parity_check"].__setitem__(
                "target_rows_match_frozen_r5_reference", False
            ),
        ),
    ],
)
def test_forged_supporting_router_artifact_aborts_before_publication(
    role: str,
    mutate,
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    _install_forward_stubs(monkeypatch)
    session = date(2026, 7, 1)
    manifest = _write_snapshot_manifest(
        root,
        session,
        _after_close(session) - timedelta(minutes=1),
    )
    real_writer = adapter.write_router_execution_artifacts

    def forged_writer(**kwargs):
        artifacts = real_writer(**kwargs)
        path = artifacts[role]
        payload = json.loads(path.read_text(encoding="utf-8"))
        mutate(payload)
        _write_json(path, payload)
        return artifacts

    monkeypatch.setattr(adapter, "write_router_execution_artifacts", forged_writer)
    with pytest.raises(ValueError, match="supporting router artifact semantics"):
        _run_session(root, monkeypatch, session, manifest)

    forward = root / "reports/forward/us_multiasset_forward_mm_r5_d01"
    assert not (forward / "evidence" / session.isoformat()).exists()
    assert not (forward / "receipts" / f"{session.isoformat()}.json").exists()
    assert not (forward / "decisions.jsonl").exists()
    assert not (root / "reports/execution").exists()


def test_symlinked_reports_ancestor_cannot_redirect_publication(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path / "workspace", repo_root, selected=["R5D01"])
    _install_forward_stubs(monkeypatch)
    session = date(2026, 7, 1)
    manifest = _write_snapshot_manifest(
        root,
        session,
        _after_close(session) - timedelta(minutes=1),
    )
    redirected = tmp_path / "redirected-reports"
    (root / "reports").rename(redirected)
    (root / "reports").symlink_to(redirected, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked or invalid ancestor"):
        _run_session(root, monkeypatch, session, manifest)

    assert not (redirected / "forward").exists()


def test_failed_evidence_directory_rename_leaves_no_partial_bundle_or_stage(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    _install_forward_stubs(monkeypatch)
    session = date(2026, 7, 1)
    manifest = _write_snapshot_manifest(
        root,
        session,
        _after_close(session) - timedelta(minutes=1),
    )

    def fail_rename(_source: Path, _destination: Path) -> None:
        raise OSError("simulated evidence rename failure")

    monkeypatch.setattr(adapter, "_rename_directory_atomic", fail_rename)
    with pytest.raises(OSError, match="simulated evidence rename failure"):
        _run_session(root, monkeypatch, session, manifest)

    forward = root / "reports/forward/us_multiasset_forward_mm_r5_d01"
    evidence_parent = forward / "evidence"
    staging_parent = forward / ".router-staging"
    assert not (evidence_parent / session.isoformat()).exists()
    assert not evidence_parent.exists() or not any(evidence_parent.iterdir())
    assert not staging_parent.exists() or not any(staging_parent.iterdir())
    assert not (forward / "decisions.jsonl").exists()
    assert not (root / "reports/execution").exists()


def test_external_evaluation_custody_tamper_fails_closed(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    _allow_final_dossier(monkeypatch)
    evaluation_receipts = list(_custody_dir(root).glob("*/evaluation/*/receipt.json"))
    assert len(evaluation_receipts) == 1
    receipt_path = evaluation_receipts[0]
    receipt_path.chmod(0o600)
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["entry_count"] += 1
    receipt_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    receipt_path.chmod(0o400)
    spec_path = (root / SPEC_PATHS["R5D01"]).resolve()

    with pytest.raises(ValueError, match="canonical|manifest"):
        adapter._require_final_dossier(
            root=root,
            spec=load_strategy_spec(spec_path),
            spec_path=spec_path,
            candidate_id="R5D01",
            custody_dir=_custody_dir(root),
        )


def test_missing_required_session_closes_epoch_without_backfill(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    _install_forward_stubs(monkeypatch)
    sessions = adapter._expected_sessions(date(2026, 7, 1), count=3)
    first_manifest = _write_snapshot_manifest(
        root,
        sessions[0],
        _after_close(sessions[0]) - timedelta(minutes=1),
    )
    _run_session(root, monkeypatch, sessions[0], first_manifest)
    third_manifest = _write_snapshot_manifest(
        root,
        sessions[2],
        _after_close(sessions[2]) - timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match="epoch is closed"):
        _run_session(root, monkeypatch, sessions[2], third_manifest)

    readiness = json.loads(
        (root / "reports/forward/us_multiasset_forward_mm_r5_d01/readiness.json").read_text(
            encoding="utf-8"
        )
    )
    assert readiness["epoch_closed"] is True
    assert readiness["missing_required_sessions"] == [sessions[1].isoformat()]
    assert readiness["forward_observation_pass"] is False


def test_frozen_target_artifact_tamper_invalidates_receipt_and_closes_epoch(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    _install_forward_stubs(monkeypatch)
    sessions = adapter._expected_sessions(date(2026, 7, 1), count=2)
    first_manifest = _write_snapshot_manifest(
        root,
        sessions[0],
        _after_close(sessions[0]) - timedelta(minutes=1),
    )
    result = _run_session(root, monkeypatch, sessions[0], first_manifest)
    row = _ledger_rows(result.forward_ledger_path)[0]
    target_path = root / row["evidence_bindings"]["router_target_weights"]["path"]
    target_path.chmod(0o600)
    target_path.write_text(target_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    second_manifest = _write_snapshot_manifest(
        root,
        sessions[1],
        _after_close(sessions[1]) - timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match="epoch is closed"):
        _run_session(root, monkeypatch, sessions[1], second_manifest)

    readiness = json.loads(result.forward_readiness_path.read_text(encoding="utf-8"))
    assert readiness["epoch_closed"] is True
    assert readiness["invalid_required_sessions"] == [sessions[0].isoformat()]


@pytest.mark.parametrize(
    "field_name",
    [
        "target_weights_path",
        "rebalance_intents_path",
        "cost_stress_path",
        "data_evidence_path",
        "validation_path",
    ],
)
def test_observation_binds_every_immutable_router_artifact_path(
    field_name: str,
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    _install_forward_stubs(monkeypatch)
    session = date(2026, 7, 1)
    manifest = _write_snapshot_manifest(
        root,
        session,
        _after_close(session) - timedelta(minutes=1),
    )
    result = _run_session(root, monkeypatch, session, manifest)
    row = _ledger_rows(result.forward_ledger_path)[0]
    observation_binding = row["evidence_bindings"]["router_execution_observation"]
    observation_path = root / observation_binding["path"]
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    observation[field_name] = "reports/execution/forged.json"
    forged_bytes = adapter._canonical_json_bytes(observation)
    observation_path.chmod(0o600)
    observation_path.write_bytes(forged_bytes)
    observation_path.chmod(0o400)

    forged_row = json.loads(json.dumps(row))
    forged_binding = forged_row["evidence_bindings"]["router_execution_observation"]
    forged_binding["sha256"] = hashlib.sha256(forged_bytes).hexdigest()
    forged_binding["size_bytes"] = len(forged_bytes)
    spec_path = (root / SPEC_PATHS["R5D01"]).resolve()
    spec = load_strategy_spec(spec_path)
    dossier = adapter._require_final_dossier(
        root=root,
        spec=spec,
        spec_path=spec_path,
        candidate_id="R5D01",
        custody_dir=_custody_dir(root),
    )

    reasons = adapter._validate_evidence_bindings(root, spec, dossier, forged_row)
    assert "execution_observation_payload_mismatch" in reasons


@pytest.mark.slow
def test_twenty_contiguous_receipts_pass_but_remain_non_orderable(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    _install_forward_stubs(monkeypatch)
    sessions = adapter._expected_sessions(date(2026, 7, 1), count=20)
    result = None
    for index, session in enumerate(sessions):
        manifest = _write_snapshot_manifest(
            root,
            session,
            _after_close(session) - timedelta(minutes=1),
            suffix=str(index),
        )
        result = _run_session(root, monkeypatch, session, manifest)
    assert result is not None

    readiness = json.loads(result.forward_readiness_path.read_text(encoding="utf-8"))
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    intents = json.loads(result.rebalance_intents_path.read_text(encoding="utf-8"))
    assert readiness["contiguous_bound_session_count"] == 20
    assert readiness["forward_observation_pass"] is True
    assert readiness["execution_substate"] == "observation_only"
    assert readiness["paper_ready_pass"] is False
    assert readiness["paper_order_authorization"] is False
    assert readiness["broker_writes"] is False
    assert readiness["generic_paper_bridge"] is False
    assert report["paper_ready_pass"] is False
    assert report["paper_order_authorization"] is False
    assert all(item["requires_order"] is False for item in intents["intents"])
    rows = _ledger_rows(result.forward_ledger_path)
    assert len(rows) == 20
    assert all(row["operator_lock_anchor_sha256"] for row in rows)
    assert all(row["operator_evaluation_anchor_sha256"] for row in rows)
    assert all(row["evaluation_receipt_sha256"] for row in rows)
    assert all(row["evaluation_anchor_sha256"] for row in rows)
    assert all(row["adapter_implementation_sha256"] for row in rows)
    assert all(row["target_sha256"] for row in rows)
    assert all(row["lock_custody_receipt_sha256"] for row in rows)
    assert all(row["lock_custody_bundle_sha256"] for row in rows)
    assert all(row["evaluation_custody_receipt_sha256"] for row in rows)
    assert all(row["evaluation_custody_bundle_sha256"] for row in rows)


def test_cli_r5_dispatch_requires_snapshot_and_external_custody(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import open_composer.cli as cli

    root = _make_workspace(tmp_path, repo_root, selected=["R5D01"])
    spec_path = root / SPEC_PATHS["R5D01"]
    monkeypatch.setattr(cli, "project_root", lambda: root)

    with pytest.raises(typer.BadParameter, match="snapshot-manifest"):
        _call_target_weights_cli(cli, spec_path=spec_path)
    with pytest.raises(typer.BadParameter, match="custody-dir"):
        _call_target_weights_cli(
            cli,
            spec_path=spec_path,
            snapshot_manifest=root / "snapshot.json",
        )


def test_cli_routes_r5_to_frozen_adapter_and_preserves_legacy_path(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import open_composer.cli as cli
    import open_composer.research.multiasset_momentum_portfolio as legacy

    root = _make_workspace(tmp_path / "r5", repo_root, selected=["R5D01"])
    spec_path = root / SPEC_PATHS["R5D01"]
    manifest = root / "snapshot.json"
    manifest.write_text("{}\n", encoding="utf-8")
    calls: list[dict] = []

    def run_r5(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return SimpleNamespace(
            report_path=root / "report.json",
            candidate_id="R5D01",
            market_session="2026-07-31",
            forward_observation_pass=False,
        )

    monkeypatch.setattr(
        adapter, "run_multiasset_forward_multimodal_r5_target_weight_mapping", run_r5
    )
    monkeypatch.setattr(cli, "project_root", lambda: root)
    _call_target_weights_cli(
        cli,
        spec_path=spec_path,
        snapshot_manifest=manifest,
        custody_dir=_custody_dir(root),
    )
    assert len(calls) == 1
    assert calls[0]["kwargs"]["candidate_id"] == "R5D01"
    assert calls[0]["kwargs"]["snapshot_manifest_path"] == manifest
    assert calls[0]["kwargs"]["custody_dir"] == _custody_dir(root)

    legacy_calls: list[tuple[Path, Path]] = []
    legacy_relative = Path("strategy_specs/drafts/us_multiasset_etf_trend_d1.yaml")
    legacy_spec = root / legacy_relative
    legacy_spec.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo_root / legacy_relative, legacy_spec)

    def write_legacy(spec: Path, project: Path) -> dict[str, Path]:
        legacy_calls.append((spec, project))
        return {
            "router_target_weights": project / "legacy-targets.json",
            "router_execution_observation": project / "legacy-observation.json",
        }

    monkeypatch.setattr(legacy, "write_multiasset_target_weights_for_spec", write_legacy)
    _call_target_weights_cli(cli, spec_path=legacy_spec)
    assert legacy_calls == [(legacy_spec.resolve(), root)]
    assert len(calls) == 1

    spoofed_legacy_spec = root / "strategy_specs/drafts/spoofed-legacy.yaml"
    shutil.copy2(legacy_spec, spoofed_legacy_spec)
    with pytest.raises(typer.BadParameter, match="canonical StrategySpec path mismatch"):
        _call_target_weights_cli(cli, spec_path=spoofed_legacy_spec)
    assert legacy_calls == [(legacy_spec.resolve(), root)]

    legacy_payload = yaml.safe_load(legacy_spec.read_text(encoding="utf-8"))
    legacy_payload["costs"]["slippage_bps"] += 0.25
    legacy_spec.write_text(
        yaml.safe_dump(legacy_payload, sort_keys=False),
        encoding="utf-8",
    )
    with pytest.raises(typer.BadParameter, match="semantic hash mismatch"):
        _call_target_weights_cli(cli, spec_path=legacy_spec)
    assert legacy_calls == [(legacy_spec.resolve(), root)]

    unknown_spec = repo_root / "strategy_specs/drafts/us_multiasset_forward_mm_r4_d01.yaml"
    with pytest.raises(typer.BadParameter, match="unsupported cross_sectional_momentum"):
        _call_target_weights_cli(cli, spec_path=unknown_spec)
    assert legacy_calls == [(legacy_spec.resolve(), root)]


def test_legacy_direct_writer_reads_frozen_artifacts_without_regeneration(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import open_composer.research.multiasset_momentum_portfolio as legacy

    root, spec_path = _make_legacy_artifact_workspace(tmp_path, repo_root, legacy)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy portfolio generation or market access was invoked")

    monkeypatch.setattr(legacy, "write_multiasset_momentum_portfolio", forbidden)
    monkeypatch.setattr(legacy, "_load_panels", forbidden)
    artifacts = legacy.write_multiasset_target_weights_for_spec(spec_path, root)

    assert artifacts == {
        "router_target_weights": root
        / "reports/execution/us_multiasset_etf_trend_d1-target-weights.json",
        "router_execution_observation": root
        / "reports/execution/us_multiasset_etf_trend_d1-execution-observation.json",
    }


def test_legacy_direct_writer_rejects_spoof_and_symlinked_ancestor_before_data_access(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import open_composer.research.multiasset_momentum_portfolio as legacy

    root, spec_path = _make_legacy_artifact_workspace(
        tmp_path / "regular",
        repo_root,
        legacy,
    )
    calls: list[str] = []

    def forbidden(*_args, **_kwargs):
        calls.append("market_or_generator")
        raise AssertionError("market access should not occur")

    monkeypatch.setattr(legacy, "write_multiasset_momentum_portfolio", forbidden)
    monkeypatch.setattr(legacy, "_load_panels", forbidden)
    spoof = root / "strategy_specs/drafts/spoof.yaml"
    shutil.copy2(spec_path, spoof)
    with pytest.raises(ValueError, match="not frozen|canonical StrategySpec path mismatch"):
        legacy.write_multiasset_target_weights_for_spec(spoof, root)
    assert calls == []

    symlink_root = (tmp_path / "symlink").resolve()
    external = (tmp_path / "external-specs").resolve()
    external.mkdir(parents=True)
    shutil.copy2(repo_root / spec_path.relative_to(root), external / spec_path.name)
    (symlink_root / "strategy_specs").mkdir(parents=True)
    (symlink_root / "strategy_specs/drafts").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="missing or symlinked ancestor"):
        legacy.write_multiasset_target_weights_for_spec(
            symlink_root / spec_path.relative_to(root),
            symlink_root,
        )
    assert calls == []


def test_legacy_direct_writer_revalidates_spec_after_artifact_reads(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import open_composer.research.multiasset_momentum_portfolio as legacy

    root, spec_path = _make_legacy_artifact_workspace(tmp_path, repo_root, legacy)
    real_read = legacy._read_json_beneath_root

    def mutate_after_observation(*args, **kwargs):
        payload = real_read(*args, **kwargs)
        if kwargs.get("label") == "legacy multiasset execution observation":
            spec_payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
            spec_payload["costs"]["slippage_bps"] += 0.25
            spec_path.write_text(
                yaml.safe_dump(spec_payload, sort_keys=False),
                encoding="utf-8",
            )
        return payload

    monkeypatch.setattr(legacy, "_read_json_beneath_root", mutate_after_observation)
    with pytest.raises(
        ValueError, match="semantic hash mismatch|changed during artifact validation"
    ):
        legacy.write_multiasset_target_weights_for_spec(spec_path, root)


def _call_target_weights_cli(
    cli,
    *,
    spec_path: Path,
    snapshot_manifest: Path | None = None,
    custody_dir: Path | None = None,
) -> None:
    cli.strategy_target_weights(
        spec=spec_path,
        symbols=None,
        data_source="alpaca",
        start=None,
        end=None,
        selected_route_label=None,
        refresh_data=False,
        snapshot_manifest=snapshot_manifest,
        custody_dir=custody_dir,
        as_of="2026-07-31T22:00:00+00:00",
    )


def _make_legacy_artifact_workspace(
    root: Path,
    repo_root: Path,
    legacy,
) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    strategy_name = "us_multiasset_etf_trend_d1"
    spec_relative = legacy.LEGACY_MULTIASSET_MOMENTUM_SPEC_BINDINGS[strategy_name][0]
    spec_path = root / spec_relative
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo_root / spec_relative, spec_path)
    target_relative = Path("reports/execution") / f"{strategy_name}-target-weights.json"
    observation_relative = Path("reports/execution") / f"{strategy_name}-execution-observation.json"
    _write_json(
        root / legacy.PORTFOLIO_PATH,
        {
            "sleeves": [
                {
                    "strategy_name": strategy_name,
                    "target_weights_path": target_relative.as_posix(),
                    "execution_observation_path": observation_relative.as_posix(),
                }
            ]
        },
    )
    _write_json(
        root / target_relative,
        {
            "strategy_name": strategy_name,
            "source_spec_path": spec_relative.as_posix(),
            "portfolio_mode": "cross_sectional_momentum",
            "summary": {"broker_writes": False},
        },
    )
    _write_json(
        root / observation_relative,
        {
            "strategy_name": strategy_name,
            "source_spec_path": spec_relative.as_posix(),
            "execution_substate": "observation_only",
            "blockers": [],
            "target_weights_path": target_relative.as_posix(),
        },
    )
    return root, spec_path


def _make_workspace(
    root: Path,
    repo_root: Path,
    *,
    selected: list[str],
    research_pass: bool = True,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _copy_specs_and_adapter(root, repo_root)
    iteration = root / ITERATION_DIR
    lock_dir = iteration / "lock-set"
    evaluation_dir = iteration / "evaluation-run"
    lock_dir.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)

    candidate_manifest = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "candidates": [
            dict(adapter.R5_CANDIDATE_ROLE_CONTRACT[candidate_id]) for candidate_id in SPEC_PATHS
        ],
    }
    holdout = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "forward_epoch_utc": "2026-07-01T00:00:00-04:00",
        "forward_count_start": 0,
        "minimum_contiguous_bound_sessions": 20,
        "backfill_allowed": False,
        "strategy_or_implementation_change_resets_count": True,
        "missing_required_session_action": "close_epoch_and_start_new_epoch_after_adjudication",
    }
    feature_contract = {
        "schema_version": 1,
        "llm_formula_provenance": {"prompt_hash": "f" * 64},
    }
    label_contract = {"schema_version": 1, "label": "forward_return_21"}
    validation_contract = {
        "schema_version": 1,
        "folds": [{"fold_id": "F1", "train_start": "2021-01-04"}],
    }
    artifacts = {
        "candidate-manifest.json": candidate_manifest,
        "holdout-contract.json": holdout,
        "feature-contract.json": feature_contract,
        "label-contract.json": label_contract,
        "validation-contract.json": validation_contract,
    }
    artifact_bindings = []
    for filename, payload in artifacts.items():
        path = iteration / filename
        _write_json(path, payload)
        artifact_bindings.append(_binding(root, path))

    spec_rows = []
    for candidate_id, relative in SPEC_PATHS.items():
        path = root / relative
        spec_rows.append(
            {
                "candidate_id": candidate_id,
                "path": relative.as_posix(),
                "file_sha256": _sha256(path),
                "semantic_sha256": strategy_content_hash(load_strategy_spec(path)),
            }
        )
    preregistration = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "status": "behavior_contracts_locked_before_first_r5_price_calculation",
        "artifacts": artifact_bindings,
        "specs": spec_rows,
    }
    preregistration_path = lock_dir / "preregistration-lock.json"
    _write_json(preregistration_path, preregistration)
    runner = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "status": "implementation_locked_before_first_r5_price_calculation",
        "files": [_binding(root, root / adapter.ADAPTER_RELATIVE_PATH)],
    }
    runner_path = lock_dir / "runner-lock.json"
    _write_json(runner_path, runner)
    anchor_subject = {
        "iter_id": ITER_ID,
        "preregistration_lock_sha256": _sha256(preregistration_path),
        "runner_lock_sha256": _sha256(runner_path),
    }
    operator_lock_anchor = _hash_payload(anchor_subject)
    lock_anchor_path = lock_dir / "lock-anchor.json"
    _write_json(
        lock_anchor_path,
        {
            "schema_version": 1,
            **anchor_subject,
            "operator_lock_anchor_sha256": operator_lock_anchor,
        },
    )
    attempt_path = iteration / "evaluation-attempt.json"
    _write_json(
        attempt_path,
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "status": "reserved_before_first_price_parse",
        },
    )

    child_names = {
        "feature_ledger": "feature-ledger.jsonl",
        "prediction_ledger": "prediction-ledger.jsonl",
        "daily_return_ledger": "daily-return-ledger.jsonl",
        "target_ledger": "target-ledger.jsonl",
        "event_ledger": "cost-event-ledger.jsonl",
        "benchmark_ledger": "benchmark-ledger.jsonl",
        "model_ledger": "model-ledger.jsonl",
        "trial_ledger": "trial-ledger.jsonl",
        "cost_reconciliation": "cost-reconciliation.json",
        "model_provenance": "model-provenance.json",
        "evaluation": "evaluation-report.json",
        "evaluation_markdown": "evaluation-report.md",
        "decision_record": "decision-record.md",
    }
    evaluation = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "decision": ("continue_to_locked_forward_observation" if research_pass else "stop_r5"),
        "workflow_pass": research_pass,
        "research_pass": research_pass,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "selected_candidate_ids": selected if research_pass else [],
        "candidates": {
            candidate_id: {"promotion_eligible": candidate_id not in adapter.SELECTION_PROHIBITED}
            for candidate_id in SPEC_PATHS
        },
    }
    for name, filename in child_names.items():
        path = evaluation_dir / filename
        if name == "evaluation":
            _write_json(path, evaluation)
        elif path.suffix == ".json":
            _write_json(path, {"schema_version": 1, "name": name})
        else:
            path.write_text(f"{name}\n", encoding="utf-8")
    children = {
        name: _binding(root, evaluation_dir / filename) for name, filename in child_names.items()
    }
    receipt = {
        "schema_version": 3,
        "receipt_contract": "multiasset_forward_multimodal_r5_v3",
        "iter_id": ITER_ID,
        "evidence_publication_status": "complete",
        "decision": evaluation["decision"],
        "workflow_pass": research_pass,
        "research_pass": research_pass,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "preregistration_lock": _binding(root, preregistration_path),
        "runner_lock": _binding(root, runner_path),
        "lock_anchor": _binding(root, lock_anchor_path),
        "evaluation_attempt": _binding(root, attempt_path),
        "children": children,
    }
    receipt_path = evaluation_dir / "evaluation-receipt.json"
    _write_json(receipt_path, receipt)
    evaluation_anchor_path = evaluation_dir / "evaluation-anchor.json"
    evaluation_anchor_subject = {
        "schema_version": 1,
        "anchor_contract": EVALUATION_ANCHOR_CONTRACT,
        "iter_id": ITER_ID,
        "status": "complete_for_external_hash_custody",
        "anchor_path": evaluation_anchor_path.relative_to(root).as_posix(),
        "receipt": _binding(root, receipt_path),
        "preregistration_lock": _binding(root, preregistration_path),
        "runner_lock": _binding(root, runner_path),
        "lock_anchor": _binding(root, lock_anchor_path),
        "evaluation_attempt": _binding(root, attempt_path),
        "operator_lock_anchor_sha256": operator_lock_anchor,
        "custody_requirement": "test_fixture",
        "local_read_only_mode_is_not_independent_custody": True,
    }
    _write_json(
        evaluation_anchor_path,
        {
            **evaluation_anchor_subject,
            "operator_evaluation_anchor_sha256": _hash_payload(evaluation_anchor_subject),
        },
    )
    operator_evaluation_anchor = _hash_payload(evaluation_anchor_subject)
    lock_entries: dict[str, bytes] = {}
    for binding in [*artifact_bindings, *spec_rows, *runner["files"]]:
        relative = str(binding["path"])
        lock_entries[relative] = (root / relative).read_bytes()
    for path in (preregistration_path, runner_path, lock_anchor_path):
        lock_entries[path.relative_to(root).as_posix()] = path.read_bytes()
    lock_custody = write_external_custody_bundle(
        project_root=root,
        custody_root=_custody_dir(root),
        namespace=adapter.R5_CUSTODY_NAMESPACE,
        record_kind="lock",
        subject_sha256=operator_lock_anchor,
        entries=lock_entries,
        subject={
            "iter_id": ITER_ID,
            "operator_lock_anchor_sha256": operator_lock_anchor,
            "lock_anchor_file_sha256": _sha256(lock_anchor_path),
            "source_bundle_complete": True,
        },
    )
    evaluation_entries = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in [
            *(evaluation_dir / filename for filename in child_names.values()),
            preregistration_path,
            runner_path,
            lock_anchor_path,
            attempt_path,
            receipt_path,
            evaluation_anchor_path,
        ]
    }
    evaluation_entries["external-custody/lock-receipt.json"] = (
        lock_custody.receipt_path.read_bytes()
    )
    write_external_custody_bundle(
        project_root=root,
        custody_root=_custody_dir(root),
        namespace=adapter.R5_CUSTODY_NAMESPACE,
        record_kind="evaluation",
        subject_sha256=operator_evaluation_anchor,
        entries=evaluation_entries,
        subject={
            "iter_id": ITER_ID,
            "operator_lock_anchor_sha256": operator_lock_anchor,
            "operator_evaluation_anchor_sha256": operator_evaluation_anchor,
            "evaluation_anchor_file_sha256": _sha256(evaluation_anchor_path),
            "lock_custody_receipt_sha256": lock_custody.receipt_sha256,
            "publication_only_recovery_allowed": True,
            "price_recomputation_allowed": False,
        },
    )
    return root.resolve()


def _copy_specs_and_adapter(root: Path, repo_root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for relative in SPEC_PATHS.values():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / relative, destination)
    adapter_destination = root / adapter.ADAPTER_RELATIVE_PATH
    adapter_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo_root / adapter.ADAPTER_RELATIVE_PATH, adapter_destination)
    return root.resolve()


def _custody_dir(root: Path) -> Path:
    return (root.parent / f"{root.name}-external-custody").resolve()


def _allow_final_dossier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        adapter,
        "validate_iteration_dossier",
        lambda *_args, **_kwargs: SimpleNamespace(ok=True, blocked=[]),
    )


def _install_forward_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_final_dossier(monkeypatch)

    def load_panel(_root: Path, manifest_path: Path) -> PanelData:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        session = date.fromisoformat(manifest["items"][0]["quality"]["complete_sessions"][-1])
        index = pd.DatetimeIndex([pd.Timestamp(session)])
        symbols = sorted([*RANKABLE_SYMBOLS, RESERVE_SYMBOL])
        frame = pd.DataFrame(
            [[100.0 + i for i in range(len(symbols))]], index=index, columns=symbols
        )
        volume = pd.DataFrame([[1_000_000.0] * len(symbols)], index=index, columns=symbols)
        return PanelData(
            open=frame,
            high=frame * 1.01,
            low=frame * 0.99,
            close=frame,
            volume=volume,
            manifest=manifest,
        )

    def compute(
        panel: PanelData,
        _specs: dict,
        *,
        candidate_id: str,
        train_start_session: str,
        provenance: dict | None = None,
    ) -> adapter.R5TargetComputation:
        del train_start_session, provenance
        session = pd.Timestamp(panel.close.index.max()).date().isoformat()
        symbols = sorted(panel.close.columns)
        weights = {symbol: 0.0 for symbol in symbols}
        for symbol in ("IEF", "QQQ", "SPY"):
            weights[symbol] = 1.0 / 3.0
        frame = pd.DataFrame([weights], index=pd.DatetimeIndex([session]), columns=symbols)
        target_hash = adapter._target_hash(weights)
        record = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "segment_id": "FORWARD",
            "candidate_id": candidate_id,
            "decision_session": session,
            "execution_session": session,
            "selected_symbols": ["IEF", "QQQ", "SPY"],
            "weights": weights,
            "target_sha256": target_hash,
            "fallback_reason": None,
            "unexpected_model_fallback": False,
        }
        model = (
            {
                "candidate_id": candidate_id,
                "decision_session": session,
                "model_id": "model-1",
                "status": "fit_complete",
                "failure_reason": None,
                "fitted_model_sha256": "a" * 64,
                "prediction_sha256": "b" * 64,
            }
            if candidate_id.startswith("R5M")
            else None
        )
        return adapter.R5TargetComputation(
            candidate_id=candidate_id,
            targets=frame,
            target_records=[record],
            model_records=[model] if model else [],
            latest_target_record=record,
            latest_model_record=model,
            target_series_sha256=canonical_target_hash(frame),
        )

    monkeypatch.setattr(adapter, "_load_forward_panel", load_panel)
    monkeypatch.setattr(adapter, "compute_selected_candidate_targets", compute)
    monkeypatch.setattr(
        adapter,
        "verify_alpaca_contract_snapshot",
        lambda _root, path: json.loads(path.read_text(encoding="utf-8")),
    )


def _run_session(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    session: date,
    manifest: Path,
) -> adapter.R5ForwardTargetWeightResult:
    as_of = _after_close(session)
    monkeypatch.setattr(adapter, "_utc_now", lambda: as_of)
    return adapter.run_multiasset_forward_multimodal_r5_target_weight_mapping(
        root / SPEC_PATHS["R5D01"],
        root,
        candidate_id="R5D01",
        snapshot_manifest_path=manifest,
        custody_dir=_custody_dir(root),
        as_of=as_of,
    )


def _write_snapshot_manifest(
    root: Path,
    session: date,
    retrieved_at: datetime,
    *,
    suffix: str = "",
) -> Path:
    path = root / "data/forward" / f"snapshot-{session.isoformat()}-{suffix}.json"
    payload = {
        "schema_version": 1,
        "provider": "alpaca",
        "retrieved_at": retrieved_at.isoformat(),
        "immutable": True,
        "overwrite_allowed": False,
        "items": [
            {
                "symbol": symbol,
                "timeframe": "daily",
                "feed": "sip",
                "adjustment": "all",
                "session_scope": "regular",
                "quality": {"complete_sessions": [session.isoformat()]},
            }
            for symbol in sorted([*RANKABLE_SYMBOLS, RESERVE_SYMBOL])
        ],
    }
    _write_json(path, payload)
    return path


def _after_close(session: date) -> datetime:
    return datetime.combine(session, time(22, 0), tzinfo=UTC)


def _ledger_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _binding(root: Path, path: Path) -> dict[str, object]:
    contents = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(contents).hexdigest(),
        "size_bytes": len(contents),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_payload(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
