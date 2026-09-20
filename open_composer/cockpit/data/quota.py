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
The Claude OAuth access token can live in any of three places on this box,
tried in this fixed order (Step 18, T6b) because they fail in genuinely
different ways that the owner needs to tell apart:

1. The ``CLAUDE_CODE_OAUTH_TOKEN`` environment variable.
2. ``~/.paseo/config.json``'s ``agents.providers.claude.env.CLAUDE_CODE_OAUTH_TOKEN``
   -- a long-lived ``sk-ant-oat01-...`` token from ``claude setup-token``. It
   runs inference (that is how agents on this box work at all) but was
   observed 2026-09-20 to lack the ``user:profile`` scope this endpoint
   requires: HTTP 403, ``permission_error``. No amount of re-authenticating
   *this* token fixes that; a setup-token flow does not appear to ever mint
   that scope.
3. ``~/.claude/.credentials.json`` -- the interactive CLI login's token. It
   does carry ``user:profile`` when fresh, but expires: HTTP 401,
   ``authentication_error``. Re-running interactive login fixes this one.

Both non-repo paths are outside ``open_composer.cockpit.security.safe_repo_path``
(which validates paths *inside* the repo), so each is one explicit, hardcoded
module constant -- :data:`CLAUDE_CREDENTIALS_PATH`, :data:`PASEO_CONFIG_PATH`
-- never a caller-supplied or request-derived path. ``~/.paseo/config.json``
also holds *other providers'* secrets alongside this one key, so
:func:`_load_oauth_token_from_paseo` parses the whole small JSON document (it
has to, to reach the nested key) but only ever extracts and returns that one
string; the parsed ``dict`` is a local that goes out of scope on return, and
none of its other keys are read, logged, or placed on any dataclass.
:func:`_load_oauth_token`, :func:`_load_oauth_token_from_paseo`, and
:func:`_load_oauth_token_from_env` are the only functions in this module that
ever hold a real token in a variable; the instant their one caller
(``ClaudeQuotaCache._refresh``) has copied a chosen token into an
``Authorization`` header value for one outgoing request, that local binding
is deleted. The token is never stored on a dataclass field, never logged,
and never returned by any other function -- :class:`CredentialProbe`, the
per-source diagnosis record rendered on ``/quota``, carries only a source
name, a boolean, and a short fixed outcome string, never the token or a
response body. A failing HTTP response's body can itself echo request
headers back (a real misbehavior class for reverse gateways) -- any
diagnostic text this module keeps from an error response body is passed
through ``secret_scrub`` before it is ever stored, so a token-shaped string
in that body cannot reach a rendered page either.

