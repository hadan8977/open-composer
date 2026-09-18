"""``portfolio.mode=insider_buy_portfolio`` -> target weights (H-20260917-01).

Small synthetic fixtures (a universe-panel parquet, an insider-feature
parquet, and a miniature SIP daily archive) written under ``tmp_path``,
exercising ``run_insider_portfolio_target_weight_mapping`` end to end --
mirrors the style of ``tests/test_model_ranking_target_weights.py`` and
``tests/test_paper_rehearsal.py``. Covers:

(a) the feature date chosen is the latest one at or before the last
    completed session, and a row dated after that bound is never used;
(b) the ``adv_rank`` band filter;
(c) the ``net_buy_usd_60d`` minimum;
(d) per-name cap clamping scales gross down rather than exceeding the cap;
(e) a candidate with no recent SIP bar is skipped and recorded; and
(f) the universe-root fallback records a warning.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml

from open_composer.adapters.execution.insider_portfolio_target_weights import (
    REQUIRED_INSIDER_COLUMNS,
    run_insider_portfolio_target_weight_mapping,
)
from open_composer.models.strategy_spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SPEC = (
    REPO_ROOT / "tests" / "fixtures" / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
)

#: A real Mon-Fri run of US-equity sessions in September 2026 with no holiday
#: (verified against open_composer.market_calendar.us_equity_session_close).
MONTH_END = pd.Timestamp("2026-08-31")
FEATURE_DATE = pd.Timestamp("2026-09-16")
#: 06:00 ET Thursday 2026-09-17 -- before that session's open, so the last
#: *completed* session is Wednesday 2026-09-16.
NOW = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)

DEFAULT_INSIDER_BUY: dict[str, object] = {
    "universe_root": "data/features/universe_broad",
    "universe_fallback_root": "data/features/universe",
    "insider_feature_root": "data/features/insider_broad",
    "insider_feature_fallback_root": "data/features/insider",
    "adv_rank_min": None,
    "adv_rank_max": None,
    "min_open_market_buy_count_60d": 1,
    "min_net_buy_usd_60d": 25_000.0,
    "min_buyers_60d": 1,
    "rank_column": "net_buy_usd_60d",
    "max_names": 100,
    "gross_target": 1.0,
    "per_name_cap": 0.6,
    "rebalance": "calendar_month_end",
    "stale_bar_sessions": 5,
}


def _insider_row(
    symbol: str, trade_date: object, *, buy_count: int, net_buy_usd: float, buyers: int
) -> dict[str, object]:
    """Build one insider-table row keyed off ``REQUIRED_INSIDER_COLUMNS``
    (rather than hardcoding column names a second time), so this fixture
    breaks loudly if the adapter's required-column contract ever changes."""
    row: dict[str, object] = {"symbol": symbol, "trade_date": pd.Timestamp(trade_date)}
    row.update(dict(zip(REQUIRED_INSIDER_COLUMNS, (buy_count, net_buy_usd, buyers), strict=True)))
    return row


def _write_insider(root: Path, rows: list[dict[str, object]], *, feature_dir: str) -> None:
    frame = pd.DataFrame(rows)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    out_dir = root / feature_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    for year, group in frame.groupby(frame["trade_date"].dt.year):
        group.to_parquet(out_dir / f"{int(year)}.parquet", index=False)


def _write_universe(
    root: Path,
    rows: list[dict[str, object]],
    *,
    universe_dir: str,
    month_end: pd.Timestamp = MONTH_END,
) -> None:
    frame = pd.DataFrame(rows)
    frame["month_end"] = month_end
    out_dir = root / universe_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out_dir / f"{month_end.year}.parquet", index=False)


def _write_sip_daily(
    root: Path, series_by_symbol: dict[str, tuple[list[pd.Timestamp], list[float]]]
) -> None:
    """Same layout as ``tests/test_model_ranking_target_weights.py``'s
    ``_write_sip_daily_archive`` / ``tests/test_sip_parquet_loader.py``:
    ``data/sip/daily/{year}/*.parquet`` with symbol/timestamp/open/high/low/
    close/volume/trade_count/vwap. A symbol absent here has no bar at all,
    i.e. it is unconditionally stale."""
    frames = []
    for symbol, (dates, closes) in series_by_symbol.items():
        frames.append(
            pd.DataFrame(
                {
                    "symbol": [symbol] * len(dates),
                    "timestamp": pd.DatetimeIndex(dates, tz="UTC"),
                    "open": closes,
                    "high": closes,
                    "low": closes,
                    "close": closes,
                    "volume": [1_000_000.0] * len(dates),
                    "trade_count": [100.0] * len(dates),
                    "vwap": closes,
                }
            )
        )
    combined = pd.concat(frames, ignore_index=True)
    for year, group in combined.groupby(combined["timestamp"].dt.year):
        out_dir = root / "data" / "sip" / "daily" / str(int(year))
        out_dir.mkdir(parents=True, exist_ok=True)
        group.to_parquet(out_dir / "shard-0000.parquet", index=False)


