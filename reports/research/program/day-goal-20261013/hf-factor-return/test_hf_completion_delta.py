"""Actual runtime accounting and public warm-start serialization parity tests."""

import json
import pickle

import numpy as np
import pytest
from hf_completion_resources import process_limit, snapshot
from hf_models import hgb
from hf_run_models import binning_digest, tree_state_digest


def test_conservative_baseline_allowances_and_commitments_once(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps(
            dict(
                cap_CPU=36000,
                base_conservative_CPU=460.49,
                entries=[
                    dict(job_id="read", status="closed", charge_CPU=5),
                    dict(job_id="outer-time-only", status="closed", charge_CPU=12.3),
                    dict(job_id="review", status="reserved", upper_CPU=180),
                ],
            )
        )
    )
    state = snapshot(path)
    assert state["conservative_used_CPU"] == pytest.approx(477.79)
    assert state["committed_CPU"] == 180
    assert state["remaining_uncommitted_CPU"] == pytest.approx(35342.21)


def test_duplicate_job_blocks_nested_double_count(tmp_path):
    path = tmp_path / "ledger.json"
    row = dict(job_id="same-launch", status="closed", charge_CPU=2)
    path.write_text(
        json.dumps(dict(cap_CPU=36000, base_conservative_CPU=460.49, entries=[row, row]))
    )
    with pytest.raises(AssertionError, match="charged twice"):
        snapshot(path)


def test_inclusive_1200_slot_keeps_launcher_margin():
    assert process_limit(1200) == 1195
    assert process_limit(1700) == 1695
    assert process_limit(700) == 695


@pytest.mark.parametrize("depth,rate", [(4, 0.01), (6, 0.1)])
def test_public_same_data_checkpoint_resume_matches_uninterrupted(depth, rate):
    rng = np.random.default_rng(51)
    x = rng.normal(size=(300, 9))
    y = x[:, 0] * x[:, 1] + x[:, 2] + rng.normal(size=300) * 0.1
    original = hgb(depth, rate, 50, warm_start=True).fit(x, y)
    original.set_params(max_iter=150).fit(x, y)
    prefix = tree_state_digest(original, 150)
    bins = binning_digest(original)
    restored = pickle.loads(pickle.dumps(original, protocol=5))
    assert restored.get_params() == original.get_params()
    assert tree_state_digest(restored, 150) == prefix
    assert (
        restored._feature_subsample_rng.bit_generator.state
        == original._feature_subsample_rng.bit_generator.state
    )
    original.set_params(max_iter=350).fit(x, y)
    restored.set_params(max_iter=350).fit(x, y)
    assert restored.n_iter_ == 350
    assert tree_state_digest(restored, 150) == prefix
    assert binning_digest(restored) == bins
    assert tree_state_digest(restored, 350) == tree_state_digest(original, 350)
    np.testing.assert_array_equal(restored.predict(x), original.predict(x))
