"""H-20260917-01: Form 4 open-market insider buying as an *independent* monthly
strategy on the broad universe (every tradable US common stock, price >= $2,
60-session dollar ADV >= $1M, delisted names backfilled), held 1 / 3 / 6 months
in overlapping monthly tranches, reported by liquidity band.

Card: ``reports/research/hypotheses/H-20260917-01-insider-independent-broad-universe.md``
Data card: ``reports/research/hypotheses/D-20260917-01-broad-universe-and-delisted-backfill.md``
Earlier lesson this round does *not* repeat: ``reports/research/lessons/L-20260916-01.md``
(insider buying as a gate on the momentum book -- the layers did not intersect;
here the insider signal selects the book on its own).

Design (the card's, unchanged)
------------------------------
* Formation at every month-end cohort date ``t`` of the PIT universe panel
  (``universe_as_of_calendar_month`` semantics: the cohort *is* that month's
  ``month_end`` row set; ``adv_rank`` is that same cohort's own ranking).
  Eligible = cohort names whose insider row at ``t`` shows a visible
  open-market buy (``TRANS_CODE = P``) in the trailing 60 sessions. Variants
  are columns of one table, never separate runs (see ``VARIANTS``); the 30 / 90
  session windows do not exist in the insider table, so they are proxied by
  ``days_since_last_visible_buy <= 30 / 90`` and labelled as proxies.
* Portfolio: equal weight, at most ``MAX_NAMES`` names (largest
  ``net_buy_usd_60d`` kept), held ``k`` months as ``k`` overlapping monthly
  tranches with ``1/k`` of capital each (Jegadeesh-Titman overlapping
  portfolios). Weights are normalized to 100% invested at every month-end
  (L-20260916-03: decisions are read off the exposure-normalized book); a month
  whose tranches are *all* empty sits in ``BIL``.
* Returns: daily, ``kernel.loop.returns_from_weight_schedule`` with price
  hygiene on (the default since 2026-09-17), ``next_open`` execution, 10 bps
  per side -- the same cost identity as the momentum ledger
  (``scripts/run_step13_m_grid.py::PRIMARY_COST_BPS``); 25 bps stress is
  priced for the main cell.
* Liquidity bands from the cohort's ``adv_rank``: 1-500 / 501-1500 / 1501+ and
  all bands. Splits: prior-63-session return < -20% or not; cluster (>= 2
  buyers) or single buyer.
* Controls (all mandatory): SPY / IWM / MTUM / SPMO buy-and-hold; same-band
  equal weight; same-size random draw from the same band at every formation
  date, >= 5 seeds, reported as a distribution; vol-matched excess vs SPY via
  ``kernel.vol_matched``.
* Placebo: filing-date shift +/- 30 sessions -- the ``insider_broad_placebo_
  shift30_seed*`` tables built by ``scripts/build_insider_features.py``;
  however many exist when the report stage runs are used and the count is
  stated. The narrow (top-1000) placebo tables are *not* substituted.
* Survivorship: every headline number is reported twice -- full broad
  universe vs the universe restricted to names in the original SIP archive
  (``data/sip/daily/_LAYOUT.json`` shard symbols); a name is "backfilled" iff
  it is not there.

Stages (each resumable from ``reports/research/iterations/<id>/cache/``)
-------------------------------------------------------------------------
``load``   universe panel, wide open/close matrices (+ BIL cash leg), the
           insider columns at formation dates, the formation frame, placebo
           insider columns, benchmark ETF returns.
``price``  one daily-return series per cell (real / same-band EW / random
           seed / placebo seed), main variant first, cached per cell.
``report`` metrics, refutation criteria, ``summary.json`` and ``report.md``.
``paper``  the latest-month selection (what the paper adapter would buy).

Nothing here writes a ledger row; nothing goes through ``loop.run_experiment``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from open_composer.adapters.data.sip_parquet import load_sip_bars  # noqa: E402
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel import loop as kernel_loop  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    DEFAULT_MIN_COHORT_SYMBOLS,
    RebalanceEvent,
    returns_from_weight_schedule,
    universe_as_of_calendar_month,
)
from open_composer.research.kernel.mechanism_eval import annualized_cagr, max_drawdown  # noqa: E402
from open_composer.research.kernel.pick_export import turnover_per_rebalance  # noqa: E402
from open_composer.research.kernel.vol_matched import (  # noqa: E402
    cagr_excess_vol_matched,
    vol_match_weight,
)

ITERATION_ID = "h20260917_01_insider_independent"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
FEATURES_ROOT = ROOT / "data" / "features"
SIP_LAYOUT_PATH = ROOT / "data" / "sip" / "daily" / "_LAYOUT.json"

#: Cache and artifact paths are per feature-table family. Without this the
#: broad-universe run silently reused the narrow run's cached formation frame
#: and price matrix (2026-09-18: "load: ... present -- reusing" finished in
#: 0.0s and the whole 991-cell grid was priced off 2024-2025 top-1500 data).
#: ``bind_paths`` is called once from ``main`` before any stage runs.
CACHE_DIR = OUT_DIR / "cache" / "broad"
RETURNS_DIR = CACHE_DIR / "returns"
BOOKS_DIR = CACHE_DIR / "books"
SUMMARY_PATH = OUT_DIR / "summary.json"
REPORT_PATH = OUT_DIR / "report.md"
PAPER_PATH = OUT_DIR / "paper_candidates_latest.json"


def bind_paths(features_suffix: str) -> str:
    """Point the cache and artifact paths at this feature family and return its
    tag (``broad`` keeps the headline file names; anything else is suffixed)."""
    global CACHE_DIR, RETURNS_DIR, BOOKS_DIR, SUMMARY_PATH, REPORT_PATH, PAPER_PATH
    tag = features_suffix.strip("_") or "narrow"
    CACHE_DIR = OUT_DIR / "cache" / tag
    RETURNS_DIR = CACHE_DIR / "returns"
    BOOKS_DIR = CACHE_DIR / "books"
    stem = "" if tag == "broad" else f"_{tag}"
    SUMMARY_PATH = OUT_DIR / f"summary{stem}.json"
    REPORT_PATH = OUT_DIR / f"report{stem}.md"
    PAPER_PATH = OUT_DIR / f"paper_candidates_latest{stem}.json"
    return tag


#: Same cost identity as the momentum ledger (scripts/run_step13_m_grid.py).
PRIMARY_COST_BPS = 10.0
STRESS_COST_BPS = 25.0
EXECUTION = "next_open"
CASH_SYMBOL = "BIL"
BENCHMARK_SYMBOLS: tuple[str, ...] = ("SPY", "IWM", "MTUM", "SPMO")
MAX_NAMES = 100
HORIZONS: tuple[int, ...] = (1, 3, 6)
RANDOM_SEEDS: tuple[int, ...] = (1, 2, 3, 4, 5)
PLACEBO_SHIFT_DAYS = 30
DATA_START = "2016-01-04"
RECENT_WINDOW_START = "2024-01-02"
#: Refutation thresholds, the card's own.
T_THRESHOLD = 2.0
RANDOM_SHARE_THRESHOLD = 0.5
MIN_SESSIONS_FOR_STATS = 40

BANDS: dict[str, tuple[int, int | None]] = {
    "all": (1, None),
    "b1_500": (1, 500),
    "b501_1500": (501, 1500),
    "b1501_plus": (1501, None),
}
BAND_LABELS = {"all": "全部", "b1_500": "1–500", "b501_1500": "501–1500", "b1501_plus": "1501+"}
UNIVERSE_VERSIONS: tuple[str, ...] = ("full", "survivors")
UNIVERSE_LABELS = {"full": "全池（含回补退市名）", "survivors": "仅归档幸存名"}

#: Every selectable variant, as a column predicate over the formation frame.
VARIANTS: dict[str, str] = {
    "any60": "过去 60 个交易日内 ≥ 1 笔可见公开市场买入（open_market_buy_count_60d > 0）",
    "usd25k": "any60 且 60 日净买入金额 ≥ 25,000 美元（net_buy_usd_60d >= 25000）",
    "cluster": "60 日内 ≥ 2 个不同买家（buyers_60d >= 2）",
    "cmp": (
        "60 日内 ≥ 1 笔 Cohen-Malloy-Pomorski 严格口径机会型买入（cmp_opportunistic_buy_60d > 0）"
    ),
    "any30": "30 日窗口代理：days_since_last_visible_buy <= 30（表里没有 30 日列）",
    "any90": "90 日窗口代理：days_since_last_visible_buy <= 90（表里没有 90 日列）",
    "any60_down20": "any60 且近 63 个交易日收益 < -20%（拆分：跌幅段）",
    "any60_notdown20": "any60 且近 63 个交易日收益 ≥ -20%（拆分：非跌幅段）",
    "any60_single": "any60 且只有 1 个买家（buyers_60d == 1，拆分：非集群）",
}
CARD_VARIANTS: tuple[str, ...] = ("any60", "usd25k", "cluster", "cmp", "any30", "any90")
SPLIT_VARIANTS: tuple[str, ...] = ("any60_down20", "any60_notdown20", "any60_single")
MAIN_VARIANT = "any60"
INSIDER_COLUMNS: tuple[str, ...] = (
    "open_market_buy_count_60d",
    "net_buy_usd_60d",
    "buyers_60d",
    "cmp_opportunistic_buy_60d",
    "days_since_last_visible_buy",
    "open_market_sell_count_60d",
)
WINDOWS: dict[str, tuple[str | None, str | None]] = {
    "full": (None, None),
    "pre_2020": (None, "2019-12-31"),
    "from_2020": ("2020-01-01", None),
    "recent_2024": (RECENT_WINDOW_START, None),
}
WINDOW_LABELS = {
    "full": "全样本",
    "pre_2020": "2020 年前",
    "from_2020": "2020 年起",
    "recent_2024": "2024 年起",
}

_T0 = time.time()


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')} +{time.time() - _T0:7.1f}s] {message}", flush=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n")


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"not JSON serializable: {type(value)}")


def _ns(values: pd.Series | pd.Index) -> pd.Series | pd.Index:
    """Datetime column normalized to ``datetime64[ns]`` so month_end (us),
    daily (us) and insider (ns) keys compare and join exactly."""
    return pd.to_datetime(values).astype("datetime64[ns]")


# --------------------------------------------------------------------------
# paths / roots
# --------------------------------------------------------------------------


def feature_roots(suffix: str) -> dict[str, Path]:
    return {
        "universe": FEATURES_ROOT / f"universe{suffix}",
        "daily": FEATURES_ROOT / f"daily{suffix}",
        "insider": FEATURES_ROOT / f"insider{suffix}",
    }


def placebo_roots(suffix: str) -> list[Path]:
    pattern = f"insider{suffix}_placebo_shift{PLACEBO_SHIFT_DAYS}_seed*"
    return sorted(p for p in FEATURES_ROOT.glob(pattern) if any(p.glob("20*.parquet")))


def placebo_seed_of(root: Path) -> str:
    return root.name.rsplit("seed", 1)[-1]


def archive_symbols() -> set[str]:
    layout = json.loads(SIP_LAYOUT_PATH.read_text())
    shards = layout["shard_symbols"]
    out: set[str] = set()
    if isinstance(shards, dict):
        for symbols in shards.values():
            out.update(str(s) for s in symbols)
    else:
        out.update(str(s) for s in shards)
    return out


def band_of(adv_rank: pd.Series) -> pd.Series:
    rank = adv_rank.to_numpy()
    out = np.where(rank <= 500, "b1_500", np.where(rank <= 1500, "b501_1500", "b1501_plus"))
    return pd.Series(out, index=adv_rank.index, dtype="object")


# --------------------------------------------------------------------------
# stage: load
# --------------------------------------------------------------------------


def _benchmark_prices(symbols: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(close, open)`` daily frames indexed by naive trade_date."""
    raw = load_sip_bars(list(symbols), frequency="daily", start=DATA_START)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
    raw["trade_date"] = _ns(pd.to_datetime(raw["timestamp"].dt.date))
    raw = raw.sort_values(["symbol", "timestamp"]).drop_duplicates(
        ["symbol", "trade_date"], keep="last"
    )
    close = raw.pivot(index="trade_date", columns="symbol", values="close").astype("float64")
    open_ = raw.pivot(index="trade_date", columns="symbol", values="open").astype("float64")
    return close.sort_index(), open_.sort_index()


