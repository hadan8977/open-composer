"""Consolidated, parametrized replacement for the per-round
``test_rNN_features_labels_and_embargo_use_registered_timing`` tests
that were copy-pasted across ``test_pit_semantic_theme_r14.py`` .. ``r22.py``.

Each round mutated the feature/label contract slightly (new recovery-boost
inputs, USD stress-pressure gating, D01 routing, ...), so the assertion
bodies genuinely differ round to round -- they are preserved verbatim here
(only renamed to reference the round module via its import alias) and
dispatched from a single parametrized test so pytest collects one test
per round without duplicating the setup boilerplate as a new top-level
test function in each per-round module.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

import open_composer.research.pit_semantic_theme_r14 as r14
import open_composer.research.pit_semantic_theme_r15 as r15
import open_composer.research.pit_semantic_theme_r16 as r16
import open_composer.research.pit_semantic_theme_r17 as r17
import open_composer.research.pit_semantic_theme_r18 as r18
import open_composer.research.pit_semantic_theme_r19 as r19
import open_composer.research.pit_semantic_theme_r20 as r20
import open_composer.research.pit_semantic_theme_r21 as r21
import open_composer.research.pit_semantic_theme_r22 as r22

ROOT = Path(__file__).resolve().parents[1]


def _case_r14() -> None:
    panel = r14.load_r14_price_panel(ROOT)
    specs = r14.load_and_validate_r14_specs(ROOT)
    dataset = r14.build_r14_feature_dataset(panel)
    folds = r14.development_folds(panel.open.index)
    point = dataset[dataset["execution_session"] >= folds[0]["test_start"]].iloc[0]
    position = int(point["decision_position"])

    assert int(point["execution_position"]) == position + 1
    assert int(point["m01_label_end_position"]) == position + 21
    assert int(point["m02_label_end_position"]) == position + 11
    assert point["qqq_momentum_20"] == (
        panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 20]["QQQ"] - 1.0
    )
    expected_leadership = bool(
        panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 60]["SMH"] - 1.0 > 0.0
        and panel.close.iloc[position]["SMH"]
        / panel.close["SMH"].iloc[position - 149 : position + 1].mean()
        - 1.0
        > 0.0
        and panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 120]["SMH"]
        > panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"]
        and panel.close.iloc[position]["SOXL"] / panel.close.iloc[position - 20]["SOXL"] - 1.0 > 0.0
        and panel.close.iloc[position]["SOXL"]
        / panel.close["SOXL"].iloc[position - 99 : position + 1].mean()
        - 1.0
        > 0.0
    )
    assert bool(point["semiconductor_leadership"]) is expected_leadership

    labelled = dataset[dataset["m01_barbell_label"].notna()].iloc[0]
    execution_position = int(labelled["execution_position"])
    label_end_position = int(labelled["m01_label_end_position"])
    tqqq_return = (
        panel.open.iloc[label_end_position]["TQQQ"] / panel.open.iloc[execution_position]["TQQQ"]
        - 1.0
    )
    soxl_return = (
        panel.open.iloc[label_end_position]["SOXL"] / panel.open.iloc[execution_position]["SOXL"]
        - 1.0
    )
    barbell_return = (
        r14.LEADERSHIP_WEIGHTS["SOXL"] * soxl_return + r14.LEADERSHIP_WEIGHTS["TQQQ"] * tqqq_return
    )
    assert labelled["m01_barbell_label"] == float(
        barbell_return - tqqq_return - r14.INCREMENTAL_OVERRIDE_COST > 0.0
    )

    for candidate_id, label_name, terminal_column in (
        ("R14M01", "m01_barbell_label", "m01_label_end_position"),
        ("R14M02", "m02_survival_label", "m02_label_end_position"),
    ):
        train = r14.training_rows_for_r14_prediction(
            dataset,
            decision_position=position,
            spec=specs[candidate_id],
            label_name=label_name,
        )
        assert not train.empty
        assert int(train[terminal_column].max()) <= position - 21
        assert train[label_name].isin([0.0, 1.0]).all()


def _case_r15() -> None:
    panel = r15.load_r15_price_panel(ROOT)
    specs = r15.load_and_validate_r15_specs(ROOT)
    dataset = r15.build_r15_feature_dataset(panel)
    folds = r15.development_folds(panel.open.index)
    point = dataset[dataset["execution_session"] >= folds[0]["test_start"]].iloc[0]
    position = int(point["decision_position"])

    assert int(point["execution_position"]) == position + 1
    assert int(point["m01_label_end_position"]) == position + 21
    assert int(point["m02_label_end_position"]) == position + 11
    assert point["qqq_momentum_20"] == (
        panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 20]["QQQ"] - 1.0
    )
    expected_leadership = bool(
        panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 60]["SMH"] - 1.0 > 0.0
        and panel.close.iloc[position]["SMH"]
        / panel.close["SMH"].iloc[position - 149 : position + 1].mean()
        - 1.0
        > 0.0
        and panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 120]["SMH"]
        > panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"]
        and panel.close.iloc[position]["SOXL"] / panel.close.iloc[position - 20]["SOXL"] - 1.0 > 0.0
        and panel.close.iloc[position]["SOXL"]
        / panel.close["SOXL"].iloc[position - 99 : position + 1].mean()
        - 1.0
        > 0.0
    )
    assert bool(point["semiconductor_leadership"]) is expected_leadership

    labelled = dataset[dataset["m01_soxl100_label"].notna()].iloc[0]
    execution_position = int(labelled["execution_position"])
    label_end_position = int(labelled["m01_label_end_position"])
    tqqq_return = (
        panel.open.iloc[label_end_position]["TQQQ"] / panel.open.iloc[execution_position]["TQQQ"]
        - 1.0
    )
    soxl_return = (
        panel.open.iloc[label_end_position]["SOXL"] / panel.open.iloc[execution_position]["SOXL"]
        - 1.0
    )
    leadership_return = (
        r15.LEADERSHIP_WEIGHTS["SOXL"] * soxl_return
        + r15.LEADERSHIP_WEIGHTS.get("TQQQ", 0.0) * tqqq_return
    )
    assert labelled["m01_soxl100_label"] == float(
        leadership_return - tqqq_return - r15.INCREMENTAL_OVERRIDE_COST > 0.0
    )

    for candidate_id, label_name, terminal_column in (
        ("R15M01", "m01_soxl100_label", "m01_label_end_position"),
        ("R15M02", "m02_survival_label", "m02_label_end_position"),
    ):
        train = r15.training_rows_for_r15_prediction(
            dataset,
            decision_position=position,
            spec=specs[candidate_id],
            label_name=label_name,
        )
        assert not train.empty
        assert int(train[terminal_column].max()) <= position - 21
        assert train[label_name].isin([0.0, 1.0]).all()


def _case_r16() -> None:
    panel = r16.load_r16_price_panel(ROOT)
    specs = r16.load_and_validate_r16_specs(ROOT)
    dataset = r16.build_r16_feature_dataset(panel)
    folds = r16.development_folds(panel.open.index)
    point = dataset[dataset["execution_session"] >= folds[0]["test_start"]].iloc[0]
    position = int(point["decision_position"])

    assert int(point["execution_position"]) == position + 1
    assert int(point["m01_label_end_position"]) == position + 21
    assert int(point["m02_label_end_position"]) == position + 11
    assert point["qqq_momentum_20"] == (
        panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 20]["QQQ"] - 1.0
    )
    expected_leadership = bool(
        panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 60]["SMH"] - 1.0 > 0.0
        and panel.close.iloc[position]["SMH"]
        / panel.close["SMH"].iloc[position - 149 : position + 1].mean()
        - 1.0
        > 0.0
        and panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 120]["SMH"]
        > panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"]
        and panel.close.iloc[position]["SOXL"] / panel.close.iloc[position - 20]["SOXL"] - 1.0 > 0.0
        and panel.close.iloc[position]["SOXL"]
        / panel.close["SOXL"].iloc[position - 99 : position + 1].mean()
        - 1.0
        > 0.0
    )
    assert bool(point["semiconductor_leadership"]) is expected_leadership

    labelled = dataset[dataset["m01_soxl100_label"].notna()].iloc[0]
    execution_position = int(labelled["execution_position"])
    label_end_position = int(labelled["m01_label_end_position"])
    tqqq_return = (
        panel.open.iloc[label_end_position]["TQQQ"] / panel.open.iloc[execution_position]["TQQQ"]
        - 1.0
    )
    soxl_return = (
        panel.open.iloc[label_end_position]["SOXL"] / panel.open.iloc[execution_position]["SOXL"]
        - 1.0
    )
    leadership_return = (
        r16.LEADERSHIP_WEIGHTS["SOXL"] * soxl_return
        + r16.LEADERSHIP_WEIGHTS.get("TQQQ", 0.0) * tqqq_return
    )
    assert labelled["m01_soxl100_label"] == float(
        leadership_return - tqqq_return - r16.INCREMENTAL_OVERRIDE_COST > 0.0
    )

    for candidate_id, label_name, terminal_column in (
        ("R16M01", "m01_soxl100_label", "m01_label_end_position"),
        ("R16M02", "m02_survival_label", "m02_label_end_position"),
    ):
        train = r16.training_rows_for_r16_prediction(
            dataset,
            decision_position=position,
            spec=specs[candidate_id],
            label_name=label_name,
        )
        assert not train.empty
        assert int(train[terminal_column].max()) <= position - 21
        assert train[label_name].isin([0.0, 1.0]).all()


def _case_r17() -> None:
    panel = r17.load_r17_price_panel(ROOT)
    specs = r17.load_and_validate_r17_specs(ROOT)
    dataset = r17.build_r17_feature_dataset(panel)
    folds = r17.development_folds(panel.open.index)
    point = dataset[dataset["execution_session"] >= folds[0]["test_start"]].iloc[0]
    position = int(point["decision_position"])

    assert int(point["execution_position"]) == position + 1
    assert int(point["m01_label_end_position"]) == position + 21
    assert int(point["m02_label_end_position"]) == position + 11
    assert point["qqq_momentum_20"] == (
        panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 20]["QQQ"] - 1.0
    )
    expected_qqq_trend_50 = (
        panel.close.iloc[position]["QQQ"]
        / panel.close["QQQ"]
        .iloc[position - r17.RECOVERY_QQQ_TREND_SESSIONS + 1 : position + 1]
        .mean()
        - 1.0
    )
    expected_tqqq_momentum_10 = (
        panel.close.iloc[position]["TQQQ"]
        / panel.close.iloc[position - r17.RECOVERY_TQQQ_MOMENTUM_SESSIONS]["TQQQ"]
        - 1.0
    )
    expected_breadth_count = sum(
        panel.close.iloc[position][symbol]
        > panel.close[symbol]
        .iloc[position - r17.RECOVERY_BREADTH_TREND_SESSIONS + 1 : position + 1]
        .mean()
        for symbol in ("QQQ", "XLK", "IGV", "SOXX", "SMH")
    )
    expected_risk_on = bool(
        panel.close.iloc[position]["QQQ"]
        > panel.close["QQQ"].iloc[position - 199 : position + 1].mean()
        or panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"] - 1.0 > 0.0
    )
    expected_recovery = bool(
        not expected_risk_on
        and expected_qqq_trend_50 > 0.0
        and expected_tqqq_momentum_10 >= r17.RECOVERY_TQQQ_MOMENTUM_MIN
        and expected_breadth_count >= r17.RECOVERY_BREADTH_MIN_COUNT
    )
    assert point["qqq_trend_gap_50"] == expected_qqq_trend_50
    assert point["tqqq_momentum_10"] == expected_tqqq_momentum_10
    assert int(point["tech_breadth_count_100"]) == expected_breadth_count
    assert bool(point["recovery_boost"]) is expected_recovery
    expected_leadership = bool(
        panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 60]["SMH"] - 1.0 > 0.0
        and panel.close.iloc[position]["SMH"]
        / panel.close["SMH"].iloc[position - 149 : position + 1].mean()
        - 1.0
        > 0.0
        and panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 120]["SMH"]
        > panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"]
        and panel.close.iloc[position]["SOXL"] / panel.close.iloc[position - 20]["SOXL"] - 1.0 > 0.0
        and panel.close.iloc[position]["SOXL"]
        / panel.close["SOXL"].iloc[position - 99 : position + 1].mean()
        - 1.0
        > 0.0
    )
    assert bool(point["semiconductor_leadership"]) is expected_leadership

    labelled = dataset[dataset["m01_soxl100_label"].notna()].iloc[0]
    execution_position = int(labelled["execution_position"])
    label_end_position = int(labelled["m01_label_end_position"])
    tqqq_return = (
        panel.open.iloc[label_end_position]["TQQQ"] / panel.open.iloc[execution_position]["TQQQ"]
        - 1.0
    )
    soxl_return = (
        panel.open.iloc[label_end_position]["SOXL"] / panel.open.iloc[execution_position]["SOXL"]
        - 1.0
    )
    leadership_return = (
        r17.LEADERSHIP_WEIGHTS["SOXL"] * soxl_return
        + r17.LEADERSHIP_WEIGHTS.get("TQQQ", 0.0) * tqqq_return
    )
    assert labelled["m01_soxl100_label"] == float(
        leadership_return - tqqq_return - r17.INCREMENTAL_OVERRIDE_COST > 0.0
    )

    for candidate_id, label_name, terminal_column in (
        ("R17M01", "m01_soxl100_label", "m01_label_end_position"),
        ("R17M02", "m02_survival_label", "m02_label_end_position"),
    ):
        train = r17.training_rows_for_r17_prediction(
            dataset,
            decision_position=position,
            spec=specs[candidate_id],
            label_name=label_name,
        )
        assert not train.empty
        assert int(train[terminal_column].max()) <= position - 21
        assert train[label_name].isin([0.0, 1.0]).all()


def _case_r18() -> None:
    panel = r18.load_r18_price_panel(ROOT)
    specs = r18.load_and_validate_r18_specs(ROOT)
    dataset = r18.build_r18_feature_dataset(panel)
    folds = r18.development_folds(panel.open.index)
    point = dataset[dataset["execution_session"] >= folds[0]["test_start"]].iloc[0]
    position = int(point["decision_position"])

    assert int(point["execution_position"]) == position + 1
    assert int(point["m01_label_end_position"]) == position + 21
    assert int(point["m02_label_end_position"]) == position + 11
    assert point["qqq_momentum_20"] == (
        panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 20]["QQQ"] - 1.0
    )
    expected_qqq_trend_50 = (
        panel.close.iloc[position]["QQQ"]
        / panel.close["QQQ"]
        .iloc[position - r18.RECOVERY_QQQ_TREND_SESSIONS + 1 : position + 1]
        .mean()
        - 1.0
    )
    expected_tqqq_momentum_10 = (
        panel.close.iloc[position]["TQQQ"]
        / panel.close.iloc[position - r18.RECOVERY_TQQQ_MOMENTUM_SESSIONS]["TQQQ"]
        - 1.0
    )
    expected_breadth_count = sum(
        panel.close.iloc[position][symbol]
        > panel.close[symbol]
        .iloc[position - r18.RECOVERY_BREADTH_TREND_SESSIONS + 1 : position + 1]
        .mean()
        for symbol in ("QQQ", "XLK", "IGV", "SOXX", "SMH")
    )
    expected_risk_on = bool(
        panel.close.iloc[position]["QQQ"]
        > panel.close["QQQ"].iloc[position - 199 : position + 1].mean()
        or panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"] - 1.0 > 0.0
    )
    expected_recovery = bool(
        not expected_risk_on
        and expected_qqq_trend_50 > 0.0
        and expected_tqqq_momentum_10 >= r18.RECOVERY_TQQQ_MOMENTUM_MIN
        and expected_breadth_count >= r18.RECOVERY_BREADTH_MIN_COUNT
    )
    assert point["qqq_trend_gap_50"] == expected_qqq_trend_50
    assert point["tqqq_momentum_10"] == expected_tqqq_momentum_10
    assert int(point["tech_breadth_count_100"]) == expected_breadth_count
    assert bool(point["recovery_boost"]) is expected_recovery
    expected_leadership = bool(
        panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 60]["SMH"] - 1.0 > 0.0
        and panel.close.iloc[position]["SMH"]
        / panel.close["SMH"].iloc[position - 149 : position + 1].mean()
        - 1.0
        > 0.0
        and panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 120]["SMH"]
        > panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"]
        and panel.close.iloc[position]["USD"] / panel.close.iloc[position - 20]["USD"] - 1.0 > 0.0
        and panel.close.iloc[position]["USD"]
        / panel.close["USD"].iloc[position - 99 : position + 1].mean()
        - 1.0
        > 0.0
    )
    assert bool(point["semiconductor_leadership"]) is expected_leadership

    labelled = dataset[dataset["m01_usd100_label"].notna()].iloc[0]
    execution_position = int(labelled["execution_position"])
    label_end_position = int(labelled["m01_label_end_position"])
    tqqq_return = (
        panel.open.iloc[label_end_position]["TQQQ"] / panel.open.iloc[execution_position]["TQQQ"]
        - 1.0
    )
    usd_return = (
        panel.open.iloc[label_end_position]["USD"] / panel.open.iloc[execution_position]["USD"]
        - 1.0
    )
    leadership_return = (
        r18.LEADERSHIP_WEIGHTS["USD"] * usd_return
        + r18.LEADERSHIP_WEIGHTS.get("TQQQ", 0.0) * tqqq_return
    )
    assert labelled["m01_usd100_label"] == float(
        leadership_return - tqqq_return - r18.INCREMENTAL_OVERRIDE_COST > 0.0
    )

    for candidate_id, label_name, terminal_column in (
        ("R18M01", "m01_usd100_label", "m01_label_end_position"),
        ("R18M02", "m02_survival_label", "m02_label_end_position"),
    ):
        train = r18.training_rows_for_r18_prediction(
            dataset,
            decision_position=position,
            spec=specs[candidate_id],
            label_name=label_name,
        )
        assert not train.empty
        assert int(train[terminal_column].max()) <= position - 21
        assert train[label_name].isin([0.0, 1.0]).all()


def _case_r19() -> None:
    panel = r19.load_r19_price_panel(ROOT)
    specs = r19.load_and_validate_r19_specs(ROOT)
    dataset = r19.build_r19_feature_dataset(panel)
    _, d01_records = r19.build_r19_d01_targets(panel, specs["R19D01"], dataset)
    folds = r19.development_folds(panel.open.index)
    point = dataset[dataset["execution_session"] >= folds[0]["test_start"]].iloc[0]
    position = int(point["decision_position"])

    assert int(point["execution_position"]) == position + 1
    assert int(point["m01_label_end_position"]) == position + 21
    assert int(point["m02_label_end_position"]) == position + 11
    assert point["qqq_momentum_20"] == (
        panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 20]["QQQ"] - 1.0
    )
    expected_qqq_trend_50 = (
        panel.close.iloc[position]["QQQ"]
        / panel.close["QQQ"]
        .iloc[position - r19.RECOVERY_QQQ_TREND_SESSIONS + 1 : position + 1]
        .mean()
        - 1.0
    )
    expected_tqqq_momentum_10 = (
        panel.close.iloc[position]["TQQQ"]
        / panel.close.iloc[position - r19.RECOVERY_TQQQ_MOMENTUM_SESSIONS]["TQQQ"]
        - 1.0
    )
    expected_breadth_count = sum(
        panel.close.iloc[position][symbol]
        > panel.close[symbol]
        .iloc[position - r19.RECOVERY_BREADTH_TREND_SESSIONS + 1 : position + 1]
        .mean()
        for symbol in ("QQQ", "XLK", "IGV", "SOXX", "SMH")
    )
    expected_risk_on = bool(
        panel.close.iloc[position]["QQQ"]
        > panel.close["QQQ"].iloc[position - 199 : position + 1].mean()
        or panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"] - 1.0 > 0.0
    )
    expected_recovery = bool(
        not expected_risk_on
        and expected_qqq_trend_50 > 0.0
        and expected_tqqq_momentum_10 >= r19.RECOVERY_TQQQ_MOMENTUM_MIN
        and expected_breadth_count >= r19.RECOVERY_BREADTH_MIN_COUNT
    )
    assert point["qqq_trend_gap_50"] == expected_qqq_trend_50
    assert point["tqqq_momentum_10"] == expected_tqqq_momentum_10
    assert int(point["tech_breadth_count_100"]) == expected_breadth_count
    assert bool(point["recovery_boost"]) is expected_recovery
    expected_leadership = bool(
        panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 60]["SMH"] - 1.0 > 0.0
        and panel.close.iloc[position]["SMH"]
        / panel.close["SMH"].iloc[position - 149 : position + 1].mean()
        - 1.0
        > 0.0
        and panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 120]["SMH"]
        > panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"]
        and panel.close.iloc[position]["USD"] / panel.close.iloc[position - 20]["USD"] - 1.0 > 0.0
        and panel.close.iloc[position]["USD"]
        / panel.close["USD"].iloc[position - 99 : position + 1].mean()
        - 1.0
        > 0.0
    )
    assert bool(point["semiconductor_leadership"]) is expected_leadership
    assert dataset["m02_label_route"].tolist() == [row["selected_target"] for row in d01_records]

    labelled = dataset[dataset["m01_tqqq100_label"].notna()].iloc[0]
    execution_position = int(labelled["execution_position"])
    label_end_position = int(labelled["m01_label_end_position"])
    tqqq_return = (
        panel.open.iloc[label_end_position]["TQQQ"] / panel.open.iloc[execution_position]["TQQQ"]
        - 1.0
    )
    usd_return = (
        panel.open.iloc[label_end_position]["USD"] / panel.open.iloc[execution_position]["USD"]
        - 1.0
    )
    assert labelled["m01_tqqq100_label"] == float(
        tqqq_return - usd_return - r19.INCREMENTAL_OVERRIDE_COST > 0.0
    )

    for candidate_id, label_name, terminal_column in (
        ("R19M01", "m01_tqqq100_label", "m01_label_end_position"),
        ("R19M02", "m02_survival_label", "m02_label_end_position"),
    ):
        train = r19.training_rows_for_r19_prediction(
            dataset,
            decision_position=position,
            spec=specs[candidate_id],
            label_name=label_name,
        )
        assert not train.empty
        assert int(train[terminal_column].max()) <= position - 21
        assert train[label_name].isin([0.0, 1.0]).all()


def _case_r20() -> None:
    panel = r20.load_r20_price_panel(ROOT)
    specs = r20.load_and_validate_r20_specs(ROOT)
    dataset = r20.build_r20_feature_dataset(panel)
    _, d01_records = r20.build_r20_d01_targets(panel, specs["R20D01"], dataset)
    folds = r20.development_folds(panel.open.index)
    point = dataset[dataset["execution_session"] >= folds[0]["test_start"]].iloc[0]
    position = int(point["decision_position"])

    assert int(point["execution_position"]) == position + 1
    assert int(point["m01_label_end_position"]) == position + 21
    assert int(point["m02_label_end_position"]) == position + 11
    assert point["qqq_momentum_20"] == (
        panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 20]["QQQ"] - 1.0
    )
    expected_qqq_trend_50 = (
        panel.close.iloc[position]["QQQ"]
        / panel.close["QQQ"]
        .iloc[position - r20.RECOVERY_QQQ_TREND_SESSIONS + 1 : position + 1]
        .mean()
        - 1.0
    )
    expected_tqqq_momentum_10 = (
        panel.close.iloc[position]["TQQQ"]
        / panel.close.iloc[position - r20.RECOVERY_TQQQ_MOMENTUM_SESSIONS]["TQQQ"]
        - 1.0
    )
    expected_breadth_count = sum(
        panel.close.iloc[position][symbol]
        > panel.close[symbol]
        .iloc[position - r20.RECOVERY_BREADTH_TREND_SESSIONS + 1 : position + 1]
        .mean()
        for symbol in ("QQQ", "XLK", "IGV", "SOXX", "SMH")
    )
    expected_base_risk_on = bool(
        panel.close.iloc[position]["QQQ"]
        > panel.close["QQQ"].iloc[position - 199 : position + 1].mean()
        or panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"] - 1.0 > 0.0
    )
    pressure_active = False
    pressure_transition = "clear"
    usd_close = panel.close["USD"]
    for pressure_position in range(200, position + 1):
        usd_drawdown_20 = (
            usd_close.iloc[pressure_position]
            / usd_close.iloc[pressure_position - 19 : pressure_position + 1].max()
            - 1.0
        )
        usd_trend_gap_100 = (
            usd_close.iloc[pressure_position]
            / usd_close.iloc[pressure_position - 99 : pressure_position + 1].mean()
            - 1.0
        )
        usd_momentum_20 = (
            usd_close.iloc[pressure_position] / usd_close.iloc[pressure_position - 20] - 1.0
        )
        pressure_active, pressure_transition = r20._advance_usd_pressure(
            active=pressure_active,
            drawdown_20=usd_drawdown_20,
            trend_gap_100=usd_trend_gap_100,
            momentum_20=usd_momentum_20,
        )
    expected_risk_on = bool(expected_base_risk_on and not pressure_active)
    expected_recovery = bool(
        not expected_base_risk_on
        and not pressure_active
        and expected_qqq_trend_50 > 0.0
        and expected_tqqq_momentum_10 >= r20.RECOVERY_TQQQ_MOMENTUM_MIN
        and expected_breadth_count >= r20.RECOVERY_BREADTH_MIN_COUNT
    )
    assert point["qqq_trend_gap_50"] == expected_qqq_trend_50
    assert point["tqqq_momentum_10"] == expected_tqqq_momentum_10
    assert int(point["tech_breadth_count_100"]) == expected_breadth_count
    assert bool(point["base_risk_on"]) is expected_base_risk_on
    assert bool(point["risk_on"]) is expected_risk_on
    assert bool(point["usd_pressure_active"]) is pressure_active
    assert point["usd_pressure_transition"] == pressure_transition
    assert bool(point["recovery_boost"]) is expected_recovery
    expected_leadership = bool(
        panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 60]["SMH"] - 1.0 > 0.0
        and panel.close.iloc[position]["SMH"]
        / panel.close["SMH"].iloc[position - 149 : position + 1].mean()
        - 1.0
        > 0.0
        and panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 120]["SMH"]
        > panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"]
        and panel.close.iloc[position]["USD"] / panel.close.iloc[position - 20]["USD"] - 1.0 > 0.0
        and panel.close.iloc[position]["USD"]
        / panel.close["USD"].iloc[position - 99 : position + 1].mean()
        - 1.0
        > 0.0
    )
    assert bool(point["semiconductor_leadership"]) is expected_leadership
    assert dataset["m02_label_route"].tolist() == [row["selected_target"] for row in d01_records]

    labelled = dataset[dataset["m01_tqqq100_label"].notna()].iloc[0]
    execution_position = int(labelled["execution_position"])
    label_end_position = int(labelled["m01_label_end_position"])
    tqqq_return = (
        panel.open.iloc[label_end_position]["TQQQ"] / panel.open.iloc[execution_position]["TQQQ"]
        - 1.0
    )
    usd_return = (
        panel.open.iloc[label_end_position]["USD"] / panel.open.iloc[execution_position]["USD"]
        - 1.0
    )
    assert labelled["m01_tqqq100_label"] == float(
        tqqq_return - usd_return - r20.INCREMENTAL_OVERRIDE_COST > 0.0
    )

    for candidate_id, label_name, terminal_column in (
        ("R20M01", "m01_tqqq100_label", "m01_label_end_position"),
        ("R20M02", "m02_survival_label", "m02_label_end_position"),
    ):
        train = r20.training_rows_for_r20_prediction(
            dataset,
            decision_position=position,
            spec=specs[candidate_id],
            label_name=label_name,
        )
        assert not train.empty
        assert int(train[terminal_column].max()) <= position - 21
        assert train[label_name].isin([0.0, 1.0]).all()


def _case_r21() -> None:
    panel = r21.load_r21_price_panel(ROOT)
    specs = r21.load_and_validate_r21_specs(ROOT)
    dataset = r21.build_r21_feature_dataset(panel)
    _, d01_records = r21.build_r21_d01_targets(panel, specs["R21D01"], dataset)
    folds = r21.development_folds(panel.open.index)
    point = dataset[dataset["execution_session"] >= folds[0]["test_start"]].iloc[0]
    position = int(point["decision_position"])

    assert int(point["execution_position"]) == position + 1
    assert int(point["m01_label_end_position"]) == position + 21
    assert int(point["m02_label_end_position"]) == position + 11
    assert point["qqq_momentum_20"] == (
        panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 20]["QQQ"] - 1.0
    )
    expected_qqq_trend_50 = (
        panel.close.iloc[position]["QQQ"]
        / panel.close["QQQ"]
        .iloc[position - r21.RECOVERY_QQQ_TREND_SESSIONS + 1 : position + 1]
        .mean()
        - 1.0
    )
    expected_tqqq_momentum_10 = (
        panel.close.iloc[position]["TQQQ"]
        / panel.close.iloc[position - r21.RECOVERY_TQQQ_MOMENTUM_SESSIONS]["TQQQ"]
        - 1.0
    )
    expected_breadth_count = sum(
        panel.close.iloc[position][symbol]
        > panel.close[symbol]
        .iloc[position - r21.RECOVERY_BREADTH_TREND_SESSIONS + 1 : position + 1]
        .mean()
        for symbol in ("QQQ", "XLK", "IGV", "SOXX", "SMH")
    )
    expected_base_risk_on = bool(
        panel.close.iloc[position]["QQQ"]
        > panel.close["QQQ"].iloc[position - 199 : position + 1].mean()
        or panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"] - 1.0 > 0.0
    )
    pressure_active = False
    pressure_transition = "clear"
    usd_close = panel.close["USD"]
    for pressure_position in range(200, position + 1):
        usd_drawdown_20 = (
            usd_close.iloc[pressure_position]
            / usd_close.iloc[pressure_position - 19 : pressure_position + 1].max()
            - 1.0
        )
        usd_trend_gap_100 = (
            usd_close.iloc[pressure_position]
            / usd_close.iloc[pressure_position - 99 : pressure_position + 1].mean()
            - 1.0
        )
        usd_momentum_20 = (
            usd_close.iloc[pressure_position] / usd_close.iloc[pressure_position - 20] - 1.0
        )
        pressure_active, pressure_transition = r21._advance_usd_pressure(
            active=pressure_active,
            drawdown_20=usd_drawdown_20,
            trend_gap_100=usd_trend_gap_100,
            momentum_20=usd_momentum_20,
        )
    expected_risk_on = bool(expected_base_risk_on and not pressure_active)
    expected_recovery = bool(
        not expected_risk_on
        and expected_qqq_trend_50 > 0.0
        and expected_tqqq_momentum_10 >= r21.RECOVERY_TQQQ_MOMENTUM_MIN
        and expected_breadth_count >= r21.RECOVERY_BREADTH_MIN_COUNT
    )
    assert point["qqq_trend_gap_50"] == expected_qqq_trend_50
    assert point["tqqq_momentum_10"] == expected_tqqq_momentum_10
    assert int(point["tech_breadth_count_100"]) == expected_breadth_count
    assert bool(point["base_risk_on"]) is expected_base_risk_on
    assert bool(point["risk_on"]) is expected_risk_on
    assert bool(point["usd_pressure_active"]) is pressure_active
    assert point["usd_pressure_transition"] == pressure_transition
    assert bool(point["recovery_boost"]) is expected_recovery
    expected_leadership = bool(
        panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 60]["SMH"] - 1.0 > 0.0
        and panel.close.iloc[position]["SMH"]
        / panel.close["SMH"].iloc[position - 149 : position + 1].mean()
        - 1.0
        > 0.0
        and panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 120]["SMH"]
        > panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"]
        and panel.close.iloc[position]["USD"] / panel.close.iloc[position - 20]["USD"] - 1.0 > 0.0
        and panel.close.iloc[position]["USD"]
        / panel.close["USD"].iloc[position - 99 : position + 1].mean()
        - 1.0
        > 0.0
    )
    assert bool(point["semiconductor_leadership"]) is expected_leadership
    assert dataset["m02_label_route"].tolist() == [row["selected_target"] for row in d01_records]

    labelled = dataset[dataset["m01_tqqq100_label"].notna()].iloc[0]
    execution_position = int(labelled["execution_position"])
    label_end_position = int(labelled["m01_label_end_position"])
    tqqq_return = (
        panel.open.iloc[label_end_position]["TQQQ"] / panel.open.iloc[execution_position]["TQQQ"]
        - 1.0
    )
    usd_return = (
        panel.open.iloc[label_end_position]["USD"] / panel.open.iloc[execution_position]["USD"]
        - 1.0
    )
    assert labelled["m01_tqqq100_label"] == float(
        tqqq_return - usd_return - r21.INCREMENTAL_OVERRIDE_COST > 0.0
    )

    for candidate_id, label_name, terminal_column in (
        ("R21M01", "m01_tqqq100_label", "m01_label_end_position"),
        ("R21M02", "m02_survival_label", "m02_label_end_position"),
    ):
        train = r21.training_rows_for_r21_prediction(
            dataset,
            decision_position=position,
            spec=specs[candidate_id],
            label_name=label_name,
        )
        assert not train.empty
        assert int(train[terminal_column].max()) <= position - 21
        assert train[label_name].isin([0.0, 1.0]).all()


def _case_r22() -> None:
    panel = r22.load_r22_price_panel(ROOT)
    specs = r22.load_and_validate_r22_specs(ROOT)
    dataset = r22.build_r22_feature_dataset(panel)
    _, d01_records = r22.build_r22_d01_targets(panel, specs["R22D01"], dataset)
    folds = r22.development_folds(panel.open.index)
    point = dataset[dataset["execution_session"] >= folds[0]["test_start"]].iloc[0]
    position = int(point["decision_position"])

    assert int(point["execution_position"]) == position + 1
    assert int(point["m01_label_end_position"]) == position + 21
    assert int(point["m02_label_end_position"]) == position + 11
    assert point["qqq_momentum_20"] == (
        panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 20]["QQQ"] - 1.0
    )
    expected_qqq_trend_50 = (
        panel.close.iloc[position]["QQQ"]
        / panel.close["QQQ"]
        .iloc[position - r22.RECOVERY_QQQ_TREND_SESSIONS + 1 : position + 1]
        .mean()
        - 1.0
    )
    expected_tqqq_momentum_10 = (
        panel.close.iloc[position]["TQQQ"]
        / panel.close.iloc[position - r22.RECOVERY_TQQQ_MOMENTUM_SESSIONS]["TQQQ"]
        - 1.0
    )
    expected_breadth_count = sum(
        panel.close.iloc[position][symbol]
        > panel.close[symbol]
        .iloc[position - r22.RECOVERY_BREADTH_TREND_SESSIONS + 1 : position + 1]
        .mean()
        for symbol in ("QQQ", "XLK", "IGV", "SOXX", "SMH")
    )
    expected_base_risk_on = bool(
        panel.close.iloc[position]["QQQ"]
        > panel.close["QQQ"].iloc[position - 199 : position + 1].mean()
        or panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"] - 1.0 > 0.0
    )
    pressure_active = False
    pressure_transition = "clear"
    usd_close = panel.close["USD"]
    for pressure_position in range(200, position + 1):
        usd_drawdown_20 = (
            usd_close.iloc[pressure_position]
            / usd_close.iloc[pressure_position - 19 : pressure_position + 1].max()
            - 1.0
        )
        usd_trend_gap_100 = (
            usd_close.iloc[pressure_position]
            / usd_close.iloc[pressure_position - 99 : pressure_position + 1].mean()
            - 1.0
        )
        usd_momentum_20 = (
            usd_close.iloc[pressure_position] / usd_close.iloc[pressure_position - 20] - 1.0
        )
        pressure_active, pressure_transition = r22._advance_usd_pressure(
            active=pressure_active,
            drawdown_20=usd_drawdown_20,
            trend_gap_100=usd_trend_gap_100,
            momentum_20=usd_momentum_20,
        )
    expected_risk_on = bool(expected_base_risk_on and not pressure_active)
    expected_recovery = bool(
        not expected_risk_on
        and expected_qqq_trend_50 > 0.0
        and expected_tqqq_momentum_10 >= r22.RECOVERY_TQQQ_MOMENTUM_MIN
        and expected_breadth_count >= r22.RECOVERY_BREADTH_MIN_COUNT
    )
    assert point["qqq_trend_gap_50"] == expected_qqq_trend_50
    assert point["tqqq_momentum_10"] == expected_tqqq_momentum_10
    assert int(point["tech_breadth_count_100"]) == expected_breadth_count
    assert bool(point["base_risk_on"]) is expected_base_risk_on
    assert bool(point["risk_on"]) is expected_risk_on
    assert bool(point["usd_pressure_active"]) is pressure_active
    assert point["usd_pressure_transition"] == pressure_transition
    assert bool(point["recovery_boost"]) is expected_recovery
    expected_leadership = bool(
        panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 60]["SMH"] - 1.0 > 0.0
        and panel.close.iloc[position]["SMH"]
        / panel.close["SMH"].iloc[position - 149 : position + 1].mean()
        - 1.0
        > 0.0
        and panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 120]["SMH"]
        > panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 120]["QQQ"]
        and panel.close.iloc[position]["USD"] / panel.close.iloc[position - 20]["USD"] - 1.0 > 0.0
        and panel.close.iloc[position]["USD"]
        / panel.close["USD"].iloc[position - 99 : position + 1].mean()
        - 1.0
        > 0.0
    )
    assert bool(point["semiconductor_leadership"]) is expected_leadership
    assert dataset["m02_label_route"].tolist() == [row["selected_target"] for row in d01_records]

    labelled = dataset[dataset["m01_tqqq100_label"].notna()].iloc[0]
    execution_position = int(labelled["execution_position"])
    label_end_position = int(labelled["m01_label_end_position"])
    tqqq_return = (
        panel.open.iloc[label_end_position]["TQQQ"] / panel.open.iloc[execution_position]["TQQQ"]
        - 1.0
    )
    usd_return = (
        panel.open.iloc[label_end_position]["USD"] / panel.open.iloc[execution_position]["USD"]
        - 1.0
    )
    assert labelled["m01_tqqq100_label"] == float(
        tqqq_return - usd_return - r22.INCREMENTAL_OVERRIDE_COST > 0.0
    )

    for candidate_id, label_name, terminal_column in (
        ("R22M01", "m01_tqqq100_label", "m01_label_end_position"),
        ("R22M02", "m02_survival_label", "m02_label_end_position"),
    ):
        train = r22.training_rows_for_r22_prediction(
            dataset,
            decision_position=position,
            spec=specs[candidate_id],
            label_name=label_name,
        )
        assert not train.empty
        assert int(train[terminal_column].max()) <= position - 21
        assert train[label_name].isin([0.0, 1.0]).all()


_CASES: dict[str, Callable[[], None]] = {
    "r14": _case_r14,
    "r15": _case_r15,
    "r16": _case_r16,
    "r17": _case_r17,
    "r18": _case_r18,
    "r19": _case_r19,
    "r20": _case_r20,
    "r21": _case_r21,
    "r22": _case_r22,
}


@pytest.mark.parametrize("round_id", sorted(_CASES))
@pytest.mark.slow
def test_features_labels_and_embargo_use_registered_timing(round_id: str) -> None:
    _CASES[round_id]()
