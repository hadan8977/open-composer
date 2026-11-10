"""Validation books must remain distinct from plans and backtest results."""

import hashlib
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from open_composer.cockpit.data.paper_trials import load_validation_trials

NOW = datetime(2026, 10, 19, 10, tzinfo=UTC)


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def book(tmp_path):
    write(
        tmp_path,
        "config/paper-validation-dashboard.json",
        {
            "schema_version": 1,
            "candidates": [
                {
                    "task_id": "MODEL",
                    "label": "Model",
                    "kind": "standalone model",
                    "snapshot": "reports/paper/validation/MODEL.json",
                }
            ],
        },
    )
    return tmp_path


def snapshot(root, **changes):
    sources = {
        key: write(root, f"reports/paper/model/{key}.json", {"kind": key})
        for key in ("decision", "checkpoint", "reconciliation", "valuation")
    }
    data = {
        "schema_version": 1,
        "task_id": "MODEL",
        "mode": "paper",
        "status": "running",
        "observed_at_utc": "2026-10-16T20:30:00Z",
        "market_as_of": "2026-10-16",
        "reconciled_at_utc": "2026-10-16T20:29:00Z",
        "source_bindings": sources,
        "capital_usd": 20000,
        "nav_usd": 20100,
        "net_pnl_usd": 100,
        "net_return_pct": 0.5,
        "net_pnl_status": "reconciled",
        "positions": [{"symbol": "SPY", "qty": 2, "market_value": 1200}],
        "orders": {"submitted": 1, "filled": 1, "rejected": 0, "pending": 0},
    }
    data.update(changes)
    write(root, "reports/paper/validation/MODEL.json", data)
    return data


def test_missing_snapshot_is_not_running_or_zero_profit(book):
    (row,) = load_validation_trials(book, now=NOW)
    assert row.status == "not_started"
    assert row.net_pnl_usd is None and row.nav_usd is None and row.filled is None


def test_running_book_has_bound_actual_data_and_market_date(book):
    snapshot(book)
    (row,) = load_validation_trials(book, now=NOW)
    assert row.status == "running"
    assert row.net_pnl_usd == 100 and row.net_return_pct == 0.5
    assert row.positions[0].market_value == 1200 and row.filled == 1
    assert row.observed_at.isoformat() == "2026-10-16T20:30:00+00:00"


def test_changed_checkpoint_cannot_keep_running_claim(book):
    snapshot(book)
    write(book, "reports/paper/model/checkpoint.json", {"changed": True})
    (row,) = load_validation_trials(book, now=NOW)
    assert row.status == "needs_attention"
    assert row.net_pnl_usd is None


def test_unreconciled_or_backtest_number_is_not_paper_profit(book):
    snapshot(book, net_pnl_status="backtest")
    (row,) = load_validation_trials(book, now=NOW)
    assert row.status == "running" and row.net_pnl_usd is None
    assert row.positions[0].market_value is None
    snapshot(book, mode="backtest")
    (row,) = load_validation_trials(book, now=NOW)
    assert row.status == "needs_attention" and row.positions == ()


def test_future_or_missing_evidence_cannot_look_current(book):
    snapshot(book, source_bindings={})
    (row,) = load_validation_trials(book, now=NOW)
    assert row.status == "needs_attention"
    snapshot(book, observed_at_utc="2026-10-20T09:30:00Z")
    (row,) = load_validation_trials(book, now=NOW)
    assert row.status == "needs_attention" and row.net_pnl_usd is None


def test_snapshot_path_cannot_read_config_or_symlink_outside_paper(book):
    config = book / "config/paper-validation-dashboard.json"
    data = json.loads(config.read_text())
    data["candidates"][0]["snapshot"] = "reports/paper/../../config/secret.env"
    config.write_text(json.dumps(data))
    (row,) = load_validation_trials(book, now=NOW)
    assert row.status == "needs_attention"
    assert not row.note


def test_no_trade_and_zero_profit_are_valid_when_actually_reconciled(book):
    snapshot(
        book,
        nav_usd=20000,
        net_pnl_usd=0,
        net_return_pct=0,
        positions=[],
        orders={"submitted": 0, "filled": 0, "rejected": 0, "pending": 0},
    )
    (row,) = load_validation_trials(book, now=NOW)
    assert row.status == "running" and row.net_pnl_usd == 0 and row.filled == 0


