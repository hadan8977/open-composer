from __future__ import annotations

import json
from pathlib import Path
from shutil import copyfile
from types import SimpleNamespace

import yaml

from open_composer.adapters.broker import alpaca_paper
from open_composer.adapters.events import fetch_capability_events
from open_composer.capabilities import evaluate_capabilities
from open_composer.context import build_signal_context
from open_composer.engines.backtest_engine import run_backtest
from open_composer.engines.scanner_engine import run_scan
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research import draft_strategy_from_idea, optimize_strategy
from open_composer.research.alternative_data_evidence import build_alternative_data_evidence
from open_composer.research.short_risk import build_short_risk_report


def test_signal_context_excludes_future_records(sample_workspace: Path) -> None:
    fetch_capability_events("sec", sample_workspace, ["QQQ"], offline=True)
    fetch_capability_events("alpha_vantage", sample_workspace, ["QQQ"], offline=True)
    fetch_capability_events("fred", sample_workspace, None, offline=True)
    artifacts = run_backtest(
        sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml",
        root=sample_workspace,
    )
    context = build_signal_context(artifacts.signals[0].id, sample_workspace)
    assert context.events
    assert context.macro
    assert all(event.published_at <= artifacts.signals[0].timestamp for event in context.events)


def test_natural_language_to_context_to_paper_mock(sample_workspace: Path, monkeypatch) -> None:
    idea = (
        "Create a QQQ 15m pullback strategy with SEC filings, FRED macro, "
        "Alpha Vantage news, GDELT broad events, and Alpaca Paper later."
    )
    spec_path = draft_strategy_from_idea(idea, sample_workspace)
    spec = load_strategy_spec(spec_path)
    assert "events.sec_filings" in spec.required_capabilities
    research_plan = json.loads(
        (
            sample_workspace / "reports" / "research" / f"{spec.name}-draft-research-plan.json"
        ).read_text(encoding="utf-8")
    )
    assert research_plan["research_brief"]["strategy_name"] == spec.name
    assert research_plan["search_space"]["candidate_count"] >= 1
    assert "promotion_report" in research_plan["default_validation"]
    assert all(evaluation.passed for evaluation in evaluate_capabilities(sample_workspace))

    fetch_capability_events("sec", sample_workspace, ["QQQ"], offline=True)
    fetch_capability_events("alpha_vantage", sample_workspace, ["QQQ"], offline=True)
    fetch_capability_events("gdelt", sample_workspace, ["QQQ"], offline=True)
    fetch_capability_events("fred", sample_workspace, None, offline=True)

    artifacts = run_backtest(spec_path, root=sample_workspace)
    assert artifacts.signals
    latest_signals = run_scan(spec_path, root=sample_workspace)
    assert latest_signals
    context = build_signal_context(latest_signals[0].id, sample_workspace)
    assert context.news

    active_spec_path = sample_workspace / "strategy_specs" / "active" / f"{spec.name}.yaml"
    copyfile(spec_path, active_spec_path)
    raw = yaml.safe_load(active_spec_path.read_text(encoding="utf-8"))
    raw["lifecycle"] = "active"
    raw["execution"]["mode"] = "paper_auto"
    raw["execution"]["broker"] = "alpaca_paper"
    active_spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active_spec = load_strategy_spec(active_spec_path)

    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")

    def fake_submit(client, signal_arg, qty, client_order_id):
        return SimpleNamespace(id="paper_order_1", status="accepted")

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(equity="10000")

    monkeypatch.setattr(alpaca_paper, "_submit_market_order", fake_submit)
    order = alpaca_paper.submit_paper_order(
        latest_signals[0], active_spec, sample_workspace, client=MockClient()
    )
    assert order.paper
    assert order.client_order_id == f"oc-{latest_signals[0].id}"
    assert order.version_id == latest_signals[0].version_id
    assert order.spec_hash == latest_signals[0].spec_hash


