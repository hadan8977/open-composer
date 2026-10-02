# ruff: noqa: E501
"""Realism ladder for the total-return M0/M1 long-short (T-20261002-25, preregistered).

Preregistration: ``reports/research/program/realism-ladder-2026-10-02/prereg.md`` (committed before
any R1a-R6 number).  Stages:

``r0``      the identity rung: the regime-analysis M0 long-short rebuilt with the functions of
            ``scripts/analyze_equity_book_regimes.py`` and compared with its ``results.json``.
``ladder``  R1a, R1 .. R6 for the four variants (composite {M0, M1} x universe {U3000, P1000}),
            five weekly offsets; writes the daily series and ``ladder_raw.json``.
``checks``  identity checks of the vectorised pieces against the book's own classes
            (``op.ShortEligibility``, ``RiskModel.predicted_beta``, ``make_cost_fn``).
``report``  windows metrics, scorecard v2 items for R4-R6, decision rule, ``results.json``.

    scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/realism_ladder_book_ls.py --stage ladder
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import analyze_equity_book_regimes as reg  # noqa: E402

OUT = ROOT / "reports/research/program/realism-ladder-2026-10-02"
REG_RESULTS = ROOT / "reports/research/program/regimes-2026-10-01/results.json"
R0_WINDOWS = ("stress", "anchor", "owner_A_2024_01_2026_06", "owner_B_2026_07_now")
R0_TOL = 1e-9


def r0_series() -> tuple[pd.Series, pd.Series]:
    """Daily M0 long-short return and turnover exactly as ``run_signals`` builds them (the signal
    list is empty: only the ``m0_composite`` column is evaluated)."""
    open_, _ = reg.load_etf()
    sessions = open_["SPY"].dropna().index
    spy_open = open_["SPY"]
    f_parts, to_parts = [], []
    cols = ["trade_date", "symbol", "ind_code", "m0_composite", "m0_n_themes"]
    for year in range(2017, 2027):
        sig = pd.read_parquet(reg.DATA / f"signals/{year}.parquet", columns=cols)
        sig = sig[(sig["trade_date"] >= reg.SIGNAL_START) & (sig["trade_date"] <= reg.SIGNAL_END)]
        if sig.empty:
            continue
        ret = reg.year_returns(year, sessions, spy_open)
        df = sig.merge(ret, on=["trade_date", "symbol"], how="inner")
        df = df[np.isfinite(df["e"])]
        del sig, ret
        f, to = reg.ls_returns(df, [], {})
        f_parts.append(f)
        to_parts.append(to)
        print(year, len(df), "rows", flush=True)
        del df
    f = pd.concat(f_parts).sort_index()["m0_composite"]
    to = pd.concat(to_parts).sort_index()["m0_composite"]
    return f, to


def r0_identity() -> dict:
    f, to = r0_series()
    stored = json.loads(REG_RESULTS.read_text())["windows"]
    out: dict = {"tolerance": R0_TOL, "windows": {}, "max_abs_diff": 0.0, "pass": True}
    for k in R0_WINDOWS:
        a, b = reg.WINDOWS[k]
        mine = reg.stats(f.loc[a:b], to)
        ref = stored[k]["m0_composite"]
        diffs = {}
        for key, v in ref.items():
            m = mine.get(key)
            diffs[key] = None if m is None else abs(float(m) - float(v))
        worst = max((d for d in diffs.values() if d is not None), default=float("nan"))
        missing = [key for key, d in diffs.items() if d is None]
        ok = bool(math.isfinite(worst) and worst <= R0_TOL and not missing)
        out["windows"][k] = {
            "mine": mine,
            "stored": ref,
            "abs_diff": diffs,
            "worst": worst,
            "missing_keys": missing,
            "pass": ok,
        }
        out["max_abs_diff"] = max(out["max_abs_diff"], worst if math.isfinite(worst) else 1e99)
        out["pass"] = out["pass"] and ok
    return out


# ---------------------------------------------------------------------------
# constants (fixed by the preregistration)
# ---------------------------------------------------------------------------
EQUITY = 1_000_000.0
FLAT_COST_PER_SIDE = 0.0008
BORROW_BP_YEAR = 25.0
VIX_THRESHOLD = 20.60
VIX_FFILL = 3
START = "2017-10-02"
VARIANTS = ("M0_U3000", "M0_P1000", "M1_U3000", "M1_P1000")
OFFSETS = (0, 1, 2, 3, 4)
WEEK = 5
RUNGS = ("R1", "R2", "R3", "R4", "R5", "R6")
WINDOWS = {
    "A": ("2024-01-08", "2026-06-30"),
    "B": ("2026-07-01", "2026-12-31"),
    "stress": ("2017-10-02", "2023-08-31"),
    "recent": ("2024-01-08", "2026-12-31"),
}
EB = ROOT / "data/research/equity_book"
RAW = EB / "realism_ladder"


# ---------------------------------------------------------------------------
# pure rules (unit tested)
# ---------------------------------------------------------------------------
def target_weights(score: pd.Series, ind: pd.Series) -> pd.Series:
    """Industry-demeaned score scaled to long 1 / short 1 (``w = 2 s_dm / sum|s_dm|``)."""
    s = score.dropna()
    if s.empty:
        return s.astype(float)
    g = ind.reindex(s.index).fillna(-1)
    dm = s - s.groupby(g.to_numpy()).transform("mean")
    gross = float(dm.abs().sum())
    if not gross > 0:
        return dm * 0.0
    return 2.0 * dm / gross


def restrict_shorts(w: pd.Series, eligible: pd.Series) -> pd.Series:
    """Short names outside the easy-to-borrow set get weight 0; the short leg is rescaled to -1."""
    ok = eligible.reindex(w.index).fillna(False).astype(bool)
    out = w.where((w >= 0) | ok, 0.0)
    neg = out < 0
    s = -float(out[neg].sum())
    if s > 0:
        out[neg] = out[neg] / s
    return out


def hedge_size(w: np.ndarray, beta: np.ndarray) -> float:
    """SPY position (fraction of equity) that offsets the weighted beta: ``-sum w_i beta_i``."""
    return float(-np.nansum(w * beta))


def vix_scale(vix: float, threshold: float = VIX_THRESHOLD) -> float:
    """1 normally, 0.5 when the VIX at the decision date is above the threshold (NaN: 1)."""
    return 0.5 if (np.isfinite(vix) and vix > threshold) else 1.0


def decision_positions(
    n_dates: int, first_pos: int, last_pos: int, period: int, offset: int
) -> list[int]:
    """Calendar positions of the decision dates: ``pos % period == offset``, from ``first_pos``."""
    return [p for p in range(first_pos, last_pos + 1) if p % period == offset]


def hold_block(
    w0: np.ndarray,
    r: np.ndarray,
    spy_r: np.ndarray,
    *,
    beta: np.ndarray | None = None,
    h0: float = 0.0,
) -> dict[str, np.ndarray | float]:
    """Hold fixed *shares* for ``len(r)`` labels.

    ``w0``: weights (fraction of equity) at the start; ``r``: (L, N) stock returns (NaN = 0);
    ``spy_r``: (L,) SPY returns on the same fill basis.  Positions drift: label j earns
    ``w0 * G_j * r_j`` with ``G_j`` the cumulative growth before day j.  ``beta`` (per stock)
    adds the R0-style hedge ``-w0 G_j beta r_spy_j`` (hedge notional follows the drifted stock);
    ``h0`` is a SPY position held in fixed shares.  Also returns the drifted weights and SPY
    position after the block, and the drifted short notional of every label."""
    r = np.where(np.isfinite(r), r, 0.0)
    g_after = np.cumprod(1.0 + r, axis=0)
    g_before = np.vstack([np.ones((1, r.shape[1])), g_after[:-1]])
    pos = w0[None, :] * g_before
    pnl = (pos * r).sum(axis=1)
    if beta is not None:
        pnl = pnl - (pos * beta[None, :]).sum(axis=1) * spy_r
    s_after = np.cumprod(1.0 + spy_r)
    s_before = np.concatenate([[1.0], s_after[:-1]])
    pnl_hedge = h0 * s_before * spy_r
    short = -(np.where(pos < 0, pos, 0.0)).sum(axis=1)
    return {
        "pnl": pnl + pnl_hedge,
        "stock_pnl": pnl,
        "hedge_pnl": pnl_hedge,
        "w_end": w0 * g_after[-1],
        "h_end": float(h0 * s_after[-1]),
        "short_notional": short,
    }


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
class YearStore:
    """Lazy per-year reader of ``<base>/<stem>_<year>.parquet`` (or ``<year>.parquet``)."""

    def __init__(self, path_fmt: str, columns: list[str]) -> None:
        self.path_fmt, self.columns = path_fmt, columns
        self._year: int | None = None
        self._df: pd.DataFrame | None = None
        self._dates: np.ndarray | None = None

    def at(self, t: pd.Timestamp) -> pd.DataFrame:
        if self._year != t.year:
            df = pd.read_parquet(self.path_fmt.format(year=t.year), columns=self.columns)
            self._df = df.sort_values(["trade_date", "symbol"], kind="stable").reset_index(
                drop=True
            )
            self._dates = self._df["trade_date"].to_numpy()
            self._year = t.year
        assert self._df is not None and self._dates is not None
        d = np.datetime64(t.to_datetime64())
        lo, hi = np.searchsorted(self._dates, d, "left"), np.searchsorted(self._dates, d, "right")
        return self._df.iloc[lo:hi].set_index("symbol")


class EwmaBeta:
    """``beta_ewma`` of the latest saved risk-model date <= t (saved weekly), as
    ``RiskModel.predicted_beta(t, "ewma")``; falls back to the previous year before the first
    saved date of a year."""

    def __init__(self, base: Path = EB / "risk") -> None:
        self.base = base
        self._cache: dict[int, pd.DataFrame] = {}

    def _year(self, y: int) -> pd.DataFrame:
        if y not in self._cache:
            if len(self._cache) > 1:
                self._cache.pop(min(self._cache))
            f = self.base / f"exposures_{y}.parquet"
            self._cache[y] = (
                pd.read_parquet(f, columns=["trade_date", "symbol", "beta_ewma"])
                if f.exists()
                else pd.DataFrame(columns=["trade_date", "symbol", "beta_ewma"])
            )
        return self._cache[y]

    def at(self, t: pd.Timestamp) -> tuple[pd.Series, pd.Timestamp]:
        for y in (t.year, t.year - 1):
            df = self._year(y)
            ok = df[df["trade_date"] <= t]
            if len(ok):
                d = ok["trade_date"].max()
                return df[df["trade_date"] == d].set_index("symbol")["beta_ewma"], d
        raise KeyError(f"no saved risk model on or before {t.date()}")


class Prices:
    """Wide open/close matrices of the symbols that were ever a decision-universe member, over the
    ``panel/_calendar.parquet`` session calendar, plus SPY, reverse-split flags and VIX."""

    def __init__(self) -> None:
        cal = pd.read_parquet(EB / "panel/_calendar.parquet")
        self.dates = pd.DatetimeIndex(cal["trade_date"])
        self.T = len(self.dates)
        syms: set[str] = set()
        for f in sorted((EB / "alpha/book_v1").glob("themes_*.parquet")):
            syms |= set(pd.read_parquet(f, columns=["symbol"])["symbol"])
        self.symbols = pd.Index(sorted(syms))
        self.N = len(self.symbols)
        self.O = np.full((self.T, self.N), np.nan)
        self.C = np.full((self.T, self.N), np.nan)
        self.off_calendar_rows = 0
        for f in sorted((EB / "prices").glob("*.parquet")):
            df = pd.read_parquet(f, columns=["trade_date", "symbol", "open", "close"])
            df = df.drop_duplicates(["trade_date", "symbol"], keep="last")
            r = self.dates.get_indexer(pd.DatetimeIndex(df["trade_date"]))
            k = self.symbols.get_indexer(df["symbol"])
            self.off_calendar_rows += int((r < 0).sum())
            ok = (r >= 0) & (k >= 0)
            self.O[r[ok], k[ok]] = df["open"].to_numpy("float64")[ok]
            self.C[r[ok], k[ok]] = df["close"].to_numpy("float64")[ok]
            del df
        etf = pd.read_parquet(
            EB / "etf_daily.parquet", columns=["trade_date", "symbol", "open", "close"]
        )
        etf = etf[etf["symbol"] == "SPY"].set_index("trade_date").sort_index()
        self.spy_o = etf["open"].reindex(self.dates).to_numpy("float64")
        self.spy_c = etf["close"].reindex(self.dates).to_numpy("float64")
        self._rs_cum: np.ndarray | None = None
        vix = reg.load_vix()["VIXCLS"].reindex(self.dates).ffill(limit=VIX_FFILL)
        self.vix = vix.to_numpy("float64")

    def pos(self, t: pd.Timestamp) -> int:
        return int(self.dates.get_loc(t))

    def rs_recent(self, pos: int) -> np.ndarray:
        """Reverse split in the past ``RS_WINDOW`` sessions incl. ``pos`` (as ShortEligibility)."""
        from open_composer.research.equity_book.borrow import RS_WINDOW, detect_reverse_splits

        if self._rs_cum is None:
            flags = detect_reverse_splits(
                pd.DataFrame(self.O, copy=False), pd.DataFrame(self.C, copy=False)
            )
            self._rs_cum = np.cumsum(flags.to_numpy(dtype=bool), axis=0, dtype=np.int32)
        lo = max(pos - RS_WINDOW + 1, 0)
        base = self._rs_cum[lo - 1] if lo > 0 else 0
        return (self._rs_cum[pos] - base) > 0

    def fill(self, kind: str) -> tuple[np.ndarray, np.ndarray]:
        return (self.O, self.spy_o) if kind == "open" else (self.C, self.spy_c)

    def returns(self, kind: str, p: int, length: int) -> tuple[np.ndarray, np.ndarray]:
        """Labels p .. p+length-1: F(t+2)/F(t+1) - 1 for stocks (NaN allowed) and SPY."""
        f, s = self.fill(kind)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = f[p + 2 : p + 2 + length] / f[p + 1 : p + 1 + length] - 1.0
            rs = s[p + 2 : p + 2 + length] / s[p + 1 : p + 1 + length] - 1.0
        return r, rs


# ---------------------------------------------------------------------------
# the ladder pass
# ---------------------------------------------------------------------------
RUNG_SPEC = {
    "R1": dict(fill="open", ws="full", hedge="beta252", cost="flat", borrow=False, vix=False),
    "R2": dict(fill="close", ws="full", hedge="beta252", cost="flat", borrow=False, vix=False),
    "R3": dict(fill="close", ws="etb", hedge="beta252", cost="flat", borrow=False, vix=False),
    "R4": dict(fill="close", ws="etb", hedge="beta252", cost="real", borrow=True, vix=False),
    "R5": dict(fill="close", ws="etb", hedge="spy_ewma", cost="real", borrow=True, vix=False),
    "R6": dict(fill="close", ws="etb", hedge="spy_ewma", cost="real", borrow=True, vix=True),
}


class Context:
    def __init__(self) -> None:
        from open_composer.research.equity_book.costfn import make_cost_fn
        from scripts.run_book_v1_stage2 import FormationIC, ThemeStore

        self.px = Prices()
        self.themes = ThemeStore()
        fic = pd.read_parquet(EB / "alpha/book_v1/formation_ic.parquet")
        self.fic = FormationIC(fic, self.px.dates)
        self.panel = YearStore(
            str(EB / "panel/{year}.parquet"),
            [
                "trade_date",
                "symbol",
                "close",
                "dollar_adv_21",
                "adv_rank",
                "vol_21",
                "beta_252_spy",
            ],
        )
        self.sig = YearStore(
            str(EB / "signals/{year}.parquet"), ["trade_date", "symbol", "ind_code"]
        )
        self.ewma = EwmaBeta()
        self.cost_fn = make_cost_fn("close")


def real_cost(
    ctx: Context,
    t: pd.Timestamp,
    names: pd.Index,
    d_w: np.ndarray,
    d_h: float,
    attrs: pd.DataFrame,
) -> float:
    """Trade cost (spread + impact + fees) as a fraction of equity from the book's cost function."""
    nz = np.flatnonzero(np.abs(d_w) > 1e-12)
    sym = list(names[nz])
    amt = list(d_w[nz] * EQUITY)
    if abs(d_h) > 1e-12:
        sym.append("SPY")
        amt.append(d_h * EQUITY)
    if not sym:
        return 0.0
    a = attrs.reindex(sym)
    trades = pd.DataFrame(
        {
            "symbol": sym,
            "dollar_trade": amt,
            "price": a["close"].to_numpy(),
            "prior_close": a["close"].to_numpy(),
            "dollar_adv_21": a["dollar_adv_21"].to_numpy(),
            "vol_21": a["vol_21"].to_numpy(),
            "trade_date": t,
        }
    )
    c = ctx.cost_fn(trades, None)
    return float(c["spread"] + c["impact"] + c["fees"]) / EQUITY


