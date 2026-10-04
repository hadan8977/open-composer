import numpy as np
import pytest

from open_composer.research.equity_book.trading_rules import RULES, apply_rule


def _all_true(n: int) -> np.ndarray:
    return np.ones(n, dtype=bool)


def test_b0_identity_is_bit_identical_copy():
    w = np.array([0.3, -0.2, 0.0, 0.1])
    x_old = np.array([1.0, 1.0, 1.0, 1.0])
    out = apply_rule("B0", x_old, w, w, 1.0, 1.0, np.array([True, False, True, True]))
    assert np.array_equal(out, w)
    assert out is not w
    out[0] = 9.0
    assert w[0] == 0.3


def test_unknown_rule_raises():
    with pytest.raises(ValueError):
        apply_rule("P9", np.zeros(2), np.ones(2), np.ones(2), 1.0, 1.0, _all_true(2))


def test_p2_p3_fractions():
    x_old = np.array([0.0, 0.3, -0.1])
    w = np.array([0.6, 0.0 + 0.3, 0.2])
    p2 = apply_rule("P2", x_old, w, w, 1.0, 1.0, _all_true(3))
    p3 = apply_rule("P3", x_old, w, w, 1.0, 1.0, _all_true(3))
    assert np.allclose(p2, [0.3, 0.3, 0.05])
    assert np.allclose(p3, x_old + (w - x_old) / 3.0)


def test_non_member_exits_under_every_rule():
    x_old = np.array([0.2, 0.2, -0.1])
    w = np.array([0.4, 0.0, 0.2])
    for rule in RULES:
        out = apply_rule(rule, x_old, w, w, 1.0, 1.0, _all_true(3))
        assert out[1] == 0.0


def test_never_short_non_eligible_including_old_short_with_positive_target():
    x_old = np.array([-0.2, 0.1])
    w = np.array([0.1, 0.2])
    elig = np.array([False, True])
    p2 = apply_rule("P2", x_old, w, w, 1.0, 1.0, elig)
    # x_old + 0.5 * (0.1 + 0.2) = -0.05 -> clamped to 0 for a non-eligible name
    assert p2[0] == 0.0
    assert np.isclose(p2[1], 0.15)
    # a non-eligible member that would stay short is lifted to 0 (not to the target)
    out = apply_rule("N25", np.array([-0.2, 0.0]), np.array([-0.1, 0.1]), w, 1.0, 1.0, elig)
    assert out[0] == 0.0


def test_band_no_trade_inside_and_edge_outside():
    w = np.array([0.3, -0.3, 0.1, -0.1])
    d = 0.25 * np.std(w)
    inside = w + np.array([0.5, -0.5, 0.5, -0.5]) * d
    out = apply_rule("N25", inside, w, w, 1.0, 1.0, _all_true(4))
    assert np.allclose(out, inside)
    far = w + np.array([2.0, -2.0, 2.0, -2.0]) * d
    out = apply_rule("N25", far, w, w, 1.0, 1.0, _all_true(4))
    assert np.allclose(out, w + np.array([1.0, -1.0, 1.0, -1.0]) * d)
    out50 = apply_rule("N50", far, w, w, 1.0, 1.0, _all_true(4))
    assert np.allclose(out50, far)  # 2d is the edge of the 0.5 sd band


def test_band_width_uses_ddof0_over_members_only():
    w = np.array([0.4, -0.4, 0.0, 0.0, 0.0])
    # members: 0.4, -0.4 -> population sd 0.4; including zeros would give a smaller sd
    x_old = np.array([0.4 + 0.5, -0.4, 0.0, 0.0, 0.0])
    out = apply_rule("N50", x_old, w, w, 1.0, 1.0, _all_true(5))
    assert np.isclose(out[0], 0.4 + 0.5 * 0.4)
    assert np.isclose(out[1], -0.4)
    assert out[2] == 0.0


def test_p2v_scale_flip_and_steady_state():
    w_unit = np.array([0.4, -0.4, 0.2])
    # s: 1 -> 0.5, book was at the unit target before: x_old = w_unit
    out = apply_rule("P2V", w_unit, 0.5 * w_unit, w_unit, 0.5, 1.0, _all_true(3))
    assert np.allclose(out, 0.5 * w_unit)
    # s_prev = 1, x_old = w_unit and s_t = 1 stays put
    out = apply_rule("P2V", w_unit, w_unit, w_unit, 1.0, 1.0, _all_true(3))
    assert np.allclose(out, w_unit)
    # x_old = 0.5 * w_unit under s_prev = 0.5 is already at the unit target
    out = apply_rule("P2V", 0.5 * w_unit, w_unit, w_unit, 1.0, 0.5, _all_true(3))
    assert np.allclose(out, w_unit)  # u_old = w_unit -> unchanged
    # scale 1 -> 0.5 with the book not at target: half way in unit space, then scaled at once
    x_old = np.array([0.0, 0.0, 0.0])
    out = apply_rule("P2V", x_old, 0.5 * w_unit, w_unit, 0.5, 1.0, _all_true(3))
    assert np.allclose(out, 0.5 * 0.5 * w_unit)


def test_first_block_from_empty_book():
    w = np.array([0.4, -0.2, 0.0, 0.1])
    x_old = np.zeros(4)
    assert np.allclose(apply_rule("P2", x_old, w, w, 1.0, 1.0, _all_true(4)), 0.5 * w)
    assert np.allclose(apply_rule("P3", x_old, w, w, 1.0, 1.0, _all_true(4)), w / 3.0)
    assert np.allclose(apply_rule("P2V", x_old, w, w, 1.0, 1.0, _all_true(4)), 0.5 * w)
    d = 0.25 * np.std(w[w != 0])
    n25 = apply_rule("N25", x_old, w, w, 1.0, 1.0, _all_true(4))
    assert np.allclose(n25[w != 0], w[w != 0] - np.sign(w[w != 0]) * d)


def test_sign_flip_across_zero_under_band():
    w = np.array([0.3, -0.3, 0.2, -0.2])
    d = 0.25 * np.std(w)
    x_old = -w  # every name on the wrong side
    out = apply_rule("N25", x_old, w, w, 1.0, 1.0, _all_true(4))
    assert np.allclose(out, w - np.sign(w) * d)
    assert np.all(np.sign(out) == np.sign(w))


def test_empty_target_flattens_everything():
    w = np.zeros(3)
    x_old = np.array([0.1, -0.1, 0.2])
    for rule in RULES:
        out = apply_rule(rule, x_old, w, w, 1.0, 1.0, _all_true(3))
        assert np.all(out == 0.0)


def test_turnover_ordering_on_random_walk_target():
    rng = np.random.default_rng(7)
    n, steps = 60, 80
    w = rng.normal(size=n)
    w = w / np.abs(w).sum() * 2.0
    elig = _all_true(n)
    state = {r: np.zeros(n) for r in ("B0", "P2", "P3")}
    turn = {r: 0.0 for r in state}
    for _ in range(steps):
        w = 0.6 * w + 0.4 * rng.normal(size=n) / n
        for r in state:
            x_new = apply_rule(r, state[r], w, w, 1.0, 1.0, elig)
            turn[r] += float(np.abs(x_new - state[r]).sum())
            state[r] = x_new
    assert turn["P3"] < turn["P2"] < turn["B0"]
