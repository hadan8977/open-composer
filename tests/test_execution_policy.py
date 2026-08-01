"""Tests for open_composer.research.execution_policy (P4)."""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copyfile, copytree

import pytest

from open_composer.research.execution_policy import (
    DEFAULT_ALTERNATIVES,
    ExecutionAlternative,
    ExecutionPolicyArtifacts,
    RecommendationContext,
    detect_context,
    generate_execution_policy_artifacts,
    recommend_alternative,
)


@pytest.fixture()
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _fixture_spec(repo_root: Path) -> Path:
    return (
        repo_root / "tests" / "fixtures" / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    )


@pytest.fixture()
def minimal_workspace(tmp_path: Path, repo_root: Path) -> Path:
    """Minimal workspace with a real spec for execution policy tests."""
    for relative in [
        "strategy_specs/drafts",
        "strategies/fixture_pullback_15m",
        "capabilities",
        "data/sample",
        "data/fixtures/capabilities",
        "reports/harness/execution",
    ]:
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)

    src_spec = _fixture_spec(repo_root)
    if src_spec.exists():
        dest = tmp_path / "strategies" / "fixture_pullback_15m" / "fixture_pullback_15m.yaml"
        copyfile(src_spec, dest)

    copytree(repo_root / "capabilities", tmp_path / "capabilities", dirs_exist_ok=True)
    if (repo_root / "data" / "fixtures" / "capabilities").is_dir():
        copytree(
            repo_root / "data" / "fixtures" / "capabilities",
            tmp_path / "data" / "fixtures" / "capabilities",
            dirs_exist_ok=True,
        )
    return tmp_path


class TestExecutionAlternative:
    def test_default_alternatives_are_non_empty(self) -> None:
        assert len(DEFAULT_ALTERNATIVES) >= 3

    def test_default_alternatives_have_required_fields(self) -> None:
        for alt in DEFAULT_ALTERNATIVES:
            assert alt.order_style
            assert alt.time_in_force
            assert alt.description
            assert alt.fill_certainty in {"high", "medium", "low"}
            assert alt.slippage_risk in {"high", "medium", "low"}

    def test_expected_order_styles_present(self) -> None:
        styles = {a.order_style for a in DEFAULT_ALTERNATIVES}
        assert "moo_market" in styles or "opg_limit" in styles  # at least one opening style
        assert "day_market" in styles
        assert "loo_limit" in styles or "opg_limit" in styles


class TestRecommendationContext:
    def test_default_context_fields(self) -> None:
        ctx = RecommendationContext()
        assert ctx.is_leveraged_etf is False
        assert ctx.is_paper_auto is False
        assert ctx.universe_symbols == []

    def test_custom_context(self) -> None:
        ctx = RecommendationContext(
            is_leveraged_etf=True,
            is_paper_auto=True,
            universe_symbols=["TQQQ"],
        )
        assert ctx.is_leveraged_etf is True
        assert ctx.universe_symbols == ["TQQQ"]


class TestDetectContext:
    def test_detect_context_from_spec(self, repo_root: Path, tmp_path: Path) -> None:
        from open_composer.models.strategy_spec import load_strategy_spec

        src_spec = _fixture_spec(repo_root)
        if not src_spec.exists():
            pytest.skip("fixture_pullback_15m.yaml not present")
        dest = tmp_path / "fixture_pullback_15m.yaml"
        copyfile(src_spec, dest)
        copytree(repo_root / "capabilities", tmp_path / "capabilities", dirs_exist_ok=True)
        spec = load_strategy_spec(dest)
        ctx = detect_context(spec)
        assert isinstance(ctx, RecommendationContext)
        assert isinstance(ctx.universe_symbols, list)

    def test_detects_leveraged_etf(self, tmp_path: Path, repo_root: Path) -> None:
        from open_composer.models.strategy_spec import load_strategy_spec

        spec_text = """
name: leveraged_test
description: Test leveraged ETF detection
timeframe: daily
universe: [TQQQ]
lifecycle: draft
entry:
  all: [close > high * 0.99]
exit:
  all: [close < low * 1.01]
risk:
  max_trades_per_day: 1
  max_position_weight: 0.2
execution:
  backend: python_reference
  mode: manual_signal
  signal_on: bar_close
  fill_assumption: next_bar_open
  broker: none
"""
        (tmp_path / "capabilities").mkdir(parents=True, exist_ok=True)
        copytree(repo_root / "capabilities", tmp_path / "capabilities", dirs_exist_ok=True)
        spec_path = tmp_path / "leveraged_test.yaml"
        spec_path.write_text(spec_text)
        spec = load_strategy_spec(spec_path)
        ctx = detect_context(spec)
        assert ctx.is_leveraged_etf is True


