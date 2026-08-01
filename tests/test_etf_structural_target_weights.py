from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

import open_composer.adapters.execution.etf_structural_target_weights as etf_targets


@pytest.fixture()
def r10_spec_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "strategy_specs"
        / "drafts"
        / "us_etf_core_diversifier_forward_r10.yaml"
    )


def test_r10_baseline_before_epoch_writes_no_forward_session(
    tmp_path: Path,
    r10_spec_path: Path,
    monkeypatch,
) -> None:
    local_spec = _copy_spec(tmp_path, r10_spec_path)
    manifest = _stub_market_inputs(
        tmp_path,
        monkeypatch,
        latest="2026-07-17",
        retrieved_at="2026-07-18T12:00:00+00:00",
        now="2026-07-19T18:00:00+00:00",
    )

    result = etf_targets.run_etf_structural_target_weight_mapping(
        local_spec,
        tmp_path,
        snapshot_manifest_path=manifest,
        as_of=datetime(2026, 7, 19, 18, tzinfo=UTC),
    )

    readiness = _read_json(result.forward_readiness_path)
    assert result.parity_status == "ok"
    assert readiness["valid_bound_sessions"] == 0
    assert readiness["forward_observation_pass"] is False
    assert not result.forward_ledger_path.exists()
    observation = _read_json(result.report_path)
    assert observation["paper_order_authorization"] is False
    assert observation["broker_writes"] is False


def test_r10_forward_session_is_idempotent_and_content_changes_fail_closed(
    tmp_path: Path,
    r10_spec_path: Path,
    monkeypatch,
) -> None:
    local_spec = _copy_spec(tmp_path, r10_spec_path)
    manifest = _stub_market_inputs(tmp_path, monkeypatch, latest="2026-07-20")
    as_of = datetime(2026, 7, 20, 21, tzinfo=UTC)

    first = etf_targets.run_etf_structural_target_weight_mapping(
        local_spec,
        tmp_path,
        snapshot_manifest_path=manifest,
        as_of=as_of,
    )
    second = etf_targets.run_etf_structural_target_weight_mapping(
        local_spec,
        tmp_path,
        snapshot_manifest_path=manifest,
        as_of=as_of,
    )

    rows = first.forward_ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    assert first.forward_ledger_path == second.forward_ledger_path
    assert _read_json(first.forward_readiness_path)["valid_bound_sessions"] == 1

    monkeypatch.setattr(etf_targets, "compute_monthly_targets", _changed_targets)
    with pytest.raises(ValueError, match="immutable forward evidence differs"):
        etf_targets.run_etf_structural_target_weight_mapping(
            local_spec,
            tmp_path,
            snapshot_manifest_path=manifest,
            as_of=as_of,
        )


def test_r10_forward_observation_rejects_retroactive_snapshot_retrieval(
    tmp_path: Path,
    r10_spec_path: Path,
    monkeypatch,
) -> None:
    local_spec = _copy_spec(tmp_path, r10_spec_path)
    manifest = _stub_market_inputs(
        tmp_path,
        monkeypatch,
        latest="2026-07-20",
        retrieved_at="2026-07-21T12:00:00+00:00",
    )

    result = etf_targets.run_etf_structural_target_weight_mapping(
        local_spec,
        tmp_path,
        snapshot_manifest_path=manifest,
        as_of=datetime(2026, 7, 20, 21, tzinfo=UTC),
    )

    observation = _read_json(result.report_path)
    assert observation["workflow_pass"] is False
    assert observation["parity"]["status"] == "blocked"
    assert any("after observed_at" in item for item in observation["parity"]["blockers"])
    assert not result.forward_ledger_path.exists()


def test_r10_missing_first_forward_session_does_not_count(
    tmp_path: Path,
    r10_spec_path: Path,
    monkeypatch,
) -> None:
    local_spec = _copy_spec(tmp_path, r10_spec_path)
    manifest = _stub_market_inputs(
        tmp_path,
        monkeypatch,
        latest="2026-07-21",
        retrieved_at="2026-07-21T20:30:00+00:00",
        now="2026-07-21T21:00:00+00:00",
    )

    result = etf_targets.run_etf_structural_target_weight_mapping(
        local_spec,
        tmp_path,
        snapshot_manifest_path=manifest,
        as_of=datetime(2026, 7, 21, 21, tzinfo=UTC),
    )

    readiness = _read_json(result.forward_readiness_path)
    assert readiness["valid_receipt_sessions"] == 1
    assert readiness["valid_bound_sessions"] == 0
    assert readiness["coverage_missing_sessions"] == ["2026-07-20"]
    assert readiness["forward_observation_pass"] is False
    assert readiness["workflow_pass"] is False


def test_r10_historical_as_of_is_rejected_before_writes(
    tmp_path: Path,
    r10_spec_path: Path,
    monkeypatch,
) -> None:
    local_spec = _copy_spec(tmp_path, r10_spec_path)
    manifest = _stub_market_inputs(
        tmp_path,
        monkeypatch,
        latest="2026-07-20",
        now="2026-07-21T21:00:00+00:00",
    )

    with pytest.raises(ValueError, match="cannot be backfilled"):
        etf_targets.run_etf_structural_target_weight_mapping(
            local_spec,
            tmp_path,
            snapshot_manifest_path=manifest,
            as_of=datetime(2026, 7, 20, 21, tzinfo=UTC),
        )
    assert not (tmp_path / "reports").exists()


