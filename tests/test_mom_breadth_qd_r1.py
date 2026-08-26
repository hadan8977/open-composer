from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from open_composer.market_calendar import us_equity_session_dates
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research import mom_breadth_qd_r1 as breadth_runner
from open_composer.research.mom_breadth_qd_r1 import (
    BENCHMARK_FAMILY_IDS,
    CAMPAIGN_ROOT,
    DEVELOPMENT_ATTEMPT_PATH,
    DEVELOPMENT_RECEIPT_PATH,
    ITERATION_ROOT,
    BenchmarkFamilyResult,
    PricePanel,
    SimulationResult,
    _advancing_pair_correlation_diagnostic,
    _assert_pristine_publication_state,
    _benchmark_family,
    _calendar_window_active,
    _development_effective_trial_count,
    _load_development_session_calendar,
    _max_drawdown,
    _panel_from_symbol_frames,
    _promotion_passes,
    _publish_staged_outputs,
    _read_price_csv_until,
    _validate_dependency_skipped_iteration_gate,
    _validate_iteration_contract_identities,
    _verify_feasibility_references,
    _verify_ledger_effective_trial_count,
    _verify_runtime_lock_inventory,
    build_target_schedule,
    simulate_target_schedule,
)
from scripts.prepare_mom_breadth_qd_r1 import (
    BRANCHES,
    CANDIDATE_POLICIES,
    _bounded_development_csv,
    _build_spec,
)
from scripts.prepare_mom_breadth_qd_r1 import (
    PORTFOLIO_RETURN_IDENTITY as GENERATED_PORTFOLIO_RETURN_IDENTITY,
)


@pytest.fixture(scope="module")
def synthetic_panel() -> PricePanel:
    sessions = pd.bdate_range("2020-01-02", "2021-12-31")
    symbols = [
        "AAPL",
        "AMZN",
        "AVGO",
        "BIL",
        "GLD",
        "GOOGL",
        "IEF",
        "META",
        "MSFT",
        "NFLX",
        "QLD",
        "QQQ",
        "SPY",
        "TQQQ",
        "XLB",
        "XLE",
        "XLF",
        "XLI",
        "XLK",
        "XLP",
        "XLU",
        "XLV",
        "XLY",
    ]
    positions = np.arange(len(sessions), dtype=float)
    opens: dict[str, np.ndarray] = {}
    closes: dict[str, np.ndarray] = {}
    volumes: dict[str, np.ndarray] = {}
    for offset, symbol in enumerate(symbols, start=1):
        drift = 0.0001 + offset / 1_000_000.0
        base = (
            50.0
            + offset
            + np.exp(drift * positions)
            + 0.3 * np.sin(positions / (4.0 + offset / 10.0))
        )
        open_values = base * (1.0 + 0.002 * np.sin(positions / 7.0 + offset))
        close_values = open_values * (1.0 + 0.003 * np.cos(positions / 5.0 + offset))
        if symbol == "BIL":
            open_values = 100.0 * np.exp(0.00005 * positions)
            close_values = open_values * 1.00002
        opens[symbol] = open_values
        closes[symbol] = close_values
        volumes[symbol] = 1_000_000.0 * (1.0 + 0.7 * np.square(np.sin(positions / 9.0 + offset)))
    return PricePanel(
        opens=pd.DataFrame(opens, index=sessions),
        closes=pd.DataFrame(closes, index=sessions),
        volumes=pd.DataFrame(volumes, index=sessions),
    )


def test_simulation_uses_next_open_and_has_no_terminal_liquidation() -> None:
    sessions = pd.bdate_range("2020-12-30", "2021-01-06")
    panel = PricePanel(
        opens=pd.DataFrame(
            {
                "BIL": [100.0] * len(sessions),
                "QQQ": [100.0, 100.0, 110.0, 121.0, 121.0, 121.0],
            },
            index=sessions,
        ),
        closes=pd.DataFrame(
            {"BIL": [100.0] * len(sessions), "QQQ": [100.0] * len(sessions)},
            index=sessions,
        ),
        volumes=pd.DataFrame(
            {"BIL": [1.0] * len(sessions), "QQQ": [1.0] * len(sessions)},
            index=sessions,
        ),
    )
    schedule = {sessions[1]: {"QQQ": 1.0}}

    result = simulate_target_schedule(
        panel,
        schedule,
        cost_bps=0,
        validation_start=date(2021, 1, 1),
        validation_end=date(2021, 1, 6),
    )

    assert list(result.returns.index) == list(sessions[2:])
    assert result.returns.iloc[0] == pytest.approx(0.10)
    assert result.returns.iloc[1] == pytest.approx(0.10)
    assert len(result.returns) == len(sessions[2:])


def test_one_way_cost_is_applied_to_target_turnover(synthetic_panel: PricePanel) -> None:
    panel = synthetic_panel
    execution = panel.index[panel.index.get_indexer([pd.Timestamp("2021-06-01")])[0]]
    schedule = {execution: {"QQQ": 1.0}}

    low = simulate_target_schedule(panel, schedule, cost_bps=10)
    high = simulate_target_schedule(panel, schedule, cost_bps=40)

    affected = panel.index[panel.index.get_loc(execution) + 1]
    assert low.turnover.loc[affected] == pytest.approx(2.0)
    assert low.returns.loc[affected] > high.returns.loc[affected]


def test_label_contract_identifies_simple_portfolio_returns() -> None:
    assert (
        GENERATED_PORTFOLIO_RETURN_IDENTITY
        == breadth_runner.PORTFOLIO_RETURN_IDENTITY
        == "open_t_to_open_t_plus_1_simple_return_net_of_turnover_cost"
    )


def test_generated_spec_uses_valid_research_strict_acquisition_tier() -> None:
    candidate = {
        "candidate_id": "CAL01",
        "method_variant": "turn_of_month_window",
        "factor_variant": "last_one_and_first_three_exchange_sessions",
        "hypothesis_id": "H6_CALENDAR_FLOW",
        "branch_id": "B6_CALENDAR_FLOW",
        "archive_descriptors": {"mechanism_family": "calendar_boundary_flow"},
        "promotion_eligible": True,
    }

    spec = StrategySpec.model_validate(
        _build_spec(
            iter_id="mom_breadth_calendar_flow_r1",
            branch=BRANCHES["mom_breadth_calendar_flow_r1"],
            candidate=candidate,
        )
    )

    assert spec.data_assumptions.acquisition_tier == "research_strict"
    assert spec.data_assumptions.model_extra["derived_development_slice"] is True


def test_benchmark_family_uses_full_universe_buy_and_hold_and_cost_views() -> None:
    sessions = pd.bdate_range("2020-12-31", periods=3)
    branch_panel = PricePanel(
        opens=pd.DataFrame(
            {
                "QQQ": [100.0, 200.0, 300.0],
                "BIL": [100.0, 100.0, 100.0],
            },
            index=sessions,
        ),
        closes=pd.DataFrame(
            {"QQQ": [100.0] * 3, "BIL": [100.0] * 3},
            index=sessions,
        ),
        volumes=pd.DataFrame(
            {"QQQ": [1.0] * 3, "BIL": [1.0] * 3},
            index=sessions,
        ),
    )
    benchmark_sessions = pd.DatetimeIndex([pd.Timestamp("2019-12-31"), *sessions])
    benchmark_panel = PricePanel(
        opens=pd.DataFrame(
            {
                symbol: [100.0] * len(benchmark_sessions)
                for symbol in ("SPY", "QQQ", "XLK", "BIL", "TQQQ")
            },
            index=benchmark_sessions,
        ),
        closes=pd.DataFrame(
            {
                symbol: [100.0] * len(benchmark_sessions)
                for symbol in ("SPY", "QQQ", "XLK", "BIL", "TQQQ")
            },
            index=benchmark_sessions,
        ),
        volumes=pd.DataFrame(
            {
                symbol: [1.0] * len(benchmark_sessions)
                for symbol in ("SPY", "QQQ", "XLK", "BIL", "TQQQ")
            },
            index=benchmark_sessions,
        ),
    )

    result = _benchmark_family(
        benchmark_panel,
        branch_panel,
        primary_symbol="QQQ",
        index=sessions[1:],
    )

    expected = pd.Series([0.5, 1.0 / 3.0], index=sessions[1:])
    assert set(result.returns_by_cost) == {10, 20, 40}
    for cost_bps in (10, 20, 40):
        pd.testing.assert_series_equal(
            result.returns_by_cost[cost_bps]["equal_weight_universe"],
            expected,
            check_names=False,
            check_exact=False,
            rtol=1e-12,
        )
    assert result.initialization_session_by_stream["SPY_buy_hold"] == "2019-12-31"
    assert result.initialization_session_by_stream["equal_weight_universe"] == "2020-12-31"
    assert result.initial_one_way_turnover == pytest.approx(1.0)
    assert result.initial_wealth_by_cost == pytest.approx({10: 0.999, 20: 0.998, 40: 0.996})
    assert result.roles["ex_post_best_symbol"] == "QQQ_ex_post_best"
    for streams in result.returns_by_cost.values():
        assert all(stream.index.equals(sessions[1:]) for stream in streams.values())


def _flat_benchmark_panel(sessions: pd.DatetimeIndex) -> PricePanel:
    values = pd.DataFrame(
        {symbol: [100.0] * len(sessions) for symbol in ("SPY", "QQQ", "XLK", "BIL", "TQQQ")},
        index=sessions,
    )
    return PricePanel(opens=values, closes=values, volumes=values)


def test_benchmark_family_can_report_bil_as_ex_post_best() -> None:
    sessions = pd.bdate_range("2020-12-31", periods=3)
    opens = pd.DataFrame(
        {"QQQ": [100.0, 80.0, 70.0], "BIL": [100.0, 100.0, 100.0]},
        index=sessions,
    )
    branch_panel = PricePanel(opens=opens, closes=opens, volumes=opens)

    result = _benchmark_family(
        _flat_benchmark_panel(sessions),
        branch_panel,
        primary_symbol="QQQ",
        index=sessions[1:],
    )

    assert result.roles["ex_post_best_symbol"] == "BIL_ex_post_best"


def test_benchmark_family_rejects_missing_same_symbol() -> None:
    sessions = pd.bdate_range("2020-12-31", periods=3)
    opens = pd.DataFrame({"BIL": [100.0] * 3}, index=sessions)
    branch_panel = PricePanel(opens=opens, closes=opens, volumes=opens)

    with pytest.raises(ValueError, match="same-symbol benchmark"):
        _benchmark_family(
            _flat_benchmark_panel(sessions),
            branch_panel,
            primary_symbol="QQQ",
            index=sessions[1:],
        )


def test_benchmark_family_requires_initialization_before_validation() -> None:
    sessions = pd.bdate_range("2021-01-04", periods=3)
    branch_panel = _flat_benchmark_panel(sessions)

    with pytest.raises(ValueError, match="initialization must precede validation"):
        _benchmark_family(
            branch_panel,
            branch_panel,
            primary_symbol="QQQ",
            index=sessions,
        )


def _passing_execution_contracts() -> tuple[dict, dict, dict]:
    label = {
        "portfolio_return": GENERATED_PORTFOLIO_RETURN_IDENTITY,
        "terminal_liquidation_included": False,
        "model_training": False,
    }
    cost = {
        "cost_views": [
            {"name": "low", "one_way_bps": 10},
            {"name": "primary", "one_way_bps": 20},
            {"name": "severe", "one_way_bps": 40},
        ],
        "primary_one_way_bps": 20,
        "cost_applied_to": "one_way_notional_turnover_at_next_regular_open",
        "terminal_rejoin_cost_included": False,
    }
    benchmark = {
        "required": list(BENCHMARK_FAMILY_IDS),
        "same_sessions": True,
        "same_cost_views": True,
        "cost_views_bps": [10, 20, 40],
        "primary_one_way_bps": 20,
        "cost_applied_to": "initial_notional_at_first_available_development_open",
        "initialization_precedes_validation": True,
        "allocation": "fixed_initial_notional_buy_and_hold_no_rebalance",
        "terminal_liquidation_included": False,
        "validation_return_cost_note": (
            "initialization_cost_precedes_validation_so_validation_daily_returns_are_cost_invariant"
        ),
        "equal_weight_symbols": ["QQQ", "BIL"],
        "ex_post_best_symbols": ["QQQ", "BIL"],
        "ex_post_best_symbol_selectable": False,
        "cash_proxy_symbol": "BIL",
        "market_proxy_symbol": "SPY",
        "growth_proxy_symbol": "QQQ",
        "sector_theme_proxy_symbol": "XLK",
        "leveraged_growth_proxy_symbol": "TQQQ",
    }
    return label, cost, benchmark


