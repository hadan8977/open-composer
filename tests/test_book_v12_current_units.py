"""Affected recovery checks: original units/formulas, closed calendar, source reuse."""

import json
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from open_composer.research.features.daily_features import build_daily_features
from scripts import build_book_v12_current_units as units
from scripts import refresh_book_v12_current_units as refresh


@pytest.mark.parametrize(
    "stamp,decision,execution",
    [
        ("2026-11-03T00:30:00+00:00", "2026-11-02", "2026-11-03"),
        ("2026-11-02T00:30:00+00:00", "2026-10-30", "2026-11-02"),
        ("2026-11-27T06:30:00+00:00", "2026-11-25", "2026-11-27"),
        ("2026-03-09T00:30:00+00:00", "2026-03-06", "2026-03-09"),
    ],
)
def test_utc_execution_date_across_ny_evening_weekend_dst_holiday(stamp, decision, execution):
    assert refresh.clock(datetime.fromisoformat(stamp)) == (
        date.fromisoformat(decision),
        date.fromisoformat(execution),
    )


@pytest.mark.parametrize(
    "stamp", ["2026-11-01T00:30:00+00:00", "2026-11-26T06:30:00+00:00", "2026-07-03T06:30:00+00:00"]
)
def test_non_execution_session_refused(stamp):
    with pytest.raises(ValueError, match="UTC run day"):
        refresh.clock(datetime.fromisoformat(stamp))


@pytest.mark.parametrize("symbol", ["CQP", "SCCO"])
def test_known_action_bad_correct_and_unknown_source_states(symbol):
    spec = units.KNOWN_ACTIONS[symbol]
    raw = spec["raw_close"]
    bad = np.prod([1 - rate / raw for rate in spec["vendor_cash"]])
    good = (1 - spec["cash"] / raw) / spec["shares"]
    assert (
        units.known_action_state(
            symbol, raw, raw, 10000, round(raw * bad, 2), round(raw * bad, 2), 10000
        )["classification"]
        == "vendor_known_misadjustment"
    )
    assert (
        units.known_action_state(
            symbol,
            raw,
            raw,
            10000,
            round(raw * good, 2),
            round(raw * good, 2),
            np.floor(10000 * spec["shares"]),
        )["classification"]
        == "vendor_already_correct"
    )
    with pytest.raises(ValueError):
        units.known_action_state(symbol, raw, raw, 10000, raw * 1.1, raw * 1.1, 10000)


def test_private_action_transform_stops_at_execution_date_and_keeps_other_names():
    frame = pd.DataFrame(
        {
            "symbol": ["SCCO", "SCCO", "OTHER"],
            "timestamp": pd.to_datetime(["2026-11-02", "2026-11-03", "2026-11-02"], utc=True),
            "open": [177.06, 176.19, 20.0],
            "high": [180.0, 180.0, 21.0],
            "low": [175.0, 175.0, 19.0],
            "close": [177.06, 176.19, 20.0],
            "volume": [1531181.0, 100.0, 200.0],
        }
    )
    result, mask, residual = units.transform_known_action(frame, "SCCO", 0.9951181529604152, 1.0106)
    pd.testing.assert_frame_equal(result.loc[~mask], frame.loc[~mask], check_exact=True)
    assert residual < 1
    assert result.iloc[0].close == frame.iloc[0].close * 0.9951181529604152


@pytest.mark.parametrize("symbol", ["CQP", "SCCO"])
def test_provider_corrected_metadata_requires_actual_correct_bars(symbol):
    spec = units.KNOWN_ACTIONS[symbol]
    stocks = [{"rate": 1.0106}] if symbol == "SCCO" else []
    for signature in [spec["vendor_cash"], [spec["cash"]]]:
        units.validate_known_action_signature(
            symbol, "vendor_already_correct", [{"rate": x} for x in signature], stocks
        )
    with pytest.raises(ValueError):
        units.validate_known_action_signature(
            symbol, "vendor_known_misadjustment", [{"rate": spec["cash"]}], stocks
        )
    with pytest.raises(ValueError):
        units.validate_known_action_signature(
            symbol,
            "vendor_already_correct",
            [{"rate": spec["cash"] / 2}, {"rate": spec["cash"] / 2}],
            stocks,
        )


