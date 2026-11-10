from __future__ import annotations

import html
import json
import re
import threading
from html.parser import HTMLParser
from pathlib import Path

import pytest
from cockpit_contract_fixture import cockpit_workspace as cockpit_workspace
from fastapi.testclient import TestClient

from open_composer.cockpit import app as APP_MODULE
from open_composer.cockpit.app import create_app
from open_composer.cockpit.data.hypotheses import load_cards
from open_composer.cockpit.data.queue import parse_queue
from open_composer.cockpit.security import PathTraversalError, safe_repo_path, secret_scrub


@pytest.fixture
def client(cockpit_workspace: Path) -> TestClient:
    return TestClient(create_app(warm=False))


# --------------------------------------------------------------------------
# Routes render
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/reports",
        "/research",
        "/hypotheses",
        "/health",
        "/healthz",
        "/lineage",
        "/agents",
        "/paper",
        "/paper/accounts",
        "/paper/history",
        "/quota",
    ],
)
def test_core_routes_return_200(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200


# --------------------------------------------------------------------------
# The owner-facing home, paper pages and shared navigation use Chinese.
# Research and system page content retains its existing English vocabulary;
# authored source content may still be Chinese.
# --------------------------------------------------------------------------

_CJK_RE = re.compile(r"[一-鿿]")


class _DropZh(HTMLParser):
    """Strip every element marked `lang="zh"` (owner-facing Chinese content:
    attention items, live-track text, report titles and bullets) and return
    the rest of the document's text, so the chrome can be checked alone."""

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self._depth = 0
        self._stack: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        zh = dict(attrs).get("lang") == "zh"
        self._stack.append(zh)
        if zh:
            self._depth += 1
        for _name, value in attrs:
            if value and not self._depth:
                self.out.append(value)

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack.pop():
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._depth:
            self.out.append(data)


def chrome_text(page: str) -> str:
    parser = _DropZh()
    parser.feed(page)
    return "\n".join(parser.out)


@pytest.mark.parametrize(
    "path", ["/research", "/hypotheses", "/lineage", "/health", "/agents", "/quota"]
)
def test_no_cjk_outside_card_titles_on_pages_that_do_not_embed_card_bodies(
    client: TestClient, cockpit_workspace: Path, path: str
) -> None:
    response = client.get(path)
    assert response.status_code == 200
    # Jinja2 autoescapes a title's ASCII quotes (e.g. `"` -> `&#34;`) on the
    # way to HTML, so unescape before matching the raw title text back out.
    # Elements marked `lang="zh"` carry owner-facing content (the Today
    # screen's attention items, live-track text and report headlines) and
    # are dropped first; `/reports` embeds whole Chinese documents and is
    # not checked here, like `/card/<id>`.
    # Localized shared navigation does not change these pages' content language.
    page = re.sub(r"<nav\b[^>]*>.*?</nav>", "", response.text, flags=re.S)
    page = re.sub(r'<header class="mobile-head[^>]*>.*?</header>', "", page, flags=re.S)
    text = html.unescape(chrome_text(page))
    # `title`, `layer` and `data_layer` are the card's own authored prose
    # (parsed from its `层：`/`数据层：` fields) shown as-is on the board row
    # (`/`) and lineage node (`/lineage`) -- card content, not chrome. Longest
    # first: some cards' `layer` (e.g. "选股") is a literal substring of
    # another card's (e.g. "选股（独立策略）"), and stripping the short one
    # first would mangle the longer one into a leftover fragment.
    # The research task queue (`/` tile, `/hypotheses` lanes) shows each
    # task's authored title, status text and newest note: content too.
    queue_text = (cockpit_workspace / "reports/research/control/autonomous-queue.md").read_text(
        encoding="utf-8"
    )
    known_content = sorted(
        {
            field
            for card in load_cards(cockpit_workspace)
            for field in (card.title, card.layer, card.data_layer)
            if field
        }
        | {
            field
            for item in parse_queue(queue_text)
            for field in (item.title, item.status_text, item.last_note)
            if field
        },
        key=len,
        reverse=True,
    )
    for field in known_content:
        text = text.replace(field, "")
    found = _CJK_RE.findall(text)
    assert not found, f"{path} rendered {len(found)} CJK character(s) in UI chrome: {found!r}"


def test_healthz_is_json_liveness(client: TestClient) -> None:
    response = client.get("/healthz")
    body = response.json()
    assert body["status"] == "ok"
    assert "time" in body


def test_health_page_renders_cron_and_freshness_sections(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert "Data freshness" in response.text
    assert "Cron jobs" in response.text


# --------------------------------------------------------------------------
# The GET-only invariant. This is the enforcement mechanism for the whole
# read-only design (plan section 6, rule 1): if this test starts failing, a
# write route was added somewhere and the change must be reverted or reworked
# rather than the test relaxed.
# --------------------------------------------------------------------------


def test_every_route_is_get_or_head_only() -> None:
    app = create_app(warm=False)
    checked = 0
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            # Mounted sub-apps (StaticFiles) do not expose `.methods` on the
            # `Mount` object itself; StaticFiles enforces GET/HEAD internally
            # (see test_static_mount_rejects_post below) so it is not a gap in
            # this invariant, just a different enforcement point.
            continue
        checked += 1
        assert methods <= {"GET", "HEAD"}, (
            f"route {getattr(route, 'path', route)!r} allows {methods}, "
            "which violates the cockpit's no-write-route rule"
        )
    assert checked > 0, "expected at least one concrete route to check"


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/reports",
        "/research",
        "/health",
        "/healthz",
        "/lineage",
        "/agents",
        "/paper",
        "/paper/accounts",
        "/paper/history",
        "/paper/ledger/unknown",
        "/quota",
    ],
)
def test_post_is_rejected_with_405(client: TestClient, path: str) -> None:
    response = client.post(path)
    assert response.status_code == 405


