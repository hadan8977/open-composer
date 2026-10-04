"""The report centre (`/reports`, 2026-10-04): the index over the three report
kinds, the markdown rendering, and the route's validation. Every test builds
its own files under ``tmp_path``; the autouse fixture in ``tests/conftest.py``
keeps real transcripts and agent trees out of reach."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_composer.cockpit.app import create_app
from open_composer.cockpit.data import reports as R

DAILY = "# Open Composer 日报 · 2026-10-04（周日）\n\n概览。\n\n## 需要你处理\n\n- 没有。\n"
WEEKLY = "# 周报 2026-W40\n\n## 0. 一页结论\n\n- **钱**：+1.12%。\n"
WEEKLY_DATA = "# 附：一周数据\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
ROUND = (
    "# 主审轮 2026-10-05 01:07 UTC\n\n- **做了什么**：审核 v1.4。\n- **结果**：保留 M0。\n"
    "- **模拟盘值守**：正常。\n- 第四条不进首页。\n"
)


def _repo(tmp_path: Path, *, rounds: bool = True) -> Path:
    (tmp_path / "logs/owner-report").mkdir(parents=True)
    (tmp_path / "reports/owner/weekly").mkdir(parents=True)
    (tmp_path / "reports/owner/rounds").mkdir(parents=True)
    (tmp_path / "logs/owner-report/daily-2026-10-03.md").write_text("# 日报 10-03\n", "utf-8")
    (tmp_path / "logs/owner-report/daily-2026-10-04.md").write_text(DAILY, "utf-8")
    (tmp_path / "logs/owner-report/sent-daily-2026-10-04.json").write_text("{}", "utf-8")
    (tmp_path / "logs/owner-report/weekly-2026-10-04.md").write_text(WEEKLY_DATA, "utf-8")
    (tmp_path / "reports/owner/weekly/2026-W40.zh.md").write_text(WEEKLY, "utf-8")
    (tmp_path / "reports/owner/weekly/notes.zh.md").write_text("# not a week\n", "utf-8")
    (tmp_path / "reports/owner/rounds/README.md").write_text("# how to\n", "utf-8")
    if rounds:
        (tmp_path / "reports/owner/rounds/2026-10-05T0107Z-lead.md").write_text(ROUND, "utf-8")
        (tmp_path / "reports/owner/rounds/2026-10-05T0407Z-exec.md").write_text(
            "# 执行轮 2026-10-05 04:07 UTC\n\n- 跑了 T-03。\n", "utf-8"
        )
        (tmp_path / "reports/owner/rounds/junk.md").write_text("# junk\n", "utf-8")
    return tmp_path


# --------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------


def test_index_lists_each_kind_newest_first_and_skips_strays(tmp_path: Path) -> None:
    index = R.build_report_index(_repo(tmp_path), now=datetime(2026, 10, 5, 6, tzinfo=UTC))
    assert [e.id for e in index.daily] == ["daily-2026-10-04", "daily-2026-10-03"]
    assert index.daily[0].title == "Open Composer 日报 · 2026-10-04（周日）"
    assert [e.id for e in index.weekly] == ["2026-W40"]
    assert index.weekly[0].note == "judgement + data"
    assert index.weekly[0].paths == (
        "reports/owner/weekly/2026-W40.zh.md",
        "logs/owner-report/weekly-2026-10-04.md",
    )
    assert [e.id for e in index.rounds] == ["2026-10-05T0407Z-exec", "2026-10-05T0107Z-lead"]
    assert index.rounds[1].is_lead and index.latest_lead_round is index.rounds[1]
    assert index.newest is index.rounds[0]
    assert any("notes.zh.md" in w for w in index.warnings)
    assert any("junk.md" in w for w in index.warnings)
    assert not any("README" in w for w in index.warnings)


def test_index_is_empty_but_sound_for_a_bare_repo(tmp_path: Path) -> None:
    index = R.build_report_index(tmp_path)
    assert index.total == 0 and index.newest is None and index.latest_lead_round is None


def test_weekly_data_without_a_judgement_is_listed_as_data_only(tmp_path: Path) -> None:
    (tmp_path / "logs/owner-report").mkdir(parents=True)
    (tmp_path / "logs/owner-report/weekly-2026-10-11.md").write_text(WEEKLY_DATA, "utf-8")
    index = R.build_report_index(tmp_path)
    assert [(e.id, e.note) for e in index.weekly] == [("2026-W41", "data only")]


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def test_markdown_renders_tables_ordered_and_nested_lists_and_escapes_html() -> None:
    html = R.render_report_markdown(
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n1. one\n2. two\n   - nested\n\n<script>x()</script>\n"
    )
    assert "<table>" in html and "<td>1</td>" in html
    assert "<ol>" in html and html.count("<ul>") == 1
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_markdown_scrubs_secrets_before_rendering() -> None:
    html = R.render_report_markdown("key: APCA_API_SECRET_KEY=abcdef123456 and sk-abcdefghijkl\n")
    assert "abcdef123456" not in html and "sk-abcdefghijkl" not in html
    assert "REDACTED" in html


def test_load_report_joins_the_weekly_halves_and_reports_unreadable_files(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    index = R.build_report_index(root)
    doc = R.load_report(root, index.find("weekly", "2026-W40"))
    assert "一页结论" in doc.html and doc.appendix_html and "<table>" in doc.appendix_html
    assert doc.error is None and doc.modified_at is not None
    (root / "logs/owner-report/daily-2026-10-04.md").unlink()
    broken = R.load_report(root, index.find("daily", "daily-2026-10-04"))
    assert broken.html == "" and broken.error and "cannot read" in broken.error


def test_report_bullets_take_the_first_top_level_items() -> None:
    assert R.report_bullets(ROUND) == (
        "做了什么：审核 v1.4。",
        "结果：保留 M0。",
        "模拟盘值守：正常。",
    )
    assert R.report_title("no heading here\n", "fallback") == "fallback"


@pytest.mark.parametrize(
    "kind,report_id,ok",
    [
        ("daily", "daily-2026-10-04", True),
        ("daily", "daily-2026-10-04.md", False),
        ("daily", "../app", False),
        ("weekly", "2026-W40", True),
        ("weekly", "2026-W4", False),
        ("rounds", "2026-10-05T0107Z-lead", True),
        ("rounds", "README", False),
        ("nope", "daily-2026-10-04", False),
    ],
)
def test_valid_report_id(kind: str, report_id: str, ok: bool) -> None:
    assert R.valid_report_id(kind, report_id) is ok


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    root = _repo(tmp_path)
    monkeypatch.setattr("open_composer.cockpit.app.project_root", lambda: root)
    monkeypatch.setattr("open_composer.cockpit.api.project_root", lambda: root)
    monkeypatch.setattr("open_composer.cockpit.data.health.project_root", lambda: root)
    return TestClient(create_app(warm=False))


def test_reports_index_shows_three_kinds_newest_first(client: TestClient) -> None:
    page = client.get("/reports")
    assert page.status_code == 200
    text = page.text
    for kind in ("Daily", "Weekly", "Rounds"):
        assert f'<span class="t-cap">{kind}</span>' in text
    assert text.index("/reports/daily/daily-2026-10-04") < text.index(
        "/reports/daily/daily-2026-10-03"
    )
    assert text.index("/reports/rounds/2026-10-05T0407Z-exec") < text.index(
        "/reports/rounds/2026-10-05T0107Z-lead"
    )
    assert 'href="/reports/rounds/README"' not in text and 'href="/reports/rounds/junk"' not in text
    assert 'class="reports"' in text  # list mode, not detail mode


def test_reports_detail_renders_the_document(client: TestClient) -> None:
    page = client.get("/reports/weekly/2026-W40")
    assert page.status_code == 200
    assert "一页结论" in page.text and "Data appendix" in page.text
    assert 'class="reports is-detail"' in page.text
    assert "report-row is-open" in page.text
    assert "<title>周报 2026-W40 · Reports · Quant</title>" in page.text


def test_reports_empty_rounds_has_an_explained_empty_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _repo(tmp_path, rounds=False)
    monkeypatch.setattr("open_composer.cockpit.app.project_root", lambda: root)
    monkeypatch.setattr("open_composer.cockpit.data.health.project_root", lambda: root)
    page = TestClient(create_app(warm=False)).get("/reports")
    assert page.status_code == 200
    assert "No round reports yet" in page.text


def test_reports_on_a_bare_repo_renders(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("open_composer.cockpit.app.project_root", lambda: tmp_path)
    monkeypatch.setattr("open_composer.cockpit.data.health.project_root", lambda: tmp_path)
    page = TestClient(create_app(warm=False)).get("/reports")
    assert page.status_code == 200
    assert "No daily report yet" in page.text and "Nothing to read yet" in page.text


@pytest.mark.parametrize(
    "path",
    [
        "/reports/daily/nope",
        "/reports/daily/daily-2026-10-09",
        "/reports/daily/..%2f..%2fapp.py",
        "/reports/rounds/README",
        "/reports/rounds/junk",
        "/reports/weekly/notes",
        "/reports/secrets/daily-2026-10-04",
    ],
)
def test_bad_report_paths_return_404_not_500(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_reports_api_lists_the_index(client: TestClient) -> None:
    body = client.get("/api/reports.json").json()
    assert [e["id"] for e in body["rounds"]] == ["2026-10-05T0407Z-exec", "2026-10-05T0107Z-lead"]
    assert body["weekly"][0]["href"] == "/reports/weekly/2026-W40"
