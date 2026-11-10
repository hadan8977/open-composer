# ruff: noqa: E501
"""T-20261007-06: 1-minute regular-session panels for the G1 stock pools (reuses the T-15 builder).

Writes data/features/t0706_minute/<SYM>.parquet; resumable (existing files are skipped).
Usage: t0706_build_panels.py POOL [POOL...]   (pool names of t0706_grid, or explicit symbols)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t0706_grid as G  # noqa: E402
import t15_build_etf_panels as B  # noqa: E402

B.OUT = ROOT / "data/features/t0706_minute"
B.ARCHIVES = {
    "hist": (ROOT / "data/sip-hist/minute", range(2017, 2023)),
    "sip": (ROOT / "data/sip/minute", range(2023, 2027)),
}  # 2016 is not needed: V4 starts 2017-10 and the noise band needs 14 days of history


def main() -> int:
    B.OUT.mkdir(parents=True, exist_ok=True)
    syms: list[str] = []
    for a in sys.argv[1:]:
        syms += G.pool_symbols(a) if a in G.G1_POOLS else [a]
    syms = list(dict.fromkeys(syms))
    lay = B.sip_layout()
    for s in syms:
        p = B.OUT / f"{s}.parquet"
        if p.exists() or s not in lay:
            if s not in lay:
                print(s, "NOT_IN_LAYOUT", flush=True)
            continue
        t0 = time.time()
        d = B.extract(s, int(lay[s]))
        if d.empty:
            print(s, "EMPTY", flush=True)
            continue
        d = d[d["date"] <= G.DATA_END]
        d.to_parquet(p)
        if (d["date"].dt.year == 2023).sum() < 240 * 380:
            B.fix_year_level(s, 2023)
        print(
            s,
            len(d),
            d.date.min().date(),
            d.date.max().date(),
            d.date.nunique(),
            f"{time.time() - t0:.0f}s",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
