from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.dynamic_theme_stock_r9 import (
    BENCHMARK_SYMBOLS,
    compute_r9_d01_targets,
    compute_r9_d02_targets,
    mutual_knn_components,
    validate_r9_runtime_panel,
    validate_r9_spec_pair,
)

D01_PATH = Path("strategy_specs/drafts/us_dynamic_theme_stock_r9_d01.yaml")
D02_PATH = Path("strategy_specs/drafts/us_dynamic_theme_stock_r9_d02.yaml")


@pytest.fixture(scope="module")
def r9_inputs():
    repo_root = Path(__file__).resolve().parents[1]
    d01 = load_strategy_spec(repo_root / D01_PATH)
    d02 = load_strategy_spec(repo_root / D02_PATH)
    closes, volumes, membership, early_theme, late_theme = _rotating_theme_panel(d01.universe)
    targets, records = compute_r9_d01_targets(closes, volumes, membership, d01)
    return {
        "d01": d01,
        "d02": d02,
        "closes": closes,
        "volumes": volumes,
        "membership": membership,
        "early_theme": early_theme,
        "late_theme": late_theme,
        "targets": targets,
        "records": records,
    }


def test_r9_specs_bind_broad_diagnostic_parent_and_multiscale_layers(repo_root: Path) -> None:
    d01 = load_strategy_spec(repo_root / D01_PATH)
    d02 = load_strategy_spec(repo_root / D02_PATH)

    validate_r9_spec_pair(d01, d02)

    candidates = [symbol for symbol in d01.universe if symbol not in BENCHMARK_SYMBOLS]
    discovery = d01.notes.model_dump(mode="json")["theme_discovery"]
    assert len(candidates) == 62
    assert discovery["parent_membership_source"] == "daily_frozen_dynamic_parent"
    assert discovery["fast_layer"]["momentum_sessions"] == [3, 5]
    assert discovery["propagation_layer"]["momentum_sessions"] == [10, 20]
    assert discovery["semantic_labels_selectable"] is False
    assert d02.notes.model_dump(mode="json")["aggressive_beta_core"]["risk_on_weights"] == {
        "TQQQ": 0.75,
        "theme_satellite": 0.25,
    }


def test_mutual_knn_components_separates_unrelated_cohorts() -> None:
    symbols = list("ABCDEF")
    affinity = pd.DataFrame(0.0, index=symbols, columns=symbols)
    np.fill_diagonal(affinity.values, 1.0)
    for group, value in (("ABC", 0.80), ("DEF", 0.75)):
        for left in group:
            for right in group:
                affinity.at[left, right] = 1.0 if left == right else value
    affinity.at["A", "D"] = affinity.at["D", "A"] = -0.90

    components = mutual_knn_components(
        affinity,
        k=2,
        threshold=0.30,
        minimum_members=3,
        maximum_members=5,
    )

    assert components == (("A", "B", "C"), ("D", "E", "F"))


@pytest.mark.slow
def test_r9_d01_changes_theme_and_respects_decision_time_membership(r9_inputs) -> None:
    records = r9_inputs["records"]
    early_theme = set(r9_inputs["early_theme"])
    late_theme = set(r9_inputs["late_theme"])
    membership_start = r9_inputs["membership"].index[120]
    nonempty = [row for row in records if row["selected_symbols"]]

    early = [
        row
        for row in nonempty
        if pd.Timestamp(row["decision_session"]) < membership_start
        and len(early_theme & set(row["selected_symbols"])) >= 2
    ]
    late = [
        row
        for row in nonempty
        if pd.Timestamp(row["decision_session"]) > r9_inputs["membership"].index[145]
        and len(late_theme & set(row["selected_symbols"])) >= 2
    ]

    assert early
    assert late
    assert all(
        not (late_theme & set(row["selected_symbols"]))
        for row in records
        if pd.Timestamp(row["decision_session"]) < membership_start
    )
    assert set(early[-1]["selected_symbols"]) != set(late[-1]["selected_symbols"])
    assert {theme["layer"] for row in nonempty for theme in row["themes"]}.issubset(
        {"fast", "propagation"}
    )


def test_r9_runtime_candidates_come_from_daily_membership_not_static_spec(r9_inputs) -> None:
    first = r9_inputs["membership"].columns[0]
    dynamic_symbol = "NEW_THEME_LEADER"
    closes = r9_inputs["closes"].rename(columns={first: dynamic_symbol})
    volumes = r9_inputs["volumes"].rename(columns={first: dynamic_symbol})
    membership = r9_inputs["membership"].rename(columns={first: dynamic_symbol})

    candidates = validate_r9_runtime_panel(
        closes,
        volumes,
        membership,
        r9_inputs["d01"],
    )

    assert dynamic_symbol in candidates
    assert first not in candidates


