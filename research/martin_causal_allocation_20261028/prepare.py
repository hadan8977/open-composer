"""Read-only plan support; no strategy imports, allocation execution or matcher.

Collect all saved R decision receipts, then inspect only observed prior volume
for the nine native-admitted names at four same-callback cash witnesses. Never
compute candidate A quantities, hypothetical outcomes, labels or an account.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import resource
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = Path(__file__).resolve().parent
RUN = TASK / "runs/allocation-plan-20261028"
OUT = RUN / "preparation-01"
PREVIOUS = ROOT / "research/martin_research_restart_20261028"
PRIOR = PREVIOUS / "runs/opportunity-audit-retry-20261028"
NATIVE = PREVIOUS / "native-runs/q1-2024-attempt-cap-v1"
SEQ = ROOT / (
    "reports/research/program/martin-quantization-plan-20261021/"
    "resume-20261023/owner-prompt-route-reassessment/sequence-context-information"
)
MINUTE = 60_000_000_000


def load(path):
    return json.loads(path.read_text())


def save(path, obj):
    with path.open("x") as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def stamp():
    return datetime.now(UTC).isoformat()


def binding(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size, sha256=h.hexdigest())


def close(a, b):
    assert math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-7), (a, b)


def collect():
    import pyarrow.parquet as pq

    from open_composer.research.agent_workflow import require_research

    require_research(ROOT)
    wall, cpu = time.monotonic(), time.process_time()
    OUT.mkdir()
    save(
        OUT / "process.json",
        dict(
            pid=os.getpid(),
            started_at_utc=stamp(),
            kind="finite_read_only_preparation",
            recovery="Inspect this same attempt; no account or remote job exists.",
        ),
    )
    sources = [Path(__file__).resolve(), TASK / "protocol.md", TASK / "allocation-contract.json"]

    # Accepted dependencies must be unchanged; this is not a renewed financial_go.
    accepted = load(PREVIOUS / "scope-review.json")
    assert accepted["verdict"] == "approve_deep_plan" and accepted["author_is_reviewer"] is False
    for row in accepted["bindings"]:
        path = PREVIOUS / row["path"]
        assert binding(path)["sha256"] == row["sha256"], path
        sources.append(path)
    for name in (
        "reviewer/review.json",
        "delivery/results.json",
        "delivery/costs-and-exposure.json",
    ):
        sources.append(PRIOR / name)
    assert load(PRIOR / "reviewer/review.json")["decision"] == "accept"
    sources += [PREVIOUS / "scope-review.json", SEQ / "input-manifest.json"]

    receipt = PRIOR / "diagnostic-01/states-R.csv"
    sources.append(receipt)
    with receipt.open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1754 and len({r["confirmation_id"] for r in rows}) == 1754
    assert sum(r["feature_status"] == "valid" for r in rows) == 1713
    assert all("2024-01-02" <= r["day"] <= "2024-03-28" for r in rows)
    native_manifest = {r["path"]: r for r in load(PRIOR / "diagnostic-01/source-bindings.json")}
    proposals_path = NATIVE / "R/proposals.json"
    assert (
        binding(proposals_path)["sha256"]
        == native_manifest[str(proposals_path.relative_to(ROOT))]["sha256"]
    )
    props = load(proposals_path)
    sources.append(proposals_path)
    groups = defaultdict(list)
    for row in rows:
        ns = int(row["native_close_callback_ns"])
        assert ns == int(row["decision_ns"]) + 1
        groups[ns].append(row)
        if row["proposal_source_index"]:
            p = props[int(row["proposal_source_index"])]
            assert p["confirmation_id"] == row["confirmation_id"]
            assert p["quantity"] == int(row["planned_quantity"])
            assert p["admitted"] == (row["admitted"] == "True")
            assert p["received_mark_valuation"]["at_ns"] == ns
    assert sum(bool(r["proposal_source_index"]) for r in rows) == len(props) == 1420

    # Check all callback-local reservation transitions without opening an account.
    witnesses, checked = [], Counter()
    for ns, batch in groups.items():
        original = batch[0]
        reserve = float(original["reserved_cash"])
        prior_positive = False
        local_contention = False
        eligible = []
        for r in batch:
            close(r["native_cash"], original["native_cash"])
            close(r["unsettled_cash"], original["unsettled_cash"])
            close(r["reserved_cash"], reserve)
            close(
                r["spendable_cash"],
                max(0, float(r["native_cash"]) - float(r["unsettled_cash"]) - reserve),
            )
            if r["proposal_source_index"]:
                eligible.append(r)
                limits = json.loads(r["binding_quantity_limits"])
                if prior_positive and "cash" in limits:
                    local_contention = True
                p = props[int(r["proposal_source_index"])]
                if p["admitted"]:
                    reserve += p["quantity"] * p["worst_price"] * 1.001
                    prior_positive = True
            checked["callback_reservation_state_rows"] += 1
        if local_contention:
            members = [r for r in eligible if r["admitted"] == "True"]
            witnesses.append(
                dict(
                    native_close_callback_ns=ns,
                    day=batch[0]["day"],
                    all_confirmation_ids=[r["confirmation_id"] for r in batch],
                    eligible=eligible,
                    selected=members,
                )
            )
    assert len(witnesses) == 4
    assert sum(len(w["selected"]) for w in witnesses) == 9

    # Exact equality predicates before materialization; only nine Q1 volume rows.
    needed = defaultdict(set)
    for w in witnesses:
        for r in w["selected"]:
            needed[r["day"][:7]].add((r["symbol"], w["native_close_callback_ns"] - 1 - 2 * MINUTE))
    volume, read_receipts = {}, []
    input_manifest = {
        str(Path(r["path"]).resolve()): r for r in load(SEQ / "input-manifest.json")["bindings"]
    }
    for month, keys in sorted(needed.items()):
        assert month in {"2024-01", "2024-02", "2024-03"}
        path = SEQ / "minute-months" / (month + ".parquet")
        actual = binding(path)
        expected = input_manifest[str(path.resolve())]
        assert actual["sha256"] == expected["sha256"] and actual["bytes"] == expected["bytes"]
        sources.append(path)
        filters = [
            [
                ("symbol", "=", s),
                ("timestamp", "=", datetime.fromtimestamp(ns // 1_000_000_000, UTC)),
            ]
            for s, ns in sorted(keys)
        ]
        table = pq.read_table(path, columns=["symbol", "timestamp", "volume"], filters=filters)
        got = table.to_pylist()
        assert len(got) == len(keys)
        for row in got:
            ns = int(row["timestamp"].timestamp()) * 1_000_000_000
            key = row["symbol"], ns
            assert key in keys and key not in volume
            assert math.isfinite(row["volume"]) and row["volume"] >= 4
            volume[key] = row["volume"]
        read_receipts.append(
            dict(
                path=actual["path"],
                columns=["symbol", "timestamp", "volume"],
                predicates=[dict(symbol=s, timestamp_ns=ns) for s, ns in sorted(keys)],
                materialized_rows=len(got),
                price_or_return_columns_read=False,
            )
        )
    assert len(volume) == 9

    raw_witnesses = []
    for w in witnesses:
        selected = w["selected"]
        first = props[int(selected[0]["proposal_source_index"])]
        book = first["book"]
        E, C = book["equity"], book["spendable_cash"]
        H, J = max(0, E - book["gross_notional"]), max(0, 0.02 * E - book["initial_risk_dollars"])
        requests = []
        for r in selected:
            p = props[int(r["proposal_source_index"])]
            v = volume[r["symbol"], w["native_close_callback_ns"] - 1 - 2 * MINUTE]
            price = p["worst_price"]
            unit = price - p["initial_stop"] + 0.001 * (price + p["initial_stop"])
            bounds = dict(
                entry_risk=math.floor(0.005 * E / unit),
                aggregate_risk=math.floor(J / unit),
                name=math.floor(0.25 * E / price),
                gross=math.floor(H / price),
                cash=math.floor(C / (price * 1.001)),
                prior_volume=math.floor(0.01 * v),
            )
            request = min(bounds.values())
            assert request >= p["quantity"] > 0
            requests.append(
                dict(
                    symbol=r["symbol"],
                    confirmation_id=r["confirmation_id"],
                    proposal_source_index=int(r["proposal_source_index"]),
                    native_sequential_quantity=p["quantity"],
                    standalone_native_request=request,
                    original_bounds_at_common_book=bounds,
                    prior_volume=v,
                    prior_bar_start_ns=w["native_close_callback_ns"] - 1 - 2 * MINUTE,
                    worst_price=price,
                    unit_planned_risk=unit,
                    native_reserved_cash=p["quantity"] * price * 1.001,
                    request_capital=request * price * 1.001,
                )
            )
        cash_demand = sum(r["request_capital"] for r in requests)
        risk_demand = sum(r["standalone_native_request"] * r["unit_planned_risk"] for r in requests)
        gross_demand = sum(r["standalone_native_request"] * r["worst_price"] for r in requests)
        raw_witnesses.append(
            dict(
                day=w["day"],
                native_close_callback_ns=w["native_close_callback_ns"],
                common_book=book,
                confirmed_ids=w["all_confirmation_ids"],
                selected_native_names=[r["symbol"] for r in requests],
                requests=requests,
                cash_request_sum=cash_demand,
                cash_available=C,
                request_exceeds_cash=cash_demand > C,
                request_exceeds_gross=gross_demand > H,
                request_exceeds_planned_risk=risk_demand > J,
                greater_standalone_request=any(
                    r["standalone_native_request"] > r["native_sequential_quantity"]
                    for r in requests
                ),
                candidate_allocations_or_profits_computed=False,
            )
        )
    identifiable = sum(
        w["greater_standalone_request"] and w["request_exceeds_cash"] for w in raw_witnesses
    )
    save(OUT / "witnesses.json", raw_witnesses)
    save(OUT / "volume-read-receipts.json", read_receipts)

    for arm in ("B", "R"):
        path = NATIVE / arm / "result.json"
        assert binding(path)["sha256"] == native_manifest[str(path.relative_to(ROOT))]["sha256"]
        sources.append(path)
    prior_results = {arm: load(NATIVE / arm / "result.json") for arm in ("B", "R")}
    clock_paths = [
        "reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014/code/native_events.py",
        "reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014/code/nautilus_policy_adapter.py",
        "reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014/code/native_book_view.py",
        "reports/research/program/martin-learned-payoff-state-20261026/execution_feed_v3.py",
        "reports/research/program/martin-learned-payoff-state-20261026/attempt_policy.py",
        "reports/research/program/martin-decision-loop-model-continuation-20261026/observed_native.py",
        "reports/research/program/martin-decision-loop-model-continuation-20261026/source-clock-amendment.md",
    ]
    sources.extend(ROOT / name for name in clock_paths)
    for name in (
        "control.json",
        "research/workflow.json",
        "config/memory-budget.json",
        "reports/ops/restructure-resume-20261028.json",
        "reports/research/program/martin-decision-loop-model-continuation-20261026/actual-cumulative-usage-at-cap70-20261027.json",
    ):
        sources.append(ROOT / name)
    save(OUT / "source-bindings.json", [binding(p) for p in dict.fromkeys(sources)])
    summary = dict(
        status="author_checks_pass_pending_independent_review",
        at_utc=stamp(),
        confirmations=1754,
        feature_valid=1713,
        feature_missing=41,
        unique_close_callbacks=len(groups),
        multi_confirmation_callbacks=sum(len(v) > 1 for v in groups.values()),
        multi_policy_eligible_callbacks=sum(
            sum(bool(r["proposal_source_index"]) for r in v) > 1 for v in groups.values()
        ),
        multi_positive_native_intent_callbacks=sum(
            sum(r["admitted"] == "True" for r in v) > 1 for v in groups.values()
        ),
        later_cash_financial_bound_callbacks=len(witnesses),
        exact_volume_rows_recovered=9,
        identifiable_cash_contention_callbacks=identifiable,
        support_decision="sufficient to submit a bounded component plan"
        if identifiable
        else "park: no identifiable contention",
        verification=dict(checked),
        clock_sources=clock_paths,
        prior_accounts=prior_results,
        new_financial_starts=0,
        new_hypothetical_labels=0,
        new_fits=0,
        new_optimizer_updates=0,
        new_financial_candidate_evaluations=0,
        proposed_rules=1,
        new_provider_calls=0,
        known_financial_start_floor=65,
        full_learning_roots=8666,
        accepted_prefix=1152,
        remaining_roots=7514,
        new_off_window_market_data_rows=0,
        unmeasured="interactive reads/edits/LLM usage and actual dollar bill unknown",
        caveats=[
            "Only four cash-path witnesses; no economic effect size or significance identified.",
            "No A allocation quantity, funded path or outcome computed.",
            "Only nine observed volume bounds recovered; all other unsaved bounds "
            "and physical missing paths remain unknown.",
            "Prior actual cross-window ranking-column exposure is retained in the linked "
            "prior costs-and-exposure.json.",
        ],
        inner_cpu_seconds=time.process_time() - cpu,
        inner_wall_seconds=time.monotonic() - wall,
        maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    save(OUT / "support.json", summary)
    save(
        OUT / "completion.json",
        dict(
            pid=os.getpid(),
            finished_at_utc=stamp(),
            status="complete_read_only_preparation",
            detached_jobs=0,
        ),
    )
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "confirmations",
                    "unique_close_callbacks",
                    "multi_positive_native_intent_callbacks",
                    "later_cash_financial_bound_callbacks",
                    "identifiable_cash_contention_callbacks",
                    "inner_cpu_seconds",
                    "maxrss_kib",
                )
            }
        )
    )


def resource_receipt(path):
    lines = path.read_text().splitlines()

    def field(label):
        return next(line.split(": ", 1)[1] for line in lines if label in line)

    wall = [float(x) for x in field("Elapsed (wall clock)").split(":")]
    return dict(
        path=str(path.relative_to(ROOT)),
        cpu_seconds=float(field("User time")) + float(field("System time")),
        wall_seconds=sum(v * 60**i for i, v in enumerate(reversed(wall))),
        maxrss_kib=int(field("Maximum resident set size")),
        exit_status=int(field("Exit status")),
    )


def finalize():
    from open_composer.research.agent_workflow import validate_results

    support = load(OUT / "support.json")
    receipt = resource_receipt(RUN / "preparation-01.resource.txt")
    assert receipt["exit_status"] == 0
    costs = dict(
        primary_measured_receipt=receipt,
        inner_costs_included_not_additive=True,
        finalization_receipt=str((RUN / "finalization-01.resource.txt").relative_to(ROOT)),
        finalization_receipt_available_after_this_process=True,
        interactive_reads_edits_agent_lint_costs="unmeasured, not zero",
        actual_dollar_bill=None,
        new_financial_starts=0,
        new_labels=0,
        new_fits=0,
        new_provider_calls=0,
        materialized_volume_rows=9,
        new_off_window_rows=0,
        known_financial_start_floor=65,
        prior_cross_window_exposure=str(
            (PRIOR / "delivery/costs-and-exposure.json").relative_to(ROOT)
        ),
        execution_estimate=dict(
            accounts=1,
            cpu_minutes=[18, 25],
            wall_minutes=[20, 35],
            rss_mib=[400, 650],
            capped_memory_mib=900,
            timeout_seconds=3600,
            required_owner_reserve_mib=500,
            control_reruns=0,
            source="Actual accepted B/R result.json measured CPU/wall/RSS; estimate, not admission",
        ),
    )
    save(OUT / "costs-and-exposure.json", costs)
    sources = [
        OUT / "support.json",
        OUT / "witnesses.json",
        OUT / "volume-read-receipts.json",
        OUT / "source-bindings.json",
        OUT / "costs-and-exposure.json",
        RUN / "preparation-01.resource.txt",
        TASK / "protocol.md",
        TASK / "allocation-contract.json",
        PRIOR / "delivery/results.json",
        PRIOR / "reviewer/review.json",
    ]
    result = dict(
        direction=TASK.name,
        kind="diagnostic",
        engine=(
            "prepare.py: saved-receipt clock/reservation support and nine Q1 "
            "observed-volume request checks only; no candidate account or allocation execution"
        ),
        source_artifacts=[str(p.relative_to(ROOT)) for p in sources],
        data_and_exposure=(
            "Seen Q1/static29, all1754 saved R confirmations including41 missing features. "
            "Nine observed prior-volume rows at four existing cash-bound callbacks; "
            "no new price/return/off-window data, labels or fits. Known financial-start "
            "floor65 unchanged; prior cross-window ranking-column read retained; "
            "full8666/accepted1152/remainder7514 preserved."
        ),
        costs=(
            f"Primary preparation outer receipt CPU {receipt['cpu_seconds']:.2f}s, "
            f"wall {receipt['wall_seconds']:.2f}s, peak {receipt['maxrss_kib']}KiB. "
            "Inner costs included; finalization raw receipt separate, interactive/agent "
            "dollar costs unknown. Later one-A estimate18-25 CPU minutes/20-35 wall "
            "minutes/400-650MiB, not admission."
        ),
        baseline=(
            "Accepted prior R(cap3) net$2993.36, economic incumbent B(cap1) net$4099.75 "
            "and cash$0. These are retained prior results, no new financial result; A unknown."
        ),
        n_trials=65,
        net_profit_usd=None,
        baseline_net_profit_usd=4099.75,
        dsr=None,
        dsr_note=(
            "N/A: preparation only;65 is a financial-start lower bound with unknown earlier "
            "exposure, not effective independent trials. PBO also unidentified; "
            "no optimization or promotion."
        ),
        limitations=support["caveats"]
        + [
            "Independent plan acceptance and affected implementation/numeric-representation "
            "review still required before any later financial_go.",
            "Saved controls reusable only under exact unaffected semantics "
            "and native sequential-preview parity.",
            "Same-volatility normalization is descriptive; no recent, physical-execution, "
            "model-contribution or readiness claim.",
        ],
    )
    save(RUN / "results.json", result)
    save(TASK / "results.json", result)
    validate_results(ROOT, str((RUN / "results.json").relative_to(ROOT)), TASK.name)
    print(
        json.dumps(
            dict(
                status="results_contract_pass",
                candidate_net_profit_usd=None,
                identifiable_cash_contention_callbacks=support[
                    "identifiable_cash_contention_callbacks"
                ],
            )
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["collect", "finalize"])
    args = parser.parse_args()
    (collect if args.mode == "collect" else finalize)()
