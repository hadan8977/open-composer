from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.knowledge_memory import (
    VISIBILITY_PARTITIONS,
    assess_iteration_knowledge,
    build_iteration_knowledge_context,
    build_knowledge_index,
    canonical_source_url,
    claim_fingerprint,
    scout_knowledge,
)


def test_canonical_source_url_removes_tracking_and_arxiv_version() -> None:
    assert (
        canonical_source_url("HTTP://WWW.ARXIV.ORG/abs/2505.15155v2?utm_source=test")
        == "https://arxiv.org/abs/2505.15155"
    )
    assert canonical_source_url("reports/harness/source_cards/local.jsonl") == ""
    assert canonical_source_url("file:///tmp/source.txt") == ""
    assert canonical_source_url("http://localhost/source") == ""
    assert canonical_source_url("http://foo.localhost/source") == ""
    assert canonical_source_url("http://localhost./source") == ""
    assert canonical_source_url("http://127.0.0.1/source") == ""
    assert canonical_source_url("http://[::1]/source") == ""
    assert canonical_source_url("http://169.254.169.254/source") == ""
    assert canonical_source_url("http://2130706433/source") == ""
    assert canonical_source_url("http://0x7f000001/source") == ""
    assert canonical_source_url("http://0177.0.0.1/source") == ""
    assert canonical_source_url("http://127.1/source") == ""
    assert canonical_source_url("http://0x7f.0.0.1/source") == ""
    assert canonical_source_url("http://10.0.0.1.nip.io/source") == ""
    assert canonical_source_url("https://user:secret@example.com/source") == ""
    assert (
        canonical_source_url("https://example.com/paper/?ref=feed&version=2&utm_medium=email")
        == "https://example.com/paper?version=2"
    )


def test_build_knowledge_index_deduplicates_and_retains_negative_results(
    tmp_path: Path,
) -> None:
    cards = tmp_path / "reports/harness/source_cards/strategy.jsonl"
    cards.parent.mkdir(parents=True)
    rows = [
        _source_card("one", "https://arxiv.org/abs/2505.15155v1?utm_source=a"),
        _source_card("two", "https://www.arxiv.org/abs/2505.15155v2"),
    ]
    cards.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    iteration = tmp_path / "reports/research/iterations/round_one"
    iteration.mkdir(parents=True)
    (iteration / "decision-record.md").write_text(
        "# Decision Record\n\n- Decision: stop\n- Reason: OOS failure.\n",
        encoding="utf-8",
    )
    model = iteration / "models/model.joblib"
    model.parent.mkdir()
    model.write_bytes(b"frozen-model")

    result = build_knowledge_index(tmp_path)

    assert result.payload["source_count"] == 1
    assert result.payload["duplicate_source_occurrences"] == 1
    assert result.payload["sources"][0]["occurrence_count"] == 2
    assert result.payload["empirical_memory"][0]["negative_result"] is True
    assert result.payload["model_memory"][0]["reuse_policy"].startswith("frozen_inference")
    assert tuple(result.payload["visibility_partitions"]) == VISIBILITY_PARTITIONS


def test_knowledge_index_uses_only_receipt_verified_final_decision(tmp_path: Path) -> None:
    iteration = tmp_path / "reports/research/iterations/round_final"
    evaluation_dir = iteration / "evaluation-run"
    evaluation_dir.mkdir(parents=True)
    root_decision = iteration / "decision-record.md"
    final_decision = evaluation_dir / "decision-record.md"
    evaluation = evaluation_dir / "evaluation-report.json"
    trial_ledger = evaluation_dir / "trial-ledger.jsonl"
    root_decision.write_text("# Decision Record\n\n- Decision: pending\n", encoding="utf-8")
    final_decision.write_text(
        "# Decision Record\n\n- Decision: stop\n- Reason: historical challenge failed.\n",
        encoding="utf-8",
    )
    evaluation.write_text(
        json.dumps(
            {
                "decision": "stop",
                "historical_challenge": True,
                "workflow_pass": True,
                "research_pass": False,
                "llm_contribution_pass": False,
                "paper_ready_pass": False,
            }
        ),
        encoding="utf-8",
    )
    trial_ledger.write_text('{"candidate_id":"D01"}\n', encoding="utf-8")

    def binding(path: Path) -> dict[str, object]:
        raw = path.read_bytes()
        return {
            "path": str(path.relative_to(tmp_path)),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }

    receipt = {
        "schema_version": 1,
        "iter_id": "round_final",
        "evidence_publication_status": "complete",
        "decision": "stop",
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "children": {
            "decision_record": binding(final_decision),
            "evaluation": binding(evaluation),
            "trial_ledger": binding(trial_ledger),
        },
    }
    (evaluation_dir / "evaluation-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")

    verified = build_knowledge_index(tmp_path).payload["empirical_memory"]

    assert len(verified) == 1
    assert verified[0]["artifact_path"].endswith("evaluation-run/decision-record.md")
    assert verified[0]["visibility_partition"] == "challenge_result"
    assert verified[0]["negative_result"] is True

    final_decision.write_text("# Decision Record\n\n- Decision: pivot\n", encoding="utf-8")
    after_tamper = build_knowledge_index(tmp_path).payload["empirical_memory"]

    assert len(after_tamper) == 1
    assert after_tamper[0]["artifact_path"].endswith("round_final/decision-record.md")
    assert after_tamper[0]["negative_result"] is False


