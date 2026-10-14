import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import forward_publication as publication
import forward_refresh_io as io
from forward_feature_epoch import publish_forward_table
from prepare_host_forward_version import sha256, verify_prefix

from scripts import refresh_equity_book_live as rf


def frame(path, dates, values, keys=("symbol", "trade_date")):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {key: ["A"] * len(dates) for key in keys if key != "trade_date"}
    data.update(trade_date=pd.to_datetime(dates), value=values)
    pd.DataFrame(data).to_parquet(path, index=False)


def config(root, old, name="daily"):
    manifest = root / "source-manifest.json"
    manifest.write_text(json.dumps({"corrected_bindings": []}))
    return {
        "year": 2026,
        "version_id": "test",
        "anchor_end": "2026-10-13",
        "version_directory": "versions",
        "tables": {name: {"anchor_sha256": sha256(old)}},
        "runtime_context_manifest": str(manifest),
        "runtime_source_manifest": str(manifest),
    }


def test_dependency_snapshot_after_actual_monthly_update(tmp_path, monkeypatch):
    monkeypatch.setattr(io, "stage_admission", lambda *a: None)
    monkeypatch.setattr(rf, "wait_for_quiet", lambda: True)
    features = tmp_path / "features"
    old = features / "daily_broad/2026.parquet"
    frame(old, ["2026-10-30", "2026-11-02"], [1.0, 2.0])
    universe = features / "universe_broad/2026.parquet"
    universe.parent.mkdir(parents=True)
    pd.DataFrame(
        {"symbol": ["A"], "month_end": pd.to_datetime(["2026-09-30"]), "value": [1.0]}
    ).to_parquet(universe, index=False)
    before = sha256(universe)
    cfg = config(tmp_path, old, "daily_broad")
    cfg["anchor_end"] = "2026-11-02"
    cfg.update(runtime_primary_root="unused", runtime_delisted_root="unused")
    for key, value in {
        "ROOT": tmp_path,
        "LIVE": tmp_path / "live",
        "FEATURES": features,
        "BACKUP_ROOT": tmp_path / "backups",
        "STAGE_ROOT": features / "_tmp",
    }.items():
        monkeypatch.setattr(rf, key, value)

    def runner(argv, **kw):
        if "--out-dir" in argv:
            target = tmp_path / argv[argv.index("--out-dir") + 1] / "2026.parquet"
            if "universe_broad" in str(target):
                target.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame(
                    {
                        "symbol": ["A", "A"],
                        "month_end": pd.to_datetime(["2026-09-30", "2026-10-30"]),
                        "value": [99.0, 3.0],
                    }
                ).to_parquet(target, index=False)
            else:
                frame(target, ["2026-10-30", "2026-11-02", "2026-11-03"], [99.0, 99.0, 3.0])
        return subprocess.CompletedProcess(argv, 0, "", "")

    tables = [rf.table_by_name(n) for n in ["universe_broad", "daily_broad"]]
    plan = rf.build_plan(
        date(2026, 11, 3), tables=tables, stages=[], fetch=False, forward_config=cfg
    )
    assert rf.run_plan(date(2026, 11, 3), plan, runner, forward_config=cfg) == 0
    assert sha256(universe) != before
    manifest = json.loads(Path(cfg["runtime_source_manifest"]).read_text())
    binding = next(
        v for v in manifest["producer_dependencies"] if v["source_path"] == str(universe)
    )
    assert binding["sha256"] == sha256(universe)
    assert len(pd.read_parquet(universe)) == 2
    assert pd.read_parquet(universe)["value"].iloc[0] == 1.0
    assert pd.read_parquet(old)["value"].tolist() == [1.0, 2.0, 3.0]


