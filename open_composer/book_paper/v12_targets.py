"""Production target generator of book v1.2 (``t20261002_book_v12``, T-20261002-28).

``build_v12_targets(D, variant=...)`` returns the two schema-2 ``BookTarget`` files (F1 for quant1,
F2 for quant2) of decision date D.  It is stateless: for each of the five tranches it recomputes the
T-25 R6 weights at the tranche's last decision date <= D, sizes its virtual shares at that date's
close, and holds those shares fixed to D (the account simulator of ``scripts/book_v12_account.py``
does the same, day by day).  The account target at D is the netted whole-share book:

* stock shares = ``round_half_away(sum_o virtual shares)`` (times the F1 gross-cap scale when the
  netted book would exceed G = 1.8);
* SPY = the tranches' virtual hedge shares (F1); F2 adds the core 1.0 x E at close(D);
* F1 T-bill leg x = ``tbill_fraction(L, S)`` of the rounded target book at close(D).

Weights are ``shares x close(D) / E`` and ``reference_prices`` are the closes of D, so the order
engine's ``round_half_away(weight x E / price)`` reproduces the target shares.

The contract logic is not reimplemented: tranche rules, scaling, virtual shares and the T-bill leg
come from ``open_composer.research.equity_book.book_v12``; the decision inputs (theme scores,
easy-to-borrow proxy, fill mask, EWMA beta, VIX) come from the functions of
``scripts/book_v12_account.py``, which this module drives with a window-sized data context that
can be pointed at any equity-book root (the research snapshot, or the live root of T-20261001-22).

Differences from the simulator that cannot be removed in production (all reported, none hidden):

* the simulator's fill mask (a name needs a close on D+1) is only applied here to tranche dates
  whose D+1 is at or before D, unless ``fill_lookahead=True`` (parity tests, replay diagnostics);
  the newest tranche cannot know D+1 and keeps every name;
* the simulator carries positions between days (minimum-notional drops, delisted names); the target
  is the stateless netted book, so a name without a close on D is dropped and listed in
  ``V12Bundle.unpriced``.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.book_paper.targets import (
    BookTarget,
    NameExposure,
    default_execution_date,
    now_utc_text,
    seal_target,
)
from open_composer.research.equity_book import book_v12 as bv

ROOT = Path(__file__).resolve().parents[2]
RESEARCH_ROOT = ROOT / "data/research/equity_book"
ITERATION_DIR = ROOT / "reports/research/iterations/t20261002_book_v12"
RESULTS_JSON = ITERATION_DIR / "results.json"
BOOK_PREFIX = "t20261002_book_v12"
VARIANTS = ("M0_U3000", "M0_P1000", "M1_U3000", "M1_P1000")
ACCOUNT_OF_FORM = {"F1": "quant1", "F2": "quant2"}
RS_LOOKBACK = 253  # sessions of price history before the oldest decision date (reverse-split flags)
VIX_FFILL = 3  # same forward fill as the backtest
MAX_TRANCHE_WALKBACK = 4  # extra weeks back when a tranche date has no theme row
MONTH_SESSIONS = 25  # M1 replays the tranche's first decision of the calendar month


class TargetRefused(RuntimeError):
    """The generator will not produce a target (stale or incomplete data, bad variant)."""


# ---------------------------------------------------------------------------
# data context (window-sized stand-in of ``realism_ladder_book_ls.Context``)
# ---------------------------------------------------------------------------
def default_data_root() -> Path:
    """``OC_EQUITY_BOOK_DIR`` when set (live root), else the research snapshot."""
    env = os.environ.get("OC_EQUITY_BOOK_DIR")
    return Path(env) if env else RESEARCH_ROOT


def _ensure_repo_on_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


class _Rows:
    """Row-addressable window of a (T, N) matrix: absolute row index in, NaN row past the end."""

    def __init__(self, base: int, data: np.ndarray) -> None:
        self.base, self.data = base, data

    def __getitem__(self, i: int) -> np.ndarray:
        j = int(i) - self.base
        if j < 0:
            raise IndexError(f"row {i} is before the loaded window ({self.base})")
        if j >= self.data.shape[0]:
            return np.full(self.data.shape[1], np.nan)
        return self.data[j]


class _Prices:
    """Duck-typed ``realism_ladder_book_ls.Prices`` over a window of sessions."""

    def __init__(
        self, root: Path, dates: pd.DatetimeIndex, first_pos: int, last_pos: int, vix_dir: Path
    ) -> None:
        self.dates = dates
        self.T = len(dates)
        self.base = first_pos
        hi = min(last_pos, self.T - 1)
        lo_date = dates[first_pos]
        frames = []
        for year in range(dates[first_pos].year, dates[hi].year + 1):
            f = root / "prices" / f"{year}.parquet"
            if not f.exists():
                continue
            df = pd.read_parquet(f, columns=["trade_date", "symbol", "open", "close"])
            df = df[(df["trade_date"] >= lo_date) & (df["trade_date"] <= dates[hi])]
            frames.append(df.drop_duplicates(["trade_date", "symbol"], keep="last"))
        if not frames:
            raise TargetRefused(f"no price files under {root / 'prices'}")
        allp = pd.concat(frames, ignore_index=True)
        self.symbols = pd.Index(sorted(allp["symbol"].unique()))
        n_rows = hi - first_pos + 1
        o_mat = np.full((n_rows, len(self.symbols)), np.nan)
        c_mat = np.full((n_rows, len(self.symbols)), np.nan)
        r = dates.get_indexer(pd.DatetimeIndex(allp["trade_date"])) - first_pos
        k = self.symbols.get_indexer(allp["symbol"])
        ok = (r >= 0) & (r < n_rows) & (k >= 0)
        o_mat[r[ok], k[ok]] = allp["open"].to_numpy("float64")[ok]
        c_mat[r[ok], k[ok]] = allp["close"].to_numpy("float64")[ok]
        del allp, frames
        self.N = len(self.symbols)
        self._o, self._c = o_mat, c_mat
        self.C = _Rows(first_pos, c_mat)
        etf = pd.read_parquet(root / "etf_daily.parquet", columns=["trade_date", "symbol", "close"])
        self.etf_close: dict[str, np.ndarray] = {}
        for sym in ("SPY", "SGOV", "BIL"):
            s = etf[etf["symbol"] == sym].drop_duplicates("trade_date", keep="last")
            self.etf_close[sym] = (
                s.set_index("trade_date")["close"].sort_index().reindex(dates).to_numpy("float64")
            )
        self.spy_c = self.etf_close["SPY"]
        vix = _load_vix(vix_dir).reindex(dates).ffill(limit=VIX_FFILL)
        self.vix = vix.to_numpy("float64")
        self._rs_cum: np.ndarray | None = None

    def rs_recent(self, pos: int) -> np.ndarray:
        """Reverse split in the past ``RS_WINDOW`` sessions incl. ``pos`` (as ShortEligibility)."""
        from open_composer.research.equity_book.borrow import RS_WINDOW, detect_reverse_splits

        if self._rs_cum is None:
            flags = detect_reverse_splits(
                pd.DataFrame(self._o, copy=False), pd.DataFrame(self._c, copy=False)
            )
            self._rs_cum = np.cumsum(flags.to_numpy(dtype=bool), axis=0, dtype=np.int32)
        lo = max(pos - RS_WINDOW + 1, 0)
        if lo - 1 < self.base and lo > 0:
            raise IndexError("reverse-split window starts before the loaded price window")
        base = self._rs_cum[lo - 1 - self.base] if lo > 0 else 0
        return (self._rs_cum[pos - self.base] - base) > 0


def _load_vix(vix_dir: Path) -> pd.Series:
    f = vix_dir / "VIXCLS.csv"
    if not f.exists():
        raise TargetRefused(f"VIX file missing: {f}")
    v = pd.read_csv(f, na_values=["."])
    v["observation_date"] = pd.to_datetime(v["observation_date"])
    return v.set_index("observation_date")["VIXCLS"].astype(float)


def default_vix_dir(root: Path) -> Path:
    """``<root>/../vix`` when it exists (the research layout), else the research VIX directory."""
    sibling = Path(root).parent / "vix"
    return sibling if (sibling / "VIXCLS.csv").exists() else ROOT / "data/research/vix"


@dataclass
class V12Context:
    """Everything the decision functions of the account script read, from one equity-book root."""

    root: Path
    px: _Prices
    themes: Any
    fic: Any
    panel: Any
    sig: Any
    ewma: Any
    first_pos: int
    last_pos: int

    @classmethod
    def open(
        cls,
        data_root: Path | str | None,
        *,
        first_date: date | pd.Timestamp,
        last_date: date | pd.Timestamp,
        vix_dir: Path | None = None,
    ) -> V12Context:
        """Window covering the tranche history of every decision date in [first_date, last_date]."""
        _ensure_repo_on_path()
        from scripts.realism_ladder_book_ls import EwmaBeta, YearStore
        from scripts.run_book_v1_stage2 import FormationIC, ThemeStore

        root = Path(data_root) if data_root else default_data_root()
        cal_file = root / "panel/_calendar.parquet"
        if not cal_file.exists():
            raise TargetRefused(f"no session calendar under {root}")
        cal = pd.read_parquet(cal_file)
        dates = pd.DatetimeIndex(cal["trade_date"])
        if not dates.is_monotonic_increasing:
            raise TargetRefused("session calendar is not sorted")
        p_first = int(dates.searchsorted(pd.Timestamp(first_date)))
        if p_first >= len(dates):
            raise TargetRefused(f"{first_date} is after the last session of {root}")
        p_last = int(dates.searchsorted(pd.Timestamp(last_date), side="right")) - 1
        if p_last < 0 or p_last < p_first:
            raise TargetRefused(f"no session between {first_date} and {last_date} in {root}")
        margin = bv.N_TRANCHES * (1 + MAX_TRANCHE_WALKBACK) + MONTH_SESSIONS + RS_LOOKBACK
        base = max(0, p_first - margin)
        px = _Prices(root, dates, base, p_last + 1, vix_dir or default_vix_dir(root))
        fic = pd.read_parquet(root / "alpha/book_v1/formation_ic.parquet")
        panel = YearStore(
            str(root / "panel/{year}.parquet"),
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
        sig = YearStore(str(root / "signals/{year}.parquet"), ["trade_date", "symbol", "ind_code"])
        return cls(
            root=root,
            px=px,
            themes=ThemeStore(root / "alpha/book_v1"),
            fic=FormationIC(fic, dates),
            panel=panel,
            sig=sig,
            ewma=EwmaBeta(root / "risk"),
            first_pos=p_first,
            last_pos=p_last,
        )


# ---------------------------------------------------------------------------
# tranche arithmetic
# ---------------------------------------------------------------------------
def tranche_positions(p_d: int, n: int = bv.N_TRANCHES) -> list[int]:
    """Position of every tranche's last decision date <= ``p_d`` (tranche o: ``pos % n == o``)."""
    return [p_d - ((p_d - o) % n) for o in range(n)]