def _read_insider_at(root: Path, years: list[int], dates: set[pd.Timestamp]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for year in years:
        path = root / f"{year}.parquet"
        if not path.exists():
            continue
        frame = pd.read_parquet(path, columns=["symbol", "trade_date", *INSIDER_COLUMNS])
        frame["trade_date"] = _ns(frame["trade_date"])
        frame = frame.loc[frame["trade_date"].isin(dates)]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["symbol", "trade_date", *INSIDER_COLUMNS])
    out = pd.concat(frames, ignore_index=True)
    out["symbol"] = out["symbol"].astype(str)
    for column in INSIDER_COLUMNS:
        out[column] = pd.to_numeric(out[column], errors="coerce").astype("float64")
    return out


def _latest_insider_date(root: Path) -> pd.Timestamp | None:
    files = sorted(p for p in root.glob("20*.parquet") if p.stem.isdigit())
    if not files:
        return None
    dates = pd.read_parquet(files[-1], columns=["trade_date"])["trade_date"]
    return pd.Timestamp(_ns(dates).max())


def stage_load(args: argparse.Namespace) -> None:
    manifest_path = CACHE_DIR / "load_manifest.json"
    if manifest_path.exists() and not args.force:
        _log(f"load: {manifest_path} present -- reusing (pass --force to rebuild)")
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    roots = feature_roots(args.features_suffix)
    for name, root in roots.items():
        if not any(root.glob("20*.parquet")):
            raise SystemExit(f"load: {name} root {root} has no year files yet")
    daily_years = sorted(
        int(p.stem) for p in roots["daily"].glob("20*.parquet") if p.stem.isdigit()
    )
    years = [y for y in (args.years or daily_years) if y in daily_years]
    _log(f"load: features_suffix={args.features_suffix!r} years={years}")

    universe = load_universe_panel(roots["universe"], years=years)
    universe["month_end"] = _ns(universe["month_end"])
    universe["symbol"] = universe["symbol"].astype(str)
    cohort_sizes = universe.groupby("month_end").size()
    formation_dates = sorted(
        pd.Timestamp(d) for d, n in cohort_sizes.items() if n >= DEFAULT_MIN_COHORT_SYMBOLS
    )
    _log(
        f"load: universe {len(universe):,} rows, {universe['symbol'].nunique():,} symbols, "
        f"{len(formation_dates)} cohort dates "
        f"{formation_dates[0].date()}..{formation_dates[-1].date()}"
    )

    latest_insider = _latest_insider_date(roots["insider"])
    if latest_insider is None:
        raise SystemExit("load: insider root has no year files")
    wanted_dates = set(formation_dates) | {latest_insider}

    close_frames: list[pd.DataFrame] = []
    open_frames: list[pd.DataFrame] = []
    ret63_frames: list[pd.DataFrame] = []
    for year in years:
        path = roots["daily"] / f"{year}.parquet"
        table = pq.read_table(path, columns=["symbol", "trade_date", "open", "close", "ret_63"])
        frame = table.to_pandas()
        del table
        frame["trade_date"] = _ns(frame["trade_date"])
        frame["symbol"] = frame["symbol"].astype(str)
        frame = frame.drop_duplicates(["trade_date", "symbol"], keep="last")
        close_frames.append(frame.pivot(index="trade_date", columns="symbol", values="close"))
        open_frames.append(frame.pivot(index="trade_date", columns="symbol", values="open"))
        at = frame.loc[frame["trade_date"].isin(wanted_dates), ["symbol", "trade_date", "ret_63"]]
        ret63_frames.append(at.copy())
        _log(f"load: daily {year}: {len(frame):,} rows, {frame['symbol'].nunique():,} symbols")
        del frame
    close_wide = pd.concat(close_frames).sort_index().astype("float64")
    open_wide = pd.concat(open_frames).sort_index().astype("float64")
    del close_frames, open_frames
    close_wide = close_wide.reindex(columns=sorted(close_wide.columns))
    open_wide = open_wide.reindex(columns=close_wide.columns)
    close_wide.columns = close_wide.columns.astype(str)
    open_wide.columns = open_wide.columns.astype(str)
    close_wide.index = _ns(close_wide.index)
    open_wide.index = _ns(open_wide.index)

    bench_close, bench_open = _benchmark_prices((*BENCHMARK_SYMBOLS, CASH_SYMBOL))
    bench_close = bench_close.reindex(close_wide.index)
    bench_open = bench_open.reindex(close_wide.index)
    close_wide[CASH_SYMBOL] = bench_close[CASH_SYMBOL]
    open_wide[CASH_SYMBOL] = bench_open[CASH_SYMBOL]
    bench_returns = bench_close.pct_change(fill_method=None)
    bench_returns.index.name = "trade_date"
    _log(
        f"load: price matrix {close_wide.shape[0]} sessions x {close_wide.shape[1]} symbols, "
        f"{close_wide.index[0].date()}..{close_wide.index[-1].date()}"
    )
    close_wide.to_parquet(CACHE_DIR / "close_wide.parquet")
    open_wide.to_parquet(CACHE_DIR / "open_wide.parquet")
    bench_returns.to_parquet(CACHE_DIR / "benchmark_returns.parquet")
    last_price_date = pd.Timestamp(close_wide.index[-1])
    price_dates = close_wide.index
    del close_wide, open_wide

    ret63 = pd.concat(ret63_frames, ignore_index=True)
    ret63["ret_63"] = pd.to_numeric(ret63["ret_63"], errors="coerce").astype("float64")
    del ret63_frames

    if latest_insider.year not in years:
        # Same rationale as `insider_years` below: the as-of `ret_63` shown
        # in the paper section's top-20 table must come from its own year
        # file even when `--years` excludes that year, or it is silently
        # left as NaN for every symbol.
        latest_daily_path = roots["daily"] / f"{latest_insider.year}.parquet"
        if latest_daily_path.exists():
            latest_daily = pq.read_table(
                latest_daily_path, columns=["symbol", "trade_date", "ret_63"]
            ).to_pandas()
            latest_daily["trade_date"] = _ns(latest_daily["trade_date"])
            latest_daily["symbol"] = latest_daily["symbol"].astype(str)
            latest_daily = latest_daily.loc[
                latest_daily["trade_date"] == latest_insider
            ].drop_duplicates(["trade_date", "symbol"], keep="last")
            latest_daily["ret_63"] = pd.to_numeric(latest_daily["ret_63"], errors="coerce").astype(
                "float64"
            )
            ret63 = pd.concat([ret63, latest_daily], ignore_index=True)
            del latest_daily

    # `latest_insider` (used for the paper as-of section) is the true latest
    # date in the insider table, independent of `--years`; if that date falls
    # in a year outside the `--years` filter (e.g. a smoke test restricted to
    # past years while the insider table already has this year's data), it
    # must still be read or the as-of merge below silently produces all-NaN
    # insider columns for every symbol.
    insider_years = sorted(set(years) | {latest_insider.year})
    insider = _read_insider_at(roots["insider"], insider_years, wanted_dates)
    _log(f"load: insider rows at formation/latest dates: {len(insider):,}")

    archive = archive_symbols()
    rows = universe.loc[
        universe["month_end"].isin(formation_dates),
        ["month_end", "symbol", "adv_rank", "dollar_adv", "close"],
    ].rename(columns={"month_end": "formation_date"})
    rows["adv_rank"] = rows["adv_rank"].astype("int64")
    rows["is_backfilled"] = ~rows["symbol"].isin(archive)
    rows["band"] = band_of(rows["adv_rank"])
    rows = rows.merge(
        ret63.rename(columns={"trade_date": "formation_date"}),
        on=["formation_date", "symbol"],
        how="left",
    )
    rows = rows.merge(
        insider.rename(columns={"trade_date": "formation_date"}),
        on=["formation_date", "symbol"],
        how="left",
    )
    coverage = rows.groupby("formation_date")["open_market_buy_count_60d"].apply(
        lambda s: float(s.notna().mean())
    )
    # A formation date needs (a) an insider row for the cohort (the table
    # starts 2016-01-04 and stops at its as_of) and (b) at least two sessions
    # of prices after it (next-open fill plus one marked day).
    keep_dates = [
        d
        for d in formation_dates
        if coverage.get(d, 0.0) > 0.5
        and price_dates.searchsorted(d, side="right") + 1 < len(price_dates)
    ]
    dropped = [d for d in formation_dates if d not in set(keep_dates)]
    if dropped:
        _log(
            f"load: dropping {len(dropped)} formation dates without insider coverage or "
            f"post-formation prices: {[d.date().isoformat() for d in dropped]}"
        )
    rows = rows.loc[rows["formation_date"].isin(keep_dates)].reset_index(drop=True)
    rows.to_parquet(CACHE_DIR / "formation.parquet", index=False)
    n_backfilled = int(rows.drop_duplicates("symbol")["is_backfilled"].sum())
    _log(
        f"load: formation frame {len(rows):,} rows, {rows['formation_date'].nunique()} dates, "
        f"{rows['symbol'].nunique():,} symbols ({n_backfilled:,} backfilled)"
    )

    # Latest as-of rows for the paper section: the cohort in effect on the
    # latest insider date joined with that date's insider row and ret_63.
    latest_cohort = universe_as_of_calendar_month(universe, latest_insider)
    latest_month = universe.loc[universe["month_end"] <= latest_insider, "month_end"].max()
    latest_rows = universe.loc[
        (universe["month_end"] == latest_month) & universe["symbol"].isin(latest_cohort),
        ["symbol", "adv_rank", "dollar_adv", "close"],
    ].copy()
    latest_rows["as_of"] = latest_insider
    latest_rows["cohort_month_end"] = latest_month
    latest_rows["is_backfilled"] = ~latest_rows["symbol"].isin(archive)
    latest_rows["band"] = band_of(latest_rows["adv_rank"].astype("int64"))
    latest_rows = latest_rows.merge(
        ret63.loc[ret63["trade_date"] == latest_insider, ["symbol", "ret_63"]],
        on="symbol",
        how="left",
    )
    latest_rows = latest_rows.merge(
        insider.loc[insider["trade_date"] == latest_insider].drop(columns=["trade_date"]),
        on="symbol",
        how="left",
    )
    latest_rows.to_parquet(CACHE_DIR / "latest_asof.parquet", index=False)

    placebo_found: dict[str, str] = {}
    for root in placebo_roots(args.features_suffix):
        seed = placebo_seed_of(root)
        frame = _read_insider_at(root, years, set(keep_dates))
        frame.rename(columns={"trade_date": "formation_date"}).to_parquet(
            CACHE_DIR / f"placebo_{seed}.parquet", index=False
        )
        placebo_found[seed] = str(root.relative_to(ROOT))
        _log(f"load: placebo seed {seed}: {len(frame):,} rows")

    band_sizes = rows.groupby([rows["formation_date"].dt.year, "band"]).size().unstack(fill_value=0)
    manifest = {
        "features_suffix": args.features_suffix,
        "roots": {k: str(v.relative_to(ROOT)) for k, v in roots.items()},
        "years": years,
        "formation_dates": [d.date().isoformat() for d in keep_dates],
        "formation_dates_dropped": [d.date().isoformat() for d in dropped],
        "latest_insider_date": latest_insider.date().isoformat(),
        "latest_cohort_month_end": pd.Timestamp(latest_month).date().isoformat(),
        "last_price_date": last_price_date.date().isoformat(),
        "price_sessions": int(len(price_dates)),
        "symbols_in_formation_frame": int(rows["symbol"].nunique()),
        "symbols_backfilled": int(rows.drop_duplicates("symbol")["is_backfilled"].sum()),
        "archive_symbols": len(archive),
        "band_rows_per_year": {
            str(y): {str(b): int(v) for b, v in r.items()} for y, r in band_sizes.iterrows()
        },
        "placebo_tables": placebo_found,
        "insider_manifest": json.loads((roots["insider"] / "_build_manifest.json").read_text())
        if (roots["insider"] / "_build_manifest.json").exists()
        else None,
    }
    _write_json(manifest_path, manifest)
    _log("load: done")


