from __future__ import annotations

import json
from pathlib import Path

import yaml

from open_composer.adapters.execution.nautilus_trader import build_nautilus_backtest_plan
from open_composer.compiler.spec_to_pine import compile_pine_strategy
from open_composer.dashboard import build_dashboard_catalog
from open_composer.engines.backtest_engine import run_backtest
from open_composer.engines.scanner_engine import run_scan
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research import draft_strategy_from_idea
from open_composer.strategy_capabilities import assess_strategy_capabilities
from open_composer.strategy_lifecycle import activate_strategy
from open_composer.strategy_versions import (
    diff_strategy_versions,
    load_strategy_versions,
    register_strategy_version,
    rollback_strategy_version,
)


def test_strategy_version_registry_snapshots_specs_and_binds_runs(
    sample_workspace: Path,
) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    version = register_strategy_version(
        spec_path,
        sample_workspace,
        created_by="test",
    )
    artifacts = run_backtest(spec_path, root=sample_workspace)

    versions = load_strategy_versions(sample_workspace, "fixture_pullback_15m")
    assert versions[0].version_id == version.version_id
    assert version.backend == "python_reference"
    assert (sample_workspace / version.snapshot_path).exists()
    assert (sample_workspace / version.manifest_path).exists()
    assert artifacts.run.version_id == version.version_id
    assert artifacts.run.spec_hash == version.content_hash
    assert artifacts.run.strategy_backend == "python_reference"
    assert artifacts.run.execution_backend == "python_reference"
    assert artifacts.signals[0].version_id == version.version_id
    assert artifacts.signals[0].spec_hash == version.content_hash


def test_nautilus_backtest_plan_is_written_for_nautilus_backend(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "open_composer.adapters.execution.nautilus_trader.nautilus_trader_available",
        lambda: True,
    )
    active_path = activate_strategy(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
    )

    artifacts = run_backtest(active_path, root=sample_workspace)
    catalog = build_dashboard_catalog(sample_workspace)

    backend_plan_path = Path(artifacts.run.backend_plan_path or "")
    plan = json.loads(backend_plan_path.read_text(encoding="utf-8"))
    dashboard_run = next(run for run in catalog.runs if run.run_id == artifacts.run.run_id)

    assert artifacts.run.strategy_backend == "nautilus_trader"
    assert artifacts.run.execution_backend == "nautilus_backtest"
    assert artifacts.run.signals >= 1
    assert artifacts.run.trades >= 1
    assert backend_plan_path.exists()
    assert artifacts.backend_plan_path == str(backend_plan_path)
    assert artifacts.signals[0].execution_backend == "nautilus_backtest"
    assert plan["strategy_name"] == "fixture_pullback_15m"
    assert plan["execution_backend"] == "nautilus_backtest"
    assert plan["selected_backend"] == "nautilus_trader"
    assert plan["bar_type"] == "15m-ohlcv"
    assert dashboard_run.backend_plan_path == str(backend_plan_path)


