"""Read-only metadata/provenance checks; never loads financial rows or runs a book."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path.cwd()
C = Path(__file__).resolve().parent
P = C.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(P))
from run_execution_accounts import admission_blockers, resume_identity  # noqa: E402

from open_composer.research.iteration_dossier import _campaign_contract_blockers  # noqa: E402

D = ROOT / "reports/research/iterations/t20261014_hf_execution_value"
search = json.loads((D / "search-space.json").read_text())
shared_blocked = _campaign_contract_blockers(search, ROOT, stage="pre-discovery")
finance_blocked = admission_blockers()
for name in ("market_component", "iteration_dossier"):
    qualified = f"open_composer.research.{name}"
    spec = importlib.util.spec_from_file_location(
        qualified, C / "candidate/open_composer/research" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
from open_composer.research.iteration_dossier import (  # noqa: E402
    _campaign_contract_blockers as candidate_blockers,
)
from open_composer.research.market_component import (  # noqa: E402
    fixed_seen_component_comparison_applies,
)

candidate_blocked = candidate_blockers(search, ROOT, stage="pre-discovery")
assert "campaign_contract_required_for_new_iteration" in shared_blocked
assert not fixed_seen_component_comparison_applies(search, ROOT)
assert "campaign_contract_required_for_new_iteration" in candidate_blocked
assert finance_blocked and "independent_implementation_review_not_approved" in finance_blocked
before = json.loads((C / "before-bindings.json").read_text())
assert all(
    hashlib.sha256(Path(r["before_path"]).read_bytes()).hexdigest() == r["sha256"] for r in before
)
for name in (
    "open_composer/research/iteration_dossier.py",
    "open_composer/research/market_component.py",
):
    row = next(r for r in before if r["path"] == name)
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == row["sha256"]
manifest = json.loads((P / "implementation-manifest.json").read_text())
mismatches = []
for row in manifest["files"]:
    digest = hashlib.sha256()
    with (ROOT / row["path"]).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != row["sha256"]:
        mismatches.append(row["path"])
assert not mismatches
row = next(
    r
    for r in json.loads((D / "candidate-manifest.json").read_text())["candidates"]
    if r["candidate_id"] == "DP_H16_SLOW__PLS_IDX_CTS__B0"
)
identity, history = resume_identity(row, 20, 20000, P / "execution-input-manifest.json")
assert history is None and identity["matched_exposure_input"] is None
assert set(identity["execution_code"]) == {"policy", "cash_actions", "producer"}
assert identity["execution_code"]["cash_actions"]["path"] == str(
    (P.parent / "hf_accounts.py").resolve()
)
assert identity["execution_code"]["producer"]["path"] == str(
    (P / "run_execution_accounts.py").resolve()
)
result = {
    "scope": "Read-only current bindings and guards; no financial admission claimed",
    "actual_shared_campaign_blockers": shared_blocked,
    "isolated_candidate_actual_scope_blockers": candidate_blocked,
    "actual_candidate_component_applicable": False,
    "reason": (
        "Actual implementation review still revise; new manifest/scope not independently accepted"
    ),
    "actual_producer_financial_guard": finance_blocked,
    "before_binding_checks": len(before),
    "before_mismatches": [],
    "shared_consumers_unchanged": True,
    "current_implementation_bindings_checked": len(manifest["files"]),
    "current_binding_mismatches": [],
    "actual_default_resume_identity": identity,
    "new_financial_runs": 0,
    "old_account_reruns": 0,
    "new_inference": 0,
    "new_requests": 0,
}
(C / "current-native-probe.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            k: result[k]
            for k in [
                "actual_shared_campaign_blockers",
                "isolated_candidate_actual_scope_blockers",
                "actual_producer_financial_guard",
                "current_implementation_bindings_checked",
                "current_binding_mismatches",
            ]
        }
    )
)
