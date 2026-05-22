from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_composer.models.runner import PaperRunSignalResult
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.notifications import (
    dispatch_notification,
    notification_config_status,
    read_notification_log,
    send_test_notification,
)
from open_composer.notifications.telegram import TelegramNotificationError, send_telegram_message
from open_composer.paper_controls import set_paper_kill_switch
from open_composer.runner.paper import _notify_paper_signal


def test_telegram_missing_token_or_chat_raises(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(TelegramNotificationError, match="missing"):
        send_telegram_message("hello")


def test_dispatch_writes_log_with_default_config(sample_workspace: Path) -> None:
    record = dispatch_notification(
        kind="signal_actionable",
        severity="info",
        title="Signal test",
        body="QQQ entry",
        metadata={"signal_id": "sig-1"},
        root=sample_workspace,
    )

    rows = read_notification_log(sample_workspace)

    assert record.kind == "signal_actionable"
    assert rows[-1]["title"] == "Signal test"
    assert any(item["channel"] == "log_only" for item in rows[-1]["deliveries"])
    assert (sample_workspace / "reports" / "notifications" / "log.jsonl").exists()


def test_severity_gate_skips_outbound_when_below_policy(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    _write_config(
        sample_workspace,
        """
version: 1
telegram:
  enabled: true
policies:
  - kind: system_alert
    channels: [telegram, log_only]
    min_severity: warn
""",
    )

    def fail_send(*_args, **_kwargs):
        raise AssertionError("telegram send should not run")

    monkeypatch.setattr("open_composer.notifications.send_telegram_message", fail_send)
    record = dispatch_notification(
        kind="system_alert",
        severity="info",
        title="Below gate",
        root=sample_workspace,
    )

    assert record.deliveries[0].status == "skipped"
    assert "below policy" in record.deliveries[0].message


def test_channel_failure_does_not_raise_and_does_not_log_secret(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    _write_config(
        sample_workspace,
        """
version: 1
telegram:
  enabled: true
policies:
  - kind: system_alert
    channels: [telegram, log_only]
    min_severity: info
""",
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "secret-chat")

    def fail_send(*_args, **_kwargs):
        raise TelegramNotificationError("network failed")

    monkeypatch.setattr("open_composer.notifications.send_telegram_message", fail_send)

    record = dispatch_notification(
        kind="system_alert",
        severity="info",
        title="System",
        root=sample_workspace,
    )

    text = (sample_workspace / "reports" / "notifications" / "log.jsonl").read_text(
        encoding="utf-8"
    )
    assert any(item.channel == "telegram" and item.status == "error" for item in record.deliveries)
    assert "secret-token" not in text
    assert "secret-chat" not in text


def test_notify_test_dry_run_and_status(sample_workspace: Path) -> None:
    record = send_test_notification(sample_workspace, dry_run=True)
    status = notification_config_status(sample_workspace)

    assert record.kind == "signal_actionable"
    assert status.config_path == "config/notifications.yaml"
    assert status.log_path == "reports/notifications/log.jsonl"


def test_kill_switch_records_notification(sample_workspace: Path) -> None:
    set_paper_kill_switch(
        sample_workspace,
        enabled=True,
        reason="operator hold",
        updated_by="pytest",
    )

    rows = read_notification_log(sample_workspace)
    assert rows[-1]["kind"] == "kill_switch"
    assert rows[-1]["severity"] == "red"
    assert rows[-1]["metadata"]["enabled"] is True


def test_paper_runner_signal_notification_hook(sample_workspace: Path) -> None:
    spec = load_strategy_spec(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    )
    signal_result = PaperRunSignalResult(
        signal_id="sig-order-error",
        action="entry",
        symbol="QQQ",
        price=100.0,
        decision="order_error",
        message="alpaca rejected order",
    )

    _notify_paper_signal(signal_result, spec, sample_workspace)

    rows = read_notification_log(sample_workspace)
    assert rows[-1]["kind"] == "alpaca_error"
    assert rows[-1]["severity"] == "red"
    assert rows[-1]["metadata"]["signal_id"] == "sig-order-error"


def _write_config(root: Path, text: str) -> None:
    path = root / "config" / "notifications.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def test_notification_log_is_jsonl(sample_workspace: Path) -> None:
    dispatch_notification(kind="system_alert", severity="info", title="JSON", root=sample_workspace)
    path = sample_workspace / "reports" / "notifications" / "log.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        assert json.loads(line)["id"]