def test_all_nine_reader_prefixes_same_day_next_session_and_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(io, "stage_admission", lambda *a: None)
    monkeypatch.setattr(rf, "wait_for_quiet", lambda: True)
    live = tmp_path / "live"
    cfg = {
        "year": 2026,
        "version_id": "test",
        "anchor_end": "2026-10-13",
        "version_directory": "versions",
        "tables": {},
        "readers": {},
    }
    source = tmp_path / "source-manifest.json"
    source.write_text(json.dumps({"corrected_bindings": []}))
    cfg.update(runtime_context_manifest=str(source), runtime_source_manifest=str(source))
    old_bytes, pre2026 = {}, {}
    for outputs in io.READER_OUTPUTS.values():
        for relative, keys in outputs:
            relative = relative.format(year=2026)
            path = live / relative
            frame(path, ["2026-10-13", "2026-10-13"], [1.0, 2.0], keys)
            cfg["readers"][io.reader_name(relative)] = {
                "anchor_sha256": sha256(path),
                "anchor_end": "2026-10-13",
            }
            old_bytes[relative] = path.read_bytes()
            prior = live / relative.replace("2026", "2025") if "2026" in relative else None
            if prior:
                frame(prior, ["2025-12-31"], [0.0], keys)
                pre2026[prior] = sha256(prior)
    (live / "risk/meta.json").write_text(json.dumps({"asof": "2026-10-13", "groups": ["A"]}))
    monkeypatch.setattr(rf, "ROOT", tmp_path)
    monkeypatch.setattr(rf, "LIVE", live)
    calls = []
    now = [date(2026, 10, 14)]

    def runner(argv, **kw):
        view = Path(kw["env"]["OC_EQUITY_BOOK_DIR"])
        if "scripts/build_equity_book_risk.py" in argv:
            assert argv[argv.index("--out") + 1] == str(view / "risk")
            assert "--write-from-year" in argv
            stage = "risk"
        elif "scripts/build_book_v1_alpha.py" in argv:
            assert "--write-from-year" in argv
            stage = "alpha"
        elif "scripts/build_equity_book_signals.py" in argv:
            stage = "signals"
        else:
            stage = next(s for s in ["panel", "prices", "etf"] if s in argv)
            if stage == "prices":
                assert "--years" in argv
        calls.append(stage)
        if stage == "risk":
            (view / "risk/meta.json").write_text(
                json.dumps({"asof": now[0].isoformat(), "groups": ["A"]})
            )
        for relative, keys in io.READER_OUTPUTS[stage]:
            frame(
                view / relative.format(year=2026),
                ["2026-10-13", "2026-10-14", now[0].isoformat()]
                if now[0].day == 15
                else ["2026-10-13", "2026-10-14"],
                [99.0, 99.0, 3.0] if now[0].day == 15 else [99.0, 3.0],
                keys,
            )
        return subprocess.CompletedProcess(argv, 0, "", "")

    stages = list(io.READER_OUTPUTS)
    for stage in stages:
        plan = rf.build_plan(now[0], upstream=False, stages=[stage], forward_config=cfg)
        assert rf.run_plan(now[0], plan, runner, forward_config=cfg) == 0
    assert io.already_published(tmp_path, cfg, now[0], [], live, stages)
    count = len(calls)
    for stage in stages:
        plan = rf.build_plan(now[0], upstream=False, stages=[stage], forward_config=cfg)
        assert rf.run_plan(now[0], plan, runner, forward_config=cfg) == 0
    assert len(calls) == count
    first = {}
    for relative in old_bytes:
        path = live / relative
        assert pd.read_parquet(path)["value"].tolist() == [1.0, 2.0, 3.0]
        first[relative] = path.read_bytes()
    now[0] = date(2026, 10, 15)
    cfg.pop("runtime_live_root")
    for stage in stages:
        plan = rf.build_plan(now[0], upstream=False, stages=[stage], forward_config=cfg)
        assert rf.run_plan(now[0], plan, runner, forward_config=cfg) == 0
    assert len(calls) == count * 2
    assert json.loads((live / "risk/meta.json").read_text())["asof"] == "2026-10-15"
    for relative in old_bytes:
        assert pd.read_parquet(live / relative)["value"].tolist() == [1.0, 2.0, 3.0, 3.0]
    assert all(sha256(path) == value for path, value in pre2026.items())


