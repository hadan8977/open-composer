"""Live VIX close file for the v1.2 target generator (``data/live/vix/VIXCLS.csv``).

The generator reads ``<equity-book root>/../vix/VIXCLS.csv`` (``v12_targets.default_vix_dir``) and
needs VIX at every tranche formation date up to the decision date D.  The research file is FRED
``VIXCLS``, which posts with a 1-3 business-day lag, so at the 23:15 UTC target step D is missing.
CBOE's own daily history (``VIX_History.csv``, the source FRED republishes) has D the same evening.

This script writes FRED's rows plus CBOE closes for the dates after FRED's last row, in FRED's
format, after checking that the two sources agree on every overlapping date (2026-10-04: 9,285 of
9,285 equal).  Atomic write; the previous file stays when a fetch or the check fails.

Exit codes: 0 ok, 2 a fetch failed, 3 the overlap check failed.  No broker interface, no keys.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/live/vix"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
USER_AGENT = "open-composer-research/1.0"
TOL = 0.005  # both sources publish two decimals
EXIT_OK, EXIT_FETCH, EXIT_CHECK = 0, 2, 3


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (fixed https URLs)
        return resp.read().decode("utf-8")


def parse_fred(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text), na_values=["."])
    s = df.set_index(pd.to_datetime(df["observation_date"]))["VIXCLS"].astype(float)
    return s.dropna().sort_index()


def parse_cboe(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    s = df.set_index(pd.to_datetime(df["DATE"], format="%m/%d/%Y"))["CLOSE"].astype(float)
    return s.dropna().sort_index()


def merge(fred: pd.Series, cboe: pd.Series) -> tuple[pd.Series, dict]:
    both = fred.index.intersection(cboe.index)
    diff = (fred.loc[both] - cboe.loc[both]).abs()
    bad = diff[diff > TOL]
    tail = cboe[cboe.index > fred.index.max()]
    merged = pd.concat([fred, tail.round(2)]).sort_index()
    info = {
        "overlap_days": int(len(both)),
        "overlap_mismatches": int(len(bad)),
        "mismatch_dates": [d.date().isoformat() for d in bad.index[-10:]],
        "fred_last": fred.index.max().date().isoformat(),
        "cboe_last": cboe.index.max().date().isoformat(),
        "appended_from_cboe": [d.date().isoformat() for d in tail.index],
        "last_date": merged.index.max().date().isoformat(),
    }
    return merged, info


def run(out_dir: Path, get: Callable[[str], str] = http_get) -> int:
    try:
        fred = parse_fred(get(FRED_URL))
        cboe = parse_cboe(get(CBOE_URL))
    except Exception as exc:  # noqa: BLE001 (any network or parse error keeps the old file)
        print(f"fetch failed: {exc}", file=sys.stderr)
        return EXIT_FETCH
    merged, info = merge(fred, cboe)
    if info["overlap_days"] < 250 or info["overlap_mismatches"] > 0:
        print(f"overlap check failed: {info}", file=sys.stderr)
        return EXIT_CHECK
    out_dir.mkdir(parents=True, exist_ok=True)
    csv = pd.DataFrame(
        {"observation_date": merged.index.strftime("%Y-%m-%d"), "VIXCLS": merged.to_numpy()}
    )
    tmp = out_dir / "VIXCLS.csv.tmp"
    csv.to_csv(tmp, index=False)
    tmp.replace(out_dir / "VIXCLS.csv")
    meta = {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {"fred": FRED_URL, "cboe": CBOE_URL},
        "rule": "FRED rows; CBOE closes appended after FRED's last date; overlap must match",
        **info,
    }
    (out_dir / "VIXCLS.meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"VIX to {info['last_date']} (appended {info['appended_from_cboe']})")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    return run(Path(ap.parse_args(argv).out_dir))


if __name__ == "__main__":
    raise SystemExit(main())