def run_pass(
    ctx: Context,
    variant: str,
    period: int,
    offset: int,
    rungs: tuple[str, ...],
    limit: int | None = None,
) -> dict[str, pd.DataFrame]:
    """One (variant, offset) pass over the weekly (or daily) rebalances for the listed rungs."""
    from open_composer.research.equity_book.borrow import short_eligible
    from scripts.run_book_v1_stage2 import AlphaSource

    method, universe = variant.split("_")
    uni = universe.lower()
    flag = "in_u3000" if uni == "u3000" else "in_p1000"
    px = ctx.px
    src = AlphaSource(ctx.themes, ctx.fic, method, uni)
    first = int(px.dates.searchsorted(pd.Timestamp(START)))
    last_label = px.T - 3
    dec = decision_positions(px.T, first, last_label, period, offset)
    state = {r: dict(w=np.zeros(px.N), h=0.0) for r in rungs}
    rows: dict[str, list[pd.DataFrame]] = {r: [] for r in rungs}
    n_vix_nan = 0
    for i, p in enumerate(dec):
        if limit is not None and i >= limit:
            break
        t = px.dates[p]
        nxt = dec[i + 1] if i + 1 < len(dec) else last_label + 1
        length = nxt - p
        th = ctx.themes.at(t)
        if th.empty:
            continue
        members = th.index[th[flag].to_numpy(bool)]
        state_obj = type("S", (), {"pos": p})()
        score = src(t, state_obj, members)
        ind = ctx.sig.at(t)["ind_code"]
        w_full_s = target_weights(score, ind)
        idx = px.symbols.get_indexer(w_full_s.index)
        keep = idx >= 0
        w_full = np.zeros(px.N)
        w_full[idx[keep]] = w_full_s.to_numpy()[keep]
        attrs = ctx.panel.at(t)
        a = attrs.reindex(w_full_s.index)
        se = short_eligible(
            pd.DataFrame(
                {
                    "adv_rank": a["adv_rank"],
                    "price": a["close"],
                    "reverse_split_252": px.rs_recent(p)[idx.clip(min=0)] & (idx >= 0),
                },
                index=w_full_s.index,
            )
        )
        w_etb_s = restrict_shorts(w_full_s, se)
        w_etb = np.zeros(px.N)
        w_etb[idx[keep]] = w_etb_s.to_numpy()[keep]
        b252 = np.ones(px.N)
        bb = a["beta_252_spy"].fillna(1.0).clip(-0.5, 3.0)
        b252[idx[keep]] = bb.to_numpy()[keep]
        need_ewma = any(RUNG_SPEC[r]["hedge"] == "spy_ewma" for r in rungs)
        b_ewma = np.ones(px.N)
        if need_ewma:
            be, _ = ctx.ewma.at(t)
            ev = be.reindex(w_full_s.index).fillna(1.0).clip(-1.0, 4.0)
            b_ewma[idx[keep]] = ev.to_numpy()[keep]
        vscale = vix_scale(px.vix[p])
        if not np.isfinite(px.vix[p]):
            n_vix_nan += 1
        for r in rungs:
            spec = RUNG_SPEC[r]
            fill, _ = px.fill(spec["fill"])
            w = (w_full if spec["ws"] == "full" else w_etb).copy()
            w[~np.isfinite(fill[p + 1])] = 0.0
            scale = vscale if spec["vix"] else 1.0
            w = w * scale
            ret, spy_r = px.returns(spec["fill"], p, length)
            st = state[r]
            if spec["hedge"] == "spy_ewma":
                h = hedge_size(w, b_ewma)
                blk = hold_block(w, ret, spy_r, h0=h)
            else:
                h = 0.0
                blk = hold_block(w, ret, spy_r, beta=b252)
            d_w = w - st["w"]
            d_h = h - st["h"]
            turnover = float(np.abs(d_w).sum())
            if spec["cost"] == "flat":
                cost = FLAT_COST_PER_SIDE * turnover
            else:
                cost = real_cost(ctx, t, px.symbols, d_w, d_h, attrs)
            n = len(blk["pnl"])
            cost_v = np.zeros(n)
            cost_v[0] = cost
            to_v = np.zeros(n)
            to_v[0] = turnover
            bor = (
                blk["short_notional"] * (BORROW_BP_YEAR / 1e4 / 252.0)
                if spec["borrow"]
                else np.zeros(n)
            )
            rows[r].append(
                pd.DataFrame(
                    {
                        "gross": blk["pnl"],
                        "cost": cost_v,
                        "borrow": bor,
                        "turnover": to_v,
                        "spy": spy_r,
                        "hedge_size": np.full(n, h),
                        "vix_scale": np.full(n, scale),
                    },
                    index=px.dates[p : p + n],
                )
            )
            st["w"], st["h"] = blk["w_end"], blk["h_end"]
    out = {}
    for r in rungs:
        df = pd.concat(rows[r])
        df["net"] = df["gross"] - df["cost"] - df["borrow"]
        df.attrs["vix_nan_decisions"] = n_vix_nan
        out[r] = df
    return out


