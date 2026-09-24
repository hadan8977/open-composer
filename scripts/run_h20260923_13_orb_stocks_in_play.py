"""H-20260923-13, Stocks-in-Play ORB: individual-stock opening-range breakout
filtered by opening relative volume ("Stocks in Play", Zarattini, Barbon & Aziz,
SSRN 4729284).

Iteration dossier: ``reports/research/iterations/h20260923_13_orb_stocks_in_play/``
(frozen, passed ``oc research iteration validate --stage pre-backtest``). This
script implements ``engine-design.md``'s Stage 0-3 plan; do not change any
preregistered rule, parameter, window, candidate or gate -- candidate
parameters, cost levels and windows are loaded at runtime from
``candidate-manifest.json`` / ``cost-contract.json`` / this module's own
``WINDOWS`` (transcribed once from ``search-space.json``), and the seven
adoption-rule gates are parsed from the hypothesis card's own YAML frontmatter
(``reports/research/hypotheses/H-20260923-13-orb-stocks-in-play.md``), not
retyped, so evaluation is provably tied to the preregistered text.

Rule (see ``hypotheses.md`` and ``candidate-manifest.json`` for the full text)
-------------------------------------------------------------------------------
* Opening range = the five 1-minute bars 09:30:00-09:34:59 ET.
* Doji = ``open == close`` exactly in the opening range -> no order that day
  for the real candidate (the paper's own rule; a disclosed correction of the
  5%-band approximation ``scripts/run_h20260918_02_orb_etf.py`` used).
* Direction = sign(close - open) of the opening range, when not a doji.
* Entry = a **stop order** at the opening range's own extreme in that
  direction (buy-stop at the range high if bullish, sell-stop at the range low
  if bearish), active from 09:35 ET through end of session. Filled at the
  trigger price, or at the bar's own open if that bar gaps through the
  trigger (worse fill, conservative).
* Protective stop-loss = 10% of 14-day ATR from the entry price (**not** the
  opposite extreme of the candle -- this differs from the ETF-ORB script).
  Same bar as entry, or the session's last bar, resolved conservatively: the
  stop is checked before falling through to an EOD close. A one-bar-late
  variant (protective stop not live until the bar after entry) is reported
  alongside, per the QuantConnect forum's reported backtest/live discrepancy.
* Exit at the stop or end of session, whichever first. **No profit target**
  (the paper's individual-stock section describes none; a disclosed removal
  of the ETF script's 10R target, added there by analogy from a different
  paper).
* Selection: each day, rank symbols passing price/avg-volume/ATR/relative-
  volume floors by relative volume (today's opening-range volume / mean of
  the same window over the trailing 14 trading days) and trade only the top
  20 (SIP01/SIP02) or the paper's own floors with both directions active
  (SIP03, long-short, never promotable, fidelity check only).
* Sizing: 1% of an equal split slot (equity / 20) risked per trade, notional
  capped at ``leverage_cap * slot_capital`` (1.0x house default for
  SIP01/SIP02, the paper's own 4x for SIP03); equity compounds once per day
  across the day's (up to 20) concurrent names.
* Costs: 5/10/20 bp per side on notional (all reported) plus a **separate,
  not-blended** ``$0.0035``/share commission cross-check column; design-window
  gate (d) additionally evaluates 20bp *and* the commission stacked together.

Data-loading design (Stage 0-3, mirrors ``engine-design.md``)
-------------------------------------------------------------------------------
``stage 0``    Lightweight diligence: confirm both minute archives and the
               daily archive exist and cover the proposed windows, and run the
               named pre-market-prints probe. No hand-built shard index is
               written (see "Deviation from engine-design.md" below).
``stage 1``    Per calendar year, two DuckDB passes over the *whole* minute
               archive for that year, aggregated to tiny per-(symbol, day)
               tables entirely inside DuckDB (never materializing raw minute
               rows in pandas): the opening-range candle (open/high/low/close/
               volume, ``cache/opening_bars/<year>.parquet``) and, from
               ``data/sip/daily`` (one unified archive, 2016-2026), each
               symbol's trailing-14-trading-day ATR/average-volume/prior-close
               eligibility inputs (``cache/daily_eligibility/<year>.parquet``).
               Shard files are read in small batches (``SHARD_BATCH_SIZE``)
               to stay under the DuckDB connection's own memory_limit.
``stage 2``    Per (screen, window): pure arithmetic over the Stage 1 cache --
               apply eligibility floors, compute relative volume, rank, and
               select the real top-20 and 10 RL (random-liquid-non-in-play)
               seeds' draws from the eligible-but-not-top-20 remainder.
               Candidates with identical eligibility+ranking parameters share
               one "screen" (SIP01 and SIP03 share the paper's own floors;
               SIP02 has its own stricter floor), so ranking is computed once,
               not three times.
``stage 3``    Per (screen, window): for each session day, fetch that day's
               *full* intraday path (09:35 through session close) only for the
               day's selected symbols (real top-20 union all 10 RL seeds'
               draws -- roughly 20-150 symbols/day, not the ~13,000-symbol
               universe), and resolve the stop-order-trigger-then-protective-
               stop walk for both directions and both stop-fill variants.
``report``     Per-candidate/control portfolio-equity simulation (pure
               arithmetic over the Stage 3 cache, cheap enough to re-derive on
               every invocation) across the cost/stop-fill grid, gate
               evaluation against the hypothesis card's own frontmatter
               criteria, ``trial-ledger.jsonl``, ``summary.json`` and
               ``report.md``.

Deviation from ``engine-design.md``: no hand-built symbol-to-shard manifest
-------------------------------------------------------------------------------
``engine-design.md`` sketches a hand-built ``symbol -> shard`` JSON index (one
per archive) so Stage 3 can find a specific symbol's file quickly. This script
does not build one. Two reasons: (1) Stage 1 does not need one at all -- it
scans *every* shard file for the requested year via a plain filesystem glob
(no symbol lookup), so the disclosed staleness of ``data/sip/minute/
_LAYOUT.json``'s ``shard_symbols`` index for shards <=316/year never enters
Stage 1's path. (2) Stage 3's per-day, per-symbol-list reads reuse
``open_composer.adapters.data.sip_parquet.load_sip_bars`` (already imported
by the ETF-ORB script for its own benchmark loads), passing ``root=data/sip``
or ``root=data/sip-hist`` as appropriate -- its shard selection reads each
shard file's own parquet-footer ``symbol`` min/max statistics directly
(``_shard_symbol_range``), not the separate, disclosed-stale ``_LAYOUT.json``
index, so it is immune to that staleness by construction and needs no
duplicate index. This is an implementation-strategy choice, not a change to
any preregistered rule, parameter, window, candidate or gate; both minute
archives and the unified 2016-2026 daily archive were confirmed to exist by
directory listing before this script was written.

Stages are resumable from ``reports/research/iterations/
h20260923_13_orb_stocks_in_play/cache/`` (Stage 1: per year; Stage 2/3: per
(screen, window) -- the task's own natural resumability unit, since the
select and 2026 windows are run and reported together, then the design
window separately). Every heavy stage should run through
``scripts/run_capped.sh`` on this 3.9GB box.

Usage::

    ./scripts/run_capped.sh --mem 1.2G -- \\
        uv run python scripts/run_h20260923_13_orb_stocks_in_play.py \\
        --stage 1 --windows select report_2026
"""

from __future__ import annotations

import argparse
import glob as glob_module
import json
import math
import sys
import time
from datetime import date, datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from open_composer.adapters.data.sip_parquet import (  # noqa: E402
    BAR_COLUMNS,
    SipParquetError,
    _finalize,
    _range_can_contain,
    _read_shard,
    _shard_symbol_range,
    _utc_timestamp,
    load_sip_bars,
)
from open_composer.market_calendar import (  # noqa: E402
    NEW_YORK,
    us_equity_session_close,
    us_equity_session_dates,
)
from open_composer.research.kernel.mechanism_eval import annualized_cagr, max_drawdown  # noqa: E402

ITERATION_ID = "h20260923_13_orb_stocks_in_play"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = OUT_DIR / "cache"
OPENING_DIR = CACHE_DIR / "opening_bars"
DAILY_DIR = CACHE_DIR / "daily_eligibility"
SELECTIONS_DIR = CACHE_DIR / "selections"
OUTCOMES_DIR = CACHE_DIR / "outcomes"
STAGE0_PATH = CACHE_DIR / "stage0_diligence.json"
TRIAL_LEDGER_PATH = OUT_DIR / "trial-ledger.jsonl"
REPORT_PATH = OUT_DIR / "report.md"
SUMMARY_PATH = OUT_DIR / "summary.json"
DECISION_RECORD_PATH = OUT_DIR / "decision-record.md"
HYPOTHESIS_CARD_PATH = (
    ROOT / "reports" / "research" / "hypotheses" / "H-20260923-13-orb-stocks-in-play.md"
)
CANDIDATE_MANIFEST_PATH = OUT_DIR / "candidate-manifest.json"
COST_CONTRACT_PATH = OUT_DIR / "cost-contract.json"

SIP_ROOT = ROOT / "data" / "sip"
SIP_HIST_ROOT = ROOT / "data" / "sip-hist"

#: Frozen windows, transcribed once from search-space.json / candidate-manifest.json.
WINDOWS: dict[str, tuple[date, date]] = {
    "design": (date(2016, 1, 4), date(2022, 12, 30)),
    "select": (date(2023, 9, 18), date(2025, 12, 31)),
    "report_2026": (date(2026, 1, 2), date(2026, 9, 17)),
}
WINDOW_ORDER: tuple[str, ...] = ("select", "report_2026", "design")
FROZEN_SELECT_WINDOW = "select"  # the only window that ranks a candidate

SEED_COUNT = 10
RD_SEEDS: tuple[int, ...] = tuple(range(1, SEED_COUNT + 1))
RL_SEEDS: tuple[int, ...] = tuple(range(1, SEED_COUNT + 1))

MAX_POSITIONS = 20
ATR_LOOKBACK_DAYS = 14
AVG_VOLUME_LOOKBACK_DAYS = 14
RELVOL_LOOKBACK_DAYS = 14
BORROW_ANNUAL_RATE = 0.003  # SIP03 short legs only; matches the ETF-ORB convention
MINUTES_PER_YEAR = 365.0 * 24.0 * 60.0

#: NY-local minute-of-day bounds for the opening range, 09:30:00-09:34:59 ET.
#: Filtering must convert each row's own timestamp to NY local time (DuckDB's
#: ``timezone('America/New_York', timestamp)``, which resolves DST per row
#: from the row's own date) rather than testing a fixed UTC clock-time band:
#: an earlier version of this query tested "UTC time-of-day in {EDT band} OR
#: {EST band}" on the mistaken assumption that only one band could have
#: matching rows on a given date. That is false -- both bands fall within
#: continuous regular trading hours (09:30-16:00 ET) or the pre-market window
#: (confirmed present in this archive by Stage 0's diligence probe), so on an
#: EDT date the "EST band" (14:30-14:34 UTC = 10:30-10:34 ET, forty minutes
#: into the *regular* session) matched real bars too, and vice versa for
#: pre-market on EST dates -- corrupting the aggregated candle (bar_count up
#: to 10, volume summed across two unrelated 5-minute windows, open/close
#: picked via MAX over whichever window's bar happened to be numerically
#: larger). Caught 2026-09-23 before any Stage 2/3 work consumed the bad
#: cache; see the regression tests in tests/test_run_h20260923_13_orb_script.py.
_OPEN_RANGE_START_MINUTE = 9 * 60 + 30
_OPEN_RANGE_END_MINUTE = 9 * 60 + 34

