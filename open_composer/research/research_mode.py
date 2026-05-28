from __future__ import annotations

from open_composer.models.experiment import ResearchMode


def normalize_research_mode(value: str | None) -> ResearchMode:
    if value is None or value == "":
        return "audited"
    if value not in {"playground", "audited"}:
        msg = "--research-mode must be one of: playground, audited"
        raise ValueError(msg)
    return value  # type: ignore[return-value]
