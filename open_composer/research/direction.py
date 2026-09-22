"""Evidence-backed direction checks, before allocating research compute.

This verifies the receipt, not the truth of a trading thesis. Source prose is
never executed. Existing frozen v1/v2 briefs keep their original contracts.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

TEXT_FIELDS = (
    "objective",
    "target_regime_and_horizon",
    "existing_solution_comparison",
    "remaining_evidence_gap",
    "negative_experiments_checked",
    "cost_and_execution_assumptions",
    "stop_condition",
)
SOURCE_TYPES = {
    "broker_official_docs",
    "exchange_official_docs",
    "provider_official_docs",
    "regulatory_docs",
    "paper",
    "platform_docs",
    "industry_standard",
}


def requires_direction_review(iteration: Path, root: Path, external: dict[str, Any]) -> bool:
    """New/changed dossiers cannot opt out by changing their schema to v2.

    The installed migration inventory freezes existing artifacts, not caller
    supplied timestamps. Isolated fixture workspaces without that inventory
    use the explicit schema contract.
    """
    if int(external.get("schema_version") or 1) >= 3:
        return True
    policy = root / "config/research-direction-legacy.json"
    if not policy.exists():
        return False
    inventory = json.loads(policy.read_text(encoding="utf-8"))["frozen_iterations"]
    frozen = inventory.get(iteration.name)
    if not isinstance(frozen, dict):
        return True
    if not {"external-brief.json", "search-space.json"}.issubset(frozen):
        # An old directory/manifest alone is not a previously frozen dossier.
        return True
    for name, digest in frozen.items():
        path = iteration / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return True
    return not frozen


def direction_review_template(iter_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "iter_id": iter_id,
        "reviewed_at": None,
        "decision": "pending",
        **dict.fromkeys(TEXT_FIELDS, ""),
        "queries": [],
        "sources": [],
        "cheapest_decisive_test": {
            "action": "",
            "pass_condition": "",
            "falsification_condition": "",
            "max_compute_minutes": None,
        },
    }


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def _http_url(value: Any) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def validate_direction_review(
    path: Path,
    root: Path,
    *,
    expected_iter_id: str | None = None,
    now: datetime | None = None,
    check_freshness: bool = True,
) -> list[str]:
    """Return blockers, including changed/missing source snapshots.

    Freshness is an allocation check. A final report retains the historical
    receipt and must not fail merely because its research happened weeks ago.
    """
    moment = now or datetime.now(UTC)
    blocked: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["direction_review_missing_or_invalid"]
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return ["direction_review_schema_invalid"]
    if expected_iter_id is not None and payload.get("iter_id") != expected_iter_id:
        blocked.append("direction_review_iteration_mismatch")
    if payload.get("decision") != "proceed":
        blocked.append("direction_review_not_proceed")
    reviewed = _timestamp(payload.get("reviewed_at"))
    if reviewed is None or reviewed > moment + timedelta(minutes=5):
        blocked.append("direction_review_timestamp_invalid")
    elif check_freshness and moment - reviewed > timedelta(days=7):
        blocked.append("direction_review_stale")
    for key in TEXT_FIELDS:
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            blocked.append(f"direction_review_missing:{key}")
    test = payload.get("cheapest_decisive_test")
    if not isinstance(test, dict):
        blocked.append("direction_decisive_test_missing")
    else:
        for key in ("action", "pass_condition", "falsification_condition"):
            if not isinstance(test.get(key), str) or not test[key].strip():
                blocked.append(f"direction_decisive_test_missing:{key}")
        budget = test.get("max_compute_minutes")
        if type(budget) is not int or not 1 <= budget <= 1440:
            blocked.append("direction_decisive_test_budget_invalid")
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        blocked.append("direction_web_queries_missing")
        queries = []
    found_urls: set[str] = set()
    for index, query in enumerate(queries):
        if not isinstance(query, dict):
            blocked.append(f"direction_query_invalid:{index}")
            continue
        searched = _timestamp(query.get("searched_at"))
        urls = query.get("opened_urls")
        if (
            not str(query.get("query") or "").strip()
            or searched is None
            or (reviewed is not None and searched > reviewed)
            or not isinstance(urls, list)
            or not urls
            or not all(_http_url(url) for url in urls)
        ):
            blocked.append(f"direction_query_invalid:{index}")
        elif check_freshness and moment - searched > timedelta(days=7):
            blocked.append(f"direction_query_stale:{index}")
        else:
            found_urls.update(urls)
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        return blocked + ["direction_opened_sources_missing"]
    for index, source in enumerate(sources):
        prefix = f"direction_source_{index}"
        if not isinstance(source, dict):
            blocked.append(f"{prefix}:invalid")
            continue
        if source.get("url") not in found_urls:
            blocked.append(f"{prefix}:not_in_search_receipt")
        if source.get("source_type") not in SOURCE_TYPES:
            blocked.append(f"{prefix}:source_type_invalid")
        published = source.get("published_or_updated_at")
        if published != "unknown":
            try:
                date.fromisoformat(str(published)[:10])
            except ValueError:
                blocked.append(f"{prefix}:publication_date_invalid")
        for key in (
            "claim",
            "source_type",
            "published_or_updated_at",
            "market_and_period",
            "applicability",
            "limitations",
            "independent_replication",
        ):
            if not isinstance(source.get(key), str) or not source[key].strip():
                blocked.append(f"{prefix}:missing_{key}")
        fetched = _timestamp(source.get("fetched_at"))
        if fetched is None or (reviewed is not None and fetched > reviewed):
            blocked.append(f"{prefix}:fetched_at_invalid")
        elif check_freshness and moment - fetched > timedelta(days=30):
            blocked.append(f"{prefix}:refresh_required")
        try:
            snapshot = (root / str(source.get("snapshot_path") or "")).resolve()
            snapshot.relative_to(root.resolve())
            if not snapshot.is_file() or snapshot.stat().st_size > 5_000_000:
                raise ValueError("missing or oversized snapshot")
            body = snapshot.read_bytes()
            if not body or hashlib.sha256(body).hexdigest() != source.get("sha256"):
                raise ValueError("changed or empty snapshot")
        except (OSError, ValueError):
            blocked.append(f"{prefix}:snapshot_missing_or_hash_mismatch")
            continue
        try:
            cards_path = (root / str(source.get("source_card_path") or "")).resolve()
            cards_path.relative_to(root.resolve())
            if not cards_path.is_file() or cards_path.stat().st_size > 5_000_000:
                raise ValueError("missing or oversized source cards")
            cards = [
                json.loads(line) for line in cards_path.read_text().splitlines() if line.strip()
            ]
            matches = [
                card
                for card in cards
                if isinstance(card, dict) and card.get("claim_id") == source.get("claim_id")
            ]
            if len(matches) != 1:
                raise ValueError("source claim missing or ambiguous")
            card = matches[0]
            verified = (
                card.get("verification_status") == "source_verified"
                or card.get("status") == "verified"
            )
            if not verified or card.get("source_url") != source.get("url"):
                raise ValueError("source claim unverified or wrong URL")
            if card.get("claim") != source.get("claim"):
                raise ValueError("direction must use the canonical verified claim")
            fetched_receipt = _timestamp(card.get("fetched_at") or card.get("retrieved_at"))
            if fetched_receipt is None or fetched_receipt != fetched:
                raise ValueError("source refresh requires a matching fetch receipt")
            digest = card.get("source_sha256", card.get("sha256"))
            if digest != source.get("sha256"):
                raise ValueError("source claim snapshot differs")
            quote = card.get("quote")
            normalized = html.unescape(re.sub(r"<[^>]+>", " ", body.decode(errors="replace")))
            if (
                not isinstance(quote, str)
                or not quote.strip()
                or " ".join(quote.split()) not in " ".join(normalized.split())
            ):
                raise ValueError("source quotation absent from snapshot")
        except (OSError, ValueError):
            blocked.append(f"{prefix}:verified_claim_binding_invalid")
    return blocked