# --------------------------------------------------------------------------
# books
# --------------------------------------------------------------------------

Tranches = dict[pd.Timestamp, dict[str, float]]


def variant_mask(frame: pd.DataFrame, variant: str) -> pd.Series:
    buys = frame["open_market_buy_count_60d"].fillna(0.0)
    any60 = buys > 0
    if variant == "any60":
        return any60
    if variant == "usd25k":
        return any60 & (frame["net_buy_usd_60d"].fillna(0.0) >= 25_000.0)
    if variant == "cluster":
        return frame["buyers_60d"].fillna(0.0) >= 2
    if variant == "cmp":
        return frame["cmp_opportunistic_buy_60d"].fillna(0.0) > 0
    if variant == "any30":
        return frame["days_since_last_visible_buy"].le(30).fillna(False)
    if variant == "any90":
        return frame["days_since_last_visible_buy"].le(90).fillna(False)
    if variant == "any60_down20":
        return any60 & frame["ret_63"].lt(-0.20).fillna(False)
    if variant == "any60_notdown20":
        return any60 & frame["ret_63"].ge(-0.20).fillna(False)
    if variant == "any60_single":
        return any60 & (frame["buyers_60d"].fillna(0.0) == 1)
    raise KeyError(variant)


def band_frame(formation: pd.DataFrame, universe_version: str, band: str) -> pd.DataFrame:
    frame = formation if universe_version == "full" else formation.loc[~formation["is_backfilled"]]
    low, high = BANDS[band]
    mask = frame["adv_rank"] >= low
    if high is not None:
        mask &= frame["adv_rank"] <= high
    return frame.loc[mask]


def equal_weight_tranches(
    eligible: pd.DataFrame, dates: list[pd.Timestamp], *, max_names: int | None
) -> Tranches:
    """One equal-weight tranche per formation date from ``eligible`` rows; when
    more than ``max_names`` qualify the largest ``net_buy_usd_60d`` are kept
    (ties broken by symbol so the book is deterministic)."""
    out: Tranches = {d: {} for d in dates}
    for date, rows in eligible.groupby("formation_date", sort=True):
        if max_names is not None and len(rows) > max_names:
            rows = rows.sort_values(["net_buy_usd_60d", "symbol"], ascending=[False, True]).head(
                max_names
            )
        symbols = sorted(rows["symbol"].astype(str))
        if not symbols:
            continue
        weight = 1.0 / len(symbols)
        out[pd.Timestamp(date)] = {s: weight for s in symbols}
    return out


def random_tranches(
    pool: pd.DataFrame,
    sizes: dict[pd.Timestamp, int],
    dates: list[pd.Timestamp],
    rng: np.random.Generator,
) -> Tranches:
    """Same-size random control: at every formation date draw exactly as many
    names as the real tranche holds, uniformly from the same band's cohort."""
    out: Tranches = {d: {} for d in dates}
    grouped = {
        pd.Timestamp(d): sorted(r["symbol"].astype(str)) for d, r in pool.groupby("formation_date")
    }
    for date in dates:
        n = sizes.get(date, 0)
        candidates = grouped.get(date, [])
        if n <= 0 or not candidates:
            continue
        n = min(n, len(candidates))
        picked = rng.choice(np.asarray(candidates, dtype=object), size=n, replace=False)
        out[date] = {str(s): 1.0 / n for s in picked}
    return out


def overlapping_schedule(
    tranches: Tranches, dates: list[pd.Timestamp], k: int
) -> list[RebalanceEvent]:
    """``k`` overlapping monthly tranches, 1/k of capital each, normalized to
    100% invested across the tranches that are non-empty; a month with no
    non-empty tranche at all sits in ``CASH_SYMBOL``."""
    events: list[RebalanceEvent] = []
    for i, date in enumerate(dates):
        weights: dict[str, float] = {}
        live = 0
        for j in range(k):
            if i - j < 0:
                continue
            tranche = tranches.get(dates[i - j], {})
            if not tranche:
                continue
            live += 1
            for symbol, weight in tranche.items():
                weights[symbol] = weights.get(symbol, 0.0) + weight / k
        if live == 0:
            selected = {CASH_SYMBOL: 1.0}
        else:
            scale = k / live
            selected = {s: w * scale for s, w in weights.items()}
        events.append(
            RebalanceEvent(
                date=date.isoformat(), universe_size=0, selected=selected, portfolio_beta=None
            )
        )
    return events


def book_stats(
    tranches: Tranches, events: list[RebalanceEvent], dates: list[pd.Timestamp], k: int
) -> dict[str, Any]:
    sizes = [len(tranches.get(d, {})) for d in dates]
    turnover = turnover_per_rebalance(events)
    positions = [len([s for s in e.selected if s != CASH_SYMBOL]) for e in events]
    cash_months = sum(1 for e in events if CASH_SYMBOL in e.selected)
    raw_exposure = [
        sum(1 for j in range(k) if i - j >= 0 and tranches.get(dates[i - j], {})) / min(k, i + 1)
        for i in range(len(dates))
    ]
    return {
        "months": len(dates),
        "tranche_size_mean": float(np.mean(sizes)) if sizes else 0.0,
        "tranche_size_min": int(np.min(sizes)) if sizes else 0,
        "tranche_size_max": int(np.max(sizes)) if sizes else 0,
        "tranche_size_latest": int(sizes[-1]) if sizes else 0,
        "empty_tranches": int(sum(1 for s in sizes if s == 0)),
        "positions_mean": float(np.mean(positions)) if positions else 0.0,
        "cash_months": int(cash_months),
        "raw_exposure_mean": float(np.mean(raw_exposure)) if raw_exposure else 0.0,
        "turnover_per_month_mean": float(np.mean(turnover[1:])) if len(turnover) > 1 else None,
        "turnover_annualized": float(np.mean(turnover[1:]) * 12.0) if len(turnover) > 1 else None,
    }


# --------------------------------------------------------------------------
# stage: price
# --------------------------------------------------------------------------


@dataclass
class Context:
    formation: pd.DataFrame
    close_wide: pd.DataFrame
    open_wide: pd.DataFrame
    bench_returns: pd.DataFrame
    dates: list[pd.Timestamp]
    placebo: dict[str, pd.DataFrame]
    manifest: dict[str, Any]


