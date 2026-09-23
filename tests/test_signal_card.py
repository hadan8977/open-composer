from __future__ import annotations

import numpy as np
import pandas as pd

from open_composer.research import signal_card as sc


def _market(T: int = 320, N: int = 90, seed: int = 0) -> sc.Market:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0005, 0.02, size=(T, N))
    open_ = (100 * np.cumprod(1 + rets, axis=0)).astype(np.float32)
    close = (open_ * (1 + rng.normal(0, 0.005, size=(T, N)))).astype(np.float32)
    rank = np.tile(np.arange(1, N + 1, dtype=np.float32), (T, 1))
    dates = pd.bdate_range("2023-01-02", periods=T)
    return sc.Market(dates, pd.Index([f"S{i}" for i in range(N)]), open_, close, rank)


def test_forward_returns_enter_next_open() -> None:
    m = _market(T=10, N=3)
    f = m.forward_returns(2)
    assert np.isclose(f[0, 1], m.open_[3, 1] / m.open_[1, 1] - 1)
    assert np.isnan(f[-3:]).all()
    r = m.next_open_returns()
    assert np.isclose(r[4, 2], m.open_[5, 2] / m.open_[4, 2] - 1)


def test_hold_averages_cohorts_and_calendar_time_normalizes() -> None:
    c = np.zeros((6, 2), dtype=np.float32)
    c[0, 0] = 1.0
    c[1, 1] = 1.0
    held = sc.hold(c, 2)
    assert np.allclose(held[:, 0], [0, 0.5, 0.5, 0, 0, 0])
    assert np.allclose(held[:, 1], [0, 0, 0.5, 0.5, 0, 0])
    cal = sc.hold(c, 2, normalize=True)
    assert np.allclose(cal[2], [0.5, 0.5])
    assert np.allclose(cal[1], [1.0, 0.0])


def test_rank_card_finds_a_leaked_signal_and_not_noise() -> None:
    m = _market()
    rng = np.random.default_rng(1)
    leak = m.forward_returns(5) + rng.normal(0, 0.02, m.open_.shape).astype(np.float32)
    card = sc.rank_card(m, leak, top_k=10, primary=5, seeds=2)
    assert card["ic"]["h5"]["mean"] > 0.3
    assert card["flags"]["predictive"] and card["flags"]["beats_shuffle"]
    assert card["book"]["all"]["h5"]["10bp"]["excess_ann"] > 0
    noise = rng.normal(size=m.open_.shape).astype(np.float32)
    quiet = sc.rank_card(m, noise, top_k=10, primary=5, seeds=2)
    assert abs(quiet["ic"]["h5"]["mean"]) < 0.05
    assert not quiet["flags"]["predictive"]


def test_event_card_sees_planted_drift_and_placebo_does_not() -> None:
    m = _market(T=400, N=80, seed=3)
    rng = np.random.default_rng(4)
    sig = np.full(m.open_.shape, np.nan, dtype=np.float32)
    rows = rng.integers(130, 330, 150)
    cols = rng.integers(0, 80, 150)
    for t, n in zip(rows, cols, strict=True):
        sig[t, n] = 1.0
        m.open_[t + 2 :, n] *= 1.04  # +4% between the entry open and 20 sessions later
    card = sc.event_card(m, sig, primary=20, seeds=3)
    assert card["car"]["h20"]["mean"] > 0.02
    assert card["flags"]["beats_redated"]
    moved = [p["car"] for p in card["placebo"]["redated"]]
    assert max(moved) < card["car"]["h20"]["mean"]


def test_render_and_write_round_trip(tmp_path) -> None:
    m = _market(T=200, N=60)
    sig = np.random.default_rng(2).normal(size=m.open_.shape).astype(np.float32)
    card = sc.rank_card(m, sig, top_k=10, primary=5, seeds=1)
    card = {
        "meta": {
            "name": "noise",
            "mode": "rank",
            "source": "synthetic",
            "lag": 0,
            "direction": 1,
            "threshold": None,
            "top_n": 60,
            "top_k": 10,
            "primary_horizon": 5,
            "generated_at": "2026-09-23T00:00:00+00:00",
        },
        **card,
    }
    js, md = sc.write_card(card, tmp_path)
    assert js.exists() and "Signal card: noise" in md.read_text()
    assert (tmp_path / "index.jsonl").read_text().count('"noise"') == 1


def test_row_ranks_match_pandas_with_ties_and_gaps() -> None:
    rng = np.random.default_rng(5)
    x = rng.integers(0, 6, size=(40, 25)).astype(np.float32)
    x[rng.random(x.shape) < 0.3] = np.nan
    got = sc._row_ranks(x, chunk=7)
    want = pd.DataFrame(x).rank(axis=1).to_numpy(np.float32)
    assert np.allclose(got, want, equal_nan=True)


def test_admission_and_summary_follow_the_manifest(tmp_path) -> None:
    import json

    m = _market()
    leak = m.forward_returns(5) + np.random.default_rng(1).normal(0, 0.02, m.open_.shape).astype(
        np.float32
    )
    card = sc.rank_card(m, leak, top_k=10, primary=5, seeds=2)
    card = {
        "meta": {"name": "leak", "mode": "rank", "source": "synthetic", "lag": 0, "direction": 1}
        | {"threshold": None, "top_n": 90, "top_k": 10, "primary_horizon": 5}
        | {"generated_at": "2026-09-23T00:00:00+00:00"},
        **card,
    }
    sc.write_card(card, tmp_path)
    assert sc.admission(card) in {"admit", "reject"}
    manifest = tmp_path / "lib-manifest.json"
    manifest.write_text(
        json.dumps({"library": "lib", "signals": [{"name": "leak"}, {"name": "x"}]})
    )
    text = sc.library_summary(manifest, tmp_path)
    assert "| leak | rank | 5d |" in text and "not run" in text
    assert (tmp_path / "lib-summary.md").exists()


def test_composite_averages_directional_percentile_ranks(monkeypatch) -> None:
    m = _market(T=60, N=40)
    a = np.tile(np.arange(40, dtype=np.float32), (60, 1))
    b = -a  # opposite ordering

    def fake_load(market, **kw):
        return a if kw["column"] == "a" else b

    monkeypatch.setattr(sc, "load_signal", fake_load)
    same = sc.composite_signal(m, [{"column": "a"}, {"column": "b", "direction": -1}])
    assert np.allclose(same[0], sc.percentile_ranks(a, m.member())[0])
    flat = sc.composite_signal(m, [{"column": "a"}, {"column": "b"}])
    assert np.allclose(flat[0], flat[0][0])  # opposite signals cancel to a constant