def run_ladder() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    ctx = Context()
    meta = {"off_calendar_price_rows": ctx.px.off_calendar_rows, "n_symbols": ctx.px.N}
    for variant in VARIANTS:
        # R1a: daily bridge
        f = RAW / f"R1a_{variant}_daily.parquet"
        if not f.exists():
            out = run_pass(ctx, variant, 1, 0, ("R1",))
            out["R1"].to_parquet(f)
            print(variant, "R1a done", flush=True)
        for o in OFFSETS:
            files = {r: RAW / f"{r}_{variant}_o{o}.parquet" for r in RUNGS}
            if all(x.exists() for x in files.values()):
                continue
            out = run_pass(ctx, variant, WEEK, o, RUNGS)
            for r, df in out.items():
                df.to_parquet(files[r])
            print(variant, "offset", o, "done", flush=True)
    (RAW / "ladder_meta.json").write_text(json.dumps(meta, indent=1))


# ---------------------------------------------------------------------------
# checks: the vectorised pieces against the book's own classes
# ---------------------------------------------------------------------------
def run_checks() -> None:
    from open_composer.research.equity_book import optimize as op
    from open_composer.research.equity_book.borrow import short_eligible
    from open_composer.research.equity_book.panel import PricePanel
    from open_composer.research.equity_book.risk import RiskModel

    px = Prices()
    panel_store = YearStore(
        str(EB / "panel/{year}.parquet"),
        ["trade_date", "symbol", "close", "dollar_adv_21", "adv_rank", "vol_21"],
    )
    pp = PricePanel.from_dir(start="2022-06-01", end="2024-06-28", include_etfs=False)
    se = op.ShortEligibility(pp)
    out: dict = {"short_eligibility": {}, "ewma_beta": {}}
    for d in ("2024-01-02", "2024-03-28", "2024-06-14"):
        t = pd.Timestamp(d)
        attrs = panel_store.at(t)
        theirs = se(pp.dates.get_loc(t), attrs)
        mine = short_eligible(
            pd.DataFrame(
                {
                    "adv_rank": attrs["adv_rank"],
                    "price": attrs["close"],
                    "reverse_split_252": pd.Series(px.rs_recent(px.pos(t)), index=px.symbols)
                    .reindex(attrs.index)
                    .fillna(False)
                    .to_numpy(),
                },
                index=attrs.index,
            )
        )
        out["short_eligibility"][d] = {
            "names": int(len(attrs)),
            "eligible_theirs": int(theirs.sum()),
            "eligible_mine": int(mine.sum()),
            # names never in a decision universe are not in the wide matrices (no reverse-split
            # history): compare on the names the ladder can hold
            "n_different": int(
                ((theirs.reindex(mine.index) != mine) & mine.index.isin(px.symbols)).sum()
            ),
            "n_different_outside_ladder_symbols": int(
                ((theirs.reindex(mine.index) != mine) & ~mine.index.isin(px.symbols)).sum()
            ),
        }
    rm = RiskModel()
    eb = EwmaBeta()
    for d in ("2024-01-02", "2024-03-28", "2025-06-12", "2026-09-15"):
        t = pd.Timestamp(d)
        try:
            theirs = rm.predicted_beta(t, "ewma")
        except KeyError:
            theirs = None
        mine, saved = eb.at(t)
        out["ewma_beta"][d] = {
            "saved_date": str(saved.date()),
            "n": int(len(mine)),
            "max_abs_diff_vs_RiskModel": (
                None if theirs is None else float((theirs.reindex(mine.index) - mine).abs().max())
            ),
            "riskmodel_keyerror_fallback_used": theirs is None,
        }
    out["calendar_off_rows"] = px.off_calendar_rows
    out["pass"] = bool(
        all(v["n_different"] == 0 for v in out["short_eligibility"].values())
        and all((v["max_abs_diff_vs_RiskModel"] or 0.0) < 1e-12 for v in out["ewma_beta"].values())
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "checks.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, indent=1, default=float))


# ---------------------------------------------------------------------------
# report: window metrics, scorecard items, decision rule
# ---------------------------------------------------------------------------
def max_drawdown(r: pd.Series) -> float:
    c = r.cumsum()
    return float((c - c.cummax()).min())


def ols_beta(y: pd.Series, x: pd.Series) -> float:
    d = pd.concat([y, x], axis=1).dropna()
    if len(d) < 20:
        return float("nan")
    xv = d.iloc[:, 1].to_numpy()
    yv = d.iloc[:, 0].to_numpy()
    xc = xv - xv.mean()
    return float((xc * (yv - yv.mean())).sum() / (xc**2).sum())


def series_metrics(df: pd.DataFrame, window: tuple[str, str]) -> dict:
    from open_composer.research.scorecard_v2 import annual_sharpe
    from scripts.eval_book_v1_stage2 import dimson_beta

    sub = df.loc[window[0] : window[1]]
    n = len(sub)
    if n < 20:
        return {"n": n}
    net, gross = sub["net"], sub["gross"]
    to_sum = float(sub["turnover"].sum())
    return {
        "n": n,
        "gross_sharpe": annual_sharpe(gross),
        "net_sharpe": annual_sharpe(net),
        "ann_ret_gross": float(gross.mean() * 252),
        "ann_ret_net": float(net.mean() * 252),
        "ann_vol_net": float(net.std(ddof=1) * math.sqrt(252)),
        "max_dd_net": max_drawdown(net),
        "beta_ols": ols_beta(net, sub["spy"]),
        "beta_dimson": dimson_beta(df["net"], df["spy"], window),
        "turnover_one_sided_ann": float(sub["turnover"].mean() * 252 / 2.0),
        "trade_cost_bp_yr": float(sub["cost"].mean() * 252 * 1e4),
        "borrow_bp_yr": float(sub["borrow"].mean() * 252 * 1e4),
        "cost_bp_per_side_traded": float(sub["cost"].sum() / to_sum * 1e4) if to_sum > 0 else None,
        "mean_vix_scale": float(sub["vix_scale"].mean()),
    }


def blend(frames: list[pd.DataFrame]) -> pd.DataFrame:
    common = frames[0].index
    for f in frames[1:]:
        common = common.intersection(f.index)
    cols = ["gross", "cost", "borrow", "turnover", "spy", "hedge_size", "vix_scale", "net"]
    return sum(f.loc[common, cols] for f in frames) / len(frames)


def run_report() -> None:
    from open_composer.research.scorecard_v2 import score_family

    def load(rung: str, variant: str, o: int) -> pd.DataFrame:
        return pd.read_parquet(RAW / f"{rung}_{variant}_o{o}.parquet")

    res: dict = {"rungs": {}, "scorecard": {}, "windows": WINDOWS}
    # R1a (daily)
    res["rungs"]["R1a"] = {}
    for v in VARIANTS:
        d = pd.read_parquet(RAW / f"R1a_{v}_daily.parquet")
        res["rungs"]["R1a"][v] = {"blend": {w: series_metrics(d, ab) for w, ab in WINDOWS.items()}}
    series: dict = {}
    for r in RUNGS:
        res["rungs"][r] = {}
        for v in VARIANTS:
            offs = [load(r, v, o) for o in OFFSETS]
            series[(r, v)] = offs
            bl = blend(offs)
            res["rungs"][r][v] = {
                "blend": {w: series_metrics(bl, ab) for w, ab in WINDOWS.items()},
                "offsets": {
                    str(o): {w: series_metrics(d, ab) for w, ab in WINDOWS.items()}
                    for o, d in zip(OFFSETS, offs, strict=True)
                },
            }
    phases = json.loads((ROOT / "data/research/equity_book/regimes/phases.json").read_text())[
        "phases_recent"
    ]
    state = pd.read_parquet(ROOT / "data/research/equity_book/regimes/market_state.parquet")[
        "state"
    ]
    for r in ("R4", "R5", "R6"):
        rows, rows2 = [], []
        for v in VARIANTS:
            for o, d in zip(OFFSETS, series[(r, v)], strict=True):
                base = pd.DataFrame(
                    {"date": d.index, "variant": v, "offset": o, "net": d["net"].to_numpy()}
                )
                rows.append(base.assign(gross=d["gross"].to_numpy()))
                rows2.append(
                    base.assign(
                        net=(d["gross"] - 2.0 * (d["cost"] + d["borrow"])).to_numpy(),
                        gross=float("nan"),
                    )
                )
        returns, cost2x = pd.concat(rows), pd.concat(rows2)
        bil = pd.Series(0.0, index=pd.DatetimeIndex(returns["date"].unique()).sort_values())
        sc = score_family(returns, cost2x, bil, phases, state, n_trials=len(VARIANTS))
        res["scorecard"][r] = {
            "family": sc["family"],
            "variants": {
                v: {
                    "dsr": c["dsr"]["dsr"],
                    "psr0": c["dsr"]["psr0"],
                    "sr_annual_excess_recent": c["dsr"]["sr_annual"],
                    "n_eff": c["dsr"]["n_eff"],
                    "V4": c["vetoes"]["V4"],
                    "V5_z_min": c["vetoes"]["V5"]["z_min"],
                    "V5_windows": c["vetoes"]["V5"]["windows"],
                    "check_e": c["robustness"]["e_recent_consistency"],
                    "offset_sharpes": c["robustness"]["d_offsets"]["offset_sharpes"],
                }
                for v, c in sc["variants"].items()
            },
        }
    # decision rule on R6
    dec: dict = {}
    for v in VARIANTS:
        rec = res["rungs"]["R6"][v]["blend"]["recent"]
        card = res["scorecard"]["R6"]["variants"][v]
        c1 = bool(rec["net_sharpe"] >= 0.90)
        c2 = bool(abs(rec["beta_ols"]) <= 0.15 and abs(rec["beta_dimson"]) <= 0.15)
        c3 = card["V4"].get("triggered") is False
        z = card["V5_z_min"]
        c4 = bool(z is not None and z >= -2.0)
        dec[v] = {
            "net_sharpe_recent_ge_0.90": c1,
            "beta_ols_dimson_within_0.15": c2,
            "V4_not_vetoed": c3,
            "z_ge_minus_2": c4,
            "all": bool(c1 and c2 and c3 and c4),
            "values": {
                "net_sharpe_recent": rec["net_sharpe"],
                "beta_ols": rec["beta_ols"],
                "beta_dimson": rec["beta_dimson"],
                "V4_triggered": card["V4"].get("triggered"),
                "z": z,
            },
        }
    res["decision_rule"] = {
        "per_variant": dec,
        "proceed": bool(any(d["all"] for d in dec.values())),
    }
    r0 = json.loads((OUT / "r0_identity.json").read_text())
    res["R0_identity"] = {"pass": r0["pass"], "max_abs_diff": r0["max_abs_diff"]}
    res["R0_M0_U3000"] = {
        k: r0["windows"][k]["mine"]
        for k in ("stress", "anchor", "owner_A_2024_01_2026_06", "owner_B_2026_07_now")
    }
    res["trials"] = {"new_series": 28, "note": "4 variants x R1-R6 plus R1a diagnostic"}
    ck = OUT / "checks.json"
    res["checks"] = json.loads(ck.read_text()) if ck.exists() else None
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=float))
    print("wrote", OUT / "results.json", "proceed =", res["decision_rule"]["proceed"])