Resolution is ordered, not "probe all three and report the best": sources
are tried in the fixed order above, and a source with no token found there
costs nothing (``"absent"``, no HTTP attempt). A source *with* a token is
always attempted even after an earlier source already failed -- stopping at
the first failure would have hidden one of this box's two real,
simultaneously-true failure reasons from the diagnosis table -- but the
round stops at the first *success*, since a live snapshot makes further
attempts pointless. The whole pass counts as exactly one breaker failure
when it nets no success (see "Cache, breaker, timeout" below), never three,
so a box with two broken sources and one absent one still only spends one
of the three-strikes budget per cache period. When every attempted source
fails, the round's single headline reason is chosen by priority --
``token expired -- re-login`` before ``token lacks user:profile scope``
before a generic HTTP failure before ``timeout``/``network error`` before
``invalid response`` -- because on this box specifically, fixing the expired
credential (case 3 above) is the one action that actually restores live
reads; naming it first, even when a scope failure is *also* true of another
source, points the owner at the fix that works. The full, unprioritized
picture (every attempted source's own outcome) is what :class:`CredentialProbe`
and its ``/quota`` table are for -- the headline reason is a recommendation,
not a claim that the other failures do not exist.

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

Usage estimate: absolute tokens, never a percentage (T6b)
-----------------------------------------------------------
:func:`build_usage_estimate` answers a narrower, honest question that does
not depend on the live endpoint at all: from this machine's own
``~/.claude/projects/*/*.jsonl`` transcripts, how many tokens did the
current rolling five-hour window actually spend, by model, and across how
many distinct sessions? This is a real count of what these transcripts
recorded, not a percentage of anything -- the five-hour *limit* the live
endpoint measures against is not public and not guessed at here, so turning
a token count into "X%" would be manufactured precision dressed up as a
number. The template labels this block "estimate (from local transcripts)"
and never puts a "%" next to it, distinct from the live block's percentages.

One correctness trap this had to avoid: a single logical assistant turn can
appear as *multiple* ``type: "assistant"`` lines in a transcript (observed
2026-09-20 -- one session had 376 such lines but only 24 distinct
``message.id`` values), each carrying the *same* ``usage`` object. Summing
every line naively overcounts by roughly 2x on real data. Every accumulator
in this module keys by ``message.id`` and keeps exactly one ``usage`` record
per id, so a repeated line contributes once.

Reading strategy, matching :func:`_last_quota_event_in_file`'s existing
bounded-tail pattern rather than a fresh one: a file whose ``mtime`` is
older than the window start cannot contain a line timestamped inside the
window (transcripts are append-only), so it is skipped without being opened
at all. A file that was touched inside the window is read from the end in
growing chunks (:data:`_USAGE_SCAN_INITIAL_TAIL_BYTES`, doubling-by-4 up to
:data:`_USAGE_SCAN_MAX_TAIL_BYTES`) until either the window's start is
reached inside the chunk already read, the whole file has been read, or the
cap is hit -- whichever comes first. No file is ever read past that cap
regardless of its total size, and no file is ever loaded as one whole
string held alongside others; each file's chunk is decoded, scanned for the
records it contributes, and discarded before the next file is opened.
:class:`UsageEstimateCache` caches the assembled result for
:data:`USAGE_ESTIMATE_CACHE_TTL_SECONDS` (60s) so that the topbar, which
renders this on every screen, does not re-scan on every request.

Usage estimate, T6c: a second source, and fresh vs cache read
-----------------------------------------------------------------
T6b's estimate only ever scanned ``~/.claude/projects/*/*.jsonl`` -- the
*main* sessions. The subagents this project runs (``Task``-tool
invocations) write their own transcripts to a second, disjoint location,
``/tmp/claude-0/<project-slug>/<session-id>/tasks/<agent-id>.output``, in
the identical JSONL shape (``message.usage``/``message.id`` and all).
Measured on this box 2026-09-20 for the 2026-09-19 working day, subagent
transcripts carried roughly 11x the fresh tokens the main-session-only
estimate saw. :func:`build_usage_estimate` now reads both sources with the
same bounded-tail, mtime-filtered discipline described above (see
:func:`_bounded_tail_scan_usage`, shared by both), tags every accumulated
:class:`RoleModelUsage` row with a ``role`` (``"main"`` or ``"subagent"``),
and degrades the subagent side to "tree not found" (never an error) when
``/tmp/claude-0`` is absent (e.g. after a reboot) -- see
``subagent_tree_found`` on :class:`UsageEstimate`.

A cache read is billed at a fraction of a fresh token, so folding it into
any other total manufactures a number that is both alarming and
meaningless (T6c brief: an 11.5M "total" on this box becomes ~150M once
subagents are counted, purely from cache reads). Every accumulator in this
module therefore keeps ``fresh`` (``input + output + cache_creation``) and
``cache_read`` as two permanently separate fields -- :class:`RoleModelUsage`
and :class:`SubagentTaskUsage` never expose a combined "total", and no
function in this module ever adds a ``cache_read_tokens`` value into a
``fresh_tokens`` value. The topbar collapses this to one line,
``UsageEstimate.topbar_label`` (e.g. ``"fresh 4.3M (main 0.4M, subagents
3.9M) . 5h window"``), built with :func:`format_compact_token_count` --
absolute tokens with a compact unit, fresh only, never a cache-read figure
and never a percentage.

Per-task subagent labels come from the *opposite* end of the file from
every other read in this module: :func:`_extract_first_user_text` takes a
small, fixed-size read of the first ``_LABEL_HEAD_BYTES`` (not a tail) to
find the first user-role line, because the brief a subagent was given is
necessarily near the start of its own transcript, not the end. This is a
second, independent bound (never more than one small prefix read per
file) alongside the existing growing-tail-to-16-MiB-cap read used for
usage; a file whose usage-relevant tail scan hits that cap without fully
covering the window is marked ``truncated=True`` on its
:class:`SubagentTaskUsage` and rendered on ``/quota`` as ``partial`` --
the page must say so rather than silently understating that one task's
numbers.

429 calibration (T6c)
-----------------------
:func:`find_last_throttle_event` (T6b, above) reports only the single most
recent ``quotaLimits`` hit. :func:`find_all_throttle_events` collects every
``quotaLimits{status: "rejected"}`` line seen across the same bounded
per-file tail read, and :func:`compute_throttle_calibration` turns that
list into an honest, non-percentage answer to "how much fresh usage
actually preceded a real throttle": for each event, the fresh tokens
(both sources, all roles) in the 5-hour window ending at that event's own
timestamp. This is reported as ``empirical window capacity`` -- a count,
never a percentage of anything -- because the true 5-hour limit remains
unpublished (same reasoning as the usage estimate itself). When at least
two events have a computed figure, the page also shows their min and
median, labelled plainly as such. The one ratio this module ever computes
against this figure is ``vs_last_throttle_ratio`` -- current fresh divided
by the fresh-at-last-throttle figure -- and only when that denominator
exists and is positive; it is a ratio (e.g. ``0.87x``), never rendered
with a ``%`` sign. With no throttle event on file at all, the page states
``no throttle observed yet`` rather than a manufactured zero.
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
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
#: T6b's second credential source. Outside the repo, like `CLAUDE_CREDENTIALS_PATH`
#: above -- same allowlist discipline, same reasons `safe_repo_path` does not apply.
PASEO_CONFIG_PATH: Final[Path] = Path.home() / ".paseo" / "config.json"
CODEX_AUTH_PATH: Final[Path] = Path.home() / ".codex" / "auth.json"
CLAUDE_PROJECTS_DIR: Final[Path] = Path.home() / ".claude" / "projects"

DEFAULT_TIMEOUT_SECONDS: Final[float] = 5.0
CACHE_TTL_SECONDS: Final[float] = 60.0
BREAKER_FAILURE_THRESHOLD: Final[int] = 3
BREAKER_COOLDOWN_SECONDS: Final[float] = 600.0  # 10 minutes

#: T6b: ordered credential resolution. The env var name is Anthropic's own
#: (also what a real `claude setup-token` writes into `~/.paseo/config.json`).
_ENV_TOKEN_VAR: Final[str] = "CLAUDE_CODE_OAUTH_TOKEN"

CredentialSourceKey = Literal["env", "paseo", "credentials_file"]

#: Fixed resolution order and display labels -- never the token, see module
#: docstring's "Credential handling". Order matches the module docstring's
#: numbered list.
CREDENTIAL_SOURCE_ORDER: Final[tuple[CredentialSourceKey, ...]] = (
    "env",
    "paseo",
    "credentials_file",
)
_CREDENTIAL_SOURCE_LABELS: Final[dict[CredentialSourceKey, str]] = {
    "env": f"env:{_ENV_TOKEN_VAR}",
    "paseo": "~/.paseo/config.json",
    "credentials_file": "~/.claude/.credentials.json",
}

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
# Usage estimate (T6b): see module docstring's "Usage estimate" section.
# --------------------------------------------------------------------------

USAGE_ESTIMATE_WINDOW_HOURS: Final[float] = 5.0
USAGE_ESTIMATE_CACHE_TTL_SECONDS: Final[float] = 60.0
#: First tail read per file. Large enough to cover a normal session's
#: worth of chatter without a second read; doubled-by-4 (see
#: `_scan_transcript_for_usage`) up to the cap below on a busy file.
_USAGE_SCAN_INITIAL_TAIL_BYTES: Final[int] = 1_048_576  # 1 MiB
_USAGE_SCAN_MAX_TAIL_BYTES: Final[int] = 16 * 1024 * 1024  # 16 MiB, never more per file
#: Safety cap on how many in-window files get scanned at all, independent of
#: the per-file byte cap above -- guards against a pathological number of
#: distinct session files all touched inside one five-hour window.
_MAX_USAGE_TRANSCRIPT_FILES: Final[int] = 50

#: T6c: subagent (`Task`-tool) transcripts, a second, disjoint source from
#: the main-session `CLAUDE_PROJECTS_DIR` tree above -- see module
#: docstring's "Usage estimate, T6c" section. A bare module global, like
#: `CLAUDE_PROJECTS_DIR`, so a test can monkeypatch it in place; the `/tmp`
#: tree can be absent after a reboot, which degrades to "tree not found"
#: rather than an error (see `build_usage_estimate`).
SUBAGENT_TASKS_ROOT: Final[Path] = Path("/tmp/claude-0")
#: project-slug / session-id / tasks / agent-id, relative to `SUBAGENT_TASKS_ROOT`.
_SUBAGENT_TASK_GLOB: Final[str] = "*/*/tasks/*.output"
_MAIN_TRANSCRIPT_GLOB: Final[str] = "*/*.jsonl"
_MAX_SUBAGENT_TASK_FILES: Final[int] = 50
#: Bounded, fixed-size *head* read (not the tail-growing pattern used for
#: usage) for a subagent task's label -- the brief a task was given is near
#: the start of its own transcript, not the end.
_LABEL_HEAD_BYTES: Final[int] = 65_536  # 64 KiB
_LABEL_BRIEF_CHARS: Final[int] = 60
#: 429 calibration (T6c): bounds how many past throttle events get a fresh
#: computed for them -- see `compute_throttle_calibration`. `event_count`
#: itself is never truncated by this; only how many get a fresh figure. Kept
#: small: computing one event's figure means scanning every in-window file
#: across both sources (observed cost on this box: ~1-2s per event, mtime
#: filtering being a much weaker bound for an old historical window than
#: for "now" -- see `compute_throttle_calibration`'s docstring), and
#: `ThrottleCalibrationCache` below only amortizes *repeated* renders, not
#: the first one.
_MAX_THROTTLE_EVENTS_FOR_CALIBRATION: Final[int] = 5
#: `ThrottleCalibrationCache`'s TTL -- same period as `UsageEstimateCache`,
#: for the same reason (this is a per-page-render computation, not a
#: per-screen one, but is expensive enough on this box to still need it).
THROTTLE_CALIBRATION_CACHE_TTL_SECONDS: Final[float] = 60.0


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


def _load_oauth_token_from_paseo(path: Path) -> str | None:
    """Read ``agents.providers.claude.env.CLAUDE_CODE_OAUTH_TOKEN`` from `path`.

    `path` holds several other providers' secrets alongside this one key
    (module docstring). Parsing the whole small JSON document is required to
    reach the nested key, but only that one string is ever pulled out; the
    parsed ``dict`` (and every sibling provider's secret in it) goes out of
    scope the moment this function returns and is never logged, stored on a
    dataclass, or handed to any caller other than the one that immediately
    builds one `Authorization` header from it.
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
    agents = data.get("agents")
    if not isinstance(agents, dict):
        return None
    providers = agents.get("providers")
    if not isinstance(providers, dict):
        return None
    claude = providers.get("claude")
    if not isinstance(claude, dict):
        return None
    env = claude.get("env")
    if not isinstance(env, dict):
        return None
    token = env.get(_ENV_TOKEN_VAR)
    return token if isinstance(token, str) and token else None


def _load_oauth_token_from_env(env: Mapping[str, str]) -> str | None:
    """Read `_ENV_TOKEN_VAR` from an environment mapping (default `os.environ`).

    Takes the mapping as a parameter (never reaches into `os.environ`
    itself) so a test can supply a synthetic one without mutating the real
    process environment.
    """
    token = env.get(_ENV_TOKEN_VAR)
    return token if isinstance(token, str) and token else None


def _resolve_credential_candidates(
    *, env: Mapping[str, str], paseo_path: Path, credentials_path: Path
) -> tuple[tuple[CredentialSourceKey, str, str | None], ...]:
    """The three (source, display label, token-or-None) candidates, in the
    fixed order documented in the module docstring's "Credential handling".
    """
    return (
        ("env", _CREDENTIAL_SOURCE_LABELS["env"], _load_oauth_token_from_env(env)),
        ("paseo", _CREDENTIAL_SOURCE_LABELS["paseo"], _load_oauth_token_from_paseo(paseo_path)),
        (
            "credentials_file",
            _CREDENTIAL_SOURCE_LABELS["credentials_file"],
            _load_oauth_token(credentials_path),
        ),
    )


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
class CredentialProbe:
    """One credential source's diagnosis for one resolution round (T6b).

    Rendered as a row in the ``/quota`` credential table. Never carries the
    token or a response body -- ``label`` is one of the three fixed display
    strings in :data:`_CREDENTIAL_SOURCE_LABELS`, and ``outcome`` is one of
    the short fixed strings documented on :func:`build_quota_report`'s
    caller, `ClaudeQuotaCache._refresh`: ``"ok"``, ``"expired (401)"``,
    ``"insufficient scope (403)"``, ``"http <code>"``, ``"timeout"``,
    ``"network error"``, ``"invalid response"``, or ``"absent"`` (no token
    found at this source, so no request was attempted).
    """

    source: CredentialSourceKey
    label: str
    token_found: bool
    outcome: str


@dataclass(frozen=True)
class ClaudeQuotaSnapshot:
    """What is known about Claude subscription usage right now.

    ``available=False`` covers every failure mode named in the T6 brief:
    ``unavailable_reason`` is one of ``"timeout"``, ``"http 4xx/5xx"``,
    ``"no credentials"``, ``"breaker open"``, plus two this module adds for
    completeness (``"network error"`` for a connection failure that is not a
    timeout, ``"invalid response"`` for a response that parses as JSON but
    not into the expected shape), plus two T6b adds once a specific status
    code names the actual cause (``"token expired -- re-login"`` for a 401,
    ``"token lacks user:profile scope"`` for a 403) -- see module docstring's
    "Credential handling" for why these two get to be the headline reason
    ahead of the generic ones. ``diagnostic`` is only ever populated for an
    HTTP error, and only after `secret_scrub` -- see module docstring.
    ``credential_probes`` is the full per-source diagnosis for this round
    (T6b); it is empty only when the breaker was already open and even then
    still reports each source's `token_found` (a local file read, not a
    network attempt) -- see `ClaudeQuotaCache._refresh`.
    """

    fetched_at: datetime
    available: bool
    windows: tuple[ClaudeWindow, ...]
    extra_usage: ClaudeExtraUsage | None
    unavailable_reason: str | None
    diagnostic: str | None
    http_status: int | None = None
    credential_probes: tuple[CredentialProbe, ...] = ()


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
    moment: datetime,
    reason: str,
    *,
    diagnostic: str | None = None,
    http_status: int | None = None,
    credential_probes: tuple[CredentialProbe, ...] = (),
) -> ClaudeQuotaSnapshot:
    return ClaudeQuotaSnapshot(
        fetched_at=moment,
        available=False,
        windows=(),
        extra_usage=None,
        unavailable_reason=reason,
        diagnostic=diagnostic,
        http_status=http_status,
        credential_probes=credential_probes,
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
# Round-level failure summary: which attempted source's outcome becomes the
# one headline `unavailable_reason` when a whole resolution round fails.
# See module docstring's "Credential handling", last paragraph, for why this
# is a priority pick rather than "first attempted" or "last attempted".
# --------------------------------------------------------------------------

#: Most actionable first. Only reached for probes that were actually
#: attempted (a token was found there); `"absent"` never appears here.
_ROUND_REASON_PRIORITY: Final[tuple[str, ...]] = (
    "expired (401)",
    "insufficient scope (403)",
    "http",  # generic bucket for any `f"http {code}"` outcome
    "timeout",
    "network error",
    "invalid response",
)

_OUTCOME_TO_ROUND_REASON: Final[dict[str, str]] = {
    "expired (401)": "token expired -- re-login",
    "insufficient scope (403)": "token lacks user:profile scope",
    "timeout": "timeout",
    "network error": "network error",
    "invalid response": "invalid response",
}


def _priority_rank(outcome: str) -> int:
    key = "http" if outcome.startswith("http ") else outcome
    try:
        return _ROUND_REASON_PRIORITY.index(key)
    except ValueError:
        return len(_ROUND_REASON_PRIORITY)  # defensive: unrecognized outcome, lowest priority


def _round_reason_for_outcome(outcome: str) -> str:
    """The pre-T6b-compatible `unavailable_reason` string for one outcome.

    Every code path that is not 401/403 keeps its exact pre-T6b wording
    (``"http 4xx/5xx"``, ``"timeout"``, ``"network error"``,
    ``"invalid response"``) so existing callers and tests that predate the
    three-source round see unchanged text for those cases.
    """
    if outcome in _OUTCOME_TO_ROUND_REASON:
        return _OUTCOME_TO_ROUND_REASON[outcome]
    if outcome.startswith("http "):
        return "http 4xx/5xx"
    return outcome


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
        paseo_config_path: Path | None = None,
        env: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> ClaudeQuotaReport:
        moment = now or datetime.now(UTC)
        if self._snapshot is not None and self._snapshot_at is not None:
            age = (moment - self._snapshot_at).total_seconds()
            if 0 <= age < CACHE_TTL_SECONDS:
                return self._make_report(moment, served_from_cache=True, cache_age=age)

        snapshot = self._refresh(
            moment,
            credentials_path=credentials_path,
            paseo_config_path=paseo_config_path,
            env=env,
            client=client,
            timeout=timeout,
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
        paseo_config_path: Path | None,
        env: Mapping[str, str] | None,
        client: httpx.Client | None,
        timeout: float,
    ) -> ClaudeQuotaSnapshot:
        """One resolution round across all three credential sources.

        See module docstring's "Credential handling": sources are tried in
        `CREDENTIAL_SOURCE_ORDER`, an absent source costs no HTTP attempt, a
        present-but-failing source does not stop the round (so the diagnosis
        table can show every real failure, not just the first), and the
        round stops at the first success. Whatever happens, this whole call
        is at most one round -- `_record_failure` below is called at most
        once per round, never once per source, so the breaker's
        three-strikes budget is spent in cache periods, not in credential
        sources.
        """
        # Local, cheap, no network: which sources have a token right now.
        # Computed even when the breaker is open below, since checking for a
        # token is a local file/env read, not the network attempt the
        # breaker exists to gate.
        candidates = _resolve_credential_candidates(
            env=env if env is not None else os.environ,
            paseo_path=paseo_config_path if paseo_config_path is not None else PASEO_CONFIG_PATH,
            credentials_path=(
                credentials_path if credentials_path is not None else CLAUDE_CREDENTIALS_PATH
            ),
        )

        if self._breaker_open_until is not None:
            if moment < self._breaker_open_until:
                probes = tuple(
                    CredentialProbe(
                        source=source,
                        label=label,
                        token_found=token is not None,
                        outcome="breaker open" if token is not None else "absent",
                    )
                    for source, label, token in candidates
                )
                return _unavailable_snapshot(moment, "breaker open", credential_probes=probes)
            # Cooldown elapsed: close the breaker and allow exactly one fresh round.
            self._breaker_open_until = None
            self._consecutive_failures = 0

        probes: list[CredentialProbe] = []
        winning_snapshot: ClaudeQuotaSnapshot | None = None
        best_priority: int | None = None
        best_reason: str | None = None
        best_diagnostic: str | None = None
        best_http_status: int | None = None

        def _consider_failure(
            outcome: str, *, diagnostic: str | None = None, http_status: int | None = None
        ) -> None:
            nonlocal best_priority, best_reason, best_diagnostic, best_http_status
            rank = _priority_rank(outcome)
            if best_priority is None or rank < best_priority:
                best_priority = rank
                best_reason = _round_reason_for_outcome(outcome)
                best_diagnostic = diagnostic
                best_http_status = http_status

        owns_client = client is None
        http_client = client if client is not None else _build_http_client()
        try:
            for source, label, token in candidates:
                if token is None:
                    probes.append(
                        CredentialProbe(
                            source=source, label=label, token_found=False, outcome="absent"
                        )
                    )
                    continue

                version = discover_claude_cli_version()
                headers = {
                    "Authorization": f"Bearer {token}",
                    "anthropic-beta": CLAUDE_OAUTH_BETA_HEADER,
                    "User-Agent": f"claude-code/{version}",
                }
                del token  # must not survive past building this one header value

                try:
                    response = http_client.get(CLAUDE_USAGE_URL, headers=headers, timeout=timeout)
                except httpx.TimeoutException:
                    probes.append(
                        CredentialProbe(
                            source=source, label=label, token_found=True, outcome="timeout"
                        )
                    )
                    _consider_failure("timeout")
                    continue
                except httpx.HTTPError:
                    probes.append(
                        CredentialProbe(
                            source=source, label=label, token_found=True, outcome="network error"
                        )
                    )
                    _consider_failure("network error")
                    continue

                if response.status_code == 401:
                    probes.append(
                        CredentialProbe(
                            source=source, label=label, token_found=True, outcome="expired (401)"
                        )
                    )
                    diagnostic = secret_scrub(response.text[:500]) if response.text else None
                    _consider_failure("expired (401)", diagnostic=diagnostic, http_status=401)
                    continue
                if response.status_code == 403:
                    probes.append(
                        CredentialProbe(
                            source=source,
                            label=label,
                            token_found=True,
                            outcome="insufficient scope (403)",
                        )
                    )
                    diagnostic = secret_scrub(response.text[:500]) if response.text else None
                    _consider_failure(
                        "insufficient scope (403)", diagnostic=diagnostic, http_status=403
                    )
                    continue
                if response.status_code >= 400:
                    outcome = f"http {response.status_code}"
                    probes.append(
                        CredentialProbe(
                            source=source, label=label, token_found=True, outcome=outcome
                        )
                    )
                    diagnostic = secret_scrub(response.text[:500]) if response.text else None
                    _consider_failure(
                        outcome, diagnostic=diagnostic, http_status=response.status_code
                    )
                    continue

                try:
                    winning_snapshot = _parse_usage_payload(response.json(), now=moment)
                except Exception:
                    # Defensive: this endpoint is undocumented and can change
                    # shape without notice (module docstring) -- a parse
                    # surprise must degrade this one probe, not crash the page.
                    probes.append(
                        CredentialProbe(
                            source=source,
                            label=label,
                            token_found=True,
                            outcome="invalid response",
                        )
                    )
                    _consider_failure("invalid response")
                    continue

                probes.append(
                    CredentialProbe(source=source, label=label, token_found=True, outcome="ok")
                )
                break  # a live snapshot makes further sources pointless
        finally:
            if owns_client:
                http_client.close()

        probes_tuple = tuple(probes)
        if winning_snapshot is not None:
            self._consecutive_failures = 0
            self._breaker_open_until = None
            return replace(winning_snapshot, credential_probes=probes_tuple)

        self._record_failure(moment)
        reason = best_reason if best_reason is not None else "no credentials"
        return _unavailable_snapshot(
            moment,
            reason,
            diagnostic=best_diagnostic,
            http_status=best_http_status,
            credential_probes=probes_tuple,
        )

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


def _all_quota_events_in_file(path: Path) -> tuple[ThrottleEvent, ...]:
    """Every `quotaLimits{status: "rejected"}` line in one file's bounded tail.

    Same fixed-size tail read as `_last_quota_event_in_file` (this module's
    existing bounded-tail pattern), but collects every matching line instead
    of stopping at the first (most recent) one -- T6c's calibration needs a
    count and a spread across events, not just the latest. Filtered to
    `status: "rejected"` specifically: per
    `reports/research/intel/I-20260919-02-subscription-quota-readout.md`,
    every `quotaLimits` object ever observed on this box has that status
    (an `allowed`/`allowed_warning` status has never been seen), but
    filtering explicitly here documents the assumption rather than relying
    on it silently.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - _TRANSCRIPT_TAIL_BYTES))
            chunk = handle.read()
    except OSError:
        return ()
    lines = chunk.decode("utf-8", errors="replace").split("\n")
    if size > _TRANSCRIPT_TAIL_BYTES:
        lines = lines[1:]  # drop a possibly-truncated first line

    events: list[ThrottleEvent] = []
    for line in lines:
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
        if quota_obj.get("status") != "rejected":
            continue
        events.append(
            ThrottleEvent(
                kind="event",
                at=_parse_iso(obj.get("timestamp")),
                rate_limit_type=(
                    quota_obj.get("rateLimitType")
                    if isinstance(quota_obj.get("rateLimitType"), str)
                    else None
                ),
                status=(
                    quota_obj.get("status") if isinstance(quota_obj.get("status"), str) else None
                ),
                resets_at=_parse_epoch_seconds(quota_obj.get("resetsAt")),
                overage_status=(
                    quota_obj.get("overageStatus")
                    if isinstance(quota_obj.get("overageStatus"), str)
                    else None
                ),
                source_path=secret_scrub(str(path)),
            )
        )
    return tuple(events)


