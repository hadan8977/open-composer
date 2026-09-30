"""T-20260930-03: year-end tax-loss rebound, ten December windows 2016-2025.

Frozen design: ``reports/research/iterations/h20260930_03_tax_loss_year_end/
hypotheses.md`` (restating queue task T-20260930-03; nothing here changes a
number). Long-only equal-weight baskets of the lowest year-to-date (YTD)
performers on the 15th of a month, entered at the next open, versus the
equal-weight pool, after ADV-tiered costs. W2 = the main December window,
W1 = 15 November -> 15 December diagnostic, PFEB / PJUN = off-season placebo
windows built the same way.

Memory: one calendar-year segment (15 December of the prior year to 5 February
of the next year, roughly 3.4M daily bars) is read from ``data/sip/daily`` at a
time and released; run it under ``scripts/run_capped.sh --mem 1.2G``.
Prices pass ``sanitize_price_matrices`` (defaults) before any return is
computed, and symbols with a split-like one-day close ratio between the YTD
baseline day and the exit day are excluded from pool and baskets alike.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_h20260929_21_lockups import (  # noqa: E402
    ASSET_METADATA_PATH,
    load_non_common_stock_symbols,
)
from run_h20260929_21_lockup_books import SPREAD_BPS_TIERS, adv_tier_bps  # noqa: E402
from run_t20260929_32_gap_fade_ls import is_split_like_ratio  # noqa: E402

ITER_ID = "h20260930_03_tax_loss_year_end"
ITER_DIR = ROOT / "reports/research/iterations" / ITER_ID
SIP_DAILY_GLOB = (ROOT / "data/sip/daily/*/*.parquet").as_posix()

YEARS = list(range(2016, 2026))
POOL_TOP_N = 1500
POOL_B_MIN_RANK_EXCLUSIVE = 500  # pool B = ranks 501-1500
MIN_PRICE = 5.0
ADV_WINDOW = 21
ADV_MIN_VALID = 15
DECILE_Q = 0.10
LOSS_THRESHOLD = -0.30
# frozen continue conditions
MIN_MEAN_EXCESS = 0.015
MIN_POSITIVE_YEARS = 7
MIN_T = 2.0
PLACEBO_MAX_FRACTION = 0.5
RECENT_YEARS = (2024, 2025)  # Dec 2024 -> Jan 2025 and Dec 2025 -> Jan 2026
FORWARD_NOT_BEFORE = "2026-12-15"

# window -> (signal month, day, year offset), exit key -> (month, day, year offset)
WINDOWS: dict[str, dict] = {
    "W2": {"signal": (12, 15, 0), "exits": {"X15": (1, 15, 1), "X31": (1, 31, 1)}},
    "W1": {"signal": (11, 15, 0), "exits": {"X1215": (12, 15, 0)}},
    "PFEB": {"signal": (2, 15, 0), "exits": {"X15": (3, 15, 0), "X31": (3, 31, 0)}},
    "PJUN": {"signal": (6, 15, 0), "exits": {"X15": (7, 15, 0), "X31": (7, 31, 0)}},
}
# shape id -> (selection, pool)
SHAPES = {
    "D10_A": ("decile", "A"),
    "D10_B": ("decile", "B"),
    "L30_A": ("loss30", "A"),
}
CANDIDATES = [
    ("D10_A_X0115", "D10_A", "X15"),
    ("D10_A_X0131", "D10_A", "X31"),
    ("D10_B_X0115", "D10_B", "X15"),
    ("D10_B_X0131", "D10_B", "X31"),
    ("L30_A_X0115", "L30_A", "X15"),
    ("L30_A_X0131", "L30_A", "X31"),
]


def _log(msg: str, t0: float) -> None:
    print(f"[{time.time() - t0:7.1f}s] {msg}", flush=True)


# --------------------------------------------------------------------------
# calendar rules
# --------------------------------------------------------------------------


def last_trading_day_on_or_before(cal: pd.DatetimeIndex, ts: pd.Timestamp) -> int | None:
    """Position in ``cal`` of the last session <= ``ts``, or None."""
    pos = int(cal.searchsorted(ts, side="right")) - 1
    return pos if pos >= 0 else None


def first_trading_day_on_or_after(cal: pd.DatetimeIndex, ts: pd.Timestamp) -> int | None:
    pos = int(cal.searchsorted(ts, side="left"))
    return pos if pos < len(cal) else None


def window_positions(
    cal: pd.DatetimeIndex, year: int, window: str, exit_key: str
) -> dict[str, int | None]:
    """Signal / entry / exit session positions for ``year``'s ``window``.

    Signal day = last session on or before the 15th (the signal uses only that
    close and earlier); entry = first session on or after the 16th; exit =
    last session on or before the target day.
    """
    spec = WINDOWS[window]
    s_month, s_day, s_off = spec["signal"]
    e_month, e_day, e_off = spec["exits"][exit_key]
    sig_date = pd.Timestamp(year + s_off, s_month, s_day)
    entry_date = sig_date + pd.Timedelta(days=1)
    exit_date = pd.Timestamp(year + e_off, e_month, e_day)
    return {
        "signal": last_trading_day_on_or_before(cal, sig_date),
        "entry": first_trading_day_on_or_after(cal, entry_date),
        "exit": last_trading_day_on_or_before(cal, exit_date),
    }


def baseline_position(cal: pd.DatetimeIndex, year: int) -> tuple[int | None, str]:
    """(position, price field) of the YTD baseline: last close of the prior year.

    When the prior year is absent from the data (2016), the first session's
    open is the documented proxy.
    """
    prior = last_trading_day_on_or_before(cal, pd.Timestamp(year - 1, 12, 31))
    if prior is not None and cal[prior].year == year - 1:
        return prior, "close"
    first = first_trading_day_on_or_after(cal, pd.Timestamp(year, 1, 1))
    return first, "open"


# --------------------------------------------------------------------------
# pool and returns for one window
# --------------------------------------------------------------------------


def tier_bps_per_side(rank: float) -> float:
    return adv_tier_bps(rank)


def build_pool_frame(
    close: pd.DataFrame,
    open_: pd.DataFrame,
    volume: pd.DataFrame,
    *,
    base_pos: int,
    base_field: str,
    sig_pos: int,
    entry_pos: int,
    exit_pos: int,
) -> tuple[pd.DataFrame, dict]:
    """Pool A (ADV rank <= 1,500) with YTD, rank, tier and window return.

    The YTD and the ADV use only rows <= ``sig_pos``. Hygiene exclusions
    (split-like ratio between baseline and exit, no exit price) are applied
    after ranking and counted.
    """
    base_px = (close if base_field == "close" else open_).iloc[base_pos]
    sig_close = close.iloc[sig_pos]
    entry_open = open_.iloc[entry_pos]
    with np.errstate(invalid="ignore", divide="ignore"):
        ytd = sig_close / base_px - 1.0
    dollar = (close * volume).iloc[max(0, sig_pos - ADV_WINDOW + 1) : sig_pos + 1]
    adv = dollar.median(axis=0)
    adv[dollar.count(axis=0) < ADV_MIN_VALID] = np.nan
    valid = (
        np.isfinite(ytd)
        & np.isfinite(entry_open)
        & np.isfinite(adv)
        & (sig_close >= MIN_PRICE)
        & (base_px > 0)
        & (entry_open > 0)
    )
    ranked = adv[valid].rank(ascending=False, method="first")
    pool_syms = ranked.index[ranked <= POOL_TOP_N]
    counts = {"n_valid_universe": int(valid.sum()), "n_pool_before_hygiene": int(len(pool_syms))}

    seg = close.iloc[base_pos : exit_pos + 1][pool_syms]
    prev = seg.iloc[:-1].to_numpy()
    nxt = seg.iloc[1:].to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = nxt / prev
    split_like = is_split_like_ratio(ratio).any(axis=0)
    hold = close.iloc[entry_pos : exit_pos + 1][pool_syms]
    exit_px = hold.ffill().iloc[-1]
    exit_missing_last = hold.iloc[-1].isna()
    frame = pd.DataFrame(
        {
            "ytd": ytd[pool_syms],
            "rank": ranked[pool_syms],
            "entry_open": entry_open[pool_syms],
            "exit_px": exit_px,
            "split_like": split_like,
            "early_term": exit_missing_last & exit_px.notna(),
        }
    )
    counts["n_split_like_excluded"] = int(frame["split_like"].sum())
    counts["n_no_exit_excluded"] = int((~np.isfinite(frame["exit_px"])).sum())
    frame = frame.loc[~frame["split_like"] & np.isfinite(frame["exit_px"])].copy()
    frame["ret"] = frame["exit_px"] / frame["entry_open"] - 1.0
    frame["tier_bp"] = [tier_bps_per_side(r) for r in frame["rank"]]
    counts["n_pool"] = int(len(frame))
    counts["n_early_term_in_pool"] = int(frame["early_term"].sum())
    return frame, counts


def select_basket(frame: pd.DataFrame, shape: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(pool, basket) for a candidate shape; the benchmark is that pool."""
    selection, pool_id = SHAPES[shape]
    pool = frame if pool_id == "A" else frame.loc[frame["rank"] > POOL_B_MIN_RANK_EXCLUSIVE]
    if len(pool) == 0:
        return pool, pool
    if selection == "decile":
        thr = float(np.quantile(pool["ytd"].to_numpy(), DECILE_Q))
        basket = pool.loc[pool["ytd"] <= thr]
    else:
        basket = pool.loc[pool["ytd"] <= LOSS_THRESHOLD]
    return pool, basket


