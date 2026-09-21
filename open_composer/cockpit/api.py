"""Read-only JSON mirror of every cockpit HTML screen (Step 18/plan-two-frontends T11).

``open_composer.cockpit.app`` renders each screen server-side with Jinja2;
this module renders the exact same underlying data as JSON, one endpoint per
HTML route, so a static single-page front end (the future ``/v2`` build, and
eventually a native SwiftUI client -- see
``docs/cockpit/plan-two-frontends-2026-09-20.zh.md`` section 2, path C) can
render every screen without a server-side template engine.

Design constraints (see the plan and the T11 brief this module implements):

* **Read-only.** Every route here is a ``GET``; there is no query parameter
  that triggers work beyond a plain read, and this module starts no
  subprocess of its own (the data layer it calls already bounds its own
  subprocess use -- see ``open_composer.cockpit.data.health``/``.agents``).
* **No circular import.** ``open_composer.cockpit.app`` imports this module
  (to call :func:`register_api_routes`), so this module must never import
  ``open_composer.cockpit.app`` back. Where a route needs something
  ``app.py`` also needs (the six top-bar status objects, and the
  ``_layout_connected`` lineage layout function), the shared thing lives
  either here (:data:`CARD_ID_PATH_RE`) or in the data layer
  (``open_composer.cockpit.data.hypotheses._layout_connected``), and both
  ``app.py`` and this module import it from there.
* **Validation matches the HTML route exactly.** Every path parameter this
  module accepts (``card_id``, ``agent_id``, ``strategy``) is checked with
  the identical validator the sibling HTML route in ``app.py`` uses, in the
  identical order, so the two can never diverge on what counts as "not
  found" -- a malformed id and a well-formed-but-unknown id both return 404,
  never 500.
* **The data layer already scrubs secrets** (``open_composer.cockpit.security.
  secret_scrub``, applied inside ``open_composer.cockpit.data.*`` before a
  string ever reaches a dataclass field). :func:`to_jsonable` only changes
  *shape* (dataclass -> dict, ``datetime`` -> ISO-8601 string, ...); it never
  touches text content, so nothing here can un-scrub or re-introduce a
  secret-shaped string. ``tests/test_cockpit_api.py`` still runs every
  response through ``secret_scrub`` as a defense-in-depth check.
"""

from __future__ import annotations

import dataclasses
import math
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from open_composer.cockpit.data.agents import (
    AGENT_ID_RE,
    build_agent_detail,
    load_agents,
    load_heavy_jobs,
)
from open_composer.cockpit.data.health import build_health_report
from open_composer.cockpit.data.hypotheses import (
    _layout_connected,
    build_hypotheses_report,
    extract_criteria_sections,
    find_card,
    flatten_lineage_for_mobile,
    headline_summary,
    lane_status,
)
from open_composer.cockpit.data.paper import (
    AUTH_STATE_LABELS,
    build_paper_report,
    build_strategy_detail,
    compute_equity_chart_layout,
    discover_strategy_names,
)
from open_composer.cockpit.data.quota import build_quota_report, get_default_claude_cache
from open_composer.cockpit.markdown import render_markdown
from open_composer.cockpit.security import PathTraversalError, safe_repo_path
from open_composer.config import project_root

#: Matches `open_composer.cockpit.data.hypotheses.CARD_ID_RE` (an `H-`/`D-`
#: card id) without capture groups -- validated before a card id ever
#: touches the filesystem, by both the HTML `/card/{card_id}` route
#: (`open_composer.cockpit.app`) and `GET /api/hypotheses/{card_id}.json`
#: below, so the two routes can never disagree on what a valid id looks like.
CARD_ID_PATH_RE = re.compile(r"^[HD]-\d{8}-\d{2}$")