@pytest.mark.parametrize(
    ("contract_name", "field", "invalid"),
    [
        ("label", "portfolio_return", "log_return"),
        ("cost", "primary_one_way_bps", 10),
        ("benchmark", "cost_views_bps", [20]),
        ("benchmark", "equal_weight_symbols", ["QQQ"]),
        ("benchmark", "allocation", "daily_rebalanced"),
    ],
)
def test_execution_contract_identity_mutations_fail_closed(
    contract_name: str,
    field: str,
    invalid: object,
) -> None:
    label, cost, benchmark = _passing_execution_contracts()
    selected = {"label": label, "cost": cost, "benchmark": benchmark}[contract_name]
    selected[field] = invalid

    with pytest.raises(ValueError, match=f"{contract_name} contract"):
        _validate_iteration_contract_identities(
            iter_id="child",
            label_contract=label,
            cost_contract=cost,
            benchmark_contract=benchmark,
            expected_symbols=("QQQ", "BIL"),
        )


def test_passing_execution_contract_identity_is_accepted() -> None:
    label, cost, benchmark = _passing_execution_contracts()

    _validate_iteration_contract_identities(
        iter_id="child",
        label_contract=label,
        cost_contract=cost,
        benchmark_contract=benchmark,
        expected_symbols=("QQQ", "BIL"),
    )


def test_candidate_metrics_consume_primary_twenty_bps_benchmarks(monkeypatch) -> None:
    sessions = pd.bdate_range("2021-01-04", periods=8)
    candidate_returns = {
        cost: pd.Series(np.linspace(0.001, 0.008, len(sessions)) - cost / 1_000_000, index=sessions)
        for cost in (10, 20, 40)
    }
    simulations = {
        cost: SimulationResult(
            returns=returns,
            turnover=pd.Series(0.0, index=sessions),
            signal_rows=(),
        )
        for cost, returns in candidate_returns.items()
    }
    streams_by_cost = {
        cost: {
            "BIL": pd.Series(cost / 1_000_000, index=sessions),
            "QQQ": pd.Series(cost / 100_000, index=sessions),
            "TQQQ": pd.Series(cost / 50_000, index=sessions),
        }
        for cost in (10, 20, 40)
    }
    benchmark_family = BenchmarkFamilyResult(
        returns_by_cost=streams_by_cost,
        roles={"cash_proxy": "BIL", "growth_proxy": "QQQ", "leveraged_growth_proxy": "TQQQ"},
        initialization_session_by_stream={
            "BIL": "2020-12-31",
            "QQQ": "2020-12-31",
            "TQQQ": "2020-12-31",
        },
        initial_one_way_turnover=1.0,
        initial_wealth_by_cost={10: 0.999, 20: 0.998, 40: 0.996},
    )
    captured: dict[str, object] = {}

    def fake_promotion_metrics(**kwargs):
        captured["qqq_returns"] = kwargs["qqq_returns"]
        captured["tqqq_returns"] = kwargs["tqqq_returns"]
        return {
            "cagr": 1.0,
            "cagr_excess_qqq": 1.0,
            "tqqq_cagr_capture": 1.0,
            "tqqq_upside_capture": 1.0,
            "tqqq_downside_capture": 0.0,
            "max_drawdown": 0.0,
            "mar": 1.0,
            "positive_fold_count": 4,
            "stress_total_return": 1.0,
        }

    sharpe_inputs: list[pd.Series] = []

    def fake_sharpe(values: pd.Series) -> float:
        sharpe_inputs.append(values.copy())
        return 2.0

    monkeypatch.setattr(
        breadth_runner, "recompute_candidate_promotion_metrics", fake_promotion_metrics
    )
    monkeypatch.setattr(breadth_runner, "_safe_sharpe", fake_sharpe)
    monkeypatch.setattr(breadth_runner, "deflated_sharpe_probability", lambda *args, **kwargs: 1.0)
    contract = SimpleNamespace(
        candidate_promotion_policy=SimpleNamespace(
            annualization_sessions=252,
            cagr_minimum=0.0,
            cagr_excess_qqq_minimum=0.0,
            tqqq_cagr_capture_minimum=0.0,
            tqqq_upside_capture_minimum=0.0,
            tqqq_downside_capture_maximum=1.0,
            max_drawdown_minimum=-1.0,
            mar_minimum=0.0,
            minimum_positive_folds=1,
            stress_total_return_minimum=0.0,
        ),
        statistical_family_policy=SimpleNamespace(
            primary_sharpe_minimum=1.0,
            primary_sharpe_operator=">",
            dsr_minimum=0.0,
            dsr_hac_lag=1,
        ),
        qd_archive=SimpleNamespace(quality_metric="development_worst_fold_sharpe_excess_bil_20bps"),
    )
    fold_contract = {
        "folds": [
            {
                "fold_id": f"D{offset + 1}",
                "start_session": sessions[offset * 2].date().isoformat(),
                "end_session": sessions[offset * 2 + 1].date().isoformat(),
            }
            for offset in range(4)
        ]
    }

    metrics = breadth_runner._candidate_metrics(
        contract,
        result_by_cost=simulations,
        benchmark_family=benchmark_family,
        fold_contract=fold_contract,
        effective_trial_count=8195,
    )

    assert captured["qqq_returns"] == streams_by_cost[20]["QQQ"].to_list()
    assert captured["tqqq_returns"] == streams_by_cost[20]["TQQQ"].to_list()
    pd.testing.assert_series_equal(
        sharpe_inputs[0],
        candidate_returns[20] - streams_by_cost[20]["BIL"],
    )
    assert all(row["primary_cost_bps"] == 20 for row in metrics["benchmark_metrics"].values())
    assert all(
        set(row["cost_views"]) == {"10", "20", "40"}
        for row in metrics["benchmark_metrics"].values()
    )


def test_calendar_window_uses_exchange_session_positions() -> None:
    sessions = pd.DatetimeIndex(us_equity_session_dates(date(2023, 3, 1), date(2023, 4, 28)))

    active = [
        sessions[position].date().isoformat()
        for position in range(len(sessions))
        if _calendar_window_active(
            sessions,
            position,
            {"relative_month_session_offsets": [-1, 0, 1, 2]},
        )
    ]

    assert active == [
        "2023-03-01",
        "2023-03-02",
        "2023-03-03",
        "2023-03-31",
        "2023-04-03",
        "2023-04-04",
        "2023-04-05",
        "2023-04-28",
    ]
    assert pd.Timestamp("2023-04-07") not in sessions


def _calendar_artifact_payload(tmp_path: Path) -> tuple[dict, dict[str, str]]:
    implementation_source = Path(breadth_runner.__file__).parents[1] / "market_calendar.py"
    implementation_path = tmp_path / "open_composer/market_calendar.py"
    implementation_path.parent.mkdir(parents=True)
    implementation_path.write_bytes(implementation_source.read_bytes())
    sessions = [
        value.isoformat() for value in us_equity_session_dates(date(2017, 2, 1), date(2023, 12, 29))
    ]
    sessions_sha256 = hashlib.sha256(
        json.dumps(sessions, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    payload = {
        "schema_version": 1,
        "artifact_type": "us_equity_daily_session_calendar_v1",
        "campaign_id": "mom_breadth_qd_r1",
        "calendar_id": "XNYS",
        "timezone": "America/New_York",
        "session_label": "exchange_local_date",
        "session_scope": "regular",
        "ruleset_id": "open_composer_us_equity_calendar_v1",
        "ruleset_implementation_path": "open_composer/market_calendar.py",
        "ruleset_implementation_sha256": hashlib.sha256(
            implementation_path.read_bytes()
        ).hexdigest(),
        "requested_start": "2017-02-01",
        "requested_end": "2023-12-29",
        "first_session": sessions[0],
        "last_session": sessions[-1],
        "session_count": len(sessions),
        "sessions": sessions,
        "sessions_sha256": sessions_sha256,
        "derived_from_price_data": False,
        "protected_partitions_included": False,
        "source_card_claim_id": "breadth_qd_nyse_session_calendar",
    }
    path = tmp_path / breadth_runner.EXCHANGE_CALENDAR_PATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii")
    binding = {
        "path": breadth_runner.EXCHANGE_CALENDAR_PATH.as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    return payload, binding


def test_development_session_calendar_artifact_round_trips(tmp_path: Path) -> None:
    _, binding = _calendar_artifact_payload(tmp_path)

    sessions = _load_development_session_calendar(tmp_path, binding)

    assert sessions[0] == pd.Timestamp("2017-02-01")
    assert sessions[-1] == pd.Timestamp("2023-12-29")
    assert len(sessions) == 1740


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "out_of_order", "holiday_injection", "count_drift", "sha_drift"],
)
def test_development_session_calendar_artifact_mutations_fail_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    payload, _ = _calendar_artifact_payload(tmp_path)
    sessions = list(payload["sessions"])
    if mutation == "duplicate":
        sessions.insert(10, sessions[10])
    elif mutation == "out_of_order":
        sessions[10], sessions[11] = sessions[11], sessions[10]
    elif mutation == "holiday_injection":
        sessions.append("2023-04-07")
        sessions.sort()
    elif mutation == "count_drift":
        payload["session_count"] += 1
    elif mutation == "sha_drift":
        payload["sessions_sha256"] = "0" * 64
    if mutation in {"duplicate", "out_of_order", "holiday_injection"}:
        payload["sessions"] = sessions
        payload["session_count"] = len(sessions)
        payload["first_session"] = sessions[0]
        payload["last_session"] = sessions[-1]
        payload["sessions_sha256"] = hashlib.sha256(
            json.dumps(sessions, sort_keys=True, separators=(",", ":")).encode("ascii")
        ).hexdigest()
    path = tmp_path / breadth_runner.EXCHANGE_CALENDAR_PATH
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii")
    binding = {
        "path": breadth_runner.EXCHANGE_CALENDAR_PATH.as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }

    with pytest.raises(ValueError, match="exchange calendar"):
        _load_development_session_calendar(tmp_path, binding)


@pytest.mark.parametrize(
    "mutation", ["missing_month_end", "single_symbol_missing", "extra_good_friday"]
)
def test_price_panel_requires_exact_locked_exchange_sessions(mutation: str) -> None:
    expected = pd.DatetimeIndex(us_equity_session_dates(date(2023, 3, 27), date(2023, 4, 10)))
    actual = expected
    if mutation in {"missing_month_end", "single_symbol_missing"}:
        actual = actual[actual != pd.Timestamp("2023-03-31")]
    else:
        actual = actual.union(pd.DatetimeIndex([pd.Timestamp("2023-04-07")])).sort_values()
    frames = {
        symbol: pd.DataFrame(
            {"open": 100.0, "close": 100.0, "volume": 1_000.0},
            index=(expected if mutation == "single_symbol_missing" and symbol == "BIL" else actual),
        )
        for symbol in ("BIL", "QQQ")
    }

    with pytest.raises(ValueError, match="exactly cover locked exchange sessions"):
        _panel_from_symbol_frames(
            frames,
            start=date(2023, 3, 27),
            end=date(2023, 4, 10),
            expected_sessions=expected,
        )


def test_target_schedule_rejects_price_derived_calendar_drift(
    synthetic_panel: PricePanel,
) -> None:
    with pytest.raises(ValueError, match="locked exchange sessions"):
        build_target_schedule(
            CANDIDATE_POLICIES["CAL01"],
            synthetic_panel,
            exchange_sessions=synthetic_panel.index[:-1],
        )


@pytest.mark.parametrize(
    "candidate_id",
    sorted(
        candidate_id for candidate_id in CANDIDATE_POLICIES if not candidate_id.startswith("PIT")
    ),
)
def test_all_executable_candidate_policies_build_finite_synthetic_targets(
    candidate_id: str,
    synthetic_panel: PricePanel,
) -> None:
    panel = synthetic_panel

    schedule = build_target_schedule(
        CANDIDATE_POLICIES[candidate_id],
        panel,
        exchange_sessions=panel.index,
    )

    assert schedule
    for weights in schedule.values():
        assert sum(weights.values()) == pytest.approx(1.0)
        assert all(np.isfinite(value) and value >= 0.0 for value in weights.values())


@pytest.mark.parametrize("candidate_id", ["PIT01", "PIT02", "PIT03"])
def test_pit_candidates_fail_closed_without_declared_dependency(
    candidate_id: str,
    synthetic_panel: PricePanel,
) -> None:
    with pytest.raises(ValueError, match="PIT stock policies"):
        build_target_schedule(
            CANDIDATE_POLICIES[candidate_id],
            synthetic_panel,
            exchange_sessions=synthetic_panel.index,
        )


def test_development_csv_slice_stops_before_future_bytes(tmp_path: Path) -> None:
    source = tmp_path / "prices.csv"
    source.write_bytes(
        b"timestamp,open,high,low,close,volume\n"
        b"2017-02-01 05:00:00+00:00,1,1,1,1,1\n"
        b"2023-12-29 05:00:00+00:00,2,2,2,2,2\n"
        b"this future row must never be parsed\n"
    )

    payload, metadata = _bounded_development_csv(source)

    assert b"future" not in payload
    assert metadata["row_count"] == 2
    assert metadata["last_session"] == "2023-12-29"


def test_development_csv_slice_rejects_late_start(tmp_path: Path) -> None:
    source = tmp_path / "prices.csv"
    source.write_bytes(
        b"timestamp,open,high,low,close,volume\n"
        b"2017-02-02 05:00:00+00:00,1,1,1,1,1\n"
        b"2023-12-29 05:00:00+00:00,2,2,2,2,2\n"
    )

    with pytest.raises(ValueError, match="incomplete declared bounds"):
        _bounded_development_csv(source)


def test_runtime_price_reader_stops_exactly_at_development_end(tmp_path: Path) -> None:
    source = tmp_path / "prices.csv"
    source.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2017-02-01 05:00:00+00:00,1,1,1,1,1\n"
        "2023-12-29 05:00:00+00:00,2,2,2,2,2\n"
        "not-a-timestamp,secret,secret,secret,secret,secret\n",
        encoding="ascii",
    )

    frame = _read_price_csv_until(source, end=date(2023, 12, 29))

    assert list(frame.index) == [pd.Timestamp("2017-02-01"), pd.Timestamp("2023-12-29")]


