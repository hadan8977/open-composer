"""Recovery must preserve feature values and reject stale/corrupted checkpoints."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from open_composer.research.features.alpha158 import compute_alpha158
from scripts import build_alpha158_features as builder


def _bars() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2025-01-02", periods=85)
    result = []
    for symbol in ["AAA", "BBB", "CCC"]:
        close = 100 + rng.normal(size=len(dates)).cumsum()
        result.append(
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "trade_date": dates,
                    "open": close * 0.99,
                    "high": close * 1.02,
                    "low": close * 0.98,
                    "close": close,
                    "volume": rng.integers(100, 10000, size=len(dates)).astype(float),
                }
            )
        )
    return pd.concat(result, ignore_index=True)


def test_streamed_features_match_old_concat_sort_exactly(tmp_path, monkeypatch):
    bars = _bars()
    frames = [compute_alpha158(group) for _, group in bars.groupby("symbol")]
    frames.append(frames[0].iloc[:0])
    paths = []
    for index, frame in enumerate(reversed(frames)):
        path = tmp_path / f"batch-{index}.parquet"
        frame.to_parquet(path, index=False)
        paths.append(path)
    expected = pd.concat(frames, ignore_index=True).sort_values(["symbol", "trade_date"])
    read_parquet = pd.read_parquet
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: pytest.fail("materialized a batch"))
    out_path = tmp_path / "out.parquet"
    assert builder._consolidate_batches(
        paths, out_path, memory_limit="64MB", temp_directory=tmp_path / "spill"
    ) == len(expected)
    pd.testing.assert_frame_equal(read_parquet(out_path), expected, check_exact=True)


def test_duplicate_keys_do_not_replace_prior_output(tmp_path):
    frame = compute_alpha158(_bars()).iloc[:5]
    batch = tmp_path / "batch.parquet"
    frame.to_parquet(batch, index=False)
    output = tmp_path / "out.parquet"
    output.write_bytes(b"prior output")
    with pytest.raises(ValueError, match="duplicate"):
        builder._consolidate_batches(
            [batch, batch], output, memory_limit="64MB", temp_directory=tmp_path / "spill"
        )
    assert output.read_bytes() == b"prior output"


def test_checkpoint_identity_and_corruption_are_not_silently_reused(tmp_path):
    path = tmp_path / "batch.parquet"
    frame = pd.DataFrame({"symbol": ["AAA"]})
    frame.to_parquet(path)
    assert not builder._checkpoint_valid(path, "identity", ["AAA"])
    builder._write_checkpoint(frame, path, "identity", ["AAA"])
    assert builder._checkpoint_valid(path, "identity", ["AAA"])
    with pytest.raises(ValueError, match="identity mismatch"):
        builder._checkpoint_valid(path, "changed", ["AAA"])
    with pytest.raises(ValueError, match="identity mismatch"):
        builder._checkpoint_valid(path, "identity", ["BBB"])
    with path.open("ab") as handle:
        handle.write(b"corruption")
    with pytest.raises(ValueError, match="checksum mismatch"):
        builder._checkpoint_valid(path, "identity", ["AAA"])


def test_identity_binds_source_bytes_universe_and_batch_size(tmp_path):
    source = tmp_path / "bars.parquet"
    source.write_bytes(b"old source")
    stat = source.stat()
    baseline = builder._build_identity(2025, ["AAA"], 100, [source])
    assert baseline != builder._build_identity(2025, ["BBB"], 100, [source])
    assert baseline != builder._build_identity(2025, ["AAA"], 50, [source])
    source.write_bytes(b"new source")
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert baseline != builder._build_identity(2025, ["AAA"], 100, [source])


def test_interrupted_build_resumes_completed_batch_without_reading_frames(tmp_path, monkeypatch):
    daily = tmp_path / "daily"
    (daily / "2025").mkdir(parents=True)
    _bars().rename(columns={"trade_date": "timestamp"}).to_parquet(
        daily / "2025" / "bars.parquet", index=False
    )
    output = tmp_path / "features"
    legacy = output / "_scratch" / "2025" / "batch-000.parquet"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"unbound legacy data must be preserved")
    monkeypatch.setattr(builder, "DAILY_ROOT", daily)
    monkeypatch.setattr(builder, "DUCKDB_TMP", tmp_path / "spill")
    monkeypatch.setattr(builder, "universe_union_symbols", lambda _: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(
        "sys.argv",
        ["builder", "--years", "2025", "--out-dir", str(output), "--symbol-batch-size", "1"],
    )
    actual_builder = builder.build_alpha158_features
    calls = []

    def interrupted(*args, **kwargs):
        calls.append(args[1])
        if len(calls) == 2:
            raise RuntimeError("simulated termination")
        return actual_builder(*args, **kwargs)

    monkeypatch.setattr(builder, "build_alpha158_features", interrupted)
    with pytest.raises(RuntimeError, match="simulated termination"):
        builder.main()
    assert not (output / "2025.complete.json").exists()
    calls.clear()

    def resumed(*args, **kwargs):
        calls.append(args[1])
        return actual_builder(*args, **kwargs)

    monkeypatch.setattr(builder, "build_alpha158_features", resumed)
    read_parquet = pd.read_parquet
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: pytest.fail("read whole checkpoint"))
    assert builder.main() == 0
    assert calls == [["BBB"], ["CCC"]]
    assert legacy.read_bytes() == b"unbound legacy data must be preserved"
    pd.testing.assert_frame_equal(
        read_parquet(output / "2025.parquet"),
        actual_builder(str(daily / "2025" / "*.parquet"), ["AAA", "BBB", "CCC"]),
        check_exact=True,
    )
    assert (output / "2025.complete.json").exists()
    calls.clear()
    assert builder.main() == 0
    assert not calls


@pytest.mark.parametrize("size", ["0", "101", "-1"])
def test_rejects_batches_outside_resource_contract(size, monkeypatch):
    monkeypatch.setattr("sys.argv", ["builder", "--symbol-batch-size", size])
    with pytest.raises(SystemExit) as error:
        builder.main()
    assert error.value.code == 2
