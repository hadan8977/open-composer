"""Isolated candidate module overlay, never writing the shared CLI or its tests."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path.cwd()
C = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
for name in ("market_component", "iteration_dossier"):
    qualified = f"open_composer.research.{name}"
    path = C / "candidate/open_composer/research" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(qualified, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
raise SystemExit(pytest.main(sys.argv[1:]))