def test_strategy_versions_diff_and_safe_rollback(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    draft_version = register_strategy_version(spec_path, sample_workspace, created_by="test")
    active_path = activate_strategy(
        spec_path,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
    )
    active_version = load_strategy_versions(sample_workspace, "fixture_pullback_15m")[-1]

    diff = diff_strategy_versions(
        sample_workspace,
        "fixture_pullback_15m",
        draft_version.version_id,
        active_version.version_id,
    )
    rollback = rollback_strategy_version(
        sample_workspace,
        "fixture_pullback_15m",
        active_version.version_id,
    )
    rolled_back = load_strategy_spec(rollback.path)
    catalog = build_dashboard_catalog(sample_workspace)
    rolled_catalog_version = next(
        version
        for version in catalog.versions
        if version.strategy_name == "fixture_pullback_15m"
        and version.version_id == rollback.version.version_id
    )

    assert active_path.exists()
    assert diff.changed
    assert any("paper_auto" in line or "nautilus_trader" in line for line in diff.diff_lines)
    assert (
        rollback.path
        == sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    )
    assert rolled_back.lifecycle == "draft"
    assert rolled_back.execution.mode == "manual_signal"
    assert rolled_back.execution.broker == "none"
    assert rollback.version.parent_version_id == active_version.version_id
    assert rolled_catalog_version.parent_version_id == active_version.version_id
    assert rolled_catalog_version.created_by == "strategy_rollback"


def test_breakout_strategy_generation_uses_expanded_factors_and_catalog(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    idea = "Create a QQQ 15m breakout strategy with volume expansion and volatility filter."
    monkeypatch.setattr(
        "open_composer.adapters.execution.nautilus_trader.nautilus_trader_available",
        lambda: True,
    )

    spec_path = draft_strategy_from_idea(idea, sample_workspace)
    spec = load_strategy_spec(spec_path)
    report = assess_strategy_capabilities(spec_path)
    backtest = run_backtest(spec_path, root=sample_workspace)
    latest_signals = run_scan(spec_path, root=sample_workspace)
    pine_path = compile_pine_strategy(spec_path, root=sample_workspace)
    catalog = build_dashboard_catalog(sample_workspace)

    assert spec.name == "qqq_breakout_volume_15m"
    assert spec.llm_review.enabled is False
    assert spec.factors["breakout_level"].expression == "lag(highest(close, 6), 1)"
    assert spec.factors["volatility_range"].expression == "atr(5)"
    assert "close > breakout_level" in spec.entry.all
    assert "volatility_range > 0.45" in spec.entry.all
    assert report.finding("python_mvp_backtest").status == "supported"
    assert report.finding("tradingview_pine_strategy").status == "supported"
    assert report.backend_plan.status == "supported"
    assert backtest.run.version_id is not None
    assert backtest.run.signals >= 1
    assert latest_signals
    assert "ta.atr(5)" in pine_path.read_text(encoding="utf-8")
    assert (sample_workspace / "strategy_versions" / spec.name).exists()
    assert any(strategy.strategy_name == spec.name for strategy in catalog.strategies)
    catalog_strategy = next(
        strategy for strategy in catalog.strategies if strategy.strategy_name == spec.name
    )
    assert catalog_strategy.model_role == "pure_quant"
    assert catalog_strategy.factor_count == 3
    assert catalog_strategy.backend == "python_reference"
    assert catalog_strategy.backend_status == "supported"
    assert catalog_strategy.compatibility["python_mvp_backtest"] == "supported"
    assert catalog.summary.strategy_backend_counts == {"python_reference": 2}
    assert catalog.summary.backend_status_counts == {"partial": 1, "supported": 1}


def test_generated_strategy_can_run_real_nautilus_backtest(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    idea = "Create a QQQ 15m breakout strategy with volume expansion and volatility filter."
    monkeypatch.setattr(
        "open_composer.adapters.execution.nautilus_trader.nautilus_trader_available",
        lambda: True,
    )

    draft_path = draft_strategy_from_idea(idea, sample_workspace)
    active_path = activate_strategy(
        draft_path,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
    )
    artifacts = run_backtest(active_path, root=sample_workspace)
    catalog = build_dashboard_catalog(sample_workspace)

    dashboard_run = next(run for run in catalog.runs if run.run_id == artifacts.run.run_id)
    dashboard_strategy = next(
        strategy
        for strategy in catalog.strategies
        if strategy.strategy_name == "qqq_breakout_volume_15m"
    )

    assert artifacts.run.strategy_backend == "nautilus_trader"
    assert artifacts.run.execution_backend == "nautilus_backtest"
    assert artifacts.run.backend_plan_path
    assert artifacts.run.report_path and Path(artifacts.run.report_path).exists()
    assert artifacts.run.signal_log_path and Path(artifacts.run.signal_log_path).exists()
    parity_paths = sorted((sample_workspace / "reports" / "parity").glob("*backend-parity.md"))
    assert parity_paths
    parity_text = parity_paths[-1].read_text(encoding="utf-8")
    assert "Backend Parity" in parity_text
    assert "Primary backend: `nautilus_backtest`" in parity_text
    assert "Reference backend: `python_reference`" in parity_text
    assert any("backend parity report" in item for item in artifacts.run.assumptions)
    assert artifacts.run.bars > 0
    assert artifacts.signals
    assert all(signal.execution_backend == "nautilus_backtest" for signal in artifacts.signals)
    assert dashboard_run.execution_backend == "nautilus_backtest"
    assert dashboard_run.backend_plan_path == artifacts.run.backend_plan_path
    assert dashboard_strategy.backend == "nautilus_trader"


def test_llm_feature_factor_replays_from_saved_packets(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    feature_path = sample_workspace / "feature_logs" / "qqq_llm_features.jsonl"
    monkeypatch.setattr(
        "open_composer.adapters.execution.nautilus_trader.nautilus_trader_available",
        lambda: True,
    )
    feature_path.write_text(
        (
            '{"timestamp":"2026-01-01T00:00:00Z",'
            '"published_at":"2026-01-01T00:00:00Z",'
            '"fetched_at":"2026-01-01T00:00:00Z",'
            '"visible_at":"2026-01-01T00:00:00Z",'
            '"source":"llm","symbol":"QQQ","llm_sentiment_score":0.8}\n'
        ),
        encoding="utf-8",
    )
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_llm_feature_15m.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "qqq_llm_feature_15m",
                "description": "QQQ strategy gated by replayed LLM sentiment feature.",
                "timeframe": "15m",
                "universe": ["QQQ"],
                "lifecycle": "draft",
                "factors": {
                    "llm_sentiment": {
                        "source": "llm_feature",
                        "path": "feature_logs/qqq_llm_features.jsonl",
                        "field": "llm_sentiment_score",
                        "default": 0.0,
                        "description": "Structured LLM sentiment score replayed by timestamp.",
                    },
                    "trend_gap": {
                        "source": "expression",
                        "expression": "close - ema(close, 5)",
                    },
                },
                "entry": {
                    "all": [
                        "llm_sentiment > 0.5",
                        "trend_gap > 0",
                        "volume > sma(volume, 3)",
                    ]
                },
                "exit": {"any": ["llm_sentiment < 0.2", "close < ema(close, 5)"]},
                "risk": {
                    "max_trades_per_day": 2,
                    "max_position_weight": 0.1,
                    "stop_loss_pct": 1.0,
                    "take_profit_pct": 2.0,
                },
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {
                    "source": "sample",
                    "symbol": "QQQ",
                    "path": "data/sample/qqq_15m.csv",
                },
                "llm_review": {"enabled": False},
                "required_capabilities": ["market.sample_ohlcv", "news.alpha_vantage"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    spec = load_strategy_spec(spec_path)
    report = assess_strategy_capabilities(spec_path)
    plan = build_nautilus_backtest_plan(
        spec_path,
        sample_workspace,
        run_id_value="run_llm_feature",
    )
    backtest = run_backtest(spec_path, root=sample_workspace)
    run_scan(spec_path, root=sample_workspace)
    catalog = build_dashboard_catalog(sample_workspace)
    binding = plan.custom_data_bindings[0]

    assert spec.factors["llm_sentiment"].source == "llm_feature"
    assert binding.factor_name == "llm_sentiment"
    assert binding.exists is True
    assert binding.record_count == 1
    assert binding.point_in_time_status == "partial"
    assert "dedupe_key is missing" in "; ".join(binding.replay_warnings)
    assert "schema_version is missing" in "; ".join(binding.replay_warnings)
    assert report.finding("python_mvp_backtest").status == "partial"
    assert report.finding("llm_quant_workflow").status == "partial"
    assert report.backend_plan.status == "partial"
    assert backtest.signals
    assert backtest.run.report_path
    backtest_report = Path(backtest.run.report_path).read_text(encoding="utf-8")
    assert "## Feature Replay" in backtest_report
    assert "Backtest execution reads saved feature packets only" in backtest_report
    assert "status=`partial`" in backtest_report
    assert "dedupe_key is missing" in backtest_report
    scan_report = sorted(
        (sample_workspace / "reports" / "scans").glob("scan-qqq_llm_feature_15m*.md")
    )[-1].read_text(encoding="utf-8")
    assert "## Feature Replay" in scan_report
    assert "status=`partial`" in scan_report
    strategy = next(
        item for item in catalog.strategies if item.strategy_name == "qqq_llm_feature_15m"
    )
    assert strategy.llm_feature_factor_names == ["llm_sentiment"]
    assert strategy.backend_status == "partial"


def test_feature_packet_factor_replays_nested_feature_fields(
    sample_workspace: Path,
) -> None:
    feature_path = sample_workspace / "feature_logs" / "qqq_event_features.jsonl"
    feature_path.write_text(
        (
            '{"timestamp":"2026-01-01T00:00:00Z","published_at":"2026-01-01T00:00:00Z",'
            '"fetched_at":"2026-01-01T00:01:00Z","source":"alpha_vantage",'
            '"symbol":"QQQ","dedupe_key":"news:qqq:1","schema_version":"1",'
            '"features":{"event_risk_score":0.8}}\n'
        ),
        encoding="utf-8",
    )
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_event_feature_15m.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "qqq_event_feature_15m",
                "description": "QQQ strategy gated by replayed event feature packets.",
                "timeframe": "15m",
                "universe": ["QQQ"],
                "lifecycle": "draft",
                "factors": {
                    "event_risk": {
                        "source": "feature_packet",
                        "path": "feature_logs/qqq_event_features.jsonl",
                        "field": "event_risk_score",
                        "default": 0.0,
                        "description": "Point-in-time event risk score from saved packets.",
                    },
                    "trend_gap": {
                        "source": "expression",
                        "expression": "close - ema(close, 5)",
                    },
                },
                "entry": {
                    "all": [
                        "event_risk > 0.5",
                        "trend_gap > 0",
                        "volume > sma(volume, 3)",
                    ]
                },
                "exit": {"any": ["event_risk < 0.2", "close < ema(close, 5)"]},
                "risk": {
                    "max_trades_per_day": 2,
                    "max_position_weight": 0.1,
                    "stop_loss_pct": 1.0,
                    "take_profit_pct": 2.0,
                },
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {
                    "source": "sample",
                    "symbol": "QQQ",
                    "path": "data/sample/qqq_15m.csv",
                },
                "llm_review": {"enabled": False},
                "required_capabilities": ["market.sample_ohlcv", "news.alpha_vantage"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    spec = load_strategy_spec(spec_path)
    report = assess_strategy_capabilities(spec_path)
    plan = build_nautilus_backtest_plan(
        spec_path,
        sample_workspace,
        run_id_value="run_event_feature",
    )
    plan_path = sample_workspace / "reports" / "runs" / "nautilus" / "run_event_feature.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    report_path = sample_workspace / "reports" / "backtests" / "run_event_feature.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "\n".join(
            [
                "# Backtest Report: qqq_event_feature_15m",
                "",
                "- Run ID: `run_event_feature`",
                "- Strategy ID: `qqq_event_feature_15m`",
                "- Strategy backend: `nautilus_trader`",
                "- Execution backend: `nautilus_backtest`",
                f"- Backend plan path: `{plan_path}`",
                "- Symbol: `QQQ`",
                "- Timeframe: `15m`",
                "- Bars: 1",
                "- Signals: 0",
                "- Closed trades: 0",
                "- Start equity: 100000.00",
                "- End equity: 100000.00",
                "- Total return: 0.00%",
                "- Annualized return: n/a",
                "- Sharpe ratio: n/a",
                "- Total fees: 0.00",
                "",
            ]
        ),
        encoding="utf-8",
    )
    backtest = run_backtest(spec_path, root=sample_workspace)
    catalog = build_dashboard_catalog(sample_workspace)
    binding = plan.custom_data_bindings[0]
    dashboard_run = next(run for run in catalog.runs if run.run_id == "run_event_feature")

    assert spec.factors["event_risk"].source == "feature_packet"
    assert binding.factor_name == "event_risk"
    assert binding.exists is True
    assert binding.record_count == 1
    assert binding.point_in_time_status == "complete"
    assert binding.replay_warnings == []
    assert binding.first_timestamp == "2026-01-01T00:00:00+00:00"
    assert binding.last_timestamp == "2026-01-01T00:00:00+00:00"
    assert dashboard_run.custom_data_bindings[0].factor_name == "event_risk"
    assert dashboard_run.custom_data_bindings[0].point_in_time_status == "complete"
    assert report.finding("python_mvp_backtest").status == "partial"
    assert any(
        "feature_packet factors" in reason
        for reason in report.finding("python_mvp_backtest").reasons
    )
    assert report.finding("nautilus_trader_backend").status == "partial"
    assert report.backend_plan.feature_packet_factor_names == ["event_risk"]
    assert report.finding("tradingview_pine_strategy").status == "partial"
    assert any(
        "feature_packet factors" in reason
        for reason in report.finding("tradingview_pine_strategy").reasons
    )
    assert backtest.signals
    assert backtest.run.report_path
    backtest_report = Path(backtest.run.report_path).read_text(encoding="utf-8")
    assert "## Feature Replay" in backtest_report
    assert "event_risk" in backtest_report
    assert "status=`complete`" in backtest_report
    assert "schema_versions=`['1']`" in backtest_report
    strategy = next(
        item for item in catalog.strategies if item.strategy_name == "qqq_event_feature_15m"
    )
    assert "event_risk" in strategy.factor_names
    assert strategy.llm_feature_factor_names == []


def test_nautilus_backtest_replays_feature_packets_as_custom_data(
    sample_workspace: Path,
) -> None:
    feature_path = sample_workspace / "feature_logs" / "qqq_event_features.jsonl"
    feature_path.write_text(
        (
            '{"timestamp":"2026-01-01T00:00:00Z","published_at":"2026-01-01T00:00:00Z",'
            '"fetched_at":"2026-01-01T00:01:00Z","source":"alpha_vantage",'
            '"symbol":"QQQ","dedupe_key":"news:qqq:1","schema_version":"1",'
            '"features":{"event_risk_score":0.8}}\n'
        ),
        encoding="utf-8",
    )
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_nautilus_event_15m.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "qqq_nautilus_event_15m",
                "description": "QQQ Nautilus strategy gated by replayed event feature packets.",
                "timeframe": "15m",
                "universe": ["QQQ"],
                "lifecycle": "draft",
                "factors": {
                    "event_risk": {
                        "source": "feature_packet",
                        "path": "feature_logs/qqq_event_features.jsonl",
                        "field": "event_risk_score",
                        "default": 0.0,
                        "description": "Point-in-time event risk score from saved packets.",
                    }
                },
                "entry": {"all": ["event_risk > 0.5", "close > ema(close, 5)"]},
                "exit": {"any": ["event_risk < 0.2", "close < ema(close, 5)"]},
                "risk": {
                    "max_trades_per_day": 2,
                    "max_position_weight": 0.1,
                    "stop_loss_pct": 1.0,
                    "take_profit_pct": 2.0,
                },
                "execution": {
                    "backend": "nautilus_trader",
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {
                    "source": "sample",
                    "symbol": "QQQ",
                    "path": "data/sample/qqq_15m.csv",
                },
                "llm_review": {"enabled": False},
                "required_capabilities": ["market.sample_ohlcv", "news.alpha_vantage"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    artifacts = run_backtest(spec_path, root=sample_workspace)

    assert artifacts.run.execution_backend == "nautilus_backtest"
    assert artifacts.signals
    assert any("custom data events" in assumption for assumption in artifacts.run.assumptions)
