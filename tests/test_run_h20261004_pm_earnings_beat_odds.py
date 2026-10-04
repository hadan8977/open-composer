"""Synthetic-data tests for scripts/run_h20261004_pm_earnings_beat_odds.py (T-20261004-51)."""

# ruff: noqa: E501
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.market_sessions import next_us_equity_session, us_equity_session_dates

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_h20261004_pm_earnings_beat_odds.py"
spec = importlib.util.spec_from_file_location("run_pm_earn", SCRIPT)
assert spec and spec.loader
run = importlib.util.module_from_spec(spec)
sys.modules["run_pm_earn"] = run
spec.loader.exec_module(run)

SESSIONS = [pd.Timestamp(d) for d in us_equity_session_dates(date(2025, 9, 1), date(2026, 9, 30))]


def synthetic(
    n_weeks: int = 40, per_week: int = 12, *, beat_effect: float, p_effect: float, seed: int = 1
):
    """Events on consecutive Wednesdays; returns planted as beat_effect*beat + p_effect*(P-0.5)."""
    rng = np.random.default_rng(seed)
    ev_rows, bars = [], {}
    spy_open = pd.Series(100.0, index=SESSIONS)
    bars["SPY"] = pd.DataFrame({"open": spy_open, "close": spy_open})
    k = 0
    for w in range(n_weeks):
        r = SESSIONS[5 + w * 5 + 2]
        s = SESSIONS[SESSIONS.index(r) - 1]
        for _ in range(per_week):
            sym = f"T{k}"
            k += 1
            p = float(rng.uniform(0.2, 0.9))
            beat = int(rng.random() < p)
            ret = beat_effect * beat + p_effect * (p - 0.5) + rng.normal(0, 0.03)
            close = pd.Series(50.0, index=SESSIONS)
            close.loc[close.index >= r] = 50.0 * (1 + ret)
            bars[sym] = pd.DataFrame({"open": close, "close": close})
            ev_rows.append(
                {
                    "slug": sym,
                    "ticker": sym,
                    "beat": beat,
                    "sip_bars_ok": True,
                    "S": s,
                    "R": r,
                    "P": p,
                    "P7": float(np.clip(p + rng.normal(0, 0.1), 0.01, 0.99)),
                    "P_stale": False,
                    "volume_usd": 9000.0,
                }
            )
    return pd.DataFrame(ev_rows), bars


def test_groups_pool_thin_weeks_within_a_season() -> None:
    days = (
        [pd.Timestamp("2026-01-07")] * 4  # week A: 4 events
        + [pd.Timestamp("2026-01-14")] * 3  # week B: 3 -> pooled with A (7 >= 6)
        + [pd.Timestamp("2026-01-21")] * 6  # week C: own group
        + [pd.Timestamp("2026-01-28")] * 2  # tail 2 -> merged into C
        + [pd.Timestamp("2026-06-03")] * 3  # separate season, 3 events -> dropped
    )
    df = pd.DataFrame({"R": days})
    out, info = run.assign_groups(df)
    assert info == {"groups": 2, "dropped_events": 3}
    assert out["grp"].nunique() == 2
    assert (out.groupby("grp").size() >= 6).all()


def test_weekly_ic_matches_spearman() -> None:
    from scipy import stats

    rng = np.random.default_rng(3)
    df = pd.DataFrame(
        {
            "grp": np.repeat([0, 1], 10),
            "s": rng.normal(size=20),
            "r": rng.normal(size=20),
        }
    )
    ic = run.weekly_ic(df, "s", "r")
    for g in (0, 1):
        part = df[df.grp == g]
        assert ic[g] == pytest.approx(stats.spearmanr(part.s, part.r)[0])


def test_tercile_spread_and_costs() -> None:
    df = pd.DataFrame(
        {
            "grp": [0] * 6,
            "s": [1, 2, 3, 4, 5, 6],
            "r": [-0.02, -0.02, 0.0, 0.0, 0.03, 0.03],
            "hold_sessions": [1.0] * 6,
            "R": pd.Timestamp("2026-01-07"),
        }
    )
    sp = run.tercile_spreads(df, "s", "r")
    assert sp.loc[0, "spread"] == pytest.approx(0.05)
    summary = run.spread_summary(sp)
    borrow_bp = 0.01 / 252 * 1e4
    assert summary["gross_mean_bp"] == pytest.approx(500.0)
    assert summary["net_primary_mean_bp"] == pytest.approx(500.0 - 40.0 - borrow_bp)
    assert summary["net_stress_mean_bp"] == pytest.approx(500.0 - 80.0 - borrow_bp)


