"""Prospective source/input preparation and affected synthetic verification."""

# ruff: noqa: E402
import json
import resource
import subprocess
import sys
from pathlib import Path

P = Path(__file__).resolve().parents[2]
F = Path(__file__).resolve().parent
sys.path.insert(0, str(P / "code"))
sys.path.insert(0, str(F))
from consumer_admission import ROOT, bind, save
from continuation_admission import claim, rearm, remaining


def main(job):
    claim(job, "offline_input")
    files = [
        P / "code/continuation_admission.py",
        P / "economic-results/build_source_inventory.py",
        *F.glob("*.py"),
    ]
    for action in [("format",), ("check", "--fix")]:
        r = subprocess.run(
            [str(ROOT / ".venv/bin/ruff"), *action, *map(str, files)],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stdout + r.stderr
    rearm(job)
    # Existing product capabilities tested honestly. No quote readiness inferred
    # from an OHLC fixture or automatic fallback to IEX/sample data.
    for name, args in [
        ("registry_fixture", ["capability", "test"]),
        (
            "strategy",
            [
                "spec",
                "capabilities",
                str(ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml"),
                "--json",
            ],
        ),
    ]:
        if name == "registry_fixture" and (F / (name + "-capability.log")).exists():
            evaluations = json.loads((ROOT / "reports/capabilities/evaluation.json").read_text())
            bars = [
                e for e in evaluations["evaluations"] if e["capability_id"] == "market.alpaca_bars"
            ]
            assert len(bars) == 1 and bars[0]["passed"] is True
            save(
                F / "registry-scoped-disposition.json",
                dict(
                    required_bars=bars[0],
                    overall_exit=1,
                    unrelated_failed_capability="market.dm_author_deciles",
                    fixture_failure_retained=True,
                    no_repeat_of_whole_registry=True,
                ),
            )
            continue
        limit = max(1, int(remaining(job) - 20))
        r = subprocess.run(
            [str(ROOT / ".venv/bin/oc"), *args],
            capture_output=True,
            text=True,
            preexec_fn=lambda limit=limit: resource.setrlimit(
                resource.RLIMIT_CPU, (limit, limit + 1)
            ),
        )
        (F / (name + "-capability.log")).write_text(r.stdout + r.stderr)
        assert r.returncode == 0, r.stdout + r.stderr
        rearm(job)
    inventory = json.loads(
        (P / "economic-results/complete-source-clock-inventory.json").read_text()
    )
    requests = []
    for session in inventory["sessions"]:
        for w in session["windows"]:
            q = dict(
                w,
                query_start_ns=w["start_ns"] - 60 * 10**9,
                kind="quotes",
                host="data.alpaca.markets",
                path="/stocks/quotes",
                max_pages=3,
                page_cap=4 * 1024 * 1024,
                identity=(
                    "fixed recorded ticker; asof- disables automatic symbol mapping, "
                    "not PIT/vintage certification"
                ),
            )
            from gap_source import utc_ns

            q["params"] = dict(
                symbols=w["symbol"],
                start=utc_ns(q["query_start_ns"]),
                end=utc_ns(q["end_ns"]),
                feed="sip",
                asof="-",
                sort="asc",
                currency="USD",
                limit=10000,
            )
            requests.append(q)
    # Exact initial bootstrap: both previously exposed failure minutes, whole
    # deterministic clock windows. They do not select a profitable variant.
    bootstrap = []
    for day, minute in [("2024-09-13", 31), ("2025-02-11", 59)]:
        rows = [
            q
            for q in requests
            if q["symbol"] == "LMND" and q["session"] == day and minute in q["gap_minutes"]
        ]
        assert len(rows) == 1, (day, minute)
        bootstrap.append(rows[0]["id"])
    scope = dict(
        schema_version=3,
        author="7c7b1f3d-b962-4bbe-a2eb-87578888a8d5",
        inventory=bind(P / "economic-results/complete-source-clock-inventory.json"),
        requests=requests,
        request_upper=266,
        entity_upper=212975794,
        bootstrap_source_ids=bootstrap,
        released_HTTP_now=False,
        potential_request_definitions=len(requests),
        potential_pages_are_not_authorized_call_count=True,
        releases=(
            "Only exact accepted bootstrap IDs initially. Later active "
            "native-risk release at chronological missing minute; named IDs "
            "and immutable response reused across all comparisons. No "
            "PnL/sign/ranking selector."
        ),
        retries=0,
        redirects=0,
        methods=["GET"],
        CPU=1,
        memory_MiB=900,
        source_identity=(
            "current-vintage six original ticker controls; original exactraw "
            "certification not expanded"
        ),
        parse_order=(
            "invalid clock/schema/order/bounds or error/byte/pagecap stops "
            "followups, preserves raw/partial and full reservations"
        ),
        overlap=(
            "Each deterministic <=30minute gap group includes necessary60s "
            "initial quote. Overlapping initial lookback bytes disclosed; no "
            "repeated completed window calls. Quote messages and rawunits "
            "never deduped or used as synthetic signal bars."
        ),
        missing_depth_extension=(
            "This inventory counts actual Frame missing fields only. A future "
            "zero-depth/coordinate/necessary action witness is an explicit "
            "bound extension needing affected entry acceptance; it is never "
            "an arbitrary implicit GET."
        ),
    )
    save(F / "source-scope.json", scope)
    from decimal import Decimal

    from gap_source import MAX_AGE_NS, Observation, qualify_gap

    t = 1730471400 * 10**9

    def quote(at, bid="9.8", ask="9.8", conditions=("R",), raw=None):
        return Observation(
            "quotes",
            at,
            0,
            str(at),
            conditions,
            "A",
            "synthetic",
            raw or str((at, bid, ask, conditions)),
            bid=Decimal(bid),
            ask=Decimal(ask),
            bid_size_raw_units=Decimal(100),
            ask_size_raw_units=Decimal(100),
        )

    qa = dict(source_query_and_page_QA=True, source_provenance="fully_synthetic_inert")
    checks = []

    def check(name, predicate):
        assert predicate, name
        checks.append(name)

    initial = quote(t - 10**9)
    good = qualify_gap("SOFI", t, t + 60 * 10**9, (initial, quote(t + 30 * 10**9)), qa)
    check("valid_complete_conditional_window", good.unresolved_ns is None)
    check(
        "missing_initial",
        qualify_gap("SOFI", t, t + 60 * 10**9, (), qa).unresolved_reason
        == "missing_causally_prior_initial_BBO",
    )
    bad = quote(t - 1, "10", "9")
    check(
        "latest_crossed_not_skipped",
        qualify_gap("SOFI", t, t + 60 * 10**9, (initial, bad), qa).unresolved_reason
        == "crossed_quote",
    )
    check(
        "stale_initial",
        qualify_gap("SOFI", t, t + 60 * 10**9, (quote(t - MAX_AGE_NS),), qa).unresolved_reason
        == "stale_initial_BBO",
    )
    check(
        "age_unknown_not_healed",
        qualify_gap("SOFI", t, t + 80 * 10**9, (initial, quote(t + 70 * 10**9)), qa).unresolved_ns
        == t + 59 * 10**9,
    )
    check(
        "equal_timestamp_distinct_unknown",
        qualify_gap(
            "SOFI", t, t + 60 * 10**9, (initial, quote(t + 20), quote(t + 20, "9.7")), qa
        ).unresolved_ns
        == t + 20,
    )
    check(
        "identical_message_retained",
        len(
            qualify_gap(
                "SOFI",
                t,
                t + 60 * 10**9,
                (initial, quote(t + 20), quote(t + 20), quote(t + 30 * 10**9)),
                qa,
            ).events
        )
        == 3,
    )
    check(
        "bad_condition_unknown",
        qualify_gap(
            "SOFI", t, t + 60 * 10**9, (initial, quote(t + 20, conditions=("X",))), qa
        ).unresolved_reason
        == "unsupported_quote_qualification",
    )
    # Full engines on synthetic inputs only; old ordinary feed parity and new
    # gap/protective failure lifecycles have real native callbacks.
    from decision_system import read_parameters
    from gap_events import gap_minute
    from gap_native_engine import make_engine as new_engine
    from native_engine import make_engine as old_engine
    from native_events import native_month
    from nautilus_trader.model.identifiers import ClientId
    from test_decision_system import SPEC
    from verify_feed_reuse import source
    from verify_shared_feed import snapshot

    engines = 0
    parity = []
    for candidate, route, scenario in [
        ("P_SYSTEM", "market", "O-H-L-C"),
        ("P_EMA", "capped", "O-L-H-C"),
    ]:
        results = []
        for factory in (old_engine, new_engine):
            e, s = factory(
                read_parameters(SPEC),
                candidate,
                route,
                20,
                dict(spec="inert", input="synthetic", contract="inert"),
            )
            engines += 1
            try:
                b, q, c, _ = native_month(source(), scenario, {}, None)
                e.add_data(b)
                e.add_data(q)
                e.add_data(c, client_id=ClientId("MARTIN"))
                e.run()
                results.append(snapshot(s))
            finally:
                e.dispose()
        check("ordinary_no_gap_" + candidate, results[0] == results[1])
        parity.append(dict(candidate=candidate, route=route, scenario=scenario, exact=True))
    for mode in ["valid", "partial", "bad", "protect_rejected"]:
        packets = source()
        selected = packets[1]
        selected["missing"] = ["SOFI"]
        selected["prices"] = [r for r in selected["prices"] if r["symbol"] != "SOFI"]
        from gap_source import integer_ns

        st = integer_ns(selected["start"])
        price = "9.6" if mode == "protect_rejected" else "9.8"
        initial = quote(st - 10**9, price, price)
        obs = (initial, quote(st + 10 * 10**9, price, price), quote(st + 40 * 10**9, price, price))
        if mode == "bad":
            obs = (initial, quote(st + 20, "10", "9"))
        window = qualify_gap("SOFI", st, st + 60 * 10**9, obs, qa)
        if mode == "partial":
            # Whole-share quantity1 reproduces terminal partial cancel before
            # reprotection, with the same declared risk quantities.
            import gap_events

            before = gap_events.SYNTHETIC_DEPTH_PHYSICAL_SHARES
            gap_events.SYNTHETIC_DEPTH_PHYSICAL_SHARES = 1
        e, s = new_engine(
            read_parameters(SPEC),
            "P_SYSTEM",
            "market",
            20,
            dict(spec="inert", input="synthetic", contract="inert"),
        )
        engines += 1
        try:
            for packet in packets:
                data = (
                    gap_minute(packet, "O-H-L-C", {}, None, {"SOFI": window})
                    if packet is selected
                    else native_month([packet], "O-H-L-C", {}, None)
                )
                b, q, c, _ = data
                if b:
                    e.add_data(b)
                if q:
                    e.add_data(q)
                e.add_data(c, client_id=ClientId("MARTIN"))
                e.run(streaming=True)
                e.clear_data()
            e.end()
            actual = dict(mode=mode, **snapshot(s))
            save(F / (mode + "-native-inert.json"), actual)
            if mode == "bad":
                check("bad_quote_sticky_unknown", s.book.path_unknown)
            else:
                check(mode + "_known_lifecycle", not s.book.path_unknown)
            if mode == "protect_rejected":
                check(
                    "protective_rejection_actually_exercised",
                    any(
                        a["action"] == "terminal_protective_rejection_safety_exit" for a in s.audit
                    ),
                )
            if mode == "partial":
                check(
                    "partial_native_exercised",
                    any(a["action"] == "native_partial" for a in s.audit),
                )
        finally:
            e.dispose()
            if mode == "partial":
                gap_events.SYNTHETIC_DEPTH_PHYSICAL_SHARES = before
    save(
        F / "author-synthetic-verification.json",
        dict(
            checks=checks,
            native_engines=engines,
            no_gap_parity=parity,
            real_HTTP=0,
            actual_source_native=0,
            new_prices_are_synthetic=True,
            bootstrap_source_ids=bootstrap,
        ),
    )
    out = ROOT / "reports/harness/data/martin_complete_system_20261014-capability-review.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    save(
        out,
        dict(
            strategy_name="martin_complete_system_20261014",
            reviewed_at="2026-10-14",
            capabilities=[
                dict(
                    capability_id="market.alpaca_bars",
                    kind="market",
                    status="partial",
                    strict_behavior="research_replay_cache",
                    paper_ready=False,
                    notes=(
                        "Original conditional normalized source bars; registeredOHLC "
                        "fixture pass is not exactraw, quote/stop coverage or paper "
                        "certificate."
                    ),
                )
            ],
            feature_packet_pit_check="warning",
            sample_data_caveats=[
                "Currentvintage deterministic context; no news/LLM/new signal modality."
            ],
            scoped_execution_dependency=dict(
                source="Alpaca existing SIP raw quote witnesses",
                status="pending_affected_source_entry_input_acceptance",
                registry_quote_capability_available=False,
                signal_capability=False,
                product_or_paper_quote_readiness=False,
            ),
            conclusion="warning",
        ),
    )
    account = json.loads((P / "cumulative-accounting.json").read_text())
    account.update(
        review_total_CPU=604.3,
        review_remaining_CPU=395.7,
        old_review_retired_at_root_allocation=True,
        original_review_lineage_note=(
            "Prior587.81+ee4.90+ee6.59+Root5=604.30; all future reviews "
            "charge prospective36000, not remaining395.70"
        ),
        market_combined_request_cap=352,
        market_combined_entity_byte_cap=268435456,
        market_requests_remaining=266,
        market_entity_remaining_B=212975794,
    )
    save(P / "cumulative-accounting.json", account)
    state = json.loads((P / "current-state.json").read_text())
    state.update(
        status="source_consumer_v3_exact_scope_affected_acceptance_preparation",
        next_action=(
            "Original ee exact source scope/consumer acceptance then two "
            "source-only fixed bootstrap windows; source-QA + actual/native "
            "gap route acceptance before whole first8. Newprospective charges "
            "only; no oldunknown replay."
        ),
        complete_source_clock_inventory=bind(
            P / "economic-results/complete-source-clock-inventory.json"
        ),
        source_consumer_affected_plan=bind(F / "affected-plan.json"),
        old_comparison_remaining_CPU=395.7,
        root_notification_pending_native_final=False,
        root_notification_mode="complete accepted result or new material decision only",
        latest_bulk_result_independent_acceptance_pending=False,
        economic_execution_admitted=False,
    )
    save(P / "current-state.json", state)


if __name__ == "__main__":
    main(sys.argv[1])
