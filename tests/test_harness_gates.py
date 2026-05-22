"""Tests for open_composer.harness.gates and open_composer.harness.stages."""

from __future__ import annotations

from pathlib import Path
from shutil import copyfile, copytree

import pytest

from open_composer.harness.gates import GATE_REGISTRY, GateResult, run_gate, run_gates
from open_composer.harness.policy import (
    check_artifact,
    detect_risk_domains,
    required_artifacts_for_domains,
)
from open_composer.harness.stages import STAGE_REQUIREMENTS, check_stage, gates_for_stage
from open_composer.models.options import OptionsOverlaySpec, OptionsSpec
from open_composer.models.strategy_spec import load_strategy_spec


@pytest.fixture()
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture()
def spec_path(tmp_path: Path, repo_root: Path) -> Path:
    """Minimal workspace + spec path for gate tests."""
    for relative in [
        "strategy_specs/drafts",
        "capabilities",
        "data/sample",
        "data/fixtures/capabilities",
        "reports/backtests",
        "reports/research",
        "strategy_versions",
    ]:
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)
    dest = tmp_path / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    copyfile(repo_root / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml", dest)
    copyfile(
        repo_root / "data" / "sample" / "qqq_15m.csv",
        tmp_path / "data" / "sample" / "qqq_15m.csv",
    )
    copytree(repo_root / "capabilities", tmp_path / "capabilities", dirs_exist_ok=True)
    copytree(
        repo_root / "data" / "fixtures" / "capabilities",
        tmp_path / "data" / "fixtures" / "capabilities",
        dirs_exist_ok=True,
    )
    return dest


class TestGateRegistry:
    def test_built_in_gates_are_registered(self) -> None:
        expected = {
            "spec_validation",
            "expression_safety",
            "leakage_check",
            "capability_evaluation",
            "research_capability_evaluation",
            "reference_backtest",
            "factor_lab",
            "alternative_data",
            "promotion_report",
            "paper_readiness",
        }
        assert expected.issubset(GATE_REGISTRY)

    def test_run_gate_unknown_returns_blocked(self, tmp_path: Path, spec_path: Path) -> None:
        result = run_gate("nonexistent_gate_xyz", spec_path, tmp_path)
        assert result.status == "blocked"
        assert "not registered" in result.message

    def test_gate_returns_gate_result_instance(self, tmp_path: Path, spec_path: Path) -> None:
        result = run_gate("spec_validation", spec_path, tmp_path)
        assert isinstance(result, GateResult)
        assert result.name == "spec_validation"
        assert result.status in {"ok", "warning", "blocked"}

    def test_run_gates_returns_one_result_per_gate(self, tmp_path: Path, spec_path: Path) -> None:
        names = ["spec_validation", "expression_safety"]
        results = run_gates(names, spec_path, tmp_path)
        assert len(results) == 2
        assert results[0].name == "spec_validation"
        assert results[1].name == "expression_safety"


class TestSpecValidationGate:
    def test_valid_spec_returns_ok(self, tmp_path: Path, spec_path: Path) -> None:
        result = run_gate("spec_validation", spec_path, tmp_path)
        assert result.status == "ok"
        assert "qqq_pullback_15m" in result.message

    def test_missing_spec_returns_blocked(self, tmp_path: Path) -> None:
        result = run_gate("spec_validation", tmp_path / "missing.yaml", tmp_path)
        assert result.status == "blocked"


class TestExpressionSafetyGate:
    def test_valid_expressions_return_ok(self, tmp_path: Path, spec_path: Path) -> None:
        result = run_gate("expression_safety", spec_path, tmp_path)
        assert result.status == "ok"

    def test_unsafe_expression_returns_blocked(self, tmp_path: Path, repo_root: Path) -> None:
        import yaml

        dest = tmp_path / "bad_spec.yaml"
        src = repo_root / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
        raw = yaml.safe_load(src.read_text(encoding="utf-8"))
        raw["entry"]["all"] = ["__import__('os').system('rm -rf /')"]
        dest.write_text(yaml.safe_dump(raw), encoding="utf-8")
        result = run_gate("expression_safety", dest, tmp_path)
        assert result.status == "blocked"


class TestLeakageCheckGate:
    def test_standard_spec_returns_ok(self, tmp_path: Path, spec_path: Path) -> None:
        result = run_gate("leakage_check", spec_path, tmp_path)
        assert result.status == "ok"
        assert result.evidence is not None
        ev = result.evidence
        assert ev["signal_on"] == "bar_close"  # type: ignore[index]
        assert ev["fill_assumption"] == "next_bar_open"  # type: ignore[index]

    def test_llm_review_without_packets_returns_warning(
        self, tmp_path: Path, repo_root: Path
    ) -> None:
        import yaml

        dest = tmp_path / "llm_spec.yaml"
        src = repo_root / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
        raw = yaml.safe_load(src.read_text(encoding="utf-8"))
        raw["llm_review"] = {"enabled": True}
        dest.write_text(yaml.safe_dump(raw), encoding="utf-8")
        result = run_gate("leakage_check", dest, tmp_path)
        assert result.status == "warning"
        assert "PIT packets" in result.message


class TestResearchCapabilityGate:
    def test_research_capability_ignores_paper_and_llm_non_applicable_blockers(
        self, tmp_path: Path, spec_path: Path
    ) -> None:
        result = run_gate("research_capability_evaluation", spec_path, tmp_path)

        assert result.status in {"ok", "warning"}
        assert result.evidence is not None
        evidence = result.evidence
        assert "alpaca_paper_execution" in evidence["not_applicable"]  # type: ignore[index]
        assert "llm_quant_workflow" in evidence["not_applicable"]  # type: ignore[index]
        assert "alpaca_paper_execution" not in evidence["blocked"]  # type: ignore[index]
        assert "llm_quant_workflow" not in evidence["blocked"]  # type: ignore[index]

    def test_advisory_context_partial_is_not_applicable_for_research(
        self, tmp_path: Path, spec_path: Path
    ) -> None:
        result = run_gate("research_capability_evaluation", spec_path, tmp_path)

        assert result.status == "ok"
        assert result.evidence is not None
        evidence = result.evidence
        assert "python_mvp_backtest" in evidence["not_applicable"]  # type: ignore[index]
        assert "tradingview_pine_strategy" in evidence["not_applicable"]  # type: ignore[index]

    def test_partial_capabilities_are_warnings(self, tmp_path: Path, spec_path: Path) -> None:
        import yaml

        raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        raw["llm_review"] = {"enabled": True}
        raw["required_capabilities"] = [
            "market.sample_ohlcv",
            "events.sec_filings",
            "news.alpha_vantage",
        ]
        spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

        result = run_gate("research_capability_evaluation", spec_path, tmp_path)

        assert result.status == "warning"
        assert result.evidence is not None
        evidence = result.evidence
        assert "python_mvp_backtest" in evidence["warnings"]  # type: ignore[index]
        assert "tradingview_pine_strategy" in evidence["warnings"]  # type: ignore[index]
        assert "llm_quant_workflow" in evidence["warnings"]  # type: ignore[index]
        assert "nautilus_trader_backend" in evidence["not_applicable"]  # type: ignore[index]


class TestCapabilityEvaluationGate:
    def test_unsupported_capabilities_are_blocked(self, tmp_path: Path, spec_path: Path) -> None:
        import yaml

        raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        raw["entry"]["all"] = ["supertrend(close, 10) > 0"]
        spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

        result = run_gate("capability_evaluation", spec_path, tmp_path)

        assert result.status == "blocked"
        assert result.evidence is not None
        evidence = result.evidence
        assert "python_mvp_backtest" in evidence["blocked"]  # type: ignore[index]
        assert "tradingview_pine_strategy" in evidence["blocked"]  # type: ignore[index]


class TestRiskDomainPolicy:
    def test_router_domain_triggers_required_artifacts(
        self, tmp_path: Path, spec_path: Path
    ) -> None:
        import yaml

        raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        raw["name"] = "beta_router_harness"
        raw["timeframe"] = "daily"
        raw["universe"] = ["QQQ", "TQQQ", "SQQQ"]
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
        spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        spec = load_strategy_spec(spec_path)

        domains = detect_risk_domains(spec, tmp_path)
        artifacts = required_artifacts_for_domains(domains)

        assert "router_strategy" in domains
        assert {
            "router_target_weights",
            "router_rebalance_intents",
            "router_execution_observation",
            "router_cost_stress",
            "router_data_evidence",
            "router_validation",
        } <= artifacts

    def test_short_domain_triggers_required_artifacts(
        self, tmp_path: Path, spec_path: Path
    ) -> None:
        import yaml

        raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        raw["position_direction"] = "long_short"
        spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        spec = load_strategy_spec(spec_path)

        domains = detect_risk_domains(spec, tmp_path)
        artifacts = required_artifacts_for_domains(domains)

        assert "short_selling" in domains
        assert {
            "short_sale_source_cards",
            "borrow_cost_estimate",
            "short_squeeze_stress",
            "ex_dividend_risk_note",
            "short_exposure_policy",
        } <= artifacts

    def test_options_domains_trigger_contract_artifacts(self, tmp_path: Path) -> None:
        overlay = OptionsOverlaySpec.model_validate(
            {
                "name": "qqq_protective_put_overlay",
                "base_strategy": "strategy_specs/active/qqq_router.yaml",
                "overlay_type": "protective_put",
                "max_premium_pct": 1.0,
            }
        )
        primary = OptionsSpec.model_validate(
            {
                "name": "spx_put_spread_weekly",
                "underlying": "SPX",
                "strategy_type": "put_spread",
                "expiry_target": "weekly",
                "max_position_pct": 0.05,
            }
        )

        overlay_domains = detect_risk_domains(overlay, tmp_path)
        primary_domains = detect_risk_domains(primary, tmp_path)

        assert overlay_domains == ["options_overlay"]
        assert "options_primary" in primary_domains
        assert {
            "options_chain_source_cards",
            "greeks_profile",
            "roll_schedule",
            "iv_stress_report",
            "overlay_cost_report",
            "assignment_risk_note",
        } <= required_artifacts_for_domains(overlay_domains)
        assert {
            "options_chain_source_cards",
            "greeks_profile",
            "contract_selection_log",
            "expiry_ladder",
            "iv_stress_report",
            "assignment_risk_note",
        } <= required_artifacts_for_domains(primary_domains)

    def test_shared_source_card_path_requires_contract_specific_claim_id(
        self,
        tmp_path: Path,
    ) -> None:
        cards_dir = tmp_path / "reports" / "harness" / "source_cards"
        cards_dir.mkdir(parents=True, exist_ok=True)
        (cards_dir / "shared_source_card_strategy.jsonl").write_text(
            (
                '{"claim_id":"shared_source_card_strategy:short-paper-broker-verification-required",'
                '"claim":"Short broker rules verified.",'
                '"source_url":"https://docs.alpaca.markets/",'
                '"source_type":"broker_official_docs",'
                '"accessed_at":"2026-05-22",'
                '"applies_to":["shared_source_card_strategy","short_selling"],'
                '"impact_on_spec":"blocks short order authorization until current",'
                '"limitations":"fixture"}\n'
            ),
            encoding="utf-8",
        )

        short_status = check_artifact(
            "short_sale_source_cards",
            "shared_source_card_strategy",
            tmp_path,
        )
        options_status = check_artifact(
            "options_chain_source_cards",
            "shared_source_card_strategy",
            tmp_path,
        )

        assert short_status.schema_ok is True
        assert options_status.schema_ok is False
        assert (
            "claim_id:shared_source_card_strategy:options-chain-provider-coverage"
            in options_status.missing_fields
        )

        (cards_dir / "shared_source_card_strategy.jsonl").write_text(
            (
                '{"claim_id":"shared_source_card_strategy:options-chain-provider-coverage",'
                '"claim":"Options provider coverage verified."}\n'
            ),
            encoding="utf-8",
        )
        incomplete_options_status = check_artifact(
            "options_chain_source_cards",
            "shared_source_card_strategy",
            tmp_path,
        )

        assert incomplete_options_status.schema_ok is False
        assert (
            "claim_id:shared_source_card_strategy:options-chain-provider-coverage:source_url"
            in incomplete_options_status.missing_fields
        )


class TestFactorLabHarnessGate:
    def test_no_custom_factors_are_not_applicable_for_harness(
        self, tmp_path: Path, spec_path: Path
    ) -> None:
        result = run_gate("factor_lab", spec_path, tmp_path)

        assert result.status == "ok"
        assert "not applicable" in result.message.lower()
        assert result.evidence is not None
        assert result.evidence["not_applicable"] is True  # type: ignore[index]


class TestStageRequirements:
    def test_all_stages_defined(self) -> None:
        assert set(STAGE_REQUIREMENTS) >= {"draft", "research", "promotion", "paper_ready"}

    def test_draft_stage_is_subset_of_research(self) -> None:
        draft = set(STAGE_REQUIREMENTS["draft"])
        research = set(STAGE_REQUIREMENTS["research"])
        assert draft.issubset(research)

    def test_gates_for_stage_returns_list(self) -> None:
        names = gates_for_stage("draft")
        assert isinstance(names, list)
        assert len(names) >= 2

    def test_gates_for_stage_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown stage"):
            gates_for_stage("nonexistent_stage")

    def test_research_uses_research_capability_gate(self) -> None:
        assert "research_capability_evaluation" in STAGE_REQUIREMENTS["research"]
        assert "capability_evaluation" not in STAGE_REQUIREMENTS["research"]

    def test_promotion_does_not_include_paper_readiness(self) -> None:
        assert "promotion_report" in STAGE_REQUIREMENTS["promotion"]
        assert "paper_readiness" not in STAGE_REQUIREMENTS["promotion"]
        assert "promotion_report" in STAGE_REQUIREMENTS["paper_ready"]
        assert "paper_readiness" in STAGE_REQUIREMENTS["paper_ready"]


class TestCheckStage:
    def test_draft_stage_ok_for_valid_spec(self, tmp_path: Path, spec_path: Path) -> None:
        status, results = check_stage("draft", spec_path, tmp_path)
        assert status in {"ok", "warning", "blocked"}
        assert len(results) == len(gates_for_stage("draft"))

    def test_check_stage_returns_gate_results(self, tmp_path: Path, spec_path: Path) -> None:
        _status, results = check_stage("draft", spec_path, tmp_path)
        for result in results:
            assert isinstance(result, GateResult)
            assert result.status in {"ok", "warning", "blocked"}

    def test_research_stage_no_longer_blocks_on_non_applicable_surfaces(
        self, tmp_path: Path, spec_path: Path
    ) -> None:
        status, results = check_stage("research", spec_path, tmp_path)

        assert status == "ok"
        assert {result.name for result in results} == set(gates_for_stage("research"))
