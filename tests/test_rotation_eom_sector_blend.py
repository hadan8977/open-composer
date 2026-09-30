"""``etf_rotation.selection_rule=eom_reversal_sector_front_run_blend``.

Card H-20260928-20 candidate C2 on the paper engine: the calendar helpers,
the pure book, the replay, the config contract, content-hash stability for
the momentum sleeves, and one end-to-end run of the real mapping entry point
on synthetic ``data/sip/daily`` parquet under ``tmp_path``. Exact parity with
the screen lane on the real archive is checked by
``scripts/check_eom_sector_blend_parity.py``, not here.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from open_composer.adapters.execution.rotation_target_weights import (
    eom_sector_blend_book,
    fourth_friday,
    front_run_score_window,
    replay_eom_sector_blend_books,
    run_rotation_target_weight_mapping,
)
from open_composer.models.strategy_spec import ETFRotationConfig, load_strategy_spec
from open_composer.strategy_versions import _remove_unset_schema_extensions

REPO_ROOT = Path(__file__).resolve().parents[1]
C2_SPEC = REPO_ROOT / "strategy_specs" / "drafts" / "us_etf_eom_sector_blend_monthly.yaml"
MOMENTUM_SPEC = (
    REPO_ROOT / "strategy_specs" / "drafts" / "us_etf_sector_rotation_252_top2_weekly.yaml"
)
MENU = ["SPY", "XLB", "XLE", "XLK"]
DATES: list[date] = [d.date() for d in pd.bdate_range("2025-06-02", "2026-08-31")]


def _blend_config(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "menu": list(MENU),
        "cash_symbol": "SHY",
        "selection_rule": "eom_reversal_sector_front_run_blend",
        "eom_sector_blend": {"reversal_symbol": "SPY", "reversal_weight": 0.5},
        "top_n": 2,
        "rebalance": "monthly_last_session",
        "absolute_momentum_filter": False,
    }
    raw.update(overrides)
    return raw


def _closes(
    *, sector_moves: dict[str, float], spy_last_week: float
) -> dict[str, dict[date, float]]:
    """Flat 100 everywhere, except: each sector moves by ``sector_moves`` in a
    straight line across September 2025 (the front-run window of the
    2026-07-31 signal), and SPY moves by ``spy_last_week`` between the July
    2026 fourth Friday (07-24) and the month's last session (07-31)."""
    out: dict[str, dict[date, float]] = {"SPY": {}, "SHY": {}}
    september = [day for day in DATES if day.year == 2025 and day.month == 9]
    for symbol, move in sector_moves.items():
        series: dict[date, float] = {}
        for day in DATES:
            if day < september[0]:
                series[day] = 100.0
            elif day <= september[-1]:
                step = september.index(day) + 1
                series[day] = 100.0 * (1.0 + move * step / len(september))
            else:
                series[day] = 100.0 * (1.0 + move)
        out[symbol] = series
    for day in DATES:
        out["SHY"][day] = 80.0
        late_july = date(2026, 7, 24) < day <= date(2026, 7, 31)
        after = day > date(2026, 7, 31)
        out["SPY"][day] = 100.0 * (1.0 + spy_last_week) if late_july or after else 100.0
    return out


def _series(
    closes: dict[str, dict[date, float]],
) -> dict[str, tuple[list[date], dict[date, float]]]:
    return {symbol: (sorted(values), values) for symbol, values in closes.items()}


def _write_archive(root: Path, closes: dict[str, dict[date, float]]) -> None:
    rows = [
        {
            "symbol": symbol,
            "timestamp": pd.Timestamp(day, tz="UTC"),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1_000_000.0,
            "trade_count": 100.0,
            "vwap": close,
        }
        for symbol, series in closes.items()
        for day, close in series.items()
    ]
    frame = pd.DataFrame(rows)
    for year, group in frame.groupby(frame["timestamp"].dt.year):
        out_dir = root / "data" / "sip" / "daily" / str(int(year))
        out_dir.mkdir(parents=True, exist_ok=True)
        group.to_parquet(out_dir / "shard-0000.parquet", index=False)
    account = root / "reports" / "paper" / "account.json"
    account.parent.mkdir(parents=True, exist_ok=True)
    account.write_text(json.dumps({"equity": 100_000.0, "generated_at": "x"}), encoding="utf-8")


# ---------------------------------------------------------------------------
# calendar helpers


