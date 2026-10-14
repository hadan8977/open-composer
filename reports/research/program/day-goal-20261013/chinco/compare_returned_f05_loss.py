"""Original matched outer-loss diagnostic; no fitting or portfolio replay."""

import os

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

import datetime  # noqa: E402
import gzip  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import resource  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "scripts/modal_budget.py").exists())
HERE = Path(__file__).resolve().parent
BASE = ROOT / "reports/research/program/day-goal-20261011-2/chinco-modern-adaptation"
METHOD = BASE / "method-implementation"
sys.path.insert(0, str(METHOD / "stage-S1-v1"))
import numpy as np  # noqa: E402
from study_statistics import forecast_loss_report  # noqa: E402

resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
started = time.process_time()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def load(stream, acceptance, manifest, folder, list_key):
    accepted, transport = read(acceptance), read(manifest)
    assert accepted["transport_sha256"] == sha(manifest)
    forecast_binding = next(
        r for r in transport[list_key] if r["path"] == "science/forecasts.jsonl.gz"
    )
    forecast_path = folder / "forecasts.jsonl.gz"
    assert forecast_path.stat().st_size == forecast_binding["bytes"]
    assert sha(forecast_path) == forecast_binding["sha256"]
    forecasts = {}
    with gzip.open(forecast_path, "rt") as handle:
        for line in handle:
            row = json.loads(line)
            if row["stream"] == stream:
                key = (row["target"], row["decision_ns"])
                assert key not in forecasts
                forecasts[key] = (row["forecast"], row["forecast_id"])
    binding = next(r for r in transport[list_key] if r["path"] == "science/outer-loss.jsonl.gz")
    path = folder / "outer-loss.jsonl.gz"
    assert path.stat().st_size == binding["bytes"] and sha(path) == binding["sha256"]
    data = {}
    with gzip.open(path, "rt") as handle:
        for line in handle:
            row = json.loads(line)
            if row["stream"] != stream:
                continue
            key = (row["target"], row["decision_ns"])
            assert key not in data
            value, identity = forecasts[key]
            assert identity == row["forecast_id"]
            if row["squared_loss"] is not None:
                assert value is not None and row["label"] is not None
                assert math.isclose(
                    row["squared_loss"],
                    (row["label"] - value) ** 2,
                    rel_tol=1e-12,
                    abs_tol=1e-30,
                )
            data[key] = row
    assert len(data) == 44375 and forecasts.keys() == data.keys()
    return data, {
        "acceptance": {"path": str(acceptance.relative_to(ROOT)), "sha256": sha(acceptance)},
        "outer_loss": {"path": str(path.relative_to(ROOT)), "sha256": sha(path)},
    }


f05_stage = METHOD / "stage-S2-F05-v1"
f05_job = f05_stage / "actual-execution-attempt01"
candidate, candidate_binding = load(
    "F05",
    f05_stage / "Root-independent-result-review/root-F05-result-acceptance.json",
    f05_job / "returned/manifest.json",
    f05_job / "returned/job/science",
    "files",
)
comparisons, bindings = {}, {"F05": candidate_binding}
for ref, acceptance in {
    "F01": METHOD / "remote-S1-v1/root-baseline-result-acceptance.json",
    "F03": METHOD / "remote-S1-v1/root-F03-result-acceptance.json",
    "F04": METHOD / "stage-S2-F04-v1/full-five-day-execution/root-F04-result-acceptance.json",
}.items():
    folder = (ROOT / read(acceptance)["evaluation_report"]["path"]).parent
    if ref == "F04":
        manifest, field = folder.parent.parent / "manifest.json", "files"
    else:
        manifest, field = folder.parent / "transport-manifest.json", "artifacts"
    reference, bindings[ref] = load(ref, acceptance, manifest, folder, field)
    assert candidate.keys() == reference.keys()
    cluster, unavailable = {}, 0
    for key, row in candidate.items():
        other = reference[key]
        assert row["label_ns"] == other["label_ns"] and row["label"] == other["label"]
        left, right = row["squared_loss"], other["squared_loss"]
        if left is None or right is None:
            unavailable += 1
            continue
        assert math.isfinite(left) and math.isfinite(right)
        day = datetime.datetime.fromtimestamp(key[1] // 10**9, datetime.UTC).date().isoformat()
        values = cluster.setdefault((day, key[0]), np.zeros(3))
        values += np.array([1, left, right])
    identity = f"F05_vs_{ref}"
    result = forecast_loss_report({identity: cluster})[identity]
    result["relative_MSE_improvement_percent"] = (
        100 * result["reference_minus_candidate_MSE"] / result["reference_MSE"]
    )
    result["unpaired_requested_keys_retained"] = unavailable
    comparisons[identity] = result

output = {
    "at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
    "scope": "Frozen direct paired outer loss and original 500 two-way cluster draws.",
    "requested_keys_each": 44375,
    "labels_and_label_times_identical": True,
    "comparisons": comparisons,
    "input_bindings": bindings,
    "statistics": {
        "path": str((METHOD / "stage-S1-v1/study_statistics.py").relative_to(ROOT)),
        "sha256": sha(METHOD / "stage-S1-v1/study_statistics.py"),
    },
    "numpy_version": np.__version__,
    "CPU_seconds": time.process_time() - started,
    "new_fits": 0,
    "new_portfolio_replays": 0,
    "new_candidates": 0,
    "research_pass": False,
    "ml_contribution_pass": False,
    "paper_ready_pass": False,
    "independent_scientific_acceptance": False,
    "limits": [
        "Five known development sessions, dependent target-minute observations.",
        "Matched finite loss intersection does not change the full ledger calendar.",
        "Prediction MSE improvement is distinct from costed portfolio contribution.",
        "No final scientific review or original TAQ reproduction claim.",
    ],
}
path = HERE / "F05-matched-loss-20261014.json"
with path.open("x") as handle:
    json.dump(output, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps({"path": str(path.relative_to(ROOT)), "comparisons": comparisons}))
