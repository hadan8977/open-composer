"""H-20260916-02 stage 1 step 3: preregistered factor screen for the news-attention columns.

Card: ``reports/research/hypotheses/H-20260916-02-news-attention-features.md``
("进现有筛选器（IC / ICIR / FDR / 符号稳定性）"). **This docstring is the
preregistration** -- written before the run, not edited afterwards to fit the
numbers. No LLM is involved at any point.

Why a separate script instead of adding ``"news_attention"`` to
``scripts/screen_factors.py``'s ``LIBRARIES`` or to
``scripts/screen_insider_factors.py``: each of those scripts' docstrings *is* an
already-executed preregistration that fixes its own multiple-testing
denominator (506 tests for the Step 13-F 3.5 price-volume screen, 39 for the
Form 4 screen). Appending a third data layer to either would silently rewrite a
finished preregistration's BH denominator. The news columns are a different
data layer and a different hypothesis family (``news_attention_features``), so
they get their own preregistration and their own BH denominator.

Protocol (same shape as ``screen_insider_factors.py``; the differences that
matter are listed after it):

* Sample: weekly rebalance rows (``loop.weekly_rebalance_dates`` over each
  year's real trading calendar, taken from ``data/features/labels/``), universe
  = that month's point-in-time top-500 by ADV rank
  (``loop.universe_as_of_calendar_month``, ``top_n=500``).
* **Window: 2024-01-02 .. 2026-08-31 only** -- about 139 weekly dates. The news
  archive's first real day is 2024-01-01 (45 articles are visible earlier) and
  its last ``visible_at`` is 2026-09-09, and a 21-session forward label needs a
  month of future sessions. Every table this script writes is therefore a
  **小样本 (2024→)** table and says so; the three sub-windows below are single
  calendar years, not the three-year blocks the Form 4 screen could afford.
* Factors: ``features.news_attention.SCREEN_COLUMNS`` -- the published feature
  columns minus ``distinct_sources_5d``, which this archive makes a constant
  (one source, ``benzinga``, for all 684,876 articles; a column with no
  cross-sectional variance has an undefined rank IC, so including it would pad
  the BH denominator with a test that cannot reject). The exclusion and its
  reason are declared in ``SCREEN_EXCLUDED_COLUMNS``, i.e. in the column
  contract, not here.
* Labels: ``label_rank_5`` (the repo's ML target: within-date percentile of the
  5-session forward excess), ``label_excess_5`` and ``label_excess_21`` (raw
  forward 5- and 21-session excess). 16 x 3 = **48 tests**; BH q=0.05 is run on
  those 48 and on no others.
  Disclosed near-duplication: ``label_rank_5`` is a strictly monotone
  within-date transform of ``label_excess_5``, so their Spearman rank ICs are
  identical up to tie handling. Both are reported because the card asks for the
  repo's ML target *and* the raw forward excess; the report states the measured
  gap so nobody reads them as independent evidence.
* Per (factor, label): per-date cross-sectional Spearman rank IC ->
  ``ic_mean``, ``ic_std``, ``icir = mean/std``, ``t = icir * sqrt(n)``;
  two-sided Student-t p-value (df = n-1) and BH q=0.05 on the full-window t.
  A "recent" sub-window is reported too, starting 2025-09-01 (the last twelve
  months), because with a 2.7-year sample the Form 4 screen's "2024 onward =
  recent" split would have been the whole sample.
* Sign stability: the fraction of the three preregistered sub-windows (2024 /
  2025 / 2026) whose own mean IC shares the full-window mean IC's sign, so the
  only possible values are 0, 1/3, 2/3, 1 -- and, per lesson L-20260916-01
  item 5, the per-year version is *the same thing* here, because the
  sub-windows already are single years. That is a real loss of resolution and
  the report states it rather than dressing three years up as a stability test.
* Also per factor: week-over-week cross-sectional rank autocorrelation (a
  turnover proxy), missing rate, and the share of rows that are exactly zero.
  The zero share is the number that decides whether a column can be a ranking
  feature at all: a count column is 0 (not missing) for every stock-week with
  no article in the window, and an IC computed over a cross-section that is
  mostly ties is a far weaker statistic than its ``n`` suggests.

The card's own extra question (not part of the 48): ``attention_surge_5d``'s IC
**inside each novelty tercile**, i.e. "surge + novel" versus "surge +
repetitive". Terciles are cut per date on ``novelty_5d`` among the names that
have one (a name with no article in 5 sessions has no novelty, so it is in no
tercile), and the IC is computed inside each tercile. These are reported as a
separate block, with their own BH run over their own 9 tests (3 terciles x 3
labels), and they are *not* mixed into the 48: the 48 is the family the card's
stop condition (1) is scored on.

Usage (light: ~139 weekly dates x 500 names x 16 columns)::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/screen_news_attention_factors.py

Outputs (all under ``reports/research/iterations/h20260916_02_news_attention/``):
``step3-news-screen.parquet`` (one row per factor x label),
``step3-news-screen.json`` (the same table plus the run's metadata and the
tercile block) and ``step3-news-screen.md``. Per-year checkpoints live in
``step3_screen_checkpoints/`` so an interrupted run resumes.
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

from open_composer.research.features.news_attention import (  # noqa: E402
    NEWS_ATTENTION_ROOT,
    SCREEN_COLUMNS,
    SCREEN_EXCLUDED_COLUMNS,
)
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    universe_as_of_calendar_month,
    weekly_rebalance_dates,
)

LABELS_ROOT = ROOT / "data" / "features" / "labels"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / "h20260916_02_news_attention"
CHECKPOINT_DIR = OUT_DIR / "step3_screen_checkpoints"
OUT_PARQUET = OUT_DIR / "step3-news-screen.parquet"
OUT_JSON = OUT_DIR / "step3-news-screen.json"
OUT_MD = OUT_DIR / "step3-news-screen.md"

LABEL_COLUMNS: tuple[str, ...] = ("label_rank_5", "label_excess_5", "label_excess_21")
ALL_YEARS: tuple[int, ...] = (2024, 2025, 2026)
UNIVERSE_TOP_N = 500
#: The card's sample window. Both ends are preregistered, for the reasons in
#: the module docstring (archive start; 21-session forward label).
SAMPLE_START = pd.Timestamp("2024-01-02")
SAMPLE_END = pd.Timestamp("2026-08-31")
#: "Recent" cannot be "2024 onward" on a 2024-onward sample; the last twelve
#: months is the smallest split that still has ~50 weekly cross-sections.
RECENT_START = pd.Timestamp("2025-09-01")
SUB_WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", "2026-12-31"),
)
MIN_CROSS_SECTION = 10
FDR_Q = 0.05
#: The card's extra question: the surge column's IC inside each novelty tercile.
TERCILE_FACTOR = "attention_surge_5d"
TERCILE_SPLIT_COLUMN = "novelty_5d"
TERCILE_NAMES: tuple[str, ...] = ("novelty_low", "novelty_mid", "novelty_high")
#: Columns the gate in step 4 reads, whose screener verdict the card's stop
#: condition about "no column has signal" is read off first.
GATE_COLUMNS: tuple[str, ...] = (
    "attention_surge_5d",
    "novelty_5d",
    "news_count_20d",
    "news_count_5d",
    "days_since_last_news",
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
    """The year's weekly rebalance dates inside the preregistered sample window,
    derived from the label table's own trade dates (real SIP sessions) so this
    screen's dates are the dates the rest of the repo rebalances on.
    """
    path = LABELS_ROOT / f"{year}.parquet"
    if not path.exists():
        return []
    dates = pd.read_parquet(path, columns=["trade_date"])["trade_date"]
    weekly = weekly_rebalance_dates(sorted(pd.to_datetime(dates.unique())))
    return [date for date in weekly if SAMPLE_START <= date <= SAMPLE_END]


def _membership(
    universe_panel: pd.DataFrame, dates: list[pd.Timestamp], top_n: int
) -> pd.DataFrame:
    rows: list[tuple[pd.Timestamp, str]] = []
    for date in dates:
        for symbol in universe_as_of_calendar_month(universe_panel, date, top_n=top_n):
            rows.append((date, symbol))
    return pd.DataFrame(rows, columns=["trade_date", "symbol"])


def _spearman(left: pd.Series, right: pd.Series) -> float | None:
    valid = left.notna() & right.notna()
    if valid.sum() < MIN_CROSS_SECTION:
        return None
    value = left.loc[valid].corr(right.loc[valid], method="spearman")
    return float(value) if pd.notna(value) else None


def _process_year(
    year: int,
    news_root: Path,
    universe_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    """One year's per-(date, factor, label) ICs, per-factor counters and the
    tercile block, as a tidy frame that round-trips through parquet.
    """
    dates = _weekly_dates_for_year(year)
    if not dates:
        return pd.DataFrame(), 0
    news_path = news_root / f"{year}.parquet"
    if not news_path.exists():
        return pd.DataFrame(), 0
    columns = sorted({*SCREEN_COLUMNS, TERCILE_SPLIT_COLUMN, TERCILE_FACTOR})
    factors = pd.read_parquet(news_path, columns=["symbol", "trade_date", *columns])
    factors = factors.loc[factors["trade_date"].isin(dates)]
    labels = pd.read_parquet(
        LABELS_ROOT / f"{year}.parquet", columns=["symbol", "trade_date", *LABEL_COLUMNS]
    )
    labels = labels.loc[labels["trade_date"].isin(dates)]
    factors["symbol"] = factors["symbol"].astype(str)
    labels["symbol"] = labels["symbol"].astype(str)
    merged = factors.merge(labels, on=["symbol", "trade_date"], how="inner")
    merged = merged.merge(
        _membership(universe_panel, dates, UNIVERSE_TOP_N), on=["trade_date", "symbol"], how="inner"
    )
    if merged.empty:
        return pd.DataFrame(), 0

    rows: list[dict[str, object]] = []
    counters: dict[str, _Counter] = {column: _Counter() for column in SCREEN_COLUMNS}
    for column in SCREEN_COLUMNS:
        counter = counters[column]
        counter.total = len(merged)
        counter.missing = int(merged[column].isna().sum())
        counter.zero = int((merged[column] == 0).sum())

    def _record(kind: str, factor: str, label: str, date: pd.Timestamp, ic: float) -> None:
        rows.append(
            {
                "record_type": kind,
                "factor": factor,
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

    for date, group in merged.groupby("trade_date", sort=True):
        for column in SCREEN_COLUMNS:
            for label in LABEL_COLUMNS:
                ic = _spearman(group[column], group[label])
                if ic is not None:
                    _record("ic", column, label, date, ic)
        # The card's tercile question. Terciles are cut on this date's own
        # novelty cross-section among names that have a novelty value at all.
        novelty = group[TERCILE_SPLIT_COLUMN]
        defined = group.loc[novelty.notna()]
        if len(defined) >= 3 * MIN_CROSS_SECTION:
            try:
                buckets = pd.qcut(
                    defined[TERCILE_SPLIT_COLUMN], 3, labels=list(TERCILE_NAMES), duplicates="drop"
                )
            except ValueError:
                buckets = None
            if buckets is not None:
                for bucket_name, bucket in defined.groupby(buckets, observed=True):
                    for label in LABEL_COLUMNS:
                        ic = _spearman(bucket[TERCILE_FACTOR], bucket[label])
                        if ic is not None:
                            _record("tercile_ic", str(bucket_name), label, date, ic)

    for column in SCREEN_COLUMNS:
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
    """Standard BH step-up; NaN p-values never pass. Kept local so this
    script's preregistered denominator is visibly independent of the other
    screens' denominators.
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


