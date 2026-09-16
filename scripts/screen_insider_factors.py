"""H-20260916-01 step 1: preregistered factor screen for the Form 4 insider columns.

Card: ``reports/research/hypotheses/H-20260916-01-insider-form4-confirmation-gate.md``
(step 1: "特征进现有筛选器（IC / ICIR / FDR / 符号稳定性），与价量因子同协议").
**This docstring is the preregistration** -- written before the run, not
edited afterwards to fit the numbers.

Why a separate script instead of adding ``"insider"`` to
``scripts/screen_factors.py``'s ``LIBRARIES``: that script's own module
docstring *is* the Step 13-F 3.5 preregistration and it fixes the multiple-
testing count at "253 factors x 2 labels = 506 tests". Adding 13 insider
columns to the same run would silently rewrite an already-executed
preregistration's FDR denominator. The insider columns are a different data
layer and a different hypothesis family (``insider_form4_gate``), so they get
their own preregistration and their own BH denominator -- which is exactly
what ``step0-collector-report.md`` section 9 handed over.

Protocol (identical in shape to Step 13-F 3.5, three deliberate differences
listed after it):

* Sample: weekly rebalance rows (``loop.weekly_rebalance_dates`` over each
  year's real trading calendar, taken from ``data/features/labels/``), universe
  = that month's point-in-time top-500 by ADV rank
  (``loop.universe_as_of_calendar_month``, ``top_n=500``).
* Factors: the 13 non-key columns of ``data/features/insider/{year}.parquet``
  (``features.insider.INSIDER_COLUMNS`` -- the single source of that list).
* Labels: ``label_rank_5`` (the repo's ML target: within-date percentile of
  the 5-session forward excess), ``label_excess_5`` and ``label_excess_21``
  (raw forward 5- and 21-session excess returns). 13 x 3 = **39 tests**; BH
  q=0.05 is run on those 39 and on no others.
  Disclosed near-duplication: ``label_rank_5`` is a strictly monotone
  within-date transform of ``label_excess_5``, so their Spearman rank ICs are
  identical up to tie handling. Both are reported because the card asks for
  the repo's ML target *and* the raw forward excess; the report states the
  measured gap between the two columns so nobody reads them as independent
  evidence.
* Per (factor, label): per-date cross-sectional Spearman rank IC ->
  ``ic_mean``, ``ic_std``, ``icir = mean/std``, ``t = icir * sqrt(n)`` over the
  full sample and over the recent window (2024-01-02 onward); two-sided
  Student-t p-value (df = n-1) and BH q=0.05 on the full-sample t.
* Sign stability, the card's stop-condition (3) quantity: the three
  preregistered sub-windows 2018-2020 / 2021-2023 / 2024-2026, scored as the
  fraction of sub-windows whose own mean IC shares the full-sample mean IC's
  sign (so the only possible values are 0, 1/3, 2/3, 1). The per-year version
  (Step 13-F 3.5's own definition) is reported next to it, not instead of it.
* Also per factor: week-over-week cross-sectional rank autocorrelation (a
  turnover proxy), missing rate, and the share of rows that are exactly zero
  -- the last one matters here in a way it never did for price-volume
  factors, because an insider column is 0 (not missing) for the ~85% of
  stock-days with no visible filing in the window, and an IC computed over a
  cross-section that is 85% ties is a much weaker statistic than its ``n``
  suggests.

Three deliberate differences from Step 13-F 3.5, each with its reason:

1. ``top_n=500``, not 1500 -- the card's pool is top-500 and the gate in step
   2 only ever sees top-500 names. Screening on a wider pool would measure a
   factor the strategy cannot trade.
2. Years 2018-2026, so the three sub-windows tile the full sample exactly.
   2016-2017 are excluded: the ``cmp_*`` split is structurally empty before
   2019 (it needs three prior years of visible filings and the archive starts
   2016), and Step 13-F 3.5 also starts at 2018.
3. No dedup / no top-N feature-set export. There are 13 columns with known
   algebraic identities between them (``routine + opportunistic ==
   open_market_buy_count``), so a rank-correlation dedup would only
   re-discover the identities documented in ``features/insider.py``; and this
   screen's output is evidence for one card, not a feature set for a model.

Missing-value semantics (from ``step0-collector-report.md`` section 9): the
insider table has a row for every stock-day in the pool, with 0 -- not null --
where no filing was visible. The only genuinely nullable column is
``days_since_last_visible_buy`` (null = the issuer never had a visible open-
market buy). Nothing is dropped for being zero.

Usage (light: ~50 weekly dates x 500 names x 13 columns per year)::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/screen_insider_factors.py

Outputs (all under ``reports/research/iterations/h20260916_01_insider_gate/``):
``step1-insider-screen.parquet`` (one row per factor x label),
``step1-insider-screen.json`` (the same table plus the run's metadata) and
``step1-insider-screen.md``. Per-year checkpoints live in
``step1_screen_checkpoints/`` so an interrupted run resumes.
"""

