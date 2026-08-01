from __future__ import annotations

import json
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
        "published_or_updated_at": "accessed 2026-07-15",
        "source_type": "platform_docs",
        "credibility": "test",
        "core_claim": f"Claim for {url}",
        "project_applicability": "test",
        "reflection": "test",
    }


def _write_valid_scout(iteration: Path, iter_id: str, *, new_candidate_count: int) -> None:
    import hashlib

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
