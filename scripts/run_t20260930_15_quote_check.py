# ruff: noqa: E501
"""T-20260930-15: measured-quote check of T-20260930-13's two decision cells (A1 + A2).

Design is frozen in ``reports/research/iterations/t20260930_13_intraday_periodicity/``:
``hypotheses.md`` + ``amendment-2026-09-30-measured-spread.md`` (A1: sampling, SIP NBBO,
last valid quote) + ``amendment-2026-09-30-a2-executable-quotes.md`` (A2: executable returns,
gap ``s``, mechanical tier; A2 wins where they differ).  This script only executes it: it
never changes the picks, the gross mean ``m``, ``t`` or the placebo numbers.

Credentials live only in the ``DataSession`` request headers; nothing here prints or stores them.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

ITERATION_ID = "t20260930_13_intraday_periodicity"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = OUT_DIR / "cache"
EXTRACT_DIR = CACHE_DIR / "extract"
QUOTE_CACHE = CACHE_DIR / "quotes"
RESULTS_PATH = OUT_DIR / "results.json"
OUT_JSON = OUT_DIR / "quote-check.json"
OUT_MD = OUT_DIR / "quote-check.md"

QUOTES_URL = "https://data.alpaca.markets/v2/stocks/quotes"
BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
NY = ZoneInfo("America/New_York")
SEED = 20260930
N_DAYS = 30
BATCH = 100
LIMIT = 10000
WINDOW_S = (5, 60)
MAX_PAGES = 200
CELLS = ("C_L20_P1500", "O_L20_P1500")
# (period, ET time of day of the quote check)
T_ENTRY = {"C": (15, 30), "O": (10, 0)}
T_DIAG = (15, 50)
BUFFER_1X_BP = 8.0  # A2: 2 bp x 4 (continuous + auction leg, both legs), see A2 "说明"
BUFFER_2X_BP = 16.0
T_MIN = 2.0
BEAT_MIN = 0.90
BP = 1e4


# --------------------------------------------------------------------------
# pure logic (unit tested)
# --------------------------------------------------------------------------


def sample_days(trading_days: Any) -> list[str]:
    """30 seeded days (A1/A2): ``default_rng(20260930).choice(days, 30, replace=False)``
    over the ascending, de-duplicated trading days; returned ascending as ISO strings."""
    days = sorted({str(pd.Timestamp(d).date()) for d in trading_days})
    rng = np.random.default_rng(SEED)
    picked = rng.choice(np.asarray(days), N_DAYS, replace=False)
    return sorted(str(d) for d in picked)


def et_to_utc_ns(day: str, hh: int, mm: int) -> int:
    """UTC epoch nanoseconds of ``day hh:mm:00`` America/New_York (daylight saving exact)."""
    d = date.fromisoformat(day)
    dt = datetime(d.year, d.month, d.day, hh, mm, 0, tzinfo=NY).astimezone(UTC)
    return int(dt.timestamp()) * 1_000_000_000


def rfc3339(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1e9, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_valid_quote(bid: float, ask: float) -> bool:
    """A2/A1: bid > 0 and ask > bid (crossed and locked quotes are dropped)."""
    return bool(np.isfinite(bid) and np.isfinite(ask) and bid > 0 and ask > bid)


def quote_times_ns(ts: list[str]) -> np.ndarray:
    return np.array([t.rstrip("Z") for t in ts], dtype="datetime64[ns]").astype("int64")


def update_last_valid(
    state: dict[str, tuple[float, float, int]],
    quotes_by_symbol: dict[str, list[dict[str, Any]]],
    start_ns: int,
    end_ns: int,
) -> None:
    """Fold one page of quotes into ``state``: per symbol keep the latest valid quote with
    ``start_ns <= t < end_ns`` (the end is exclusive: [T - w, T))."""
    for sym, qs in quotes_by_symbol.items():
        if not qs:
            continue
        t = quote_times_ns([q["t"] for q in qs])
        bid = np.array([q.get("bp", np.nan) for q in qs], dtype="float64")
        ask = np.array([q.get("ap", np.nan) for q in qs], dtype="float64")
        ok = (t >= start_ns) & (t < end_ns) & np.isfinite(bid) & np.isfinite(ask)
        ok &= (bid > 0) & (ask > bid)
        if not ok.any():
            continue
        i = int(np.flatnonzero(ok)[np.argmax(t[ok])])
        prev = state.get(sym)
        if prev is None or int(t[i]) >= prev[2]:
            state[sym] = (float(bid[i]), float(ask[i]), int(t[i]))


def leg_returns(
    period: str, leg: str, p: np.ndarray, ref: np.ndarray, bid: np.ndarray, ask: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """(trade-price return, executable return) of one leg (A2).

    C (enter 15:30, exit at the close ``ref``): long buys the ask, short sells the bid.
    O (enter at the open ``ref``, exit 10:00): long sells the bid, short buys the ask.
    Short returns are signed as P&L of the short (negative of the price move)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        if period == "C":
            trade = ref / p - 1.0
            exe = ref / (ask if leg == "long" else bid) - 1.0
        else:
            trade = p / ref - 1.0
            exe = (bid if leg == "long" else ask) / ref - 1.0
    if leg == "short":
        trade, exe = -trade, -exe
    return trade, exe


