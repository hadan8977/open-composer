"""Generic giants-sweep engine: one manifest, one pass, every candidate family.

Brief: reports/research/briefs/ENGINE-giants-sweep-2026-09-22.md
Manifest: config/giants_sweep/manifest.yaml (built from the "汇总" table of
reports/research/intel/I-20260922-03-giants-census.md).

Nothing about the measurement protocol is re-invented here. The four windows, the
cost model, the next-open fill assumption, the metric definitions, the data panel
and the random-pick placebo all come from
``scripts/run_h20260918_05_recent_menu.py``; the G1-G5 gate thresholds and the
calendar-shift placebo come from ``scripts/run_h20260922_02_s3_voltarget.py``; the
Wilder RSI and the nested-branch evaluation order come from
``scripts/run_h20260922_04_rsi_branch.py``. This file only adds the spec
interpreter that lets one manifest express all of them, plus the primitives the
census needs that none of those three had (canary/13612W, relative-momentum
selection, fixed weights with real drift between rebalances, the 9-sig signal
line, whole-basket trend following and the overnight leg).

Regression contract: ``--regress`` re-expresses the three live sleeves S1/S2/S3
of H-20260918-05 as manifest specs and fails if any window Sharpe moves by more
than 0.01 from ``rotation_cell`` recomputed on the same panel. The card's own
section-5 numbers are reported alongside; S1's holdout Sharpe is 2.18 today
against 2.22 in the card, and the reference implementation reproduces 2.18 too,
so that gap is SIP archive drift since 2026-09-18, not an engine difference.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402

ITER_ID = "giants_sweep_20260922"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
MANIFEST_PATH = ROOT / "config" / "giants_sweep" / "manifest.yaml"

# gate thresholds -- copied verbatim from run_h20260922_02_s3_voltarget.py
GATE_G1_CAGR = 0.50
GATE_G1_MAXDD = -0.35
GATE_G1ALT_SHARPE = 2.0
GATE_G1ALT_CAGR = 0.30
GATE_G2_SHARPE = 1.0
GATE_G3_PLACEBO = 0.10

REGRESSION_TARGETS = {
    # H-20260918-05 section 5, the three sleeves live on the Alpaca paper account
    "S1_rot_A2_sector_lb252_top2_weekly": {"select": 1.14, "holdout": 2.22, "anchor": 1.36},
    "S2_rot_A3_growth_lbblend_top2_monthly": {"select": 1.66, "holdout": 1.36, "anchor": 1.50},
    "S3_rot_A4_levered_lb63_top2_monthly": {"select": 1.21, "holdout": 1.80, "anchor": 1.48},
}
REGRESSION_SPECS = {
    "S1_rot_A2_sector_lb252_top2_weekly": {
        "rebalance": "weekly",
        "root": {
            "rank": {
                "menu": base.MENUS["A2_sector"],
                "lookback": 252,
                "top_n": 2,
                "cash_filter": "SHY",
            }
        },
    },
    "S2_rot_A3_growth_lbblend_top2_monthly": {
        "rebalance": "monthly",
        "root": {
            "rank": {
                "menu": base.MENUS["A3_growth"],
                "lookback": "blend",
                "top_n": 2,
                "cash_filter": "SHY",
            }
        },
    },
    "S3_rot_A4_levered_lb63_top2_monthly": {
        "rebalance": "monthly",
        "root": {
            "rank": {
                "menu": base.MENUS["A4_levered"],
                "lookback": 63,
                "top_n": 2,
                "cash_filter": "SHY",
            }
        },
    },
}


# --------------------------------------------------------------------------- data


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _walk_symbols(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "asset" and isinstance(value, str):
                out.add(value)
            elif key in {"menu", "assets", "risk_assets", "defensive"} and isinstance(value, list):
                out.update(str(item) for item in value)
            elif key == "weights" and isinstance(value, dict):
                out.update(str(item) for item in value)
            elif key in {"cash_filter", "cash_asset", "growth_asset", "bond_asset"}:
                if isinstance(value, str):
                    out.add(value)
            elif key == "substitutions" and isinstance(value, dict):
                out.update(str(item) for item in value.values())
            else:
                _walk_symbols(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk_symbols(item, out)


def manifest_symbols(manifest: dict[str, Any]) -> list[str]:
    out: set[str] = {manifest["cash_asset"], manifest["risk_free_asset"]}
    out.update(manifest["benchmarks"])
    for candidate in manifest["candidates"]:
        _walk_symbols(candidate["spec"], out)
    for spec in REGRESSION_SPECS.values():
        _walk_symbols(spec, out)
    return sorted(out)


# ----------------------------------------------------------------- indicator cache


class Panel:
    """Daily close/open panel plus every indicator the manifest can reference."""

    def __init__(self, close: pd.DataFrame, open_: pd.DataFrame, cash: str) -> None:
        self.close = close
        self.open = open_
        self.cash = cash
        self.index = close.index
        self.n = len(self.index)
        self.columns = list(close.columns)
        self.col_i = {s: i for i, s in enumerate(self.columns)}
        prev_c = close.shift(1)
        self.leg_open = (open_ / prev_c - 1.0).fillna(0.0).to_numpy(dtype=float)
        self.leg_close = (close / open_ - 1.0).fillna(0.0).to_numpy(dtype=float)
        self.total = (close / prev_c - 1.0).fillna(0.0).to_numpy(dtype=float)
        self._sma: dict[tuple[str, int], np.ndarray] = {}
        self._rsi: dict[tuple[str, int], np.ndarray] = {}
        self._mom: dict[Any, np.ndarray] = {}
        self._monthly = self._month_end_frame()
        self._m13612w = self._daily_align(self._compute_13612w())
        self._rel13 = self._daily_align(self._compute_rel13())

    # -- monthly helpers ----------------------------------------------------
    def _month_end_frame(self) -> pd.DataFrame:
        keys = self.index.to_period("M")
        last = pd.Series(self.index, index=self.index).groupby(keys).transform("max")
        mask = pd.Series(self.index, index=self.index) == last
        frame = self.close.loc[mask.to_numpy()]
        frame.index = frame.index.to_period("M")
        return frame

    def _compute_13612w(self) -> pd.DataFrame:
        p = self._monthly
        return (
            12.0 * (p / p.shift(1) - 1.0)
            + 4.0 * (p / p.shift(3) - 1.0)
            + 2.0 * (p / p.shift(6) - 1.0)
            + (p / p.shift(12) - 1.0)
        )

    def _compute_rel13(self) -> pd.DataFrame:
        p = self._monthly
        return p / p.rolling(13, min_periods=13).mean()

    def _daily_align(self, monthly: pd.DataFrame) -> np.ndarray:
        """Month-end feature, visible from the month-end session onwards."""
        stamped = monthly.copy()
        stamped.index = pd.DatetimeIndex(
            [self.close.loc[self.close.index.to_period("M") == p].index[-1] for p in monthly.index]
        )
        return stamped.reindex(self.index).ffill().to_numpy(dtype=float)

    # -- indicator accessors ------------------------------------------------
    def sma_above(self, asset: str, window: int) -> np.ndarray:
        key = (asset, window)
        if key not in self._sma:
            px = self.close[asset]
            ma = px.rolling(window, min_periods=window).mean()
            self._sma[key] = (px > ma).to_numpy(dtype=bool) & ma.notna().to_numpy()
        return self._sma[key]

    def rsi(self, asset: str, window: int) -> np.ndarray:
        key = (asset, window)
        if key not in self._rsi:
            self._rsi[key] = _wilder_rsi(self.close[asset], window).to_numpy(dtype=float)
        return self._rsi[key]

    def momentum(self, lookback: Any) -> np.ndarray:
        key = str(lookback)
        if key not in self._mom:
            if lookback == "blend":
                parts = [self.close.pct_change(k, fill_method=None) for k in (21, 63, 126, 252)]
                frame = sum(parts) / len(parts)
            else:
                frame = self.close.pct_change(int(lookback), fill_method=None)
            self._mom[key] = frame.to_numpy(dtype=float)
        return self._mom[key]

    def m13612w(self) -> np.ndarray:
        return self._m13612w

    def rel13(self) -> np.ndarray:
        return self._rel13


def _wilder_rsi(close: pd.Series, window: int) -> pd.Series:
    """Identical to run_h20260922_04_rsi_branch.wilder_rsi."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return rsi.where(avg_loss.notna() & (avg_loss > 0), 100.0).where(avg_gain.notna())


