from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from open_composer.models.event import EventRecord
from open_composer.research.pit_semantic_theme_forward import (
    FORWARD_DATA_DIR,
    FORWARD_LOCK_PATH,
    FORWARD_REPORT_DIR,
    ForwardSourcePacket,
    _safe_error,
    build_forward_source_packets,
    forward_lock_binding_paths,
    freeze_pit_semantic_theme_forward,
    observe_pit_semantic_theme_forward,
    retry_pit_semantic_theme_forward_llm,
    verify_pit_semantic_theme_forward_lock,
)

ROOT = Path(__file__).resolve().parents[1]


class ValidThemeBackend:
    def infer(self, *, model, prompt, input_payload, output_schema):
        del model, prompt, output_schema
        packet = input_payload["source_packet"]
        entities = input_payload["allowed_entities"][:2]
        return {
            "theme_id": input_payload["required_theme_id"],
            "entities": entities,
            "relationships": [
                {
                    "source_entity": entities[0],
                    "target_entity": entities[1],
                    "relationship_type": "infrastructure",
                    "evidence_packet_ids": [packet["packet_id"]],
                }
            ],
            "direction": 0.75,
            "confidence": 0.8,
            "novelty": 0.7,
            "horizon_sessions": 8,
            "evidence_packet_ids": [packet["packet_id"]],
            "unknown_fields": [],
        }


class UnboundThemeBackend:
    def infer(self, *, model, prompt, input_payload, output_schema):
        del model, prompt, output_schema
        packet = input_payload["source_packet"]
        return {
            "theme_id": input_payload["required_theme_id"],
            "entities": ["UNBOUND"],
            "relationships": [],
            "direction": 0.9,
            "confidence": 0.9,
            "novelty": 0.9,
            "horizon_sessions": 5,
            "evidence_packet_ids": [packet["packet_id"]],
            "unknown_fields": [],
        }


class AuthFailureThemeBackend:
    def infer(self, *, model, prompt, input_payload, output_schema):
        del model, prompt, input_payload, output_schema
        raise RuntimeError(
            "Incorrect API key provided: sk-live-secret-fragment; code=invalid_api_key"
        )


def test_forward_packet_schema_and_model_require_complete_pit_identity() -> None:
    schema = json.loads(
        (ROOT / "schemas/pit_semantic_theme_forward_packet.schema.json").read_text(encoding="utf-8")
    )
    required = set(schema["required"])
    assert {
        "packet_id",
        "published_at",
        "fetched_at",
        "first_seen_at",
        "visible_at",
        "source",
        "source_url",
        "input_hash",
        "schema_version",
        "rights_scope",
    }.issubset(required)
    assert schema["properties"]["acquisition_mode"] == {"const": "live_api_forward_only"}
    assert required == set(ForwardSourcePacket.model_json_schema()["required"])


def test_source_packets_group_provider_symbols_and_bind_first_seen() -> None:
    epoch_start = datetime(2026, 8, 5, 0, tzinfo=UTC)
    observed_at = datetime(2026, 8, 5, 1, tzinfo=UTC)
    events = _news_events(fetched_at=datetime(2026, 8, 5, 0, 30, tzinfo=UTC))

    packets = build_forward_source_packets(
        events,
        epoch_id="r12fwd_test",
        epoch_started_at=epoch_start,
        observed_at=observed_at,
    )

    assert len(packets) == 1
    assert packets[0].symbols == ["NVDA", "VRT"]
    assert packets[0].fetched_at == datetime(2026, 8, 5, 0, 30, tzinfo=UTC)
    assert packets[0].visible_at == packets[0].fetched_at
    assert packets[0].packet_id == f"r12pkt_{packets[0].input_hash[:24]}"