def half_spread(bid: np.ndarray, ask: np.ndarray) -> np.ndarray:
    """A1 half-spread (ask - bid) / (ask + bid)."""
    return (ask - bid) / (ask + bid)


def spread_position(p: np.ndarray, bid: np.ndarray, ask: np.ndarray) -> np.ndarray:
    return (p - bid) / (ask - bid)


def day_mean(values: np.ndarray, days: np.ndarray) -> tuple[float, int]:
    """Mean over days of the per-day mean of finite ``values``; (result, number of days)."""
    ok = np.isfinite(values)
    if not ok.any():
        return float("nan"), 0
    df = pd.DataFrame({"d": days[ok], "v": values[ok]})
    per = df.groupby("d")["v"].mean()
    return float(per.mean()), int(len(per))


def a2_tier(m_bp: float, s_bp: float, t_nw: float, beat: float) -> str:
    """A2 mechanical tier.  closed: m - s - 8 < 0 or t < 2 or placebo beat < 0.90;
    pass: m - 2 s - 16 >= 0 (t and placebo also ok); otherwise marginal."""
    if not all(np.isfinite(x) for x in (m_bp, s_bp, t_nw, beat)):
        raise ValueError("non-finite tier input")
    if (m_bp - s_bp - BUFFER_1X_BP) < 0 or t_nw < T_MIN or beat < BEAT_MIN:
        return "closed"
    if (m_bp - 2.0 * s_bp - BUFFER_2X_BP) >= 0:
        return "pass"
    return "marginal"


def quantiles(x: np.ndarray, qs: tuple[float, ...] = (0.05, 0.25, 0.5, 0.75, 0.95)) -> dict:
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return {f"q{int(q * 100):02d}": None for q in qs}
    return {f"q{int(q * 100):02d}": float(np.quantile(x, q)) for q in qs}


# --------------------------------------------------------------------------
# quote fetching (cached per (day, T, window, symbol batch))
# --------------------------------------------------------------------------


def _cache_path(day: str, hh: int, mm: int, window_s: int, symbols: list[str]) -> Path:
    h = hashlib.md5(",".join(symbols).encode()).hexdigest()[:10]
    return QUOTE_CACHE / f"{day}_{hh:02d}{mm:02d}_w{window_s}_{h}.parquet"


def fetch_last_quotes_batch(
    session: Any, day: str, hh: int, mm: int, symbols: list[str], window_s: int
) -> pd.DataFrame:
    """Last valid quote in [T - window_s, T) for every symbol of the batch (NaN if none)."""
    path = _cache_path(day, hh, mm, window_s, symbols)
    if path.exists():
        return pd.read_parquet(path)
    end_ns = et_to_utc_ns(day, hh, mm)
    start_ns = end_ns - window_s * 1_000_000_000
    params: dict[str, Any] = {
        "symbols": ",".join(symbols),
        "start": rfc3339(start_ns),
        "end": rfc3339(end_ns),
        "feed": "sip",
        "limit": LIMIT,
    }
    state: dict[str, tuple[float, float, int]] = {}
    token = None
    for _ in range(MAX_PAGES):
        if token:
            params["page_token"] = token
        data = session.get_url(QUOTES_URL, params)
        update_last_valid(state, data.get("quotes") or {}, start_ns, end_ns)
        token = data.get("next_page_token")
        if not token:
            break
    else:
        raise RuntimeError(f"page cap hit for {day} {hh}:{mm} {symbols[:2]}")
    rows = [
        {
            "symbol": s,
            "bid": state[s][0] if s in state else np.nan,
            "ask": state[s][1] if s in state else np.nan,
            "qt_ns": state[s][2] if s in state else -1,
            "window_s": window_s,
        }
        for s in symbols
    ]
    df = pd.DataFrame(rows)
    QUOTE_CACHE.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    return df


