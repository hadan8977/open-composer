"""Step 6.5: enforce cross-family selection and thesis-keyword alignment."""

from __future__ import annotations

from open_composer.research.auto_research import (
    _select_top_k,
    _select_with_keyword_heuristic,
    _thesis_alignment_lines,
)
from open_composer.research.factor_library import get_factor


def test_overnight_thesis_selects_overnight_gap_family() -> None:
    thesis = "Overnight thesis: exploit overnight gap behavior on SYN daily bars."
    candidates = _select_with_keyword_heuristic(thesis)

    assert any(candidate.family == "overnight_gap" for candidate in candidates), (
        "overnight thesis must include overnight_gap factors; got families "
        f"{[candidate.family for candidate in candidates]}"
    )


def test_trend_thesis_adds_risk_filter() -> None:
    thesis = "Trend thesis: find a strong daily uptrend continuation strategy on SYN."
    candidates = _select_with_keyword_heuristic(thesis)
    families = {candidate.family for candidate in candidates}

    assert "trend_momentum" in families
    assert families & {"risk_regime", "drawdown_guard", "volatility_rank"}, (
        f"trend thesis must include a risk filter; got families {families}"
    )


def test_mean_reversion_thesis_adds_risk_filter() -> None:
    thesis = "Mean reversion thesis: buy oversold daily pullbacks on SYN."
    candidates = _select_with_keyword_heuristic(thesis)
    families = {candidate.family for candidate in candidates}

    assert "momentum_short" in families
    assert families & {"risk_regime", "drawdown_guard", "volatility_rank"}, (
        f"mean reversion thesis must include a risk filter; got families {families}"
    )


def test_drawdown_thesis_selects_drawdown_family() -> None:
    thesis = "Defensive thesis: reduce exposure during drawdowns and crashes."
    candidates = _select_with_keyword_heuristic(thesis)
    families = {candidate.family for candidate in candidates}

    assert "drawdown_guard" in families or any(
        "drawdown" in candidate.id for candidate in candidates
    ), f"drawdown thesis must surface drawdown factors; got families {families}"


def test_volatility_thesis_selects_volatility_family() -> None:
    thesis = "Volatility thesis: trade only when volatility is calm."
    candidates = _select_with_keyword_heuristic(thesis)
    families = {candidate.family for candidate in candidates}

    assert "volatility_rank" in families or "risk_regime" in families


def test_at_least_two_families_in_all_cases() -> None:
    """No thesis should be locked to a single family."""
    for thesis in [
        "Trend continuation on SYN.",
        "Mean reversion buy the dip.",
        "Volatility breakout regime.",
        "Risk regime defensive switch.",
        "Overnight gap exploit.",
    ]:
        candidates = _select_with_keyword_heuristic(thesis)
        families = {candidate.family for candidate in candidates}
        assert len(families) >= 2, (
            f"single-family lockdown still present for thesis={thesis!r}; families={families}"
        )


def test_thesis_alignment_explains_unselected_required_family() -> None:
    candidates = [
        get_factor("alpha158_overnight_gap"),
        get_factor("volatility_rank_20_252"),
    ]
    selected = [get_factor("volatility_rank_20_252")]
    lines = _thesis_alignment_lines(
        "Overnight gap exploit on QQQ daily.",
        candidates,
        selected,
        {
            "alpha158_overnight_gap": {
                "rank_ic": 0.0043,
                "coverage_pct": 99.8,
                "observations": 495,
            },
            "volatility_rank_20_252": {
                "rank_ic": 0.188,
                "coverage_pct": 99.8,
                "observations": 495,
            },
        },
    )

    text = "\n".join(lines)
    assert "`overnight_gap`: candidate present but not selected" in text
    assert "rank_ic below selection threshold" in text


def test_top_k_limits_risk_filter_concentration() -> None:
    candidates = [
        get_factor("volatility_rank_20_252"),
        get_factor("drawdown_guard_20_60"),
        get_factor("leveraged_etf_extension_guard"),
        get_factor("overextension_mean_reversion_guard"),
        get_factor("alpha101_007_price_above_sma_10d"),
        get_factor("alpha101_009_roc_5d"),
    ]
    scores = {
        factor.id: {
            "rank_ic": 0.10 - index * 0.001,
            "ir": 0.8 - index * 0.01,
            "coverage_pct": 95.0,
            "observations": 250,
            "stability_score": 0.8,
        }
        for index, factor in enumerate(candidates)
    }

    selected = _select_top_k(scores, candidates, 5)
    risk_families = {"risk_regime", "drawdown_guard", "volatility_rank"}

    assert len(selected) == 5
    assert sum(1 for factor in selected[:3] if factor.family in risk_families) <= 2
    assert any(factor.family == "trend_momentum" for factor in selected)


def test_top_k_prefers_higher_ir_when_rank_ic_is_tied() -> None:
    low_ir = get_factor("alpha101_007_price_above_sma_10d")
    high_ir = get_factor("alpha101_009_roc_5d")
    candidates = [low_ir, high_ir]
    scores = {
        low_ir.id: {
            "rank_ic": 0.05,
            "ir": 0.4,
            "coverage_pct": 95.0,
            "observations": 250,
            "stability_score": 0.6,
        },
        high_ir.id: {
            "rank_ic": 0.05,
            "ir": 1.1,
            "coverage_pct": 95.0,
            "observations": 250,
            "stability_score": 0.6,
        },
    }

    selected = _select_top_k(scores, candidates, 1)

    assert selected == [high_ir]


def test_top_k_requires_rank_ic_and_ir_thresholds() -> None:
    factor = get_factor("alpha101_007_price_above_sma_10d")
    candidates = [factor]
    scores = {
        factor.id: {
            "rank_ic": 0.01,
            "ir": 0.8,
            "coverage_pct": 95.0,
            "observations": 250,
            "stability_score": 0.6,
        }
    }

    selected = _select_top_k(scores, candidates, 1)

    assert selected == []
