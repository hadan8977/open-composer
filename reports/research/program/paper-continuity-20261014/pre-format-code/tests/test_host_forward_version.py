from pathlib import Path
import sys

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prepare_host_forward_version as forward


def inputs(tmp_path, duplicate_suffix=False):
    dates = pa.array(["2026-10-06", "2026-10-07", "2026-10-07"]).cast(pa.timestamp("ns"))
    old = pa.table({"symbol": ["A", "A", "A"], "trade_date": dates,
                    "close": [1.0, -0.0, np.nan], "ret_1": [None, 0.1, 0.2], "covered": [True, None, False]})
    suffix = pa.table({"symbol": ["A", "A" if duplicate_suffix else "B"],
                      "trade_date": pa.array(["2026-10-08", "2026-10-08"]).cast(pa.timestamp("ns")),
                      "close": [2.0, 3.0], "ret_1": [0.3, None], "covered": [True, False]})
    pq.write_table(old, tmp_path / "old.parquet")
    pq.write_table(pa.concat_tables([old, suffix]), tmp_path / "candidate.parquet")
    (tmp_path / "source.json").write_text("{}\n")
    return dict(baseline=tmp_path / "old.parquet", candidate=tmp_path / "candidate.parquet",
                output=tmp_path / "combined.parquet", expected_baseline_sha256=forward.sha256(tmp_path / "old.parquet"),
                prefix_end="2026-10-07", suffix_end="2026-10-08", source_manifest=tmp_path / "source.json", version_id="test")


def test_prefix_keeps_null_floatbits_and_unequal_duplicate_occurrences(tmp_path):
    kwargs = inputs(tmp_path)
    result = forward.compose(**kwargs)
    assert result["legacy_duplicate_occurrences_preserved"] == 1
    assert result["suffix_rows"] == 2
    assert result["original_whole_panel_invariance_pass"] is None
    assert forward.sha256(kwargs["baseline"]) == kwargs["expected_baseline_sha256"]
    with pytest.raises(ValueError, match="already exists"):
        forward.compose(**kwargs)


def test_duplicate_suffix_is_rejected_and_attempt_preserved(tmp_path):
    with pytest.raises(ValueError, match="suffix duplicate"):
        forward.compose(**inputs(tmp_path, duplicate_suffix=True))
    assert (tmp_path / "combined.parquet.tmp").exists()
    assert not (tmp_path / "combined.parquet").exists()


def test_changed_baseline_is_not_admitted(tmp_path):
    kwargs = inputs(tmp_path)
    kwargs["expected_baseline_sha256"] = "0"*64
    with pytest.raises(ValueError, match="binding changed"):
        forward.compose(**kwargs)