def _write_spec(
    root: Path,
    *,
    name: str = "test_insider_buy_portfolio",
    insider_buy: dict[str, object] | None = None,
) -> Path:
    raw = yaml.safe_load(FIXTURE_SPEC.read_text(encoding="utf-8"))
    params = {**DEFAULT_INSIDER_BUY, **(insider_buy or {})}
    raw.update(
        {
            "name": name,
            "timeframe": "daily",
            "universe": ["AAA"],
            "portfolio": {
                "mode": "insider_buy_portfolio",
                "weighting": "equal_weight",
                "gross_exposure_limit": 1.0,
                "insider_buy": params,
            },
        }
    )
    raw["data"]["source"] = "alpaca"
    raw["data"]["path"] = None
    raw["data"]["feed"] = "sip"
    path = root / f"{name}.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    StrategySpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    return path


def test_feature_date_is_latest_completed_session_not_future(tmp_path: Path) -> None:
    """(a) With rows on 2026-09-11, 09-14, 09-16 and 09-17, and ``now`` bound
    to the completed session 2026-09-16, the adapter must pick 09-16 -- never
    09-17 (still in the future relative to the bound) and never an older row
    when a newer eligible one exists. The 09-17 row is deliberately
    *ineligible* (buy_count=0): if the code ever used it by mistake the run
    would refuse to write an empty book and raise, so a passing, non-raising
    run with the right feature date is a strong check on its own."""
    spec_path = _write_spec(tmp_path)
    _write_universe(
        tmp_path,
        [{"symbol": "AAA", "adv_rank": 1, "dollar_adv": 5_000_000.0, "close": 100.0}],
        universe_dir="data/features/universe_broad",
    )
    _write_insider(
        tmp_path,
        [
            _insider_row("AAA", "2026-09-11", buy_count=3, net_buy_usd=10.0, buyers=2),
            _insider_row("AAA", "2026-09-14", buy_count=3, net_buy_usd=20.0, buyers=2),
            _insider_row("AAA", "2026-09-16", buy_count=3, net_buy_usd=100_000.0, buyers=2),
            _insider_row("AAA", "2026-09-17", buy_count=0, net_buy_usd=999_999.0, buyers=0),
        ],
        feature_dir="data/features/insider_broad",
    )
    _write_sip_daily(tmp_path, {"AAA": ([FEATURE_DATE], [100.0])})

    result = run_insider_portfolio_target_weight_mapping(
        spec_path, tmp_path, now=NOW, account_equity_override=100_000.0
    )

    assert result.manifest["insider_feature_date"] == "2026-09-16"
    assert result.manifest["feature_date_bound_last_completed_session"] == "2026-09-16"
    assert result.manifest["selected_count"] == 1
    assert result.is_new_signal is True


