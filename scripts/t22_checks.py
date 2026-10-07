# ruff: noqa: E501
"""T-20261006-22 identity and no-look-ahead checks (contract.md sections 13 and 16 item 5).

T22_STORE=<store> uv run python scripts/t22_checks.py [--out reports/.../checks.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book.backtest import BookConfig, run_book  # noqa: E402
from scripts import t22_build as B  # noqa: E402
from scripts import t22_run as R  # noqa: E402


def check_pca_no_lookahead(store: R.Store) -> dict:
    close = np.asarray(store.m("close"), dtype="float64")
    r = np.full_like(close, np.nan)
    r[1:] = close[1:] / close[:-1] - 1.0
    r[~np.isfinite(r)] = np.nan
    rank = np.asarray(store.m("adv_rank"))
    refresh = store.meta["pca_refresh_positions"]
    out = []
    for p in (refresh[10], refresh[60]):
        nxt = p + B.PCA_REFRESH
        w = r[p - B.PCA_WINDOW + 1 : p + 1]
        sel = np.flatnonzero(
            (rank[p] <= B.PCA_SET_RANK) & (np.isfinite(w).sum(axis=0) >= B.PCA_MIN_OBS)
        )
        e_full = np.full(r.shape, np.nan, dtype="float32")
        B.pca_block(r, w, sel, p, nxt, e_full)
        for t in (p + 1, p + 8):
            r2 = r.copy()
            r2[t + 1 :] = np.nan  # nothing after t
            if t - 1 > p:
                r2[p + 1 : t] = np.nan  # nothing between the refresh and t
            e_tr = np.full(r.shape, np.nan, dtype="float32")
            B.pca_block(r2, w, sel, p, t + 1, e_tr)
            a, b = e_full[t], e_tr[t]
            same = bool(
                np.array_equal(np.isfinite(a), np.isfinite(b))
                and np.allclose(a[np.isfinite(a)], b[np.isfinite(b)], atol=0, rtol=0)
            )
            out.append(
                {
                    "refresh_pos": int(p),
                    "t": int(t),
                    "identical": same,
                    "n_finite": int(np.isfinite(a).sum()),
                }
            )
    stored_rows = []
    e_store = store.m("e_pca")
    p = refresh[10]
    w = r[p - B.PCA_WINDOW + 1 : p + 1]
    sel = np.flatnonzero(
        (rank[p] <= B.PCA_SET_RANK) & (np.isfinite(w).sum(axis=0) >= B.PCA_MIN_OBS)
    )
    e_re = np.full(r.shape, np.nan, dtype="float32")
    B.pca_block(r, w, sel, p, p + 3, e_re)
    for t in (p + 1, p + 2):
        a, b = np.asarray(e_store[t]), e_re[t]
        fin = np.isfinite(a) & np.isfinite(b)
        stored_rows.append(
            {
                "t": int(t),
                "max_abs_diff_vs_store": float(np.abs(a[fin] - b[fin]).max())
                if fin.any()
                else None,
                "n_compared": int(fin.sum()),
            }
        )
    return {
        "truncation": out,
        "store_vs_recompute": stored_rows,
        "pass": all(x["identical"] for x in out),
    }


def check_signal_no_lookahead(store: R.Store) -> dict:
    res = []
    for resid in ("ind", "pca"):
        for L in (5, 21):
            t = 1500
            s_full = R.signal_row(store, resid, L, t)

            class Fake:
                shape = store.shape

                def m(self, name, _t=t, _s=store):
                    a = np.array(_s.m(name))
                    a[_t + 1 :] = np.nan
                    return a

            s_tr = R.signal_row(Fake(), resid, L, t)
            same = bool(
                np.array_equal(np.isfinite(s_full), np.isfinite(s_tr))
                and np.allclose(s_full[np.isfinite(s_full)], s_tr[np.isfinite(s_tr)])
            )
            res.append({"resid": resid, "L": L, "t": t, "identical": same})
    return {"cases": res, "pass": all(x["identical"] for x in res)}


def check_engine_identity(store: R.Store, start: str, end: str, n_days: int = 20) -> dict:
    """Zero-cost run (H=1, exec open): the equity change between consecutive trade opens equals the
    weight-weighted open-to-open return of the traded target book (stale-open rule aside)."""
    panel = R.load_panel(
        store, (pd.Timestamp(start) - pd.Timedelta(days=40)).strftime("%Y-%m-%d"), end
    )
    books = R.build_books(store, panel, start, end, 500, "ind", 5, "none", 1)
    sig = [d for d in panel.dates if pd.Timestamp(start) <= d <= pd.Timestamp(end)]
    cfg = BookConfig(
        freq="D",
        exec_price="open",
        cost_fn=lambda t, s: {"spread": 0.0},
        borrow_bp_per_year=0.0,
        margin_rate=0.0,
        start=start,
        end=end,
        initial_equity=1.0,
        snapshots=True,
        signal_dates=sig,
    )
    targets: dict[pd.Timestamp, dict] = {}

    def decide(t, state):
        p = store.pos(t)
        tgt = R.combine([books.get(p)], 1, store)
        targets[t] = tgt
        return tgt

    res = run_book(panel, decide, cfg)
    d = res.daily
    tdates = [x for x in d.index[d["is_trade_day"]]]
    diffs = []
    o = panel.open
    for k in range(1, min(len(tdates) - 1, n_days + 1)):
        a, b = tdates[k], tdates[k + 1]
        dec = panel.dates[panel.dates.get_loc(a) - 1]
        tgt = targets.get(dec)
        if not tgt:
            continue
        ia, ib = panel.dates.get_loc(a), panel.dates.get_loc(b)
        tot = 0.0
        ok = True
        for s, w in tgt.items():
            if s == "TBILL":
                s = "SGOV" if panel.has("SGOV") and np.isfinite(o[ia, panel.col("SGOV")]) else "BIL"
            if not panel.has(s):
                ok = False
                break
            j = panel.col(s)
            if not (np.isfinite(o[ia, j]) and np.isfinite(o[ib, j])):
                ok = False
                break
            tot += w * (o[ib, j] / o[ia, j] - 1.0)
        if not ok:
            continue
        eng = d.loc[b, "equity_open_pre"] / d.loc[a, "equity_open_post"] - 1.0
        diffs.append(abs(eng - tot))
    return {
        "n_compared": len(diffs),
        "max_abs_diff": float(max(diffs)) if diffs else None,
        "pass": bool(diffs and max(diffs) <= 1e-9),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--start", default="2024-01-05")
    ap.add_argument("--end", default="2024-03-29")
    a = ap.parse_args()
    store = R.Store()
    out = {
        "store": str(R.STORE),
        "pca_no_lookahead": check_pca_no_lookahead(store),
        "signal_no_lookahead": check_signal_no_lookahead(store),
        "engine_identity": check_engine_identity(store, a.start, a.end),
    }
    out["all_pass"] = bool(
        out["pca_no_lookahead"]["pass"]
        and out["signal_no_lookahead"]["pass"]
        and out["engine_identity"]["pass"]
    )
    print(json.dumps(out, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
