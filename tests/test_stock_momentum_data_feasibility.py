from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.stock_momentum_data_feasibility import (
    run_stock_momentum_data_feasibility,
)


def test_feasibility_builds_diagnostic_panels_but_keeps_research_blocked(
    tmp_path: Path,
) -> None:
    snapshot = _write_snapshot(tmp_path)
    symbols = ["A", "B"]
    for symbol in symbols:
        _write_daily_cache(tmp_path, symbol)
        _write_minute_cache(tmp_path, symbol)

    result = run_stock_momentum_data_feasibility(
        tmp_path,
        snapshot_path=snapshot,
        intraday_symbols=symbols,
        daily_min_symbols=2,
        daily_max_symbols=2,
        daily_min_records=90,
        intraday_min_history_months=0.0,
        intraday_min_sessions=1,
        intraday_max_gap_rate=0.0,
    )

    assert result.payload["status"] == "complete_with_external_blockers"
    assert result.payload["q2_diagnostic_execution_authorized"] is True
    assert result.payload["research_pass"] is False
    assert result.payload["paper_ready_pass"] is False
    assert result.payload["daily_panel"]["selected_count"] == 2
    assert result.payload["intraday_panel"]["panel_quality_go"] is True
    assert result.payload["intraday_panel"]["q2_diagnostic_go"] is False
    assert result.payload["candidate_accounting"] == {
        "frozen_candidate_count": 48,
        "diagnostic_runnable_count": 28,
        "dependency_skipped_count": 20,
        "unresolved_count": 0,
        "balanced": True,
    }
    assert result.parent_universe_path.exists()
    parent = json.loads(result.parent_universe_path.read_text(encoding="utf-8"))
    assert parent["selection_funnel"][0] == {
        "stage": "raw_snapshot",
        "count": 500,
        "removed_from_previous": 0,
    }
    assert parent["selection_funnel"][-1]["count"] == 500
    assert parent["rejection_reasons"] == {}
    daily = json.loads(result.daily_manifest_path.read_text(encoding="utf-8"))
    assert daily["historical_research_qualified"] is False
    assert "point_in_time_membership_missing" in daily["blockers"]
    assert all(row.get("content_sha256") for row in daily["rows"])
    assert [row["symbol"] for row in daily["benchmark_inputs"]] == ["SPY", "XLK", "BIL"]
    assert all(row["runtime_input_eligible"] for row in daily["benchmark_inputs"])
    assert daily["runtime_cross_section"] == {
        "rank_universe": "selected_symbols_exact",
        "breadth_universe": "selected_symbols_exact",
        "dispersion_universe": "selected_symbols_exact",
        "symbol_count": 2,
    }
    assert daily["runtime_alignment"]["policy"] == (
        "exact_intersection_of_selected62_SPY_XLK_BIL_sessions"
    )
    assert daily["runtime_alignment"]["common_timestamp_count"] == 100
    execution_map = json.loads(
        (
            tmp_path
            / "reports/research/iterations/mom_stock_intraday_codesign_q1/q2-execution-map.json"
        ).read_text(encoding="utf-8")
    )
    by_id = {row["candidate_id"]: row for row in execution_map["rows"]}
    assert execution_map["schema_version"] == 2
    assert execution_map["runtime_entrypoint"].endswith(":run_stock_momentum_codesign_q2")
    assert execution_map["feature_formulas"]["vol_21_raw"].startswith("close.shift(1)")
    assert execution_map["ranking_contract"]["incomplete_cross_section_action"] == (
        "skip_entire_decision_and_record_reason"
    )
    assert execution_map["risk_context_regime_contract"]["D11_usage"].startswith("exclude")
    assert execution_map["model_selection_contract"]["outer_purge"] == (
        "label_end_position<=outer_test_start_position-embargo_bars"
    )
    assert "purged_inner_train_only" in execution_map["model_selection_contract"]["inner_stage_fit"]
    assert (
        "purged_full_outer_train_only"
        in execution_map["model_selection_contract"]["outer_stage_refit"]
    )
    assert execution_map["missing_input_contract"]["validation_order"][1] == (
        "validate_selected62_primitive_open_close_volume_rows"
    )
    assert execution_map["missing_input_contract"]["validation_order"][-2] == (
        "validate_complete_selected62_future_open_label_window"
    )
    assert "offsets_0_and_5" in execution_map["missing_input_contract"]["label_open_window"]
    assert (
        "every_offset_0_through_21" in execution_map["missing_input_contract"]["label_open_window"]
    )
    assert (
        "must_never_change_features_scores_or_weights"
        in execution_map["missing_input_contract"]["label_open_window"]
    )
    assert execution_map["benchmark_evaluation_contract"]["terminal_turnover"].startswith(
        "not_charged"
    )
    assert by_id["D12"]["score_components"] == {
        "mom_252_skip21_rank": 0.4,
        "industry_relative_126_rank": 0.3,
        "volume_surprise_21_63_rank": 0.2,
        "trend_consistency_252_rank": 0.1,
    }
    assert by_id["M09"]["blend_formula"].startswith("0.65*pct_rank(M01)")
    assert by_id["M05"]["risk_acceptance"].endswith("active_stage_train_row_predictions")
    assert by_id["M01"]["primitive_missing_policy"].startswith("skip_entire_decision")
    assert by_id["M01"]["derived_feature_missing_policy"] == (
        "active_stage_train_median_imputation"
    )
    assert by_id["D01"]["derived_feature_missing_policy"] == "skip_entire_decision"
    assert by_id["M09"]["decision_stride_bars"] == 5
    assert by_id["M09"]["composite_parent_training"] == by_id["M10"]["composite_parent_training"]
    assert by_id["M09"]["composite_parent_training"]["risk_parent_train_stride_bars"] == 21
    assert by_id["M09"]["composite_parent_training"]["state_reuse"].startswith("none")
    assert execution_map["fallback_contract"]["equal_weight_cash"] == "100pct_BIL_cash_proxy"
    assert "20pct_each" in execution_map["fallback_contract"]["fixed_position_caps"]
    assert execution_map["fallback_contract"]["cycle_or_resolution_failure"] == (
        "100pct_BIL_cash_proxy"
    )
    assert (
        "one_selected62_symbol"
        in execution_map["benchmark_evaluation_contract"]["ex_post_best_symbol_report_only"]
    )
    assert (
        "last_outer_test_horizon_open"
        in execution_map["benchmark_evaluation_contract"]["ex_post_best_symbol_report_only"]
    )
    assert by_id["M16"]["fit_allowed"] is False
    assert by_id["M16"]["future_shift_bars"] == 5
    assert result.payload["path_gates"]["intraday_independent"]["q2_action"] == (
        "dependency_skipped"
    )
    authorization = {
        row["candidate_id"]: row["action"] for row in result.payload["q2_authorization"]["rows"]
    }
    assert {
        candidate_id for candidate_id, action in authorization.items() if action == "run_diagnostic"
    } == {
        *[f"D{index:02d}" for index in range(1, 13)],
        *[f"M{index:02d}" for index in range(1, 17)],
    }
    assert {
        candidate_id
        for candidate_id, action in authorization.items()
        if action == "dependency_skipped"
    } == {
        *[f"I{index:02d}" for index in range(1, 13)],
        *[f"E{index:02d}" for index in range(1, 9)],
    }


