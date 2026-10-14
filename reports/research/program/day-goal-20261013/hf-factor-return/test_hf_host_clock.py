"""Availability, not returns, chooses the host initialization close."""

import numpy as np
import pandas as pd
from hf_host_clock import first_valid_common_close


def fixture():
    ix = pd.date_range("2020-01-01", periods=6)
    frame = pd.DataFrame({"a": [np.nan, 0.1, 0.2, 0.3, 0.4, 0.5],
                          "b": [np.nan, np.nan, 0.0, 0.1, 0.2, 0.3]}, index=ix)
    return ix, frame


def test_leading_only_availability_and_initial_return_is_not_reinvested():
    ix, frame = fixture()
    start = first_valid_common_close(ix, frame, ["a", "b"])
    assert start == ix[2]
    growth = np.r_[1.0, np.cumprod(1 + frame.loc[start:, "a"].to_numpy()[1:])]
    np.testing.assert_allclose(growth, [1, 1.3, 1.82, 2.73])


def test_return_magnitude_and_sign_cannot_choose_start():
    ix, frame = fixture()
    expected = first_valid_common_close(ix, frame, ["a", "b"])
    frame = frame * -100
    assert first_valid_common_close(ix, frame, ["a", "b"]) == expected


def test_internal_nan_is_not_skipped_by_new_start():
    ix, frame = fixture()
    frame.loc[ix[4], "b"] = np.nan
    start = first_valid_common_close(ix, frame, ["a", "b"])
    assert start == ix[2]
    assert not np.isfinite(frame.loc[start:].to_numpy()[1:]).all()


def test_no_complete_host_is_unavailable():
    ix, frame = fixture()
    frame["b"] = np.nan
    assert first_valid_common_close(ix, frame, ["a", "b"]) is None
