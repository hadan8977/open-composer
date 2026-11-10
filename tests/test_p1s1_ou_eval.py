from __future__ import annotations

import numpy as np

from scripts.p1s1_ou_eval import ou_scores


def test_vectorized_ou_scores_has_causal_state_and_thresholds() -> None:
    rng = np.random.default_rng(1)
    path = np.cumsum(rng.normal(size=(60, 4)), axis=0)
    score, pos = ou_scores(path, np.zeros(4))
    assert score.shape == (4,)
    assert pos.shape == (4,)
    assert np.isin(pos, [-1.0, 0.0, 1.0]).all()