def test_feasibility_quarantines_unused_daily_fields_without_global_session_drop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    snapshot = _write_snapshot(tmp_path)
    _write_daily_cache(tmp_path, "A", invalid_ohlc_rows=1)
    _write_daily_cache(tmp_path, "B")
    for symbol in ["A", "B"]:
        _write_minute_cache(tmp_path, symbol)
    monkeypatch.setattr(
        "open_composer.research.stock_momentum_data_feasibility.MAX_DIAGNOSTIC_FIELD_ANOMALY_RATIO",
        0.01,
    )

    result = run_stock_momentum_data_feasibility(
        tmp_path,
        snapshot_path=snapshot,
        intraday_symbols=["A", "B"],
        daily_min_symbols=2,
        daily_max_symbols=2,
        daily_min_records=90,
        intraday_min_history_months=0.0,
        intraday_min_sessions=1,
        intraday_max_gap_rate=0.0,
    )

    daily = json.loads(result.daily_manifest_path.read_text(encoding="utf-8"))
    rows = {row["symbol"]: row for row in daily["rows"]}
    row = rows["A"]
    assert daily["historical_diagnostic_go"] is True
    assert daily["historical_research_qualified"] is False
    assert row["quality_pass"] is True
    assert row["valid_ohlc"] is False
    assert row["invalid_ohlc_count"] == 1
    assert row["invalid_required_field_count"] == 0
    assert row["q2_excluded_sessions"] == []
    assert rows["B"]["quality_pass"] is True
    assert daily["q2_global_excluded_sessions"] == []
    assert daily["q2_field_anomalies"] == [
        {
            "symbol": "A",
            "timestamp": row["invalid_ohlc_timestamps"][0],
            "quarantined_fields": ["high", "low"],
        }
    ]
    assert daily["data_cleaning_policy"]["forward_fill_allowed"] is False
    assert daily["data_cleaning_policy"]["high_low_dependent_candidates_allowed"] is False


