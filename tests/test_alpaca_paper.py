from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
import yaml

from open_composer import paper_authorization
from open_composer.adapters.broker import alpaca_paper
from open_composer.dashboard import build_dashboard_catalog
from open_composer.execution_policy import require_orderable_execution_policy
from open_composer.models.paper import PaperOrderIntent, PaperOrderRecord
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_authorization import (
    PaperOrderAuthorizationStatus,
    broker_account_id_hash,
)
from open_composer.paper_controls import (
    build_paper_alerts,
    build_paper_status,
    clear_paper_kill_switch,
    enable_paper_kill_switch,
    paper_orders_blocked,
    reconcile_paper_state,
    refresh_paper_monitor,
    run_paper_monitor_loop,
)
from open_composer.paper_lock import paper_submission_lock
from open_composer.storage import append_jsonl
from open_composer.strategy_versions import strategy_content_hash, strategy_version_id


def _active_paper_spec(sample_workspace: Path) -> Path:
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = yaml.safe_load(draft.read_text(encoding="utf-8"))
    raw["lifecycle"] = "active"
    raw["execution"]["mode"] = "paper_auto"
    raw["execution"]["broker"] = "alpaca_paper"
    active = sample_workspace / "strategy_specs" / "active" / "fixture_pullback_15m.yaml"
    active.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return active


def test_paper_submit_is_idempotent(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _mock_readiness_ok(monkeypatch)
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    signal = Signal(
        id="sig_test",
        run_id="run",
        strategy_name=spec.name,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        timestamp="2026-01-02T15:45:00Z",
        action="entry",
        side="buy",
        source="scan",
        price=100.0,
        conditions=[],
        lifecycle="active",
        execution_mode="paper_auto",
        fill_assumption="next_bar_open",
    )
    calls = {"count": 0}
    _prepare_submission(sample_workspace, monkeypatch, spec, signal)

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(id="paper-account-test", equity="10000")

        def get_orders(self, filter=None) -> list[SimpleNamespace]:
            return []

    def fake_submit(client, signal_arg, qty, client_order_id, *, time_in_force, write_guard):
        calls["count"] += 1
        assert time_in_force == "day"
        assert write_guard is not None
        return SimpleNamespace(id="order_1", status="accepted")

    monkeypatch.setattr(alpaca_paper, "_submit_market_order", fake_submit)
    client = _verified_test_client(MockClient())
    first = alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=client)
    second = alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=client)
    assert first.id == "order_1"
    assert second.signal_id == signal.id
    assert calls["count"] == 1
    intents = (sample_workspace / "reports" / "paper" / "order_intents.jsonl").read_text(
        encoding="utf-8"
    )
    orders = (sample_workspace / "reports" / "paper" / "orders.jsonl").read_text(encoding="utf-8")
    assert len(intents.splitlines()) == 1
    assert '"execution_policy_id": "day-test"' in orders
    assert '"authorization_id": "auth_bbbbbbbbbbbbbbbb"' in orders
    assert '"signal_record_hash":' in orders


def test_paper_submit_uses_opg_limit_execution_policy(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _mock_readiness_ok(monkeypatch)
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    policy_path = (
        sample_workspace
        / "reports"
        / "harness"
        / "execution"
        / f"{spec.name}-execution-policy.json"
    )
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        (
            '{"strategy_name":"fixture_pullback_15m","policy_id":"loo-test",'
            '"order_style":"loo_limit","time_in_force":"opg",'
            '"price_protection":{"limit_offset_bps":25}}'
        ),
        encoding="utf-8",
    )
    signal = Signal(
        id="sig_limit",
        run_id="run",
        strategy_name=spec.name,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        timestamp="2026-01-02T15:45:00Z",
        action="entry",
        side="buy",
        source="scan",
        price=100.0,
        conditions=[],
        lifecycle="active",
        execution_mode="paper_auto",
        fill_assumption="next_bar_open",
    )
    captured = {}
    _prepare_submission(sample_workspace, monkeypatch, spec, signal)

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(id="paper-account-test", equity="10000")

        def get_orders(self, filter=None) -> list[SimpleNamespace]:
            return []

    def fake_submit(
        client,
        signal_arg,
        qty,
        client_order_id,
        *,
        limit_price,
        time_in_force,
        write_guard,
    ):
        captured["limit_price"] = limit_price
        captured["time_in_force"] = time_in_force
        assert write_guard is not None
        return SimpleNamespace(id="order_limit", status="accepted")

    monkeypatch.setattr(alpaca_paper, "_submit_limit_order", fake_submit)
    order = alpaca_paper.submit_paper_order(
        signal,
        spec,
        sample_workspace,
        client=_verified_test_client(MockClient()),
    )

    assert order.id == "order_limit"
    assert captured == {"limit_price": 100.25, "time_in_force": "opg"}


def test_missing_or_unsupported_policy_never_calls_broker(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _mock_readiness_ok(monkeypatch)
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    signal = _target_signal(spec, action="entry", target_weight=spec.risk.max_position_weight)
    calls = {"count": 0}

    class MockClient(_TargetStateClient):
        _open_composer_paper_verified = True
        _open_composer_paper_origin = alpaca_paper.ALPACA_PAPER_ORIGIN

        def submit_order(self, _request):
            calls["count"] += 1

    client = _verified_test_client(MockClient(position_qty=0.0, equity=10_000.0))
    with pytest.raises(alpaca_paper.PaperOrderError, match="explicit execution policy"):
        alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=client)

    policy_path = (
        sample_workspace
        / "reports"
        / "harness"
        / "execution"
        / f"{spec.name}-execution-policy.json"
    )
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        '{"policy_id":"twap-test","order_style":"twap","time_in_force":"day"}',
        encoding="utf-8",
    )
    with pytest.raises(alpaca_paper.PaperOrderError, match="unsupported paper order_style"):
        alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=client)
    assert calls["count"] == 0


def test_unlogged_or_mutated_signal_never_calls_broker(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _mock_readiness_ok(monkeypatch)
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    signal = _target_signal(spec, action="entry", target_weight=spec.risk.max_position_weight)
    _prepare_submission(sample_workspace, monkeypatch, spec, signal, persist_signal=False)
    client = _TargetStateClient(position_qty=0.0, equity=10_000.0)

    with pytest.raises(alpaca_paper.PaperOrderError, match="must be persisted"):
        alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=client)

    append_jsonl(sample_workspace / "signal_logs" / "persisted.jsonl", [signal])
    signal.price += 1.0
    with pytest.raises(alpaca_paper.PaperOrderError, match="does not match the persisted"):
        alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=client)


def test_retry_reconciles_prepared_intent_before_resubmitting(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _mock_readiness_ok(monkeypatch)
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    signal = _target_signal(spec, action="entry", target_weight=spec.risk.max_position_weight)
    signal.target_weight = None
    _prepare_submission(sample_workspace, monkeypatch, spec, signal)
    submitted = {"count": 0, "order": None}

    class MockClient(_TargetStateClient):
        def get_orders(self, filter=None) -> list[SimpleNamespace]:
            return [submitted["order"]] if submitted["order"] is not None else []

    client = _verified_test_client(MockClient(position_qty=0.0, equity=10_000.0))

    def fake_submit(
        _client,
        _signal,
        _qty,
        client_order_id,
        *,
        time_in_force,
        write_guard,
    ):
        assert write_guard is not None
        submitted["count"] += 1
        submitted["order"] = SimpleNamespace(
            id="broker-order",
            client_order_id=client_order_id,
            status="accepted",
        )
        return submitted["order"]

    real_append = alpaca_paper._append_jsonl_durable

    def crash_before_order_audit(path, row):
        if path.name == "orders.jsonl":
            raise OSError("simulated local audit interruption")
        return real_append(path, row)

    monkeypatch.setattr(alpaca_paper, "_submit_market_order", fake_submit)
    monkeypatch.setattr(alpaca_paper, "_append_jsonl_durable", crash_before_order_audit)
    with pytest.raises(OSError, match="simulated local audit interruption"):
        alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=client)
    assert submitted["count"] == 1
    assert (sample_workspace / "reports" / "paper" / "order_intents.jsonl").exists()

    monkeypatch.setattr(alpaca_paper, "_append_jsonl_durable", real_append)
    recovered = alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=client)
    assert recovered.id == "broker-order"
    assert submitted["count"] == 1


