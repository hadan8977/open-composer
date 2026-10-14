# ruff: noqa: E501
"""Independent read pass over actual source payload hashes and timestamp columns.

No factor scores, labels, models, forecasts or economic returns are produced.
"""

import hashlib
import json
import os
import resource
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from open_composer.market_sessions import us_equity_session_close, us_equity_session_dates

P = Path(__file__).parent
resource.setrlimit(resource.RLIMIT_CPU, (200, 200))
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
pa.set_cpu_count(1)
pa.set_io_thread_count(1)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binding(path):
    return {"path": str(path), "sha256": sha(path), "bytes": path.stat().st_size}


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def main():
    progress_path = P / "complete-input-progress.json"
    progress = json.loads(progress_path.read_text())
    assert progress["process_exit_status"] == 0 and progress["complete_months"] == 300
    manifest_path = P / "complete-input-request-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert sha(manifest_path) == "40c2e73e8f81bdc26c8add44022a6be2a120a2eaa89e96d0079979dd035c2c3a"
    requests = {row["month"]: row for row in manifest["files"]}
    files = {row["month"]: row for row in progress["files"]}
    assert len(files) == len(requests) == 300 and files.keys() == requests.keys()
    ledger_path = P / "continuation-source-request-ledger.json"
    ledger = json.loads(ledger_path.read_text())
    columns = pq.read_metadata(Path(files["199601"]["path"])).schema.names
    days = []
    file_bindings = []
    for month in sorted(files):
        expected = files[month]
        path = Path(expected["path"])
        actual = binding(path)
        assert actual["sha256"] == expected["sha256"] and actual["bytes"] == expected["bytes"]
        if requests[month]["size_bytes_verified"] is not None:
            assert actual["bytes"] == requests[month]["size_bytes_verified"]
        meta = pq.read_metadata(path)
        assert meta.schema.names == columns and meta.num_rows == expected["rows"]
        if month != "199601":
            receipt = next(r for r in reversed(ledger) if r.get("path") == str(path))
            assert receipt["status"] == 200 and receipt["body_complete"]
            assert receipt["sha256"] == actual["sha256"] and receipt["bytes"] == actual["bytes"]
            assert receipt["url"] == requests[month]["url"]
        ticks = pq.read_table(path, columns=["datetime"], use_threads=False).column(0).to_pylist()
        assert ticks == sorted(ticks) and len(set(ticks)) == len(ticks)
        assert all(t.tzinfo is None and t.strftime("%Y%m") == month for t in ticks)
        by_date = {}
        for tick in ticks:
            by_date.setdefault(tick.date(), []).append(tick)
        rederived = []
        for day, values in by_date.items():
            tickset = set(values)
            anchor = datetime.combine(day, time(9, 30))
            gaps = sum(
                (b - a).total_seconds() != 60 for a, b in zip(values, values[1:], strict=False)
            )
            row = {
                "date": str(day),
                "rows": len(values),
                "first": str(values[0]),
                "last": str(values[-1]),
                "non_one_minute_steps": gaps,
                "duplicate_times": 0,
            }
            rederived.append(row)
            helper_close = us_equity_session_close(day)
            nominal = (
                None if helper_close is None else day.strftime("%Y-%m-%d ") + str(helper_close)
            )
            row = dict(
                row,
                local_rule_helper_close=nominal,
                observed_tail_matches_helper=nominal == row["last"],
                source_0930_separate=values[0].strftime("%H:%M:%S") == "09:30:00",
                equal15_intraday_windows_before_observed_tail=sum(
                    all(
                        anchor + timedelta(minutes=15 * k + minute) in tickset
                        for minute in range(1, 16)
                    )
                    for k in range(26)
                ),
            )
            days.append(row)
        assert rederived == expected["days"]
        assert (
            expected["nonfinite_values"]
            == expected["NaN_values"]
            == expected["infinite_values"]
            == 0
        )
        assert expected["values_not_in_log1p_domain"] == 0
        file_bindings.append(
            dict(
                actual,
                month=month,
                rows=meta.num_rows,
                columns=meta.num_columns,
                source_QA_values_verified_by_first_pass=True,
            )
        )
    assert len({d["date"] for d in days}) == len(days)
    start, end = date.fromisoformat(days[0]["date"]), date.fromisoformat(days[-1]["date"])
    observed = {d["date"] for d in days}
    helper = {str(d) for d in us_equity_session_dates(start, end)}
    result = {
        "as_of_utc": datetime.now(UTC).isoformat(),
        "task_id": "DAY3-HF-FACTOR-RETURN",
        "verification_role": "owner_sourceQA_not_independent_scientific_review",
        "required_and_received_months": 300,
        "first_month": "199601",
        "last_month": "202012",
        "total_actual_monthly_file_bytes": sum(r["bytes"] for r in file_bindings),
        "total_actual_rows": sum(r["rows"] for r in file_bindings),
        "factor_columns": columns[:-1],
        "timestamp_column": columns[-1],
        "numeric_type": "DOUBLE",
        "timezone_metadata": "isAdjustedToUTC=false, naive; NYendtick is APP convention, not proven",
        "source_value_QA_first_pass": "Everyfullmonth272columns checked finite/log1pdomain/schema/order/duplicates, not sampled; rawvalueQA is bound in progress",
        "this_second_pass": "Everymonth SHA/size/metadata/schema/timezone andeverytimestamp re-read; exactperday first-pass metadata equality. Values not re-read secondtime.",
        "bindings": {
            "request_manifest": binding(manifest_path),
            "source_progress": binding(progress_path),
            "actual_cumulative_ledger": binding(ledger_path),
            "initial_resolution_ledger_immutable": binding(
                P / "resolution-sources/continuation-ledger-at-independent-scope-review.json"
            ),
            "recovery": binding(P / "source-intake-recovery-500.json"),
            "oneCPU_repair": binding(P / "source-QA-singleCPU-repair.json"),
        },
        "files": file_bindings,
        "days": days,
        "observed_days": len(days),
        "row_count_distribution": dict(Counter(d["rows"] for d in days)),
        "helper_expected_source_absent": sorted(helper - observed),
        "source_present_helper_closed": sorted(observed - helper),
        "source_tails_not_equal_existing_helper": [
            d for d in days if not d["observed_tail_matches_helper"]
        ],
        "calendar_admission": "Localrulehelper is notfull1996..2020 verifiedcalendar; defects/dateexceptions andpostearlyclose tails preserved. Need separately boundfixedhistoryclock beforedependentaggregation. Rawinputcomplete doesnotcertifycalendar/PIT/source15mlegs.",
        "source_fit_or_economic_runs": 0,
        "input_market_economic_ready": False,
        "CPU_coreseconds": resource.getrusage(resource.RUSAGE_SELF).ru_utime
        + resource.getrusage(resource.RUSAGE_SELF).ru_stime,
        "peak_RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    save(P / "complete-source-input-QA.json", result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "required_and_received_months",
                    "total_actual_monthly_file_bytes",
                    "total_actual_rows",
                    "observed_days",
                    "CPU_coreseconds",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