def test_feasibility_blocks_daily_path_when_panel_anomaly_budget_is_exceeded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    snapshot = _write_snapshot(tmp_path)
    for symbol in ["A", "B"]:
        _write_daily_cache(tmp_path, symbol, invalid_ohlc_rows=1)
        _write_minute_cache(tmp_path, symbol)
    monkeypatch.setattr(
        "open_composer.research.stock_momentum_data_feasibility."
        "MAX_DIAGNOSTIC_PANEL_FIELD_ANOMALIES",
        1,
    )

    result = run_stock_momentum_data_feasibility(
        tmp_path,
        snapshot_path=snapshot,
        intraday_symbols=["A", "B"],
        daily_min_symbols=2,
        daily_max_symbols=2,
        daily_min_records=90,
        intraday_min_history_months=0.0,
        intraday_min_sessions=1,
        intraday_max_gap_rate=0.0,
    )

    daily = json.loads(result.daily_manifest_path.read_text(encoding="utf-8"))
    assert daily["selected_count"] == 2
    assert daily["field_anomaly_budget_pass"] is False
    assert daily["historical_diagnostic_go"] is False


def test_feasibility_freezes_benchmark_hashes_and_common_session_intersection(
    tmp_path: Path,
) -> None:
    snapshot = _write_snapshot(tmp_path)
    for symbol in ["A", "B"]:
        _write_daily_cache(tmp_path, symbol)
    bil_path = tmp_path / "data/cache/bil_daily_longbridge_nasdaq_basic.csv"
    bil = pd.read_csv(bil_path).iloc[:-1]
    bil.to_csv(bil_path, index=False)

    result = run_stock_momentum_data_feasibility(
        tmp_path,
        snapshot_path=snapshot,
        intraday_symbols=["A", "B"],
        daily_min_symbols=2,
        daily_max_symbols=2,
        daily_min_records=90,
    )

    daily = json.loads(result.daily_manifest_path.read_text(encoding="utf-8"))
    benchmarks = {row["symbol"]: row for row in daily["benchmark_inputs"]}
    assert all(row["cache_sha256"] for row in benchmarks.values())
    assert all(row["manifest_sha256"] for row in benchmarks.values())
    assert benchmarks["BIL"]["manifest_runtime_cache_matches"] is False
    assert benchmarks["BIL"]["runtime_input_eligible"] is True
    assert daily["runtime_alignment"]["common_timestamp_count"] == 99
    assert daily["runtime_alignment"]["sessions_not_in_exact_intersection"] == 1
    assert daily["historical_diagnostic_go"] is True


