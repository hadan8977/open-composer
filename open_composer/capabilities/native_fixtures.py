"""Strict offline validation for retained research inputs that are not OHLCV bars.

Passing proves the declared local schema/retained-byte checks only. Historical
availability, source completeness, costs and paper readiness need task reception.
"""

from __future__ import annotations

import hashlib
import json
import re
import tarfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

NATIVE_MARKET_SHAPES = {
    "saved_operating_nav_receipt_v1",
    "dm_author_decile_archive_v1",
    "ff3_monthly_decimal_v1",
}


def evaluate_native_market_fixture(root: Path, path: Path, shape: str):
    """Return the existing evaluator tuple; malformed inputs fail as one whole fixture."""
    try:
        if shape == "saved_operating_nav_receipt_v1":
            records = _operating_nav(root, path)
        elif shape == "dm_author_decile_archive_v1":
            records = _author_deciles(path)
        elif shape == "ff3_monthly_decimal_v1":
            records = _monthly_ff3(path)
        else:
            raise ValueError(f"unsupported native market shape: {shape}")
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        EOFError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as exc:
        return 0, [0.0], [f"native fixture validation failed: {exc}"]
    return (
        records,
        [1.0],
        [
            f"Offline {shape} schema/retained-byte validation only; "
            "no historical PIT, executable bars, physical fills or paper-readiness certification."
        ],
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _bound_path(root: Path, binding: dict) -> Path:
    """Read only an existing repository-relative binding; no fetch or deserialization hooks."""
    name = binding["path"]
    _require(
        isinstance(name, str) and not Path(name).is_absolute(), "binding path must be relative"
    )
    # Retained files may resolve through the repository's read-only archive symlinks.
    # Reject lexical traversal while allowing those already installed archive bindings.
    _require(".." not in Path(name).parts, "binding path traversal")
    path = root / name
    _require(path.is_file(), f"missing retained binding: {name}")
    _require(type(binding["bytes"]) is int, "binding byte count must be an integer")
    _require(path.stat().st_size == binding["bytes"], f"retained byte count differs: {name}")
    digest = binding["sha256"]
    _require(
        isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
        "binding needs a SHA256 identity",
    )
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    _require(actual == digest, f"retained SHA256 differs: {name}")
    return path


def _operating_nav(root: Path, path: Path) -> int:
    receipt = json.loads(path.read_text())
    names = receipt["names"]
    _require(names == ["S1", "S2", "S3", "C2", "BASE", "H5"], "retained source inventory differs")
    sessions = receipt["sessions"]
    _require(type(sessions) is int and sessions > 1, "invalid receipt session count")
    _require(
        receipt["fit_calls"] == 0 and receipt["financial_calls"] == 0,
        "receipt is not an input-only reception",
    )
    _require(receipt["source_strategy_replayed"] is False, "receipt reports a source replay")
    _require(receipt["exact_exchange_calendar"] is True, "receipt lacks its calendar attestation")
    first = receipt["first_dynamic_index"]
    _require(type(first) is int and 0 < first < sessions, "invalid first dynamic index")
    _require(receipt["past_source_rows_at_first_dynamic"] == first, "history count differs")
    views = receipt["source_views"]
    _require(set(views) == {"10", "20"}, "retained cost-view inventory differs")
    _bound_path(root, receipt["input_bindings"])
    arrays = _bound_path(root, receipt["received_arrays"])
    with np.load(arrays, allow_pickle=False) as data:
        dates = pd.DatetimeIndex(pd.to_datetime(data["dates"], format="%Y-%m-%d", errors="raise"))
        _require(
            len(dates) == sessions and dates.is_monotonic_increasing and dates.is_unique,
            "retained session calendar differs",
        )
        _require(
            receipt["dates"] == [str(dates[0].date()), str(dates[-1].date())],
            "receipt date bounds differ",
        )
        for cost, view in views.items():
            _require(view["source_dates"] == sessions, "cost-view session count differs")
            for key in (
                "source_rows_exactly_aligned",
                "positive_finite_NAV",
                "source_gross_inner_NAV_bridge",
                "EOF_held_source_marks_present",
            ):
                _require(view[key] is True, f"receipt does not attest {key}")
            prices, inner, gross = (data[f"{key}_{cost}"] for key in ("prices", "inner", "gross"))
            _require(prices.shape == (sessions + 1, len(names)), "NAV matrix shape differs")
            _require(inner.shape == gross.shape == (sessions, len(names)), "bridge shape differs")
            _require(
                np.isfinite(prices).all() and (prices > 0).all(), "NAV must be positive finite"
            )
            _require(np.isfinite(inner).all() and (inner >= -1e-10).all(), "invalid inner costs")
            net = prices[1:] / prices[:-1] - 1
            _require(
                np.isfinite(gross).all() and np.allclose(gross, net + inner, atol=1e-10, rtol=0),
                "saved gross/net/inner-cost bridge differs",
            )
            if cost == "10":
                _require(
                    data["returns_10"].shape == net.shape
                    and np.allclose(data["returns_10"], net, atol=1e-10, rtol=0),
                    "saved primary net-return bridge differs",
                )
    return sessions


def _monthly_ff3(path: Path) -> int:
    frame = pd.read_csv(path, dtype={"month": str})
    columns = ["month", "Mkt-RF", "SMB", "HML", "RF"]
    _require(list(frame.columns) == columns, "FF3 needs month and the exact four factor columns")
    _require(not frame.empty, "empty monthly FF3 fixture")
    _require(frame["month"].str.fullmatch(r"\d{6}").all(), "month must be YYYYMM")
    months = pd.DatetimeIndex(pd.to_datetime(frame["month"], format="%Y%m", errors="raise"))
    _require(
        months.is_monotonic_increasing and months.is_unique, "duplicate or unordered FF3 months"
    )
    values = frame[columns[1:]].apply(pd.to_numeric, errors="raise").to_numpy()
    _require(np.isfinite(values).all(), "nonfinite FF3 factor or RF value")
    # These are the already converted selected decimal vectors, never synthesized
    # prices or account cash accrual. Numeric magnitude cannot prove vintage/PIT.
    return len(frame)


def _author_deciles(path: Path) -> int:
    records = 0
    with tarfile.open(path, mode="r:gz") as archive:
        for member_name in ("txt/d_m_pt_tot.txt", "txt/m_m_pt_tot.txt"):
            matches = [member for member in archive.getmembers() if member.name == member_name]
            _require(
                len(matches) == 1 and matches[0].isfile(),
                f"missing/duplicate author member {member_name}",
            )
            stream = archive.extractfile(matches[0])
            _require(stream is not None, f"unreadable author member {member_name}")
            with stream:
                frame = pd.read_csv(
                    stream,
                    sep=r"\s+",
                    header=None,
                    names=["date", "decile", "return", "cap", "count"],
                    dtype={"date": str},
                )
            _require(not frame.empty, f"empty author member {member_name}")
            _require(frame["date"].str.fullmatch(r"\d{8}").all(), "author date must be YYYYMMDD")
            pd.to_datetime(frame["date"], format="%Y%m%d", errors="raise")
            numeric = frame[["decile", "return", "cap", "count"]].apply(
                pd.to_numeric, errors="raise"
            )
            _require(np.isfinite(numeric.to_numpy()).all(), "nonfinite author portfolio value")
            _require(
                (numeric["return"] > -1).all() and (numeric["return"] <= 100).all(),
                "invalid/sentinel author decimal return",
            )
            _require(
                (numeric["cap"] > 0).all()
                and (numeric["count"] > 0).all()
                and (numeric["count"] % 1 == 0).all(),
                "invalid author cap/count",
            )
            _require(frame["date"].is_monotonic_increasing, "unordered author dates")
            _require(len(frame) % 10 == 0, "incomplete author decile row")
            _require(
                np.array_equal(
                    numeric["decile"].to_numpy(), np.tile(np.arange(1, 11), len(frame) // 10)
                ),
                "author decile identity/order differs",
            )
            _require((frame.groupby("date").size() == 10).all(), "incomplete/duplicate author date")
            if member_name.startswith("txt/m_"):
                months = pd.to_datetime(
                    frame["date"].drop_duplicates(), format="%Y%m%d"
                ).dt.to_period("M")
                _require(months.is_unique, "duplicate author month")
            records += len(frame)
    return records