def test_closed_new_month_member_is_added_before_target_scope(tmp_path):
    source = tmp_path / "source"
    view = tmp_path / "view"
    p = source / "data/live/equity_book/prices/2026.parquet"
    p.parent.mkdir(parents=True)
    pd.DataFrame({"symbol": ["OLD"]}).to_parquet(p, index=False)
    p = view / "data/features/universe_broad/2026.parquet"
    p.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "symbol": ["OLD", "NEW", "OUT"],
            "month_end": pd.to_datetime(["2026-09-30", "2026-10-30", "2026-10-30"]),
            "adv_rank": [100, 3999, 4001],
        }
    ).to_parquet(p, index=False)
    declared = tmp_path / "declared.json"
    declared.write_text(
        json.dumps(
            {
                "symbols": ["OLD", "NEW", "OUT", "HELD", "SPY", "SGOV", "BIL"],
                "actual_owned_symbols": ["HELD"],
            }
        )
    )
    scope = units.execution_consumer_scope(view, source, declared, date(2026, 11, 2))
    assert set(scope["symbols"]) == {"OLD", "NEW", "HELD", "SPY", "SGOV", "BIL"}
    assert scope["outside_execution_scope"] == ["OUT"]


def _source(root, frame):
    path = root / "data/sip/daily/2016/shard.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    meta = {
        "source_bindings": [
            {
                "path": str(path.relative_to(root)),
                "source": str(path),
                "sha256": units.digest(path),
                "bytes": path.stat().st_size,
            }
        ]
    }
    (root / "current-units-source.json").write_text(json.dumps(meta))
    (root / "current-units-known-actions-repair.json").write_text('{"repairs":[]}')
    return path


def _fixture(tmp_path):
    view = tmp_path / "view"
    new = tmp_path / "next"
    days = pd.bdate_range("2016-01-04", periods=32, tz="UTC")
    frames = []
    for symbol, level in [("A", 10.0), ("B", 20.0), ("SPY", 200.0)]:
        frames.append(
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "timestamp": days,
                    "open": level,
                    "high": level,
                    "low": level,
                    "close": level,
                    "volume": 1000.0,
                    "trade_count": 10.0,
                }
            )
        )
    raw = pd.concat(frames, ignore_index=True)
    raw.loc[(raw.symbol == "A") & (raw.timestamp == days[12]), ["volume", "trade_count"]] = [
        0.0,
        1.0,
    ]
    old = _source(view, raw)
    declared = tmp_path / "old-declared.json"
    declared.write_text(json.dumps({"symbols": ["A", "B", "SPY"], "declared_at": "old"}))
    dest = view / "data/features/daily_broad/2016.parquet"
    dest.parent.mkdir(parents=True)
    allcols = tmp_path / "full.parquet"
    build_daily_features(
        [str(old)],
        ["A", "B", "SPY"],
        output_year=2016,
        output_parquet=allcols,
        memory_limit="100MB",
        threads=1,
    )
    pd.read_parquet(allcols, columns=units.DAILY_COLUMNS).to_parquet(dest, index=False)
    receipt = {
        "binding": units.daily_binding(view, declared, 2016),
        "output_sha256": units.digest(dest),
    }
    dest.with_suffix(".receipt.json").write_text(json.dumps(receipt))
    return view, new, declared, raw, dest


def test_timestamp_context_relocation_reuses_completed_numeric_year(tmp_path, monkeypatch):
    view, new, old_names, raw, dest = _fixture(tmp_path)
    _source(new, raw)
    names = tmp_path / "new-declared.json"
    names.write_text(json.dumps({"symbols": ["A", "B", "SPY"], "declared_at": "tomorrow"}))
    before = units.digest(dest)

    def refused(*args, **kwargs):
        raise AssertionError("unchanged semantic inputs must reuse original completed numbers")

    monkeypatch.setattr(
        "open_composer.research.features.daily_features.build_daily_features", refused
    )
    result = units.incremental_daily(view, new, names, old_names, date(2016, 12, 31))
    assert result[0]["reused_without_recomputation"]
    assert units.digest(dest) == before


