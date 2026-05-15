from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from open_composer.config import project_root, run_id
from open_composer.models.notification import (
    NotificationChannel,
    NotificationConfig,
    NotificationConfigStatus,
    NotificationDelivery,
    NotificationKind,
    NotificationPolicy,
    NotificationRecord,
    NotificationSeverity,
)
from open_composer.notifications.telegram import (
    TelegramNotificationError,
    escape_markdown_v2,
    send_telegram_message,
)
from open_composer.storage import append_jsonl

CONFIG_PATH = Path("config") / "notifications.yaml"
LOG_PATH = Path("reports") / "notifications" / "log.jsonl"
SEVERITY_RANK: dict[NotificationSeverity, int] = {"info": 1, "warn": 2, "red": 3}

DEFAULT_POLICIES = [
    NotificationPolicy(
        kind="signal_actionable",
        channels=["telegram", "log_only"],
        min_severity="info",
    ),
    NotificationPolicy(kind="signal_paper_only", channels=["log_only"], min_severity="info"),
    NotificationPolicy(kind="kill_switch", channels=["telegram", "log_only"], min_severity="red"),
    NotificationPolicy(kind="alpaca_error", channels=["telegram", "log_only"], min_severity="warn"),
    NotificationPolicy(kind="system_alert", channels=["telegram", "log_only"], min_severity="warn"),
    NotificationPolicy(
        kind="selector_recommendation",
        channels=["log_only"],
        min_severity="info",
    ),
    NotificationPolicy(kind="regime_change", channels=["log_only"], min_severity="warn"),
    NotificationPolicy(kind="digest_daily", channels=["log_only"], min_severity="info"),
]


class NotificationConfigError(RuntimeError):
    pass


def load_notification_config(root: Path | None = None) -> NotificationConfig:
    base = root or project_root()
    path = base / CONFIG_PATH
    if not path.exists():
        return NotificationConfig(policies=list(DEFAULT_POLICIES))
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise NotificationConfigError(f"invalid notification config YAML: {exc}") from exc
    try:
        config = NotificationConfig.model_validate(raw)
    except ValidationError as exc:
        raise NotificationConfigError(str(exc)) from exc
    if not config.policies:
        config.policies = list(DEFAULT_POLICIES)
    return config


def notification_config_status(root: Path | None = None) -> NotificationConfigStatus:
    base = root or project_root()
    config = load_notification_config(base)
    config_path = base / CONFIG_PATH
    log_path = base / LOG_PATH
    telegram = config.telegram
    return NotificationConfigStatus(
        config_path=_relpath(config_path, base),
        config_exists=config_path.exists(),
        log_path=_relpath(log_path, base),
        telegram_enabled=telegram.enabled,
        telegram_bot_token_env=telegram.bot_token_env,
        telegram_bot_token_present=bool(os.getenv(telegram.bot_token_env)),
        telegram_chat_id_env=telegram.chat_id_env,
        telegram_chat_id_present=bool(os.getenv(telegram.chat_id_env)),
        telegram_parse_mode=telegram.parse_mode,
        policies=config.policies,
        config=config,
    )


def read_notification_log(root: Path | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
    base = root or project_root()
    path = base / LOG_PATH
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-max(0, limit) :]


def dispatch_notification(
    *,
    kind: NotificationKind,
    severity: NotificationSeverity,
    title: str,
    body: str = "",
    metadata: dict[str, Any] | None = None,
    root: Path | None = None,
    dry_run: bool = False,
) -> NotificationRecord:
    base = root or project_root()
    config = load_notification_config(base)
    policy = _policy_for_kind(config.policies, kind)
    channels = _normalized_channels(policy.channels)
    record = NotificationRecord(
        id=run_id(f"notify-{kind}"),
        kind=kind,
        severity=severity,
        title=title,
        body=body,
        metadata=metadata or {},
        requested_channels=channels,
    )
    severity_allowed = SEVERITY_RANK[severity] >= SEVERITY_RANK[policy.min_severity]
    if not severity_allowed:
        record.deliveries.append(
            NotificationDelivery(
                channel="log_only",
                status="skipped",
                message=f"severity below policy min_severity={policy.min_severity}",
            )
        )
        _append_notification_record(base, record)
        return record

    for channel in channels:
        if channel == "log_only":
            record.deliveries.append(
                NotificationDelivery(channel="log_only", status="delivered", message="logged")
            )
            continue
        if channel == "telegram":
            record.deliveries.append(_deliver_telegram(config, record, dry_run=dry_run))
    _append_notification_record(base, record)
    return record


