"""Bound existing-input causal feature preparation. No economics or fits."""

import argparse
import gzip
import json
import pickle
import resource
import time
from collections import defaultdict
from datetime import UTC, timedelta
from pathlib import Path

from consumer_admission import (
    ROOT,
    P,
    bind,
    claim_launch,
    native_admission,
    phase_admission,
    settle,
    update,
    usage,
)


def generate_frames(job_id, *, child):
    started = time.process_time()
    row = phase_admission(job_id, "runtime", child=child, claim_runtime=not child)
    limit = int(row["runtime_CPU_upper"])
    assert limit > time.process_time() + 2
    resource.setrlimit(resource.RLIMIT_CPU, (limit - 2, limit - 1))
    import msgspec
    import pyarrow.parquet as pq
    from decision_system import read_parameters
    from frame_producer import NEW_YORK, SYMBOLS, FrameProducer

    input_path = P / "complete-input-v2-result.json"
    inputs = json.loads(input_path.read_text())
    spec = ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml"
    job = dict(
        input_result=bind(input_path),
        spec=bind(spec),
        files=[
            bind(Path(__file__).resolve()),
            bind(P / "code/frame_producer.py"),
            bind(P / "code/context_producer.py"),
            bind(P / "code/geometry.py"),
            bind(P / "code/consumer_admission.py"),
        ],
        science_review=bind(P / "revisions/r1/independent-review.json"),
        CPU_upper=limit,
        reservation_id=job_id,
        prospective_phase="runtime",
        review=bind(P / "consumer-independent-review.json"),
        prefix_semantic_verification=bind(P / "causal-hygiene-verification.json"),
        CPUs=1,
        memory_MiB=900,
        HTTP=0,
        fit=0,
        PnL=0,
        declaration="Sourcecontext fields only; no order evaluation or market execution",
    )
    prefixes = json.loads((P / "frame-prefix-inspection.json").read_text())
    reusable = {
        Path(r["path"]).name: bind(ROOT / r["path"])
        for r in prefixes
        if r["status"] == "gzip_complete"
    }
    for b in json.loads((P / "inputs/frames-v2/completed-shards.json").read_text()):
        assert bind(ROOT / b["path"]) == b
        reusable[Path(b["path"]).name] = b
    job["completed_prefixes"] = list(reusable.values())
    job["old_failed_resource_bindings"] = [
        bind(P / "frame-preparation-resource.txt"),
        bind(P / "frame-preparation-resume-resource.txt"),
    ]
    job["same_semantics_change"] = (
        "Avoid immutable timestamp deepcopy; replay context of completed prefixes "
        "without rewriting them"
    )
    (P / "frame-preparation-resume3-manifest.json").write_text(json.dumps(job, indent=2) + "\n")
    for b in inputs["auxiliary_outputs"]:
        assert bind(ROOT / b["path"]) == b
    daily = json.loads((P / "inputs/full-v1/daily-basis.json").read_text())
    actions = json.loads((P / "inputs/full-v1/actions.json").read_text())
    indexes = pq.read_table(P / "inputs/full-v1/indexes.parquet").to_pylist()
    producer = FrameProducer(read_parameters(spec), daily, indexes, actions)
    out = P / "inputs/frames-v3"
    out.mkdir(parents=True, exist_ok=False)
    outputs = []
    frame_count = 0
    calendar_minutes = 0
    missing_count = 0
    trigger_masks = {}
    for b in inputs["outputs"]:
        path = ROOT / b["path"]
        assert bind(path) == b
        records = pq.read_table(path).to_pylist()
        byday = defaultdict(lambda: defaultdict(dict))
        for r in records:
            t = r["timestamp"].astimezone(UTC)
            r["timestamp"] = t
            byday[t.astimezone(NEW_YORK).date()][t][r["symbol"]] = r
        year, month = map(int, path.stem.split("-"))
        dates = [d for d in producer.calendar if d.year == year and d.month == month]
        dest = out / (path.stem + ".jsonl.gz")
        reuse = reusable.get(dest.name)
        if reuse is not None:
            assert bind(ROOT / reuse["path"]) == reuse
            for day in dates:
                producer.begin_session(day)
                n = int((producer.close - producer.open).total_seconds() / 60)
                for minute in range(n):
                    t = producer.open + timedelta(minutes=minute)
                    producer.complete_minute(minute, byday[day].get(t, {}), serialize=False)
                trigger_masks[str(day)] = {
                    s: False for s in SYMBOLS if not producer.trigger_eligible[s]
                }
            outputs.append(reuse)
            print(
                json.dumps(dict(month=path.stem, reused=True, CPU=time.process_time() - started)),
                flush=True,
            )
            continue
        with gzip.open(dest, "wb", compresslevel=1) as stream:
            for day in dates:
                events = producer.begin_session(day)
                n = int((producer.close - producer.open).total_seconds() / 60)
                for minute in range(n):
                    t = producer.open + timedelta(minutes=minute)
                    row = byday[day].get(t, {})
                    frames = producer.complete_minute(minute, row)
                    missing = [s for s in SYMBOLS if s not in row]
                    packet = dict(
                        start=t.isoformat(),
                        session=str(day),
                        ordinal=producer.session,
                        minute=minute,
                        session_minutes=n,
                        actions=events if minute == 0 else [],
                        missing=missing,
                        prices=list(row.values()),
                        frames=frames,
                    )
                    stream.write(
                        msgspec.json.encode(packet, enc_hook=lambda x: x.isoformat()) + b"\n"
                    )
                    frame_count += len(frames)
                    calendar_minutes += 1
                    missing_count += len(missing)
                trigger_masks[str(day)] = {
                    s: False for s in SYMBOLS if not producer.trigger_eligible[s]
                }
        outputs.append(bind(dest))
        print(
            json.dumps(dict(month=path.stem, reused=False, CPU=time.process_time() - started)),
            flush=True,
        )
        (out / "completed-shards.json").write_text(json.dumps(outputs, indent=2) + "\n")
        with (out / "last-complete-producer.pkl").open("wb") as handle:
            pickle.dump(producer, handle, protocol=5)
    result = dict(
        manifest=bind(P / "frame-preparation-resume3-manifest.json"),
        outputs=outputs,
        trigger_masks=trigger_masks,
        trigger_mask_availability=(
            "Known split at actions; source opening ratio at actual09:30 "
            "minute only. Applied to entry eligibility, never holding out"
            "comes."
        ),
        frames=frame_count,
        calendar_minutes=calendar_minutes,
        missing_symbol_minutes=missing_count,
        qa=dict(producer.qa),
        HTTP=0,
        fit=0,
        PnL=0,
        policy_evaluations=0,
        counters_scope=(
            "New output shards only; reused complete prefix counters "
            "reconciled independently before result interpretation"
        ),
        CPU=time.process_time() - started,
        RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    (P / "frame-preparation-result.json").write_text(json.dumps(result, indent=2) + "\n")
    update(job_id, frame_result=bind(P / "frame-preparation-result.json"))
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("frames", "calendar_minutes", "missing_symbol_minutes", "qa", "CPU")
            }
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--economic-inline", action="store_true", required=True)
    parser.add_argument("--reservation-id", required=True)
    parser.add_argument("--standalone", action="store_true")
    args = parser.parse_args()
    args.job_id = args.reservation_id
    if not args.standalone:
        generate_frames(args.reservation_id, child=True)
        return
    claim_launch(args.job_id, "frames")
    outcome = "failed"
    runtime_started = None
    try:
        native_admission(args.job_id)
        runtime_started = usage()[0]
        generate_frames(args.job_id, child=False)
        outcome = "runtime_complete_no_account_cells"
    finally:
        if runtime_started is not None:
            update(args.job_id, runtime_actual_CPU=usage()[0] - runtime_started)
        settle(args.job_id, outcome)


if __name__ == "__main__":
    main()
