#!/usr/bin/env python3
"""Preflight, lock and round log for the twice-daily autonomous research round.

A Paseo schedule starts a fresh agent (latest Opus at high effort) at 01:07 and
13:07 UTC, and that agent follows ``docs/runbook-autonomous-round.zh.md``. It
shares the owner's 5-hour quota, so a round only goes ahead when:

* no other round holds the lock (a crashed round's lock goes stale after
  ``--lock-max-hours``);
* no usage-limit reset is pending in the local transcripts;
* once the real Claude subscription quota can be read (T-20260927-04 budget
  plan A, owner-approved 2026-09-28): the 5h window is under 50%, and under
  30% if the owner is active, and the estimated background share of the
  rolling 7-day window is under 40%;
* only when that quota reading is unavailable does this fall back to the
  older owner-quiet gate: no Claude session that started before the grace
  window wrote a transcript line inside the quiet window.

    uv run python scripts/autonomous_preflight.py check
    uv run python scripts/autonomous_preflight.py wait-quiet --max-minutes 120
    uv run python scripts/autonomous_preflight.py acquire --agent-id <literal id>
    uv run python scripts/autonomous_preflight.py release
    uv run python scripts/autonomous_preflight.py log --status done --task T-... \\
        --summary "..." --usage-json '<release output>'

``acquire`` finds the round's own transcript by looking for the literal agent id
in recently written transcripts (the tool call that runs ``acquire`` is logged
before it executes), so ``release`` can report what this round and its
subagents consumed. Token counts are a lower bound read from local files, never
a subscription percentage. Every command prints one JSON object and exits 0;
the decision is in the JSON.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from open_composer.cockpit.data.quota import _bounded_tail_scan_usage, get_default_claude_cache

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "logs" / "autonomous" / "round.lock"
LOG_PATH = ROOT / "reports" / "research" / "control" / "autonomous-log.md"
QUOTA_CACHE_PATH = ROOT / "logs" / "autonomous" / "quota-cache.json"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
CAPPED_SLICE = Path("/sys/fs/cgroup/research.slice/research-capped.slice")
MARKER_SCAN_BYTES = 2_000_000

# Quota-gating thresholds (T-20260927-04 budget plan A, owner-approved 2026-09-28).
_FIVE_HOUR_MAX: Final[float] = 50.0
_FIVE_HOUR_OWNER_ACTIVE_MAX: Final[float] = 30.0
_BACKGROUND_WEEK_MAX: Final[float] = 40.0

# Shared on-disk quota cache (T-20260927-04 follow-up): the usage endpoint's
# rate limit is shared across every preflight process, the cockpit, and the
# owner's own sessions, so most rounds must not call it fresh.
_QUOTA_CACHE_FRESH_MINUTES: Final[float] = 10.0
_QUOTA_CACHE_STALE_MAX_MINUTES: Final[float] = 60.0

LOG_HEADER = (
    "# 自动研究轮日志\n\n"
    "每行一轮，由 `scripts/autonomous_preflight.py log` 追加，跳过的轮也记。"
    "用量来自本机会话记录：本轮会话及其子代理的 fresh token（输入 + 缓存写入 + 输出），"
    "是下限，不是订阅百分比。执行手册：`docs/runbook-autonomous-round.zh.md`。\n\n"
    "| 开始 (UTC) | 结束 (UTC) | 状态 | 任务 | 摘要 | fresh / cache-read tokens |\n"
    "|---|---|---|---|---|---|\n"
)


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def first_timestamp(path: Path, max_lines: int = 50) -> datetime | None:
    """Timestamp of the first timestamped line: when the session started."""
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= max_lines:
                    break
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    ts = _parse_ts(row.get("timestamp"))
                    if ts is not None:
                        return ts
    except OSError:
        return None
    return None


@dataclass(frozen=True)
class SessionActivity:
    path: str
    started_at: str | None
    last_write: str


def owner_activity(
    projects_dir: Path, now: datetime, quiet_minutes: float, grace_minutes: float
) -> list[SessionActivity]:
    """Sessions that started before the grace window and wrote inside the quiet window.

    A session that started inside the grace window is skipped: at preflight
    time that is almost always the round itself.
    """
    active: list[SessionActivity] = []
    if not projects_dir.is_dir():
        return active
    quiet_cutoff = now - timedelta(minutes=quiet_minutes)
    grace_cutoff = now - timedelta(minutes=grace_minutes)
    for path in projects_dir.glob("*/*.jsonl"):
        try:
            last_write = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        except OSError:
            continue
        if last_write < quiet_cutoff:
            continue
        started = first_timestamp(path)
        if started is not None and started > grace_cutoff:
            continue
        active.append(
            SessionActivity(
                path=str(path),
                started_at=started.isoformat() if started else None,
                last_write=last_write.isoformat(),
            )
        )
    return sorted(active, key=lambda item: item.last_write, reverse=True)


def read_lock(path: Path) -> dict[str, Any] | None:
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return lock if isinstance(lock, dict) else None


def lock_is_fresh(lock: dict[str, Any], now: datetime, max_hours: float) -> bool:
    started = _parse_ts(lock.get("started_at"))
    return started is not None and now - started < timedelta(hours=max_hours)


def usage_state() -> dict[str, Any]:
    """The autonomy controller's transcript-based reader (no OAuth probe)."""
    try:
        from open_composer.research.autonomy import usage_snapshot

        return usage_snapshot()
    except Exception as exc:  # a broken reader must not block the round
        return {"error": f"{type(exc).__name__}: {exc}"}