def test_paper_submit_revalidates_authorization_immediately_before_broker_write(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _mock_readiness_ok(monkeypatch)
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    signal = _target_signal(spec, action="entry", target_weight=spec.risk.max_position_weight)
    signal.target_weight = None
    _prepare_submission(sample_workspace, monkeypatch, spec, signal)
    events: list[str] = []

    class MockClient(_TargetStateClient):
        def get_orders(self, filter=None) -> list[SimpleNamespace]:
            events.append("broker_lookup")
            return []

        def submit_order(self, _request):
            events.append("broker_submit")
            return SimpleNamespace(id="order-revalidated", status="accepted")

    def fake_revalidate(_spec, _root, authorization):
        events.append("authorization_revalidated")
        return authorization

    monkeypatch.setattr(
        alpaca_paper,
        "revalidate_paper_submission_authorization",
        fake_revalidate,
    )

    order = alpaca_paper.submit_paper_order(
        signal,
        spec,
        sample_workspace,
        client=_verified_test_client(MockClient(position_qty=0.0, equity=10_000.0)),
    )

    assert order.id == "order-revalidated"
    assert events[-2:] == ["authorization_revalidated", "broker_submit"]
    assert events.count("authorization_revalidated") == 2


def test_low_level_broker_write_requires_verified_submission_guard(sample_workspace: Path) -> None:
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    signal = _target_signal(spec, action="entry", target_weight=spec.risk.max_position_weight)

    with pytest.raises(alpaca_paper.PaperOrderError, match="verified submission guard"):
        alpaca_paper._submit_market_order(
            object(),
            signal,
            1.0,
            "oc-direct-call",
            time_in_force="day",
        )


def test_broker_write_guard_is_request_bound_one_shot_and_policy_immutable(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _mock_readiness_ok(monkeypatch)
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    signal = _target_signal(spec, action="entry", target_weight=spec.risk.max_position_weight)
    signal.target_weight = None
    _prepare_submission(sample_workspace, monkeypatch, spec, signal)
    captured: dict[str, object] = {}

    def capture_guard(client, signal_arg, policy, qty, client_order_id, *, write_guard):
        captured["guard"] = write_guard
        return SimpleNamespace(id="captured-order", status="accepted")

    monkeypatch.setattr(alpaca_paper, "_submit_policy_order", capture_guard)
    alpaca_paper.submit_paper_order(
        signal,
        spec,
        sample_workspace,
        client=_verified_test_client(_TargetStateClient(position_qty=0.0, equity=10_000.0)),
    )
    guard = captured["guard"]
    assert isinstance(guard, alpaca_paper._PaperBrokerWriteGuard)
    valid_qty = guard.qty

    class WriteClient(_TargetStateClient):
        def __init__(self):
            super().__init__(position_qty=0, equity=10_000)
            self.submissions = 0

        def submit_order(self, _request):
            self.submissions += 1
            return SimpleNamespace(id="guarded-order", status="accepted")

    client = _verified_test_client(WriteClient())
    with pytest.raises(alpaca_paper.PaperOrderError, match="request binding is stale: qty"):
        alpaca_paper._submit_market_order(
            client,
            signal,
            valid_qty + 1,
            f"oc-{signal.id}",
            time_in_force="day",
            write_guard=guard,
        )

    guard.context.policy.payload["order_style"] = "moo_market"
    with pytest.raises(alpaca_paper.PaperOrderError, match="policy payload was mutated"):
        alpaca_paper._submit_market_order(
            client,
            signal,
            valid_qty,
            f"oc-{signal.id}",
            time_in_force="day",
            write_guard=guard,
        )
    guard.context.policy.payload["order_style"] = "day_market"

    alpaca_paper._submit_market_order(
        client,
        signal,
        valid_qty,
        f"oc-{signal.id}",
        time_in_force="day",
        write_guard=guard,
    )
    assert client.submissions == 1
    with pytest.raises(alpaca_paper.PaperOrderError, match="already consumed"):
        alpaca_paper._submit_market_order(
            client,
            signal,
            valid_qty,
            f"oc-{signal.id}",
            time_in_force="day",
            write_guard=guard,
        )


def test_paper_client_marker_rejects_non_sandbox_client() -> None:
    client = SimpleNamespace(
        _base_url=alpaca_paper.ALPACA_PAPER_ORIGIN,
        _sandbox=False,
    )

    with pytest.raises(alpaca_paper.PaperOrderError, match="configured for Alpaca Paper"):
        alpaca_paper._mark_verified_paper_client(client)


def test_single_symbol_target_does_not_buy_while_already_long(
    sample_workspace: Path,
) -> None:
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    signal = _target_signal(spec, action="entry", target_weight=spec.risk.max_position_weight)
    client = _TargetStateClient(position_qty=3.0, equity=10_000.0)

    assert alpaca_paper.resolve_target_order_quantity(client, spec, signal) is None


def test_single_symbol_zero_target_does_not_sell_while_flat(
    sample_workspace: Path,
) -> None:
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    signal = _target_signal(spec, action="exit", target_weight=0.0)
    client = _TargetStateClient(position_qty=0.0, equity=10_000.0)

    assert alpaca_paper.resolve_target_order_quantity(client, spec, signal) is None


def test_single_symbol_exit_uses_actual_position_quantity(
    sample_workspace: Path,
) -> None:
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    signal = _target_signal(spec, action="exit", target_weight=0.0)
    client = _TargetStateClient(position_qty=2.5, equity=10_000.0)

    assert alpaca_paper.resolve_target_order_quantity(client, spec, signal) == 2.5


def test_single_symbol_target_rejects_forced_one_share_oversize(
    sample_workspace: Path,
) -> None:
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    signal = _target_signal(spec, action="entry", target_weight=spec.risk.max_position_weight)
    signal.price = 500.0
    client = _TargetStateClient(position_qty=0.0, equity=100.0)

    with pytest.raises(alpaca_paper.PaperOrderError, match="cannot buy one share"):
        alpaca_paper.resolve_target_order_quantity(client, spec, signal)


def test_canary_scales_strategy_target_to_bound_and_audits_order(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    policy_path = (
        sample_workspace
        / "reports"
        / "harness"
        / "execution"
        / f"{spec.name}-execution-policy.json"
    )
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(
            {
                "strategy_name": spec.name,
                "policy_id": "canary-limit-test",
                "order_style": "loo_limit",
                "time_in_force": "opg",
                "price_protection": {"limit_offset_bps": 20},
            }
        ),
        encoding="utf-8",
    )
    signal = _target_signal(
        spec,
        action="entry",
        target_weight=spec.risk.max_position_weight,
    )
    signal.price = 100
    _prepare_submission(sample_workspace, monkeypatch, spec, signal)
    authorization = PaperOrderAuthorizationStatus(
        authorized=True,
        message="bounded canary",
        path=sample_workspace / "canary.json",
        content_hash="f" * 64,
        payload={
            "authorization_id": "auth_" + "f" * 16,
            "authorized_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "broker_account_id_hash": broker_account_id_hash("paper-account-test"),
            "allowed_symbols": [spec.primary_symbol],
            "limits": {
                "max_order_notional_usd": 500,
                "max_session_notional_usd": 1000,
                "max_total_notional_usd": 2000,
                "max_orders_per_session": 2,
                "max_total_orders": 4,
            },
        },
        kind="canary",
    )
    monkeypatch.setattr(
        "open_composer.paper_readiness.assess_paper_strategy_readiness_for_spec",
        lambda _spec, _root: SimpleNamespace(
            status="warning",
            execution_substate="canary_authorized",
        ),
    )
    monkeypatch.setattr(
        alpaca_paper,
        "assess_paper_canary_authorization",
        lambda _spec, _root: authorization,
    )
    monkeypatch.setattr(
        alpaca_paper,
        "revalidate_paper_submission_authorization",
        lambda _spec, _root, _expected: authorization,
    )
    calls = {"count": 0}

    class MockClient(_TargetStateClient):
        _open_composer_paper_verified = True
        _open_composer_paper_origin = alpaca_paper.ALPACA_PAPER_ORIGIN

        def submit_order(self, _request):
            calls["count"] += 1
            return SimpleNamespace(
                id="canary-scaled-order",
                status="accepted",
                symbol=spec.primary_symbol,
                side="buy",
                qty="1",
                client_order_id=f"oc-{signal.id}",
            )

    record = alpaca_paper.submit_paper_order(
        signal,
        spec,
        sample_workspace,
        client=_verified_test_client(MockClient(position_qty=0, equity=20_000)),
    )

    assert calls["count"] == 1
    assert record.qty == 1
    assert record.requested_target_weight == spec.risk.max_position_weight
    assert record.effective_target_weight == pytest.approx(100.2 / 20_000)
    assert record.pretrade_position_qty == 0
    assert record.target_position_qty == 1
    assert record.canary_position_limit_usd == 200
    assert record.risk_effect == "increase"
    intent = PaperOrderIntent.model_validate_json(
        (sample_workspace / "reports" / "paper" / "order_intents.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert intent.requested_target_weight == record.requested_target_weight
    assert intent.effective_target_weight == record.effective_target_weight
    assert intent.canary_position_limit_usd == record.canary_position_limit_usd
    assert intent.risk_effect == "increase"


def test_canary_rechecks_position_immediately_before_broker_write(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    policy_path = (
        sample_workspace
        / "reports"
        / "harness"
        / "execution"
        / f"{spec.name}-execution-policy.json"
    )
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(
            {
                "strategy_name": spec.name,
                "policy_id": "canary-race-test",
                "order_style": "loo_limit",
                "time_in_force": "opg",
                "price_protection": {"limit_offset_bps": 20},
            }
        ),
        encoding="utf-8",
    )
    signal = _target_signal(spec, action="exit", target_weight=0.0)
    _prepare_submission(sample_workspace, monkeypatch, spec, signal)
    authorization = PaperOrderAuthorizationStatus(
        authorized=True,
        message="bounded canary",
        path=sample_workspace / "canary.json",
        content_hash="a" * 64,
        payload={
            "authorization_id": "auth_" + "a" * 16,
            "authorized_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "broker_account_id_hash": broker_account_id_hash("paper-account-test"),
            "allowed_symbols": [spec.primary_symbol],
            "limits": {
                "max_order_notional_usd": 500,
                "max_session_notional_usd": 1000,
                "max_total_notional_usd": 2000,
                "max_orders_per_session": 2,
                "max_total_orders": 4,
            },
        },
        kind="canary",
    )
    monkeypatch.setattr(
        "open_composer.paper_readiness.assess_paper_strategy_readiness_for_spec",
        lambda _spec, _root: SimpleNamespace(
            status="warning",
            execution_substate="canary_authorized",
        ),
    )
    monkeypatch.setattr(
        alpaca_paper,
        "assess_paper_canary_authorization",
        lambda _spec, _root: authorization,
    )
    monkeypatch.setattr(
        alpaca_paper,
        "revalidate_paper_submission_authorization",
        lambda _spec, _root, _expected: authorization,
    )
    calls = {"positions": 0, "submissions": 0}

    class PositionChangedClient(_TargetStateClient):
        def get_all_positions(self):
            calls["positions"] += 1
            if calls["positions"] == 1:
                return [SimpleNamespace(symbol=spec.primary_symbol, qty="2")]
            return []

        def submit_order(self, _request):
            calls["submissions"] += 1
            return SimpleNamespace(id="unsafe-order", status="accepted")

    with pytest.raises(
        alpaca_paper.PaperOrderError,
        match="broker target state changed after intent reservation",
    ):
        alpaca_paper.submit_paper_order(
            signal,
            spec,
            sample_workspace,
            client=_verified_test_client(PositionChangedClient(position_qty=2, equity=10_000)),
        )
    assert calls["positions"] >= 2
    assert calls["submissions"] == 0


@pytest.mark.parametrize("emergency", ["kill_switch", "revocation"])
def test_emergency_control_preempts_blocked_pre_submit_reconciliation(
    sample_workspace: Path,
    monkeypatch,
    emergency: str,
) -> None:
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    signal = _target_signal(
        spec,
        action="entry",
        target_weight=spec.risk.max_position_weight,
    )
    authorization = _prepare_canary_submission(sample_workspace, monkeypatch, spec, signal)
    reconciliation_started = Event()
    release_reconciliation = Event()
    revoked = Event()
    submissions = 0

    original_reconcile = alpaca_paper._revalidate_canary_broker_target

    def blocking_reconcile(*args, **kwargs):
        reconciliation_started.set()
        if not release_reconciliation.wait(timeout=3):
            raise AssertionError("test did not release final broker reconciliation")
        return original_reconcile(*args, **kwargs)

    def revalidate(_spec, _root, _expected):
        if revoked.is_set():
            raise ValueError("paper canary was revoked during submission")
        return authorization

    expected_revocation = sample_workspace / "revocation.json"

    def fake_revoke_locked(*args, **kwargs):
        revoked.set()
        return expected_revocation

    monkeypatch.setattr(
        alpaca_paper,
        "_revalidate_canary_broker_target",
        blocking_reconcile,
    )
    monkeypatch.setattr(
        alpaca_paper,
        "revalidate_paper_submission_authorization",
        revalidate,
    )
    monkeypatch.setattr(
        paper_authorization,
        "_write_paper_canary_revocation_locked",
        fake_revoke_locked,
    )

    class BlockingClient(_TargetStateClient):
        def submit_order(self, _request):
            nonlocal submissions
            submissions += 1
            return SimpleNamespace(id="unsafe-order", status="accepted")

    client = _verified_test_client(BlockingClient(position_qty=0, equity=10_000))

    def trigger_emergency():
        if emergency == "kill_switch":
            return enable_paper_kill_switch(
                sample_workspace,
                reason="preempt pending submission",
                updated_by="test",
            )
        return paper_authorization.write_paper_canary_revocation(
            spec,
            sample_workspace,
            revoked_by="test",
            reason="preempt pending submission",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        submission = executor.submit(
            alpaca_paper.submit_paper_order,
            signal,
            spec,
            sample_workspace,
            client,
        )
        assert reconciliation_started.wait(timeout=2)
        emergency_result = executor.submit(trigger_emergency)
        try:
            published = emergency_result.result(timeout=2)
        finally:
            release_reconciliation.set()
        if emergency == "kill_switch":
            assert published.enabled is True
            expected_error = "kill switch is enabled"
        else:
            assert published == expected_revocation
            assert revoked.is_set()
            expected_error = "revoked during submission"
        with pytest.raises(alpaca_paper.PaperOrderError, match=expected_error):
            submission.result(timeout=2)
    assert submissions == 0


@pytest.mark.parametrize("expired_gate", ["authorization", "freshness", "order_window"])
def test_temporal_gates_are_last_before_broker_write(
    sample_workspace: Path,
    monkeypatch,
    expired_gate: str,
) -> None:
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    signal = _target_signal(
        spec,
        action="entry",
        target_weight=spec.risk.max_position_weight,
    )
    authorization = _prepare_canary_submission(sample_workspace, monkeypatch, spec, signal)
    reconciled = Event()
    submissions = 0

    def finish_reconciliation(*args, **kwargs):
        reconciled.set()

    def revalidate(_spec, _root, _expected):
        if expired_gate == "authorization" and reconciled.is_set():
            raise ValueError("paper canary authorization expired after reconciliation")
        return authorization

    def require_fresh(_signal, *, observed_at=None):
        if expired_gate == "freshness" and reconciled.is_set():
            raise ValueError("paper signal expired after reconciliation")

    def require_window(_spec, _policy, *, observed_at=None):
        if expired_gate == "order_window" and reconciled.is_set():
            raise ValueError("paper order window closed after reconciliation")

    monkeypatch.setattr(
        alpaca_paper,
        "_revalidate_canary_broker_target",
        finish_reconciliation,
    )
    monkeypatch.setattr(
        alpaca_paper,
        "revalidate_paper_submission_authorization",
        revalidate,
    )
    monkeypatch.setattr(alpaca_paper, "require_fresh_paper_signal", require_fresh)
    monkeypatch.setattr(alpaca_paper, "require_paper_order_window", require_window)

    class TimingClient(_TargetStateClient):
        def submit_order(self, _request):
            nonlocal submissions
            submissions += 1
            return SimpleNamespace(id="unsafe-order", status="accepted")

    with pytest.raises(alpaca_paper.PaperOrderError, match="expired|closed"):
        alpaca_paper.submit_paper_order(
            signal,
            spec,
            sample_workspace,
            client=_verified_test_client(TimingClient(position_qty=0, equity=10_000)),
        )
    assert reconciled.is_set()
    assert submissions == 0


def test_authorization_expiry_after_local_evidence_blocks_broker_write(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    signal = _target_signal(
        spec,
        action="entry",
        target_weight=spec.risk.max_position_weight,
    )
    authorization = _prepare_canary_submission(sample_workspace, monkeypatch, spec, signal)
    clock = {"now": datetime.now(UTC)}
    authorization.payload["authorized_at"] = (clock["now"] - timedelta(hours=1)).isoformat()
    authorization.payload["expires_at"] = (clock["now"] + timedelta(minutes=1)).isoformat()
    submissions = 0
    original_local_check = alpaca_paper._revalidate_local_write_evidence

    def expire_after_local_check(guard):
        original_local_check(guard)
        clock["now"] += timedelta(minutes=2)

    monkeypatch.setattr(
        alpaca_paper,
        "_revalidate_local_write_evidence",
        expire_after_local_check,
    )
    monkeypatch.setattr(
        alpaca_paper,
        "_paper_broker_write_decision_time",
        lambda: clock["now"],
    )

    class ExpiryClient(_TargetStateClient):
        def submit_order(self, _request):
            nonlocal submissions
            submissions += 1
            return SimpleNamespace(id="unsafe-order", status="accepted")

    with pytest.raises(
        alpaca_paper.PaperOrderError,
        match="not effective at broker-write decision time",
    ):
        alpaca_paper.submit_paper_order(
            signal,
            spec,
            sample_workspace,
            client=_verified_test_client(ExpiryClient(position_qty=0, equity=10_000)),
        )
    assert submissions == 0


def test_final_temporal_predicates_share_decision_timestamp(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    signal = _target_signal(
        spec,
        action="entry",
        target_weight=spec.risk.max_position_weight,
    )
    authorization = _prepare_canary_submission(sample_workspace, monkeypatch, spec, signal)
    decision_at = datetime.now(UTC)
    authorization.payload["authorized_at"] = (decision_at - timedelta(hours=1)).isoformat()
    authorization.payload["expires_at"] = (decision_at + timedelta(hours=1)).isoformat()
    final_checks: list[tuple[str, datetime]] = []
    local_evidence_checked = Event()
    original_effective_check = alpaca_paper.require_paper_submission_authorization_effective_at
    original_local_check = alpaca_paper._revalidate_local_write_evidence

    def local_check(guard):
        original_local_check(guard)
        local_evidence_checked.set()

    def effective_check(current, observed_at):
        assert local_evidence_checked.is_set()
        final_checks.append(("authorization", observed_at))
        original_effective_check(current, observed_at)

    def fresh_check(_signal, *, observed_at=None):
        if observed_at is not None:
            final_checks.append(("freshness", observed_at))

    def window_check(_spec, _policy, *, observed_at=None):
        if observed_at is not None:
            final_checks.append(("order_window", observed_at))

    monkeypatch.setattr(alpaca_paper, "_revalidate_local_write_evidence", local_check)
    monkeypatch.setattr(
        alpaca_paper,
        "require_paper_submission_authorization_effective_at",
        effective_check,
    )
    monkeypatch.setattr(alpaca_paper, "require_fresh_paper_signal", fresh_check)
    monkeypatch.setattr(alpaca_paper, "require_paper_order_window", window_check)
    monkeypatch.setattr(
        alpaca_paper,
        "_paper_broker_write_decision_time",
        lambda: decision_at,
    )

    class DecisionClient(_TargetStateClient):
        def submit_order(self, _request):
            return SimpleNamespace(id="decision-order", status="accepted")

    record = alpaca_paper.submit_paper_order(
        signal,
        spec,
        sample_workspace,
        client=_verified_test_client(DecisionClient(position_qty=0, equity=10_000)),
    )

    assert record.id == "decision-order"
    assert final_checks == [
        ("authorization", decision_at),
        ("freshness", decision_at),
        ("order_window", decision_at),
    ]


def test_concurrent_canary_reservations_share_one_session_limit(
    sample_workspace: Path,
) -> None:
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    policy = require_orderable_execution_policy(spec, sample_workspace)
    authorization = PaperOrderAuthorizationStatus(
        authorized=True,
        message="bounded canary",
        path=sample_workspace / "canary.json",
        content_hash="c" * 64,
        payload={
            "authorization_id": "auth_" + "a" * 16,
            "broker_account_id_hash": broker_account_id_hash("paper-account-test"),
            "allowed_symbols": [spec.primary_symbol],
            "limits": {
                "max_order_notional_usd": 100,
                "max_session_notional_usd": 100,
                "max_total_notional_usd": 200,
                "max_orders_per_session": 1,
                "max_total_orders": 2,
            },
        },
        kind="canary",
    )
    context = alpaca_paper.PaperSubmissionContext(policy=policy, authorization=authorization)
    client = _VerifiedTargetStateClient(position_qty=0, equity=10_000)

    def reserve(index: int):
        signal = _target_signal(spec, action="entry", target_weight=0.01)
        signal.id = f"sig_concurrent_{index}"
        signal.version_id = strategy_version_id(spec)
        signal.spec_hash = strategy_content_hash(spec)
        record_hash = hashlib.sha256(signal.id.encode("utf-8")).hexdigest()
        intent_id = f"intent_{index:016x}"
        with paper_submission_lock(sample_workspace):
            alpaca_paper._enforce_canary_order_limits(
                sample_workspace,
                client,
                spec,
                signal,
                context,
                intent_id=intent_id,
                order_qty=1,
                reference_price=100,
                estimated_notional=100,
                risk_effect="increase",
            )
            return alpaca_paper._prepare_order_intent(
                sample_workspace,
                signal,
                sample_workspace / "signal_logs" / f"{signal.run_id}.jsonl",
                record_hash,
                context,
                intent_id=intent_id,
                order_qty=1,
                reference_price=100,
                estimated_notional=100,
                client_order_id=f"oc-{signal.id}",
                target_resolution=None,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(reserve, index) for index in range(2)]
    successes = [future.result() for future in futures if future.exception() is None]
    errors = [future.exception() for future in futures if future.exception() is not None]

    assert len(successes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], alpaca_paper.PaperOrderError)
    assert "session order-count limit exceeded" in str(errors[0])
    ledger = sample_workspace / "reports" / "paper" / "order_intents.jsonl"
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 1


def test_canary_lifetime_limit_counts_prior_authorizations(sample_workspace: Path) -> None:
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    policy = require_orderable_execution_policy(spec, sample_workspace)
    authorization = PaperOrderAuthorizationStatus(
        authorized=True,
        message="renewed bounded canary",
        path=sample_workspace / "canary.json",
        content_hash="d" * 64,
        payload={
            "authorization_id": "auth_" + "f" * 16,
            "broker_account_id_hash": broker_account_id_hash("paper-account-test"),
            "allowed_symbols": [spec.primary_symbol],
            "limits": {
                "max_order_notional_usd": 1000,
                "max_session_notional_usd": 2500,
                "max_total_notional_usd": 12000,
                "max_orders_per_session": 4,
                "max_total_orders": 16,
            },
        },
        kind="canary",
    )
    context = alpaca_paper.PaperSubmissionContext(policy=policy, authorization=authorization)
    reserved_at = datetime.now(UTC) - timedelta(days=60)
    prior = [
        PaperOrderIntent(
            id=f"intent_{index:016x}",
            created_at=reserved_at,
            client_order_id=f"oc-prior-{index}",
            signal_id=f"sig_prior_{index}",
            signal_record_hash=hashlib.sha256(f"signal-{index}".encode()).hexdigest(),
            signal_log_path="signal_logs/prior.jsonl",
            strategy_name=spec.name,
            version_id=strategy_version_id(spec),
            spec_hash=strategy_content_hash(spec),
            execution_policy_id=policy.policy_id,
            execution_policy_hash=policy.content_hash,
            order_style="day_market",
            time_in_force="day",
            authorization_id=f"auth_{index:016x}",
            authorization_hash=hashlib.sha256(f"auth-{index}".encode()).hexdigest(),
            authorization_kind="canary",
            symbol=spec.primary_symbol,
            side="buy",
            qty=1,
            reference_price=750,
            estimated_notional=750,
            reserved_at=reserved_at,
        )
        for index in range(40)
    ]
    append_jsonl(sample_workspace / "reports" / "paper" / "order_intents.jsonl", prior)
    signal = _target_signal(spec, action="entry", target_weight=0.01)

    with pytest.raises(alpaca_paper.PaperOrderError, match="lifetime reservation limit"):
        alpaca_paper._enforce_canary_order_limits(
            sample_workspace,
            _VerifiedTargetStateClient(position_qty=0, equity=10_000),
            spec,
            signal,
            context,
            intent_id="intent_ffffffffffffffff",
            order_qty=1,
            reference_price=100,
            estimated_notional=100,
            risk_effect="increase",
        )


def test_canary_risk_reducing_exit_does_not_consume_increase_caps(
    sample_workspace: Path,
) -> None:
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    policy = require_orderable_execution_policy(spec, sample_workspace)
    authorization = PaperOrderAuthorizationStatus(
        authorized=True,
        message="bounded canary",
        path=sample_workspace / "canary.json",
        content_hash="e" * 64,
        payload={
            "authorization_id": "auth_" + "e" * 16,
            "broker_account_id_hash": broker_account_id_hash("paper-account-test"),
            "allowed_symbols": [spec.primary_symbol],
            "limits": {
                "max_order_notional_usd": 100,
                "max_session_notional_usd": 100,
                "max_total_notional_usd": 100,
                "max_orders_per_session": 1,
                "max_total_orders": 1,
            },
        },
        kind="canary",
    )
    context = alpaca_paper.PaperSubmissionContext(policy=policy, authorization=authorization)
    reserved_at = datetime.now(UTC)
    prior = PaperOrderIntent(
        id="intent_1111111111111111",
        created_at=reserved_at,
        client_order_id="oc-prior-entry",
        signal_id="sig_prior_entry",
        signal_record_hash="1" * 64,
        signal_log_path="signal_logs/prior.jsonl",
        strategy_name=spec.name,
        version_id=strategy_version_id(spec),
        spec_hash=strategy_content_hash(spec),
        execution_policy_id=policy.policy_id,
        execution_policy_hash=policy.content_hash,
        order_style="day_market",
        time_in_force="day",
        authorization_id=str(authorization.payload["authorization_id"]),
        authorization_hash=str(authorization.content_hash),
        authorization_kind="canary",
        symbol=spec.primary_symbol,
        side="buy",
        qty=1,
        reference_price=100,
        estimated_notional=100,
        risk_effect="increase",
        reserved_at=reserved_at,
    )
    append_jsonl(sample_workspace / "reports" / "paper" / "order_intents.jsonl", [prior])
    signal = _target_signal(spec, action="exit", target_weight=0.0)

    alpaca_paper._enforce_canary_order_limits(
        sample_workspace,
        _VerifiedTargetStateClient(position_qty=2, equity=10_000),
        spec,
        signal,
        context,
        intent_id="intent_2222222222222222",
        order_qty=2,
        reference_price=100,
        estimated_notional=200,
        risk_effect="reduce",
    )


def test_canary_rejects_unknown_broker_order_status(sample_workspace: Path) -> None:
    authorization = PaperOrderAuthorizationStatus(
        authorized=True,
        message="bounded canary",
        path=sample_workspace / "canary.json",
        content_hash="e" * 64,
        payload={"authorization_id": "auth_" + "e" * 16},
        kind="canary",
    )
    context = alpaca_paper.PaperSubmissionContext(
        policy=SimpleNamespace(),
        authorization=authorization,
    )

    class UnknownStatusClient:
        def get_orders(self, filter=None):
            return [
                SimpleNamespace(
                    id="unknown-status-order",
                    client_order_id="foreign-order",
                    status="mystery_state",
                )
            ]

    with pytest.raises(alpaca_paper.PaperOrderError, match="unrecognized broker order status"):
        alpaca_paper._require_canary_open_orders_bound(
            sample_workspace,
            UnknownStatusClient(),
            context,
        )


def test_paper_sync_writes_mock_orders(sample_workspace: Path) -> None:
    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(id="paper-account-test")

        def get_orders(self, filter=None) -> list[SimpleNamespace]:
            return [
                SimpleNamespace(
                    id="order_1",
                    client_order_id="oc-sig_test",
                    symbol="QQQ",
                    side="buy",
                    qty="1",
                    status="accepted",
                )
            ]

    path = alpaca_paper.sync_paper_orders(
        sample_workspace,
        client=_verified_test_client(MockClient()),
    )
    assert path.exists()
    assert (sample_workspace / "reports" / "paper" / "open_orders.json").exists()


def test_paper_sync_writes_idempotent_immutable_filled_receipt(
    sample_workspace: Path,
) -> None:
    submitted_at = datetime(2026, 7, 21, 13, 27, tzinfo=UTC)
    filled_at = datetime(2026, 7, 21, 13, 30, tzinfo=UTC)
    local = PaperOrderRecord(
        id="order_filled",
        signal_id="sig_filled",
        client_order_id="oc-sig_filled",
        strategy_name="fixture_pullback_15m",
        strategy_id="fixture_pullback_15m",
        version_id="ver_aaaaaaaaaaaa",
        spec_hash="a" * 64,
        execution_policy_id="opg_limit_v1",
        execution_policy_hash="b" * 64,
        order_style="opg_limit",
        time_in_force="opg",
        authorization_id="auth_aaaaaaaaaaaaaaaa",
        authorization_hash="c" * 64,
        authorization_kind="canary",
        signal_record_hash="d" * 64,
        signal_log_path="signal_logs/run.jsonl",
        order_intent_id="intent_aaaaaaaaaaaaaaaa",
        order_intent_hash="e" * 64,
        symbol="QQQ",
        side="buy",
        qty=2,
        reference_price=500,
        estimated_notional=1000,
        status="submitted",
        submitted_at=submitted_at,
    )
    append_jsonl(sample_workspace / "reports" / "paper" / "orders.jsonl", [local])

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(id="paper-account-test")

        def get_orders(self, filter=None) -> list[SimpleNamespace]:
            return [
                SimpleNamespace(
                    id="order_filled",
                    client_order_id="oc-sig_filled",
                    symbol="QQQ",
                    side="buy",
                    qty="2",
                    filled_qty="2",
                    filled_avg_price="500.25",
                    status="filled",
                    order_type="limit",
                    time_in_force="opg",
                    limit_price="501",
                    submitted_at=submitted_at,
                    accepted_at=submitted_at,
                    filled_at=filled_at,
                )
            ]

    client = _verified_test_client(MockClient())
    alpaca_paper.sync_paper_orders(sample_workspace, client=client)
    alpaca_paper.sync_paper_orders(sample_workspace, client=client)

    latest_path = sample_workspace / "reports" / "paper" / "broker_receipts" / "latest-sync.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest["paper"] is True
    assert latest["broker_account_id_hash"] == broker_account_id_hash("paper-account-test")
    assert latest["order_count"] == 1
    receipt_ref = latest["order_receipts"][0]
    receipt_path = sample_workspace / receipt_ref["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["receipt_source"] == "alpaca_paper_sync"
    assert receipt["local_order_binding_status"] == "matched"
    assert receipt["fill_id_source"] == "derived_from_broker_order_aggregate"
    assert hashlib.sha256(receipt_path.read_bytes()).hexdigest() == receipt_ref["sha256"]
    index = sample_workspace / "reports" / "paper" / "broker_receipts" / "index.jsonl"
    assert len(index.read_text(encoding="utf-8").splitlines()) == 1


def test_paper_sync_preserves_legacy_order_as_unmatched_receipt(
    sample_workspace: Path,
) -> None:
    submitted_at = datetime(2026, 7, 9, 13, 27, tzinfo=UTC)
    legacy = PaperOrderRecord(
        id="order_legacy",
        signal_id="sig_legacy",
        client_order_id="oc-sig_legacy",
        strategy_name="fixture_pullback_15m",
        symbol="QQQ",
        side="sell",
        qty=2,
        status="accepted",
        submitted_at=submitted_at,
    )
    append_jsonl(sample_workspace / "reports" / "paper" / "orders.jsonl", [legacy])

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(id="paper-account-test")

        def get_orders(self, filter=None) -> list[SimpleNamespace]:
            return [
                SimpleNamespace(
                    id="order_legacy",
                    client_order_id="oc-sig_legacy",
                    symbol="QQQ",
                    side="sell",
                    qty="2",
                    filled_qty="0",
                    status="accepted",
                    order_type="limit",
                    time_in_force="opg",
                    limit_price="500",
                    submitted_at=submitted_at,
                    accepted_at=submitted_at,
                )
            ]

    path = alpaca_paper.sync_paper_orders(
        sample_workspace,
        client=_verified_test_client(MockClient()),
    )
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["local_order_binding_status"] == "unmatched"
    latest = json.loads(
        (sample_workspace / "reports" / "paper" / "broker_receipts" / "latest-sync.json").read_text(
            encoding="utf-8"
        )
    )
    receipt = json.loads((sample_workspace / latest["order_receipts"][0]["path"]).read_text())
    assert receipt["local_order_binding_status"] == "unmatched"
    assert receipt["local_order_record"]["client_order_id"] == "oc-sig_legacy"


def test_paper_sync_rejects_incomplete_current_execution_metadata(
    sample_workspace: Path,
) -> None:
    local = PaperOrderRecord(
        id="order_incomplete",
        signal_id="sig_incomplete",
        client_order_id="oc-sig_incomplete",
        strategy_name="fixture_pullback_15m",
        execution_policy_id="opg_limit_v1",
        symbol="QQQ",
        side="buy",
        qty=1,
        status="accepted",
    )
    append_jsonl(sample_workspace / "reports" / "paper" / "orders.jsonl", [local])

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(id="paper-account-test")

        def get_orders(self, filter=None) -> list[SimpleNamespace]:
            return [
                SimpleNamespace(
                    id="order_incomplete",
                    client_order_id="oc-sig_incomplete",
                    symbol="QQQ",
                    side="buy",
                    qty="1",
                    filled_qty="0",
                    status="accepted",
                    order_type="limit",
                    time_in_force="opg",
                )
            ]

    with pytest.raises(alpaca_paper.PaperOrderError, match="local_execution_style"):
        alpaca_paper.sync_paper_orders(
            sample_workspace,
            client=_verified_test_client(MockClient()),
        )


def test_paper_sync_rejects_broker_snapshot_omitting_local_order(
    sample_workspace: Path,
) -> None:
    orders_path = sample_workspace / "reports" / "paper" / "orders.jsonl"
    orders_path.parent.mkdir(parents=True, exist_ok=True)
    orders_path.write_text(
        (
            '{"id":"order_old","signal_id":"sig_old","client_order_id":"oc-sig_old",'
            '"strategy_name":"fixture_pullback_15m","symbol":"AMD","side":"buy",'
            '"qty":1,"status":"accepted","paper":true,'
            '"submitted_at":"2026-01-02T15:45:00Z"}\n'
        ),
        encoding="utf-8",
    )

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(id="paper-account-test")

        def get_orders(self, filter=None) -> list[SimpleNamespace]:
            return []

    with pytest.raises(alpaca_paper.PaperOrderError, match="omitted locally submitted orders"):
        alpaca_paper.sync_paper_orders(
            sample_workspace,
            client=_verified_test_client(MockClient()),
        )
    assert not (sample_workspace / "reports" / "paper" / "open_orders.json").exists()


def test_paper_account_sync_feeds_status_and_dashboard(sample_workspace: Path) -> None:
    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(
                id="paper-account-test",
                equity="10500.50",
                cash="2500.25",
                buying_power="5000.50",
                portfolio_value="10500.50",
                status="ACTIVE",
            )

        def get_all_positions(self) -> list[SimpleNamespace]:
            return [
                SimpleNamespace(
                    symbol="QQQ",
                    qty="3",
                    market_value="1200",
                    cost_basis="1100",
                    unrealized_pl="100",
                    unrealized_plpc="0.0909",
                    current_price="400",
                    side="long",
                )
            ]

    account_path, positions_path = alpaca_paper.sync_paper_account(
        sample_workspace,
        client=_verified_test_client(MockClient()),
    )
    snapshot = build_paper_status(sample_workspace)
    catalog = build_dashboard_catalog(sample_workspace)

    assert account_path.exists()
    assert positions_path.exists()
    assert snapshot.account_equity == 10500.50
    assert snapshot.account_cash == 2500.25
    assert snapshot.account_buying_power == 5000.50
    assert snapshot.account_portfolio_value == 10500.50
    assert snapshot.account_snapshot_at is not None
    assert snapshot.position_count == 1
    assert snapshot.total_position_market_value == 1200
    assert snapshot.total_unrealized_pl == 100
    assert snapshot.positions_snapshot_at is not None
    assert catalog.summary.paper_account_equity == 10500.50
    assert catalog.summary.paper_account_snapshot_at is not None
    assert catalog.summary.paper_position_count == 1
    assert catalog.summary.paper_total_unrealized_pl == 100
    assert catalog.summary.paper_positions_snapshot_at is not None
    assert len(catalog.paper_positions) == 1
    assert catalog.paper_positions[0].symbol == "QQQ"
    assert catalog.paper_positions[0].qty == 3
    assert catalog.paper_positions[0].unrealized_pl == 100


def test_paper_reconciliation_flags_order_position_mismatch(sample_workspace: Path) -> None:
    alpaca_paper.sync_paper_account(
        sample_workspace,
        client=_verified_test_client(
            type(
                "MockClient",
                (),
                {
                    "get_account": lambda self: SimpleNamespace(
                        id="paper-account-test",
                        equity="10000",
                        cash="5000",
                        buying_power="10000",
                        portfolio_value="10000",
                        status="ACTIVE",
                    ),
                    "get_all_positions": lambda self: [],
                },
            )()
        ),
    )
    write_order = sample_workspace / "reports" / "paper" / "orders.jsonl"
    write_order.parent.mkdir(parents=True, exist_ok=True)
    write_order.write_text(
        (
            '{"id":"order_1","signal_id":"sig_1","client_order_id":"oc-sig_1",'
            '"strategy_name":"fixture_pullback_15m","symbol":"QQQ","side":"buy",'
            '"qty":1,"status":"filled","paper":true,'
            '"submitted_at":"2026-01-02T15:45:00Z"}\n'
        ),
        encoding="utf-8",
    )

    report = reconcile_paper_state(sample_workspace)
    alert_report = build_paper_alerts(sample_workspace)
    snapshot = build_paper_status(sample_workspace)
    catalog = build_dashboard_catalog(sample_workspace)

    assert report.status == "warning"
    assert report.issue_count == 2
    assert {issue.code for issue in report.issues} == {
        "filled_buy_without_position",
        "missing_positions_snapshot",
    }
    assert report.report_json_path
    assert (sample_workspace / report.report_json_path).exists()
    assert report.report_markdown_path
    assert (sample_workspace / report.report_markdown_path).exists()
    assert alert_report.status == "warning"
    assert alert_report.alert_count == 1
    assert alert_report.alerts[0].code == "paper_reconciliation_issues"
    assert alert_report.report_json_path
    assert (sample_workspace / alert_report.report_json_path).exists()
    assert alert_report.report_markdown_path
    assert (sample_workspace / alert_report.report_markdown_path).exists()
    assert snapshot.reconciliation_status == "warning"
    assert snapshot.reconciliation_issue_count == 2
    assert snapshot.alert_status == "warning"
    assert snapshot.alert_count == 1
    assert catalog.summary.paper_reconciliation_status == "warning"
    assert catalog.summary.paper_reconciliation_issue_count == 2
    assert catalog.summary.paper_alert_status == "warning"
    assert catalog.summary.paper_alert_count == 1


def test_paper_monitor_refresh_writes_all_local_reports(sample_workspace: Path) -> None:
    report = refresh_paper_monitor(sample_workspace)
    snapshot = build_paper_status(sample_workspace)

    assert report.status == "warning"
    assert report.alert_count >= 1
    assert report.reconciliation_report_path
    assert report.alert_report_path
    assert report.report_json_path
    assert (sample_workspace / report.report_json_path).exists()
    assert report.report_markdown_path
    assert (sample_workspace / report.report_markdown_path).exists()
    assert (sample_workspace / report.status_path).exists()
    assert snapshot.alert_count == report.alert_count
    assert snapshot.reconciliation_issue_count == report.reconciliation_issue_count


def test_paper_monitor_can_sync_broker_snapshots_before_refresh(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    account_path = sample_workspace / "reports" / "paper" / "account.json"
    positions_path = sample_workspace / "reports" / "paper" / "positions.json"
    sync_path = sample_workspace / "reports" / "paper" / "sync.jsonl"

    def fake_sync(base: Path) -> list[str]:
        account_path.parent.mkdir(parents=True, exist_ok=True)
        account_path.write_text(
            '{"equity":10000,"cash":5000,"buying_power":8000,'
            '"portfolio_value":10000,"status":"ACTIVE","paper":true}\n',
            encoding="utf-8",
        )
        positions_path.write_text('{"positions":[]}\n', encoding="utf-8")
        sync_path.write_text("", encoding="utf-8")
        return [str(sync_path), str(account_path), str(positions_path)]

    monkeypatch.setattr("open_composer.paper_controls._sync_broker_snapshots", fake_sync)

    report = refresh_paper_monitor(sample_workspace, sync_broker=True)
    snapshot = build_paper_status(sample_workspace)

    assert report.status == "ok"
    assert report.sync_broker is True
    assert report.sync_status == "ok"
    assert report.sync_output_paths == [str(sync_path), str(account_path), str(positions_path)]
    assert snapshot.account_equity == 10000
    assert snapshot.account_snapshot_at is not None


def test_paper_status_flags_stale_account_and_positions_snapshots(sample_workspace: Path) -> None:
    account_path = sample_workspace / "reports" / "paper" / "account.json"
    positions_path = sample_workspace / "reports" / "paper" / "positions.json"
    account_path.parent.mkdir(parents=True, exist_ok=True)
    account_path.write_text(
        (
            '{"generated_at":"2026-01-01T00:00:00Z","equity":10000,"cash":5000,'
            '"buying_power":8000,"portfolio_value":10000,"status":"ACTIVE","paper":true}\n'
        ),
        encoding="utf-8",
    )
    positions_path.write_text(
        (
            '{"positions":[{"symbol":"QQQ","qty":3,"market_value":1200,'
            '"cost_basis":1100,"unrealized_pl":100,"unrealized_plpc":0.09,'
            '"current_price":400,"side":"long","updated_at":"2026-01-01T00:00:00Z",'
            '"paper":true}]}\n'
        ),
        encoding="utf-8",
    )

    alerts = build_paper_alerts(sample_workspace)
    snapshot = build_paper_status(sample_workspace)

    assert alerts.status == "warning"
    assert {alert.code for alert in alerts.alerts} >= {
        "stale_paper_account_snapshot",
        "stale_paper_positions_snapshot",
    }
    assert snapshot.account_snapshot_at is not None
    assert snapshot.positions_snapshot_at is not None


def test_paper_monitor_loop_records_cycles(sample_workspace: Path) -> None:
    reports = run_paper_monitor_loop(
        sample_workspace,
        interval_seconds=0,
        max_cycles=2,
    )
    cycles_path = sample_workspace / "reports" / "paper" / "monitor_cycles.jsonl"

    assert len(reports) == 2
    assert cycles_path.exists()
    assert len(cycles_path.read_text(encoding="utf-8").splitlines()) == 2
    assert reports[-1].status == "warning"


def test_paper_kill_switch_blocks_order_submission(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _mock_readiness_ok(monkeypatch)
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    signal = Signal(
        id="sig_blocked",
        run_id="run",
        strategy_name=spec.name,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        timestamp="2026-01-02T15:45:00Z",
        action="entry",
        side="buy",
        source="scan",
        price=100.0,
        conditions=[],
        lifecycle="active",
        execution_mode="paper_auto",
        fill_assumption="next_bar_open",
    )
    clear_paper_kill_switch(sample_workspace, updated_by="test")
    enable_paper_kill_switch(sample_workspace, reason="safety", updated_by="test")

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(equity="10000")

    try:
        alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=MockClient())
    except alpaca_paper.PaperOrderError as exc:
        assert "paper kill switch is enabled" in str(exc)
    else:
        raise AssertionError("paper order should be blocked by kill switch")


def test_missing_paper_kill_switch_control_blocks_submission_before_broker_access(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _mock_readiness_ok(monkeypatch)
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    signal = _target_signal(spec, action="entry", target_weight=spec.risk.max_position_weight)
    signal.target_weight = None
    _prepare_submission(sample_workspace, monkeypatch, spec, signal)
    (sample_workspace / "reports" / "paper" / "kill_switch.json").unlink()
    assert paper_orders_blocked(sample_workspace) is True
    calls = {"account": 0, "orders": 0}

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            calls["account"] += 1
            return SimpleNamespace(id="paper-account-test", equity="10000")

        def get_orders(self, filter=None) -> list[SimpleNamespace]:
            calls["orders"] += 1
            return []

    with pytest.raises(alpaca_paper.PaperOrderError, match="control file is missing"):
        alpaca_paper.submit_paper_order(
            signal,
            spec,
            sample_workspace,
            client=_verified_test_client(MockClient()),
        )
    assert calls == {"account": 0, "orders": 0}


def test_invalid_paper_kill_switch_control_blocks_submission_before_broker_access(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _mock_readiness_ok(monkeypatch)
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    signal = _target_signal(spec, action="entry", target_weight=spec.risk.max_position_weight)
    _prepare_submission(sample_workspace, monkeypatch, spec, signal)
    (sample_workspace / "reports" / "paper" / "kill_switch.json").write_text(
        '{"enabled":"not-a-boolean"}\n',
        encoding="utf-8",
    )
    assert paper_orders_blocked(sample_workspace) is True
    calls = {"account": 0}

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            calls["account"] += 1
            return SimpleNamespace(id="paper-account-test", equity="10000")

    with pytest.raises(alpaca_paper.PaperOrderError, match="control file is invalid"):
        alpaca_paper.submit_paper_order(
            signal,
            spec,
            sample_workspace,
            client=_verified_test_client(MockClient()),
        )
    assert calls["account"] == 0


def test_empty_paper_kill_switch_control_fails_closed(sample_workspace: Path) -> None:
    path = sample_workspace / "reports" / "paper" / "kill_switch.json"
    path.write_text("{}\n", encoding="utf-8")

    assert paper_orders_blocked(sample_workspace) is True


def test_paper_kill_switch_rejects_rolled_back_clear_pointer(sample_workspace: Path) -> None:
    clear = clear_paper_kill_switch(sample_workspace, updated_by="test")
    clear_payload = (sample_workspace / "reports" / "paper" / "kill_switch.json").read_bytes()
    enable_paper_kill_switch(sample_workspace, reason="hold", updated_by="test")
    pointer = sample_workspace / "reports" / "paper" / "kill_switch.json"
    pointer.write_bytes(clear_payload)

    assert clear.enabled is False
    assert paper_orders_blocked(sample_workspace) is True


def test_paper_kill_switch_rejects_symlink_and_hardlink_aliases(
    sample_workspace: Path,
) -> None:
    state = clear_paper_kill_switch(sample_workspace, updated_by="test")
    archive = (
        sample_workspace
        / "reports"
        / "paper"
        / "control_history"
        / "kill_switch"
        / f"{state.event_id}.json"
    )
    pointer = sample_workspace / "reports" / "paper" / "kill_switch.json"
    pointer.unlink()
    pointer.symlink_to(archive)
    assert paper_orders_blocked(sample_workspace) is True

    pointer.unlink()
    pointer.hardlink_to(archive)
    assert paper_orders_blocked(sample_workspace) is True


def test_submit_paper_order_requires_readiness_ok(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    signal = Signal(
        id="sig_readiness_blocked",
        run_id="run",
        strategy_name=spec.name,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        timestamp="2026-01-02T15:45:00Z",
        action="entry",
        side="buy",
        source="scan",
        price=100.0,
        conditions=[],
        lifecycle="active",
        execution_mode="paper_auto",
        fill_assumption="next_bar_open",
    )

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(equity="10000")

    try:
        alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=MockClient())
    except alpaca_paper.PaperOrderError as exc:
        assert "explicit bounded canary authorization" in str(exc)
    else:
        raise AssertionError("paper order should be blocked by readiness")


def test_paper_status_snapshot_rebuilds_from_artifacts(sample_workspace: Path) -> None:
    clear_paper_kill_switch(sample_workspace, updated_by="test")
    enable_paper_kill_switch(sample_workspace, reason="maintenance", updated_by="test")
    path = alpaca_paper.sync_paper_orders(
        sample_workspace,
        client=_verified_test_client(
            type(
                "MockClient",
                (),
                {
                    "get_account": lambda self: SimpleNamespace(id="paper-account-test"),
                    "get_orders": lambda self, filter=None: [
                        SimpleNamespace(
                            id="order_1",
                            client_order_id="oc-sig_test",
                            symbol="QQQ",
                            side="buy",
                            qty="1",
                            status="accepted",
                        )
                    ],
                },
            )()
        ),
    )
    snapshot = build_paper_status(sample_workspace)

    assert path.exists()
    assert snapshot.kill_switch.enabled is True
    assert snapshot.open_order_count == 1
    assert snapshot.order_status_counts["accepted"] == 1
    assert snapshot.notes
    catalog = build_dashboard_catalog(sample_workspace)
    assert catalog.summary.audit_count == 3
    assert {audit.action for audit in catalog.audits if audit.kind == "paper_kill_switch"} == {
        "clear",
        "enable",
    }


def test_trading_client_uses_configured_paper_base_url(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_API_BASE_URL", "https://paper-api.alpaca.markets/v2")

    captured = {}

    class MockTradingClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self._base_url = kwargs["url_override"]
            self._sandbox = kwargs["paper"]

    monkeypatch.setattr("alpaca.trading.client.TradingClient", MockTradingClient)
    alpaca_paper._trading_client()

    assert captured["api_key"] == "key"
    assert captured["secret_key"] == "secret"
    assert captured["paper"] is True
    assert captured["url_override"] == "https://paper-api.alpaca.markets"


def test_paper_scope_defaults_off_and_rejects_nonpaper_endpoint(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_PAPER", raising=False)
    assert alpaca_paper.alpaca_paper_enabled() is False

    monkeypatch.setenv("ALPACA_PAPER", "true")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_API_BASE_URL", "https://api.alpaca.markets/v2")
    with pytest.raises(alpaca_paper.PaperOrderError, match="paper-api.alpaca.markets"):
        alpaca_paper._trading_client()


def test_unverified_injected_client_cannot_submit_or_publish_paper_sync(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _mock_readiness_ok(monkeypatch)
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    _write_day_market_policy(sample_workspace, spec.name)
    signal = _target_signal(spec, action="entry", target_weight=0.01)
    _prepare_submission(sample_workspace, monkeypatch, spec, signal)
    calls = {"account": 0, "orders": 0, "submit": 0}

    class UnverifiedClient(_TargetStateClient):
        def get_account(self):
            calls["account"] += 1
            return super().get_account()

        def get_orders(self, filter=None):
            calls["orders"] += 1
            return []

        def submit_order(self, request):
            calls["submit"] += 1
            return SimpleNamespace(id="must-not-submit")

    client = UnverifiedClient(position_qty=0, equity=10_000)
    expected = "strict Alpaca Paper factory"

    with pytest.raises(alpaca_paper.PaperOrderError, match=expected):
        alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=client)
    with pytest.raises(alpaca_paper.PaperOrderError, match=expected):
        alpaca_paper.sync_paper_orders(sample_workspace, client=client)
    with pytest.raises(alpaca_paper.PaperOrderError, match=expected):
        alpaca_paper.sync_paper_account(sample_workspace, client=client)

    assert calls == {"account": 0, "orders": 0, "submit": 0}
    assert not (sample_workspace / "reports" / "paper" / "sync.jsonl").exists()
    assert not (sample_workspace / "reports" / "paper" / "account.json").exists()


def _mock_readiness_ok(monkeypatch) -> None:
    import open_composer.paper_readiness as paper_readiness

    monkeypatch.setattr(
        paper_readiness,
        "assess_paper_strategy_readiness_for_spec",
        lambda spec, root: SimpleNamespace(status="ok", execution_substate="order_authorized"),
    )


def _write_day_market_policy(root: Path, strategy_name: str) -> None:
    path = root / "reports" / "harness" / "execution" / f"{strategy_name}-execution-policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            '{"strategy_name":"fixture_pullback_15m","policy_id":"day-test",'
            '"order_style":"day_market","time_in_force":"day",'
            '"naked_market_justification":"paper-only test fixture"}'
        ),
        encoding="utf-8",
    )


def _prepare_submission(
    root: Path,
    monkeypatch,
    spec,
    signal: Signal,
    *,
    persist_signal: bool = True,
) -> None:
    from open_composer.execution_policy import require_orderable_execution_policy

    require_orderable_execution_policy(spec, root)
    signal.strategy_id = spec.name
    signal.version_id = strategy_version_id(spec)
    signal.spec_hash = strategy_content_hash(spec)
    signal.timestamp = datetime.now(UTC)
    signal.created_at = datetime.now(UTC)
    if persist_signal:
        append_jsonl(root / "signal_logs" / f"{signal.run_id}.jsonl", [signal])
    authorization = PaperOrderAuthorizationStatus(
        authorized=True,
        message="authorized for test",
        path=root / "reports" / "harness" / "paper" / f"{spec.name}-order-authorization.json",
        content_hash="a" * 64,
        payload={"authorization_id": "auth_" + ("b" * 16)},
        kind="full",
    )
    monkeypatch.setattr(
        alpaca_paper,
        "assess_paper_order_authorization",
        lambda _spec, _root: authorization,
    )
    monkeypatch.setattr(
        alpaca_paper,
        "revalidate_paper_submission_authorization",
        lambda _spec, _root, _expected: authorization,
    )
    monkeypatch.setattr(
        alpaca_paper,
        "require_fresh_paper_signal",
        lambda _signal, **kwargs: None,
    )
    monkeypatch.setattr(
        alpaca_paper,
        "require_paper_order_window",
        lambda _spec, _policy, **kwargs: None,
    )


def _prepare_canary_submission(root: Path, monkeypatch, spec, signal: Signal):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _prepare_submission(root, monkeypatch, spec, signal)
    authorization = PaperOrderAuthorizationStatus(
        authorized=True,
        message="bounded canary",
        path=root / "canary.json",
        content_hash="c" * 64,
        payload={
            "authorization_id": "auth_" + ("c" * 16),
            "authorized_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "broker_account_id_hash": broker_account_id_hash("paper-account-test"),
            "allowed_symbols": [spec.primary_symbol],
            "limits": {
                "max_order_notional_usd": 500,
                "max_session_notional_usd": 1000,
                "max_total_notional_usd": 2000,
                "max_orders_per_session": 2,
                "max_total_orders": 4,
            },
        },
        kind="canary",
    )
    monkeypatch.setattr(
        "open_composer.paper_readiness.assess_paper_strategy_readiness_for_spec",
        lambda _spec, _root: SimpleNamespace(
            status="warning",
            execution_substate="canary_authorized",
        ),
    )
    monkeypatch.setattr(
        alpaca_paper,
        "assess_paper_canary_authorization",
        lambda _spec, _root: authorization,
    )
    monkeypatch.setattr(
        alpaca_paper,
        "revalidate_paper_submission_authorization",
        lambda _spec, _root, _expected: authorization,
    )
    return authorization


class _TargetStateClient:
    def __init__(self, *, position_qty: float, equity: float, symbol: str = "QQQ") -> None:
        self.position_qty = position_qty
        self.equity = equity
        self.symbol = symbol

    def get_account(self) -> SimpleNamespace:
        return SimpleNamespace(id="paper-account-test", equity=str(self.equity))

    def get_all_positions(self) -> list[SimpleNamespace]:
        if self.position_qty == 0:
            return []
        return [SimpleNamespace(symbol=self.symbol, qty=str(self.position_qty))]

    def get_orders(self, filter=None) -> list[SimpleNamespace]:
        return []


class _VerifiedTargetStateClient(_TargetStateClient):
    _base_url = alpaca_paper.ALPACA_PAPER_ORIGIN
    _sandbox = True
    _open_composer_paper_verified = True
    _open_composer_paper_origin = alpaca_paper.ALPACA_PAPER_ORIGIN
    _open_composer_paper_verification_token = alpaca_paper._PAPER_CLIENT_VERIFICATION_TOKEN


def _verified_test_client(client):
    client._base_url = alpaca_paper.ALPACA_PAPER_ORIGIN
    client._sandbox = True
    return alpaca_paper._mark_verified_paper_client(client)


def _target_signal(spec, *, action: str, target_weight: float) -> Signal:
    return Signal(
        id=f"sig_target_{action}",
        run_id="run",
        strategy_name=spec.name,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        timestamp="2026-01-02T15:45:00Z",
        action=action,
        side="buy" if action == "entry" else "sell",
        source="scan",
        price=100.0,
        target_weight=target_weight,
        conditions=[],
        lifecycle="active",
        execution_mode="paper_auto",
        fill_assumption="next_bar_open",
    )
