"""Feature-only cache parity/performance witness, no orders or market P&L.

Hourly fixture is deliberately synthetic, labeled here and excluded from the
consumer inputs. Tests exact static-cache equivalence across 1/5/15 switches.
"""

import json
import time
from datetime import date, timedelta
from pathlib import Path
import pyarrow.parquet as pq
from decision_system import read_parameters
from frame_producer import FrameProducer, SYMBOLS
from geometry import Day
from prepare_complete_inputs import P, ROOT, bind


def main():
    root = P / "inputs/full-v1"
    daily = json.loads((root / "daily-basis.json").read_text())
    actions = json.loads((root / "actions.json").read_text())
    indexes = pq.read_table(root / "indexes.parquet").to_pylist()
    params = read_parameters(ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml")
    day = date(2024, 6, 3)
    prices = pq.read_table(root / "2024-06.parquet").to_pylist()
    bytime = {}
    for r in prices:
        if r["timestamp"].date() == day:
            bytime.setdefault(r["timestamp"], {})[r["symbol"]] = r
    results = []
    times = []
    for cached in (False, True):
        f = FrameProducer(params, daily, indexes, actions, cache_frames=cached)
        f.begin_session(day)
        for s in SYMBOLS:
            f.hours[s] = [
                Day(f.open - timedelta(hours=24 + i), 10, 11, 9, 10, 100000, 10)
                for i in reversed(range(150))
            ]
        started = time.process_time()
        rows = []
        for minute in range(390):
            rows.extend(
                f.complete_minute(minute, bytime.get(f.open + timedelta(minutes=minute), {}))
            )
        results.append(json.dumps(rows, default=lambda x: x.isoformat(), sort_keys=True))
        times.append(time.process_time() - started)
    assert results[0] == results[1], "cached fields changed actual frame semantics"
    result = dict(
        status="exact_serialized_Frame_parity",
        reference_CPU=times[0],
        cached_CPU=times[1],
        reference_and_cached_fixture_Sha=__import__("hashlib")
        .sha256(results[0].encode())
        .hexdigest(),
        minute_bars=390,
        hourly_fixture="synthetic performance witness, not admissible market features",
        new_policy_evaluations=0,
        new_PnL=0,
        implementation=bind(Path(__file__).resolve()),
    )
    (P / "frame-cache-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