def to_jsonable(obj: Any, *, root: Path) -> Any:
    """Recursively convert ``obj`` into something ``json.dumps`` accepts.

    Rules (T11 brief):

    * a dataclass *instance* -> a plain ``dict`` of its own fields, built by
      iterating :func:`dataclasses.fields` and recursing into each value
      (deliberately not ``dataclasses.asdict``, which would recurse on its
      own and bypass every other rule below for nested dataclasses);
    * ``datetime`` -> an ISO-8601 string; a naive ``datetime`` is treated as
      UTC first, so the output always carries an explicit ``+00:00`` (or
      other) offset -- never an offset-less string a client could misread
      as local time;
    * ``date`` (and not ``datetime``, checked first since ``datetime`` is a
      ``date`` subclass) -> its ISO string (``YYYY-MM-DD``);
    * ``Path`` -> a string relative to ``root`` when the path is inside it
      (e.g. a hypothesis card's own repo-relative path), else ``str(path)``
      unchanged (e.g. a session transcript under ``~/.claude/projects``,
      which is real filesystem information, not a secret);
    * ``Enum`` -> ``.value`` (recursed, in case the value itself needs
      converting);
    * ``tuple``/``list``/``set``/``frozenset`` -> a ``list``, each item
      recursed;
    * ``dict`` -> a ``dict`` with every key coerced through ``str()`` (JSON
      object keys are always strings) and every value recursed;
    * ``float`` NaN/±inf -> ``None`` (``json.dumps(..., allow_nan=False)``,
      which `fastapi.responses.JSONResponse` uses, would otherwise raise);
    * ``str``/``int``/``bool``/``None`` -> passed through unchanged;
    * anything else -> ``str(obj)`` (a defensive catch-all; nothing in this
      repo's cockpit data layer is expected to hit this branch today).
    """
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, Enum):
        return to_jsonable(obj.value, root=root)
    if isinstance(obj, datetime):
        aware = obj if obj.tzinfo is not None else obj.replace(tzinfo=UTC)
        return aware.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Path):
        try:
            return str(obj.relative_to(root))
        except ValueError:
            return str(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: to_jsonable(getattr(obj, f.name), root=root) for f in dataclasses.fields(obj)
        }
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_jsonable(item, root=root) for item in obj]
    if isinstance(obj, dict):
        return {str(key): to_jsonable(value, root=root) for key, value in obj.items()}
    return str(obj)


def _json(payload: dict[str, Any]) -> JSONResponse:
    """Every endpoint's response wrapper: JSON, never cached (T11 brief:
    every response carries ``Cache-Control: no-store``, matching the rest of
    this read-only, always-current cockpit)."""
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})


