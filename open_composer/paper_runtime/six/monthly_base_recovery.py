"""Current BASE input preparation with separate scientific and receipt clocks.

No training, publication, account or scheduler interface is present. Original
arithmetic executes only through the versioned scientific source loader.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from open_composer.paper_runtime.source_loader import install_source_imports, load_source

FORMATION = "2026-10"
SCIENTIFIC_CUTOFF = "2026-11-02T09:35:00-05:00"
ORIGINAL_RELATIVE = Path("reports/research/program/owner-profit-delivery-plan-20261017/candidate-contribution/future-input-receiver")


def _load(path):
    return json.loads(Path(path).read_text())


def _clock(value):
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert value.tzinfo is not None
    return value


def _binding(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha}


def _checked(row, root):
    path = Path(row["path"])
    if not path.is_absolute():
        path = Path(root) / path
    bound = _binding(path)
    assert bound["bytes"] == row["bytes"] and bound["sha256"] == row["sha256"], "Changed received bytes"
    return path.resolve()


def _save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


@contextlib.contextmanager
def _originals(root):
    """Use in a disposable capped monthly child, as the original component requires."""
    root = Path(root).resolve()
    install_source_imports(root)
    names = ["receiver_common", "features", "source_contract", "retained_sources", "receiver"]
    prior = {name: sys.modules.pop(name, None) for name in names}
    modules = {}
    try:
        for name in names:
            module = load_source(name, root / ORIGINAL_RELATIVE / (name + ".py"), root=root)
            sys.modules[name] = modules[name] = module
        yield modules
    finally:
        for name in names:
            sys.modules.pop(name, None)
            if prior[name] is not None:
                sys.modules[name] = prior[name]


def _capture(folder, expected_request, capture_binding, *, root, before, context):
    complete_path = _checked(capture_binding, root)
    assert complete_path == folder / "complete.json"
    complete = _load(complete_path)
    assert complete["request"] == expected_request and complete["status"] == "completed"
    assert complete["capture_context"] == context and len(complete["pages"]) == 1
    meta_path = _checked(complete["pages"][0], root)
    assert meta_path == folder / "GET001.json"
    meta = _load(meta_path)
    start_path = folder / "GET001.started.json"
    start = _load(start_path)
    raw_path = _checked(meta["response"], root)
    assert raw_path == folder / "GET001.raw"
    assert meta["status_code"] == 200 and meta["next_page_token"] is None
    for value in [start, meta]:
        assert value["endpoint"] == expected_request["endpoint"] and value["params"] == expected_request["params"]
        assert value["capture_context"] == context
    assert meta["requested_at"] == start["requested_at"]
    assert _clock("2026-10-30T16:00:00-04:00") <= _clock(meta["requested_at"]) <= _clock(meta["received_at"]) <= _clock(complete["completed_at"]) <= before
    assert {p.name for p in folder.iterdir()} == {"complete.json", "GET001.json", "GET001.started.json", "GET001.raw"}
    return raw_path.read_bytes(), [capture_binding, complete["pages"][0], _binding(start_path), meta["response"]], _clock(meta["received_at"])


def _current_source(source_preparation, projection, root, modules, *, now):
    """Rebuild exact source semantics from immutable actual HTTP receipts."""
    rc, contract = modules["receiver_common"], modules["source_contract"]
    path = Path(source_preparation).resolve()
    complete = _load(path)
    assert complete["status"] == "completed_current_source_preparation_not_month_admission"
    context_path = _checked(complete["context"], root)
    context = _load(context_path)
    assert context["kind"] == "actual_current_SEC_source_preparation_no_month_admission"
    assert context["scientific_fact_and_label_cutoff"] == complete["scientific_fact_and_label_cutoff"] == SCIENTIFIC_CUTOFF
    assert _clock(complete["actual_completed_at"]) <= now
    # Current receipt time establishes current availability only. The collector's
    # wall limit is never substituted for the frozen fact/label cutoff.
    before = min(now, _clock(context["collection_wall_deadline"]))
    requests = [r for r in contract.requests(FORMATION, "2026-09-30", raw_start=False) if r["key"] != "actions"]
    assert context["requests"] == requests
    assert set(complete["snapshots"]) == {r["key"] for r in requests}
    inventory = _load(rc.SHARE / "share-source-inventory.json")
    bindings, parsed, latest = [_binding(path), complete["context"]], {}, None
    for request in requests:
        raw, rows, received = _capture(path.parent / "snapshots" / request["key"], request, complete["snapshots"][request["key"]], root=root, before=before, context=complete["context"])
        symbol = request["key"].split("-", 1)[1]
        payload = json.loads(raw)
        parsed[request["key"]] = contract.count_records(payload, inventory["selected_members"][symbol]["cik"]) if request["key"].startswith("counts-") else contract.filing_clocks(payload)
        del payload
        bindings += rows
        latest = max(latest, received) if latest else received
    projection = Path(projection).resolve()
    audit = _load(projection / "audit.json")
    for row in audit["source_page_bindings"]:
        _checked(row, root)
    original_path = Path(audit["source_page_bindings"][0]["path"])
    assert original_path == root / "reports/paper/diagnostics/dated-target-refresh/2026-11-02/current-source.json"
    original = _load(original_path)
    assert original["reference_day"] == "2026-10-30" and original["application_day"] == "2026-11-02"
    raw, actions = {}, {}
    for item in original["data"]:
        if item["group"] != "core" or item["key"] not in ["raw-bars", "actions"]:
            continue
        for page in item["pages"]:
            meta = _load(_checked(page["metadata"], root))
            body = _load(_checked(page["response"], root))
            assert meta["status_code"] == 200 and meta["response"] == page["response"] and body.get("next_page_token") is None
            assert _clock(meta["received_at"]) <= _clock(SCIENTIFIC_CUTOFF)
            assert set(rc.UNITS) <= set(meta["params"]["symbols"].split(","))
            if item["key"] == "raw-bars":
                assert all(meta["params"][k] == value for k, value in [("feed", "sip"), ("adjustment", "raw"), ("asof", "-"), ("timeframe", "1Day")])
                assert meta["params"]["start"][:10] <= "2026-09-30" and meta["params"]["end"][:10] > "2026-10-30"
                for symbol in rc.UNITS:
                    for bar in body["bars"].get(symbol, []):
                        if "2026-09-30" <= bar["t"][:10] <= "2026-10-30":
                            key = symbol, bar["t"]
                            assert key not in raw
                            raw[key] = bar
            else:
                assert meta["params"]["start"] <= "2026-09-30" and meta["params"]["end"] > "2026-10-30"
                for kind, rows in body["corporate_actions"].items():
                    for row in rows:
                        symbol = row.get("symbol") or row.get("source_symbol") or row.get("acquiree_symbol")
                        if symbol in rc.UNITS or row.get("acquirer_symbol") in rc.UNITS:
                            actions.setdefault(kind, []).append(row)
    projected_raw = {"bars": {s: [row for (symbol, stamp), row in sorted(raw.items()) if symbol == s] for s in rc.UNITS}, "next_page_token": None}
    projected_actions = {"corporate_actions": actions, "next_page_token": None}
    assert projected_raw == _load(projection / "raw31-projection.json")
    assert projected_actions == _load(projection / "actions31-projection.json")
    bindings += audit["source_page_bindings"] + [_binding(projection / "raw31-projection.json"), _binding(projection / "actions31-projection.json")]
    cache_path = _checked(complete["accepted_class_cache"], root)
    assert cache_path == rc.SHARE / "class-witnesses/source-result.json"
    cache = {(r["symbol"], r["record"]["accn"]): r for r in _load(cache_path)["rows"]}
    bindings.append(complete["accepted_class_cache"])
    cover_parser = rc.module("base_recovery_cover_parser", rc.SHARE / "receive_class_witnesses.py")
    selected, witnesses, expected_covers = {}, {}, set()
    cutoff_date = _clock(SCIENTIFIC_CUTOFF).date().isoformat()
    for symbol in rc.SYMBOLS:
        member = inventory["selected_members"][symbol]
        records = parsed["counts-" + symbol]
        clocks = parsed["filings-" + symbol]
        records = [r for r in records if r.get("end", "9999") <= "2026-10-30" and r.get("filed", "9999") <= cutoff_date and (not clocks.get(r["accn"], {}).get("acceptanceDateTime") or _clock(clocks[r["accn"]]["acceptanceDateTime"]) <= _clock(SCIENTIFIC_CUTOFF))]
        selected[symbol], witnesses[symbol] = dict(member, records=records), {}
        for record, filing in contract.candidate_rows(records, clocks, FORMATION, SCIENTIFIC_CUTOFF):
            if filing is None:
                continue
            old = cache.get((symbol, record["accn"]))
            if contract.cached_class(old, record, filing):
                assert _clock(old["received_at_utc"]) <= _clock(SCIENTIFIC_CUTOFF)
                if old.get("received_gzip"):
                    bindings.append(_binding(_checked(old["received_gzip"], root)))
                witnesses[symbol][record["accn"]] = old
            else:
                request = contract.cover_request(symbol, record, filing, member["cik"])
                expected_covers.add(request["key"])
                raw_body, rows, received = _capture(path.parent / "covers" / request["key"], request, complete["covers"][request["key"]], root=root, before=before, context=complete["context"])
                witnesses[symbol][record["accn"]] = {"symbol": symbol, "cik": member["cik"], "record": record, "clock": filing, **cover_parser.parse_cover(raw_body, symbol, record)}
                bindings += rows
                latest = max(latest, received)
    assert set(complete["covers"]) == expected_covers
    return {"manifest": {"formation_month": FORMATION, "prefix_end": "2026-09-30", "source_cutoff": SCIENTIFIC_CUTOFF},
        "objects": {"raw-bars": [projected_raw], "actions": [projected_actions]},
        "inventory": dict(inventory, selected_members=selected), "witnesses": witnesses,
        "bindings": bindings, "actual_sources_received_through": latest.isoformat()}


def prepare_input(*, root, source_preparation, projection, output, now=None):
    """Build the real current monthly packet; no new date authority or fit implied.

    Keyword paths: completed current SEC preparation JSON, reviewed original
    raw/action projection directory, and a fresh isolated staging output folder.
    Returns the binding of `context.json`, suitable for the later monthly fit.
    """
    root, output = Path(root).resolve(), Path(output).resolve()
    assert output != root and not output.is_relative_to(root / "runtime")
    assert not output.exists(), "Retain orphan/partial output; never silently rebuild"
    now = datetime.now(UTC) if now is None else now
    assert now.tzinfo is not None
    with _originals(root) as modules:
        receiver, rc, features = modules["receiver"], modules["receiver_common"], modules["features"]
        source = _current_source(source_preparation, projection, root, modules, now=now)
        seed_binding = rc.binding(root / ORIGINAL_RELATIVE / "accepted-seed.json")
        monthly, old, units, inherited, old_actions, pending, consumed = receiver.load_previous(seed_binding)
        repair = {}
        for key in ["raw_close", "raw_open"]:
            target, original = units[key][:, :28], old[key]
            overlap = np.isfinite(target) & np.isfinite(original)
            assert np.array_equal(target[overlap], original[overlap]), "Conflicting finite raw prefix"
            assert not (np.isfinite(target) & ~np.isfinite(original)).any()
            missing = ~np.isfinite(target) & np.isfinite(original)
            repair[key] = int(missing.sum())
            target[missing] = original[missing]
            assert np.array_equal(target, original, equal_nan=True)
        source["actions"] = features.merge_actions(old_actions, source["objects"]["actions"], "2026-09-30")
        daily, _ = features.extend_daily(old, units, inherited, source)
        completed, events, completed_rows = features.complete_labels(monthly, daily, SCIENTIFIC_CUTOFF, pending)
        current, feature_receipt = features.formation(daily, source)
        packet = {k: completed[k] for k in ["context", "symbols", "months", "primitive", "flags", "turnover", "eligible", "label", "entry", "label_end"]}
        packet["dates"] = daily["dates"]
        for key in ["primitive", "flags", "turnover", "eligible"]:
            packet[key] = np.concatenate([packet[key], np.asarray(current[key], dtype=packet[key].dtype)[None]], axis=0)
        for key, value in [("months", FORMATION), ("entry", len(daily["dates"])), ("label_end", -1)]:
            packet[key] = np.concatenate([packet[key], np.asarray([value], dtype=packet[key].dtype)])
        packet["label"] = np.concatenate([packet["label"], np.full((1, 28), np.nan)])
        for key in ["primitive", "flags", "turnover", "eligible", "months", "entry"]:
            assert np.array_equal(packet[key][:-1], monthly[key], equal_nan=True) if np.issubdtype(packet[key].dtype, np.number) else np.array_equal(packet[key][:-1], monthly[key])
        finite = np.isfinite(monthly["label"])
        assert np.array_equal(packet["label"][:-1][finite], monthly["label"][finite])
        assert [str(monthly["months"][i]) for i in completed_rows] == ["2026-08"]
        september = list(packet["months"]).index("2026-09")
        assert not np.isfinite(packet["label"][september]).any() and int(packet["label_end"][september]) == -1
        with rc.legacy(rc.SHARE):
            learning = rc.module("base_recovery_original_fold", rc.SHARE / "learning.py")
            fold = learning.fold(packet, len(packet["entry"]) - 1)
        output.mkdir(parents=True)
        np.savez_compressed(output / "packet.npz", **packet)
        np.savez_compressed(output / "daily.npz", **daily)
        _save(output / "actions.json", source["actions"])
        _save(output / "feature-reception.json", rc.clean(feature_receipt))
        _save(output / "maturity-reception.json", rc.clean(events))
        consumed += source["bindings"] + receiver.code_bindings() + [_binding(__file__)]
        unique = {row["path"]: row for row in consumed}
        for row in unique.values():
            _checked(row, root)
        context = {"schema": "monthly-base-current-prepared-v1", "formation_month": FORMATION,
            "feature_end": "2026-10-30", "scientific_fact_and_label_cutoff": SCIENTIFIC_CUTOFF,
            "actual_sources_received_through": source["actual_sources_received_through"],
            "actual_prepared_at": datetime.now(UTC).isoformat(), "source_preparation": _binding(source_preparation),
            "reviewed_projection": str(Path(projection).resolve()), "original_seed": seed_binding,
            "whole_roster": rc.SYMBOLS, "source_roster": rc.UNITS,
            "outputs": {name: _binding(output / name) for name in ["packet.npz", "daily.npz", "actions.json", "feature-reception.json", "maturity-reception.json"]},
            "completed_label_months": [str(monthly["months"][i]) for i in completed_rows],
            "pending_label_months": [str(monthly["months"][i]) for i in pending if i not in completed_rows] + [FORMATION],
            "raw_prefix_missing_cells_filled": repair, "consumed": list(unique.values()),
            "fold": rc.clean({k: v for k, v in fold.items() if k not in ["i", "j", "weights"]}),
            "fit_calls": 0, "historical_timely_source_claim": False}
        _save(output / "context.json", context)
        _save(output / "seal.json", {"context": _binding(output / "context.json"), "actual_sealed_at": datetime.now(UTC).isoformat()})
    return _binding(output / "context.json")


def receive_input(context_binding, *, root, now=None):
    """Receive exact completed staging bytes; does not certify a trading schedule."""
    now = datetime.now(UTC) if now is None else now
    path = _checked(context_binding, root)
    context = _load(path)
    assert context["schema"] == "monthly-base-current-prepared-v1"
    assert context["formation_month"] == FORMATION and context["scientific_fact_and_label_cutoff"] == SCIENTIFIC_CUTOFF
    seal = _load(path.parent / "seal.json")
    assert seal["context"] == context_binding
    assert _clock(context["actual_sources_received_through"]) <= _clock(context["actual_prepared_at"]) <= _clock(seal["actual_sealed_at"]) <= now
    for row in [context["source_preparation"], context["original_seed"], *context["consumed"], *context["outputs"].values()]:
        _checked(row, root)
    with np.load(context["outputs"]["packet.npz"]["path"], allow_pickle=False) as packet:
        assert str(packet["months"][-1]) == FORMATION and str(packet["dates"][-1]) == context["feature_end"]
        assert int(packet["entry"][-1]) == len(packet["dates"]) and int(packet["label_end"][-1]) == -1
        assert not np.isfinite(packet["label"][-1]).any()
        september = list(packet["months"]).index("2026-09")
        assert not np.isfinite(packet["label"][september]).any() and int(packet["label_end"][september]) == -1
    return context
