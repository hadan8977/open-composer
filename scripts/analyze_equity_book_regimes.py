"""Market regime phases and signal performance by phase for the equity book (2026-10-01).

Two stages, run in order:

``--stage market``   SPY / IWM / VIX / breadth state and SPY drawdown episodes -> the phase list.
                     The phase rule is fixed in this file before any signal number is computed.
``--stage signals``  industry- and beta-neutral daily long-short returns of every v1 library
                     signal and theme, by phase, by owner window and by ex-ante market state; a
                     factor-momentum timing check; risk-model style factor returns by phase.

These are measurements on data the project has already seen.  They feed the Stage-2 contract
amendment (which windows decide a pass) and the combiner design (whether recent-performance
weighting adds value); they do not select signals.

Signal return convention: the processed score at the close of t (point-in-time, built by
``scripts/build_equity_book_signals.py``) is held from the open of t+1 to the open of t+2.  The
stock return is beta-hedged with the panel's 252-day SPY beta and demeaned within the risk
model's industry group, so each series is an industry- and beta-neutral long-short return with
$1 long and $1 short.  Names without a return on the day drop out (no delisting return): a
diagnostic simplification, stated in the report.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/research/equity_book"
WORK = DATA / "regimes"
OUT = ROOT / "reports/research/program/regimes-2026-10-01"
VIX_DIR = ROOT / "data/research/vix"

# ---- the phase rule (fixed before any signal number is computed) -------------------------------
DD_THRESHOLD = 0.07  # an SPY close-to-close drawdown of at least 7% defines a correction episode
OWNER_NODE = "2026-07-01"  # owner's split, 2026-10-01: 2024-01..2026-06 vs 2026-07..now
STATE_FIT_END = "2023-08-31"  # VIX tercile thresholds are fitted on 2016-01..2023-08 only
MIN_PHASE_SESSIONS = 10
WINDOWS = {
    "stress": ("2017-10-02", "2023-08-31"),
    "anchor": ("2024-01-08", "2026-09-15"),
    "owner_A_2024_01_2026_06": ("2024-01-08", "2026-06-30"),
    "owner_B_2026_07_now": ("2026-07-01", "2026-09-15"),
}
SIGNAL_START, SIGNAL_END = "2017-10-02", "2026-09-15"  # last t with an open at t+2 (data 09-17)
COST_PER_SIDE = 0.0008  # rough all-in one-way cost for the net column (close execution, U3000)
SECTORS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")


# ---------------------------------------------------------------------------
# market stage
# ---------------------------------------------------------------------------
def load_etf() -> tuple[pd.DataFrame, pd.DataFrame]:
    e = pd.read_parquet(DATA / "etf_daily.parquet")
    close = e.pivot(index="trade_date", columns="symbol", values="close").sort_index()
    open_ = e.pivot(index="trade_date", columns="symbol", values="open").sort_index()
    return open_, close


def load_vix() -> pd.DataFrame:
    out = {}
    for name in ("VIXCLS", "VXVCLS"):
        v = pd.read_csv(VIX_DIR / f"{name}.csv", na_values=["."])
        v["observation_date"] = pd.to_datetime(v["observation_date"])
        out[name] = v.set_index("observation_date")[name].astype(float)
    return pd.DataFrame(out)


def breadth_series() -> pd.Series:
    """Share of U3000 members whose close is above their 200-session mean (needs >= 150 obs)."""
    closes, members = [], []
    for p in sorted((DATA / "panel").glob("20*.parquet")):
        df = pd.read_parquet(p, columns=["trade_date", "symbol", "close", "in_u3000"])
        closes.append(
            df.pivot(index="trade_date", columns="symbol", values="close").astype("float32")
        )
        members.append(df.loc[df["in_u3000"], ["trade_date", "symbol"]])
    close = pd.concat(closes).sort_index()
    close = close.groupby(level=0).last()
    sma = close.rolling(200, min_periods=150).mean()
    above = (close > sma).where(sma.notna())
    m = pd.concat(members)
    m["v"] = 1.0
    mem = m.pivot_table(index="trade_date", columns="symbol", values="v", aggfunc="first")
    mem = mem.reindex(index=above.index, columns=above.columns)
    a = above.where(mem.notna())
    return a.mean(axis=1, skipna=True).rename("breadth_200")


def drawdown_episodes(close: pd.Series, threshold: float) -> list[dict]:
    """Peak -> trough -> recovery episodes whose close-to-close drawdown reaches ``threshold``."""
    eps: list[dict] = []
    peak_px, peak_dt = close.iloc[0], close.index[0]
    trough_px, trough_dt = peak_px, peak_dt
    in_dd = False
    for dt, px in close.items():
        if px >= peak_px:
            if in_dd:
                eps.append(
                    {
                        "peak": peak_dt,
                        "trough": trough_dt,
                        "recovery": dt,
                        "depth": trough_px / peak_px - 1.0,
                    }
                )
                in_dd = False
            peak_px, peak_dt = px, dt
            trough_px, trough_dt = px, dt
            continue
        if px < trough_px:
            trough_px, trough_dt = px, dt
        if trough_px / peak_px - 1.0 <= -threshold:
            in_dd = True
    if in_dd:
        eps.append(
            {
                "peak": peak_dt,
                "trough": trough_dt,
                "recovery": None,
                "depth": trough_px / peak_px - 1,
            }
        )
    return eps


def build_phases(sessions: pd.DatetimeIndex, eps: list[dict], start: str, end: str) -> list[dict]:
    """Cut [start, end] at every episode peak, trough and recovery and at the owner node; label
    each piece advance / correction / rebound; merge pieces shorter than MIN_PHASE_SESSIONS into
    the previous piece."""
    s = sessions[(sessions >= pd.Timestamp(start)) & (sessions <= pd.Timestamp(end))]
    label = pd.Series("advance", index=s)
    cuts = {s[0], pd.Timestamp(OWNER_NODE)} if pd.Timestamp(OWNER_NODE) <= s[-1] else {s[0]}
    for e in eps:
        rec = e["recovery"] if e["recovery"] is not None else s[-1] + pd.Timedelta(days=1)
        label[(s > e["peak"]) & (s <= e["trough"])] = "correction"
        label[(s > e["trough"]) & (s < rec)] = "rebound"
        for c in (e["peak"], e["trough"], rec):
            nxt = s[s > c]
            if len(nxt):
                cuts.add(nxt[0])
    cuts = sorted(c for c in cuts if s[0] <= c <= s[-1])
    pieces = []
    for i, c in enumerate(cuts):
        stop = cuts[i + 1] if i + 1 < len(cuts) else s[-1] + pd.Timedelta(days=1)
        idx = s[(s >= c) & (s < stop)]
        if len(idx) == 0:
            continue
        pieces.append({"start": idx[0], "end": idx[-1], "n": len(idx), "label": label[idx[0]]})
    merged: list[dict] = []
    for p in pieces:
        if merged and p["n"] < MIN_PHASE_SESSIONS:
            merged[-1]["end"], merged[-1]["n"] = p["end"], merged[-1]["n"] + p["n"]
        else:
            merged.append(dict(p))
    for i, p in enumerate(merged):
        p["id"] = f"P{i + 1:02d}"
    return merged


def run_market() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    _, close = load_etf()
    spy = close["SPY"].dropna()
    sessions = spy.index
    vix = load_vix().reindex(sessions).ffill(limit=3)
    st = pd.DataFrame(index=sessions)
    st["spy"] = spy
    st["sma200"] = spy.rolling(200).mean()
    st["above200"] = st["spy"] > st["sma200"]
    st["dd"] = spy / spy.cummax() - 1.0
    lr = np.log(spy).diff()
    st["rv21"] = lr.rolling(21).std() * math.sqrt(252)
    st["ret63"] = spy.pct_change(63)
    st["iwm_spy_63"] = (close["IWM"] / spy).pct_change(63)
    st["vix"] = vix["VIXCLS"]
    st["vix_vxv"] = vix["VIXCLS"] / vix["VXVCLS"]
    st["breadth_200"] = breadth_series().reindex(sessions)
    fit = st.loc[:STATE_FIT_END, "vix"].dropna()
    lo, hi = float(fit.quantile(1 / 3)), float(fit.quantile(2 / 3))
    st["vix_state"] = np.where(st["vix"] <= lo, "low", np.where(st["vix"] <= hi, "mid", "high"))
    st.loc[st["vix"].isna(), "vix_state"] = None
    st["trend_state"] = np.where(st["above200"], "up", "down")
    st.loc[st["sma200"].isna(), "trend_state"] = None
    st["state"] = st["trend_state"] + "_" + st["vix_state"]
    st.to_parquet(WORK / "market_state.parquet")

    eps = drawdown_episodes(spy[spy.index >= "2016-01-01"], DD_THRESHOLD)
    phases_recent = build_phases(sessions, eps, "2024-01-08", SIGNAL_END)
    phases_hist = build_phases(sessions, eps, "2017-10-02", "2023-08-31")
    for p in phases_hist:
        p["id"] = "H" + p["id"][1:]

    def describe(p: dict) -> dict:
        w = st.loc[p["start"] : p["end"]]
        prev = st.loc[: p["start"]].iloc[-2] if len(st.loc[: p["start"]]) > 1 else w.iloc[0]
        sec = close.loc[p["start"] : p["end"], list(SECTORS)]
        sec_prev = close.loc[: p["start"], list(SECTORS)].iloc[-2]
        sec_ret = (sec.iloc[-1] / sec_prev - 1.0).dropna().sort_values()
        iwm_prev = close.loc[: p["start"], "IWM"].iloc[-2]
        return {
            "id": p["id"],
            "start": str(p["start"].date()),
            "end": str(p["end"].date()),
            "sessions": int(p["n"]),
            "label": p["label"],
            "spy_return": float(w["spy"].iloc[-1] / prev["spy"] - 1.0),
            "iwm_minus_spy": float(
                (close.loc[p["end"], "IWM"] / iwm_prev - 1.0)
                - (w["spy"].iloc[-1] / prev["spy"] - 1)
            ),
            "max_dd_in_phase": float((w["spy"] / w["spy"].cummax() - 1.0).min()),
            "realized_vol": float(lr.loc[p["start"] : p["end"]].std() * math.sqrt(252)),
            "vix_mean": float(w["vix"].mean()),
            "vix_max": float(w["vix"].max()),
            "breadth_mean": float(w["breadth_200"].mean()),
            "best_sector": f"{sec_ret.index[-1]} {sec_ret.iloc[-1]:+.1%}",
            "worst_sector": f"{sec_ret.index[0]} {sec_ret.iloc[0]:+.1%}",
            "state_mix": {
                k: round(float(v), 3) for k, v in w["state"].value_counts(normalize=True).items()
            },
        }

    last = st.dropna(subset=["vix"]).iloc[-1]
    res = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        "rule": {
            "drawdown_threshold": DD_THRESHOLD,
            "owner_node": OWNER_NODE,
            "min_phase_sessions": MIN_PHASE_SESSIONS,
            "vix_terciles_fit": f"2016-01..{STATE_FIT_END}",
            "vix_low_max": lo,
            "vix_mid_max": hi,
            "trend": "SPY close above its 200-session mean",
        },
        "episodes": [
            {
                "peak": str(e["peak"].date()),
                "trough": str(e["trough"].date()),
                "recovery": None if e["recovery"] is None else str(e["recovery"].date()),
                "depth": float(e["depth"]),
            }
            for e in eps
        ],
        "phases_recent": [describe(p) for p in phases_recent],
        "phases_hist": [describe(p) for p in phases_hist],
        "latest_state": {
            "date": str(last.name.date()),
            "spy_vs_sma200": float(last["spy"] / last["sma200"] - 1.0),
            "dd": float(last["dd"]),
            "rv21": float(last["rv21"]),
            "vix": float(last["vix"]),
            "vix_vxv": float(last["vix_vxv"]),
            "breadth_200": None if pd.isna(last["breadth_200"]) else float(last["breadth_200"]),
            "state": last["state"],
        },
        "state_share": {
            k: {
                s: round(float(v), 3)
                for s, v in st.loc[a:b, "state"].value_counts(normalize=True).items()
            }
            for k, (a, b) in WINDOWS.items()
        },
    }
    (WORK / "phases.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


# ---------------------------------------------------------------------------
# signals stage
# ---------------------------------------------------------------------------
def signal_columns() -> tuple[list[str], dict[str, list[str]]]:
    """Processed signal names with a coverage flag, and theme -> member names."""
    sch = pq.ParquetFile(DATA / "signals/2026.parquet").schema_arrow.names
    names = [n[: -len("_cov")] for n in sch if n.endswith("_cov")]
    from open_composer.research.equity_book.signals import THEME_SIGNALS

    return names, {t: list(v) for t, v in THEME_SIGNALS.items()}


def year_returns(year: int, sessions: pd.DatetimeIndex, spy_open: pd.Series) -> pd.DataFrame:
    """Long (trade_date, symbol, e): beta-hedged open(t+1)->open(t+2) stock return."""
    frames = [pd.read_parquet(DATA / f"prices/{year}.parquet")]
    nxt = DATA / f"prices/{year + 1}.parquet"
    if nxt.exists():
        n = pd.read_parquet(nxt)
        frames.append(n[n["trade_date"] <= n["trade_date"].min() + pd.Timedelta(days=10)])
    px = pd.concat(frames)
    op = px.pivot(index="trade_date", columns="symbol", values="open").sort_index()
    cal = sessions[(sessions >= op.index.min()) & (sessions <= op.index.max())]
    op = op.reindex(cal)
    r = op.shift(-2) / op.shift(-1) - 1.0
    so = spy_open.reindex(cal)
    r_spy = so.shift(-2) / so.shift(-1) - 1.0
    r = r[r.index.year == year]
    long = r.stack().rename("r").reset_index()
    long.columns = ["trade_date", "symbol", "r"]
    long["r_spy"] = long["trade_date"].map(r_spy)
    beta = pd.read_parquet(
        DATA / f"panel/{year}.parquet", columns=["trade_date", "symbol", "beta_252_spy"]
    )
    long = long.merge(beta, on=["trade_date", "symbol"], how="left")
    b = long["beta_252_spy"].fillna(1.0).clip(-0.5, 3.0)
    long["e"] = long["r"] - b * long["r_spy"]
    return long[["trade_date", "symbol", "e"]]


def ls_returns(
    df: pd.DataFrame, names: list[str], themes: dict[str, list[str]]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily industry/beta-neutral long-short return and turnover for each signal."""
    df = df.sort_values(["trade_date", "symbol"]).reset_index(drop=True)
    codes, dates = pd.factorize(df["trade_date"], sort=True)
    nd = len(dates)
    grp = codes.astype(np.int64) * 10_000 + df["ind_code"].to_numpy(np.int64)
    gcodes, _ = pd.factorize(grp)
    e = df["e"].to_numpy(float)
    gsum = np.bincount(gcodes, weights=e)
    gcnt = np.bincount(gcodes)
    e_dm = e - (gsum / gcnt)[gcodes]
    sym_codes, _ = pd.factorize(df["symbol"])
    out_f, out_to = {}, {}
    covers = {n: df[f"{n}_cov"].to_numpy(bool) for n in names}
    cols = list(names) + [f"theme_{t}" for t in themes] + ["m0_composite"]
    for col in cols:
        if col.startswith("theme_"):
            members = themes[col[len("theme_") :]]
            mask = np.zeros(len(df), bool)
            for m in members:
                mask |= covers[m]
        elif col == "m0_composite":
            mask = df["m0_n_themes"].to_numpy() > 0
        else:
            mask = covers[col]
        s = df[col].to_numpy(float)
        mask = mask & np.isfinite(s)
        sm = np.where(mask, s, 0.0)
        cnt = np.bincount(codes, weights=mask.astype(float), minlength=nd)
        mean = np.bincount(codes, weights=sm, minlength=nd) / np.maximum(cnt, 1)
        w = np.where(mask, s - mean[codes], 0.0)
        gross = np.bincount(codes, weights=np.abs(w), minlength=nd)
        ok_day = (cnt >= 50) & (gross > 0)
        w = np.where(ok_day[codes], 2.0 * w / np.where(gross > 0, gross, 1.0)[codes], 0.0)
        f = np.bincount(codes, weights=w * e_dm, minlength=nd)
        wide = np.zeros((nd, sym_codes.max() + 1))
        wide[codes, sym_codes] = w
        to = np.abs(np.diff(wide, axis=0)).sum(axis=1)
        out_f[col] = np.where(ok_day, f, np.nan)
        out_to[col] = np.concatenate([[np.nan], to])
    idx = pd.DatetimeIndex(dates)
    return pd.DataFrame(out_f, index=idx), pd.DataFrame(out_to, index=idx)


