"""Availability-only QA of already accepted small raw15 inputs; no account run."""

import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
from hf_execution_policy import scheduled_reference_available

P = Path(__file__).resolve().parent
ROOT = Path.cwd()
OLD = P.parent
manifest_path = P / "execution-input-manifest.json"
manifest = json.loads(manifest_path.read_text())
days = json.loads((OLD / "funded-SPY-clock-proposed.json").read_text())["rows"]
expected = {r["date"]: r["regular15_windows"] for r in days[1:]}
bars = {}
for binding in manifest["price_inputs"]:
    path = ROOT / binding["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]
    for row in pq.read_table(
        path,
        columns=[
            "date",
            "window_minute",
            "open",
            "close",
            "first_price_age_minutes",
            "last_price_age_to_window_end_minutes",
        ],
        use_threads=False,
    ).to_pylist():
        day = str(row["date"].date()) if hasattr(row["date"], "date") else str(row["date"])
        if day in expected:
            bars.setdefault(day, {})[(row["window_minute"] - 570) // 15] = row
start_unknown, end_unknown, risk_incomplete, start_bad, end_bad = [], [], [], [], []
for day, n in expected.items():
    rows = bars.get(day, {})
    bad_start = [k for k in range(n) if not scheduled_reference_available(rows.get(k, {}), "open")]
    bad_end = [k for k in range(n) if not scheduled_reference_available(rows.get(k, {}), "close")]
    if bad_start:
        start_unknown.append(day)
        start_bad.extend({"date": day, "ordinal": k} for k in bad_start)
    if bad_end:
        end_unknown.append(day)
        end_bad.extend({"date": day, "ordinal": k} for k in bad_end)
    if bad_start or bad_end:
        risk_incomplete.append(day)
result = {
    "scope": (
        "Endpoint availability only; reused actual raw15 inputs, no model/account/PnL evaluation"
    ),
    "execution_input_manifest": {
        "path": str(manifest_path.relative_to(ROOT)),
        "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    },
    "scheduled_close_definition": (
        "last one-minute close at window_minute+14, zero last_price_age_to_window_end_minutes"
    ),
    "funded_sessions_after_initializer": len(expected),
    "complete_risk_sessions": len(expected) - len(risk_incomplete),
    "incomplete_risk_sessions": risk_incomplete,
    "unknown_start_exposure_sessions": start_unknown,
    "unavailable_scheduled_starts": start_bad,
    "unavailable_scheduled_closes": end_bad,
    "price_input_bindings": manifest["price_inputs"],
    "new_financial_runs": 0,
    "new_inference": 0,
    "new_requests": 0,
    "large_original_source_reread": False,
}
(P / "revision-input-clock-QA.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            k: result[k]
            for k in [
                "funded_sessions_after_initializer",
                "complete_risk_sessions",
                "unknown_start_exposure_sessions",
                "incomplete_risk_sessions",
            ]
        }
    )
)
