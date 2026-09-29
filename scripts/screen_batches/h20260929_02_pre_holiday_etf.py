"""T-20260929-02 batch: `scripts/screen_batch.py --batch
h20260929_02_pre_holiday_etf --iteration h20260929_02_pre_holiday_etf`.

Pre-holiday return premium (`dir:pre_holiday_effect_small_cap_tier`), per the
2026-09-29 02:1x UTC coordinator revision to the queue task (overrides the
original signal_card-based plan, which cannot answer "does holding pay off"
because signal_card's excess return is relative to the whole-market average
and this is a same-day, all-stocks calendar event that cancels out in that
relative framing): long a small-cap/micro-cap ETF (or, for the large-cap
control group, SPY/QQQ) only around the last trading day before an exchange
closure, cash otherwise. Mechanism: Ariel (1990) found pre-holiday-session
index returns 9-14x an average session's; a later out-of-sample replication
("The Pre-Holiday Premium of Ariel (1990) Has Largely Become A Small-Firm
Effect Out of Sample", https://exa.ai/library/publication/k47n5zm6fft, also
https://www.nowpublishers.com/article/Details/CFR-0111 -- abstract only, no
full text available this session) reports the premium surviving mainly in
small stocks through 1983-2019, with the large-cap premium "largely gone"
after 1990. This batch is the first local, direct test of that "small minus
large" pattern under this project's cost/fill contract.

Universe: 4 small/micro-cap ETFs {IWM, IJR, IWC, VB} (small-cap/micro-cap
tier, expected by the source to retain the premium) + 2 large-cap/index ETFs
{SPY, QQQ} (large-cap control, expected by the source to have lost it). All
6 are plain long-only US equity ETFs, full local SIP daily coverage
2016-01-04..2026-09-28 (checked before writing this module -- no missing
symbols expected).

Holiday-day construction (`pre_holiday_days`, below) uses ONLY the trading
calendar of `close.index` -- which sessions exist, never a price value --
exactly the convention `h20260928_42_opex_week.py`'s docstring already
justifies for locating the month's 3rd Friday: the NYSE holiday calendar is
public knowledge well in advance, so treating "will session S be followed by
a multi-day gap not explained by a weekend" as known at `asof` is not a price
leak, only a calendar-lookahead, and is explicitly assumed here (recorded in
`direction-review.json` and `candidate-manifest.json`). A trading day `d0` is
flagged as a pre-holiday day if the gap in calendar days to the NEXT trading
day `d1` exceeds the weekend-only gap implied by `d0`'s weekday (3 days after
a Friday, 1 day otherwise) -- this also picks up one-off ad hoc closures
(e.g. 2025-01-09, the national day of mourning), which are real, publicly
known closures, not data gaps (checked: SPY/QQQ/SHY have complete, gap-free
local coverage over this period other than genuine exchange closures).

12 primary candidates `PREHOL_{IWM,IJR,IWC,VB,SPY,QQQ}_H{1,2}` + 6 placebo
candidates `PREHOL_{...}_RAND` (deterministic pseudo-random non-pre-holiday
entry days, same trigger count as the real rule, hold 1 session) =
18 candidates, `CANDIDATES: list[lane.ScreenCandidate]`.

Rule (primary, `PREHOL_{TICKER}_H{hold}`): let `d0` be a pre-holiday day (the
last trading day before an exchange closure). Entry signal fires at the close
of the trading day immediately before `d0` -> buy `TICKER` at `d0`'s open.
Hold for `hold` trading days (starting at `d0`); exit signal fires at the
close of the `hold`-th held session -> sell at the next session's open, back
to cash (SHY, via the lane's own remainder rule). `hold=1` captures just the
pre-holiday session itself; `hold=2` also captures the first session after
the reopen.

Rule (placebo, `PREHOL_{TICKER}_RAND`): a deterministic pseudo-random,
non-pre-holiday trading day substitutes for the real entry-signal date (SHA-
256 hash of "TICKER|PREHOL_RAND|<date>", uniform draw compared against the
real rule's own trigger rate -- `len(real entry dates) / len(index)`, ~3.8%
computed from `close.index` itself, so the placebo is frequency-matched to
the real rule without hardcoding a number). Same hold length (1 session).
Never eligible for any keep tier (see `candidate-manifest.json`'s
`keep_rule`) -- an internal falsification control only.

Both rule families read only `close.columns` (ticker presence) and
`close.index` (the calendar) -- never a single price value, so there is no
look-ahead by construction, the same guarantee `h20260928_42_opex_week.py`
gives for its own calendar-anchored rules. `tests/test_h20260929_02_pre_
holiday_etf.py` checks this directly: mutating every price in `close` after
`asof` must not change any `weights_fn` output.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import screen_lane as lane  # noqa: E402

PRIMARY_TICKERS: tuple[str, ...] = ("IWM", "IJR", "IWC", "VB", "SPY", "QQQ")
SMALL_CAP_TICKERS: tuple[str, ...] = ("IWM", "IJR", "IWC", "VB")
LARGE_CAP_TICKERS: tuple[str, ...] = ("SPY", "QQQ")
HOLDS: tuple[int, ...] = (1, 2)


def _is_pre_holiday_gap(d0: pd.Timestamp, d1: pd.Timestamp) -> bool:
    """True iff the calendar-day gap between consecutive trading sessions
    `d0` -> `d1` exceeds the weekend-only gap implied by `d0`'s weekday (3
    days after a Friday, 1 day otherwise) -- i.e. `d0` is the last trading
    day before an exchange closure not explained by a weekend."""
    expected = 3 if d0.weekday() == 4 else 1
    gap = (d1 - d0).days
    return gap > expected


def pre_holiday_positions(index: pd.DatetimeIndex) -> list[int]:
    """Positions `i` in `index` such that `index[i]` is a pre-holiday day.
    Uses only `index` (the calendar), never a price."""
    idx = list(index)
    return [i for i in range(len(idx) - 1) if _is_pre_holiday_gap(idx[i], idx[i + 1])]


def entry_signal_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Last known trading day strictly before each pre-holiday day -- the
    entry signal date (close of this day -> buy at the pre-holiday day's
    open)."""
    idx = list(index)
    out = [idx[i - 1] for i in pre_holiday_positions(index) if i - 1 >= 0]
    return sorted(set(out))