# --------------------------------------------------------------------- calendars


def signal_positions(index: pd.DatetimeIndex, rebalance: str) -> list[int]:
    if rebalance == "daily":
        return list(range(len(index)))
    period = {"weekly": "W", "monthly": "M", "bimonthly": "M", "quarterly": "Q"}[rebalance]
    stamps = pd.Series(index, index=index)
    last = stamps.groupby(index.to_period(period)).transform("max")
    flags = (stamps == last).to_numpy()
    positions = [i for i, flag in enumerate(flags) if flag]
    if rebalance == "bimonthly":
        positions = positions[::2]
    return positions


# ------------------------------------------------------------- spec interpreter


class Interpreter:
    """Evaluate one manifest ``spec`` node into a target book at a signal date."""

    def __init__(
        self,
        panel: Panel,
        *,
        shift: int = 0,
        pick_rng: np.random.Generator | None = None,
    ) -> None:
        self.panel = panel
        self.shift = shift
        self.pick_rng = pick_rng

    def _ref(self, i: int) -> int:
        return max(0, i - self.shift)

    def book(self, node: Any, i: int) -> dict[str, float]:
        out: dict[str, float] = {}
        self._eval(node, i, 1.0, out)
        total = sum(out.values())
        if total <= 0:
            return {self.panel.cash: 1.0}
        return out

    # -- node dispatch ------------------------------------------------------
    def _eval(self, node: Any, i: int, weight: float, out: dict[str, float]) -> None:
        if isinstance(node, str):
            out[node] = out.get(node, 0.0) + weight
            return
        if not isinstance(node, dict) or not node:
            out[self.panel.cash] = out.get(self.panel.cash, 0.0) + weight
            return
        kind = next(iter(node))
        handler = getattr(self, f"_node_{kind}", None)
        if handler is None:
            raise ValueError(f"unknown spec primitive: {kind}")
        handler(node[kind], i, weight, out)

    def _node_asset(self, spec: str, i: int, weight: float, out: dict[str, float]) -> None:
        out[spec] = out.get(spec, 0.0) + weight

    def _node_weights(self, spec: dict, i: int, weight: float, out: dict[str, float]) -> None:
        for symbol, share in spec.items():
            out[symbol] = out.get(symbol, 0.0) + weight * float(share)

    def _node_blend(self, spec: list, i: int, weight: float, out: dict[str, float]) -> None:
        for leg in spec:
            self._eval(leg["node"], i, weight * float(leg["weight"]), out)

    def _node_gate(self, spec: dict, i: int, weight: float, out: dict[str, float]) -> None:
        ref = self._ref(i)
        kind = spec["type"]
        asset = spec["asset"]
        if kind == "sma":
            value = bool(self.panel.sma_above(asset, int(spec["window"]))[ref])
            hit = value if spec.get("op", "above") == "above" else not value
        elif kind == "rsi":
            raw = self.panel.rsi(asset, int(spec["window"]))[ref]
            if not np.isfinite(raw):
                hit = False
            elif spec.get("op", "above") == "above":
                hit = raw > float(spec["threshold"])
            else:
                hit = raw < float(spec["threshold"])
        else:  # pragma: no cover - the manifest only uses sma and rsi gates
            raise ValueError(f"unsupported gate type {kind}")
        branch = spec["on_true"] if hit else spec["on_false"]
        self._eval(branch, i, weight, out)

    def _select(self, scores: np.ndarray, menu: list[str], top_n: int) -> list[str]:
        idx = [self.panel.col_i[s] for s in menu]
        values = scores[idx]
        live = [(s, v) for s, v in zip(menu, values, strict=True) if np.isfinite(v)]
        if not live:
            return []
        if self.pick_rng is not None:
            names = [s for s, _ in live]
            k = min(top_n, len(names))
            return [str(x) for x in self.pick_rng.choice(names, size=k, replace=False)]
        live.sort(key=lambda row: row[1], reverse=True)
        return [s for s, _ in live[:top_n]]

    def _node_rank(self, spec: dict, i: int, weight: float, out: dict[str, float]) -> None:
        ref = self._ref(i)
        menu = list(spec["menu"])
        method = spec.get("method", "momentum")
        if method == "rel13":
            scores = self.panel.rel13()[ref]
        else:
            scores = self.panel.momentum(spec.get("lookback", 21))[ref]
        chosen = self._select(scores, menu, int(spec["top_n"]))
        cash_filter = spec.get("cash_filter")
        if cash_filter:
            benchmark = scores[self.panel.col_i[cash_filter]]
            if np.isfinite(benchmark):
                chosen = [s for s in chosen if scores[self.panel.col_i[s]] > benchmark]
        if not chosen:
            out[self.panel.cash] = out.get(self.panel.cash, 0.0) + weight
            return
        # "park": an absolute-momentum reject leaves that slice in cash, which is what
        # BAA publishes ("instead place that portion of the portfolio in cash").
        # "renormalize" (default): survivors share the full slice, which is the frozen
        # H-20260918-05 convention the live S1/S2/S3 sleeves were measured under.
        if spec.get("cash_policy", "renormalize") == "park":
            slots = int(spec["top_n"])
        else:
            slots = len(chosen)
        share = weight / slots
        for symbol in chosen:
            out[symbol] = out.get(symbol, 0.0) + share
        if len(chosen) < slots:
            out[self.panel.cash] = out.get(self.panel.cash, 0.0) + share * (slots - len(chosen))

    def _node_canary(self, spec: dict, i: int, weight: float, out: dict[str, float]) -> None:
        ref = self._ref(i)
        scores = self.panel.m13612w()[ref]
        values = [scores[self.panel.col_i[s]] for s in spec["assets"]]
        if any(not np.isfinite(v) for v in values):
            out[self.panel.cash] = out.get(self.panel.cash, 0.0) + weight
            return
        branch = spec["on_ok"] if all(v > 0 for v in values) else spec["on_fail"]
        self._eval(branch, i, weight, out)

    def _node_trend_basket(self, spec: dict, i: int, weight: float, out: dict[str, float]) -> None:
        ref = self._ref(i)
        menu = list(spec["menu"])
        share = weight / len(menu)
        cash = spec.get("cash_asset", self.panel.cash)
        if spec.get("method", "sma") == "sma":
            flags = {s: bool(self.panel.sma_above(s, int(spec["window"]))[ref]) for s in menu}
        else:
            scores = self.panel.momentum(int(spec["window"]))[ref]
            flags = {
                s: bool(
                    np.isfinite(scores[self.panel.col_i[s]]) and scores[self.panel.col_i[s]] > 0.0
                )
                for s in menu
            }
        for symbol in menu:
            target = symbol if flags[symbol] else cash
            out[target] = out.get(target, 0.0) + share

    def _node_accel_dual_momentum(
        self, spec: dict, i: int, weight: float, out: dict[str, float]
    ) -> None:
        ref = self._ref(i)
        subs = spec.get("substitutions", {})
        lookbacks = [int(k) for k in spec["lookbacks"]]
        scores: dict[str, float] = {}
        for symbol in spec["risk_assets"]:
            parts = [self.panel.momentum(lb)[ref][self.panel.col_i[symbol]] for lb in lookbacks]
            scores[symbol] = float(np.mean(parts)) if all(np.isfinite(parts)) else float("nan")
        live = {s: v for s, v in scores.items() if np.isfinite(v)}
        if live:
            best = max(live, key=lambda s: live[s])
            if live[best] > 0.0:
                target = subs.get(best, best)
                out[target] = out.get(target, 0.0) + weight
                return
        defensive = self.panel.momentum(int(spec.get("defensive_lookback", 21)))[ref]
        options = [
            (s, defensive[self.panel.col_i[s]])
            for s in spec["defensive"]
            if np.isfinite(defensive[self.panel.col_i[s]])
        ]
        if not options:
            out[self.panel.cash] = out.get(self.panel.cash, 0.0) + weight
            return
        pick = max(options, key=lambda row: row[1])[0]
        target = subs.get(pick, pick)
        out[target] = out.get(target, 0.0) + weight


