from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from open_composer.adapters.broker import alpaca_paper
from open_composer.dashboard import build_dashboard_catalog
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_controls import (
    build_paper_alerts,
    build_paper_status,
    clear_paper_kill_switch,
    enable_paper_kill_switch,
    reconcile_paper_state,
    refresh_paper_monitor,
    run_paper_monitor_loop,
)


def _active_paper_spec(sample_workspace: Path) -> Path:
    draft = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    raw = yaml.safe_load(draft.read_text(encoding="utf-8"))
    raw["lifecycle"] = "active"
    raw["execution"]["mode"] = "paper_auto"
    raw["execution"]["broker"] = "alpaca_paper"
    active = sample_workspace / "strategy_specs" / "active" / "qqq_pullback_15m.yaml"
    active.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return active


def test_paper_submit_is_idempotent(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
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

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(equity="10000")

    def fake_submit(client, signal_arg, qty, client_order_id):
        calls["count"] += 1
        return SimpleNamespace(id="order_1", status="accepted")

    monkeypatch.setattr(alpaca_paper, "_submit_market_order", fake_submit)
    first = alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=MockClient())
    second = alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=MockClient())
    assert first.id == "order_1"
    assert second.signal_id == signal.id
    assert calls["count"] == 1


def test_paper_sync_writes_mock_orders(sample_workspace: Path) -> None:
    class MockClient:
        def get_orders(self) -> list[SimpleNamespace]:
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

    path = alpaca_paper.sync_paper_orders(sample_workspace, client=MockClient())
    assert path.exists()


def test_paper_account_sync_feeds_status_and_dashboard(sample_workspace: Path) -> None:
    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(
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
        client=MockClient(),
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
        client=type(
            "MockClient",
            (),
            {
                "get_account": lambda self: SimpleNamespace(
                    equity="10000",
                    cash="5000",
                    buying_power="10000",
                    portfolio_value="10000",
                    status="ACTIVE",
                ),
                "get_all_positions": lambda self: [],
            },
        )(),
    )
    write_order = sample_workspace / "reports" / "paper" / "orders.jsonl"
    write_order.parent.mkdir(parents=True, exist_ok=True)
    write_order.write_text(
        (
            '{"id":"order_1","signal_id":"sig_1","client_order_id":"oc-sig_1",'
            '"strategy_name":"qqq_pullback_15m","symbol":"QQQ","side":"buy",'
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
    assert report.report_json_path and Path(report.report_json_path).exists()
    assert report.report_markdown_path and Path(report.report_markdown_path).exists()
    assert alert_report.status == "warning"
    assert alert_report.alert_count == 1
    assert alert_report.alerts[0].code == "paper_reconciliation_issues"
    assert alert_report.report_json_path and Path(alert_report.report_json_path).exists()
    assert alert_report.report_markdown_path and Path(alert_report.report_markdown_path).exists()
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
    assert report.report_json_path and Path(report.report_json_path).exists()
    assert report.report_markdown_path and Path(report.report_markdown_path).exists()
    assert Path(report.status_path).exists()
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


def test_paper_status_snapshot_rebuilds_from_artifacts(sample_workspace: Path) -> None:
    clear_paper_kill_switch(sample_workspace, updated_by="test")
    enable_paper_kill_switch(sample_workspace, reason="maintenance", updated_by="test")
    path = alpaca_paper.sync_paper_orders(
        sample_workspace,
        client=type(
            "MockClient",
            (),
            {
                "get_orders": lambda self: [
                    SimpleNamespace(
                        id="order_1",
                        client_order_id="oc-sig_test",
                        symbol="QQQ",
                        side="buy",
                        qty="1",
                        status="accepted",
                    )
                ]
            },
        )(),
    )
    snapshot = build_paper_status(sample_workspace)

    assert path.exists()
    assert snapshot.kill_switch.enabled is True
    assert snapshot.open_order_count == 1
    assert snapshot.order_status_counts["accepted"] == 1
    assert snapshot.notes
    catalog = build_dashboard_catalog(sample_workspace)
    assert catalog.summary.audit_count == 2
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

    monkeypatch.setattr("alpaca.trading.client.TradingClient", MockTradingClient)
    alpaca_paper._trading_client()

    assert captured["api_key"] == "key"
    assert captured["secret_key"] == "secret"
    assert captured["paper"] is True
    assert captured["url_override"] == "https://paper-api.alpaca.markets"
