"""T-20261002-30: account-level numbers for the 2026-11-01 paper renewal decision.

Aligns six daily return series (S1, S2, S3, C2, v1.2 F1, v1.2 F2), then reports correlation,
risk concentration, account Sharpe (with same-volatility control), joint drawdowns and forward
paper-vs-backtest tracking. Numbers only; no recommendation.

    scripts/run_capped.sh --mem 1.5G -- uv run python scripts/account_review_2026_10.py

Writes data/research/account_review_2026_10/returns.parquet (not committed) and
reports/research/program/account-review-2026-10/{account-review.json,report.md}.

Conventions (fixed before any result was read):
- S1-S3 are recomputed with `run_h20260927_01_sleeve_combination.sleeve_returns` on the current
  SIP panel (restated 2026-10-02) through 2026-10-02; their rows before the common start are NaN.
- C2 is the stored `C2__o00__net{10,20}` through 2026-09-17 and a recomputation of the same
  lane rules on the current panel after that (the stored column no longer reproduces from the
  restated SIP panel: max abs diff ~0.010; recorded in `series.C2.stored_vs_recomputed`).
- v1.2 F1/F2 = `net_pnl / 1e6` moved to the realization date with `realization_dated()` (data
  pitfall #60). The v1.2 files have one cost level, so the 20 bp tables reuse them unchanged.
- Sharpe = mean/std (ddof=1) of daily return minus BIL, times sqrt(252).
- Combinations rebalance on the first session of each month with a 5 bp cost on one-way
  turnover (the T-43 allocation convention); weights drift within the month.
- A series covers a window when it starts no later than 7 days after the window start and ends
  no earlier than 7 days before the window end; otherwise the cell is null (no extrapolation).
  `stress_common` (2018-02-01..2023-08-31) is added because the 2016-05 stress window is not
  covered by any sleeve except C2.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_20_recent_opt as batch  # noqa: E402
import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260927_01_sleeve_combination as comb  # noqa: E402
import run_program_dd30_allocation as dd  # noqa: E402
import screen_batch  # noqa: E402
import screen_lane as lane  # noqa: E402

OUT_DIR = ROOT / "reports/research/program/account-review-2026-10"
RETURNS_PATH = ROOT / "data/research/account_review_2026_10/returns.parquet"
SCREEN_RETURNS = ROOT / "reports/research/screens/h20260928_20_recent_opt/returns.parquet"
PANEL_END = "2026-10-02"
STORED_C2_END = pd.Timestamp("2026-09-17")
RISK_ASOF = pd.Timestamp("2026-09-30")
SLEEVES = ["S1", "S2", "S3", "C2"]
ALL = ["S1", "S2", "S3", "C2", "F1", "F2"]
SLEEVE_CAPITAL = 15_000.0
LOOKBACK = 63
REBAL_COST = dd.REBAL_COST
DEBIT_DAILY = dd.DEBIT_RATE / 252.0
WINDOWS = {
    "stress": ("2016-05-02", "2023-08-31"),
    "anchor": ("2024-01-08", "2026-09-17"),
    "ytd2026": ("2026-01-02", "2026-09-17"),
    "stress_common": ("2018-02-01", "2023-08-31"),
}
COVER_SLACK = pd.Timedelta(days=7)
REH = ROOT / "reports/paper/rehearsal"
PAPER = {
    "S1": "us_etf_sector_rotation_252_top2_weekly",
    "S2": "us_etf_growth_rotation_blend_top2_monthly",
    "S3": "us_etf_levered_rotation_63_top2_monthly",
    "C2": "us_etf_eom_sector_blend_monthly",
}
T43_WEIGHTS = {"S3": 0.60, "C2": 0.335, "F2": 0.12, "F1": 0.025}
T43_BORROW = 0.08
BACKTEST_PICKS: dict[str, Any] = {}


# ------------------------------------------------------------------ series


def load_series() -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict[str, Any]]:
    """Return ({'10': frame, '20': frame}, panel close, per-series metadata)."""
    base.HOLD_END = PANEL_END
    cands = screen_batch.candidates_from_module(batch)
    c2_cand = next(c for c in cands if c.id == "C2")
    close, _open, leg_open, leg_close, _rf = lane.load_batch_panel(
        cands, getattr(batch, "extend_panel", None)
    )
    start = comb.common_start(close)
    c2_start = lane.first_valid_signal_date(close, c2_cand)
    weights, _ = lane.weights_frame(close, c2_cand, 0)
    stored = pd.read_parquet(SCREEN_RETURNS)
    frames: dict[str, pd.DataFrame] = {}
    meta: dict[str, Any] = {}
    for tag, bps in (("10", 10.0), ("20", 20.0)):
        sl = comb.sleeve_returns(close, leg_open, leg_close, bps)
        re_c2, _ = lane.salvage.simulate(weights, leg_open, leg_close, np.ones(len(close)), bps)
        col = f"C2__o00__net{tag}"
        c2 = re_c2.copy()
        common = stored.index.intersection(c2.index)
        c2.loc[common] = stored[col].loc[common]
        diff = (re_c2.loc[common] - stored[col].loc[common]).abs()
        meta.setdefault("C2", {})[f"stored_vs_recomputed_net{tag}"] = {
            "sessions": int(len(common)),
            "max_abs_diff": float(diff.max()),
            "mean_abs_diff": float(diff.mean()),
            "sessions_over_1e-6": int((diff > 1e-6).sum()),
            "note": "SIP daily restated 2026-10-02 (data/sip/daily/_restatements.jsonl); "
            "stored column dated 2026-09-28",
        }
        data = {k.upper(): v for k, v in sl.items()}
        data["C2"] = c2
        for key in ("S1", "S2", "S3"):
            data[key] = data[key].where(data[key].index >= start)
        data["C2"] = data["C2"].where(data["C2"].index >= c2_start)
        for f in ("F1", "F2"):
            d = pd.read_parquet(ROOT / f"data/research/book_v12/A1_M0_U3000_{f}.parquet")
            r = dd.realization_dated(d["net_pnl"] / 1e6)
            r.iloc[: dd.BOOK_REALIZATION_LAG] = np.nan
            data[f] = r
        frame = pd.DataFrame({k: pd.Series(v) for k, v in data.items()})
        frame.index = pd.to_datetime(frame.index)
        frames[tag] = frame[ALL].sort_index()
    picks: dict[str, dict[str, dict[str, float]]] = {}
    for key in ("S1", "S2", "S3"):
        w, _ = comb.salvage.sleeve_weights(close, key.lower())
        w = w.loc["2026-08-28":]
        changed = w[(w.diff().abs().sum(axis=1) > 0) | (w.index == w.index[0])]
        picks[key] = {
            str(d.date()): {c: round(float(v), 4) for c, v in row.items() if v > 0}
            for d, row in changed.iterrows()
        }
    meta["backtest_pre_overlay_weights_since_2026_08_28"] = picks
    for k in ALL:
        s = frames["10"][k].dropna()
        meta.setdefault(k, {}).update(
            {"start": str(s.index[0].date()), "end": str(s.index[-1].date()), "rows": len(s)}
        )
    meta["S1"]["source"] = meta["S2"]["source"] = meta["S3"]["source"] = (
        "run_h20260927_01_sleeve_combination.sleeve_returns() on current SIP panel; "
        f"rows before common start {start.date()} set to NaN"
    )
    meta["C2"]["source"] = (
        f"stored {SCREEN_RETURNS.relative_to(ROOT)} C2__o00__net10/net20 through "
        f"{STORED_C2_END.date()}; lane recomputation after; first valid signal "
        f"{pd.Timestamp(c2_start).date()}"
    )
    for f in ("F1", "F2"):
        meta[f]["source"] = (
            f"data/research/book_v12/A1_M0_U3000_{f}.parquet net_pnl/1e6, realization_dated() "
            f"lag {dd.BOOK_REALIZATION_LAG}; first {dd.BOOK_REALIZATION_LAG} rows NaN; one cost "
            "level only (also used in the 20 bp tables)"
        )
    return frames, close, meta


def covers(series: pd.Series, window: tuple[str, str]) -> bool:
    s = series.dropna()
    if s.empty:
        return False
    return (s.index[0] <= pd.Timestamp(window[0]) + COVER_SLACK) and (
        s.index[-1] >= pd.Timestamp(window[1]) - COVER_SLACK
    )


def in_window(frame: pd.DataFrame | pd.Series, window: tuple[str, str]):
    return frame.loc[window[0] : window[1]]


# ------------------------------------------------------------------ correlation


def weekly(frame: pd.DataFrame) -> pd.DataFrame:
    return (1.0 + frame).resample("W-FRI").prod(min_count=1) - 1.0


def corr_block(frame: pd.DataFrame, window: tuple[str, str]) -> dict[str, Any]:
    cols = list(frame.columns)
    ok = {c: covers(frame[c], window) for c in cols}
    win = in_window(frame, window)
    out: dict[str, Any] = {"covered": ok}
    for label, data in (("daily", win), ("weekly", weekly(win))):
        mat: dict[str, dict[str, float | None]] = {}
        for a in cols:
            mat[a] = {}
            for b in cols:
                if a == b and ok[a]:
                    mat[a][b] = 1.0
                elif ok[a] and ok[b]:
                    both = data[[a, b]].dropna()
                    mat[a][b] = float(both[a].corr(both[b])) if len(both) > 2 else None
                else:
                    mat[a][b] = None
        out[label] = mat
        out[f"{label}_n"] = int(len(data.dropna(how="all")))
    roll = frame.rolling(LOOKBACK, min_periods=LOOKBACK)
    med: dict[str, dict[str, float | None]] = {}
    p90: dict[str, dict[str, float | None]] = {}
    for a in cols:
        med[a], p90[a] = {}, {}
        for b in cols:
            if a == b or not (ok[a] and ok[b]):
                med[a][b] = p90[a][b] = None
                continue
            rc = roll[a].corr(frame[b]).loc[window[0] : window[1]].dropna()
            med[a][b] = float(rc.median()) if len(rc) else None
            p90[a][b] = float(rc.quantile(0.9)) if len(rc) else None
    out["rolling63_median"] = med
    out["rolling63_p90"] = p90
    return out


# ------------------------------------------------------------------ combinations


def month_starts(index: pd.DatetimeIndex) -> np.ndarray:
    pos = pd.Series(np.arange(len(index)), index=index).groupby(index.to_period("M")).cumcount()
    return (pos.to_numpy() == 0) & (np.arange(len(index)) > 0)


def combine(
    frame: pd.DataFrame,
    cols: list[str],
    mode: str,
    fixed: dict[str, float] | None = None,
    borrow: float = 0.0,
) -> pd.Series:
    """Monthly-rebalanced combination of `cols` ('equal' | 'invvol' | 'fixed') with drift.

    The series starts on the first session where weights can be set and every column is valid.
    """
    data = frame[cols].dropna()
    idx = data.index
    arr = data.to_numpy()
    n = len(idx)
    reb = month_starts(idx)
    first = LOOKBACK if mode == "invvol" else 0
    if n <= first:
        return pd.Series(dtype=float)
    if mode == "invvol":
        # first month-start at or after `first`
        cand = np.flatnonzero(reb & (np.arange(n) >= first))
        if len(cand) == 0:
            return pd.Series(dtype=float)
        first = int(cand[0])

    def target(t: int) -> np.ndarray:
        if mode == "equal":
            return np.full(len(cols), 1.0 / len(cols))
        if mode == "fixed":
            assert fixed is not None
            return np.array([fixed[c] for c in cols])
        vol = arr[t - LOOKBACK : t].std(axis=0, ddof=1)
        inv = 1.0 / vol
        return inv / inv.sum()

    w = target(first)
    h = np.append(w, -borrow) if borrow else w.copy()
    out = np.zeros(n - first)
    for i, t in enumerate(range(first, n)):
        cost = 0.0
        if reb[t] and t > first:
            w = target(t)
            wt = np.append(w, -borrow) if borrow else w
            cost = REBAL_COST * np.abs(wt - h).sum()
            h = wt.copy()
        r = np.append(arr[t], DEBIT_DAILY) if borrow else arr[t]
        grown = h * (1.0 + r)
        port = grown.sum()
        out[i] = port * (1.0 - cost) - 1.0
        h = grown / port
    return pd.Series(out, index=idx[first:])


def stats(ret: pd.Series, rf: pd.Series) -> dict[str, Any]:
    r = ret.dropna()
    ex = r - rf.reindex(r.index).fillna(0.0)
    nav = (1.0 + r).cumprod()
    yrs = len(r) / 252.0
    return {
        "start": str(r.index[0].date()),
        "end": str(r.index[-1].date()),
        "days": int(len(r)),
        "sharpe": float(ex.mean() / ex.std(ddof=1) * np.sqrt(252)) if ex.std() > 0 else None,
        "vol": float(r.std(ddof=1) * np.sqrt(252)),
        "cagr": float(nav.iloc[-1] ** (1 / yrs) - 1) if yrs > 0 else None,
        "max_dd": float((nav / nav.cummax() - 1).min()),
    }


def window_sharpe(
    ret: pd.Series, s3: pd.Series, shy: pd.Series, rf: pd.Series, window: tuple[str, str]
) -> dict[str, Any]:
    if ret.empty or not covers(ret, window) or not covers(s3, window):
        return {"combo": None, "control": None, "delta": None, "k": None}
    r = in_window(ret, window).dropna()
    s = s3.reindex(r.index)
    k = float(r.std(ddof=1) / s.std(ddof=1))
    control = k * s + (1.0 - k) * shy.reindex(r.index).fillna(0.0)
    a, c = stats(r, rf), stats(control, rf)
    return {
        "combo": a,
        "control": {**c, "note": "k*S3+(1-k)*SHY"},
        "k": k,
        "k_above_1_levered_at_SHY": bool(k > 1.0),
        "delta": None if a["sharpe"] is None or c["sharpe"] is None else a["sharpe"] - c["sharpe"],
    }


def build_combos(frame: pd.DataFrame) -> dict[str, pd.Series]:
    combos = {
        "EQ4": combine(frame, SLEEVES, "equal"),
        "IV4": combine(frame, SLEEVES, "invvol"),
        "IV4_F1": combine(frame, SLEEVES + ["F1"], "invvol"),
        "IV4_F2": combine(frame, SLEEVES + ["F2"], "invvol"),
        "T43": combine(frame, list(T43_WEIGHTS), "fixed", fixed=T43_WEIGHTS, borrow=T43_BORROW),
    }
    for drop in SLEEVES:
        combos[f"DROP_{drop}"] = combine(frame, [c for c in SLEEVES if c != drop], "equal")
    return combos


# ------------------------------------------------------------------ concentration


def risk_contribution(
    frame: pd.DataFrame, cols: list[str], weights: np.ndarray, asof: pd.Timestamp
):
    data = frame[cols].loc[:asof].dropna().iloc[-LOOKBACK:]
    cov = data.cov().to_numpy()
    var = float(weights @ cov @ weights)
    rc = weights * (cov @ weights) / var
    return {
        "window": [str(data.index[0].date()), str(data.index[-1].date())],
        "days": int(len(data)),
        "weights": dict(zip(cols, map(float, weights), strict=True)),
        "ann_vol_by_sleeve": dict(zip(cols, map(float, np.sqrt(np.diag(cov) * 252)), strict=True)),
        "portfolio_ann_vol": float(np.sqrt(var * 252)),
        "risk_contribution_share": dict(zip(cols, map(float, rc), strict=True)),
        "effective_bets": float(1.0 / np.sum(rc**2)),
    }


def sip_closes(symbols: list[str], day: str) -> dict[str, float]:
    import duckdb

    con = duckdb.connect()
    in_list = ",".join(f"'{s}'" for s in symbols)
    rows = con.execute(
        f"SELECT symbol, close FROM read_parquet('data/sip/daily/2026/*.parquet') "
        f"WHERE symbol IN ({in_list}) AND timestamp::DATE = DATE '{day}'"
    ).fetchall()
    con.close()
    return {s: float(c) for s, c in rows}


def overlap(last_day: str) -> dict[str, Any]:
    holdings: dict[str, dict[str, float]] = {}
    equity = None
    for key, name in PAPER.items():
        text = (REH / f"{name}-latest.md").read_text(encoding="utf-8")
        m = re.search(r"仅本策略账本持仓 (\{[^}]*\})", text)
        holdings[key] = {k: float(v) for k, v in ast.literal_eval(m.group(1)).items()} if m else {}
        eq = re.search(r"账户权益：([\d,\.]+)", text)
        equity = float(eq.group(1).replace(",", "")) if eq else equity
    symbols = sorted({s for h in holdings.values() for s in h})
    px = sip_closes(symbols, last_day)
    by_symbol: dict[str, dict[str, float]] = {}
    for key, h in holdings.items():
        for sym, qty in h.items():
            by_symbol.setdefault(sym, {})[key] = qty * px[sym]
    rows = []
    for sym, parts in by_symbol.items():
        total = sum(parts.values())
        rows.append(
            {
                "symbol": sym,
                "total_usd": total,
                "by_sleeve_usd": parts,
                "pct_of_account_equity": total / equity if equity else None,
                "n_sleeves": len(parts),
            }
        )
    rows.sort(key=lambda r: -r["total_usd"])
    return {
        "as_of_close": last_day,
        "account_equity_usd": equity,
        "holdings_qty_by_sleeve": holdings,
        "sleeve_market_value_usd": {
            k: sum(q * px[s] for s, q in h.items()) for k, h in holdings.items()
        },
        "by_symbol": rows,
        "total_exposure_usd": float(sum(r["total_usd"] for r in rows)),
    }


# ------------------------------------------------------------------ worst windows


def worst_windows(frame: pd.DataFrame, combo: pd.Series, cols: list[str], span: int, top: int = 5):
    data = frame[cols].reindex(combo.index)
    comp = (1.0 + combo).rolling(span).apply(np.prod, raw=True) - 1.0
    comp = comp.dropna().sort_values()
    picked: list[pd.Timestamp] = []
    pos = {d: i for i, d in enumerate(combo.index)}
    rows = []
    for end, val in comp.items():
        if any(abs(pos[end] - pos[p]) < span for p in picked):
            continue
        picked.append(end)
        i = pos[end]
        sub = data.iloc[i - span + 1 : i + 1]
        rows.append(
            {
                "start": str(sub.index[0].date()),
                "end": str(end.date()),
                "combo_return": float(val),
                "sleeve_returns": {c: float((1.0 + sub[c]).prod() - 1.0) for c in cols},
            }
        )
        if len(rows) == top:
            break
    return rows


# ------------------------------------------------------------------ forward tracking


def forward(frame: pd.DataFrame, close: pd.DataFrame, last_day: pd.Timestamp) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, name in PAPER.items():
        fills = [json.loads(x) for x in (REH / f"{name}-fills.jsonl").read_text().splitlines() if x]
        summary = json.loads((REH / f"{name}-fills-summary.json").read_text())
        filled = [f for f in fills if f.get("filled_qty")]
        first = pd.Timestamp(min(f["session"] for f in fills))
        days = close.index[(close.index >= first) & (close.index <= last_day)]
        qty: dict[str, float] = {}
        pnl = []
        prev = None
        for d in days:
            day_pnl = 0.0
            for sym, q in qty.items():
                if prev is not None:
                    day_pnl += q * (close.at[d, sym] - close.at[prev, sym])
            for f in filled:
                if pd.Timestamp(f["session"]) == d:
                    sgn = 1.0 if f["side"] == "buy" else -1.0
                    day_pnl += (
                        sgn * f["filled_qty"] * (close.at[d, f["symbol"]] - f["filled_avg_price"])
                    )
                    qty[f["symbol"]] = qty.get(f["symbol"], 0.0) + sgn * f["filled_qty"]
            pnl.append(day_pnl)
            prev = d
        pnl_s = pd.Series(pnl, index=days)
        equity_prev = SLEEVE_CAPITAL + pnl_s.cumsum().shift(1).fillna(0.0)
        paper = pnl_s / equity_prev
        bt = frame[key].reindex(days)
        row: dict[str, Any] = {
            "paper_source": f"reports/paper/rehearsal/{name}-fills.jsonl (ledger P&L on SIP "
            "closes, "
            f"base ${SLEEVE_CAPITAL:,.0f}, no cash yield, no fees)",
            "first_fill_session": str(first.date()),
            "last_day": str(days[-1].date()),
            "trading_days": int(len(days)),
            "sample_too_short": bool(len(days) < 10),
        }
        if bt.isna().any():
            row["backtest"] = "unavailable"
        else:
            for label, sel in (
                ("from_first_fill", slice(None)),
                ("from_day_after_first_fill", slice(1, None)),
            ):
                p, b = paper.iloc[sel], bt.iloc[sel]
                row[label] = {
                    "days": int(len(p)),
                    "paper_cum": float((1 + p).prod() - 1),
                    "backtest_cum": float((1 + b).prod() - 1),
                    "cum_diff_paper_minus_backtest": float((1 + p).prod() - (1 + b).prod()),
                    "daily_diff_std": float((p - b).std(ddof=1)) if len(p) > 1 else None,
                }
            row["daily"] = {
                str(d.date()): {"paper": float(paper[d]), "backtest": float(bt[d])} for d in days
            }
        row["backtest_pre_overlay_weights_changes"] = BACKTEST_PICKS.get(key)
        sess = summary["sessions"]
        slip_open = [
            f["slippage_vs_open_bps"] for f in fills if f.get("slippage_vs_open_bps") is not None
        ]
        slip_ref = [
            f["slippage_vs_reference_bps"]
            for f in fills
            if f.get("slippage_vs_reference_bps") is not None
        ]
        row["fills"] = {
            "orders": int(sum(s["orders"] for s in sess.values())),
            "unfilled": int(sum(s["unfilled"] for s in sess.values())),
            "filled_partial": int(sum(s["filled_partial"] for s in sess.values())),
            "cancelled_before_open": int(sum(s["cancelled_before_open"] for s in sess.values())),
            "fill_rows": len(fills),
            "slippage_vs_open_bps_median": float(np.median(slip_open)) if slip_open else None,
            "slippage_vs_open_bps_worst": float(max(slip_open)) if slip_open else None,
            "slippage_vs_reference_bps_median": float(np.median(slip_ref)) if slip_ref else None,
            "slippage_vs_reference_bps_worst": float(max(slip_ref)) if slip_ref else None,
            "sign": "positive = worse than benchmark (fills-summary convention)",
        }
        out[key] = row
    return out


# ------------------------------------------------------------------ report


def _f(x: float | None, nd: int = 2) -> str:
    return "null" if x is None else f"{x:.{nd}f}"


def render_report(res: dict[str, Any]) -> str:
    corr, sh = res["correlation"], res["account_sharpe"]
    risk, fwd = res["risk_contribution"], res["forward_tracking"]["sleeves"]
    ex = risk["existing_account_equal_15000"]
    lines = [
        f"# Account review 2026-10 (T-20261002-30, numbers only, awaiting lead review) {''}"
        f"generated {res['generated_at']}. Details: account-review.json. Windows: anchor "
        "2024-01-08..09-17, ytd 2026-01-02..09-17, stress_common 2018-02-01..2023-08-31 "
        "(the 2016-05 stress window is null for every series except C2). S1-S3 from 2017-02-01, "
        "C2 from 2016-02-29, F1/F2 2017-10-04..2026-09-15 (v1.2 realization-dated, lag 2). "
        "SIP restated 2026-10-02: stored C2 differs from recompute (max abs 0.010).",
        "## Correlation (daily D / weekly W; rolling-63d median/p90 on anchor daily)",
        "| pair | anchor D | anchor W | ytd D | ytd W | s-common D | s-common W | roll63 med/p90 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for a, b in [
        ("S1", "C2"),
        ("S2", "S3"),
        ("S2", "C2"),
        ("S3", "C2"),
        ("S3", "F1"),
        ("S3", "F2"),
        ("C2", "F2"),
    ]:
        cells = [
            _f(corr[w][k][a][b])
            for w in ("anchor", "ytd2026", "stress_common")
            for k in ("daily", "weekly")
        ]
        rm, rp = corr["anchor"]["rolling63_median"][a][b], corr["anchor"]["rolling63_p90"][a][b]
        lines.append(f"| {a}-{b} | " + " | ".join(cells) + f" | {_f(rm)}/{_f(rp)} |")
    rc = ex["risk_contribution_share"]
    lines += [
        f"## Risk (4 sleeves x $15,000, 63d to {ex['window'][1]}): contribution "
        + ", ".join(f"{k} {v:.0%}" for k, v in rc.items())
        + f"; effective bets {ex['effective_bets']:.2f}; "
        f"book ann vol {ex['portfolio_ann_vol']:,.0f} USD",
    ]
    t = risk["t43_weights_cov_ending_last_v12_date"]
    lines.append(
        f"T-43 weights, 63d to {t['window'][1]}: "
        + ", ".join(f"{k} {v:.0%}" for k, v in t["risk_contribution_share"].items())
        + f"; effective bets {t['effective_bets']:.2f}"
    )
    ov = res["overlap"]
    lines.append(
        f"Overlap at {ov['as_of_close']} close (USD, total {ov['total_exposure_usd']:,.0f}): "
        + ", ".join(f"{r['symbol']} {r['total_usd']:,.0f}" for r in ov["by_symbol"][:6])
        + " (XLK held by S1+S2)"
    )
    lines += [
        "## Account Sharpe, combo/same-vol S3 control (10 bp; last col 20 bp anchor)",
        "| combo | anchor | ytd | s-common | 20bp anchor |",
        "|---|---|---|---|---|",
    ]
    for c in ["EQ4", "DROP_S1", "DROP_S2", "DROP_S3", "DROP_C2", "IV4", "IV4_F1", "IV4_F2", "T43"]:
        row = []
        for tag, wins in (
            ("bps10", ("anchor", "ytd2026", "stress_common")),
            ("bps20", ("anchor",)),
        ):
            for w in wins:
                x = sh[tag]["combinations"][c]["windows"][w]
                row.append(
                    "null"
                    if x["combo"] is None
                    else f"{x['combo']['sharpe']:.2f}/{x['control']['sharpe']:.2f}"
                )
        lines.append(f"| {c} | " + " | ".join(row) + " |")
    lines.append(
        "EQ4 equal 4 sleeves; DROP_x equal 3; IV4* inverse-63d-vol monthly; "
        "T43 S3 .60 C2 .335 F2 .12 F1 .025 borrow .08."
    )
    lines += ["## Joint losses (worst per span; 5 each in JSON)"]
    for lab, v in res["worst_windows"].items():
        for key in ("worst_21d", "worst_63d"):
            w = v[key][0]
            parts = ", ".join(f"{k} {x:+.1%}" for k, x in w["sleeve_returns"].items())
            lines.append(
                f"{lab} {key}: {w['start']}..{w['end']} {w['combo_return']:+.1%} ({parts})"
            )
    lines += [
        "## Forward paper vs backtest (first fill..2026-10-02; paper = ledger P&L on SIP closes)",
    ]
    lines += [
        "| sleeve | days | cum diff | from day 2 | daily sd | slip bp med/worst | unfilled/part |",
        "|---|---|---|---|---|---|---|",
    ]
    for k, v in fwd.items():
        a, b = v["from_first_fill"], v["from_day_after_first_fill"]
        fl = v["fills"]
        short = " (sample too short)" if v["sample_too_short"] else ""
        lines.append(
            f"| {k} | {v['trading_days']}{short} | {a['cum_diff_paper_minus_backtest']:+.2%} | "
            f"{b['cum_diff_paper_minus_backtest']:+.2%} | {a['daily_diff_std']:.2%} | "
            f"{fl['slippage_vs_open_bps_median']:.1f}/{fl['slippage_vs_open_bps_worst']:.1f} | "
            f"{fl['unfilled']}/{fl['filled_partial']} |"
        )
    lines.append(
        "S3: backtest held SHY 100% 09-01..09-30 (month-end signal chose cash); "
        "paper held UPRO from 09-21; "
        "TECL+UPRO in both from 10-01."
    )
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ main


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    frames, close, meta = load_series()
    BACKTEST_PICKS.update(meta["backtest_pre_overlay_weights_since_2026_08_28"])
    f10, f20 = frames["10"], frames["20"]
    RETURNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(
        [f10.add_suffix("__net10"), f20[SLEEVES[:3] + ["C2"]].add_suffix("__net20")], axis=1
    ).to_parquet(RETURNS_PATH)

    rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
    shy = (close["SHY"] / close["SHY"].shift(1) - 1.0).fillna(0.0)
    s3_10, s3_20 = f10["S3"], f20["S3"]

    correlation = {name: corr_block(f10, win) for name, win in WINDOWS.items()}

    asof_cov = risk_contribution(f10, SLEEVES, np.full(4, SLEEVE_CAPITAL), RISK_ASOF)
    t43_cols = list(T43_WEIGHTS)
    last_v12 = f10[["F1", "F2"]].dropna().index[-1]
    t43_cov_v12 = risk_contribution(
        f10, t43_cols, np.array([T43_WEIGHTS[c] for c in t43_cols]), last_v12
    )
    risk = {
        "existing_account_equal_15000": asof_cov,
        "t43_weights_cov_ending_last_v12_date": {
            **t43_cov_v12,
            "note": "v1.2 series end 2026-09-15, so this covariance cannot end 2026-09-30; "
            "borrow leg (-0.08) carries no volatility",
        },
    }

    close_last = close.index[-1]
    ov = overlap(str(close_last.date()))

    account_sharpe: dict[str, Any] = {}
    account_sharpe["definition"] = (
        "Sharpe = mean/std(ddof=1) of daily return minus BIL * sqrt(252); monthly rebalance, 5 bp "
        "turnover cost; control = k*S3 + (1-k)*SHY with k = std(combo)/std(S3) over the window"
    )
    combo_series: dict[str, dict[str, pd.Series]] = {}
    for tag, frame, s3 in (("10", f10, s3_10), ("20", f20, s3_20)):
        combos = build_combos(frame)
        combo_series[tag] = combos
        table: dict[str, Any] = {}
        for cname, ret in combos.items():
            table[cname] = {
                "span": [str(ret.index[0].date()), str(ret.index[-1].date())] if len(ret) else None,
                "windows": {
                    wname: window_sharpe(ret, s3, shy, rf, win) for wname, win in WINDOWS.items()
                },
            }
        solo = {
            k: {
                w: (stats(in_window(frame[k], win), rf) if covers(frame[k], win) else None)
                for w, win in WINDOWS.items()
            }
            for k in ALL
        }
        account_sharpe[f"bps{tag}"] = {"combinations": table, "single_series": solo}
    account_sharpe["combo_definitions"] = {
        "EQ4": "S1,S2,S3,C2 equal capital",
        "DROP_x": "the other three sleeves, equal capital",
        "IV4": "four sleeves, inverse 63d vol at each month start (baseline for the F rows)",
        "IV4_F1": "four sleeves + v1.2 F1, inverse 63d vol at each month start",
        "IV4_F2": "four sleeves + v1.2 F2, inverse 63d vol at each month start",
        "T43": f"T-43 weights {T43_WEIGHTS} with borrow {T43_BORROW} at {dd.DEBIT_RATE:.3f}",
    }

    c10 = combo_series["10"]
    worst = {}
    for label, cname, cols in (
        ("EQ4", "EQ4", SLEEVES),
        ("IV4_F1", "IV4_F1", SLEEVES + ["F1"]),
    ):
        ret = c10[cname]
        worst[label] = {
            "span": [str(ret.index[0].date()), str(ret.index[-1].date())],
            "worst_21d": worst_windows(f10, ret, cols, 21),
            "worst_63d": worst_windows(f10, ret, cols, 63),
        }

    fwd = forward(f10, close, close_last)
    recon = json.loads((ROOT / "reports/paper/reconciliation.json").read_text())

    result = {
        "generated_at": stamp,
        "task": "T-20261002-30",
        "series": meta,
        "returns_file": str(RETURNS_PATH.relative_to(ROOT)),
        "windows": WINDOWS,
        "correlation": correlation,
        "risk_contribution": risk,
        "overlap": ov,
        "account_sharpe": account_sharpe,
        "worst_windows": worst,
        "forward_tracking": {
            "reconciliation_generated_at": recon.get("generated_at"),
            "reconciliation_status": recon.get("status"),
            "last_sip_close_used": str(close_last.date()),
            "sleeves": fwd,
            "c2_note": "C2 backtest comparison uses the lane recomputation after 2026-09-17",
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "account-review.json").write_text(
        json.dumps(result, indent=1, default=str) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "report.md").write_text(render_report(result), encoding="utf-8")
    print("wrote", OUT_DIR / "account-review.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
