from __future__ import annotations

import json
from pathlib import Path

import yaml

from open_composer.paper_readiness import (
    assess_paper_strategy_readiness,
    write_paper_readiness_report,
)
from open_composer.strategy_lifecycle import activate_strategy


def test_paper_readiness_blocks_default_sample_paper_strategy(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    monkeypatch.setenv("ALPACA_PAPER", "true")
    active = activate_strategy(
        sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml",
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
    )

    report = assess_paper_strategy_readiness(active, sample_workspace)
    json_path, md_path = write_paper_readiness_report(report, sample_workspace)

    assert report.status == "blocked"
    assert report.ready is False
    assert {check.name for check in report.blocking_checks} >= {
        "data_source",
        "alpaca_env",
        "capability_report",
        "promotion_report",
    }
    data_source_check = next(check for check in report.checks if check.name == "data_source")
    assert any("--data-source alpaca" in action for action in data_source_check.suggested_actions)
    assert json_path.exists()
    assert md_path.exists()
    assert "Paper Strategy Readiness" in md_path.read_text(encoding="utf-8")


def test_activate_can_enforce_paper_readiness(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)

    try:
        activate_strategy(
            sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml",
            sample_workspace,
            paper_auto=True,
            allow_paper_auto=True,
            enforce_paper_readiness=True,
        )
    except ValueError as exc:
        assert "paper strategy readiness blocked" in str(exc)
    else:
        raise AssertionError("paper_auto activation should be blocked by readiness")

    report_path = (
        sample_workspace
        / "reports"
        / "paper"
        / "readiness"
        / "qqq_pullback_15m.activation_candidate.json"
    )
    assert report_path.exists()
    assert not (sample_workspace / "strategy_specs" / "active" / "qqq_pullback_15m.yaml").exists()


def test_paper_readiness_passes_for_live_cache_alpaca_strategy(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    account_path = sample_workspace / "reports" / "paper" / "account.json"
    account_path.parent.mkdir(parents=True, exist_ok=True)
    account_path.write_text(
        (
            '{"generated_at":"2026-05-12T12:00:00Z","equity":10000,"cash":5000,'
            '"buying_power":8000,"portfolio_value":10000,"status":"ACTIVE","paper":true}\n'
        ),
        encoding="utf-8",
    )
    promotion_path = (
        sample_workspace / "reports" / "research" / "qqq_paper_ready_15m-promotion.json"
    )
    promotion_path.parent.mkdir(parents=True, exist_ok=True)
    promotion_path.write_text(
        json.dumps(
            {
                "strategy_name": "qqq_paper_ready_15m",
                "source_spec_path": "strategy_specs/active/qqq_paper_ready_15m.yaml",
                "status": "ok",
                "ready": True,
                "gate_summary": {
                    "workflow_pass": True,
                    "research_pass": True,
                    "llm_contribution_pass": None,
                    "paper_ready_pass": True,
                },
                "checks": [
                    {"name": "in_sample", "status": "ok", "message": "ok", "details": {}},
                    {"name": "strict_data", "status": "ok", "message": "ok", "details": {}},
                    {
                        "name": "feature_packets",
                        "status": "ok",
                        "message": "ok",
                        "details": {},
                    },
                    {
                        "name": "benchmark_family",
                        "status": "ok",
                        "message": "ok",
                        "details": {},
                    },
                    {"name": "factor_lab", "status": "ok", "message": "ok", "details": {}},
                    {
                        "name": "execution_reality",
                        "status": "ok",
                        "message": "ok",
                        "details": {},
                    },
                    {
                        "name": "alternative_data",
                        "status": "ok",
                        "message": "ok",
                        "details": {},
                    },
                ],
                "benchmark_family": {"complete": True, "missing": [], "benchmarks": {}},
                "research_manifest": {
                    "research_contract_path": (
                        "reports/research/qqq_paper_ready_15m-research-contract.json"
                    )
                },
                "full_window": {
                    "run_id": "full",
                    "bars": 10,
                    "signals": 2,
                    "trades": 1,
                    "total_return_pct": 1.0,
                    "annualized_return_pct": 2.0,
                    "sharpe_ratio": 1.0,
                    "data_sanity_status": "ok",
                    "evidence_level": "E1_single_source_research",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    draft = sample_workspace / "strategy_specs" / "drafts" / "qqq_paper_ready_15m.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "qqq_paper_ready_15m"
    raw["required_capabilities"] = ["market.sample_ohlcv"]
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active = activate_strategy(
        draft,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
        data_source="alpaca",
    )

    report = assess_paper_strategy_readiness(active, sample_workspace)

    assert report.ready is True
    assert report.status == "ok"
    assert {check.name: check.status for check in report.checks}["data_source"] == "ok"
    assert {check.name: check.status for check in report.checks}["alpaca_env"] == "ok"
    assert {check.name: check.status for check in report.checks}["account_snapshot"] == "ok"
    assert {check.name: check.status for check in report.checks}["portfolio_risk"] == "ok"
    assert report.gate_summary["paper_ready_pass"] is True


def test_paper_readiness_requires_research_contract_and_new_promotion_checks(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    promotion_path = (
        sample_workspace / "reports" / "research" / "qqq_missing_research_contract-promotion.json"
    )
    promotion_path.parent.mkdir(parents=True, exist_ok=True)
    promotion_path.write_text(
        json.dumps(
            {
                "strategy_name": "qqq_missing_research_contract",
                "source_spec_path": "strategy_specs/active/qqq_missing_research_contract.yaml",
                "status": "ok",
                "ready": True,
                "gate_summary": {"paper_ready_pass": True},
                "checks": [
                    {"name": "strict_data", "status": "ok", "message": "ok", "details": {}},
                    {"name": "feature_packets", "status": "ok", "message": "ok", "details": {}},
                    {"name": "benchmark_family", "status": "ok", "message": "ok", "details": {}},
                ],
                "benchmark_family": {"complete": True, "missing": [], "benchmarks": {}},
            }
        ),
        encoding="utf-8",
    )
    draft = sample_workspace / "strategy_specs" / "drafts" / "qqq_missing_research_contract.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "qqq_missing_research_contract"
    raw["required_capabilities"] = ["market.sample_ohlcv"]
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active = activate_strategy(
        draft,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
        data_source="alpaca",
    )

    report = assess_paper_strategy_readiness(active, sample_workspace)
    promotion_check = next(check for check in report.checks if check.name == "promotion_report")

    assert promotion_check.status == "blocked"
    assert "factor_lab check is not ok" in promotion_check.message
    assert "research contract path is missing" in promotion_check.message


def test_paper_readiness_blocks_incomplete_feature_packets(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    account_path = sample_workspace / "reports" / "paper" / "account.json"
    account_path.parent.mkdir(parents=True, exist_ok=True)
    account_path.write_text(
        (
            '{"generated_at":"2026-05-12T12:00:00Z","equity":10000,"cash":5000,'
            '"buying_power":8000,"portfolio_value":10000,"status":"ACTIVE","paper":true}\n'
        ),
        encoding="utf-8",
    )
    feature_path = sample_workspace / "feature_logs" / "qqq_llm_features.jsonl"
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    feature_path.write_text(
        (
            '{"timestamp":"2026-01-01T00:00:00Z","source":"llm","symbol":"QQQ",'
            '"dedupe_key":"llm:qqq:1","llm_sentiment":0.8}\n'
        ),
        encoding="utf-8",
    )
    draft = sample_workspace / "strategy_specs" / "drafts" / "qqq_paper_llm_15m.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "qqq_paper_llm_15m"
    raw["factors"] = {
        **raw.get("factors", {}),
        "llm_sentiment": {
            "source": "llm_feature",
            "path": "feature_logs/qqq_llm_features.jsonl",
            "field": "llm_sentiment",
            "default": 0.0,
            "description": "Saved LLM sentiment replay input.",
        },
    }
    raw["entry"]["all"].append("llm_sentiment > 0.5")
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active = activate_strategy(
        draft,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
        data_source="alpaca",
    )

    report = assess_paper_strategy_readiness(active, sample_workspace)
    feature_check = next(check for check in report.checks if check.name == "feature_packets")

    assert report.ready is False
    assert feature_check.status == "blocked"
    assert "PIT-complete replay packets" in feature_check.message
    assert "published_at is missing" in feature_check.message


def test_paper_readiness_blocks_feature_packets_without_evidence(
    sample_workspace: Path,
) -> None:
    feature_path = sample_workspace / "feature_logs" / "qqq_llm_features.jsonl"
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    feature_path.write_text(
        (
            '{"timestamp":"2026-01-01T00:00:00Z","published_at":"2026-01-01T00:00:00Z",'
            '"fetched_at":"2026-01-01T00:01:00Z","visible_at":"2026-01-01T00:01:00Z",'
            '"source":"llm","symbol":"QQQ","dedupe_key":"llm:qqq:1",'
            '"schema_version":"1","llm_sentiment":0.8}\n'
        ),
        encoding="utf-8",
    )
    draft = sample_workspace / "strategy_specs" / "drafts" / "qqq_paper_llm_15m.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "qqq_paper_llm_15m"
    raw["factors"] = {
        **raw.get("factors", {}),
        "llm_sentiment": {
            "source": "llm_feature",
            "path": "feature_logs/qqq_llm_features.jsonl",
            "field": "llm_sentiment",
            "default": 0.0,
            "description": "Saved LLM sentiment replay input.",
        },
    }
    raw["entry"]["all"].append("llm_sentiment > 0.5")
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active = activate_strategy(
        draft,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
        data_source="alpaca",
    )

    report = assess_paper_strategy_readiness(active, sample_workspace)
    feature_check = next(check for check in report.checks if check.name == "feature_packets")

    assert report.ready is False
    assert feature_check.status == "blocked"
    assert "marginal lift" in feature_check.message
    assert feature_check.details["missing_evidence"]
