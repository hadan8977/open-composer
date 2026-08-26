from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.adapters.data.alpaca import AlpacaDataError
from open_composer.adapters.data.alpaca_snapshot import (
    ALL_ADJUSTMENT_RISK,
    AlpacaRawHTTPResponse,
    _load_contract,
    _requests_from_contract,
    load_immutable_alpaca_snapshot,
    materialize_alpaca_contract_snapshot,
    verify_alpaca_contract_snapshot,
)
from open_composer.models.strategy_spec import StrategySpec


class MockPageClient:
    def __init__(self, pages: list[dict | bytes]) -> None:
        self.pages = list(pages)
        self.requests = []

    def get_raw(
        self,
        *,
        path: str,
        data: dict,
        headers: dict,
    ) -> AlpacaRawHTTPResponse:
        self.requests.append((path, dict(data), dict(headers)))
        page = self.pages.pop(0)
        entity = page if isinstance(page, bytes) else json.dumps(page).encode("utf-8")
        return AlpacaRawHTTPResponse(
            status_code=200,
            entity_bytes=entity,
            headers={"Content-Type": "application/json"},
        )


def test_immutable_alpaca_snapshot_preserves_pages_and_manifest(tmp_path: Path) -> None:
    contract = _write_contract(tmp_path)
    client = MockPageClient(
        [
            {
                "bars": {"SPY": [_bar("2026-01-02T05:00:00Z", 100.0)]},
                "next_page_token": "page-2",
            },
            {
                "bars": {"SPY": [_bar("2026-01-05T05:00:00Z", 101.0)]},
                "next_page_token": None,
            },
            *_complete_daily_responses(200.0, 300.0, 400.0),
        ]
    )

    manifest_path = materialize_alpaca_contract_snapshot(
        tmp_path,
        contract,
        client=client,
        retrieved_at=datetime(2026, 1, 6, tzinfo=UTC),
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = manifest["items"][0]
    output = manifest_path.parent / item["output_path"]
    assert item["row_count"] == 2
    assert item["page_count"] == 2
    assert item["quality"]["status"] == "complete"
    assert item["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert (manifest_path.parent / item["pages"][0]["path"]).exists()
    assert client.requests[0][0] == "/stocks/bars"
    assert client.requests[0][1]["limit"] == 10_000
    assert str(client.requests[0][1]["feed"]) == "sip"
    assert str(client.requests[0][1]["adjustment"]) == "raw"
    assert str(client.requests[0][1]["sort"]) == "asc"
    assert client.requests[0][1]["asof"] == "2026-01-05"
    assert str(client.requests[0][1]["currency"]) == "USD"
    assert client.requests[0][2]["Accept-Encoding"] == "identity"
    assert client.requests[1][1]["page_token"] == "page-2"
    assert manifest["bundle_role"] == "candidate_research"
    assert manifest["request_count"] == 4
    assert manifest["adjustment_policy"]["all_equivalence_assumed"] is False
    assert manifest["adjustment_policy"]["all_adjustment_risk"] == ALL_ADJUSTMENT_RISK
    assert {row["adjustment"] for row in manifest["items"]} == {
        "raw",
        "split",
        "dividend",
        "all",
    }
    assert (manifest_path.parent / "PUBLICATION_COMPLETE.json").exists()
    assert manifest["inventory_count"] == len(manifest["inventory"])
    assert manifest["calendar_sha256"]
    assert verify_alpaca_contract_snapshot(tmp_path, manifest_path)["request_count"] == 4

    with pytest.raises(AlpacaDataError, match="immutable snapshot already exists"):
        materialize_alpaca_contract_snapshot(tmp_path, contract, client=MockPageClient([]))


def test_immutable_alpaca_snapshot_rejects_duplicate_conflicts_atomically(
    tmp_path: Path,
) -> None:
    contract = _write_contract(tmp_path)
    client = MockPageClient(
        [
            {
                "bars": {"SPY": [_bar("2026-01-02T05:00:00Z", 100.0)]},
                "next_page_token": "page-2",
            },
            {
                "bars": {
                    "SPY": [
                        _bar("2026-01-02T05:00:00Z", 999.0),
                        _bar("2026-01-05T05:00:00Z", 101.0),
                    ]
                },
                "next_page_token": None,
            },
        ]
    )

    with pytest.raises(AlpacaDataError, match="duplicate Alpaca timestamps"):
        materialize_alpaca_contract_snapshot(tmp_path, contract, client=client)

    assert not (tmp_path / "data" / "research" / "snapshot-test").exists()
    assert not list((tmp_path / "data" / "research").glob(".snapshot-test.tmp-*"))


def test_immutable_alpaca_snapshot_rejects_missing_sessions(tmp_path: Path) -> None:
    contract = _write_contract(tmp_path)
    client = MockPageClient(
        [
            {
                "bars": {"SPY": [_bar("2026-01-02T05:00:00Z", 100.0)]},
                "next_page_token": None,
            }
        ]
    )

    with pytest.raises(AlpacaDataError, match="daily session completeness failed"):
        materialize_alpaca_contract_snapshot(tmp_path, contract, client=client)


def test_snapshot_contract_rejects_through_date_mismatch_before_network(tmp_path: Path) -> None:
    contract = _write_contract(tmp_path)
    payload = json.loads(contract.read_text(encoding="utf-8"))
    payload["latest_frozen_session"] = "2026-01-02"
    contract.write_text(json.dumps(payload), encoding="utf-8")
    client = MockPageClient([])

    with pytest.raises(AlpacaDataError, match="does not end at latest_frozen_session"):
        materialize_alpaca_contract_snapshot(tmp_path, contract, client=client)

    assert client.requests == []


def test_candidate_snapshot_rejects_intraday_mixing(tmp_path: Path) -> None:
    contract = _write_contract(tmp_path)
    payload = json.loads(contract.read_text(encoding="utf-8"))
    payload["timeframes"]["30m"] = {
        "symbols": ["SPY"],
        "adjustments": ["raw"],
        "requested_start": "2026-01-02T00:00:00Z",
        "requested_end_exclusive": "2026-01-06T00:00:00Z",
        "required_for": ["execution_shadow"],
    }
    contract.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AlpacaDataError, match="must contain only daily"):
        materialize_alpaca_contract_snapshot(
            tmp_path,
            contract,
            client=MockPageClient([]),
        )


def test_snapshot_contract_rejects_unsafe_symbol_before_network(tmp_path: Path) -> None:
    contract = _write_contract(tmp_path)
    payload = json.loads(contract.read_text(encoding="utf-8"))
    payload["symbols"] = ["../SPY"]
    payload["timeframes"]["daily"]["symbols"] = ["../SPY"]
    contract.write_text(json.dumps(payload), encoding="utf-8")
    client = MockPageClient([])

    with pytest.raises(AlpacaDataError, match="unsafe or unsupported"):
        materialize_alpaca_contract_snapshot(tmp_path, contract, client=client)

    assert client.requests == []


def test_immutable_intraday_snapshot_drops_and_records_extended_hours(
    tmp_path: Path,
) -> None:
    contract = _write_intraday_contract(tmp_path)
    bars = [_bar("2026-01-02T09:00:00Z", 99.0)]
    for index in range(13):
        timestamp = pd.Timestamp("2026-01-02T14:30:00Z") + pd.Timedelta(minutes=30 * index)
        bars.append(_bar(timestamp.isoformat(), 100.0 + index))
    client = MockPageClient([{"bars": {"SPY": bars}, "next_page_token": None}])

    manifest_path = materialize_alpaca_contract_snapshot(
        tmp_path,
        contract,
        client=client,
    )

    item = json.loads(manifest_path.read_text(encoding="utf-8"))["items"][0]
    assert item["row_count"] == 13
    assert item["quality"]["provider_off_session_bar_count"] == 1


def test_snapshot_verifier_rejects_tampered_raw_page(tmp_path: Path) -> None:
    contract = _write_contract(tmp_path)
    client = MockPageClient(
        [
            {
                "bars": {
                    "SPY": [
                        _bar("2026-01-02T05:00:00Z", 100.0),
                        _bar("2026-01-05T05:00:00Z", 101.0),
                    ]
                },
                "next_page_token": None,
            },
            *_complete_daily_responses(200.0, 300.0, 400.0),
        ]
    )
    manifest_path = materialize_alpaca_contract_snapshot(
        tmp_path,
        contract,
        client=client,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    page_path = manifest_path.parent / manifest["items"][0]["pages"][0]["path"]
    page_path.write_text(page_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(AlpacaDataError, match="raw page SHA-256 mismatch"):
        verify_alpaca_contract_snapshot(tmp_path, manifest_path)


def test_fourteen_symbol_contract_expands_exact_daily_bundle(tmp_path: Path) -> None:
    contract = _write_contract(tmp_path)
    payload = json.loads(contract.read_text(encoding="utf-8"))
    symbols = [
        "SPY",
        "QQQ",
        "BIL",
        "GLD",
        "IEF",
        "XLB",
        "XLE",
        "XLF",
        "XLI",
        "XLK",
        "XLP",
        "XLU",
        "XLV",
        "XLY",
    ]
    payload["symbols"] = symbols
    payload["timeframes"]["daily"]["symbols"] = symbols
    contract.write_text(json.dumps(payload), encoding="utf-8")

    requests = _requests_from_contract(_load_contract(contract))

    assert len(requests) == 56
    assert {request.symbol for request in requests} == set(symbols)
    assert all(
        request.timeframe == "daily"
        and request.feed == "sip"
        and request.adjustment in {"raw", "split", "dividend", "all"}
        and request.symbol_asof.isoformat() == "2026-01-05"
        and request.currency == "USD"
        for request in requests
    )


def test_immutable_alpaca_strategy_loader_verifies_sidecar_hash(tmp_path: Path) -> None:
    path = tmp_path / "data" / "research" / "bound" / "spy_1d_alpaca_sip_all.csv"
    path.parent.mkdir(parents=True)
    frame = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-02T05:00:00+00:00",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000,
            }
        ]
    )
    frame.to_csv(path, index=False)
    manifest = {
        "symbol": "SPY",
        "timeframe": "daily",
        "feed": "sip",
        "adjustment": "all",
        "session_scope": "regular",
        "output_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "row_count": 1,
        "first_timestamp": "2026-01-02T05:00:00+00:00",
        "last_timestamp": "2026-01-02T05:00:00+00:00",
        "quality": {"status": "complete"},
    }
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    spec = _immutable_spec(path.relative_to(tmp_path).as_posix())

    loaded = load_immutable_alpaca_snapshot(spec, tmp_path)

    assert loaded.attrs["data_source_mode"] == "immutable_research_snapshot"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(AlpacaDataError, match="SHA-256 mismatch"):
        load_immutable_alpaca_snapshot(spec, tmp_path)