def stats(f: pd.Series, to: pd.Series | None) -> dict:
    f = f.dropna()
    n = len(f)
    if n < 5:
        return {"n": n}
    mu, sd = f.mean(), f.std()
    d = {
        "n": n,
        "ann_ret": float(mu * 252),
        "ann_vol": float(sd * math.sqrt(252)),
        "sharpe": float(mu / sd * math.sqrt(252)) if sd > 0 else None,
        "t": float(mu / (sd / math.sqrt(n))) if sd > 0 else None,
    }
    if to is not None:
        t = to.reindex(f.index).fillna(to.mean())
        net = f - COST_PER_SIDE * t
        d["turnover_ann"] = float(t.mean() * 252 / 2.0)  # x gross (gross = 2)
        d["net_sharpe"] = float(net.mean() / net.std() * math.sqrt(252)) if net.std() > 0 else None
        d["net_ann_ret"] = float(net.mean() * 252)
    return d


def factor_momentum(f: pd.DataFrame, slow: list[str]) -> dict:
    """Time-series and cross-sectional factor momentum over 21-session blocks of the slow set."""
    x = f[slow].loc[SIGNAL_START:SIGNAL_END]
    blk = np.arange(len(x)) // 21
    m = x.groupby(blk).sum(min_count=15)
    m.index = [x.index[blk == b][0] for b in m.index]
    out = {}
    for lb in (1, 6, 12):
        trail = m.rolling(lb, min_periods=lb).sum().shift(1)
        sign = np.sign(trail)
        ts = (sign * m).mean(axis=1, skipna=True).where(trail.notna().sum(axis=1) >= 10)
        rk = trail.rank(axis=1, pct=True)
        cs = m.where(rk > 0.5).mean(axis=1, skipna=True).where(trail.notna().sum(axis=1) >= 10)
        static = m.mean(axis=1, skipna=True).where(trail.notna().sum(axis=1) >= 10)
        for name, ser in (
            ("ts", ts),
            ("cs", cs),
            ("static", static),
            ("ts_minus_static", ts - static),
            ("cs_minus_static", cs - static),
        ):
            for win, (a, b) in (("stress", WINDOWS["stress"]), ("anchor", WINDOWS["anchor"])):
                s = ser.loc[a:b].dropna()
                if len(s) < 6:
                    continue
                sd = s.std()
                out[f"L{lb}_{name}_{win}"] = {
                    "months": len(s),
                    "mean_month": float(s.mean()),
                    "sharpe_ann": float(s.mean() / sd * math.sqrt(12)) if sd > 0 else None,
                    "t": float(s.mean() / (sd / math.sqrt(len(s)))) if sd > 0 else None,
                }
    return out


