from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_composer.adapters.broker import alpaca_paper
from open_composer.market_calendar import next_us_equity_session
from open_composer.models.paper import PaperOrderRecord
from open_composer.paper_tca import (
    LOCAL_HASH_AUTHENTICITY_CAVEAT,
    PaperTCAValidationError,
    build_paper_tca_report,
    ingest_paper_tca_observation,
)
from open_composer.storage import append_jsonl

STRATEGY = "paper_tca_test"
SPEC_HASH = "a" * 64
POLICY_ID = "opg_limit_v1"
POLICY_HASH = "b" * 64


def test_paper_tca_rejects_future_timestamp(tmp_path: Path) -> None:
    as_of = datetime(2026, 7, 20, 16, tzinfo=UTC)
    observation = _observation(tmp_path, 1, decision_at=as_of + timedelta(minutes=1))

    with pytest.raises(PaperTCAValidationError, match="timestamp_in_future"):
        _ingest(tmp_path, observation, as_of=as_of)


def test_paper_tca_rejects_artifact_hash_mismatch(tmp_path: Path) -> None:
    as_of = datetime(2026, 7, 20, 18, tzinfo=UTC)
    observation = _observation(
        tmp_path,
        1,
        decision_at=datetime(2026, 7, 20, 14, tzinfo=UTC),
    )
    observation["broker_receipt_sha256"] = "0" * 64

    with pytest.raises(PaperTCAValidationError, match="broker_receipt_hash_mismatch"):
        _ingest(tmp_path, observation, as_of=as_of)

    receipt_path = tmp_path / str(observation["broker_receipt_path"])
    observation["broker_receipt_sha256"] = _sha256(receipt_path)
    observation["fill_price"] = 601.0
    with pytest.raises(PaperTCAValidationError, match="broker_receipt_binding_mismatch"):
        _ingest(tmp_path, observation, as_of=as_of)
    observation["fill_price"] = 600.75
    _ingest(tmp_path, observation, as_of=as_of)
    receipt_path.write_text('{"changed":true}\n', encoding="utf-8")
    report = _report(
        tmp_path,
        epoch=datetime(2026, 7, 20, 13, tzinfo=UTC),
        as_of=as_of,
        minimum_observations=1,
    )
    assert report["valid_observation_count"] == 0
    assert report["excluded_observations"][0]["reasons"] == ["broker_receipt_hash_mismatch"]
    with pytest.raises(PaperTCAValidationError, match="broker_receipt_hash_mismatch"):
        _ingest(tmp_path, observation, as_of=as_of)


def test_paper_tca_rejects_receipt_absent_from_sync_manifest(tmp_path: Path) -> None:
    as_of = datetime(2026, 7, 20, 18, tzinfo=UTC)
    observation = _observation(
        tmp_path,
        1,
        decision_at=datetime(2026, 7, 20, 14, tzinfo=UTC),
    )
    for path in (tmp_path / "reports" / "paper" / "broker_receipts" / "syncs").glob("*.json"):
        path.unlink()

    with pytest.raises(PaperTCAValidationError, match="broker_receipt_not_in_sync"):
        _ingest(tmp_path, observation, as_of=as_of)


def test_paper_tca_append_is_idempotent_and_rejects_conflicting_ids(
    tmp_path: Path,
) -> None:
    as_of = datetime(2026, 7, 20, 18, tzinfo=UTC)
    first = _observation(
        tmp_path,
        1,
        decision_at=datetime(2026, 7, 20, 14, tzinfo=UTC),
    )

    initial = _ingest(tmp_path, first, as_of=as_of)
    duplicate = _ingest(tmp_path, first, as_of=as_of)

    assert initial.appended is True
    assert duplicate.appended is False
    assert initial.observation_id == duplicate.observation_id
    assert len(initial.ledger_path.read_text(encoding="utf-8").splitlines()) == 1

    conflict = _observation(
        tmp_path,
        2,
        order_id=first["order_id"],
        decision_at=datetime(2026, 7, 20, 15, tzinfo=UTC),
    )
    with pytest.raises(PaperTCAValidationError, match="duplicate_order_id"):
        _ingest(tmp_path, conflict, as_of=as_of)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("qty", float("nan"), "qty_invalid"),
        ("fill_price", 0.0, "fill_price_invalid"),
        ("filled_at", "2026-07-20T13:00:00+00:00", "timestamp_order_invalid"),
    ],
)
def test_paper_tca_rejects_invalid_numbers_and_timestamp_order(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
) -> None:
    as_of = datetime(2026, 7, 20, 18, tzinfo=UTC)
    observation = _observation(
        tmp_path,
        1,
        decision_at=datetime(2026, 7, 20, 14, tzinfo=UTC),
    )
    observation[field] = value

    with pytest.raises(PaperTCAValidationError, match=error):
        _ingest(tmp_path, observation, as_of=as_of)