def load_context(*, need_prices: bool = True) -> Context:
    manifest = json.loads((CACHE_DIR / "load_manifest.json").read_text())
    formation = pd.read_parquet(CACHE_DIR / "formation.parquet")
    formation["formation_date"] = _ns(formation["formation_date"])
    dates = sorted(pd.Timestamp(d) for d in formation["formation_date"].unique())
    bench = pd.read_parquet(CACHE_DIR / "benchmark_returns.parquet")
    bench.index = _ns(bench.index)
    placebo: dict[str, pd.DataFrame] = {}
    for path in sorted(CACHE_DIR.glob("placebo_*.parquet")):
        frame = pd.read_parquet(path)
        frame["formation_date"] = _ns(frame["formation_date"])
        placebo[path.stem.split("_", 1)[1]] = frame
    if need_prices:
        close_wide = pd.read_parquet(CACHE_DIR / "close_wide.parquet")
        open_wide = pd.read_parquet(CACHE_DIR / "open_wide.parquet")
        close_wide.index = _ns(close_wide.index)
        open_wide.index = _ns(open_wide.index)
    else:
        close_wide = pd.DataFrame()
        open_wide = pd.DataFrame()
    return Context(formation, close_wide, open_wide, bench, dates, placebo, manifest)


def cell_key(
    kind: str, universe_version: str, variant: str, band: str, k: int, seed: str | int | None = None
) -> str:
    key = f"{kind}__{universe_version}__{variant}__{band}__k{k}"
    return key if seed is None else f"{key}__s{seed}"


def _returns_path(key: str) -> Path:
    return RETURNS_DIR / f"{key}.parquet"


def price_events(
    ctx: Context, events: list[RebalanceEvent], cost_bps: float
) -> tuple[pd.Series, int]:
    held = sorted({s for e in events for s in e.selected})
    columns = [s for s in held if s in ctx.close_wide.columns]
    missing = len(held) - len(columns)
    if CASH_SYMBOL not in columns:
        columns.append(CASH_SYMBOL)
    returns = returns_from_weight_schedule(
        events,
        ctx.close_wide[columns],
        ctx.bench_returns["SPY"].fillna(0.0),
        cost_bps_per_side=cost_bps,
        include_hedge=False,
        execution=EXECUTION,
        open_wide=ctx.open_wide[columns],
    )
    return returns, missing


def _save_cell(key: str, returns: pd.Series, stats: dict[str, Any]) -> None:
    RETURNS_DIR.mkdir(parents=True, exist_ok=True)
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"trade_date": returns.index, "ret": returns.to_numpy(dtype="float64")})
    frame.to_parquet(_returns_path(key), index=False)
    _write_json(BOOKS_DIR / f"{key}.json", stats)


def _cell_done(key: str) -> bool:
    return _returns_path(key).exists() and (BOOKS_DIR / f"{key}.json").exists()


def _price_and_save(
    ctx: Context,
    key: str,
    tranches: Tranches,
    k: int,
    *,
    cost_bps: float = PRIMARY_COST_BPS,
    extra: dict[str, Any] | None = None,
) -> None:
    events = overlapping_schedule(tranches, ctx.dates, k)
    returns, missing = price_events(ctx, events, cost_bps)
    stats = book_stats(tranches, events, ctx.dates, k)
    stats["symbols_missing_from_price_matrix"] = missing
    stats["price_hygiene"] = {
        k_: v
        for k_, v in kernel_loop.LAST_PRICE_HYGIENE_MANIFEST.items()
        if not isinstance(v, (list, dict))
    }
    stats["cost_bps_per_side"] = cost_bps
    if extra:
        stats.update(extra)
    _save_cell(key, returns, stats)


def enumerate_variant_order(args: argparse.Namespace) -> list[str]:
    wanted = list(args.variants) if args.variants else [*CARD_VARIANTS, *SPLIT_VARIANTS]
    ordered = (
        [MAIN_VARIANT] + [v for v in CARD_VARIANTS if v != MAIN_VARIANT] + list(SPLIT_VARIANTS)
    )
    return [v for v in ordered if v in wanted]


def stage_price(args: argparse.Namespace) -> None:
    ctx = load_context()
    horizons = tuple(args.horizons) if args.horizons else HORIZONS
    seeds = RANDOM_SEEDS[: args.seeds] if args.seeds else RANDOM_SEEDS
    bands = list(args.bands) if args.bands else list(BANDS)
    universe_versions = (
        list(args.universe_versions) if args.universe_versions else list(UNIVERSE_VERSIONS)
    )
    variants = enumerate_variant_order(args)
    _log(
        f"price: {len(ctx.dates)} formation dates, variants={variants}, bands={bands}, "
        f"horizons={horizons}, seeds={seeds}, universe_versions={universe_versions}, "
        f"placebo seeds loaded={sorted(ctx.placebo)}"
    )
    done = 0
    skipped = 0

    # --- same-band equal weight (one per universe version x band x k) ------
    for uv in universe_versions:
        for band in bands:
            pool = band_frame(ctx.formation, uv, band)
            if pool.empty:
                continue
            ew = None
            for k in horizons:
                key = cell_key("ew", uv, "band", band, k)
                if _cell_done(key) and not args.force:
                    skipped += 1
                    continue
                ew = ew or equal_weight_tranches(pool, ctx.dates, max_names=None)
                _price_and_save(ctx, key, ew, k)
                done += 1
                _log(f"price: {key} done")

    # --- real books + same-size random controls -----------------------------
    for variant in variants:
        for uv in universe_versions:
            for band in bands:
                pool = band_frame(ctx.formation, uv, band)
                if pool.empty:
                    continue
                eligible = pool.loc[variant_mask(pool, variant)]
                real = equal_weight_tranches(eligible, ctx.dates, max_names=MAX_NAMES)
                sizes = {d: len(t) for d, t in real.items()}
                if sum(sizes.values()) == 0:
                    _log(f"price: {uv}/{variant}/{band}: no eligible names at any date -- skipped")
                    continue
                for k in horizons:
                    key = cell_key("real", uv, variant, band, k)
                    if not (_cell_done(key) and not args.force):
                        _price_and_save(ctx, key, real, k)
                        done += 1
                        _log(
                            f"price: {key} done (tranche mean {np.mean(list(sizes.values())):.1f})"
                        )
                    else:
                        skipped += 1
                    if variant == MAIN_VARIANT and uv == "full":
                        key_stress = cell_key("stress", uv, variant, band, k)
                        if not (_cell_done(key_stress) and not args.force):
                            _price_and_save(ctx, key_stress, real, k, cost_bps=STRESS_COST_BPS)
                            done += 1
                for seed in seeds:
                    rng = np.random.default_rng(
                        [
                            int(seed),
                            list(VARIANTS).index(variant),
                            list(BANDS).index(band),
                            UNIVERSE_VERSIONS.index(uv),
                        ]
                    )
                    control: Tranches | None = None
                    for k in horizons:
                        key = cell_key("random", uv, variant, band, k, seed)
                        if _cell_done(key) and not args.force:
                            skipped += 1
                            continue
                        control = control or random_tranches(pool, sizes, ctx.dates, rng)
                        _price_and_save(ctx, key, control, k, extra={"seed": int(seed)})
                        done += 1
                _log(f"price: {uv}/{variant}/{band}: random controls done")

    # --- placebo (filing-date shift tables), full universe only --------------
    if not args.skip_placebo:
        for seed, placebo_frame in ctx.placebo.items():
            base = ctx.formation.drop(columns=list(INSIDER_COLUMNS)).merge(
                placebo_frame, on=["formation_date", "symbol"], how="left"
            )
            for variant in variants:
                if variant in SPLIT_VARIANTS:
                    continue
                for band in bands:
                    pool = band_frame(base, "full", band)
                    if pool.empty:
                        continue
                    eligible = pool.loc[variant_mask(pool, variant)]
                    tranches = equal_weight_tranches(eligible, ctx.dates, max_names=MAX_NAMES)
                    if not any(tranches.values()):
                        continue
                    for k in horizons:
                        key = cell_key("placebo", "full", variant, band, k, seed)
                        if _cell_done(key) and not args.force:
                            skipped += 1
                            continue
                        _price_and_save(ctx, key, tranches, k, extra={"placebo_seed": seed})
                        done += 1
            _log(f"price: placebo seed {seed} done")
    _log(f"price: finished -- {done} cells priced, {skipped} reused")


# --------------------------------------------------------------------------
# stage: report
# --------------------------------------------------------------------------


def monthly_returns(series: pd.Series) -> pd.Series:
    return (1.0 + series).groupby(series.index.to_period("M")).prod() - 1.0


def nw_tstat(values: np.ndarray, lag: int) -> float:
    """Newey-West (Bartlett) t-statistic of the mean; ``lag = k - 1`` for a
    k-month overlapping-tranche book, 0 for plain."""
    clean = np.asarray(values, dtype="float64")
    clean = clean[np.isfinite(clean)]
    n = len(clean)
    if n < 6:
        return float("nan")
    mean = clean.mean()
    resid = clean - mean
    variance = float(resid @ resid) / n
    for lag_ in range(1, min(lag, n - 1) + 1):
        weight = 1.0 - lag_ / (lag + 1.0)
        variance += 2.0 * weight * float(resid[lag_:] @ resid[:-lag_]) / n
    if variance <= 0:
        return float("nan")
    return float(mean / math.sqrt(variance / n))


def slice_window(series: pd.Series, window: str) -> pd.Series:
    start, end = WINDOWS[window]
    out = series
    if start is not None:
        out = out.loc[out.index >= pd.Timestamp(start)]
    if end is not None:
        out = out.loc[out.index <= pd.Timestamp(end)]
    return out


def basic_stats(series: pd.Series, bil: pd.Series) -> dict[str, Any] | None:
    if len(series) < MIN_SESSIONS_FOR_STATS:
        return None
    excess = series - bil.reindex(series.index).fillna(0.0)
    vol = float(series.std() * math.sqrt(252.0))
    return {
        "cagr": annualized_cagr(series),
        "vol": vol,
        "max_drawdown": max_drawdown(series),
        "sharpe_excess_bil": float(excess.mean() / excess.std() * math.sqrt(252.0))
        if excess.std() > 0
        else None,
        "sessions": int(len(series)),
        "window": [series.index[0].date().isoformat(), series.index[-1].date().isoformat()],
    }