def _add_p_and_fdr(frame: pd.DataFrame) -> pd.DataFrame:
    p_values = 2.0 * scipy_stats.t.sf(
        np.abs(frame["t_full"].to_numpy()), df=np.maximum(frame["n_full"].to_numpy() - 1, 1)
    )
    p_values = np.where(frame["n_full"].to_numpy() >= 2, p_values, np.nan)
    frame["p_value_full"] = p_values
    frame["fdr_pass"] = _benjamini_hochberg(p_values, FDR_Q)
    p_recent = 2.0 * scipy_stats.t.sf(
        np.abs(frame["t_recent"].to_numpy()), df=np.maximum(frame["n_recent"].to_numpy() - 1, 1)
    )
    p_recent = np.where(frame["n_recent"].to_numpy() >= 2, p_recent, np.nan)
    frame["p_value_recent"] = p_recent
    frame["fdr_pass_recent"] = _benjamini_hochberg(p_recent, FDR_Q)
    return frame


def build_screen_table(
    ic_accumulators: dict[tuple[str, str], _Accumulator],
    counters: dict[str, _Counter],
    *,
    order: tuple[str, ...],
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
                "ic_mean_2024": per_window["2024"],
                "ic_mean_2025": per_window["2025"],
                "ic_mean_2026": per_window["2026"],
                "sign_stability_windows": stability,
                "rank_autocorr_weekly": (
                    counter.corr_sum / counter.n_pairs if counter.n_pairs else float("nan")
                ),
                "missing_rate": counter.missing / counter.total if counter.total else float("nan"),
                "zero_rate": counter.zero / counter.total if counter.total else float("nan"),
            }
        )
    screen = pd.DataFrame(rows)
    if screen.empty:
        return screen
    screen = _add_p_and_fdr(screen)
    factor_order = {column: index for index, column in enumerate(order)}
    label_order = {label: index for index, label in enumerate(LABEL_COLUMNS)}
    screen["_order"] = screen["factor"].map(factor_order)
    screen["_label_order"] = screen["label"].map(label_order)
    return screen.sort_values(["_order", "_label_order"], ignore_index=True).drop(
        columns=["_order", "_label_order"]
    )