def test_paper_tca_report_excludes_stale_observations(tmp_path: Path) -> None:
    as_of = datetime(2026, 8, 1, tzinfo=UTC)
    stale = _observation(
        tmp_path,
        1,
        decision_at=datetime(2026, 7, 1, 14, tzinfo=UTC),
    )
    current = _observation(
        tmp_path,
        2,
        decision_at=datetime(2026, 7, 20, 14, tzinfo=UTC),
    )
    _ingest(tmp_path, stale, as_of=as_of)
    _ingest(tmp_path, current, as_of=as_of)

    report = _report(
        tmp_path,
        epoch=datetime(2026, 7, 15, tzinfo=UTC),
        as_of=as_of,
        minimum_observations=1,
    )

    assert report["valid_observation_count"] == 1
    assert report["excluded_observation_count"] == 1
    assert report["excluded_observations"][0]["reasons"] == ["before_epoch"]
    assert report["minimum_observations"] == 30
    assert report["paper_tca_pass"] is False


@pytest.mark.slow
def test_paper_tca_report_passes_with_thirty_bound_observations(tmp_path: Path) -> None:
    epoch = datetime(2026, 7, 20, 13, tzinfo=UTC)
    sessions = _sessions(date(2026, 7, 20), count=10)
    as_of = datetime(2026, 8, 5, 20, tzinfo=UTC)
    for index in range(30):
        session = sessions[index // 3]
        observation = _observation(
            tmp_path,
            index,
            decision_at=datetime(
                session.year,
                session.month,
                session.day,
                13,
                index % 3 * 3,
                tzinfo=UTC,
            ),
        )
        _ingest(tmp_path, observation, as_of=as_of)

    report = _report(tmp_path, epoch=epoch, as_of=as_of)

    assert report["minimum_observations"] == 30
    assert report["valid_observation_count"] == 30
    assert report["excluded_observation_count"] == 0
    assert report["distinct_session_count"] == 10
    assert all(report["quality_checks"].values())
    assert report["matched_paper_tca_pass"] is True
    assert report["status"] == "pass"
    assert report["local_hash_authenticity_caveat"] == LOCAL_HASH_AUTHENTICITY_CAVEAT


def test_thirty_same_session_tca_observations_do_not_pass(tmp_path: Path) -> None:
    epoch = datetime(2026, 7, 20, 12, tzinfo=UTC)
    as_of = datetime(2026, 7, 20, 20, tzinfo=UTC)
    for index in range(30):
        observation = _observation(
            tmp_path,
            index,
            decision_at=epoch + timedelta(minutes=index * 3),
        )
        _ingest(tmp_path, observation, as_of=as_of)

    report = _report(tmp_path, epoch=epoch, as_of=as_of)

    assert report["valid_observation_count"] == 30
    assert report["distinct_session_count"] == 1
    assert report["quality_checks"]["minimum_distinct_sessions"] is False
    assert report["matched_paper_tca_pass"] is False


def test_generated_alpaca_sync_receipt_is_tca_ingestible(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    decision_at = now - timedelta(minutes=10)
    submitted_at = now - timedelta(minutes=8)
    filled_at = now - timedelta(minutes=7)
    authorization_id = "auth_" + "c" * 16
    authorization_hash = "d" * 64
    local = PaperOrderRecord(
        id="generated-order",
        signal_id="generated-signal",
        client_order_id="oc-generated-signal",
        strategy_name=STRATEGY,
        strategy_id=STRATEGY,
        version_id="ver_aaaaaaaaaaaa",
        spec_hash=SPEC_HASH,
        execution_policy_id=POLICY_ID,
        execution_policy_hash=POLICY_HASH,
        order_style="opg_limit",
        time_in_force="opg",
        authorization_id=authorization_id,
        authorization_hash=authorization_hash,
        authorization_kind="canary",
        signal_record_hash="e" * 64,
        signal_log_path="signal_logs/generated.jsonl",
        order_intent_id="intent_aaaaaaaaaaaaaaaa",
        order_intent_hash="f" * 64,
        symbol="SPY",
        side="buy",
        qty=1,
        reference_price=600,
        estimated_notional=600,
        status="submitted",
        submitted_at=submitted_at,
    )
    append_jsonl(tmp_path / "reports" / "paper" / "orders.jsonl", [local])

    class Client:
        _base_url = alpaca_paper.ALPACA_PAPER_ORIGIN
        _sandbox = True

        def get_account(self):
            return SimpleNamespace(id="paper-account")

        def get_orders(self, filter=None):
            return [
                SimpleNamespace(
                    id="generated-order",
                    client_order_id="oc-generated-signal",
                    symbol="SPY",
                    side="buy",
                    qty="1",
                    filled_qty="1",
                    filled_avg_price="600.75",
                    status="filled",
                    order_type="limit",
                    time_in_force="opg",
                    limit_price="601",
                    submitted_at=submitted_at,
                    accepted_at=submitted_at,
                    filled_at=filled_at,
                )
            ]

    alpaca_paper.sync_paper_orders(
        tmp_path,
        client=alpaca_paper._mark_verified_paper_client(Client()),
    )
    sync = json.loads(
        (tmp_path / "reports" / "paper" / "broker_receipts" / "latest-sync.json").read_text()
    )
    receipt_path = tmp_path / sync["order_receipts"][0]["path"]
    receipt = json.loads(receipt_path.read_text())
    source = {
        "strategy_name": STRATEGY,
        "spec_hash": SPEC_HASH,
        "execution_policy_id": POLICY_ID,
        "execution_policy_hash": POLICY_HASH,
        "authorization_id": authorization_id,
        "authorization_hash": authorization_hash,
        "broker_account_id_hash": receipt["broker_account_id_hash"],
        "paper": True,
        "order_id": "generated-order",
        "client_order_id": "oc-generated-signal",
        "symbol": "SPY",
        "side": "buy",
        "qty": 1,
        "order_style": "opg_limit",
        "time_in_force": "opg",
        "decision_price": 600,
        "arrival_price": 600.25,
        "decision_at": decision_at.isoformat(),
        "submitted_at": submitted_at.isoformat(),
    }
    source_path = tmp_path / "evidence" / "generated-source.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(json.dumps(source, sort_keys=True) + "\n")
    observation = {
        **source,
        "fill_id": receipt["fill_id"],
        "fill_price": receipt["fill_price"],
        "filled_at": receipt["filled_at"],
        "observed_at": receipt["observed_at"],
        "source_packet_path": source_path.relative_to(tmp_path).as_posix(),
        "source_packet_sha256": _sha256(source_path),
        "broker_receipt_path": receipt_path.relative_to(tmp_path).as_posix(),
        "broker_receipt_sha256": _sha256(receipt_path),
    }

    result = _ingest(tmp_path, observation, as_of=now + timedelta(minutes=1))
    assert result.appended is True
    assert result.record["authorization_id"] == authorization_id


def _ingest(
    root: Path,
    observation: dict[str, object],
    *,
    as_of: datetime,
):
    return ingest_paper_tca_observation(
        observation,
        root=root,
        strategy_name=STRATEGY,
        spec_hash=SPEC_HASH,
        execution_policy_id=POLICY_ID,
        execution_policy_hash=POLICY_HASH,
        as_of=as_of,
    )


def _report(
    root: Path,
    *,
    epoch: datetime,
    as_of: datetime,
    minimum_observations: int = 30,
) -> dict[str, object]:
    return build_paper_tca_report(
        root=root,
        strategy_name=STRATEGY,
        spec_hash=SPEC_HASH,
        execution_policy_id=POLICY_ID,
        execution_policy_hash=POLICY_HASH,
        epoch=epoch,
        as_of=as_of,
        minimum_observations=minimum_observations,
    )


def _observation(
    root: Path,
    index: int,
    *,
    decision_at: datetime,
    order_id: object | None = None,
) -> dict[str, object]:
    order = str(order_id or f"order-{index}")
    submitted_at = decision_at + timedelta(minutes=1)
    filled_at = submitted_at + timedelta(minutes=1)
    observed_at = filled_at + timedelta(minutes=1)
    qty = 2.0
    decision_price = 600.0
    arrival_price = 600.25
    official_open_price = 600.5
    fill_price = 600.75
    evidence_dir = root / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    source_path = evidence_dir / f"source-{index}.json"
    client_order_id = f"oc-signal-{index}"
    authorization_id = "auth_" + "c" * 16
    authorization_hash = "d" * 64
    account_hash = "f" * 64
    order_style = "opg_limit"
    time_in_force = "opg"
    source = {
        "strategy_name": STRATEGY,
        "spec_hash": SPEC_HASH,
        "execution_policy_id": POLICY_ID,
        "execution_policy_hash": POLICY_HASH,
        "authorization_id": authorization_id,
        "authorization_hash": authorization_hash,
        "broker_account_id_hash": account_hash,
        "paper": True,
        "order_id": order,
        "client_order_id": client_order_id,
        "symbol": "SPY",
        "side": "buy",
        "qty": qty,
        "order_style": order_style,
        "time_in_force": time_in_force,
        "decision_price": decision_price,
        "arrival_price": arrival_price,
        "official_open_price": official_open_price,
        "decision_at": decision_at.isoformat(),
        "submitted_at": submitted_at.isoformat(),
    }
    broker_order = {
        "id": order,
        "client_order_id": client_order_id,
        "symbol": "SPY",
        "side": "buy",
        "qty": qty,
        "filled_qty": qty,
        "filled_avg_price": fill_price,
        "status": "filled",
        "order_type": "limit",
        "time_in_force": time_in_force,
        "limit_price": 601.0,
        "submitted_at": submitted_at.isoformat(),
        "accepted_at": submitted_at.isoformat(),
        "filled_at": filled_at.isoformat(),
        "updated_at": filled_at.isoformat(),
    }
    local_order = PaperOrderRecord(
        id=order,
        signal_id=f"signal-{index}",
        client_order_id=client_order_id,
        strategy_name=STRATEGY,
        strategy_id=STRATEGY,
        version_id="ver_aaaaaaaaaaaa",
        spec_hash=SPEC_HASH,
        execution_policy_id=POLICY_ID,
        execution_policy_hash=POLICY_HASH,
        order_style=order_style,
        time_in_force=time_in_force,
        authorization_id=authorization_id,
        authorization_hash=authorization_hash,
        authorization_kind="canary",
        signal_record_hash=hashlib.sha256(f"signal-{index}".encode()).hexdigest(),
        signal_log_path=f"signal_logs/signal-{index}.jsonl",
        order_intent_id=f"intent_{index:016x}",
        order_intent_hash=hashlib.sha256(f"intent-{index}".encode()).hexdigest(),
        symbol="SPY",
        side="buy",
        qty=qty,
        reference_price=decision_price,
        estimated_notional=qty * decision_price,
        status="submitted",
        submitted_at=submitted_at,
    )
    append_jsonl(root / "reports" / "paper" / "orders.jsonl", [local_order])
    receipt_path = alpaca_paper._write_immutable_broker_receipt(
        root,
        broker_order,
        local_order,
        broker_account_hash=account_hash,
        captured_at=observed_at,
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_refs = []
    for order_directory in sorted(
        (root / "reports" / "paper" / "broker_receipts" / "orders").iterdir()
    ):
        candidates = [
            json.loads(path.read_text(encoding="utf-8")) for path in order_directory.glob("*.json")
        ]
        latest = max(candidates, key=lambda item: int(item["sequence"]))
        latest_path = order_directory / f"{latest['state_sha256']}.json"
        receipt_refs.append(
            {
                "order_id": latest["order_id"],
                "path": latest_path.relative_to(root).as_posix(),
                "sha256": _sha256(latest_path),
                "state_sha256": latest["state_sha256"],
            }
        )
    alpaca_paper._write_broker_sync_receipt(
        root,
        captured_at=observed_at,
        broker_account_hash=account_hash,
        receipts=receipt_refs,
        local_order_count=len(receipt_refs),
    )
    source_path.write_text(json.dumps(source, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "strategy_name": STRATEGY,
        "spec_hash": SPEC_HASH,
        "execution_policy_id": POLICY_ID,
        "execution_policy_hash": POLICY_HASH,
        "authorization_id": authorization_id,
        "authorization_hash": authorization_hash,
        "broker_account_id_hash": account_hash,
        "paper": True,
        "order_id": order,
        "fill_id": receipt["fill_id"],
        "client_order_id": client_order_id,
        "symbol": "SPY",
        "side": "buy",
        "qty": qty,
        "order_style": order_style,
        "time_in_force": time_in_force,
        "decision_price": decision_price,
        "arrival_price": arrival_price,
        "official_open_price": official_open_price,
        "fill_price": fill_price,
        "decision_at": decision_at.isoformat(),
        "submitted_at": submitted_at.isoformat(),
        "filled_at": filled_at.isoformat(),
        "observed_at": observed_at.isoformat(),
        "source_packet_path": source_path.relative_to(root).as_posix(),
        "source_packet_sha256": _sha256(source_path),
        "broker_receipt_path": receipt_path.relative_to(root).as_posix(),
        "broker_receipt_sha256": _sha256(receipt_path),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sessions(start: date, *, count: int) -> list[date]:
    sessions = [start]
    while len(sessions) < count:
        sessions.append(next_us_equity_session(sessions[-1]))
    return sessions
