"""Pure(ish) data for the cockpit's persistent quota top bar and `/quota` (Step 18, T6).

Mirrors ``open_composer.cockpit.data.health``/``paper``/``hypotheses`` in one
respect and deliberately breaks from them in another. Like those modules:
nothing here renders HTML, ``open_composer.cockpit.app`` is the only thing
that imports both this module and the template engine, and every public
function degrades to a recorded, renderable state rather than raising. Unlike
those modules: this one is *not* a pure-function/frozen-dataclass reader of
files that already exist on disk. It calls a live, undocumented network
endpoint, so it needs a small amount of deliberate, encapsulated mutable
state -- :class:`ClaudeQuotaCache` -- to hold the 60-second cache, the
circuit breaker, and the burn-rate ring buffer across requests in this
long-running process. That state lives in exactly one place; every other
function in this module remains a pure transform.

Three data sources, three honesty levels
-----------------------------------------
1. **Claude, live**: ``GET https://api.anthropic.com/api/oauth/usage``. This
   endpoint is undocumented and reverse-engineered (see
   ``reports/research/intel/I-20260919-02-subscription-quota-readout.md``):
   it can change shape or disappear without notice, and an incorrect
   ``User-Agent`` gets a caller hard-throttled. Every failure mode --
   timeout, HTTP 4xx/5xx, no credentials, an open circuit breaker, a
   malformed response body -- degrades to an ``unavailable`` snapshot with a
   short, fixed reason string. None of them raise.
2. **Claude, fallback**: the most recent ``quotaLimits`` object recorded in
   this machine's own ``~/.claude/projects/*/*.jsonl`` transcripts. This only
   exists at the moment a real request got a 429, so it is reported as an
   *event* (``ThrottleEvent``) -- "last throttled at X, resets at Y" -- never
   as a live gauge. It is read only for the ``/quota`` detail page, not the
   topbar, because scanning transcript tails on every page render across all
   five screens would be wasted I/O for a value the topbar does not show.
3. **Codex**: this box's ``~/.codex/auth.json`` has ``auth_mode: "apikey"``
   (a local proxy in front of third-party models), which has no subscription
   window to read at all -- that is reported as a first-class state
   (``"api key billing -- no subscription quota"``), not an error. The
   ``account/rateLimits/read`` JSON-RPC shape (per ``codex app-server
   generate-json-schema``) is implemented and unit-tested
   (:func:`parse_codex_rate_limits_response`) but is reserved, dead code on
   this box: :func:`build_codex_quota_state` only ever calls a supplied
   :class:`CodexRateLimitsClient`, and no code in this repo ever constructs
   one. If the login here ever becomes a ChatGPT subscription, wiring in a
   real client activates the path; until then it can only report "not
   wired", never crash. This module never spawns a ``codex`` subprocess.

Credential handling
--------------------
The Claude OAuth access token lives in ``~/.claude/.credentials.json``, which
is outside the repository, so ``open_composer.cockpit.security.safe_repo_path``
(which validates paths *inside* the repo) does not apply. Instead this module
uses one explicit, hardcoded constant, :data:`CLAUDE_CREDENTIALS_PATH` --
never a caller-supplied or request-derived path. :func:`_load_oauth_token` is
the only function in this module that ever holds the token in a variable; the
instant its one caller (``ClaudeQuotaCache._refresh``) has copied it into an
``Authorization`` header value for one outgoing request, that local binding
is deleted. The token is never stored on a dataclass field, never logged,
and never returned by any other function. A failing HTTP response's body can
itself echo request headers back (a real misbehavior class for reverse
gateways) -- any diagnostic text this module keeps from an error response
body is passed through ``secret_scrub`` before it is ever stored, so a
token-shaped string in that body cannot reach a rendered page either.

Cache, breaker, timeout
-------------------------
* A 5-second request timeout (:data:`DEFAULT_TIMEOUT_SECONDS`).
* A 60-second in-memory cache (:data:`CACHE_TTL_SECONDS`) so concurrent or
  rapid page renders never trigger more than one live call per minute.
* A circuit breaker: after :data:`BREAKER_FAILURE_THRESHOLD` (3) consecutive
  failures, no further attempts are made for
  :data:`BREAKER_COOLDOWN_SECONDS` (10 minutes); the next call after that
  window closes the breaker and tries again.

Burn rate
----------
:class:`ClaudeQuotaCache` keeps an in-memory-only ring buffer
(:data:`_MAX_BURN_SAMPLES`) of successful five-hour-window readings -- never
written to disk, matching the cockpit's read-only design. A time-to-100%
projection is computed only when there are at least two samples spanning at
least five minutes (:data:`_MIN_BURN_SPAN_SECONDS`) *and* utilization is
rising between the oldest and newest sample; a single sample is never
extrapolated from, and every other case renders the fixed label
``"projection: not enough samples"``.
"""