from __future__ import annotations

import argparse
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

from open_composer.research.features.insider import INSIDER_COLUMNS, INSIDER_ROOT  # noqa: E402
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    universe_as_of_calendar_month,
    weekly_rebalance_dates,
)

LABELS_ROOT = ROOT / "data" / "features" / "labels"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / "h20260916_01_insider_gate"
CHECKPOINT_DIR = OUT_DIR / "step1_screen_checkpoints"
OUT_PARQUET = OUT_DIR / "step1-insider-screen.parquet"
OUT_JSON = OUT_DIR / "step1-insider-screen.json"
OUT_MD = OUT_DIR / "step1-insider-screen.md"

LABEL_COLUMNS: tuple[str, ...] = ("label_rank_5", "label_excess_5", "label_excess_21")
ALL_YEARS: tuple[int, ...] = tuple(range(2018, 2027))
UNIVERSE_TOP_N = 500
RECENT_START = pd.Timestamp("2024-01-02")
#: The card's stop-condition (3) sub-windows, inclusive on both ends.
SUB_WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("2018_2020", "2018-01-01", "2020-12-31"),
    ("2021_2023", "2021-01-01", "2023-12-31"),
    ("2024_2026", "2024-01-01", "2026-12-31"),
)
MIN_CROSS_SECTION = 10
FDR_Q = 0.05
#: Gate columns whose screener verdict the card's stop condition (3) is about.
GATE_COLUMNS: tuple[str, ...] = (
    "open_market_buy_count_60d",
    "net_buyers_60d",
    "buyers_60d",
    "cmp_opportunistic_buy_60d",
    "open_market_sell_count_60d",
)


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


@dataclass
class _Accumulator:
    dates: list[pd.Timestamp] = field(default_factory=list)
    ic_values: list[float] = field(default_factory=list)


@dataclass
class _Counter:
    total: int = 0
    missing: int = 0
    zero: int = 0
    corr_sum: float = 0.0
    n_pairs: int = 0


def _weekly_dates_for_year(year: int) -> list[pd.Timestamp]:
    """The year's weekly rebalance dates, derived from the label table's own
    trade dates (i.e. real SIP trading days) rather than from a generated
    market calendar, so this screen's dates are the same dates the rest of the
    repo rebalances on.
    """
    path = LABELS_ROOT / f"{year}.parquet"
    if not path.exists():
        return []
    dates = pd.read_parquet(path, columns=["trade_date"])["trade_date"]
    return weekly_rebalance_dates(sorted(pd.to_datetime(dates.unique())))


def _membership(
    universe_panel: pd.DataFrame, dates: list[pd.Timestamp], top_n: int
) -> pd.DataFrame:
    rows: list[tuple[pd.Timestamp, str]] = []
    for date in dates:
        for symbol in universe_as_of_calendar_month(universe_panel, date, top_n=top_n):
            rows.append((date, symbol))
    return pd.DataFrame(rows, columns=["trade_date", "symbol"])


