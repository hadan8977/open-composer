"""CLI1 affected cases only; reuse93af baseline/three failures and old guard evidence."""

import ast
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

P = Path(__file__).resolve().parent.parent
C = P / "candidate-admission-v1"
sys.path.insert(0, str(C))
from test_candidate_admission import _binding, _write, fixed_fixture, reseal  # noqa: E402

from open_composer.research.iteration_dossier import _campaign_contract_blockers  # noqa: E402
from open_composer.research.market_component import (  # noqa: E402
    _canonical_fixed_comparison_matches,
    fixed_seen_component_comparison_applies,
)

WARNING = "warning:reviewed_fixed_seen_component_campaign_not_applicable"


def reseal_writer(root, directory, search, manifest):
    _write(directory / "candidate-manifest.json", manifest)
    search["candidate_manifest_sha256"] = _binding(root, directory / "candidate-manifest.json")[
        "sha256"
    ]
    _write(directory / "search-space.json", search)


def assert_outcome(root, search, expected):
    assert fixed_seen_component_comparison_applies(search, root) is expected
    blocked = _campaign_contract_blockers(search, root, stage="pre-discovery")
    if expected:
        assert blocked == [WARNING]
    else:
        assert "campaign_contract_required_for_new_iteration" in blocked and WARNING not in blocked


@pytest.mark.parametrize(
    "mutation",
    ["baseline", "manifest_new_model_fits", "row_new_model_selection", "row_adaptive_selection"],
)
def test_reviewer_exact_baseline_and_three_counterexamples(tmp_path, mutation):
    directory, _, search, manifest, _ = fixed_fixture(tmp_path)
    signed = {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in [
            "fixed-comparison.json",
            "implementation-review.json",
            "scientific-plan.json",
            "independent-review.json",
            "approved-inventory.json",
        ]
    }
    if mutation == "manifest_new_model_fits":
        manifest["new_model_fits"] = 1
    elif mutation == "row_new_model_selection":
        manifest["candidates"][0]["new_model_selection"] = True
    elif mutation == "row_adaptive_selection":
        manifest["candidates"][0]["adaptive_selection"] = True
    reseal_writer(tmp_path, directory, search, manifest)
    assert_outcome(tmp_path, search, mutation == "baseline")
    assert all(
        hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
        for name, digest in signed.items()
    )


def test_operation_types_and_every_candidate_include_last_row(tmp_path):
    directory, _, search, manifest, _ = fixed_fixture(tmp_path)
    # A single fixture suffices. Only ordinary canonical writer hashes change.
    for value, expected in [
        (None, True),
        (False, True),
        (0, True),
        (1, False),
        (True, False),
        ("0", False),
        ("false", False),
        (0.0, False),
        ([], False),
    ]:
        manifest["new_model_fits"] = value
        manifest["candidates"][-1]["adaptive_selection"] = value
        reseal_writer(tmp_path, directory, search, manifest)
        assert_outcome(tmp_path, search, expected)


@pytest.mark.parametrize("position", ["manifest", "last_row"])
def test_unapproved_scientific_key_rejected_even_if_signed_as_wiring(tmp_path, position):
    fixture = fixed_fixture(tmp_path)
    directory, _, search, manifest, _ = fixture
    scope = json.loads((directory / "fixed-comparison.json").read_text())
    if position == "manifest":
        manifest["new_training_recipe"] = {"steps": 1}
        scope["canonical_wiring"] = {"manifest": {"new_training_recipe": {"steps": 1}}}
    else:
        row = manifest["candidates"][-1]
        row["new_training_recipe"] = {"steps": 1}
        scope["canonical_wiring"] = {
            "candidates": {row["candidate_id"]: {"new_training_recipe": {"steps": 1}}}
        }
    _write(directory / "fixed-comparison.json", scope)
    reseal(tmp_path, fixture)  # Signed metadata cannot approve a new scientific key.
    assert_outcome(tmp_path, search, False)


def test_approved_scientific_value_cannot_change_type(tmp_path):
    directory, _, search, manifest, _ = fixed_fixture(tmp_path)
    manifest["candidates"][-1]["promotion_eligible"] = 0  # Python False==0 is insufficient.
    reseal_writer(tmp_path, directory, search, manifest)
    assert_outcome(tmp_path, search, False)


def test_added_known_wiring_requires_exact_independent_scope_projection(tmp_path):
    fixture = fixed_fixture(tmp_path)
    directory, _, search, manifest, _ = fixture
    row = manifest["candidates"][-1]
    row["scale_curve_point"] = False
    reseal_writer(tmp_path, directory, search, manifest)
    assert_outcome(tmp_path, search, False)
    scope = json.loads((directory / "fixed-comparison.json").read_text())
    scope["canonical_wiring"] = {"candidates": {row["candidate_id"]: {"scale_curve_point": False}}}
    _write(directory / "fixed-comparison.json", scope)
    reseal(tmp_path, fixture)
    assert_outcome(tmp_path, search, True)
    row["scale_curve_point"] = True
    reseal_writer(tmp_path, directory, search, manifest)
    assert_outcome(tmp_path, search, False)


def test_actual_fixed_inventory_rendering_matches_without_claiming_native_acceptance():
    d = Path.cwd() / "reports/research/iterations/t20261014_hf_execution_value"
    manifest = json.loads((d / "candidate-manifest.json").read_text())
    approved = json.loads((P / "candidate-manifest-proposed.json").read_text())
    scope = json.loads((P / "fixed-component-comparison.json").read_text())
    search = json.loads((d / "search-space.json").read_text())
    assert len(manifest["candidates"]) == 60
    assert _canonical_fixed_comparison_matches(
        manifest, approved, scope, search, scope["approved_inventory"]
    )
    assert not fixed_seen_component_comparison_applies(
        search, Path.cwd()
    )  # Actual review not reapproved.


def test_actual_producer_disk_boundary_and_launch_identity_are_exact():
    tree = ast.parse((P / "run_execution_accounts.py").read_text())
    constant = next(
        n.value.value
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "DISK_REFRESH_RESERVE_BYTES" for t in n.targets)
    )
    test = next(
        n.test
        for n in ast.walk(tree)
        if isinstance(n, ast.If) and "shutil.disk_usage" in ast.unparse(n.test)
    )
    expression = compile(ast.Expression(test), "<actual-producer-disk-guard>", "eval")
    assert constant == 9533075101
    threshold = constant + 64 * 1024**2
    for free, refuse in [(threshold - 1, True), (threshold, False), (threshold + 1, False)]:
        namespace = {
            "shutil": SimpleNamespace(
                disk_usage=lambda path, observed_free=free: SimpleNamespace(free=observed_free)
            ),
            "P": P,
            "DISK_REFRESH_RESERVE_BYTES": constant,
        }
        assert eval(expression, namespace) is refuse
    launch = json.loads((P / "first-book-launch-manifest.json").read_text())
    assert launch["disk_refresh_reserve_bytes"] == constant
    assert launch["book_checkpoint_atomic_output_bytes"] == 64 * 1024**2
