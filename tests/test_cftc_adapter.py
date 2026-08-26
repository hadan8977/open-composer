from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

import pytest

from open_composer.adapters.events import cftc


def test_native_pre_row_uses_official_system_timestamps_and_hashes() -> None:
    event = cftc.records_to_cftc_events(
        [_row("2023-01-31", created_at="2023-02-24T20:30:04.153Z")],
        fetched_at=datetime(2026, 8, 13, tzinfo=UTC),
    )[0]

    expected = datetime(2023, 2, 24, 20, 30, 4, 153000, tzinfo=UTC)
    assert event.visible_at == expected
    assert event.published_at == expected
    assert event.fetched_at == expected
    assert event.first_seen_at == expected
    assert event.availability_basis == "max_socrata_created_at_updated_at"
    assert event.collector_retrieved_at == datetime(2026, 8, 13, tzinfo=UTC)
    assert event.raw["fetched_at_semantics"] == (
        "historical_replay_availability_not_local_download"
    )
    assert len(event.input_hash) == 64
    assert event.prompt_hash == cftc.CFTC_TFF_TRANSFORM_HASH
    assert event.transform_hash == cftc.CFTC_TFF_TRANSFORM_HASH


def test_legacy_pre_rows_use_two_week_lag_with_dst() -> None:
    event = cftc.records_to_cftc_events(
        [_row("2022-03-01", created_at="2022-09-13T14:16:09.004Z")],
        fetched_at=datetime(2026, 8, 13, tzinfo=UTC),
    )[0]

    assert event.visible_at == datetime(2022, 3, 15, 13, 30, tzinfo=UTC)
    assert event.availability_basis == (
        "official_normal_release_plus_14d_with_special_outage_exclusion"
    )


@pytest.mark.parametrize("report_date", ["2018-12-24", "2019-01-08", "2019-03-12"])
def test_shutdown_backlog_fails_closed(report_date: str) -> None:
    records = cftc.records_to_cftc_events(
        [_row(report_date, created_at="2022-09-13T14:16:09.004Z")],
        fetched_at=datetime(2026, 8, 13, tzinfo=UTC),
    )

    assert records == []


def test_native_pre_rows_fail_closed_on_missing_or_future_system_timestamp() -> None:
    missing = _row("2023-04-04", created_at="2023-04-07T19:30:04Z")
    missing.pop(":updated_at")
    future = _row("2026-08-11", created_at="2026-08-14T19:30:04Z")

    assert (
        cftc.records_to_cftc_events(
            [missing, future],
            fetched_at=datetime(2026, 8, 13, tzinfo=UTC),
        )
        == []
    )


def test_live_download_queries_stable_contract_code_and_system_fields(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        text = _csv_payload(_row("2023-01-31", created_at="2023-02-24T20:30:04.153Z"))
        url = "https://publicreporting.cftc.gov/resource/gpe5-46if.csv?fixture=1"

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, params: dict[str, object], timeout: float):
        captured.update({"url": url, "params": params, "timeout": timeout})
        return Response()

    monkeypatch.setattr(cftc.httpx, "get", fake_get)
    events = cftc.fetch_cftc_tff_events(
        contracts=["NQ_COT"],
        start=date(2023, 1, 31),
        end=date(2023, 1, 31),
    )

    assert len(events) == 1
    params = captured["params"]
    assert isinstance(params, dict)
    assert ":created_at" in str(params["$select"])
    assert ":updated_at" in str(params["$select"])
    assert "cftc_contract_market_code='20974+'" in str(params["$where"])


def test_snapshot_is_immutable_and_records_exclusions(tmp_path, monkeypatch) -> None:
    rows = [
        _row("2019-01-08", created_at="2022-09-13T14:16:09.004Z"),
        _row("2023-01-31", created_at="2023-02-24T20:30:04.153Z"),
    ]
    download = cftc._CFTCDownload(
        records=rows,
        retrieved_at=datetime(2026, 8, 13, tzinfo=UTC),
        request_url="https://publicreporting.cftc.gov/resource/gpe5-46if.csv?locked=1",
    )
    monkeypatch.setattr(cftc, "_download_cftc_tff_records", lambda **_: download)

    result = cftc.materialize_cftc_tff_snapshot(tmp_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    snapshot = result.snapshot_path.read_bytes()

    assert result.excluded_records == 1
    assert manifest["downloaded_records"] == 2
    assert manifest["records"] == 1
    assert manifest["excluded_records"] == 1
    assert manifest["snapshot_sha256"] == hashlib.sha256(snapshot).hexdigest()
    assert manifest["prompt_hash"] == cftc.CFTC_TFF_TRANSFORM_HASH
    with pytest.raises(FileExistsError, match="immutable CFTC snapshot"):
        cftc.materialize_cftc_tff_snapshot(tmp_path)


def _row(report_date: str, *, created_at: str) -> dict[str, str]:
    return {
        ":id": f"row-{report_date}",
        ":created_at": created_at,
        ":updated_at": created_at,
        "id": f"{report_date.replace('-', '')}20974+F",
        "report_date_as_yyyy_mm_dd": f"{report_date}T00:00:00.000",
        "market_and_exchange_names": "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
        "cftc_contract_market_code": "20974+",
        "open_interest_all": "62994",
        "dealer_positions_long_all": "18517",
        "dealer_positions_short_all": "2124",
        "asset_mgr_positions_long": "15068",
        "asset_mgr_positions_short": "13275",
        "lev_money_positions_long": "10602",
        "lev_money_positions_short": "20210",
        "other_rept_positions_long": "2277",
        "other_rept_positions_short": "5385",
        "nonrept_positions_long_all": "7736",
        "nonrept_positions_short_all": "13206",
    }


def _csv_payload(row: dict[str, str]) -> str:
    fields = list(row)
    header = ",".join(f'"{field}"' for field in fields)
    values = ",".join(f'"{row[field]}"' for field in fields)
    return f"{header}\n{values}\n"
