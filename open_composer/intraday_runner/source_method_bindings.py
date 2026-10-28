"""Reuse the exact accepted pure quote parser and funded raw-share math.

Read once, hash those bytes, then compile those same bytes. No provider/client,
credential loading, opaque parent script execution, or consumed study rerun.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType

QUOTE_ROOT = "reports/research/program/dia-sequential-quote-validation-20261017"
CASH_PATH = (
    "reports/research/program/return-line-replenishment-20261016/"
    "dia-shareholder-account-20261017/accounting.py"
)
CODE = {
    "quotes": {
        "path": f"{QUOTE_ROOT}/quotes.py",
        "sha256": "34d0699c413abfde1967e8c4862f5b85c0c6561689a9f9a17281e4b4f4084c12",
    },
    "cash": {
        "path": CASH_PATH,
        "sha256": "4e8614da292ec9dc1b3e0fd7878b3600eaa13df787db975d11c77a7b44bd2807",
    },
}


def bound_bytes(root: Path, binding: dict) -> bytes:
    path = root / binding["path"]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != binding["sha256"]:
        raise ValueError("source-method reader hash changed")
    if "bytes" in binding and len(data) != binding["bytes"]:
        raise ValueError("source-method reader length changed")
    return data


def source_module(root: Path, name: str) -> ModuleType:
    binding = CODE[name]
    from open_composer.paper_runtime.source_loader import source_bytes

    data = source_bytes(root / binding["path"], root=root)
    if hashlib.sha256(data).hexdigest() != binding["sha256"]:
        raise ValueError("versioned accounting/quote source hash differs")
    key = f"_oc_bound_source_{name}_{binding['sha256'][:16]}"
    if key not in sys.modules:
        module = ModuleType(key)
        module.__file__ = str(root / binding["path"])
        sys.modules[key] = module
        try:
            exec(compile(data, module.__file__, "exec"), module.__dict__)
        except BaseException:
            del sys.modules[key]
            raise
    return sys.modules[key]


def quote_metadata(root: Path, bindings: dict) -> tuple[dict, dict]:
    """Bindings belong to the exact native entry; never trust an unbound pointer."""
    conditions = {
        tape: json.loads(bound_bytes(root, bindings[f"quote_conditions_{tape}"])) for tape in "ABC"
    }
    venues = json.loads(bound_bytes(root, bindings["exchanges"]))
    if any("R" not in conditions[tape] for tape in "ABC") or not venues:
        raise ValueError("required quote metadata absent")
    return conditions, venues
