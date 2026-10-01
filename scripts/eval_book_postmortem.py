"""Analysis of the equity book v1 post-mortem (T-20261001-19; ``postmortem/prereg.md``).

Stages (each reads raw files, writes its section of ``postmortem/results.json``; none reruns a
backtest):

    ladder   L0 (T-08 close paths) / L1 / L2c / L2a x {M0_A, M1_C} x offsets 0-4: per-window net and
             gross Sharpe, excess, vol, max DD, beta, turnover, costs, style exposures; D1-D3; the
             M0 signal reference.
    tc       transfer coefficient of L0 and L1 at every rebalance.
    attrib   offset-blended P&L attribution of L0 and L1 (market, industry, styles, specific,
             ETF-hedge leg, T-bill leg, costs, unreconciled).

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/eval_book_postmortem.py --stage ladder

Metric maths is ``open_composer.research.equity_book.evaluate`` and the helpers of
``scripts/eval_book_rf1.py`` / ``scripts/eval_book_v1_stage2.py`` (imported, not copied).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book.evaluate import window_metrics  # noqa: E402
from scripts import eval_book_rf1 as rf1  # noqa: E402

ev = rf1.ev
PM_DIR = ROOT / "reports/research/iterations/t20261001_book_v1/postmortem"
PM_CACHE = PM_DIR / "cache"
RESULTS = PM_DIR / "results.json"
RISK_DIR = ROOT / "data/research/equity_book/risk"
SIGNAL = ROOT / "data/research/equity_book/regimes/signal_ls_daily.parquet"

WINDOWS = {
    "A": ("2024-01-08", "2026-06-30"),
    "B": ("2026-07-01", "2026-09-17"),
    "stress": ("2017-10-02", "2023-08-31"),
    "anchor": ("2024-01-08", "2026-09-17"),
}
VARIANTS = ("M0_A", "M1_C")
OFFSETS = (0, 1, 2, 3, 4)
RUNGS = ("L0", "L1", "L2c", "L2a")
REF_CAPS = {"size": 0.10}  # every other style: 0.25 (the L0 cap)
REF_STYLE_CAP = 0.25
CAP_TOL = 1e-4
D1_A_GROSS, D1_STRESS_GROSS = 0.30, -0.30
D2_A_NET, D2_STRESS_NET = 0.15, 0.0
D3_DRAG = 0.30
TRADING_DAYS = 252


# ---------------------------------------------------------------------------
# pure helpers (unit tested)
# ---------------------------------------------------------------------------


def share_at_cap(exposure: np.ndarray, cap: float, tol: float = CAP_TOL) -> float:
    """Share of rebalances whose absolute style exposure is at or above ``cap - tol``."""
    e = np.abs(np.asarray(exposure, dtype="float64"))
    return float(np.mean(e >= cap - tol)) if len(e) else float("nan")


def style_summary(
    rec: pd.DataFrame, n_groups: int, styles: Sequence[str], window: tuple[str, str]
) -> dict[str, Any]:
    """Mean signed target exposure and share at the L0 reference cap per style, over the
    rebalances with decision date in ``window``.  ``rec`` has ``date`` and ``exposures_target``
    (JSON list: market, industry groups, styles)."""
    a, b = window
    sub = rec[(rec["date"] >= a) & (rec["date"] <= b) & rec["exposures_target"].notna()]
    if len(sub) == 0:
        return {"n": 0}
    arr = np.array([json.loads(x) for x in sub["exposures_target"]], dtype="float64")
    sty = arr[:, 1 + n_groups :]
    out: dict[str, Any] = {"n": int(len(sub))}
    for i, s in enumerate(styles):
        cap = REF_CAPS.get(s, REF_STYLE_CAP)
        out[s] = {
            "mean": float(sty[:, i].mean()),
            "mean_abs": float(np.abs(sty[:, i]).mean()),
            "share_at_ref_cap": share_at_cap(sty[:, i], cap),
        }
    return out


def transfer_coefficient(
    weights: pd.Series, score: pd.Series, sigma: pd.Series | None = None
) -> dict[str, float]:
    """Cross-sectional Pearson correlations over the names in ``score`` (finite values): plain
    ``corr(w, score)``; and, when ``sigma`` is given, the risk-adjusted form of Clarke, de Silva and
    Thorley (2002), ``corr(w * sigma, score)`` with ``sigma`` the residual (specific) volatility
    (alpha / sigma = IC * score).  Names not in ``weights`` have weight 0."""
    s = score.dropna()
    w = weights.reindex(s.index).fillna(0.0)
    out = {"n_universe": int(len(s)), "n_held": int((w != 0).sum())}

    def corr(x: np.ndarray, y: np.ndarray) -> float:
        if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
            return float("nan")
        return float(np.corrcoef(x, y)[0, 1])

    out["tc"] = corr(w.to_numpy("float64"), s.to_numpy("float64"))
    if sigma is not None:
        sg = sigma.reindex(s.index)
        ok = sg.notna().to_numpy()
        out["tc_risk_adjusted"] = corr(
            (w.to_numpy("float64") * sg.to_numpy("float64"))[ok], s.to_numpy("float64")[ok]
        )
    return out


def attribute_day(
    w: pd.Series,
    ret: pd.Series,
    x: pd.DataFrame,
    f: pd.Series,
    factor_names: Sequence[str],
    groups: Sequence[str],
    styles: Sequence[str],
) -> dict[str, float]:
    """One day of the stock-book return split: ``w`` holdings (fractions of equity at the start of
    the day), ``ret`` the day's stock returns, ``x`` exposures (rows: names; names without a row
    have zero exposures), ``f`` the day's factor returns.  Components sum to ``sum(w * ret)``:
    market + industry + styles + specific."""
    r = ret.reindex(w.index).fillna(0.0)
    total = float((w * r).sum())
    xe = x.reindex(w.index).fillna(0.0)
    expo = (xe[list(factor_names)].mul(w, axis=0)).sum(axis=0)
    contrib = expo * f.reindex(factor_names).fillna(0.0)
    out = {"market": float(contrib["market"])}
    out["industry"] = float(contrib[list(groups)].sum())
    for s in styles:
        out[f"style_{s}"] = float(contrib[s])
    out["specific"] = total - float(contrib.sum())
    return out


def ladder_decisions(med: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, Any]:
    """D1, D2, D3 of prereg section 4.  ``med[rung][variant]`` carries the median-over-offsets
    ``net_sharpe`` / ``gross_sharpe`` per window name."""

    def g(rung: str, v: str, key: str, w: str) -> float:
        return float(med[rung][v][key][w])

    out: dict[str, Any] = {"D1": {}, "D2": {}, "D2a": {}, "D3": {}}
    for v in VARIANTS:
        dg_a = g("L1", v, "gross_sharpe", "A") - g("L0", v, "gross_sharpe", "A")
        dg_s = g("L1", v, "gross_sharpe", "stress") - g("L0", v, "gross_sharpe", "stress")
        out["D1"][v] = {
            "gross_A_change": dg_a,
            "gross_stress_change": dg_s,
            "pass": bool(dg_a >= D1_A_GROSS and dg_s >= D1_STRESS_GROSS),
        }
        for key, rung in (("D2", "L2c"), ("D2a", "L2a")):
            da = g(rung, v, "net_sharpe", "A") - g("L1", v, "net_sharpe", "A")
            ds = g(rung, v, "net_sharpe", "stress") - g("L1", v, "net_sharpe", "stress")
            out[key][v] = {
                "net_A_change": da,
                "net_stress_change": ds,
                "pass": bool(da >= D2_A_NET and ds >= D2_STRESS_NET),
            }
        drag = g("L1", v, "gross_sharpe", "A") - g("L1", v, "net_sharpe", "A")
        out["D3"][v] = {"cost_drag_A": drag, "pass": bool(drag > D3_DRAG)}
    for k in ("D1", "D2", "D2a", "D3"):
        out[k]["both_variants"] = bool(all(out[k][v]["pass"] for v in VARIANTS))
    return out


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------


def path_dir(rung: str, variant: str, k: int) -> Path:
    if rung == "L0":
        hits = sorted(rf1.CACHE.glob(f"*/{variant}_o{k}_close"))
    else:
        hits = sorted(PM_CACHE.glob(f"**/PM_{rung}_{variant}_o{k}"))
    if len(hits) != 1:
        raise FileNotFoundError(f"{rung} {variant} o{k}: {len(hits)} dirs")
    return hits[0]


def load_daily(d: Path) -> pd.DataFrame:
    daily = pd.read_parquet(d / "daily.parquet").set_index("trade_date").sort_index()
    daily.index = pd.to_datetime(daily.index)
    return daily


def load_records(d: Path) -> pd.DataFrame:
    rec = pd.read_parquet(d / "records.parquet", columns=["date", "exposures_target", "ok"])
    rec["date"] = pd.to_datetime(rec["date"])
    return rec


def now_utc() -> str:
    return subprocess.check_output(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True).strip()


def write_section(name: str, section: Any) -> None:
    doc = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    doc[name] = section
    doc[f"{name}_generated_at_utc"] = now_utc()
    RESULTS.write_text(json.dumps(ev.clean(doc), indent=1, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# ladder
# ---------------------------------------------------------------------------


def path_block(
    d: Path,
    rf: pd.Series,
    spy: pd.Series,
    bil: pd.Series,
    shy: pd.Series,
    n_groups: int,
    styles: Sequence[str],
) -> dict[str, Any]:
    daily = load_daily(d)
    rec = load_records(d)
    net = daily["net"]
    net_ca = ev.cash_aligned(net, bil, shy)
    out: dict[str, Any] = {"windows": {}}
    for w, win in WINDOWS.items():
        p = window_metrics(net, rf, spy, win, daily)
        a = window_metrics(net_ca, rf, spy, win)
        g = window_metrics(daily["gross"], rf, spy, win)
        out["windows"][w] = {
            "net_sharpe": rf1.min_stat(p, a, "sharpe"),
            "net_sharpe_plain": p.get("sharpe", float("nan")),
            "net_sharpe_cash_aligned": a.get("sharpe", float("nan")),
            "gross_sharpe": g.get("sharpe", float("nan")),
            "net_ann_excess": rf1.min_stat(p, a, "ann_excess_return"),
            "vol": p.get("vol", float("nan")),
            "max_dd": p.get("max_dd", float("nan")),
            "beta_ols": p.get("beta_spy", float("nan")),
            "beta_dimson": ev.dimson_beta(net, spy, win),
            "turnover_one_sided_ann": p.get("turnover", float("nan")),
            "costs_bp_per_year": ev._window_costs_bp(daily, win),
            "styles": style_summary(rec, n_groups, styles, win),
        }
    return out


def flat_numeric(d: Mapping[str, Any], prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, Mapping):
            out.update(flat_numeric(v, key + "."))
        elif isinstance(v, (int, float, np.floating)) and not isinstance(v, bool):
            out[key] = float(v)
    return out


def nest(flat: Mapping[str, float]) -> dict[str, Any]:
    root: dict[str, Any] = {}
    for key, v in flat.items():
        parts = key.split(".")
        cur = root
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = v
    return root


def median_blocks(blocks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    flats = [flat_numeric(b) for b in blocks]
    keys = sorted(set().union(*[set(f) for f in flats]))
    return nest({k: rf1.median([f.get(k, float("nan")) for f in flats]) for k in keys})


def signal_reference(rf: pd.Series, spy: pd.Series) -> dict[str, Any]:
    s = pd.read_parquet(SIGNAL)["m0_composite"]
    zero = pd.Series(0.0, index=rf.index)  # a dollar-neutral long-short earns no risk-free rate
    out = {
        "series": "data/research/equity_book/regimes/signal_ls_daily.parquet:m0_composite",
        "convention": "raw mean/std*sqrt(252), no risk-free subtraction",
        "last_date": str(s.index.max().date()),
    }
    for w, win in WINDOWS.items():
        m = window_metrics(s, zero, spy, win)
        out[w] = {"sharpe": m.get("sharpe", float("nan")), "n": m.get("n", 0)}
    return out


def run_ladder() -> None:
    rf, spy = rf1.load_rf_spy()
    bil, shy = ev.load_bil_shy()
    meta = json.loads((RISK_DIR / "meta.json").read_text())
    n_groups, styles = len(meta["groups"]), list(meta["styles"])
    per_path: dict[str, Any] = {}
    med: dict[str, dict[str, Any]] = {r: {} for r in RUNGS}
    for rung in RUNGS:
        for v in VARIANTS:
            blocks = []
            for k in OFFSETS:
                b = path_block(path_dir(rung, v, k), rf, spy, bil, shy, n_groups, styles)
                per_path[f"{rung}_{v}_o{k}"] = b
                blocks.append(b)
            m = median_blocks(blocks)
            # the decision rules read median net / gross Sharpe per window
            m["net_sharpe"] = {w: m["windows"][w]["net_sharpe"] for w in WINDOWS}
            m["gross_sharpe"] = {w: m["windows"][w]["gross_sharpe"] for w in WINDOWS}
            med[rung][v] = m
    res = {
        "windows": WINDOWS,
        "rule": "per offset min(plain, cash-aligned) net Sharpe; median over 5 offsets",
        "median": med,
        "decisions": ladder_decisions(med),
        "signal_reference": signal_reference(rf, spy),
        "per_path": per_path,
    }
    write_section("ladder", res)
    for v in VARIANTS:
        for rung in RUNGS:
            nm, gm = med[rung][v]["net_sharpe"], med[rung][v]["gross_sharpe"]
            print(
                f"{rung} {v}: net A {nm['A']:.3f} B {nm['B']:.3f} stress {nm['stress']:.3f} | "
                f"gross A {gm['A']:.3f} B {gm['B']:.3f} stress {gm['stress']:.3f}"
            )
    print(json.dumps(ev.clean(res["decisions"]), ensure_ascii=False))


# ---------------------------------------------------------------------------
# transfer coefficient
# ---------------------------------------------------------------------------


def run_tc() -> None:
    from open_composer.research.equity_book.backtest import TBILL
    from open_composer.research.equity_book.optimize import TBILL_SYMBOLS
    from open_composer.research.equity_book.panel import HEDGE_ETFS, PanelAttributes, PricePanel
    from open_composer.research.equity_book.risk import RiskModel
    from scripts.build_book_v1_alpha import OUT_DIR
    from scripts.run_book_v1_stage2 import (
        DEFAULT_END,
        LOAD_START,
        UNIVERSE_OF,
        AlphaSource,
        FormationIC,
        ThemeStore,
    )

    non_stock = set(HEDGE_ETFS) | set(TBILL_SYMBOLS) | {TBILL}
    panel = PricePanel.from_dir(
        start=LOAD_START, end=DEFAULT_END, symbols=[], include_etfs=False, load_open=False
    )
    rm = RiskModel()
    attrs = PanelAttributes()
    store = ThemeStore()
    fic = FormationIC(pd.read_parquet(OUT_DIR / "formation_ic.parquet"), panel.dates)

    class _State:
        def __init__(self, pos: int) -> None:
            self.pos = pos

    rows: list[dict[str, Any]] = []
    cache_m0: dict[tuple[str, pd.Timestamp], tuple[pd.Series, pd.Series]] = {}
    for rung in ("L0", "L1"):
        for v in VARIANTS:
            method, config = v.split("_")
            uni_name = UNIVERSE_OF[config]
            ucol = "in_p1000" if config == "C" else "in_u3000"
            for k in OFFSETS:
                d = path_dir(rung, v, k)
                tg = pd.read_parquet(d / "targets.parquet")
                tg["decision_date"] = pd.to_datetime(tg["decision_date"])
                tg = tg[~tg["symbol"].isin(non_stock)]
                src = AlphaSource(store, fic, method, uni_name)
                for t, grp in tg.groupby("decision_date"):
                    key = (v, t)
                    if method == "M0" and key in cache_m0:
                        score, sigma = cache_m0[key]
                    else:
                        x, f, dvar = rm.at(t)
                        at = attrs.at(t)
                        universe = at.index[at[ucol].astype(bool).to_numpy()].intersection(x.index)
                        score = src(t, _State(panel.dates.get_loc(t)), universe)
                        sigma = pd.Series(
                            np.sqrt(np.maximum(dvar.reindex(universe).to_numpy(), 0.0)),
                            index=universe,
                        )
                        if method == "M0":
                            cache_m0[key] = (score, sigma)
                    w = grp.set_index("symbol")["weight"]
                    tc = transfer_coefficient(w, score, sigma)
                    rows.append({"rung": rung, "variant": v, "offset": k, "date": t, **tc})
                print(f"tc {rung} {v} o{k}: {len(rows)} rows", flush=True)
    df = pd.DataFrame(rows)
    df.to_parquet(PM_DIR / "tc_rebalances.parquet", index=False)
    res: dict[str, Any] = {
        "definition": "see prereg.md section 5",
        "n_rebalances": int(len(df)),
        "median": {},
    }
    for rung in ("L0", "L1"):
        for v in VARIANTS:
            sub = df[(df["rung"] == rung) & (df["variant"] == v)]
            res["median"][f"{rung}_{v}"] = {
                w: {
                    "n": int(len(sub[(sub["date"] >= a) & (sub["date"] <= b)])),
                    "tc": float(sub[(sub["date"] >= a) & (sub["date"] <= b)]["tc"].median()),
                    "tc_risk_adjusted": float(
                        sub[(sub["date"] >= a) & (sub["date"] <= b)]["tc_risk_adjusted"].median()
                    ),
                }
                for w, (a, b) in WINDOWS.items()
            }
    write_section("tc", res)
    print(json.dumps(ev.clean(res["median"]), ensure_ascii=False))


# ---------------------------------------------------------------------------
# attribution
# ---------------------------------------------------------------------------


def run_attrib() -> None:
    from open_composer.research.equity_book.backtest import TBILL
    from open_composer.research.equity_book.optimize import TBILL_SYMBOLS
    from open_composer.research.equity_book.panel import HEDGE_ETFS, PricePanel
    from open_composer.research.equity_book.risk import RiskModel

    meta = json.loads((RISK_DIR / "meta.json").read_text())
    factors, groups, styles = list(meta["factors"]), list(meta["groups"]), list(meta["styles"])
    etfs = set(HEDGE_ETFS)
    tbills = set(TBILL_SYMBOLS) | {TBILL}
    bil, _shy = ev.load_bil_shy()

    fr = pd.concat(
        [pd.read_parquet(RISK_DIR / f"factor_returns_{y}.parquet") for y in range(2017, 2027)]
    )
    fret = fr.pivot(index="trade_date", columns="factor", values="ret").sort_index()

    paths: dict[str, dict[str, Any]] = {}
    symbols: set[str] = set()
    for rung in ("L0", "L1"):
        for v in VARIANTS:
            for k in OFFSETS:
                d = path_dir(rung, v, k)
                tg = pd.read_parquet(d / "targets.parquet")
                tg["decision_date"] = pd.to_datetime(tg["decision_date"])
                symbols |= set(tg["symbol"]) - tbills
                paths[f"{rung}_{v}_o{k}"] = {
                    "rung": rung,
                    "variant": v,
                    "daily": load_daily(d),
                    "targets": {
                        t: g.set_index("symbol")["weight"] for t, g in tg.groupby("decision_date")
                    },
                }
    panel = PricePanel.from_dir(
        start="2017-09-01",
        end="2026-09-17",
        symbols=sorted(symbols - etfs),
        load_open=False,
    )
    close = panel.frame("close")
    ret = (close / close.shift(1) - 1.0).iloc[1:]
    dates = [t for t in ret.index if t >= pd.Timestamp("2017-10-02")]
    rm = RiskModel()
    comp_names = ["market", "industry", *[f"style_{s}" for s in styles], "specific"]
    out_rows: dict[str, list[dict[str, float]]] = {p: [] for p in paths}
    hold: dict[str, pd.Series] = {p: pd.Series(dtype="float64") for p in paths}
    xcache: tuple[pd.Timestamp | None, pd.DataFrame | None] = (None, None)
    for i, t in enumerate(dates):
        prev = ret.index[ret.index.get_loc(t) - 1]
        try:
            used = rm.resolve(prev)
        except KeyError:
            used = None
        if used is not None and used != xcache[0]:
            x, _f, _d = rm.at(used)
            xcache = (used, x)
        x = xcache[1]
        r = ret.loc[t]
        f = fret.loc[t] if t in fret.index else pd.Series(dtype="float64")
        for p, st in paths.items():
            daily = st["daily"]
            if t not in daily.index:
                continue
            eq_prev = daily["equity"].shift(1).loc[t]
            h = hold[p]
            row: dict[str, float] = {}
            if len(h) and np.isfinite(eq_prev):
                w_all = h / eq_prev
                w_stk = w_all[~w_all.index.isin(etfs)]
                w_etf = w_all[w_all.index.isin(etfs)]
                stock_total = float((w_stk * r.reindex(w_stk.index).fillna(0.0)).sum())
                if x is not None and len(f):
                    row = attribute_day(w_stk, r, x, f, factors, groups, styles)
                else:
                    row = {c: 0.0 for c in comp_names}
                    row["specific"] = stock_total
                etf_ret = float((w_etf * r.reindex(w_etf.index).fillna(0.0)).sum())
                row["etf_leg"] = etf_ret
                row["stock_total"] = stock_total
                # holdings drift
                h = h * (1.0 + r.reindex(h.index).fillna(0.0))
                hold[p] = h
            else:
                row = {c: 0.0 for c in comp_names}
                row["etf_leg"] = 0.0
                row["stock_total"] = 0.0
            tb = float(daily["tbill_exp"].shift(1).loc[t]) if i else 0.0
            row["tbill_leg"] = (0.0 if not np.isfinite(tb) else tb) * float(bil.get(t, 0.0))
            costs = float(
                daily.loc[
                    t, ["cost_spread", "cost_impact", "cost_fees", "cost_borrow", "cost_margin"]
                ].sum()
            )
            row["costs"] = -costs
            row["gross_reported"] = float(daily.loc[t, "gross"])
            row["net_reported"] = float(daily.loc[t, "net"])
            out_rows[p].append({"date": t, **row})
            tgt = st["targets"].get(t)
            if tgt is not None:
                eq_t = float(daily["equity"].loc[t])
                tgt = tgt[~tgt.index.isin(tbills)]
                hold[p] = tgt * eq_t
        if i % 250 == 0:
            print(f"attrib day {i}/{len(dates)}", flush=True)
    frames = {p: pd.DataFrame(rows).set_index("date") for p, rows in out_rows.items()}
    comps = [*comp_names, "etf_leg", "tbill_leg", "costs"]
    res: dict[str, Any] = {
        "definition": "see prereg.md section 6",
        "components": comps,
        "blended": {},
        "reconciliation": {},
    }
    for rung in ("L0", "L1"):
        for v in VARIANTS:
            sel = [frames[f"{rung}_{v}_o{k}"] for k in OFFSETS]
            blend = sum(s[comps + ["gross_reported", "net_reported"]] for s in sel) / len(sel)
            blend["unreconciled"] = blend["gross_reported"] - (
                blend[[c for c in comps if c != "costs"]].sum(axis=1)
            )
            blend.to_parquet(PM_DIR / f"attrib_{rung}_{v}.parquet")
            block: dict[str, Any] = {}
            for w, (a, b) in WINDOWS.items():
                sub = blend[(blend.index >= a) & (blend.index <= b)]
                block[w] = {
                    c: {
                        "ann_contribution": float(sub[c].mean() * TRADING_DAYS),
                        "sharpe": float(sub[c].mean() / sub[c].std(ddof=1) * np.sqrt(TRADING_DAYS))
                        if sub[c].std(ddof=1) > 0
                        else float("nan"),
                    }
                    for c in [*comps, "unreconciled", "gross_reported", "net_reported"]
                }
            res["blended"][f"{rung}_{v}"] = block
    write_section("attrib", res)
    for key, block in res["blended"].items():
        top = sorted(
            ((c, block["A"][c]["ann_contribution"]) for c in comps if c != "costs"),
            key=lambda kv: -abs(kv[1]),
        )[:4]
        print(key, [(c, round(x, 4)) for c, x in top])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["ladder", "tc", "attrib"], required=True)
    args = ap.parse_args()
    {"ladder": run_ladder, "tc": run_tc, "attrib": run_attrib}[args.stage]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