_QUOTA_FIELD_KEYS: Final[tuple[str, ...]] = (
    "five_hour_percent",
    "seven_day_percent",
    "five_hour_resets_at",
    "seven_day_resets_at",
)


class _QuotaUnavailable(RuntimeError):
    """The live quota reader has nothing usable this round; ``str()`` is the reason."""


def _empty_quota_fields() -> dict[str, Any]:
    return dict.fromkeys(_QUOTA_FIELD_KEYS)


def _read_quota_live() -> dict[str, Any]:
    """Exactly one call through the cockpit's own quota cache/breaker.

    Raises `_QuotaUnavailable` (message = the snapshot's own reason, e.g.
    ``"http 4xx/5xx"`` for a 429) when the snapshot itself is not available,
    so every failure -- network, breaker-open, or unavailable snapshot --
    reaches `quota_state`'s cache-fallback logic the same way.
    """
    report = get_default_claude_cache().get(now=_now())
    if not report.snapshot.available:
        raise _QuotaUnavailable(report.snapshot.unavailable_reason or "unavailable")
    by_key = {window.key: window for window in report.snapshot.windows}
    fields = _empty_quota_fields()
    for window_key in ("five_hour", "seven_day"):
        window = by_key.get(window_key)
        if window is None:
            continue
        fields[f"{window_key}_percent"] = window.percent_used
        fields[f"{window_key}_resets_at"] = (
            window.resets_at.isoformat() if window.resets_at is not None else None
        )
    return fields