def run_signals() -> None:
    names, themes = signal_columns()
    phases = json.loads((WORK / "phases.json").read_text())
    st = pd.read_parquet(WORK / "market_state.parquet")
    open_, _ = load_etf()
    sessions = open_["SPY"].dropna().index
    spy_open = open_["SPY"]
    f_parts, to_parts = [], []
    sig_cols = ["trade_date", "symbol", "ind_code", "m0_composite", "m0_n_themes"]
    sig_cols += names + [f"{n}_cov" for n in names] + [f"theme_{t}" for t in themes]
    for year in range(2017, 2027):
        sig = pd.read_parquet(DATA / f"signals/{year}.parquet", columns=sig_cols)
        sig = sig[(sig["trade_date"] >= SIGNAL_START) & (sig["trade_date"] <= SIGNAL_END)]
        if sig.empty:
            continue
        ret = year_returns(year, sessions, spy_open)
        df = sig.merge(ret, on=["trade_date", "symbol"], how="inner")
        df = df[np.isfinite(df["e"])]
        del sig, ret
        f, to = ls_returns(df, names, themes)
        f_parts.append(f)
        to_parts.append(to)
        print(year, len(df), "rows", f.shape, flush=True)
        del df
    F = pd.concat(f_parts).sort_index()
    TO = pd.concat(to_parts).sort_index()
    F.to_parquet(WORK / "signal_ls_daily.parquet")
    TO.to_parquet(WORK / "signal_turnover_daily.parquet")

    styles = []
    for year in range(2017, 2027):
        fr = pd.read_parquet(DATA / f"risk/factor_returns_{year}.parquet")
        styles.append(fr.pivot(index="trade_date", columns="factor", values="ret"))
    S = pd.concat(styles).sort_index()
    style_names = [
        "size",
        "beta",
        "momentum",
        "resid_vol",
        "liquidity",
        "value",
        "profitability",
        "investment",
        "reversal",
    ]
    S = S[style_names]

    res: dict = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        "windows": {},
        "phases": {},
        "states": {},
        "style_phases": {},
    }
    cols = list(F.columns)
    for k, (a, b) in WINDOWS.items():
        res["windows"][k] = {c: stats(F[c].loc[a:b], TO[c]) for c in cols}
    all_phases = phases["phases_hist"] + phases["phases_recent"]
    for p in all_phases:
        res["phases"][p["id"]] = {c: stats(F[c].loc[p["start"] : p["end"]], TO[c]) for c in cols}
        res["style_phases"][p["id"]] = {
            c: stats(S[c].loc[p["start"] : p["end"]], None) for c in style_names
        }
    state = st["state"].reindex(F.index)
    for s in sorted(state.dropna().unique()):
        idx = state.index[state == s]
        res["states"][s] = {c: stats(F[c].loc[idx], TO[c]) for c in cols}
        res["states"][s]["_n_days"] = int(len(idx))
    res["style_windows"] = {
        k: {c: stats(S[c].loc[a:b], None) for c in style_names} for k, (a, b) in WINDOWS.items()
    }
    slow = [n for n in names if n in sum(themes.values(), [])]
    res["factor_momentum"] = factor_momentum(F, slow)
    corr_recent = (
        F[[f"theme_{t}" for t in themes]].loc[WINDOWS["anchor"][0] : WINDOWS["anchor"][1]].corr()
    )
    corr_stress = (
        F[[f"theme_{t}" for t in themes]].loc[WINDOWS["stress"][0] : WINDOWS["stress"][1]].corr()
    )
    res["theme_corr_anchor"] = corr_recent.round(3).to_dict()
    res["theme_corr_stress"] = corr_stress.round(3).to_dict()
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=float))
    print("wrote", OUT / "results.json")


