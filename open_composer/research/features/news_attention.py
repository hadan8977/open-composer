"""Column contract and text primitives for the news-attention feature table.

Card: ``reports/research/hypotheses/H-20260916-02-news-attention-features.md``
(stage 1, **no LLM of any kind**). The table itself is built by
``scripts/build_news_attention_features.py`` into
``data/features/news_attention/{year}.parquet`` with the usual
``symbol, trade_date`` key, so it loads through
``panel.load_feature_panel(..., extra_feature_roots=[NEWS_ATTENTION_ROOT])``
and through the per-library loaders unchanged -- the same shape
``features/insider.py`` established for H-20260916-01.

This module holds the names and the *pure* text functions only, so that the
builder, the screener, the gate and the tests all resolve one definition of
"novelty" and one keyword dictionary and cannot drift apart. It imports
nothing but the standard library, matching ``feature_sets.py``'s rule that
importing a registry never touches the filesystem.

Point-in-time rule (the only visibility rule in this family)
-----------------------------------------------------------
An article is attributed to the **first US equity session whose 09:30 ET open
is at or after the article's ``visible_at``**. So a row dated ``D`` counts
exactly the articles that were already visible when ``D``'s opening auction
ran, and a strategy that trades at ``D``'s open may use the ``D`` row. There
is no other timestamp in this family: ``created_at``/``updated_at`` are
publisher bookkeeping and ``fetched_at`` is our own collection time, neither
of which is a visibility guarantee.

Window convention
-----------------
``*_5d`` / ``*_20d`` / ``*_60d`` are trailing windows of that many consecutive
US equity sessions **ending at the row's own ``trade_date`` inclusive**, over
attributed sessions (never publication timestamps). ``news_count_1d`` is the
row's own session alone, i.e. everything that became visible between the
previous session's open and this session's open.

Known archive limits, measured 2026-09-16 (they belong in the contract because
every consumer has to caveat them):

* the archive has exactly **one** ``source`` (``benzinga``) for all 684,876
  articles, so ``distinct_sources_5d`` is 1 whenever there is any news and 0
  otherwise -- it carries no cross-sectional information at all and is
  therefore listed in :data:`SCREEN_EXCLUDED_COLUMNS`. ``distinct_authors_5d``
  (509 distinct authors) is published beside it as the informative stand-in.
* coverage effectively starts 2024-01-01 (45 articles are visible before it),
  so the 60-session baseline of :func:`attention_surge` is truncated for the
  first ~60 sessions of 2024. The builder divides by the number of *available*
  5-session blocks rather than a fixed 12, and publishes
  ``news_history_sessions`` so a consumer can drop or flag those rows.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NEWS_ATTENTION_ROOT = ROOT / "data" / "features" / "news_attention"
NEWS_PACKETS_ROOT = ROOT / "data" / "features" / "news_packets"

#: Trailing windows, in US equity sessions.
SHORT_WINDOW = 5
LONG_WINDOW = 20
BASELINE_WINDOW = 60

#: Articles naming more than this many symbols are market-wide roundups
#: ("10 stocks moving in Tuesday's session"), not stock-specific news. They
#: are dropped from attribution entirely rather than truncated to the first
#: ten, because truncation would silently invent a ranking among the named
#: tickers that the article does not have. The builder reports how many
#: articles this removes.
MAX_SYMBOL_FANOUT = 10

#: The fixed, rule-based (non-LLM) event dictionary. Matched case-insensitively
#: against the article **headline only** -- not the summary: summaries in this
#: archive include boilerplate disclaimers and "Benzinga Insights" template
#: paragraphs that fire these words on articles that are not about the event,
#: and a headline is the part a human skimming a feed actually reads. Each
#: pattern is a whole-word alternation; ``ceo`` deliberately does not match
#: "ceos" only by accident of the word boundary -- it does, and that is fine.
KEYWORD_PATTERNS: Mapping[str, tuple[str, ...]] = {
    "earnings": ("earnings", "eps", "quarterly results", "q1 results", "q2 results"),
    "guidance": ("guidance", "outlook", "forecasts?", "reaffirms"),
    "acquisition": ("acquisitions?", "acquires?", "acquired", "takeover", "to buy"),
    "merger": ("mergers?", "merges?", "merging", "combine with"),
    "lawsuit": ("lawsuits?", "sues", "sued", "litigation", "class action", "settlement"),
    "fda": ("fda", "clinical trial", "phase [123]", "phase i{1,3}"),
    "downgrade": ("downgrades?", "downgraded", "cuts price target", "lowers price target"),
    "upgrade": ("upgrades?", "upgraded", "raises price target", "boosts price target"),
    "ceo": ("ceo", "chief executive"),
}

#: ``{group: compiled whole-word alternation}``, built once at import.
KEYWORD_REGEXES: Mapping[str, re.Pattern[str]] = {
    group: re.compile(r"\b(?:" + "|".join(patterns) + r")\b", re.IGNORECASE)
    for group, patterns in KEYWORD_PATTERNS.items()
}

#: Keyword feature column names, in dictionary order.
KEYWORD_COLUMNS: tuple[str, ...] = tuple(
    f"kw_{group}_{SHORT_WINDOW}d" for group in KEYWORD_PATTERNS
)

#: Non-key feature columns of ``data/features/news_attention/{year}.parquet``,
#: in table order.
NEWS_ATTENTION_COLUMNS: tuple[str, ...] = (
    "news_count_1d",
    "news_count_5d",
    "news_count_20d",
    "attention_surge_5d",
    "distinct_sources_5d",
    "distinct_authors_5d",
    "novelty_5d",
    "days_since_last_news",
    *KEYWORD_COLUMNS,
)

#: Columns carried in the table as diagnostics, never scored as factors.
NEWS_ATTENTION_METADATA_COLUMNS: tuple[str, ...] = (
    "visible_at",
    "news_count_60d",
    "news_baseline_5d",
    "novelty_basis_5d",
    "news_history_sessions",
)

#: Feature columns deliberately **excluded** from the screener's BH-FDR family,
#: with the reason. Excluding a constant is not cherry-picking: a column with
#: no cross-sectional variance has an undefined rank IC, so including it would
#: only pad the denominator with a test that cannot reject anything.
SCREEN_EXCLUDED_COLUMNS: Mapping[str, str] = {
    "distinct_sources_5d": (
        "the archive has a single source (benzinga) for all 684,876 articles, "
        "so this column is 1 whenever news_count_5d > 0 and 0 otherwise; "
        "distinct_authors_5d is its informative stand-in"
    ),
}

#: The columns the screener actually tests, i.e. the pre-registered family.
SCREEN_COLUMNS: tuple[str, ...] = tuple(
    column for column in NEWS_ATTENTION_COLUMNS if column not in SCREEN_EXCLUDED_COLUMNS
)

_NON_WORD = re.compile(r"[^0-9a-z]+")


def normalize_headline(text: str | None) -> str:
    """Lowercased, punctuation-stripped, whitespace-collapsed headline.

    Used for both exact-duplicate detection and shingling, so "AAPL Q3 Beats!"
    and "aapl q3 beats" are one headline rather than two.
    """
    if not text:
        return ""
    return _NON_WORD.sub(" ", text.lower()).strip()


def word_trigrams(text: str | None) -> frozenset[tuple[str, ...]]:
    """Word-level 3-grams of ``text`` (already normalized or not).

    Word trigrams rather than character trigrams: the repetition this feature
    must detect is *templated wording* ("shares are trading higher after the
    company reported"), and character trigrams score any two English headlines
    as ~40% similar, which would make every novelty value small and the
    cross-section flat. Headlines with fewer than three tokens fall back to
    their token set (as 1-grams) so that a two-word headline is still
    comparable to itself rather than silently scoring as maximally novel.
    """
    tokens = normalize_headline(text).split()
    if not tokens:
        return frozenset()
    if len(tokens) < 3:
        return frozenset((token,) for token in tokens)
    return frozenset(
        (tokens[index], tokens[index + 1], tokens[index + 2]) for index in range(len(tokens) - 2)
    )


def jaccard(left: frozenset[tuple[str, ...]], right: frozenset[tuple[str, ...]]) -> float:
    """``|A n B| / |A u B|``; 0.0 when either side is empty (an empty headline
    is not "identical" to anything, it is unmeasurable, and 0.0 -- maximally
    novel -- is the reading that never invents repetition that is not there).
    """
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    if intersection == 0:
        return 0.0
    return intersection / len(left | right)


def max_overlap(
    trigrams: frozenset[tuple[str, ...]],
    priors: Iterable[frozenset[tuple[str, ...]]],
) -> float:
    """Largest :func:`jaccard` between ``trigrams`` and any prior headline.

    0.0 when ``priors`` is empty -- a first-ever headline for a symbol has
    nothing to repeat, so it is fully novel.
    """
    best = 0.0
    for prior in priors:
        value = jaccard(trigrams, prior)
        if value > best:
            best = value
            if best >= 1.0:
                return 1.0
    return best


def novelty_from_overlaps(overlaps: Sequence[float]) -> float:
    """``1 - mean(overlaps)``; ``nan`` for an empty sequence (no news in the
    window means novelty is *undefined*, not 1.0 -- conflating "nothing was
    written" with "everything written was new" is exactly the confusion the
    ``news_count_*`` columns exist to keep separate).
    """
    if not overlaps:
        return float("nan")
    return 1.0 - (sum(overlaps) / len(overlaps))


def keyword_hits(headline: str | None) -> dict[str, bool]:
    """``{group: whether the headline matches that group}`` for every group in
    :data:`KEYWORD_PATTERNS`. A headline may match several groups.
    """
    text = headline or ""
    return {group: bool(regex.search(text)) for group, regex in KEYWORD_REGEXES.items()}


def attention_surge(
    count_5d: float,
    count_60d: float,
    *,
    history_sessions: int,
    window: int = SHORT_WINDOW,
    baseline_window: int = BASELINE_WINDOW,
) -> float:
    """``count_5d / max(mean 5-session count over the trailing 60 sessions, 1)``.

    The denominator is the trailing ``baseline_window``-session total divided
    by the number of ``window``-session blocks that the **archive actually
    covers** (``history_sessions``, floored at one block), not by a fixed 12.
    With a fixed 12 every early-2024 row would show a spuriously large surge
    purely because the news archive starts 2024-01-01 and the denominator was
    counting sessions that no collector ever saw.

    The baseline includes the current 5-session window. That makes the measure
    deliberately conservative -- a spike has to beat its own contribution to
    its baseline, and the maximum attainable value is the number of blocks
    (12 on a full history) -- and it avoids the arbitrary "skip the last 5
    sessions" choice, which would make the feature discontinuous in a way no
    published attention measure is.

    The ``max(..., 1)`` floor is the card's own: without it, a stock with no
    news for 60 sessions and one article today would have an infinite surge.
    """
    blocks = max(history_sessions, window) / window
    baseline = max(count_60d / blocks, 1.0)
    return count_5d / baseline
