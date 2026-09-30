"""T-20260929-80 cheap IC negation test: DAT / miner stock vs coin beta-hedged spread.

Iteration ``h20260929_80_dat_vs_coin``. Everything numeric below (pairs, signals, horizon,
thresholds, windows, gate) is frozen in the iteration's ``direction-review.json`` and
``candidate-manifest.json`` before this script computes any spread return or IC.

Two modes:

* ``feasibility`` -- loads prices, applies ``sanitize_price_matrices`` defaults and the SBET
  continuity rule, and reports row counts / coverage / dropped items. Computes no returns
  beyond the SBET continuity check and no IC.
* ``ic`` -- builds the three beta-hedged spreads and the four signal families (Z120, Z250,
  M20, M60), computes Spearman IC against the next-20-session beta-hedged spread return
  (open t+1 -> open t+21), Newey-West (lag 20) t, 500 random-alignment placebos and the
  independent |z|>1 (or |R|>=10%) episode counts per window, and writes ``results.json``
  with mechanical ``gate_checks``.

Run under ``scripts/run_capped.sh --mem 1.8G -- uv run python scripts/run_h20260929_80_dat_ic.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.features.price_hygiene import sanitize_price_matrices  # noqa: E402

ITER_ID = "h20260929_80_dat_vs_coin"
ITER_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
RESULTS_PATH = ITER_DIR / "results.json"
FEASIBILITY_PATH = ITER_DIR / "feasibility-observed.json"

PANEL_START = "2019-01-01"
SESSION_PRICES = ROOT / "data" / "research" / "crypto" / "session_prices.parquet"
SIP_GLOB = str(ROOT / "data" / "sip" / "daily" / "*" / "*.parquet")

MSTR = ["MSTR"]
MINERS = ["MARA", "RIOT", "CLSK", "CIFR", "WULF", "HUT", "IREN", "CORZ"]
ETH_TREASURY = ["BMNR", "SBET"]
COIN_ETF = {"BTC": "FBTC", "ETH": "ETHA"}
COIN_SPOT = {"BTC": "BTCUSD", "ETH": "ETHUSD"}
COIN_ETF_START = {"BTC": "2024-01-11", "ETH": "2024-07-23"}
# P3 members enter only from the ETH-treasury pivot dates (frozen, see direction-review.json).
P3_START = "2025-05-27"
SBET_START = "2025-05-27"
# Miner entry dates where the local ticker history starts as a SPAC / other security (checked in
# price data before any spread return: CIFR SPAC prices ~ $10 until the 2021-08-30 merger session,
# WULF close 33.9 -> 20.3 on 2021-12-14 = first TeraWulf session). Others enter on their first
# post-hygiene row ("按各自上市日进入").
MEMBER_ENTRY = {"CIFR": "2021-08-30", "WULF": "2021-12-14"}
SBET_MAX_ABS_LOG_RET = 0.5  # |log return| > 50% between adjacent sessions is dropped and reported

PAIRS = {
    "P1": {"name": "MSTR/BTC", "members": MSTR, "coin": "BTC", "start": None},
    "P2": {"name": "miner basket/BTC", "members": MINERS, "coin": "BTC", "start": None},
    "P3": {
        "name": "ETH treasury basket/ETH",
        "members": ETH_TREASURY,
        "coin": "ETH",
        "start": P3_START,
    },
}
SIGNALS = {
    "Z120": {"family": "Z", "param": 120, "expected_sign": -1},
    "Z250": {"family": "Z", "param": 250, "expected_sign": -1},
    "M20": {"family": "M", "param": 20, "expected_sign": +1},
    "M60": {"family": "M", "param": 60, "expected_sign": +1},
}
WINDOWS = {
    "anchor": ("2024-01-08", "2026-09-17"),
    "stress": ("2020-08-11", "2023-12-29"),
}
HORIZON = 20
NW_LAG = 20
N_PLACEBO = 500
PLACEBO_SEED = 20260930
BETA_WINDOW = 60
BETA_MIN_OBS = 40
BETA_CLIP = (0.5, 3.0)
EPISODE_GAP = 20
Z_THRESHOLD = 1.0
M_THRESHOLD = 0.10
MIN_STRESS_OBS = 60  # stress window "has data" only with at least this many valid sessions
MIN_ANCHOR_EPISODES = 6
MIN_ABS_T = 2.0


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------


def load_prices() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(close, open, report): DAT stocks + coin ETFs on the SPY session calendar, sanitized."""
    symbols = sorted({*MSTR, *MINERS, *ETH_TREASURY, *COIN_ETF.values(), "SPY"})
    in_list = ",".join(f"'{s}'" for s in symbols)
    con = duckdb.connect()
    frame = con.execute(
        f"""
        SELECT symbol, timestamp::DATE AS d, open, close, volume, trade_count
        FROM read_parquet('{SIP_GLOB}')
        WHERE symbol IN ({in_list}) AND timestamp::DATE >= DATE '{PANEL_START}'
        """
    ).df()
    con.close()
    raw_rows = frame.groupby("symbol").size().to_dict()
    ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
    n_ghost = frame.loc[ghost].groupby("symbol").size().to_dict()
    frame = (
        frame.loc[~ghost].sort_values("volume", ascending=False).drop_duplicates(["symbol", "d"])
    )
    close = frame.pivot(index="d", columns="symbol", values="close").sort_index()
    open_ = frame.pivot(index="d", columns="symbol", values="open").sort_index()
    close.index = pd.to_datetime(close.index)
    open_.index = pd.to_datetime(open_.index)
    calendar = close["SPY"].dropna().index
    close = close.reindex(calendar).drop(columns=["SPY"])
    open_ = open_.reindex(calendar).drop(columns=["SPY"])
    close, open_, hygiene = sanitize_price_matrices(close, open_)
    assert open_ is not None
    report: dict = {
        "raw_rows_since_panel_start": {k: int(v) for k, v in raw_rows.items()},
        "ghost_bar_rows_dropped": {k: int(v) for k, v in n_ghost.items()},
        "hygiene_manifest": hygiene.manifest(),
        "discards": [],
    }
    # Frozen symbol-specific rules from the plan.
    if "SBET" in close.columns:
        pre = close.index < pd.Timestamp(SBET_START)
        n_pre = int(close.loc[pre, "SBET"].notna().sum())
        close.loc[pre, "SBET"] = np.nan
        open_.loc[pre, "SBET"] = np.nan
        report["discards"].append(
            {"symbol": "SBET", "rule": f"pre-{SBET_START} rows (reused ticker)", "rows": n_pre}
        )
        ret = np.log(close["SBET"] / close["SBET"].shift(1))
        bad = ret[ret.abs() > SBET_MAX_ABS_LOG_RET].dropna()
        for date, val in bad.items():
            report["discards"].append(
                {
                    "symbol": "SBET",
                    "rule": "adjacent-session |log return| > 0.5 (not verified as split)",
                    "session": str(date.date()),
                    "log_return": float(val),
                }
            )
        # Blank the price at the offending session so neither return touching it survives.
        for date in bad.index:
            close.loc[date, "SBET"] = np.nan
            open_.loc[date, "SBET"] = np.nan
    for sym, entry in MEMBER_ENTRY.items():
        if sym in close.columns:
            pre = close.index < pd.Timestamp(entry)
            n_pre = int(close.loc[pre, sym].notna().sum())
            close.loc[pre, sym] = np.nan
            open_.loc[pre, sym] = np.nan
            report["discards"].append(
                {"symbol": sym, "rule": f"pre-{entry} rows (SPAC / prior security)", "rows": n_pre}
            )
    if "BMNR" in close.columns:
        pre = close.index < pd.Timestamp("2025-06-05")
        n_pre = int(close.loc[pre, "BMNR"].notna().sum())
        close.loc[pre, "BMNR"] = np.nan
        open_.loc[pre, "BMNR"] = np.nan
        report["discards"].append(
            {"symbol": "BMNR", "rule": "pre-2025-06-05 rows (reused ticker)", "rows": n_pre}
        )
    return close, open_, report