# ----------------------------------------------------------------- simulation


def simulate_book(
    panel: Panel,
    spec: dict[str, Any],
    cost_bps: float,
    *,
    shift: int = 0,
    pick_rng: np.random.Generator | None = None,
    drift: bool = False,
) -> tuple[pd.Series, pd.Series]:
    """Frozen convention: signal on the close of t, book effective at the open of t+1."""
    interp = Interpreter(panel, shift=shift, pick_rng=pick_rng)
    positions = signal_positions(panel.index, spec["rebalance"])
    n = panel.n
    ncol = len(panel.columns)
    changes: dict[int, np.ndarray] = {}
    for i in positions:
        if i + 1 >= n:
            continue
        book = interp.book(spec["root"], i)
        vec = np.zeros(ncol)
        for symbol, share in book.items():
            vec[panel.col_i[symbol]] += share
        changes[i + 1] = vec

    rets = np.zeros(n)
    turns = np.zeros(n)
    cash_vec = np.zeros(ncol)
    cash_vec[panel.col_i[panel.cash]] = 1.0
    held = cash_vec.copy()
    w_prev = cash_vec.copy()
    for i in range(n):
        if drift:
            grown = held * (1.0 + panel.leg_open[i])
            total = grown.sum()
            at_open = grown / total if total > 0 else held
            if i in changes:
                target = changes[i]
                turnover = float(np.abs(target - at_open).sum())
                at_open = target
            else:
                turnover = 0.0
            rets[i] = float(w_prev @ panel.leg_open[i] + at_open @ panel.leg_close[i])
            rets[i] -= turnover * cost_bps / 10_000.0
            turns[i] = turnover
            after = at_open * (1.0 + panel.leg_close[i])
            total = after.sum()
            held = after / total if total > 0 else at_open
            w_prev = at_open
        else:
            w = changes.get(i, w_prev)
            turnover = float(np.abs(w - w_prev).sum())
            rets[i] = float(w_prev @ panel.leg_open[i] + w @ panel.leg_close[i])
            rets[i] -= turnover * cost_bps / 10_000.0
            turns[i] = turnover
            w_prev = w
    return pd.Series(rets, index=panel.index), pd.Series(turns, index=panel.index)


