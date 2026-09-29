"""Batch screening lane: judge 10-30 published strategy rules in one run under
one fixed contract, instead of one 360-480 line script + 13-file dossier per
idea.

Reuses, unedited: `run_h20260918_05_recent_menu.py` (`base`) for the panel
loader, cost/fill convention and `Metrics`/`metrics`; `run_h20260922_05_salvage`
(`salvage`) for `legs`/`simulate`/`vol_scale`/`boost_window`/`dip_signal`/S1-S3;
`run_h20260927_01_sleeve_combination` (`combo`) for `solve_k`/`control_series`;
`run_h20260928_01_s3_rebalance_tranching` (`tranche`) for `shifted_signal_dates`
/`offset_effective`/`simulate_effective`/`passes_g1_or_g1alt`. This module adds
no new simulator: every return series is produced by `salvage.simulate` or
`tranche.simulate_effective`.

Usage for a future round
-------------------------
1. Write the iteration dossier (`reports/research/iterations/<iter_id>/`) and
   its `candidate-manifest.json` first, one entry per `ScreenCandidate.id`,
   *before* any return is computed (research-mission preregistration rule).
2. Write `scripts/screen_batches/<batch>.py` exporting `CANDIDATES:
   list[ScreenCandidate]` with ids matching the manifest exactly.
3. Run:
       scripts/run_capped.sh --mem 1.8G -- \\
           uv run python scripts/screen_batch.py --batch <batch> \\
               --iteration <iter_id>
4. Read `reports/research/screens/<batch>/leaderboard.md`. A candidate only
   clears the bar if `diversifier_pass` is true and the judged (median-offset)
   anchor Sharpe beats a vol-matched S3 control (owner rule: Sharpe first, not
   sizing) -- G1/G1' alone is not sufficient.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import run_h20260927_01_sleeve_combination as combo  # noqa: E402
import run_h20260928_01_s3_rebalance_tranching as tranche  # noqa: E402

from open_composer.research.campaign_statistics import deflated_sharpe_probability  # noqa: E402

CASH = base.CASH  # SHY
RF = base.RF  # BIL

# Widen warmup the same way the tranching/combination scripts do, so the
# stress window (starting 2016-05-02) has lookback history behind it.
PANEL_START = "2015-01-02"

WINDOWS: dict[str, tuple[str, str]] = {
    "select": ("2023-09-18", "2025-12-31"),
    "anchor": ("2024-01-08", "2026-09-17"),
    "holdout": ("2026-01-02", "2026-09-17"),  # contaminated: reference only
    "stress": ("2016-05-02", "2023-09-15"),
}
CONTAMINATED_WINDOWS = frozenset({"holdout"})
CALENDAR_2022 = ("2022-01-01", "2022-12-31")

MONTHLY_OFFSETS: list[int] = list(range(21))
WEEKLY_OFFSETS: list[int] = list(range(5))

COST_BPS_PRIMARY = base.COST_BPS_PRIMARY  # 10.0
COST_BPS_STRESS = base.COST_BPS_STRESS  # 20.0

DIVERSIFIER_SHARPE_EDGE_MIN = combo.SHARPE_EDGE_MIN  # 0.10
DSR_HAC_LAG = 21  # matches DSR_HAC_LAG convention used across scripts/evaluate_*.py


@dataclass(frozen=True)
class ScreenCandidate:
    """One published rule under test. `weights_fn` is long-only, sum(weights)
    <= 1, and may look at `close.loc[:asof]` only; the screening harness adds
    the 1 - sum(weights) remainder to SHY.

    `freq` is "M" (monthly), "W" (weekly), or "D" -- calendar-anchored daily
    rules (turn-of-month, pre-FOMC drift, ...). For "D", `weights_fn` is
    evaluated on every trading day by default (signal at that day's close,
    next-open fill, same as M/W); there is exactly one version, so offsets
    don't apply. `signal_dates_fn(index) -> list[pd.Timestamp]` lets a slow
    "D" rule restrict evaluation to a handful of dates a year (e.g. only
    FOMC-eve sessions) instead of every day; weights are held constant
    between those dates, same as any other frequency."""

    id: str
    name: str
    source_card: str
    universe: tuple[str, ...]
    freq: str  # "M", "W", or "D"
    weights_fn: Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]
    signal_dates_fn: Callable[[pd.DatetimeIndex], list[pd.Timestamp]] | None = None

    def __post_init__(self) -> None:
        if self.freq not in ("M", "W", "D"):
            raise ValueError(f"{self.id}: freq must be 'M', 'W' or 'D', got {self.freq!r}")


def offsets_for_freq(freq: str) -> list[int]:
    if freq == "M":
        return MONTHLY_OFFSETS
    if freq == "W":
        return WEEKLY_OFFSETS
    return [0]  # "D": exactly one version, offsets don't apply


def batch_symbols(candidates: list[ScreenCandidate]) -> list[str]:
    """Union of every candidate's universe with the S3 incumbent's own
    universe (needed for the diversifier test and the S3 correlation)."""
    out = set(salvage.symbols()) | {CASH, RF}
    for c in candidates:
        out.update(c.universe)
    return sorted(out)


PanelExtender = Callable[[pd.DataFrame, pd.DataFrame], tuple[pd.DataFrame, pd.DataFrame]]


def apply_panel_extension(
    close: pd.DataFrame, open_: pd.DataFrame, extend_panel: PanelExtender
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Append instruments that are not in the SIP daily panel (crypto sampled
    at the US session, synthetic leveraged series, ...). `extend_panel(close,
    open_)` returns (extra_close, extra_open) with new columns only; they are
    reindexed to the equity calendar with no fill, so the extender must supply
    session-aligned prices itself."""
    extra_close, extra_open = extend_panel(close, open_)
    if list(extra_close.columns) != list(extra_open.columns):
        raise ValueError("extend_panel: close and open columns differ")
    clash = sorted(set(extra_close.columns) & set(close.columns))
    if clash:
        raise ValueError(f"extend_panel: columns already in the panel: {clash}")
    extra_close = extra_close.reindex(close.index)
    extra_open = extra_open.reindex(open_.index)
    return pd.concat([close, extra_close], axis=1), pd.concat([open_, extra_open], axis=1)


