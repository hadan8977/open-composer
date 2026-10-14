"""Verify existing checkpoint/input and bind only the authorized resource/resume delta."""

import hashlib
import json
import pickle
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import sklearn
from hf_features import P, bind, save
from hf_models import hgb
from hf_run_models import binning_digest, tree_state_digest

E = P / "economic"
D = Path.cwd() / "reports/research/iterations/t20261013_hf_factor_conditional_method"
A = P / "implementation-M2-archive"


def main():
    assert sklearn.__version__ == "1.9.0"
    old = json.loads((A / "implementation-manifest.json").read_text())
    model_input = json.loads((E / "HGB-input-IDX-2019.json").read_text())
    checkpoint = E / "models/HGB-IDX-2019-depth6-lr0.1-trees150.pkl"
    expected = json.loads((P / "economic-capacity-decision.json").read_text())["checkpoints"][1]
    assert bind(checkpoint) == expected["checkpoint"]
    for field in ["scaled", "scaling"]:
        assert bind(model_input[field]["path"]) == model_input[field]
    with np.load(model_input["scaling"]["path"]) as state:
        assert int(state["n_train"]) == 96451
        scaler_values = {
            key: dict(
                shape=list(state[key].shape),
                dtype=str(state[key].dtype),
                sha256=hashlib.sha256(state[key].tobytes()).hexdigest(),
            )
            for key in state.files
        }
    model = pickle.loads(checkpoint.read_bytes())
    assert model.get_params() == hgb(6, 0.1, 150, warm_start=True).get_params()
    assert model.n_iter_ == len(model._predictors) == 150
    contract = dict(
        schema_version=1,
        checkpoint150=bind(checkpoint),
        scaled_input=model_input["scaled"],
        scaler=model_input["scaling"],
        sklearn_version="1.9.0",
        source_feature_manifest=model_input["source"],
        n_train=96451,
        n_validation=24113,
        parameters=model.get_params(),
        completed150_intrinsic_CPU=expected["cumulative_CPU"],
        first150_tree_digest=tree_state_digest(model, 150),
        bin_threshold_digest=binning_digest(model),
        random_seed=int(model._random_seed),
        feature_subsample_rng_state=model._feature_subsample_rng.bit_generator.state,
        scaler_value_hashes=scaler_values,
        original50_150_not_overwritten=True,
        resume_additional_trees=200,
        output350=str(E / "models/HGB-IDX-2019-depth6-lr0.1-trees350.pkl"),
        old_incomplete350_exposure_and450_failure_preserved=True,
        public_warm_start_only=True,
        private_kernel_or_binning_reuse=False,
        real_fit_inference_or_score_read_during_preparation=False,
    )
    save(P / "calibration-resume-contract.json", contract)
    authority = bind(P / "root-complete-economic-resource-amendment.json")
    admission = dict(
        schema_version=2,
        task_id="DAY3-HF-FACTOR-RETURN",
        authority=authority,
        local_CPU_cores=1,
        memory_cap_MiB=1024,
        economic_unique_cap_coreseconds=36000,
        calibration_continuation_inclusive_CPU=1200,
        launcher_margin_CPU=5,
        original_preparation_and500_reservations_not_borrowed=True,
        required=(
            "Actual affected independent implementation acceptance, applicable native gates, "
            "ledger job reservation and fresh capped memory admission"
        ),
        source_market_paid_cloud_Hadan_broker_authority_added=False,
        exact_caps_not_integer_minutes=True,
    )
    save(P / "resource-admission.json", admission)
    changed = [P / "hf_run_models.py", P / "hf_evaluate.py"]
    files = []
    for record in old["files"]:
        path = Path(record["path"])
        absolute = path.resolve()
        if absolute in changed:
            files.append(bind(absolute))
        else:
            files.append(record)
    additions = [
        P / "hf_completion_resources.py",
        P / "test_hf_completion_delta.py",
        P / "prepare_hf_completion_delta.py",
        P / "completion-delta-tests.xml",
        P / "completion-delta-tests-resource.txt",
        P / "resource-admission.json",
        P / "calibration-resume-contract.json",
        P / "root-complete-economic-resource-amendment.json",
        P / "root-warm-start-primary-evidence.json",
        checkpoint,
        Path(model_input["scaled"]["path"]),
        Path(model_input["scaling"]["path"]),
    ]
    files.extend(bind(path) for path in additions)
    updated = dict(
        old,
        as_of_utc=datetime.now(UTC).isoformat(),
        files=files,
        file_count=len(files),
        scope=old["scope"] + "; resource-only M2 native warm checkpoint continuation",
        entrypoints=[bind(P / "hf_run_models.py"), bind(P / "hf_evaluate.py")],
        M1_immutable_archive=bind(A / "implementation-manifest.json"),
        resource_amendment=authority,
        resume_contract=bind(P / "calibration-resume-contract.json"),
        unaffected71_bindings_reused_without_large_rehash=True,
        new_synthetic_runtime_resume_tests=5,
        new_real_market_fits=0,
        science_data_candidates_validation_cost_choice_unchanged=True,
    )
    save(P / "implementation-manifest.json", updated)
    method = json.loads((D / "method-definition.json").read_text())
    method["implementation_manifest"] = bind(P / "implementation-manifest.json")
    method["resource_amendment"] = authority
    save(D / "method-definition.json", method)
    direction = json.loads((D / "direction-review.json").read_text())
    check = direction["cheapest_decisive_test"]
    check.update(
        pass_condition=(
            "Complete measured350 projection plus actual used/commitments "
            "fitsRoot amended cumulative36000 and reveals decision-relevant "
            "net account/method contribution."
        ),
        max_compute_minutes=600,
        exact_resource_cap_coreseconds=36000,
        minute_rounding_not_new_CPU=(
            "Root exact36000 cumulative CPU, including prior460.49 "
            "and all current work;600min is presentation only."
        ),
    )
    direction["resource_amendment"] = authority
    save(D / "direction-review.json", direction)
    save(
        P / "completion-implementation-delta.json",
        dict(
            schema_version=1,
            task_id="DAY3-HF-FACTOR-RETURN",
            author="7b109880-ac40-447e-b2a6-f0ed1266ebac",
            reviewer="ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3",
            authority=authority,
            old_M1=bind(A / "implementation-manifest.json"),
            new_M2=bind(P / "implementation-manifest.json"),
            old_code={name: bind(A / name) for name in ["hf_run_models.py", "hf_evaluate.py"]},
            new_code={
                name: bind(P / name)
                for name in ["hf_run_models.py", "hf_evaluate.py", "hf_completion_resources.py"]
            },
            resume_contract=bind(P / "calibration-resume-contract.json"),
            budget_ledger_base=bind(P / "economic-resource-ledger.json"),
            native_method=bind(D / "method-definition.json"),
            native_direction=bind(D / "direction-review.json"),
            tests=bind(P / "completion-delta-tests.xml"),
            old_source_and_input_acceptance_retained=True,
            scope=(
                "Only resource limits, exact conservative tally, public warm150→350 continuation, "
                "same original complete projection with actual committed costs; "
                "no source/model/clock/account/selection changes."
            ),
            runtime_resume_native_economic_gates_ready=False,
        ),
    )
    print(
        json.dumps(
            dict(
                status="delta_prepared",
                manifest=bind(P / "implementation-manifest.json"),
                resume_contract=bind(P / "calibration-resume-contract.json"),
                fits=0,
            )
        )
    )


if __name__ == "__main__":
    main()
