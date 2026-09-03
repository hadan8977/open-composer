"""Daily benchmark return series on the kernel's plain-calendar-date index.

Every kernel script that builds its own return series from
``dataset.dates``-style plain "YYYY-MM-DD" strings (rather than SIP's native
tz-aware intraday timestamps) needs its benchmark series indexed the same
way, or ``pandas.Series.reindex`` silently returns all-missing rows for a day
that is, in fact, present -- the two representations of "2026-08-24" do not
compare equal when one carries a UTC time-of-day and the other does not.

This exact mismatch was independently discovered and fixed twice
(``scripts/evaluate_champion_route_sip.py`` for the router pipeline's
``dataset.dates``, then again in
``open_composer.research.kernel.mechanisms.intraday_momentum_etf`` for the
intraday-momentum mechanism's own per-session index) before being extracted
here. Use this function for any new kernel script's benchmark series instead
of re-deriving the fix a third time.
"""

from __future__ import annotations

import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars


def daily_returns_on_naive_dates(
    symbol: str,
    *,
    start: str | None = None,
    end: str | None = None,
) -> pd.Series:
    """Daily close-to-close returns for ``symbol``, indexed by naive midnight
    Timestamp on the calendar date (SIP's tz-aware time-of-day collapsed
    away), matching ``dataset.dates``-style plain-date conventions elsewhere
    in the kernel.
    """
    frame = load_sip_bars(symbol, frequency="daily", start=start, end=end)
    rows = frame.loc[frame["symbol"] == symbol].copy()
    rows["timestamp"] = pd.to_datetime(rows["timestamp"], utc=True)
    rows = rows.sort_values("timestamp")
    rows["date"] = rows["timestamp"].dt.date.astype(str)
    rows = rows.drop_duplicates("date", keep="last")
    prices = pd.Series(
        pd.to_numeric(rows["close"], errors="raise").to_numpy(),
        index=pd.DatetimeIndex(rows["date"]),
        name=symbol,
    )
    returns = prices.pct_change(fill_method=None).dropna()
    returns.name = symbol
    return returns
