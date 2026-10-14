"""Read-only bounded binding check for a scientific input allocation review."""

import hashlib
import json
import pathlib
import resource
import time

resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
P = pathlib.Path(__file__).resolve().parent
ROOT = P.parents[4]
start = time.process_time()
seen = {}
conflicts = []


def check(row, local_base=None):
    relative = pathlib.Path(row["path"])
    path = ((local_base or ROOT) / relative) if not str(relative).startswith("reports/") else ROOT / relative
    raw = path.read_bytes()
    actual = {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    if actual["sha256"] != row["sha256"] or actual["bytes"] != row["bytes"]:
        conflicts.append(actual)
    seen[actual["path"]] = actual


decision_path = P / "scientific-input-decision.json"
manifest_path = P / "decision-manifest.json"
assert hashlib.sha256(decision_path.read_bytes()).hexdigest() == "fe41700fbc2da40a236587ed96537aac30c996714ac4d6cab6f2fe6f8b7704f8"
assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == "57e91846ec65c9d45dc4e2a9524ffb14f57ff970f1118061aa605ea79b7747cd"
decision = json.loads(decision_path.read_text())
manifest = json.loads(manifest_path.read_text())
check(manifest["decision"])
for row in manifest["files"] + list(decision["bindings"].values()):
    check(row)
local = json.loads((P / "local-input/package-manifest.json").read_text())
for row in local["files"]:
    check(row, P / "local-input")
evidence = json.loads((P / "osap-schema-connection-evidence.json").read_text())
gitchecks = []
for row in evidence["actual_version_bound_sources"]:
    check(row["binding"])
    raw = (ROOT / row["binding"]["path"]).read_bytes()
    actual = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    gitchecks.append({"repo_path": row["repo_path"], "matches_git_blob": actual == row["git_blob_sha1"]})
for name in ["author-public-return-connection-evidence.json", "local-input/independent-input-acceptance.json"]:
    data = json.loads((P / name).read_text())
    for row in data["bindings"].values():
        check(row)
assert not conflicts and all(row["matches_git_blob"] for row in gitchecks)
result = {
    "task_id": "DAY3-JOINT-DAILY-METHOD",
    "scope": "Static binding/source-code identity only; no repeat source numeric input audit or market/model calculation",
    "decision_sha256": hashlib.sha256(decision_path.read_bytes()).hexdigest(),
    "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    "decision_manifest_files": len(manifest["files"]),
    "nested_local_files": len(local["files"]),
    "unique_paths_checked": len(seen),
    "bytes_hashed_unique": sum(row["bytes"] for row in seen.values()),
    "mismatches": conflicts,
    "git_blob_checks": gitchecks,
    "CPU_coreseconds": time.process_time() - start,
    "peak_RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    "source_market_requests": 0,
    "fits_economic_runs": 0,
}
out = P / "independent-scientific-input-binding-verification.json"
assert not out.exists()
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(result, ensure_ascii=False))