def test_output_replaced_head_write_interrupted_recovers_without_replay(tmp_path, monkeypatch):
    old, output, candidate = [
        tmp_path / n for n in ["old.parquet", "output.parquet", "candidate.parquet"]
    ]
    frame(old, ["2026-10-13"], [1.0])
    output.write_bytes(old.read_bytes())
    frame(candidate, ["2026-10-13", "2026-10-14"], [99.0, 2.0])
    cfg = config(tmp_path, old)
    original = publication.atomic_json

    def interrupted(path, value):
        if path.parent.name == "latest":
            raise OSError("injected ENOSPC after output replacement")
        original(path, value)

    monkeypatch.setattr(publication, "atomic_json", interrupted)
    with pytest.raises(OSError):
        publish_forward_table(tmp_path, "daily", old, candidate, output, date(2026, 10, 14), cfg)
    assert pd.read_parquet(output)["value"].tolist() == [1.0, 2.0]
    assert not (tmp_path / "versions/latest/daily.json").exists()
    monkeypatch.setattr(publication, "atomic_json", original)
    publication.recover_pending(tmp_path / "versions")
    head = json.loads((tmp_path / "versions/latest/daily.json").read_text())
    assert head["output"]["sha256"] == sha256(output)
    assert head["output"]["path"] == "output.parquet"
    assert verify_prefix(old, output)["rows"] == 1
    journal = next((tmp_path / "versions/transactions").glob("*.json"))
    assert json.loads(journal.read_text())["recovered_from_matching_output"]


def test_real_disk_gate_refuses_before_snapshot(tmp_path, monkeypatch):
    class Stat:
        f_bavail = 1
        f_frsize = 1

    monkeypatch.setattr(io.os, "statvfs", lambda p: Stat())
    cfg = {"version_directory": "versions"}
    with pytest.raises(OSError, match="disk admission failed"):
        io.disk_admission(
            tmp_path,
            cfg,
            source_root=tmp_path,
            tables=[],
            live=tmp_path,
            stages=[],
            year=2026,
            fetch=False,
        )
    assert not (tmp_path / "versions/context").exists()
    receipt = next((tmp_path / "versions/admissions").glob("*.json"))
    assert not json.loads(receipt.read_text())["admitted"]


