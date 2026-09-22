"""Minimal per-primitive samples for the giants-sweep spec interpreter.

Scope is deliberately small: one hand-checkable example per primitive plus the
frozen next-open fill convention. The economic acceptance evidence lives in
reports/research/iterations/giants_sweep_20260922/, not here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

engine = pytest.importorskip("run_giants_sweep")


@pytest.fixture(scope="module")
def panel() -> engine.Panel:
    index = pd.bdate_range("2020-01-01", periods=420)
    n = len(index)
    ramp = np.linspace(100.0, 300.0, n)
    fall = np.linspace(300.0, 100.0, n)
    flat = np.full(n, 50.0)
    close = pd.DataFrame(
        {"UP": ramp, "DOWN": fall, "CASH": flat, "BOND": flat * 1.0},
        index=index,
    )
    # a 1% overnight gap on every session, the rest of the move intraday
    open_ = close.shift(1).fillna(close.iloc[0]) * 1.01
    return engine.Panel(close, open_, "CASH")


def book(panel, node, i: int, **kwargs) -> dict[str, float]:
    return engine.Interpreter(panel, **kwargs).book(node, i)


def test_asset_and_weights_nodes(panel):
    assert book(panel, {"asset": "UP"}, 400) == {"UP": 1.0}
    assert book(panel, {"weights": {"UP": 0.7, "BOND": 0.3}}, 400) == {"UP": 0.7, "BOND": 0.3}


def test_blend_node_splits_between_legs(panel):
    node = {
        "blend": [
            {"weight": 0.6, "node": {"asset": "UP"}},
            {"weight": 0.4, "node": {"asset": "BOND"}},
        ]
    }
    assert book(panel, node, 400) == pytest.approx({"UP": 0.6, "BOND": 0.4})


def test_sma_gate_picks_the_branch_matching_the_trend(panel):
    node = {
        "gate": {
            "type": "sma",
            "asset": "UP",
            "window": 200,
            "op": "above",
            "on_true": {"asset": "UP"},
            "on_false": {"asset": "CASH"},
        }
    }
    assert book(panel, node, 400) == {"UP": 1.0}
    node["gate"]["asset"] = "DOWN"
    assert book(panel, node, 400) == {"CASH": 1.0}


def test_rsi_gate_fires_on_a_pure_uptrend(panel):
    node = {
        "gate": {
            "type": "rsi",
            "asset": "UP",
            "window": 10,
            "threshold": 80,
            "op": "above",
            "on_true": {"asset": "CASH"},
            "on_false": {"asset": "UP"},
        }
    }
    assert book(panel, node, 400) == {"CASH": 1.0}


def test_rank_renormalizes_by_default_and_parks_when_asked(panel):
    menu = ["UP", "DOWN"]
    renorm = {"rank": {"menu": menu, "lookback": 21, "top_n": 2, "cash_filter": "CASH"}}
    assert book(panel, renorm, 400) == {"UP": 1.0}
    park = dict(renorm["rank"], cash_policy="park")
    assert book(panel, {"rank": park}, 400) == pytest.approx({"UP": 0.5, "CASH": 0.5})


def test_canary_switches_the_whole_book(panel):
    node = {
        "canary": {
            "assets": ["UP"],
            "method": "m13612w",
            "on_ok": {"asset": "UP"},
            "on_fail": {"asset": "BOND"},
        }
    }
    assert book(panel, node, 400) == {"UP": 1.0}
    node["canary"]["assets"] = ["DOWN"]
    assert book(panel, node, 400) == {"BOND": 1.0}


def test_trend_basket_sends_only_the_broken_sleeve_to_cash(panel):
    node = {
        "trend_basket": {
            "menu": ["UP", "DOWN"],
            "method": "sma",
            "window": 200,
            "cash_asset": "BOND",
        }
    }
    assert book(panel, node, 400) == pytest.approx({"UP": 0.5, "BOND": 0.5})


def test_accelerating_dual_momentum_applies_substitutions(panel):
    node = {
        "accel_dual_momentum": {
            "risk_assets": ["DOWN"],
            "defensive": ["BOND"],
            "lookbacks": [21, 63, 126],
            "defensive_lookback": 21,
            "substitutions": {"BOND": "CASH"},
        }
    }
    assert book(panel, node, 400) == {"CASH": 1.0}


def test_calendar_shift_reads_an_older_signal(panel):
    node = {
        "gate": {
            "type": "sma",
            "asset": "UP",
            "window": 200,
            "op": "above",
            "on_true": {"asset": "UP"},
            "on_false": {"asset": "CASH"},
        }
    }
    # index 210 is just past the first 200-session window, so a 20-session shift
    # lands before the moving average exists and the false branch must win
    assert book(panel, node, 210) == {"UP": 1.0}
    assert book(panel, node, 210, shift=20) == {"CASH": 1.0}


def test_random_pick_placebo_ignores_the_ranking(panel):
    node = {"rank": {"menu": ["UP", "DOWN"], "lookback": 21, "top_n": 1}}
    picks = {
        next(iter(book(panel, node, 400, pick_rng=np.random.default_rng(seed))))
        for seed in range(30)
    }
    assert picks == {"UP", "DOWN"}


def test_signal_dates_respect_the_rebalance_cadence(panel):
    daily = engine.signal_positions(panel.index, "daily")
    monthly = engine.signal_positions(panel.index, "monthly")
    bimonthly = engine.signal_positions(panel.index, "bimonthly")
    quarterly = engine.signal_positions(panel.index, "quarterly")
    assert len(daily) == panel.n
    assert len(monthly) == 20
    assert bimonthly == monthly[::2]
    assert len(quarterly) == 7


def test_book_is_effective_at_the_next_open_not_the_signal_close(panel):
    spec = {"rebalance": "daily", "root": {"asset": "UP"}}
    ret, turns = engine.simulate_book(panel, spec, 0.0)
    # the book starts in cash and only moves after the first signal close
    assert turns.iloc[0] == 0.0
    assert turns.iloc[1] == pytest.approx(2.0)
    ci = panel.col_i["CASH"]
    cash_day0 = float(panel.leg_open[0][ci] + panel.leg_close[0][ci])
    assert ret.iloc[0] == pytest.approx(cash_day0)


def test_costs_are_charged_on_the_execution_session(panel):
    spec = {"rebalance": "daily", "root": {"asset": "UP"}}
    free, _ = engine.simulate_book(panel, spec, 0.0)
    charged, turns = engine.simulate_book(panel, spec, 10.0)
    assert (free - charged).iloc[1] == pytest.approx(turns.iloc[1] * 10.0 / 10_000.0)


def test_fixed_weights_drift_between_rebalances(panel):
    spec = {"rebalance": "quarterly", "root": {"weights": {"UP": 0.5, "BOND": 0.5}}}
    _, turns = engine.simulate_book(panel, spec, 0.0, drift=True)
    # a drifting book only trades on its own rebalance dates
    assert int((turns > 0).sum()) <= len(engine.signal_positions(panel.index, "quarterly")) + 1


def test_overnight_only_earns_the_gap_and_pays_two_sides(panel):
    spec = {"overnight": {"asset": "UP", "skip_weekdays": []}}
    ret, turns, hold = engine.simulate_overnight(panel, spec, 0.0)
    assert bool(hold[1]) and not bool(hold[0])
    assert ret.iloc[1] == pytest.approx(float(panel.leg_open[1][panel.col_i["UP"]]))
    assert turns.iloc[1] == pytest.approx(2.0)
    charged, _, _ = engine.simulate_overnight(panel, spec, 10.0)
    assert (ret - charged).iloc[1] == pytest.approx(2.0 * 10.0 / 10_000.0)


def test_overnight_skip_weekdays_drops_those_nights(panel):
    spec = {"overnight": {"asset": "UP", "skip_weekdays": [2, 4]}}
    _, _, hold = engine.simulate_overnight(panel, spec, 0.0)
    weekday = panel.index.weekday.to_numpy()
    for i in range(1, panel.n):
        assert bool(hold[i]) == (int(weekday[i - 1]) not in {2, 4})


def test_unknown_primitive_is_refused(panel):
    with pytest.raises(ValueError, match="unknown spec primitive"):
        book(panel, {"teleport": {}}, 400)


def test_manifest_is_loadable_and_every_primitive_is_implemented():
    manifest = engine.load_manifest()
    assert manifest["iter_id"] == "giants_sweep_20260922"
    assert len(manifest["candidates"]) == 24
    assert {c["id"] for c in manifest["candidates"]}.__len__() == 24
    known = {name[len("_node_") :] for name in dir(engine.Interpreter) if name.startswith("_node_")}
    known |= {"signal_growth", "overnight", "rebalance", "root"}
    for candidate in manifest["candidates"]:
        spec = candidate["spec"]
        assert set(spec) <= known, candidate["id"]
