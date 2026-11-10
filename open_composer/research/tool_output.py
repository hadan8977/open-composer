"""Character-budgeted pages shared by local research tools (no token claims)."""

from __future__ import annotations


def page(text: str, *, offset: int = 0, budget: int = 2400) -> dict:
    if offset < 0 or not 128 <= budget <= 16000:
        raise ValueError("offset >= 0 and character budget 128..16000 required")
    end = min(len(text), offset + budget)
    return {
        "text": text[offset:end],
        "budget_unit": "characters",
        "budget": budget,
        "omitted": end < len(text),
        "next_offset": end if end < len(text) else None,
    }
