"""Factor exposures of the hedge ETFs (design section 8, D5).

The hedge ETFs (SPY, IWM, IJR and the sector SPDRs) are not in the model's U3000 cross-section, so
they have no exposure row ``x_i`` or specific variance.  They get one from a *rolling time-series
regression* of their daily close-to-close returns on the model's daily factor returns::

    r_etf,t = sum_g b_g (f_mkt,t + f_g,t) + sum_s b_s f_s,t + e_t        (252 sessions ending at t)

Parametrisation.  A stock has exposure 1 on the market and 1 on exactly one industry, so for a
stock the industry exposures sum to the market exposure.  The model identifies the market factor
through ``sum_g W_g f_g = 0``; a regression on separate ``f_mkt`` and ``f_g`` columns is therefore
(near-)collinear and the industry loadings are only determined up to a multiple of ``W_g``.  We
remove the ambiguity by giving the ETF the *stock-like* representative: ``b_mkt = sum_g b_g``
(the regressors are ``f_mkt + f_g`` per industry plus the styles).  Then ``b_g`` is the ETF's
industry weight (they sum to its market loading), which is what the optimizer's industry
constraint needs to see: a long-stock book that mirrors the market and a short SPY leg cancel in
every industry.  The fit is the minimum-norm least squares (``numpy.linalg.lstsq``); ``ridge`` adds
an optional ridge (fraction of the mean diagonal of ``Z'Z``), default 0 = plain OLS.

Specific variance ``D_etf = SSR / (n - p)`` (daily variance), floored at ``SPEC_VAR_FLOOR``.

Date alignment: the factor return stamped at date ``d`` is the return of session ``d``; the ETF
return of session ``d`` is ``close_d / close_{d-1} - 1`` on the factor-return calendar (a missing
ETF close makes the return NaN; such a day is dropped from that ETF's regression).

Results are cached on disk (``data/research/equity_book/etf_risk/etf_exposures.parquet``) keyed by
the size/mtime of the factor-return files, so a rebuilt risk model invalidates the cache.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from open_composer.research.equity_book.panel import DEFAULT_DIR
from open_composer.research.equity_book.risk import MARKET, RISK_DIR, STYLES, RiskModel

ETF_RISK_DIR = DEFAULT_DIR / "etf_risk"
# Hedge instruments: broad index and sector ETFs (the T-bill ETFs are the sleeve, not hedges).
HEDGE_ETF_SYMBOLS = (
    "SPY",
    "IWM",
    "IJR",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
)
WINDOW = 252
MIN_OBS = 200
SPEC_VAR_FLOOR = 1e-7  # daily variance (about 0.5% annualised idiosyncratic vol)


def fit_etf_loadings(
    y: np.ndarray,
    f_mkt: np.ndarray,
    f_groups: np.ndarray,
    f_styles: np.ndarray,
    ridge: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """One ETF's regression.  ``y`` (T), ``f_mkt`` (T), ``f_groups`` (T, G), ``f_styles`` (T, S).
    Returns ``(b_groups, b_styles, b_market, spec_var)``; ``b_market = b_groups.sum()``.  The
    caller drops NaN rows."""
    z = np.column_stack([f_groups + f_mkt[:, None], f_styles])
    n, p = z.shape
    if ridge > 0.0:
        zz = z.T @ z
        lam = ridge * float(np.mean(np.diag(zz)))
        theta = np.linalg.solve(zz + lam * np.eye(p), z.T @ y)
    else:
        theta, *_ = np.linalg.lstsq(z, y, rcond=None)
    resid = y - z @ theta
    dof = max(n - p, 1)
    g = f_groups.shape[1]
    return theta[:g], theta[g:], float(theta[:g].sum()), float(resid @ resid / dof)


def load_factor_returns(base: Path | str = RISK_DIR) -> pd.DataFrame:
    """All saved daily factor returns as a wide frame (dates x factors)."""
    base = Path(base)
    parts = [pd.read_parquet(f) for f in sorted(base.glob("factor_returns_*.parquet"))]
    if not parts:
        raise FileNotFoundError(f"no factor_returns_*.parquet under {base}")
    long = pd.concat(parts, ignore_index=True)
    return long.pivot(index="trade_date", columns="factor", values="ret").sort_index()


def load_etf_daily(path: Path | str | None = None) -> pd.DataFrame:
    """The ETF daily file: ``trade_date, symbol, open, close, volume``."""
    p = Path(path) if path else DEFAULT_DIR / "etf_daily.parquet"
    return pd.read_parquet(p)


def regress_etfs(
    fr: pd.DataFrame,
    etf_ret: pd.DataFrame,
    groups: Sequence[str],
    styles: Sequence[str],
    factors: Sequence[str],
    date: pd.Timestamp,
    window: int = WINDOW,
    min_obs: int = MIN_OBS,
    ridge: float = 0.0,
) -> tuple[pd.DataFrame, pd.Series]:
    """Exposure rows (``factors`` columns) and specific variances of every ETF in ``etf_ret`` using
    the ``window`` factor-return sessions ending at ``date``.  An ETF with fewer than ``min_obs``
    valid sessions in the window is omitted."""
    pos = int(fr.index.searchsorted(pd.Timestamp(date), "right"))
    win = fr.iloc[max(pos - window, 0) : pos]
    f_mkt = win[MARKET].to_numpy("float64")
    f_g = win[list(groups)].to_numpy("float64")
    f_s = win[list(styles)].to_numpy("float64")
    ok_f = np.isfinite(f_g).all(1) & np.isfinite(f_s).all(1) & np.isfinite(f_mkt)
    rows: dict[str, np.ndarray] = {}
    dvar: dict[str, float] = {}
    for sym in etf_ret.columns:
        y = etf_ret[sym].reindex(win.index).to_numpy("float64")
        ok = ok_f & np.isfinite(y)
        if ok.sum() < min_obs:
            continue
        bg, bs, bm, sv = fit_etf_loadings(y[ok], f_mkt[ok], f_g[ok], f_s[ok], ridge)
        x = pd.Series(0.0, index=list(factors))
        x[MARKET] = bm
        x[list(groups)] = bg
        x[list(styles)] = bs
        rows[sym] = x.to_numpy()
        dvar[sym] = max(sv, SPEC_VAR_FLOOR)
    x_df = pd.DataFrame.from_dict(rows, orient="index", columns=list(factors))
    return x_df, pd.Series(dvar, dtype="float64", name="spec_var")


def _cache_key(base: Path, window: int, ridge: float) -> str:
    h = hashlib.sha256()
    for f in sorted(base.glob("factor_returns_*.parquet")):
        st = f.stat()
        h.update(f"{f.name}:{st.st_size}:{int(st.st_mtime)}".encode())
    h.update(f"w{window}:r{ridge}".encode())
    return h.hexdigest()[:16]


class ETFRisk:
    """Rolling-regression exposures of the hedge ETFs at the risk model's saved dates, with a disk
    cache.  ``at(date) -> (X, D)``: ``X`` (ETFs x factors, ``risk_model.factors`` order), ``D``
    daily specific variance.  A date between saved dates uses the latest saved date (like
    :class:`RiskModel`).  Call :meth:`flush` to persist newly computed dates."""

    def __init__(
        self,
        risk_model: RiskModel,
        etf_daily: pd.DataFrame | None = None,
        symbols: Sequence[str] = HEDGE_ETF_SYMBOLS,
        cache_dir: Path | str | None = ETF_RISK_DIR,
        window: int = WINDOW,
        ridge: float = 0.0,
    ) -> None:
        self.rm = risk_model
        self.window = window
        self.ridge = ridge
        etf = etf_daily if etf_daily is not None else load_etf_daily()
        self.symbols = [s for s in symbols if s in set(etf["symbol"])]
        self.etf_daily = etf[etf["symbol"].isin(self.symbols)]
        self.fr = load_factor_returns(risk_model.base)
        close = (
            self.etf_daily.pivot(index="trade_date", columns="symbol", values="close")
            .sort_index()
            .reindex(self.fr.index)
        )
        self.etf_ret = close / close.shift(1) - 1.0
        vol = (
            self.etf_daily.pivot(index="trade_date", columns="symbol", values="volume")
            .sort_index()
            .astype("float64")
        )
        cl_all = self.etf_daily.pivot(index="trade_date", columns="symbol", values="close")
        self._adv = (vol * cl_all.reindex(vol.index)).rolling(21, min_periods=10).mean()
        self._close_all = cl_all.sort_index()
        self._mem: dict[pd.Timestamp, tuple[pd.DataFrame, pd.Series]] = {}
        self._dirty = False
        self.cache_dir = None if cache_dir is None else Path(cache_dir)
        self._key = _cache_key(Path(risk_model.base), window, ridge)
        self._disk = self._load_disk()

    # -- disk cache -----------------------------------------------------------

    @property
    def _path(self) -> Path | None:
        return None if self.cache_dir is None else self.cache_dir / "etf_exposures.parquet"

    def _load_disk(self) -> pd.DataFrame | None:
        p = self._path
        meta = None if self.cache_dir is None else self.cache_dir / "etf_exposures.meta.json"
        if p is None or meta is None or not p.exists() or not meta.exists():
            return None
        try:
            if json.loads(meta.read_text()).get("key") != self._key:
                return None
            return pd.read_parquet(p)
        except Exception:
            return None

    def flush(self) -> None:
        """Write every in-memory date (merged with the disk cache) to the cache file."""
        p = self._path
        if p is None or not self._dirty:
            return
        frames = []
        for d, (x, dv) in sorted(self._mem.items()):
            f = x.copy()
            f.insert(0, "spec_var", dv.reindex(f.index))
            f.insert(0, "symbol", f.index)
            f.insert(0, "trade_date", d)
            frames.append(f.reset_index(drop=True))
        new = pd.concat(frames, ignore_index=True)
        if self._disk is not None:
            keep = self._disk[~self._disk["trade_date"].isin(set(new["trade_date"]))]
            new = pd.concat([keep, new], ignore_index=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        new.to_parquet(p, index=False)
        (p.parent / "etf_exposures.meta.json").write_text(
            json.dumps({"key": self._key, "window": self.window, "ridge": self.ridge})
        )
        self._disk = new
        self._dirty = False

    # -- access ---------------------------------------------------------------

    def at(self, date: pd.Timestamp | str) -> tuple[pd.DataFrame, pd.Series]:
        d = self.rm.resolve(date)
        if d in self._mem:
            return self._mem[d]
        if self._disk is not None:
            sub = self._disk[self._disk["trade_date"] == d]
            if len(sub):
                x = sub.set_index("symbol")[self.rm.factors]
                dv = sub.set_index("symbol")["spec_var"]
                self._mem[d] = (x, dv)
                return x, dv
        x, dv = regress_etfs(
            self.fr,
            self.etf_ret,
            self.rm.groups,
            STYLES,
            self.rm.factors,
            d,
            self.window,
            ridge=self.ridge,
        )
        self._mem[d] = (x, dv)
        self._dirty = True
        return x, dv

    def adv(self, date: pd.Timestamp | str) -> pd.Series:
        """21-session mean dollar volume of each ETF as of ``date`` (decision close)."""
        pos = int(self._adv.index.searchsorted(pd.Timestamp(date), "right")) - 1
        return self._adv.iloc[pos] if pos >= 0 else pd.Series(dtype="float64")

    def price(self, date: pd.Timestamp | str) -> pd.Series:
        pos = int(self._close_all.index.searchsorted(pd.Timestamp(date), "right")) - 1
        return self._close_all.iloc[pos] if pos >= 0 else pd.Series(dtype="float64")
