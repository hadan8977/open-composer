"""T-20261005-31 (R1005-T31): trial registry and Deflated Sharpe Ratio for the four ETF sleeves.

Measurement only: no strategy, spec or threshold is changed.  Rerun with

    scripts/run_capped.sh --mem 1.5G -- uv run python \
        reports/research/program/etf-dsr-2026-10-08/compute.py

What it does
* Rebuilds the daily net (10 bp per side, next-open fills) series of the CURRENT specs of S1, S2,
  S3 with the frozen engines (scripts/run_h20260918_05_recent_menu.py, run_h20260922_05_salvage.py,
  run_h20260928_23_s1_s2_rebalance_timing.py) on a 2015-01-02 panel, and takes the equal-weight
  mean of 5 rebalance offsets (signal day moved 0..4 sessions later; offset 0 is the live rule,
  asserted equal to ``salvage.run_cell``).  C2 is calendar-anchored (one version) and is read from
  reports/research/screens/h20260928_20_recent_opt/returns.parquet.
* Reruns every trial-family variant that can be rerun (the 104-cell H-20260918-05 grid and the
  overlay cells; for C2 the screen return files) to get the cross-variant variance of the annual
  Sharpe and the mean pairwise correlation.  Variants that cannot be rerun enter N with an assumed
  pairwise correlation of 0.5 (stated in results.json).
* DSR via open_composer.research.scorecard_v2.dsr on the excess-over-BIL series, n_eff =
  1 + (N-1)(1-mean corr) as in config/evaluation-standard-v2.json.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import run_h20260928_23_s1_s2_rebalance_timing as t23  # noqa: E402

from open_composer.research import scorecard_v2 as sc  # noqa: E402

CFG = sc.load_config()
RECENT_START = CFG["recent_window_start"]  # 2024-01-08
FULL_START = "2017-01-03"  # 252-session lookback + 260-session min history after panel start
N_OFFSETS = 5
ASSUMED_CORR_UNRERUN = 0.5
BASE_TARGET_S3, BOOST_TARGET_S3, BOOST_HOLD_S3 = 0.40, 0.60, 10  # S3 spec (H-20260922-05 path B)
SCREENS = ROOT / "reports/research/screens"
IT = "reports/research/iterations"

SPEC_CELL = {  # sleeve -> (grid-cell key in base.MENUS terms, vol target, boost)
    "S1": {"menu": "A2_sector", "lookback": "252", "rebal": "weekly", "top_n": 2, "target": None},
    "S2": {
        "menu": "A3_growth",
        "lookback": "blend",
        "rebal": "monthly",
        "top_n": 2,
        "target": 0.156,
    },
    "S3": {"menu": "A4_levered", "lookback": "63", "rebal": "monthly", "top_n": 2, "target": 0.40},
}

# ---------------------------------------------------------------------------
# trial families.  Each item: (label, n_trials, source path, rerun?)
# ``n_low`` = variants seen before the current spec was adopted (incl. its overlay);
# ``n_high`` = n_low + every other variant of the same mechanism family looked at before or after.
# ---------------------------------------------------------------------------
GRID = (
    "H-20260918-05 grid: 64 rotation cells (4 menus x lookback{63,126,252,blend} x top_n{1,2} x "
    "{monthly,weekly}) + 40 levered-trend cells",
    104,
    f"{IT}/h20260918_05_recent_menu/candidate-manifest.json",
    "reports/research/hypotheses/H-20260918-05-recent-window-etf-menu.md",
)
POOL = (
    "H-20260918-06 ETF pool: 96 cells (8 score x leverage families)",
    96,
    f"{IT}/h20260918_06_etf_pool/candidate-manifest.json",
)
GIANTS = (
    "Giants sweep 2026-09-22: 24 cells (F1 TQQQ RSI hedge, F2, F4, F5, F6 industry trend, F7)",
    24,
    f"{IT}/giants_sweep_20260922/candidate-manifest.json",
)
RSI_BRANCH = (
    "H-20260922-04 RSI-branch rotation: 16 cells",
    16,
    f"{IT}/h20260922_04_rsi_branch/candidate-manifest.json",
)
COMBO = (
    "H-20260927-01 sleeve combination: 7 candidates",
    7,
    f"{IT}/h20260927_01_sleeve_combination/candidate-manifest.json",
)
MENUS40 = (
    "H-20260928-40 equity ETF menus: 24 candidates",
    24,
    f"{IT}/h20260928_40_equity_etf_menus/candidate-manifest.json",
)

FAMILIES: dict[str, dict[str, Any]] = {
    "S1": {
        "strategy_id": "us_etf_sector_rotation_252_top2_weekly",
        "low": [GRID],
        "high_extra": [
            POOL,
            GIANTS,
            RSI_BRANCH,
            COMBO,
            MENUS40,
            (
                "H-20260922-05 path A, S1 vol-target cells 0.086/0.114 (tested, not adopted)",
                2,
                f"{IT}/h20260922_05_salvage/candidate-manifest.json",
            ),
            (
                "H-20260928-23 S1 weekly rebalance-day offsets O00..O04 (descriptive)",
                5,
                f"{IT}/h20260928_23_s1_rebalance_timing/candidate-manifest.json",
            ),
        ],
        "extra_rerun": [("S1_vt0.086", 0.086), ("S1_vt0.114", 0.114)],
    },
    "S2": {
        "strategy_id": "us_etf_growth_rotation_blend_top2_monthly",
        "low": [
            GRID,
            (
                "H-20260922-05 path A, S2 vol-target cells 0.117/0.156 (0.156 adopted)",
                2,
                f"{IT}/h20260922_05_salvage/candidate-manifest.json",
            ),
        ],
        "high_extra": [
            POOL,
            GIANTS,
            RSI_BRANCH,
            COMBO,
            MENUS40,
            (
                "H-20260928-23 S2 monthly rebalance-day offsets O00..O20 (descriptive)",
                21,
                f"{IT}/h20260928_23_s1_s2_rebalance_timing/candidate-manifest.json",
            ),
        ],
        "extra_rerun": [("S2_vt0.117", 0.117), ("S2_vt0.156", 0.156)],
    },
    "S3": {
        "strategy_id": "us_etf_levered_rotation_63_top2_monthly",
        "low": [
            GRID,
            (
                "H-20260922-02 S3 vol-target/brake grid: 3 targets x 2 brakes x 2 lookbacks",
                12,
                f"{IT}/h20260922_02_s3_voltarget/candidate-manifest.json",
            ),
            (
                "H-20260922-05 path B dip-boost cells: boost target {0.55,0.60} x hold {5,10}",
                4,
                f"{IT}/h20260922_05_salvage/candidate-manifest.json",
            ),
        ],
        "high_extra": [
            POOL,
            GIANTS,
            RSI_BRANCH,
            (
                "H-20260923-10 levered lanes: 5 candidates",
                5,
                f"{IT}/h20260923_10_levered_lanes/candidate-manifest.json",
            ),
            (
                "H-20260923-11 S3 bear guard: 5 candidates",
                5,
                f"{IT}/h20260923_11_s3_bear_guard/candidate-manifest.json",
            ),
            (
                "H-20260923-12 S3 defense-first: 3 candidates",
                3,
                f"{IT}/h20260923_12_s3_defense_first/candidate-manifest.json",
            ),
            COMBO,
            (
                "H-20260928-01 S3 rebalance tranching / offsets: 22 candidates",
                22,
                f"{IT}/h20260928_01_s3_rebalance_tranching/candidate-manifest.json",
            ),
            (
                "H-20260928-04 S3 alt-diversifier batch 1: 19 candidates",
                19,
                f"{IT}/h20260928_04_s3_alt_div_batch1/candidate-manifest.json",
            ),
        ],
        "extra_rerun": [
            ("S3_vt0.40", (0.40, None, None)),
            *[
                (f"S3_vt0.40_boost{bt}_h{h}", (0.40, bt, h))
                for bt, h in itertools.product((0.55, 0.60), (5, 10))
            ],
        ],
    },
}
RERUN_PREFIXES = (
    "H-20260918-05 grid",
    "H-20260922-05 path",
    "H-20260928-05 batch 2",
    "H-20260928-20",
    "H-20260928-42",
    "H-20260930-10",
)
# C2 is handled separately (screen returns).
C2_FAMILY = {
    "strategy_id": "us_etf_eom_sector_blend_monthly",
    "low": [
        (
            "H-20260928-05 batch 2: 7 candidates (EOM_REVERSAL_SPY = E0 and "
            "FRONT_RUN_SECTOR_TOP2 = S0 are counted once, in the next line)",
            5,
            f"{IT}/h20260928_05_registry_etf_batch2/candidate-manifest.json",
        ),
        (
            "H-20260928-20 recent-regime optimisation: 20 candidates "
            "(E0..E7, S0..S_ABSFILTER, C1, C2)",
            20,
            f"{IT}/h20260928_20_recent_regime_opt/candidate-manifest.json",
        ),
    ],
    "high_extra": [
        (
            "H-20260928-42 opex week calendar: 8 candidates (its 12 PLACEBO_* controls are not "
            "search trials and are excluded from N and from the variance/correlation)",
            8,
            f"{IT}/h20260928_42_opex_week/candidate-manifest.json",
        ),
        (
            "H-20260930-10 industry seasonality: 6 candidates",
            6,
            f"{IT}/h20260930_10_industry_seasonality/candidate-manifest.json",
        ),
        (
            "H-20260930-01 rebalancing front-run: 8 candidates (no returns file -> not rerun)",
            8,
            f"{IT}/h20260930_01_rebalancing_front_run/candidate-manifest.json",
        ),
    ],
}


# ---------------------------------------------------------------------------
# engine helpers
# ---------------------------------------------------------------------------
def eff_for(
    close,
    leg_open,
    leg_close,
    cfg: dict[str, Any],
    offset: int,
    target: float | None,
    boost: np.ndarray | None = None,
    boost_target: float | None = None,
) -> tuple[np.ndarray, list[str]]:
    """t23.offset_effective generalised to any grid cell and an optional dip boost."""
    menu = [s for s in base.MENUS[cfg["menu"]] if s in close.columns]
    cols = sorted(set(menu + [base.CASH]))
    score = base.momentum_score(close, cfg["lookback"])
    cash_score = score[base.CASH]
    signal_dates = t23.shifted_signal_dates(close.index, cfg["rebal"], offset)
    picks: dict[pd.Timestamp, list[str]] = {}
    for d in signal_dates:
        row = score.loc[d, menu].dropna()
        if row.empty:
            continue
        chosen = list(row.sort_values(ascending=False).index[: cfg["top_n"]])
        cs = cash_score.loc[d]
        if pd.notna(cs):
            chosen = [s for s in chosen if row[s] > cs]
        picks[d] = chosen
    weights = base.weights_from_selection(close.index, signal_dates, picks, cols)
    wb = weights.to_numpy(dtype=float)
    if target is None and boost is None:
        return wb, cols
    gross, _ = salvage.simulate(weights, leg_open, leg_close, np.ones(len(close.index)), 0.0)
    scale = salvage.vol_scale(close.index, signal_dates, gross, target, boost, boost_target)
    cash_i = cols.index(base.CASH)
    risk = wb.copy()
    risk[:, cash_i] = 0.0
    eff = risk * scale[:, None]
    eff[:, cash_i] = wb[:, cash_i] + (1.0 - scale) * risk.sum(axis=1)
    return eff, cols


def blended(close, leg_open, leg_close, cfg, target=None, boost=None, boost_target=None):
    rets = []
    for o in range(N_OFFSETS):
        eff, cols = eff_for(close, leg_open, leg_close, cfg, o, target, boost, boost_target)
        r, _ = t23.simulate_effective(eff, cols, leg_open, leg_close, base.COST_BPS_PRIMARY)
        rets.append(r)
    return pd.concat(rets, axis=1).mean(axis=1), rets[0]


def trend_series(close, open_, asset, sma, gate_on):
    r, _ = base.trend_cell(close, open_, asset, sma, gate_on, base.COST_BPS_PRIMARY)
    return r


def window(s: pd.Series, name: str) -> pd.Series:
    a = RECENT_START if name == "recent" else FULL_START
    return s.loc[s.index >= pd.Timestamp(a)].dropna()


def read_screen_series(dirname: str, rf: pd.Series) -> dict[str, pd.Series]:
    p = SCREENS / dirname / "returns.parquet"
    if not p.exists():
        return {}
    r = pd.read_parquet(p)
    out = {}
    for c in r.columns:
        if not c.endswith("net10") or "PLACEBO" in c:
            continue
        if "__o" in c and "__o00__" not in c:
            continue
        s = r[c]
        s.index = pd.to_datetime(s.index)
        out[f"{dirname}:{c.split('__')[0]}"] = s
    return out


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------
def family_stats(series: dict[str, pd.Series], n_total: int, wname: str) -> dict[str, Any]:
    """Cross-variant var(SR) and the pair-weighted mean correlation over ``n_total`` trials, of
    which ``len(series)`` are measured and the rest are assumed at ASSUMED_CORR_UNRERUN."""
    w = {k: window(v, wname) for k, v in series.items()}
    w = {k: v for k, v in w.items() if len(v) > 100 and v.std() > 0}
    frame = pd.DataFrame(w).dropna(how="any")
    srs = np.array([sc.annual_sharpe(frame[c].to_numpy()) for c in frame.columns])
    var_sr = float(np.var(srs, ddof=1))
    cm = frame.corr().to_numpy()
    iu = np.triu_indices_from(cm, k=1)
    k = len(frame.columns)
    corr_meas = float(cm[iu].mean())
    pairs_total = n_total * (n_total - 1) / 2.0
    pairs_meas = k * (k - 1) / 2.0
    corr_mix = (pairs_meas * corr_meas + (pairs_total - pairs_meas) * ASSUMED_CORR_UNRERUN) / (
        pairs_total
    )
    return {
        "n_rerun": k,
        "var_sr_annual": var_sr,
        "sr_median": float(np.median(srs)),
        "sr_max": float(srs.max()),
        "corr_measured_rerun": corr_meas,
        "corr_mix": float(corr_mix),
        "share_pairs_assumed": float(1 - pairs_meas / pairs_total),
        "names": list(frame.columns),
        "sr": [float(x) for x in srs],
    }


def dsr_at(excess: np.ndarray, var_sr: float, corr: float, n: float) -> dict[str, float]:
    n_eff = sc.n_eff_from_corr(n, corr)
    out = sc.dsr(excess, var_sr_annual=var_sr, n_eff=n_eff)
    out["n_eff"] = n_eff
    return out


def n_at_dsr(excess: np.ndarray, var_sr: float, corr: float, thr: float = 0.70) -> Any:
    """Smallest integer N whose DSR falls below ``thr``; 1 if PSR(0) itself is below, ">1e9"."""
    if dsr_at(excess, var_sr, corr, 1)["dsr"] < thr:
        return 1
    hi = 2
    while dsr_at(excess, var_sr, corr, hi)["dsr"] >= thr:
        hi *= 2
        if hi > 1e9:
            return ">1e9"
    lo = hi // 2  # dsr(lo) >= thr, dsr(hi) < thr
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if dsr_at(excess, var_sr, corr, mid)["dsr"] >= thr:
            lo = mid
        else:
            hi = mid
    return hi


def build_result(
    sleeve: str,
    spec_series: pd.Series,
    rerun: dict[str, pd.Series],
    fam: dict[str, Any],
    rf: pd.Series,
    extra_notes: list[str],
) -> dict[str, Any]:
    low_items, high_items = fam["low"], fam["low"] + fam["high_extra"]
    n_low = int(sum(i[1] for i in low_items))
    n_high = int(sum(i[1] for i in high_items))
    n_used = n_high  # brief: upper bound for the main result
    excess = (spec_series - rf.reindex(spec_series.index).fillna(0.0)).dropna()
    res: dict[str, Any] = {
        "sleeve": sleeve,
        "strategy_id": fam["strategy_id"],
        "trial_family": [
            {
                "label": i[0],
                "n": i[1],
                "source": i[2],
                "in_n_low": i in low_items,
                "rerun_for_stats": i[0].startswith(RERUN_PREFIXES),
            }
            for i in high_items
        ],
        "n_low": n_low,
        "n_high": n_high,
        "n_used": n_used,
        "n_used_rule": "upper bound (n_high) for the main result; n_low shown in sensitivity",
    }
    for wname in ("recent", "full"):
        fs = family_stats(rerun, n_used, wname)
        x = window(excess, wname).to_numpy()
        main = dsr_at(x, fs["var_sr_annual"], fs["corr_mix"], n_used)
        sens = {
            f"{m}x": dsr_at(x, fs["var_sr_annual"], fs["corr_mix"], max(1.0, m * n_used))["dsr"]
            for m in (0.5, 1, 2, 5)
        }
        sens["n_low"] = dsr_at(x, fs["var_sr_annual"], fs["corr_mix"], n_low)["dsr"]
        # corr sensitivity: assumed 0.5 -> measured-only corr (no assumption) and 0.8
        sens_corr = {
            f"corr={c}": dsr_at(x, fs["var_sr_annual"], c, n_used)["dsr"] for c in (0.3, 0.5, 0.8)
        }
        res[f"dsr_{wname}"] = main["dsr"]
        res[f"{wname}_detail"] = {
            "window": [
                str(window(excess, wname).index[0].date()),
                str(window(excess, wname).index[-1].date()),
            ],
            "sessions": main["sessions"],
            "sr_annual_excess_over_BIL": main["sr_annual"],
            "psr0": main["psr0"],
            "skew": main["skew"],
            "kurtosis": main["kurtosis"],
            "sr0_annual_expected_max_null": main["sr0_annual"],
            "n_eff": main["n_eff"],
            "mean_pairwise_corr": fs["corr_mix"],
            "mean_pairwise_corr_is_assumption": fs["share_pairs_assumed"] > 0,
            "corr_measured_on_rerun_variants": fs["corr_measured_rerun"],
            "share_of_pairs_with_assumed_corr_0.5": fs["share_pairs_assumed"],
            "n_rerun_variants": fs["n_rerun"],
            "var_sr_annual": fs["var_sr_annual"],
            "rerun_sr_median": fs["sr_median"],
            "rerun_sr_max": fs["sr_max"],
            "sensitivity_N": sens,
            "sensitivity_corr_at_n_used": sens_corr,
            "n_at_dsr_070": n_at_dsr(x, fs["var_sr_annual"], fs["corr_mix"]),
        }
        if wname == "recent":
            res["mean_pairwise_corr"] = fs["corr_mix"]
            res["mean_pairwise_corr_is_assumption"] = True
            res["var_sr_annual"] = fs["var_sr_annual"]
            res["n_eff"] = main["n_eff"]
            res["sensitivity"] = sens
            res["n_at_dsr_070"] = res["recent_detail"]["n_at_dsr_070"]
            res["passes_p1_dsr"] = bool(
                main["dsr"] >= CFG["tiers"]["P1_paper_incubation"]["dsr_min"]
            )
    res["notes"] = extra_notes
    return res


def main() -> int:
    base.WARMUP_START = "2015-01-02"
    symbols = sorted(set(base.all_symbols()) | set(salvage.symbols()))
    close, open_ = base.load_panel(symbols)
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
    sig = salvage.dip_signal(close)
    print(
        f"panel {close.index[0].date()}..{close.index[-1].date()} symbols={close.shape[1]}",
        flush=True,
    )

    # ---- common grid, 5-offset blend (rotation cells), trend cells single series
    grid: dict[str, pd.Series] = {}
    for menu, lb, top, reb in itertools.product(
        base.MENUS, base.GRID_LOOKBACKS, base.GRID_TOPN, base.GRID_REBAL
    ):
        cfg = {"menu": menu, "lookback": lb, "top_n": top, "rebal": reb}
        grid[f"rot_{menu}_lb{lb}_top{top}_{reb}"] = blended(close, leg_open, leg_close, cfg)[0]
    for asset, sma, gate in itertools.product(base.TREND_ASSETS, base.GRID_SMA, base.GRID_GATE_ON):
        grid[f"trd_{asset}_sma{sma}_{gate}"] = trend_series(close, open_, asset, sma, gate)
    assert len(grid) == 104, len(grid)
    print("grid done", flush=True)

    # ---- current specs (blend) + O00 parity with salvage.run_cell
    spec: dict[str, pd.Series] = {}
    parity: dict[str, float] = {}
    boost = salvage.boost_window(sig, BOOST_HOLD_S3)
    for k, cfg in SPEC_CELL.items():
        if k == "S3":
            s, o0 = blended(close, leg_open, leg_close, cfg, BASE_TARGET_S3, boost, BOOST_TARGET_S3)
            ref, _ = salvage.run_cell(
                close,
                leg_open,
                leg_close,
                "s3",
                BASE_TARGET_S3,
                base.COST_BPS_PRIMARY,
                boost=boost,
                boost_target=BOOST_TARGET_S3,
            )
        else:
            s, o0 = blended(close, leg_open, leg_close, cfg, cfg["target"])
            ref, _ = salvage.run_cell(
                close, leg_open, leg_close, k.lower(), cfg["target"], base.COST_BPS_PRIMARY
            )
        parity[k] = float(np.max(np.abs(ref.to_numpy() - o0.to_numpy())))
        assert parity[k] < 1e-9, (k, parity[k])
        spec[k] = s
    print("spec parity", parity, flush=True)

    results = []
    for k in ("S1", "S2", "S3"):
        fam = FAMILIES[k]
        rerun = dict(grid)
        for name, tgt in fam["extra_rerun"]:
            cfg = SPEC_CELL[k]
            if k == "S3":
                t, bt, h = tgt
                b = salvage.boost_window(sig, h) if bt else None
                rerun[name] = blended(close, leg_open, leg_close, cfg, t, b, bt)[0]
            else:
                rerun[name] = blended(close, leg_open, leg_close, cfg, tgt)[0]
        notes = [
            "series = mean of 5 rebalance offsets (signal day +0..+4 sessions), 10 bp per side, "
            "next-open fills, minus BIL daily return; O00 reproduces salvage.run_cell "
            f"(max abs diff {parity[k]:.2e}).",
            "rerun variants (measured var_sr / corr): the 104-cell H-20260918-05 grid "
            "(rotation cells 5-offset blended, trend cells single) plus the listed overlay cells; "
            "all other family members are not rerun and enter N with an assumed pairwise corr 0.5.",
        ]
        if k == "S3":
            notes.append(
                "S3 counts are a floor: variants mentioned only in reports or notes of the "
                "2023-2025 salvage designs (H-20260923-09 attribution has no manifest, "
                "H-20260928-13 manifest is empty) are not countable and are covered by "
                "the 2x and 5x sensitivity rows."
            )
        results.append(build_result(k, spec[k], rerun, fam, rf, notes))
        print(
            k,
            "dsr_recent",
            results[-1]["dsr_recent"],
            "dsr_full",
            results[-1]["dsr_full"],
            flush=True,
        )

    # ---- C2 from screen returns
    c2_series: dict[str, pd.Series] = {}
    for d in (
        "h20260928_20_recent_opt",
        "h20260928_05_batch2",
        "h20260928_42_opex_week",
        "h20260930_10_industry_seasonality",
    ):
        c2_series.update(read_screen_series(d, rf))
    # E0 == EOM_REVERSAL_SPY and S0 == FRONT_RUN_SECTOR_TOP2: drop the batch-2 duplicates
    for dup in (
        "h20260928_05_batch2:EOM_REVERSAL_SPY",
        "h20260928_05_batch2:FRONT_RUN_SECTOR_TOP2",
    ):
        c2_series.pop(dup, None)
    c2_spec = c2_series["h20260928_20_recent_opt:C2"]
    notes = [
        "C2 is calendar-anchored (one version, no rebalance-day offsets): the single series is "
        "C2__o00__net10 of reports/research/screens/h20260928_20_recent_opt/returns.parquet "
        "(10 bp per side, next-open fills), minus BIL.",
        "rerun variants = every o00 net10 column of the screen return files for batch 2 "
        "(5 non-duplicate candidates), the 20 recent-regime variants, the opex-week "
        "(non-placebo) and industry-seasonality screens; H-20260930-01 (8) has no "
        "returns file and enters N with assumed corr 0.5.",
    ]
    results.append(build_result("C2", c2_spec, c2_series, C2_FAMILY, rf, notes))
    print(
        "C2",
        "dsr_recent",
        results[-1]["dsr_recent"],
        "dsr_full",
        results[-1]["dsr_full"],
        flush=True,
    )

    out = {
        "task": "T-20261005-31",
        "code": "R1005-T31",
        "config": "config/evaluation-standard-v2.json",
        "dsr_impl": "open_composer/research/scorecard_v2.py::dsr",
        "p1_dsr_min": CFG["tiers"]["P1_paper_incubation"]["dsr_min"],
        "windows": {"recent": f"{RECENT_START}..panel end", "full": f"{FULL_START}..panel end"},
        "panel": [str(close.index[0].date()), str(close.index[-1].date())],
        "series_basis": "excess over BIL, net 10 bp per side, next-open fills",
        "o00_parity_max_abs_diff": parity,
        "results": results,
    }
    (OUT / "results.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("written", OUT / "results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
