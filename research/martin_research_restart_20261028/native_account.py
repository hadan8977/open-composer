# ruff: noqa: I001
# common must install immutable research import paths before legacy imports.
"""Q1 component driver adapted from received native_accounts.py; matching stays native."""

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path
import csv
import json
import os
import resource
import time
import numpy as np
import pandas as pd
from common import (
    OUT,
    SEQ,
    INPUTS,
    F1,
    gate,
    save,
    stamp,
    digest,
    active_parameters,
    verified_source,
    verify_notices,
)
from native_factory import make_engine
from source_envelope import source_envelope
from execution_feed_v3 import SavedInputs, execution_packets, native_interval
from source_feed_recovery01 import management_boundary
from native_events import source_intervals, causal_activity
from nautilus_trader.model.identifiers import ClientId
from open_composer.market_sessions import us_equity_session_dates


def run_cell(arm, native_output):
    gate(new_start=True, financial=True)
    assert arm in ("B", "R")
    cell = "2024Q1-" + arm
    folder = Path(native_output).resolve()
    assert folder.is_relative_to(OUT / "native-runs")
    assert not folder.exists(), "Retain all actual attempts; do not overwrite a failed account"
    verify_notices()
    folder.mkdir(parents=True)
    start = time.monotonic()
    cpu = time.process_time()
    process = dict(
        pid=os.getpid(), started_at_utc=stamp(), status="running_not_accepted", cell=cell
    )
    save(folder / "process.json", process)
    names = json.loads((F1 / "universe.json").read_text())["symbols"]
    contexts = pd.read_parquet(verified_source(SEQ / "daily-context.parquet"))
    ctx = {(r["symbol"], r["day"]): r for r in contexts.to_dict("records")}
    daily = np.load(verified_source(SEQ / "daily-ohlcv-60.npy"), mmap_mode="r")
    startday = date(2024, 1, 2)
    endday = date(2024, 3, 28)
    dates = us_equity_session_dates(startday, endday)
    ordinals = {str(d): i for i, d in enumerate(dates)}
    parameters = active_parameters(arm)
    engine, strategy = make_engine(
        names,
        parameters,
        dict(
            spec=digest(OUT / f"StrategySpec-{arm}.yaml"),
            input=digest(INPUTS / "manifest.json"),
            contract=digest(OUT / "protocol.md"),
            cell="observed-" + cell,
        ),
    )
    strategy.context = ctx
    strategy.daily_sequences = daily
    strategy.session_ordinals = ordinals
    strategy.arm = "R"  # Existing always-A behavior; B/R are component identities only.
    strategy.policy.arm = arm
    saved = SavedInputs(INPUTS)
    counts = Counter()
    coverage = []
    nav = []
    month = None
    bars = None
    peak = 20000.0
    worst_dd = 0.0
    sum_exposure = 0.0
    sample_count = 0
    missing_mark_samples = 0
    observed_close_peak = 20000.0
    observed_underwater = 0
    max_observed_underwater = 0
    writerfile = (folder / "minute-account.csv").open("x")
    writer = csv.DictWriter(
        writerfile,
        fieldnames=[
            "native_ns",
            "day",
            "equity",
            "cash",
            "gross",
            "all_positive_holdings_current",
            "held_mark_witness",
        ],
    )
    writer.writeheader()
    try:
        for day in dates:
            gate()
            key = (day.year, day.month)
            if key != month:
                bars = pd.read_parquet(
                    verified_source(SEQ / "minute-months" / f"{day.year}-{day.month:02}.parquet")
                )
                bars["NYday"] = bars.timestamp.dt.tz_convert("America/New_York").dt.date
                month = key
            packets, events, qa = execution_packets(
                day, bars.loc[bars.NYday == day], ctx, names, ordinals[str(day)], saved
            )
            strategy.source_event_envelope = source_envelope(packets)
            strategy.input_events.clear()
            strategy.input_events.update(events)
            strategy.source_minutes = {
                (r["symbol"], pd.Timestamp(p["start"]).value // 60_000_000_000)
                for p in packets
                for r in p["prices"]
            }
            coverage.append(dict(day=str(day), symbols=qa))
            # Known previous daily close/age is processed at actual 09:29 before today's quote.
            engine.add_data(
                [management_boundary(day, ordinals[str(day)])], client_id=ClientId("MARTIN")
            )
            for interval, afternoon in source_intervals(packets, parameters["entry_cutoff_minute"]):
                active = (
                    causal_activity(strategy, interval[0], afternoon=True)
                    if afternoon
                    else set(names)
                )
                strategy.runtime_active_symbols = active
                books, quotes, boundaries = native_interval(interval, active)
                if afternoon and day == dates[-1]:
                    boundaries.append(management_boundary(day, ordinals[str(day)], terminal=True))
                if books:
                    engine.add_data(books)
                if quotes:
                    engine.add_data(quotes)
                engine.add_data(boundaries, client_id=ClientId("MARTIN"))
                del books, quotes, boundaries
                engine.run(streaming=True)
                engine.clear_data()
                if strategy.book.path_unknown:
                    break
            for snap in strategy.snapshots:
                gross = sum(
                    q * snap["prices"].get(s, 0) for s, q in snap["quantities"].items() if q
                )
                writer.writerow(
                    dict(
                        native_ns=snap["at_ns"],
                        day=str(day),
                        equity=snap["equity"],
                        cash=snap["cash"],
                        gross=gross,
                        held_mark_witness=json.dumps(snap["received_mark_valuation"]["held"]),
                        all_positive_holdings_current=snap["received_mark_valuation"][
                            "all_positive_holdings_current"
                        ],
                    )
                )
                if snap["received_mark_valuation"]["all_positive_holdings_current"]:
                    peak = max(peak, snap["equity"])
                    worst_dd = min(worst_dd, 100 * (snap["equity"] / peak - 1))
                    sum_exposure += gross / snap["equity"]
                    sample_count += 1
                else:
                    missing_mark_samples += 1
            closing_observation = strategy.snapshots[-1] if strategy.snapshots else None
            writerfile.flush()
            with (folder / "audit.jsonl").open("a") as stream:
                for row in strategy.audit:
                    counts[row["action"]] += 1
                    stream.write(json.dumps(row, default=str) + "\n")
            with (folder / "policy-audit.jsonl").open("a") as stream:
                for symbol, state in strategy.policy.states.items():
                    for row in state.audit:
                        stream.write(json.dumps(dict(symbol=symbol, **row), default=str) + "\n")
                    state.audit.clear()
            strategy.audit.clear()
            strategy.snapshots.clear()
            if strategy.book.path_unknown:
                break
            view, _ = strategy._view()
            nav.append(
                dict(
                    day=str(day),
                    equity=view.equity,
                    cash=strategy._cash(),
                    gross=view.gross_notional,
                    all_positive_holdings_current=closing_observation["received_mark_valuation"][
                        "all_positive_holdings_current"
                    ]
                    if closing_observation
                    else False,
                )
            )
            if nav[-1]["all_positive_holdings_current"]:
                observed_close_peak = max(observed_close_peak, view.equity)
                observed_underwater = (
                    observed_underwater + 1 if view.equity < observed_close_peak else 0
                )
                max_observed_underwater = max(max_observed_underwater, observed_underwater)
            save(
                folder / "checkpoint.json",
                dict(
                    pid=os.getpid(),
                    last_day=str(day),
                    status="partial_not_serialized_engine",
                    cash=strategy._cash(),
                    positions={
                        s: st.quantity for s, st in strategy.policy.states.items() if st.quantity
                    },
                    pending={k: asdict(v) for k, v in strategy.book.reserved.items()},
                ),
            )
            # Keep completed label/proposal evidence durable without creating hypothetical labels.
            save(folder / "completed-labels.json", strategy.completed_labels)
            save(folder / "proposals.json", strategy.policy.proposals)
            save(
                folder / "proposal-inputs.json",
                [
                    dict(symbol=k[0], decision_time=k[1], **v)
                    for k, v in strategy.proposal_payloads.items()
                ],
            )
            if len(nav) % 25 == 0:
                print(cell, day, len(nav), round(strategy._cash(), 2), flush=True)
        engine.end()
        for name, value in [
            ("funding-events", strategy.funding_events),
            ("observation-gaps", strategy.observation_gaps),
            ("submission-valuations", strategy.submission_valuations),
            ("decision-events", strategy.policy.decision_events),
            ("actual-stop-nanoseconds", strategy.policy.last_stop_ns),
            ("execution-source-events", strategy.execution_source_events),
            ("native-intents", {k: asdict(v) for k, v in strategy.native_intents.items()}),
            ("signals", strategy.policy.signals),
            ("management-events", strategy.management_events),
            ("completed-labels", strategy.completed_labels),
            ("proposals", strategy.policy.proposals),
            ("open-events", strategy.open_events),
            ("coverage", coverage),
            (
                "proposal-inputs",
                [
                    dict(symbol=k[0], decision_time=k[1], **v)
                    for k, v in strategy.proposal_payloads.items()
                ],
            ),
        ]:
            save(folder / (name + ".json"), value)
        pd.DataFrame(nav).to_csv(folder / "equity.csv", index=False)
        pd.DataFrame(strategy.closed_trades).to_csv(folder / "trades.csv", index=False)
        positions = [
            dict(symbol=p.instrument_id.symbol.value, quantity=p.quantity.as_double())
            for p in engine.cache.positions_open()
        ]
        orders = [
            dict(id=str(o.client_order_id), status=str(o.status))
            for o in engine.cache.orders_open()
        ]
        complete = (
            not positions
            and not orders
            and len(nav) == len(dates)
            and not strategy.book.reserved
            and not strategy.book.path_unknown
        )
        cash = strategy._cash()
        events = strategy.execution_source_events
        fees = sum(e["fee"] for e in events)
        raw_cashflow_net = sum(
            (1 if e["action"] != "buy" else -1) * e["quantity"] * e["price"] - e["fee"]
            for e in events
        )
        result = dict(
            cell=cell,
            arm=arm,
            status="complete_observed_conditional" if complete else "incomplete",
            native_cash=cash,
            net_dollars=cash - 20000 if complete else None,
            return_pct=(cash / 20000 - 1) * 100 if complete else None,
            fees=fees,
            fixed_fill_gross_dollars=raw_cashflow_net + fees if complete else None,
            native_cent_cash_gross_dollars=cash - 20000 + fees if complete else None,
            native_cent_vs_raw_cashflow_residual_dollars=cash - 20000 - raw_cashflow_net,
            unsettled=list(strategy.book.unsettled),
            waits={k: asdict(v) for k, v in strategy.policy.waits.items()},
            observed_minute_drawdown_pct=worst_dd,
            mean_observed_gross=sum_exposure / sample_count if sample_count else 0,
            observed_samples=sample_count,
            stale_inclusive_mark_samples=missing_mark_samples,
            missing_daily_closing_observations=sum(
                not r["all_positive_holdings_current"] for r in nav
            ),
            max_observed_close_underwater_observations=max_observed_underwater,
            physical_continuous_drawdown_identified=False,
            active_gap_count=len(strategy.observation_gaps),
            positive_fills_without_actual_freshness=sum(
                e["quantity"] > 0 and not e["source_event_freshness"]["fresh"] for e in events
            ),
            calendar_sessions=len(dates),
            observed_account_days=len(nav),
            closed_labels=len(strategy.completed_labels),
            proposals=len(strategy.policy.proposals),
            buy_intents=len(strategy.policy.signals),
            open_positions=positions,
            open_orders=orders,
            reservations={k: asdict(v) for k, v in strategy.book.reserved.items()},
            unknown_reasons=strategy.book.unknown_reasons,
            missing_active_minutes=strategy.omitted_active_minutes,
            retained_book_fills=sum(e["retained_book_execution"] for e in events),
            native_counts=dict(counts),
            raw_cashflow_net=raw_cashflow_net,
            closed_net=sum(r["native_net"] for r in strategy.completed_labels),
            cpu_core_s=time.process_time() - cpu,
            wall_s=time.monotonic() - start,
            maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        )
        save(folder / "result.json", result)
        process.update(status=result["status"], finished_at_utc=stamp())
        save(folder / "process.json", process)
        print(json.dumps(result), flush=True)
        return result
    finally:
        writerfile.close()
        engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--arm", required=True, choices=("B", "R"))
    p.add_argument("--native-output", required=True)
    args = p.parse_args()
    run_cell(args.arm, args.native_output)
