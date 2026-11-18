"""Reuse the accepted pure quote parser and funded raw-share math.

The versioned copies run under their historical paths (see paper_runtime's
source_loader). No provider/client, credential loading or study rerun.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import ModuleType

CODE = {
    "quotes": "reports/research/program/dia-sequential-quote-validation-20261017/quotes.py",
    "cash": (
        "reports/research/program/return-line-replenishment-20261016/"
        "dia-shareholder-account-20261017/accounting.py"
    ),
}


def bound_bytes(root: Path, binding: dict) -> bytes:
    """Read a recorded evidence file; its recorded sha256 must still match."""
    path = root / binding["path"]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != binding["sha256"]:
        raise ValueError("source-method reader hash changed")
    if "bytes" in binding and len(data) != binding["bytes"]:
        raise ValueError("source-method reader length changed")
    return data


def source_module(root: Path, name: str) -> ModuleType:
    from open_composer.paper_runtime.source_loader import source_bytes

    key = f"_oc_bound_source_{name}"
    if key not in sys.modules:
        path = root / CODE[name]
        module = ModuleType(key)
        module.__file__ = str(path)
        sys.modules[key] = module
        try:
            exec(compile(source_bytes(path, root=root), module.__file__, "exec"), module.__dict__)
        except BaseException:
            del sys.modules[key]
            raise
    return sys.modules[key]
