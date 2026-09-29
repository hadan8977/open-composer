"""T-20260928-42 batch: `scripts/screen_batch.py --batch h20260928_42_opex_week
--iteration h20260928_42_opex_week`.

Option-expiration-week calendar effect (`dir:option_expiration_week_calendar_
effect`): long a large-cap/index ETF only during the week containing the
month's third Friday (standard monthly option expiration), cash otherwise.
Mechanism (Stivers & Sun 2013, J. Banking & Finance; summarized by Quantpedia
at https://quantpedia.com/strategies/option-expiration-week-effect): covered
call writers roll expiring positions on the third Friday and, especially, the
following Monday (Garcia-Ares & Muravyev 2025, FMA working paper), and option
market-maker delta-hedge rebalancing over the week reduces short-stock hedge
positions, providing a tailwind to the underlying.

20 candidates, `CANDIDATES: list[lane.ScreenCandidate]` (this module DOES
import `screen_lane`, following `h20260928_18_vix_putw.py`'s pattern, since
all rules share the same calendar-anchored-daily construction and no
per-rule helper needs to be hidden from the lane):

  8 primary  `OPEX_{SPY,QQQ,DIA,IWM}_{WEEK,WEEKMON}`
  12 placebo `PLACEBO_W{1,2,4}_{SPY,QQQ,DIA,IWM}` (anchored to the 1st, 2nd,
             or 4th Friday's week instead of the 3rd -- internal falsification
             controls, not eligible for keep tiers; see candidate-manifest.json)

Rule (all candidates, `freq="D"` with a `signal_dates_fn` restricting
evaluation to a handful of dates a year, per `screen_lane.py`'s calendar-
anchored-rule convention):

  entry signal date := the last KNOWN trading day strictly before the Monday
    of the target week (WEEK/WEEKMON: the week containing the month's 3rd
    Friday; PLACEBO_Wn: the week containing the month's nth Friday), at that
    day's close -> next trading day's open buy (weight 1.0, single ticker).
  exit signal date (WEEK, PLACEBO_Wn) := the last KNOWN trading day within the
    target week itself, at that day's close -> next trading day's open sell
    (weight 0.0, i.e. `{}`, all to SHY per the lane's own remainder rule).
  exit signal date (WEEKMON) := the first KNOWN trading day of the week AFTER
    the target week, at that day's close -> next trading day's open sell.

"Known trading day" means a session present in `close.index` at or before
`asof` is never used to decide the CURRENT month's dates; only the exchange's
own trading-day calendar (which sessions exist, not their prices) is used to
locate the 3rd/nth Friday's week and its trading days, the same convention
already used and justified by `h20260928_05_batch2.py`'s `_is_month_end`
(the NYSE calendar is public well in advance -- this is not a price leak).
`weights_fn` here never reads a single price value, only `close.columns`
(ticker presence) and `close.index` (calendar), so there is no look-ahead by
construction, stronger than the usual `close.loc[:asof]` convention.

Cost/fill convention is the frozen contract (close signal -> next open fill,
10bp/20bp per side) applied unedited by the lane; note this differs from
Quantpedia's own "Friday close to Friday close" holding period (we enter at
the following trading day's OPEN, one session later, and for WEEK exit at the
next session's open after the expiration week's own last close) -- a fixed
contract constraint, not a rule change made to help this candidate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import screen_lane as lane  # noqa: E402

PRIMARY_TICKERS: tuple[str, ...] = ("SPY", "QQQ", "DIA", "IWM")


def _months_in_index(index: pd.DatetimeIndex) -> list[tuple[int, int]]:
    return sorted({(int(y), int(m)) for y, m in zip(index.year, index.month, strict=True)})


def _nth_friday(year: int, month: int, n: int) -> pd.Timestamp | None:
    start = pd.Timestamp(year=year, month=month, day=1)
    end = start + pd.offsets.MonthEnd(0)
    fridays = pd.date_range(start, end, freq="W-FRI")
    return fridays[n - 1] if len(fridays) >= n else None


def _week_monday(friday: pd.Timestamp) -> pd.Timestamp:
    """Monday of the calendar week containing `friday` (a Friday: weekday()==4)."""
    return friday - pd.Timedelta(days=friday.weekday())


def _nearest_trading_day_before(index: pd.DatetimeIndex, when: pd.Timestamp) -> pd.Timestamp | None:
    candidates = index[index < when]
    return candidates[-1] if len(candidates) else None


def _trading_days_in_range(
    index: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DatetimeIndex:
    return index[(index >= start) & (index <= end)]


def entry_dates_for_friday(index: pd.DatetimeIndex, n: int) -> list[pd.Timestamp]:
    """Last known trading day strictly before the Monday of the week
    containing the month's n-th Friday, for every month present in `index`.
    Months with no n-th Friday (e.g. n=4 in a 4-Friday-less month) are
    skipped."""
    out: list[pd.Timestamp] = []
    for y, m in _months_in_index(index):
        friN = _nth_friday(y, m, n)
        if friN is None:
            continue
        wk_mon = _week_monday(friN)
        before = _nearest_trading_day_before(index, wk_mon)
        if before is not None:
            out.append(before)
    return sorted(set(out))


def exit_dates_same_week(index: pd.DatetimeIndex, n: int) -> list[pd.Timestamp]:
    """Last known trading day within the target week itself (Monday..Sunday
    calendar range) -- exit signal for WEEK and PLACEBO_Wn variants."""
    out: list[pd.Timestamp] = []
    for y, m in _months_in_index(index):
        friN = _nth_friday(y, m, n)
        if friN is None:
            continue
        wk_mon = _week_monday(friN)
        week_days = _trading_days_in_range(index, wk_mon, wk_mon + pd.Timedelta(days=6))
        if len(week_days):
            out.append(week_days[-1])
    return sorted(set(out))


def exit_dates_following_week(index: pd.DatetimeIndex, n: int) -> list[pd.Timestamp]:
    """First known trading day of the week AFTER the target week -- exit
    signal for the WEEKMON variant (n=3 only, used by OPEX_*_WEEKMON)."""
    out: list[pd.Timestamp] = []
    for y, m in _months_in_index(index):
        friN = _nth_friday(y, m, n)
        if friN is None:
            continue
        wk_mon = _week_monday(friN)
        next_mon = wk_mon + pd.Timedelta(days=7)
        next_week_days = _trading_days_in_range(index, next_mon, next_mon + pd.Timedelta(days=6))
        if len(next_week_days):
            out.append(next_week_days[0])
    return sorted(set(out))


def _make_entry_only_weights_fn(symbol: str, n: int):
    """True for every WEEK/WEEKMON/PLACEBO variant: `weights_fn` is only ever
    evaluated at the entry or exit signal dates it supplied via
    `signal_dates_fn`; at an entry date it returns full weight, at an exit
    date (never in the entry set) it returns `{}` (all to SHY, the lane's own
    remainder convention). Reads only `close.columns` and `close.index` --
    never a price value."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if symbol not in close.columns:
            return {}
        if asof in set(entry_dates_for_friday(close.index, n)):
            return {symbol: 1.0}
        return {}

    fn.__name__ = f"w_opex_{symbol.lower()}_n{n}"
    return fn