def _read_quota_cache_file(cache_path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def _write_quota_cache_file(cache_path: Path, fields: dict[str, Any], *, now: datetime) -> None:
    # Only the four numeric/ISO fields plus provenance -- never tokens or a response body.
    payload = {key: fields.get(key) for key in _QUOTA_FIELD_KEYS}
    payload["fetched_at"] = now.isoformat()
    payload["source"] = "live"
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    except OSError:  # a cache write failure must not block the round
        pass


def quota_state(
    *, now: datetime | None = None, cache_path: Path = QUOTA_CACHE_PATH
) -> dict[str, Any]:
    """Real Claude subscription usage, shared on disk so every process shares one rate limit.

    T-20260927-04 budget plan A: the usage endpoint's rate limit is shared
    across every preflight process, the cockpit, and the owner's own
    sessions, so a fresh network call is not made every time this runs:

    * a cached reading younger than `_QUOTA_CACHE_FRESH_MINUTES` is reused
      with no network call at all;
    * otherwise `_read_quota_live` is called exactly once. On success the
      cache file is refreshed. On failure, a last-good cached reading
      younger than `_QUOTA_CACHE_STALE_MAX_MINUTES` is reused and marked
      `stale: True` with `age_minutes` -- a stale reading still drives the
      budget gate in `decide()`. Older than that (or no cache at all),
      every field is `None` and `quota_error` names the failure.

    Delegates entirely to the cockpit's own `open_composer.cockpit.data.quota`
    module -- never reads credentials or probes the network itself; the
    cache file it maintains holds only the four numeric/ISO fields plus
    `fetched_at`/`source`, never tokens or a response body.
    """
    moment = now or _now()
    cached = _read_quota_cache_file(cache_path)
    cached_fetched_at = _parse_ts(cached.get("fetched_at")) if cached else None
    cached_age_minutes = (
        (moment - cached_fetched_at).total_seconds() / 60.0
        if cached_fetched_at is not None
        else None
    )
    if (
        cached is not None
        and cached_age_minutes is not None
        and 0 <= cached_age_minutes < _QUOTA_CACHE_FRESH_MINUTES
    ):
        return {key: cached.get(key) for key in _QUOTA_FIELD_KEYS}

    try:
        fields = _read_quota_live()
    except Exception as exc:  # a broken reader must not block the round
        if (
            cached is not None
            and cached_age_minutes is not None
            and 0 <= cached_age_minutes < _QUOTA_CACHE_STALE_MAX_MINUTES
        ):
            result = {key: cached.get(key) for key in _QUOTA_FIELD_KEYS}
            result["stale"] = True
            result["age_minutes"] = round(cached_age_minutes, 1)
            return result
        result = _empty_quota_fields()
        result["quota_error"] = (
            str(exc) if isinstance(exc, _QuotaUnavailable) else type(exc).__name__
        )
        return result

    _write_quota_cache_file(cache_path, fields, now=moment)
    return fields


def _parse_log_fresh_tokens(cell: str) -> int:
    """The fresh-token half of a round-log cell like ``"123,456 / 7"`` (or ``"n/a"`` -> 0)."""
    first = cell.split("/", 1)[0].strip().replace(",", "")
    try:
        return int(first)
    except ValueError:
        return 0


def round_tokens_since(log_path: Path, since: datetime) -> int:
    """Fresh tokens booked by autonomous rounds (any status, `skipped` included) since ``since``.

    Parses the markdown table `scripts/autonomous_preflight.py log` appends
    to (`reports/research/control/autonomous-log.md`): columns are start,
    end, status, task, summary, ``"fresh / cache-read tokens"``.
    """
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError:
        return 0
    total = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|---"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) != 6:
            continue
        started = _parse_ts(cells[0])
        if started is None or started < since:
            continue
        total += _parse_log_fresh_tokens(cells[5])
    return total


def total_local_fresh_tokens_since(projects_dir: Path, since: datetime) -> int:
    """Fresh tokens (input + cache-creation + output) across every local transcript since ``since``.

    Covers every main session under ``projects_dir`` plus its subagents,
    deduped by message id per file (mirrors `session_usage`'s scan). This is
    the denominator for `background_week_percent_est` -- the numerator,
    round-attributed tokens, is a subset of this same measure.
    """
    if not projects_dir.is_dir():
        return 0
    total = 0
    for main_path in sorted(projects_dir.glob("*/*.jsonl")):
        files = [main_path, *sorted((main_path.parent / main_path.stem).glob("subagents/*.jsonl"))]
        for path in files:
            try:
                messages, _sessions, _truncated = _bounded_tail_scan_usage(path, since)
            except OSError:
                continue
            for record in messages.values():
                total += record.input_tokens + record.output_tokens + record.cache_creation_tokens
    return total


def estimate_background_week_percent(
    quota: dict[str, Any],
    *,
    now: datetime,
    log_path: Path = LOG_PATH,
    projects_dir: Path = PROJECTS_DIR,
) -> float:
    """Autonomous rounds' estimated share of the owner's rolling 7-day Claude budget.

    A fresh-token proxy, not the provider's own cost-weighted usage metric:
    it assumes the round's tokens cost the same per token as the rest of the
    owner's week (model mix and cache reuse differ by session, so this is
    only an estimate, not an audited cost share). Returns 0.0 whenever the
    inputs cannot support an estimate: no `seven_day_percent`/`resets_at`,
    `seven_day_percent < 1`, or no local usage recorded in the window.
    """
    seven_day_percent = quota.get("seven_day_percent")
    resets_raw = quota.get("seven_day_resets_at")
    if seven_day_percent is None or resets_raw is None or seven_day_percent < 1:
        return 0.0
    resets_at = _parse_ts(resets_raw)
    if resets_at is None:
        return 0.0
    week_start = resets_at - timedelta(days=7)
    all_tokens = total_local_fresh_tokens_since(projects_dir, week_start)
    if all_tokens == 0:
        return 0.0
    round_tokens = round_tokens_since(log_path, week_start)
    return round(round_tokens / (all_tokens / seven_day_percent), 4)


def budget_object(quota: dict[str, Any], background_week_est: float) -> dict[str, Any]:
    """The `budget` object printed by `check` and `acquire` (T-20260927-04 budget plan A)."""
    return {
        "five_hour_percent": quota.get("five_hour_percent"),
        "seven_day_percent": quota.get("seven_day_percent"),
        "background_week_percent_est": background_week_est,
        "thresholds": {
            "five_hour_max": _FIVE_HOUR_MAX,
            "five_hour_owner_active_max": _FIVE_HOUR_OWNER_ACTIVE_MAX,
            "background_week_max": _BACKGROUND_WEEK_MAX,
        },
    }


def decide(
    *,
    now: datetime,
    lock: dict[str, Any] | None,
    lock_max_hours: float,
    usage: dict[str, Any],
    activity: list[SessionActivity],
    quota: dict[str, Any] | None = None,
    background_week_percent_est: float | None = None,
) -> tuple[str, list[str]]:
    """Go/skip verdict. Precedence (T-20260927-04 budget plan A, owner-approved 2026-09-28):

    1. a fresh lock always wins (`skip_round_running`);
    2. an active or unrecorded throttle event always wins (`skip_rate_limited`);
    3. once both quota percents are known: 5h >= 50% skips; owner active and
       5h >= 30% skips; estimated background weekly share >= 40% skips;
       otherwise go, even if the owner is active -- the quota gate replaces
       the plain owner-quiet gate once quota is available;
    4. quota unavailable: fall back to the pre-budget-plan behaviour (owner
       active -> `wait_owner_active`, else `go`).
    """
    if lock is not None and lock_is_fresh(lock, now, lock_max_hours):
        return "skip_round_running", [
            f"lock held since {lock.get('started_at')} by {lock.get('agent_id')}"
        ]
    retry_after = _parse_ts(usage.get("retry_after"))
    if retry_after is not None and retry_after > now:
        return "skip_rate_limited", [f"usage limit resets at {retry_after.isoformat()}"]
    if usage.get("unknown_throttle_reset"):
        return "skip_rate_limited", [
            "a usage limit was hit in the last 5 hours and no reset time was recorded"
        ]

    quota = quota or {}
    five_hour = quota.get("five_hour_percent")
    seven_day = quota.get("seven_day_percent")
    if five_hour is not None and seven_day is not None:
        if five_hour >= _FIVE_HOUR_MAX:
            return "skip_quota", [f"5h window >= {_FIVE_HOUR_MAX:.0f}% ({five_hour:.1f}%)"]
        if activity and five_hour >= _FIVE_HOUR_OWNER_ACTIVE_MAX:
            return "skip_quota", [
                f"owner active and 5h >= {_FIVE_HOUR_OWNER_ACTIVE_MAX:.0f}% ({five_hour:.1f}%)"
            ]
        if (
            background_week_percent_est is not None
            and background_week_percent_est >= _BACKGROUND_WEEK_MAX
        ):
            return "skip_quota", [
                "background weekly share >= "
                f"{_BACKGROUND_WEEK_MAX:.0f}% ({background_week_percent_est:.1f}%)"
            ]
        reasons = []
        if lock is not None:
            reasons.append(f"stale lock from {lock.get('started_at')} ignored")
        return "go", reasons

    if activity:
        return "wait_owner_active", [
            f"{len(activity)} session(s) wrote in the quiet window; "
            f"latest at {activity[0].last_write}"
        ]
    reasons = []
    if lock is not None:
        reasons.append(f"stale lock from {lock.get('started_at')} ignored")
    return "go", reasons


def git_state(root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=60, check=False
        )
        return done.stdout

    dirty = [line[3:] for line in run("status", "--porcelain").splitlines() if line.strip()]
    return {
        "branch": run("rev-parse", "--abbrev-ref", "HEAD").strip(),
        "head": run("log", "-1", "--format=%h %s").strip(),
        "dirty_count": len(dirty),
        "dirty": dirty[:40],
    }


def heavy_jobs(slice_dir: Path = CAPPED_SLICE) -> int:
    try:
        return sum(1 for path in slice_dir.glob("run-*.scope") if path.is_dir())
    except OSError:
        return 0


def check_report(args: argparse.Namespace) -> dict[str, Any]:
    now = _now()
    lock = read_lock(LOCK_PATH)
    usage = usage_state()
    quota = quota_state()
    background_est = estimate_background_week_percent(quota, now=now)
    activity = owner_activity(PROJECTS_DIR, now, args.quiet_minutes, args.grace_minutes)
    decision, reasons = decide(
        now=now,
        lock=lock,
        lock_max_hours=args.lock_max_hours,
        usage=usage,
        activity=activity,
        quota=quota,
        background_week_percent_est=background_est,
    )
    return {
        "now": now.isoformat(),
        "decision": decision,
        "reasons": reasons,
        "owner_sessions": [asdict(item) for item in activity[:5]],
        "lock": lock,
        "usage": usage,
        "quota": quota,
        "budget": budget_object(quota, background_est),
        "heavy_jobs_running": heavy_jobs(),
        "git": git_state(ROOT),
    }


def find_session_by_marker(projects_dir: Path, marker: str, since: datetime) -> Path | None:
    """The most recently started transcript, written since ``since``, containing ``marker``.

    Another session can contain the marker too (someone typed the round's
    agent id there), but it started earlier than the round itself.
    """
    needle = marker.encode("utf-8")
    matches: list[tuple[datetime, Path]] = []
    for path in projects_dir.glob("*/*.jsonl"):
        try:
            stat = path.stat()
            if datetime.fromtimestamp(stat.st_mtime, UTC) < since:
                continue
            with path.open("rb") as handle:
                handle.seek(max(0, stat.st_size - MARKER_SCAN_BYTES))
                if needle not in handle.read():
                    continue
        except OSError:
            continue
        started = first_timestamp(path) or datetime.min.replace(tzinfo=UTC)
        matches.append((started, path))
    return max(matches)[1] if matches else None


def session_usage(session_file: Path, since: datetime) -> dict[str, Any]:
    """Token use of one session and its subagents from ``since`` on."""
    files = [
        session_file,
        *sorted((session_file.parent / session_file.stem).glob("subagents/*.jsonl")),
    ]
    totals = {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0}
    by_model: dict[str, int] = {}
    for path in files:
        messages, _sessions, _truncated = _bounded_tail_scan_usage(path, since)
        for record in messages.values():
            totals["input"] += record.input_tokens
            totals["output"] += record.output_tokens
            totals["cache_creation"] += record.cache_creation_tokens
            totals["cache_read"] += record.cache_read_tokens
            fresh = record.input_tokens + record.output_tokens + record.cache_creation_tokens
            by_model[record.model] = by_model.get(record.model, 0) + fresh
    return {
        "since": since.isoformat(),
        "files": len(files),
        "fresh_tokens": totals["input"] + totals["output"] + totals["cache_creation"],
        "cache_read_tokens": totals["cache_read"],
        "output_tokens": totals["output"],
        "fresh_by_model": by_model,
    }


def acquire(args: argparse.Namespace) -> dict[str, Any]:
    now = _now()
    lock = read_lock(LOCK_PATH)
    quota = quota_state()
    background_est = estimate_background_week_percent(quota, now=now)
    budget = budget_object(quota, background_est)
    if lock is not None and lock_is_fresh(lock, now, args.lock_max_hours):
        return {
            "acquired": False,
            "reason": "another round holds the lock",
            "lock": lock,
            "quota": quota,
            "budget": budget,
        }
    session = find_session_by_marker(PROJECTS_DIR, args.agent_id, now - timedelta(minutes=10))
    started = first_timestamp(session) if session else None
    new_lock = {
        "started_at": now.isoformat(),
        "agent_id": args.agent_id,
        "session_file": str(session) if session else None,
        "session_started_at": started.isoformat() if started else None,
        "stale_lock_replaced": lock,
    }
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(new_lock, indent=1) + "\n", encoding="utf-8")
    return {"acquired": True, "lock": new_lock, "quota": quota, "budget": budget}


