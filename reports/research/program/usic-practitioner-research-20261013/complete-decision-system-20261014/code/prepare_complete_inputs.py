"""Existing-input basis/calendar/action preparation under the approved R1 scope.

No HTTP, fills, P&L, fitted model or policy evaluation. Missing/action intervals
remain explicit. This program is resource capped by its caller and CPU rlimit.
"""

from __future__ import annotations

import hashlib
import json
import math
import resource
import time
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from datetime import time as day_time
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from open_composer.market_sessions import NEW_YORK, us_equity_session_close, us_equity_session_dates
from open_composer.research.features.price_hygiene import sanitize_price_matrices

P = Path(__file__).resolve().parents[1]
ROOT = Path.cwd()
SYMBOLS = ["COIN", "GME", "LMND", "SMCI", "SOFI", "SOUN"]


def bind(path):
    with path.open("rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    return dict(path=str(path.relative_to(ROOT)), sha256=sha, bytes=path.stat().st_size)


def freeze():
    inv = json.loads((P / "input-inventory.json").read_text())
    inputs = [e["entity"] for e in inv["entities"]]
    minute = []
    for r in inv["minute_clock_coverage"]:
        if len(r["observed"]) != 1:
            raise ValueError(
                "ambiguous or absent already-inventoried source; explicit resolution required"
            )
        minute.append(
            dict(
                symbol=r["symbol"],
                year=r["year"],
                month=r["month"],
                binding=r["observed"][0]["entity"],
            )
        )
    layout = json.loads((ROOT / "data/sip/minute/_LAYOUT.json").read_text())["shard_symbols"]
    for symbol in SYMBOLS:
        for k, symbols in layout.items():
            f = ROOT / f"data/sip/minute/2023/12/shard-{int(k):04d}.parquet"
            if symbol in symbols and f.is_file():
                minute.append(dict(symbol=symbol, year=2023, month=12, binding=bind(f)))
    layout = json.loads((ROOT / "data/sip/daily/_LAYOUT.json").read_text())["shard_symbols"]
    allsyms = sorted({s for v in layout.values() for s in v})
    indexes = []
    for symbol in ("QQQ", "IWM"):
        shards = {int(k) for k, v in layout.items() if symbol in v} | {allsyms.index(symbol) // 40}
        for year in (2023, 2024, 2025):
            for k in sorted(shards):
                f = ROOT / f"data/sip/daily/{year}/shard-{k:04d}.parquet"
                if f.is_file():
                    indexes.append(dict(symbol=symbol, year=year, binding=bind(f)))
    review = bind(P / "revisions/r1/independent-review.json")
    assert review["sha256"] == "3bf332391c61b79225255de63d7b0cc1696fd241975f397e5dd9e8f9b9ebf1d1"
    result = dict(
        schema_version=1,
        review=review,
        scientific_plan=bind(P / "revisions/r1/scientific-plan-v2.json"),
        entity_inputs=inputs,
        minute_inputs=minute,
        index_inputs=indexes,
        new_HTTP=0,
        fit=0,
        PnL=0,
        preparation_CPU_upper=180,
        CPUs=1,
        memory_MiB=900,
        scope=("2024-25 six seen symbols, necessary Dec2023 hourly warmup "
               "and 2023-25 QQQ/IWM daily context"),
        exact_raw_certified=False,
        current_vintage=True,
    )
    (P / "complete-input-job-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    started = time.process_time()
    resource.setrlimit(resource.RLIMIT_CPU, (170, 175))
    manifest = freeze()  # Exact input bindings persist BEFORE price-column reads.
    out = P / "inputs/full-v1"
    out.mkdir(parents=True, exist_ok=False)
    con = duckdb.connect()
    con.execute("SET threads=1")
    con.execute("SET memory_limit='300MB'")
    daily = defaultdict(lambda: defaultdict(dict))
    actions = []
    for b in manifest["entity_inputs"]:
        assert bind(ROOT / b["path"]) == b
        obj = json.loads((ROOT / b["path"]).read_text())
        for kind, rows in obj.get("corporate_actions", {}).items():
            actions.extend(dict(kind=kind, row=r) for r in rows)
        for symbol, rows in obj.get("bars", {}).items():
            if symbol not in SYMBOLS or not rows:
                continue
            if "daily_raw" in b["path"]:
                adjustment = "raw"
            elif "daily_all" in b["path"]:
                adjustment = "all"
            else:
                continue
            for r in rows:
                d = (
                    datetime.fromisoformat(r["t"].replace("Z", "+00:00"))
                    .astimezone(NEW_YORK)
                    .date()
                )
                daily[adjustment][symbol][d.isoformat()] = r
    (out / "daily-basis.json").write_text(json.dumps(daily) + "\n")
    (out / "actions.json").write_text(json.dumps(actions, indent=2) + "\n")
    indexrows = []
    sources = []
    for e in manifest["index_inputs"]:
        assert bind(ROOT / e["binding"]["path"]) == e["binding"]
        rows = con.execute(
            "SELECT timestamp,open,high,low,close,volume,vwap FROM read_parquet(?) WHERE symbol=? ORDER BY timestamp",
            [str(ROOT / e["binding"]["path"]), e["symbol"]],
        ).fetchall()
        sources.append(dict(**e, rows=len(rows)))
        indexrows.extend(
            dict(symbol=e["symbol"], timestamp=t, open=o, high=h, low=l, close=c, volume=v, vwap=vw)
            for t, o, h, l, c, v, vw in rows
        )
    df = pd.DataFrame(indexrows)
    if df.duplicated(["symbol", "timestamp"]).any():
        duplicates = df[df.duplicated(["symbol", "timestamp"], keep=False)]
        if any(
            g.drop_duplicates().shape[0] > 1 for _, g in duplicates.groupby(["symbol", "timestamp"])
        ):
            raise ValueError("conflicting index entities; cannot choose favorable vintage")
        df = df.drop_duplicates(["symbol", "timestamp"])
    closes = df.pivot(index="timestamp", columns="symbol", values="close")
    opens = df.pivot(index="timestamp", columns="symbol", values="open")
    clean_close, clean_open, hygiene = sanitize_price_matrices(closes, opens)
    for symbol in ("QQQ", "IWM"):
        for i in df.index[df.symbol == symbol]:
            t = df.at[i, "timestamp"]
            if pd.isna(clean_close.loc[t, symbol]) or pd.isna(clean_open.loc[t, symbol]):
                df.loc[i, ["open", "high", "low", "close", "vwap"]] = float("nan")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out / "indexes.parquet")
    sessions = []
    outputs = []
    splits = [a["row"] for a in actions if a["kind"] == "forward_splits"]
    months = sorted({(e["year"], e["month"]) for e in manifest["minute_inputs"]})
    for year, month in months:
        records = []
        nextmonth = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        dates = us_equity_session_dates(date(year, month, 1), nextmonth - timedelta(days=1))
        for e in manifest["minute_inputs"]:
            if (e["year"], e["month"]) != (year, month):
                continue
            symbol = e["symbol"]
            b = e["binding"]
            assert bind(ROOT / b["path"]) == b
            original = con.execute(
                "SELECT timestamp,open,high,low,close,volume,vwap FROM read_parquet(?) WHERE symbol=? ORDER BY timestamp",
                [str(ROOT / b["path"]), symbol],
            ).fetchall()
            byday = defaultdict(list)
            for r in original:
                byday[r[0].astimezone(NEW_YORK).date()].append(r)
            for d in dates:
                prior = [
                    x for x in daily["raw"][symbol] if x < str(d) and x in daily["all"][symbol]
                ]
                if not prior:
                    sessions.append(
                        dict(symbol=symbol, day=str(d), status="no_prior_basis", missing=None)
                    )
                    continue
                prev = max(prior)
                raw = daily["raw"][symbol][prev]
                adj = daily["all"][symbol][prev]
                ratios = [
                    raw[k] / adj[k] for k in ("o", "h", "l", "c", "vw") if raw.get(k) and adj.get(k)
                ]
                f = ratios[-1]
                vf = raw["v"] / adj["v"]
                if max(abs(r / f - 1) for r in ratios) > 1e-4:
                    sessions.append(
                        dict(
                            symbol=symbol, day=str(d), status="nonuniform_prior_basis", missing=None
                        )
                    )
                    continue
                for action in splits:
                    if action["symbol"] == symbol and prev < action["ex_date"] <= str(d):
                        ratio = action["new_rate"] / action["old_rate"]
                        f /= ratio
                        vf *= ratio
                op = datetime.combine(d, day_time(9, 30), tzinfo=NEW_YORK).astimezone(UTC)
                cl = datetime.combine(d, us_equity_session_close(d), tzinfo=NEW_YORK).astimezone(
                    UTC
                )
                expected = {
                    op + timedelta(minutes=i) for i in range(int((cl - op).total_seconds() / 60))
                }
                seen = set()
                dupes = set()
                invalid = []
                for t, o, h, l, c, v, vw in byday[d]:
                    if t not in expected:
                        continue
                    if t in seen:
                        dupes.add(t)
                        continue
                    vals = [o, h, l, c, vw]
                    if (
                        not all(math.isfinite(x) and x > 0 for x in vals)
                        or not l <= min(o, c) <= max(o, c) <= h
                        or v < 0
                    ):
                        invalid.append(t.isoformat())
                        continue
                    seen.add(t)
                    records.append(
                        dict(
                            symbol=symbol,
                            timestamp=t,
                            open=o * f,
                            high=h * f,
                            low=l * f,
                            close=c * f,
                            volume=v * vf,
                            vwap=vw * f,
                            prior_basis=prev,
                            price_factor=f,
                            volume_factor=vf,
                        )
                    )
                sessions.append(
                    dict(
                        symbol=symbol,
                        day=str(d),
                        status="conditional_normalized",
                        expected=len(expected),
                        observed=len(seen),
                        missing=[t.isoformat() for t in sorted(expected - seen)],
                        duplicate=[t.isoformat() for t in sorted(dupes)],
                        invalid=invalid,
                        exact_raw_certified=False,
                        prior_basis=prev,
                        price_factor=f,
                        volume_factor=vf,
                    )
                )
        if records:
            dest = out / f"{year}-{month:02}.parquet"
            pq.write_table(pa.Table.from_pylist(records), dest, compression="zstd")
            outputs.append(bind(dest))
    result = dict(
        manifest=bind(P / "complete-input-job-manifest.json"),
        sessions=sessions,
        outputs=outputs,
        auxiliary_outputs=[
            bind(out / f) for f in ("daily-basis.json", "actions.json", "indexes.parquet")
        ],
        index_sources=sources,
        source_basis=("previous-complete-day raw/all scalar; known effective split "
                      "transforms separate; remaining rights unresolved"),
        raw_witness_scope="unchanged four actual November2024 symbol-days only; no new raw certification",
        new_HTTP=0,
        fit=0,
        PnL=0,
        CPU=time.process_time() - started,
        RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        index_hygiene=repr(hygiene),
    )
    (P / "complete-input-result.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps(dict(months=len(outputs), symbol_days=len(sessions), CPU=result["CPU"])))


if __name__ == "__main__":
    main()