def test_preregistration_binding_rejects_changed_or_symlinked_implementation(
    tmp_path: Path,
    r10_spec_path: Path,
) -> None:
    local_spec = _copy_spec(tmp_path, r10_spec_path)
    spec = etf_targets.load_strategy_spec(local_spec)
    contract = tmp_path / "contracts" / "contract.json"
    baseline = tmp_path / "data" / "baseline.json"
    adapter = (
        tmp_path / "open_composer" / "adapters" / "execution" / "etf_structural_target_weights.py"
    )
    for path, contents in [
        (contract, b'{"contract": true}\n'),
        (baseline, b'{"baseline": true}\n'),
        (adapter, b"LOCKED = True\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    lock_path = (
        tmp_path
        / "reports"
        / "research"
        / "iterations"
        / "mom_etf_core_diversifier_forward_r10"
        / "preregistration-lock.json"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_payload = {
        "schema_version": 1,
        "iter_id": "mom_etf_core_diversifier_forward_r10",
        "created_at": "2026-07-19T18:47:00Z",
        "spec": {
            "path": local_spec.relative_to(tmp_path).as_posix(),
            "file_sha256": _sha256(local_spec),
            "semantic_sha256": etf_targets.strategy_content_hash(spec),
        },
        "contracts": [
            {"path": contract.relative_to(tmp_path).as_posix(), "sha256": _sha256(contract)}
        ],
        "baseline_data": {
            "path": baseline.relative_to(tmp_path).as_posix(),
            "sha256": _sha256(baseline),
        },
        "implementation": [
            {"path": adapter.relative_to(tmp_path).as_posix(), "sha256": _sha256(adapter)}
        ],
    }
    lock_path.write_text(json.dumps(lock_payload), encoding="utf-8")

    binding = etf_targets._require_preregistration_binding(
        root=tmp_path,
        spec_path=local_spec,
        spec=spec,
        observed_at=datetime(2026, 7, 20, 21, tzinfo=UTC),
    )
    assert binding.lock_path == lock_path

    original = adapter.read_bytes()
    adapter.write_text("LOCKED = False\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sha256 mismatch"):
        etf_targets._require_preregistration_binding(
            root=tmp_path,
            spec_path=local_spec,
            spec=spec,
            observed_at=datetime(2026, 7, 20, 21, tzinfo=UTC),
        )

    adapter.write_bytes(original)
    target = adapter.with_name("locked-target.py")
    adapter.rename(target)
    adapter.symlink_to(target.name)
    with pytest.raises(ValueError, match="regular file inside the project root"):
        etf_targets._require_preregistration_binding(
            root=tmp_path,
            spec_path=local_spec,
            spec=spec,
            observed_at=datetime(2026, 7, 20, 21, tzinfo=UTC),
        )


def _stub_market_inputs(
    tmp_path: Path,
    monkeypatch,
    *,
    latest: str,
    retrieved_at: str = "2026-07-20T21:00:00+00:00",
    now: str = "2026-07-20T21:00:00+00:00",
) -> Path:
    manifest = tmp_path / "snapshot-manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    index = pd.bdate_range(end=latest, periods=300)
    columns = [
        "BIL",
        "GLD",
        "IEF",
        "QQQ",
        "SPY",
        "XLB",
        "XLE",
        "XLF",
        "XLI",
        "XLK",
        "XLP",
        "XLU",
        "XLV",
        "XLY",
    ]
    closes = pd.DataFrame(100.0, index=index, columns=columns)
    monkeypatch.setattr(
        etf_targets,
        "verify_alpaca_contract_snapshot",
        lambda root, path: {
            "provider": "alpaca",
            "retrieved_at": retrieved_at,
            "items": [{"quality": {"complete_sessions": [latest]}}],
        },
    )
    monkeypatch.setattr(etf_targets, "_load_daily_close_panel", lambda path, spec: closes)
    monkeypatch.setattr(etf_targets, "compute_monthly_targets", _fixed_targets)
    monkeypatch.setattr(
        etf_targets,
        "_utc_now",
        lambda: datetime.fromisoformat(now).astimezone(UTC),
    )
    lock_path = tmp_path / "test-preregistration-lock.json"
    lock_path.write_text("{}\n", encoding="utf-8")
    binding = etf_targets.ForwardPreregistrationBinding(
        lock_path=lock_path,
        lock_sha256=_sha256(lock_path),
        implementation_bindings=[
            {
                "path": "open_composer/adapters/execution/etf_structural_target_weights.py",
                "sha256": "a" * 64,
            }
        ],
    )
    monkeypatch.setattr(
        etf_targets,
        "_require_preregistration_binding",
        lambda **kwargs: binding,
    )
    return manifest


def _fixed_targets(closes, spec):
    columns = list(closes.columns)
    rows = []
    records = []
    for decision, execution, spy, ief, bil, target_hash in [
        ("2026-05-29", "2026-06-01", 0.4, 0.15, 0.45, "1" * 64),
        ("2026-06-30", "2026-07-01", 0.4, 0.15, 0.45, "2" * 64),
    ]:
        weights = {symbol: 0.0 for symbol in columns}
        weights.update({"SPY": spy, "IEF": ief, "BIL": bil})
        rows.append(weights)
        records.append(
            {
                "iter_id": "frozen_reference",
                "candidate_id": "R10D01",
                "decision_session": decision,
                "execution_session": execution,
                "target_sha256": target_hash,
            }
        )
    return pd.DataFrame(rows, index=pd.to_datetime(["2026-06-01", "2026-07-01"])), records


def _changed_targets(closes, spec):
    targets, records = _fixed_targets(closes, spec)
    targets.loc[pd.Timestamp("2026-07-01"), "SPY"] = 0.3
    targets.loc[pd.Timestamp("2026-07-01"), "BIL"] = 0.55
    records[-1]["target_sha256"] = "3" * 64
    return targets, records


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_spec(root: Path, source: Path) -> Path:
    destination = root / "strategy_specs" / "drafts" / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    return destination


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
