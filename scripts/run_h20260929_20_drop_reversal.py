"""Backtest for iteration h20260929_20_news_nonews_drop_reversal.

12 preregistered candidates (candidate-manifest.json): a market-adjusted
one-day drop of >=D (D in {5%, 8%}) in the top-1500 PIT-ADV tier, held
h in {1, 3, 5} sessions, entered at the open of t+1 and exited at the close
of t+h:

  DROP_NN_D{5,8}_H{1,3,5}    long the no-news drops (reversal leg)
  DRIFT_NEWS_D{5,8}_H{1,3,5} short the news-accompanied drops (drift leg,
                              top-1000-ADV tier only, borrow fee modeled)

Everything reuses the frozen S3 close-to-close/next-open-fill P&L formula
(`run_h20260922_05_salvage.legs`), generalized in `simulate_tiered` below to
support a per-symbol, per-day ADV-tiered spread cost and a short-borrow
carry cost, neither of which the frozen `salvage.simulate` supports. S3
comparisons (`correlation_with_s3`, `diversifier_edge_for_offset`,
`s3_incumbent`, `assert_same_session_convention`) are imported from
`scripts/screen_lane.py` unedited.

Placebos, computed for every candidate at the trade level (not as separate
portfolio candidates): (i) news/no-news labels shuffled within each day's
qualifying events; (ii) the same stocks redated to a random other TEST-window
trading date. Both use a cluster-robust (by entry date) standard error for
the trade-level average-return comparison.

Run under scripts/run_capped.sh --mem 1.8G --.
"""

from __future__ import annotations

import json
import sys
import zlib
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import screen_lane  # noqa: E402

from open_composer.research.campaign_statistics import deflated_sharpe_probability  # noqa: E402

DATA_DIR = ROOT / "data" / "research" / "h20260929_20_news_nonews_drop_reversal"
ITER_DIR = ROOT / "reports" / "research" / "iterations" / "h20260929_20_news_nonews_drop_reversal"
SCREENS_DIR = ROOT / "reports" / "research" / "screens" / "h20260929_20_news_nonews_drop_reversal"

TEST_WINDOW = ("2024-01-08", "2026-09-17")
COST_BPS_BY_TIER = {1: 3.0, 2: 6.0, 3: 12.0}  # top-500 / 500-1000 / 1000-1500
BORROW_ANNUAL_PCT = 1.0
MAX_POSITIONS = 20
MAX_WEIGHT = 0.10
BIL = "BIL"
TRIAL_COUNT = 12  # full preregistered manifest size, per candidate-manifest.json
DSR_HAC_LAG = 21
SEED = 20260929

CANDIDATES = [
    {"id": f"DROP_NN_D{int(d * 100)}_H{h}", "leg": "no_news_long", "D": d, "h": h, "tier_max": 3}
    for d in (0.05, 0.08)
    for h in (1, 3, 5)
] + [
    {"id": f"DRIFT_NEWS_D{int(d * 100)}_H{h}", "leg": "news_short", "D": d, "h": h, "tier_max": 2}
    for d in (0.05, 0.08)
    for h in (1, 3, 5)
]
assert len(CANDIDATES) == TRIAL_COUNT


def _stable_hash(text: str) -> int:
    """Deterministic across processes/runs, unlike builtin `hash()` on str
    (randomized per-process by PYTHONHASHSEED) -- placebo seeds must be
    reproducible."""
    return zlib.crc32(text.encode())


def leg_events(events: pd.DataFrame, leg: str, D: float, tier_max: int) -> pd.DataFrame:
    sub = events[events["adj_ret"] <= -D]
    sub = sub[sub["tier"] <= tier_max]
    if leg == "no_news_long":
        sub = sub[~sub["news_flag"]]
    else:
        sub = sub[sub["news_flag"]]
    return sub.reset_index(drop=True)


