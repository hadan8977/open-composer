from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from open_composer.config import default_openai_model, ensure_dir, openai_api_key, openai_base_url
from open_composer.models.event import SignalContext
from open_composer.models.review_card import ReviewCard
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec
from open_composer.storage import write_json

ReviewStatus = Literal[
    "written",
    "missing_api_key",
    "refused",
    "auth_failed",
    "rate_limited",
    "timeout",
    "api_error",
]


@dataclass(frozen=True)
class ReviewResult:
    review: ReviewCard | None
    status: ReviewStatus
    message: str


def review_signal_with_llm(
    signal: Signal,
    spec: StrategySpec,
    root: Path,
    client: Any | None = None,
    model: str | None = None,
    context: SignalContext | None = None,
) -> ReviewCard | None:
    return review_signal_with_status(signal, spec, root, client, model, context).review


def review_signal_with_status(
    signal: Signal,
    spec: StrategySpec,
    root: Path,
    client: Any | None = None,
    model: str | None = None,
    context: SignalContext | None = None,
) -> ReviewResult:
    selected_model = model or spec.llm_review.model or default_openai_model()
    if client is None and not openai_api_key():
        return ReviewResult(None, "missing_api_key", "OPENAI_API_KEY is not set")
    client = client or _openai_client()
    if context is None:
        try:
            from open_composer.context import build_signal_context

            context = build_signal_context(signal.id, root)
        except Exception:
            context = None
    prompt = _review_prompt(signal, spec, context)
    try:
        review = _call_structured_review(client, selected_model, prompt)
    except Exception as exc:
        status, message = _classify_review_error(exc)
        return ReviewResult(None, status, message)
    if review is None:
        return ReviewResult(
            None,
            "refused",
            "model refused or returned no schema-valid review card",
        )
    json_path = root / "reports" / "reviews" / f"{signal.id}.json"
    md_path = root / "reports" / "reviews" / f"{signal.id}.md"
    write_json(json_path, review)
    _write_review_markdown(md_path, review)
    return ReviewResult(review, "written", f"reports/reviews/{signal.id}.json")


def _classify_review_error(exc: Exception) -> tuple[ReviewStatus, str]:
    name = type(exc).__name__
    status_code = getattr(exc, "status_code", None)
    lowered = name.lower()
    if status_code == 401 or "auth" in lowered:
        return (
            "auth_failed",
            "OpenAI authentication failed; check OPENAI_API_KEY and OPENAI_BASE_URL",
        )
    if status_code == 429 or "ratelimit" in lowered or "rate_limit" in lowered:
        return "rate_limited", "OpenAI request was rate limited"
    if "timeout" in lowered:
        return "timeout", "OpenAI request timed out"
    suffix = f" status={status_code}" if status_code else f" error={name}"
    return "api_error", f"OpenAI review request failed;{suffix}"


def _openai_client() -> Any:
    from openai import OpenAI

    return OpenAI(api_key=openai_api_key(), base_url=openai_base_url())


def _call_structured_review(client: Any, model: str, prompt: str) -> ReviewCard | None:
    messages = [
        {
            "role": "system",
            "content": (
                "You review candidate trading signals for a personal research workflow. "
                "You do not provide financial advice or automatic real-money trade instructions. "
                "Return a schema-valid review card."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    try:
        response = client.responses.parse(model=model, input=messages, text_format=ReviewCard)
        return _extract_parsed_review(response)
    except TypeError:
        response = client.responses.create(
            model=model,
            input=messages,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "review_card",
                    "strict": True,
                    "schema": ReviewCard.model_json_schema(),
                }
            },
        )
        return ReviewCard.model_validate_json(response.output_text)


def _extract_parsed_review(response: Any) -> ReviewCard | None:
    for output in getattr(response, "output", []):
        if getattr(output, "type", None) != "message":
            continue
        for item in getattr(output, "content", []):
            if getattr(item, "type", None) == "refusal":
                return None
            parsed = getattr(item, "parsed", None)
            if isinstance(parsed, ReviewCard):
                return parsed
            if isinstance(parsed, dict):
                return ReviewCard.model_validate(parsed)
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, ReviewCard):
        return parsed
    if isinstance(parsed, dict):
        return ReviewCard.model_validate(parsed)
    return None


def _review_prompt(signal: Signal, spec: StrategySpec, context: SignalContext | None) -> str:
    payload = {
        "signal": signal.model_dump(mode="json"),
        "strategy": {
            "name": spec.name,
            "description": spec.description,
            "entry": spec.entry.model_dump(),
            "exit": spec.exit.model_dump(),
            "risk": spec.risk.model_dump(),
            "execution": spec.execution.model_dump(),
            "notes": spec.notes.model_dump(),
        },
    }
    if context is not None:
        payload["context"] = context.model_dump(mode="json")
    return json.dumps(payload, indent=2, sort_keys=True)


def _write_review_markdown(path: Path, review: ReviewCard) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Review Card: {review.signal_id}",
        "",
        f"- Verdict: `{review.verdict}`",
        f"- Confidence: {review.confidence:.2f}",
        f"- Catalyst: {review.catalyst or 'n/a'}",
        "",
        "## Evidence",
        *[f"- {item}" for item in review.evidence],
        "",
        "## Risks",
        *[f"- {item}" for item in review.risks],
        "",
        f"Primary risk source: {review.primary_risk_source or 'n/a'}",
        "",
        "## If Wrong",
        *[f"- {item}" for item in review.if_wrong_top_3_reasons],
        "",
        "## Invalidation",
        *[f"- {item}" for item in review.invalidation],
        "",
        f"Action suggestion: {review.action_suggestion}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
