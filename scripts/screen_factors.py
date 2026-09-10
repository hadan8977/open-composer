"""Step 13-F 3.5: preregistered factor screen.

docs/plan-step-13f-open-factor-library-import-and-screening-2026-09-09.zh.md
section 3.5. **This docstring is the preregistration** ("先写进本节再跑，不许
事后改" -- written before running, not edited after to fit the results):

* Sample: Friday rebalance-day rows (``loop.weekly_rebalance_dates``),
  universe = that month's PIT top-1500 (``loop.universe_as_of_calendar_month``,
  ``top_n=1500``). Labels: ``label_excess_5``, ``label_excess_10`` (from the
  already-built ``data/features/labels/``, not recomputed here).
* Per factor x per label: daily cross-sectional Spearman rank IC series ->
  full-sample (2018-2026) and recent (2024-01-02 onward) windows'
  ``ic_mean, ic_std, icir=mean/std, t=icir*sqrt(n)``; per-year IC mean and
  **sign stability** (fraction of years whose own mean IC shares the
  full-sample mean's sign); the factor's own cross-sectional rank's
  week-over-week autocorrelation (a turnover proxy, not to be confused with
  the IC itself); missing rate.
* Multiple testing: Benjamini-Hochberg q=0.05 FDR on the full-sample
  t-stats, p-values from a two-sided Student-t survival function (df =
  n_weeks-1). Factors "informative recently but not full-sample" (does not
  pass full-sample FDR, but is picked by the recent-ICIR ranking below) get
  their own disclosure table -- excluded from the FDR-passing count, but
  still eligible as ``screened_top40_recent`` candidates.
* Output: the recent-ICIR-ranked top 40 (within a near-duplicate family,
  rank correlation > 0.9 counts as duplicate, keep the higher |icir_recent|)
  to ``config/feature_sets/screened_top40_recent.json`` (each factor's IC
  numbers and source library included), plus the full table as markdown.
* Memory: one library's one year at a time; never concatenate all factor
  columns into a single wide table.

**Disclosed deviation from the plan's own count estimate**: the plan's
"~520 factors x 2 labels ~= 1,040 tests" assumed the full Alpha101 (101)
and Alpha191 (191) libraries. Sections 3.0/3.2 found ``py-alpha-lib``
unusable on this box (Python/AVX2 mismatches) and hand-ported only 20 ids
from each instead. The real count this script tests is 154 (alpha158) + 20
(alpha101) + 20 (alpha191) + 25 (osap_price) + 21 (reversal_trend,
continuous columns only) = 240 factors x 2 labels = 480 tests. FDR is run
on however many tests actually execute, not the plan's original estimate --
using the real count is the statistically correct choice regardless of
which number was originally guessed.

**Rank-correlation dedup, a documented memory-driven approximation**: the
plan's "秩相关 > 0.9" dedup check is computed over each recent-window
candidate factor's cross-sectional rank on only the most recent
``DEDUP_SAMPLE_WEEKS`` rebalance dates (default 8, ~2 months), not the
factors' full multi-year value history -- correlating ~100 candidates'
full recent-window (date x symbol) panels pairwise would need a wide
in-memory matrix this box's 1.2-1.8GB cap cannot comfortably hold. Formula-
level near-duplicates (e.g. two K-bar ratio variants) show high correlation
on any reasonably sized sample of dates, so this is judged an acceptable
approximation, not silently skipped.

**Per-(year, library) checkpointing (2026-09-10 follow-up)**: the first
real run against the full archive died silently after "2023
reversal_trend" with no traceback -- the kernel memcg killed it at the
1.8G cap while starting 2024 alpha158, and because nothing was
checkpointed, the whole run's progress (2018-2023 x all 5 libraries) was
lost. Every (year, library) cell now writes its just-computed IC/
autocorrelation/missing-rate contribution to
``reports/research/factor_screen/_checkpoints/{year}_{library}.parquet``
(``_serialize_checkpoint``/``_write_checkpoint``, atomic via a same-dir
temp file + rename) immediately after computing it; a rerun that finds
that file already on disk loads it straight into the accumulators instead
of recomputing (``_load_checkpoint_into_accumulators``,
``_run_year_library``), so a mid-run OOM kill now costs at most one
(year, library) cell's work, not the whole run's. Checkpoint contents
round-trip exactly -- resuming produces the same accumulator state as an
uninterrupted run would have, not an approximation. Checkpoints are
gitignored scratch state (see ``.gitignore``), not a committed artifact.

**Column-chunked processing, a second 2026-09-10 memory fix**: the killed
run's peak (1.71GB, against alpha158's 154 float64 columns -- see
``data/features/alpha158/{year}.parquet``, ~650MB on disk and ~850MB as an
in-memory float64 frame for 2024 alone) came from loading and merging
every factor column for a whole library-year at once before the
rank-autocorrelation loop touched any of them. ``_process_library_year``
now processes ``columns`` in ``FACTOR_CHUNK_SIZE``-wide slices (default
40, ~26% of alpha158's 154): each chunk's ``_load_library_year`` call
reads only that chunk's columns, downcasts any float64 factor column to
float32 immediately after the weekly-date filter (a change to
``_load_library_year`` itself, so the dedup step's
``_load_recent_sample_panel`` -- which shares the same loader -- benefits
too), and the chunk's frames are ``del``-eted and ``gc.collect()``-ed
before the next chunk starts. The per-year rank-autocorrelation pivot
additionally reuses the dedup step's existing "sample the last N
rebalance dates" design (``AUTOCORR_SAMPLE_WEEKS``, default 8, mirroring
``DEDUP_SAMPLE_WEEKS``) instead of pivoting every weekly date in the year
-- accumulated across 9 years this still yields roughly 9 x 7 = 63
week-over-week pairs per factor, judged sufficient for a turnover proxy
that was never meant to be exact. This changes nothing about
``ic_accumulators``/``missing_accumulators`` (chunking a sum is still the
same sum); it does reduce how many week-pairs feed
``autocorr_accumulators`` -- a disclosed, deliberate trade-off, not a
silent one.

Usage (foreground; already per-year/per-library/per-column-chunk chunked
internally, and resumable via checkpoints)::

    uv run python scripts/screen_factors.py

Usage (detached + capped, if memory is tight)::

    nohup ./scripts/run_capped.sh --mem 1.2G -- \
        uv run python scripts/screen_factors.py \
        > /tmp/screen_factors.log 2>&1 &
"""

