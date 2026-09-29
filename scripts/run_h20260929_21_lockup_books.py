"""T-20260929-21: calendar-time short (and info-only avoid-long) book for the
IPO lockup-expiration event list built by ``scripts/build_h20260929_21_lockups.py``.

Reuses ``scripts/screen_lane.py`` (``s3_incumbent``, ``correlation_with_s3``,
``diversifier_edge_for_offset``, ``CASH``, ``RF``, ``PANEL_START``) and
``scripts/run_h20260922_05_salvage.py`` (``legs``) unmodified, plus
``scripts/run_h20260918_05_recent_menu.py`` (``load_panel``, for BIL) --
same reuse pattern ``run_h20260929_12_hedged_books.py`` already uses for its
own CASH/RF legs. Does NOT import anything from ``run_t20260929_3*`` (a
different, in-flux session's scripts) per this task's explicit instruction.

Close-to-close convention
--------------------------
``simulate_book``/``stock_legs`` below are a fresh, self-contained
reimplementation of ``run_h20260922_05_salvage.legs``/``.simulate``'s own
overnight/intraday leg-mixing formula (old weight earns the overnight gap
``open(t)/close(t-1)-1``, new weight earns the intraday move
``close(t)/open(t)-1``), extended with a per-column daily borrow drag on
short exposure. ``tests/test_h20260929_21_lockup.py`` checks this against
the actual frozen ``salvage.legs``/``.simulate`` for a synthetic
single-asset book (point 4 of the task's test requirements) rather than
assuming the replication is correct.

Portfolio construction
-----------------------
Calendar-time, <=15 concurrent positions, <=10% of capital each, remainder
in BIL. Capacity is enforced by a greedy first-come sweep over events sorted
by entry-signal date: an event is admitted only if accepting it never pushes
the concurrently-open count (among already-admitted events) above 15 on any
day of its intended holding window; otherwise it is skipped entirely
(``capacity_skipped``, counted and reported, never silently dropped).

Usage::

    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/run_h20260929_21_lockup_books.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import screen_lane  # noqa: E402

from open_composer.research.campaign_statistics import deflated_sharpe_probability  # noqa: E402

ITER_DIR = ROOT / "reports/research/iterations/h20260929_21_ipo_lockup_expiry"
EVENTS_PATH = ITER_DIR / "events.parquet"
DAILY_BROAD_DIR = ROOT / "data" / "features" / "daily_broad"

TEST_WINDOW = ("2024-01-08", "2026-09-17")
STRESS_WINDOW = ("2016-05-02", "2023-09-15")
MIN_TEST_EVENTS = 40
MAX_CONCURRENT = 15
MAX_WEIGHT_PER_POSITION = 0.10

WINDOW_OFFSETS = {"L5L1": (5, 1), "L1L5": (1, 5)}
ADV_FILTERS = ["adv1500", "unrestricted"]
MOM_FILTERS = ["all", "pos", "neg"]

SPREAD_BPS_TIERS = [(500, 3.0), (1000, 6.0), (1500, 12.0), (float("inf"), 25.0)]
BORROW_ANNUAL_TOP1500 = 0.03
BORROW_ANNUAL_BEYOND = 0.25
BORROW_DAYCOUNT = 360.0  # Alpaca's own HTB fee convention (daily fee / 360)

DATE_SHIFT_SESSIONS = 60
RANDOM_PLACEBO_SEED = 20260929
DSR_HAC_LAG = 21
N_TRIALS = 13
K1_ANCHOR_SHARPE_MIN = 1.19
EDGE_MIN = 0.05
CORR_MAX = 1.0  # no correlation gate in this iteration's frozen rule


def _log(msg: str, t0: float) -> None:
    print(f"[h20260929_21_books] {msg} ({time.monotonic() - t0:.0f}s)", flush=True)


# --------------------------------------------------------------------------
# close-to-close engine (self-contained; verified against salvage in tests)
# --------------------------------------------------------------------------


def stock_legs(open_: np.ndarray, close: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-symbol overnight/intraday legs, same formula as
    ``run_h20260922_05_salvage.legs``: ``leg_open[t]=open[t]/close[t-1]-1``,
    ``leg_close[t]=close[t]/open[t]-1``. Row 0's ``leg_open`` is NaN (no
    ``close[-1]``) and filled to 0 by ``simulate_book``."""
    prev_close = np.empty_like(close)
    prev_close[0] = np.nan
    prev_close[1:] = close[:-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        leg_open = open_ / prev_close - 1.0
        leg_close = close / open_ - 1.0
    return leg_open, leg_close


def simulate_book(
    weights: np.ndarray,
    leg_open: np.ndarray,
    leg_close: np.ndarray,
    cost_bps: np.ndarray,
    borrow_daily_rate: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Close-to-close book simulation with per-column turnover cost (bps)
    and a per-column daily borrow drag on short exposure (``weight<0``).

    On day i, old weights (row i-1) earn the overnight gap ``leg_open[i]``,
    new weights (row i) earn the intraday move ``leg_close[i]`` -- the same
    convention as ``salvage.simulate``/``screen_lane.s3_incumbent``, so no
    relabeling is needed before any comparison with S3. Turnover cost is
    ``sum(|w_i - w_{i-1}| * cost_bps / 1e4)``; a position entering (0->-w)
    and later exiting (-w->0) is charged the round-trip cost automatically,
    once on each leg. Borrow cost is ``sum(max(-w_i, 0) * borrow_daily_rate)``
    applied on the CURRENT (post-rebalance) day's weight, i.e. charged for
    every session the short is actually held, including its first and last.
    """
    T, N = weights.shape
    w_prev = np.zeros(N, dtype=np.float64)
    gross = np.zeros(T, dtype=np.float64)
    turnover = np.zeros(
        T, dtype=np.float64
    )  # raw sum(|delta w|), same semantics as salvage.simulate
    cost = np.zeros(T, dtype=np.float64)
    borrow = np.zeros(T, dtype=np.float64)
    lo_filled = np.where(np.isfinite(leg_open), leg_open, 0.0)
    lc_filled = np.where(np.isfinite(leg_close), leg_close, 0.0)
    for i in range(T):
        w = weights[i]
        diff = np.abs(w - w_prev)
        gross[i] = float(w_prev @ lo_filled[i] + w @ lc_filled[i])
        turnover[i] = float(diff.sum())
        cost[i] = float(diff @ cost_bps) / 1e4
        borrow[i] = float(np.maximum(-w, 0.0) @ borrow_daily_rate)
        w_prev = w
    net = gross - cost - borrow
    return net, turnover


# --------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------


def load_trading_calendar() -> pd.DatetimeIndex:
    frame = pd.concat(
        [
            pd.read_parquet(p, columns=["trade_date"])
            for p in sorted(DAILY_BROAD_DIR.glob("*.parquet"))
        ],
        ignore_index=True,
    )
    return pd.DatetimeIndex(sorted(frame["trade_date"].unique()))


def load_event_stock_panel(symbols: list[str], calendar: pd.DatetimeIndex) -> dict:
    """Loads the event-stock open/close/ADV panel and runs it through
    ``open_composer.research.features.price_hygiene.sanitize_price_matrices``
    (default thresholds: 10x one-day jump, 5-session gap) before anything
    downstream computes a return from it. Recent-IPO names are exactly the
    thin, newly-listed tickers most exposed to post-bankruptcy relistings on
    a recycled symbol, unadjusted splits, and one-day bad prints (coordinator
    note, 2026-09-29, citing T-20's WOLF/APH/KIDZ findings in data/sip/daily
    and a 1,757% single-trade loss that voided that round's calendar
    metrics). ``data/features/daily_broad`` does not expose ``volume``/
    ``trade_count``, so ``drop_ghost_bars`` cannot run at this layer; ghost
    bars are presumed already dropped upstream by the feature build
    (``features/daily_features.py``'s ``GHOST_BAR_SQL_PREDICATE``, per that
    module's own docstring) -- this is a documented assumption, not
    independently re-verified here. Returns the sanitized close/open plus
    the ``PriceHygieneReport`` (written into results.json verbatim)."""
    from open_composer.research.features.price_hygiene import sanitize_price_matrices

    frames = []
    for p in sorted(DAILY_BROAD_DIR.glob("*.parquet")):
        f = pd.read_parquet(p, columns=["symbol", "trade_date", "open", "close", "dollar_adv_21"])
        f = f.loc[f["symbol"].isin(symbols)]
        if len(f):
            frames.append(f)
    panel = pd.concat(frames, ignore_index=True)
    close = panel.pivot(index="trade_date", columns="symbol", values="close").reindex(calendar)
    open_ = panel.pivot(index="trade_date", columns="symbol", values="open").reindex(calendar)
    adv = panel.pivot(index="trade_date", columns="symbol", values="dollar_adv_21").reindex(
        calendar
    )
    close, open_, hygiene_report = sanitize_price_matrices(close, open_)
    return {"close": close, "open": open_, "adv": adv, "hygiene_report": hygiene_report}


def load_bil(calendar: pd.DatetimeIndex) -> dict:
    from open_composer.research.features.price_hygiene import sanitize_price_matrices

    base.WARMUP_START = screen_lane.PANEL_START
    close, open_ = base.load_panel(["BIL"])
    close, open_, hygiene_report = sanitize_price_matrices(close, open_)
    leg_open, leg_close = salvage.legs(close, open_)
    close = close.reindex(calendar)
    leg_open = leg_open.reindex(calendar).fillna(0.0)
    leg_close = leg_close.reindex(calendar).fillna(0.0)
    return {
        "close": close["BIL"].to_numpy(),
        "leg_open": leg_open["BIL"].to_numpy(),
        "leg_close": leg_close["BIL"].to_numpy(),
        "hygiene_report": hygiene_report,
    }


# --------------------------------------------------------------------------
# ADV rank / momentum filter (computed at L-10, PIT)
# --------------------------------------------------------------------------


def adv_tier_bps(rank: float) -> float:
    if not np.isfinite(rank):
        return SPREAD_BPS_TIERS[-1][1]
    for threshold, bps in SPREAD_BPS_TIERS:
        if rank <= threshold:
            return bps
    return SPREAD_BPS_TIERS[-1][1]


def borrow_annual_rate(rank: float) -> float:
    if np.isfinite(rank) and rank <= 1500:
        return BORROW_ANNUAL_TOP1500
    return BORROW_ANNUAL_BEYOND


def compute_event_context(
    events: pd.DataFrame, calendar: pd.DatetimeIndex, panel: dict
) -> pd.DataFrame:
    """Adds ``l_idx`` (calendar position of L), ``adv_rank_l10``,
    ``ipo_to_l10_return`` to each event row. Events whose L or L-10 fall
    outside the panel's date range, or whose symbol has no ADV/close value
    at L-10, get NaN filter fields (excluded from ADV/momentum-filtered
    cells, but still eligible for the ``unrestricted``/``all`` cells)."""
    pos_by_date = {d: i for i, d in enumerate(calendar)}
    adv = panel["adv"]
    close = panel["close"]
    rows = []
    for row in events.itertuples(index=False):
        l_idx = pos_by_date.get(pd.Timestamp(row.lockup_date))
        if l_idx is None or l_idx < 10:
            rows.append({"l_idx": None, "adv_rank_l10": np.nan, "ipo_to_l10_return": np.nan})
            continue
        l10_idx = l_idx - 10
        l10_date = calendar[l10_idx]
        day_adv = adv.loc[l10_date]
        symbol_adv = day_adv.get(row.symbol, np.nan)
        if np.isfinite(symbol_adv):
            rank = int((day_adv > symbol_adv).sum()) + 1
        else:
            rank = np.nan
        first_close = close[row.symbol].loc[calendar >= pd.Timestamp(row.ipo_date)].dropna()
        l10_close = close.loc[l10_date, row.symbol] if row.symbol in close.columns else np.nan
        if len(first_close) and np.isfinite(l10_close):
            ipo_to_l10 = float(l10_close / first_close.iloc[0] - 1.0)
        else:
            ipo_to_l10 = np.nan
        rows.append({"l_idx": l_idx, "adv_rank_l10": rank, "ipo_to_l10_return": ipo_to_l10})
    ctx = pd.DataFrame(rows)
    return pd.concat([events.reset_index(drop=True), ctx], axis=1)


def filter_events(events: pd.DataFrame, adv_filter: str, mom_filter: str) -> pd.DataFrame:
    sub = events.dropna(subset=["l_idx"]).copy()
    if adv_filter == "adv1500":
        sub = sub.loc[sub["adv_rank_l10"] <= 1500]
    if mom_filter == "pos":
        sub = sub.loc[sub["ipo_to_l10_return"] > 0]
    elif mom_filter == "neg":
        sub = sub.loc[sub["ipo_to_l10_return"] <= 0]
    return sub


# --------------------------------------------------------------------------
# capacity-constrained event admission
# --------------------------------------------------------------------------


def admit_with_capacity(
    events: pd.DataFrame, offset_before: int, offset_after: int, n_sessions: int
) -> tuple[pd.DataFrame, int]:
    """Greedy first-come admission: an event is admitted only if it never
    pushes the concurrently-open count (among already-admitted events)
    above ``MAX_CONCURRENT`` on any day of its own holding window. Returns
    ``(admitted_events_with_entry_exit_idx, n_capacity_skipped)``."""
    sub = events.copy()
    sub["entry_sig_idx"] = sub["l_idx"] - offset_before
    sub["exit_sig_idx"] = sub["l_idx"] + offset_after
    sub = sub.loc[(sub["entry_sig_idx"] >= 0) & (sub["exit_sig_idx"] + 1 < n_sessions)]
    sub = sub.sort_values(["entry_sig_idx", "lockup_date", "symbol"]).reset_index(drop=True)
    open_count = np.zeros(n_sessions, dtype=np.int32)
    admitted_rows = []
    skipped = 0
    for row in sub.itertuples(index=False):
        start = int(row.entry_sig_idx) + 1
        end = int(row.exit_sig_idx) + 1  # inclusive last active day
        if open_count[start : end + 1].max(initial=0) >= MAX_CONCURRENT:
            skipped += 1
            continue
        open_count[start : end + 1] += 1
        admitted_rows.append(row._asdict())
    return pd.DataFrame(admitted_rows), skipped


# --------------------------------------------------------------------------
# book construction (short or long) for an admitted event set
# --------------------------------------------------------------------------


def build_book(
    admitted: pd.DataFrame,
    panel: dict,
    bil: dict,
    calendar: pd.DatetimeIndex,
    *,
    direction: float,
    cost_multiplier: float = 1.0,
) -> tuple[np.ndarray, dict]:
    """``direction`` is -1.0 for short, +1.0 for long (info-only). Returns
    ``(net_daily_return, diagnostics)``."""
    n_sessions = len(calendar)
    if admitted.empty:
        return np.zeros(n_sessions), {"n_events": 0}
    symbols = admitted["symbol"].tolist()
    close = panel["close"][symbols].to_numpy()
    open_ = panel["open"][symbols].to_numpy()
    leg_open, leg_close = stock_legs(open_, close)
    n_events = len(admitted)
    indicator = np.zeros((n_sessions, n_events), dtype=np.float64)
    cost_bps_col = np.zeros(n_events, dtype=np.float64)
    borrow_col = np.zeros(n_events, dtype=np.float64)
    for j, row in enumerate(admitted.itertuples(index=False)):
        start = int(row.entry_sig_idx) + 1
        end = int(row.exit_sig_idx) + 1
        indicator[start : end + 1, j] = 1.0
        cost_bps_col[j] = adv_tier_bps(row.adv_rank_l10) * cost_multiplier
        borrow_col[j] = (borrow_annual_rate(row.adv_rank_l10) * cost_multiplier) / BORROW_DAYCOUNT
    n_open = indicator.sum(axis=1)
    per_pos_weight = np.where(
        n_open > 0, np.minimum(1.0 / np.maximum(n_open, 1.0), MAX_WEIGHT_PER_POSITION), 0.0
    )
    stock_weights = indicator * per_pos_weight[:, None] * direction
    bil_weight = 1.0 - np.abs(stock_weights).sum(axis=1)

    combo_w = np.empty((n_sessions, n_events + 1), dtype=np.float64)
    combo_w[:, :n_events] = stock_weights
    combo_w[:, n_events] = bil_weight
    combo_leg_open = np.empty((n_sessions, n_events + 1), dtype=np.float64)
    combo_leg_open[:, :n_events] = leg_open
    combo_leg_open[:, n_events] = bil["leg_open"]
    combo_leg_close = np.empty((n_sessions, n_events + 1), dtype=np.float64)
    combo_leg_close[:, :n_events] = leg_close
    combo_leg_close[:, n_events] = bil["leg_close"]
    cost_bps_full = np.append(cost_bps_col, 0.0)
    borrow_full = np.append(borrow_col if direction < 0 else np.zeros(n_events), 0.0)

    net, _ = simulate_book(combo_w, combo_leg_open, combo_leg_close, cost_bps_full, borrow_full)
    diagnostics = {
        "n_events": n_events,
        "max_concurrent_realized": int(n_open.max()) if n_sessions else 0,
    }
    return net, diagnostics


# --------------------------------------------------------------------------
# per-trade stats (hit rate, avg return/trade, worst trade)
# --------------------------------------------------------------------------


_EMPTY_TRADE_STATS: dict[str, object] = {
    "n_trades": 0,
    "hit_rate_negative_car_pct": None,
    "hit_rate_profitable_after_cost_pct": None,
    "avg_return_per_trade_net": None,
    "median_return_per_trade_net": None,
    "trimmed_mean_1_99_return_per_trade_net": None,
    "worst_trade_net": None,
    "largest_abs_gross_return_trades": [],
    "car_series": [],
}


def per_trade_stats(
    admitted: pd.DataFrame, panel: dict, calendar: pd.DatetimeIndex, *, direction: float
) -> dict:
    """Per-trade P&L, after the coordinator's price-hygiene note (2026-09-29):
    ``panel["close"]``/``panel["open"]`` are already ``sanitize_price_matrices``-masked
    (NaN across a detected regime break), so a relisted/unadjusted-split
    price pair on either side of a break is skipped here by the same
    ``not np.isfinite(...)`` guard that already handled ordinary missing
    data -- no separate check is needed. Reports mean, median, and a
    1%/99%-trimmed mean side by side (per the coordinator's request) so a
    single extreme trade cannot be read as if it were typical, plus the 5
    largest ``|gross_trade_return|`` trades with symbol/date for a manual
    eyeball check."""
    if admitted.empty:
        return dict(_EMPTY_TRADE_STATS)
    open_ = panel["open"]
    records = []
    for row in admitted.itertuples(index=False):
        entry_date = calendar[int(row.entry_sig_idx) + 1]
        exit_date = calendar[int(row.exit_sig_idx) + 1]
        entry_px = open_.loc[entry_date, row.symbol]
        exit_px = open_.loc[exit_date, row.symbol]
        if not (np.isfinite(entry_px) and np.isfinite(exit_px)) or entry_px <= 0:
            continue
        raw_return = float(exit_px / entry_px - 1.0)  # long-side raw price change
        car = raw_return  # cumulative abnormal-return proxy: raw holding-period return
        gross_trade_return = -raw_return if direction < 0 else raw_return
        bps = adv_tier_bps(row.adv_rank_l10)
        rate = borrow_annual_rate(row.adv_rank_l10)
        n_days_held = int(row.exit_sig_idx) - int(row.entry_sig_idx)
        cost = 2.0 * bps / 1e4
        borrow_cost = rate / BORROW_DAYCOUNT * n_days_held if direction < 0 else 0.0
        net_trade_return = gross_trade_return - cost - borrow_cost
        records.append(
            {
                "symbol": row.symbol,
                "lockup_date": str(row.lockup_date),
                "entry_date": str(entry_date.date()),
                "exit_date": str(exit_date.date()),
                "car_raw_price_change": car,
                "gross_trade_return": gross_trade_return,
                "net_trade_return": net_trade_return,
            }
        )
    if not records:
        return dict(_EMPTY_TRADE_STATS)
    df = pd.DataFrame(records)
    trimmed_lo, trimmed_hi = df["net_trade_return"].quantile([0.01, 0.99])
    trimmed = df.loc[df["net_trade_return"].between(trimmed_lo, trimmed_hi), "net_trade_return"]
    largest = (
        df.assign(abs_gross=df["gross_trade_return"].abs())
        .sort_values("abs_gross", ascending=False)
        .head(5)[["symbol", "entry_date", "exit_date", "gross_trade_return", "net_trade_return"]]
        .to_dict(orient="records")
    )
    return {
        "n_trades": int(len(df)),
        "hit_rate_negative_car_pct": float((df["car_raw_price_change"] < 0).mean() * 100.0),
        "hit_rate_profitable_after_cost_pct": float((df["net_trade_return"] > 0).mean() * 100.0),
        "avg_return_per_trade_net": float(df["net_trade_return"].mean()),
        "median_return_per_trade_net": float(df["net_trade_return"].median()),
        "trimmed_mean_1_99_return_per_trade_net": float(trimmed.mean()) if len(trimmed) else None,
        "worst_trade_net": float(df["net_trade_return"].min()),
        "largest_abs_gross_return_trades": largest,
        "car_series": df.to_dict(orient="records"),
    }


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------


def annualized_metrics(ret: pd.Series) -> dict:
    if len(ret) == 0 or ret.std(ddof=1) == 0 or not np.isfinite(ret.std(ddof=1)):
        return {
            "cagr": float("nan"),
            "sharpe": float("nan"),
            "vol": float("nan"),
            "max_dd": float("nan"),
        }
    mean = float(ret.mean())
    std = float(ret.std(ddof=1))
    sharpe = mean / std * np.sqrt(252.0) if std > 0 else float("nan")
    equity = (1.0 + ret).cumprod()
    n_years = len(ret) / 252.0
    cagr = float(equity.iloc[-1] ** (1.0 / n_years) - 1.0) if n_years > 0 else float("nan")
    dd = (equity / equity.cummax() - 1.0).min()
    return {
        "cagr": cagr,
        "sharpe": float(sharpe),
        "vol": float(std * np.sqrt(252.0)),
        "max_dd": float(dd),
    }


def window_mask(index: pd.DatetimeIndex, window: tuple[str, str]) -> np.ndarray:
    a, b = pd.Timestamp(window[0]), pd.Timestamp(window[1])
    return (index >= a) & (index <= b)


def clustered_t_stat(
    real_car: np.ndarray, placebo_car: np.ndarray, dates: list[str]
) -> tuple[float, float]:
    """Real-minus-placebo CAR, t-stat clustered by event date (cluster =
    unique lockup_date string; within-cluster diffs averaged before the
    t-test so multiple events sharing an exact lockup date do not inflate
    the effective sample size)."""
    diff = real_car - placebo_car
    frame = pd.DataFrame({"date": dates, "diff": diff})
    by_date = frame.groupby("date")["diff"].mean()
    n = len(by_date)
    if n < 2:
        return float("nan"), float("nan")
    mean_diff = float(by_date.mean())
    se = float(by_date.std(ddof=1) / np.sqrt(n))
    t = mean_diff / se if se > 0 else float("nan")
    return mean_diff, t


# --------------------------------------------------------------------------
# placebos
# --------------------------------------------------------------------------


def shift_events(admitted: pd.DataFrame, shift_sessions: int, n_sessions: int) -> pd.DataFrame:
    """Date-shift placebo: same stocks, same window WIDTH, ``L`` moved by
    ``shift_sessions`` trading sessions. ``width_before``/``width_after``
    MUST be computed from the ORIGINAL ``l_idx`` before it is reassigned --
    computing them afterward (an earlier version of this function) algebraically
    cancels the shift out entirely (``new_entry = new_l - (new_l - old_entry)
    == old_entry``), silently making the "placebo" identical to the real
    trade. Caught by inspecting a first run's ``results.json``: every
    ``date_shift_*`` placebo showed ``mean_diff == 0.0`` and ``t_stat`` NaN
    (zero-variance real-minus-placebo diff) across all ~1,000 paired trades,
    which is what an identical-trade bug looks like, not what a real placebo
    result looks like."""
    sub = admitted.copy()
    width_before = sub["l_idx"] - sub["entry_sig_idx"]
    width_after = sub["exit_sig_idx"] - sub["l_idx"]
    sub["l_idx"] = sub["l_idx"] + shift_sessions
    sub["entry_sig_idx"] = sub["l_idx"] - width_before
    sub["exit_sig_idx"] = sub["l_idx"] + width_after
    sub = sub.loc[(sub["entry_sig_idx"] >= 0) & (sub["exit_sig_idx"] + 1 < n_sessions)]
    return sub


def random_date_events(admitted: pd.DataFrame, n_sessions: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    sub = admitted.copy()
    width_before = sub["l_idx"] - sub["entry_sig_idx"]
    width_after = sub["exit_sig_idx"] - sub["l_idx"]
    lo = int(width_before.max()) + 1
    hi = n_sessions - int(width_after.max()) - 2
    sub["l_idx"] = rng.integers(lo, hi, size=len(sub))
    sub["entry_sig_idx"] = sub["l_idx"] - width_before
    sub["exit_sig_idx"] = sub["l_idx"] + width_after
    return sub


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def evaluate_cell(
    cid: str,
    window: str,
    admitted_full: pd.DataFrame,
    panel: dict,
    bil: dict,
    calendar: pd.DatetimeIndex,
    *,
    direction: float,
    cost_multiplier: float = 1.0,
) -> dict:
    net, diag = build_book(
        admitted_full, panel, bil, calendar, direction=direction, cost_multiplier=cost_multiplier
    )
    ret = pd.Series(net, index=calendar)
    test_mask = window_mask(calendar, TEST_WINDOW)
    stress_mask = window_mask(calendar, STRESS_WINDOW)
    test_metrics = annualized_metrics(ret.loc[test_mask])
    stress_metrics = annualized_metrics(ret.loc[stress_mask])
    n_test_events = (
        int(
            (
                (admitted_full["l_idx"] >= calendar.searchsorted(pd.Timestamp(TEST_WINDOW[0])))
                & (admitted_full["l_idx"] <= calendar.searchsorted(pd.Timestamp(TEST_WINDOW[1])))
            ).sum()
        )
        if not admitted_full.empty
        else 0
    )
    trade_stats = per_trade_stats(admitted_full, panel, calendar, direction=direction)
    test_years = (pd.Timestamp(TEST_WINDOW[1]) - pd.Timestamp(TEST_WINDOW[0])).days / 365.25
    return {
        "candidate_id": cid,
        "window": window,
        "diagnostics": diag,
        "test_metrics": test_metrics,
        "stress_metrics": stress_metrics,
        "n_test_events": n_test_events,
        "trades_per_year_test": float(n_test_events / test_years) if test_years > 0 else None,
        "trade_stats": trade_stats,
        "return_series": ret,
    }


def main() -> None:
    t0 = time.monotonic()
    calendar = load_trading_calendar()
    events = pd.read_parquet(EVENTS_PATH)
    all_symbols = sorted(events["symbol"].unique())
    _log(f"loaded {len(events)} raw events, {len(all_symbols)} symbols", t0)
    panel = load_event_stock_panel(all_symbols, calendar)
    _log("loaded event stock panel", t0)
    bil = load_bil(calendar)
    _log("loaded BIL leg panel", t0)
    events = compute_event_context(events, calendar, panel)
    events.to_parquet(ITER_DIR / "events_with_context.parquet", index=False)
    n_sessions = len(calendar)

    results: dict[str, object] = {"cells": {}, "capacity_skipped": {}}
    cell_returns: dict[str, pd.Series] = {}

    for window, (before, after) in WINDOW_OFFSETS.items():
        for adv_f in ADV_FILTERS:
            for mom_f in MOM_FILTERS:
                cid = f"{window}_{adv_f}_{mom_f}"
                filtered = filter_events(events, adv_f, mom_f)
                admitted, skipped = admit_with_capacity(filtered, before, after, n_sessions)
                results["capacity_skipped"][cid] = skipped
                cell = evaluate_cell(cid, window, admitted, panel, bil, calendar, direction=-1.0)
                cell_returns[cid] = cell.pop("return_series")
                results["cells"][cid] = cell
                _log(
                    f"{cid}: n_events={cell['diagnostics']['n_events']} "
                    f"n_test_events={cell['n_test_events']}",
                    t0,
                )

    # info-only avoid-long row: L5L1 window, unrestricted/all filter, long direction
    filtered = filter_events(events, "unrestricted", "all")
    admitted, skipped = admit_with_capacity(filtered, *WINDOW_OFFSETS["L5L1"], n_sessions)
    results["capacity_skipped"]["avoid_long_info"] = skipped
    cell = evaluate_cell("avoid_long_info", "L5L1", admitted, panel, bil, calendar, direction=+1.0)
    cell_returns["avoid_long_info"] = cell.pop("return_series")
    results["cells"]["avoid_long_info"] = cell

    # rank tradeable cells by TEST sharpe (fallback: stress sharpe if test insufficient)
    tradeable_ids = [c for c in results["cells"] if c != "avoid_long_info"]

    def rank_key(cid: str) -> float:
        m = results["cells"][cid]["test_metrics"]
        s = m["sharpe"]
        return s if np.isfinite(s) else -1e9

    best_cid = max(tradeable_ids, key=rank_key)
    best = results["cells"][best_cid]
    best_ret = cell_returns[best_cid]
    _log(
        f"best cell by TEST sharpe: {best_cid} "
        f"sharpe={best['test_metrics']['sharpe']:.3f} "
        f"n_test_events={best['n_test_events']}",
        t0,
    )

    # placebos for the best cell
    window = best["window"]
    before, after = WINDOW_OFFSETS[window]
    adv_f, mom_f = best_cid.split("_")[1], best_cid.split("_")[2]
    filtered = filter_events(events, adv_f, mom_f)
    admitted, _ = admit_with_capacity(filtered, before, after, n_sessions)

    shifted_pos = shift_events(admitted, DATE_SHIFT_SESSIONS, n_sessions)
    shifted_neg = shift_events(admitted, -DATE_SHIFT_SESSIONS, n_sessions)
    random_ev = random_date_events(admitted, n_sessions, RANDOM_PLACEBO_SEED)

    real_trades = per_trade_stats(admitted, panel, calendar, direction=-1.0)
    shift_pos_trades = per_trade_stats(shifted_pos, panel, calendar, direction=-1.0)
    shift_neg_trades = per_trade_stats(shifted_neg, panel, calendar, direction=-1.0)
    random_trades = per_trade_stats(random_ev, panel, calendar, direction=-1.0)

    def align_and_tstat(real_stats: dict, placebo_stats: dict) -> dict:
        """Pairs real and placebo trades by their STABLE original-event
        identity (symbol, original lockup_date) -- ``shift_events``/
        ``random_date_events`` move ``l_idx``/``entry_sig_idx``/
        ``exit_sig_idx`` but never touch the ``lockup_date`` column, so it
        remains a valid join key across both. Positional truncation (an
        earlier version of this function) would silently mispair events
        whenever the shift/random redraw drops a different subset at the
        calendar boundary than the real run did."""
        real_df = pd.DataFrame(real_stats["car_series"])
        placebo_df = pd.DataFrame(placebo_stats["car_series"])
        if real_df.empty or placebo_df.empty:
            return {"n": 0, "mean_diff": None, "t_stat": None}
        merged = real_df.merge(
            placebo_df, on=["symbol", "lockup_date"], suffixes=("_real", "_placebo")
        )
        n = len(merged)
        if n < 2:
            return {"n": n, "mean_diff": None, "t_stat": None}
        mean_diff, t = clustered_t_stat(
            -merged["car_raw_price_change_real"].to_numpy(),  # short P&L direction
            -merged["car_raw_price_change_placebo"].to_numpy(),
            merged["lockup_date"].tolist(),
        )
        return {"n": n, "mean_diff": mean_diff, "t_stat": t}

    placebo_results = {
        "date_shift_plus60": align_and_tstat(real_trades, shift_pos_trades),
        "date_shift_minus60": align_and_tstat(real_trades, shift_neg_trades),
        "random_date": align_and_tstat(real_trades, random_trades),
    }
    _log(f"placebos for {best_cid}: {json.dumps(placebo_results)}", t0)

    # 2x-cost rerun for best cell
    best_2x = evaluate_cell(
        best_cid, window, admitted, panel, bil, calendar, direction=-1.0, cost_multiplier=2.0
    )
    best_2x.pop("return_series")

    # S3 correlation / diversifier edge for the best cell
    close_etf, open_etf = base.load_panel(
        sorted(set(salvage.symbols()) | {screen_lane.CASH, screen_lane.RF})
    )
    leg_open_etf, leg_close_etf = salvage.legs(close_etf, open_etf)
    rf = (close_etf[screen_lane.RF] / close_etf[screen_lane.RF].shift(1) - 1.0).fillna(0.0)
    shy_ret = (close_etf[screen_lane.CASH] / close_etf[screen_lane.CASH].shift(1) - 1.0).fillna(0.0)
    s3_ret, _ = screen_lane.s3_incumbent(
        close_etf, leg_open_etf, leg_close_etf, screen_lane.COST_BPS_PRIMARY
    )

    try:
        corr_s3 = screen_lane.correlation_with_s3(best_ret, s3_ret, TEST_WINDOW)
    except AssertionError as exc:
        corr_s3 = None
        _log(f"correlation_with_s3 raised (convention check): {exc}", t0)
    try:
        edge = screen_lane.diversifier_edge_for_offset(s3_ret, best_ret, shy_ret, rf, TEST_WINDOW)
    except AssertionError as exc:
        edge = None
        _log(f"diversifier_edge_for_offset raised (convention check): {exc}", t0)

    # DSR on the judged best candidate's TEST daily return series
    test_mask = window_mask(calendar, TEST_WINDOW)
    best_test_ret = best_ret.loc[test_mask].dropna().to_numpy()
    try:
        dsr = deflated_sharpe_probability(best_test_ret, trial_count=N_TRIALS, hac_lag=DSR_HAC_LAG)
    except ValueError as exc:
        dsr = None
        _log(f"DSR unavailable: {exc}", t0)

    n_test_events_best = best["n_test_events"]
    decision_rule = {
        "sharpe_or_edge_pass": bool(
            (
                np.isfinite(best["test_metrics"]["sharpe"])
                and best["test_metrics"]["sharpe"] >= K1_ANCHOR_SHARPE_MIN
            )
            or (edge is not None and edge >= EDGE_MIN)
        ),
        "placebo_pass": bool(
            all(
                p["t_stat"] is not None and np.isfinite(p["t_stat"]) and p["t_stat"] >= 2.0
                for p in [
                    placebo_results["date_shift_plus60"],
                    placebo_results["date_shift_minus60"],
                ]
            )
        ),
        "survives_2x_costs": bool(
            np.isfinite(best_2x["test_metrics"]["sharpe"])
            and (best["test_metrics"]["sharpe"] <= 0 or best_2x["test_metrics"]["sharpe"] > 0)
        ),
        "sufficient_test_events": bool(n_test_events_best >= MIN_TEST_EVENTS),
    }
    if not decision_rule["sufficient_test_events"]:
        verdict_window = "STRESS"
        stress_pass = bool(
            np.isfinite(best["stress_metrics"]["sharpe"])
            and best["stress_metrics"]["sharpe"] >= K1_ANCHOR_SHARPE_MIN
        )
        overall_verdict = "insufficient_test_events_stress_decides"
    else:
        verdict_window = "TEST"
        stress_pass = None
        overall_verdict = "admitted" if all(decision_rule.values()) else "refuted"

    out = {
        "iter_id": "h20260929_21_ipo_lockup_expiry",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "test_window": TEST_WINDOW,
        "stress_window": STRESS_WINDOW,
        "n_candidates": N_TRIALS,
        "cells": results["cells"],
        "capacity_skipped": results["capacity_skipped"],
        "best_candidate_id": best_cid,
        "best_candidate_2x_costs": best_2x,
        "placebos": placebo_results,
        "correlation_with_s3_test": corr_s3,
        "diversifier_edge_vs_s3_test": edge,
        "dsr_probability": dsr,
        "dsr_trial_count": N_TRIALS,
        "decision_rule": decision_rule,
        "verdict_window": verdict_window,
        "stress_pass_if_used": stress_pass,
        "overall_verdict": overall_verdict,
        "event_counts": {
            "total_raw_events": int(len(events)),
            "by_method": {k: int(v) for k, v in events["method"].value_counts().items()},
        },
        "price_hygiene": {
            "event_stock_panel": panel["hygiene_report"].manifest(),
            "bil_panel": bil["hygiene_report"].manifest(),
            "note": (
                "sanitize_price_matrices (default thresholds: 10x one-day jump, "
                "5-session gap) applied to close/open before any return was "
                "computed, per the coordinator's 2026-09-29 note (T-20 found "
                "post-bankruptcy relistings, unadjusted splits and one-day bad "
                "prints in data/sip/daily). Ghost-bar dropping was not run at "
                "this layer -- data/features/daily_broad exposes no volume/"
                "trade_count column -- and is presumed already applied upstream "
                "by the feature build; not independently re-verified here."
            ),
        },
    }
    (ITER_DIR / "results.json").write_text(
        json.dumps(
            out, indent=2, default=lambda x: float(x) if isinstance(x, np.floating) else str(x)
        )
    )
    _log(f"wrote results.json; overall_verdict={overall_verdict}", t0)


if __name__ == "__main__":
    main()
