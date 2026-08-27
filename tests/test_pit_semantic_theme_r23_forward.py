from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from open_composer.models.event import EventRecord
from open_composer.research.pit_semantic_theme_r11 import UNIVERSE
from open_composer.research.pit_semantic_theme_r22 import (
    MODEL_FEATURES,
    build_r22_feature_dataset,
    load_r22_price_panel,
)
from open_composer.research.pit_semantic_theme_r23_forward import (
    FORWARD_DATA_DIR,
    FORWARD_REPORT_DIR,
    HISTORICAL_LOCK_PATH,
    HISTORICAL_REPORT_PATH,
    HISTORICAL_TARGET_LEDGER_PATH,
    LOCKED_PATHS,
    PROMPT_PATH,
    SOURCE_PACKET_CONTRACT,
    SPEC_PATHS,
    _account_snapshot,
    _events_first_seen_in_epoch,
    _intents_payload,
    _target_payload,
    build_r23_forward_feature_dataset,
    build_r23_forward_role_targets,
    build_r23_forward_source_packets,
    build_r23_semantic_diagnostics,
    freeze_pit_semantic_theme_r23_forward,
    observe_pit_semantic_theme_r23_forward,
)

ROOT = Path(__file__).resolve().parents[1]


class _BoundThemeBackend:
    def infer(
        self,
        *,
        model: str,
        prompt: str,
        input_payload: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]:
        del model, prompt, output_schema
        packet_id = input_payload["source_packet"]["packet_id"]
        entities = input_payload["allowed_entities"]
        return {
            "theme_id": input_payload["required_theme_id"],
            "event_type": "commercial_contract",
            "impact_subjects": entities,
            "entities": entities,
            "relationships": [
                {
                    "source_entity": entities[0],
                    "target_entity": entities[1],
                    "relationship_type": "supplier",
                    "evidence_packet_ids": [packet_id],
                }
            ],
            "direction": 0.5,
            "confidence": 0.7,
            "novelty": 0.6,
            "horizon_sessions": 5,
            "evidence_packet_ids": [packet_id],
            "unknown_fields": ["economic_relationship"],
        }


class _AuthFailBackend:
    def __init__(self) -> None:
        self.calls = 0

    def infer(
        self,
        *,
        model: str,
        prompt: str,
        input_payload: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]:
        del model, prompt, input_payload, output_schema
        self.calls += 1
        raise RuntimeError("Error code: 401 invalid_api_key sk-test-sensitive-fragment")


def _event(
    timestamp: datetime,
    *,
    provider_id: str = "42",
    symbols: tuple[str, ...] = ("NVDA", "AMD"),
    linked: bool = True,
) -> EventRecord:
    title = (
        "NVDA supplies AMD for a joint data center launch"
        if linked
        else "NVDA and AMD are mentioned in a market roundup"
    )
    summary = (
        "The supplier contract explicitly affects both companies and expands capacity."
        if linked
        else "The article lists recent market moves without an economic relationship."
    )
    return EventRecord(
        id=f"alpaca-news-{provider_id}-{symbols[0].lower()}",
        source="alpaca_news",
        symbol=symbols[0],
        published_at=timestamp - timedelta(minutes=10),
        fetched_at=timestamp,
        visible_at=timestamp,
        first_seen_at=timestamp,
        revision="provider_current_version",
        revision_id=timestamp.isoformat(),
        version_id=f"{provider_id}:{timestamp.isoformat()}",
        rights="provider_terms_apply",
        rights_scope="internal_forward_feature_research_only",
        availability_quality="collector_fetch_time_first_seen",
        availability_basis="local_collector_first_seen_not_provider_created_at",
        acquisition_mode="live_api_forward_only",
        event_type="company_news",
        title=title,
        summary=summary,
        url=f"https://example.com/{provider_id}",
        sentiment="unknown",
        relevance_score=1.0,
        dedupe_key=f"alpaca_news:{provider_id}:{symbols[0]}",
        raw={
            "provider_id": provider_id,
            "provider_symbols": list(symbols),
        },
    )