def test_forward_lock_binds_contracts_specs_and_implementation(tmp_path: Path) -> None:
    _copy_forward_lock_inputs(tmp_path)

    result = freeze_pit_semantic_theme_forward(
        tmp_path,
        created_at=datetime(2026, 8, 5, 0, tzinfo=UTC),
    )
    verified = verify_pit_semantic_theme_forward_lock(
        tmp_path,
        observed_at=datetime(2026, 8, 5, 1, tzinfo=UTC),
    )

    assert result.lock_path == tmp_path / FORWARD_LOCK_PATH
    assert result.epoch_id == verified["epoch_id"]
    assert verified["lock"]["historical_backfill_credit"] is False
    assert verified["lock"]["broker_writes"] is False
    assert len(verified["lock"]["specs"]) == 8

    prompt = tmp_path / "prompts/pit_semantic_theme_r12_factor_v1.txt"
    prompt.write_text(prompt.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
    with pytest.raises(ValueError, match="binding changed"):
        verify_pit_semantic_theme_forward_lock(
            tmp_path,
            observed_at=datetime(2026, 8, 5, 1, tzinfo=UTC),
        )


def test_forward_observation_materializes_roles_and_exact_d01_fallback(
    tmp_path: Path,
) -> None:
    _prepare_forward_workspace(tmp_path)
    observed_at = datetime(2026, 8, 5, 1, tzinfo=UTC)

    result = observe_pit_semantic_theme_forward(
        tmp_path,
        backend_name="test",
        model="test-structured-model",
        observed_at=observed_at,
        events=_news_events(fetched_at=datetime(2026, 8, 5, 0, 30, tzinfo=UTC)),
        backend=ValidThemeBackend(),
        price_frames={
            "QQQ": _price_frame(100.0, 0.0010),
            "NVDA": _price_frame(120.0, 0.0040),
            "VRT": _price_frame(80.0, 0.0030),
        },
    )

    assert result.status == "published"
    assert result.source_packet_count == 1
    assert result.selected_theme_count == 1
    assert result.llm_factor_count == 2
    assert result.observation_path is not None
    payload = result.payload
    assert payload["observation_only"] is True
    assert payload["broker_writes"] is False
    assert payload["semantic_stock_budget"] == 0.0
    roles = {row["candidate_id"]: row for row in payload["candidate_roles"]}
    assert set(roles) == {
        "R12D01",
        "R12D02",
        "R12M01",
        "R12M02",
        "R12L01",
        "R12C01",
        "R12F01",
        "R12P01",
    }
    assert {row["target_sha256"] for row in roles.values()} == {
        payload["d01_target_snapshot"]["target_sha256"]
    }
    assert roles["R12F01"]["status"] == "exact_fallback"
    assert roles["R12M01"]["status"] == "stopped"
    assert roles["R12L01"]["valid_llm_theme_count"] == 1
    assert (
        payload["placebo"]["mapping"][0]["source_symbol"]
        != payload["placebo"]["mapping"][0]["placebo_symbol"]
    )
    assert (tmp_path / FORWARD_DATA_DIR / "event-features.jsonl").exists()
    assert (tmp_path / FORWARD_DATA_DIR / "theme-factors.jsonl").exists()
    assert (tmp_path / FORWARD_DATA_DIR / "placebo-theme-factors.jsonl").exists()
    assert (tmp_path / FORWARD_REPORT_DIR / "latest-observation.json").exists()

    repeated = observe_pit_semantic_theme_forward(
        tmp_path,
        backend_name="test",
        model="test-structured-model",
        observed_at=observed_at,
        events=_news_events(fetched_at=datetime(2026, 8, 5, 0, 30, tzinfo=UTC)),
        backend=ValidThemeBackend(),
        price_frames={
            "QQQ": _price_frame(100.0, 0.0010),
            "NVDA": _price_frame(120.0, 0.0040),
            "VRT": _price_frame(80.0, 0.0030),
        },
    )
    assert repeated.status == "no_new_packets"
    ledger = (tmp_path / FORWARD_REPORT_DIR / "observation-ledger.jsonl").read_text(
        encoding="utf-8"
    )
    assert len([line for line in ledger.splitlines() if line.strip()]) == 1


def test_invalid_llm_entity_fails_to_exact_fallback_without_factor_rows(
    tmp_path: Path,
) -> None:
    _prepare_forward_workspace(tmp_path)
    observed_at = datetime(2026, 8, 5, 1, tzinfo=UTC)

    result = observe_pit_semantic_theme_forward(
        tmp_path,
        backend_name="test",
        model="test-structured-model",
        observed_at=observed_at,
        events=_news_events(fetched_at=datetime(2026, 8, 5, 0, 30, tzinfo=UTC)),
        backend=UnboundThemeBackend(),
        price_frames={
            "QQQ": _price_frame(100.0, 0.0010),
            "NVDA": _price_frame(120.0, 0.0040),
            "VRT": _price_frame(80.0, 0.0030),
        },
    )

    assert result.status == "published"
    assert result.llm_factor_count == 0
    llm = result.payload["llm_materialization"]["results"]
    assert llm[0]["status"] == "fallback"
    assert llm[0]["fallback_candidate_id"] == "R12D02_then_R12D01"
    roles = {row["candidate_id"]: row for row in result.payload["candidate_roles"]}
    assert roles["R12L01"]["status"] == "fallback"
    assert (tmp_path / FORWARD_DATA_DIR / "theme-factors.jsonl").read_text(encoding="utf-8") == ""


def test_llm_retry_reuses_bound_packets_without_new_forward_session_credit(
    tmp_path: Path,
) -> None:
    _prepare_forward_workspace(tmp_path)
    observed_at = datetime(2026, 8, 5, 1, tzinfo=UTC)
    prices = {
        "QQQ": _price_frame(100.0, 0.0010),
        "NVDA": _price_frame(120.0, 0.0040),
        "VRT": _price_frame(80.0, 0.0030),
    }
    observation = observe_pit_semantic_theme_forward(
        tmp_path,
        backend_name="test",
        model="test-structured-model",
        observed_at=observed_at,
        events=_news_events(fetched_at=datetime(2026, 8, 5, 0, 30, tzinfo=UTC)),
        backend=AuthFailureThemeBackend(),
        price_frames=prices,
    )
    assert observation.llm_factor_count == 0
    source_index = tmp_path / FORWARD_DATA_DIR / "source-packet-index.jsonl"
    original_source_bytes = source_index.read_bytes()
    original_packet = json.loads(original_source_bytes)
    original_first_seen = original_packet["first_seen_at"]

    failed_retry = retry_pit_semantic_theme_forward_llm(
        tmp_path,
        backend_name="test",
        model="test-structured-model",
        observed_at=datetime(2026, 8, 5, 2, tzinfo=UTC),
        backend=AuthFailureThemeBackend(),
    )
    assert failed_retry.status == "published"
    assert failed_retry.attempted_packet_count == 1
    assert failed_retry.valid_factor_count == 0
    assert failed_retry.payload["forward_session_credit"] is False
    assert failed_retry.payload["source_packet_credit"] == 0
    persisted_failure = failed_retry.retry_path.read_text(encoding="utf-8")
    assert "sk-live-secret-fragment" not in persisted_failure
    assert "credentials not persisted" in persisted_failure

    successful_retry = retry_pit_semantic_theme_forward_llm(
        tmp_path,
        backend_name="test",
        model="test-structured-model",
        observed_at=datetime(2026, 8, 5, 3, tzinfo=UTC),
        backend=ValidThemeBackend(),
    )
    assert successful_retry.status == "published"
    assert successful_retry.attempted_packet_count == 1
    assert successful_retry.valid_factor_count == 2
    result = successful_retry.payload["results"][0]
    assert result["status"] == "valid"
    assert result["attempt_number"] == 2
    assert result["source_observation_id"] == observation.observation_id
    assert successful_retry.payload["source_evidence"][0]["packet_ids"] == [
        original_packet["packet_id"]
    ]

    repeated = retry_pit_semantic_theme_forward_llm(
        tmp_path,
        backend_name="test",
        model="test-structured-model",
        observed_at=datetime(2026, 8, 5, 4, tzinfo=UTC),
        backend=ValidThemeBackend(),
    )
    assert repeated.status == "no_pending_llm_packets"
    assert source_index.read_bytes() == original_source_bytes
    assert (
        json.loads(source_index.read_text(encoding="utf-8"))["first_seen_at"] == original_first_seen
    )
    observation_ledger = tmp_path / FORWARD_REPORT_DIR / "observation-ledger.jsonl"
    assert len(observation_ledger.read_text(encoding="utf-8").splitlines()) == 1
    retry_ledger = tmp_path / FORWARD_REPORT_DIR / "llm-retry-ledger.jsonl"
    assert len(retry_ledger.read_text(encoding="utf-8").splitlines()) == 2


def test_tampered_lock_rejects_before_forward_evidence_write(tmp_path: Path) -> None:
    _prepare_forward_workspace(tmp_path)
    prompt = tmp_path / "prompts/pit_semantic_theme_r12_factor_v1.txt"
    prompt.write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match="binding changed"):
        observe_pit_semantic_theme_forward(
            tmp_path,
            backend_name="test",
            observed_at=datetime(2026, 8, 5, 1, tzinfo=UTC),
            events=_news_events(fetched_at=datetime(2026, 8, 5, 0, 30, tzinfo=UTC)),
            backend=ValidThemeBackend(),
            price_frames={},
        )

    assert not (tmp_path / FORWARD_DATA_DIR).exists()
    assert not (tmp_path / FORWARD_REPORT_DIR).exists()


