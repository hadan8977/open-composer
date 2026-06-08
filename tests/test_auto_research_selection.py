"""Step 6.5: enforce cross-family selection and thesis-keyword alignment."""

from __future__ import annotations

from open_composer.research.auto_research import _select_with_keyword_heuristic


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