def test_r9_d01_target_is_unchanged_by_post_decision_prices(r9_inputs) -> None:
    d01 = r9_inputs["d01"]
    closes = r9_inputs["closes"]
    volumes = r9_inputs["volumes"]
    membership = r9_inputs["membership"]
    original_records = r9_inputs["records"]
    pivot = next(row for row in original_records[15:] if row["selected_symbols"])
    decision = pd.Timestamp(pivot["decision_session"])
    execution = pd.Timestamp(pivot["execution_session"])
    changed_closes = closes.loc[:execution].copy()
    changed_volumes = volumes.loc[:execution].copy()
    changed_membership = membership.loc[:execution].copy()
    future = changed_closes.index > decision
    symbol_scale = np.linspace(0.65, 1.75, changed_closes.shape[1])
    changed_closes.loc[future] = changed_closes.loc[future].mul(symbol_scale, axis=1)
    changed_volumes.loc[future] *= 4.0

    changed_targets, changed_records = compute_r9_d01_targets(
        changed_closes,
        changed_volumes,
        changed_membership,
        d01,
    )
    changed_by_execution = {pd.Timestamp(row["execution_session"]): row for row in changed_records}

    pd.testing.assert_series_equal(
        r9_inputs["targets"].loc[execution],
        changed_targets.loc[execution],
    )
    assert pivot["target_sha256"] == changed_by_execution[execution]["target_sha256"]


def test_r9_d02_uses_tqqq_like_core_and_dynamic_stock_satellite(r9_inputs) -> None:
    targets, records = compute_r9_d02_targets(
        r9_inputs["closes"],
        r9_inputs["volumes"],
        r9_inputs["membership"],
        r9_inputs["d01"],
        r9_inputs["d02"],
        d01_result=(r9_inputs["targets"], r9_inputs["records"]),
    )
    risk_on = next(
        row
        for row in reversed(records)
        if row["state"] == "risk_on" and row["selected_theme_symbols"]
    )
    weights = pd.Series(risk_on["weights"])
    stock_symbols = [
        symbol for symbol in r9_inputs["d01"].universe if symbol not in BENCHMARK_SYMBOLS
    ]

    assert np.allclose(targets.sum(axis=1), 1.0)
    assert weights["TQQQ"] == pytest.approx(0.75)
    assert weights.loc[stock_symbols].sum() == pytest.approx(0.25)
    assert set(weights.loc[stock_symbols][weights.loc[stock_symbols] > 0].index) == set(
        risk_on["selected_theme_symbols"]
    )
    assert max(weights.loc[stock_symbols]) <= 0.18


def _rotating_theme_panel(universe: list[str], session_count: int = 190):
    rng = np.random.default_rng(9009)
    sessions = pd.bdate_range("2025-10-01", periods=session_count)
    candidates = [symbol for symbol in universe if symbol not in BENCHMARK_SYMBOLS]
    early_theme = tuple(candidates[:5])
    late_theme = tuple(candidates[5:10])
    market = rng.normal(0.00065, 0.0050, session_count)
    growth = rng.normal(0.00045, 0.0035, session_count)
    early = rng.normal(np.where(np.arange(session_count) < 108, 0.0020, -0.0010), 0.0050)
    late = rng.normal(np.where(np.arange(session_count) < 108, -0.0005, 0.0025), 0.0050)
    returns: dict[str, np.ndarray] = {}
    for index, symbol in enumerate(candidates):
        noise = rng.normal(
            0.0,
            0.0012 if symbol in {*early_theme, *late_theme} else 0.0080,
            session_count,
        )
        if symbol in early_theme:
            values = 0.25 * market + 0.20 * growth + early + noise
        elif symbol in late_theme:
            values = 0.25 * market + 0.20 * growth + late + noise
        else:
            values = 0.30 * market + noise + (index % 7) * 0.00001
        returns[symbol] = np.clip(values, -0.12, 0.12)
    spy = market
    qqq = 0.65 * market + growth + 0.00045
    returns.update(
        {
            "SPY": spy,
            "QQQ": qqq,
            "QLD": np.clip(2.0 * qqq, -0.20, 0.20),
            "TQQQ": np.clip(3.0 * qqq, -0.30, 0.30),
            "BIL": np.full(session_count, 0.00012),
        }
    )
    closes = pd.DataFrame(
        {symbol: 100.0 * np.cumprod(1.0 + returns[symbol]) for symbol in universe},
        index=sessions,
    )
    volumes = pd.DataFrame(
        {
            symbol: 2_000_000.0
            * np.exp(rng.normal(0.0, 0.12, session_count))
            * (
                1.0
                + (0.30 if symbol in early_theme else 0.0) * (np.arange(session_count) < 108)
                + (0.35 if symbol in late_theme else 0.0) * (np.arange(session_count) >= 108)
            )
            for symbol in universe
        },
        index=sessions,
    )
    membership = pd.DataFrame(True, index=sessions, columns=candidates, dtype=bool)
    membership.loc[sessions[:120], list(late_theme)] = False
    return closes, volumes, membership, early_theme, late_theme
