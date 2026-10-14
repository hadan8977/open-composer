"""Admitted200 offline dependency: small schemas/pure checks/synthetic native only."""

# ruff: noqa: E402
import ast
import json
import subprocess
import sys
from dataclasses import asdict, replace
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P / "code"))
from consumer_admission import (
    ROOT,
    bind,
    claim_launch,
    empirical_limit,
    locked_ledger,
    receipt,
    settle,
    verify_bindings,
)


def run(job):
    review_path = P / "economic-results/source-clock-independent-review.json"
    review = json.loads(review_path.read_text())
    assert review["verdict"] == "approve_deep_plan"
    assert review["author"] != review["reviewer"]
    assert review["allocation"]["prospective_offline_implementation_CPU"] == 200
    verify_bindings(review["bindings"])
    assert receipt(job)["input_scope_review"] == bind(review_path)
    assert receipt(job)["combined_CPU_upper"] <= 200
    with locked_ledger() as reservation_folder:
        matched = [json.loads(q.read_text()) for q in reservation_folder.glob("*.json")]
        matched = [r for r in matched if r.get("input_scope_review") == bind(review_path)]
        consumed = sum(
            Decimal(str(r["charged_CPU"] if r["status"] == "settled" else r["combined_CPU_upper"]))
            for r in matched
        )
        assert consumed <= Decimal("200")
    claim_launch(job, "consumer")
    empirical_limit(job)
    outcome = "offline_source_clock_failed"
    try:
        fresh = subprocess.run(
            [
                "python3",
                str(ROOT / "scripts/memory_budget.py"),
                "admit",
                "--kind",
                "job",
                "--mem",
                "400",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        paths = [
            Path(__file__),
            P / "economic-results/source_clock.py",
            P / "economic-results/source_clock_native.py",
        ]
        for path in paths:
            compile(path.read_text(), str(path), "exec")
        checks = []
        for arguments in (["format", *map(str, paths)], ["check", "--fix", *map(str, paths)]):
            completed = subprocess.run(
                [str(ROOT / ".venv/bin/ruff"), *arguments], capture_output=True, text=True
            )
            checks.append(
                dict(
                    argv=arguments,
                    exit=completed.returncode,
                    output=completed.stdout + completed.stderr,
                )
            )
            assert completed.returncode == 0, completed.stdout + completed.stderr
        import source_clock as sc

        old_tree = ast.parse((P / "economic-results/check_gap_events.py").read_text())
        new_tree = ast.parse(paths[1].read_text())
        old_ns = next(n for n in old_tree.body if isinstance(n, ast.FunctionDef) and n.name == "ns")
        new_ns = next(n for n in new_tree.body if isinstance(n, ast.FunctionDef) and n.name == "ns")
        # Docstrings differ, executable parser bodies and all9digits are exact.
        assert ast.dump(ast.Module(body=old_ns.body[1:], type_ignores=[])) == ast.dump(
            ast.Module(body=new_ns.body[1:], type_ignores=[])
        )
        assert sc.ns("2024-09-13T14:01:00.000000009Z") - sc.ns("2024-09-13T14:01:00Z") == 9
        scope = json.loads((P / "economic-results/gap-events-scope.json").read_text())
        loaded, schemas = {}, []
        for query in scope["requests"]:
            b = P / "economic-results/gap-events" / (query["id"] + ".bin")
            records, meta = sc.parse_source(b.read_bytes(), query["kind"], bind(b)["sha256"])
            assert meta["page_token"] is None and not meta["coverage_certified"]
            low, high = sc.ns(query["gap_start"]), sc.ns(query["gap_end"])
            central = tuple(r for r in records if low <= r.event_ns < high)
            loaded[(query["day"], query["kind"])] = records
            schemas.append(
                dict(
                    id=query["id"],
                    source=bind(b),
                    records=len(records),
                    central=len(central),
                    same_ns_extra=len(records) - len({r.event_ns for r in records}),
                    quote_problems=[
                        r.source_ordinal
                        for r in records
                        if r.kind == "quotes" and r.quote_problem()
                    ],
                    all_central_I=all("I" in r.conditions for r in central)
                    if query["kind"] == "trades"
                    else None,
                    central_size=str(sum(r.trade_size_raw_units for r in central))
                    if query["kind"] == "trades"
                    else None,
                    real_native_engines=0,
                    coverage_certified=False,
                )
            )
        # Freeze the 12 actual-source component setups before any native replay.
        fixtures = []
        tick = Decimal("0.0001")
        for day in ("2024-09-13", "2025-02-11"):
            quotes, trades = loaded[(day, "quotes")], loaded[(day, "trades")]
            query = next(q for q in scope["requests"] if q["day"] == day)
            low, high = sc.ns(query["gap_start"]), sc.ns(query["gap_end"])
            first, central_first = quotes[0], next(q for q in quotes if low <= q.event_ns < high)
            prices = [p for q in quotes for p in (q.bid, q.ask)] + [t.price for t in trades]
            minimum = min(prices)
            safe = (minimum / tick).to_integral_value(rounding=ROUND_FLOOR) * tick - tick
            for mode, stop in (
                ("expost_below_all", safe),
                ("first_central_bid", central_first.bid),
                ("first_central_ask", central_first.ask),
            ):
                for qty in (1, 25):
                    R0 = qty * (first.ask - stop)
                    fixtures.append(
                        dict(
                            id=f"SOURCE_CLOCK_V1__{day}__{mode}__q{qty}",
                            day=day,
                            mode=mode,
                            quantity=qty,
                            tick=str(tick),
                            stop=str(stop),
                            threshold_source_ordinal=central_first.source_ordinal
                            if mode != "expost_below_all"
                            else None,
                            threshold_information=(
                                "nonselectable retrospective controlled stress, not causal strategy"
                            ),
                            first_source_quote=asdict(first),
                            first_central_quote=asdict(central_first),
                            initial_cash="20000.00",
                            initial_reference=str(first.ask),
                            expected_initial_fill_price=str(first.ask),
                            entry_submit_ns=first.event_ns + 10000,
                            expected_terminal_fill_ns=first.event_ns + 10000,
                            protection_activation=(
                                "same native ns as terminal fill, synchronous callback ordinal "
                                "after actual fill"
                            ),
                            original_submitted_R0=str(R0),
                            initial_R0_status="positive" if R0 > 0 else "invalid_nonpositive_R0",
                            R_if_invalid=None,
                            synthetic_L2_depth_shares=100,
                            raw_quote_sizes_are_not_depth=True,
                            historical_size_unit_certified=False,
                            native_BBO_order=(
                                "book-before-quote adapter convention, never broker evidence"
                            ),
                            first_unresolved_price_ns=low,
                            native_policy_datetime_precision=(
                                "inherited microseconds; native integer ns separately retained"
                            ),
                            maximum_observed_quote_age_ns=60 * 10**9,
                            interval_end_ns=high,
                            source_versions=[
                                bind(P / "economic-results/gap-events" / (q["id"] + ".bin"))
                                for q in scope["requests"]
                                if q["day"] == day
                            ],
                        )
                    )
            qa_early = sc.classify_absent_bar(
                trades, low, high, low, page_parse_valid=True, token=None
            )
            qa_late = sc.classify_absent_bar(
                trades, low, high, high, page_parse_valid=True, token=None
            )
            assert qa_early.state == "unresolved_absence"
            assert qa_late.state == "source_not_emitted_with_actual_condition_evidence"
            assert not qa_late.new_completed_signal_bar and not qa_late.price_path_certified
        assert len(fixtures) == len({f["id"] for f in fixtures}) == 12
        contract = dict(
            version="SOURCE_CLOCK_V1",
            parent_complete=False,
            actual_source_components_not_executed=True,
            provenance="Current-vintage source event-time assumption; no arrival/PIT/firmNBBO",
            primary_cost_filled_side_bps=20,
            diagnostic_cost_bps=0,
            stress_cost_bps=40,
            full_strategy_candidate_count_added=0,
            old_unknown_cells_preserved=4,
            broker_election_never_certified_by_necessary_reference=True,
            fixtures=fixtures,
        )
        folder = P / "economic-results/source-clock-v1-final"
        folder.mkdir(exist_ok=False)
        # Contract comes before synthetic engine tests; actual market replay is0.
        (folder / "fixture-contract.json").write_text(
            json.dumps(contract, default=str, indent=2) + "\n"
        )
        assert (folder / "fixture-contract.json").read_bytes() == (
            P / "economic-results/source-clock-v1/fixture-contract.json"
        ).read_bytes()
        pure = []
        base = sc.ns("2024-01-02T14:30:00Z")
        q = sc.Observation(
            "quotes",
            base,
            0,
            "synthetic",
            ("R",),
            "C",
            "synthetic",
            "synthetic",
            bid=Decimal("10"),
            ask=Decimal("10.02"),
            bid_size_raw_units=Decimal("1"),
            ask_size_raw_units=Decimal("1"),
        )
        t = sc.Observation(
            "trades",
            base + 20,
            0,
            "synthetic",
            ("I",),
            "C",
            "synthetic",
            "synthetic",
            price=Decimal("10.01"),
            trade_size_raw_units=Decimal("1"),
        )
        setup = sc.StopSetup(Decimal("10.02"), base + 1, base + 2, 25, 1000000000)

        def case(name, quotes, trades, reason, expected=None, config=setup):
            got = sc.stop_reference(quotes, trades, config)
            assert len(got) == len(trades) and got[-1].reason == reason
            assert got[-1].observed_price_reference is expected
            assert got[-1].broker_stop_election.startswith("unknown")
            pure.append(dict(name=name, output=[asdict(r) for r in got]))

        case(
            "observed_match_not_broker",
            (q,),
            (t,),
            "observed_necessary_price_conditions_only",
            True,
        )
        case(
            "I_not_eligibility",
            (q,),
            (replace(t, conditions=()),),
            "observed_necessary_price_conditions_only",
            True,
        )
        case(
            "threshold_false",
            (q,),
            (replace(t, price=Decimal("10.03")),),
            "observed_necessary_price_conditions_only",
            False,
        )
        case("no_initial", (), (t,), "unknown_no_initial_bbo")
        case(
            "crossed_invalidates_old",
            (q, replace(q, event_ns=base + 10, source_ordinal=1, bid=Decimal("10.04"))),
            (t,),
            "unknown_crossed_quote",
        )
        case(
            "zero_invalidates_old",
            (q, replace(q, event_ns=base + 10, source_ordinal=1, bid=Decimal("0"))),
            (t,),
            "unknown_nonpositive_quote",
        )
        case(
            "qualification_invalidates_old",
            (q, replace(q, event_ns=base + 10, source_ordinal=1, conditions=("X",))),
            (t,),
            "unknown_unsupported_quote_qualification",
        )
        case(
            "same_ns_unknown",
            (q, replace(q, event_ns=t.event_ns, source_ordinal=1)),
            (t,),
            "unknown_cross_stream_same_ns_order",
        )
        case(
            "no_fill_no_election",
            (q,),
            (t,),
            "protection_not_active",
            config=sc.StopSetup(setup.stop, None, None, 25, 10**9),
        )
        case(
            "activation_same_ns",
            (q,),
            (replace(t, event_ns=base + 2),),
            "unknown_activation_same_ns_order",
        )
        case(
            "stale_age", (q,), (replace(t, event_ns=base + 10**9 + 1),), "unknown_stale_observation"
        )
        certified = sc.stop_reference((replace(q, synthetic_then_nbbo=True),), (t,), setup)[0]
        assert (
            certified.certified_then_nbbo_necessary_condition is True
            and certified.broker_stop_election.startswith("unknown")
        )
        same = (t, replace(t, source_ordinal=1, price=Decimal("10.015")))
        assert [r.source_ordinal for r in sc.stop_reference((q,), same, setup)] == [0, 1]
        try:
            sc.StopSetup(setup.stop, base + 2, base + 1, 25, 10**9)
        except ValueError:
            pass
        else:
            raise AssertionError("pre-fill protection accepted")
        for partial in (False, True):
            b = sc.no_bar_boundary(base, unacknowledged_partial=partial)
            assert not b.new_frame and not b.new_entry_or_trim_signal
            assert b.defer_session_month_for_unacknowledged_partial is partial
        # Only handcrafted synthetic quotes reach an engine in this offline job.
        from source_clock_native import run_component

        try:
            run_component(
                loaded[("2024-09-13", "quotes")],
                fixtures[0],
                ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml",
                provenance="separately_admitted_real_source_component",
            )
        except ValueError as error:
            assert str(error) == "actual_source_requires_independent_component_native_admission"
        else:
            raise AssertionError("standalone actual source bypassed native gate")

        synthetic_quotes = (
            q,
            replace(
                q,
                event_ns=base + 2 * 10**9,
                source_ordinal=1,
                bid=Decimal("9.80"),
                ask=Decimal("9.82"),
            ),
            replace(
                q,
                event_ns=base + 3 * 10**9,
                source_ordinal=2,
                bid=Decimal("9.50"),
                ask=Decimal("9.52"),
            ),
        )
        before = repr(synthetic_quotes)
        native = []
        for qty, depth, missing in (
            (1, 100, None),
            (25, 100, None),
            (25, 1, None),
            (25, 100, base + 10**9),
        ):
            f = dict(
                id=f"INERT__q{qty}__depth{depth}__missing{missing}",
                quantity=qty,
                initial_reference="10.02",
                stop="9.90",
                initial_R0_status="positive",
                entry_submit_ns=base + 10000,
                synthetic_L2_depth_shares=depth,
                first_unresolved_price_ns=missing,
            )
            result = run_component(
                synthetic_quotes,
                f,
                ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml",
                provenance="fully_synthetic_inert",
            )
            assert result["native_engines"] == 1
            assert (
                result["native_reports"]
                and result["native_reports"][0]["ns"] >= f["entry_submit_ns"]
            )
            assert result["initial_R0"] == qty * (10.02 - 9.9)
            if missing is None:
                assert (
                    not result["unknown"]
                    and result["quantity"] == 0
                    and len(result["closed_R"]) == 1
                )
                assert not result["pending"]
                reports = result["native_reports"]
                assert len({r["report_id"] for r in reports}) == len(reports)
                assert sum(Decimal(r["quantity"]) for r in reports[1:]) == Decimal(
                    reports[0]["quantity"]
                )
                actual_qty = Decimal(reports[0]["quantity"])
                cost = sum(Decimal(r["commission"].split()[0]) for r in reports)
                proceeds = sum(Decimal(r["price"]) * Decimal(r["quantity"]) for r in reports[1:])
                purchased = Decimal(reports[0]["price"]) * actual_qty
                dollars = proceeds - purchased - cost
                assert abs(
                    Decimal(str(result["closed_R"][0]))
                    - dollars / Decimal(str(result["initial_R0"]))
                ) < Decimal("1e-9")
                assert abs(
                    Decimal(str(result["native_cash"])) - (Decimal("20000") + dollars)
                ) < Decimal("0.00001")
                if depth == 1:
                    assert any(
                        a["action"] == "terminal_partial_cancel_ack" for a in result["audit"]
                    )
            else:
                assert result["unknown"] and result["quantity"] == qty
                assert result["closed_R"] == result["firstunknown"]["known_prefix_closed_R"] == []
                assert result["native_cash"] is None and result["R"] is None
                assert result["quarantined"]
                assert result["feedback_after"] == result["firstunknown"]["feedback"]
                assert not result["snapshots"]
            native.append(dict(fixture=f, result=result))
        assert repr(synthetic_quotes) == before
        proof = dict(
            implementation_files=[bind(path) for path in paths],
            fixture_contract=bind(folder / "fixture-contract.json"),
            accepted_science=bind(review_path),
            schemas=schemas,
            pure_checks=pure,
            synthetic_native_checks=native,
            native_engines=4,
            real_market_native_engines=0,
            actual_market_order_or_account_replay=0,
            HTTP=0,
            nativeCLI=0,
            Frame_generation=0,
            new_fits=0,
            full_strategy_trials_added=0,
            fresh=fresh.stdout.strip(),
            lint=checks,
            source_objects_unchanged=True,
            ns_parser_executable_AST_equal=True,
            mother_complete=False,
            economic_execution_admitted=False,
        )
        (folder / "author-verification.json").write_text(
            json.dumps(proof, default=str, indent=2) + "\n"
        )
        outcome = "offline_source_clock_schema_pure_and_synthetic_native_complete"
        print(
            json.dumps(
                dict(
                    outcome=outcome,
                    synthetic_native_engines=4,
                    real_market_native=0,
                    full_strategy_returns=0,
                )
            )
        )
    finally:
        settle(job, outcome)


if __name__ == "__main__":
    run(sys.argv[1])