def test_verified_previous_context_reuses_only_uncorrected_snapshot(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from prepare_forward_source_context import prepare_context

    root = tmp_path / "source"
    raw = root / "data/sip/daily/2026"
    raw.mkdir(parents=True)
    azn = pa.table(
        {
            "symbol": ["AZN"] * 20,
            "timestamp": pd.date_range("2026-01-01", periods=20),
            "close": [1.0] * 20,
        }
    )
    pq.write_table(azn, raw / "azn.parquet")
    canonical = pa.table(
        {
            "symbol": ["WORX"] * 69,
            "timestamp": pd.date_range("2026-02-01", periods=69),
            "close": [2.0] * 69,
        }
    )
    pq.write_table(canonical, root / "canonical.parquet")
    for name in ["canonical1.parquet", "canonical2.parquet"]:
        pq.write_table(canonical, raw / name)
    unchanged = raw / "ordinary.parquet"
    pq.write_table(
        pa.table({"symbol": ["A"], "timestamp": pd.to_datetime(["2026-01-01"]), "close": [3.0]}),
        unchanged,
    )
    quarantine = root / "quarantine.json"
    quarantine.write_text(
        json.dumps(
            {
                "target_shard": "2026/azn.parquet",
                "quarantine_keys": [
                    ["AZN", str(v)[:10]] for v in pd.date_range("2026-01-01", periods=20)
                ],
            }
        )
    )
    cfg = {
        "year": 2026,
        "source_corrections": {
            "AZN_manifest": "quarantine.json",
            "AZN_manifest_sha256": sha256(quarantine),
            "canonical69": "canonical.parquet",
            "canonical69_sha256": sha256(root / "canonical.parquet"),
            "canonical_input_paths": [
                "data/sip/daily/2026/canonical1.parquet",
                "data/sip/daily/2026/canonical2.parquet",
            ],
        },
    }
    first, second = tmp_path / "first", tmp_path / "second"
    prepare_context(root, cfg, first, 2026)
    before = {p.relative_to(first): sha256(p) for p in first.rglob("*.parquet")}
    result = prepare_context(root, cfg, second, 2026, previous=first)
    assert result["reused_verified_snapshot_bytes"] == unchanged.stat().st_size
    assert (first / "data/sip/daily/2026/ordinary.parquet").stat().st_ino == (
        second / "data/sip/daily/2026/ordinary.parquet"
    ).stat().st_ino
    assert (first / "data/sip/daily/2026/azn.parquet").stat().st_ino != (
        second / "data/sip/daily/2026/azn.parquet"
    ).stat().st_ino
    assert all(sha256(first / key) == value for key, value in before.items())


def test_recovery_refuses_an_independently_changed_output(tmp_path, monkeypatch):
    old, output, candidate = [
        tmp_path / n for n in ["old.parquet", "output.parquet", "candidate.parquet"]
    ]
    frame(old, ["2026-10-13"], [1.0])
    output.write_bytes(old.read_bytes())
    frame(candidate, ["2026-10-14"], [2.0])
    cfg = config(tmp_path, old)
    original = publication.atomic_json

    def interrupted(path, value):
        if path.parent.name == "latest":
            raise OSError("injected failure")
        original(path, value)

    monkeypatch.setattr(publication, "atomic_json", interrupted)
    with pytest.raises(OSError):
        publish_forward_table(tmp_path, "daily", old, candidate, output, date(2026, 10, 14), cfg)
    monkeypatch.setattr(publication, "atomic_json", original)
    frame(output, ["2026-10-14"], [777.0])
    with pytest.raises(ValueError, match="matches neither"):
        publication.recover_pending(tmp_path / "versions")


def test_alpha_metadata_interruption_restores_merged_ic_without_rebuilding(tmp_path, monkeypatch):
    live, snapshot = tmp_path / "live", tmp_path / "snapshot"
    theme = live / "alpha/book_v1/themes_2026.parquet"
    frame(theme, ["2026-10-13"], [1.0])
    cfg = config(tmp_path, theme)
    cfg["tables"] = {}
    name = io.reader_name("alpha/book_v1/themes_2026.parquet")
    cfg["readers"] = {name: {"anchor_sha256": sha256(theme), "anchor_end": "2026-10-13"}}
    old_ic = pd.DataFrame(
        {
            "formation_date": pd.to_datetime(["2024-12-31", "2025-01-31"]),
            "universe": ["U", "U"],
            "series": ["S", "S"],
            "ic": [0.1, 0.2],
        }
    )
    ic_path = live / "alpha/book_v1/formation_ic.parquet"
    old_ic.to_parquet(ic_path, index=False)
    frozen = snapshot / "alpha/book_v1/formation_ic.parquet"
    frozen.parent.mkdir(parents=True)
    old_ic.to_parquet(frozen, index=False)
    old_sha = sha256(ic_path)
    for key, value in [("ROOT", tmp_path), ("LIVE", live), ("SNAPSHOT", snapshot)]:
        monkeypatch.setattr(rf, key, value)
    monkeypatch.setattr(io, "stage_admission", lambda *a: None)
    monkeypatch.setattr(rf, "wait_for_quiet", lambda: True)

    def runner(argv, **kw):
        view = Path(kw["env"]["OC_EQUITY_BOOK_DIR"])
        frame(view / "alpha/book_v1/themes_2026.parquet", ["2026-10-13", "2026-10-14"], [99.0, 2.0])
        fresh = pd.DataFrame(
            {
                "formation_date": pd.to_datetime(["2025-01-31", "2026-09-30"]),
                "universe": ["U", "U"],
                "series": ["S", "S"],
                "ic": [0.2, 0.3],
            }
        )
        fresh.to_parquet(view / "alpha/book_v1/formation_ic.parquet", index=False)
        return subprocess.CompletedProcess(argv, 0, "", "")

    original = io.shutil.copyfile

    def failure(source, target, *a, **kw):
        if str(target).endswith(".forward.tmp"):
            raise OSError("injected metadata replacement interruption")
        return original(source, target, *a, **kw)

    monkeypatch.setattr(io.shutil, "copyfile", failure)
    plan = rf.build_plan(date(2026, 10, 14), upstream=False, stages=["alpha"], forward_config=cfg)
    assert rf.run_plan(date(2026, 10, 14), plan, runner, forward_config=cfg) == rf.EXIT_UPSTREAM
    assert sha256(ic_path) == old_sha
    assert pd.read_parquet(theme)["value"].tolist() == [1.0, 2.0]
    monkeypatch.setattr(io.shutil, "copyfile", original)
    io.recover_metadata(tmp_path / "versions")
    assert pd.read_parquet(ic_path)["ic"].tolist() == [0.1, 0.2, 0.3]
    assert (live / "alpha/book_v1/formation_ic_merge.json").exists()