def load_batch_panel(
    candidates: list[ScreenCandidate],
    extend_panel: PanelExtender | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    """(close, open_, leg_open, leg_close, rf). Sets `base.WARMUP_START` the
    same way the tranching/combination scripts do before loading. A batch
    module may export `extend_panel` (see `apply_panel_extension`)."""
    base.WARMUP_START = PANEL_START
    close, open_ = base.load_panel(batch_symbols(candidates))
    if extend_panel is not None:
        close, open_ = apply_panel_extension(close, open_, extend_panel)
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[RF] / close[RF].shift(1) - 1.0).fillna(0.0)
    return close, open_, leg_open, leg_close, rf


def signal_dates(index: pd.DatetimeIndex, freq: str, offset: int) -> list[pd.Timestamp]:
    """Monthly: `tranche.shifted_signal_dates` unchanged. Weekly: the same
    semantics (last trading day of each period, shifted `offset` sessions
    later), on a weekly calendar."""
    if freq == "M":
        return tranche.shifted_signal_dates(index, offset)
    flags = base.rebalance_flags(index, "weekly").to_numpy()
    positions = np.flatnonzero(flags) + offset
    return [index[i] for i in positions if i < len(index)]


def candidate_signal_dates(
    index: pd.DatetimeIndex, candidate: ScreenCandidate, offset: int
) -> list[pd.Timestamp]:
    """The dates `weights_fn` is evaluated on. "M"/"W": `signal_dates` above.
    "D": every trading day, or just `candidate.signal_dates_fn(index)` if the
    candidate supplies one (offset is ignored -- there is exactly one
    version for "D")."""
    if candidate.freq == "D":
        if candidate.signal_dates_fn is not None:
            return list(candidate.signal_dates_fn(index))
        return list(index)
    return signal_dates(index, candidate.freq, offset)


def first_valid_signal_date(close: pd.DataFrame, candidate: ScreenCandidate) -> pd.Timestamp:
    """First offset-0 signal date at which `weights_fn` returns a nonzero,
    finite weight -- i.e. the date the candidate first has enough lookback
    history to be computed at all."""
    universe = [s for s in candidate.universe if s in close.columns]
    for d in candidate_signal_dates(close.index, candidate, 0):
        raw = candidate.weights_fn(close, d) or {}
        if any(k in universe and np.isfinite(v) and v > 0 for k, v in raw.items()):
            return d
    return close.index[-1]


