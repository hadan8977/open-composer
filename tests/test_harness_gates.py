"""Tests for open_composer.harness.gates and open_composer.harness.stages."""

from __future__ import annotations

from pathlib import Path
from shutil import copyfile, copytree

import pytest

from open_composer.harness.gates import GATE_REGISTRY, GateResult, run_gate, run_gates
from open_composer.harness.stages import STAGE_REQUIREMENTS, check_stage, gates_for_stage


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
            "reference_backtest",
            "factor_lab",
            "alternative_data",
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