def load_spot() -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = pd.read_parquet(SESSION_PRICES, columns=["symbol", "date", "open", "close"])
    frame["date"] = pd.to_datetime(frame["date"])
    close = frame.pivot(index="date", columns="symbol", values="close").sort_index()
    open_ = frame.pivot(index="date", columns="symbol", values="open").sort_index()
    return close, open_


def coverage_table(close: pd.DataFrame) -> dict:
    out = {}
    for sym in close.columns:
        s = close[sym].dropna()
        out[sym] = {
            "rows": int(len(s)),
            "first": str(s.index[0].date()) if len(s) else None,
            "last": str(s.index[-1].date()) if len(s) else None,
        }
    return out


# ---------------------------------------------------------------------------
# spread construction
# ---------------------------------------------------------------------------


def coin_series(
    coin: str,
    calendar: pd.DatetimeIndex,
    etf_close: pd.DataFrame,
    etf_open: pd.DataFrame,
    spot_close: pd.DataFrame,
    spot_open: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    """(daily close-to-close log return, log open level) of the coin leg.

    The ETF (FBTC / ETHA) is used on sessions where it has both today's and the previous
    close (or open) and the spot session price otherwise, so the hedge leg is the ETF from
    2024-01-11 (BTC) / 2024-07-23 (ETH) and spot before that.
    """
    etf, spot = COIN_ETF[coin], COIN_SPOT[coin]
    sc = spot_close[spot].reindex(calendar)
    so = spot_open[spot].reindex(calendar)
    ec = etf_close[etf].reindex(calendar)
    eo = etf_open[etf].reindex(calendar)
    r_spot = np.log(sc / sc.shift(1))
    r_etf = np.log(ec / ec.shift(1))
    ret = r_etf.where(r_etf.notna(), r_spot)
    on_spot = np.log(so / sc.shift(1))
    on_etf = np.log(eo / ec.shift(1))
    overnight = on_etf.where(on_etf.notna(), on_spot)
    level_close = ret.fillna(0.0).cumsum()
    log_open = level_close.shift(1) + overnight
    return ret, log_open


def dat_series(
    members: list[str],
    start: str | None,
    close: pd.DataFrame,
    open_: pd.DataFrame,
) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    """(equal-weight daily log return, per-member log open, per-member valid mask).

    Members contribute a daily return only when both closes are valid (no padding) and,
    for P3, from the pair start date. The basket window return is the mean of member
    ``ln(open_{t+21}/open_{t+1})`` over members valid at both opens.
    """
    cols = [m for m in members if m in close.columns]
    c = close[cols].copy()
    o = open_[cols].copy()
    if start is not None:
        mask = c.index < pd.Timestamp(start)
        c.loc[mask] = np.nan
        o.loc[mask] = np.nan
    r = np.log(c / c.shift(1))
    ret = r.mean(axis=1, skipna=True)
    ret[r.notna().sum(axis=1) == 0] = np.nan
    return ret, np.log(o), r


def rolling_beta(r_dat: pd.Series, r_coin: pd.Series) -> pd.Series:
    both = pd.concat([r_dat, r_coin], axis=1, keys=["d", "c"])
    valid = both.notna().all(axis=1)
    d = both["d"].where(valid)
    c = both["c"].where(valid)
    n = valid.astype(float).rolling(BETA_WINDOW, min_periods=1).sum()
    mean_d = d.rolling(BETA_WINDOW, min_periods=BETA_MIN_OBS).mean()
    mean_c = c.rolling(BETA_WINDOW, min_periods=BETA_MIN_OBS).mean()
    cov = (d * c).rolling(BETA_WINDOW, min_periods=BETA_MIN_OBS).mean() - mean_d * mean_c
    var = (c * c).rolling(BETA_WINDOW, min_periods=BETA_MIN_OBS).mean() - mean_c**2
    beta = (cov / var).clip(*BETA_CLIP)
    beta[n < BETA_MIN_OBS] = np.nan
    return beta


def log_price_ratio(r_dat: pd.Series, r_coin: pd.Series) -> pd.Series:
    """Cumulative log(DAT/coin) ratio, NaN until the DAT leg has its first valid return.

    Missing days inside the sample count as no move; before the pair starts the ratio is NaN so
    a rolling z-score never mixes a flat pre-listing zero history into its mean and std.
    """
    ratio = (r_dat.fillna(0.0) - r_coin.fillna(0.0)).cumsum()
    return ratio.where(r_dat.expanding().count() > 0)


def build_pair(
    pair: dict,
    close: pd.DataFrame,
    open_: pd.DataFrame,
    spot_close: pd.DataFrame,
    spot_open: pd.DataFrame,
) -> dict[str, pd.Series]:
    cal = close.index
    r_coin, coin_log_open = coin_series(pair["coin"], cal, close, open_, spot_close, spot_open)
    r_dat, dat_log_open, _ = dat_series(pair["members"], pair["start"], close, open_)
    beta = rolling_beta(r_dat, r_coin)
    # Forward 20-session open->open window from the next open (t+1) to t+1+20.
    dat_open_df = dat_log_open
    # Members must be valid at both opens; mean over members valid at both.
    both_valid = dat_open_df.shift(-(HORIZON + 1)).notna() & dat_open_df.shift(-1).notna()
    diff = dat_open_df.shift(-(HORIZON + 1)) - dat_open_df.shift(-1)
    win_dat = diff.where(both_valid).mean(axis=1, skipna=True)
    win_dat[both_valid.sum(axis=1) == 0] = np.nan
    win_coin = coin_log_open.shift(-(HORIZON + 1)) - coin_log_open.shift(-1)
    fwd = win_dat - beta * win_coin
    # Signals. Z uses the unhedged cumulative log ratio; M uses the lagged-beta hedged return.
    ratio = log_price_ratio(r_dat, r_coin)
    hedged_daily = r_dat - beta.shift(1) * r_coin
    out: dict[str, pd.Series] = {"fwd": fwd, "beta": beta}
    for name, spec in SIGNALS.items():
        n = spec["param"]
        if spec["family"] == "Z":
            mu = ratio.rolling(n, min_periods=n).mean()
            sd = ratio.rolling(n, min_periods=n).std()
            out[name] = (ratio - mu) / sd
        else:
            out[name] = hedged_daily.rolling(n, min_periods=n).sum()
    return out


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------


def _zrank(x: np.ndarray) -> np.ndarray:
    r = pd.Series(x).rank(method="average").to_numpy()
    r = r - r.mean()
    sd = r.std()
    return r / sd if sd > 0 else np.full_like(r, np.nan)


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    zx, zy = _zrank(x), _zrank(y)
    return float(np.mean(zx * zy))


def newey_west_t(x: np.ndarray, lag: int) -> float | None:
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < lag + 5:
        return None
    m = x.mean()
    e = x - m
    gamma0 = float(np.dot(e, e) / n)
    lrv = gamma0
    for k in range(1, lag + 1):
        w = 1.0 - k / (lag + 1.0)
        lrv += 2.0 * w * float(np.dot(e[k:], e[:-k]) / n)
    if lrv <= 0:
        return None
    return float(m / np.sqrt(lrv / n))


def ic_stats(
    sig: np.ndarray, fwd: np.ndarray, expected_sign: int, rng: np.random.Generator
) -> dict:
    n = len(sig)
    if n < MIN_STRESS_OBS:
        return {"n_obs": int(n), "ic": None, "nw_t": None, "placebo_pct": None}
    zx, zy = _zrank(sig), _zrank(fwd)
    prod = zx * zy
    ic = float(prod.mean())
    nw_t = newey_west_t(prod, NW_LAG)
    obs_adj = expected_sign * ic
    placebo = np.empty(N_PLACEBO)
    for i in range(N_PLACEBO):
        shift = int(rng.integers(HORIZON + 1, n - HORIZON))
        placebo[i] = expected_sign * float(np.mean(np.roll(zx, shift) * zy))
    return {
        "n_obs": int(n),
        "ic": ic,
        "nw_t": nw_t,
        "placebo_pct": float(np.mean(placebo < obs_adj) * 100.0),
        "placebo_p_one_sided": float(np.mean(placebo >= obs_adj)),
        "placebo_ic_p95_sign_adjusted": float(np.quantile(placebo, 0.95)),
    }


def count_episodes(dates: pd.DatetimeIndex, active: np.ndarray, calendar: pd.DatetimeIndex) -> int:
    pos = calendar.get_indexer(dates)
    count, last = 0, None
    for p, flag in zip(pos, active, strict=True):
        if not flag:
            continue
        if last is None or p - last >= EPISODE_GAP:
            count += 1
            last = p
    return count


def evaluate(series: dict[str, dict[str, pd.Series]], calendar: pd.DatetimeIndex) -> list[dict]:
    rng = np.random.default_rng(PLACEBO_SEED)
    rows: list[dict] = []
    for pair_id, pair_series in series.items():
        for sig_name, spec in SIGNALS.items():
            for window, (lo, hi) in WINDOWS.items():
                sig = pair_series[sig_name]
                fwd = pair_series["fwd"]
                df = pd.concat([sig, fwd], axis=1, keys=["s", "f"]).dropna()
                df = df[(df.index >= lo) & (df.index <= hi)]
                st = ic_stats(df["s"].to_numpy(), df["f"].to_numpy(), spec["expected_sign"], rng)
                thr = Z_THRESHOLD if spec["family"] == "Z" else M_THRESHOLD
                active = (
                    (df["s"].abs() > thr).to_numpy()
                    if spec["family"] == "Z"
                    else (df["s"].abs() >= thr).to_numpy()
                )
                row = {
                    "pair": pair_id,
                    "signal": sig_name,
                    "window": window,
                    "expected_ic_sign": spec["expected_sign"],
                    "first_date": str(df.index[0].date()) if len(df) else None,
                    "last_date": str(df.index[-1].date()) if len(df) else None,
                    "n_episodes": count_episodes(df.index, active, calendar) if len(df) else 0,
                    "episode_rule": (
                        f"|z|>{Z_THRESHOLD}" if spec["family"] == "Z" else f"|R|>={M_THRESHOLD}"
                    )
                    + f", starts >= {EPISODE_GAP} sessions apart",
                }
                row.update(st)
                ic = row.get("ic")
                row["sign_matches_preregistered"] = (
                    None if ic is None else bool(np.sign(ic) == spec["expected_sign"])
                )
                rows.append(row)
    return rows


def gate_checks(rows: list[dict]) -> dict:
    """Mechanical reading of the frozen continue condition, per (pair, signal) cell."""
    cells: dict[str, dict] = {}
    lookup = {(r["pair"], r["signal"], r["window"]): r for r in rows}
    for pair_id in PAIRS:
        for sig in SIGNALS:
            a = lookup[(pair_id, sig, "anchor")]
            s = lookup[(pair_id, sig, "stress")]
            a_ok_sign = a["sign_matches_preregistered"] is True
            a_t = a["nw_t"]
            a_t_ok = a_t is not None and abs(a_t) >= MIN_ABS_T
            stress_has_data = s["n_obs"] >= MIN_STRESS_OBS
            stress_ok = (not stress_has_data) or s["sign_matches_preregistered"] is True
            episodes_ok = a["n_episodes"] >= MIN_ANCHOR_EPISODES
            checks = {
                "c1_anchor_sign_matches_preregistered": {
                    "value": a["ic"],
                    "expected_sign": a["expected_ic_sign"],
                    "pass": bool(a_ok_sign),
                },
                "c2_anchor_abs_nw_t_ge_2.0": {
                    "value": a_t,
                    "threshold": MIN_ABS_T,
                    "pass": bool(a_t_ok),
                },
                "c3_stress_same_sign_when_data": {
                    "stress_has_data": bool(stress_has_data),
                    "stress_n_obs": s["n_obs"],
                    "stress_ic": s["ic"],
                    "stress_nw_t": s["nw_t"],
                    "pass": bool(stress_ok),
                    "note": "not applicable (no stress data)" if not stress_has_data else "",
                },
                "c4_anchor_independent_episodes_ge_6": {
                    "value": a["n_episodes"],
                    "threshold": MIN_ANCHOR_EPISODES,
                    "pass": bool(episodes_ok),
                },
            }
            cells[f"{pair_id}_{sig}"] = {
                "checks": checks,
                "all_pass": bool(all(c["pass"] for c in checks.values())),
            }
    passing = [k for k, v in cells.items() if v["all_pass"]]
    return {
        "rule": (
            "continue only if at least one (pair, signal) cell has, on the anchor window, IC "
            "sign equal to the preregistered sign with NW(lag 20) |t| >= 2.0, the stress window "
            "(where >= 60 valid sessions exist) has the same sign, and >= 6 independent anchor "
            "episodes"
        ),
        "cells": cells,
        "passing_cells": passing,
        "continue": bool(passing),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def run_feasibility() -> None:
    close, open_, report = load_prices()
    report["coverage_after_hygiene"] = coverage_table(close)
    spot_close, _ = load_spot()
    report["spot_coverage"] = coverage_table(spot_close[["BTCUSD", "ETHUSD"]])
    report["calendar"] = [str(close.index[0].date()), str(close.index[-1].date())]
    FEASIBILITY_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("coverage_after_hygiene", "discards")}, indent=1))


