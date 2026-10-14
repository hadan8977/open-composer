"""Seal completed outputs and existing nested evidence without repeating input hashes."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

P = Path(__file__).resolve().parent
E = P / "economic"


def binding(path):
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns, before.st_ino) == (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    ), str(path)
    return dict(path=str(path), sha256=digest.hexdigest(), bytes=after.st_size)


def main():
    assert json.loads((E / "evaluation-resource.json").read_text())["completed"]
    result = json.loads((P / "complete-costed-result.json").read_text())
    assert not result["author_interpretation_pending"]
    names = [
        "brief.md",
        "scientific-plan.json",
        "execution-contract.json",
        "independent-plan-review.json",
        "implementation-manifest.json",
        "independent-implementation-review.json",
        "independent-feature-input-acceptance.json",
        "independent-complete-source-input-acceptance.json",
        "independent-market-cache-bridge-acceptance.json",
        "complete-source-input-manifest.json",
        "market-cache-bridge-manifest.json",
        "completion-native-gate.json",
        "completion-full-study-admission.json",
        "completion-implementation-delta.json",
        "calibration-resume-contract.json",
        "root-complete-economic-resource-amendment.json",
        "root-owner-return-resolution-20261014.json",
        "completion-agent-fallback-runtime.json",
        "resource-admission.json",
        "completion-live-account-reservation-amendment.json",
        "completion-resource-ledger-before-live-account-reservation.json",
        "host-leading-availability-diff.json",
        "complete-host-clock-evidence.json",
        "hf_host_clock.py",
        "hf_complete_host.py",
        "completion-host-AST-diff.json",
        "independent-host-clock-diff-review.json",
        "interpret_hf_costed_result.py",
        "write_hf_final_support.py",
        "seal_hf_costed_package.py",
        "completion-host-native-wiring.json",
        "completion-host-native-repair.json",
        "completion-host-entrypoint-fix.json",
        "complete-costed-result.json",
        "complete-costed-result.md",
        "completion-resource-ledger-at-result.json",
        "hf_accounts.py",
        "hf_diagnostics.py",
        "hf_evaluate.py",
        "hf_run_models.py",
        "hf_features.py",
        "hf_completion_resources.py",
        "write_hf_costed_result.py",
        "build_hf_complete_manifest.py",
    ]
    paths = {P / name for name in names}
    paths.update((E / "results").iterdir())
    paths.update((E / "models").iterdir())
    paths.update((P / "implementation-M3-archive").iterdir())
    dossier = Path("reports/research/iterations/t20261013_hf_factor_conditional_method")
    paths.update(dossier / name for name in [
        "evaluation-report.json", "evaluation-report.md", "trial-ledger.jsonl",
        "decision-record.md", "method-definition.json", "direction-review.json",
        "candidate-manifest.json", "data-feasibility.json", "search-space.json",
        "knowledge-assessment.json",
    ])
    paths.update(Path("reports/harness/forensics") / name for name in [
        "conditional_hf_factor_method-backtest-forensics.json",
        "conditional_hf_factor_method-backtest-forensics.md",
    ])
    for name in [
        "linear-model-manifest.json",
        "HGB-model-manifest.json",
        "linear-predictions.npy",
        "HGB-predictions.npy",
        "model-trial-ledger.jsonl",
        "full-resource-projection.json",
        "evaluation-resource.json",
        "hgb-resource.json",
        "host-completion-resource.json",
    ]:
        paths.add(E / name)
    paths.update(E.glob("*resource*.txt"))
    paths.update(P.glob("completion-*-resource*.txt"))
    records = [binding(path) for path in sorted(paths) if path.is_file()]
    assert all((P / name).is_file() for name in names)
    output = dict(
        schema_version=1,
        task_id="DAY3-HF-FACTOR-RETURN",
        as_of_utc=datetime.now(UTC).isoformat(),
        files=records,
        file_count=len(records),
        bytes=sum(r["bytes"] for r in records),
        original_model_and_standalone_account_implementation_preserved=True,
        host_only_leading_availability_diff_explicit=True,
        large_source_feature_and_market_inputs=(
            "Nested accepted manifests and independent receipts; this output seal does not "
            "claim a new full input or source reread."
        ),
        ledger_snapshot_is_before_final_independent_acceptance=True,
        numerical_scope="20 pipelines / 800 diagnostics / 100 funded / 40 independent host sleeves",
        history_and_failed_exposure_retained=True,
        independent_result_acceptance_pending=True,
    )
    destination = P / "complete-costed-final-manifest.json"
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(binding(destination)))


if __name__ == "__main__":
    main()
