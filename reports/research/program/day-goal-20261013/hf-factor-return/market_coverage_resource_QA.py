# ruff: noqa: E501
"""Actual partial market-input geometry and resource needs; no returns or models."""

import hashlib
import json
import math
import os
import resource
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

P = Path(__file__).parent


def b(path):
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def main():
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    ledgerpath = P / "market-input/market-request-ledger.json"
    ledger = json.loads(ledgerpath.read_text())
    assert len(ledger) == 15 and all(r["status"] == 200 and r["body_complete"] for r in ledger)
    by_time = {}
    pages = []
    for r in ledger:
        path = Path(r["path"])
        assert b(path)["sha256"] == r["sha256"] and path.stat().st_size == r["retained_bytes"]
        x = json.loads(path.read_bytes())
        values = x["bars"]["SPY"]
        assert values and x["next_page_token"]
        for row in values:
            tick = datetime.fromisoformat(row["t"].replace("Z", "+00:00"))
            assert tick.tzinfo is not None and tick not in by_time
            assert row["o"] > 0 and row["c"] > 0 and row["l"] > 0
            assert row["l"] <= min(row["o"], row["c"]) <= max(row["o"], row["c"]) <= row["h"]
            by_time[tick] = row
        pages.append(
            dict(
                b(path),
                rows=len(values),
                first=values[0]["t"],
                last=values[-1]["t"],
                next_page_present=True,
            )
        )
    ticks = sorted(by_time)
    timezone = ZoneInfo("America/New_York")
    funded = json.loads((P / "funded-SPY-clock-proposed.json").read_text())
    expected = {row["date"]: row for row in funded["rows"]}
    regular = {}
    for tick in ticks:
        local = tick.astimezone(timezone)
        row = expected.get(str(local.date()))
        if row and row["open"] <= str(local.time()) < row["close"]:
            regular.setdefault(str(local.date()), []).append(local)
    missing = []
    for day, values in regular.items():
        row = expected[day]
        start = datetime.combine(
            date.fromisoformat(day), datetime.strptime("09:30", "%H:%M").time(), timezone
        )
        wanted = {start + timedelta(minutes=15 * k) for k in range(row["regular15_windows"])}
        assert all(t.minute % 15 == 0 and t.second == 0 for t in values)
        missing.append(
            {
                "date": day,
                "regular_rows": len(values),
                "expected": len(wanted),
                "missing_times": [str(t) for t in sorted(wanted - set(values))],
            }
        )
    last_local_day = str(ticks[-1].astimezone(timezone).date())
    covered_days = [day for day in expected if day <= last_local_day]
    future_days = [day for day in expected if day > last_local_day]
    average_bytes = sum(r["bytes"] for r in ledger) / len(ledger)
    request_rate = len(ledger) / len(covered_days)
    expected_additional = math.ceil(request_rate * len(future_days))
    projected_bytes = average_bytes * expected_additional
    source = json.loads((P / "complete-source-input-QA.json").read_text())
    clock = {
        d["date"]: d for d in json.loads((P / "source-conditional-clock.json").read_text())["rows"]
    }
    previous = []
    sample_counts = Counter()
    packet_geometry = []
    for day in source["days"]:
        policy = clock.get(day["date"])
        if policy is None or not day["source_0930_separate"]:
            continue
        nominal = 14 if policy["nominal_source_close"] == "13:00:00" else 26
        complete = min(nominal, day["equal15_intraday_windows_before_observed_tail"])
        # Geometry derives each current packet from mature past/currentwindows.
        # Label availability is separately evaluated after target maturity.
        packet_valid = bool(previous and previous[-1]["complete"] >= 4 and len(previous) >= 20)
        valid_k = [
            k
            for k in range(4, nominal)
            if packet_valid and k <= complete and previous[-20]["complete"] >= k
        ]
        label_k = [k for k in valid_k if k + 1 <= complete]
        year = int(day["date"][:4])
        if year >= 1997:
            sample_counts[year] += len(label_k)
        packet_geometry.append(
            {
                "date": day["date"],
                "nominal": nominal,
                "complete": complete,
                "mature_packet_k": valid_k,
                "future_label_mature_k": label_k,
            }
        )
        previous.append({"date": day["date"], "complete": complete})
    n_prior2019 = sum(n for year, n in sample_counts.items() if year <= 2018)
    n_train2019 = math.floor(0.8 * n_prior2019)
    result = {
        "as_of_utc": datetime.now(UTC).isoformat(),
        "task_id": "DAY3-HF-FACTOR-RETURN",
        "role": "input_geometry_not_return_or_fit_evidence",
        "pages": pages,
        "market_HTTP_requests": 15,
        "market_actual_bytes": sum(r["bytes"] for r in ledger),
        "total_rows": len(ticks),
        "first_actual_UTC": str(ticks[0]),
        "last_actual_UTC": str(ticks[-1]),
        "next_page_token_present_at_bound": True,
        "requested_page_limit": 10000,
        "observed_rows_per_page_min_max": [
            min(p["rows"] for p in pages),
            max(p["rows"] for p in pages),
        ],
        "full_request_count_or_provider_internal_limit_certified": False,
        "regular_clock_days_observed": len(regular),
        "regular_rows": sum(len(v) for v in regular.values()),
        "actual_partial_day_grid_checks": missing,
        "funded_scope_expected_days": len(expected),
        "expected_days_through_last_date": len(covered_days),
        "expected_days_after_last_date": len(future_days),
        "last_local_date": last_local_day,
        "market_units_remaining": 0,
        "market_bytes_remaining": 12_657_184 - sum(r["bytes"] for r in ledger),
        "projection_not_actual": {
            "measured_requests_per_covered_day": request_rate,
            "mean_bytes_per_request": average_bytes,
            "linear_additional_requests": expected_additional,
            "linear_additional_response_bytes": projected_bytes,
            "assumption": "2016observedpage/calendar density extends; futureliquidity/aggregation/page count can vary. Exactfullpages/bytesN/A.",
            "proposed_extra_request_hard_cap": 120,
            "proposed_extra_byte_cap": 0,
            "same_old_global_16MiB_hard_byte_stop": True,
            "requests_not_yet_authorized": True,
        },
        "source_mature_geometry_not_featurevalues": {
            "eligible_rows_by_year_upper": dict(sorted(sample_counts.items())),
            "2019_train_rows_geometry_upper": n_train2019,
            "2019_float64_816X_bytes": n_train2019 * 816 * 8,
            "2019_binned_uint8_816X_bytes": n_train2019 * 816,
            "jump_tau_andactualfeature_label_gates_not_recomputed": True,
            "source_geometry": packet_geometry,
        },
        "claim_limits": "No complete2016..2020market input, no actualcostedstudy/NAV/MLfit. Geometry upperbounds exclude additionaltau/featureinvalidity, notmeasuredHGB RSS/CPU. Sourceacceptance andplan remainvalid but fullinput/native/economicreadyfalse; no posthoc short2016study orindex-as-SPY substitution.",
        "CPU_coreseconds": resource.getrusage(resource.RUSAGE_SELF).ru_utime
        + resource.getrusage(resource.RUSAGE_SELF).ru_stime,
        "max_RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    save(P / "market-input-coverage-and-resource-QA.json", result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "market_HTTP_requests",
                    "market_actual_bytes",
                    "total_rows",
                    "regular_rows",
                    "last_local_date",
                    "expected_days_after_last_date",
                    "projection_not_actual",
                    "CPU_coreseconds",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
