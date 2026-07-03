from __future__ import annotations

from typing import Any

import yaml

SAFE_YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def safe_load_yaml(stream: Any) -> Any:
    return yaml.load(stream, Loader=SAFE_YAML_LOADER)
