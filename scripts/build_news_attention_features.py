"""H-20260916-02 stage 1: point-in-time news attention / novelty features, **no LLM**.

Card: ``reports/research/hypotheses/H-20260916-02-news-attention-features.md``
(stage 1 only -- "第 1 阶段（无 LLM）". Nothing in this file calls, imports or
depends on a language model; the keyword dictionary is a fixed regex table in
``open_composer/research/features/news_attention.py``.)

Input: ``data/features/news_packets/{2024,2025,2026}.parquet`` (684,876 Alpaca /
Benzinga articles; columns ``id, created_at, updated_at, symbols, headline,
summary, source, url, author, fetched_at, visible_at``).
Output: ``data/features/news_attention/{year}.parquet`` -- one row per
``(trade_date, symbol)`` for the point-in-time top-``--top-n`` ADV cohort, in
the same ``symbol, trade_date`` key shape every other feature library under
``data/features/`` uses.

Point-in-time rule (the only visibility rule in this file)
----------------------------------------------------------
An article is attributed to the **first US equity session whose 09:30 ET open
is at or after its ``visible_at``**. A row dated ``D`` therefore counts exactly
the articles that were already public when ``D``'s opening auction ran, and a
strategy that trades at ``D``'s open may read the ``D`` row. Concretely: an
article visible at 2024-03-05 14:12 ET lands on 2024-03-06; one visible at
2024-03-06 09:29:59 ET lands on 2024-03-06; one visible at 09:30:01 lands on
2024-03-07. ``created_at`` / ``updated_at`` (publisher bookkeeping -- the
archive's files are partitioned by ``updated_at``, which is why a 2011 article
sits in ``2024.parquet``) and ``fetched_at`` (our own collection time, all
2026-09-09) are never used as visibility.

Window convention
-----------------
``*_5d`` / ``*_20d`` / ``*_60d`` are trailing windows of that many consecutive
US equity sessions ending at the row's own ``trade_date`` **inclusive**, over
attributed sessions. ``news_count_1d`` is the row's own session alone, i.e.
everything that became visible between the previous session's open and this
session's open.

Multi-symbol articles
---------------------
An article is attributed to **every** symbol it lists (a joint article about
NVDA and AMD is news for both). Articles listing more than
``MAX_SYMBOL_FANOUT`` = 10 symbols are dropped from attribution entirely -- they
are market-wide roundups ("12 stocks moving in Tuesday's session"), not
stock-specific news, and truncating to the first ten would invent a ranking the
article does not have. The count of dropped articles is in the manifest and in
the report. Articles listing no symbol at all are also dropped.

Feature definitions (exact, and this docstring is the specification)
--------------------------------------------------------------------
Let ``A(S, w)`` be the articles attributed to symbol ``S`` in the trailing
window ``w`` ending at ``D``.

``news_count_1d`` / ``news_count_5d`` / ``news_count_20d``
    ``|A(S, 1)|``, ``|A(S, 5)|``, ``|A(S, 20)|``.
``attention_surge_5d``
    ``news_count_5d / max(news_count_60d / blocks, 1)`` where ``blocks`` is the
    number of 5-session blocks the news archive actually covers inside the
    trailing 60 sessions (``max(news_history_sessions, 5) / 5``), floored at 1
    block. See ``features.news_attention.attention_surge`` for why the baseline
    includes the current window and why the divisor is not the constant 12.
``distinct_sources_5d``
    Distinct ``source`` values in ``A(S, 5)``. **Degenerate in this archive**:
    every one of the 684,876 articles has ``source == "benzinga"``, so this
    column is 1 whenever there is news and 0 otherwise. It is published because
    the card asks for it, is excluded from the screener's BH family
    (``features.news_attention.SCREEN_EXCLUDED_COLUMNS``), and
    ``distinct_authors_5d`` (509 distinct authors) is published beside it as the
    informative stand-in.
``distinct_authors_5d``
    Distinct ``author`` values in ``A(S, 5)``.
``novelty_5d``
    ``1 - mean over a in A(S, 5) of maxoverlap(a)``, where ``maxoverlap(a)`` is
    the largest word-3-gram Jaccard similarity between ``a``'s headline and any
    of ``S``'s **other** headlines from the 20 sessions strictly before ``a``'s
    own attributed session. Exact duplicate headlines are collapsed first, per
    symbol and per session, so a wire story repeated three times in one day
    counts once. ``null`` when ``A(S, 5)`` is empty (novelty of nothing is
    undefined, not 1.0).

    Disclosed reading: "the prior 20 days" is taken **per headline** (the 20
    sessions before that headline), not per row ``D`` (the 20 sessions before
    ``D``'s 5-session window). Both readings match the card's wording; the
    per-headline one is computable once per article instead of once per
    (article, ``D``) pair, and it judges every headline against what a reader
    had actually already seen when it appeared. The per-``D`` variant is
    registered as an unused variant of the ``news_attention_features`` family.
``kw_<group>_5d``
    Number of articles in ``A(S, 5)`` whose **headline** matches the fixed
    ``KEYWORD_PATTERNS`` group (earnings / guidance / acquisition / merger /
    lawsuit / fda / downgrade / upgrade / ceo). Headline only, not summary: the
    archive's summaries carry template boilerplate that fires these words on
    articles that are not about the event.
``days_since_last_news``
    Sessions since the most recent session with at least one article for ``S``
    (0 on a session that has news), over the archive's whole history -- not only
    the 60-session window. ``null`` when the archive has never carried an
    article for ``S``. **Floored by the archive start**: coverage effectively
    begins 2024-01-01, so a January 2024 value of 12 can mean "12 sessions" or
    "no article has ever been collected".

Symbol-shuffle placebo (required by the card) -- two modes, one of them rejected
--------------------------------------------------------------------------------
``--shuffle-symbols-seed N`` randomizes which company each article is about.
``--shuffle-symbols-mode`` picks how, and the two modes are **not** equally good
controls:

``relabel`` (default, and the mode this round's placebo uses)
    One single random bijection of the whole point-in-time universe, drawn once
    from the seed and applied to every article for the entire sample: every
    article that named ``AAPL`` now names ``pi(AAPL)`` instead. Each pseudo-symbol's
    news history is therefore *exactly* some real symbol's news history --
    identical counts, identical heavy tail, identical week-to-week persistence,
    identical keyword mix -- and the **only** thing destroyed is the pairing
    between a news time series and a return time series. That is what a placebo
    for this family has to destroy, and nothing else.
``draw``
    Per article, the same number of symbols drawn uniformly without replacement
    from that session's PIT cohort. Rejected as this round's control, with the
    measurement that rejected it: it flattens the attention distribution, because
    real coverage is heavy-tailed (a mega-cap gets 40 articles a week, most names
    get none) and a uniform draw spreads the same articles evenly. Measured
    2026-09-16: the share of stock-days with any article in the trailing 5
    sessions goes from **69.2% (real) to 97.4% (draw)**. A control that changes
    the feature's own distribution is not a size-matched control -- it is a
    different, easier experiment, and the ``no news in 20 sessions`` tier nearly
    vanishes inside it. Kept in the CLI so the comparison stays reproducible.

Output goes to a separate root
(``data/features/news_attention_placebo_{mode}_seed{N}/``) so a placebo table can
never be mistaken for the real one. Note what neither mode can destroy: both keep
the calendar, so a feature that is really a market-wide time-series signal in
disguise would survive both -- which is why the round also runs the within-week
same-size state shuffle in ``kernel/news_gate.shuffle_states_within_date``.

Stages (each resumable; re-running a stage whose outputs exist is a no-op
unless ``--force``)::

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/build_news_attention_features.py articles \\
        > /tmp/news_attention_articles.log 2>&1 &
    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/build_news_attention_features.py features \\
        > /tmp/news_attention_features.log 2>&1 &
    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/build_news_attention_features.py weekly-panel

``all`` runs the three in order. ``articles`` writes the exploded, attributed
article table to ``<out-root>/_articles/{year}.parquet`` (the expensive pass
over the packets); ``features`` turns it into the dense per-(session, symbol)
table one output year at a time; ``weekly-panel`` collapses that to the Friday
x top-``--weekly-top-n`` grid the screener scores on.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from open_composer.market_calendar import us_equity_session_dates  # noqa: E402
from open_composer.research.features.news_attention import (  # noqa: E402
    BASELINE_WINDOW,
    KEYWORD_PATTERNS,
    KEYWORD_REGEXES,
    LONG_WINDOW,
    MAX_SYMBOL_FANOUT,
    NEWS_ATTENTION_COLUMNS,
    NEWS_ATTENTION_METADATA_COLUMNS,
    NEWS_PACKETS_ROOT,
    SHORT_WINDOW,
    max_overlap,
    normalize_headline,
    word_trigrams,
)
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    universe_as_of_calendar_month,
    weekly_rebalance_dates,
)

UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
DEFAULT_OUT_ROOT = ROOT / "data" / "features" / "news_attention"
ARTICLES_DIRNAME = "_articles"
ARTICLES_INDEX_NAME = "_articles_index.json"
WEEKLY_PANEL_NAME = "screening_panel_weekly.parquet"
MANIFEST_NAME = "_build_manifest.json"

NEW_YORK = ZoneInfo("America/New_York")
FEATURE_UNIVERSE_TOP_N = 1000
WEEKLY_PANEL_TOP_N = 500
#: The packet files' own names. They are partitioned by ``updated_at`` year, so
#: all of them are scanned and rows are re-bucketed by attributed session year.
PACKET_YEARS: tuple[int, ...] = (2024, 2025, 2026)
#: Output years. 2023 gets no file: the archive holds 45 articles visible before
#: 2024-01-01, which is not a cross-section.
FEATURE_YEARS: tuple[int, ...] = (2024, 2025, 2026)
#: Session index warm-up start. 2023 is needed only so that January 2024 rows
#: have 59 prior sessions to look back over (all of them newsless, which is
#: what ``news_history_sessions`` records).
SESSION_START = date(2023, 9, 1)
READ_BATCH_ROWS = 40_000
PACKET_COLUMNS = ("id", "symbols", "headline", "author", "source", "visible_at")
#: Symbol-shuffle placebo modes; see the module docstring for why ``draw`` is
#: kept but not used as this round's control.
SHUFFLE_MODES: tuple[str, ...] = ("relabel", "draw")
DEFAULT_SHUFFLE_MODE = "relabel"


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


# --------------------------------------------------------------------------
# calendar
# --------------------------------------------------------------------------


def build_sessions(last_date: date) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """``(session dates, that session's 09:30 ET open in UTC)``.

    The second array is what ``visible_at`` is bisected against, so the
    attribution rule is one ``searchsorted`` and cannot drift from the
    docstring.
    """
    sessions = pd.DatetimeIndex(
        [pd.Timestamp(day) for day in us_equity_session_dates(SESSION_START, last_date)]
    )
    opens = pd.DatetimeIndex(
        [
            pd.Timestamp(day.date()).tz_localize(NEW_YORK).replace(hour=9, minute=30)
            for day in sessions
        ]
    ).tz_convert("UTC")
    return sessions, opens


def session_open_utc(trade_date: pd.Timestamp) -> pd.Timestamp:
    return (
        pd.Timestamp(trade_date.date())
        .tz_localize(NEW_YORK)
        .replace(hour=9, minute=30)
        .tz_convert("UTC")
    )


# --------------------------------------------------------------------------
# stage: articles
# --------------------------------------------------------------------------


def _articles_dir(out_root: Path) -> Path:
    return out_root / ARTICLES_DIRNAME


def _keyword_flags(headlines: pd.Series) -> dict[str, np.ndarray]:
    """One boolean array per keyword group, computed on the *article* level
    (before the symbol explode) so a 10-symbol article costs one regex pass.
    """
    return {
        group: headlines.str.contains(regex, regex=True, na=False).to_numpy()
        for group, regex in KEYWORD_REGEXES.items()
    }


def _cohort_symbol_arrays(
    sessions: pd.DatetimeIndex, universe_panel: pd.DataFrame, top_n: int
) -> tuple[dict[int, np.ndarray], set[str]]:
    """``{session index: that session's PIT cohort as an array}`` plus the union.

    The per-session arrays are what the symbol-shuffle placebo draws from, so
    the placebo can never assign an article to a symbol that was not in the
    tradable universe on that very session.
    """
    cohorts: dict[int, np.ndarray] = {}
    union: set[str] = set()
    cache: dict[pd.Period, np.ndarray] = {}
    for index, timestamp in enumerate(sessions):
        month = timestamp.to_period("M")
        if month not in cache:
            cohort = universe_as_of_calendar_month(universe_panel, timestamp, top_n=top_n)
            cache[month] = np.array(sorted(cohort), dtype=object)
        cohorts[index] = cache[month]
        union.update(cache[month].tolist())
    return cohorts, union


def stage_articles(
    *,
    out_root: Path,
    sessions: pd.DatetimeIndex,
    opens: pd.DatetimeIndex,
    universe_panel: pd.DataFrame,
    top_n: int,
    shuffle_seed: int | None,
    shuffle_mode: str,
    force: bool,
) -> dict[str, object]:
    """Explode the packets into ``(session, symbol, article)`` rows.

    One pass over each packet file, in row batches, writing one part file per
    (packet year, attributed session year) pair and then concatenating the
    parts per attributed year. Peak memory is one batch plus one packet year's
    exploded rows, not the whole archive.
    """
    target_dir = _articles_dir(out_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_root / ARTICLES_INDEX_NAME
    if index_path.exists() and not force:
        log(f"{index_path.name} already present -- reusing (checkpoint)")
        return json.loads(index_path.read_text())

    opens_values = opens.to_numpy()
    cohorts, universe_union = _cohort_symbol_arrays(sessions, universe_panel, top_n)
    log(f"PIT universe union (adv_rank <= {top_n}): {len(universe_union):,} symbols")
    rng = np.random.default_rng(shuffle_seed) if shuffle_seed is not None else None
    relabel: dict[str, str] | None = None
    if rng is not None and shuffle_mode == "relabel":
        ordered = np.array(sorted(universe_union), dtype=object)
        relabel = dict(zip(ordered.tolist(), rng.permutation(ordered).tolist(), strict=True))
        fixed = sum(1 for key, value in relabel.items() if key == value)
        log(
            f"placebo (relabel, seed={shuffle_seed}): one fixed bijection over "
            f"{len(relabel):,} universe symbols, {fixed} symbol(s) mapped to themselves"
        )

    stats = {
        "articles_read": 0,
        "articles_no_symbol": 0,
        "articles_over_fanout": 0,
        "articles_after_as_of": 0,
        "articles_before_sessions": 0,
        "articles_no_universe_symbol": 0,
        "articles_attributed": 0,
        "rows_attributed": 0,
    }
    parts: dict[int, list[Path]] = defaultdict(list)

    for packet_year in PACKET_YEARS:
        path = NEWS_PACKETS_ROOT / f"{packet_year}.parquet"
        if not path.exists():
            log(f"packets {packet_year}: missing -- skipped")
            continue
        buffers: dict[int, list[pd.DataFrame]] = defaultdict(list)
        reader = pq.ParquetFile(path)
        for batch in reader.iter_batches(batch_size=READ_BATCH_ROWS, columns=list(PACKET_COLUMNS)):
            frame = batch.to_pandas()
            stats["articles_read"] += len(frame)
            counts = frame["symbols"].map(lambda value: 0 if value is None else len(value))
            no_symbol = counts == 0
            over_fanout = counts > MAX_SYMBOL_FANOUT
            stats["articles_no_symbol"] += int(no_symbol.sum())
            stats["articles_over_fanout"] += int(over_fanout.sum())
            frame = frame.loc[~(no_symbol | over_fanout)]
            if frame.empty:
                continue
            visible = pd.to_datetime(frame["visible_at"], utc=True).to_numpy()
            index = np.searchsorted(opens_values, visible, side="left")
            after = index >= len(opens_values)
            stats["articles_after_as_of"] += int(after.sum())
            # An article visible before the warm-up window's first session open
            # has no attributable session here. ``searchsorted`` would silently
            # pile all of them onto session 0; they are dropped instead (there
            # are ~20, all 2011-2017 re-runs that the packets' ``updated_at``
            # partitioning dragged into the 2024 file).
            before = visible < opens_values[0]
            stats["articles_before_sessions"] += int(before.sum())
            drop = after | before
            frame = frame.loc[~drop]
            index = index[~drop]
            if frame.empty:
                continue

            keywords = _keyword_flags(frame["headline"].fillna(""))
            kept_symbols: list[np.ndarray] = []
            for listed in frame["symbols"].to_numpy():
                kept = [str(symbol) for symbol in listed if str(symbol) in universe_union]
                kept_symbols.append(np.array(kept, dtype=object))
            sizes = np.array([len(item) for item in kept_symbols], dtype=np.int64)
            empty = sizes == 0
            stats["articles_no_universe_symbol"] += int(empty.sum())
            if relabel is not None:
                # Fixed bijection: each article keeps its fan-out and every
                # pseudo-symbol inherits one real symbol's entire news history.
                kept_symbols = [
                    np.array([relabel.get(symbol, symbol) for symbol in item], dtype=object)
                    for item in kept_symbols
                ]
            elif rng is not None:
                kept_symbols = [
                    (
                        rng.choice(cohorts[session], size=size, replace=False)
                        if size and len(cohorts[session]) >= size
                        else np.array([], dtype=object)
                    )
                    for session, size in zip(index, sizes, strict=True)
                ]
                sizes = np.array([len(item) for item in kept_symbols], dtype=np.int64)
                empty = sizes == 0
            keep = ~empty
            if not keep.any():
                continue
            stats["articles_attributed"] += int(keep.sum())
            repeat = sizes[keep]
            exploded = pd.DataFrame(
                {
                    "session_index": np.repeat(index[keep], repeat).astype(np.int32),
                    "symbol": np.concatenate([kept_symbols[i] for i in np.flatnonzero(keep)]),
                    "article_id": np.repeat(frame["id"].to_numpy()[keep], repeat),
                    "author": np.repeat(frame["author"].fillna("").to_numpy()[keep], repeat),
                    "source": np.repeat(frame["source"].fillna("").to_numpy()[keep], repeat),
                    "headline_norm": np.repeat(
                        frame["headline"].fillna("").map(normalize_headline).to_numpy()[keep],
                        repeat,
                    ),
                }
            )
            for group in KEYWORD_PATTERNS:
                exploded[f"kw_{group}"] = np.repeat(keywords[group][keep], repeat)
            stats["rows_attributed"] += len(exploded)
            years = sessions[exploded["session_index"].to_numpy()].year
            for year in np.unique(years):
                buffers[int(year)].append(exploded.loc[years == year])
            del exploded, frame

        for year, frames in buffers.items():
            part = target_dir / f"part-{packet_year}-{year}.parquet"
            combined = pd.concat(frames, ignore_index=True)
            combined.to_parquet(part, index=False, compression="zstd")
            parts[year].append(part)
            log(f"packets {packet_year} -> session year {year}: {len(combined):,} rows")
            del combined, frames
        del buffers

    first_session_index = None
    for year in sorted(parts):
        frames = [pd.read_parquet(part) for part in parts[year]]
        combined = pd.concat(frames, ignore_index=True).sort_values(
            ["symbol", "session_index"], kind="stable", ignore_index=True
        )
        combined.to_parquet(target_dir / f"{year}.parquet", index=False, compression="zstd")
        candidate = int(combined["session_index"].min())
        first_session_index = (
            candidate if first_session_index is None else min(first_session_index, candidate)
        )
        log(f"session year {year}: {len(combined):,} attributed (article, symbol) rows")
        del combined, frames
    for year in sorted(parts):
        for part in parts[year]:
            part.unlink()

    payload = {
        "stats": stats,
        "first_session_index": first_session_index,
        "first_session_date": (
            sessions[first_session_index].date().isoformat()
            if first_session_index is not None
            else None
        ),
        "years": sorted(parts),
        "sessions_first": sessions[0].date().isoformat(),
        "sessions_last": sessions[-1].date().isoformat(),
        "shuffle_symbols_seed": shuffle_seed,
        "shuffle_symbols_mode": shuffle_mode if shuffle_seed is not None else None,
        "max_symbol_fanout": MAX_SYMBOL_FANOUT,
        "universe_top_n": top_n,
        "universe_union_symbols": len(universe_union),
    }
    index_path.write_text(json.dumps(payload, indent=2) + "\n")
    log(f"wrote {index_path.name}: {stats}")
    return payload


# --------------------------------------------------------------------------
# novelty
# --------------------------------------------------------------------------


def compute_novelty(
    frame: pd.DataFrame, *, window: int = LONG_WINDOW
) -> tuple[np.ndarray, np.ndarray]:
    """``(max_overlap, is_first_occurrence)`` per (symbol, article) row.

    ``max_overlap`` is the largest word-3-gram Jaccard similarity between this
    row's headline and any of that symbol's distinct headlines from the
    ``window`` sessions **strictly before** this row's own session (0.0 when
    there are none -- nothing to repeat).

    ``is_first_occurrence`` is the "dedupe exact headlines first" half of the
    card's definition: it is ``True`` for the first row of each
    ``(symbol, session, normalized headline)`` group, so a wire story that
    appears three times in one session contributes one term to that session's
    novelty mean instead of three. Deduplication is **within a session, not
    across the window**: the same headline reappearing a week later is a genuine
    repeat and must score overlap ~1.0 against its earlier self, which is the
    entire point of the feature.

    ``frame`` needs ``symbol``, ``session_index``, ``headline_norm`` and must be
    sorted by ``(symbol, session_index)``. Trigram sets are memoized per
    distinct normalized headline, which is what keeps this affordable: the
    archive has far fewer distinct headlines than (article, symbol) rows.
    """
    symbols = frame["symbol"].to_numpy()
    session_index = frame["session_index"].to_numpy()
    headlines = frame["headline_norm"].to_numpy()
    total = len(frame)
    overlaps = np.zeros(total, dtype=np.float64)
    first = np.zeros(total, dtype=bool)
    trigram_cache: dict[str, frozenset[tuple[str, ...]]] = {}

    def trigrams(text: str) -> frozenset[tuple[str, ...]]:
        cached = trigram_cache.get(text)
        if cached is None:
            cached = word_trigrams(text)
            trigram_cache[text] = cached
        return cached

    block_start = 0
    while block_start < total:
        block_end = block_start
        while block_end < total and symbols[block_end] == symbols[block_start]:
            block_end += 1
        low = block_start
        position = block_start
        while position < block_end:
            session = session_index[position]
            group_end = position
            while group_end < block_end and session_index[group_end] == session:
                group_end += 1
            while low < position and session_index[low] < session - window:
                low += 1
            prior_texts = {headlines[other] for other in range(low, position)}
            prior_texts.discard("")
            prior_trigrams = [trigrams(text) for text in prior_texts]
            seen: set[str] = set()
            for row in range(position, group_end):
                text = headlines[row]
                if text in seen:
                    continue
                seen.add(text)
                first[row] = True
                if prior_trigrams and text:
                    overlaps[row] = max_overlap(trigrams(text), prior_trigrams)
            position = group_end
        block_start = block_end
    return overlaps, first


# --------------------------------------------------------------------------
# dense per-year computation
# --------------------------------------------------------------------------


def _rolling_window_sum(daily: np.ndarray, window: int) -> np.ndarray:
    """Trailing ``window``-column inclusive sum along axis 1."""
    cumulative = np.cumsum(daily, axis=1)
    shifted = np.zeros_like(cumulative)
    shifted[:, window:] = cumulative[:, :-window]
    return cumulative - shifted


def _distinct_key_counts(
    *,
    symbol_positions: np.ndarray,
    keys: np.ndarray,
    indices: np.ndarray,
    n_symbols: int,
    local_start: int,
    n_local: int,
    window: int,
) -> np.ndarray:
    """Distinct ``keys`` with at least one event in the trailing ``window``
    sessions, per (symbol, local session) cell.

    Same interval-merge algorithm as
    ``scripts/build_insider_features.py::_distinct_owner_counts`` (each event at
    global index ``v`` covers ``[v, v + window - 1]``; overlapping intervals for
    one (symbol, key) pair are merged so a key appearing twice in a window
    counts once), reimplemented here rather than imported so that neither
    card's feature table changes meaning when the other's builder is edited.
    """
    counts = np.zeros((n_symbols, n_local), dtype=np.int32)
    if symbol_positions.size == 0:
        return counts
    order = np.lexsort((indices, keys, symbol_positions))
    symbol_positions = symbol_positions[order]
    keys = keys[order]
    indices = indices[order]

    same_group = np.empty(symbol_positions.size, dtype=bool)
    same_group[0] = False
    same_group[1:] = (symbol_positions[1:] == symbol_positions[:-1]) & (keys[1:] == keys[:-1])
    contiguous = np.zeros(symbol_positions.size, dtype=bool)
    contiguous[1:] = same_group[1:] & ((indices[1:] - indices[:-1]) < window)
    starts = ~contiguous

    run_symbol = symbol_positions[starts]
    run_start = indices[starts]
    run_end = np.maximum.reduceat(indices, np.flatnonzero(starts)) + window - 1

    local_first = np.clip(run_start - local_start, 0, n_local)
    local_last = np.clip(run_end - local_start + 1, 0, n_local)
    keep = local_last > local_first
    if not keep.any():
        return counts
    difference = np.zeros((n_symbols, n_local + 1), dtype=np.int32)
    np.add.at(difference, (run_symbol[keep], local_first[keep]), 1)
    np.add.at(difference, (run_symbol[keep], local_last[keep]), -1)
    return np.cumsum(difference, axis=1)[:, :n_local].astype(np.int32)


def _read_article_window(
    articles_dir: Path, sessions: pd.DatetimeIndex, low: int, high: int
) -> pd.DataFrame:
    """Attributed article rows with ``low <= session_index <= high``."""
    years = sorted({int(sessions[low].year), int(sessions[high].year)})
    years = list(range(years[0], years[-1] + 1))
    frames = []
    for year in years:
        path = articles_dir / f"{year}.parquet"
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        frames.append(frame.loc[frame["session_index"].between(low, high)])
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(
        ["symbol", "session_index"], kind="stable", ignore_index=True
    )


def build_year(
    year: int,
    *,
    articles_dir: Path,
    sessions: pd.DatetimeIndex,
    universe_panel: pd.DataFrame,
    top_n: int,
    archive_first_session: int,
) -> pd.DataFrame:
    year_positions = np.flatnonzero(sessions.year == year)
    if year_positions.size == 0:
        return pd.DataFrame()
    first_target = int(year_positions[0])
    last_target = int(year_positions[-1])
    # The dense grid starts 59 sessions before the first output row (the 60-day
    # baseline); novelty additionally needs 20 sessions of headlines before the
    # grid's own first session, so articles are read from further back still.
    local_start = max(0, first_target - (BASELINE_WINDOW - 1))
    n_local = last_target - local_start + 1
    target_offset = first_target - local_start
    read_low = max(0, local_start - LONG_WINDOW)

    target_dates = sessions[first_target : last_target + 1]
    cohorts = {
        timestamp: universe_as_of_calendar_month(universe_panel, timestamp, top_n=top_n)
        for timestamp in target_dates
    }
    symbols = sorted(set().union(*cohorts.values()))
    if not symbols:
        return pd.DataFrame()
    symbol_position = {symbol: position for position, symbol in enumerate(symbols)}
    n_symbols = len(symbols)

    articles = _read_article_window(articles_dir, sessions, read_low, last_target)
    if not articles.empty:
        articles = articles.loc[articles["symbol"].astype(str).isin(symbol_position)]
    if articles.empty:
        return pd.DataFrame()
    log(f"{year}: {len(articles):,} attributed rows in the read window; computing novelty ...")
    overlaps, first_occurrence = compute_novelty(articles)
    articles["max_overlap"] = overlaps
    articles["novelty_term"] = first_occurrence
    articles = articles.loc[articles["session_index"] >= local_start]
    if articles.empty:
        return pd.DataFrame()

    positions = articles["symbol"].astype(str).map(symbol_position).to_numpy(dtype=np.int64)
    globals_ = articles["session_index"].to_numpy(dtype=np.int64)
    locals_ = globals_ - local_start
    ones = np.ones(1, dtype=np.float64)

    daily: dict[str, np.ndarray] = {
        name: np.zeros((n_symbols, n_local), dtype=np.float64)
        for name in ("count", "novelty_sum", "novelty_count", *KEYWORD_PATTERNS)
    }
    np.add.at(daily["count"], (positions, locals_), ones)
    # Novelty's numerator and denominator use the deduped headline rows only
    # (see ``compute_novelty``); the raw article count does not dedupe, because
    # "how much was written" and "how much of it was new" are different
    # questions and the card asks for both.
    term = articles["novelty_term"].to_numpy(dtype=bool)
    np.add.at(
        daily["novelty_sum"],
        (positions[term], locals_[term]),
        articles["max_overlap"].to_numpy(dtype=float)[term],
    )
    np.add.at(daily["novelty_count"], (positions[term], locals_[term]), ones)
    for group in KEYWORD_PATTERNS:
        flag = articles[f"kw_{group}"].to_numpy(dtype=bool)
        np.add.at(daily[group], (positions[flag], locals_[flag]), ones)

    rolled_5 = {name: _rolling_window_sum(array, SHORT_WINDOW) for name, array in daily.items()}
    count_20 = _rolling_window_sum(daily["count"], LONG_WINDOW)
    count_60 = _rolling_window_sum(daily["count"], BASELINE_WINDOW)

    author_codes = pd.factorize(articles["author"].astype(str))[0].astype(np.int64)
    source_codes = pd.factorize(articles["source"].astype(str))[0].astype(np.int64)
    distinct_authors = _distinct_key_counts(
        symbol_positions=positions,
        keys=author_codes,
        indices=globals_,
        n_symbols=n_symbols,
        local_start=local_start,
        n_local=n_local,
        window=SHORT_WINDOW,
    )
    distinct_sources = _distinct_key_counts(
        symbol_positions=positions,
        keys=source_codes,
        indices=globals_,
        n_symbols=n_symbols,
        local_start=local_start,
        n_local=n_local,
        window=SHORT_WINDOW,
    )

    # days_since_last_news uses the whole archive, not just the grid: the carry-in
    # is the last session with an article strictly before the grid starts.
    last_news = np.full((n_symbols, n_local), -1, dtype=np.int64)
    np.maximum.at(last_news, (positions, locals_), globals_)
    carry = _carry_in_last_news(articles_dir, symbol_position, local_start)
    last_news[:, 0] = np.maximum(last_news[:, 0], carry)
    np.maximum.accumulate(last_news, axis=1, out=last_news)

    window = slice(target_offset, n_local)
    n_target = n_local - target_offset
    global_indices = np.arange(first_target, last_target + 1, dtype=np.int64)
    days_since = np.where(
        last_news[:, window] < 0, np.nan, global_indices[None, :] - last_news[:, window]
    )
    history_sessions = np.clip(global_indices - archive_first_session + 1, 0, BASELINE_WINDOW)
    blocks = np.maximum(history_sessions, SHORT_WINDOW) / SHORT_WINDOW
    count_5d = rolled_5["count"][:, window]
    baseline = np.maximum(count_60[:, window] / blocks[None, :], 1.0)
    novelty_count_5d = rolled_5["novelty_count"][:, window]
    with np.errstate(invalid="ignore", divide="ignore"):
        novelty = np.where(
            novelty_count_5d > 0,
            1.0 - rolled_5["novelty_sum"][:, window] / novelty_count_5d,
            np.nan,
        )

    mask = np.zeros((n_symbols, n_target), dtype=bool)
    for column, timestamp in enumerate(target_dates):
        cohort = cohorts[timestamp]
        if not cohort:
            continue
        rows = [symbol_position[symbol] for symbol in cohort if symbol in symbol_position]
        mask[rows, column] = True
    selected = np.flatnonzero(mask.ravel())
    if selected.size == 0:
        return pd.DataFrame()

    symbol_array = np.repeat(np.array(symbols, dtype=object), n_target)
    date_array = np.tile(target_dates.to_numpy(), n_symbols)
    frame = pd.DataFrame(
        {
            "symbol": symbol_array[selected],
            "trade_date": date_array[selected],
            "news_count_1d": daily["count"][:, window].ravel()[selected],
            "news_count_5d": count_5d.ravel()[selected],
            "news_count_20d": count_20[:, window].ravel()[selected],
            "attention_surge_5d": (count_5d / baseline).ravel()[selected],
            "distinct_sources_5d": distinct_sources[:, window].ravel()[selected],
            "distinct_authors_5d": distinct_authors[:, window].ravel()[selected],
            "novelty_5d": novelty.ravel()[selected],
            "days_since_last_news": days_since.ravel()[selected],
            **{
                f"kw_{group}_{SHORT_WINDOW}d": rolled_5[group][:, window].ravel()[selected]
                for group in KEYWORD_PATTERNS
            },
            "news_count_60d": count_60[:, window].ravel()[selected],
            "news_baseline_5d": baseline.ravel()[selected],
            "novelty_basis_5d": novelty_count_5d.ravel()[selected],
            "news_history_sessions": np.tile(history_sessions, n_symbols)[selected],
        }
    )
    frame["symbol"] = frame["symbol"].astype("string")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    numeric = [
        *NEWS_ATTENTION_COLUMNS,
        *(column for column in NEWS_ATTENTION_METADATA_COLUMNS if column != "visible_at"),
    ]
    for column in numeric:
        frame[column] = frame[column].astype("float32")
    visible_at_map = {
        timestamp: session_open_utc(timestamp) for timestamp in frame["trade_date"].unique()
    }
    frame["visible_at"] = frame["trade_date"].map(visible_at_map)
    ordered = [
        "symbol",
        "trade_date",
        *NEWS_ATTENTION_COLUMNS,
        *NEWS_ATTENTION_METADATA_COLUMNS,
    ]
    return (
        frame[ordered].sort_values(["symbol", "trade_date"], kind="stable").reset_index(drop=True)
    )


def _carry_in_last_news(
    articles_dir: Path,
    symbol_position: dict[str, int],
    local_start: int,
) -> np.ndarray:
    """Last session index with an article strictly before ``local_start``, per
    symbol -- the carry-in for ``days_since_last_news`` so that a January row
    does not report "no news ever" just because the dense grid starts there.

    Every attributed-article year file is scanned (there are three, two columns
    each), which is cheap and cannot miss a symbol whose last article predates
    the grid by more than a year. The archive itself starts 2024-01, so a
    ``-1`` here genuinely means "the collector never saw an article for this
    symbol", which the manifest's ``first_session_date`` lets a consumer
    distinguish from a real 200-session silence.
    """
    carry = np.full(len(symbol_position), -1, dtype=np.int64)
    for path in sorted(articles_dir.glob("[0-9][0-9][0-9][0-9].parquet")):
        frame = pd.read_parquet(path, columns=["symbol", "session_index"])
        frame = frame.loc[frame["session_index"] < local_start]
        if frame.empty:
            continue
        grouped = frame.groupby("symbol", sort=False)["session_index"].max()
        for symbol, value in grouped.items():
            position = symbol_position.get(str(symbol))
            if position is not None:
                carry[position] = max(carry[position], int(value))
    return carry


# --------------------------------------------------------------------------
# stage: features / weekly panel
# --------------------------------------------------------------------------


def stage_features(
    *,
    out_root: Path,
    sessions: pd.DatetimeIndex,
    universe_panel: pd.DataFrame,
    top_n: int,
    archive_first_session: int,
    force: bool,
) -> list[str]:
    articles_dir = _articles_dir(out_root)
    written: list[str] = []
    for year in FEATURE_YEARS:
        target = out_root / f"{year}.parquet"
        if target.exists() and not force:
            log(f"{year}: already built (checkpoint)")
            written.append(str(target))
            continue
        frame = build_year(
            year,
            articles_dir=articles_dir,
            sessions=sessions,
            universe_panel=universe_panel,
            top_n=top_n,
            archive_first_session=archive_first_session,
        )
        if frame.empty:
            log(f"{year}: no rows")
            continue
        temporary = target.with_suffix(".parquet.part")
        frame.to_parquet(temporary, index=False, compression="zstd")
        temporary.replace(target)
        written.append(str(target))
        log(
            f"{year}: {len(frame):,} rows, {frame['symbol'].nunique():,} symbols, "
            f"share with news in 5d = {float((frame['news_count_5d'] > 0).mean()):.2%}, "
            f"in 20d = {float((frame['news_count_20d'] > 0).mean()):.2%}"
        )
        del frame
    return written


def stage_weekly_panel(
    *, out_root: Path, sessions: pd.DatetimeIndex, top_n: int, force: bool
) -> Path | None:
    target = out_root / WEEKLY_PANEL_NAME
    if target.exists() and not force:
        log(f"{WEEKLY_PANEL_NAME} already present -- reusing (checkpoint)")
        return target
    universe_panel = load_universe_panel(UNIVERSE_ROOT)
    fridays = set(weekly_rebalance_dates(list(sessions)))
    frames: list[pd.DataFrame] = []
    for path in sorted(out_root.glob("[0-9][0-9][0-9][0-9].parquet")):
        frame = pd.read_parquet(path)
        frame = frame.loc[frame["trade_date"].isin(fridays)]
        if frame.empty:
            continue
        cohorts = {
            timestamp: universe_as_of_calendar_month(universe_panel, timestamp, top_n=top_n)
            for timestamp in frame["trade_date"].unique()
        }
        keep = [
            symbol in cohorts[timestamp]
            for symbol, timestamp in zip(frame["symbol"], frame["trade_date"], strict=True)
        ]
        frames.append(frame.loc[keep])
    if not frames:
        log("weekly panel: no rows")
        return None
    panel = pd.concat(frames, ignore_index=True)
    panel.insert(1, "friday_date", panel["trade_date"])
    panel = panel.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)
    temporary = target.with_suffix(".parquet.part")
    panel.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(target)
    log(
        f"weekly panel: {len(panel):,} rows, {panel['trade_date'].nunique():,} fridays, "
        f"{panel['symbol'].nunique():,} symbols -> {target}"
    )
    return target


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "stage", choices=("articles", "features", "weekly-panel", "all"), nargs="?", default="all"
    )
    parser.add_argument("--top-n", type=int, default=FEATURE_UNIVERSE_TOP_N)
    parser.add_argument("--weekly-top-n", type=int, default=WEEKLY_PANEL_TOP_N)
    parser.add_argument(
        "--shuffle-symbols-seed",
        type=int,
        default=None,
        help="Placebo: randomize which company each article is about. Separate output root.",
    )
    parser.add_argument(
        "--shuffle-symbols-mode",
        choices=SHUFFLE_MODES,
        default=DEFAULT_SHUFFLE_MODE,
        help=(
            "relabel (default): one fixed universe-wide bijection, preserving every "
            "feature's distribution and persistence. draw: per-article uniform draw from "
            "that session's cohort -- rejected as a control because it flattens coverage "
            "(69.2%% -> 97.4%% of stock-days with an article in 5 sessions)."
        ),
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help=(
            "Last feature date, YYYY-MM-DD. Defaults to the last session covered by "
            "the news archive's own last visible_at."
        ),
    )
    parser.add_argument("--out-root", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    return parser


def _archive_last_visible() -> pd.Timestamp:
    last = None
    for year in PACKET_YEARS:
        path = NEWS_PACKETS_ROOT / f"{year}.parquet"
        if not path.exists():
            continue
        values = pd.read_parquet(path, columns=["visible_at"])["visible_at"]
        candidate = pd.to_datetime(values, utc=True).max()
        last = candidate if last is None else max(last, candidate)
    if last is None:
        raise SystemExit(f"no news packets under {NEWS_PACKETS_ROOT}")
    return last


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    seed = args.shuffle_symbols_seed
    mode = args.shuffle_symbols_mode
    out_root = args.out_root or (
        DEFAULT_OUT_ROOT
        if seed is None
        else DEFAULT_OUT_ROOT.with_name(f"news_attention_placebo_{mode}_seed{seed}")
    )
    out_root.mkdir(parents=True, exist_ok=True)

    if args.as_of:
        last_date = date.fromisoformat(args.as_of)
    else:
        last_visible = _archive_last_visible()
        last_date = last_visible.tz_convert(NEW_YORK).date()
    sessions, opens = build_sessions(last_date)
    log(f"sessions: {sessions[0].date()} .. {sessions[-1].date()} ({len(sessions):,})")
    universe_panel = load_universe_panel(UNIVERSE_ROOT)

    index_payload: dict[str, object] | None = None
    if args.stage in ("articles", "all"):
        index_payload = stage_articles(
            out_root=out_root,
            sessions=sessions,
            opens=opens,
            universe_panel=universe_panel,
            top_n=args.top_n,
            shuffle_seed=seed,
            shuffle_mode=mode,
            force=args.force,
        )
    if index_payload is None:
        index_path = out_root / ARTICLES_INDEX_NAME
        if not index_path.exists():
            raise SystemExit(f"{index_path} missing -- run the `articles` stage first")
        index_payload = json.loads(index_path.read_text())

    archive_first_session = int(index_payload["first_session_index"] or 0)
    written: list[str] = [
        str(path) for path in sorted(out_root.glob("[0-9][0-9][0-9][0-9].parquet"))
    ]
    if args.stage in ("features", "all"):
        written = stage_features(
            out_root=out_root,
            sessions=sessions,
            universe_panel=universe_panel,
            top_n=args.top_n,
            archive_first_session=archive_first_session,
            force=args.force,
        )
    if args.stage in ("weekly-panel", "all"):
        stage_weekly_panel(
            out_root=out_root, sessions=sessions, top_n=args.weekly_top_n, force=args.force
        )

    manifest = {
        "card": "reports/research/hypotheses/H-20260916-02-news-attention-features.md",
        "stage": "1 (no LLM)",
        "built_at": datetime.now().astimezone().isoformat(),
        "as_of": last_date.isoformat(),
        "sessions": [sessions[0].date().isoformat(), sessions[-1].date().isoformat()],
        "packets": [str(NEWS_PACKETS_ROOT / f"{year}.parquet") for year in PACKET_YEARS],
        "visibility_rule": (
            "article attributed to the first US equity session whose 09:30 ET open is "
            ">= visible_at; created_at/updated_at/fetched_at are never used"
        ),
        "windows": {
            "short": SHORT_WINDOW,
            "long": LONG_WINDOW,
            "baseline": BASELINE_WINDOW,
        },
        "max_symbol_fanout": MAX_SYMBOL_FANOUT,
        "fanout_policy": "articles listing more than max_symbol_fanout symbols are dropped",
        "novelty_rule": (
            "1 - mean over the trailing 5 sessions' articles of the max word-3-gram "
            "Jaccard similarity between that headline and the symbol's distinct "
            "headlines from the 20 sessions strictly before that headline's own session; "
            "null when there were no articles in the 5 sessions"
        ),
        "surge_rule": ("news_count_5d / max(news_count_60d / (max(news_history_sessions,5)/5), 1)"),
        "keyword_groups": {group: list(patterns) for group, patterns in KEYWORD_PATTERNS.items()},
        "keyword_field": "headline only (not summary)",
        "feature_columns": list(NEWS_ATTENTION_COLUMNS),
        "metadata_columns": list(NEWS_ATTENTION_METADATA_COLUMNS),
        "feature_universe_top_n": args.top_n,
        "weekly_panel_top_n": args.weekly_top_n,
        "shuffle_symbols_seed": seed,
        "shuffle_symbols_mode": mode if seed is not None else None,
        "archive_first_session_note": (
            "``news_history_sessions`` counts from ``articles_index.first_session_date``, which is "
            "the first session any attributed article lands on -- 2023-10-30, from 25 stray "
            "re-published articles that the packets' updated_at partitioning dragged in. Real "
            "coverage starts 2024-01-01, so January 2024 rows are credited with ~40 sessions of "
            "history they effectively did not have. That makes their attention_surge_5d "
            "denominator too large and the surge too small -- the conservative direction -- and "
            "the per-row value used is published in news_history_sessions."
        ),
        "articles_index": index_payload,
        "years": written,
        "llm_used": False,
    }
    (out_root / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n")
    log(f"wrote {out_root / MANIFEST_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
