from datetime import date
import json
from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from forward_feature_epoch import publish_forward_table
from prepare_host_forward_version import sha256


def test_each_new_suffix_freezes_previously_published_history(tmp_path):
    old = tmp_path / "anchor.parquet"
    first = pd.DataFrame({"symbol": ["A"], "trade_date": pd.to_datetime(["2026-10-07"]), "close": [10.]})
    first.to_parquet(old, index=False)
    manifest = tmp_path / "source.json"
    manifest.write_text('{}\n')
    config = {"tables": {"daily": {"anchor_sha256": sha256(old)}}, "year": 2026,
              "version_directory": "version", "version_id": "test", "anchor_end": "2026-10-07",
              "runtime_source_manifest": str(manifest)}
    out = tmp_path / "live.parquet"
    candidate = tmp_path / "day8.parquet"
    pd.concat([first.assign(close=99.), pd.DataFrame({"symbol": ["A"],
        "trade_date": pd.to_datetime(["2026-10-08"]), "close": [11.]})]).to_parquet(candidate, index=False)
    publish_forward_table(tmp_path, "daily", old, candidate, out, date(2026, 10, 8), config)
    assert pd.read_parquet(out).close.tolist() == [10., 11.]
    backup = tmp_path / "backup.parquet"
    backup.write_bytes(out.read_bytes())
    second = tmp_path / "day9.parquet"
    pd.DataFrame({"symbol": ["A", "A", "A"],
        "trade_date": pd.to_datetime(["2026-10-07", "2026-10-08", "2026-10-09"]),
        "close": [199., 111., 12.]}).to_parquet(second, index=False)
    publish_forward_table(tmp_path, "daily", backup, second, out, date(2026, 10, 9), config)
    assert pd.read_parquet(out).close.tolist() == [10., 11., 12.]
    receipt = json.loads((tmp_path / "version/latest/daily.json").read_text())
    assert receipt["prefix_end"] == "2026-10-08"
    assert receipt["original_whole_panel_invariance_pass"] is None
    assert (tmp_path / "version/natural-candidates/2026-10-08/daily.parquet").is_file()
    with pytest.raises(ValueError, match="receipt/hash mismatch"):
        publish_forward_table(tmp_path, "daily", old, second, out, date(2026, 10, 12), config)