@dataclass
class TrancheState:
    o: int
    p: int
    date: pd.Timestamp
    vscale: float
    h_unit: float
    k1: float
    k2: float
    virt1: np.ndarray  # F1 virtual stock shares (dense over px.symbols)
    virt2: np.ndarray
    hedge1: float  # F1 virtual SPY shares
    hedge2: float
    beta: np.ndarray  # dense EWMA beta used by the hedge (missing 1.0, clipped [-1, 4])
    n_members: int
    fill_assumed: bool = False


def _dense_beta(di: Any, symbols: pd.Index) -> np.ndarray:
    names = di.score.dropna().index
    idx = symbols.get_indexer(names)
    ev = di.beta.reindex(names).fillna(1.0).clip(-1.0, 4.0).to_numpy()
    out = np.ones(len(symbols))
    keep = idx >= 0
    out[idx[keep]] = ev[keep]
    return out


def _first_month_positions(ctx: V12Context, p: int, o: int) -> list[int]:
    """Decision positions of tranche ``o`` from the first of ``p``'s calendar month to ``p``."""
    t = ctx.px.dates[p]
    q = int(ctx.px.dates.searchsorted(pd.Timestamp(t.year, t.month, 1)))
    q += (o - q) % bv.N_TRANCHES
    return list(range(q, p + 1, bv.N_TRANCHES))


