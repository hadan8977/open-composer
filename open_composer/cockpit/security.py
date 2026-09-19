"""Security helpers shared by every cockpit screen.

The cockpit is read-only and unauthenticated at the application layer (Cloudflare
Access handles auth at the edge -- see `AGENTS.md`). The two helpers in this module
are the compensating controls for the two ways a read-only app can still leak
something it should not:

* ``secret_scrub`` -- every piece of file-derived or log-derived text that reaches
  a Jinja2 template must be passed through this first, so an agent session log or
  a cron log tail can never render a live token even though the app never writes
  anything.
* ``safe_repo_path`` -- every relative path an operator can type into a URL (a
  card id, a report path, a log name) must be resolved through this before it
  touches the filesystem, so ``..`` or an absolute path can never escape the repo.

Both are exercised by ``tests/test_cockpit_app.py`` with table-driven cases; treat
that test as the contract when extending the pattern list.
"""

from __future__ import annotations

import re
from pathlib import Path

_MASK = "***REDACTED***"

# Each pattern captures (or matches) exactly the sensitive span so replacement can
# keep any surrounding text (e.g. "Authorization: Bearer sk-xxx" keeps the header
# name). Order matters: more specific patterns run before the generic
# key/token/secret/password assignment catch-all so we do not double-mask and
# mangle a boundary.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    # sk-... style API keys (OpenAI, Anthropic, and lookalikes). Anthropic keys are
    # "sk-ant-...", OpenAI keys are "sk-proj-..." or "sk-...": one pattern covers
    # all of them since they share the "sk-" prefix and are token-charset after it.
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    # "Bearer <token>" authorization headers.
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-.=]{8,}"),
    # Named environment variables that are always secrets regardless of value
    # shape, e.g. `CLAUDE_CODE_OAUTH_TOKEN=abc123` or `export OPENAI_API_KEY: xyz`.
    re.compile(
        r"\b(CLAUDE_CODE_OAUTH_TOKEN|OPENAI_API_KEY|ANTHROPIC_API_KEY|APCA_API_KEY_ID"
        r"|APCA_API_SECRET_KEY|APCA_API_[A-Z_]*KEY[A-Z_]*)\b\s*[:=]\s*\S+"
    ),
    # Generic `key` / `token` / `secret` / `password` assignments in any casing,
    # ini/env/json/yaml style (`FOO_TOKEN=...`, `"secret": "..."`, `password: ...`).
    re.compile(
        r"(?i)\b[\w.-]*(?:key|token|secret|password)[\w.-]*\b\s*[:=]\s*"
        r"(\"[^\"]+\"|'[^']+'|\S+)"
    ),
)


def secret_scrub(text: str) -> str:
    """Mask secret-shaped substrings in ``text`` before it reaches a template.

    This is a defense-in-depth regex scrub, not a guarantee of exhaustive secret
    detection -- it exists because the cockpit renders text it did not generate
    (cron log tails, agent session transcripts) and that text can legitimately
    contain a real credential if something upstream misbehaved. It always returns
    a string the same "shape" as the input with sensitive spans replaced by
    ``***REDACTED***``.
    """
    if not text:
        return text
    scrubbed = text
    for pattern in _PATTERNS:
        scrubbed = pattern.sub(_MASK, scrubbed)
    return scrubbed


class PathTraversalError(ValueError):
    """Raised when a requested relative path would escape the repo root."""


def safe_repo_path(rel: str, *, root: Path | None = None) -> Path:
    """Resolve ``rel`` to an absolute path inside the repo root, or raise.

    ``root`` defaults to :func:`open_composer.config.project_root`. Rejects
    absolute paths, ``..`` segments that climb above ``root``, and symlinks whose
    resolved target lands outside ``root`` (a symlink escape). The check is done
    on the fully resolved path (``Path.resolve()``, which follows symlinks) so a
    symlink planted inside the repo that points outside of it is caught the same
    way a literal ``../..`` would be.
    """
    from open_composer.config import project_root

    base = (root or project_root()).resolve()
    candidate = Path(rel)
    if candidate.is_absolute():
        raise PathTraversalError(f"absolute paths are not allowed: {rel!r}")

    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise PathTraversalError(f"path escapes repo root: {rel!r}") from exc
    return resolved