def _process_year(
    year: int,
    insider_root: Path,
    universe_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    """One year's per-(date, factor, label) ICs plus per-factor counters, as a
    tidy frame that round-trips through parquet (the checkpoint format).
    """
    dates = _weekly_dates_for_year(year)
    if not dates:
        return pd.DataFrame(), 0
    insider_path = insider_root / f"{year}.parquet"
    if not insider_path.exists():
        return pd.DataFrame(), 0
    factors = pd.read_parquet(insider_path, columns=["symbol", "trade_date", *INSIDER_COLUMNS])
    factors = factors.loc[factors["trade_date"].isin(dates)]
    labels = pd.read_parquet(
        LABELS_ROOT / f"{year}.parquet", columns=["symbol", "trade_date", *LABEL_COLUMNS]
    )
    labels = labels.loc[labels["trade_date"].isin(dates)]
    merged = factors.merge(labels, on=["symbol", "trade_date"], how="inner")
    merged = merged.merge(
        _membership(universe_panel, dates, UNIVERSE_TOP_N), on=["trade_date", "symbol"], how="inner"
    )
    if merged.empty:
        return pd.DataFrame(), 0

    rows: list[dict[str, object]] = []
    counters: dict[str, _Counter] = {column: _Counter() for column in INSIDER_COLUMNS}
    for column in INSIDER_COLUMNS:
        counter = counters[column]
        counter.total = len(merged)
        counter.missing = int(merged[column].isna().sum())
        counter.zero = int((merged[column] == 0).sum())

    for date, group in merged.groupby("trade_date", sort=True):
        for column in INSIDER_COLUMNS:
            factor_values = group[column]
            if factor_values.notna().sum() < MIN_CROSS_SECTION:
                continue
            for label in LABEL_COLUMNS:
                label_values = group[label]
                valid = factor_values.notna() & label_values.notna()
                if valid.sum() < MIN_CROSS_SECTION:
                    continue
                ic = factor_values.loc[valid].corr(label_values.loc[valid], method="spearman")
                if pd.notna(ic):
                    rows.append(
                        {
                            "record_type": "ic",
                            "factor": column,
                            "label": label,
                            "trade_date": date,
                            "ic": float(ic),
                            "corr_sum": None,
                            "n_pairs": None,
                            "total": None,
                            "missing": None,
                            "zero": None,
                        }
                    )

    # Week-over-week cross-sectional rank autocorrelation (turnover proxy).
    # Small enough here to use every weekly date in the year, unlike
    # scripts/screen_factors.py's sampled approximation.
    for column in INSIDER_COLUMNS:
        wide = merged.pivot(index="trade_date", columns="symbol", values=column)
        if len(wide) < 2:
            continue
        ranked = wide.rank(axis=1, pct=True)
        previous = ranked.iloc[:-1].reset_index(drop=True)
        following = ranked.iloc[1:].reset_index(drop=True)
        weekly_corr = previous.corrwith(following, axis=1).dropna()
        if weekly_corr.empty:
            continue
        counters[column].corr_sum += float(weekly_corr.sum())
        counters[column].n_pairs += int(len(weekly_corr))

    for column, counter in counters.items():
        rows.append(
            {
                "record_type": "counter",
                "factor": column,
                "label": None,
                "trade_date": None,
                "ic": None,
                "corr_sum": counter.corr_sum,
                "n_pairs": counter.n_pairs,
                "total": counter.total,
                "missing": counter.missing,
                "zero": counter.zero,
            }
        )
    return pd.DataFrame(rows), len(merged)


def _window_stats(series: pd.Series, start: pd.Timestamp | None, end: pd.Timestamp | None) -> dict:
    if start is not None:
        series = series.loc[series.index >= start]
    if end is not None:
        series = series.loc[series.index <= end]
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


def _benjamini_hochberg(p_values: np.ndarray, q: float) -> np.ndarray:
    """Standard BH step-up; NaN p-values never pass. Same implementation as
    ``scripts/screen_factors.py``'s, kept local so this script's own
    preregistered denominator is visibly independent of that one's.
    """
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
    below = ranked <= (np.arange(1, m + 1) / m) * q
    if not below.any():
        return passing
    max_i = int(np.max(np.where(below)[0]))
    passing[valid_idx[order[: max_i + 1]]] = True
    return passing


def _sign_stability_windows(series: pd.Series, full_sign: float) -> tuple[float, dict[str, float]]:
    per_window: dict[str, float] = {}
    for name, start, end in SUB_WINDOWS:
        stats = _window_stats(series, pd.Timestamp(start), pd.Timestamp(end))
        per_window[name] = stats["ic_mean"]
    finite = {k: v for k, v in per_window.items() if np.isfinite(v)}
    if not finite or full_sign == 0:
        return float("nan"), per_window
    share = float(np.mean([np.sign(v) == np.sign(full_sign) for v in finite.values()]))
    return share, per_window


def _sign_stability_years(series: pd.Series, full_sign: float) -> float:
    per_year = series.groupby(series.index.year).mean()
    if per_year.empty or full_sign == 0:
        return float("nan")
    return float(np.mean(np.sign(per_year) == np.sign(full_sign)))


def build_screen_table(
    ic_accumulators: dict[tuple[str, str], _Accumulator],
    counters: dict[str, _Counter],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (factor, label), bucket in ic_accumulators.items():
        series = pd.Series(bucket.ic_values, index=pd.DatetimeIndex(bucket.dates)).sort_index()
        full = _window_stats(series, None, None)
        recent = _window_stats(series, RECENT_START, None)
        stability, per_window = _sign_stability_windows(series, full["ic_mean"])
        counter = counters.get(factor, _Counter())
        rows.append(
            {
                "factor": factor,
                "label": label,
                "ic_mean_full": full["ic_mean"],
                "ic_std_full": full["ic_std"],
                "icir_full": full["icir"],
                "t_full": full["t"],
                "n_full": full["n"],
                "ic_mean_recent": recent["ic_mean"],
                "icir_recent": recent["icir"],
                "t_recent": recent["t"],
                "n_recent": recent["n"],
                "ic_mean_2018_2020": per_window["2018_2020"],
                "ic_mean_2021_2023": per_window["2021_2023"],
                "ic_mean_2024_2026": per_window["2024_2026"],
                "sign_stability_windows": stability,
                "sign_stability_years": _sign_stability_years(series, full["ic_mean"]),
                "rank_autocorr_weekly": (
                    counter.corr_sum / counter.n_pairs if counter.n_pairs else float("nan")
                ),
                "missing_rate": counter.missing / counter.total if counter.total else float("nan"),
                "zero_rate": counter.zero / counter.total if counter.total else float("nan"),
            }
        )
    screen = pd.DataFrame(rows)
    p_values = 2.0 * scipy_stats.t.sf(
        np.abs(screen["t_full"].to_numpy()), df=np.maximum(screen["n_full"].to_numpy() - 1, 1)
    )
    p_values = np.where(screen["n_full"].to_numpy() >= 2, p_values, np.nan)
    screen["p_value_full"] = p_values
    screen["fdr_pass"] = _benjamini_hochberg(p_values, FDR_Q)
    p_recent = 2.0 * scipy_stats.t.sf(
        np.abs(screen["t_recent"].to_numpy()), df=np.maximum(screen["n_recent"].to_numpy() - 1, 1)
    )
    p_recent = np.where(screen["n_recent"].to_numpy() >= 2, p_recent, np.nan)
    screen["p_value_recent"] = p_recent
    screen["fdr_pass_recent"] = _benjamini_hochberg(p_recent, FDR_Q)
    order = {column: index for index, column in enumerate(INSIDER_COLUMNS)}
    screen["_order"] = screen["factor"].map(order)
    label_order = {label: index for index, label in enumerate(LABEL_COLUMNS)}
    screen["_label_order"] = screen["label"].map(label_order)
    screen = screen.sort_values(["_order", "_label_order"], ignore_index=True).drop(
        columns=["_order", "_label_order"]
    )
    return screen


def _render_markdown(screen: pd.DataFrame, meta: dict) -> str:
    lines: list[str] = []
    lines.append("# H-20260916-01 第 1 步：Form 4 内部人因子筛选（预登记）")
    lines.append("")
    lines.append(
        f"- 生成时间：{meta['generated_at']}｜样本：{meta['first_date']} → {meta['last_date']}"
        f"（{meta['weekly_dates']} 个周频调仓日，{meta['rows']:,} 个股票日）"
    )
    lines.append(
        f"- 协议：{meta['n_factors']} 个内部人列 × {meta['n_labels']} 个标签 = "
        f"**{meta['n_tests']} 次检验**，BH q={FDR_Q}；池子 = 当月点时 top-{UNIVERSE_TOP_N} ADV；"
        f"近窗 = {RECENT_START.date()} 起"
    )
    lines.append(
        f"- 全样本通过 FDR：{meta['n_fdr_pass']}/{meta['n_tests']}；"
        f"近窗通过 FDR：{meta['n_fdr_pass_recent']}/{meta['n_tests']}"
    )
    lines.append("")
    lines.append("## 全表（每列 × 每标签）")
    lines.append("")
    lines.append(
        "| 因子 | 标签 | 全样本 IC | ICIR | t | n | 近窗 IC | 近窗 t | "
        "2018-20 | 2021-23 | 2024-26 | 符号稳定性(3 窗) | 符号稳定性(逐年) | FDR | 近窗 FDR |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:-:|:-:|")
    for _, row in screen.iterrows():
        lines.append(
            f"| `{row['factor']}` | {row['label']} | {row['ic_mean_full']:+.4f} | "
            f"{row['icir_full']:+.3f} | {row['t_full']:+.2f} | {int(row['n_full'])} | "
            f"{row['ic_mean_recent']:+.4f} | {row['t_recent']:+.2f} | "
            f"{row['ic_mean_2018_2020']:+.4f} | {row['ic_mean_2021_2023']:+.4f} | "
            f"{row['ic_mean_2024_2026']:+.4f} | {row['sign_stability_windows']:.2f} | "
            f"{row['sign_stability_years']:.2f} | "
            f"{'是' if row['fdr_pass'] else '否'} | {'是' if row['fdr_pass_recent'] else '否'} |"
        )
    lines.append("")
    lines.append("## 每列的覆盖率（为什么 IC 的 n 比看起来弱）")
    lines.append("")
    lines.append("| 因子 | 缺失率 | 恰好为 0 的比例 | 周度秩自相关 |")
    lines.append("|---|---:|---:|---:|")
    for factor, group in screen.groupby("factor", sort=False):
        row = group.iloc[0]
        lines.append(
            f"| `{factor}` | {row['missing_rate'] * 100:.1f}% | {row['zero_rate'] * 100:.1f}% | "
            f"{row['rank_autocorr_weekly']:.3f} |"
        )
    lines.append("")
    lines.append("## 门控列的停止判据 (3)：近窗 |t| ≥ 2 且 3 窗符号稳定性 ≥ 0.7")
    lines.append("")
    lines.append("| 门控列 | 标签 | 近窗 t | 3 窗符号稳定性 | 判据 (3) |")
    lines.append("|---|---|---:|---:|:-:|")
    for item in meta["gate_column_verdicts"]:
        lines.append(
            f"| `{item['factor']}` | {item['label']} | {item['t_recent']:+.2f} | "
            f"{item['sign_stability_windows']:.2f} | {item['verdict']} |"
        )
    lines.append("")
    lines.append(
        "判据 (3) 的读法（卡上原文「内部人特征在筛选器 recent 窗 |t| < 2 且符号稳定性 < 0.7」）："
        "**两个条件同时成立才算命中停止条件**，所以表里的 FAIL 表示这一列在近窗既不显著、"
        "符号也不稳定。"
    )
    lines.append("")
    lines.append(f"标签近似核对：{meta['label_rank_vs_excess_note']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--insider-root", type=Path, default=INSIDER_ROOT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    universe_panel = load_universe_panel(UNIVERSE_ROOT)
    _log(f"universe panel: {len(universe_panel):,} rows")

    ic_accumulators: dict[tuple[str, str], _Accumulator] = defaultdict(_Accumulator)
    counters: dict[str, _Counter] = defaultdict(_Counter)
    total_rows = 0
    all_dates: list[pd.Timestamp] = []
    for year in ALL_YEARS:
        checkpoint = CHECKPOINT_DIR / f"{year}.parquet"
        if checkpoint.exists() and not args.force:
            frame = pd.read_parquet(checkpoint)
            _log(f"{year}: loaded checkpoint ({len(frame):,} records)")
        else:
            started = time.monotonic()
            frame, rows = _process_year(year, args.insider_root, universe_panel)
            if frame.empty:
                _log(f"{year}: no rows")
                continue
            temporary = checkpoint.with_suffix(".parquet.part")
            frame.to_parquet(temporary, index=False)
            temporary.replace(checkpoint)
            elapsed = time.monotonic() - started
            _log(f"{year}: {rows:,} stock-days, {len(frame):,} records ({elapsed:.0f}s)")
        ic_rows = frame.loc[frame["record_type"] == "ic"]
        for (factor, label), group in ic_rows.groupby(["factor", "label"], sort=False):
            bucket = ic_accumulators[(str(factor), str(label))]
            bucket.dates.extend(pd.to_datetime(group["trade_date"]).tolist())
            bucket.ic_values.extend(float(value) for value in group["ic"])
        all_dates.extend(pd.to_datetime(ic_rows["trade_date"].unique()).tolist())
        for _, row in frame.loc[frame["record_type"] == "counter"].iterrows():
            counter = counters[str(row["factor"])]
            counter.total += int(row["total"])
            counter.missing += int(row["missing"])
            counter.zero += int(row["zero"])
            counter.corr_sum += float(row["corr_sum"])
            counter.n_pairs += int(row["n_pairs"])
            total_rows = sum(c.total for c in counters.values()) // max(len(counters), 1)

    screen = build_screen_table(ic_accumulators, dict(counters))
    weekly_dates = sorted(set(all_dates))

    rank_gap = float("nan")
    paired = screen.set_index(["factor", "label"])
    gaps = []
    for factor in INSIDER_COLUMNS:
        if (factor, "label_rank_5") in paired.index and (factor, "label_excess_5") in paired.index:
            gaps.append(
                abs(
                    float(paired.loc[(factor, "label_rank_5"), "ic_mean_full"])
                    - float(paired.loc[(factor, "label_excess_5"), "ic_mean_full"])
                )
            )
    if gaps:
        rank_gap = float(np.max(gaps))

    gate_verdicts = []
    for factor in GATE_COLUMNS:
        for label in LABEL_COLUMNS:
            subset = screen.loc[(screen["factor"] == factor) & (screen["label"] == label)]
            if subset.empty:
                continue
            row = subset.iloc[0]
            weak = abs(row["t_recent"]) < 2.0 and row["sign_stability_windows"] < 0.7
            gate_verdicts.append(
                {
                    "factor": factor,
                    "label": label,
                    "t_recent": float(row["t_recent"]),
                    "sign_stability_windows": float(row["sign_stability_windows"]),
                    # The card stops only when BOTH are weak, so "FAIL" here
                    # means the stop condition is hit for this column.
                    "verdict": "FAIL" if weak else "PASS",
                }
            )

    meta = {
        "hypothesis": "H-20260916-01",
        "step": 1,
        "card": "reports/research/hypotheses/H-20260916-01-insider-form4-confirmation-gate.md",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "insider_root": str(args.insider_root),
        "protocol": (
            "own preregistration (this script's module docstring); "
            "deliberately NOT merged into scripts/screen_factors.py's 506-test count"
        ),
        "universe_top_n": UNIVERSE_TOP_N,
        "years": list(ALL_YEARS),
        "labels": list(LABEL_COLUMNS),
        "n_factors": len(INSIDER_COLUMNS),
        "n_labels": len(LABEL_COLUMNS),
        "n_tests": int(len(screen)),
        "fdr_q": FDR_Q,
        "n_fdr_pass": int(screen["fdr_pass"].sum()),
        "n_fdr_pass_recent": int(screen["fdr_pass_recent"].sum()),
        "weekly_dates": len(weekly_dates),
        "first_date": weekly_dates[0].date().isoformat() if weekly_dates else None,
        "last_date": weekly_dates[-1].date().isoformat() if weekly_dates else None,
        "rows": int(total_rows),
        "recent_window_start": RECENT_START.date().isoformat(),
        "sub_windows": [{"name": n, "start": s, "end": e} for n, s, e in SUB_WINDOWS],
        "gate_column_verdicts": gate_verdicts,
        "label_rank_vs_excess_note": (
            f"`label_rank_5` 与 `label_excess_5` 的全样本 IC 最大差 {rank_gap:.5f}"
            "（两者按定义只差同日单调变换与并列处理，所以它们不是两条独立证据）"
        ),
        "max_abs_ic_gap_rank_vs_excess_5": rank_gap,
    }

    temporary = OUT_PARQUET.with_suffix(".parquet.part")
    screen.to_parquet(temporary, index=False)
    temporary.replace(OUT_PARQUET)
    OUT_JSON.write_text(
        json.dumps(
            {"meta": meta, "table": json.loads(screen.to_json(orient="records"))},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    OUT_MD.write_text(_render_markdown(screen, meta), encoding="utf-8")
    _log(
        f"wrote {OUT_PARQUET.name}, {OUT_JSON.name}, {OUT_MD.name}: "
        f"{meta['n_tests']} tests, {meta['n_fdr_pass']} pass full-sample BH, "
        f"{meta['n_fdr_pass_recent']} pass recent BH"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