def compute_tranche(
    ctx: V12Context, variant: str, o: int, p: int, *, p_d: int, fill_lookahead: bool
) -> TrancheState:
    """Weights and virtual shares of tranche ``o`` at decision position ``p`` (<= ``p_d``)."""
    _ensure_repo_on_path()
    from scripts import book_v12_account as acct

    px = ctx.px
    flag = acct.variant_flag(variant)
    di = None
    walk = 0
    while di is None:
        # a fresh source per attempt: M1 re-weights at the tranche's first decision of each
        # calendar month, so replay that call (the first with a theme row) before the real one
        src = acct.make_source(ctx, variant)
        for q in _first_month_positions(ctx, p, o):
            di_q = acct.decision_inputs(ctx, src, flag, q)
            if di_q is not None:
                di = di_q if q == p else acct.decision_inputs(ctx, src, flag, p)
                break
        if di is None:
            walk += 1
            if walk > MAX_TRANCHE_WALKBACK:
                raise TargetRefused(f"tranche {o}: no theme row at {px.dates[p].date()} or earlier")
            p -= bv.N_TRANCHES
    fill_assumed = False
    if (p == p_d and not fill_lookahead) or p + 1 >= px.T:
        di = dataclasses.replace(di, fill_ok=np.ones(px.N, dtype=bool))
        fill_assumed = True
    tt = acct.tranche_from_inputs(ctx, di)
    if not math.isfinite(di.vix):
        raise TargetRefused(f"VIX missing at {px.dates[p].date()} (stale VIX file)")
    p_ref = np.asarray(px.C[p], dtype="float64")
    spy_ref = float(px.spy_c[p])
    if not (math.isfinite(spy_ref) and spy_ref > 0):
        raise TargetRefused(f"SPY close missing at {px.dates[p].date()}")
    k1 = bv.f1_k_eff(tt.vscale, tt.h_unit)
    k2 = bv.f2_k2_eff(tt.vscale, tt.h_unit)
    e = bv.EQUITY
    return TrancheState(
        o=o,
        p=p,
        date=px.dates[p],
        vscale=tt.vscale,
        h_unit=tt.h_unit,
        k1=k1,
        k2=k2,
        virt1=bv.virtual_shares(tt.w_unit, k1, e, p_ref),
        virt2=bv.virtual_shares(tt.w_unit, k2, e, p_ref),
        hedge1=tt.h_unit * k1 * (e / bv.N_TRANCHES) / spy_ref,
        hedge2=tt.h_unit * k2 * (e / bv.N_TRANCHES) / spy_ref,
        beta=_dense_beta(di, px.symbols),
        n_members=tt.n_members,
        fill_assumed=fill_assumed,
    )


