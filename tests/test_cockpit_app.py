from __future__ import annotations

import html
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_composer.cockpit.app import create_app
from open_composer.cockpit.data.hypotheses import load_cards
from open_composer.cockpit.security import PathTraversalError, safe_repo_path, secret_scrub
from open_composer.config import project_root


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


# --------------------------------------------------------------------------
# Routes render
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", ["/", "/health", "/healthz", "/lineage", "/agents", "/paper", "/quota"]
)
def test_core_routes_return_200(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200


# --------------------------------------------------------------------------
# UI is English-only (plan section 3.5): the parsing vocabulary that matches
# the Chinese source cards stays Chinese in the Python data layer, and a
# card's own authored title is Chinese card *content* (the same category as
# the card body rendered on `/card/<id>`) -- both `/` and `/lineage` legitimately
# display every card's title (board row / graph node & tooltip), and all 19
# real cards have a Chinese title, so this test strips those known titles out
# before checking. What must never come back as CJK is the surrounding UI
# chrome itself: nav labels, headings, lane names, chips, warnings, captions.
# --------------------------------------------------------------------------

_CJK_RE = re.compile(r"[一-鿿]")


@pytest.mark.parametrize("path", ["/", "/lineage", "/health", "/agents", "/paper", "/quota"])
def test_no_cjk_outside_card_titles_on_pages_that_do_not_embed_card_bodies(
    client: TestClient, path: str
) -> None:
    response = client.get(path)
    assert response.status_code == 200
    # Jinja2 autoescapes a title's ASCII quotes (e.g. `"` -> `&#34;`) on the
    # way to HTML, so unescape before matching the raw title text back out.
    text = html.unescape(response.text)
    # `title`, `layer` and `data_layer` are the card's own authored prose
    # (parsed from its `层：`/`数据层：` fields) shown as-is on the board row
    # (`/`) and lineage node (`/lineage`) -- card content, not chrome. Longest
    # first: some cards' `layer` (e.g. "选股") is a literal substring of
    # another card's (e.g. "选股（独立策略）"), and stripping the short one
    # first would mangle the longer one into a leftover fragment.
    known_content = sorted(
        {
            field
            for card in load_cards(project_root())
            for field in (card.title, card.layer, card.data_layer)
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
    app = create_app()
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
    ["/", "/health", "/healthz", "/lineage", "/agents", "/paper", "/quota"],
)
def test_post_is_rejected_with_405(client: TestClient, path: str) -> None:
    response = client.post(path)
    assert response.status_code == 405


def test_static_mount_rejects_post(client: TestClient) -> None:
    response = client.post("/static/css/cockpit.css")
    assert response.status_code == 405


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
]


@pytest.mark.parametrize(
    "label,raw,secret", SECRET_SCRUB_CASES, ids=[c[0] for c in SECRET_SCRUB_CASES]
)
def test_secret_scrub_masks_each_pattern(label: str, raw: str, secret: str) -> None:
    scrubbed = secret_scrub(raw)
    assert secret not in scrubbed, f"{label}: secret value leaked through: {scrubbed!r}"
    assert "REDACTED" in scrubbed, f"{label}: no redaction marker present: {scrubbed!r}"


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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # An empty directory has no `data/`, no `logs/`, and (from this process'
    # point of view) an unrelated crontab -- every data-freshness lookup must
    # fall back to "unknown" rather than raise, and the page must still render.
    monkeypatch.setattr("open_composer.cockpit.app.project_root", lambda: tmp_path)
    monkeypatch.setattr("open_composer.cockpit.data.health.project_root", lambda: tmp_path)

    app = create_app()
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert "unknown" in response.text