def write_report_md() -> None:
    """``report.md`` (Chinese, facts only) from ``results.json``."""
    r = json.loads((OUT / "results.json").read_text())
    names = {
        "R1a": "R1a 日频（新构造）",
        "R1": "R1 周频开盘",
        "R2": "R2 收盘成交",
        "R3": "R3 仅 ETB 做空",
        "R4": "R4 真实成本+融券",
        "R5": "R5 书级 EWMA beta 对冲",
        "R6": "R6 VIX 减半",
    }
    f2 = lambda x: "—" if x is None or not np.isfinite(x) else f"{x:.2f}"  # noqa: E731
    L: list[str] = []
    L.append("# 现实阶梯：总回报 M0/M1 多空的构造成本（T-20261002-25）\n")
    L.append(
        "数字全部来自同目录 `results.json`（`scripts/realism_ladder_book_ls.py`，预注册 `prereg.md`）。"
        f" R0 同一性检查：最大绝对差 {r['R0_identity']['max_abs_diff']}（容差 1e-9），通过={r['R0_identity']['pass']}。\n"
    )
    L.append("## 1. 近期窗口（2024-01-08..数据末，5 个偏移等权）净夏普逐级变化\n")
    L.append("| 档 | " + " | ".join(VARIANTS) + " |")
    L.append("|---|" + "---|" * len(VARIANTS))
    a0 = r["R0_M0_U3000"]["anchor"]
    L.append(
        f"| R0 回归分析口径（仅 M0_U3000，毛/净） | 毛 {f2(a0['sharpe'])} / 净 {f2(a0['net_sharpe'])} | — | — | — |"
    )
    for k in ("R1a", "R1", "R2", "R3", "R4", "R5", "R6"):
        cells = []
        for v in VARIANTS:
            m = r["rungs"][k][v]["blend"]["recent"]
            cells.append(f"毛 {f2(m['gross_sharpe'])} / 净 {f2(m['net_sharpe'])}")
        L.append(f"| {names[k]} | " + " | ".join(cells) + " |")
    L.append("\n## 2. 逐级夏普变化（净，近期）\n")
    L.append("| 步骤 | " + " | ".join(VARIANTS) + " |")
    L.append("|---|" + "---|" * len(VARIANTS))
    seq = ["R1a", "R1", "R2", "R3", "R4", "R5", "R6"]
    for a, b in zip(seq[:-1], seq[1:], strict=True):
        cells = []
        for v in VARIANTS:
            x = r["rungs"][b][v]["blend"]["recent"]["net_sharpe"]
            y = r["rungs"][a][v]["blend"]["recent"]["net_sharpe"]
            cells.append(f"{x - y:+.2f}")
        L.append(f"| {a} → {b} | " + " | ".join(cells) + " |")
    cells = []
    for v in VARIANTS:
        x = r["rungs"]["R6"][v]["blend"]["recent"]["net_sharpe"]
        y = r["rungs"]["R1a"][v]["blend"]["recent"]["net_sharpe"]
        cells.append(f"{x - y:+.2f}")
    L.append("| R1a → R6 合计 | " + " | ".join(cells) + " |")
    L.append(
        f"\nR0 → R1a（M0_U3000 近期净夏普）：{f2(a0['net_sharpe'])} → {f2(r['rungs']['R1a']['M0_U3000']['blend']['recent']['net_sharpe'])}"
        "（换构造：行业中性权重、rank-normal、不预知次日是否有价；R0 用全截面去均值分数且只保留有收益的名字）。\n"
    )
    for w, title in (
        ("A", "A 2024-01-08..2026-06-30"),
        ("B", "B 2026-07-01..数据末"),
        ("stress", "压力期 2017-10-02..2023-08-31"),
    ):
        L.append(f"## 3{'ABC'[['A', 'B', 'stress'].index(w)]}. {title}：净夏普 / 毛夏普\n")
        L.append("| 档 | " + " | ".join(VARIANTS) + " |")
        L.append("|---|" + "---|" * len(VARIANTS))
        for k in seq:
            cells = []
            for v in VARIANTS:
                m = r["rungs"][k][v]["blend"][w]
                cells.append(f"{f2(m.get('net_sharpe'))} / {f2(m.get('gross_sharpe'))}")
            L.append(f"| {names[k]} | " + " | ".join(cells) + " |")
        L.append("")
    L.append(
        "## 4. 近期窗口：实现 beta（OLS / Dimson）、年化净收益、净波动、最大回撤、单边换手、成本\n"
    )
    L.append(
        "| 档 | 变体 | beta OLS | beta Dimson | 年化净收益 | 年化净波动 | 最大回撤 | 单边年换手 | 交易成本 bp/年 | 融券 bp/年 | 每边成本 bp |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for k in seq:
        for v in VARIANTS:
            m = r["rungs"][k][v]["blend"]["recent"]
            L.append(
                f"| {k} | {v} | {f2(m['beta_ols'])} | {f2(m['beta_dimson'])} | {m['ann_ret_net']:.1%} | {m['ann_vol_net']:.1%} | {m['max_dd_net']:.1%} | {m['turnover_one_sided_ann']:.1f} | {m['trade_cost_bp_yr']:.0f} | {m['borrow_bp_yr']:.0f} | {f2(m['cost_bp_per_side_traded'])} |"
            )
    L.append("\n## 5. 评价标准 v2 项目（R4-R6，4 个变体，n_trials=4，bil=0）\n")
    L.append(
        "| 档 | 变体 | DSR | N_eff | V4 触发 | V4 63 日最大亏损（σ） | z 最小值 | 偏移净夏普（近期，5 个） |"
    )
    L.append("|---|---|---|---|---|---|---|---|")
    for k in ("R4", "R5", "R6"):
        fam = r["scorecard"][k]["family"]
        for v in VARIANTS:
            c = r["scorecard"][k]["variants"][v]
            v4 = c["V4"]
            s63 = v4.get("windows", {}).get("63", {}).get("loss_in_sigma")
            offs = ", ".join(f2(x) for x in c["offset_sharpes"].values())
            L.append(
                f"| {k} | {v} | {f2(c['dsr'])} | {f2(fam['n_eff'])} | {v4.get('triggered')} | {f2(s63)} | {f2(c['V5_z_min'])} | {offs} |"
            )
    L.append("\n## 6. 判定规则（R6，机械）\n")
    L.append(
        "| 变体 | 近期净夏普 ≥ 0.90 | beta 在 ±0.15 内（OLS 与 Dimson） | V4 未否决 | z ≥ −2 | 全部满足 |"
    )
    L.append("|---|---|---|---|---|---|")
    for v, d in r["decision_rule"]["per_variant"].items():
        vals = d["values"]
        L.append(
            f"| {v} | {d['net_sharpe_recent_ge_0.90']}（{f2(vals['net_sharpe_recent'])}） | {d['beta_ols_dimson_within_0.15']}（{f2(vals['beta_ols'])} / {f2(vals['beta_dimson'])}） | {d['V4_not_vetoed']}（触发={vals['V4_triggered']}） | {d['z_ge_minus_2']}（{f2(vals['z'])}） | {d['all']} |"
        )
    L.append(
        f"\n判定：{'进入 v1.2 简单构造合同' if r['decision_rule']['proceed'] else '停止（书线暂停，等待新信号）'}（proceed={r['decision_rule']['proceed']}）。"
    )
    L.append(
        f"\n试验计数：本任务新增 {r['trials']['new_series']} 条序列（{r['trials']['note']}）；项目级累计账本未找到，未汇总。\n"
    )
    ck = r.get("checks")
    if ck:
        L.append("## 7. 向量化部件与账本类的同一性检查\n")
        L.append(
            f"`checks.json`：通过={ck['pass']}；ETB 集合与 `op.ShortEligibility` 不同的名字数 {[v['n_different'] for v in ck['short_eligibility'].values()]}；EWMA beta 与 `RiskModel.predicted_beta` 最大差 {[v['max_abs_diff_vs_RiskModel'] for v in ck['ewma_beta'].values()]}。\n"
        )
    L.append("## 8. 口径与局限\n")
    L.append("- 当天数据末标签 2026-09-15（标签日 t 的收益是 F(t+2)/F(t+1)−1，需要 t+2 的价格）。")
    L.append(
        "- 持仓期内股数固定、权重漂移；换仓时按漂移后权重计成交额；R1-R4 的 beta 对冲沿用 R0 口径（逐股 beta_252，对冲额随漂移），不计对冲成本；R5/R6 用 SPY 固定股数并计 SPY 成本。"
    )
    L.append(
        "- 无退市收益（缺价格的名字按持有、收益 0）；融券只按 25 bp 基础费率，ETB 集合没有空头占比条款；多头无融资成本；成本来自拟合模型，不是模拟盘成交。"
    )
    L.append(
        "- 这些窗口此前都被看过，结果是构造现实性的度量，不是样本外证据；2–3 年窗口的夏普标准误约 0.6，B 窗约 1.4 以上。\n"
    )
    L.append("是否写 v1.2 由主审决定。")
    (OUT / "report.md").write_text("\n".join(L) + "\n")
    print("wrote", OUT / "report.md")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["r0", "ladder", "checks", "report"], required=True)
    a = ap.parse_args()
    if a.stage == "ladder":
        run_ladder()
        return
    if a.stage == "checks":
        run_checks()
        return
    if a.stage == "report":
        run_report()
        write_report_md()
        return
    if a.stage == "r0":
        res = r0_identity()
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "r0_identity.json").write_text(json.dumps(res, indent=1, default=float))
        print(json.dumps({k: res[k] for k in ("max_abs_diff", "pass")}))


if __name__ == "__main__":
    main()
