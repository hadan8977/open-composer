from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

import open_composer.cli as cli_module
import open_composer.paper_authorization as paper_authorization
from open_composer.cli import app
from open_composer.execution_policy import resolve_execution_policy
from open_composer.market_calendar import next_us_equity_session
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.paper_authorization import (
    assess_paper_canary_authorization,
    paper_authorization_archive_path,
    paper_canary_revocation_archive_path,
    paper_canary_revocation_path,
    write_paper_canary_authorization,
    write_paper_canary_revocation,
    write_paper_order_authorization,
)
from open_composer.paper_controls import clear_paper_kill_switch
from open_composer.paper_lock import paper_control_lock
from open_composer.paper_readiness import (
    PaperStrategyReadinessCheck,
    assess_paper_strategy_readiness,
    assess_paper_strategy_readiness_for_spec,
    write_paper_readiness_report,
)
from open_composer.strategy_lifecycle import activate_strategy
from open_composer.strategy_versions import strategy_content_hash


def test_paper_readiness_blocks_default_sample_paper_strategy(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    monkeypatch.setenv("ALPACA_PAPER", "true")
    active = activate_strategy(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
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


def test_paper_readiness_requires_an_explicit_kill_switch_control_file(
    sample_workspace: Path,
) -> None:
    (sample_workspace / "reports" / "paper" / "kill_switch.json").unlink()

    report = assess_paper_strategy_readiness(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
        sample_workspace,
    )
    check = next(item for item in report.checks if item.name == "kill_switch")

    assert check.status == "blocked"
    assert check.details["control_file_present"] is False
    assert "fail closed" in check.message


def test_activate_can_enforce_paper_readiness(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)

    try:
        activate_strategy(
            sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
            sample_workspace,
            paper_auto=True,
            allow_paper_auto=True,
            enforce_paper_readiness=True,
        )
    except ValueError as exc:
        assert "paper strategy readiness not order-authorized" in str(exc)
    else:
        raise AssertionError("paper_auto activation should be blocked by readiness")

    report_path = (
        sample_workspace
        / "reports"
        / "paper"
        / "readiness"
        / "fixture_pullback_15m.activation_candidate.json"
    )
    assert report_path.exists()
    assert not (
        sample_workspace / "strategy_specs" / "active" / "fixture_pullback_15m.yaml"
    ).exists()


def test_candidate_paper_readiness_capability_uses_candidate_spec(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    source = load_strategy_spec(draft)
    raw = source.model_dump(mode="json")
    raw["lifecycle"] = "active"
    raw["execution"] = {
        **raw["execution"],
        "backend": "nautilus_trader",
        "mode": "paper_auto",
        "broker": "alpaca_paper",
    }
    raw["data"] = {**raw["data"], "source": "alpaca", "path": None}
    candidate = StrategySpec.model_validate(raw)

    report = assess_paper_strategy_readiness_for_spec(candidate, sample_workspace, spec_path=draft)
    capability_check = next(check for check in report.checks if check.name == "capability_report")

    assert capability_check.status in {"ok", "warning"}
    assert "strategy must be promoted to lifecycle=active" not in capability_check.message
    assert "execution.mode must be paper_auto" not in capability_check.message


def test_paper_readiness_passes_for_live_cache_alpaca_strategy(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _write_paper_account_snapshot(sample_workspace)
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
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
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

    assert report.ready is False
    assert report.status == "blocked"
    assert {check.name: check.status for check in report.checks}["data_source"] == "ok"
    assert {check.name: check.status for check in report.checks}["alpaca_env"] == "ok"
    assert {check.name: check.status for check in report.checks}["account_snapshot"] == "ok"
    assert {check.name: check.status for check in report.checks}["portfolio_risk"] == "ok"
    assert report.gate_summary["paper_ready_pass"] is False
    harness_check = {check.name: check for check in report.checks}.get("harness_artifacts")
    assert harness_check is not None, "harness_artifacts check must run for paper_auto specs"
    assert harness_check.status == "blocked"


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
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
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
    _write_paper_account_snapshot(sample_workspace)
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
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
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
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
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


def test_paper_readiness_accepts_adaptive_router_portfolio_routing(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    draft = sample_workspace / "strategy_specs" / "drafts" / "adaptive_router_portfolio.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "adaptive_router_portfolio"
    raw["universe"] = ["AAPL", "MSFT", "NVDA"]
    raw["timeframe"] = "1m"
    raw["data"] = {"source": "alpaca", "symbol": "AAPL", "feed": "iex"}
    raw["required_capabilities"] = ["market.alpaca_bars"]
    raw["portfolio"] = {
        "mode": "adaptive_intraday_internal_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 0.15,
        "max_symbol_weight": 0.15,
        "same_day_flatten": True,
        "duplicate_signal_policy": "stable_signal_id",
        "selected_route_label": "open_momentum:lb5_entry1_top1_open0_mom0_rv0.8_none",
    }
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")

    report = assess_paper_strategy_readiness(draft, sample_workspace)
    checks = {check.name: check for check in report.checks}

    assert checks["portfolio_routing"].status == "ok"
    assert checks["portfolio_risk"].status == "ok"
    assert checks["alpaca_env"].status == "blocked"


def test_paper_readiness_accepts_hybrid_router_portfolio_routing(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    draft = sample_workspace / "strategy_specs" / "drafts" / "hybrid_router_portfolio.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "hybrid_router_portfolio"
    raw["universe"] = ["AAPL", "MSFT", "NVDA"]
    raw["timeframe"] = "1m"
    raw["data"] = {"source": "alpaca", "symbol": "AAPL", "feed": "iex"}
    raw["required_capabilities"] = ["market.alpaca_bars"]
    raw["portfolio"] = {
        "mode": "hybrid_adaptive_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": False,
        "duplicate_signal_policy": "stable_signal_id",
        "selected_route_label": "open_to_open:lb20_top1_qsm50_min0_w1",
    }
    raw["risk"]["max_position_weight"] = 1.0
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")

    report = assess_paper_strategy_readiness(draft, sample_workspace)
    checks = {check.name: check for check in report.checks}

    assert checks["portfolio_routing"].status == "ok"
    assert checks["portfolio_risk"].status == "ok"
    assert checks["alpaca_env"].status == "blocked"


def test_paper_readiness_blocks_static_current_symbol_universe(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _write_paper_account_snapshot(sample_workspace)
    draft = sample_workspace / "strategy_specs" / "drafts" / "static_universe_router.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "static_universe_router"
    raw["universe"] = ["AAPL", "MSFT", "NVDA"]
    raw["data"] = {"source": "alpaca", "symbol": "AAPL", "feed": "iex"}
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active = activate_strategy(
        draft,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
        data_source="alpaca",
    )

    report = assess_paper_strategy_readiness(active, sample_workspace)
    checks = {check.name: check for check in report.checks}

    assert report.ready is False
    assert checks["universe_audit"].status == "blocked"
    assert "point-in-time universe membership" in checks["universe_audit"].message


def test_paper_readiness_router_can_be_observation_only_when_evidence_exists(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _write_paper_account_snapshot(sample_workspace)
    draft = sample_workspace / "strategy_specs" / "drafts" / "beta_router_observation.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "beta_router_observation"
    raw["timeframe"] = "daily"
    raw["universe"] = ["QQQ", "TQQQ", "SQQQ"]
    raw["data"] = {"source": "alpaca", "symbol": "QQQ", "feed": "iex"}
    raw["required_capabilities"] = ["market.alpaca_bars"]
    raw["notes"] = {
        **raw.get("notes", {}),
        "universe_audit": {
            "point_in_time_membership": True,
            "selection_timestamp": "2026-05-22T00:00:00Z",
            "delisting_policy": "Fixed ETF route; no current equity-index membership backfill.",
        },
    }
    raw["risk"]["max_position_weight"] = 1.0
    raw["portfolio"] = {
        "mode": "beta_exposure_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": False,
        "selected_route_label": (
            "beta:sma200_mom120_min0_vol20_maxvnone_dd120_maxddnone_"
            "levsmanone_levmaxvnone_levdd60_levmaxddnone_"
            "onTQQQ1_neuQQQ1_offCASH0_vtnone"
        ),
    }
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active = activate_strategy(
        draft,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
        data_source="alpaca",
    )

    _write_ready_promotion(sample_workspace, "beta_router_observation")
    _write_router_harness_artifacts(sample_workspace, "beta_router_observation")
    _write_paper_validation_days(sample_workspace, active)

    report = assess_paper_strategy_readiness(active, sample_workspace)

    assert report.ready is False
    assert report.execution_substate == "observation_only"
    assert report.gate_summary["paper_ready_pass"] is False
    assert report.gate_summary["execution_substate"] == "observation_only"


def test_full_paper_authorization_is_disabled_even_with_complete_artifacts(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _write_paper_account_snapshot(sample_workspace)
    draft = sample_workspace / "strategy_specs" / "drafts" / "beta_router_authorized.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "beta_router_authorized"
    raw["timeframe"] = "daily"
    raw["universe"] = ["QQQ", "TQQQ", "SQQQ"]
    raw["data"] = {"source": "alpaca", "symbol": "QQQ", "feed": "iex"}
    raw["required_capabilities"] = ["market.alpaca_bars"]
    raw["notes"] = {
        **raw.get("notes", {}),
        "universe_audit": {
            "point_in_time_membership": True,
            "selection_timestamp": "2026-05-22T00:00:00Z",
            "delisting_policy": "Fixed ETF route; no current equity-index membership backfill.",
        },
    }
    raw["risk"]["max_position_weight"] = 1.0
    raw["portfolio"] = {
        "mode": "beta_exposure_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": False,
        "selected_route_label": (
            "beta:sma200_mom120_min0_vol20_maxvnone_dd120_maxddnone_"
            "levsmanone_levmaxvnone_levdd60_levmaxddnone_"
            "onTQQQ1_neuQQQ1_offCASH0_vtnone"
        ),
    }
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active = activate_strategy(
        draft,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
        data_source="alpaca",
    )

    _write_ready_promotion(sample_workspace, "beta_router_authorized")
    _write_router_harness_artifacts(sample_workspace, "beta_router_authorized")
    _write_paper_validation_days(sample_workspace, active)
    _mock_matched_paper_tca_pass(monkeypatch)
    with pytest.raises(ValueError, match="Full paper order authorization is disabled"):
        _write_router_order_authorization(sample_workspace, "beta_router_authorized")

    report = assess_paper_strategy_readiness(active, sample_workspace)

    assert report.ready is False
    assert report.execution_substate == "observation_only"
    assert report.gate_summary["paper_ready_pass"] is False
    assert report.gate_summary["execution_substate"] == "observation_only"

    data_manifest = (
        sample_workspace / "reports" / "research" / "beta_router_authorized-data-manifest.json"
    )
    data_manifest.write_text('{"immutable":false}\n', encoding="utf-8")
    stale = assess_paper_strategy_readiness(active, sample_workspace)
    checks = {check.name: check for check in stale.checks}
    assert stale.ready is False
    assert stale.execution_substate == "blocked"
    assert checks["promotion_report"].status == "blocked"
    assert checks["order_authorization"].status == "warning"


def test_bounded_canary_is_orderable_without_claiming_full_readiness(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    active = _write_beta_router_active(sample_workspace, "beta_router_canary")
    active_payload = yaml.safe_load(active.read_text(encoding="utf-8"))
    active_payload["notes"] = {
        **active_payload.get("notes", {}),
        "minimum_bound_forward_sessions": 1,
        "paper_validation_start": "2026-07-01",
    }
    active.write_text(yaml.safe_dump(active_payload), encoding="utf-8")
    _write_ready_promotion(sample_workspace, "beta_router_canary")
    _write_router_harness_artifacts(sample_workspace, "beta_router_canary")
    _write_paper_account_snapshot(sample_workspace)
    _write_empty_broker_sync(sample_workspace)
    clear_paper_kill_switch(sample_workspace, updated_by="test")
    _write_forward_observation_day(sample_workspace, active, date(2026, 7, 1))
    _write_canary_safety_review(sample_workspace, "beta_router_canary")
    spec = load_strategy_spec(active)

    authorization_path = write_paper_canary_authorization(
        spec,
        sample_workspace,
        authorized_by="test_operator",
        confirm_paper_only=True,
        confirm_canary_risk=True,
        duration_days=7,
        max_order_notional=500,
        max_session_notional=1000,
        max_total_notional=2000,
        max_orders_per_session=2,
        max_total_orders=4,
    )

    authorization = assess_paper_canary_authorization(spec, sample_workspace)
    report = assess_paper_strategy_readiness(active, sample_workspace)
    assert authorization_path.is_file()
    authorization_payload = json.loads(authorization_path.read_text(encoding="utf-8"))
    authorization_archive = paper_authorization_archive_path(
        sample_workspace,
        spec,
        authorization_payload["authorization_id"],
    )
    assert authorization_archive.is_file()
    assert json.loads(authorization_archive.read_text(encoding="utf-8")) == authorization_payload
    assert authorization_payload["authorization_sequence"] == 1
    assert authorization_payload["previous_authorization_id"] is None
    assert authorization_payload["exclusive_account_writer"] == "open_composer_only"
    assert authorization.authorized is True
    assert authorization.kind == "canary"
    assert report.status == "warning"
    assert report.execution_substate == "canary_authorized"
    assert report.ready is False
    assert report.gate_summary["paper_canary_pass"] is True
    assert report.gate_summary["paper_ready_pass"] is False

    write_paper_canary_authorization(
        spec,
        sample_workspace,
        authorized_by="test_operator",
        confirm_paper_only=True,
        confirm_canary_risk=True,
        duration_days=7,
        max_order_notional=500,
        max_session_notional=1000,
        max_total_notional=2000,
        max_orders_per_session=2,
        max_total_orders=4,
    )
    replacement_payload = json.loads(authorization_path.read_text(encoding="utf-8"))
    assert replacement_payload["authorization_sequence"] == 2
    assert (
        replacement_payload["previous_authorization_id"]
        == authorization_payload["authorization_id"]
    )

    revocation_path = write_paper_canary_revocation(
        spec,
        sample_workspace,
        revoked_by="test_operator",
        reason="test completed",
    )
    revocation_payload = json.loads(revocation_path.read_text(encoding="utf-8"))
    revocation_archive = paper_canary_revocation_archive_path(
        sample_workspace,
        spec,
        revocation_payload["revocation_id"],
    )
    assert revocation_archive.is_file()
    assert json.loads(revocation_archive.read_text(encoding="utf-8")) == revocation_payload
    paper_canary_revocation_path(sample_workspace, spec).unlink()
    revoked = assess_paper_canary_authorization(spec, sample_workspace)
    after = assess_paper_strategy_readiness(active, sample_workspace)
    assert revoked.authorized is False
    assert "revoked" in revoked.details["mismatches"]
    assert after.execution_substate == "observation_only"

    authorization_path.write_text(
        json.dumps(authorization_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rolled_back = assess_paper_canary_authorization(spec, sample_workspace)
    assert rolled_back.authorized is False
    assert "authorization_superseded" in rolled_back.details["mismatches"]


def test_canary_authorization_cli_help_smoke() -> None:
    result = CliRunner().invoke(app, ["paper", "authorize-canary", "--help"])
    assert result.exit_code == 0, result.output
    assert "--confirm-canary-risk" in result.output
    assert "--max-order-notional" in result.output


def test_canary_review_requires_exclusive_account_writer_binding(
    sample_workspace: Path,
) -> None:
    spec = load_strategy_spec(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    )
    policy = SimpleNamespace(policy_id="test-policy", content_hash="1" * 64)
    authorization = {
        "promotion_report_hash": "2" * 64,
        "data_manifest_hash": "3" * 64,
        "harness_verify_hash": "4" * 64,
        "broker_account_id_hash": "5" * 64,
        "limits": {
            "max_order_notional_usd": 500,
            "max_session_notional_usd": 1000,
            "max_total_notional_usd": 2000,
            "max_orders_per_session": 2,
            "max_total_orders": 4,
        },
    }
    review = {
        "strategy_name": spec.name,
        "spec_hash": strategy_content_hash(spec),
        "execution_policy_id": policy.policy_id,
        "execution_policy_hash": policy.content_hash,
        "promotion_report_hash": authorization["promotion_report_hash"],
        "data_manifest_hash": authorization["data_manifest_hash"],
        "harness_verify_hash": authorization["harness_verify_hash"],
        "overall": "approved",
        "blocking_items": [],
        "harness_verify_pass": True,
        "kill_switch_verified": True,
        "signal_order_linkage": True,
        "credential_scope": "paper_only",
        "maximum_canary_limits": dict(authorization["limits"]),
    }
    path = sample_workspace / "canary-review.json"
    path.write_text(json.dumps(review), encoding="utf-8")

    missing = paper_authorization._canary_review_mismatches(
        path,
        spec,
        policy,
        authorization,
    )

    assert "canary_safety_review.exclusive_account_writer" in missing
    assert "canary_safety_review.broker_account_id_hash" in missing

    review["exclusive_account_writer"] = "open_composer_only"
    review["broker_account_id_hash"] = authorization["broker_account_id_hash"]
    path.write_text(json.dumps(review), encoding="utf-8")
    assert (
        paper_authorization._canary_review_mismatches(
            path,
            spec,
            policy,
            authorization,
        )
        == []
    )


def test_canary_revocation_is_serialized_with_final_control_check(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec = load_strategy_spec(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    )
    worker_started = Event()
    mutation_started = Event()
    expected = sample_workspace / "revocation.json"

    def fake_locked(*args, **kwargs):
        mutation_started.set()
        return expected

    monkeypatch.setattr(
        paper_authorization,
        "_write_paper_canary_revocation_locked",
        fake_locked,
    )

    def revoke():
        worker_started.set()
        return write_paper_canary_revocation(
            spec,
            sample_workspace,
            revoked_by="test",
            reason="concurrent stop",
        )

    with ThreadPoolExecutor(max_workers=1) as executor:
        with paper_control_lock(sample_workspace):
            future = executor.submit(revoke)
            assert worker_started.wait(timeout=1)
            assert mutation_started.wait(timeout=0.1) is False
        assert future.result(timeout=1) == expected
    assert mutation_started.is_set()


def test_submission_revalidation_rejects_changed_authorization_hash(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec = load_strategy_spec(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    )
    expected = paper_authorization.PaperOrderAuthorizationStatus(
        authorized=True,
        message="initial",
        path=sample_workspace / "authorization.json",
        content_hash="a" * 64,
        payload={"authorization_id": "auth_" + "a" * 16},
        kind="full",
    )
    changed = paper_authorization.PaperOrderAuthorizationStatus(
        authorized=True,
        message="replacement",
        path=expected.path,
        content_hash="b" * 64,
        payload=expected.payload,
        kind="full",
    )
    monkeypatch.setattr(
        paper_authorization,
        "assess_paper_order_authorization",
        lambda _spec, _root: changed,
    )

    with pytest.raises(
        ValueError, match="changed after order intent reservation: authorization_hash"
    ):
        paper_authorization.revalidate_paper_submission_authorization(
            spec,
            sample_workspace,
            expected,
        )


def test_doctor_reports_alpaca_paper_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_PAPER", raising=False)
    getenv = cli_module.os.getenv
    monkeypatch.setattr(
        cli_module.os,
        "getenv",
        lambda name, default=None: default if name == "ALPACA_PAPER" else getenv(name, default),
    )

    result = CliRunner().invoke(app, ["doctor", "--plain"])

    assert result.exit_code == 0
    assert "ALPACA_PAPER\tfalse\tmust be true for paper orders" in result.output


def test_router_full_authorization_cli_is_disabled_before_readiness(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_COMPOSER_ROOT", str(sample_workspace))
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    _write_beta_router_active(sample_workspace, "beta_router_cli_blocked")
    _write_ready_promotion(sample_workspace, "beta_router_cli_blocked")

    result = CliRunner().invoke(
        app,
        [
            "paper",
            "authorize-router",
            "beta_router_cli_blocked",
            "--authorized-by",
            "test_operator",
            "--confirm-paper-only",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code != 0
    assert "Full paper order authorization is disabled" in result.output
    assert not (
        sample_workspace
        / "reports"
        / "harness"
        / "paper"
        / "beta_router_cli_blocked-router-order-authorization.json"
    ).exists()


def test_router_full_authorization_cli_is_explicitly_disabled(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_COMPOSER_ROOT", str(sample_workspace))
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    active = _write_beta_router_active(sample_workspace, "beta_router_cli_authorized")
    _write_ready_promotion(sample_workspace, "beta_router_cli_authorized")
    _write_router_harness_artifacts(sample_workspace, "beta_router_cli_authorized")
    _write_paper_account_snapshot(sample_workspace)
    _write_paper_validation_days(sample_workspace, active)
    _mock_matched_paper_tca_pass(monkeypatch)

    result = CliRunner().invoke(
        app,
        [
            "paper",
            "authorize-router",
            "beta_router_cli_authorized",
            "--authorized-by",
            "test_operator",
            "--confirm-paper-only",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code != 0
    assert "Full paper order authorization is disabled" in result.output
    auth_path = (
        sample_workspace
        / "reports"
        / "harness"
        / "paper"
        / "beta_router_cli_authorized-router-order-authorization.json"
    )
    assert not auth_path.exists()
    report = assess_paper_strategy_readiness(active, sample_workspace)
    assert report.status == "warning"
    assert report.execution_substate == "observation_only"


def test_paper_readiness_sample_acquisition_tier_blocks_live_paper(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "qqq_sample_tier_blocked"
    raw["lifecycle"] = "active"
    raw["execution"] = {
        **raw["execution"],
        "backend": "nautilus_trader",
        "mode": "paper_auto",
        "broker": "alpaca_paper",
    }
    raw["data"] = {"source": "alpaca", "symbol": "QQQ", "feed": "iex"}
    raw["data_assumptions"] = {
        **raw.get("data_assumptions", {}),
        "acquisition_tier": "sample_smoke",
    }
    spec = StrategySpec.model_validate(raw)

    report = assess_paper_strategy_readiness_for_spec(spec, sample_workspace)
    checks = {check.name: check for check in report.checks}

    assert report.execution_substate == "blocked"
    assert checks["data_source"].status == "blocked"
    assert "sample_smoke" in checks["data_source"].message


def _write_beta_router_active(root: Path, strategy_name: str) -> Path:
    raw = yaml.safe_load(
        (root / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = strategy_name
    raw["timeframe"] = "daily"
    raw["universe"] = ["QQQ", "TQQQ", "SQQQ"]
    raw["lifecycle"] = "active"
    raw["data"] = {"source": "alpaca", "symbol": "QQQ", "feed": "iex"}
    raw["required_capabilities"] = ["market.alpaca_bars"]
    raw["execution"] = {
        **raw["execution"],
        "backend": "nautilus_trader",
        "mode": "paper_auto",
        "broker": "alpaca_paper",
    }
    raw["notes"] = {
        **raw.get("notes", {}),
        "universe_audit": {
            "point_in_time_membership": True,
            "selection_timestamp": "2026-05-22T00:00:00Z",
            "delisting_policy": "Fixed ETF route; no current equity-index membership backfill.",
        },
    }
    raw["risk"]["max_position_weight"] = 1.0
    raw["portfolio"] = {
        "mode": "beta_exposure_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": False,
        "selected_route_label": (
            "beta:sma200_mom120_min0_vol20_maxvnone_dd120_maxddnone_"
            "levsmanone_levmaxvnone_levdd60_levmaxddnone_"
            "onTQQQ1_neuQQQ1_offCASH0_vtnone"
        ),
    }
    active = root / "strategy_specs" / "active" / f"{strategy_name}.yaml"
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return active


def _write_paper_account_snapshot(root: Path) -> None:
    generated_at = datetime.now(UTC).isoformat()
    account_path = root / "reports" / "paper" / "account.json"
    positions_path = root / "reports" / "paper" / "positions.json"
    account_path.parent.mkdir(parents=True, exist_ok=True)
    account_path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "equity": 10000,
                "cash": 5000,
                "buying_power": 8000,
                "portfolio_value": 10000,
                "broker_account_id_hash": hashlib.sha256(b"paper-account-test").hexdigest(),
                "status": "ACTIVE",
                "paper": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    positions_path.write_text(
        json.dumps({"generated_at": generated_at, "paper": True, "positions": []}) + "\n",
        encoding="utf-8",
    )


def _write_ready_promotion(root: Path, strategy_name: str) -> None:
    spec = load_strategy_spec(root / "strategy_specs" / "active" / f"{strategy_name}.yaml")
    contract_path = root / "reports" / "research" / f"{strategy_name}-contract.json"
    data_manifest_path = root / "reports" / "research" / f"{strategy_name}-data-manifest.json"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps({"strategy_name": strategy_name}) + "\n", encoding="utf-8")
    data_manifest_path.write_text(
        json.dumps({"strategy_name": strategy_name, "immutable": True}) + "\n",
        encoding="utf-8",
    )
    path = root / "reports" / "research" / f"{strategy_name}-promotion.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "source_spec_path": f"strategy_specs/active/{strategy_name}.yaml",
                "status": "ok",
                "ready": True,
                "gate_summary": {"paper_ready_pass": True},
                "checks": [
                    {"name": "strict_data", "status": "ok", "message": "ok", "details": {}},
                    {"name": "universe_audit", "status": "ok", "message": "ok", "details": {}},
                    {"name": "feature_packets", "status": "ok", "message": "ok", "details": {}},
                    {"name": "benchmark_family", "status": "ok", "message": "ok", "details": {}},
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
                    "spec_hash": strategy_content_hash(spec),
                    "research_contract_path": str(contract_path.relative_to(root)),
                    "research_contract_hash": _sha256_file(contract_path),
                    "data_manifest_path": str(data_manifest_path.relative_to(root)),
                    "data_manifest_hash": _sha256_file(data_manifest_path),
                },
            }
        ),
        encoding="utf-8",
    )


def _write_router_harness_artifacts(root: Path, strategy_name: str) -> None:
    execution_dir = root / "reports" / "execution"
    research_dir = root / "reports" / "research"
    harness_execution_dir = root / "reports" / "harness" / "execution"
    paper_dir = root / "reports" / "harness" / "paper"
    source_cards_dir = root / "reports" / "harness" / "source_cards"
    execution_dir.mkdir(parents=True, exist_ok=True)
    research_dir.mkdir(parents=True, exist_ok=True)
    harness_execution_dir.mkdir(parents=True, exist_ok=True)
    paper_dir.mkdir(parents=True, exist_ok=True)
    source_cards_dir.mkdir(parents=True, exist_ok=True)
    target_path = execution_dir / f"{strategy_name}-target-weights.json"
    intents_path = execution_dir / f"{strategy_name}-rebalance-intents.json"
    cost_path = research_dir / f"{strategy_name}-router-cost-stress.json"
    data_path = research_dir / f"{strategy_name}-router-data-evidence.json"
    validation_path = research_dir / f"{strategy_name}-router-validation.json"
    observation_path = execution_dir / f"{strategy_name}-execution-observation.json"
    target_path.write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "source_spec_path": f"strategy_specs/active/{strategy_name}.yaml",
                "portfolio_mode": "beta_exposure_router",
                "target_weights": [],
                "summary": {},
                "acquisition_tier": "paper_ready_live",
            }
        ),
        encoding="utf-8",
    )
    intents_path.write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "source_spec_path": f"strategy_specs/active/{strategy_name}.yaml",
                "portfolio_mode": "beta_exposure_router",
                "intents": [],
                "summary": {},
                "execution_substate": "observation_only",
            }
        ),
        encoding="utf-8",
    )
    cost_path.write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "status": "ok",
                "scenarios": [],
                "recommendation": "observe",
            }
        ),
        encoding="utf-8",
    )
    data_path.write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "status": "ok",
                "data_source": "alpaca",
                "acquisition_tier": "paper_ready_live",
                "data_profile": {},
            }
        ),
        encoding="utf-8",
    )
    validation_path.write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "status": "ok",
                "portfolio_mode": "beta_exposure_router",
                "summary": {},
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )
    observation_path.write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "source_spec_path": f"strategy_specs/active/{strategy_name}.yaml",
                "execution_substate": "observation_only",
                "target_weights_path": str(target_path.relative_to(root)),
                "rebalance_intents_path": str(intents_path.relative_to(root)),
            }
        ),
        encoding="utf-8",
    )
    (source_cards_dir / f"{strategy_name}.jsonl").write_text(
        json.dumps(
            {
                "claim_id": f"{strategy_name}:source-research",
                "claim": (
                    "Paper router execution relies on sourced broker, exchange, "
                    "data, and leveraged ETF controls."
                ),
                "source_url": "https://docs.alpaca.markets/docs/trading/orders/",
                "source_type": "broker_official_docs",
                "accessed_at": "2026-07-09",
                "applies_to": ["broker_specific", "paper_auto", "router_strategy"],
                "impact_on_spec": (
                    "Require execution policy, safety review, and router authorization "
                    "before orders."
                ),
                "limitations": "Test fixture source card; production cards must cite current docs.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (harness_execution_dir / f"{strategy_name}-execution-policy.json").write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "policy_id": f"loo_limit_{strategy_name}_v1",
                "order_style": "loo_limit",
                "time_in_force": "opg",
                "price_protection": {"type": "limit", "limit_offset_bps": 25.0},
                "gap_filter": {"enabled": True, "max_open_gap_pct": 2.5},
                "spread_filter": {"enabled": True, "max_spread_bps": 20.0},
                "participation_cap": {"max_adv_pct": 2.5},
                "fallback_behavior": {"if_not_filled": "skip"},
                "tca_plan": {"enabled": True},
                "source_card_ids": [f"{strategy_name}:source-research"],
                "alternatives_compared": ["loo_limit", "day_market"],
            }
        ),
        encoding="utf-8",
    )
    (harness_execution_dir / f"{strategy_name}-execution-reality.json").write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "policy_id": f"loo_limit_{strategy_name}_v1",
                "slippage_scenarios": [],
                "gap_stress": {},
                "capacity_assessment": {},
                "tca_reference_prices": ["official_open"],
            }
        ),
        encoding="utf-8",
    )
    (harness_execution_dir / f"{strategy_name}-gap-stress.json").write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "scenarios": [],
                "max_adverse_gap_pct": 5.0,
                "fill_model_gap_handling": "skip excessive gaps",
                "recommended_gap_filter": "skip abs(open_gap_pct)>2.5",
            }
        ),
        encoding="utf-8",
    )
    (harness_execution_dir / f"{strategy_name}-leveraged-etf-risk.md").write_text(
        "# Leveraged ETF Risk Note\n\nPath dependency and gap risk acknowledged.\n",
        encoding="utf-8",
    )
    (paper_dir / f"{strategy_name}-paper-safety-review.json").write_text(
        json.dumps(_paper_safety_payload(root, strategy_name)),
        encoding="utf-8",
    )
    verify_dir = root / "reports" / "harness" / "verify"
    verify_dir.mkdir(parents=True, exist_ok=True)
    (verify_dir / f"{strategy_name}.json").write_text(
        json.dumps({"strategy_name": strategy_name, "overall": "ok"}),
        encoding="utf-8",
    )