def test_immutable_alpaca_strategy_loader_never_falls_back(tmp_path: Path) -> None:
    spec = _immutable_spec("data/research/missing.csv")

    with pytest.raises(AlpacaDataError, match="snapshot is missing"):
        load_immutable_alpaca_snapshot(spec, tmp_path)


def test_generic_loader_resolves_verified_snapshot_bundle_item(tmp_path: Path) -> None:
    contract = _write_contract(tmp_path)
    manifest_path = materialize_alpaca_contract_snapshot(
        tmp_path,
        contract,
        client=MockPageClient(_complete_daily_responses(100.0, 200.0, 300.0, 400.0)),
        retrieved_at=datetime(2026, 1, 6, tzinfo=UTC),
    )
    spec = _immutable_spec(manifest_path.relative_to(tmp_path).as_posix())

    loaded = load_ohlcv_for_spec(spec, tmp_path)

    assert loaded["open"].tolist() == [400.0, 401.0]
    assert loaded.attrs["data_source_mode"] == "immutable_research_snapshot_bundle"
    assert loaded.attrs["data_bundle_item_identity"] == {
        "symbol": "SPY",
        "timeframe": "daily",
        "feed": "sip",
        "adjustment": "all",
        "session_scope": "regular",
    }
    assert loaded.attrs["data_bundle_manifest_path"] == str(manifest_path.resolve())


