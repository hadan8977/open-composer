"""Fake-HTTP and fake-bars tests for scripts/pm_midterm_shadow.py (T-20261004-53)."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pm_midterm_shadow.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("pm_midterm_shadow", SCRIPT)
assert spec and spec.loader
sh = importlib.util.module_from_spec(spec)
sys.modules["pm_midterm_shadow"] = sh
spec.loader.exec_module(sh)
bd, rn = sh.bd, sh.rn

# 2026-10-05 is a Monday; EDT: 15:50 ET = 19:50 UTC, 15:30 ET = 19:30 UTC
IN_WINDOW = datetime(2026, 10, 5, 19, 50, tzinfo=UTC)


class FakeHttp:
    def __init__(self, prices: dict[str, float] | None = None, *, empty: bool = False):
        self.prices = prices or {bd.POLY_HOUSE_R_TOKEN: 0.40, bd.POLY_SENATE_R_TOKEN: 0.60}
        self.empty = empty
        self.calls: list[dict] = []

    def get(self, url, params=None, *, allow_404=False):
        params = params or {}
        self.calls.append(dict(params))
        if self.empty:
            return {"history": []}
        end = params["endTs"]
        return {"history": [{"t": end - 120, "p": self.prices[params["market"]]}]}


def make_daily(tmp_path: Path) -> Path:
    sessions = bd.sessions_between(date(2025, 7, 14), date(2026, 10, 2))
    rng = np.random.default_rng(11)
    rows = []
    for name in ("polymarket_house_r", "polymarket_senate_r"):
        px = np.clip(0.4 + np.cumsum(rng.normal(0, 0.01, len(sessions))), 0.05, 0.95)
        rows.append(
            pd.DataFrame({"series": name, "session": pd.DatetimeIndex(sessions), "price": px})
        )
    path = tmp_path / "daily.parquet"
    pd.concat(rows, ignore_index=True).to_parquet(path, index=False)
    return path


def lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines()]


def test_window_guard_blocks_without_network_or_writes(tmp_path) -> None:
    http = FakeHttp()
    for now in (
        datetime(2026, 10, 5, 19, 30, tzinfo=UTC),  # 15:30 ET, too early
        datetime(2026, 10, 5, 19, 55, tzinfo=UTC),  # 15:55 ET, window is half-open
        datetime(2026, 10, 3, 19, 50, tzinfo=UTC),  # Saturday
        datetime(2026, 10, 2, 19, 50, tzinfo=UTC),  # before the forward window
        datetime(2026, 11, 5, 20, 50, tzinfo=UTC),  # after the window (EST 15:50)
    ):
        out = sh.run_signal(
            now, http, tmp_path, daily_path=make_daily(tmp_path), log=lambda *_: None
        )
        assert out["written"] == 0
    assert http.calls == [] and not (tmp_path / "signals.jsonl").exists()


def test_window_follows_dst() -> None:
    ok_edt, _, _ = sh.window_status(datetime(2026, 10, 30, 19, 45, tzinfo=UTC))
    ok_est, _, _ = sh.window_status(datetime(2026, 11, 2, 20, 45, tzinfo=UTC))
    wrong_edt, _, _ = sh.window_status(datetime(2026, 10, 30, 20, 45, tzinfo=UTC))
    assert ok_edt and ok_est and not wrong_edt


def test_signal_matches_the_backtest_pipeline_and_is_idempotent(tmp_path) -> None:
    daily_path = make_daily(tmp_path)
    http = FakeHttp()
    out = sh.run_signal(IN_WINDOW, http, tmp_path, daily_path=daily_path, log=lambda *_: None)
    assert out["written"] == 1
    row = lines(tmp_path / "signals.jsonl")[0]
    # independent computation with the run script's functions
    panel = sh.base_panel(daily_path)
    panel.loc[pd.Timestamp("2026-10-05")] = [0.40, 0.60]
    expected = rn.transform(rn.delta_p(panel)).iloc[-1]
    assert row["session"] == "2026-10-05" and row["return_session"] == "2026-10-06"
    assert abs(row["signal"] - expected) < 1e-12
    assert row["late_backfill"] is False and row["price_house"] == 0.40
    pos = row["positions"]
    assert set(pos) == set(bd.ASSETS) and len(pos) == 27
    assert pos["SPY"] == pytest.approx(row["signal"]) and pos["TLT"] == pytest.approx(
        -row["signal"]
    )
    # run time minus 120 s is the price timestamp used (the fake returns end-120)
    assert row["price_ts_house"] == int(IN_WINDOW.timestamp()) - 120
    again = sh.run_signal(IN_WINDOW, http, tmp_path, daily_path=daily_path, log=lambda *_: None)
    assert again["written"] == 0 and len(lines(tmp_path / "signals.jsonl")) == 1


def test_dry_run_writes_nothing(tmp_path) -> None:
    out = sh.run_signal(
        IN_WINDOW,
        FakeHttp(),
        tmp_path,
        daily_path=make_daily(tmp_path),
        dry_run=True,
        log=lambda *_: None,
    )
    assert out["written"] == 0 and len(out["rows"]) == 1
    assert not (tmp_path / "signals.jsonl").exists()


def test_missed_sessions_are_backfilled_and_flagged(tmp_path) -> None:
    daily_path = make_daily(tmp_path)
    http = FakeHttp()
    sh.run_signal(IN_WINDOW, http, tmp_path, daily_path=daily_path, log=lambda *_: None)
    later = datetime(2026, 10, 8, 19, 50, tzinfo=UTC)  # Thursday; 10-06 and 10-07 missed
    out = sh.run_signal(later, http, tmp_path, daily_path=daily_path, log=lambda *_: None)
    assert out["written"] == 3
    rows = lines(tmp_path / "signals.jsonl")
    assert [r["session"] for r in rows] == ["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"]
    assert [r["late_backfill"] for r in rows] == [False, True, True, False]
    # the backfill uses the true 16:00 cut, the live row uses run time
    assert rows[1]["price_ts_house"] == bd.cut_epoch(date(2026, 10, 6)) - 120


def test_no_price_means_failure_and_no_write(tmp_path) -> None:
    with pytest.raises(RuntimeError):
        sh.run_signal(
            IN_WINDOW,
            FakeHttp(empty=True),
            tmp_path,
            daily_path=make_daily(tmp_path),
            log=lambda *_: None,
        )
    assert not (tmp_path / "signals.jsonl").exists()


def fake_bars(rets: dict[str, float], days: list[str]) -> dict[str, pd.Series]:
    idx = pd.DatetimeIndex(days)
    return {t: pd.Series([100.0, 100.0 * (1 + rets.get(t, 0.0))], index=idx) for t in bd.ASSETS}


def test_realize_computes_basket_with_costs_and_is_idempotent(tmp_path) -> None:
    daily_path = make_daily(tmp_path)
    sh.run_signal(IN_WINDOW, FakeHttp(), tmp_path, daily_path=daily_path, log=lambda *_: None)
    sig = lines(tmp_path / "signals.jsonl")[0]["signal"]
    rets = {t: 0.01 for t in bd.ASSETS}
    bars = fake_bars(rets, ["2026-10-05", "2026-10-06"])
    out = sh.run_realize(bars, tmp_path, log=lambda *_: None)
    assert out["realized"] == 1
    row = lines(tmp_path / "realized.jsonl")[0]
    dirs = dict(zip(bd.ASSETS, rn.direction_vector(bd.ASSETS), strict=True))
    expected_gross = np.mean([sig * dirs[t] * 0.01 for t in bd.ASSETS])
    assert row["basket_gross"] == pytest.approx(expected_gross)
    costs = dict(zip(bd.ASSETS, rn.cost_vector(bd.ASSETS), strict=True))
    expected_cost = np.mean(
        [abs(sig * dirs[t]) * costs[t] / 1e4 for t in bd.ASSETS]
    )  # entry from zero
    assert row["turnover_cost"] == pytest.approx(expected_cost)
    assert row["basket_net"] == pytest.approx(expected_gross - expected_cost)
    assert sh.run_realize(bars, tmp_path, log=lambda *_: None)["realized"] == 0


def test_realize_skips_when_return_session_has_no_bars(tmp_path) -> None:
    sh.run_signal(
        IN_WINDOW, FakeHttp(), tmp_path, daily_path=make_daily(tmp_path), log=lambda *_: None
    )
    idx = pd.DatetimeIndex(["2026-10-05"])
    bars = {t: pd.Series([100.0], index=idx) for t in bd.ASSETS}
    out = sh.run_realize(bars, tmp_path, log=lambda *_: None)
    assert out["realized"] == 0 and out["skipped"][0][0] == "2026-10-05"
    assert not (tmp_path / "realized.jsonl").exists()


def test_summary_is_labelled_forward_only(tmp_path) -> None:
    s = sh.summarize(tmp_path)
    assert s["label"] == "forward_only_no_decision" and s["signals_logged"] == 0
    assert s["sessions_in_window"] == len(bd.sessions_between(date(2026, 10, 5), date(2026, 11, 4)))
    daily_path = make_daily(tmp_path)
    sh.run_signal(IN_WINDOW, FakeHttp(), tmp_path, daily_path=daily_path, log=lambda *_: None)
    sh.run_realize(
        fake_bars({t: 0.01 for t in bd.ASSETS}, ["2026-10-05", "2026-10-06"]),
        tmp_path,
        log=lambda *_: None,
    )
    s = sh.summarize(tmp_path)
    assert (
        s["signals_logged"] == 1
        and s["realized_sessions"] == 1
        and s["sharpe_net_annualized"] is None
    )
    assert "forward_only_no_decision" in sh.format_summary(s)
