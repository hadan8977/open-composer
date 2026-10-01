"""Readers for the equity-book research panel (built by ``scripts/build_equity_book_panel.py``).

Two kinds of data, deliberately separate:

* :class:`PricePanel` -- wide ``open`` / ``close`` matrices (dates x symbols, float64) of *every*
  panel symbol after price hygiene plus the hedge ETFs.  This is all the backtest engine
  (:mod:`open_composer.research.equity_book.backtest`) needs.  A symbol with no price row from some
  date on is a delisting; the panel never drops a name because it left the top-4000 ADV cohort.
* :class:`PanelAttributes` -- the long attribute panel ``panel/<year>.parquet`` (universe flags,
  mcap, industry, ADV, beta, ...) read year by year.  Signals, the risk model and cost models use
  it; nothing here loads all years at once.

Layout (``data/research/equity_book/``)::

    prices/<year>.parquet     trade_date, symbol, open, close
    panel/<year>.parquet      see ``PANEL_COLUMNS``
    etf_daily.parquet         trade_date, symbol, open, close, volume
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DIR = ROOT / "data/research/equity_book"

PANEL_COLUMNS = [
    "trade_date",
    "symbol",
    "open",
    "close",
    "dollar_adv_21",
    "adv_rank",
    "mcap",
    "mcap_source",
    "in_u3000",
    "in_p1000",
    "ff48",
    "ff48_verified",
    "beta_252_spy",
    "idio_vol_63",
    "vol_21",
    "is_tradeable",
]
HEDGE_ETFS = (
    "SPY",
    "IWM",
    "IJR",
    "SGOV",
    "BIL",
    "SHY",
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


@dataclass
class PricePanel:
    """Wide open/close matrices.  ``open``/``close`` are ``(T, N)`` float64 with NaN for a
    missing price; ``dates`` is the session calendar, ``symbols`` the column labels."""

    dates: pd.DatetimeIndex
    symbols: pd.Index
    open: np.ndarray
    close: np.ndarray

    def __post_init__(self) -> None:
        if self.open.shape != self.close.shape or self.open.shape != (
            len(self.dates),
            len(self.symbols),
        ):
            raise ValueError("open/close must be (len(dates), len(symbols))")
        self.dates = pd.DatetimeIndex(self.dates)
        self.symbols = pd.Index(self.symbols)
        self._col = {s: j for j, s in enumerate(self.symbols)}

    # -- constructors ------------------------------------------------------

    @classmethod
    def from_frames(cls, open_: pd.DataFrame, close: pd.DataFrame) -> PricePanel:
        """From two wide DataFrames (index = dates, columns = symbols)."""
        cols = close.columns.union(open_.columns)
        idx = close.index.union(open_.index)
        o = open_.reindex(index=idx, columns=cols)
        c = close.reindex(index=idx, columns=cols)
        return cls(pd.DatetimeIndex(idx), cols, o.to_numpy("float64"), c.to_numpy("float64"))

    @classmethod
    def from_long(cls, df: pd.DataFrame, dates: pd.DatetimeIndex | None = None) -> PricePanel:
        """From a long frame with columns ``trade_date, symbol, open, close``.  ``dates`` fixes the
        calendar (default: the union of the dates in ``df``)."""
        df = df.drop_duplicates(["trade_date", "symbol"], keep="last")
        o = df.pivot(index="trade_date", columns="symbol", values="open")
        c = df.pivot(index="trade_date", columns="symbol", values="close")
        if dates is not None:
            o, c = o.reindex(dates), c.reindex(dates)
        return cls.from_frames(o, c)

    @classmethod
    def from_dir(
        cls,
        base_dir: Path | str = DEFAULT_DIR,
        *,
        symbols: Iterable[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        include_etfs: bool = True,
        load_open: bool = True,
    ) -> PricePanel:
        """Read ``prices/<year>.parquet`` (+ ``etf_daily.parquet``) with duckdb.  Calendar: the
        stock-panel calendar (sessions with >= 500 names); ETF rows on other dates are dropped.
        ``symbols`` restricts the stock columns (ETFs are always kept when ``include_etfs``).
        ``load_open=False`` keeps ``open`` as a zero-memory all-NaN view."""
        import duckdb

        base = Path(base_dir)
        con = duckdb.connect()
        con.execute("SET memory_limit='700MB'")
        con.execute("SET threads=2")
        files = sorted((base / "prices").glob("*.parquet"))
        if not files:
            raise FileNotFoundError(f"no price files under {base / 'prices'}")
        wanted = None if symbols is None else set(symbols)
        if wanted is not None and include_etfs:
            wanted |= set(HEDGE_ETFS)
        date_where = []
        if start is not None:
            date_where.append(f"trade_date >= TIMESTAMP '{start}'")
        if end is not None:
            date_where.append(f"trade_date <= TIMESTAMP '{end}'")
        where = list(date_where)
        if wanted is not None:
            con.register("wanted", pd.DataFrame({"symbol": sorted(wanted)}))
            where.append("symbol in (select symbol from wanted)")
        clause = ("where " + " and ".join(where)) if where else ""
        date_clause = ("where " + " and ".join(date_where)) if date_where else ""
        globs = ", ".join(f"'{f}'" for f in files)
        cal = pd.DatetimeIndex(  # the session calendar never depends on the symbol filter
            con.execute(
                f"select distinct trade_date from read_parquet([{globs}]) {date_clause} order by 1"
            ).df()["trade_date"]
        )
        syms = con.execute(
            f"select distinct symbol from read_parquet([{globs}]) {clause} order by 1"
        ).df()["symbol"]
        etf_path = base / "etf_daily.parquet"
        use_etf = include_etfs and etf_path.exists()
        if use_etf:
            etf_syms = con.execute(
                f"select distinct symbol from read_parquet('{etf_path}') {clause}"
            ).df()["symbol"]
            syms = pd.concat([syms, etf_syms]).drop_duplicates().sort_values()
        cols = pd.Index(syms.astype(str).tolist())
        shape = (len(cal), len(cols))
        # ``load_open=False``: a read-only all-NaN view (no memory); for close-only consumers
        o = np.full(shape, np.nan) if load_open else np.broadcast_to(np.float64("nan"), shape)
        c = np.full(shape, np.nan)

        def fill(df: pd.DataFrame) -> None:
            r = cal.get_indexer(pd.DatetimeIndex(df["trade_date"]))
            k = cols.get_indexer(df["symbol"].astype(str))
            ok = (r >= 0) & (k >= 0)
            if load_open:
                o[r[ok], k[ok]] = df["open"].to_numpy("float64")[ok]
            c[r[ok], k[ok]] = df["close"].to_numpy("float64")[ok]

        sources = [str(f) for f in files] + ([str(etf_path)] if use_etf else [])
        for f in sources:
            fill(
                con.execute(
                    f"select trade_date, symbol, open, close from read_parquet('{f}') {clause}"
                ).df()
            )
        return cls(cal, cols, o, c)

    # -- access ------------------------------------------------------------

    def col(self, symbol: str) -> int:
        return self._col[symbol]

    def has(self, symbol: str) -> bool:
        return symbol in self._col

    def frame(self, field: str = "close") -> pd.DataFrame:
        arr = self.close if field == "close" else self.open
        return pd.DataFrame(arr, index=self.dates, columns=self.symbols)

    def subset(self, symbols: Sequence[str]) -> PricePanel:
        keep = [self._col[s] for s in symbols if s in self._col]
        return PricePanel(
            self.dates, self.symbols[keep], self.open[:, keep].copy(), self.close[:, keep].copy()
        )


class PanelAttributes:
    """Lazy reader of ``panel/<year>.parquet``.  ``at(date)`` returns the cross-section of one
    session indexed by symbol; ``year(y)`` returns a whole year (use the ``columns`` filter)."""

    def __init__(self, base_dir: Path | str = DEFAULT_DIR) -> None:
        self.dir = Path(base_dir) / "panel"
        self._cache: dict[int, pd.DataFrame] = {}

    def year(self, year: int, columns: Sequence[str] | None = None) -> pd.DataFrame:
        cols = None if columns is None else sorted(set(columns) | {"trade_date", "symbol"})
        return pd.read_parquet(self.dir / f"{year}.parquet", columns=cols)

    def at(self, date: pd.Timestamp | str) -> pd.DataFrame:
        d = pd.Timestamp(date)
        if d.year not in self._cache:
            self._cache.clear()  # one year in memory at a time
            self._cache[d.year] = self.year(d.year)
        yr = self._cache[d.year]
        return yr[yr["trade_date"] == d].set_index("symbol")

    def trade_attrs(self, decision_date: pd.Timestamp, symbols: Sequence[str]) -> pd.DataFrame:
        """``dollar_adv_21``, ``vol_21``, ``adv_rank`` at ``decision_date`` for ``symbols`` (NaN
        rows for symbols not in the panel); a ready ``BookConfig.trade_attrs`` hook for the cost
        model."""
        cs = self.at(decision_date)
        cols = [c for c in ("dollar_adv_21", "vol_21", "adv_rank", "close") if c in cs.columns]
        out = cs.reindex(list(symbols))[cols]
        return out.rename(columns={"close": "prior_close"})
