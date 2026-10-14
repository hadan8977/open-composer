"""Bound SMCI-only input repair: undo known 10:1 rounding coordinates, no P&L."""

import json
import resource
import time
from pathlib import Path
from collections import defaultdict
from datetime import UTC, date, datetime, time as day_time, timedelta

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from open_composer.market_sessions import NEW_YORK, us_equity_session_close, us_equity_session_dates
from prepare_complete_inputs import P, ROOT, bind


def main():
    started = time.process_time()
    resource.setrlimit(resource.RLIMIT_CPU, (55, 60))
    manifest = json.loads((P / "complete-input-job-manifest.json").read_text())
    original = json.loads((P / "complete-input-result.json").read_text())
    actions = json.loads((P / "inputs/full-v1/actions.json").read_text())
    split = next(
        a["row"] for a in actions if a["kind"] == "forward_splits" and a["row"]["symbol"] == "SMCI"
    )
    assert split["ex_date"] == "2024-10-01" and split["new_rate"] == 10 and split["old_rate"] == 1
    shards = [
        e
        for e in manifest["minute_inputs"]
        if e["symbol"] == "SMCI" and (e["year"], e["month"]) <= (2024, 10)
    ]
    inputs = [
        bind(P / "complete-input-result.json"),
        bind(P / "basis-probe.json"),
        bind(P / "inputs/full-v1/actions.json"),
    ]
    job = dict(
        inputs=inputs,
        shards=shards,
        implementation=bind(Path(__file__).resolve()),
        CPU_upper=60,
        new_HTTP=0,
        fit=0,
        PnL=0,
        evidence_class="known-split coordinate; minute raw precision remains unresolved before split",
    )
    (P / "split-basis-repair-manifest.json").write_text(json.dumps(job, indent=2) + "\n")
    out = P / "inputs/split-basis-v2"
    out.mkdir(parents=True, exist_ok=False)
    con = duckdb.connect()
    con.execute("SET threads=1")
    con.execute("SET memory_limit='250MB'")
    replacements = []
    outputs = []
    for e in shards:
        b = e["binding"]
        assert bind(ROOT / b["path"]) == b
        key = f"{e['year']}-{e['month']:02}"
        old = pq.read_table(P / f"inputs/full-v1/{key}.parquet").to_pylist()
        other = [r for r in old if r["symbol"] != "SMCI"]
        raw = con.execute(
            "SELECT timestamp,open,high,low,close,volume,vwap FROM read_parquet(?) WHERE symbol='SMCI' ORDER BY timestamp",
            [str(ROOT / b["path"])],
        ).fetchall()
        byday = defaultdict(list)
        for r in raw:
            byday[r[0].astimezone(NEW_YORK).date()].append(r)
        end = date(e["year"] + 1, 1, 1) if e["month"] == 12 else date(e["year"], e["month"] + 1, 1)
        for d in us_equity_session_dates(date(e["year"], e["month"], 1), end - timedelta(days=1)):
            factor = 10.0 if str(d) < split["ex_date"] else 1.0
            op = datetime.combine(d, day_time(9, 30), tzinfo=NEW_YORK).astimezone(UTC)
            cl = datetime.combine(d, us_equity_session_close(d), tzinfo=NEW_YORK).astimezone(UTC)
            expected = {
                op + timedelta(minutes=i) for i in range(int((cl - op).total_seconds() / 60))
            }
            seen = set()
            for t, o, h, low, c, v, vw in byday[d]:
                if t not in expected:
                    continue
                assert t not in seen and low <= min(o, c) <= max(o, c) <= h
                if v <= 0:
                    continue
                seen.add(t)
                other.append(
                    dict(
                        symbol="SMCI",
                        timestamp=t,
                        open=o * factor,
                        high=h * factor,
                        low=low * factor,
                        close=c * factor,
                        volume=v / factor,
                        vwap=vw * factor,
                        prior_basis="bound-known-split-chain",
                        price_factor=factor,
                        volume_factor=1 / factor,
                    )
                )
            replacements.append(
                dict(
                    symbol="SMCI",
                    day=str(d),
                    status="known_split_conditional_precision",
                    expected=len(expected),
                    observed=len(seen),
                    missing=[t.isoformat() for t in sorted(expected - seen)],
                    duplicate=[],
                    invalid=[],
                    price_factor=factor,
                    volume_factor=1 / factor,
                    exact_raw_certified=False,
                    source_rounding_raw_coordinate_half_cent=factor * 0.005,
                )
            )
        dest = out / (key + ".parquet")
        pq.write_table(pa.Table.from_pylist(other), dest, compression="zstd")
        outputs.append(bind(dest))
    replaced = {r["day"] for r in replacements}
    sessions = [
        r for r in original["sessions"] if not (r["symbol"] == "SMCI" and r["day"] in replaced)
    ] + replacements
    mapped = {Path(b["path"]).name: b for b in original["outputs"]}
    mapped.update({Path(b["path"]).name: b for b in outputs})
    result = dict(
        original_input_result=inputs[0],
        repair_manifest=bind(P / "split-basis-repair-manifest.json"),
        outputs=[mapped[k] for k in sorted(mapped)],
        auxiliary_outputs=original["auxiliary_outputs"],
        sessions=sessions,
        precision_residual="Known split inversion removes scalar drift but cannot recover rounded historical minute raw prices. No exact raw extrapolation.",
        CPU=time.process_time() - started,
        RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        HTTP=0,
        fit=0,
        PnL=0,
    )
    (P / "complete-input-v2-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                symbol_days=len(sessions),
                complete=sum(r.get("expected") == r.get("observed") for r in sessions),
                residual_basis_days=sum(r["status"] == "nonuniform_prior_basis" for r in sessions),
                CPU=result["CPU"],
            )
        )
    )


if __name__ == "__main__":
    main()
