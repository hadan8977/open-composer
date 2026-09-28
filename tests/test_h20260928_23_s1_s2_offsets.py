from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import run_h20260928_23_s1_s2_rebalance_timing as mod  # noqa: E402


def _synthetic_panel(
    symbols: list[str], n_sessions: int, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A deterministic random-walk close/open panel over a business-day index,
    long enough to produce real weekly/monthly rebalance signals."""
    index = pd.bdate_range("2018-01-02", periods=n_sessions)
    rng = np.random.default_rng(seed)
    close = pd.DataFrame(index=index, columns=sorted(symbols), dtype=float)
    for col in close.columns:
        drift = rng.normal(0.0002, 0.0005)
        rets = rng.normal(drift, 0.01, size=n_sessions)
        close[col] = 100.0 * np.cumprod(1.0 + rets)
    # open = prior close nudged by a small independent overnight return, so
    # open != close and the open/close leg split is non-degenerate.
    overnight = rng.normal(0.0, 0.002, size=(n_sessions, len(close.columns)))
    open_ = close.shift(1).to_numpy() * (1.0 + overnight)
    open_ = pd.DataFrame(open_, index=index, columns=close.columns)
    open_.iloc[0] = close.iloc[0]
    return close, open_


def _menu_symbols(key: str) -> list[str]:
    cfg = salvage.SLEEVES[key]
    return sorted(set(base.MENUS[cfg["menu"]] + [base.CASH]))


class TestShiftedSignalDates:
    def test_offset_zero_matches_unshifted_rebalance_flags(self):
        index = pd.bdate_range("2020-01-01", periods=120)
        flags = base.rebalance_flags(index, "weekly")
        expected = list(index[flags.to_numpy()])
        assert mod.shifted_signal_dates(index, "weekly", 0) == expected

    def test_offset_shifts_every_signal_date_by_the_same_number_of_sessions(self):
        index = pd.bdate_range("2020-01-01", periods=120)
        flags = base.rebalance_flags(index, "monthly").to_numpy()
        base_positions = np.flatnonzero(flags)
        for offset in (1, 5, 10):
            shifted = mod.shifted_signal_dates(index, "monthly", offset)
            expected_positions = [i + offset for i in base_positions if i + offset < len(index)]
            assert shifted == [index[i] for i in expected_positions]
            # every shifted date really is `offset` sessions after its base date
            for base_i, shifted_date in zip(base_positions, shifted, strict=False):
                assert index.get_loc(shifted_date) == base_i + offset

    def test_offset_near_panel_end_drops_dates_that_fall_off_the_panel(self):
        index = pd.bdate_range("2020-01-01", periods=25)
        flags = base.rebalance_flags(index, "weekly").to_numpy()
        base_positions = np.flatnonzero(flags)
        shifted = mod.shifted_signal_dates(index, "weekly", 4)
        assert len(shifted) <= len(base_positions)
        assert all(d in index for d in shifted)


class TestOffsetZeroReproducesLiveCell:
    @pytest.mark.parametrize(
        ("key", "target"),
        [("s1", None), ("s2", mod.S2_TARGET)],
    )
    def test_offset_zero_bit_equal_to_salvage_run_cell(self, key, target):
        symbols = _menu_symbols(key) + [base.RF]
        close, open_ = _synthetic_panel(symbols, n_sessions=400, seed=20260928)
        leg_open, leg_close = salvage.legs(close, open_)

        ref, _ = salvage.run_cell(close, leg_open, leg_close, key, target, base.COST_BPS_PRIMARY)

        eff, cols = mod.offset_effective(close, leg_open, leg_close, key, 0, target)
        got, _ = mod.simulate_effective(eff, cols, leg_open, leg_close, base.COST_BPS_PRIMARY)

        max_abs = float(np.max(np.abs(ref.to_numpy() - got.to_numpy())))
        assert max_abs <= 1e-12

    @pytest.mark.parametrize(
        ("key", "target"),
        [("s1", None), ("s2", mod.S2_TARGET)],
    )
    def test_nonzero_offset_uses_later_signal_dates_than_offset_zero(self, key, target):
        symbols = _menu_symbols(key) + [base.RF]
        close, _ = _synthetic_panel(symbols, n_sessions=400, seed=7)

        _, dates0 = mod.sleeve_weights_offset(close, key, 0)
        _, dates3 = mod.sleeve_weights_offset(close, key, 3)

        assert len(dates3) <= len(dates0)
        pos = {d: i for i, d in enumerate(close.index)}
        for d0, d3 in zip(dates0, dates3, strict=False):
            assert pos[d3] == pos[d0] + 3


def test_load_manifest_guard_accepts_the_real_preregistered_candidate_sets():
    for key, expected_n in (("s1", 5), ("s2", 21)):
        manifest = mod.load_manifest_guard(key)
        ids = [c["candidate_id"] for c in manifest["candidates"]]
        assert ids == [f"O{o:02d}" for o in range(expected_n)]


def test_load_manifest_guard_rejects_a_tampered_candidate_set(tmp_path, monkeypatch):
    bad_dir = tmp_path / "reports/research/iterations/h20260928_23_s1_rebalance_timing"
    bad_dir.mkdir(parents=True)
    (bad_dir / "candidate-manifest.json").write_text(
        '{"candidates": [{"candidate_id": "O00"}, {"candidate_id": "O99"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    with pytest.raises(SystemExit):
        mod.load_manifest_guard("s1")


class TestPanelStartRegression:
    """2026-09-28 bug: the script never set base.WARMUP_START before
    base.load_panel, so it silently used the recent-menu default
    ("2022-06-01") and every "stress" window actually only covered
    2022-06..2023-08. scripts/run_h20260928_01_s3_rebalance_tranching.py
    already gets this right (its line `base.WARMUP_START = PANEL_START`
    before load_panel); this script must do the same."""

    def test_panel_start_constant_covers_the_stress_windows(self):
        assert mod.PANEL_START == "2015-01-02"
        for cfg in mod.SLEEVES.values():
            stress_start = pd.Timestamp(cfg["windows"]["stress"][0])
            assert pd.Timestamp(mod.PANEL_START) <= stress_start

    def test_assert_panel_covers_stress_window_accepts_a_full_panel(self):
        # 2016-01-04 is the SIP daily archive's actual earliest session
        # (confirmed via h20260928_01_s3_rebalance_tranching's results.json),
        # even though PANEL_START requests 2015-01-02.
        index = pd.bdate_range("2016-01-04", periods=10)
        mod.assert_panel_covers_stress_window(index)  # must not raise

    def test_assert_panel_covers_stress_window_rejects_a_truncated_panel(self):
        # exactly the failure mode of the bug: panel silently starts in 2022
        index = pd.bdate_range("2022-06-01", periods=10)
        with pytest.raises(SystemExit, match="panel_first_session"):
            mod.assert_panel_covers_stress_window(index)

    def test_main_sets_warmup_start_before_load_panel(self, monkeypatch):
        seen: dict[str, str] = {}

        def fake_load_panel(symbols):
            seen["warmup_start"] = mod.base.WARMUP_START
            raise SystemExit("stop before the real, expensive panel load")

        monkeypatch.setattr(mod.base, "load_panel", fake_load_panel)
        with pytest.raises(SystemExit):
            mod.main()
        assert seen["warmup_start"] == "2015-01-02"