def window_actual_start(window_start: str, first_valid: pd.Timestamp) -> pd.Timestamp:
    return max(pd.Timestamp(window_start), first_valid)


def missing_symbols(close: pd.DataFrame, candidate: ScreenCandidate) -> list[str]:
    return [s for s in candidate.universe if s not in close.columns]


def weights_frame(
    close: pd.DataFrame, candidate: ScreenCandidate, offset: int
) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """Target-weight frame: candidate weights plus a SHY remainder, held
    constant between signal dates, effective at the OPEN of the session after
    each signal date -- the same piecewise-constant convention as
    `base.weights_from_selection`."""
    universe = [s for s in candidate.universe if s in close.columns]
    cols = sorted(set(universe) | {CASH})
    dates = candidate_signal_dates(close.index, candidate, offset)
    pos = {d: i for i, d in enumerate(close.index)}
    next_change: dict[int, dict[str, float]] = {}
    for d in dates:
        i = pos[d]
        if i + 1 >= len(close.index):
            continue
        raw = candidate.weights_fn(close, d) or {}
        raw = {k: float(v) for k, v in raw.items() if k in universe and np.isfinite(v) and v > 0}
        total = sum(raw.values())
        if total > 1.0 + 1e-9:
            raise ValueError(f"{candidate.id}: weights sum to {total:.6f} > 1 at {d.date()}")
        book = dict(raw)
        book[CASH] = book.get(CASH, 0.0) + max(0.0, 1.0 - total)
        next_change[i + 1] = book
    rows: list[dict[str, float]] = []
    current: dict[str, float] = {CASH: 1.0}
    for i in range(len(close.index)):
        if i in next_change:
            current = next_change[i]
        rows.append(dict(current))
    frame = pd.DataFrame(rows, index=close.index).reindex(columns=cols).fillna(0.0)
    return frame, dates


def candidate_returns_for_offset(
    close: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    candidate: ScreenCandidate,
    offset: int,
    cost_bps: float,
) -> tuple[pd.Series, pd.Series]:
    """Daily net returns for one candidate at one rebalance offset. Builds the
    target-weight frame above, then calls the frozen `salvage.simulate`
    unchanged (no vol overlay -- `scale = 1` everywhere)."""
    weights, _dates = weights_frame(close, candidate, offset)
    scale = np.ones(len(close.index))
    return salvage.simulate(weights, leg_open, leg_close, scale, cost_bps)


@dataclass
class OffsetMetrics:
    net10: dict[str, float]
    net20: dict[str, float]
    g1_10bp: bool
    g1_20bp: bool


def evaluate_offset_window(
    ret10: pd.Series,
    turn10: pd.Series,
    ret20: pd.Series,
    turn20: pd.Series,
    rf: pd.Series,
    window: tuple[str, str],
    first_valid: pd.Timestamp,
) -> tuple[dict[str, object], pd.Timestamp]:
    start = window_actual_start(window[0], first_valid)
    end = pd.Timestamp(window[1])
    mask10 = (ret10.index >= start) & (ret10.index <= end)
    mask20 = (ret20.index >= start) & (ret20.index <= end)
    m10 = asdict(base.metrics(ret10.loc[mask10], rf, turn10.loc[mask10]))
    m20 = asdict(base.metrics(ret20.loc[mask20], rf, turn20.loc[mask20]))
    g1_10 = tranche.passes_g1_or_g1alt(m10) if np.isfinite(m10["sharpe"]) else False
    g1_20 = tranche.passes_g1_or_g1alt(m20) if np.isfinite(m20["sharpe"]) else False
    return {"net10": m10, "net20": m20, "g1_10bp": bool(g1_10), "g1_20bp": bool(g1_20)}, start


