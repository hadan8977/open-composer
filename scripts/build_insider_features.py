"""H-20260916-01 step 0/1: point-in-time Form 4 insider features.

Card: ``reports/research/hypotheses/H-20260916-01-insider-form4-confirmation-gate.md``
Input: ``data/raw/insider/parsed/{yyyy}q{n}.parquet`` and (when collected)
``data/raw/insider/tail/parsed/{yyyymmdd}.parquet``, both written by
``scripts/collect_sec_insider_transactions.py``.
Output: ``data/features/insider/{year}.parquet`` -- one row per
``(trade_date, symbol)`` in the same ``symbol, trade_date`` key shape every
other feature library under ``data/features/`` uses, so it can be read by
``open_composer.research.features.panel.load_feature_panel`` and by
``scripts/screen_factors.py``'s loader without a new code path.

Point-in-time rule (the only visibility rule in this file)
----------------------------------------------------------
A Form 4 becomes usable at the **next US equity session after its
``FILING_DATE``** (``market_calendar.next_us_equity_session``). ``TRANS_DATE``
is *never* a visibility timestamp: a 2024q1 filing legitimately reports a
2022 transaction, and 2016q1 contains transactions dated 2005. Every
60-day window below is a window over *visible* dates, not trade dates.

Window convention
-----------------
``*_60d`` means the 60 consecutive US equity sessions ending at the row's
own ``trade_date`` inclusive -- i.e. a filing counts iff its visible
session index ``v`` satisfies ``t - 59 <= v <= t``. A filing that becomes
visible on the row's own ``trade_date`` is included, which is correct for
a signal consumed at that session's open or later.

Buy / sell / other
------------------
* buy  = ``TRANS_CODE == 'P'`` and ``TRANS_ACQUIRED_DISP_CD == 'A'``
* sell = ``TRANS_CODE == 'S'`` and ``TRANS_ACQUIRED_DISP_CD == 'D'``
* other = ``TRANS_CODE in {'M', 'A', 'F'}`` (option exercise, grant/award,
  tax withholding) -- counted separately in ``other_count_60d`` and never
  mixed into a buy or sell, because those three codes are mechanical
  compensation events, not discretionary opinions about price.

Only Form 4 and 4/A rows are used (``document_type``): Form 3 is an
initial statement of holdings and Form 5 is an annual catch-up, neither of
which is an open-market opinion at the filing date.

Joint filings
-------------
A single Form 4 can be filed by several reporting owners, and the SEC data
set repeats the transaction once per owner. Share, dollar and transaction
counts therefore use ``owner_seq == 0`` rows only; distinct-owner counts
(``buyers_60d`` / ``sellers_60d``) use every owner row.

Routine vs opportunistic (Cohen-Malloy-Pomorski)
------------------------------------------------
The exact rule implemented, stated so it can be checked and criticized:

1. Take one open-market buy ``e`` by owner ``o`` in issuer ``i``, with
   ``TRANS_DATE`` in calendar month ``m`` of year ``y``, first visible at
   session index ``v``.
2. ``e`` is **routine** iff for every ``k`` in ``{1, 2, 3}`` the pair
   ``(o, i)`` has at least one open-market transaction (code ``P`` *or*
   ``S``) whose ``TRANS_DATE`` falls in calendar month ``m`` of year
   ``y - k``, reported in a filing that was already visible at ``v``.
3. Otherwise ``e`` is **opportunistic** -- which is the card's literal
   rule and what ``opportunistic_buy_60d`` counts.

Because step 3 lumps "has three years of trades but not in this month"
together with "has no three-year record at all", the table also publishes
CMP's own stricter cut:

* ``cmp_opportunistic_buy_60d`` -- not routine *and* the pair has at
  least one visible ``P``/``S`` transaction in each of the three prior
  calendar years. CMP require that record before calling a trade
  opportunistic.
* ``cmp_unclassified_buy_60d`` -- the rest. Structurally unclassifiable:
  new insiders, one-off buyers, and the 2016-2018 warm-up window where
  our own archive does not reach back three years.

``routine_buy_60d + opportunistic_buy_60d == open_market_buy_count_60d``
and ``opportunistic_buy_60d == cmp_opportunistic_buy_60d +
cmp_unclassified_buy_60d`` hold exactly, so both cuts are available to
step 1 and step 2 without rebuilding the table.

Three deliberate choices in that rule:

* **The classification is evaluated once, at the buy's own visible date**
  ``v``, not re-evaluated at every later feature date ``t >= v``. Using
  less information than is available at ``t`` can only make the label
  more conservative, never leak.
* **Only codes P and S count as prior-year history.** Including grants,
  vesting and tax withholding (``A``/``F``/``M``) would label nearly every
  officer routine, because those events are contractually annual --
  which destroys the split instead of measuring it. CMP's own data
  (Thomson Reuters insider filings) is open-market trades.
* **History is keyed by (owner, issuer), not owner alone.** A ten-percent
  holder or fund that files on many issuers would otherwise look routine
  at issuer A because of a same-month trade in issuer B.

Placebo (required by the card)
------------------------------
``--shift-filing-dates-days N`` shifts every *filing's* visible session
index by a per-accession random integer drawn from
``{-N..-1} u {1..N}`` with a fixed seed (``--placebo-seed``, default 20260916).
The shift is drawn per accession, not per row, so a filing's rows stay
coherent, and the output goes to a separate root
(``data/features/insider_placebo_shift{N}_seed{S}/``) so a placebo table can
never be mistaken for the real one. If the card's effect survives this,
the effect is a size/sector/liquidity proxy, not insider information.

Usage::

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/build_insider_features.py \\
        > /tmp/insider_features.log 2>&1 &

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/build_insider_features.py \\
        --shift-filing-dates-days 30 \\
        > /tmp/insider_features_placebo.log 2>&1 &
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.market_calendar import (  # noqa: E402
    next_us_equity_session,
    us_equity_session_dates,
)
from open_composer.research.features.insider import INSIDER_COLUMNS  # noqa: E402
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    universe_as_of_calendar_month,
    weekly_rebalance_dates,
)

PARSED_ROOT = ROOT / "data" / "raw" / "insider" / "parsed"
TAIL_PARSED_ROOT = ROOT / "data" / "raw" / "insider" / "tail" / "parsed"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
DEFAULT_OUT_ROOT = ROOT / "data" / "features" / "insider"
WEEKLY_PANEL_NAME = "screening_panel_weekly.parquet"

NEW_YORK = ZoneInfo("America/New_York")
WINDOW_SESSIONS = 60
FEATURE_UNIVERSE_TOP_N = 1000
WEEKLY_PANEL_TOP_N = 500
OTHER_CODES = ("M", "A", "F")
DEFAULT_PLACEBO_SEED = 20260916

#: The feature columns this table publishes, in output order. Single source
#: of truth is ``open_composer.research.features.insider`` so the
#: feature-set registry and this builder cannot drift apart.
FEATURE_COLUMNS: tuple[str, ...] = INSIDER_COLUMNS

#: Share and dollar aggregates stay float64: a 60-day net share flow can
#: exceed float32's ~7 significant digits (observed -166,998.625 where the
#: true value was -166,998), and a USD flow above 1e9 would lose hundreds
#: of dollars. Counts and day gaps are small integers and stay float32.
WIDE_COLUMNS: tuple[str, ...] = ("net_buy_shares_60d", "net_buy_usd_60d")

READ_COLUMNS = (
    "accession",
    "document_type",
    "filing_date",
    "issuer_symbol",
    "reporting_owner_cik",
    "owner_seq",
    "trans_date",
    "trans_code",
    "acquired_disposed",
    "shares",
    "price_per_share",
)


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


# --------------------------------------------------------------------------
# calendar
# --------------------------------------------------------------------------


def build_session_index(start: date, end: date) -> tuple[pd.DatetimeIndex, dict[pd.Timestamp, int]]:
    sessions = pd.DatetimeIndex([pd.Timestamp(day) for day in us_equity_session_dates(start, end)])
    return sessions, {timestamp: position for position, timestamp in enumerate(sessions)}


def visible_session(filing_date: pd.Timestamp) -> pd.Timestamp:
    """The first session on which a filing dated ``filing_date`` may be used."""
    return pd.Timestamp(next_us_equity_session(filing_date.date()))


def session_open_utc(trade_date: pd.Timestamp) -> pd.Timestamp:
    return (
        pd.Timestamp(trade_date.date())
        .tz_localize(NEW_YORK)
        .replace(hour=9, minute=30)
        .tz_convert("UTC")
    )


# --------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------


def load_transactions(*, symbols: set[str] | None) -> pd.DataFrame:
    """Every parsed Form 4/4-A non-derivative transaction row, narrowed to
    ``symbols`` (the union point-in-time universe) if given."""
    paths = sorted(PARSED_ROOT.glob("*.parquet")) + sorted(TAIL_PARSED_ROOT.glob("*.parquet"))
    if not paths:
        raise SystemExit(
            f"no parsed insider quarters under {PARSED_ROOT}; "
            "run scripts/collect_sec_insider_transactions.py --stage quarterly first"
        )
    frames: list[pd.DataFrame] = []
    for path in paths:
        frame = pd.read_parquet(path, columns=list(READ_COLUMNS))
        frame = frame.loc[frame["document_type"].isin(["4", "4/A"])]
        if symbols is not None:
            frame = frame.loc[frame["issuer_symbol"].isin(symbols)]
        if frame.empty:
            continue
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    combined["trans_code"] = combined["trans_code"].astype("string").fillna("")
    combined["acquired_disposed"] = combined["acquired_disposed"].astype("string").fillna("")
    combined["owner_cik"] = pd.to_numeric(combined["reporting_owner_cik"], errors="coerce").astype(
        "Int64"
    )
    return combined.drop(columns=["reporting_owner_cik", "document_type"])


def attach_visible_index(
    transactions: pd.DataFrame,
    session_position: dict[pd.Timestamp, int],
    *,
    shift_days: int,
    seed: int,
) -> pd.DataFrame:
    """Add ``visible_idx`` (session index at which the filing may be used).

    ``shift_days > 0`` is the card's placebo: a per-accession random shift
    of the visible index, drawn once per accession with ``seed``.
    """
    filing_dates = pd.to_datetime(transactions["filing_date"]).dt.normalize()
    unique_dates = pd.DatetimeIndex(filing_dates.dropna().unique())
    mapping = {
        filing_date: session_position.get(visible_session(filing_date), -1)
        for filing_date in unique_dates
    }
    transactions = transactions.copy()
    transactions["visible_idx"] = filing_dates.map(mapping).fillna(-1).astype("int64")

    if shift_days > 0:
        accessions = transactions["accession"].astype("string")
        codes, uniques = pd.factorize(accessions)
        rng = np.random.default_rng(seed)
        offsets = rng.integers(1, shift_days + 1, size=len(uniques))
        signs = rng.choice(np.array([-1, 1]), size=len(uniques))
        deltas = offsets * signs
        last_index = max(session_position.values())
        shifted = transactions["visible_idx"].to_numpy() + deltas[codes]
        shifted = np.clip(shifted, 0, last_index)
        transactions["visible_idx"] = np.where(
            transactions["visible_idx"].to_numpy() < 0, -1, shifted
        )
        log(
            f"placebo: shifted {len(uniques):,} accessions by a per-accession "
            f"random +/-1..{shift_days} session offset (seed={seed})"
        )

    return transactions.loc[transactions["visible_idx"] >= 0]


def classify_transactions(transactions: pd.DataFrame) -> pd.DataFrame:
    transactions = transactions.copy()
    transactions["is_buy"] = (transactions["trans_code"] == "P") & (
        transactions["acquired_disposed"] == "A"
    )
    transactions["is_sell"] = (transactions["trans_code"] == "S") & (
        transactions["acquired_disposed"] == "D"
    )
    transactions["is_other"] = transactions["trans_code"].isin(OTHER_CODES)
    shares = pd.to_numeric(transactions["shares"], errors="coerce").fillna(0.0)
    price = pd.to_numeric(transactions["price_per_share"], errors="coerce").fillna(0.0)
    transactions["shares_num"] = shares.astype("float64")
    transactions["usd"] = (shares * price).astype("float64")
    return transactions


def label_buy_routineness(transactions: pd.DataFrame) -> pd.DataFrame:
    """Per-row routine / opportunistic / unclassified flags for open-market buys.

    Returns three boolean columns (all ``False`` on non-buy rows), which
    partition the open-market buys exactly:

    ``is_routine_buy``
        The ``(owner, issuer)`` pair has a ``P`` or ``S`` transaction whose
        ``TRANS_DATE`` month equals this buy's month in *each* of the three
        prior calendar years, reported in a filing already visible at this
        buy's own visible session.
    ``is_cmp_opportunistic_buy``
        Not routine, but the pair does have at least one visible ``P``/``S``
        transaction in *each* of the three prior calendar years -- i.e. the
        insider has the three-year track record CMP require before calling
        a trade opportunistic rather than merely unclassifiable.
    ``is_cmp_unclassified_buy``
        Not routine and without that three-year record. Structurally
        unclassifiable, mostly new insiders and the 2016-2018 warm-up
        window where our own history simply does not go back far enough.

    ``opportunistic_buy_60d`` in the published table is the *literal* card
    rule (``not routine`` = ``cmp_opportunistic`` + ``cmp_unclassified``);
    the two CMP components are published separately so step 2 can use the
    stricter split without rebuilding the table.
    """
    trades = transactions.loc[transactions["is_buy"] | transactions["is_sell"]]
    trans_dates = pd.to_datetime(trades["trans_date"])
    history = pd.DataFrame(
        {
            "symbol": trades["issuer_symbol"].to_numpy(),
            "owner": trades["owner_cik"].to_numpy(),
            "year": trans_dates.dt.year.to_numpy(),
            "month": trans_dates.dt.month.to_numpy(),
            "visible_idx": trades["visible_idx"].to_numpy(),
        }
    ).dropna(subset=["owner", "year", "month"])
    earliest_month = (
        history.groupby(["symbol", "owner", "year", "month"], sort=False)["visible_idx"]
        .min()
        .rename("first_visible_idx")
        .reset_index()
    )
    earliest_year = (
        history.groupby(["symbol", "owner", "year"], sort=False)["visible_idx"]
        .min()
        .rename("first_visible_idx_year")
        .reset_index()
    )

    buys = transactions.loc[transactions["is_buy"]]
    buy_trans_dates = pd.to_datetime(buys["trans_date"])
    candidates = pd.DataFrame(
        {
            "row": buys.index.to_numpy(),
            "symbol": buys["issuer_symbol"].to_numpy(),
            "owner": buys["owner_cik"].to_numpy(),
            "year": buy_trans_dates.dt.year.to_numpy(),
            "month": buy_trans_dates.dt.month.to_numpy(),
            "visible_idx": buys["visible_idx"].to_numpy(),
        }
    )
    resolvable = ~(candidates["owner"].isna() | candidates["year"].isna()).to_numpy()
    visible = candidates["visible_idx"].to_numpy()
    routine = resolvable.copy()
    has_three_year_record = resolvable.copy()
    for lag in (1, 2, 3):
        lagged = candidates.assign(year=candidates["year"] - lag)
        month_probe = lagged.merge(
            earliest_month, on=["symbol", "owner", "year", "month"], how="left"
        )["first_visible_idx"]
        routine &= (month_probe.notna() & (month_probe.to_numpy() <= visible)).to_numpy()
        year_probe = lagged.merge(earliest_year, on=["symbol", "owner", "year"], how="left")[
            "first_visible_idx_year"
        ]
        has_three_year_record &= (
            year_probe.notna() & (year_probe.to_numpy() <= visible)
        ).to_numpy()

    flags = pd.DataFrame(
        False,
        index=transactions.index,
        columns=["is_routine_buy", "is_cmp_opportunistic_buy", "is_cmp_unclassified_buy"],
    )
    rows = candidates["row"].to_numpy()
    flags.loc[rows[routine], "is_routine_buy"] = True
    flags.loc[rows[~routine & has_three_year_record], "is_cmp_opportunistic_buy"] = True
    flags.loc[rows[~routine & ~has_three_year_record], "is_cmp_unclassified_buy"] = True
    is_buy = transactions["is_buy"].to_numpy()
    for column in flags.columns:
        flags[column] = flags[column].to_numpy() & is_buy
    return flags


# --------------------------------------------------------------------------
# per-year dense computation
# --------------------------------------------------------------------------


def _scatter_sum(
    target: np.ndarray, rows: np.ndarray, columns: np.ndarray, values: np.ndarray
) -> None:
    np.add.at(target, (rows, columns), values)


def _rolling_window_sum(daily: np.ndarray, window: int) -> np.ndarray:
    """Trailing ``window``-column inclusive sum along axis 1."""
    cumulative = np.cumsum(daily, axis=1)
    shifted = np.zeros_like(cumulative)
    shifted[:, window:] = cumulative[:, :-window]
    return cumulative - shifted


def _distinct_owner_counts(
    *,
    symbol_positions: np.ndarray,
    owners: np.ndarray,
    indices: np.ndarray,
    n_symbols: int,
    local_start: int,
    n_local: int,
    window: int,
) -> np.ndarray:
    """Distinct owners with at least one qualifying event in the trailing
    ``window`` sessions, for every (symbol, local session) cell.

    Each (symbol, owner) event at global index ``v`` covers the closed
    interval ``[v, v + window - 1]`` of feature dates. Overlapping
    intervals for the same (symbol, owner) are merged first, so an owner
    who buys twice in one window is counted once; then a per-symbol
    difference array turns the merged intervals into counts.
    """
    counts = np.zeros((n_symbols, n_local), dtype=np.int32)
    if symbol_positions.size == 0:
        return counts
    order = np.lexsort((indices, owners, symbol_positions))
    symbol_positions = symbol_positions[order]
    owners = owners[order]
    indices = indices[order]

    same_group = np.empty(symbol_positions.size, dtype=bool)
    same_group[0] = False
    same_group[1:] = (symbol_positions[1:] == symbol_positions[:-1]) & (owners[1:] == owners[:-1])
    contiguous = np.zeros(symbol_positions.size, dtype=bool)
    contiguous[1:] = same_group[1:] & ((indices[1:] - indices[:-1]) < window)
    starts = ~contiguous

    run_symbol = symbol_positions[starts]
    run_start = indices[starts]
    run_end = np.maximum.reduceat(indices, np.flatnonzero(starts)) + window - 1

    local_first = np.clip(run_start - local_start, 0, n_local)
    local_last = np.clip(run_end - local_start + 1, 0, n_local)
    keep = local_last > local_first
    if not keep.any():
        return counts
    difference = np.zeros((n_symbols, n_local + 1), dtype=np.int32)
    np.add.at(difference, (run_symbol[keep], local_first[keep]), 1)
    np.add.at(difference, (run_symbol[keep], local_last[keep]), -1)
    return np.cumsum(difference, axis=1)[:, :n_local].astype(np.int32)


def build_year(
    year: int,
    *,
    transactions: pd.DataFrame,
    sessions: pd.DatetimeIndex,
    universe_panel: pd.DataFrame,
    top_n: int,
) -> pd.DataFrame:
    year_mask = sessions.year == year
    target_positions = np.flatnonzero(year_mask)
    if target_positions.size == 0:
        return pd.DataFrame()
    first_target = int(target_positions[0])
    last_target = int(target_positions[-1])
    local_start = max(0, first_target - (WINDOW_SESSIONS - 1))
    n_local = last_target - local_start + 1
    target_offset = first_target - local_start

    target_dates = sessions[first_target : last_target + 1]
    cohorts = {
        timestamp: universe_as_of_calendar_month(universe_panel, timestamp, top_n=top_n)
        for timestamp in target_dates
    }
    symbols = sorted(set().union(*cohorts.values())) if cohorts else []
    if not symbols:
        return pd.DataFrame()
    symbol_position = {symbol: position for position, symbol in enumerate(symbols)}
    n_symbols = len(symbols)

    window = transactions.loc[
        (transactions["visible_idx"] >= local_start)
        & (transactions["visible_idx"] <= last_target)
        & (transactions["issuer_symbol"].isin(symbol_position))
    ]
    positions = window["issuer_symbol"].map(symbol_position).to_numpy(dtype=np.int64)
    locals_ = window["visible_idx"].to_numpy(dtype=np.int64) - local_start

    primary = window["owner_seq"].fillna(0).to_numpy(dtype=np.int64) == 0
    is_buy = window["is_buy"].to_numpy(dtype=bool)
    is_sell = window["is_sell"].to_numpy(dtype=bool)
    is_other = window["is_other"].to_numpy(dtype=bool)
    shares = window["shares_num"].to_numpy(dtype=np.float64)
    usd = window["usd"].to_numpy(dtype=np.float64)
    routine = window["is_routine_buy"].to_numpy(dtype=bool)
    cmp_opportunistic = window["is_cmp_opportunistic_buy"].to_numpy(dtype=bool)
    cmp_unclassified = window["is_cmp_unclassified_buy"].to_numpy(dtype=bool)

    daily = {
        name: np.zeros((n_symbols, n_local), dtype=np.float64)
        for name in (
            "buy_shares",
            "sell_shares",
            "buy_usd",
            "sell_usd",
            "buy_count",
            "sell_count",
            "other_count",
            "opportunistic_buy",
            "routine_buy",
            "cmp_opportunistic_buy",
            "cmp_unclassified_buy",
        )
    }
    buy_primary = primary & is_buy
    sell_primary = primary & is_sell
    other_primary = primary & is_other
    _scatter_sum(
        daily["buy_shares"], positions[buy_primary], locals_[buy_primary], shares[buy_primary]
    )
    _scatter_sum(
        daily["sell_shares"], positions[sell_primary], locals_[sell_primary], shares[sell_primary]
    )
    _scatter_sum(daily["buy_usd"], positions[buy_primary], locals_[buy_primary], usd[buy_primary])
    _scatter_sum(
        daily["sell_usd"], positions[sell_primary], locals_[sell_primary], usd[sell_primary]
    )
    ones = np.ones(1, dtype=np.float64)
    _scatter_sum(daily["buy_count"], positions[buy_primary], locals_[buy_primary], ones)
    _scatter_sum(daily["sell_count"], positions[sell_primary], locals_[sell_primary], ones)
    _scatter_sum(daily["other_count"], positions[other_primary], locals_[other_primary], ones)
    for name, flag in (
        ("opportunistic_buy", buy_primary & ~routine),
        ("routine_buy", buy_primary & routine),
        ("cmp_opportunistic_buy", buy_primary & cmp_opportunistic),
        ("cmp_unclassified_buy", buy_primary & cmp_unclassified),
    ):
        _scatter_sum(daily[name], positions[flag], locals_[flag], ones)

    rolled = {name: _rolling_window_sum(array, WINDOW_SESSIONS) for name, array in daily.items()}

    owners = window["owner_cik"].fillna(-1).to_numpy(dtype=np.int64)
    buyers = _distinct_owner_counts(
        symbol_positions=positions[is_buy],
        owners=owners[is_buy],
        indices=window["visible_idx"].to_numpy(dtype=np.int64)[is_buy],
        n_symbols=n_symbols,
        local_start=local_start,
        n_local=n_local,
        window=WINDOW_SESSIONS,
    )
    sellers = _distinct_owner_counts(
        symbol_positions=positions[is_sell],
        owners=owners[is_sell],
        indices=window["visible_idx"].to_numpy(dtype=np.int64)[is_sell],
        n_symbols=n_symbols,
        local_start=local_start,
        n_local=n_local,
        window=WINDOW_SESSIONS,
    )

    # days_since_last_visible_buy uses full history, not just the window.
    last_buy = np.full((n_symbols, n_local), -1, dtype=np.int64)
    buy_rows = positions[is_buy]
    buy_cols = locals_[is_buy]
    buy_global = window["visible_idx"].to_numpy(dtype=np.int64)[is_buy]
    np.maximum.at(last_buy, (buy_rows, buy_cols), buy_global)
    carry_in = _carry_in_last_buy(transactions, symbol_position, local_start)
    last_buy[:, 0] = np.maximum(last_buy[:, 0], carry_in)
    np.maximum.accumulate(last_buy, axis=1, out=last_buy)

    slice_ = slice(target_offset, n_local)
    n_target = n_local - target_offset
    global_indices = np.arange(first_target, last_target + 1, dtype=np.int64)
    days_since = np.where(
        last_buy[:, slice_] < 0, np.nan, global_indices[None, :] - last_buy[:, slice_]
    )

    mask = np.zeros((n_symbols, n_target), dtype=bool)
    for column, timestamp in enumerate(target_dates):
        cohort = cohorts[timestamp]
        if not cohort:
            continue
        rows = [symbol_position[symbol] for symbol in cohort if symbol in symbol_position]
        mask[rows, column] = True
    selected = np.flatnonzero(mask.ravel())
    if selected.size == 0:
        return pd.DataFrame()

    symbol_array = np.repeat(np.array(symbols, dtype=object), n_target)
    date_array = np.tile(target_dates.to_numpy(), n_symbols)
    buyers_flat = buyers[:, slice_].ravel()[selected].astype(np.float32)
    sellers_flat = sellers[:, slice_].ravel()[selected].astype(np.float32)
    frame = pd.DataFrame(
        {
            "symbol": symbol_array[selected],
            "trade_date": date_array[selected],
            "net_buy_shares_60d": (
                rolled["buy_shares"][:, slice_] - rolled["sell_shares"][:, slice_]
            ).ravel()[selected],
            "net_buy_usd_60d": (
                rolled["buy_usd"][:, slice_] - rolled["sell_usd"][:, slice_]
            ).ravel()[selected],
            "buyers_60d": buyers_flat,
            "sellers_60d": sellers_flat,
            "net_buyers_60d": buyers_flat - sellers_flat,
            "open_market_buy_count_60d": rolled["buy_count"][:, slice_].ravel()[selected],
            "open_market_sell_count_60d": rolled["sell_count"][:, slice_].ravel()[selected],
            "other_count_60d": rolled["other_count"][:, slice_].ravel()[selected],
            "opportunistic_buy_60d": rolled["opportunistic_buy"][:, slice_].ravel()[selected],
            "routine_buy_60d": rolled["routine_buy"][:, slice_].ravel()[selected],
            "cmp_opportunistic_buy_60d": rolled["cmp_opportunistic_buy"][:, slice_].ravel()[
                selected
            ],
            "cmp_unclassified_buy_60d": rolled["cmp_unclassified_buy"][:, slice_].ravel()[selected],
            "days_since_last_visible_buy": days_since.ravel()[selected],
        }
    )
    frame["symbol"] = frame["symbol"].astype("string")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    for column in FEATURE_COLUMNS:
        frame[column] = frame[column].astype("float64" if column in WIDE_COLUMNS else "float32")
    visible_at_map = {
        timestamp: session_open_utc(timestamp) for timestamp in frame["trade_date"].unique()
    }
    frame["visible_at"] = frame["trade_date"].map(visible_at_map)
    return frame.sort_values(["symbol", "trade_date"], kind="stable").reset_index(drop=True)


def _carry_in_last_buy(
    transactions: pd.DataFrame, symbol_position: dict[str, int], local_start: int
) -> np.ndarray:
    carry = np.full(len(symbol_position), -1, dtype=np.int64)
    prior = transactions.loc[
        transactions["is_buy"]
        & (transactions["visible_idx"] < local_start)
        & (transactions["issuer_symbol"].isin(symbol_position))
    ]
    if prior.empty:
        return carry
    grouped = prior.groupby("issuer_symbol", sort=False)["visible_idx"].max()
    for symbol, value in grouped.items():
        carry[symbol_position[str(symbol)]] = int(value)
    return carry


# --------------------------------------------------------------------------
# weekly screening panel
# --------------------------------------------------------------------------


def build_weekly_panel(
    out_root: Path,
    *,
    sessions: pd.DatetimeIndex,
    top_n: int,
    universe_root: Path = UNIVERSE_ROOT,
) -> Path:
    """Collapse the daily table to the weekly rebalance grid the F-track
    screener scores on, restricted to the point-in-time top-``top_n`` ADV
    cohort of the panel under ``universe_root``."""
    universe_panel = load_universe_panel(universe_root)
    fridays = set(weekly_rebalance_dates(list(sessions)))
    frames: list[pd.DataFrame] = []
    for path in sorted(out_root.glob("[0-9][0-9][0-9][0-9].parquet")):
        frame = pd.read_parquet(path)
        frame = frame.loc[frame["trade_date"].isin(fridays)]
        if frame.empty:
            continue
        cohorts = {
            timestamp: universe_as_of_calendar_month(universe_panel, timestamp, top_n=top_n)
            for timestamp in frame["trade_date"].unique()
        }
        keep = [
            symbol in cohorts[timestamp]
            for symbol, timestamp in zip(frame["symbol"], frame["trade_date"], strict=True)
        ]
        frames.append(frame.loc[keep])
    panel = pd.concat(frames, ignore_index=True)
    panel.insert(1, "friday_date", panel["trade_date"])
    panel = panel.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)
    target = out_root / WEEKLY_PANEL_NAME
    temporary = target.with_suffix(".parquet.part")
    panel.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(target)
    log(
        f"weekly panel: {len(panel):,} rows, "
        f"{panel['trade_date'].nunique():,} fridays, {panel['symbol'].nunique():,} symbols "
        f"-> {target}"
    )
    return target


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-year", type=int, default=2016)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument("--top-n", type=int, default=FEATURE_UNIVERSE_TOP_N)
    parser.add_argument("--weekly-top-n", type=int, default=WEEKLY_PANEL_TOP_N)
    parser.add_argument(
        "--shift-filing-dates-days",
        type=int,
        default=0,
        help="Placebo: per-accession random +/-1..N session shift of the visible date.",
    )
    parser.add_argument("--placebo-seed", type=int, default=DEFAULT_PLACEBO_SEED)
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help=(
            "Last feature date, YYYY-MM-DD. Defaults to today. Sessions after this "
            "date get no row at all, rather than a row whose 60-day window is empty "
            "only because the future has not happened yet."
        ),
    )
    parser.add_argument("--out-root", type=Path, default=None)
    parser.add_argument(
        "--universe-root",
        type=Path,
        default=UNIVERSE_ROOT,
        help=(
            "PIT universe panel dir (default data/features/universe; pass "
            "data/features/universe_broad with a large --top-n for the broad universe)"
        ),
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-weekly-panel", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    shift = max(0, args.shift_filing_dates_days)
    out_root = args.out_root or (
        DEFAULT_OUT_ROOT
        if shift == 0
        else DEFAULT_OUT_ROOT.with_name(f"insider_placebo_shift{shift}_seed{args.placebo_seed}")
    )
    out_root.mkdir(parents=True, exist_ok=True)

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    last_date = min(date(args.end_year, 12, 31), as_of)
    sessions, session_position = build_session_index(date(args.start_year, 1, 1), last_date)
    log(
        f"feature dates: {sessions[0].date()} .. {sessions[-1].date()} ({len(sessions):,} sessions)"
    )
    universe_root = Path(args.universe_root)
    universe_panel = load_universe_panel(universe_root)
    universe_symbols = set(universe_panel.loc[universe_panel["adv_rank"] <= args.top_n, "symbol"])
    log(
        f"point-in-time universe union (adv_rank <= {args.top_n}): "
        f"{len(universe_symbols):,} symbols"
    )

    transactions = load_transactions(symbols=universe_symbols)
    log(f"loaded {len(transactions):,} Form 4/4-A transaction rows in the universe")
    transactions = attach_visible_index(
        transactions, session_position, shift_days=shift, seed=args.placebo_seed
    )
    transactions = classify_transactions(transactions)
    buys = transactions.loc[transactions["is_buy"]]
    if len(buys):
        missing_price = float((buys["usd"] == 0).mean())
        log(f"open-market buys with no usable price (usd contribution 0): {missing_price:.2%}")
    transactions = pd.concat([transactions, label_buy_routineness(transactions)], axis=1)
    primary_buys = transactions.loc[
        transactions["is_buy"] & (transactions["owner_seq"].fillna(0) == 0)
    ]
    if len(primary_buys):
        log(
            "open-market buy split: "
            f"routine {float(primary_buys['is_routine_buy'].mean()):.2%}, "
            f"CMP-opportunistic {float(primary_buys['is_cmp_opportunistic_buy'].mean()):.2%}, "
            f"unclassified {float(primary_buys['is_cmp_unclassified_buy'].mean()):.2%}"
        )
    transactions = transactions.drop(
        columns=["accession", "trans_code", "acquired_disposed", "shares", "price_per_share"]
    )

    written: list[str] = []
    for year in range(args.start_year, args.end_year + 1):
        target = out_root / f"{year}.parquet"
        if target.exists() and not args.force:
            log(f"{year}: already built")
            written.append(str(target))
            continue
        frame = build_year(
            year,
            transactions=transactions,
            sessions=sessions,
            universe_panel=universe_panel,
            top_n=args.top_n,
        )
        if frame.empty:
            log(f"{year}: no rows (no sessions or no universe cohort)")
            continue
        temporary = target.with_suffix(".parquet.part")
        frame.to_parquet(temporary, index=False, compression="zstd")
        temporary.replace(target)
        written.append(str(target))
        log(
            f"{year}: {len(frame):,} rows, {frame['symbol'].nunique():,} symbols, "
            f"share with a visible buy in 60d = "
            f"{float((frame['open_market_buy_count_60d'] > 0).mean()):.2%}"
        )
        del frame

    if not args.skip_weekly_panel:
        build_weekly_panel(
            out_root, sessions=sessions, top_n=args.weekly_top_n, universe_root=universe_root
        )

    manifest = {
        "built_at": datetime.now().astimezone().isoformat(),
        "as_of": last_date.isoformat(),
        "universe_root": str(universe_root),
        "first_feature_date": sessions[0].date().isoformat(),
        "last_feature_date": sessions[-1].date().isoformat(),
        "window_sessions": WINDOW_SESSIONS,
        "visibility_rule": "next_us_equity_session(FILING_DATE)",
        "document_types": ["4", "4/A"],
        "buy_codes": ["P"],
        "sell_codes": ["S"],
        "other_codes": list(OTHER_CODES),
        "feature_universe_top_n": args.top_n,
        "weekly_panel_top_n": args.weekly_top_n,
        "placebo_shift_filing_dates_days": shift,
        "placebo_seed": args.placebo_seed if shift else None,
        "routine_rule": (
            "routine iff for k in 1..3 the (owner, issuer) pair has a P or S transaction "
            "whose TRANS_DATE month equals this buy's month in year y-k, reported in a "
            "filing visible at or before this buy's own visible session; "
            "opportunistic_buy_60d = not routine (the card's literal rule); "
            "cmp_opportunistic_buy_60d additionally requires a visible P/S transaction in "
            "each of the three prior calendar years, cmp_unclassified_buy_60d is the rest"
        ),
        "years": written,
    }
    (out_root / "_build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    log(f"wrote {out_root / '_build_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
