from __future__ import annotations

from open_composer.research.event_seeded_theme_stock_r10_evaluation import (
    EFFECTIVE_TRIAL_COUNT,
    _development_performance_gates,
    _event_theme_diagnostics,
)


def test_r10_event_theme_diagnostics_count_confirmed_lifecycle_and_rotation() -> None:
    records = [
        {
            "event_seeds": [{"symbol": "A"}],
            "selected_symbols": [],
            "themes": [{"theme_id": "t1", "state": "formation"}],
        },
        {
            "event_seeds": [],
            "selected_symbols": ["A", "B"],
            "themes": [{"theme_id": "t1", "state": "confirmed"}],
        },
        {
            "event_seeds": [{"symbol": "C"}],
            "selected_symbols": ["B", "C"],
            "themes": [
                {"theme_id": "t1", "state": "expansion"},
                {"theme_id": "t2", "state": "formation"},
            ],
        },
        {
            "event_seeds": [],
            "selected_symbols": ["C"],
            "themes": [
                {"theme_id": "t1", "state": "mature"},
                {"theme_id": "t2", "state": "exhausted"},
            ],
        },
    ]

    result = _event_theme_diagnostics(records)

    assert result == {
        "event_seed_count": 2,
        "formed_theme_count": 2,
        "confirmed_theme_count": 1,
        "median_confirmed_lifecycle_sessions": 3.0,
        "maximum_confirmed_lifecycle_sessions": 3,
        "selected_symbol_count": 3,
        "selected_symbols": ["A", "B", "C"],
    }


def test_r10_d01_development_gates_bind_turnover_lifecycle_and_beta_lift() -> None:
    metrics = {
        "cagr": 0.60,
        "max_drawdown": -0.50,
        "annualized_sharpe_excess_BIL": 1.20,
        "mar": 1.20,
        "tqqq_up_capture": 0.90,
        "tqqq_down_capture": 0.80,
        "annualized_reported_one_way_turnover": 29.0,
    }
    gates = _development_performance_gates(
        candidate_id="R10D01",
        metrics=metrics,
        severe_metrics={"total_return": 0.10},
        qqq_metrics={"cagr": 0.30},
        tqqq_metrics={"cagr": 0.65},
        positive_lift_folds=3,
        dsr={"probability": 0.80},
        pbo={"probability": 0.30},
        d02_metrics={"cagr": 0.55},
        theme_diagnostics={"median_confirmed_lifecycle_sessions": 3.0},
    )

    assert all(row["pass"] for row in gates)
    assert {row["name"] for row in gates} >= {
        "annualized_one_way_turnover",
        "median_confirmed_lifecycle_sessions",
        "d01_cagr_exceeds_d02",
    }

    metrics["annualized_reported_one_way_turnover"] = 30.01
    failed = _development_performance_gates(
        candidate_id="R10D01",
        metrics=metrics,
        severe_metrics={"total_return": 0.10},
        qqq_metrics={"cagr": 0.30},
        tqqq_metrics={"cagr": 0.65},
        positive_lift_folds=3,
        dsr={"probability": 0.80},
        pbo={"probability": 0.30},
        d02_metrics={"cagr": 0.55},
        theme_diagnostics={"median_confirmed_lifecycle_sessions": 2.0},
    )
    by_name = {row["name"]: row for row in failed}
    assert by_name["annualized_one_way_turnover"]["pass"] is False
    assert by_name["median_confirmed_lifecycle_sessions"]["pass"] is False


def test_r10_effective_trial_count_includes_all_eight_frozen_candidates() -> None:
    assert EFFECTIVE_TRIAL_COUNT == 8022 + 8