def _render_markdown(screen: pd.DataFrame, terciles: pd.DataFrame, meta: dict) -> str:
    lines: list[str] = []
    lines.append("# H-20260916-02 第 3 步：新闻注意力因子筛选（预登记，2024→ 小样本）")
    lines.append("")
    lines.append(
        f"- 生成时间：{meta['generated_at']}｜样本：{meta['first_date']} → {meta['last_date']}"
        f"（{meta['weekly_dates']} 个周频调仓日，{meta['rows']:,} 个股票日）"
    )
    lines.append(
        f"- 协议：{meta['n_factors']} 个新闻列 × {meta['n_labels']} 个标签 = "
        f"**{meta['n_tests']} 次检验**，BH q={FDR_Q}；池子 = 当月点时 top-{UNIVERSE_TOP_N} ADV；"
        f"近窗 = {RECENT_START.date()} 起（最近 12 个月）"
    )
    lines.append(
        f"- 全窗通过 FDR：{meta['n_fdr_pass']}/{meta['n_tests']}；"
        f"近窗通过 FDR：{meta['n_fdr_pass_recent']}/{meta['n_tests']}"
    )
    lines.append(
        "- **样本只有 2.7 年**（新闻档案 2024-01 才开始），所以：三个子窗就是三个自然年，"
        "「符号稳定性」只有 0 / 0.33 / 0.67 / 1.00 四个取值，且等价于「三年符号一致」；"
        "这一节的每张表都要按小样本读。"
    )
    for column, reason in SCREEN_EXCLUDED_COLUMNS.items():
        lines.append(f"- 排除列 `{column}`（不进 BH 分母）：{reason}")
    lines.append("")
    lines.append("## 全表（每列 × 每标签）")
    lines.append("")
    lines.append(
        "| 因子 | 标签 | 全窗 IC | ICIR | t | n | 近窗 IC | 近窗 t | "
        "2024 | 2025 | 2026 | 符号稳定性(3 年) | FDR | 近窗 FDR |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:-:|:-:|")
    for _, row in screen.iterrows():
        lines.append(
            f"| `{row['factor']}` | {row['label']} | {row['ic_mean_full']:+.4f} | "
            f"{row['icir_full']:+.3f} | {row['t_full']:+.2f} | {int(row['n_full'])} | "
            f"{row['ic_mean_recent']:+.4f} | {row['t_recent']:+.2f} | "
            f"{row['ic_mean_2024']:+.4f} | {row['ic_mean_2025']:+.4f} | "
            f"{row['ic_mean_2026']:+.4f} | {row['sign_stability_windows']:.2f} | "
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
    lines.append(f"## 卡上的附加问题：`{TERCILE_FACTOR}` 在 `{TERCILE_SPLIT_COLUMN}` 三分位内的 IC")
    lines.append("")
    lines.append(
        "读法：`novelty_high` = 「突增且新颖」，`novelty_low` = 「突增但重复」。"
        "三分位按每个调仓日自己的截面切，只在有新颖度取值（过去 5 个交易日有报道）的名字里切；"
        f"这 {len(terciles)} 个检验有自己的 BH（{FDR_Q}），"
        f"**不进上面那 {meta['n_tests']} 个的分母**。"
    )
    lines.append("")
    if terciles.empty:
        lines.append("（没有足够的截面做三分位。）")
    else:
        lines.append("| 三分位 | 标签 | 全窗 IC | ICIR | t | n | 2024 | 2025 | 2026 | FDR |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|:-:|")
        for _, row in terciles.iterrows():
            lines.append(
                f"| `{row['factor']}` | {row['label']} | {row['ic_mean_full']:+.4f} | "
                f"{row['icir_full']:+.3f} | {row['t_full']:+.2f} | {int(row['n_full'])} | "
                f"{row['ic_mean_2024']:+.4f} | {row['ic_mean_2025']:+.4f} | "
                f"{row['ic_mean_2026']:+.4f} | {'是' if row['fdr_pass'] else '否'} |"
            )
    lines.append("")
    lines.append("## 第 4 步门控列的判据：全窗过 FDR 或近窗 |t| ≥ 2 且符号稳定性 ≥ 0.67")
    lines.append("")
    lines.append("| 门控列 | 标签 | 全窗 t | 近窗 t | 符号稳定性 | 过 FDR | 判据 |")
    lines.append("|---|---|---:|---:|---:|:-:|:-:|")
    for item in meta["gate_column_verdicts"]:
        lines.append(
            f"| `{item['factor']}` | {item['label']} | {item['t_full']:+.2f} | "
            f"{item['t_recent']:+.2f} | {item['sign_stability_windows']:.2f} | "
            f"{'是' if item['fdr_pass'] else '否'} | {item['verdict']} |"
        )
    lines.append("")
    lines.append(f"标签近似核对：{meta['label_rank_vs_excess_note']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--news-root", type=Path, default=NEWS_ATTENTION_ROOT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    universe_panel = load_universe_panel(UNIVERSE_ROOT)
    _log(f"universe panel: {len(universe_panel):,} rows")

    ic_accumulators: dict[tuple[str, str], _Accumulator] = defaultdict(_Accumulator)
    tercile_accumulators: dict[tuple[str, str], _Accumulator] = defaultdict(_Accumulator)
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
            frame, rows = _process_year(year, args.news_root, universe_panel)
            if frame.empty:
                _log(f"{year}: no rows")
                continue
            temporary = checkpoint.with_suffix(".parquet.part")
            frame.to_parquet(temporary, index=False)
            temporary.replace(checkpoint)
            _log(
                f"{year}: {rows:,} stock-days, {len(frame):,} records "
                f"({time.monotonic() - started:.0f}s)"
            )
        for kind, sink in (("ic", ic_accumulators), ("tercile_ic", tercile_accumulators)):
            subset = frame.loc[frame["record_type"] == kind]
            for (factor, label), group in subset.groupby(["factor", "label"], sort=False):
                bucket = sink[(str(factor), str(label))]
                bucket.dates.extend(pd.to_datetime(group["trade_date"]).tolist())
                bucket.ic_values.extend(float(value) for value in group["ic"])
            if kind == "ic":
                all_dates.extend(pd.to_datetime(subset["trade_date"].unique()).tolist())
        for _, row in frame.loc[frame["record_type"] == "counter"].iterrows():
            counter = counters[str(row["factor"])]
            counter.total += int(row["total"])
            counter.missing += int(row["missing"])
            counter.zero += int(row["zero"])
            counter.corr_sum += float(row["corr_sum"])
            counter.n_pairs += int(row["n_pairs"])
        total_rows = sum(c.total for c in counters.values()) // max(len(counters), 1)

    screen = build_screen_table(ic_accumulators, dict(counters), order=SCREEN_COLUMNS)
    terciles = build_screen_table(tercile_accumulators, {}, order=TERCILE_NAMES)
    weekly_dates = sorted(set(all_dates))

    paired = screen.set_index(["factor", "label"])
    gaps = [
        abs(
            float(paired.loc[(factor, "label_rank_5"), "ic_mean_full"])
            - float(paired.loc[(factor, "label_excess_5"), "ic_mean_full"])
        )
        for factor in SCREEN_COLUMNS
        if (factor, "label_rank_5") in paired.index and (factor, "label_excess_5") in paired.index
    ]
    rank_gap = float(np.max(gaps)) if gaps else float("nan")

    gate_verdicts = []
    for factor in GATE_COLUMNS:
        for label in LABEL_COLUMNS:
            subset = screen.loc[(screen["factor"] == factor) & (screen["label"] == label)]
            if subset.empty:
                continue
            row = subset.iloc[0]
            strong = bool(row["fdr_pass"]) or (
                abs(row["t_recent"]) >= 2.0 and row["sign_stability_windows"] >= 0.66
            )
            gate_verdicts.append(
                {
                    "factor": factor,
                    "label": label,
                    "t_full": float(row["t_full"]),
                    "t_recent": float(row["t_recent"]),
                    "sign_stability_windows": float(row["sign_stability_windows"]),
                    "fdr_pass": bool(row["fdr_pass"]),
                    "verdict": "PASS" if strong else "FAIL",
                }
            )

    meta = {
        "hypothesis": "H-20260916-02",
        "stage": "1 (no LLM)",
        "step": 3,
        "card": "reports/research/hypotheses/H-20260916-02-news-attention-features.md",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "news_root": str(args.news_root),
        "protocol": (
            "own preregistration (this script's module docstring); deliberately NOT merged "
            "into scripts/screen_factors.py's 506-test count or "
            "scripts/screen_insider_factors.py's 39-test count"
        ),
        "universe_top_n": UNIVERSE_TOP_N,
        "years": list(ALL_YEARS),
        "sample_window": [SAMPLE_START.date().isoformat(), SAMPLE_END.date().isoformat()],
        "small_sample_note": "2024→ 小样本：新闻档案 2024-01 才开始，全窗只有约 2.7 年",
        "labels": list(LABEL_COLUMNS),
        "n_factors": len(SCREEN_COLUMNS),
        "n_labels": len(LABEL_COLUMNS),
        "n_tests": int(len(screen)),
        "excluded_columns": dict(SCREEN_EXCLUDED_COLUMNS),
        "fdr_q": FDR_Q,
        "n_fdr_pass": int(screen["fdr_pass"].sum()) if not screen.empty else 0,
        "n_fdr_pass_recent": int(screen["fdr_pass_recent"].sum()) if not screen.empty else 0,
        "n_tercile_tests": int(len(terciles)),
        "n_tercile_fdr_pass": int(terciles["fdr_pass"].sum()) if not terciles.empty else 0,
        "weekly_dates": len(weekly_dates),
        "first_date": weekly_dates[0].date().isoformat() if weekly_dates else None,
        "last_date": weekly_dates[-1].date().isoformat() if weekly_dates else None,
        "rows": int(total_rows),
        "recent_window_start": RECENT_START.date().isoformat(),
        "sub_windows": [{"name": n, "start": s, "end": e} for n, s, e in SUB_WINDOWS],
        "tercile_factor": TERCILE_FACTOR,
        "tercile_split_column": TERCILE_SPLIT_COLUMN,
        "gate_column_verdicts": gate_verdicts,
        "label_rank_vs_excess_note": (
            f"`label_rank_5` 与 `label_excess_5` 的全窗 IC 最大差 {rank_gap:.5f}"
            "（两者按定义只差同日单调变换与并列处理，所以它们不是两条独立证据）"
        ),
        "max_abs_ic_gap_rank_vs_excess_5": rank_gap,
        "llm_used": False,
    }

    temporary = OUT_PARQUET.with_suffix(".parquet.part")
    screen.to_parquet(temporary, index=False)
    temporary.replace(OUT_PARQUET)
    OUT_JSON.write_text(
        json.dumps(
            {
                "meta": meta,
                "table": json.loads(screen.to_json(orient="records")),
                "terciles": json.loads(terciles.to_json(orient="records")),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    OUT_MD.write_text(_render_markdown(screen, terciles, meta), encoding="utf-8")
    _log(
        f"wrote {OUT_PARQUET.name}, {OUT_JSON.name}, {OUT_MD.name}: "
        f"{meta['n_tests']} tests, {meta['n_fdr_pass']} pass full-window BH, "
        f"{meta['n_fdr_pass_recent']} pass recent BH; "
        f"terciles {meta['n_tercile_fdr_pass']}/{meta['n_tercile_tests']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