# ---------------------------------------------------------------------------
# netted book and target files
# ---------------------------------------------------------------------------
@dataclass
class FormBook:
    """Netted whole-share target book of one account form."""

    form: str
    stock_shares: np.ndarray  # dense over symbols, rounded (after the gross-cap scale)
    virt_total: np.ndarray  # dense unrounded sum of the tranche virtual shares
    scale: float
    scale_event: bool
    hedge_virtual: float  # unrounded SPY hedge shares (tranche sum x scale)
    spy_virtual: float  # unrounded SPY shares incl. the F2 core
    spy_shares: int
    long_frac: float
    short_frac: float
    tbill_fraction: float
    tbill_symbol: str | None
    tbill_shares: int
    beta_eff: np.ndarray


@dataclass
class V12Bundle:
    decision_date: date
    execution_date: date
    variant: str
    data_root: Path
    tranches: list[TrancheState]
    books: dict[str, FormBook]
    targets: dict[str, BookTarget]
    unpriced: dict[str, list[str]] = field(default_factory=dict)
    vix: float = float("nan")
    tbill_symbol: str = "SGOV"
    p_d: int = 0
    symbols: pd.Index | None = None
    close_d: np.ndarray | None = None
    notes: list[str] = field(default_factory=list)


def _tbill_price(px: _Prices, p_d: int) -> tuple[str, float]:
    for sym in bv_tbill_symbols():
        v = float(px.etf_close[sym][p_d])
        if math.isfinite(v) and v > 0:
            return sym, v
    raise TargetRefused("neither SGOV nor BIL has a close on the decision date")


