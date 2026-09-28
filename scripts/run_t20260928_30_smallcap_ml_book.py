"""T-20260928-30: long-only book from the frozen B0 price-volume LightGBM
ranking model, with per-stock spread costs, capacity caps and a turnover
buffer -- judged by the owner's K1/K2 keep tiers.

Direction: ``dir:lgbm_price_volume_ranking_small_caps``
(``reports/research/harvest/directions.jsonl``). Prior evidence: the T-
20260928-10 kill test (``reports/research/iterations/t20260928_10_ml_killtest/
report.md``, "第二次运行") found B0 -- LightGBM regression on 24 price-volume
features, monthly formation, target 21-day beta-adjusted excess demeaned
within (date, ADV quintile), 3-year rolling training, quarterly retrain,
embargo 21, fixed hyperparameters, NaN rows kept -- has real walk-forward
RankIC in a widened (close>=$3, 21d dollar ADV>=$1M) universe: 0.020 (t 3.12)
overall, 0.031 (t 5.75) in the illiquid tercile. That test measured ranking
quality only (validation-role RankIC at monthly formation dates), no
portfolio, no costs. This task turns the same frozen model into a tradable
book and prices it honestly.

**Reused, unmodified** (imported, never edited -- see this repo's frozen-file
convention): ``scripts/run_t20260928_10_ml_killtest.py`` (``kt`` below) for
the B0 candidate spec, its LightGBM model class/hyperparameters, the PIT
universe loader, the price-matrix loader, and the monthly cohort/target/
rank-normalize helpers; ``scripts/run_h20260917_02_ml_ranking.py`` (``h02``)
for ``Fold``/``build_folds``/``embargo_cutoff`` (via ``kernel.loop``) and the
24-column ``DAILY_FEATURE_COLUMNS`` registry; ``scripts/screen_lane.py`` for
the vol-matched S3 diversifier-edge computation (K2); ``scripts/
run_h20260928_01_s3_rebalance_tranching.py`` for ``shifted_signal_dates``
(the repo's one definition of "21 monthly rebalance offsets" -- month-end
signal sessions moved 0..20 trading sessions later) and the G1/G1' gate
constants (informative only, not this task's verdict rule);
``scripts/run_h20260922_05_salvage.py`` / ``scripts/
run_h20260918_05_recent_menu.py`` for the S3 sleeve universe and its price
panel loader (needed only for K2, a completely different symbol set --
ETFs -- from this task's own stock panel).

**New in this script** (not available anywhere else, because nothing else in
the repo needs per-stock costs or a full-daily-calendar prediction panel):
the Abdi-Ranaldo (2017) spread estimator (:func:`abdi_ranaldo_pair_terms` /
:func:`spread_estimate_from_ohlc`, unit-tested), the turnover-buffered top-N
selection (:func:`buffered_selection`, unit-tested), the capacity cap
(:func:`capacity_capped_weight`, unit-tested), the daily-cohort builder that
generalizes ``kt.build_cohort_frames``'s biweekly step to every trading day
(:func:`build_daily_cohort`), and the per-stock-cost portfolio engine
(:func:`simulate_book`) -- none of the existing simulators
(``salvage.simulate``, ``base.portfolio_returns``, ``tranche.
simulate_effective``) take a per-(date, symbol) cost, only one scalar
``cost_bps`` for the whole book.

Spec (frozen before any return was computed, see the task brief
T-20260928-30 and ``reports/research/harvest/directions.jsonl``'s
``dir:lgbm_price_volume_ranking_small_caps`` row):

* Model: B0 exactly -- same 24 features, same fixed LightGBM
  hyperparameters, same 3-year rolling / quarterly retrain / embargo-21
  schedule. Trained on the *monthly* formation dates as before (``kt``'s
  monthly cohort), but the resulting fold model is applied to **every
  trading day** in the quarter that fold's ``test_dates`` role covers (the
  quarter after the validation quarter -- the same "traded portfolio only
  ever reads the test role" convention ``h02.build_folds``'s own docstring
  already documents), so all 21 monthly rebalance offsets have daily
  coverage, not just month-ends. Predictions therefore start with the
  earliest fold's test quarter, not at the archive's first date (2016-01) --
  the actual first predicted date is recorded in ``results.json`` and used
  as each window's *actual* start.
* Universe each day: the existing PIT universe (``data/features/
  universe_t20260928_10``, close>=$3, 21d mean dollar ADV>=$1M), membership
  and ADV rank held constant between month-ends (point-in-time -- this is
  the same convention ``kt.build_cohort_frames`` already uses for its
  biweekly cadence, generalized here to daily; documented, not a silent
  shortcut). Liquidity terciles are the month-end cohort's own ADV-rank
  tercile, also held constant intra-month.
* V1: top 50 by prediction, whole eligible universe that day. V2: top 50
  within the illiquid tercile (``T3_illiquid``) only. Equal weight (1 /
  number of names actually selected, typically 50); turnover buffer keeps a
  previously-held name unless its current rank exceeds 150 (within the same
  universe V1/V2 draws from); the book is topped back up to exactly 50 names
  (or fewer if the eligible pool that day is smaller) with the best-ranked
  names not already held (:func:`buffered_selection`). Monthly rebalance =
  ``tranche.shifted_signal_dates`` (calendar month-end shifted 0..20 trading
  sessions later -- the repo's one existing definition of "21 monthly
  rebalance offsets"); signal at that day's close, weights effective at the
  next session's open, held constant (no intra-period drift modeled -- same
  simplification as every other book in this repo, ``base.portfolio_returns``
  /``salvage.simulate``).
* Costs, per side per stock: base = 10 bp + 0.5 x spread; stress = 20 bp +
  1.0 x spread; flat10/flat20 bp reported for reference. Spread = Abdi-
  Ranaldo (2017) close-high-low estimator ("two-day corrected" variant, their
  preferred one), trailing 21 trading days of (close, high, low) from
  ``data/sip/daily`` (which carries high/low; ``data/features/daily_broad``
  does not), floored at 0 and capped at 5%, point-in-time (uses only data
  through the signal date).
* Capacity: $100,000 account; each position <= 1% of that stock's own
  trailing 21-day **median** daily dollar volume (close x volume, from
  ``data/sip/daily`` -- deliberately the *median*, not the mean ADV the
  eligibility filter uses; different metric for a different purpose, kept
  distinct on purpose). Weight above the cap is not redistributed -- it
  stays uninvested (idle, 0%-return cash), matching the brief exactly.
* Metrics: reuse ``run_h20260918_05_recent_menu.metrics`` (``base.metrics``)
  unmodified for CAGR/Sharpe/max-DD/turnover-per-year on each offset's daily
  net-return series; report the median/min/max over the 21 offsets (never a
  single hand-picked offset). Windows: stress 2016-05-02..2023-08-31 (from
  the first predicted date), select 2023-09-18..2025-12-31, anchor
  2024-01-08..(latest data date), holdout 2026-01-02..2026-09-17 (flagged
  contaminated, reference only).
* Placebo: 20 random-rank books per variant (same universe, N, buffer,
  costs, offsets -- only the ranking is replaced by a random permutation
  each seed); reported win rate = the fraction of the 20 placebo offset-
  median Sharpes the real book's offset-median Sharpe beats, at base cost,
  in stress and anchor.
* K2: ``screen_lane.diversifier_edge_for_offset`` (Sharpe of an inverse-vol
  S3+candidate combination minus a vol-matched k*S3+(1-k)*SHY control),
  offset-median, base cost, stress and anchor.
* Verdict (fixed, not touched after seeing numbers): **keep (K1)** if
  offset-median Sharpe at base cost >= 0.65 (stress) and >= 1.19 (anchor)
  AND CAGR > 0 at stress cost in both windows; **keep (K2)** if the S3
  combination edge >= +0.05 in both windows; else **reject**. G1/G1' status
  is reported as informative only (``tranche.passes_g1_or_g1alt``, this
  task's own verdict does not depend on it). DSR-style caution: this
  family's cumulative trial count is 6 (T-20260928-10's B0/5/6/11 kill-test
  cells + this task's V1/V2), reported via ``campaign_statistics.
  deflated_sharpe_probability`` on each variant's judged anchor-window
  excess-return series -- informative, not a gate.

Usage (Modal; see ``scripts/modal_run.py`` docstring)::

    python3 scripts/modal_budget.py check --job t20260928-30-smoke --cpu 2 \\
        --memory-gib 8 --timeout-min 15
    python3 scripts/modal_run.py --job t20260928-30-smoke --cpu 2 --memory-gib 8 \\
        --timeout-min 15 \\
        --data data/features/universe_t20260928_10 --data data/features/daily_broad \\
        --data data/sip/daily \\
        --out reports/research/iterations/t20260928_30_smallcap_ml_book \\
        --fetch-to reports/research/control/scratch/t20260928_30_smoke \\
        -- uv run python -u scripts/run_t20260928_30_smallcap_ml_book.py --stage all \\
        --smoke --window-start 2022-01-01 --window-end 2022-12-31 --max-symbols 200

    python3 scripts/modal_budget.py check --job t20260928-30-real --cpu 8 \\
        --memory-gib 32 --timeout-min 90
    python3 scripts/modal_run.py --job t20260928-30-real --cpu 8 --memory-gib 32 \\
        --timeout-min 90 \\
        --data data/features/universe_t20260928_10 --data data/features/daily_broad \\
        --data data/sip/daily \\
        --out reports/research/iterations/t20260928_30_smallcap_ml_book \\
        -- uv run python -u scripts/run_t20260928_30_smallcap_ml_book.py --stage all --force
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

from open_composer.research.campaign_statistics import deflated_sharpe_probability  # noqa: E402
from open_composer.research.features import price_hygiene  # noqa: E402
from scripts import run_h20260917_02_ml_ranking as h02  # noqa: E402
from scripts import run_h20260918_05_recent_menu as base  # noqa: E402
from scripts import run_h20260922_05_salvage as salvage  # noqa: E402
from scripts import run_h20260928_01_s3_rebalance_tranching as tranche  # noqa: E402
from scripts import run_t20260928_10_ml_killtest as kt  # noqa: E402
from scripts import screen_lane  # noqa: E402

ITERATION_ID = "t20260928_30_smallcap_ml_book"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = OUT_DIR / "cache"
RESULTS_PATH = OUT_DIR / "results.json"
REPORT_PATH = OUT_DIR / "report.md"
SIP_DAILY_GLOB = str(ROOT / "data" / "sip" / "daily" / "*" / "*.parquet")

# --------------------------------------------------------------------------
# frozen spec constants
# --------------------------------------------------------------------------

DEFAULT_WINDOW_START = "2016-01-04"  # data start; actual stress start is the first predicted date
DEFAULT_WINDOW_END = None  # latest date in the archive, resolved at runtime

WINDOWS_TEMPLATE: dict[str, tuple[str, str | None]] = {
    "stress": (None, "2023-08-31"),  # start = first predicted date, floored at 2016-05-02
    "select": ("2023-09-18", "2025-12-31"),
    "anchor": ("2024-01-08", None),  # end = latest data date
    "holdout": ("2026-01-02", "2026-09-17"),
}
CONTAMINATED_WINDOWS = frozenset({"holdout"})
STRESS_FLOOR = pd.Timestamp("2016-05-02")

N_TOP = 50
BUFFER_RANK = 150
ACCOUNT_VALUE = 100_000.0
CAPACITY_FRACTION = 0.01
SPREAD_FLOOR = 0.0
SPREAD_CAP = 0.05
SPREAD_WINDOW_DAYS = 21
LIQUIDITY_WINDOW_DAYS = 21

COST_BASE_FLAT_BPS = 10.0
COST_STRESS_FLAT_BPS = 20.0
COST_BASE_SPREAD_WEIGHT = 0.5
COST_STRESS_SPREAD_WEIGHT = 1.0

OFFSETS: list[int] = list(range(21))
PLACEBO_SEEDS = 20

K1_STRESS_SHARPE_MIN = 0.65
K1_ANCHOR_SHARPE_MIN = 1.19
K2_EDGE_MIN = 0.05

# T-20260928-10's four kill-test cells (B0/5/6/11) + this task's two variants
# (V1/V2) -- see module docstring's DSR paragraph.
DSR_TRIAL_COUNT = 6
DSR_HAC_LAG = screen_lane.DSR_HAC_LAG  # 21, matches the lane's own convention

_T0 = time.time()


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')} +{time.time() - _T0:7.1f}s] {message}", flush=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=h02._json_default) + "\n"
    )


# --------------------------------------------------------------------------
# pure functions -- unit tested in tests/test_t20260928_30_smallcap_ml_book.py
# --------------------------------------------------------------------------


def abdi_ranaldo_pair_terms(close: pd.Series, high: pd.Series, low: pd.Series) -> pd.Series:
    """Abdi & Ranaldo (2017, Review of Financial Studies 30(12):4437-4480)
    close-high-low spread estimator, per-pair term. Source for the exact
    formula (the paper's own PDF is not machine-extractable; this lecture
    summary reproduces its equations directly):
    https://ba-odegaard.no/teach/notes/liquidity_estimators/
    abdi_ranaldo_high_low_estimator/slides_high_low_ar.pdf (citing Abdi &
    Ranaldo 2017 sec. "Defining the estimator").

    eta_t = (ln(high_t) + ln(low_t)) / 2   (log mid-range -- the paper's
        proxy for the efficient price: high/low are each assumed to have
        touched one side of the spread, so their midpoint cancels the two
        half-spreads).
    c_t = ln(close_t)
    S_t^2 = (c_t - eta_t) * (c_t - eta_{t+1})   -- the two-day pair term.

    Returned series is indexed like the input (one symbol, ascending dates):
    position i holds sqrt(max(S_{i-1}^2, 0)), i.e. the term formed from days
    (i-1, i) -- attributed to day i because it is only computable once day
    i's own high/low are known (no look-ahead: as of the close of day i, the
    term for pair (i-1, i) is knowable). Position 0 is NaN (no prior day).
    """
    c = np.log(close.to_numpy(dtype="float64"))
    eta = (np.log(high.to_numpy(dtype="float64")) + np.log(low.to_numpy(dtype="float64"))) / 2.0
    n = len(c)
    out = np.full(n, np.nan, dtype="float64")
    if n >= 2:
        raw = (c[:-1] - eta[:-1]) * (c[:-1] - eta[1:])
        out[1:] = np.sqrt(np.maximum(raw, 0.0))
    return pd.Series(out, index=close.index)


def rolling_spread_estimate(pair_terms: pd.Series, window_pairs: int) -> pd.Series:
    """Trailing mean of :func:`abdi_ranaldo_pair_terms` over ``window_pairs``
    consecutive pair terms (Abdi & Ranaldo's "two-day corrected" variant --
    their preferred one, an average of ``S_t`` rather than a single pooled
    covariance). ``min_periods=window_pairs`` so an incomplete window is NaN
    rather than a noisy partial estimate."""
    return pair_terms.rolling(window_pairs, min_periods=window_pairs).mean()


def spread_estimate_from_ohlc(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    window_days: int = SPREAD_WINDOW_DAYS,
    floor: float = SPREAD_FLOOR,
    cap: float = SPREAD_CAP,
) -> pd.Series:
    """Point-in-time trailing ``window_days``-day Abdi-Ranaldo spread
    estimate (``window_days`` raw close/high/low observations ->
    ``window_days - 1`` pair terms), floored at ``floor`` and capped at
    ``cap`` (the brief's own bounds)."""
    terms = abdi_ranaldo_pair_terms(close, high, low)
    est = rolling_spread_estimate(terms, window_pairs=window_days - 1)
    return est.clip(lower=floor, upper=cap)


def buffered_selection(
    previous_holdings: set[str],
    ranked_symbols: list[str],
    n_target: int,
    buffer_rank: int,
) -> list[str]:
    """Turnover-buffered top-N selection. ``ranked_symbols`` is best-first
    (rank 1 = best) within the relevant universe (whole book for V1, the
    illiquid tercile only for V2). A previously-held name is retained if its
    *current* rank is <= ``buffer_rank``; retained names beyond ``n_target``
    (only possible if more than ``n_target`` old holdings still qualify) are
    trimmed to the best-ranked ``n_target`` of them, so the book always ends
    at exactly ``n_target`` names (or fewer if ``ranked_symbols`` itself has
    fewer than ``n_target`` entries -- e.g. an early, thin illiquid
    tercile). Remaining slots are filled with the best-ranked names not
    already retained. Deterministic, no randomness."""
    rank_of = {s: i + 1 for i, s in enumerate(ranked_symbols)}
    retained = [s for s in ranked_symbols if s in previous_holdings and rank_of[s] <= buffer_rank]
    retained = sorted(retained, key=lambda s: rank_of[s])[:n_target]
    retained_set = set(retained)
    out = list(retained)
    for s in ranked_symbols:
        if len(out) >= n_target:
            break
        if s not in retained_set:
            out.append(s)
    return out


def capacity_capped_weight(
    equal_weight: float,
    dollar_vol_median_21: float,
    account_value: float = ACCOUNT_VALUE,
    cap_fraction: float = CAPACITY_FRACTION,
) -> float:
    """Position weight after the capacity constraint: at most
    ``cap_fraction`` of the stock's own trailing 21-day *median* dollar
    volume, expressed as a fraction of ``account_value``. Weight above the
    cap is **not** redistributed to other names -- it stays uninvested
    (idle, 0%-return cash), exactly as the brief specifies."""
    if not np.isfinite(dollar_vol_median_21) or dollar_vol_median_21 <= 0 or account_value <= 0:
        return 0.0
    cap_weight = (cap_fraction * dollar_vol_median_21) / account_value
    return float(min(max(equal_weight, 0.0), max(cap_weight, 0.0)))


def per_stock_cost_bps(spread: pd.Series, flat_bps: float, spread_weight: float) -> pd.Series:
    """``flat_bps + spread_weight * spread * 10_000`` -- ``spread`` is a
    fraction of price (e.g. 0.01 = 1%), converted to bps here so the caller
    always works in bps."""
    spread_bps = spread.fillna(0.0) * 10_000.0
    return flat_bps + spread_weight * spread_bps


# --------------------------------------------------------------------------
# stage: cohort -- daily universe membership + rank-normalized B0 features
# --------------------------------------------------------------------------


def _years_for_window(window_start: str, window_end: str) -> list[int]:
    return list(range(pd.Timestamp(window_start).year, pd.Timestamp(window_end).year + 1))


def build_daily_cohort(
    custom_universe: pd.DataFrame,
    trading_calendar: pd.DatetimeIndex,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> pd.DataFrame:
    """``(trade_date, symbol, adv_rank, dollar_adv)`` for every trading day
    in ``[window_start, window_end]`` -- daily generalization of
    ``kt.build_cohort_frames``'s biweekly cohort: each day's membership is
    the most recently known (point-in-time) month-end cohort, updated only
    at real month-ends. Built as one cross-join per month-end block (not one
    merge per day) for speed at ~2,500 trading days x ~3,500 symbols/day."""
    universe = custom_universe.copy()
    universe["month_end"] = h02._ns(universe["month_end"])
    universe["symbol"] = universe["symbol"].astype(str)
    cohort_sizes = universe.groupby("month_end").size()
    valid_month_ends = sorted(
        d
        for d in universe["month_end"].unique()
        if cohort_sizes.get(d, 0) >= h02.DEFAULT_MIN_COHORT_SYMBOLS
    )
    if not valid_month_ends:
        return pd.DataFrame(columns=["trade_date", "symbol", "adv_rank", "dollar_adv"])
    groups = {
        me: universe.loc[universe["month_end"] == me, ["symbol", "adv_rank", "dollar_adv"]]
        for me in valid_month_ends
    }
    cal = trading_calendar[(trading_calendar >= window_start) & (trading_calendar <= window_end)]
    boundaries = list(valid_month_ends) + [pd.Timestamp(window_end) + pd.Timedelta(days=1)]
    frames = []
    for i, me in enumerate(valid_month_ends):
        lo, hi = boundaries[i], boundaries[i + 1]
        days = cal[(cal >= lo) & (cal < hi)]
        if len(days) == 0:
            continue
        g = groups[me]
        block = pd.DataFrame(
            {
                "trade_date": np.repeat(days.to_numpy(), len(g)),
                "symbol": np.tile(g["symbol"].to_numpy(), len(days)),
                "adv_rank": np.tile(g["adv_rank"].to_numpy(), len(days)),
                "dollar_adv": np.tile(g["dollar_adv"].to_numpy(), len(days)),
            }
        )
        frames.append(block)
    return (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=["trade_date", "symbol", "adv_rank", "dollar_adv"])
    )


def add_adv_tercile_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """Same qcut logic as ``kt.add_adv_tercile``, generalized to a
    ``trade_date`` column instead of ``formation_date`` (that function
    groups by a hardcoded column name)."""

    def _tercile(s: pd.Series) -> pd.Series:
        try:
            return pd.qcut(s, 3, labels=["T1_liquid", "T2_mid", "T3_illiquid"], duplicates="drop")
        except ValueError:
            return pd.Series(["T1_liquid"] * len(s), index=s.index)

    frame = frame.copy()
    frame["adv_tercile"] = frame.groupby("trade_date")["adv_rank"].transform(_tercile).astype(str)
    return frame


def rank_normalize_daily(frame: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    """Percentile rank of each feature within its day's cross-section --
    same operation as ``kt.rank_normalize_and_filter`` (percentile rank
    within ``formation_date``), applied per ``trade_date`` here so every
    trading day, not just formation dates, is rank-normalized the same way
    the training panel was."""
    frame = frame.copy()
    for c in feature_columns:
        frame[c] = frame.groupby("trade_date")[c].rank(pct=True)
    return frame


def stage_cohort(args: argparse.Namespace) -> None:
    manifest_path = CACHE_DIR / "cohort_manifest.json"
    if manifest_path.exists() and not args.force:
        _log(f"cohort: {manifest_path} present -- reusing (pass --force to rebuild)")
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    window_start = pd.Timestamp(args.window_start)
    window_end = pd.Timestamp(args.window_end)
    years = _years_for_window(args.window_start, args.window_end)
    _log(f"cohort: window {window_start.date()}..{window_end.date()}, years={years}")

    custom_universe = kt.load_universe_panel(kt.CUSTOM_UNIVERSE_ROOT, years=years)
    if args.max_symbols is not None:
        custom_universe = custom_universe.loc[custom_universe["adv_rank"] <= args.max_symbols]
    n_sym = custom_universe["symbol"].nunique()
    _log(f"cohort: universe {len(custom_universe):,} rows, {n_sym:,} symbols")

    close_wide, open_wide, daily_raw = kt.load_price_matrices(years)
    trading_calendar = close_wide.index
    close_sanitized, open_sanitized, hygiene_report = price_hygiene.sanitize_price_matrices(
        close_wide, open_wide
    )
    _log(
        f"cohort: price hygiene masked {hygiene_report.symbols_masked} symbols "
        f"({hygiene_report.price_cells_masked} cells)"
    )
    if "SPY" not in close_sanitized.columns:
        _log("cohort: SPY missing from panel, fetching benchmark prices")
        bench_close, _bench_open = h02._benchmark_prices(("SPY",))
        close_sanitized["SPY"] = bench_close.reindex(close_sanitized.index)["SPY"]
        _log("cohort: SPY benchmark fetched")
    else:
        _log("cohort: SPY already present in panel")

    # ---- monthly training panel (same construction as kt's B0 candidate) ----
    monthly_cohort, _biweekly_unused = kt.build_cohort_frames(
        custom_universe, trading_calendar, window_start, window_end, None
    )
    _log(f"cohort: monthly_cohort {len(monthly_cohort):,} rows")
    monthly_panel = kt.attach_daily_features(monthly_cohort, daily_raw)
    _log(f"cohort: attach_daily_features -> {len(monthly_panel):,} rows")
    monthly_panel = kt.build_target(monthly_panel, close_sanitized, horizon=21)
    _log("cohort: build_target done")
    monthly_panel = kt.add_adv_tercile(monthly_panel)
    _log("cohort: add_adv_tercile done")
    monthly_panel, kept_features, coverage = kt.rank_normalize_and_filter(
        monthly_panel, kt.BASE_FEATURE_COLUMNS
    )
    _log("cohort: rank_normalize_and_filter done")
    monthly_panel.to_parquet(CACHE_DIR / "monthly_panel.parquet", index=False)
    _log(
        f"cohort: monthly training panel {len(monthly_panel):,} rows, "
        f"{monthly_panel['formation_date'].nunique()} dates, "
        f"{len(kept_features)}/{len(kt.BASE_FEATURE_COLUMNS)} features kept"
    )

    # ---- daily cohort for prediction (every trading day) ----
    daily_cohort = build_daily_cohort(custom_universe, trading_calendar, window_start, window_end)
    _log(f"cohort: build_daily_cohort -> {len(daily_cohort):,} rows")
    daily_cohort = add_adv_tercile_daily(daily_cohort)
    _log("cohort: add_adv_tercile_daily done")
    daily_feature_cols = [*kt.BASE_FEATURE_COLUMNS, h02.BETA_COLUMN]
    daily_features = daily_raw[["symbol", "trade_date", *daily_feature_cols]].copy()
    daily_features["trade_date"] = h02._ns(daily_features["trade_date"])
    daily_features["symbol"] = daily_features["symbol"].astype(str)
    daily_cohort = daily_cohort.merge(daily_features, on=["trade_date", "symbol"], how="left")
    _log(f"cohort: merged daily features -> {len(daily_cohort):,} rows")
    daily_cohort = rank_normalize_daily(daily_cohort, kept_features)
    _log("cohort: rank_normalize_daily done")
    daily_cohort.to_parquet(CACHE_DIR / "daily_cohort.parquet", index=False)
    _log(f"cohort: daily prediction panel {len(daily_cohort):,} rows")

    close_sanitized.to_parquet(CACHE_DIR / "close_sanitized.parquet")
    open_sanitized.to_parquet(CACHE_DIR / "open_sanitized.parquet")

    manifest = {
        "window_start": args.window_start,
        "window_end": args.window_end,
        "years": years,
        "smoke": bool(args.smoke),
        "max_symbols": args.max_symbols,
        "kept_features": kept_features,
        "feature_coverage": coverage,
        "monthly_panel_rows": int(len(monthly_panel)),
        "daily_cohort_rows": int(len(daily_cohort)),
        "trading_calendar_sessions": int(len(trading_calendar)),
        "trading_calendar_start": str(trading_calendar[0].date()),
        "trading_calendar_end": str(trading_calendar[-1].date()),
    }
    _write_json(manifest_path, manifest)
    _log(f"cohort: wrote {manifest_path}")


# --------------------------------------------------------------------------
# stage: liquidity -- Abdi-Ranaldo spread + trailing median dollar volume
# --------------------------------------------------------------------------


def stage_liquidity(args: argparse.Namespace) -> None:
    out_path = CACHE_DIR / "liquidity.parquet"
    if out_path.exists() and not args.force:
        _log(f"liquidity: {out_path} present -- reusing (pass --force to rebuild)")
        return
    manifest = json.loads((CACHE_DIR / "cohort_manifest.json").read_text())
    symbols = sorted(
        pd.read_parquet(CACHE_DIR / "daily_cohort.parquet", columns=["symbol"])["symbol"].unique()
    )
    win = f"{manifest['window_start']}..{manifest['window_end']}"
    _log(f"liquidity: {len(symbols)} symbols, window {win}")

    con = duckdb.connect()
    con.execute(f"SET memory_limit='{args.duckdb_memory}'")
    con.execute(f"SET threads={args.duckdb_threads}")
    symbols_sql = ",".join("'" + s.replace("'", "''") + "'" for s in symbols)
    query = f"""
    WITH raw AS (
        SELECT symbol, timestamp::DATE AS trade_date, close, high, low, volume
        FROM read_parquet('{SIP_DAILY_GLOB}')
        WHERE symbol IN ({symbols_sql})
          AND timestamp::DATE >= DATE '{manifest["window_start"]}'
          AND timestamp::DATE <= DATE '{manifest["window_end"]}'
          AND close > 0 AND high > 0 AND low > 0
          AND NOT (volume <= 0)
    ),
    mid AS (
        SELECT symbol, trade_date, close, high, low, volume,
               (ln(high) + ln(low)) / 2.0 AS eta,
               LEAD((ln(high) + ln(low)) / 2.0) OVER w AS eta_next
        FROM raw
        WINDOW w AS (PARTITION BY symbol ORDER BY trade_date)
    ),
    pair AS (
        SELECT symbol, trade_date, close * volume AS dollar_vol,
               sqrt(greatest((ln(close) - eta) * (ln(close) - eta_next), 0.0)) AS s_t
        FROM mid
        WHERE eta_next IS NOT NULL
    )
    SELECT symbol, trade_date,
           AVG(s_t) OVER (
               PARTITION BY symbol ORDER BY trade_date
               ROWS BETWEEN {SPREAD_WINDOW_DAYS - 2} PRECEDING AND CURRENT ROW
           ) AS spread_raw,
           COUNT(s_t) OVER (
               PARTITION BY symbol ORDER BY trade_date
               ROWS BETWEEN {SPREAD_WINDOW_DAYS - 2} PRECEDING AND CURRENT ROW
           ) AS spread_n,
           MEDIAN(dollar_vol) OVER (
               PARTITION BY symbol ORDER BY trade_date
               ROWS BETWEEN {LIQUIDITY_WINDOW_DAYS - 1} PRECEDING AND CURRENT ROW
           ) AS dollar_vol_median_21,
           COUNT(dollar_vol) OVER (
               PARTITION BY symbol ORDER BY trade_date
               ROWS BETWEEN {LIQUIDITY_WINDOW_DAYS - 1} PRECEDING AND CURRENT ROW
           ) AS liquidity_n
    FROM pair
    """
    frame = con.execute(query).df()
    con.close()
    frame["trade_date"] = h02._ns(frame["trade_date"])
    frame["symbol"] = frame["symbol"].astype(str)
    # point-in-time: only a full trailing window counts (matches
    # spread_estimate_from_ohlc's min_periods behaviour and the brief's own
    # 21-day window), floored/capped as specified.
    frame["spread_21"] = np.where(
        frame["spread_n"] >= SPREAD_WINDOW_DAYS - 1,
        frame["spread_raw"].clip(lower=SPREAD_FLOOR, upper=SPREAD_CAP),
        np.nan,
    )
    frame["dollar_vol_median_21"] = np.where(
        frame["liquidity_n"] >= LIQUIDITY_WINDOW_DAYS, frame["dollar_vol_median_21"], np.nan
    )
    out = frame[["symbol", "trade_date", "spread_21", "dollar_vol_median_21"]]
    out.to_parquet(out_path, index=False)
    coverage = out["spread_21"].notna().mean()
    _log(f"liquidity: wrote {out_path}, {len(out):,} rows, spread coverage {coverage:.1%}")


# --------------------------------------------------------------------------
# stage: predict -- walk-forward B0, daily out-of-fold predictions
# --------------------------------------------------------------------------


def stage_predict(args: argparse.Namespace) -> None:
    out_path = CACHE_DIR / "predictions.parquet"
    if out_path.exists() and not args.force:
        _log(f"predict: {out_path} present -- reusing (pass --force to rebuild)")
        return
    manifest = json.loads((CACHE_DIR / "cohort_manifest.json").read_text())
    kept_features: list[str] = manifest["kept_features"]
    monthly_panel = pd.read_parquet(CACHE_DIR / "monthly_panel.parquet")
    monthly_panel["formation_date"] = h02._ns(monthly_panel["formation_date"])
    daily_cohort = pd.read_parquet(CACHE_DIR / "daily_cohort.parquet")
    daily_cohort["trade_date"] = h02._ns(daily_cohort["trade_date"])
    trading_calendar = pd.DatetimeIndex(
        sorted(pd.read_parquet(CACHE_DIR / "close_sanitized.parquet", columns=[]).index)
    )

    formation_dates = sorted(monthly_panel["formation_date"].unique())
    target_col = "target_excess_21"
    h02.EMBARGO_DAYS = 21
    folds = h02.build_folds(formation_dates, trading_calendar, kt.DEFAULT_TRAIN_YEARS)
    _log(f"predict: {len(folds)} quarterly folds, {len(kept_features)} features")

    pred_frames = []
    fold_meta = []
    for fold in folds:
        train_frame = monthly_panel.loc[monthly_panel["formation_date"].isin(fold.train_dates)]
        train_frame = train_frame.dropna(subset=[target_col])
        meta = {
            "fold_id": fold.fold_id,
            "train_start": fold.train_start.date().isoformat(),
            "train_cutoff": fold.train_cutoff.date().isoformat(),
            "train_rows": int(len(train_frame)),
        }
        if len(train_frame) < h02.MIN_TRAIN_ROWS or not fold.test_dates:
            meta["skipped"] = f"train_rows={len(train_frame)}, test_dates={len(fold.test_dates)}"
            fold_meta.append(meta)
            continue
        model = kt.MODEL_FACTORIES["lgbm_reg"]()
        X_train = train_frame[kept_features].to_numpy(dtype="float64")
        y_train = train_frame[target_col].to_numpy(dtype="float64")
        groups_train = train_frame["formation_date"].to_numpy()
        model.fit(X_train, y_train, groups_train)

        test_quarter = pd.Timestamp(fold.test_dates[0]).to_period("Q")
        coverage_days = trading_calendar[trading_calendar.to_period("Q") == test_quarter]
        day_panel = daily_cohort.loc[daily_cohort["trade_date"].isin(coverage_days)]
        day_panel = day_panel.dropna(subset=kept_features, how="all")
        if day_panel.empty:
            meta["coverage_days"] = 0
            fold_meta.append(meta)
            continue
        preds = model.predict(day_panel[kept_features].to_numpy(dtype="float64"))
        out = day_panel[["trade_date", "symbol", "adv_tercile", "adv_rank"]].copy()
        out["prediction"] = preds
        out["fold_id"] = fold.fold_id
        pred_frames.append(out)
        meta["coverage_days"] = int(len(coverage_days))
        meta["coverage_start"] = str(coverage_days[0].date()) if len(coverage_days) else None
        meta["coverage_end"] = str(coverage_days[-1].date()) if len(coverage_days) else None
        fold_meta.append(meta)
        span = f"{meta.get('coverage_start')}..{meta.get('coverage_end')}"
        _log(f"predict: fold {fold.fold_id} -- {span}")

    predictions = (
        pd.concat(pred_frames, ignore_index=True)
        if pred_frames
        else pd.DataFrame(
            columns=["trade_date", "symbol", "adv_tercile", "adv_rank", "prediction", "fold_id"]
        )
    )
    predictions = predictions.sort_values(["trade_date", "symbol"]).reset_index(drop=True)
    predictions.to_parquet(out_path, index=False)
    _write_json(CACHE_DIR / "fold_meta.json", fold_meta)
    first_date = predictions["trade_date"].min() if not predictions.empty else None
    last_date = predictions["trade_date"].max() if not predictions.empty else None
    _log(f"predict: wrote {out_path}, {len(predictions):,} rows, {first_date}..{last_date}")


# --------------------------------------------------------------------------
# stage: portfolio -- V1/V2 books, all offsets, costs, capacity, buffer
# --------------------------------------------------------------------------


def resolve_windows(
    first_predicted: pd.Timestamp, latest_date: pd.Timestamp
) -> dict[str, tuple[str, str]]:
    stress_start = max(STRESS_FLOOR, first_predicted)
    windows = dict(WINDOWS_TEMPLATE)
    windows["stress"] = (str(stress_start.date()), windows["stress"][1])
    windows["anchor"] = (windows["anchor"][0], str(latest_date.date()))
    return {k: (a, b) for k, (a, b) in windows.items()}


def build_signal_book(
    predictions: pd.DataFrame,
    variant: str,
    trading_index: pd.DatetimeIndex,
    offset: int,
) -> dict[pd.Timestamp, list[str]]:
    """Holdings (buffered top-50) at each of this offset's signal dates,
    keyed by the signal date (effective at the next session's open)."""
    universe = (
        predictions
        if variant == "V1"
        else predictions.loc[predictions["adv_tercile"] == "T3_illiquid"]
    )
    by_date = {
        d: g.sort_values("prediction", ascending=False) for d, g in universe.groupby("trade_date")
    }
    signal_dates = tranche.shifted_signal_dates(trading_index, offset)
    holdings: dict[pd.Timestamp, list[str]] = {}
    previous: set[str] = set()
    for d in signal_dates:
        g = by_date.get(d)
        if g is None or g.empty:
            holdings[d] = sorted(previous)  # no predictions that day -- hold prior book
            continue
        ranked = list(g["symbol"])
        book = buffered_selection(previous, ranked, N_TOP, BUFFER_RANK)
        holdings[d] = book
        previous = set(book)
    return holdings


def simulate_book(
    holdings_by_signal_date: dict[pd.Timestamp, list[str]],
    trading_index: pd.DatetimeIndex,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    liquidity: pd.DataFrame,  # indexed (trade_date, symbol) -> spread_21, dollar_vol_median_21
    flat_bps: float,
    spread_weight: float,
) -> tuple[pd.Series, pd.Series]:
    """Daily net-return and turnover series for one offset/variant/cost
    regime. Per-stock cost = ``flat_bps + spread_weight * spread_21_bps``,
    applied to ``|target_weight - previous_weight|`` for each symbol whose
    weight changes at a rebalance -- the direct per-stock generalization of
    every other simulator in this repo (``turnover * cost_bps / 10_000``,
    here summed name-by-name because the per-unit cost is name-specific).
    Weights are held piecewise constant between rebalances (no intra-period
    drift), matching the repo-wide convention. Uninvested capacity-capped
    residual earns 0% (idle cash, not SHY -- brief's own "stays in cash").
    """
    n = len(trading_index)
    pos_of = {d: i for i, d in enumerate(trading_index)}
    all_symbols = sorted({s for book in holdings_by_signal_date.values() for s in book})
    if not all_symbols:
        zero = pd.Series(0.0, index=trading_index)
        return zero, zero.copy()
    lo = leg_open.reindex(columns=all_symbols).fillna(0.0).to_numpy(dtype="float64")
    lc = leg_close.reindex(columns=all_symbols).fillna(0.0).to_numpy(dtype="float64")
    sym_index = {s: i for i, s in enumerate(all_symbols)}

    w_prev = np.zeros(len(all_symbols), dtype="float64")
    weights_over_time = np.zeros((n, len(all_symbols)), dtype="float64")
    turnover = np.zeros(n, dtype="float64")
    cost = np.zeros(n, dtype="float64")

    change_at: dict[int, np.ndarray] = {}
    for d, book in sorted(holdings_by_signal_date.items()):
        i = pos_of.get(d)
        if i is None or i + 1 >= n:
            continue
        target = np.zeros(len(all_symbols), dtype="float64")
        if book:
            equal_weight = 1.0 / len(book)
            liq_day = liquidity.get(d, {})
            for s in book:
                dv = liq_day.get(s, (np.nan, np.nan))[1]
                target[sym_index[s]] = capacity_capped_weight(equal_weight, dv)
        change_at[i + 1] = (d, target)

    current_w = w_prev
    for i in range(n):
        if i in change_at:
            signal_date, target = change_at[i]
            liq_day = liquidity.get(signal_date, {})
            # A name can be present in `liq_day` with an explicit NaN spread
            # (not enough trailing history yet for its own Abdi-Ranaldo
            # estimate, e.g. a recent IPO) -- distinct from being absent from
            # `liq_day` entirely. Route both through the same tested
            # `per_stock_cost_bps` (which floors NaN spread to 0, i.e. "no
            # extra spread charge beyond the flat bp component" for that
            # name on that day) so a missing estimate can never turn a whole
            # day's return into NaN.
            spread_frac = pd.Series(
                [liq_day.get(s, (np.nan, np.nan))[0] for s in all_symbols],
                index=all_symbols,
                dtype="float64",
            )
            per_name_cost_bps = per_stock_cost_bps(spread_frac, flat_bps, spread_weight).to_numpy()
            delta = np.abs(target - current_w)
            cost[i] = float(np.dot(delta, per_name_cost_bps) / 10_000.0)
            turnover[i] = float(delta.sum())
            current_w = target
        weights_over_time[i] = current_w

    w_prev_arr = np.vstack([np.zeros((1, len(all_symbols))), weights_over_time[:-1]])
    gross = (w_prev_arr * lo).sum(axis=1) + (weights_over_time * lc).sum(axis=1)
    net = gross - cost
    return pd.Series(net, index=trading_index), pd.Series(turnover, index=trading_index)


def get_rf_series(trading_calendar: pd.DatetimeIndex) -> pd.Series:
    """BIL close-to-close return, reindexed to ``trading_calendar``. BIL is
    an ETF -- ``kt``'s stock-only universe (``data/features/daily_broad``)
    excludes ETFs/funds by construction, so it is never a column of
    ``close_sanitized`` and must be fetched separately, the same fallback
    ``h02._benchmark_prices`` already provides for SPY in ``stage_cohort``.
    Cached once (this fetch scans the full SIP archive, ~100s) and reused by
    both ``stage_portfolio`` and ``stage_report``."""
    cache_path = CACHE_DIR / "rf_series.parquet"
    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached.index = h02._ns(cached.index)
        return cached["rf"].reindex(trading_calendar).fillna(0.0)
    bench_close, _bench_open = h02._benchmark_prices((base.RF,))
    close = bench_close.reindex(trading_calendar).ffill()
    rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
    rf.to_frame("rf").to_parquet(cache_path)
    return rf


def _liquidity_lookup(
    liquidity: pd.DataFrame,
) -> dict[pd.Timestamp, dict[str, tuple[float, float]]]:
    """``{trade_date: {symbol: (spread_21, dollar_vol_median_21)}}`` for O(1)
    per-rebalance lookups (the alternative -- a DataFrame ``.loc`` per name
    per rebalance -- is far slower at this scale)."""
    out: dict[pd.Timestamp, dict[str, tuple[float, float]]] = {}
    for row in liquidity.itertuples(index=False):
        out.setdefault(row.trade_date, {})[row.symbol] = (row.spread_21, row.dollar_vol_median_21)
    return out


def offset_metric_summary(per_offset: dict[int, dict[str, float]]) -> dict[str, dict[str, float]]:
    offsets = sorted(per_offset)
    out: dict[str, dict[str, float]] = {}
    for metric in ("cagr", "sharpe", "max_dd", "turnover_yr"):
        vals = np.array([per_offset[o][metric] for o in offsets], dtype=float)
        finite = vals[np.isfinite(vals)]
        out[metric] = {
            "min": float(np.min(finite)) if len(finite) else float("nan"),
            "median": float(np.median(finite)) if len(finite) else float("nan"),
            "max": float(np.max(finite)) if len(finite) else float("nan"),
        }
    return out


def _judged_offset(sharpe_by_offset: dict[int, float]) -> int:
    ordered = sorted(sharpe_by_offset, key=lambda o: sharpe_by_offset[o])
    return ordered[len(ordered) // 2]


def stage_portfolio(args: argparse.Namespace) -> None:
    out_path = CACHE_DIR / "portfolio_results.json"
    if out_path.exists() and not args.force:
        _log(f"portfolio: {out_path} present -- reusing (pass --force to rebuild)")
        return
    predictions = pd.read_parquet(CACHE_DIR / "predictions.parquet")
    predictions["trade_date"] = h02._ns(predictions["trade_date"])
    liquidity = pd.read_parquet(CACHE_DIR / "liquidity.parquet")
    liquidity["trade_date"] = h02._ns(liquidity["trade_date"])
    close_sanitized = pd.read_parquet(CACHE_DIR / "close_sanitized.parquet")
    open_sanitized = pd.read_parquet(CACHE_DIR / "open_sanitized.parquet")
    close_sanitized.index = h02._ns(close_sanitized.index)
    open_sanitized.index = h02._ns(open_sanitized.index)

    if predictions.empty:
        raise RuntimeError("portfolio: no predictions -- run stage predict first")
    trading_index = close_sanitized.index
    prev_close = close_sanitized.shift(1)
    leg_open = (open_sanitized / prev_close - 1.0).fillna(0.0)
    leg_close = (close_sanitized / open_sanitized - 1.0).fillna(0.0)
    rf = get_rf_series(trading_index)

    liquidity_lookup = _liquidity_lookup(liquidity)
    first_predicted = predictions["trade_date"].min()
    latest_date = trading_index[-1]
    windows = resolve_windows(first_predicted, latest_date)
    _log(f"portfolio: windows {windows}")

    cost_regimes = {
        "base": (COST_BASE_FLAT_BPS, COST_BASE_SPREAD_WEIGHT),
        "stress": (COST_STRESS_FLAT_BPS, COST_STRESS_SPREAD_WEIGHT),
        "flat10": (COST_BASE_FLAT_BPS, 0.0),
        "flat20": (COST_STRESS_FLAT_BPS, 0.0),
    }

    variant_results: dict[str, Any] = {}
    variant_returns: dict[str, dict[int, pd.Series]] = {}
    for variant in ("V1", "V2"):
        _log(f"portfolio: building {variant}")
        holdings_by_offset = {
            o: build_signal_book(predictions, variant, trading_index, o) for o in OFFSETS
        }
        per_window: dict[str, Any] = {w: {"offsets": {}} for w in windows}
        base_ret_by_offset: dict[int, pd.Series] = {}
        for o in OFFSETS:
            holdings = holdings_by_offset[o]
            regime_series: dict[str, tuple[pd.Series, pd.Series]] = {}
            for regime, (flat_bps, spread_w) in cost_regimes.items():
                ret, turn = simulate_book(
                    holdings,
                    trading_index,
                    leg_open,
                    leg_close,
                    liquidity_lookup,
                    flat_bps,
                    spread_w,
                )
                regime_series[regime] = (ret, turn)
            base_ret_by_offset[o] = regime_series["base"][0]
            for wname, (a, b) in windows.items():
                mask = (trading_index >= a) & (trading_index <= b)
                cell: dict[str, Any] = {}
                for regime, (ret, turn) in regime_series.items():
                    m = base.metrics(ret.loc[mask], rf, turn.loc[mask])
                    cell[regime] = asdict(m)
                per_window[wname]["offsets"][o] = cell
        for wname in windows:
            sharpe_by_offset = {
                o: per_window[wname]["offsets"][o]["base"]["sharpe"] for o in OFFSETS
            }
            per_window[wname]["summary_base"] = offset_metric_summary(
                {o: per_window[wname]["offsets"][o]["base"] for o in OFFSETS}
            )
            per_window[wname]["summary_stress"] = offset_metric_summary(
                {o: per_window[wname]["offsets"][o]["stress"] for o in OFFSETS}
            )
            per_window[wname]["summary_flat10"] = offset_metric_summary(
                {o: per_window[wname]["offsets"][o]["flat10"] for o in OFFSETS}
            )
            per_window[wname]["summary_flat20"] = offset_metric_summary(
                {o: per_window[wname]["offsets"][o]["flat20"] for o in OFFSETS}
            )
            per_window[wname]["judged_offset"] = _judged_offset(sharpe_by_offset)
        variant_results[variant] = {"per_window": per_window, "windows": windows}
        variant_returns[variant] = base_ret_by_offset
        _write_json(CACHE_DIR / f"returns_{variant}_meta.json", {"n_offsets": len(OFFSETS)})
        for o in OFFSETS:
            base_ret_by_offset[o].to_frame("ret").to_parquet(
                CACHE_DIR / f"ret_{variant}_o{o}.parquet"
            )

    _write_json(
        out_path,
        {
            "variants": variant_results,
            "windows": windows,
            "first_predicted": str(first_predicted.date()),
        },
    )
    _log(f"portfolio: wrote {out_path}")


# --------------------------------------------------------------------------
# stage: placebo, K2, report
# --------------------------------------------------------------------------


def build_random_book(
    predictions: pd.DataFrame,
    variant: str,
    trading_index: pd.DatetimeIndex,
    offset: int,
    seed: int,
) -> dict[pd.Timestamp, list[str]]:
    universe = (
        predictions
        if variant == "V1"
        else predictions.loc[predictions["adv_tercile"] == "T3_illiquid"]
    )
    by_date = {d: g for d, g in universe.groupby("trade_date")}
    signal_dates = tranche.shifted_signal_dates(trading_index, offset)
    holdings: dict[pd.Timestamp, list[str]] = {}
    previous: set[str] = set()
    for i, d in enumerate(signal_dates):
        g = by_date.get(d)
        if g is None or g.empty:
            holdings[d] = sorted(previous)
            continue
        rng = np.random.default_rng((seed, offset, i))
        ranked = list(rng.permutation(g["symbol"].to_numpy()))
        book = buffered_selection(previous, ranked, N_TOP, BUFFER_RANK)
        holdings[d] = book
        previous = set(book)
    return holdings


def stage_report(args: argparse.Namespace) -> None:
    del args
    portfolio = json.loads((CACHE_DIR / "portfolio_results.json").read_text())
    windows = portfolio["windows"]
    predictions = pd.read_parquet(CACHE_DIR / "predictions.parquet")
    predictions["trade_date"] = h02._ns(predictions["trade_date"])
    liquidity = pd.read_parquet(CACHE_DIR / "liquidity.parquet")
    liquidity["trade_date"] = h02._ns(liquidity["trade_date"])
    close_sanitized = pd.read_parquet(CACHE_DIR / "close_sanitized.parquet")
    open_sanitized = pd.read_parquet(CACHE_DIR / "open_sanitized.parquet")
    close_sanitized.index = h02._ns(close_sanitized.index)
    open_sanitized.index = h02._ns(open_sanitized.index)
    trading_index = close_sanitized.index
    prev_close = close_sanitized.shift(1)
    leg_open = (open_sanitized / prev_close - 1.0).fillna(0.0)
    leg_close = (close_sanitized / open_sanitized - 1.0).fillna(0.0)
    rf = get_rf_series(trading_index)
    liquidity_lookup = _liquidity_lookup(liquidity)

    # ---- placebo ----
    placebo_results: dict[str, Any] = {}
    for variant in ("V1", "V2"):
        placebo_sharpes: dict[str, list[float]] = {"stress": [], "anchor": []}
        for seed in range(PLACEBO_SEEDS):
            sharpe_by_offset = {"stress": {}, "anchor": {}}
            for o in OFFSETS:
                holdings = build_random_book(predictions, variant, trading_index, o, seed)
                ret, turn = simulate_book(
                    holdings,
                    trading_index,
                    leg_open,
                    leg_close,
                    liquidity_lookup,
                    COST_BASE_FLAT_BPS,
                    COST_BASE_SPREAD_WEIGHT,
                )
                for wname in ("stress", "anchor"):
                    a, b = windows[wname]
                    mask = (trading_index >= a) & (trading_index <= b)
                    m = base.metrics(ret.loc[mask], rf, turn.loc[mask])
                    sharpe_by_offset[wname][o] = m.sharpe
            for wname in ("stress", "anchor"):
                vals = [v for v in sharpe_by_offset[wname].values() if np.isfinite(v)]
                placebo_sharpes[wname].append(float(np.median(vals)) if vals else float("nan"))
        placebo_results[variant] = placebo_sharpes
        _log(f"report: placebo done for {variant}")

    # ---- K2: S3 combination ----
    base.WARMUP_START = screen_lane.PANEL_START
    etf_close, etf_open = base.load_panel(salvage.symbols())
    etf_leg_open, etf_leg_close = salvage.legs(etf_close, etf_open)
    etf_rf = (etf_close[screen_lane.RF] / etf_close[screen_lane.RF].shift(1) - 1.0).fillna(0.0)
    etf_shy_ret = (etf_close[screen_lane.CASH] / etf_close[screen_lane.CASH].shift(1) - 1.0).fillna(
        0.0
    )
    s3_ret10, _s3_turn10 = screen_lane.s3_incumbent(
        etf_close, etf_leg_open, etf_leg_close, screen_lane.COST_BPS_PRIMARY
    )
    k2_results: dict[str, Any] = {}
    dsr_results: dict[str, Any] = {}
    for variant in ("V1", "V2"):
        edge_by_window: dict[str, float] = {}
        for wname in ("stress", "anchor"):
            a, b = windows[wname]
            edges = []
            for o in OFFSETS:
                ret = pd.read_parquet(CACHE_DIR / f"ret_{variant}_o{o}.parquet")["ret"]
                edges.append(
                    screen_lane.diversifier_edge_for_offset(
                        s3_ret10, ret, etf_shy_ret, etf_rf, (a, b)
                    )
                )
            edge_by_window[wname] = float(np.median(edges))
        k2_results[variant] = edge_by_window

        judged_offset = portfolio["variants"][variant]["per_window"]["anchor"]["judged_offset"]
        judged_ret = pd.read_parquet(CACHE_DIR / f"ret_{variant}_o{judged_offset}.parquet")["ret"]
        a, b = windows["anchor"]
        mask = (judged_ret.index >= a) & (judged_ret.index <= b)
        excess = (
            (judged_ret.loc[mask] - rf.reindex(judged_ret.index).fillna(0.0).loc[mask])
            .dropna()
            .to_numpy()
        )
        try:
            dsr_results[variant] = float(
                deflated_sharpe_probability(
                    excess, trial_count=DSR_TRIAL_COUNT, hac_lag=DSR_HAC_LAG
                )
            )
        except ValueError as exc:
            dsr_results[variant] = None
            _log(f"report: DSR failed for {variant}: {exc}")

    # ---- verdict ----
    verdicts: dict[str, Any] = {}
    g1_status: dict[str, Any] = {}
    for variant in ("V1", "V2"):
        pw = portfolio["variants"][variant]["per_window"]
        stress_sharpe = pw["stress"]["summary_base"]["sharpe"]["median"]
        anchor_sharpe = pw["anchor"]["summary_base"]["sharpe"]["median"]
        stress_cagr_stresscost = pw["stress"]["summary_stress"]["cagr"]["median"]
        anchor_cagr_stresscost = pw["anchor"]["summary_stress"]["cagr"]["median"]
        k1 = bool(
            stress_sharpe >= K1_STRESS_SHARPE_MIN
            and anchor_sharpe >= K1_ANCHOR_SHARPE_MIN
            and stress_cagr_stresscost > 0
            and anchor_cagr_stresscost > 0
        )
        k2 = bool(
            k2_results[variant]["stress"] >= K2_EDGE_MIN
            and k2_results[variant]["anchor"] >= K2_EDGE_MIN
        )
        placebo_win_rate = {
            wname: float(
                np.mean(
                    [
                        pw[wname]["summary_base"]["sharpe"]["median"] > p
                        for p in placebo_results[variant][wname]
                        if np.isfinite(p)
                    ]
                )
            )
            for wname in ("stress", "anchor")
        }
        verdicts[variant] = {
            "stress_sharpe_base_median": stress_sharpe,
            "anchor_sharpe_base_median": anchor_sharpe,
            "stress_cagr_stresscost_median": stress_cagr_stresscost,
            "anchor_cagr_stresscost_median": anchor_cagr_stresscost,
            "k1_pass": k1,
            "k2_edge": k2_results[variant],
            "k2_pass": k2,
            "verdict": "keep_K1" if k1 else ("keep_K2" if k2 else "reject"),
            "placebo_win_rate": placebo_win_rate,
            "dsr_anchor": dsr_results[variant],
        }
        g1 = {
            wname: bool(
                tranche.passes_g1_or_g1alt(
                    {
                        "cagr": pw[wname]["summary_base"]["cagr"]["median"],
                        "max_dd": pw[wname]["summary_base"]["max_dd"]["median"],
                        "sharpe": pw[wname]["summary_base"]["sharpe"]["median"],
                    }
                )
            )
            for wname in windows
        }
        g1_status[variant] = g1

    results = {
        "task": "T-20260928-30",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "windows": windows,
        "portfolio": portfolio["variants"],
        "placebo": placebo_results,
        "k2": k2_results,
        "dsr_anchor": dsr_results,
        "dsr_trial_count": DSR_TRIAL_COUNT,
        "g1_status_informative_only": g1_status,
        "verdict": verdicts,
    }
    _write_json(RESULTS_PATH, results)
    _log(f"report: wrote {RESULTS_PATH}")
    _write_markdown_report(results)


def _fmt(x: float | None, pct: bool = False, digits: int = 3) -> str:
    if x is None or not np.isfinite(x):
        return "NA"
    return f"{x * 100:.1f}%" if pct else f"{x:.{digits}f}"


def _write_markdown_report(results: dict[str, Any]) -> None:
    lines = [
        "# T-20260928-30 小盘/低流动性 LightGBM 价量排序模型多做空头寸成本压测",
        "",
        "承接 `dir:lgbm_price_volume_ranking_small_caps`（"
        "`reports/research/iterations/t20260928_10_ml_killtest/report.md` 第二次运行）："
        "冻结 B0 模型（24 个价量特征、月度形成、21 日 beta 调整超额收益、"
        "3 年滚动训练、季度重训、embargo 21），逐日预测（用覆盖当日的那一折模型），"
        "在拓宽后的股票池（收盘价>=$3、21 日美元 ADV>=$100 万）上构建两个只做多组合，"
        "计入逐只股票的 Abdi-Ranaldo (2017) 价差成本、容量上限和调仓缓冲带。",
        "",
        "## 规格（预注册，未在看到结果后调整）",
        "",
        "- V1：全池预测值前 50；V2：仅在最不流动三分位内取预测值前 50。等权，"
        "调仓缓冲：原持仓排名 <=150（V1 全池 / V2 三分位内）才保留，",
        "  否则用当日最佳未持有名字补满 50。",
        "- 21 个月度调仓日偏移（`tranche.shifted_signal_dates`），收盘出信号、次日开盘成交。",
        "- 每只股票每边成本：基准 = 10bp + 0.5 x 价差；压力 = 20bp + 1.0 x 价差；",
        "  价差 = Abdi-Ranaldo (2017) 收盘-最高-最低价估计量，21 日滚动，点时，下限 0、上限 5%。",
        "  另报固定 10bp / 20bp 作参照。",
        "- 容量：账户 $100,000，单只持仓 <= 该股 21 日成交额中位数的 1%；",
        "  超出部分留作闲置现金（不投资、不计收益）。",
        "",
        "## 各变体、各窗口结果（偏移中位数 / 最小 / 最大，基准成本，另列压力成本 CAGR）",
        "",
    ]
    for variant in ("V1", "V2"):
        v = results["verdict"][variant]
        lines.append(f"### {variant}")
        lines.append("")
        lines.append(
            "| 窗口 | Sharpe(基准,中位) | Sharpe(min/max) | CAGR(基准,中位) "
            "| CAGR(压力成本,中位) | MaxDD(基准,中位) | 年化换手(基准,中位) |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for wname, pw in results["portfolio"][variant]["per_window"].items():
            sb = pw["summary_base"]
            ss = pw["summary_stress"]
            tag = "（受污染，仅参考）" if wname in CONTAMINATED_WINDOWS else ""
            lines.append(
                f"| {wname}{tag} | {_fmt(sb['sharpe']['median'])} "
                f"| {_fmt(sb['sharpe']['min'])}/{_fmt(sb['sharpe']['max'])} "
                f"| {_fmt(sb['cagr']['median'], pct=True)} "
                f"| {_fmt(ss['cagr']['median'], pct=True)} "
                f"| {_fmt(sb['max_dd']['median'], pct=True)} "
                f"| {_fmt(sb['turnover_yr']['median'])} |"
            )
        lines += [
            "",
            f"占位胜率（真实偏移中位数 Sharpe 战胜 20 个随机排名占位的比例）："
            f"压力期 {_fmt(v['placebo_win_rate']['stress'], pct=True)}，"
            f"对标窗 {_fmt(v['placebo_win_rate']['anchor'], pct=True)}。",
            "",
            f"K2（与 S3 组合、同波动对照的夏普增量，偏移中位数）："
            f"压力期 {_fmt(v['k2_edge']['stress'])}，对标窗 {_fmt(v['k2_edge']['anchor'])}"
            f"（门槛 >= {K2_EDGE_MIN}）。",
            "",
            f"DSR（对标窗，judged offset，trial_count={results['dsr_trial_count']}，"
            "含 T-20260928-10 的 B0/5/6/11 四个否决单元）："
            f"{_fmt(v['dsr_anchor'])}（仅供参考，不是门槛）。",
            "",
            "G1/G1' 状态（仅参考，非本任务判定条件）："
            + ", ".join(
                f"{w}={'过' if p else '未过'}"
                for w, p in results["g1_status_informative_only"][variant].items()
            ),
            "",
            f"**判定：{v['verdict']}**"
            f"（K1: 压力期偏移中位数 Sharpe>={K1_STRESS_SHARPE_MIN} "
            f"且对标窗>={K1_ANCHOR_SHARPE_MIN} "
            f"且两窗压力成本下 CAGR>0 -> {'过' if v['k1_pass'] else '未过'}；"
            f"K2: 两窗组合增量>=+{K2_EDGE_MIN} -> {'过' if v['k2_pass'] else '未过'}）",
            "",
        ]
    lines += [
        "## 花费",
        "",
        "见 `python3 scripts/modal_budget.py status`；本任务实测花费见下（执行者手填）。",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")
    _log(f"report: wrote {REPORT_PATH}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=["cohort", "liquidity", "predict", "portfolio", "report", "all"],
        default="all",
    )
    parser.add_argument("--window-start", default=DEFAULT_WINDOW_START)
    parser.add_argument(
        "--window-end", default=None, help="default: latest date in data/features/daily_broad"
    )
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--duckdb-memory", default="24GB")
    parser.add_argument("--duckdb-threads", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    return parser


def _resolve_window_end(window_end: str | None) -> str:
    if window_end is not None:
        return window_end
    years = sorted(int(p.stem) for p in kt.DAILY_ROOT.glob("*.parquet") if p.stem.isdigit())
    latest_year = years[-1]
    table = pd.read_parquet(kt.DAILY_ROOT / f"{latest_year}.parquet", columns=["trade_date"])
    return str(pd.Timestamp(table["trade_date"].max()).date())


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.window_end = _resolve_window_end(args.window_end)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stages = (
        ["cohort", "liquidity", "predict", "portfolio", "report"]
        if args.stage == "all"
        else [args.stage]
    )
    for stage in stages:
        _log(f"=== stage {stage} ===")
        if stage == "cohort":
            stage_cohort(args)
        elif stage == "liquidity":
            stage_liquidity(args)
        elif stage == "predict":
            stage_predict(args)
        elif stage == "portfolio":
            stage_portfolio(args)
        elif stage == "report":
            stage_report(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
