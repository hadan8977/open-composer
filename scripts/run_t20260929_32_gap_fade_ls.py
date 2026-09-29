"""T-20260929-32: cross-sectional gap-fade with a tradable short leg.

Owner widened the research scope on 2026-09-29 to everything Alpaca Paper can
trade, including short selling of easy-to-borrow names with borrow cost
modeled (``CLAUDE.md`` / ``AGENTS.md`` "Research scope"). H-20260922-08
(``reports/research/hypotheses/H-20260922-08-cross-sectional-gap-fade.md``,
``scripts/run_h20260922_08_gap_fade.py``) found the cross-sectional overnight
gap-fade signal real (early window 2016-2021 gross +99.0%/yr, Sharpe 3.01, in
the panel's most illiquid tier), with the edge concentrated on the SHORT leg
(fading up-gaps) and in the least liquid names -- but it was frozen
``not_executable`` because the paper-rehearsal execution path had no short
leg. This task reruns the *same signal and timing* (z-scored overnight gap,
long the most-negative-z names / short the most-positive-z names, enter at
that session's open, exit at that session's close, one-day holding period,
no overnight exposure) with (a) a short leg restricted to an easy-to-borrow
proxy universe and (b) realistic per-stock frictions, and asks whether the
edge survives.

**2026-09-29 price-hygiene correction (mid-task, coordinator-relayed)**:
neither H-20260922-08's original script nor this task's first draft called
the repo's price-hygiene module, and ``data/sip/daily`` (and therefore
``data/features/gap_panel.parquet``, built from it) carries three defects
that manufacture fake overnight gaps concentrated exactly in the illiquid
short-leg tier: post-bankruptcy relistings under a reused ticker (WOLF
1.21->22.1), one-day bad prints (KIDZ, IXHL), and unadjusted splits (APH
161.34->80.69). This script therefore computes the signal **twice** from the
same raw ``data/sip/daily`` bars: a ``raw`` path (byte-for-byte the same
construction ``build_gap_panel.py``/H-20260922-08 used -- kept only so the
size of the artifact is visible, never used for the verdict) and a
``sanitized`` path (wide close/open/high/low matrices passed through
``open_composer.research.features.price_hygiene.mask_regime_breaks`` --
the function ``sanitize_price_matrices`` wraps, called here with all four
matrices and default thresholds so high/low are masked consistently with
close/open for the Abdi-Ranaldo spread -- plus a trigger-session split-like
filter this module did not have, see :func:`is_split_like_ratio`, which
drops a signal whose gap ratio itself sits within 3% (log-space) of a common
split multiple regardless of the 10x jump threshold that only catches
outright regime breaks). **The verdict uses the sanitized path only.**

**Reused, unmodified**:
``scripts/run_h20260922_08_gap_fade.py``'s signal definition (gap, sigma21,
oc, z; the point-in-time construction: gap uses the official open against
the prior adjusted close, and the 21-day trailing vol/liquidity filters use
only prior sessions) is reproduced in :func:`build_signal_panel`, applied to
either the raw or the hygiene-masked wide matrices.
``open_composer.research.features.price_hygiene`` (``ph`` below) for
``mask_regime_breaks`` and ``daily_returns_no_pad``.
``scripts/run_t20260928_30_smallcap_ml_book.py`` (``ml30`` below) for the
Abdi-Ranaldo (2017) close-high-low spread estimator (``spread_estimate_from_ohlc``,
unit-tested there) and its ``per_stock_cost_bps`` cost formula -- applied
per symbol over the wide matrices in :func:`spread_wide` rather than
recomputed in SQL (an earlier draft's DuckDB window-function version over
~8,600 symbols' full history OOM-killed this box's 1.8GB cgroup twice; a
Python loop calling the already-vectorized-per-symbol pure function is both
correct and far lighter, since each call is O(sessions) with no cross-symbol
buffer). ``scripts/run_h20260918_05_recent_menu.py`` (``base``) for
``load_panel`` and ``metrics`` (BIL-excess Sharpe, the convention the K1
thresholds below were frozen against). ``scripts/run_h20260922_05_salvage.py``
(``salvage``) for ``symbols()`` (S3's own ETF universe, needed only for K2).
``scripts/screen_lane.py`` for ``s3_incumbent`` / ``diversifier_edge_for_offset``
(K2) and ``PANEL_START``/``COST_BPS_PRIMARY``.

**New in this script**: the easy-to-borrow proxy filter and ADV-bucket
assignment, the sign-randomization placebo (:func:`placebo_sign_flip`), the
per-leg return engine (:func:`leg_return`, :func:`combine_legs`), the wide
matrix loader (:func:`load_wide_matrices`), the wide-matrix signal builder
(:func:`build_signal_panel`), and the split-like trigger filter
(:func:`is_split_like_ratio`).

Spec (frozen before any number below was computed -- see the task brief
T-20260929-32; the hygiene correction changes *data*, not the frozen spec):

* Short-leg universe (easy-to-borrow proxy): close >= $5 (already the panel's
  own floor) and 21-day median dollar volume (``dv21``) >= $5M, and not in
  the top decile of that day's cross-sectional short-interest days-to-cover
  (``dtc_cross_sectional_pct < 0.90``, point-in-time via its own
  ``visible_date``; coverage starts 2018, so the DTC screen is simply not
  applied in 2016-2017). ADV buckets reported separately: $5-20M, $20-100M,
  >$100M.
* Long leg: unchanged from H-20260922-08's $1M-floor panel (``dv21 >= 1e6``),
  K=10 most negative z each day.
* Books: L/S (long leg + short leg, dollar-neutral, equal weight within
  legs, 1x long + 1x short = 2x gross, Alpaca's overnight cap) and S-only
  hedged (short leg + long SPY of equal dollars, same-day open-to-close).
* Frictions per side: base = 5bp + 0.5 x Abdi-Ranaldo spread; stress = 2x
  that. Borrow on the short leg: 0.5%/yr (ADV > $100M), 2%/yr ($20-100M),
  5%/yr ($5-20M), charged daily (/360, Alpaca's own HTB fee day-count).
  Also reported: the repo's frozen flat 10bp/20bp per side (no spread).
* Windows: stress 2016-05-02..2023-08-31, select 2023-09-18..2025-12-31,
  anchor 2024-01-08..latest, 2026 flagged contaminated. One-day holding
  period, no periodic rebalance -- "21 rebalance offsets" does not apply.
* Placebo: same books, each day's cross-sectional z sign flipped with
  probability 0.5, 20 seeds -> share of placebos beating the real book.
* K2: ``screen_lane.diversifier_edge_for_offset`` at base frictions.
* Verdict: keep K1 if Sharpe at base frictions >= 0.65 in stress AND >= 1.19
  in anchor AND CAGR at stress frictions is positive in both; keep K2 if the
  S3 combination edge >= +0.05 in both; else reject -- **sanitized path
  only**.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.research.features import price_hygiene as ph  # noqa: E402
from scripts import run_h20260918_05_recent_menu as base  # noqa: E402
from scripts import run_h20260922_05_salvage as salvage  # noqa: E402
from scripts import run_t20260928_30_smallcap_ml_book as ml30  # noqa: E402
from scripts import screen_lane  # noqa: E402

ITERATION_ID = "t20260929_32_gap_fade_ls"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = OUT_DIR / "cache"
RESULTS_PATH = OUT_DIR / "results.json"
REPORT_PATH = OUT_DIR / "report.md"

GAP_PANEL = ROOT / "data" / "features" / "gap_panel.parquet"
SIP_DAILY_GLOB = str(ROOT / "data" / "sip" / "daily" / "*" / "*.parquet")
SHORT_INTEREST_GLOB = str(ROOT / "data" / "features" / "short_interest" / "20*.parquet")

# --------------------------------------------------------------------------
# frozen spec constants
# --------------------------------------------------------------------------

K = 10  # leg size -- H-20260922-08's illiquid-tier judgement cell (liq $1M, K=10)

WINDOWS_TEMPLATE: dict[str, tuple[str, str | None]] = {
    "stress": ("2016-05-02", "2023-08-31"),
    "select": ("2023-09-18", "2025-12-31"),
    "anchor": ("2024-01-08", None),  # end = latest date in the panel
}
CONTAMINATED_START = "2026-01-01"

# H-20260922-08's own windows, reused verbatim only for the hygiene recheck
# (section 6 of results.json) so that comparison is apples-to-apples.
EARLY_ORIGINAL = ("2016-03-31", "2021-12-31")
LATE_ORIGINAL_START = "2022-01-01"

COST_BASE_FLAT_BPS = 5.0
COST_STRESS_FLAT_BPS = 10.0
COST_BASE_SPREAD_WEIGHT = 0.5
COST_STRESS_SPREAD_WEIGHT = 1.0
FLAT_REF_BASE_BPS = 10.0  # repo-standard flat reference (base.COST_BPS_PRIMARY)
FLAT_REF_STRESS_BPS = 20.0  # base.COST_BPS_STRESS
FLAT_REF_SPREAD_WEIGHT = 0.0

DTC_TOP_DECILE = 0.90
ADV_MIN_SHORT = 5e6
LONG_LEG_MIN_DV21 = 1e6  # H-20260922-08's own $1M panel floor
PANEL_MIN_CLOSE = 5.0
PANEL_MIN_HISTORY = 60
LIQUIDITY_WINDOW_DAYS = 21
# name -> (lower bound inclusive, upper bound exclusive, annual borrow rate)
ADV_BUCKETS: dict[str, tuple[float, float, float]] = {
    "5_20m": (5e6, 2e7, 0.05),
    "20_100m": (2e7, 1e8, 0.02),
    "100m_plus": (1e8, np.inf, 0.005),
}
BORROW_DAYCOUNT = 360.0  # Alpaca's own HTB fee convention (daily fee / 360)

# Common split/reverse-split multiples. 10x and 1/10 are already caught by
# price_hygiene's default 10x jump threshold (and the row is masked to NaN
# before this filter ever runs), but are listed anyway so this function is
# correct on its own if ever reused with a looser hygiene threshold.
SPLIT_LIKE_RATIOS = (0.1, 0.2, 0.25, 1.0 / 3.0, 0.5, 2.0 / 3.0, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0)
SPLIT_LIKE_LOG_TOL = 0.03  # ~3% relative tolerance in log space

PLACEBO_SEEDS = 20

K1_STRESS_SHARPE_MIN = 0.65
K1_ANCHOR_SHARPE_MIN = 1.19
K2_EDGE_MIN = 0.05

VARIANTS = ("main", "5_20m", "20_100m", "100m_plus")
BOOK_TYPES = ("LS", "S_hedged")
COST_REGIMES = ("base", "stress", "flat10", "flat20")


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.date().isoformat()
    raise TypeError(type(o))


# --------------------------------------------------------------------------
# stage: raw wide matrices (no window functions in SQL -- see module
# docstring on why an earlier DuckDB-window-function version OOM-killed)
# --------------------------------------------------------------------------


def load_wide_matrices(force: bool = False) -> dict[str, pd.DataFrame]:
    """(close, open, high, low, volume), sessions x symbols, straight off
    ``data/sip/daily`` for exactly the symbols the existing gap panel already
    uses (so the raw path's eligible universe is unchanged) -- a plain
    filtered SELECT, no window functions, so the query itself cannot be the
    memory blow-up."""
    path = CACHE_DIR / "wide_matrices.parquet"
    if path.exists() and not force:
        long = pd.read_parquet(path)
    else:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect()
        con.execute("SET memory_limit='1400MB'; SET threads=2;")
        query = f"""
        SELECT r.symbol, r.date, r.open, r.high, r.low, r.close, r.volume
        FROM (
            SELECT symbol, timestamp::DATE AS date, open, high, low, close, volume
            FROM read_parquet('{SIP_DAILY_GLOB}')
            WHERE open > 0 AND high > 0 AND low > 0 AND close > 0
        ) r
        WHERE r.symbol IN (SELECT DISTINCT symbol FROM read_parquet('{GAP_PANEL.as_posix()}'))
        """
        long = con.execute(query).df()
        con.close()
        long["date"] = pd.to_datetime(long["date"])
        long.to_parquet(path, index=False)
    _log(f"wide matrices: {len(long):,} raw daily bars, {long['symbol'].nunique():,} symbols")
    out = {}
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = long.pivot(index="date", columns="symbol", values=col).sort_index()
    return out


# --------------------------------------------------------------------------
# stage: split-like trigger filter (new -- price_hygiene's 10x jump
# threshold does not catch ordinary 2x/3x/4x unadjusted splits)
# --------------------------------------------------------------------------


def is_split_like_ratio(
    ratio: np.ndarray,
    *,
    candidates: tuple[float, ...] = SPLIT_LIKE_RATIOS,
    tol: float = SPLIT_LIKE_LOG_TOL,
) -> np.ndarray:
    """Boolean array, same shape as ``ratio``: True where ``ratio`` sits
    within ``tol`` (log-space, ~``tol`` relative) of a common split/reverse-
    split multiple. Applied to the *trigger* session's own gap ratio
    (``open / prev_close``), never to the outcome (``close / open``) -- the
    brief is explicit that filtering on hold-window outcomes would drop real
    short squeezes, which look identical to a split in magnitude but are a
    genuine, capturable (or in this case, genuinely painful) price move."""
    ratio = np.asarray(ratio, dtype="float64")
    valid = np.isfinite(ratio) & (ratio > 0)
    logr = np.full_like(ratio, np.nan)
    logr[valid] = np.log(ratio[valid])
    out = np.zeros_like(ratio, dtype=bool)
    for c in candidates:
        out |= valid & (np.abs(logr - np.log(c)) < tol)
    return out


# --------------------------------------------------------------------------
# stage: signal panel (wide -> long), replicating build_gap_panel.py's SQL
# in pandas so it can run on either the raw or the hygiene-masked matrices
# --------------------------------------------------------------------------


def build_signal_panel(
    close_w: pd.DataFrame,
    open_w: pd.DataFrame,
    volume_w: pd.DataFrame,
    *,
    filter_split_like: bool,
) -> pd.DataFrame:
    """Long-format panel with columns [date, symbol, open, close, dv21, oc,
    z], eligibility identical to ``build_gap_panel.py``'s SQL: history >= 60
    prior sessions, trailing sigma21 > 0, prev_close >= $5, dv21 >= $1M.
    ``close_w``/``open_w`` may be raw or ``price_hygiene``-masked; masked
    (NaN) cells simply fail to produce an eligible row, which is exactly
    what "the pre-break history no longer exists" should do to a signal
    built on it."""
    prev_close = close_w.shift(1)
    prev_close_2 = close_w.shift(2)
    valid_close = close_w.notna()
    history = valid_close.shift(1, fill_value=False).cumsum()
    daily_ret = ph.daily_returns_no_pad(close_w)
    sigma21 = (
        daily_ret.rolling(LIQUIDITY_WINDOW_DAYS, min_periods=LIQUIDITY_WINDOW_DAYS)
        .std(ddof=1)
        .shift(1)
    )
    dollar_vol = close_w * volume_w
    dv21 = (
        dollar_vol.shift(1)
        .rolling(LIQUIDITY_WINDOW_DAYS, min_periods=LIQUIDITY_WINDOW_DAYS)
        .median()
    )
    gap = open_w / prev_close - 1.0
    oc = close_w / open_w - 1.0
    z = gap / sigma21.replace(0.0, np.nan)

    eligible = (
        (history >= PANEL_MIN_HISTORY)
        & sigma21.notna()
        & (sigma21 > 0)
        & (prev_close >= PANEL_MIN_CLOSE)
        & prev_close_2.notna()
        & (prev_close_2 > 0)
        & (dv21 >= LONG_LEG_MIN_DV21)
        & gap.notna()
        & oc.notna()
        & z.notna()
    )
    if filter_split_like:
        split_like = is_split_like_ratio((open_w / prev_close).to_numpy())
        eligible = eligible & ~pd.DataFrame(
            split_like, index=eligible.index, columns=eligible.columns
        )

    mask_arr = eligible.to_numpy()
    rows, cols = np.where(mask_arr)
    dates_arr = close_w.index.to_numpy()
    symbols_arr = np.asarray(close_w.columns)
    panel = pd.DataFrame(
        {
            "date": dates_arr[rows],
            "symbol": symbols_arr[cols],
            "open": open_w.to_numpy()[rows, cols],
            "close": close_w.to_numpy()[rows, cols],
            "dv21": dv21.to_numpy()[rows, cols],
            "oc": oc.to_numpy()[rows, cols],
            "z": z.to_numpy()[rows, cols],
        }
    )
    return panel.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)


def spread_wide(close_w: pd.DataFrame, high_w: pd.DataFrame, low_w: pd.DataFrame) -> pd.DataFrame:
    """Trailing 21-day Abdi-Ranaldo spread, one column per symbol, via
    ``ml30.spread_estimate_from_ohlc`` (unit-tested, unmodified) applied per
    symbol -- a plain Python loop over ~8,600 symbols, each call O(sessions)
    with no cross-symbol buffer, which is what makes this safe where the
    DuckDB window-function version was not."""
    out: dict[str, pd.Series] = {}
    for sym in close_w.columns:
        out[sym] = ml30.spread_estimate_from_ohlc(close_w[sym], high_w[sym], low_w[sym])
    return pd.DataFrame(out, index=close_w.index)


def lookup_from_wide(wide: pd.DataFrame, dates: pd.Series, symbols: pd.Series) -> np.ndarray:
    """``wide.loc[dates[i], symbols[i]]`` for every ``i``, vectorized via
    integer position indexing (no merge -- a melt+merge of an 8,600-column
    matrix is exactly the kind of memory blow-up this script now avoids
    elsewhere)."""
    date_pos = {d: i for i, d in enumerate(wide.index)}
    col_pos = {s: i for i, s in enumerate(wide.columns)}
    di = dates.map(date_pos).to_numpy()
    si = symbols.map(col_pos).to_numpy()
    values = wide.to_numpy()
    return values[di, si]


# --------------------------------------------------------------------------
# stage: DTC + costs + eligibility (shared by the raw and sanitized panels)
# --------------------------------------------------------------------------


def load_dtc() -> pd.DataFrame:
    """Point-in-time cross-sectional days-to-cover percentile, keyed by its
    own ``visible_date``. Coverage starts 2018 (2016-2017 has no
    short-interest file); callers must not silently backfill."""
    con = duckdb.connect()
    df = con.execute(
        f"""
        SELECT symbol, visible_date::DATE AS visible_date, dtc_cross_sectional_pct
        FROM read_parquet('{SHORT_INTEREST_GLOB}')
        WHERE dtc_cross_sectional_pct IS NOT NULL
        """
    ).df()
    con.close()
    df["visible_date"] = pd.to_datetime(df["visible_date"])
    return df.sort_values(["visible_date", "symbol"]).reset_index(drop=True)


def attach_dtc(panel: pd.DataFrame, dtc: pd.DataFrame) -> pd.DataFrame:
    p = panel.sort_values(["date", "symbol"]).reset_index(drop=True)
    d = dtc.sort_values(["visible_date", "symbol"]).reset_index(drop=True)
    return pd.merge_asof(
        p, d, left_on="date", right_on="visible_date", by="symbol", direction="backward"
    )


def add_costs_and_eligibility(
    panel: pd.DataFrame,
    close_w: pd.DataFrame,
    high_w: pd.DataFrame,
    low_w: pd.DataFrame,
    dtc: pd.DataFrame,
) -> pd.DataFrame:
    spread = spread_wide(close_w, high_w, low_w)
    panel = panel.copy()
    panel["spread_21"] = lookup_from_wide(spread, panel["date"], panel["symbol"])
    panel = attach_dtc(panel, dtc)

    panel["cost_zero"] = 0.0
    panel["cost_base"] = (
        ml30.per_stock_cost_bps(panel["spread_21"], COST_BASE_FLAT_BPS, COST_BASE_SPREAD_WEIGHT)
        / 1e4
    )
    panel["cost_stress"] = (
        ml30.per_stock_cost_bps(panel["spread_21"], COST_STRESS_FLAT_BPS, COST_STRESS_SPREAD_WEIGHT)
        / 1e4
    )
    panel["cost_flat10"] = (
        ml30.per_stock_cost_bps(panel["spread_21"], FLAT_REF_BASE_BPS, FLAT_REF_SPREAD_WEIGHT) / 1e4
    )
    panel["cost_flat20"] = (
        ml30.per_stock_cost_bps(panel["spread_21"], FLAT_REF_STRESS_BPS, FLAT_REF_SPREAD_WEIGHT)
        / 1e4
    )

    adv_bucket = pd.Series(pd.NA, index=panel.index, dtype="object")
    borrow_annual = pd.Series(np.nan, index=panel.index)
    for name, (lo, hi, rate) in ADV_BUCKETS.items():
        mask = (panel["dv21"] >= lo) & (panel["dv21"] < hi)
        adv_bucket = adv_bucket.mask(mask, name)
        borrow_annual = borrow_annual.mask(mask, rate)
    panel["adv_bucket"] = adv_bucket
    panel["borrow_annual"] = borrow_annual

    not_top_decile_dtc = panel["dtc_cross_sectional_pct"].isna() | (
        panel["dtc_cross_sectional_pct"] < DTC_TOP_DECILE
    )
    panel["short_eligible_main"] = (panel["dv21"] >= ADV_MIN_SHORT) & not_top_decile_dtc
    for name in ADV_BUCKETS:
        panel[f"short_eligible_{name}"] = panel["short_eligible_main"] & (
            panel["adv_bucket"] == name
        )
    return panel


# --------------------------------------------------------------------------
# stage: selection + returns (shared, agnostic to raw/sanitized origin)
# --------------------------------------------------------------------------


def select_side(panel: pd.DataFrame, mask: pd.Series, k: int, most_negative: bool) -> pd.DataFrame:
    """Top/bottom ``k`` names by ``z`` each day, within ``mask``. Ties broken
    by symbol (deterministic, ``method='first'`` after a stable sort)."""
    d = panel.loc[mask, ["date", "symbol", "z"]].copy()
    d = d.sort_values(["date", "symbol"], kind="stable")
    d["rank"] = d.groupby("date")["z"].rank(method="first", ascending=most_negative)
    return d.loc[d["rank"] <= k, ["date", "symbol"]]


def leg_return(
    sel: pd.DataFrame,
    panel_indexed: pd.DataFrame,
    cost_col: str,
    side: int,
    apply_borrow: bool,
) -> pd.Series:
    """Mean per-name contribution to the leg, grouped by day. ``side=+1`` for
    long, ``-1`` for short; cost is charged on entry and exit (2x the
    per-side cost); borrow is charged for the one day held, only on shorts."""
    m = sel.merge(panel_indexed, on=["date", "symbol"], how="inner")
    contrib = side * m["oc"] - 2.0 * m[cost_col]
    if apply_borrow:
        contrib = contrib - m["borrow_annual"].fillna(0.0) / BORROW_DAYCOUNT
    return contrib.groupby(m["date"]).mean()


def spy_leg_return(spy_oc: pd.Series, cost_bps: float) -> pd.Series:
    return spy_oc - 2.0 * cost_bps / 1e4


def combine_legs(a: pd.Series, b: pd.Series) -> pd.Series:
    df = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner")
    return df.mean(axis=1)


def placebo_sign_flip(panel: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Flip each day's z sign with probability 0.5 (equivalent to swapping
    that day's long and short legs); the sign is drawn once per date, shared
    by every symbol traded that day."""
    rng = np.random.default_rng(20260929 + seed)
    dates = panel["date"].drop_duplicates().sort_values()
    signs = pd.Series(rng.choice([-1.0, 1.0], size=len(dates)), index=dates.to_numpy())
    out = panel.copy()
    out["z"] = out["z"] * out["date"].map(signs).to_numpy()
    return out


# --------------------------------------------------------------------------
# stage: metrics + verdict
# --------------------------------------------------------------------------


def window_stats(ret: pd.Series, rf: pd.Series, window: tuple[str, str]) -> dict[str, float]:
    a, b = window
    mask = (ret.index >= a) & (ret.index <= b)
    turnover = pd.Series(2.0, index=ret.index)  # informational only, not used for cost
    m = base.metrics(ret.loc[mask], rf, turnover.loc[mask])
    return asdict(m)


def raw_stats(ret: pd.Series) -> dict[str, float]:
    """H-20260922-08's own ``stats()``: raw (not BIL-excess) Sharpe, used
    only for the hygiene recheck section so it matches the original card's
    own numbers directly."""
    ret = ret.dropna()
    if len(ret) < 30:
        return {}
    eq = (1.0 + ret).cumprod()
    years = len(ret) / 252.0
    return {
        "days": int(len(ret)),
        "cagr": float(eq.iloc[-1] ** (1.0 / years) - 1.0) if eq.iloc[-1] > 0 else -1.0,
        "sharpe": float(ret.mean() / ret.std(ddof=1) * np.sqrt(252.0))
        if ret.std(ddof=1) > 0
        else float("nan"),
        "max_dd": float((eq / eq.cummax() - 1.0).min()),
        "mean_bp": float(ret.mean() * 1e4),
    }


def _panel_idx_columns(panel: pd.DataFrame) -> pd.DataFrame:
    return panel[
        [
            "date",
            "symbol",
            "oc",
            "cost_zero",
            "cost_base",
            "cost_stress",
            "cost_flat10",
            "cost_flat20",
            "borrow_annual",
        ]
    ]


def original_card_recheck(panel: pd.DataFrame, latest: str) -> dict[str, Any]:
    """H-20260922-08's own judgement cell (liq $1M, K=10, gross -- no cost,
    no borrow, both legs drawn from the same unrestricted $1M panel, not the
    new ETB proxy) recomputed on whatever panel is passed in (raw or
    sanitized), so the size of the hygiene artifact in the original card's
    headline numbers is directly visible."""
    panel_idx = _panel_idx_columns(panel)
    all_true = pd.Series(True, index=panel.index)
    long_sel = select_side(panel, all_true, K, most_negative=True)
    short_sel = select_side(panel, all_true, K, most_negative=False)
    long_ret = leg_return(long_sel, panel_idx, "cost_zero", side=1, apply_borrow=False)
    short_ret = leg_return(short_sel, panel_idx, "cost_zero", side=-1, apply_borrow=False)
    ls_ret = combine_legs(long_ret, short_ret)
    windows = {"early": EARLY_ORIGINAL, "late": (LATE_ORIGINAL_START, latest)}
    out: dict[str, Any] = {"ls_combined": {}, "short_leg_alone": {}, "long_leg_alone": {}}
    for wname, w in windows.items():
        a, b = w
        for label, series in (
            ("ls_combined", ls_ret),
            ("short_leg_alone", short_ret),
            ("long_leg_alone", long_ret),
        ):
            mask = (series.index >= a) & (series.index <= b)
            out[label][wname] = raw_stats(series.loc[mask])
    return out


def run_variant(
    panel: pd.DataFrame,
    long_sel: pd.DataFrame,
    spy_ret_raw: pd.Series,
    rf: pd.Series,
    windows: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    panel_idx = _panel_idx_columns(panel)
    out: dict[str, Any] = {"universe": {}, "books": {}}
    for variant in VARIANTS:
        elig_col = "short_eligible_main" if variant == "main" else f"short_eligible_{variant}"
        short_sel = select_side(panel, panel[elig_col].fillna(False), K, most_negative=False)
        n_short_days = short_sel.groupby("date").size()
        out["universe"][variant] = {
            "short_selection_days": int(len(n_short_days)),
            "short_median_names_per_day": float(n_short_days.median())
            if len(n_short_days)
            else 0.0,
            "short_days_below_k": int((n_short_days < K).sum()),
        }
        for regime in COST_REGIMES:
            cost_col = f"cost_{regime}"
            long_ret = leg_return(long_sel, panel_idx, cost_col, side=1, apply_borrow=False)
            short_ret = leg_return(short_sel, panel_idx, cost_col, side=-1, apply_borrow=True)
            spy_cost_bps = {
                "base": COST_BASE_FLAT_BPS,
                "stress": COST_STRESS_FLAT_BPS,
                "flat10": FLAT_REF_BASE_BPS,
                "flat20": FLAT_REF_STRESS_BPS,
            }[regime]
            spy_ret = spy_leg_return(spy_ret_raw, spy_cost_bps)
            ls_ret = combine_legs(long_ret, short_ret)
            s_hedged_ret = combine_legs(short_ret, spy_ret)
            for book_name, ret in (("LS", ls_ret), ("S_hedged", s_hedged_ret)):
                key = f"{variant}/{book_name}/{regime}"
                out["books"][key] = {
                    wname: window_stats(ret, rf, w) for wname, w in windows.items()
                }
    return out


def verdict_for(book_stats: dict[str, dict[str, dict[str, float]]]) -> dict[str, Any]:
    def get(variant: str, book: str, regime: str, window: str, field: str) -> float:
        return book_stats[f"{variant}/{book}/{regime}"][window][field]

    out: dict[str, Any] = {}
    for variant in VARIANTS:
        for book in BOOK_TYPES:
            stress_sharpe = get(variant, book, "base", "stress", "sharpe")
            anchor_sharpe = get(variant, book, "base", "anchor", "sharpe")
            stress_cagr_stresscost = get(variant, book, "stress", "stress", "cagr")
            anchor_cagr_stresscost = get(variant, book, "stress", "anchor", "cagr")
            k1 = bool(
                np.isfinite(stress_sharpe)
                and np.isfinite(anchor_sharpe)
                and stress_sharpe >= K1_STRESS_SHARPE_MIN
                and anchor_sharpe >= K1_ANCHOR_SHARPE_MIN
                and stress_cagr_stresscost > 0
                and anchor_cagr_stresscost > 0
            )
            out[f"{variant}/{book}"] = {
                "stress_sharpe_base": stress_sharpe,
                "anchor_sharpe_base": anchor_sharpe,
                "stress_cagr_stresscost": stress_cagr_stresscost,
                "anchor_cagr_stresscost": anchor_cagr_stresscost,
                "k1_pass": k1,
            }
    return out


def _recompute_book_return(
    panel: pd.DataFrame,
    panel_idx: pd.DataFrame,
    long_sel: pd.DataFrame,
    variant: str,
    book: str,
    regime: str,
    spy_ret_raw: pd.Series,
) -> pd.Series:
    elig_col = "short_eligible_main" if variant == "main" else f"short_eligible_{variant}"
    short_sel = select_side(panel, panel[elig_col].fillna(False), K, most_negative=False)
    cost_col = f"cost_{regime}"
    long_ret = leg_return(long_sel, panel_idx, cost_col, side=1, apply_borrow=False)
    short_ret = leg_return(short_sel, panel_idx, cost_col, side=-1, apply_borrow=True)
    if book == "LS":
        return combine_legs(long_ret, short_ret)
    spy_cost_bps = {
        "base": COST_BASE_FLAT_BPS,
        "stress": COST_STRESS_FLAT_BPS,
        "flat10": FLAT_REF_BASE_BPS,
        "flat20": FLAT_REF_STRESS_BPS,
    }[regime]
    spy_ret = spy_leg_return(spy_ret_raw, spy_cost_bps)
    return combine_legs(short_ret, spy_ret)


def evaluate_panel(
    panel: pd.DataFrame,
    spy_ret_raw: pd.Series,
    etf_rf: pd.Series,
    etf_shy_ret: pd.Series,
    s3_ret: pd.Series,
    windows: dict[str, tuple[str, str]],
    seeds: int,
) -> dict[str, Any]:
    panel_idx = _panel_idx_columns(panel)
    long_sel = select_side(panel, pd.Series(True, index=panel.index), K, most_negative=True)
    _log(f"  long leg: {long_sel['date'].nunique():,} selection days")

    result = run_variant(panel, long_sel, spy_ret_raw, etf_rf, windows)
    book_stats = result["books"]

    real_stress_sharpe = {b: book_stats[f"main/{b}/base"]["stress"]["sharpe"] for b in BOOK_TYPES}
    real_anchor_sharpe = {b: book_stats[f"main/{b}/base"]["anchor"]["sharpe"] for b in BOOK_TYPES}
    placebo_sharpes: dict[str, dict[str, list[float]]] = {
        b: {"stress": [], "anchor": []} for b in BOOK_TYPES
    }
    for seed in range(seeds):
        flipped = placebo_sign_flip(panel, seed)
        p_long_sel = select_side(
            flipped, pd.Series(True, index=flipped.index), K, most_negative=True
        )
        p_short_sel = select_side(
            flipped, flipped["short_eligible_main"].fillna(False), K, most_negative=False
        )
        p_long_ret = leg_return(p_long_sel, panel_idx, "cost_base", side=1, apply_borrow=False)
        p_short_ret = leg_return(p_short_sel, panel_idx, "cost_base", side=-1, apply_borrow=True)
        p_spy_ret = spy_leg_return(spy_ret_raw, COST_BASE_FLAT_BPS)
        p_ls = combine_legs(p_long_ret, p_short_ret)
        p_sh = combine_legs(p_short_ret, p_spy_ret)
        for book, ret in (("LS", p_ls), ("S_hedged", p_sh)):
            for wname in ("stress", "anchor"):
                s = window_stats(ret, etf_rf, windows[wname])["sharpe"]
                placebo_sharpes[book][wname].append(s)
    placebo_summary = {
        book: {
            wname: {
                "median_sharpe": float(np.nanmedian(vals)) if vals else float("nan"),
                "beat_fraction": float(
                    np.mean(
                        [
                            v
                            > (real_stress_sharpe if wname == "stress" else real_anchor_sharpe)[
                                book
                            ]
                            for v in vals
                            if np.isfinite(v)
                        ]
                    )
                )
                if vals
                else float("nan"),
            }
            for wname, vals in windows_.items()
        }
        for book, windows_ in placebo_sharpes.items()
    }

    k2_results: dict[str, Any] = {}
    for variant in VARIANTS:
        for book in BOOK_TYPES:
            key = f"{variant}/{book}"
            cand_ret = _recompute_book_return(
                panel, panel_idx, long_sel, variant, book, "base", spy_ret_raw
            )
            k2_results[key] = {
                wname: screen_lane.diversifier_edge_for_offset(
                    s3_ret, cand_ret, etf_shy_ret, etf_rf, windows[wname]
                )
                for wname in ("stress", "anchor")
            }

    verdict = verdict_for(book_stats)
    for key, edges in k2_results.items():
        k2_pass = bool(edges["stress"] >= K2_EDGE_MIN and edges["anchor"] >= K2_EDGE_MIN)
        verdict[key]["k2_edge"] = edges
        verdict[key]["k2_pass"] = k2_pass
        verdict[key]["verdict"] = (
            "keep_K1" if verdict[key]["k1_pass"] else ("keep_K2" if k2_pass else "reject")
        )

    return {
        "short_universe": result["universe"],
        "books": book_stats,
        "placebo": placebo_summary,
        "k2_edge": k2_results,
        "verdict": verdict,
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--seeds", type=int, default=PLACEBO_SEEDS)
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    _log("loading raw wide matrices")
    wide = load_wide_matrices(force=args.force)
    close_raw, open_raw, high_raw, low_raw, volume = (
        wide["close"],
        wide["open"],
        wide["high"],
        wide["low"],
        wide["volume"],
    )

    _log("applying price_hygiene.mask_regime_breaks (default thresholds) to close/open/high/low")
    (close_san, open_san, high_san, low_san), hygiene_report = ph.mask_regime_breaks(
        close_raw, open_raw, high_raw, low_raw
    )
    _log(
        f"hygiene: {hygiene_report.symbols_masked} symbols masked "
        f"({hygiene_report.symbols_masked_for_jump} jump, "
        f"{hygiene_report.symbols_masked_for_gap} gap), "
        f"{hygiene_report.price_cells_masked:,} close cells blanked"
    )

    _log("building raw signal panel (no hygiene, no split filter -- matches the original card)")
    panel_raw_signal = build_signal_panel(close_raw, open_raw, volume, filter_split_like=False)
    _log("building sanitized signal panel (hygiene-masked + split-like trigger filter)")
    panel_san_signal = build_signal_panel(close_san, open_san, volume, filter_split_like=True)
    n_split_dropped = int(
        len(build_signal_panel(close_san, open_san, volume, filter_split_like=False))
        - len(panel_san_signal)
    )
    _log(
        f"panel rows: raw={len(panel_raw_signal):,} sanitized_pre_split_filter="
        f"{len(panel_san_signal) + n_split_dropped:,} sanitized={len(panel_san_signal):,} "
        f"(split-like trigger rows dropped: {n_split_dropped:,})"
    )

    dtc = load_dtc()
    _log("attaching spread + DTC + costs (raw panel, raw high/low)")
    panel_raw = add_costs_and_eligibility(panel_raw_signal, close_raw, high_raw, low_raw, dtc)
    _log("attaching spread + DTC + costs (sanitized panel, sanitized high/low)")
    panel_san = add_costs_and_eligibility(panel_san_signal, close_san, high_san, low_san, dtc)

    latest_date = max(panel_raw["date"].max(), panel_san["date"].max())
    windows = {
        "stress": WINDOWS_TEMPLATE["stress"],
        "select": WINDOWS_TEMPLATE["select"],
        "anchor": (WINDOWS_TEMPLATE["anchor"][0], latest_date.strftime("%Y-%m-%d")),
    }
    latest_str = latest_date.strftime("%Y-%m-%d")
    _log(f"latest date {latest_date.date()}; windows {windows}")

    base.WARMUP_START = screen_lane.PANEL_START
    etf_close, etf_open = base.load_panel(salvage.symbols())
    spy_ret_raw = (etf_close["SPY"] / etf_open["SPY"] - 1.0).dropna()
    etf_rf = (etf_close[screen_lane.RF] / etf_close[screen_lane.RF].shift(1) - 1.0).fillna(0.0)
    etf_shy_ret = (etf_close[screen_lane.CASH] / etf_close[screen_lane.CASH].shift(1) - 1.0).fillna(
        0.0
    )
    s3_ret, _s3_turn = screen_lane.s3_incumbent(
        etf_close, *salvage.legs(etf_close, etf_open), screen_lane.COST_BPS_PRIMARY
    )

    _log("original-card hygiene recheck (raw)")
    recheck_raw = original_card_recheck(panel_raw, latest_str)
    _log("original-card hygiene recheck (sanitized)")
    recheck_san = original_card_recheck(panel_san, latest_str)

    _log("evaluating RAW panel (reference only, not used for the verdict)")
    eval_raw = evaluate_panel(
        panel_raw, spy_ret_raw, etf_rf, etf_shy_ret, s3_ret, windows, args.seeds
    )
    _log("evaluating SANITIZED panel (verdict)")
    eval_san = evaluate_panel(
        panel_san, spy_ret_raw, etf_rf, etf_shy_ret, s3_ret, windows, args.seeds
    )

    payload = {
        "iteration_id": ITERATION_ID,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "k_per_leg": K,
        "windows": windows,
        "contaminated_start": CONTAMINATED_START,
        "hygiene_report": hygiene_report.manifest(),
        "split_like_filter": {
            "candidates": list(SPLIT_LIKE_RATIOS),
            "log_tol": SPLIT_LIKE_LOG_TOL,
            "sanitized_rows_dropped": n_split_dropped,
        },
        "panel_rows": {"raw": int(len(panel_raw)), "sanitized": int(len(panel_san))},
        "panel_symbols": {
            "raw": int(panel_raw["symbol"].nunique()),
            "sanitized": int(panel_san["symbol"].nunique()),
        },
        "dtc_coverage_of_panel_rows": {
            "raw": float(panel_raw["dtc_cross_sectional_pct"].notna().mean()),
            "sanitized": float(panel_san["dtc_cross_sectional_pct"].notna().mean()),
        },
        "original_card_recheck": {"raw": recheck_raw, "sanitized": recheck_san},
        "raw": eval_raw,
        "sanitized": eval_san,
        "verdict_source": "sanitized",
        "rebalance_offsets": "not applicable -- one-day holding period, every session re-selected",
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, default=_json_default) + "\n")
    _log(f"wrote {RESULTS_PATH}")

    _log("=== original-card recheck: late-window short leg alone, gross ===")
    for tag, rc in (("raw", recheck_raw), ("sanitized", recheck_san)):
        late = rc["short_leg_alone"].get("late", {})
        sharpe = late.get("sharpe", float("nan"))
        cagr = late.get("cagr", float("nan"))
        _log(f"  {tag}: sharpe={sharpe:.2f} cagr={cagr:.2%}")

    _log("=== sanitized verdict ===")
    for key, v in eval_san["verdict"].items():
        _log(
            f"{key}: stress_sharpe={v['stress_sharpe_base']:.2f} "
            f"anchor_sharpe={v['anchor_sharpe_base']:.2f} k1={v['k1_pass']} "
            f"k2_edge={v['k2_edge']} k2={v['k2_pass']} -> {v['verdict']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
