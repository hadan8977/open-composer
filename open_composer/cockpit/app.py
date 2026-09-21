"""FastAPI application factory for the read-only cockpit (Step 18, T3+T4+T5+T6).

Everything this app can do is a GET (or HEAD) request against files this repo
already owns (crontab, `df`/`free`, hypothesis cards and their lineage (T4),
paper rehearsal artifacts (T5)) or a bounded live/local read of quota state
(T6: the Claude subscription-usage endpoint, this machine's own transcripts,
and Codex's local auth mode) -- and (T7-T8) agent session logs later. There
is intentionally no POST/PUT/PATCH/DELETE route anywhere --
``tests/test_cockpit_app.py`` walks ``app.routes`` and fails loudly if one
ever appears; treat that test as the enforcement mechanism for the whole
design, not a formality.

Authentication is not this app's job: ``oc cockpit serve`` (see
``open_composer/cli.py``) refuses anything but ``127.0.0.1``, and Cloudflare
Access authenticates at the edge (see ``AGENTS.md``).

Interface for T7-T8
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
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from open_composer.cockpit.api import CARD_ID_PATH_RE, register_api_routes
from open_composer.cockpit.data.agents import (
    AGENT_ID_RE,
    agent_state_dot,
    build_agent_detail,
    find_agent_record,
    format_elapsed_seconds,
    format_entry_count,
    format_timeline_time,
    get_default_topbar_agents_cache,
    load_agents,
    load_heavy_jobs,
    stream_agent_timeline,
)
from open_composer.cockpit.data.health import (
    build_data_freshness,
    build_health_report,
    summarize_statuses,
)
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
    build_rehearsal_countdown,
    build_strategy_detail,
    compute_equity_chart_layout,
    discover_strategy_names,
)
from open_composer.cockpit.data.quota import (
    THROTTLE_CALIBRATION_CACHE_TTL_SECONDS,
    USAGE_ESTIMATE_WINDOW_HOURS,
    CodexQuotaState,
    TopbarQuota,
    UsageEstimate,
    build_codex_quota_state,
    build_quota_report,
    format_compact_token_count,
    get_default_claude_cache,
    get_default_throttle_calibration_cache,
    get_default_usage_estimate_cache,
    to_topbar_quota,
    unknown_topbar_quota,
)
from open_composer.cockpit.markdown import render_markdown
from open_composer.cockpit.security import PathTraversalError, safe_repo_path
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
    ("quota", "/quota", "Quota"),
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


def _topbar_rehearsal_countdown(root: Path) -> dict[str, str]:
    """Soonest rehearsal-authorization expiry, for the top bar (T5).

    Best-effort like `_topbar_data_freshness` above: any failure degrades to
    an "unknown" badge rather than breaking whichever screen is showing it --
    `/paper` is where a real failure should be visible in detail.
    """
    try:
        countdown = build_rehearsal_countdown(root)
    except Exception:
        return {"status": "unknown", "label": "unknown"}
    return {"status": countdown.status, "label": countdown.label}


def _topbar_claude_quota(now: datetime) -> TopbarQuota:
    """Claude's compact topbar view (T6). Every failure mode of the quota
    module already degrades to a rendered state on its own (see
    `open_composer.cockpit.data.quota`'s module docstring); this wrapper is
    one more defensive layer, matching `_topbar_data_freshness` above, so an
    integration surprise here still cannot blank a page.
    """
    try:
        report = get_default_claude_cache().get(now=now)
        return to_topbar_quota(report, now=now)
    except Exception:
        return unknown_topbar_quota()


_UNKNOWN_CODEX_QUOTA_STATE = CodexQuotaState(
    auth_mode=None,
    subscription_capable=False,
    available=False,
    label="unknown (state builder failed)",
    windows=(),
    note="",
)


def _topbar_codex_quota() -> CodexQuotaState:
    """Codex's compact topbar view (T6). `build_codex_quota_state` never
    raises by construction (see its docstring), but this wrapper mirrors
    `_topbar_claude_quota` above as one more defensive layer at the
    integration boundary.
    """
    try:
        return build_codex_quota_state()
    except Exception:
        return _UNKNOWN_CODEX_QUOTA_STATE


def _topbar_agents() -> tuple[tuple[str, str], ...]:
    """`(agent_id, last_status)` for every non-closed agent, for the top
    bar's status-dot row (plan section 4: "agent 状态点：每个活着的 agent 一个点").

    Goes through `TopbarAgentsCache` (T10) rather than calling
    `load_agents(enrich=False)` directly: parsing every agent JSON file on
    every screen's `_base_context` (~230 files, ~0.3s on this box) is cheap
    once, not free on every request. See
    `open_composer.cockpit.data.agents.TopbarAgentsCache`'s docstring for
    why this is a short TTL cache rather than an mtime-based parse-skip.
    """
    try:
        report = get_default_topbar_agents_cache().get()
    except Exception:
        return ()
    return tuple(
        (summary.record.id, summary.record.last_status)
        for summary in report.agents
        if summary.record.last_status != "closed"
    )


def _topbar_usage_estimate(now: datetime) -> UsageEstimate:
    """The transcript-based usage estimate's compact topbar view (T6b).

    Second line of the quota topbar slot, distinct from the live gauge
    above it (plan section 3.5: "one line for the live state ..., one line
    for the estimate"). `build_usage_estimate` already degrades to an
    all-zero estimate rather than raising (see its docstring); this wrapper
    is one more defensive layer at the integration boundary, matching
    `_topbar_claude_quota`/`_topbar_codex_quota` above.
    """
    try:
        return get_default_usage_estimate_cache().get(now=now)
    except Exception:
        return UsageEstimate(
            window_start=now,
            window_end=now,
            by_role_model=(),
            subagent_tasks=(),
            fresh_main=0,
            fresh_subagent=0,
            fresh_total=0,
            cache_read_main=0,
            cache_read_subagent=0,
            cache_read_total=0,
            distinct_session_count=0,
            main_files_scanned=0,
            subagent_files_scanned=0,
            subagent_tree_found=False,
            topbar_label=f"fresh {format_compact_token_count(0)} "
            f"(main {format_compact_token_count(0)}, subagents {format_compact_token_count(0)}) "
            f". {USAGE_ESTIMATE_WINDOW_HOURS:.0f}h window",
            generated_at=now,
        )


def _format_short_timestamp(value: datetime | None) -> str:
    """`YYYY-MM-DD HH:MMZ`, no microseconds, no UTC offset punctuation (plan
    section 3.5, `/quota`-specific rule folded in at T6c): every timestamp on
    that page renders through this, registered below as the `short_ts`
    Jinja filter. `None` renders as `unknown` -- a label, not a sentence.
    """
    if value is None:
        return "unknown"
    return value.strftime("%Y-%m-%d %H:%M") + "Z"


def _status_context() -> dict[str, Any]:
    """The six top-bar status objects (plan section 4's persistent top bar).

    Shared verbatim by every HTML screen's :func:`_base_context` and by
    ``GET /api/status.json`` (T11, ``open_composer.cockpit.api``) -- passed to
    :func:`open_composer.cockpit.api.register_api_routes` as its
    ``status_context`` callable -- so the HTML top bar and the JSON status
    endpoint can never independently drift.
    """
    root = project_root()
    now = datetime.now(UTC)
    return {
        "claude": _topbar_claude_quota(now),
        "codex": _topbar_codex_quota(),
        "usage_estimate": _topbar_usage_estimate(now),
        "agents": _topbar_agents(),
        "data_freshness": _topbar_data_freshness(root),
        "rehearsal": _topbar_rehearsal_countdown(root),
    }


def _base_context(request: Request, active: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    status = _status_context()
    return {
        "request": request,
        "screens": SCREENS,
        "active_screen": active,
        "topbar_data_freshness": status["data_freshness"],
        "topbar_rehearsal": status["rehearsal"],
        "topbar_quota_claude": status["claude"],
        "topbar_quota_codex": status["codex"],
        "topbar_usage_estimate": status["usage_estimate"],
        "topbar_agents": status["agents"],
        "generated_at": now,
        "screen_label": next(
            (label for slug, _path, label in SCREENS if slug == active), "Cockpit"
        ),
        # Detail routes render the content block alone when asked for a partial,
        # which is how the inspector (desktop) and the sheet (phone) load them.
        "layout": "partial.html" if request.query_params.get("partial") else "base.html",
    }


def _format_span(seconds: float) -> str:
    whole = int(seconds)
    if whole < 3600:
        return f"{max(1, whole // 60)}m"
    if whole < 86400:
        return f"{whole // 3600}h"
    return f"{whole // 86400}d"


def _format_ago(value: datetime | None, now: datetime | None = None) -> str:
    """Relative time for lists: `now`, `4m ago`, `3h ago`, `12d ago`, `in 2h`."""
    if value is None:
        return "never"
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    moment = now or datetime.now(UTC)
    seconds = (moment - value).total_seconds()
    if seconds < -45:
        return "in " + _format_span(-seconds)
    if seconds < 45:
        return "now"
    return _format_span(seconds) + " ago"


def _format_hms(value: datetime | None) -> str:
    if value is None:
        return "–"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%H:%M:%S")


def _format_money(value: float | None) -> str:
    if value is None:
        return "–"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _format_k(value: int | float | None) -> str:
    if value is None:
        return "–"
    return format_compact_token_count(int(value))


#: Name of the T10 warm thread, for tests that inspect `threading.enumerate()`.
_WARM_THREAD_NAME = "cockpit-quota-warm"
_WARM_THREAD_LOCK = threading.Lock()
_WARM_THREAD_STARTED = False


def _warm_once(now: datetime | None = None) -> None:
    """One refresh pass: the usage estimate, the 429 calibration, and the
    live Claude quota cache (plan item 1's "at startup and then every
    `THROTTLE_CALIBRATION_CACHE_TTL_SECONDS`..."). Each cache already
    degrades any of its own failure modes to a renderable state rather than
    raising (see their own docstrings); the `except Exception` here is one
    more defensive layer so a surprise in one cache can never stop this
    background thread or the caches after it in the same pass.
    """
    moment = now if now is not None else datetime.now(UTC)
    try:
        usage = get_default_usage_estimate_cache().get(now=moment)
    except Exception:
        usage = None
    try:
        get_default_throttle_calibration_cache().get(
            now=moment, current_fresh_total=usage.fresh_total if usage is not None else 0
        )
    except Exception:
        pass
    try:
        get_default_claude_cache().get(now=moment)
    except Exception:
        pass


def _warm_loop() -> None:
    """Background body of the T10 warm thread.

    Does nothing at all -- never even enters the periodic loop -- when this
    box has no Claude transcript tree (`CLAUDE_PROJECTS_DIR` absent): every
    cache this warms degrades cleanly to an empty/unavailable state with
    nothing to scan, so looping forever to no effect would only be a wasted
    daemon thread. This is also what keeps the thread harmless under pytest:
    the suite's autouse fixture (`tests/conftest.py`) already points
    `CLAUDE_PROJECTS_DIR` at a nonexistent path for every test, so even a
    test that constructs the app with the `warm=True` default exits this
    function immediately rather than scanning real data or looping.
    """
    from open_composer.cockpit.data.quota import CLAUDE_PROJECTS_DIR

    if not CLAUDE_PROJECTS_DIR.exists():
        return
    while True:
        _warm_once()
        time.sleep(THROTTLE_CALIBRATION_CACHE_TTL_SECONDS)


def _start_warm_thread() -> threading.Thread | None:
    """Start the process-wide warm thread exactly once (plan item 1: "guard
    against double start").

    `create_app()` can run more than once in the same process (a reload, or
    more than one test module importing it) and every cache this thread
    warms is itself process-wide (`get_default_*_cache()`), so a second
    thread would duplicate work without adding coverage. Returns the
    started `Thread`, or `None` when a thread was already running.
    """
    global _WARM_THREAD_STARTED
    with _WARM_THREAD_LOCK:
        if _WARM_THREAD_STARTED:
            return None
        _WARM_THREAD_STARTED = True
    thread = threading.Thread(target=_warm_loop, name=_WARM_THREAD_NAME, daemon=True)
    thread.start()
    return thread


def create_app(*, warm: bool = True) -> FastAPI:
    """Build the cockpit's FastAPI app.

    `warm`, default `True`: start the T10 background thread that keeps the
    429-calibration/usage-estimate/live-quota caches refreshed off the
    request path (see `_warm_loop`). The real `oc cockpit serve` entry point
    always wants this; tests that care about the thread's absence construct
    the app with `warm=False` explicitly (most tests do not need to, since
    `_warm_loop` is already a no-op without a real `~/.claude/projects`
    tree -- see its docstring).
    """
    app = FastAPI(
        title="Open Composer Cockpit",
        description="Read-only status cockpit. No write routes exist by design.",
    )
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["short_ts"] = _format_short_timestamp
    templates.env.filters["elapsed_s"] = format_elapsed_seconds
    templates.env.filters["hms_ts"] = format_timeline_time
    templates.env.filters["agent_dot"] = agent_state_dot
    templates.env.filters["ago"] = _format_ago
    templates.env.filters["hms"] = _format_hms
    templates.env.filters["money"] = _format_money
    templates.env.filters["k"] = _format_k
    templates.env.filters["count_sep"] = format_entry_count
    if warm:
        _start_warm_thread()
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
        node_status = {node.card_id: lane_status(node.lane) for node in graph.nodes}
        mobile_rows = flatten_lineage_for_mobile(graph)
        linked_ids = {edge.source for edge in graph.edges} | {edge.target for edge in graph.edges}
        layout = _layout_connected(graph, linked_ids)
        context = _base_context(request, "lineage")
        context["linked_ids"] = linked_ids
        context["isolated"] = tuple(node for node in graph.nodes if node.card_id not in linked_ids)
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

    @app.get("/agents", response_class=HTMLResponse)
    def agents_index_page(request: Request) -> HTMLResponse:
        """Screen 3: agent activity (plan section 4, "agent 活动").

        `load_agents()` (default `enrich=True`) resolves and reads a bounded
        transcript tail for every non-closed agent; `load_heavy_jobs()` is
        the separate "当前重活" section for `scripts/run_capped.sh` scopes.
        Both degrade to an empty/`available=False` state on their own rather
        than raising, so this route has nothing extra to catch.
        """
        report = load_agents()
        heavy = load_heavy_jobs()
        counts = {
            "running": sum(1 for a in report.agents if a.record.last_status == "running"),
            "idle": sum(1 for a in report.agents if a.record.last_status == "idle"),
            "error": sum(1 for a in report.agents if a.record.last_status == "error"),
            "closed": sum(1 for a in report.agents if a.record.last_status == "closed"),
        }
        context = _base_context(request, "agents")
        context["report"] = report
        context["heavy"] = heavy
        context["counts"] = counts
        return templates.TemplateResponse(request, "agents.html", context)

    @app.get("/agents/{agent_id}", response_class=HTMLResponse)
    def agent_detail_page(request: Request, agent_id: str) -> HTMLResponse:
        """Agent detail: the full text-and-tool audit timeline for one
        session, plus any nested subagent transcripts.

        `agent_id` is validated against `AGENT_ID_RE` before
        `build_agent_detail` (which re-validates via `find_agent_record`)
        ever touches the filesystem; both a malformed id and a well-formed
        but unknown one return 404, never 500.
        """
        if not AGENT_ID_RE.match(agent_id):
            raise HTTPException(status_code=404, detail="not a valid agent id")
        detail = build_agent_detail(agent_id)
        if detail.record is None:
            raise HTTPException(status_code=404, detail="agent not found")
        context = _base_context(request, "agents")
        context["detail"] = detail
        return templates.TemplateResponse(request, "agent_detail.html", context)

    @app.get("/agents/{agent_id}/stream")
    def agent_stream(agent_id: str) -> StreamingResponse:
        """SSE tail of one agent's transcript, from the current end.

        Existence is checked once, up front, with the same validated
        `find_agent_record` lookup the detail page uses -- an unknown or
        malformed id returns 404 immediately rather than opening a stream
        that would only ever say "not found". `stream_agent_timeline` does
        the actual bounded polling/keep-alive/timeout work; see its
        docstring in `open_composer.cockpit.data.agents`.
        """
        if not AGENT_ID_RE.match(agent_id):
            raise HTTPException(status_code=404, detail="not a valid agent id")
        if find_agent_record(agent_id) is None:
            raise HTTPException(status_code=404, detail="agent not found")
        return StreamingResponse(
            stream_agent_timeline(agent_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/paper", response_class=HTMLResponse)
    def paper_index_page(request: Request) -> HTMLResponse:
        """Screen 4: paper trading (plan section 4, "模拟盘").

        One summary row per strategy, the FreqUI multi-bot rollup pattern the
        plan calls for. "策略" is the organising dimension: this route never
        groups or filters by symbol.
        """
        report = build_paper_report(project_root())
        context = _base_context(request, "paper")
        context["report"] = report
        context["auth_state_labels"] = AUTH_STATE_LABELS
        return templates.TemplateResponse(request, "paper.html", context)

    @app.get("/paper/{strategy}", response_class=HTMLResponse)
    def paper_detail_page(request: Request, strategy: str) -> HTMLResponse:
        """Paper trading detail for one strategy.

        `strategy` is validated against `discover_strategy_names` (built from
        the files actually on disk) *before* any further filesystem access --
        both an unknown name (`/paper/nope`) and a traversal attempt return
        404, never 500. `safe_repo_path` is still run as defense in depth,
        per the plan's explicit "validate, and still go through
        safe_repo_path" instruction (mirrors `card_detail_page` above).
        """
        root = project_root()
        if strategy not in discover_strategy_names(root):
            raise HTTPException(status_code=404, detail="unknown strategy")
        try:
            safe_repo_path(f"reports/paper/rehearsal/{strategy}-latest.json", root=root)
        except PathTraversalError as exc:
            raise HTTPException(status_code=404, detail="invalid strategy path") from exc

        detail = build_strategy_detail(root, strategy)
        context = _base_context(request, "paper")
        context["detail"] = detail
        context["chart"] = compute_equity_chart_layout(detail.equity_series)
        context["auth_state_labels"] = AUTH_STATE_LABELS
        return templates.TemplateResponse(request, "paper_detail.html", context)

    @app.get("/quota", response_class=HTMLResponse)
    def quota_page(request: Request) -> HTMLResponse:
        """Quota detail (T6): all four Claude windows, extra usage, the Codex
        state, the last throttle event from the transcript fallback layer,
        and the cache/breaker state -- the density-over-prose counterpart to
        the compact topbar slots every other screen shows.

        Not one of the five main screens (`SCREENS`), so no nav entry is
        highlighted for it; it is reached from the topbar quota slots.
        """
        report = build_quota_report(get_default_claude_cache())
        context = _base_context(request, "quota")
        context["report"] = report
        return templates.TemplateResponse(request, "quota.html", context)

    # T11: read-only JSON mirror of every HTML screen above (`/api/*.json`),
    # for the future SwiftUI client (plan section 2, path C) and for the B
    # front end's static build below. `status_context=_status_context` is
    # the same six-object builder `_base_context` uses for the HTML top bar,
    # so `GET /api/status.json` cannot independently drift from it.
    register_api_routes(app, status_context=_status_context)

    # T12: the B front end (Figma-derived React, `frontend/cockpit-v2/`) is a
    # one-time `vite build --base=/v2/` static artifact committed under
    # `static/v2/`, not a node runtime this server ever starts -- mounted
    # only when that build actually exists so a checkout without it (or
    # mid-build) still serves every other route unchanged.
    v2_dir = STATIC_DIR / "v2"
    if (v2_dir / "index.html").exists():
        app.mount("/v2", StaticFiles(directory=str(v2_dir), html=True), name="v2")

    return app
