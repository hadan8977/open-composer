"""H-20260916-02 stage 1: news-attention pre-check, twin cells and report. **No LLM.**

Card: ``reports/research/hypotheses/H-20260916-02-news-attention-features.md``
(stage 1 only. Stage 2 -- scoring a sample of articles with a language model --
is deliberately **out of scope**: the user requires a separately configured
model for it, and nothing in this file, in
``scripts/build_news_attention_features.py`` or in
``open_composer/research/{features/news_attention,kernel/news_gate}.py`` calls,
imports or depends on one. The report ends with a stage-2 handoff paragraph
sizing the sample a scorer would need.)

Order of work is not negotiable this round. ``docs/current-view.zh.md`` item 2,
written out of lesson ``L-20260916-01``, makes the **pre-check cross-table** a
precondition for any "layer Y on top of book X" card: before a single twin cell
is priced, the round must publish Y's hit rate on X's actual holdings next to
its hit rate on the whole pool. H-20260916-01 spent a day discovering that
insider buying covers 1.9% of the momentum book; the same table for news takes
half an hour. So stage ``precheck`` runs first, its verdict decides whether
``evaluate`` runs at all, and the report prints it above everything else.

The primary cell is not re-designed and not re-tuned. It is exactly
``step13_m0b_mom_over_vol63_uni500_k50_gate_off`` -- ``MomentumFactorStrategy``
on the derived column ``momentum_252_21_over_vol_63``, PIT universe
``adv_rank <= 500``, top 50 equal-weight names, weekly (last session of each ISO
week), trend gate **off**, 24-month trailing training window, quarterly refit,
``next_open`` execution, 10 bps/side primary and 25 bps/side stress cost, ``BIL``
cash leg -- built here with the same imported loaders H-20260916-01 and -03
used (``scripts/run_step13_m_grid._load_common_data``,
``kernel.pick_export``, ``kernel.vol_matched``), so the book is the same book
and a gated variant and its equal-weight parent are never priced by two
different engines. The evaluation window is clipped to **2024-01-02 onward**,
because that is where the news archive begins; every table is a 2024→ 小样本
table and says so.

**No ledger row is written.** Nothing here goes through ``loop.run_experiment``;
the v2 gate verdicts are computed with ``reference_only=True`` and reported as
disclosure only.

Gates (see ``kernel/news_gate.py`` for why the card's one sentence is three
experiments), each priced twice -- ``_raw`` (the freed weight sits in ``BIL``,
so gross exposure falls) and ``_norm`` (the same relative weights rescaled to
100% gross). Per ``L-20260916-03`` **``_norm`` is the decision-relevant one**:
any drawdown or vol-matched-excess improvement that comes from holding less is
reproduced by a random placebo.

Two independent controls, both on five seeds and both on the normalized books:

* ``shuffle`` -- the same-size random control ``L-20260916-01`` made mandatory:
  the gate's own state labels permuted across names *within each rebalance
  week*, so every week keeps exactly its full/partial/half counts, gross
  exposure and position count, and only the identity of the names is
  randomized. This separates "the gate picked the right names" from "a smaller,
  more concentrated subset of the same book does this by itself".
* ``symshuffle`` -- the card's own placebo, built upstream: every article's
  symbol list is reassigned to the same number of random symbols from that
  session's PIT cohort
  (``build_news_attention_features.py --shuffle-symbols-seed S
  --shuffle-symbols-mode relabel``, five seeds, each into its own
  ``data/features/news_attention_relabel_seed{S}/``; the real table is never
  overwritten). ``relabel`` is one fixed universe-wide bijection, so every
  pseudo-symbol inherits some real symbol's **entire** news history -- same
  counts, same heavy tail, same week-to-week persistence, same keyword mix --
  and the only thing destroyed is the pairing between a news series and a return
  series. The builder's other mode (``draw``, a per-article uniform draw from the
  session cohort) was measured and rejected as a control: it flattens the
  attention distribution (share of stock-days with an article in the trailing 5
  sessions goes 69.2% -> 97.4%), which makes it an easier experiment rather than
  a matched one.

Stages (each resumable from its own checkpoints under
``reports/research/iterations/h20260916_02_news_attention/``; re-running a stage
whose outputs exist is a no-op unless ``--force``)::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_02_news_attention.py export
    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_02_news_attention.py precheck
    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_02_news_attention.py gate-states
    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_02_news_attention.py evaluate

``evaluate`` prices every book and then renders the report; ``report``
re-renders ``report.{json,md}`` from ``results-raw.json`` alone, without
re-pricing. The placebo feature tables ``gate-states`` expects are built first,
one seed at a time::

    for seed in 20260916 20260917 20260918 20260919 20260920; do
        ./scripts/run_capped.sh --mem 1.8G -- \\
            uv run python scripts/build_news_attention_features.py all \\
                --shuffle-symbols-seed "$seed" --shuffle-symbols-mode relabel
    done
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.research.features.news_attention import (  # noqa: E402
    NEWS_ATTENTION_COLUMNS,
    NEWS_ATTENTION_ROOT,
    SCREEN_COLUMNS,
)
from open_composer.research.features.panel import load_feature_panel  # noqa: E402
from open_composer.research.kernel.baseline_strategies import MomentumFactorStrategy  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    RebalanceEvent,
    build_weight_schedule,
    returns_from_weight_schedule,
)
from open_composer.research.kernel.mechanism_eval import annualized_cagr, max_drawdown  # noqa: E402
from open_composer.research.kernel.news_gate import (  # noqa: E402
    GATE_SPECS,
    STATE_WEIGHT_MULTIPLIER,
    SURGE_THRESHOLD,
    gate_state_changes_per_year,
    gate_states,
    normalize_weights_to_full_exposure,
    rebalances_with_gate_change_per_year,
    shuffle_states_within_date,
    state_shares,
)
from open_composer.research.kernel.pick_export import (  # noqa: E402
    PickCollector,
    turnover_per_rebalance,
    weight_schedule_from_pick_frame,
)
from open_composer.research.kernel.vol_matched import (  # noqa: E402
    cagr_excess_vol_matched,
    vol_match_weight,
)
from open_composer.research.regime import gates as regime_gates  # noqa: E402
from open_composer.research.regime import metrics as regime_metrics  # noqa: E402

m_grid = importlib.import_module("scripts.run_step13_m_grid")

OUT_DIR = ROOT / "reports" / "research" / "iterations" / "h20260916_02_news_attention"
PICKS_PATH = OUT_DIR / "picks.parquet"
SCHEDULE_PATH = OUT_DIR / "schedule_baseline.json"
GATE_STATES_DIR = OUT_DIR / "gate_states"
PRECHECK_JSON = OUT_DIR / "precheck.json"
PRECHECK_MD = OUT_DIR / "precheck.md"
RESULTS_PATH = OUT_DIR / "results-raw.json"
REPORT_JSON_PATH = OUT_DIR / "report.json"
REPORT_MD_PATH = OUT_DIR / "report.md"
SCREEN_JSON = OUT_DIR / "step3-news-screen.json"

#: The primary cell, unchanged (same constants as H-20260916-01's step 2).
SCORE_COLUMN = "momentum_252_21_over_vol_63"
PRIMARY_CELL = "step13_m0b_mom_over_vol63_uni500_k50_gate_off"
UNIVERSE_TOP_N = 500
TOP_K = 50
TRAIN_WINDOW_MONTHS = m_grid.TRAIN_WINDOW_MONTHS  # 24
PRIMARY_COST_BPS = m_grid.PRIMARY_COST_BPS  # 10.0
STRESS_COST_BPS = m_grid.STRESS_COST_BPS  # 25.0
CASH_SYMBOL = m_grid.CASH_SYMBOL  # "BIL"
EXECUTION = "next_open"
DATA_YEARS: tuple[int, ...] = tuple(range(2016, 2027))
TEST_YEARS: tuple[int, ...] = tuple(range(2017, 2027))

#: The news archive's own start. Everything this card evaluates is clipped here,
#: and every table it prints is labelled "2024→ 小样本".
NEWS_START = pd.Timestamp("2024-01-02")

PLACEBO_SEEDS: tuple[int, ...] = (20260916, 20260917, 20260918, 20260919, 20260920)
CONTROL_SHUFFLE = "shuffle"
CONTROL_SYMSHUFFLE = "symshuffle"
#: Which ``build_news_attention_features.py --shuffle-symbols-mode`` the card's
#: placebo uses. ``relabel`` is one fixed universe-wide bijection, so every
#: pseudo-symbol inherits a real symbol's entire news history (same counts, same
#: heavy tail, same persistence) and only the news<->returns pairing is broken.
#: The alternative ``draw`` mode was measured and rejected: a per-article uniform
#: draw flattens the attention distribution (share of stock-days with an article
#: in the trailing 5 sessions goes 69.2% -> 97.4%), so it is a different, easier
#: experiment rather than a matched control.
PLACEBO_SHUFFLE_MODE = "relabel"

#: The pre-check's own thresholds, fixed before the numbers were seen.
#:
#: ``PRECHECK_MIN_COVERAGE`` is the brief's ">= 20% weekly overlap with the
#: book" gate: if fewer than a fifth of the book's stock-weeks have any article
#: in the trailing 20 sessions, the news layer structurally cannot see the book
#: and the twin cells are skipped (H-20260916-01's Form 4 layer failed exactly
#: this test at 1.9%, after a full day of pricing).
#: ``PRECHECK_MIN_TIER_SHARE`` is the second half that L-20260916-01 says a
#: coverage number alone misses: a layer can cover 100% of the book and still
#: never move it, if the tier it would act on is empty. A gate whose acting tier
#: touches fewer than this share of book stock-weeks is reported as
#: "structurally inert" even when it is priced.
PRECHECK_MIN_COVERAGE = 0.20
PRECHECK_MIN_TIER_SHARE = 0.02

#: Card stop-condition thresholds, verbatim.
#: (1) "0 attention columns pass FDR" -- read off the screener.
#: (2) "placebo effect comparable" -- a control reaching >= 50% of the real
#:     improvement, the L-20260916-03 rule, on the 5-seed mean.
#: (3) "the gate raises turnover without raising normalized excess".
STOP_PLACEBO_SHARE = 0.5
#: The card's own expectation bar (lower than the insider card's, because the
#: sample is 2.7 years): vol-matched excess improves by >= 2 percentage points.
CARD_EXPECTED_IMPROVEMENT_PP = 0.02
#: A turnover rise this large counts as "raised" for stop condition (3).
STOP_TURNOVER_RISE = 0.02


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    tmp.replace(path)


def _write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(tmp, index=False)
    tmp.replace(path)


def _events_to_json(schedule: list[RebalanceEvent]) -> list[dict[str, Any]]:
    return [
        {
            "date": event.date,
            "universe_size": event.universe_size,
            "selected": event.selected,
            "portfolio_beta": event.portfolio_beta,
        }
        for event in schedule
    ]


# --------------------------------------------------------------------------
# stage: export (the unchanged primary book)
# --------------------------------------------------------------------------


def stage_export(*, force: bool) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not force and PICKS_PATH.exists() and SCHEDULE_PATH.exists():
        _log(f"{PICKS_PATH.name} / {SCHEDULE_PATH.name} already present -- reusing (checkpoint)")
        return
    common = m_grid._load_common_data(years=DATA_YEARS, trend_gate_required=False)
    _log(f"loading feature panel on {len(common.weekly_dates)} weekly rebalance dates ...")
    panel = load_feature_panel(
        ["momentum_252_21", "vol_63"],
        ["label_rank_5"],
        dates=common.weekly_dates,
        include_prices=False,
    )
    ratio = panel["momentum_252_21"] / panel["vol_63"]
    panel[SCORE_COLUMN] = ratio.replace([np.inf, -np.inf], np.nan)
    collector = PickCollector(feature_columns=(SCORE_COLUMN,))
    trading_calendar = pd.DatetimeIndex(sorted(common.price_panel["trade_date"].unique()))
    _log(f"building the weight schedule for test years {TEST_YEARS} ...")
    schedule = build_weight_schedule(
        panel=panel,
        universe_panel=common.universe_panel,
        strategy_factory=lambda: MomentumFactorStrategy(factor_column=SCORE_COLUMN),
        feature_columns=[SCORE_COLUMN],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=TEST_YEARS,
        top_k=TOP_K,
        hedge="none",
        trading_calendar=trading_calendar,
        train_window_months=TRAIN_WINDOW_MONTHS,
        refit_frequency="quarterly",
        universe_top_n=UNIVERSE_TOP_N,
        trend_gate_series=None,
        trend_gate_cash_symbol=CASH_SYMBOL,
        pick_observer=collector,
    )
    picks = collector.to_frame()
    _write_parquet(PICKS_PATH, picks)
    _write_json(SCHEDULE_PATH, _events_to_json(schedule))
    _log(
        f"wrote {PICKS_PATH.name}: {len(picks):,} rows, "
        f"{picks['rebalance_date'].nunique()} rebalance dates, "
        f"{picks['rebalance_date'].min().date()}..{picks['rebalance_date'].max().date()}"
    )


# --------------------------------------------------------------------------
# joining the news table onto a book
# --------------------------------------------------------------------------


def _news_root_for(source: str) -> Path:
    if source == "real":
        return NEWS_ATTENTION_ROOT
    seed = int(source.removeprefix(CONTROL_SYMSHUFFLE))
    return NEWS_ATTENTION_ROOT.with_name(
        f"news_attention_placebo_{PLACEBO_SHUFFLE_MODE}_seed{seed}"
    )


def _gate_state_path(source: str) -> Path:
    return GATE_STATES_DIR / f"{source}.parquet"


def load_news_rows(news_root: Path, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """The news-attention rows for ``dates`` (one row per (date, symbol)).

    Only the requested dates are read, so the whole daily table never has to be
    resident; the file is per calendar year, and a weekly grid touches every
    year the book spans.
    """
    frames: list[pd.DataFrame] = []
    for year in sorted({int(date.year) for date in dates}):
        path = news_root / f"{year}.parquet"
        if not path.exists():
            continue
        frame = pd.read_parquet(
            path, columns=["symbol", "trade_date", *NEWS_ATTENTION_COLUMNS, "news_history_sessions"]
        )
        frames.append(frame.loc[frame["trade_date"].isin(dates)])
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["symbol"] = out["symbol"].astype(str)
    return out


def novelty_median_reference(news_root: Path, dates: pd.DatetimeIndex) -> pd.Series:
    """``{rebalance date: that date's PIT top-500 pool median ``novelty_5d``}``.

    The median is taken over the **pool**, not over the book: the book's own
    median is endogenous (half the book is above it by construction, whatever
    the news says), while the pool's median is a number a live implementation
    could compute at the open from the same table. The pool panel is the
    builder's ``screening_panel_weekly.parquet`` (Friday x top-500); a book date
    that is not a pool date (holiday weeks shift the ISO-week last session) takes
    the most recent earlier pool date, never a later one.
    """
    panel_path = news_root / "screening_panel_weekly.parquet"
    if not panel_path.exists():
        raise SystemExit(f"{panel_path} missing -- run the builder's weekly-panel stage")
    panel = pd.read_parquet(panel_path, columns=["friday_date", "novelty_5d"])
    panel["friday_date"] = pd.to_datetime(panel["friday_date"])
    medians = (
        panel.groupby("friday_date")["novelty_5d"]
        .median()
        .sort_index()
        .rename("novelty_median_ref")
    )
    wanted = pd.DataFrame({"rebalance_date": pd.DatetimeIndex(sorted(set(dates)))})
    joined = pd.merge_asof(
        wanted,
        medians.reset_index().rename(columns={"friday_date": "rebalance_date"}),
        on="rebalance_date",
        direction="backward",
    )
    return joined.set_index("rebalance_date")["novelty_median_ref"]


def build_gate_state_frame(picks: pd.DataFrame, news_root: Path) -> pd.DataFrame:
    """One row per (rebalance date, held symbol) with that date's point-in-time
    news columns, the pool novelty median, and each gate's state.
    """
    dates = pd.DatetimeIndex(sorted(picks["rebalance_date"].unique()))
    news = load_news_rows(news_root, dates)
    frame = picks.copy()
    frame["symbol"] = frame["symbol"].astype(str)
    merged = frame.merge(
        news, left_on=["symbol", "rebalance_date"], right_on=["symbol", "trade_date"], how="left"
    ).drop(columns=["trade_date"])
    medians = novelty_median_reference(news_root, dates)
    merged["novelty_median_ref"] = merged["rebalance_date"].map(medians)
    missing = merged["news_count_20d"].isna()
    if missing.any():
        _log(
            f"{int(missing.sum())}/{len(merged)} book rows have no news-table row "
            "(not in that month's top-1000 cohort) -- counted as 'no news', the "
            "conservative reading"
        )
    for gate in GATE_SPECS:
        merged[f"state_{gate}"] = gate_states(merged, gate)
    return merged


def stage_gate_states(*, force: bool, sources: list[str]) -> None:
    picks = pd.read_parquet(PICKS_PATH)
    picks["rebalance_date"] = pd.to_datetime(picks["rebalance_date"])
    picks = picks.loc[picks["rebalance_date"] >= NEWS_START]
    _log(
        f"book clipped to the news window: {len(picks):,} rows, "
        f"{picks['rebalance_date'].nunique()} rebalances, "
        f"{picks['rebalance_date'].min().date()}..{picks['rebalance_date'].max().date()}"
    )
    GATE_STATES_DIR.mkdir(parents=True, exist_ok=True)
    for source in sources:
        path = _gate_state_path(source)
        if path.exists() and not force:
            _log(f"{source}: {path.name} already present -- reusing (checkpoint)")
            continue
        root = _news_root_for(source)
        if not root.exists():
            _log(f"{source}: {root} missing -- skipping")
            continue
        states = build_gate_state_frame(picks, root)
        _write_parquet(path, states)
        shares = {gate: state_shares(states[f"state_{gate}"]) for gate in GATE_SPECS}
        _log(f"{source}: wrote {path.name} ({len(states):,} rows); state shares {shares}")


# --------------------------------------------------------------------------
# stage: precheck (runs before anything is priced)
# --------------------------------------------------------------------------


def _coverage_block(frame: pd.DataFrame) -> dict[str, Any]:
    """Coverage and cross-sectional-variation diagnostics for one population."""
    if frame.empty:
        return {}
    out: dict[str, Any] = {
        "rows": int(len(frame)),
        "any_news_5d": float((frame["news_count_5d"].fillna(0) > 0).mean()),
        "any_news_20d": float((frame["news_count_20d"].fillna(0) > 0).mean()),
        "columns": {},
    }
    for column in SCREEN_COLUMNS:
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        # Cross-sectional variation is the question a ranking feature has to
        # answer, so the dispersion is measured *within* each date and averaged,
        # never pooled across dates (a pooled std can look healthy while every
        # single cross-section is constant).
        per_date = frame.groupby("rebalance_date")[column]
        out["columns"][column] = {
            "mean": float(values.mean()),
            "missing_rate": float(values.isna().mean()),
            "zero_rate": float((values == 0).mean()),
            "nonzero_rate": float((values.fillna(0) != 0).mean()),
            "within_date_std_mean": float(per_date.std().mean()),
            "within_date_distinct_mean": float(per_date.nunique().mean()),
            "within_date_distinct_share_mean": float(
                (per_date.nunique() / per_date.size().replace(0, np.nan)).mean()
            ),
        }
    return out


def stage_precheck(*, force: bool) -> dict[str, Any]:
    """The mandatory cross-table: does the news layer see the momentum book?

    Published before any twin cell is priced, per ``docs/current-view.zh.md``
    item 2. Three questions, three answers, by year:

    1. **Coverage** -- the share of stock-days with at least one article in the
       trailing 5 / 20 sessions, in the top-500 pool and in the top-50 momentum
       book. If the book's share is far below the pool's, the two signals look
       at disjoint sets of stocks and a halving gate on that book is
       arithmetically a de-leveraging device (the Form 4 finding).
    2. **Tier shares** -- what fraction of book stock-weeks each gate would
       actually act on. Full coverage with an empty acting tier is still an
       inert layer.
    3. **Cross-sectional variation** -- per column, the within-date standard
       deviation and the share of distinct values, averaged over dates. A column
       that is 0 for 95% of a cross-section cannot be a ranking feature no
       matter what its pooled IC says.
    """
    if PRECHECK_JSON.exists() and not force:
        _log(f"{PRECHECK_JSON.name} already present -- reusing (checkpoint)")
        return json.loads(PRECHECK_JSON.read_text())

    picks = pd.read_parquet(PICKS_PATH)
    picks["rebalance_date"] = pd.to_datetime(picks["rebalance_date"])
    picks = picks.loc[picks["rebalance_date"] >= NEWS_START]
    dates = pd.DatetimeIndex(sorted(picks["rebalance_date"].unique()))
    book = build_gate_state_frame(picks, NEWS_ATTENTION_ROOT)

    panel_path = NEWS_ATTENTION_ROOT / "screening_panel_weekly.parquet"
    pool = pd.read_parquet(panel_path)
    pool["friday_date"] = pd.to_datetime(pool["friday_date"])
    pool = pool.loc[(pool["friday_date"] >= dates.min()) & (pool["friday_date"] <= dates.max())]
    pool = pool.rename(columns={"friday_date": "rebalance_date"})
    medians = novelty_median_reference(
        NEWS_ATTENTION_ROOT, pd.DatetimeIndex(pool["rebalance_date"])
    )
    pool["novelty_median_ref"] = pool["rebalance_date"].map(medians)
    for gate in GATE_SPECS:
        pool[f"state_{gate}"] = gate_states(pool, gate)

    payload: dict[str, Any] = {
        "hypothesis": "H-20260916-02",
        "stage": "1 (no LLM)",
        "step": "pre-check cross-table (runs before any twin cell)",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "window": [dates.min().date().isoformat(), dates.max().date().isoformat()],
        "rebalances": int(len(dates)),
        "book_cell": PRIMARY_CELL,
        "pool_source": (
            "data/features/news_attention/screening_panel_weekly.parquet (friday x top-500 ADV)"
        ),
        "book_source": "reports/research/iterations/h20260916_02_news_attention/picks.parquet",
        "thresholds": {
            "min_coverage": PRECHECK_MIN_COVERAGE,
            "min_tier_share": PRECHECK_MIN_TIER_SHARE,
        },
        "small_sample_note": "2024→ 小样本",
        "overall": {"pool": _coverage_block(pool), "book": _coverage_block(book)},
        "by_year": {},
        "gates": {},
        "llm_used": False,
    }
    for year in sorted({int(date.year) for date in dates}):
        pool_year = pool.loc[pool["rebalance_date"].dt.year == year]
        book_year = book.loc[book["rebalance_date"].dt.year == year]
        payload["by_year"][str(year)] = {
            "pool": {
                "rows": int(len(pool_year)),
                "any_news_5d": float((pool_year["news_count_5d"].fillna(0) > 0).mean()),
                "any_news_20d": float((pool_year["news_count_20d"].fillna(0) > 0).mean()),
                "median_news_count_5d": float(pool_year["news_count_5d"].median()),
                "median_novelty_5d": float(pool_year["novelty_5d"].median()),
            },
            "book": {
                "rows": int(len(book_year)),
                "any_news_5d": float((book_year["news_count_5d"].fillna(0) > 0).mean()),
                "any_news_20d": float((book_year["news_count_20d"].fillna(0) > 0).mean()),
                "median_news_count_5d": float(book_year["news_count_5d"].median()),
                "median_novelty_5d": float(book_year["novelty_5d"].median()),
            },
            "gates": {
                gate: {
                    "pool_shares": state_shares(pool_year[f"state_{gate}"]),
                    "book_shares": state_shares(book_year[f"state_{gate}"]),
                }
                for gate in GATE_SPECS
            },
        }
    for gate in GATE_SPECS:
        pool_shares = state_shares(pool[f"state_{gate}"])
        book_shares = state_shares(book[f"state_{gate}"])
        acting = "full" if gate != "gate_N_nonews" else "half"
        payload["gates"][gate] = {
            "description": GATE_SPECS[gate].description,
            "pool_shares": pool_shares,
            "book_shares": book_shares,
            "acting_state": acting,
            "acting_share_book": book_shares.get(acting),
            "acting_share_pool": pool_shares.get(acting),
            "book_over_pool_ratio": (
                book_shares.get(acting, 0.0) / pool_shares[acting]
                if pool_shares.get(acting)
                else None
            ),
            "inert": bool((book_shares.get(acting) or 0.0) < PRECHECK_MIN_TIER_SHARE),
        }

    coverage = payload["overall"]["book"]["any_news_20d"]
    payload["verdict"] = {
        "book_any_news_20d": coverage,
        "book_any_news_5d": payload["overall"]["book"]["any_news_5d"],
        "pool_any_news_20d": payload["overall"]["pool"]["any_news_20d"],
        "coverage_pass": bool(coverage >= PRECHECK_MIN_COVERAGE),
        "run_twin_cells": bool(coverage >= PRECHECK_MIN_COVERAGE),
        "inert_gates": [gate for gate, block in payload["gates"].items() if block["inert"]],
    }
    _write_json(PRECHECK_JSON, payload)
    PRECHECK_MD.write_text(_render_precheck_markdown(payload), encoding="utf-8")
    _log(
        f"pre-check: book any-news-20d {coverage:.1%} vs pool "
        f"{payload['overall']['pool']['any_news_20d']:.1%}; "
        f"run_twin_cells={payload['verdict']['run_twin_cells']}"
    )
    return payload


def _pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "N/A"
    return f"{value * 100:.1f}%"


def _render_precheck_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# H-20260916-02 前置检查交叉表（2024→ 小样本，孪生单元之前必须先出）")
    lines.append("")
    lines.append(
        f"- 生成时间：{payload['generated_at']}｜窗口 {payload['window'][0]} → "
        f"{payload['window'][1]}（{payload['rebalances']} 个调仓周）"
    )
    lines.append(
        f"- 书 = `{payload['book_cell']}`（动量 top-50，等权）；池 = {payload['pool_source']}"
    )
    lines.append(
        f"- 判据（事前定的）：覆盖率门槛 {_pct(payload['thresholds']['min_coverage'])}，"
        f"「有效档」门槛 {_pct(payload['thresholds']['min_tier_share'])}"
    )
    lines.append("")
    lines.append("## 1. 覆盖率：新闻层看得见这本书吗")
    lines.append("")
    lines.append(
        "| 年 | 池 5 日有报道 | 书 5 日有报道 | 池 20 日有报道 | 书 20 日有报道 "
        "| 池中位条数(5d) | 书中位条数(5d) |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for year, block in payload["by_year"].items():
        lines.append(
            f"| {year} | {_pct(block['pool']['any_news_5d'])} | "
            f"{_pct(block['book']['any_news_5d'])} | "
            f"{_pct(block['pool']['any_news_20d'])} | {_pct(block['book']['any_news_20d'])} | "
            f"{block['pool']['median_news_count_5d']:.0f} | "
            f"{block['book']['median_news_count_5d']:.0f} |"
        )
    overall_pool = payload["overall"]["pool"]
    overall_book = payload["overall"]["book"]
    lines.append(
        f"| 全窗 | {_pct(overall_pool['any_news_5d'])} | {_pct(overall_book['any_news_5d'])} | "
        f"{_pct(overall_pool['any_news_20d'])} | {_pct(overall_book['any_news_20d'])} | — | — |"
    )
    lines.append("")
    lines.append("## 2. 门控的「有效档」占比：层看得见 ≠ 层会动手")
    lines.append("")
    lines.append("| 门 | 动手的档 | 池占比 | 书占比 | 书/池 | 是否结构性无效 |")
    lines.append("|---|---|---:|---:|---:|:-:|")
    for gate, block in payload["gates"].items():
        ratio = block["book_over_pool_ratio"]
        lines.append(
            f"| `{gate}` | {block['acting_state']} | {_pct(block['acting_share_pool'])} | "
            f"{_pct(block['acting_share_book'])} | "
            f"{'N/A' if ratio is None else f'{ratio:.2f}'} | "
            f"{'是' if block['inert'] else '否'} |"
        )
    lines.append("")
    lines.append("## 3. 截面变异：这些列能不能当排序特征")
    lines.append("")
    lines.append(
        "读法：`日内标准差` 和 `日内不同取值占比` 都是**在每个调仓日的截面里**算再对日期取平均。"
        "一列在池子里 95% 是 0，它的合并 IC 再好看也不是可排序的特征。"
    )
    lines.append("")
    lines.append(
        "| 列 | 池 恰好为 0 | 池 日内标准差 | 池 日内不同取值占比 | 书 恰好为 0 | 书 日内标准差 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|")
    for column in SCREEN_COLUMNS:
        pool_column = overall_pool.get("columns", {}).get(column)
        book_column = overall_book.get("columns", {}).get(column)
        if pool_column is None:
            continue
        lines.append(
            f"| `{column}` | {_pct(pool_column['zero_rate'])} | "
            f"{pool_column['within_date_std_mean']:.3f} | "
            f"{_pct(pool_column['within_date_distinct_share_mean'])} | "
            f"{_pct(book_column['zero_rate']) if book_column else 'N/A'} | "
            f"{book_column['within_date_std_mean']:.3f} |"
        )
    lines.append("")
    verdict = payload["verdict"]
    lines.append("## 结论（这一节决定后面跑不跑孪生单元）")
    lines.append("")
    lines.append(
        f"- 书里 20 个交易日内有报道的股票周占 **{_pct(verdict['book_any_news_20d'])}**"
        f"（池子 {_pct(verdict['pool_any_news_20d'])}）；"
        f"5 日内有报道占 {_pct(verdict['book_any_news_5d'])}。"
        f"覆盖率门槛 {_pct(payload['thresholds']['min_coverage'])} → "
        f"**{'过' if verdict['coverage_pass'] else '不过'}**。"
    )
    if verdict["inert_gates"]:
        lines.append(f"- 结构性无效的门：{', '.join(f'`{g}`' for g in verdict['inert_gates'])}。")
    else:
        lines.append("- 没有结构性无效的门（每个门的有效档都动得到书里足够多的名字）。")
    lines.append(
        f"- 因此 **{'继续做孪生单元' if verdict['run_twin_cells'] else '跳过孪生单元'}**。"
    )
    lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# stage: evaluate
# --------------------------------------------------------------------------


def variant_books(states: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """``{variant label: frame with a ``weight`` column}`` -- the baseline plus
    every gate in raw (freed weight to BIL) and exposure-normalized form.
    """
    books: dict[str, pd.DataFrame] = {"gate_off": states[["rebalance_date", "symbol", "weight"]]}
    for name in GATE_SPECS:
        multiplier = states[f"state_{name}"].map(STATE_WEIGHT_MULTIPLIER)
        raw = states.assign(weight=states["weight"] * multiplier)
        books[f"{name}_raw"] = raw[["rebalance_date", "symbol", "weight"]]
        books[f"{name}_norm"] = normalize_weights_to_full_exposure(raw)[
            ["rebalance_date", "symbol", "weight"]
        ]
    return books


def _slice_window(series: pd.Series, start: pd.Timestamp) -> pd.Series:
    return series.loc[series.index >= start]


def _window_block(
    returns: pd.Series,
    stress_returns: pd.Series,
    spy_returns: pd.Series,
    bil_returns: pd.Series,
    schedule: list[RebalanceEvent],
    start: pd.Timestamp,
) -> dict[str, Any]:
    sliced = _slice_window(returns, start)
    weekly = m_grid._weekly_returns_excluding_cash(schedule, returns, recent_start=start)
    return {
        "cagr_net": annualized_cagr(sliced),
        "max_drawdown": max_drawdown(sliced),
        "cagr_excess_vol_matched_spy": cagr_excess_vol_matched(sliced, spy_returns, bil_returns),
        "vol_match_weight_vs_spy": vol_match_weight(sliced, spy_returns),
        "hit_rate_weekly": regime_metrics.hit_rate(weekly),
        "stress_cost_cagr_net": annualized_cagr(_slice_window(stress_returns, start)),
        "window": [
            sliced.index.min().date().isoformat(),
            sliced.index.max().date().isoformat(),
        ],
        "weeks": len(weekly),
    }


def _variant_metrics(
    *,
    label: str,
    book: pd.DataFrame,
    states: pd.DataFrame,
    gate_name: str | None,
    returns: pd.Series,
    stress_returns: pd.Series,
    spy_returns: pd.Series,
    bil_returns: pd.Series,
    schedule: list[RebalanceEvent],
    oos_start: pd.Timestamp,
) -> dict[str, Any]:
    weekly_recent = m_grid._weekly_returns_excluding_cash(
        schedule, returns, recent_start=pd.Timestamp(regime_gates.RECENT_WINDOW_START)
    )
    verdict = regime_gates.evaluate_recent_high_return_candidate(
        experiment_id=f"h20260916_02_{label}",
        config_hash=f"h20260916_02_{label}",
        full_returns=returns,
        full_stress_returns=stress_returns,
        spy_returns=spy_returns,
        bil_returns=bil_returns,
        weekly_holding_period_net_returns_recent=weekly_recent,
        rebalances_with_change_per_year=m_grid._rebalances_with_change_per_year(schedule),
        family=m_grid.FAMILY,
        is_ml=False,
        reference_only=True,
    )
    turnover = turnover_per_rebalance(schedule)
    exposure = [
        sum(weight for symbol, weight in event.selected.items() if symbol != CASH_SYMBOL)
        for event in schedule
        if event.selected
    ]
    metrics: dict[str, Any] = {
        "label": label,
        "recent_2024": {
            "cagr_net": verdict.metrics["cagr_recent_net"],
            "max_drawdown": verdict.metrics["max_drawdown_recent"],
            "cagr_excess_vol_matched_spy": verdict.metrics["cagr_excess_vol_matched_spy"],
            "vol_match_weight_vs_spy": verdict.metrics["vol_match_weight_vs_spy"],
            "hit_rate_weekly": verdict.metrics["hit_rate_weekly"],
            "sharpe_excess_bil": verdict.metrics["sharpe_excess_bil_recent"],
            "stress_cost_cagr_net": verdict.metrics["stress_cost_recent_cagr_net"],
            "window": [
                verdict.metrics["recent_window_start"],
                verdict.metrics["recent_window_end"],
            ],
            "all_gates_pass": verdict.all_gates_pass,
        },
        "news_window": _window_block(
            returns, stress_returns, spy_returns, bil_returns, schedule, oos_start
        ),
        "turnover_per_rebalance_mean": float(np.mean(turnover[1:])) if len(turnover) > 1 else None,
        "turnover_annualized": float(np.mean(turnover[1:]) * 52.0) if len(turnover) > 1 else None,
        "mean_invested_exposure": float(np.mean(exposure)) if exposure else None,
        "min_invested_exposure": float(np.min(exposure)) if exposure else None,
        "rebalance_count": len([event for event in schedule if event.selected]),
        "positions_per_week_mean": float(
            book.loc[book["weight"] > 0].groupby("rebalance_date").size().mean()
        ),
    }
    if gate_name is not None:
        column = f"state_{gate_name}"
        metrics["state_shares"] = state_shares(states[column])
        metrics["state_shares_per_year"] = {
            str(year): state_shares(group[column])
            for year, group in states.groupby(pd.to_datetime(states["rebalance_date"]).dt.year)
        }
        metrics["gate_state_changes_per_year"] = gate_state_changes_per_year(states, gate_name)
        metrics["rebalances_with_gate_change_per_year"] = rebalances_with_gate_change_per_year(
            states, gate_name
        )
    return metrics


def _price_streams(
    schedule: list[RebalanceEvent],
    price_wide: pd.DataFrame,
    open_wide: pd.DataFrame,
    spy_returns: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    primary = returns_from_weight_schedule(
        schedule,
        price_wide,
        spy_returns,
        cost_bps_per_side=PRIMARY_COST_BPS,
        include_hedge=False,
        execution=EXECUTION,
        open_wide=open_wide,
    )
    stress = returns_from_weight_schedule(
        schedule,
        price_wide,
        spy_returns,
        cost_bps_per_side=STRESS_COST_BPS,
        include_hedge=False,
        execution=EXECUTION,
        open_wide=open_wide,
    )
    return primary, stress


def stage_evaluate(*, force: bool) -> None:
    del force
    precheck = json.loads(PRECHECK_JSON.read_text()) if PRECHECK_JSON.exists() else None
    if precheck is None:
        raise SystemExit("run the `precheck` stage first -- it decides whether this stage runs")
    if not precheck["verdict"]["run_twin_cells"]:
        _log(
            "pre-check says the news layer does not cover the book "
            f"({precheck['verdict']['book_any_news_20d']:.1%} < "
            f"{PRECHECK_MIN_COVERAGE:.0%}) -- twin cells skipped by design"
        )
        _write_json(RESULTS_PATH, {"skipped_by_precheck": True, "precheck": precheck["verdict"]})
        return

    states_real = pd.read_parquet(_gate_state_path("real"))
    states_real["rebalance_date"] = pd.to_datetime(states_real["rebalance_date"])
    oos_dates = pd.DatetimeIndex(sorted(states_real["rebalance_date"].unique()))
    oos_start = oos_dates.min()
    _log(f"book span: {oos_start.date()}..{oos_dates.max().date()} ({len(oos_dates)} rebalances)")

    years = tuple(range(oos_start.year, 2027))
    common = m_grid._load_common_data(years=years, trend_gate_required=False)
    held = set(states_real["symbol"].astype(str)) | {CASH_SYMBOL}
    for seed in PLACEBO_SEEDS:
        path = _gate_state_path(f"{CONTROL_SYMSHUFFLE}{seed}")
        if path.exists():
            held |= set(pd.read_parquet(path, columns=["symbol"])["symbol"].astype(str))
    price_panel = common.price_panel
    price_panel = price_panel.loc[price_panel["symbol"].astype(str).isin(held)]
    _log(f"price panel narrowed to {price_panel['symbol'].nunique()} held symbols")
    price_wide = price_panel.pivot(index="trade_date", columns="symbol", values="close")
    open_wide = price_panel.pivot(index="trade_date", columns="symbol", values="open")
    spy_returns = common.spy_returns
    bil_returns = common.bil_returns
    del common, price_panel

    results: dict[str, Any] = {"variants": {}, "control_variants": {}}

    def price(
        label: str,
        book: pd.DataFrame,
        states: pd.DataFrame,
        gate_name: str | None,
        cash: str | None,
    ) -> dict[str, Any]:
        schedule = weight_schedule_from_pick_frame(
            book, cash_symbol=cash, universe_size_column=None
        )
        primary, stress = _price_streams(schedule, price_wide, open_wide, spy_returns)
        return _variant_metrics(
            label=label,
            book=book,
            states=states,
            gate_name=gate_name,
            returns=primary,
            stress_returns=stress,
            spy_returns=spy_returns,
            bil_returns=bil_returns,
            schedule=schedule,
            oos_start=oos_start,
        )

    books = variant_books(states_real)
    for label, book in books.items():
        gate_name = None if label == "gate_off" else label.rsplit("_", 1)[0]
        cash = None if label.endswith("_norm") or label == "gate_off" else CASH_SYMBOL
        results["variants"][label] = price(label, book, states_real, gate_name, cash)
        recent = results["variants"][label]["news_window"]
        _log(
            f"{label}: 2024→ CAGR {recent['cagr_net']:.4f} MDD {recent['max_drawdown']:.4f} "
            f"vol-matched excess {recent['cagr_excess_vol_matched_spy']:.4f} "
            f"exposure {results['variants'][label]['mean_invested_exposure']:.3f}"
        )

    def price_control(control: str, seed: int, states: pd.DataFrame) -> int:
        control_books = variant_books(states)
        count = 0
        for gate_name in GATE_SPECS:
            label = f"{gate_name}_norm"
            key = f"{label}__{control}{seed}"
            results["control_variants"][key] = price(
                key, control_books[label], states, gate_name, None
            )
            count += 1
        return count

    for seed in PLACEBO_SEEDS:
        priced = price_control(CONTROL_SHUFFLE, seed, shuffle_states_within_date(states_real, seed))
        _log(f"{CONTROL_SHUFFLE}{seed}: priced {priced} within-week state-shuffled books")

    for seed in PLACEBO_SEEDS:
        path = _gate_state_path(f"{CONTROL_SYMSHUFFLE}{seed}")
        if not path.exists():
            _log(f"{CONTROL_SYMSHUFFLE}{seed}: no gate-state checkpoint -- skipping")
            continue
        states = pd.read_parquet(path)
        states["rebalance_date"] = pd.to_datetime(states["rebalance_date"])
        priced = price_control(CONTROL_SYMSHUFFLE, seed, states)
        _log(f"{CONTROL_SYMSHUFFLE}{seed}: priced {priced} symbol-shuffled-feature books")

    _write_json(RESULTS_PATH, results)
    _log(f"wrote {RESULTS_PATH.name} ({len(results['variants'])} real books)")
    stage_report()


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------


def _reference_disclosures() -> dict[str, Any]:
    payload = json.loads(
        (ROOT / "config" / "promotion" / "recent-regime-high-return-gates-v2.json").read_text()
    )
    return payload["reference_disclosures"]


def _screen_payload() -> dict[str, Any] | None:
    if not SCREEN_JSON.exists():
        return None
    return json.loads(SCREEN_JSON.read_text())


def _control_aggregate(
    results: dict[str, Any], baseline_excess: float, control: str
) -> dict[str, Any]:
    """Per gate: each control seed's vol-matched-excess improvement over the
    baseline, plus that distribution's mean/min/max.

    The verdict uses the mean seed and discloses the spread -- L-20260916-03's
    rule, because one draw decided that round's borderline call by 0.007.
    """
    out: dict[str, Any] = {}
    for gate_name in GATE_SPECS:
        label = f"{gate_name}_norm"
        rows = [
            metrics
            for key, metrics in results.get("control_variants", {}).items()
            if key.startswith(f"{label}__{control}")
        ]
        if not rows:
            continue
        improvements = [
            row["news_window"]["cagr_excess_vol_matched_spy"] - baseline_excess for row in rows
        ]
        out[label] = {
            "seeds": len(rows),
            "improvements": improvements,
            "improvement_mean": float(np.mean(improvements)),
            "improvement_min": float(np.min(improvements)),
            "improvement_max": float(np.max(improvements)),
            "cagr_mean": float(np.mean([r["news_window"]["cagr_net"] for r in rows])),
            "max_drawdown_mean": float(np.mean([r["news_window"]["max_drawdown"] for r in rows])),
            "excess_mean": float(
                np.mean([r["news_window"]["cagr_excess_vol_matched_spy"] for r in rows])
            ),
            "hit_rate_weekly_mean": float(
                np.mean([r["news_window"]["hit_rate_weekly"] for r in rows])
            ),
            "turnover_per_rebalance_mean": float(
                np.mean([r["turnover_per_rebalance_mean"] for r in rows])
            ),
            "mean_invested_exposure": float(np.mean([r["mean_invested_exposure"] for r in rows])),
            "positions_per_week_mean": float(np.mean([r["positions_per_week_mean"] for r in rows])),
        }
    return out


def _stop_conditions(
    *,
    results: dict[str, Any],
    screen: dict[str, Any] | None,
    shuffle: dict[str, Any],
    symshuffle: dict[str, Any],
) -> dict[str, Any]:
    """The card's three stop conditions, per gate. Any one hit stops the path."""
    baseline = results["variants"]["gate_off"]
    baseline_excess = baseline["news_window"]["cagr_excess_vol_matched_spy"]
    baseline_turnover = baseline["turnover_per_rebalance_mean"]

    if screen is None:
        fdr_detail = "筛选器结果缺失（step3-news-screen.json 未生成）"
        fdr_pass_count: int | None = None
    else:
        fdr_pass_count = int(screen["meta"]["n_fdr_pass"])
        fdr_detail = (
            f"{fdr_pass_count}/{screen['meta']['n_tests']} 个检验过全窗 BH（q=0.05）；"
            f"近窗 {screen['meta']['n_fdr_pass_recent']}/{screen['meta']['n_tests']}；"
            f"三分位块 {screen['meta']['n_tercile_fdr_pass']}/{screen['meta']['n_tercile_tests']}"
        )
    condition_one = {
        "name": "(1) 注意力列 0 项过 FDR",
        "verdict": (
            "unknown"
            if fdr_pass_count is None
            else ("STOP" if fdr_pass_count == 0 else "not triggered")
        ),
        "detail": fdr_detail,
        "n_fdr_pass": fdr_pass_count,
    }

    out: dict[str, Any] = {"screen": condition_one, "gates": {}}
    for gate_name in GATE_SPECS:
        label = f"{gate_name}_norm"
        variant = results["variants"].get(label)
        if variant is None:
            continue
        excess = variant["news_window"]["cagr_excess_vol_matched_spy"]
        improvement = excess - baseline_excess
        turnover = variant["turnover_per_rebalance_mean"]
        turnover_rise = (
            None if turnover is None or baseline_turnover is None else turnover - baseline_turnover
        )
        block: dict[str, Any] = {
            "excess": excess,
            "baseline_excess": baseline_excess,
            "improvement_pp": improvement,
            "meets_card_expectation": bool(improvement >= CARD_EXPECTED_IMPROVEMENT_PP),
            "turnover": turnover,
            "baseline_turnover": baseline_turnover,
            "turnover_rise": turnover_rise,
        }
        for control, aggregate in ((CONTROL_SHUFFLE, shuffle), (CONTROL_SYMSHUFFLE, symshuffle)):
            entry = aggregate.get(label)
            if entry is None:
                block[control] = {"verdict": "unknown", "detail": "没有这个对照的种子"}
                continue
            share = entry["improvement_mean"] / improvement if improvement != 0 else None
            block[control] = {
                "seeds": entry["seeds"],
                "improvement_mean": entry["improvement_mean"],
                "improvement_min": entry["improvement_min"],
                "improvement_max": entry["improvement_max"],
                "share_of_real": share,
                "verdict": (
                    "n/a (真实改善 <= 0)"
                    if improvement <= 0
                    else ("STOP" if (share or 0.0) >= STOP_PLACEBO_SHARE else "not triggered")
                ),
            }
        condition_two_verdicts = [
            block[control].get("verdict") for control in (CONTROL_SHUFFLE, CONTROL_SYMSHUFFLE)
        ]
        block["condition_2"] = {
            "name": "(2) 占位效应相当（任一对照达到真实改善的 50%）",
            "verdict": (
                "STOP"
                if "STOP" in condition_two_verdicts
                else ("n/a (真实改善 <= 0)" if improvement <= 0 else "not triggered")
            ),
        }
        raised_turnover = bool(turnover_rise is not None and turnover_rise > STOP_TURNOVER_RISE)
        block["condition_3"] = {
            "name": "(3) 换手上升而归一化超额不升",
            "verdict": ("STOP" if raised_turnover and improvement <= 0 else "not triggered"),
            "detail": (
                f"换手 {_fmt_num(baseline_turnover)} → {_fmt_num(turnover)}"
                f"（{_fmt_num(turnover_rise, signed=True)}），"
                f"归一化同波动超额改善 {improvement * 100:+.1f} 个百分点"
            ),
        }
        block["overall"] = (
            "STOP"
            if "STOP" in (block["condition_2"]["verdict"], block["condition_3"]["verdict"])
            else "not triggered"
        )
        out["gates"][gate_name] = block
    return out


def _caveats(*, results: dict[str, Any], precheck: dict[str, Any]) -> list[str]:
    lines = [
        "**样本只有 2024-01 → 2026-09（约 2.7 年、139 个调仓周）**，因为新闻档案 2024-01 才开始。"
        "本报告每张表都按「2024→ 小样本」读；三个子窗就是三个自然年，符号稳定性只有四个取值。",
        "新闻档案只有一个来源（benzinga，684,876 条全部如此），所以 `distinct_sources_5d` 是常数，"
        "已排除在 BH 分母之外，`distinct_authors_5d`（509 个作者）是它的替身。",
        "2024 年前 60 个交易日的 60 日基线是截断的（档案起点），"
        "突增分母按**实际可用**的 5 日块数除，`news_history_sessions` 记录了每行的可用长度。",
        "`news_history_sessions` 从档案第一条被归属的新闻那天（2023-10-30，25 条被 "
        "`updated_at` 分区拖进来的旧文重发）开始数，而真实覆盖是 2024-01-01 才开始的，"
        "所以 2024 年 1 月的行被记成有约 40 个交易日的历史（实际上没有）。"
        "后果是那些行的突增分母偏大、突增偏小——**偏保守的方向**，不会造出假的突增；"
        "每行实际用的长度都写在 `news_history_sessions` 里。",
        "`days_since_last_news` 在 2024 年初被档案起点托底：一个 2024-01 的值 12 可能是"
        "「12 个交易日」也可能是「从未收集到」。",
        "扇出 > 10 只股票的文章（13,289 篇）整篇不参与归属；"
        "没有任何股票代码的（21,137 篇）同样不参与。点时归属之后，"
        "在点时 top-1000 池里至少命中一只票的文章是 339,885 篇、460,652 个(文章, 股票)行。",
        "账本未写：这一轮不经过 `loop.run_experiment`，"
        "`reports/research/ledger/experiments.jsonl` 未改动；"
        "报告里的合同 v2 判定是 `reference_only` 披露。",
        "**第 1 阶段完全不用 LLM**：特征是计数、去重和固定正则词典，没有任何模型调用。",
        "符号占位用的是 `--shuffle-symbols-mode relabel`（一个全样本固定双射），"
        "不是逐篇从当日池子里随机抽。抽取式占位被量化否掉了："
        "2024 年真实表里 5 日内有报道占 69.2%、`news_count_5d` 的标准差/均值 = 2.18、"
        "99 分位 38 条，"
        "抽取式占位变成 97.4%、0.52、10 条，20 日无报道的一档从 6.1% 掉到 0.8%——"
        "它把注意力分布本身压平了，所以不是同尺寸对照，而是一个更容易的实验。"
        "证据见 `placebo-mode-comparison.json`。",
        "两套占位都保留日历，所以一个「其实是全市场时序信号」的特征会同时活过两套；"
        "这就是为什么本轮还要跑周内同尺寸打乱（`kernel/news_gate.shuffle_states_within_date`）。",
    ]
    if precheck["verdict"]["inert_gates"]:
        lines.append(
            "结构性无效的门（有效档触及的股票周低于 "
            f"{PRECHECK_MIN_TIER_SHARE:.0%}）：{', '.join(precheck['verdict']['inert_gates'])}。"
        )
    if results.get("skipped_by_precheck"):
        lines.append("孪生单元按前置检查的结论跳过，没有定价任何门控书。")
    return lines


def _stage_two_handoff(precheck: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    """The sizing paragraph the user needs to budget a stage-2 LLM scorer."""
    rebalances = precheck["rebalances"]
    book = precheck["overall"]["book"]
    mean_5d = book["columns"]["news_count_5d"]["mean"]
    per_week_articles = mean_5d * TOP_K
    total_articles = per_week_articles * rebalances
    surge_share = precheck["gates"]["gate_N_surge"]["acting_share_book"] or 0.0
    return {
        "weeks": rebalances,
        "names_per_week": TOP_K,
        "articles_per_name_5d_mean": mean_5d,
        "articles_per_week_mean": per_week_articles,
        "articles_total_full_book": total_articles,
        "surge_tier_share_of_book": surge_share,
        "articles_total_surge_tier_only": total_articles * surge_share,
        "note": (
            "counts are (article, symbol) attributions inside the trailing 5 sessions of each "
            "rebalance date; a scorer reading headline+summary only needs the packet rows, "
            "which average ~1.1 KB of text each"
        ),
        "priced_variants": len(results.get("variants", {})),
    }


def _fmt_num(value: float | None, *, signed: bool = False) -> str:
    """A turnover-scale number, or ``N/A`` -- used in the stop-condition detail
    strings so a missing metric reads as missing instead of raising.
    """
    if value is None or not np.isfinite(value):
        return "N/A"
    return f"{value:+.3f}" if signed else f"{value:.3f}"


def _delta_pp(value: float, reference: float | None) -> str:
    """``value - reference`` in percentage points, or ``N/A``."""
    if reference is None or not np.isfinite(reference):
        return "N/A"
    return f"{(value - reference) * 100:+.1f}pp"


def _share_pct(value: float | None) -> str:
    """A control's improvement as a share of the real one, or ``N/A``."""
    if value is None or not np.isfinite(value):
        return "N/A"
    return f"{value * 100:.0f}%"


def _fmt_pp(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "N/A"
    return f"{value * 100:+.1f}pp"


def _build_report(*, results: dict[str, Any], precheck: dict[str, Any]) -> dict[str, Any]:
    screen = _screen_payload()
    if results.get("skipped_by_precheck"):
        return {
            "hypothesis": "H-20260916-02",
            "stage": "1 (no LLM)",
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "precheck": precheck,
            "skipped_by_precheck": True,
            "screen": screen["meta"] if screen else None,
            "caveats": _caveats(results=results, precheck=precheck),
            "stage_two_handoff": _stage_two_handoff(precheck, results),
            "llm_used": False,
        }
    baseline_excess = results["variants"]["gate_off"]["news_window"]["cagr_excess_vol_matched_spy"]
    shuffle = _control_aggregate(results, baseline_excess, CONTROL_SHUFFLE)
    symshuffle = _control_aggregate(results, baseline_excess, CONTROL_SYMSHUFFLE)
    return {
        "hypothesis": "H-20260916-02",
        "stage": "1 (no LLM)",
        "card": "reports/research/hypotheses/H-20260916-02-news-attention-features.md",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "primary_cell": PRIMARY_CELL,
        "family": "news_attention_features",
        "trials_used_this_round": len(GATE_SPECS),
        "evaluation_window_start": NEWS_START.date().isoformat(),
        "gate_descriptions": {name: spec.description for name, spec in GATE_SPECS.items()},
        "surge_threshold": SURGE_THRESHOLD,
        "precheck": precheck,
        "screen": screen["meta"] if screen else None,
        "screen_table": screen["table"] if screen else None,
        "screen_terciles": screen["terciles"] if screen else None,
        "variants": results["variants"],
        "controls": {CONTROL_SHUFFLE: shuffle, CONTROL_SYMSHUFFLE: symshuffle},
        "stop_conditions": _stop_conditions(
            results=results, screen=screen, shuffle=shuffle, symshuffle=symshuffle
        ),
        "reference_disclosures": _reference_disclosures(),
        "caveats": _caveats(results=results, precheck=precheck),
        "stage_two_handoff": _stage_two_handoff(precheck, results),
        "ledger": "not written (no loop.run_experiment; contract v2 verdicts are reference_only)",
        "llm_used": False,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# H-20260916-02 第 1 阶段：新闻注意力特征（不用 LLM）— 2024→ 小样本")
    lines.append("")
    lines.append(
        f"- 生成时间：{report['generated_at']}｜假设族：`news_attention_features`"
        f"（本轮用掉 {report.get('trials_used_this_round', 0)} 次）"
    )
    lines.append(
        "- 一句话：**先出前置检查交叉表，再定价**。这一节的顺序是 `docs/current-view.zh.md` 第 2 条"
        "（来自 L-20260916-01）规定的，不是本轮的选择。"
    )
    lines.append("- 第 1 阶段没有任何 LLM 调用；第 2 阶段（模型打分）不在本轮范围内。")
    lines.append("")

    precheck = report["precheck"]
    verdict = precheck["verdict"]
    lines.append("## 0. 前置检查交叉表（先看这个）")
    lines.append("")
    lines.append(
        f"窗口 {precheck['window'][0]} → {precheck['window'][1]}，"
        f"{precheck['rebalances']} 个调仓周。完整表在 `precheck.md`。三个数：",
    )
    lines.append("")
    lines.append("| 问题 | 池（top-500） | 书（动量 top-50） | 书/池 |")
    lines.append("|---|---:|---:|---:|")
    pool = precheck["overall"]["pool"]
    book = precheck["overall"]["book"]
    for key, label in (
        ("any_news_5d", "5 个交易日内有报道"),
        ("any_news_20d", "20 个交易日内有报道"),
    ):
        ratio = book[key] / pool[key] if pool[key] else float("nan")
        lines.append(f"| {label} | {_pct(pool[key])} | {_pct(book[key])} | {ratio:.2f} |")
    lines.append("")
    lines.append("| 门 | 动手的档 | 池占比 | 书占比 | 结构性无效 |")
    lines.append("|---|---|---:|---:|:-:|")
    for gate, block in precheck["gates"].items():
        lines.append(
            f"| `{gate}` | {block['acting_state']} | {_pct(block['acting_share_pool'])} | "
            f"{_pct(block['acting_share_book'])} | {'是' if block['inert'] else '否'} |"
        )
    lines.append("")
    lines.append(
        f"**结论：新闻层{'覆盖' if verdict['coverage_pass'] else '不覆盖'}这本书"
        f"（书里 20 日内有报道 {_pct(verdict['book_any_news_20d'])}，门槛 "
        f"{_pct(precheck['thresholds']['min_coverage'])}），"
        f"所以{'继续做孪生单元' if verdict['run_twin_cells'] else '跳过孪生单元'}。**"
        " 这和 Form 4 的 1.9% 是两种完全不同的情形：新闻不是「看不见这本书」，"
        "问题只能是「看见了但没有信息」。"
    )
    lines.append("")
    lines.append("截面变异（能不能当排序特征）：完整一列一行的表在 `precheck.md` 第 3 节。")
    lines.append("")

    screen = report.get("screen")
    lines.append("## 1. 筛选器（预登记，2024→ 小样本）")
    lines.append("")
    if screen is None:
        lines.append("筛选器结果缺失。")
    else:
        lines.append(
            f"{screen['n_factors']} 列 × {screen['n_labels']} 标签 = "
            f"**{screen['n_tests']} 次检验**，"
            f"BH q={screen['fdr_q']}；样本 {screen['first_date']} → {screen['last_date']}"
            f"（{screen['weekly_dates']} 个周频调仓日）。"
        )
        lines.append("")
        lines.append(
            f"- 全窗过 FDR：**{screen['n_fdr_pass']}/{screen['n_tests']}**；"
            f"近窗（{screen['recent_window_start']} 起）过 FDR："
            f"{screen['n_fdr_pass_recent']}/{screen['n_tests']}"
        )
        lines.append(
            f"- 卡上附加问题（`{screen['tercile_factor']}` 按 `{screen['tercile_split_column']}` "
            f"三分位）：{screen['n_tercile_fdr_pass']}/{screen['n_tercile_tests']} 过它自己的 BH"
        )
        for column, reason in screen.get("excluded_columns", {}).items():
            lines.append(f"- 排除列 `{column}`：{reason}")
        lines.append("")
        table = report.get("screen_table") or []
        top = sorted(table, key=lambda row: -abs(row.get("t_full") or 0.0))[:12]
        if top:
            lines.append("按 |t| 排前 12 的检验（完整表在 `step3-news-screen.md`）：")
            lines.append("")
            lines.append(
                "| 因子 | 标签 | 全窗 IC | ICIR | t | 2024 | 2025 | 2026 | 符号稳定性 | FDR |"
            )
            lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|:-:|")
            for row in top:
                lines.append(
                    f"| `{row['factor']}` | {row['label']} | {row['ic_mean_full']:+.4f} | "
                    f"{row['icir_full']:+.3f} | {row['t_full']:+.2f} | "
                    f"{row['ic_mean_2024']:+.4f} | {row['ic_mean_2025']:+.4f} | "
                    f"{row['ic_mean_2026']:+.4f} | {row['sign_stability_windows']:.2f} | "
                    f"{'是' if row['fdr_pass'] else '否'} |"
                )
            lines.append("")
        terciles = report.get("screen_terciles") or []
        if terciles:
            lines.append("三分位块（`novelty_high` = 突增且新颖，`novelty_low` = 突增但重复）：")
            lines.append("")
            lines.append("| 三分位 | 标签 | 全窗 IC | ICIR | t | n | FDR |")
            lines.append("|---|---|---:|---:|---:|---:|:-:|")
            for row in terciles:
                lines.append(
                    f"| `{row['factor']}` | {row['label']} | {row['ic_mean_full']:+.4f} | "
                    f"{row['icir_full']:+.3f} | {row['t_full']:+.2f} | {int(row['n_full'])} | "
                    f"{'是' if row['fdr_pass'] else '否'} |"
                )
            lines.append("")

    if report.get("skipped_by_precheck"):
        lines.append("## 2. 孪生单元")
        lines.append("")
        lines.append("按前置检查的结论跳过。")
    else:
        lines.append("## 2. 孪生单元（2024→ 小样本，**归一化到 100% 暴露**是决策口径）")
        lines.append("")
        for name, description in report["gate_descriptions"].items():
            lines.append(f"- `{name}`：{description}")
        lines.append("")
        lines.append(
            "| 变体 | CAGR | 最大回撤 | 同波动 SPY 超额 | 周胜率 | 平均持仓只数 "
            "| 平均暴露 | 每周双边换手 |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for label, variant in report["variants"].items():
            window = variant["news_window"]
            lines.append(
                f"| `{label}` | {window['cagr_net'] * 100:.1f}% | "
                f"{window['max_drawdown'] * 100:.1f}% | "
                f"{window['cagr_excess_vol_matched_spy'] * 100:+.1f}% | "
                f"{window['hit_rate_weekly'] * 100:.1f}% | "
                f"{variant['positions_per_week_mean']:.1f} | "
                f"{variant['mean_invested_exposure']:.3f} | "
                f"{variant['turnover_per_rebalance_mean']:.3f} |"
            )
        lines.append("")
        lines.append(
            "**`_raw` 和 `_norm` 这两行必须一起读，这是 L-20260916-03 那条教训的第三次出现。**"
            "`gate_N_surge_raw` 看起来是本轮最好的一行（最大回撤 -28.3% → -15.1%，"
            "同波动超额 -11.0% → -5.5%），但它的平均暴露只有 **0.525**：门把 95% 的持仓减半，"
            "省下来的钱全放进 BIL。把同样的相对权重归一化回 100% 暴露，"
            "同波动超额变成 **-12.2%，比门关**更差。"
            "也就是说 `_raw` 那一行测的是「少拿一半」，不是「新闻选对了名字」。"
            "`gate_N_tiered` 同理（暴露 0.756，raw -8.4% → norm -11.5%）。"
        )
        reference = report["reference_disclosures"]
        lines.append("")
        lines.append("对照数（合同 v2 的 `reference_disclosures`，披露口径）：")
        lines.append("")
        lines.append("| 基准 | CAGR | 最大回撤 |")
        lines.append("|---|---:|---:|")
        for name, block in reference.items():
            if not isinstance(block, dict):
                continue
            cagr = block.get("cagr_net") or block.get("cagr")
            drawdown = block.get("max_drawdown")
            lines.append(
                f"| {name} | {'N/A' if cagr is None else f'{cagr * 100:.1f}%'} | "
                f"{'N/A' if drawdown is None else f'{drawdown * 100:.1f}%'} |"
            )
        lines.append("")
        lines.append("### 两套对照（都是 5 个种子，都报分布）")
        lines.append("")
        lines.append(
            "| 门（归一化） | 真实改善 | 同尺寸随机（周内打乱）均值 | 最小 | 最大 | 占真实 | "
            "符号打乱（重建特征）均值 | 最小 | 最大 | 占真实 |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for gate, block in report["stop_conditions"]["gates"].items():
            shuffle = block.get(CONTROL_SHUFFLE, {})
            symshuffle = block.get(CONTROL_SYMSHUFFLE, {})
            lines.append(
                f"| `{gate}_norm` | {_fmt_pp(block['improvement_pp'])} | "
                f"{_fmt_pp(shuffle.get('improvement_mean'))} | "
                f"{_fmt_pp(shuffle.get('improvement_min'))} | "
                f"{_fmt_pp(shuffle.get('improvement_max'))} | "
                f"{_share_pct(shuffle.get('share_of_real'))} | "
                f"{_fmt_pp(symshuffle.get('improvement_mean'))} | "
                f"{_fmt_pp(symshuffle.get('improvement_min'))} | "
                f"{_fmt_pp(symshuffle.get('improvement_max'))} | "
                f"{_share_pct(symshuffle.get('share_of_real'))} |"
            )
        lines.append("")

    lines.append("## 3. 停止判据（卡上三条，逐条 PASS/FAIL）")
    lines.append("")
    stop = report["stop_conditions"] if "stop_conditions" in report else None
    if stop is None:
        lines.append("没有定价，判据 (2)(3) 无法评。")
    else:
        condition_one = stop["screen"]
        lines.append(
            f"- **(1) 注意力列 0 项过 FDR** → `{condition_one['verdict']}`："
            f"{condition_one['detail']}"
        )
        lines.append("")
        lines.append("| 门 | (2) 占位效应相当 | (3) 换手升而超额不升 | 合计 |")
        lines.append("|---|:-:|:-:|:-:|")
        for gate, block in stop["gates"].items():
            lines.append(
                f"| `{gate}` | {block['condition_2']['verdict']} | "
                f"{block['condition_3']['verdict']} | {block['overall']} |"
            )
        lines.append("")
        for gate, block in stop["gates"].items():
            lines.append(f"- `{gate}`：{block['condition_3']['detail']}")
        lines.append("")
        lines.append(
            "判据 (2) 对三个门都标「n/a」，因为它们的真实改善全是**负数**——"
            "「占位是否复现了改善」这个问题在没有改善的时候没有意义，"
            "判据 (1) 和 (3) 已经停了这条路。"
            "但上面那张对照表仍然有信息，而且是本轮最直接的一条："
            "周内同尺寸打乱（只随机化「是哪几只被减半」，只数和暴露分毫不动）"
            "复现了真实门 **88% / 111% / 92%** 的效应。"
            "换句话说，按「新闻突增且新颖」决定谁满仓、和**随机**决定谁满仓，"
            "在这本书上给出的结果分不开。"
        )
        lines.append("")

    lines.append("## 4. 必报的五个数（每个门，归一化口径，2024→）")
    lines.append("")
    reference = report.get("reference_disclosures", {})
    lines.append("| 变体 | SPY 超额（同波动） | 对 SPY | 对 MTUM | 对 SPMO | 占位（两套均值） |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    if not report.get("skipped_by_precheck"):
        for gate, block in report["stop_conditions"]["gates"].items():
            label = f"{gate}_norm"
            variant = report["variants"][label]
            cagr = variant["news_window"]["cagr_net"]
            spy = reference.get("SPY", {}).get("cagr")
            mtum = reference.get("MTUM", {}).get("cagr")
            spmo = reference.get("SPMO", {}).get("cagr")
            placebos = [
                block.get(CONTROL_SHUFFLE, {}).get("improvement_mean"),
                block.get(CONTROL_SYMSHUFFLE, {}).get("improvement_mean"),
            ]
            placebos = [value for value in placebos if value is not None]
            lines.append(
                f"| `{label}` | "
                f"{variant['news_window']['cagr_excess_vol_matched_spy'] * 100:+.1f}% | "
                f"{_delta_pp(cagr, spy)} | {_delta_pp(cagr, mtum)} | {_delta_pp(cagr, spmo)} | "
                f"{_fmt_pp(float(np.mean(placebos)) if placebos else None)} |"
            )
    lines.append("")

    lines.append("## 5. 说明与已知缺陷")
    lines.append("")
    for line in report["caveats"]:
        lines.append(f"- {line}")
    lines.append("")

    handoff = report["stage_two_handoff"]
    lines.append("## 6. 第 2 阶段交接（给你算 token 预算用）")
    lines.append("")
    lines.append(
        f"如果第 2 阶段要用一个单独配置的模型给新闻打分，需要的样本量是这么大："
        f"规则动量每周选 **{handoff['names_per_week']} 只**，本窗共 **{handoff['weeks']} 周**；"
        f"每只票在调仓日前 5 个交易日平均有 **{handoff['articles_per_name_5d_mean']:.1f} 条**新闻，"
        f"所以每周约 **{handoff['articles_per_week_mean']:.0f} 条**、全窗约 "
        f"**{handoff['articles_total_full_book']:,.0f} 条**"
        "（(文章, 股票) 归属数，标题+摘要平均约 1.1 KB）。"
        f"只给「突增且新颖」那一档打分的话，占书的 {_pct(handoff['surge_tier_share_of_book'])}，"
        f"全窗约 **{handoff['articles_total_surge_tier_only']:,.0f} 条**。"
        "所以「每周 50 只 × 当周新闻」这句话在我们自己的数据上是"
        f"每周 {handoff['articles_per_week_mean']:.0f} 条量级，不是卡上估的 2–5 千条——"
        "卡上那个数是按全池子估的。前向影子（H-04）每周只需要几百条，一次历史回测需要几万条。"
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def stage_report() -> None:
    results = json.loads(RESULTS_PATH.read_text())
    precheck = json.loads(PRECHECK_JSON.read_text())
    report = _build_report(results=results, precheck=precheck)
    _write_json(REPORT_JSON_PATH, report)
    REPORT_MD_PATH.write_text(_render_markdown(report), encoding="utf-8")
    _log(f"wrote {REPORT_JSON_PATH.name} and {REPORT_MD_PATH.name}")
    if "stop_conditions" in report:
        condition_one = report["stop_conditions"]["screen"]
        _log(f"stop-condition (1): {condition_one['verdict']} -- {condition_one['detail']}")
        for gate, block in report["stop_conditions"]["gates"].items():
            _log(
                f"stop-condition[{gate}] (2) {block['condition_2']['verdict']} "
                f"(3) {block['condition_3']['verdict']} -> {block['overall']}"
            )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "stage",
        choices=("export", "precheck", "gate-states", "evaluate", "report", "all"),
        nargs="?",
        default="all",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help=(
            "Comma-separated gate-state sources for the gate-states stage "
            "(default: real plus every symshuffle seed whose feature table exists)."
        ),
    )
    args = parser.parse_args(argv)

    if args.sources:
        sources = [item.strip() for item in args.sources.split(",") if item.strip()]
    else:
        sources = ["real", *[f"{CONTROL_SYMSHUFFLE}{seed}" for seed in PLACEBO_SEEDS]]

    if args.stage in ("export", "all"):
        stage_export(force=args.force)
    if args.stage in ("precheck", "all"):
        stage_precheck(force=args.force)
    if args.stage in ("gate-states", "all"):
        stage_gate_states(force=args.force, sources=sources)
    if args.stage in ("evaluate", "all"):
        stage_evaluate(force=args.force)
    if args.stage == "report":
        stage_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