def test_existing_html_and_api_read_the_same_trial(book, monkeypatch):
    from open_composer.cockpit import api, app

    snapshot(book)
    write(
        book,
        "reports/paper/book/quant1/daily/2026-10-16.json",
        {
            "account": "quant1",
            "book_id": "example:F1",
            "execution_date": "2026-10-16",
            "generated_at_utc": "2026-10-16T22:40:00Z",
            "pnl": {"equity": 1020000, "net_pnl": 5000},
            "reconciliation": {"n_orders": 3, "n_filled": 3},
        },
    )
    monkeypatch.setattr(app, "project_root", lambda: book)
    monkeypatch.setattr(api, "project_root", lambda: book)
    monkeypatch.setattr(
        app,
        "_base_context",
        lambda request, active: {
            "request": request,
            "active_screen": active,
            "layout": "base.html",
            "generated_at": NOW,
            "nav_groups": [],
            "tabs": [],
            "tab_also": {},
            "full_strip": False,
            "topbar_system": {
                "title": "test",
                "status": "ok",
                "label": "test",
                "running": 0,
            },
            "topbar_rehearsal": {"label": None},
        },
    )
    client = TestClient(app.create_app(warm=False))
    payload = client.get("/api/paper.json")
    assert payload.status_code == 200
    (row,) = payload.json()["report"]["validation_trials"]
    assert row["net_pnl_usd"] == 100 and row["status"] == "running"
    assert row["kind"] == "standalone model"
    (account,) = payload.json()["report"]["account_books"]
    assert account["account"] == "quant1" and account["net_pnl_usd"] is None
    page = client.get("/paper")
    assert page.status_code == 200
    assert "Model" in page.text and "F1" in page.text
    assert 'href="/paper/ledger/trial/MODEL"' in page.text
    assert 'href="/paper/ledger/book/quant1"' in page.text
    assert "<details" not in page.text
    published_rows = {r["source_id"]: r for r in payload.json()["dashboard"]["rows"]}
    assert published_rows["MODEL"]["pnl_usd"] is None
    assert published_rows["MODEL"]["status_label"] == "等待估值"
    detail = client.get(published_rows["MODEL"]["href"])
    assert detail.status_code == 200
    assert "SPY" in detail.text and "已提交" in detail.text and "已成交" in detail.text
    assert client.get(published_rows["quant1"]["href"]).status_code == 200
    assert client.get("/paper/ledger/trial/unknown").status_code == 404


def current_service(
    root,
    monkeypatch,
    *,
    heartbeat="2026-10-19T10:00:00Z",
    operation_at=None,
    status="process_online",
):
    from scripts import reconcile_six_paper_performance

    config_path = root / "config/paper-validation-dashboard.json"
    config = json.loads(config_path.read_text())
    activities = write(root, "reports/paper/filled.json", {"activities": []})
    config.update(
        service_state="reports/research/program/current/runtime.json",
        performance_activities=activities["path"],
        performance_activities_sha256=activities["sha256"],
    )
    config["candidates"][0]["policy"] = "MODEL"
    config_path.write_text(json.dumps(config))
    write(
        root,
        config["service_state"],
        {
            "heartbeat_at": heartbeat,
            "status": status,
            "policy_status": {
                "MODEL": {
                    "status": "ready_waiting_rth",
                    "observed_at": operation_at or heartbeat,
                }
            },
            "orders": {"unconfirmed": {"book": "MODEL", "status": "prepared_unknown"}},
        },
    )
    monkeypatch.setattr(
        reconcile_six_paper_performance,
        "project",
        lambda *args, **kwargs: {
            "broker_account_observed_at": "2026-10-19T09:59:50Z",
            "sleeves": {
                "MODEL": {
                    "market_value_usd": 1200,
                    "trading_PnL_before_unverified_items_usd": 25,
                    "execution_basis_status": "reported_average_provisional",
                }
            },
        },
    )


def test_live_heartbeat_and_components_are_distinct_from_certified_net(book, monkeypatch):
    snapshot(book, status="starting", net_pnl_status="unknown")
    current_service(book, monkeypatch)
    (row,) = load_validation_trials(book, now=NOW)
    assert row.service_phase == "waiting_market_open"
    assert row.service_observed_at == NOW
    assert row.component_pnl_usd == 25 and row.component_market_value_usd == 1200
    assert row.component_basis_status == "reported_average_provisional"
    assert row.net_pnl_usd is None and row.nav_usd is None
    assert row.recorded_order_intents == 1 and row.submitted == 0


def test_stopped_heartbeat_cannot_keep_a_current_service_label(book, monkeypatch):
    snapshot(book, status="starting", net_pnl_status="unknown")
    current_service(book, monkeypatch, heartbeat="2026-10-19T09:50:00Z")
    (row,) = load_validation_trials(book, now=NOW)
    assert row.service_phase == "stale"
    assert row.net_pnl_usd is None


