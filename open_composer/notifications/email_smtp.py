"""Send e-mail over SMTP (the owner digest, `docs/owner-reporting.zh.md`).

The credentials live outside the repository in a KEY=VALUE file (mode 600):
``SMTP_HOST``, ``SMTP_PORT``, ``SMTP_USER``, ``SMTP_PASSWORD``, ``MAIL_FROM`` and
``MAIL_TO`` (comma-separated).  Port 465 uses implicit TLS, any other port STARTTLS.
Nothing here prints or logs the password.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any

DEFAULT_MAIL_ENV = Path("/root/.config/open-composer/report-mail.env")
MAIL_ENV_VAR = "OC_REPORT_MAIL_ENV"
REQUIRED_KEYS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_TO")


class MailConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class MailConfig:
    host: str
    port: int
    user: str
    sender: str
    recipients: tuple[str, ...]
    password: str = field(repr=False)


def mail_env_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    override = os.environ.get(MAIL_ENV_VAR)
    return Path(override) if override else DEFAULT_MAIL_ENV


def load_mail_config(path: Path | None = None) -> MailConfig:
    source = mail_env_path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise MailConfigError(f"cannot read mail config {source}: {exc.strerror}") from None
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    missing = [key for key in REQUIRED_KEYS if not values.get(key)]
    if missing:
        raise MailConfigError(f"{source}: missing {', '.join(missing)}")
    try:
        port = int(values["SMTP_PORT"])
    except ValueError:
        raise MailConfigError(f"{source}: SMTP_PORT is not a number") from None
    recipients = tuple(addr.strip() for addr in values["MAIL_TO"].split(",") if addr.strip())
    return MailConfig(
        host=values["SMTP_HOST"],
        port=port,
        user=values["SMTP_USER"],
        sender=values["MAIL_FROM"],
        recipients=recipients,
        password=values["SMTP_PASSWORD"],
    )


def build_message(
    config: MailConfig,
    subject: str,
    text: str,
    html: str | None = None,
    attachments: Sequence[tuple[str, str]] = (),
) -> EmailMessage:
    """Plain text (+ optional HTML alternative); ``attachments`` are
    ``(filename, utf-8 text)`` pairs sent as ``text/markdown`` files."""
    message = EmailMessage()
    message["From"] = config.sender
    message["To"] = ", ".join(config.recipients)
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain="open-composer.local")
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    for filename, body in attachments:
        message.add_attachment(
            body.encode("utf-8"), maintype="text", subtype="markdown", filename=filename
        )
    return message


def send_message(
    config: MailConfig,
    message: EmailMessage,
    *,
    smtp_factory: Callable[..., Any] | None = None,
    timeout: float = 30.0,
) -> None:
    context = ssl.create_default_context()
    if config.port == 465:
        factory = smtp_factory or smtplib.SMTP_SSL
        server = factory(config.host, config.port, timeout=timeout, context=context)
    else:
        factory = smtp_factory or smtplib.SMTP
        server = factory(config.host, config.port, timeout=timeout)
    with server:
        if config.port != 465:
            server.starttls(context=context)
        server.login(config.user, config.password)
        server.send_message(message)
