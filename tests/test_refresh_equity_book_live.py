# ruff: noqa: E501
"""Plan, lock and freshness logic of the live-root refresh driver (no network, no big files)."""

from __future__ import annotations

import json
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
