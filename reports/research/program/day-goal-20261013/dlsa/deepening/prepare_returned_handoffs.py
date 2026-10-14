"""Verify existing terminal transport and make immutable per-fit H5 handoffs."""

import json
from pathlib import Path

from verify_completed_h5 import BASE, expected_artifacts, sha

HERE = Path(__file__).resolve().parent
RUN = "dlsa-fold10-native-A09A10-cont01-20261013"
ATTEMPT = HERE / "runtime/attempts" / RUN


def read(p):
    return json.loads(p.read_text())


def write_new(p, value):
    with p.open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    operator = read(ATTEMPT / "operator-receipt.json")
    remote = read(ATTEMPT / "remote-call-result.json")
    fetched = ATTEMPT / "fetched"
    transport = read(fetched / "transport-manifest.json")
    fetch = read(ATTEMPT / "fetch-receipt.json")
    assert operator["driver_returncode"] == 0
    assert operator["scientific_invocations_requested"] == 1
    assert operator["budget_returncode"] == 0
    assert operator["driver_log_sha256"] == sha(ATTEMPT / "modal-driver.log")
    assert fetch["transport_manifest_sha256"] == sha(fetched / "transport-manifest.json")
    assert fetch["remote"] == transport
    for result in (remote, transport):
        assert result["status"] == "completed" and result["returncode"] == 0
        assert result["run_id"] == RUN
        assert result["runtime_manifest_sha256"] == operator["runtime_manifest_sha256"]
        assert result["wall_seconds"] <= 7200
    artifacts = transport["artifacts"]
    assert len({r["path"] for r in artifacts}) == len(artifacts)
    assert sum(r["bytes"] for r in artifacts) == transport["bytes"]
    assert transport["bytes"] <= 64 * 1024 * 1024
    for row in artifacts:
        path = (fetched / row["path"]).resolve()
        assert path.is_relative_to(fetched)
        assert path.stat().st_size == row["bytes"] and sha(path) == row["sha256"]
    runtime = read(fetched / "runtime-receipt.json")
    assert runtime["status"] == "completed" and runtime["returncode"] == 0
    assert runtime["new_completed_batch_notifications"] == 1600
    assert runtime["source_HTTP"] == runtime["new_data_upload_bytes"] == 0
    for fit_id in ("A09-fold10", "A10-fold10"):
        expected = expected_artifacts(fit_id, 5)
        selected = [r for r in artifacts if r["path"] in expected]
        assert {r["path"] for r in selected} == expected
        snapshot = fetched / f"snapshot-{fit_id}.json"
        write_new(
            snapshot,
            {
                "fit_id": fit_id,
                "run_id": RUN,
                "transport_manifest_sha256": sha(fetched / "transport-manifest.json"),
                "artifacts": selected,
                "total_bytes": sum(r["bytes"] for r in selected),
                "scientific_acceptance_pending": True,
            },
        )
        write_new(
            HERE / f"handoff-{fit_id}.json",
            {
                "fit_id": fit_id,
                "snapshot_receipt": {"path": str(snapshot), "sha256": sha(snapshot)},
                "local_science_root": str(fetched / "fold10-matched-training" / fit_id),
                "original_admission": str(BASE / "r2/Root-final-runtime-admission.json"),
                "accepted_start_fits": 10,
                "accepted_start_updates": 8000,
            },
        )
    print(json.dumps({"transport_files": len(artifacts), "bytes": transport["bytes"]}))


if __name__ == "__main__":
    main()
