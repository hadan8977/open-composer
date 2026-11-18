from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from open_composer.research.knowledge_memory import build_knowledge_index
from open_composer.research.knowledge_tools import Knowledge, safe_path


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False))


def test_context_first_page_receives_current_run_and_latest_waiting_phase(tmp_path):
    task = tmp_path / "research/current"
    task.mkdir(parents=True)
    (task / "brief.md").write_text("frozen economic question " * 50)
    save(task / "runs/r1/lead/checkpoint.json", {"summary": "OLD_ZERO_ROOTS " * 100})
    save(
        task / "runs/r1/run.json",
        {
            "direction": "current",
            "run_id": "r1",
            "status": "running",
            "started": "2026-11-03T06:00:00+00:00",
            "phases": {
                "lead": {"started": "2026-11-03T09:00:00+00:00", "status": "blocked"},
                "worker_resume_5": {
                    "started": "2026-11-04T03:20:30+00:00",
                    "status": "blocked",
                    "session": "original-session",
                    "summary": "CURRENT_85_ROOTS",
                    "wait_state": {"state": "waiting"},
                },
            },
        },
    )
    save(
        task / "runs/r2/run.json",
        {
            "direction": "current",
            "run_id": "r2",
            "status": "round_finished",
            "started": "2026-11-04T04:00:00+00:00",
            "phases": {},
        },
    )
    k = Knowledge(tmp_path)
    try:
        k.index(["research/current"])
        response = k.context("current", budget=900)
        assert response["text"].splitlines()[0].endswith("runs/r1/run.json")
        summary = json.loads(response["text"].splitlines()[1])
        assert summary["latest_phase"]["name"] == "worker_resume_5"
        assert summary["latest_phase"]["wait_state"] == "waiting"
        assert summary["latest_phase"]["session"] == "original-session"
        assert "CURRENT_85_ROOTS" in response["text"]
        assert "OLD_ZERO_ROOTS" not in response["text"]
        assert len(response["text"]) <= 900 and response["omitted"]
    finally:
        k.close()


@pytest.fixture
def knowledge(tmp_path):
    cards = tmp_path / "reports/harness/source_cards/test.jsonl"
    cards.parent.mkdir(parents=True)
    cards.write_text(
        "\n".join(
            json.dumps(r, ensure_ascii=False)
            for r in [
                {
                    "source_url": "https://example.org/paper?utm_source=test",
                    "claim": "允许的收益回撤条件 experiment_20261104",
                    "visibility_partition": "public_literature",
                },
                {
                    "source_url": "https://example.org/paper",
                    "claim": "FORBIDDEN challenge_secret",
                    "visibility_partition": "challenge_result",
                },
                {
                    "source_url": "https://example.org/unknown",
                    "claim": "UNKNOWN_SECRET",
                    "visibility_partition": "restricted",
                },
            ]
        )
    )
    save(
        tmp_path / "research/current/runs/r1/worker/reply.json",
        {"status": "blocked", "summary": "TASK_DRAFT 等待任务恢复"},
    )
    save(
        tmp_path / "research/other/results.json",
        {"visibility_partition": "forward_observation", "summary": "FORBIDDEN_OTHER"},
    )
    save(
        tmp_path / "research/current/results.json",
        {"visibility_partition": "train_only_empirical", "historical_challenge": "MIXED_SECRET"},
    )
    k = Knowledge(tmp_path)
    k.index()
    yield k
    k.close()


