from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from shutil import copyfile, copytree

import pytest
import yaml

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_controls import clear_paper_kill_switch
from open_composer.research.iteration_dossier import (
    init_iteration_dossier,
    validate_iteration_dossier,
)
from open_composer.strategy_versions import strategy_content_hash

_PATH_PREFIX_PATTERN = re.compile(r"(reports|strategy_specs|signal_logs|data|\.codex|\.agents)\\")


def assert_no_windows_paths(payload: object) -> None:
    """Recursively assert serialized artifact paths use POSIX separators."""
    if isinstance(payload, dict):
        for value in payload.values():
            assert_no_windows_paths(value)
    elif isinstance(payload, list):
        for value in payload:
            assert_no_windows_paths(value)
    elif isinstance(payload, str) and _PATH_PREFIX_PATTERN.search(payload):
        raise AssertionError(f"non-POSIX artifact path detected: {payload!r}")


@pytest.fixture()
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture()
def fixture_specs_root(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "strategy_specs" / "drafts"


@pytest.fixture()
def sample_workspace(tmp_path: Path, repo_root: Path, fixture_specs_root: Path) -> Path:
    for relative in [
        "strategy_specs/drafts",
        "strategy_specs/active",
        "capabilities",
        "watchlists",
        "data/sample",
        "data/cache",
        "data/fixtures/capabilities",
        "data/raw/events",
        "data/raw/macro",
        "event_logs",
        "feature_logs",
        "reports/backtests",
        "reports/capabilities",
        "reports/context",
        "reports/parity",
        "reports/scans",
        "reports/reviews",
        "reports/paper",
        "reports/runs",
        "reports/research",
        "reports/options",
        "signal_logs",
        "journal",
        "strategies_pine/generated",
        "strategy_versions",
    ]:
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)
    copyfile(
        fixture_specs_root / "fixture_pullback_15m.yaml",
        tmp_path / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
    )
    copyfile(
        repo_root / "data" / "sample" / "qqq_15m.csv", tmp_path / "data" / "sample" / "qqq_15m.csv"
    )
    copyfile(
        repo_root / "data" / "sample" / "mu_15m.csv", tmp_path / "data" / "sample" / "mu_15m.csv"
    )
    copyfile(
        repo_root / "data" / "sample" / "syn_daily.csv",
        tmp_path / "data" / "sample" / "syn_daily.csv",
    )
    copyfile(
        repo_root / "watchlists" / "memory_storage.yaml",
        tmp_path / "watchlists" / "memory_storage.yaml",
    )
    copytree(repo_root / "capabilities", tmp_path / "capabilities", dirs_exist_ok=True)
    copytree(
        repo_root / "data" / "fixtures" / "capabilities",
        tmp_path / "data" / "fixtures" / "capabilities",
        dirs_exist_ok=True,
    )
    # Paper submissions now require an explicit control artifact; the shared fixture
    # establishes a deliberately clear state rather than relying on an absent file.
    clear_paper_kill_switch(
        tmp_path,
        reason="test fixture clear state",
        updated_by="pytest",
    )
    return tmp_path