def quotes_for(session: Any, day: str, hh: int, mm: int, symbols: list[str]) -> pd.DataFrame:
    """A1/A2 rule: last valid quote in [T-5s, T); the still-missing ones in [T-60s, T)."""
    symbols = sorted(set(symbols))
    parts = []
    for i in range(0, len(symbols), BATCH):
        parts.append(fetch_last_quotes_batch(session, day, hh, mm, symbols[i : i + BATCH], 5))
    first = pd.concat(parts, ignore_index=True)
    miss = sorted(first.loc[~np.isfinite(first["bid"]), "symbol"])
    if miss:
        parts2 = []
        for i in range(0, len(miss), BATCH):
            parts2.append(fetch_last_quotes_batch(session, day, hh, mm, miss[i : i + BATCH], 60))
        second = pd.concat(parts2, ignore_index=True)
        first = pd.concat([first[np.isfinite(first["bid"])], second], ignore_index=True)
    return first.drop_duplicates("symbol", keep="first").reset_index(drop=True)


def fetch_raw_closes(session: Any, day: str, symbols: list[str]) -> pd.DataFrame:
    """Unadjusted SIP daily close of ``day`` per symbol.  The local price archive is split
    adjusted while historical quotes are as-printed, so quotes are rescaled by
    ``adjusted close / raw close`` of the same session (see ``rescale_quotes``)."""
    symbols = sorted(set(symbols))
    parts = []
    for i in range(0, len(symbols), BATCH):
        batch = symbols[i : i + BATCH]
        h = hashlib.md5(",".join(batch).encode()).hexdigest()[:10]
        path = QUOTE_CACHE / f"rawclose_{day}_{h}.parquet"
        if path.exists():
            parts.append(pd.read_parquet(path))
            continue
        params: dict[str, Any] = {
            "symbols": ",".join(batch),
            "timeframe": "1Day",
            "start": rfc3339(et_to_utc_ns(day, 0, 0)),
            "end": rfc3339(et_to_utc_ns(day, 23, 59)),
            "adjustment": "raw",
            "feed": "sip",
            "limit": LIMIT,
        }
        got: dict[str, float] = {}
        token = None
        for _ in range(MAX_PAGES):
            if token:
                params["page_token"] = token
            data = session.get_url(BARS_URL, params)
            for sym, bars in (data.get("bars") or {}).items():
                for b in bars:
                    got[sym] = float(b["c"])
            token = data.get("next_page_token")
            if not token:
                break
        df = pd.DataFrame({"symbol": batch, "raw_close": [got.get(x, np.nan) for x in batch]})
        QUOTE_CACHE.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(path)
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def rescale_quotes(fr: pd.DataFrame, bid_col: str, ask_col: str) -> pd.DataFrame:
    """Put as-printed quotes on the local (split adjusted) price basis: multiply by
    ``close / raw_close`` of the same session.  No raw close -> the quote is unusable (NaN)."""
    fr = fr.copy()
    with np.errstate(invalid="ignore", divide="ignore"):
        factor = fr["close"] / fr["raw_close"]
    factor = factor.where(np.isfinite(factor) & (factor > 0))
    fr["adj_factor"] = factor
    fr[bid_col] = fr[bid_col] * factor
    fr[ask_col] = fr[ask_col] * factor
    return fr


# --------------------------------------------------------------------------
# main computation
# --------------------------------------------------------------------------


