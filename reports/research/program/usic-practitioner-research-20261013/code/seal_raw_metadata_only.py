"""Small metadata-only seal; reuse retained entity hashes, no raw-row reads."""

import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
OUT = BASE / "revisions/v3-finite-qqq"


def bind(p):
    return {"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


ledger = json.loads((OUT / "market/request-ledger.json").read_text())
target = OUT / "actual-diagnostic-package-manifest.json"
assert not target.exists()
metadata = [p for p in OUT.rglob("*") if p.is_file() and p.suffix in {".json", ".txt", ".py"}
            and "entry-r1-before" not in p.parts and "__pycache__" not in p.parts
            and not p.name.startswith("independent")]
metadata += [p for p in (BASE / "code").glob("*.py") if p.name in {
    "acquire_finite_cohort_bridge.py", "repair_declared_sec_source.py",
    "build_finite_raw_diagnostic.py", "seal_bounded_raw_components.py",
    "seal_actual_bridge_result.py", "seal_raw_metadata_only.py"}]
manifest = {
    "schema_version": 3, "role": "actual_raw_components_partial_causal_features_not_economic_input",
    "result": bind(OUT / "actual-bridge-result.json"),
    "files": [bind(p) for p in sorted(set(metadata))],
    "complete_market_entity_bindings_from_author_request_ledger": [a["entity"] for a in ledger["attempts"]],
    "complete_source_entity": {
        "path": str((OUT / "source-repair-entities/nport-1.bin").relative_to(ROOT)),
        "sha256": "5a9d80e6fcd288e79822440b3a0136c49216d767c3a2ae8b3598f8772edfb613"},
    "prior403_entity": {
        "path": str((OUT / "source-entities/nport-1.bin").relative_to(ROOT)),
        "sha256": "1857abfd9aa871de9b3b7f6a5c9e229ad1627569d9fb6e82d0af1f978e7a0c43"},
    "FTD_existing_source_bindings": json.loads((OUT / "identity-candidates.json").read_text())["FTD_sources"],
    "failed_partial_pointer_files_preserved_not_complete_or_consumed": [
        str((OUT / "derived-attempt1/source-record-pointers.jsonl").relative_to(ROOT)),
        str((OUT / "derived/source-record-pointers.jsonl").relative_to(ROOT))],
    "partial_pointer_hashes": None,
    "complete_source_entity_hashes_are_authoritative_not_partial_row_indices": True,
    "last_metadata_timeout": {"actual_exit": 137, "wall_limit_s": 0.4,
                              "CPU_unknown_conservative_charge": 0.4,
                              "time_child_CPU_zero_is_not_proof_of_zero_spend": True},
    "bridge_CPU_used_before_this_small_metadata_seal": 119.88,
    "this_metadata_seal_conservative_CPU_charge_max": 0.10,
    "bridge_CPU_used_cap_remaining_conservative": [119.98, 120, 0.02],
    "Martin_CPU_used_cap_remaining_conservative": [261.44, 2000, 1738.56],
    "independent_component_acceptance": "pending; author does not self-approve",
    "economic_CPU_used_allocated": [0, 0],
    "all_parent_sealed_packages_untouched": True,
}
target.write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(bind(target)))