def run_book(
    events: pd.DataFrame,
    trading_days: pd.DatetimeIndex,
    h: int,
    sign: float,
    borrow: bool,
    cost_multiplier: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Capacity-constrained (<=MAX_POSITIONS, each <=MAX_WEIGHT) calendar-time
    book. Largest-drop-first tie-break, no pyramiding per symbol (preregistered
    in candidate-manifest.json). Returns (weights, cost_bps_frame,
    borrow_frame, trades_df); weights has one extra BIL column carrying the
    1 - sum(other weights) remainder."""
    n = len(trading_days)
    pos_of_day = {d: i for i, d in enumerate(trading_days)}
    ev = events.copy()
    ev["signal_idx"] = ev["event_date"].map(pos_of_day)
    ev = ev.dropna(subset=["signal_idx"])
    ev["signal_idx"] = ev["signal_idx"].astype(int)
    ev["entry_idx"] = ev["signal_idx"] + 1
    ev["exit_idx"] = ev["entry_idx"] + h - 1
    ev = ev[(ev["entry_idx"] < n) & (ev["exit_idx"] < n)]

    entries_by_day = {day: grp for day, grp in ev.groupby("entry_idx")}
    symbols = sorted(ev["symbol"].unique())
    cols = [*symbols, BIL]
    weights = pd.DataFrame(0.0, index=trading_days, columns=cols)
    cost_bps_frame = pd.DataFrame(0.0, index=trading_days, columns=cols)
    borrow_frame = pd.DataFrame(0.0, index=trading_days, columns=cols)

    open_positions: dict[str, dict] = {}
    trades: list[dict] = []
    for day in range(n):
        open_positions = {s: v for s, v in open_positions.items() if v["exit_idx"] >= day}
        if day in entries_by_day:
            todays = entries_by_day[day]
            todays = todays[~todays["symbol"].isin(open_positions)]
            todays = todays.sort_values("adj_ret")  # most negative (largest drop) first
            capacity_left = MAX_POSITIONS - len(open_positions)
            accept = todays.iloc[: max(capacity_left, 0)]
            for _, row in accept.iterrows():
                sym = row["symbol"]
                open_positions[sym] = {
                    "exit_idx": int(row["exit_idx"]),
                    "tier": int(row["tier"]),
                    "entry_idx": int(row["entry_idx"]),
                }
                trades.append(
                    {
                        "symbol": sym,
                        "entry_idx": int(row["entry_idx"]),
                        "exit_idx": int(row["exit_idx"]),
                        "tier": int(row["tier"]),
                        "adj_ret_trigger": float(row["adj_ret"]),
                    }
                )
        n_open = len(open_positions)
        if n_open > 0:
            w_each = min(1.0 / n_open, MAX_WEIGHT)
            for sym, info in open_positions.items():
                weights.at[trading_days[day], sym] = sign * w_each
                tier_rate = COST_BPS_BY_TIER[info["tier"]] * cost_multiplier
                cost_bps_frame.at[trading_days[day], sym] = tier_rate
                if borrow:
                    borrow_frame.at[trading_days[day], sym] = BORROW_ANNUAL_PCT / 100.0 / 252.0
    risky_sum = weights[symbols].sum(axis=1) if symbols else pd.Series(0.0, index=trading_days)
    weights[BIL] = 1.0 - risky_sum
    trades_df = pd.DataFrame(trades)
    return weights, cost_bps_frame, borrow_frame, trades_df


def simulate_tiered(
    weights: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    cost_bps_frame: pd.DataFrame,
    borrow_frame: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    """Same close-to-close/next-open-fill P&L formula as
    `run_h20260922_05_salvage.simulate` (row i = weight effective from the
    open to the close of session i), generalized to a per-column, per-day
    cost-bps array (instead of one scalar) and an added borrow-cost term on
    held notional. BIL carries no spread cost (cash, not a traded position)."""
    cols = list(weights.columns)
    wb = weights.to_numpy(dtype=float)
    lo = leg_open[cols].to_numpy(dtype=float)
    lc = leg_close[cols].to_numpy(dtype=float)
    cost_arr = cost_bps_frame[cols].to_numpy(dtype=float)
    borrow_arr = borrow_frame[cols].to_numpy(dtype=float)
    n = len(wb)
    rets = np.zeros(n)
    turns = np.zeros(n)
    w_prev = np.zeros(wb.shape[1])
    for i in range(n):
        w = wb[i]
        gross = float(w_prev @ lo[i] + w @ lc[i])
        dw = np.abs(w - w_prev)
        cost = float((dw * cost_arr[i] / 10000.0).sum())
        borrow_cost = float((np.abs(w) * borrow_arr[i]).sum())
        rets[i] = gross - cost - borrow_cost
        turns[i] = float(dw.sum())
        w_prev = w
    return pd.Series(rets, index=weights.index), pd.Series(turns, index=weights.index)


def trade_economics(
    trades: pd.DataFrame, open_: pd.DataFrame, close: pd.DataFrame, sign: float, borrow: bool
) -> pd.DataFrame:
    if trades.empty:
        return trades.assign(gross_ret=[], net_ret=[], hold_days=[])
    out = trades.copy()
    entry_px = open_.to_numpy()
    close_px = close.to_numpy()
    col_idx = {c: i for i, c in enumerate(open_.columns)}
    gross = np.full(len(out), np.nan)
    for i, row in enumerate(out.itertuples()):
        ci = col_idx.get(row.symbol)
        if ci is None:
            continue
        p0 = entry_px[row.entry_idx, ci]
        p1 = close_px[row.exit_idx, ci]
        if not (np.isfinite(p0) and np.isfinite(p1)) or p0 <= 0:
            continue
        gross[i] = sign * (p1 / p0 - 1.0)
    out["gross_ret"] = gross
    out["hold_days"] = out["exit_idx"] - out["entry_idx"] + 1
    tier_bps = out["tier"].map(COST_BPS_BY_TIER)
    spread_cost = 2.0 * tier_bps / 10000.0  # entry + exit, one side each
    borrow_cost = (BORROW_ANNUAL_PCT / 100.0 / 252.0) * out["hold_days"] if borrow else 0.0
    out["net_ret"] = out["gross_ret"] - spread_cost - borrow_cost
    out["entry_date"] = out["entry_idx"].map(lambda i: open_.index[i])
    return out.dropna(subset=["gross_ret"]).reset_index(drop=True)


def clustered_mean_se(returns: np.ndarray, dates: np.ndarray) -> tuple[float, float, int]:
    """Cluster-robust (Liang-Zeger) mean and SE for a simple sample mean,
    clustered by entry date -- same-day trades share event/market risk."""
    n = len(returns)
    if n == 0:
        return float("nan"), float("nan"), 0
    mean = float(np.mean(returns))
    df = pd.DataFrame({"r": returns, "d": dates})
    cluster_sums = df.groupby("d")["r"].apply(lambda s: float((s - mean).sum()))
    variance = float((cluster_sums**2).sum()) / (n**2)
    se = float(np.sqrt(max(variance, 0.0)))
    return mean, se, n


def two_sample_cluster_t(
    a_returns: np.ndarray, a_dates: np.ndarray, b_returns: np.ndarray, b_dates: np.ndarray
) -> dict[str, float]:
    mean_a, se_a, n_a = clustered_mean_se(a_returns, a_dates)
    mean_b, se_b, n_b = clustered_mean_se(b_returns, b_dates)
    denom = float(np.sqrt(se_a**2 + se_b**2))
    t = float((mean_a - mean_b) / denom) if denom > 0 else float("nan")
    return {
        "mean_a": mean_a,
        "se_a": se_a,
        "n_a": n_a,
        "mean_b": mean_b,
        "se_b": se_b,
        "n_b": n_b,
        "t_stat": t,
    }


def shuffled_label_pseudo_events(
    events_all: pd.DataFrame, leg: str, D: float, tier_max: int, seed: int
) -> pd.DataFrame:
    """Pool of events (both news and no-news) qualifying at D/tier; shuffle
    the news_flag label within each calendar day (preserving that day's
    true/false counts), keep the pseudo subset matching `leg` (pseudo-no-news
    for the long leg, pseudo-news for the short leg) -- this must select the
    same label the real leg conditions on, or the placebo silently compares
    against the wrong group."""
    rng = np.random.default_rng(seed)
    sub = events_all[(events_all["adj_ret"] <= -D) & (events_all["tier"] <= tier_max)].copy()

    def shuffle_group(g: pd.DataFrame) -> pd.DataFrame:
        vals = g["news_flag"].to_numpy().copy()
        rng.shuffle(vals)
        g = g.copy()
        g["news_flag"] = vals
        return g

    shuffled = sub.groupby("event_date", group_keys=False).apply(shuffle_group)
    pseudo = (
        shuffled[shuffled["news_flag"]] if leg == "news_short" else shuffled[~shuffled["news_flag"]]
    )
    return pseudo.reset_index(drop=True)


def redated_pseudo_events(
    events_leg: pd.DataFrame, trading_days: pd.DatetimeIndex, test_mask: np.ndarray, seed: int
) -> pd.DataFrame:
    """Same stocks, each event moved to a random OTHER TEST-window trading
    date for that symbol (adj_ret_trigger and tier kept from the real event,
    only used for capacity tie-break/cost -- the point under test is whether
    the specific drop DATE matters, not a fresh random signal)."""
    rng = np.random.default_rng(seed)
    test_days = trading_days[test_mask]
    if len(test_days) == 0 or events_leg.empty:
        return events_leg.iloc[0:0].copy()
    out = events_leg.copy()
    replacement_idx = rng.integers(0, len(test_days), size=len(out))
    out["event_date"] = test_days[replacement_idx]
    return out.reset_index(drop=True)


def window_mask(index: pd.DatetimeIndex, window: tuple[str, str]) -> np.ndarray:
    a, b = window
    mask = (index >= a) & (index <= b)
    return mask.to_numpy() if hasattr(mask, "to_numpy") else np.asarray(mask)


def main() -> None:
    events = pd.read_parquet(DATA_DIR / "events.parquet")
    events["event_date"] = pd.to_datetime(events["event_date"])
    close = pd.read_parquet(DATA_DIR / "panel_close.parquet")
    open_ = pd.read_parquet(DATA_DIR / "panel_open.parquet")
    trading_days = close.index
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[BIL] / close[BIL].shift(1) - 1.0).fillna(0.0)
    test_mask_all = window_mask(trading_days, TEST_WINDOW)

    events_test = events[
        (events["event_date"] >= TEST_WINDOW[0]) & (events["event_date"] <= TEST_WINDOW[1])
    ]
    print(f"events in TEST window: {len(events_test)}")

    # S3 benchmark panel (separate universe, screen_lane's own frozen loader).
    close_s3, open_s3, leg_open_s3, leg_close_s3, rf_s3 = screen_lane.load_batch_panel([])
    s3_ret10, _s3_turn10 = screen_lane.s3_incumbent(
        close_s3, leg_open_s3, leg_close_s3, screen_lane.COST_BPS_PRIMARY
    )
    shy_ret_s3 = (close_s3[screen_lane.CASH] / close_s3[screen_lane.CASH].shift(1) - 1.0).fillna(
        0.0
    )

    results: dict[str, dict] = {}
    all_trades: dict[str, pd.DataFrame] = {}

    for cand in CANDIDATES:
        cid = cand["id"]
        sign = 1.0 if cand["leg"] == "no_news_long" else -1.0
        borrow = cand["leg"] == "news_short"
        ev_leg = leg_events(events_test, cand["leg"], cand["D"], cand["tier_max"])

        per_mult: dict[str, dict] = {}
        judged_ret = None
        judged_trades = None
        for mult_label, mult in (("cost1x", 1.0), ("cost2x", 2.0)):
            weights, cost_bps_frame, borrow_frame, trades = run_book(
                ev_leg, trading_days, cand["h"], sign, borrow, mult
            )
            ret, turn = simulate_tiered(weights, leg_open, leg_close, cost_bps_frame, borrow_frame)
            mask = test_mask_all
            m = base.metrics(ret.loc[mask], rf, turn.loc[mask])
            per_mult[mult_label] = {"metrics": asdict(m), "n_trades": int(len(trades))}
            if mult_label == "cost1x":
                judged_ret = ret
                judged_trades = trade_economics(trades, open_, close, sign, borrow)
                all_trades[cid] = judged_trades

        # --- S3 comparisons (cost1x series only) ---
        assert judged_ret is not None
        corr_stress = float("nan")  # STRESS window is data-infeasible for this mechanism
        corr_anchor = screen_lane.correlation_with_s3(judged_ret, s3_ret10, TEST_WINDOW)
        edge_anchor = screen_lane.diversifier_edge_for_offset(
            s3_ret10, judged_ret, shy_ret_s3, rf_s3, TEST_WINDOW
        )

        excess = (
            judged_ret.loc[test_mask_all]
            - rf.reindex(judged_ret.index).fillna(0.0).loc[test_mask_all]
        ).to_numpy()
        try:
            dsr = float(
                deflated_sharpe_probability(excess, trial_count=TRIAL_COUNT, hac_lag=DSR_HAC_LAG)
            )
        except ValueError as exc:
            dsr = None
            dsr_error = str(exc)
        else:
            dsr_error = None

        # --- trade-level stats (cost1x) ---
        assert judged_trades is not None
        if len(judged_trades) > 0:
            hit_rate = float((judged_trades["net_ret"] > 0).mean())
            avg_ret = float(judged_trades["net_ret"].mean())
            median_ret = float(judged_trades["net_ret"].median())
            worst = float(judged_trades["net_ret"].min())
            skew = float(judged_trades["net_ret"].skew())
            years = (pd.Timestamp(TEST_WINDOW[1]) - pd.Timestamp(TEST_WINDOW[0])).days / 365.25
            trades_per_year = float(len(judged_trades) / years) if years > 0 else float("nan")
            time_in_market = float((judged_ret.loc[test_mask_all] != 0).mean())
        else:
            hit_rate = avg_ret = median_ret = worst = skew = trades_per_year = time_in_market = (
                float("nan")
            )

        # --- placebo (i): shuffled news/no-news label ---
        shuffled = shuffled_label_pseudo_events(
            events_test,
            cand["leg"],
            cand["D"],
            cand["tier_max"],
            seed=SEED + _stable_hash(cid) % 1000,
        )
        _w, _c, _b, shuf_trades_raw = run_book(shuffled, trading_days, cand["h"], sign, borrow, 1.0)
        shuf_trades = trade_economics(shuf_trades_raw, open_, close, sign, borrow)
        placebo_shuffled = (
            two_sample_cluster_t(
                judged_trades["net_ret"].to_numpy(),
                judged_trades["entry_date"].to_numpy(),
                shuf_trades["net_ret"].to_numpy(),
                shuf_trades["entry_date"].to_numpy(),
            )
            if len(judged_trades) > 0
            else {"t_stat": float("nan")}
        )

        # --- placebo (ii): redated to a random TEST-window date ---
        redated = redated_pseudo_events(
            ev_leg, trading_days, test_mask_all, seed=SEED + 500 + _stable_hash(cid) % 1000
        )
        _w2, _c2, _b2, redated_trades_raw = run_book(
            redated, trading_days, cand["h"], sign, borrow, 1.0
        )
        redated_trades = trade_economics(redated_trades_raw, open_, close, sign, borrow)
        placebo_redated = (
            two_sample_cluster_t(
                judged_trades["net_ret"].to_numpy(),
                judged_trades["entry_date"].to_numpy(),
                redated_trades["net_ret"].to_numpy(),
                redated_trades["entry_date"].to_numpy(),
            )
            if len(judged_trades) > 0
            else {"t_stat": float("nan")}
        )

        results[cid] = {
            "leg": cand["leg"],
            "D_pct": int(cand["D"] * 100),
            "hold_sessions": cand["h"],
            "n_trades_test": int(len(judged_trades)),
            "n_events_qualifying": int(len(ev_leg)),
            "hit_rate": hit_rate,
            "avg_return_per_trade_net": avg_ret,
            "median_return_per_trade_net": median_ret,
            "worst_trade_net": worst,
            "skew": skew,
            "trades_per_year": trades_per_year,
            "time_in_market": time_in_market,
            "calendar_metrics_cost1x": per_mult["cost1x"]["metrics"],
            "calendar_metrics_cost2x": per_mult["cost2x"]["metrics"],
            "correlation_with_s3_test": corr_anchor,
            "correlation_with_s3_stress": corr_stress,
            "diversifier_edge_vs_s3_test": edge_anchor,
            "dsr_test": dsr,
            "dsr_error": dsr_error,
            "placebo_shuffled_label": placebo_shuffled,
            "placebo_redated": placebo_redated,
            "n_trades_cost2x_survivor": per_mult["cost2x"]["n_trades"] > 0
            and per_mult["cost2x"]["metrics"]["cagr"] is not None,
            "cagr_positive_cost2x": (
                per_mult["cost2x"]["metrics"]["cagr"] is not None
                and np.isfinite(per_mult["cost2x"]["metrics"]["cagr"])
                and per_mult["cost2x"]["metrics"]["cagr"] > 0
            ),
        }
        print(
            f"{cid}: trades={len(judged_trades)} hit_rate={hit_rate:.3f} "
            f"avg_ret={avg_ret:.4f} sharpe={per_mult['cost1x']['metrics']['sharpe']:.3f} "
            f"corr_s3={corr_anchor:.3f} edge={edge_anchor:.3f} dsr={dsr}"
        )

    SCREENS_DIR.mkdir(parents=True, exist_ok=True)
    ITER_DIR.mkdir(parents=True, exist_ok=True)
    results_path = ITER_DIR / "results.json"
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str) + "\n")
    print(f"wrote {results_path}")

    trades_dir = SCREENS_DIR / "trades"
    trades_dir.mkdir(parents=True, exist_ok=True)
    for cid, trades in all_trades.items():
        trades.to_csv(trades_dir / f"{cid}.csv", index=False)
    print(f"wrote per-candidate trade files to {trades_dir}")


if __name__ == "__main__":
    main()