def test_provider_auth_errors_never_persist_key_material() -> None:
    error = RuntimeError(
        "Incorrect API key provided: sk-live-secret-fragment; code=invalid_api_key"
    )
    rendered = _safe_error(error)
    assert "sk-live" not in rendered
    assert "secret-fragment" not in rendered
    assert "credentials not persisted" in rendered


def _prepare_forward_workspace(root: Path) -> None:
    _copy_forward_lock_inputs(root)
    freeze_pit_semantic_theme_forward(
        root,
        created_at=datetime(2026, 8, 5, 0, tzinfo=UTC),
    )
    target = root / "reports/execution/us_pit_semantic_theme_r12_d01-target-weights.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for symbol, weight in {"TQQQ": 0.8, "QQQ": 0.0, "SOXS": 0.0, "BIL": 0.0}.items():
        rows.append(
            {
                "signal_session": "2026-08-04",
                "rebalance_session": "2026-08-05",
                "symbol": symbol,
                "target_weight": weight,
                "state": "equity_pass:risk_on",
            }
        )
    target.write_text(
        json.dumps(
            {
                "strategy_name": "us_pit_semantic_theme_r12_d01",
                "acquisition_tier": "paper_ready_live",
                "route_label": "locked-test-route",
                "parity_check": {"status": "pass", "blockers": []},
                "target_weights": rows,
            }
        ),
        encoding="utf-8",
    )