def _semantic_price_frames(
    *,
    end: str = "2026-08-05",
    confirmed: bool = True,
) -> dict[str, pd.DataFrame]:
    sessions = pd.bdate_range(end=end, periods=70, tz="UTC")
    frames: dict[str, pd.DataFrame] = {}
    for symbol, start, finish in (
        ("QQQ", 100.0, 104.0),
        ("NVDA", 100.0, 120.0 if confirmed else 102.0),
        ("AMD", 80.0, 100.0 if confirmed else 81.0),
    ):
        close = pd.Series(
            [
                start + (finish - start) * index / (len(sessions) - 1)
                for index in range(len(sessions))
            ]
        )
        volume = pd.Series([1_000_000.0] * len(sessions))
        if confirmed and symbol != "QQQ":
            volume.iloc[-5:] = 3_000_000.0
        frame = pd.DataFrame(
            {
                "timestamp": sessions,
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": volume,
            }
        )
        frame.attrs["data_source_mode"] = "injected"
        frames[symbol] = frame
    return frames


@pytest.mark.slow
def test_forward_features_match_locked_r23_decision_features_without_labels() -> None:
    panel = load_r22_price_panel(ROOT)
    historical = build_r22_feature_dataset(panel)
    forward = build_r23_forward_feature_dataset(panel)
    columns = [
        "decision_position",
        "decision_session",
        "execution_position",
        "execution_session",
        "risk_on",
        "base_risk_on",
        "usd_pressure_active",
        "usd_pressure_transition",
        "fast_price_recovery",
        "ordinary_stress_recovery",
        "usd_pressure_recovery",
        "recovery_boost",
        "semiconductor_leadership",
        "qqq_trend_gap_50",
        "tqqq_momentum_10",
        "tech_breadth_count_100",
        *MODEL_FEATURES,
    ]

    pd.testing.assert_frame_equal(
        forward.loc[:, columns].reset_index(drop=True),
        historical.loc[:, columns].reset_index(drop=True),
        check_exact=True,
    )
    assert "m01_tqqq100_label" not in forward
    assert "m02_survival_label" not in forward


@pytest.mark.slow
def test_forward_targets_cover_all_roles_and_preserve_exact_fallbacks() -> None:
    panel = load_r22_price_panel(ROOT)
    targets, diagnostics = build_r23_forward_role_targets(
        ROOT,
        panel=panel,
        action_session=datetime(2026, 8, 4).date(),
        lock_state={"epoch_id": "unit_epoch", "lock_sha256": "0" * 64},
    )

    assert set(targets) == {
        "R23D01",
        "R23D02",
        "R23M01",
        "R23M02",
        "R23L01",
        "R23C01",
        "R23F01",
        "R23P01",
    }
    assert all(sum(weights.values()) == 1.0 for weights in targets.values())
    assert targets["R23D02"] == targets["R23D01"]
    assert targets["R23L01"] == targets["R23D01"]
    assert targets["R23F01"] == targets["R23M01"]
    assert targets["R23C01"] == targets["R23M01"]
    assert targets["R23P01"] == targets["R23M01"]
    assert diagnostics["training_scope"] == "locked_development_only"
    assert diagnostics["training_end"] == "2025-07-31"
    assert diagnostics["transfer_outcomes_used"] is False
    assert diagnostics["broker_writes"] is False


def test_multi_company_source_price_attention_and_llm_gate_can_become_active() -> None:
    fetched_at = datetime(2026, 8, 3, 22, 0, tzinfo=UTC)
    observed_at = datetime(2026, 8, 5, 22, 0, tzinfo=UTC)
    packets = build_r23_forward_source_packets(
        [_event(fetched_at)],
        epoch_id="r23fwd_unit",
        epoch_started_at=fetched_at - timedelta(minutes=1),
        observed_at=observed_at,
    )

    assert len(packets) == 1
    assert packets[0].packet_contract == SOURCE_PACKET_CONTRACT
    assert packets[0].symbols == ["AMD", "NVDA"]
    diagnostics = build_r23_semantic_diagnostics(
        ROOT,
        packets=packets,
        decision_session=datetime(2026, 8, 5).date(),
        observed_at=observed_at,
        backend_name="unit",
        model="unit-model",
        backend=_BoundThemeBackend(),
        price_frames=_semantic_price_frames(),
    )
    result = diagnostics["llm_materialization"]["results"][0]
    assert result["status"] == "valid"
    assert result["structured_output"]["entities"] == ["AMD", "NVDA"]
    assert result["structured_output"]["evidence_packet_ids"] == [packets[0].packet_id]
    assert result["gate_evaluation"]["admitted"] is True
    assert diagnostics["admitted_deterministic_theme_count"] == 1
    assert diagnostics["llm_materialization"]["admitted_factor_count"] == 1
    assert diagnostics["deterministic_themes"][0]["state"] == "active"
    assert diagnostics["deterministic_themes"][0]["positive_member_breadth"] == 1.0
    assert diagnostics["semantic_stock_budget"] == 0.0
    assert diagnostics["broker_writes"] is False