def simulate_fixed_weights(
    panel: Panel, spec: dict[str, Any], cost_bps: float, *, weights: dict[str, float] | None = None
) -> tuple[pd.Series, pd.Series]:
    node = dict(spec["root"])
    if weights is not None:
        node = {"weights": weights}
    return simulate_book(
        panel, {"rebalance": spec["rebalance"], "root": node}, cost_bps, drift=True
    )


def simulate_signal_growth(
    panel: Panel, spec: dict[str, Any], cost_bps: float, *, rng: np.random.Generator | None = None
) -> tuple[pd.Series, pd.Series]:
    """9-sig: a signal line that must grow `rate` per rebalance period.

    Above the line, the excess in the growth asset is sold into bonds; below it,
    bonds above the floor are moved back into the growth asset.
    """
    cfg = spec["root"]["signal_growth"]
    growth = cfg["growth_asset"]
    bond = cfg["bond_asset"]
    rate = float(cfg["rate"])
    floor = float(cfg["bond_floor"])
    start = float(cfg.get("initial_growth_weight", 0.6))
    if rng is not None:
        start = float(rng.uniform(0.2, 0.9))
        rate = float(rng.uniform(0.0, 0.2))
    positions = set(signal_positions(panel.index, spec["rebalance"]))
    gi, bi = panel.col_i[growth], panel.col_i[bond]
    n = panel.n
    ncol = len(panel.columns)
    rets = np.zeros(n)
    turns = np.zeros(n)
    held = np.zeros(ncol)
    held[panel.col_i[panel.cash]] = 1.0
    w_prev = held.copy()
    equity = 1.0
    signal_value: float | None = None
    armed = False
    for i in range(n):
        grown = held * (1.0 + panel.leg_open[i])
        total = grown.sum()
        at_open = grown / total if total > 0 else held
        turnover = 0.0
        if armed:
            target = np.zeros(ncol)
            desired = min(max(signal_value or 0.0, 0.0), equity * (1.0 - floor))
            target[gi] = desired / equity if equity > 0 else start
            target[bi] = 1.0 - target[gi]
            turnover = float(np.abs(target - at_open).sum())
            at_open = target
            armed = False
        if i - 1 in positions and i < n:
            armed = True
            if signal_value is None:
                signal_value = start * equity
            else:
                signal_value *= 1.0 + rate
        rets[i] = float(w_prev @ panel.leg_open[i] + at_open @ panel.leg_close[i])
        rets[i] -= turnover * cost_bps / 10_000.0
        turns[i] = turnover
        equity *= 1.0 + rets[i]
        after = at_open * (1.0 + panel.leg_close[i])
        total = after.sum()
        held = after / total if total > 0 else at_open
        w_prev = at_open
    return pd.Series(rets, index=panel.index), pd.Series(turns, index=panel.index)


