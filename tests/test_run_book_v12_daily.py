from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_book_v12_daily as driver  # noqa: E402


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