def test_single_etf_packet_is_context_only_and_never_calls_llm() -> None:
    fetched_at = datetime(2026, 8, 3, 22, 0, tzinfo=UTC)
    observed_at = datetime(2026, 8, 5, 22, 0, tzinfo=UTC)
    packets = build_r23_forward_source_packets(
        [_event(fetched_at, symbols=("SPY",))],
        epoch_id="r23fwd_unit",
        epoch_started_at=fetched_at - timedelta(minutes=1),
        observed_at=observed_at,
    )
    backend = _AuthFailBackend()

    diagnostics = build_r23_semantic_diagnostics(
        ROOT,
        packets=packets,
        decision_session=datetime(2026, 8, 5).date(),
        observed_at=observed_at,
        backend_name="unit",
        model="unit-model",
        backend=backend,
        price_frames=_semantic_price_frames(),
    )

    assert backend.calls == 0
    assert diagnostics["dynamic_company_symbols"] == []
    assert diagnostics["admitted_deterministic_theme_count"] == 0
    assert diagnostics["llm_materialization"]["admitted_factor_count"] == 0
    assert diagnostics["deterministic_themes"][0]["state"] == "seeded"


def test_price_confirmation_cannot_create_a_missing_economic_link() -> None:
    fetched_at = datetime(2026, 8, 3, 22, 0, tzinfo=UTC)
    observed_at = datetime(2026, 8, 5, 22, 0, tzinfo=UTC)
    packets = build_r23_forward_source_packets(
        [_event(fetched_at, linked=False)],
        epoch_id="r23fwd_unit",
        epoch_started_at=fetched_at - timedelta(minutes=1),
        observed_at=observed_at,
    )

    diagnostics = build_r23_semantic_diagnostics(
        ROOT,
        packets=packets,
        decision_session=datetime(2026, 8, 5).date(),
        observed_at=observed_at,
        backend_name="unit",
        model="unit-model",
        backend=_BoundThemeBackend(),
        price_frames=_semantic_price_frames(),
    )

    deterministic = diagnostics["deterministic_themes"][0]
    assert deterministic["confirmed_members"] == ["AMD", "NVDA"]
    assert deterministic["relationships"] == []
    assert deterministic["gate_checks"]["economic_link"] is False
    assert deterministic["admitted"] is False


def test_forward_excludes_news_first_seen_before_epoch() -> None:
    epoch_started_at = datetime(2026, 8, 5, 22, 0, tzinfo=UTC)
    old_event = _event(epoch_started_at - timedelta(seconds=1))
    new_event = _event(epoch_started_at + timedelta(seconds=1))

    eligible = _events_first_seen_in_epoch(
        [old_event, new_event],
        epoch_started_at=epoch_started_at,
    )

    assert eligible == [new_event]


def test_llm_authentication_error_is_redacted_and_stops_repeated_calls() -> None:
    fetched_at = datetime(2026, 8, 3, 22, 0, tzinfo=UTC)
    observed_at = datetime(2026, 8, 5, 22, 0, tzinfo=UTC)
    packets = build_r23_forward_source_packets(
        [
            _event(fetched_at, provider_id="42"),
            _event(fetched_at + timedelta(seconds=1), provider_id="43"),
        ],
        epoch_id="r23fwd_unit",
        epoch_started_at=fetched_at - timedelta(minutes=1),
        observed_at=observed_at,
    )
    backend = _AuthFailBackend()
    diagnostics = build_r23_semantic_diagnostics(
        ROOT,
        packets=packets,
        decision_session=datetime(2026, 8, 5).date(),
        observed_at=observed_at,
        backend_name="openai",
        model="unit-model",
        backend=backend,
        price_frames=_semantic_price_frames(),
    )
    serialized = json.dumps(diagnostics)

    assert backend.calls == 1
    assert "sk-test" not in serialized
    assert "invalid_api_key" not in serialized
    assert "authentication_or_credential_error_redacted" in serialized


