from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_composer.cockpit.app import create_app
from open_composer.cockpit.data import hypotheses as H
from open_composer.cockpit.markdown import render_markdown
from open_composer.config import project_root

REPO_ROOT = project_root()


def _make_card(
    card_id: str = "H-20260101-01",
    *,
    kind: str = "H",
    title: str = "title",
    status_text: str = "",
    lane: str = "unclassified",
    lane_reason: str | None = None,
    previous: str | None = None,
    referenced_ids: tuple[str, ...] = (),
    body_markdown: str = "",
    front_matter: H.CardFrontMatter | None = None,
) -> H.Card:
    return H.Card(
        id=card_id,
        kind=kind,
        title=title,
        status_text=status_text,
        lane=lane,
        lane_reason=lane_reason,
        script=None,
        output_dir=None,
        layer=None,
        data_layer=None,
        lesson_ref=None,
        previous=previous,
        referenced_ids=referenced_ids,
        body_markdown=body_markdown,
        front_matter=front_matter,
        path=f"reports/research/hypotheses/{card_id}.md",
        parse_warnings=(),
    )


# --------------------------------------------------------------------------
# Real corpus: every card parses, none is dropped, unclassified always has a reason
# --------------------------------------------------------------------------


def test_all_real_cards_parse_and_none_is_dropped() -> None:
    hyp_dir = REPO_ROOT / "reports" / "research" / "hypotheses"
    on_disk = sorted(p.name for p in hyp_dir.glob("*.md") if p.name != "README.md")

    cards = H.load_cards(REPO_ROOT)

    assert [c.path.rsplit("/", 1)[-1] for c in cards] == on_disk
    assert len(cards) == len(on_disk)
    # README.md and trial-families.json are not cards.
    assert all(c.id != "README" for c in cards)


def test_no_card_is_ever_dropped_when_grouped_by_lane() -> None:
    cards = H.load_cards(REPO_ROOT)
    lanes = H.group_cards_by_lane(cards)
    flattened = [c for bucket in lanes.values() for c in bucket]
    assert len(flattened) == len(cards)
    assert {c.id for c in flattened} == {c.id for c in cards}


def test_every_unclassified_card_carries_a_reason_and_raw_status() -> None:
    cards = H.load_cards(REPO_ROOT)
    unclassified = [c for c in cards if c.lane == "unclassified"]
    # The vocabulary covers the whole corpus as of 2026-09-19 (19 cards, 0
    # unclassified). This is not asserted as "must stay 0" -- a new card with
    # novel status prose legitimately lands here -- but every such card must
    # carry a reason and still be rendered.
    assert len(unclassified) == 0, [(c.id, c.lane_reason) for c in unclassified]
    for card in unclassified:
        assert card.lane_reason, f"{card.id} is unclassified with no reason"


def test_the_real_cards_with_an_explicit_previous_field() -> None:
    # The invariant is that the field keeps parsing, not that the corpus stops
    # growing: every new card that declares a predecessor used to break an exact
    # equality here, which taught us to edit the test rather than read it. These
    # relations are the ones re-measured 2026-09-22, after the front-matter parser
    # learned the Chinese keys (上一环 / 上一张卡) that the corpus actually writes;
    # before that fix, cards declaring the predecessor in front matter rather than
    # in prose were silently dropped. Losing any of them means the parsing broke.
    known = {
        "H-20260919-01": "H-20260918-06",  # prose form
        "H-20260919-02": "H-20260917-01",  # prose form
        "H-20260922-01": "H-20260916-06",
        "H-20260922-02": "H-20260918-05",
        "H-20260922-04": "H-20260918-05",  # front-matter form, needs the CJK key
        "H-20260922-05": "H-20260922-02",
        "H-20260922-07": "H-20260918-02",  # front-matter form, needs the CJK key
    }
    cards = H.load_cards(REPO_ROOT)
    with_previous = {c.id: c.previous for c in cards if c.previous}
    missing = {k: v for k, v in known.items() if with_previous.get(k) != v}
    assert not missing, f"predecessor parsing regressed for {missing}"
    assert len(with_previous) >= len(known)


# --------------------------------------------------------------------------
# Lane mapping: table-driven over synthetic status strings
# --------------------------------------------------------------------------


