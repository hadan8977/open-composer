#!/usr/bin/env python3
# ruff: noqa: E501
"""T-20261007-02 frozen run: R (scheduled releases, Kalshi) and J (odds jumps, Polymarket) -> results.json.
Usage: t0702_run.py [--part R|J|all]. Rules: scripts/t0702_pm_grid.py. Nothing here changes after results."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import t0702_pm_grid as G  # noqa: E402
import t15_engine as E  # noqa: E402
import t15_stats as T  # noqa: E402

from open_composer.research import scorecard_v2 as S  # noqa: E402

ET = ZoneInfo("America/New_York")
OUT = ROOT / "reports/research/iterations/t20261007_02_pm_event_study"
DATA = ROOT / "data/research/pm_event_study"
RECENT = pd.Timestamp(G.WINDOW_START)
SEEDS = 100
TOL = 2  # minutes allowed between requested and available bar

# ----------------------------------------------------------------------------- ETF minutes
_PX: dict[str, tuple[np.ndarray, np.ndarray]] = {}


def load_px():
    df = pd.read_parquet(DATA / "etf_minute.parquet", columns=["symbol", "timestamp", "open"])
    for sym, g in df.groupby("symbol"):
        g = g.sort_values("timestamp")
        _PX[sym] = (
            g.timestamp.values.astype("datetime64[m]").astype(np.int64),
            g.open.values.astype(float),
        )


def bar_open(sym: str, tmin: int):
    ts, op = _PX[sym]
    i = int(np.searchsorted(ts, tmin))
    if i < len(ts) and ts[i] - tmin <= TOL:
        return float(op[i]), int(ts[i])
    return None


def et_minute(tmin: int) -> int:
    d = datetime.fromtimestamp(tmin * 60, UTC).astimezone(ET)
    return d.hour * 60 + d.minute


def et_date(tmin: int):
    return datetime.fromtimestamp(tmin * 60, UTC).astimezone(ET).date()


def trade(
    sym: str, entry_min: int, hold_min: int, d: int, shift: int = 0, cap_et: int | None = None
):
    """Return dict(gross_bp, cost1_bp, cost2_bp, ret_long_bp, date) or None. d = +1 long, -1 short."""
    a = bar_open(sym, entry_min + shift)
    if a is None:
        return None
    ex_min = entry_min + shift + hold_min
    if cap_et is not None:
        em = et_minute(a[1])
        ex_min = min(ex_min, a[1] + (cap_et - em))
    b = bar_open(sym, ex_min)
    if b is None or b[1] <= a[1]:
        return None
    r = math.log(b[0] / a[0]) * 1e4
    out = {"date": et_date(a[1]), "entry": a[1], "exit": b[1], "ret_long_bp": r}
    for k, mult in (("1", 1.0), ("2", 2.0)):
        c_in_buy = G.one_way_cost_bp(sym, a[0], False, et_minute(a[1]), mult)
        c_in_sell = G.one_way_cost_bp(sym, a[0], True, et_minute(a[1]), mult)
        c_out_buy = G.one_way_cost_bp(sym, b[0], False, et_minute(b[1]), mult)
        c_out_sell = G.one_way_cost_bp(sym, b[0], True, et_minute(b[1]), mult)
        out["cost_long_" + k] = c_in_buy + c_out_sell  # long: buy in, sell out
        out["cost_short_" + k] = c_in_sell + c_out_buy  # short: sell in, buy out
    return out


# ----------------------------------------------------------------------------- calendar and series
def session_dates() -> pd.DatetimeIndex:
    ts, _ = _PX["SPY"]
    days = sorted({et_date(int(t)) for t in ts[::30]})
    d = pd.DatetimeIndex(pd.to_datetime(days))
    return d[(d >= RECENT)]


def daily(trades: list[dict], dates: pd.DatetimeIndex, signs: np.ndarray, mult="1") -> np.ndarray:
    idx = {pd.Timestamp(x): i for i, x in enumerate(dates)}
    out = np.zeros(len(dates))
    for t, s in zip(trades, signs, strict=False):
        i = idx.get(pd.Timestamp(t["date"]))
        if i is None:
            continue
        gross = s * t["ret_long_bp"]
        cost = t["cost_long_" + mult] if s > 0 else t["cost_short_" + mult]
        out[i] += (gross - cost) / 1e4
    return out


def daily_gross(trades, dates, signs):
    idx = {pd.Timestamp(x): i for i, x in enumerate(dates)}
    out = np.zeros(len(dates))
    for t, s in zip(trades, signs, strict=False):
        i = idx.get(pd.Timestamp(t["date"]))
        if i is not None:
            out[i] += s * t["ret_long_bp"] / 1e4
    return out


def placebo_sharpes(trades, signs, dates, rng, net=True):
    """Timing placebo: same entries, random direction, 100 seeds."""
    n = len(trades)
    if n == 0:
        return []
    idx = {pd.Timestamp(x): i for i, x in enumerate(dates)}
    di = np.array([idx.get(pd.Timestamp(t["date"]), -1) for t in trades])
    keep = di >= 0
    rl = np.array([t["ret_long_bp"] for t in trades])[keep]
    cl = np.array([t["cost_long_1"] for t in trades])[keep]
    cs = np.array([t["cost_short_1"] for t in trades])[keep]
    di = di[keep]
    res = []
    for _ in range(SEEDS):
        s = rng.choice([-1.0, 1.0], size=len(rl))
        pnl = s * rl - (np.where(s > 0, cl, cs) if net else 0.0)
        ser = np.bincount(di, weights=pnl / 1e4, minlength=len(dates))
        res.append(S.annual_sharpe(ser))
    return res


# ----------------------------------------------------------------------------- R events
def r_event_table() -> pd.DataFrame:
    df = pd.read_parquet(DATA / "r_events.parquet")
    df = df[df.release_utc <= pd.Timestamp(datetime.now(UTC))].copy()
    df["R1"] = df.E_pre - df.E_ref
    df["R2"] = df.E_pre - df.baseline
    df["ok"] = df.valid & (df.age_h.fillna(1e9) <= G.R_MAX_CANDLE_AGE_H)
    df = df.sort_values(["cls", "release_utc"])
    return df


def r_trades(
    df: pd.DataFrame,
    sig: str,
    h: int,
    asset: str,
    since: pd.Timestamp,
    until: pd.Timestamp | None = None,
    shift=0,
    classes=None,
):
    out, rows = [], []
    for cls, g in df.groupby("cls"):
        if classes is not None and cls not in classes:
            continue
        s_cls = G.R_HAWKISH_SIGN[cls]
        past: list[float] = []
        for _, e in g.iterrows():
            v = e[sig.split("_")[0]]
            if not (e.ok and np.isfinite(v)):
                continue
            thr = float(np.median(past)) if len(past) >= G.R_WARMUP_EVENTS else None
            past.append(abs(v))
            if thr is None or abs(v) < thr or v == 0:
                continue
            t0 = pd.Timestamp(e.release_utc).tz_convert("UTC")
            if t0 < since or (until is not None and t0 >= until):
                continue
            d = -1 if (s_cls * np.sign(v)) > 0 else 1  # hawkish -> short
            tm = int(t0.timestamp() // 60)
            tr = trade(asset, tm, h, d, shift)
            if tr is None:
                rows.append({"cls": cls, "skipped": True})
                continue
            tr.update(cls=cls, event=e.event, d=d)
            out.append(tr)
    return out


# ----------------------------------------------------------------------------- J events
def load_j_jumps(theta_min=3.0):
    q = json.load(open(DATA / "polymarket/qualified_markets.json"))
    rows = []
    for m in q:
        f = DATA / "polymarket/hist" / f"{m['token'][:24]}.json"
        if not f.exists():
            continue
        pts = json.load(open(f))["pts"]
        end = pd.Timestamp(m["end"]).timestamp() if m.get("end") else 4e9
        for (t0, p0), (t1, p1) in zip(pts[:-1], pts[1:], strict=False):
            dt = (t1 - t0) / 60
            if not (50 <= dt <= 75):
                continue
            dp = (p1 - p0) * 100
            if abs(dp) < theta_min:
                continue
            if min(p0, p1) < G.J_PRICE_BOUNDS[0] or max(p0, p1) > G.J_PRICE_BOUNDS[1]:
                continue
            if end - t1 < G.J_NEAR_END_HOURS * 3600:
                continue
            rows.append(
                {
                    "token": m["token"],
                    "theme": m["theme"],
                    "t1": int(t1),
                    "dp": dp,
                    "title": m["question"],
                }
            )
    return pd.DataFrame(rows)


def j_tradable(tsec: int) -> bool:
    d = datetime.fromtimestamp(tsec, UTC).astimezone(ET)
    if d.weekday() >= 5:
        return False
    lo = int(G.J_DECISION_WINDOW_ET[0][:2]) * 60 + int(G.J_DECISION_WINDOW_ET[0][3:])
    hi = int(G.J_DECISION_WINDOW_ET[1][:2]) * 60 + int(G.J_DECISION_WINDOW_ET[1][3:])
    return lo <= d.hour * 60 + d.minute <= hi


def j_episodes(jumps: pd.DataFrame, theta: float) -> pd.DataFrame:
    j = jumps[
        (jumps.dp.abs() >= theta) & (jumps.t1 >= pd.Timestamp(G.WINDOW_START, tz="UTC").timestamp())
    ].copy()
    j["tradable"] = j.t1.map(j_tradable)
    eps = []
    for _th, g in j[j.tradable].groupby("theme"):
        g = g.sort_values("t1")
        cur = None
        for _, r in g.iterrows():
            if cur is not None and r.t1 - cur["t1"] <= G.J_DEDUP_HOURS * 3600:
                if abs(r.dp) > abs(cur["dp"]):
                    cur = r.to_dict()
                    eps[-1] = cur  # same cluster, keep the largest
                continue
            cur = r.to_dict()
            eps.append(cur)
    return pd.DataFrame(eps), len(j), int(j.tradable.sum())


def j_trades(eps: pd.DataFrame, h: int, mode: str, shift=0, theme_filter=None, asset_override=None):
    if eps.empty:
        return []
    out = []
    last_exit: dict[str, int] = {}
    cap = int(G.J_EXIT_CAP_ET[:2]) * 60 + int(G.J_EXIT_CAP_ET[3:])
    for _, e in eps.sort_values("t1").iterrows():
        if theme_filter and e.theme != theme_filter:
            continue
        _, sign, etf, _x = G.THEMES[e.theme]
        if asset_override:
            etf = asset_override
        d = int(np.sign(e.dp)) * sign
        if mode == "reverse":
            d = -d
        tm = (
            int(e.t1 // 60) + 1
        )  # decision on the close of the minute of the later odds point, fill at the next bar
        if tm <= last_exit.get(etf, 0):
            continue
        tr = trade(etf, tm, h, d, shift, cap_et=cap)
        if tr is None:
            continue
        last_exit[etf] = tr["exit"]
        tr.update(theme=e.theme, d=d, token=e.token)
        out.append(tr)
    return out


# ----------------------------------------------------------------------------- stats
def variant_stats(trades, dates, masks, seed):
    signs = np.array([t["d"] for t in trades], float)
    net1 = daily(trades, dates, signs, "1")
    net2 = daily(trades, dates, signs, "2")
    gross = daily_gross(trades, dates, signs)
    rec = masks["recent"]
    n = len(trades)
    pnl_net = (
        np.array(
            [
                (
                    t["d"] * t["ret_long_bp"]
                    - (t["cost_long_1"] if t["d"] > 0 else t["cost_short_1"])
                )
                for t in trades
            ]
        )
        if n
        else np.array([])
    )
    pnl_gross = np.array([t["d"] * t["ret_long_bp"] for t in trades]) if n else np.array([])
    res = {
        "n_trades": n,
        "mean_gross_bp": float(pnl_gross.mean()) if n else None,
        "mean_net_bp": float(pnl_net.mean()) if n else None,
        "t_net_per_trade": float(pnl_net.mean() / (pnl_net.std(ddof=1) / math.sqrt(n)))
        if n > 2 and pnl_net.std(ddof=1) > 0
        else None,
        "hit_net": float((pnl_net > 0).mean()) if n else None,
        "sharpe_net": S.annual_sharpe(net1[rec]) if n >= 5 else None,
        "sharpe_gross": S.annual_sharpe(gross[rec]) if n >= 5 else None,
        "sharpe_net_cost2x": S.annual_sharpe(net2[rec]) if n >= 5 else None,
        "sd_trade_bp": float(np.sqrt(np.mean(np.array([t["ret_long_bp"] for t in trades]) ** 2)))
        if n
        else None,
        "mde_net_mean_bp_80pct": float(
            2.487
            * math.sqrt(np.mean(np.array([t["ret_long_bp"] for t in trades]) ** 2))
            / math.sqrt(n)
        )
        if n
        else None,
    }
    rng = np.random.default_rng(seed)
    pn = placebo_sharpes(trades, signs, dates, rng, True)
    pg = placebo_sharpes(trades, signs, dates, rng, False)
    res["placebo_net_pct"] = (
        S.placebo_percentile(res["sharpe_net"], pn)
        if res["sharpe_net"] is not None and pn
        else None
    )
    res["placebo_gross_pct"] = (
        S.placebo_percentile(res["sharpe_gross"], pg)
        if res["sharpe_gross"] is not None and pg
        else None
    )
    return res, net1, net2, gross


def finalize(variants, dates, masks, shifted_fn):
    """variants: list of dict(id, part, trades). Selection, DSR, robustness for the selected spec of each part."""
    keys = []
    nets = {}
    for v in variants:
        v["stats"], net1, net2, gross = variant_stats(
            v["trades"], dates, masks, seed=abs(hash(v["id"])) % (2**31)
        )
        nets[v["id"]] = (net1, net2, gross)
        keys.append(v["id"])
    rec = masks["recent"]
    X = np.array([nets[k][0] for k in keys])
    srs = np.array(
        [
            v["stats"]["sharpe_net"] if v["stats"]["sharpe_net"] is not None else np.nan
            for v in variants
        ]
    )
    var_sr = float(np.nanvar(srs, ddof=1)) if np.isfinite(srs).sum() > 2 else 0.0
    M = X[:, rec]
    M = M[np.std(M, axis=1) > 0]
    rho = float(np.nanmean(np.corrcoef(M)[np.triu_indices(len(M), 1)])) if len(M) > 2 else 0.0
    n_eff = S.n_eff_from_corr(len(keys), rho)
    sel = {}
    for part in ("R", "J"):
        pv = [v for v in variants if v["part"] == part and v["stats"]["sharpe_net"] is not None]
        if not pv:
            sel[part] = None
            continue
        top3 = sorted(pv, key=lambda v: -v["stats"]["sharpe_net"])[:3]
        med = sorted(top3, key=lambda v: v["stats"]["sharpe_net"])[len(top3) // 2]
        net1, net2, gross = nets[med["id"]]
        dsr = S.dsr(net1[rec][np.isfinite(net1[rec])], var_sr_annual=var_sr, n_eff=n_eff)
        rob = T.robustness(net1, net2, dates, masks, med["stats"]["placebo_gross_pct"])
        shifts = {}
        for sh in (0, 1, 2):
            tr = shifted_fn(med, sh)
            sg = np.array([t["d"] for t in tr], float)
            shifts[sh] = S.annual_sharpe(daily(tr, dates, sg, "1")[rec]) if len(tr) >= 5 else None
        d_ok = sum(1 for x in shifts.values() if x is not None and x > 0) >= 2
        rob["d_shift_sharpes"] = shifts
        rob["d_ok"] = bool(d_ok)
        rob["score"] += int(d_ok)
        p1 = T.tier_p1(dsr.get("dsr"), med["stats"]["placebo_net_pct"], rob["score"])
        sel[part] = {
            "selected": med["id"],
            "top3": [v["id"] for v in top3],
            "dsr": dsr,
            "robustness": rob,
            "p1": p1,
            "veto_V3_cost2x_sharpe_gt0": bool(
                med["stats"]["sharpe_net_cost2x"] is not None
                and med["stats"]["sharpe_net_cost2x"] > 0
            ),
        }
    return {
        "n_trials": len(keys),
        "var_sr_annual": var_sr,
        "mean_pairwise_corr": rho,
        "n_eff": n_eff,
    }, sel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="all")
    ap.add_argument("--out", default="results.json")
    a = ap.parse_args()
    load_px()
    dates = session_dates()
    masks = E.window_masks(dates)
    variants, extra = [], {}
    rdf = r_event_table()
    since = pd.Timestamp(G.WINDOW_START, tz="UTC")
    qual = [
        c
        for c, g in rdf[rdf.release_utc >= since].groupby("cls")
        if int(g.ok.sum()) >= G.R_MIN_EVENTS_PER_CLASS
    ]
    extra["R_qualifying_classes"] = qual
    extra["R_valid_events_by_class_since_2024"] = {
        c: int(g.ok.sum()) for c, g in rdf[rdf.release_utc >= since].groupby("cls")
    }
    if a.part in ("R", "all"):
        # positive control (not tradable): realised surprise, TLT [T, T+h]
        pc = []
        for _, e in rdf[
            (rdf.release_utc >= since) & rdf.ok & rdf.actual.notna() & rdf.cls.isin(qual)
        ].iterrows():
            v = e.actual - e.E_pre
            if v == 0 or not np.isfinite(v):
                continue
            d = -1 if G.R_HAWKISH_SIGN[e.cls] * np.sign(v) > 0 else 1
            tm = int(pd.Timestamp(e.release_utc).timestamp() // 60)
            for h in (5, 30):
                a_ = bar_open("TLT", tm)
                b_ = bar_open("TLT", tm + h)
                if a_ and b_:
                    pc.append(
                        {
                            "cls": e.cls,
                            "h": h,
                            "date": str(et_date(tm)),
                            "r": d * math.log(b_[0] / a_[0]) * 1e4,
                        }
                    )
        pcd = pd.DataFrame(pc)
        ctrl = {}
        for h, g in pcd.groupby("h"):
            by = g.groupby("date").r.mean()
            ctrl[int(h)] = {
                "n_events": int(len(g)),
                "mean_bp": float(g.r.mean()),
                "t_date_clustered": float(by.mean() / (by.std(ddof=1) / math.sqrt(len(by))))
                if len(by) > 2
                else None,
            }
        extra["R_positive_control_realised_surprise_TLT"] = ctrl
        extra["R_positive_control_passes"] = bool(
            ctrl.get(30, {}).get("t_date_clustered") is not None
            and ctrl[30]["t_date_clustered"] >= 2.0
        )
        for sg in G.R_SIGNALS:
            for h in G.R_HORIZONS_MIN:
                tr = r_trades(rdf[rdf.cls.isin(qual)], sg, h, G.R_ASSET, since)
                variants.append(
                    {
                        "id": f"R_{sg.split('_')[0]}_h{h}",
                        "part": "R",
                        "sig": sg,
                        "h": h,
                        "trades": tr,
                    }
                )
    jinfo = {}
    if a.part in ("J", "all"):
        jumps = load_j_jumps(3.0)
        eps_by = {}
        for th in G.J_THETA_PP:
            eps, n_raw, n_trad = j_episodes(jumps, th)
            eps_by[th] = eps
            jinfo[f"theta{th}"] = {
                "raw_jumps_since_2024": n_raw,
                "tradable_hours": n_trad,
                "episodes": int(len(eps)),
                "by_theme": eps.theme.value_counts().to_dict() if len(eps) else {},
            }
            for h in G.J_HORIZONS_MIN:
                for m in G.J_MODES:
                    variants.append(
                        {
                            "id": f"J_t{th}_h{h}_{m}",
                            "part": "J",
                            "th": th,
                            "h": h,
                            "mode": m,
                            "trades": j_trades(eps, h, m),
                        }
                    )
        extra["J_universe"] = jinfo

    def shifted(v, sh):
        if v["part"] == "R":
            return r_trades(rdf[rdf.cls.isin(qual)], v["sig"], v["h"], G.R_ASSET, since, shift=sh)
        return j_trades(eps_by[v["th"]], v["h"], v["mode"], shift=sh)

    meta, sel = finalize(variants, dates, masks, shifted)
    res = {
        "generated_at": datetime.now(UTC).isoformat(),
        "window": [G.WINDOW_START, str(dates.max().date())],
        "sessions": int(len(dates)),
        "dsr_meta": meta,
        "selection": sel,
        **extra,
        "variants": [{"id": v["id"], "part": v["part"], **v["stats"]} for v in variants],
    }
    # report-only breakdowns
    rep = {}
    if a.part in ("R", "all"):
        for cls in qual:
            for sg in G.R_SIGNALS:
                tr = r_trades(rdf, sg, 30, G.R_ASSET, since, classes=[cls])
                pn = np.array(
                    [
                        t["d"] * t["ret_long_bp"]
                        - (t["cost_long_1"] if t["d"] > 0 else t["cost_short_1"])
                        for t in tr
                    ]
                )
                rep[f"R_class_{cls}_{sg}_h30_TLT"] = {
                    "n": len(tr),
                    "mean_net_bp": float(pn.mean()) if len(tr) else None,
                    "t": float(pn.mean() / (pn.std(ddof=1) / math.sqrt(len(pn))))
                    if len(pn) > 2 and pn.std(ddof=1) > 0
                    else None,
                }
        for asset in G.R_SECONDARY:
            for sg in G.R_SIGNALS:
                tr = r_trades(rdf[rdf.cls.isin(qual)], sg, 30, asset, since)
                pn = np.array(
                    [
                        t["d"] * t["ret_long_bp"]
                        - (t["cost_long_1"] if t["d"] > 0 else t["cost_short_1"])
                        for t in tr
                    ]
                )
                rep[f"R_pooled_{sg}_h30_{asset}"] = {
                    "n": len(tr),
                    "mean_net_bp": float(pn.mean()) if len(tr) else None,
                    "t": float(pn.mean() / (pn.std(ddof=1) / math.sqrt(len(pn))))
                    if len(pn) > 2 and pn.std(ddof=1) > 0
                    else None,
                }
    if a.part in ("J", "all"):
        for th in sorted({t for t in eps_by}):
            for theme in sorted(G.THEMES):
                for m in G.J_MODES:
                    tr = j_trades(eps_by[th], 60, m, theme_filter=theme)
                    if not tr:
                        continue
                    pn = np.array(
                        [
                            t["d"] * t["ret_long_bp"]
                            - (t["cost_long_1"] if t["d"] > 0 else t["cost_short_1"])
                            for t in tr
                        ]
                    )
                    rep[f"J_theme_{theme}_t{th}_h60_{m}"] = {
                        "n": len(tr),
                        "mean_net_bp": float(pn.mean()),
                        "t": float(pn.mean() / (pn.std(ddof=1) / math.sqrt(len(pn))))
                        if len(pn) > 2 and pn.std(ddof=1) > 0
                        else None,
                    }
    res["report_only_not_for_selection"] = rep
    (OUT / a.out).write_text(json.dumps(res, indent=2, default=str) + "\n")
    print("wrote", a.out, "variants", len(variants))


if __name__ == "__main__":
    main()