def test_adv_rank_band_filters_cohort(tmp_path: Path) -> None:
    """(b) A [501, 1000] adv_rank band keeps III (601) and JJJ (602) but
    drops AAA (rank 1, below the band) and KKK (rank 1500, above the band)
    even though both clear the insider thresholds and would otherwise
    outrank at least one in-band name."""
    spec_path = _write_spec(
        tmp_path, insider_buy={"adv_rank_min": 501, "adv_rank_max": 1000, "per_name_cap": 1.0}
    )
    _write_universe(
        tmp_path,
        [
            {"symbol": "AAA", "adv_rank": 1, "dollar_adv": 5_000_000.0, "close": 100.0},
            {"symbol": "III", "adv_rank": 601, "dollar_adv": 100_000.0, "close": 20.0},
            {"symbol": "JJJ", "adv_rank": 602, "dollar_adv": 90_000.0, "close": 10.0},
            {"symbol": "KKK", "adv_rank": 1500, "dollar_adv": 50_000.0, "close": 5.0},
        ],
        universe_dir="data/features/universe_broad",
    )
    _write_insider(
        tmp_path,
        [
            _insider_row("AAA", FEATURE_DATE, buy_count=3, net_buy_usd=300_000.0, buyers=2),
            _insider_row("III", FEATURE_DATE, buy_count=2, net_buy_usd=150_000.0, buyers=2),
            _insider_row("JJJ", FEATURE_DATE, buy_count=1, net_buy_usd=26_000.0, buyers=1),
            _insider_row("KKK", FEATURE_DATE, buy_count=5, net_buy_usd=400_000.0, buyers=3),
        ],
        feature_dir="data/features/insider_broad",
    )
    _write_sip_daily(
        tmp_path,
        {
            "AAA": ([FEATURE_DATE], [100.0]),
            "III": ([FEATURE_DATE], [20.0]),
            "JJJ": ([FEATURE_DATE], [10.0]),
            "KKK": ([FEATURE_DATE], [5.0]),
        },
    )

    result = run_insider_portfolio_target_weight_mapping(
        spec_path, tmp_path, now=NOW, account_equity_override=100_000.0
    )

    selected = {row["symbol"] for row in _selected_rows(tmp_path, "test_insider_buy_portfolio")}
    assert selected == {"III", "JJJ"}
    assert result.manifest["adv_rank_band"] == [501, 1000]
    assert result.manifest["universe_in_band"] == 2


def test_net_buy_usd_minimum_filters_candidates(tmp_path: Path) -> None:
    """(c) BBB clears the buy-count and buyers minimums but its
    net_buy_usd_60d (20,000) sits below the 25,000 floor, so only AAA
    (100,000) is selected."""
    spec_path = _write_spec(tmp_path, insider_buy={"per_name_cap": 1.0})
    _write_universe(
        tmp_path,
        [
            {"symbol": "AAA", "adv_rank": 1, "dollar_adv": 5_000_000.0, "close": 100.0},
            {"symbol": "BBB", "adv_rank": 2, "dollar_adv": 4_000_000.0, "close": 50.0},
        ],
        universe_dir="data/features/universe_broad",
    )
    _write_insider(
        tmp_path,
        [
            _insider_row("AAA", FEATURE_DATE, buy_count=3, net_buy_usd=100_000.0, buyers=2),
            _insider_row("BBB", FEATURE_DATE, buy_count=2, net_buy_usd=20_000.0, buyers=2),
        ],
        feature_dir="data/features/insider_broad",
    )
    _write_sip_daily(tmp_path, {"AAA": ([FEATURE_DATE], [100.0]), "BBB": ([FEATURE_DATE], [50.0])})

    result = run_insider_portfolio_target_weight_mapping(
        spec_path, tmp_path, now=NOW, account_equity_override=100_000.0
    )

    selected = {row["symbol"] for row in _selected_rows(tmp_path, "test_insider_buy_portfolio")}
    assert selected == {"AAA"}
    assert result.manifest["eligible_after_thresholds"] == 1


def test_per_name_cap_clamps_gross_down(tmp_path: Path) -> None:
    """(d) 12 eligible names, max_names=10, gross_target=1.0,
    per_name_cap=0.05: unclamped equal weight would be 1/10 = 0.10, which
    exceeds the 0.05 cap, so every selected name is clamped to 0.05 and the
    gross is scaled *down* to 0.5 rather than the cap being exceeded."""
    spec_path = _write_spec(
        tmp_path, insider_buy={"max_names": 10, "gross_target": 1.0, "per_name_cap": 0.05}
    )
    symbols = [f"S{i:02d}" for i in range(12)]
    _write_universe(
        tmp_path,
        [
            {"symbol": s, "adv_rank": i + 1, "dollar_adv": 1_000_000.0 - i, "close": 50.0}
            for i, s in enumerate(symbols)
        ],
        universe_dir="data/features/universe_broad",
    )
    _write_insider(
        tmp_path,
        [
            _insider_row(
                s, FEATURE_DATE, buy_count=2, net_buy_usd=1_000_000.0 - i * 1_000.0, buyers=2
            )
            for i, s in enumerate(symbols)
        ],
        feature_dir="data/features/insider_broad",
    )
    _write_sip_daily(tmp_path, {s: ([FEATURE_DATE], [50.0]) for s in symbols})

    result = run_insider_portfolio_target_weight_mapping(
        spec_path, tmp_path, now=NOW, account_equity_override=100_000.0
    )

    assert result.manifest["selected_count"] == 10
    assert result.manifest["gross_scaled_down"] is True
    assert result.manifest["weight_per_name"] == pytest.approx(0.05)
    assert result.manifest["gross_effective"] == pytest.approx(0.5)
    selected = _selected_rows(tmp_path, "test_insider_buy_portfolio")
    assert {row["symbol"] for row in selected} == set(symbols[:10])
    assert all(row["target_weight"] == pytest.approx(0.05) for row in selected)