def release(_args: argparse.Namespace) -> dict[str, Any]:
    now = _now()
    lock = read_lock(LOCK_PATH)
    if lock is None:
        return {"released": False, "reason": "no lock held"}
    started = _parse_ts(lock.get("started_at")) or now
    result: dict[str, Any] = {
        "released": True,
        "started_at": started.isoformat(),
        "ended_at": now.isoformat(),
        "minutes": round((now - started).total_seconds() / 60.0, 1),
        "usage": None,
    }
    session_file = lock.get("session_file")
    if session_file and Path(session_file).is_file():
        since = _parse_ts(lock.get("session_started_at")) or started
        try:
            result["usage"] = session_usage(Path(session_file), since)
        except Exception as exc:  # report, never fail the release
            result["usage_error"] = f"{type(exc).__name__}: {exc}"
    else:
        result["usage_error"] = "round transcript not identified at acquire"
    LOCK_PATH.unlink(missing_ok=True)
    return result


def _cell(text: Any) -> str:
    return str(text if text is not None else "").replace("|", "/").replace("\n", " ").strip()


def append_log(args: argparse.Namespace) -> dict[str, Any]:
    usage_blob: dict[str, Any] = {}
    if args.usage_json:
        raw = args.usage_json
        if raw.startswith("@"):
            raw = Path(raw[1:]).read_text(encoding="utf-8")
        try:
            usage_blob = json.loads(raw)
        except ValueError:
            usage_blob = {}
    usage = usage_blob.get("usage") or {}
    tokens = (
        f"{usage.get('fresh_tokens', 0):,} / {usage.get('cache_read_tokens', 0):,}"
        if usage
        else "n/a"
    )
    now = _now()
    started = usage_blob.get("started_at") or args.started or now.isoformat()
    ended = usage_blob.get("ended_at") or now.isoformat()
    row = (
        f"| {_cell(started[:16])} | {_cell(ended[:16])} | {_cell(args.status)} | "
        f"{_cell(args.task)} | {_cell(args.summary)} | {tokens} |\n"
    )
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        LOG_PATH.write_text(LOG_HEADER, encoding="utf-8")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(row)
    return {"logged": True, "path": str(LOG_PATH.relative_to(ROOT)), "row": row.strip()}