def _load_inputs(days: list[str]) -> dict[str, Any]:
    from scripts import run_t20260929_35_overnight_persistence as t35

    picks = {}
    for cid in CELLS:
        p = pd.read_parquet(CACHE_DIR / f"picks_{cid}.parquet")
        p["date"] = pd.to_datetime(p["date"])
        p = p[p["date"].isin(pd.DatetimeIndex(pd.to_datetime(days)))].copy()
        p["date"] = p["date"].dt.strftime("%Y-%m-%d")
        picks[cid] = p.reset_index(drop=True)
    symbols = sorted({s for p in picks.values() for s in p["symbol"]})
    wide = t35.load_wide_float32(symbols, days)
    wide.pop("_overlap")
    daily = []
    for name in ("open", "close"):
        w = wide[name]
        w.index = pd.DatetimeIndex(w.index).strftime("%Y-%m-%d")
        daily.append(w.stack(future_stack=True).rename(name))
    daily_df = pd.concat(daily, axis=1).reset_index()
    daily_df.columns = ["date", "symbol", "open", "close"]
    daily_df = daily_df.dropna(subset=["open", "close"])
    daily_df[["open", "close"]] = daily_df[["open", "close"]].astype("float64")
    ex = (
        pl.scan_parquet(sorted(EXTRACT_DIR.glob("*.parquet")))
        .filter(pl.col("date").is_in([date.fromisoformat(d) for d in days]))
        .select(["symbol", "date", "p_0959", "p_1529", "p_1549"])
        .collect()
        .to_pandas()
    )
    ex["date"] = pd.to_datetime(ex["date"]).dt.strftime("%Y-%m-%d")
    ex = ex.drop_duplicates(["symbol", "date"], keep="last")
    return {"picks": picks, "daily": daily_df, "extract": ex}


def factor_summary(fr: pd.DataFrame) -> dict[str, Any]:
    f = fr["adj_factor"].to_numpy("float64")
    ok = np.isfinite(f)
    dev = np.abs(f[ok] - 1.0)
    return {
        "n_rows": int(len(f)),
        "n_no_factor": int((~ok).sum()),
        "n_factor_ne_1_gt_1e-4": int((dev > 1e-4).sum()),
        "n_factor_ne_1_gt_1e-3": int((dev > 1e-3).sum()),
        "n_factor_ne_1_gt_1e-2": int((dev > 1e-2).sum()),
        "n_factor_between_1e-4_and_5e-3": int(((dev > 1e-4) & (dev < 5e-3)).sum()),
    }


def basis_offset_flags(
    df: pd.DataFrame, p_col: str, thr: float = 0.004, min_n: int = 3
) -> np.ndarray:
    """True for pairs of symbols whose median ln(trade price / quote mid) over the sample
    exceeds ``thr`` in absolute value (>= ``min_n`` rows).  A stable offset means the local
    minute prices and daily prices sit on different dividend-adjustment bases; genuine noise
    (spread, 60 s staleness) averages out over the symbol's rows.  Report-only."""
    with np.errstate(invalid="ignore", divide="ignore"):
        lr = pd.Series(
            np.log(df[p_col].to_numpy("float64") / ((df["bid_entry"] + df["ask_entry"]) / 2)),
            index=df.index,
        )
    lr = lr.where(np.isfinite(lr))
    med = lr.groupby(df["symbol"]).transform("median")
    cnt = lr.groupby(df["symbol"]).transform("count")
    return ((med.abs() > thr) & (cnt >= min_n)).to_numpy()


def _pos_block(pos: np.ndarray) -> dict[str, Any]:
    ok = pos[np.isfinite(pos)]
    return {
        "mean": float(ok.mean()) if len(ok) else None,
        "share_outside_0_1": float(((ok < 0) | (ok > 1)).mean()) if len(ok) else None,
        **quantiles(pos),
    }