LANE_CASES = [
    ("bare 预注册", "预注册已写死，等待评估", "preregistered"),
    ("bare 已写死", "已写死，尚未开跑", "preregistered"),
    ("bare 待跑", "设计完成，待跑", "preregistered"),
    ("bare 在跑", "在跑，预计明天出结果", "running"),
    ("bare 运行中", "运行中", "running"),
    ("bare 评估在跑", "评估在跑", "running"),
    ("bullet done+被否定", "- 状态：**done — 被否定**（四个门命中停止条件）", "refuted"),
    ("bare done+refuted", "**done / refuted**（见 L-20260918-01）", "refuted"),
    ("bare 已执行+否定", "已执行，否定", "refuted"),
    ("bare 已执行+通过", "已执行，三个 cell 通过，今天上模拟盘", "shipped"),
    ("bare 已执行+上线", "已执行，通过并上线", "shipped"),
    ("bare 搁置", "搁置，等待更多数据", "on hold"),
    ("bare 暂停", "暂停中", "on hold"),
    ("english proposed", "proposed（等你配置模型）", "proposed"),
    ("english approved", "approved（Fable 决定）", "approved"),
    ("english running", "**running -> see the lesson file**", "running"),
    ("approved but already running", "approved（Fable 决定），评估在跑", "running"),
    ("empty status", "", "unclassified"),
    (
        "done+否定 wins over incidental 预注册 mention",
        "已执行，否定。8 个族的预注册选择规则没有一个打赢",
        "refuted",
    ),
    (
        "在跑 wins over 已写死/预注册 when both present",
        "预注册已写死；描述统计已出，评估在跑",
        "running",
    ),
]


@pytest.mark.parametrize(
    "label,status_text,expected_lane", LANE_CASES, ids=[c[0] for c in LANE_CASES]
)
def test_derive_lane_table_driven(label: str, status_text: str, expected_lane: str) -> None:
    lane, reason = H.derive_lane(status_text)
    assert lane == expected_lane, (
        f"{label}: expected {expected_lane}, got {lane} (reason={reason!r})"
    )
    if lane == "unclassified":
        assert reason


def test_lane_layout_bare_line_vs_bullet(tmp_path: Path) -> None:
    hyp_dir = tmp_path / "reports" / "research" / "hypotheses"
    hyp_dir.mkdir(parents=True)
    (hyp_dir / "H-20260101-01-bare.md").write_text(
        "# H-20260101-01 bare layout\n\n"
        "状态：**已执行，通过，上线**\n执行脚本：`scripts/run_x.py`\n\n## 1. body\n",
        encoding="utf-8",
    )
    (hyp_dir / "H-20260101-02-bullet.md").write_text(
        "# H-20260101-02 bullet layout\n\n"
        "- 状态：**已执行，被否定**（详情见复盘）· 假设族：x\n\n## 1. body\n",
        encoding="utf-8",
    )
    cards = {c.id: c for c in H.load_cards(tmp_path)}
    assert cards["H-20260101-01"].lane == "shipped"
    assert cards["H-20260101-02"].lane == "refuted"


# --------------------------------------------------------------------------
# Results join by card_id
# --------------------------------------------------------------------------


def test_load_results_joins_real_summaries_by_card_id() -> None:
    # The research loop keeps writing into reports/research/iterations/ from a
    # separate session, so this asserts structure, not an exact census: the
    # three cards known to carry card_id on 2026-09-19 must still join, and
    # every summary.json that cannot join must surface as a warning naming its
    # file rather than vanish. Exact counts were removed on 2026-09-20 after a
    # concurrent research run added a summary.json and broke a hard-coded 4.
    results = H.load_results(REPO_ROOT)
    assert {"H-20260918-05", "H-20260918-06", "H-20260919-01"} <= set(results.by_card_id)
    volband_iterations = {f.iteration_id for f in results.by_card_id["H-20260919-01"]}
    assert {"h20260919_01_smoke", "h20260919_01_volband"} <= volband_iterations
    joined_files = {f.iteration_id for fs in results.by_card_id.values() for f in fs}
    all_summaries = {
        p.parent.name for p in (REPO_ROOT / "reports/research/iterations").glob("*/summary.json")
    }
    unjoined = all_summaries - joined_files
    assert unjoined, "expected at least one pre-card_id summary.json in the real corpus"
    for iteration_id in unjoined:
        assert any(iteration_id in w for w in results.warnings), f"{iteration_id} dropped silently"