class TestRecommendAlternative:
    def test_leveraged_etf_recommends_price_protected_style(self) -> None:
        ctx = RecommendationContext(
            is_leveraged_etf=True,
            is_paper_auto=True,
            is_daily_open=True,
            universe_symbols=["TQQQ"],
        )
        alt = recommend_alternative(ctx)
        # Should pick a price-protected style, not a naked market order
        assert alt.order_style in {"opg_limit", "loo_limit"}

    def test_daily_open_paper_auto_recommends_opening_style(self) -> None:
        ctx = RecommendationContext(
            is_leveraged_etf=False,
            is_paper_auto=True,
            is_daily_open=True,
            universe_symbols=["SPY"],
        )
        alt = recommend_alternative(ctx)
        assert isinstance(alt, ExecutionAlternative)
        assert alt.order_style  # non-empty

    def test_daily_open_manual_signal_recommends_opening_style(self) -> None:
        ctx = RecommendationContext(
            is_leveraged_etf=False,
            is_paper_auto=False,
            is_daily_open=True,
            universe_symbols=["SPY"],
        )
        alt = recommend_alternative(ctx)
        assert alt.order_style == "opg_limit"

    def test_leveraged_daily_open_manual_signal_recommends_limit_on_open(self) -> None:
        ctx = RecommendationContext(
            is_leveraged_etf=True,
            is_paper_auto=False,
            is_daily_open=True,
            universe_symbols=["TQQQ"],
        )
        alt = recommend_alternative(ctx)
        assert alt.order_style == "loo_limit"

    def test_fallback_returns_day_market(self) -> None:
        ctx = RecommendationContext(
            is_leveraged_etf=False,
            is_paper_auto=False,
            is_daily_open=False,
            universe_symbols=["AAPL"],
        )
        alt = recommend_alternative(ctx)
        assert alt.order_style == "day_market"

    def test_returns_executable_alternative(self) -> None:
        ctx = RecommendationContext(
            is_leveraged_etf=False,
            is_paper_auto=False,
            universe_symbols=["SPY"],
        )
        alt = recommend_alternative(ctx)
        assert isinstance(alt, ExecutionAlternative)


