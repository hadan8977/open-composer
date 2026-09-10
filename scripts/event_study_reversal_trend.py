"""Step 13-P scope addition A2: event study for the 4 reversal-trend signals.

docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md
section A2: "日线、全宇宙（PIT top-1500）、2018-2026 与 2024→ 分开：对四个信号各算：
事件数、事后 1/5/10/21 日超额收益（减当日宇宙中位数）的均值/中位数/胜率、按日期聚类
的 t 值；对照 = 同日随机等量非信号股票的 1,000 次抽样分布（占位）。判定：'有信息' =
5 日与 10 日超额均值 > 0 且 t > 2.5 且高于占位分布 95 分位。"

**Universe/PIT caveat**: "excess return" here is ``build_labels``'s
``label_excess_h`` -- forward h-day return minus that date's cross-sectional
median, computed over the historical *union* of ever-admitted universe
symbols (``universe_union_symbols``, same convention every other Step 13-F
build script already uses), not a freshly-reconstructed per-date PIT
top-1500 cohort. This is a documented approximation of the plan's "PIT
top-1500" phrase, not a literal implementation of it -- rebuilding a true
time-varying per-date universe join was judged out of scope for this
"placeholder" (plan's own word) control under today's deadline.

**Statistics, precisely**:

* ``mean``/``median``/``hit_rate`` (the ">0" check in the informative
  criterion uses ``mean``): raw event-level, i.e. over every individual
  (symbol, event date) observation, *not* date-averaged -- multiple same-day
  firings each count once.
* ``t`` (date-clustered): events are first averaged *within* each event
  date (so a date with many firings does not get pseudo-replicated weight),
  then ``t = mean(per_date_means) / (std(per_date_means, ddof=1) /
  sqrt(n_dates))``.
* Placebo comparison ("above the 95th percentile"): compares the *same*
  ``mean(per_date_means)`` quantity used for ``t`` against a distribution of
  1,000 Monte Carlo draws of that identical statistic computed from random
  (with replacement, same day, equal count -- "同日随机等量非信号股票") non-firing
  symbols -- not the raw event-level mean, so the comparison is apples-to-
  apples with what the t-test itself measures.

**Memory discipline**: processed one year at a time (this box's convention);
the placebo's running sum/count is accumulated *additively* across years
(each of the 1,000 draws' per-date means simply sum, and date counts simply
add, whether computed one year at a time or all at once), so peak memory
is bounded by a single year's merged panel (~500-650k rows), never the full
multi-year window at once. 2024-2026 is processed once and its contribution
credited to both the "2018_2026" and "2024_onward" windows, not recomputed.

Usage (foreground; this script does its own per-year chunking, so it is
lighter than the *_features.py build scripts and does not need a
--years-limited smoke-test mode)::

    uv run python scripts/event_study_reversal_trend.py

Usage (detached + capped, if memory is tight)::

    nohup ./scripts/run_capped.sh --mem 1.2G -- \
        uv run python scripts/event_study_reversal_trend.py \
        > /tmp/event_study_reversal_trend.log 2>&1 &
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.research.features.labels import build_labels  # noqa: E402
from open_composer.research.features.reversal_trend_daily import (  # noqa: E402
    REVERSAL_TREND_SIGNAL_COLUMNS,
)
from open_composer.research.features.universe import universe_union_symbols  # noqa: E402

DAILY_ROOT = ROOT / "data" / "sip" / "daily"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
REVERSAL_TREND_ROOT = ROOT / "data" / "features" / "reversal_trend"
OUT_PATH = ROOT / "reports" / "research" / "factor_screen" / "reversal_trend_event_study.md"

HORIZONS: tuple[int, ...] = (1, 5, 10, 21)
INFORMATIVE_HORIZONS: tuple[int, ...] = (5, 10)
T_THRESHOLD = 2.5
N_PLACEBO_DRAWS = 1000
RANDOM_SEED = 1337

#: (window name, start date inclusive, end date inclusive-or-None-for-open).
WINDOWS: tuple[tuple[str, pd.Timestamp, pd.Timestamp | None], ...] = (
    ("2018_2026", pd.Timestamp("2018-01-01"), pd.Timestamp("2026-12-31")),
    ("2024_onward", pd.Timestamp("2024-01-01"), None),
)


class _Bucket:
    """Accumulates one (window, signal, horizon) triple's statistics across
    however many per-year passes touch it."""

    def __init__(self) -> None:
        self.real_dates: list[pd.Timestamp] = []
        self.real_values: list[float] = []
        self.placebo_sum = np.zeros(N_PLACEBO_DRAWS, dtype=np.float64)
        self.placebo_n_dates = 0


def _available_archive_years() -> list[int]:
    return sorted(int(p.name) for p in DAILY_ROOT.iterdir() if p.is_dir() and p.name.isdigit())


def _load_year_merged(
    year: int, universe_symbols: list[str], archive_years: list[int]
) -> pd.DataFrame:
    """This year's reversal-trend signals joined to this year's forward-
    return labels. Labels need up to 21 trading days of *lookahead*, so the
    label build's glob spans [year, year+1] (clipped to the archive) and is
    filtered back down to ``year`` afterward -- the forward-looking mirror
    of every other build script's backward LOOKBACK_YEARS.
    """
    signal_path = REVERSAL_TREND_ROOT / f"{year}.parquet"
    signals = pd.read_parquet(
        signal_path, columns=["symbol", "trade_date", *REVERSAL_TREND_SIGNAL_COLUMNS]
    )

    label_years = [y for y in (year, year + 1) if y in archive_years]
    glob_paths = [str(DAILY_ROOT / str(y) / "*.parquet") for y in label_years]
    labels = build_labels(
        glob_paths,
        universe_symbols,
        horizons=HORIZONS,
        memory_limit="1.0GB",
        temp_directory=str(ROOT / "data" / "_duckdb_tmp"),
    )
    labels = labels.loc[labels["trade_date"].dt.year == year]

    return signals.merge(labels, on=["symbol", "trade_date"], how="inner")


def _process_date_group(
    date: pd.Timestamp,
    group: pd.DataFrame,
    rng: np.random.Generator,
    buckets: dict[tuple[str, str, int], _Bucket],
    window_names: list[str],
) -> None:
    for signal in REVERSAL_TREND_SIGNAL_COLUMNS:
        firing = group.loc[group[signal] > 0]
        if firing.empty:
            continue
        non_firing = group.loc[group[signal] <= 0]
        k_events = len(firing)

        for horizon in HORIZONS:
            excess_col = f"label_excess_{horizon}"
            firing_values = firing[excess_col].dropna().to_numpy()
            if len(firing_values) == 0:
                continue
            pool = non_firing[excess_col].dropna().to_numpy()

            placebo_draw_means: np.ndarray | None = None
            if len(pool) > 0:
                idx = rng.integers(0, len(pool), size=(N_PLACEBO_DRAWS, k_events))
                placebo_draw_means = pool[idx].mean(axis=1)

            for window_name in window_names:
                bucket = buckets[(window_name, signal, horizon)]
                bucket.real_dates.extend([date] * len(firing_values))
                bucket.real_values.extend(firing_values.tolist())
                if placebo_draw_means is not None:
                    bucket.placebo_sum += placebo_draw_means
                    bucket.placebo_n_dates += 1


def _windows_containing(year: int) -> list[str]:
    names = []
    for name, start, end in WINDOWS:
        if year < start.year:
            continue
        if end is not None and year > end.year:
            continue
        names.append(name)
    return names


def _summarize(bucket: _Bucket) -> dict[str, float | int]:
    n_events = len(bucket.real_values)
    if n_events == 0:
        return {
            "n_events": 0,
            "n_dates": 0,
            "mean": float("nan"),
            "median": float("nan"),
            "hit_rate": float("nan"),
            "t_stat": float("nan"),
            "placebo_p95": float("nan"),
            "date_clustered_mean": float("nan"),
        }
    values = np.array(bucket.real_values)
    per_date = (
        pd.Series(values, index=pd.Index(bucket.real_dates, name="trade_date"))
        .groupby("trade_date")
        .mean()
    )
    n_dates = len(per_date)
    date_clustered_mean = float(per_date.mean())
    if n_dates >= 2 and per_date.std(ddof=1) > 0:
        t_stat = float(per_date.mean() / (per_date.std(ddof=1) / np.sqrt(n_dates)))
    else:
        t_stat = float("nan")
    if bucket.placebo_n_dates > 0:
        placebo_distribution = bucket.placebo_sum / bucket.placebo_n_dates
        placebo_p95 = float(np.percentile(placebo_distribution, 95))
    else:
        placebo_p95 = float("nan")
    return {
        "n_events": n_events,
        "n_dates": n_dates,
        "mean": float(values.mean()),
        "median": float(np.median(values)),
        "hit_rate": float((values > 0).mean()),
        "t_stat": t_stat,
        "placebo_p95": placebo_p95,
        "date_clustered_mean": date_clustered_mean,
    }


def _is_informative(stats_by_horizon: dict[int, dict[str, float | int]]) -> bool:
    for horizon in INFORMATIVE_HORIZONS:
        stats = stats_by_horizon[horizon]
        if not (stats["mean"] > 0):
            return False
        if not (stats["t_stat"] > T_THRESHOLD):
            return False
        if not (stats["date_clustered_mean"] > stats["placebo_p95"]):
            return False
    return True


def _render_report(all_stats: dict[str, dict[str, dict[int, dict]]]) -> str:
    lines = [
        "# Reversal Trend event study",
        "",
        "docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md section A2.",
        "",
        "Universe: historical union of ever-admitted universe symbols (see this"
        " script's module docstring for the PIT-top-1500 approximation caveat)."
        f" Placebo: {N_PLACEBO_DRAWS} Monte Carlo draws, same-day equal-count"
        " random non-firing symbols, with replacement, seed"
        f" {RANDOM_SEED}. Informative = for both the 5-day and 10-day horizons:"
        f" mean > 0 AND date-clustered t > {T_THRESHOLD} AND date-clustered mean"
        " above the placebo distribution's 95th percentile.",
        "",
    ]
    for window_name, _, _ in WINDOWS:
        lines.append(f"## Window: {window_name}")
        lines.append("")
        for signal in REVERSAL_TREND_SIGNAL_COLUMNS:
            stats_by_horizon = all_stats[window_name][signal]
            informative = _is_informative(stats_by_horizon)
            lines.append(f"### {signal} -- informative: {'YES' if informative else 'no'}")
            lines.append("")
            lines.append(
                "| horizon | n_events | n_dates | mean | median | hit_rate |"
                " date_clustered_mean | t_stat | placebo_p95 |"
            )
            lines.append("|---|---|---|---|---|---|---|---|---|")
            for horizon in HORIZONS:
                s = stats_by_horizon[horizon]
                lines.append(
                    f"| {horizon}d | {s['n_events']} | {s['n_dates']} |"
                    f" {s['mean']:.5f} | {s['median']:.5f} | {s['hit_rate']:.3f} |"
                    f" {s['date_clustered_mean']:.5f} | {s['t_stat']:.2f} |"
                    f" {s['placebo_p95']:.5f} |"
                )
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    archive_years = _available_archive_years()
    universe_symbols = sorted(universe_union_symbols(UNIVERSE_ROOT))
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] universe union: {len(universe_symbols)}",
        flush=True,
    )

    target_years = [y for y in archive_years if y >= 2018]
    rng = np.random.default_rng(RANDOM_SEED)
    buckets: dict[tuple[str, str, int], _Bucket] = {
        (window_name, signal, horizon): _Bucket()
        for window_name, _, _ in WINDOWS
        for signal in REVERSAL_TREND_SIGNAL_COLUMNS
        for horizon in HORIZONS
    }

    for year in target_years:
        window_names = _windows_containing(year)
        if not window_names:
            continue
        started = time.monotonic()
        merged = _load_year_merged(year, universe_symbols, archive_years)
        for date, group in merged.groupby("trade_date", sort=False):
            _process_date_group(date, group, rng, buckets, window_names)
        del merged
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: done ({window_names}),"
            f" {time.monotonic() - started:.0f}s",
            flush=True,
        )

    all_stats: dict[str, dict[str, dict[int, dict]]] = {}
    for window_name, _, _ in WINDOWS:
        all_stats[window_name] = {}
        for signal in REVERSAL_TREND_SIGNAL_COLUMNS:
            all_stats[window_name][signal] = {
                horizon: _summarize(buckets[(window_name, signal, horizon)]) for horizon in HORIZONS
            }

    report = _render_report(all_stats)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] wrote {OUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