def simulate_overnight(
    panel: Panel,
    spec: dict[str, Any],
    cost_bps: float,
    *,
    mask_override: np.ndarray | None = None,
) -> tuple[pd.Series, pd.Series, np.ndarray]:
    """Buy at the close of t, sell at the open of t+1; flat during the session."""
    cfg = spec["overnight"]
    asset = cfg["asset"]
    skip = set(int(x) for x in cfg.get("skip_weekdays", []))
    ai = panel.col_i[asset]
    n = panel.n
    # hold[i] is True when the book is long `asset` from the close of i-1 to the open of i
    hold = np.zeros(n, dtype=bool)
    if mask_override is not None:
        hold = mask_override.astype(bool)
    else:
        weekday = panel.index.weekday.to_numpy()
        for i in range(1, n):
            if int(weekday[i - 1]) not in skip:
                hold[i] = True
    rets = np.zeros(n)
    turns = np.zeros(n)
    for i in range(n):
        if hold[i]:
            rets[i] = float(panel.leg_open[i][ai]) - 2.0 * cost_bps / 10_000.0
            turns[i] = 2.0
    return pd.Series(rets, index=panel.index), pd.Series(turns, index=panel.index), hold


def run_candidate(
    panel: Panel,
    candidate: dict[str, Any],
    cost_bps: float,
    *,
    shift: int = 0,
    pick_rng: np.random.Generator | None = None,
    weights: dict[str, float] | None = None,
    growth_rng: np.random.Generator | None = None,
    night_mask: np.ndarray | None = None,
) -> tuple[pd.Series, pd.Series]:
    spec = candidate["spec"]
    if "overnight" in spec:
        rets, turns, _ = simulate_overnight(panel, spec, cost_bps, mask_override=night_mask)
        return rets, turns
    root = spec["root"]
    if "signal_growth" in root:
        return simulate_signal_growth(panel, spec, cost_bps, rng=growth_rng)
    if "weights" in root:
        return simulate_fixed_weights(panel, spec, cost_bps, weights=weights)
    return simulate_book(panel, spec, cost_bps, shift=shift, pick_rng=pick_rng)


# -------------------------------------------------------------------- reporting


def flat(prefix: str, metrics: base.Metrics) -> dict[str, float]:
    return {f"{prefix}_{k}": v for k, v in asdict(metrics).items()}


def vol_matched_excess(ret: pd.Series, bench: pd.Series, window: str) -> float:
    a, b = base.WINDOWS[window]
    r = ret.loc[(ret.index >= a) & (ret.index <= b)]
    m = bench.loc[(bench.index >= a) & (bench.index <= b)]
    rv, bv = r.std(ddof=1), m.std(ddof=1)
    if not rv or not np.isfinite(rv) or not bv:
        return float("nan")
    years = len(r) / 252.0
    scaled = float((1.0 + r * (bv / rv)).prod() ** (1.0 / years) - 1.0)
    return scaled - float((1.0 + m).prod() ** (1.0 / years) - 1.0)


REGRESSION_REFERENCE = {
    "S1_rot_A2_sector_lb252_top2_weekly": ("A2_sector", "252", 2, "weekly"),
    "S2_rot_A3_growth_lbblend_top2_monthly": ("A3_growth", "blend", 2, "monthly"),
    "S3_rot_A4_levered_lb63_top2_monthly": ("A4_levered", "63", 2, "monthly"),
}


def regression_check(panel: Panel, rf: pd.Series, tolerance: float = 0.01) -> list[dict]:
    """Two comparisons, only the first of which gates the run.

    1. Engine vs `run_h20260918_05_recent_menu.rotation_cell` recomputed today on the
       same panel. This is the implementation identity the brief asks for and it is
       the pass/fail gate.
    2. Engine vs the numbers printed in H-20260918-05 section 5. Those were computed
       on 2026-09-18; any residual difference is archive drift since that date, not
       an engine difference, so it is reported rather than enforced.
    """
    rows = []
    for name, spec in REGRESSION_SPECS.items():
        ret, turns = simulate_book(panel, spec, base.COST_BPS_PRIMARY)
        wm = base.window_metrics(ret, rf, turns)
        menu, lookback, top_n, rebalance = REGRESSION_REFERENCE[name]
        ref_ret, ref_turns = base.rotation_cell(
            panel.close, panel.open, menu, lookback, top_n, rebalance, base.COST_BPS_PRIMARY
        )
        ref_wm = base.window_metrics(ref_ret, rf, ref_turns)
        row = {"cell": name}
        worst_ref = 0.0
        worst_card = 0.0
        for window, expected in REGRESSION_TARGETS[name].items():
            actual = float(wm[window].sharpe)
            reference = float(ref_wm[window].sharpe)
            row[f"{window}_engine"] = round(actual, 4)
            row[f"{window}_reference_impl"] = round(reference, 4)
            row[f"{window}_card"] = expected
            row[f"{window}_delta_vs_reference"] = round(actual - reference, 4)
            row[f"{window}_delta_vs_card"] = round(actual - expected, 4)
            worst_ref = max(worst_ref, abs(actual - reference))
            worst_card = max(worst_card, abs(actual - expected))
        row["worst_abs_delta_vs_reference"] = round(worst_ref, 4)
        row["worst_abs_delta_vs_card"] = round(worst_card, 4)
        row["pass"] = bool(worst_ref <= tolerance)
        rows.append(row)
    return rows


