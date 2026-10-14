"""Fail-closed driver for reviewed continuous cells. No autonomous launch."""

import argparse
import gzip
import json
import subprocess
import time
from collections import Counter

import msgspec
from consumer_admission import (
    ROOT,
    P,
    bind,
    claim_launch,
    empirical_limit,
    empirical_remaining,
    native_admission,
    phase_admission,
    settle,
    update,
    usage,
    verified_frames,
)


def flush(strategy, folder, key, counters):
    with gzip.open(folder / (key + "-audit.jsonl.gz"), "wb", compresslevel=1) as f:
        for r in strategy.audit:
            counters[r["action"]] += 1
            f.write(msgspec.json.encode(r) + b"\n")
    strategy.audit.clear()
    with gzip.open(folder / (key + "-NAV.jsonl.gz"), "wb", compresslevel=1) as f:
        for r in strategy.snapshots:
            f.write(msgspec.json.encode(r) + b"\n")
    strategy.snapshots.clear()
    with gzip.open(folder / (key + "-policy.jsonl.gz"), "wb", compresslevel=1) as f:
        for symbol, state in strategy.policy.states.items():
            for r in state.audit:
                counters["policy:" + r.get("reason", "execution_report")] += 1
                f.write(msgspec.json.encode(dict(symbol=symbol, **r)) + b"\n")
            state.audit.clear()


def account_report(
    cell,
    engine,
    strategy,
    counts,
    input_minutes,
    complete,
    CPU,
    last_source_boundary,
    largest_interval_CPU,
):
    return dict(
        cell=cell,
        status="budget_incomplete"
        if not complete
        else "conditional_complete"
        if not strategy.book.path_unknown
        else "unknown_continuous_path",
        unknown_reasons=strategy.book.unknown_reasons,
        counts=dict(counts),
        input_minutes=input_minutes,
        actual_native_orders=len(engine.cache.orders()),
        first_unknown=strategy.book.first_unknown,
        known_prefix_closed_attempt_R=list(strategy.book.closed_R),
        closed_attempt_R=None
        if strategy.book.path_unknown or not complete
        else list(strategy.book.closed_R),
        open_positions=None
        if strategy.book.path_unknown or not complete
        else [
            dict(symbol=p.instrument_id.symbol.value, native_units=p.quantity.as_double())
            for p in engine.cache.positions_open()
        ],
        uninterpretable_native_diagnostics=dict(
            event_counts=dict(strategy.uninterpretable_counts),
            positions_at_engine_end=[
                dict(symbol=p.instrument_id.symbol.value, native_units=p.quantity.as_double())
                for p in engine.cache.positions_open()
            ],
            economic_interpretation=False,
        )
        if strategy.book.path_unknown
        else None,
        terminal_cash=None if strategy.book.path_unknown or not complete else strategy._cash(),
        terminal_equity=None
        if strategy.book.path_unknown or not complete
        else strategy._view()[0].equity,
        last_known_account=strategy.last_known_snapshot,
        remainder_after_first_unknown=(
            "NA; later native events quarantined, later source months unexecuted"
        )
        if strategy.book.path_unknown
        else None,
        terminal_liquidation=False,
        source_vintage="current_conditional",
        raw_exact_certified=False,
        promotion_eligible=False,
        paper_ready_pass=False,
        CPU=CPU,
        annual_views=["2024", "2025"],
        scenario_not_global_NAV_bound=True,
        full_source_clock_complete=complete and not strategy.book.path_unknown,
        last_source_boundary=last_source_boundary,
        largest_interval_CPU=largest_interval_CPU,
        native_checkpoint_available=False,
        incomplete_recovery=(
            "Completed source Frames reused; account retry must replay "
            "same definition with charged physical exposure"
        )
        if not complete
        else None,
    )