def offset_summary(per_offset_net10: dict[int, dict[str, float]]) -> dict[str, dict[str, float]]:
    """min/median/max of each metric across offsets (net10). The judged value
    is the median -- the owner rule that a live date can never be hand-picked."""
    offsets = sorted(per_offset_net10)
    out: dict[str, dict[str, float]] = {}
    for metric in ("cagr", "sharpe", "max_dd", "vol"):
        vals = np.array([per_offset_net10[o][metric] for o in offsets], dtype=float)
        out[metric] = {
            "min": float(np.min(vals)),
            "median": float(np.median(vals)),
            "max": float(np.max(vals)),
        }
    return out


def judged_offset(values_by_offset: dict[int, float]) -> int:
    """The offset whose value equals the median (exact for an odd offset
    count: 21 monthly or 5 weekly versions)."""
    ordered = sorted(values_by_offset, key=lambda o: values_by_offset[o])
    return ordered[len(ordered) // 2]


def s3_incumbent(
    close: pd.DataFrame, leg_open: pd.DataFrame, leg_close: pd.DataFrame, cost_bps: float
) -> tuple[pd.Series, pd.Series]:
    """The live month-end S3 (offset 0), via `tranche.offset_effective` /
    `tranche.simulate_effective` exactly as the tranching script computes it."""
    boost = salvage.boost_window(salvage.dip_signal(close), tranche.S3_BOOST_HOLD)
    eff, cols = tranche.offset_effective(close, leg_open, leg_close, 0, boost)
    return tranche.simulate_effective(eff, cols, leg_open, leg_close, cost_bps)


def combine_two_sleeves(
    sleeve_rets: dict[str, pd.Series], index: pd.DatetimeIndex, combo_cost_bps: float
) -> tuple[pd.Series, pd.Series]:
    """Two-sleeve port of `combo.combine_portfolio` + `combo.weights_inverse_vol`
    (63-session trailing inverse-vol, monthly rebalance, intra-month drift,
    turnover cost). Ported rather than called directly because the frozen
    functions hardcode three sleeve keys ("s1","s2","s3"); the math is
    otherwise identical."""
    keys = ("s3", "candidate")
    lookback = combo.INV_VOL_LOOKBACK
    rets_np = {k: sleeve_rets[k].reindex(index).fillna(0.0).to_numpy() for k in keys}
    r = np.column_stack([rets_np[k] for k in keys])
    n = len(index)
    flags = base.rebalance_flags(index, "monthly").to_numpy()
    signal_positions = np.flatnonzero(flags)
    rebal_effective = {int(i) + 1 for i in signal_positions if i + 1 < n}

    def weight_fn(asof: int) -> np.ndarray:
        start = asof - lookback + 1
        if start < 0:
            return np.array([0.5, 0.5])
        stds = {k: float(np.std(rets_np[k][start : asof + 1], ddof=1)) for k in keys}
        if any(v <= 0 or not np.isfinite(v) for v in stds.values()):
            return np.array([0.5, 0.5])
        inv = {k: 1.0 / v for k, v in stds.items()}
        total = sum(inv.values())
        return np.array([inv[k] / total for k in keys])

    port_ret = np.zeros(n)
    turnover = np.zeros(n)
    w_prev = weight_fn(-1)
    for i in range(n):
        if i in rebal_effective:
            target = weight_fn(i - 1)
            turnover[i] = float(np.abs(target - w_prev).sum())
            w_prev = target
        day_ret = float(np.dot(w_prev, r[i]))
        port_ret[i] = day_ret - turnover[i] * combo_cost_bps / 10_000.0
        grown = w_prev * (1.0 + r[i])
        total = float(grown.sum())
        w_prev = grown / total if total != 0.0 else w_prev
    return pd.Series(port_ret, index=index), pd.Series(turnover, index=index)


def diversifier_edge_for_offset(
    s3_ret10: pd.Series,
    candidate_ret10: pd.Series,
    shy_ret: pd.Series,
    rf: pd.Series,
    window: tuple[str, str],
) -> float:
    """edge = Sharpe(S3 + candidate, inverse-vol) - Sharpe(k*S3 + (1-k)*SHY),
    k solved (`combo.solve_k`) so the control matches the combo's realized
    vol in this window."""
    assert_same_session_convention(candidate_ret10, s3_ret10, window)
    index = candidate_ret10.index.intersection(s3_ret10.index)
    combo_ret, combo_turn = combine_two_sleeves(
        {"s3": s3_ret10, "candidate": candidate_ret10}, index, COST_BPS_PRIMARY
    )
    a, b = window
    mask = (index >= a) & (index <= b)
    combo_met = base.metrics(combo_ret.loc[mask], rf, combo_turn.loc[mask])
    target_vol = float(combo_ret.loc[mask].std(ddof=1))
    r_s3_win = s3_ret10.reindex(index).loc[mask].to_numpy()
    r_shy_win = shy_ret.reindex(index).loc[mask].to_numpy()
    k = combo.solve_k(target_vol, r_s3_win, r_shy_win)
    ctrl_ret = pd.Series(combo.control_series(k, r_s3_win, r_shy_win), index=index[mask])
    zero_turn = pd.Series(0.0, index=ctrl_ret.index)
    ctrl_met = base.metrics(ctrl_ret, rf, zero_turn)
    return combo_met.sharpe - ctrl_met.sharpe


def assert_same_session_convention(
    candidate_ret: pd.Series, s3_ret: pd.Series, window: tuple[str, str]
) -> None:
    """Refuse a candidate whose daily returns sit one session off S3's.

    S3 (salvage engine) is close-to-close with next-open fills on rebalance
    days. A series built on another engine's convention (e.g. signal_card's
    open-to-open ``next_open_returns``, labelled at the start of the
    interval) correlates with S3 more at lag +/-1 than at lag 0; mixing them
    understates the correlation and overstates every combination edge
    (2026-09-29, h20260929_12 first run). Near-zero correlations at every lag
    (hedged or market-neutral books) pass.
    """
    a, b = window
    idx = candidate_ret.index.intersection(s3_ret.index)
    idx = idx[(idx >= a) & (idx <= b)]
    if len(idx) < 30:
        return
    c = candidate_ret.reindex(s3_ret.index)
    s = s3_ret
    lag0 = abs(float(c.loc[idx].corr(s.loc[idx])))
    lagged = max(
        abs(float(c.shift(1).loc[idx].corr(s.loc[idx]))),
        abs(float(c.shift(-1).loc[idx].corr(s.loc[idx]))),
    )
    if lagged > 0.2 and lagged > lag0 + 0.1:
        raise ValueError(
            "candidate returns look one session off S3's convention "
            f"(|corr| lag0 {lag0:.2f} vs lag+/-1 {lagged:.2f} in {a}..{b}); "
            "rebuild the candidate on S3's close-to-close, next-open-fill convention"
        )


def correlation_with_s3(
    candidate_ret: pd.Series, s3_ret: pd.Series, window: tuple[str, str]
) -> float:
    a, b = window
    idx = candidate_ret.index.intersection(s3_ret.index)
    idx = idx[(idx >= a) & (idx <= b)]
    if len(idx) < 2:
        return float("nan")
    assert_same_session_convention(candidate_ret, s3_ret, window)
    sub = pd.DataFrame({"c": candidate_ret.loc[idx], "s3": s3_ret.loc[idx]})
    if sub["c"].std(ddof=1) == 0 or sub["s3"].std(ddof=1) == 0:
        return float("nan")
    return float(sub.corr().loc["c", "s3"])


def evaluate_candidate(
    candidate: ScreenCandidate,
    *,
    close: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    rf: pd.Series,
    shy_ret: pd.Series,
    s3_ret10: pd.Series,
    n_trials: int,
) -> dict[str, object]:
    """Full per-candidate result: per-offset/per-window metrics and gates,
    min/median/max across offsets, the diversifier test against S3, S3
    correlation, and deflated Sharpe on the judged anchor Sharpe. Also returns
    the raw per-offset net10/net20 series for `returns.parquet`."""
    missing = missing_symbols(close, candidate)
    result: dict[str, object] = {
        "id": candidate.id,
        "name": candidate.name,
        "source_card": candidate.source_card,
        "universe": list(candidate.universe),
        "freq": candidate.freq,
        "missing_symbols": missing,
        "n_trials": n_trials,
    }
    if missing:
        result["skipped"] = True
        result["skip_reason"] = f"missing from local panel: {missing}"
        return result
    result["skipped"] = False

    offsets = offsets_for_freq(candidate.freq)
    first_valid = first_valid_signal_date(close, candidate)
    result["first_valid_signal_date"] = str(first_valid.date())
    result["offsets"] = offsets
    result["n_offsets"] = len(offsets)  # "D" candidates: exactly 1, no offset sweep

    ret10_by_offset: dict[int, pd.Series] = {}
    ret20_by_offset: dict[int, pd.Series] = {}
    per_window: dict[str, dict[str, object]] = {}
    for wname in WINDOWS:
        per_window[wname] = {"offsets": {}, "actual_start": None}

    for offset in offsets:
        ret10, turn10 = candidate_returns_for_offset(
            close, leg_open, leg_close, candidate, offset, COST_BPS_PRIMARY
        )
        ret20, turn20 = candidate_returns_for_offset(
            close, leg_open, leg_close, candidate, offset, COST_BPS_STRESS
        )
        ret10_by_offset[offset] = ret10
        ret20_by_offset[offset] = ret20
        for wname, window in WINDOWS.items():
            metrics_dict, start = evaluate_offset_window(
                ret10, turn10, ret20, turn20, rf, window, first_valid
            )
            per_window[wname]["offsets"][offset] = metrics_dict
            per_window[wname]["actual_start"] = str(start.date())

    judged: dict[str, dict[str, object]] = {}
    for wname, body in per_window.items():
        net10_by_offset = {o: body["offsets"][o]["net10"] for o in offsets}
        body["summary_net10"] = offset_summary(net10_by_offset)
        body["g1_pass_count_10bp"] = sum(1 for o in offsets if body["offsets"][o]["g1_10bp"])
        body["g1_pass_count_20bp"] = sum(1 for o in offsets if body["offsets"][o]["g1_20bp"])
        sharpe_by_offset = {o: net10_by_offset[o]["sharpe"] for o in offsets}
        jo = judged_offset(sharpe_by_offset)
        judged[wname] = {"offset": jo, **net10_by_offset[jo]}
    result["per_window"] = per_window
    result["judged"] = judged

    diversifier: dict[str, object] = {}
    for wname in ("anchor", "stress"):
        window = WINDOWS[wname]
        edge_by_offset = {
            o: diversifier_edge_for_offset(s3_ret10, ret10_by_offset[o], shy_ret, rf, window)
            for o in offsets
        }
        diversifier[wname] = {
            "edge_by_offset": edge_by_offset,
            "judged_edge": float(np.median(list(edge_by_offset.values()))),
        }
    diversifier["pass"] = bool(
        diversifier["anchor"]["judged_edge"] >= DIVERSIFIER_SHARPE_EDGE_MIN
        and diversifier["stress"]["judged_edge"] >= DIVERSIFIER_SHARPE_EDGE_MIN
    )
    result["diversifier"] = diversifier

    judged_anchor_offset = judged["anchor"]["offset"]
    result["correlation_with_s3"] = {
        "stress": correlation_with_s3(
            ret10_by_offset[judged_anchor_offset], s3_ret10, WINDOWS["stress"]
        ),
        "anchor": correlation_with_s3(
            ret10_by_offset[judged_anchor_offset], s3_ret10, WINDOWS["anchor"]
        ),
        "2022": correlation_with_s3(ret10_by_offset[judged_anchor_offset], s3_ret10, CALENDAR_2022),
    }

    anchor_start = window_actual_start(WINDOWS["anchor"][0], first_valid)
    anchor_end = pd.Timestamp(WINDOWS["anchor"][1])
    judged_ret = ret10_by_offset[judged_anchor_offset]
    mask = (judged_ret.index >= anchor_start) & (judged_ret.index <= anchor_end)
    excess = (judged_ret.loc[mask] - rf.reindex(judged_ret.index).fillna(0.0).loc[mask]).to_numpy()
    try:
        result["dsr_anchor"] = float(
            deflated_sharpe_probability(excess, trial_count=n_trials, hac_lag=DSR_HAC_LAG)
        )
    except ValueError as exc:
        result["dsr_anchor"] = None
        result["dsr_anchor_error"] = str(exc)

    result["_returns_net10_by_offset"] = ret10_by_offset
    result["_returns_net20_by_offset"] = ret20_by_offset
    return result
