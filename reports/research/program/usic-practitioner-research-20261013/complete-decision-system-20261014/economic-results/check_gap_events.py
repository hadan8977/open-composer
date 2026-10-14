"""Source-only quote/trade witnesses; no native events, signals, fills or gap repair."""

# ruff: noqa: E402
import argparse
import calendar
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "code"))
from consumer_admission import (
    AUTHOR,
    REVIEWER,
    P,
    bind,
    claim_launch,
    empirical_limit,
    empirical_remaining,
    locked_ledger,
    native_admission,
    phase_admission,
    save,
    settle,
    verify_bindings,
)

sys.path.insert(0, str(P.parent / "code"))
from acquire_components import bounded_get


def ns(value):
    """Parse provider UTC nanoseconds without floating-point/microsecond truncation."""
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z", value)
    if not match:
        raise ValueError("unsupported_source_timestamp")
    whole = calendar.timegm(datetime.fromisoformat(match[1]).timetuple())
    return whole * 10**9 + int((match[2] or "0").ljust(9, "0"))


def summarize(rows, query, token):
    observed, invalid = [], []
    for index, row in enumerate(rows):
        try:
            observed.append((ns(row["t"]), index, row))
        except (ValueError, TypeError, KeyError):
            invalid.append(dict(index=index, timestamp=row.get("t")))
    low, high = ns(query["gap_start"]), ns(query["gap_end"])
    start, end = ns(query["params"]["start"]), ns(query["params"]["end"])
    central = [r for t, i, r in observed if low <= t < high]
    before = [r for t, i, r in observed if t < low]
    timestamps = [t for t, i, r in observed]
    identical = Counter(json.dumps(r, sort_keys=True, default=str) for r in rows)
    result = dict(
        source_rows=len(rows),
        valid_timestamp_rows=len(observed),
        invalid_timestamp_rows=invalid,
        source_timestamp_nondecreasing=all(
            a <= b for a, b in zip(timestamps, timestamps[1:], strict=False)
        ),
        shared_timestamp_extra_rows=len(timestamps) - len(set(timestamps)),
        exact_duplicate_message_extra_rows=sum(n - 1 for n in identical.values()),
        outside_inclusive_query_rows=[
            dict(index=i, timestamp=r["t"]) for t, i, r in observed if not start <= t <= end
        ],
        central_missing_bar_minute_source_events=len(central),
        first_central_timestamp=central[0]["t"] if central else None,
        last_central_timestamp=central[-1]["t"] if central else None,
        conditions=sorted({str(c) for r in rows for c in r.get("c", [])}),
        source_first_visible=None,
        next_page_token=token,
        page_no_token_and_valid_timestamp_parse=token is None and not invalid,
        original_unknown_paths_stay_unknown=True,
        proves_no_trades_or_quote_crossing=False,
        firm_NBBO_certified=False,
        fill_reconstructed=False,
        coverage_gate_pass=False,
    )
    if query["kind"] == "quotes":
        result.update(
            last_quote_before_gap=before[-1] if before else None,
            first_quote_inside_gap=central[0] if central else None,
            crossed_quote_rows=sum(Decimal(str(r["bp"])) > Decimal(str(r["ap"])) for r in rows),
            nonpositive_price_quote_rows=sum(
                min(Decimal(str(r["bp"])), Decimal(str(r["ap"]))) <= 0 for r in rows
            ),
            quote_size_units_certified=False,
        )
    else:
        result.update(
            central_raw_trade_size_sum=str(
                sum((Decimal(str(r["s"])) for r in central), Decimal(0))
            ),
            central_raw_trade_conditions=sorted({str(c) for r in central for c in r.get("c", [])}),
            bar_eligibility_of_trade_conditions_certified=False,
        )
    return result