def test_generic_bundle_loader_fails_closed_for_missing_identity(tmp_path: Path) -> None:
    contract = _write_contract(tmp_path)
    manifest_path = materialize_alpaca_contract_snapshot(
        tmp_path,
        contract,
        client=MockPageClient(_complete_daily_responses(100.0, 200.0, 300.0, 400.0)),
        retrieved_at=datetime(2026, 1, 6, tzinfo=UTC),
    )
    payload = _immutable_spec(manifest_path.relative_to(tmp_path).as_posix()).model_dump(
        mode="python"
    )
    payload["data"]["symbol"] = "QQQ"
    payload["universe"] = ["QQQ"]
    spec = StrategySpec.model_validate(payload)

    with pytest.raises(AlpacaDataError, match="exactly one matching item"):
        load_ohlcv_for_spec(spec, tmp_path)


def _write_contract(root: Path) -> Path:
    _write_source_bindings(root)
    path = root / "contract.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "iter_id": "snapshot_test_r1",
                "provider": "alpaca",
                "feed": "sip",
                "adjustments": ["raw", "split", "dividend", "all"],
                "symbol_asof": "2026-01-05",
                "symbol_asof_semantics": "symbol_mapping_only_not_historical_data_vintage",
                "currency": "USD",
                "spin_off_handling": ("provider_all_composite_only_no_independent_decomposition"),
                "historical_vintage_claim_allowed": False,
                "session_scope": "regular",
                "latest_frozen_session": "2026-01-05",
                "symbols": ["SPY"],
                "timeframes": {
                    "daily": {
                        "symbols": ["SPY"],
                        "adjustments": ["raw", "split", "dividend", "all"],
                        "requested_start": "2026-01-02T00:00:00Z",
                        "requested_end_exclusive": "2026-01-06T00:00:00Z",
                        "required_for": ["candidate_research"],
                    }
                },
                "bundle_role": "candidate_research",
                "candidate_required_dataset": "daily",
                "immutable_output_root": "data/research/snapshot-test",
                "manifest_requirements": ["raw_and_normalized_sha256"],
                "forward_fill_allowed": False,
                "zero_return_substitution_allowed": False,
                "partial_completed_session_allowed": False,
                "overwrite_existing_snapshot_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_intraday_contract(root: Path) -> Path:
    _write_source_bindings(root)
    path = root / "intraday-contract.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "iter_id": "snapshot_test_r1",
                "provider": "alpaca",
                "feed": "sip",
                "adjustments": ["raw"],
                "symbol_asof": "2026-01-02",
                "symbol_asof_semantics": "symbol_mapping_only_not_historical_data_vintage",
                "currency": "USD",
                "spin_off_handling": ("provider_all_composite_only_no_independent_decomposition"),
                "historical_vintage_claim_allowed": False,
                "session_scope": "regular",
                "latest_frozen_session": "2026-01-02",
                "symbols": ["SPY"],
                "timeframes": {
                    "30m": {
                        "symbols": ["SPY"],
                        "adjustments": ["raw"],
                        "requested_start": "2026-01-02T00:00:00Z",
                        "requested_end_exclusive": "2026-01-03T00:00:00Z",
                        "required_for": ["execution_shadow"],
                    }
                },
                "bundle_role": "selection_prohibited_execution_shadow",
                "candidate_required_dataset": None,
                "immutable_output_root": "data/research/intraday-test",
                "manifest_requirements": ["raw_and_normalized_sha256"],
                "forward_fill_allowed": False,
                "zero_return_substitution_allowed": False,
                "partial_completed_session_allowed": False,
                "overwrite_existing_snapshot_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_source_bindings(root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    bindings = [
        "schemas/alpaca_snapshot_contract.schema.json",
        "schemas/alpaca_snapshot_manifest.schema.json",
        "open_composer/adapters/data/alpaca_snapshot.py",
        "open_composer/market_calendar.py",
    ]
    for relative in bindings:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo_root / relative, destination)


