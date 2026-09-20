"""Pure data for the cockpit's hypothesis board, lineage view and card detail
(Step 18, screens 1-2 and the card detail page).

Nothing in this module renders HTML or Jinja2 -- ``open_composer.cockpit.app``
is the only thing that imports both this module and the template engine,
mirroring ``open_composer.cockpit.data.health``. Every function here is
read-only: it globs and reads small Markdown/JSON files already checked into
the repo, nothing is written back and nothing is cached to disk.

Three data sources feed this screen, all listed in plan section 5:

* ``reports/research/hypotheses/*.md`` -- one hand-written card per
  hypothesis (``H-YYYYMMDD-NN``) or data/framework correction
  (``D-YYYYMMDD-NN``). Format is **not** uniform (see :func:`load_cards`);
  parsing is deliberately tolerant and a card that cannot be classified goes
  to the ``unclassified`` lane with a reason attached rather than disappearing.
* ``reports/research/iterations/*/summary.json`` -- machine-written trial
  results. Only some of them carry a top-level ``card_id`` field; only those
  join to a card (see :func:`load_results`). This is a real gap in the data,
  not a parser bug: as of 2026-09-19, 4 of the 8 existing ``summary.json``
  files predate the ``card_id`` convention.
* The cards' own prose -- an explicit ``上一环：`` field (when present) and
  incidental card-id mentions in the body feed :func:`build_lineage`'s two
  edge kinds.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from open_composer.cockpit.data.health import Status
from open_composer.cockpit.security import secret_scrub
from open_composer.config import project_root
from open_composer.yaml_utils import safe_load_yaml

# --------------------------------------------------------------------------
# Card id / lane vocabulary
# --------------------------------------------------------------------------

#: `H-` (hypothesis) or `D-` (data/framework correction) followed by an
#: 8-digit date and a 2-digit sequence number, e.g. `H-20260919-01`.
CARD_ID_RE = re.compile(r"^([HD])-(\d{8})-(\d{2})$")
_CARD_ID_ANYWHERE_RE = re.compile(r"\b([HD]-\d{8}-\d{2})\b")

#: Swimlanes in board order (plan section 4, screen 1). `unclassified` is last and
#: is a *guarantee*, not a fallback that is expected to stay empty: any card
#: whose status text does not contain a recognized keyword lands here rather
#: than being dropped or guessed at. See `test_no_card_is_ever_dropped`.
# Lane order follows this project's own card lifecycle, written down in
# docs/proposal-research-loop-redesign-2026-09-15.zh.md section 2.3
# (提出 / 你已批准 / 运行中 / 完成), with 完成 split by outcome and two extra
# buckets: `data card` for D- cards, which are data/framework corrections with no
# hypothesis lifecycle at all, and `unclassified` for anything the vocabulary cannot
# place. Step 18's plan originally invented a different vocabulary; measured
# against the real corpus on 2026-09-19 that mislabelled 7 of 19 cards as
# unclassified purely because their status prose is English.
LANES: tuple[str, ...] = (
    "proposed",
    "approved",
    "preregistered",
    "running",
    "shipped",
    "refuted",
    "on hold",
    "data card",
    "unclassified",
)

# Keyword sets for the tolerant, keyword-based lane classifier. Chinese
# keywords are matched literally; "done" and "refuted" are the two English
# exceptions the plan's cards actually use (e.g. "done / refuted").
_PREREG_WORDS = ("预注册", "已写死", "待跑")
_PROPOSED_WORDS = ("proposed", "提出")
_APPROVED_WORDS = ("approved", "已批准")
_RUNNING_WORDS = ("在跑", "运行中", "评估在跑", "running")
_HOLD_WORDS = ("搁置", "暂停")
_DONE_WORDS = ("已执行", "done")
_NEGATIVE_WORDS = ("否定", "被否定", "refuted")
_POSITIVE_WORDS = ("通过", "上线", "上模拟盘")

# Reused from health.py's four-word status vocabulary (`ok`/`warn`/`stale`/
# `unknown`) so the whole cockpit shares one palette, per the convention
# documented at the top of `cockpit.css`. A finished, shipped hypothesis is
# `ok`; a finished, refuted one is `stale` (read as "needs no more attention,
# but the color for a settled-negative outcome", the same reinterpretation
# health.py already uses for non-freshness fields); an active trial or a
# paused one is `warn`; anything not yet started, or not classifiable, is
# `unknown`.
_LANE_STATUS: dict[str, Status] = {
    "shipped": "ok",
    "refuted": "stale",
    "running": "warn",
    "on hold": "warn",
    "preregistered": "unknown",
    "proposed": "unknown",
    "approved": "unknown",
    "data card": "unknown",
    "unclassified": "unknown",
}


def lane_status(lane: str) -> Status:
    return _LANE_STATUS.get(lane, "unknown")


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)


def derive_lane(status_text: str) -> tuple[str, str | None]:
    """Map a card's raw status prose to a lane, plus a reason if unclassified.

    Order matters and was chosen against the real corpus, not just the rule
    list: the two "done + verdict" rules are checked *before* either
    single-keyword rule (预注册/在跑/搁置) because a single generic keyword
    like `预注册` is much more likely to show up incidentally inside prose
    (e.g. H-20260918-06's status line says "已执行，否定" but also mentions
    "预注册选择规则" as a noun phrase describing the method, not the card's
    lifecycle state) than a specific co-occurring pair is. Within the two
    single-keyword checks, `在跑` is checked before `预注册` for the same
    reason: H-20260919-02's status line is "预注册已写死...评估在跑" and the
    more current signal ("evaluation is running now") should win over the
    completed-setup signal ("the grid is frozen").

    The vocabulary covers both languages, because the real corpus mixes them:
    `proposed` / `approved` / `running` appear in English on 7 of the 19 cards
    while the newer ones write 已执行 / 评估在跑 in Chinese. `已批准` and `提出`
    are checked last so that a card which is approved *and* already running is
    filed under the more current state.

    Anything still unmatched goes to `unclassified` **with its raw status text and a
    reason**, and is rendered on the board like any other card. A card is never
    dropped for being unparseable -- an invisible card is worse than an
    unlabelled one.
    """
    if not status_text or not status_text.strip():
        return "unclassified", "no 状态 field found on this card"
    done = _contains_any(status_text, _DONE_WORDS)
    if done and _contains_any(status_text, _NEGATIVE_WORDS):
        return "refuted", None
    if done and _contains_any(status_text, _POSITIVE_WORDS):
        return "shipped", None
    if _contains_any(status_text, _HOLD_WORDS):
        return "on hold", None
    if _contains_any(status_text, _RUNNING_WORDS):
        return "running", None
    if _contains_any(status_text, _PREREG_WORDS):
        return "preregistered", None
    if _contains_any(status_text, _APPROVED_WORDS):
        return "approved", None
    if _contains_any(status_text, _PROPOSED_WORDS):
        return "proposed", None
    # Note: deliberately avoids the substring "key" immediately before a
    # colon-and-value here (e.g. spelling out "keyword:") -- `secret_scrub`'s
    # generic catch-all pattern treats "<word ending in key/token/secret/
    # password>: <value>" as a leaked credential, and this message embeds the
    # untouched raw status text right after itself.
    return (
        "unclassified",
        f"status text has no recognized lane marker; raw status text = {status_text!r}",
    )


# --------------------------------------------------------------------------
# Card front matter (optional, forward-looking -- see README.md)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Criterion:
    name: str
    threshold: Any
    direction: str | None = None


@dataclass(frozen=True)
class CardFrontMatter:
    card_id: str | None
    status: str | None
    lane: str | None
    previous: str | None
    criteria: tuple[Criterion, ...] = field(default_factory=tuple)


_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n?", re.DOTALL)


def _extract_front_matter(text: str, warnings: list[str]) -> tuple[CardFrontMatter | None, str]:
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return None, text
    remainder = text[match.end() :]
    try:
        data = safe_load_yaml(match.group(1))
    except yaml.YAMLError as exc:
        warnings.append(f"front-matter YAML parse error, ignored: {exc}")
        return None, remainder
    if not isinstance(data, dict):
        warnings.append("front-matter is not a mapping, ignored")
        return None, remainder
    criteria: list[Criterion] = []
    for item in data.get("criteria") or []:
        if isinstance(item, dict) and item.get("name"):
            criteria.append(
                Criterion(
                    name=str(item["name"]),
                    threshold=item.get("threshold"),
                    direction=(
                        str(item["direction"]) if item.get("direction") is not None else None
                    ),
                )
            )
    return (
        CardFrontMatter(
            card_id=data.get("card_id"),
            status=data.get("status"),
            lane=data.get("lane"),
            previous=data.get("previous"),
            criteria=tuple(criteria),
        ),
        remainder,
    )


# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Card:
    id: str
    kind: str  # "H" or "D"
    title: str
    status_text: str
    lane: str
    lane_reason: str | None
    script: str | None
    output_dir: str | None
    layer: str | None
    data_layer: str | None
    lesson_ref: str | None
    previous: str | None
    referenced_ids: tuple[str, ...]
    body_markdown: str
    front_matter: CardFrontMatter | None
    path: str  # display path, relative to the repo root
    parse_warnings: tuple[str, ...]


_TITLE_LINE_RE = re.compile(r"^#\s*([HD]-\d{8}-\d{2})\s+(.*)$")
_HEADING_BOUNDARY_RE = re.compile(r"^##\s+", re.MULTILINE)

_SCRIPT_RE = re.compile(r"执行脚本[：:]\s*(.+)")
_OUTPUT_DIR_RE = re.compile(r"产出目录[：:]\s*(.+)")
_OUTPUT_RE = re.compile(r"产出(?!目录)[：:]\s*(.+)")
_LAYER_RE = re.compile(r"(?<!数据)层[：:]\s*([^·\n]+)")
_DATA_LAYER_RE = re.compile(r"数据层[：:]\s*([^·\n]+)")
# 上一环 and 上一张卡 are the same relation written two ways; both are causal
# ("this card follows from that one") and both produce a solid lineage edge.
_PREVIOUS_RE = re.compile(r"(?:上一环|上一张卡)[：:]\s*`?([HD]-\d{8}-\d{2})`?")
_STATUS_LINE_RE = re.compile(r"^\s*-?\s*状态[：:]\s*(.+)$", re.MULTILINE)
_LESSON_FIELD_RE = re.compile(r"教训[：:]?\s*`?(L-\d{8}-\d{2})`?")
_LESSON_PATH_RE = re.compile(r"lessons/(L-\d{8}-\d{2})\.md")

#: Bytes above which a card is treated as unparseable rather than read in
#: full -- purely defensive; the largest real card is ~21KB (see plan
#: ground-truth notes), so this only guards against a future runaway file on
#: a 3.9GB box.
MAX_CARD_BYTES = 2_000_000


def _clean_field(value: str) -> str:
    value = value.strip()
    match = re.fullmatch(r"\*\*(.+)\*\*", value)
    if match:
        value = match.group(1).strip()
    return value


def _first_field(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return _clean_field(match.group(1)) if match else None


def _header_block(remainder: str) -> str:
    """Everything before the first `##` heading -- where `状态：` always
    lives in every card observed. `执行脚本`/`产出`/`产出目录` are scanned
    over the whole document instead (see `load_cards`'s docstring note):
    older-format cards (e.g. H-20260916-01) put those in a later "成本与执行"
    section rather than in the header block.
    """
    match = _HEADING_BOUNDARY_RE.search(remainder)
    return remainder[: match.start()] if match else remainder


def _parse_card_file(path: Path, base: Path) -> Card:
    warnings: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return Card(
            id=path.stem,
            kind="H",
            title=path.stem,
            status_text="",
            lane="unclassified",
            lane_reason=f"could not read file: {exc}",
            script=None,
            output_dir=None,
            layer=None,
            data_layer=None,
            lesson_ref=None,
            previous=None,
            referenced_ids=(),
            body_markdown="",
            front_matter=None,
            path=str(path.relative_to(base)),
            parse_warnings=(f"could not read file: {exc}",),
        )

    if len(raw.encode("utf-8", errors="replace")) > MAX_CARD_BYTES:
        warnings.append(f"file exceeds {MAX_CARD_BYTES} byte parse cap, treated as unparseable")
        return Card(
            id=path.stem,
            kind="H",
            title=path.stem,
            status_text="",
            lane="unclassified",
            lane_reason=warnings[-1],
            script=None,
            output_dir=None,
            layer=None,
            data_layer=None,
            lesson_ref=None,
            previous=None,
            referenced_ids=(),
            body_markdown="",
            front_matter=None,
            path=str(path.relative_to(base)),
            parse_warnings=tuple(warnings),
        )

    front_matter, remainder = _extract_front_matter(raw, warnings)
    remainder = remainder.lstrip("\n")

    lines = remainder.split("\n")
    first_line = lines[0] if lines else ""
    title_match = _TITLE_LINE_RE.match(first_line.strip())

    if title_match:
        card_id = title_match.group(1)
        title = title_match.group(2).strip()
        body_after_title = "\n".join(lines[1:]).lstrip("\n")
    else:
        warnings.append(f"first line does not match '# H|D-YYYYMMDD-NN title': {first_line!r}")
        fallback_id_match = _CARD_ID_ANYWHERE_RE.search(path.name)
        card_id = (front_matter.card_id if front_matter else None) or (
            fallback_id_match.group(1) if fallback_id_match else path.stem
        )
        title = first_line.strip() or path.stem
        body_after_title = remainder

    if front_matter and front_matter.card_id and front_matter.card_id != card_id:
        warnings.append(
            f"front-matter card_id {front_matter.card_id!r} disagrees with title id {card_id!r}"
        )

    id_match = CARD_ID_RE.match(card_id)
    kind = id_match.group(1) if id_match else "H"
    if not id_match:
        warnings.append(
            f"card id {card_id!r} does not match [HD]-YYYYMMDD-NN, defaulting kind to 'H'"
        )

    header_block = _header_block(remainder)

    status_text = (
        front_matter.status if front_matter and front_matter.status else None
    ) or _first_field(_STATUS_LINE_RE, header_block)
    if status_text is None:
        status_text = ""
        warnings.append("no 状态 field found in the header block")

    script = _first_field(_SCRIPT_RE, remainder)
    output_dir = _first_field(_OUTPUT_DIR_RE, remainder) or _first_field(_OUTPUT_RE, remainder)
    layer = _first_field(_LAYER_RE, remainder)
    data_layer = _first_field(_DATA_LAYER_RE, remainder)

    previous = (
        front_matter.previous
        if front_matter and front_matter.previous
        else _first_field(_PREVIOUS_RE, remainder)
    )

    lesson_ref = _first_field(_LESSON_FIELD_RE, remainder)
    if lesson_ref is None:
        lesson_match = _LESSON_PATH_RE.search(remainder)
        lesson_ref = lesson_match.group(1) if lesson_match else None

    referenced_ids = tuple(
        dict.fromkeys(m for m in _CARD_ID_ANYWHERE_RE.findall(remainder) if m != card_id)
    )

    if front_matter and front_matter.lane:
        if front_matter.lane in LANES:
            lane, lane_reason = front_matter.lane, None
        else:
            warnings.append(
                f"front-matter lane {front_matter.lane!r} is not one of {LANES}, "
                "using keyword mapping"
            )
            lane, lane_reason = derive_lane(status_text)
    else:
        lane, lane_reason = derive_lane(status_text)

    # D- cards are data/framework corrections ("性质：数据与框架修正，不是策略假设"),
    # so they carry no 状态 field and have no hypothesis lifecycle to be in the
    # middle of. Filing them under `unclassified` would read as a parser failure; they
    # get their own lane instead.
    if kind == "D" and lane == "unclassified":
        lane, lane_reason = "data card", None

    return Card(
        id=card_id,
        kind=kind,
        title=secret_scrub(title),
        status_text=secret_scrub(status_text),
        lane=lane,
        lane_reason=secret_scrub(lane_reason) if lane_reason else None,
        script=secret_scrub(script) if script else None,
        output_dir=secret_scrub(output_dir) if output_dir else None,
        layer=secret_scrub(layer) if layer else None,
        data_layer=secret_scrub(data_layer) if data_layer else None,
        lesson_ref=lesson_ref,
        previous=previous,
        referenced_ids=referenced_ids,
        body_markdown=secret_scrub(body_after_title),
        front_matter=front_matter,
        path=str(path.relative_to(base)),
        parse_warnings=tuple(warnings),
    )


def load_cards(root: Path | None = None) -> tuple[Card, ...]:
    """Every hypothesis/data card under ``reports/research/hypotheses/``.

    ``README.md`` and ``trial-families.json`` in the same directory are not
    cards and are skipped by name/extension. Every ``*.md`` file besides
    ``README.md`` is parsed -- a parse failure degrades to an ``unclassified`` card
    carrying the reason, it never raises and never drops the file.
    """
    base = root or project_root()
    hyp_dir = base / "reports" / "research" / "hypotheses"
    if not hyp_dir.is_dir():
        return ()
    cards: list[Card] = []
    for path in sorted(hyp_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        try:
            cards.append(_parse_card_file(path, base))
        except Exception as exc:  # defensive: a parser bug must not drop the card or crash the page
            cards.append(
                Card(
                    id=path.stem,
                    kind="H",
                    title=path.stem,
                    status_text="",
                    lane="unclassified",
                    lane_reason=f"parser raised {exc!r}",
                    script=None,
                    output_dir=None,
                    layer=None,
                    data_layer=None,
                    lesson_ref=None,
                    previous=None,
                    referenced_ids=(),
                    body_markdown="",
                    front_matter=None,
                    path=str(path.relative_to(base)),
                    parse_warnings=(f"parser raised {exc!r}",),
                )
            )
    return tuple(cards)


def find_card(cards: Sequence[Card], card_id: str) -> Card | None:
    for card in cards:
        if card.id == card_id:
            return card
    return None


def group_cards_by_lane(cards: Sequence[Card]) -> dict[str, tuple[Card, ...]]:
    """Bucket ``cards`` into :data:`LANES`, in lane order.

    Uses ``setdefault`` rather than a plain dict comprehension so that even a
    card whose ``lane`` is somehow not one of :data:`LANES` (should not
    happen; :func:`derive_lane` only returns known lanes) still shows up
    somewhere instead of vanishing -- this is the invariant
    ``test_no_card_is_ever_dropped`` checks by flattening every bucket back
    out and comparing the count to ``len(cards)``.
    """
    buckets: dict[str, list[Card]] = {lane: [] for lane in LANES}
    for card in cards:
        buckets.setdefault(card.lane, []).append(card)
    return {lane: tuple(items) for lane, items in buckets.items()}


# --------------------------------------------------------------------------
# Results (reports/research/iterations/*/summary.json)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultFacts:
    card_id: str
    iteration_id: str
    path: str
    cell_count: int | None
    windows: dict[str, Any] | None
    incumbent_to_beat: dict[str, Any] | None
    benchmarks: tuple[dict[str, Any], ...] | None
    family_picks: tuple[dict[str, Any], ...] | None
    generated_at: str | None
    raw_keys: tuple[str, ...]


@dataclass(frozen=True)
class ResultsIndex:
    by_card_id: dict[str, tuple[ResultFacts, ...]]
    warnings: tuple[str, ...]

    def for_card(self, card_id: str) -> tuple[ResultFacts, ...]:
        return self.by_card_id.get(card_id, ())


#: A `summary.json` above this size degrades to a warning instead of being
#: read -- the plan's single-response memory budget is 50MB (section 6.5) and
#: this module may be asked to join every iteration's results into one page.
MAX_SUMMARY_BYTES = 5_000_000


def load_results(root: Path | None = None) -> ResultsIndex:
    """Index every ``summary.json`` under ``reports/research/iterations/`` by
    its top-level ``card_id`` field.

    Joining on the prose ``产出目录：``/``产出：`` field a card writes for
    itself would be fragile (free text, sometimes a glob pattern, sometimes a
    plain path) and would silently miss the cards that do not have that field
    at all. ``card_id`` inside ``summary.json`` is the one machine-written,
    exact-match key, so that is what this joins on -- at the cost of not
    joining the 4 (of 8) existing ``summary.json`` files that predate the
    ``card_id`` convention. Those are recorded as warnings, not silently
    skipped, so the gap is visible on the health/detail views rather than
    just absent.
    """
    base = root or project_root()
    iterations_dir = base / "reports" / "research" / "iterations"
    warnings: list[str] = []
    by_card: dict[str, list[ResultFacts]] = defaultdict(list)

    if not iterations_dir.is_dir():
        return ResultsIndex(by_card_id={}, warnings=(f"{iterations_dir} does not exist",))

    for summary_path in sorted(iterations_dir.glob("*/summary.json")):
        iteration_id = summary_path.parent.name
        rel_path = str(summary_path.relative_to(base))
        try:
            size = summary_path.stat().st_size
        except OSError as exc:
            warnings.append(f"{rel_path}: could not stat file ({exc})")
            continue
        if size > MAX_SUMMARY_BYTES:
            warnings.append(
                f"{rel_path}: skipped, {size} bytes exceeds the {MAX_SUMMARY_BYTES} byte cap"
            )
            continue
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            warnings.append(f"{rel_path}: corrupt or unreadable summary.json ({exc})")
            continue
        if not isinstance(data, dict):
            warnings.append(f"{rel_path}: summary.json top level is not a JSON object, skipped")
            continue

        card_id = data.get("card_id")
        if not isinstance(card_id, str) or not CARD_ID_RE.match(card_id):
            warnings.append(f"{rel_path}: no usable top-level card_id field, cannot join to a card")
            continue

        benchmarks = data.get("benchmarks")
        family_picks = data.get("family_picks")
        windows = data.get("windows")
        incumbent = data.get("incumbent_to_beat")
        generated_at = data.get("generated_at")

        by_card[card_id].append(
            ResultFacts(
                card_id=card_id,
                iteration_id=iteration_id,
                path=rel_path,
                cell_count=data.get("cell_count")
                if isinstance(data.get("cell_count"), int)
                else None,
                windows=windows if isinstance(windows, dict) else None,
                incumbent_to_beat=incumbent if isinstance(incumbent, dict) else None,
                benchmarks=tuple(benchmarks) if isinstance(benchmarks, list) else None,
                family_picks=tuple(family_picks) if isinstance(family_picks, list) else None,
                generated_at=generated_at if isinstance(generated_at, str) else None,
                raw_keys=tuple(sorted(data.keys())),
            )
        )

    return ResultsIndex(
        by_card_id={card_id: tuple(items) for card_id, items in by_card.items()},
        warnings=tuple(warnings),
    )


def headline_summary(facts: ResultFacts) -> str:
    """One short, human-readable line of headline numbers for the board."""
    parts: list[str] = []
    if facts.cell_count is not None:
        parts.append(f"{facts.cell_count} cell(s)")
    if facts.incumbent_to_beat:
        name = facts.incumbent_to_beat.get("name")
        sharpe = facts.incumbent_to_beat.get("select_sharpe")
        if name is not None and sharpe is not None:
            parts.append(f"incumbent {name}: select_sharpe={sharpe}")
    if facts.family_picks is not None:
        parts.append(f"{len(facts.family_picks)} family pick(s)")
    if facts.benchmarks is not None:
        parts.append(f"{len(facts.benchmarks)} benchmark(s)")
    return "; ".join(parts) if parts else f"summary.json present ({facts.iteration_id})"


# --------------------------------------------------------------------------
# 判定 vs 实际 ("criteria vs actual"), rendered honestly
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CriteriaSection:
    """A heading (containing 判定 or 预注册) plus its raw markdown body.

    Rendered verbatim next to whatever `ResultFacts` matched the same card
    and explicitly labeled "未结构化（人工对照）" (unstructured, human
    cross-check) by the caller -- this module never turns the prose into a
    pass/fail verdict. Most cards state their criteria in prose, not in a
    machine-checkable form, and inventing structure that is not there would
    misrepresent what was actually pre-registered.
    """

    heading: str
    level: int
    markdown: str


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def extract_criteria_sections(body_markdown: str) -> tuple[CriteriaSection, ...]:
    headings = [
        (m.start(), len(m.group(1)), m.group(2).strip())
        for m in _HEADING_RE.finditer(body_markdown)
    ]
    sections: list[CriteriaSection] = []
    for idx, (start, level, heading_text) in enumerate(headings):
        if "判定" not in heading_text and "预注册" not in heading_text:
            continue
        end = len(body_markdown)
        for next_start, next_level, _ in headings[idx + 1 :]:
            if next_level <= level:
                end = next_start
                break
        sections.append(
            CriteriaSection(
                heading=heading_text, level=level, markdown=body_markdown[start:end].rstrip()
            )
        )
    return tuple(sections)


# --------------------------------------------------------------------------
# Lineage (screen 2)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LineageNode:
    card_id: str
    title: str
    lane: str
    kind: str


@dataclass(frozen=True)
class LineageEdge:
    source: str  # the earlier/foundational card
    target: str  # the later card that derives from or mentions `source`
    kind: str  # "explicit_previous" | "mentioned"

    @property
    def label(self) -> str:
        if self.kind == "explicit_previous":
            return "declared"
        return "mentioned"

    @property
    def is_explicit(self) -> bool:
        return self.kind == "explicit_previous"


@dataclass(frozen=True)
class LineageGraph:
    nodes: tuple[LineageNode, ...]
    edges: tuple[LineageEdge, ...]
    roots: tuple[str, ...]
    layer_of: dict[str, int]
    warnings: tuple[str, ...]


def build_lineage(cards: Sequence[Card]) -> LineageGraph:
    """Build the two-edge-kind lineage graph (plan section 4, screen 2).

    Solid (``explicit_previous``) edges come only from a card's own
    ``上一环：`` field. As measured on 2026-09-19, only one of the 19 cards
    has that field -- this is a fact about the corpus, not a parser gap, and
    drawing a lineage graph from explicit edges alone would be almost empty.

    Dashed (``mentioned``) edges come from any other card id mentioned in a
    card's body (``Card.referenced_ids``, already self-reference-excluded).
    This is a *weak* signal -- "mentions" is not "derives from" -- and must
    never be drawn as if it were the strong signal. If a (source, target)
    pair already has an explicit edge, the weaker mention of the same pair is
    dropped rather than double-drawn (e.g. H-20260919-02 both declares
    `上一环: H-20260917-01` *and* repeats that id in the same line -- that is
    one edge, not two).

    Layering uses Kahn's algorithm so a cycle terminates the layering pass
    (it cannot loop forever: each pass either shrinks the frontier or ends)
    rather than hanging; any node left unresolved after the pass is reported
    in ``warnings`` and parked one layer past the deepest resolved layer so
    the graph still renders something.
    """
    nodes = tuple(LineageNode(card_id=c.id, title=c.title, lane=c.lane, kind=c.kind) for c in cards)
    node_ids = {n.card_id for n in nodes}
    warnings: list[str] = []
    edge_kind_by_pair: dict[tuple[str, str], str] = {}

    for card in cards:
        if not card.previous:
            continue
        if card.previous == card.id:
            warnings.append(f"{card.id}: 上一环 references itself, ignored")
            continue
        if card.previous not in node_ids:
            warnings.append(f"{card.id}: 上一环 references unknown card {card.previous!r}, ignored")
            continue
        edge_kind_by_pair[(card.previous, card.id)] = "explicit_previous"

    for card in cards:
        for ref in card.referenced_ids:
            if ref == card.id:
                continue
            if ref not in node_ids:
                warnings.append(f"{card.id}: mentions unknown card {ref!r}, not drawn")
                continue
            pair = (ref, card.id)
            if pair in edge_kind_by_pair:
                continue  # already explicit for this pair -- do not also draw it dashed
            edge_kind_by_pair[pair] = "mentioned"

    edges = tuple(
        LineageEdge(source=src, target=tgt, kind=kind)
        for (src, tgt), kind in edge_kind_by_pair.items()
    )

    indegree = dict.fromkeys(node_ids, 0)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        indegree[edge.target] += 1
        outgoing[edge.source].append(edge.target)

    roots = tuple(sorted(nid for nid, deg in indegree.items() if deg == 0))
    remaining = dict(indegree)
    layer_of: dict[str, int] = {}
    frontier = list(roots)
    current_layer = 0
    while frontier:
        for nid in frontier:
            layer_of[nid] = current_layer
        next_frontier: list[str] = []
        for nid in frontier:
            for target in outgoing.get(nid, ()):
                remaining[target] -= 1
                if remaining[target] == 0:
                    next_frontier.append(target)
        frontier = sorted(set(next_frontier))
        current_layer += 1

    unresolved = sorted(nid for nid in node_ids if nid not in layer_of)
    if unresolved:
        warnings.append(
            "cycle detected in lineage graph, could not topologically order: "
            + ", ".join(unresolved)
        )
        for nid in unresolved:
            layer_of[nid] = current_layer

    return LineageGraph(
        nodes=nodes, edges=edges, roots=roots, layer_of=layer_of, warnings=tuple(warnings)
    )


@dataclass(frozen=True)
class MobileLineageRow:
    """One row of the phone-layout indented lineage list (plan section 4,
    screen 2: "手机上退化成缩进列表"). ``edge_label`` is ``None`` for a root
    row (no parent in this branch) and otherwise carries the *same* label
    :attr:`LineageEdge.label` would show on desktop -- solid/dashed becomes a
    text label instead of a line style, per the plan's explicit instruction
    not to lose the strong/weak distinction just because the layout changed.
    """

    card_id: str
    title: str
    lane: str
    depth: int
    edge_label: str | None
    is_cycle_repeat: bool = False


def flatten_lineage_for_mobile(graph: LineageGraph) -> tuple[MobileLineageRow, ...]:
    """Depth-first flatten of ``graph`` into indented rows, grouped by root.

    A node reachable from more than one parent (a real "diamond" in the
    corpus: H-20260918-03 derives from both D-20260917-01 and
    H-20260917-02) appears once per branch that reaches it -- that is
    intentional, not a bug, for a small graph rendered as a list. A node
    that is its own ancestor along one branch (a cycle) is appended once
    more so the cycle is visible, then that branch stops recursing instead
    of looping forever; :func:`build_lineage` already reports the same
    cycle in ``graph.warnings``, this is a second, independent guard against
    hanging while rendering the list.
    """
    node_by_id = {n.card_id: n for n in graph.nodes}
    children_of: dict[str, list[LineageEdge]] = defaultdict(list)
    for edge in graph.edges:
        children_of[edge.source].append(edge)
    for source in children_of:
        children_of[source].sort(key=lambda e: e.target)

    rows: list[MobileLineageRow] = []

    def walk(card_id: str, depth: int, edge_label: str | None, ancestors: frozenset[str]) -> None:
        node = node_by_id[card_id]
        is_repeat = card_id in ancestors
        rows.append(
            MobileLineageRow(
                card_id=card_id,
                title=node.title,
                lane=node.lane,
                depth=depth,
                edge_label=edge_label,
                is_cycle_repeat=is_repeat,
            )
        )
        if is_repeat:
            return
        next_ancestors = ancestors | {card_id}
        for edge in children_of.get(card_id, ()):
            walk(edge.target, depth + 1, edge.label, next_ancestors)

    for root_id in graph.roots:
        walk(root_id, 0, None, frozenset())

    # A pure cycle (every node in it has an incoming edge) has no root at
    # all, so the walk above would silently skip it entirely. Treat the
    # lowest id in each such leftover component as a synthetic root instead
    # of dropping it -- consistent with this module's "a card never silently
    # disappears" rule applying to the lineage view too, not just the board.
    visited = {row.card_id for row in rows}
    for card_id in sorted(node_by_id):
        if card_id not in visited:
            walk(card_id, 0, None, frozenset())
            visited = {row.card_id for row in rows}

    return tuple(rows)


@dataclass(frozen=True)
class LineageLayout:
    """Pure numeric layout for the inline-SVG lineage graph: a card id to
    ``(x, y)`` pixel position, plus the canvas size. Wrapping into rows
    within a layer (rather than one column per layer) keeps the mostly-root
    layer (many cards have no edges at all, see `build_lineage`) from
    rendering as one absurdly tall column.
    """

    positions: dict[str, tuple[float, float]]
    width: float
    height: float


def compute_lineage_layout(
    graph: LineageGraph,
    *,
    column_width: float = 220.0,
    row_height: float = 70.0,
    per_row: int = 4,
    margin: float = 40.0,
) -> LineageLayout:
    by_layer: dict[int, list[str]] = defaultdict(list)
    for card_id, layer in graph.layer_of.items():
        by_layer[layer].append(card_id)
    for layer in by_layer:
        by_layer[layer].sort()

    positions: dict[str, tuple[float, float]] = {}
    max_x = margin
    max_y = margin
    for layer in sorted(by_layer):
        card_ids = by_layer[layer]
        x = margin + layer * column_width
        for idx, card_id in enumerate(card_ids):
            row, col = divmod(idx, per_row)
            px = x + col * (column_width / max(per_row, 1))
            py = margin + row * row_height
            positions[card_id] = (px, py)
            max_x = max(max_x, px)
            max_y = max(max_y, py)

    return LineageLayout(positions=positions, width=max_x + column_width, height=max_y + row_height)


# --------------------------------------------------------------------------
# Aggregate report
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HypothesesReport:
    generated_at: datetime
    cards: tuple[Card, ...]
    lanes: dict[str, tuple[Card, ...]]
    results: ResultsIndex
    lineage: LineageGraph


def build_hypotheses_report(root: Path | None = None) -> HypothesesReport:
    """Assemble the full hypothesis board data model.

    Each phase is isolated: a broken card file must degrade that one card to
    `unclassified` (already handled inside `load_cards`), and a missing/corrupt
    `summary.json` must degrade to a warning (already handled inside
    `load_results`) -- neither should take down the board. The outer
    try/except here is a last-resort backstop mirroring
    `health.build_health_report`'s per-section isolation, exercised by
    `test_hypotheses_report_degrades_when_repo_root_is_empty`.
    """
    base = root or project_root()
    try:
        cards = load_cards(base)
    except Exception:
        cards = ()
    try:
        results = load_results(base)
    except Exception:
        results = ResultsIndex(
            by_card_id={}, warnings=("failed to load reports/research/iterations",)
        )
    try:
        lineage = build_lineage(cards)
    except Exception:
        lineage = LineageGraph(
            nodes=(), edges=(), roots=(), layer_of={}, warnings=("failed to build lineage",)
        )

    return HypothesesReport(
        generated_at=datetime.now(UTC),
        cards=cards,
        lanes=group_cards_by_lane(cards),
        results=results,
        lineage=lineage,
    )


__all__ = [
    "CARD_ID_RE",
    "LANES",
    "Card",
    "CardFrontMatter",
    "Criterion",
    "CriteriaSection",
    "HypothesesReport",
    "LineageEdge",
    "LineageGraph",
    "LineageLayout",
    "LineageNode",
    "MobileLineageRow",
    "ResultFacts",
    "ResultsIndex",
    "build_hypotheses_report",
    "build_lineage",
    "compute_lineage_layout",
    "derive_lane",
    "extract_criteria_sections",
    "find_card",
    "flatten_lineage_for_mobile",
    "group_cards_by_lane",
    "headline_summary",
    "lane_status",
    "load_cards",
    "load_results",
]
