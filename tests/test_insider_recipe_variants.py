"""Tests for the five 10b5-1 opportunistic-buying recipe variants added to
``scripts/run_h20260917_01_insider_independent.py`` (H-20260917-01):
``recipe_od_nonplan``, ``recipe_od_nonplan_cluster``, ``recipe_od_nonplan_usd25k``,
``recipe_od_plan`` (the control twin) and ``recipe_od_unknown``, plus the
``recipe_2023q2`` window and the pre-2023q2 empty-book guard
(``_guard_recipe_windows``).

These are unit tests on small synthetic formation frames / summary
structures only -- no real data, no full pipeline. The crossed
``*_od_nonplan_60d`` / ``*_od_plan_60d`` / ``*_od_flag_unknown_60d`` columns
are treated as already-aggregated inputs (their construction lives in
``scripts/build_insider_features.py``, out of scope here); what is tested is
``variant_mask``'s use of those columns, and the report-stage guard against
reporting the guaranteed-empty pre-2023q2 book as a real result.
"""

from __future__ import annotations

import importlib

import numpy as np
import pandas as pd

mod = importlib.import_module("scripts.run_h20260917_01_insider_independent")

variant_mask = mod.variant_mask
RECIPE_VARIANTS = mod.RECIPE_VARIANTS
WINDOWS = mod.WINDOWS


def _base_frame(n: int) -> dict[str, list[float]]:
    """Columns every ``variant_mask`` call touches unconditionally (the
    ``any60`` computation at the top of the function runs before the
    per-variant branches), plus the six new crossed columns, all zeroed."""
    return {
        "open_market_buy_count_60d": [1.0] * n,
        "open_market_buy_count_od_nonplan_60d": [0.0] * n,
        "buyers_od_nonplan_60d": [0.0] * n,
        "net_buy_usd_od_nonplan_60d": [0.0] * n,
        "open_market_buy_count_od_plan_60d": [0.0] * n,
        "open_market_buy_count_od_flag_unknown_60d": [0.0] * n,
    }


# --------------------------------------------------------------------------
# each mask selects exactly the intended rows
# --------------------------------------------------------------------------