def compute_cell(period: str, frame: pd.DataFrame, m_stats: dict[str, Any]) -> dict[str, Any]:
    """Frame: one row per (date, leg, symbol) pick with daily open/close, trade slot prices
    and the entry-time quote (``bid_entry``/``ask_entry``/``w_entry``); C also has the 15:50 quote."""
    from scripts import run_t20260930_13_intraday_periodicity as t13

    p_col = "p_1529" if period == "C" else "p_0959"
    ref_col = "close" if period == "C" else "open"
    out: dict[str, Any] = {"period": period}
    n_picks = frame.groupby("leg").size().to_dict()
    res: dict[str, dict[str, Any]] = {}
    flag_all = basis_offset_flags(frame, p_col)
    for leg in ("long", "short"):
        f = frame[frame["leg"] == leg]
        fl = flag_all[(frame["leg"] == leg).to_numpy()]
        p = f[p_col].to_numpy("float64")
        ref = f[ref_col].to_numpy("float64")
        bid = f["bid_entry"].to_numpy("float64")
        ask = f["ask_entry"].to_numpy("float64")
        # trade-price return through the T-13 function (identical arithmetic to results.json)
        slots = {k: f[p_col].to_numpy("float64") for k in t13.SLOTS}
        rets = t13.period_returns(
            f["open"].to_numpy("float64"), f["close"].to_numpy("float64"), slots
        )
        r_trade = rets["r_C"] if period == "C" else rets["r_O"]
        r_trade = -r_trade if leg == "short" else r_trade
        trade, exe = leg_returns(period, leg, p, ref, bid, ask)
        ok_price = np.isfinite(p) & np.isfinite(ref)
        ok_quote = np.isfinite(bid) & np.isfinite(ask)
        both = ok_price & ok_quote
        assert np.allclose(trade[ok_price], r_trade[ok_price], equal_nan=True)
        s = np.where(both, trade - exe, np.nan)
        days = f["date"].to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            h = np.where(ok_quote, half_spread(bid, ask), np.nan)
            pos = np.where(both, spread_position(p, bid, ask), np.nan)
        s_bp, nd = day_mean(s * BP, days)
        h_bp, _ = day_mean(h * BP, days)
        tr_bp, _ = day_mean(np.where(both, trade, np.nan) * BP, days)
        ex_bp, _ = day_mean(np.where(both, exe, np.nan) * BP, days)
        res[leg] = {
            "n_picks": int(len(f)),
            "n_missing_price": int((~ok_price).sum()),
            "n_missing_quote": int((~ok_quote).sum()),
            "n_quote_5s": int((f["w_entry"] == 5).sum()),
            "n_quote_60s": int((f["w_entry"] == 60).sum()),
            "n_pairs": int(both.sum()),
            "n_days": nd,
            "s_bp": s_bp,
            "s_median_bp": float(np.nanmedian(s) * BP) if both.any() else None,
            "s_p95_bp": float(np.nanquantile(s, 0.95) * BP) if both.any() else None,
            "s_max_bp": float(np.nanmax(s) * BP) if both.any() else None,
            "s_winsor_1_99_bp": (
                float(
                    np.nanmean(
                        np.clip(
                            s[both], np.nanquantile(s[both], 0.01), np.nanquantile(s[both], 0.99)
                        )
                    )
                    * BP
                )
                if both.any()
                else None
            ),
            "h_bp": h_bp,
            "trade_return_bp": tr_bp,
            "executable_return_bp": ex_bp,
            "trade_price_spread_position": _pos_block(pos),
            "n_pairs_basis_flagged": int((both & fl).sum()),
            "s_bp_excl_basis_flagged": day_mean(np.where(fl, np.nan, s) * BP, days)[0],
            "trade_return_bp_excl_basis_flagged": day_mean(
                np.where(both & ~fl, trade, np.nan) * BP, days
            )[0],
            "executable_return_bp_excl_basis_flagged": day_mean(
                np.where(both & ~fl, exe, np.nan) * BP, days
            )[0],
            "trade_price_spread_position_excl_basis_flagged": _pos_block(np.where(fl, np.nan, pos)),
            "share_spread_gt_50bp": float((h[np.isfinite(h)] * 2 * BP > 50).mean())
            if ok_quote.any()
            else None,
        }
    n_all = int(sum(n_picks.values()))
    n_missing = res["long"]["n_missing_quote"] + res["short"]["n_missing_quote"]
    n_missing_price = res["long"]["n_missing_price"] + res["short"]["n_missing_price"]
    s_long, s_short = res["long"]["s_bp"], res["short"]["s_bp"]
    s_bp = s_long + s_short
    m, t_nw, beat = m_stats["mean_bp"], m_stats["t_nw5"], m_stats["placebo_beat"]
    out.update(
        {
            "n_picks_long": res["long"]["n_picks"],
            "n_picks_short": res["short"]["n_picks"],
            "n_pairs_long": res["long"]["n_pairs"],
            "n_pairs_short": res["short"]["n_pairs"],
            "missing_share": n_missing / max(n_all, 1),
            "missing_price_share": n_missing_price / max(n_all, 1),
            "s_long_bp": s_long,
            "s_short_bp": s_short,
            "s_bp": s_bp,
            "h_long_bp": res["long"]["h_bp"],
            "h_short_bp": res["short"]["h_bp"],
            "m_bp": m,
            "t_nw5": t_nw,
            "placebo_beat": beat,
            "net_1x_bp": m - s_bp - BUFFER_1X_BP,
            "net_2x_bp": m - 2.0 * s_bp - BUFFER_2X_BP,
            "tier": a2_tier(m, s_bp, t_nw, beat),
            "sample_gross_trade_bp": res["long"]["trade_return_bp"]
            + res["short"]["trade_return_bp"],
            "sample_gross_executable_bp": res["long"]["executable_return_bp"]
            + res["short"]["executable_return_bp"],
            "legs": res,
        }
    )
    s_ex = res["long"]["s_bp_excl_basis_flagged"] + res["short"]["s_bp_excl_basis_flagged"]
    sym_flag = frame.loc[flag_all, "symbol"].nunique()
    out["basis_mismatch_report_only"] = {
        "note": "symbols whose median ln(trade price / adjusted quote mid) exceeds 0.4% "
        "(>=3 rows): local minute vs daily dividend-adjustment basis differs; T-13's r_C/r_O "
        "carries that offset for these names.  The A2 tier above uses ALL pairs.",
        "n_flagged_symbols": int(sym_flag),
        "n_symbols": int(frame["symbol"].nunique()),
        "share_picks_flagged": float(flag_all.mean()),
        "s_excl_bp": s_ex,
        "net_1x_excl_bp": m - s_ex - BUFFER_1X_BP,
        "net_2x_excl_bp": m - 2.0 * s_ex - BUFFER_2X_BP,
        "tier_excl_using_full_window_m": a2_tier(m, s_ex, t_nw, beat),
        "sample_gross_trade_excl_bp": res["long"]["trade_return_bp_excl_basis_flagged"]
        + res["short"]["trade_return_bp_excl_basis_flagged"],
        "sample_gross_executable_excl_bp": res["long"]["executable_return_bp_excl_basis_flagged"]
        + res["short"]["executable_return_bp_excl_basis_flagged"],
    }
    return out


