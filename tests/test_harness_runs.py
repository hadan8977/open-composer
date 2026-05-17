"""Tests for open_composer.harness.runs (append-only JSONL evidence log)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from open_composer.harness.runs import append_run, evidence_for, query_runs
from open_composer.research.kernel.gates import GateResult


def _make_results(status: str = "ok") -> list[GateResult]:
    return [
        GateResult(name="spec_validation", status=status, message="test"),
        GateResult(name="expression_safety", status="ok", message="test"),
    ]


class TestAppendRun:
    def test_creates_log_file(self, tmp_path: Path) -> None:
        log = append_run(
            strategy_name="test_strat",
            spec_hash="abc123",
            stage="draft",
            results=_make_results(),
            root=tmp_path,
        )
        assert log.exists()
        assert log.suffix == ".jsonl"

    def test_appends_multiple_runs(self, tmp_path: Path) -> None:
        for _ in range(3):
            append_run(
                strategy_name="test_strat",
                spec_hash="abc123",
                stage="draft",
                results=_make_results(),
                root=tmp_path,
            )
        log = tmp_path / "reports" / "research" / "harness-runs.jsonl"
        lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 3

    def test_record_contains_expected_fields(self, tmp_path: Path) -> None:
        import json

        append_run(
            strategy_name="alpha",
            spec_hash="deadbeef",
            stage="research",
            results=_make_results(),
            root=tmp_path,
        )
        log = tmp_path / "reports" / "research" / "harness-runs.jsonl"
        record = json.loads(log.read_text(encoding="utf-8").strip())
        assert record["strategy_name"] == "alpha"
        assert record["spec_hash"] == "deadbeef"
        assert record["stage"] == "research"
        assert record["status"] == "ok"
        assert isinstance(record["gate_results"], list)
        assert len(record["gate_results"]) == 2

    def test_aggregate_status_blocked(self, tmp_path: Path) -> None:
        import json

        results = [
            GateResult(name="spec_validation", status="blocked", message="fail"),
            GateResult(name="expression_safety", status="ok", message="ok"),
        ]
        append_run(
            strategy_name="strat",
            spec_hash="xyz",
            stage="draft",
            results=results,
            root=tmp_path,
        )
        log = tmp_path / "reports" / "research" / "harness-runs.jsonl"
        record = json.loads(log.read_text(encoding="utf-8").strip())
        assert record["status"] == "blocked"

    def test_aggregate_status_warning(self, tmp_path: Path) -> None:
        import json

        results = [
            GateResult(name="leakage_check", status="warning", message="warn"),
            GateResult(name="expression_safety", status="ok", message="ok"),
        ]
        append_run(
            strategy_name="strat",
            spec_hash="xyz",
            stage="draft",
            results=results,
            root=tmp_path,
        )
        log = tmp_path / "reports" / "research" / "harness-runs.jsonl"
        record = json.loads(log.read_text(encoding="utf-8").strip())
        assert record["status"] == "warning"


class TestQueryRuns:
    def test_empty_log_returns_empty(self, tmp_path: Path) -> None:
        runs = query_runs(strategy_name="any", root=tmp_path)
        assert runs == []

    def test_filter_by_strategy_name(self, tmp_path: Path) -> None:
        for name in ["alpha", "beta", "alpha"]:
            append_run(
                strategy_name=name,
                spec_hash="h",
                stage="draft",
                results=_make_results(),
                root=tmp_path,
            )
        runs = query_runs(strategy_name="alpha", root=tmp_path)
        assert len(runs) == 2
        assert all(r["strategy_name"] == "alpha" for r in runs)

    def test_filter_by_stage(self, tmp_path: Path) -> None:
        for stage in ["draft", "research", "draft"]:
            append_run(
                strategy_name="strat",
                spec_hash="h",
                stage=stage,
                results=_make_results(),
                root=tmp_path,
            )
        runs = query_runs(stage="draft", root=tmp_path)
        assert len(runs) == 2

    def test_filter_by_since(self, tmp_path: Path) -> None:
        append_run(
            strategy_name="strat",
            spec_hash="h",
            stage="draft",
            results=_make_results(),
            root=tmp_path,
        )
        future = datetime.now(UTC) + timedelta(hours=1)
        runs = query_runs(since=future, root=tmp_path)
        assert runs == []

    def test_no_filter_returns_all(self, tmp_path: Path) -> None:
        for _ in range(4):
            append_run(
                strategy_name="strat",
                spec_hash="h",
                stage="draft",
                results=_make_results(),
                root=tmp_path,
            )
        runs = query_runs(root=tmp_path)
        assert len(runs) == 4


class TestEvidenceFor:
    def test_returns_matching_hash(self, tmp_path: Path) -> None:
        append_run(
            strategy_name="strat",
            spec_hash="hash_a",
            stage="draft",
            results=_make_results(),
            root=tmp_path,
        )
        append_run(
            strategy_name="strat",
            spec_hash="hash_b",
            stage="draft",
            results=_make_results(),
            root=tmp_path,
        )
        ev = evidence_for("strat", "hash_a", root=tmp_path)
        assert len(ev) == 1
        assert ev[0]["spec_hash"] == "hash_a"

    def test_returns_empty_for_unknown_hash(self, tmp_path: Path) -> None:
        append_run(
            strategy_name="strat",
            spec_hash="hash_a",
            stage="draft",
            results=_make_results(),
            root=tmp_path,
        )
        ev = evidence_for("strat", "hash_z", root=tmp_path)
        assert ev == []
