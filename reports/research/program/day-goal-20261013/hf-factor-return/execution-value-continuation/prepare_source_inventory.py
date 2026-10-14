"""Local source extraction and preparation accounting; no economic simulation."""

import hashlib
import json
import resource
import subprocess
from datetime import UTC, datetime
from pathlib import Path

P = Path(__file__).resolve().parent
OLD = P.parent
ROOT = Path.cwd()


def bind(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
    }


def save(name, value):
    (P / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


ledger_path = OLD / "completion-resource-ledger.json"
ledger = json.loads(ledger_path.read_text())
charged = ledger["base_conservative_CPU"] + sum(
    entry.get("charge_CPU", 0) for entry in ledger["entries"]
)
held = [entry for entry in ledger["entries"] if entry["status"] != "closed"]
assert abs(charged - 12444.47) < 1e-6, "Root inherited ledger has changed; reconcile first"
assert sum(entry["upper_CPU"] for entry in held) == 30.0
subprocess.run(
    ["pdftotext", "-layout", str(P / "GP2013-author.pdf"), str(P / "GP2013-author.txt")],
    check=True,
)
inputs = [
    P / "GP2013-author.pdf",
    P / "GP2013-author.txt",
    OLD / "sources/hf-zoo-appendix.pdf",
    OLD / "sources/hf-zoo-appendix.txt",
    OLD / "hf-zoo-read.txt",
    OLD / "hf_accounts.py",
    OLD / "hf_features.py",
    OLD / "hf_models.py",
    OLD / "hf_evaluate.py",
    OLD / "source-fidelity-map.json",
    OLD / "implementation-manifest.json",
    OLD / "independent-result-review.json",
    OLD / "complete-costed-result.json",
    OLD / "complete-costed-completion-receipt.json",
    OLD / "features/feature-metadata.json",
    OLD / "features/packet-row-clock.json",
    OLD / "economic/linear-predictions.npy",
    OLD / "economic/HGB-predictions.npy",
    P / "existing-path-attribution.json",
    P / "source-ledger.json",
    P / "owner-runtime-readback.json",
]
save(
    "local-source-and-preparation-bindings.json",
    {
        "at_utc": datetime.now(UTC).isoformat(),
        "bindings": [bind(path) for path in inputs],
        "new_network_requests": 0,
        "model_fits": 0,
        "financial_simulations": 0,
        "original_attribution_not_repeated": True,
    },
)
sources = json.loads((P / "source-ledger.json").read_text())
assert sum(entry["units"] for entry in sources["entries"]) == 4
save(
    "authority-and-resource-reconciliation.json",
    {
        "task_id": "HF-EXECUTION-VALUE-CONTINUATION-20261014",
        "at_utc": datetime.now(UTC).isoformat(),
        "inherited_ledger": bind(ledger_path),
        "charged_CPU": charged,
        "held_entries": held,
        "held_CPU": 30.0,
        "inherited_uncommitted_CPU": 36000 - charged - 30,
        "source_units_actual_recorded": 4,
        "source_units_stale_current_state": 3,
        "source_direct_bytes_actual_recorded": sources["direct_bytes_used"],
        "new_units_this_turn": 0,
        "remaining_request_units": 4,
        "direct_byte_nominal_headroom": sources["direct_byte_cap"] - sources["direct_bytes_used"],
        "unknown_web_transfer_retained": True,
        "source_30_CPU_held_not_released_or_recharged": True,
        "text_extraction_completed_now": True,
        "original_source_download_not_restarted": True,
        "economic_execution_admitted": False,
    },
)
usage = resource.getrusage(resource.RUSAGE_SELF)
children = resource.getrusage(resource.RUSAGE_CHILDREN)
save(
    "source-preparation-internal-profile.json",
    {
        "CPU": usage.ru_utime + usage.ru_stime + children.ru_utime + children.ru_stime,
        "max_RSS_KiB": max(usage.ru_maxrss, children.ru_maxrss),
        "new_economic_runs": 0,
    },
)
print("Source extraction, inherited budget and request-ledger reconciliation complete.")