#: shard files per DuckDB query. Per-file overhead (connection setup, file
#: open/footer-read cost) dominates at small batch sizes -- measured
#: 2026-09-23 against real 2024 shards: ~58ms/file at 60 files/batch,
#: 18ms/file at 900 files/batch (peak RSS 342MB, well under the connection's
#: own 700MB memory_limit below). 900 is picked from that measurement, not
#: guessed.
SHARD_BATCH_SIZE = 900

#: cost variants reported for every (candidate/control, window); the fifth
#: ("20bp_plus_commission") is not an independent report column -- it exists
#: only to evaluate design-window gate (d), which is stacked per the card.
COST_VARIANT_ORDER: tuple[str, ...] = (
    "5bp",
    "10bp",
    "20bp",
    "commission_only",
    "20bp_plus_commission",
)
PRIMARY_COST_VARIANT = "10bp"
STOP_FILL_VARIANTS: tuple[str, ...] = ("same_bar_conservative", "one_bar_late")
PRIMARY_STOP_FILL_VARIANT = "same_bar_conservative"

#: published reference numbers, quoted in hypotheses.md; long+short combined,
#: no long-only split ever published -- kept next to our long-only SIP01/SIP02
#: results with that caveat repeated in report.md, never blended into them.
PUBLISHED_REFERENCE = {
    "paper_headline_long_short": {
        "total_return": 16.37,
        "annualized_return": 0.416,
        "sharpe": 2.81,
        "max_drawdown": -0.12,
        "note": "Zarattini/Barbon/Aziz SSRN 4729284, 2016-2023, long+short combined, "
        "no long-only split ever published, zero-slippage MATLAB backtest, $0.0035/share "
        "commission only (no bps).",
    },
    "paper_base_no_relvol_filter": {
        "total_return": 0.29,
        "sharpe": 0.48,
        "note": "same paper, same window, relative-volume filter removed.",
    },
    "spy_buy_and_hold_paper_window": {
        "total_return": 1.98,
        "sharpe": 0.78,
        "note": "same paper, same 2016-2023 window.",
    },
    "quantconnect_replication_2016_only": {
        "sharpe": 2.396,
        "spy_sharpe": 0.836,
        "note": "independent QuantConnect replication, 2016 only, top-1000-liquid universe.",
    },
    "etf_orb_known_negative_oos": {
        "note": "dir:orb_etf_opening_range_breakout OOS 2024-01-02..2026-09-17: QQQ -3.0%, "
        "SPY -6.0% annualized; random-direction placebo captured 92.7-92.9% of real return. "
        "Reused as a reference floor, not re-simulated here.",
    },
}

_T0 = time.time()


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')} +{time.time() - _T0:7.1f}s] {message}", flush=True)


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp | datetime | date):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.bool_):
        return bool(value)
    raise TypeError(f"not JSON serializable: {type(value)}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n")


# --------------------------------------------------------------------------
# preregistered inputs, loaded at runtime (never retyped/hardcoded)
# --------------------------------------------------------------------------


def load_candidate_manifest() -> dict[str, dict[str, Any]]:
    payload = json.loads(CANDIDATE_MANIFEST_PATH.read_text(encoding="utf-8"))
    return {row["candidate_id"]: row for row in payload["candidates"]}


def load_cost_contract() -> dict[str, Any]:
    return json.loads(COST_CONTRACT_PATH.read_text(encoding="utf-8"))


def load_gate_criteria() -> list[dict[str, Any]]:
    text = HYPOTHESIS_CARD_PATH.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{HYPOTHESIS_CARD_PATH} has no YAML frontmatter")
    _, frontmatter, _ = text.split("---", 2)
    payload = yaml.safe_load(frontmatter)
    criteria = payload.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError(f"{HYPOTHESIS_CARD_PATH} frontmatter has no criteria list")
    return criteria


def screen_key(params: dict[str, Any]) -> tuple[Any, ...]:
    return (
        params["price_floor_usd"],
        params["avg_volume_floor_shares_per_day"],
        params["atr_floor_usd"],
        params["relative_volume_floor"],
        params["top_n_by_relative_volume"],
    )


