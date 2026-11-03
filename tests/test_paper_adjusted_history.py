import copy

import numpy as np
import pandas as pd
import pytest

from open_composer.paper_runtime.six.adjusted_history import append_adjusted_history


def fixture():
    dates = pd.to_datetime(["2026-10-29", "2026-10-30"])
    opening = pd.DataFrame({"BOND": [99.19, 100.27]}, index=dates)
    close = pd.DataFrame({"BOND": [99.22, 100.0]}, index=dates)
    old = {("BOND", str(d.date())): {"o": opening.loc[d, "BOND"], "c": close.loc[d, "BOND"]} for d in dates}
    factor = 1 - 0.335 / 100
    new = {k: {f: round(v * factor, 2) for f, v in row.items()} for k, row in old.items()}
    new["BOND", "2026-11-02"] = {"o": 99.77, "c": 100.1}
    actions = [{"id": "received-dividend", "symbol": "BOND", "ex_date": "2026-11-02", "rate": 0.335}]
    return opening, close, old, new, actions, factor


def test_received_dividend_preserves_prefix_and_the_following_day():
    opening, close, old, new, actions, factor = fixture()
    op, cl, scales, qa = append_adjusted_history(
        opening, close, old, new, {"BOND": 1.0}, actions,
        prior_reference="2026-10-30", reference="2026-11-02",
    )
    assert np.array_equal(cl.iloc[:2], close) and np.array_equal(op.iloc[:2], opening)
    assert cl.iloc[-1, 0] == 100.1 / factor
    assert qa["BOND"]["method"] == "received_dividend_and_cent_rounding"
    tomorrow = copy.deepcopy(new)
    tomorrow["BOND", "2026-11-03"] = {"o": 100.2, "c": 100.3}
    op2, cl2, scales2, _ = append_adjusted_history(
        op, cl, new, tomorrow, scales, [],
        prior_reference="2026-11-02", reference="2026-11-03",
    )
    assert np.array_equal(cl2.iloc[:-1], cl) and np.array_equal(op2.iloc[:-1], op)
    assert scales2 == scales and cl2.iloc[-1, 0] == 100.3 / factor


@pytest.mark.parametrize("defect", ["missing_action", "wrong_amount", "large_revision", "missing_cell"])
def test_unexplained_price_changes_still_refuse(defect):
    opening, close, old, new, actions, _ = fixture()
    if defect == "missing_action":
        actions = []
    elif defect == "wrong_amount":
        actions[0]["rate"] = 0.5
    elif defect == "large_revision":
        new["BOND", "2026-10-29"]["o"] += 0.1
    else:
        del new["BOND", "2026-10-29"]
    with pytest.raises(ValueError):
        append_adjusted_history(
            opening, close, old, new, {"BOND": 1.0}, actions,
            prior_reference="2026-10-30", reference="2026-11-02",
        )
