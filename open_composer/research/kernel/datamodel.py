from __future__ import annotations

from dataclasses import asdict
from typing import Any

from open_composer.json_utils import json_safe_payload


class ResearchDataModel:
    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return json_safe_payload(asdict(self))