class TestGenerateExecutionPolicyArtifacts:
    def test_inline_strategy_policy_is_source_of_truth(self, minimal_workspace: Path) -> None:
        spec_path = minimal_workspace / "inline_policy.yaml"
        spec_path.write_text(_inline_policy_spec(), encoding="utf-8")

        result = generate_execution_policy_artifacts(
            spec_path=spec_path,
            root=minimal_workspace,
            overwrite=True,
        )

        policy = json.loads(result.policy_path.read_text(encoding="utf-8"))
        assert policy["generated_from_inline_strategy_spec"] is True
        assert policy["policy_id"] == "inline-opg-v1"
        assert policy["price_protection"]["limit_offset_bps"] == 20.0
        assert policy["gap_filter"]["max_open_gap_pct"] == 2.5
        assert policy["spread_filter"] == {
            "enabled": True,
            "max_spread_bps": 15.0,
            "action_on_exceed": "skip",
        }
        assert policy["participation_cap"]["max_adv_pct"] == 0.01
        assert policy["fallback_behavior"]["if_spread_exceeds_limit"] == "skip"
        assert policy["tca_plan"]["reference_prices"] == [
            "decision_price",
            "official_open",
            "arrival_price",
            "vwap",
        ]

    def test_inline_policy_rejects_source_card_override(self, minimal_workspace: Path) -> None:
        spec_path = minimal_workspace / "inline_policy.yaml"
        spec_path.write_text(_inline_policy_spec(), encoding="utf-8")

        with pytest.raises(ValueError, match="must match the inline StrategySpec"):
            generate_execution_policy_artifacts(
                spec_path=spec_path,
                root=minimal_workspace,
                overwrite=True,
                source_card_ids=["different-card"],
            )

    def test_generates_required_artifacts(self, minimal_workspace: Path) -> None:
        spec_path = (
            minimal_workspace / "strategies" / "fixture_pullback_15m" / "fixture_pullback_15m.yaml"
        )
        if not spec_path.exists():
            pytest.skip("spec not copied")

        result = generate_execution_policy_artifacts(
            spec_path=spec_path,
            root=minimal_workspace,
            overwrite=True,
            source_card_ids=[],
        )

        assert isinstance(result, ExecutionPolicyArtifacts)
        assert result.policy_path.exists(), "execution policy JSON not written"
        assert result.reality_path.exists(), "execution reality JSON not written"
        assert result.markdown_path.exists(), "execution reality narrative not written"

    def test_policy_json_has_required_fields(self, minimal_workspace: Path) -> None:
        spec_path = (
            minimal_workspace / "strategies" / "fixture_pullback_15m" / "fixture_pullback_15m.yaml"
        )
        if not spec_path.exists():
            pytest.skip("spec not copied")

        result = generate_execution_policy_artifacts(
            spec_path=spec_path,
            root=minimal_workspace,
            overwrite=True,
            source_card_ids=["sc-001"],
        )

        policy = json.loads(result.policy_path.read_text())
        assert "policy_id" in policy
        assert "order_style" in policy
        assert "time_in_force" in policy
        assert "alternatives_compared" in policy
        assert isinstance(policy["alternatives_compared"], list)
        assert len(policy["alternatives_compared"]) >= 2
        assert policy["source_card_ids"] == ["sc-001"]

    def test_does_not_overwrite_without_flag(self, minimal_workspace: Path) -> None:
        spec_path = (
            minimal_workspace / "strategies" / "fixture_pullback_15m" / "fixture_pullback_15m.yaml"
        )
        if not spec_path.exists():
            pytest.skip("spec not copied")

        result = generate_execution_policy_artifacts(
            spec_path=spec_path,
            root=minimal_workspace,
            overwrite=True,
            source_card_ids=[],
        )
        mtime_before = result.policy_path.stat().st_mtime

        generate_execution_policy_artifacts(
            spec_path=spec_path,
            root=minimal_workspace,
            overwrite=False,
            source_card_ids=[],
        )

        assert result.policy_path.stat().st_mtime == mtime_before, (
            "artifact was overwritten when overwrite=False"
        )

    def test_reality_json_has_slippage_scenarios(self, minimal_workspace: Path) -> None:
        spec_path = (
            minimal_workspace / "strategies" / "fixture_pullback_15m" / "fixture_pullback_15m.yaml"
        )
        if not spec_path.exists():
            pytest.skip("spec not copied")

        result = generate_execution_policy_artifacts(
            spec_path=spec_path,
            root=minimal_workspace,
            overwrite=True,
            source_card_ids=[],
        )

        reality = json.loads(result.reality_path.read_text())
        assert "slippage_scenarios" in reality
        assert len(reality["slippage_scenarios"]) >= 2
        for scenario in reality["slippage_scenarios"]:
            assert "slippage_bps" in scenario


def _inline_policy_spec() -> str:
    return """
name: inline_policy_test
description: Inline policy must remain the source of truth.
timeframe: daily
universe: [SPY]
lifecycle: draft
entry:
  all: ["close > sma(close, 20)"]
exit:
  all: ["close <= sma(close, 20)"]
risk:
  max_trades_per_day: 1
  max_position_weight: 0.4
execution:
  backend: python_reference
  mode: manual_signal
  signal_on: bar_close
  fill_assumption: next_bar_open
  broker: none
execution_policy:
  policy_id: inline-opg-v1
  order_style: opg_limit
  time_in_force: opg
  price_protection:
    limit_offset_bps: 20
    max_open_gap_pct: 2.5
    max_spread_bps: 15
  participation_cap:
    max_adv_pct: 0.01
    max_open_bar_volume_pct: 0.1
  fallback_behavior:
    if_not_filled: skip
    if_gap_exceeds_limit: skip
    if_spread_exceeds_limit: skip
  tca:
    enabled: true
    compare_to: [decision_price, official_open, arrival_price, vwap]
    record_submitted_at: true
    record_fill_price: true
    review_frequency: weekly
  alternatives_compared: [moo_market, opg_limit, delayed_open_30m_shadow]
  source_card_ids: [inline-card]
reality_model:
  fill_model: next_regular_open_with_policy
  slippage_model: stress_bps_by_volatility_and_participation
  stress_scenarios:
    - {name: primary, slippage_bps: 10, open_gap_pct: 0.5}
    - {name: stress, slippage_bps: 20, open_gap_pct: 1.5}
"""
