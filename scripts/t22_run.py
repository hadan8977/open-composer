# ruff: noqa: E501
"""T-20261006-22 runner: rule cells through run_book (contract.md sections 3-8, 11).

flock /tmp/oc-heavy.lock ./scripts/run_capped.sh --mem 1.2G -- uv run python scripts/t22_run.py --stage A --universe 1000 --L 5 --H 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book.backtest import BookConfig, run_book  # noqa: E402
from open_composer.research.equity_book.costfn import make_cost_fn  # noqa: E402
from open_composer.research.equity_book.panel import HEDGE_ETFS, PricePanel  # noqa: E402

STORE = Path(os.environ.get("T22_STORE") or ROOT / "data/research/t22_streversal")
RES = Path(os.environ.get("T22_RESULTS") or STORE / "results")
EQUITY = 300_000.0
SIDE_GROSS = 0.5
NAMES_PER_SIDE = 100  # contract.md section 16 item 4
PRICE_LO, PRICE_HI = 5.0, 750.0
MIN_NAMES = 150  # fewer candidates than this: no book that day
BORROW_BP = 25.0
MIN_NOTIONAL = 100.0
SHORT_MAX_RANK: int | None = None  # borrow stress: shorts only in adv_rank <= this
VIX_LO, VIX_HI = 0.5, 1.8
NEWS_START = pd.Timestamp("2024-01-02")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Store:
    def __init__(self) -> None:
        meta = json.loads((STORE / "meta.json").read_text())
        self.dates = pd.DatetimeIndex(meta["dates"])
        self.symbols = pd.Index(meta["symbols"])
        self.shape = tuple(meta["shape"])
        self.meta = meta
        self._m: dict[str, np.ndarray] = {}
        self.vix = np.load(STORE / "vix.npy")
        self.spy = int(self.symbols.get_loc("SPY"))

    def m(self, name: str) -> np.ndarray:
        if name not in self._m:
            self._m[name] = np.load(STORE / f"{name}.npy", mmap_mode="r")
        return self._m[name]

    def pos(self, date: pd.Timestamp) -> int:
        return int(self.dates.get_loc(pd.Timestamp(date)))


def vix_scale(vix: np.ndarray, t: int) -> float:
    if t < 252 or not np.isfinite(vix[t]):
        return 1.0
    med = np.nanmedian(vix[t - 251 : t + 1])
    return float(np.clip(vix[t] / med, VIX_LO, VIX_HI)) if np.isfinite(med) and med > 0 else 1.0


SCORE_OVERRIDE: np.ndarray | None = None  # (T, N) model scores; replaces the rule signal when set


def signal_row(store: Store, resid: str, L: int, t: int) -> np.ndarray:
    """S_L,i,t = -sum of the last L daily residuals (contract section 3); NaN if too few days."""
    if SCORE_OVERRIDE is not None:
        return np.asarray(SCORE_OVERRIDE[t], dtype="float64")
    e = store.m(f"e_{resid}")
    if t - L + 1 < 1:
        return np.full(store.shape[1], np.nan)
    w = np.asarray(e[t - L + 1 : t + 1], dtype="float64")
    cnt = np.isfinite(w).sum(axis=0)
    need = L if L <= 5 else int(np.ceil(0.8 * L))
    s = np.nansum(w, axis=0) * np.where(cnt > 0, L / np.maximum(cnt, 1), np.nan)
    return np.where(cnt >= need, -s, np.nan)


def candidates(store: Store, t: int, u: int, cond: str, score: np.ndarray) -> np.ndarray:
    px = np.asarray(store.m("close")[t])
    ok = (
        (np.asarray(store.m("adv_rank")[t]) <= u)
        & (np.asarray(store.m("is_tradeable")[t]) > 0)
        & np.isfinite(score)
        & (px >= PRICE_LO)
        & (px <= PRICE_HI)
    )
    if cond == "lowturn":
        to = np.asarray(store.m("turnover")[t], dtype="float64")
        ok &= np.isfinite(to)
        if ok.sum() >= 2:
            ok &= to <= np.median(to[ok])
    elif cond == "nonews":
        if store.dates[t] < NEWS_START:
            return np.zeros_like(ok)
        ok &= np.asarray(store.m("news_row")[t]) & (np.asarray(store.m("news_1d")[t]) == 0)
    return ok


def pick(
    idx: np.ndarray, score: np.ndarray, long: bool, gross: float
) -> tuple[np.ndarray, np.ndarray]:
    """The NAMES_PER_SIDE most extreme names (highest S for longs, lowest for shorts), equal weight."""
    k = min(NAMES_PER_SIDE, len(idx))
    order = np.argsort(-score[idx] if long else score[idx], kind="stable")[:k]
    sel = idx[order]
    return sel, np.full(k, gross / NAMES_PER_SIDE)


def placebo_score(
    store: Store, t: int, ok: np.ndarray, score: np.ndarray, placebo: tuple[str, int]
) -> np.ndarray:
    """Standard section 3 placebos: ``gross`` shuffles the score across the candidates every day;
    ``net`` gives every symbol a random rank that is fixed within a calendar quarter (seeded) and
    assigns the sorted true scores to the candidates in that rank order."""
    mode, seed = placebo
    out = score.copy()
    idx = np.flatnonzero(ok)
    if mode == "gross":
        rng = np.random.default_rng(seed * 100003 + t)
        out[idx] = score[idx][rng.permutation(len(idx))]
    else:
        d = store.dates[t]
        q = d.year * 4 + (d.month - 1) // 3
        u = np.random.default_rng(seed * 1009 + q).random(store.shape[1])
        ranks = np.argsort(np.argsort(u[idx], kind="stable"), kind="stable")
        out[idx] = np.sort(score[idx])[ranks]
    return out


def single_day_book(
    store: Store,
    t: int,
    u: int,
    resid: str,
    L: int,
    cond: str,
    placebo: tuple[str, int] | None = None,
) -> tuple[np.ndarray, np.ndarray, float] | None:
    """(master idx, signed weights incl. no hedge, hedge weight for SPY) of the single-day book at close t."""
    score = signal_row(store, resid, L, t)
    ok = candidates(store, t, u, cond, score)
    if ok.sum() < MIN_NAMES:
        return None
    if placebo is not None:
        score = placebo_score(store, t, ok, score, placebo)
    s_t = vix_scale(store.vix, t) if cond == "vixscale" else 1.0
    g = SIDE_GROSS * s_t
    idx_long = np.flatnonzero(ok)
    sh = ok & np.asarray(store.m("short_elig")[t])
    if SHORT_MAX_RANK is not None:
        sh &= np.asarray(store.m("adv_rank")[t]) <= SHORT_MAX_RANK
    idx_short = np.flatnonzero(sh)
    if len(idx_short) < NAMES_PER_SIDE:
        return None
    li, lw = pick(idx_long, score, True, g)
    si, sw = pick(idx_short, score, False, g)
    idx = np.concatenate([li, si])
    w = np.concatenate([lw, -sw])
    beta = np.asarray(store.m("beta_252_spy")[t][idx], dtype="float64")
    beta = np.clip(np.where(np.isfinite(beta), beta, 1.0), -0.5, 3.0)
    hedge = -float((w * beta).sum())
    return idx, w, hedge


def combine(
    books: list[tuple[np.ndarray, np.ndarray, float] | None], H: int, store: Store
) -> dict[str, float] | None:
    """Target book = mean of the last H single-day books (contract section 6)."""
    live = [b for b in books if b is not None]
    if not live or books[-1] is None:
        return None
    acc: dict[int, float] = {}
    hedge = 0.0
    for idx, w, h in live:
        for j, x in zip(idx.tolist(), w.tolist(), strict=True):
            acc[j] = acc.get(j, 0.0) + x / H
        hedge += h / H
    out = {str(store.symbols[j]): x for j, x in acc.items()}
    out["SPY"] = out.get("SPY", 0.0) + hedge
    out = {s: x for s, x in out.items() if abs(x) * EQUITY >= MIN_NOTIONAL or s == "SPY"}
    out["TBILL"] = 1.0
    return out


class CostProbe:
    """Wraps costfn: records traded dollars and the share above 1% of dollar_adv_21."""

    def __init__(self, inner):
        self.inner = inner
        self.notional = 0.0
        self.big = 0.0
        self.parts: list[float] = []

    def __call__(self, trades: pd.DataFrame, state=None):
        d = trades["dollar_trade"].abs().to_numpy("float64")
        adv = (
            trades["dollar_adv_21"].to_numpy("float64")
            if "dollar_adv_21" in trades
            else np.full(len(d), np.nan)
        )
        with np.errstate(invalid="ignore", divide="ignore"):
            part = d / adv
        stock = ~trades["symbol"].isin(HEDGE_ETFS).to_numpy()
        self.notional += float(d[stock].sum())
        self.big += float(d[stock & (part > 0.01)].sum())
        self.parts.extend(part[stock & np.isfinite(part)].tolist()[:2000])
        return self.inner(trades, state)


def make_attrs(store: Store, panel: PricePanel):
    sym_pos = {s: j for j, s in enumerate(store.symbols)}
    adv = store.m("dollar_adv_21")
    vol = store.m("vol_21")
    rank = store.m("adv_rank")

    def hook(decision_date: pd.Timestamp, symbols) -> pd.DataFrame:
        t = store.pos(decision_date)
        pi = panel.dates.get_loc(pd.Timestamp(decision_date))
        j = np.array([sym_pos.get(s, -1) for s in symbols])
        ok = j >= 0
        out = pd.DataFrame(
            index=list(symbols),
            columns=["dollar_adv_21", "vol_21", "adv_rank", "prior_close"],
            dtype="float64",
        )
        out.loc[ok, "dollar_adv_21"] = np.asarray(adv[t])[j[ok]]
        out.loc[ok, "vol_21"] = np.asarray(vol[t])[j[ok]]
        out.loc[ok, "adv_rank"] = np.asarray(rank[t])[j[ok]]
        cols = np.array([panel.col(s) if panel.has(s) else -1 for s in symbols])
        okc = cols >= 0
        out.loc[okc, "prior_close"] = panel.close[pi, cols[okc]]
        return out

    return hook


def load_panel(store: Store, start: str, end: str | None = None) -> PricePanel:
    keep = [
        s for s in store.symbols if s in set(store.symbols)
    ]  # master set (adv_rank <= 4000 ever) + ETFs
    ever3000 = np.flatnonzero(
        np.nanmin(
            np.where(
                np.isfinite(np.asarray(store.m("adv_rank"))), np.asarray(store.m("adv_rank")), 1e9
            ),
            axis=0,
        )
        <= 3000
    )
    names = [str(store.symbols[j]) for j in ever3000]
    del keep
    return PricePanel.from_dir(symbols=names, start=start, end=end, load_open=True)


def run_cell(
    store: Store,
    panel: PricePanel,
    target_fn,
    exec_: str,
    start: str,
    end: str,
    snapshots: bool = False,
    borrow_bp: float = BORROW_BP,
):
    """``target_fn(pos) -> dict | None``: target weights decided at the close of session ``pos``."""
    sig_dates = [d for d in panel.dates if pd.Timestamp(start) <= d <= pd.Timestamp(end)]
    probe = CostProbe(make_cost_fn(exec_))
    cfg = BookConfig(
        freq="D",
        exec_price=exec_,
        cost_fn=probe,
        borrow_bp_per_year=borrow_bp,
        start=start,
        end=end,
        initial_equity=EQUITY,
        trade_attrs=make_attrs(store, panel),
        snapshots=snapshots,
        signal_dates=sig_dates,
    )

    def decide(t: pd.Timestamp, state):
        return target_fn(store.pos(t))

    res = run_book(panel, decide, cfg)
    return res, probe


def overlap_target(books_by_pos: dict[int, tuple | None], H: int, store: Store):
    return lambda p: combine([books_by_pos.get(p - k) for k in range(H - 1, -1, -1)], H, store)


def offset_target(books_by_pos: dict[int, tuple | None], k: int, period: int, store: Store):
    """Weekly-style sub-book: hold the single-day book of the latest signal day s <= p with
    (s - k) % period == 0 at full weight (contract.md section 11, robustness d)."""
    return lambda p: combine([books_by_pos.get(p - ((p - k) % period))], 1, store)


def build_books(
    store: Store,
    panel: PricePanel,
    start: str,
    end: str,
    u: int,
    resid: str,
    L: int,
    cond: str,
    H_max: int = 10,
    placebo: tuple[str, int] | None = None,
) -> dict[int, tuple | None]:
    a = store.pos(panel.dates[panel.dates.searchsorted(pd.Timestamp(start))]) - (H_max - 1)
    b = store.pos(panel.dates[panel.dates.searchsorted(pd.Timestamp(end), "right") - 1])
    return {t: single_day_book(store, t, u, resid, L, cond, placebo) for t in range(a, b + 1)}


def summarize(
    res, rf: pd.Series, spy: pd.Series, probe: CostProbe, window: tuple[str, str]
) -> dict:
    from open_composer.research.equity_book.evaluate import window_metrics

    d = res.daily
    out = {"net_1x": window_metrics(res.net, rf, spy, window, d)}
    cost_cols = ["cost_spread", "cost_impact", "cost_fees", "cost_borrow", "cost_margin"]
    sub = d.loc[window[0] : window[1]]
    tot_cost = sub[cost_cols].sum(axis=1)
    for k in (0.5, 2.0):
        net_k = sub["gross"] - k * tot_cost
        out[f"net_{k}x"] = window_metrics(net_k, rf, spy, window)
    g = sub["gross"] - 0.0  # gross includes costs added back
    ex = g - rf.reindex(sub.index).fillna(0.0)
    sd = float(ex.std(ddof=1))
    out["gross"] = {
        "sharpe": float(ex.mean() / sd * np.sqrt(252)) if sd > 0 else float("nan"),
        "ann_return": float(ex.mean() * 252),
    }
    out["costs_ann"] = {c: float(sub[c].sum() / len(sub) * 252) for c in cost_cols}
    out["capacity"] = {
        "traded_notional": probe.notional,
        "share_above_1pct_adv": probe.big / probe.notional if probe.notional else float("nan"),
        "median_participation": float(np.median(probe.parts)) if probe.parts else float("nan"),
    }
    out["exposure"] = {
        "avg_long": float(sub["long_exp"].mean()),
        "avg_short": float(sub["short_exp"].mean()),
        "avg_n_long": float(sub["n_long"].mean()),
        "avg_n_short": float(sub["n_short"].mean()),
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="A")
    ap.add_argument("--universe", type=int, nargs="+", default=[1000])
    ap.add_argument("--resid", nargs="+", default=["beta", "ind", "pca"])
    ap.add_argument("--L", type=int, nargs="+", default=[5])
    ap.add_argument("--cond", nargs="+", default=["none"])
    ap.add_argument("--H", type=int, nargs="+", default=[5])
    ap.add_argument("--exec", nargs="+", default=["open", "close"])
    ap.add_argument("--start", default="2024-01-05")
    ap.add_argument("--end", default="2026-09-15")
    ap.add_argument("--tag", default="A")
    ap.add_argument("--limit-days", type=int, default=0)
    a = ap.parse_args()
    from open_composer.research.equity_book.evaluate import load_rf_spy

    store = Store()
    pstart = (pd.Timestamp(a.start) - pd.Timedelta(days=40)).strftime("%Y-%m-%d")
    panel = load_panel(store, pstart, a.end)
    log(f"panel {panel.close.shape}")
    rf, spy = load_rf_spy()
    RES.mkdir(parents=True, exist_ok=True)
    window = ("2024-01-08", a.end) if a.start >= "2024-01-01" else (a.start, a.end)
    for u in a.universe:
        for resid in a.resid:
            for L in a.L:
                for cond in a.cond:
                    t0 = time.time()
                    books = build_books(store, panel, a.start, a.end, u, resid, L, cond, max(a.H))
                    log(
                        f"books U{u} {resid} L{L} {cond}: {time.time() - t0:.1f}s ({sum(b is not None for b in books.values())}/{len(books)} days)"
                    )
                    for H in a.H:
                        for ex in a.exec:
                            cell = f"R_U{u}_{resid}_L{L}_{cond}_H{H}_{ex}"
                            out_file = RES / a.tag / f"{cell}.json"
                            if out_file.exists():
                                continue
                            t1 = time.time()
                            res, probe = run_cell(
                                store, panel, overlap_target(books, H, store), ex, a.start, a.end
                            )
                            summ = summarize(res, rf, spy, probe, window)
                            summ.update(
                                {
                                    "cell_id": cell,
                                    "universe": u,
                                    "resid": resid,
                                    "L": L,
                                    "cond": cond,
                                    "H": H,
                                    "exec": ex,
                                    "info": {k: v for k, v in res.info.items()},
                                }
                            )
                            out_file.parent.mkdir(parents=True, exist_ok=True)
                            out_file.write_text(json.dumps(summ))
                            res.daily.to_parquet(RES / a.tag / f"{cell}.parquet")
                            m = summ["net_1x"]
                            log(
                                f"{cell}: net {m.get('sharpe', float('nan')):.2f} gross {summ['gross']['sharpe']:.2f} cost/gross {m.get('cost_share', float('nan')):.2f} turn {m.get('turnover', float('nan')):.1f} ({time.time() - t1:.0f}s)"
                            )


if __name__ == "__main__":
    main()