def test_fourth_friday_matches_the_fourth_friday_of_every_month() -> None:
    for year in range(2016, 2027):
        for month in range(1, 13):
            start = pd.Timestamp(year=year, month=month, day=1)
            fridays = pd.date_range(start, start + pd.offsets.MonthEnd(0), freq="W-FRI")
            assert fourth_friday(year, month) == fridays[3].date()


@pytest.mark.parametrize(
    ("signal", "window"),
    [
        (date(2026, 9, 30), (date(2025, 11, 1), date(2025, 11, 30))),
        (date(2026, 10, 30), (date(2025, 12, 1), date(2025, 12, 31))),
        (date(2026, 11, 30), (date(2026, 1, 1), date(2026, 1, 31))),
        (date(2026, 12, 31), (date(2026, 2, 1), date(2026, 2, 28))),
        (date(2027, 12, 31), (date(2027, 2, 1), date(2027, 2, 28))),
        (date(2023, 12, 29), (date(2023, 2, 1), date(2023, 2, 28))),
    ],
)
def test_front_run_window_is_the_month_after_the_holding_month_a_year_earlier(
    signal: date, window: tuple[date, date]
) -> None:
    assert front_run_score_window(signal) == window


# ---------------------------------------------------------------------------
# pure book


def test_book_fires_the_reversal_leg_and_picks_the_top_two_sectors() -> None:
    series = _series(
        _closes(sector_moves={"XLB": -0.03, "XLE": 0.05, "XLK": 0.10}, spy_last_week=-0.01)
    )
    book = eom_sector_blend_book(
        series,
        date(2026, 7, 31),
        menu=MENU,
        cash_symbol="SHY",
        reversal_symbol="SPY",
        reversal_weight=0.5,
        top_n=2,
    )
    assert book.reversal_anchor_session == date(2026, 7, 24)
    assert book.reversal_fired
    assert book.reversal_return == pytest.approx(-0.01)
    assert book.score_window == (date(2025, 9, 1), date(2025, 9, 30))
    assert book.picks == ["XLK", "XLE"]
    assert book.weights == pytest.approx({"SPY": 0.5, "XLK": 0.25, "XLE": 0.25, "SHY": 0.0})


def test_book_leaves_the_reversal_slot_in_cash_when_spy_rose() -> None:
    series = _series(
        _closes(sector_moves={"XLB": -0.03, "XLE": 0.05, "XLK": 0.10}, spy_last_week=0.01)
    )
    book = eom_sector_blend_book(
        series,
        date(2026, 7, 31),
        menu=MENU,
        cash_symbol="SHY",
        reversal_symbol="SPY",
        reversal_weight=0.5,
        top_n=2,
    )
    assert not book.reversal_fired
    assert book.weights == pytest.approx({"XLK": 0.25, "XLE": 0.25, "SHY": 0.5})


def test_book_is_all_cash_when_no_leg_can_be_computed() -> None:
    closes = _closes(sector_moves={"XLB": -0.03, "XLE": 0.05, "XLK": 0.10}, spy_last_week=0.01)
    late = {
        symbol: {d: v for d, v in s.items() if d >= date(2026, 1, 2)}
        for symbol, s in closes.items()
    }
    book = eom_sector_blend_book(
        _series(late),
        date(2026, 7, 31),
        menu=MENU,
        cash_symbol="SHY",
        reversal_symbol="SPY",
        reversal_weight=0.5,
        top_n=2,
    )
    assert book.picks == []
    assert set(book.ineligible) == {"XLB", "XLE", "XLK"}
    assert book.weights == {"SHY": 1.0}


def test_replay_changes_the_book_at_the_open_after_each_month_end() -> None:
    series = _series(
        _closes(sector_moves={"XLB": -0.03, "XLE": 0.05, "XLK": 0.10}, spy_last_week=-0.01)
    )
    sessions = [day for day in DATES if day != date(2026, 7, 3)]  # Independence Day observed
    frame, signals = replay_eom_sector_blend_books(
        series,
        sessions,
        menu=MENU,
        cash_symbol="SHY",
        reversal_symbol="SPY",
        reversal_weight=0.5,
        top_n=2,
    )
    assert date(2026, 7, 31) in signals
    assert frame.loc[date(2026, 7, 31), "SPY"] == 0.0
    assert frame.loc[date(2026, 8, 3)].to_dict() == pytest.approx(
        {"SHY": 0.0, "SPY": 0.5, "XLB": 0.0, "XLE": 0.25, "XLK": 0.25}
    )
    assert frame.loc[sessions[0]].to_dict() == {
        "SHY": 1.0,
        "SPY": 0.0,
        "XLB": 0.0,
        "XLE": 0.0,
        "XLK": 0.0,
    }
    assert frame.sum(axis=1).round(12).eq(1.0).all()


