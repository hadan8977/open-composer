"""Publish saved native Martin accounts through the common lab; never replay prices."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from open_composer.lab import Experiment, TrialLedger, Variant, run_batch
from open_composer.lab.models import EngineResult
from open_composer.research.agent_workflow import local_path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/research/program/martin-decision-loop-model-continuation-20261026"
DIRECTION = "martin_model_completion_20261102"


def read(path):
    return json.loads(path.read_text())


def binding(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path.relative_to(ROOT)), "sha256": digest, "bytes": path.stat().st_size}


def saved_account(arm, *, source=SOURCE):
    """Keep native rounding, missing-mark flags and any received account identity alias."""
    comparison = read(source / "economic-comparison.json")
    attribution = read(source / "economic-flow-decomposition.json")
    aliases = attribution.get("source_account_aliases", {})
    alias_paths = []
    if aliases:
        proof_path = source / "account-equivalence.json"
        proof = read(proof_path)
        receipt = proof["independent_reception"]
        receipt_path = local_path(ROOT, receipt["path"])
        if (
            aliases != {"H": "R"}
            or proof["aliases"] != aliases
            or not proof["proved_identical_inputs"]
            or binding(receipt_path)["sha256"] != receipt["sha256"]
            or not read(receipt_path)["H_reuse_go"]
        ):
            raise ValueError("Account identity reuse lacks its received native proof")
        alias_paths = [proof_path, receipt_path]
    source_arm = aliases.get(arm, arm)
    folder = source / "runs" / f"2026-{source_arm}"
    result = read(folder / "result.json")
    if result["status"] != "complete_observed_conditional" or any(
        result[k] for k in ("open_positions", "open_orders", "reservations", "unknown_reasons")
    ):
        raise ValueError("Native account is incomplete; do not synthesize financial results")
    ending = float(result["native_cash"])
    if not math.isclose(ending - 20000, result["net_dollars"], abs_tol=1e-6):
        raise ValueError("Native net dollars do not reconcile to final cash")
    if not math.isclose(
        result["net_dollars"], comparison["accounts"][arm]["net_dollars"], abs_tol=1e-6
    ):
        raise ValueError("Comparison does not match the original account")
    bridge = read(folder / "saved-cash-bridge.json")
    if not math.isclose(float(bridge["native_cent_net"]), result["net_dollars"], abs_tol=1e-6):
        raise ValueError("Saved cash bridge does not match account dollars")
    curve = pd.read_csv(folder / "equity.csv", parse_dates=["day"]).set_index("day")
    if (
        len(curve) != result["calendar_sessions"]
        or curve.index.has_duplicates
        or not curve.index.is_monotonic_increasing
    ):
        raise ValueError("Original account calendar is incomplete")
    paths = [
        folder / "result.json",
        folder / "equity.csv",
        folder / "execution-source-events.json",
        folder / "saved-cash-bridge.json",
        source / "economic-comparison.json",
        source / "economic-flow-decomposition.json",
        *alias_paths,
    ]
    return EngineResult(
        engine="Martin native_accounts.run_cell: saved source-native reception",
        initial_equity_usd=20000,
        end_equity_usd=ending,
        native={"result": result, "bindings": [binding(p) for p in paths]},
        ledger=curve,
        # Native gaps mean the daily marks are not a complete physical return path.
        # Preserve those marks, but do not convert stale holdings into new statistics.
        net_returns=None,
        metadata={"logical_arm": arm, "source_arm": source_arm, "new_account_runs": 0},
        limitations=[
            "Saved account import only; no fit, account replay or new economic experiment",
            "All histories seen; static 29 securities/28 issuers; observed synthetic O-L-H-C",
            "Native daily marks retain stale-holding flags; physical return path unidentified",
            "Earlier selectable trial inventory unknown; account starts are not independent N",
        ],
    )


def export_saved(batch_id):
    # Validate every complete input before writing an exposure import or partial batch.
    outputs = {arm: saved_account(arm) for arm in "RSTH"}
    ledger = TrialLedger(ROOT / "research" / DIRECTION / "trials.jsonl")
    import_id = "original-fixed-S-T-models"
    if not any(e.trial_id == import_id for e in ledger.events()):
        ledger.import_prior(
            import_id,
            count=2,
            evidence=[
                str((SOURCE / "economic-comparison.json").relative_to(ROOT)),
                str((SOURCE / "protocol-proposal.md").relative_to(ROOT)),
            ],
            note="Two observed fixed learned candidates S/T. R baseline and H participation "
            "control remain separate. This is a known subset, not complete historical N. "
            "The 66 prior account-start floor is not converted into selectable trials.",
        )
    return run_batch(
        ROOT,
        experiment=Experiment(
            direction=DIRECTION,
            data_and_exposure="Frozen 2024 training/2025 input-only calibration/2026 Jan-Sep "
            "187-session evaluation; all history seen. n_trials is the known "
            "selectable subset, earlier history unknown.",
            costs="Native 10bp/side, whole shares, cash/T+1 and preserved cent rounding",
            baseline="R always-attempt native $20,000 account; T remains frozen primary",
            baseline_net_profit_usd=outputs["R"].net_profit_usd,
            limitations=("DSR unavailable: unknown complete trial history and physical returns",),
        ),
        batch_id=batch_id,
        variants=[
            Variant(
                arm,
                {"arm": arm, "source": str(SOURCE.relative_to(ROOT))},
                lambda arm=arm: outputs[arm],
                counts_as_trial=False,
                exposure_note="Saved account reception; S/T already imported once. "
                "R/H remain baseline/control. No new numerical experiment.",
            )
            for arm in "RSTH"
        ],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()
    batch = export_saved(args.batch)
    print(
        json.dumps(
            {
                "folder": str(batch.folder.relative_to(ROOT)),
                "failures": batch.failures,
                "known_selectable_subset": batch.n_trials,
                "new_account_runs": 0,
            }
        )
    )
