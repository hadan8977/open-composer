from __future__ import annotations

import json
from pathlib import Path

import yaml

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
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"

    version = register_strategy_version(
        spec_path,
        sample_workspace,
        created_by="test",
    )
    artifacts = run_backtest(spec_path, root=sample_workspace)

    versions = load_strategy_versions(sample_workspace, "qqq_pullback_15m")
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
        sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml",
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
    assert plan["strategy_name"] == "qqq_pullback_15m"
    assert plan["execution_backend"] == "nautilus_backtest"
    assert plan["selected_backend"] == "nautilus_trader"
    assert plan["bar_type"] == "15m-ohlcv"
    assert dashboard_run.backend_plan_path == str(backend_plan_path)


def test_strategy_versions_diff_and_safe_rollback(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    draft_version = register_strategy_version(spec_path, sample_workspace, created_by="test")
    active_path = activate_strategy(
        spec_path,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
    )
    active_version = load_strategy_versions(sample_workspace, "qqq_pullback_15m")[-1]

    diff = diff_strategy_versions(
        sample_workspace,
        "qqq_pullback_15m",
        draft_version.version_id,
        active_version.version_id,
    )
    rollback = rollback_strategy_version(
        sample_workspace,
        "qqq_pullback_15m",
        active_version.version_id,
    )
    rolled_back = load_strategy_spec(rollback.path)
    catalog = build_dashboard_catalog(sample_workspace)
    rolled_catalog_version = next(
        version
        for version in catalog.versions
        if version.strategy_name == "qqq_pullback_15m"
        and version.version_id == rollback.version.version_id
    )

    assert active_path.exists()
    assert diff.changed
    assert any("paper_auto" in line or "nautilus_trader" in line for line in diff.diff_lines)
    assert rollback.path == sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
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
        '{"timestamp":"2026-01-01T00:00:00Z","llm_sentiment_score":0.8}\n',
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
    backtest = run_backtest(spec_path, root=sample_workspace)
    catalog = build_dashboard_catalog(sample_workspace)

    assert spec.factors["llm_sentiment"].source == "llm_feature"
    assert report.finding("python_mvp_backtest").status == "partial"
    assert report.finding("llm_quant_workflow").status == "partial"
    assert report.backend_plan.status == "partial"
    assert backtest.signals
    strategy = next(
        item for item in catalog.strategies if item.strategy_name == "qqq_llm_feature_15m"
    )
    assert strategy.llm_feature_factor_names == ["llm_sentiment"]
    assert strategy.backend_status == "partial"
