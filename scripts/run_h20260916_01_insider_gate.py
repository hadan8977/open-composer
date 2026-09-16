"""H-20260916-01 step 2: Form 4 insider confirmation gate, twin cells on the rule-momentum book.

Card: ``reports/research/hypotheses/H-20260916-01-insider-form4-confirmation-gate.md``
(including its "第 0 步完成后的两处修订" section, which is what defines the gates
below -- the card's original "机会型净买入比例 > 截面中位数" cut was replaced after
step 0 found the strict Cohen-Malloy-Pomorski opportunistic flag covers only
1-3% of stock-days in the top-500 pool).

One-line hypothesis: keep the rule-momentum primary signal exactly as it is,
and let visible Form 4 insider buying decide only *how much* of each weekly
pick to hold (full / half / none), versus today's flat equal weight.

The primary cell is not re-designed and not re-tuned. It is exactly
``step13_m0b_mom_over_vol63_uni500_k50_gate_off``: ``MomentumFactorStrategy``
on the derived column ``momentum_252_21_over_vol_63``, PIT universe
``adv_rank <= 500``, top 50 names, weekly (last session of each ISO week),
equal weight, trend gate **off**, 24-month trailing training window,
quarterly refit, ``next_open`` execution, 10 bps/side primary and 25 bps/side
stress cost, ``BIL`` cash leg. Data loading, universe handling, benchmark
augmentation and regime-table date clipping are **imported** from
``scripts/run_step13_m_grid.py``; the pick export, the schedule rebuild and
the vol-matched excess helper are the ones H-20260916-03 already built
(``kernel.pick_export``, ``kernel.vol_matched``), so a gated book and its
equal-weight parent are never priced by two different engines.

**No ledger row is written.** Nothing here goes through
``loop.run_experiment``; the v2 gate verdicts are computed with
``reference_only=True`` and reported as disclosure only.

Gates (each evaluated both raw and exposure-normalized -- see below):

* ``gate_off``  -- the baseline, equal weight, every pick at full weight.
* ``gate_A`` "any_buy"     -- full weight iff ``open_market_buy_count_60d >= 1``
  **and** ``net_buyers_60d > 0`` at the rebalance date; otherwise half weight.
* ``gate_B`` "cluster"     -- full weight iff ``buyers_60d >= 2``; else half.
* ``gate_C`` "cmp_opportunistic" -- full weight iff
  ``cmp_opportunistic_buy_60d >= 1``; else half.
* ``gate_A_veto`` "veto"   -- weight 0 iff ``open_market_sell_count_60d >= 3``
  **and** ``open_market_buy_count_60d == 0``; else full weight.

Per the card's revision 3 and lesson ``L-20260916-01``'s predecessor
``L-20260916-03``, every gated design is priced twice:

* ``_raw``  -- the card's literal "减半或转 BIL": the freed weight sits in
  ``BIL``, so average gross exposure falls below 100%.
* ``_norm`` -- the same relative weights rescaled to 100% gross with no BIL
  leg. **This is the decision-relevant comparison.** L-20260916-03 showed that
  any "improvement" in drawdown or vol-matched excess that comes from holding
  less is reproduced by a random placebo, because de-leveraging moves every
  risk-adjusted number mechanically. Normalizing removes the leverage channel
  and leaves only the selection channel.

Placebo: the insider features are rebuilt with
``scripts/build_insider_features.py --shift-filing-dates-days 30
--placebo-seed S`` for five seeds (each into its own
``data/features/insider_placebo_shift30_seed{S}/``; the real table is never
overwritten), and gates A and B are re-run on each. Five seeds, not one, is
L-20260916-03's rule: that round's first single-seed placebo ratio missed the
50% line by 0.007, which is noise, not evidence.

Pre-filing check: the literature this card rests on says insider *cluster*
buying's abnormal return is realized **before** the filing becomes public
(+1.61% pre-filing, ~0 on the filing day and the day after --
``reports/research/control/informed-flow-sources-and-strategy-families-2026-09-16.md``
A.5). ``prefiling`` stage measures that directly on our own data: for every
(symbol, visible filing date) pair behind a gate-A "full weight" decision, the
SPY-excess return over the 5 sessions before the visible date versus sessions
+1..+5 and +6..+20 after it. If the effect sits before visibility, the gate
can only ever be a slow confirmation variable, never a "buy what they bought"
signal, and the report has to say so plainly.

Stages (each resumable from its own checkpoints under
``reports/research/iterations/h20260916_01_insider_gate/``; re-running a stage
whose outputs exist is a no-op unless ``--force``)::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_01_insider_gate.py export
    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_01_insider_gate.py gate-states
    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_01_insider_gate.py prefiling
    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_01_insider_gate.py evaluate

``evaluate`` prices every book and then renders the report; ``report`` re-renders
``step2-twin-report.{json,md}`` from ``step2-results-raw.json`` alone, without
re-pricing. The placebo feature tables the ``gate-states`` stage expects are
built first, one seed at a time (each into its own directory; the real table is
never touched)::

    for seed in 20260916 20260917 20260918 20260919 20260920; do
        ./scripts/run_capped.sh --mem 1.8G -- \\
            uv run python scripts/build_insider_features.py \\
                --shift-filing-dates-days 30 --placebo-seed "$seed" \\
                --as-of 2026-09-15 --skip-weekly-panel --force
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

from open_composer.research.features.insider import INSIDER_ROOT  # noqa: E402
from open_composer.research.features.panel import load_feature_panel  # noqa: E402
from open_composer.research.kernel.baseline_strategies import MomentumFactorStrategy  # noqa: E402
from open_composer.research.kernel.insider_gate import (  # noqa: E402
    GATE_SPECS,
    STATE_WEIGHT_MULTIPLIER,
    gate_state_changes_per_year,
    gate_states,
    normalize_weights_to_full_exposure,
    rebalances_with_gate_change_per_year,
    state_shares,
)
from open_composer.research.kernel.loop import (  # noqa: E402
    RebalanceEvent,
    build_weight_schedule,
    returns_from_weight_schedule,
)
from open_composer.research.kernel.mechanism_eval import annualized_cagr, max_drawdown  # noqa: E402
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

OUT_DIR = ROOT / "reports" / "research" / "iterations" / "h20260916_01_insider_gate"
PICKS_PATH = OUT_DIR / "picks.parquet"
SCHEDULE_PATH = OUT_DIR / "schedule_baseline.json"
GATE_STATES_DIR = OUT_DIR / "gate_states"
RESULTS_PATH = OUT_DIR / "step2-results-raw.json"
PREFILING_PATH = OUT_DIR / "step2-prefiling-check.json"
REPORT_JSON_PATH = OUT_DIR / "step2-twin-report.json"
REPORT_MD_PATH = OUT_DIR / "step2-twin-report.md"

#: The primary cell, unchanged.
SCORE_COLUMN = "momentum_252_21_over_vol_63"
PRIMARY_CELL = "step13_m0b_mom_over_vol63_uni500_k50_gate_off"
UNIVERSE_TOP_N = 500
TOP_K = 50
TRAIN_WINDOW_MONTHS = m_grid.TRAIN_WINDOW_MONTHS  # 24
PRIMARY_COST_BPS = m_grid.PRIMARY_COST_BPS  # 10.0
STRESS_COST_BPS = m_grid.STRESS_COST_BPS  # 25.0
CASH_SYMBOL = m_grid.CASH_SYMBOL  # "BIL"
EXECUTION = "next_open"

#: 2016 is warm-up only: ``momentum_252_21`` needs 252 sessions of history and
#: the daily archive starts 2016-01-04, so no 2016 row has a score. Same
#: reasoning (and same values) as H-20260916-03.
DATA_YEARS: tuple[int, ...] = tuple(range(2016, 2027))
TEST_YEARS: tuple[int, ...] = tuple(range(2017, 2027))

#: The window H-20260916-03 reported as its "full OOS". This card needs no
#: training history of its own (the gate is a rule, not a model), so its own
#: full span starts in 2017; this second start date exists only so the two
#: rounds' tables can be read side by side.
H03_COMPARABLE_START = pd.Timestamp("2020-04-01")

PLACEBO_SHIFT_DAYS = 30
PLACEBO_SEEDS: tuple[int, ...] = (20260916, 20260917, 20260918, 20260919, 20260920)
#: Which gates get a control run. The card asks for A and B; every gate gets
#: one anyway, because a gate that clears stop condition (1) without a placebo
#: beside it is exactly the un-falsifiable "improvement" L-20260916-03 was
#: written about, and which gate clears (1) is not knowable before the run.
PLACEBO_GATES: tuple[str, ...] = ("gate_A", "gate_B", "gate_C", "gate_A_veto")

#: Two independent controls, both run on all five seeds:
#:
#: * ``shift`` -- the card's own placebo: every filing's visible date moved by a
#:   per-accession random +-1..30 sessions before the features are rebuilt.
#:   Note its known weakness, disclosed in the report: these are 60-session
#:   rolling counts with a weekly cross-sectional rank autocorrelation of
#:   0.93-0.97, so a <=30-session shift leaves much of the cross-section in
#:   place. It is a weak destroyer for slow columns, which makes a *surviving*
#:   effect weak evidence and a *destroyed* effect strong evidence.
#: * ``shuffle`` -- the missing-by-construction control the shift cannot give:
#:   the gate's own state labels permuted across names *within each rebalance
#:   week*, so every week keeps exactly the same number of full/half/vetoed
#:   names (and therefore exactly the same gross exposure and concentration)
#:   but assigns them at random. This is the only way to separate "the gate
#:   picked the right names" from "holding a smaller, more concentrated random
#:   subset of the same book does this by itself". Normalized books only --
#:   the raw books' exposure question is already answered by normalization.
CONTROL_SHIFT = "shift"
CONTROL_SHUFFLE = "shuffle"

#: Pre-filing event-study windows, in trading sessions relative to the
#: filing's visible session ``v`` (``v`` itself is day 0 -- the first session
#: the information may be acted on).
PREFILING_PRE = (-5, -1)
PREFILING_POST_NEAR = (1, 5)
PREFILING_POST_FAR = (6, 20)

#: Card's stop-condition thresholds, verbatim. Not tunable here.
STOP_EXCESS_IMPROVEMENT_PP = 0.03
STOP_PLACEBO_SHARE = 0.5
STOP_SCREEN_ABS_T = 2.0
STOP_SCREEN_SIGN_STABILITY = 0.7
STOP_TENB51_SHARE = 0.5
STOP_MIN_SWITCHES_PER_YEAR = 4

#: Step 0's measured 10b5-1 checkbox share (``step0-collector-report.md`` 3.1),
#: the input to stop condition (4). The field only exists from 2023q2.
TENB51 = {
    "field_available_from": "2023q2",
    "field_available_share_2024_onward": 1.0,
    "checked_share_by_year": {"2023": 0.155, "2024": 0.211, "2025": 0.222, "2026": 0.163},
    "max_checked_share": 0.222,
}


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


def _events_from_json(payload: list[dict[str, Any]]) -> list[RebalanceEvent]:
    return [
        RebalanceEvent(
            date=row["date"],
            universe_size=int(row["universe_size"]),
            selected={str(k): float(v) for k, v in row["selected"].items()},
            portfolio_beta=row.get("portfolio_beta"),
        )
        for row in payload
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
    _log(f"panel rows={len(panel):,} memory={panel.memory_usage(deep=True).sum() / 1e6:.0f}MB")

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
        trend_gate_series=None,  # the cell is gate_off
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
    empty = [event.date for event in schedule if not event.selected]
    _log(f"{len(empty)} rebalance weeks produced no book at all: {empty}")


# --------------------------------------------------------------------------
# stage: gate-states (join the insider table onto the book)
# --------------------------------------------------------------------------


def _insider_root_for(source: str) -> Path:
    if source == "real":
        return INSIDER_ROOT
    seed = int(source.removeprefix("placebo"))
    return INSIDER_ROOT.with_name(f"insider_placebo_shift{PLACEBO_SHIFT_DAYS}_seed{seed}")


def _gate_state_path(source: str) -> Path:
    return GATE_STATES_DIR / f"{source}.parquet"


def build_gate_state_frame(picks: pd.DataFrame, insider_root: Path) -> pd.DataFrame:
    """One row per (rebalance date, held symbol) with the insider columns the
    gates read, as of that rebalance date, plus each gate's state.

    The join is on ``(symbol, trade_date == rebalance_date)`` against
    ``data/features/insider/{year}.parquet``, whose rows are already
    point-in-time (a filing is visible on the next session after its
    ``FILING_DATE``, and every ``*_60d`` window is measured over visible
    dates). Nothing here looks forward.
    """
    book = picks.loc[(picks["weight"] > 0.0) & (picks["symbol"] != CASH_SYMBOL)].copy()
    book["rebalance_date"] = pd.to_datetime(book["rebalance_date"])
    wanted = sorted({column for spec in GATE_SPECS.values() for column in spec.columns})
    # Carried for the pre-filing event study, not read by any gate, and
    # deliberately *not* zero-filled: null means "this issuer never had a
    # visible open-market buy", which is not the same statement as "0 sessions
    # ago".
    extra = ["days_since_last_visible_buy"]
    years = sorted({int(date.year) for date in book["rebalance_date"]})
    frames = []
    for year in years:
        path = insider_root / f"{year}.parquet"
        if not path.exists():
            continue
        dates = set(book.loc[book["rebalance_date"].dt.year == year, "rebalance_date"])
        frame = pd.read_parquet(path, columns=["symbol", "trade_date", *wanted, *extra])
        frame = frame.loc[frame["trade_date"].isin(dates)]
        frames.append(frame)
    if not frames:
        raise SystemExit(f"no insider feature years found under {insider_root}")
    insider = pd.concat(frames, ignore_index=True)
    merged = book.merge(
        insider.rename(columns={"trade_date": "rebalance_date"}),
        on=["symbol", "rebalance_date"],
        how="left",
    )
    merged["insider_row_present"] = merged[wanted[0]].notna()
    for column in wanted:
        merged[column] = merged[column].fillna(0.0)
    for name in GATE_SPECS:
        merged[f"state_{name}"] = gate_states(merged, name)
    columns = [
        "rebalance_date",
        "symbol",
        "weight",
        "score",
        "score_pct",
        "cohort_size",
        "universe_size",
        "insider_row_present",
        *wanted,
        *extra,
        *[f"state_{name}" for name in GATE_SPECS],
    ]
    return merged[[c for c in columns if c in merged.columns]].sort_values(
        ["rebalance_date", "symbol"], ignore_index=True
    )


def stage_gate_states(*, force: bool, sources: list[str]) -> None:
    picks = pd.read_parquet(PICKS_PATH)
    GATE_STATES_DIR.mkdir(parents=True, exist_ok=True)
    for source in sources:
        path = _gate_state_path(source)
        if path.exists() and not force:
            _log(f"{path.name}: already present -- reusing (checkpoint)")
            continue
        root = _insider_root_for(source)
        if not (root / "_build_manifest.json").exists():
            _log(f"{source}: {root} not built yet -- skipping")
            continue
        frame = build_gate_state_frame(picks, root)
        _write_parquet(path, frame)
        missing = int((~frame["insider_row_present"]).sum())
        shares = {name: state_shares(frame[f"state_{name}"]) for name in GATE_SPECS}
        _log(
            f"{source}: {len(frame):,} book rows, {missing} with no insider row "
            f"({missing / max(len(frame), 1):.3%}); "
            + "; ".join(
                f"{name} full={share.get('full', 0.0):.3f}" for name, share in shares.items()
            )
        )


# --------------------------------------------------------------------------
# stage: prefiling (is the effect before or after visibility?)
# --------------------------------------------------------------------------


def stage_prefiling(*, force: bool) -> None:
    if PREFILING_PATH.exists() and not force:
        _log(f"{PREFILING_PATH.name}: already present -- reusing (checkpoint)")
        return
    states = pd.read_parquet(_gate_state_path("real"))
    gated_in = states.loc[states["state_gate_A"] == "full"].copy()
    if gated_in.empty:
        raise SystemExit("no gate-A full-weight rows; run gate-states first")

    years = sorted({int(date.year) for date in pd.to_datetime(states["rebalance_date"])})
    years = tuple(range(min(years) - 1, max(years) + 1))
    _log(f"loading price panel for the event study (years {years}) ...")
    common = m_grid._load_common_data(years=years, trend_gate_required=False)
    # The session index has to come from the full panel (it defines the
    # trading calendar the ``days_since_last_visible_buy`` offsets are counted
    # on), but the price pivot only needs the gated-in names.
    sessions = pd.DatetimeIndex(sorted(common.price_panel["trade_date"].unique()))
    position = {date: index for index, date in enumerate(sessions)}
    wanted_symbols = set(gated_in["symbol"].astype(str))
    panel = common.price_panel
    panel = panel.loc[panel["symbol"].astype(str).isin(wanted_symbols)]
    close = panel.pivot(index="trade_date", columns="symbol", values="close")
    close = close.reindex(sessions).sort_index()
    symbol_returns = close.pct_change()
    spy_returns = common.spy_returns.reindex(close.index)

    # days_since_last_visible_buy counts sessions since the most recent visible
    # open-market buy, so the visible session itself is
    # `rebalance_date - days_since_last_visible_buy` sessions back on the
    # trading calendar. Rows with no visible buy at all are null and dropped.
    gated_in = gated_in.loc[gated_in["days_since_last_visible_buy"].notna()]
    gated_in = gated_in.loc[gated_in["days_since_last_visible_buy"] >= 0]
    rebalance_positions = pd.to_datetime(gated_in["rebalance_date"]).map(position)
    visible_positions = rebalance_positions - gated_in["days_since_last_visible_buy"].astype(int)
    gated_in = gated_in.assign(visible_position=visible_positions)
    gated_in = gated_in.loc[gated_in["visible_position"].notna()]
    events = (
        gated_in[["symbol", "visible_position"]]
        .drop_duplicates()
        .astype({"visible_position": int})
        .reset_index(drop=True)
    )
    _log(
        f"{len(gated_in):,} gate-A full-weight book rows -> {len(events):,} unique "
        "(symbol, visible filing session) events"
    )

    def window_excess(symbol: str, start: int, end: int) -> float:
        """Compounded symbol return minus compounded SPY return over
        ``sessions[start..end]`` inclusive; NaN if the window runs off either
        end of the calendar or the symbol has a gap in it.
        """
        if start < 0 or end >= len(sessions) or start > end:
            return float("nan")
        if symbol not in symbol_returns.columns:
            return float("nan")
        index = sessions[start : end + 1]
        own = symbol_returns.loc[index, symbol]
        if own.isna().any():
            return float("nan")
        market = spy_returns.loc[index]
        if market.isna().any():
            return float("nan")
        return float((1.0 + own).prod() - (1.0 + market).prod())

    rows: list[dict[str, Any]] = []
    for symbol, visible_position in zip(events["symbol"], events["visible_position"], strict=True):
        rows.append(
            {
                "symbol": symbol,
                "visible_date": sessions[visible_position].date().isoformat(),
                "pre_5": window_excess(
                    symbol, visible_position + PREFILING_PRE[0], visible_position + PREFILING_PRE[1]
                ),
                "post_1_5": window_excess(
                    symbol,
                    visible_position + PREFILING_POST_NEAR[0],
                    visible_position + PREFILING_POST_NEAR[1],
                ),
                "post_6_20": window_excess(
                    symbol,
                    visible_position + PREFILING_POST_FAR[0],
                    visible_position + PREFILING_POST_FAR[1],
                ),
            }
        )
    frame = pd.DataFrame(rows)
    _write_parquet(OUT_DIR / "prefiling_events.parquet", frame)

    def describe(column: str) -> dict[str, Any]:
        series = frame[column].dropna()
        if series.empty:
            return {"n": 0}
        from scipy import stats as scipy_stats

        t_stat, p_value = scipy_stats.ttest_1samp(series, 0.0)
        return {
            "n": int(len(series)),
            "mean": float(series.mean()),
            "median": float(series.median()),
            "std": float(series.std(ddof=1)),
            "t": float(t_stat),
            "p_value": float(p_value),
            "share_positive": float((series > 0).mean()),
        }

    pre = describe("pre_5")
    near = describe("post_1_5")
    far = describe("post_6_20")
    total_abs = abs(pre.get("mean", 0.0)) + abs(near.get("mean", 0.0)) + abs(far.get("mean", 0.0))
    payload = {
        "definition": (
            "for every unique (symbol, visible filing session) pair behind a gate_A "
            "full-weight decision, the compounded SPY-excess return over sessions "
            f"{PREFILING_PRE[0]}..{PREFILING_PRE[1]} (before visibility), "
            f"{PREFILING_POST_NEAR[0]}..{PREFILING_POST_NEAR[1]} and "
            f"{PREFILING_POST_FAR[0]}..{PREFILING_POST_FAR[1]} (after visibility, "
            "session 0 = the visible session itself, the first session we could act on)"
        ),
        "visible_session_source": (
            "rebalance_date shifted back days_since_last_visible_buy trading sessions"
        ),
        "book_rows": int(len(gated_in)),
        "unique_events": int(len(events)),
        "pre_5": pre,
        "post_1_5": near,
        "post_6_20": far,
        "pre_share_of_total_abs_mean": (
            abs(pre.get("mean", 0.0)) / total_abs if total_abs > 0 else None
        ),
    }
    _write_json(PREFILING_PATH, payload)
    _log(
        f"prefiling: pre(-5..-1) mean {pre.get('mean')}, post(+1..+5) mean {near.get('mean')}, "
        f"post(+6..+20) mean {far.get('mean')}"
    )


# --------------------------------------------------------------------------
# stage: evaluate
# --------------------------------------------------------------------------


def shuffled_states(states: pd.DataFrame, seed: int) -> pd.DataFrame:
    """``states`` with every gate's state column permuted **within each
    rebalance date** -- the concentration/exposure-preserving control.

    Permuting inside the week (not across the whole frame) is what keeps each
    week's full/half/veto counts exactly as the real gate produced them, so the
    shuffled book has the same number of positions, the same gross exposure
    after normalization and the same turnover profile; only the identity of the
    names is randomized.
    """
    rng = np.random.default_rng(seed)
    out = states.copy()
    groups = out.groupby("rebalance_date").indices
    for gate in GATE_SPECS:
        column = f"state_{gate}"
        values = out[column].to_numpy(copy=True)
        for index in groups.values():
            values[index] = rng.permutation(values[index])
        out[column] = values
    return out


def variant_books(states: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """``{variant label: frame with a ``weight`` column}`` -- the baseline plus
    every gate in raw (freed weight to BIL) and exposure-normalized (rescaled
    to 100% gross) form.
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
        experiment_id=f"h20260916_01_{label}",
        config_hash=f"h20260916_01_{label}",
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
        "full_oos": _window_block(
            returns, stress_returns, spy_returns, bil_returns, schedule, oos_start
        ),
        "h03_comparable": _window_block(
            returns, stress_returns, spy_returns, bil_returns, schedule, H03_COMPARABLE_START
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
        metrics["state_shares_recent_2024"] = state_shares(
            states.loc[
                pd.to_datetime(states["rebalance_date"])
                >= pd.Timestamp(regime_gates.RECENT_WINDOW_START),
                column,
            ]
        )
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
    states_real = pd.read_parquet(_gate_state_path("real"))
    states_real["rebalance_date"] = pd.to_datetime(states_real["rebalance_date"])
    oos_dates = pd.DatetimeIndex(sorted(states_real["rebalance_date"].unique()))
    oos_start = oos_dates.min()
    _log(f"book span: {oos_start.date()}..{oos_dates.max().date()} ({len(oos_dates)} rebalances)")

    years = tuple(range(oos_start.year, 2027))
    common = m_grid._load_common_data(years=years, trend_gate_required=False)
    # Narrow the mark-to-market panel to the names any book can hold before
    # pivoting. ``returns_from_weight_schedule`` recomputes ``pct_change()``
    # over the whole wide frame on every call and this round makes ~60 of
    # those calls (9 real books + 20 placebo books, primary and stress cost
    # each), so carrying the ~3,000 columns of the full archive instead of the
    # few hundred actually held is both the memory peak and most of the
    # runtime, for zero effect on any number: the function only ever reads
    # columns a schedule names.
    held = set(states_real["symbol"].astype(str)) | {CASH_SYMBOL}
    for seed in PLACEBO_SEEDS:
        path = _gate_state_path(f"placebo{seed}")
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

    results: dict[str, Any] = {"variants": {}, "placebo_variants": {}}
    books = variant_books(states_real)
    for label, book in books.items():
        gate_name = None if label == "gate_off" else label.rsplit("_", 1)[0]
        cash = None if label.endswith("_norm") or label == "gate_off" else CASH_SYMBOL
        schedule = weight_schedule_from_pick_frame(
            book, cash_symbol=cash, universe_size_column=None
        )
        primary, stress = _price_streams(schedule, price_wide, open_wide, spy_returns)
        results["variants"][label] = _variant_metrics(
            label=label,
            book=book,
            states=states_real,
            gate_name=gate_name,
            returns=primary,
            stress_returns=stress,
            spy_returns=spy_returns,
            bil_returns=bil_returns,
            schedule=schedule,
            oos_start=oos_start,
        )
        recent = results["variants"][label]["recent_2024"]
        _log(
            f"{label}: 2024→ CAGR {recent['cagr_net']:.4f} MDD {recent['max_drawdown']:.4f} "
            f"vol-matched excess {recent['cagr_excess_vol_matched_spy']:.4f} "
            f"exposure {results['variants'][label]['mean_invested_exposure']:.3f}"
        )

    def price_control(
        control: str, seed: int, states: pd.DataFrame, suffixes: tuple[str, ...]
    ) -> int:
        books = variant_books(states)
        count = 0
        for gate_name in PLACEBO_GATES:
            for suffix in suffixes:
                label = f"{gate_name}_{suffix}"
                book = books[label]
                cash = None if suffix == "norm" else CASH_SYMBOL
                schedule = weight_schedule_from_pick_frame(
                    book, cash_symbol=cash, universe_size_column=None
                )
                primary, stress = _price_streams(schedule, price_wide, open_wide, spy_returns)
                key = f"{label}__{control}{seed}"
                results["placebo_variants"][key] = _variant_metrics(
                    label=key,
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
                count += 1
        return count

    for seed in PLACEBO_SEEDS:
        path = _gate_state_path(f"placebo{seed}")
        if not path.exists():
            _log(f"shift{seed}: no gate-state checkpoint -- skipping")
            continue
        shifted = pd.read_parquet(path)
        shifted["rebalance_date"] = pd.to_datetime(shifted["rebalance_date"])
        priced = price_control(CONTROL_SHIFT, seed, shifted, ("raw", "norm"))
        _log(f"shift{seed}: priced {priced} filing-date-shifted books")

    for seed in PLACEBO_SEEDS:
        priced = price_control(CONTROL_SHUFFLE, seed, shuffled_states(states_real, seed), ("norm",))
        _log(f"shuffle{seed}: priced {priced} within-week state-shuffled books")

    # Checkpoint before rendering: pricing 29 books is the expensive part, and
    # the report's wording is the part that gets iterated on. ``report`` can
    # then be re-rendered from this file alone.
    _write_json(RESULTS_PATH, results)
    _log(f"wrote {RESULTS_PATH.name} ({len(results['variants'])} real books)")
    stage_report()


def stage_report() -> None:
    """Re-render ``step2-twin-report.{json,md}`` from the priced-book
    checkpoint, without re-pricing anything."""
    results = json.loads(RESULTS_PATH.read_text())
    states_real = pd.read_parquet(_gate_state_path("real"))
    states_real["rebalance_date"] = pd.to_datetime(states_real["rebalance_date"])
    oos_dates = pd.DatetimeIndex(sorted(states_real["rebalance_date"].unique()))
    report = _build_report(results=results, states=states_real, oos_dates=oos_dates)
    _write_json(REPORT_JSON_PATH, report)
    REPORT_MD_PATH.write_text(_render_markdown(report), encoding="utf-8")
    _log(f"wrote {REPORT_JSON_PATH.name} and {REPORT_MD_PATH.name}")
    for name, conditions in report["stop_conditions"].items():
        for key, value in conditions.items():
            _log(f"stop-condition[{name}] {key}: {value['verdict']} -- {value['detail']}")


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------


def _reference_disclosures() -> dict[str, Any]:
    payload = json.loads(
        (ROOT / "config" / "promotion" / "recent-regime-high-return-gates-v2.json").read_text()
    )
    return payload["reference_disclosures"]


def _pool_vs_book_gate_shares(states: pd.DataFrame) -> dict[str, Any] | None:
    """Each gate's "full weight" share in the whole top-500 pool versus in the
    top-50 momentum book, over the book's own date range.

    This is the single most informative diagnostic of the round and it is
    computed, never typed: if the book's share is far below the pool's, the
    momentum signal and the insider-buy signal are looking at disjoint sets of
    stocks, and a halving gate on that book is arithmetically a de-leveraging
    device rather than a selector. Pool rows come from
    ``data/features/insider/screening_panel_weekly.parquet`` (Friday x top-500
    ADV); book rows are the actual rebalance dates, which are ISO-week last
    sessions and therefore Fridays except in holiday weeks.
    """
    panel_path = INSIDER_ROOT / "screening_panel_weekly.parquet"
    if not panel_path.exists():
        return None
    columns = sorted({column for spec in GATE_SPECS.values() for column in spec.columns})
    panel = pd.read_parquet(panel_path, columns=["symbol", "friday_date", *columns])
    panel["friday_date"] = pd.to_datetime(panel["friday_date"])
    book_dates = pd.to_datetime(states["rebalance_date"])
    panel = panel.loc[
        (panel["friday_date"] >= book_dates.min()) & (panel["friday_date"] <= book_dates.max())
    ]
    recent = pd.Timestamp(regime_gates.RECENT_WINDOW_START)
    panel_recent = panel.loc[panel["friday_date"] >= recent]
    out: dict[str, Any] = {
        "pool_rows": int(len(panel)),
        "book_rows": int(len(states)),
        "pool_source": "data/features/insider/screening_panel_weekly.parquet (friday x top-500)",
        "gates": {},
    }
    for gate in GATE_SPECS:
        pool = state_shares(gate_states(panel, gate))
        pool_r = state_shares(gate_states(panel_recent, gate))
        book = state_shares(states[f"state_{gate}"])
        book_r = state_shares(states.loc[book_dates >= recent, f"state_{gate}"])
        out["gates"][gate] = {
            "pool_full_share": pool.get("full"),
            "book_full_share": book.get("full"),
            "pool_veto_share": pool.get("veto"),
            "book_veto_share": book.get("veto"),
            "pool_full_share_recent": pool_r.get("full"),
            "book_full_share_recent": book_r.get("full"),
            "book_over_pool_full_ratio": (
                book.get("full", 0.0) / pool["full"] if pool.get("full") else None
            ),
        }
    return out


def _screen_table() -> dict[str, Any] | None:
    path = OUT_DIR / "step1-insider-screen.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _fmt(value: float | None, spec: str) -> str:
    return "N/A" if value is None else format(value, spec)


def _pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "N/A"
    return f"{value * 100:.1f}%"


def _control_aggregate(
    results: dict[str, Any], baseline_excess: float, control: str
) -> dict[str, Any]:
    """Per (gate, raw/norm): what each control seed's vol-matched-excess
    improvement over the baseline was, plus that distribution's mean/min/max.

    The verdict uses the mean seed and discloses the spread, which is
    L-20260916-03's rule: one draw decided that round's borderline call by
    0.007, so a single number is not reportable.
    """
    out: dict[str, Any] = {}
    for gate_name in PLACEBO_GATES:
        for suffix in ("raw", "norm"):
            label = f"{gate_name}_{suffix}"
            rows = [
                metrics
                for key, metrics in results["placebo_variants"].items()
                if key.startswith(f"{label}__{control}")
            ]
            if not rows:
                continue
            improvements = [
                row["recent_2024"]["cagr_excess_vol_matched_spy"] - baseline_excess for row in rows
            ]
            out[label] = {
                "seeds": len(rows),
                "improvements": improvements,
                "improvement_mean": float(np.mean(improvements)),
                "improvement_min": float(np.min(improvements)),
                "improvement_max": float(np.max(improvements)),
                "cagr_recent_mean": float(np.mean([r["recent_2024"]["cagr_net"] for r in rows])),
                "max_drawdown_recent_mean": float(
                    np.mean([r["recent_2024"]["max_drawdown"] for r in rows])
                ),
                "cagr_excess_vol_matched_spy_mean": float(
                    np.mean([r["recent_2024"]["cagr_excess_vol_matched_spy"] for r in rows])
                ),
                "hit_rate_weekly_mean": float(
                    np.mean([r["recent_2024"]["hit_rate_weekly"] for r in rows])
                ),
                "turnover_per_rebalance_mean": float(
                    np.mean([r["turnover_per_rebalance_mean"] for r in rows])
                ),
                "mean_invested_exposure": float(
                    np.mean([r["mean_invested_exposure"] for r in rows])
                ),
                "full_oos_cagr_mean": float(np.mean([r["full_oos"]["cagr_net"] for r in rows])),
                "full_oos_max_drawdown_mean": float(
                    np.mean([r["full_oos"]["max_drawdown"] for r in rows])
                ),
                "full_oos_excess_mean": float(
                    np.mean([r["full_oos"]["cagr_excess_vol_matched_spy"] for r in rows])
                ),
                "gated_in_share_mean": float(
                    np.mean([r["state_shares"].get("full", 0.0) for r in rows])
                ),
                "positions_per_week_mean": float(
                    np.mean([r["positions_per_week_mean"] for r in rows])
                ),
            }
    return out


#: Which screener column each gate's stop-condition (3) verdict reads.
GATE_SCREEN_COLUMN: dict[str, str] = {
    "gate_A": "open_market_buy_count_60d",
    "gate_B": "buyers_60d",
    "gate_C": "cmp_opportunistic_buy_60d",
    "gate_A_veto": "open_market_sell_count_60d",
}
#: The screener label whose recent-window |t| and sign stability the verdict
#: uses. ``label_rank_5`` is the repo's own ML target and the gate is a weekly
#: decision, so the 5-session horizon is the matching one.
GATE_SCREEN_LABEL = "label_rank_5"


def _stop_conditions(
    *,
    results: dict[str, Any],
    placebo: dict[str, Any],
    shuffle: dict[str, Any],
    screen: dict[str, Any] | None,
) -> dict[str, Any]:
    baseline = results["variants"]["gate_off"]
    baseline_excess = baseline["recent_2024"]["cagr_excess_vol_matched_spy"]
    out: dict[str, Any] = {}
    for gate_name in GATE_SPECS:
        label = f"{gate_name}_norm"
        real = results["variants"][label]
        real_excess = real["recent_2024"]["cagr_excess_vol_matched_spy"]
        improvement = real_excess - baseline_excess
        aggregate = placebo.get(label)
        placebo_improvement = aggregate["improvement_mean"] if aggregate else None
        ratio = (
            placebo_improvement / improvement
            if aggregate is not None and improvement > 0.0
            else None
        )
        ratio_max = (
            aggregate["improvement_max"] / improvement
            if aggregate is not None and improvement > 0.0
            else None
        )
        screen_row = None
        screen_column = GATE_SCREEN_COLUMN[gate_name]
        if screen is not None:
            for row in screen["table"]:
                if row["factor"] == screen_column and row["label"] == GATE_SCREEN_LABEL:
                    screen_row = row
                    break
        t_recent = screen_row["t_recent"] if screen_row else None
        stability = screen_row["sign_stability_windows"] if screen_row else None
        screen_weak = (
            t_recent is not None
            and stability is not None
            and abs(t_recent) < STOP_SCREEN_ABS_T
            and stability < STOP_SCREEN_SIGN_STABILITY
        )
        switches = real.get("rebalances_with_gate_change_per_year", {})
        # 2026 is a partial year (the archive ends 2026-09-15), so it cannot be
        # held to a full-year activity floor; it is reported but excluded from
        # the minimum.
        full_years = {year: count for year, count in switches.items() if str(year) not in {"2026"}}
        min_switches = min(full_years.values()) if full_years else None
        out[gate_name] = {
            "1_vol_matched_excess_improvement_ge_3pp": {
                "verdict": "PASS" if improvement >= STOP_EXCESS_IMPROVEMENT_PP else "FAIL",
                "value": improvement,
                "threshold": STOP_EXCESS_IMPROVEMENT_PP,
                "detail": (
                    f"同波动 SPY 超额（归一化后，2024→）{baseline_excess:.4f} -> "
                    f"{real_excess:.4f}（改善 {improvement:+.4f}，需要 >= "
                    f"+{STOP_EXCESS_IMPROVEMENT_PP:.4f}）"
                ),
            },
            "2_placebo_improvement_lt_50pct_of_real": {
                "verdict": (
                    "N/A" if ratio is None else ("FAIL" if ratio >= STOP_PLACEBO_SHARE else "PASS")
                ),
                "value": ratio,
                "threshold": STOP_PLACEBO_SHARE,
                "placebo_seeds": aggregate["seeds"] if aggregate else 0,
                "placebo_improvements": aggregate["improvements"] if aggregate else [],
                "placebo_improvement_mean": placebo_improvement,
                "placebo_improvement_max": aggregate["improvement_max"] if aggregate else None,
                "placebo_ratio_max": ratio_max,
                # Additional disclosure, not part of the card's own condition:
                # the within-week state shuffle keeps exposure/concentration
                # and randomizes only which names the gate picked.
                "shuffle_control_improvement_mean": (
                    shuffle[label]["improvement_mean"] if label in shuffle else None
                ),
                "shuffle_control_ratio": (
                    shuffle[label]["improvement_mean"] / improvement
                    if label in shuffle and improvement > 0.0
                    else None
                ),
                "detail": (
                    f"真实改善 {improvement:+.4f}；占位 "
                    f"{aggregate['seeds'] if aggregate else 0} 个种子的改善均值 "
                    f"{_fmt(placebo_improvement, '+.4f')}"
                    + (
                        f"（最小 {aggregate['improvement_min']:+.4f}，最大 "
                        f"{aggregate['improvement_max']:+.4f}）"
                        if aggregate
                        else ""
                    )
                    + f"；均值比 {_fmt(ratio, '.3f')}，最差种子比 {_fmt(ratio_max, '.3f')}"
                    + (
                        "（真实改善不是正数，这个比值没有意义：判据 (1) 已经停了这条路）"
                        if improvement <= 0.0
                        else ""
                    )
                    + ("（本门没有跑占位，见报告口径一节）" if aggregate is None else "")
                    + (
                        "；附加对照（周内打乱门的标签、保持每周满仓/减半/剔除的个数不变）"
                        f"改善均值 {shuffle[label]['improvement_mean'] * 100:+.1f} pp"
                        + (
                            f"，是真实的 "
                            f"{shuffle[label]['improvement_mean'] / improvement * 100:.0f}%"
                            if improvement > 0.0
                            else ""
                        )
                        if label in shuffle
                        else ""
                    )
                ),
            },
            "3_screen_recent_t_and_sign_stability": {
                # The card stops only when BOTH are weak.
                "verdict": "FAIL" if screen_weak else ("PASS" if screen_row else "N/A"),
                "screen_column": screen_column,
                "screen_label": GATE_SCREEN_LABEL,
                "t_recent": t_recent,
                "sign_stability_windows": stability,
                "thresholds": {
                    "abs_t": STOP_SCREEN_ABS_T,
                    "sign_stability": STOP_SCREEN_SIGN_STABILITY,
                },
                "detail": (
                    f"筛选器 `{screen_column}` vs `{GATE_SCREEN_LABEL}`：近窗 t = "
                    f"{_fmt(t_recent, '+.2f')}，3 窗符号稳定性 = {_fmt(stability, '.2f')}"
                    f"（同时 |t| < {STOP_SCREEN_ABS_T} 且稳定性 < "
                    f"{STOP_SCREEN_SIGN_STABILITY} 才算命中）"
                ),
            },
            "4_10b5_1_indistinguishable_share_gt_50pct": {
                "verdict": "PASS" if TENB51["max_checked_share"] <= STOP_TENB51_SHARE else "FAIL",
                "value": TENB51["max_checked_share"],
                "threshold": STOP_TENB51_SHARE,
                "detail": (
                    "第 0 步实测：`SUBMISSION.AFF10B5ONE` 字段 2023q2 起 100% 可用，"
                    f"打勾比例逐年 {TENB51['checked_share_by_year']}，最高 "
                    f"{TENB51['max_checked_share'] * 100:.1f}%，低于 50%。"
                    "2016-2022 完全没有这个字段，属于已披露的盲区，不是可区分性失败。"
                ),
            },
            "5_gate_switches_ge_4_per_year": {
                "verdict": (
                    "N/A"
                    if min_switches is None
                    else ("FAIL" if min_switches < STOP_MIN_SWITCHES_PER_YEAR else "PASS")
                ),
                "value": min_switches,
                "threshold": STOP_MIN_SWITCHES_PER_YEAR,
                "rebalances_with_gate_change_per_year": switches,
                "gate_state_changes_per_year": real.get("gate_state_changes_per_year", {}),
                "detail": (
                    "每年有多少个调仓周里，门至少改变了一只持仓的权重（2026 是残年，"
                    f"报出但不参与取最小）：最小年 "
                    f"{'N/A' if min_switches is None else min_switches}"
                    f"，需要 >= {STOP_MIN_SWITCHES_PER_YEAR}"
                ),
            },
        }
    return out


def _caveats(*, results: dict[str, Any], oos_dates: pd.DatetimeIndex) -> list[str]:
    baseline = results["variants"]["gate_off"]
    return [
        "**内部人特征表在本轮开头被重建过一次。** 第 0 步的表是 2026-09-16 02:33 建的，"
        "而 EDGAR 日更尾段的解析到 04:17 才跑完，所以那张表 2026-07 起的覆盖率是 0%，"
        "而且行一直延伸到 2026-12-31（`--as-of` 当时没传）。第 2 步开始前用 "
        "`--force --as-of 2026-09-15` 重建了一次：现在 2026 年是 136,096 行、"
        "截止 2026-09-15、60 日内有可见买入的比例 14.34%。第 0 步报告里 3.3 节那张"
        "「7 月起 0%」的表说的是补齐前的状态，重建后已经不成立。",
        "**股票池是今天重建过的版本。** `data/features/universe` 的月中单行 cohort 缺陷"
        "（L-20260916-03 第 4 条）已经修好，所以这一轮没有整周空仓的调仓周；"
        "H-20260916-03 的数字是在有 7 个空仓周的旧池子上算的，两轮的基线因此不完全可比，"
        "这里的基线是用修好的池子重新跑出来的。",
        f"**基线在近窗算出 {_pct(baseline['recent_2024']['cagr_net'])}，账本里那一格是 33.0%。** "
        "同一批持仓、不同窗口边界：账本那一格的调仓表从 2024-01-08 才开始建仓（含一次性 100% "
        "换手成本），这里的调仓表从 2017 年就在跑。两个数都对，口径不同，不能混用。",
        "**卡上写的是 2016 起，实际从 2017-01-06 起。** `momentum_252_21` 需要 252 个交易日"
        "历史，日线档案从 2016-01-04 开始，所以 2016 年这一列全是空值，2016 只当暖机年。",
        "**`cmp_opportunistic_buy_60d`（gate_C）在 2019 年之前结构性为 0。** CMP 严格口径需要"
        "三年可见申报历史，我们的档案从 2016 开始，所以 gate_C 在 2017-2018 等价于"
        "「全部减半」。这不是数据缺陷，是口径的必然结果，但它让 gate_C 的全样本数字"
        "带着两年纯去杠杆的尾巴。",
        "**没有写账本。** 这一轮不经过 `loop.run_experiment`，"
        "`reports/research/ledger/experiments.jsonl` 一行都没写；表里的合同 v2 判定是 "
        "`reference_only` 披露，不构成任何晋级资格。",
        "**判据 (3) 的「符号稳定性 ≥ 0.7」在三个子窗上只有四个可能取值**"
        "（0、0.33、0.67、1.00），所以这个门槛实际等价于「三个窗口符号完全一致」。"
        "表里几乎所有列都落在 0.67，意思是 2018-2020 那一段的符号和后两段相反——"
        "内部人列在 2018-2020 普遍是负 IC、2024 年后转正或接近零。逐年版本"
        "（九个窗口，粒度更细）在 `step1-insider-screen.md` 里一并列出。",
        "**有一个「显著但方向相反」的结果，必须单独说。** `cmp_opportunistic_buy_60d` 对 "
        "21 日超额在近窗的 t = -2.73（|t| ≥ 2），但符号是负的：严格机会型内部人买入越多，"
        "未来 21 日的截面超额越低。卡上的判据 (3) 只看 |t| 和符号稳定性、不看符号方向，"
        "所以它在形式上「没有命中停止条件」；但按假设本身的方向读，这是**反向证据**，"
        "不是支持证据。另外它的 3 窗符号稳定性只有 0.33，全样本 t 只有 -0.54，"
        "39 次检验里近窗没有一个过 BH FDR，所以更可能是多重检验的噪声而不是真实的反向 alpha。",
        "**唯一一个全样本过 FDR 的检验也是反向的**：`routine_buy_60d` 对 21 日超额，"
        "全样本 t = -3.36，符号稳定性 1.00，且 CMP 文献恰恰说例行买入的信息含量约为零。"
        "它同时覆盖率极低（99.6% 的股票日为 0），所以它不构成一个可交易的方向，"
        "只是提醒：在这批数据上「内部人买入」这个方向在动量池里是弱负相关，不是弱正相关。",
        f"**评估区间 {oos_dates.min().date()} → {oos_dates.max().date()}，"
        f"{len(oos_dates)} 个调仓周。** 门的阈值（≥1 笔买入、≥2 个买家、≥1 笔 CMP 机会型、"
        "≥3 笔卖出且无买入）都是卡上事先写死的，没有在这些数据上调过；"
        "但也没有第三段独立数据可以再验一次，这是本轮证据强度的上限。",
    ]


def _build_report(
    *, results: dict[str, Any], states: pd.DataFrame, oos_dates: pd.DatetimeIndex
) -> dict[str, Any]:
    baseline_excess = results["variants"]["gate_off"]["recent_2024"]["cagr_excess_vol_matched_spy"]
    placebo = _control_aggregate(results, baseline_excess, CONTROL_SHIFT)
    shuffle = _control_aggregate(results, baseline_excess, CONTROL_SHUFFLE)
    screen = _screen_table()
    prefiling = json.loads(PREFILING_PATH.read_text()) if PREFILING_PATH.exists() else None
    coverage = {
        "book_rows": int(len(states)),
        "rows_without_insider_row": int((~states["insider_row_present"]).sum()),
        "share_without_insider_row": float((~states["insider_row_present"]).mean()),
    }
    return {
        "hypothesis": "H-20260916-01",
        "step": 2,
        "card": "reports/research/hypotheses/H-20260916-01-insider-form4-confirmation-gate.md",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "primary_cell": PRIMARY_CELL,
        "ledger_written": False,
        "ledger_note": (
            "evaluation does not go through loop.run_experiment, so no row was appended to "
            "reports/research/ledger/experiments.jsonl; the v2 gate verdicts here are "
            "reference_only disclosures"
        ),
        "cost_assumptions": {
            "primary_cost_bps_per_side": PRIMARY_COST_BPS,
            "stress_cost_bps_per_side": STRESS_COST_BPS,
            "execution": EXECUTION,
            "returns_contract": "portfolio_returns.buy_and_hold_drift.v2",
            "cash_leg": CASH_SYMBOL,
        },
        "oos_window": {
            "first_rebalance": oos_dates.min().date().isoformat(),
            "last_rebalance": oos_dates.max().date().isoformat(),
            "rebalance_dates": int(len(oos_dates)),
            "h03_comparable_start": H03_COMPARABLE_START.date().isoformat(),
        },
        "gate_definitions": {
            name: {"description": spec.description, "columns": list(spec.columns)}
            for name, spec in GATE_SPECS.items()
        },
        "insider_coverage": coverage,
        "pool_vs_book_gate_shares": _pool_vs_book_gate_shares(states),
        "placebo": {
            "shift_filing_dates_days": PLACEBO_SHIFT_DAYS,
            "seeds": list(PLACEBO_SEEDS),
            "gates": list(PLACEBO_GATES),
            "note": (
                "features rebuilt per seed into data/features/insider_placebo_shift30_seed{S}/; "
                "the real table is never overwritten. Placebo runs are controls and are not "
                "counted as trials in trial-families.json."
            ),
        },
        "variants": results["variants"],
        # Only each control book's headline numbers are carried into the
        # committed report: with 4 gates x 5 seeds x 2 controls the full metric
        # blocks are ~250KB of per-year state shares nobody reads, and they are
        # already on disk in the (gitignored) step2-results-raw.json checkpoint
        # this report is rendered from. The aggregates below are what the
        # verdict uses.
        "placebo_variants_headline": {
            key: {
                "recent_2024_cagr_net": metrics["recent_2024"]["cagr_net"],
                "recent_2024_max_drawdown": metrics["recent_2024"]["max_drawdown"],
                "recent_2024_cagr_excess_vol_matched_spy": metrics["recent_2024"][
                    "cagr_excess_vol_matched_spy"
                ],
                "recent_2024_hit_rate_weekly": metrics["recent_2024"]["hit_rate_weekly"],
                "full_oos_cagr_net": metrics["full_oos"]["cagr_net"],
                "full_oos_max_drawdown": metrics["full_oos"]["max_drawdown"],
                "full_oos_cagr_excess_vol_matched_spy": metrics["full_oos"][
                    "cagr_excess_vol_matched_spy"
                ],
                "mean_invested_exposure": metrics["mean_invested_exposure"],
                "positions_per_week_mean": metrics["positions_per_week_mean"],
                "turnover_per_rebalance_mean": metrics["turnover_per_rebalance_mean"],
                "gated_in_share": metrics.get("state_shares", {}).get("full"),
            }
            for key, metrics in results["placebo_variants"].items()
        },
        "placebo_aggregate": placebo,
        "shuffle_aggregate": shuffle,
        "prefiling_check": prefiling,
        "screen_meta": screen["meta"] if screen else None,
        "screen_table": screen["table"] if screen else None,
        "reference_disclosures": _reference_disclosures(),
        "stop_conditions": _stop_conditions(
            results=results, placebo=placebo, shuffle=shuffle, screen=screen
        ),
        "caveats": _caveats(results=results, oos_dates=oos_dates),
    }


def _verdict_lines(report: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    failed = {
        gate: [name for name, item in conditions.items() if item["verdict"] == "FAIL"]
        for gate, conditions in report["stop_conditions"].items()
    }
    any_failed = any(failed.values())
    if any_failed:
        lines.append(
            "**假设被否定。** 四个门（any_buy / cluster / cmp_opportunistic / veto）"
            "都命中了卡上「任一命中即停」的停止条件："
            + "；".join(
                f"{gate} 命中 {len(names)} 条（{', '.join(names) if names else '无'}）"
                for gate, names in failed.items()
            )
            + "。"
        )
    else:
        lines.append("**没有命中任何停止条件。**")
    lines.append("")
    baseline = report["variants"]["gate_off"]["recent_2024"]
    for gate in report["stop_conditions"]:
        real = report["variants"][f"{gate}_norm"]
        raw = report["variants"][f"{gate}_raw"]
        improvement = (
            real["recent_2024"]["cagr_excess_vol_matched_spy"]
            - baseline["cagr_excess_vol_matched_spy"]
        )
        aggregate = report["placebo_aggregate"].get(f"{gate}_norm")
        shuffle = (report.get("shuffle_aggregate") or {}).get(f"{gate}_norm")
        share = (
            f"，申报日平移占位（{aggregate['seeds']} 个种子）的改善均值 "
            f"{aggregate['improvement_mean'] * 100:+.1f} 个百分点"
            f"（是真实的 {aggregate['improvement_mean'] / improvement * 100:.0f}%）"
            if aggregate is not None and improvement > 0
            else ""
        )
        if shuffle is not None and improvement > 0:
            share += (
                f"，周内打乱标签的附加对照改善均值 "
                f"{shuffle['improvement_mean'] * 100:+.1f} 个百分点"
                f"（是真实的 {shuffle['improvement_mean'] / improvement * 100:.0f}%）"
            )
        lines.append(
            f"- **{gate}**：归一化后 2024→ 同波动 SPY 超额 "
            f"{_pct(baseline['cagr_excess_vol_matched_spy'])} → "
            f"{_pct(real['recent_2024']['cagr_excess_vol_matched_spy'])}"
            f"（{improvement * 100:+.1f} 个百分点，要求 ≥ +3.0），"
            f"CAGR {_pct(baseline['cagr_net'])} → {_pct(real['recent_2024']['cagr_net'])}，"
            f"最大回撤 {_pct(baseline['max_drawdown'])} → "
            f"{_pct(real['recent_2024']['max_drawdown'])}"
            + share
            + f"。未归一化（余额放 BIL）的同一个门：平均暴露 "
            f"{_pct(raw['mean_invested_exposure'])}，同波动超额 "
            f"{_pct(raw['recent_2024']['cagr_excess_vol_matched_spy'])}。"
        )
        # Any gate that clears condition (1) on the recent window gets its
        # other two windows spelled out in the same breath: a gain that only
        # exists in the gated window is a window artifact, and that is exactly
        # the kind of thing a recent-window-only contract cannot see.
        if improvement >= STOP_EXCESS_IMPROVEMENT_PP:
            baseline_full = report["variants"]["gate_off"]["full_oos"]
            baseline_h03 = report["variants"]["gate_off"]["h03_comparable"]
            key = "cagr_excess_vol_matched_spy"
            lines.append(
                f"  - **但这个改善只存在于近窗。** 同一个门在 H-03 可比窗（2020Q2→）的同波动超额是 "
                f"{_pct(baseline_h03[key])} → {_pct(real['h03_comparable'][key])}"
                f"（{(real['h03_comparable'][key] - baseline_h03[key]) * 100:+.1f} pp），"
                f"在全样本（2017→）是 {_pct(baseline_full[key])} → "
                f"{_pct(real['full_oos'][key])}"
                f"（{(real['full_oos'][key] - baseline_full[key]) * 100:+.1f} pp），"
                f"最大回撤在全样本上还更差：{_pct(baseline_full['max_drawdown'])} → "
                f"{_pct(real['full_oos']['max_drawdown'])}。"
            )
    lines.append("")
    return lines


def _render_markdown(report: dict[str, Any]) -> str:
    reference = report["reference_disclosures"]
    lines: list[str] = []
    lines.append("# H-20260916-01 Form 4 内部人确认门 — 第 1–2 步结果")
    lines.append("")
    lines.append(
        f"- 生成时间：{report['generated_at']}｜一级信号：`{report['primary_cell']}`（未改动）"
    )
    lines.append(
        f"- 评估区间：{report['oos_window']['first_rebalance']} → "
        f"{report['oos_window']['last_rebalance']}"
        f"（{report['oos_window']['rebalance_dates']} 个调仓周，周频，"
        f"每周五收盘信号 → 下一交易日开盘成交）"
    )
    costs = report["cost_assumptions"]
    lines.append(
        f"- 成本与执行：主成本 {costs['primary_cost_bps_per_side']:.0f} bp/边、"
        f"压力成本 {costs['stress_cost_bps_per_side']:.0f} bp/边、"
        f"`{costs['execution']}`、现金腿 {costs['cash_leg']}，与 Step 13 完全一致"
    )
    lines.append(
        "- 账本：这一轮不经过 `loop.run_experiment`，"
        "`reports/research/ledger/experiments.jsonl` 一行都没写；表里的合同 v2 判定是 "
        "`reference_only` 披露，不构成晋级资格。"
    )
    lines.append("")
    lines.append("## 结论（先看这一段）")
    lines.append("")
    lines.extend(_verdict_lines(report))

    prefiling = report.get("prefiling_check")
    if prefiling:
        lines.append("### 申报前 vs 申报后（这一轮最重要的一张数）")
        lines.append("")
        lines.append(
            f"对每一个进入 gate_A「满仓」的（股票，可见申报日）组合（去重后 "
            f"{prefiling['unique_events']:,} 个事件），相对 SPY 的累计超额："
        )
        lines.append("")
        lines.append("| 窗口（交易日，0 = 可见日） | 事件数 | 平均超额 | 中位 | t | 正向比例 |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for key, name in (
            ("pre_5", "-5 .. -1（可见之前，我们拿不到）"),
            ("post_1_5", "+1 .. +5（可见之后）"),
            ("post_6_20", "+6 .. +20（可见之后）"),
        ):
            item = prefiling[key]
            lines.append(
                f"| {name} | {item['n']:,} | {item['mean'] * 100:+.2f}% | "
                f"{item['median'] * 100:+.2f}% | {item['t']:+.2f} | "
                f"{item['share_positive'] * 100:.1f}% |"
            )
        lines.append("")
        pre = prefiling["pre_5"]
        near = prefiling["post_1_5"]
        far = prefiling["post_6_20"]
        significant = [
            name
            for name, item in (("-5..-1", pre), ("+1..+5", near), ("+6..+20", far))
            if abs(item["t"]) >= 2.0
        ]
        if not significant:
            lines.append(
                f"**三个窗口都和 0 区分不开**（|t| 最大 "
                f"{max(abs(pre['t']), abs(near['t']), abs(far['t'])):.2f}），"
                f"而且样本只有 {prefiling['unique_events']} 个事件。"
                "所以在我们自己的数据上，既不能证实也不能推翻文献那个「超额发生在申报之前」"
                "的结论——**样本量本身就是本轮的结论**：十年的动量 top-50 组合里，"
                "总共只出现过这么多次「入选时 60 天内有内部人公开市场买入」。"
                "换句话说，问题不是「申报后还有没有钱」，而是「动量股里几乎没有内部人在买」。"
            )
        elif pre["mean"] > 0 and pre["mean"] > far["mean"]:
            lines.append(
                "**大部分效应确实在可见日之前。** 这和文献一致（集群买入的 +1.61% 发生在申报日"
                "之前），也就意味着 Form 4 只能当慢变量和否决位，不能「跟着买」——"
                "我们能行动的第一刻，信息已经被价格吸收了。"
            )
        else:
            lines.append(
                f"可见日之前的超额（{pre['mean'] * 100:+.2f}%）并不大于可见日之后 +6..+20 的"
                f"超额（{far['mean'] * 100:+.2f}%），所以「效应全在申报前」这个说法在我们自己的"
                f"样本上不成立；但显著的窗口是 {', '.join(significant)}，读的时候要看 t 值。"
            )
        lines.append("")

    lines.append("## 第 1 步：筛选器（内部人 13 列 × 3 个标签）")
    lines.append("")
    screen_meta = report.get("screen_meta")
    screen_table = report.get("screen_table")
    if screen_meta and screen_table:
        lines.append(
            f"预登记：{screen_meta['n_factors']} 列 × {screen_meta['n_labels']} 个标签 = "
            f"**{screen_meta['n_tests']} 次检验**，BH q={screen_meta['fdr_q']}，"
            f"池子 = 当月点时 top-{screen_meta['universe_top_n']} ADV，"
            f"样本 {screen_meta['first_date']} → {screen_meta['last_date']}"
            f"（{screen_meta['weekly_dates']} 个周频日）。"
            f"全样本过 FDR {screen_meta['n_fdr_pass']}/{screen_meta['n_tests']}，"
            f"近窗过 FDR {screen_meta['n_fdr_pass_recent']}/{screen_meta['n_tests']}。"
            "**这是本卡自己的一次预登记，没有并进 `scripts/screen_factors.py` 的 506 次检验。**"
        )
        lines.append("")
        lines.append(
            "| 因子 | 标签 | 全样本 IC | ICIR | t | 近窗 IC | 近窗 t | "
            "2018-20 | 2021-23 | 2024-26 | 符号稳定性(3 窗) | 为 0 的比例 | FDR |"
        )
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:-:|")
        for row in screen_table:
            lines.append(
                f"| `{row['factor']}` | {row['label']} | {row['ic_mean_full']:+.4f} | "
                f"{row['icir_full']:+.3f} | {row['t_full']:+.2f} | "
                f"{row['ic_mean_recent']:+.4f} | {row['t_recent']:+.2f} | "
                f"{row['ic_mean_2018_2020']:+.4f} | {row['ic_mean_2021_2023']:+.4f} | "
                f"{row['ic_mean_2024_2026']:+.4f} | {row['sign_stability_windows']:.2f} | "
                f"{row['zero_rate'] * 100:.0f}% | {'是' if row['fdr_pass'] else '否'} |"
            )
        lines.append("")
        lines.append(screen_meta["label_rank_vs_excess_note"] + "。")
        lines.append("")
    else:
        lines.append("（筛选器还没跑，先跑 `scripts/screen_insider_factors.py`。）")
        lines.append("")

    lines.append("## 第 2 步：门的定义")
    lines.append("")
    lines.append("| 门 | 满仓条件 | 不满足时 | 读的列 |")
    lines.append("|---|---|---|---|")
    for name, item in report["gate_definitions"].items():
        lines.append(
            f"| `{name}` | {item['description']} | 见左列 | "
            + ", ".join(f"`{column}`" for column in item["columns"])
            + " |"
        )
    lines.append("")
    coverage = report["insider_coverage"]
    lines.append(
        f"持仓与内部人表的对齐：{coverage['book_rows']:,} 个（调仓日，持仓）行里有 "
        f"{coverage['rows_without_insider_row']:,} 行"
        f"（{coverage['share_without_insider_row'] * 100:.3f}%）"
        "在内部人表里找不到对应行（这些按「没有可见申报」处理，即不满仓）。"
    )
    lines.append("")

    pool = report.get("pool_vs_book_gate_shares")
    if pool:
        lines.append("### 为什么这个门几乎总是「减半」（本轮最关键的一张表）")
        lines.append("")
        lines.append(
            f"同一个条件，在整个 top-500 池子里（{pool['pool_rows']:,} 个周度股票日）"
            f"和在动量 top-50 组合里（{pool['book_rows']:,} 个持仓周）的命中率："
        )
        lines.append("")
        lines.append(
            "| 门 | top-500 池子满仓占比 | 动量组合满仓占比 | 组合/池子 | 近窗池子 | 近窗组合 |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|")
        for gate, item in pool["gates"].items():
            lines.append(
                f"| `{gate}` | {_pct(item['pool_full_share'])} | "
                f"{_pct(item['book_full_share'])} | "
                f"{_fmt(item['book_over_pool_full_ratio'], '.2f')}× | "
                f"{_pct(item['pool_full_share_recent'])} | "
                f"{_pct(item['book_full_share_recent'])} |"
            )
        lines.append("")
        veto = pool["gates"]["gate_A_veto"]
        gate_a = pool["gates"]["gate_A"]
        lines.append(
            f"读法：「有内部人在买」这件事在动量 top-50 里的命中率是 "
            f"{_pct(gate_a['book_full_share'])}，只有整个池子"
            f"（{_pct(gate_a['pool_full_share'])}）的 "
            f"{_fmt(gate_a['book_over_pool_full_ratio'], '.2f')} 倍；"
            f"反过来「卖 ≥ 3 笔且无买入」在组合里命中 {_pct(veto['book_veto_share'])}，"
            f"高于池子的 {_pct(veto['pool_veto_share'])}。"
            "**动量赢家正是内部人在卖的地方，不是在买的地方。** 于是「不合格者减半」这个门"
            "在 98% 的持仓上都取「减半」，数学上等价于把整本书的暴露砍到一半再给 2% 的名字"
            "加权——这正是 L-20260916-03 说的去杠杆器，不是选择器。"
        )
        lines.append("")

    lines.append("## 对照表（2024-01-02 起的近窗，与合同 v2 同窗口）")
    lines.append("")
    lines.append(
        "| 方案 | 2024→ CAGR | 最大回撤 | 同波动 SPY 超额 | 周胜率 | 每周双边换手 | "
        "平均持仓暴露 | 平均持仓只数 | 满仓名额占比 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")

    def row(label: str, title: str) -> str:
        metrics = report["variants"][label]
        recent = metrics["recent_2024"]
        full_share = metrics.get("state_shares_recent_2024", {}).get("full")
        return (
            f"| {title} | {_pct(recent['cagr_net'])} | {_pct(recent['max_drawdown'])} | "
            f"{_pct(recent['cagr_excess_vol_matched_spy'])} | "
            f"{_pct(recent['hit_rate_weekly'])} | "
            f"{metrics['turnover_per_rebalance_mean']:.2f} | "
            f"{_pct(metrics['mean_invested_exposure'])} | "
            f"{metrics['positions_per_week_mean']:.1f} | "
            f"{'—' if full_share is None else _pct(full_share)} |"
        )

    lines.append(row("gate_off", "门关（等权基线）"))
    for gate in report["stop_conditions"]:
        lines.append(row(f"{gate}_norm", f"{gate}（**归一化**，决策口径）"))
        lines.append(row(f"{gate}_raw", f"{gate}（未归一化，余额放 BIL）"))
        aggregate = report["placebo_aggregate"].get(f"{gate}_norm")
        if aggregate is not None:
            lines.append(
                f"| {gate}（归一化，占位 {aggregate['seeds']} 个种子均值） | "
                f"{_pct(aggregate['cagr_recent_mean'])} | "
                f"{_pct(aggregate['max_drawdown_recent_mean'])} | "
                f"{_pct(aggregate['cagr_excess_vol_matched_spy_mean'])} | "
                f"{_pct(aggregate['hit_rate_weekly_mean'])} | "
                f"{aggregate['turnover_per_rebalance_mean']:.2f} | "
                f"{_pct(aggregate['mean_invested_exposure'])} | "
                f"{aggregate['positions_per_week_mean']:.1f} | "
                f"{_pct(aggregate['gated_in_share_mean'])} |"
            )
    lines.append(
        f"| SPY | {_pct(reference['SPY']['cagr'])} | {_pct(reference['SPY']['max_drawdown'])} | "
        f"基准 | {_pct(reference['SPY']['weekly_hit_rate'])} | 0 | 100% | — | — |"
    )
    lines.append(
        f"| MTUM | {_pct(reference['MTUM']['cagr'])} | "
        f"{_pct(reference['MTUM']['max_drawdown'])} | — | "
        f"{_pct(reference['MTUM']['weekly_hit_rate'])} | 0 | 100% | — | — |"
    )
    lines.append(
        f"| SPMO | {_pct(reference['SPMO']['cagr'])} | "
        f"{_pct(reference['SPMO']['max_drawdown'])} | — | "
        f"{_pct(reference['SPMO']['weekly_hit_rate'])} | 0 | 100% | — | — |"
    )
    lines.append("")
    lines.append(
        f"SPY/MTUM/SPMO 三行取自合同 v2 的 `reference_disclosures`（{reference['window']}），"
        "不是这里重算的。"
    )
    lines.append("")

    lines.append("## 全样本外窗口（2017 起）与 H-03 可比窗（2020Q2 起）")
    lines.append("")
    lines.append(
        "| 方案 | 2017→ CAGR | 2017→ 最大回撤 | 2017→ 同波动超额 | "
        "2020Q2→ CAGR | 2020Q2→ 最大回撤 | 2020Q2→ 同波动超额 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for label, title in [("gate_off", "门关（等权基线）")] + [
        (f"{gate}_{suffix}", f"{gate}（{'归一化' if suffix == 'norm' else '未归一化'}）")
        for gate in report["stop_conditions"]
        for suffix in ("norm", "raw")
    ]:
        metrics = report["variants"][label]
        full = metrics["full_oos"]
        h03 = metrics["h03_comparable"]
        lines.append(
            f"| {title} | {_pct(full['cagr_net'])} | {_pct(full['max_drawdown'])} | "
            f"{_pct(full['cagr_excess_vol_matched_spy'])} | {_pct(h03['cagr_net'])} | "
            f"{_pct(h03['max_drawdown'])} | {_pct(h03['cagr_excess_vol_matched_spy'])} |"
        )
    lines.append("")

    lines.append("## 门的状态分布与切换频率")
    lines.append("")
    lines.append("| 门 | 满仓 | 减半 | 剔除 | 近窗满仓 | 门改动过的调仓周（逐年） |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for gate in report["stop_conditions"]:
        metrics = report["variants"][f"{gate}_norm"]
        shares = metrics["state_shares"]
        recent = metrics["state_shares_recent_2024"]
        switches = metrics["rebalances_with_gate_change_per_year"]
        lines.append(
            f"| `{gate}` | {_pct(shares.get('full'))} | {_pct(shares.get('half'))} | "
            f"{_pct(shares.get('veto'))} | {_pct(recent.get('full'))} | "
            + ", ".join(f"{year}:{count}" for year, count in sorted(switches.items()))
            + " |"
        )
    lines.append("")
    lines.append(
        "「门改动过的调仓周」= 该年有多少个调仓周里，门给至少一只持仓的权重与它上一次"
        "被持有时的状态不同。逐股状态变化的原始计数在 `step2-twin-report.json` 的 "
        "`gate_state_changes_per_year` 里。"
    )
    lines.append("")

    baseline_excess = report["variants"]["gate_off"]["recent_2024"]["cagr_excess_vol_matched_spy"]

    def control_table(aggregate_key: str, title: str, note: str) -> None:
        aggregates = report.get(aggregate_key) or {}
        if not aggregates:
            return
        lines.append(f"## {title}")
        lines.append("")
        lines.append(note)
        lines.append("")
        lines.append("| 门（口径） | 种子数 | 真实改善 | 对照改善均值 | 最小 | 最大 | 对照/真实 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for label, aggregate in aggregates.items():
            real_improvement = (
                report["variants"][label]["recent_2024"]["cagr_excess_vol_matched_spy"]
                - baseline_excess
            )
            ratio = (
                aggregate["improvement_mean"] / real_improvement if real_improvement > 0 else None
            )
            lines.append(
                f"| `{label}` | {aggregate['seeds']} | {real_improvement * 100:+.1f} pp | "
                f"{aggregate['improvement_mean'] * 100:+.1f} pp | "
                f"{aggregate['improvement_min'] * 100:+.1f} pp | "
                f"{aggregate['improvement_max'] * 100:+.1f} pp | "
                f"{_fmt(ratio, '.2f') if ratio is not None else '不适用（真实改善 ≤ 0）'} |"
            )
        lines.append("")

    control_table(
        "placebo_aggregate",
        "占位一：申报日随机平移 ±30 个交易日（卡上的占位，每门 5 个种子）",
        "每个种子重建一整套内部人特征（写到各自的目录，真表从不被覆盖），再用同一套门重跑。"
        "**这个占位对 60 日计数类列是弱破坏**：它们的周度截面秩自相关是 0.93–0.97，"
        "平移 ≤ 30 个交易日后窗口内容只变了一部分。所以「占位仍在」只是弱证据，"
        "「占位被打掉」才是强证据。",
    )
    control_table(
        "shuffle_aggregate",
        "占位二：周内打乱门的标签（附加对照，保持暴露与集中度不变）",
        "把门给出的 满仓/减半/剔除 标签在每个调仓周内部随机重排：每周满仓几只、剔除几只"
        "完全不变，因此归一化后的总暴露、持仓只数、换手都不变，**只有「是哪几只」被随机化**。"
        "这是唯一能把「门挑对了名字」和「把 50 只换成 21 只随机股票本身就会这样」分开的对照。"
        "它不在卡上的五条判据里，作为必报披露列出。",
    )

    lines.append("## 否定判据（卡上写死的五条，任一命中即停；只看归一化口径）")
    lines.append("")
    for gate, conditions in report["stop_conditions"].items():
        lines.append(f"### {gate}")
        lines.append("")
        for name, item in conditions.items():
            lines.append(f"- **{item['verdict']}** `{name}`：{item['detail']}")
        lines.append("")

    lines.append("## 数据口径与需要知道的坑")
    lines.append("")
    for caveat in report["caveats"]:
        lines.append(f"- {caveat}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "stage", choices=["export", "gate-states", "prefiling", "evaluate", "report"]
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--sources",
        nargs="*",
        default=None,
        help="gate-states only: real / placebo{seed} (default: real + every built placebo seed)",
    )
    args = parser.parse_args(argv)
    if args.stage == "export":
        stage_export(force=args.force)
    elif args.stage == "gate-states":
        sources = args.sources or ["real", *(f"placebo{seed}" for seed in PLACEBO_SEEDS)]
        stage_gate_states(force=args.force, sources=sources)
    elif args.stage == "prefiling":
        stage_prefiling(force=args.force)
    elif args.stage == "report":
        stage_report()
    else:
        stage_evaluate(force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
