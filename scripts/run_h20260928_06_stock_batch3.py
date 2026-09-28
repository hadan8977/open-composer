"""H-20260928-06: judge ten testable-now stock-level registry directions (batch
3) against the owner's 2026-09-28 keep rule (K1 Sharpe vs S3, K2 diversifier
edge vs a vol-matched k*S3+(1-k)*SHY control).

Dossier: ``reports/research/iterations/h20260928_06_registry_stock_batch3/``
(``direction-review.json`` + ``candidate-manifest.json`` frozen before this
script computed any return). This module adds no new simulator: cross-sectional
and event candidates reuse ``open_composer.research.signal_card`` (``load_market``,
``load_signal``, ``topk_cohorts``, ``hold``, ``book_returns``) unchanged; the two
single-index ETF-timing families reuse ``run_h20260918_05_recent_menu``'s
(``base``) ``weights_from_selection``/``portfolio_returns``/``metrics`` unchanged;
K2/correlation/DSR reuse ``scripts/screen_lane.py``'s ``s3_incumbent``,
``diversifier_edge_for_offset``, ``correlation_with_s3`` and
``open_composer.research.campaign_statistics.deflated_sharpe_probability``.

Candidates (see ``candidate-manifest.json`` for the full contract):

    momentum_concentrated_k37   momentum_252_21 top-37, monthly (h=21)
    skew_52wk_high_k95          dist_from_252d_high top-95, monthly (h=21)
    vam_momentum_k50            momentum_252_21/vol_63 top-50, monthly (h=21)
                                 (AEGIS step 1 only, disclosed partial proxy)
    a13d_item4_h6/h12/h24       Schedule 13D item4 new filings, calendar-time
                                 hold 126/252/504 sessions
    monday_afternoon_spy/qqq    Monday close-vs-open direction, hold the week
    overnight_only_spy/qqq      static long-overnight/flat-intraday, 2x cost
                                 (explicit daily round trip)

Overlapping daily cohorts and the calendar-time event books are date-neutral by
construction (one path, no offset sweep); the two ETF-timing families are
static/one-version rules with no periodic-rebalance-date ambiguity either.
Windows, cost and Sharpe conventions are ``scripts/screen_lane.py``'s
``WINDOWS``/``COST_BPS_PRIMARY``/``COST_BPS_STRESS`` and
``run_h20260918_05_recent_menu``'s ``metrics`` (RF-excess Sharpe, BIL),
unchanged.

    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/run_h20260928_06_stock_batch3.py
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import screen_lane  # noqa: E402

from open_composer.research.campaign_statistics import deflated_sharpe_probability  # noqa: E402
from open_composer.research.signal_card import (  # noqa: E402
    Market,
    book_returns,
    hold,
    load_market,
    load_signal,
    topk_cohorts,
)

ITER_ID = "h20260928_06_registry_stock_batch3"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
MANIFEST_PATH = OUT_DIR / "candidate-manifest.json"
CHECKPOINT_PATH = OUT_DIR / "results.json"

TOP_N = 500
COST_BPS_PRIMARY = screen_lane.COST_BPS_PRIMARY  # 10.0
COST_BPS_STRESS = screen_lane.COST_BPS_STRESS  # 20.0
WINDOWS = screen_lane.WINDOWS
CONTAMINATED = screen_lane.CONTAMINATED_WINDOWS
CALENDAR_2022 = screen_lane.CALENDAR_2022
DSR_HAC_LAG = screen_lane.DSR_HAC_LAG
TRIAL_COUNT = 10  # ten preregistered candidates in this batch

K1_SHARPE_ANCHOR_MIN = 1.19
K1_SHARPE_STRESS_MIN = 0.65
K2_EDGE_MIN = 0.05

FILINGS_13D = ROOT / "data" / "features" / "sec_13d" / "filings.parquet"

EXPECTED_CANDIDATE_IDS = [
    "momentum_concentrated_k37",
    "skew_52wk_high_k95",
    "vam_momentum_k50",
    "a13d_item4_h6",
    "a13d_item4_h12",
    "a13d_item4_h24",
    "monday_afternoon_spy",
    "monday_afternoon_qqq",
    "overnight_only_spy",
    "overnight_only_qqq",
]


def _log(msg: str) -> None:
    print(f"[stock_batch3] {msg}", flush=True)


def guard_manifest() -> dict:
    """Refuse to run a candidate that is not in the frozen manifest (or vice
    versa): the manifest and this script's candidate set must match exactly."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_ids = [c["candidate_id"] for c in manifest["candidates"]]
    if manifest_ids != EXPECTED_CANDIDATE_IDS:
        raise ValueError(
            f"candidate-manifest.json ids {manifest_ids} do not match this "
            f"script's EXPECTED_CANDIDATE_IDS {EXPECTED_CANDIDATE_IDS}"
        )
    return manifest