def build_screens(candidates: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """``screen_id -> [candidate_ids]`` for candidates sharing one eligibility +
    ranking rule (SIP01 and SIP03 share the paper's own floors; only trade
    mechanics -- allow_short, leverage_cap -- differ between them)."""
    groups: dict[tuple[Any, ...], list[str]] = {}
    for candidate_id in sorted(candidates):
        key = screen_key(candidates[candidate_id]["parameters"])
        groups.setdefault(key, []).append(candidate_id)
    return {f"screen_{'_'.join(ids).lower()}": ids for ids in groups.values()}


def cost_variant_table(cost_contract: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """``cost_variant -> (bps_per_side, commission_per_share)``."""
    commission = float(cost_contract["commission_per_share_paper_fidelity_cross_check"])
    grid = cost_contract["slippage_bps_per_side_grid"]
    table: dict[str, tuple[float, float]] = {}
    for bps in grid:
        table[f"{int(bps)}bp"] = (float(bps), 0.0)
    table["commission_only"] = (0.0, commission)
    stress_bps = float(cost_contract["stress_bps_per_side"])
    table["20bp_plus_commission"] = (stress_bps, commission)
    return table


def years_for_window(window_name: str) -> tuple[int, ...]:
    start, end = WINDOWS[window_name]
    years = list(range(start.year, end.year + 1))
    if window_name == "report_2026":
        years = [start.year - 1, *years]  # December lookback for relative volume
    return tuple(years)


def years_for_windows(window_names: tuple[str, ...]) -> tuple[int, ...]:
    years: set[int] = set()
    for name in window_names:
        years.update(years_for_window(name))
    return tuple(sorted(years))


# --------------------------------------------------------------------------
# Stage 0: lightweight diligence (no hand-built shard index; see docstring)
# --------------------------------------------------------------------------


def stage0_diligence(force: bool) -> dict[str, Any]:
    if STAGE0_PATH.exists() and not force:
        _log(f"stage0: cache present ({STAGE0_PATH}) -- reusing (pass --force to rebuild)")
        return json.loads(STAGE0_PATH.read_text(encoding="utf-8"))

    def _years_present(path: Path) -> list[int]:
        if not path.is_dir():
            return []
        return sorted(int(p.name) for p in path.iterdir() if p.is_dir() and p.name.isdigit())

    findings: dict[str, Any] = {
        "sip_minute_years": _years_present(SIP_ROOT / "minute"),
        "sip_hist_minute_years": _years_present(SIP_HIST_ROOT / "minute"),
        "sip_daily_years": _years_present(SIP_ROOT / "daily"),
    }
    try:
        probe = load_sip_bars(
            ["AAPL"],
            frequency="minute",
            start=pd.Timestamp(2024, 1, 3),
            end=pd.Timestamp(2024, 1, 3, 23, 59, 59),
            allow_missing=True,
        )
    except SipParquetError as exc:
        findings["premarket_probe_error"] = str(exc)
        probe = pd.DataFrame()
    if not probe.empty:
        ny_time = probe["timestamp"].dt.tz_convert(NEW_YORK).dt.time
        findings.update(
            {
                "premarket_probe_symbol": "AAPL",
                "premarket_probe_date": "2024-01-03",
                "premarket_probe_total_rows": int(len(probe)),
                "premarket_probe_rows_before_0930_et": int((ny_time < dt_time(9, 30)).sum()),
                "premarket_probe_earliest_et_time": str(min(ny_time)),
            }
        )
    else:
        findings["premarket_probe_rows_before_0930_et"] = None
    findings["generated_at"] = datetime.now(NEW_YORK).isoformat()
    _write_json(STAGE0_PATH, findings)
    _log(f"stage0: wrote {STAGE0_PATH}")
    return findings


# --------------------------------------------------------------------------
# Stage 1: per-year opening-range + daily-eligibility caches
# --------------------------------------------------------------------------


def _minute_shard_files_for_year(year: int) -> list[Path]:
    """The month-sharded layout's shard files for one year, falling back to
    the legacy whole-year glob only when no month directory exists at all.

    CORRECTION (2026-09-24, second pass -- see module docstring): an earlier
    version of this fix (same day) preferred the month layout *exclusively*
    whenever a month directory existed at all, on the assumption --
    inherited from this repo's own ``scripts/build_news_hf_reaction.py`` and
    from ``sip_parquet.py``'s docstring -- that the legacy and month layouts
    hold the *same* bars for a year that has both. Verified false for 2023
    specifically by direct footer inspection: AAPL and AMD (and likely
    others) have zero rows across all 801 September-2023 month-dir shards
    but are present in the legacy ``shard-0001.parquet``. The
    month-exclusive version silently dropped those symbols from the whole
    2023 opening_bars cache with no error (``bar_count`` stayed <= 5 because
    the row was simply absent, not corrupted) -- caught only because a
    parallel Stage 3 fetch built on the same wrong assumption returned a
    different symbol set than a direct ``load_sip_bars`` call for the same
    day. Every other archive year (2016-2022, 2024-2026) has *no* loose
    year-level shard files at all -- verified directly -- so this function's
    behavior is unchanged for them. For 2023, this function still returns
    only the month layout; :func:`stage1_opening_bars` separately aggregates
    :func:`_minute_shard_files_for_year_legacy_only`'s files and fills in
    only the (symbol, session_date) keys missing from the month-derived
    result, rather than reading both layers as one undifferentiated batch."""
    root = SIP_HIST_ROOT if year <= 2022 else SIP_ROOT
    year_dir = root / "minute" / str(year)
    if not year_dir.is_dir():
        return []
    month_dirs = sorted(p for p in year_dir.iterdir() if p.is_dir() and p.name.isdigit())
    if month_dirs:
        files: list[Path] = []
        for month_dir in month_dirs:
            files.extend(sorted(month_dir.glob("shard-*.parquet")))
        return files
    return sorted(year_dir.glob("shard-*.parquet"))


def _minute_shard_files_for_year_legacy_only(year: int) -> list[Path]:
    """The legacy whole-year shards for ``year``, only when a month-sharded
    layout *also* exists (see :func:`_minute_shard_files_for_year`'s
    docstring for why this is needed at all). Returns ``[]`` when there is
    no month directory, since in that case ``_minute_shard_files_for_year``
    already uses the legacy glob as its primary (only) source."""
    root = SIP_HIST_ROOT if year <= 2022 else SIP_ROOT
    year_dir = root / "minute" / str(year)
    if not year_dir.is_dir():
        return []
    has_month_dirs = any(p.is_dir() and p.name.isdigit() for p in year_dir.iterdir())
    if not has_month_dirs:
        return []
    return sorted(year_dir.glob("shard-*.parquet"))


def _chunked(items: list[Path], size: int) -> list[list[Path]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


#: ``union_by_name=True`` is required: some shards are empty-fetch-window
#: placeholders with only a ``(symbol, timestamp)`` schema (0 rows, no
#: open/high/low/close/volume columns at all -- confirmed by direct footer
#: inspection, e.g. ``data/sip/minute/2023/01/shard-0868.parquet``). Without
#: it, DuckDB refuses to glob/list files with different schemas at all;
#: with it, the missing columns become NULL for those (zero) rows, which
#: ``WHERE volume > 0`` then naturally excludes.
_OPENING_RANGE_SQL = f"""
    WITH tagged AS (
        SELECT
            symbol,
            open, high, low, close, volume,
            timezone('America/New_York', timestamp) AS ny_local
        FROM read_parquet(?, union_by_name = true)
        WHERE volume > 0
    ), banded AS (
        SELECT
            symbol, ny_local, open, high, low, close, volume,
            (EXTRACT(hour FROM ny_local)::INTEGER * 60
                + EXTRACT(minute FROM ny_local)::INTEGER) AS ny_minute_of_day
        FROM tagged
    ), opening AS (
        SELECT
            symbol, ny_local, open, high, low, close, volume,
            ny_minute_of_day - {_OPEN_RANGE_START_MINUTE} AS bar_idx
        FROM banded
        WHERE ny_minute_of_day BETWEEN {_OPEN_RANGE_START_MINUTE} AND {_OPEN_RANGE_END_MINUTE}
    )
    SELECT
        symbol,
        CAST(ny_local AS DATE) AS session_date,
        MAX(CASE WHEN bar_idx = 0 THEN open END) AS candle_open,
        MAX(CASE WHEN bar_idx = 4 THEN close END) AS candle_close,
        MAX(high) AS candle_high,
        MIN(low) AS candle_low,
        SUM(volume) AS candle_volume,
        COUNT(*) AS bar_count
    FROM opening
    GROUP BY symbol, CAST(ny_local AS DATE)
"""

_OPENING_BAR_COLUMNS = [
    "symbol",
    "session_date",
    "candle_open",
    "candle_close",
    "candle_high",
    "candle_low",
    "candle_volume",
    "bar_count",
]


def _opening_bar_cache_path(year: int) -> Path:
    return OPENING_DIR / f"{year}.parquet"


def _aggregate_opening_bars(files: list[Path], year: int, label: str) -> pd.DataFrame:
    """Batch ``files`` through ``_OPENING_RANGE_SQL`` and return the
    combined, deduplicated, bar_count-checked (symbol, session_date) frame.
    ``label`` is just for logging (e.g. ``"month"`` vs ``"legacy"``, see
    :func:`stage1_opening_bars`)."""
    if not files:
        return pd.DataFrame(columns=_OPENING_BAR_COLUMNS)
    batches = _chunked(files, SHARD_BATCH_SIZE)
    frames: list[pd.DataFrame] = []
    t_year = time.time()
    for index, batch in enumerate(batches):
        t0 = time.time()
        con = duckdb.connect()
        try:
            con.execute("SET TimeZone='UTC'")
            con.execute("SET memory_limit='700MB'")
            con.execute("SET threads=2")
            chunk = con.execute(_OPENING_RANGE_SQL, [[str(p) for p in batch]]).fetchdf()
        finally:
            con.close()
        frames.append(chunk)
        if (index + 1) % 10 == 0 or (index + 1) == len(batches):
            total_rows = sum(len(f) for f in frames)
            _log(
                f"stage1-opening: {year} ({label}) batch {index + 1}/{len(batches)}: "
                f"{total_rows:,} symbol-days so far, {time.time() - t0:.1f}s last batch, "
                f"{time.time() - t_year:.1f}s elapsed"
            )
    combined = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=_OPENING_BAR_COLUMNS)
    )
    if not combined.empty:
        combined["session_date"] = pd.to_datetime(combined["session_date"])
        # kind="stable" makes the keep="last" choice deterministic across
        # runs if a shard set ever has a genuine duplicate key internally.
        combined = combined.sort_values(["symbol", "session_date"], kind="stable")
        combined = combined.drop_duplicates(subset=["symbol", "session_date"], keep="last")
        bad = combined[combined["bar_count"] > 5]
        if not bad.empty:
            raise ValueError(
                f"stage1-opening: {year} ({label}): {len(bad)} symbol-day rows have "
                f"bar_count > 5 (max {int(bad['bar_count'].max())}) -- the opening-range "
                "time filter let in bars outside 09:30:00-09:34:59 ET; this is the exact "
                "DST-band corruption this query was fixed against, do not write this cache"
            )
    return combined


def stage1_opening_bars(years: tuple[int, ...], force: bool) -> None:
    OPENING_DIR.mkdir(parents=True, exist_ok=True)
    for year in years:
        out_path = _opening_bar_cache_path(year)
        if out_path.exists() and not force:
            _log(f"stage1-opening: {year} cache present -- reusing (pass --force to rebuild)")
            continue
        files = _minute_shard_files_for_year(year)
        if not files:
            _log(f"stage1-opening: {year}: no minute shards found -- skipped")
            pd.DataFrame(columns=_OPENING_BAR_COLUMNS).to_parquet(out_path, index=False)
            continue
        t_year = time.time()
        combined = _aggregate_opening_bars(files, year, "month")
        # 2026-09-24 fix (see _minute_shard_files_for_year's docstring): for
        # a year with both layouts (2023 only -- verified for every other
        # year), the month layout is not a strict superset of the legacy
        # one (AAPL/AMD proved entirely absent from the September 2023
        # month shards). Aggregate the legacy shards separately and fill in
        # only the (symbol, session_date) keys the month pass never
        # produced, rather than unioning raw bars (which would need a
        # source-priority tiebreak the archive gives no clean way to make,
        # and would reintroduce the double-counting this query was already
        # fixed against for genuine overlaps).
        legacy_files = _minute_shard_files_for_year_legacy_only(year)
        if legacy_files:
            legacy_combined = _aggregate_opening_bars(legacy_files, year, "legacy")
            if not legacy_combined.empty:
                if combined.empty:
                    combined = legacy_combined
                else:
                    have = combined[["symbol", "session_date"]].drop_duplicates()
                    marked = legacy_combined.merge(
                        have, on=["symbol", "session_date"], how="left", indicator=True
                    )
                    extra = legacy_combined[marked["_merge"].to_numpy() == "left_only"]
                    if not extra.empty:
                        _log(
                            f"stage1-opening: {year}: {len(extra):,} symbol-day rows found only "
                            "in the legacy whole-year shards (absent from every month-sharded "
                            "shard) -- adding them rather than silently dropping those symbol-days"
                        )
                        combined = pd.concat([combined, extra], ignore_index=True)
        combined.to_parquet(out_path, index=False)
        _log(
            f"stage1-opening: {year}: wrote {len(combined):,} symbol-day rows -> {out_path} "
            f"({time.time() - t_year:.1f}s total)"
        )


_DAILY_SQL = """
    SELECT symbol, CAST(timestamp AS DATE) AS session_date, high, low, close, volume
    FROM read_parquet(?, union_by_name = true)
    WHERE volume > 0
"""


def _daily_cache_path(year: int) -> Path:
    return DAILY_DIR / f"{year}.parquet"


def _load_daily_year_raw(year: int) -> pd.DataFrame:
    pattern = str(SIP_ROOT / "daily" / str(year) / "shard-*.parquet")
    if not glob_module.glob(pattern):
        return pd.DataFrame(columns=["symbol", "session_date", "high", "low", "close", "volume"])
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone='UTC'")
        con.execute("SET memory_limit='700MB'")
        con.execute("SET threads=2")
        return con.execute(_DAILY_SQL, [pattern]).fetchdf()
    finally:
        con.close()


def stage1_daily_eligibility(years: tuple[int, ...], force: bool) -> None:
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    for year in years:
        out_path = _daily_cache_path(year)
        if out_path.exists() and not force:
            _log(f"stage1-daily: {year} cache present -- reusing (pass --force to rebuild)")
            continue
        t0 = time.time()
        frames = [_load_daily_year_raw(y) for y in (year - 1, year)]
        frames = [f for f in frames if not f.empty]
        if not frames:
            _log(f"stage1-daily: {year}: no daily shards -- skipped")
            pd.DataFrame(
                columns=[
                    "symbol",
                    "session_date",
                    "close",
                    "eligibility_price",
                    "atr14",
                    "avg_volume14",
                ]
            ).to_parquet(out_path, index=False)
            continue
        combined = pd.concat(frames, ignore_index=True)
        combined["session_date"] = pd.to_datetime(combined["session_date"])
        combined = combined.drop_duplicates(subset=["symbol", "session_date"], keep="last")
        combined = combined.sort_values(["symbol", "session_date"])
        grouped = combined.groupby("symbol", sort=False)
        prev_close = grouped["close"].shift(1)
        true_range = pd.concat(
            [
                combined["high"] - combined["low"],
                (combined["high"] - prev_close).abs(),
                (combined["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        combined = combined.assign(prev_close=prev_close, true_range=true_range)
        # "known before the open": ATR14/avg-volume14 as of day t use only
        # days t-14..t-1 (rolling(14) then shift(1) to drop day t itself);
        # the eligibility price is simply the prior close.
        combined["atr14"] = combined.groupby("symbol", sort=False)["true_range"].transform(
            lambda s: s.rolling(ATR_LOOKBACK_DAYS).mean().shift(1)
        )
        combined["avg_volume14"] = combined.groupby("symbol", sort=False)["volume"].transform(
            lambda s: s.rolling(AVG_VOLUME_LOOKBACK_DAYS).mean().shift(1)
        )
        combined["eligibility_price"] = combined["prev_close"]
        out = combined[combined["session_date"].dt.year == year]
        out = out[["symbol", "session_date", "close", "eligibility_price", "atr14", "avg_volume14"]]
        out.to_parquet(out_path, index=False)
        _log(
            f"stage1-daily: {year}: wrote {len(out):,} symbol-day rows -> {out_path} "
            f"({time.time() - t0:.1f}s)"
        )


def _missing_stage1_years(years: tuple[int, ...]) -> list[int]:
    return [
        y
        for y in years
        if not (_opening_bar_cache_path(y).exists() and _daily_cache_path(y).exists())
    ]


def _load_opening_cache(years: tuple[int, ...]) -> pd.DataFrame:
    frames = [
        pd.read_parquet(_opening_bar_cache_path(y))
        for y in years
        if _opening_bar_cache_path(y).exists()
    ]
    if not frames:
        return pd.DataFrame(columns=_OPENING_BAR_COLUMNS)
    frame = pd.concat(frames, ignore_index=True)
    frame["session_date"] = pd.to_datetime(frame["session_date"])
    # Memory optimization (2026-09-24, disclosed deviation -- see module
    # docstring): `symbol` as `object` dtype stores a separate Python str per
    # row; across a multi-year concat that is millions of repeated tickers
    # held three times over (opening, daily, and their merge) at once, which
    # is what pushed Stage 2 past a 1.3G cap on this 3.9GB box with the
    # news-reaction build running concurrently. `category` stores the same
    # values once per unique symbol. Verified in-repl on pandas 2.3.3 that
    # merging a categorical key against another categorical OR plain object
    # key produces byte-identical rows and pandas coerces the output `symbol`
    # column back to plain `object`, so every downstream consumer (the
    # groupby/rolling in compute_eligible_universe, itertuples in
    # _append_selection_rows, etc.) sees exactly what it always did. This
    # changes only in-memory representation, never row content, order, or
    # values -- unlike filtering, it cannot interact with the rolling-window
    # relative-volume calculation.
    frame["symbol"] = frame["symbol"].astype("category")
    return frame


def _load_daily_cache(years: tuple[int, ...]) -> pd.DataFrame:
    frames = [pd.read_parquet(_daily_cache_path(y)) for y in years if _daily_cache_path(y).exists()]
    if not frames:
        return pd.DataFrame(
            columns=[
                "symbol",
                "session_date",
                "close",
                "eligibility_price",
                "atr14",
                "avg_volume14",
            ]
        )
    frame = pd.concat(frames, ignore_index=True)
    frame["session_date"] = pd.to_datetime(frame["session_date"])
    frame["symbol"] = frame["symbol"].astype("category")  # see _load_opening_cache
    return frame


# --------------------------------------------------------------------------
# pure eligibility / ranking logic (unit-tested directly)
# --------------------------------------------------------------------------


def _merge_opening_daily_by_year(opening: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Inner-join opening/daily one calendar year at a time and concatenate.

    Memory optimization (2026-09-24, disclosed deviation -- see module
    docstring): measured peak RSS for a single ``opening.merge(daily, ...)``
    across the select window's 3 combined years at ~2.7GB, which OOM-killed
    Stage 2 even at a 1.3G cgroup cap on this 3.9GB box. A join's key
    (``symbol``, ``session_date``) can never cross a calendar-year boundary,
    so ``concat(join(opening_y, daily_y) for y in years) == join(opening,
    daily)`` exactly -- this is just distributing the join over a partition
    of the input by year, not a change to which rows match. It cuts the
    largest single merge call from ~3 years of rows to 1, which is what
    brought Stage 2 back under budget."""
    if opening.empty or daily.empty:
        return opening.merge(daily, on=["symbol", "session_date"], how="inner")
    years = sorted(set(opening["session_date"].dt.year) | set(daily["session_date"].dt.year))
    parts = [
        opening[opening["session_date"].dt.year == year].merge(
            daily[daily["session_date"].dt.year == year],
            on=["symbol", "session_date"],
            how="inner",
        )
        for year in years
    ]
    return pd.concat(parts, ignore_index=True)


def compute_eligible_universe(opening: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Merge Stage 1's two caches, compute relative volume, direction and the
    doji flag. Does not apply any candidate's own eligibility floors -- see
    :func:`apply_eligibility_floors`."""
    merged = _merge_opening_daily_by_year(opening, daily)
    merged = merged[merged["bar_count"] == 5].copy()
    merged = merged.sort_values(["symbol", "session_date"])
    merged["rel_volume"] = merged.groupby("symbol", sort=False)["candle_volume"].transform(
        lambda s: s / s.shift(1).rolling(RELVOL_LOOKBACK_DAYS).mean()
    )
    merged["is_doji"] = merged["candle_open"] == merged["candle_close"]
    merged["direction_real"] = np.where(
        merged["is_doji"], np.nan, np.sign(merged["candle_close"] - merged["candle_open"])
    )
    return merged


def apply_eligibility_floors(universe: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    return universe[
        universe["eligibility_price"].notna()
        & universe["avg_volume14"].notna()
        & universe["atr14"].notna()
        & (universe["eligibility_price"] >= params["price_floor_usd"])
        & (universe["avg_volume14"] >= params["avg_volume_floor_shares_per_day"])
        & (universe["atr14"] >= params["atr_floor_usd"])
        & (universe["rel_volume"] >= params["relative_volume_floor"])
    ]


def select_real_top_n(eligible_day: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """One day's eligible rows -> the top ``top_n`` by relative volume
    descending (ties broken by symbol for determinism)."""
    ranked = eligible_day.sort_values(["rel_volume", "symbol"], ascending=[False, True])
    return ranked.head(top_n)


def select_rl_draw(
    eligible_day: pd.DataFrame, top_n: int, rng: np.random.Generator
) -> pd.DataFrame:
    """One day's eligible rows -> ``top_n`` symbols drawn uniformly at random
    from the eligible-but-not-real-top-20 remainder (the RL control)."""
    ranked = eligible_day.sort_values(["rel_volume", "symbol"], ascending=[False, True])
    remainder = ranked.iloc[top_n:]
    if remainder.empty:
        return remainder
    n = min(top_n, len(remainder))
    idx = rng.choice(len(remainder), size=n, replace=False)
    return remainder.iloc[sorted(idx)]


def _trim_to_window_with_lookback(frame: pd.DataFrame, start: Any, end: Any) -> pd.DataFrame:
    """Trim a Stage 1 cache frame to ``[start - 30 calendar days, end]``.

    Memory optimization (2026-09-24, disclosed deviation -- see module
    docstring): Stage 1 caches are loaded a full calendar year at a time
    (``years_for_window``), but a window such as ``select`` (starting
    2023-09-18) or ``report_2026`` (starting 2026-01-02, with 2025 loaded
    only for lookback) only ever keeps rows in ``[start, end]`` after
    :func:`apply_eligibility_floors` -- every earlier row exists solely so
    ``rel_volume``'s ``rolling(14)`` window has trailing history for the
    first dates in the window. 30 calendar days is a generous margin over
    the needed 14 *trading* days through any holiday calendar. Trimming here,
    before the merge, cannot change any retained date's rel_volume/atr14/
    avg_volume14: every date that survives the caller's own
    ``[start, end]`` filter keeps its full, unmodified trailing window. This
    is what cut Stage 2 down from merging ~1.1M excess January-August rows
    for a window that starts in September (``select``) / ~2M excess rows
    from a year loaded only for its December tail (``report_2026``)."""
    lookback_start = pd.Timestamp(start) - pd.Timedelta(days=30)
    return frame[
        (frame["session_date"] >= lookback_start) & (frame["session_date"] <= pd.Timestamp(end))
    ]


def _selection_cache_path(screen_id: str, window_name: str) -> Path:
    return SELECTIONS_DIR / screen_id / f"{window_name}.parquet"


def stage2_select(
    screens: dict[str, list[str]],
    candidates: dict[str, dict[str, Any]],
    window_names: tuple[str, ...],
    force: bool,
) -> None:
    SELECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    for screen_id, member_ids in screens.items():
        params = candidates[member_ids[0]]["parameters"]
        top_n = int(params["top_n_by_relative_volume"])
        for window_name in window_names:
            out_path = _selection_cache_path(screen_id, window_name)
            if out_path.exists() and not force:
                _log(f"stage2: {screen_id}/{window_name} cache present -- reusing")
                continue
            years = years_for_window(window_name)
            missing_years = _missing_stage1_years(years)
            if missing_years:
                _log(
                    f"stage2: {screen_id}/{window_name}: Stage 1 cache missing for "
                    f"years {missing_years} (of {years}) -- run stage 1 first, skipping"
                )
                continue
            opening = _load_opening_cache(years)
            daily = _load_daily_cache(years)
            if opening.empty or daily.empty:
                _log(
                    f"stage2: {screen_id}/{window_name}: Stage 1 cache is empty for "
                    f"years {years} -- skipping"
                )
                continue
            start, end = WINDOWS[window_name]
            opening = _trim_to_window_with_lookback(opening, start, end)
            daily = _trim_to_window_with_lookback(daily, start, end)
            universe = compute_eligible_universe(opening, daily)
            eligible = apply_eligibility_floors(universe, params)
            eligible = eligible[
                (eligible["session_date"] >= pd.Timestamp(start))
                & (eligible["session_date"] <= pd.Timestamp(end))
            ]
            rl_rngs = {seed: np.random.default_rng(seed) for seed in RL_SEEDS}
            rows: list[dict[str, Any]] = []
            eligible_days = 0
            for session_date, day_frame in eligible.groupby("session_date", sort=True):
                eligible_days += 1
                real_top = select_real_top_n(day_frame, top_n)
                _append_selection_rows(rows, session_date, "real", 0, real_top)
                for seed in RL_SEEDS:
                    drawn = select_rl_draw(day_frame, top_n, rl_rngs[seed])
                    if not drawn.empty:
                        _append_selection_rows(rows, session_date, "rl", seed, drawn)
            selection = pd.DataFrame(rows)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            selection.to_parquet(out_path, index=False)
            _log(
                f"stage2: {screen_id}/{window_name}: {eligible_days:,} eligible days, "
                f"wrote {len(selection):,} selection rows -> {out_path}"
            )


def _append_selection_rows(
    rows: list[dict[str, Any]],
    session_date: Any,
    variant: str,
    seed: int,
    frame: pd.DataFrame,
) -> None:
    for row in frame.itertuples():
        rows.append(
            {
                "session_date": session_date,
                "variant": variant,
                "seed": seed,
                "symbol": row.symbol,
                "candle_high": row.candle_high,
                "candle_low": row.candle_low,
                "direction_real": row.direction_real,
                "atr14": row.atr14,
                "rel_volume": row.rel_volume,
            }
        )


# --------------------------------------------------------------------------
# Stage 3: per-day, per-selected-symbol path simulation
# --------------------------------------------------------------------------


def _simulate_sip_outcome(
    direction: int,
    trigger_price: float,
    atr14: float,
    stop_loss_fraction: float,
    path_bars: list[tuple[float, float, float, float]],
    *,
    one_bar_late_stop: bool,
) -> dict[str, Any] | None:
    """``path_bars`` = ``[(open, high, low, close), ...]`` from 09:35 ET
    through the session's last bar, chronological. Returns ``None`` if the
    stop order never triggers. Entry fills at ``trigger_price``, or at a
    bar's own open if that bar gaps through the trigger. The protective stop
    (``stop_loss_fraction * atr14`` from entry) is checked starting on the
    entry bar itself (``same_bar_conservative``) or the bar after
    (``one_bar_late_stop=True``); when both entry and stop would be touched
    within the same bar, the stop is assumed to fire (conservative, matching
    this project's existing ETF-ORB stop-before-target convention)."""
    if not path_bars or trigger_price is None or not math.isfinite(trigger_price):
        return None
    entry_index: int | None = None
    entry_price: float | None = None
    for index, (bar_open, bar_high, bar_low, _bar_close) in enumerate(path_bars):
        if direction == 1:
            triggered = bar_high >= trigger_price
            gapped = bar_open >= trigger_price
        else:
            triggered = bar_low <= trigger_price
            gapped = bar_open <= trigger_price
        if triggered:
            entry_index = index
            entry_price = bar_open if gapped else trigger_price
            break
    if entry_index is None or entry_price is None:
        return None
    if atr14 is None or not (atr14 > 0) or not math.isfinite(atr14):
        return None
    stop_distance = stop_loss_fraction * atr14
    stop_loss_price = entry_price - stop_distance if direction == 1 else entry_price + stop_distance
    start_check = entry_index + 1 if one_bar_late_stop else entry_index
    exit_price: float | None = None
    exit_reason: str | None = None
    holding_bars: int | None = None
    for index in range(start_check, len(path_bars)):
        _bar_open, bar_high, bar_low, _bar_close = path_bars[index]
        hit_stop = bar_low <= stop_loss_price if direction == 1 else bar_high >= stop_loss_price
        if hit_stop:
            exit_price, exit_reason = stop_loss_price, "stop"
            holding_bars = index - entry_index + 1
            break
    if exit_price is None:
        exit_price = path_bars[-1][3]
        exit_reason = "close"
        holding_bars = len(path_bars) - entry_index
    return {
        "entry_index": entry_index,
        "entry_price": entry_price,
        "stop_loss_price": stop_loss_price,
        "R": stop_distance,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "holding_bars": holding_bars,
    }


def _sip_outcome_fields(outcome: dict[str, Any] | None) -> dict[str, Any]:
    if outcome is None:
        return {
            "entry_price": np.nan,
            "R": np.nan,
            "exit_price": np.nan,
            "exit_reason": None,
            "holding_bars": np.nan,
        }
    return {
        "entry_price": outcome["entry_price"],
        "R": outcome["R"],
        "exit_price": outcome["exit_price"],
        "exit_reason": outcome["exit_reason"],
        "holding_bars": outcome["holding_bars"],
    }


def _minute_root_for_day(day: date) -> Path:
    return SIP_HIST_ROOT if day.year <= 2022 else SIP_ROOT


def _minute_shard_files_for_month(year: int, month: int) -> list[Path]:
    """Shard files for one (year, month), preferring the month-sharded
    layout and falling back to the legacy whole-year layout only when no
    month directory exists at all for that year.

    Memory optimization (2026-09-24, disclosed deviation -- see module
    docstring): ``load_sip_bars``'s generic shard discovery
    (``sip_parquet._candidate_shards``) unions the legacy whole-year shards
    with the month-sharded ones for any year that has both (2023 has 317
    whole-year shards *and* 12 month directories) -- correct, since
    ``sip_parquet._finalize`` deduplicates the resulting overlap, but for a
    single day's ~100-symbol query it means reading up to 317 whole-year
    shards (each holding all 12 months of data) to serve one day's request.
    That is what spiked a single Stage 3 day-fetch to ~2.8GB RSS and
    OOM-killed the process at a 1G cgroup cap with an empty log (it died
    before the first progress line, which only prints every 25 days).
    Deliberately not fixed in ``sip_parquet.py`` itself -- that module is
    shared by other scripts and is out of scope here; this mirrors the
    month-preferred pattern already used for Stage 1's own minute reads
    (:func:`_minute_shard_files_for_year`). This function alone is NOT
    sufficient for correctness on 2023 -- see :func:`_fetch_day_path_bars`,
    which falls back to the legacy shards for any symbol the month layout
    turns out not to cover at all."""
    root = SIP_HIST_ROOT if year <= 2022 else SIP_ROOT
    year_dir = root / "minute" / str(year)
    if not year_dir.is_dir():
        return []
    month_dir = year_dir / f"{month:02d}"
    if month_dir.is_dir():
        return sorted(month_dir.glob("shard-*.parquet"))
    if any(p.is_dir() and p.name.isdigit() for p in year_dir.iterdir()):
        return []  # other months exist for this year, but not this one
    return sorted(year_dir.glob("shard-*.parquet"))  # legacy-only year, no month dirs at all


def _read_shards_for_symbols(paths: list[Path], symbols: list[str]) -> list[pd.DataFrame]:
    wanted = set(symbols)
    parts: list[pd.DataFrame] = []
    for path in paths:
        symbol_range = _shard_symbol_range(path)
        if symbol_range is not None and not _range_can_contain(symbol_range, symbols):
            continue
        chunk = _read_shard(path, wanted)
        if chunk is not None and not chunk.empty:
            parts.append(chunk)
    return parts


def _fetch_day_path_bars(
    day: date, symbols: list[str]
) -> dict[str, list[tuple[float, float, float, float]]]:
    if not symbols:
        return {}
    start_ts = _utc_timestamp(pd.Timestamp(day))
    end_ts = start_ts + pd.Timedelta(hours=23, minutes=59, seconds=59)
    try:
        parts = _read_shards_for_symbols(
            _minute_shard_files_for_month(day.year, day.month), symbols
        )
        # Correctness fix (2026-09-24, second pass -- see
        # _minute_shard_files_for_year's docstring): the month layout is not
        # guaranteed to cover every symbol the legacy layout does (verified
        # false for AAPL/AMD in September 2023). Only pay the legacy
        # whole-year read for symbols the month pass actually missed, never
        # unconditionally -- that is what keeps this fetch cheap for the
        # common case where the month layout already has everything asked
        # for (and for every year other than 2023, where there is no legacy
        # layer to fall back to at all).
        found = {str(s) for part in parts for s in part["symbol"].unique()}
        missing = [s for s in symbols if s not in found]
        if missing:
            legacy_files = _minute_shard_files_for_year_legacy_only(day.year)
            if legacy_files:
                parts.extend(_read_shards_for_symbols(legacy_files, missing))
    except SipParquetError:
        return {}
    frame = (
        pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=list(BAR_COLUMNS))
    )
    frame = _finalize(frame, start_ts, end_ts)
    if frame.empty:
        return {}
    close_time = us_equity_session_close(day)
    if close_time is None:
        return {}
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    ny_time = frame["timestamp"].dt.tz_convert(NEW_YORK).dt.time
    frame = frame.assign(ny_time=ny_time)
    frame = frame[(frame["ny_time"] >= dt_time(9, 35)) & (frame["ny_time"] < close_time)]
    result: dict[str, list[tuple[float, float, float, float]]] = {}
    for symbol, group in frame.groupby("symbol", sort=False):
        ordered = group.sort_values("ny_time").drop_duplicates("ny_time", keep="last")
        result[str(symbol)] = list(
            zip(
                ordered["open"].tolist(),
                ordered["high"].tolist(),
                ordered["low"].tolist(),
                ordered["close"].tolist(),
                strict=True,
            )
        )
    return result


def _outcomes_cache_path(screen_id: str, window_name: str) -> Path:
    return OUTCOMES_DIR / screen_id / f"{window_name}.parquet"


def stage3_simulate(
    screens: dict[str, list[str]],
    candidates: dict[str, dict[str, Any]],
    window_names: tuple[str, ...],
    force: bool,
) -> None:
    OUTCOMES_DIR.mkdir(parents=True, exist_ok=True)
    for screen_id, member_ids in screens.items():
        params = candidates[member_ids[0]]["parameters"]
        stop_fraction = float(params["stop_loss_fraction_of_atr14"])
        for window_name in window_names:
            out_path = _outcomes_cache_path(screen_id, window_name)
            if out_path.exists() and not force:
                _log(f"stage3: {screen_id}/{window_name} cache present -- reusing")
                continue
            sel_path = _selection_cache_path(screen_id, window_name)
            if not sel_path.exists():
                _log(f"stage3: {screen_id}/{window_name}: no selection cache -- run stage 2 first")
                continue
            selection = pd.read_parquet(sel_path)
            if selection.empty:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame(
                    columns=[
                        "session_date",
                        "symbol",
                        "direction",
                        "stop_fill_variant",
                        "entry_price",
                        "R",
                        "exit_price",
                        "exit_reason",
                        "holding_bars",
                    ]
                ).to_parquet(out_path, index=False)
                _log(f"stage3: {screen_id}/{window_name}: empty selection -- wrote empty cache")
                continue
            selection["session_date"] = pd.to_datetime(selection["session_date"])
            needed = selection[["session_date", "symbol", "candle_high", "candle_low", "atr14"]]
            needed = needed.drop_duplicates(subset=["session_date", "symbol"])
            rows: list[dict[str, Any]] = []
            dates = sorted(needed["session_date"].unique())
            t_start = time.time()
            for index, session_date in enumerate(dates):
                day = needed[needed["session_date"] == session_date]
                py_date = pd.Timestamp(session_date).date()
                symbols = sorted(day["symbol"].unique().tolist())
                path_bars_by_symbol = _fetch_day_path_bars(py_date, symbols)
                for row in day.itertuples():
                    bars = path_bars_by_symbol.get(row.symbol)
                    if not bars:
                        continue
                    for direction in (1, -1):
                        trigger = row.candle_high if direction == 1 else row.candle_low
                        for variant_label, one_bar_late in (
                            ("same_bar_conservative", False),
                            ("one_bar_late", True),
                        ):
                            outcome = _simulate_sip_outcome(
                                direction,
                                trigger,
                                row.atr14,
                                stop_fraction,
                                bars,
                                one_bar_late_stop=one_bar_late,
                            )
                            rows.append(
                                {
                                    "session_date": session_date,
                                    "symbol": row.symbol,
                                    "direction": direction,
                                    "stop_fill_variant": variant_label,
                                    **_sip_outcome_fields(outcome),
                                }
                            )
                if (index + 1) % 25 == 0 or (index + 1) == len(dates):
                    _log(
                        f"stage3: {screen_id}/{window_name} [{index + 1}/{len(dates)}] "
                        f"{py_date}: {time.time() - t_start:.1f}s elapsed"
                    )
            outcomes = pd.DataFrame(rows)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            outcomes.to_parquet(out_path, index=False)
            _log(
                f"stage3: {screen_id}/{window_name}: wrote {len(outcomes):,} outcome rows "
                f"-> {out_path} ({time.time() - t_start:.1f}s)"
            )


# --------------------------------------------------------------------------
# report stage: trades, portfolio-equity simulation, gates
# --------------------------------------------------------------------------


def build_trades(
    candidate_params: dict[str, Any],
    selection: pd.DataFrame,
    outcomes: pd.DataFrame,
    window: tuple[date, date],
    *,
    variant: str,
    seed: int,
) -> dict[str, pd.DataFrame]:
    """Return ``{stop_fill_variant: trades_frame}`` for one candidate's real
    trades (``variant="real"``), its RD control (``variant="rd"``, direction
    redrawn ±1 unconstrained by allow_short -- see report.md methodology
    notes) or its RL control (``variant="rl"``, same long/short mechanics as
    the real candidate, different selected symbols)."""
    empty = pd.DataFrame(
        columns=[
            "session_date",
            "symbol",
            "direction",
            "entry_price",
            "R",
            "exit_price",
            "holding_bars",
        ]
    )
    if selection.empty or outcomes.empty:
        return {sv: empty for sv in STOP_FILL_VARIANTS}
    start, end = window
    sel = selection[
        (selection["session_date"] >= pd.Timestamp(start))
        & (selection["session_date"] <= pd.Timestamp(end))
    ]
    if variant in ("real", "rd"):
        sel = sel[sel["variant"] == "real"]
    else:
        sel = sel[(sel["variant"] == "rl") & (sel["seed"] == seed)]
    if sel.empty:
        return {sv: empty for sv in STOP_FILL_VARIANTS}
    sel = sel.sort_values(["session_date", "symbol"]).copy()
    if variant == "rd":
        rng = np.random.default_rng(seed)
        sel["trade_direction"] = rng.choice([1, -1], size=len(sel))
    else:
        sel["trade_direction"] = sel["direction_real"]
    sel = sel[sel["trade_direction"].notna()]
    if variant != "rd":
        # RD's whole purpose is testing the value of the directional call
        # itself, decoupled from the candidate's own long/short business
        # constraint -- see the module docstring and report methodology
        # notes. "real" and "rl" both use "same mechanics" as the base
        # candidate, which includes its own allow_long/allow_short.
        if not candidate_params["allow_short"]:
            sel = sel[sel["trade_direction"] == 1]
        if not candidate_params["allow_long"]:
            sel = sel[sel["trade_direction"] == -1]
    sel = sel.assign(trade_direction=sel["trade_direction"].astype(int))

    result: dict[str, pd.DataFrame] = {}
    for stop_variant in STOP_FILL_VARIANTS:
        outcome_slice = outcomes[outcomes["stop_fill_variant"] == stop_variant]
        merged = sel.merge(
            outcome_slice,
            left_on=["session_date", "symbol", "trade_direction"],
            right_on=["session_date", "symbol", "direction"],
            how="inner",
        )
        merged = merged[merged["R"].notna() & (merged["R"] > 0)]
        result[stop_variant] = merged
    return result


def simulate_portfolio_equity(
    trades: pd.DataFrame,
    session_dates: list[date],
    *,
    max_positions: int,
    leverage_cap: float,
    cost_bps: float,
    commission_per_share: float,
    risk_pct_of_slot: float,
    borrow_annual_rate: float,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    """Compound a portfolio of up to ``max_positions`` concurrent names once
    per day. Slot capital = equity at the start of the day / max_positions;
    risk ``risk_pct_of_slot`` of that slot per trade; notional capped at
    ``leverage_cap * slot_capital``. Equity compounds once per session."""
    equity = 1.0
    daily_return: dict[date, float] = dict.fromkeys(session_dates, 0.0)
    trade_rows: list[dict[str, Any]] = []
    by_date: dict[Any, pd.DataFrame] = (
        {key: group for key, group in trades.groupby("session_date", sort=True)}
        if not trades.empty
        else {}
    )
    for session_date in sorted(session_dates):
        day_trades = by_date.get(pd.Timestamp(session_date))
        if day_trades is None or day_trades.empty:
            continue
        slot_capital = equity / max_positions
        risk_dollars = risk_pct_of_slot * slot_capital
        day_pnl = 0.0
        day_rows: list[dict[str, Any]] = []
        for row in day_trades.itertuples():
            r_value = float(row.R)
            if not (r_value > 0) or not math.isfinite(r_value):
                continue
            notional = min(risk_dollars * row.entry_price / r_value, leverage_cap * slot_capital)
            if notional <= 0:
                continue
            shares = notional / row.entry_price
            direction = int(row.trade_direction)
            gross_pnl = shares * (row.exit_price - row.entry_price) * direction
            entry_notional = shares * row.entry_price
            exit_notional = shares * row.exit_price
            cost = (entry_notional + exit_notional) * (cost_bps / 10_000.0)
            commission = shares * commission_per_share * 2.0
            borrow = 0.0
            if direction == -1 and borrow_annual_rate > 0:
                holding_minutes = float(row.holding_bars)
                borrow = entry_notional * borrow_annual_rate * (holding_minutes / MINUTES_PER_YEAR)
            net_pnl = gross_pnl - cost - commission - borrow
            day_pnl += net_pnl
            day_rows.append(
                {
                    "date": session_date,
                    "symbol": row.symbol,
                    "direction": direction,
                    "entry_price": row.entry_price,
                    "exit_price": row.exit_price,
                    "exit_reason": row.exit_reason,
                    "net_pnl": net_pnl,
                    "entry_notional": entry_notional,
                    "r_multiple": direction * (row.exit_price - row.entry_price) / r_value,
                }
            )
        if not day_rows:
            continue
        day_return = day_pnl / equity
        equity *= 1.0 + day_return
        daily_return[session_date] = day_return
        trade_rows.extend(day_rows)
    dates_sorted = sorted(daily_return)
    returns = pd.Series(
        [daily_return[d] for d in dates_sorted], index=pd.to_datetime(dates_sorted), dtype="float64"
    )
    return returns, trade_rows


def compute_metrics(
    returns: pd.Series,
    trade_rows: list[dict[str, Any]],
    total_session_days: int,
    max_positions: int,
) -> dict[str, Any]:
    if len(returns) == 0 or total_session_days == 0:
        return {
            "annualized_return": None,
            "max_drawdown": None,
            "annualized_vol": None,
            "sharpe": None,
            "win_rate": None,
            "trades": 0,
            "avg_r_multiple": None,
            "exposure": None,
            "avg_positions_per_day": None,
            "turnover_annualized": None,
        }
    std = float(returns.std())
    n_trades = len(trade_rows)
    wins = sum(1 for row in trade_rows if row["net_pnl"] > 0)
    wealth = float((1.0 + returns).prod())
    mean_equity = float((1.0 + returns).cumprod().mean()) if len(returns) else 1.0
    years = total_session_days / 252.0
    gross_notional = sum(row["entry_notional"] for row in trade_rows)
    turnover = (
        (gross_notional / mean_equity / years)
        if (trade_rows and years > 0 and mean_equity > 0)
        else None
    )
    return {
        "annualized_return": annualized_cagr(returns),
        "max_drawdown": max_drawdown(returns),
        "annualized_vol": std * math.sqrt(252.0) if std == std else None,
        "sharpe": float(returns.mean() / std * math.sqrt(252.0)) if std > 0 else None,
        "win_rate": wins / n_trades if n_trades else None,
        "trades": n_trades,
        "avg_r_multiple": float(np.mean([row["r_multiple"] for row in trade_rows]))
        if trade_rows
        else None,
        "exposure": n_trades / (total_session_days * max_positions),
        "avg_positions_per_day": n_trades / total_session_days,
        "turnover_annualized": turnover,
        "total_return": wealth - 1.0,
    }


def _slice_metrics_by_year(returns: pd.Series) -> dict[int, dict[str, Any]]:
    by_year: dict[int, dict[str, Any]] = {}
    if returns.empty:
        return by_year
    for year, group in returns.groupby(returns.index.year):
        by_year[int(year)] = {
            "annualized_return": annualized_cagr(group) if len(group) else None,
            "max_drawdown": max_drawdown(group) if len(group) else None,
            "sessions": int(len(group)),
        }
    return by_year


def _buy_hold_stats(symbol: str, start: date, end: date) -> dict[str, Any] | None:
    try:
        raw = load_sip_bars([symbol], frequency="daily", start=start, end=end)
    except Exception as exc:  # noqa: BLE001 - report a clean "unavailable", not a crash
        _log(f"benchmark: {symbol} {start}..{end}: unavailable ({exc})")
        return None
    raw = raw.sort_values("timestamp")
    ny_date = raw["timestamp"].dt.tz_convert(NEW_YORK).dt.date
    closes = pd.Series(raw["close"].to_numpy(dtype="float64"), index=pd.to_datetime(ny_date))
    closes = closes[~closes.index.duplicated(keep="last")].sort_index()
    returns = closes.pct_change(fill_method=None).dropna()
    if returns.empty:
        return None
    return {
        "annualized_return": annualized_cagr(returns),
        "max_drawdown": max_drawdown(returns),
        "sessions": int(len(returns)),
    }


def _equal_weight_eligible_returns(
    universe: pd.DataFrame, params: dict[str, Any], window: tuple[date, date]
) -> pd.Series:
    eligible = apply_eligibility_floors(universe, params)
    start, end = window
    eligible = eligible[
        (eligible["session_date"] >= pd.Timestamp(start))
        & (eligible["session_date"] <= pd.Timestamp(end))
    ]
    if eligible.empty:
        return pd.Series(dtype="float64")
    day_return = (
        (eligible["close"] / eligible["eligibility_price"] - 1.0)
        .groupby(eligible["session_date"])
        .mean()
    )
    return day_return.sort_index()


def evaluate_gate(criterion: dict[str, Any], value: float | None) -> dict[str, Any]:
    threshold = float(criterion["threshold"])
    direction = criterion["direction"]
    passed = None
    if value is not None and isinstance(value, int | float) and math.isfinite(value):
        if direction == ">":
            passed = value > threshold
        elif direction == ">=":
            passed = value >= threshold
        elif direction == "<":
            passed = value < threshold
        elif direction == "<=":
            passed = value <= threshold
    return {
        "name": criterion["name"],
        "threshold": threshold,
        "direction": direction,
        "value": value,
        "pass": passed,
    }


def _window_ready(window_name: str, screens: dict[str, list[str]]) -> bool:
    years = years_for_window(window_name)
    if not all(
        _opening_bar_cache_path(y).exists() and _daily_cache_path(y).exists() for y in years
    ):
        return False
    return all(
        _selection_cache_path(sid, window_name).exists()
        and _outcomes_cache_path(sid, window_name).exists()
        for sid in screens
    )


def _trial_id(
    candidate_id: str, variant: str, seed: int, window: str, stop_variant: str, cost_variant: str
) -> str:
    tag = candidate_id if variant == "real" else f"{candidate_id}_{variant}{seed:02d}"
    return f"{tag}__{window}__{stop_variant}__{cost_variant}"


def stage_report(
    screens: dict[str, list[str]],
    candidates: dict[str, dict[str, Any]],
    cost_contract: dict[str, Any],
    gate_criteria: list[dict[str, Any]],
) -> dict[str, Any]:
    cost_variants = cost_variant_table(cost_contract)
    candidate_screen = {cid: sid for sid, members in screens.items() for cid in members}
    trial_rows: list[dict[str, Any]] = []
    grid: dict[str, dict[str, dict[str, dict[str, dict[str, Any]]]]] = {}
    by_year: dict[str, dict[str, dict[int, dict[str, Any]]]] = {}
    window_status: dict[str, str] = {}

    universes: dict[str, pd.DataFrame] = {}
    selections: dict[tuple[str, str], pd.DataFrame] = {}
    outcomes: dict[tuple[str, str], pd.DataFrame] = {}

    for window_name in WINDOWS:
        ready = _window_ready(window_name, screens)
        window_status[window_name] = "complete" if ready else "pending"
        if not ready:
            continue
        years = years_for_window(window_name)
        opening = _load_opening_cache(years)
        daily = _load_daily_cache(years)
        if not opening.empty:
            opening = _trim_to_window_with_lookback(opening, *WINDOWS[window_name])
        if not daily.empty:
            daily = _trim_to_window_with_lookback(daily, *WINDOWS[window_name])
        universe = (
            compute_eligible_universe(opening, daily)
            if not opening.empty and not daily.empty
            else pd.DataFrame()
        )
        universes[window_name] = universe
        for screen_id in screens:
            selections[(screen_id, window_name)] = pd.read_parquet(
                _selection_cache_path(screen_id, window_name)
            )
            sel_frame = selections[(screen_id, window_name)]
            if not sel_frame.empty:
                sel_frame["session_date"] = pd.to_datetime(sel_frame["session_date"])
            outcomes[(screen_id, window_name)] = pd.read_parquet(
                _outcomes_cache_path(screen_id, window_name)
            )
            out_frame = outcomes[(screen_id, window_name)]
            if not out_frame.empty:
                out_frame["session_date"] = pd.to_datetime(out_frame["session_date"])

    for candidate_id, manifest_row in candidates.items():
        params = manifest_row["parameters"]
        screen_id = candidate_screen[candidate_id]
        borrow_rate = BORROW_ANNUAL_RATE if params["allow_short"] else 0.0
        leverage_cap = float(params["leverage_cap"])
        risk_pct = float(params["risk_per_trade_pct_of_slot_capital"])
        max_positions = int(params["max_positions"])
        grid.setdefault(candidate_id, {})
        by_year.setdefault(candidate_id, {})

        for window_name, window in WINDOWS.items():
            if window_status[window_name] != "complete":
                continue
            session_dates = list(us_equity_session_dates(*window))
            selection = selections[(screen_id, window_name)]
            outcome_frame = outcomes[(screen_id, window_name)]
            trades = build_trades(params, selection, outcome_frame, window, variant="real", seed=0)
            grid[candidate_id].setdefault(window_name, {})
            for stop_variant in STOP_FILL_VARIANTS:
                grid[candidate_id][window_name].setdefault(stop_variant, {})
                for cost_label in COST_VARIANT_ORDER:
                    bps, commission = cost_variants[cost_label]
                    returns, trade_rows = simulate_portfolio_equity(
                        trades[stop_variant],
                        session_dates,
                        max_positions=max_positions,
                        leverage_cap=leverage_cap,
                        cost_bps=bps,
                        commission_per_share=commission,
                        risk_pct_of_slot=risk_pct,
                        borrow_annual_rate=borrow_rate,
                    )
                    metrics = compute_metrics(
                        returns, trade_rows, len(session_dates), max_positions
                    )
                    grid[candidate_id][window_name][stop_variant][cost_label] = metrics
                    trial_rows.append(
                        {
                            "trial_id": _trial_id(
                                candidate_id, "real", 0, window_name, stop_variant, cost_label
                            ),
                            "iter_id": ITERATION_ID,
                            "candidate_id": candidate_id,
                            "variant": "real",
                            "seed": 0,
                            "window": window_name,
                            "stop_fill_variant": stop_variant,
                            "cost_variant": cost_label,
                            "cost_bps": bps,
                            "commission_per_share": commission,
                            "metrics": metrics,
                            "generated_at": datetime.now(NEW_YORK).isoformat(),
                        }
                    )
                if stop_variant == PRIMARY_STOP_FILL_VARIANT:
                    by_year[candidate_id].setdefault(window_name, {})
                    primary_bps, primary_comm = cost_variants[PRIMARY_COST_VARIANT]
                    primary_returns, _ = simulate_portfolio_equity(
                        trades[stop_variant],
                        session_dates,
                        max_positions=max_positions,
                        leverage_cap=leverage_cap,
                        cost_bps=primary_bps,
                        commission_per_share=primary_comm,
                        risk_pct_of_slot=risk_pct,
                        borrow_annual_rate=borrow_rate,
                    )
                    by_year[candidate_id][window_name] = _slice_metrics_by_year(primary_returns)

            # controls: SIP01/SIP02 only (SIP03 is a diagnostic, no seeds).
            if candidate_id in ("SIP01", "SIP02"):
                for control_kind, seeds in (("rd", RD_SEEDS), ("rl", RL_SEEDS)):
                    for seed in seeds:
                        control_trades = build_trades(
                            params,
                            selection,
                            outcome_frame,
                            window,
                            variant=control_kind,
                            seed=seed,
                        )
                        bps, commission = cost_variants[PRIMARY_COST_VARIANT]
                        returns, trade_rows = simulate_portfolio_equity(
                            control_trades[PRIMARY_STOP_FILL_VARIANT],
                            session_dates,
                            max_positions=max_positions,
                            leverage_cap=leverage_cap,
                            cost_bps=bps,
                            commission_per_share=commission,
                            risk_pct_of_slot=risk_pct,
                            borrow_annual_rate=borrow_rate,
                        )
                        metrics = compute_metrics(
                            returns, trade_rows, len(session_dates), max_positions
                        )
                        grid[candidate_id][window_name].setdefault(f"control_{control_kind}", {})
                        grid[candidate_id][window_name][f"control_{control_kind}"][seed] = metrics
                        trial_rows.append(
                            {
                                "trial_id": _trial_id(
                                    candidate_id,
                                    control_kind,
                                    seed,
                                    window_name,
                                    PRIMARY_STOP_FILL_VARIANT,
                                    PRIMARY_COST_VARIANT,
                                ),
                                "iter_id": ITERATION_ID,
                                "candidate_id": candidate_id,
                                "variant": control_kind,
                                "seed": seed,
                                "window": window_name,
                                "stop_fill_variant": PRIMARY_STOP_FILL_VARIANT,
                                "cost_variant": PRIMARY_COST_VARIANT,
                                "cost_bps": bps,
                                "commission_per_share": commission,
                                "metrics": metrics,
                                "generated_at": datetime.now(NEW_YORK).isoformat(),
                            }
                        )

    # benchmarks (best-effort; a missing symbol/window degrades to "n/a")
    benchmarks: dict[str, Any] = {}
    for window_name, window in WINDOWS.items():
        if window_status[window_name] != "complete":
            continue
        benchmarks[window_name] = {
            "SPY": _buy_hold_stats("SPY", *window),
            "BIL": _buy_hold_stats("BIL", *window),
        }
        for screen_id, member_ids in screens.items():
            params = candidates[member_ids[0]]["parameters"]
            universe = universes.get(window_name)
            if universe is None or universe.empty:
                continue
            eq_returns = _equal_weight_eligible_returns(universe, params, window)
            benchmarks[window_name][f"equal_weight_{screen_id}"] = {
                "annualized_return": annualized_cagr(eq_returns) if len(eq_returns) else None,
                "max_drawdown": max_drawdown(eq_returns) if len(eq_returns) else None,
                "sessions": int(len(eq_returns)),
            }

    # gates: evaluated exactly as preregistered, only for SIP01/SIP02.
    gates: dict[str, list[dict[str, Any]]] = {}
    adoption: dict[str, Any] = {}
    for candidate_id in ("SIP01", "SIP02"):
        rows: list[dict[str, Any]] = []
        design_ready = window_status.get("design") == "complete"
        select_ready = window_status.get(FROZEN_SELECT_WINDOW) == "complete"
        screen_id = candidate_screen[candidate_id]

        def _cagr(
            window_name: str, stop_variant: str, cost_label: str, *, _cid: str = candidate_id
        ) -> float | None:
            return (
                grid.get(_cid, {})
                .get(window_name, {})
                .get(stop_variant, {})
                .get(cost_label, {})
                .get("annualized_return")
            )

        def _median_control(
            window_name: str, control_kind: str, *, _cid: str = candidate_id
        ) -> float | None:
            seeds_metrics = (
                grid.get(_cid, {}).get(window_name, {}).get(f"control_{control_kind}", {})
            )
            values = [
                m["annualized_return"]
                for m in seeds_metrics.values()
                if m.get("annualized_return") is not None
            ]
            return float(np.median(values)) if values else None

        real_design_cagr = (
            _cagr("design", PRIMARY_STOP_FILL_VARIANT, PRIMARY_COST_VARIANT)
            if design_ready
            else None
        )
        eq_weight_cagr = (
            benchmarks.get("design", {})
            .get(f"equal_weight_{screen_id}", {})
            .get("annualized_return")
            if design_ready
            else None
        )
        design_gate_a = (
            None
            if real_design_cagr is None or eq_weight_cagr is None
            else real_design_cagr - eq_weight_cagr
        )
        rd_median = _median_control("design", "rd") if design_ready else None
        design_gate_b = (
            None if real_design_cagr is None or rd_median is None else real_design_cagr - rd_median
        )
        rl_median = _median_control("design", "rl") if design_ready else None
        design_gate_c = (
            None if real_design_cagr is None or rl_median is None else real_design_cagr - rl_median
        )
        design_gate_d = (
            _cagr("design", PRIMARY_STOP_FILL_VARIANT, "20bp_plus_commission")
            if design_ready
            else None
        )

        select_cagr_10bp = (
            _cagr(FROZEN_SELECT_WINDOW, PRIMARY_STOP_FILL_VARIANT, "10bp") if select_ready else None
        )
        select_mdd_10bp = (
            grid.get(candidate_id, {})
            .get(FROZEN_SELECT_WINDOW, {})
            .get(PRIMARY_STOP_FILL_VARIANT, {})
            .get("10bp", {})
            .get("max_drawdown")
            if select_ready
            else None
        )
        placebo_rate = None
        if select_ready:
            rd_seeds = (
                grid.get(candidate_id, {}).get(FROZEN_SELECT_WINDOW, {}).get("control_rd", {})
            )
            rl_seeds = (
                grid.get(candidate_id, {}).get(FROZEN_SELECT_WINDOW, {}).get("control_rl", {})
            )
            draws = [
                m["annualized_return"]
                for m in list(rd_seeds.values()) + list(rl_seeds.values())
                if m.get("annualized_return") is not None
            ]
            if draws and select_cagr_10bp is not None:
                placebo_rate = float(np.mean([select_cagr_10bp > d for d in draws]))

        values_by_name = {
            "design_beats_equal_weight_eligible_universe": design_gate_a,
            "design_beats_rd_placebo_median": design_gate_b,
            "design_beats_rl_placebo_median": design_gate_c,
            "design_positive_net_of_20bp_plus_commission": design_gate_d,
            "select_window_cagr_10bp": select_cagr_10bp,
            "select_window_max_drawdown_10bp": select_mdd_10bp,
            "select_window_placebo_beat_rate": placebo_rate,
        }
        for criterion in gate_criteria:
            rows.append(evaluate_gate(criterion, values_by_name.get(criterion["name"])))
        gates[candidate_id] = rows
        all_evaluated = all(r["pass"] is not None for r in rows)
        adoption[candidate_id] = {
            "all_gates_evaluated": all_evaluated,
            "adoption_pass": bool(all_evaluated and all(r["pass"] for r in rows)),
        }

    if all(not v["adoption_pass"] for v in adoption.values()):
        overall_verdict = (
            "keep_refuted"
            if all(v["all_gates_evaluated"] for v in adoption.values())
            else "pending"
        )
    else:
        overall_verdict = (
            ",".join(cid for cid, v in adoption.items() if v["adoption_pass"]) + "_adopted"
        )

    summary = {
        "iter_id": ITERATION_ID,
        "generated_at": datetime.now(NEW_YORK).isoformat(),
        "windows": {name: [w[0].isoformat(), w[1].isoformat()] for name, w in WINDOWS.items()},
        "window_status": window_status,
        "screens": screens,
        "grid": grid,
        "by_year": by_year,
        "benchmarks": benchmarks,
        "gates": gates,
        "adoption": adoption,
        "overall_verdict": overall_verdict,
        "published_reference": PUBLISHED_REFERENCE,
        "stage0_diligence": json.loads(STAGE0_PATH.read_text(encoding="utf-8"))
        if STAGE0_PATH.exists()
        else None,
    }

    TRIAL_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRIAL_LEDGER_PATH.open("w", encoding="utf-8") as handle:
        for row in trial_rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")
    _log(f"report: wrote {len(trial_rows):,} trial rows -> {TRIAL_LEDGER_PATH}")

    _write_json(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report_markdown(summary), encoding="utf-8")
    _log(f"report: wrote {SUMMARY_PATH} and {REPORT_PATH}")
    return summary


# --------------------------------------------------------------------------
# report.md rendering
# --------------------------------------------------------------------------


def _num(value: Any, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "n/a"
    return format(value, f".{digits}f")


def _pct(value: Any, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "n/a"
    return format(value, f".{digits}%")


def render_report_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# H-20260923-13: Stocks-in-Play opening-range breakout -- backtest report")
    lines.append("")
    lines.append(
        "Iteration `h20260923_13_orb_stocks_in_play`. SIP01/SIP02 are the promotable long-only "
        "candidates; SIP03 (long-short) is a fidelity diagnostic only, never eligible for "
        "promotion. RD (random direction) and RL (random non-in-play liquid stock) controls are "
        "run for SIP01/SIP02 only, 10 seeds each, at the primary cost cell (10bp/side, "
        "same-bar-conservative stop fill)."
    )
    lines.append("")

    lines.append("## Window status")
    lines.append("")
    lines.append("| window | date range | status |")
    lines.append("|---|---|---|")
    for name, (start, end) in summary["windows"].items():
        lines.append(
            f"| {name} | {start} .. {end} | {summary['window_status'].get(name, 'pending')} |"
        )
    lines.append("")
    pending = [name for name, status in summary["window_status"].items() if status != "complete"]
    if pending:
        lines.append(
            f"Pending windows: {', '.join(pending)}. Resume with, e.g.:\n\n"
            "```\n"
            "./scripts/run_capped.sh --mem 1.2G -- uv run python "
            "scripts/run_h20260923_13_orb_stocks_in_play.py --stage 1 --windows "
            f"{' '.join(pending)}\n"
            "./scripts/run_capped.sh --mem 1.2G -- uv run python "
            "scripts/run_h20260923_13_orb_stocks_in_play.py --stage 2 --windows "
            f"{' '.join(pending)}\n"
            "./scripts/run_capped.sh --mem 1.2G -- uv run python "
            "scripts/run_h20260923_13_orb_stocks_in_play.py --stage 3 --windows "
            f"{' '.join(pending)}\n"
            "uv run python scripts/run_h20260923_13_orb_stocks_in_play.py --stage report\n"
            "```\n"
        )

    for window_name in summary["windows"]:
        if summary["window_status"].get(window_name) != "complete":
            continue
        lines.append(f"## Headline: {window_name} (primary cost 10bp/side, same-bar-conservative)")
        lines.append("")
        lines.append(
            "| candidate | CAGR | Sharpe | max DD | hit rate | avg R | trades | exposure "
            "| turnover(ann.) |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for candidate_id in summary["grid"]:
            metrics = (
                summary["grid"][candidate_id]
                .get(window_name, {})
                .get(PRIMARY_STOP_FILL_VARIANT, {})
                .get(PRIMARY_COST_VARIANT)
            )
            if metrics is None:
                continue
            lines.append(
                f"| {candidate_id} | {_pct(metrics['annualized_return'])} "
                f"| {_num(metrics['sharpe'])} | {_pct(metrics['max_drawdown'])} "
                f"| {_pct(metrics['win_rate'])} | {_num(metrics['avg_r_multiple'])} "
                f"| {metrics['trades']} | {_pct(metrics['exposure'])} "
                f"| {_num(metrics['turnover_annualized'])} |"
            )
        bench = summary["benchmarks"].get(window_name, {})
        for label, stats in bench.items():
            if stats is None:
                continue
            lines.append(
                f"| bench:{label} | {_pct(stats.get('annualized_return'))} | n/a "
                f"| {_pct(stats.get('max_drawdown'))} | n/a | n/a | n/a | n/a | n/a |"
            )
        lines.append("")

        lines.append(f"### Cost sensitivity ({window_name}, same-bar-conservative)")
        lines.append("")
        lines.append("| candidate | " + " | ".join(COST_VARIANT_ORDER) + " |")
        lines.append("|---|" + "---:|" * len(COST_VARIANT_ORDER))
        for candidate_id in summary["grid"]:
            cells = (
                summary["grid"][candidate_id]
                .get(window_name, {})
                .get(PRIMARY_STOP_FILL_VARIANT, {})
            )
            row = " | ".join(
                _pct(cells.get(cv, {}).get("annualized_return")) for cv in COST_VARIANT_ORDER
            )
            lines.append(f"| {candidate_id} | {row} |")
        lines.append("")

        lines.append(f"### Stop-fill variant ({window_name}, {PRIMARY_COST_VARIANT})")
        lines.append("")
        lines.append("| candidate | same_bar_conservative CAGR | one_bar_late CAGR |")
        lines.append("|---|---:|---:|")
        for candidate_id in summary["grid"]:
            cons = (
                summary["grid"][candidate_id]
                .get(window_name, {})
                .get("same_bar_conservative", {})
                .get(PRIMARY_COST_VARIANT, {})
                .get("annualized_return")
            )
            late = (
                summary["grid"][candidate_id]
                .get(window_name, {})
                .get("one_bar_late", {})
                .get(PRIMARY_COST_VARIANT, {})
                .get("annualized_return")
            )
            lines.append(f"| {candidate_id} | {_pct(cons)} | {_pct(late)} |")
        lines.append("")

        lines.append(f"### By year ({window_name}, primary cell)")
        lines.append("")
        lines.append("| candidate | year | CAGR | max DD | sessions |")
        lines.append("|---|---:|---:|---:|---:|")
        for candidate_id, windows_map in summary["by_year"].items():
            for year, stats in sorted(windows_map.get(window_name, {}).items()):
                lines.append(
                    f"| {candidate_id} | {year} | {_pct(stats['annualized_return'])} "
                    f"| {_pct(stats['max_drawdown'])} | {stats['sessions']} |"
                )
        lines.append("")

        lines.append(f"### RD / RL placebo controls ({window_name}, primary cell)")
        lines.append("")
        lines.append("| candidate | control | real CAGR | median seed CAGR | seed CAGR range |")
        lines.append("|---|---|---:|---:|---|")
        for candidate_id in ("SIP01", "SIP02"):
            real_cagr = (
                summary["grid"]
                .get(candidate_id, {})
                .get(window_name, {})
                .get(PRIMARY_STOP_FILL_VARIANT, {})
                .get(PRIMARY_COST_VARIANT, {})
                .get("annualized_return")
            )
            for control_kind in ("rd", "rl"):
                seeds_metrics = (
                    summary["grid"]
                    .get(candidate_id, {})
                    .get(window_name, {})
                    .get(f"control_{control_kind}", {})
                )
                values = [
                    m["annualized_return"]
                    for m in seeds_metrics.values()
                    if m.get("annualized_return") is not None
                ]
                if not values:
                    continue
                spread = f"{_pct(min(values))} ~ {_pct(max(values))}"
                lines.append(
                    f"| {candidate_id} | {control_kind.upper()} | {_pct(real_cagr)} "
                    f"| {_pct(float(np.median(values)))} | {spread} |"
                )
        lines.append("")

    lines.append(
        "## Adoption-rule gates (evaluated exactly as preregistered in the hypothesis card)"
    )
    lines.append("")
    lines.append("| candidate | gate | value | threshold | direction | pass |")
    lines.append("|---|---|---:|---:|:-:|:-:|")
    for candidate_id, rows in summary["gates"].items():
        for row in rows:
            pass_text = "PASS" if row["pass"] else ("FAIL" if row["pass"] is False else "n/a")
            lines.append(
                f"| {candidate_id} | {row['name']} | {_num(row['value'], 4)} "
                f"| {_num(row['threshold'], 4)} | {row['direction']} | {pass_text} |"
            )
    lines.append("")
    for candidate_id, verdict in summary["adoption"].items():
        lines.append(
            f"- {candidate_id}: all gates evaluated = {verdict['all_gates_evaluated']}, "
            f"adoption_pass = {verdict['adoption_pass']}"
        )
    lines.append("")
    lines.append(f"**Overall verdict: `{summary['overall_verdict']}`**")
    lines.append("")

    lines.append("## Published numbers (reference only, long+short combined -- see caveat)")
    lines.append("")
    lines.append(
        "SIP01/SIP02 above are long-only; the paper's own headline (Sharpe 2.81, 41.6% annualized, "
        "1,637% total, -12% max drawdown) is a combined long+short number with no long-only split "
        "ever published, so it is **not** a same-basis comparison for SIP01/SIP02. SIP03 (long-"
        "short, this report's diagnostic row, never promotable) is the only candidate meant to be "
        "read against it, as an implementation-fidelity check."
    )
    lines.append("")
    for key, payload in summary["published_reference"].items():
        numbers = json.dumps({k: v for k, v in payload.items() if k != "note"})
        lines.append(f"- `{key}`: {numbers} -- {payload.get('note', '')}")
    lines.append("")

    lines.append("## Data-quality diligence (Stage 0)")
    lines.append("")
    diligence = summary.get("stage0_diligence") or {}
    lines.append(f"```json\n{json.dumps(diligence, indent=2, default=str)}\n```")
    lines.append("")

    lines.append("## Methodology notes and disclosed deviations")
    lines.append("")
    lines.append(
        "- Doji = `candle_open == candle_close` exactly (the paper's own rule; a disclosed "
        "correction of `scripts/run_h20260918_02_orb_etf.py`'s 5%-of-range approximation)."
    )
    lines.append(
        "- No hand-built symbol-to-shard index was written (a disclosed implementation-strategy "
        "departure from `engine-design.md`'s sketch, not from any preregistered rule/parameter/"
        "window/candidate/gate); see the script's module docstring for the reasoning."
    )
    lines.append(
        "- RD's random direction draw (±1) is unconstrained by a candidate's own `allow_short` "
        "even for long-only SIP01/SIP02, matching `search-space.json`'s literal control "
        "description and this project's existing ETF-ORB placebo convention. This makes RD a "
        "strictly more permissive control than the candidate itself for long-only candidates, "
        "which is conservative for adoption-rule gate (b)."
    )
    lines.append(
        "- RL uses the candidate's own long/short mechanics (`allow_long`/`allow_short`) on a "
        'different, randomly-drawn set of eligible-but-not-top-20 symbols -- "same mechanics, '
        'different selection", per `search-space.json`.'
    )
    lines.append(
        "- The equal-weight-eligible-universe benchmark uses each eligible symbol's own prior-"
        "close-to-close daily return (from the same `data/sip/daily` eligibility table), not a "
        "same-day open-to-close or full-path return, since Stage 3 deliberately does not fetch "
        "full-day paths for the whole eligible universe (only the ~20-150 selected/drawn names "
        "per day) -- a disclosed, conservative proxy."
    )
    lines.append(
        "- Position sizing follows `candidate-manifest.json` exactly per candidate "
        "(`leverage_cap` 1.0x for SIP01/SIP02, the paper's own 4.0x for SIP03), not a single "
        "house-wide constant."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--stage", choices=["0", "1", "2", "3", "report", "all"], default="all")
    parser.add_argument("--windows", nargs="*", default=None, choices=list(WINDOWS))
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    window_names = tuple(args.windows) if args.windows else tuple(WINDOW_ORDER)
    years = years_for_windows(window_names)
    candidates = load_candidate_manifest()
    cost_contract = load_cost_contract()
    screens = build_screens(candidates)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.stage in ("all", "0"):
        stage0_diligence(args.force)
    if args.stage in ("all", "1"):
        stage1_opening_bars(years, args.force)
        stage1_daily_eligibility(years, args.force)
    if args.stage in ("all", "2"):
        stage2_select(screens, candidates, window_names, args.force)
    if args.stage in ("all", "3"):
        stage3_simulate(screens, candidates, window_names, args.force)
    if args.stage in ("all", "report"):
        gate_criteria = load_gate_criteria()
        stage_report(screens, candidates, cost_contract, gate_criteria)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
