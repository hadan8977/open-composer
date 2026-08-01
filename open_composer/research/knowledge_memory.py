from __future__ import annotations

import hashlib
import ipaddress
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


@dataclass(frozen=True)
class KnowledgeContextResult:
    report_path: Path
    payload: dict[str, Any]


def canonical_source_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlsplit(raw)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    if scheme not in {"http", "https"} or not host:
        return ""
    if (
        parsed.username
        or parsed.password
        or "." not in host
        or host == "localhost"
        or host.endswith((".localhost", ".local", ".nip.io", ".sslip.io", ".xip.io"))
    ):
        return ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        legacy_ipv4_labels = host.split(".")
        if all(re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", label) for label in legacy_ipv4_labels):
            return ""
    else:
        if not address.is_global:
            return ""
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
    port = f":{parsed.port}" if parsed.port else ""
    return urllib.parse.urlunsplit((scheme, f"{host}{port}", path, query, ""))


def claim_fingerprint(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_knowledge_index(root: Path | None = None) -> KnowledgeBuildResult:
    base = root or project_root()
    source_rows = _collect_sources(base)
    sources = _group_source_rows(source_rows)
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


def _group_source_rows(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                "verification_statuses": _unique_strings(
                    str(row.get("verification_status") or "legacy") for row in rows
                ),
                "first_seen": accessed[0] if accessed else None,
                "last_verified": accessed[-1] if accessed else None,
                "occurrence_count": len(rows),
                "duplicate_count": max(0, len(rows) - 1),
                "claims": claims,
                "claim_fingerprints": [claim_fingerprint(claim) for claim in claims],
                "topics": _unique_strings(topic for row in rows for topic in row.get("topics", [])),
                "locations": locations,
                "stale": bool(stale_rows) and len(stale_rows) == len(rows),
            }
        )

    return sources


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
    queries = manifest.get("queries", [])
    curated = manifest.get("curated_candidates", [])
    if not isinstance(queries, list):
        raise ValueError("knowledge scout queries must be a list")
    if not isinstance(curated, list):
        raise ValueError("knowledge scout curated_candidates must be a list")
    if not queries and not curated:
        raise ValueError("knowledge scout manifest requires queries or curated_candidates")
    max_results = int(manifest.get("max_results_per_query", 5))
    if max_results < 1 or max_results > 20:
        raise ValueError("max_results_per_query must be between 1 and 20")
    build_knowledge_index(base)
    brief_path = iteration_dir / "external-brief.json"
    brief = json.loads(brief_path.read_text(encoding="utf-8")) if brief_path.exists() else {}
    current_locations = _current_source_card_locations(brief, iter_id, base)
    current_locations.add(_relpath(brief_path, base))
    prior_source_rows = [
        row
        for row in _collect_sources(base)
        if str(row.get("location") or "") not in current_locations
    ]
    known = {str(row["canonical_url"]): row for row in _group_source_rows(prior_source_rows)}
    baseline_payload = {
        "schema_version": 1,
        "iter_id": iter_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "excluded_current_locations": sorted(current_locations),
        "source_count": len(known),
        "sources": [
            {
                "source_id": row["source_id"],
                "canonical_url": canonical_url,
                "claim_fingerprints": row.get("claim_fingerprints", []),
                "locations": row.get("locations", []),
            }
            for canonical_url, row in sorted(known.items())
        ],
    }
    baseline_path = iteration_dir / "knowledge-baseline.json"
    write_json(baseline_path, baseline_payload)
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
                    "validation_status": (
                        "source_verified_prior"
                        if existing
                        and "source_verified" in existing.get("verification_statuses", [])
                        else "candidate_unvalidated"
                    ),
                    "existing_locations": list(existing.get("locations", [])) if existing else [],
                },
            )
            candidate["query_ids"] = _unique_strings([*candidate["query_ids"], query_id])
            candidate["topics"] = _unique_strings(
                [*candidate["topics"], *[str(x) for x in query_row.get("topics", [])]]
            )
    for item in curated:
        if not isinstance(item, dict):
            raise ValueError("knowledge scout curated candidate rows must be objects")
        canonical = canonical_source_url(str(item.get("url") or ""))
        title = str(item.get("title") or "").strip()
        if not canonical or not title:
            raise ValueError("knowledge scout curated candidate requires an http(s) URL and title")
        existing = known.get(canonical)
        candidate = candidates.setdefault(
            canonical,
            {
                "url": str(item["url"]),
                "title": title,
                "summary": str(item.get("summary") or "").strip(),
                "published_at": str(item.get("published_at") or "").strip(),
                "authors": [str(value) for value in item.get("authors", [])],
                "source_type": str(item.get("source_type") or "unverified"),
                "canonical_url": canonical,
                "query_ids": [],
                "topics": [],
                "knowledge_status": "already_known" if existing else "new_candidate",
                "validation_status": (
                    "source_verified_prior"
                    if existing and "source_verified" in existing.get("verification_statuses", [])
                    else "candidate_unvalidated"
                ),
                "existing_locations": list(existing.get("locations", [])) if existing else [],
            },
        )
        candidate["query_ids"] = _unique_strings(
            [*candidate["query_ids"], str(item.get("discovery_id") or "curated_web")]
        )
        candidate["topics"] = _unique_strings(
            [*candidate["topics"], *[str(value) for value in item.get("topics", [])]]
        )
    rows = sorted(
        candidates.values(),
        key=lambda row: (str(row.get("published_at") or ""), str(row.get("title") or "")),
        reverse=True,
    )
    payload = {
        "schema_version": 2,
        "iter_id": iter_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "external_brief_path": _relpath(brief_path, base),
        "external_brief_sha256": _sha256_file(brief_path),
        "provider": "arxiv_official_api+curated_web_manifest" if curated else "arxiv_official_api",
        "manifest_path": _relpath(manifest_path, base),
        "query_manifest_sha256": _sha256_file(manifest_path),
        "baseline_path": _relpath(baseline_path, base),
        "baseline_sha256": _sha256_file(baseline_path),
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


def build_iteration_knowledge_context(
    iter_id: str,
    root: Path | None = None,
    *,
    max_sources: int = 24,
) -> KnowledgeContextResult:
    base = root or project_root()
    iteration_dir = base / ITERATION_ROOT / iter_id
    brief_path = iteration_dir / "external-brief.json"
    manifest_path = iteration_dir / "knowledge-scout-queries.json"
    if not brief_path.exists():
        raise FileNotFoundError(f"external brief missing: {brief_path}")
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    )
    topics = _unique_strings(
        [
            *[str(value) for value in brief.get("topic_coverage", [])],
            *[
                str(value)
                for row in manifest.get("queries", [])
                if isinstance(row, dict)
                for value in row.get("topics", [])
            ],
            *[
                str(value)
                for row in manifest.get("curated_candidates", [])
                if isinstance(row, dict)
                for value in row.get("topics", [])
            ],
        ]
    )
    topic_tokens = _search_tokens(" ".join(topics))
    index = build_knowledge_index(base).payload
    source_rows = []
    for source in index["sources"]:
        searchable = " ".join(
            [
                str(source.get("canonical_url") or ""),
                *[str(value) for value in source.get("topics", [])],
                *[str(value) for value in source.get("claims", [])],
            ]
        )
        overlap = sorted(topic_tokens & _search_tokens(searchable))
        if overlap:
            source_rows.append({**source, "matched_tokens": overlap, "match_score": len(overlap)})
    source_rows.sort(
        key=lambda row: (int(row["match_score"]), not bool(row.get("stale"))),
        reverse=True,
    )
    empirical = [
        row
        for row in index["empirical_memory"]
        if row.get("visibility_partition") == "train_only_empirical"
        and (
            _search_tokens(str(row.get("iteration_id") or "")) & topic_tokens
            or "mom" in str(row.get("iteration_id") or "").lower()
        )
    ]
    models = []
    for row in index["model_memory"]:
        iteration_id = str(row.get("iteration_id") or "")
        if not (
            _search_tokens(" ".join([iteration_id, str(row.get("role") or "")])) & topic_tokens
            or "mom" in iteration_id.lower()
        ):
            continue
        models.append(
            {
                key: row.get(key)
                for key in [
                    "model_id",
                    "iteration_id",
                    "size_bytes",
                    "role",
                    "feature_contract_sha256",
                    "training_data_sha256",
                    "prompt_hash",
                    "reuse_policy",
                ]
            }
        )
    restricted_empirical = [
        row
        for row in index["empirical_memory"]
        if row.get("visibility_partition") in {"challenge_result", "forward_observation"}
    ]
    payload = {
        "schema_version": 1,
        "iter_id": iter_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "topics": topics,
        "matched_sources": source_rows[:max_sources],
        "negative_empirical_memory": [row for row in empirical if row.get("negative_result")],
        "model_memory": models,
        "restricted_memory_summary": {
            "challenge_result_count": len(
                {
                    str(row.get("iteration_id") or "")
                    for row in restricted_empirical
                    if row.get("visibility_partition") == "challenge_result"
                }
            ),
            "forward_observation_count": len(
                {
                    str(row.get("iteration_id") or "")
                    for row in restricted_empirical
                    if row.get("visibility_partition") == "forward_observation"
                }
            ),
            "outcome_details_exposed": False,
        },
        "visibility_contract": index["partition_contract"],
        "contract": {
            "context_is_research_input_not_alpha": True,
            "challenge_and_forward_results_excluded_from_candidate_generation": True,
            "restricted_model_outcomes_redacted": True,
            "stale_sources_require_refresh": True,
        },
    }
    path = iteration_dir / "knowledge-context.json"
    write_json(path, payload)
    return KnowledgeContextResult(report_path=path, payload=payload)


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
    current_source_locations = _current_source_card_locations(brief, iter_id, base)
    for source in brief.get("sources", []):
        canonical = canonical_source_url(str(source.get("url") or ""))
        indexed_row = indexed.get(canonical, {})
        prior_locations = [
            path
            for path in indexed_row.get("locations", [])
            if path != current_location and path not in current_source_locations
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
    scout = _load_valid_scout(scout_path, iteration_dir, iter_id, base)
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
    context = build_iteration_knowledge_context(iter_id, base)
    payload = {
        "schema_version": 1,
        "iter_id": iter_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "external_brief_path": _relpath(brief_path, base),
        "external_brief_sha256": _sha256_file(brief_path),
        "status": "blocked" if blocked else "ok",
        "blocked": blocked,
        "counts": counts,
        "source_assessment": rows,
        "scout_path": _relpath(scout_path, base) if scout else None,
        "scout_new_candidates": int(scout.get("new_candidate_count", 0)),
        "knowledge_index_path": _relpath(base / KNOWLEDGE_ROOT / "index.json", base),
        "knowledge_context_path": _relpath(context.report_path, base),
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
                    "topics": list(card.applies_to),
                    "verification_status": card.verification_status,
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
        brief_topics = [str(value) for value in payload.get("topic_coverage", [])]
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
                    "topics": _unique_strings(
                        [*brief_topics, *[str(value) for value in source.get("topics", [])]]
                    ),
                    "verification_status": "legacy_external_brief",
                    "stale": _source_is_stale(str(source.get("source_type") or ""), accessed),
                    "location": _relpath(path, root),
                }
            )
    return rows