def test_chinese_memory_storage_prompt_optimizes_and_scans(sample_workspace: Path) -> None:
    idea = "针对最近的内存存储的动能做一个日内的策略，先手动实盘，模拟盘可以自动交易"
    spec_path = draft_strategy_from_idea(idea, sample_workspace)
    spec = load_strategy_spec(spec_path)
    assert spec.name == "memory_storage_momentum_15m"
    assert spec.primary_symbol == "MU"
    assert "market.memory_storage_sample" in spec.required_capabilities

    result = optimize_strategy(spec_path, sample_workspace, min_return_pct=1.0, min_signals=1)
    assert result.best_artifacts.run.total_return_pct >= 1.0
    assert result.best_artifacts.run.signals >= 1
    assert result.report_path.exists()

    aggressive_result = optimize_strategy(
        spec_path, sample_workspace, min_return_pct=3.0, min_signals=1
    )
    assert aggressive_result.best_spec.name.startswith("memory_storage_momentum_15m_optimized_")
    assert aggressive_result.best_artifacts.run.total_return_pct >= 3.0

    fetch_capability_events("sec", sample_workspace, ["MU"], offline=True)
    fetch_capability_events("alpha_vantage", sample_workspace, ["MU"], offline=True)
    fetch_capability_events("gdelt", sample_workspace, ["MU"], offline=True)
    fetch_capability_events("fred", sample_workspace, None, offline=True)
    latest_signals = run_scan(result.best_spec_path, root=sample_workspace)
    context = build_signal_context(latest_signals[0].id, sample_workspace)
    assert context.events
    assert context.news
    assert context.macro


def test_short_risk_report_writes_harness_artifacts(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_short_risk.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "qqq_short_risk"
    raw["position_direction"] = "long_short"
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    result = build_short_risk_report(spec_path, sample_workspace)

    assert result.status == "ok"
    assert result.report_path.exists()
    assert result.source_cards_path.exists()
    assert result.borrow_cost_path.exists()
    assert result.squeeze_stress_path.exists()
    assert result.dividend_risk_path.exists()
    assert result.exposure_policy_path.exists()
    policy = json.loads(result.exposure_policy_path.read_text(encoding="utf-8"))
    assert policy["paper_auto_default"] == "blocked"
    assert policy["position_direction"] == "long_short"


def test_alternative_data_evidence_marks_non_trading_llm_as_advisory(
    sample_workspace: Path,
) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_advisory_llm.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "qqq_advisory_llm"
    raw["llm_review"] = {"enabled": True}
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    result = build_alternative_data_evidence(spec_path, sample_workspace)

    assert result.status == "ok"
    assert result.advisory_only is True
    pit = json.loads(result.pit_replay_path.read_text(encoding="utf-8"))
    lift = json.loads(result.marginal_lift_path.read_text(encoding="utf-8"))
    robustness = json.loads(result.modality_robustness_path.read_text(encoding="utf-8"))
    assert pit["replay_method"] == "not_applicable_advisory_only"
    assert lift["robustness_check"] == "advisory_only"
    assert robustness["fallback_behavior"] == "ignore_advisory_context"


def test_alpaca_cache_strategy_meets_target_thresholds(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    spec_path = (
        sample_workspace
        / "strategy_specs"
        / "drafts"
        / "mu_breakout_volume_15m_optimized_volume_plus.yaml"
    )
    cache_path = sample_workspace / "data" / "cache" / "mu_15m_iex.csv"
    copyfile(
        repo_root
        / "strategy_specs"
        / "drafts"
        / "mu_breakout_volume_15m_optimized_volume_plus.yaml",
        spec_path,
    )
    copyfile(repo_root / "data" / "sample" / "mu_15m.csv", cache_path)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["data"] = {
        **raw["data"],
        "source": "alpaca",
        "symbol": "MU",
        "path": None,
        "feed": "iex",
    }
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    result = optimize_strategy(
        spec_path,
        sample_workspace,
        min_return_pct=15,
        min_signals=1,
        min_sharpe=1.5,
    )

    assert result.best_spec.name.endswith("optimized_volume_plus")
    assert result.best_artifacts.run.annualized_return_pct is not None
    assert result.best_artifacts.run.annualized_return_pct >= 15
    assert result.best_artifacts.run.sharpe_ratio is not None
    assert result.best_artifacts.run.sharpe_ratio >= 1.5
    assert result.best_artifacts.run.total_return_pct > 0
    report_text = result.report_path.read_text(encoding="utf-8")
    assert "Minimum Sharpe target: 1.50" in report_text
    assert "optimized_volume_plus" in report_text
    artifacts = run_backtest(result.best_spec_path, root=sample_workspace)
    backtest_text = Path(artifacts.run.report_path or "").read_text(encoding="utf-8")
    assert "Data provenance: alpaca cache." in backtest_text