def test_static_assets_are_immutable_and_versioned(client: TestClient) -> None:
    """Static files carry a one-year immutable cache header and every page
    references them with a content-hash query, so a redeploy is picked up
    at once while an unchanged build never re-validates through the tunnel.
    HTML itself never carries that header."""
    asset = client.get("/static/css/cockpit.css")
    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    page = client.get("/")
    versions = set(
        re.findall(r"/static/(?:css/cockpit\.css|js/cockpit\.js)\?v=([0-9a-f]{12})", page.text)
    )
    assert len(versions) == 1
    assert "immutable" not in page.headers.get("cache-control", "")


def test_shell_is_named_quant(client: TestClient) -> None:
    page = client.get("/")
    assert "<i></i>Quant</a>" in page.text
    assert "Cockpit</a>" not in page.text
    assert "<title>总览 · Quant</title>" in page.text
    assert "<title>模拟盘 · Quant</title>" in client.get("/paper").text
    assert "<title>Research · Quant</title>" in client.get("/research").text
    assert "<title>Reports · Quant</title>" in client.get("/reports").text


def test_static_mount_rejects_post(client: TestClient) -> None:
    response = client.post("/static/css/cockpit.css")
    assert response.status_code == 405


@pytest.fixture
def published_paper_ui(cockpit_workspace: Path, monkeypatch: pytest.MonkeyPatch):
    from open_composer.cockpit import api
    from open_composer.cockpit.data.paper_overview import _chart

    rows = [
        dict(
            id=f"six/MODEL_{index}",
            label=f"Model {index}",
            capital_usd=20000,
            pnl_usd=10 * index,
            return_pct=index / 20,
            status="已退出" if index == 8 else "实际账本",
        )
        for index in range(9)
    ]
    daily = [
        dict(day="2026-10-23", pnl_usd=360, return_pct=0.2, missing=[], pools=["six"]),
        dict(day="2026-10-26", pnl_usd=None, return_pct=None, missing=["six"], pools=["six"]),
    ]
    overview = dict(
        available=True,
        through_session="2026-10-26",
        snapshot=dict(
            rows=rows,
            pnl_usd=363.45,
            return_pct=0.2019166667,
            capital_usd=180000,
            adjustment_usd=3.45,
            unassigned_capital_usd=0,
            pool_readings=[],
            at_start="2026-10-27T04:20:00+00:00",
            at_end="2026-10-27T04:20:03+00:00",
        ),
        daily=daily,
        charts={field: _chart(daily, field) for field in ("pnl_usd", "return_pct")},
    )
    monkeypatch.setattr(APP_MODULE, "load_paper_overview", lambda root: overview)
    monkeypatch.setattr(api, "load_paper_overview", lambda root: overview)
    return TestClient(create_app(warm=False)), overview


