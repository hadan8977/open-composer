# ruff: noqa: E501
"""T-20261006-22 stage 2: spec selection, offsets, placebos, robustness cells, whole-share check,
attribution, correlation and the scorecard (contract.md section 16).  Resumable: every product is
written to ``<store>/results/<tag>/`` and skipped if present.

    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t22_stage2.py select
    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t22_stage2.py offsets|placebo|robust|share|attrib
    uv run python scripts/t22_stage2.py score
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

import os  # noqa: E402

from open_composer.research.equity_book.evaluate import load_rf_spy  # noqa: E402
from scripts import t22_run as R  # noqa: E402

REC_START, REC_END = "2024-01-05", os.environ.get("T22_REC_END", "2026-09-15")
STRESS_START, STRESS_END = "2017-09-29", "2023-08-31"
IT = ROOT / "reports/research/iterations/t20261006_22_st_reversal"
SEL_FILE = R.RES / "selected.json"


def annual_sharpe(x: pd.Series) -> float:
    x = x.dropna()
    sd = float(x.std(ddof=1))
    return float(x.mean() / sd * np.sqrt(252)) if sd > 0 and len(x) > 20 else float("nan")


def load_main(tag: str = "A") -> pd.DataFrame:
    rows = []
    for f in sorted((R.RES / tag).glob("R_U*.json")):
        d = json.loads(f.read_text())
        rows.append(
            {
                "cell_id": d["cell_id"],
                "universe": d["universe"],
                "resid": d["resid"],
                "L": d["L"],
                "H": d["H"],
                "net": d["net_1x"].get("sharpe"),
                "gross": d["gross"]["sharpe"],
            }
        )
    return pd.DataFrame(rows)


def select() -> dict:
    df = load_main("A")
    if len(df) != 24:
        raise SystemExit(f"stage A incomplete: {len(df)}/24 cells")
    top = df.sort_values("net", ascending=False).head(3).reset_index(drop=True)
    sel = top.iloc[1].to_dict()  # middle-ranked of the top three (standard 5b item 6)
    sel["top3"] = top["cell_id"].tolist()
    SEL_FILE.write_text(json.dumps(sel, indent=1))
    print(json.dumps(sel, indent=1))
    return sel


def selected() -> dict:
    return json.loads(SEL_FILE.read_text())


def setup(start: str, end: str):
    store = R.Store()
    panel = R.load_panel(
        store, (pd.Timestamp(start) - pd.Timedelta(days=40)).strftime("%Y-%m-%d"), end
    )
    rf, spy = load_rf_spy()
    return store, panel, rf, spy


def sel_args(sel: dict) -> tuple[int, str, int, int]:
    return int(sel["universe"]), sel["resid"], int(sel["L"]), int(sel["H"])


def save(res, probe, name: str, tag: str, rf, spy, extra: dict | None = None) -> dict:
    out_dir = R.RES / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    window = ("2024-01-08", REC_END)
    summ = R.summarize(res, rf, spy, probe, window)
    summ.update(extra or {})
    summ["cell_id"] = name
    (out_dir / f"{name}.json").write_text(json.dumps(summ))
    res.daily.to_parquet(out_dir / f"{name}.parquet")
    return summ


def cmd_offsets(window: str = "recent") -> None:
    sel = selected()
    u, resid, L, H = sel_args(sel)
    start, end, tag = (
        (REC_START, REC_END, "offsets")
        if window == "recent"
        else (STRESS_START, STRESS_END, "offsets_stress")
    )
    store, panel, rf, spy = setup(start, end)
    books = R.build_books(store, panel, start, end, u, resid, L, "none", 10)
    if H != 5:
        print(
            "selected H != 5: rebalance offsets are not defined for a daily-rebalanced H=1 book; check d not met"
        )
        return
    for k in range(5):
        name = f"OFF{k}_" + sel["cell_id"]
        if (R.RES / tag / f"{name}.parquet").exists():
            continue
        res, probe = R.run_cell(
            store, panel, R.offset_target(books, k, 5, store), "open", start, end
        )
        (R.RES / tag).mkdir(parents=True, exist_ok=True)
        res.daily.to_parquet(R.RES / tag / f"{name}.parquet")
        print(name, window, "done", flush=True)


def cmd_placebo(n: int = 100, shard: int = 0, nshards: int = 1) -> None:
    sel = selected()
    u, resid, L, H = sel_args(sel)
    store, panel, rf, spy = setup(REC_START, REC_END)
    f = R.RES / ("placebo.json" if nshards == 1 else f"placebo_shard{shard}.json")
    acc = json.loads(f.read_text()) if f.exists() else {"net": {}, "gross": {}}
    window = ("2024-01-08", REC_END)
    for seed in range(shard, n, nshards):
        for mode in ("net", "gross"):
            if str(seed) in acc[mode]:
                continue
            books = R.build_books(
                store, panel, REC_START, REC_END, u, resid, L, "none", H, placebo=(mode, seed)
            )
            res, probe = R.run_cell(
                store, panel, R.overlap_target(books, H, store), "open", REC_START, REC_END
            )
            d = res.daily.loc[window[0] : window[1]]
            col = "net" if mode == "net" else "gross"
            ex = d[col] - rf.reindex(d.index).fillna(0.0)
            acc[mode][str(seed)] = annual_sharpe(ex)
            f.write_text(json.dumps(acc))
        print(
            f"seed {seed} net {acc['net'][str(seed)]:.2f} gross {acc['gross'][str(seed)]:.2f}",
            flush=True,
        )


def cmd_robust() -> None:
    sel = selected()
    u, resid, L, H = sel_args(sel)
    store, panel, rf, spy = setup(REC_START, REC_END)
    base = f"U{u}_{resid}_L{L}"
    cases = [
        ("lowturn", "open", R.BORROW_BP, {}),
        ("nonews", "open", R.BORROW_BP, {}),
        ("vixscale", "open", R.BORROW_BP, {}),
        ("none", "close", R.BORROW_BP, {}),
        ("none", "open", 100.0, {"borrow_stress": True}),
    ]
    for cond, ex, borrow, extra in cases:
        name = f"ROB_{cond}_{ex}_b{int(borrow)}_{base}_H{H}"
        if (R.RES / "robust" / f"{name}.parquet").exists():
            continue
        books = R.build_books(store, panel, REC_START, REC_END, u, resid, L, cond, H)
        res, probe = R.run_cell(
            store,
            panel,
            R.overlap_target(books, H, store),
            ex,
            REC_START,
            REC_END,
            borrow_bp=borrow,
        )
        s = save(res, probe, name, "robust", rf, spy, extra)
        print(name, s["net_1x"].get("sharpe"), s["gross"]["sharpe"], flush=True)
    # shorts restricted to adv_rank <= 1000 (borrow stress, contract section 16 item 7)
    name = f"ROB_short1000_open_b25_{base}_H{H}"
    if not (R.RES / "robust" / f"{name}.parquet").exists():
        R.SHORT_MAX_RANK = 1000
        books = R.build_books(store, panel, REC_START, REC_END, u, resid, L, "none", H)
        R.SHORT_MAX_RANK = None
        res, probe = R.run_cell(
            store, panel, R.overlap_target(books, H, store), "open", REC_START, REC_END
        )
        s = save(res, probe, name, "robust", rf, spy)
        print(name, s["net_1x"].get("sharpe"), flush=True)


def cmd_share() -> None:
    """Whole-share feasibility (standard V2) on >= 20 sampled sessions of the selected spec."""
    sel = selected()
    u, resid, L, H = sel_args(sel)
    store, panel, rf, spy = setup(REC_START, REC_END)
    books = R.build_books(store, panel, REC_START, REC_END, u, resid, L, "none", H)
    tf = R.overlap_target(books, H, store)
    cl = np.asarray(store.m("close"))
    adv = np.asarray(store.m("dollar_adv_21"))
    sym_pos = {s: j for j, s in enumerate(store.symbols)}
    pos = [
        store.pos(d)
        for d in panel.dates
        if pd.Timestamp("2024-02-01") <= d <= pd.Timestamp(REC_END)
    ]
    rng = np.random.default_rng(20261006)
    sample = sorted(rng.choice(pos[1:], size=40, replace=False))
    rows = []
    for t in sample:
        tgt, prev = tf(t), tf(t - 1)
        if not tgt or not prev:
            continue
        names = [s for s in tgt if s not in ("TBILL",)]
        j = np.array([sym_pos[s] for s in names])
        price = cl[t, j].astype("float64")
        w = np.array([tgt[s] for s in names])
        wp = np.array([prev.get(s, 0.0) for s in names])
        ok = np.isfinite(price) & (price > 0)
        tgt_d = w[ok] * R.EQUITY
        px = price[ok]
        real_d = np.round(tgt_d / px) * px
        short = tgt_d < 0
        short_ratio = (
            float(-real_d[short].sum() / -tgt_d[short].sum()) if short.any() else float("nan")
        )
        rel_l1 = float(np.abs(real_d - tgt_d).sum() / np.abs(tgt_d).sum())
        net_dev = float(abs((real_d - tgt_d).sum()) / R.EQUITY)
        trade_d = np.abs(w[ok] - wp[ok]) * R.EQUITY
        a = adv[t, j][ok]
        part = trade_d[trade_d > 0] / a[trade_d > 0]
        rows.append(
            {
                "t": str(store.dates[t].date()),
                "short_ratio": short_ratio,
                "rel_l1": rel_l1,
                "net_dev": net_dev,
                "median_participation": float(np.nanmedian(part)),
                "n_names": int(ok.sum()),
            }
        )
    df = pd.DataFrame(rows)
    out = {
        "n_sessions": len(df),
        "median_short_ratio": float(df.short_ratio.median()),
        "min_short_ratio": float(df.short_ratio.min()),
        "median_rel_l1": float(df.rel_l1.median()),
        "max_rel_l1": float(df.rel_l1.max()),
        "max_net_dev": float(df.net_dev.max()),
        "median_participation": float(df.median_participation.median()),
        "rows": rows,
    }
    out["v2_pass"] = bool(
        out["min_short_ratio"] >= 0.90
        and out["median_rel_l1"] <= 0.30
        and out["max_net_dev"] <= 0.05
        and out["median_participation"] <= 0.01
    )
    (R.RES / "whole_share.json").write_text(json.dumps(out, indent=1))
    print({k: v for k, v in out.items() if k != "rows"})


def cmd_attrib() -> None:
    """Gross P&L by liquidity tier (adv_rank <= 500 / 501-1000 / 1001-3000) and by recent phase, from the
    post-trade holdings of the selected spec (close-to-close approximation, drift ignored)."""
    sel = selected()
    u, resid, L, H = sel_args(sel)
    store, panel, rf, spy = setup(REC_START, REC_END)
    books = R.build_books(store, panel, REC_START, REC_END, u, resid, L, "none", H)
    res, probe = R.run_cell(
        store, panel, R.overlap_target(books, H, store), "open", REC_START, REC_END, snapshots=True
    )
    cl = np.asarray(store.m("close"), dtype="float64")
    rank = np.asarray(store.m("adv_rank"))
    sym_pos = {s: j for j, s in enumerate(store.symbols)}
    rows = []
    dates = sorted(res.holdings)
    for d in dates:
        t = store.pos(d)
        w = res.holdings[d]
        j = np.array([sym_pos.get(s, -1) for s in w.index])
        ok = j >= 0
        r1 = np.where(
            np.isfinite(cl[t, j[ok]]) & np.isfinite(cl[t - 1, j[ok]]),
            cl[t, j[ok]] / cl[t - 1, j[ok]] - 1.0,
            0.0,
        )
        rk = rank[t, j[ok]]
        ww = w.to_numpy()[ok]
        tier = np.where(rk <= 500, "adv<=500", np.where(rk <= 1000, "adv501-1000", "adv1001-3000"))
        for name in np.unique(tier):
            m = tier == name
            rows.append(
                {
                    "date": d,
                    "tier": name,
                    "long": float((ww[m & (ww > 0)] * r1[m & (ww > 0)]).sum()),
                    "short": float((ww[m & (ww < 0)] * r1[m & (ww < 0)]).sum()),
                }
            )
    df = pd.DataFrame(rows)
    out = {
        "by_tier_ann_pnl": (
            df.groupby("tier")[["long", "short"]].sum() / len(dates) * 252
        ).to_dict(),
        "note": "post-trade weights x next close-to-close return; trade-day open-to-close subtleties ignored; SPY hedge and T-bill excluded",
    }
    (R.RES / "attribution.json").write_text(json.dumps(out, indent=1))
    print(out)


def book_corr() -> dict:
    stock = pd.read_parquet(ROOT / "data/research/book_v12/A1_M0_U3000_F1.parquet")
    eq = stock["equity"]
    r_stock = (eq / eq.shift(1) - 1.0).dropna()
    out = {}
    for f in sorted((R.RES / "A").glob("R_U*.parquet")):
        d = pd.read_parquet(f)["net"]
        s = d.loc["2024-01-08":REC_END]
        j = pd.concat([s, r_stock], axis=1, join="inner").dropna()
        out[f.stem] = {"corr_with_v12_m0_u3000_f1": float(j.corr().iloc[0, 1]), "n": len(j)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "cmd", choices=["select", "offsets", "placebo", "robust", "share", "attrib", "corr"]
    )
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--window", default="recent")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    a = ap.parse_args()
    if a.cmd == "select":
        select()
    elif a.cmd == "offsets":
        cmd_offsets(a.window)
    elif a.cmd == "placebo":
        cmd_placebo(a.n, a.shard, a.nshards)
    elif a.cmd == "robust":
        cmd_robust()
    elif a.cmd == "share":
        cmd_share()
    elif a.cmd == "attrib":
        cmd_attrib()
    else:
        (R.RES / "book_corr.json").write_text(json.dumps(book_corr(), indent=1))


if __name__ == "__main__":
    main()
