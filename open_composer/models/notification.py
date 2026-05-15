from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

NotificationChannel = Literal["telegram", "log_only"]
NotificationKind = Literal[
    "signal_actionable",
    "signal_paper_only",
    "selector_recommendation",
    "kill_switch",
    "alpaca_error",
    "regime_change",
    "digest_daily",
    "system_alert",
]
NotificationSeverity = Literal["info", "warn", "red"]
NotificationDeliveryStatus = Literal["delivered", "dry_run", "error", "skipped"]


class TelegramConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    chat_id_env: str = "TELEGRAM_CHAT_ID"
    parse_mode: Literal["MarkdownV2", "HTML", "plain"] = "MarkdownV2"
    quiet_hours_local: tuple[int, int] | None = None


class NotificationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: NotificationKind
    channels: list[NotificationChannel] = Field(default_factory=lambda: ["log_only"])
    min_severity: NotificationSeverity = "info"


class NotificationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    policies: list[NotificationPolicy] = Field(default_factory=list)


class NotificationDelivery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: NotificationChannel
    status: NotificationDeliveryStatus
    message: str = ""


class NotificationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: NotificationKind
    severity: NotificationSeverity
    title: str
    body: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    requested_channels: list[NotificationChannel] = Field(default_factory=list)
    deliveries: list[NotificationDelivery] = Field(default_factory=list)


class NotificationConfigStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_path: str
    config_exists: bool
    log_path: str
    telegram_enabled: bool
    telegram_bot_token_env: str
    telegram_bot_token_present: bool
    telegram_chat_id_env: str
    telegram_chat_id_present: bool
    telegram_parse_mode: str
    policies: list[NotificationPolicy] = Field(default_factory=list)
    config: NotificationConfig