from __future__ import annotations

import json
import shutil
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Literal, Protocol

import httpx

from open_composer.cockpit.data.health import Status
from open_composer.cockpit.security import secret_scrub

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

#: Undocumented, reverse-engineered (see module docstring). Referenced as a
#: bare module global everywhere it is used (never baked into a function's
#: default parameter value) so a test can monkeypatch it in place.
CLAUDE_USAGE_URL: Final[str] = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_OAUTH_BETA_HEADER: Final[str] = "oauth-2025-04-20"

#: The *only* allowlisted credential path this module ever reads. Outside the
#: repo root, so `security.safe_repo_path` does not apply; hardcoded rather
#: than accepting any caller/request-supplied path, by design.
CLAUDE_CREDENTIALS_PATH: Final[Path] = Path.home() / ".claude" / ".credentials.json"
CODEX_AUTH_PATH: Final[Path] = Path.home() / ".codex" / "auth.json"
CLAUDE_PROJECTS_DIR: Final[Path] = Path.home() / ".claude" / "projects"

DEFAULT_TIMEOUT_SECONDS: Final[float] = 5.0
CACHE_TTL_SECONDS: Final[float] = 60.0
BREAKER_FAILURE_THRESHOLD: Final[int] = 3
BREAKER_COOLDOWN_SECONDS: Final[float] = 600.0  # 10 minutes

#: At most one successful sample per `CACHE_TTL_SECONDS`, so this covers a
#: little over 5 hours of history -- exactly the window the projection needs.
_MAX_BURN_SAMPLES: Final[int] = 300
_MIN_BURN_SPAN_SECONDS: Final[float] = 5 * 60.0

#: Version string installed on this box on 2026-09-20 (`claude` 2.1.273, per
#: `reports/research/intel/I-20260919-02-...`); used only if local discovery
#: (`discover_claude_cli_version`) cannot read the real installed version, so
#: the User-Agent still looks like a plausible current release rather than a
#: placeholder that risks the "wrong UA gets hard-throttled" failure mode.
_FALLBACK_CLAUDE_CLI_VERSION: Final[str] = "2.1.273"

_TRANSCRIPT_TAIL_BYTES: Final[int] = 200_000
_MAX_TRANSCRIPT_FILES_SCANNED: Final[int] = 20

_CODEX_LABEL_APIKEY: Final[str] = "api key billing -- no subscription quota"
_NOT_ENOUGH_SAMPLES_LABEL: Final[str] = "projection: not enough samples"


# --------------------------------------------------------------------------
# Small shared parsing helpers (mirrors `paper._parse_dt`/`_num`)
# --------------------------------------------------------------------------


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_epoch_seconds(value: Any) -> datetime | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _format_duration_short(seconds: float) -> str:
    if seconds <= 0:
        return "due"
    hours = seconds / 3600.0
    if hours >= 1:
        return f"{hours:.1f}h"
    minutes = seconds / 60.0
    if minutes >= 1:
        return f"{minutes:.0f}m"
    return f"{seconds:.0f}s"


# --------------------------------------------------------------------------
# CLI version discovery (local file reads only -- no subprocess spawn)
# --------------------------------------------------------------------------


def _resolve_claude_binary(which_fn: Callable[[str], str | None]) -> Path | None:
    which = which_fn("claude")
    if not which:
        return None
    try:
        return Path(which).resolve()
    except OSError:
        return None


def _read_version_from_binary_path(binary_path: Path) -> str | None:
    """Walk up from an installed ``claude`` binary looking for the npm
    package's own ``package.json``.

    On this box the resolved binary is
    ``.../node_modules/@anthropic-ai/claude-code/bin/claude.exe``, so
    ``package.json`` is two directories up; a third level is checked for a
    slightly different install layout. This is a plain local file read, not
    a ``claude --version`` subprocess -- spawning a whole Node process just
    to build a User-Agent string is wasteful on this 3.9GB box and would
    have to happen at most once every `CACHE_TTL_SECONDS` regardless, so the
    subprocess path was rejected in favor of this.
    """
    for parent in (
        binary_path.parent,
        binary_path.parent.parent,
        binary_path.parent.parent.parent,
    ):
        package_json = parent / "package.json"
        if not package_json.is_file():
            continue
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("name") != "@anthropic-ai/claude-code":
            continue
        version = data.get("version")
        if isinstance(version, str) and version:
            return version
    return None


