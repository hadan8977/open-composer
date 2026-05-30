from __future__ import annotations

import json
from types import SimpleNamespace

from open_composer.research.router_common import (
    RouterCandidate,
    RouterMetrics,
    RouterWalkForwardSlice,
    acceptance_gate,
    quality_flags,
    write_router_research_artifacts,
)


def _metrics(
    *,
    annualized: float,
    sharpe: float,
    drawdown: float,
    benchmark_alpha: float = -10.0,
    best_symbol_alpha: float = -100.0,
) -> RouterMetrics:
    return RouterMetrics(
        days=252,
        start_date="2025-01-01",
        end_date="2025-12-31",
        total_return_pct=annualized,
        annualized_return_pct=annualized,
        sharpe_ratio=sharpe,
        max_drawdown_pct=drawdown,
        traded_days=200,
        round_trips=20,
        average_selected_count=1.0,
        win_day_pct=52.0,
        benchmark_symbol="TQQQ",
        benchmark_buy_hold_return_pct=50.0,
        benchmark_buy_hold_annualized_pct=50.0,
        alpha_vs_benchmark_buy_hold_annualized_pct=benchmark_alpha,
        market_symbol="QQQ",
        market_buy_hold_return_pct=20.0,
        market_buy_hold_annualized_pct=20.0,
        alpha_vs_market_buy_hold_annualized_pct=annualized - 20.0,
        equal_weight_buy_hold_return_pct=20.0,
        equal_weight_buy_hold_annualized_pct=20.0,
        alpha_vs_equal_weight_buy_hold_annualized_pct=annualized - 20.0,
        best_symbol_buy_hold_pct=200.0,
        best_symbol="SOXL",
        alpha_vs_best_symbol_buy_hold_pct=best_symbol_alpha,
        exposure_pct=80.0,
        skipped_days=10,
        average_gross_exposure_pct=55.0,
        max_gross_exposure_pct=60.0,
        max_symbol_weight_pct=55.0,
    )


def test_absolute_return_risk_objective_does_not_block_on_tqqq_alpha() -> None:
    train = _metrics(annualized=20.0, sharpe=0.8, drawdown=-30.0, benchmark_alpha=-30.0)
    oos = _metrics(annualized=48.0, sharpe=1.3, drawdown=-28.0, benchmark_alpha=15.0)
    full = _metrics(annualized=31.0, sharpe=1.02, drawdown=-37.0, benchmark_alpha=-14.0)

    assert quality_flags(train, oos, full, objective="absolute_return_risk") == []

    candidate = RouterCandidate(
        rank=1,
        params=SimpleNamespace(label="route"),
        score=1.0,
        train=train,
        out_of_sample=oos,
        full_window=full,
        quality_flags=[],
    )
    walk_forward = [
        RouterWalkForwardSlice(fold=index, params=candidate.params, train=train, test=oos)
        for index in range(1, 6)
    ]

    gate = acceptance_gate(candidate, walk_forward, "absolute_return_risk")

    assert gate["passed"] is True
    assert gate["quality_flags"] == []
    assert "train_no_alpha_vs_benchmark" in gate["advisory_flags"]
    assert "does_not_beat_ex_post_best_symbol" in gate["advisory_flags"]


def test_benchmark_objective_keeps_benchmark_alpha_flags() -> None:
    train = _metrics(annualized=20.0, sharpe=0.8, drawdown=-30.0, benchmark_alpha=-30.0)
    oos = _metrics(annualized=25.0, sharpe=1.0, drawdown=-20.0, benchmark_alpha=-5.0)
    full = _metrics(annualized=30.0, sharpe=1.0, drawdown=-25.0, benchmark_alpha=-15.0)

    flags = quality_flags(train, oos, full, objective="risk_adjusted_benchmark_alpha")

    assert "train_no_alpha_vs_benchmark" in flags
    assert "oos_no_alpha_vs_benchmark" in flags
    assert "does_not_beat_ex_post_best_symbol" in flags


def test_write_router_research_artifacts_creates_harness_shapes(tmp_path) -> None:
    train = _metrics(annualized=20.0, sharpe=0.8, drawdown=-30.0)
    oos = _metrics(annualized=48.0, sharpe=1.3, drawdown=-28.0)
    full = _metrics(annualized=31.0, sharpe=1.02, drawdown=-37.0)
    candidate = RouterCandidate(
        rank=1,
        params=SimpleNamespace(label="route"),
        score=1.0,
        train=train,
        out_of_sample=oos,
        full_window=full,
        quality_flags=[],
    )
    walk_forward = [RouterWalkForwardSlice(fold=1, params=candidate.params, train=train, test=oos)]
    payload = {
        "search_space": {
            "candidate_count": 1,
            "parameter_ranges": {"momentum_lookback_days": [20]},
            "filters": ["bounded"],
        },
        "research_cost": {"candidate_count": 1},
        "acceptance_gate": acceptance_gate(candidate, walk_forward, "absolute_return_risk"),
        "candidates": [
            {
                "rank": 1,
                "params": {"label": "route", "momentum_lookback_days": 20},
                "score": 1.0,
                "quality_flags": [],
                "train": train.__dict__,
                "out_of_sample": oos.__dict__,
                "full_window": full.__dict__,
            }
        ],
        "selected_candidate": {
            "params": {"label": "route", "momentum_lookback_days": 20},
            "out_of_sample": oos.__dict__,
        },
        "walk_forward": [
            {
                "fold": 1,
                "params": {"label": "route", "momentum_lookback_days": 20},
                "train": train.__dict__,
                "test": oos.__dict__,
            }
        ],
    }

    write_router_research_artifacts(
        base=tmp_path,
        strategy_name="router",
        mode="hybrid_adaptive_router",
        report_suffix="hybrid-adaptive-router",
        payload=payload,
        data_profile={"provider": "fixture"},
    )

    research_dir = tmp_path / "reports" / "research"
    search_space = json.loads((research_dir / "router-search-space.json").read_text())
    candidate_set = json.loads((research_dir / "router-candidate-set.json").read_text())
    walk_forward_payload = json.loads((research_dir / "router-walk-forward.json").read_text())
    ledger_lines = (research_dir / "router-trial-ledger.jsonl").read_text().splitlines()

    assert search_space["total_combinations"] == 1
    assert candidate_set["selected_candidate_id"] == "route"
    assert walk_forward_payload["conclusion"] == "pass"
    assert json.loads(ledger_lines[0])["selected"] is True