def test_occurrence_visibility_applies_before_search_get_context_and_counts(knowledge):
    k = knowledge
    allowed = k.search("收益回撤")
    assert allowed["visible_matches"] == 1
    assert "允许" in allowed["text"] and "FORBIDDEN" not in allowed["text"]
    assert k.search("challenge_secret")["visible_matches"] == 0
    assert k.search("UNKNOWN_SECRET")["visible_matches"] == 0
    assert k.search("TASK_DRAFT")["visible_matches"] == 0
    assert k.search("TASK_DRAFT", task="current")["visible_matches"] == 1
    assert k.status()["visible_documents"] == 1
    all_rows = k.db.execute("SELECT * FROM docs").fetchall()
    for row in all_rows:
        result = k.get(row["id"])
        if row["visibility"] != "public_literature":
            assert result["state"] == "unavailable"
        assert not any(w in json.dumps(result) for w in ("FORBIDDEN", "MIXED_SECRET"))
    assert "TASK_DRAFT" in k.context("current")["text"]
    assert "FORBIDDEN" not in k.context("current")["text"]
    assert "MIXED_SECRET" not in k.context("current")["text"]
    assert k.get("../../control.json")["state"] == "unavailable"
    assert k.search("experiment_20261104")["visible_matches"] == 1


def test_incremental_deleted_changed_and_directory_sources_never_return_cached_text(knowledge):
    k = knowledge
    source = k.root / "reports/harness/source_cards/test.jsonl"
    before = k.db.execute(
        "SELECT version FROM files WHERE path=?", ("reports/harness/source_cards/test.jsonl",)
    ).fetchone()[0]
    k.index()
    assert (
        k.db.execute(
            "SELECT version FROM files WHERE path=?", ("reports/harness/source_cards/test.jsonl",)
        ).fetchone()[0]
        == before
    )
    source.unlink()
    assert k.search("收益回撤")["visible_matches"] == 0
    k.index()
    assert k.db.execute("SELECT count(*) FROM docs").fetchone()[0] == 6
    source.mkdir()
    k.index()
    assert k.status()["visible_documents"] == 0
    source.rmdir()
    source.write_text(
        json.dumps(
            {
                "source_url": "https://example.org/new",
                "claim": "UPDATED",
                "visibility_partition": "public_literature",
            }
        )
    )
    k.index()
    assert k.search("UPDATED")["visible_matches"] == 1
    assert k.search("experiment_20261104")["visible_matches"] == 0


def test_pagination_and_visibility_changes_without_reindex(knowledge):
    k = knowledge
    row = k.visible()[0]
    original = k.get(row["id"], budget=16000)["text"]
    fragments = []
    offset = 0
    while True:
        response = k.get(row["id"], offset=offset, budget=128)
        fragments.append(response["text"])
        if response["next_offset"] is None:
            break
        offset = response["next_offset"]
    assert "".join(fragments) == original
    assert response["budget_unit"] == "characters"
    source = k.root / row["path"]
    source.write_text(source.read_text().replace("public_literature", "challenge_result"))
    assert k.get(row["id"])["state"] == "unavailable"
    assert k.status()["visible_documents"] == 0


def test_path_symlink_scope_and_unknown_schema(knowledge, tmp_path):
    k = knowledge
    secret = tmp_path / "secret.json"
    secret.write_text("secret")
    link = tmp_path / "research/current/brief.md"
    link.symlink_to(secret)
    k.index()
    with pytest.raises(ValueError):
        safe_path(tmp_path, "research/current/brief.md")
    with pytest.raises(ValueError):
        k.index(["../secret"])
    with pytest.raises(ValueError):
        k.index(["config"])
    dbpath = tmp_path / "runtime/research-tools/knowledge.sqlite3"
    with sqlite3.connect(dbpath) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="Unsupported"):
        Knowledge(tmp_path)


def test_legacy_build_refuses_symlink_before_collection(tmp_path):
    archived = tmp_path / "private/archive"
    archived.mkdir(parents=True)
    target = tmp_path / "reports/research/knowledge/index.json"
    target.parent.mkdir(parents=True)
    target.symlink_to(archived, target_is_directory=True)
    with pytest.raises(ValueError, match="archived/symlinked"):
        build_knowledge_index(tmp_path)
    assert target.is_symlink() and not list(archived.iterdir())