def safe_dispatch_notification(
    *,
    kind: NotificationKind,
    severity: NotificationSeverity,
    title: str,
    body: str = "",
    metadata: dict[str, Any] | None = None,
    root: Path | None = None,
) -> NotificationRecord | None:
    base = root or project_root()
    try:
        return dispatch_notification(
            kind=kind,
            severity=severity,
            title=title,
            body=body,
            metadata=metadata,
            root=base,
        )
    except Exception as exc:
        record = NotificationRecord(
            id=run_id(f"notify-{kind}-error"),
            kind=kind,
            severity=severity,
            title=title,
            body=body,
            metadata=metadata or {},
            requested_channels=["log_only"],
            deliveries=[
                NotificationDelivery(
                    channel="log_only",
                    status="error",
                    message=f"notification dispatch failed: {exc}",
                )
            ],
        )
        try:
            _append_notification_record(base, record)
        except Exception:
            return None
        return record


def send_test_notification(
    root: Path | None = None,
    *,
    kind: NotificationKind = "signal_actionable",
    severity: NotificationSeverity = "info",
    dry_run: bool = False,
) -> NotificationRecord:
    return dispatch_notification(
        kind=kind,
        severity=severity,
        title="Open Composer notification test",
        body="Hello from Open Composer.",
        metadata={"source": "oc notify test"},
        root=root,
        dry_run=dry_run,
    )


def _deliver_telegram(
    config: NotificationConfig,
    record: NotificationRecord,
    *,
    dry_run: bool,
) -> NotificationDelivery:
    telegram = config.telegram
    if not telegram.enabled:
        return NotificationDelivery(
            channel="telegram",
            status="skipped",
            message="telegram disabled",
        )
    if dry_run:
        return NotificationDelivery(channel="telegram", status="dry_run", message="not sent")
    try:
        send_telegram_message(
            _telegram_text(record, parse_mode=telegram.parse_mode),
            bot_token_env=telegram.bot_token_env,
            chat_id_env=telegram.chat_id_env,
            parse_mode=telegram.parse_mode,
        )
    except TelegramNotificationError as exc:
        return NotificationDelivery(channel="telegram", status="error", message=str(exc))
    return NotificationDelivery(channel="telegram", status="delivered", message="sent")


def _telegram_text(record: NotificationRecord, *, parse_mode: str) -> str:
    title = f"[{record.severity.upper()}] {record.title}"
    lines = [title, record.body.strip()]
    meta_parts = [
        f"{key}={value}"
        for key, value in sorted(record.metadata.items())
        if value is not None and isinstance(value, str | int | float | bool)
    ]
    if meta_parts:
        lines.append(" ".join(meta_parts[:8]))
    text = "\n".join(line for line in lines if line)
    if parse_mode == "MarkdownV2":
        return escape_markdown_v2(text)
    return text


def _policy_for_kind(
    policies: Iterable[NotificationPolicy],
    kind: NotificationKind,
) -> NotificationPolicy:
    for policy in policies:
        if policy.kind == kind:
            return policy
    return NotificationPolicy(kind=kind, channels=["log_only"], min_severity="info")


def _normalized_channels(channels: list[NotificationChannel]) -> list[NotificationChannel]:
    result: list[NotificationChannel] = []
    for channel in [*channels, "log_only"]:
        if channel not in result:
            result.append(channel)
    return result


def _append_notification_record(root: Path, record: NotificationRecord) -> None:
    append_jsonl(root / LOG_PATH, [record])


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
