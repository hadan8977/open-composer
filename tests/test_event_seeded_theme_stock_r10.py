from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.event_seeded_theme_stock_r10 import (
    BENCHMARK_SYMBOLS,
    compute_r10_d01_targets,
    compute_r10_d02_targets,
    validate_r10_runtime_panel,
    validate_r10_spec_pair,
)


@pytest.fixture(scope="module")
def r10_specs() -> tuple[StrategySpec, StrategySpec]:
    return (
        load_strategy_spec("strategy_specs/drafts/us_event_seeded_theme_stock_r10_d01.yaml"),
        load_strategy_spec("strategy_specs/drafts/us_event_seeded_theme_stock_r10_d02.yaml"),
    )


@pytest.fixture(scope="module")
def r10_panel(r10_specs):
    d01, _d02 = r10_specs
    panel = _event_rotation_panel(d01)
    targets, records = compute_r10_d01_targets(
        panel["opens"],
        panel["closes"],
        panel["volumes"],
        panel["membership"],
        d01,
    )
    return {**panel, "targets": targets, "records": records}


def test_r10_specs_bind_event_seeded_dynamic_membership(r10_specs) -> None:
    d01, d02 = r10_specs

    validate_r10_spec_pair(d01, d02)

    payload = d01.model_dump(mode="json")
    payload["notes"]["event_theme_discovery"]["semantic_labels_selectable"] = True
    changed = StrategySpec.model_validate(payload)
    with pytest.raises(ValueError, match="dynamic-universe identity"):
        validate_r10_spec_pair(changed, d02)


def test_r10_d01_compute_rejects_changed_hysteresis_contract(r10_specs, r10_panel) -> None:
    d01, _d02 = r10_specs
    payload = d01.model_dump(mode="json")
    payload["notes"]["hysteresis"]["maximum_member_substitutions_per_rebalance"] = 2
    changed = StrategySpec.model_validate(payload)

    with pytest.raises(ValueError, match="portfolio-hysteresis contract changed"):
        compute_r10_d01_targets(
            r10_panel["opens"],
            r10_panel["closes"],
            r10_panel["volumes"],
            r10_panel["membership"],
            changed,
        )


def test_r10_d02_compute_rejects_changed_beta_contract(r10_specs, r10_panel) -> None:
    _d01, d02 = r10_specs
    payload = d02.model_dump(mode="json")
    payload["notes"]["beta_state"]["minimum_state_days"] = 4
    changed = StrategySpec.model_validate(payload)

    with pytest.raises(ValueError, match="aggressive-beta contract changed"):
        compute_r10_d02_targets(
            r10_panel["opens"],
            r10_panel["closes"],
            r10_panel["volumes"],
            r10_panel["membership"],
            changed,
        )


def test_r10_event_themes_rotate_across_symbols_not_in_static_spec(r10_specs, r10_panel) -> None:
    d01, _d02 = r10_specs
    targets = r10_panel["targets"]
    records = r10_panel["records"]
    early = set(r10_panel["early"])
    late = set(r10_panel["late"])
    runtime_symbols = set(r10_panel["membership"].columns)

    assert runtime_symbols.isdisjoint(d01.universe)
    assert np.allclose(targets.sum(axis=1), 1.0)
    assert float(targets[list(runtime_symbols)].max().max()) <= 0.15 + 1e-12
    assert float(targets[list(runtime_symbols)].sum(axis=1).max()) <= 0.40 + 1e-12

    early_rows = [row for row in records if early & set(row["selected_symbols"])]
    late_rows = [row for row in records if late & set(row["selected_symbols"])]
    assert early_rows
    assert late_rows
    assert pd.Timestamp(early_rows[0]["decision_session"]) < pd.Timestamp(
        late_rows[0]["decision_session"]
    )
    assert "FUTURE_IPO" not in {symbol for row in records for symbol in row["selected_symbols"]}

    states = {theme["state"] for row in records for theme in row["themes"]}
    assert {"formation", "confirmed", "cooldown"}.issubset(states)


