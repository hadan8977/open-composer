"""Tests for the read-only JSON API (Step 18/plan-two-frontends T11).

Mirrors the shape of ``tests/test_cockpit_app.py`` (same ``client`` fixture
pattern, ``warm=False`` so the T10 background thread never starts) and relies
on the same ``tests/conftest.py`` autouse fixture to keep every quota/agent
lookup off the real network and off this box's real credentials/transcripts.

Covers, per the T11 brief:

* every ``/api/*`` route is ``GET``-only;
* every one of the ten endpoints returns 200, JSON, ``Cache-Control:
  no-store``, and the exact documented top-level key set;
* no response ever contains an offset-less ("naive-looking") ISO datetime
  string;
* ``secret_scrub`` is a no-op on every response body (defense in depth: the
  data layer already scrubs, this proves the serializer does not undo that);
* the three detail routes 404 (never 500) on a malformed or unknown id;
* :func:`open_composer.cockpit.api.to_jsonable`'s conversion rules, unit
  tested directly.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from open_composer.cockpit.api import to_jsonable
from open_composer.cockpit.app import create_app
from open_composer.cockpit.security import secret_scrub


@pytest.fixture
def client() -> TestClient:
    # `warm=False`: matches `tests/test_cockpit_app.py`'s fixture -- this
    # suite does not exercise the T10 background warm thread.
    return TestClient(create_app(warm=False))


# --------------------------------------------------------------------------
# Route enumeration: every `/api/*` route is GET-only.
# --------------------------------------------------------------------------


def test_every_api_route_is_get_only() -> None:
    """Stricter than `test_cockpit_app.test_every_route_is_get_or_head_only`
    (which allows `{"GET", "HEAD"}` to accommodate the mounted static app):
    a plain `@app.get(...)` route (which is all `register_api_routes` ever
    declares) has `methods == {"GET"}` exactly, with no implicit `HEAD`. See
    module docstring.
    """
    app = create_app(warm=False)
    api_routes = [r for r in app.routes if getattr(r, "path", "").startswith("/api/")]
    assert len(api_routes) == 10, f"expected 10 /api/ routes, found {len(api_routes)}"
    for route in api_routes:
        methods = getattr(route, "methods", None)
        assert methods == {"GET"}, (
            f"route {route.path!r} has methods {methods!r}, expected exactly {{'GET'}}"
        )


# --------------------------------------------------------------------------
# Shape: the seven "list" endpoints that need no path parameter.
# --------------------------------------------------------------------------

LIST_ENDPOINTS: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "/api/status.json",
        frozenset(
            {
                "generated_at",
                "claude",
                "codex",
                "usage_estimate",
                "agents",
                "data_freshness",
                "rehearsal",
            }
        ),
    ),
    ("/api/hypotheses.json", frozenset({"generated_at", "lanes", "warnings"})),
    (
        "/api/lineage.json",
        frozenset(
            {
                "generated_at",
                "nodes",
                "edges",
                "node_status",
                "layout",
                "isolated",
                "mobile_rows",
            }
        ),
    ),
    ("/api/agents.json", frozenset({"generated_at", "counts", "agents", "heavy"})),
    ("/api/paper.json", frozenset({"generated_at", "report", "auth_state_labels"})),
    ("/api/quota.json", frozenset({"generated_at", "report"})),
    ("/api/health.json", frozenset({"generated_at", "report"})),
)


def _assert_common_response_shape(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("application/json"), content_type
    assert response.headers.get("cache-control") == "no-store"
    return json.loads(response.text)  # raises if not valid JSON


@pytest.mark.parametrize("path,expected_keys", LIST_ENDPOINTS)
def test_list_endpoint_shape(client: TestClient, path: str, expected_keys: frozenset[str]) -> None:
    response = client.get(path)
    data = _assert_common_response_shape(response)
    assert set(data.keys()) == expected_keys


# --------------------------------------------------------------------------
# Shape: the three detail endpoints, driven by whatever id the corresponding
# list endpoint actually returns on this box (skip, don't fail, if empty).
# --------------------------------------------------------------------------


def test_hypothesis_detail_endpoint_shape(client: TestClient) -> None:
    listing = client.get("/api/hypotheses.json").json()
    card_id = next(
        (card["id"] for lane in listing["lanes"] for card in lane["cards"]),
        None,
    )
    if card_id is None:
        pytest.skip("no hypothesis cards on this box")
    response = client.get(f"/api/hypotheses/{card_id}.json")
    data = _assert_common_response_shape(response)
    assert set(data.keys()) == {
        "generated_at",
        "card",
        "body_html",
        "criteria",
        "results",
        "neighbours",
        "neighbour_cards",
    }
    assert data["card"]["id"] == card_id
    assert "body_markdown" in data["card"]  # unlike the list endpoint's card, kept here


def test_agent_detail_endpoint_shape(client: TestClient) -> None:
    listing = client.get("/api/agents.json").json()
    agents = listing["agents"]
    if not agents:
        pytest.skip("no agents on this box")
    agent_id = agents[0]["record"]["id"]
    response = client.get(f"/api/agents/{agent_id}.json")
    data = _assert_common_response_shape(response)
    assert set(data.keys()) == {"generated_at", "detail"}
    assert data["detail"]["record"]["id"] == agent_id


def test_paper_detail_endpoint_shape(client: TestClient) -> None:
    listing = client.get("/api/paper.json").json()
    strategies = listing["report"]["strategies"]
    if not strategies:
        pytest.skip("no paper strategies on this box")
    name = strategies[0]["name"]
    response = client.get(f"/api/paper/{name}.json")
    data = _assert_common_response_shape(response)
    assert set(data.keys()) == {"generated_at", "detail", "chart", "auth_state_labels"}
    assert data["detail"]["name"] == name


# --------------------------------------------------------------------------
# Cross-cutting invariants over every endpoint that returns 200 on this box.
# --------------------------------------------------------------------------

_NAIVE_ISO_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$")


def _find_naive_datetime_strings(obj: Any, path: str = "$") -> list[str]:
    """Recursively collect every JSON path whose string value looks like an
    ISO datetime with no UTC offset and no trailing ``Z`` -- the shape
    :func:`open_composer.cockpit.api.to_jsonable` must never produce.
    """
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            hits.extend(_find_naive_datetime_strings(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            hits.extend(_find_naive_datetime_strings(value, f"{path}[{index}]"))
    elif isinstance(obj, str) and _NAIVE_ISO_DATETIME_RE.match(obj):
        hits.append(f"{path} = {obj!r}")
    return hits


def _all_ok_responses(client: TestClient) -> list[tuple[str, Any]]:
    """Every endpoint that returns 200 on this box: the seven list endpoints
    plus whichever detail endpoints have a real id to hit."""
    responses: list[tuple[str, Any]] = [(path, client.get(path)) for path, _keys in LIST_ENDPOINTS]

    hyp_listing = next(r for p, r in responses if p == "/api/hypotheses.json").json()
    card_id = next(
        (card["id"] for lane in hyp_listing["lanes"] for card in lane["cards"]),
        None,
    )
    if card_id is not None:
        path = f"/api/hypotheses/{card_id}.json"
        responses.append((path, client.get(path)))

    agents_listing = next(r for p, r in responses if p == "/api/agents.json").json()
    if agents_listing["agents"]:
        agent_id = agents_listing["agents"][0]["record"]["id"]
        path = f"/api/agents/{agent_id}.json"
        responses.append((path, client.get(path)))

    paper_listing = next(r for p, r in responses if p == "/api/paper.json").json()
    if paper_listing["report"]["strategies"]:
        name = paper_listing["report"]["strategies"][0]["name"]
        path = f"/api/paper/{name}.json"
        responses.append((path, client.get(path)))

    return responses


def test_no_response_contains_a_naive_iso_datetime_string(client: TestClient) -> None:
    for path, response in _all_ok_responses(client):
        assert response.status_code == 200, (path, response.text)
        hits = _find_naive_datetime_strings(response.json())
        assert not hits, f"{path}: naive-looking datetime string(s): {hits[:5]}"


def test_secret_scrub_is_a_no_op_on_every_response(client: TestClient) -> None:
    for path, response in _all_ok_responses(client):
        assert response.status_code == 200, (path, response.text)
        text = response.text
        assert secret_scrub(text) == text, f"{path}: secret_scrub changed the response body"


# --------------------------------------------------------------------------
# 404, never 500, on bad path parameters.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/hypotheses/nope.json",
        "/api/hypotheses/H-20990101-01.json",
        "/api/agents/not-an-id.json",
        "/api/paper/../../etc.json",
        "/api/paper/nope.json",
    ],
)
def test_bad_path_parameters_return_404_not_500(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404, (path, response.status_code, response.text)


# --------------------------------------------------------------------------
# `to_jsonable` unit tests.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Inner:
    value: int


@dataclass(frozen=True)
class _Outer:
    inner: _Inner
    label: str


class _Color(Enum):
    RED = "red"


def test_to_jsonable_recurses_into_nested_dataclasses(tmp_path: Path) -> None:
    obj = _Outer(inner=_Inner(value=42), label="x")
    assert to_jsonable(obj, root=tmp_path) == {"inner": {"value": 42}, "label": "x"}


def test_to_jsonable_naive_datetime_gets_utc_offset(tmp_path: Path) -> None:
    naive = datetime(2026, 1, 2, 3, 4, 5)
    assert naive.tzinfo is None
    result = to_jsonable(naive, root=tmp_path)
    assert result == "2026-01-02T03:04:05+00:00"


def test_to_jsonable_aware_datetime_keeps_its_own_offset(tmp_path: Path) -> None:
    aware = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert to_jsonable(aware, root=tmp_path) == "2026-01-02T03:04:05+00:00"


def test_to_jsonable_path_inside_root_becomes_relative(tmp_path: Path) -> None:
    inside = tmp_path / "sub" / "file.txt"
    assert to_jsonable(inside, root=tmp_path) == "sub/file.txt"


def test_to_jsonable_path_outside_root_stays_absolute(tmp_path: Path) -> None:
    outside = Path("/definitely/outside/this/tmp_path/file.txt")
    assert to_jsonable(outside, root=tmp_path) == str(outside)


def test_to_jsonable_nan_and_inf_become_none(tmp_path: Path) -> None:
    assert to_jsonable(float("nan"), root=tmp_path) is None
    assert to_jsonable(float("inf"), root=tmp_path) is None
    assert to_jsonable(float("-inf"), root=tmp_path) is None
    assert to_jsonable(1.5, root=tmp_path) == 1.5


def test_to_jsonable_tuple_becomes_list(tmp_path: Path) -> None:
    assert to_jsonable((1, 2, 3), root=tmp_path) == [1, 2, 3]
    assert to_jsonable({1, 2}, root=tmp_path) in ([1, 2], [2, 1])


def test_to_jsonable_enum_becomes_its_value(tmp_path: Path) -> None:
    assert to_jsonable(_Color.RED, root=tmp_path) == "red"


def test_to_jsonable_dict_keys_are_stringified(tmp_path: Path) -> None:
    assert to_jsonable({1: "a", "b": 2}, root=tmp_path) == {"1": "a", "b": 2}


def test_to_jsonable_passthrough_scalars(tmp_path: Path) -> None:
    assert to_jsonable("s", root=tmp_path) == "s"
    assert to_jsonable(7, root=tmp_path) == 7
    assert to_jsonable(True, root=tmp_path) is True
    assert to_jsonable(None, root=tmp_path) is None
