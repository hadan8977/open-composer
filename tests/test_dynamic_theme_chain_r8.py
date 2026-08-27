from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.adapters.data.alpaca_snapshot import (
    AlpacaSnapshotContract,
    _requests_from_contract,
)
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.dynamic_theme_chain_r8 import (
    D01_CANDIDATE_SYMBOLS,
    ITER_ID,
    LEVERAGED_SYMBOLS,
    SPEC_PATHS,
    UNIVERSE,
    PanelData,
    _development_folds,
    _evaluation_windows,
    _simulation_metric_views,
    _validate_specs,
    compute_d01_targets,
    compute_d02_targets,
    connected_components,
    cross_sectional_percentile,
    cscv_probability_backtest_overfitting,
    deflated_sharpe_probability,
    run_dynamic_theme_chain_r8,
)
from open_composer.research.etf_structural_r9 import simulate_target_portfolio


def test_r8_snapshot_contract_expands_to_eighty_independent_requests(
    repo_root: Path,
) -> None:
    path = (
        repo_root / "reports/research/iterations/mom_dynamic_theme_chain_r8/snapshot-contract.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    contract = AlpacaSnapshotContract.model_validate(payload)
    requests = _requests_from_contract(contract.model_dump(mode="json"))

    assert contract.iter_id == ITER_ID
    assert tuple(contract.symbols) == UNIVERSE
    assert contract.latest_frozen_session.isoformat() == "2026-08-03"
    assert len(requests) == 80
    assert {(row.symbol, row.adjustment) for row in requests} == {
        (symbol, adjustment)
        for symbol in UNIVERSE
        for adjustment in ("raw", "split", "dividend", "all")
    }


def test_r8_specs_keep_broker_free_fixed_candidate_contract(repo_root: Path) -> None:
    specs = {
        candidate_id: load_strategy_spec(repo_root / path)
        for candidate_id, path in SPEC_PATHS.items()
    }

    _validate_specs(specs)

    assert (
        tuple(specs["R8D01"].notes.model_dump(mode="json")["graph_contract"]["candidate_symbols"])
        == D01_CANDIDATE_SYMBOLS
    )
    route = specs["R8D02"].notes.model_dump(mode="json")["route_contract"]
    assert route["tqqq_weight"] == 0.65
    assert route["qld_weight"] == 0.35
    assert route["maximum_total_leveraged_etf_weight"] == 1.0


def test_positive_correlation_graph_does_not_join_negative_pair() -> None:
    correlations = pd.DataFrame(
        [
            [1.0, 0.60, -0.80, 0.10],
            [0.60, 1.0, -0.70, 0.05],
            [-0.80, -0.70, 1.0, 0.55],
            [0.10, 0.05, 0.55, 1.0],
        ],
        index=["A", "B", "C", "D"],
        columns=["A", "B", "C", "D"],
    )

    assert connected_components(correlations, threshold=0.35) == [("A", "B"), ("C", "D")]


def test_cross_sectional_rank_uses_symbol_ascending_tie_break() -> None:
    ranks = cross_sectional_percentile(pd.Series({"B": 2.0, "A": 2.0, "C": 1.0}))

    assert ranks["A"] == 1.0
    assert ranks["A"] > ranks["B"] > ranks["C"]


def test_d01_targets_are_next_session_mwf_capped_and_no_lookahead(repo_root: Path) -> None:
    closes, volumes = _synthetic_panel()
    spec = load_strategy_spec(repo_root / SPEC_PATHS["R8D01"])

    targets, records = compute_d01_targets(closes, volumes, spec)

    assert len(targets) > 30
    assert np.allclose(targets.sum(axis=1), 1.0)
    assert (targets >= 0).all().all()
    assert all(session.weekday() in {0, 2, 4} for session in targets.index)
    assert (targets.drop(columns="BIL").max(axis=1) <= 0.60 + 1e-12).all()
    assert (targets.loc[:, list(LEVERAGED_SYMBOLS)].sum(axis=1) <= 0.75 + 1e-12).all()
    assert all(len(row["selected_symbols"]) <= 3 for row in records)
    for row in records:
        weights = row["weights"]
        for members in {tuple(value) for value in row["selected_theme_map"].values()}:
            assert sum(weights[symbol] for symbol in members) <= 0.50 + 1e-12

    pivot = records[len(records) // 2]
    decision = pd.Timestamp(pivot["decision_session"])
    execution = pd.Timestamp(pivot["execution_session"])
    changed_closes = closes.copy()
    changed_volumes = volumes.copy()
    changed_closes.loc[changed_closes.index > decision] *= 1.75
    changed_volumes.loc[changed_volumes.index > decision] *= 3.0

    changed_targets, changed_records = compute_d01_targets(changed_closes, changed_volumes, spec)
    changed_by_execution = {row["execution_session"]: row for row in changed_records}

    pd.testing.assert_series_equal(targets.loc[execution], changed_targets.loc[execution])
    assert (
        pivot["target_sha256"] == changed_by_execution[pivot["execution_session"]]["target_sha256"]
    )


def test_d02_targets_follow_aggressive_state_machine(repo_root: Path) -> None:
    closes, _ = _synthetic_panel()
    spec = load_strategy_spec(repo_root / SPEC_PATHS["R8D02"])
    targets, records = compute_d02_targets(closes, spec)

    assert len(targets) > 30
    assert np.allclose(targets.sum(axis=1), 1.0)
    assert all(pd.Timestamp(row["execution_session"]).weekday() in {0, 2, 4} for row in records)
    assert "strong_risk_on" in {row["state"] for row in records}
    for row in records:
        weights = row["weights"]
        if row["state"] == "strong_risk_on":
            assert weights["TQQQ"] == 0.65
            assert weights["QLD"] == 0.35
        elif row["state"] == "moderate_risk_on":
            assert weights["QQQ"] == 1.0
        else:
            assert weights["BIL"] == 1.0


def test_evaluation_windows_folds_and_terminal_metric_views() -> None:
    sessions = pd.bdate_range("2019-01-02", periods=1800)
    windows = _evaluation_windows(sessions, sessions[100], sessions[-1])
    lockbox = sessions[
        (sessions >= windows["lockbox"]["start"]) & (sessions <= windows["lockbox"]["end"])
    ]
    folds = _development_folds(sessions, windows["development"])

    assert len(lockbox) - 1 == 252
    assert len(folds) == 4
    assert all(fold["test_interval_count"] >= 126 for fold in folds)

    opens = pd.DataFrame(
        {
            symbol: 100.0 * np.cumprod(np.full(len(sessions), 1.0004 + index * 0.000001))
            for index, symbol in enumerate(UNIVERSE)
        },
        index=sessions,
    )
    target = {symbol: 0.0 for symbol in UNIVERSE}
    target["QQQ"] = 1.0
    targets = pd.DataFrame(
        [target],
        index=pd.DatetimeIndex([windows["lockbox"]["start"]]),
        columns=opens.columns,
    )
    simulation = simulate_target_portfolio(
        opens,
        targets,
        cost_bps=20.0,
        start=windows["lockbox"]["start"],
        end=windows["lockbox"]["end"],
    )
    metrics = _simulation_metric_views(simulation, opens)

    assert metrics["with_terminal"]["terminal_liquidation_count"] == 1
    assert metrics["without_terminal"]["terminal_liquidation_count"] == 0
    assert metrics["without_terminal"]["total_return"] > metrics["with_terminal"]["total_return"]


def test_cscv_pbo_is_candidate_id_invariant_for_identical_streams() -> None:
    index = pd.bdate_range("2020-01-02", periods=800)
    values = pd.Series(np.sin(np.arange(800) / 17.0) * 0.002 + 0.0005, index=index)

    pbo = cscv_probability_backtest_overfitting(
        {"R8D01": values, "R8D02": values.copy()},
        block_count=8,
    )
    dsr = deflated_sharpe_probability(values, 8014)

    assert pbo["partition_count"] == 70
    assert pbo["probability"] == 0.5
    assert all(row["overfit_loss"] == 0.5 for row in pbo["partitions"])
    assert 0.0 <= dsr["probability"] <= 1.0


@pytest.mark.slow
def test_full_deterministic_evaluation_pipeline_on_synthetic_panel(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch,
) -> None:
    closes, volumes = _synthetic_panel(session_count=1650)
    opens = closes * 1.0002
    panel = PanelData(open=opens, close=closes, volume=volumes)
    specs_by_name = {
        path.name: load_strategy_spec(repo_root / path) for path in SPEC_PATHS.values()
    }
    output = tmp_path / "reports/research/iterations/mom_dynamic_theme_chain_r8"
    output.mkdir(parents=True)
    monkeypatch.setattr(
        "open_composer.research.dynamic_theme_chain_r8._preflight",
        lambda _root: {
            "status": "ok",
            "snapshot_manifest_sha256": "a" * 64,
            "snapshot_manifest_path": "data/research/synthetic/snapshot-manifest.json",
        },
    )
    monkeypatch.setattr(
        "open_composer.research.dynamic_theme_chain_r8.load_r8_panel",
        lambda _root, _manifest: panel,
    )
    monkeypatch.setattr(
        "open_composer.research.dynamic_theme_chain_r8.load_strategy_spec",
        lambda path: specs_by_name[Path(path).name],
    )

    result = run_dynamic_theme_chain_r8(tmp_path)

    assert result.evaluation_path.exists()
    assert result.trial_ledger_path.exists()
    assert result.payload["workflow_pass"] is True
    assert result.payload["paper_ready_pass"] is False
    assert result.payload["broker_writes"] is False
    assert result.payload["pbo"]["partition_count"] == 70
    assert set(result.payload["candidates"]) == {"R8D01", "R8D02"}
    assert (
        result.payload["candidates"]["R8D02"]["windows"]["full"]["primary_20bps"]["with_terminal"][
            "market_interval_count"
        ]
        > 1200
    )


def _synthetic_panel(session_count: int = 260) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(8208)
    sessions = pd.bdate_range("2024-01-02", periods=session_count)
    market = rng.normal(0.0004, 0.006, session_count)
    technology = rng.normal(0.0005, 0.008, session_count)
    group_a = rng.normal(0.0010, 0.008, session_count)
    group_b = rng.normal(0.0006, 0.007, session_count)
    returns: dict[str, np.ndarray] = {}
    for symbol in UNIVERSE:
        noise = rng.normal(0.0, 0.0015, session_count)
        if symbol == "SPY":
            values = market
        elif symbol == "QQQ":
            values = 0.35 * market + technology
        elif symbol == "BIL":
            values = np.full(session_count, 0.00015) + noise * 0.02
        elif symbol in D01_CANDIDATE_SYMBOLS[:9]:
            values = 0.25 * market + 0.35 * technology + group_a + noise
        else:
            values = 0.30 * market + 0.20 * technology + group_b + noise
        if symbol == "TQQQ":
            values = values * 1.8
        elif symbol in {"QLD", "SOXL"}:
            values = values * 1.4
        returns[symbol] = np.clip(values, -0.15, 0.15)
    closes = pd.DataFrame(
        {symbol: 100.0 * np.cumprod(1.0 + returns[symbol]) for symbol in UNIVERSE},
        index=sessions,
    )
    volumes = pd.DataFrame(
        {
            symbol: 1_000_000.0
            * np.exp(rng.normal(0.0, 0.15, session_count))
            * (1.0 + 0.02 * index)
            for index, symbol in enumerate(UNIVERSE)
        },
        index=sessions,
    )
    return closes, volumes
