"""Metadata-only same-semantics wrapper replacement after independent receipt."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

P = Path(__file__).resolve().parents[1]
ROOT = P.parents[4]
ITER = ROOT / "reports/research/iterations/usic_public_decision_replay_20261014"
V = P / "revisions/native-json-interface"


def binding(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def main():
    receipt_path = V / "independent-implementation-review.json"
    receipt = json.loads(receipt_path.read_text())
    assert receipt["verdict"] == "approve_implementation"
    assert receipt["author"] == "f9add224-744b-471c-b812-c43cc179fa38"
    assert receipt["reviewer"] == "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3"
    reviewed = receipt["bindings"]["implementation_manifest"]
    assert (ROOT / reviewed["path"]).resolve() == (V / "implementation-manifest.json").resolve()
    assert reviewed["sha256"] == binding(V / "implementation-manifest.json")["sha256"]
    # Preserve the independently validated old dossier as a single immutable snapshot.
    before = V / "before-dossier"
    assert not before.exists(), "no_implicit_native_metadata_rewrite"
    before.mkdir()
    names = (
        "method-definition.json",
        "candidate-manifest.json",
        "data-feasibility.json",
        "search-space.json",
    )
    for name in names:
        (before / name).write_bytes((ITER / name).read_bytes())
    definition = json.loads((ITER / "method-definition.json").read_text())
    definition["implementation_manifest"] = reviewed
    definition["independent_implementation_review"] = binding(receipt_path)
    save(ITER / "method-definition.json", definition)
    manifest = json.loads((ITER / "candidate-manifest.json").read_text())
    for row in manifest["candidates"]:
        row["method_definition_sha256"] = binding(ITER / "method-definition.json")["sha256"]
    save(ITER / "candidate-manifest.json", manifest)
    feasibility = json.loads((ITER / "data-feasibility.json").read_text())
    feasibility["required_references"]["implementation"] = binding(receipt_path)
    by_id = {row["candidate_id"]: row for row in manifest["candidates"]}
    for row in feasibility["candidate_authorization"]["rows"]:
        row["candidate_binding_sha256"] = hashlib.sha256(
            json.dumps(by_id[row["candidate_id"]], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    save(ITER / "data-feasibility.json", feasibility)
    search = json.loads((ITER / "search-space.json").read_text())
    search["candidate_manifest_sha256"] = binding(ITER / "candidate-manifest.json")["sha256"]
    search["data_feasibility_sha256"] = binding(ITER / "data-feasibility.json")["sha256"]
    save(ITER / "search-space.json", search)
    print(json.dumps({"metadata_updated": True, "economic_runs": 0, "new_market": 0}))


if __name__ == "__main__":
    main()