def basket_metrics(pool: pd.DataFrame, basket: pd.DataFrame, iwm_ret: float) -> dict:
    if len(basket) == 0 or len(pool) == 0:
        return {
            "n_pool": int(len(pool)),
            "n_selected": int(len(basket)),
            "basket_gross": None,
            "cost": None,
            "basket_net": None,
            "pool_ret": None,
            "excess_gross": None,
            "excess_net": None,
            "iwm_ret": iwm_ret,
            "excess_net_vs_iwm": None,
        }
    gross = float(basket["ret"].mean())
    cost = float((2.0 * basket["tier_bp"] / 1e4).mean())
    net = gross - cost
    pool_ret = float(pool["ret"].mean())
    return {
        "n_pool": int(len(pool)),
        "n_selected": int(len(basket)),
        "basket_gross": gross,
        "cost": cost,
        "basket_net": net,
        "pool_ret": pool_ret,
        "excess_gross": gross - pool_ret,
        "excess_net": net - pool_ret,
        "iwm_ret": iwm_ret,
        "excess_net_vs_iwm": net - iwm_ret if np.isfinite(iwm_ret) else None,
        "mean_ytd_selected": float(basket["ytd"].mean()),
        "mean_tier_bp_selected": float(basket["tier_bp"].mean()),
    }


