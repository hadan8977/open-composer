from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.knowledge_memory import (
    VISIBILITY_PARTITIONS,
    assess_iteration_knowledge,
    build_knowledge_index,
    canonical_source_url,
    scout_knowledge,
)


def test_canonical_source_url_removes_tracking_and_arxiv_version() -> None:
    assert (
        canonical_source_url("HTTP://WWW.ARXIV.ORG/abs/2505.15155v2?utm_source=test")
        == "https://arxiv.org/abs/2505.15155"
    )
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

    (iteration / "knowledge-scout.json").write_text(
        json.dumps({"new_candidate_count": 2}), encoding="utf-8"
    )
    passed = assess_iteration_knowledge("round_three", tmp_path)

    assert passed.payload["status"] == "ok"
    assert passed.payload["counts"]["reused"] == 1
    assert passed.payload["counts"]["new"] == 7


def test_knowledge_cli_build_and_assess(tmp_path: Path, monkeypatch) -> None:
    iteration = tmp_path / "reports/research/iterations/round_four"
    iteration.mkdir(parents=True)
    (iteration / "external-brief.json").write_text(
        json.dumps(
            {"sources": [_brief_source(f"https://example.com/{index}") for index in range(8)]}
        ),
        encoding="utf-8",
    )
    (iteration / "knowledge-scout.json").write_text(
        json.dumps({"new_candidate_count": 1}), encoding="utf-8"
    )
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
