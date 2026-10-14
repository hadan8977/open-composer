"""Two independently admitted raw witnesses; no gap repair or economic rerun."""

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "code"))
from consumer_admission import (  # noqa: E402
    AUTHOR,
    REVIEWER,
    ROOT,
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
from acquire_components import bounded_get  # noqa: E402


def now():
    return datetime.now(UTC).isoformat()


def main(job):
    # No factory/credential initialization until both independent grants and
    # exact code/scope/input/current-authority/native/unique-resource gates pass.
    approval = json.loads((P / "economic-results/gap-witness-independent-review.json").read_text())
    assert approval["verdict"] == "approve_bounded_gap_witness"
    assert approval["author"] == AUTHOR and approval["reviewer"] == REVIEWER != AUTHOR
    verify_bindings(approval["bindings"])
    assert approval["bindings"]["code"] == bind(HERE)
    scope_path = P / "economic-results/gap-witness-scope.json"
    assert approval["bindings"]["scope"] == bind(scope_path)
    scope = json.loads(scope_path.read_text())
    assert approval["allocation"]["requests"] == 2
    assert approval["allocation"]["entity_bytes"] == 400000
    assert approval["economic_execution_admitted"] is False
    assert scope["parameter_changes"] == scope["gap_filling"] == scope["fits"] == 0
    row = claim_launch(job, "consumer")
    assert row["empirical_CPU_upper"] <= approval["allocation"]["prospective_input_CPU"]
    outcome, transport = "failed_gap_witness", None
    folder = P / "economic-results/gap-witness"
    ledger_path = folder / "request-ledger.json"
    ledger = dict(
        at_utc=now(),
        requests_used=0,
        complete_entity_bytes=0,
        incomplete_response_reserved_bytes=0,
        wire_bytes=None,
        attempts=[],
        retries=0,
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
        comparisons = []
        input_result = json.loads((P / "complete-input-v2-result.json").read_text())
        import duckdb

        db = duckdb.connect(config={"threads": 1})
        try:
            for query in scope["requests"]:
                assert empirical_remaining(job) > 10
                # Serial global aggregate counter plus durable unknown-byte reservation
                # precede GET. Failure keeps its request and reserved entity cap.
                with locked_ledger():
                    account_path = P / "cumulative-accounting.json"
                    account = json.loads(account_path.read_text())
                    used = account["original_market_requests_used"] + account.get(
                        "new_market_requests", 0
                    )
                    used_bytes = account["original_market_entity_bytes_used"] + account.get(
                        "new_market_entity_bytes", 0
                    )
                    assert used + 1 <= 96 and used_bytes + 200000 <= 134217728
                    account["new_market_requests"] = account.get("new_market_requests", 0) + 1
                    account["new_market_entity_bytes"] = (
                        account.get("new_market_entity_bytes", 0) + 200000
                    )
                    save(account_path, account)
                attempt = dict(
                    id=query["id"],
                    params=query["params"],
                    requested_at=now(),
                    historical_first_visible=None,
                    status="started",
                    reserved_bytes=200000,
                )
                ledger["attempts"].append(attempt)
                ledger["requests_used"] += 1
                ledger["incomplete_response_reserved_bytes"] += 200000
                save(ledger_path, ledger)
                try:
                    body, meta = bounded_get(
                        transport._client, "/stocks/bars", query["params"], 200000
                    )
                except Exception as exc:
                    attempt.update(status="transport_failure", exception_type=type(exc).__name__)
                    save(ledger_path, ledger)
                    break
                entity = folder / (query["id"] + ".bin")
                with entity.open("xb") as stream:
                    stream.write(body)
                attempt.update(
                    meta, entity=bind(entity), fetched_at=now(), retained_bytes=len(body)
                )
                if meta["entity_complete"]:
                    ledger["incomplete_response_reserved_bytes"] -= 200000
                    ledger["complete_entity_bytes"] += len(body)
                    with locked_ledger():
                        a = json.loads((P / "cumulative-accounting.json").read_text())
                        a["new_market_entity_bytes"] -= 200000 - len(body)
                        save(P / "cumulative-accounting.json", a)
                attempt["status"] = (
                    "complete_response" if meta["entity_complete"] else "incomplete_prefix"
                )
                save(ledger_path, ledger)
                if not meta["entity_complete"] or meta["http_status"] != 200:
                    break
                payload = json.loads(body, parse_float=Decimal)
                if payload.get("next_page_token"):
                    attempt["status"] = "pagination_unresolved_no_followup"
                    save(ledger_path, ledger)
                    break
                assert set(payload.get("bars", {})) <= {"LMND"}
                day = query["day"]
                expected = next(
                    x
                    for x in input_result["sessions"]
                    if x.get("symbol") == "LMND" and x.get("day") == day
                )
                raw = {x["t"]: x for x in payload.get("bars", {}).get("LMND", [])}
                normalized = next(
                    x for x in input_result["outputs"] if Path(x["path"]).name.startswith(day[:7])
                )
                assert bind(ROOT / normalized["path"]) == normalized
                rows = db.execute(
                    "SELECT timestamp,open,high,low,close,volume,vwap FROM read_parquet(?) "
                    "WHERE symbol='LMND' AND CAST(timestamp AS DATE)=? ORDER BY timestamp",
                    [str(ROOT / normalized["path"]), day],
                ).fetchall()
                differences, overlap = [], 0
                raw_keys = {
                    datetime.fromisoformat(t.replace("Z", "+00:00")).isoformat(): x
                    for t, x in raw.items()
                }
                for timestamp, *values in rows:
                    key = (
                        timestamp.replace(tzinfo=UTC).isoformat()
                        if timestamp.tzinfo is None
                        else timestamp.astimezone(UTC).isoformat()
                    )
                    if key not in raw_keys:
                        differences.append(dict(time=key, kind="normalized_without_raw"))
                        continue
                    overlap += 1
                    r = raw_keys[key]
                    for field, value in zip(("o", "h", "l", "c", "v", "vw"), values, strict=True):
                        if Decimal(str(value)) != Decimal(str(r[field])):
                            differences.append(
                                dict(
                                    time=key, field=field, normalized=str(value), raw=str(r[field])
                                )
                            )
                comparisons.append(
                    dict(
                        day=day,
                        raw_rows=len(raw),
                        normalized_rows=len(rows),
                        exact_overlap_rows=overlap if not differences else None,
                        differences=differences,
                        previously_missing=list(expected["missing"]),
                        previously_missing_present_in_raw=[
                            t for t in expected["missing"] if t in raw_keys
                        ],
                        requested_first_unknown=query["first_unknown_utc"],
                        first_unknown_minute_in_raw=query["first_unknown_utc"] in raw_keys,
                        does_not_prove_no_trade_or_quote_crossing=True,
                        existing_paths_remain_unknown=True,
                    )
                )
                save(folder / "comparisons-partial.json", comparisons)
        finally:
            db.close()
        save(
            folder / "result.json",
            dict(
                scope=bind(scope_path),
                approval=bind(P / "economic-results/gap-witness-independent-review.json"),
                requests=bind(ledger_path),
                comparisons=comparisons,
                full_raw_certification=False,
                modified_Frame_outputs=0,
                fits=0,
                account_replays=0,
                gap_filling=0,
                next=(
                    "If raw has the same holes, investigate quote coverage; no padding. "
                    "If different, independently admit corrected input before replay."
                ),
            ),
        )
        outcome = "bounded_gap_source_diagnosis_complete"
        print(
            json.dumps(
                dict(
                    outcome=outcome,
                    HTTP=ledger["requests_used"],
                    output=bind(folder / "result.json"),
                )
            ),
            flush=True,
        )
    finally:
        if transport is not None:
            transport.close()
        if folder.exists():
            ledger["finished_at"] = now()
            save(ledger_path, ledger)
        settle(job, outcome)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reservation-id", required=True)
    main(parser.parse_args().reservation_id)