@pytest.mark.parametrize("path", ["/", "/paper"])
def test_paper_comparison_mount_receives_all_top_level_choices_and_fallback_links(
    published_paper_ui, path: str
) -> None:
    client, overview = published_paper_ui
    response = client.get(path)
    assert response.status_code == 200
    text = response.text
    assert 'data-native-comparison aria-label="策略收益比较"' in text
    assert "data-comparison-root" in text
    assert 'type="module" src="/static/js/paper-comparison.mjs?v=' in text
    match = re.search(r'<script type="application/json">(.*?)</script>', text, flags=re.S)
    assert match is not None
    comparison = json.loads(match[1])
    assert comparison["initial_capital_usd"] == 100000
    assert comparison["snapshot_at"] == overview["snapshot"]["at_end"]
    assert [s["id"] for s in comparison["strategies"]] == [
        row["id"] for row in overview["snapshot"]["rows"]
    ]
    assert [s["latest_return_pct"] for s in comparison["strategies"]] == [
        row["return_pct"] for row in overview["snapshot"]["rows"]
    ]
    assert sum(s["default_selected"] for s in comparison["strategies"]) == 8
    assert comparison["strategies"][-1]["archived"]
    # These fixtures have a current valuation but no published historical
    # strategy series. The chart input must not manufacture daily points.
    assert comparison["days"] == []
    assert "<details" not in text
    fallback = re.search(r"<noscript>(.*?)</noscript>", text, flags=re.S)
    assert fallback is not None
    assert re.findall(r'href="([^"]+)"', fallback[1]) == [
        "/paper/ledger/" + row["id"] for row in overview["snapshot"]["rows"]
    ]
    assert "data-total-pnl" not in text
    assert "账户、数据与运行明细" not in text
    assert "计算口径与数据日期" not in text


def test_ledger_links_open_detail_and_unknown_ids_return_404(published_paper_ui) -> None:
    client, overview = published_paper_ui
    for row in overview["snapshot"]["rows"]:
        response = client.get("/paper/ledger/" + row["id"])
        assert response.status_code == 200
        assert f'data-title="{row["label"]}"' in response.text
        history_id = (
            "account--quant1--broker-daily" if row["id"] == "F1" else row["id"].replace("/", "--")
        )
        assert f'href="/paper/history#history-{history_id}"' in response.text
    partial = client.get("/paper/ledger/six/MODEL_0?partial=1")
    assert partial.status_code == 200 and 'data-title="Model 0"' in partial.text
    assert "<html" not in partial.text
    assert client.get("/paper/ledger/six/UNKNOWN").status_code == 404


