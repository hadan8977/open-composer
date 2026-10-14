from __future__ import annotations

import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_book_v12_daily as driver  # noqa: E402


@pytest.fixture(autouse=True)
def current_plan_dates(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 7, 18, tzinfo=UTC)

    monkeypatch.setattr(driver, "datetime", Clock)
    monkeypatch.setattr(
        driver,
        "load_target_file",
        lambda path: SimpleNamespace(
            decision_date=date(2026, 10, 6), execution_date=date(2026, 10, 7)
        ),
    )


def test_run_plans_submits_every_account_even_when_one_fails(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        account = cmd[cmd.index("--account") + 1]
        failed = account == driver.BOOK_ACCOUNTS[0] and "submit" in cmd
        return subprocess.CompletedProcess(cmd, 2 if failed else 0, "", "")

    monkeypatch.setattr(driver.subprocess, "run", fake_run)
    monkeypatch.setattr(driver, "target_path", lambda root, account, day: Path(__file__))
    code = driver.run_plans(tmp_path, date(2026, 10, 6), submit=True)
    assert code == driver.EXIT_COMMAND
    ran = [(c[c.index("--account") + 1], c[c.index("book-paper") + 1]) for c in calls]
    second = driver.BOOK_ACCOUNTS[1]
    assert (second, "plan") in ran and (second, "submit") in ran


def test_run_plans_skips_submit_after_a_failed_plan(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        account = cmd[cmd.index("--account") + 1]
        failed = account == driver.BOOK_ACCOUNTS[0] and "plan" in cmd
        return subprocess.CompletedProcess(cmd, 1 if failed else 0, "", "")

    monkeypatch.setattr(driver.subprocess, "run", fake_run)
    monkeypatch.setattr(driver, "target_path", lambda root, account, day: Path(__file__))
    assert driver.run_plans(tmp_path, date(2026, 10, 6), submit=True) == driver.EXIT_COMMAND
    ran = [(c[c.index("--account") + 1], c[c.index("book-paper") + 1]) for c in calls]
    assert (driver.BOOK_ACCOUNTS[0], "submit") not in ran
    assert (driver.BOOK_ACCOUNTS[1], "submit") in ran


def test_run_plans_returns_zero_when_all_steps_pass(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        driver.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, "", "")
    )
    monkeypatch.setattr(driver, "target_path", lambda root, account, day: Path(__file__))
    assert driver.run_plans(tmp_path, date(2026, 10, 6), submit=True) == 0


def test_run_plans_forwards_the_tif_mode_to_submit(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(driver.subprocess, "run", fake_run)
    monkeypatch.setattr(driver, "target_path", lambda root, account, day: Path(__file__))
    rc = driver.run_plans(tmp_path, date(2026, 10, 6), submit=True, tif_mode="market")
    assert rc == 0
    submits = [c for c in calls if "submit" in c]
    assert len(submits) == 2
    assert all(c[c.index("--tif-mode") + 1] == "market" for c in submits)


def test_run_plans_submits_only_the_named_accounts(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(driver.subprocess, "run", fake_run)
    monkeypatch.setattr(driver, "target_path", lambda root, account, day: Path(__file__))
    rc = driver.run_plans(
        tmp_path, date(2026, 10, 6), submit=True, tif_mode="market", accounts=("quant1",)
    )
    assert rc == 0
    accounts = {c[c.index("--account") + 1] for c in calls}
    assert accounts == {"quant1"}
    assert [c[c.index("book-paper") + 1] for c in calls] == ["plan", "submit"]


def test_main_rejects_unknown_accounts(capsys) -> None:
    with pytest.raises(SystemExit):
        driver.main(["--plan", "--accounts", "quant3"])
    assert "--accounts must name book accounts" in capsys.readouterr().err


def test_default_targets_refuses_stale_calendar_before_old_target_noop(monkeypatch, tmp_path):
    data = tmp_path / "private"
    (data / "panel").mkdir(parents=True)
    (data / "panel/_calendar.parquet").touch()
    monkeypatch.setattr(driver.v12, "last_session", lambda root: date(2026, 10, 7))
    monkeypatch.setattr(driver, "target_path", lambda *args: Path(__file__))
    monkeypatch.setattr(driver.v12, "build_v12_bundle", lambda *a, **k: pytest.fail("stale build"))
    assert (
        driver.run_targets(tmp_path, data, None, None, now=datetime(2026, 10, 14, 1, tzinfo=UTC))
        == driver.EXIT_FRESH
    )


def test_old_target_plan_refused_before_subprocess_or_broker(monkeypatch, tmp_path):
    monkeypatch.setattr(driver, "latest_target_path", lambda *args: Path(__file__))
    monkeypatch.setattr(driver.subprocess, "run", lambda *a, **k: pytest.fail("stale broker call"))
    assert (
        driver.run_plans(tmp_path, None, submit=False, now=datetime(2026, 10, 13, 18, tzinfo=UTC))
        == driver.EXIT_FRESH
    )


def test_next_session_preview_is_readonly_and_backdated_submit_refused(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(driver, "target_path", lambda *args: Path(__file__))
    monkeypatch.setattr(
        driver,
        "load_target_file",
        lambda *a: SimpleNamespace(
            decision_date=date(2026, 10, 13), execution_date=date(2026, 10, 14)
        ),
    )
    monkeypatch.setattr(
        driver.subprocess,
        "run",
        lambda cmd, **k: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    now = datetime(2026, 10, 14, 1, tzinfo=UTC)
    assert (
        driver.run_plans(
            tmp_path,
            date(2026, 10, 13),
            submit=False,
            execution_date=date(2026, 10, 14),
            now=now,
            accounts=("quant1",),
        )
        == 0
    )
    assert len(calls) == 1 and "submit" not in calls[0]
    assert (
        driver.run_plans(
            tmp_path,
            date(2026, 10, 13),
            submit=True,
            execution_date=date(2026, 10, 14),
            now=now,
            accounts=("quant1",),
        )
        == driver.EXIT_FRESH
    )
    assert len(calls) == 1


def test_early_close_and_holiday_completed_session():
    assert driver.latest_completed_us_equity_session(
        datetime(2026, 11, 27, 18, 1, tzinfo=UTC)
    ) == date(2026, 11, 27)
    assert driver.latest_completed_us_equity_session(
        datetime(2026, 11, 26, 23, tzinfo=UTC)
    ) == date(2026, 11, 25)