# --------------------------------------------------------------------------
# statistics and verdict
# --------------------------------------------------------------------------


def annual_stats(values: list[float | None]) -> dict:
    arr = np.array([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    n = len(arr)
    if n < 2:
        return {
            "n": n,
            "mean": float(arr.mean()) if n else None,
            "t_clustered": None,
            "n_positive": int((arr > 0).sum()),
            "mean_without_best": None,
        }
    sd = float(arr.std(ddof=1))
    mean = float(arr.mean())
    t = mean / (sd / np.sqrt(n)) if sd > 0 else None
    without_best = np.delete(arr, int(arr.argmax()))
    return {
        "n": n,
        "mean": mean,
        "std": sd,
        "t_clustered": t,
        "n_positive": int((arr > 0).sum()),
        "mean_without_best": float(without_best.mean()),
    }


def evaluate_conditions(
    real_values: dict[int, float | None],
    placebo_feb_mean: float | None,
    placebo_jun_mean: float | None,
) -> dict:
    """The five frozen continue conditions for one candidate.

    ``real_values``: signal year -> net excess of the candidate's window.
    """
    ordered = [real_values.get(y) for y in YEARS]
    st = annual_stats(ordered)
    complete = st["n"] == len(YEARS)
    mean = st["mean"]
    c1 = bool(complete and mean is not None and mean >= MIN_MEAN_EXCESS)
    c2 = bool(complete and st["n_positive"] >= MIN_POSITIVE_YEARS)
    c3 = bool(complete and st["t_clustered"] is not None and st["t_clustered"] >= MIN_T)
    if (
        complete
        and mean is not None
        and placebo_feb_mean is not None
        and placebo_jun_mean is not None
    ):
        placebo_sum = placebo_feb_mean + placebo_jun_mean
        c4 = bool(mean > 0 and placebo_sum <= PLACEBO_MAX_FRACTION * mean)
    else:
        placebo_sum = None
        c4 = False
    recent = {str(y): real_values.get(y) for y in RECENT_YEARS}
    c5 = bool(all(v is not None and v > 0 for v in recent.values()))
    return {
        "stats": st,
        "recent_windows": recent,
        "placebo_feb_mean": placebo_feb_mean,
        "placebo_jun_mean": placebo_jun_mean,
        "placebo_sum": placebo_sum,
        "placebo_average": None if placebo_sum is None else placebo_sum / 2.0,
        "conditions": {
            "c1_mean_net_excess_ge_1p5pct": {
                "value": mean,
                "threshold": MIN_MEAN_EXCESS,
                "pass": c1,
            },
            "c2_positive_years_ge_7": {
                "value": st["n_positive"],
                "threshold": MIN_POSITIVE_YEARS,
                "pass": c2,
            },
            "c3_clustered_t_ge_2": {"value": st["t_clustered"], "threshold": MIN_T, "pass": c3},
            "c4_placebo_sum_le_half_real_mean": {
                "value": placebo_sum,
                "threshold": None if mean is None else PLACEBO_MAX_FRACTION * mean,
                "pass": c4,
            },
            "c5_dec2024_and_dec2025_positive": {"value": recent, "threshold": 0.0, "pass": c5},
        },
        "all_pass": bool(c1 and c2 and c3 and c4 and c5),
    }


# --------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------


def excluded_symbols() -> tuple[set[str], dict]:
    meta = pd.read_parquet(ASSET_METADATA_PATH, columns=["symbol", "is_probable_fund_or_etf"])
    funds = set(meta.loc[meta["is_probable_fund_or_etf"].fillna(False).astype(bool), "symbol"])
    non_common = load_non_common_stock_symbols()
    excl = funds | non_common
    return excl, {
        "fund_name_filter_symbols": len(funds),
        "non_common_name_filter_symbols": len(non_common),
        "metadata_rows": int(len(meta)),
    }


def load_year_segment(year: int, excl: set[str]) -> tuple[dict, pd.Series | None]:
    """close / open / volume matrices for one segment plus the IWM open/close."""
    start = "2016-01-01" if year == YEARS[0] else f"{year - 1}-12-15"
    end = f"{year + 1}-02-05"
    con = duckdb.connect()
    con.execute("SET memory_limit='700MB'; SET threads=2;")
    con.register("excl", pd.DataFrame({"symbol": sorted(excl)}))
    query = f"""
        SELECT symbol, CAST(timestamp AS DATE) AS date, open, close, volume
        FROM read_parquet('{SIP_DAILY_GLOB}')
        WHERE timestamp >= TIMESTAMPTZ '{start} 00:00:00+00'
          AND timestamp < TIMESTAMPTZ '{end} 00:00:00+00'
          AND open > 0 AND close > 0
          AND NOT (volume = 0 AND COALESCE(trade_count, 0) = 0)
    """
    long = con.execute(query).df()
    con.close()
    long["date"] = pd.to_datetime(long["date"])
    iwm = long.loc[long["symbol"] == "IWM"].set_index("date")[["open", "close"]].sort_index()
    long = long.loc[~long["symbol"].isin(excl)]
    mats = {}
    for col in ("close", "open", "volume"):
        mats[col] = long.pivot(index="date", columns="symbol", values=col).sort_index()
    n_rows = len(long)
    del long
    cal = mats["close"].index
    mats["open"] = mats["open"].reindex(index=cal, columns=mats["close"].columns)
    mats["volume"] = mats["volume"].reindex(index=cal, columns=mats["close"].columns)
    mats["n_rows"] = n_rows
    return mats, iwm


def run_year(year: int, excl: set[str], t0: float) -> tuple[dict, dict]:
    from open_composer.research.features.price_hygiene import sanitize_price_matrices

    mats, iwm = load_year_segment(year, excl)
    close, open_, hyg = sanitize_price_matrices(mats["close"], mats["open"])
    volume = mats["volume"]
    cal = close.index
    _log(
        f"{year}: {mats['n_rows']:,} bars, {close.shape[1]:,} symbols, "
        f"hygiene masked {hyg.symbols_masked} symbols / {hyg.price_cells_masked} cells",
        t0,
    )
    base_pos, base_field = baseline_position(cal, year)
    out: dict = {}
    counts: dict = {}
    for window, spec in WINDOWS.items():
        for exit_key in spec["exits"]:
            pos = window_positions(cal, year, window, exit_key)
            if (
                base_pos is None
                or any(v is None for v in pos.values())
                or not (base_pos < pos["signal"] < pos["entry"] <= pos["exit"])
            ):
                out[(window, exit_key)] = None
                continue
            frame, cnt = build_pool_frame(
                close,
                open_,
                volume,
                base_pos=base_pos,
                base_field=base_field,
                sig_pos=pos["signal"],
                entry_pos=pos["entry"],
                exit_pos=pos["exit"],
            )
            iwm_ret = float("nan")
            if len(iwm) and cal[pos["entry"]] in iwm.index and cal[pos["exit"]] in iwm.index:
                iwm_ret = float(
                    iwm.loc[cal[pos["exit"]], "close"] / iwm.loc[cal[pos["entry"]], "open"] - 1.0
                )
            per_shape = {}
            for shape in SHAPES:
                pool, basket = select_basket(frame, shape)
                per_shape[shape] = basket_metrics(pool, basket, iwm_ret)
            per_shape["_dates"] = {
                "baseline": str(cal[base_pos].date()) + f" ({base_field})",
                "signal": str(cal[pos["signal"]].date()),
                "entry": str(cal[pos["entry"]].date()),
                "exit": str(cal[pos["exit"]].date()),
            }
            out[(window, exit_key)] = per_shape
            counts[f"{window}/{exit_key}"] = cnt
    hyg_summary = {
        "symbols_masked": hyg.symbols_masked,
        "symbols_masked_for_jump": hyg.symbols_masked_for_jump,
        "symbols_masked_for_gap": hyg.symbols_masked_for_gap,
        "price_cells_masked": hyg.price_cells_masked,
        "contract": hyg.contract,
    }
    return out, {"pool_counts": counts, "hygiene": hyg_summary, "n_bars": mats["n_rows"]}


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def collect(annual: dict[int, dict], window: str, exit_key: str, shape: str, field: str):
    vals = {}
    for y in YEARS:
        rec = annual[y].get((window, exit_key))
        vals[y] = None if rec is None else rec[shape].get(field)
    return vals


def mean_of(vals: dict[int, float | None]) -> float | None:
    arr = [v for v in vals.values() if v is not None and np.isfinite(v)]
    return float(np.mean(arr)) if len(arr) == len(YEARS) else None


def assemble(annual: dict[int, dict], meta_by_year: dict[int, dict]) -> dict:
    tables: dict = {}
    for window, spec in WINDOWS.items():
        tables[window] = {}
        for exit_key in spec["exits"]:
            tables[window][exit_key] = {}
            for shape in SHAPES:
                rows = []
                for y in YEARS:
                    rec = annual[y].get((window, exit_key))
                    if rec is None:
                        rows.append({"year": y, "missing": True})
                        continue
                    rows.append({"year": y, **rec[shape], "dates": rec["_dates"]})
                tables[window][exit_key][shape] = rows

    candidates_out = {}
    n_pass = 0
    for cid, shape, exit_key in CANDIDATES:
        real = collect(annual, "W2", exit_key, shape, "excess_net")
        feb = mean_of(collect(annual, "PFEB", exit_key, shape, "excess_net"))
        jun = mean_of(collect(annual, "PJUN", exit_key, shape, "excess_net"))
        ev = evaluate_conditions(real, feb, jun)
        gross = collect(annual, "W2", exit_key, shape, "excess_gross")
        iwm = collect(annual, "W2", exit_key, shape, "excess_net_vs_iwm")
        real_9 = {y: v for y, v in real.items() if y != YEARS[0]}
        ev["annual_net_excess"] = {str(y): real[y] for y in YEARS}
        ev["annual_gross_excess"] = {str(y): gross[y] for y in YEARS}
        ev["annual_basket_net"] = {
            str(y): v for y, v in collect(annual, "W2", exit_key, shape, "basket_net").items()
        }
        ev["annual_pool_return"] = {
            str(y): v for y, v in collect(annual, "W2", exit_key, shape, "pool_ret").items()
        }
        ev["annual_n_selected"] = {
            str(y): v for y, v in collect(annual, "W2", exit_key, shape, "n_selected").items()
        }
        ev["gross_excess_stats"] = annual_stats([gross[y] for y in YEARS])
        ev["iwm_hedged_stats"] = annual_stats([iwm[y] for y in YEARS])
        ev["iwm_hedged_annual"] = {str(y): iwm[y] for y in YEARS}
        ev["sensitivity_2017_2025_stats"] = annual_stats([real_9[y] for y in real_9])
        ev["placebo_feb_stats"] = annual_stats(
            list(collect(annual, "PFEB", exit_key, shape, "excess_net").values())
        )
        ev["placebo_jun_stats"] = annual_stats(
            list(collect(annual, "PJUN", exit_key, shape, "excess_net").values())
        )
        ev["failed_conditions"] = [k for k, v in ev["conditions"].items() if not v["pass"]]
        candidates_out[cid] = {"shape": shape, "exit": exit_key, **ev}
        n_pass += int(ev["all_pass"])

    w1 = {}
    for shape in SHAPES:
        net = collect(annual, "W1", "X1215", shape, "excess_net")
        gross = collect(annual, "W1", "X1215", shape, "excess_gross")
        w1[shape] = {
            "net_excess_stats": annual_stats([net[y] for y in YEARS]),
            "gross_excess_stats": annual_stats([gross[y] for y in YEARS]),
            "annual_net_excess": {str(y): net[y] for y in YEARS},
            "annual_gross_excess": {str(y): gross[y] for y in YEARS},
            "direction": (
                "underperforms pool (expected direction)"
                if (mean_of(gross) is not None and mean_of(gross) < 0)
                else "does not underperform pool"
            ),
        }

    verdict = {
        "n_candidates": len(CANDIDATES),
        "n_candidates_passing_all_five": n_pass,
        "overall": "watch_recent_forward_only" if n_pass else "refuted",
        "label": (
            "recent observation only (ten windows); 2026-12-15 is the real out-of-sample test"
            if n_pass
            else "tax-loss rebound closed"
        ),
        "passing_candidates": [c for c, v in candidates_out.items() if v["all_pass"]],
    }
    if n_pass:
        verdict["forward_tracking_suggestion"] = {
            "not_before": FORWARD_NOT_BEFORE,
            "task": (
                "Forward-only tracking of the passing candidate(s): signal on the 2026-12-15 "
                "close, entry at the next open, exits 2027-01-15 / 2027-01-29, same tiered "
                "costs and pool benchmark; no paper trading without the owner's authorization."
            ),
        }
    return {"tables": tables, "candidates": candidates_out, "w1_diagnostic": w1, "verdict": verdict}


def _clean(obj):
    """Recursively turn NaN/inf/numpy scalars into JSON-safe values."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj) if np.isfinite(obj) else None
    return obj


def main() -> None:
    t0 = time.time()
    excl, excl_meta = excluded_symbols()
    _log(f"excluded symbols: {len(excl):,} ({excl_meta})", t0)
    annual: dict[int, dict] = {}
    meta_by_year: dict[int, dict] = {}
    for year in YEARS:
        annual[year], meta_by_year[year] = run_year(year, excl, t0)
    body = assemble(annual, meta_by_year)
    result = {
        "iter_id": ITER_ID,
        "generated_by": "scripts/run_h20260930_03_tax_loss_year_end.py",
        "design": "reports/research/iterations/h20260930_03_tax_loss_year_end/hypotheses.md",
        "years": YEARS,
        "frozen": {
            "pool_top_n": POOL_TOP_N,
            "pool_b": "ADV rank 501-1500",
            "min_price": MIN_PRICE,
            "adv": (
                f"median of close x volume over {ADV_WINDOW} sessions (>= {ADV_MIN_VALID} valid)"
            ),
            "cost_tiers_bp_per_side": [[a, b] for a, b in SPREAD_BPS_TIERS[:3]],
            "decile_q": DECILE_Q,
            "loss_threshold": LOSS_THRESHOLD,
            "conditions": {
                "min_mean_excess": MIN_MEAN_EXCESS,
                "min_positive_years": MIN_POSITIVE_YEARS,
                "min_t": MIN_T,
                "placebo_sum_max_fraction_of_real_mean": PLACEBO_MAX_FRACTION,
                "recent_windows": list(RECENT_YEARS),
            },
            "baseline_2016_note": (
                "data start 2016-01-04: the 2016 YTD baseline is the 2016-01-04 open "
                "(documented proxy for the 2015 last close)"
            ),
            "excess_definition": (
                "net basket return (gross minus 2 x tier bp, mean over names) "
                "minus costless equal-weight pool return"
            ),
        },
        "exclusion_filters": excl_meta,
        "per_year_meta": {str(y): meta_by_year[y] for y in YEARS},
        **body,
        "runtime_seconds": time.time() - t0,
    }
    ITER_DIR.mkdir(parents=True, exist_ok=True)
    out = ITER_DIR / "results.json"
    out.write_text(json.dumps(_clean(result), indent=2) + "\n")
    _log(f"wrote {out}; verdict {result['verdict']['overall']}", t0)


if __name__ == "__main__":
    main()