def discover_claude_cli_version(*, which_fn: Callable[[str], str | None] = shutil.which) -> str:
    """The installed Claude Code CLI version, or `_FALLBACK_CLAUDE_CLI_VERSION`.

    `which_fn` is injectable so a test can simulate "claude is not on PATH"
    without touching the real environment.
    """
    binary = _resolve_claude_binary(which_fn)
    if binary is None:
        return _FALLBACK_CLAUDE_CLI_VERSION
    return _read_version_from_binary_path(binary) or _FALLBACK_CLAUDE_CLI_VERSION


# --------------------------------------------------------------------------
# Credential loading -- see module docstring's "Credential handling" section
# --------------------------------------------------------------------------


def _load_oauth_token(path: Path) -> str | None:
    """Read the OAuth access token from `path`, or ``None``.

    The only function in this module that ever holds the token in a local
    variable. Its one caller uses the return value immediately to build a
    single `Authorization` header and then deletes its own local copy; the
    token is never placed on a dataclass, logged, or returned by any other
    function in this module.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    oauth = data.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return None
    token = oauth.get("accessToken")
    return token if isinstance(token, str) and token else None


# --------------------------------------------------------------------------
# Claude usage payload parsing
# --------------------------------------------------------------------------

#: (payload key, display label). Order is the display order everywhere.
_WINDOW_SPECS: Final[tuple[tuple[str, str], ...]] = (
    ("five_hour", "5h"),
    ("seven_day", "7d"),
    ("seven_day_opus", "7d opus"),
    ("seven_day_sonnet", "7d sonnet"),
)


@dataclass(frozen=True)
class ClaudeWindow:
    key: str
    label: str
    percent_used: float | None
    resets_at: datetime | None
    status: Status


@dataclass(frozen=True)
class ClaudeExtraUsage:
    """``extra_usage`` from the live payload, kept generic.

    The endpoint is undocumented and this sub-object's exact shape was not
    independently confirmed (see the intel brief) -- rather than guess at
    field names and silently drop unrecognized ones, every key is kept as a
    scrubbed, truncated string for display, capped so a surprising payload
    cannot inflate memory or the rendered page.
    """

    present: bool
    summary: dict[str, str]


@dataclass(frozen=True)
class ClaudeQuotaSnapshot:
    """What is known about Claude subscription usage right now.

    ``available=False`` covers every failure mode named in the T6 brief:
    ``unavailable_reason`` is one of ``"timeout"``, ``"http 4xx/5xx"``,
    ``"no credentials"``, ``"breaker open"``, plus two this module adds for
    completeness (``"network error"`` for a connection failure that is not a
    timeout, ``"invalid response"`` for a response that parses as JSON but
    not into the expected shape). ``diagnostic`` is only ever populated for
    an HTTP error, and only after `secret_scrub` -- see module docstring.
    """

    fetched_at: datetime
    available: bool
    windows: tuple[ClaudeWindow, ...]
    extra_usage: ClaudeExtraUsage | None
    unavailable_reason: str | None
    diagnostic: str | None
    http_status: int | None = None


# ok/warn/stale thresholds mirror `health.build_disk_status`/`build_memory_status`
# (80% warn, 92% critical) -- the same shared traffic-light vocabulary and the
# same "state the threshold at its call site" convention as the rest of the
# cockpit's data layer.
def _classify_percent(percent: float | None) -> Status:
    if percent is None:
        return "unknown"
    if percent >= 92:
        return "stale"
    if percent >= 80:
        return "warn"
    return "ok"


def _parse_window(raw: Any, key: str, label: str) -> ClaudeWindow:
    if not isinstance(raw, dict):
        return ClaudeWindow(
            key=key, label=label, percent_used=None, resets_at=None, status="unknown"
        )
    utilization = raw.get("utilization")
    percent: float | None = None
    if isinstance(utilization, (int, float)) and not isinstance(utilization, bool):
        percent = max(0.0, float(utilization) * 100.0)
    resets_at = _parse_epoch_seconds(raw.get("resets_at"))
    return ClaudeWindow(
        key=key,
        label=label,
        percent_used=percent,
        resets_at=resets_at,
        status=_classify_percent(percent),
    )


_MAX_EXTRA_USAGE_FIELDS: Final[int] = 10
_MAX_EXTRA_USAGE_VALUE_CHARS: Final[int] = 120


def _parse_extra_usage(raw: Any) -> ClaudeExtraUsage | None:
    if not isinstance(raw, dict):
        return None
    summary: dict[str, str] = {}
    for key in sorted(raw)[:_MAX_EXTRA_USAGE_FIELDS]:
        scrubbed_key = secret_scrub(str(key))
        scrubbed_value = secret_scrub(str(raw[key]))[:_MAX_EXTRA_USAGE_VALUE_CHARS]
        summary[scrubbed_key] = scrubbed_value
    return ClaudeExtraUsage(present=True, summary=summary)


def _parse_usage_payload(payload: Any, *, now: datetime) -> ClaudeQuotaSnapshot:
    if not isinstance(payload, dict):
        raise ValueError("usage payload is not a JSON object")
    windows = tuple(_parse_window(payload.get(key), key, label) for key, label in _WINDOW_SPECS)
    return ClaudeQuotaSnapshot(
        fetched_at=now,
        available=True,
        windows=windows,
        extra_usage=_parse_extra_usage(payload.get("extra_usage")),
        unavailable_reason=None,
        diagnostic=None,
        http_status=200,
    )


def _unavailable_snapshot(
    moment: datetime, reason: str, *, diagnostic: str | None = None, http_status: int | None = None
) -> ClaudeQuotaSnapshot:
    return ClaudeQuotaSnapshot(
        fetched_at=moment,
        available=False,
        windows=(),
        extra_usage=None,
        unavailable_reason=reason,
        diagnostic=diagnostic,
        http_status=http_status,
    )


# --------------------------------------------------------------------------
# Burn rate (in-memory only -- see module docstring)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BurnRateSample:
    at: datetime
    five_hour_percent: float


@dataclass(frozen=True)
class BurnRateProjection:
    available: bool
    eta: datetime | None
    rate_percent_per_hour: float | None
    label: str  # fully composed for direct template interpolation


def compute_burn_rate_projection(
    samples: Sequence[BurnRateSample], *, now: datetime
) -> BurnRateProjection:
    """Time-to-100% for the 5-hour window, or the fixed "not enough samples" label.

    Requires at least two samples spanning at least `_MIN_BURN_SPAN_SECONDS`
    with utilization rising between the oldest and the newest -- a single
    sample is never extrapolated from, and a flat or falling trend (e.g.
    right after the window reset) never projects a fake ETA.
    """
    not_enough = BurnRateProjection(
        available=False, eta=None, rate_percent_per_hour=None, label=_NOT_ENOUGH_SAMPLES_LABEL
    )
    if len(samples) < 2:
        return not_enough
    first, last = samples[0], samples[-1]
    span_seconds = (last.at - first.at).total_seconds()
    if span_seconds < _MIN_BURN_SPAN_SECONDS:
        return not_enough
    delta_percent = last.five_hour_percent - first.five_hour_percent
    if delta_percent <= 0:
        return not_enough
    rate_per_second = delta_percent / span_seconds
    rate_per_hour = rate_per_second * 3600.0
    remaining_percent = 100.0 - last.five_hour_percent
    if remaining_percent <= 0:
        return BurnRateProjection(
            available=True, eta=now, rate_percent_per_hour=rate_per_hour, label="projection: due"
        )
    eta = last.at + timedelta(seconds=remaining_percent / rate_per_second)
    eta_label = _format_duration_short((eta - now).total_seconds())
    return BurnRateProjection(
        available=True,
        eta=eta,
        rate_percent_per_hour=rate_per_hour,
        label=f"projection: eta {eta_label}",
    )


# --------------------------------------------------------------------------
# Cache + circuit breaker + live fetch
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaudeQuotaReport:
    """A cache-aware view of Claude usage, for the topbar and `/quota`."""

    snapshot: ClaudeQuotaSnapshot
    served_from_cache: bool
    cache_age_seconds: float
    breaker_open: bool
    breaker_open_until: datetime | None
    consecutive_failures: int
    projection: BurnRateProjection


def _build_http_client() -> httpx.Client:
    """The real network client used when a caller does not inject one.

    Its own function purely so a test can monkeypatch it to return an
    `httpx.MockTransport`-backed client and exercise the full
    `ClaudeQuotaCache` -> FastAPI route pipeline without ever opening a
    socket (see `tests/test_cockpit_quota.py`).
    """
    return httpx.Client()


class ClaudeQuotaCache:
    """Process-wide cache + circuit breaker + burn-rate ring buffer.

    One instance is shared by every request in a running cockpit process
    (`get_default_claude_cache`); tests construct their own instance so
    state never leaks between them. See the module docstring's "Cache,
    breaker, timeout" and "Burn rate" sections for the exact policy; this
    class is the one place in the module that holds mutable state.
    """

    def __init__(self) -> None:
        self._snapshot: ClaudeQuotaSnapshot | None = None
        self._snapshot_at: datetime | None = None
        self._consecutive_failures = 0
        self._breaker_open_until: datetime | None = None
        self._samples: deque[BurnRateSample] = deque(maxlen=_MAX_BURN_SAMPLES)

    def get(
        self,
        *,
        now: datetime | None = None,
        credentials_path: Path | None = None,
        client: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> ClaudeQuotaReport:
        moment = now or datetime.now(UTC)
        if self._snapshot is not None and self._snapshot_at is not None:
            age = (moment - self._snapshot_at).total_seconds()
            if 0 <= age < CACHE_TTL_SECONDS:
                return self._make_report(moment, served_from_cache=True, cache_age=age)

        snapshot = self._refresh(
            moment, credentials_path=credentials_path, client=client, timeout=timeout
        )
        self._snapshot = snapshot
        self._snapshot_at = moment
        if snapshot.available:
            self._record_sample(moment, snapshot)
        return self._make_report(moment, served_from_cache=False, cache_age=0.0)

    def _refresh(
        self,
        moment: datetime,
        *,
        credentials_path: Path | None,
        client: httpx.Client | None,
        timeout: float,
    ) -> ClaudeQuotaSnapshot:
        if self._breaker_open_until is not None:
            if moment < self._breaker_open_until:
                return _unavailable_snapshot(moment, "breaker open")
            # Cooldown elapsed: close the breaker and allow exactly one fresh attempt.
            self._breaker_open_until = None
            self._consecutive_failures = 0

        path = credentials_path if credentials_path is not None else CLAUDE_CREDENTIALS_PATH
        token = _load_oauth_token(path)
        if token is None:
            return _unavailable_snapshot(moment, "no credentials")

        version = discover_claude_cli_version()
        headers = {
            "Authorization": f"Bearer {token}",
            "anthropic-beta": CLAUDE_OAUTH_BETA_HEADER,
            "User-Agent": f"claude-code/{version}",
        }
        del token  # must not survive past building this one header value

        owns_client = client is None
        http_client = client if client is not None else _build_http_client()
        try:
            try:
                response = http_client.get(CLAUDE_USAGE_URL, headers=headers, timeout=timeout)
            except httpx.TimeoutException:
                self._record_failure(moment)
                return _unavailable_snapshot(moment, "timeout")
            except httpx.HTTPError:
                self._record_failure(moment)
                return _unavailable_snapshot(moment, "network error")
        finally:
            if owns_client:
                http_client.close()

        if response.status_code >= 400:
            self._record_failure(moment)
            diagnostic = secret_scrub(response.text[:500]) if response.text else None
            return _unavailable_snapshot(
                moment, "http 4xx/5xx", diagnostic=diagnostic, http_status=response.status_code
            )

        try:
            snapshot = _parse_usage_payload(response.json(), now=moment)
        except Exception:
            # Defensive: this endpoint is undocumented and can change shape
            # without notice (module docstring) -- a parse surprise must
            # degrade this one snapshot, not crash the page.
            self._record_failure(moment)
            return _unavailable_snapshot(moment, "invalid response")

        self._consecutive_failures = 0
        self._breaker_open_until = None
        return snapshot

    def _record_failure(self, moment: datetime) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= BREAKER_FAILURE_THRESHOLD:
            self._breaker_open_until = moment + timedelta(seconds=BREAKER_COOLDOWN_SECONDS)

    def _record_sample(self, moment: datetime, snapshot: ClaudeQuotaSnapshot) -> None:
        five_hour = next((w for w in snapshot.windows if w.key == "five_hour"), None)
        if five_hour is None or five_hour.percent_used is None:
            return
        self._samples.append(BurnRateSample(at=moment, five_hour_percent=five_hour.percent_used))

    def _make_report(
        self, moment: datetime, *, served_from_cache: bool, cache_age: float
    ) -> ClaudeQuotaReport:
        assert self._snapshot is not None  # get() always refreshes before this is called
        breaker_open = self._breaker_open_until is not None and moment < self._breaker_open_until
        return ClaudeQuotaReport(
            snapshot=self._snapshot,
            served_from_cache=served_from_cache,
            cache_age_seconds=cache_age,
            breaker_open=breaker_open,
            breaker_open_until=self._breaker_open_until,
            consecutive_failures=self._consecutive_failures,
            projection=compute_burn_rate_projection(tuple(self._samples), now=moment),
        )


_DEFAULT_CLAUDE_QUOTA_CACHE = ClaudeQuotaCache()


def get_default_claude_cache() -> ClaudeQuotaCache:
    """The process-wide cache `open_composer.cockpit.app` shares across requests.

    A function (not a bare module attribute reference from callers) so a
    test can `monkeypatch.setattr("open_composer.cockpit.app.get_default_claude_cache", ...)`
    and get a fresh, isolated cache instead of the one long-lived instance a
    real server keeps for its entire run.
    """
    return _DEFAULT_CLAUDE_QUOTA_CACHE


# --------------------------------------------------------------------------
# Claude fallback: last `quotaLimits` event from local transcripts
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ThrottleEvent:
    """The most recent `quotaLimits` object seen in a local transcript.

    ``kind`` is always `"event"`, carried on the dataclass so a template
    cannot accidentally treat this as a live gauge -- it is only ever
    written the moment a real request got a 429 (see module docstring).
    """

    kind: Literal["event"]
    at: datetime | None
    rate_limit_type: str | None
    status: str | None
    resets_at: datetime | None
    overage_status: str | None
    source_path: str


def _last_quota_event_in_file(path: Path) -> ThrottleEvent | None:
    """Bounded tail-scan of one transcript file for its last `quotaLimits` line.

    Reads only the last `_TRANSCRIPT_TAIL_BYTES` (a `seek()` from the end,
    never the whole file), mirroring `health._read_log_tail`'s bounded-tail
    pattern -- a months-old, multi-hundred-MB transcript file costs at most
    this bound to inspect, never its full size.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - _TRANSCRIPT_TAIL_BYTES))
            chunk = handle.read()
    except OSError:
        return None
    lines = chunk.decode("utf-8", errors="replace").split("\n")
    if size > _TRANSCRIPT_TAIL_BYTES:
        lines = lines[1:]  # drop a possibly-truncated first line

    for line in reversed(lines):
        stripped = line.strip()
        if not stripped or "quotaLimits" not in stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        quota_obj = obj.get("quotaLimits")
        if not isinstance(quota_obj, dict):
            continue
        return ThrottleEvent(
            kind="event",
            at=_parse_iso(obj.get("timestamp")),
            rate_limit_type=(
                quota_obj.get("rateLimitType")
                if isinstance(quota_obj.get("rateLimitType"), str)
                else None
            ),
            status=quota_obj.get("status") if isinstance(quota_obj.get("status"), str) else None,
            resets_at=_parse_epoch_seconds(quota_obj.get("resetsAt")),
            overage_status=(
                quota_obj.get("overageStatus")
                if isinstance(quota_obj.get("overageStatus"), str)
                else None
            ),
            source_path=secret_scrub(str(path)),
        )
    return None