def test_trade_count_only_ghost_revision_matches_unchanged_native_formula(tmp_path):
    view, new, names, raw, dest = _fixture(tmp_path)
    previous = pd.read_parquet(dest)
    raw.loc[(raw.symbol == "A") & (raw.volume == 0), "trade_count"] = 0.0
    fresh = _source(new, raw)
    full = tmp_path / "expected.parquet"
    build_daily_features(
        [str(fresh)],
        ["A", "B", "SPY"],
        output_year=2016,
        output_parquet=full,
        memory_limit="100MB",
        threads=1,
    )
    result = units.incremental_daily(view, new, names, names, date(2016, 12, 31))
    assert result[0]["actual_changed_input_symbols"] == ["A"]
    actual = pd.read_parquet(dest).sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    expected = (
        pd.read_parquet(full, columns=units.DAILY_COLUMNS)
        .sort_values(["symbol", "trade_date"])
        .reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
    pd.testing.assert_frame_equal(
        previous.loc[previous.symbol == "B"].reset_index(drop=True),
        actual.loc[actual.symbol == "B"].reset_index(drop=True),
        check_exact=True,
    )


def test_prepare_only_does_not_touch_pointer_or_working_view(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    pointer = tmp_path / "pointer.json"
    pointer.write_text(json.dumps({"view_root": str(tmp_path / "accepted"), "status": "ready"}))
    original = pointer.read_bytes()
    monkeypatch.setattr(refresh, "clock", lambda: (date(2026, 11, 2), date(2026, 11, 3)))
    monkeypatch.setattr(refresh.original, "FileLock", lambda _: nullcontext())
    monkeypatch.setattr(refresh.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(refresh.archive, "_read_pending", lambda _: {})
    monkeypatch.setattr(refresh.archive, "_exclusive_lock", lambda _: nullcontext())
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setattr("forward_refresh_io.disk_admission", lambda *a, **kw: {"admitted": True})
    writes = []

    def record(path, obj):
        assert path != pointer and not path.is_relative_to(tmp_path / "accepted")
        writes.append(path)

    monkeypatch.setattr(refresh, "atomic_json", record)
    args = SimpleNamespace(
        equity_basis=300000,
        source_root=tmp_path,
        input_pointer=pointer,
        check_ready=False,
        prepare_only=True,
        view_parent=tmp_path / "runtime",
    )
    refresh.run(args)
    assert pointer.read_bytes() == original
    assert not (tmp_path / "accepted").exists()
    assert writes == [tmp_path / "runtime/latest-source-resource.json"]


def test_source_fetch_charge_preserves_default_terms_and_service_reserve(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import forward_refresh_io as io

    monkeypatch.setattr(
        io.os, "statvfs", lambda _: SimpleNamespace(f_bavail=4 * 1024**3, f_frsize=1)
    )
    config = {"version_directory": "admission", "disk_spill_bound_bytes": 0}
    base = io.disk_admission(
        tmp_path,
        dict(config),
        source_root=tmp_path,
        tables=[],
        live=tmp_path,
        stages=[],
        year=2026,
        fetch=False,
    )
    source = io.disk_admission(
        tmp_path,
        dict(config),
        source_root=tmp_path,
        tables=[],
        live=tmp_path,
        stages=[],
        year=2026,
        fetch=True,
        source_fetch_bound_bytes=2 * 1024**3,
    )
    assert base["terms"]["source_fetch_bytes"] == 0
    assert source["terms"]["source_fetch_bytes"] == 2 * 1024**3
    assert source["terms"]["service_disk_reserve_bytes"] == 512 * 1024**2
    assert source["required_available_bytes"] - base["required_available_bytes"] == 2 * 1024**3
    assert source["admitted"]


def test_pending_read_and_exact_drain_are_locked_and_preserve_new_obligations(
    tmp_path, monkeypatch
):
    from contextlib import contextmanager

    locked = False
    reads = 0
    written = []

    @contextmanager
    def lock(_):
        nonlocal locked
        locked = True
        yield
        locked = False

    def read(_):
        nonlocal reads
        assert locked
        reads += 1
        return {"A": 0.1} if reads == 1 else {"A": 0.2, "B": 0.3}

    monkeypatch.setattr(refresh.archive, "_exclusive_lock", lock)
    monkeypatch.setattr(refresh.archive, "_read_pending", read)
    monkeypatch.setattr(refresh.archive, "_clients", lambda: (None, object()))
    monkeypatch.setattr(refresh.archive, "rewrite_full_history", lambda *a, **kw: [{"symbol": "A"}])
    monkeypatch.setattr(refresh.archive, "_write_pending", lambda _, p, **kw: written.append(p))
    refresh.finish_pending_source(tmp_path)
    assert written == [{"A": 0.2, "B": 0.3}]


def test_native_code_root_data_rebase_and_canonical_zip_are_separate(tmp_path, monkeypatch):
    native = tmp_path / "code"
    view = tmp_path / "view"
    cache = tmp_path / "cache"
    path = native / "scripts/build_sec_xbrl_fundamentals.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "from pathlib import Path\nimport os\nROOT=Path(__file__).resolve().parents[1]\n"
        "DEFAULT_DIR=Path(os.environ['OC_EQUITY_BOOK_DIR'])\nPANEL=DEFAULT_DIR/'panel'\n"
        "FACTS=ROOT/'data/features/facts.parquet'\n"
        "ZIP_PATH=ROOT/'data/raw/sec_xbrl/companyfacts.zip'\n"
    )
    view.mkdir()
    monkeypatch.setenv("OC_BOOK_NATIVE_CODE_ROOT", str(native))
    monkeypatch.setenv("OC_BOOK_SOURCE_CACHE_ROOT", str(cache))
    module = units.load_native(view, "build_sec_xbrl_fundamentals")
    assert module.PANEL == view / "data/live/equity_book/panel"
    assert module.FACTS == view / "data/features/facts.parquet"
    assert module.ZIP_PATH == cache / "data/raw/sec_xbrl/companyfacts.zip"
    receipt = json.loads((view / "native-code-execution.jsonl").read_text())
    assert receipt["actual_path"] == str(path)
    assert receipt["sha256"] == units.digest(path)
