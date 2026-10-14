"""Bounded synthetic adversarial checks of the unapplied candidate; no financial data."""

import importlib.util
import json
import os
import resource
import sys
import tempfile
from pathlib import Path

ROOT = Path.cwd()
P = Path(__file__).resolve().parent
C = P / "candidate-admission-v1"
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
resource.setrlimit(resource.RLIMIT_CPU, (40, 41))
assert len(os.sched_getaffinity(0)) == 1
assert __import__("shutil").disk_usage(ROOT).free > 9_533_075_101 + 2 * 1024**2

for name in ("market_component", "iteration_dossier"):
    qualified = f"open_composer.research.{name}"
    spec = importlib.util.spec_from_file_location(
        qualified, C / "candidate/open_composer/research" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)

spec = importlib.util.spec_from_file_location(
    "hf_review_candidate_fixture", C / "test_candidate_admission.py"
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
from open_composer.research.iteration_dossier import _campaign_contract_blockers  # noqa: E402
from open_composer.research.market_component import (  # noqa: E402
    fixed_seen_component_comparison_applies,
)

results = []
for mutation in (
    "baseline",
    "manifest_new_model_fits",
    "row_new_model_selection",
    "row_adaptive_selection",
):
    with tempfile.TemporaryDirectory(prefix="hf-revision-review-") as temp:
        root = Path(temp)
        fixture = fixtures.fixed_fixture(root)
        directory, external, search, manifest, definition = fixture
        if mutation == "manifest_new_model_fits":
            manifest["new_model_fits"] = 1
        elif mutation == "row_new_model_selection":
            manifest["candidates"][0]["new_model_selection"] = True
        elif mutation == "row_adaptive_selection":
            manifest["candidates"][0]["adaptive_selection"] = True
        if mutation != "baseline":
            # Only reseal ordinary writer-owned canonical metadata. Do not
            # modify any synthetic independent review or approved inventory.
            fixtures._write(directory / "candidate-manifest.json", manifest)
            search["candidate_manifest_sha256"] = fixtures._binding(
                root, directory / "candidate-manifest.json"
            )["sha256"]
            fixtures._write(directory / "search-space.json", search)
        applies = fixed_seen_component_comparison_applies(search, root)
        blockers = _campaign_contract_blockers(search, root, stage="pre-discovery")
        results.append(
            {
                "mutation": mutation,
                "fixed_component_applies": applies,
                "campaign_blockers": blockers,
                "independent_reviews_or_scope_changed": False,
                "approved_inventory_changed": False,
            }
        )

usage = resource.getrusage(resource.RUSAGE_SELF)
result = {
    "synthetic_only": True,
    "financial_runs": 0,
    "results": results,
    "CPU_seconds": usage.ru_utime + usage.ru_stime,
    "max_RSS_KiB": usage.ru_maxrss,
    "affinity": sorted(os.sched_getaffinity(0)),
}
(P / "independent-revision-decisive-probe-v1.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