def bv_tbill_symbols() -> tuple[str, str]:
    return ("SGOV", "BIL")


def _net_book(
    form: str,
    virt_total: np.ndarray,
    hedge_virtual: float,
    beta_eff: np.ndarray,
    close_d: np.ndarray,
    spy_d: float,
    tbill: tuple[str, float],
) -> FormBook:
    e = bv.EQUITY
    core_shares = bv.F2_CORE * e / spy_d if form == "F2" else 0.0

    def book_at(scale: float):
        stock_q = bv.round_half_away_array(virt_total * scale)
        spy_q = int(bv.round_half_away_array(np.array([hedge_virtual * scale + core_shares]))[0])
        val = stock_q * np.where(np.isfinite(close_d), close_d, 0.0)
        spy_val = spy_q * spy_d
        long_f = (val[val > 0].sum() + max(spy_val, 0.0)) / e
        short_f = (-val[val < 0].sum() + max(-spy_val, 0.0)) / e
        return stock_q, spy_q, long_f, short_f

    scale, event = 1.0, False
    stock_q, spy_q, long_f, short_f = book_at(scale)
    if form == "F1" and long_f + short_f > bv.G_CAP + 1e-12:
        scale, event = bv.gross_scale(long_f, short_f), True
        stock_q, spy_q, long_f, short_f = book_at(scale)
    x = bv.tbill_fraction(long_f, short_f) if form == "F1" else 0.0
    sym, price = tbill
    t_shares = int(bv.round_half_away_array(np.array([x * e / price]))[0]) if form == "F1" else 0
    return FormBook(
        form=form,
        stock_shares=stock_q,
        virt_total=virt_total,
        scale=scale,
        scale_event=event,
        hedge_virtual=hedge_virtual * scale,
        spy_virtual=hedge_virtual * scale + core_shares,
        spy_shares=spy_q,
        long_frac=float(long_f),
        short_frac=float(short_f),
        tbill_fraction=float(x),
        tbill_symbol=sym if form == "F1" else None,
        tbill_shares=t_shares,
        beta_eff=beta_eff,
    )


def _effective_beta(tranches: list[TrancheState], form: str) -> np.ndarray:
    """Share-weighted EWMA beta over the tranches that hold the name (1.0 where no net shares)."""
    num = np.zeros_like(tranches[0].beta)
    den = np.zeros_like(num)
    for t in tranches:
        v = t.virt1 if form == "F1" else t.virt2
        num += v * t.beta
        den += v
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(np.abs(den) > 1e-12, num / den, np.nan)
    return out