def test_both_agents_use_identical_real_cli_and_offline_claude_contract(tmp_path):
    import subprocess
    import sys

    from open_composer.research.agent_workflow import Reply

    project = Path(__file__).resolve().parents[1]
    contract = json.loads((project / "tests/fixtures/research-tools/cli-contract.json").read_text())
    assert contract["tools"]["codex"] == contract["tools"]["claude"]
    source = tmp_path / "reports/harness/source_cards/allowed.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "source_url": "https://example.org/drawdown",
                "claim": "drawdown observation",
                "visibility_partition": "public_literature",
            }
        )
    )
    prefix = [sys.executable, str(project / "scripts/research_tools.py"), "--root", str(tmp_path)]
    subprocess.run([*prefix, "index"], check=True, capture_output=True, text=True)
    responses = []
    for provider in ("codex", "claude"):
        args = contract["tools"][provider][2:]
        call = subprocess.run([*prefix, *args], check=True, capture_output=True, text=True)
        responses.append(json.loads(call.stdout))
    assert responses[0] == responses[1]
    assert responses[0]["visible_matches"] == 1
    assert len(responses[0]["text"]) <= 128
    fixture = contract["claude_result_fixture"]
    reply = Reply.model_validate(fixture["structured_output"])
    assert reply.wait is None and fixture["session_id"] == "fixture-session"
    resume = contract["claude_examples"]["resume"]
    assert resume[:2] == ["claude", "-p"]
    assert resume[resume.index("--resume") + 1] == fixture["session_id"]
    assert all("--bare" not in command for command in contract["claude_examples"].values())
    old = dict(fixture["structured_output"])
    old.pop("wait")
    old.pop("next_review")
    assert Reply.model_validate(old).wait is None


def test_old_occurrences_and_bilingual_aliases_are_admitted_only_with_visibility(tmp_path):
    save(
        tmp_path / "reports/research/iterations/legacy/external-brief.json",
        {
            "sources": [
                {
                    "url": "https://example.org/old",
                    "core_claim": "drawdown condition OLD_ID",
                    "visibility_partition": "public_literature",
                },
                {
                    "url": "https://example.org/old",
                    "core_claim": "HIDDEN_OLD",
                    "visibility_partition": "challenge_result",
                },
                {"url": "https://example.org/unknown", "core_claim": "HIDDEN_UNKNOWN"},
            ]
        },
    )
    save(
        tmp_path / "reports/research/iterations/legacy/evaluation-report.json",
        {"visibility_partition": "train_only_empirical", "summary": "回撤持续时长 train"},
    )
    k = Knowledge(tmp_path)
    try:
        k.index(["reports/research/iterations"])
        result = k.search("回撤")
        assert result["visible_matches"] == 2 and "OLD_ID" in result["text"]
        assert k.search("drawdown")["visible_matches"] == 2
        assert k.search("OLD_ID")["visible_matches"] == 1
        assert k.search("HIDDEN_OLD")["visible_matches"] == 0
        assert k.search("HIDDEN_UNKNOWN")["visible_matches"] == 0
        assert k.status()["visible_documents"] == 2
        hidden = k.db.execute("SELECT id FROM docs WHERE text LIKE '%HIDDEN_OLD%'").fetchone()[0]
        assert k.get(hidden)["state"] == "unavailable"
    finally:
        k.close()


def test_task_list_and_invalid_task_diagnostics(tmp_path):
    save(tmp_path / "research/current/brief.md", {"question": "TASK_LIST"})
    k = Knowledge(tmp_path)
    try:
        k.index(["research/current"])
        tasks = k.tasks()
        assert "current" in tasks["tasks"]
        assert "current" in tasks["text"]
        with pytest.raises(ValueError, match="direction directory"):
            k.visible("bad task!")
    finally:
        k.close()


