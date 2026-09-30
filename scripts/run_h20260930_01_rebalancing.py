"""T-20260930-01: 60/40 rebalancing-pressure front-run (Harvey-Mazzoleni-Melone), equity leg.

Iteration ``h20260930_01_rebalancing_front_run``. Signal formulas, windows, regressions, gates and
candidates are frozen in ``preregistration.md`` / ``candidate-manifest.json`` before any number is
computed here.

Modes:

* ``regress`` -- builds Threshold / Calendar / W signals from SPY and IEF closes, runs the HC3
  negation regressions (overnight, intraday, total; SPY and SPY-IEF; three windows), 500
  date-shift placebos, the dividend check, and writes ``results.json`` with ``gate_checks``.
* ``ledger`` -- only after G1-G3 pass: candidate net ledgers R1-R8 (see ``run_ledger``).

Run under ``scripts/run_capped.sh --mem 600M -- uv run python
scripts/run_h20260930_01_rebalancing.py regress``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ITER_ID = "h20260930_01_rebalancing_front_run"
ITER_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
RESULTS_PATH = ITER_DIR / "results.json"
SIP_GLOB = str(ROOT / "data" / "sip" / "daily" / "*" / "*.parquet")
LONGBRIDGE_DIR = ROOT / "data" / "research" / "longbridge_adjusted_daily"

SYMBOLS = ["SPY", "IEF", "TLT", "QQQ", "TQQQ", "SQQQ", "BIL"]
TARGET = 0.6
DELTAS = [round(0.001 * i, 3) for i in range(1, 26)]  # 0.1% .. 2.5%
NORM = 0.012
SEED = 20260930
N_PLACEBO = 500
SHIFT_MIN, SHIFT_MAX = 10, 60

WINDOWS = {
    "full": ("2016-01-05", "2026-09-29"),
    "stress": ("2016-05-02", "2023-08-31"),
    "anchor": ("2024-01-08", "2026-09-29"),
}
GATE_T_FULL = -2.5
GATE_T_ANCHOR = 2.0
GATE_SHARPE = 0.8


# --------------------------------------------------------------------------- signals
def simulate_portfolio(
    ret_s: np.ndarray, ret_i: np.ndarray, delta: float | None, month_end: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray]:
    """Weight-drift simulation of a 60/40 portfolio.

    Returns ``(dev, signal)``: ``dev[t]`` = pre-rebalance weight minus 0.6 at the close of t;
    ``signal[t]`` = dev[t] when a reset happens at t (Threshold: ``|dev| > delta``), else 0.
    For the Calendar portfolio pass ``delta=None`` and a boolean ``month_end`` array: it is reset
    at month ends and ``signal`` equals ``dev`` on every day. Element 0 is the initial state
    (weight 0.6, no return), so ``dev[0] = 0``.
    """
    n = len(ret_s)
    dev = np.zeros(n)
    sig = np.zeros(n)
    w_post = TARGET
    for t in range(1, n):
        grown_s = w_post * (1.0 + ret_s[t])
        grown_i = (1.0 - w_post) * (1.0 + ret_i[t])
        w_pre = grown_s / (grown_s + grown_i)
        dev[t] = w_pre - TARGET
        if delta is not None:
            if abs(dev[t]) > delta:
                sig[t] = dev[t]
                w_post = TARGET
            else:
                w_post = w_pre
        else:
            sig[t] = dev[t]
            w_post = TARGET if (month_end is not None and month_end[t]) else w_pre
    return dev, sig


def threshold_signal(ret_s: np.ndarray, ret_i: np.ndarray) -> np.ndarray:
    total = np.zeros(len(ret_s))
    for delta in DELTAS:
        total += simulate_portfolio(ret_s, ret_i, delta, None)[1]
    return total / len(DELTAS)


def month_position(index: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """``(month_end, k)``: month_end[t] True when the next data session is in a different
    month; k[t] = 1 + later sessions in the same month, or 0 when the month is not followed by
    a later month in the data (incomplete last month)."""
    n = len(index)
    ym = index.year * 100 + index.month
    month_end = np.zeros(n, dtype=bool)
    k = np.zeros(n, dtype=int)
    for t in range(n - 1):
        month_end[t] = ym[t + 1] != ym[t]
    # k: count backwards within a month, only for months with a later month present
    last_ym = ym[-1]
    count = 0
    for t in range(n - 1, -1, -1):
        if ym[t] == last_ym:
            k[t] = 0
            continue
        if t == n - 1 or ym[t + 1] != ym[t]:
            count = 1
        else:
            count += 1
        k[t] = count
    return month_end, k


def calendar_signals(
    ret_s: np.ndarray, ret_i: np.ndarray, index: pd.DatetimeIndex
) -> tuple[np.ndarray, np.ndarray]:
    """``(dev_c, cal_mod)``. CalMod = -sign(dev) for k in 2..5, +sign(dev at the k=5 session) for
    k == 1, 0 otherwise (see preregistration.md)."""
    month_end, k = month_position(index)
    dev_c, _ = simulate_portfolio(ret_s, ret_i, None, month_end)
    n = len(index)
    cal = np.zeros(n)
    for t in range(n):
        if 2 <= k[t] <= 5:
            cal[t] = -np.sign(dev_c[t])
        elif k[t] == 1 and t >= 4 and k[t - 4] == 5:
            cal[t] = np.sign(dev_c[t - 4])
    return dev_c, cal


def build_signals(close: pd.DataFrame) -> pd.DataFrame:
    ret = close[["SPY", "IEF"]].pct_change()
    rs = ret["SPY"].fillna(0.0).to_numpy()
    ri = ret["IEF"].fillna(0.0).to_numpy()
    thr = threshold_signal(rs, ri)
    dev_c, cal_mod = calendar_signals(rs, ri, close.index)
    _, k = month_position(close.index)
    cal_l4 = np.where((k >= 2) & (k <= 5), dev_c, 0.0)
    w = 0.6 * (-thr / NORM) + 0.4 * cal_mod
    return pd.DataFrame(
        {"THR": thr, "CAL_L4": cal_l4, "CALMOD": cal_mod, "W": w, "DEV_C": dev_c, "K": k},
        index=close.index,
    )


# --------------------------------------------------------------------------- regression
def hc3_slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """OLS y = a + b x with HC3 standard error. Returns (b, se, t)."""
    n = len(x)
    if n < 30 or np.std(x) == 0:
        return float("nan"), float("nan"), float("nan")
    xm = x - x.mean()
    sxx = float(np.dot(xm, xm))
    b = float(np.dot(xm, y - y.mean()) / sxx)
    a = float(y.mean() - b * x.mean())
    e = y - a - b * x
    # leverage for simple regression with intercept
    h = 1.0 / n + xm**2 / sxx
    var_b = float(np.sum((xm**2) * (e**2) / (1.0 - h) ** 2) / sxx**2)
    se = var_b**0.5
    return b, se, b / se if se > 0 else float("nan")


def shifted_t(x: np.ndarray, y: np.ndarray, mask: np.ndarray, shifts: np.ndarray) -> np.ndarray:
    out = np.empty(len(shifts))
    for j, s in enumerate(shifts):
        xs = np.roll(x, int(s))
        out[j] = hc3_slope(xs[mask], y[mask])[2]
    return out


def make_shifts(rng: np.random.Generator, n: int = N_PLACEBO) -> np.ndarray:
    mag = rng.integers(SHIFT_MIN, SHIFT_MAX + 1, size=n)
    sign = rng.choice([-1, 1], size=n)
    return mag * sign


def next_day_segments(open_: pd.Series, close: pd.Series) -> dict[str, pd.Series]:
    """Segment returns of session t+1 indexed at t (the signal date)."""
    on = open_.shift(-1) / close - 1.0
    idr = close.shift(-1) / open_.shift(-1) - 1.0
    cc = close.shift(-1) / close - 1.0
    return {"ON": on, "ID": idr, "CC": cc}


def regression_table(
    sig: pd.DataFrame, open_: pd.DataFrame, close: pd.DataFrame
) -> tuple[list[dict], dict]:
    rng = np.random.default_rng(SEED)
    shifts = make_shifts(rng)
    seg_spy = next_day_segments(open_["SPY"], close["SPY"])
    seg_ief = next_day_segments(open_["IEF"], close["IEF"])
    legs = {
        "SPY": seg_spy,
        "SPY-IEF": {k: seg_spy[k] - seg_ief[k] for k in seg_spy},
    }
    expected = {"THR": -1, "CAL_L4": -1, "CALMOD": 1, "W": 1}
    idx = close.index
    # window masks by return date t+1
    ret_date = pd.Series(idx, index=idx).shift(-1)
    masks = {}
    for wname, (a, b) in WINDOWS.items():
        masks[wname] = ((ret_date >= a) & (ret_date <= b)).to_numpy()
    rows: list[dict] = []
    for leg, segs in legs.items():
        for seg, yser in segs.items():
            y_all = yser.to_numpy()
            for signame, sign_exp in expected.items():
                x_all = sig[signame].to_numpy()
                for wname, mask in masks.items():
                    m = mask & np.isfinite(y_all) & np.isfinite(x_all)
                    b, se, t = hc3_slope(x_all[m], y_all[m])
                    tp = shifted_t(x_all, np.nan_to_num(y_all), m, shifts)
                    tp = tp[np.isfinite(tp)]
                    # one-sided quantile in the expected direction: share of placebo t at or
                    # beyond the real t toward the expected side
                    if sign_exp < 0:
                        beyond = float(np.mean(tp <= t)) if np.isfinite(t) else float("nan")
                    else:
                        beyond = float(np.mean(tp >= t)) if np.isfinite(t) else float("nan")
                    two = float(np.mean(np.abs(tp) >= abs(t))) if np.isfinite(t) else float("nan")
                    rows.append(
                        {
                            "leg": leg,
                            "segment": seg,
                            "signal": signame,
                            "expected_sign": sign_exp,
                            "window": wname,
                            "n": int(m.sum()),
                            "coef": b,
                            "hc3_se": se,
                            "hc3_t": t,
                            "mean_y_bp": float(np.mean(y_all[m]) * 1e4),
                            "placebo_share_beyond_one_sided": beyond,
                            "placebo_share_beyond_two_sided": two,
                            "n_placebo": int(len(tp)),
                        }
                    )
    return rows, {"seed": SEED, "n_placebo": N_PLACEBO, "shift_range": [SHIFT_MIN, SHIFT_MAX]}


def cell(rows: list[dict], leg: str, segment: str, signal: str, window: str) -> dict:
    for r in rows:
        if (r["leg"], r["segment"], r["signal"], r["window"]) == (leg, segment, signal, window):
            return r
    raise KeyError((leg, segment, signal, window))


def regression_gates(rows: list[dict]) -> list[dict]:
    full = cell(rows, "SPY", "ID", "THR", "full")
    anchor = cell(rows, "SPY", "ID", "THR", "anchor")
    on_full = cell(rows, "SPY", "ON", "THR", "full")
    g1 = bool(full["coef"] < 0)
    g2 = bool(full["hc3_t"] <= GATE_T_FULL)
    g3 = bool(anchor["coef"] < 0 and abs(anchor["hc3_t"]) >= GATE_T_ANCHOR)
    overnight_dominant = bool(
        on_full["hc3_t"] < full["hc3_t"] and not (g2 and g3) and on_full["hc3_t"] <= GATE_T_FULL
    )
    return [
        {
            "id": "G1",
            "condition": "SPY open->close (ID) Threshold coefficient negative, full sample",
            "value": full["coef"],
            "passed": g1,
        },
        {
            "id": "G2",
            "condition": f"SPY ID Threshold full-sample HC3 t <= {GATE_T_FULL}",
            "value": full["hc3_t"],
            "passed": g2,
        },
        {
            "id": "G3",
            "condition": (
                "anchor window 2024-01-08..2026-09-29: coefficient negative and "
                f"|t| >= {GATE_T_ANCHOR}"
            ),
            "value": {"coef": anchor["coef"], "hc3_t": anchor["hc3_t"]},
            "passed": g3,
        },
        {
            "id": "G_overnight",
            "condition": (
                "informational: effect mainly overnight (ON t more negative than ID t, "
                "ON t <= -2.5, ID fails G2 or G3) -> not obtainable at a next-open fill"
            ),
            "value": {"on_full_t": on_full["hc3_t"], "id_full_t": full["hc3_t"]},
            "passed": overnight_dominant,
        },
    ]


# --------------------------------------------------------------------------- data
def load_prices() -> tuple[pd.DataFrame, pd.DataFrame]:
    import duckdb

    in_list = ",".join(f"'{s}'" for s in SYMBOLS)
    con = duckdb.connect()
    frame = con.execute(
        f"""
        SELECT symbol, timestamp::DATE AS d, open, close, volume
        FROM read_parquet('{SIP_GLOB}')
        WHERE symbol IN ({in_list})
        """
    ).df()
    con.close()
    frame = frame.sort_values("volume", ascending=False).drop_duplicates(["symbol", "d"])
    close = frame.pivot(index="d", columns="symbol", values="close").sort_index()
    open_ = frame.pivot(index="d", columns="symbol", values="open").sort_index()
    close.index = pd.to_datetime(close.index)
    open_.index = pd.to_datetime(open_.index)
    return open_, close


def dividend_check(open_: pd.DataFrame, close: pd.DataFrame) -> dict:
    """Are SIP closes dividend-adjusted? QQQ (has a local adjusted series) is the reference;
    SPY/IEF/TLT are judged from ex-dividend overnight gaps."""
    out: dict = {}
    qqq_path = LONGBRIDGE_DIR / "qqq_daily_longbridge_adjusted.csv"
    if qqq_path.exists():
        adj = pd.read_csv(qqq_path, usecols=["timestamp", "close"])
        adj["d"] = pd.to_datetime(adj["timestamp"].str[:10])
        adj = adj.set_index("d")["close"]
        both = pd.concat([close["QQQ"], adj], axis=1, keys=["sip", "adj"]).dropna()
        ratio = both["adj"] / both["sip"]
        out["QQQ_adjusted_over_sip_close"] = {
            "first_date": str(ratio.index[0].date()),
            "ratio_first": float(ratio.iloc[0]),
            "last_date": str(ratio.index[-1].date()),
            "ratio_last": float(ratio.iloc[-1]),
            "interpretation": (
                "ratio_first well below 1 would mean SIP closes are raw; a ratio near 1 "
                "means SIP closes are already dividend-adjusted"
            ),
        }
    ov = open_.shift(-1) / close - 1.0  # overnight into t+1, indexed t
    ov = ov.shift(1)  # overnight ending at open of t, indexed t
    days = pd.Series(close.index, index=close.index)
    first_bd = days.groupby([days.dt.year, days.dt.month]).transform("min") == days
    third_fri = (days.dt.weekday == 4) & (days.dt.day >= 15) & (days.dt.day <= 21)
    qtr_ex = third_fri & days.dt.month.isin([3, 6, 9, 12])
    for sym, flag, label in (
        ("IEF", first_bd, "first business day of month (monthly ex-dividend)"),
        ("TLT", first_bd, "first business day of month (monthly ex-dividend)"),
        ("SPY", qtr_ex, "third Friday of Mar/Jun/Sep/Dec (quarterly ex-dividend)"),
        ("QQQ", qtr_ex, "third Friday of Mar/Jun/Sep/Dec (reference symbol)"),
    ):
        s = ov[sym].dropna()
        f = flag.reindex(s.index).fillna(False)
        out[f"{sym}_overnight_gap_bp"] = {
            "ex_dividend_day_definition": label,
            "mean_on_ex_days_bp": float(s[f].mean() * 1e4),
            "n_ex_days": int(f.sum()),
            "mean_other_days_bp": float(s[~f].mean() * 1e4),
        }
    ratio_first = out.get("QQQ_adjusted_over_sip_close", {}).get("ratio_first")
    out["sip_closes_dividend_adjusted"] = (
        None if ratio_first is None else bool(abs(ratio_first - 1.0) < 0.005)
    )
    adjusted = out["sip_closes_dividend_adjusted"]
    if adjusted:
        out["conclusion"] = (
            "QQQ adjusted/SIP close ratio is within 0.5 percent of 1 at the first common date "
            "(2016-01-04) and stays there, so the SIP daily bars are already dividend-adjusted. "
            "SPY/IEF/TLT have no local adjusted series; the same convention is inferred (their "
            "ex-dividend overnight gap means above are far smaller than the dividend yield). "
            "Bond-leg returns then include coupon carry approximately."
        )
    else:
        out["conclusion"] = (
            "QQQ adjusted/SIP ratio differs from 1: SIP closes are raw. Bond legs (IEF/TLT) then "
            "under-count coupon carry; they are diagnostics only."
        )
    return out


# --------------------------------------------------------------------------- main
def run_regress() -> Path:
    open_, close = load_prices()
    for sym in ("SPY", "IEF"):
        assert close[sym].notna().sum() > 2500, sym
    span = {
        s: [str(close[s].dropna().index[0].date()), str(close[s].dropna().index[-1].date())]
        for s in SYMBOLS
    }
    idx = close["SPY"].dropna().index.intersection(close["IEF"].dropna().index)
    close_f, open_f = close.loc[idx], open_.loc[idx]
    sig = build_signals(close_f)
    rows, placebo_meta = regression_table(sig, open_f, close_f)
    gates = regression_gates(rows)
    div = dividend_check(open_, close)
    stats = {
        "n_sessions": int(len(idx)),
        "first": str(idx[0].date()),
        "last": str(idx[-1].date()),
        "symbol_span": span,
        "W_abs_ge_1_share": float((sig["W"].abs() >= 1).mean()),
        "THR_std": float(sig["THR"].std()),
        "W_std": float(sig["W"].std()),
        "calmod_nonzero_days": int((sig["CALMOD"] != 0).sum()),
    }
    ok = all(g["passed"] for g in gates if g["id"] in ("G1", "G2", "G3"))
    w_arr = sig["W"].to_numpy()
    pos = np.minimum(np.abs(w_arr), 1.0)
    id_w = cell(rows, "SPY", "ID", "W", "full")["coef"]
    implied = {
        "note": (
            "informational only, not a gate and not a ledger: full-sample regression coef of "
            "SPY open->close on W times E[|W| * min(|W|,1)] versus the open->close cost of "
            "2 * 10 bp * E[min(|W|,1)] per day (10 bp per side, entry and exit)"
        ),
        "coef_W_SPY_ID_full": id_w,
        "regression_implied_gross_bp_per_day": float(id_w * np.mean(np.abs(w_arr) * pos) * 1e4),
        "cost_bp_per_day_10bp_per_side_open_to_close": float(20.0 * pos.mean()),
        "mean_position": float(pos.mean()),
    }
    payload = {
        "iter_id": ITER_ID,
        "stage": "regression_negation_test",
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "signal_stats": stats,
        "placebo": placebo_meta,
        "windows_by_return_date": WINDOWS,
        "regression_table": rows,
        "dividend_check": div,
        "gate_checks": gates,
        "regression_gate_passed": ok,
        "ledger_run": False,
        "verdict": (
            "regression gate passed; run the candidate ledger"
            if ok
            else "stopped at the regression gate (G1-G3); no candidate ledger was run"
        ),
        "candidate_net_sharpe": {
            cid: None
            for cid in (
                "R1_SPREAD_SPY_IEF",
                "R2_SPREAD_SPY_TLT",
                "R3_SPY",
                "R4_QQQ",
                "R5_TQQQ_SQQQ",
                "R6_SPY_ABSW_GE1",
                "R7_SPREAD_ABSW_GE1",
                "R8_SPY_CALENDAR_ONLY",
            )
        },
        "informational_implied_gross_vs_cost": implied,
        "candidate_status": "not_run_gate_failed" if not ok else "pending_ledger",
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return RESULTS_PATH


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["regress", "ledger"])
    args = ap.parse_args(argv)
    if args.mode == "regress":
        path = run_regress()
        print(path)
        return 0
    raise SystemExit("ledger mode is only written if the regression gate passes")


if __name__ == "__main__":
    raise SystemExit(main())
