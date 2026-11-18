# ruff: noqa: E501 -- Exact fixed source identities and scientific contract literals.
"""Fixed31 lawful request plan and exact received-page parser; no HTTP on import."""

import math
from collections import defaultdict
from datetime import timedelta

from receiver_common import (
    HERE,
    SHARE,
    SYMBOLS,
    UNITS,
    absolute_fact_time,
    binding,
    calendar,
    canonical,
    checked,
    clock,
    load,
    module,
    month_dates,
    now,
)

from open_composer.market_sessions import NEW_YORK

BAR_URL = "https://data.alpaca.markets/v2/stocks/bars"
ACTION_URL = "https://data.alpaca.markets/v1/corporate-actions"


def requests(formation_month, prefix_end, raw_start=None):
    """The authorized transport receives this exact inventory; no live quote probe."""
    end = month_dates(formation_month)[-1]
    following = (clock(end + "T00:00:00+00:00") + timedelta(days=1)).date().isoformat()
    inventory = load(SHARE / "share-source-inventory.json")
    result = [
        dict(
            key="raw-bars",
            endpoint=BAR_URL,
            params=dict(
                symbols=",".join(UNITS),
                start=prefix_end + "T00:00:00Z",
                end=following + "T00:00:00Z",
                timeframe="1Day",
                feed="sip",
                adjustment="raw",
                asof="-",
                limit=10000,
                sort="asc",
            ),
        ),
        dict(
            key="actions",
            endpoint=ACTION_URL,
            params=dict(
                symbols=",".join(UNITS), start=prefix_end, end=following, limit=1000, sort="asc"
            ),
        ),
    ]
    if raw_start is False:
        result = result[1:]
    elif raw_start is not None:
        result[0]["params"]["start"] = raw_start + "T00:00:00Z"
    for s in SYMBOLS:
        cik = inventory["selected_members"][s]["cik"]
        result.extend(
            [
                dict(
                    key="counts-" + s,
                    endpoint=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
                    params={},
                ),
                dict(
                    key="filings-" + s,
                    endpoint=f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
                    params={},
                ),
            ]
        )
    return result


def pages(folder, request, cutoff, earliest):
    """Exactly listed complete page/start/raw/HTTP bytes, never a glob consumer."""
    folder = canonical(folder)
    complete_path = folder / "complete.json"
    complete_binding = binding(complete_path)
    complete = load(complete_path)
    checked(complete["capture_context"])
    assert complete["request"] == request and complete["status"] == "completed"
    assert complete["pages"] and clock(complete["completed_at"]) <= clock(cutoff)
    expected = {"complete.json"}
    bindings, objects, cursor, latest = [complete_binding], [], None, None
    for i, row in enumerate(complete["pages"], 1):
        name = f"GET{i:03}"
        meta_path = checked(row, folder / (name + ".json"))
        meta = load(meta_path)
        start_path = folder / (name + ".started.json")
        start_binding = binding(start_path)
        start = load(start_path)
        raw_path = checked(meta["response"], folder / (name + ".raw"))
        params = dict(request["params"])
        if cursor:
            params["page_token"] = cursor
        assert meta["endpoint"] == start["endpoint"] == request["endpoint"]
        assert meta["params"] == start["params"] == params
        assert meta["requested_at"] == start["requested_at"]
        assert meta["capture_context"] == start["capture_context"] == complete["capture_context"]
        assert (
            earliest
            <= clock(meta["requested_at"])
            <= clock(meta["received_at"])
            <= clock(complete["completed_at"])
            <= clock(cutoff)
        )
        assert meta["status_code"] == 200, "Failed source retained; no silent zero or retry"
        obj = load(raw_path)
        cursor = obj.get("next_page_token")
        assert meta["next_page_token"] == cursor
        assert (
            binding(meta_path) == row
            and binding(start_path) == start_binding
            and binding(raw_path) == meta["response"]
        )
        bindings += [row, start_binding, meta["response"]]
        objects.append(obj)
        latest = max(latest, clock(meta["received_at"])) if latest else clock(meta["received_at"])
        expected.update([name + ".json", name + ".started.json", name + ".raw"])
        assert cursor is not None or i == len(complete["pages"]), "Extra page after completion"
    assert cursor is None
    assert binding(complete_path) == complete_binding
    assert {p.name for p in folder.iterdir() if p.is_file()} == expected, (
        "Unlisted or partial source bytes"
    )
    return objects, bindings, latest


