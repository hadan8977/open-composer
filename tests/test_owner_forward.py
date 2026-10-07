from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from statistics import NormalDist

import numpy as np

from open_composer.reports import owner_forward as of
from open_composer.research.scorecard_v2 import psr as reference_psr

RETURNS = [0.004, -0.002, 0.003, 0.001, -0.001, 0.005, 0.002, -0.003, 0.004, 0.0, 0.003, 0.002]


def test_psr_matches_scorecard_reference() -> None:
    stats = of.sharpe_confidence(RETURNS)
    assert stats["psr"] is not None
    assert math.isclose(stats["psr"], reference_psr(np.array(RETURNS)), rel_tol=1e-9)
    assert stats["sharpe_annual"] > 0


def test_min_trl_is_the_length_where_psr_reaches_95_percent() -> None:
    stats = of.sharpe_confidence(RETURNS)
    n = stats["min_trl"]
    assert n is not None and n > 1
    # at the minimum track record length PSR = 0.95 by construction (same moments, n sessions)
    mean, std, skew, kurt = of._moments(RETURNS)
    sr = mean / std
    den = of._denominator(sr, skew, kurt)
    assert math.isclose(of._N.cdf(sr * math.sqrt(n - 1) / den), 0.95, abs_tol=1e-9)


def test_small_or_flat_samples_give_no_estimate() -> None:
    assert of.sharpe_confidence(RETURNS[: of.MIN_SAMPLE - 1]) == {
        "sharpe_annual": None,
        "psr": None,
        "min_trl": None,
    }
    assert of.sharpe_confidence([0.001] * 12)["psr"] is None


def test_non_positive_sharpe_has_no_minimum_length() -> None:
    stats = of.sharpe_confidence([-r for r in RETURNS])
    assert stats["psr"] is not None and stats["psr"] < 0.5
    assert stats["min_trl"] is None


def test_recorded_sharpe_overrides_the_zero_rf_sharpe() -> None:
    plain = of.sharpe_confidence(RETURNS)
    lower = of.sharpe_confidence(RETURNS, sharpe_annual=plain["sharpe_annual"] - 1.0)
    assert lower["sharpe_annual"] == plain["sharpe_annual"] - 1.0
    assert lower["psr"] < plain["psr"]
    assert lower["min_trl"] > plain["min_trl"]


def _summary(n_forward: int, sharpe: float | None, meaningful: bool = True) -> dict:
    z = {
        "backtest_full": {"n_forward": n_forward, "z": 0.5},
        "backtest_recent": {
            "n_forward": n_forward,
            "z": -0.25,
            "base_mean_daily": 0.001,
            "base_std_daily": 0.01,
        },
    }
    strategy = {"days": n_forward, "sharpe": sharpe, "sharpe_meaningful": meaningful}
    segment = {"forward_oos_plus_paper": {"strategy": strategy}}
    return {
        "candidates": {
            "S1": {"primary_boundary_commit": {"z": z, "segments": segment}},
            "V12F1": {
                "primary_boundary_commit": {
                    "z": {"backtest_full": {"n_forward": 0, "z": None}},
                    "segments": {},
                }
            },
        }
    }


def _record(candidate: str, values: list[float]) -> list[dict[str, str]]:
    return [
        {"date": f"2026-09-{i + 1:02d}", "candidate": candidate, "segment": "paper"}
        | {"net_return": str(v)}
        for i, v in enumerate(values)
    ] + [
        {"date": "2026-08-01", "candidate": candidate, "segment": "design_seen"}
        | {"net_return": "0.5"}
    ]


def test_forward_rows_use_forward_segments_and_mark_missing() -> None:
    rows = {
        r.candidate: r for r in of.build_forward_rows(_summary(12, 3.0), _record("S1", RETURNS))
    }
    s1 = rows["S1"]
    assert s1.n_forward == 12 and s1.z_full == 0.5 and s1.z_recent == -0.25
    assert s1.sharpe_annual == 3.0  # the design_seen day (+50%) is not part of the forward sample
    assert s1.min_trl == of.expected_min_trl(0.001, 0.01) and s1.progress == 12 / s1.min_trl
    assert rows["V12F1"].n_forward == 0 and "缺" in rows["V12F1"].note
    assert rows["S2"].n_forward is None and "缺" in rows["S2"].note