def _write_router_order_authorization(root: Path, strategy_name: str) -> None:
    spec = load_strategy_spec(root / "strategy_specs" / "active" / f"{strategy_name}.yaml")
    write_paper_order_authorization(
        spec,
        root,
        authorized_by="test_operator",
        confirm_paper_only=True,
    )


def _mock_matched_paper_tca_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        "open_composer.paper_readiness._paper_tca_check",
        lambda _spec, _root: PaperStrategyReadinessCheck(
            name="matched_paper_tca",
            status="ok",
            message="Verified TCA fixture.",
            details={"valid_observation_count": 30, "distinct_session_count": 10},
        ),
    )


def _paper_safety_payload(root: Path, strategy_name: str) -> dict[str, object]:
    spec = load_strategy_spec(root / "strategy_specs" / "active" / f"{strategy_name}.yaml")
    policy = resolve_execution_policy(spec, root)
    promotion_path = root / "reports" / "research" / f"{strategy_name}-promotion.json"
    promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
    manifest = promotion["research_manifest"]
    return {
        "strategy_name": strategy_name,
        "overall": "approved",
        "blocking_items": [],
        "lifecycle_status": "active",
        "harness_verify_pass": True,
        "kill_switch_verified": True,
        "order_window": "09:28-09:32 ET",
        "duplicate_order_policy": "stable_signal_id",
        "credential_scope": "paper_only",
        "signal_order_linkage": True,
        "spec_hash": strategy_content_hash(spec),
        "execution_policy_id": policy.policy_id if policy else None,
        "execution_policy_hash": policy.content_hash if policy else None,
        "promotion_report_hash": _sha256_file(promotion_path),
        "data_manifest_hash": manifest["data_manifest_hash"],
    }


