"""Bounded audit of returned evidence; no model, prices, or portfolio replay."""

import collections
import datetime
import gzip
import hashlib
import json
import math
import resource
import statistics
import time
from pathlib import Path

resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
started = time.process_time()
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "scripts/modal_budget.py").exists())
HERE = Path(__file__).resolve().parent
BASE = ROOT / "reports/research/program/day-goal-20261011-2/chinco-modern-adaptation"
F05 = BASE / "method-implementation/stage-S2-F05-v1"
JOB = F05 / "actual-execution-attempt01"
CORE = JOB / "core-prefix-evidence"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def rows(name):
    with gzip.open(CORE / "science" / (name + ".jsonl.gz"), "rt") as handle:
        for line in handle:
            yield json.loads(line)


bindings = []
prior = {}
for name, relative in {
    "F01": "method-implementation/remote-S1-v1/root-baseline-result-acceptance.json",
    "F03": "method-implementation/remote-S1-v1/root-F03-result-acceptance.json",
    "F04": (
        "method-implementation/stage-S2-F04-v1/full-five-day-execution/"
        "root-F04-result-acceptance.json"
    ),
    "Q0": "method-implementation/accepted-decision-Q0-replay-v1/Root-result-acceptance.json",
    "funding": "broker-applicability/cash-funding-20261012/Root-result-acceptance.json",
    "bottleneck": "fidelity-next-decision/accepted-output-bottleneck/root-result-acceptance.json",
    "cost": "fidelity-next-decision/cost-applicability/root-judgment-acceptance.json",
}.items():
    path = BASE / relative
    accepted = read(path)
    binding_key = next(
        (
            k
            for k in (
                "evaluation_report",
                "independent_acceptance",
                "result_binding",
                "result",
                "decision",
            )
            if isinstance(accepted.get(k), dict) and "path" in accepted[k]
        ),
        None,
    )
    if binding_key:
        binding = accepted[binding_key]
        assert sha(ROOT / binding["path"]) == binding["sha256"]
    bindings.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path)})
    prior[name] = accepted

transport = read(JOB / "returned/manifest.json")
assert (
    sha(JOB / "returned/manifest.json")
    == "5d15c6e17e27a39b778e08bde839cb4a7d60e4789a598d74d78566c4d65d3f6e"
)
declared = {row["path"]: row for row in transport["files"]}
core_manifest = read(JOB / "core-prefix-evidence-verification.json")
for row in core_manifest["files"]:
    path = CORE / row["path"]
    assert row == declared[row["path"]]
    assert path.stat().st_size == row["bytes"] and sha(path) == row["sha256"]
admission = read(JOB / "actual-runtime-admission-operator01.json")
execution = read(CORE / "science/execution-receipt.json")
report = read(CORE / "science/evaluation-report.json")
runtime = read(CORE / "runtime-receipt.json")
manifest = read(F05 / "run-manifest-F05-five-day.json")
assert execution["code_hashes"] == admission["implementation_hashes"]
assert (
    execution["stage_manifest_sha256"]
    == sha(F05 / "run-manifest-F05-five-day.json")
    == admission["run_manifest_sha256"]
)
assert report["plan_sha256"] == admission["plan_sha256"]
assert runtime["native_exit_code"] == 0 and execution["status"] == "complete_admitted_scope"
assert not read(CORE / "operator-owned-tree-exit.json")["owned_remaining_processes"]
assert math.isclose(
    runtime["wall_seconds"] * 4, runtime["conservative_whole_job_CPU_charge_seconds"], abs_tol=1e-6
)
assert report["exposure"] == execution["exposure"]

keys, successful, sigma = set(), set(), collections.Counter()
quotes, selection = collections.Counter(), collections.Counter()
producer = {}
for row in rows("entry-hurdle-diagnostic"):
    key = (row["target"], row["decision_ns"])
    assert row["stream"] == "F05" and key not in keys
    keys.add(key)
    seconds = row["full_batch_producer_seconds"]
    assert math.isfinite(seconds) and seconds >= 0
    if row["decision_ns"] in producer:
        assert producer[row["decision_ns"]] == seconds
    producer[row["decision_ns"]] = seconds
    if row["forecast"] is not None:
        successful.add(key)
        sigma["zero" if row["sigma"] == 0 else "positive"] += 1
    if row["strict_weight"] > 0:
        selection["strict_weight_positive"] += 1
        assert row["eligible"] and row["sigma"] > 0 and row["forecast"] > row["primary_hurdle"]
    spread = row["quoted_full_relative_spread"]
    if not row["eligible"] or spread is None:
        continue
    assert math.isclose(row["primary_hurdle"], spread + 0.004, abs_tol=1e-15)
    label = "zero" if row["sigma"] == 0 else "positive"
    f = row["forecast"]
    for sign, value in (("positive", f), ("negative_absolute", -f)):
        if value > spread:
            quotes[f"{sign}_above_spread_sigma_{label}"] += 1
        if value > row["primary_hurdle"]:
            quotes[f"{sign}_above_primary_sigma_{label}"] += 1