def filing_clocks(payload):
    recent = payload["filings"]["recent"]
    fields = ["accessionNumber", "filingDate", "acceptanceDateTime", "primaryDocument"]
    assert len({len(recent[k]) for k in fields}) == 1
    return {
        a: dict(accn=a, filed=f, acceptanceDateTime=t, primaryDocument=d)
        for a, f, t, d in zip(*(recent[k] for k in fields), strict=True)
    }


def count_records(payload, cik):
    assert int(payload["cik"]) == cik
    tag = payload.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {})
    # An explicitly received absence remains unsupported, never CIK-based share invention.
    records = []
    for r in tag.get("units", {}).get("shares", []):
        if r.get("form") not in [
            "10-Q",
            "10-K",
            "10-Q/A",
            "10-K/A",
            "20-F",
            "20-F/A",
            "40-F",
            "40-F/A",
        ]:
            continue
        v = r.get("val")
        if (
            not isinstance(v, (float, int))
            or not math.isfinite(v)
            or v <= 0
            or r.get("end", "9999") > r.get("filed", "")
        ):
            continue
        records.append(
            {k: r.get(k) for k in ["end", "filed", "accn", "form", "val", "fy", "fp", "frame"]}
        )
    return records


def candidate_rows(records, clocks, month, cutoff):
    records = [
        r
        for r in records
        if r["end"] <= month_dates(month)[-1] and r["filed"] < clock(cutoff).date().isoformat()
    ]

    def admissible(r):
        c = clocks.get(r["accn"])
        if c and c.get("acceptanceDateTime"):
            try:
                return clock(c["acceptanceDateTime"]) <= clock(cutoff)
            except (TypeError, ValueError):
                pass
        return True

    records = [r for r in records if admissible(r)]
    if not records:
        return []
    end = max(r["end"] for r in records)
    filed = max(r["filed"] for r in records if r["end"] == end)
    return [(r, clocks.get(r["accn"])) for r in records if r["end"] == end and r["filed"] == filed]


def cached_class(old, r, c):
    return bool(
        old
        and c
        and all(old["record"].get(k) == r.get(k) for k in ["end", "filed", "accn", "form", "val"])
        and old["clock"] == c
    )


def cover_request(symbol, record, filing, cik):
    key = symbol + "-" + record["accn"]
    return dict(
        key=key,
        endpoint=f"https://www.sec.gov/Archives/edgar/data/{cik}/{record['accn'].replace('-', '')}/{filing['primaryDocument']}",
        params={},
    )


