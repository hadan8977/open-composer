from __future__ import annotations

import hashlib
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
    candidate_authorization_binding_sha256,
    init_iteration_dossier,
    validate_iteration_dossier,
)
from open_composer.strategy_versions import strategy_content_hash

_PATH_PREFIX_PATTERN = re.compile(r"(reports|strategy_specs|signal_logs|data|\.codex|\.agents)\\")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "slow: full-round replay/training-heavy tests, run via `make test-full` / `make verify`.",
    )


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
        campaign_id = f"{iter_id}_campaign"
        iteration_root = sample_workspace / "reports/research/iterations" / iter_id
        campaign_path = (
            sample_workspace
            / "reports/research/campaigns"
            / campaign_id
            / "research-campaign-contract.json"
        )
        manifest_path = iteration_root / "candidate-manifest.json"
        feasibility_path = iteration_root / "data-feasibility.json"
        universe_path = iteration_root / "universe-contract.json"
        partition_path = iteration_root / "development-partition-contract.json"
        cost_path = iteration_root / "cost-table.json"

        raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        notes = raw.setdefault("notes", {})
        design = notes.setdefault("research_design", {})
        design.update(
            {
                "iter_id": iter_id,
                "campaign_contract_path": campaign_path.relative_to(sample_workspace).as_posix(),
                "candidate_manifest_path": manifest_path.relative_to(sample_workspace).as_posix(),
                "data_feasibility_path": feasibility_path.relative_to(sample_workspace).as_posix(),
            }
        )
        spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

        spec = load_strategy_spec(spec_path)
        spec_hash = strategy_content_hash(spec)
        source_spec_path = spec_path.relative_to(sample_workspace).as_posix()
        paths = init_iteration_dossier(iter_id, sample_workspace)
        candidate_ids = [f"C{index:02d}" for index in range(1, candidate_count + 1)]
        descriptor = {
            "economic_mechanism": "Deterministic fixture parameter variation",
            "universe_or_asset_class": "Long-lived US ETF fixtures",
            "horizon": "One test window",
            "data_modality": "Local sample OHLCV",
            "portfolio_construction": "Single-asset deterministic fixture",
            "execution_style": "Next-bar test execution",
            "universe_selection": "fixed_long_lived",
            "role": "research",
        }
        campaign = {
            "schema_version": 1,
            "campaign_id": campaign_id,
            "created_at": "2026-08-15T17:00:00Z",
            "title": "Parameter sweep test campaign",
            "objective": "Exercise a fully preregistered test-only parameter sweep.",
            "parent_iteration_ids": ["fixture_parent_iteration"],
            "child_iteration_ids": [iter_id],
            "root_hypothesis_id": "H0",
            "hypotheses": [
                {
                    "hypothesis_id": "H0",
                    "parent_hypothesis_id": None,
                    **descriptor,
                    "promotion_eligible": False,
                },
                {
                    "hypothesis_id": "H1",
                    "parent_hypothesis_id": "H0",
                    **descriptor,
                    "promotion_eligible": True,
                },
            ],
            "branch_quotas": [
                {
                    "branch_id": "B1",
                    "hypothesis_id": "H1",
                    "min_candidates": candidate_count,
                    "max_candidates": candidate_count,
                }
            ],
            "candidate_blueprints": [
                {
                    "candidate_id": candidate_id,
                    "hypothesis_id": "H1",
                    "branch_id": "B1",
                    "child_iteration_id": iter_id,
                    "method_variant": f"fixture_method_{candidate_id}",
                    "factor_variant": f"fixture_factor_{candidate_id}",
                    "archive_descriptors": {
                        "economic_mechanism": "fixture_parameter_sweep",
                        "horizon": "test_window",
                    },
                    "model_training": False,
                    "promotion_eligible": True,
                }
                for candidate_id in candidate_ids
            ],
            "visibility_partitions": [
                {
                    "partition_id": "development",
                    "kind": "development",
                    "allowed_operations": [
                        "candidate_generation",
                        "candidate_pruning",
                        "archive_update",
                    ],
                },
                {
                    "partition_id": "frozen_oos",
                    "kind": "frozen_oos",
                    "allowed_operations": ["promotion_evaluation", "reporting"],
                },
            ],
            "exposure_budgets": {
                "candidate_budget": candidate_count,
                "cumulative_trial_exposure_budget": candidate_count,
            },
            "exploration_policy": {
                "generation_mode": "enumerated_candidates",
                "mutation_mode": "none",
            },
            "qd_archive": {
                "cell_key_fields": ["economic_mechanism", "horizon"],
                "quality_metric": "development_cost_stressed_sharpe",
                "quality_direction": "maximize",
                "quality_partition_id": "development",
                "tie_break_rules": [{"field": "candidate_id", "direction": "ascending"}],
                "max_elites_per_cell": 1,
            },
            "statistical_family_policy": {
                "primary_sharpe_minimum": 1.0,
                "primary_sharpe_operator": ">",
                "advancing_pair_correlation": {
                    "method": "pearson",
                    "return_stream": (
                        "development_validation_continuous_daily_primary_20bps_terminal_free"
                    ),
                    "absolute_maximum": 0.70,
                    "operator": "<=",
                    "minimum_passing_pair_count": 1,
                },
                "dsr_minimum": 0.75,
                "pbo_maximum": 0.4,
                "spa_p_value_maximum": 0.05,
                "dsr_hac_lag": 21,
                "pbo_block_count": 8,
                "pbo_in_sample_block_count": 4,
                "spa_block_length": 21,
                "spa_resample_count": 2000,
                "spa_seed": 4201,
            },
            "candidate_promotion_policy": {
                "primary_cost_bps": 20,
                "stress_cost_bps": 40,
                "annualization_sessions": 252,
                "cagr_excess_qqq_minimum": 0.08,
                "qqq_capture_ratio_minimum": 1.0,
                "qqq_downside_capture_maximum": 1.5,
                "max_drawdown_minimum": -0.65,
                "mar_minimum": 0.4,
                "chronological_fold_count": 4,
                "minimum_positive_folds": 3,
                "development_partition_id": "development",
                "development_fold_ids": ["D1", "D2", "D3", "D4"],
                "stress_total_return_minimum": 0.0,
                "stress_total_return_operator": ">",
                "required_benchmark_roles": [
                    "same_symbol_buy_and_hold",
                    "equal_weight_universe",
                    "market_proxy",
                    "growth_proxy",
                    "sector_theme_proxy",
                    "cash_proxy",
                    "leveraged_growth_proxy",
                    "ex_post_best_symbol",
                ],
            },
            "expensive_resource_rungs": [],
            "promotion_evidence": None,
        }
        campaign_path.parent.mkdir(parents=True, exist_ok=True)
        campaign_path.write_text(json.dumps(campaign, sort_keys=True), encoding="utf-8")
        campaign_relpath = campaign_path.relative_to(sample_workspace).as_posix()

        partition_path.write_text(
            json.dumps({"partition_id": "development", "kind": "development"}),
            encoding="utf-8",
        )
        candidate_rows = [
            {
                "candidate_id": candidate_id,
                "path": "parameter_sweep",
                "role": "deterministic_fixture",
                "method": f"fixture_method_{candidate_id}",
                "ablation": "none",
                "spec_path": source_spec_path,
                "fallback": "cash_proxy",
                "data_contract": "fixture",
                "feature_contract": "fixture",
                "label_contract": "fixture",
                "validation_contract": "fixture",
                "cost_contract": "fixture",
                "benchmark_contract": "fixture",
                "campaign_id": campaign_id,
                "hypothesis_id": "H1",
                "branch_id": "B1",
                "child_iteration_id": iter_id,
                "promotion_eligible": True,
                "quality_metric": "development_cost_stressed_sharpe",
                "universe_contract_path": universe_path.relative_to(sample_workspace).as_posix(),
                "universe_contract_sha256": "0" * 64,
                "development_partition_contract_path": partition_path.relative_to(
                    sample_workspace
                ).as_posix(),
                "development_partition_contract_sha256": hashlib.sha256(
                    partition_path.read_bytes()
                ).hexdigest(),
            }
            for candidate_id in candidate_ids
        ]
        feasibility = {
            "schema_version": 1,
            "report_type": "test_fixture_data_feasibility",
            "iter_id": iter_id,
            "workflow_pass": True,
            "research_pass": False,
            "llm_contribution_pass": False,
            "paper_ready_pass": False,
            "historical_evaluation_authorized": True,
            "campaign_universe": {
                "status": "ready",
                "capability_ids": ["market.sample_ohlcv"],
            },
            "path_gates": {
                "parameter_sweep": {
                    "action": "evaluate",
                    "historical_evaluation_go": True,
                    "candidate_ids": candidate_ids,
                }
            },
            "candidate_accounting": {
                "frozen_candidate_count": candidate_count,
                "evaluation_authorized_count": candidate_count,
                "dependency_skipped_count": 0,
                "unresolved_count": 0,
                "balanced": True,
            },
            "candidate_authorization": {
                "candidate_count": candidate_count,
                "rows": [
                    {
                        "candidate_id": row["candidate_id"],
                        "path": row["path"],
                        "action": "evaluate",
                        "reason_code": "test_fixture_ready",
                        "candidate_binding_sha256": (candidate_authorization_binding_sha256(row)),
                    }
                    for row in candidate_rows
                ],
            },
            "required_reference_names": ["campaign_contract"],
            "required_references": {
                "campaign_contract": {
                    "path": campaign_relpath,
                    "sha256": hashlib.sha256(campaign_path.read_bytes()).hexdigest(),
                }
            },
        }
        feasibility_path.write_text(json.dumps(feasibility, sort_keys=True), encoding="utf-8")
        feasibility_relpath = feasibility_path.relative_to(sample_workspace).as_posix()
        universe = {
            "schema_version": 1,
            "campaign_id": campaign_id,
            "child_iteration_id": iter_id,
            "hypothesis_id": "H1",
            "universe_selection": "fixed_long_lived",
            "promotion_eligible": True,
            "contract_status": "ready",
            "capability_ids": ["market.sample_ohlcv"],
            "data_feasibility_binding": {
                "path": feasibility_relpath,
                "sha256": hashlib.sha256(feasibility_path.read_bytes()).hexdigest(),
            },
            "universe_definition": {
                "membership_mode": "fixed_long_lived_symbols",
                "symbols": ["QQQ", "SPY"],
                "selection_rule": "predeclared_test_fixture_symbols",
                "selection_frozen_at": "2026-08-15T17:00:00Z",
            },
        }
        universe_path.write_text(json.dumps(universe, sort_keys=True), encoding="utf-8")
        universe_sha256 = hashlib.sha256(universe_path.read_bytes()).hexdigest()
        for row in candidate_rows:
            row["universe_contract_sha256"] = universe_sha256

        contracts = {
            group: {"fixture": {"description": "test-only contract"}}
            for group in ["data", "features", "labels", "validation", "costs", "benchmarks"]
        }
        manifest = {
            "schema_version": 1,
            "iter_id": iter_id,
            "generated_before_backtest": True,
            "candidate_count": candidate_count,
            "contracts": contracts,
            "spec_hashes": {source_spec_path: spec_hash},
            "candidates": candidate_rows,
        }
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        cost_path.write_text(
            json.dumps({"primary_cost_bps": 20, "test_fixture": True}),
            encoding="utf-8",
        )
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
                    "schema_version": 3,
                    "created_at": "2026-08-15T17:00:00+00:00",
                    "iter_id": iter_id,
                    "strategy_name": spec.name,
                    "source_spec_path": source_spec_path,
                    "spec_hash": spec_hash,
                    "campaign_id": campaign_id,
                    "campaign_contract_path": campaign_relpath,
                    "campaign_contract_sha256": hashlib.sha256(
                        campaign_path.read_bytes()
                    ).hexdigest(),
                    "candidate_manifest_path": manifest_path.relative_to(
                        sample_workspace
                    ).as_posix(),
                    "candidate_manifest_sha256": hashlib.sha256(
                        manifest_path.read_bytes()
                    ).hexdigest(),
                    "data_feasibility_sha256": hashlib.sha256(
                        feasibility_path.read_bytes()
                    ).hexdigest(),
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
                    "cost_table_path": cost_path.relative_to(sample_workspace).as_posix(),
                    "data_feasibility_path": feasibility_relpath,
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