def _write_empty_broker_sync(root: Path) -> None:
    account = json.loads((root / "reports" / "paper" / "account.json").read_text())
    open_orders_path = root / "reports" / "paper" / "open_orders.json"
    open_orders_path.write_text(
        json.dumps({"generated_at": datetime.now(UTC).isoformat(), "paper": True, "orders": []}),
        encoding="utf-8",
    )
    sync_path = root / "reports" / "paper" / "broker_receipts" / "latest-sync.json"
    sync_path.parent.mkdir(parents=True, exist_ok=True)
    sync_path.write_text(
        json.dumps(
            {
                "receipt_version": 1,
                "receipt_source": "alpaca_paper_sync",
                "captured_at": datetime.now(UTC).isoformat(),
                "paper": True,
                "broker_account_id_hash": account["broker_account_id_hash"],
                "order_count": 0,
                "order_receipts": [],
            }
        ),
        encoding="utf-8",
    )


def _write_forward_observation_day(root: Path, spec_path: Path, day: date) -> None:
    spec = load_strategy_spec(spec_path)
    policy = resolve_execution_policy(spec, root)
    assert policy is not None
    started_at = datetime(day.year, day.month, day.day, 14, tzinfo=UTC)
    evidence = {
        "target_weights": {"strategy_name": spec.name, "target_weights": []},
        "review_card": {"strategy": spec.name, "date": day.isoformat()},
        "state_drift": {
            "report_type": "paper_state_drift",
            "date": day.isoformat(),
            "status": "ok",
        },
    }
    bindings = []
    for role, payload in evidence.items():
        path = root / "forward_evidence" / f"{spec.name}-{day:%Y%m%d}-{role}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        bindings.append(
            {
                "role": role,
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    log = {
        "report_type": "daily_paper_cycle",
        "cycle_receipt_version": 3,
        "date": day.isoformat(),
        "started_at": started_at.isoformat(),
        "ended_at": (started_at + timedelta(minutes=5)).isoformat(),
        "strategy": spec.name,
        "spec_hash": strategy_content_hash(spec),
        "active_spec_hash": strategy_content_hash(spec),
        "active_spec_path": f"strategy_specs/active/{spec.name}.yaml",
        "execution_policy_id": policy.policy_id,
        "execution_policy_hash": policy.content_hash,
        "status": "ok",
        "paper_order_authorization": False,
        "paper_authorization_substate": "observation_only",
        "previous_day_remediation_check": {"status": "ok"},
        "steps": [
            {"name": "readiness", "exit_code": 0},
            {"name": "target_weights", "exit_code": 0},
            {"name": "paper_cycle", "exit_code": 0},
            {"name": "paper_monitor", "exit_code": 0},
            {"name": "state_drift", "exit_code": 0},
        ],
        "artifact_paths": {},
        "evidence_bindings": bindings,
    }
    log_path = root / "reports" / "paper" / "daily_cycle" / f"{spec.name}-{day:%Y%m%d}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log), encoding="utf-8")


def _write_canary_safety_review(root: Path, strategy_name: str) -> None:
    spec = load_strategy_spec(root / "strategy_specs" / "active" / f"{strategy_name}.yaml")
    policy = resolve_execution_policy(spec, root)
    assert policy is not None
    promotion_path = root / "reports" / "research" / f"{strategy_name}-promotion.json"
    promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
    verify_path = root / "reports" / "harness" / "verify" / f"{strategy_name}.json"
    account = json.loads((root / "reports" / "paper" / "account.json").read_text(encoding="utf-8"))
    payload = {
        "strategy_name": strategy_name,
        "overall": "approved",
        "blocking_items": [],
        "harness_verify_pass": True,
        "kill_switch_verified": True,
        "credential_scope": "paper_only",
        "exclusive_account_writer": "open_composer_only",
        "broker_account_id_hash": account["broker_account_id_hash"],
        "signal_order_linkage": True,
        "spec_hash": strategy_content_hash(spec),
        "execution_policy_id": policy.policy_id,
        "execution_policy_hash": policy.content_hash,
        "promotion_report_hash": _sha256_file(promotion_path),
        "data_manifest_hash": promotion["research_manifest"]["data_manifest_hash"],
        "harness_verify_hash": _sha256_file(verify_path),
        "maximum_canary_limits": {
            "max_order_notional_usd": 1000,
            "max_session_notional_usd": 2500,
            "max_total_notional_usd": 12000,
            "max_orders_per_session": 4,
            "max_total_orders": 16,
        },
    }
    path = root / "reports" / "harness" / "paper" / f"{strategy_name}-canary-safety-review.json"
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_paper_validation_days(root: Path, spec_path: Path, count: int = 20) -> None:
    spec = load_strategy_spec(spec_path)
    policy = resolve_execution_policy(spec, root)
    log_dir = root / "reports" / "paper" / "daily_cycle"
    log_dir.mkdir(parents=True, exist_ok=True)
    day = date(2026, 6, 1)
    for _ in range(count):
        started_at = datetime(day.year, day.month, day.day, 14, tzinfo=UTC)
        payload = {
            "report_type": "daily_paper_cycle",
            "cycle_receipt_version": 3,
            "date": day.isoformat(),
            "started_at": started_at.isoformat(),
            "ended_at": (started_at + timedelta(minutes=5)).isoformat(),
            "strategy": spec.name,
            "spec_hash": strategy_content_hash(spec),
            "active_spec_hash": strategy_content_hash(spec),
            "active_spec_path": f"strategy_specs/active/{spec.name}.yaml",
            "execution_policy_id": policy.policy_id if policy else None,
            "execution_policy_hash": policy.content_hash if policy else None,
            "status": "ok",
            "paper_order_authorization": True,
            "paper_authorization_substate": "order_authorized",
            "previous_day_remediation_check": {"status": "ok"},
            "steps": [
                {"name": "readiness", "exit_code": 0},
                {"name": "target_weights", "exit_code": 0},
                {"name": "paper_cycle", "exit_code": 0},
                {"name": "paper_monitor", "exit_code": 0},
                {"name": "state_drift", "exit_code": 0},
            ],
            "artifact_paths": {},
        }
        account_hash = hashlib.sha256(b"paper-account-test").hexdigest()
        authorization = {
            "strategy_name": spec.name,
            "spec_hash": strategy_content_hash(spec),
            "execution_policy_id": policy.policy_id if policy else None,
            "execution_policy_hash": policy.content_hash if policy else None,
            "authorization_kind": "full",
            "execution_substate": "order_authorized",
            "authorized": True,
            "authorized_at": started_at.isoformat(),
            "authorized_by": "test_operator",
            "order_scope": "alpaca_paper_only",
            "real_money_broker_writes": "out_of_scope",
        }
        authorization["authorization_id"] = (
            "auth_"
            + hashlib.sha256(
                json.dumps(
                    authorization,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:16]
        )
        evidence = {
            "target_weights": {
                "strategy_name": spec.name,
                "target_weights": [],
            },
            "review_card": {"strategy": spec.name, "date": day.isoformat()},
            "state_drift": {
                "report_type": "paper_state_drift",
                "date": day.isoformat(),
                "status": "ok",
            },
            "paper_readiness": {
                "strategy_name": spec.name,
                "status": "ok",
                "execution_substate": "order_authorized",
            },
            "broker_sync": {"paper": True, "orders": []},
            "broker_sync_receipt": {
                "receipt_version": 1,
                "receipt_source": "alpaca_paper_sync",
                "paper": True,
                "broker_account_id_hash": account_hash,
            },
            "paper_authorization": authorization,
            "account_snapshot": {
                "paper": True,
                "broker_account_id_hash": account_hash,
            },
            "positions_snapshot": {"paper": True, "positions": []},
            "paper_monitor": {
                "status": "ok",
                "sync_broker": True,
                "sync_status": "ok",
            },
            "paper_cycle": {
                "run_id": f"paper-{day:%Y%m%d}",
                "strategy_name": spec.name,
                "spec_hash": strategy_content_hash(spec),
                "signals": [],
            },
        }
        bindings = []
        for role, evidence_payload in evidence.items():
            evidence_path = (
                root / "paper_validation_evidence" / f"{spec.name}-{day:%Y%m%d}-{role}.json"
            )
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text(
                json.dumps(evidence_payload, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            bindings.append(
                {
                    "role": role,
                    "path": evidence_path.relative_to(root).as_posix(),
                    "sha256": _sha256_file(evidence_path),
                    "size_bytes": evidence_path.stat().st_size,
                }
            )
        payload["evidence_bindings"] = bindings
        path = log_dir / f"{spec.name}-{day:%Y%m%d}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        day = next_us_equity_session(day)
