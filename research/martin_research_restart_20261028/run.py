"""Two actual sequential native accounts; lab writes results and durable exposure."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from common import INPUTS, OUT, ROOT, SEQ, active_parameters, digest, gate, save, stamp

DIRECTION = OUT.name
PRIOR = "martin-known-financial-starts-through-20261027"
INITIAL = 20000.0


def check_inputs():
    """Metadata/code checks only; no prices, labels, fitted model or financial run."""
    evidence = json.loads((OUT / "evidence.json").read_text())
    missing = [r["path"] for r in evidence["bindings"] if not (ROOT / r["path"]).is_file()]
    if missing:
        raise FileNotFoundError(missing)
    for row in evidence["bindings"]:
        if digest(ROOT / row["path"]) != row["sha256"]:
            raise ValueError(f"Changed accepted dependency: {row['path']}")
    baseline, repeat = active_parameters("B"), active_parameters("R")
    assert baseline.pop("attempts_per_day") == 1
    assert repeat.pop("attempts_per_day") == 3
    assert baseline == repeat
    source = json.loads((SEQ / "input-manifest.json").read_text())
    minute_paths = [SEQ / "minute-months" / f"2024-{month:02}.parquet" for month in (1, 2, 3)]
    for path in [*minute_paths, SEQ / "daily-context.parquet", SEQ / "daily-ohlcv-60.npy"]:
        row = next(r for r in source["bindings"] if Path(r["path"]).resolve() == path)
        assert path.is_file() and path.stat().st_size == row["bytes"]
    for month in ("2024-01", "2024-02", "2024-03"):
        assert (INPUTS / month / "notices.jsonl").is_file()
    return {
        "status": "input_metadata_ready_not_financial_evidence",
        "brief_bytes": (OUT / "brief.md").stat().st_size,
        "frozen_calendar": evidence["calendar"],
        "data_array_bytes_read": 0,
        "existing_text_bindings_checked": len(evidence["bindings"]),
        "financial_runs": 0,
        "fits": 0,
    }


def native_account(arm, folder, deadline):
    import pandas as pd

    from open_composer.lab import EngineResult

    gate(new_start=True, financial=True)
    folder.parent.mkdir(parents=True, exist_ok=True)
    log = folder.parent / f"{arm}.log"
    launch = folder.parent / f"{arm}-launch.json"
    command = [
        sys.executable,
        str(OUT / "native_account.py"),
        "--arm",
        arm,
        "--native-output",
        str(folder),
    ]
    save(launch, {"status": "starting", "at": stamp(), "command": command})
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Frozen outer runtime boundary reached before next account")
    try:
        with log.open("x") as stream:
            process = subprocess.run(
                command,
                cwd=ROOT,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=remaining,
                check=False,
            )
        save(
            launch,
            {
                "status": "exited",
                "at": stamp(),
                "command": command,
                "returncode": process.returncode,
            },
        )
    except BaseException as exc:
        save(
            launch,
            {
                "status": "interrupted",
                "at": stamp(),
                "command": command,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "partial_native_folder": str(folder.relative_to(ROOT)),
            },
        )
        raise
    if process.returncode:
        raise RuntimeError(f"Actual native {arm} failed; inspect {log.relative_to(ROOT)}")
    native = json.loads((folder / "result.json").read_text())
    if native["status"] != "complete_observed_conditional":
        raise RuntimeError(f"Native {arm} is incomplete; retain {folder.relative_to(ROOT)}")
    if native["positive_fills_without_actual_freshness"] or native["retained_book_fills"]:
        raise ValueError("Native account has positive stale/retained-book fills")
    events = json.loads((folder / "execution-source-events.json").read_text())
    # Native fee/cash ledgers remain primary. This checks, rather than simulates, them.
    flow = sum(
        ((-1 if e["action"] == "buy" else 1) * e["quantity"] * e["price"] - e["fee"])
        for e in events
    )
    positive = [e for e in events if e["quantity"] > 0]
    residual = native["native_cash"] - INITIAL - flow
    tolerance = 0.011 * len(positive) + 1e-6
    if abs(residual) > tolerance:
        raise ValueError("Cashflow residual exceeds per-callback cent rounding bound")
    equity = pd.read_csv(folder / "equity.csv", parse_dates=["day"]).set_index("day")["equity"]
    returns = equity.div(equity.shift(fill_value=INITIAL)).sub(1)
    return EngineResult(
        engine="existing Martin ObservedEngine/NautilusTrader 1.219.0",
        initial_equity_usd=INITIAL,
        end_equity_usd=native["native_cash"],
        native=native,
        ledger=pd.DataFrame(events),
        net_returns=returns,
        limitations=[
            "Seen static29-security development cohort; no PIT/unseen-market inference",
            "Synthetic adjusted O-L-H-C received-tape economics; physical missing paths unknown",
            "Session returns carry received native marks; "
            "see observed-minute drawdown and gap diagnostics",
            "10bp/side is a research cost assumption, not measured executable broker friction",
            "Reentry cap counts submitted intents; repeated nonfilled attempts can also differ",
            "No model fitted; the full 8666-root learning objective remains open",
        ],
        metadata={
            "native_folder": str(folder.relative_to(ROOT)),
            "arm": arm,
            "spec": str((OUT / f"StrategySpec-{arm}.yaml").relative_to(ROOT)),
            "cashflow_residual": residual,
            "cent_rounding_bound": tolerance,
            "calendar": ["2024-01-02", "2024-03-28"],
            "exposure": "seen/development",
        },
    )


def attempt_attribution(folder):
    """Classify actual native outcomes; never assign hypothetical absent-trade PnL."""
    import pandas as pd

    labels = json.loads((folder / "completed-labels.json").read_text())
    proposals = json.loads((folder / "proposals.json").read_text())
    events = json.loads((folder / "execution-source-events.json").read_text())
    intents, by_key = {}, {}
    for proposal in proposals:
        if proposal.get("admitted"):
            key = (proposal["symbol"], proposal["day"])
            by_key[key] = by_key.get(key, 0) + 1
            intents[proposal["intent_id"]] = by_key[key]
    full_stops = [
        (r["symbol"], r["actual_exit_ns"]) for r in labels if "stop" in r.get("exit_reason", "")
    ]
    rows = []
    for row in labels:
        ordinal = intents.get(row["entry_intent_id"])
        earlier_stop = [
            ns
            for symbol, ns in full_stops
            if symbol == row["symbol"]
            and ns < row["actual_entry_ns"]
            and str(pd.Timestamp(ns, unit="ns", tz="UTC").tz_convert("America/New_York").date())
            == row["day"]
        ]
        rows.append(
            {
                "symbol": row["symbol"],
                "day": row["day"],
                "confirmation_id": row["confirmation_id"],
                "submitted_ordinal": ordinal,
                "actual_entry_ns": row["actual_entry_ns"],
                "actual_exit_ns": row["actual_exit_ns"],
                "quantity": row["actual_quantity"],
                "net_dollars": row["native_net"],
                "fees": row["total_fees"],
                "exit_reason": row["exit_reason"],
                "same_session_prior_full_stop": max(earlier_stop) if earlier_stop else None,
            }
        )
    return {
        "closed_actual_trades": rows,
        "later_submitted_intents": sum(v > 1 for v in intents.values()),
        "positive_buy_callbacks": sum(e["action"] == "buy" and e["quantity"] > 0 for e in events),
        "unfilled_buy_callbacks": sum(e["action"] == "buy" and e["quantity"] == 0 for e in events),
        "interpretation": "Per-trade attribution is descriptive; "
        "policy increment includes sizing and later cash/slot competition",
    }


def run(batch_id):
    from open_composer.lab import DSRConfig, Experiment, TrialLedger, Variant, run_batch
    from open_composer.research.agent_workflow import identifier

    identifier(batch_id)
    gate(new_start=True, financial=True)
    check_inputs()
    deadline = time.monotonic() + 3600
    ledger = TrialLedger(OUT / "trials.jsonl")
    if not any(e.trial_id == PRIOR for e in ledger.events()):
        ledger.import_prior(
            PRIOR,
            count=63,
            evidence=[
                "reports/research/program/martin-parent-first-pullback-20261025/accepted-completion.json",
                "reports/research/program/martin-learned-payoff-state-20261026/state.json",
            ],
            note="Known financial-start floor:62 prior+1 later incompleteR; "
            "not independent hypotheses/exhaustive project count. Label initializations separate.",
        )
    native_folder = OUT / "native-runs" / batch_id
    exposure = (
        "Seen 2024-Q1 Jan2-Mar28, all29 static names/28issuers, prior-only eligibility; "
        "conditional received tape; known prior financial starts>=63"
    )
    dsr = DSRConfig(
        method="none",
        assumptions="Short dependent development component; "
        "account-start floor is not independent-trial dispersion. PBO/DSR not identified.",
    )
    baseline = run_batch(
        ROOT,
        experiment=Experiment(
            direction=DIRECTION,
            data_and_exposure=exposure,
            costs="10bp/side; inherited synthetic O-L-H-C/tick/ACK; no additional fee grid",
            baseline="Cash, no interest; matched R comparison follows",
            baseline_net_profit_usd=0.0,
        ),
        batch_id=batch_id + "-baseline",
        variants=[
            Variant(
                "B",
                {"attempts_per_day": 1},
                lambda: native_account("B", native_folder / "B", deadline),
                exposure_note="Count actual baseline account start conservatively; "
                "no independent-trial claim",
            )
        ],
        dsr_config=dsr,
    )
    if baseline.failures:
        raise RuntimeError(f"Baseline incomplete; R not started: {baseline.failures}")
    b = json.loads((native_folder / "B/result.json").read_text())
    repeat = run_batch(
        ROOT,
        experiment=Experiment(
            direction=DIRECTION,
            data_and_exposure=exposure,
            costs="Identical10bp/side, native engine/cash/risk/partial runner to measured B",
            baseline=f"Actual B cap1 at {str((native_folder / 'B/result.json').relative_to(ROOT))}",
            baseline_net_profit_usd=b["net_dollars"],
        ),
        batch_id=batch_id + "-repeated",
        variants=[
            Variant(
                "R",
                {"attempts_per_day": 3},
                lambda: native_account("R", native_folder / "R", deadline),
            )
        ],
        dsr_config=dsr,
        selected_id="R",
    )
    if repeat.failures:
        raise RuntimeError(f"Repeated account incomplete: {repeat.failures}")
    r = json.loads((native_folder / "R/result.json").read_text())
    summary = {
        "status": "two_actual_accounts_complete_pending_independent_result_review",
        "at": stamp(),
        "B_net_dollars": b["net_dollars"],
        "R_net_dollars": r["net_dollars"],
        "R_minus_B_dollars": r["net_dollars"] - b["net_dollars"],
        "fees": {"B": b["fees"], "R": r["fees"]},
        "observed_minute_drawdown_pct": {
            "B": b["observed_minute_drawdown_pct"],
            "R": r["observed_minute_drawdown_pct"],
        },
        "n_trials_known_financial_start_floor": repeat.n_trials,
        "new_financial_starts": 2,
        "new_fits": 0,
        "attribution": {arm: attempt_attribution(native_folder / arm) for arm in ("B", "R")},
        "model_learning_validated": False,
        "paper_ready": False,
        "next_decision": "Apply frozen protocol interpretation and deliver concrete next brief; "
        "no nearby cap/window/stop rescue grid",
    }
    save(native_folder / "comparison.json", summary)
    print(
        json.dumps({k: v for k, v in summary.items() if k != "attribution"}, ensure_ascii=False),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(check_inputs(), indent=2))
    elif not args.batch_id:
        parser.error("--batch-id is required for an actual account batch")
    else:
        run(args.batch_id)
