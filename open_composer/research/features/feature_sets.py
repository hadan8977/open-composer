"""Step 13-F 3.4: named feature-set registry for the M/L-track research
loop and the F-track screening script.

docs/plan-step-13f-open-factor-library-import-and-screening-2026-09-09.zh.md
section 3.4: ``FEATURE_SETS = {"daily27": [...], "alpha158": [...],
"alpha101": [...], "alpha191": [...], "osap_price": [...],
"screened_top40_recent": <json>}`` and ``resolve_feature_set(name) ->
(columns, roots)``. Callers pass ``roots`` straight through to
``panel.py::load_feature_panel(..., extra_feature_roots=roots)``.

**Importing this module never touches the filesystem except for
``screened_top40_recent``** (and only when that specific name is
resolved) -- every other feature set's column list is a plain Python
constant, so ``import feature_sets`` cannot fail just because a table has
not been built yet. Requesting an unbuilt table's *data* still fails, but
that happens inside ``load_feature_panel``'s DuckDB query, not here.
"""

from __future__ import annotations

import json
from pathlib import Path

from open_composer.research.features.alpha101 import ALPHA101_COLUMNS
from open_composer.research.features.alpha158 import DEFAULT_WINDOWS, alpha158_columns
from open_composer.research.features.alpha191 import ALPHA191_COLUMNS
from open_composer.research.features.osap_price import OSAP_PRICE_COLUMNS
from open_composer.research.features.reversal_trend_daily import (
    REVERSAL_TREND_CONTINUOUS_COLUMNS,
)

ROOT = Path(__file__).resolve().parents[3]
FEATURES_ROOT = ROOT / "data" / "features"
DAILY_ROOT = FEATURES_ROOT / "daily"
ALPHA158_ROOT = FEATURES_ROOT / "alpha158"
ALPHA101_ROOT = FEATURES_ROOT / "alpha101"
ALPHA191_ROOT = FEATURES_ROOT / "alpha191"
OSAP_PRICE_ROOT = FEATURES_ROOT / "osap_price"
REVERSAL_TREND_ROOT = FEATURES_ROOT / "reversal_trend"
SCREENED_TOP40_PATH = ROOT / "config" / "feature_sets" / "screened_top40_recent.json"

#: The 26 non-key columns of ``data/features/daily/{year}.parquet`` that
#: Step 11/13 Track M actually uses (the plan calls this set "daily27";
#: this repo's real table has 26 such columns -- the 20
#: ``*_{5,21}d_mean`` intraday-derived columns are proven-negative per
#: Step 11 Wave B and deliberately excluded here, not an oversight).
#: Hardcoded (not read from the parquet schema) so this list is stable and
#: reviewable even if the table gains an unrelated column later.
DAILY27_COLUMNS: tuple[str, ...] = (
    "open",
    "close",
    "ret_1",
    "ret_5",
    "ret_21",
    "ret_63",
    "ret_126",
    "ret_252",
    "vol_21",
    "vol_63",
    "beta_252_spy",
    "idio_vol_63",
    "max_ret_1_21",
    "dollar_adv_21",
    "dollar_adv_63",
    "amihud_21",
    "dist_from_252d_high",
    "momentum_252_21",
    "dollar_adv_21_over_63",
    "ret_1_rel",
    "ret_5_rel",
    "ret_21_rel",
    "ret_63_rel",
    "ret_126_rel",
    "ret_252_rel",
    "momentum_252_21_rel",
)

# OSAP_PRICE_COLUMNS and REVERSAL_TREND_CONTINUOUS_COLUMNS are imported
# above, not redefined here, so this registry can never drift from the
# tables that actually get built: osap_price.py's 25 columns (24
# per-symbol + momvol) and reversal_trend_daily.py's 21 continuous
# ``rt_*`` columns (the 4 discrete signal columns are event-study-only,
# see that module's docstring).