def test_scout_marks_known_and_new_candidates(tmp_path: Path) -> None:
    cards = tmp_path / "reports/harness/source_cards/strategy.jsonl"
    cards.parent.mkdir(parents=True)
    cards.write_text(
        json.dumps(_source_card("known", "https://arxiv.org/abs/2505.15155")) + "\n",
        encoding="utf-8",
    )
    iteration = tmp_path / "reports/research/iterations/round_two"
    iteration.mkdir(parents=True)
    (iteration / "external-brief.json").write_text(
        json.dumps({"sources": []}),
        encoding="utf-8",
    )
    (iteration / "knowledge-scout-queries.json").write_text(
        json.dumps(
            {
                "max_results_per_query": 5,
                "queries": [{"query_id": "q1", "query": "all:momentum", "topics": ["mom"]}],
            }
        ),
        encoding="utf-8",
    )

    result = scout_knowledge(
        "round_two",
        tmp_path,
        fetcher=lambda _query, _limit: _atom_feed().encode(),
    )

    assert result.payload["candidate_count"] == 2
    assert result.payload["new_candidate_count"] == 1
    assert result.payload["already_known_count"] == 1
    assert all(
        row["validation_status"] == "candidate_unvalidated" for row in result.payload["candidates"]
    )


def test_scout_merges_curated_web_candidates_without_treating_them_as_validated(
    tmp_path: Path,
) -> None:
    iteration = tmp_path / "reports/research/iterations/round_curated"
    iteration.mkdir(parents=True)
    (iteration / "external-brief.json").write_text(
        json.dumps({"sources": []}),
        encoding="utf-8",
    )
    (iteration / "knowledge-scout-queries.json").write_text(
        json.dumps(
            {
                "queries": [],
                "curated_candidates": [
                    {
                        "discovery_id": "github_reference",
                        "url": "https://github.com/microsoft/qlib",
                        "title": "Qlib",
                        "summary": "Workflow reference.",
                        "source_type": "platform_docs",
                        "published_at": "accessed 2026-07-15",
                        "topics": ["momentum", "research workflow"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = scout_knowledge("round_curated", tmp_path)

    assert result.payload["candidate_count"] == 1
    assert result.payload["new_candidate_count"] == 1
    assert result.payload["candidates"][0]["validation_status"] == "candidate_unvalidated"
    assert "curated_web_manifest" in result.payload["provider"]


def test_scout_rebuilds_prior_verification_after_excluding_current_cards(
    tmp_path: Path,
) -> None:
    cards_root = tmp_path / "reports/harness/source_cards"
    cards_root.mkdir(parents=True)
    url = "https://example.com/shared"
    (cards_root / "prior.jsonl").write_text(
        json.dumps(_source_card("prior", url)) + "\n", encoding="utf-8"
    )
    current_card = {
        **_source_card("current", url),
        "iteration_id": "round_baseline",
        "verification_status": "source_verified",
        "verified_at": "2026-07-15T00:00:00Z",
        "verification_method": "test_fixture",
    }
    (cards_root / "current.jsonl").write_text(json.dumps(current_card) + "\n", encoding="utf-8")
    iteration = tmp_path / "reports/research/iterations/round_baseline"
    iteration.mkdir(parents=True)
    source = _brief_source(url)
    (iteration / "external-brief.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "current_source_card_paths": ["reports/harness/source_cards/current.jsonl"],
                "source_evidence_bindings": [
                    {
                        "canonical_url": url,
                        "source_card_claim_id": "current",
                        "claim_fingerprint": claim_fingerprint("Claim current"),
                        "brief_claim_fingerprint": claim_fingerprint(source["core_claim"]),
                    }
                ],
                "sources": [source],
            }
        ),
        encoding="utf-8",
    )
    (iteration / "knowledge-scout-queries.json").write_text(
        json.dumps(
            {
                "queries": [],
                "curated_candidates": [
                    {
                        "url": url,
                        "title": "Shared source",
                        "source_type": "paper",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = scout_knowledge("round_baseline", tmp_path)

    assert result.payload["candidates"][0]["knowledge_status"] == "already_known"
    assert result.payload["candidates"][0]["validation_status"] == "candidate_unvalidated"


def test_scout_allows_distinct_claim_bindings_for_one_source_url(tmp_path: Path) -> None:
    cards_root = tmp_path / "reports/harness/source_cards"
    cards_root.mkdir(parents=True)
    url = "https://example.com/official-orders"
    cards = []
    sources = []
    bindings = []
    for claim_id, claim in [
        ("semantics", "OPG is an auction order."),
        ("cutoff", "OPG has a cutoff."),
    ]:
        cards.append(
            {
                **_source_card(claim_id, url),
                "claim": claim,
                "iteration_id": "round_shared_url",
                "verification_status": "source_verified",
                "verified_at": "2026-07-19T00:00:00Z",
                "verification_method": "test_fixture",
            }
        )
        source = {**_brief_source(url), "core_claim": claim}
        sources.append(source)
        bindings.append(
            {
                "canonical_url": url,
                "source_card_claim_id": claim_id,
                "claim_fingerprint": claim_fingerprint(claim),
                "brief_claim_fingerprint": claim_fingerprint(claim),
            }
        )
    (cards_root / "current.jsonl").write_text(
        "\n".join(json.dumps(card) for card in cards) + "\n",
        encoding="utf-8",
    )
    iteration = tmp_path / "reports/research/iterations/round_shared_url"
    iteration.mkdir(parents=True)
    (iteration / "external-brief.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "current_source_card_paths": ["reports/harness/source_cards/current.jsonl"],
                "source_evidence_bindings": bindings,
                "sources": sources,
            }
        ),
        encoding="utf-8",
    )
    (iteration / "knowledge-scout-queries.json").write_text(
        json.dumps(
            {
                "queries": [],
                "curated_candidates": [
                    {"url": url, "title": "Official orders", "source_type": "platform_docs"}
                ],
            }
        ),
        encoding="utf-8",
    )

    result = scout_knowledge("round_shared_url", tmp_path)

    assert result.payload["candidate_count"] == 1
    assert result.payload["schema_version"] == 2
    brief_path = iteration / "external-brief.json"
    tampered = json.loads(brief_path.read_text(encoding="utf-8"))
    tampered["objective"] = "changed after scout"
    brief_path.write_text(json.dumps(tampered), encoding="utf-8")
    try:
        assess_iteration_knowledge("round_shared_url", tmp_path)
    except ValueError as exc:
        assert "external brief hash mismatch" in str(exc)
    else:
        raise AssertionError("schema-v2 scout must remain bound to the external brief")


def test_assessment_requires_scout_and_reports_reuse_novelty(tmp_path: Path) -> None:
    prior = tmp_path / "reports/harness/source_cards/strategy.jsonl"
    prior.parent.mkdir(parents=True)
    prior.write_text(
        json.dumps(_source_card("known", "https://example.com/known")) + "\n",
        encoding="utf-8",
    )
    iteration = tmp_path / "reports/research/iterations/round_three"
    iteration.mkdir(parents=True)
    sources = [
        _brief_source("https://example.com/known"),
        *[_brief_source(f"https://example.com/new-{index}") for index in range(7)],
    ]
    (iteration / "external-brief.json").write_text(
        json.dumps({"sources": sources}), encoding="utf-8"
    )

    blocked = assess_iteration_knowledge("round_three", tmp_path)
    assert blocked.payload["status"] == "blocked"
    assert "knowledge_scout_missing" in blocked.payload["blocked"]

    _write_valid_scout(iteration, "round_three", new_candidate_count=2)
    passed = assess_iteration_knowledge("round_three", tmp_path)

    assert passed.payload["status"] == "ok"
    assert passed.payload["counts"]["reused"] == 1
    assert passed.payload["counts"]["new"] == 7
    assert passed.payload["external_brief_path"].endswith("external-brief.json")
    assert passed.payload["external_brief_sha256"]


def test_assessment_rejects_scout_with_stale_manifest_hash(tmp_path: Path) -> None:
    iteration = tmp_path / "reports/research/iterations/round_tampered"
    iteration.mkdir(parents=True)
    (iteration / "external-brief.json").write_text(
        json.dumps(
            {"sources": [_brief_source(f"https://example.com/{index}") for index in range(8)]}
        ),
        encoding="utf-8",
    )
    _write_valid_scout(iteration, "round_tampered", new_candidate_count=1)
    (iteration / "knowledge-scout-queries.json").write_text(
        json.dumps({"queries": [{"query_id": "changed", "query": "all:changed"}]}),
        encoding="utf-8",
    )

    try:
        assess_iteration_knowledge("round_tampered", tmp_path)
    except ValueError as exc:
        assert "manifest hash mismatch" in str(exc)
    else:
        raise AssertionError("stale scout manifests must not pass assessment")


def test_assessment_does_not_treat_current_iteration_source_cards_as_prior(
    tmp_path: Path,
) -> None:
    current_cards = tmp_path / "reports/harness/source_cards/current.jsonl"
    current_cards.parent.mkdir(parents=True)
    current_cards.write_text(
        "\n".join(
            json.dumps(
                {
                    **_source_card(str(index), f"https://example.com/current-{index}"),
                    "iteration_id": "round_current",
                    "verification_status": "source_verified",
                    "verified_at": "2026-07-15T00:00:00Z",
                    "verification_method": "test_fixture",
                }
            )
            for index in range(8)
        )
        + "\n",
        encoding="utf-8",
    )
    iteration = tmp_path / "reports/research/iterations/round_current"
    iteration.mkdir(parents=True)
    sources = [_brief_source(f"https://example.com/current-{index}") for index in range(8)]
    bindings = [
        {
            "canonical_url": f"https://example.com/current-{index}",
            "source_card_claim_id": str(index),
            "claim_fingerprint": claim_fingerprint(f"Claim {index}"),
            "brief_claim_fingerprint": claim_fingerprint(sources[index]["core_claim"]),
        }
        for index in range(8)
    ]
    (iteration / "external-brief.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "current_source_card_paths": ["reports/harness/source_cards/current.jsonl"],
                "source_evidence_bindings": bindings,
                "sources": sources,
            }
        ),
        encoding="utf-8",
    )
    _write_valid_scout(iteration, "round_current", new_candidate_count=1)

    result = assess_iteration_knowledge("round_current", tmp_path)

    assert result.payload["status"] == "ok"
    assert result.payload["counts"]["new"] == 8

    tampered = json.loads((iteration / "external-brief.json").read_text(encoding="utf-8"))
    tampered["sources"][0]["core_claim"] = "Guaranteed alpha from an unrelated claim."
    (iteration / "external-brief.json").write_text(json.dumps(tampered), encoding="utf-8")
    try:
        assess_iteration_knowledge("round_current", tmp_path)
    except ValueError as exc:
        assert "brief claim mismatch" in str(exc)
    else:
        raise AssertionError("brief claims must remain bound to verified fingerprints")


def test_assessment_rejects_unbound_current_source_card_path(tmp_path: Path) -> None:
    cards = tmp_path / "reports/harness/source_cards/prior.jsonl"
    cards.parent.mkdir(parents=True)
    cards.write_text(
        json.dumps(_source_card("prior", "https://example.com/prior")) + "\n",
        encoding="utf-8",
    )
    iteration = tmp_path / "reports/research/iterations/round_unbound"
    iteration.mkdir(parents=True)
    (iteration / "external-brief.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "current_source_card_paths": ["reports/harness/source_cards/prior.jsonl"],
                "source_evidence_bindings": [],
                "sources": [_brief_source("https://example.com/prior") for _ in range(8)],
            }
        ),
        encoding="utf-8",
    )

    try:
        assess_iteration_knowledge("round_unbound", tmp_path)
    except ValueError as exc:
        assert "iteration mismatch" in str(exc)
    else:
        raise AssertionError("unbound current source cards must not be excluded as prior evidence")


def test_assessment_allows_fully_bound_zero_economic_change_repair_to_reuse_parent_evidence(
    tmp_path: Path,
) -> None:
    iteration, _parent, _repair_contract = _write_pure_implementation_repair_fixture(tmp_path)

    result = assess_iteration_knowledge(iteration.name, tmp_path)

    assert result.payload["status"] == "ok"
    assert result.payload["counts"] == {"reused": 8, "new": 0, "refresh_required": 0}
    exception = result.payload["novelty_policy"]["pure_implementation_repair_reuse"]
    assert exception["applied"] is True
    assert exception["source_iteration_id"] == "round_parent"
    assert exception["candidate_count"] == 8
    assert exception["incremental_economic_trial_count"] == 0


def test_assessment_keeps_new_or_refresh_gate_for_nonrepair_reuse(tmp_path: Path) -> None:
    iteration, _parent, _repair_contract = _write_pure_implementation_repair_fixture(tmp_path)
    manifest_path = iteration / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["implementation_repair_only"] = False
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = assess_iteration_knowledge(iteration.name, tmp_path)

    assert result.payload["status"] == "blocked"
    assert "knowledge_no_new_or_refresh_evidence" in result.payload["blocked"]
    assert result.payload["novelty_policy"]["pure_implementation_repair_reuse"] is None


def test_assessment_rejects_invalid_implementation_repair_reuse_contract(tmp_path: Path) -> None:
    iteration, parent, _repair_contract = _write_pure_implementation_repair_fixture(tmp_path)
    manifest_path = iteration / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"]["governance"]["repair_v1"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (parent / "knowledge-assessment.json").write_text(
        json.dumps({"iter_id": parent.name, "status": "blocked"}), encoding="utf-8"
    )

    result = assess_iteration_knowledge(iteration.name, tmp_path)

    assert result.payload["status"] == "blocked"
    assert "knowledge_no_new_or_refresh_evidence" in result.payload["blocked"]
    assert any(
        blocker.startswith("knowledge_implementation_repair_reuse_contract_invalid:")
        and "governance_binding:repair_v1:hash_mismatch" in blocker
        and "parent_knowledge_assessment" in blocker
        for blocker in result.payload["blocked"]
    )


def test_assessment_rejects_non_object_economic_equivalence_row(tmp_path: Path) -> None:
    iteration, _parent, repair_contract_path = _write_pure_implementation_repair_fixture(tmp_path)
    repair_contract = json.loads(repair_contract_path.read_text(encoding="utf-8"))
    repair_contract["economic_spec_equivalence"][0] = "invalid"
    repair_contract_path.write_text(json.dumps(repair_contract), encoding="utf-8")
    manifest_path = iteration / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    repair_binding = manifest["contracts"]["governance"]["repair_v1"]
    repair_binding["sha256"] = hashlib.sha256(repair_contract_path.read_bytes()).hexdigest()
    repair_binding["size_bytes"] = repair_contract_path.stat().st_size
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = assess_iteration_knowledge(iteration.name, tmp_path)

    assert result.payload["status"] == "blocked"
    assert "knowledge_no_new_or_refresh_evidence" in result.payload["blocked"]
    assert any(
        "implementation_repair_economic_identity" in blocker
        for blocker in result.payload["blocked"]
    )


def test_knowledge_cli_build_and_assess(tmp_path: Path, monkeypatch) -> None:
    iteration = tmp_path / "reports/research/iterations/round_four"
    iteration.mkdir(parents=True)
    (iteration / "external-brief.json").write_text(
        json.dumps(
            {"sources": [_brief_source(f"https://example.com/{index}") for index in range(8)]}
        ),
        encoding="utf-8",
    )
    _write_valid_scout(iteration, "round_four", new_candidate_count=1)
    monkeypatch.setattr("open_composer.cli.project_root", lambda: tmp_path)
    runner = CliRunner()

    build = runner.invoke(app, ["research", "knowledge", "build"], catch_exceptions=False)
    assess = runner.invoke(
        app,
        ["research", "knowledge", "assess", "round_four", "--json"],
        catch_exceptions=False,
    )

    assert build.exit_code == 0
    assert assess.exit_code == 0
    assert json.loads(assess.output)["status"] == "ok"


def test_iteration_context_retrieves_sources_negative_results_and_models(tmp_path: Path) -> None:
    cards = tmp_path / "reports/harness/source_cards/momentum.jsonl"
    cards.parent.mkdir(parents=True)
    source = _source_card("momentum", "https://example.com/momentum")
    source["applies_to"] = ["cross_sectional_momentum", "machine_learning"]
    cards.write_text(json.dumps(source) + "\n", encoding="utf-8")
    current = tmp_path / "reports/research/iterations/mom_current"
    current.mkdir(parents=True)
    (current / "external-brief.json").write_text(
        json.dumps({"topic_coverage": ["cross sectional momentum", "machine learning"]}),
        encoding="utf-8",
    )
    prior = tmp_path / "reports/research/iterations/mom_train"
    prior.mkdir(parents=True)
    (prior / "decision-record.md").write_text(
        "# Decision Record\n\n- Decision: stop\n- Reason: failed OOS.\n",
        encoding="utf-8",
    )
    model = prior / "models/model.joblib"
    model.parent.mkdir()
    model.write_bytes(b"model")
    challenge = tmp_path / "reports/research/iterations/mom_challenge"
    challenge.mkdir(parents=True)
    (challenge / "decision-record.md").write_text(
        "# Decision Record\n\n- Decision: stop\n- Reason: exposed challenge failed.\n",
        encoding="utf-8",
    )
    (challenge / "evaluation-report.json").write_text(
        json.dumps({"lockbox": {"return": 99}, "research_pass": False}),
        encoding="utf-8",
    )

    result = build_iteration_knowledge_context("mom_current", tmp_path)

    assert result.payload["matched_sources"][0]["canonical_url"].endswith("/momentum")
    assert result.payload["negative_empirical_memory"]
    assert result.payload["model_memory"]
    assert "status" not in result.payload["model_memory"][0]
    assert "artifact_path" not in result.payload["model_memory"][0]
    assert result.payload["restricted_memory_summary"]["challenge_result_count"] == 1
    assert result.payload["restricted_memory_summary"]["outcome_details_exposed"] is False
    assert result.payload["contract"]["context_is_research_input_not_alpha"] is True


def test_context_excludes_decision_records_that_reference_challenge(tmp_path: Path) -> None:
    current = tmp_path / "reports/research/iterations/mom_current"
    current.mkdir(parents=True)
    (current / "external-brief.json").write_text(
        json.dumps({"topic_coverage": ["momentum"]}), encoding="utf-8"
    )
    prior = tmp_path / "reports/research/iterations/mom_prior"
    prior.mkdir(parents=True)
    (prior / "decision-record.md").write_text(
        "# Decision Record\n\n- Decision: stop\n- Reason: exposed challenge failed.\n",
        encoding="utf-8",
    )
    (prior / "memory-provenance.json").write_text(
        json.dumps({"decision_record_visibility_partition": "train_only_empirical"}),
        encoding="utf-8",
    )

    result = build_iteration_knowledge_context("mom_current", tmp_path)

    assert result.payload["negative_empirical_memory"] == []
    assert result.payload["restricted_memory_summary"]["challenge_result_count"] == 1


def _source_card(claim_id: str, url: str) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "claim": f"Claim {claim_id}",
        "source_url": url,
        "source_type": "paper",
        "accessed_at": "2026-07-15",
        "applies_to": ["test"],
        "impact_on_spec": "test",
        "limitations": "test",
    }


def _brief_source(url: str) -> dict[str, str]:
    return {
        "url": url,
        "published_or_updated_at": f"accessed {date.today().isoformat()}",
        "source_type": "platform_docs",
        "credibility": "test",
        "core_claim": f"Claim for {url}",
        "project_applicability": "test",
        "reflection": "test",
    }


def _write_valid_scout(iteration: Path, iter_id: str, *, new_candidate_count: int) -> None:
    manifest = iteration / "knowledge-scout-queries.json"
    manifest.write_text(
        json.dumps({"queries": [{"query_id": "q", "query": "all:test"}]}),
        encoding="utf-8",
    )
    baseline = iteration / "knowledge-baseline.json"
    baseline.write_text(json.dumps({"schema_version": 1, "iter_id": iter_id}), encoding="utf-8")
    candidates = [
        {
            "canonical_url": f"https://example.com/scout-{index}",
            "validation_status": "candidate_unvalidated",
        }
        for index in range(new_candidate_count)
    ]
    (iteration / "knowledge-scout.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": iter_id,
                "query_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "baseline_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
                "candidate_count": len(candidates),
                "new_candidate_count": new_candidate_count,
                "candidates": candidates,
            }
        ),
        encoding="utf-8",
    )


