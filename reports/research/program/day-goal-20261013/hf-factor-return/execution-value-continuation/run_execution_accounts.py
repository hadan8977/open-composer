"""Guarded first-book/full-account producer; no market run before actual acceptance."""

import argparse
import hashlib
import json
import os
import pickle
import resource
import shutil
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from hf_execution_policy import POLICIES, run_policy_book

ROOT = Path.cwd()
P = Path(__file__).resolve().parent
ITER = ROOT / "reports/research/iterations/t20261014_hf_execution_value"
DISK_REFRESH_RESERVE_BYTES = 9_533_075_101


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resume_identity(row, bps, capital, input_manifest_path, neutral_path=None, code_paths=None):
    """Bind the complete execution definition and the actual matched exposure input."""
    if code_paths is None:
        import hf_accounts

        code_paths = {
            "policy": P / "hf_execution_policy.py",
            "cash_actions": Path(hf_accounts.__file__).resolve(),
            "producer": Path(__file__).resolve(),
        }
    if set(code_paths) != {"policy", "cash_actions", "producer"}:
        raise ValueError("Complete execution code dependency identity required")
    history, neutral = None, None
    is_neutral = row["kind"] == "causal_prior63session_exposure_control"
    if is_neutral != (neutral_path is not None):
        raise ValueError("Matched exposure input required exactly for neutral control")
    if is_neutral:
        body = neutral_path.read_bytes()
        matched = json.loads(body)
        matched_id = row["candidate_id"].replace("NEUTRAL_", "")
        if (
            matched.get("candidate_id") != matched_id
            or matched.get("initial") != capital
            or matched.get("cost_each_side") != bps / 10000
        ):
            raise ValueError("Matched exposure candidate/capital/cost mismatch")
        history = matched["daily_regular_exposure"]
        neutral = {
            "path": str(neutral_path.resolve()),
            "sha256": hashlib.sha256(body).hexdigest(),
            "matched_candidate_id": matched_id,
            "exposure_sha256": hashlib.sha256(
                json.dumps(history, sort_keys=True, allow_nan=False).encode()
            ).hexdigest(),
        }
    identity = {
        "candidate": row,
        "cost_bps": bps,
        "capital_USD": capital,
        "policy_configuration": asdict(POLICIES[row["policy"]["policy_id"]]),
        "inputs_sha256": file_digest(input_manifest_path),
        "execution_code": {
            name: {"path": str(path.resolve()), "sha256": file_digest(path)}
            for name, path in code_paths.items()
        },
        "matched_exposure_input": neutral,
    }
    return identity, history


def load_checkpoint(path, identity):
    with path.open("rb") as stream:
        saved = pickle.load(stream)
    if saved["identity"] != identity:
        raise ValueError("Same-definition native resume only: complete identity mismatch")
    return saved["state"]