def run_cell(cell, frames, folder, bindings, *, remaining=None):
    from decision_system import read_parameters
    from native_engine import make_engine
    from native_events import causal_activity, native_month, source_intervals
    from nautilus_trader.model.identifiers import ClientId

    started = time.process_time()
    factors = {"SMCI": 0.1}
    engine, strategy = make_engine(
        read_parameters(ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml"),
        cell["candidate"],
        cell["route"],
        cell["cost_bps_per_side"],
        dict(bindings, cell=cell["cell_id"]),
        factors,
    )
    counts = Counter()
    input_minutes = 0
    complete = True
    largest_interval_CPU = 0.0
    last_source_boundary = None
    try:
        for b in frames["outputs"]:
            path = ROOT / b["path"]
            if path.name.startswith("2023-"):
                continue  # Feature warmup, no economic account clock.
            assert bind(path) == b
            with gzip.open(path, "rb") as stream:
                packets = [msgspec.json.decode(line) for line in stream]
            for interval, afternoon in source_intervals(
                packets, strategy.config.parameters["entry_cutoff_minute"]
            ):
                if remaining and remaining() < max(25, 2 * largest_interval_CPU + 12):
                    complete = False
                    break
                t = time.process_time()
                active = causal_activity(strategy, interval[0], afternoon=afternoon)
                strategy.runtime_active_symbols = active
                books, quotes, boundaries, factors = native_month(
                    interval,
                    cell["scenario"],
                    factors,
                    frames["trigger_masks"],
                    active_symbols=active,
                )
                if books:
                    engine.add_data(books)
                if quotes:
                    engine.add_data(quotes)
                engine.add_data(boundaries, client_id=ClientId("MARTIN"))
                del books, quotes, boundaries
                engine.run(streaming=True)
                engine.clear_data()
                input_minutes += len(interval)
                last_source_boundary = dict(
                    session=interval[-1]["session"], minute=interval[-1]["minute"]
                )
                largest_interval_CPU = max(largest_interval_CPU, time.process_time() - t)
                if strategy.book.path_unknown:
                    break
            del packets
            flush(strategy, folder, path.name[:7], counts)
            print(
                json.dumps(
                    dict(
                        cell_id=cell["cell_id"],
                        month=path.name[:7],
                        CPU=time.process_time() - started,
                        unknown=strategy.book.path_unknown,
                    )
                ),
                flush=True,
            )
            if strategy.book.path_unknown or not complete:
                # Contract makes the joint remainder irreversibly unknown.
                # Do not spend on fictitious later NAV or heal at the next file.
                break
        engine.end()
        report = account_report(
            cell,
            engine,
            strategy,
            counts,
            input_minutes,
            complete,
            time.process_time() - started,
            last_source_boundary,
            largest_interval_CPU,
        )
        (folder / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cells", nargs="+", required=True)
    parser.add_argument("--reservation-id", required=True)
    parser.add_argument("--same-definition-recovery", action="store_true")
    parser.add_argument("--technical-feed-probe", action="store_true")
    parser.add_argument("--shared-block", action="store_true")
    args = parser.parse_args()
    args.job_id = args.reservation_id
    row = claim_launch(args.job_id, "consumer")
    assert row["cells"] == args.cells
    manifest = json.loads((P / "consumer-cases.json").read_text())
    outcome = "failed"
    uncertain_child = False
    try:
        row = native_admission(args.job_id)
        if not (P / "frame-preparation-result.json").exists():
            phase_admission(args.job_id, "runtime")
            before = usage()[1]
            uncertain_child = True
            generated = subprocess.run(
                [
                    str(ROOT / ".venv/bin/python"),
                    str(P / "code/prepare_frames.py"),
                    "--economic-inline",
                    "--reservation-id",
                    args.job_id,
                ],
                check=False,
            )
            uncertain_child = False
            runtime_actual = usage()[1] - before
            update(
                args.job_id,
                runtime_actual_CPU=runtime_actual,
                runtime_returncode=generated.returncode,
            )
            assert generated.returncode == 0, "Feature phase incomplete; no account cell started"
        frames = verified_frames()  # File existence alone never admits reuse.
        phase_admission(args.job_id, "empirical")
        empirical_limit(args.job_id)
        out = P / "economic-results"
        out.mkdir(exist_ok=True)
        ledger = out / "trial-ledger.jsonl"
        bindings = dict(
            spec=bind(ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml")[
                "sha256"
            ],
            input=bind(P / "frame-preparation-result.json")["sha256"],
            contract=bind(P / "revisions/r1/event-book-contract.json")["sha256"],
        )
        if args.technical_feed_probe:
            from profile_native_feed import probe

            probe(args.job_id, frames, bindings)
            outcome = "technical_feed_probe_complete"
            return
        if args.shared_block:
            from native_shared_feed import run_block

            cells = [
                next(c for c in manifest["cells"] if c["cell_id"] == cid) for cid in args.cells
            ]
            assert 1 < len(cells) <= 2 and len({c["scenario"] for c in cells}) == 1
            folders = {}
            for cid in args.cells:
                folder = out / cid
                recovering = folder.exists()
                if recovering:
                    assert args.same_definition_recovery and not (folder / "result.json").exists()
                    assert cid == "P_SYSTEM__market__20bps__O-H-L-C"
                    archived = out / "interrupted-first-SIGXCPU" / cid
                    archived.parent.mkdir(exist_ok=True)
                    assert not archived.exists()
                    folder.rename(archived)
                folder.mkdir(exist_ok=False)
                folders[cid] = folder
                with ledger.open("a") as f:
                    f.write(
                        json.dumps(
                            dict(
                                cell_id=cid,
                                status="started",
                                reservation_id=args.job_id,
                                admission=bind(P / "consumer-independent-review.json"),
                                same_definition_recovery=recovering,
                                shared_block=args.cells,
                            )
                        )
                        + "\n"
                    )
            reports = run_block(
                cells, frames, folders, bindings, remaining=lambda: empirical_remaining(args.job_id)
            )
            for cid, report in reports.items():
                with ledger.open("a") as f:
                    f.write(
                        json.dumps(
                            dict(
                                cell_id=cid,
                                status=report["status"],
                                report=bind(folders[cid] / "result.json"),
                            )
                        )
                        + "\n"
                    )
            outcome = (
                "budget_incomplete"
                if any(r["status"] == "budget_incomplete" for r in reports.values())
                else "batch_complete"
            )
            return
        for cid in args.cells:
            # Fresh authority/bindings/current native and original commitments
            # are rechecked at each existing phase boundary, never per-card Root.
            phase_admission(args.job_id, "empirical")
            empirical_limit(args.job_id)
            folder = out / cid
            recovering = folder.exists()
            if folder.exists():
                assert args.same_definition_recovery
                assert not (folder / "result.json").exists(), "completed cell is never repeated"
                assert cid == "P_SYSTEM__market__20bps__O-H-L-C", "only evidenced interrupted cell"
                archived = out / "interrupted-first-SIGXCPU" / cid
                archived.parent.mkdir(exist_ok=True)
                assert not archived.exists()
                folder.rename(archived)
            folder.mkdir(exist_ok=False)
            cell = next(c for c in manifest["cells"] if c["cell_id"] == cid)
            with ledger.open("a") as f:
                f.write(
                    json.dumps(
                        dict(
                            cell_id=cid,
                            status="started",
                            reservation_id=args.job_id,
                            admission=bind(P / "consumer-independent-review.json"),
                            same_definition_recovery=recovering,
                            new_selectable_definition=False,
                        )
                    )
                    + "\n"
                )
            report = run_cell(
                cell, frames, folder, bindings, remaining=lambda: empirical_remaining(args.job_id)
            )
            with ledger.open("a") as f:
                f.write(
                    json.dumps(
                        dict(
                            cell_id=cid,
                            status=report["status"],
                            report=bind(folder / "result.json"),
                        )
                    )
                    + "\n"
                )
            (out / "batch-current.json").write_text(
                json.dumps(
                    dict(
                        native=row.get("native"),
                        last_cell=cid,
                        reservation_id=args.job_id,
                        own_and_child_CPU=usage(),
                    ),
                    indent=2,
                )
                + "\n"
            )
            if report["status"] == "budget_incomplete":
                outcome = "budget_incomplete"
                break
        else:
            outcome = "batch_complete"
        print(json.dumps(dict(status=outcome, own_and_child_CPU=usage())))
    finally:
        if uncertain_child:
            update(args.job_id, status="unknown_child_usage", outcome="interrupted")
        else:
            settle(args.job_id, outcome)


if __name__ == "__main__":
    main()
