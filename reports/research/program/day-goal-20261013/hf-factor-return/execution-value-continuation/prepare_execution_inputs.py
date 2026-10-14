"""Bind and inspect actual small inputs; never simulate a real account or refit a model."""

import hashlib
import json
import os
import resource
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from hf_execution_policy import Clock

P = Path(__file__).resolve().parent
OLD = P.parent
ROOT = Path.cwd()
STREAMS = [
    "PLS_IDX_CTS",
    "PLS_IDX_MKT",
    "PLS_IDX_STALE",
    "PLS_INV_CTS",
    "HGB_IDX_CTS",
    "AR26_CTS",
    "ZERO",
    "NEG_PLS",
]


def bind(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
    }


def save(name, value):
    (P / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU, (120, 121))
    at = datetime.now(UTC).isoformat()
    local = json.loads((P / "local-source-and-preparation-bindings.json").read_text())
    expected = {row["path"]: row for row in local["bindings"]}
    forecast_files = [
        OLD / "features/packet-row-clock.json",
        OLD / "economic/linear-predictions.npy",
        OLD / "economic/HGB-predictions.npy",
    ]
    actual = [bind(path) for path in forecast_files]
    assert all(row == expected[row["path"]] for row in actual)
    days_path = OLD / "funded-SPY-clock-proposed.json"
    days = json.loads(days_path.read_text())["rows"]
    assert len(days) == 1259
    day_index = {row["date"]: i for i, row in enumerate(days)}
    records = json.loads(forecast_files[0].read_text())
    linear = np.load(forecast_files[1], mmap_mode="r")
    nonlinear = np.load(forecast_files[2], mmap_mode="r")
    manifests = [
        OLD / "economic/linear-model-manifest.json",
        OLD / "economic/HGB-model-manifest.json",
    ]
    linear_ids, nonlinear_ids = [
        json.loads(path.read_text())["candidate_ids"] for path in manifests
    ]
    assert linear.shape == (len(records), len(linear_ids))
    assert nonlinear.shape == (len(records), len(nonlinear_ids))
    selected = [i for i, row in enumerate(records) if row["date"] in day_index]
    source_row, decision_minute, source_day = [], [], []
    label_mature, cts_label_available, legal = [], [], []
    score = np.full((len(selected), len(STREAMS)), np.nan, dtype="float64")
    representative = {}
    for out_row, source_id in enumerate(selected):
        row = records[source_id]
        day, minute = row["date"], row["minute"]
        n = days[day_index[day]]["regular15_windows"]
        clock = Clock(day, minute, 570 + 15 * n)
        current_legal = 630 <= minute and clock.remaining_intraday_windows > 0
        source_row.append(source_id)
        decision_minute.append(minute)
        source_day.append(day_index[day])
        label_mature.append(row["target_mature"])
        cts_label_available.append(row["cts_target_available"])
        legal.append(current_legal)
        for col, stream in enumerate(STREAMS):
            if stream == "ZERO":
                score[out_row, col] = 0
            elif stream == "NEG_PLS":
                score[out_row, col] = -linear[source_id, linear_ids.index("PLS_IDX_CTS")]
            elif stream in linear_ids:
                score[out_row, col] = linear[source_id, linear_ids.index(stream)]
            else:
                score[out_row, col] = nonlinear[source_id, nonlinear_ids.index(stream)]
        key = (
            "ordinary_near_close"
            if n == 26 and minute >= 930
            else "short_near_close"
            if n == 14 and minute >= 750
            else "first_mature"
        )
        representative.setdefault(key, clock.record())
    assert len({(d, m) for d, m in zip(source_day, decision_minute, strict=True)}) == len(selected)
    compact_path = P / "execution-input-packets.npz"
    np.savez(
        compact_path,
        source_row=np.array(source_row, dtype="int64"),
        day=np.array(source_day, dtype="int16"),
        minute=np.array(decision_minute, dtype="int16"),
        score=score,
        original_label_mature=np.array(label_mature, dtype=bool),
        original_cts_label_available=np.array(cts_label_available, dtype=bool),
        current_legal=np.array(legal, dtype=bool),
    )
    price_bindings, price_qa = [], []
    for year in range(2016, 2021):
        path = OLD / "market-input/cache-bridge" / f"SPY-raw15-aggregated-{year}.parquet"
        price_bindings.append(bind(path))
        rows = pq.read_table(path, use_threads=False).to_pylist()
        seen, delayed, invalid = set(), 0, 0
        for row in rows:
            day = str(row["date"].date()) if hasattr(row["date"], "date") else str(row["date"])
            assert day in day_index
            minute = row["window_minute"]
            key = day, minute
            assert key not in seen
            seen.add(key)
            n = days[day_index[day]]["regular15_windows"]
            assert 570 <= minute < 570 + 15 * n and (minute - 570) % 15 == 0
            delayed += int(row["first_price_age_minutes"] != 0)
            invalid += int(not all(np.isfinite(row[k]) and row[k] > 0 for k in ["open", "close"]))
        price_qa.append(
            {
                "year": year,
                "rows": len(rows),
                "duplicate_windows": 0,
                "late_first_references": delayed,
                "nonfinite_or_nonpositive_prices": invalid,
                "observed_missing_windows_not_filled": True,
                "column_names": pq.read_schema(path).names,
            }
        )
    other_paths = [
        days_path,
        *manifests,
        OLD / "market-input/cache-bridge/SPY-BIL-bound-actions.json",
        OLD.parent / "primary-return-breadth/inputs/bars_raw-01.json",
        OLD.parent / "primary-return-breadth/cash-calendar.json",
        OLD / "economic/results/SPY_BH__20-ledger.json",
        OLD / "economic/results/SPY_BH__40-ledger.json",
        OLD / "economic/results/BIL_BH__20-ledger.json",
        OLD / "economic/results/SPY_OVERNIGHT_ONLY__20-ledger.json",
    ]
    other = [bind(path) for path in other_paths]
    passive = json.loads((OLD / "economic/results/SPY_BH__20-ledger.json").read_text())
    assert [row["date"] for row in passive["daily"]] == [row["date"] for row in days]
    actions = json.loads(
        (OLD / "market-input/cache-bridge/SPY-BIL-bound-actions.json").read_text()
    )["actions"]
    save(
        "execution-input-QA.json",
        {
            "at_utc": at,
            "stage": "read_only_small_input_preparation",
            "inputs_ready_conditional": True,
            "source_current_vintage_PIT_certified": False,
            "model_manifest_order_and_packet_identity_verified": True,
            "source_packet_rows_read": len(records),
            "physical_packet_rows_retained": len(selected),
            "current_legal_rows": sum(legal),
            "future_label_unmatured_rows_retained": sum(not b for b in label_mature),
            "future_label_mask_used_to_select_current_rows": False,
            "streams": STREAMS,
            "finite_scores": dict(zip(STREAMS, np.isfinite(score).sum(0).tolist(), strict=True)),
            "clock_examples": representative,
            "price_QA": price_qa,
            "SPY_non_dividend_actions_in_physical_period": [
                a
                for a in actions
                if a["symbol"] == "SPY"
                and a["type"] != "cash_dividends"
                and days[0]["date"] <= a["ex_date"] <= days[-1]["date"]
            ],
            "old_passive_daily_clock_compatible": True,
            "old_real_accounts_resimulated": 0,
            "actual_returns_or_new_policy_performance_computed": False,
            "model_training_or_inference": 0,
            "new_market_or_source_requests": 0,
        },
    )
    save(
        "execution-input-manifest.json",
        {
            "schema_version": 3,
            "iter_id": "t20261014_hf_execution_value",
            "inherited_source_acceptance": bind(
                OLD / "independent-complete-source-input-acceptance.json"
            ),
            "inherited_full_result_acceptance": bind(OLD / "independent-result-review.json"),
            "inherited_price_bridge_acceptance": bind(
                OLD / "independent-market-cache-bridge-acceptance.json"
            ),
            "original_source_inputs": actual,
            "price_inputs": price_bindings,
            "other_inputs": other,
            "actual_financial_read_inputs": [bind(compact_path), *price_bindings, *other],
            "new_compact_packet": bind(compact_path),
            "input_QA": bind(P / "execution-input-QA.json"),
            "no_large_source_reread": True,
            "economic_execution_admitted": False,
        },
    )
    usage = resource.getrusage(resource.RUSAGE_SELF)
    print(
        json.dumps(
            {
                "input_QA": "ready_conditional",
                "packet_rows": len(selected),
                "source_unmatured_rows_retained": sum(not b for b in label_mature),
                "CPU": usage.ru_utime + usage.ru_stime,
                "max_RSS_KiB": usage.ru_maxrss,
                "financial_runs": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
