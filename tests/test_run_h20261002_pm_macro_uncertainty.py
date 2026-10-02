"""Synthetic tests for the statistics in scripts/run_h20261002_pm_macro_uncertainty.py
(T-20261002-44). No market data and no Kalshi data are read."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "run_h20261002_pm_macro_uncertainty", SCRIPTS / "run_h20261002_pm_macro_uncertainty.py"
)
assert spec and spec.loader
run = importlib.util.module_from_spec(spec)
sys.modules["run_h20261002_pm_macro_uncertainty"] = run
spec.loader.exec_module(run)


def test_diff_bp_and_empty_group():
    frame = pd.DataFrame({"U_rel": [0.5, 0.9, 1.2, 2.0], "r": [0.001, 0.003, 0.004, 0.006]})
    assert run.diff_bp(frame, "r") == pytest.approx((0.005 - 0.002) * 1e4)
    assert math.isnan(run.diff_bp(frame[frame["U_rel"] > 1], "r"))


def test_welch_t_matches_formula():
    a, b = np.array([1.0, 2.0, 3.0, 4.0]), np.array([0.0, 1.0, 1.0, 2.0])
    out = run.welch_t(a, b)
    expected = (a.mean() - b.mean()) / math.sqrt(a.var(ddof=1) / 4 + b.var(ddof=1) / 4)
    assert out["t"] == pytest.approx(expected)
    assert out["n_a"] == 4 and out["n_b"] == 4


def test_hc1_slope_recovers_a_noiseless_line():
    x = np.linspace(-1, 1, 30)
    y = 0.002 + 0.01 * x + np.tile([1e-4, -1e-4], 15)
    out = run.hc1_slope(x, y)
    assert out["b"] == pytest.approx(0.01, abs=2e-4)
    assert out["t_hc1"] > 20


def test_binomial_tail():
    assert run.binom_p_one_sided(10, 10) == pytest.approx(1 / 1024)
    assert run.binom_p_one_sided(0, 5) == pytest.approx(1.0)
    assert run.binom_p_one_sided(5, 8) == pytest.approx(
        sum(math.comb(8, k) for k in (5, 6, 7, 8)) / 256
    )


def test_event_target_month_parses_old_and_new_tickers():
    assert run.event_target_month("KXCPI-26JUL") == "2026-7"
    assert run.event_target_month("CPI-23DEC") == "2023-12"
    assert run.event_target_month("KXPAYROLLS-26SEP") == "2026-9"
    assert run.event_target_month("GDP-21JUN30") is None


def _nowcast_json(path: Path) -> None:
    chart = lambda target, labels, vals: {  # noqa: E731
        "chart": {"subcaption": target},
        "categories": [{"category": [{"label": label} for label in labels]}],
        "dataset": [
            {"seriesname": "CPI Inflation", "data": [{"value": v} for v in vals]},
            {"seriesname": "Core CPI Inflation", "data": [{"value": "9"} for _ in vals]},
        ],
    }
    path.write_text(
        json.dumps(
            [
                chart(
                    "2022-12",
                    ["12/30", "12/31", "01/03", "PCE Dec", "01/12"],
                    ["0.1", "0.2", "", "", "0.3"],
                ),
                chart("2023-1", ["01/01", "01/02"], ["0.5", "0.6"]),
            ]
        )
    )


def test_cleveland_loader_rolls_the_year_and_skips_blanks(tmp_path):
    path = tmp_path / "n.json"
    _nowcast_json(path)
    nc = run.load_cleveland_nowcast(path)
    s = nc["2022-12"]
    assert list(s.index.strftime("%Y-%m-%d")) == ["2022-12-30", "2022-12-31", "2023-01-12"]
    assert list(s.to_numpy()) == [0.1, 0.2, 0.3]


def test_gap_table_uses_only_nowcasts_dated_before_the_release(tmp_path):
    path = tmp_path / "n.json"
    _nowcast_json(path)
    nc = run.load_cleveland_nowcast(path)
    ru = pd.DataFrame(
        {
            "series": ["KXCPI"],
            "event_ticker": ["CPI-22DEC"],
            "pmf_mean": [0.25],
            "release_date": [pd.Timestamp("2023-01-12")],
            "excluded": [False],
        }
    )
    cal = pd.DatetimeIndex(["2023-01-11", "2023-01-12"])
    rets = pd.DataFrame({"TLT_co_ex": [0.0, -0.001]}, index=cal)
    gap = run.build_gap_table(ru, rets, nc, cal)
    # the 2023-01-12 value (0.3) is dated on the release day and must not be used
    assert gap.loc[0, "nowcast"] == pytest.approx(0.2)
    assert gap.loc[0, "gap"] == pytest.approx(0.05)


def test_h2_hit_rule_counts_hotter_gap_against_falling_tlt():
    gap = pd.DataFrame(
        {
            "gap": [0.10, 0.12, -0.15, -0.11, 0.01, -0.02],
            "TLT_co_ex": [-0.003, -0.002, 0.004, -0.001, 0.0, 0.0],
            "release_date": pd.to_datetime(["2024-02-01"] * 6),
        }
    )
    out = run.run_h2(gap)
    # median |gap| = 0.105 keeps |gap| in {0.12, 0.15, 0.11}; hits: +0.12/TLT down, -0.15/TLT up
    # (both hits), -0.11/TLT down (miss)
    assert out["continue_rule"]["pooled"]["n"] == 3
    assert out["continue_rule"]["pooled"]["hits"] == 2


def test_candidate_costs_and_borrow():
    day = pd.DataFrame(
        {
            "release_date": pd.to_datetime(["2024-03-01", "2024-04-01"]),
            "U_rel": [1.5, 0.8],
            "QQQ_cc_ex": [0.01, 0.01],
        }
    )
    trades = run.candidate_returns("U1", day, day, pd.DataFrame(), 1.0)
    assert len(trades) == 1  # only U_rel > 1
    assert trades["net"].iloc[0] == pytest.approx(0.01 - 2 * 2.0 / 1e4)
    stress = run.candidate_returns("U1", day, day, pd.DataFrame(), 2.0)
    assert stress["net"].iloc[0] == pytest.approx(0.01 - 2 * 4.0 / 1e4)
    weights = run.candidate_returns("U6", day, day, pd.DataFrame(), 1.0)
    assert weights["w"].tolist() == [pytest.approx(0.75), pytest.approx(0.4)]
    gap = pd.DataFrame(
        {"release_date": pd.to_datetime(["2024-03-01"]), "gap": [0.1], "TLT_co_ex": [-0.002]}
    )
    g1 = run.candidate_returns("G1", day, day, gap, 1.0)
    assert g1["w"].iloc[0] == -1.0  # hotter than consensus: short TLT
    assert g1["gross"].iloc[0] == pytest.approx(0.002)
    assert g1["net"].iloc[0] == pytest.approx(0.002 - 2 * 2.0 / 1e4 - 0.005 / 252.0)


def test_shuffle_keeps_each_series_multiset_and_never_mixes_series():
    rng = np.random.default_rng(0)
    events = pd.DataFrame(
        {
            "series": ["A", "A", "A", "B", "B", "B"],
            "release_date": pd.to_datetime(
                ["2024-01-02", "2024-02-02", "2024-03-04", "2024-04-02", "2024-05-02", "2024-06-04"]
            ),
            "U_rel": [0.5, 0.6, 0.7, 1.5, 1.6, 1.7],
        }
    )
    for _ in range(25):
        out = run.shuffle_within_series(events, rng)
        assert sorted(out.loc[out["series"] == "A", "U_rel"]) == [0.5, 0.6, 0.7]
        assert sorted(out.loc[out["series"] == "B", "U_rel"]) == [1.5, 1.6, 1.7]
        assert out["release_date"].tolist() == events["release_date"].tolist()


def test_permuted_d_takes_values_from_the_two_by_two_grid():
    rng = np.random.default_rng(0)
    events = pd.DataFrame(
        {
            "series": ["A", "A", "B", "B"],
            "release_date": pd.to_datetime(
                ["2024-01-02", "2024-02-02", "2024-03-04", "2024-04-02"]
            ),
            "U_rel": [2.0, 0.5, 2.0, 0.5],
        }
    )
    rets = pd.DataFrame({"r": [0.01, 0.0, 0.01, 0.0]}, index=events["release_date"])
    values = {round(run.permuted_d(events, rets, rng, "r"), 6) for _ in range(60)}
    assert values <= {100.0, 0.0, -100.0} and len(values) > 1