def register_api_routes(app: FastAPI, *, status_context: Callable[[], dict[str, Any]]) -> None:
    """Register every ``GET /api/*.json`` route on ``app``.

    ``status_context`` builds the same six top-bar status objects
    ``open_composer.cockpit.app._base_context`` puts into the HTML top bar
    (``claude``, ``codex``, ``usage_estimate``, ``agents``,
    ``data_freshness``, ``rehearsal``) -- passed in from ``app.py`` rather
    than imported from it, so this module never imports ``app.py`` back (see
    module docstring's "no circular import").
    """

    @app.get("/api/status.json")
    def api_status() -> JSONResponse:
        root = project_root()
        status = status_context()
        payload = {
            "generated_at": to_jsonable(datetime.now(UTC), root=root),
            "claude": to_jsonable(status["claude"], root=root),
            "codex": to_jsonable(status["codex"], root=root),
            "usage_estimate": to_jsonable(status["usage_estimate"], root=root),
            "agents": to_jsonable(status["agents"], root=root),
            "data_freshness": to_jsonable(status["data_freshness"], root=root),
            "rehearsal": to_jsonable(status["rehearsal"], root=root),
        }
        return _json(payload)

    @app.get("/api/hypotheses.json")
    def api_hypotheses() -> JSONResponse:
        """Mirrors `open_composer.cockpit.app.index_page`: every lane, in
        `group_cards_by_lane` order, each card without its (potentially
        large) `body_markdown` but with the same per-card headline list the
        HTML board row shows.
        """
        root = project_root()
        report = build_hypotheses_report(root)
        lanes: list[dict[str, Any]] = []
        for lane, cards in report.lanes.items():
            card_payloads = []
            for card in cards:
                data = to_jsonable(card, root=root)
                data.pop("body_markdown", None)
                data["headlines"] = [
                    headline_summary(facts) for facts in report.results.for_card(card.id)
                ]
                card_payloads.append(data)
            lanes.append({"lane": lane, "status": lane_status(lane), "cards": card_payloads})
        payload = {
            "generated_at": to_jsonable(datetime.now(UTC), root=root),
            "lanes": lanes,
            "warnings": to_jsonable(report.results.warnings, root=root),
        }
        return _json(payload)

    @app.get("/api/hypotheses/{card_id}.json")
    def api_hypothesis_detail(card_id: str) -> JSONResponse:
        """Mirrors `open_composer.cockpit.app.card_detail_page`: full card
        (including `body_markdown`) plus its rendered HTML, criteria
        sections, joined results, and lineage neighbours. Validation is
        identical to the HTML route, in the identical order, so both return
        404 (never 500) for the same bad input.
        """
        if not CARD_ID_PATH_RE.match(card_id):
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

        criteria = []
        for section in extract_criteria_sections(card.body_markdown):
            data = to_jsonable(section, root=root)
            data["html"] = render_markdown(section.markdown)
            criteria.append(data)

        results = []
        for facts in report.results.for_card(card.id):
            data = to_jsonable(facts, root=root)
            data["headline"] = headline_summary(facts)
            results.append(data)

        neighbours = [
            edge
            for edge in report.lineage.edges
            if edge.source == card.id or edge.target == card.id
        ]
        cards_by_id = {c.id: c for c in report.cards}
        neighbour_ids = {edge.source for edge in neighbours} | {edge.target for edge in neighbours}
        neighbour_cards: dict[str, dict[str, Any]] = {}
        for neighbour_id in neighbour_ids:
            neighbour_card = cards_by_id.get(neighbour_id)
            if neighbour_card is None:
                continue  # defensive: build_lineage never emits an edge to an unknown id
            neighbour_cards[neighbour_id] = {
                "id": neighbour_card.id,
                "title": neighbour_card.title,
                "lane": neighbour_card.lane,
                "status": lane_status(neighbour_card.lane),
            }

        payload = {
            "generated_at": to_jsonable(datetime.now(UTC), root=root),
            "card": to_jsonable(card, root=root),
            "body_html": render_markdown(card.body_markdown),
            "criteria": criteria,
            "results": results,
            "neighbours": to_jsonable(neighbours, root=root),
            "neighbour_cards": neighbour_cards,
        }
        return _json(payload)

    @app.get("/api/lineage.json")
    def api_lineage() -> JSONResponse:
        """Mirrors `open_composer.cockpit.app.lineage_page`."""
        root = project_root()
        report = build_hypotheses_report(root)
        graph = report.lineage
        node_status = {node.card_id: lane_status(node.lane) for node in graph.nodes}
        mobile_rows = flatten_lineage_for_mobile(graph)
        linked_ids = {edge.source for edge in graph.edges} | {edge.target for edge in graph.edges}
        layout = _layout_connected(graph, linked_ids)
        isolated = tuple(node for node in graph.nodes if node.card_id not in linked_ids)
        payload = {
            "generated_at": to_jsonable(datetime.now(UTC), root=root),
            "nodes": to_jsonable(graph.nodes, root=root),
            "edges": to_jsonable(graph.edges, root=root),
            "node_status": node_status,
            "layout": to_jsonable(layout, root=root),
            "isolated": to_jsonable(isolated, root=root),
            "mobile_rows": to_jsonable(mobile_rows, root=root),
        }
        return _json(payload)

    @app.get("/api/agents.json")
    def api_agents() -> JSONResponse:
        """Mirrors `open_composer.cockpit.app.agents_index_page`."""
        root = project_root()
        report = load_agents()
        heavy = load_heavy_jobs()
        counts = {
            "running": sum(1 for a in report.agents if a.record.last_status == "running"),
            "idle": sum(1 for a in report.agents if a.record.last_status == "idle"),
            "error": sum(1 for a in report.agents if a.record.last_status == "error"),
            "closed": sum(1 for a in report.agents if a.record.last_status == "closed"),
        }
        payload = {
            "generated_at": to_jsonable(datetime.now(UTC), root=root),
            "counts": counts,
            "agents": to_jsonable(report.agents, root=root),
            "heavy": to_jsonable(heavy, root=root),
        }
        return _json(payload)

    @app.get("/api/agents/{agent_id}.json")
    def api_agent_detail(agent_id: str) -> JSONResponse:
        """Mirrors `open_composer.cockpit.app.agent_detail_page`. Validation
        is identical to the HTML route: `AGENT_ID_RE` first, then
        `build_agent_detail` (which re-validates via `find_agent_record`);
        both a malformed id and a well-formed but unknown one return 404.
        """
        if not AGENT_ID_RE.match(agent_id):
            raise HTTPException(status_code=404, detail="not a valid agent id")
        detail = build_agent_detail(agent_id)
        if detail.record is None:
            raise HTTPException(status_code=404, detail="agent not found")
        root = project_root()
        payload = {
            "generated_at": to_jsonable(datetime.now(UTC), root=root),
            "detail": to_jsonable(detail, root=root),
        }
        return _json(payload)

    @app.get("/api/paper.json")
    def api_paper() -> JSONResponse:
        """Mirrors `open_composer.cockpit.app.paper_index_page`."""
        root = project_root()
        report = build_paper_report(root)
        payload = {
            "generated_at": to_jsonable(datetime.now(UTC), root=root),
            "report": to_jsonable(report, root=root),
            "auth_state_labels": to_jsonable(AUTH_STATE_LABELS, root=root),
        }
        return _json(payload)

    @app.get("/api/paper/{strategy}.json")
    def api_paper_detail(strategy: str) -> JSONResponse:
        """Mirrors `open_composer.cockpit.app.paper_detail_page`. Validation
        is identical to the HTML route: `strategy` must be one of
        `discover_strategy_names`, and its would-be `-latest.json` path must
        still clear `safe_repo_path` as defense in depth.
        """
        root = project_root()
        if strategy not in discover_strategy_names(root):
            raise HTTPException(status_code=404, detail="unknown strategy")
        try:
            safe_repo_path(f"reports/paper/rehearsal/{strategy}-latest.json", root=root)
        except PathTraversalError as exc:
            raise HTTPException(status_code=404, detail="invalid strategy path") from exc

        detail = build_strategy_detail(root, strategy)
        payload = {
            "generated_at": to_jsonable(datetime.now(UTC), root=root),
            "detail": to_jsonable(detail, root=root),
            "chart": to_jsonable(compute_equity_chart_layout(detail.equity_series), root=root),
            "auth_state_labels": to_jsonable(AUTH_STATE_LABELS, root=root),
        }
        return _json(payload)

    @app.get("/api/quota.json")
    def api_quota() -> JSONResponse:
        """Mirrors `open_composer.cockpit.app.quota_page`."""
        root = project_root()
        report = build_quota_report(get_default_claude_cache())
        payload = {
            "generated_at": to_jsonable(datetime.now(UTC), root=root),
            "report": to_jsonable(report, root=root),
        }
        return _json(payload)

    @app.get("/api/health.json")
    def api_health() -> JSONResponse:
        """Mirrors `open_composer.cockpit.app.health_page`."""
        root = project_root()
        report = build_health_report(root)
        payload = {
            "generated_at": to_jsonable(datetime.now(UTC), root=root),
            "report": to_jsonable(report, root=root),
        }
        return _json(payload)


__all__ = ["CARD_ID_PATH_RE", "register_api_routes", "to_jsonable"]
