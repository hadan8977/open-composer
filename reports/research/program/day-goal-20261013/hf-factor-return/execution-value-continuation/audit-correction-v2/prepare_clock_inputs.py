"""Accepted minute-cache reuse and recent selected-asset input QA; no return/account computation."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pyarrow.parquet as pq

ROOT = Path.cwd()
Q = Path(__file__).resolve().parent
P = Q.parent
OLD = P.parent
TZ = ZoneInfo("America/New_York")


def bind(path):
    path = path.resolve()
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
    (Q / name).write_text(json.dumps(value, indent=2) + "\n")


days = json.loads((OLD / "funded-SPY-clock-proposed.json").read_text())["rows"]
byday = {row["date"]: (i, 570 + 15 * row["regular15_windows"]) for i, row in enumerate(days)}
accepted = json.loads((OLD / "market-input/cache-bridge/cache-bridge-QA.json").read_text())
records = []
source = []
for year in accepted["annual"]:
    for page in year["pages"]:
        binding = page["raw"]
        path = ROOT / binding["path"]
        assert bind(path)["sha256"] == binding["sha256"]
        source.append(binding)
        content = json.loads(path.read_bytes())
        for row in content["bars"]["SPY"]:
            stamp = datetime.fromisoformat(row["t"].replace("Z", "+00:00")).astimezone(TZ)
            day = stamp.date().isoformat()
            if day not in byday:
                continue
            index, close = byday[day]
            minute = stamp.hour * 60 + stamp.minute
            if not 570 <= minute < close:
                continue
            records.append((index, minute, float(row["o"]), float(row["c"]), float(row["v"])))
        del content
records.sort(key=lambda row: (row[0], row[1]))
keys = [1440 * r[0] + r[1] for r in records]
assert len(keys) == len(set(keys)) and len(records) == 488935
rowof = {key: i for i, key in enumerate(keys)}
price = np.array([r[2:4] for r in records], dtype="float64")
np.savez_compressed(
    Q / "historical-raw-minute-input.npz",
    day=np.array([r[0] for r in records], dtype="int16"),
    minute=np.array([r[1] for r in records], dtype="int16"),
    open=price[:, 0],
    close=price[:, 1],
    volume=np.array([r[4] for r in records], dtype="float64"),
)
packet = np.load(P / "execution-input-packets.npz")
known = np.full(len(packet["day"]), np.nan)
arrival = np.full((len(known), 3), np.nan)
endpoint = np.full((len(known), 3), np.nan)
legal = np.zeros((len(known), 3), dtype=bool)
common = np.zeros(len(known), dtype=bool)
for i, (di, m) in enumerate(zip(packet["day"], packet["minute"], strict=True)):
    di, m = int(di), int(m)
    session_close = byday[days[di]["date"]][1]
    previous = rowof.get(di * 1440 + m - 1)
    if previous is not None:
        known[i] = price[previous, 1]
    common[i] = m + 15 < session_close  # Same opportunity set as the old L15 clock.
    for j, delay in enumerate([1, 5, 15]):
        at = m + delay
        end = m + 15 if delay < 15 else m + 30
        legal[i, j] = di > 0 and at < session_close and end <= session_close
        fill = rowof.get(di * 1440 + at)
        last = rowof.get(di * 1440 + end - 1)
        if fill is not None:
            arrival[i, j] = price[fill, 0]
        if last is not None:
            endpoint[i, j] = price[last, 1]
np.savez_compressed(
    Q / "timely-reference-input.npz",
    day=packet["day"],
    minute=packet["minute"],
    score=packet["score"],
    original_label_mature=packet["original_label_mature"],
    original_cts_label_available=packet["original_cts_label_available"],
    known_before_boundary_close=known,
    arrival_open=arrival,
    payoff_endpoint_close=endpoint,
    legal=legal,
    common_opportunity=common,
)
# Selected current local SPY assets only. Do not scan the cloud tree/universe.
recent = []
for kind, path in [
    ("minute", "data/sip/minute/2026/09/shard-0927.parquet"),
    ("minute", "data/sip/minute/2026/10/shard-0927.parquet"),
    ("daily", "data/sip/daily/2026/shard-0278.parquet"),
]:
    f = ROOT / path
    meta = pq.ParquetFile(f)
    names = meta.schema_arrow.names
    timestamp = "timestamp" if "timestamp" in names else "time" if "time" in names else "date"
    table = pq.read_table(
        f, columns=["symbol", timestamp], filters=[("symbol", "=", "SPY")], use_threads=False
    )
    times = table[timestamp].to_pylist()
    assert times
    recent.append(
        {
            "kind": kind,
            "binding": bind(f),
            "schema": str(meta.schema_arrow),
            "SPY_rows": len(times),
            "first_timestamp": str(min(times)),
            "last_timestamp": str(max(times)),
            "adjustment": "all per fetch_sip_universe/update_sip_archive code; not raw physical share price",
            "economic_returns_computed": False,
        }
    )
qa = {
    "historical_raw_minute_rows": len(records),
    "original_packet_rows": len(known),
    "clocks": ["A1", "A5", "L15"],
    "legal_counts": legal.sum(axis=0).tolist(),
    "reference_price_missing_on_legal": (legal & ~np.isfinite(arrival)).sum(axis=0).tolist(),
    "payoff_endpoint_missing_on_legal": (legal & ~np.isfinite(endpoint)).sum(axis=0).tolist(),
    "common_opportunity_rows_excluding_initializer": int((common & (packet["day"] > 0)).sum()),
    "future_label_masks_not_used_for_eligibility": True,
    "old_market_cache_acceptance_reused": True,
    "source_page_bindings": source,
    "new_outputs": [
        bind(Q / "historical-raw-minute-input.npz"),
        bind(Q / "timely-reference-input.npz"),
    ],
    "recent_selected_asset_metadata": recent,
    "recent_only_information_and_normalized_return_eligible": True,
    "recent_raw_share_cash_or_272factor_readiness": False,
    "new_market_requests": 0,
    "new_models_or_inference": 0,
    "financial_runs": 0,
}
save("actual-input-readiness.json", qa)
print(
    json.dumps(
        {
            k: qa[k]
            for k in [
                "historical_raw_minute_rows",
                "original_packet_rows",
                "legal_counts",
                "reference_price_missing_on_legal",
                "payoff_endpoint_missing_on_legal",
                "recent_selected_asset_metadata",
            ]
        }
    )
)
