"""H-20260916-07 step 2: preregistered factor screen for the FINRA short-interest columns.

Card: ``reports/research/hypotheses/H-20260916-07-finra-short-interest-avoid-list.md``
**This docstring is the preregistration** -- written before the run, not edited
afterwards to fit the numbers.

Why a third screening script instead of a flag on an existing one: both
``scripts/screen_factors.py`` (253 price-volume factors x 2 labels = 506 tests)
and ``scripts/screen_insider_factors.py`` (13 insider columns x 3 labels = 39
tests) have module docstrings that *are* already-executed preregistrations and
fix their own BH denominators. Adding five short-interest columns to either
would silently rewrite a finished preregistration's multiple-testing count.
Short interest is a different data layer and a different hypothesis family
(``short_interest_avoid``), so it gets its own preregistration and its own BH
denominator. The statistics themselves are *imported* from
``scripts.screen_insider_factors`` rather than re-implemented, so a third copy
of a Benjamini-Hochberg step-up cannot drift from the other two; the repo
already crosses script boundaries this way
(``run_h20260916_01_insider_gate.py`` imports ``run_step13_m_grid``'s helpers).

Protocol (identical in shape to ``screen_insider_factors.py``, differences
listed after it):

* Sample: weekly rebalance rows (``loop.weekly_rebalance_dates`` over each
  year's real trading calendar, taken from ``data/features/labels/``), universe
  = that month's point-in-time top-500 by ADV rank
  (``loop.universe_as_of_calendar_month``, ``top_n=500``).
* Factors: the 5 non-key columns of
  ``data/features/short_interest/{year}.parquet``
  (``features.short_interest.SHORT_INTEREST_COLUMNS`` -- the single source of
  that list).
* Labels: ``label_rank_5``, ``label_excess_5``, ``label_excess_21``.
  5 x 3 = **15 tests**; BH q=0.05 is run on those 15 and on no others.
  Disclosed near-duplication, same as the insider screen: ``label_rank_5`` is a
  strictly monotone within-date transform of ``label_excess_5``, so their
  Spearman rank ICs coincide up to tie handling, and the report prints the
  measured gap so nobody reads them as independent evidence.
* Per (factor, label): per-date cross-sectional Spearman rank IC ->
  ``ic_mean``, ``ic_std``, ``icir``, ``t = icir * sqrt(n)`` over the full sample
  and over the recent window (2024-01-02 onward); two-sided Student-t p-value
  and BH q=0.05 on the full-sample t.
* Sign stability over the three preregistered sub-windows 2018-2020 /
  2021-2023 / 2024-2026, scored as the fraction of sub-windows whose own mean
  IC shares the full-sample sign (possible values 0, 1/3, 2/3, 1). The per-year
  version is reported next to it, not instead of it.
* Also per factor: week-over-week cross-sectional rank autocorrelation, missing
  rate and exact-zero rate. Autocorrelation matters more here than for any
  earlier library: the underlying data only changes twice a month, so a
  short-interest column's weekly rank autocorrelation should be near 1 and an
  IC series computed on overlapping weeks has far fewer independent
  observations than its ``n``. The report states this next to the t-statistics
  instead of letting ``n`` speak for a precision the data does not have.

Four deliberate differences from the insider screen, each with its reason:

1. **Sign expectation is negative, and preregistered as such.** The literature
   leg this card leans on is the short one (high short interest -> lower future
   returns), so the card's hypothesis predicts *negative* IC against forward
   excess for ``days_to_cover``, ``short_interest_ratio`` and
   ``dtc_cross_sectional_pct``. A significantly positive IC does not support the
   avoid list; it refutes it. The output therefore carries an explicit
   ``supports_card`` column rather than leaving a reader to infer direction from
   a sign.
2. **Years 2018-2026.** Not a choice: the free FINRA API's earliest settlement
   date is 2017-12-29 (first visible 2018-01-10), so 2016-2017 do not exist for
   this layer. The three sub-windows still tile the sample exactly.
3. **``staleness_days`` is screened as a negative control**, not as a candidate
   factor. It is a deterministic sawtooth of the publication calendar. Whatever
   IC it shows is an upper bound on how much of any other column's IC is
   calendar rather than short interest; a days-to-cover column that does not
   beat it has shown nothing. It is inside the BH denominator because leaving a
   preregistered test out of the denominator after seeing its value is exactly
   the move FDR exists to prevent.
4. **No dedup / no top-N feature-set export.** Five columns with known
   relationships (``dtc_cross_sectional_pct`` is a within-date monotone
   transform of ``days_to_cover``) -- a rank-correlation dedup would only
   rediscover them, and this screen's output is evidence for one card, not a
   feature set for a model.

Missing-value semantics: every stock-day in the pool has a row, but the
short-interest columns are **null**, not 0, when the symbol has no visible
FINRA record (or none with a positive average daily volume). Nothing is
zero-filled here -- a null is "we cannot see this name's short interest", which
is not the statement "its short interest is zero". Coverage is quoted per year
in the pre-check table and again here as ``missing_rate``.

Usage (light: ~50 weekly dates x 500 names x 5 columns per year)::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/screen_short_interest_factors.py

Outputs (all under
``reports/research/iterations/h20260916_07_short_interest/``):
``screen.parquet`` (one row per factor x label), ``screen.json`` (the same
table plus the run's metadata) and ``screen.md``. Per-year checkpoints live in
``screen_checkpoints/`` so an interrupted run resumes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats as scipy_stats  # noqa: E402

from open_composer.research.features.short_interest import (  # noqa: E402
    SHORT_INTEREST_COLUMNS,
    SHORT_INTEREST_ROOT,
)
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    universe_as_of_calendar_month,
    weekly_rebalance_dates,
)

# The statistics, imported rather than copied: one BH step-up, one window-stats
# helper and one sign-stability definition for all three screens in the repo.
from scripts.screen_insider_factors import (  # noqa: E402
    FDR_Q,
    MIN_CROSS_SECTION,
    RECENT_START,
    SUB_WINDOWS,
    _Accumulator,
    _benjamini_hochberg,
    _Counter,
    _sign_stability_windows,
    _sign_stability_years,
    _window_stats,
)

LABELS_ROOT = ROOT / "data" / "features" / "labels"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / "h20260916_07_short_interest"
CHECKPOINT_DIR = OUT_DIR / "screen_checkpoints"
OUT_PARQUET = OUT_DIR / "screen.parquet"
OUT_JSON = OUT_DIR / "screen.json"
OUT_MD = OUT_DIR / "screen.md"

LABEL_COLUMNS: tuple[str, ...] = ("label_rank_5", "label_excess_5", "label_excess_21")
ALL_YEARS: tuple[int, ...] = tuple(range(2018, 2027))
UNIVERSE_TOP_N = 500

#: Preregistered sign expectation. The card's leg of the literature is the short
#: one (high short interest -> lower future returns), so a *negative* IC against
#: forward excess supports the avoid list and a positive one refutes it.
#: ``staleness_days`` is a calendar control with no predicted direction.
EXPECTED_SIGN: dict[str, int] = {
    "days_to_cover": -1,
    "short_interest_ratio": -1,
    "dtc_change_vs_prior": -1,
    "dtc_cross_sectional_pct": -1,
    "staleness_days": 0,
}

#: The column the card's gate is actually built on; its screener verdict is the
#: one the report's stop condition quotes.
GATE_COLUMN = "dtc_cross_sectional_pct"


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _weekly_dates_for_year(year: int) -> list[pd.Timestamp]:
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
    feature_root: Path,
    universe_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    """One year's per-(date, factor, label) ICs plus per-factor counters."""
    dates = _weekly_dates_for_year(year)
    if not dates:
        return pd.DataFrame(), 0
    feature_path = feature_root / f"{year}.parquet"
    if not feature_path.exists():
        return pd.DataFrame(), 0
    factors = pd.read_parquet(
        feature_path, columns=["symbol", "trade_date", *SHORT_INTEREST_COLUMNS]
    )
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
    counters: dict[str, _Counter] = {column: _Counter() for column in SHORT_INTEREST_COLUMNS}
    for column in SHORT_INTEREST_COLUMNS:
        counter = counters[column]
        counter.total = len(merged)
        counter.missing = int(merged[column].isna().sum())
        counter.zero = int((merged[column] == 0).sum())

    for date, group in merged.groupby("trade_date", sort=True):
        for column in SHORT_INTEREST_COLUMNS:
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

    for column in SHORT_INTEREST_COLUMNS:
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
        expected = EXPECTED_SIGN.get(factor, 0)
        rows.append(
            {
                "factor": factor,
                "label": label,
                "expected_sign": expected,
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
                "supports_card": bool(
                    expected != 0
                    and np.isfinite(full["ic_mean"])
                    and np.sign(full["ic_mean"]) == expected
                ),
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
    order = {column: index for index, column in enumerate(SHORT_INTEREST_COLUMNS)}
    label_order = {label: index for index, label in enumerate(LABEL_COLUMNS)}
    screen["_order"] = screen["factor"].map(order)
    screen["_label_order"] = screen["label"].map(label_order)
    return screen.sort_values(["_order", "_label_order"], ignore_index=True).drop(
        columns=["_order", "_label_order"]
    )


def _render_markdown(screen: pd.DataFrame, meta: dict) -> str:
    lines: list[str] = []
    lines.append("# H-20260916-07 第 2 步：FINRA 空头兴趣因子筛选（预登记）")
    lines.append("")
    lines.append(
        f"- 生成时间：{meta['generated_at']}｜样本：{meta['first_date']} → {meta['last_date']}"
        f"（{meta['weekly_dates']} 个周频调仓日，{meta['rows']:,} 个股票日）"
    )
    lines.append(
        f"- 协议：{meta['n_factors']} 个空头兴趣列 × {meta['n_labels']} 个标签 = "
        f"**{meta['n_tests']} 次检验**，BH q={FDR_Q}（本族独立分母）；"
        f"池子 = 当月点时 top-{UNIVERSE_TOP_N} ADV；近窗 = {RECENT_START.date()} 起"
    )
    lines.append(
        f"- 全样本通过 FDR：{meta['n_fdr_pass']}/{meta['n_tests']}；"
        f"近窗通过 FDR：{meta['n_fdr_pass_recent']}/{meta['n_tests']}；"
        f"方向与卡一致（IC 为负）的检验：{meta['n_supports_card']}/{meta['n_directional_tests']}"
    )
    lines.append("")
    lines.append(
        "**预登记的方向**：卡靠的是文献里的空方腿（高空头兴趣 → 未来收益更低），"
        "所以 `days_to_cover` / `short_interest_ratio` / `dtc_change_vs_prior` / "
        "`dtc_cross_sectional_pct` 对前瞻超额的 IC 应为**负**；显著为正不是支持，是反驳。"
        "`staleness_days` 是日历负对照，没有预期方向。"
    )
    lines.append("")
    lines.append("## 全表（每列 × 每标签）")
    lines.append("")
    lines.append(
        "| 因子 | 标签 | 预期符号 | 全样本 IC | ICIR | t | n | 近窗 IC | 近窗 t | "
        "2018-20 | 2021-23 | 2024-26 | 符号稳定性(3 窗) | 符号稳定性(逐年) | "
        "方向符合卡 | FDR | 近窗 FDR |"
    )
    lines.append("|---|---|:-:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:-:|:-:|:-:|")
    for _, row in screen.iterrows():
        expected = {1: "+", -1: "−", 0: "n/a"}[int(row["expected_sign"])]
        lines.append(
            f"| `{row['factor']}` | {row['label']} | {expected} | {row['ic_mean_full']:+.4f} | "
            f"{row['icir_full']:+.3f} | {row['t_full']:+.2f} | {int(row['n_full'])} | "
            f"{row['ic_mean_recent']:+.4f} | {row['t_recent']:+.2f} | "
            f"{row['ic_mean_2018_2020']:+.4f} | {row['ic_mean_2021_2023']:+.4f} | "
            f"{row['ic_mean_2024_2026']:+.4f} | {row['sign_stability_windows']:.2f} | "
            f"{row['sign_stability_years']:.2f} | "
            f"{'是' if row['supports_card'] else '否'} | "
            f"{'是' if row['fdr_pass'] else '否'} | {'是' if row['fdr_pass_recent'] else '否'} |"
        )
    lines.append("")
    lines.append("## 每列的覆盖率与自相关（为什么 t 的 n 比看起来弱）")
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
    lines.append(
        "底层数据每月只更新两次，所以周度秩自相关接近 1 是**结构性的**："
        "相邻周的 IC 不是独立观测，上表的 t 统计量因此系统性偏大。"
        f"若按「每个结算周期只算一次」折算，独立观测数约为 {meta['independent_cycles']} 个"
        f"（而不是 n = {meta['max_n_full']}），这一点在读显著性时必须扣掉。"
    )
    lines.append("")
    lines.append(f"标签近似核对：{meta['label_rank_vs_excess_note']}")
    lines.append("")
    lines.append("## 门控列（卡的 avoid 条件建立在这一列上）")
    lines.append("")
    lines.append("| 门控列 | 标签 | 全样本 t | 近窗 t | 3 窗符号稳定性 | 方向符合卡 | 判据 |")
    lines.append("|---|---|---:|---:|---:|:-:|:-:|")
    for item in meta["gate_column_verdicts"]:
        lines.append(
            f"| `{item['factor']}` | {item['label']} | {item['t_full']:+.2f} | "
            f"{item['t_recent']:+.2f} | {item['sign_stability_windows']:.2f} | "
            f"{'是' if item['supports_card'] else '否'} | {item['verdict']} |"
        )
    lines.append("")
    lines.append(
        "判据的读法：`PASS` = 这一列在近窗 |t| ≥ 2 **或** 3 窗符号稳定性 ≥ 0.7，"
        "**且**方向与卡一致；否则 `FAIL`（筛选器层面没有可用信号）。"
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--feature-root", type=Path, default=SHORT_INTEREST_ROOT)
    parser.add_argument(
        "--out-suffix",
        default="",
        help=(
            "Suffix for the output and checkpoint names, e.g. '-placebo20260916'. "
            "Required whenever --feature-root is a placebo root: without it a "
            "placebo run would overwrite the real screen's outputs and its "
            "checkpoints, and a later reader could not tell them apart."
        ),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    suffix = args.out_suffix
    if args.feature_root != SHORT_INTEREST_ROOT and not suffix:
        raise SystemExit(
            "--feature-root points at a non-default (placebo) root; pass --out-suffix "
            "so the placebo screen cannot overwrite the real one"
        )
    out_parquet = OUT_PARQUET.with_name(f"screen{suffix}.parquet")
    out_json = OUT_JSON.with_name(f"screen{suffix}.json")
    out_md = OUT_MD.with_name(f"screen{suffix}.md")
    checkpoint_dir = CHECKPOINT_DIR.with_name(f"screen_checkpoints{suffix}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    universe_panel = load_universe_panel(UNIVERSE_ROOT)
    _log(f"universe panel: {len(universe_panel):,} rows")

    ic_accumulators: dict[tuple[str, str], _Accumulator] = defaultdict(_Accumulator)
    counters: dict[str, _Counter] = defaultdict(_Counter)
    total_rows = 0
    all_dates: list[pd.Timestamp] = []
    for year in ALL_YEARS:
        checkpoint = checkpoint_dir / f"{year}.parquet"
        if checkpoint.exists() and not args.force:
            frame = pd.read_parquet(checkpoint)
            _log(f"{year}: loaded checkpoint ({len(frame):,} records)")
        else:
            started = time.monotonic()
            frame, rows = _process_year(year, args.feature_root, universe_panel)
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

    paired = screen.set_index(["factor", "label"])
    gaps = [
        abs(
            float(paired.loc[(factor, "label_rank_5"), "ic_mean_full"])
            - float(paired.loc[(factor, "label_excess_5"), "ic_mean_full"])
        )
        for factor in SHORT_INTEREST_COLUMNS
        if (factor, "label_rank_5") in paired.index and (factor, "label_excess_5") in paired.index
    ]
    rank_gap = float(np.max(gaps)) if gaps else float("nan")

    gate_verdicts = []
    for label in LABEL_COLUMNS:
        subset = screen.loc[(screen["factor"] == GATE_COLUMN) & (screen["label"] == label)]
        if subset.empty:
            continue
        row = subset.iloc[0]
        strong = abs(row["t_recent"]) >= 2.0 or row["sign_stability_windows"] >= 0.7
        gate_verdicts.append(
            {
                "factor": GATE_COLUMN,
                "label": label,
                "t_full": float(row["t_full"]),
                "t_recent": float(row["t_recent"]),
                "sign_stability_windows": float(row["sign_stability_windows"]),
                "supports_card": bool(row["supports_card"]),
                "verdict": "PASS" if (strong and bool(row["supports_card"])) else "FAIL",
            }
        )

    directional = screen.loc[screen["expected_sign"] != 0]
    max_n_full = int(screen["n_full"].max()) if len(screen) else 0
    meta = {
        "hypothesis": "H-20260916-07",
        "step": 2,
        "card": ("reports/research/hypotheses/H-20260916-07-finra-short-interest-avoid-list.md"),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "feature_root": str(args.feature_root),
        "protocol": (
            "own preregistration (this script's module docstring); deliberately NOT merged "
            "into scripts/screen_factors.py's 506-test count nor "
            "scripts/screen_insider_factors.py's 39-test count"
        ),
        "universe_top_n": UNIVERSE_TOP_N,
        "years": list(ALL_YEARS),
        "labels": list(LABEL_COLUMNS),
        "n_factors": len(SHORT_INTEREST_COLUMNS),
        "n_labels": len(LABEL_COLUMNS),
        "n_tests": int(len(screen)),
        "fdr_q": FDR_Q,
        "n_fdr_pass": int(screen["fdr_pass"].sum()),
        "n_fdr_pass_recent": int(screen["fdr_pass_recent"].sum()),
        "n_supports_card": int(directional["supports_card"].sum()),
        "n_directional_tests": int(len(directional)),
        "expected_sign": EXPECTED_SIGN,
        "weekly_dates": len(weekly_dates),
        "first_date": weekly_dates[0].date().isoformat() if weekly_dates else None,
        "last_date": weekly_dates[-1].date().isoformat() if weekly_dates else None,
        "rows": int(total_rows),
        "recent_window_start": RECENT_START.date().isoformat(),
        "sub_windows": [{"name": n, "start": s, "end": e} for n, s, e in SUB_WINDOWS],
        "max_n_full": max_n_full,
        # Two settlement cycles a month: the number of genuinely new
        # cross-sections behind the weekly IC series.
        "independent_cycles": int(round(max_n_full * 24.0 / 52.0)) if max_n_full else 0,
        "gate_column": GATE_COLUMN,
        "gate_column_verdicts": gate_verdicts,
        "label_rank_vs_excess_note": (
            f"`label_rank_5` 与 `label_excess_5` 的全样本 IC 最大差 {rank_gap:.5f}"
            "（两者按定义只差同日单调变换与并列处理，所以它们不是两条独立证据）"
        ),
        "max_abs_ic_gap_rank_vs_excess_5": rank_gap,
    }

    temporary = out_parquet.with_suffix(".parquet.part")
    screen.to_parquet(temporary, index=False)
    temporary.replace(out_parquet)
    out_json.write_text(
        json.dumps(
            {"meta": meta, "table": json.loads(screen.to_json(orient="records"))},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    out_md.write_text(_render_markdown(screen, meta), encoding="utf-8")
    _log(
        f"wrote {out_parquet.name}, {out_json.name}, {out_md.name}: "
        f"{meta['n_tests']} tests, {meta['n_fdr_pass']} pass full-sample BH, "
        f"{meta['n_fdr_pass_recent']} pass recent BH, "
        f"{meta['n_supports_card']}/{meta['n_directional_tests']} in the card's direction"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
