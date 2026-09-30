"""T-20260929-80 stage 2: 24 preregistered DAT / miner vs coin spread candidates.

Run only because the stage-1 IC gate (``scripts/run_h20260929_80_dat_ic.py``, results.json
``gate_checks``) continued. ``scripts/screen_lane.py`` cannot hold shorts, so this script
reuses the frozen lane / T-37 pieces unedited (panel loader, S3 incumbent, K2 machinery, tier
logic, DSR, signed simulator) and adds the spread state machines. Frozen in the iteration dossier
(``stage2-protocol-preregistration.md``) before any book return was computed.

Books are cash-financed overlays (SHY weight 0); reported Sharpe is the overlay's excess Sharpe
and the K2 sleeve is overlay + T-bill collateral return (same convention as T-37 / T-51).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260929_37_ls_short_unlocked as t37  # noqa: E402
import run_h20260929_80_dat_ic as ic  # noqa: E402
import screen_lane as lane  # noqa: E402

from open_composer.research.campaign_statistics import deflated_sharpe_probability  # noqa: E402

base = lane.base
salvage = lane.salvage

ITER_ID = ic.ITER_ID
OUT_PATH = ROOT / "reports/research/iterations" / ITER_ID / "screen-results.json"
WINDOWS = dict(ic.WINDOWS)  # anchor 2024-01-08..2026-09-17, stress 2020-08-11..2023-12-29
N_TRIALS = 24
N_PLACEBO_SEEDS = 40
PLACEBO_MAX_EXCEED = 0.10
Z_ENTRY, Z_EXIT, MAX_HOLD = 1.0, 0.25, 60
M_THRESHOLD = 0.10
BORROW_MAIN, BORROW_HIGH = 0.03, 0.15
SPOT_EXTRA_BPS = 15.0  # spot-leg 25 bp per side versus 10 bp ETF/stock (pre-ETF window only)
MIN_WINDOW_DAYS = 60
FLAT = {"flat10": 10.0, "flat20": 20.0}

SPOT_COLS = {"BTC": "BTCSPOT", "ETH": "ETHSPOT"}
ETF_COLS = {"BTC": "FBTC", "ETH": "ETHA"}


def candidate_grid() -> list[dict[str, Any]]:
    out = []
    for sig, spec in ic.SIGNALS.items():
        for pid in ic.PAIRS:
            for side in ("SYM", "SHORT"):
                out.append(
                    {
                        "id": f"{pid}_{sig}_{side}",
                        "pair": pid,
                        "signal": sig,
                        "family": spec["family"],
                        "side": side,
                    }
                )
    assert len(out) == 24
    return out


# ---------------------------------------------------------------------------
# panel
# ---------------------------------------------------------------------------


def build_panel(index: pd.DatetimeIndex):
    close, open_, report = ic.load_prices()
    spot_close, spot_open = ic.load_spot()
    stock_cols = sorted({*ic.MSTR, *ic.MINERS, *ic.ETH_TREASURY})
    keep = [*stock_cols, *ETF_COLS.values()]
    pc = close[keep].reindex(index)
    po = open_[keep].reindex(index)
    for coin, col in SPOT_COLS.items():
        sym = ic.COIN_SPOT[coin]
        pc[col] = spot_close[sym].reindex(index)
        po[col] = spot_open[sym].reindex(index)
    series = {
        pid: ic.build_pair(p, close, open_, spot_close, spot_open) for pid, p in ic.PAIRS.items()
    }
    series = {pid: {k: v.reindex(index) for k, v in d.items()} for pid, d in series.items()}
    return pc, po, series, report


# ---------------------------------------------------------------------------
# state machines and weights
# ---------------------------------------------------------------------------


def state_at_signal_dates(
    signal: np.ndarray, family: str, side: str, sig_rows: list[int]
) -> dict[int, int]:
    """Position state (-1 short DAT / long coin, +1 long DAT / short coin, 0 flat) chosen at the
    close of each signal row. Z: enter at |z| >= 1 against z, exit at |z| <= 0.25, on a sign
    cross or after 60 sessions; M: sign(R) whenever |R| >= 10%. Short-only never goes +1."""
    out: dict[int, int] = {}
    state, entry_row, entry_sign = 0, None, 0
    for i in sig_rows:
        v = signal[i]
        if not np.isfinite(v):
            state, entry_row = 0, None
            out[i] = 0
            continue
        if family == "M":
            want = int(np.sign(v)) if abs(v) >= M_THRESHOLD else 0
            if side == "SHORT" and want > 0:
                want = 0
            out[i] = want
            continue
        if state != 0:
            crossed = np.sign(v) != entry_sign and abs(v) > Z_EXIT
            if abs(v) <= Z_EXIT or crossed or (entry_row is not None and i - entry_row >= MAX_HOLD):
                state, entry_row = 0, None
        if state == 0:
            if v >= Z_ENTRY:
                state, entry_sign, entry_row = -1, 1, i
            elif v <= -Z_ENTRY and side == "SYM":
                state, entry_sign, entry_row = 1, -1, i
        out[i] = state
    return out


class Book:
    def __init__(self, pc: pd.DataFrame, po: pd.DataFrame, series: dict, index: pd.DatetimeIndex):
        self.cols = list(pc.columns)
        self.ix = {c: i for i, c in enumerate(self.cols)}
        self.index = index
        self.n = len(index)
        self.valid_c = pc.notna().to_numpy()
        self.valid_o = po.notna().to_numpy()
        self.series = series
        self.etf_start = {c: pd.Timestamp(ic.COIN_ETF_START[c]) for c in ic.COIN_ETF_START}

    def coin_col(self, coin: str, row: int) -> int:
        if self.index[row] >= self.etf_start[coin]:
            return self.ix[ETF_COLS[coin]]
        return self.ix[SPOT_COLS[coin]]

    def vector(self, pid: str, state: int, refresh_row: int) -> np.ndarray:
        """Target weight vector effective at the open of `refresh_row` from the signal close of
        refresh_row - 1 (hedge ratio and membership known then)."""
        w = np.zeros(len(self.cols))
        if state == 0 or refresh_row < 1:
            return w
        pair = ic.PAIRS[pid]
        beta = self.series[pid]["beta"].iloc[refresh_row - 1]
        if not np.isfinite(beta):
            return w
        members = [
            self.ix[m]
            for m in pair["members"]
            if m in self.ix
            and self.valid_c[refresh_row - 1, self.ix[m]]
            and self.valid_o[refresh_row, self.ix[m]]
        ]
        if pair["start"] is not None and self.index[refresh_row] < pd.Timestamp(pair["start"]):
            members = []
        cc = self.coin_col(pair["coin"], refresh_row)
        if not members or not (self.valid_c[refresh_row - 1, cc] and self.valid_o[refresh_row, cc]):
            return w
        w_dat, w_coin = 1.0 / (1.0 + beta), beta / (1.0 + beta)
        for m in members:
            w[m] = state * w_dat / len(members)
        w[cc] = -state * w_coin
        return w

    def state_eff(self, cand: dict[str, Any], offset: int) -> tuple[np.ndarray, list[int]]:
        pid = cand["pair"]
        sig = self.series[pid][cand["signal"]].to_numpy()
        pos = {d: i for i, d in enumerate(self.index)}
        sig_dates = lane.signal_dates(self.index, "W", offset)
        rows = [pos[d] for d in sig_dates]
        chosen = state_at_signal_dates(sig, cand["family"], cand["side"], rows)
        eff = np.zeros(self.n, dtype=int)
        refresh: list[int] = []
        current = 0
        change = {i + 1: s for i, s in chosen.items() if i + 1 < self.n}
        for r in range(self.n):
            if r in change:
                current = change[r]
                refresh.append(r)
            eff[r] = current
        return eff, refresh

    def weights(self, cand: dict[str, Any], eff: np.ndarray, refresh: list[int]) -> np.ndarray:
        w = np.zeros((self.n, len(self.cols)))
        rows = set(refresh) | {r for r in range(1, self.n) if eff[r] != eff[r - 1]}
        cur = np.zeros(len(self.cols))
        for r in range(self.n):
            if r in rows:
                cur = self.vector(cand["pair"], int(eff[r]), r)
            w[r] = cur
        return w


# ---------------------------------------------------------------------------
# simulation
# ---------------------------------------------------------------------------


def cost_fracs(cols: list[str], index: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    out = {}
    for name, bps in FLAT.items():
        m = np.full((len(index), len(cols)), bps / 1e4)
        for c in SPOT_COLS.values():
            m[:, cols.index(c)] = (bps + SPOT_EXTRA_BPS) / 1e4
        out[name] = m
    return out


def run_sim(
    w: np.ndarray, lo: np.ndarray, lc: np.ndarray, costs: dict, index
) -> dict[str, pd.Series]:
    rate = np.full_like(w, BORROW_MAIN)
    s = t37.simulate_signed(w, lo, lc, costs, rate)
    g, b3 = s["gross"], s["borrow"]
    out = {
        "ret_10_after": g - s["cost"]["flat10"] - b3,
        "ret_20_after": g - s["cost"]["flat20"] - b3,
        "ret_10_borrow15": g - s["cost"]["flat10"] - b3 * (BORROW_HIGH / BORROW_MAIN),
        "ret_gross": g,
        "turn": s["turn"],
        "borrow": b3,
    }
    return {k: pd.Series(v, index=index) for k, v in out.items()}


def first_active(w: np.ndarray, index) -> pd.Timestamp:
    return t37.first_active(w, index)


def wstats(v: dict[str, pd.Series], key: str, window, first_valid) -> dict[str, float]:
    start = lane.window_actual_start(window[0], first_valid)
    end = pd.Timestamp(window[1])
    if start > end:
        return {"days": 0, "cagr": np.nan, "vol": np.nan, "sharpe": np.nan, "max_dd": np.nan}
    r = v[key]
    mask = (r.index >= start) & (r.index <= end)
    if int(mask.sum()) < MIN_WINDOW_DAYS:
        return {
            "days": int(mask.sum()),
            "cagr": np.nan,
            "vol": np.nan,
            "sharpe": np.nan,
            "max_dd": np.nan,
        }
    return t37.window_stats(r, v["turn"], v["borrow"], window, first_valid)


def med(x: list[float]) -> float:
    a = np.array(x, dtype=float)
    return float(np.nanmedian(a)) if np.isfinite(a).any() else float("nan")


def evaluate(book: Book, lo, lc, costs, cand, rf, shy_ret, s3_ret10, cand_ix) -> dict[str, Any]:
    index = book.index
    offsets = list(range(5))
    effs = {o: book.state_eff(cand, o) for o in offsets}
    weights = {o: book.weights(cand, *effs[o]) for o in offsets}
    first_valid = max(first_active(w, index) for w in weights.values())
    sims = {o: run_sim(weights[o], lo, lc, costs, index) for o in offsets}
    out: dict[str, Any] = {"id": cand["id"], **{k: cand[k] for k in ("pair", "signal", "side")}}
    out["first_valid_signal_effective"] = str(first_valid.date())
    summary: dict[str, Any] = {}
    for wname, window in WINDOWS.items():
        rows = {
            k: [wstats(sims[o], k, window, first_valid) for o in offsets]
            for k in ("ret_10_after", "ret_20_after", "ret_10_borrow15", "ret_gross")
        }
        a = rows["ret_10_after"]
        summary[wname] = {
            "median_sharpe_10bp_borrow3": med([r["sharpe"] for r in a]),
            "min_sharpe_10bp_borrow3": float(np.nanmin([r["sharpe"] for r in a]))
            if np.isfinite([r["sharpe"] for r in a]).any()
            else float("nan"),
            "max_sharpe_10bp_borrow3": float(np.nanmax([r["sharpe"] for r in a]))
            if np.isfinite([r["sharpe"] for r in a]).any()
            else float("nan"),
            "median_sharpe_20bp_borrow3": med([r["sharpe"] for r in rows["ret_20_after"]]),
            "median_sharpe_10bp_borrow15": med([r["sharpe"] for r in rows["ret_10_borrow15"]]),
            "median_sharpe_gross": med([r["sharpe"] for r in rows["ret_gross"]]),
            "median_cagr_10bp_borrow3": med([r["cagr"] for r in a]),
            "median_cagr_20bp_borrow3": med([r["cagr"] for r in rows["ret_20_after"]]),
            "median_cagr_10bp_borrow15": med([r["cagr"] for r in rows["ret_10_borrow15"]]),
            "median_vol": med([r["vol"] for r in a]),
            "median_max_dd": med([r["max_dd"] for r in a]),
            "days": a[0]["days"],
        }
    out["windows"] = summary
    # K2 edges (sleeve = overlay + T-bill collateral)
    edges = {}
    for wname, window in WINDOWS.items():
        vals = []
        for o in offsets:
            n_act = wstats(sims[o], "ret_10_after", window, first_valid)["days"]
            if n_act < MIN_WINDOW_DAYS:
                vals.append(np.nan)
                continue
            vals.append(
                lane.diversifier_edge_for_offset(
                    s3_ret10,
                    sims[o]["ret_10_after"] + rf.reindex(index).fillna(0.0),
                    shy_ret,
                    rf,
                    window,
                )
            )
        edges[wname] = {"median": med(vals), "by_offset": [float(v) for v in vals]}
    out["k2_edge_vs_s3"] = edges
    # judged offset + DSR (anchor)
    anchor_vals = [
        wstats(sims[o], "ret_10_after", WINDOWS["anchor"], first_valid)["sharpe"] for o in offsets
    ]
    order = sorted(range(5), key=lambda k: np.nan_to_num(anchor_vals[k], nan=-9.0))
    judged = offsets[order[2]]
    a_start = lane.window_actual_start(WINDOWS["anchor"][0], first_valid)
    jr = sims[judged]["ret_10_after"]
    mask = (jr.index >= a_start) & (jr.index <= pd.Timestamp(WINDOWS["anchor"][1]))
    try:
        dsr = float(
            deflated_sharpe_probability(
                jr.loc[mask].to_numpy(), trial_count=N_TRIALS, hac_lag=lane.DSR_HAC_LAG
            )
        )
    except ValueError:
        dsr = None
    out["judged_offset"] = judged
    out["dsr_anchor_24_trials"] = dsr
    # random-entry-date placebo: circular shift of the state path inside the active span
    span = max(0, int(np.argmax(np.abs(weights[0]).sum(axis=1) > 0)))
    plc_anchor, plc_stress = [], []
    for seed in range(N_PLACEBO_SEEDS):
        rng = np.random.default_rng(seed * 1000 + cand_ix)
        shift = int(rng.integers(MAX_HOLD, max(MAX_HOLD + 1, book.n - span - MAX_HOLD)))
        per = {}
        for o in offsets:
            eff, refresh = effs[o]
            eff2 = eff.copy()
            eff2[span:] = np.roll(eff[span:], shift)
            w2 = book.weights(cand, eff2, refresh)
            per[o] = run_sim(w2, lo, lc, costs, index)
        plc_anchor.append(
            med(
                [
                    wstats(per[o], "ret_10_after", WINDOWS["anchor"], first_valid)["sharpe"]
                    for o in offsets
                ]
            )
        )
        plc_stress.append(
            med(
                [
                    wstats(per[o], "ret_10_after", WINDOWS["stress"], first_valid)["sharpe"]
                    for o in offsets
                ]
            )
        )
    cand_a = summary["anchor"]["median_sharpe_10bp_borrow3"]
    pa = np.array(plc_anchor, dtype=float)
    exceed = float(np.mean(pa >= cand_a)) if np.isfinite(cand_a) else float("nan")
    out["random_entry_placebo"] = {
        "seeds": N_PLACEBO_SEEDS,
        "anchor_median_sharpes": [float(x) for x in pa],
        "stress_median_sharpes": [float(x) for x in plc_stress],
        "anchor_max": float(np.nanmax(pa)) if np.isfinite(pa).any() else float("nan"),
        "fraction_of_placebos_at_or_above_candidate": exceed,
        "passes_le_10pct": bool(np.isfinite(exceed) and exceed <= PLACEBO_MAX_EXCEED),
    }
    tier = t37.tier_from(
        summary["anchor"]["median_sharpe_10bp_borrow3"],
        summary["stress"]["median_sharpe_10bp_borrow3"]
        if np.isfinite(summary["stress"]["median_sharpe_10bp_borrow3"])
        else -9.0,
        summary["anchor"]["median_cagr_20bp_borrow3"],
        summary["stress"]["median_cagr_20bp_borrow3"]
        if np.isfinite(summary["stress"]["median_cagr_20bp_borrow3"])
        else -9.0,
        edges["anchor"]["median"],
        edges["stress"]["median"] if np.isfinite(edges["stress"]["median"]) else -9.0,
        out["random_entry_placebo"]["anchor_max"],
    )
    out.update(tier)
    out["stress_window_available"] = bool(
        np.isfinite(summary["stress"]["median_sharpe_10bp_borrow3"])
    )
    out["borrow15_anchor_positive"] = bool(summary["anchor"]["median_cagr_10bp_borrow15"] > 0)
    out["borrow15_anchor_sharpe_positive"] = bool(
        summary["anchor"]["median_sharpe_10bp_borrow15"] > 0
    )
    out["share_of_days_with_position"] = float(
        np.mean([np.mean(np.abs(w).sum(axis=1) > 0) for w in weights.values()])
    )
    return out


def main() -> int:
    t0 = datetime.now(UTC)
    base.WARMUP_START = lane.PANEL_START
    lane_close, lane_open = base.load_panel(sorted(set(salvage.symbols()) | {lane.CASH, lane.RF}))
    index = lane_close.index
    leg_open_l, leg_close_l = salvage.legs(lane_close, lane_open)
    rf = (lane_close[lane.RF] / lane_close[lane.RF].shift(1) - 1.0).fillna(0.0)
    shy_ret = (lane_close[lane.CASH] / lane_close[lane.CASH].shift(1) - 1.0).fillna(0.0)
    s3_ret10, _ = lane.s3_incumbent(lane_close, leg_open_l, leg_close_l, lane.COST_BPS_PRIMARY)
    pc, po, series, report = build_panel(index)
    lo_df, lc_df = salvage.legs(pc, po)
    lo, lc = lo_df.to_numpy(), lc_df.to_numpy()
    book = Book(pc, po, series, index)
    costs = cost_fracs(book.cols, index)
    rows = []
    for ix, cand in enumerate(candidate_grid()):
        rows.append(evaluate(book, lo, lc, costs, cand, rf, shy_ret, s3_ret10, ix))
        r = rows[-1]
        a, s = r["windows"]["anchor"], r["windows"]["stress"]
        print(
            f"{cand['id']}: anchor {a['median_sharpe_10bp_borrow3']:.3f} stress "
            f"{s['median_sharpe_10bp_borrow3']:.3f} edges "
            f"{r['k2_edge_vs_s3']['anchor']['median']:.3f}/"
            f"{r['k2_edge_vs_s3']['stress']['median']:.3f} plc_exceed "
            f"{r['random_entry_placebo']['fraction_of_placebos_at_or_above_candidate']:.2f} "
            f"tier {r['tier']}",
            flush=True,
        )
    payload = {
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "runtime_seconds": (datetime.now(UTC) - t0).total_seconds(),
        "contract": {
            "windows": WINDOWS,
            "k1_anchor": t37.K1_ANCHOR,
            "k1_stress": t37.K1_STRESS,
            "k2_edge_min": t37.K2_EDGE_MIN,
            "judged": (
                "median over 5 weekly rebalance offsets, 10 bp per side per leg "
                "(spot legs +15 bp), "
                "3%/yr borrow on every short weight"
            ),
            "n_trials_dsr": N_TRIALS,
            "placebo": "40 circular shifts of the position-state path; exceeded by <= 10%",
            "borrow_sensitivity": BORROW_HIGH,
        },
        "data_notes": {"discards": report["discards"]},
        "candidates": rows,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2, default=float) + "\n", encoding="utf-8")
    print("wrote", OUT_PATH, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