def checkpoint_writer(checkpoint, identity):
    """Real producer callback: atomic durable publication on every completed day."""

    def save_checkpoint(state):
        temp = checkpoint.with_suffix(".tmp")
        with temp.open("wb") as stream:
            pickle.dump({"identity": identity, "state": state}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(checkpoint)
        directory = os.open(checkpoint.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    return save_checkpoint


def verify(row):
    path = ROOT / row["path"]
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != row["sha256"]:
        raise ValueError(f"Changed bound input: {path}")
    return path


def admission_blockers():
    state = json.loads((P / "current-state.json").read_text())
    blocked = []
    if state.get("economic_execution_admitted") is not True:
        blocked.append("Root_financial_launch_not_admitted")
    hold_path = ROOT / "reports/research/control/owner-compute-hold.json"
    if not hold_path.is_file():
        blocked.append("current_owner_compute_authority_missing")
    elif json.loads(hold_path.read_text()).get("research_paused") is not False:
        blocked.append("current_owner_compute_authority_not_active")
    if len(os.sched_getaffinity(0)) != 1:
        blocked.append("single_core_runtime_required")
    review_path = P / "independent-implementation-review.json"
    if not review_path.is_file():
        blocked.append("independent_implementation_review_missing")
    else:
        review = json.loads(review_path.read_text())
        if (
            review.get("verdict") != "approve_implementation"
            or not review.get("reviewer")
            or review.get("reviewer") == review.get("author")
        ):
            blocked.append("independent_implementation_review_not_approved")
        else:
            binding = next(
                (
                    b
                    for b in review.get("bindings", [])
                    if b["path"].endswith("/implementation-manifest.json")
                ),
                None,
            )
            if binding is None:
                blocked.append("implementation_review_manifest_not_bound")
            else:
                manifest = json.loads(verify(binding).read_text())
                for dependency in manifest["files"]:
                    verify(dependency)
                science = json.loads(verify(manifest["scientific_plan"]).read_text())
                verify(science["full_definition"])
                verify(science["candidate_manifest"])
    gate_path = P / "native-iteration-gate.json"
    if not gate_path.is_file():
        blocked.append("actual_native_iteration_gate_missing")
    else:
        gate = json.loads(gate_path.read_text())
        if gate.get("status") != "ok":
            blocked.append("actual_native_iteration_gate_not_ok")
        else:
            for row in gate["current_artifact_bindings"]:
                verify(row)
    if not blocked:
        from open_composer.research.iteration_dossier import validate_iteration_dossier

        actual = validate_iteration_dossier(ITER.name, ROOT, stage="pre-backtest")
        if actual.status != "ok":
            blocked.extend(actual.blocked)
    return blocked


def load_inputs():
    manifest = json.loads((P / "execution-input-manifest.json").read_text())
    for binding in manifest["actual_financial_read_inputs"]:
        verify(binding)
    packet = np.load(P / "execution-input-packets.npz")
    old = P.parent
    days = json.loads((old / "funded-SPY-clock-proposed.json").read_text())["rows"]
    bars = {}
    for year in range(2016, 2021):
        path = old / "market-input/cache-bridge" / f"SPY-raw15-aggregated-{year}.parquet"
        for row in pq.read_table(path, use_threads=False).to_pylist():
            day = str(row["date"].date()) if hasattr(row["date"], "date") else str(row["date"])
            bars.setdefault(day, {})[(row["window_minute"] - 570) // 15] = row
    raw_daily = json.loads(
        (old.parent / "primary-return-breadth/inputs/bars_raw-01.json").read_text()
    )["bars"]
    marks = {r["t"][:10]: r["c"] for r in raw_daily["SPY"]}
    actions = json.loads(
        (old / "market-input/cache-bridge/SPY-BIL-bound-actions.json").read_text()
    )["actions"]
    eligible = json.loads((old.parent / "primary-return-breadth/cash-calendar.json").read_text())[
        "eligible_dates"
    ]
    return days, bars, marks, actions, eligible, packet


def one_book(row, bps, inputs, output_dir):
    days, bars, marks, actions, eligible, packet = inputs
    qa = json.loads((P / "execution-input-QA.json").read_text())
    stream = row["stream"]
    col = qa["streams"].index(stream)
    scores = {
        (days[int(di)]["date"], int(minute)): float(score)
        for di, minute, score in zip(
            packet["day"], packet["minute"], packet["score"][:, col], strict=True
        )
    }
    identity = f"{row['candidate_id']}__{bps}__20k"
    result_path = output_dir / f"{identity}.json"
    checkpoint = output_dir / f"{identity}.checkpoint.pkl"
    if result_path.exists():
        raise ValueError("Completed book cannot be silently restarted")
    neutral_path = None
    if row["kind"] == "causal_prior63session_exposure_control":
        matched_id = row["candidate_id"].replace("NEUTRAL_", "")
        neutral_path = output_dir / f"{matched_id}__{bps}__20k.json"
    input_id, neutral_history = resume_identity(
        row, bps, 20000, P / "execution-input-manifest.json", neutral_path
    )
    resume = load_checkpoint(checkpoint, input_id) if checkpoint.exists() else None

    result = run_policy_book(
        days,
        bars,
        marks,
        scores,
        actions,
        eligible,
        POLICIES[row["policy"]["policy_id"]],
        row["anchor"],
        bps / 10000,
        exposure_history=neutral_history,
        resume_state=resume,
        on_complete_day=checkpoint_writer(checkpoint, input_id),
    )
    result["candidate_id"] = row["candidate_id"]
    result["input_identity"] = input_id
    temp = result_path.with_suffix(".tmp")
    temp.write_text(json.dumps(result, allow_nan=False) + "\n")
    temp.replace(result_path)
    returned = json.loads(result_path.read_text())
    assert len(returned["daily"]) == len(days) and returned["input_identity"] == input_id
    if checkpoint.exists():
        checkpoint.unlink()  # Verified completion only; interrupted points are retained.
    return identity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-admission", action="store_true")
    parser.add_argument("--first-book", action="store_true")
    args = parser.parse_args()
    if not args.check_admission:
        # Counts from process start, including imports/native/input guards;
        # five CPU seconds remain for the capped launcher inside the200 envelope.
        resource.setrlimit(resource.RLIMIT_CPU, (195, 196))
    blocked = admission_blockers()
    if args.check_admission:
        print(
            json.dumps(
                {"status": "blocked" if blocked else "ok", "blocked": blocked, "financial_runs": 0}
            )
        )
        return 0
    if blocked:
        raise RuntimeError("; ".join(blocked))
    ledger = json.loads((P / "cumulative-resource-ledger.json").read_text())
    charged = ledger["base_conservative_CPU"] + sum(
        r.get("charge_CPU", 0) for r in ledger["entries"]
    )
    allocation = json.loads((P / "root-plan-allocation-v1.json").read_text())
    remaining = allocation["package_cap_CPU"] - (
        charged - allocation["package_start_cumulative_CPU"]
    )
    if remaining <= 200:
        raise RuntimeError("Not enough original package CPU remains for first-book admission")
    if shutil.disk_usage(P).free < DISK_REFRESH_RESERVE_BYTES + 64 * 1024**2:
        raise RuntimeError("First book needs9533075101-byte refresh reserve plus64MiB output room")
    if not args.first_book:
        raise RuntimeError("Full batch requires measured first-book runtime allocation")
    row = next(
        row
        for row in json.loads((ITER / "candidate-manifest.json").read_text())["candidates"]
        if row["candidate_id"] == "DP_H16_SLOW__PLS_IDX_CTS__B0"
    )
    out = P / "economic"
    out.mkdir(exist_ok=True)
    identity = one_book(row, 20, load_inputs(), out)
    print(
        json.dumps({"completed_book": identity, "first_book_metrics_not_selected_or_printed": True})
    )


if __name__ == "__main__":
    main()
