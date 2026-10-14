"""Propagate the accepted M3 host-only bindings through the existing native graph."""

import hashlib
import json
from pathlib import Path

P = Path(__file__).resolve().parent
D = Path("reports/research/iterations/t20261013_hf_factor_conditional_method")


def bind(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bytes=path.stat().st_size)


def read(path):
    return json.loads(path.read_text())


def save(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main():
    review = read(P / "independent-implementation-review.json")
    assert review["verdict"] == "approve_implementation"
    rows = review["bindings"]
    rows = rows.values() if isinstance(rows, dict) else rows
    assert any(r.get("sha256") == bind(P / "implementation-manifest.json")["sha256"]
               for r in rows)
    method = read(D / "method-definition.json")
    method["implementation_manifest"] = bind(P / "implementation-manifest.json")
    method["independent_implementation_review"] = bind(P / "independent-implementation-review.json")
    method["host_availability_diff"] = bind(P / "host-leading-availability-diff.json")
    method["independent_host_availability_review"] = bind(P / "independent-host-clock-diff-review.json")
    save(D / "method-definition.json", method)
    direction = read(D / "direction-review.json")
    direction["independent_implementation_review"] = bind(P / "independent-implementation-review.json")
    save(D / "direction-review.json", direction)
    candidates = read(D / "candidate-manifest.json")
    for row in candidates["candidates"]:
        row["method_definition_sha256"] = bind(D / "method-definition.json")["sha256"]
    save(D / "candidate-manifest.json", candidates)
    by_id = {row["candidate_id"]: row for row in candidates["candidates"]}
    feasibility = read(D / "data-feasibility.json")
    feasibility["required_references"]["input_acceptance"] = bind(
        (P / "independent-implementation-review.json").relative_to(Path.cwd())
    )
    for row in feasibility["candidate_authorization"]["rows"]:
        row["candidate_binding_sha256"] = hashlib.sha256(json.dumps(
            by_id[row["candidate_id"]], sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
    save(D / "data-feasibility.json", feasibility)
    search = read(D / "search-space.json")
    search["candidate_manifest_sha256"] = bind(D / "candidate-manifest.json")["sha256"]
    search["data_feasibility_sha256"] = bind(D / "data-feasibility.json")["sha256"]
    save(D / "search-space.json", search)
    save(P / "completion-host-native-wiring.json", dict(
        scope="Only M3 implementation/review and leading-host-clock binding propagation",
        native_go_claimed=False,
        bindings=[bind(D / n) for n in ["method-definition.json", "direction-review.json",
                                        "candidate-manifest.json", "data-feasibility.json",
                                        "search-space.json"]],
        original_candidate_definitions_and_contracts_unchanged=True,
    ))
    print("M3 accepted binding graph propagated; actual guard still required")


if __name__ == "__main__":
    main()