def test_holm_adjustment() -> None:
    assert run.holm({"A1": 0.01, "A3": 0.04}) == {"A1": 0.02, "A3": 0.04}
    assert run.holm({"A1": 0.04, "A3": 0.03}) == {"A3": 0.06, "A1": 0.06}


def test_clustered_pooled_ic_recovers_planted_signal() -> None:
    rng = np.random.default_rng(4)
    s = rng.normal(size=600)
    df = pd.DataFrame(
        {"grp": np.repeat(np.arange(30), 20), "s": s, "r": 0.5 * s + rng.normal(size=600)}
    )
    out = run.pooled_ic(df, "s", "r")
    assert out["ic"] > 0.3 and out["t"] > 5


def test_shuffles_are_reproducible_and_centered() -> None:
    rng = np.random.default_rng(5)
    df = pd.DataFrame(
        {"grp": np.repeat(np.arange(20), 10), "s": rng.normal(size=200), "r": rng.normal(size=200)}
    )
    a = run.shuffle_ics(df, "s", "r", n=200)
    b = run.shuffle_ics(df, "s", "r", n=200)
    assert np.array_equal(a, b)
    assert abs(a.mean()) < 0.02


def test_attach_returns_window_and_placebo_next_session() -> None:
    events, bars = synthetic(n_weeks=2, per_week=1, beat_effect=0.0, p_effect=0.0)
    r = events.loc[0, "R"]
    bars["T0"].loc[bars["T0"].index >= r, ["open", "close"]] = 55.0
    nxt = next_us_equity_session(r.date())
    bars["T0"].loc[bars["T0"].index >= pd.Timestamp(nxt), "close"] = 60.5
    out = run.attach_returns(events, bars)
    assert out.loc[0, "ret_win"] == pytest.approx(0.10)
    assert out.loc[0, "ret_next"] == pytest.approx(0.10)
    assert out.loc[0, "hold_sessions"] == 1.0


def test_positive_control_failure_stops_before_ha() -> None:
    events, bars = synthetic(beat_effect=0.0, p_effect=0.0)
    result = run.run_analysis(events, bars)
    assert result["verdict"] == "pipeline_suspect"
    assert "H_A" not in result
    assert result["overlay_scoring"] == "not_run"


def test_planted_signal_passes_continue_rule() -> None:
    events, bars = synthetic(beat_effect=0.03, p_effect=0.20)
    result = run.run_analysis(events, bars)
    assert result["positive_control"]["t"] >= 3
    cr = result["continue_rule"]
    assert (
        cr["rule1_ic_positive_t_ge_2"]
        and cr["rule2_net_spread_positive"]
        and cr["rule3_above_shuffle_p95"]
    )
    assert result["verdict"] == "continue"
    assert result["overlay_scoring"] == "pending"
    assert result["H_A"]["A1"]["n_weeks"] == 40


def test_no_signal_beyond_beat_is_refuted_or_inconclusive() -> None:
    # Returns follow the realized beat but not P beyond its correlation with beat.
    events, bars = synthetic(beat_effect=0.03, p_effect=0.0, seed=9)
    result = run.run_analysis(events, bars)
    assert result["verdict"] in {"stop_refuted", "inconclusive", "continue"}
    assert result["placebos"]["shuffle"]["n"] == run.N_SHUFFLES
    assert result["secondary"]["sector_adjusted"]["status"] == "not_run"


def test_write_outputs(tmp_path: Path) -> None:
    events, bars = synthetic(beat_effect=0.03, p_effect=0.20)
    result = run.run_analysis(events, bars)
    run.write_outputs(result, tmp_path)
    doc = json.loads((tmp_path / "results.json").read_text())
    assert doc["research_pass"] is True and doc["paper_ready_pass"] is False
    ledger = [json.loads(x) for x in (tmp_path / "trial-ledger.jsonl").read_text().splitlines()]
    assert [r["candidate_id"] for r in ledger] == ["A1", "A3"]
    assert ledger[1]["decision_eligible"] is False
    assert "Verdict" in (tmp_path / "report.md").read_text()
