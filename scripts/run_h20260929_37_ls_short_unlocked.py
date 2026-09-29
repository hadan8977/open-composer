"""T-20260929-37: low-turnover long/short candidates unlocked by short selling.

Three directions, 16 preregistered candidates (candidate-manifest.json):

* A  dual-class share pairs: z-score of log(P_a / P_b) vs its own rolling mean,
  long the cheaper class, short the richer class, dollar-neutral per pair.
* B  ETF crash -> constituent laggards: after an ETF closes in the worst 10% of
  its trailing-252 day returns, long the k biggest laggards among a fixed list
  of 2016 top-10 holdings and short the ETF, hold 5 or 10 sessions.
* C  sector SPDR intramonth momentum (Quantpedia): month-end 252d ranking,
  D+1 momentum, D+2/D+3 reversed, D-10..D-5 momentum; long-short or long top-k
  vs short SPY; plus a plain monthly ablation.

`scripts/screen_lane.py` cannot hold shorts (`weights_frame` keeps weights > 0),
so this script reuses the lane's frozen pieces unedited (panel loader, windows,
offset convention, metrics, S3 incumbent, K2 machinery, DSR) and adds signed
weight builders, per-symbol costs (5 bp + half Abdi-Ranaldo spread, doubled for
stress, frozen flat 10/20 bp) and ADV-tier borrow fees. Same book convention as
h20260929_51: cash-financed overlay, SHY weight 0, reported Sharpe is the
overlay's excess Sharpe, K2 sleeve = overlay + T-bill collateral return.

Judgement rule (frozen in cost-table.json before any result): the judged value
is the median over rebalance offsets (A, C ablation), entry delays 0/1/2 (B) or
the single calendar version (C composite) of the flat 10 bp after-borrow Sharpe.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import screen_lane as lane  # noqa: E402

from open_composer.research.campaign_statistics import deflated_sharpe_probability  # noqa: E402
from open_composer.research.features import price_hygiene as ph  # noqa: E402

base = lane.base
salvage = lane.salvage

ITER_ID = "h20260929_37_ls_short_unlocked"
OUT_DIR = ROOT / "reports/research/iterations" / ITER_ID
DAILY_GLOB = str(ROOT / "data" / "sip" / "daily" / "*" / "*.parquet")
BENCH = "SPY"

# ---- frozen contract (cost-table.json) -------------------------------------
K1_ANCHOR, K1_STRESS = 1.1882, 0.6447
S3_ANCHOR, S3_STRESS = 1.4853, 0.8059
K2_EDGE_MIN, K2_EDGE_STRONG = 0.05, 0.10
N_TRIALS = 22  # 16 candidates + 3 direction mirrors + 3 direction random placebos
N_PLACEBO_SEEDS = 20
FLAT_BPS = {"flat10": 10.0, "flat20": 20.0}
MAIN_FLAT_BPS, MAIN_SPREAD_W = 5.0, 0.5
STRESS_FLAT_BPS, STRESS_SPREAD_W = 10.0, 1.0
BORROW_HI, BORROW_LO, BORROW_ETF = 0.005, 0.02, 0.005
DV_HI, DV_MIN_SHORT = 50e6, 5e6
MIN_SHORT_CLOSE = 5.0
Z_ENTRY = 1.0
SPLIT_LOOKBACK_EXTRA = 1

# ---- universes --------------------------------------------------------------
# BRK.A/BRK.B excluded (BRK.A ~700k USD per share, no fractional short).
PAIRS: list[tuple[str, str]] = [
    ("GOOG", "GOOGL"),
    ("FOX", "FOXA"),
    ("NWS", "NWSA"),
    ("LEN", "LEN.B"),
    ("HEI", "HEI.A"),
    ("BF.A", "BF.B"),
    ("UA", "UAA"),
    ("Z", "ZG"),
    ("MKC", "MKC.V"),
    ("GEF", "GEF.B"),
]
# Fixed lists, NOT point-in-time constituents (survivor bias); approximate early-2016
# top-10 holdings written from memory of the funds, not from a holdings file.
CONSTITUENTS: dict[str, list[str]] = {
    "XLK": ["AAPL", "MSFT", "META", "GOOGL", "IBM", "INTC", "ORCL", "CSCO", "V", "MA"],
    "SOXX": ["INTC", "TXN", "QCOM", "NVDA", "AVGO", "MU", "ADI", "AMAT", "LRCX", "NXPI"],
}
SECTORS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
ETF_COLS = set(SECTORS) | {"SOXX", BENCH}


@dataclass(frozen=True)
class Cand:
    id: str
    direction: str  # "A", "B", "C"
    params: dict[str, Any] = field(default_factory=dict)


CANDIDATES: list[Cand] = [
    Cand("DC_M252_ALWAYS", "A", dict(freq="M", win=252, thr=0.0)),
    Cand("DC_M63_ALWAYS", "A", dict(freq="M", win=63, thr=0.0)),
    Cand("DC_M252_THR1", "A", dict(freq="M", win=252, thr=Z_ENTRY)),
    Cand("DC_M63_THR1", "A", dict(freq="M", win=63, thr=Z_ENTRY)),
    Cand("DC_W252_ALWAYS", "A", dict(freq="W", win=252, thr=0.0)),
    Cand("DC_W63_THR1", "A", dict(freq="W", win=63, thr=Z_ENTRY)),
    Cand("LL_XLK_K3_H5", "B", dict(etf="XLK", k=3, hold=5)),
    Cand("LL_XLK_K5_H5", "B", dict(etf="XLK", k=5, hold=5)),
    Cand("LL_XLK_K3_H10", "B", dict(etf="XLK", k=3, hold=10)),
    Cand("LL_XLK_K5_H10", "B", dict(etf="XLK", k=5, hold=10)),
    Cand("LL_SOXX_K3_H5", "B", dict(etf="SOXX", k=3, hold=5)),
    Cand("SIM_LS_K3", "C", dict(kind="LS", k=3)),
    Cand("SIM_LS_K2", "C", dict(kind="LS", k=2)),
    Cand("SIM_MN_K3", "C", dict(kind="MN", k=3)),
    Cand("SIM_MN_K2", "C", dict(kind="MN", k=2)),
    Cand("SIM_ABL_LS_K3_MONTHLY", "C", dict(kind="ABL", k=3)),
]
HEADLINE = {"A": "DC_M252_ALWAYS", "B": "LL_XLK_K3_H5", "C": "SIM_LS_K3"}


def all_symbols() -> list[str]:
    syms = {BENCH, *SECTORS, "SOXX", lane.CASH, lane.RF}
    for a, b in PAIRS:
        syms |= {a, b}
    for lst in CONSTITUENTS.values():
        syms |= set(lst)
    syms |= set(CONSTITUENTS)
    return sorted(syms)


# ---- data -------------------------------------------------------------------


@dataclass
class Panel:
    close: pd.DataFrame
    open: pd.DataFrame
    spread: pd.DataFrame  # trailing-21d Abdi-Ranaldo, lagged one session
    dv21: pd.DataFrame  # median close*volume of the prior 21 sessions
    split_close: pd.DataFrame  # bool: one-day close/close ratio is split-like
    split_gap: pd.DataFrame  # bool: open / prior close ratio is split-like
    hygiene: dict[str, Any]


def load_stock_panel(symbols: list[str], index: pd.DatetimeIndex) -> Panel:
    import duckdb

    from scripts import run_t20260929_32_gap_fade_ls as t32

    con = duckdb.connect()
    con.execute("SET memory_limit='900MB'")
    con.execute("SET threads=2")
    in_list = ",".join(f"'{s}'" for s in symbols)
    frame = con.execute(
        f"""
        SELECT symbol, timestamp::DATE AS d, open, high, low, close, volume, trade_count
        FROM read_parquet('{DAILY_GLOB}')
        WHERE symbol IN ({in_list}) AND timestamp::DATE >= DATE '{base.WARMUP_START}'
              AND timestamp::DATE <= DATE '{base.HOLD_END}'
              AND open > 0 AND high > 0 AND low > 0 AND close > 0
        ORDER BY symbol, d
        """
    ).df()
    con.close()
    ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
    frame = frame.loc[~ghost]

    def wide(col: str) -> pd.DataFrame:
        w = frame.pivot(index="d", columns="symbol", values=col).sort_index()
        w.index = pd.to_datetime(w.index)
        return w.reindex(index)

    close, open_ = wide("close"), wide("open")
    high, low, volume = wide("high"), wide("low"), wide("volume")
    close, open_, report = ph.sanitize_price_matrices(close, open_)
    assert open_ is not None
    high = high.where(close.notna())
    low = low.where(close.notna())
    spread = t32.spread_wide(close, high, low).shift(1)
    spread = spread.fillna(float(np.nanmedian(spread.to_numpy())))
    dv21 = (close * volume).shift(1).rolling(21, min_periods=21).median()
    prev_close = close.shift(1)
    split_close = pd.DataFrame(
        t32.is_split_like_ratio((close / prev_close).to_numpy()),
        index=close.index,
        columns=close.columns,
    )
    split_gap = pd.DataFrame(
        t32.is_split_like_ratio((open_ / prev_close).to_numpy()),
        index=close.index,
        columns=close.columns,
    )
    hygiene = {
        "contract": report.contract,
        "symbols_masked": report.symbols_masked,
        "masked_symbols": list(report.masked_symbols),
        "price_cells_masked": report.price_cells_masked,
    }
    return Panel(close, open_, spread, dv21, split_close, split_gap, hygiene)


# ---- costs / borrow / simulation -------------------------------------------


def borrow_rates(dv21: pd.DataFrame) -> pd.DataFrame:
    rate = pd.DataFrame(BORROW_LO, index=dv21.index, columns=dv21.columns)
    rate = rate.mask(dv21 >= DV_HI, BORROW_HI)
    for col in dv21.columns:
        if col in ETF_COLS:
            rate[col] = BORROW_ETF
    return rate


def cost_fractions(spread: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {
        name: pd.DataFrame(bps / 1e4, index=spread.index, columns=spread.columns)
        for name, bps in FLAT_BPS.items()
    }
    out["main"] = MAIN_FLAT_BPS / 1e4 + MAIN_SPREAD_W * spread
    out["stress"] = STRESS_FLAT_BPS / 1e4 + STRESS_SPREAD_W * spread
    return out


def simulate_signed(
    weights: np.ndarray,
    lo: np.ndarray,
    lc: np.ndarray,
    cost_fracs: dict[str, np.ndarray],
    rate: np.ndarray,
) -> dict[str, Any]:
    """Row i of `weights` is the target book effective at the OPEN of session i
    (same convention as `salvage.simulate`): the day earns w_prev @ overnight-leg
    plus w @ open-to-close leg, and pays |w - w_prev| * cost at the open. Borrow
    is charged on the short weights held at the close of session i."""
    w_prev = np.vstack([np.zeros((1, weights.shape[1])), weights[:-1]])
    gross = (w_prev * lo).sum(axis=1) + (weights * lc).sum(axis=1)
    diff = np.abs(weights - w_prev)
    turn = diff.sum(axis=1)
    costs = {name: (diff * frac).sum(axis=1) for name, frac in cost_fracs.items()}
    short_abs = np.where(weights < 0, -weights, 0.0)
    borrow = (short_abs * rate).sum(axis=1) / 252.0
    return {"gross": gross, "turn": turn, "cost": costs, "borrow": borrow}


def series_variants(sim: dict[str, Any], index: pd.DatetimeIndex) -> dict[str, pd.Series]:
    g, b = sim["gross"], sim["borrow"]
    out = {
        "ret_10_after": g - sim["cost"]["flat10"] - b,
        "ret_10_before": g - sim["cost"]["flat10"],
        "ret_gross": g,
        "ret_20_after": g - sim["cost"]["flat20"] - b,
        "ret_main_after": g - sim["cost"]["main"] - b,
        "ret_stress_after": g - sim["cost"]["stress"] - b,
        "turn": sim["turn"],
        "borrow": b,
    }
    return {k: pd.Series(v, index=index) for k, v in out.items()}


# ---- tier logic (pure, unit-tested) -----------------------------------------


def tier_from(
    anchor_sharpe: float,
    stress_sharpe: float,
    cagr20_anchor: float,
    cagr20_stress: float,
    edge_anchor: float,
    edge_stress: float,
    placebo_max_anchor: float | None,
) -> dict[str, Any]:
    k1 = bool(
        anchor_sharpe >= K1_ANCHOR
        and stress_sharpe >= K1_STRESS
        and cagr20_anchor > 0
        and cagr20_stress > 0
    )
    k2 = bool(edge_anchor >= K2_EDGE_MIN and edge_stress >= K2_EDGE_MIN)
    strong = bool(
        (edge_anchor >= K2_EDGE_STRONG and edge_stress >= K2_EDGE_STRONG)
        or (k1 and anchor_sharpe >= S3_ANCHOR and stress_sharpe >= S3_STRESS)
    )
    watch = bool(anchor_sharpe >= K1_ANCHOR and not k1)
    raw = (
        "keep_strong"
        if (k1 or k2) and strong
        else "keep"
        if (k1 or k2)
        else ("watch_recent" if watch else "reject")
    )
    placebo_pass = True if placebo_max_anchor is None else bool(anchor_sharpe > placebo_max_anchor)
    tier = raw if (raw == "reject" or placebo_pass) else "reject_placebo"
    failed = []
    if not (k1 or k2):
        if anchor_sharpe < K1_ANCHOR:
            failed.append(f"K1 anchor {anchor_sharpe:.4f} < {K1_ANCHOR}")
        elif stress_sharpe < K1_STRESS:
            failed.append(f"K1 stress {stress_sharpe:.4f} < {K1_STRESS}")
        elif not (cagr20_anchor > 0 and cagr20_stress > 0):
            failed.append("K1 20 bp CAGR not positive in both windows")
        failed.append(
            f"K2 edges anchor {edge_anchor:.4f} / stress {edge_stress:.4f} (need >= {K2_EDGE_MIN})"
        )
    if raw != "reject" and not placebo_pass:
        failed.append(
            f"placebo max anchor {placebo_max_anchor:.4f} >= candidate {anchor_sharpe:.4f}"
        )
    return {
        "k1": k1,
        "k2": k2,
        "strong": strong,
        "watch_recent": watch,
        "tier_before_placebo": raw,
        "placebo_pass": placebo_pass,
        "tier": tier,
        "failed_conditions": failed,
    }


# ---- weight builders --------------------------------------------------------


def piecewise(n: int, m: int, events: list[tuple[int, np.ndarray]]) -> np.ndarray:
    """Weights matrix from (effective_row, book) events; each book holds until
    the next event (a zero book flattens)."""
    w = np.zeros((n, m))
    events = sorted(events, key=lambda e: e[0])
    for j, (row, vec) in enumerate(events):
        if row >= n:
            continue
        end = events[j + 1][0] if j + 1 < len(events) else n
        w[row : min(end, n)] = vec
    return w


@dataclass
class Ctx:
    panel: Panel
    cols: list[str]
    col_ix: dict[str, int]
    n: int
    elig_short: np.ndarray  # bool n x m, at the signal close
    valid: np.ndarray  # bool n x m, close notna
    split_sig: np.ndarray  # bool n x m: split-like close ratio or gap ratio on the signal day
    rate: np.ndarray
    ret1: np.ndarray  # close-to-close returns (NaN kept)


def make_ctx(panel: Panel) -> Ctx:
    cols = list(panel.close.columns)
    close = panel.close
    elig = ((close >= MIN_SHORT_CLOSE) & (panel.dv21 >= DV_MIN_SHORT)).to_numpy()
    for c in ETF_COLS & set(cols):
        elig[:, cols.index(c)] = close[c].notna().to_numpy()
    split_sig = (panel.split_close | panel.split_gap).to_numpy()
    return Ctx(
        panel=panel,
        cols=cols,
        col_ix={c: i for i, c in enumerate(cols)},
        n=len(close),
        elig_short=elig,
        valid=close.notna().to_numpy(),
        split_sig=split_sig,
        rate=borrow_rates(panel.dv21).to_numpy(),
        ret1=close.pct_change(fill_method=None).to_numpy(),
    )


# -- A: dual-class pairs --------


def pair_signals(ctx: Ctx, win: int) -> np.ndarray:
    """z-score of log(P_a/P_b) vs its trailing `win`-day mean/std (n x P), NaN when
    either class is missing in the window or has a split-like one-day move in
    the trailing window (look-back only, never outcome based)."""
    close = ctx.panel.close
    split = ctx.panel.split_close
    out = np.full((ctx.n, len(PAIRS)), np.nan)
    for p, (a, b) in enumerate(PAIRS):
        if a not in close.columns or b not in close.columns:
            continue
        r = np.log(close[a] / close[b])
        mu = r.rolling(win, min_periods=win).mean()
        sd = r.rolling(win, min_periods=win).std(ddof=1)
        z = (r - mu) / sd.replace(0.0, np.nan)
        bad = (
            (split[a] | split[b])
            .astype(float)
            .rolling(win + SPLIT_LOOKBACK_EXTRA, min_periods=1)
            .max()
        )
        out[:, p] = z.where(bad < 1.0).to_numpy()
    return out


def pair_book(
    ctx: Ctx,
    z_row: np.ndarray,
    i: int,
    thr: float,
    flip: bool,
    rng: np.random.Generator | None,
) -> np.ndarray:
    """Signed book (length m) for signal row i. Per pair weight 1/N of each leg."""
    m = len(ctx.cols)
    vec = np.zeros(m)
    npairs = len(PAIRS)
    for p, (a, b) in enumerate(PAIRS):
        z = z_row[p]
        if not np.isfinite(z) or abs(z) < max(thr, 1e-12):
            continue
        ia, ib = ctx.col_ix[a], ctx.col_ix[b]
        if (
            not (ctx.valid[i, ia] and ctx.valid[i, ib])
            or ctx.split_sig[i, ia]
            or ctx.split_sig[i, ib]
        ):
            continue
        sgn = 1.0 if z < 0 else -1.0  # +1: long a (cheap), short b
        if rng is not None:
            sgn = 1.0 if rng.random() < 0.5 else -1.0
        elif flip:
            sgn = -sgn
        short_ix = ib if sgn > 0 else ia
        if not ctx.elig_short[i, short_ix]:
            continue
        long_ix = ia if sgn > 0 else ib
        vec[long_ix] += 1.0 / npairs
        vec[short_ix] -= 1.0 / npairs
    return vec


def weights_A(
    ctx: Ctx,
    zmat: np.ndarray,
    cand: Cand,
    offset: int,
    flip: bool = False,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    idx = ctx.panel.close.index
    dates = lane.signal_dates(idx, cand.params["freq"], offset)
    pos = {d: i for i, d in enumerate(idx)}
    events: list[tuple[int, np.ndarray]] = []
    for d in dates:
        i = pos[d]
        if i + 1 >= ctx.n:
            continue
        events.append((i + 1, pair_book(ctx, zmat[i], i, cand.params["thr"], flip, rng)))
    return piecewise(ctx.n, len(ctx.cols), events)


# -- B: ETF crash -> constituent laggards --------


def etf_triggers(ctx: Ctx, etf: str) -> np.ndarray:
    ret = pd.Series(ctx.ret1[:, ctx.col_ix[etf]], index=ctx.panel.close.index)
    thr = ret.shift(1).rolling(252, min_periods=252).quantile(0.10)
    return (ret <= thr).fillna(False).to_numpy()


def weights_B(
    ctx: Ctx,
    cand: Cand,
    trig: np.ndarray,
    delay: int,
    flip: bool = False,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    etf, k, hold = cand.params["etf"], cand.params["k"], cand.params["hold"]
    m = len(ctx.cols)
    ie = ctx.col_ix[etf]
    stocks = [ctx.col_ix[s] for s in CONSTITUENTS[etf] if s in ctx.col_ix]
    events: list[tuple[int, np.ndarray]] = []
    busy_until = -1
    for t in np.flatnonzero(trig):
        e = int(t) + 1 + delay
        if e >= ctx.n or e < busy_until:
            continue
        ok = [
            j
            for j in stocks
            if ctx.valid[t, j]
            and ctx.elig_short[t, j]
            and not ctx.split_sig[t, j]
            and np.isfinite(ctx.ret1[t, j])
        ]
        if len(ok) < k or not np.isfinite(ctx.ret1[t, ie]) or not ctx.valid[t, ie]:
            continue
        rel = np.array([ctx.ret1[t, j] - ctx.ret1[t, ie] for j in ok])
        if rng is not None:
            chosen = [ok[x] for x in rng.permutation(len(ok))[:k]]
        else:
            chosen = [ok[x] for x in np.argsort(rel, kind="stable")[:k]]
        vec = np.zeros(m)
        for j in chosen:
            vec[j] += 1.0 / k
        vec[ie] -= 1.0
        if flip:
            vec = -vec
        events.append((e, vec))
        events.append((e + hold, np.zeros(m)))
        busy_until = e + hold
    return piecewise(ctx.n, m, events)


# -- C: sector SPDR intramonth momentum --------


def month_end_positions(index: pd.DatetimeIndex) -> list[int]:
    s = pd.Series(np.arange(len(index)), index=index)
    return [int(v) for v in s.groupby(index.to_period("M")).max().to_numpy()]


def sector_book(
    ctx: Ctx,
    i: int,
    kind: str,
    k: int,
    flip: bool,
    rng: np.random.Generator | None,
) -> np.ndarray | None:
    ix = [ctx.col_ix[s] for s in SECTORS]
    close = ctx.panel.close.to_numpy()
    if i < 252 or not all(ctx.valid[i, j] and ctx.valid[i - 252, j] for j in ix):
        return None
    mom = np.array([close[i, j] / close[i - 252, j] - 1.0 for j in ix])
    order = np.argsort(-mom, kind="stable") if rng is None else rng.permutation(len(ix))
    vec = np.zeros(len(ctx.cols))
    for j in order[:k]:
        vec[ix[j]] += 1.0 / k
    if kind == "MN":
        vec[ctx.col_ix[BENCH]] -= 1.0
    else:  # LS and ABL
        for j in order[-k:]:
            vec[ix[j]] -= 1.0 / k
    return -vec if flip else vec


def weights_C_calendar(
    ctx: Ctx,
    cand: Cand,
    shift: int = 0,
    flip: bool = False,
    rng_seed: int | None = None,
) -> np.ndarray:
    m = len(ctx.cols)
    kind, k = cand.params["kind"], cand.params["k"]
    me = month_end_positions(ctx.panel.close.index)
    rng = np.random.default_rng(rng_seed) if rng_seed is not None else None
    books: dict[int, np.ndarray | None] = {i: sector_book(ctx, i, kind, k, flip, rng) for i in me}
    events: list[tuple[int, np.ndarray]] = []
    zero = np.zeros(m)
    for j, i in enumerate(me):
        b = books[i]
        if b is not None:
            for row, vec in (
                (i + 1 + shift, b),
                (i + 2 + shift, -b),
                (i + 4 + shift, zero),
            ):
                events.append((row, vec))
        # leg 3: window D-10..D-5 of this month uses the previous month-end ranking
        if j > 0 and books[me[j - 1]] is not None:
            pb = books[me[j - 1]]
            events.append((i - 10 + shift, pb))  # type: ignore[arg-type]
            events.append((i - 4 + shift, zero))
    events = [(r, v) for r, v in events if 0 <= r < ctx.n]
    # events are constructed in non-overlapping windows; keep the last per row
    dedup: dict[int, np.ndarray] = {}
    for r, v in events:
        dedup[r] = v
    return piecewise(ctx.n, m, list(dedup.items()))


def weights_C_monthly(
    ctx: Ctx,
    cand: Cand,
    offset: int,
    flip: bool = False,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    idx = ctx.panel.close.index
    dates = lane.signal_dates(idx, "M", offset)
    pos = {d: i for i, d in enumerate(idx)}
    events: list[tuple[int, np.ndarray]] = []
    for d in dates:
        i = pos[d]
        if i + 1 >= ctx.n:
            continue
        b = sector_book(ctx, i, "ABL", cand.params["k"], flip, rng)
        events.append((i + 1, b if b is not None else np.zeros(len(ctx.cols))))
    return piecewise(ctx.n, len(ctx.cols), events)


# ---- evaluation -------------------------------------------------------------


def window_stats(
    ret: pd.Series,
    turn: pd.Series,
    borrow: pd.Series,
    window: tuple[str, str],
    first_valid: pd.Timestamp,
) -> dict[str, float]:
    start = lane.window_actual_start(window[0], first_valid)
    mask = (ret.index >= start) & (ret.index <= pd.Timestamp(window[1]))
    zero = pd.Series(0.0, index=ret.index)
    m = base.metrics(ret.loc[mask], zero, turn.loc[mask])
    years = max(int(mask.sum()) / 252.0, 1e-9)
    return {
        "days": m.days,
        "cagr": m.cagr,
        "vol": m.vol,
        "sharpe": m.sharpe,
        "max_dd": m.max_dd,
        "turnover_yr": m.turnover_yr,
        "borrow_drag_yr": float(borrow.loc[mask].sum() / years),
        "actual_start": str(start.date()),
    }


def first_active(weights: np.ndarray, index: pd.DatetimeIndex) -> pd.Timestamp:
    active = np.abs(weights).sum(axis=1) > 0
    return index[int(np.argmax(active))] if active.any() else index[-1]


def med(vals: list[float]) -> float:
    return float(np.median(np.array(vals, dtype=float)))


@dataclass
class Runner:
    ctx: Ctx
    lo: np.ndarray
    lc: np.ndarray
    cost_fracs: dict[str, np.ndarray]
    rf: pd.Series
    shy_ret: pd.Series
    s3_ret10: pd.Series

    def sim(self, weights: np.ndarray) -> dict[str, pd.Series]:
        s = simulate_signed(weights, self.lo, self.lc, self.cost_fracs, self.ctx.rate)
        return series_variants(s, self.ctx.panel.close.index)


def variants_for(cand: Cand) -> list[Any]:
    if cand.direction == "A":
        return lane.offsets_for_freq(cand.params["freq"])
    if cand.direction == "B":
        return [0, 1, 2]
    if cand.params["kind"] == "ABL":
        return lane.offsets_for_freq("M")
    return [0]


def build_variant(
    runner: Runner,
    cand: Cand,
    variant: Any,
    *,
    aux: dict[str, Any],
    flip: bool = False,
    rng: np.random.Generator | None = None,
    rng_seed: int | None = None,
) -> np.ndarray:
    ctx = runner.ctx
    if cand.direction == "A":
        return weights_A(ctx, aux["z"][cand.params["win"]], cand, variant, flip, rng)
    if cand.direction == "B":
        return weights_B(ctx, cand, aux["trig"][cand.params["etf"]], variant, flip, rng)
    if cand.params["kind"] == "ABL":
        return weights_C_monthly(ctx, cand, variant, flip, rng)
    return weights_C_calendar(ctx, cand, shift=variant, flip=flip, rng_seed=rng_seed)


def summarize_variants(
    per_var: dict[Any, dict[str, pd.Series]], first_valid: pd.Timestamp
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for wname, window in lane.WINDOWS.items():
        rows: dict[str, list[dict[str, float]]] = {
            k: []
            for k in (
                "ret_10_after",
                "ret_10_before",
                "ret_gross",
                "ret_20_after",
                "ret_main_after",
                "ret_stress_after",
            )
        }
        for v in per_var.values():
            for k in rows:
                rows[k].append(window_stats(v[k], v["turn"], v["borrow"], window, first_valid))
        a10 = rows["ret_10_after"]
        out[wname] = {
            "median_sharpe_after_borrow_10bp": med([r["sharpe"] for r in a10]),
            "min_sharpe_after_borrow_10bp": float(min(r["sharpe"] for r in a10)),
            "max_sharpe_after_borrow_10bp": float(max(r["sharpe"] for r in a10)),
            "sharpe_after_borrow_10bp_by_variant": [r["sharpe"] for r in a10],
            "median_sharpe_before_borrow_10bp": med([r["sharpe"] for r in rows["ret_10_before"]]),
            "median_sharpe_gross_no_cost_no_borrow": med([r["sharpe"] for r in rows["ret_gross"]]),
            "median_sharpe_after_borrow_20bp": med([r["sharpe"] for r in rows["ret_20_after"]]),
            "median_sharpe_main_5bp_half_spread": med(
                [r["sharpe"] for r in rows["ret_main_after"]]
            ),
            "median_sharpe_stress_2x_spread": med([r["sharpe"] for r in rows["ret_stress_after"]]),
            "median_cagr_after_borrow_10bp": med([r["cagr"] for r in a10]),
            "median_cagr_after_borrow_20bp": med([r["cagr"] for r in rows["ret_20_after"]]),
            "median_cagr_main": med([r["cagr"] for r in rows["ret_main_after"]]),
            "median_max_dd_after_borrow_10bp": med([r["max_dd"] for r in a10]),
            "median_vol_10bp": med([r["vol"] for r in a10]),
            "median_turnover_yr": med([r["turnover_yr"] for r in a10]),
            "median_borrow_drag_yr": med([r["borrow_drag_yr"] for r in a10]),
            "actual_start": a10[0]["actual_start"],
        }
    return out


def placebo_block(
    runner: Runner, cand: Cand, aux: dict[str, Any], first_valid: pd.Timestamp, cand_ix: int
) -> dict[str, Any]:
    anchors, stresses = [], []
    for seed in range(N_PLACEBO_SEEDS):
        per_var: dict[Any, dict[str, pd.Series]] = {}
        for v in variants_for(cand):
            rng = np.random.default_rng(
                seed * 1000 + cand_ix * 10 + (v if isinstance(v, int) else 0)
            )
            w = build_variant(
                runner,
                cand,
                v,
                aux=aux,
                rng=rng,
                rng_seed=seed * 1000 + cand_ix * 10 + (v if isinstance(v, int) else 0),
            )
            per_var[v] = runner.sim(w)
        sh = {}
        for wname in ("anchor", "stress"):
            vals = []
            for v in per_var.values():
                vals.append(
                    window_stats(
                        v["ret_10_after"], v["turn"], v["borrow"], lane.WINDOWS[wname], first_valid
                    )["sharpe"]
                )
            sh[wname] = med(vals)
        anchors.append(sh["anchor"])
        stresses.append(sh["stress"])
    a = np.array(anchors, dtype=float)
    return {
        "seeds": N_PLACEBO_SEEDS,
        "anchor_median_sharpes": [float(x) for x in a],
        "stress_median_sharpes": [float(x) for x in stresses],
        "anchor_max": float(np.nanmax(a)),
        "anchor_mean": float(np.nanmean(a)),
        "anchor_p95": float(np.nanpercentile(a, 95)),
        "stress_mean": float(np.nanmean(np.array(stresses, dtype=float))),
    }


def evaluate(runner: Runner, cand: Cand, aux: dict[str, Any], cand_ix: int) -> dict[str, Any]:
    index = runner.ctx.panel.close.index
    variants = variants_for(cand)
    weights = {v: build_variant(runner, cand, v, aux=aux) for v in variants}
    first_valid = max(first_active(w, index) for w in weights.values())
    per_var = {v: runner.sim(w) for v, w in weights.items()}
    summary = summarize_variants(per_var, first_valid)
    # K2 (sleeve = overlay + T-bill collateral)
    edges: dict[str, dict[str, float]] = {}
    for wname in ("anchor", "stress"):
        by_v = {
            v: lane.diversifier_edge_for_offset(
                runner.s3_ret10,
                per_var[v]["ret_10_after"] + runner.rf.reindex(index).fillna(0.0),
                runner.shy_ret,
                runner.rf,
                lane.WINDOWS[wname],
            )
            for v in variants
        }
        edges[wname] = {"median": med(list(by_v.values())), "min": float(min(by_v.values()))}
    # judged variant + DSR
    anchor_by_v = {
        v: window_stats(
            per_var[v]["ret_10_after"],
            per_var[v]["turn"],
            per_var[v]["borrow"],
            lane.WINDOWS["anchor"],
            first_valid,
        )["sharpe"]
        for v in variants
    }
    judged = lane.judged_offset({int(i): s for i, s in enumerate(anchor_by_v.values())})
    judged_variant = list(anchor_by_v.keys())[judged]
    a_start = lane.window_actual_start(lane.WINDOWS["anchor"][0], first_valid)
    jr = per_var[judged_variant]["ret_10_after"]
    mask = (jr.index >= a_start) & (jr.index <= pd.Timestamp(lane.WINDOWS["anchor"][1]))
    try:
        dsr = float(
            deflated_sharpe_probability(
                jr.loc[mask].to_numpy(), trial_count=N_TRIALS, hac_lag=lane.DSR_HAC_LAG
            )
        )
    except ValueError:
        dsr = None
    # mirror (sign-flipped book, same eligibility/cost/borrow rules)
    mir_var = {v: runner.sim(build_variant(runner, cand, v, aux=aux, flip=True)) for v in variants}
    mir_first = first_valid
    mirror = summarize_variants(mir_var, mir_first)
    plc = placebo_block(runner, cand, aux, first_valid, cand_ix)
    anc, stress = summary["anchor"], summary["stress"]
    tier = tier_from(
        anc["median_sharpe_after_borrow_10bp"],
        stress["median_sharpe_after_borrow_10bp"],
        anc["median_cagr_after_borrow_20bp"],
        stress["median_cagr_after_borrow_20bp"],
        edges["anchor"]["median"],
        edges["stress"]["median"],
        plc["anchor_max"],
    )
    exposure = float(np.mean([np.mean(np.abs(w).sum(axis=1) > 0) for w in weights.values()]))
    sh_mirror = {
        "anchor": mirror["anchor"]["median_sharpe_after_borrow_10bp"],
        "stress": mirror["stress"]["median_sharpe_after_borrow_10bp"],
    }
    return {
        "id": cand.id,
        "direction": cand.direction,
        "params": cand.params,
        "variants": [str(v) for v in variants],
        "variant_kind": {
            "A": "rebalance offsets",
            "B": "entry delay sessions",
            "C": "calendar version / offsets",
        }[cand.direction],
        "first_valid_signal_effective": str(first_valid.date()),
        "share_of_days_with_position": exposure,
        "windows": summary,
        "k2_edge_vs_s3": edges,
        "judged_variant": str(judged_variant),
        "dsr_anchor_after_borrow": dsr,
        "n_trials": N_TRIALS,
        "mirror": {"sharpe": sh_mirror, "windows": mirror},
        "random_placebo": plc,
        "tier_inputs": {
            "anchor_median_sharpe_after_borrow_10bp": anc["median_sharpe_after_borrow_10bp"],
            "stress_median_sharpe_after_borrow_10bp": stress["median_sharpe_after_borrow_10bp"],
            "anchor_median_cagr_after_borrow_20bp": anc["median_cagr_after_borrow_20bp"],
            "stress_median_cagr_after_borrow_20bp": stress["median_cagr_after_borrow_20bp"],
            "anchor_k2_edge_median": edges["anchor"]["median"],
            "stress_k2_edge_median": edges["stress"]["median"],
            "placebo_max_anchor": plc["anchor_max"],
        },
        **tier,
    }


def main() -> int:
    t0 = datetime.now(UTC)
    base.WARMUP_START = lane.PANEL_START
    lane_close, lane_open = base.load_panel(
        sorted(set(salvage.symbols()) | {lane.CASH, lane.RF, BENCH})
    )
    index = lane_close.index
    leg_open_l, leg_close_l = salvage.legs(lane_close, lane_open)
    rf = (lane_close[lane.RF] / lane_close[lane.RF].shift(1) - 1.0).fillna(0.0)
    shy_ret = (lane_close[lane.CASH] / lane_close[lane.CASH].shift(1) - 1.0).fillna(0.0)
    s3_ret10, _ = lane.s3_incumbent(lane_close, leg_open_l, leg_close_l, lane.COST_BPS_PRIMARY)

    panel = load_stock_panel(all_symbols(), index)
    missing = sorted(set(all_symbols()) - set(panel.close.columns) - {lane.CASH, lane.RF})
    if missing:
        print("missing symbols:", missing, flush=True)
    ctx = make_ctx(panel)
    lo, lc = salvage.legs(panel.close, panel.open)
    costs = {k: v.to_numpy() for k, v in cost_fractions(panel.spread).items()}
    runner = Runner(ctx, lo.to_numpy(), lc.to_numpy(), costs, rf, shy_ret, s3_ret10)
    aux = {
        "z": {w: pair_signals(ctx, w) for w in (63, 252)},
        "trig": {etf: etf_triggers(ctx, etf) for etf in CONSTITUENTS},
    }
    null_edges = {
        w: lane.diversifier_edge_for_offset(s3_ret10, rf.copy(), shy_ret, rf, lane.WINDOWS[w])
        for w in ("anchor", "stress")
    }
    print("null sleeve (zero overlay + T-bill) K2 edge:", null_edges, flush=True)
    rows = []
    for ix, cand in enumerate(CANDIDATES):
        rows.append(evaluate(runner, cand, aux, ix))
        r = rows[-1]
        a, s = r["windows"]["anchor"], r["windows"]["stress"]
        print(
            f"{cand.id}: anchor {a['median_sharpe_after_borrow_10bp']:.3f} stress "
            f"{s['median_sharpe_after_borrow_10bp']:.3f} edges "
            f"{r['k2_edge_vs_s3']['anchor']['median']:.3f}/"
            f"{r['k2_edge_vs_s3']['stress']['median']:.3f} "
            f"tier {r['tier']}",
            flush=True,
        )
    out = {
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "runtime_seconds": (datetime.now(UTC) - t0).total_seconds(),
        "contract": {
            "windows": lane.WINDOWS,
            "k1_anchor": K1_ANCHOR,
            "k1_stress": K1_STRESS,
            "s3_anchor": S3_ANCHOR,
            "s3_stress": S3_STRESS,
            "k2_edge_min": K2_EDGE_MIN,
            "k2_edge_strong": K2_EDGE_STRONG,
            "judged_cost": "flat 10 bp per side per leg, ADV-tier borrow deducted",
            "borrow": {"hi_ge_50M": BORROW_HI, "lo_5M_50M": BORROW_LO, "etf": BORROW_ETF},
            "n_trials_dsr": N_TRIALS,
            "placebo_seeds": N_PLACEBO_SEEDS,
        },
        "panel_notes": {
            "price_hygiene_report": panel.hygiene,
            "missing_symbols": missing,
            "constituent_lists": CONSTITUENTS,
            "pairs": PAIRS,
        },
        "diagnostics_added_before_final_run": {
            "note": (
                "median_sharpe_gross_no_cost_no_borrow and null_sleeve_k2_edge were added after "
                "a first complete run showed every tier as reject; candidate list, thresholds "
                "and judged fields were not changed and reproduce the first run exactly"
            ),
            "null_sleeve_k2_edge": null_edges,
        },
        "candidates": rows,
        "headline_candidates": HEADLINE,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "results.json").write_text(
        json.dumps(out, indent=2, default=float) + "\n", encoding="utf-8"
    )
    print("wrote", OUT_DIR / "results.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
