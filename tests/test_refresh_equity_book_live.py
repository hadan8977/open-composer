# ruff: noqa: E501
"""Plan, lock and freshness logic of the live-root refresh driver (no network, no big files)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from scripts import refresh_equity_book_live as rf


def _labels(plan: list[rf.Step]) -> list[str]:
    return [f"{s.stage}:{s.label}" for s in plan]


def test_plan_covers_every_live_stage_for_the_current_year() -> None:
    plan = rf.build_plan(date(2026, 10, 2))
    text = [s.text() for s in plan]
    live = [s for s in plan if s.stage.startswith("live:")]
    assert [s.stage for s in live if s.kind == "run"] == [f"live:{n}" for n in rf.LIVE_STAGES]
    assert rf.LIVE_STAGES.index("risk") < rf.LIVE_STAGES.index("signals")  # signals read residuals
    assert all(
        s.env["OC_EQUITY_BOOK_DIR"] == "data/live/equity_book" for s in live if s.kind == "run"
    )
    joined = "\n".join(text)
    assert "build_equity_book_panel.py panel --years 2026" in joined
    assert "build_equity_book_signals.py build --years 2026 --force" in joined
    assert "--start 2017-01-01 --end 2026-10-02" in joined
    assert "alpha" in joined and "merge formation_ic" in joined
    assert "alpha-cols" not in joined and " report" not in joined
    # upstream first, in table order; disabled tables are left out
    ups = [s.stage for s in plan if s.stage.startswith("up:")]
    assert ups[0] == "up:universe" and "up:daily_broad" in ups
    assert "up:alpha101_alpha191_broad" not in ups
    assert plan.index(next(s for s in plan if s.stage == "up:daily_broad")) < plan.index(live[0])


def test_plan_across_the_new_year() -> None:
    plan = rf.build_plan(date(2027, 1, 4))
    joined = "\n".join(s.text() for s in plan)
    assert "panel --years 2027" in joined
    assert "build --years 2027 --force" in joined
    assert (
        "--start 2017-01-01 --end 2027-01-04" in joined
    )  # fixed start: the model needs the history
    assert "daily_broad/2027.parquet" in joined
    steps = {s.stage: s for s in plan if s.label == "backup"}
    assert steps["up:daily_broad"].argv == ["daily_broad/2027.parquet"]


def test_plan_options_and_restatement_years() -> None:
    plan = rf.build_plan(date(2026, 10, 2), fetch=False, upstream=False, stages=["panel", "risk"])
    assert _labels(plan) == ["live:panel:build", "live:risk:build"]
    plan = rf.build_plan(date(2026, 10, 2), extra_daily_years=[2024, 2025, 2026])
    builds = [s for s in plan if s.stage == "up:daily_broad" and s.label.startswith("build")]
    assert [s.label for s in builds] == ["build 2026", "build 2025", "build 2024"] or [
        s.label for s in builds
    ] == ["build 2026", "build 2024", "build 2025"]
    other = [s for s in plan if s.stage == "up:daily" and s.label.startswith("build")]
    assert len(other) == 1  # only daily_broad is rebuilt for earlier years
    plan = rf.build_plan(date(2026, 10, 2), fetch=False)
    assert not any(s.label == "fetch" for s in plan)


def test_restatement_records(tmp_path: Path) -> None:
    path = tmp_path / "_restatements.jsonl"
    recs = [
        {"symbol": "AAA", "max_rel_diff": 1e-6, "years_rewritten": [2025, 2026]},
        {"symbol": "BBB", "max_rel_diff": 0.5, "years_rewritten": [2023, 2024, 2025, 2026]},
        {"symbol": "ZZZ", "max_rel_diff": 0.5, "years_rewritten": [2016]},
    ]
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    got, offset = rf.new_split_restatements(path, 0, {"AAA", "BBB"})
    assert [r["symbol"] for r in got] == ["BBB"] and offset == 3
    assert rf.restatement_years(got, 2026) == [2023, 2024, 2025]
    again, offset2 = rf.new_split_restatements(path, offset, None)
    assert again == [] and offset2 == 3


def test_lock_is_exclusive_and_released(tmp_path: Path) -> None:
    lock = tmp_path / "data/live/.refresh.lock"
    with rf.FileLock(lock):
        with pytest.raises(rf.RefreshLocked):
            with rf.FileLock(lock):
                pass
    with rf.FileLock(lock):  # released after the first holder left
        pass
    # a second process cannot take a held lock either
    code = (
        "import sys; sys.path.insert(0, '.');"
        "from scripts import refresh_equity_book_live as rf;"
        f"l = rf.FileLock(__import__('pathlib').Path({str(lock)!r}));"
        "\ntry:\n l.__enter__(); print('got')\nexcept rf.RefreshLocked:\n print('locked')"
    )
    with rf.FileLock(lock):
        out = subprocess.run(
            [sys.executable, "-c", code], cwd=rf.ROOT, capture_output=True, text=True, check=True
        )
    assert out.stdout.strip() == "locked"


def _write_live(live: Path, last: str, year: int = 2026, lagging: str | None = None) -> None:
    for sub in ("panel", "prices", "signals", "risk", "alpha/book_v1"):
        (live / sub).mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"trade_date": pd.to_datetime(["2026-09-30", last]), "symbol": "A"})
    frame.to_parquet(live / f"panel/{year}.parquet")
    frame.to_parquet(live / f"prices/{year}.parquet")
    frame.to_parquet(live / f"signals/{year}.parquet")
    frame.to_parquet(live / f"risk/exposures_{year}.parquet")
    frame.to_parquet(live / "etf_daily.parquet")
    lag = pd.DataFrame(
        {"trade_date": pd.to_datetime(["2026-09-29", lagging or last]), "symbol": "A"}
    )
    lag.to_parquet(live / f"alpha/book_v1/themes_{year}.parquet")


def test_freshness_all_stages_equal_to_sip(tmp_path: Path) -> None:
    _write_live(tmp_path, "2026-10-02")
    now = datetime(2026, 10, 3, 22, 45, tzinfo=UTC)
    fresh = rf.freshness(tmp_path, date(2026, 10, 2), 2026, now=now)
    assert fresh["fresh"] is True and fresh["lagging_stages"] == []
    assert fresh["stages"]["panel"] == {"last_date": "2026-10-02", "equals_sip_last": True}
    assert fresh["generated_utc"] == "2026-10-03T22:45:00Z"


def test_freshness_names_the_lagging_stage_and_missing_files(tmp_path: Path) -> None:
    _write_live(tmp_path, "2026-10-02", lagging="2026-10-01")
    fresh = rf.freshness(tmp_path, date(2026, 10, 2), 2026)
    assert fresh["fresh"] is False and fresh["lagging_stages"] == ["alpha"]
    # SIP ahead of everything: every stage lags
    fresh = rf.freshness(tmp_path, date(2026, 10, 5), 2026)
    assert sorted(fresh["lagging_stages"]) == sorted(rf.FRESH_STAGES)
    # no partition for the new year yet: last_date None, not fresh
    fresh = rf.freshness(tmp_path, date(2027, 1, 4), 2027)
    assert fresh["stages"]["panel"]["last_date"] is None and fresh["fresh"] is False
    # no SIP date at all
    assert rf.freshness(tmp_path, None, 2026)["fresh"] is False
    path = rf.write_freshness(tmp_path, fresh)
    assert json.loads(path.read_text())["year"] == 2027


def test_expected_session_rolls_back_over_weekends_and_before_the_close() -> None:
    sat = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)
    assert rf.expected_session(sat) == date(2026, 10, 2)
    fri_evening = datetime(2026, 10, 2, 22, 45, tzinfo=UTC)
    assert rf.expected_session(fri_evening) == date(2026, 10, 2)
    mon_morning = datetime(2026, 10, 5, 13, 0, tzinfo=UTC)
    assert rf.expected_session(mon_morning) == date(2026, 10, 2)


def test_strict_cut_and_check_command() -> None:
    dates = [date(2026, 9, d) for d in (1, 2, 3, 4, 8, 9)]
    assert rf.strict_cut(dates) == date(2026, 9, 3)
    assert rf.strict_cut(dates[:3]) is None
    table = rf.table_by_name("daily_broad")
    cmd = rf.check_command(
        table, Path("old.parquet"), Path("new.parquet"), date(2026, 9, 3), Path("o.json")
    )
    assert "--price-aware-cols" in cmd and cmd[cmd.index("--cut") + 1] == "2026-09-03"
    plain = rf.check_command(
        rf.table_by_name("insider_broad"), Path("o"), Path("n"), date(2026, 9, 3), Path("r.json")
    )
    assert "--price-col" not in plain


def test_failed_check_restores_the_backup_and_exits_3(tmp_path: Path, monkeypatch) -> None:
    feat = tmp_path / "features"
    (feat / "daily_broad").mkdir(parents=True)
    out = feat / "daily_broad/2026.parquet"
    pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-08"]
            ),
            "symbol": "A",
            "close": 1.0,
        }
    ).to_parquet(out)
    before = out.read_bytes()
    monkeypatch.setattr(rf, "FEATURES", feat)
    monkeypatch.setattr(rf, "STAGE_ROOT", feat / "_tmp")
    monkeypatch.setattr(rf, "BACKUP_ROOT", tmp_path / "backup")
    table = rf.table_by_name("daily_broad")

    def runner(argv, **_kw):
        if "check_feature_invariance.py" in " ".join(argv):
            return subprocess.CompletedProcess(argv, 1, "", "changed rows")
        stage = feat / "_tmp/daily_broad"
        pd.DataFrame(
            {"trade_date": pd.to_datetime(["2026-09-01"]), "symbol": "A", "close": 2.0}
        ).to_parquet(stage / "2026.parquet")
        return subprocess.CompletedProcess(argv, 0, "", "")

    steps = [
        s for s in rf.build_plan(date(2026, 9, 8), tables=[table], stages=[]) if s.kind == "run"
    ]
    code = rf.run_upstream_table(table, date(2026, 9, 8), steps, runner)
    assert code == rf.EXIT_UPSTREAM
    assert out.read_bytes() == before  # the live feature file is untouched

    def ok_runner(argv, **_kw):
        if "check_feature_invariance.py" in " ".join(argv):
            return subprocess.CompletedProcess(argv, 0, "", "")
        return runner(argv)

    assert rf.run_upstream_table(table, date(2026, 9, 8), steps, ok_runner) == rf.EXIT_OK
    assert out.read_bytes() != before  # swapped in after a passing check


def test_upstream_last_dates_flag_the_lagging_table(tmp_path: Path) -> None:
    for name, last in (("daily_broad", "2026-10-02"), ("insider_broad", "2026-10-01")):
        (tmp_path / name).mkdir()
        pd.DataFrame(
            {"trade_date": pd.to_datetime(["2026-09-30", last]), "symbol": "A"}
        ).to_parquet(tmp_path / name / "2026.parquet")
    got = rf.upstream_last_dates(tmp_path, 2026, date(2026, 10, 2))
    assert got["daily_broad"] == {"last_date": "2026-10-02", "reaches_sip_last": True}
    assert got["insider_broad"] == {"last_date": "2026-10-01", "reaches_sip_last": False}
    assert got["news_attention"] == {"last_date": None, "reaches_sip_last": False}


def test_merge_formation_ic_is_idempotent(tmp_path: Path) -> None:
    def frame(dates: list[str], ic: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "formation_date": pd.to_datetime(dates),
                "universe": "u3000",
                "series": "M0",
                "ic": ic,
                "n": 100,
            }
        )

    snap, live = tmp_path / "snap", tmp_path / "live"
    (snap / "alpha/book_v1").mkdir(parents=True)
    (live / "alpha/book_v1").mkdir(parents=True)
    frame(["2024-11-29", "2024-12-31", "2025-01-31"], 0.1).to_parquet(
        snap / "alpha/book_v1/formation_ic.parquet"
    )
    frame(["2024-12-31", "2025-01-31", "2025-02-28"], 0.2).to_parquet(
        live / "alpha/book_v1/formation_ic.parquet"
    )
    path = rf.merge_formation_ic(live, snap)
    merged = pd.read_parquet(path)
    # snapshot rows up to 2024-12-31, live rows from 2025-01-01
    assert merged["formation_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2024-11-29",
        "2024-12-31",
        "2025-01-31",
        "2025-02-28",
    ]
    assert merged["ic"].tolist() == [0.1, 0.1, 0.2, 0.2]
    live_only = pd.read_parquet(live / "alpha/book_v1/formation_ic_live_only.parquet")
    assert len(live_only) == 3 and set(live_only["ic"]) == {0.2}
    # a second call (nothing rebuilt in between) must not turn the merged file into the live-only one
    rf.merge_formation_ic(live, snap)
    assert pd.read_parquet(path)["ic"].tolist() == [0.1, 0.1, 0.2, 0.2]
    assert len(pd.read_parquet(live / "alpha/book_v1/formation_ic_live_only.parquet")) == 3


def test_new_month_ends_only_closed_months() -> None:
    sessions = [date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)]
    assert rf.new_month_ends(date(2026, 8, 31), sessions) == [date(2026, 9, 30)]
    assert rf.new_month_ends(date(2026, 9, 30), sessions) == []  # already stored
    # the latest month is never closed, even when its last session is the last weekday
    assert rf.new_month_ends(date(2026, 8, 31), [date(2026, 9, 29), date(2026, 9, 30)]) == []
    # a missed month is picked up as well, oldest first
    sess = [date(2026, 8, 31), date(2026, 9, 30), date(2026, 10, 2)]
    assert rf.new_month_ends(date(2026, 7, 31), sess) == [date(2026, 8, 31), date(2026, 9, 30)]
    assert rf.new_month_ends(None, []) == []


def _universe_frame(month_ends: list[str], symbols: list[str], adv: float) -> pd.DataFrame:
    rows = [
        {"month_end": pd.Timestamp(m), "symbol": s, "adv_rank": i + 1, "dollar_adv": adv}
        for m in month_ends
        for i, s in enumerate(symbols)
    ]
    return pd.DataFrame(rows)


def _monthly_setup(tmp_path: Path, monkeypatch) -> rf.Table:
    feat = tmp_path / "features"
    (feat / "universe").mkdir(parents=True)
    (feat / "daily_broad").mkdir(parents=True)
    _universe_frame(["2026-08-31"], ["A", "B"], 1.0).to_parquet(feat / "universe/2026.parquet")
    dates = ["2026-08-31", "2026-09-30", "2026-10-01", "2026-10-02"]
    pd.DataFrame({"trade_date": pd.to_datetime(dates), "symbol": "A"}).to_parquet(
        feat / "daily_broad/2026.parquet"
    )
    monkeypatch.setattr(rf, "FEATURES", feat)
    monkeypatch.setattr(rf, "STAGE_ROOT", feat / "_tmp")
    monkeypatch.setattr(rf, "BACKUP_ROOT", tmp_path / "backup")
    return rf.table_by_name("universe")


def test_monthly_table_skips_without_a_new_month_end(tmp_path: Path, monkeypatch) -> None:
    table = _monthly_setup(tmp_path, monkeypatch)
    # make 09-30 already stored: no closed month end is left
    _universe_frame(["2026-08-31", "2026-09-30"], ["A", "B"], 1.0).to_parquet(
        rf.FEATURES / "universe/2026.parquet"
    )
    calls: list[list[str]] = []

    def runner(argv, **_kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    assert rf.run_upstream_table(table, date(2026, 10, 2), [], runner) == rf.EXIT_OK
    assert calls == []  # nothing built, nothing compared


def test_monthly_table_appends_new_month_and_keeps_old_rows(tmp_path: Path, monkeypatch) -> None:
    table = _monthly_setup(tmp_path, monkeypatch)
    out = rf.FEATURES / "universe/2026.parquet"
    before = pd.read_parquet(out)

    def runner(argv, **_kw):
        if "check_feature_invariance.py" in " ".join(argv):
            return subprocess.CompletedProcess(argv, 0, "", "")
        stage = rf.STAGE_ROOT / "universe"
        # the builder re-estimates every month: August moved, September is new
        _universe_frame(["2026-08-31", "2026-09-30"], ["A", "B", "C"], 9.0).to_parquet(
            stage / "2026.parquet"
        )
        return subprocess.CompletedProcess(argv, 0, "", "")

    steps = [
        s for s in rf.build_plan(date(2026, 10, 2), tables=[table], stages=[]) if s.kind == "run"
    ]
    assert rf.run_upstream_table(table, date(2026, 10, 2), steps, runner) == rf.EXIT_OK
    after = pd.read_parquet(out)
    aug = after[after["month_end"] == pd.Timestamp("2026-08-31")].reset_index(drop=True)
    pd.testing.assert_frame_equal(aug, before.reset_index(drop=True))  # old month frozen
    sep = after[after["month_end"] == pd.Timestamp("2026-09-30")]
    assert sorted(sep["symbol"]) == ["A", "B", "C"] and (sep["dollar_adv"] == 9.0).all()
    assert not (rf.STAGE_ROOT / "universe").exists()  # staging cleaned


def test_failed_check_cleans_staging(tmp_path: Path, monkeypatch) -> None:
    feat = tmp_path / "features"
    (feat / "insider_broad").mkdir(parents=True)
    old = pd.DataFrame(
        {"trade_date": pd.to_datetime(["2026-09-30", "2026-10-01"]), "symbol": "A", "x": 1.0}
    )
    old.to_parquet(feat / "insider_broad/2026.parquet")
    old.to_parquet(feat / "insider_broad/2025.parquet")
    monkeypatch.setattr(rf, "FEATURES", feat)
    monkeypatch.setattr(rf, "STAGE_ROOT", feat / "_tmp")
    monkeypatch.setattr(rf, "BACKUP_ROOT", tmp_path / "backup")
    table = rf.table_by_name("insider_broad")
    seen: dict[str, bool] = {}

    def runner(argv, **_kw):
        stage = feat / "_tmp/insider_broad"
        if "check_feature_invariance.py" in " ".join(argv):
            seen["prior_is_copy"] = not (stage / "2025.parquet").is_symlink()
            return subprocess.CompletedProcess(argv, 1, "", "")
        seen["prior_is_copy"] = not (stage / "2025.parquet").is_symlink()
        old.assign(x=2.0).to_parquet(stage / "2026.parquet")
        return subprocess.CompletedProcess(argv, 0, "", "")

    steps = [
        s for s in rf.build_plan(date(2026, 10, 2), tables=[table], stages=[]) if s.kind == "run"
    ]
    assert rf.run_upstream_table(table, date(2026, 10, 2), steps, runner) == rf.EXIT_UPSTREAM
    assert seen["prior_is_copy"] and not (feat / "_tmp/insider_broad").exists()
    assert (feat / "insider_broad/2026.parquet").read_bytes() == (
        tmp_path / "backup/2026-10-02/insider_broad/2026.parquet"
    ).read_bytes()


def test_restatement_cursor_init_and_read(tmp_path: Path) -> None:
    log_file = tmp_path / "_restatements.jsonl"
    log_file.write_text('{"symbol": "A", "max_rel_diff": 0.5}\n' * 3)
    cursor = tmp_path / "state.json"
    assert rf.read_cursor(cursor) is None  # missing cursor: nothing is processed automatically
    assert rf.init_cursor(log_file, cursor) == 3
    assert rf.read_cursor(cursor) == 3
    records, offset = rf.new_split_restatements(log_file, rf.read_cursor(cursor) or 0, None)
    assert records == [] and offset == 3
    log_file.write_text(log_file.read_text() + '{"symbol": "B", "max_rel_diff": 0.9}\n')
    records, offset = rf.new_split_restatements(log_file, 3, None)
    assert [r["symbol"] for r in records] == ["B"] and offset == 4


def _universe_files(root: Path, month_end: str) -> None:
    (root / "universe_broad").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"month_end": pd.to_datetime([month_end]), "symbol": ["A"]}).to_parquet(
        root / "universe_broad/2026.parquet"
    )


def test_membership_cut_follows_the_universe_month_end(tmp_path: Path) -> None:
    feat, state = tmp_path / "features", tmp_path / "state.json"
    _universe_files(feat, "2026-09-30")
    assert rf.last_universe_month_end(feat) == date(2026, 9, 30)
    # first run, no state: conservative, rows from the month end on are not gated
    assert rf.membership_cut(feat, state) == date(2026, 9, 29)
    rf.write_state(state, universe_month_end="2026-08-31")  # a month end came in since the last run
    assert rf.membership_cut(feat, state) == date(2026, 9, 29)
    rf.write_state(state, universe_month_end="2026-09-30")  # nothing new: full gate
    assert rf.membership_cut(feat, state) is None
    # the cursor keeps living in the same file
    rf.write_cursor(5, date(2026, 10, 2), state)
    assert rf.read_cursor(state) == 5 and rf.read_state(state)["universe_month_end"] == "2026-09-30"


def test_membership_cut_limits_the_gate_of_universe_keyed_tables(
    tmp_path: Path, monkeypatch
) -> None:
    feat = tmp_path / "features"
    (feat / "insider_broad").mkdir(parents=True)
    dates = pd.to_datetime(["2026-09-29", "2026-09-30", "2026-10-01"])
    pd.DataFrame({"trade_date": dates, "symbol": "A", "x": 1.0}).to_parquet(
        feat / "insider_broad/2026.parquet"
    )
    monkeypatch.setattr(rf, "FEATURES", feat)
    monkeypatch.setattr(rf, "STAGE_ROOT", feat / "_tmp")
    monkeypatch.setattr(rf, "BACKUP_ROOT", tmp_path / "backup")
    table = rf.table_by_name("insider_broad")
    cuts: list[str] = []

    def runner(argv, **_kw):
        if "check_feature_invariance.py" in " ".join(argv):
            cuts.append(argv[argv.index("--cut") + 1])
            return subprocess.CompletedProcess(argv, 0, "", "")
        pd.DataFrame({"trade_date": dates, "symbol": "A", "x": 1.0}).to_parquet(
            feat / "_tmp/insider_broad/2026.parquet"
        )
        return subprocess.CompletedProcess(argv, 0, "", "")

    steps = [
        s for s in rf.build_plan(date(2026, 10, 1), tables=[table], stages=[]) if s.kind == "run"
    ]
    assert (
        rf.run_upstream_table(table, date(2026, 10, 1), steps, runner, member_cut=date(2026, 9, 29))
        == 0
    )
    assert rf.run_upstream_table(table, date(2026, 10, 1), steps, runner) == 0
    assert cuts == ["2026-09-29", "2026-10-01"]


def test_heavy_process_wait_ignores_own_tree_and_gives_up() -> None:
    procs = [(100, 1, 5_000), (200, 100, 900_000), (300, 200, 800_000), (400, 1, 700_000)]
    # 200/300 are descendants of 100 (me): only 400 blocks
    assert rf.other_heavy_processes(procs, 100, 600_000) == [(400, 700_000)]
    assert rf.other_heavy_processes(procs[:3], 100, 600_000) == []
    ticks = iter(range(0, 10_000, 30))
    sleeps: list[float] = []
    assert not rf.wait_for_quiet(
        600_000,
        max_wait_s=60,
        table=lambda: procs,
        sleep=sleeps.append,
        clock=lambda: float(next(ticks)),
        me=100,
    )
    assert sleeps  # it did wait before giving up
    rows = iter([procs, procs[:3]])
    assert rf.wait_for_quiet(
        600_000, table=lambda: next(rows), sleep=lambda s: None, clock=lambda: 0.0, me=100
    )


def test_new_entrant_symbols_and_allow_flag(tmp_path: Path) -> None:
    old, new = tmp_path / "old.parquet", tmp_path / "new.parquet"
    pd.DataFrame(
        {"symbol": ["A", "B"], "trade_date": pd.to_datetime(["2026-09-01"] * 2)}
    ).to_parquet(old)
    pd.DataFrame(
        {"symbol": ["A", "B", "C"], "trade_date": pd.to_datetime(["2026-09-01"] * 3)}
    ).to_parquet(new)
    assert rf.new_entrant_symbols(old, new) == ["C"]
    table = rf.table_by_name("short_volume_broad")
    allow = tmp_path / "allow.txt"
    cmd = rf.check_command(table, old, new, date(2026, 9, 29), tmp_path / "o.json", allow)
    assert cmd[cmd.index("--allow-only-new") + 1] == str(allow)
    assert "--allow-only-new" not in rf.check_command(
        table, old, new, date(2026, 9, 29), tmp_path / "o.json"
    )


def _restatement(symbol: str, at: str, diff: float, years: list[int], rows=(10, 10)) -> str:
    rec = {
        "detected_at": at,
        "max_rel_diff": diff,
        "mode": "repair",
        "rows_before": rows[0],
        "rows_after": rows[1],
        "symbol": symbol,
        "years_rewritten": years,
    }
    return json.dumps(rec)


BUILT_2022 = datetime(2026, 9, 18, 7, 3, tzinfo=UTC)
BUILT_2026 = datetime(2026, 10, 4, 15, 6, tzinfo=UTC)


def _restatement_log(path: Path) -> Path:
    lines = [
        _restatement("A", "2026-10-02T04:13:19.1+00:00", 49.0, [2021, 2022, 2026]),
        _restatement("A", "2026-10-02T04:13:19.1+00:00", 49.0, [2021, 2022, 2026]),
        _restatement("B", "2026-10-02T04:13:19.1+00:00", 1e-5, [2022]),  # dividend-size
        _restatement("C", "2026-10-02T04:13:19.1+00:00", 1e-5, [2023, 2022], rows=(10, 12)),
        _restatement("D", "2026-09-01T00:00:00+00:00", 3.0, [2022]),  # before the build
        _restatement("E", "2026-10-05T22:00:04+00:00", 7.0, [2026]),
        _restatement("F", "2026-10-02T04:13:19.1+00:00", 9.0, [2026]),  # 2026 rebuilt after it
        _restatement("G", "2026-10-05T22:00:04+00:00", 9.0, [2019]),  # year not replaced
        _restatement("H", "2026-10-05T22:00:04+00:00", 0.004, [2025, 2026]),  # dividend re-basing
        "not json",
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


def test_rebased_symbols_follow_partition_build_times(tmp_path: Path) -> None:
    log = _restatement_log(tmp_path / "_restatements.jsonl")
    parts = [(2022, BUILT_2022), (2026, BUILT_2026)]
    assert rf.rebased_symbols(parts, log) == ["A", "C", "E"]
    assert rf.rebased_symbols([(2026, BUILT_2026)], log) == ["E"]
    assert rf.restated_symbols(parts, log) == ["A", "B", "C", "E", "H"]
    assert rf.restated_symbols([(2026, BUILT_2026)], log) == ["E", "H"]
    assert rf.rebased_symbols([], log) == []
    assert rf.rebased_symbols(parts, tmp_path / "missing.jsonl") == []


def test_replaced_partitions_read_the_backup_build_times(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(rf, "BACKUP_ROOT", tmp_path / "backup")
    root = tmp_path / "backup/2026-10-05/daily_broad"
    root.mkdir(parents=True)
    for year, built in ((2022, BUILT_2022), (2026, BUILT_2026)):
        (root / f"{year}.parquet").write_bytes(b"x")
        os.utime(root / f"{year}.parquet", (built.timestamp(), built.timestamp()))
    (root / "notes.txt").write_text("not a partition")
    assert rf.replaced_partitions(date(2026, 10, 5)) == [(2022, BUILT_2022), (2026, BUILT_2026)]
    assert rf.replaced_partitions(date(2026, 10, 6)) == []


def _nsi_frame(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [s for s, _ in rows],
            "trade_date": pd.to_datetime([d for _, d in rows]),
            "nsi252": 0.1,
        }
    )


def _rebased_setup(tmp_path: Path, monkeypatch) -> Path:
    feat = tmp_path / "features"
    monkeypatch.setattr(rf, "FEATURES", feat)
    monkeypatch.setattr(rf, "STAGE_ROOT", feat / "_tmp")
    monkeypatch.setattr(rf, "BACKUP_ROOT", tmp_path / "backup")
    monkeypatch.setattr(rf, "SIP_DAILY", tmp_path / "sip")
    (tmp_path / "sip").mkdir()
    _restatement_log(tmp_path / "sip/_restatements.jsonl")
    part = tmp_path / "backup/2026-10-05/daily_broad/2022.parquet"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"x")
    os.utime(part, (BUILT_2022.timestamp(), BUILT_2022.timestamp()))
    return feat


def test_rebased_keys_are_allowed_only_for_price_following_tables(
    tmp_path: Path, monkeypatch
) -> None:
    feat = _rebased_setup(tmp_path, monkeypatch)
    day = date(2026, 10, 5)
    seen: dict[str, list[str]] = {}
    for name, rel in (("nsi", "nsi/nsi.parquet"), ("insider_broad", "insider_broad/2026.parquet")):
        out = feat / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        _nsi_frame([("A", "2026-01-05"), ("Z", "2026-01-05")]).to_parquet(out)
        table = rf.table_by_name(name)
        target = out if table.in_place else feat / "_tmp" / name / out.name

        def runner(argv, _target=target, _name=name, **_kw):
            if "check_feature_invariance.py" in " ".join(argv):
                seen[_name] = list(argv)
                return subprocess.CompletedProcess(argv, 0, "", "")
            _nsi_frame([("A", "2026-02-02"), ("Z", "2026-01-05")]).to_parquet(_target)
            return subprocess.CompletedProcess(argv, 0, "", "")

        steps = [s for s in rf.build_plan(day, tables=[table], stages=[]) if s.kind == "run"]
        assert rf.run_upstream_table(table, day, steps, runner) == rf.EXIT_OK
    nsi = seen["nsi"]
    allow_new = Path(nsi[nsi.index("--allow-only-new") + 1]).read_text().split()
    allow_old = Path(nsi[nsi.index("--allow-only-old") + 1]).read_text().split()
    assert allow_new == allow_old == ["A", "C"]  # E rewrote 2026, which was not replaced here
    assert "--allow-only-old" not in seen["insider_broad"]
    assert "--allow-only-new" not in seen["insider_broad"]
    assert rf.table_by_name("sec_fundamentals_daily").keys_follow_prices
    assert not any(t.keys_follow_prices for t in rf.UPSTREAM if t.check == "price")


def test_check_command_passes_the_allow_old_file() -> None:
    table = rf.table_by_name("nsi")
    cmd = rf.check_command(
        table, Path("o"), Path("n"), date(2026, 10, 2), Path("r.json"), None, Path("old.txt")
    )
    assert cmd[cmd.index("--allow-only-old") + 1] == "old.txt"
    assert "--allow-only-new" not in cmd


def test_backup_is_taken_once_per_day(tmp_path: Path, monkeypatch) -> None:
    feat = _rebased_setup(tmp_path, monkeypatch)
    out = feat / "nsi/nsi.parquet"
    out.parent.mkdir(parents=True)
    _nsi_frame([("Z", "2026-01-05")]).to_parquet(out)
    first = out.read_bytes()
    table = rf.table_by_name("nsi")
    day = date(2026, 10, 5)
    versions = iter(["2026-01-06", "2026-01-07"])

    def runner(argv, **_kw):
        if "check_feature_invariance.py" not in " ".join(argv):
            _nsi_frame([("Z", "2026-01-05"), ("Z", next(versions))]).to_parquet(out)
        return subprocess.CompletedProcess(argv, 0, "", "")

    steps = [s for s in rf.build_plan(day, tables=[table], stages=[]) if s.kind == "run"]
    assert rf.run_upstream_table(table, day, steps, runner) == rf.EXIT_OK
    assert rf.run_upstream_table(table, day, steps, runner) == rf.EXIT_OK
    assert rf._backup_path(table, 2026, day).read_bytes() == first


def test_price_level_columns_use_two_zones_and_leave_restated_symbols_out(
    tmp_path: Path, monkeypatch
) -> None:
    feat = _rebased_setup(tmp_path, monkeypatch)
    day = date(2026, 10, 5)
    daily = tmp_path / "backup/2026-10-05/daily/2026.parquet"
    daily.parent.mkdir(parents=True)
    daily.write_bytes(b"x")
    os.utime(daily, (BUILT_2026.timestamp(), BUILT_2026.timestamp()))
    days = ["2026-09-24", "2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"]
    seen: dict[str, list[str]] = {}
    for name in ("short_interest", "insider_broad"):
        out = feat / name / "2026.parquet"
        out.parent.mkdir(parents=True)
        _nsi_frame([("A", d) for d in [*days, "2026-10-02"]]).to_parquet(out)
        table = rf.table_by_name(name)

        def runner(argv, _name=name, **_kw):
            if "check_feature_invariance.py" in " ".join(argv):
                seen[_name] = list(argv)
            else:
                _nsi_frame([("A", d) for d in [*days, "2026-10-02", "2026-10-05"]]).to_parquet(
                    feat / "_tmp" / _name / "2026.parquet"
                )
            return subprocess.CompletedProcess(argv, 0, "", "")

        steps = [s for s in rf.build_plan(day, tables=[table], stages=[]) if s.kind == "run"]
        assert rf.run_upstream_table(table, day, steps, runner) == rf.EXIT_OK
    si = seen["short_interest"]
    assert si[si.index("--cut") + 1] == "2026-09-29"  # last date minus 3 sessions
    assert Path(si[si.index("--exclude-symbols") + 1]).read_text().split() == ["E", "H"]
    plain = seen["insider_broad"]
    assert plain[plain.index("--cut") + 1] == "2026-10-02"
    assert "--exclude-symbols" not in plain
    assert [t.name for t in rf.UPSTREAM if t.values_follow] == ["short_interest"]
