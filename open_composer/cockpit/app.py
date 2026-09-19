"""FastAPI application factory for the read-only cockpit (Step 18, T3).

Everything this app can do is a GET (or HEAD) request against files this repo
already owns: crontab, `df`/`free` today, and (T4-T8) hypothesis cards, paper
rehearsal artifacts, and agent session logs later. There is intentionally no
POST/PUT/PATCH/DELETE route anywhere -- ``tests/test_cockpit_app.py`` walks
``app.routes`` and fails loudly if one ever appears; treat that test as the
enforcement mechanism for the whole design, not a formality.

Authentication is not this app's job: ``oc cockpit serve`` (see
``open_composer/cli.py``) refuses anything but ``127.0.0.1``, and Cloudflare
Access authenticates at the edge (see ``AGENTS.md``).

Interface for T4-T8
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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from open_composer.cockpit.data.health import (
    build_data_freshness,
    build_health_report,
    summarize_statuses,
)
from open_composer.config import project_root

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
        # T4 replaces this body with the hypothesis board. Until then the home
        # route renders the health screen so the app is not blank at "/".
        report = build_health_report(project_root())
        context = _base_context(request, "hypotheses")
        context["report"] = report
        return templates.TemplateResponse(request, "health.html", context)

    def _stub_page(slug: str, label: str):
        def _handler(request: Request) -> HTMLResponse:
            context = _base_context(request, slug)
            context["screen_label"] = label
            return templates.TemplateResponse(request, "stub.html", context)

        return _handler

    app.get("/lineage", response_class=HTMLResponse)(_stub_page("lineage", "Lineage"))
    app.get("/agents", response_class=HTMLResponse)(_stub_page("agents", "Agents"))
    app.get("/paper", response_class=HTMLResponse)(_stub_page("paper", "Paper"))

    return app