@pytest.fixture()
def preregister_iteration_dossier(
    sample_workspace: Path,
) -> Callable[..., str]:
    def preregister(spec_path: Path, *, candidate_count: int) -> str:
        iter_id = f"{spec_path.stem}_parameter_sweep"
        raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        notes = raw.setdefault("notes", {})
        design = notes.setdefault("research_design", {})
        design["iter_id"] = iter_id
        spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

        spec = load_strategy_spec(spec_path)
        spec_hash = strategy_content_hash(spec)
        source_spec_path = spec_path.relative_to(sample_workspace).as_posix()
        paths = init_iteration_dossier(iter_id, sample_workspace)
        sources = [
            {
                "url": f"https://example.com/test-source-{index}",
                "published_or_updated_at": "2026-01-01",
                "source_type": "paper" if index < 3 else "platform_docs",
                "credibility": "test_fixture",
                "core_claim": f"bounded test claim {index}",
                "project_applicability": "Exercises a preregistered parameter sweep.",
                "reflection": "Synthetic fixture evidence is never promotion evidence.",
            }
            for index in range(8)
        ]
        source_cards_path = paths.root / "source-cards.jsonl"
        source_cards_path.write_text(
            "".join(
                json.dumps(
                    {
                        "id": f"test-source-{index}",
                        "url": source["url"],
                        "claim": source["core_claim"],
                        "fixture_only": True,
                    },
                    sort_keys=True,
                )
                + "\n"
                for index, source in enumerate(sources)
            ),
            encoding="utf-8",
        )
        source_cards_relpath = source_cards_path.relative_to(sample_workspace).as_posix()
        paths.external_brief_json.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "iter_id": iter_id,
                    "strategy_name": spec.name,
                    "source_spec_path": source_spec_path,
                    "spec_hash": spec_hash,
                    "objective": "Exercise the bounded parameter-sweep test path.",
                    "current_source_card_paths": [source_cards_relpath],
                    "source_evidence_bindings": [
                        {
                            "source_url": source["url"],
                            "source_card_path": source_cards_relpath,
                            "claim_id": f"test-source-{index}",
                        }
                        for index, source in enumerate(sources)
                    ],
                    "sources": sources,
                    "topic_coverage": [
                        "parameter bounds",
                        "candidate accounting",
                        "cost assumptions",
                        "benchmark coverage",
                        "selection bias",
                        "test-only evidence limits",
                    ],
                    "candidate_matrix_revisions": [
                        {
                            "path": "parameter_sweep",
                            "decision": "keep",
                            "reason": "bounded fixture coverage",
                        }
                    ],
                    "hypothesis_links": [
                        {"hypothesis_id": "H1", "source_urls": [sources[0]["url"]]}
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        paths.search_space_json.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "iter_id": iter_id,
                    "strategy_name": spec.name,
                    "source_spec_path": source_spec_path,
                    "spec_hash": spec_hash,
                    "total_candidate_budget": candidate_count,
                    "paths": [
                        {
                            "name": "parameter_sweep",
                            "candidate_count": candidate_count,
                            "hypothesis_refs": ["H1"],
                            "parameters": {"bounded_fixture_values": candidate_count},
                            "benchmark_family": ["same_symbol", "cash_proxy"],
                        }
                    ],
                    "trial_ledger_paths": [],
                    "evaluation_report_paths": [],
                    "cost_table_path": "",
                    "data_feasibility_path": "",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        paths.external_brief_md.write_text(
            "# External Brief\n\n"
            "This synthetic test dossier verifies that the command honors a complete "
            "pre-backtest gate. Its sources are fixtures, its claims are not market evidence, "
            "and none of its outputs may support promotion, paper readiness, or trading.\n",
            encoding="utf-8",
        )
        paths.hypotheses_md.write_text(
            "# Hypotheses\n\n"
            "Hypothesis: the bounded fixture values exercise deterministic candidate accounting. "
            "Failure mode: the command runs without a validated iteration binding. "
            "Measurement: candidate count and report artifacts match the declared budget. "
            "Stop/Pivot criterion: stop when any hash, budget, or dossier validation fails. "
            "This text is test-only and does not make a research or promotion claim.\n",
            encoding="utf-8",
        )
        paths.search_space_md.write_text(
            "# Search Space\n\n"
            "The test evaluates one bounded parameter path with a fixed candidate count. "
            "Every command invocation must remain within that declared count and retain "
            "deterministic costs, benchmark labels, and source-spec identity throughout the run. "
            "Fixture outputs are excluded from promotion and paper evidence.\n",
            encoding="utf-8",
        )
        paths.decision_record_md.write_text(
            "# Decision Record\n\n"
            "Path: parameter_sweep fixture. Decision: pending. Reason: execution has not yet "
            "produced the bounded test report. Next iteration suggestion: retain the same "
            "candidate budget and fail closed on any stale spec hash or invalid dossier. "
            "This record is solely for command-level test coverage.\n",
            encoding="utf-8",
        )
        validation = validate_iteration_dossier(iter_id, sample_workspace, stage="pre-backtest")
        if not validation.ok:
            raise AssertionError(f"test iteration dossier invalid: {validation.blocked}")
        return iter_id

    return preregister