def receive_sources(manifest_path, cutoff):
    """Receive actual current formation source universe and matching class covers."""
    manifest_path = canonical(manifest_path)
    manifest = load(manifest_path)
    month = manifest["formation_month"]
    assert cutoff == manifest["source_cutoff"] == calendar(month)["source_cutoff"]
    from retained_sources import receive_retained

    reused = receive_retained(
        manifest.get("retained_captures", []),
        cutoff,
        manifest["prefix_end"],
        month_dates(month)[-1],
    )
    if reused["tail"] >= month_dates(month)[-1]:
        raw_start = False
    elif reused["tail"] > manifest["prefix_end"]:
        raw_start = (clock(reused["tail"] + "T00:00:00Z") + timedelta(days=1)).date().isoformat()
    else:
        raw_start = None
    required = requests(month, manifest["prefix_end"], raw_start)
    folders = manifest["requests"]
    assert set(folders) == {r["key"] for r in required}
    earliest = absolute_fact_time(month_dates(month)[-1])
    assert earliest <= clock(now()) and clock(cutoff) <= clock(now()), (
        "Future formation is not received"
    )
    parsed, bindings, latest = (
        {},
        [binding(manifest_path)] + reused["bindings"],
        max(earliest, reused["received_through"]) if reused["received_through"] else earliest,
    )
    inventory = load(SHARE / "share-source-inventory.json")
    root = canonical(manifest["capture_directory"])
    assert root == HERE / "captures" / month and manifest_path == root / "manifest.json", (
        "Wrong canonical source month/root"
    )
    from receiver import code_bindings

    capture = load(checked(manifest["capture_context"], root / "capture-started.json"))
    assert manifest["capture_code_bindings"] == capture["code_bindings"] == code_bindings()
    assert (
        manifest["capture_invocation_id"] == capture["capture_invocation_id"]
        and manifest["capture_admission"] == capture["admission"]
        and capture["admission"]
    )
    assert (
        capture["formation_month"] == month
        and capture["source_cutoff"] == cutoff
        and capture["previous"] == manifest["previous"]
        and capture["requests"] == required
    )
    assert capture["retained_captures"] == manifest.get("retained_captures", []), (
        "Source reuse set changed after invocation"
    )
    assert capture["source_plan"] == dict(
        formation_month=month,
        source_cutoff=cutoff,
        previous=manifest["previous"],
        retained_captures=manifest.get("retained_captures", []),
        requests=required,
    ), "Changed admitted source plan"
    assert (
        earliest <= clock(capture["started_at"]) <= clock(manifest["completed_at"]) <= clock(cutoff)
    )
    bindings.append(binding(root / "capture-started.json"))
    assert set(p.name for p in root.iterdir() if p.is_dir()) == set(folders) | {"covers"}
    for request in required:
        folder = checked(folders[request["key"]], root / request["key"] / "complete.json").parent
        objects, receipts, seen = pages(folder, request, cutoff, earliest)
        assert load(folder / "complete.json")["capture_context"] == manifest["capture_context"]
        if request["key"].startswith("counts-"):
            assert len(objects) == 1
            s = request["key"].removeprefix("counts-")
            member = inventory["selected_members"][s]
            parsed[request["key"]] = [
                dict(cik=member["cik"], records=count_records(objects[0], member["cik"]))
            ]
        elif request["key"].startswith("filings-"):
            assert len(objects) == 1
            parsed[request["key"]] = [dict(clocks=filing_clocks(objects[0]))]
        else:
            parsed[request["key"]] = objects
        bindings += receipts
        latest = max(latest, seen)
    parsed["raw-bars"] = reused["raw"] + parsed.get("raw-bars", [])
    parsed["actions"] = reused["actions"] + parsed["actions"]
    inventory = load(SHARE / "share-source-inventory.json")
    cache_path = checked(
        manifest["accepted_class_cache"], SHARE / "class-witnesses/source-result.json"
    )
    cache = {(r["symbol"], r["record"]["accn"]): r for r in load(cache_path)["rows"]}
    bindings.append(binding(cache_path))
    cover_parser = module("base_receiver_cover_parser", SHARE / "receive_class_witnesses.py")
    selected_members, witnesses, cover_keys = {}, defaultdict(dict), set()
    decision_date = clock(cutoff).date().isoformat()
    for s in SYMBOLS:
        assert len(parsed["counts-" + s]) == len(parsed["filings-" + s]) == 1
        member = inventory["selected_members"][s]
        clocks = parsed["filings-" + s][0]["clocks"]
        records = parsed["counts-" + s][0]["records"]
        records = [
            r
            for r in records
            if r.get("end", "9999") <= month_dates(month)[-1]
            and r.get("filed", "9999") <= decision_date
            and (
                not clocks.get(r["accn"], {}).get("acceptanceDateTime")
                or clock(clocks[r["accn"]]["acceptanceDateTime"]) <= clock(cutoff)
            )
        ]
        selected_members[s] = dict(member, records=records)
        # Only latest potentially public instant/publication group needs class evidence.
        if records:
            for r, c in candidate_rows(records, clocks, month, cutoff):
                if c is None:
                    # Missing actual filing clock/class witness is explicit unsupported.
                    continue
                old = cache.get((s, r["accn"]))
                if cached_class(old, r, c):
                    assert clock(old["received_at_utc"]) <= clock(cutoff)
                    witnesses[s][r["accn"]] = old
                    continue
                key = s + "-" + r["accn"]
                cover_keys.add(key)
                url = f"https://www.sec.gov/Archives/edgar/data/{member['cik']}/{r['accn'].replace('-', '')}/{c['primaryDocument']}"
                request = cover_request(s, r, c, member["cik"])
                folder = root / "covers" / key
                complete_binding = binding(folder / "complete.json")
                complete = load(folder / "complete.json")
                assert complete["request"] == request and len(complete["pages"]) == 1
                # Cover responses are HTML, so receive their actual typed body separately.
                meta_path = checked(complete["pages"][0], folder / "GET001.json")
                meta = load(meta_path)
                start_path = folder / "GET001.started.json"
                start_binding = binding(start_path)
                start = load(start_path)
                raw = checked(meta["response"], folder / "GET001.raw")
                assert (
                    meta["endpoint"] == start["endpoint"] == url
                    and meta["params"] == start["params"] == {}
                )
                assert meta["status_code"] == 200 and complete["status"] == "completed"
                assert meta["requested_at"] == start["requested_at"]
                assert (
                    meta["capture_context"]
                    == start["capture_context"]
                    == complete["capture_context"]
                    == manifest["capture_context"]
                )
                assert (
                    earliest
                    <= clock(meta["requested_at"])
                    <= clock(meta["received_at"])
                    <= clock(complete["completed_at"])
                    <= clock(cutoff)
                )
                assert {p.name for p in folder.iterdir()} == {
                    "complete.json",
                    "GET001.json",
                    "GET001.started.json",
                    "GET001.raw",
                }
                witnesses[s][r["accn"]] = dict(
                    symbol=s,
                    cik=member["cik"],
                    record=r,
                    clock=c,
                    **cover_parser.parse_cover(raw.read_bytes(), s, r),
                )
                assert binding(folder / "complete.json") == complete_binding
                assert binding(meta_path) == complete["pages"][0]
                assert binding(start_path) == start_binding
                assert binding(raw) == meta["response"]
                bindings += [
                    complete_binding,
                    complete["pages"][0],
                    start_binding,
                    meta["response"],
                ]
                latest = max(latest, clock(meta["received_at"]))
    assert set(manifest["covers"]) == cover_keys
    assert set(p.name for p in (root / "covers").iterdir()) == cover_keys
    for key in cover_keys:
        checked(manifest["covers"][key], root / "covers" / key / "complete.json")
    expected_days = month_dates(month)
    coverage = {}
    for symbol in UNITS:
        observed = sorted(
            {
                clock(r["t"]).astimezone(NEW_YORK).date().isoformat()
                for obj in parsed["raw-bars"]
                for r in obj["bars"].get(symbol, [])
                if clock(r["t"]).astimezone(NEW_YORK).date().isoformat() in expected_days
            }
        )
        coverage[symbol] = dict(
            expected_sessions=expected_days,
            observed_sessions=observed,
            missing_sessions=[d for d in expected_days if d not in observed],
            explicit_complete_request_with_no_bars=not observed,
            issuer_retained=True,
        )
    return dict(
        manifest=manifest,
        objects=parsed,
        inventory=dict(inventory, selected_members=selected_members),
        witnesses=dict(witnesses),
        bindings=bindings,
        raw_coverage=coverage,
        sources_received_through=latest.isoformat(),
    )
