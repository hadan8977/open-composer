"""Receive immutable, already accepted model provenance; never old signals/go.

Import is inert. All operations are standard-library metadata/hash reads. This
module contains no decoder, fit, feature builder, inference or broker entry.
Receiving historical provenance does not admit any current computational stage.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
PEER = "93af0483-230a-4632-8b48-c63cd53a01f7"
TASK = "CURRENT-PAPER-SCIENCE-20261020"


def canonical(path):
    result = Path(path).absolute()
    assert result == result.resolve(), "Canonical immutable artifact path required"
    return result


def binding(path):
    p = canonical(path)
    data = p.read_bytes()
    return dict(path=str(p), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def checked(row, expected=None):
    assert type(row) is dict and set(row) == {"path", "bytes", "sha256"}
    assert type(row["bytes"]) is int and row["bytes"] >= 0
    assert type(row["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
    p = canonical(row["path"])
    assert expected is None or p == canonical(expected), "Wrong historical canonical slot"
    assert binding(p) == row, "Changed immutable artifact"
    return p


def load(path):
    p = canonical(path)
    assert p.suffix == ".json", "This metadata receiver never decodes arrays/checkpoints"
    return json.loads(p.read_text())


def clock(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    assert result.tzinfo is not None
    return result.astimezone(timezone.utc)


def receive_historical_artifacts(policy):
    """Return bound model/preprocessing sources, excluding old forecast weights.

    Exact old independent result/input receipts establish a historical artifact
    boundary. Their old computation dates remain old; neither old for_execution
    consumers nor their expired authority/admission functions are called here.
    The actual current stage must separately receive current input/peer/native,
    resource, capability, clock and exact implementation admission before using
    a numerical decoder or computing anything.
    """
    assert policy in {"BASE", "H5", "LSTM"}
    contract = load(HERE / "prospective-contract.json")
    assert contract["task_id"] == TASK
    inventory = load(checked(contract["historical_artifacts"], HERE / "historical-artifact-inventory.json"))
    assert inventory["task_id"] == TASK and set(inventory["policies"]) == {"BASE", "H5", "LSTM"}
    item = inventory["policies"][policy]
    root = canonical(item["historical_root"])
    wrapper = load(checked(item["accepted_wrapper"], root / "accepted-current-component.json"))
    review = load(checked(item["independent_result_review"], root / "independent-result-review.json"))
    final = load(checked(item["final"], root / "final-manifest.json"))
    assert review["reviewer"] == PEER and review["independent"] is True
    assert review["task_id"] == final["task_id"] == item["historical_task_id"]
    assert review["verdict"] == "approve_result" and review["component_result_accepted"] is True
    assert review["target"] == item["final"]
    assert wrapper["component_result_accepted"] is True
    assert wrapper["independent_result_review"] == item["independent_result_review"]
    assert wrapper["sealed_final" if policy == "BASE" else "final"] == item["final"]
    assert item["forecast_and_order_reuse_allowed"] is False
    previous = load(checked(item["old_input"], root / ("received/input/output.json" if policy == "BASE" else "input/output.json")))
    input_review = load(checked(item["old_input_review"], root / "independent-current-input-review.json"))
    assert input_review["reviewer"] == PEER
    assert input_review["verdict"] == "accept_complete_current_input" and input_review["target"] == item["old_input"]
    assert input_review["source_linked_controls_accepted"] is True
    assert input_review["derived_control_witness"] == item["old_input"]
    files = {r["path"]: r for r in final["files"]}
    assert len(files) == len(final["files"])
    assert files[item["old_input"]["path"]] == item["old_input"]
    for key in ["model_artifacts", "support_artifacts", "model_metadata"]:
        for row in item.get(key, []):
            checked(row)
    if policy == "BASE":
        assert item["model_artifacts"] == [previous["model_state"], previous["model_source"]]
        state = load(checked(previous["model_state"]))
        assert state["feature_count"] == 14 and state["model"]["alpha"] == 10
        assert state["source"] == previous["model_source"]
        assert state["late_reconstruction_not_Oct1_contemporaneous"] is True
        assert state["actual_created_at"] == contract["BASE"]["model"]["trained_at"]
        assert state["symbols"] == previous["symbols"]
        assert previous["observation_month"] == "2026-09"
        adopted = dict(model=previous["model_state"], feature_packet=previous["model_source"],
                       fixed_formation_fields=["primitive", "flags", "turnover", "formation_eligible"],
                       actual_trained_at=state["actual_created_at"], epoch="2026-10")
    elif policy == "H5":
        result = load(root / "models/output.json")
        assert binding(root / "models/output.json") in item["model_metadata"]
        started = load(root / "models/started.json")
        worker = load(root / "models/worker-started.json")
        seal = load(root / "models/seal.json")
        complete = load(root / "models/completed.json")
        assert seal["started"] == complete["started"] == binding(root / "models/started.json")
        assert seal["worker"] == complete["worker"] == binding(root / "models/worker-started.json")
        assert complete["seal"] == binding(root / "models/seal.json")
        assert seal["output"] == binding(root / "models/output.json")
        assert worker["started"] == seal["started"]
        request = started["go"]["request"]
        assert request["stage"] == "models" and request["task_id"] == item["historical_task_id"]
        assert result["genuine_new_fits"] == 2 and result["current_predictions"] == 0
        assert result["input"] == item["old_input"]
        assert [r["arm"] for r in result["models"]] == ["STOCK", "STATE"]
        assert [r["state"] for r in result["models"]] == item["model_artifacts"]
        audit = previous["training_audit"]
        contexts = {}
        for row in result["models"]:
            arm = row["arm"]
            assert row == load(root / "models" / (arm + "-completed.json"))
            context = load(checked(row["started"], root / "models" / (arm + "-started.json")))
            assert context["input"] == row["input"] == item["old_input"]
            assert row["input_complete"] == context["input_complete"] == binding(root / "input/completed.json")
            assert context["native"] == row["native"] == worker["native"] == started["go"]["native"]
            assert context["invocation"] == row["invocation"] == worker["invocation"] == request["invocation"]
            assert context["model_attempt"] == row["model_attempt"] == request["invocation"] + ":" + arm
            assert context["epoch"] == "2026-10" and context["cutoff"] == "2026-09-30"
            assert context["rows"] == audit["rows"] == 23248
            assert context["preprocessing"] == audit["preprocessing"][arm]
            assert context["medians"] == context["preprocessing"]["medians"]
            assert context["feature_order"] == context["preprocessing"]["feature_order"]
            assert context["labels_sha256"] == audit["labels_sha256"]
            assert context["ID_weight_sha256"] == audit["ID_weight_sha256"]
            assert context["train_matrix_sha256"] == context["preprocessing"]["train_matrix_sha256"]
            assert context["parameters"] == contract["H5"]["model_parameters"]
            assert clock(worker["claimed_at"]) <= clock(context["started_at"]) <= clock(row["completed_at"]) <= clock(result["computed_completed_at"]) <= clock(seal["sealed_at"]) <= clock(complete["completed_at"])
            contexts[arm] = context
        assert [r["model_attempt"] for r in result["models"]] == item["model_attempts"]
        adopted = dict(states=item["model_artifacts"], model_metadata=item["model_metadata"],
                       exact_inner_contexts=contexts, training_input=item["old_input"],
                       original_completed_at=complete["completed_at"], epoch="2026-10")
    else:
        contexts = previous["model_context"]
        assert [r["seed"] for r in contexts] == item["model_seeds"] == [20261016, 20261017]
        assert [r["checkpoint"] for r in contexts] == item["model_artifacts"]
        attempts = []
        for context in contexts:
            metadata = load(checked(context["metadata"]))
            seal = load(checked(context["seal"]))
            assert seal["files"] == dict(data=context["saved_forecast"], metadata=context["metadata"], checkpoint=context["checkpoint"])
            assert metadata["seed"] == context["seed"] and metadata["year"] == 2026
            assert metadata["role"] == "MEANNET" and metadata["parameters"] == 2421
            assert metadata["preprocessing"] == context["preprocessing"]
            assert metadata["torch_version"] == "2.13.0+cu130" and metadata["device"] == "cpu"
            assert metadata["latest_train_label_date"] == "2025-02-18"
            assert metadata["latest_validation_label_date"] == "2025-12-31"
            assert metadata["latest_validation_label_date"] < "2026-01-01"
            assert metadata["test_first_decision"] == "2026-01-02"
            assert clock(context["original_completed_at"]) < clock("2026-10-20T00:00:00Z")
            attempts.append(metadata["attempt_id"])
        assert len(set(attempts)) == 2
        adopted = dict(checkpoints=item["model_artifacts"], original_contexts=contexts,
                       original_attempts=attempts, epoch="2026", new_fits=0)
    return dict(task_id=TASK, policy=policy, provenance="immutable accepted historical models, not current forecast",
                inventory=binding(HERE / "historical-artifact-inventory.json"),
                historical_review=item["independent_result_review"], historical_input_review=item["old_input_review"],
                adopted=adopted, old_forecast_adopted=False, current_stage_admitted=False)
