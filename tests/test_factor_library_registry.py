from __future__ import annotations

import json

from open_composer.research.factor_library import (
    ALL_FACTORS,
    all_factor_definitions,
    factor_definition_ids,
    get_factor_definition,
    list_factors,
    materialize_expression,
    write_factor_library_artifact,
)


def test_factor_library_ids_are_unique_and_include_core_router_factors() -> None:
    ids = factor_definition_ids()

    assert len(ids) == len(set(ids))
    assert "absolute_time_series_momentum_120" in ids
    assert "cross_sectional_relative_momentum_120" in ids
    assert "tech_canary_breadth" in ids
    assert "defensive_asset_dual_momentum" in ids
    assert "leveraged_etf_extension_guard" in ids
    assert "risk_on_recovery_boost" in ids
    assert "strong_risk_on_state" in ids
    assert "core_beta_sleeve" in ids
    assert "leadership_satellite_rank" in ids
    assert "stress_only_defensive_sleeve" in ids
    assert "post_drawdown_reentry_state" in ids
    assert "overextension_mean_reversion_guard" in ids
    assert "post_stress_cooldown_confirmation" in ids
    assert "melt_up_peak_risk_guard" in ids
    assert "early_deterioration_downshift" in ids
    assert "underlying_moving_average_leverage_gate" in ids
    assert "volatility_managed_leverage_state" in ids
    assert "momentum_crash_rebound_guard" in ids
    assert "overnight_intraday_return_split" in ids
    assert "open_gap_delay_confirmation" in ids
    assert "tqqq_delayed_entry_execution_overlay" in ids
    assert "overnight_first_half_hour_reversal_regime" in ids
    assert "late_day_intraday_momentum_pressure" in ids
    assert "pre_fomc_event_window_state" in ids


def test_factor_library_definitions_have_parameters_and_source_cards() -> None:
    for definition in all_factor_definitions():
        assert definition.id
        assert definition.family
        assert definition.default_parameter_space or "{" not in (definition.expression or "")
        assert definition.source_card_ids

    canary = get_factor_definition("tech_canary_breadth")

    assert canary.default_parameter_space["min_breadth"] == [2, 3, 4]
    assert "breadth" in canary.label.lower()

    core = get_factor_definition("core_beta_sleeve")

    assert core.default_parameter_space["core_weight_pct"] == [25.0, 40.0, 55.0]
    assert "cash" in " ".join(core.implementation_notes)

    cooldown = get_factor_definition("post_stress_cooldown_confirmation")

    assert cooldown.default_parameter_space["cooldown_days"] == [0, 5, 10, 20]
    assert "gross" in " ".join(cooldown.implementation_notes)

    melt_up = get_factor_definition("melt_up_peak_risk_guard")

    assert melt_up.default_parameter_space["momentum60_min_pct"] == [40.0, 60.0]
    assert "downshift" in " ".join(melt_up.implementation_notes)

    deterioration = get_factor_definition("early_deterioration_downshift")

    assert deterioration.default_parameter_space["tqqq_dd20_trigger_pct"] == [8.0, 9.0, 10.0]
    assert "QQQ" in str(deterioration.default_parameter_space["fallback_asset"])

    leverage_gate = get_factor_definition("underlying_moving_average_leverage_gate")

    assert "TQQQ" in str(leverage_gate.default_parameter_space["risk_on_tiers"])
    assert "cash" in " ".join(leverage_gate.implementation_notes)

    vol_state = get_factor_definition("volatility_managed_leverage_state")

    assert vol_state.default_parameter_space["high_vol_rank"] == [0.65, 0.75, 0.85]
    assert "cash" in " ".join(vol_state.implementation_notes)

    rebound_guard = get_factor_definition("momentum_crash_rebound_guard")

    assert rebound_guard.default_parameter_space["required_breadth"] == [1, 2, 3]

    overnight = get_factor_definition("overnight_intraday_return_split")

    assert overnight.family == "execution_timing"
    assert overnight.default_parameter_space["large_gap_pct"] == [1.0, 2.0, 3.0]

    open_gap = get_factor_definition("open_gap_delay_confirmation")

    assert open_gap.default_parameter_space["confirmation_minutes"] == [5, 15, 30]
    assert "intraday" in " ".join(open_gap.implementation_notes).lower()

    delayed_entry = get_factor_definition("tqqq_delayed_entry_execution_overlay")

    assert delayed_entry.default_parameter_space["delay_minutes"] == [5, 15, 30]
    assert "TQQQ" in str(delayed_entry.default_parameter_space["covered_symbols"])

    overnight_reversal = get_factor_definition("overnight_first_half_hour_reversal_regime")

    assert overnight_reversal.family == "execution_timing"
    assert overnight_reversal.default_parameter_space["confirmation_minutes"] == [15, 30]
    assert "100%" in " ".join(overnight_reversal.implementation_notes)

    late_day_pressure = get_factor_definition("late_day_intraday_momentum_pressure")

    assert late_day_pressure.default_parameter_space["window_minutes"] == [30, 60]
    assert "next-session" in " ".join(late_day_pressure.implementation_notes)

    transition_gld = get_factor_definition("transition_gld_momentum_overlay")

    assert transition_gld.family == "defensive_transition"
    assert transition_gld.default_parameter_space["lookback_days"] == [20, 60]
    assert "100%" in " ".join(transition_gld.implementation_notes)

    pre_fomc = get_factor_definition("pre_fomc_event_window_state")

    assert pre_fomc.family == "event_calendar"
    assert "point-in-time" in " ".join(pre_fomc.implementation_notes)


def test_factor_library_catalog_meets_step6_size_and_expression_targets() -> None:
    assert len(ALL_FACTORS) >= 80
    assert len([definition for definition in ALL_FACTORS if definition.expression]) >= 70
    assert len({definition.family for definition in ALL_FACTORS}) >= 15
    assert get_factor_definition("alpha101_001_neg_delta_close_1d").expression
    assert get_factor_definition("alpha158_overnight_gap").expression


def test_materialize_expression_uses_defaults_and_params() -> None:
    factor = get_factor_definition("absolute_time_series_momentum_120")

    assert materialize_expression(factor, {}) == "(close - lag(close, 60)) / lag(close, 60)"
    assert materialize_expression(factor, {"lookback_days": 120}) == (
        "(close - lag(close, 120)) / lag(close, 120)"
    )


def test_list_factors_filters_by_family_and_inputs() -> None:
    factors = list_factors(family="overnight_gap", inputs={"open", "close"}, expression_only=True)

    ids = {factor.id for factor in factors}
    assert "alpha158_overnight_gap" in ids
    assert all(set(factor.inputs).issubset({"open", "close"}) for factor in factors)


def test_write_factor_library_artifact(tmp_path) -> None:
    json_path, md_path = write_factor_library_artifact(
        strategy_name="router",
        factor_ids=[
            "absolute_time_series_momentum_120",
            "tech_canary_breadth",
            "leveraged_etf_extension_guard",
        ],
        root=tmp_path,
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert payload["strategy_name"] == "router"
    assert payload["factor_count"] == 3
    assert payload["factor_ids"] == [
        "absolute_time_series_momentum_120",
        "tech_canary_breadth",
        "leveraged_etf_extension_guard",
    ]
    assert md_path.exists()