def test_expected_min_trl_uses_the_backtest_sharpe_with_normal_moments() -> None:
    # daily Sharpe 0.1: 1 + (1 + 0.1**2 / 2) * (z_0.95 / 0.1) ** 2
    z95 = NormalDist().inv_cdf(0.95)
    assert math.isclose(of.expected_min_trl(0.001, 0.01), 1 + 1.005 * (z95 / 0.1) ** 2)
    assert of.expected_min_trl(-0.001, 0.01) is None
    assert of.expected_min_trl(None, 0.01) is None


def test_forward_sharpe_hidden_until_the_record_flags_it_meaningful() -> None:
    summary = _summary(12, 9.0, meaningful=False)
    row = of.build_forward_rows(summary, _record("S1", RETURNS))[0]
    assert row.sharpe_annual is None and row.psr is None and "样本不足" in row.note
    assert row.min_trl == of.expected_min_trl(0.001, 0.01) and row.progress == 12 / row.min_trl


def test_forward_rows_small_sample_is_flagged_not_estimated() -> None:
    row = of.build_forward_rows(_summary(5, 1.0), _record("S1", RETURNS[:5]))[0]
    assert row.psr is None and "样本不足" in row.note


def test_render_forward_and_missing_source(tmp_path: Path) -> None:
    assert "读取失败" in of.render_forward(of.load_forward_rows(tmp_path))[0]
    rows = of.build_forward_rows(_summary(12, 3.0), _record("S1", RETURNS))
    text = "\n".join(
        of.render_forward((rows, {"track_start": "a", "last_session": "b", "source": "s"}))
    )
    assert "| S1 | 12 |" in text and "| V12F1 | 0 | 缺 |" in text


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_book_actions_not_started_before_first_order_day(tmp_path: Path) -> None:
    base = tmp_path / "reports/paper/book/quant1"
    _write(base / "plans/2026-10-05.json", {"summary": {"n_orders": 9}, "equity_basis": 1000.0})
    assert of.collect_book_actions(tmp_path) == []
    assert "未开始" in of.render_book_actions([])[0]


def test_book_actions_read_plan_receipts_and_daily(tmp_path: Path) -> None:
    base = tmp_path / "reports/paper/book/quant1"
    _write(
        base / "plans/2026-10-07.json",
        {
            "dry_run": True,
            "equity_basis": 1000.0,
            "summary": {"n_orders": 10, "buy_notional": 300.0, "sell_notional": 100.0},
        },
    )
    _write(
        base / "orders/2026-10-07.json",
        {"sent": [{"symbol": "A"}] * 8, "skipped_existing": [], "failed": [{"symbol": "B"}] * 2},
    )
    _write(
        base / "orders/2026-10-07.rerun-101500.json",
        {"sent": [{"symbol": "C"}], "skipped_existing": [], "failed": []},
    )
    _write(
        base / "daily/2026-10-07.json",
        {"reconciliation": {"n_filled": 6, "n_partial": 1, "n_unfilled": 2, "n_missing": 1}},
    )
    _write(
        tmp_path / "reports/paper/book/quant2/plans/2026-10-07.json", {"summary": {"n_orders": 3}}
    )
    rows = {a.account: a for a in of.collect_book_actions(tmp_path, accounts=("quant1", "quant2"))}
    one = rows["quant1"]
    assert one.day == date(2026, 10, 7) and one.state == "已对账"
    assert (one.n_planned, one.n_sent, one.n_rejected) == (10, 9, 2)
    assert (one.n_filled, one.n_partial, one.n_unfilled) == (6, 1, 3)
    assert one.turnover == 0.4 and len(one.receipts) == 2
    two = rows["quant2"]
    assert two.state == "已出计划，未发单" and two.n_sent is None and two.turnover is None
    text = "\n".join(of.render_book_actions(list(rows.values())))
    assert "| 2026-10-07 | quant1 | 已对账 | 10 | 9 | 2 | 6 | 1 | 3 | 40.0% |" in text
    assert "| 2026-10-07 | quant2 | 已出计划，未发单 | 3 | — |" in text