def test_development_effective_trial_count_uses_actual_cost_view_exposure() -> None:
    contract = SimpleNamespace(
        exposure_budgets=SimpleNamespace(
            prior_effective_trial_count=8147,
            candidate_budget=19,
            cumulative_trial_exposure_budget=57,
        )
    )

    assert _development_effective_trial_count(contract, evaluated_candidate_count=16) == 8195


def test_max_drawdown_includes_initial_wealth_peak() -> None:
    returns = pd.Series([-0.5, 1.0])

    assert _max_drawdown(returns) == pytest.approx(-0.5)


@pytest.mark.parametrize(
    ("actual", "precomputed", "raises"),
    [(8195, 8195, False), (8194, 8195, True), (8195, 8194, True)],
)
def test_development_ledger_count_must_equal_precomputed_8195(
    monkeypatch: pytest.MonkeyPatch,
    actual: int,
    precomputed: int,
    raises: bool,
) -> None:
    monkeypatch.setattr(
        breadth_runner,
        "effective_trial_count_from_ledger",
        lambda *_: actual,
    )
    if raises:
        with pytest.raises(ValueError, match="must equal 8195"):
            _verify_ledger_effective_trial_count(
                SimpleNamespace(),
                SimpleNamespace(),
                precomputed_effective_trial_count=precomputed,
            )
    else:
        assert (
            _verify_ledger_effective_trial_count(
                SimpleNamespace(),
                SimpleNamespace(),
                precomputed_effective_trial_count=precomputed,
            )
            == 8195
        )


def test_development_dsr_is_an_individual_advance_gate() -> None:
    contract = SimpleNamespace(
        candidate_promotion_policy=SimpleNamespace(
            cagr_minimum=0.45,
            cagr_excess_qqq_minimum=0.08,
            tqqq_cagr_capture_minimum=0.85,
            tqqq_upside_capture_minimum=0.85,
            tqqq_downside_capture_maximum=0.90,
            max_drawdown_minimum=-0.65,
            mar_minimum=0.40,
            minimum_positive_folds=3,
            stress_total_return_minimum=0.0,
        ),
        statistical_family_policy=SimpleNamespace(
            primary_sharpe_minimum=1.0,
            primary_sharpe_operator=">",
            dsr_minimum=0.75,
        ),
    )
    metrics = {
        "cagr": 0.46,
        "cagr_excess_qqq": 0.09,
        "tqqq_cagr_capture": 0.86,
        "tqqq_upside_capture": 0.86,
        "tqqq_downside_capture": 0.89,
        "max_drawdown": -0.60,
        "mar": 0.50,
        "positive_fold_count": 3,
        "stress_total_return": 0.01,
    }

    assert _promotion_passes(metrics, 1.01, 0.74, contract)["dsr_probability"] is False
    assert _promotion_passes(metrics, 1.01, 0.75, contract)["dsr_probability"] is True

    contract.statistical_family_policy.primary_sharpe_minimum = 1.01
    assert _promotion_passes(metrics, 1.01, 0.75, contract)["sharpe_excess_bil"] is False
    assert _promotion_passes(metrics, 1.02, 0.75, contract)["sharpe_excess_bil"] is True


@pytest.mark.parametrize(
    ("right", "threshold", "expected"),
    [
        ([0.0, 1.0, 1.0, 2.0, 1.0], 0.70, True),
        ([0.0, 0.0, 1.0, 1.0, 2.0], 0.70, False),
        ([0.0, 1.0, 1.0, 2.0, 1.0], 0.60, False),
    ],
)
def test_advancing_pair_correlation_uses_locked_policy(
    right: list[float],
    threshold: float,
    expected: bool,
) -> None:
    policy = SimpleNamespace(
        method="pearson",
        return_stream="development_validation_continuous_daily_primary_20bps_terminal_free",
        absolute_maximum=threshold,
        operator="<=",
        minimum_passing_pair_count=1,
    )
    contract = SimpleNamespace(
        statistical_family_policy=SimpleNamespace(advancing_pair_correlation=policy)
    )

    diagnostic = _advancing_pair_correlation_diagnostic(
        contract,
        {
            "A": pd.Series([0.0, 1.0, 2.0, 3.0, 4.0]),
            "B": pd.Series(right),
        },
    )

    assert diagnostic["pass"] is expected
    assert diagnostic["policy"]["absolute_maximum"] == threshold
    assert diagnostic["policy"]["method"] == "pearson"


def _artifact_binding(root: Path, relative: Path, content: str) -> dict[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="ascii")
    return {"path": relative.as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_runtime_lock_verifies_every_immutable_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    implementation_path = Path("impl.py")
    amendment_path = Path("amendment.json")
    calendar_path = Path("calendar.json")
    monkeypatch.setattr(
        breadth_runner,
        "LOCKED_IMPLEMENTATION_PATHS",
        {"implementation": implementation_path},
    )
    monkeypatch.setattr(breadth_runner, "INTEGRITY_AMENDMENT_PATH", amendment_path)
    monkeypatch.setattr(breadth_runner, "EXCHANGE_CALENDAR_PATH", calendar_path)
    inventory = {
        "implementation": _artifact_binding(tmp_path, implementation_path, "implementation\n"),
        "development_integrity_amendment": _artifact_binding(
            tmp_path, amendment_path, "amendment\n"
        ),
        "exchange_calendar_artifact": _artifact_binding(tmp_path, calendar_path, "calendar\n"),
        "extra_locked_evidence": _artifact_binding(tmp_path, Path("extra.json"), "evidence\n"),
    }
    lock_path = tmp_path / ITERATION_ROOT / "child" / "phase-one-preregistration-lock.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        json.dumps(
            {
                "lock_type": "breadth_campaign_phase_one_preregistration_v1",
                "campaign_id": "mom_breadth_qd_r1",
                "iter_id": "child",
                "generated_before_backtest": True,
                "generated_before_model_training": True,
                "frozen_oos_read_authorized": False,
                "broker_writes": False,
                "candidate_ids": ["C01"],
                "candidate_policy_sha256": {"C01": "0" * 64},
                "immutable_inventory": inventory,
            },
            sort_keys=True,
        ),
        encoding="ascii",
    )
    contract = SimpleNamespace(
        child_iteration_ids=("child",),
        candidate_blueprints=(SimpleNamespace(candidate_id="C01", child_iteration_id="child"),),
    )

    assert _verify_runtime_lock_inventory(tmp_path, contract)["child"]["path"].endswith(
        "phase-one-preregistration-lock.json"
    )

    (tmp_path / "extra.json").write_text("drift\n", encoding="ascii")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _verify_runtime_lock_inventory(tmp_path, contract)


def test_skipped_iteration_feasibility_must_bind_current_phase_one_lock(
    tmp_path: Path,
) -> None:
    evidence = _artifact_binding(tmp_path, Path("evidence.json"), "{}\n")
    lock = _artifact_binding(tmp_path, Path("lock.json"), "{}\n")
    feasibility = {
        "required_reference_names": ["evidence", "phase_one_preregistration_lock"],
        "required_references": {
            "evidence": evidence,
            "phase_one_preregistration_lock": lock,
        },
    }

    _verify_feasibility_references(
        tmp_path,
        iter_id="pit",
        feasibility=feasibility,
        phase_one_lock=lock,
    )

    with pytest.raises(ValueError, match="phase-one lock identity"):
        _verify_feasibility_references(
            tmp_path,
            iter_id="pit",
            feasibility=feasibility,
            phase_one_lock={"path": "lock.json", "sha256": "0" * 64},
        )


def test_feasibility_exact_inventory_rejects_coordinated_ordinary_reference_removal(
    tmp_path: Path,
) -> None:
    ordinary = _artifact_binding(tmp_path, Path("market.json"), "{}\n")
    lock = _artifact_binding(tmp_path, Path("lock.json"), "{}\n")
    expected = {
        "market_data_artifact_1": ordinary,
        "phase_one_preregistration_lock": lock,
    }
    feasibility = {
        "required_reference_names": sorted(expected),
        "required_references": expected,
    }
    _verify_feasibility_references(
        tmp_path,
        iter_id="fresh_preflight",
        feasibility=feasibility,
        phase_one_lock=lock,
        expected_references=expected,
    )

    coordinated = json.loads(json.dumps(feasibility))
    coordinated["required_references"].pop("market_data_artifact_1")
    coordinated["required_reference_names"].remove("market_data_artifact_1")
    with pytest.raises(ValueError, match="exact reference inventory"):
        _verify_feasibility_references(
            tmp_path,
            iter_id="fresh_preflight",
            feasibility=coordinated,
            phase_one_lock=lock,
            expected_references=expected,
        )