# ---------------------------------------------------------------------------
# report stage
# ---------------------------------------------------------------------------
def min_track_record(
    sr_annual: float, sr_null: float = 0.0, skew: float = 0.0, kurt: float = 3.0, conf: float = 0.95
) -> float:
    """Bailey & Lopez de Prado (2012) minimum track record length, in daily observations."""
    from statistics import NormalDist

    z = NormalDist().inv_cdf(conf)
    sr, sr0 = sr_annual / math.sqrt(252), sr_null / math.sqrt(252)
    if sr <= sr0:
        return float("inf")
    return 1.0 + (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2) * (z / (sr - sr0)) ** 2


def power_table() -> list[dict]:
    rows = []
    for name, (a, b) in WINDOWS.items():
        n = len(pd.bdate_range(a, b))
        rows.append({"window": name, "sessions_approx": n, "sharpe_se_annual": math.sqrt(252 / n)})
    mtrl = {f"{s:.1f}": min_track_record(s) for s in (0.8, 1.0, 1.2, 1.5, 2.0)}
    return rows + [{"min_track_record_sessions_95pct_vs_0": mtrl}]


def _fmt(x: float | None, nd: int = 2) -> str:
    return "—" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{nd}f}"


def run_report() -> None:
    ph = json.loads((WORK / "phases.json").read_text())
    r = json.loads((OUT / "results.json").read_text())
    names, themes = signal_columns()
    theme_cols = [f"theme_{t}" for t in themes] + ["m0_composite"]
    slow = [n for n in names if n in sum(themes.values(), [])]
    fast_base = ["rev_21_ind", "on252", "news_attention"]
    alphas = [n for n in names if n.startswith(("a101_", "g191_"))]
    L: list[str] = []
    L.append("# 大盘阶段与各信号分阶段表现（2026-10-01）\n")
    L.append(
        f"生成：`scripts/analyze_equity_book_regimes.py`，市场阶段 {ph['generated_utc']} UTC，信号 {r['generated_utc']} UTC。数字全部来自同目录 `results.json` 和 `data/research/equity_book/regimes/phases.json`。\n"  # noqa: E501
    )
    L.append("## 1. 方法\n")
    L.append(
        f"- **阶段规则（先定规则、后算信号）**：SPY 收盘回撤 ≥{DD_THRESHOLD:.0%} 的高点、低点、收复新高日切段，加机主节点 {OWNER_NODE}；高点到低点记 correction，低点到收复记 rebound，其余记 advance；短于 {MIN_PHASE_SESSIONS} 个会话的段并入前一段。"  # noqa: E501
    )
    L.append(
        f"- **事前状态（每天收盘可知，可用于择时）**：趋势 = SPY 是否在 200 日均线上方；波动 = VIX 三分位，阈值只用 2016-01..{STATE_FIT_END} 拟合（低 ≤{ph['rule']['vix_low_max']:.2f}，中 ≤{ph['rule']['vix_mid_max']:.2f}）。"  # noqa: E501
    )
    L.append(
        "- **信号收益**：t 日收盘的处理后分数（S1 信号库，时点正确），t+1 开盘到 t+2 开盘持有；个股收益先减 252 日 SPY beta × SPY 收益，再在风险模型行业组内去均值；权重 = 覆盖股票内去均值的分数，多空各 1 美元。每日调仓，所以快信号的毛收益是上限；净值栏按单边 8 bp 扣成本，只是粗口径。"  # noqa: E501
    )
    L.append(
        "- **局限**：这些窗口项目以前都看过，只能用来设计，不能当样本外证据；当天没有收益的股票直接剔除（不计退市收益）；风格因子收益来自风险模型 v1 的日度截面回归。\n"  # noqa: E501
    )
    L.append("## 2. 大盘阶段\n")
    L.append(
        "| 段 | 起止 | 会话 | 类型 | SPY | IWM−SPY | 段内最大回撤 | 实现波动 | VIX 均/峰 | 200 日线上方占比 | 最强 / 最弱板块 |"  # noqa: E501
    )
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for p in ph["phases_hist"] + ph["phases_recent"]:
        L.append(
            f"| {p['id']} | {p['start']}..{p['end']} | {p['sessions']} | {p['label']} | {p['spy_return']:+.1%} | {p['iwm_minus_spy']:+.1%} | {p['max_dd_in_phase']:+.1%} | {p['realized_vol']:.0%} | {p['vix_mean']:.1f}/{p['vix_max']:.0f} | {_fmt(p['breadth_mean'])} | {p['best_sector']} / {p['worst_sector']} |"  # noqa: E501
        )
    ls_ = ph["latest_state"]
    L.append(
        f"\n最新状态（{ls_['date']}）：SPY 在 200 日线上方 {ls_['spy_vs_sma200']:+.1%}，距高点 {ls_['dd']:+.1%}，21 日实现波动 {ls_['rv21']:.0%}，VIX {ls_['vix']:.1f}，VIX/VXV {ls_['vix_vxv']:.2f}，状态 {ls_['state']}。"  # noqa: E501
    )
    L.append("\n各窗口的事前状态占比：\n")
    L.append(
        "| 窗口 | " + " | ".join(["up_low", "up_mid", "up_high", "down_mid", "down_high"]) + " |"
    )
    L.append("|---|---|---|---|---|---|")
    for k, v in ph["state_share"].items():
        L.append(
            f"| {k} | "
            + " | ".join(
                f"{v.get(s, 0):.2f}"
                for s in ["up_low", "up_mid", "up_high", "down_mid", "down_high"]
            )
            + " |"
        )

    def window_table(cols: list[str], title: str) -> None:
        L.append(f"\n### {title}\n")
        L.append(
            "| 信号 | 压力期 夏普 | 压力期 净夏普 | A 2024-01..2026-06 夏普 | A 净夏普 | A 年化 | A t | B 2026-07..09 夏普 | B 年化 | 年换手（×总额） |"  # noqa: E501
        )
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        W = r["windows"]
        for c in cols:
            s, a, b = W["stress"][c], W["owner_A_2024_01_2026_06"][c], W["owner_B_2026_07_now"][c]
            L.append(
                f"| {c} | {_fmt(s.get('sharpe'))} | {_fmt(s.get('net_sharpe'))} | {_fmt(a.get('sharpe'))} | {_fmt(a.get('net_sharpe'))} | {_fmt(a.get('ann_ret', float('nan')) * 100, 1)}% | {_fmt(a.get('t'))} | {_fmt(b.get('sharpe'))} | {_fmt(b.get('ann_ret', float('nan')) * 100, 1)}% | {_fmt(a.get('turnover_ann'), 0)} |"  # noqa: E501
            )

    L.append("\n## 3. 各信号在三个窗口的表现（行业内、beta 对冲、多空各 1 美元）")
    window_table(theme_cols, "3.1 主题和 M0 合成")
    window_table(slow, "3.2 慢信号")
    window_table(fast_base, "3.3 快信号（只进 ML）")
    best_alpha = sorted(
        alphas, key=lambda c: -(r["windows"]["owner_A_2024_01_2026_06"][c].get("net_sharpe") or -9)
    )[:8]
    window_table(
        best_alpha, "3.4 Alpha101/191：A 窗净夏普最高的 8 个（仅描述，按 A 窗排序本身就是挑选）"
    )

    def phase_matrix(cols: list[str], src: str, title: str, ids: list[str]) -> None:
        L.append(f"\n### {title}\n")
        L.append("| | " + " | ".join(ids) + " |")
        L.append("|---" * (len(ids) + 1) + "|")
        for c in cols:
            L.append(
                f"| {c} | " + " | ".join(_fmt(r[src][i][c].get("sharpe"), 1) for i in ids) + " |"
            )

    rec_ids = [p["id"] for p in ph["phases_recent"]]
    hist_ids = [p["id"] for p in ph["phases_hist"]]
    L.append("\n## 4. 分阶段年化夏普（毛）")
    L.append("段内会话少（10–150），单段夏普的标准误约 1.3–5，只看符号和跨段一致性。\n")
    phase_matrix(theme_cols, "phases", "4.1 主题 × 近期阶段", rec_ids)
    phase_matrix(theme_cols, "phases", "4.2 主题 × 历史阶段", hist_ids)
    styles = [
        "size",
        "beta",
        "momentum",
        "resid_vol",
        "liquidity",
        "value",
        "profitability",
        "investment",
        "reversal",
    ]
    phase_matrix(styles, "style_phases", "4.3 风险模型纯风格因子 × 近期阶段", rec_ids)
    L.append("\n## 5. 按事前状态（2017-10..2026-09 全部日子）\n")
    st_ids = [
        s for s in ["up_low", "up_mid", "up_high", "down_mid", "down_high"] if s in r["states"]
    ]
    L.append("| | " + " | ".join(f"{s}（{r['states'][s]['_n_days']} 天）" for s in st_ids) + " |")
    L.append("|---" * (len(st_ids) + 1) + "|")
    for c in theme_cols + [
        "mom_12_1",
        "resid_mom_12_1",
        "sue_eps",
        "cmp_opp_buy_60d",
        "neg_short_vol_ratio_21",
        "on252",
        "rev_21_ind",
    ]:
        L.append(
            f"| {c} | "
            + " | ".join(_fmt(r["states"][s][c].get("sharpe"), 2) for s in st_ids)
            + " |"
        )
    L.append("\n## 6. 择时检验：按近期表现加权（因子动量）\n")
    L.append(
        "22 个慢信号的 21 会话块收益。ts = 按过去 L 块累计收益的符号做多或做空该信号；cs = 只持有过去 L 块排名前一半的信号；static = 全部等权。差值行检验择时有没有增量。\n"  # noqa: E501
    )
    L.append("| 规则 | 窗口 | 月数 | 月均 | 年化夏普 | t |")
    L.append("|---|---|---|---|---|---|")
    for k, v in r["factor_momentum"].items():
        lb, rest = k.split("_", 1)
        rule, win = rest.rsplit("_", 1)
        L.append(
            f"| {lb} {rule} | {win} | {v['months']} | {v['mean_month'] * 100:.2f}% | {_fmt(v['sharpe_ann'])} | {_fmt(v['t'])} |"  # noqa: E501
        )
    L.append("\n## 7. 统计效力（代码计算）\n")
    L.append("| 窗口 | 约会话数 | 年化夏普的标准误 |")
    L.append("|---|---|---|")
    pw = power_table()
    for row in pw[:-1]:
        L.append(f"| {row['window']} | {row['sessions_approx']} | {row['sharpe_se_annual']:.2f} |")
    m = pw[-1]["min_track_record_sessions_95pct_vs_0"]
    L.append(
        "\n最短业绩长度（Bailey–López de Prado 2012，正态假设，95% 置信区分真实夏普与 0）："
        + "；".join(f"夏普 {k} 需 {v:.0f} 个会话（约 {v / 252:.1f} 年）" for k, v in m.items())
        + "。"
    )
    (OUT / "report_tables.md").write_text("\n".join(L) + "\n")
    r["power"] = pw
    (OUT / "results.json").write_text(json.dumps(r, indent=1, default=float))
    print("wrote", OUT / "report_tables.md")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["market", "signals", "report"], required=True)
    a = ap.parse_args()
    {"market": run_market, "signals": run_signals, "report": run_report}[a.stage]()


if __name__ == "__main__":
    main()