def test_load_results_missing_directory_degrades_to_warning(tmp_path: Path) -> None:
    results = H.load_results(tmp_path)
    assert results.by_card_id == {}
    assert results.warnings


def test_load_results_corrupt_json_degrades_to_warning(tmp_path: Path) -> None:
    iterations_dir = tmp_path / "reports" / "research" / "iterations" / "broken_run"
    iterations_dir.mkdir(parents=True)
    (iterations_dir / "summary.json").write_text("{not valid json", encoding="utf-8")

    results = H.load_results(tmp_path)

    assert results.by_card_id == {}
    assert len(results.warnings) == 1
    assert "corrupt or unreadable" in results.warnings[0]


def test_load_results_oversized_file_degrades_to_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    iterations_dir = tmp_path / "reports" / "research" / "iterations" / "huge_run"
    iterations_dir.mkdir(parents=True)
    (iterations_dir / "summary.json").write_text(
        json.dumps({"card_id": "H-20260101-01"}), encoding="utf-8"
    )

    monkeypatch.setattr(H, "MAX_SUMMARY_BYTES", 1)  # anything real is "too big" now

    results = H.load_results(tmp_path)

    assert results.by_card_id == {}
    assert len(results.warnings) == 1
    assert "exceeds" in results.warnings[0]


def test_load_results_missing_card_id_field_degrades_to_warning(tmp_path: Path) -> None:
    iterations_dir = tmp_path / "reports" / "research" / "iterations" / "no_card_id_run"
    iterations_dir.mkdir(parents=True)
    (iterations_dir / "summary.json").write_text(json.dumps({"cell_count": 5}), encoding="utf-8")

    results = H.load_results(tmp_path)

    assert results.by_card_id == {}
    assert "no usable top-level card_id" in results.warnings[0]


# --------------------------------------------------------------------------
# Lineage: two edge kinds, cycle detection that terminates
# --------------------------------------------------------------------------


def test_build_lineage_distinguishes_explicit_and_mentioned_edges() -> None:
    a = _make_card("H-20260101-01")
    b = _make_card("H-20260101-02", previous="H-20260101-01", referenced_ids=("H-20260101-01",))
    c = _make_card("H-20260101-03", referenced_ids=("H-20260101-01",))

    graph = H.build_lineage([a, b, c])

    by_pair = {(e.source, e.target): e.kind for e in graph.edges}
    # b both declares 上一环 and repeats the id in its body: one edge, the
    # strong one, not two.
    assert by_pair[("H-20260101-01", "H-20260101-02")] == "explicit_previous"
    assert by_pair[("H-20260101-01", "H-20260101-03")] == "mentioned"
    assert len(graph.edges) == 2

    explicit_edge = next(e for e in graph.edges if e.kind == "explicit_previous")
    mentioned_edge = next(e for e in graph.edges if e.kind == "mentioned")
    assert explicit_edge.is_explicit is True
    assert mentioned_edge.is_explicit is False
    assert explicit_edge.label != mentioned_edge.label


def test_build_lineage_never_promotes_a_dashed_edge_to_solid() -> None:
    # A mention of a card that is *not* the explicit previous must stay dashed,
    # even when the same card also has an explicit previous elsewhere.
    a = _make_card("H-20260101-01")
    b = _make_card("H-20260101-02")
    c = _make_card(
        "H-20260101-03", previous="H-20260101-01", referenced_ids=("H-20260101-01", "H-20260101-02")
    )

    graph = H.build_lineage([a, b, c])
    by_pair = {(e.source, e.target): e.kind for e in graph.edges}

    assert by_pair[("H-20260101-01", "H-20260101-03")] == "explicit_previous"
    assert by_pair[("H-20260101-02", "H-20260101-03")] == "mentioned"


def test_build_lineage_reports_a_cycle_instead_of_hanging() -> None:
    a = _make_card("H-20260101-01", previous="H-20260101-03")
    b = _make_card("H-20260101-02", previous="H-20260101-01")
    c = _make_card("H-20260101-03", previous="H-20260101-02")

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(H.build_lineage, [a, b, c])
        graph = future.result(
            timeout=5
        )  # fails the test instead of hanging forever if this regresses

    assert graph.warnings
    assert any("cycle" in w for w in graph.warnings)
    assert len(graph.edges) == 3


