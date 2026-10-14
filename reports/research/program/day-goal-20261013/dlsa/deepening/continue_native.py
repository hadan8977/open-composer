"""Native runner continuation glue; no source intake, scheduler, guard or data staging."""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def commands_for(fit, code, inputs, output):
    """Only original fit/replay CLI; a complete fit is never optimized again."""
    folder = output / fit["fit_id"]
    base = [
        sys.executable,
        str(code / "runner.py"),
        "--configs",
        str(code / "training-configs.json"),
        "--input-root",
        str(inputs),
        "--fit-id",
        fit["fit_id"],
        "--device",
        "cuda:0",
    ]
    commands = []
    if not fit["training_complete"]:
        argv = base + [
            "--mode",
            "fit",
            "--input-manifest",
            str(folder / "input-manifest.json"),
            "--output-dir",
            str(folder / "fit"),
        ]
        if fit["native_cursor_updates"] > 0:
            argv += ["--resume", str(folder / "fit/latest.pt")]
        commands.append({"mode": "fit", "argv": argv})
    if not fit["replay_complete"]:
        commands.append(
            {
                "mode": "replay",
                "argv": base
                + [
                    "--mode",
                    "replay",
                    "--input-manifest",
                    str(folder / "replay-input-manifest.json"),
                    "--output-dir",
                    str(folder / "replay"),
                    "--resume",
                    str(folder / "fit"),
                ],
            }
        )
    return commands


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--accepted-state", type=Path, required=True)
    p.add_argument("--old-root", type=Path, required=True)
    p.add_argument("--code-root", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    state = json.loads(args.accepted_state.read_text())
    expected = [f"A{i:02d}-fold10" for i in range(5, 11)]
    fits = state["fits"]
    if [x["fit_id"] for x in fits] != expected:
        raise ValueError("exact original sixfit inventory required")
    for fit in fits:
        if type(fit["training_complete"]) is not bool or type(fit["replay_complete"]) is not bool:
            raise ValueError("completion flags must be actual booleans")
        if (
            type(fit["native_cursor_updates"]) is not int
            or not 0 <= fit["native_cursor_updates"] <= 800
        ):
            raise ValueError("invalid native cursor")
        if fit["training_complete"] and fit["native_cursor_updates"] != 800:
            raise ValueError("complete fit must have800 original updates")
        if fit["replay_complete"] and not fit["training_complete"]:
            raise ValueError("replay cannot precede complete fit")
    inputs = args.old_root.parent / state["input_cache_run_id"] / "work"
    inventory = [
        {
            "fit_id": fit["fit_id"],
            "remaining_unique_nominal_updates": 800 - fit["native_cursor_updates"],
            "commands": commands_for(fit, args.code_root, inputs, args.output_dir),
        }
        for fit in fits
    ]
    if not args.execute:
        print(json.dumps({"role": "argv_only_not_launch", "inventory": inventory}, indent=2))
        return
    # Planning while theoldjob is live is permitted; actual execution is not.
    if not (
        state.get("root_authorized") is True
        and state.get("old_job_actual_terminated") is True
        and state.get("input_and_native_checkpoint_hashes_accepted") is True
        and state.get("cumulative_resource_budget_freshly_admitted") is True
    ):
        raise ValueError("actual oldexit/input/native/cumulativebudget admissions required")
    # -I remains compatible: stdlib is loaded before adding only the declared code root.
    sys.path.insert(0, str(args.code_root))
    from runtime_common import checked_file, sha, write_json

    required_data = {
        "residual",
        "residual_mask",
        "composition_training",
        "composition_evaluation",
        "source_cnn",
        "source_frictions",
        "source_fourier",
        "source_preprocess",
        "source_simulation",
        "source_factor_utils",
        "plan",
        "independent_review",
    }
    if not required_data.issubset({x["id"] for x in state["data_files"]}) or not {
        "runner.py",
        "training_core.py",
        "replay.py",
        "training-configs.json",
        "runtime_common.py",
    }.issubset({x["path"] for x in state["code_files"]}):
        raise ValueError("complete original input/code bindings required")
    if args.old_root.resolve() == args.output_dir.resolve() or args.output_dir.exists():
        raise ValueError("new isolated continuation output required")
    for row in state["data_files"]:
        checked_file(inputs, row)
    for row in state["code_files"]:
        checked_file(args.code_root, row)
    args.output_dir.mkdir(parents=True)
    completed = []
    for fit, item in zip(fits, inventory, strict=True):
        if fit["fit_id"] > state["execute_through_fit_id"]:
            break  # Fixed original-order prefix; later preregistered fits stay deferred.
        if not item["commands"]:
            continue  # Original completedfit+replay outputs stay immutable inoldprefix.
        folder = args.output_dir / fit["fit_id"]
        folder.mkdir()
        accepted = fit["input_manifest"]
        write_json(folder / "input-manifest.json", accepted)
        if (
            fit.get("input_manifest_sha256") is not None
            and sha(folder / "input-manifest.json") != fit["input_manifest_sha256"]
        ):
            raise ValueError("native inputmanifest bytes must remain exact")
        for row in fit["preserved_fit_files"]:
            # Parent must bind only original checkpoints/snapshots/closed logs of thisfit.
            prefix = "fold10-matched-training/" + fit["fit_id"] + "/fit/"
            name = row["path"].removeprefix(prefix)
            if not row["path"].startswith(prefix) or not re.fullmatch(
                r"latest\.pt|final-epoch99\.pt|validation-epoch(?:0|10|20|30|40|50|60|70|80|90)\.pt|training-steps\.jsonl|result\.json",
                name,
            ):
                raise ValueError("preservedfit file outside exact namedfit")
            if fit["native_cursor_updates"] == 0:
                # Pre-checkpoint failure evidence stays inoldprefix; fresh fitdir stays absent.
                continue
            source = checked_file(args.old_root, row)
            target = folder / "fit" / Path(row["path"]).name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, target)
        for command in item["commands"]:
            if command["mode"] == "replay":
                replay_manifest = {
                    **accepted,
                    "native_fit_input_manifest_sha256": sha(folder / "input-manifest.json"),
                }
                write_json(folder / "replay-input-manifest.json", replay_manifest)
            print("DLSA_MODEL_STAGE_STARTED " + fit["fit_id"] + "/" + command["mode"], flush=True)
            native = subprocess.run(command["argv"], check=False).returncode
            if native != 0:
                write_json(
                    args.output_dir / "continuation-receipt.json",
                    {
                        "status": "failed_native_state_retained",
                        "completed": completed,
                        "native_exit": native,
                        "source_HTTP": 0,
                    },
                )
                raise SystemExit(native)
            completed.append({"fit_id": fit["fit_id"], "mode": command["mode"]})
            write_json(
                args.output_dir / "continuation-receipt.json",
                {"status": "continuing", "completed": completed, "source_HTTP": 0},
            )
            print("DLSA_MODEL_STAGE_COMPLETED " + fit["fit_id"] + "/" + command["mode"], flush=True)
    write_json(
        args.output_dir / "continuation-receipt.json",
        {
            "status": "requested_native_prefix_complete",
            "completed": completed,
            "source_HTTP": 0,
            "old_outputs_immutable": True,
            "all_six_frozen_fits_complete": state["execute_through_fit_id"] == "A10-fold10",
            "executed_through_fit_id": state["execute_through_fit_id"],
        },
    )


if __name__ == "__main__":
    main()