def _current_source_card_locations(brief: dict[str, Any], iter_id: str, root: Path) -> set[str]:
    if int(brief.get("schema_version") or 1) < 2:
        return set()
    locations: set[str] = set()
    cards_by_id: dict[str, SourceCard] = {}
    allowed_root = (root / "reports/harness/source_cards").resolve()
    for raw in brief.get("current_source_card_paths", []):
        path = (root / str(raw)).resolve()
        try:
            path.relative_to(allowed_root)
        except ValueError as exc:
            raise ValueError(f"current source card is outside source_cards: {raw}") from exc
        if path.suffix != ".jsonl" or not path.exists():
            raise ValueError(f"current source card missing or invalid: {raw}")
        rows = _read_jsonl(path)
        cards = [SourceCard.model_validate(row) for row in rows]
        if not cards or any(card.iteration_id != iter_id for card in cards):
            raise ValueError(f"current source card iteration mismatch: {raw}")
        for card in cards:
            if (
                card.verification_status != "source_verified"
                or not card.verified_at
                or not card.verification_method
            ):
                raise ValueError(f"current source card is not source_verified: {card.claim_id}")
            if card.claim_id in cards_by_id:
                raise ValueError(f"duplicate current source claim_id: {card.claim_id}")
            cards_by_id[card.claim_id] = card
        locations.add(_relpath(path, root))
    bindings = brief.get("source_evidence_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("schema v2 external brief requires source_evidence_bindings")
    bindings_by_url: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    binding_keys: set[tuple[str, str]] = set()
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            raise ValueError("source evidence bindings must be objects")
        canonical = canonical_source_url(str(binding.get("canonical_url") or ""))
        claim_id = str(binding.get("source_card_claim_id") or "")
        key = (canonical, claim_id)
        if not canonical or not claim_id or key in binding_keys:
            raise ValueError("source evidence binding has invalid or duplicate claim key")
        binding_keys.add(key)
        bindings_by_url.setdefault(canonical, []).append((index, binding))
    consumed_bindings: set[int] = set()
    for source in brief.get("sources", []):
        canonical = canonical_source_url(str(source.get("url") or ""))
        candidates = bindings_by_url.get(canonical, [])
        if not candidates:
            raise ValueError(f"external brief source is not evidence-bound: {canonical}")
        source_fingerprint = claim_fingerprint(str(source.get("core_claim") or ""))
        matches = [
            (index, binding)
            for index, binding in candidates
            if str(binding.get("brief_claim_fingerprint") or "") == source_fingerprint
            and index not in consumed_bindings
        ]
        if len(matches) != 1:
            raise ValueError(f"source evidence binding brief claim mismatch: {canonical}")
        binding_index, binding = matches[0]
        consumed_bindings.add(binding_index)
        claim_id = str(binding.get("source_card_claim_id") or "")
        card = cards_by_id.get(claim_id)
        if card is None or canonical_source_url(card.source_url) != canonical:
            raise ValueError(f"source evidence binding card mismatch: {canonical}")
        if str(binding.get("claim_fingerprint") or "") != claim_fingerprint(card.claim):
            raise ValueError(f"source evidence binding claim mismatch: {canonical}")
        if str(binding.get("brief_claim_fingerprint") or "") != source_fingerprint:
            raise ValueError(f"source evidence binding brief claim mismatch: {canonical}")
    if len(consumed_bindings) != len(bindings):
        raise ValueError("source evidence bindings do not match external brief sources")
    return locations


def _load_valid_scout(
    scout_path: Path,
    iteration_dir: Path,
    iter_id: str,
    root: Path,
) -> dict[str, Any]:
    if not scout_path.exists():
        return {}
    scout = json.loads(scout_path.read_text(encoding="utf-8"))
    manifest_path = iteration_dir / "knowledge-scout-queries.json"
    baseline_path = iteration_dir / "knowledge-baseline.json"
    schema_version = scout.get("schema_version")
    if schema_version not in {1, 2} or scout.get("iter_id") != iter_id:
        raise ValueError("knowledge scout identity mismatch")
    if schema_version == 2:
        brief_path = iteration_dir / "external-brief.json"
        if scout.get("external_brief_path") != _relpath(brief_path, root):
            raise ValueError("knowledge scout external brief path mismatch")
        if not brief_path.exists() or scout.get("external_brief_sha256") != _sha256_file(
            brief_path
        ):
            raise ValueError("knowledge scout external brief hash mismatch")
    if not manifest_path.exists() or scout.get("query_manifest_sha256") != _sha256_file(
        manifest_path
    ):
        raise ValueError("knowledge scout manifest hash mismatch")
    if not baseline_path.exists() or scout.get("baseline_sha256") != _sha256_file(baseline_path):
        raise ValueError("knowledge scout baseline hash mismatch")
    candidates = scout.get("candidates")
    if not isinstance(candidates, list) or int(scout.get("candidate_count", -1)) != len(candidates):
        raise ValueError("knowledge scout candidate count mismatch")
    for candidate in candidates:
        if not isinstance(candidate, dict) or not canonical_source_url(
            str(candidate.get("canonical_url") or "")
        ):
            raise ValueError("knowledge scout candidate is invalid")
        if candidate.get("validation_status") not in {
            "candidate_unvalidated",
            "source_verified_prior",
        }:
            raise ValueError("knowledge scout candidate validation status is invalid")
    return scout


def _collect_empirical_memory(root: Path) -> list[dict[str, Any]]:
    rows = []
    iterations_root = root / ITERATION_ROOT
    for path in sorted(iterations_root.glob("*/decision-record.md")):
        text = path.read_text(encoding="utf-8")
        decisions = re.findall(r"Decision:\s*([^\n]+)", text, flags=re.IGNORECASE)
        normalized = [item.strip().lower() for item in decisions]
        partition = _iteration_decision_partition(path.parent, text)
        rows.append(
            {
                "iteration_id": path.parent.name,
                "artifact_path": _relpath(path, root),
                "visibility_partition": partition,
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
        has_challenge = _contains_key(payload, {"historical_challenge", "lockbox"})
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


def _iteration_decision_partition(iteration_dir: Path, text: str) -> str:
    provenance_path = iteration_dir / "memory-provenance.json"
    declared_partition = ""
    if provenance_path.exists():
        try:
            payload = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        declared_partition = str(payload.get("decision_record_visibility_partition") or "")
    if (iteration_dir / "observation-state.json").exists():
        return "forward_observation"
    for report_path in [
        iteration_dir / "evaluation-report.json",
        iteration_dir / "model-comparison.json",
    ]:
        if not report_path.exists():
            continue
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _contains_key(payload, {"historical_challenge", "lockbox"}):
            return "challenge_result"
    lowered = text.lower()
    if "challenge" in lowered or "lockbox" in lowered:
        return "challenge_result"
    if "forward observation" in lowered or "forward-only" in lowered:
        return "forward_observation"
    if declared_partition in {"challenge_result", "forward_observation"}:
        return declared_partition
    return "train_only_empirical"


def _contains_key(value: Any, keys: set[str]) -> bool:
    if isinstance(value, dict):
        normalized = {str(key).lower() for key in value}
        if any(any(marker in key for marker in keys) for key in normalized):
            return True
        return any(_contains_key(item, keys) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, keys) for item in value)
    return False


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


def _search_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", value.lower())
        if token not in {"and", "for", "from", "the", "with"}
    }


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