def _make_week_signal_dates_fn(n: int):
    def fn(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
        return sorted(set(entry_dates_for_friday(index, n)) | set(exit_dates_same_week(index, n)))

    return fn


def _make_weekmon_signal_dates_fn(n: int):
    def fn(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
        return sorted(
            set(entry_dates_for_friday(index, n)) | set(exit_dates_following_week(index, n))
        )

    return fn


CANDIDATES: list[lane.ScreenCandidate] = []

for _sym in PRIMARY_TICKERS:
    CANDIDATES.append(
        lane.ScreenCandidate(
            id=f"OPEX_{_sym}_WEEK",
            name=f"Option-expiration week (3rd-Friday week) {_sym}, exit same week",
            source_card="stivers_sun_2013_option_expiration_week_effect",
            universe=(_sym,),
            freq="D",
            weights_fn=_make_entry_only_weights_fn(_sym, 3),
            signal_dates_fn=_make_week_signal_dates_fn(3),
        )
    )
    CANDIDATES.append(
        lane.ScreenCandidate(
            id=f"OPEX_{_sym}_WEEKMON",
            name=f"Option-expiration week (3rd-Friday week) {_sym}, exit following Monday",
            source_card="garcia_ares_muravyev_2025_rollover_day",
            universe=(_sym,),
            freq="D",
            weights_fn=_make_entry_only_weights_fn(_sym, 3),
            signal_dates_fn=_make_weekmon_signal_dates_fn(3),
        )
    )

for _n in (1, 2, 4):
    for _sym in PRIMARY_TICKERS:
        CANDIDATES.append(
            lane.ScreenCandidate(
                id=f"PLACEBO_W{_n}_{_sym}",
                name=f"Placebo: {_n}th-Friday week {_sym} (not opex week), exit same week",
                source_card="opex_week_internal_placebo_non_expiration_weeks",
                universe=(_sym,),
                freq="D",
                weights_fn=_make_entry_only_weights_fn(_sym, _n),
                signal_dates_fn=_make_week_signal_dates_fn(_n),
            )
        )

assert len(CANDIDATES) == 20, f"expected 20 candidates, got {len(CANDIDATES)}"
assert len({c.id for c in CANDIDATES}) == 20, "duplicate candidate ids"