from __future__ import annotations

import gc
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats as scipy_stats  # noqa: E402

from open_composer.research.features.feature_sets import resolve_feature_set  # noqa: E402
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    universe_as_of_calendar_month,
    weekly_rebalance_dates,
)

FEATURES_ROOT = ROOT / "data" / "features"
LABELS_ROOT = FEATURES_ROOT / "labels"
UNIVERSE_ROOT = FEATURES_ROOT / "universe"
OUT_PARQUET = ROOT / "reports" / "research" / "factor_screen" / "step13f_screen.parquet"
OUT_MD = ROOT / "reports" / "research" / "factor_screen" / "step13f_screen.md"
OUT_JSON = ROOT / "config" / "feature_sets" / "screened_top40_recent.json"
CHECKPOINTS_ROOT = ROOT / "reports" / "research" / "factor_screen" / "_checkpoints"

LIBRARIES: tuple[str, ...] = ("alpha158", "alpha101", "alpha191", "osap_price", "reversal_trend")
LABEL_COLUMNS: tuple[str, ...] = ("label_excess_5", "label_excess_10")
ALL_YEARS: list[int] = list(range(2018, 2027))
RECENT_START = pd.Timestamp("2024-01-02")
UNIVERSE_TOP_N = 1500
MIN_CROSS_SECTION = 10  # minimum non-null names for one date's IC/rank-corr to count
FDR_Q = 0.05
TOP_N = 40
DEDUP_RANK_CORR_THRESHOLD = 0.9
DEDUP_CANDIDATE_POOL = 150  # headroom above TOP_N before dedup removes near-duplicates
DEDUP_SAMPLE_WEEKS = 8  # see module docstring's "documented approximation"
FACTOR_CHUNK_SIZE = 40  # 2026-09-10 memory fix -- see module docstring
AUTOCORR_SAMPLE_WEEKS = 8  # same design as DEDUP_SAMPLE_WEEKS, see module docstring