# ---------------------------------------------------------------------------
# config contract and content hash


def test_blend_config_accepts_the_c2_shape() -> None:
    config = ETFRotationConfig.model_validate(_blend_config())
    assert config.eom_sector_blend is not None
    assert config.lookbacks is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"eom_sector_blend": None},
        {"rebalance": "weekly_friday"},
        {"lookbacks": [21]},
        {"absolute_momentum_filter": True},
        {"eom_sector_blend": {"reversal_symbol": "QQQ"}},
        {"top_n": 4},
        {"unfilled_slot_policy": "renormalize_survivors"},
        {"vol_target": {"target_annual_vol": 0.2}},
    ],
)
def test_blend_config_rejects_what_the_rule_does_not_support(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ETFRotationConfig.model_validate(_blend_config(**overrides))


def test_momentum_config_still_needs_lookbacks_and_no_blend_block() -> None:
    base = {
        "menu": ["XLK", "XLV"],
        "cash_symbol": "SHY",
        "top_n": 1,
        "rebalance": "monthly_last_session",
    }
    with pytest.raises(ValidationError):
        ETFRotationConfig.model_validate(base)
    with pytest.raises(ValidationError):
        ETFRotationConfig.model_validate(
            {**base, "lookbacks": [21], "eom_sector_blend": {"reversal_symbol": "XLK"}}
        )
    assert ETFRotationConfig.model_validate({**base, "lookbacks": [21]}).lookbacks == [21]


def test_new_fields_stay_out_of_momentum_sleeve_hashes_but_bind_the_blend_spec() -> None:
    momentum = load_strategy_spec(MOMENTUM_SPEC)
    payload = momentum.model_dump(mode="json")
    _remove_unset_schema_extensions(momentum, payload)
    assert "selection_rule" not in payload["portfolio"]["etf_rotation"]
    assert "eom_sector_blend" not in payload["portfolio"]["etf_rotation"]

    blend = load_strategy_spec(C2_SPEC)
    payload = blend.model_dump(mode="json")
    _remove_unset_schema_extensions(blend, payload)
    rotation = payload["portfolio"]["etf_rotation"]
    assert rotation["selection_rule"] == "eom_reversal_sector_front_run_blend"
    assert rotation["eom_sector_blend"] == {"reversal_symbol": "SPY", "reversal_weight": 0.5}


# ---------------------------------------------------------------------------
# end to end through the real spec field


def test_mapping_writes_the_blend_book_for_the_real_spec_shape(tmp_path: Path) -> None:
    closes = _closes(sector_moves={"XLB": -0.03, "XLE": 0.05, "XLK": 0.10}, spy_last_week=-0.01)
    _write_archive(tmp_path, closes)
    raw = yaml.safe_load(C2_SPEC.read_text(encoding="utf-8"))
    raw["name"] = "eom_blend_smoke"
    raw["universe"] = [*MENU, "SHY"]
    raw["portfolio"]["etf_rotation"]["menu"] = list(MENU)
    spec_path = tmp_path / "strategy_specs" / "drafts" / "eom_blend_smoke.yaml"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    result = run_rotation_target_weight_mapping(
        spec_path, tmp_path, as_of=datetime(2026, 8, 27, 20, 0, tzinfo=UTC)
    )

    manifest = result.manifest
    assert manifest["signal_session"] == "2026-07-31"
    assert manifest["rebalance_session"] == "2026-08-03"
    assert manifest["selection_rule"] == "eom_reversal_sector_front_run_blend"
    assert manifest["selected"] == ["SPY", "XLE", "XLK"]
    assert manifest["eom_sector_blend"]["reversal_fired"] is True
    assert manifest["eom_sector_blend"]["front_run_picks"] == ["XLK", "XLE"]
    assert manifest["sizing_equity"] == pytest.approx(15_000.0)
    payload = json.loads(result.target_weights_path.read_text(encoding="utf-8"))
    weights = {row["symbol"]: row["target_weight"] for row in payload["target_weights"]}
    assert weights == pytest.approx({"SHY": 0.0, "SPY": 0.5, "XLE": 0.25, "XLK": 0.25})
    assert result.signal_count == 3
