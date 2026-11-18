"""Synthetic native-schema fixtures; no downloads or claims about source availability."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.capabilities.evaluator import _evaluate_capability
from open_composer.capabilities.registry import load_registry
from open_composer.models.capability import Capability


def capability(shape: str, fixture: str) -> Capability:
    return Capability(
        id="market.native_test",
        kind="market",
        data_shape=shape,
        status="trial",
        provider="synthetic_offline_fixture",
        reliability="unknown",
        default_mode="offline",
        strict_behavior="research_only",
        paper_ready_timeframes=[],
        fixture=fixture,
        min_score=1.0,
        caveats=["Synthetic schema test only; no historical PIT or paper evidence"],
    )


def test_registered_native_shapes_keep_research_restrictions():
    registry = load_registry(Path(__file__).resolve().parents[1])
    expected = {
        "market.retained_strategy_operating_nav_units": "saved_operating_nav_receipt_v1",
        "market.dm_author_deciles": "dm_author_decile_archive_v1",
        "market.french_ff3_monthly_current_vintage": "ff3_monthly_decimal_v1",
        "market.french_ff3_annual_archives": "ff3_monthly_decimal_v1",
    }
    for item in registry.capabilities:
        if item.id in expected:
            assert item.data_shape == expected[item.id]
            assert item.status == "trial"
            assert item.strict_behavior == "research_only"
            assert item.paper_ready_timeframes == []
            assert item.caveats


def ff3(path: Path) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "month": ["202401", "202402", "202403"],
            "Mkt-RF": [-0.01, 0.02, 0.005],
            "SMB": [0.002, -0.003, 0],
            "HML": [-0.001, 0.002, 0],
            "RF": [0.001, 0.001, 0.001],
        }
    )
    frame.to_csv(path, index=False)
    return frame


def test_ff3_keeps_negative_decimal_returns_without_invented_ohlcv(tmp_path: Path):
    path = tmp_path / "factors.csv"
    ff3(path)
    item = capability("ff3_monthly_decimal_v1", path.name)
    before = item.model_dump()
    result = _evaluate_capability(tmp_path, item)
    assert result.passed and result.records == 3 and result.score == 1
    assert "no historical PIT" in result.issues[0]
    assert item.model_dump() == before


@pytest.mark.parametrize("defect", ["duplicate", "order", "month", "nonfinite", "columns"])
def test_ff3_rejects_invalid_calendar_factors_and_schema(tmp_path: Path, defect):
    path = tmp_path / "factors.csv"
    frame = ff3(path)
    if defect == "duplicate":
        frame.loc[1, "month"] = frame.loc[0, "month"]
    elif defect == "order":
        frame = frame.iloc[::-1]
    elif defect == "month":
        frame.loc[1, "month"] = "202413"
    elif defect == "nonfinite":
        frame.loc[1, "RF"] = np.nan
    else:
        frame = frame.rename(columns={"SMB": "SMB_FF5"})
    frame.to_csv(path, index=False)
    result = _evaluate_capability(tmp_path, capability("ff3_monthly_decimal_v1", path.name))
    assert not result.passed and result.records == 0 and result.score == 0


def author_archive(path: Path, defect: str | None = None):
    with tarfile.open(path, "w:gz") as archive:
        for name, dates in (
            ("txt/d_m_pt_tot.txt", ["20240102", "20240103"]),
            ("txt/m_m_pt_tot.txt", ["20240131", "20240229"]),
        ):
            if defect == "missing" and name.startswith("txt/m_"):
                continue
            rows = [
                f"{date} {decile} {-0.005 + decile * 0.001} 1000 50\n"
                for date in dates
                for decile in range(1, 11)
            ]
            if defect == "decile":
                rows.pop()
            if defect == "sentinel":
                rows[0] = rows[0].replace("-0.004", "-999")
            payload = "".join(rows).encode()
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            if defect == "symlink":
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                archive.addfile(member)
            else:
                archive.addfile(member, io.BytesIO(payload))


def test_author_archive_validates_actual_daily_and_monthly_decile_rows(tmp_path: Path):
    path = tmp_path / "author.tar.gz"
    author_archive(path)
    before = path.read_bytes()
    result = _evaluate_capability(tmp_path, capability("dm_author_decile_archive_v1", path.name))
    assert result.passed and result.records == 40
    assert path.read_bytes() == before
    assert not (tmp_path / "txt").exists()  # Inspect streams, never extract an archive.


@pytest.mark.parametrize("defect", ["missing", "decile", "sentinel", "symlink"])
def test_author_archive_rejects_incomplete_sentinel_and_nonfile_members(tmp_path: Path, defect):
    path = tmp_path / "author.tar.gz"
    author_archive(path, defect)
    result = _evaluate_capability(tmp_path, capability("dm_author_decile_archive_v1", path.name))
    assert not result.passed and result.records == 0


def bind(path: Path, root: Path) -> dict:
    return {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def nav_fixture(root: Path, *, broken_bridge: bool = False):
    source = root / "source.json"
    source.write_text('{"synthetic_source": true}\n')
    dates = np.array(["2024-01-02", "2024-01-03", "2024-01-04"])
    prices = np.broadcast_to(np.array([100, 101, 100.5, 102])[:, None], (4, 6)).copy()
    net = prices[1:] / prices[:-1] - 1
    inner = np.full((3, 6), 0.001)
    arrays = root / "received.npz"
    np.savez(
        arrays,
        dates=dates,
        prices_10=prices,
        prices_20=prices,
        inner_10=inner,
        inner_20=inner,
        returns_10=net,
        gross_10=net + inner + (0.01 if broken_bridge else 0),
        gross_20=net + inner,
    )
    view = {
        "source_dates": 3,
        "source_rows_exactly_aligned": True,
        "positive_finite_NAV": True,
        "source_gross_inner_NAV_bridge": True,
        "EOF_held_source_marks_present": True,
    }
    receipt = {
        "names": ["S1", "S2", "S3", "C2", "BASE", "H5"],
        "sessions": 3,
        "dates": [dates[0], dates[-1]],
        "fit_calls": 0,
        "financial_calls": 0,
        "source_strategy_replayed": False,
        "exact_exchange_calendar": True,
        "first_dynamic_index": 1,
        "past_source_rows_at_first_dynamic": 1,
        "source_views": {"10": view, "20": view},
        "input_bindings": bind(source, root),
        "received_arrays": bind(arrays, root),
    }
    path = root / "receipt.json"
    path.write_text(json.dumps(receipt))
    return path, receipt


def test_nav_receipt_verifies_retained_bytes_shapes_and_cost_bridge(tmp_path: Path):
    path, _ = nav_fixture(tmp_path)
    result = _evaluate_capability(tmp_path, capability("saved_operating_nav_receipt_v1", path.name))
    assert result.passed and result.records == 3
    assert "physical fills or paper-readiness" in result.issues[0]


@pytest.mark.parametrize("defect", ["binding", "bridge", "traversal", "replay", "inventory"])
def test_nav_receipt_rejects_bad_identity_bridge_scope_and_inventory(tmp_path: Path, defect):
    path, receipt = nav_fixture(tmp_path, broken_bridge=defect == "bridge")
    if defect == "binding":
        receipt["received_arrays"]["sha256"] = "0" * 64
    elif defect == "traversal":
        receipt["input_bindings"]["path"] = "../outside"
    elif defect == "replay":
        receipt["source_strategy_replayed"] = True
    elif defect == "inventory":
        receipt["names"][-1] = "INVENTED"
    path.write_text(json.dumps(receipt))
    result = _evaluate_capability(tmp_path, capability("saved_operating_nav_receipt_v1", path.name))
    assert not result.passed and result.records == 0
