import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from open_composer.lab.adapters import screen_engine, screen_modules

ROOT = Path(__file__).resolve().parents[1]


def test_screen_adapter_preserves_frozen_source_costs_windows_and_returns(tmp_path, monkeypatch):
    batch, lane = screen_modules(ROOT)
    index = pd.bdate_range("2015-01-02", "2026-09-17")
    position = np.arange(len(index))
    symbols = sorted(set(lane.salvage.symbols()) | {lane.CASH, lane.RF, "AAA"})
    close = pd.DataFrame(
        {
            symbol: 100
            * np.exp(
                position * (0.0001 + j * 0.00001) + np.sin(position * (0.07 + j * 0.005)) * 0.04
            )
            for j, symbol in enumerate(symbols)
        },
        index=index,
    )
    open_ = close.shift(1).fillna(close.iloc[0])
    leg_open, leg_close = lane.salvage.legs(close, open_)
    candidate = lane.ScreenCandidate(
        id="fixture_screen",
        name="Synthetic screen adapter",
        source_card="fixture",
        universe=("AAA",),
        freq="D",
        weights_fn=lambda frame, date: {"AAA": 0.5},
    )
    rf = close[lane.RF].pct_change(fill_method=None).fillna(0.0)
    panel = {
        "close": close,
        "leg_open": leg_open,
        "leg_close": leg_close,
        "rf": rf,
        "shy_ret": close[lane.CASH].pct_change(fill_method=None).fillna(0),
        "s3_ret10": close[lane.CASH].pct_change(fill_method=None).fillna(0),
    }
    native = lane.evaluate_candidate(candidate, **panel, n_trials=9)
    adapted = screen_engine(ROOT, candidate, panel=panel, n_trials=9, initial_equity_usd=10_000)
    offset = native["judged"]["anchor"]["offset"]
    start = native["per_window"]["anchor"]["actual_start"]
    expected = native["_returns_net10_by_offset"][offset].loc[start : lane.WINDOWS["anchor"][1]]
    pd.testing.assert_series_equal(adapted.net_returns, expected)
    assert adapted.end_equity_usd == pytest.approx(10_000 * (1 + expected).prod())
    assert adapted.native["dsr_anchor"] == native["dsr_anchor"]
    assert adapted.metadata["windows"] == lane.WINDOWS
    assert adapted.metadata["contaminated_windows"] == ["holdout"]
    assert adapted.metadata["cost_bps_primary"] == 10
    assert adapted.metadata["cost_bps_stress"] == 20
    turnover = adapted.ledger[f"turnover_offset_{offset}"]
    pd.testing.assert_series_equal(
        adapted.ledger[f"cost10_offset_{offset}"],
        turnover * 10 / 10_000,
        check_names=False,
    )
    np.testing.assert_allclose(
        adapted.ledger[f"net10_offset_{offset}"] - adapted.ledger[f"net20_offset_{offset}"],
        turnover * 10 / 10_000,
        atol=1e-15,
    )

    # Exercise the real CLI path: prior exposure + failed candidate must affect
    # final DSR, while the earlier source statistic remains labeled separately.
    from open_composer.lab.screening import run_screen_batch
    from open_composer.research.agent_workflow import validate_results
    from open_composer.research.campaign_statistics import deflated_sharpe_probability

    missing = lane.ScreenCandidate(
        "missing", "Missing input", "fixture", ("ABSENT",), "D", lambda frame, date: {"ABSENT": 1.0}
    )
    monkeypatch.setattr(
        batch, "load_batch_module", lambda name: SimpleNamespace(CANDIDATES=[candidate, missing])
    )
    monkeypatch.setattr(
        lane, "load_batch_panel", lambda *args: (close, open_, leg_open, leg_close, rf)
    )
    iterations = tmp_path / "iterations"
    (iterations / "accepted").mkdir(parents=True)
    (iterations / "accepted/candidate-manifest.json").write_text(
        json.dumps({"candidates": [{"candidate_id": candidate.id}, {"candidate_id": missing.id}]})
    )
    monkeypatch.setattr(batch, "ITERATIONS_DIR", iterations)
    (tmp_path / "control.json").write_text('{"draft":false,"research":true}')
    legacy = tmp_path / "reports/research/screens/fixture/leaderboard.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"n_trials":5}')
    folder = run_screen_batch(
        tmp_path, "fixture", iteration="accepted", direction="screen_fixture", batch_id="first"
    )
    manifest = json.loads((folder / "batch.json").read_text())
    assert manifest["n_trials"] == 7
    assert set(manifest["failures"]) == {"missing"}
    assert manifest["counts"]["variants"] == 2
    result = validate_results(tmp_path, manifest["results"][candidate.id], "screen_fixture")
    assert result.n_trials == 7
    expected_dsr = deflated_sharpe_probability(
        (adapted.net_returns - rf.loc[adapted.net_returns.index]).to_numpy(),
        trial_count=7,
        hac_lag=lane.DSR_HAC_LAG,
    )
    assert result.dsr == pytest.approx(expected_dsr)
    row = json.loads((folder / "leaderboard.json").read_text())["candidates"][0]
    assert row["source_n_trials"] == 6
    assert row["n_trials"] == 7
    assert row["dsr_anchor"] == pytest.approx(expected_dsr)
    assert json.loads(legacy.read_text())["n_trials"] == 5
