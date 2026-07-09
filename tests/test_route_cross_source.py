from __future__ import annotations

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.route_cross_source import judge_route_cross_source


def _rows(*, alternate_state: str | None = None, crisis_flip: bool = False) -> list[dict]:
    return [
        {
            "date": "2018-10-02",
            "state": alternate_state or "risk_on",
            "weights": {"TQQQ": 1.0},
            "contributions": {"TQQQ": -0.01 if crisis_flip else 0.01},
            "cost": 0.0,
            "net_return": -0.01 if crisis_flip else 0.01,
            "tqqq_return": 0.02 if crisis_flip else -0.01,
        },
        {
            "date": "2020-03-02",
            "state": "hard_stress_defensive",
            "weights": {"GLD": 1.0},
            "contributions": {"GLD": 0.02},
            "cost": 0.0,
            "net_return": 0.02,
            "tqqq_return": -0.1,
        },
        {
            "date": "2022-06-01",
            "state": "risk_on",
            "weights": {"TQQQ": 1.0},
            "contributions": {"TQQQ": 0.03},
            "cost": 0.0,
            "net_return": 0.03,
            "tqqq_return": -0.2,
        },
        {
            "date": "2023-01-03",
            "state": "risk_on",
            "weights": {"TQQQ": 1.0},
            "contributions": {"TQQQ": 0.01},
            "cost": 0.0,
            "net_return": 0.01,
            "tqqq_return": 0.005,
        },
    ]


def _metrics(annualized: float = 12.0, maxdd: float = -20.0) -> dict:
    return {
        "total_return_pct": 100.0,
        "annualized_return_pct": annualized,
        "sharpe_ratio": 1.0,
        "max_drawdown_pct": maxdd,
    }


def test_route_cross_source_judge_passes_when_all_gates_pass() -> None:
    payload = judge_route_cross_source(
        main_rows=_rows(),
        alt_rows=_rows(),
        main_metrics=_metrics(),
        alt_metrics=_metrics(annualized=13.0, maxdd=-22.0),
    )

    assert payload["route_cross_source_pass"] is True
    assert payload["gates"]["crisis_conclusions_do_not_flip"]["passed"] is True
    assert payload["gates"]["state_sequence_consistency_gte_95pct"]["actual_pct"] == 100.0


def test_route_cross_source_judge_fails_when_crisis_conclusion_flips() -> None:
    payload = judge_route_cross_source(
        main_rows=_rows(),
        alt_rows=_rows(crisis_flip=True),
        main_metrics=_metrics(),
        alt_metrics=_metrics(),
    )

    assert payload["route_cross_source_pass"] is False
    crisis_gate = payload["gates"]["crisis_conclusions_do_not_flip"]
    assert crisis_gate["passed"] is False
    assert crisis_gate["windows"][0]["conclusion_flipped"] is True


def test_route_cross_source_judge_fails_when_state_consistency_is_low() -> None:
    payload = judge_route_cross_source(
        main_rows=_rows(),
        alt_rows=_rows(alternate_state="risk_off"),
        main_metrics=_metrics(),
        alt_metrics=_metrics(),
    )

    assert payload["route_cross_source_pass"] is False
    state_gate = payload["gates"]["state_sequence_consistency_gte_95pct"]
    assert state_gate["passed"] is False
    assert state_gate["mismatch_count"] == 1


def test_step8_cross_source_cli_help_smoke() -> None:
    runner = CliRunner()

    assert runner.invoke(app, ["data", "fetch-alt-daily", "--help"]).exit_code == 0
    assert (
        runner.invoke(app, ["strategy", "route-cross-source-validation", "--help"]).exit_code == 0
    )
