"""FastAPI application factory for the read-only cockpit (Step 18, T3+T4).

Everything this app can do is a GET (or HEAD) request against files this repo
already owns: crontab, `df`/`free`, hypothesis cards and their lineage (T4),
and (T5-T8) paper rehearsal artifacts and agent session logs later. There is
intentionally no POST/PUT/PATCH/DELETE route anywhere -- ``tests/test_cockpit_app.py``
walks ``app.routes`` and fails loudly if one ever appears; treat that test as
the enforcement mechanism for the whole design, not a formality.

Authentication is not this app's job: ``oc cockpit serve`` (see
``open_composer/cli.py``) refuses anything but ``127.0.0.1``, and Cloudflare
Access authenticates at the edge (see ``AGENTS.md``).

Interface for T5-T8
-------------------
* ``SCREENS`` is the single source of truth for the five-screen nav (slug, URL
  path, label). Add a screen's route with the same slug used here and its stub
  disappears automatically -- there is no separate registry to update.
* ``_base_context(request, active)`` returns the context dict every screen
  must merge into its own before rendering; it carries the nav list and the
  top-bar placeholders. Call it, then add your own keys, then render.
* Each screen's data module (``open_composer/cockpit/data/<screen>.py``) is
  expected to export plain dataclasses with no HTML in them, mirroring
  ``open_composer/cockpit/data/health.py``. Routes stay thin: fetch the report,
  merge into ``_base_context``, hand it to a template.
* ``templates/base.html`` exposes one block, ``content``; every screen
  template ``{% extends "base.html" %}`` and fills it.
* CSS conventions are documented at the top of
  ``open_composer/cockpit/static/css/cockpit.css`` (``.responsive-table`` +
  ``data-label``, ``.dot--ok|warn|stale|unknown``, ``.panel``, ``.stat-card``).
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from open_composer.cockpit.data.health import (
    build_data_freshness,
    build_health_report,
    summarize_statuses,
)
from open_composer.cockpit.data.hypotheses import (
    build_hypotheses_report,
    compute_lineage_layout,
    extract_criteria_sections,
    find_card,
    flatten_lineage_for_mobile,
    headline_summary,
    lane_status,
)
from open_composer.cockpit.markdown import render_markdown
from open_composer.cockpit.security import PathTraversalError, safe_repo_path
from open_composer.config import project_root

#: Validated before a card id ever touches the filesystem (T4 brief, "card
#: detail" section) -- matches `open_composer.cockpit.data.hypotheses.CARD_ID_RE`.
_CARD_ID_PATH_RE = re.compile(r"^[HD]-\d{8}-\d{2}$")

_PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = _PACKAGE_DIR / "templates"
STATIC_DIR = _PACKAGE_DIR / "static"

# Every screen the information architecture in plan section 4 calls for.
# (slug, url path, nav label). T4-T8 replace the stub route body for their
# slug; the URL and the nav entry do not need to change when they do.
SCREENS: tuple[tuple[str, str, str], ...] = (
    ("hypotheses", "/", "Hypotheses"),
    ("lineage", "/lineage", "Lineage"),
    ("agents", "/agents", "Agents"),
    ("paper", "/paper", "Paper"),
    ("health", "/health", "Health"),
)


def _topbar_data_freshness(root: Path) -> dict[str, str]:
    """Roll every data-freshness entry up into one badge for the top bar.

    Best-effort: any failure degrades to an "unknown" badge rather than
    breaking the page the badge is decorating -- the health screen itself
    (`/health`) is where a real failure should be visible in detail.
    """
    try:
        entries = build_data_freshness(root)
        status = summarize_statuses(tuple(entry.status for entry in entries))
    except Exception:
        return {"status": "unknown", "label": "unknown"}
    return {"status": status, "label": status}


def _base_context(request: Request, active: str) -> dict[str, Any]:
    root = project_root()
    return {
        "request": request,
        "screens": SCREENS,
        "active_screen": active,
        "topbar_data_freshness": _topbar_data_freshness(root),
        "generated_at": datetime.now(UTC),
    }


def create_app() -> FastAPI:
    app = FastAPI(
        title="Open Composer Cockpit",
        description="Read-only status cockpit. No write routes exist by design.",
    )
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        """Liveness probe: cheap, no filesystem/subprocess work.

        Deliberately does not call `build_health_report` -- that is what
        `/health` is for. This route only proves the process is alive.
        """
        return JSONResponse(
            {"status": "ok", "time": datetime.now(UTC).isoformat(), "pid": os.getpid()}
        )

    @app.get("/health", response_class=HTMLResponse)
    def health_page(request: Request) -> HTMLResponse:
        report = build_health_report(project_root())
        context = _base_context(request, "health")
        context["report"] = report
        return templates.TemplateResponse(request, "health.html", context)

    @app.get("/", response_class=HTMLResponse)
    def index_page(request: Request) -> HTMLResponse:
        """Screen 1: the hypothesis-card board (plan section 4, "假设卡看板").

        Swimlanes come pre-bucketed from `group_cards_by_lane` in lane order;
        this route's only job is to also look up, per card, whichever
        `summary.json` results joined to it by `card_id` (see
        `hypotheses.load_results`'s docstring for why the join key is
        `card_id` and not the card's own prose "产出目录" field) and reduce
        each to one headline string for the row.
        """
        report = build_hypotheses_report(project_root())
        headlines: dict[str, list[str]] = {
            card.id: [headline_summary(facts) for facts in report.results.for_card(card.id)]
            for card in report.cards
        }
        context = _base_context(request, "hypotheses")
        context["report"] = report
        context["headlines"] = headlines
        context["lane_status"] = lane_status
        return templates.TemplateResponse(request, "hypotheses.html", context)

    @app.get("/lineage", response_class=HTMLResponse)
    def lineage_page(request: Request) -> HTMLResponse:
        """Screen 2: research lineage (plan section 4, "研究血统图").

        Two edge kinds, drawn differently on purpose: solid = an explicit
        `上一环：` field (only 1 of 19 cards has one, as of 2026-09-19 -- see
        `hypotheses.build_lineage`'s docstring), dashed = a weaker "this card
        id is mentioned somewhere in that card's body" signal. Desktop gets
        an inline SVG (`compute_lineage_layout`); phone gets the same graph
        flattened into an indented list (`flatten_lineage_for_mobile`) with
        the edge kind shown as a text label instead of a line style, per the
        plan's explicit instruction not to force a force-directed graph onto
        a phone screen.
        """
        report = build_hypotheses_report(project_root())
        graph = report.lineage
        layout = compute_lineage_layout(graph)
        node_status = {node.card_id: lane_status(node.lane) for node in graph.nodes}
        mobile_rows = flatten_lineage_for_mobile(graph)
        context = _base_context(request, "lineage")
        context["graph"] = graph
        context["layout"] = layout
        context["node_status"] = node_status
        context["mobile_rows"] = mobile_rows
        return templates.TemplateResponse(request, "lineage.html", context)

    @app.get("/card/{card_id}", response_class=HTMLResponse)
    def card_detail_page(request: Request, card_id: str) -> HTMLResponse:
        """Card detail: markdown body, matched results, and lineage neighbours.

        `card_id` is validated against `^[HD]-\\d{8}-\\d{2}$` before it is used
        for anything -- including before the one-more `safe_repo_path` check
        on the card's own (already-known-safe, glob-discovered) path, per the
        plan's explicit "validate, and still go through safe_repo_path"
        instruction for this route. Both an invalid id (`/card/nope`) and a
        well-formed but unknown id return 404, never 500.
        """
        if not _CARD_ID_PATH_RE.match(card_id):
            raise HTTPException(status_code=404, detail="not a valid card id")

        root = project_root()
        report = build_hypotheses_report(root)
        card = find_card(report.cards, card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="card not found")
        try:
            safe_repo_path(card.path, root=root)
        except PathTraversalError as exc:
            raise HTTPException(status_code=404, detail="invalid card path") from exc

        card_html = render_markdown(card.body_markdown)
        criteria_sections = [
            (section, render_markdown(section.markdown))
            for section in extract_criteria_sections(card.body_markdown)
        ]
        results = report.results.for_card(card.id)
        neighbours = [
            edge
            for edge in report.lineage.edges
            if edge.source == card.id or edge.target == card.id
        ]

        context = _base_context(request, "hypotheses")
        context["card"] = card
        context["card_html"] = card_html
        context["criteria_sections"] = criteria_sections
        context["results"] = results
        context["headline_summary"] = headline_summary
        context["neighbours"] = neighbours
        context["cards_by_id"] = {c.id: c for c in report.cards}
        context["lane_status"] = lane_status
        return templates.TemplateResponse(request, "card_detail.html", context)

    def _stub_page(slug: str, label: str):
        def _handler(request: Request) -> HTMLResponse:
            context = _base_context(request, slug)
            context["screen_label"] = label
            return templates.TemplateResponse(request, "stub.html", context)

        return _handler

    app.get("/agents", response_class=HTMLResponse)(_stub_page("agents", "Agents"))
    app.get("/paper", response_class=HTMLResponse)(_stub_page("paper", "Paper"))

    return app