def test_missing_visibility_defaults_to_public_literature(tmp_path):
    source = tmp_path / "reports/harness/source_cards/default.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "claim_id": "default-public",
                "source_url": "https://example.org/default-public",
                "claim": "DEFAULT_PUBLIC_CLAIM",
                "source_type": "paper",
                "accessed_at": "2026-11-15",
            }
        )
    )
    k = Knowledge(tmp_path)
    try:
        result = k.index(["reports/harness/source_cards"])
        assert result["source_cards"]["valid"] == 1
        response = k.search("DEFAULT_PUBLIC_CLAIM")
        assert response["visible_matches"] == 1
        assert '"schema_valid": true' in response["text"]
        assert '"quote": false' in response["text"]
        assert k.status()["visible_documents"] == 1
    finally:
        k.close()


def test_exact_duplicate_source_cards_collapse_in_search(tmp_path):
    card = {
        "claim_id": "same-claim",
        "source_url": "https://example.org/same",
        "claim": "SAME_DUPLICATE_CLAIM",
        "source_type": "paper",
        "accessed_at": "2026-11-15",
    }
    for name in ("one", "two"):
        path = tmp_path / f"reports/harness/source_cards/{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(card))
    k = Knowledge(tmp_path)
    try:
        result = k.index(["reports/harness/source_cards"])
        assert result["canonical_source_cards"] == 1
        assert result["duplicate_source_rows"] == 1
        response = k.search("SAME_DUPLICATE_CLAIM")
        assert response["visible_matches"] == 1
        assert '"usage_count": 2' in response["text"]
        status = k.status()
        assert status["canonical_source_cards"] == 1
        assert status["duplicate_source_rows"] == 1
    finally:
        k.close()


def test_failures_and_map_use_row_level_internal_records(tmp_path):
    save(
        tmp_path / "research/current/brief.md",
        {"question": "CURRENT_QUESTION"},
    )
    (tmp_path / "research/current/brief.md").write_text("CURRENT_QUESTION")
    trials = tmp_path / "research/current/trials.jsonl"
    trials.parent.mkdir(parents=True, exist_ok=True)
    trials.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {
                    "trial_id": "t-failed",
                    "event": "finished",
                    "status": "failed",
                    "counts_as_trial": True,
                    "note": "lookahead in feature",
                },
                {
                    "trial_id": "t-ok",
                    "event": "finished",
                    "status": "complete",
                    "counts_as_trial": True,
                },
            ]
        )
    )
    decisions = tmp_path / "research/current/decisions.tsv"
    decisions.write_text(
        "variant\tdecision\tnote\nD1\tpark\tFAILED_BRANCH\nD2\tPark_pending\tCASE_INSENSITIVE\n"
    )
    verdicts = tmp_path / "reports/owner/verdicts.jsonl"
    verdicts.parent.mkdir(parents=True)
    verdicts.write_text(
        json.dumps({"event_id": "E1", "verdict": "correct", "what_was_wrong": "OWNER_NOTE"})
    )
    registry = tmp_path / "reports/research/trials.jsonl"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"candidate_id": "c1", "family": "test"}))
    caps = tmp_path / "capabilities/registry.yaml"
    caps.parent.mkdir()
    caps.write_text(
        "version: 1\ncapabilities:\n  - id: market.test\n    status: trial\n    provider: test\n"
    )
    k = Knowledge(tmp_path)
    try:
        indexed = k.index()
        assert indexed["documents"] >= 7
        failed = k.failures("lookahead")
        assert failed["failed"] == 1
        assert "t-failed" in failed["text"] and "lookahead" in failed["text"]
        branch = k.failures("FAILED_BRANCH")
        assert branch["failed"] >= 1 and "park" in branch["text"]
        assert k.failures("CASE_INSENSITIVE")["failed"] == 1
        missing = k.failures("NO_SUCH_FAILURE")
        assert missing["failed"] == 0 and missing["available_failures"] >= 2
        mapped = k.map(task="current")
        assert "research/current/brief.md" in mapped["text"]
        assert "research/current/trials.jsonl" in mapped["text"]
        assert (
            "reports/owner/verdicts.jsonl" in k.status()["text"]
            or k.search("OWNER_NOTE")["visible_matches"] == 1
        )
        assert k.search("market.test")["visible_matches"] >= 1
        assert "capabilities/registry.yaml" in k.search("market.test")["text"]
    finally:
        k.close()