def excess_block(strategy: pd.Series, benchmark: pd.Series, lag: int) -> dict[str, Any]:
    aligned = benchmark.reindex(strategy.index).fillna(0.0)
    ex = monthly_returns(strategy) - monthly_returns(aligned)
    values = ex.to_numpy(dtype="float64")
    return {
        "mean_monthly_excess": float(np.nanmean(values)) if len(values) else None,
        "t_nw": nw_tstat(values, lag),
        "t_plain": nw_tstat(values, 0),
        "months": int(len(values)),
        "monthly_hit_rate": float(np.mean(values > 0)) if len(values) else None,
    }


def load_returns(key: str) -> pd.Series | None:
    path = _returns_path(key)
    if not path.exists():
        return None
    frame = pd.read_parquet(path)
    series = pd.Series(frame["ret"].to_numpy(dtype="float64"), index=_ns(frame["trade_date"]))
    return series.sort_index()


def load_book(key: str) -> dict[str, Any] | None:
    path = BOOKS_DIR / f"{key}.json"
    return json.loads(path.read_text()) if path.exists() else None


def _percentiles(values: list[float]) -> dict[str, float | None]:
    clean = [v for v in values if v is not None and np.isfinite(v)]
    if not clean:
        return {"mean": None, "p5": None, "p95": None, "min": None, "max": None, "n": 0}
    arr = np.asarray(clean, dtype="float64")
    return {
        "mean": float(arr.mean()),
        "p5": float(np.percentile(arr, 5)),
        "p95": float(np.percentile(arr, 95)),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "n": int(len(arr)),
    }


