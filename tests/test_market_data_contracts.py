from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_composer.capabilities.evaluator import evaluate_capabilities
from open_composer.data_contracts import build_market_data_manifest, validate_market_data_rows


def test_trade_tick_contract_requires_price_size_timestamp(repo_root: Path) -> None:
    rows = validate_market_data_rows(
        repo_root / "data" / "fixtures" / "market_data" / "trade_ticks.jsonl",
        "trade_tick",
    )

    assert len(rows) == 2
    assert rows[0].price > 0
    assert rows[0].size > 0


def test_quote_tick_contract_requires_bid_ask_ordering(tmp_path: Path) -> None:
    path = tmp_path / "bad_quotes.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": "2026-01-02T14:30:00Z",
                "symbol": "QQQ",
                "bid_price": 500.20,
                "bid_size": 1,
                "ask_price": 500.10,
                "ask_size": 1,
                "source": "fixture",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="bid_price"):
        validate_market_data_rows(path, "quote_tick")


def test_order_book_delta_contract_requires_sequence(tmp_path: Path) -> None:
    path = tmp_path / "bad_depth.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": "2026-01-02T14:30:00Z",
                "symbol": "QQQ",
                "side": "bid",
                "price": 500.10,
                "size_delta": 100,
                "level": 1,
                "source": "fixture",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sequence"):
        validate_market_data_rows(path, "order_book_delta")


def test_market_data_manifest_hash_changes_when_rows_change(tmp_path: Path) -> None:
    path = tmp_path / "quotes.jsonl"
    path.write_text(
        (
            '{"timestamp":"2026-01-02T14:30:00Z","symbol":"QQQ","bid_price":500.09,'
            '"bid_size":300,"ask_price":500.11,"ask_size":250,"source":"fixture"}\n'
        ),
        encoding="utf-8",
    )
    first = build_market_data_manifest(path, "quote_tick", root=tmp_path)
    path.write_text(
        (
            '{"timestamp":"2026-01-02T14:30:00Z","symbol":"QQQ","bid_price":500.10,'
            '"bid_size":300,"ask_price":500.12,"ask_size":250,"source":"fixture"}\n'
        ),
        encoding="utf-8",
    )
    second = build_market_data_manifest(path, "quote_tick", root=tmp_path)

    assert first.sha256 != second.sha256
    assert first.paper_ready is False
    assert first.kind == "quote_tick"


def test_capability_registry_can_express_l2_research_only(sample_workspace: Path) -> None:
    evaluations = evaluate_capabilities(sample_workspace)
    microstructure = next(
        item for item in evaluations if item.capability_id == "market.microstructure_fixture"
    )

    assert microstructure.passed is True
    assert microstructure.records == 2