@pytest.mark.parametrize(
    ("blocked", "raises"),
    [
        (["search_space_data_feasibility_not_authorized"], False),
        (
            [
                "search_space_data_feasibility_not_authorized",
                "candidate_manifest_phase_one_lock_sha256_mismatch",
            ],
            True,
        ),
        ([], True),
    ],
)
def test_dependency_skipped_iteration_allows_only_expected_dossier_blocker(
    monkeypatch: pytest.MonkeyPatch,
    blocked: list[str],
    raises: bool,
) -> None:
    monkeypatch.setattr(
        breadth_runner,
        "validate_iteration_dossier",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="blocked" if blocked else "ok",
            blocked=blocked,
        ),
    )
    if raises:
        with pytest.raises(ValueError, match="unexpected blockers"):
            _validate_dependency_skipped_iteration_gate("pit", Path("."))
    else:
        _validate_dependency_skipped_iteration_gate("pit", Path("."))


def test_attempt_or_staging_state_blocks_one_shot_rerun(tmp_path: Path) -> None:
    contract = SimpleNamespace(child_iteration_ids=("child",))
    attempt = tmp_path / DEVELOPMENT_ATTEMPT_PATH
    attempt.parent.mkdir(parents=True)
    attempt.write_text("{}\n", encoding="ascii")

    with pytest.raises(FileExistsError, match="one-shot"):
        _assert_pristine_publication_state(tmp_path, contract)


def test_staged_publication_finishes_with_campaign_receipt(tmp_path: Path) -> None:
    branch_parent = tmp_path / ITERATION_ROOT / "child"
    branch_parent.mkdir(parents=True)
    branch_staging = branch_parent / "evaluation-run.staging-test"
    branch_staging.mkdir()
    (branch_staging / "evaluation-report.json").write_text("{}\n", encoding="ascii")
    campaign_parent = tmp_path / CAMPAIGN_ROOT
    campaign_parent.mkdir(parents=True)
    campaign_staging = campaign_parent / "development-evaluation.staging-test"
    campaign_staging.mkdir()
    for name in (
        "qd-archive.json",
        "allocation-ledger.jsonl",
        "development-evaluation-report.json",
        DEVELOPMENT_RECEIPT_PATH.name,
    ):
        (campaign_staging / name).write_text("{}\n", encoding="ascii")

    _publish_staged_outputs(
        root=tmp_path,
        branch_staging={"child": branch_staging},
        campaign_staging=campaign_staging,
    )

    assert (branch_parent / "evaluation-run/evaluation-report.json").is_file()
    assert (tmp_path / DEVELOPMENT_RECEIPT_PATH).is_file()
    assert not campaign_staging.exists()


@pytest.mark.parametrize(
    "fail_after_move",
    [
        pytest.param(1, id="branch_moved_to_final"),
        pytest.param(2, id="qd_archive_moved_to_final"),
        pytest.param(3, id="allocation_ledger_moved_to_final"),
        pytest.param(4, id="report_final_receipt_still_staged"),
        pytest.param(5, id="receipt_final_empty_staging_remains"),
    ],
)
def test_staged_publication_is_retryable_after_every_atomic_move(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_after_move: int,
) -> None:
    branch_parent = tmp_path / ITERATION_ROOT / "child"
    branch_parent.mkdir(parents=True)
    branch_staging = branch_parent / "evaluation-run.staging-test"
    branch_staging.mkdir()
    _write_recovery_json(branch_staging / "evaluation-report.json", {"branch": "child"})
    campaign_staging = tmp_path / CAMPAIGN_ROOT / "development-evaluation.staging-test"
    campaign_staging.mkdir(parents=True)
    _write_recovery_json(campaign_staging / "qd-archive.json", {"archive": "sealed"})
    _write_recovery_jsonl(
        campaign_staging / "allocation-ledger.jsonl",
        [{"candidate_id": "SYN01", "decision": "stop"}],
    )
    _write_recovery_json(
        campaign_staging / "development-evaluation-report.json",
        {"development_pre_oos_ready": False},
    )
    _write_recovery_json(
        campaign_staging / DEVELOPMENT_RECEIPT_PATH.name,
        {"completion_marker": True},
    )
    final_branch = branch_parent / "evaluation-run"
    publication_files = [
        {
            "path": (final_branch / "evaluation-report.json").relative_to(tmp_path).as_posix(),
            "sha256": hashlib.sha256(
                (branch_staging / "evaluation-report.json").read_bytes()
            ).hexdigest(),
        }
    ]
    for name in (
        "qd-archive.json",
        "allocation-ledger.jsonl",
        "development-evaluation-report.json",
    ):
        publication_files.append(
            {
                "path": (tmp_path / CAMPAIGN_ROOT / name).relative_to(tmp_path).as_posix(),
                "sha256": hashlib.sha256((campaign_staging / name).read_bytes()).hexdigest(),
            }
        )

    original_move = breadth_runner._move_publication_path
    move_count = 0

    def move_then_interrupt(path: Path, target: Path) -> None:
        nonlocal move_count
        original_move(path, target)
        move_count += 1
        if move_count == fail_after_move:
            raise RuntimeError("synthetic post-move interruption")

    with monkeypatch.context() as scoped:
        scoped.setattr(breadth_runner, "_move_publication_path", move_then_interrupt)
        with pytest.raises(RuntimeError, match="post-move interruption"):
            _publish_staged_outputs(
                root=tmp_path,
                branch_staging={"child": branch_staging},
                campaign_staging=campaign_staging,
                publication_files=publication_files,
            )

    assert final_branch.is_dir()
    campaign_names = (
        "qd-archive.json",
        "allocation-ledger.jsonl",
        "development-evaluation-report.json",
    )
    moved_campaign_count = min(max(fail_after_move - 1, 0), len(campaign_names))
    for offset, name in enumerate(campaign_names):
        final_path = tmp_path / CAMPAIGN_ROOT / name
        staged_path = campaign_staging / name
        assert final_path.is_file() is (offset < moved_campaign_count)
        assert staged_path.is_file() is (offset >= moved_campaign_count)
    receipt_final = tmp_path / DEVELOPMENT_RECEIPT_PATH
    receipt_staged = campaign_staging / DEVELOPMENT_RECEIPT_PATH.name
    assert receipt_final.is_file() is (fail_after_move == 5)
    assert receipt_staged.is_file() is (fail_after_move < 5)
    assert campaign_staging.is_dir()
    if fail_after_move == 5:
        assert not any(campaign_staging.iterdir())

    _publish_staged_outputs(
        root=tmp_path,
        branch_staging={"child": branch_staging},
        campaign_staging=campaign_staging,
        publication_files=publication_files,
    )

    assert final_branch.is_dir()
    assert all((tmp_path / CAMPAIGN_ROOT / name).is_file() for name in campaign_names)
    assert receipt_final.is_file()
    assert not campaign_staging.exists()
    for binding in publication_files:
        path = tmp_path / binding["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]


def _write_recovery_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )


def _write_recovery_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="ascii",
    )


def _recovery_signal_row(
    *,
    decision_session: str = "2021-01-04",
    execution_session: str = "2021-01-05",
    target_weights: dict[str, float] | None = None,
    one_way_turnover: float = 0.0,
) -> dict:
    row = {
        "schema_version": 1,
        "execution_session": execution_session,
        "decision_session": decision_session,
        "target_weights": target_weights or {"BIL": 1.0},
        "one_way_turnover": one_way_turnover,
        "broker_writes": False,
    }
    row["signal_id"] = breadth_runner._canonical_sha256(row)
    return row


