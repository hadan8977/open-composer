from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from open_composer.adapters.data.cboe_volatility import (
    VIX3M_HISTORY_URL,
    VIX_HISTORY_URL,
    build_cboe_volatility_packets,
    collect_cboe_volatility_snapshot,
    load_cboe_volatility_snapshot,
)

VIX_CSV = b"""DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2026,15,16,14,15.5\n01/05/2026,16,17,15,16.5\n"""
VIX3M_CSV = b"""DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2026,18,19,17,18.5\n01/05/2026,19,20,18,19.5\n"""


def test_packets_use_next_equity_open_and_preserve_real_fetch_time() -> None:
    fetched_at = datetime(2026, 1, 6, 16, tzinfo=UTC)

    packets = build_cboe_volatility_packets(
        VIX_CSV,
        VIX3M_CSV,
        fetched_at=fetched_at,
    )

    friday = packets[0]
    assert friday.observation_date.isoformat() == "2026-01-02"
    assert friday.published_at == datetime(2026, 1, 2, 21, 15, tzinfo=UTC)
    assert friday.visible_at == datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    assert friday.fetched_at == fetched_at
    assert friday.fetched_at_is_historical_first_seen is False
    assert friday.prompt_hash is None
    assert friday.vix_to_vix3m_ratio == pytest.approx(15.5 / 18.5)


def test_snapshot_is_immutable_and_hash_checked(tmp_path: Path) -> None:
    payloads = {VIX_HISTORY_URL: VIX_CSV, VIX3M_HISTORY_URL: VIX3M_CSV}
    output = tmp_path / "snapshot"

    manifest_path = collect_cboe_volatility_snapshot(
        output,
        fetch_bytes=payloads.__getitem__,
        fetched_at=datetime(2026, 1, 6, 16, tzinfo=UTC),
    )

    frame = load_cboe_volatility_snapshot(manifest_path)
    assert len(frame) == 2
    assert frame["visible_at"].dtype == pd.DatetimeTZDtype(tz="UTC")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["historical_first_seen_claim"] is False
    assert manifest["latest_usable_observation_date"] == "2026-01-05"
    with pytest.raises(ValueError, match="already exists"):
        collect_cboe_volatility_snapshot(
            output,
            fetch_bytes=payloads.__getitem__,
            fetched_at=datetime(2026, 1, 6, 16, tzinfo=UTC),
        )

    normalized = output / "cboe-volatility-daily.csv"
    normalized.write_text(normalized.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_cboe_volatility_snapshot(manifest_path)


def test_duplicate_date_and_invalid_ohlc_fail_closed() -> None:
    duplicate = VIX_CSV + b"01/05/2026,16,17,15,16.5\n"
    with pytest.raises(ValueError, match="duplicate date"):
        build_cboe_volatility_packets(
            duplicate,
            VIX3M_CSV,
            fetched_at=datetime(2026, 8, 14, tzinfo=UTC),
        )

    invalid = b"DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2026,15,14,13,15.5\n"
    with pytest.raises(ValueError, match="high is below"):
        build_cboe_volatility_packets(
            invalid,
            b"DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2026,18,19,17,18.5\n",
            fetched_at=datetime(2026, 8, 14, tzinfo=UTC),
        )


def test_missing_pair_on_equity_session_fails_closed() -> None:
    missing_leg = VIX_CSV + b"01/06/2026,17,18,16,17.5\n"

    with pytest.raises(ValueError, match="missing paired equity-session rows"):
        build_cboe_volatility_packets(
            missing_leg,
            VIX3M_CSV,
            fetched_at=datetime(2026, 1, 7, tzinfo=UTC),
        )
