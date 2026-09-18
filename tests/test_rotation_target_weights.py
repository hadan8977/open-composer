"""``portfolio.mode=etf_rotation_portfolio`` -> target weights.

Synthetic parquet fixtures written under ``tmp_path`` (``data/sip/daily/
{year}/*.parquet``) plus a fake ``reports/paper/account.json`` -- the real
archive is never read. ``portfolio.etf_rotation`` is not yet wired into the
real ``StrategySpec`` (a concurrent change is adding it), so most tests call
:func:`run_rotation_target_weight_mapping_for_spec` directly with a real
``StrategySpec`` (built from the shared test fixture, with only
``portfolio.mode`` monkeypatched -- a plain attribute set, since Pydantic v2
does not re-validate on assignment) and a ``SimpleNamespace`` standing in for
``spec.portfolio.etf_rotation``. The one end-to-end test that loads a YAML
through the real ``portfolio.etf_rotation`` field is skipped until that field
exists (see ``_real_spec_supports_etf_rotation``).

Covers: ranking + weight-sum-to-one with the cash remainder; the
absolute-momentum filter sending a weak pick to cash; ghost-bar exclusion;
idempotence across three consecutive intra-period days; a short-history
symbol marked ineligible instead of crashing; ``weekly_friday`` vs
``monthly_last_session`` picking different sessions; the three
``notional_budget_usd`` sizing cases; and three period-completion "gotcha"
cases (rebalance date must be decided from the real market calendar, not
from whatever date happens to be newest in the archive).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from open_composer.adapters.execution.rotation_target_weights import (
    build_weights,
    load_price_panel,
    resolve_signal_session,
    run_rotation_target_weight_mapping,
    run_rotation_target_weight_mapping_for_spec,
)
from open_composer.models.strategy_spec import PortfolioConfig, StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SPEC = (
    REPO_ROOT / "tests" / "fixtures" / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
)

#: Business days spanning a month boundary (July 2026 -> August 2026) and
#: several ISO week boundaries, used by every full-pipeline test below. Starts
#: well before July so that July's 66 on/before-session count clears the real
#: ``ETFRotationConfig.min_history_sessions`` floor of 30.
ALL_DATES: list[date] = [d.date() for d in pd.bdate_range("2026-05-01", "2026-08-31")]


# ---------------------------------------------------------------------------
# fixture builders


def _build_spec(*, name: str) -> StrategySpec:
    """A real, fully-valid ``StrategySpec`` with ``portfolio.mode`` set to
    ``etf_rotation_portfolio`` by plain attribute assignment -- Pydantic v2
    does not re-run ``Literal``/model validators on assignment, so this is a
    real spec object (``build_signal``/``strategy_content_hash`` work
    unmodified) even though the real schema does not register this mode
    yet."""
    raw = yaml.safe_load(FIXTURE_SPEC.read_text(encoding="utf-8"))
    raw["name"] = name
    raw["timeframe"] = "daily"
    raw["universe"] = ["SPY"]
    raw["data"]["source"] = "alpaca"
    raw["data"]["path"] = None
    raw["data"]["feed"] = "sip"
    spec = StrategySpec.model_validate(raw)
    spec.portfolio.mode = "etf_rotation_portfolio"
    spec.portfolio.weighting = "equal_weight"
    spec.portfolio.gross_exposure_limit = 1.0
    spec.portfolio.max_symbol_weight = 1.0
    return spec


def _rotation_config(
    *,
    menu: list[str],
    cash_symbol: str,
    lookbacks: list[int],
    top_n: int,
    rebalance: str,
    absolute_momentum_filter: bool,
    min_history_sessions: int,
    notional_budget_usd: float | None = None,
    unfilled_slot_policy: str = "cash",
) -> SimpleNamespace:
    """Stand-in for ``spec.portfolio.etf_rotation`` (``ETFRotationConfig``)."""
    return SimpleNamespace(
        menu=menu,
        cash_symbol=cash_symbol,
        lookbacks=lookbacks,
        top_n=top_n,
        rebalance=rebalance,
        absolute_momentum_filter=absolute_momentum_filter,
        min_history_sessions=min_history_sessions,
        notional_budget_usd=notional_budget_usd,
        unfilled_slot_policy=unfilled_slot_policy,
    )


def _trend_series(dates: list[date], *, base: float, slope: float) -> dict[date, float]:
    return {day: base * (1.0 + slope * idx) for idx, day in enumerate(dates)}


def _sip_rows(
    series_by_symbol: dict[str, dict[date, float]], *, ghost: bool = False
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for symbol, series in series_by_symbol.items():
        for day, close in series.items():
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": pd.Timestamp(day, tz="UTC"),
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": 0.0 if ghost else 1_000_000.0,
                    "trade_count": 0.0 if ghost else 100.0,
                    "vwap": close,
                }
            )
    return rows


def _write_sip_daily(root: Path, rows: list[dict[str, object]]) -> None:
    frame = pd.DataFrame(rows)
    for year, group in frame.groupby(frame["timestamp"].dt.year):
        out_dir = root / "data" / "sip" / "daily" / str(int(year))
        out_dir.mkdir(parents=True, exist_ok=True)
        existing = list(out_dir.glob("shard-*.parquet"))
        group.to_parquet(out_dir / f"shard-{len(existing):04d}.parquet", index=False)


def _write_account(root: Path, equity: float) -> None:
    path = root / "reports" / "paper" / "account.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"equity": equity, "generated_at": "2026-08-27T20:00:00Z"}), encoding="utf-8"
    )


def _read_target_weights(root: Path, name: str) -> dict[str, object]:
    path = root / "reports" / "execution" / f"{name}-target-weights.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _spec_path(tmp_path: Path, name: str) -> Path:
    return tmp_path / "strategy_specs" / "drafts" / f"{name}.yaml"


#: Shared 4-ETF-plus-cash universe: strictly ordered momentum by construction
#: (AAA > BBB > DDD > CCC), so "top-2" and "ranking order" assertions do not
#: depend on the exact lookback arithmetic.
def _write_ranking_fixture(tmp_path: Path) -> None:
    series = {
        "AAA": _trend_series(ALL_DATES, base=100.0, slope=0.004),
        "BBB": _trend_series(ALL_DATES, base=50.0, slope=0.002),
        "CCC": _trend_series(ALL_DATES, base=80.0, slope=-0.001),
        "DDD": _trend_series(ALL_DATES, base=30.0, slope=0.0005),
        "CASHX": _trend_series(ALL_DATES, base=10.0, slope=0.0006),
    }
    _write_sip_daily(tmp_path, _sip_rows(series))
    _write_account(tmp_path, 100_000.0)


def _ranking_config(
    *, rebalance: str, top_n: int = 2, absolute_momentum_filter: bool = False
) -> SimpleNamespace:
    return _rotation_config(
        menu=["AAA", "BBB", "CCC", "DDD"],
        cash_symbol="CASHX",
        lookbacks=[2, 3],
        top_n=top_n,
        rebalance=rebalance,
        absolute_momentum_filter=absolute_momentum_filter,
        min_history_sessions=6,
    )


AS_OF_AUG27 = datetime(2026, 8, 27, 20, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# 1. ranking + weight sum


def test_ranking_picks_top_symbols_and_weights_sum_to_one_with_cash_remainder(
    tmp_path: Path,
) -> None:
    _write_ranking_fixture(tmp_path)
    spec = _build_spec(name="rotation_ranking")
    rotation_config = _ranking_config(rebalance="monthly_last_session", top_n=2)

    result = run_rotation_target_weight_mapping_for_spec(
        spec, rotation_config, _spec_path(tmp_path, spec.name), tmp_path, as_of=AS_OF_AUG27
    )

    assert result.manifest["signal_session"] == "2026-07-31"
    assert result.manifest["selected"] == ["AAA", "BBB"]
    payload = _read_target_weights(tmp_path, spec.name)
    rows = {row["symbol"]: row for row in payload["target_weights"]}
    assert set(rows) == {"AAA", "BBB", "CASHX"}
    assert rows["AAA"]["target_weight"] == pytest.approx(0.5)
    assert rows["BBB"]["target_weight"] == pytest.approx(0.5)
    assert rows["AAA"]["selected"] is True
    assert rows["CASHX"]["target_weight"] == pytest.approx(0.0)
    assert rows["CASHX"]["selected"] is False
    assert rows["CASHX"]["leg"] == "cash"
    assert rows["AAA"]["leg"] == "rotation"
    assert sum(row["target_weight"] for row in rows.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 2. absolute-momentum filter


def test_absolute_momentum_filter_sends_weak_pick_to_cash(tmp_path: Path) -> None:
    spec = _build_spec(name="rotation_filter")
    rotation_config = _rotation_config(
        menu=["WEAK", "STRONG"],
        cash_symbol="CASHX",
        lookbacks=[2, 3],
        top_n=2,
        rebalance="monthly_last_session",
        absolute_momentum_filter=True,
        min_history_sessions=6,
    )
    series = {
        "WEAK": _trend_series(ALL_DATES, base=40.0, slope=0.0003),
        "STRONG": _trend_series(ALL_DATES, base=60.0, slope=0.005),
        "CASHX": _trend_series(ALL_DATES, base=10.0, slope=0.0008),
    }
    _write_sip_daily(tmp_path, _sip_rows(series))
    _write_account(tmp_path, 100_000.0)

    result = run_rotation_target_weight_mapping_for_spec(
        spec, rotation_config, _spec_path(tmp_path, spec.name), tmp_path, as_of=AS_OF_AUG27
    )

    assert result.manifest["selected"] == ["STRONG"]
    assert result.manifest["dropped_by_absolute_momentum"] == ["WEAK"]
    payload = _read_target_weights(tmp_path, spec.name)
    rows = {row["symbol"]: row for row in payload["target_weights"]}
    assert "WEAK" not in rows
    assert rows["STRONG"]["target_weight"] == pytest.approx(0.5)
    assert rows["CASHX"]["target_weight"] == pytest.approx(0.5)
    assert rows["CASHX"]["selected"] is True


# ---------------------------------------------------------------------------
# 3. ghost bars excluded


def test_ghost_bars_excluded_from_price_series(tmp_path: Path) -> None:
    real_dates = ALL_DATES[:10]
    _write_sip_daily(
        tmp_path, _sip_rows({"GBAR": _trend_series(real_dates, base=100.0, slope=0.001)})
    )
    ghost_day = date(2026, 8, 1)
    _write_sip_daily(tmp_path, _sip_rows({"GBAR": {ghost_day: 99_999.0}}, ghost=True))

    panel = load_price_panel(tmp_path, ["GBAR"], [2026], memory_limit="600MB", threads=2)

    dates_seen = set(panel.loc[panel["symbol"] == "GBAR", "trade_date"])
    assert ghost_day not in dates_seen
    assert dates_seen == set(real_dates)
    assert 99_999.0 not in set(panel["close"])


# ---------------------------------------------------------------------------
# 4. idempotence across three consecutive intra-period days


def test_idempotent_across_three_consecutive_days_inside_one_month(tmp_path: Path) -> None:
    _write_ranking_fixture(tmp_path)
    spec = _build_spec(name="rotation_idempotent")
    rotation_config = _ranking_config(rebalance="monthly_last_session", top_n=2)

    signal_sessions = []
    books = []
    for day in (3, 4, 5):
        result = run_rotation_target_weight_mapping_for_spec(
            spec,
            rotation_config,
            _spec_path(tmp_path, spec.name),
            tmp_path,
            as_of=datetime(2026, 8, day, 20, 0, tzinfo=UTC),
        )
        signal_sessions.append(result.manifest["signal_session"])
        payload = _read_target_weights(tmp_path, spec.name)
        books.append({row["symbol"]: row["target_weight"] for row in payload["target_weights"]})

    assert signal_sessions == ["2026-07-31", "2026-07-31", "2026-07-31"]
    assert books[0] == books[1] == books[2]


# ---------------------------------------------------------------------------
# 5. insufficient history -> ineligible, not a crash


def test_insufficient_history_marks_symbol_ineligible_not_crash(tmp_path: Path) -> None:
    spec = _build_spec(name="rotation_ineligible")
    rotation_config = _rotation_config(
        menu=["AAA", "BBB", "NEWCO"],
        cash_symbol="CASHX",
        lookbacks=[2, 3],
        top_n=2,
        rebalance="weekly_friday",
        absolute_momentum_filter=False,
        min_history_sessions=6,
    )
    newco_dates = [
        date(2026, 8, 17),
        date(2026, 8, 18),
        date(2026, 8, 19),
        date(2026, 8, 20),
        date(2026, 8, 21),
    ]
    series = {
        "AAA": _trend_series(ALL_DATES, base=100.0, slope=0.003),
        "BBB": _trend_series(ALL_DATES, base=50.0, slope=0.001),
        "CASHX": _trend_series(ALL_DATES, base=10.0, slope=0.0005),
        "NEWCO": _trend_series(newco_dates, base=20.0, slope=0.01),
    }
    _write_sip_daily(tmp_path, _sip_rows(series))
    _write_account(tmp_path, 100_000.0)

    result = run_rotation_target_weight_mapping_for_spec(
        spec,
        rotation_config,
        _spec_path(tmp_path, spec.name),
        tmp_path,
        as_of=datetime(2026, 8, 21, 20, 0, tzinfo=UTC),
    )

    assert result.manifest["signal_session"] == "2026-08-21"
    ineligible = {row["symbol"]: row["reason"] for row in result.manifest["ineligible"]}
    assert "NEWCO" in ineligible
    assert "insufficient history" in ineligible["NEWCO"]
    assert "NEWCO" not in result.manifest["selected"]
    assert set(result.manifest["selected"]) == {"AAA", "BBB"}


# ---------------------------------------------------------------------------
# 6. weekly_friday vs monthly_last_session pick different sessions


def test_weekly_friday_and_monthly_last_session_pick_different_sessions(tmp_path: Path) -> None:
    _write_ranking_fixture(tmp_path)

    spec_monthly = _build_spec(name="rotation_monthly")
    result_monthly = run_rotation_target_weight_mapping_for_spec(
        spec_monthly,
        _ranking_config(rebalance="monthly_last_session"),
        _spec_path(tmp_path, spec_monthly.name),
        tmp_path,
        as_of=AS_OF_AUG27,
    )

    spec_weekly = _build_spec(name="rotation_weekly")
    result_weekly = run_rotation_target_weight_mapping_for_spec(
        spec_weekly,
        _ranking_config(rebalance="weekly_friday"),
        _spec_path(tmp_path, spec_weekly.name),
        tmp_path,
        as_of=AS_OF_AUG27,
    )

    assert result_monthly.manifest["signal_session"] == "2026-07-31"
    assert result_weekly.manifest["signal_session"] == "2026-08-21"
    assert result_monthly.manifest["signal_session"] != result_weekly.manifest["signal_session"]


# ---------------------------------------------------------------------------
# 7. notional_budget_usd sizing cases


@pytest.mark.parametrize(
    ("notional_budget_usd", "expected_sizing_equity", "expected_binds"),
    [
        (40_000.0, 40_000.0, True),
        (200_000.0, 100_000.0, False),
        (None, 100_000.0, False),
    ],
)
def test_notional_budget_usd_caps_sizing_equity(
    tmp_path: Path,
    notional_budget_usd: float | None,
    expected_sizing_equity: float,
    expected_binds: bool,
) -> None:
    _write_ranking_fixture(tmp_path)
    spec = _build_spec(name="rotation_budget")
    rotation_config = _ranking_config(rebalance="monthly_last_session")
    rotation_config.notional_budget_usd = notional_budget_usd

    result = run_rotation_target_weight_mapping_for_spec(
        spec, rotation_config, _spec_path(tmp_path, spec.name), tmp_path, as_of=AS_OF_AUG27
    )

    assert result.manifest["account_equity"] == pytest.approx(100_000.0)
    assert result.manifest["sizing_equity"] == pytest.approx(expected_sizing_equity)
    assert result.manifest["notional_budget_binds"] is expected_binds
    payload = _read_target_weights(tmp_path, spec.name)
    rows = {row["symbol"]: row for row in payload["target_weights"]}
    assert rows["AAA"]["sizing_equity"] == pytest.approx(expected_sizing_equity)


# ---------------------------------------------------------------------------
# 8. period completion must come from the market calendar, not the archive


def test_weekly_friday_period_end_from_calendar_not_archive_latest_thursday() -> None:
    """A Thursday cron run must not treat "today" as the rebalance date just
    because it is the newest row the archive happens to contain -- Friday is
    a real (if not-yet-archived) trading day, so the previous Friday is the
    last *completed* week."""
    available = [
        date(2026, 9, 11),
        date(2026, 9, 14),
        date(2026, 9, 15),
        date(2026, 9, 16),
        date(2026, 9, 17),
    ]
    result = resolve_signal_session(available, "weekly_friday", latest_session=date(2026, 9, 17))
    assert result == date(2026, 9, 11)


def test_monthly_last_session_period_end_from_calendar_not_archive_latest_thursday() -> None:
    available = [
        date(2026, 8, 31),
        date(2026, 9, 14),
        date(2026, 9, 15),
        date(2026, 9, 16),
        date(2026, 9, 17),
    ]
    result = resolve_signal_session(
        available, "monthly_last_session", latest_session=date(2026, 9, 17)
    )
    assert result == date(2026, 8, 31)


def test_weekly_friday_period_end_when_latest_session_is_the_friday_itself() -> None:
    available = [
        date(2026, 9, 11),
        date(2026, 9, 14),
        date(2026, 9, 15),
        date(2026, 9, 16),
        date(2026, 9, 17),
        date(2026, 9, 18),
    ]
    result = resolve_signal_session(available, "weekly_friday", latest_session=date(2026, 9, 18))
    assert result == date(2026, 9, 18)


# ---------------------------------------------------------------------------
# 9. once the concurrent StrategySpec change lands, exercise the real field too


def _real_spec_supports_etf_rotation() -> bool:
    return "etf_rotation" in PortfolioConfig.model_fields


@pytest.mark.skipif(
    not _real_spec_supports_etf_rotation(),
    reason="portfolio.etf_rotation is not wired into the real StrategySpec yet",
)
def test_real_strategy_spec_etf_rotation_end_to_end_smoke(tmp_path: Path) -> None:
    _write_ranking_fixture(tmp_path)
    raw = yaml.safe_load(FIXTURE_SPEC.read_text(encoding="utf-8"))
    raw["name"] = "rotation_real_spec_smoke"
    raw["timeframe"] = "daily"
    raw["universe"] = ["SPY"]
    raw["data"]["source"] = "alpaca"
    raw["data"]["path"] = None
    raw["data"]["feed"] = "sip"
    raw["portfolio"] = {
        "mode": "etf_rotation_portfolio",
        "weighting": "equal_weight",
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "etf_rotation": {
            "menu": ["AAA", "BBB", "CCC", "DDD"],
            "cash_symbol": "CASHX",
            "lookbacks": [2, 3],
            "top_n": 2,
            "rebalance": "monthly_last_session",
            "absolute_momentum_filter": False,
            "min_history_sessions": 30,
        },
    }
    spec_path = _spec_path(tmp_path, raw["name"])
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    result = run_rotation_target_weight_mapping(spec_path, tmp_path, as_of=AS_OF_AUG27)

    assert result.manifest["signal_session"] == "2026-07-31"
    assert result.manifest["selected"] == ["AAA", "BBB"]


# ---------------------------------------------------------------------------
# 10. unfilled_slot_policy: what happens to a dropped pick's weight
#
# The preregistered grid on card H-20260918-05 renormalized among survivors, so
# the three shipped specs set renormalize_survivors explicitly. The model
# default stays the defensive per-slot-cash rule, because renormalizing
# concentrates exactly when the absolute-momentum filter is warning.


def test_build_weights_cash_policy_leaves_the_dropped_slot_in_cash() -> None:
    weights = build_weights(["STRONG"], top_n=2, cash_symbol="CASHX", unfilled_slot_policy="cash")
    assert weights == pytest.approx({"STRONG": 0.5, "CASHX": 0.5})


def test_build_weights_renormalize_gives_the_single_survivor_everything() -> None:
    weights = build_weights(
        ["STRONG"], top_n=2, cash_symbol="CASHX", unfilled_slot_policy="renormalize_survivors"
    )
    assert weights["STRONG"] == pytest.approx(1.0)
    assert weights["CASHX"] == pytest.approx(0.0)


def test_build_weights_policies_agree_when_every_slot_is_filled() -> None:
    picks = ["A", "B"]
    cash = build_weights(picks, top_n=2, cash_symbol="CASHX", unfilled_slot_policy="cash")
    renorm = build_weights(
        picks, top_n=2, cash_symbol="CASHX", unfilled_slot_policy="renormalize_survivors"
    )
    assert cash["A"] == pytest.approx(renorm["A"]) == pytest.approx(0.5)
    assert cash["B"] == pytest.approx(renorm["B"]) == pytest.approx(0.5)


def test_build_weights_empty_book_is_all_cash_under_both_policies() -> None:
    for policy in ("cash", "renormalize_survivors"):
        assert build_weights([], top_n=2, cash_symbol="CASHX", unfilled_slot_policy=policy) == {
            "CASHX": 1.0
        }


def test_build_weights_rejects_an_unknown_policy() -> None:
    with pytest.raises(ValueError, match="unfilled_slot_policy"):
        build_weights(["A"], top_n=2, cash_symbol="CASHX", unfilled_slot_policy="halve_it")


def test_renormalize_policy_end_to_end_puts_the_survivor_at_full_weight(tmp_path: Path) -> None:
    spec = _build_spec(name="rotation_renormalize")
    rotation_config = _rotation_config(
        menu=["WEAK", "STRONG"],
        cash_symbol="CASHX",
        lookbacks=[2, 3],
        top_n=2,
        rebalance="monthly_last_session",
        absolute_momentum_filter=True,
        min_history_sessions=6,
        unfilled_slot_policy="renormalize_survivors",
    )
    series = {
        "WEAK": _trend_series(ALL_DATES, base=40.0, slope=0.0003),
        "STRONG": _trend_series(ALL_DATES, base=60.0, slope=0.005),
        "CASHX": _trend_series(ALL_DATES, base=10.0, slope=0.0008),
    }
    _write_sip_daily(tmp_path, _sip_rows(series))
    _write_account(tmp_path, 100_000.0)

    result = run_rotation_target_weight_mapping_for_spec(
        spec, rotation_config, _spec_path(tmp_path, spec.name), tmp_path, as_of=AS_OF_AUG27
    )

    assert result.manifest["selected"] == ["STRONG"]
    assert result.manifest["dropped_by_absolute_momentum"] == ["WEAK"]
    assert result.manifest["unfilled_slot_policy"] == "renormalize_survivors"
    payload = _read_target_weights(tmp_path, spec.name)
    rows = {row["symbol"]: row for row in payload["target_weights"]}
    assert rows["STRONG"]["target_weight"] == pytest.approx(1.0)
    assert rows["CASHX"]["target_weight"] == pytest.approx(0.0)
