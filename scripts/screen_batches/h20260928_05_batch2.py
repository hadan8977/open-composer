"""H-20260928-05 registry triage, batch 2: seven long-only published-rule
replications for `scripts/screen_batch.py --batch h20260928_05_batch2
--iteration h20260928_05_registry_etf_batch2`.

Deliberately does NOT import `screen_lane` (per the iteration brief): every
function here is a standalone pure `fn(close: pd.DataFrame, asof: pd.Timestamp)
-> dict[str, float]` that only reads `close.loc[:asof]` (or, for the two
calendar-boundary helpers, the full `close.index` -- exchange trading-day
structure, never future prices; see the note on `_is_month_end` below).
`SPECS` is a list of plain dicts (`id, name, source_card, universe, freq, fn`,
plus `signal_dates_fn` for the two calendar-anchored daily rules), matched by
id to `reports/research/iterations/h20260928_05_registry_etf_batch2/candidate-
manifest.json`. No return is computed by this module and it is not run as
part of this preregistration round.

Candidates
----------
HFEA_UPRO_TMF          fixed 55% UPRO / 45% TMF (Hedgefundie's Excellent
                        Adventure), monthly-approximated rebalance of the
                        published quarterly rule (scripts/screen_lane.py only
                        supports M/W/D -- a documented, conservative
                        deviation: monthly rebalance means MORE turnover/cost
                        than the original, never less).
TOM_SPY                turn-of-month: long SPY from the close of the last
                        trading day of the month through the close of the
                        4th trading day of the next month, cash otherwise
                        (etftrends.com / hulltactical.com construction).
EOM_REVERSAL_SPY        end-of-month reversal: long SPY next month only if
                        this month's return from its 4th Friday's close to
                        its own month-end close was negative (Graziani 2024).
FRONT_RUN_SECTOR_TOP2   Quantpedia front-running sector seasonality: rank the
                        9 original Select Sector SPDRs (XLB/XLE/XLF/XLI/XLK/
                        XLP/XLU/XLV/XLY) by their return in calendar month
                        (holding_month + 1) one year before the holding
                        year, hold the top 2 equal-weight.
FOMC_DRIFT_SPY          pre-FOMC announcement drift on SPY: long from the
                        close of the last trading day before a scheduled
                        FOMC meeting through the close of the meeting's
                        final day, cash otherwise (Lucca & Moench 2015 via
                        quantseeker.com's replication).
FOMC_DRIFT_TQQQ         same signal dates, leveraged leg (quantseeker.com
                        also reports TQQQ/SPXL).
XYLD_COVERED_CALL_PROXY buy-and-hold XYLD (Global X S&P 500 Covered Call
                        ETF, inception 2013-06-21) as an HONEST PROXY for the
                        registry's covered-call CEF direction: the fund
                        actually studied by the cited 2008 paper (ticker BEP,
                        "S&P 500 Covered Call Fund Inc.") liquidated on
                        2010-02-02 and is not tradable today.

FOMC meeting dates are copied verbatim from the Federal Reserve's calendar
pages (not inferred from price action):
  - 2021-2026: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
  - 2015: https://www.federalreserve.gov/monetarypolicy/fomchistorical2015.htm
  - 2016: https://www.federalreserve.gov/monetarypolicy/fomchistorical2016.htm
  - 2017: https://www.federalreserve.gov/monetarypolicy/fomchistorical2017.htm
  - 2018: https://www.federalreserve.gov/monetarypolicy/fomchistorical2018.htm
  - 2019: https://www.federalreserve.gov/monetarypolicy/fomchistorical2019.htm
  - 2020: https://www.federalreserve.gov/monetarypolicy/fomchistorical2020.htm
Only the 8 REGULARLY SCHEDULED meetings per year are included. 2019-10-04
(unscheduled conference call) and the 2020 emergency/notation-vote actions
(2020-03-02, 03-15, 03-19, 03-23, 03-31, 08-27) are excluded; 2020's regular
March meeting was itself cancelled/absorbed by the emergency actions, so 2020
has 7 scheduled meetings instead of 8.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

SECTOR_ETFS: tuple[str, ...] = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")

# (start, end) calendar dates of every scheduled FOMC meeting, 2015-09-16
# through 2026-09-16 -- see the module docstring for the source URLs.
FOMC_MEETINGS: tuple[tuple[str, str], ...] = (
    ("2015-01-27", "2015-01-28"),
    ("2015-03-17", "2015-03-18"),
    ("2015-04-28", "2015-04-29"),
    ("2015-06-16", "2015-06-17"),
    ("2015-07-28", "2015-07-29"),
    ("2015-09-16", "2015-09-17"),
    ("2015-10-27", "2015-10-28"),
    ("2015-12-15", "2015-12-16"),
    ("2016-01-26", "2016-01-27"),
    ("2016-03-15", "2016-03-16"),
    ("2016-04-26", "2016-04-27"),
    ("2016-06-14", "2016-06-15"),
    ("2016-07-26", "2016-07-27"),
    ("2016-09-20", "2016-09-21"),
    ("2016-11-01", "2016-11-02"),
    ("2016-12-13", "2016-12-14"),
    ("2017-01-31", "2017-02-01"),
    ("2017-03-14", "2017-03-15"),
    ("2017-05-02", "2017-05-03"),
    ("2017-06-13", "2017-06-14"),
    ("2017-07-25", "2017-07-26"),
    ("2017-09-19", "2017-09-20"),
    ("2017-10-31", "2017-11-01"),
    ("2017-12-12", "2017-12-13"),
    ("2018-01-30", "2018-01-31"),
    ("2018-03-20", "2018-03-21"),
    ("2018-05-01", "2018-05-02"),
    ("2018-06-12", "2018-06-13"),
    ("2018-07-31", "2018-08-01"),
    ("2018-09-25", "2018-09-26"),
    ("2018-11-07", "2018-11-08"),
    ("2018-12-18", "2018-12-19"),
    ("2019-01-29", "2019-01-30"),
    ("2019-03-19", "2019-03-20"),
    ("2019-04-30", "2019-05-01"),
    ("2019-06-18", "2019-06-19"),
    ("2019-07-30", "2019-07-31"),
    ("2019-09-17", "2019-09-18"),
    ("2019-10-29", "2019-10-30"),
    ("2019-12-10", "2019-12-11"),
    ("2020-01-28", "2020-01-29"),
    ("2020-04-28", "2020-04-29"),
    ("2020-06-09", "2020-06-10"),
    ("2020-07-28", "2020-07-29"),
    ("2020-09-15", "2020-09-16"),
    ("2020-11-04", "2020-11-05"),
    ("2020-12-15", "2020-12-16"),
    ("2021-01-26", "2021-01-27"),
    ("2021-03-16", "2021-03-17"),
    ("2021-04-27", "2021-04-28"),
    ("2021-06-15", "2021-06-16"),
    ("2021-07-27", "2021-07-28"),
    ("2021-09-21", "2021-09-22"),
    ("2021-11-02", "2021-11-03"),
    ("2021-12-14", "2021-12-15"),
    ("2022-01-25", "2022-01-26"),
    ("2022-03-15", "2022-03-16"),
    ("2022-05-03", "2022-05-04"),
    ("2022-06-14", "2022-06-15"),
    ("2022-07-26", "2022-07-27"),
    ("2022-09-20", "2022-09-21"),
    ("2022-11-01", "2022-11-02"),
    ("2022-12-13", "2022-12-14"),
    ("2023-01-31", "2023-02-01"),
    ("2023-03-21", "2023-03-22"),
    ("2023-05-02", "2023-05-03"),
    ("2023-06-13", "2023-06-14"),
    ("2023-07-25", "2023-07-26"),
    ("2023-09-19", "2023-09-20"),
    ("2023-10-31", "2023-11-01"),
    ("2023-12-12", "2023-12-13"),
    ("2024-01-30", "2024-01-31"),
    ("2024-03-19", "2024-03-20"),
    ("2024-04-30", "2024-05-01"),
    ("2024-06-11", "2024-06-12"),
    ("2024-07-30", "2024-07-31"),
    ("2024-09-17", "2024-09-18"),
    ("2024-11-06", "2024-11-07"),
    ("2024-12-17", "2024-12-18"),
    ("2025-01-28", "2025-01-29"),
    ("2025-03-18", "2025-03-19"),
    ("2025-05-06", "2025-05-07"),
    ("2025-06-17", "2025-06-18"),
    ("2025-07-29", "2025-07-30"),
    ("2025-09-16", "2025-09-17"),
    ("2025-10-28", "2025-10-29"),
    ("2025-12-09", "2025-12-10"),
    ("2026-01-27", "2026-01-28"),
    ("2026-03-17", "2026-03-18"),
    ("2026-04-28", "2026-04-29"),
    ("2026-06-16", "2026-06-17"),
    ("2026-07-28", "2026-07-29"),
    ("2026-09-15", "2026-09-16"),
)


def _is_month_end(index: pd.DatetimeIndex, asof: pd.Timestamp) -> bool:
    """True iff `asof` is the last KNOWN trading day of its calendar month in
    the full trading-day index. Uses `index` (which may extend past `asof`)
    only for the exchange's own trading-day calendar, never for price values
    -- the NYSE calendar is public knowledge well in advance, so this does
    not leak future returns. Appending future rows for LATER months never
    changes this for an `asof` in an earlier, already-closed month."""
    month_days = index[(index.year == asof.year) & (index.month == asof.month)]
    return len(month_days) > 0 and month_days[-1] == asof


def _is_nth_trading_day(index: pd.DatetimeIndex, asof: pd.Timestamp, n: int) -> bool:
    month_days = index[(index.year == asof.year) & (index.month == asof.month)]
    return len(month_days) >= n and month_days[n - 1] == asof


def _nearest_trading_day_at_or_before(
    index: pd.DatetimeIndex, when: pd.Timestamp
) -> pd.Timestamp | None:
    candidates = index[index <= when]
    return candidates[-1] if len(candidates) else None


def _nearest_trading_day_before(index: pd.DatetimeIndex, when: pd.Timestamp) -> pd.Timestamp | None:
    candidates = index[index < when]
    return candidates[-1] if len(candidates) else None


# --------------------------------------------------------------------------
# HFEA_UPRO_TMF
# --------------------------------------------------------------------------


def w_hfea_upro_tmf(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    hist = close.loc[:asof]
    for sym in ("UPRO", "TMF"):
        if sym not in hist.columns or hist[sym].dropna().empty:
            return {}
    return {"UPRO": 0.55, "TMF": 0.45}


# --------------------------------------------------------------------------
# TOM_SPY
# --------------------------------------------------------------------------


def tom_signal_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    ser = pd.Series(index, index=index)
    out: list[pd.Timestamp] = []
    for _, group in ser.groupby([index.year, index.month]):
        out.append(group.iloc[-1])
        if len(group) >= 4:
            out.append(group.iloc[3])
    return sorted(out)


def w_tom_spy(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    if "SPY" not in close.columns:
        return {}
    if _is_month_end(close.index, asof):
        return {"SPY": 1.0}
    return {}


# --------------------------------------------------------------------------
# EOM_REVERSAL_SPY
# --------------------------------------------------------------------------


def _fourth_friday(year: int, month: int) -> pd.Timestamp | None:
    start = pd.Timestamp(year=year, month=month, day=1)
    end = start + pd.offsets.MonthEnd(0)
    fridays = pd.date_range(start, end, freq="W-FRI")
    return fridays[3] if len(fridays) >= 4 else None


def w_eom_reversal_spy(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    if "SPY" not in close.columns:
        return {}
    if not _is_month_end(close.index, asof):
        return {}
    hist = close.loc[:asof]
    fri = _fourth_friday(asof.year, asof.month)
    if fri is None:
        return {}
    fri_trading = _nearest_trading_day_at_or_before(hist.index, fri)
    if fri_trading is None or fri_trading >= asof:
        return {}
    p_fri = hist["SPY"].loc[fri_trading]
    p_end = hist["SPY"].loc[asof]
    if not np.isfinite(p_fri) or not np.isfinite(p_end) or p_fri <= 0:
        return {}
    eom_return = p_end / p_fri - 1.0
    return {"SPY": 1.0} if eom_return < 0 else {}


# --------------------------------------------------------------------------
# FRONT_RUN_SECTOR_TOP2
# --------------------------------------------------------------------------


def _holding_month_and_year(asof: pd.Timestamp) -> tuple[int, int]:
    if asof.month == 12:
        return 1, asof.year + 1
    return asof.month + 1, asof.year


def _score_window(holding_month: int, holding_year: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """'Last year's return, one calendar month after the holding month' --
    e.g. holding month = January (of year Y): base = January of year Y-1,
    score window = February of year Y-1 (etftrends/quantpedia's
    front-running construction: shift the true-seasonality ranking month one
    month earlier than it would naively fall)."""
    base = pd.Timestamp(year=holding_year - 1, month=holding_month, day=1)
    score_start = base + pd.DateOffset(months=1)
    score_end = score_start + pd.DateOffset(months=1) - pd.Timedelta(days=1)
    return score_start, score_end


def w_front_run_sector_top2(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    if not _is_month_end(close.index, asof):
        return {}
    hist = close.loc[:asof]
    holding_month, holding_year = _holding_month_and_year(asof)
    score_start, score_end = _score_window(holding_month, holding_year)
    d_start = _nearest_trading_day_at_or_before(hist.index, score_start)
    d_end = _nearest_trading_day_at_or_before(hist.index, score_end)
    if d_start is None or d_end is None or d_start >= d_end:
        return {}
    scores: dict[str, float] = {}
    for sym in SECTOR_ETFS:
        if sym not in hist.columns:
            continue
        p0 = hist[sym].loc[d_start]
        p1 = hist[sym].loc[d_end]
        if np.isfinite(p0) and np.isfinite(p1) and p0 > 0:
            scores[sym] = float(p1 / p0 - 1.0)
    if len(scores) < 2:
        return {}
    top2 = sorted(scores, key=lambda sym: scores[sym], reverse=True)[:2]
    return {sym: 0.5 for sym in top2}


# --------------------------------------------------------------------------
# FOMC_DRIFT_SPY / FOMC_DRIFT_TQQQ
# --------------------------------------------------------------------------


def fomc_entry_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    out = []
    for start, _end in FOMC_MEETINGS:
        before = _nearest_trading_day_before(index, pd.Timestamp(start))
        if before is not None:
            out.append(before)
    return out


def fomc_exit_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    out = []
    for _start, end in FOMC_MEETINGS:
        on_or_before = _nearest_trading_day_at_or_before(index, pd.Timestamp(end))
        if on_or_before is not None:
            out.append(on_or_before)
    return out


def fomc_signal_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    return sorted(set(fomc_entry_dates(index)) | set(fomc_exit_dates(index)))


def _make_fomc_weights_fn(symbol: str):
    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if symbol not in close.columns:
            return {}
        if asof in set(fomc_entry_dates(close.index)):
            return {symbol: 1.0}
        return {}

    fn.__name__ = f"w_fomc_drift_{symbol.lower()}"
    return fn


w_fomc_drift_spy = _make_fomc_weights_fn("SPY")
w_fomc_drift_tqqq = _make_fomc_weights_fn("TQQQ")


# --------------------------------------------------------------------------
# XYLD_COVERED_CALL_PROXY
# --------------------------------------------------------------------------


def w_xyld_covered_call_proxy(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    hist = close.loc[:asof]
    if "XYLD" not in hist.columns or hist["XYLD"].dropna().empty:
        return {}
    return {"XYLD": 1.0}


# --------------------------------------------------------------------------
# SPECS
# --------------------------------------------------------------------------


def month_end_signal_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Last trading day of every calendar month in `index`. EOM_REVERSAL_SPY
    and FRONT_RUN_SECTOR_TOP2 are calendar-anchored: they decide only at the
    month's last session, so they run as single-version "D" rules on these
    dates (interactive-session correction 2026-09-28, made before any valid
    result: declared "M", 20 of 21 rebalance offsets never fired and the
    median version was pure SHY)."""
    s = pd.Series(index, index=index)
    return list(s.groupby([index.year, index.month]).max())