def _pct(x: Any) -> str:
    try:
        value = float(x)
    except (TypeError, ValueError):
        return "n/a"
    return "n/a" if not np.isfinite(value) else f"{value * 100:.1f}%"


def _num(x: Any) -> str:
    try:
        value = float(x)
    except (TypeError, ValueError):
        return "n/a"
    return "n/a" if not np.isfinite(value) else f"{value:.2f}"


def write_report(summary: pd.DataFrame, benchmarks: pd.DataFrame, manifest: dict) -> None:
    mark = {True: "yes", False: "no"}
    lines: list[str] = []
    lines.append("# Giants sweep -- giants_sweep_20260922")
    lines.append("")
    lines.append(
        "Engine `scripts/run_giants_sweep.py`, manifest `config/giants_sweep/manifest.yaml`. "
        f"{len(summary)} preregistered cells from families "
        f"{', '.join(sorted(summary['family'].unique()))}. Windows, costs, fills, placebos and "
        "gate thresholds are the frozen ones from H-20260918-05 and H-20260922-02; nothing was "
        "tuned here."
    )
    lines.append("")
    lines.append("## Windows and protocol")
    lines.append("")
    for name, (a, b) in base.WINDOWS.items():
        lines.append(f"- `{name}` {a} .. {b}")
    lines.append(
        "- costs `sum(|delta w|) * bps` charged on the execution session, 10 bp primary / "
        "20 bp stress; signal on the close, fill at the next session's open."
    )
    lines.append("")
    lines.append("## Benchmarks (buy and hold, no costs)")
    lines.append("")
    lines.append(
        "| benchmark | anchor CAGR | anchor max DD | anchor Sharpe | holdout Sharpe | "
        "select Sharpe |"
    )
    lines.append("|---|---|---|---|---|---|")
    for _, r in benchmarks.iterrows():
        lines.append(
            f"| {r['cell_id']} | {_pct(r['anchor_cagr'])} | {_pct(r['anchor_max_dd'])} | "
            f"{_num(r['anchor_sharpe'])} | {_num(r['holdout_sharpe'])} | "
            f"{_num(r['select_sharpe'])} |"
        )
    lines.append("")

    groups = [
        ("All gates pass", summary.loc[summary["all_gates"]]),
        (
            "Partial pass",
            summary.loc[
                (~summary["all_gates"])
                & (summary[["G1", "G1_alt", "G2", "G3", "G4"]].sum(axis=1) > 0)
            ],
        ),
        (
            "Fail",
            summary.loc[
                (~summary["all_gates"])
                & (summary[["G1", "G1_alt", "G2", "G3", "G4"]].sum(axis=1) == 0)
            ],
        ),
    ]
    for title, frame in groups:
        ranked = frame.sort_values("select_sharpe", ascending=False).head(20)
        lines.append(f"## {title} ({len(frame)} cells, top {len(ranked)} shown)")
        lines.append("")
        if ranked.empty:
            lines.append("None.")
            lines.append("")
            continue
        lines.append(
            "| cell | family | anchor CAGR | anchor DD | anchor Sh | holdout Sh | select Sh | "
            "turnover/yr | placebo beat | 20bp anchor CAGR | G1 | G1' | G2 | G3 | G4 | G5 |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for _, r in ranked.iterrows():
            lines.append(
                f"| `{r['cell_id']}` | {r['family']} | {_pct(r['anchor_cagr'])} | "
                f"{_pct(r['anchor_max_dd'])} | {_num(r['anchor_sharpe'])} | "
                f"{_num(r['holdout_sharpe'])} | {_num(r['select_sharpe'])} | "
                f"{_num(r['anchor_turnover_yr'])} | {_pct(r['placebo_beat_frac_worst'])} | "
                f"{_pct(r['stress20_anchor_cagr'])} | {mark[bool(r['G1'])]} | "
                f"{mark[bool(r['G1_alt'])]} | {mark[bool(r['G2'])]} | {mark[bool(r['G3'])]} | "
                f"{mark[bool(r['G4'])]} | {mark[bool(r['G5'])]} |"
            )
        lines.append("")

    lines.append("## Gate definitions (unchanged from H-20260922-02)")
    lines.append("")
    lines.append("- G1: anchor CAGR >= 50% and anchor max drawdown >= -35%")
    lines.append("- G1': anchor Sharpe >= 2.0 and anchor CAGR >= 30%")
    lines.append("- G2: holdout Sharpe >= 1.0 and holdout CAGR > 0")
    lines.append(
        "- G3: every declared placebo beats the true cell on select Sharpe <= 10% of seeds"
    )
    lines.append("- G4: G1 or G1' still holds at 20 bp per side")
    lines.append("- G5: long-only spot US ETFs on the existing Alpaca daily cron")
    lines.append("")
    lines.append("## Vol-matched excess over the benchmark family (anchor window)")
    lines.append("")
    lines.append("| cell | vs SPY | vs MTUM | vs SPMO | vs QQQ | vs TQQQ |")
    lines.append("|---|---|---|---|---|---|")
    for _, r in summary.sort_values("anchor_sharpe", ascending=False).head(20).iterrows():
        cells = " | ".join(
            _pct(r[f"vol_matched_excess_vs_{b}_anchor"]) for b in manifest["benchmarks"]
        )
        lines.append(f"| `{r['cell_id']}` | {cells} |")
    lines.append("")
    lines.append("## Caveats a reader must carry")
    lines.append("")
    reg = json.loads((OUT_DIR / "regression-check.json").read_text(encoding="utf-8"))
    worst_ref = max(r["worst_abs_delta_vs_reference"] for r in reg)
    worst_card = max(r["worst_abs_delta_vs_card"] for r in reg)
    lines.append(
        f"- Engine regression: the three live sleeves reproduce "
        f"`run_h20260918_05_recent_menu.rotation_cell` to {worst_ref:.4f} Sharpe on the same "
        f"panel. Against H-20260918-05 section 5 as printed the worst gap is {worst_card:.4f} "
        "(S1's holdout Sharpe, 2.18 today vs 2.22 in the card); the reference implementation "
        "reproduces 2.18 today too, so that is SIP archive drift since 2026-09-18."
    )
    lines.append(
        "- The F7 overnight cells are charged the frozen 10/20 bp per side, which is far "
        "stricter than the source paper's unstated cost assumption. Their failure is a cost "
        "verdict, not a signal verdict: two round trips per night at 10 bp is about 20 bp a "
        "night, and the protocol was not relaxed for one family."
    )
    lines.append(
        "- For monthly cells a 1-20 session calendar shift usually lands on the previous "
        "month-end feature, so the shift placebo tests 'last month's signal' rather than a "
        "fine-grained timing jitter. A beat fraction near 1.0 there means the month of the "
        "signal does not matter, which is still a real negative result, but it is a coarser "
        "control than the daily cells get."
    )
    lines.append(
        "- The 9-sig cell implements the published quarterly signal line and 10% bond floor "
        "only; the thread's later discretionary overrides are not modelled."
    )
    lines.append(
        "- Every window here is a bull market. No cell was tested in a bear regime, and the "
        "absolute-momentum and canary defences barely fired."
    )
    lines.append("")
    (OUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# -------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regress", action="store_true", help="only run the S1/S2/S3 regression")
    ap.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    args = ap.parse_args(argv)

    manifest = load_manifest(args.manifest)
    symbols = manifest_symbols(manifest)
    close, open_ = base.load_panel(symbols)
    missing = [s for s in symbols if s not in close.columns]
    if missing:
        raise SystemExit(f"missing symbols in the SIP archive: {missing}")
    panel = Panel(close, open_, manifest["cash_asset"])
    rf = close[manifest["risk_free_asset"]].pct_change(fill_method=None).fillna(0.0)
    print(
        f"panel {panel.n} sessions x {len(panel.columns)} symbols "
        f"{panel.index[0].date()}..{panel.index[-1].date()}",
        flush=True,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    reg = regression_check(panel, rf)
    (OUT_DIR / "regression-check.json").write_text(json.dumps(reg, indent=2), encoding="utf-8")
    for row in reg:
        print(
            f"regression {row['cell']}: vs reference impl "
            f"{row['worst_abs_delta_vs_reference']}, vs card "
            f"{row['worst_abs_delta_vs_card']} -> {'PASS' if row['pass'] else 'FAIL'}",
            flush=True,
        )
    if not all(row["pass"] for row in reg):
        raise SystemExit("regression check failed; refusing to run the sweep")
    if args.regress:
        return 0

    seeds = manifest["placebo_seeds"]
    rows: list[dict] = []
    placebo_rows: list[dict] = []
    equity: dict[str, pd.Series] = {}

    for candidate in manifest["candidates"]:
        cid = candidate["id"]
        record: dict[str, Any] = {
            "cell_id": cid,
            "family": candidate["family"],
            "source_url": candidate["source_url"],
            "params": json.dumps(candidate["spec"], sort_keys=True, default=str),
            "reported_annualized": candidate["reported"].get("annualized"),
            "reported_max_drawdown": candidate["reported"].get("max_drawdown"),
            "reported_sharpe": candidate["reported"].get("sharpe"),
            "reported_period": candidate["reported"].get("period"),
            "placebos": ",".join(candidate["placebos"]),
        }
        for tag, cost in (("", base.COST_BPS_PRIMARY), ("stress20_", base.COST_BPS_STRESS)):
            ret, turns = run_candidate(panel, candidate, cost)
            wm = base.window_metrics(ret, rf, turns)
            for window, metrics in wm.items():
                for key, value in asdict(metrics).items():
                    record[f"{tag}{window}_{key}"] = value
            if tag == "":
                equity[cid] = ret
        rows.append(record)
        print(
            f"cell {cid}: anchor cagr {_pct(record['anchor_cagr'])} "
            f"sharpe {_num(record['anchor_sharpe'])}",
            flush=True,
        )

        true_select = record["select_sharpe"]
        for kind in candidate["placebos"]:
            count = seeds["calendar_shift"] if kind == "calendar_shift" else 60
            for seed in range(count):
                rng = np.random.default_rng(seed)
                kwargs: dict[str, Any] = {}
                if kind == "calendar_shift":
                    kwargs["shift"] = int(rng.integers(1, 21))
                elif kind == "random_pick":
                    kwargs["pick_rng"] = rng
                elif kind == "random_weights":
                    node = candidate["spec"]["root"]
                    if "weights" in node:
                        names = list(node["weights"])
                        draw = rng.dirichlet(np.ones(len(names)))
                        kwargs["weights"] = dict(zip(names, draw, strict=True))
                    else:
                        kwargs["growth_rng"] = rng
                elif kind == "random_nights":
                    _, _, mask = simulate_overnight(panel, candidate["spec"], base.COST_BPS_PRIMARY)
                    picks = rng.choice(panel.n, size=int(mask.sum()), replace=False)
                    new_mask = np.zeros(panel.n, dtype=bool)
                    new_mask[picks] = True
                    new_mask[0] = False
                    kwargs["night_mask"] = new_mask
                pret, pturns = run_candidate(panel, candidate, base.COST_BPS_PRIMARY, **kwargs)
                pwm = base.window_metrics(pret, rf, pturns)
                placebo_rows.append(
                    {
                        "cell_id": cid,
                        "family": candidate["family"],
                        "placebo": kind,
                        "seed": seed,
                        "select_sharpe": pwm["select"].sharpe,
                        "holdout_sharpe": pwm["holdout"].sharpe,
                        "anchor_sharpe": pwm["anchor"].sharpe,
                        "anchor_cagr": pwm["anchor"].cagr,
                        "anchor_max_dd": pwm["anchor"].max_dd,
                    }
                )
        print(f"  placebos done for {cid} ({true_select:.2f} select Sharpe)", flush=True)

    summary = pd.DataFrame(rows)
    placebo = pd.DataFrame(placebo_rows)

    bench_rows = []
    for symbol in manifest["benchmarks"]:
        ret, turns = base.buy_hold(close, open_, symbol)
        wm = base.window_metrics(ret, rf, turns)
        row = {"cell_id": f"bench_{symbol}"}
        for window, metrics in wm.items():
            row.update(flat(window, metrics))
        bench_rows.append(row)
        equity[f"bench_{symbol}"] = ret
    benchmarks = pd.DataFrame(bench_rows)

    # gates and benchmark-relative columns
    gate_cols: list[dict] = []
    for _, r in summary.iterrows():
        cid = r["cell_id"]
        pb = placebo.loc[placebo["cell_id"] == cid]
        beats = {}
        for kind in str(r["placebos"]).split(","):
            sub = pb.loc[pb["placebo"] == kind]
            beats[kind] = (
                float((sub["select_sharpe"] >= r["select_sharpe"]).mean()) if len(sub) else np.nan
            )
        worst = float(np.nanmax(list(beats.values()))) if beats else np.nan
        g1 = bool(r["anchor_cagr"] >= GATE_G1_CAGR and r["anchor_max_dd"] >= GATE_G1_MAXDD)
        g1alt = bool(
            r["anchor_sharpe"] >= GATE_G1ALT_SHARPE and r["anchor_cagr"] >= GATE_G1ALT_CAGR
        )
        g2 = bool(r["holdout_sharpe"] >= GATE_G2_SHARPE and r["holdout_cagr"] > 0)
        g3 = bool(np.isfinite(worst) and worst <= GATE_G3_PLACEBO)
        g4 = bool(
            (
                r["stress20_anchor_cagr"] >= GATE_G1_CAGR
                and r["stress20_anchor_max_dd"] >= GATE_G1_MAXDD
            )
            or (
                r["stress20_anchor_sharpe"] >= GATE_G1ALT_SHARPE
                and r["stress20_anchor_cagr"] >= GATE_G1ALT_CAGR
            )
        )
        entry = {
            "cell_id": cid,
            "placebo_beat_frac_worst": worst,
            "G1": g1,
            "G1_alt": g1alt,
            "G2": g2,
            "G3": g3,
            "G4": g4,
            "G5": True,
            "all_gates": bool((g1 or g1alt) and g2 and g3 and g4),
        }
        for kind, value in beats.items():
            entry[f"placebo_beat_frac_{kind}"] = value
        for symbol in manifest["benchmarks"]:
            entry[f"vol_matched_excess_vs_{symbol}_anchor"] = vol_matched_excess(
                equity[cid], equity[f"bench_{symbol}"], "anchor"
            )
        gate_cols.append(entry)
    summary = summary.merge(pd.DataFrame(gate_cols), on="cell_id", how="left")

    summary.to_parquet(OUT_DIR / "summary.parquet", index=False)
    placebo.to_parquet(OUT_DIR / "placebo.parquet", index=False)
    benchmarks.to_parquet(OUT_DIR / "benchmarks.parquet", index=False)
    pd.DataFrame({k: (1.0 + v).cumprod() for k, v in equity.items()}).to_parquet(
        OUT_DIR / "equity.parquet"
    )
    write_report(summary, benchmarks, manifest)
    print(
        f"cells={len(summary)} all_gates={int(summary['all_gates'].sum())} "
        f"placebo_rows={len(placebo)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
