import subprocess
from datetime import date
from pathlib import Path

import pandas as pd

from scripts import refresh_equity_book_live as rf


def test_inplace_forward_failure_restores_the_published_bytes(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(rf.__file__).parent))
    import forward_feature_epoch as epoch

    features = tmp_path / "features"
    out = features / "nsi/nsi.parquet"
    out.parent.mkdir(parents=True)
    pd.DataFrame(
        {"symbol": ["A"], "trade_date": pd.to_datetime(["2026-10-07"]), "nsi252": [0.1]}
    ).to_parquet(out, index=False)
    original = out.read_bytes()
    monkeypatch.setattr(rf, "ROOT", tmp_path)
    monkeypatch.setattr(rf, "FEATURES", features)
    monkeypatch.setattr(rf, "BACKUP_ROOT", tmp_path / "backup")
    monkeypatch.setattr(rf, "STAGE_ROOT", features / "_tmp")

    def runner(argv, **kwargs):
        pd.DataFrame(
            {"symbol": ["A"], "trade_date": pd.to_datetime(["2026-10-08"]), "nsi252": [0.2]}
        ).to_parquet(out, index=False)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fail(*args, **kwargs):
        raise ValueError("binding failure")

    monkeypatch.setattr(epoch, "publish_forward_table", fail)
    table = rf.table_by_name("nsi")
    step = rf.Step("up:nsi", "build", ["bounded-test"])
    result = rf.run_upstream_table(
        table,
        date(2026, 10, 8),
        [step],
        runner,
        forward_config={"tables": {"nsi": {}}, "version_directory": "version"},
    )
    assert result == rf.EXIT_UPSTREAM
    assert out.read_bytes() == original


def test_existing_source_caches_are_reparsed_after_fetch():
    assert "--force" in rf.table_by_name("sec_fundamentals_facts").build
    assert "--force" in rf.table_by_name("news_attention").pre_build[0]
    for name in ("short_volume_broad", "short_interest"):
        parsers = [
            cmd
            for cmd in rf.table_by_name(name).fetch
            if "--stage" in cmd and cmd[cmd.index("--stage") + 1] == "parse"
        ]
        assert len(parsers) == 1 and "--force" in parsers[0]
