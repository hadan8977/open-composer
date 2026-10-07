"""scripts/owner_report.py: transient SMTP errors are retried, others are not."""

from __future__ import annotations

import importlib.util
import smtplib
import ssl
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "owner_report_script", ROOT / "scripts" / "owner_report.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("owner_report_script", module)
    spec.loader.exec_module(module)
    return module


owner_report = _load()


def _flaky(failures: list[BaseException]):
    calls: list[int] = []

    def sender(config, message):
        calls.append(1)
        if failures:
            raise failures.pop(0)

    return sender, calls


def test_transient_ssl_eof_is_retried_then_sent():
    sender, calls = _flaky([ssl.SSLEOFError("EOF occurred in violation of protocol")])
    waits: list[float] = []
    used = owner_report.send_with_retry(None, None, sender=sender, sleep=waits.append)
    assert used == 2
    assert len(calls) == 2
    assert waits == [owner_report.SEND_BACKOFF_SECONDS[0]]


def test_gives_up_after_three_attempts():
    failures = [smtplib.SMTPServerDisconnected("closed") for _ in range(3)]
    sender, calls = _flaky(failures)
    waits: list[float] = []
    with pytest.raises(smtplib.SMTPServerDisconnected):
        owner_report.send_with_retry(None, None, sender=sender, sleep=waits.append)
    assert len(calls) == 3
    assert waits == list(owner_report.SEND_BACKOFF_SECONDS)


def test_authentication_error_is_not_retried():
    sender, calls = _flaky([smtplib.SMTPAuthenticationError(535, b"bad credentials")])
    with pytest.raises(smtplib.SMTPAuthenticationError):
        owner_report.send_with_retry(None, None, sender=sender, sleep=lambda _s: None)
    assert len(calls) == 1