assert len(keys) == 44375 and len(producer) == 1775
assert (
    len(successful)
    == 44375
    - execution["exposure"]["unavailable_forecasts"]
    - execution["exposure"]["failed_forecasts"]
)

features, economic, usable = set(), collections.Counter(), collections.Counter()
for row in rows("feature-availability"):
    key = (row["target"], row["decision_ns"])
    assert key not in features and row["requested_pool"] == 500
    features.add(key)
    if key in successful:
        economic[row["economic_symbols"]] += 1
        usable[row["usable_symbols"]] += 1
assert features == keys and sum(usable.values()) == len(successful)

days = list(rows("continuous-daily-NAV"))
assert len(days) == 30
sessions = [s["date"] for s in manifest["sessions"]]
view_results = []
for view, value in report["views"].items():
    daily = sorted((r for r in days if r["view_id"] == view), key=lambda r: r["date"])
    assert [r["date"] for r in daily] == sessions
    assert all(
        r["full_session"] and r["path_complete"] and not r["wealth_unknown"] and r["cash"] >= 0
        for r in daily
    )
    previous = 20000.0
    for row, ret in zip(daily, value["daily_returns"], strict=True):
        assert math.isclose(row["NAV"] / previous - 1, ret, abs_tol=1e-12)
        previous = row["NAV"]
    assert math.isclose(previous - 20000, value["net_dollars"], abs_tol=1e-8)
    view_results.append(
        {
            "view": view,
            "net_dollars_reported": value["net_dollars"],
            "filled_commands_reported": report["execution_coverage"][view]["filled_commands"],
            "acceptance": "preliminary_core_only",
        }
    )

inventory = {r["path"] for r in transport["parts"] if (JOB / "returned" / r["path"]).exists()}
output = {
    "at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
    "scope": (
        "Existing accepted reports plus 28 originally returned F05 core members; "
        "descriptor/recorded NAV consistency only."
    ),
    "prior_acceptance_bindings": bindings,
    "F05": {
        "core_members_SHA_verified": len(core_manifest["files"]),
        "report_SHA": sha(CORE / "science/evaluation-report.json"),
        "original_parts_local": len(inventory),
        "original_parts_total": len(transport["parts"]),
        "actual_owned_exit_verified": True,
        "full_archive_accepted": False,
        "independent_scientific_acceptance": False,
        "requested_target_minutes": len(keys),
        "recorded_successful_forecasts": len(successful),
        "recorded_sigma": dict(sigma),
        "sigma_recomputed_from_fitted_values": False,
        "economic_symbols_successful_min_max": [min(economic), max(economic)],
        "usable_symbols_successful_min_max": [min(usable), max(usable)],
        "successful_economic_width_histogram": dict(sorted(economic.items())),
        "successful_usable_width_histogram": dict(sorted(usable.items())),
        "eligible_recorded_quote_exceedance": dict(quotes),
        "selection": dict(selection),
        "producer_median_seconds_from_recorded_diagnostics": statistics.median(producer.values()),
        "producer_max_seconds_from_recorded_diagnostics": max(producer.values()),
        "L5_batch_misses_from_recorded_diagnostics": sum(v > 3 for v in producer.values()),
        "L15_batch_misses_from_recorded_diagnostics": sum(v > 13 for v in producer.values()),
        "recorded_daily_NAV_report_consistency": True,
        "full_cash_share_fee_fill_ledger_reconciliation": False,
        "views": view_results,
        "new_fits": 0,
        "new_replays": 0,
    },
    "new_economic_trials": 0,
    "CPU_seconds": time.process_time() - started,
    "charge_to": (
        "Original F05 500 CPU-second technical/result verification reserve; "
        "no final independent acceptance claimed."
    ),
}
path = HERE / "existing-evidence-check.json"
with path.open("x") as handle:
    json.dump(output, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(
    json.dumps(
        {
            "path": str(path.relative_to(ROOT)),
            "CPU_seconds": output["CPU_seconds"],
            "F05": {k: v for k, v in output["F05"].items() if not k.endswith("histogram")},
        }
    )
)
