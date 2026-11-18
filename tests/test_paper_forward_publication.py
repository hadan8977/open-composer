"""Regressions for delayed paper equity and truthful snapshot publication."""
from datetime import UTC, date, datetime
from decimal import Decimal
import json
import sys
import types

import pytest

from open_composer.reports.paper_equity import account_equity_points, snapshot_session
from scripts.extend_paper_projection_forward import extend_account
from scripts.publish_paper_forward_projection import equity_by_day, stamp_by_day


def capture(at="2026-11-10T06:47:02+00:00", equity="102856.37"):
    return {
        "captured_at": at,
        "account": {"equity": equity},
        "portfolio_history": {
            "timestamp": [1793926800, 1794013200, 1794272400],
            "equity": [101907.52, 102012.74, 0.0],
        },
    }


@pytest.mark.parametrize("at,expected", [
    ("2026-11-09T21:00:00+00:00", date(2026, 11, 9)),
    ("2026-11-10T06:47:02+00:00", date(2026, 11, 9)),
    ("2026-11-10T09:00:00+00:00", None),
    ("2026-11-10T19:00:00+00:00", None),
    ("2026-11-10T21:00:00+00:00", date(2026, 11, 10)),
    ("2026-11-27T18:00:00+00:00", date(2026, 11, 27)),
    ("2026-11-28T17:00:00+00:00", date(2026, 11, 27)),
    ("2026-11-02T08:59:59+00:00", date(2026, 10, 30)),
    ("2026-11-02T09:00:00+00:00", None),
])
def test_snapshot_window_accounts_for_close_early_close_dst_and_weekend(at, expected):
    assert snapshot_session(datetime.fromisoformat(at)) == expected


def test_delayed_daily_equity_keeps_dates_and_actual_snapshot_stamp():
    receipt = capture()
    days = [date(2026, 11, 6), date(2026, 11, 9)]
    points = extend_account({}, receipt, days)
    assert [p["equity_usd"] for p in points] == [102012.74, 102856.37]
    assert points[-1]["valuation"] == "broker_account_snapshot_after_close"
    assert points[-1]["at"] == receipt["captured_at"]
    assert equity_by_day(receipt)["2026-11-09"] == Decimal("102856.37")
    assert stamp_by_day(receipt)["2026-11-09"] == receipt["captured_at"]


def test_mid_session_equity_cannot_fill_prior_close_gap():
    receipt = capture("2026-11-10T19:00:00+00:00")
    point = extend_account({}, receipt, [date(2026, 11, 9)])[0]
    assert point["equity_usd"] is None and point["missing"]
    assert "2026-11-09" not in equity_by_day(receipt)


def test_posted_daily_equity_wins_over_live_and_current_session_is_not_final():
    receipt = capture("2026-11-10T19:00:00+00:00")
    receipt["portfolio_history"]["equity"][-1] = 102800
    receipt["portfolio_history"]["timestamp"].append(1794358800)
    receipt["portfolio_history"]["equity"].append(103000)
    result = account_equity_points(receipt)
    assert result[date(2026, 11, 9)]["equity_usd"] == Decimal("102800")
    assert result[date(2026, 11, 9)]["source"] == "alpaca_portfolio_history_1D"
    assert date(2026, 11, 10) not in result


@pytest.mark.parametrize("value", ["0", "NaN", "Infinity", "100"])
def test_placeholder_live_values_remain_gaps(value):
    assert date(2026, 11, 9) not in account_equity_points(capture(equity=value))


def test_failed_extension_cannot_publish_stale_history(tmp_path, monkeypatch):
    from scripts import publish_paper_dashboard_daily as daily

    monkeypatch.setattr(daily, "ROOT", tmp_path)
    monkeypatch.setattr(daily, "LOG", tmp_path / "publish.jsonl")
    sealed = tmp_path / "sealed.json"
    sealed.write_text(json.dumps({"histories": []}))
    monkeypatch.setattr(daily, "SEALED_HISTORY", sealed)
    calls = []
    notices = []
    monkeypatch.setitem(sys.modules, "paper_watchdog", types.SimpleNamespace(
        notify=lambda *args, **kwargs: notices.append(args)))

    def run(step, command):
        calls.append(step)
        if step == "capture":
            from pathlib import Path
            out = Path(command[command.index("--out") + 1])
            for alias in ("legacy", "quant1", "six"):
                (out / f"account-{alias}.json").write_text(json.dumps(capture()))
        return dict(step=step, exit_code=1 if step == "extend" else 0,
                    stderr_tail="saved failure", stdout_tail="")

    monkeypatch.setattr(daily, "run", run)
    monkeypatch.setattr(sys, "argv", ["publish", "--day", "2026-11-09"])
    assert daily.main() == 2
    assert calls == ["capture", "extend"]
    assert len(notices) == 1
    assert json.loads(daily.LOG.read_text())["ok"] is False