def test_large_task_log_uses_bounded_byte_read_and_is_never_design_evidence(tmp_path):
    path = tmp_path / "research/example/runs/r1/worker/engine.log"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x" * 700000 + b"END_MARKER")
    k = Knowledge(tmp_path)
    try:
        k.index(["research/example"])
        assert not k.visible()
        row = k.visible("example")[0]
        assert k.get(row["id"])["state"] == "unavailable"
        result = k.get(row["id"], task="example", byte_offset=699990, budget=128)
        assert result["text"].endswith("END_MARKER")
        assert result["budget_unit"] == "bytes" and result["next_offset"] is None
        assert len(result["text"]) == 20
        path.unlink()
        assert k.get(row["id"], task="example")["state"] == "unavailable"
    finally:
        k.close()


@pytest.mark.parametrize(
    "restricted",
    [
        {"lockbox": {"result": "RESTRICTED_SENTINEL"}},
        {"wrapper": [{"historical_challenge": {"result": "RESTRICTED_SENTINEL"}}]},
        {"wrapper": {"forward_observation": {"result": "RESTRICTED_SENTINEL"}}},
        {"wrapper": {"visibility_partition": "challenge_result", "result": "RESTRICTED_SENTINEL"}},
    ],
)
def test_nested_mixed_occurrences_and_task_documents_never_enter_any_read(tmp_path, restricted):
    card = {
        "source_url": "https://example.org/paper",
        "visibility_partition": "public_literature",
        "claim": "public claim",
        **restricted,
    }
    source = tmp_path / "reports/harness/source_cards/mixed.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(card))
    save(
        tmp_path / "reports/research/iterations/mixed/external-brief.json",
        {
            "sources": [
                {**card, "url": card["source_url"]},
                {
                    "url": card["source_url"],
                    "visibility_partition": "public_literature",
                    "core_claim": "PUBLIC_SIBLING",
                },
            ]
        },
    )
    save(
        tmp_path / "research/example/results.json",
        {"visibility_partition": "train_only_empirical", **restricted},
    )
    k = Knowledge(tmp_path)
    try:
        k.index()
        hidden_ids = [
            r[0]
            for r in k.db.execute("SELECT id FROM docs WHERE text LIKE '%RESTRICTED_SENTINEL%'")
        ]
        assert len(hidden_ids) == 3
        assert k.search("RESTRICTED_SENTINEL")["visible_matches"] == 0
        assert k.search("RESTRICTED_SENTINEL", task="example")["visible_matches"] == 0
        assert k.status()["visible_documents"] == 1
        assert k.status(task="example")["visible_documents"] == 1
        assert k.search("PUBLIC_SIBLING")["visible_matches"] == 1
        for response in [
            k.status(),
            k.status(task="example"),
            k.context("example"),
            *(k.get(i, task="example") for i in hidden_ids),
        ]:
            assert "RESTRICTED_SENTINEL" not in json.dumps(response)
        # An older derived row may have admitted unchanged mixed bytes. Every
        # live read rechecks occurrence policy, without requiring source edits.
        k.db.execute("UPDATE docs SET visibility='public_literature' WHERE id=?", (hidden_ids[0],))
        k.db.commit()
        assert k.get(hidden_ids[0])["state"] == "unavailable"
        assert k.search("RESTRICTED_SENTINEL")["visible_matches"] == 0
        assert k.status()["visible_documents"] == 1
    finally:
        k.close()