def find_all_throttle_events(
    root: Path | None = None, *, max_files: int = _MAX_TRANSCRIPT_FILES_SCANNED
) -> tuple[ThrottleEvent, ...]:
    """Every observed throttle event across this machine's Claude transcripts (T6c).

    Unlike `find_last_throttle_event`, does not stop at the first file with
    a hit -- every qualifying event in every one of the `max_files`
    most-recently-modified transcripts is collected, so
    `compute_throttle_calibration` can report a real count and a spread
    rather than only the most recent occurrence.
    """
    base = root if root is not None else CLAUDE_PROJECTS_DIR
    if not base.is_dir():
        return ()
    try:
        candidates = sorted(
            (p for p in base.glob("*/*.jsonl") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return ()
    events: list[ThrottleEvent] = []
    for path in candidates[:max_files]:
        try:
            events.extend(_all_quota_events_in_file(path))
        except Exception:
            continue
    return tuple(events)


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
# Usage estimate (T6b/T6c) -- see module docstring's "Usage estimate"
# sections. Absolute tokens from local transcripts, never a percentage; no
# network. Fresh (input + output + cache_creation) and cache_read are kept
# permanently separate -- see "Usage estimate, T6c" in the module docstring.
# --------------------------------------------------------------------------

UsageRole = Literal["main", "subagent"]

#: Fixed role display/sort order -- main first, then subagent, matching the
#: T6c brief's own table ("main session" column before "subagents").
_ROLE_ORDER: Final[tuple[UsageRole, ...]] = ("main", "subagent")


@dataclass(frozen=True)
class _UsageRecord:
    """One `message.id`'s usage, keyed and deduped by the caller.

    Private accumulator shared by the main-transcript and subagent-task
    scanners (`_bounded_tail_scan_usage`) -- never returned from a public
    function.
    """

    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    at: datetime | None


@dataclass(frozen=True)
class RoleModelUsage:
    """One `(role, model)` bucket's token totals within the estimate window.

    `fresh_tokens` (`input + output + cache_creation`) and
    `cache_read_tokens` are kept as two separate fields and never summed
    into a third "total" field anywhere in this module -- see module
    docstring's "Usage estimate, T6c" section for why a folded total is
    both alarming and meaningless here.
    """

    role: UsageRole
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    fresh_tokens: int
    cache_read_tokens: int


@dataclass(frozen=True)
class SubagentTaskUsage:
    """One subagent task file's token totals and identity, for the `/quota`
    per-task table (T6c). `label` is the file stem plus a `secret_scrub`bed
    ~60-character snippet of the task's own first user-role line (its
    brief) -- see `_subagent_task_label`. `truncated` is set when this
    file's bounded tail scan hit `_USAGE_SCAN_MAX_TAIL_BYTES` without fully
    covering the window, meaning this task's own numbers may understate its
    real usage; the `/quota` page must render that as `partial`, not
    silently.
    """

    label: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    fresh_tokens: int
    cache_read_tokens: int
    turns: int
    first_activity: datetime | None
    last_activity: datetime | None
    file_size_bytes: int
    truncated: bool
    source_path: str


@dataclass(frozen=True)
class UsageEstimate:
    """A transcript-derived, absolute-tokens usage figure for one window.

    Deliberately has no percentage field and no folded fresh+cache_read
    total -- see module docstring's "Usage estimate" sections. Every
    number here is a real count of what local transcripts (both the main
    `CLAUDE_PROJECTS_DIR` tree and the `SUBAGENT_TASKS_ROOT` tree, T6c)
    recorded in ``[window_start, window_end)``; the `*_files_scanned`,
    `subagent_tree_found`, and `generated_at` fields are the
    honesty/staleness receipts a reader needs to trust the rest.
    """

    window_start: datetime
    window_end: datetime
    by_role_model: tuple[RoleModelUsage, ...]
    subagent_tasks: tuple[SubagentTaskUsage, ...]  # sorted by fresh_tokens, descending
    fresh_main: int
    fresh_subagent: int
    fresh_total: int
    cache_read_main: int
    cache_read_subagent: int
    cache_read_total: int
    distinct_session_count: int  # main sessions only -- see `_bounded_tail_scan_usage`
    main_files_scanned: int
    subagent_files_scanned: int
    subagent_tree_found: bool
    topbar_label: str  # e.g. "fresh 4.3M (main 0.4M, subagents 3.9M) . 5h window"
    generated_at: datetime


def format_compact_token_count(n: int) -> str:
    """Absolute token count with a compact unit (k / M), never a percentage.

    ``0`` and every value below 1,000 render as a bare integer; below
    1,000,000 as ``N.Nk``; at or above as ``N.NM``. Negative input is
    clamped to 0 (a token count is never negative; defensive only).
    """
    n = max(0, int(n))
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _usage_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _iter_files_in_window(
    root: Path, glob_pattern: str, window_start: datetime, *, max_files: int
) -> tuple[Path, ...]:
    """Files matching `glob_pattern` under `root` whose `mtime` falls inside
    the window, newest first.

    A file untouched since before `window_start` is append-only and so
    cannot contain a line timestamped inside the window -- it is excluded
    here without ever being opened (module docstring's "Reading strategy").
    Shared by the main-transcript (`_MAIN_TRANSCRIPT_GLOB`) and subagent-task
    (`_SUBAGENT_TASK_GLOB`) sources (T6c).
    """
    if not root.is_dir():
        return ()
    try:
        candidates = [p for p in root.glob(glob_pattern) if p.is_file()]
    except OSError:
        return ()
    in_window: list[tuple[float, Path]] = []
    for path in candidates:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if datetime.fromtimestamp(mtime, tz=UTC) >= window_start:
            in_window.append((mtime, path))
    in_window.sort(key=lambda pair: pair[0], reverse=True)
    return tuple(path for _, path in in_window[:max_files])


def _decode_tail_lines(path: Path, tail_bytes: int) -> tuple[list[str], int]:
    """Read the last `tail_bytes` of `path` and split into lines.

    Returns `(lines, chunk_start_offset)`. When `chunk_start_offset > 0` the
    first decoded line may be a truncated fragment of a longer line, so the
    caller drops it (mirrors `_last_quota_event_in_file`'s existing pattern).
    """
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        start = max(0, size - tail_bytes)
        handle.seek(start)
        chunk = handle.read()
    lines = chunk.decode("utf-8", errors="replace").split("\n")
    if start > 0:
        lines = lines[1:]
    return lines, start


def _bounded_tail_scan_usage(
    path: Path, window_start: datetime, *, window_end: datetime | None = None
) -> tuple[dict[str, _UsageRecord], set[str], bool]:
    """Bounded, growing tail-scan of one transcript for in-window usage.

    Shared by the main-transcript scan (`build_usage_estimate`) and the
    per-subagent-task scan (`_scan_subagent_task_file`, T6c) -- the JSONL
    shape is identical between the two sources (module docstring's "Usage
    estimate, T6c" section). Returns `(usage_by_message_id, session_ids,
    truncated)`. Keying by `message.id` (never summing every matching line)
    is what makes this honest -- see module docstring's "one correctness
    trap" paragraph: a single logical turn can be logged as several lines
    sharing one `usage` object, and summing every line overcounts.

    `window_end`, when given, excludes any line timestamped at or after it
    -- used only by `_fresh_tokens_in_window` (T6c 429 calibration), which
    computes a *historical* window that must not pick up lines the file
    grew after that window closed. The default `None` (used by every other
    caller, whose window always ends at "now") applies no upper bound,
    matching this function's pre-T6c behavior exactly.

    Starts with `_USAGE_SCAN_INITIAL_TAIL_BYTES` and, if the window is not
    yet fully covered by what has been read (the oldest parsed timestamp in
    the chunk is still `>= window_start`, and the chunk is not already the
    whole file), grows the tail by 4x and re-reads, up to
    `_USAGE_SCAN_MAX_TAIL_BYTES` -- this file is never read past that cap
    and is never held in memory as more than one such chunk at a time.
    `truncated` is `True` only when the cap was hit *and* the window was
    not fully covered *and* the whole file was not already read -- i.e.
    real content beyond the cap was left unread (T6c: rendered as `partial`
    on `/quota` for a subagent task).
    """
    messages: dict[str, _UsageRecord] = {}
    sessions: set[str] = set()
    try:
        size = path.stat().st_size
    except OSError:
        return messages, sessions, False
    if size <= 0:
        return messages, sessions, False

    tail_bytes = min(size, _USAGE_SCAN_INITIAL_TAIL_BYTES)
    truncated = False
    while True:
        try:
            lines, start = _decode_tail_lines(path, tail_bytes)
        except OSError:
            return messages, sessions, False

        earliest_seen_ts: datetime | None = None
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            ts = _parse_iso(obj.get("timestamp"))
            if ts is None:
                continue
            if earliest_seen_ts is None or ts < earliest_seen_ts:
                earliest_seen_ts = ts
            if ts < window_start:
                continue
            if window_end is not None and ts >= window_end:
                continue

            session_id = obj.get("sessionId")
            if isinstance(session_id, str) and session_id:
                sessions.add(session_id)

            if obj.get("type") != "assistant":
                continue
            message = obj.get("message")
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            msg_id = message.get("id")
            if not isinstance(msg_id, str) or not msg_id:
                continue
            model = message.get("model")
            model = model if isinstance(model, str) and model else "unknown"
            messages[msg_id] = _UsageRecord(
                model=model,
                input_tokens=_usage_int(usage.get("input_tokens")),
                output_tokens=_usage_int(usage.get("output_tokens")),
                cache_creation_tokens=_usage_int(usage.get("cache_creation_input_tokens")),
                cache_read_tokens=_usage_int(usage.get("cache_read_input_tokens")),
                at=ts,
            )

        reached_bof = start == 0
        window_fully_covered = reached_bof or (
            earliest_seen_ts is not None and earliest_seen_ts < window_start
        )
        hit_cap = tail_bytes >= _USAGE_SCAN_MAX_TAIL_BYTES
        whole_file_read = tail_bytes >= size
        if window_fully_covered or hit_cap or whole_file_read:
            truncated = hit_cap and not window_fully_covered and not whole_file_read
            break
        tail_bytes = min(_USAGE_SCAN_MAX_TAIL_BYTES, size, tail_bytes * 4)

    return messages, sessions, truncated


def _extract_first_user_text(path: Path, *, head_bytes: int = _LABEL_HEAD_BYTES) -> str | None:
    """The first user-role message's text in `path`'s first `head_bytes` (T6c).

    A bounded, fixed-size read from the *start* of the file -- the opposite
    end from every other scan in this module -- because the brief a
    subagent task was given is necessarily near the start of its own
    transcript. If no user-role line with text appears in that prefix, the
    caller falls back to the file stem alone rather than reading further
    (module docstring's "Usage estimate, T6c" section).
    """
    try:
        with path.open("rb") as handle:
            chunk = handle.read(head_bytes)
    except OSError:
        return None
    if not chunk:
        return None
    lines = chunk.decode("utf-8", errors="replace").split("\n")
    if len(chunk) >= head_bytes:
        lines = lines[:-1]  # last line may be a truncated fragment
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or obj.get("type") != "user":
            continue
        message = obj.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    block_text = block.get("text")
                    if isinstance(block_text, str) and block_text.strip():
                        return block_text.strip()
    return None


def _subagent_task_label(path: Path) -> str:
    """`<file stem>: <~60 char, secret_scrubbed brief>`, or just the stem."""
    brief = _extract_first_user_text(path)
    if not brief:
        return path.stem
    snippet = secret_scrub(brief)[:_LABEL_BRIEF_CHARS].strip()
    return f"{path.stem}: {snippet}" if snippet else path.stem


def _scan_subagent_task_file(path: Path, window_start: datetime) -> SubagentTaskUsage | None:
    """One subagent task file's `SubagentTaskUsage`, or `None`.

    `None` covers both "unreadable" and "no in-window usage recorded" --
    the latter is the common case (module docstring: many `tasks/*.output`
    files are bash-tool captures with no assistant `usage` at all), and a
    task contributing nothing is simply absent from the per-task table
    rather than rendered as an all-zero row.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size <= 0:
        return None
    messages, _sessions, truncated = _bounded_tail_scan_usage(path, window_start)
    if not messages:
        return None
    input_tokens = sum(record.input_tokens for record in messages.values())
    output_tokens = sum(record.output_tokens for record in messages.values())
    cache_creation_tokens = sum(record.cache_creation_tokens for record in messages.values())
    cache_read_tokens = sum(record.cache_read_tokens for record in messages.values())
    models = sorted({record.model for record in messages.values()})
    activities = [record.at for record in messages.values() if record.at is not None]
    return SubagentTaskUsage(
        label=_subagent_task_label(path),
        model="+".join(models) if models else "unknown",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation_tokens,
        fresh_tokens=input_tokens + output_tokens + cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
        turns=len(messages),
        first_activity=min(activities) if activities else None,
        last_activity=max(activities) if activities else None,
        file_size_bytes=size,
        truncated=truncated,
        source_path=secret_scrub(str(path)),
    )


def build_usage_estimate(
    root: Path | None = None,
    *,
    now: datetime | None = None,
    max_files: int = _MAX_USAGE_TRANSCRIPT_FILES,
    subagent_root: Path | None = None,
    max_subagent_files: int = _MAX_SUBAGENT_TASK_FILES,
) -> UsageEstimate:
    """Absolute token totals for the current rolling window, from local
    transcripts only -- no network, no live-endpoint dependency, see module
    docstring's "Usage estimate" sections. Degrades to an all-zero estimate
    (never raises) when a transcripts directory is missing or every file in
    it fails to read; a caller-visible zero is honest here (it means "no
    local record of usage in this window"), unlike a guessed percentage.

    T6c: combines two independent sources -- the main-session transcripts
    under `root` (default `CLAUDE_PROJECTS_DIR`) and the subagent task
    transcripts under `subagent_root` (default `SUBAGENT_TASKS_ROOT`, bare
    module global so a test can monkeypatch it). The subagent side missing
    entirely (`/tmp` absent after a reboot) degrades to
    `subagent_tree_found=False` with all-zero subagent totals, never an
    error.
    """
    moment = now or datetime.now(UTC)
    window_start = moment - timedelta(hours=USAGE_ESTIMATE_WINDOW_HOURS)

    main_base = root if root is not None else CLAUDE_PROJECTS_DIR
    main_files = _iter_files_in_window(
        main_base, _MAIN_TRANSCRIPT_GLOB, window_start, max_files=max_files
    )
    all_messages: dict[str, _UsageRecord] = {}
    sessions: set[str] = set()
    for path in main_files:
        try:
            messages, file_sessions, _truncated = _bounded_tail_scan_usage(path, window_start)
        except Exception:
            # Defensive: one unreadable/surprising transcript must not blank
            # the whole estimate.
            continue
        all_messages.update(messages)
        sessions.update(file_sessions)

    main_totals: dict[str, list[int]] = {}  # model -> [input, output, cache_creation, cache_read]
    for record in all_messages.values():
        bucket = main_totals.setdefault(record.model, [0, 0, 0, 0])
        bucket[0] += record.input_tokens
        bucket[1] += record.output_tokens
        bucket[2] += record.cache_creation_tokens
        bucket[3] += record.cache_read_tokens

    subagent_base = subagent_root if subagent_root is not None else SUBAGENT_TASKS_ROOT
    subagent_tree_found = subagent_base.is_dir()
    subagent_files = (
        _iter_files_in_window(
            subagent_base, _SUBAGENT_TASK_GLOB, window_start, max_files=max_subagent_files
        )
        if subagent_tree_found
        else ()
    )
    subagent_tasks: list[SubagentTaskUsage] = []
    subagent_totals: dict[str, list[int]] = {}
    for path in subagent_files:
        try:
            task = _scan_subagent_task_file(path, window_start)
        except Exception:
            # Defensive: one unreadable/surprising task file must not blank
            # the whole estimate.
            continue
        if task is None:
            continue
        subagent_tasks.append(task)
        bucket = subagent_totals.setdefault(task.model, [0, 0, 0, 0])
        bucket[0] += task.input_tokens
        bucket[1] += task.output_tokens
        bucket[2] += task.cache_creation_tokens
        bucket[3] += task.cache_read_tokens
    subagent_tasks.sort(key=lambda t: t.fresh_tokens, reverse=True)

    by_role_model: list[RoleModelUsage] = []
    for role, totals in (("main", main_totals), ("subagent", subagent_totals)):
        for model, values in sorted(totals.items()):
            input_t, output_t, cache_creation_t, cache_read_t = values
            by_role_model.append(
                RoleModelUsage(
                    role=role,  # type: ignore[arg-type]
                    model=model,
                    input_tokens=input_t,
                    output_tokens=output_t,
                    cache_creation_tokens=cache_creation_t,
                    fresh_tokens=input_t + output_t + cache_creation_t,
                    cache_read_tokens=cache_read_t,
                )
            )

    fresh_main = sum(row.fresh_tokens for row in by_role_model if row.role == "main")
    fresh_subagent = sum(row.fresh_tokens for row in by_role_model if row.role == "subagent")
    cache_read_main = sum(row.cache_read_tokens for row in by_role_model if row.role == "main")
    cache_read_subagent = sum(
        row.cache_read_tokens for row in by_role_model if row.role == "subagent"
    )
    window_hours_label = f"{USAGE_ESTIMATE_WINDOW_HOURS:.0f}h"
    topbar_label = (
        f"fresh {format_compact_token_count(fresh_main + fresh_subagent)} "
        f"(main {format_compact_token_count(fresh_main)}, "
        f"subagents {format_compact_token_count(fresh_subagent)}) . {window_hours_label} window"
    )

    return UsageEstimate(
        window_start=window_start,
        window_end=moment,
        by_role_model=tuple(by_role_model),
        subagent_tasks=tuple(subagent_tasks),
        fresh_main=fresh_main,
        fresh_subagent=fresh_subagent,
        fresh_total=fresh_main + fresh_subagent,
        cache_read_main=cache_read_main,
        cache_read_subagent=cache_read_subagent,
        cache_read_total=cache_read_main + cache_read_subagent,
        distinct_session_count=len(sessions),
        main_files_scanned=len(main_files),
        subagent_files_scanned=len(subagent_files),
        subagent_tree_found=subagent_tree_found,
        topbar_label=topbar_label,
        generated_at=moment,
    )


def _fresh_tokens_in_window(
    window_end: datetime,
    *,
    main_root: Path,
    subagent_root: Path,
    max_main_files: int,
    max_subagent_files: int,
) -> int:
    """Fresh tokens (both sources, all roles) in the 5h window ending at
    `window_end` (T6c 429 calibration). A lighter-weight sibling of
    `build_usage_estimate` that returns only the one integer calibration
    needs, using the same bounded-tail-scan discipline; see
    `compute_throttle_calibration`.
    """
    window_start = window_end - timedelta(hours=USAGE_ESTIMATE_WINDOW_HOURS)
    fresh = 0
    for path in _iter_files_in_window(
        main_root, _MAIN_TRANSCRIPT_GLOB, window_start, max_files=max_main_files
    ):
        try:
            messages, _sessions, _truncated = _bounded_tail_scan_usage(
                path, window_start, window_end=window_end
            )
        except Exception:
            continue
        fresh += sum(
            record.input_tokens + record.output_tokens + record.cache_creation_tokens
            for record in messages.values()
        )
    if subagent_root.is_dir():
        for path in _iter_files_in_window(
            subagent_root, _SUBAGENT_TASK_GLOB, window_start, max_files=max_subagent_files
        ):
            try:
                messages, _sessions, _truncated = _bounded_tail_scan_usage(
                    path, window_start, window_end=window_end
                )
            except Exception:
                continue
            fresh += sum(
                record.input_tokens + record.output_tokens + record.cache_creation_tokens
                for record in messages.values()
            )
    return fresh


@dataclass(frozen=True)
class ThrottleCalibration:
    """Empirical 5h-window capacity, calibrated from observed 429s (T6c).

    Never a percentage: each fresh figure is a real token count -- fresh
    tokens (both sources, all roles) summed over the 5-hour window ending
    at a `quotaLimits{status: "rejected"}` event's own timestamp. `available`
    is `False` only when no throttle event was found at all (`"no throttle
    observed yet"`); when at least one was found but its fresh figure could
    not be computed (a defensive, not-expected-in-practice path),
    `available` stays `True` (there genuinely was a throttle) while
    `last_fresh_at_event` is `None`. `vs_last_throttle_ratio` is
    `current_fresh / last_fresh_at_event` -- a ratio (e.g. `0.87`), never a
    percentage -- computed only when the denominator exists and is
    positive.
    """

    available: bool
    last_event: ThrottleEvent | None
    last_fresh_at_event: int | None
    event_count: int
    min_fresh_at_event: int | None
    median_fresh_at_event: int | None
    vs_last_throttle_ratio: float | None


def compute_throttle_calibration(
    *,
    now: datetime,
    current_fresh_total: int,
    main_root: Path | None = None,
    subagent_root: Path | None = None,
    max_events: int = _MAX_THROTTLE_EVENTS_FOR_CALIBRATION,
    max_main_files: int = _MAX_USAGE_TRANSCRIPT_FILES,
    max_subagent_files: int = _MAX_SUBAGENT_TASK_FILES,
) -> ThrottleCalibration:
    """T6c: turn every observed 429 into an honest, non-percentage figure.

    See module docstring's "429 calibration (T6c)" section. `current_fresh_total`
    is supplied by the caller (`build_quota_report` already computed it as
    part of the current `UsageEstimate`) rather than recomputed here, so
    this function never re-scans the *current* window -- only the
    historical window(s) ending at each past throttle event.

    Cost note: the mtime-only "cannot exclude" filter (`_iter_files_in_window`)
    is a tight bound when a window ends at "now" (only recently-touched files
    qualify) but a much weaker one for a window ending at an old historical
    timestamp -- on this box, a throttle event from two weeks ago pulled in
    essentially every main transcript ever since (anything touched *after*
    that old `window_start` qualifies), each read up to the usual
    `_USAGE_SCAN_MAX_TAIL_BYTES` cap. Measured at ~1-2s per event on this
    box's real data. Reducing `max_main_files`/`max_subagent_files` to fix
    this was tried and rejected: the relevant session for an old event is
    often no longer among the *most-recently-modified* files, so a smaller
    cap silently zeroes out real historical usage rather than merely
    approximating it. `ThrottleCalibrationCache` below is the actual fix for
    repeated page renders; the first render in a given 60s period still pays
    this cost, same trade-off `UsageEstimateCache` makes for the (much
    cheaper) usage estimate.
    """
    try:
        events = find_all_throttle_events(main_root)
    except Exception:
        events = ()
    dated = sorted((e for e in events if e.at is not None), key=lambda e: e.at, reverse=True)
    if not dated:
        return ThrottleCalibration(
            available=False,
            last_event=None,
            last_fresh_at_event=None,
            event_count=0,
            min_fresh_at_event=None,
            median_fresh_at_event=None,
            vs_last_throttle_ratio=None,
        )

    main_base = main_root if main_root is not None else CLAUDE_PROJECTS_DIR
    subagent_base = subagent_root if subagent_root is not None else SUBAGENT_TASKS_ROOT

    fresh_values: list[int | None] = []
    for event in dated[:max_events]:
        try:
            fresh_values.append(
                _fresh_tokens_in_window(
                    event.at,  # type: ignore[arg-type]
                    main_root=main_base,
                    subagent_root=subagent_base,
                    max_main_files=max_main_files,
                    max_subagent_files=max_subagent_files,
                )
            )
        except Exception:
            fresh_values.append(None)

    last_fresh = fresh_values[0] if fresh_values else None
    numeric = [v for v in fresh_values if v is not None]
    ratio = (
        (current_fresh_total / last_fresh) if last_fresh is not None and last_fresh > 0 else None
    )
    return ThrottleCalibration(
        available=True,
        last_event=dated[0],
        last_fresh_at_event=last_fresh,
        event_count=len(dated),
        min_fresh_at_event=min(numeric) if numeric else None,
        median_fresh_at_event=round(statistics.median(numeric)) if numeric else None,
        vs_last_throttle_ratio=ratio,
    )


class ThrottleCalibrationCache:
    """A 60-second in-memory cache for `compute_throttle_calibration` (T6c).

    Mirrors `UsageEstimateCache`'s TTL policy and carries no circuit breaker
    for the same reason: every failure mode this wraps already degrades to
    a `ThrottleCalibration(available=False, ...)` rather than raising. Exists
    because `compute_throttle_calibration` is measurably expensive on this
    box (see its own docstring's "Cost note") -- without this, every
    `/quota` render would pay that cost, not just the first one in a given
    `THROTTLE_CALIBRATION_CACHE_TTL_SECONDS` period.
    """

    def __init__(self) -> None:
        self._calibration: ThrottleCalibration | None = None
        self._computed_at: datetime | None = None

    def get(
        self,
        *,
        now: datetime,
        current_fresh_total: int,
        main_root: Path | None = None,
        subagent_root: Path | None = None,
    ) -> ThrottleCalibration:
        if self._calibration is not None and self._computed_at is not None:
            age = (now - self._computed_at).total_seconds()
            if 0 <= age < THROTTLE_CALIBRATION_CACHE_TTL_SECONDS:
                return self._calibration
        calibration = compute_throttle_calibration(
            now=now,
            current_fresh_total=current_fresh_total,
            main_root=main_root,
            subagent_root=subagent_root,
        )
        self._calibration = calibration
        self._computed_at = now
        return calibration


_DEFAULT_THROTTLE_CALIBRATION_CACHE = ThrottleCalibrationCache()


def get_default_throttle_calibration_cache() -> ThrottleCalibrationCache:
    """The process-wide cache `open_composer.cockpit.app` shares across requests.

    A function, not a bare module attribute, for the same reason as
    `get_default_claude_cache`/`get_default_usage_estimate_cache`: a test can
    monkeypatch this name to hand out a fresh, isolated instance instead of
    the one long-lived instance a real server keeps for its entire run.
    """
    return _DEFAULT_THROTTLE_CALIBRATION_CACHE


class UsageEstimateCache:
    """A 60-second in-memory cache for `build_usage_estimate` (T6b/T6c).

    Mirrors `ClaudeQuotaCache`'s TTL policy but carries no circuit breaker:
    a filesystem read has no remote service to protect, and every failure
    mode of the scan it wraps already degrades to zero rather than raising
    (see `build_usage_estimate`). Exists so the topbar, which renders this
    on every screen (module docstring), does not re-scan on every request.
    """

    def __init__(self) -> None:
        self._estimate: UsageEstimate | None = None
        self._computed_at: datetime | None = None

    def get(
        self,
        *,
        now: datetime | None = None,
        root: Path | None = None,
        subagent_root: Path | None = None,
    ) -> UsageEstimate:
        moment = now or datetime.now(UTC)
        if self._estimate is not None and self._computed_at is not None:
            age = (moment - self._computed_at).total_seconds()
            if 0 <= age < USAGE_ESTIMATE_CACHE_TTL_SECONDS:
                return self._estimate
        estimate = build_usage_estimate(root, now=moment, subagent_root=subagent_root)
        self._estimate = estimate
        self._computed_at = moment
        return estimate


_DEFAULT_USAGE_ESTIMATE_CACHE = UsageEstimateCache()


def get_default_usage_estimate_cache() -> UsageEstimateCache:
    """The process-wide cache `open_composer.cockpit.app` shares across requests.

    A function, not a bare module attribute, for the same reason as
    `get_default_claude_cache`: a test can monkeypatch this name to hand out
    a fresh, isolated instance instead of the one long-lived instance a real
    server keeps for its entire run.
    """
    return _DEFAULT_USAGE_ESTIMATE_CACHE


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
    usage_estimate: UsageEstimate
    throttle_calibration: ThrottleCalibration


def build_quota_report(
    cache: ClaudeQuotaCache,
    *,
    now: datetime | None = None,
    credentials_path: Path | None = None,
    paseo_config_path: Path | None = None,
    env: Mapping[str, str] | None = None,
    client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    transcripts_root: Path | None = None,
    subagent_transcripts_root: Path | None = None,
    codex_auth_path: Path | None = None,
    codex_rpc_client: CodexRateLimitsClient | None = None,
    usage_cache: UsageEstimateCache | None = None,
    calibration_cache: ThrottleCalibrationCache | None = None,
) -> QuotaReport:
    """Assemble the full `/quota` detail view: all four Claude windows, extra
    usage, the per-source credential diagnosis, the Codex state, the last
    throttle event from the fallback layer, the transcript-based usage
    estimate (T6b/T6c, now combining main and subagent transcripts), and the
    429 calibration (T6c). `cache` is required (not defaulted here) so
    callers -- both `open_composer.cockpit.app` and tests -- always say
    explicitly which cache instance's state (and cache age / breaker state)
    they are asking to render.
    """
    moment = now or datetime.now(UTC)
    claude_report = cache.get(
        now=moment,
        credentials_path=credentials_path,
        paseo_config_path=paseo_config_path,
        env=env,
        client=client,
        timeout=timeout,
    )
    try:
        throttle_event = find_last_throttle_event(transcripts_root)
    except Exception:
        # Defensive: a transcript-scanning surprise must not blank this page.
        throttle_event = None
    codex_state = build_codex_quota_state(auth_path=codex_auth_path, rpc_client=codex_rpc_client)
    usage_cache_obj = usage_cache if usage_cache is not None else get_default_usage_estimate_cache()
    usage_estimate = usage_cache_obj.get(
        now=moment, root=transcripts_root, subagent_root=subagent_transcripts_root
    )
    try:
        calibration_cache_obj = (
            calibration_cache
            if calibration_cache is not None
            else get_default_throttle_calibration_cache()
        )
        calibration = calibration_cache_obj.get(
            now=moment,
            current_fresh_total=usage_estimate.fresh_total,
            main_root=transcripts_root,
            subagent_root=subagent_transcripts_root,
        )
    except Exception:
        # Defensive: a calibration-scanning surprise must not blank this page.
        calibration = ThrottleCalibration(
            available=False,
            last_event=None,
            last_fresh_at_event=None,
            event_count=0,
            min_fresh_at_event=None,
            median_fresh_at_event=None,
            vs_last_throttle_ratio=None,
        )
    return QuotaReport(
        generated_at=moment,
        claude=claude_report,
        claude_throttle_event=throttle_event,
        codex=codex_state,
        usage_estimate=usage_estimate,
        throttle_calibration=calibration,
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
    "CREDENTIAL_SOURCE_ORDER",
    "DEFAULT_TIMEOUT_SECONDS",
    "PASEO_CONFIG_PATH",
    "SUBAGENT_TASKS_ROOT",
    "THROTTLE_CALIBRATION_CACHE_TTL_SECONDS",
    "USAGE_ESTIMATE_CACHE_TTL_SECONDS",
    "USAGE_ESTIMATE_WINDOW_HOURS",
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
    "CredentialProbe",
    "CredentialSourceKey",
    "QuotaReport",
    "RoleModelUsage",
    "SubagentTaskUsage",
    "ThrottleCalibration",
    "ThrottleCalibrationCache",
    "ThrottleEvent",
    "TopbarQuota",
    "TopbarQuotaBar",
    "UsageEstimate",
    "UsageEstimateCache",
    "UsageRole",
    "build_codex_quota_state",
    "build_quota_report",
    "build_usage_estimate",
    "compute_burn_rate_projection",
    "compute_throttle_calibration",
    "discover_claude_cli_version",
    "find_all_throttle_events",
    "find_last_throttle_event",
    "format_compact_token_count",
    "get_default_claude_cache",
    "get_default_throttle_calibration_cache",
    "get_default_usage_estimate_cache",
    "parse_codex_rate_limits_response",
    "to_topbar_quota",
    "unknown_topbar_quota",
]
