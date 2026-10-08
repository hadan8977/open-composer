"""T-20261007-21: toy-array tests for the S3 theme-cap target builder. No market data."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import p2_theme_budget as p2  # noqa: E402
import s3_tc10  # noqa: E402

WIN = 100
COLS = ["SPY", "SMH", "SOXL", "UPRO", "SSO", "SHY", "BIL", "QQQ"]
COLS2 = ["SOXL", "UPRO", "SHY", "SPY", "SSO"]


def _returns(n: int = 260, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    spy = rng.normal(0.0004, 0.010, n)
    th = rng.normal(0.0, 0.012, n)
    smh = 1.3 * spy + th
    data = {
        "SPY": spy,
        "SMH": smh,
        "SOXL": 3.0 * smh + rng.normal(0, 0.003, n),
        "UPRO": 3.0 * spy + rng.normal(0, 0.002, n),
        "SSO": 2.0 * spy + rng.normal(0, 0.001, n),
        "SHY": rng.normal(0.0001, 0.0005, n),
        "BIL": rng.normal(0.0001, 0.0001, n),
        "QQQ": 1.1 * spy + 0.4 * th + rng.normal(0, 0.003, n),
    }
    return pd.DataFrame(data, index=pd.bdate_range("2020-01-01", periods=n))[COLS]


def _ctx_inst(rows: dict[int, dict[str, float]]):
    ret = _returns()
    rs = p2.RiskStats(ret, window=WIN)
    view = p2.ThemeView(rs, "SMH")
    sub_k = {}
    for col, i in rs.ci.items():
        if col in p2.NO_MOVE or col in ("SHY", "BIL"):
            sub_k[i] = i
        else:
            sub_k[i] = rs.ci[p2.SUB.get(col, "SPY")]
    ctx = SimpleNamespace(
        index=ret.index,
        K=rs.K,
        views={"SMH": view},
        sub_k=sub_k,
        cash_k={rs.ci["SHY"], rs.ci["BIL"]},
    )
    n = len(ret)
    w2 = np.zeros((n, len(COLS2)))
    w2[:, COLS2.index("SHY")] = 1.0
    starts = sorted(rows)
    for j, st in enumerate(starts):
        en = starts[j + 1] if j + 1 < len(starts) else n
        w2[st:en] = 0.0
        for col, v in rows[st].items():
            w2[st:en, COLS2.index(col)] = v
    inst = SimpleNamespace(
        cols2=COLS2, w2=w2, starts=starts, kidx=np.array([rs.ci[c] for c in COLS2])
    )
    return ctx, inst, view


def test_trs_below_cap_leaves_weights_unchanged():
    ctx, inst, _ = _ctx_inst({150: {"SOXL": 0.5, "UPRO": 0.5}})
    out = s3_tc10.capped_targets(ctx, inst, level=0.999)
    r = out["rows"][0]
    assert r["s"] == 0.0 and not r["bound"]
    assert np.array_equal(out["w"], inst.w2)
    assert r["weights_capped"] == r["weights_uncapped"]
    assert r["trs_after"] == r["trs_before"]


def test_theme_holding_moves_to_substitute_in_cent_steps_and_stops_at_first_pass():
    ctx, inst, view = _ctx_inst({150: {"SOXL": 0.8, "UPRO": 0.2}})
    c = 0.30
    r = s3_tc10.capped_targets(ctx, inst, level=c)["rows"][0]
    assert r["bound"] and not r["flag"]
    assert abs(r["s"] * 100 - round(r["s"] * 100)) < 1e-9 and 0.0 < r["s"] < 1.0
    assert r["trs_after"] <= c
    # SOXL (substitute UPRO) gave up exactly s of its weight
    up = r["weights_uncapped"]
    cp = r["weights_capped"]
    assert abs(cp["SOXL"] - up["SOXL"] * (1 - r["s"])) < 1e-12
    assert abs(cp["UPRO"] - (up["UPRO"] + up["SOXL"] * r["s"])) < 1e-12
    # one 0.01 step less is not enough
    ri = ctx.views["SMH"].rs.ci
    wk = np.zeros(ctx.K)
    s_prev = r["s"] - 0.01
    wk[ri["SOXL"]] = 0.8 * (1 - s_prev)
    wk[ri["UPRO"]] = 0.2 + 0.8 * s_prev
    assert view.parts(wk, r["start"] - 1)["trs"][0] > c


def test_no_move_names_never_move():
    ctx, inst, _ = _ctx_inst({150: {"UPRO": 0.5, "SSO": 0.5}})
    out = s3_tc10.capped_targets(ctx, inst, level=1e-6)
    r = out["rows"][0]
    # the cap binds but nothing is movable: weights untouched, reported as a flagged row
    assert r["bound"] and r["flag"]
    assert r["weights_capped"] == r["weights_uncapped"]
    assert np.array_equal(out["w"], inst.w2)


def test_cash_target_stays_cash_and_weights_for_picks():
    ctx, inst, _ = _ctx_inst({150: {"SHY": 1.0}})
    r = s3_tc10.capped_targets(ctx, inst, level=0.10)["rows"][0]
    assert r["weights_capped"]["SHY"] == 1.0 and r["s"] == 0.0
    assert s3_tc10.weights_for_picks(inst, []).tolist() == [0, 0, 1, 0, 0]
    assert s3_tc10.weights_for_picks(inst, ["SOXL", "UPRO"]).tolist() == [0.5, 0.5, 0, 0, 0]
    assert s3_tc10.weights_for_picks(inst, ["SOXL"]).tolist() == [1.0, 0, 0, 0, 0]
