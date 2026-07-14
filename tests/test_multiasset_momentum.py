from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from open_composer.research import multiasset_momentum as lab


def test_candidate_matrix_is_bounded_and_method_diverse() -> None:
    rows = lab._candidate_specs()

    assert len(rows) == 60
    counts = pd.Series([row["path"] for row in rows]).value_counts().to_dict()
    assert counts == {
        "P1_etf_absolute_relative": 12,
        "P2_sector_risk_adjusted": 12,
        "P3_stock_cross_sectional": 12,
        "P4_stock_trend_quality": 12,
        "P5_stock_residual_sector_relative": 12,
    }
    assert len({row["trial_id"] for row in rows}) == 60


def test_weights_replace_old_holdings_at_rebalance() -> None:
    index = pd.date_range("2020-01-01", periods=300, freq="B", tz="UTC")
    scores = pd.DataFrame(np.nan, index=index, columns=["AAA", "BBB", "CCC"])
    scores.loc[index[252], ["AAA", "BBB", "CCC"]] = [3.0, 2.0, 1.0]
    scores.loc[index[273], ["AAA", "BBB", "CCC"]] = [1.0, 2.0, 3.0]

    weights, rebalances = lab._weights_from_scores(
        scores,
        {"rebalance_days": 21, "top_n": 1},
        sector_map={"AAA": "A", "BBB": "B", "CCC": "C"},
        cash_symbol="BIL",
    )

    assert rebalances == 2
    assert weights.loc[index[252], "AAA"] == 1.0
    assert weights.loc[index[273], "AAA"] == 0.0
    assert weights.loc[index[273], "CCC"] == 1.0
    assert weights.loc[index[280], "CCC"] == 1.0


def test_current_security_filter_rejects_non_common_and_illiquid_rows() -> None:
    valid = lab._normalized_security(
        {
            "symbol": "ABC",
            "name": "ABC Corporation Common Stock",
            "country": "United States",
            "lastsale": "$100.00",
            "volume": "1000000",
            "marketCap": "10000000000",
            "sector": "Technology",
            "industry": "Software",
        }
    )
    etf = lab._normalized_security(
        {
            "symbol": "ABCX",
            "name": "ABC Growth ETF",
            "country": "United States",
            "lastsale": "$100.00",
            "volume": "1000000",
            "marketCap": "10000000000",
        }
    )
    illiquid = lab._normalized_security(
        {
            "symbol": "XYZ",
            "name": "XYZ Common Stock",
            "country": "United States",
            "lastsale": "$100.00",
            "volume": "1000",
            "marketCap": "10000000000",
        }
    )

    assert valid is not None
    assert valid["snapshot_dollar_volume"] == 100_000_000
    assert etf is None
    assert illiquid is None


def test_materialize_universe_records_snapshot_and_survivorship_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rows = []
    for index in range(30):
        symbol = f"A{chr(65 + index // 26)}{chr(65 + index % 26)}"
        rows.append(
            {
                "symbol": symbol,
                "name": f"Company {index} Common Stock",
                "country": "United States",
                "lastsale": "$100.00",
                "volume": "1000000",
                "marketCap": str(100_000_000_000 - index * 1_000_000),
                "sector": f"Sector {index % 5}",
                "industry": "Industry",
            }
        )
    rows.extend({"symbol": f"X{index}"} for index in range(1000))
    monkeypatch.setattr(lab, "_download_nasdaq_snapshot", lambda: rows)

    def fake_quality(root, row, *, refresh, is_etf):
        del root, refresh
        return {
            **row,
            "is_etf": is_etf,
            "quality_pass": True,
            "records": 1000,
            "median_dollar_volume_60": 100_000_000.0,
            "last_timestamp": "2026-07-13T04:00:00+00:00",
            "error": None,
        }

    monkeypatch.setattr(lab, "_fetch_quality_row", fake_quality)
    result = lab.materialize_multiasset_universe(
        tmp_path,
        download_limit=20,
        final_limit=10,
        refresh=False,
    )

    payload = json.loads(result.manifest_path.read_text())
    assert payload["parent_record_count"] == 1030
    assert payload["selected_count"] == 10
    assert payload["survivorship_contract"]["point_in_time_membership_available"] is False
    assert payload["survivorship_contract"]["formal_evidence_start"] == "2026-07-14"


def test_evaluate_candidate_uses_open_to_open_returns_and_four_folds() -> None:
    index = pd.date_range("2021-01-01", periods=900, freq="B", tz="UTC")
    symbols = [f"S{number}" for number in range(12)]
    all_symbols = list(dict.fromkeys([*symbols, *lab.ALL_ETF_SYMBOLS]))
    open_prices = pd.DataFrame(index=index)
    close_prices = pd.DataFrame(index=index)
    volumes = pd.DataFrame(index=index)
    for number, symbol in enumerate(all_symbols):
        trend = np.linspace(100, 180 + number * 5, len(index))
        wave = np.sin(np.arange(len(index)) / (15 + number % 5)) * 2
        open_prices[symbol] = trend + wave
        close_prices[symbol] = trend + wave + 0.2
        volumes[symbol] = 2_000_000 + number * 100_000
    data = {
        "open": open_prices,
        "close": close_prices,
        "volume": volumes,
        "data_as_of": index[-1].isoformat(),
    }
    sectors = {symbol: f"Sector {number % 4}" for number, symbol in enumerate(symbols)}
    spec = next(row for row in lab._candidate_specs() if row["path"] == "P3_stock_cross_sectional")

    result = lab._evaluate_candidate(
        spec,
        data,
        stock_symbols=symbols,
        sector_map=sectors,
        cost_bps=10.0,
    )

    assert len(result["metrics"]["folds"]) == 4
    assert result["metrics"]["rebalance_count"] >= 30
    assert result["metrics"]["out_of_sample"]["bars"] > 100
    assert "information_ratio_vs_equal_weight" in result["metrics"]["out_of_sample"]
