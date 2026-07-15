from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.models.source_card import SourceCard, check_source_card
from open_composer.storage import write_json

KNOWLEDGE_ROOT = Path("reports/research/knowledge")
ITERATION_ROOT = Path("reports/research/iterations")
VISIBILITY_PARTITIONS = (
    "public_literature",
    "train_only_empirical",
    "challenge_result",
    "forward_observation",
)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}
ARXIV_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}
ARXIV_API_URL = "https://export.arxiv.org/api/query"


@dataclass(frozen=True)
class KnowledgeBuildResult:
    index_path: Path
    payload: dict[str, Any]


@dataclass(frozen=True)
class KnowledgeScoutResult:
    report_path: Path
    payload: dict[str, Any]


@dataclass(frozen=True)
class KnowledgeAssessmentResult:
    report_path: Path
    payload: dict[str, Any]


def canonical_source_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlsplit(raw)
    scheme = parsed.scheme.lower() or "https"
    host = parsed.netloc.lower()
    path = re.sub(r"/+$", "", parsed.path) or "/"
    if host in {"arxiv.org", "www.arxiv.org"}:
        host = "arxiv.org"
        path = re.sub(r"v\d+$", "", path)
        scheme = "https"
    if host == "doi.org":
        path = path.lower()
        scheme = "https"
    query_items = [
        (key, item)
        for key, item in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    query = urllib.parse.urlencode(sorted(query_items))
    return urllib.parse.urlunsplit((scheme, host, path, query, ""))


def claim_fingerprint(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_knowledge_index(root: Path | None = None) -> KnowledgeBuildResult:
    base = root or project_root()
    source_rows = _collect_sources(base)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        grouped[str(row["canonical_url"])].append(row)

    sources = []
    for canonical_url, rows in sorted(grouped.items()):
        claims = _unique_strings(str(row.get("claim") or "") for row in rows)
        locations = _unique_strings(str(row["location"]) for row in rows)
        accessed = sorted(
            value for value in (str(row.get("accessed_at") or "") for row in rows) if value
        )
        stale_rows = [row for row in rows if bool(row.get("stale"))]
        sources.append(
            {
                "source_id": hashlib.sha256(canonical_url.encode("utf-8")).hexdigest(),
                "canonical_url": canonical_url,
                "source_types": _unique_strings(
                    str(row.get("source_type") or "unverified") for row in rows
                ),
                "first_seen": accessed[0] if accessed else None,
                "last_verified": accessed[-1] if accessed else None,
                "occurrence_count": len(rows),
                "duplicate_count": max(0, len(rows) - 1),
                "claims": claims,
                "claim_fingerprints": [claim_fingerprint(claim) for claim in claims],
                "locations": locations,
                "stale": bool(stale_rows) and len(stale_rows) == len(rows),
            }
        )

    empirical = _collect_empirical_memory(base)
    models = _collect_model_memory(base)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "visibility_partitions": list(VISIBILITY_PARTITIONS),
        "source_count": len(sources),
        "source_occurrence_count": len(source_rows),
        "duplicate_source_occurrences": sum(row["duplicate_count"] for row in sources),
        "sources": sources,
        "empirical_memory": empirical,
        "model_memory": models,
        "partition_contract": {
            "candidate_generation_reads": ["public_literature", "train_only_empirical"],
            "candidate_generation_excludes": ["challenge_result", "forward_observation"],
            "failed_results_retained": True,
            "serialized_model_reuse_requires_decision": True,
        },
    }
    path = ensure_dir(base / KNOWLEDGE_ROOT) / "index.json"
    write_json(path, payload)
    return KnowledgeBuildResult(index_path=path, payload=payload)


def scout_knowledge(
    iter_id: str,
    root: Path | None = None,
    *,
    fetcher: Callable[[str, int], bytes] | None = None,
) -> KnowledgeScoutResult:
    base = root or project_root()
    iteration_dir = base / ITERATION_ROOT / iter_id
    manifest_path = iteration_dir / "knowledge-scout-queries.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"knowledge scout manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    queries = manifest.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("knowledge scout manifest requires non-empty queries")
    max_results = int(manifest.get("max_results_per_query", 5))
    if max_results < 1 or max_results > 20:
        raise ValueError("max_results_per_query must be between 1 and 20")
    index = build_knowledge_index(base).payload
    known = {str(row["canonical_url"]): row for row in index["sources"]}
    fetch = fetcher or _fetch_arxiv
    candidates: dict[str, dict[str, Any]] = {}
    query_results = []
    for query_row in queries:
        if not isinstance(query_row, dict):
            raise ValueError("knowledge scout query rows must be objects")
        query_id = str(query_row.get("query_id") or "").strip()
        query = str(query_row.get("query") or "").strip()
        if not query_id or not query:
            raise ValueError("knowledge scout query requires query_id and query")
        raw = fetch(query, max_results)
        parsed = _parse_arxiv_feed(raw)
        query_results.append({"query_id": query_id, "query": query, "result_count": len(parsed)})
        for item in parsed:
            canonical = canonical_source_url(str(item["url"]))
            existing = known.get(canonical)
            candidate = candidates.setdefault(
                canonical,
                {
                    **item,
                    "canonical_url": canonical,
                    "query_ids": [],
                    "topics": [],
                    "knowledge_status": "already_known" if existing else "new_candidate",
                    "validation_status": "candidate_unvalidated",
                    "existing_locations": list(existing.get("locations", [])) if existing else [],
                },
            )
            candidate["query_ids"] = _unique_strings([*candidate["query_ids"], query_id])
            candidate["topics"] = _unique_strings(
                [*candidate["topics"], *[str(x) for x in query_row.get("topics", [])]]
            )
    rows = sorted(
        candidates.values(),
        key=lambda row: (str(row.get("published_at") or ""), str(row.get("title") or "")),
        reverse=True,
    )
    payload = {
        "schema_version": 1,
        "iter_id": iter_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "arxiv_official_api",
        "manifest_path": _relpath(manifest_path, base),
        "query_manifest_sha256": _sha256_file(manifest_path),
        "query_results": query_results,
        "candidate_count": len(rows),
        "new_candidate_count": sum(row["knowledge_status"] == "new_candidate" for row in rows),
        "already_known_count": sum(row["knowledge_status"] == "already_known" for row in rows),
        "candidates": rows,
        "contract": {
            "search_hit_is_validated_knowledge": False,
            "newest_is_effective": False,
            "effectiveness_requires_empirical_evidence": True,
        },
    }
    path = iteration_dir / "knowledge-scout.json"
    write_json(path, payload)
    return KnowledgeScoutResult(report_path=path, payload=payload)


def assess_iteration_knowledge(iter_id: str, root: Path | None = None) -> KnowledgeAssessmentResult:
    base = root or project_root()
    iteration_dir = base / ITERATION_ROOT / iter_id
    brief_path = iteration_dir / "external-brief.json"
    if not brief_path.exists():
        raise FileNotFoundError(f"external brief missing: {brief_path}")
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    index = build_knowledge_index(base).payload
    indexed = {str(row["canonical_url"]): row for row in index["sources"]}
    rows = []
    current_location = _relpath(brief_path, base)
    for source in brief.get("sources", []):
        canonical = canonical_source_url(str(source.get("url") or ""))
        indexed_row = indexed.get(canonical, {})
        prior_locations = [
            path for path in indexed_row.get("locations", []) if path != current_location
        ]
        status = "reused" if prior_locations else "new"
        if indexed_row.get("stale"):
            status = "refresh_required"
        rows.append(
            {
                "canonical_url": canonical,
                "status": status,
                "source_type": source.get("source_type"),
                "prior_locations": prior_locations,
                "claim_fingerprint": claim_fingerprint(str(source.get("core_claim") or "")),
            }
        )
    scout_path = iteration_dir / "knowledge-scout.json"
    scout = json.loads(scout_path.read_text(encoding="utf-8")) if scout_path.exists() else {}
    counts = {
        status: sum(row["status"] == status for row in rows)
        for status in {"reused", "new", "refresh_required"}
    }
    blocked = []
    if len(rows) < 8:
        blocked.append("knowledge_sources_lt_8")
    if not all(partition in index["visibility_partitions"] for partition in VISIBILITY_PARTITIONS):
        blocked.append("knowledge_visibility_partitions_incomplete")
    if counts["new"] + counts["refresh_required"] < 1:
        blocked.append("knowledge_no_new_or_refresh_evidence")
    if not scout:
        blocked.append("knowledge_scout_missing")
    model_reuse_path = iteration_dir / "model-reuse-decision.json"
    write_json(
        model_reuse_path,
        {
            "schema_version": 1,
            "iter_id": iter_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "default_policy": "no_warm_start_without_explicit_drift_or_data_reason",
            "decisions": _model_reuse_rows(iter_id, index["model_memory"]),
        },
    )
    payload = {
        "schema_version": 1,
        "iter_id": iter_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "blocked" if blocked else "ok",
        "blocked": blocked,
        "counts": counts,
        "source_assessment": rows,
        "scout_path": _relpath(scout_path, base) if scout else None,
        "scout_new_candidates": int(scout.get("new_candidate_count", 0)),
        "knowledge_index_path": _relpath(base / KNOWLEDGE_ROOT / "index.json", base),
        "visibility_contract": index["partition_contract"],
        "model_memory_count": len(index["model_memory"]),
        "model_reuse_decision_path": _relpath(model_reuse_path, base),
        "negative_empirical_memory_count": sum(
            bool(row.get("negative_result")) for row in index["empirical_memory"]
        ),
    }
    path = iteration_dir / "knowledge-assessment.json"
    write_json(path, payload)
    return KnowledgeAssessmentResult(report_path=path, payload=payload)


def _model_reuse_rows(iter_id: str, models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for model in models:
        status = str(model.get("status") or "unclassified").lower()
        source_iter = str(model.get("iteration_id") or "")
        if source_iter == iter_id:
            action = "freeze_current_diagnostic"
            reason = "Current-round model is retained for forward diagnostics, not promotion."
        elif "pass" in status and "fail" not in status:
            action = "reuse_as_reference_only"
            reason = "Prior validation is comparison evidence; its weights are not warm-started."
        else:
            action = "retain_negative_memory_do_not_promote"
            reason = "Unclassified or failed prior model remains visible to prevent repetition."
        rows.append(
            {
                "model_id": model.get("model_id"),
                "artifact_path": model.get("artifact_path"),
                "source_iteration": source_iter,
                "prior_status": model.get("status"),
                "action": action,
                "reason": reason,
            }
        )
    return rows


def _collect_sources(root: Path) -> list[dict[str, Any]]:
    rows = []
    cards_root = root / "reports/harness/source_cards"
    for path in sorted(cards_root.glob("*.jsonl")) if cards_root.exists() else []:
        for raw in _read_jsonl(path):
            try:
                card = SourceCard.model_validate(raw)
                status = check_source_card(card, root)
            except (ValueError, TypeError):
                continue
            canonical = canonical_source_url(card.source_url)
            if not canonical:
                continue
            rows.append(
                {
                    "canonical_url": canonical,
                    "source_type": card.source_type,
                    "accessed_at": card.accessed_at,
                    "claim": card.claim,
                    "stale": status.stale,
                    "location": _relpath(path, root),
                }
            )
    iterations_root = root / ITERATION_ROOT
    for path in sorted(iterations_root.glob("*/external-brief.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for source in payload.get("sources", []):
            if not isinstance(source, dict):
                continue
            canonical = canonical_source_url(str(source.get("url") or ""))
            if not canonical:
                continue
            accessed = _date_from_source(source)
            rows.append(
                {
                    "canonical_url": canonical,
                    "source_type": str(source.get("source_type") or "unverified"),
                    "accessed_at": accessed,
                    "claim": str(source.get("core_claim") or ""),
                    "stale": _source_is_stale(str(source.get("source_type") or ""), accessed),
                    "location": _relpath(path, root),
                }
            )
    return rows


def _collect_empirical_memory(root: Path) -> list[dict[str, Any]]:
    rows = []
    iterations_root = root / ITERATION_ROOT
    for path in sorted(iterations_root.glob("*/decision-record.md")):
        text = path.read_text(encoding="utf-8")
        decisions = re.findall(r"Decision:\s*([^\n]+)", text, flags=re.IGNORECASE)
        normalized = [item.strip().lower() for item in decisions]
        rows.append(
            {
                "iteration_id": path.parent.name,
                "artifact_path": _relpath(path, root),
                "visibility_partition": "train_only_empirical",
                "decisions": normalized,
                "negative_result": any(item in {"stop", "pivot"} for item in normalized)
                or "research_pass=false" in text.lower(),
                "artifact_sha256": _sha256_file(path),
            }
        )
    for path in sorted(iterations_root.glob("*/evaluation-report.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        has_challenge = any(key in payload for key in ("historical_challenge", "lockbox"))
        rows.append(
            {
                "iteration_id": path.parent.name,
                "artifact_path": _relpath(path, root),
                "visibility_partition": "challenge_result"
                if has_challenge
                else "train_only_empirical",
                "workflow_pass": payload.get("workflow_pass"),
                "research_pass": payload.get("research_pass"),
                "llm_contribution_pass": payload.get("llm_contribution_pass"),
                "paper_ready_pass": payload.get("paper_ready_pass"),
                "negative_result": payload.get("research_pass") is False,
                "artifact_sha256": _sha256_file(path),
            }
        )
    for path in sorted(iterations_root.glob("*/observation-state.json")):
        rows.append(
            {
                "iteration_id": path.parent.name,
                "artifact_path": _relpath(path, root),
                "visibility_partition": "forward_observation",
                "negative_result": False,
                "artifact_sha256": _sha256_file(path),
            }
        )
    return rows


def _collect_model_memory(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((root / ITERATION_ROOT).glob("*/models/*.joblib")):
        iteration_dir = path.parent.parent
        report = _find_model_report(iteration_dir, root, path)
        rows.append(
            {
                "model_id": _sha256_file(path),
                "artifact_path": _relpath(path, root),
                "iteration_id": iteration_dir.name,
                "size_bytes": path.stat().st_size,
                "status": report.get("status", "unclassified"),
                "role": report.get("role"),
                "feature_contract_sha256": report.get("feature_contract_sha256"),
                "training_data_sha256": report.get("training_data_sha256"),
                "prompt_hash": report.get("prompt_hash"),
                "reuse_policy": "frozen_inference_only_until_explicit_retrain_decision",
                "failure_reason": report.get("failure_reason"),
            }
        )
    return rows


def _find_model_report(iteration_dir: Path, root: Path, model_path: Path) -> dict[str, Any]:
    relative = _relpath(model_path, root)
    for report_path in sorted(iteration_dir.glob("*.json")):
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stack = [payload]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                candidate_path = value.get("model_path")
                if candidate_path and str(candidate_path) == relative:
                    return value
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
    return {}


def _fetch_arxiv(query: str, max_results: int) -> bytes:
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    request = urllib.request.Request(
        f"{ARXIV_API_URL}?{params}",
        headers={"User-Agent": "OpenComposerResearch/0.1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _parse_arxiv_feed(raw: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(raw)
    rows = []
    for entry in root.findall("atom:entry", ARXIV_NAMESPACE):
        url = _xml_text(entry, "atom:id")
        title = re.sub(r"\s+", " ", _xml_text(entry, "atom:title")).strip()
        summary = re.sub(r"\s+", " ", _xml_text(entry, "atom:summary")).strip()
        published = _xml_text(entry, "atom:published")
        authors = [
            _xml_text(author, "atom:name")
            for author in entry.findall("atom:author", ARXIV_NAMESPACE)
        ]
        if not url or not title:
            continue
        rows.append(
            {
                "url": url.replace("http://", "https://"),
                "title": title,
                "summary": summary,
                "published_at": published,
                "authors": authors,
                "source_type": "paper",
            }
        )
    return rows


def _xml_text(node: ET.Element, path: str) -> str:
    child = node.find(path, ARXIV_NAMESPACE)
    return str(child.text or "").strip() if child is not None else ""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _date_from_source(source: dict[str, Any]) -> str | None:
    raw = str(source.get("published_or_updated_at") or "")
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", raw)
    if match:
        return match.group(1)
    year = re.fullmatch(r"(20\d{2})", raw.strip())
    return f"{year.group(1)}-01-01" if year else None


def _source_is_stale(source_type: str, accessed_at: str | None) -> bool:
    if not accessed_at:
        return True
    try:
        age = (date.today() - date.fromisoformat(accessed_at)).days
    except ValueError:
        return True
    thresholds = {"paper": 730, "platform_docs": 30, "provider_official_docs": 60}
    return age > thresholds.get(source_type, 90)


def _unique_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    rows = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            rows.append(item)
    return rows


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