def exit_dates_from_entries(
    index: pd.DatetimeIndex, entries: list[pd.Timestamp], hold: int
) -> list[pd.Timestamp]:
    """For each entry-signal date `e` (buy fills at `index[pos(e) + 1]`'s
    open), the exit-signal date is `hold` sessions later -- i.e. position
    `pos(e) + hold` -- so the position is held for exactly `hold` trading
    sessions before the next-open sell."""
    idx = list(index)
    pos = {d: i for i, d in enumerate(idx)}
    out: list[pd.Timestamp] = []
    for e in entries:
        p = pos.get(e)
        if p is None:
            continue
        exit_pos = p + hold
        if 0 <= exit_pos < len(idx):
            out.append(idx[exit_pos])
    return sorted(set(out))


def real_trigger_rate(index: pd.DatetimeIndex) -> float:
    """Fraction of sessions in `index` that are a real entry-signal date --
    the placebo's frequency-matching target, computed from the calendar
    alone."""
    if len(index) == 0:
        return 0.0
    return len(entry_signal_dates(index)) / float(len(index))


def rand_entry_dates(index: pd.DatetimeIndex, symbol: str) -> list[pd.Timestamp]:
    """Deterministic pseudo-random entry dates: a SHA-256 hash of the ticker
    and calendar date, compared against `real_trigger_rate(index)`, excluding
    any real entry-signal date so the placebo is drawn only from non-pre-
    holiday days. Never reads a price."""
    real = set(entry_signal_dates(index))
    rate = real_trigger_rate(index)
    out: list[pd.Timestamp] = []
    for d in index:
        if d in real:
            continue
        digest = hashlib.sha256(f"{symbol}|PREHOL_RAND|{d.date().isoformat()}".encode()).hexdigest()
        draw = int(digest[:16], 16) / float(16**16)
        if draw < rate:
            out.append(d)
    return sorted(out)


def _make_weights_fn(symbol: str, entries_fn):
    """`entries_fn(index) -> list[Timestamp]` supplies the entry-signal
    dates; `weights_fn` returns full weight on `symbol` at those dates and
    `{}` (all to SHY) elsewhere -- it is only ever evaluated at the dates
    `signal_dates_fn` supplies (entries plus exits), matching
    `h20260928_42_opex_week.py`'s pattern. Reads only `close.columns` and
    `close.index` -- never a price."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if symbol not in close.columns:
            return {}
        if asof in set(entries_fn(close.index)):
            return {symbol: 1.0}
        return {}

    return fn


def _make_signal_dates_fn(entries_fn, hold: int):
    def fn(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
        entries = entries_fn(index)
        exits = exit_dates_from_entries(index, entries, hold)
        return sorted(set(entries) | set(exits))

    return fn


CANDIDATES: list[lane.ScreenCandidate] = []

for _sym in PRIMARY_TICKERS:
    for _hold in HOLDS:
        CANDIDATES.append(
            lane.ScreenCandidate(
                id=f"PREHOL_{_sym}_H{_hold}",
                name=(
                    f"Pre-holiday premium: {_sym} last trading day before an "
                    f"exchange closure, hold {_hold} session(s)"
                ),
                source_card="ariel_1990_pre_holiday_premium_small_firm_replication",
                universe=(_sym,),
                freq="D",
                weights_fn=_make_weights_fn(_sym, entry_signal_dates),
                signal_dates_fn=_make_signal_dates_fn(entry_signal_dates, _hold),
            )
        )

for _sym in PRIMARY_TICKERS:
    _entries_fn = lambda index, _s=_sym: rand_entry_dates(index, _s)  # noqa: E731
    CANDIDATES.append(
        lane.ScreenCandidate(
            id=f"PREHOL_{_sym}_RAND",
            name=f"Placebo: {_sym} pseudo-random non-pre-holiday entry, hold 1 session",
            source_card="pre_holiday_effect_internal_placebo_random_non_holiday_day",
            universe=(_sym,),
            freq="D",
            weights_fn=_make_weights_fn(_sym, _entries_fn),
            signal_dates_fn=_make_signal_dates_fn(_entries_fn, 1),
        )
    )

assert len(CANDIDATES) == 18, f"expected 18 candidates, got {len(CANDIDATES)}"
assert len({c.id for c in CANDIDATES}) == 18, "duplicate candidate ids"