def main(job):
    review_path = P / "economic-results/gap-events-independent-review.json"
    review = json.loads(review_path.read_text())
    assert review["verdict"] == "approve_bounded_gap_microstructure_witness"
    assert review["author"] == AUTHOR and review["reviewer"] == REVIEWER != AUTHOR
    assert review["economic_execution_admitted"] is False
    verify_bindings(review["bindings"])
    assert review["bindings"]["code"] == bind(HERE)
    scope_path = P / "economic-results/gap-events-scope.json"
    assert review["bindings"]["scope"] == bind(scope_path)
    scope = json.loads(scope_path.read_text())
    alloc = review["allocation"]
    assert alloc["requests"] == 4 and alloc["entity_bytes"] == 2500000
    assert scope["fits"] == scope["PnL"] == scope["gap_filling"] == scope["account_replay"] == 0
    row = claim_launch(job, "consumer")
    assert row["empirical_CPU_upper"] <= alloc["prospective_input_CPU"] <= 80
    outcome, transport = "failed_gap_event_diagnosis", None
    folder = P / "economic-results/gap-events"
    ledger_path = folder / "request-ledger.json"
    ledger = dict(
        requests_used=0,
        complete_entity_bytes=0,
        incomplete_response_reserved_bytes=0,
        wire_bytes=None,
        retries=0,
        attempts=[],
    )
    try:
        native_admission(job)
        phase_admission(job, "empirical")
        empirical_limit(job)
        assert empirical_remaining(job) > 15
        folder.mkdir(exist_ok=False)
        save(ledger_path, ledger)
        from open_composer.adapters.data.alpaca_snapshot import _stock_data_client
        from open_composer.cli import _load_env

        _load_env()
        transport = _stock_data_client()
        results = []
        for query in scope["requests"]:
            assert empirical_remaining(job) > 10
            assert query["path"] == "/stocks/" + query["kind"]
            assert query["kind"] in ("quotes", "trades") and query["params"]["symbols"] == "LMND"
            cap = 1000000 if query["kind"] == "quotes" else 250000
            assert query["entity_cap"] == cap
            with locked_ledger():
                ap = P / "cumulative-accounting.json"
                a = json.loads(ap.read_text())
                assert (
                    a["original_market_requests_used"] + a.get("new_market_requests", 0) + 1 <= 96
                )
                assert (
                    a["original_market_entity_bytes_used"]
                    + a.get("new_market_entity_bytes", 0)
                    + cap
                    <= 134217728
                )
                a["new_market_requests"] = a.get("new_market_requests", 0) + 1
                a["new_market_entity_bytes"] = a.get("new_market_entity_bytes", 0) + cap
                save(ap, a)
            attempt = dict(
                id=query["id"],
                path=query["path"],
                params=query["params"],
                requested_at=datetime.now(UTC).isoformat(),
                reserved_bytes=cap,
                status="started",
            )
            ledger["requests_used"] += 1
            ledger["incomplete_response_reserved_bytes"] += cap
            ledger["attempts"].append(attempt)
            save(ledger_path, ledger)
            try:
                body, meta = bounded_get(transport._client, query["path"], query["params"], cap)
            except Exception as exc:
                attempt.update(status="transport_failure", exception_type=type(exc).__name__)
                save(ledger_path, ledger)
                break
            entity = folder / (query["id"] + ".bin")
            with entity.open("xb") as f:
                f.write(body)
            attempt.update(
                meta,
                entity=bind(entity),
                fetched_at=datetime.now(UTC).isoformat(),
                historical_first_visible=None,
                retained_bytes=len(body),
            )
            if meta["entity_complete"]:
                ledger["incomplete_response_reserved_bytes"] -= cap
                ledger["complete_entity_bytes"] += len(body)
                with locked_ledger():
                    ap = P / "cumulative-accounting.json"
                    a = json.loads(ap.read_text())
                    a["new_market_entity_bytes"] -= cap - len(body)
                    save(ap, a)
            attempt["status"] = (
                "complete_response" if meta["entity_complete"] else "incomplete_prefix"
            )
            save(ledger_path, ledger)
            if not meta["entity_complete"] or meta["http_status"] != 200:
                break
            payload = json.loads(body, parse_float=Decimal)
            assert set(payload.get(query["kind"], {})) <= {"LMND"}
            rows = payload.get(query["kind"], {}).get("LMND", [])
            token = payload.get("next_page_token")
            summary = summarize(rows, query, token)
            results.append(
                dict(
                    id=query["id"],
                    kind=query["kind"],
                    entity=bind(entity),
                    **summary,
                )
            )
            # Decimal values remain text in derived diagnostics; raw numeric
            # messages retain their original bytes. No price precision is lost.
            partial = json.loads(json.dumps(results, default=str))
            save(folder / "results-partial.json", partial)
            if summary["invalid_timestamp_rows"]:
                attempt["status"] = "unresolved_clock_no_followup"
                ledger["stop_reason"] = "unresolved_clock"
                save(ledger_path, ledger)
                break
            if token:
                attempt["status"] = "pagination_unresolved_no_followup"
                save(ledger_path, ledger)
                break
        save(
            folder / "result.json",
            dict(
                scope=bind(scope_path),
                approval=bind(review_path),
                requests=bind(ledger_path),
                cases=json.loads(json.dumps(results, default=str)),
                quote_or_trade_injected_into_engine=0,
                native_accounts=0,
                fits=0,
                PnL=0,
                Frame_writes=0,
                gap_filling=0,
                raw_exact_coverage_gate=False,
                old_paths_still_unknown=True,
                historical_source_vintage_PIT=False,
            ),
        )
        outcome = "gap_microstructure_source_diagnosis_complete"
        print(
            json.dumps(
                dict(
                    outcome=outcome,
                    HTTP=ledger["requests_used"],
                    output=bind(folder / "result.json"),
                )
            )
        )
    finally:
        if transport is not None:
            transport.close()
        if folder.exists():
            save(ledger_path, ledger)
        settle(job, outcome)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reservation-id", required=True)
    main(parser.parse_args().reservation_id)
