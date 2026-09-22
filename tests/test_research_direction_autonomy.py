from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from open_composer.research import autonomy
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


def test_chinese_prompt_injects_documented_context_not_rewritten_prompt(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1] / ".claude/hooks/UserPromptSubmit-harness-context.sh"
    )
    result = subprocess.run(
        ["bash", str(script)],
        input=json.dumps({"prompt": "继续优化策略，尽快盈利"}),
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "OC_ROOT": str(tmp_path)},
    )
    output = json.loads(result.stdout)
    assert "prompt" not in output
    assert output["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "research-mission.zh.md" in output["hookSpecificOutput"]["additionalContext"]


def setup_queue(tmp_path: Path, monkeypatch) -> dict:
    config = {
        "enabled": True,
        "engine": "claude",
        "daily_fresh_tokens": 10000,
        "rolling_5h_fresh_tokens": 10000,
        "interactive_reserve_fresh_tokens": 3000,
        "max_task_fresh_tokens": 1000,
        "max_task_seconds": 30,
        "max_tasks_per_day": 3,
    }
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Read the mission and research a primary source.")
    task = {
        "id": "scout_one",
        "kind": "scout",
        "prompt_path": "prompt.md",
        "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
        "depends_on": [],
    }
    write_json(tmp_path / autonomy.CONFIG_PATH, config)
    write_json(tmp_path / autonomy.QUEUE_PATH, {"tasks": [task]})
    monkeypatch.setattr(
        autonomy,
        "usage_snapshot",
        lambda: {
            "observed_at": datetime.now(UTC).isoformat(),
            "fresh_5h": 500,
            "observable": True,
            "retry_after": None,
            "unknown_throttle_reset": False,
        },
    )
    return config


def test_dry_run_does_not_spawn_or_reserve_and_completed_task_is_not_repeated(
    tmp_path, monkeypatch
) -> None:
    setup_queue(tmp_path, monkeypatch)
    calls = []

    def worker(argv, root, output, config):
        calls.append(argv)
        persisted = json.loads((root / autonomy.STATE_DIR / "state.json").read_text())
        assert persisted["tasks"]["scout_one"]["status"] == "started"
        assert "Bash" not in " ".join(argv)
        return {"exit_code": 0, "stop_reason": None}

    monkeypatch.setattr(autonomy, "_run_worker", worker)
    assert autonomy.tick(tmp_path)["mode"] == "dry_run"
    assert calls == []
    assert not (tmp_path / autonomy.STATE_DIR).exists()
    assert autonomy.tick(tmp_path, execute=True)["status"] == "completed"
    assert autonomy.tick(tmp_path, execute=True)["status"] == "idle"
    assert len(calls) == 1


def test_unknown_budget_and_interactive_reserve_prevent_dispatch(tmp_path, monkeypatch) -> None:
    config = setup_queue(tmp_path, monkeypatch)
    config["daily_fresh_tokens"] = None
    write_json(tmp_path / autonomy.CONFIG_PATH, config)
    assert "explicit_absolute_budget_required" in autonomy.tick(tmp_path, execute=True)["blocked"]
    config["daily_fresh_tokens"] = 10000
    usage = autonomy.usage_snapshot()
    usage["fresh_5h"] = 6500
    assert "interactive_reserve_or_5h_budget" in autonomy.budget_blockers(
        config, {"tasks": {}}, usage, datetime.now(UTC)
    )


def test_crashed_task_blocks_new_work_and_keeps_reservation(tmp_path, monkeypatch) -> None:
    setup_queue(tmp_path, monkeypatch)
    write_json(
        tmp_path / autonomy.STATE_DIR / "state.json",
        {
            "tasks": {
                "old_task": {
                    "status": "started",
                    "started_at": datetime.now(UTC).isoformat(),
                    "reserved_fresh_tokens": 1000,
                },
            }
        },
    )
    assert (
        "unfinished_task_requires_reconciliation"
        in autonomy.tick(tmp_path, execute=True)["blocked"]
    )


def test_active_429_pauses_even_with_unused_budget(tmp_path, monkeypatch) -> None:
    config = setup_queue(tmp_path, monkeypatch)
    usage = autonomy.usage_snapshot()
    usage["retry_after"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    assert "rate_limited" in autonomy.budget_blockers(
        config, {"tasks": {}}, usage, datetime.now(UTC)
    )


def test_429_arriving_before_spawn_prevents_the_model_call(tmp_path, monkeypatch) -> None:
    config = setup_queue(tmp_path, monkeypatch)
    usage = autonomy.usage_snapshot()
    usage["retry_after"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    monkeypatch.setattr(autonomy, "usage_snapshot", lambda: usage)
    monkeypatch.setattr(
        autonomy.subprocess, "Popen", lambda *a, **kw: pytest.fail("must not spawn")
    )
    result = autonomy._run_worker(["claude"], tmp_path, tmp_path / "out.log", config)
    assert "rate_limited" in result["stop_reason"]


def test_empty_or_error_claude_json_does_not_complete_task(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    for payload in (
        {},
        {"type": "result", "subtype": "success", "is_error": True, "result": "error"},
    ):
        write_json(path, payload)
        assert not autonomy._claude_result_success(path)
    write_json(
        path,
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Evidence and proposal",
        },
    )
    assert autonomy._claude_result_success(path)


def test_state_symlink_cannot_write_outside_workspace(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    setup_queue(root, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    state_dir = root / autonomy.STATE_DIR
    state_dir.parent.mkdir(parents=True)
    state_dir.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        autonomy.tick(root, execute=True)
    assert list(outside.iterdir()) == []


def test_corrupt_transcript_is_unknown_usage_not_zero_budget(tmp_path, monkeypatch) -> None:
    from open_composer.cockpit.data import quota

    transcript = tmp_path / "workspace" / "session.jsonl"
    transcript.parent.mkdir()
    transcript.write_text("not-json\n")
    monkeypatch.setattr(quota, "CLAUDE_PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(quota, "SUBAGENT_TASKS_ROOT", tmp_path / "no-subagents")
    assert autonomy.usage_snapshot()["observable"] is False


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