def wait_quiet(args: argparse.Namespace) -> dict[str, Any]:
    deadline = time.monotonic() + args.max_minutes * 60
    report = check_report(args)
    while report["decision"] == "wait_owner_active" and time.monotonic() < deadline:
        time.sleep(max(1.0, args.poll_minutes * 60))
        report = check_report(args)
    if report["decision"] == "wait_owner_active":
        report["decision"] = "skip_owner_active"
        report["reasons"].append(f"owner still active after {args.max_minutes} minutes")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def gate_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--quiet-minutes", type=float, default=15.0)
        p.add_argument("--grace-minutes", type=float, default=10.0)
        p.add_argument("--lock-max-hours", type=float, default=4.0)

    gate_options(sub.add_parser("check", help="decide go / wait / skip"))
    wait = sub.add_parser("wait-quiet", help="re-check until the owner is quiet")
    gate_options(wait)
    wait.add_argument("--max-minutes", type=float, default=120.0)
    wait.add_argument("--poll-minutes", type=float, default=10.0)
    take = sub.add_parser("acquire", help="take the round lock")
    take.add_argument("--agent-id", required=True, help="literal Paseo agent id")
    take.add_argument("--lock-max-hours", type=float, default=4.0)
    sub.add_parser("release", help="drop the lock and report this round's usage")
    log = sub.add_parser("log", help="append one row to the round log")
    log.add_argument("--status", required=True, choices=["done", "partial", "failed", "skipped"])
    log.add_argument("--task", default="-")
    log.add_argument("--summary", required=True)
    log.add_argument("--usage-json", default="", help="release output, inline or @file")
    log.add_argument("--started", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "check": check_report,
        "wait-quiet": wait_quiet,
        "acquire": acquire,
        "release": release,
        "log": append_log,
    }
    print(json.dumps(handlers[args.command](args), ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
