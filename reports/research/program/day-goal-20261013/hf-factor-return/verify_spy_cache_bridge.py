"""Read-only verification and input aggregation; no strategy returns or fitting."""

import hashlib
import json
import os
import resource
from datetime import UTC, datetime
from pathlib import Path

os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
resource.setrlimit(resource.RLIMIT_CPU, (100, 100))
os.environ.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")

import numpy as np
import pandas as pd
import pyarrow as pa

pa.set_cpu_count(1)
pa.set_io_thread_count(1)
P = Path(__file__).parent
OLD = Path("reports/research/program/day-goal-20261011/tail-momentum")
OUT = P / "market-input/cache-bridge"
OUT.mkdir(exist_ok=True)
NY = "America/New_York"


def bind(path):
    path = Path(path)
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bytes=path.stat().st_size)


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def frame(bars):
    d = pd.DataFrame(bars).rename(columns=dict(o="open", h="high", l="low", c="close", v="volume"))
    d["timestamp"] = pd.to_datetime(d.t, utc=True, format="ISO8601")
    ny = d.timestamp.dt.tz_convert(NY)
    d["date"] = ny.dt.tz_localize(None).dt.normalize()
    d["minute"] = ny.dt.hour * 60 + ny.dt.minute
    assert ((ny.dt.second == 0) & (ny.dt.microsecond == 0)).all()
    assert d.timestamp.is_monotonic_increasing and not d.timestamp.duplicated().any()
    prices = d[["open", "high", "low", "close"]]
    assert np.isfinite(prices.to_numpy()).all() and prices.gt(0).all().all()
    assert ((d.low <= d.open) & (d.low <= d.close) & (d.high >= d.open) & (d.high >= d.close)).all()
    assert np.isfinite(d.volume).all() and d.volume.ge(0).all()
    return d[["timestamp", "date", "minute", "open", "high", "low", "close", "volume"]]