def test_r10_formation_has_no_same_session_stock_allocation(r10_panel) -> None:
    event_position = r10_panel["early_event_position"]
    event_session = r10_panel["closes"].index[event_position].date().isoformat()
    row = next(
        record for record in r10_panel["records"] if record["decision_session"] == event_session
    )
    stock_symbols = list(r10_panel["membership"].columns)

    assert row["event_seeds"]
    assert any(theme["state"] == "formation" for theme in row["themes"])
    assert sum(float(row["weights"][symbol]) for symbol in stock_symbols) == pytest.approx(0.0)


def test_r10_non_rebalance_sessions_hold_prior_target(r10_panel) -> None:
    targets = r10_panel["targets"]
    records = r10_panel["records"]

    for position in range(1, len(records)):
        if records[position]["is_rebalance_decision"]:
            continue
        pd.testing.assert_series_equal(
            targets.iloc[position],
            targets.iloc[position - 1],
            check_names=False,
        )


def test_r10_future_changes_do_not_change_existing_target(r10_specs, r10_panel) -> None:
    d01, _d02 = r10_specs
    pivot = next(
        row
        for row in r10_panel["records"]
        if set(row["selected_symbols"]) & set(r10_panel["early"])
    )
    decision = pd.Timestamp(pivot["decision_session"])
    execution = pd.Timestamp(pivot["execution_session"])
    changed_opens = r10_panel["opens"].copy()
    changed_closes = r10_panel["closes"].copy()
    changed_volumes = r10_panel["volumes"].copy()
    changed_membership = r10_panel["membership"].copy()
    future = changed_closes.index > decision
    stock_symbols = list(changed_membership.columns)
    scale = pd.Series(
        np.linspace(0.7, 1.8, len(stock_symbols)),
        index=stock_symbols,
    )
    changed_opens.loc[future, stock_symbols] = changed_opens.loc[future, stock_symbols].mul(
        scale, axis=1
    )
    changed_closes.loc[future, stock_symbols] = changed_closes.loc[future, stock_symbols].mul(
        scale, axis=1
    )
    changed_volumes.loc[future, stock_symbols] = changed_volumes.loc[future, stock_symbols] * 3.0

    changed_targets, changed_records = compute_r10_d01_targets(
        changed_opens,
        changed_closes,
        changed_volumes,
        changed_membership,
        d01,
    )
    changed_by_execution = {pd.Timestamp(row["execution_session"]): row for row in changed_records}

    pd.testing.assert_series_equal(
        r10_panel["targets"].loc[execution],
        changed_targets.loc[execution],
    )
    assert pivot["target_sha256"] == changed_by_execution[execution]["target_sha256"]


def test_r10_d02_is_independent_of_stock_theme_inputs(r10_specs, r10_panel) -> None:
    _d01, d02 = r10_specs
    baseline, records = compute_r10_d02_targets(
        r10_panel["opens"],
        r10_panel["closes"],
        r10_panel["volumes"],
        r10_panel["membership"],
        d02,
    )
    changed_opens = r10_panel["opens"].copy()
    changed_closes = r10_panel["closes"].copy()
    changed_volumes = r10_panel["volumes"].copy()
    stock_symbols = list(r10_panel["membership"].columns)
    changed_opens[stock_symbols] *= 1.7
    changed_closes[stock_symbols] *= 0.8
    changed_volumes[stock_symbols] *= 5.0
    changed, _changed_records = compute_r10_d02_targets(
        changed_opens,
        changed_closes,
        changed_volumes,
        r10_panel["membership"],
        d02,
    )

    pd.testing.assert_frame_equal(baseline, changed)
    assert {row["state"] for row in records} <= {"risk_on", "caution", "stress"}
    nonzero_symbols = set(baseline.columns[(baseline > 0).any(axis=0)])
    assert nonzero_symbols <= {"TQQQ", "QQQ", "BIL"}


def test_r10_missing_prelisting_bars_fail_if_membership_is_spoofed_true(
    r10_specs, r10_panel
) -> None:
    d01, _d02 = r10_specs
    spoofed = r10_panel["membership"].copy()
    first_session = spoofed.index[0]
    spoofed.at[first_session, "FUTURE_IPO"] = True

    with pytest.raises(ValueError, match="active membership bar is invalid"):
        validate_r10_runtime_panel(
            r10_panel["opens"],
            r10_panel["closes"],
            r10_panel["volumes"],
            spoofed,
            d01,
        )