def test_flatten_lineage_for_mobile_terminates_and_covers_pure_cycle() -> None:
    a = _make_card("H-20260101-01", previous="H-20260101-03")
    b = _make_card("H-20260101-02", previous="H-20260101-01")
    c = _make_card("H-20260101-03", previous="H-20260101-02")
    graph = H.build_lineage([a, b, c])

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(H.flatten_lineage_for_mobile, graph)
        rows = future.result(timeout=5)

    assert {r.card_id for r in rows} == {"H-20260101-01", "H-20260101-02", "H-20260101-03"}
    assert any(r.is_cycle_repeat for r in rows)


def test_build_lineage_skips_dangling_references_without_crashing() -> None:
    a = _make_card("H-20260101-01", previous="H-20260101-99", referenced_ids=("H-20260101-98",))
    graph = H.build_lineage([a])
    assert graph.edges == ()
    assert len(graph.warnings) == 2


def test_extract_criteria_sections_finds_判定_and_预注册_headings() -> None:
    body = (
        "## 1. intro\nsome text\n\n"
        "## 2. 预注册网格与判定标准\ncontent here\nmore content\n\n"
        "## 3. 结果\nother text\n"
    )
    sections = H.extract_criteria_sections(body)
    assert len(sections) == 1
    assert "预注册" in sections[0].heading
    assert "content here" in sections[0].markdown
    assert "结果" not in sections[0].markdown


# --------------------------------------------------------------------------
# Markdown renderer: escaping and secret scrubbing
# --------------------------------------------------------------------------


def test_render_markdown_escapes_script_tags() -> None:
    out = render_markdown("before <script>alert('x')</script> after")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_markdown_escapes_script_tag_inside_heading_and_list() -> None:
    out = render_markdown("## <script>bad()</script>\n\n- <script>bad()</script>\n")
    assert "<script>" not in out
    assert out.count("&lt;script&gt;") == 2


def test_render_markdown_scrubs_secret_shaped_tokens() -> None:
    out = render_markdown("leaked key=sk-abcdefghijklmnopqrstuvwxyz1234 in a card body")
    assert "sk-abcdefghijklmnopqrstuvwxyz1234" not in out
    assert "REDACTED" in out


def test_render_markdown_renders_expected_constructs() -> None:
    body = (
        "# heading one\n"
        "## heading two\n"
        "a **bold** word and `inline code` and a [link](https://example.com/x)\n\n"
        "- item one\n- item two\n\n"
        "```python\nprint('hi')\n```\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n"
    )
    out = render_markdown(body)
    assert "<h1>heading one</h1>" in out
    assert "<h2>heading two</h2>" in out
    assert "<strong>bold</strong>" in out
    assert "<code>inline code</code>" in out
    assert '<a href="https://example.com/x"' in out
    assert "<ul><li>item one</li><li>item two</li></ul>" in out
    assert "<pre><code" in out and "print(&#x27;hi&#x27;)" in out
    assert '<table class="responsive-table">' in out
    assert '<td data-label="a">1</td>' in out


def test_render_markdown_rejects_javascript_scheme_links() -> None:
    out = render_markdown("[click me](javascript:alert(1))")
    assert "<a href" not in out
    assert "javascript:alert(1)" in out  # visible as inert text, not a live link


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize("path", ["/", "/lineage", "/card/H-20260919-01"])
def test_screens_return_200(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/card/nope", "/card/../../etc/passwd", "/card/H-99999999-99"])
def test_bad_card_ids_return_4xx_not_500(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert 400 <= response.status_code < 500


def test_card_detail_renders_body_and_results(client: TestClient) -> None:
    response = client.get("/card/H-20260918-05")
    assert response.status_code == 200
    assert "h20260918_05_recent_menu" in response.text
    assert "unstructured" in response.text


def test_hypotheses_report_degrades_when_repo_root_is_empty(tmp_path: Path) -> None:
    report = H.build_hypotheses_report(tmp_path)
    assert report.cards == ()
    assert report.lanes == {lane: () for lane in H.LANES}
    assert report.results.by_card_id == {}