@pytest.fixture
def synthetic_staged_recovery(tmp_path: Path) -> dict[str, object]:
    run_token = "a" * 32
    evaluated_iter_id = "synthetic_evaluated_branch"
    skipped_iter_id = "synthetic_dependency_skipped_branch"
    evaluated_id = "SYN01"
    skipped_id = "SKIP01"
    quality_metric = "development_worst_fold_sharpe_excess_bil_20bps"
    blueprints = (
        SimpleNamespace(
            candidate_id=evaluated_id,
            child_iteration_id=evaluated_iter_id,
            hypothesis_id="H_SYNTHETIC",
            branch_id="B_SYNTHETIC",
            archive_descriptors={"mechanism_family": "synthetic_evaluated"},
            promotion_eligible=True,
        ),
        SimpleNamespace(
            candidate_id=skipped_id,
            child_iteration_id=skipped_iter_id,
            hypothesis_id="H_SKIPPED",
            branch_id="B_SKIPPED",
            archive_descriptors={"mechanism_family": "synthetic_skipped"},
            promotion_eligible=True,
        ),
    )
    contract = SimpleNamespace(
        child_iteration_ids=(evaluated_iter_id, skipped_iter_id),
        candidate_blueprints=blueprints,
        qd_archive=SimpleNamespace(quality_metric=quality_metric),
    )

    calendar, calendar_binding = _calendar_artifact_payload(tmp_path)
    lock_path = tmp_path / ITERATION_ROOT / evaluated_iter_id / "phase-one-lock.json"
    _write_recovery_json(
        lock_path,
        {"immutable_inventory": {"exchange_calendar_artifact": calendar_binding}},
    )
    lock_binding = {
        "path": lock_path.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
    }
    attempt = {
        "registered_candidate_count": 2,
        "evaluated_candidate_count": 1,
        "incremental_effective_trial_count": 3,
        "effective_trial_count": 8195,
        "phase_one_locks": {
            evaluated_iter_id: lock_binding,
            skipped_iter_id: lock_binding,
        },
    }
    attempt_path = tmp_path / DEVELOPMENT_ATTEMPT_PATH
    _write_recovery_json(attempt_path, attempt)
    attempt_binding = {
        "path": DEVELOPMENT_ATTEMPT_PATH.as_posix(),
        "sha256": hashlib.sha256(attempt_path.read_bytes()).hexdigest(),
    }

    evaluated_iteration = tmp_path / ITERATION_ROOT / evaluated_iter_id
    skipped_iteration = tmp_path / ITERATION_ROOT / skipped_iter_id
    evaluated_spec_path = "strategy_specs/drafts/synthetic_evaluated.yaml"
    spec_path = tmp_path / evaluated_spec_path
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(
        (
            Path(__file__).resolve().parents[1]
            / "strategy_specs/drafts/us_breadth_calendar_flow_r1_cal01.yaml"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    _write_recovery_json(
        evaluated_iteration / "candidate-manifest.json",
        {"candidates": [{"candidate_id": evaluated_id, "spec_path": evaluated_spec_path}]},
    )
    _write_recovery_json(
        evaluated_iteration / "data-feasibility.json",
        {"historical_evaluation_authorized": True},
    )
    _write_recovery_json(
        evaluated_iteration / "development-partition-contract.json",
        {"partition_id": "development_validation"},
    )
    _write_recovery_json(
        skipped_iteration / "candidate-manifest.json",
        {"candidates": [{"candidate_id": skipped_id, "spec_path": "skipped.yaml"}]},
    )
    _write_recovery_json(
        skipped_iteration / "data-feasibility.json",
        {"historical_evaluation_authorized": False},
    )

    dates = [
        value.isoformat()
        for value in us_equity_session_dates(
            breadth_runner.VALIDATION_START,
            breadth_runner.VALIDATION_END,
        )
    ]
    values = [0.001 if offset % 2 else -0.0002 for offset in range(len(dates))]
    result_returns = pd.Series(values, index=pd.to_datetime(dates), dtype=float)
    staging = evaluated_iteration / f"evaluation-run.staging-{run_token}"
    staging.mkdir()
    final = evaluated_iteration / "evaluation-run"
    metrics_path = final / f"{evaluated_id}-metrics.json"
    signal_path = final / f"{evaluated_id}-signal-log.jsonl"
    primary_metrics = {
        "cagr": breadth_runner._cagr(result_returns),
        "total_return": breadth_runner._compound(result_returns),
        "max_drawdown": breadth_runner._max_drawdown(result_returns),
    }
    metrics = {
        "schema_version": 1,
        "campaign_id": breadth_runner.CAMPAIGN_ID,
        "iter_id": evaluated_iter_id,
        "candidate_id": evaluated_id,
        "spec_path": evaluated_spec_path,
        "signal_log_path": signal_path.relative_to(tmp_path).as_posix(),
        "visibility_partition": "development_validation",
        "promotion_eligible": True,
        "workflow_pass": True,
        "research_pass": False,
        "paper_ready_pass": False,
        "development_evaluation_attempt": attempt_binding,
        "frozen_oos_rows_read": 0,
        "broker_writes": False,
        "row_count": len(dates),
        "first_return_session": dates[0],
        "last_return_session": dates[-1],
        "terminal_liquidation_in_metrics": False,
        "return_stream_identity": "continuous_daily_open_to_open_net_returns_terminal_free",
        "primary_cost_bps": 20,
        "development_dsr_effective_trial_count": 8195,
        "quality_metric": quality_metric,
        "quality": 0.25,
        "annualized_sharpe_excess_bil": 0.50,
        "development_dsr_probability_diagnostic": 0.25,
        "development_gate_diagnostics": {"sharpe_excess_bil": False},
        "all_development_gate_diagnostics_pass": False,
        "cost_views": {
            "10": {"cagr": 0.0, "total_return": 0.0, "max_drawdown": 0.0},
            "20": primary_metrics,
            "40": {"cagr": 0.0, "total_return": 0.0, "max_drawdown": 0.0},
        },
    }
    metrics_staging_path = staging / metrics_path.name
    _write_recovery_json(metrics_staging_path, metrics)
    metrics_sha256 = hashlib.sha256(metrics_staging_path.read_bytes()).hexdigest()
    _write_recovery_jsonl(staging / signal_path.name, [_recovery_signal_row()])
    trial = breadth_runner._trial_row(
        candidate_id=evaluated_id,
        iter_id=evaluated_iter_id,
        action="evaluate",
        spec_path=evaluated_spec_path,
        metrics_path=metrics_path.relative_to(tmp_path).as_posix(),
        metrics_sha256=metrics_sha256,
        effective_trial_exposure=3.0,
    )
    _write_recovery_jsonl(staging / "trial-ledger.jsonl", [trial])
    _write_recovery_json(
        staging / "development-return-matrix.json",
        {
            "schema_version": 1,
            "campaign_id": breadth_runner.CAMPAIGN_ID,
            "iter_id": evaluated_iter_id,
            "visibility_partition": "development_validation",
            "return_stream_identity": "continuous_daily_open_to_open_net_returns_terminal_free",
            "cost_bps": 20,
            "dates": dates,
            "returns": {evaluated_id: values},
            "frozen_oos_rows_read": 0,
        },
    )
    report = {
        "schema_version": 1,
        "campaign_id": breadth_runner.CAMPAIGN_ID,
        "iter_id": evaluated_iter_id,
        "workflow_pass": True,
        "research_pass": False,
        "paper_ready_pass": False,
        "status": "development_evaluated",
        "candidate_count": 1,
        "evaluated_count": 1,
        "candidates": {evaluated_id: metrics},
        "effective_trial_count": 8195,
        "development_evaluation_attempt": attempt_binding,
        "publication_receipt_required": True,
        "publication_receipt_path": DEVELOPMENT_RECEIPT_PATH.as_posix(),
        "frozen_oos_rows_read": 0,
        "broker_writes": False,
    }
    _write_recovery_json(staging / "evaluation-report.json", report)
    campaign_staging = tmp_path / CAMPAIGN_ROOT / f"development-evaluation.staging-{run_token}"
    campaign_staging.mkdir(parents=True)
    return {
        "root": tmp_path,
        "run_token": run_token,
        "contract": contract,
        "attempt": attempt,
        "attempt_binding": attempt_binding,
        "amendment_binding": {
            "path": "synthetic-recovery-amendment.json",
            "sha256": "f" * 64,
        },
        "staging": staging,
        "manifest_path": evaluated_iteration / "candidate-manifest.json",
        "evaluated_feasibility_path": evaluated_iteration / "data-feasibility.json",
        "skipped_feasibility_path": skipped_iteration / "data-feasibility.json",
        "session_dates": calendar["sessions"],
        "signal_path": staging / signal_path.name,
        "evaluated_id": evaluated_id,
    }


def _load_synthetic_staged_recovery(fixture: dict[str, object]) -> object:
    return breadth_runner._load_validated_staged_results(
        fixture["root"],
        contract=fixture["contract"],
        attempt=fixture["attempt"],
        attempt_binding=fixture["attempt_binding"],
        run_token=fixture["run_token"],
        amendment_binding=fixture["amendment_binding"],
        campaign_contract_sha256="e" * 64,
    )


def test_staged_recovery_reconstructs_only_complete_synthetic_evidence(
    synthetic_staged_recovery: dict[str, object],
) -> None:
    recovered = _load_synthetic_staged_recovery(synthetic_staged_recovery)

    assert [result.candidate_id for result in recovered.evaluated] == ["SYN01"]
    assert recovered.excluded_candidate_ids == ("SKIP01",)
    assert set(recovered.branch_staging) == {"synthetic_evaluated_branch"}
    assert recovered.campaign_staging.name.endswith(str(synthetic_staged_recovery["run_token"]))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_metrics", "staged file inventory"),
        ("tampered_metrics", "trial row mismatch"),
        ("attempt_binding", "candidate metrics identity"),
        ("candidate_inventory", "candidate inventory mismatch"),
        ("date_axis", "return matrix mismatch"),
        ("trial_exposure", "trial row mismatch"),
        ("unexpected_campaign_output", "unexpected files"),
        ("branch_token", "branch staging identity"),
        ("run_token", "campaign staging identity"),
    ],
)
def test_staged_recovery_rejects_incomplete_or_drifted_evidence(
    synthetic_staged_recovery: dict[str, object],
    mutation: str,
    message: str,
) -> None:
    fixture = synthetic_staged_recovery
    staging = fixture["staging"]
    evaluated_id = str(fixture["evaluated_id"])
    metrics_path = staging / f"{evaluated_id}-metrics.json"
    if mutation == "missing_metrics":
        metrics_path.unlink()
    elif mutation == "tampered_metrics":
        metrics = json.loads(metrics_path.read_text(encoding="ascii"))
        metrics["quality"] = 0.26
        _write_recovery_json(metrics_path, metrics)
    elif mutation == "attempt_binding":
        metrics = json.loads(metrics_path.read_text(encoding="ascii"))
        metrics["development_evaluation_attempt"]["sha256"] = "0" * 64
        _write_recovery_json(metrics_path, metrics)
    elif mutation == "candidate_inventory":
        manifest_path = fixture["manifest_path"]
        manifest = json.loads(manifest_path.read_text(encoding="ascii"))
        manifest["candidates"][0]["candidate_id"] = "DRIFT01"
        _write_recovery_json(manifest_path, manifest)
    elif mutation == "date_axis":
        matrix_path = staging / "development-return-matrix.json"
        matrix = json.loads(matrix_path.read_text(encoding="ascii"))
        matrix["dates"][0] = "2021-01-05"
        _write_recovery_json(matrix_path, matrix)
    elif mutation == "trial_exposure":
        trial_path = staging / "trial-ledger.jsonl"
        trial = json.loads(trial_path.read_text(encoding="ascii"))
        trial["effective_trial_exposure"] = 4.0
        _write_recovery_jsonl(trial_path, [trial])
    elif mutation == "unexpected_campaign_output":
        campaign_staging = (
            fixture["root"]
            / CAMPAIGN_ROOT
            / f"development-evaluation.staging-{fixture['run_token']}"
        )
        _write_recovery_json(campaign_staging / "unexpected.json", {})
    elif mutation == "branch_token":
        staging.rename(staging.with_name(f"evaluation-run.staging-{'b' * 32}"))
    elif mutation == "run_token":
        fixture["run_token"] = "b" * 32

    with pytest.raises((FileNotFoundError, ValueError), match=message):
        _load_synthetic_staged_recovery(fixture)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("manifest_not_a_list", "candidate manifest is malformed"),
        ("manifest_candidate_id", "candidate inventory mismatch"),
        ("evaluated_becomes_skipped", "dependency-skipped branch has staged evaluation"),
        ("skipped_becomes_evaluated", "branch staging identity mismatch"),
        ("authorization_missing", "dependency-skipped branch has staged evaluation"),
    ],
)
def test_staged_recovery_rejects_manifest_or_feasibility_semantic_drift(
    synthetic_staged_recovery: dict[str, object],
    mutation: str,
    message: str,
) -> None:
    fixture = synthetic_staged_recovery
    if mutation.startswith("manifest"):
        path = fixture["manifest_path"]
        payload = json.loads(path.read_text(encoding="ascii"))
        if mutation == "manifest_not_a_list":
            payload["candidates"] = {"candidate_id": "SYN01"}
        else:
            payload["candidates"][0]["candidate_id"] = "SYN02"
        _write_recovery_json(path, payload)
    elif mutation == "skipped_becomes_evaluated":
        _write_recovery_json(
            fixture["skipped_feasibility_path"],
            {"historical_evaluation_authorized": True},
        )
    elif mutation == "authorization_missing":
        _write_recovery_json(fixture["evaluated_feasibility_path"], {})
    else:
        _write_recovery_json(
            fixture["evaluated_feasibility_path"],
            {"historical_evaluation_authorized": False},
        )

    with pytest.raises(ValueError, match=message):
        _load_synthetic_staged_recovery(fixture)


@pytest.mark.parametrize(
    "mutation",
    [
        "canonical_signal_id",
        "decision_execution_dates",
        "weight_sum",
        "negative_weight",
        "outside_universe_weight",
        "turnover_below_zero",
        "turnover_above_two",
    ],
)
def test_staged_recovery_signal_log_rejects_semantic_mutations(
    tmp_path: Path,
    mutation: str,
) -> None:
    session_dates = [
        value.isoformat()
        for value in us_equity_session_dates(
            breadth_runner.DEVELOPMENT_START,
            breadth_runner.VALIDATION_END,
        )
    ]
    row = _recovery_signal_row()
    if mutation == "canonical_signal_id":
        row["signal_id"] = "0" * 64
    elif mutation == "decision_execution_dates":
        row["decision_session"] = "2021-01-01"
        row["signal_id"] = breadth_runner._canonical_sha256(
            {key: value for key, value in row.items() if key != "signal_id"}
        )
    elif mutation == "weight_sum":
        row = _recovery_signal_row(target_weights={"BIL": 0.9})
    elif mutation == "negative_weight":
        row = _recovery_signal_row(target_weights={"BIL": 1.1, "QQQ": -0.1})
    elif mutation == "outside_universe_weight":
        row = _recovery_signal_row(target_weights={"BIL": 0.5, "SPY": 0.5})
    elif mutation == "turnover_below_zero":
        row = _recovery_signal_row(one_way_turnover=-0.1)
    else:
        row = _recovery_signal_row(one_way_turnover=2.1)
    path = tmp_path / "signal-log.jsonl"
    _write_recovery_jsonl(path, [row])

    with pytest.raises(ValueError, match="signal log semantic mismatch"):
        breadth_runner._validate_staged_signal_log(
            path,
            session_dates=session_dates,
            allowed_symbols=("BIL", "QQQ"),
        )


def test_staged_recovery_signal_log_accepts_canonical_semantics(tmp_path: Path) -> None:
    session_dates = [
        value.isoformat()
        for value in us_equity_session_dates(
            breadth_runner.DEVELOPMENT_START,
            breadth_runner.VALIDATION_END,
        )
    ]
    path = tmp_path / "signal-log.jsonl"
    _write_recovery_jsonl(path, [_recovery_signal_row()])

    breadth_runner._validate_staged_signal_log(
        path,
        session_dates=session_dates,
        allowed_symbols=("BIL", "QQQ"),
    )


