from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


from open_composer.research.agent_workflow import run_round
from open_composer.research.direction import (
    TEXT_FIELDS,
    direction_review_template,
    validate_direction_review,
)
from open_composer.research.iteration_dossier import (
    init_iteration_dossier,
    validate_iteration_dossier,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def review(root: Path, now: datetime) -> Path:
    snapshot = root / "source.txt"
    snapshot.write_text("Official description of source coverage and limitations.")
    stamp = now.isoformat()
    payload = direction_review_template("test_direction")
    payload.update(dict.fromkeys(TEXT_FIELDS, "An explicit, bounded research decision."))
    payload.update(
        {
            "reviewed_at": stamp,
            "decision": "proceed",
            "queries": [
                {
                    "query": "source coverage replication",
                    "searched_at": stamp,
                    "opened_urls": ["https://example.org/source"],
                }
            ],
            "sources": [
                {
                    "url": "https://example.org/source",
                    "claim": "Coverage is limited.",
                    "source_type": "provider_official_docs",
                    "published_or_updated_at": "unknown",
                    "market_and_period": "US equities; research window preregistered separately",
                    "applicability": "Test coverage before testing a strategy",
                    "limitations": "No profitability evidence",
                    "independent_replication": "Not found",
                    "fetched_at": stamp,
                    "snapshot_path": "source.txt",
                    "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                }
            ],
            "cheapest_decisive_test": {
                "action": "Measure coverage",
                "pass_condition": "Coverage >= .95",
                "falsification_condition": "Coverage < .95",
                "max_compute_minutes": 1,
            },
        }
    )
    path = root / "direction-review.json"
    payload["sources"][0].update({"source_card_path": "cards.jsonl", "claim_id": "coverage"})
    (root / "cards.jsonl").write_text(
        json.dumps(
            {
                "claim_id": "coverage",
                "claim": "Coverage is limited.",
                "fetched_at": stamp,
                "source_url": "https://example.org/source",
                "verification_status": "source_verified",
                "quote": snapshot.read_text(),
                "source_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            }
        )
        + "\n"
    )
    write_json(path, payload)
    return path


def test_direction_requires_opened_unchanged_sources(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    path = review(tmp_path, now)
    assert validate_direction_review(path, tmp_path, now=now) == []
    (tmp_path / "source.txt").write_text("Silently replaced evidence")
    assert "direction_source_0:snapshot_missing_or_hash_mismatch" in validate_direction_review(
        path, tmp_path, now=now
    )


def test_v3_direction_review_binds_sources_query_manifest_and_knowledge_baseline(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    path = review(tmp_path, now)
    payload = json.loads(path.read_text())
    query_manifest = tmp_path / "query-manifest.json"
    query_manifest.write_text(json.dumps({"queries": payload["queries"]}))
    baseline = tmp_path / "knowledge-baseline.json"
    baseline.write_text(json.dumps({"prior_claims": [], "negative_evidence": []}))
    source = payload["sources"][0]
    payload.update(
        {
            "schema_version": 3,
            "source_evidence_bindings": [
                {
                    "claim_id": source["claim_id"],
                    "source_card_path": source["source_card_path"],
                    "snapshot_path": source["snapshot_path"],
                    "snapshot_sha256": source["sha256"],
                    "source_url": source["url"],
                }
            ],
            "query_manifest": {
                "path": query_manifest.name,
                "sha256": hashlib.sha256(query_manifest.read_bytes()).hexdigest(),
            },
            "pre_iteration_knowledge_baseline": {
                "path": baseline.name,
                "sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
            },
        }
    )
    write_json(path, payload)
    assert validate_direction_review(path, tmp_path, now=now) == []

    payload["source_evidence_bindings"][0]["snapshot_sha256"] = "0" * 64
    write_json(path, payload)
    assert any(
        item.startswith("direction_v3_source_evidence_binding_mismatch:")
        for item in validate_direction_review(path, tmp_path, now=now)
    )


def test_source_must_match_query_and_iteration(tmp_path: Path) -> None:
    path = review(tmp_path, datetime.now(UTC))
    payload = json.loads(path.read_text())
    payload["queries"][0]["opened_urls"] = ["https://example.org/something-else"]
    write_json(path, payload)
    blocked = validate_direction_review(path, tmp_path, expected_iter_id="different_iteration")
    assert "direction_source_0:not_in_search_receipt" in blocked
    assert "direction_review_iteration_mismatch" in blocked


def test_staleness_blocks_new_compute_but_preserves_final_receipt(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    path = review(tmp_path, now - timedelta(days=31))
    assert "direction_review_stale" in validate_direction_review(path, tmp_path, now=now)
    assert validate_direction_review(path, tmp_path, now=now, check_freshness=False) == []


def test_unverified_or_unquoted_claim_does_not_pass(tmp_path: Path) -> None:
    path = review(tmp_path, datetime.now(UTC))
    cards = json.loads((tmp_path / "cards.jsonl").read_text())
    cards["quote"] = "A fabricated statement that the fetched page does not contain."
    (tmp_path / "cards.jsonl").write_text(json.dumps(cards) + "\n")
    assert "direction_source_0:verified_claim_binding_invalid" in validate_direction_review(
        path, tmp_path
    )


def test_new_iteration_cannot_downgrade_schema_to_bypass_installed_policy(tmp_path: Path) -> None:
    paths = init_iteration_dossier("test_direction", tmp_path)
    write_json(tmp_path / "config/research-direction-legacy.json", {"frozen_iterations": {}})
    brief = json.loads(paths.external_brief_json.read_text())
    brief["schema_version"] = 2
    write_json(paths.external_brief_json, brief)
    (paths.root / "direction-review.json").unlink()
    assert (
        "direction_review_missing_or_invalid"
        in validate_iteration_dossier("test_direction", tmp_path).blocked
    )


def test_new_iteration_gate_cannot_omit_direction_review(tmp_path: Path) -> None:
    paths = init_iteration_dossier("test_direction", tmp_path)
    assert json.loads(paths.external_brief_json.read_text())["schema_version"] == 3
    (paths.root / "direction-review.json").unlink()
    assert (
        "direction_review_missing_or_invalid"
        in validate_iteration_dossier("test_direction", tmp_path).blocked
    )
    # Historical frozen schema keeps its original contract.
    brief = json.loads(paths.external_brief_json.read_text())
    brief["schema_version"] = 2
    write_json(paths.external_brief_json, brief)
    assert not any(
        b.startswith("direction_")
        for b in validate_iteration_dossier("test_direction", tmp_path).blocked
    )


def test_chinese_brief_is_preserved_in_neutral_workflow(tmp_path: Path, repo_root: Path) -> None:
    write_json(tmp_path / "control.json", {"draft": False, "research": True})
    write_json(
        tmp_path / "config/memory-budget.json",
        json.loads((repo_root / "config/memory-budget.json").read_text(encoding="utf-8")),
    )
    workflow = json.loads((repo_root / "research/workflow.json").read_text())
    write_json(tmp_path / "research/workflow.json", workflow)
    for role in workflow["roles"].values():
        prompt_path = tmp_path / role["prompt"]
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_bytes((repo_root / role["prompt"]).read_bytes())
    brief = tmp_path / "research/chinese_fixture/brief.md"
    brief.parent.mkdir()
    original = "继续优化策略，尽快盈利\nContext: docs/research-mission.zh.md\n".encode()
    brief.write_bytes(original)
    # The blocked-worker policy keeps routine checkpoints out of Lead rounds, so
    # this neutral workflow fixture uses a real completed worker result instead.
    write_json(tmp_path / "research/chinese_fixture/raw.json", {"fixture_profit": 2})
    write_json(
        tmp_path / "research/chinese_fixture/results.json",
        {
            "direction": "chinese_fixture",
            "kind": "diagnostic",
            "engine": "synthetic fixture",
            "source_artifacts": ["research/chinese_fixture/raw.json"],
            "data_and_exposure": "fixture only",
            "costs": "not a financial result",
            "baseline": "fixture",
            "n_trials": 0,
            "net_profit_usd": None,
            "baseline_net_profit_usd": None,
            "dsr": None,
            "dsr_note": "not applicable to a fixture",
            "limitations": ["No economic evidence"],
        },
    )
    prompts = {}

    def transport(_command, prompt, folder, _timeout):
        phase = folder.name
        prompts[phase] = prompt
        reference = next(
            line.removeprefix("Brief: ")
            for line in prompt.splitlines()
            if line.startswith("Brief: ")
        )
        assert (tmp_path / reference).read_bytes() == original
        write_json(
            folder / "reply.json",
            {
                "status": "complete",
                "summary": "Synthetic transport only; no model or research execution",
                "decision": "continue" if phase == "worker" else "park",
                "results": ("research/chinese_fixture/results.json" if phase == "worker" else None),
                "next_brief": None,
                "checkpoint": None,
            },
        )
        return {"exit_code": 0, "session": f"fixture-{phase}", "usage": None}

    state = run_round(tmp_path, "chinese_fixture", "r1", 30, execute_fn=transport)

    assert state["status"] == "round_finished"
    assert set(prompts) == {"worker", "lead"}
    assert brief.read_bytes() == original
    assert (brief.parent / "runs/r1/brief.md").read_bytes() == original
    worker = workflow["roles"]["worker"]
    assert prompts["worker"].startswith((repo_root / worker["prompt"]).read_text())
    assert "继续优化策略" not in prompts["worker"]  # Read the file; do not inject/rewrite it.


def test_claim_cannot_be_replaced_or_refreshed_without_new_source_receipt(tmp_path: Path) -> None:
    path = review(tmp_path, datetime.now(UTC))
    payload = json.loads(path.read_text())
    payload["sources"][0]["claim"] = "A completely different unsupported profitability claim."
    write_json(path, payload)
    assert "direction_source_0:verified_claim_binding_invalid" in validate_direction_review(
        path, tmp_path
    )
    path = review(tmp_path, datetime.now(UTC))
    payload = json.loads(path.read_text())
    payload["sources"][0]["fetched_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    write_json(path, payload)
    assert "direction_source_0:verified_claim_binding_invalid" in validate_direction_review(
        path, tmp_path
    )


def test_partial_historical_directory_cannot_exempt_new_dossier(tmp_path: Path) -> None:
    paths = init_iteration_dossier("test_direction", tmp_path)
    manifest = paths.root / "candidate-manifest.json"
    manifest.write_text("{}")
    write_json(
        tmp_path / "config/research-direction-legacy.json",
        {
            "frozen_iterations": {
                "test_direction": {
                    "candidate-manifest.json": hashlib.sha256(manifest.read_bytes()).hexdigest()
                }
            }
        },
    )
    brief = json.loads(paths.external_brief_json.read_text())
    brief["schema_version"] = 2
    write_json(paths.external_brief_json, brief)
    (paths.root / "direction-review.json").unlink()
    assert (
        "direction_review_missing_or_invalid"
        in validate_iteration_dossier("test_direction", tmp_path).blocked
    )