SPECS: list[dict[str, object]] = [
    {
        "id": "HFEA_UPRO_TMF",
        "name": "HFEA: 55% UPRO / 45% TMF, monthly-approximated quarterly rebalance",
        "source_card": "hfea_bogleheads_upro_tmf_55_45_quarterly",
        "universe": ("UPRO", "TMF"),
        "freq": "M",
        "fn": w_hfea_upro_tmf,
    },
    {
        "id": "TOM_SPY",
        "name": "Turn-of-month SPY: month-end close through 4th trading day next month",
        "source_card": "hulltactical2024_turn_of_month_spy_captures_44pct",
        "universe": ("SPY",),
        "freq": "D",
        "fn": w_tom_spy,
        "signal_dates_fn": tom_signal_dates,
    },
    {
        "id": "EOM_REVERSAL_SPY",
        "name": "End-of-month reversal SPY: long next month iff 4th-Friday-to-EOM return < 0",
        "source_card": "graziani2024_end_of_month_reversal_ssrn",
        "universe": ("SPY",),
        "freq": "D",
        "signal_dates_fn": month_end_signal_dates,
        "fn": w_eom_reversal_spy,
    },
    {
        "id": "FRONT_RUN_SECTOR_TOP2",
        "name": "Front-running sector seasonality: top-2 of 9 sector SPDRs, lagged shifted score",
        "source_card": "quantpedia_archive_front_running_sector_seasonality",
        "universe": SECTOR_ETFS,
        "freq": "D",
        "signal_dates_fn": month_end_signal_dates,
        "fn": w_front_run_sector_top2,
    },
    {
        "id": "FOMC_DRIFT_SPY",
        "name": "Pre-FOMC announcement drift, SPY",
        "source_card": "quantseeker2025_pre_fomc_drift_alive_leveraged_etfs",
        "universe": ("SPY",),
        "freq": "D",
        "fn": w_fomc_drift_spy,
        "signal_dates_fn": fomc_signal_dates,
    },
    {
        "id": "FOMC_DRIFT_TQQQ",
        "name": "Pre-FOMC announcement drift, TQQQ (leveraged leg)",
        "source_card": "quantseeker2025_pre_fomc_drift_alive_leveraged_etfs",
        "universe": ("TQQQ",),
        "freq": "D",
        "fn": w_fomc_drift_tqqq,
        "signal_dates_fn": fomc_signal_dates,
    },
    {
        "id": "XYLD_COVERED_CALL_PROXY",
        "name": "Buy-and-hold XYLD: honest live proxy for the defunct BEP S&P 500 covered-call CEF",
        "source_card": "sec_edgar_bep_ncsr_liquidation_2010",
        "universe": ("XYLD",),
        "freq": "M",
        "fn": w_xyld_covered_call_proxy,
    },
]

# Sanity: every date used in FOMC_MEETINGS parses and start <= end.
for _start, _end in FOMC_MEETINGS:
    if date.fromisoformat(_start) > date.fromisoformat(_end):
        raise ValueError(f"FOMC meeting end before start: {_start}..{_end}")