def _bar(timestamp: str, price: float) -> dict:
    return {
        "t": timestamp,
        "o": price,
        "h": price + 1,
        "l": price - 1,
        "c": price + 0.5,
        "v": 1_000,
    }


def _complete_daily_responses(*prices: float) -> list[dict]:
    return [
        {
            "bars": {
                "SPY": [
                    _bar("2026-01-02T05:00:00Z", price),
                    _bar("2026-01-05T05:00:00Z", price + 1.0),
                ]
            },
            "next_page_token": None,
        }
        for price in prices
    ]


def _immutable_spec(path: str) -> StrategySpec:
    return StrategySpec(
        name="immutable_spy",
        description="immutable loader fixture",
        timeframe="daily",
        universe=["SPY"],
        lifecycle="draft",
        entry={"all": ["close > sma(close, 2)"]},
        exit={"all": ["close <= sma(close, 2)"]},
        risk={"max_trades_per_day": 1},
        execution={"mode": "manual_signal", "broker": "none"},
        data={"source": "alpaca", "symbol": "SPY", "feed": "sip", "path": path},
        data_assumptions={
            "source": "alpaca",
            "adjusted": True,
            "acquisition_tier": "research_strict",
            "adjustment": "all",
            "session_scope": "regular",
            "immutable_snapshot_required": True,
        },
    )