def main() -> int:
    from scripts.run_t20260930_11_gap_fade_auction import DataSession

    t0 = time.time()
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))["decision_cells"]
    pc = pd.read_parquet(CACHE_DIR / "picks_C_L20_P1500.parquet", columns=["date"])
    days = sample_days(pc["date"].unique())
    del pc
    print(f"sample days ({len(days)}): {days[0]} .. {days[-1]}", flush=True)
    inp = _load_inputs(days)
    session = DataSession()
    quotes: dict[str, dict[tuple[str, str], pd.DataFrame]] = {"C": {}, "O": {}}
    raw_closes: list[pd.DataFrame] = []
    for i, day in enumerate(days):
        pc_d = inp["picks"]["C_L20_P1500"]
        po_d = inp["picks"]["O_L20_P1500"]
        sym_c = pc_d.loc[pc_d["date"] == day, "symbol"].tolist()
        sym_c_long = pc_d.loc[(pc_d["date"] == day) & (pc_d["leg"] == "long"), "symbol"].tolist()
        sym_o = po_d.loc[po_d["date"] == day, "symbol"].tolist()
        quotes["C"][(day, "entry")] = quotes_for(session, day, *T_ENTRY["C"], sym_c)
        quotes["C"][(day, "diag")] = quotes_for(session, day, *T_DIAG, sym_c_long)
        quotes["O"][(day, "entry")] = quotes_for(session, day, *T_ENTRY["O"], sym_o)
        rc = fetch_raw_closes(session, day, sorted(set(sym_c) | set(sym_o)))
        raw_closes.append(rc.assign(date=day))
        print(
            f"[{time.time() - t0:6.0f}s] day {i + 1}/{len(days)} {day}: calls {session.calls}, 429s {session.n429}",
            flush=True,
        )

    rawc = pd.concat(raw_closes, ignore_index=True)
    inp["daily"] = inp["daily"].merge(rawc, on=["date", "symbol"], how="left")
    cells: dict[str, Any] = {}
    for cid in CELLS:
        period = cid[0]
        frame = inp["picks"][cid]
        q = {k: v for k, v in quotes[period].items() if k[1] == "entry"}
        qdf = pd.concat([v.assign(date=k[0]) for k, v in q.items()], ignore_index=True)
        qdf = qdf.rename(columns={"bid": "bid_entry", "ask": "ask_entry", "window_s": "w_entry"})
        fr = frame.merge(inp["daily"], on=["date", "symbol"], how="left").merge(
            inp["extract"], on=["date", "symbol"], how="left"
        )
        fr = fr.merge(
            qdf[["date", "symbol", "bid_entry", "ask_entry", "w_entry"]],
            on=["date", "symbol"],
            how="left",
        )
        fr = rescale_quotes(fr, "bid_entry", "ask_entry")
        cell = compute_cell(period, fr, results[cid])
        cell["adjustment_factor"] = factor_summary(fr)
        if period == "C":
            qd = pd.concat(
                [v.assign(date=k[0]) for k, v in quotes["C"].items() if k[1] == "diag"],
                ignore_index=True,
            ).rename(columns={"bid": "bid_d", "ask": "ask_d", "window_s": "w_d"})
            lg = fr[fr["leg"] == "long"].merge(
                qd[["date", "symbol", "bid_d", "ask_d", "w_d"]], on=["date", "symbol"], how="left"
            )
            lg = rescale_quotes(lg, "bid_d", "ask_d")
            okd = np.isfinite(lg["bid_d"]) & np.isfinite(lg["ask_d"]) & np.isfinite(lg["close"])
            mid = (lg["bid_d"] + lg["ask_d"]) / 2.0
            prem = np.where(okd, lg["close"] / mid - 1.0, np.nan) * BP
            pos = np.where(
                okd & np.isfinite(lg["p_1549"]),
                spread_position(
                    lg["p_1549"].to_numpy("float64"),
                    lg["bid_d"].to_numpy("float64"),
                    lg["ask_d"].to_numpy("float64"),
                ),
                np.nan,
            )
            pm, nd = day_mean(prem, lg["date"].to_numpy())
            posm, _ = day_mean(pos, lg["date"].to_numpy())
            posf = pos[np.isfinite(pos)]
            cell["diagnostics"] = {
                "n_picks_long": int(len(lg)),
                "n_quotes_1550": int(okd.sum()),
                "missing_share_1550": float(1.0 - okd.mean()) if len(lg) else None,
                "auction_premium_vs_mid1550_long_bp": {
                    "mean_of_day_means": pm,
                    "n_days": nd,
                    "pooled_mean": float(np.nanmean(prem)) if okd.any() else None,
                    **quantiles(prem),
                },
                "p1549_spread_position": {
                    "mean": float(posf.mean()) if len(posf) else None,
                    "mean_of_day_means": posm,
                    "share_outside_0_1": float(((posf < 0) | (posf > 1)).mean())
                    if len(posf)
                    else None,
                    **quantiles(pos),
                },
            }
        cells[cid] = cell

    out = {
        "task": "T-20260930-15",
        "iter_id": ITERATION_ID,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "design": "A1 sampling + A2 formulas (amendment-2026-09-30-a2-executable-quotes.md)",
        "sample_days": days,
        "n_sample_days": len(days),
        "request_calls": session.calls,
        "request_429": session.n429,
        "seconds": time.time() - t0,
        "cells": cells,
    }
    OUT_JSON.write_text(json.dumps(_clean(out), indent=2, ensure_ascii=False), encoding="utf-8")
    write_md(out)
    print(f"wrote {OUT_JSON} and {OUT_MD}", flush=True)
    return 0