def test_paper_navigation_and_api_share_the_published_dashboard(published_paper_ui) -> None:
    client, overview = published_paper_ui
    for path, label in (
        ("/paper", "策略"),
        ("/paper/accounts", "账户"),
        ("/paper/history", "历史"),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert f'href="{path}" aria-current="page">{label}</a>' in response.text
    response = client.get("/api/paper.json")
    assert response.status_code == 200
    dashboard = response.json()["dashboard"]
    assert dashboard["snapshot"] == overview["snapshot"]
    assert [row["id"] for row in dashboard["rows"]] == [
        row["id"] for row in overview["snapshot"]["rows"]
    ]


# --------------------------------------------------------------------------
# secret_scrub
# --------------------------------------------------------------------------


SECRET_SCRUB_CASES = [
    (
        "openai-style key",
        "key=sk-abcdefghijklmnopqrstuvwxyz1234",
        "sk-abcdefghijklmnopqrstuvwxyz1234",
    ),
    (
        "anthropic-style key",
        "ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnop",
        "sk-ant-api03-abcdefghijklmnop",
    ),
    (
        "bearer header",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig",
        "eyJhbGciOiJIUzI1NiJ9.payload.sig",
    ),
    (
        "claude oauth token env",
        "CLAUDE_CODE_OAUTH_TOKEN=abcdefghijklmnopqrstuvwx",
        "abcdefghijklmnopqrstuvwx",
    ),
    (
        "openai api key env",
        "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwx",
        "sk-proj-abcdefghijklmnopqrstuvwx",
    ),
    ("alpaca key id", "APCA_API_KEY_ID=AKIAABCDEFGHIJKLMNOP", "AKIAABCDEFGHIJKLMNOP"),
    (
        "alpaca secret key",
        "APCA_API_SECRET_KEY=abcdefghijklmnopqrstuvwxyz123456",
        "abcdefghijklmnopqrstuvwxyz123456",
    ),
    ("generic token assignment", "some_token: 'abcdefgh12345678'", "abcdefgh12345678"),
    ("generic password assignment", 'db_password = "hunter2hunter2"', "hunter2hunter2"),
    ("generic secret assignment", "webhook_secret=abcdef0123456789", "abcdef0123456789"),
    (
        "bare jwt",
        "relay eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fw",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
    ),
    (
        "cloudflare connector token (jwt-shaped, no dots)",
        "token eyJhIjoiNjk3ZTEyMzQ1Njc4OTBhYmNkZWYi"
        "LCJ0IjoiODliNWI4N2EtMTIzNCIsInMiOiJaWGhoYlhCc1pRPT0ifQ",
        "eyJhIjoiNjk3ZTEyMzQ1Njc4OTBhYmNkZWYi",
    ),
    (
        "basic auth header",
        "Authorization: Basic dXNlcjpwYXNzd29yZDEyMzQ1Ng==",
        "dXNlcjpwYXNzd29yZDEyMzQ1Ng==",
    ),
    (
        "lower-case bearer in a quoted curl command",
        "curl -H 'authorization: bearer abcdefghijklmnop'",
        "abcdefghijklmnop",
    ),
    (
        "github token",
        "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef012345",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef012345",
    ),
    ("slack token", "xoxb-FAKETESTNOTREAL0000000000000", "FAKETESTNOTREAL0000000000000"),
    (
        "pem private key block",
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ\n"
        "-----END OPENSSH PRIVATE KEY-----",
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ",
    ),
]

#: Text that mentions key/token words but carries no secret. Agent transcripts and
#: cron logs are full of these; masking them would make the timeline unreadable.
SECRET_SCRUB_KEEP_CASES = [
    "fresh_tokens: 4321 cache_read: 99",
    "sorted(rows, key=len)",
    "pytest -k test_quota --keyword=foo",
    "card_id: H-20260919-01 tokens=12",
    "the token budget is 5h fresh tokens",
]


@pytest.mark.parametrize(
    "label,raw,secret", SECRET_SCRUB_CASES, ids=[c[0] for c in SECRET_SCRUB_CASES]
)
def test_secret_scrub_masks_each_pattern(label: str, raw: str, secret: str) -> None:
    scrubbed = secret_scrub(raw)
    assert secret not in scrubbed, f"{label}: secret value leaked through: {scrubbed!r}"
    assert "REDACTED" in scrubbed, f"{label}: no redaction marker present: {scrubbed!r}"


@pytest.mark.parametrize("text", SECRET_SCRUB_KEEP_CASES)
def test_secret_scrub_leaves_key_words_without_a_secret_alone(text: str) -> None:
    assert secret_scrub(text) == text


def test_secret_scrub_preserves_non_secret_text() -> None:
    text = "line one\nkey=sk-abcdefghijklmnopqrstuvwxyz1234\nline three"
    scrubbed = secret_scrub(text)
    assert "line one" in scrubbed
    assert "line three" in scrubbed


def test_secret_scrub_is_idempotent_and_handles_empty_string() -> None:
    assert secret_scrub("") == ""
    once = secret_scrub("token=abcdefgh12345678")
    twice = secret_scrub(once)
    assert once == twice


# --------------------------------------------------------------------------
# safe_repo_path
# --------------------------------------------------------------------------


def test_safe_repo_path_resolves_inside_repo(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "note.md").write_text("hello", encoding="utf-8")
    resolved = safe_repo_path("reports/note.md", root=tmp_path)
    assert resolved == (tmp_path / "reports" / "note.md").resolve()


def test_safe_repo_path_rejects_dotdot_traversal(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    with pytest.raises(PathTraversalError):
        safe_repo_path("reports/../../etc/passwd", root=tmp_path)


def test_safe_repo_path_rejects_absolute_path_outside_repo(tmp_path: Path) -> None:
    with pytest.raises(PathTraversalError):
        safe_repo_path("/etc/passwd", root=tmp_path)


def test_safe_repo_path_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-target"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_text("nope", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    escape_link = repo / "escape"
    escape_link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathTraversalError):
        safe_repo_path("escape/secret.txt", root=repo)


# --------------------------------------------------------------------------
# Health screen degrades gracefully when a data source is missing
# --------------------------------------------------------------------------


def test_health_page_renders_when_repo_root_has_no_data_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cockpit_workspace: Path
) -> None:
    # An empty directory has no `data/`, no `logs/`, and (from this process'
    # point of view) an unrelated crontab -- every data-freshness lookup must
    # fall back to "unknown" rather than raise, and the page must still render.
    monkeypatch.setattr("open_composer.cockpit.app.project_root", lambda: tmp_path)
    monkeypatch.setattr("open_composer.cockpit.data.health.project_root", lambda: tmp_path)

    app = create_app(warm=False)
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert "unknown" in response.text


