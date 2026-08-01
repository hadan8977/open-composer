from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from open_composer.models.paper import PaperOrderIntent, PaperOrderRecord
from open_composer.models.signal import Signal


def test_runtime_signal_and_order_models_cover_operational_schema(repo_root: Path) -> None:
    signal_schema = _schema(repo_root, "signal.schema.json")
    order_schema = _schema(repo_root, "paper_order.schema.json")
    intent_schema = _schema(repo_root, "paper_order_intent.schema.json")
    now = datetime.now(UTC)
    signal = Signal(
        id="sig_audit",
        run_id="run_audit",
        strategy_name="audit_strategy",
        strategy_id="audit_strategy",
        version_id="ver_0123456789ab",
        spec_hash="0" * 64,
        symbol="SPY",
        timeframe="daily",
        timestamp=now,
        action="entry",
        side="buy",
        source="test",
        price=100.0,
        conditions=[],
        lifecycle="active",
        execution_mode="paper_auto",
        fill_assumption="next_bar_open",
        created_at=now,
    )
    intent = PaperOrderIntent(
        id="intent_0123456789abcdef",
        created_at=now,
        client_order_id="oc-sig_audit",
        signal_id=signal.id,
        signal_record_hash="1" * 64,
        signal_log_path="signal_logs/run_audit.jsonl",
        strategy_name=signal.strategy_name,
        version_id=str(signal.version_id),
        spec_hash=str(signal.spec_hash),
        execution_policy_id="policy-audit",
        execution_policy_hash="2" * 64,
        order_style="opg_limit",
        time_in_force="opg",
        authorization_id="auth_0123456789abcdef",
        authorization_hash="3" * 64,
        symbol=signal.symbol,
        side=signal.side,
        qty=1.0,
    )
    order = PaperOrderRecord(
        id="order-audit",
        signal_id=signal.id,
        client_order_id=intent.client_order_id,
        strategy_name=signal.strategy_name,
        strategy_id=signal.strategy_name,
        version_id=signal.version_id,
        spec_hash=signal.spec_hash,
        execution_policy_id=intent.execution_policy_id,
        execution_policy_hash=intent.execution_policy_hash,
        order_style=intent.order_style,
        time_in_force=intent.time_in_force,
        authorization_id=intent.authorization_id,
        authorization_hash=intent.authorization_hash,
        signal_record_hash=intent.signal_record_hash,
        signal_log_path=intent.signal_log_path,
        order_intent_id=intent.id,
        order_intent_hash="4" * 64,
        symbol=signal.symbol,
        side=signal.side,
        qty=1.0,
        status="accepted",
        submitted_at=now,
    )

    _assert_model_matches_schema(signal.model_dump(mode="json"), signal_schema)
    _assert_model_matches_schema(order.model_dump(mode="json"), order_schema)
    _assert_model_matches_schema(intent.model_dump(mode="json"), intent_schema)


def test_frozen_r8_snapshot_is_preserved_as_legacy_v1(repo_root: Path) -> None:
    schema = _schema(repo_root, "alpaca_snapshot_manifest.schema.json")
    manifest = json.loads(
        (
            repo_root / "data" / "research" / "alpaca_spy_dual_trend_r8" / "snapshot-manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"] == {"const": 2}
    assert manifest["schema_version"] == 1
    assert set(manifest) < set(schema["properties"])
    assert manifest["immutable"] is True
    assert manifest["overwrite_allowed"] is False
    item_schema = schema["$defs"]["item"]
    quality_schema = schema["$defs"]["quality"]
    page_schema = schema["$defs"]["page"]
    for item in manifest["items"]:
        assert set(item) < set(item_schema["properties"])
        assert set(item["quality"]) <= set(quality_schema["properties"])
        assert set(quality_schema["required"]) <= set(item["quality"])
        assert item["quality"]["status"] == "complete"
        assert item["quality"]["duplicate_timestamp_count"] == 0
        assert item["quality"]["nonfinite_count"] == 0
        assert item["quality"]["missing_timestamps"] == []
        for page in item["pages"]:
            assert set(page) < set(page_schema["properties"])


def _schema(root: Path, name: str) -> dict[str, object]:
    return json.loads((root / "schemas" / name).read_text(encoding="utf-8"))


def _assert_model_matches_schema(payload: dict[str, object], schema: dict[str, object]) -> None:
    properties = schema["properties"]
    required = schema["required"]
    assert isinstance(properties, dict)
    assert isinstance(required, list)
    assert schema["additionalProperties"] is False
    assert set(payload) == set(properties)
    assert set(required) <= set(payload)