def _write_pure_implementation_repair_fixture(
    root: Path,
) -> tuple[Path, Path, Path]:
    prior_cards = root / "reports/harness/source_cards/prior.jsonl"
    prior_cards.parent.mkdir(parents=True)
    urls = [f"https://example.com/reused-{index}" for index in range(8)]
    prior_cards.write_text(
        "\n".join(json.dumps(_source_card(str(index), url)) for index, url in enumerate(urls))
        + "\n",
        encoding="utf-8",
    )

    iterations = root / "reports/research/iterations"
    parent = iterations / "round_parent"
    iteration = iterations / "round_repair"
    parent.mkdir(parents=True)
    iteration.mkdir(parents=True)
    (parent / "knowledge-assessment.json").write_text(
        json.dumps({"iter_id": parent.name, "status": "ok"}), encoding="utf-8"
    )
    source_lock = parent / "lock-set/historical-evaluation-lock.json"
    source_lock.parent.mkdir()
    source_lock.write_text(json.dumps({"iter_id": parent.name}), encoding="utf-8")
    (iteration / "external-brief.json").write_text(
        json.dumps({"sources": [_brief_source(url) for url in urls]}), encoding="utf-8"
    )
    _write_valid_scout(iteration, iteration.name, new_candidate_count=1)

    def binding(path: Path) -> dict[str, object]:
        return {
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        }

    source_lock_binding = binding(source_lock)
    parent_audit = iteration / "parent-failure-audit.json"
    parent_audit.write_text(
        json.dumps(
            {
                "contract_id": "parent_audit_v1",
                "source_iteration_id": parent.name,
                "source_lock": source_lock_binding,
                "parameter_changes_from_outcomes": False,
                "paper_or_broker_activity": False,
                "failure": {
                    "selectable_candidate_returns_computed": False,
                    "selectable_candidate_metrics_computed": False,
                    "selection_performed": False,
                },
            }
        ),
        encoding="utf-8",
    )
    candidate_ids = [f"C{index:02d}" for index in range(8)]
    repair_contract = iteration / "implementation-repair-contract.json"
    repair_contract.write_text(
        json.dumps(
            {
                "contract_id": "repair_v1",
                "iter_id": iteration.name,
                "source_iteration_id": parent.name,
                "generated_before_repair_evaluation": True,
                "new_economic_candidate_count": 0,
                "manifest_candidate_count": len(candidate_ids),
                "effective_trial_count": 100,
                "parent_failure_audit": binding(parent_audit),
                "source_lock": source_lock_binding,
                "forbidden_changes": [
                    "universe",
                    "data",
                    "features",
                    "labels",
                    "models",
                    "seeds",
                    "fallbacks",
                    "folds",
                    "costs",
                    "benchmarks",
                    "economic_parameters",
                ],
                "economic_spec_equivalence": [
                    {"candidate_id": candidate_id, "economic_projection_equal": True}
                    for candidate_id in candidate_ids
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "iter_id": iteration.name,
        "source_iteration_id": parent.name,
        "implementation_repair_only": True,
        "incremental_economic_trial_count": 0,
        "single_new_hypothesis": "none_pure_implementation_repair",
        "candidate_count": len(candidate_ids),
        "candidates": [
            {
                "candidate_id": candidate_id,
                "implementation_repair_only": True,
                "effective_trial_increment": 0,
                "source_trial_id": f"{parent.name}:{candidate_id}",
            }
            for candidate_id in candidate_ids
        ],
        "contracts": {
            "governance": {
                "parent_audit_v1": binding(parent_audit),
                "repair_v1": binding(repair_contract),
            }
        },
    }
    (iteration / "candidate-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return iteration, parent, repair_contract


def _atom_feed() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2505.15155v2</id>
    <title>Known paper</title>
    <summary>Known summary.</summary>
    <published>2025-05-01T00:00:00Z</published>
    <author><name>Author One</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2607.00001v1</id>
    <title>New paper</title>
    <summary>New summary.</summary>
    <published>2026-07-01T00:00:00Z</published>
    <author><name>Author Two</name></author>
  </entry>
</feed>
"""
