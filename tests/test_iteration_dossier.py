from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.iteration_dossier import (
    _q2_execution_map_blockers,
    init_iteration_dossier,
    validate_iteration_dossier,
)
from open_composer.research.stock_momentum_q2_contract import (
    RUNNABLE_IDS,
    build_q2_execution_map,
)
from open_composer.strategy_versions import strategy_content_hash


def test_iteration_dossier_init_writes_template_and_validate_blocks(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)

    assert paths.external_brief_json.exists()
    assert paths.hypotheses_md.exists()
    assert paths.search_space_json.exists()
    assert paths.decision_record_md.exists()

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert result.status == "blocked"
    assert "external_brief_sources_lt_8:0" in result.blocked
    assert "external_brief_paper_sources_lt_3:0" in result.blocked
    assert "search_space_paths_missing" in result.blocked
    assert "decision_record_still_template" in result.blocked


def test_iteration_dossier_validate_passes_complete_dossier(sample_workspace: Path) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    sources = [
        {
            "url": f"https://example.com/source-{idx}",
            "published_or_updated_at": "2026-01-01",
            "source_type": "paper" if idx < 3 else "platform_docs",
            "credibility": "high",
            "core_claim": f"claim {idx}",
            "project_applicability": "Defines a bounded minute momentum hypothesis.",
            "reflection": "May decay and is sensitive to transaction costs.",
        }
        for idx in range(8)
    ]
    paths.external_brief_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "strategy_name": "us_minute_momentum",
                "source_spec_path": None,
                "spec_hash": None,
                "objective": "US minute momentum round 1",
                "sources": sources,
                "topic_coverage": [
                    "intraday momentum",
                    "intraday reversal",
                    "cross-sectional momentum",
                    "overnight intraday decomposition",
                    "volatility-managed momentum",
                    "transaction costs",
                ],
                "candidate_matrix_revisions": [
                    {"path": "P1", "decision": "keep", "reason": "supported by sources"}
                ],
                "hypothesis_links": [{"hypothesis_id": "H1", "source_urls": [sources[0]["url"]]}],
            }
        ),
        encoding="utf-8",
    )
    paths.search_space_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "strategy_name": "us_minute_momentum",
                "source_spec_path": None,
                "spec_hash": None,
                "total_candidate_budget": 20,
                "paths": [
                    {
                        "name": "P1",
                        "candidate_count": 12,
                        "hypothesis_refs": ["H1"],
                        "parameters": {"lookback": [12, 24]},
                        "benchmark_family": ["QQQ", "BIL", "naive_momentum"],
                    },
                    {
                        "name": "P2",
                        "candidate_count": 8,
                        "hypothesis_refs": ["H2"],
                        "parameters": {"top_k": [1, 2]},
                        "benchmark_family": ["SPY", "BIL", "equal_weight_universe"],
                    },
                ],
                "trial_ledger_paths": [],
                "evaluation_report_paths": [],
                "cost_table_path": "reports/research/control/minute-momentum-feasibility.json",
                "data_feasibility_path": "reports/research/control/minute-momentum-feasibility.md",
            }
        ),
        encoding="utf-8",
    )
    paths.external_brief_md.write_text(_filled_md("External brief"), encoding="utf-8")
    paths.hypotheses_md.write_text(_hypotheses_md(), encoding="utf-8")
    paths.search_space_md.write_text(_filled_md("Search space"), encoding="utf-8")
    paths.decision_record_md.write_text(_decision_record_md("pending"), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert result.status == "ok"
    assert result.blocked == []


def test_iteration_dossier_blocks_payload_iter_id_mismatch(sample_workspace: Path) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    payload = json.loads(paths.external_brief_json.read_text(encoding="utf-8"))
    payload["iter_id"] = "other_round"
    paths.external_brief_json.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert "iteration_payload_iter_id_mismatch" in result.blocked


def test_iteration_dossier_final_stage_requires_artifact_refs(sample_workspace: Path) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    paths.decision_record_md.write_text(_decision_record_md("continue"), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace, stage="final")

    assert "search_space_trial_ledger_paths_empty_final" in result.blocked
    assert "search_space_evaluation_report_paths_empty_final" in result.blocked


def test_iteration_dossier_enforces_declared_knowledge_contract(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    search = json.loads(paths.search_space_json.read_text(encoding="utf-8"))
    artifact_root = paths.root
    artifacts = {
        "assessment_path": artifact_root / "knowledge-assessment.json",
        "scout_path": artifact_root / "knowledge-scout.json",
        "model_reuse_decision_path": artifact_root / "model-reuse-decision.json",
        "modality_role_matrix_path": artifact_root / "modality-role-matrix.json",
    }
    for field_name, path in artifacts.items():
        payload = {"status": "ok"} if field_name == "assessment_path" else {"rows": []}
        path.write_text(json.dumps(payload), encoding="utf-8")
    search["knowledge_contract"] = {
        **{
            field_name: path.relative_to(sample_workspace).as_posix()
            for field_name, path in artifacts.items()
        },
        "required_visibility_partitions": [
            "public_literature",
            "train_only_empirical",
            "challenge_result",
            "forward_observation",
        ],
    }
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")

    passed = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert passed.status == "ok"

    artifacts["scout_path"].unlink()
    blocked = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "knowledge_contract_missing_artifact_scout_path" in blocked.blocked


def test_iteration_dossier_blocks_non_ok_knowledge_assessment(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    search = json.loads(paths.search_space_json.read_text(encoding="utf-8"))
    fields = {}
    for name in [
        "assessment_path",
        "scout_path",
        "model_reuse_decision_path",
        "modality_role_matrix_path",
    ]:
        path = paths.root / f"{name}.json"
        path.write_text(
            json.dumps({"status": "blocked"} if name == "assessment_path" else {}),
            encoding="utf-8",
        )
        fields[name] = path.relative_to(sample_workspace).as_posix()
    search["knowledge_contract"] = {
        **fields,
        "required_visibility_partitions": [
            "public_literature",
            "train_only_empirical",
            "challenge_result",
            "forward_observation",
        ],
    }
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "knowledge_contract_assessment_not_ok" in result.blocked


def test_iteration_dossier_validates_machine_candidate_manifest(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    search = json.loads(paths.search_space_json.read_text(encoding="utf-8"))
    search["total_candidate_budget"] = 1
    search["paths"][0]["candidate_count"] = 1
    search["data_feasibility_path"] = "reports/research/control/mom-minute-data-feasibility.json"
    manifest_path = paths.root / "candidate-manifest.json"
    search["candidate_manifest_path"] = manifest_path.relative_to(sample_workspace).as_posix()
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")
    spec_path = "strategy_specs/drafts/fixture_pullback_15m.yaml"
    candidate = {
        "candidate_id": "C01",
        "path": "P1",
        "role": "return_ranking",
        "method": "linear_rank",
        "ablation": "baseline",
        "spec_path": spec_path,
        "data_contract": "data",
        "feature_contract": "features",
        "label_contract": "label",
        "validation_contract": "validation",
        "cost_contract": "cost",
        "benchmark_contract": "benchmark",
        "fallback": "flat",
    }
    manifest = {
        "schema_version": 1,
        "iter_id": "mom_minute_r1",
        "generated_before_backtest": True,
        "candidate_count": 1,
        "spec_hashes": {
            spec_path: "6d7a0ed38e20e4929cd13f439193aa87bba3a65834a7805f64aef4bbe2cbbb46"
        },
        "contracts": {
            "data": {"data": {}},
            "features": {"features": {}},
            "labels": {"label": {}},
            "validation": {"validation": {}},
            "costs": {"cost": {}},
            "benchmarks": {"benchmark": []},
        },
        "candidates": [candidate],
    }
    fixture_spec_path = sample_workspace / spec_path
    fixture_spec_path.write_text(
        fixture_spec_path.read_text(encoding="utf-8").replace(
            "  research_design:\n",
            "  research_design:\n"
            "    iter_id: mom_minute_r1\n"
            f"    candidate_manifest_path: {search['candidate_manifest_path']}\n"
            f"    data_feasibility_path: {search['data_feasibility_path']}\n",
            1,
        ),
        encoding="utf-8",
    )
    spec = load_strategy_spec(sample_workspace / spec_path)
    manifest["spec_hashes"][spec_path] = strategy_content_hash(spec)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    search["candidate_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")

    missing_prerequisites = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "search_space_cost_table_path_missing" in missing_prerequisites.blocked
    assert "search_space_data_feasibility_path_missing" in missing_prerequisites.blocked
    feasibility = _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
        authorized=False,
    )
    rejected = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "search_space_data_feasibility_not_authorized" in rejected.blocked
    feasibility["q2_diagnostic_execution_authorized"] = True
    _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
        payload=feasibility,
    )

    passed = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert passed.status == "ok"

    feasibility["candidate_accounting"]["diagnostic_runnable_count"] = 0
    _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
        payload=feasibility,
    )
    accounting_blocked = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert any(
        item.startswith("data_feasibility_accounting_diagnostic_runnable_count_mismatch")
        for item in accounting_blocked.blocked
    )

    manifest["candidates"][0]["label_contract"] = "missing"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    blocked = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "candidate_manifest_sha256_mismatch" in blocked.blocked


def test_iteration_dossier_blocks_malformed_feasibility_contract(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    search = json.loads(paths.search_space_json.read_text(encoding="utf-8"))
    search["total_candidate_budget"] = 1
    search["paths"][0]["candidate_count"] = 1
    search["data_feasibility_path"] = "reports/research/control/mom-minute-data-feasibility.json"
    manifest_path = paths.root / "candidate-manifest.json"
    search["candidate_manifest_path"] = manifest_path.relative_to(sample_workspace).as_posix()
    spec_path = "strategy_specs/drafts/fixture_pullback_15m.yaml"
    fixture_spec_path = sample_workspace / spec_path
    fixture_spec_path.write_text(
        fixture_spec_path.read_text(encoding="utf-8").replace(
            "  research_design:\n",
            "  research_design:\n"
            "    iter_id: mom_minute_r1\n"
            f"    candidate_manifest_path: {search['candidate_manifest_path']}\n"
            f"    data_feasibility_path: {search['data_feasibility_path']}\n",
            1,
        ),
        encoding="utf-8",
    )
    manifest = _single_candidate_manifest(
        spec_path,
        strategy_content_hash(load_strategy_spec(fixture_spec_path)),
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    search["candidate_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    feasibility = _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
    )

    feasibility["q2_diagnostic_execution_authorized"] = "true"
    feasibility["research_pass"] = True
    feasibility["path_gates"]["P1"]["candidate_ids"] = ["WRONG"]
    _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
        payload=feasibility,
    )
    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert "data_feasibility_q2_diagnostic_execution_authorized_not_boolean" in result.blocked
    assert "search_space_data_feasibility_not_authorized" in result.blocked
    assert "data_feasibility_diagnostic_scope_research_pass_must_be_false" in result.blocked
    assert "data_feasibility_P1_candidate_ids_mismatch" in result.blocked

    valid = _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
    )
    search["data_feasibility_sha256"] = "0" * 64
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")
    hash_result = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "data_feasibility_sha256_mismatch" in hash_result.blocked

    valid = _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
    )
    valid["q2_authorization"]["rows"][0]["candidate_binding_sha256"] = "0" * 64
    _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
        payload=valid,
    )
    candidate_hash_result = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert any(
        item.startswith("data_feasibility_q2_authorization_candidate_sha_mismatch")
        for item in candidate_hash_result.blocked
    )

    valid = _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
    )
    valid["q2_authorization"]["rows"][0]["evidence_sha256"] = "0" * 64
    _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
        payload=valid,
    )
    evidence_hash_result = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert any(
        item.startswith("data_feasibility_q2_authorization_evidence_sha_mismatch")
        for item in evidence_hash_result.blocked
    )

    _write_candidate_feasibility(sample_workspace, paths, search, manifest)
    fixture_spec_path.write_text(
        fixture_spec_path.read_text(encoding="utf-8").replace(
            f"data_feasibility_path: {search['data_feasibility_path']}",
            "data_feasibility_path: reports/research/control/wrong.json",
            1,
        ),
        encoding="utf-8",
    )
    manifest["spec_hashes"][spec_path] = strategy_content_hash(
        load_strategy_spec(fixture_spec_path)
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    search["candidate_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")
    spec_binding_result = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert any(
        item.startswith("candidate_manifest_spec_feasibility_path_mismatch")
        for item in spec_binding_result.blocked
    )


def test_q2_execution_map_rejects_noncanonical_semantic_contracts(tmp_path: Path) -> None:
    manifest_by_id = {
        candidate_id: {
            "candidate_id": candidate_id,
            "path": "daily_deterministic" if candidate_id.startswith("D") else "daily_ml",
            "method": f"method_{candidate_id.lower()}",
            "feature_contract": "daily_price_volume_lag1",
            "label_contract": (
                "daily_downside_21d"
                if candidate_id in {"D11", "M05", "M06", "M07", "M08"}
                else "daily_rank_5d"
            ),
            "benchmark_contract": "daily_full_benchmark_family",
            "fallback": "cash",
        }
        for candidate_id in RUNNABLE_IDS
    }
    canonical = build_q2_execution_map({"candidates": list(manifest_by_id.values())})

    mutations = {
        "score": lambda payload: payload["rows"][0].__setitem__("score", "future_return_rank"),
        "feature_contract": lambda payload: payload["rows"][0].__setitem__(
            "feature_contract", "unregistered_features"
        ),
        "label_contract": lambda payload: payload["rows"][0].__setitem__(
            "label_contract", "future_label"
        ),
        "cost_contract": lambda payload: payload["rows"][0].__setitem__(
            "cost_contract", "zero_cost"
        ),
        "benchmark_contract": lambda payload: payload["rows"][0].__setitem__(
            "benchmark_contract", "incomplete_benchmarks"
        ),
        "primitive_fields": lambda payload: payload["rows"][0].__setitem__(
            "primitive_fields", ["open", "high", "low", "close", "volume"]
        ),
        "row_safety_flag": lambda payload: payload["rows"][0].__setitem__(
            "promotion_eligible", True
        ),
        "global_safety_flag": lambda payload: payload.__setitem__("forward_fill_allowed", True),
    }
    for mutation_name, mutate in mutations.items():
        payload = deepcopy(canonical)
        mutate(payload)
        path = tmp_path / f"q2-execution-map-{mutation_name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        blocked = _q2_execution_map_blockers(
            path,
            manifest_by_id,
            set(RUNNABLE_IDS),
            expected_iter_id="mom_stock_intraday_codesign_q1",
        )

        assert "q2_execution_map_canonical_contract_mismatch" in blocked, mutation_name