def test_recipe_masks_select_intended_rows() -> None:
    # Row A: bare nonplan buy only.
    # Row B: nonplan + cluster (>=2 buyers), dollar amount below the usd25k bar.
    # Row C: nonplan + usd25k, single buyer (below the cluster bar).
    # Row D: no nonplan buy, but a plan buy (the control twin's target row).
    # Row E: no nonplan/plan buy, but the plan flag itself is unknown.
    # Row F: nothing -- no insider signal of any of these kinds.
    cols = _base_frame(6)
    cols["open_market_buy_count_od_nonplan_60d"] = [1.0, 2.0, 1.0, 0.0, 0.0, 0.0]
    cols["buyers_od_nonplan_60d"] = [1.0, 2.0, 1.0, 0.0, 0.0, 0.0]
    cols["net_buy_usd_od_nonplan_60d"] = [1_000.0, 1_000.0, 30_000.0, 0.0, 0.0, 0.0]
    cols["open_market_buy_count_od_plan_60d"] = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    cols["open_market_buy_count_od_flag_unknown_60d"] = [0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    frame = pd.DataFrame(cols)

    expected = {
        "recipe_od_nonplan": [True, True, True, False, False, False],
        "recipe_od_nonplan_cluster": [False, True, False, False, False, False],
        "recipe_od_nonplan_usd25k": [False, False, True, False, False, False],
        "recipe_od_plan": [False, False, False, True, False, False],
        "recipe_od_unknown": [False, False, False, False, True, False],
    }
    assert set(expected) == set(RECIPE_VARIANTS)
    for variant, want in expected.items():
        got = variant_mask(frame, variant).tolist()
        assert got == want, f"{variant}: got {got}, want {want}"


# --------------------------------------------------------------------------
# crossed count vs its uncrossed parent (officer/director vs ten-percent owner)
# --------------------------------------------------------------------------


def test_recipe_od_nonplan_excludes_tenpct_owner_only_buy() -> None:
    """Two rows where a non-plan open-market buy exists: row 0 is an
    officer/director's, row 1 is a ten-percent owner's. The crossed
    ``open_market_buy_count_od_nonplan_60d`` column only counts
    officer/director buys, so it is <= the uncrossed general non-plan count
    on every row, and strictly less on row 1 where the only buyer is a
    ten-percent owner -- ``recipe_od_nonplan`` must pass row 0 only."""
    cols = _base_frame(2)
    general_nonplan = [1.0, 1.0]  # both rows have *some* non-plan buy
    cols["open_market_buy_count_od_nonplan_60d"] = [1.0, 0.0]  # only row 0 is od
    cols["buyers_od_nonplan_60d"] = [1.0, 0.0]
    cols["net_buy_usd_od_nonplan_60d"] = [10_000.0, 10_000.0]
    frame = pd.DataFrame(cols)

    # The crossed (od) count never exceeds the uncrossed parent count.
    crossed = frame["open_market_buy_count_od_nonplan_60d"].to_numpy()
    assert (crossed <= np.asarray(general_nonplan)).all()
    assert crossed[1] < general_nonplan[1]

    mask = variant_mask(frame, "recipe_od_nonplan").tolist()
    assert mask == [True, False]


# --------------------------------------------------------------------------
# nulls: a NaN crossed column excludes the row, it does not include it
# --------------------------------------------------------------------------


def test_nan_crossed_column_is_excluded_not_included() -> None:
    cols = _base_frame(2)
    for column in (
        "open_market_buy_count_od_nonplan_60d",
        "buyers_od_nonplan_60d",
        "net_buy_usd_od_nonplan_60d",
        "open_market_buy_count_od_plan_60d",
        "open_market_buy_count_od_flag_unknown_60d",
    ):
        cols[column] = [np.nan, cols[column][1]]
    # Give row 1 real qualifying values so the test is not vacuous.
    cols["open_market_buy_count_od_nonplan_60d"][1] = 1.0
    cols["buyers_od_nonplan_60d"][1] = 2.0
    cols["net_buy_usd_od_nonplan_60d"][1] = 30_000.0
    cols["open_market_buy_count_od_plan_60d"][1] = 1.0
    cols["open_market_buy_count_od_flag_unknown_60d"][1] = 1.0
    frame = pd.DataFrame(cols)

    for variant in RECIPE_VARIANTS:
        mask = variant_mask(frame, variant)
        assert bool(mask.iloc[0]) is False, f"{variant}: NaN row was included"
        assert bool(mask.iloc[1]) is True, f"{variant}: fully-qualifying row was excluded"


# --------------------------------------------------------------------------
# recipe_2023q2 window bounds
# --------------------------------------------------------------------------


def test_recipe_2023q2_window_bounds() -> None:
    start, end = WINDOWS["recipe_2023q2"]
    assert start == "2023-04-01"
    assert end is None


def test_recipe_2023q2_is_the_only_window_excluded_from_the_guard() -> None:
    """Sanity check on ``_unusable_windows_for_recipe``: every window that
    starts before the 10b5-1 checkbox's 2023q2 population date is unusable
    for recipe cells, and the two windows that start on/after it are not."""
    unusable = set(mod._unusable_windows_for_recipe())
    assert unusable == {"full", "pre_2020", "from_2020"}
    assert "recent_2024" not in unusable
    assert "recipe_2023q2" not in unusable


# --------------------------------------------------------------------------
# the pre-2023q2 empty-book guard over a synthetic summary structure
# --------------------------------------------------------------------------


def _synthetic_cell(variant: str) -> dict:
    per_window = {window: {"cagr": 0.01, "vol": 0.02} for window in WINDOWS}
    return {
        "variant": variant,
        "band": "all",
        "horizon_months": 3,
        "book": {"months": 100, "empty_tranches": 59},
        "real": {window: dict(stats) for window, stats in per_window.items()},
        "stress_25bps": {window: dict(stats) for window, stats in per_window.items()},
        "random": {"per_seed": {1: {window: dict(stats) for window, stats in per_window.items()}}},
        "placebo": {"per_seed": {}},
        "verdict": {
            "verdict": "supported",
            "code": "supported",
            "reasons": ["满足支持条件"],
            "t_spy": 3.0,
            "t_iwm": 2.5,
            "t_random": 2.1,
            "mean_monthly_excess_spy": 0.01,
            "random_mean_monthly_excess_spy": 0.001,
            "random_share_of_real": 0.1,
            "pre_2020_excess_spy": 0.001,
            "from_2020_excess_spy": 0.002,
            "crit_all_t_below_2": False,
            "crit_random_ge_50pct": False,
            "crit_pre_2020_only": False,
        },
    }


def test_guard_marks_pre_2023q2_windows_unusable_and_leaves_others_alone() -> None:
    cells = {
        "recipe_cell": _synthetic_cell("recipe_od_nonplan"),
        "control_cell": _synthetic_cell("any60"),
    }
    mod._guard_recipe_windows(cells)

    recipe_cell = cells["recipe_cell"]
    for window in ("full", "pre_2020", "from_2020"):
        entry = recipe_cell["real"][window]
        assert entry.get("unusable_reason") == mod.RECIPE_UNUSABLE_REASON
        # the underlying numbers stay visible for a forensic read
        assert entry["cagr"] == 0.01
    for window in ("recent_2024", "recipe_2023q2"):
        assert "unusable_reason" not in recipe_cell["real"][window]

    # stress and random per-seed metrics get the same treatment.
    assert recipe_cell["stress_25bps"]["full"].get("unusable_reason") == mod.RECIPE_UNUSABLE_REASON
    assert (
        recipe_cell["random"]["per_seed"][1]["pre_2020"].get("unusable_reason")
        == mod.RECIPE_UNUSABLE_REASON
    )
    assert "unusable_reason" not in recipe_cell["random"]["per_seed"][1]["recipe_2023q2"]

    # the refutation/summary logic must not see a real-looking verdict.
    verdict = recipe_cell["verdict"]
    assert verdict["verdict"] == "unusable"
    assert verdict["t_spy"] is None
    assert verdict["t_iwm"] is None
    assert verdict["t_random"] is None
    assert verdict["crit_all_t_below_2"] is True

    # non-empty formation-date count is explicit in the cell, not left for
    # the reader to infer from months - empty_tranches.
    assert recipe_cell["recipe_nonempty_formation_dates"] == 100 - 59
    assert recipe_cell["recipe_total_formation_dates"] == 100

    # a non-recipe cell in the same summary is untouched.
    control_cell = cells["control_cell"]
    assert control_cell["verdict"]["verdict"] == "supported"
    assert control_cell["verdict"]["t_random"] == 2.1
    assert "unusable_reason" not in control_cell["real"]["full"]
    assert "recipe_nonempty_formation_dates" not in control_cell