def _event_rotation_panel(spec: StrategySpec, session_count: int = 205):
    rng = np.random.default_rng(101001)
    sessions = pd.bdate_range("2025-01-02", periods=session_count)
    early = tuple(f"EARLY_{index}" for index in range(4))
    late = tuple(f"LATE_{index}" for index in range(4))
    others = tuple(f"OTHER_{index}" for index in range(4))
    candidates = (*early, *late, *others, "FUTURE_IPO")
    benchmarks = tuple(symbol for symbol in spec.universe if symbol in BENCHMARK_SYMBOLS)

    early_event = next(
        position for position in range(108, 125) if sessions[position].weekday() == 1
    )
    late_event = next(position for position in range(150, 170) if sessions[position].weekday() == 1)
    market = rng.normal(0.00075, 0.0030, session_count)
    qqq_return = 0.0009 + 0.65 * market + rng.normal(0.0, 0.0018, session_count)
    early_driver = rng.normal(0.0001, 0.0065, session_count)
    late_driver = rng.normal(0.0001, 0.0065, session_count)
    early_driver[early_event] = 0.080
    late_driver[late_event] = 0.085

    returns: dict[str, np.ndarray] = {}
    returns[early[0]] = 0.20 * market + early_driver
    returns[late[0]] = 0.20 * market + late_driver
    for symbol in early[1:]:
        values = 0.20 * market + 0.85 * np.roll(early_driver, 1) + 0.0010
        values[0] = 0.0010
        returns[symbol] = values + rng.normal(0.0, 0.0015, session_count)
    for symbol in late[1:]:
        values = 0.20 * market + 0.85 * np.roll(late_driver, 1) + 0.0010
        values[0] = 0.0010
        returns[symbol] = values + rng.normal(0.0, 0.0015, session_count)
    for index, symbol in enumerate(others):
        returns[symbol] = 0.25 * market + rng.normal(
            0.0001 + index * 0.00001, 0.0075, session_count
        )
    returns["FUTURE_IPO"] = 0.30 * market + rng.normal(0.0003, 0.0080, session_count)
    returns.update(
        {
            "BIL": np.full(session_count, 0.00012),
            "QQQ": qqq_return,
            "QLD": np.clip(2.0 * qqq_return, -0.20, 0.20),
            "TQQQ": np.clip(3.0 * qqq_return, -0.30, 0.30),
            "SPY": market,
        }
    )
    columns = [*candidates, *benchmarks]
    closes = pd.DataFrame(
        {
            symbol: 100.0 * np.cumprod(1.0 + np.clip(returns[symbol], -0.30, 0.30))
            for symbol in columns
        },
        index=sessions,
    )
    gap_values = pd.DataFrame(
        rng.normal(0.0001, 0.0020, (session_count, len(columns))),
        index=sessions,
        columns=columns,
    )
    gap_values.at[sessions[early_event], early[0]] = 0.035
    gap_values.at[sessions[late_event], late[0]] = 0.040
    opens = closes.shift(1) * (1.0 + gap_values)
    opens.iloc[0] = closes.iloc[0] * 0.999
    volumes = pd.DataFrame(
        {symbol: 2_000_000.0 * np.exp(rng.normal(0.0, 0.08, session_count)) for symbol in columns},
        index=sessions,
    )
    volumes.at[sessions[early_event], early[0]] *= 4.0
    volumes.at[sessions[late_event], late[0]] *= 4.0

    membership = pd.DataFrame(True, index=sessions, columns=candidates, dtype=bool)
    listing_position = 180
    membership.loc[sessions[: listing_position - 1], "FUTURE_IPO"] = False
    opens.loc[sessions[: listing_position - 1], "FUTURE_IPO"] = np.nan
    closes.loc[sessions[: listing_position - 1], "FUTURE_IPO"] = np.nan
    volumes.loc[sessions[: listing_position - 1], "FUTURE_IPO"] = np.nan
    return {
        "opens": opens,
        "closes": closes,
        "volumes": volumes,
        "membership": membership,
        "early": early,
        "late": late,
        "early_event_position": early_event,
        "late_event_position": late_event,
    }
