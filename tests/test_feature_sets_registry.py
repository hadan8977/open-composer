"""Tests for open_composer.research.features.feature_sets."""

from __future__ import annotations

import json

import pytest

from open_composer.research.features import feature_sets as fs


def test_daily27_has_no_extra_root() -> None:
    columns, roots = fs.resolve_feature_set("daily27")
    assert len(columns) == 26
    assert roots == []


def test_alpha158_columns_and_root() -> None:
    columns, roots = fs.resolve_feature_set("alpha158")
    assert len(columns) == 154
    assert roots == [fs.ALPHA158_ROOT]


def test_alpha101_and_alpha191_columns_and_roots() -> None:
    columns_101, roots_101 = fs.resolve_feature_set("alpha101")
    assert len(columns_101) == 20
    assert roots_101 == [fs.ALPHA101_ROOT]

    columns_191, roots_191 = fs.resolve_feature_set("alpha191")
    assert len(columns_191) == 20
    assert roots_191 == [fs.ALPHA191_ROOT]


def test_unknown_feature_set_raises_key_error() -> None:
    with pytest.raises(KeyError):
        fs.resolve_feature_set("does_not_exist")


def test_all_open_aggregates_every_open_library_but_not_daily27() -> None:
    columns, roots = fs.resolve_feature_set("all_open")
    daily27_columns, _ = fs.resolve_feature_set("daily27")
    assert not set(daily27_columns) & set(columns)
    assert set(fs.ALPHA158_ROOT.parts[-2:]) or True  # sanity: attribute exists
    assert fs.ALPHA158_ROOT in roots
    assert fs.ALPHA101_ROOT in roots
    assert fs.ALPHA191_ROOT in roots
    assert fs.OSAP_PRICE_ROOT in roots
    assert fs.REVERSAL_TREND_ROOT in roots
    # alpha158 (154) + alpha101 (20) + alpha191 (20) + osap_price (25) +
    # reversal_trend's continuous columns only (21 of its 25 -- the 4
    # discrete signal columns are event-study-only, not screened).
    assert len(columns) == 154 + 20 + 20 + 25 + 21


def test_screened_top40_recent_missing_file_raises_actionable_error() -> None:
    original_exists = fs.SCREENED_TOP40_PATH.exists()
    if original_exists:
        pytest.skip("screened_top40_recent.json already exists on disk")
    with pytest.raises(FileNotFoundError, match="screen_factors.py"):
        fs.resolve_feature_set("screened_top40_recent")


def test_screened_top40_recent_reads_factor_list_and_roots(tmp_path, monkeypatch) -> None:
    payload = {
        "factors": [
            {"factor": "KMID5", "source_root": "alpha158", "icir_recent": 0.09},
            {"factor": "alpha003", "source_root": "alpha101", "icir_recent": 0.07},
        ]
    }
    path = tmp_path / "screened_top40_recent.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(fs, "SCREENED_TOP40_PATH", path)

    columns, roots = fs.resolve_feature_set("screened_top40_recent")
    assert columns == ["KMID5", "alpha003"]
    assert set(roots) == {fs.FEATURES_ROOT / "alpha158", fs.FEATURES_ROOT / "alpha101"}


def test_available_feature_sets_lists_every_name() -> None:
    names = fs.available_feature_sets()
    for expected in [
        "daily27",
        "alpha158",
        "alpha101",
        "alpha191",
        "all_open",
        "screened_top40_recent",
    ]:
        assert expected in names