def test_forward_account_reconciliation_and_intents_never_authorize_orders(
    tmp_path: Path,
) -> None:
    paper = tmp_path / "reports/paper"
    paper.mkdir(parents=True)
    (paper / "account.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-08-05T22:00:00+00:00",
                "paper": True,
                "equity": 100_000.0,
                "portfolio_value": 100_000.0,
            }
        ),
        encoding="utf-8",
    )
    (paper / "positions.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-08-05T22:00:00+00:00",
                "paper": True,
                "positions": [
                    {
                        "symbol": "TQQQ",
                        "qty": 10.0,
                        "market_value": 1_000.0,
                        "side": "PositionSide.LONG",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    weights = {symbol: float(symbol == "QQQ") for symbol in UNIVERSE}
    targets = {candidate_id: weights for candidate_id in ("R23D01", "R23M01")}
    account = _account_snapshot(tmp_path.resolve(), targets)

    assert account["broker_read_only"] is True
    assert account["broker_writes"] is False
    assert account["by_candidate"]["R23D01"]["paper_position_conflict"] is True
    target = _target_payload(
        candidate_id="R23D01",
        strategy_name="us_pit_semantic_theme_r23_d01",
        spec_hash="0" * 64,
        epoch_id="r23fwd_unit",
        observation_id="20260805",
        decision_session=datetime(2026, 8, 5).date(),
        action_session=datetime(2026, 8, 6).date(),
        generated_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
        weights=weights,
        role_status={},
        model_diagnostics={
            "d01_route": {"selected_target": "QQQ"},
            "current_prediction": {"m01_selected_route": "QQQ"},
        },
        price_snapshot={"feed": "iex", "adjustment": "all", "content_sha256": "1" * 64},
    )
    intents = _intents_payload(
        candidate_id="R23D01",
        strategy_name="us_pit_semantic_theme_r23_d01",
        spec_hash="0" * 64,
        epoch_id="r23fwd_unit",
        observation_id="20260805",
        decision_session=datetime(2026, 8, 5).date(),
        action_session=datetime(2026, 8, 6).date(),
        generated_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
        previous_weights={symbol: 0.0 for symbol in UNIVERSE},
        target_weights=weights,
        target_sha256=target["target_sha256"],
    )
    assert intents["order_required_intent_count"] == 1
    assert intents["order_authority"] is False
    assert intents["broker_writes"] is False
    assert all(row["order_authorized"] is False for row in intents["rebalance_intents"])


@pytest.mark.slow
def test_offline_end_to_end_freeze_publish_receipt_and_idempotent_retry(
    tmp_path: Path,
) -> None:
    required_files = {
        *LOCKED_PATHS,
        *SPEC_PATHS.values(),
        HISTORICAL_LOCK_PATH,
        HISTORICAL_REPORT_PATH,
        HISTORICAL_TARGET_LEDGER_PATH,
        PROMPT_PATH,
        Path("reports/research/data-quality/r11-price-repair-20260804-quality.json"),
        Path(
            "open_composer/adapters/data/provenance_archive/"
            "alpaca_snapshot-"
            "7c2c15cd83a7230d6c6f37f5d336dc236f93acb0aa0a73f47ff3bb6ca240d89b.source"
        ),
        Path(
            "open_composer/adapters/data/provenance_archive/"
            "market_calendar-"
            "7146e57dc41935b1b669da86b4ad04d21500bbff042c1794db9d059c2aad1e6a.source"
        ),
    }
    for relative in required_files:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            os.link(source, destination)
    snapshot_source = ROOT / "data/research/alpaca_pit_price_adjustment_repair_20260804"
    snapshot_destination = tmp_path / snapshot_source.relative_to(ROOT)
    snapshot_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(snapshot_source, snapshot_destination, copy_function=os.link)
    paper = tmp_path / "reports/paper"
    paper.mkdir(parents=True)
    (paper / "account.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-08-05T21:00:00+00:00",
                "paper": True,
                "equity": 100_000.0,
                "portfolio_value": 100_000.0,
            }
        ),
        encoding="utf-8",
    )
    (paper / "positions.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-08-05T21:00:00+00:00",
                "paper": True,
                "positions": [],
            }
        ),
        encoding="utf-8",
    )
    created_at = datetime(2026, 8, 5, 21, 0, tzinfo=UTC)
    observed_at = datetime(2026, 8, 5, 22, 0, tzinfo=UTC)
    freeze = freeze_pit_semantic_theme_r23_forward(tmp_path, created_at=created_at)
    panel = load_r22_price_panel(tmp_path)
    price_frames = {}
    for symbol in UNIVERSE:
        last_open = float(panel.open.iloc[-1][symbol])
        last_low = float(panel.low.iloc[-1][symbol])
        last_close = float(panel.close.iloc[-1][symbol])
        last_volume = float(panel.volume.iloc[-1][symbol])
        frame = pd.DataFrame(
            [
                {
                    "timestamp": "2026-08-03T04:00:00+00:00",
                    "open": last_open,
                    "high": max(last_open, last_close) * 1.01,
                    "low": last_low,
                    "close": last_close,
                    "volume": last_volume,
                },
                {
                    "timestamp": "2026-08-04T04:00:00+00:00",
                    "open": last_close,
                    "high": last_close * 1.01,
                    "low": last_close * 0.99,
                    "close": last_close * 1.001,
                    "volume": last_volume,
                },
                {
                    "timestamp": "2026-08-05T04:00:00+00:00",
                    "open": last_close * 1.001,
                    "high": last_close * 1.01,
                    "low": last_close * 0.99,
                    "close": last_close * 0.999,
                    "volume": last_volume,
                },
            ]
        )
        frame.attrs["data_source_mode"] = "live_fetch"
        price_frames[symbol] = frame
    qqq_history = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(panel.close.index[-65:], utc=True),
            "open": panel.open["QQQ"].iloc[-65:].to_numpy(),
            "high": (
                pd.concat(
                    [panel.open["QQQ"].iloc[-65:], panel.close["QQQ"].iloc[-65:]], axis=1
                ).max(axis=1)
                * 1.01
            ).to_numpy(),
            "low": panel.low["QQQ"].iloc[-65:].to_numpy(),
            "close": panel.close["QQQ"].iloc[-65:].to_numpy(),
            "volume": panel.volume["QQQ"].iloc[-65:].to_numpy(),
        }
    )
    qqq_live = pd.concat([qqq_history, price_frames["QQQ"]], ignore_index=True)
    qqq_live["timestamp"] = pd.to_datetime(qqq_live["timestamp"], utc=True)
    qqq_live["session"] = qqq_live["timestamp"].dt.date
    price_frames["QQQ"] = (
        qqq_live.drop_duplicates("session", keep="last")
        .drop(columns="session")
        .sort_values("timestamp")
    )
    price_frames["QQQ"].attrs["data_source_mode"] = "live_fetch"
    semantic_frames = _semantic_price_frames()
    price_frames["NVDA"] = semantic_frames["NVDA"]
    price_frames["AMD"] = semantic_frames["AMD"]
    event = _event(created_at + timedelta(minutes=5))
    result = observe_pit_semantic_theme_r23_forward(
        tmp_path,
        observed_at=observed_at,
        events=[event],
        backend_name="unit",
        model="unit-model",
        backend=_BoundThemeBackend(),
        price_frames=price_frames,
    )
    retry = observe_pit_semantic_theme_r23_forward(
        tmp_path,
        observed_at=observed_at,
        events=[event],
        backend_name="unit",
        model="unit-model",
        backend=_BoundThemeBackend(),
        price_frames=price_frames,
    )

    assert result.epoch_id == freeze.epoch_id
    assert result.candidate_count == 8
    assert result.counted_forward_session is False
    assert retry.receipt_path == result.receipt_path
    assert result.receipt_path.exists()
    assert (tmp_path / FORWARD_REPORT_DIR / "readiness.json").exists()
    readiness = json.loads(
        (tmp_path / FORWARD_REPORT_DIR / "readiness.json").read_text(encoding="utf-8")
    )
    assert readiness["tier0_technical_pass"] is True
    assert readiness["valid_forward_session_count"] == 0
    observation_dir = tmp_path / FORWARD_DATA_DIR / "observations/20260805"
    price_snapshot = json.loads(
        (observation_dir / "price-snapshot.json").read_text(encoding="utf-8")
    )
    assert {row["source_mode"] for row in price_snapshot["symbols"]} == {"live_fetch"}
    for suffix in ("target-weights", "rebalance-intents", "execution-observation"):
        for candidate_id in SPEC_PATHS:
            strategy_name = f"us_pit_semantic_theme_r23_{candidate_id[3:].lower()}"
            artifact = tmp_path / "reports/execution" / f"{strategy_name}-{suffix}.json"
            assert artifact.exists()
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            assert payload["broker_writes"] is False
    assert len(list((observation_dir / "roles").glob("*/target-weights.json"))) == 8
