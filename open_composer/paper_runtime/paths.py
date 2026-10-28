"""Paths shared by the existing six-policy service and its finite children."""

import os
from pathlib import Path

LEGACY = Path("reports/research/program/paper-launch-20min-20261021")
RUNTIME = Path("runtime/paper/six")
CONFIG = Path("config/paper/six-service.json")


def repo_root():
    return Path(os.environ.get("OPEN_COMPOSER_ROOT", Path(__file__).resolve().parents[2]))


def runtime_root(root=None):
    return Path(root) / RUNTIME if root is not None else repo_root() / RUNTIME
