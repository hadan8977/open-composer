# ruff: noqa: E501 -- Exact actual source receipt schema.
"""Finite callable source capture through existing lawful transport; no scheduler."""

import json
import os
import time
import uuid
from datetime import timedelta

from receiver_common import (
    HERE,
    SHARE,
    SYMBOLS,
    absolute_fact_time,
    binding,
    calendar,
    canonical,
    clock,
    load,
    month_dates,
    now,
    save,
)
from source_contract import (
    cached_class,
    candidate_rows,
    count_records,
    cover_request,
    filing_clocks,
    pages,
    requests,
)


def capture_request(folder, request, cutoff, fetch, earliest, capture_context):
    """No automatic retries; complete pages reused, partial/failed requests retained."""
    folder = canonical(folder)
    if (folder / "complete.json").exists():
        assert load(folder / "complete.json")["capture_context"] == capture_context
        assert (
            load(folder / "complete.json")["request"] == request
            and load(folder / "complete.json")["status"] == "completed"
        )
        return binding(folder / "complete.json")
    if folder.exists():
        assert not list(folder.iterdir()), (
            "Partial/failed request needs factual recovery, not duplicate GET"
        )
    folder.mkdir(parents=True, exist_ok=True)
    cursor = None
    received = []
    seen = set()
    page = 0
    while True:
        assert clock(now()) < clock(cutoff), "Source cutoff passed; no late collection"
        page += 1
        name = f"GET{page:03}"
        params = dict(request["params"])
        if cursor:
            params["page_token"] = cursor
        started = now()
        assert earliest <= clock(started)
        save(
            folder / (name + ".started.json"),
            dict(
                endpoint=request["endpoint"],
                params=params,
                requested_at=started,
                capture_context=capture_context,
            ),
        )
        response = fetch(
            request["endpoint"],
            params,
            max(0.001, (clock(cutoff) - clock(started)).total_seconds()),
        )
        # Exact bytes and allow-listed response metadata only; credentials never enter receipts.
        raw = folder / (name + ".raw")
        with raw.open("xb") as f:
            f.write(response.entity_bytes)
            f.flush()
            os.fsync(f.fileno())
        received_at = now()
        is_html = request["endpoint"].startswith("https://www.sec.gov/Archives/")
        obj = {} if is_html or response.status_code != 200 else json.loads(response.entity_bytes)
        cursor = obj.get("next_page_token")
        meta = dict(
            endpoint=request["endpoint"],
            params=params,
            requested_at=started,
            received_at=received_at,
            status_code=response.status_code,
            response=binding(raw),
            next_page_token=cursor,
            capture_context=capture_context,
            headers={
                k: v
                for k, v in response.headers.items()
                if k.lower()
                in [
                    "date",
                    "content-type",
                    "x-request-id",
                    "x-ratelimit-remaining",
                    "x-ratelimit-reset",
                ]
            },
        )
        save(folder / (name + ".json"), meta)
        received.append(binding(folder / (name + ".json")))
        assert response.status_code == 200, (
            "Actual source failure retained; no retry or alternate source"
        )
        assert clock(received_at) <= clock(cutoff), "Late source bytes retained, not admitted"
        if not cursor:
            break
        assert cursor not in seen, "Repeated page cursor"
        seen.add(cursor)
    save(
        folder / "complete.json",
        dict(
            status="completed",
            request=request,
            pages=received,
            completed_at=now(),
            capture_context=capture_context,
        ),
    )
    return binding(folder / "complete.json")