def test_fresh_heartbeat_cannot_hide_stale_successful_operation(book, monkeypatch):
    snapshot(book, status="starting", net_pnl_status="unknown")
    current_service(book, monkeypatch, operation_at="2026-10-19T09:50:00Z")
    (row,) = load_validation_trials(book, now=NOW)
    assert row.service_phase == "stale"
    assert row.service_observed_at.isoformat() == "2026-10-19T09:50:00+00:00"


def test_global_pause_overrides_a_fresh_previous_ready_operation(book, monkeypatch):
    snapshot(book, status="starting", net_pnl_status="unknown")
    current_service(book, monkeypatch, status="paused_or_expired")
    (row,) = load_validation_trials(book, now=NOW)
    assert row.service_phase == "paused_or_expired"


def test_changed_execution_evidence_keeps_operation_but_withholds_components(book, monkeypatch):
    snapshot(book, status="starting", net_pnl_status="unknown")
    current_service(book, monkeypatch)
    write(book, "reports/paper/filled.json", {"activities": ["changed"]})
    (row,) = load_validation_trials(book, now=NOW)
    assert row.service_phase == "waiting_market_open"
    assert row.component_pnl_usd is None and row.net_pnl_usd is None
    assert any("components unavailable" in warning for warning in row.warnings)


SATURDAY = datetime(2026, 10, 24, 6, tzinfo=UTC)


def weekend_case(book, monkeypatch, *, now=SATURDAY, application="2026-10-23"):
    snapshot(book, status="failed", net_pnl_status="unknown", observed_at_utc=now.isoformat())
    current_service(book, monkeypatch, heartbeat=now.isoformat())
    config_path = book / "config/paper-validation-dashboard.json"
    config = json.loads(config_path.read_text())
    config["candidates"][0]["policy"] = "BASE"
    config_path.write_text(json.dumps(config))
    decision = write(
        book,
        "reports/research/program/paper-launch-20min-20261021/targets/BASE.json",
        {
            "policy": "BASE",
            "as_of": "2026-10-22T20:00:00Z",
            "application_day": application,
            "reference_day": "2026-10-23" if application == "2026-10-26" else "2026-10-22",
            "valid_until": application + "T19:30:00Z",
        },
    )
    # Actual native publisher uses an absolute, hash-bound decision path.
    decision["path"] = str(book / decision["path"])
    path = book / "reports/paper/validation/MODEL.json"
    data = json.loads(path.read_text())
    data["source_bindings"]["decision"] = decision
    path.write_text(json.dumps(data))
    runtime = book / config["service_state"]
    state = json.loads(runtime.read_text())
    state.update(
        account={"observed_at": now.isoformat()},
        position_mismatch={},
        open_orders=[],
        foreign_open_orders=[],
        orders={},
        policy_status={
            "BASE": {
                "status": "blocked",
                "error_type": "ValueError",
                "observed_at": now.isoformat(),
            }
        },
    )
    runtime.write_text(json.dumps(state))
    return runtime, decision


def test_weekend_carrying_is_distinct_from_expired_instruction_and_future_inputs(book, monkeypatch):
    runtime, _ = weekend_case(book, monkeypatch)
    before = runtime.read_bytes()
    (row,) = load_validation_trials(book, now=SATURDAY)
    assert row.service_phase == "closed_market_carrying"
    assert row.instruction_status == "expired"
    assert row.next_input_status == "awaiting_session_inputs"
    assert row.next_application_day == "2026-10-26"
    assert row.refresh_not_before.isoformat() == "2026-10-26T00:20:00+00:00"
    assert "blocked (ValueError)" in row.note
    assert row.status == "failed"  # Original snapshot remains visible to API consumers.
    assert row.net_pnl_usd is None and row.nav_usd is None
    assert runtime.read_bytes() == before


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"position_mismatch": {"SPY": [1, 2]}}, "blocked"),
        ({"foreign_open_orders": ["foreign"]}, "blocked"),
        ({"open_orders": ["own"]}, "blocked"),
        (
            {"orders": {"own": {"status": "prepared_unknown_until_queried"}}},
            "closed_market_carrying_order_uncertain",
        ),
        ({"account": {"observed_at": "2026-10-23T20:00:00Z"}}, "blocked"),
        ({"heartbeat_at": "2026-10-23T20:00:00Z"}, "stale"),
        ({"status": "paused_or_expired"}, "paused_or_expired"),
    ],
)
def test_closed_market_does_not_hide_reconciliation_staleness_or_pause(
    book, monkeypatch, change, expected
):
    runtime, _ = weekend_case(book, monkeypatch)
    state = json.loads(runtime.read_text())
    state.update(change)
    runtime.write_text(json.dumps(state))
    (row,) = load_validation_trials(book, now=SATURDAY)
    assert row.service_phase == expected