def _risk_size(ctx: V12Context, t: pd.Timestamp) -> pd.Series:
    """``size`` exposure of the latest saved risk-model date <= t (saved weekly)."""
    for y in (t.year, t.year - 1):
        f = ctx.root / "risk" / f"exposures_{y}.parquet"
        if not f.exists():
            continue
        df = pd.read_parquet(f, columns=["trade_date", "symbol", "size"])
        df = df[df["trade_date"] <= t]
        if len(df):
            d = df["trade_date"].max()
            return df[df["trade_date"] == d].set_index("symbol")["size"]
    return pd.Series(dtype="float64")


def _opt(x: float) -> float | None:
    return float(x) if x is not None and math.isfinite(float(x)) else None


def build_target_file(
    ctx: V12Context,
    form: str,
    book: FormBook,
    *,
    variant: str,
    p_d: int,
    logged_at_utc: str,
    close_d: np.ndarray,
    attrs: pd.DataFrame,
    ind: pd.Series,
    size: pd.Series,
    beta_d: pd.Series,
) -> BookTarget:
    px = ctx.px
    e = bv.EQUITY
    t_d = px.dates[p_d]
    spy_d = float(px.spy_c[p_d])
    # every name with a non-zero virtual position keeps its exact weight (a half share rounds to
    # zero in the engine, but belongs to the target gross that the gross check compares against)
    dollars = np.abs(book.virt_total) * np.where(np.isfinite(close_d), close_d, 0.0)
    held = np.flatnonzero(dollars > 1e-6)  # cancellation residue between tranches is not a name
    sym_index = px.symbols
    weights: dict[str, float] = {}
    for j in held:
        weights[str(sym_index[j])] = float(book.virt_total[j] * book.scale * float(close_d[j]) / e)
    # Reference prices and exposures cover every name with a close on D, not only the target
    # names: the engine needs a price (and, for a leftover position, an exposure) for any name an
    # account may still hold from earlier days (closing trades, sub-$100 leftovers).
    priced = np.flatnonzero(np.isfinite(close_d) & (close_d > 0))
    names = [str(sym_index[j]) for j in priced if str(sym_index[j]) in attrs.index]
    listed = set(names)
    names += [s for s in weights if s not in listed]
    ref: dict[str, float] = {}
    exposures: dict[str, NameExposure] = {}
    a_all = attrs.reindex(names)
    beta_d = beta_d.reindex(names).fillna(1.0).clip(-1.0, 4.0)
    idx_of = {str(sym_index[j]): int(j) for j in held}
    for i, s in enumerate(names):
        j = idx_of.get(s)
        if j is None:
            j = sym_index.get_loc(s)
        ref[s] = float(close_d[j])
        be = book.beta_eff[j] if s in weights else np.nan
        b = float(be) if math.isfinite(be) else float(beta_d.loc[s])
        a = a_all.iloc[i]
        ind_code = ind.get(s)
        sz = size.get(s)
        exposures[s] = NameExposure(
            beta=b,
            industry="unknown" if ind_code is None or pd.isna(ind_code) else str(int(ind_code)),
            size=float(sz) if sz is not None and math.isfinite(sz) else 0.0,
            dollar_adv_21=_opt(a["dollar_adv_21"]),
            vol_21=_opt(a["vol_21"]),
        )
    hedge_weight = float(book.hedge_virtual * spy_d / e)
    ref["SPY"] = spy_d
    exposures["SPY"] = NameExposure(beta=1.0, industry="index", size=0.0)
    if form == "F1":
        assert book.tbill_symbol is not None
        t_price = float(px.etf_close[book.tbill_symbol][p_d])
        weights["SPY"] = hedge_weight
        weights[book.tbill_symbol] = book.tbill_fraction
        ref[book.tbill_symbol] = t_price
        core_symbol, core_weight = book.tbill_symbol, book.tbill_fraction
    else:
        weights["SPY"] = bv.F2_CORE + hedge_weight
        core_symbol, core_weight = "SPY", bv.F2_CORE
    suffix = ":tbill=BIL" if form == "F1" and book.tbill_symbol == "BIL" else ""
    return BookTarget(
        schema_version=2,
        book_id=f"{BOOK_PREFIX}:{variant}:{form}{suffix}",
        account=ACCOUNT_OF_FORM[form],
        form=form,  # type: ignore[arg-type]
        decision_date=t_d.date(),
        execution_date=default_execution_date(t_d.date()),
        equity_basis=e,
        core_symbol=core_symbol,
        core_weight=core_weight,
        hedge_symbol="SPY",
        hedge_weight=hedge_weight,
        weights=weights,
        reference_prices=ref,
        exposures=exposures,
        logged_at_utc=logged_at_utc,
    )