#: name -> (columns, root). ``daily27`` has no root: those columns already
#: live in ``panel.py``'s ``daily_root`` default, so no
#: ``extra_feature_roots`` entry is needed for them.
#: Columns that are numerically degenerate *as implemented* and therefore
#: excluded from every M-grid feature set (Step 13-F/M, 2026-09-11).
#: ``gtja017`` = ``rank(vwap - ts_max(vwap, 15)) ** delta(close, 5)``: a
#: rank in (0, 1] raised to a raw 5-day price difference explodes to
#: ~1e68..1e307 whenever the base is small and the exponent negative, which
#: (a) DuckDB refuses to cast to FLOAT (``ConversionException`` in
#: ``panel.load_feature_panel``, seen on the alpha191 cell) and (b) is not a
#: usable feature anyway. The 3.5 screen still evaluated it (rank IC is
#: scale-free), so its row stays in the screen table; only the M-grid
#: resolution drops it. Fixing the formula itself would be an alpha191
#: build change (out of scope here; disclosed in the F chapter).
DEGENERATE_COLUMNS: frozenset[str] = frozenset({"gtja017"})

_STATIC_FEATURE_SETS: dict[str, tuple[tuple[str, ...], Path | None]] = {
    "daily27": (DAILY27_COLUMNS, None),
    "alpha158": (tuple(alpha158_columns(DEFAULT_WINDOWS)), ALPHA158_ROOT),
    "alpha101": (ALPHA101_COLUMNS, ALPHA101_ROOT),
    "alpha191": (
        tuple(c for c in ALPHA191_COLUMNS if c not in DEGENERATE_COLUMNS),
        ALPHA191_ROOT,
    ),
    "osap_price": (OSAP_PRICE_COLUMNS, OSAP_PRICE_ROOT),
    "reversal_trend": (REVERSAL_TREND_CONTINUOUS_COLUMNS, REVERSAL_TREND_ROOT),
}


def _all_open_columns_and_roots() -> tuple[tuple[str, ...], tuple[Path, ...]]:
    """``all_open``: every open-library column (alpha158+alpha101+alpha191+
    osap_price+reversal_trend's continuous ``rt_*`` columns), for the 3.5
    screen only -- deliberately excludes ``daily27`` (the existing Step 11
    features, not an "open library") and is never registered as an M-grid
    feature set (plan section 3.6: 500+ columns would blow the memory
    budget alongside a LightGBM histogram build).
    """
    names = ("alpha158", "alpha101", "alpha191", "osap_price", "reversal_trend")
    columns: list[str] = []
    roots: list[Path] = []
    for name in names:
        cols, root = _STATIC_FEATURE_SETS[name]
        columns.extend(cols)
        if root is not None and cols:
            roots.append(root)
    return tuple(columns), tuple(roots)


def available_feature_sets() -> list[str]:
    """Every resolvable name, including the dynamic ones."""
    return [*_STATIC_FEATURE_SETS.keys(), "all_open", "screened_top40_recent"]


def resolve_feature_set(name: str) -> tuple[list[str], list[Path]]:
    """``(columns, roots)`` for a registered feature-set name. ``roots`` is
    ready to pass as ``panel.py::load_feature_panel(...,
    extra_feature_roots=roots)``.

    Raises ``KeyError`` for an unknown name, and ``FileNotFoundError`` for
    ``"screened_top40_recent"`` before ``scripts/screen_factors.py`` (Step
    13-F 3.5) has written ``config/feature_sets/screened_top40_recent.json``.
    """
    if name == "all_open":
        columns, roots = _all_open_columns_and_roots()
        return list(columns), list(roots)
    if name == "screened_top40_recent":
        return _load_screened_top40_recent()
    if name not in _STATIC_FEATURE_SETS:
        raise KeyError(
            f"unknown feature set {name!r}; available: {sorted(available_feature_sets())}"
        )
    columns, root = _STATIC_FEATURE_SETS[name]
    return list(columns), ([root] if root is not None else [])


def _load_screened_top40_recent() -> tuple[list[str], list[Path]]:
    if not SCREENED_TOP40_PATH.exists():
        raise FileNotFoundError(
            f"{SCREENED_TOP40_PATH} does not exist yet -- run "
            "scripts/screen_factors.py (Step 13-F 3.5) first"
        )
    payload = json.loads(SCREENED_TOP40_PATH.read_text(encoding="utf-8"))
    factors = payload["factors"] if isinstance(payload, dict) else payload
    columns = [row["factor"] if isinstance(row, dict) else row for row in factors]
    root_names = {
        row["source_root"] for row in factors if isinstance(row, dict) and row.get("source_root")
    }
    roots = [FEATURES_ROOT / root_name for root_name in sorted(root_names)]
    return columns, roots
