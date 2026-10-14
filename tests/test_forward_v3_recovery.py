"""The three independent v2 counterexamples, with expected recovery outcomes."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import forward_feature_epoch as epoch
import forward_publication as publication
import forward_refresh_io as io
from prepare_host_forward_version import sha256

from scripts import refresh_equity_book_live as rf


def frame(path, days, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table(
            {
                "symbol": ["A"] * len(days),
                "trade_date": pa.array(days).cast(pa.timestamp("ns")),
                "value": values,
            }
        ),
        path,
    )


def config(root, old):
    source = root / "source.json"
    source.write_text('{"corrected_bindings":[]}')
    return {
        "year": 2026,
        "version_id": "test",
        "anchor_end": "2026-10-13",
        "version_directory": "versions",
        "tables": {"nsi": {"anchor_sha256": sha256(old)}},
        "runtime_context_manifest": str(source),
        "runtime_source_manifest": str(source),
    }


def test_r1_inplace_compose_failure_preserves_natural_inode(tmp_path, monkeypatch):
    features = tmp_path / "data/features"
    out = features / "nsi/nsi.parquet"
    frame(out, ["2026-10-13"], [1.0])
    accepted = sha256(out)
    cfg = config(tmp_path, out)
    for key, value in {
        "ROOT": tmp_path,
        "FEATURES": features,
        "BACKUP_ROOT": tmp_path / "backup",
        "STAGE_ROOT": features / "_tmp",
    }.items():
        monkeypatch.setattr(rf, key, value)
    monkeypatch.setattr(io, "stage_admission", lambda *a: None)
    produced = []

    def runner(argv, **kw):
        frame(out, ["2026-10-13", "2026-10-14", "2026-10-14"], [99.0, 2.0, 3.0])
        produced.append(sha256(out))
        return subprocess.CompletedProcess(argv, 0, "", "")

    result = rf.run_upstream_table(
        rf.table_by_name("nsi"),
        date(2026, 10, 14),
        [rf.Step("up:nsi", "build test", ["inert"])],
        runner,
        forward_config=cfg,
    )
    retained = next((tmp_path / "versions/natural-candidates/2026-10-14").glob("*.parquet"))
    assert result == rf.EXIT_UPSTREAM and sha256(out) == accepted
    assert sha256(retained) == produced[0] != accepted
    assert out.stat().st_ino != retained.stat().st_ino


@pytest.mark.parametrize("legacy", [False, True])
def test_r2_prepared_natural_output_rolls_back_and_keeps_candidate(tmp_path, monkeypatch, legacy):
    old, out = tmp_path / "old.parquet", tmp_path / "out.parquet"
    frame(old, ["2026-10-13"], [1.0])
    frame(out, ["2026-10-13", "2026-10-14"], [99.0, 2.0])
    natural_hash = sha256(out)
    cfg = config(tmp_path, old)
    replace = Path.replace

    def interrupted(path, target):
        if path.name.endswith(".forward.parquet") and Path(target) == out:
            raise OSError("injected prepared-before-replace")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", interrupted)
    with pytest.raises(OSError, match="prepared-before-replace"):
        epoch.publish_forward_table(tmp_path, "nsi", old, out, out, date(2026, 10, 14), cfg)
    monkeypatch.setattr(Path, "replace", replace)
    journal = next((tmp_path / "versions/transactions").glob("*.json"))
    value = json.loads(journal.read_text())
    assert value["status"] == "prepared" and value["output_was_candidate_inode"]
    if legacy:
        value.pop("output_before_sha256")
        value.pop("output_was_candidate_inode")
        journal.write_text(json.dumps(value))
    publication.recover_pending(tmp_path / "versions")
    final = json.loads(journal.read_text())
    assert final["status"] == "rolled_back"
    assert final["recovered_from_recorded_natural_output"]
    assert sha256(out) == sha256(old)
    assert sha256(Path(final["candidate"])) == natural_hash
    assert out.stat().st_ino != Path(final["candidate"]).stat().st_ino
    # A new attempt succeeds from the restored accepted prefix without deleting any journal.
    candidate = tmp_path / "next-attempt.parquet"
    frame(candidate, ["2026-10-14"], [2.0])
    epoch.publish_forward_table(tmp_path, "nsi", old, candidate, out, date(2026, 10, 14), cfg)
    assert pq.read_table(out)["value"].to_pylist() == [1.0, 2.0]


def test_r3_old_products_reference_and_real_copy_bytes_admitted_first(tmp_path, monkeypatch):
    live = tmp_path / "live"
    cfg = {"year": 2026, "version_directory": "versions", "disk_spill_bound_bytes": 1}
    old = live / "alpha/book_v1/themes_2025.parquet"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"x" * 4096)
    risk = live / "risk/cov_2025.parquet"
    risk.parent.mkdir(parents=True)
    risk.write_bytes(b"r" * 4096)
    metadata = live / "other.bin"
    metadata.write_bytes(b"m" * 4096)
    # Explicit link_prior_years cost, not hidden in a generic allowance.
    table = rf.table_by_name("short_interest")
    prior = tmp_path / "data/features/short_interest/2025.parquet"
    prior.parent.mkdir(parents=True)
    prior.write_bytes(b"p" * 8192)
    receipt = io.disk_admission(
        tmp_path,
        cfg,
        source_root=tmp_path,
        tables=[table],
        live=live,
        stages=["alpha"],
        year=2026,
        fetch=False,
    )
    assert receipt["terms"]["live_view_physical_copies_bytes"] == 4096
    assert receipt["terms"]["link_prior_years_physical_copies_bytes"] == 8192
    view = io.live_view(tmp_path, cfg, live)
    for path in [old, risk]:
        target = view / path.relative_to(live)
        assert target.is_symlink() and target.resolve() == path
    assert not (view / "other.bin").is_symlink()

    class NoRoom:
        f_bavail = 0
        f_frsize = 1

    monkeypatch.setattr(io.os, "statvfs", lambda _: NoRoom())
    before = set((tmp_path / "versions/live-attempts").iterdir())
    with pytest.raises(OSError, match="disk reserve lost"):
        io.live_view(tmp_path, cfg, live)
    assert set((tmp_path / "versions/live-attempts").iterdir()) == before


def test_r3_writable_theme_detaches_from_reference(tmp_path, monkeypatch):
    live = tmp_path / "live"
    old = live / "alpha/book_v1/themes_2025.parquet"
    current = live / "alpha/book_v1/themes_2026.parquet"
    frame(old, ["2025-12-31"], [0.0])
    frame(current, ["2026-10-13"], [1.0])
    old_hash, current_hash = sha256(old), sha256(current)
    cfg = config(tmp_path, current)
    name = io.reader_name("alpha/book_v1/themes_2026.parquet")
    cfg["readers"] = {name: {"anchor_sha256": current_hash, "anchor_end": "2026-10-13"}}
    monkeypatch.setattr(io, "stage_admission", lambda *a: None)
    step = rf.Step("live:alpha", "build", ["inert"])

    def execute(step, runner):
        view = Path(step.env["OC_EQUITY_BOOK_DIR"])
        target = view / "alpha/book_v1/themes_2026.parquet"
        assert not target.exists() and not target.is_symlink()
        assert (view / "alpha/book_v1/themes_2025.parquet").is_symlink()
        frame(target, ["2026-10-13", "2026-10-14"], [99.0, 2.0])
        assert sha256(current) == current_hash
        return 0

    assert (
        io.run_live_stage(tmp_path, cfg, live, date(2026, 10, 14), "alpha", [step], execute, None)
        == 0
    )
    assert sha256(old) == old_hash
    assert pq.read_table(current)["value"].to_pylist() == [1.0, 2.0]