def build_v12_bundle(
    decision_date: date | pd.Timestamp | str,
    *,
    variant: str,
    data_root: Path | str | None = None,
    context: V12Context | None = None,
    logged_at_utc: str | None = None,
    fill_lookahead: bool = False,
) -> V12Bundle:
    """Both targets of ``decision_date`` plus the intermediate books (for tests and the replay)."""
    if variant not in VARIANTS:
        raise TargetRefused(f"variant must be one of {VARIANTS}, got {variant!r}")
    t_d = pd.Timestamp(decision_date)
    ctx = context or V12Context.open(data_root, first_date=t_d, last_date=t_d)
    px = ctx.px
    if t_d not in px.dates:
        raise TargetRefused(f"{t_d.date()} is not a session of {ctx.root}")
    p_d = int(px.dates.get_loc(t_d))
    if p_d < ctx.first_pos or p_d > ctx.last_pos:
        raise TargetRefused("decision date outside the loaded window")
    tranches = [
        compute_tranche(ctx, variant, o, p, p_d=p_d, fill_lookahead=fill_lookahead)
        for o, p in enumerate(tranche_positions(p_d))
    ]
    close_d = np.asarray(px.C[p_d], dtype="float64")
    spy_d = float(px.spy_c[p_d])
    if not (math.isfinite(spy_d) and spy_d > 0):
        raise TargetRefused(f"SPY close missing at {t_d.date()}")
    tbill = _tbill_price(px, p_d)
    priced = np.isfinite(close_d) & (close_d > 0)
    unpriced: dict[str, list[str]] = {}
    books: dict[str, FormBook] = {}
    for form in ("F1", "F2"):
        virt = sum(t.virt1 if form == "F1" else t.virt2 for t in tranches)
        gone = np.flatnonzero((np.abs(virt) > 0) & ~priced)
        unpriced[form] = [str(px.symbols[j]) for j in gone]
        virt = np.where(priced, virt, 0.0)
        hedge = sum(t.hedge1 if form == "F1" else t.hedge2 for t in tranches)
        books[form] = _net_book(
            form, virt, float(hedge), _effective_beta(tranches, form), close_d, spy_d, tbill
        )
    attrs = ctx.panel.at(t_d)
    ind = ctx.sig.at(t_d)["ind_code"]
    size = _risk_size(ctx, t_d)
    beta_d = ctx.ewma.at(t_d)[0]
    stamp = logged_at_utc or now_utc_text()
    targets = {
        ACCOUNT_OF_FORM[form]: build_target_file(
            ctx,
            form,
            books[form],
            variant=variant,
            p_d=p_d,
            logged_at_utc=stamp,
            close_d=close_d,
            attrs=attrs,
            ind=ind,
            size=size,
            beta_d=beta_d,
        )
        for form in ("F1", "F2")
    }
    targets = {k: seal_target(v) for k, v in targets.items()}
    return V12Bundle(
        decision_date=t_d.date(),
        execution_date=default_execution_date(t_d.date()),
        variant=variant,
        data_root=ctx.root,
        tranches=tranches,
        books=books,
        targets=targets,
        unpriced=unpriced,
        vix=float(px.vix[p_d]),
        tbill_symbol=tbill[0],
        p_d=p_d,
        symbols=px.symbols,
        close_d=close_d,
    )