@dataclass
class _FactorAccumulator:
    """One (library, factor, label) triple's per-date IC observations,
    accumulated across however many years touch it."""

    dates: list[pd.Timestamp] = field(default_factory=list)
    ic_values: list[float] = field(default_factory=list)


@dataclass
class _RankAutocorrAccumulator:
    """One (library, factor)'s week-over-week rank-autocorrelation
    observations, accumulated across years."""

    corr_sum: float = 0.0
    n_pairs: int = 0


@dataclass
class _MissingAccumulator:
    total: int = 0
    missing: int = 0


def _year_calendar(library_root: Path, year: int) -> list[pd.Timestamp]:
    path = library_root / f"{year}.parquet"
    if not path.exists():
        return []
    dates = pd.read_parquet(path, columns=["trade_date"])["trade_date"]
    return sorted(pd.to_datetime(dates.unique()))


def _load_library_year(
    library_root: Path, year: int, columns: list[str], dates: list[pd.Timestamp]
) -> pd.DataFrame:
    """Read one library-year's ``columns`` (plus keys), filtered to
    ``dates``. Downcasts any float64 factor column to float32 immediately
    after filtering -- most of these tables are stored float64 on disk
    despite the build plan's float32 intent (a Step 13-F 3.1/3.2 gap, not
    fixed here), and halving the retained column width matters for both
    callers of this function: the main per-chunk screen in
    ``_process_library_year`` and the dedup step's
    ``_load_recent_sample_panel``.
    """
    path = library_root / f"{year}.parquet"
    frame = pd.read_parquet(path, columns=["symbol", "trade_date", *columns])
    frame = frame.loc[frame["trade_date"].isin(dates)]
    float64_columns = [c for c in columns if frame[c].dtype == np.float64]
    if float64_columns:
        frame = frame.astype({c: "float32" for c in float64_columns})
    return frame


def _load_labels_year(year: int, dates: list[pd.Timestamp]) -> pd.DataFrame:
    path = LABELS_ROOT / f"{year}.parquet"
    frame = pd.read_parquet(path, columns=["symbol", "trade_date", *LABEL_COLUMNS])
    return frame.loc[frame["trade_date"].isin(dates)]


def _universe_membership_frame(
    universe_panel: pd.DataFrame, dates: list[pd.Timestamp], top_n: int
) -> pd.DataFrame:
    rows = []
    for date in dates:
        for symbol in universe_as_of_calendar_month(universe_panel, date, top_n=top_n):
            rows.append((date, symbol))
    return pd.DataFrame(rows, columns=["trade_date", "symbol"])