def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    return {"iter_id": ITER_ID, "candidates": {}}


def save_checkpoint(state: dict) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(state, indent=1, default=_json_default) + "\n")


def _json_default(o: object) -> object:
    if isinstance(o, (np.generic,)):
        return o.item()
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    raise TypeError(type(o))


# ------------------------------------------------------------ stock universe


def load_stock_market() -> Market:
    _log("loading stock market top_n=500 ...")
    return load_market(top_n=TOP_N, memory_limit="1200MB")


def cross_sectional_signals(market: Market) -> dict[str, np.ndarray]:
    mom = load_signal(market, source="data/features/daily_broad", column="momentum_252_21", lag=0)
    dist = load_signal(
        market, source="data/features/daily_broad", column="dist_from_252d_high", lag=0
    )
    vol63 = load_signal(market, source="data/features/daily_broad", column="vol_63", lag=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        vam = np.where(np.isfinite(mom) & np.isfinite(vol63) & (vol63 > 0), mom / vol63, np.nan)
    return {
        "momentum_252_21": mom,
        "dist_from_252d_high": dist,
        "vam_momentum_vol63": vam.astype(np.float32),
    }


def load_13d_item4_signal(market: Market) -> np.ndarray:
    sql = (
        "SELECT issuer_symbol AS symbol, visible_session AS trade_date, 1.0 AS value "
        f"FROM read_parquet('{FILINGS_13D.as_posix()}') "
        "WHERE item4_present = true AND is_new_13d = true"
    )
    return load_signal(market, sql=sql, lag=0)


# ------------------------------------------------------------------- windows


def window_metrics(ret: pd.Series, turnover: pd.Series, rf: pd.Series) -> dict[str, dict]:
    out = {}
    for wname, (a, b) in WINDOWS.items():
        mask = (ret.index >= a) & (ret.index <= b)
        m = base.metrics(ret.loc[mask], rf, turnover.loc[mask])
        out[wname] = asdict(m)
        out[wname]["contaminated"] = wname in CONTAMINATED
    return out


def k1_verdict(net10_by_window: dict, net20_by_window: dict) -> dict:
    sharpe_anchor = net10_by_window["anchor"]["sharpe"]
    sharpe_stress = net10_by_window["stress"]["sharpe"]
    cagr_anchor_20 = net20_by_window["anchor"]["cagr"]
    cagr_stress_20 = net20_by_window["stress"]["cagr"]

    def _ok(x: float | None) -> bool:
        return x is not None and np.isfinite(x)

    sharpe_pass = (
        _ok(sharpe_anchor)
        and _ok(sharpe_stress)
        and sharpe_anchor >= K1_SHARPE_ANCHOR_MIN
        and sharpe_stress >= K1_SHARPE_STRESS_MIN
    )
    cagr_pass = (
        _ok(cagr_anchor_20) and _ok(cagr_stress_20) and cagr_anchor_20 > 0 and cagr_stress_20 > 0
    )
    return {
        "sharpe_anchor_10bp": sharpe_anchor,
        "sharpe_stress_10bp": sharpe_stress,
        "cagr_anchor_20bp": cagr_anchor_20,
        "cagr_stress_20bp": cagr_stress_20,
        "sharpe_bar_pass": bool(sharpe_pass),
        "cagr_bar_pass": bool(cagr_pass),
        "pass": bool(sharpe_pass and cagr_pass),
    }


def k2_verdict(ret10: pd.Series, s3_ret10: pd.Series, shy_ret: pd.Series, rf: pd.Series) -> dict:
    edges = {}
    for wname in ("anchor", "stress"):
        window = WINDOWS[wname]
        edges[wname] = screen_lane.diversifier_edge_for_offset(s3_ret10, ret10, shy_ret, rf, window)
    passed = all(edges[w] >= K2_EDGE_MIN for w in ("anchor", "stress"))
    return {"edge_anchor": edges["anchor"], "edge_stress": edges["stress"], "pass": bool(passed)}


def correlations(ret10: pd.Series, s3_ret10: pd.Series) -> dict:
    return {
        "stress": screen_lane.correlation_with_s3(ret10, s3_ret10, WINDOWS["stress"]),
        "anchor": screen_lane.correlation_with_s3(ret10, s3_ret10, WINDOWS["anchor"]),
        "2022": screen_lane.correlation_with_s3(ret10, s3_ret10, CALENDAR_2022),
    }


def dsr_anchor(ret10: pd.Series, rf: pd.Series) -> float | None:
    a, b = WINDOWS["anchor"]
    mask = (ret10.index >= a) & (ret10.index <= b)
    excess = (ret10.loc[mask] - rf.reindex(ret10.index).fillna(0.0).loc[mask]).dropna().to_numpy()
    try:
        return float(
            deflated_sharpe_probability(excess, trial_count=TRIAL_COUNT, hac_lag=DSR_HAC_LAG)
        )
    except ValueError:
        return None


def evaluate_series(
    candidate_id: str,
    ret10: pd.Series,
    turn10: pd.Series,
    ret20: pd.Series,
    turn20: pd.Series,
    rf: pd.Series,
    s3_ret10: pd.Series,
    shy_ret: pd.Series,
) -> dict:
    net10 = window_metrics(ret10, turn10, rf)
    net20 = window_metrics(ret20, turn20, rf)
    k1 = k1_verdict(net10, net20)
    k2 = k2_verdict(ret10, s3_ret10, shy_ret, rf)
    corr = correlations(ret10, s3_ret10)
    dsr = dsr_anchor(ret10, rf)
    tier = []
    if k1["pass"]:
        tier.append("K1")
    if k2["pass"]:
        tier.append("K2")
    return {
        "candidate_id": candidate_id,
        "n_offsets": 1,
        "date_neutral_by_construction": True,
        "net10": net10,
        "net20": net20,
        "k1": k1,
        "k2": k2,
        "correlation_with_s3": corr,
        "dsr_anchor": dsr,
        "kept": bool(tier),
        "tier": "+".join(tier) if tier else "none",
    }


# ---------------------------------------------------------- ETF-timing legs


def monday_signal_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    return [d for d in index if d.weekday() == 0]


def monday_afternoon_returns(
    close: pd.DataFrame, open_: pd.DataFrame, asset: str, cost_bps: float
) -> tuple[pd.Series, pd.Series]:
    cash = base.CASH
    cols = [asset, cash]
    mondays = monday_signal_dates(close.index)
    picks: dict[pd.Timestamp, list[str]] = {}
    for d in mondays:
        o = open_.at[d, asset] if d in open_.index else np.nan
        c = close.at[d, asset] if d in close.index else np.nan
        picks[d] = [asset] if (pd.notna(o) and pd.notna(c) and c > o) else []
    weights = base.weights_from_selection(close.index, mondays, picks, cols)
    ret = base.portfolio_returns(weights, close[cols], open_[cols], cost_bps)
    w_prev = weights.shift(1).fillna(0.0)
    turnover = (weights - w_prev).abs().sum(axis=1)
    return ret, turnover


def overnight_only_returns(
    close: pd.DataFrame, open_: pd.DataFrame, asset: str, cost_bps: float
) -> tuple[pd.Series, pd.Series]:
    """Static policy: long from close(t-1) to open(t) (overnight), flat open(t)
    to close(t) (intraday). Scored as a literal daily round trip -- 2x the
    per-side cost every session, since holding only the overnight session in
    cash equities means selling at the close and buying back at the open."""
    o = open_[asset]
    prev_c = close[asset].shift(1)
    overnight = (o / prev_c - 1.0).fillna(0.0)
    turnover = pd.Series(2.0, index=overnight.index)
    ret = overnight - turnover * cost_bps / 1e4
    return ret, turnover


# --------------------------------------------------------------------- main


def run() -> int:
    t0 = time.monotonic()
    manifest = guard_manifest()
    state = load_checkpoint()
    done = state["candidates"]

    need_stock = any(
        cid not in done
        for cid in ("momentum_concentrated_k37", "skew_52wk_high_k95", "vam_momentum_k50")
    ) or any(cid not in done for cid in ("a13d_item4_h6", "a13d_item4_h12", "a13d_item4_h24"))
    need_etf = any(
        cid not in done
        for cid in (
            "monday_afternoon_spy",
            "monday_afternoon_qqq",
            "overnight_only_spy",
            "overnight_only_qqq",
        )
    )

    if need_etf:
        _log("loading ETF panel (S3 universe + SHY/BIL/SPY/QQQ) ...")
        base.WARMUP_START = screen_lane.PANEL_START
        etf_symbols = sorted(set(salvage.symbols()) | {base.CASH, base.RF, "SPY", "QQQ"})
        close, open_ = base.load_panel(etf_symbols)
        leg_open, leg_close = salvage.legs(close, open_)
        rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
        shy_ret = (close[base.CASH] / close[base.CASH].shift(1) - 1.0).fillna(0.0)
        s3_ret10, _s3_turn10 = screen_lane.s3_incumbent(
            close, leg_open, leg_close, COST_BPS_PRIMARY
        )

        for asset in ("SPY", "QQQ"):
            cid = f"monday_afternoon_{asset.lower()}"
            if cid in done:
                continue
            ret10, turn10 = monday_afternoon_returns(close, open_, asset, COST_BPS_PRIMARY)
            ret20, turn20 = monday_afternoon_returns(close, open_, asset, COST_BPS_STRESS)
            done[cid] = evaluate_series(cid, ret10, turn10, ret20, turn20, rf, s3_ret10, shy_ret)
            save_checkpoint(state)
            _log(f"{cid} done: tier={done[cid]['tier']}")

        for asset in ("SPY", "QQQ"):
            cid = f"overnight_only_{asset.lower()}"
            if cid in done:
                continue
            ret10, turn10 = overnight_only_returns(close, open_, asset, COST_BPS_PRIMARY)
            ret20, turn20 = overnight_only_returns(close, open_, asset, COST_BPS_STRESS)
            done[cid] = evaluate_series(cid, ret10, turn10, ret20, turn20, rf, s3_ret10, shy_ret)
            save_checkpoint(state)
            _log(f"{cid} done: tier={done[cid]['tier']}")
    else:
        # Still needed for cross-sectional/event K2, correlation, DSR below.
        base.WARMUP_START = screen_lane.PANEL_START
        etf_symbols = sorted(set(salvage.symbols()) | {base.CASH, base.RF, "SPY", "QQQ"})
        close, open_ = base.load_panel(etf_symbols)
        leg_open, leg_close = salvage.legs(close, open_)
        rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
        shy_ret = (close[base.CASH] / close[base.CASH].shift(1) - 1.0).fillna(0.0)
        s3_ret10, _s3_turn10 = screen_lane.s3_incumbent(
            close, leg_open, leg_close, COST_BPS_PRIMARY
        )

    if need_stock:
        market = load_stock_market()
        ret = market.next_open_returns()
        member = market.member((1, TOP_N))
        idx = market.dates

        sigs = cross_sectional_signals(market)
        topk_specs = {
            "momentum_concentrated_k37": ("momentum_252_21", 37, 21),
            "skew_52wk_high_k95": ("dist_from_252d_high", 95, 21),
            "vam_momentum_k50": ("vam_momentum_vol63", 50, 21),
        }
        for cid, (sig_name, k, h) in topk_specs.items():
            if cid in done:
                continue
            cohorts = topk_cohorts(sigs[sig_name], member, k)
            held = hold(cohorts, h)
            net10, turn10 = book_returns(held, ret, COST_BPS_PRIMARY)
            net20, turn20 = book_returns(held, ret, COST_BPS_STRESS)
            ret10 = pd.Series(net10, index=idx)
            turn10_s = pd.Series(turn10, index=idx)
            ret20 = pd.Series(net20, index=idx)
            turn20_s = pd.Series(turn20, index=idx)
            done[cid] = evaluate_series(
                cid, ret10, turn10_s, ret20, turn20_s, rf, s3_ret10, shy_ret
            )
            save_checkpoint(state)
            _log(f"{cid} done: tier={done[cid]['tier']}")

        event_specs = {
            "a13d_item4_h6": 126,
            "a13d_item4_h12": 252,
            "a13d_item4_h24": 504,
        }
        if any(cid not in done for cid in event_specs):
            signal_13d = load_13d_item4_signal(market)
            events = member & np.isfinite(signal_13d)
        for cid, h in event_specs.items():
            if cid in done:
                continue
            held = hold(events.astype(np.float32), h, normalize=True)
            net10, turn10 = book_returns(held, ret, COST_BPS_PRIMARY)
            net20, turn20 = book_returns(held, ret, COST_BPS_STRESS)
            ret10 = pd.Series(net10, index=idx)
            turn10_s = pd.Series(turn10, index=idx)
            ret20 = pd.Series(net20, index=idx)
            turn20_s = pd.Series(turn20, index=idx)
            done[cid] = evaluate_series(
                cid, ret10, turn10_s, ret20, turn20_s, rf, s3_ret10, shy_ret
            )
            save_checkpoint(state)
            _log(f"{cid} done: tier={done[cid]['tier']}")

    state["candidates"] = {cid: done[cid] for cid in EXPECTED_CANDIDATE_IDS if cid in done}
    state["generated_at"] = pd.Timestamp.utcnow().isoformat()
    state["windows"] = {k: list(v) for k, v in WINDOWS.items()}
    state["cost_bps_primary"] = COST_BPS_PRIMARY
    state["cost_bps_stress"] = COST_BPS_STRESS
    state["keep_rule"] = manifest["keep_rule"]
    save_checkpoint(state)
    write_report(state)
    _log(f"all done in {time.monotonic() - t0:.0f}s")
    return 0


def write_report(state: dict) -> None:
    lines = [
        f"# {ITER_ID}",
        "",
        "K1: Sharpe(10bp) >= 1.19 anchor / >= 0.65 stress AND CAGR(20bp) > 0 both windows.",
        "K2: diversifier edge (S3+candidate vs vol-matched k*S3+(1-k)*SHY) "
        ">= 0.05 Sharpe both windows.",
        "",
        "| candidate | anchor Sharpe(10bp) | stress Sharpe(10bp) | edge anchor | edge stress | "
        "corr anchor | corr stress | DSR anchor | tier |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for cid in EXPECTED_CANDIDATE_IDS:
        c = state["candidates"].get(cid)
        if c is None:
            continue
        k1, k2, corr = c["k1"], c["k2"], c["correlation_with_s3"]
        dsr = c["dsr_anchor"]
        row_fmt = (
            "| {cid} | {sa:.2f} | {ss:.2f} | {ea:.3f} | {es:.3f} | "
            "{ca:.2f} | {cs:.2f} | {dsr} | {tier} |"
        )
        lines.append(
            row_fmt.format(
                cid=cid,
                sa=k1["sharpe_anchor_10bp"] or float("nan"),
                ss=k1["sharpe_stress_10bp"] or float("nan"),
                ea=k2["edge_anchor"],
                es=k2["edge_stress"],
                ca=corr["anchor"],
                cs=corr["stress"],
                dsr=f"{dsr:.3f}" if dsr is not None else "n/a",
                tier=c["tier"],
            )
        )
    kept = [cid for cid in EXPECTED_CANDIDATE_IDS if state["candidates"].get(cid, {}).get("kept")]
    lines += ["", f"Kept (K1 or K2): {kept or 'none'}", ""]
    (OUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(run())