def main():
    started = resource.getrusage(resource.RUSAGE_SELF)
    clock_path = P / "funded-SPY-clock-proposed.json"
    clock = json.loads(clock_path.read_text())["rows"]
    expected = pd.DataFrame(clock)
    expected["date"] = pd.to_datetime(expected.date)
    expected["cutoff"] = expected.close.str[:2].astype(int) * 60 + expected.close.str[3:5].astype(int)
    cutoffs = expected.set_index("date").cutoff
    attempts = {}
    for path in (OLD / "inputs/attempts").glob("*.json"):
        r = json.loads(path.read_text())
        if r.get("job", "") in {f"minute-SPY-{year}" for year in range(2016, 2021)}:
            assert r["entity_sha256"] not in attempts
            attempts[r["entity_sha256"]] = (path, r)
    bindings = [bind(clock_path), bind(OLD / "prepare_inputs.py")]
    annual = []
    aggregated = []
    for year in range(2016, 2021):
        path = OLD / f"inputs/minute-SPY-{year}/progress.json"
        prog = json.loads(path.read_text())
        assert prog["complete"] and prog["next_token"] is None
        assert prog["page"] == len(prog["pages"])
        assert prog["request"]["adjustment"] == "raw" and prog["request"]["feed"] == "sip"
        assert prog["request"]["symbols"] == "SPY" and prog["request"]["timeframe"] == "1Min"
        bindings.append(bind(path))
        prior_token = None
        prior_last = None
        frames = []
        pages = []
        raw_rows = 0
        for index, page in enumerate(prog["pages"]):
            raw_path = Path(page["raw_path"])
            rb = bind(raw_path)
            assert rb["sha256"] == page["raw_sha256"]
            attempt_path, attempt = attempts[rb["sha256"]]
            assert attempt["status_code"] == 200 and attempt["entity_bytes"] == rb["bytes"]
            assert attempt["page"] == index
            params = dict(prog["request"])
            if prior_token is not None:
                params["page_token"] = prior_token
            assert attempt["request"] == params
            body = json.loads(raw_path.read_text())
            assert set(body["bars"]) == {"SPY"}
            d = frame(body["bars"]["SPY"])
            assert prior_last is None or prior_last < d.timestamp.iloc[0]
            assert d.timestamp.ge(pd.Timestamp(params["start"])).all()
            assert d.timestamp.le(pd.Timestamp(params["end"])).all()
            prior_last = d.timestamp.iloc[-1]
            prior_token = body["next_page_token"]
            assert (prior_token is None) == (index == len(prog["pages"]) - 1)
            rth = d[d.minute.between(570, 959)].reset_index(drop=True)
            norm_path = Path(page["normalized_path"])
            nb = bind(norm_path)
            assert nb["sha256"] == page["normalized_sha256"] and len(rth) == page["rows"]
            norm = pd.read_parquet(norm_path)
            assert norm.symbol.eq("SPY").all()
            for col in rth.columns:
                np.testing.assert_array_equal(rth[col].to_numpy(), norm[col].to_numpy())
            bindings.extend([rb, nb, bind(attempt_path)])
            pages.append(dict(raw=rb, receipt=bind(attempt_path), normalized=nb,
                              raw_rows=len(d), regular_clock_rows=len(rth)))
            raw_rows += len(d)
            frames.append(rth)
        d = pd.concat(frames, ignore_index=True)
        assert not d.timestamp.duplicated().any()
        d["cutoff"] = d.date.map(cutoffs)
        outside_clock = int(d.cutoff.isna().sum())
        after_cutoff = int((d.minute >= d.cutoff).sum())
        d = d[d.cutoff.notna() & d.minute.lt(d.cutoff)].copy()
        d["window_minute"] = 570 + ((d.minute - 570) // 15) * 15
        g = d.groupby(["date", "window_minute"], sort=True)
        a = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                  close=("close", "last"), volume=("volume", "sum"),
                  minute_rows=("minute", "size"), first_minute=("minute", "min"),
                  last_minute=("minute", "max")).reset_index()
        a["timestamp"] = (a.date + pd.to_timedelta(a.window_minute, unit="m")).dt.tz_localize(NY).dt.tz_convert("UTC")
        a["first_price_age_minutes"] = a.first_minute - a.window_minute
        a["last_price_age_to_window_end_minutes"] = a.window_minute + 15 - a.last_minute - 1
        assert a.minute_rows.between(1, 15).all()
        path = OUT / f"SPY-raw15-aggregated-{year}.parquet"
        a.to_parquet(path, index=False)
        aggregated.append(a)
        annual.append(dict(year=year, pages=pages, total_raw_rows=raw_rows,
                           normalized_rows=sum(p["regular_clock_rows"] for p in pages),
                           retained_minutes=len(d), outside_calendar_minutes=outside_clock,
                           post_cutoff_minutes=after_cutoff, observed_windows=len(a),
                           fewer_than15_minutes=int(a.minute_rows.lt(15).sum()), output=bind(path)))
        print(f"bridge {year}: {len(d)} minutes / {len(a)} windows", flush=True)
    a = pd.concat(aggregated, ignore_index=True).set_index("timestamp").sort_index()
    assert not a.index.duplicated().any()
    native_rows = []
    for receipt in json.loads((P / "market-input/market-request-ledger.json").read_text()):
        path = Path(receipt["path"])
        b = bind(path)
        assert b["sha256"] == receipt["sha256"]
        bindings.append(b)
        native_rows.extend(json.loads(path.read_text())["bars"]["SPY"])
    native = frame(native_rows).set_index("timestamp")
    overlap = native.index.intersection(a.index)
    diffs = []
    for ts in overlap:
        nr, ar = native.loc[ts], a.loc[ts]
        if any(nr[c] != ar[c] for c in ["open", "high", "low", "close", "volume"]):
            diffs.append(dict(timestamp=ts.isoformat(), native={c:float(nr[c]) for c in ["open","high","low","close","volume"]},
                              aggregate={c:float(ar[c]) for c in ["open","high","low","close","volume"]},
                              minute_rows=int(ar.minute_rows)))
    overlap_stats = {}
    for c in ["open", "high", "low", "close", "volume"]:
        delta = (a.loc[overlap,c] - native.loc[overlap,c]).to_numpy(float)
        overlap_stats[c] = dict(exact_rows=int((delta == 0).sum()), different_rows=int((delta != 0).sum()),
                                max_absolute_difference=float(np.max(np.abs(delta))))
    expected_ids = []
    day_qa = []
    for row in clock:
        day = pd.Timestamp(row["date"])
        start = (day + pd.Timedelta(minutes=570)).tz_localize(NY).tz_convert("UTC")
        ids = [start + pd.Timedelta(minutes=15*k) for k in range(row["regular15_windows"])]
        expected_ids.extend(ids)
        absent = [t.isoformat() for t in ids if t not in a.index]
        day_qa.append(dict(date=row["date"], expected_windows=len(ids), missing_windows=absent))
    daily_path = Path("reports/research/program/day-goal-20261013/primary-return-breadth/inputs/bars_raw-01.json")
    daily = frame(json.loads(daily_path.read_text())["bars"]["SPY"]).set_index("date")
    # Daily bars are NY-midnight labelled, not 16:00 trade timestamps.
    assert not daily.index.duplicated().any()
    daily_q = []
    for row in clock:
        day = pd.Timestamp(row["date"])
        cutoff = int(row["close"][:2])*60+int(row["close"][3:5])
        ts = (day+pd.Timedelta(minutes=cutoff-15)).tz_localize(NY).tz_convert("UTC")
        daily_q.append(dict(date=row["date"], daily_raw_present=day in daily.index,
                            closing15_present=ts in a.index,
                            daily_close=float(daily.loc[day,"close"]) if day in daily.index else None,
                            closing15_close=float(a.loc[ts,"close"]) if ts in a.index else None))
    adjusted_path = Path("data/features/t15_minute/SPY.parquet")
    adjusted = pd.read_parquet(adjusted_path, filters=[("date", "==", pd.Timestamp("2016-01-04"))])
    raw_first = a.loc[(pd.Timestamp("2016-01-04")+pd.Timedelta(minutes=570)).tz_localize(NY).tz_convert("UTC")]
    save(OUT / "native15-overlap-differences.json", diffs)
    save(OUT / "calendar-window-coverage.json", day_qa)
    save(OUT / "raw-daily-closing-reconciliation.json", daily_q)
    bindings.extend([bind(daily_path), bind(adjusted_path), bind(Path("scripts/fetch_sip_universe.py")),
                     bind(OLD / "inputs/targeted-repair/repair-acceptance.json")])
    used = resource.getrusage(resource.RUSAGE_SELF)
    qa = dict(schema_version=1, as_of_utc=datetime.now(UTC).isoformat(),
              author="7b109880-ac40-447e-b2a6-f0ed1266ebac", research_role="source_input_QA_only",
              input_basis="SPY current-vintage SIP raw1m, asof2026-09-15; actual original receipts and body cursor chain",
              aggregation="Within each fixed left-labelled15m NY window: first open/max high/min low/last close/sum volume. Observed missing minute identities are not filled. Missing entire windows remain absent. Extended and post-calendar-cutoff rows excluded only by frozen clock.",
              clock_verified_venue=False, first_arrival_PIT=False,
              source_cache_reused_without_new_requests=True, raw_source_receipt_count=len(attempts),
              annual=annual, expected_days=len(clock), expected_windows=len(expected_ids),
              observed_windows=len(a), missing_full_windows=[t.isoformat() for t in expected_ids if t not in a.index],
              native15_overlap_rows=len(overlap), native15_overlap_stats=overlap_stats,
              native15_exact_allOHLCV_rows=len(overlap)-len(diffs), native15_differences=bind(OUT / "native15-overlap-differences.json"),
              daily_closing=bind(OUT / "raw-daily-closing-reconciliation.json"),
              daily_raw_missing_dates=[r["date"] for r in daily_q if not r["daily_raw_present"]],
              daily_vs_15m_is_different_price_clock_not_raw_basis_proof=True,
              adjusted_wide_cache_rejected=dict(binding=bind(adjusted_path),
                  first2016_open=float(adjusted.iloc[0].open), raw_first2016_open=float(raw_first.open),
                  collection_adjustment="all", cash_ledger_use=False),
              bindings=bindings, new_source_requests=0, new_market_requests=0,
              new_fits=0, strategy_returns_computed=False, economic_execution_admitted=False,
              measured_process_CPU=used.ru_utime+used.ru_stime-started.ru_utime-started.ru_stime,
              max_RSS_KiB=used.ru_maxrss)
    save(OUT / "cache-bridge-QA.json", qa)
    print(json.dumps({k:qa[k] for k in ["observed_windows", "native15_overlap_rows", "native15_exact_allOHLCV_rows", "daily_raw_missing_dates", "measured_process_CPU", "max_RSS_KiB"]}))


if __name__ == "__main__":
    main()