# --------------------------------------------------------------------------
# T10: the calibration/usage-estimate/live-quota warm thread
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_warm_thread_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this module starts from "no warm thread started yet".

    Reset the quota, Today and research-overview guards so each test observes
    its own start behavior without inheriting another app's warm state.
    """
    monkeypatch.setattr(APP_MODULE, "_WARM_THREAD_STARTED", False)
    monkeypatch.setattr(APP_MODULE, "_TODAY_WARM_STARTED", False)
    monkeypatch.setattr(APP_MODULE, "_OVERVIEW_WARM_STARTED", False)


def test_warm_loop_returns_immediately_when_transcript_root_is_absent() -> None:
    """`_warm_loop` must never enter its `while True` when there is nothing
    to warm. `tests/conftest.py`'s autouse fixture already points
    `CLAUDE_PROJECTS_DIR` at a path that does not exist for every test in
    the suite, so calling the loop body directly here is the same "roots
    absent" case `create_app(warm=True)` would hit under pytest -- driven
    through a joined, timed-out thread rather than a bare call, so a bug
    that removed the early return would fail this test instead of hanging
    the whole suite.
    """
    thread = threading.Thread(target=APP_MODULE._warm_loop, daemon=True)
    thread.start()
    thread.join(timeout=2.0)
    assert not thread.is_alive(), (
        "_warm_loop must return at once when its transcript root is absent"
    )


def test_start_warm_thread_guards_against_double_start() -> None:
    first = APP_MODULE._start_warm_thread()
    second = APP_MODULE._start_warm_thread()
    try:
        assert first is not None
        assert first.daemon is True
        assert second is None, "a second start must be a no-op, not a second thread"
    finally:
        first.join(timeout=2.0)


def test_create_app_default_warm_true_starts_the_thread_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default serving starts all four daemon warmers once per process.

    Keep the real starters/guards and replace only loop bodies, so the
    contract verifies startup without scanning data or leaving daemon loops.
    """
    started: list[threading.Thread] = []
    original = threading.Thread

    def tracking_thread(*args, **kwargs):
        thread = original(*args, **kwargs)
        started.append(thread)
        return thread

    for target in (
        "_warm_loop",
        "_today_warm_loop",
        "_research_overview_loop",
        "_paper_equity_loop",
    ):
        monkeypatch.setattr(APP_MODULE, target, lambda: None)
    monkeypatch.setattr(APP_MODULE.threading, "Thread", tracking_thread)

    create_app()
    create_app()  # a second app in the same process must not add a second thread

    assert {thread.name for thread in started} == {
        APP_MODULE._WARM_THREAD_NAME,
        APP_MODULE._TODAY_WARM_THREAD_NAME,
        APP_MODULE._OVERVIEW_WARM_THREAD_NAME,
        "cockpit-paper-equity-warm",
    }
    assert len(started) == 4
    for thread in started:
        assert thread.daemon is True
        thread.join(timeout=2.0)
        assert not thread.is_alive()


def test_create_app_warm_false_never_starts_the_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_start():
        raise AssertionError("warm=False must disable every warmer")

    for name in (
        "_start_warm_thread",
        "_start_today_warm_thread",
        "_start_research_overview_thread",
    ):
        monkeypatch.setattr(APP_MODULE, name, forbidden_start)
    create_app(warm=False)
    assert APP_MODULE._WARM_THREAD_STARTED is False
    assert APP_MODULE._TODAY_WARM_STARTED is False
    assert APP_MODULE._OVERVIEW_WARM_STARTED is False
    assert not any(t.name == APP_MODULE._WARM_THREAD_NAME for t in threading.enumerate())


def test_log_tail_quoting_chinese_is_marked_as_content() -> None:
    from open_composer.cockpit.data.health import CronLogStatus

    def status(tail: str | None) -> CronLogStatus:
        return CronLogStatus(
            path="logs/owner_report.log",
            exists=True,
            mtime=None,
            size_bytes=1,
            has_error_marker=False,
            tail_snippet=tail,
            status="ok",
        )

    assert status("2026-10-06T00:50:05Z [Open Composer] 日报 10-06（周二）").tail_has_cjk
    assert not status("sent to 1 recipient(s)").tail_has_cjk
    assert not status(None).tail_has_cjk
