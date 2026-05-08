from __future__ import annotations

from pathlib import Path

import yaml

from open_composer.config import project_root
from open_composer.models.capability import Capability, CapabilityRegistry


def load_registry(root: Path | None = None) -> CapabilityRegistry:
    base = root or project_root()
    path = base / "capabilities" / "registry.yaml"
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return CapabilityRegistry.model_validate(raw)


def get_capability(capability_id: str, root: Path | None = None) -> Capability:
    registry = load_registry(root)
    for capability in registry.capabilities:
        if capability.id == capability_id:
            return capability
    raise KeyError(f"unknown capability: {capability_id}")