def build_v12_targets(
    decision_date: date | pd.Timestamp | str,
    *,
    variant: str,
    data_root: Path | str | None = None,
    context: V12Context | None = None,
    logged_at_utc: str | None = None,
    fill_lookahead: bool = False,
) -> dict[str, BookTarget]:
    """``{"quant1": F1, "quant2": F2}`` schema-2 targets of ``decision_date`` (see module doc)."""
    return build_v12_bundle(
        decision_date,
        variant=variant,
        data_root=data_root,
        context=context,
        logged_at_utc=logged_at_utc,
        fill_lookahead=fill_lookahead,
    ).targets


# ---------------------------------------------------------------------------
# summaries and the primary-variant gate
# ---------------------------------------------------------------------------
def summarize_target(target: BookTarget) -> dict[str, Any]:
    stock = target.stock_weights
    longs = sum(w for w in stock.values() if w > 0)
    shorts = -sum(w for w in stock.values() if w < 0)
    beta = sum(target.exposures[s].beta * w for s, w in stock.items() if s in target.exposures)
    hedge_total = target.hedge_weight
    return {
        "account": target.account,
        "form": target.form,
        "book_id": target.book_id,
        "decision_date": target.decision_date.isoformat(),
        "execution_date": target.execution_date.isoformat(),
        "n_names": len(stock),
        "n_long": sum(w > 0 for w in stock.values()),
        "n_short": sum(w < 0 for w in stock.values()),
        "long": round(longs, 6),
        "short": round(shorts, 6),
        "hedge_weight": round(hedge_total, 6),
        "core_symbol": target.core_symbol,
        "core_weight": round(target.core_weight, 6),
        "gross_stock": round(longs + shorts, 6),
        "gross_total": round(sum(abs(w) for w in target.weights.values()), 6),
        "stock_beta": round(beta, 6),
        "max_name_weight": round(max((abs(w) for w in stock.values()), default=0.0), 6),
        "payload_sha256": target.payload_sha256,
    }


def primary_variant(results_path: Path = RESULTS_JSON) -> str:
    """Primary variant of the T-20261002-26 decision; refuses unless the decision is a paper start.

    ``results.json`` must carry ``primary_variant`` and ``decision``: a string that says to proceed
    to paper (``proceed to paper incubation ...`` as T-20261002-26 wrote it, ``paper_start``) and
    contains no negation, or the object ``{"paper_start": true}``."""
    if not results_path.is_file():
        raise TargetRefused(f"no results file yet: {results_path}")
    data = json.loads(results_path.read_text(encoding="utf-8"))
    variant = data.get("primary_variant") or data.get("primary")
    decision = data.get("decision")
    if not variant or decision is None:
        raise TargetRefused("results.json lacks primary_variant or decision")
    if isinstance(decision, dict):
        ok = bool(decision.get("paper_start") or decision.get("start_paper"))
    else:
        text = str(decision).strip().lower()
        negative = re.search(r"\bno paper|do not|not proceed|\bstop\b|\bhold\b|\bwithdraw", text)
        positive = re.search(r"proceed to paper|paper incubation|paper start|start paper", text)
        ok = bool(positive) and not negative or text.startswith("paper_start")
    if not ok:
        raise TargetRefused(f"decision is not a paper start: {decision!r}")
    if variant not in VARIANTS:
        raise TargetRefused(f"primary variant {variant!r} is not a contract variant")
    return str(variant)


def last_session(data_root: Path | str | None = None) -> date:
    root = Path(data_root) if data_root else default_data_root()
    cal = pd.read_parquet(root / "panel/_calendar.parquet")
    return pd.Timestamp(cal["trade_date"].max()).date()


__all__ = [
    "ITERATION_DIR",
    "RESULTS_JSON",
    "TargetRefused",
    "V12Bundle",
    "V12Context",
    "VARIANTS",
    "build_v12_bundle",
    "build_v12_targets",
    "default_data_root",
    "last_session",
    "primary_variant",
    "summarize_target",
    "tranche_positions",
]