def test_feasibility_freezes_intraday_content_despite_source_manifest_drift(
    tmp_path: Path,
) -> None:
    snapshot = _write_snapshot(tmp_path)
    _write_daily_cache(tmp_path, "A")
    _write_minute_cache(tmp_path, "A")
    manifest_path = tmp_path / "data/cache/manifests/a_1m_alpaca_iex.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["records"] -= 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = run_stock_momentum_data_feasibility(
        tmp_path,
        snapshot_path=snapshot,
        intraday_symbols=["A"],
        daily_min_symbols=1,
        daily_max_symbols=1,
        daily_min_records=90,
        intraday_min_history_months=0.0,
        intraday_min_sessions=1,
        intraday_max_gap_rate=0.0,
    )

    intraday = json.loads(result.intraday_manifest_path.read_text(encoding="utf-8"))
    assert intraday["historical_diagnostic_go"] is False
    assert intraday["historical_research_qualified"] is False
    assert intraday["panel_content_frozen"] is True
    assert intraday["source_manifest_match_count"] == 0
    assert intraday["source_manifest_drift_symbols"] == ["A"]
    assert "source_acquisition_manifest_drift" in intraday["blockers"]


def test_feasibility_requires_every_intraday_symbol(tmp_path: Path) -> None:
    snapshot = _write_snapshot(tmp_path)
    for symbol in ["A", "B"]:
        _write_daily_cache(tmp_path, symbol)
    _write_minute_cache(tmp_path, "A")

    result = run_stock_momentum_data_feasibility(
        tmp_path,
        snapshot_path=snapshot,
        intraday_symbols=["A", "B"],
        daily_min_symbols=2,
        daily_max_symbols=2,
        daily_min_records=90,
        intraday_min_history_months=0.0,
        intraday_min_sessions=1,
        intraday_max_gap_rate=0.0,
    )

    assert result.payload["intraday_panel"]["panel_quality_go"] is False
    assert result.payload["intraday_panel"]["q2_diagnostic_go"] is False
    intraday = json.loads(result.intraday_manifest_path.read_text(encoding="utf-8"))
    assert intraday["available_symbol_count"] == 1
    assert any(row.get("status") == "error" and row["symbol"] == "B" for row in intraday["rows"])


def test_feasibility_reports_cache_manifest_drift(tmp_path: Path) -> None:
    snapshot = _write_snapshot(tmp_path)
    _write_daily_cache(tmp_path, "A")
    orphan = tmp_path / "data/cache/manifests/orphan_daily_longbridge_nasdaq_basic.json"
    orphan.write_text("{}", encoding="utf-8")

    result = run_stock_momentum_data_feasibility(
        tmp_path,
        snapshot_path=snapshot,
        intraday_symbols=["A"],
        daily_min_symbols=1,
        daily_max_symbols=1,
        daily_min_records=90,
        intraday_min_history_months=0.0,
        intraday_min_sessions=1,
    )

    daily = json.loads(result.daily_manifest_path.read_text(encoding="utf-8"))
    assert daily["cache_inventory"]["drift_free"] is False
    assert daily["cache_inventory"]["manifest_without_cache"] == ["ORPHAN"]


def test_feasibility_marks_unadjusted_intraday_action_boundaries(tmp_path: Path) -> None:
    snapshot = _write_snapshot(tmp_path)
    _write_daily_cache(tmp_path, "A")
    _write_minute_cache(tmp_path, "A", split_second_session=True)

    result = run_stock_momentum_data_feasibility(
        tmp_path,
        snapshot_path=snapshot,
        intraday_symbols=["A"],
        daily_min_symbols=1,
        daily_max_symbols=1,
        daily_min_records=90,
        intraday_min_history_months=0.0,
        intraday_min_sessions=1,
        intraday_max_gap_rate=0.0,
    )

    intraday = json.loads(result.intraday_manifest_path.read_text(encoding="utf-8"))
    row = intraday["rows"][0]
    assert row["detected_action_discontinuity_count"] == 1
    assert row["detected_action_discontinuities"][0]["classification"].startswith("possible_split")
    assert row["q2_excluded_sessions"] == ["2026-01-05"]


