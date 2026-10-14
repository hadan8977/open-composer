"""Small source-derived decimal checks; independent acceptance belongs to ee."""

from __future__ import annotations

import json
import math
import resource
import time
from decimal import Decimal, localcontext
from pathlib import Path

from acquire import eligible_quote, ns, save, sha, utc
from build_components import NY, row_hash

OUT = Path(__file__).resolve().parent
ROOT = Path("/root/codex-test/open-composer")


def lines(name):
    return [json.loads(line) for line in (OUT / name).read_text().splitlines()]


def near(actual, expected):
    assert actual is not None and math.isclose(
        actual, float(expected), abs_tol=1e-14, rel_tol=1e-12
    )


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    ledger = json.loads((OUT / "data-request-ledger.json").read_text())
    assert len(ledger["attempts"]) == ledger["data_requests_used"] == 13
    assert ledger["unknown_entity_byte_allowance"] == 0
    assert not ledger["stopped_routes"] and ledger["automatic_retries"] == 0
    assert (
        sum(r["response_bytes"] for r in ledger["attempts"])
        == ledger["actual_entity_bytes"]
        == 44098
    )
    assert ledger["data_requests_used"] <= 32 and ledger["actual_entity_bytes"] <= 64 * 1024**2
    source, by_entity, raws, action_rows = {}, {}, {}, []
    for attempt in ledger["attempts"]:
        assert attempt["http_status"] == 200
        entity = ROOT / attempt["entity_path"]
        assert sha(entity) == attempt["entity_sha256"]
        assert entity.stat().st_size == attempt["response_bytes"]
        payload = json.loads(entity.read_bytes())
        source[attempt["input_id"]] = (attempt, payload)
        original = []
        if "corporate_actions" in payload:
            for category, rows in payload["corporate_actions"].items():
                original.extend((category, i, row) for i, row in enumerate(rows))
                action_rows.extend((category, row) for row in rows)
        else:
            kind = "bars" if "bars" in payload else "quotes"
            symbol = attempt["params"]["symbols"]
            rows = payload[kind].get(symbol, [])
            original.extend((None, i, row) for i, row in enumerate(rows))
            assert [ns(row["t"]) for row in rows] == sorted(ns(row["t"]) for row in rows)
            if kind == "bars" and attempt["params"]["adjustment"] == "raw":
                for row in rows:
                    import datetime

                    day = (
                        datetime.datetime.fromisoformat(row["t"].replace("Z", "+00:00"))
                        .astimezone(NY)
                        .date()
                        .isoformat()
                    )
                    raws[(symbol, day)] = row
        by_entity[attempt["entity_sha256"]] = {(c, i): row for c, i, row in original}
    normalized = lines("normalized-source-records.jsonl")
    assert len(normalized) == 392
    for row in normalized:
        original = by_entity[row["entity_sha256"]][(row["category"], row["source_ordinal"])]
        assert row["raw"] == original
        assert row_hash(original) == row["source_row_sha256"]
        assert row["historical_first_visible_at"] is None
    features = lines("price3-candidates.jsonl")
    assert len(features) == 82
    available = [f for f in features if f["Ret_D1"] is not None]
    assert len(available) == 66
    assert sum(f["source_component_usable_conditionally"] for f in features) == 65
    for feature in available:
        endpoints = feature["six_consecutive_endpoint_sessions"]
        assert len(endpoints) == 6
        symbol = feature["symbol"]
        with localcontext() as ctx:
            ctx.prec = 50
            gross = []
            for previous_day, day in zip(endpoints, endpoints[1:], strict=False):
                before, after = raws[(symbol, previous_day)], raws[(symbol, day)]
                assert before["v"] > 0 and after["v"] > 0
                split, cash = Decimal(1), Decimal(0)
                for category, action in action_rows:
                    if action.get("symbol") != symbol or action.get("ex_date") != day:
                        continue
                    if category == "forward_splits":
                        split *= Decimal(str(action["new_rate"])) / Decimal(str(action["old_rate"]))
                    elif category == "cash_dividends":
                        cash += Decimal(str(action["rate"]))
                    else:
                        raise AssertionError("Unmapped action in candidate")
                gross.append((split * Decimal(str(after["c"])) + cash) / Decimal(str(before["c"])))
            values = [g - 1 for g in gross]
            average = sum(values) / 5
            std = (sum((r - average) ** 2 for r in values) / 5).sqrt()
            near(feature["Ret_D1"], values[-1])
            near(feature["Ret_W1"], math.prod(gross) - 1)
            near(feature["STD_W1"], std)
        assert feature["STD_ddof"] == 0
        assert feature["historical_first_visible_at"] is None
        assert not feature["strict_APP_input_ready"] and not feature["full7_ready"]
        assert all(day <= feature["decision_session"] for day in endpoints)
    expected_earliest = {"AAPL": "2020-07-09", "ATVI": "2023-09-11"}
    for symbol, day in expected_earliest.items():
        assert next(f["decision_session"] for f in available if f["symbol"] == symbol) == day
    dividend = next(
        r
        for r in lines("daily-return-inputs.jsonl")
        if r["symbol"] == "AAPL" and r["session"] == "2020-08-07"
    )
    assert dividend["economic_distribution_per_previous_share"] == 0.82
    assert dividend["split_ratio_new_per_previous_share"] == 1
    split_day = next(
        f for f in features if f["symbol"] == "AAPL" and f["decision_session"] == "2020-08-31"
    )
    assert split_day["Ret_D1"] is not None and split_day["split_trigger_signal_excluded"]
    assert not split_day["source_component_usable_conditionally"]
    for feature in features:
        if feature["symbol"] == "ATVI" and feature["decision_session"] >= "2023-10-13":
            assert feature["Ret_D1"] is None
    labels = json.loads((OUT / "quote-label-candidates.json").read_text())
    assert len(labels) == 4
    unique_selections = {}
    for label in labels:
        for endpoint in ("entry_quote", "exit_quote"):
            selected = label[endpoint]
            if selected is None:
                continue
            attempt, payload = source[selected["request_id"]]
            rows = payload["quotes"][label["symbol"]]
            candidates = [
                (ns(row["t"]), i, row)
                for i, row in enumerate(rows)
                if eligible_quote(row, attempt["params"])
            ]
            stamp, ordinal, raw = min(candidates, key=lambda item: (item[0], item[1]))
            assert selected["raw"] == raw and selected["source_ordinal"] == ordinal
            assert row_hash(raw) == selected["source_row_sha256"]
            assert ns(attempt["params"]["start"]) <= stamp <= ns(attempt["params"]["end"])
            unique_selections[selected["request_id"]] = selected
        assert label["historical_first_visible_at"] is None
        assert label["actual_spendable_at"] is None
        assert not label["strict_APP_input_ready"] and not label["economic_or_strategy_return"]
        if label["gross_quote_entitlement_label"] is not None:
            before, after = label["entry_quote"]["raw"], label["exit_quote"]["raw"]
            entry_mid = (Decimal(str(before["bp"])) + Decimal(str(before["ap"]))) / 2
            exit_mid = (Decimal(str(after["bp"])) + Decimal(str(after["ap"]))) / 2
            ratio = Decimal(4) if label["case_id"] == "AAPL_split_boundary" else Decimal(1)
            near(label["entry_mid"], entry_mid)
            near(label["exit_mid"], exit_mid)
            near(label["gross_quote_entitlement_label"], ratio * exit_mid / entry_mid - 1)
            assert label["retrospective_hypothetical_endpoint_mature_at"] == after["t"]
            assert label["actual_current_candidate_mature_at"].startswith("2026-10-13")
    assert len(unique_selections) == 6
    preterminal, terminal = labels[2:]
    assert preterminal["exit_quote"] == terminal["entry_quote"]
    assert terminal["exit_quote"] is None and terminal["gross_quote_entitlement_label"] is None
    assert terminal["terminal_cash_receivable_per_eligible_old_share"] == 95
    assert terminal["actual_current_candidate_mature_at"] is None
    assert source["ATVI_quote_2023-10-13"][1] == {"quotes": {}, "next_page_token": None}
    normalized_actions = json.loads((OUT / "normalized-actions.json").read_text())
    aapl_div = next(
        a for a in normalized_actions if a["symbol"] == "AAPL" and a["ex_date"] == "2020-08-07"
    )
    assert aapl_div["cash_per_old_share"] == 0.82
    assert aapl_div["economic_effective_date"] == "2020-08-07"
    assert aapl_div["record_date"] == "2020-08-10" and aapl_div["payable_date"] == "2020-08-13"
    assert aapl_div["actual_spendable_at"] is None
    action_split = next(a for a in normalized_actions if a["category"] == "forward_splits")
    assert action_split["ex_date"] == "2020-08-31" and action_split["new_shares_per_old_share"] == 4
    assert sha(OUT.parent / "package-manifest.json") == (
        "e1f20bd777aaa3356bdc9ec575cdb67243ae9bbb010885b97c8156a15fc5faf3"
    )
    assert sha(OUT.parent / "partial-input/package-manifest.json") == (
        "927ea64e417e0b2c512eda40ab592b3a3e3d47d31d620820527ecfd23300779f"
    )
    save(
        OUT / "verification.json",
        {
            "as_of_utc": utc(),
            "verdict": "author_integrity_and_input_arithmetic_checks_pass",
            "independent_acceptance": False,
            "independent_reviewer": "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3",
            "checks": [
                "13actualrequests/44098bytes/caps/no-retries",
                "392rawentity/ordinal/canonicalrowhash bindings",
                "66price3 rows rederived with50digitDecimal endpoints/actions/populationstd",
                "65non-split-trigger conditional signal rows; causal-prefix endpoints",
                "AAPL dividend0.82oldshare/exAug7 distinctrecord/pay/process",
                "Six actual first eligible quote prefixes; exactns clocks",
                "Three split-aware quote-mid labels; Oct12entity shared",
                "ATVI emptyOct13exit/ghost remainsN/A;95right retained/no receipt",
                "historical first-visible null and strict/full7 false",
                "accepted parent/partial manifests unchanged, no repeatoldcase audit",
            ],
            "source_entity_records_parsed": 392,
            "normalized_records_checked": len(normalized),
            "price3_rows_checked": len(available),
            "labels_checked": len(labels),
            "resource": {
                "cpu_seconds": time.process_time() - cpu0,
                "wall_seconds": time.monotonic() - wall0,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            },
            "source_requests": 0,
            "fits": 0,
            "economic_computations": 0,
        },
    )
    print((OUT / "verification.json").read_text())


if __name__ == "__main__":
    main()
