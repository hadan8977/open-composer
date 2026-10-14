"""Small affected bindings only; original receipts/science and shared CLI stay intact."""

import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path.cwd()
Q = Path(__file__).resolve().parent
P = Q.parent
C = P / "candidate-admission-v1"
D = ROOT / "reports/research/iterations/t20261014_hf_execution_value"


def bind(path):
    path = path.resolve()
    body = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }


def save(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


shared = [
    "open_composer/research/iteration_dossier.py",
    "open_composer/research/market_component.py",
]
patch = "".join(
    "".join(
        difflib.unified_diff(
            (C / "before" / name).read_text().splitlines(True),
            (C / "candidate" / name).read_text().splitlines(True),
            fromfile="a/" + name,
            tofile="b/" + name,
        )
    )
    for name in shared
)
(Q / "native-applicability-v2.diff").write_text(patch)
patch = "".join(
    difflib.unified_diff(
        (
            Q
            / "before"
            / C.relative_to(ROOT)
            / "candidate/open_composer/research/market_component.py"
        )
        .read_text()
        .splitlines(True),
        (C / "candidate/open_composer/research/market_component.py").read_text().splitlines(True),
        fromfile="a/candidate/open_composer/research/market_component.py",
        tofile="b/candidate/open_composer/research/market_component.py",
    )
)
(Q / "CLI1-affected-delta.diff").write_text(patch)
patch = "".join(
    "".join(
        difflib.unified_diff(
            (Q / "before" / P.relative_to(ROOT) / name).read_text().splitlines(True),
            (P / name).read_text().splitlines(True),
            fromfile="a/" + str((P / name).relative_to(ROOT)),
            tofile="b/" + str((P / name).relative_to(ROOT)),
        )
    )
    for name in ["run_execution_accounts.py", "build_execution_dossier.py"]
)
(Q / "producer-launch-delta.diff").write_text(patch)
manifest = json.loads((P / "implementation-manifest.json").read_text())
affected = {
    str((P / name).relative_to(ROOT)): bind(P / name)
    for name in [
        "run_execution_accounts.py",
        "build_execution_dossier.py",
        "fixed-component-comparison.json",
    ]
}
manifest["files"] = [affected.get(row["path"], row) for row in manifest["files"]]
manifest["fixed_component_comparison"] = bind(P / "fixed-component-comparison.json")
manifest["native_applicability_candidate"] = {
    "exact_unapplied_shared_patch": bind(Q / "native-applicability-v2.diff"),
    "affected_delta_test_receipt": bind(Q / "tests-01.xml"),
    "implementation_R1_R3_acceptance_reused": bind(
        P / "independent-implementation-revision-review-v1.json"
    ),
}
save(P / "implementation-manifest.json", manifest)
launch = json.loads((P / "first-book-launch-manifest.json").read_text())
launch["implementation"] = bind(P / "implementation-manifest.json")
assert (
    launch["disk_refresh_reserve_bytes"] == 9533075101
    and launch["book_checkpoint_atomic_output_bytes"] == 64 * 1024**2
)
save(P / "first-book-launch-manifest.json", launch)
full = json.loads((P / "full-run-launch-manifest.json").read_text())
assert len(full["fixed20k_views"]) == 120 and len(full["conditional4k_views"]) == 36
# Current dossier bindings are preparation only. Actual reviewer verdict stays
# revise; only Root/reviewer can provide a real approved binding for native use.
definition = json.loads((D / "method-definition.json").read_text())
definition["implementation_manifest"] = bind(P / "implementation-manifest.json")
save(D / "method-definition.json", definition)
canonical = json.loads((D / "candidate-manifest.json").read_text())
for row in canonical["candidates"]:
    row["method_definition_sha256"] = bind(D / "method-definition.json")["sha256"]
save(D / "candidate-manifest.json", canonical)
from open_composer.research.iteration_dossier import (  # noqa: E402
    candidate_authorization_binding_sha256,
)

feasible = json.loads((D / "data-feasibility.json").read_text())
for row in feasible["candidate_authorization"]["rows"]:
    current = next(r for r in canonical["candidates"] if r["candidate_id"] == row["candidate_id"])
    row["candidate_binding_sha256"] = candidate_authorization_binding_sha256(current)
save(D / "data-feasibility.json", feasible)
search = json.loads((D / "search-space.json").read_text())
search["candidate_manifest_sha256"] = bind(D / "candidate-manifest.json")["sha256"]
search["data_feasibility_sha256"] = bind(D / "data-feasibility.json")["sha256"]
save(D / "search-space.json", search)
assert len(canonical["candidates"]) == 60
before = json.loads((Q / "before-bindings.json").read_text())
assert all(bind(ROOT / r["before_path"])["sha256"] == r["sha256"] for r in before)
assert all(bind(ROOT / name)["sha256"] == bind(C / "before" / name)["sha256"] for name in shared)
save(
    Q / "affected-binding-receipt.json",
    {
        "changed_implementation_file_bindings": list(affected.values()),
        "exact_unapplied_patch": bind(Q / "native-applicability-v2.diff"),
        "implementation_manifest": bind(P / "implementation-manifest.json"),
        "fixed_scope": bind(P / "fixed-component-comparison.json"),
        "launch": bind(P / "first-book-launch-manifest.json"),
        "canonical_manifest": bind(D / "candidate-manifest.json"),
        "shared_unchanged": True,
        "financial_runs": 0,
        "old49plus47_not_rerun": True,
        "original_review_probe_preserved": True,
        "candidate_identities": 60,
    },
)
print(
    json.dumps({"affected_bindings_updated": True, "shared_unchanged": True, "financial_runs": 0})
)
