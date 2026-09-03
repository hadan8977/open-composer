"""Staleness must be loud, not silent."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_sip_freshness import (  # noqa: E402
    last_completed_session,
    sessions_behind,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_weekends_and_holidays_do_not_read_as_drift() -> None:
    # 2026-01-01 is a market holiday and 2026-01-03/04 is a weekend, so the last
    # completed session before Monday 2026-01-05 is Friday 2026-01-02.
    assert last_completed_session(date(2026, 1, 5)) == date(2026, 1, 2)


def test_an_archive_current_to_the_last_session_is_zero_behind() -> None:
    reference = last_completed_session(date(2026, 9, 2))
    assert sessions_behind(reference, reference) == 0


def test_a_bar_ahead_of_the_reference_is_not_negative() -> None:
    assert sessions_behind(date(2026, 9, 10), date(2026, 9, 2)) == 0


def test_sessions_behind_counts_trading_days_not_calendar_days() -> None:
    # Friday 2026-01-02 to Monday 2026-01-05 is three calendar days but one session.
    assert sessions_behind(date(2026, 1, 2), date(2026, 1, 5)) == 1


def test_a_long_gap_is_reported_in_sessions() -> None:
    behind = sessions_behind(date(2026, 8, 4), date(2026, 9, 1))
    # Four weeks of trading days, not 28.
    assert 15 <= behind <= 22


def test_notify_on_stale_dispatches_a_system_alert(tmp_path: Path) -> None:
    import os

    env = {**os.environ, "OPEN_COMPOSER_ROOT": str(tmp_path)}
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "check_sip_freshness.py"),
            "--today",
            "2030-01-01",
            "--notify-on-stale",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1, result.stderr
    log_path = tmp_path / "reports" / "notifications" / "log.jsonl"
    assert log_path.exists(), result.stderr
    rows = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    alerts = [row for row in rows if row["kind"] == "system_alert"]
    assert alerts, rows
    assert "SIP archive stale" in alerts[-1]["title"]


def test_without_the_flag_no_notification_is_dispatched(tmp_path: Path) -> None:
    import os

    env = {**os.environ, "OPEN_COMPOSER_ROOT": str(tmp_path)}
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "check_sip_freshness.py"),
            "--today",
            "2030-01-01",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1, result.stderr
    log_path = tmp_path / "reports" / "notifications" / "log.jsonl"
    assert not log_path.exists()