def run_ic() -> None:
    close, open_, report = load_prices()
    spot_close, spot_open = load_spot()
    calendar = close.index
    series = {pid: build_pair(p, close, open_, spot_close, spot_open) for pid, p in PAIRS.items()}
    rows = evaluate(series, calendar)
    gate = gate_checks(rows)
    payload = {
        "iter_id": ITER_ID,
        "stage": "ic_gate_only",
        "verdict": "continue_to_screen" if gate["continue"] else "refuted_or_evidence_too_weak",
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "windows": WINDOWS,
        "horizon_sessions": HORIZON,
        "newey_west_lag": NW_LAG,
        "n_placebo": N_PLACEBO,
        "placebo_seed": PLACEBO_SEED,
        "placebo_definition": (
            "circular shift of the signal against the forward spread return by a random "
            "offset in [21, n-21]; placebo_pct = percent of 500 placebo sign-adjusted ICs "
            "strictly below the observed sign-adjusted IC"
        ),
        "ic_table": rows,
        "gate_checks": gate,
        "discard_list": report["discards"],
        "hygiene_manifest": report["hygiene_manifest"],
        "coverage_after_hygiene": coverage_table(close),
        "beta_summary": {
            pid: {
                "mean": float(s["beta"].mean()),
                "min": float(s["beta"].min()),
                "max": float(s["beta"].max()),
                "first_valid": str(s["beta"].first_valid_index().date()),
            }
            for pid, s in series.items()
        },
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"verdict": payload["verdict"], "passing_cells": gate["passing_cells"]}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["feasibility", "ic"])
    args = parser.parse_args()
    if args.mode == "feasibility":
        run_feasibility()
    else:
        run_ic()


if __name__ == "__main__":
    main()