def _chunked(items: list[str], size: int) -> list[list[str]]:
    """Split ``items`` into consecutive slices of at most ``size``."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def _process_library_year(
    library: str,
    year: int,
    columns: list[str],
    universe_panel: pd.DataFrame,
    ic_accumulators: dict[tuple[str, str, str], _FactorAccumulator],
    autocorr_accumulators: dict[tuple[str, str], _RankAutocorrAccumulator],
    missing_accumulators: dict[tuple[str, str], _MissingAccumulator],
) -> None:
    library_root = FEATURES_ROOT / library
    calendar = _year_calendar(library_root, year)
    dates = weekly_rebalance_dates(calendar)
    if not dates:
        return
    # 2026-09-10 memory fix (see module docstring): the autocorrelation
    # pivot only needs a turnover proxy, not every week in the year -- reuse
    # the dedup step's "sample the last N rebalance dates" design instead of
    # pivoting all of `dates`.
    autocorr_dates = dates[-AUTOCORR_SAMPLE_WEEKS:]

    label_frame = _load_labels_year(year, dates)
    membership = _universe_membership_frame(universe_panel, dates, UNIVERSE_TOP_N)

    # 2026-09-10 memory fix (see module docstring): process at most
    # FACTOR_CHUNK_SIZE factor columns at a time end-to-end (load, merge, IC
    # accumulation, autocorrelation) instead of holding the whole library's
    # columns in memory for the whole year -- this is what actually shrinks
    # the peak, since these tables are ~650-850MB/year loaded whole.
    for chunk in _chunked(columns, FACTOR_CHUNK_SIZE):
        factor_frame = _load_library_year(library_root, year, chunk, dates)
        merged = factor_frame.merge(label_frame, on=["symbol", "trade_date"], how="inner")
        merged = merged.merge(membership, on=["symbol", "trade_date"], how="inner")
        del factor_frame
        if merged.empty:
            del merged
            continue

        for factor in chunk:
            missing = missing_accumulators[(library, factor)]
            missing.total += len(merged)
            missing.missing += int(merged[factor].isna().sum())

        for date, group in merged.groupby("trade_date", sort=False):
            for factor in chunk:
                factor_values = group[factor]
                if factor_values.notna().sum() < MIN_CROSS_SECTION:
                    continue
                for label in LABEL_COLUMNS:
                    label_values = group[label]
                    valid = factor_values.notna() & label_values.notna()
                    if valid.sum() < MIN_CROSS_SECTION:
                        continue
                    ic = factor_values.loc[valid].corr(label_values.loc[valid], method="spearman")
                    if pd.notna(ic):
                        bucket = ic_accumulators[(library, factor, label)]
                        bucket.dates.append(date)
                        bucket.ic_values.append(float(ic))

        autocorr_slice = merged.loc[merged["trade_date"].isin(autocorr_dates)]
        for factor in chunk:
            try:
                wide = autocorr_slice.pivot(index="trade_date", columns="symbol", values=factor)
            except ValueError:
                continue  # duplicate (trade_date, symbol) rows -- shouldn't happen, skip it
            wide = wide.astype("float32")
            ranked = wide.rank(axis=1, pct=True).astype("float32")
            if len(ranked) < 2:
                continue
            prev = ranked.iloc[:-1].reset_index(drop=True)
            nxt = ranked.iloc[1:].reset_index(drop=True)
            weekly_corr = prev.corrwith(nxt, axis=1)
            weekly_corr = weekly_corr.dropna()
            if weekly_corr.empty:
                continue
            acc = autocorr_accumulators[(library, factor)]
            acc.corr_sum += float(weekly_corr.sum())
            acc.n_pairs += int(len(weekly_corr))

        del merged, autocorr_slice
        gc.collect()


def _serialize_checkpoint(
    ic_accumulators: dict[tuple[str, str, str], _FactorAccumulator],
    autocorr_accumulators: dict[tuple[str, str], _RankAutocorrAccumulator],
    missing_accumulators: dict[tuple[str, str], _MissingAccumulator],
) -> pd.DataFrame:
    """Flatten one (year, library) cell's freshly accumulated contribution
    (the caller passes fresh, call-scoped accumulator dicts holding only
    that cell's data -- see ``_run_year_library``) into a single long/tidy
    frame that round-trips through parquet. ``record_type`` distinguishes
    the three row shapes sharing this one file; only the columns relevant
    to that shape are non-null on any given row.
    """
    rows: list[dict] = []
    for (_library, factor, label), bucket in ic_accumulators.items():
        for date, ic in zip(bucket.dates, bucket.ic_values, strict=True):
            rows.append(
                {
                    "record_type": "ic",
                    "factor": factor,
                    "label": label,
                    "trade_date": date,
                    "ic": ic,
                    "corr_sum": None,
                    "n_pairs": None,
                    "total": None,
                    "missing": None,
                }
            )
    for (_library, factor), acc in autocorr_accumulators.items():
        rows.append(
            {
                "record_type": "autocorr",
                "factor": factor,
                "label": None,
                "trade_date": None,
                "ic": None,
                "corr_sum": acc.corr_sum,
                "n_pairs": acc.n_pairs,
                "total": None,
                "missing": None,
            }
        )
    for (_library, factor), acc in missing_accumulators.items():
        rows.append(
            {
                "record_type": "missing",
                "factor": factor,
                "label": None,
                "trade_date": None,
                "ic": None,
                "corr_sum": None,
                "n_pairs": None,
                "total": acc.total,
                "missing": acc.missing,
            }
        )
    columns = [
        "record_type",
        "factor",
        "label",
        "trade_date",
        "ic",
        "corr_sum",
        "n_pairs",
        "total",
        "missing",
    ]
    return pd.DataFrame(rows, columns=columns)


def _write_checkpoint(path: Path, frame: pd.DataFrame) -> None:
    """Write atomically (same-directory temp file + rename) so a process
    killed mid-write never leaves a truncated checkpoint that a later
    resume would silently load as complete-but-wrong."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    frame.to_parquet(tmp_path, index=False)
    tmp_path.replace(path)


def _load_checkpoint_into_accumulators(
    path: Path,
    library: str,
    ic_accumulators: dict[tuple[str, str, str], _FactorAccumulator],
    autocorr_accumulators: dict[tuple[str, str], _RankAutocorrAccumulator],
    missing_accumulators: dict[tuple[str, str], _MissingAccumulator],
) -> None:
    """Inverse of ``_serialize_checkpoint``: merge one (year, library)
    checkpoint's rows into the (possibly already partly populated) shared
    accumulator dicts, exactly as if ``_process_library_year`` had just
    computed them."""
    frame = pd.read_parquet(path)

    ic_rows = frame.loc[frame["record_type"] == "ic"]
    for (factor, label), group in ic_rows.groupby(["factor", "label"], sort=False):
        bucket = ic_accumulators[(library, factor, label)]
        bucket.dates.extend(pd.to_datetime(group["trade_date"]).tolist())
        bucket.ic_values.extend(float(v) for v in group["ic"])

    autocorr_rows = frame.loc[frame["record_type"] == "autocorr"]
    for _, row in autocorr_rows.iterrows():
        acc = autocorr_accumulators[(library, row["factor"])]
        acc.corr_sum += float(row["corr_sum"])
        acc.n_pairs += int(row["n_pairs"])

    missing_rows = frame.loc[frame["record_type"] == "missing"]
    for _, row in missing_rows.iterrows():
        acc = missing_accumulators[(library, row["factor"])]
        acc.total += int(row["total"])
        acc.missing += int(row["missing"])


def _run_year_library(
    library: str,
    year: int,
    columns: list[str],
    universe_panel: pd.DataFrame,
    ic_accumulators: dict[tuple[str, str, str], _FactorAccumulator],
    autocorr_accumulators: dict[tuple[str, str], _RankAutocorrAccumulator],
    missing_accumulators: dict[tuple[str, str], _MissingAccumulator],
    checkpoints_root: Path = CHECKPOINTS_ROOT,
) -> str:
    """Process one (year, library) cell, resuming from a checkpoint if a
    prior run already finished it. Always leaves the three shared
    accumulator dicts holding this cell's contribution merged in -- callers
    do not need to branch on the return value, which is purely for
    logging/tests. Returns ``"skipped"`` when a checkpoint was loaded
    instead of recomputed, ``"computed"`` otherwise.
    """
    checkpoint_path = checkpoints_root / f"{year}_{library}.parquet"
    if checkpoint_path.exists():
        _load_checkpoint_into_accumulators(
            checkpoint_path,
            library,
            ic_accumulators,
            autocorr_accumulators,
            missing_accumulators,
        )
        return "skipped"

    year_ic: dict[tuple[str, str, str], _FactorAccumulator] = defaultdict(_FactorAccumulator)
    year_autocorr: dict[tuple[str, str], _RankAutocorrAccumulator] = defaultdict(
        _RankAutocorrAccumulator
    )
    year_missing: dict[tuple[str, str], _MissingAccumulator] = defaultdict(_MissingAccumulator)
    _process_library_year(
        library, year, columns, universe_panel, year_ic, year_autocorr, year_missing
    )

    for key, bucket in year_ic.items():
        target = ic_accumulators[key]
        target.dates.extend(bucket.dates)
        target.ic_values.extend(bucket.ic_values)
    for key, acc in year_autocorr.items():
        target_acc = autocorr_accumulators[key]
        target_acc.corr_sum += acc.corr_sum
        target_acc.n_pairs += acc.n_pairs
    for key, acc in year_missing.items():
        target_missing = missing_accumulators[key]
        target_missing.total += acc.total
        target_missing.missing += acc.missing

    checkpoint_frame = _serialize_checkpoint(year_ic, year_autocorr, year_missing)
    _write_checkpoint(checkpoint_path, checkpoint_frame)
    del year_ic, year_autocorr, year_missing, checkpoint_frame
    gc.collect()
    return "computed"


def _window_stats(
    dates: list[pd.Timestamp], values: list[float], start: pd.Timestamp | None
) -> dict:
    series = pd.Series(values, index=pd.DatetimeIndex(dates))
    if start is not None:
        series = series.loc[series.index >= start]
    n = len(series)
    if n < 2:
        return {
            "ic_mean": float("nan"),
            "ic_std": float("nan"),
            "icir": float("nan"),
            "t": float("nan"),
            "n": n,
        }
    ic_mean = float(series.mean())
    ic_std = float(series.std(ddof=1))
    icir = ic_mean / ic_std if ic_std > 0 else float("nan")
    t = icir * np.sqrt(n) if pd.notna(icir) else float("nan")
    return {"ic_mean": ic_mean, "ic_std": ic_std, "icir": icir, "t": t, "n": n}


def _sign_stability(
    dates: list[pd.Timestamp], values: list[float], full_sample_sign: float
) -> float:
    series = pd.Series(values, index=pd.DatetimeIndex(dates))
    per_year_mean = series.groupby(series.index.year).mean()
    if per_year_mean.empty or full_sample_sign == 0:
        return float("nan")
    same_sign = np.sign(per_year_mean) == np.sign(full_sample_sign)
    return float(same_sign.mean())


def _benjamini_hochberg(p_values: np.ndarray, q: float) -> np.ndarray:
    """Standard BH step-up procedure. Returns a boolean pass/fail array
    aligned with ``p_values``'s original order. NaN p-values never pass."""
    n = len(p_values)
    passing = np.zeros(n, dtype=bool)
    valid = ~np.isnan(p_values)
    if not valid.any():
        return passing
    valid_idx = np.flatnonzero(valid)
    valid_p = p_values[valid_idx]
    order = np.argsort(valid_p)
    ranked = valid_p[order]
    m = len(ranked)
    thresholds = (np.arange(1, m + 1) / m) * q
    below = ranked <= thresholds
    if not below.any():
        return passing
    max_i = int(np.max(np.where(below)[0]))
    passing[valid_idx[order[: max_i + 1]]] = True
    return passing


def _dedupe_by_rank_correlation(
    candidates: pd.DataFrame, value_lookup: dict[tuple[str, str], pd.DataFrame], threshold: float
) -> pd.DataFrame:
    """``candidates`` sorted best-first (highest |icir_recent|). Drops any
    later candidate whose recent-window rank correlation with an
    already-kept candidate exceeds ``threshold`` (see module docstring for
    the ``value_lookup`` sampling approximation). ``value_lookup`` maps
    (library, factor) -> a ``trade_date``-indexed, symbol-columned frame of
    that factor's raw values on the sampled recent dates.
    """
    kept_rows: list[pd.Series] = []
    kept_ranked: list[pd.DataFrame] = []
    for _, row in candidates.iterrows():
        key = (row["library"], row["factor"])
        panel = value_lookup.get(key)
        is_duplicate = False
        if panel is not None and not panel.empty:
            ranked = panel.rank(axis=1, pct=True)
            for other_ranked in kept_ranked:
                common_dates = ranked.index.intersection(other_ranked.index)
                if len(common_dates) == 0:
                    continue
                corr = ranked.loc[common_dates].corrwith(other_ranked.loc[common_dates], axis=1)
                corr = corr.dropna()
                if not corr.empty and abs(corr.mean()) > threshold:
                    is_duplicate = True
                    break
            if not is_duplicate:
                kept_ranked.append(ranked)
        if not is_duplicate:
            kept_rows.append(row)
        if len(kept_rows) >= TOP_N:
            break
    return pd.DataFrame(kept_rows)


def _load_recent_sample_panel(library: str, factor: str, weeks: int) -> pd.DataFrame:
    """Last ``weeks`` rebalance dates' raw (not ranked) values for one
    factor, trade_date-indexed / symbol-columned -- used only by the dedup
    sampling approximation, not the IC computation."""
    library_root = FEATURES_ROOT / library
    recent_years = [year for year in (2025, 2026) if (library_root / f"{year}.parquet").exists()]
    frames = []
    for year in recent_years:
        calendar = _year_calendar(library_root, year)
        dates = weekly_rebalance_dates(calendar)
        frame = _load_library_year(library_root, year, [factor], dates)
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    last_dates = sorted(combined["trade_date"].unique())[-weeks:]
    combined = combined.loc[combined["trade_date"].isin(last_dates)]
    return combined.pivot(index="trade_date", columns="symbol", values=factor)


def main() -> int:
    started_all = time.monotonic()
    universe_panel = load_universe_panel(UNIVERSE_ROOT)
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] universe panel: {len(universe_panel)} rows",
        flush=True,
    )

    library_columns: dict[str, list[str]] = {}
    for library in LIBRARIES:
        columns, _ = resolve_feature_set(library)
        library_columns[library] = columns
        print(f"  {library}: {len(columns)} columns", flush=True)

    ic_accumulators: dict[tuple[str, str, str], _FactorAccumulator] = defaultdict(
        _FactorAccumulator
    )
    autocorr_accumulators: dict[tuple[str, str], _RankAutocorrAccumulator] = defaultdict(
        _RankAutocorrAccumulator
    )
    missing_accumulators: dict[tuple[str, str], _MissingAccumulator] = defaultdict(
        _MissingAccumulator
    )

    CHECKPOINTS_ROOT.mkdir(parents=True, exist_ok=True)
    for year in ALL_YEARS:
        for library in LIBRARIES:
            started = time.monotonic()
            status = _run_year_library(
                library,
                year,
                library_columns[library],
                universe_panel,
                ic_accumulators,
                autocorr_accumulators,
                missing_accumulators,
            )
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year} {library}: "
                f"{status} ({time.monotonic() - started:.0f}s)",
                flush=True,
            )

    rows: list[dict] = []
    for (library, factor, label), bucket in ic_accumulators.items():
        full = _window_stats(bucket.dates, bucket.ic_values, start=None)
        recent = _window_stats(bucket.dates, bucket.ic_values, start=RECENT_START)
        sign_stability = _sign_stability(bucket.dates, bucket.ic_values, full["ic_mean"])
        autocorr = autocorr_accumulators.get((library, factor))
        rank_autocorr = (
            autocorr.corr_sum / autocorr.n_pairs
            if autocorr and autocorr.n_pairs > 0
            else float("nan")
        )
        missing = missing_accumulators.get((library, factor))
        missing_rate = (
            missing.missing / missing.total if missing and missing.total > 0 else float("nan")
        )
        rows.append(
            {
                "library": library,
                "factor": factor,
                "label": label,
                "ic_mean_full": full["ic_mean"],
                "ic_std_full": full["ic_std"],
                "icir_full": full["icir"],
                "t_full": full["t"],
                "n_full": full["n"],
                "ic_mean_recent": recent["ic_mean"],
                "ic_std_recent": recent["ic_std"],
                "icir_recent": recent["icir"],
                "t_recent": recent["t"],
                "n_recent": recent["n"],
                "sign_stability": sign_stability,
                "rank_autocorr_weekly": rank_autocorr,
                "missing_rate": missing_rate,
            }
        )
    screen = pd.DataFrame(rows)

    p_values = 2.0 * scipy_stats.t.sf(
        np.abs(screen["t_full"].to_numpy()), df=np.maximum(screen["n_full"].to_numpy() - 1, 1)
    )
    p_values = np.where(screen["n_full"].to_numpy() >= 2, p_values, np.nan)
    screen["p_value_full"] = p_values
    screen["fdr_pass"] = _benjamini_hochberg(p_values, FDR_Q)
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {int(screen['fdr_pass'].sum())}/{len(screen)} "
        f"tests pass BH q={FDR_Q}",
        flush=True,
    )

    ranked = screen.assign(_abs_icir_recent=screen["icir_recent"].abs())
    ranked = ranked.sort_values("_abs_icir_recent", ascending=False, na_position="last")
    candidate_pool = ranked.head(DEDUP_CANDIDATE_POOL)

    value_lookup: dict[tuple[str, str], pd.DataFrame] = {}
    for (library, factor), _ in candidate_pool.groupby(["library", "factor"], sort=False):
        value_lookup[(library, factor)] = _load_recent_sample_panel(
            library, factor, DEDUP_SAMPLE_WEEKS
        )

    top40 = _dedupe_by_rank_correlation(candidate_pool, value_lookup, DEDUP_RANK_CORR_THRESHOLD)
    top40 = top40.assign(is_regime_factor=~top40["fdr_pass"])

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    screen.to_parquet(OUT_PARQUET, index=False)

    payload = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "protocol": (
            "docs/plan-step-13f-open-factor-library-import-and-screening-2026-09-09.zh.md#3.5"
        ),
        "n_tests": len(screen),
        "n_fdr_pass": int(screen["fdr_pass"].sum()),
        "factors": [
            {
                "factor": row["factor"],
                "source_root": row["library"],
                "label": row["label"],
                "icir_recent": row["icir_recent"],
                "icir_full": row["icir_full"],
                "t_recent": row["t_recent"],
                "t_full": row["t_full"],
                "sign_stability": row["sign_stability"],
                "fdr_pass": bool(row["fdr_pass"]),
                "is_regime_factor": bool(row["is_regime_factor"]),
            }
            for _, row in top40.iterrows()
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report_lines = [
        "# Step 13-F factor screen",
        "",
        f"{len(screen)} tests ({screen['library'].nunique()} libraries x"
        f" {screen['factor'].nunique()} factors x {len(LABEL_COLUMNS)} labels),"
        f" {int(screen['fdr_pass'].sum())} pass BH q={FDR_Q} on full-sample t.",
        "",
        f"## Top {len(top40)} by recent |ICIR| (deduped at rank correlation >"
        f" {DEDUP_RANK_CORR_THRESHOLD})",
        "",
        "| factor | library | label | icir_recent | t_recent | icir_full | t_full |"
        " sign_stability | fdr_pass | regime_factor |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, row in top40.iterrows():
        report_lines.append(
            f"| {row['factor']} | {row['library']} | {row['label']} |"
            f" {row['icir_recent']:.3f} | {row['t_recent']:.2f} |"
            f" {row['icir_full']:.3f} | {row['t_full']:.2f} |"
            f" {row['sign_stability']:.2f} | {row['fdr_pass']} | {row['is_regime_factor']} |"
        )
    report_lines.append("")
    OUT_MD.write_text("\n".join(report_lines), encoding="utf-8")

    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] wrote {OUT_PARQUET}, {OUT_MD}, {OUT_JSON}"
        f" ({time.monotonic() - started_all:.0f}s total)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
