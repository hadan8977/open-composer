from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from open_composer.config import project_root
from open_composer.models.capability import Capability, CapabilityRegistry
from open_composer.yaml_utils import safe_load_yaml


def load_registry(root: Path | None = None) -> CapabilityRegistry:
    base = root or project_root()
    path = base / "capabilities" / "registry.yaml"
    path = path.resolve()
    stat = path.stat()
    return _load_registry_cached(str(path), stat.st_mtime_ns, stat.st_size).model_copy(deep=True)


@lru_cache(maxsize=16)
def _load_registry_cached(path_value: str, mtime_ns: int, size: int) -> CapabilityRegistry:
    del mtime_ns, size
    path = Path(path_value)
    with path.open("r", encoding="utf-8") as handle:
        raw = safe_load_yaml(handle)
    return CapabilityRegistry.model_validate(raw)


def get_capability(capability_id: str, root: Path | None = None) -> Capability:
    registry = load_registry(root)
    for capability in registry.capabilities:
        if capability.id == capability_id:
            return capability
    raise KeyError(f"unknown capability: {capability_id}")


def find_capabilities_by_kind(kind: str, root: Path | None = None) -> list[Capability]:
    registry = load_registry(root)
    return [capability for capability in registry.capabilities if capability.kind == kind]