def test_stock_momentum_feasibility_cli_writes_negative_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    snapshot = _write_snapshot(tmp_path)
    monkeypatch.setattr("open_composer.cli.project_root", lambda: tmp_path)

    result = CliRunner().invoke(
        app,
        ["data", "stock-momentum-feasibility", "--snapshot", str(snapshot)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "status=blocked" in result.output
    report = json.loads(
        (
            tmp_path
            / "reports/research/iterations/mom_stock_intraday_codesign_q1/data-feasibility.json"
        ).read_text(encoding="utf-8")
    )
    assert report["workflow_pass"] is True
    assert report["research_pass"] is False


def _write_snapshot(root: Path) -> Path:
    path = root / "data/research/multiasset_momentum/nasdaq-current-stock-snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for index in range(500):
        symbol = _alpha_symbol(index)
        rows.append(
            {
                "country": "United States",
                "industry": "Software",
                "lastsale": "$100.00",
                "marketCap": str(100_000_000_000 - index * 1_000_000),
                "name": f"{symbol} Common Stock",
                "sector": "Technology" if index % 2 == 0 else "Finance",
                "symbol": symbol,
                "volume": "1000000",
            }
        )
    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-14T06:44:46Z",
                "record_count": len(rows),
                "report_type": "nasdaq_current_universe_snapshot",
                "rows": rows,
                "source_url": "https://example.test/current-snapshot",
            }
        ),
        encoding="utf-8",
    )
    candidate_path = (
        root / "reports/research/iterations/mom_stock_intraday_codesign_q1/candidate-manifest.json"
    )
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    source_candidate_path = (
        Path(__file__).resolve().parents[1]
        / "reports/research/iterations/mom_stock_intraday_codesign_q1/candidate-manifest.json"
    )
    candidate_path.write_text(source_candidate_path.read_text(encoding="utf-8"), encoding="utf-8")
    for symbol in ["SPY", "XLK", "BIL"]:
        _write_daily_cache(root, symbol)
    return path


def _write_daily_cache(
    root: Path,
    symbol: str,
    *,
    invalid_ohlc_rows: int = 0,
) -> None:
    cache = root / f"data/cache/{symbol.lower()}_daily_longbridge_nasdaq_basic.csv"
    manifest = root / f"data/cache/manifests/{symbol.lower()}_daily_longbridge_nasdaq_basic.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    timestamps = pd.date_range("2025-01-02", periods=100, freq="B", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * len(timestamps),
            "high": [101.0] * len(timestamps),
            "low": [99.0] * len(timestamps),
            "close": [100.5] * len(timestamps),
            "volume": [1_000_000] * len(timestamps),
        }
    )
    for index in range(invalid_ohlc_rows):
        frame.loc[index, "low"] = frame.loc[index, "open"] + 0.25
    frame.to_csv(cache, index=False)
    manifest.write_text(
        json.dumps(
            {
                "provider": "longbridge",
                "feed": "nasdaq_basic",
                "symbol": symbol,
                "timeframe": "daily",
                "request_params": {"adjusted": True},
                "records": len(frame),
                "first_timestamp": timestamps.min().isoformat(),
                "last_timestamp": timestamps.max().isoformat(),
            }
        ),
        encoding="utf-8",
    )


def _write_minute_cache(
    root: Path,
    symbol: str,
    *,
    split_second_session: bool = False,
) -> None:
    path = root / f"data/cache/{symbol.lower()}_1m_iex.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    session_one = pd.date_range("2026-01-02T14:30:00Z", periods=390, freq="1min")
    timestamps = session_one
    prices = [100.0] * len(session_one)
    if split_second_session:
        session_two = pd.date_range("2026-01-05T14:30:00Z", periods=390, freq="1min")
        timestamps = session_one.append(session_two)
        prices.extend([10.0] * len(session_two))
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": prices,
            "high": [price * 1.01 for price in prices],
            "low": [price * 0.99 for price in prices],
            "close": [price * 1.005 for price in prices],
            "volume": [10_000] * len(timestamps),
        }
    )
    frame.to_csv(path, index=False)
    manifest = root / f"data/cache/manifests/{symbol.lower()}_1m_alpaca_iex.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "provider": "alpaca",
                "feed": "iex",
                "symbol": symbol,
                "timeframe": "1m",
                "records": len(frame),
                "first_timestamp": timestamps.min().isoformat(),
                "last_timestamp": timestamps.max().isoformat(),
            }
        ),
        encoding="utf-8",
    )


def _alpha_symbol(index: int) -> str:
    value = index + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result
