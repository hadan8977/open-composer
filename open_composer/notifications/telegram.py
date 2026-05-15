"""Telegram outbound-only notification adapter.

Open Composer does not consume Telegram inbound messages, webhooks, polling
updates, inline callbacks, or bot commands. Telegram is a one-way notification
channel; all Open Composer commands still flow through the confirmed dashboard
command plan/run path.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Literal


class TelegramNotificationError(RuntimeError):
    pass


def send_telegram_message(
    text: str,
    *,
    bot_token_env: str = "TELEGRAM_BOT_TOKEN",
    chat_id_env: str = "TELEGRAM_CHAT_ID",
    parse_mode: Literal["MarkdownV2", "HTML", "plain"] = "MarkdownV2",
    timeout_seconds: int = 10,
) -> dict:
    token = os.getenv(bot_token_env)
    chat_id = os.getenv(chat_id_env)
    if not token or not chat_id:
        raise TelegramNotificationError(f"missing {bot_token_env} or {chat_id_env}")
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode != "plain":
        payload["parse_mode"] = parse_mode
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise TelegramNotificationError(f"Telegram API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TelegramNotificationError(f"Telegram API URL error: {exc.reason}") from exc


def escape_markdown_v2(text: str) -> str:
    chars = r"_*[]()~`>#+-=|{}.!\\"
    return "".join(f"\\{char}" if char in chars else char for char in text)
