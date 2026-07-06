from __future__ import annotations

from open_composer.research.hybrid_router_core import _effective_lookback, hybrid_params_from_label
from open_composer.research.pdr_attribution import simulate_daily_rows
from open_composer.research.pdr_risk_on_review import (
    build_variant_symbol_series,
    risk_on_ranked_decisions,
    same_day_variant_review,
)
from open_composer.research.post_drawdown_reentry_router import (
    post_drawdown_reentry_params_from_label,
)
from tests.test_pdr_router_parity import OVERLAY_LABEL, _fixture_dataset, _spec


def test_risk_on_ranked_review_fixture_same_day_variants() -> None:
    spec = _spec()
    dataset = _fixture_dataset()
    params = hybrid_params_from_label(OVERLAY_LABEL)
    base = post_drawdown_reentry_params_from_label(params.base_route_label)
    lookback = _effective_lookback(params)
    end_index = len(dataset.dates) - 1
    rows = simulate_daily_rows(spec, dataset, params, lookback, end_index)
    decisions = risk_on_ranked_decisions(spec, dataset, params, base, lookback, end_index)

    variants = build_variant_symbol_series(decisions)
    review = same_day_variant_review(
        spec=spec,
        dataset=dataset,
        rows=rows,
        decisions=decisions,
        variant_symbols=variants,
        folds=(("fixture", decisions[0].date, decisions[-1].date),),
    )

    assert len(decisions) == 10
    assert set(variants) >= {"fixed_TQQQ", "fixed_QLD", "smooth_k3", "tie_bias_TQQQ_eps2"}
    assert review["full_window"]["days"] == len(decisions)
    assert review["full_window"]["variants"]["fixed_TQQQ"]["days"] == len(decisions)
    assert "arithmetic_delta_pct_points" in review["folds"]["fixture"]["variants"]["fixed_QQQ"]
