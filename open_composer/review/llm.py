from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from open_composer.config import default_openai_model, ensure_dir
from open_composer.models.review_card import ReviewCard
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec
from open_composer.storage import write_json


def review_signal_with_llm(
    signal: Signal,
    spec: StrategySpec,
    root: Path,
    client: Any | None = None,
    model: str | None = None,
) -> ReviewCard | None:
    selected_model = model or spec.llm_review.model or default_openai_model()
    if client is None and not os.getenv("OPENAI_API_KEY"):
        return None
    client = client or _openai_client()
    prompt = _review_prompt(signal, spec)
    review = _call_structured_review(client, selected_model, prompt)
    if review is None:
        return None
    json_path = root / "reports" / "reviews" / f"{signal.id}.json"
    md_path = root / "reports" / "reviews" / f"{signal.id}.md"
    write_json(json_path, review)
    _write_review_markdown(md_path, review)
    return review


def _openai_client() -> Any:
    from openai import OpenAI

    return OpenAI()


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


def _review_prompt(signal: Signal, spec: StrategySpec) -> str:
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
        "## Invalidation",
        *[f"- {item}" for item in review.invalidation],
        "",
        f"Action suggestion: {review.action_suggestion}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
