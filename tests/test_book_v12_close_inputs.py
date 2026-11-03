"""Only the new physical-price source and its original snapshot-window interface."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from scripts import build_book_prices_file as prices
from scripts import collect_book_v12_close_inputs as receive


@pytest.mark.parametrize("day", [date(2026, 11, 3), date(2026, 7, 2), date(2026, 11, 27)])
def test_request_window_exactly_matches_original_ten_minute_fallback(day):
    start, end = receive.source_windows(day)["minute"]
    assert end == prices.snapshot_time_utc(day)
    assert end - start == timedelta(minutes=prices.SNAPSHOT_FALLBACK_MINUTES + 1)


def test_raw_filter_keeps_original_schema_ghost_semantics_and_excludes_cut():
    cut = datetime(2026, 11, 3, 20, 45, tzinfo=UTC)
    frame = pd.DataFrame(
        {
            "symbol": ["A", "GHOST", "REAL_ZERO", "AT_CUT"],
            "timestamp": [cut - timedelta(minutes=1)] * 3 + [cut],
            "open": [10.0, 10.0, 10.0, 10.0],
            "high": [10.0, 10.0, 11.0, 10.0],
            "low": [10.0, 10.0, 10.0, 10.0],
            "close": [10.0, 10.0, 11.0, 10.0],
            "volume": [100.0, 0.0, 0.0, 100.0],
            "trade_count": [10.0, 0.0, 0.0, 10.0],
        }
    )
    kept = receive.real_source_rows(frame, cut - timedelta(minutes=11), cut)
    assert kept.symbol.tolist() == ["A", "REAL_ZERO"]


def test_bound_raw_receipt_labels_actual_physical_prices_and_refuses_changed_file(tmp_path):
    day = date(2026, 11, 3)
    daily = tmp_path / "daily/2026/11/shard-2026-11-03.parquet"
    minute = tmp_path / "minute/2026/11/shard-2026-11-03.parquet"
    for path, stamp in [
        (daily, datetime(2026, 11, 3, 5, tzinfo=UTC)),
        (minute, datetime(2026, 11, 3, 20, 44, tzinfo=UTC)),
    ]:
        path.parent.mkdir(parents=True)
        pd.DataFrame({"symbol": ["SCCO"], "timestamp": [stamp], "close": [176.19]}).to_parquet(
            path, index=False
        )
    (tmp_path / "price-basis.json").write_text(
        json.dumps({"schema_version": 1, "feed": "sip", "adjustment": "raw"})
    )
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    receipt = {
        "execution_date": str(day),
        "feed": "sip",
        "adjustment": "raw",
        "outputs": [
            {
                "path": str(p.relative_to(tmp_path)),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in [daily, minute]
        ],
    }
    (receipts / f"{day}.json").write_text(json.dumps(receipt))
    result = prices.build_prices(day, ["SCCO"], sip_root=tmp_path)
    assert "adjustment=raw" in result["price_basis"]
    assert result["official_close"] == {"SCCO": 176.19}
    assert result["snapshot_1545"] == {"SCCO": 176.19}
    pd.DataFrame(
        {
            "symbol": ["SCCO"],
            "timestamp": [datetime(2026, 11, 3, 20, 44, tzinfo=UTC)],
            "close": [99.0],
        }
    ).to_parquet(minute, index=False)
    with pytest.raises(prices.InputsError, match="changed"):
        prices.build_prices(day, ["SCCO"], sip_root=tmp_path)


def test_missing_raw_receipt_cannot_fall_back_to_all_label(tmp_path):
    (tmp_path / "price-basis.json").write_text(
        json.dumps({"schema_version": 1, "feed": "sip", "adjustment": "raw"})
    )
    with pytest.raises(prices.InputsError, match="missing"):
        prices.source_price_basis(tmp_path, date(2026, 11, 3), [])