def test_stale_candidate_skipped_and_recorded(tmp_path: Path) -> None:
    """(e) AAA ranks first by net_buy_usd_60d but has no SIP daily bar at
    all, so it is skipped (delisted/halted/backfilled-only) and recorded in
    the manifest; the book fills from BBB and CCC instead."""
    spec_path = _write_spec(tmp_path, insider_buy={"per_name_cap": 1.0})
    _write_universe(
        tmp_path,
        [
            {"symbol": "AAA", "adv_rank": 1, "dollar_adv": 5_000_000.0, "close": 100.0},
            {"symbol": "BBB", "adv_rank": 2, "dollar_adv": 4_000_000.0, "close": 90.0},
            {"symbol": "CCC", "adv_rank": 3, "dollar_adv": 3_000_000.0, "close": 80.0},
        ],
        universe_dir="data/features/universe_broad",
    )
    _write_insider(
        tmp_path,
        [
            _insider_row("AAA", FEATURE_DATE, buy_count=3, net_buy_usd=100_000.0, buyers=2),
            _insider_row("BBB", FEATURE_DATE, buy_count=2, net_buy_usd=90_000.0, buyers=2),
            _insider_row("CCC", FEATURE_DATE, buy_count=1, net_buy_usd=80_000.0, buyers=1),
        ],
        feature_dir="data/features/insider_broad",
    )
    # AAA deliberately absent: no bar anywhere in the SIP archive.
    _write_sip_daily(tmp_path, {"BBB": ([FEATURE_DATE], [90.0]), "CCC": ([FEATURE_DATE], [80.0])})

    result = run_insider_portfolio_target_weight_mapping(
        spec_path, tmp_path, now=NOW, account_equity_override=100_000.0
    )

    assert result.manifest["skipped_stale"] == ["AAA"]
    assert result.manifest["skipped_stale_count"] == 1
    selected = {row["symbol"] for row in _selected_rows(tmp_path, "test_insider_buy_portfolio")}
    assert selected == {"BBB", "CCC"}
    assert any("skipped 1 name" in warning for warning in result.manifest["warnings"])


def test_universe_root_fallback_records_warning(tmp_path: Path) -> None:
    """(f) Only the narrow universe root has yearly parquet files (the
    broad table "is still building"); the adapter must fall back to it and
    record a loud warning rather than fail or silently use the broad path."""
    spec_path = _write_spec(tmp_path, insider_buy={"per_name_cap": 1.0})
    # data/features/universe_broad is never written -- it has no yearly
    # parquet files at all, which is exactly the fallback trigger condition.
    _write_universe(
        tmp_path,
        [{"symbol": "AAA", "adv_rank": 1, "dollar_adv": 5_000_000.0, "close": 100.0}],
        universe_dir="data/features/universe",
    )
    _write_insider(
        tmp_path,
        [_insider_row("AAA", FEATURE_DATE, buy_count=3, net_buy_usd=100_000.0, buyers=2)],
        feature_dir="data/features/insider_broad",
    )
    _write_sip_daily(tmp_path, {"AAA": ([FEATURE_DATE], [100.0])})

    result = run_insider_portfolio_target_weight_mapping(
        spec_path, tmp_path, now=NOW, account_equity_override=100_000.0
    )

    assert result.manifest["universe_root_fallback_used"] is True
    assert result.manifest["universe_root"] == "data/features/universe"
    assert any(
        "universe" in warning and "FELL BACK" in warning for warning in result.manifest["warnings"]
    )


def _selected_rows(root: Path, name: str) -> list[dict[str, object]]:
    import json

    payload = json.loads(
        (root / "reports" / "execution" / f"{name}-target-weights.json").read_text(encoding="utf-8")
    )
    return [row for row in payload["target_weights"] if row["selected"]]