def test_recovery_amendment_inventory_rejects_coordinated_staged_tamper(
    synthetic_staged_recovery: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = synthetic_staged_recovery
    root = fixture["root"]
    contract = fixture["contract"]
    attempt = fixture["attempt"]
    attempt_binding = fixture["attempt_binding"]
    run_token = str(fixture["run_token"])
    implementation_paths = {
        "development_runner": Path("synthetic-runner.py"),
        "development_runner_tests": Path("synthetic-runner-tests.py"),
    }
    for name, path in implementation_paths.items():
        (root / path).write_text(f"{name}\n", encoding="ascii")
    monkeypatch.setattr(breadth_runner, "LOCKED_IMPLEMENTATION_PATHS", implementation_paths)
    prior_implementation = {
        name: {"path": path.as_posix(), "sha256": character * 64}
        for (name, path), character in zip(
            implementation_paths.items(),
            ("a", "b"),
            strict=True,
        )
    }
    attempt["implementation"] = prior_implementation
    repaired_implementation = {
        name: {
            "path": path.as_posix(),
            "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest(),
        }
        for name, path in implementation_paths.items()
    }
    staged_inventory = breadth_runner._staged_evidence_inventory_binding(
        root,
        contract=contract,
        run_token=run_token,
    )
    preregistration_inventory = {
        "algorithm": "synthetic-preregistration-inventory-v1",
        "file_count": 0,
        "sha256": "e" * 64,
    }
    monkeypatch.setattr(
        breadth_runner,
        "_recovery_preregistration_inventory_binding",
        lambda *_args, **_kwargs: preregistration_inventory,
    )
    amendment = {
        "schema_version": 1,
        "campaign_id": breadth_runner.CAMPAIGN_ID,
        "reason": breadth_runner.RECOVERY_AMENDMENT_REASON,
        "failure": {
            "run_token": run_token,
            "attempt": attempt_binding,
            "stage": "campaign_qd_archive_serialization",
            "exception_type": "AttributeError",
            "exception_message": "'QualityDiversityArchive' object has no attribute 'to_dict'",
        },
        "prior_implementation": prior_implementation,
        "repaired_implementation": repaired_implementation,
        "recovery_contract": {
            "run_token": run_token,
            "attempt_sha256": attempt_binding["sha256"],
            "staged_evidence_only": True,
            "candidate_simulation_count": 0,
            "market_return_evaluation_count": 0,
            "incremental_effective_trial_count": 0,
            "frozen_oos_rows_read": 0,
            "model_training_count": 0,
            "simulation_or_paper_activity": False,
            "broker_writes": False,
        },
        "status_before_repair": {
            "attempt_present": True,
            "campaign_staging_present": True,
            "branch_staging_count": 1,
            "candidate_metrics_count": 1,
            "final_evaluation_present": False,
            "completion_receipt_present": False,
            "frozen_oos_rows_read": 0,
            "model_training_count": 0,
            "broker_writes": False,
        },
        "staged_evidence_inventory": staged_inventory,
        "preregistration_evidence_inventory": preregistration_inventory,
        "authorized_changes": list(breadth_runner.RECOVERY_AUTHORIZED_CHANGES),
        "forbidden_changes": list(breadth_runner.RECOVERY_FORBIDDEN_CHANGES),
    }
    _write_recovery_json(root / breadth_runner.DEVELOPMENT_RECOVERY_AMENDMENT_PATH, amendment)
    breadth_runner._validate_recovery_amendment(
        root,
        contract=contract,
        attempt=attempt,
        attempt_binding=attempt_binding,
        run_token=run_token,
        authorized_branch_count=1,
    )

    amendment["authorized_changes"] = [
        *breadth_runner.RECOVERY_AUTHORIZED_CHANGES,
        "unexpected_scope_expansion",
    ]
    _write_recovery_json(root / breadth_runner.DEVELOPMENT_RECOVERY_AMENDMENT_PATH, amendment)
    with pytest.raises(ValueError, match="recovery amendment scope"):
        breadth_runner._validate_recovery_amendment(
            root,
            contract=contract,
            attempt=attempt,
            attempt_binding=attempt_binding,
            run_token=run_token,
            authorized_branch_count=1,
        )
    amendment["authorized_changes"] = list(breadth_runner.RECOVERY_AUTHORIZED_CHANGES)

    amendment["preregistration_evidence_inventory"] = {
        **preregistration_inventory,
        "sha256": "0" * 64,
    }
    _write_recovery_json(root / breadth_runner.DEVELOPMENT_RECOVERY_AMENDMENT_PATH, amendment)
    with pytest.raises(
        ValueError,
        match="development publication preregistration evidence SHA-256 mismatch",
    ):
        breadth_runner._validate_recovery_amendment(
            root,
            contract=contract,
            attempt=attempt,
            attempt_binding=attempt_binding,
            run_token=run_token,
            authorized_branch_count=1,
        )
    amendment["preregistration_evidence_inventory"] = preregistration_inventory
    _write_recovery_json(root / breadth_runner.DEVELOPMENT_RECOVERY_AMENDMENT_PATH, amendment)

    staging = fixture["staging"]
    metrics_path = staging / "SYN01-metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="ascii"))
    metrics["quality"] = 0.26
    _write_recovery_json(metrics_path, metrics)
    trial_path = staging / "trial-ledger.jsonl"
    trial = json.loads(trial_path.read_text(encoding="ascii"))
    trial["metrics_sha256"] = hashlib.sha256(metrics_path.read_bytes()).hexdigest()
    _write_recovery_jsonl(trial_path, [trial])
    report_path = staging / "evaluation-report.json"
    report = json.loads(report_path.read_text(encoding="ascii"))
    report["candidates"]["SYN01"] = metrics
    _write_recovery_json(report_path, report)

    _load_synthetic_staged_recovery(fixture)
    with pytest.raises(ValueError, match="staged evidence SHA-256 mismatch"):
        breadth_runner._validate_recovery_amendment(
            root,
            contract=contract,
            attempt=attempt,
            attempt_binding=attempt_binding,
            run_token=run_token,
            authorized_branch_count=1,
        )


def test_recovery_attempt_requires_exact_token_and_sha256(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_token = "a" * 32
    iter_id = "synthetic_branch"
    contract = SimpleNamespace(
        child_iteration_ids=(iter_id,),
        candidate_blueprints=(SimpleNamespace(candidate_id="SYN01"),),
        exposure_budgets=SimpleNamespace(
            candidate_budget=1,
            cumulative_trial_exposure_budget=3,
            prior_effective_trial_count=8192,
        ),
    )
    campaign_contract_path = tmp_path / CAMPAIGN_ROOT / "research-campaign-contract.json"
    _write_recovery_json(campaign_contract_path, {"campaign_id": breadth_runner.CAMPAIGN_ID})
    iteration = tmp_path / ITERATION_ROOT / iter_id
    _write_recovery_json(
        iteration / "candidate-manifest.json",
        {"candidates": [{"candidate_id": "SYN01"}]},
    )
    _write_recovery_json(
        iteration / "data-feasibility.json",
        {"historical_evaluation_authorized": True},
    )
    attempt = {
        "schema_version": 1,
        "campaign_id": breadth_runner.CAMPAIGN_ID,
        "status": "reserved_before_development_market_data_read",
        "one_shot": True,
        "run_token": run_token,
        "campaign_contract_sha256": hashlib.sha256(campaign_contract_path.read_bytes()).hexdigest(),
        "registered_candidate_count": 1,
        "evaluated_candidate_count": 1,
        "cost_views_bps": [10, 20, 40],
        "incremental_effective_trial_count": 3,
        "effective_trial_count": 8195,
        "frozen_oos_rows_read": 0,
        "frozen_oos_read_authorized": False,
        "model_training_count": 0,
        "broker_writes": False,
    }
    attempt_path = tmp_path / DEVELOPMENT_ATTEMPT_PATH
    _write_recovery_json(attempt_path, attempt)
    attempt_sha256 = hashlib.sha256(attempt_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        breadth_runner, "_validate_recovery_locked_state", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        breadth_runner,
        "_validate_recovery_preregistration_state",
        lambda *_args, **_kwargs: 1,
    )

    validated = breadth_runner._validate_recovery_attempt(
        tmp_path,
        run_token=run_token,
        attempt_sha256=attempt_sha256,
        contract=contract,
    )
    assert validated[1]["sha256"] == attempt_sha256

    with pytest.raises(ValueError, match="attempt identity mismatch"):
        breadth_runner._validate_recovery_attempt(
            tmp_path,
            run_token="b" * 32,
            attempt_sha256=attempt_sha256,
            contract=contract,
        )
    with pytest.raises(ValueError, match="attempt SHA-256 mismatch"):
        breadth_runner._validate_recovery_attempt(
            tmp_path,
            run_token=run_token,
            attempt_sha256="0" * 64,
            contract=contract,
        )


def test_same_attempt_publication_recovery_api_is_explicit() -> None:
    assert callable(getattr(breadth_runner, "recover_staged_development_publication", None))


@pytest.mark.parametrize(
    "coordinated_campaign_tamper",
    [None, "qd-archive.json", "allocation-ledger.jsonl", "development-evaluation-report.json"],
    ids=["idempotent", "archive_and_receipt", "ledger_and_receipt", "report_and_receipt"],
)
def test_same_attempt_recovery_publishes_with_zero_new_exposure(
    synthetic_staged_recovery: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    coordinated_campaign_tamper: str | None,
) -> None:
    fixture = synthetic_staged_recovery
    root = fixture["root"]
    contract = fixture["contract"]
    attempt = fixture["attempt"]
    attempt_binding = fixture["attempt_binding"]
    amendment_binding = fixture["amendment_binding"]
    run_token = str(fixture["run_token"])
    evaluated_iter_id = "synthetic_evaluated_branch"
    partition_path = (
        root / ITERATION_ROOT / evaluated_iter_id / "development-partition-contract.json"
    )
    _write_recovery_json(partition_path, {"partition_id": "development_validation"})

    monkeypatch.setattr(
        breadth_runner, "load_campaign_contract", lambda *_args, **_kwargs: contract
    )
    monkeypatch.setattr(
        breadth_runner,
        "_validate_recovery_attempt",
        lambda *_args, **_kwargs: (attempt, attempt_binding, "e" * 64),
    )
    monkeypatch.setattr(
        breadth_runner,
        "_validate_recovery_amendment",
        lambda *_args, **_kwargs: amendment_binding,
    )
    monkeypatch.setattr(
        breadth_runner,
        "quality_diversity_policy_from_campaign",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )

    def fake_archive(candidates, _policy, **_kwargs):
        assert [candidate.candidate_id for candidate in candidates] == ["SYN01"]
        return SimpleNamespace(
            elites=(SimpleNamespace(candidate=SimpleNamespace(candidate_id="SYN01")),),
            model_dump=lambda: {
                "schema_version": 1,
                "candidate_ids": ["SYN01"],
                "excluded_candidate_ids": ["SKIP01"],
            },
        )

    monkeypatch.setattr(breadth_runner, "build_quality_diversity_archive", fake_archive)
    monkeypatch.setattr(
        breadth_runner,
        "initialize_allocation_ledger",
        lambda *_args, **_kwargs: SimpleNamespace(entries=(), head_sha256="0" * 64),
    )

    def fake_append(ledger, *, candidate_id, decision, effective_trial_exposure, **_kwargs):
        payload = {
            "candidate_id": candidate_id,
            "decision": decision,
            "effective_trial_exposure": effective_trial_exposure,
        }
        entry = SimpleNamespace(
            **payload,
            model_dump=lambda payload=payload: payload,
        )
        entries = (*ledger.entries, entry)
        head = hashlib.sha256(
            json.dumps(
                [row.model_dump() for row in entries],
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()
        return SimpleNamespace(entries=entries, head_sha256=head)

    monkeypatch.setattr(breadth_runner, "append_allocation_entry", fake_append)
    monkeypatch.setattr(
        breadth_runner,
        "_verify_ledger_effective_trial_count",
        lambda *_args, **_kwargs: 8195,
    )
    monkeypatch.setattr(
        breadth_runner,
        "_advancing_pair_correlation_diagnostic",
        lambda *_args, **_kwargs: {
            "policy": {
                "absolute_maximum": 0.70,
                "minimum_passing_pair_count": 1,
            },
            "correlations": {},
            "passing_pairs": [],
            "passing_pair_count": 0,
            "pass": False,
        },
    )

    def forbidden_recovery_compute(*_args, **_kwargs):
        raise AssertionError("publication recovery must not execute market or simulation work")

    for name in (
        "_load_development_session_calendar",
        "_load_branch_panel",
        "_load_benchmark_panel",
        "build_target_schedule",
        "simulate_target_schedule",
        "_candidate_metrics",
    ):
        monkeypatch.setattr(breadth_runner, name, forbidden_recovery_compute)

    if coordinated_campaign_tamper is None:
        staged = breadth_runner._load_validated_staged_results(
            root,
            contract=contract,
            attempt=attempt,
            attempt_binding=attempt_binding,
            run_token=run_token,
            amendment_binding=amendment_binding,
            campaign_contract_sha256="e" * 64,
        )
        recovery_evidence = breadth_runner._publication_recovery_evidence(
            run_token=run_token,
            attempt_sha256=attempt_binding["sha256"],
            amendment_binding=amendment_binding,
        )
        with pytest.raises(ValueError, match="reconstruction input identity"):
            breadth_runner._reconstruct_recovery_publication(
                contract=contract,
                validated_branches=replace(
                    staged,
                    amendment_binding={"path": "drifted", "sha256": "0" * 64},
                ),
                attempt=attempt,
                attempt_binding=attempt_binding,
                recovery_evidence=recovery_evidence,
                campaign_contract_sha256="e" * 64,
            )

    report = breadth_runner.recover_staged_development_publication(
        root,
        run_token=run_token,
        attempt_sha256=attempt_binding["sha256"],
    )

    recovery = report["publication_recovery"]
    assert recovery == {
        "performed": True,
        "run_token": run_token,
        "attempt_sha256": attempt_binding["sha256"],
        "amendment": amendment_binding,
        "staged_evidence_only": True,
        "candidate_simulation_count": 0,
        "market_return_evaluation_count": 0,
        "incremental_effective_trial_count": 0,
        "frozen_oos_rows_read": 0,
        "model_training_count": 0,
        "simulation_or_paper_activity": False,
        "broker_writes": False,
    }
    assert report["effective_trial_count"] == 8195
    assert report["effective_trial_exposure"] == 3.0
    assert report["development_pre_oos_ready"] is False
    assert report["development_family_statistics_diagnostic"]["status"] == "undefined"
    assert (root / ITERATION_ROOT / evaluated_iter_id / "evaluation-run").is_dir()
    assert not fixture["staging"].exists()
    assert (root / CAMPAIGN_ROOT / "qd-archive.json").is_file()
    assert (root / CAMPAIGN_ROOT / "allocation-ledger.jsonl").is_file()
    assert (root / CAMPAIGN_ROOT / "development-evaluation-report.json").is_file()
    receipt_path = root / DEVELOPMENT_RECEIPT_PATH
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    assert receipt["completion_marker"] is True
    assert receipt["receipt_published_last"] is True
    assert receipt["publication_recovery"] == recovery
    assert receipt["publication_file_count"] == len(receipt["publication_files"])
    for binding in receipt["publication_files"]:
        path = root / binding["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]

    published_state = {
        binding["path"]: (
            (root / binding["path"]).read_bytes(),
            (root / binding["path"]).stat().st_mtime_ns,
        )
        for binding in receipt["publication_files"]
    }

    residual_staging = root / CAMPAIGN_ROOT / f"development-evaluation.staging-{run_token}"
    residual_staging.mkdir()
    retried = breadth_runner.recover_staged_development_publication(
        root,
        run_token=run_token,
        attempt_sha256=attempt_binding["sha256"],
    )
    assert retried == report
    assert residual_staging.is_dir()
    assert not any(residual_staging.iterdir())
    assert published_state == {
        binding["path"]: (
            (root / binding["path"]).read_bytes(),
            (root / binding["path"]).stat().st_mtime_ns,
        )
        for binding in receipt["publication_files"]
    }

    residual_staging.rmdir()
    wrong_residual_staging = root / CAMPAIGN_ROOT / f"development-evaluation.staging-{'b' * 32}"
    wrong_residual_staging.mkdir()
    with pytest.raises(ValueError, match="residual campaign staging"):
        breadth_runner.recover_staged_development_publication(
            root,
            run_token=run_token,
            attempt_sha256=attempt_binding["sha256"],
        )
    wrong_residual_staging.rmdir()
    residual_staging.mkdir()

    original_receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    if coordinated_campaign_tamper is not None:
        target = root / CAMPAIGN_ROOT / coordinated_campaign_tamper
        original_target_bytes = target.read_bytes()
        if coordinated_campaign_tamper == "allocation-ledger.jsonl":
            rows = [
                json.loads(line)
                for line in target.read_text(encoding="ascii").splitlines()
                if line.strip()
            ]
            rows[0]["decision"] = "advance"
            _write_recovery_jsonl(target, rows)
        else:
            payload = json.loads(target.read_text(encoding="ascii"))
            payload["schema_version"] = 999
            _write_recovery_json(target, payload)
        mutated_receipt = json.loads(json.dumps(original_receipt))
        target_relative = target.relative_to(root).as_posix()
        binding = next(
            row for row in mutated_receipt["publication_files"] if row["path"] == target_relative
        )
        binding["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        _write_recovery_json(receipt_path, mutated_receipt)

        with pytest.raises(ValueError, match="campaign output identity mismatch"):
            breadth_runner.recover_staged_development_publication(
                root,
                run_token=run_token,
                attempt_sha256=attempt_binding["sha256"],
            )
        target.write_bytes(original_target_bytes)
        _write_recovery_json(receipt_path, original_receipt)
        return

    # A completed receipt must enumerate every published artifact, including
    # the campaign archive and allocation ledger.  Omitting either binding must
    # not turn a partial publication into a valid idempotent replay.
    for missing_name in ("qd-archive.json", "allocation-ledger.jsonl"):
        mutated_receipt = dict(original_receipt)
        mutated_files = [
            binding
            for binding in original_receipt["publication_files"]
            if Path(binding["path"]).name != missing_name
        ]
        mutated_receipt["publication_files"] = mutated_files
        mutated_receipt["publication_file_count"] = len(mutated_files)
        _write_recovery_json(receipt_path, mutated_receipt)
        with pytest.raises(ValueError, match="receipt identity"):
            breadth_runner.recover_staged_development_publication(
                root,
                run_token=run_token,
                attempt_sha256=attempt_binding["sha256"],
            )
        _write_recovery_json(receipt_path, original_receipt)

    mutated_receipt = {**original_receipt, "unexpected": True}
    _write_recovery_json(receipt_path, mutated_receipt)
    with pytest.raises(ValueError, match="receipt identity"):
        breadth_runner.recover_staged_development_publication(
            root,
            run_token=run_token,
            attempt_sha256=attempt_binding["sha256"],
        )
    _write_recovery_json(receipt_path, original_receipt)

    mutated_receipt = json.loads(json.dumps(original_receipt))
    mutated_receipt["publication_files"][0]["unexpected"] = True
    _write_recovery_json(receipt_path, mutated_receipt)
    with pytest.raises(ValueError, match="publication binding is malformed"):
        breadth_runner.recover_staged_development_publication(
            root,
            run_token=run_token,
            attempt_sha256=attempt_binding["sha256"],
        )
    _write_recovery_json(receipt_path, original_receipt)

    receipt_backup = receipt_path.with_name("development-evaluation-receipt.real.json")
    receipt_path.rename(receipt_backup)
    receipt_path.symlink_to(receipt_backup.name)
    with pytest.raises(ValueError, match="receipt custody"):
        breadth_runner.recover_staged_development_publication(
            root,
            run_token=run_token,
            attempt_sha256=attempt_binding["sha256"],
        )
    receipt_path.unlink()
    receipt_backup.rename(receipt_path)

    final_branch = root / ITERATION_ROOT / evaluated_iter_id / "evaluation-run"
    branch_backup = final_branch.with_name("evaluation-run.real")
    final_branch.rename(branch_backup)
    final_branch.symlink_to(branch_backup.name, target_is_directory=True)
    with pytest.raises(ValueError, match="branch custody mismatch"):
        breadth_runner.recover_staged_development_publication(
            root,
            run_token=run_token,
            attempt_sha256=attempt_binding["sha256"],
        )
    final_branch.unlink()
    branch_backup.rename(final_branch)

    residual_target = residual_staging.with_name("development-evaluation.empty-target")
    residual_target.mkdir()
    residual_staging.rmdir()
    residual_staging.symlink_to(residual_target.name, target_is_directory=True)
    with pytest.raises(ValueError, match="residual campaign staging"):
        breadth_runner.recover_staged_development_publication(
            root,
            run_token=run_token,
            attempt_sha256=attempt_binding["sha256"],
        )


@pytest.mark.parametrize("mutation", ["manifest_policy", "feasibility_reference"])
def test_recovery_revalidates_mutable_preregistration_semantics(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing mutable preregistration evidence must block no-price recovery."""
    root = Path(__file__).resolve().parents[1]
    contract = breadth_runner.load_campaign_contract(breadth_runner.CAMPAIGN_ID, root)
    campaign_contract_path = root / CAMPAIGN_ROOT / "research-campaign-contract.json"
    phase_one_locks = {}
    for iter_id in contract.child_iteration_ids:
        path = root / ITERATION_ROOT / iter_id / "phase-one-preregistration-lock.json"
        phase_one_locks[iter_id] = {
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    attempt = {
        "campaign_contract_sha256": hashlib.sha256(campaign_contract_path.read_bytes()).hexdigest(),
        "phase_one_locks": phase_one_locks,
        "run_token": "a" * 32,
    }
    target_iter = contract.child_iteration_ids[0]
    if mutation == "manifest_policy":
        target = root / ITERATION_ROOT / target_iter / "candidate-manifest.json"
    else:
        target = root / ITERATION_ROOT / target_iter / "data-feasibility.json"
    original_read_json = breadth_runner._read_json

    def read_with_drift(path: Path) -> dict:
        payload = original_read_json(path)
        if path.resolve() != target.resolve():
            return payload
        payload = json.loads(json.dumps(payload))
        if mutation == "manifest_policy":
            payload["candidates"][0]["candidate_policy_sha256"] = "0" * 64
        else:
            payload["required_references"].pop("phase_one_preregistration_lock")
        return payload

    monkeypatch.setattr(breadth_runner, "_read_json", read_with_drift)
    expected_message = (
        "candidate manifest semantics mismatch"
        if mutation == "manifest_policy"
        else "development recovery data-feasibility semantics mismatch"
    )
    with pytest.raises(ValueError, match=expected_message):
        breadth_runner._validate_recovery_preregistration_state(
            root,
            contract=contract,
            attempt=attempt,
        )


@pytest.fixture(scope="module")
def real_recovery_preregistration_context() -> tuple[Path, object, dict[str, object]]:
    root = Path(__file__).resolve().parents[1]
    contract = breadth_runner.load_campaign_contract(breadth_runner.CAMPAIGN_ID, root)
    attempt = json.loads((root / DEVELOPMENT_ATTEMPT_PATH).read_text(encoding="ascii"))
    return root, contract, attempt


def _assert_recovery_preregistration_mutation_rejected(
    monkeypatch: pytest.MonkeyPatch,
    context: tuple[Path, object, dict[str, object]],
    *,
    artifact_name: str,
    mutate,
    match: str,
    target_iter: str | None = None,
) -> None:
    root, contract, attempt = context
    iter_id = target_iter or contract.child_iteration_ids[0]
    target = root / ITERATION_ROOT / iter_id / artifact_name
    original_read_json = breadth_runner._read_json

    def read_with_mutation(path: Path) -> dict:
        payload = original_read_json(path)
        if path.resolve() == target.resolve():
            payload = json.loads(json.dumps(payload))
            mutate(payload)
        return payload

    monkeypatch.setattr(breadth_runner, "_read_json", read_with_mutation)
    with pytest.raises(ValueError, match=match):
        breadth_runner._validate_recovery_preregistration_state(
            root,
            contract=contract,
            attempt=attempt,
        )


def test_recovery_preregistration_state_accepts_exact_repository_evidence_without_market_reads(
    real_recovery_preregistration_context: tuple[Path, object, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, contract, attempt = real_recovery_preregistration_context

    def reject_market_read(*_args, **_kwargs):
        pytest.fail("recovery preregistration validation attempted a market-data read")

    monkeypatch.setattr(breadth_runner, "_read_price_csv_until", reject_market_read)

    assert (
        breadth_runner._validate_recovery_preregistration_state(
            root,
            contract=contract,
            attempt=attempt,
        )
        == 16
    )


@pytest.mark.parametrize(
    ("artifact_name", "field"),
    [
        ("knowledge-baseline.json", "sources"),
        ("knowledge-scout.json", "candidates"),
        ("knowledge-assessment.json", "source_assessment"),
        ("knowledge-context.json", "negative_empirical_memory"),
        ("model-reuse-decision.json", "decisions"),
    ],
)
def test_recovery_rejects_erased_knowledge_evidence(
    artifact_name: str,
    field: str,
    real_recovery_preregistration_context: tuple[Path, object, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(payload: dict) -> None:
        payload[field] = []

    _assert_recovery_preregistration_mutation_rejected(
        monkeypatch,
        real_recovery_preregistration_context,
        artifact_name=artifact_name,
        mutate=mutate,
        match="development recovery exact knowledge evidence mismatch",
    )


def test_recovery_preregistration_inventory_binds_exact_seven_by_nine_files(
    real_recovery_preregistration_context: tuple[Path, object, dict[str, object]],
) -> None:
    root, contract, _attempt = real_recovery_preregistration_context
    mutable_names = (
        "knowledge-baseline.json",
        "knowledge-scout.json",
        "knowledge-assessment.json",
        "knowledge-context.json",
        "model-reuse-decision.json",
        "search-space.json",
        "data-feasibility.json",
        "universe-contract.json",
        "candidate-manifest.json",
    )
    assert breadth_runner.RECOVERY_MUTABLE_PREREGISTRATION_FILES == mutable_names
    assert len(contract.child_iteration_ids) == 7

    files = []
    for iter_id in contract.child_iteration_ids:
        for name in mutable_names:
            path = root / ITERATION_ROOT / iter_id / name
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": breadth_runner._sha256(path),
                }
            )
    payload = {
        "algorithm": "sha256_canonical_json_sorted_path_size_sha256_v1",
        "iteration_ids": list(contract.child_iteration_ids),
        "file_count": 63,
        "files": files,
    }

    assert breadth_runner._recovery_preregistration_inventory_binding(
        root,
        contract=contract,
    ) == {
        "algorithm": payload["algorithm"],
        "iteration_ids": payload["iteration_ids"],
        "file_count": 63,
        "sha256": breadth_runner._canonical_sha256(payload),
    }


@pytest.mark.parametrize("field", ["method", "branch_id", "spec_path"])
def test_recovery_rejects_same_count_candidate_manifest_semantic_drift(
    field: str,
    real_recovery_preregistration_context: tuple[Path, object, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(payload: dict) -> None:
        payload["candidates"][0][field] = f"tampered_{field}"

    _assert_recovery_preregistration_mutation_rejected(
        monkeypatch,
        real_recovery_preregistration_context,
        artifact_name="candidate-manifest.json",
        mutate=mutate,
        match="development recovery candidate manifest semantics mismatch",
    )


def test_recovery_rejects_manifest_semantic_drift_with_coordinated_search_digest(
    real_recovery_preregistration_context: tuple[Path, object, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, contract, attempt = real_recovery_preregistration_context
    iter_id = contract.child_iteration_ids[0]
    iteration = root / ITERATION_ROOT / iter_id
    manifest_path = iteration / "candidate-manifest.json"
    search_path = iteration / "search-space.json"
    original_read_json = breadth_runner._read_json
    original_sha256 = breadth_runner._sha256
    manifest = json.loads(json.dumps(original_read_json(manifest_path)))
    manifest["candidates"][0]["method"] = "tampered_method"
    coordinated_manifest_sha256 = hashlib.sha256(
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("ascii")
    ).hexdigest()
    search_space = json.loads(json.dumps(original_read_json(search_path)))
    search_space["candidate_manifest_sha256"] = coordinated_manifest_sha256

    def read_with_coordinated_drift(path: Path) -> dict:
        if path.resolve() == manifest_path.resolve():
            return json.loads(json.dumps(manifest))
        if path.resolve() == search_path.resolve():
            return json.loads(json.dumps(search_space))
        return original_read_json(path)

    def sha256_with_coordinated_drift(path: Path) -> str:
        if path.resolve() == manifest_path.resolve():
            return coordinated_manifest_sha256
        return original_sha256(path)

    monkeypatch.setattr(breadth_runner, "_read_json", read_with_coordinated_drift)
    monkeypatch.setattr(breadth_runner, "_sha256", sha256_with_coordinated_drift)
    with pytest.raises(
        ValueError,
        match="development recovery candidate manifest semantics mismatch",
    ):
        breadth_runner._validate_recovery_preregistration_state(
            root,
            contract=contract,
            attempt=attempt,
        )


@pytest.mark.parametrize(
    ("group_name", "candidate_field"),
    [
        ("benchmarks", "benchmark_contract"),
        ("candidate_policies", "candidate_policy_contract"),
        ("costs", "cost_contract"),
        ("data", "data_contract"),
        ("features", "feature_contract"),
        ("labels", "label_contract"),
        ("validation", "validation_contract"),
    ],
)
def test_recovery_rejects_coordinated_manifest_contract_id_rename(
    group_name: str,
    candidate_field: str,
    real_recovery_preregistration_context: tuple[Path, object, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(payload: dict) -> None:
        contract_id, binding = next(iter(payload["contracts"][group_name].items()))
        tampered_id = f"{contract_id}_tampered"
        payload["contracts"][group_name] = {tampered_id: binding}
        for candidate in payload["candidates"]:
            candidate[candidate_field] = tampered_id

    _assert_recovery_preregistration_mutation_rejected(
        monkeypatch,
        real_recovery_preregistration_context,
        artifact_name="candidate-manifest.json",
        mutate=mutate,
        match="development recovery manifest contract group mismatch",
    )


@pytest.mark.parametrize(
    "field",
    [
        "adaptive_selection_disclosure",
        "knowledge_contract",
        "objective",
        "evaluation_report_paths",
        "trial_ledger_paths",
    ],
)
def test_recovery_rejects_exact_search_space_field_drift(
    field: str,
    real_recovery_preregistration_context: tuple[Path, object, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(payload: dict) -> None:
        if field == "knowledge_contract":
            payload[field]["assessment_path"] = "tampered.json"
        elif field in {"evaluation_report_paths", "trial_ledger_paths"}:
            payload[field] = []
        else:
            payload[field] = f"tampered_{field}"

    _assert_recovery_preregistration_mutation_rejected(
        monkeypatch,
        real_recovery_preregistration_context,
        artifact_name="search-space.json",
        mutate=mutate,
        match="development recovery search-space identity mismatch",
    )


@pytest.mark.parametrize(
    "mutation",
    ["required_reference_inventory", "blockers", "campaign_universe"],
)
def test_recovery_rejects_exact_data_feasibility_metadata_drift(
    mutation: str,
    real_recovery_preregistration_context: tuple[Path, object, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(payload: dict) -> None:
        if mutation == "required_reference_inventory":
            payload["required_references"].pop("market_data_artifact_1")
            payload["required_reference_names"].remove("market_data_artifact_1")
        elif mutation == "blockers":
            payload["blockers"] = [*payload["blockers"], "tampered_blocker"]
        else:
            payload["campaign_universe"] = {
                **payload["campaign_universe"],
                "status": "tampered",
            }

    _assert_recovery_preregistration_mutation_rejected(
        monkeypatch,
        real_recovery_preregistration_context,
        artifact_name="data-feasibility.json",
        mutate=mutate,
        match="development recovery data-feasibility semantics mismatch",
    )


@pytest.mark.parametrize(
    "field",
    ["candidate_id", "path", "action", "candidate_binding_sha256"],
)
def test_recovery_rejects_candidate_authorization_semantic_drift(
    field: str,
    real_recovery_preregistration_context: tuple[Path, object, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(payload: dict) -> None:
        row = payload["candidate_authorization"]["rows"][0]
        row[field] = "0" * 64 if field == "candidate_binding_sha256" else f"tampered_{field}"

    _assert_recovery_preregistration_mutation_rejected(
        monkeypatch,
        real_recovery_preregistration_context,
        artifact_name="data-feasibility.json",
        mutate=mutate,
        match="development recovery data-feasibility semantics mismatch",
    )


@pytest.mark.parametrize(
    "field",
    ["contract_id", "capability_ids", "universe_definition_metadata"],
)
def test_recovery_rejects_exact_universe_contract_drift(
    field: str,
    real_recovery_preregistration_context: tuple[Path, object, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(payload: dict) -> None:
        if field == "contract_id":
            payload[field] = "tampered_universe_v1"
        elif field == "capability_ids":
            payload[field] = ["market.tampered"]
        else:
            payload["universe_definition"]["selection_rule"] = "tampered_selection_rule"

    _assert_recovery_preregistration_mutation_rejected(
        monkeypatch,
        real_recovery_preregistration_context,
        artifact_name="universe-contract.json",
        mutate=mutate,
        match="development recovery exact universe contract mismatch",
        target_iter="mom_breadth_crossasset_trend_r1",
    )


@pytest.mark.parametrize("dependency_skipped", [False, True])
def test_recovery_iteration_dossier_gate_allows_only_amendment_implementation_drift(
    dependency_skipped: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_blockers = [
        *breadth_runner.RECOVERY_IMPLEMENTATION_DRIFT_BLOCKERS,
        *(["search_space_data_feasibility_not_authorized"] if dependency_skipped else []),
    ]
    monkeypatch.setattr(
        breadth_runner,
        "validate_iteration_dossier",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="blocked",
            blocked=expected_blockers,
            warnings=[],
        ),
    )
    breadth_runner._validate_recovery_iteration_dossier_gate(
        "synthetic_iteration",
        Path("."),
        dependency_skipped=dependency_skipped,
    )

    monkeypatch.setattr(
        breadth_runner,
        "validate_iteration_dossier",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="blocked",
            blocked=[*expected_blockers, "unexpected_blocker"],
            warnings=[],
        ),
    )
    with pytest.raises(ValueError, match="unexpected dossier findings"):
        breadth_runner._validate_recovery_iteration_dossier_gate(
            "synthetic_iteration",
            Path("."),
            dependency_skipped=dependency_skipped,
        )

    monkeypatch.setattr(
        breadth_runner,
        "validate_iteration_dossier",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="blocked",
            blocked=expected_blockers,
            warnings=["unexpected_warning"],
        ),
    )
    with pytest.raises(ValueError, match="unexpected dossier findings"):
        breadth_runner._validate_recovery_iteration_dossier_gate(
            "synthetic_iteration",
            Path("."),
            dependency_skipped=dependency_skipped,
        )