def cell_metrics(
    series: pd.Series,
    bench: pd.DataFrame,
    k: int,
    *,
    ew: pd.Series | None,
    random_mean: pd.Series | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    lag = max(k - 1, 0)
    for window in WINDOWS:
        sliced = slice_window(series, window)
        stats = basic_stats(sliced, bench[CASH_SYMBOL])
        if stats is None:
            out[window] = None
            continue
        try:
            stats["cagr_excess_vol_matched_spy"] = cagr_excess_vol_matched(
                sliced, bench["SPY"].fillna(0.0), bench[CASH_SYMBOL].fillna(0.0)
            )
            stats["vol_match_weight_vs_spy"] = vol_match_weight(sliced, bench["SPY"].fillna(0.0))
        except ValueError:
            stats["cagr_excess_vol_matched_spy"] = None
            stats["vol_match_weight_vs_spy"] = None
        stats["excess"] = {
            sym: excess_block(sliced, bench[sym].fillna(0.0), lag) for sym in BENCHMARK_SYMBOLS
        }
        if ew is not None:
            stats["excess"]["band_ew"] = excess_block(sliced, ew, lag)
        if random_mean is not None:
            stats["excess"]["random_mean"] = excess_block(sliced, random_mean, lag)
        out[window] = stats
    return out


def benchmark_metrics(bench: pd.DataFrame, index: pd.DatetimeIndex) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for sym in BENCHMARK_SYMBOLS:
        series = bench[sym].reindex(index).fillna(0.0)
        out[sym] = {w: basic_stats(slice_window(series, w), bench[CASH_SYMBOL]) for w in WINDOWS}
    return out


def _sig(t: float | None) -> bool:
    return t is not None and np.isfinite(t) and t >= T_THRESHOLD


def cell_verdict(real: dict[str, Any], random_agg: dict[str, Any] | None) -> dict[str, Any]:
    full = real.get("full")
    if not full:
        return {"verdict": "no_data", "reasons": ["no priced returns"]}
    ex = full["excess"]
    t_spy = ex["SPY"]["t_nw"]
    t_iwm = ex["IWM"]["t_nw"]
    t_rand = ex.get("random_mean", {}).get("t_nw")
    x_real = ex["SPY"]["mean_monthly_excess"]
    x_rand = (random_agg or {}).get("mean_monthly_excess_spy", {}).get("mean")
    share = None
    if x_real is not None and x_real > 0 and x_rand is not None:
        share = float(x_rand / x_real)
    pre = real.get("pre_2020")
    post = real.get("from_2020")
    x_pre = pre["excess"]["SPY"]["mean_monthly_excess"] if pre else None
    x_post = post["excess"]["SPY"]["mean_monthly_excess"] if post else None
    significant = _sig(t_spy) or _sig(t_iwm) or _sig(t_rand)
    crit_random = share is not None and share >= RANDOM_SHARE_THRESHOLD
    crit_pre2020_only = x_pre is not None and x_post is not None and x_pre > 0 and x_post <= 0
    reasons: list[str] = []
    if x_real is None or x_real <= 0:
        verdict = "refuted"
        code = "no_spy_excess"
        reasons.append("月超额（对 SPY）≤ 0")
    elif crit_random:
        verdict = "refuted"
        code = "random_explains"
        reasons.append(f"同尺寸随机对照达到真实超额的 {share:.0%}（≥ 50%）")
    elif crit_pre2020_only:
        verdict = "refuted"
        code = "pre_2020_only"
        reasons.append("效应只在 2020 年前（2020 年起月超额 ≤ 0）")
    elif significant and _sig(t_rand):
        verdict = "supported"
        code = "supported"
        reasons.append(
            "对 SPY/IWM 或随机对照 t ≥ 2，且对随机对照 t ≥ 2，随机份额 < 50%，2020 年起仍为正"
        )
    elif significant:
        verdict = "inconclusive"
        code = "sig_vs_bench_not_vs_random"
        reasons.append("对 SPY/IWM 显著但对同尺寸随机对照不显著（选股增量未过 t ≥ 2）")
    else:
        verdict = "inconclusive"
        code = "all_t_below_2"
        reasons.append("月超额为正但所有 t < 2")
    return {
        "verdict": verdict,
        "code": code,
        "reasons": reasons,
        "t_spy": t_spy,
        "t_iwm": t_iwm,
        "t_random": t_rand,
        "mean_monthly_excess_spy": x_real,
        "random_mean_monthly_excess_spy": x_rand,
        "random_share_of_real": share,
        "pre_2020_excess_spy": x_pre,
        "from_2020_excess_spy": x_post,
        "crit_all_t_below_2": not significant,
        "crit_random_ge_50pct": crit_random,
        "crit_pre_2020_only": crit_pre2020_only,
    }


def bh_fdr(pvalues: list[float], q: float = 0.10) -> int:
    clean = sorted(p for p in pvalues if p is not None and np.isfinite(p))
    m = len(clean)
    passed = 0
    for i, p in enumerate(clean, start=1):
        if p <= q * i / m:
            passed = i
    return passed


def _one_sided_p(t: float | None) -> float | None:
    if t is None or not np.isfinite(t):
        return None
    return float(0.5 * math.erfc(t / math.sqrt(2.0)))


def stage_report(args: argparse.Namespace) -> dict[str, Any]:
    ctx = load_context(need_prices=False)
    bench = ctx.bench_returns
    horizons = tuple(args.horizons) if args.horizons else HORIZONS
    bands = list(args.bands) if args.bands else list(BANDS)
    universe_versions = (
        list(args.universe_versions) if args.universe_versions else list(UNIVERSE_VERSIONS)
    )
    variants = enumerate_variant_order(args)
    placebo_seeds = sorted(ctx.placebo)

    cells: dict[str, Any] = {}
    reference_index: pd.DatetimeIndex | None = None
    for variant in variants:
        for uv in universe_versions:
            for band in bands:
                ew_series = {k: load_returns(cell_key("ew", uv, "band", band, k)) for k in horizons}
                for k in horizons:
                    key = cell_key("real", uv, variant, band, k)
                    series = load_returns(key)
                    if series is None:
                        continue
                    if reference_index is None:
                        reference_index = series.index
                    randoms = {
                        seed: load_returns(cell_key("random", uv, variant, band, k, seed))
                        for seed in RANDOM_SEEDS
                    }
                    randoms = {s: r for s, r in randoms.items() if r is not None}
                    random_mean = (
                        pd.concat(randoms.values(), axis=1).mean(axis=1) if randoms else None
                    )
                    real_metrics = cell_metrics(
                        series, bench, k, ew=ew_series[k], random_mean=random_mean
                    )
                    random_metrics = {
                        s: cell_metrics(r, bench, k, ew=ew_series[k], random_mean=None)
                        for s, r in randoms.items()
                    }
                    random_agg = _aggregate_controls(random_metrics)
                    placebo_metrics: dict[str, Any] = {}
                    if uv == "full":
                        for seed in placebo_seeds:
                            p = load_returns(cell_key("placebo", "full", variant, band, k, seed))
                            if p is not None:
                                placebo_metrics[seed] = cell_metrics(
                                    p, bench, k, ew=ew_series[k], random_mean=random_mean
                                )
                    placebo_agg = _aggregate_controls(placebo_metrics) if placebo_metrics else None
                    ew_metrics = (
                        cell_metrics(ew_series[k], bench, k, ew=None, random_mean=None)
                        if ew_series[k] is not None
                        else None
                    )
                    stress = load_returns(cell_key("stress", uv, variant, band, k))
                    stress_metrics = (
                        cell_metrics(stress, bench, k, ew=None, random_mean=None)
                        if stress is not None
                        else None
                    )
                    cells[key] = {
                        "universe_version": uv,
                        "variant": variant,
                        "band": band,
                        "horizon_months": k,
                        "book": load_book(key),
                        "real": real_metrics,
                        "stress_25bps": stress_metrics,
                        "band_ew": ew_metrics,
                        "band_ew_book": load_book(cell_key("ew", uv, "band", band, k)),
                        "random": {
                            "seeds": sorted(randoms),
                            "per_seed": random_metrics,
                            "aggregate": random_agg,
                        },
                        "placebo": {
                            "seeds": sorted(placebo_metrics),
                            "per_seed": placebo_metrics,
                            "aggregate": placebo_agg,
                        },
                        "verdict": cell_verdict(real_metrics, random_agg),
                    }
    if reference_index is None:
        raise SystemExit("report: no priced cells found -- run --stage price first")

    # --- card-level verdict ---------------------------------------------------
    full_cells = {k: c for k, c in cells.items() if c["universe_version"] == "full"}
    card_cells = {k: c for k, c in full_cells.items() if c["variant"] in CARD_VARIANTS}
    main_cells = {k: c for k, c in full_cells.items() if c["variant"] == MAIN_VARIANT}
    supported = [k for k, c in card_cells.items() if c["verdict"]["verdict"] == "supported"]
    any_significant = any(not c["verdict"]["crit_all_t_below_2"] for c in card_cells.values())
    code_counts = Counter(c["verdict"].get("code", "unknown") for c in card_cells.values())
    code_text = {
        "no_spy_excess": "月超额（对 SPY）≤ 0",
        "random_explains": "同尺寸随机对照达到真实超额的 ≥ 50%",
        "pre_2020_only": "效应只在 2020 年前",
        "sig_vs_bench_not_vs_random": "对 SPY/IWM 显著但选股增量（对同尺寸随机）不显著",
        "all_t_below_2": "月超额为正但所有 t < 2",
        "supported": "满足支持条件",
    }
    breakdown = "；".join(
        f"{code_text.get(code, code)} {count} 个" for code, count in code_counts.most_common()
    )
    if supported:
        card_verdict = "supported"
        card_reason = f"{len(supported)} 个（变体×分段×持有期）单元满足支持条件：{supported}"
    elif not any_significant:
        card_verdict = "refuted"
        card_reason = (
            "否定条件 (1) 命中：所有分段 × 1/3/6 月对 SPY、IWM、同尺寸随机的 t 全部 < 2"
            f"（逐格原因：{breakdown}）"
        )
    elif all(c["verdict"]["verdict"] == "refuted" for c in card_cells.values()):
        card_verdict = "refuted"
        card_reason = f"没有单元满足支持条件（逐格原因：{breakdown}）"
    else:
        card_verdict = "inconclusive"
        card_reason = f"没有单元满足支持条件，但也不是全部被否定（逐格原因：{breakdown}）"
    t_rand_p = [_one_sided_p(c["verdict"]["t_random"]) for c in full_cells.values()]
    fdr_pass = bh_fdr(t_rand_p, q=0.10)

    family_count = len(VARIANTS) * len(HORIZONS) * len(BANDS)
    summary = {
        "iteration_id": ITERATION_ID,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "load_manifest": ctx.manifest,
        "design": {
            "execution": EXECUTION,
            "cost_bps_per_side": PRIMARY_COST_BPS,
            "stress_cost_bps_per_side": STRESS_COST_BPS,
            "max_names": MAX_NAMES,
            "horizons_months": list(horizons),
            "bands": {b: list(BANDS[b]) for b in bands},
            "variants": {v: VARIANTS[v] for v in variants},
            "random_seeds": list(RANDOM_SEEDS),
            "placebo_seeds_available": placebo_seeds,
            "placebo_shift_sessions": PLACEBO_SHIFT_DAYS,
            "exposure": "normalized to 100% across non-empty tranches; all-empty month sits in BIL",
            "t_statistic": "Newey-West (Bartlett, lag = k-1) on calendar-month excess returns",
            "returns_contract": kernel_loop.PORTFOLIO_RETURNS_CONTRACT,
        },
        "benchmarks": benchmark_metrics(bench, reference_index),
        "cells": cells,
        "card_verdict": {
            "verdict": card_verdict,
            "reason": card_reason,
            "supported_cells": supported,
            "cell_reason_codes": dict(code_counts),
            "cells_evaluated_full_universe": len(full_cells),
            "card_variant_cells": len(card_cells),
            "main_variant_cells": len(main_cells),
            "cells_with_t_random_ge_2": int(
                sum(1 for c in full_cells.values() if _sig(c["verdict"]["t_random"]))
            ),
            "cells_with_any_t_ge_2": int(
                sum(1 for c in full_cells.values() if not c["verdict"]["crit_all_t_below_2"])
            ),
            "bh_fdr_q10_pass_t_random": fdr_pass,
        },
        "trial_family": {
            "family": "insider_independent_broad",
            "selectable_cells_this_round": family_count,
            "definition": (
                "variants (9) x horizons (3) x bands (4) on the full broad universe; "
                "the survivors-only twin, band-EW, random and placebo controls are not counted"
            ),
        },
    }
    _write_json(SUMMARY_PATH, summary)
    _log(f"report: wrote {SUMMARY_PATH} ({len(cells)} cells) -- card verdict {card_verdict}")
    return summary


def _aggregate_controls(per_seed: dict[Any, dict[str, Any]]) -> dict[str, Any] | None:
    if not per_seed:
        return None
    out: dict[str, Any] = {"n": len(per_seed)}
    for window in WINDOWS:
        rows = [m.get(window) for m in per_seed.values() if m.get(window)]
        if not rows:
            continue
        out[f"cagr_{window}"] = _percentiles([r["cagr"] for r in rows])
        out[f"max_drawdown_{window}"] = _percentiles([r["max_drawdown"] for r in rows])
        out[f"vol_matched_excess_spy_{window}"] = _percentiles(
            [r["cagr_excess_vol_matched_spy"] for r in rows]
        )
        out[f"mean_monthly_excess_spy_{window}"] = _percentiles(
            [r["excess"]["SPY"]["mean_monthly_excess"] for r in rows]
        )
        out[f"mean_monthly_excess_iwm_{window}"] = _percentiles(
            [r["excess"]["IWM"]["mean_monthly_excess"] for r in rows]
        )
        if all("band_ew" in r["excess"] for r in rows):
            out[f"mean_monthly_excess_band_ew_{window}"] = _percentiles(
                [r["excess"]["band_ew"]["mean_monthly_excess"] for r in rows]
            )
        if all("random_mean" in r["excess"] for r in rows):
            out[f"t_vs_random_{window}"] = _percentiles(
                [r["excess"]["random_mean"]["t_nw"] for r in rows]
            )
            out[f"mean_monthly_excess_random_{window}"] = _percentiles(
                [r["excess"]["random_mean"]["mean_monthly_excess"] for r in rows]
            )
    out["mean_monthly_excess_spy"] = out.get("mean_monthly_excess_spy_full", _percentiles([]))
    return out


# --------------------------------------------------------------------------
# stage: paper (latest-month selection)
# --------------------------------------------------------------------------


def stage_paper(args: argparse.Namespace) -> dict[str, Any]:
    latest = pd.read_parquet(CACHE_DIR / "latest_asof.parquet")
    manifest = json.loads((CACHE_DIR / "load_manifest.json").read_text())
    out: dict[str, Any] = {
        "as_of_insider_date": manifest["latest_insider_date"],
        "cohort_month_end": manifest["latest_cohort_month_end"],
        "max_names": MAX_NAMES,
        "selections": {},
    }
    variants = enumerate_variant_order(args)
    for variant in variants:
        for band in BANDS:
            pool = band_frame(
                latest.assign(formation_date=pd.Timestamp(manifest["latest_insider_date"])),
                "full",
                band,
            )
            eligible = pool.loc[variant_mask(pool, variant)]
            ranked = eligible.sort_values(["net_buy_usd_60d", "symbol"], ascending=[False, True])
            capped = ranked.head(MAX_NAMES)
            out["selections"][f"{variant}__{band}"] = {
                "variant": variant,
                "band": band,
                "eligible_names": int(len(eligible)),
                "held_names_after_cap": int(len(capped)),
                "weight_each": (1.0 / len(capped)) if len(capped) else None,
                "top20": [
                    {
                        "symbol": str(r.symbol),
                        "adv_rank": int(r.adv_rank),
                        "net_buy_usd_60d": float(r.net_buy_usd_60d)
                        if pd.notna(r.net_buy_usd_60d)
                        else None,
                        "buyers_60d": float(r.buyers_60d) if pd.notna(r.buyers_60d) else None,
                        "open_market_buy_count_60d": float(r.open_market_buy_count_60d)
                        if pd.notna(r.open_market_buy_count_60d)
                        else None,
                        "days_since_last_visible_buy": float(r.days_since_last_visible_buy)
                        if pd.notna(r.days_since_last_visible_buy)
                        else None,
                        "ret_63": float(r.ret_63) if pd.notna(r.ret_63) else None,
                        "is_backfilled": bool(r.is_backfilled),
                    }
                    for r in capped.head(20).itertuples(index=False)
                ],
                "all_held_symbols": [str(s) for s in capped["symbol"]],
            }
    _write_json(PAPER_PATH, out)
    _log(f"paper: wrote {PAPER_PATH}")
    return out


# --------------------------------------------------------------------------
# markdown
# --------------------------------------------------------------------------


def _pct(value: float | None, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def _num(value: float | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    return f"{value:.{digits}f}"


def _bp(value: float | None) -> str:
    """Monthly excess in basis points per month."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    return f"{value * 1e4:+.0f}bp"


def render_markdown(summary: dict[str, Any], paper: dict[str, Any] | None) -> str:
    cells = summary["cells"]
    man = summary["load_manifest"]
    design = summary["design"]
    lines: list[str] = []
    lines.append(
        "# H-20260917-01 内部人买入作为独立策略（全池、月频、1/3/6 月持有、按流动性分段）— 报告"
    )
    lines.append("")
    lines.append(
        f"- 生成时间：{summary['generated_at'][:16]} UTC · 数据："
        f"`{man['roots']['universe']}` / `{man['roots']['daily']}` / `{man['roots']['insider']}`"
        f"（features_suffix=`{man['features_suffix']}`）"
    )
    lines.append(
        f"- 形成日：{len(man['formation_dates'])} 个月末 cohort 日，"
        f"{man['formation_dates'][0]} .. {man['formation_dates'][-1]}；"
        f"价格到 {man['last_price_date']}；内部人表 as_of {man['latest_insider_date']}"
    )
    lines.append(
        f"- 池子：{man['symbols_in_formation_frame']:,} 个代码进过形成日 cohort，"
        f"其中 {man['symbols_backfilled']:,} 个是回补的退市/改名前代码"
        f"（不在 `data/sip/daily` 归档的 {man['archive_symbols']:,} 个里）"
    )
    lines.append(
        f"- 执行与成本：{design['execution']}，{design['cost_bps_per_side']:.0f} bp/边"
        f"（与动量账本同一口径；主单元另报 {design['stress_cost_bps_per_side']:.0f} bp 压力）；"
        f"价格卫生开启（`{design['returns_contract']}`）；暴露归一化到 100%（空月放 BIL）"
    )
    lines.append(
        f"- 统计：{design['t_statistic']}；同尺寸随机对照 {len(design['random_seeds'])} 个种子；"
        f"申报日平移 ±{design['placebo_shift_sessions']} 个交易日占位表 "
        f"**{len(design['placebo_seeds_available'])} 个**（{design['placebo_seeds_available']}）"
    )
    lines.append(
        "- 30/90 日窗口：内部人表只有 60 日列，30/90 日用 "
        "`days_since_last_visible_buy <= 30 / 90` 代理（标为 any30 / any90）。"
        "申报人角色（董事/高管/10% 股东）分档：表里没有该列，本轮未做。"
    )
    lines.append("")
    cv = summary["card_verdict"]
    lines.append(f"## 0. 结论：**{cv['verdict']}**")
    lines.append("")
    lines.append(f"- {cv['reason']}")
    lines.append(
        f"- 全池评估了 {cv['cells_evaluated_full_universe']} 个（变体 × 分段 × 持有期）单元；"
        f"其中对 SPY/IWM/随机任一 t ≥ 2 的 {cv['cells_with_any_t_ge_2']} 个，"
        f"对同尺寸随机对照 t ≥ 2 的 {cv['cells_with_t_random_ge_2']} 个，"
        f"对随机对照的单边 p 过 BH-FDR(q=0.10) 的 {cv['bh_fdr_q10_pass_t_random']} 个。"
    )
    best_key = None
    best_t = None
    for key, cell in cells.items():
        if cell.get("universe_version") != "full":
            continue
        t_r = cell["verdict"].get("t_random")
        if t_r is not None and np.isfinite(t_r) and (best_t is None or t_r > best_t):
            best_t, best_key = float(t_r), key
    if best_key is not None:
        best = cells[best_key]
        bv = best["verdict"]
        real_cagr = best["real"]["full"]["cagr"]
        x_vs_rand = best["real"]["full"]["excess"].get("random_mean", {}).get("mean_monthly_excess")
        rand_cagr_agg = ((best.get("random") or {}).get("aggregate")) or {}
        rand_cagr = rand_cagr_agg.get("cagr_full", {})
        rand_mean = rand_cagr.get("mean")
        rand_p95 = rand_cagr.get("p95")
        random_text = ""
        if rand_mean is not None:
            random_text = f"，同尺寸随机 CAGR 均值 {rand_mean:.1%}"
            if rand_p95 is not None:
                random_text += f"（p95 {rand_p95:.1%}）"
        lines.append(
            "- 选股增量（与本报告的判定分开看）：对同尺寸随机对照最强的单元是 "
            f"`{best_key}`，月超额 vs 随机 {_bp(x_vs_rand)} "
            f"t={_num(bv.get('t_random'), 1)}；该单元 CAGR {real_cagr:.1%}"
            + random_text
            + "。对随机显著说明"
            "「按内部人买入选股」比在同一池子里随便挑同样多的名字更好；它不等于跑赢 SPY。"
        )
    tf = summary["trial_family"]
    lines.append(
        f"- 假设族 `{tf['family']}` 本轮可被选中的单元数 "
        f"{tf['selectable_cells_this_round']}（{tf['definition']}）。"
    )
    lines.append("")

    # benchmarks
    lines.append("## 1. 必报对照（买入持有，收盘到收盘，无成本）")
    lines.append("")
    lines.append("| 窗口 | SPY CAGR / 回撤 | IWM | MTUM | SPMO |")
    lines.append("|---|---:|---:|---:|---:|")
    for window in WINDOWS:
        row = [WINDOW_LABELS[window]]
        for sym in BENCHMARK_SYMBOLS:
            b = summary["benchmarks"][sym].get(window)
            row.append(f"{_pct(b['cagr'])} / {_pct(b['max_drawdown'])}" if b else "n/a")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # headline table: main variant
    def cell(uv: str, variant: str, band: str, k: int) -> dict[str, Any] | None:
        return cells.get(cell_key("real", uv, variant, band, k))

    def headline_rows(variant: str, uv: str) -> list[str]:
        rows: list[str] = []
        for band in BANDS:
            for k in HORIZONS:
                c = cell(uv, variant, band, k)
                if not c or not c["real"].get("full"):
                    continue
                f = c["real"]["full"]
                ex = f["excess"]
                v = c["verdict"]
                ra = c["random"]["aggregate"] or {}
                pa = c["placebo"]["aggregate"] or {}
                rand_x = ra.get("mean_monthly_excess_spy_full", {})
                rand_cagr = ra.get("cagr_full", {})
                plc_x = pa.get("mean_monthly_excess_spy_full", {})
                book = c["book"] or {}
                tranche_txt = (
                    f"{book.get('tranche_size_mean', 0):.0f} "
                    f"({book.get('tranche_size_min', 0)}–{book.get('tranche_size_max', 0)})"
                )
                spy_txt = (
                    f"{_bp(ex['SPY']['mean_monthly_excess'])} (t {_num(ex['SPY']['t_nw'], 1)})"
                )
                iwm_txt = (
                    f"{_bp(ex['IWM']['mean_monthly_excess'])} (t {_num(ex['IWM']['t_nw'], 1)})"
                )
                band_ew = ex.get("band_ew", {})
                band_ew_txt = (
                    f"{_bp(band_ew.get('mean_monthly_excess'))} (t {_num(band_ew.get('t_nw'), 1)})"
                )
                rand_mean = ex.get("random_mean", {})
                rand_mean_txt = (
                    f"{_bp(rand_mean.get('mean_monthly_excess'))} "
                    f"(t {_num(rand_mean.get('t_nw'), 1)})"
                )
                rand_cagr_txt = (
                    f"{_pct(rand_cagr.get('mean'))} "
                    f"[{_pct(rand_cagr.get('p5'))}, {_pct(rand_cagr.get('p95'))}]; "
                    f"超额 {_bp(rand_x.get('mean'))}"
                ) + (
                    f"，占真实 {v['random_share_of_real']:.0%}"
                    if v.get("random_share_of_real") is not None
                    else ""
                )
                placebo_txt = (
                    (
                        f"{_bp(plc_x.get('mean'))} "
                        f"[{_bp(plc_x.get('p5'))}, {_bp(plc_x.get('p95'))}] "
                        f"n={plc_x.get('n', 0)}"
                    )
                    if plc_x
                    else "未建"
                )
                pre_from_2020_txt = (
                    f"{_bp(v.get('pre_2020_excess_spy'))} / {_bp(v.get('from_2020_excess_spy'))}"
                )
                rows.append(
                    "| "
                    + " | ".join(
                        [
                            BAND_LABELS[band],
                            str(k),
                            tranche_txt,
                            _pct(f["cagr"]),
                            _pct(f["max_drawdown"]),
                            _pct(f["vol"]),
                            spy_txt,
                            iwm_txt,
                            band_ew_txt,
                            rand_mean_txt,
                            _pct(f["cagr_excess_vol_matched_spy"]),
                            rand_cagr_txt,
                            placebo_txt,
                            pre_from_2020_txt,
                            _num(book.get("turnover_per_month_mean"), 2),
                            v["verdict"],
                        ]
                    )
                    + " |"
                )
        return rows

    header = (
        "| 分段 | 持有(月) | 每月只数 均值(最小–最大) | CAGR | 最大回撤 | 年化波动 | "
        "月超额 vs SPY | vs IWM | vs 同段等权 | vs 同尺寸随机均值 | "
        "同波动 SPY 超额 | 同尺寸随机 CAGR 均值 [p5, p95]; 月超额 | "
        "申报日平移占位 月超额 vs SPY [p5,p95] | "
        "月超额 vs SPY 2020 前 / 2020 起 | 月双边换手 | 判定 |"
    )
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---:|---|"
    lines.append(f"## 2. 主单元 `{MAIN_VARIANT}`（{VARIANTS[MAIN_VARIANT]}）— 全样本")
    lines.append("")
    for uv in UNIVERSE_VERSIONS:
        rows = headline_rows(MAIN_VARIANT, uv)
        if not rows:
            continue
        lines.append(f"### 2.{UNIVERSE_VERSIONS.index(uv) + 1} {UNIVERSE_LABELS[uv]}")
        lines.append("")
        lines.append(header)
        lines.append(sep)
        lines.extend(rows)
        lines.append("")
    # survivorship direction
    lines.append("### 2.3 幸存者偏差方向（全池 − 仅幸存名，月超额 vs SPY，全样本）")
    lines.append("")
    lines.append(
        "| 分段 | 持有(月) | 全池 CAGR | 仅幸存 CAGR | 全池月超额 | 仅幸存月超额 | "
        "差（全池−幸存） | 方向 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for band in BANDS:
        for k in HORIZONS:
            a = cell("full", MAIN_VARIANT, band, k)
            b = cell("survivors", MAIN_VARIANT, band, k)
            if not a or not b or not a["real"].get("full") or not b["real"].get("full"):
                continue
            xa = a["real"]["full"]["excess"]["SPY"]["mean_monthly_excess"]
            xb = b["real"]["full"]["excess"]["SPY"]["mean_monthly_excess"]
            diff = None if xa is None or xb is None else xa - xb
            direction = (
                "n/a"
                if diff is None
                else (
                    "回补后更好：旧的幸存者池低估了效应"
                    if diff > 0
                    else "回补后更差：旧的幸存者池高估了效应"
                )
            )
            cagr_a = _pct(a["real"]["full"]["cagr"])
            cagr_b = _pct(b["real"]["full"]["cagr"])
            lines.append(
                f"| {BAND_LABELS[band]} | {k} | {cagr_a} | {cagr_b} | "
                f"{_bp(xa)} | {_bp(xb)} | {_bp(diff)} | {direction} |"
            )
    lines.append("")
    # recent window for main variant
    lines.append("### 2.4 主单元 2024 年起（合同口径窗口）")
    lines.append("")
    lines.append(
        "| 分段 | 持有(月) | CAGR | 最大回撤 | 同波动 SPY 超额 | 月超额 vs SPY (t) | "
        "vs 随机均值 (t) | 25bp 压力 CAGR |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for band in BANDS:
        for k in HORIZONS:
            c = cell("full", MAIN_VARIANT, band, k)
            if not c or not c["real"].get("recent_2024"):
                continue
            r = c["real"]["recent_2024"]
            s = (c.get("stress_25bps") or {}).get("recent_2024")
            r_spy = r["excess"]["SPY"]
            r_random = r["excess"].get("random_mean", {})
            lines.append(
                f"| {BAND_LABELS[band]} | {k} | {_pct(r['cagr'])} | "
                f"{_pct(r['max_drawdown'])} | {_pct(r['cagr_excess_vol_matched_spy'])} | "
                f"{_bp(r_spy['mean_monthly_excess'])} ({_num(r_spy['t_nw'], 1)}) | "
                f"{_bp(r_random.get('mean_monthly_excess'))} ({_num(r_random.get('t_nw'), 1)}) | "
                f"{_pct(s['cagr']) if s else 'n/a'} |"
            )
    lines.append("")

    # other variants
    lines.append("## 3. 其余变体与拆分（全池，全样本）")
    lines.append("")
    for variant in [v for v in VARIANTS if v != MAIN_VARIANT]:
        rows = headline_rows(variant, "full")
        if not rows:
            continue
        lines.append(f"### `{variant}` — {VARIANTS[variant]}")
        lines.append("")
        lines.append(header)
        lines.append(sep)
        lines.extend(rows)
        lines.append("")

    # verdict grid
    lines.append(
        "## 4. 否定条件逐格判定（全池，卡上的三条：(1) 所有分段 1/3/6 月 |t| < 2；"
        "(2) 同尺寸随机 ≥ 真实 50%；(3) 效应只在 2020 年前）"
    )
    lines.append("")
    lines.append(
        "| 变体 | 分段 | 持有 | t vs SPY | t vs IWM | t vs 随机 | 随机占真实 | 2020 前 / 起 | "
        "(1) 全 t<2 | (2) 随机≥50% | (3) 仅 2020 前 | 判定 |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---|:-:|:-:|:-:|---|")
    for _key, c in cells.items():
        if c["universe_version"] != "full":
            continue
        v = c["verdict"]
        share = v.get("random_share_of_real")
        share_text = "n/a" if share is None else format(share, ".0%")
        crit1 = "是" if v.get("crit_all_t_below_2") else "否"
        crit2 = "是" if v.get("crit_random_ge_50pct") else "否"
        crit3 = "是" if v.get("crit_pre_2020_only") else "否"
        lines.append(
            f"| {c['variant']} | {BAND_LABELS[c['band']]} | {c['horizon_months']} "
            f"| {_num(v.get('t_spy'), 1)} | {_num(v.get('t_iwm'), 1)} "
            f"| {_num(v.get('t_random'), 1)} | "
            f"{share_text} | "
            f"{_bp(v.get('pre_2020_excess_spy'))} / {_bp(v.get('from_2020_excess_spy'))} | "
            f"{crit1} | {crit2} | {crit3} | {v['verdict']} |"
        )
    lines.append("")

    # paper section
    lines.append("## 5. If this goes to paper tonight（如果今晚上模拟盘）")
    lines.append("")
    if paper is None:
        lines.append("（paper 阶段未运行）")
    else:
        chosen_key = None
        if cv["supported_cells"]:
            chosen_key = max(
                cv["supported_cells"], key=lambda k_: cells[k_]["verdict"]["t_random"] or -np.inf
            )
        chosen = cells.get(chosen_key) if chosen_key else None
        if chosen is None:
            fallback_key = cell_key("real", "full", MAIN_VARIANT, "all", 3)
            chosen = cells.get(fallback_key)
            chosen_key = fallback_key
            lines.append(
                f"**没有任何单元满足支持条件。** 下面按主单元 `{MAIN_VARIANT}` / 全部分段 / "
                "持有 3 个月给出规则，只是为了让模拟盘适配器有一个可核对的目标，"
                "不代表这个单元过了研究关（研究判定见第 0 节）。"
            )
        else:
            lines.append(
                f"选中单元：`{chosen_key}`（在 {len(cv['supported_cells'])} 个满足支持条件的单元里"
                "按对随机对照的 t 取最大——这是事后挑选，"
                f"本轮共评估 {cv['cells_evaluated_full_universe']} 个单元，预期要按族计数打折）。"
            )
        if chosen:
            variant, band, k = chosen["variant"], chosen["band"], chosen["horizon_months"]
            book = chosen["book"] or {}
            sel = paper["selections"].get(f"{variant}__{band}", {})
            lines.append("")
            lines.append("**选股规则（逐字）**：")
            lines.append(
                f"1. 股票池：`data/features/universe_broad` 在 as_of 日生效的月末 cohort"
                f"（{paper['cohort_month_end']}），"
                f"流动性段 {BAND_LABELS[band]}（按 cohort 的 `adv_rank`）。"
            )
            lines.append(
                f"2. 资格：`data/features/insider_broad` 在 as_of 日"
                f"（{paper['as_of_insider_date']}）的行满足 {VARIANTS[variant]}。"
            )
            lines.append(
                f"3. 上限 {MAX_NAMES} 只：超出时按 `net_buy_usd_60d` 从大到小取前 {MAX_NAMES}"
                "（同值按代码字母序）。"
            )
            lines.append(
                f"4. 等权；持有 {k} 个月，{k} 个月度分批各占 1/{k} 资金，每个月末只换到期的那一批"
                "（本月新形成的一批用到期批次的资金买入）；分批全空的月份放 BIL。"
            )
            lines.append(
                f"5. 成交：形成日次一交易日开盘（{EXECUTION}），"
                f"成本假设 {PRIMARY_COST_BPS:.0f} bp/边。"
            )
            lines.append("")
            lines.append(
                f"- 回测里的换手：月双边换手均值 {_num(book.get('turnover_per_month_mean'), 2)}"
                f"（年化 {_num(book.get('turnover_annualized'), 1)}）；"
                f"每月新形成批次 {book.get('tranche_size_mean', 0):.0f} 只"
                f"（最近一个形成月 {book.get('tranche_size_latest', 0)} 只）；"
                f"整本书平均 {book.get('positions_mean', 0):.0f} 个持仓。"
            )
            lines.append(
                f"- as_of {paper['as_of_insider_date']}："
                f"满足资格 {sel.get('eligible_names', 0)} 只，"
                f"封顶后持有 {sel.get('held_names_after_cap', 0)} 只，"
                f"每只权重 {_pct(sel.get('weight_each'), 2)}"
                f"（仅本月这一批；k={k} 时本批占总资金 1/{k}）。"
            )
            lines.append("")
            lines.append("按 `net_buy_usd_60d` 排序的前 20 只：")
            lines.append("")
            lines.append(
                "| # | 代码 | adv_rank | 60 日净买入(美元) | 买家数 | 买入笔数 | "
                "距最近买入(交易日) | 近 63 日收益 | 回补名 |"
            )
            lines.append("|---:|---|---:|---:|---:|---:|---:|---:|:-:|")
            for i, r in enumerate(sel.get("top20", []), start=1):
                backfilled_txt = "是" if r["is_backfilled"] else ""
                lines.append(
                    f"| {i} | {r['symbol']} | {r['adv_rank']} | {r['net_buy_usd_60d']:,.0f} | "
                    f"{_num(r['buyers_60d'], 0)} | {_num(r['open_market_buy_count_60d'], 0)} | "
                    f"{_num(r['days_since_last_visible_buy'], 0)} | {_pct(r['ret_63'])} | "
                    f"{backfilled_txt} |"
                )
            lines.append("")
            lines.append(
                f"完整持有名单（{sel.get('held_names_after_cap', 0)} 只）"
                f"见 `{PAPER_PATH.relative_to(ROOT)}` 的 "
                f"`selections['{variant}__{band}'].all_held_symbols`。"
            )
    lines.append("")
    lines.append("## 6. 文件")
    lines.append("")
    lines.append(
        f"- 汇总：`{SUMMARY_PATH.relative_to(ROOT)}`；本报告：`{REPORT_PATH.relative_to(ROOT)}`；"
        f"模拟盘候选：`{PAPER_PATH.relative_to(ROOT)}`"
    )
    lines.append(
        f"- 缓存（gitignore）：`{CACHE_DIR.relative_to(ROOT)}/`"
        "（形成帧、宽价格矩阵、每个单元的日收益与簿统计）"
    )
    lines.append(
        "- 脚本：`scripts/run_h20260917_01_insider_independent.py`"
        "（阶段 load / price / report / paper，全部可断点续跑）"
    )
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--stage", choices=["all", "load", "price", "report", "paper"], default="all"
    )
    parser.add_argument(
        "--features-suffix", default="_broad", help="'' for the narrow smoke-test tables"
    )
    parser.add_argument("--years", type=int, nargs="*", default=None)
    parser.add_argument("--variants", nargs="*", default=None, choices=list(VARIANTS))
    parser.add_argument("--bands", nargs="*", default=None, choices=list(BANDS))
    parser.add_argument("--horizons", type=int, nargs="*", default=None)
    parser.add_argument(
        "--universe-versions", nargs="*", default=None, choices=list(UNIVERSE_VERSIONS)
    )
    parser.add_argument(
        "--seeds", type=int, default=None, help="number of random-control seeds (default 5)"
    )
    parser.add_argument("--skip-placebo", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = bind_paths(args.features_suffix)
    _log(f"paths: feature family {tag!r} -> cache {CACHE_DIR}, report {REPORT_PATH.name}")
    if args.stage in ("all", "load"):
        stage_load(args)
    if args.stage in ("all", "price"):
        stage_price(args)
    paper = None
    if args.stage in ("all", "paper", "report"):
        paper = stage_paper(args)
    if args.stage in ("all", "report"):
        summary = stage_report(args)
        REPORT_PATH.write_text(render_markdown(summary, paper), encoding="utf-8")
        _log(f"report: wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