def _copy_forward_lock_inputs(root: Path) -> None:
    for relative in forward_lock_binding_paths():
        source = ROOT / relative
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _news_events(*, fetched_at: datetime) -> list[EventRecord]:
    common = {
        "source": "alpaca_news",
        "published_at": datetime(2026, 8, 4, 20, tzinfo=UTC),
        "fetched_at": fetched_at,
        "visible_at": fetched_at,
        "first_seen_at": fetched_at,
        "revision": "provider_current_version",
        "revision_id": "2026-08-04T20:05:00+00:00",
        "version_id": "200:2026-08-04T20:05:00+00:00",
        "rights": "provider_terms_apply",
        "rights_scope": "internal_forward_feature_research_only",
        "availability_quality": "collector_fetch_time_first_seen",
        "availability_basis": "local_collector_first_seen_not_provider_created_at",
        "acquisition_mode": "live_api_forward_only",
        "event_type": "company_news",
        "title": "AI data center infrastructure supplier wins large order",
        "summary": "NVDA and VRT infrastructure demand accelerated through a new contract.",
        "url": "https://example.test/200",
        "sentiment": "unknown",
        "relevance_score": 1.0,
        "raw": {
            "provider_id": "200",
            "provider_symbols": ["NVDA", "VRT"],
            "provider_source": "benzinga",
            "content_requested": False,
        },
    }
    return [
        EventRecord(
            id="alpaca-news-200-nvda",
            symbol="NVDA",
            dedupe_key="alpaca_news:200:NVDA",
            **common,
        ),
        EventRecord(
            id="alpaca-news-200-vrt",
            symbol="VRT",
            dedupe_key="alpaca_news:200:VRT",
            **common,
        ),
    ]


def _price_frame(base: float, daily_growth: float) -> pd.DataFrame:
    sessions = pd.bdate_range(end="2026-08-04", periods=80, tz="UTC")
    closes = [base * ((1.0 + daily_growth) ** index) for index in range(len(sessions))]
    volumes = [5_000_000.0] * (len(sessions) - 1) + [6_000_000.0]
    return pd.DataFrame(
        {
            "timestamp": sessions,
            "open": [value * 0.999 for value in closes],
            "high": [value * 1.01 for value in closes],
            "low": [value * 0.99 for value in closes],
            "close": closes,
            "volume": volumes,
        }
    )