def test_execution_commands_enforce_declared_iteration_gate(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8").replace(
            "  research_design:\n",
            "  research_design:\n    iter_id: missing_iteration_round\n",
            1,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    runner = CliRunner()

    results = [
        runner.invoke(app, ["backtest", str(spec_path)], catch_exceptions=False),
        runner.invoke(
            app,
            ["strategy", "optimize", str(spec_path)],
            catch_exceptions=False,
        ),
        runner.invoke(
            app,
            ["strategy", "parameter-sweep", str(spec_path)],
            catch_exceptions=False,
        ),
    ]

    assert all(result.exit_code != 0 for result in results)
    assert all("iteration dossier blocked" in result.output for result in results)


def test_iteration_dossier_cli_init_and_validate(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    runner = CliRunner()

    init_result = runner.invoke(
        app,
        ["research", "iteration", "init", "mom_minute_r1"],
        catch_exceptions=False,
    )
    validate_result = runner.invoke(
        app,
        ["research", "iteration", "validate", "mom_minute_r1"],
        catch_exceptions=False,
    )

    assert init_result.exit_code == 0
    assert validate_result.exit_code == 1
    assert "external_brief_sources_lt_8:0" in validate_result.output

    json_result = runner.invoke(
        app,
        ["research", "iteration", "validate", "mom_minute_r1", "--json"],
        catch_exceptions=False,
    )
    assert json_result.exit_code == 1
    assert json.loads(json_result.output)["status"] == "blocked"


def _single_candidate_manifest(spec_path: str, spec_hash: str) -> dict:
    return {
        "schema_version": 1,
        "iter_id": "mom_minute_r1",
        "generated_before_backtest": True,
        "candidate_count": 1,
        "spec_hashes": {spec_path: spec_hash},
        "contracts": {
            "data": {"data": {}},
            "features": {"features": {}},
            "labels": {"label": {}},
            "validation": {"validation": {}},
            "costs": {"cost": {}},
            "benchmarks": {"benchmark": []},
        },
        "candidates": [
            {
                "candidate_id": "C01",
                "path": "P1",
                "role": "return_ranking",
                "method": "linear_rank",
                "ablation": "baseline",
                "spec_path": spec_path,
                "data_contract": "data",
                "feature_contract": "features",
                "label_contract": "label",
                "validation_contract": "validation",
                "cost_contract": "cost",
                "benchmark_contract": "benchmark",
                "fallback": "flat",
            }
        ],
    }


def _write_candidate_feasibility(
    root: Path,
    paths,
    search: dict,
    manifest: dict,
    *,
    authorized: bool = True,
    payload: dict | None = None,
) -> dict:
    cost_path = root / search["cost_table_path"]
    cost_path.parent.mkdir(parents=True, exist_ok=True)
    if not cost_path.exists():
        cost_path.write_text("{}", encoding="utf-8")
    artifact_paths = {
        "parent_universe": paths.root / "parent-universe.json",
        "daily_panel": paths.root / "daily-panel-manifest.json",
        "intraday_panel": paths.root / "intraday-panel-manifest.json",
        "cost_contract": cost_path,
        "q2_execution_map": paths.root / "q2-execution-map.json",
    }
    for field_name, artifact_path in artifact_paths.items():
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        if field_name == "q2_execution_map":
            execution_rows = []
            for candidate in manifest["candidates"]:
                execution_rows.append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "path": candidate["path"],
                        "method": candidate["method"],
                        "candidate_binding_sha256": hashlib.sha256(
                            json.dumps(
                                candidate,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode()
                        ).hexdigest(),
                        "primitive_fields": ["open", "close", "volume"],
                        "research_pass": False,
                        "paper_ready_pass": False,
                        "promotion_eligible": False,
                        "required_benchmarks": ["ex_post_best_symbol_report_only"],
                    }
                )
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "iter_id": "mom_minute_r1",
                        "scope": "historical_current_universe_diagnostic",
                        "survivorship_labelled": True,
                        "runnable_candidate_count": len(execution_rows),
                        "primitive_field_allowlist": ["open", "close", "volume"],
                        "high_low_dependent_candidates_allowed": False,
                        "forward_fill_allowed": False,
                        "zero_return_substitution_allowed": False,
                        "rows": execution_rows,
                    }
                ),
                encoding="utf-8",
            )
        elif not artifact_path.exists():
            artifact_path.write_text("{}", encoding="utf-8")
    if payload is None:
        candidate_ids = [str(row["candidate_id"]) for row in manifest["candidates"]]
        daily_evidence_path = artifact_paths["daily_panel"]
        payload = {
            "schema_version": 1,
            "report_type": "test_data_feasibility",
            "iter_id": "mom_minute_r1",
            "workflow_pass": True,
            "research_pass": False,
            "llm_contribution_pass": False,
            "paper_ready_pass": False,
            "q2_diagnostic_execution_authorized": authorized,
            "path_gates": {
                "P1": {
                    "q2_action": "run_diagnostic",
                    "historical_diagnostic_go": True,
                    "historical_research_qualified": False,
                    "candidate_ids": candidate_ids,
                }
            },
            "candidate_accounting": {
                "frozen_candidate_count": len(candidate_ids),
                "diagnostic_runnable_count": len(candidate_ids),
                "dependency_skipped_count": 0,
                "unresolved_count": 0,
                "balanced": True,
            },
            "q2_authorization": {
                "candidate_count": len(candidate_ids),
                "rows": [
                    {
                        "candidate_id": str(candidate["candidate_id"]),
                        "path": str(candidate["path"]),
                        "action": "run_diagnostic",
                        "reason_code": "test_diagnostic_gate",
                        "candidate_binding_sha256": hashlib.sha256(
                            json.dumps(
                                candidate,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode()
                        ).hexdigest(),
                        "evidence_path": daily_evidence_path.relative_to(root).as_posix(),
                        "evidence_sha256": hashlib.sha256(
                            daily_evidence_path.read_bytes()
                        ).hexdigest(),
                    }
                    for candidate in manifest["candidates"]
                ],
            },
        }
    for field_name, artifact_path in artifact_paths.items():
        payload[field_name] = {
            "path": artifact_path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        }
    feasibility_path = root / search["data_feasibility_path"]
    feasibility_path.parent.mkdir(parents=True, exist_ok=True)
    feasibility_path.write_text(json.dumps(payload), encoding="utf-8")
    search["data_feasibility_sha256"] = hashlib.sha256(feasibility_path.read_bytes()).hexdigest()
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")
    return payload


def _write_complete_pre_backtest_payload(paths) -> None:
    sources = [
        {
            "url": f"https://example.com/source-{idx}",
            "published_or_updated_at": "2026-01-01",
            "source_type": "paper" if idx < 3 else "platform_docs",
            "credibility": "high",
            "core_claim": f"claim {idx}",
            "project_applicability": "Defines a bounded minute momentum hypothesis.",
            "reflection": "May decay and is sensitive to transaction costs.",
        }
        for idx in range(8)
    ]
    paths.external_brief_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "strategy_name": "us_minute_momentum",
                "source_spec_path": None,
                "spec_hash": None,
                "objective": "US minute momentum round 1",
                "sources": sources,
                "topic_coverage": [
                    "intraday momentum",
                    "intraday reversal",
                    "cross-sectional momentum",
                    "overnight intraday decomposition",
                    "volatility-managed momentum",
                    "transaction costs",
                ],
                "candidate_matrix_revisions": [{"path": "P1", "decision": "keep"}],
                "hypothesis_links": [{"hypothesis_id": "H1", "source_urls": [sources[0]["url"]]}],
            }
        ),
        encoding="utf-8",
    )
    paths.search_space_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "strategy_name": "us_minute_momentum",
                "source_spec_path": None,
                "spec_hash": None,
                "total_candidate_budget": 12,
                "paths": [
                    {
                        "name": "P1",
                        "candidate_count": 12,
                        "hypothesis_refs": ["H1"],
                        "parameters": {"lookback": [12, 24]},
                        "benchmark_family": ["QQQ", "BIL", "naive_momentum"],
                    }
                ],
                "trial_ledger_paths": [],
                "evaluation_report_paths": [],
                "cost_table_path": "reports/research/control/minute-momentum-feasibility.json",
                "data_feasibility_path": "reports/research/control/minute-momentum-feasibility.md",
            }
        ),
        encoding="utf-8",
    )
    paths.external_brief_md.write_text(_filled_md("External brief"), encoding="utf-8")
    paths.hypotheses_md.write_text(_hypotheses_md(), encoding="utf-8")
    paths.search_space_md.write_text(_filled_md("Search space"), encoding="utf-8")
    paths.decision_record_md.write_text(_decision_record_md("pending"), encoding="utf-8")


def _filled_md(title: str) -> str:
    return (
        f"# {title}\n\n"
        "This file has been completed with enough project-specific content to move beyond "
        "the generated template. It records the hypothesis, evidence linkage, benchmark "
        "family, cost caveats, expected failure mode, and the next decision for the "
        "Open Composer minute momentum iteration.\n"
    )


def _hypotheses_md() -> str:
    return """# Hypotheses

## H1

- Hypothesis: Thirty-minute ETF momentum persists after the opening range when
  trend breadth is positive.
- Failure mode: The signal reverses after costs or only works in a single
  recent bull regime.
- Measurement: Four chronological walk-forward folds with QQQ, SPY, BIL,
  equal-weight universe, and naive momentum benchmarks.
- Stop/Pivot criterion: Stop if the last two folds are negative after baseline
  costs; pivot to lower frequency if cost stress dominates.
"""


def _decision_record_md(decision: str) -> str:
    return f"""# Decision Record

## P1

- Path: time-series ETF momentum.
- Decision: {decision}
- Reason: Pre-backtest dossier is ready when pending; final records must use
  continue, pivot, or stop with supporting evidence.
- Next iteration suggestion: Move to ML only if OOS decisions exceed the sample
  threshold and the non-ML baseline survives cost stress.
"""