def collect_month_sources(month, *, fetch, admit, previous=None):
    """Source plan + real capture. Caller supplies authorized HTTP transport only."""
    from receiver import code_bindings, seed

    s = seed()
    previous = previous or binding(HERE / "accepted-seed.json")
    if previous == binding(HERE / "accepted-seed.json"):
        prefix_end = s["prefix_end"]
    else:
        from receiver import receive_monthly_input

        cp = load(previous["path"])
        old = receive_monthly_input(cp["context"]["path"], cp["source_cutoff"])
        assert old["checkpoint"] == previous
        prefix_end = month_dates(cp["formation_month"])[-1]
    cutoff = calendar(month)["source_cutoff"]
    assert month in load(HERE / "source-contract.json")["permitted_formation_months"], (
        "Outside actual bounded monthly authority"
    )
    earliest = absolute_fact_time(month_dates(month)[-1])
    assert earliest <= clock(now()) < clock(cutoff), "Only actual complete-month pre-cutoff capture"
    destination = HERE / "captures" / month
    manifest_path = destination / "manifest.json"
    if manifest_path.exists():
        # Full actual receiver checks clock/bytes/pages on later numerical use.
        assert load(manifest_path)["previous"] == previous
        return manifest_path
    from retained_sources import discover, receive_retained

    retained = (
        load(destination / "capture-started.json")["retained_captures"]
        if (destination / "capture-started.json").exists()
        else discover(cutoff, prefix_end, month_dates(month)[-1])
    )
    reused = receive_retained(retained, cutoff, prefix_end, month_dates(month)[-1])
    if reused["tail"] >= month_dates(month)[-1]:
        raw_start = False
    elif reused["tail"] > prefix_end:
        raw_start = (clock(reused["tail"] + "T00:00:00Z") + timedelta(days=1)).date().isoformat()
    else:
        raw_start = None
    specs = requests(month, prefix_end, raw_start)
    codes = code_bindings()
    frozen = json.dumps(codes, sort_keys=True)
    plan = dict(
        formation_month=month,
        source_cutoff=cutoff,
        previous=previous,
        retained_captures=retained,
        requests=specs,
    )
    plan_fingerprint = json.dumps(plan, sort_keys=True)
    # Dispatch a frozen reconstruction, never the callback's mutable argument.
    frozen_plan = json.loads(plan_fingerprint)
    destination.mkdir(parents=True, exist_ok=True)
    start_path = destination / "capture-started.json"
    if start_path.exists():
        start = load(start_path)
        assert (
            start["requests"] == specs
            and start["previous"] == previous
            and start["formation_month"] == month
            and start["source_cutoff"] == cutoff
            and start["code_bindings"] == codes
            and start["source_plan"] == frozen_plan
        )
        capture_id, admission = start["capture_invocation_id"], start["admission"]
    else:
        capture_id = uuid.uuid4().hex
        admission = admit(
            plan,
            codes,
            calendar(month),
            capture_id,
        )
        assert (
            admission and frozen == json.dumps(codes, sort_keys=True) and codes == code_bindings()
        )
        assert json.dumps(plan, sort_keys=True) == plan_fingerprint, (
            "Scientific source admission plan mutated; no capture/GET allowed"
        )
        save(
            start_path,
            dict(
                formation_month=month,
                source_cutoff=cutoff,
                requests=specs,
                source_plan=frozen_plan,
                retained_captures=retained,
                previous=previous,
                code_bindings=codes,
                capture_invocation_id=capture_id,
                admission=admission,
                started_at=now(),
            ),
        )
    assert json.dumps(plan, sort_keys=True) == plan_fingerprint
    specs = frozen_plan["requests"]
    previous = frozen_plan["previous"]
    retained = frozen_plan["retained_captures"]
    capture_context = binding(start_path)
    (destination / "covers").mkdir(exist_ok=True)
    completed = {}
    next_sec = 0.0

    # SEC <=4requests/s; provider status/rate failures stop without retry.
    def paced(endpoint, params, timeout_seconds):
        nonlocal next_sec
        if "sec.gov" in endpoint:
            delay = max(0, next_sec - time.monotonic())
            if delay:
                time.sleep(delay)
            next_sec = time.monotonic() + 0.26
        assert clock(now()) < clock(cutoff)
        return fetch(
            endpoint,
            params,
            min(timeout_seconds, max(0.001, (clock(cutoff) - clock(now())).total_seconds())),
        )

    for spec in specs:
        completed[spec["key"]] = capture_request(
            destination / spec["key"], spec, cutoff, paced, earliest, capture_context
        )
    inventory = load(SHARE / "share-source-inventory.json")
    cache_file = SHARE / "class-witnesses/source-result.json"
    cache = {(r["symbol"], r["record"]["accn"]): r for r in load(cache_file)["rows"]}
    covers = {}
    for symbol in SYMBOLS:
        count_spec = next(x for x in specs if x["key"] == "counts-" + symbol)
        filing_spec = next(x for x in specs if x["key"] == "filings-" + symbol)
        counts = pages(destination / count_spec["key"], count_spec, cutoff, earliest)[0]
        filings = pages(destination / filing_spec["key"], filing_spec, cutoff, earliest)[0]
        assert len(counts) == len(filings) == 1
        cik = inventory["selected_members"][symbol]["cik"]
        for record, filing in candidate_rows(
            count_records(counts[0], cik), filing_clocks(filings[0]), month, cutoff
        ):
            if filing is None or cached_class(cache.get((symbol, record["accn"])), record, filing):
                continue
            spec = cover_request(symbol, record, filing, cik)
            covers[spec["key"]] = capture_request(
                destination / "covers" / spec["key"], spec, cutoff, paced, earliest, capture_context
            )
    assert frozen == json.dumps(codes, sort_keys=True) and codes == code_bindings()
    save(
        manifest_path,
        dict(
            formation_month=month,
            source_cutoff=cutoff,
            prefix_end=prefix_end,
            previous=previous,
            capture_directory=str(destination),
            requests=completed,
            covers=covers,
            retained_captures=retained,
            accepted_class_cache=binding(cache_file),
            capture_invocation_id=capture_id,
            capture_admission=admission,
            capture_code_bindings=codes,
            capture_context=capture_context,
            completed_at=now(),
        ),
    )
    return manifest_path