def test_missing_changed_target_does_not_gain_time_validity(book, monkeypatch):
    _, decision = weekend_case(book, monkeypatch)
    path = book / decision["path"]
    path.write_text("{}")
    (row,) = load_validation_trials(book, now=SATURDAY)
    assert row.instruction_status == "unavailable_or_invalid"


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("failed", "producer_failed"),
        ("unresolved", "attempt_unresolved"),
        ("blocked", "dependency_blocked"),
        ("published", "future_packet_unverified"),
    ],
)
def test_next_session_attempt_outcomes_are_not_readiness_claims(book, monkeypatch, kind, expected):
    _, decision = weekend_case(book, monkeypatch, application="2026-10-26")
    folder = "reports/paper/diagnostics/dated-target-refresh/2026-10-26/"
    write(book, folder + "launch-intent.json", {})
    if kind != "unresolved":
        write(
            book,
            folder + "refresh-exit.json",
            {
                "exit_code": 1 if kind == "failed" else 0,
                "published": {"BASE": decision} if kind == "published" else {},
            },
        )
        write(
            book,
            folder + "target-production-result.json",
            {"blocked_policies": {"BASE": "missing source"} if kind == "blocked" else {}},
        )
    (row,) = load_validation_trials(book, now=SATURDAY)
    assert row.next_input_status == expected
    assert row.service_phase == "closed_market_carrying"


def test_rth_does_not_become_closed_carrying_and_missed_refresh_is_explicit(book, monkeypatch):
    monday = datetime(2026, 10, 26, 15, tzinfo=UTC)
    weekend_case(book, monkeypatch, now=monday)
    (row,) = load_validation_trials(book, now=monday)
    assert row.service_phase == "blocked"
    assert row.next_input_status == "refresh_not_started"
    assert row.instruction_status == "expired"


def test_within_time_bounds_does_not_override_operator_block(book, monkeypatch):
    monday = datetime(2026, 10, 26, 15, tzinfo=UTC)
    weekend_case(book, monkeypatch, now=monday, application="2026-10-26")
    (row,) = load_validation_trials(book, now=monday)
    assert row.instruction_status == "within_time_bounds"
    assert row.service_phase == "blocked"


def test_current_session_operator_success_stays_separate_from_published_packet(book, monkeypatch):
    monday = datetime(2026, 10, 26, 15, tzinfo=UTC)
    runtime, decision = weekend_case(book, monkeypatch, now=monday, application="2026-10-26")
    state = json.loads(runtime.read_text())
    state["policy_status"]["BASE"]["status"] = "operating"
    runtime.write_text(json.dumps(state))
    folder = "reports/paper/diagnostics/dated-target-refresh/2026-10-26/"
    write(
        book,
        folder + "refresh-exit.json",
        {"exit_code": 0, "published": {"BASE": decision}},
    )
    write(book, folder + "target-production-result.json", {"blocked_policies": {}})
    (row,) = load_validation_trials(book, now=monday)
    assert row.service_phase == "operating"
    assert row.next_input_status == "publication_recorded_not_operating_acceptance"
    assert row.instruction_status == "within_time_bounds"
    assert row.net_pnl_usd is None


def test_expired_guard_is_unchanged_by_display_projection():
    from open_composer.intraday_runner.six_paper_service import validate_target

    with pytest.raises(ValueError, match="wrong, future or expired"):
        validate_target(
            {
                "policy": "BASE",
                "as_of": "2026-10-22T20:00:00Z",
                "valid_until": "2026-10-23T19:30:00Z",
            },
            "BASE",
            SATURDAY,
        )


def test_unresolved_sibling_identity_does_not_taint_other_sleeve(book, monkeypatch):
    runtime, _ = weekend_case(book, monkeypatch)
    state = json.loads(runtime.read_text())
    state["orders"] = {
        "old": {"book": "BASE_STATE_BUDGET", "status": "prepared_unknown_until_queried"}
    }
    runtime.write_text(json.dumps(state))
    (row,) = load_validation_trials(book, now=SATURDAY)
    assert row.service_phase == "closed_market_carrying"
    assert row.unresolved_order_intents == 0
