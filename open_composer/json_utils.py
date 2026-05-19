from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any


def json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def json_safe_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(json_safe_value(key)): json_safe_payload(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe_payload(item) for item in value]
    if isinstance(value, set):
        return json_safe_sorted_values(value)
    return json_safe_value(value)


def json_safe_sorted_values(values: set[Any]) -> list[Any]:
    return sorted(
        (json_safe_value(value) for value in values),
        key=lambda value: str(value),
    )