def find_last_throttle_event(
    root: Path | None = None, *, max_files: int = _MAX_TRANSCRIPT_FILES_SCANNED
) -> ThrottleEvent | None:
    """The most recent throttle event across this machine's Claude transcripts.

    Only the `max_files` most-recently-modified transcript files are
    scanned, most recent first, stopping at the first hit -- a real
    `quotaLimits` event only appears when a request was actually rejected,
    so it may not be in the single newest file, but files are append-only in
    time order so the newest file *containing* a hit is a good proxy for the
    globally most recent one without having to open every transcript this
    machine has ever written.
    """
    base = root if root is not None else CLAUDE_PROJECTS_DIR
    if not base.is_dir():
        return None
    try:
        candidates = sorted(
            (p for p in base.glob("*/*.jsonl") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    for path in candidates[:max_files]:
        event = _last_quota_event_in_file(path)
        if event is not None:
            return event
    return None


# --------------------------------------------------------------------------
# Codex -- see module docstring's "three data sources" section 3
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CodexRateLimitWindow:
    """One window of `account/rateLimits/read`'s `GetAccountRateLimitsResponse`."""

    limit_id: str  # "primary" | "secondary"
    used_percent: int | None
    resets_at: datetime | None
    window_duration_mins: int | None


def parse_codex_rate_limits_response(payload: Any) -> tuple[CodexRateLimitWindow, ...]:
    """Pure parser for the JSON-RPC `account/rateLimits/read` response shape.

    Schema is per `codex app-server generate-json-schema --experimental`
    (camelCase; `usedPercent` required, `resetsAt`/`windowDurationMins`
    nullable) -- see the intel brief. Not called by any production code path
    on this box today (`build_codex_quota_state` only calls a supplied
    `CodexRateLimitsClient`, and none is ever constructed here); kept as a
    pure, directly testable function so the interface is ready without this
    module ever spawning a `codex` subprocess.
    """
    if not isinstance(payload, dict):
        return ()
    rate_limits = payload.get("rateLimits")
    if not isinstance(rate_limits, dict):
        return ()
    windows: list[CodexRateLimitWindow] = []
    for limit_id in ("primary", "secondary"):
        raw = rate_limits.get(limit_id)
        if not isinstance(raw, dict):
            continue
        used = raw.get("usedPercent")
        duration = raw.get("windowDurationMins")
        windows.append(
            CodexRateLimitWindow(
                limit_id=limit_id,
                used_percent=used if isinstance(used, int) and not isinstance(used, bool) else None,
                resets_at=_parse_epoch_seconds(raw.get("resetsAt")),
                window_duration_mins=(
                    duration
                    if isinstance(duration, int) and not isinstance(duration, bool)
                    else None
                ),
            )
        )
    return tuple(windows)


class CodexRateLimitsClient(Protocol):
    """The seam a real `codex app-server` JSON-RPC client would implement.

    Never implemented or instantiated by production code in this repo (see
    module docstring) -- this is the reserved interface, not a live
    transport.
    """

    def read_rate_limits(self) -> Any:
        """Return the raw `GetAccountRateLimitsResponse` payload (a dict)."""
        ...


@dataclass(frozen=True)
class CodexQuotaState:
    auth_mode: str | None
    subscription_capable: bool
    available: bool
    label: str
    windows: tuple[CodexRateLimitWindow, ...]
    note: str


def _read_codex_auth_mode(path: Path) -> str | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    mode = data.get("auth_mode")
    return mode if isinstance(mode, str) else None


def build_codex_quota_state(
    *, auth_path: Path | None = None, rpc_client: CodexRateLimitsClient | None = None
) -> CodexQuotaState:
    """Codex's quota state: a first-class "api key billing" state today, a
    reserved (dead) subscription read for tomorrow.

    `rpc_client` is never supplied by `open_composer.cockpit.app` -- this
    function never spawns a `codex` subprocess or opens a socket on its own.
    If `auth_mode` is ever something other than `"apikey"` on this box *and*
    a caller supplies a real client, the live path activates automatically;
    until then it reports "not wired" rather than attempting anything.
    """
    path = auth_path if auth_path is not None else CODEX_AUTH_PATH
    auth_mode = _read_codex_auth_mode(path)

    if auth_mode is None:
        return CodexQuotaState(
            auth_mode=None,
            subscription_capable=False,
            available=False,
            label="unknown (no readable auth.json)",
            windows=(),
            note=f"{path}: not found or not parseable",
        )

    if auth_mode == "apikey":
        return CodexQuotaState(
            auth_mode="apikey",
            subscription_capable=False,
            available=False,
            label=_CODEX_LABEL_APIKEY,
            windows=(),
            note=(
                "auth_mode=apikey routes through a local proxy; "
                "there is no subscription window to read"
            ),
        )

    if rpc_client is None:
        return CodexQuotaState(
            auth_mode=auth_mode,
            subscription_capable=True,
            available=False,
            label="subscription login, rate-limit read not wired",
            windows=(),
            note=(
                "account/rateLimits/read requires a running codex app-server client; none supplied"
            ),
        )

    try:
        windows = parse_codex_rate_limits_response(rpc_client.read_rate_limits())
    except Exception as exc:  # defensive: a client failure must not crash the page
        return CodexQuotaState(
            auth_mode=auth_mode,
            subscription_capable=True,
            available=False,
            label="subscription quota read failed",
            windows=(),
            note=secret_scrub(str(exc)),
        )
    return CodexQuotaState(
        auth_mode=auth_mode,
        subscription_capable=True,
        available=True,
        label="subscription quota",
        windows=windows,
        note="live via codex app-server account/rateLimits/read",
    )


# --------------------------------------------------------------------------
# Topbar (cheap: every screen renders this)
# --------------------------------------------------------------------------

#: Plan section 4: "5 小时窗和 7 天窗两条进度条" (5h and 7d bars only) -- the
#: opus/sonnet sub-buckets are detail-page-only (`/quota`).
_TOPBAR_WINDOW_KEYS: Final[tuple[str, ...]] = ("five_hour", "seven_day")


@dataclass(frozen=True)
class TopbarQuotaBar:
    key: str
    label: str
    percent_display: str
    width_percent: float  # 0-100, clamped; 0 when percent_used is unknown
    status: Status
    reset_label: str
    projection_label: str | None  # only set on the five_hour bar


@dataclass(frozen=True)
class TopbarQuota:
    available: bool
    unavailable_reason: str | None
    bars: tuple[TopbarQuotaBar, ...]


def unknown_topbar_quota() -> TopbarQuota:
    return TopbarQuota(available=False, unavailable_reason="unknown", bars=())


def to_topbar_quota(report: ClaudeQuotaReport, *, now: datetime) -> TopbarQuota:
    """Pure transform from a `ClaudeQuotaReport` to the compact topbar view."""
    snapshot = report.snapshot
    if not snapshot.available:
        return TopbarQuota(available=False, unavailable_reason=snapshot.unavailable_reason, bars=())

    by_key = {window.key: window for window in snapshot.windows}
    bars: list[TopbarQuotaBar] = []
    for key in _TOPBAR_WINDOW_KEYS:
        window = by_key.get(key)
        if window is None:
            continue
        percent = window.percent_used
        resets_label = (
            f"reset {_format_duration_short((window.resets_at - now).total_seconds())}"
            if window.resets_at is not None
            else "reset unknown"
        )
        bars.append(
            TopbarQuotaBar(
                key=key,
                label=window.label,
                percent_display=f"{percent:.0f}%" if percent is not None else "unknown",
                width_percent=max(0.0, min(100.0, percent)) if percent is not None else 0.0,
                status=window.status,
                reset_label=resets_label,
                projection_label=report.projection.label if key == "five_hour" else None,
            )
        )
    return TopbarQuota(available=True, unavailable_reason=None, bars=tuple(bars))


# --------------------------------------------------------------------------
# `/quota` detail aggregate
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class QuotaReport:
    generated_at: datetime
    claude: ClaudeQuotaReport
    claude_throttle_event: ThrottleEvent | None
    codex: CodexQuotaState


def build_quota_report(
    cache: ClaudeQuotaCache,
    *,
    now: datetime | None = None,
    credentials_path: Path | None = None,
    client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    transcripts_root: Path | None = None,
    codex_auth_path: Path | None = None,
    codex_rpc_client: CodexRateLimitsClient | None = None,
) -> QuotaReport:
    """Assemble the full `/quota` detail view: all four Claude windows, extra
    usage, the Codex state, and the last throttle event from the fallback
    layer. `cache` is required (not defaulted here) so callers -- both
    `open_composer.cockpit.app` and tests -- always say explicitly which
    cache instance's state (and cache age / breaker state) they are asking
    to render.
    """
    moment = now or datetime.now(UTC)
    claude_report = cache.get(
        now=moment, credentials_path=credentials_path, client=client, timeout=timeout
    )
    try:
        throttle_event = find_last_throttle_event(transcripts_root)
    except Exception:
        # Defensive: a transcript-scanning surprise must not blank this page.
        throttle_event = None
    codex_state = build_codex_quota_state(auth_path=codex_auth_path, rpc_client=codex_rpc_client)
    return QuotaReport(
        generated_at=moment,
        claude=claude_report,
        claude_throttle_event=throttle_event,
        codex=codex_state,
    )


__all__ = [
    "BREAKER_COOLDOWN_SECONDS",
    "BREAKER_FAILURE_THRESHOLD",
    "CACHE_TTL_SECONDS",
    "CLAUDE_CREDENTIALS_PATH",
    "CLAUDE_OAUTH_BETA_HEADER",
    "CLAUDE_PROJECTS_DIR",
    "CLAUDE_USAGE_URL",
    "CODEX_AUTH_PATH",
    "DEFAULT_TIMEOUT_SECONDS",
    "BurnRateProjection",
    "BurnRateSample",
    "ClaudeExtraUsage",
    "ClaudeQuotaCache",
    "ClaudeQuotaReport",
    "ClaudeQuotaSnapshot",
    "ClaudeWindow",
    "CodexQuotaState",
    "CodexRateLimitWindow",
    "CodexRateLimitsClient",
    "QuotaReport",
    "ThrottleEvent",
    "TopbarQuota",
    "TopbarQuotaBar",
    "build_codex_quota_state",
    "build_quota_report",
    "compute_burn_rate_projection",
    "discover_claude_cli_version",
    "find_last_throttle_event",
    "get_default_claude_cache",
    "parse_codex_rate_limits_response",
    "to_topbar_quota",
    "unknown_topbar_quota",
]