def _clean(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return v if np.isfinite(v) else None
    if isinstance(obj, np.integer):
        return int(obj)
    return obj


def _f(x: Any, nd: int = 2) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{nd}f}"


def write_md(out: dict[str, Any]) -> None:
    L = [
        f"# T-20260930-15 measured-quote check ({out['generated_at']})",
        "",
        "Design: A1 sampling + A2 formulas, `amendment-2026-09-30-a2-executable-quotes.md`. "
        "Numbers: `quote-check.json`. Tiers are the mechanical A2 output; the verdict is the lead review's.",
        f"Sample: {out['n_sample_days']} seeded days ({out['sample_days'][0]} .. {out['sample_days'][-1]}), "
        f"{out['request_calls']} requests in the final invocation (quote and raw-close responses are cached in cache/quotes; the first invocation made 336 quote requests, the second 150 raw-close requests), {out['request_429']} HTTP 429.",
        "",
        "| cell | m bp | t_nw5 | placebo | s_long | s_short | s | h_long | h_short | net 1x | net 2x | missing quote | tier |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cid, c in out["cells"].items():
        L.append(
            f"| {cid} | {_f(c['m_bp'])} | {_f(c['t_nw5'])} | {_f(c['placebo_beat'])} | {_f(c['s_long_bp'])} | "
            f"{_f(c['s_short_bp'])} | {_f(c['s_bp'])} | {_f(c['h_long_bp'])} | {_f(c['h_short_bp'])} | "
            f"{_f(c['net_1x_bp'])} | {_f(c['net_2x_bp'])} | {_f(100 * c['missing_share'], 2)}% | {c['tier']} |"
        )
    L += [
        "",
        "net 1x = m - s - 8, net 2x = m - 2s - 16 (bp per day). h = A1 half-spread (ask-bid)/(ask+bid), bp.",
        "",
    ]
    for cid, c in out["cells"].items():
        L.append(f"## {cid}")
        L.append(
            f"- sample gross (trade-price) {_f(c['sample_gross_trade_bp'])} bp, executable {_f(c['sample_gross_executable_bp'])} bp "
            f"over the {out['n_sample_days']} days (report only; the decision `m` is the full main window)."
        )
        for leg, r in c["legs"].items():
            pos = r["trade_price_spread_position"]
            L.append(
                f"- {leg}: pairs {r['n_pairs']}/{r['n_picks']} (missing price {r['n_missing_price']}, missing quote {r['n_missing_quote']}, "
                f"60s fallback {r['n_quote_60s']}); s mean {_f(r['s_bp'])} median {_f(r['s_median_bp'])} p95 {_f(r['s_p95_bp'])} "
                f"max {_f(r['s_max_bp'])} winsor1/99 {_f(r['s_winsor_1_99_bp'])} bp; trade-price position mean {_f(pos['mean'], 3)} "
                f"(q05 {_f(pos['q05'], 2)}, q50 {_f(pos['q50'], 2)}, q95 {_f(pos['q95'], 2)}, outside [0,1] {_f(pos['share_outside_0_1'], 3)})."
            )
        b = c["basis_mismatch_report_only"]
        L.append(
            f"- basis mismatch (report only): {b['n_flagged_symbols']}/{b['n_symbols']} symbols, {_f(100 * b['share_picks_flagged'], 1)}% of picks; "
            f"excluding them s {_f(b['s_excl_bp'])} bp, net 1x {_f(b['net_1x_excl_bp'])}, net 2x {_f(b['net_2x_excl_bp'])}, tier {b['tier_excl_using_full_window_m']} (with the full-window m); "
            f"sample gross trade {_f(b['sample_gross_trade_excl_bp'])} / executable {_f(b['sample_gross_executable_excl_bp'])} bp."
        )
        af = c["adjustment_factor"]
        L.append(
            f"- adjusted/raw close factor: {af['n_factor_ne_1_gt_1e-3']}/{af['n_rows']} rows differ from 1 by >0.1%, {af['n_factor_ne_1_gt_1e-2']} by >1%, no factor {af['n_no_factor']}."
        )
        d = c.get("diagnostics")
        if d:
            a, p = d["auction_premium_vs_mid1550_long_bp"], d["p1549_spread_position"]
            L.append(
                f"- close / mid_1550 - 1 (long): day-mean {_f(a['mean_of_day_means'])} bp, pooled mean {_f(a['pooled_mean'])}, "
                f"q05 {_f(a['q05'])}, q50 {_f(a['q50'])}, q95 {_f(a['q95'])}; quotes {d['n_quotes_1550']}/{d['n_picks_long']}."
            )
            L.append(
                f"- p_1549 position in the 15:50 spread (long): mean {_f(p['mean'], 3)}, q05 {_f(p['q05'], 2)}, q25 {_f(p['q25'], 2)}, "
                f"q50 {_f(p['q50'], 2)}, q75 {_f(p['q75'], 2)}, q95 {_f(p['q95'], 2)}, outside [0,1] {_f(p['share_outside_0_1'], 3)}."
            )
        L.append("")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
