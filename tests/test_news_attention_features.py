"""Tests for the news-attention feature primitives (H-20260916-02, stage 1).

These pin the definitions the card's stop conditions are read off, so a later
edit cannot quietly change what "novelty" or "attention surge" means: the
headline normalization and shingling, the Jaccard/max-overlap pair, the surge
denominator (including the archive-truncation correction that keeps early-2024
rows from showing a fake spike), the fixed keyword dictionary, and the
builder's two non-obvious numeric kernels (rolling window sums and the
distinct-key-in-window counter).

Nothing here touches an LLM, and nothing here reads ``data/`` -- these are pure
functions plus two numpy kernels.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.features import news_attention as na

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

builder = importlib.import_module("scripts.build_news_attention_features")


# --------------------------------------------------------------------------
# text primitives
# --------------------------------------------------------------------------


def test_normalize_headline_collapses_case_and_punctuation() -> None:
    assert na.normalize_headline("AAPL's Q3 Beats!!  Big.") == "aapl s q3 beats big"
    assert na.normalize_headline(None) == ""
    assert na.normalize_headline("") == ""


def test_word_trigrams_are_word_level_and_sliding() -> None:
    assert na.word_trigrams("a b c d") == frozenset({("a", "b", "c"), ("b", "c", "d")})


def test_short_headlines_fall_back_to_token_unigrams() -> None:
    """A two-word headline must stay comparable to itself; emitting an empty
    trigram set would score every short headline as maximally novel.
    """
    assert na.word_trigrams("nvidia upgraded") == frozenset({("nvidia",), ("upgraded",)})
    assert (
        na.jaccard(na.word_trigrams("nvidia upgraded"), na.word_trigrams("nvidia upgraded")) == 1.0
    )


def test_jaccard_is_zero_when_either_side_is_empty() -> None:
    assert na.jaccard(frozenset(), na.word_trigrams("a b c")) == 0.0
    assert na.jaccard(na.word_trigrams("a b c"), frozenset()) == 0.0


def test_jaccard_matches_hand_computed_value() -> None:
    left = na.word_trigrams("alpha beta gamma delta")  # {abg, bgd}
    right = na.word_trigrams("alpha beta gamma epsilon")  # {abg, bge}
    assert left & right == {("alpha", "beta", "gamma")}
    assert na.jaccard(left, right) == pytest.approx(1 / 3)


def test_max_overlap_finds_the_closest_prior_and_short_circuits_on_identity() -> None:
    target = na.word_trigrams("company reports record quarterly revenue")
    priors = [
        na.word_trigrams("unrelated macro commentary from the desk"),
        na.word_trigrams("company reports record quarterly revenue"),
    ]
    assert na.max_overlap(target, priors) == 1.0
    assert na.max_overlap(target, []) == 0.0


def test_novelty_is_one_minus_mean_overlap_and_undefined_when_empty() -> None:
    assert na.novelty_from_overlaps([0.0, 0.5, 0.25]) == pytest.approx(1 - 0.25)
    assert np.isnan(na.novelty_from_overlaps([]))


# --------------------------------------------------------------------------
# keyword dictionary
# --------------------------------------------------------------------------


def test_keyword_groups_fire_on_whole_words_only() -> None:
    hits = na.keyword_hits("Analyst Upgrades XYZ After FDA Nod; CEO Sees Strong Guidance")
    assert hits["upgrade"] and hits["fda"] and hits["ceo"] and hits["guidance"]
    assert not hits["downgrade"] and not hits["lawsuit"] and not hits["merger"]


def test_keyword_groups_do_not_fire_on_substrings() -> None:
    """``eps`` must not match "steps" and ``fda`` must not match "fdap"; the
    dictionary is whole-word by construction and this is the regression that
    catches someone dropping the ``\\b`` anchors.
    """
    hits = na.keyword_hits("Company Steps Up Fdap Filing Plans")
    assert not hits["earnings"]
    assert not hits["fda"]


def test_keyword_columns_match_the_dictionary_order() -> None:
    assert na.KEYWORD_COLUMNS == tuple(f"kw_{group}_5d" for group in na.KEYWORD_PATTERNS)
    assert all(column in na.NEWS_ATTENTION_COLUMNS for column in na.KEYWORD_COLUMNS)


def test_degenerate_source_column_is_excluded_from_the_screen_family() -> None:
    """The archive has a single source, so ``distinct_sources_5d`` is published
    but must not pad the BH denominator with a test that cannot reject.
    """
    assert "distinct_sources_5d" in na.NEWS_ATTENTION_COLUMNS
    assert "distinct_sources_5d" in na.SCREEN_EXCLUDED_COLUMNS
    assert "distinct_sources_5d" not in na.SCREEN_COLUMNS
    assert "distinct_authors_5d" in na.SCREEN_COLUMNS


# --------------------------------------------------------------------------
# attention surge
# --------------------------------------------------------------------------


def test_surge_is_count_over_the_mean_five_session_block() -> None:
    # 12 blocks of history, 24 articles in 60 sessions -> baseline 2 per block.
    assert na.attention_surge(6.0, 24.0, history_sessions=60) == pytest.approx(3.0)


def test_surge_denominator_uses_available_history_not_a_constant_twelve() -> None:
    """The archive starts 2024-01, so a January row has ~10 sessions of history.
    Dividing its 60-session total by a constant 12 blocks would invent a spike.
    """
    truncated = na.attention_surge(6.0, 12.0, history_sessions=10)
    naive = 6.0 / max(12.0 / 12.0, 1.0)
    assert truncated == pytest.approx(1.0)
    assert naive == pytest.approx(6.0)


def test_surge_floor_prevents_division_by_an_empty_baseline() -> None:
    assert na.attention_surge(3.0, 0.0, history_sessions=60) == pytest.approx(3.0)
    assert na.attention_surge(0.0, 0.0, history_sessions=60) == 0.0


# --------------------------------------------------------------------------
# builder kernels
# --------------------------------------------------------------------------


def test_rolling_window_sum_is_trailing_and_inclusive() -> None:
    daily = np.array([[1.0, 0.0, 2.0, 0.0, 1.0, 5.0]])
    rolled = builder._rolling_window_sum(daily, 3)
    assert rolled.tolist() == [[1.0, 1.0, 3.0, 2.0, 3.0, 6.0]]


def test_distinct_key_counts_merges_repeats_of_the_same_key() -> None:
    """One symbol, one author writing on sessions 0 and 1, a second author on
    session 0: the 3-session trailing count is 2 distinct authors, not 3 events.
    """
    counts = builder._distinct_key_counts(
        symbol_positions=np.array([0, 0, 0]),
        keys=np.array([7, 7, 9]),
        indices=np.array([0, 1, 0]),
        n_symbols=1,
        local_start=0,
        n_local=5,
        window=3,
    )
    assert counts.tolist() == [[2, 2, 2, 1, 0]]


def test_distinct_key_counts_is_empty_for_no_events() -> None:
    counts = builder._distinct_key_counts(
        symbol_positions=np.array([], dtype=np.int64),
        keys=np.array([], dtype=np.int64),
        indices=np.array([], dtype=np.int64),
        n_symbols=2,
        local_start=0,
        n_local=3,
        window=5,
    )
    assert counts.tolist() == [[0, 0, 0], [0, 0, 0]]


# --------------------------------------------------------------------------
# novelty over an article frame
# --------------------------------------------------------------------------


def _articles(rows: list[tuple[str, int, str]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["symbol", "session_index", "headline_norm"])
    return frame.sort_values(["symbol", "session_index"], kind="stable", ignore_index=True)


def test_novelty_first_headline_has_nothing_to_repeat() -> None:
    overlaps, first = builder.compute_novelty(_articles([("AAA", 0, "brand new story here")]))
    assert overlaps.tolist() == [0.0]
    assert first.tolist() == [True]


def test_novelty_scores_an_exact_repeat_from_an_earlier_session_as_one() -> None:
    frame = _articles(
        [
            ("AAA", 0, "chip maker beats revenue estimates"),
            ("AAA", 3, "chip maker beats revenue estimates"),
        ]
    )
    overlaps, first = builder.compute_novelty(frame, window=20)
    assert overlaps[1] == pytest.approx(1.0)
    assert first.tolist() == [True, True]


def test_novelty_window_expires_priors_older_than_the_lookback() -> None:
    frame = _articles(
        [
            ("AAA", 0, "chip maker beats revenue estimates"),
            ("AAA", 25, "chip maker beats revenue estimates"),
        ]
    )
    overlaps, _ = builder.compute_novelty(frame, window=20)
    assert overlaps[1] == 0.0


def test_same_session_duplicates_are_deduped_not_compared_to_each_other() -> None:
    """Three copies of one wire story in one session contribute one novelty
    term, and none of them counts as a repeat of the others (they are the same
    article, not a follow-up).
    """
    frame = _articles(
        [
            ("AAA", 4, "one identical wire story"),
            ("AAA", 4, "one identical wire story"),
            ("AAA", 4, "a genuinely different headline"),
        ]
    )
    overlaps, first = builder.compute_novelty(frame)
    assert first.tolist() == [True, False, True]
    assert overlaps.tolist() == [0.0, 0.0, 0.0]


def test_novelty_does_not_leak_across_symbols() -> None:
    frame = _articles(
        [
            ("AAA", 0, "chip maker beats revenue estimates"),
            ("BBB", 3, "chip maker beats revenue estimates"),
        ]
    )
    overlaps, _ = builder.compute_novelty(frame)
    assert overlaps.tolist() == [0.0, 0.0]
