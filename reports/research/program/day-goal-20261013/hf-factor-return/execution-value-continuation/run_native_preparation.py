"""Run real native knowledge/direction/iteration functions without economic launch."""

import json
import os
import resource
import sys
from pathlib import Path

ROOT = Path.cwd()
P = Path(__file__).resolve().parent
D = ROOT / "reports/research/iterations/t20261014_hf_execution_value"
ITER_ID = D.name
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
resource.setrlimit(resource.RLIMIT_CPU, (450, 451))
sys.path.insert(0, str(P.parent))
import hf_native_policy_batch  # noqa: E402

log = []
# Reuse the previously accepted implementation: parse identical source-policy
# YAML once per collector call. Every native card/freshness/claim check executes.
# No data/approval/hash result is cached, and policy bytes are checked unchanged.
knowledge = hf_native_policy_batch.install(log)
scout_manifest = json.loads((D / "knowledge-scout-queries.json").read_text())
assert scout_manifest["queries"] == [], "No new public-source requests are authorized"
before = resource.getrusage(resource.RUSAGE_SELF)
knowledge.build_knowledge_index(ROOT)
scout = knowledge.scout_knowledge(ITER_ID, ROOT)
assessment = knowledge.assess_iteration_knowledge(ITER_ID, ROOT)
from open_composer.research.direction import validate_direction_review  # noqa: E402
from open_composer.research.iteration_dossier import validate_iteration_dossier  # noqa: E402

direction_blocked = validate_direction_review(
    D / "direction-review.json", ROOT, expected_iter_id=ITER_ID
)
validation = validate_iteration_dossier(ITER_ID, ROOT, stage="pre-backtest")
usage = resource.getrusage(resource.RUSAGE_SELF)
receipts = {
    "actual_native_functions": [
        "build_knowledge_index",
        "scout_knowledge",
        "assess_iteration_knowledge",
        "validate_direction_review",
        "validate_iteration_dossier",
    ],
    "native_direction_status": "blocked" if direction_blocked else "ok",
    "native_direction_blocked": direction_blocked,
    "native_knowledge_status": assessment.payload["status"],
    "native_knowledge_blocked": assessment.payload["blocked"],
    "native_iteration": validation.to_dict(ROOT),
    "curated_scout_candidates": scout.payload["candidate_count"],
    "new_source_requests": 0,
    "new_financial_runs": 0,
    "model_training_or_inference": 0,
    "source_policy_collection_log": log,
    "unchanged_source_policy_module": str(P.parent / "hf_native_policy_batch.py"),
    "source_checks_skipped_or_forged": False,
    "CPU": usage.ru_utime + usage.ru_stime - before.ru_utime - before.ru_stime,
    "max_RSS_KiB": usage.ru_maxrss,
    "independent_implementation_acceptance_not_author_certified": True,
}
(P / "native-preparation-receipt.json").write_text(
    json.dumps(receipts, ensure_ascii=False, indent=2) + "\n"
)
gate = {
    **validation.to_dict(ROOT),
    "actual_native_function": "validate_iteration_dossier",
    "current_artifact_bindings": [],
    "financial_launch_admitted": False,
    "new_financial_runs": 0,
}
(P / "native-iteration-gate.json").write_text(json.dumps(gate, indent=2) + "\n")
print(
    json.dumps(
        {
            "direction": receipts["native_direction_status"],
            "knowledge": receipts["native_knowledge_status"],
            "knowledge_blocked": receipts["native_knowledge_blocked"],
            "iteration": validation.status,
            "iteration_blocked": validation.blocked,
            "CPU": receipts["CPU"],
            "financial_runs": 0,
        }
    )
)
