#!/usr/bin/env python3
"""Keep the scheduled research rounds from launching into a Claude usage limit.

Each run of the Paseo lead/exec schedules starts a new agent. While the account is
limited, that agent's first model call is rejected, so the round's own preflight never
runs. From 2026-10-02 08:48 to 2026-10-03 22:07, 12 runs ended within seconds on
"You've hit your ... limit". The first of them (five-hour limit) died holding the round
lock, so the 10:07 exec round skipped. This gate runs from cron with no model call and
no credential:

1. **Limit.** A ``quotaLimits`` rejection in a recent local transcript (a round, a
   subagent or the interactive session) whose ``resetsAt`` is still ahead pauses the
   round schedules until that reset plus a margin. A model-specific limit
   (``..._opus``, ``..._sonnet``) pauses only the schedules on that model.
2. **Weekly pace.** Owner 2026-09-29: no quota API, keep a rough self-count. This
   week's usage is priced from the transcripts' token counts and compared with a cap
   calibrated on the week the weekly limit was hit. The rounds pause while the week
   is ahead of an even pace (plus slack) or past the owner reserve, and resume once
   back on pace.
3. **Dead lock.** A round lock whose holder agent no longer runs is moved aside, so
   the next round does not skip for up to the preflight's ``--lock-max-hours``.

It resumes only schedules it paused itself, so a manual pause stays paused. One pass
per call; it prints only when it acts.

    .venv/bin/python scripts/round_limit_gate.py run [--dry-run]
    .venv/bin/python scripts/round_limit_gate.py status
    .venv/bin/python scripts/round_limit_gate.py calibrate --at 2026-10-02T14:19:27Z
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from open_composer.cockpit.data.quota import _all_quota_events_in_file

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "autonomous-round-gate.json"
STATE_DIR = ROOT / "logs" / "autonomous"
STATE_PATH = STATE_DIR / "round-gate-state.json"
STATUS_PATH = STATE_DIR / "round-gate-status.json"
LEDGER_PATH = STATE_DIR / "usage-ledger.json"
LOG_PATH = STATE_DIR / "round-gate.log"
LOCK_PATH = STATE_DIR / "round.lock"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
PASEO_FALLBACK = Path("/root/.hermes/node/bin/paseo")
FAMILIES = ("opus", "sonnet", "haiku", "fable")
READ_BLOCK = 8 << 20
RECENT_IDS = 200
UNKNOWN_RESET_HOURS = 5.0
ALIVE = {"running", "initializing"}


def _ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        out = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return out if out.tzinfo else out.replace(tzinfo=UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _iso_ms(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds")


def _load(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return data if isinstance(data, dict) else default


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def transcript_files(projects_dir: Path, since: datetime) -> list[Path]:
    """Top-level and subagent transcripts modified since ``since``, newest first."""
    found: list[tuple[float, Path]] = []
    for path in [*projects_dir.glob("*/*.jsonl"), *projects_dir.glob("*/*/subagents/*.jsonl")]:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= since.timestamp():
            found.append((mtime, path))
    return [path for _, path in sorted(found, key=lambda item: item[0], reverse=True)]


# --- 1. active limits ----------------------------------------------------------------


@dataclass(frozen=True)
class Limit:
    kind: str
    until: datetime
    seen_at: datetime | None
    source: str


def active_limits(
    projects_dir: Path,
    now: datetime,
    *,
    margin: timedelta,
    last_success: dict[str, str] | None = None,
    max_files: int = 60,
) -> list[Limit]:
    """Rejections whose reset (plus margin) is still ahead, from the newest transcripts.

    A successful call of a model the limit binds, made after the rejection, means the
    limit was lifted early (the owner used a reset): that rejection no longer counts.
    """
    successes = {k: _ts(v) for k, v in (last_success or {}).items()}
    out: list[Limit] = []
    for path in transcript_files(projects_dir, now - timedelta(days=8))[:max_files]:
        for event in _all_quota_events_in_file(path):
            if event.status != "rejected":
                continue
            resets = event.resets_at
            if resets is None and event.at is not None:
                resets = event.at + timedelta(hours=UNKNOWN_RESET_HOURS)
            if resets is None or resets + margin <= now:
                continue
            kind = event.rate_limit_type or "unknown"
            lifted = event.at is not None and any(
                ok is not None and ok > event.at + timedelta(seconds=1) and limit_applies(kind, f)
                for f, ok in successes.items()
            )
            if not lifted:
                out.append(Limit(kind, resets + margin, event.at, path.name))
    return out


def limit_applies(kind: str, family: str) -> bool:
    """A model-specific limit (``seven_day_opus``) binds only that model's schedules."""
    named = [f for f in FAMILIES if f in kind.lower()]
    return not named or family in named


# --- 2. weekly pace ------------------------------------------------------------------


def week_start(now: datetime, anchor: datetime) -> datetime:
    return anchor + ((now - anchor) // timedelta(days=7)) * timedelta(days=7)


def model_family(model: Any) -> str | None:
    text = str(model or "").lower()
    return next((f for f in FAMILIES if f in text), None)


def price(usage: dict[str, Any], weights: list[float]) -> float:
    """USD-equivalent at list-price ratios; only ratios matter, the cap is calibrated."""
    w_in, w_write, w_read, w_out = weights
    return (
        float(usage.get("input_tokens") or 0) * w_in
        + float(usage.get("cache_creation_input_tokens") or 0) * w_write
        + float(usage.get("cache_read_input_tokens") or 0) * w_read
        + float(usage.get("output_tokens") or 0) * w_out
    ) / 1e6


def classify(path: Path, projects_dir: Path) -> str:
    """``round`` or ``interactive``, with ``_subagents`` for files under subagents/."""
    rel = path.relative_to(projects_dir).parts
    top = projects_dir / rel[0] / f"{rel[1]}.jsonl" if "subagents" in rel else path
    kind = "interactive"
    try:
        with top.open(encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index > 40:
                    break
                if '"type":"user"' in line:
                    kind = "round" if "自动研究" in line else "interactive"
                    break
    except OSError:
        pass
    return f"{kind}_subagents" if "subagents" in rel else kind


def _lines(path: Path, offset: int) -> Iterator[tuple[bytes, int]]:
    """Complete lines from ``offset`` on, each with the offset just past it."""
    with path.open("rb") as handle:
        handle.seek(offset)
        carry = b""
        while True:
            block = handle.read(READ_BLOCK)
            if not block:
                return
            data = carry + block
            cut = data.rfind(b"\n")
            if cut < 0:
                carry = data
                continue
            position = offset
            for raw in data[: cut + 1].split(b"\n")[:-1]:
                position += len(raw) + 1
                yield raw, position
            offset = position
            carry = data[cut + 1 :]


def update_ledger(
    ledger: dict[str, Any],
    projects_dir: Path,
    now: datetime,
    *,
    anchor: datetime,
    weights: dict[str, list[float]],
) -> dict[str, Any]:
    """Add the new transcript lines since the last pass to this week's usage."""
    start = week_start(now, anchor)
    if ledger.get("week_start") != _iso(start):
        ledger = {"week_start": _iso(start), "files": {}, "units": {}, "total": 0.0}
    files: dict[str, Any] = ledger["files"]
    for path in transcript_files(projects_dir, start):
        key = str(path)
        entry = files.get(key)
        if entry is None:
            entry = files[key] = {
                "offset": 0,
                "recent": {},
                "kind": classify(path, projects_dir),
            }
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size < entry["offset"]:  # rewritten file: count it again from the start
            entry["offset"], entry["recent"] = 0, {}
        recent: dict[str, float] = entry["recent"]
        for raw, end in _lines(path, entry["offset"]):
            if b'"usage"' in raw and b'"assistant"' in raw:
                _count(raw, ledger, entry["kind"], recent, start, now, weights)
            entry["offset"] = end
        if len(recent) > RECENT_IDS:
            entry["recent"] = dict(list(recent.items())[-RECENT_IDS:])
    ledger["updated_at"] = _iso(now)
    return ledger


def _count(
    raw: bytes,
    ledger: dict[str, Any],
    kind: str,
    recent: dict[str, float],
    start: datetime,
    now: datetime,
    weights: dict[str, list[float]],
) -> None:
    try:
        row = json.loads(raw)
    except ValueError:
        return
    if not isinstance(row, dict) or row.get("type") != "assistant":
        return
    moment = _ts(row.get("timestamp"))
    message = row.get("message") or {}
    usage = message.get("usage") if isinstance(message, dict) else None
    family = model_family(message.get("model")) if isinstance(message, dict) else None
    if moment is None or not (start <= moment <= now) or not usage or family is None:
        return
    last = ledger.setdefault("last_success", {})
    previous = _ts(last.get(family))
    if previous is None or moment > previous:
        last[family] = _iso_ms(moment)
    units = price(usage, weights.get(family, weights["opus"]))
    key = str(message.get("id") or row.get("uuid"))
    # Claude Code writes one line per content block with the same message id and usage.
    delta = max(0.0, units - recent.get(key, 0.0))
    recent[key] = max(units, recent.get(key, 0.0))
    if delta:
        ledger["units"][kind] = ledger["units"].get(kind, 0.0) + delta
        ledger["total"] = ledger.get("total", 0.0) + delta


def pace_check(
    total: float, now: datetime, start: datetime, cfg: dict[str, Any], *, paused: bool
) -> dict[str, Any]:
    """Rounds may run while the week is on an even pace and below the owner reserve.

    Hysteresis: once paused for pace, resume only below the pace line itself.
    """
    resets = int((cfg.get("extra_resets_by_week") or {}).get(_iso(start), 0))
    cap = float(cfg["weekly_cap_units"]) * (1 + resets)
    fraction = min(1.0, max(0.0, (now - start) / timedelta(days=7)))
    pace = cap * fraction
    reserve_line = (1.0 - float(cfg["owner_reserve"])) * cap
    if paused:
        allowed = total <= pace and total <= reserve_line - 0.02 * cap
    else:
        allowed = total <= pace + float(cfg["pace_slack"]) * cap and total <= reserve_line
    return {
        "allowed": allowed,
        "used_units": round(total, 1),
        "pace_units": round(pace, 1),
        "cap_units": cap,
        "extra_resets": resets,
        "used_share": round(total / cap, 3),
        "week_elapsed": round(fraction, 3),
    }


# --- Paseo ---------------------------------------------------------------------------


class Paseo(Protocol):
    def schedules(self) -> list[dict[str, Any]]: ...
    def pause(self, schedule_id: str) -> None: ...
    def resume(self, schedule_id: str) -> None: ...
    def agent_status(self, agent_id: str) -> str | None: ...


class PaseoCli:
    """The local ``paseo`` CLI. Never prints its output; errors carry the exit code only."""

    # `paseo schedule ls` took ~33 s on 2026-10-04 and the old 30 s limit killed every
    # gate run from 12:20 UTC on; three calls x 75 s still fit inside the cron's `timeout 240`.
    def __init__(self, timeout: float = 75.0) -> None:
        found = shutil.which("paseo")
        exe = found or (str(PASEO_FALLBACK) if PASEO_FALLBACK.exists() else None)
        if exe is None:
            raise RuntimeError("paseo CLI not found")
        self._exe = exe
        self._timeout = timeout
        self._env = dict(os.environ)  # cron's PATH lacks node; the CLI sits next to it
        self._env["PATH"] = f"{Path(exe).parent}:{self._env.get('PATH', '')}"

    def _run(self, *args: str) -> str:
        done = subprocess.run(
            [self._exe, *args],
            capture_output=True,
            text=True,
            timeout=self._timeout,
            env=self._env,
            check=False,
        )
        if done.returncode != 0:
            raise RuntimeError(f"paseo {' '.join(args[:2])} exited {done.returncode}")
        return done.stdout

    def schedules(self) -> list[dict[str, Any]]:
        data = json.loads(self._run("schedule", "ls", "--json"))
        return data if isinstance(data, list) else []

    def pause(self, schedule_id: str) -> None:
        self._run("schedule", "pause", schedule_id)

    def resume(self, schedule_id: str) -> None:
        self._run("schedule", "resume", schedule_id)

    def agent_status(self, agent_id: str) -> str | None:
        try:
            data = json.loads(self._run("inspect", agent_id, "--json"))
        except Exception:  # unknown agent or daemon down: leave the lock alone
            return None
        if not isinstance(data, dict):
            return None
        if data.get("Archived"):
            return "archived"
        status = data.get("Status")
        return str(status) if status else None


# --- one pass ------------------------------------------------------------------------


def run_once(
    now: datetime,
    cfg: dict[str, Any],
    paseo: Paseo,
    *,
    projects_dir: Path = PROJECTS_DIR,
    state_path: Path = STATE_PATH,
    ledger_path: Path = LEDGER_PATH,
    status_path: Path = STATUS_PATH,
    lock_path: Path = LOCK_PATH,
    log_path: Path = LOG_PATH,
    dry_run: bool = False,
) -> dict[str, Any]:
    margin = timedelta(minutes=float(cfg.get("resume_margin_minutes", 2)))
    anchor = _ts(cfg["week_anchor_utc"])
    assert anchor is not None
    state = _load(state_path, {})
    gate_paused: dict[str, Any] = state.setdefault("paused_by_gate", {})
    ledger = update_ledger(
        _load(ledger_path, {}), projects_dir, now, anchor=anchor, weights=cfg["weights"]
    )
    limits = active_limits(
        projects_dir, now, margin=margin, last_success=ledger.get("last_success")
    )
    start = week_start(now, anchor)
    pace = pace_check(
        float(ledger.get("total", 0.0)), now, start, cfg, paused=bool(state.get("pace_paused"))
    )
    actions: list[str] = []
    weekly = [lim for lim in limits if lim.kind.startswith("seven_day")]
    if weekly and state.get("cap_observed_week") != _iso(start):
        state["cap_observed_week"] = _iso(start)
        state["cap_observed_units"] = pace["used_units"]
        actions.append(
            f"weekly limit seen at {pace['used_units']} units (config cap {pace['cap_units']})"
        )
    current = {str(s.get("id")): s for s in paseo.schedules()}
    for schedule_id, family in cfg["schedules"].items():
        binding = [lim for lim in limits if limit_applies(lim.kind, family)]
        reasons = []
        if binding:
            until = max(lim.until for lim in binding)
            kinds = ",".join(sorted({lim.kind for lim in binding}))
            reasons.append(f"limit {kinds} until {_iso(until)}")
        if not pace["allowed"]:
            reasons.append(
                f"pace: used {pace['used_units']} > allowed at {pace['pace_units']} "
                f"(cap {pace['cap_units']})"
            )
        status = (current.get(schedule_id) or {}).get("status")
        if reasons and status == "active":
            if not dry_run:
                paseo.pause(schedule_id)
            gate_paused[schedule_id] = {"at": _iso(now), "reasons": reasons}
            actions.append(f"pause {schedule_id}: {'; '.join(reasons)}")
        elif reasons and schedule_id in gate_paused:
            gate_paused[schedule_id]["reasons"] = reasons
        elif not reasons and schedule_id in gate_paused:
            if status == "paused" and not dry_run:
                paseo.resume(schedule_id)
            del gate_paused[schedule_id]
            actions.append(
                f"resume {schedule_id}" if status == "paused" else f"forget {schedule_id}"
            )
    state["pace_paused"] = not pace["allowed"]
    actions.extend(clear_dead_lock(lock_path, paseo, now, dry_run=dry_run))
    summary = {
        "checked_at": _iso(now),
        "limits": [
            {"kind": lim.kind, "until": _iso(lim.until), "source": lim.source} for lim in limits
        ],
        "pace": pace,
        "usage_by_kind": {k: round(v, 1) for k, v in sorted(ledger["units"].items())},
        "paused_by_gate": sorted(gate_paused),
        "actions": actions,
        "dry_run": dry_run,
    }
    if not dry_run:
        _save(ledger_path, ledger)
        _save(state_path, state)
        _save(status_path, summary)
        if actions:
            with log_path.open("a", encoding="utf-8") as log:
                for action in actions:
                    log.write(f"{_iso(now)} {action}\n")
    return summary


def clear_dead_lock(lock_path: Path, paseo: Paseo, now: datetime, *, dry_run: bool) -> list[str]:
    lock = _load(lock_path, {}) if lock_path.exists() else {}
    agent_id = lock.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        return []
    status = paseo.agent_status(agent_id)
    if status is None or status in ALIVE:
        return []
    if not dry_run:
        os.replace(lock_path, lock_path.with_name(lock_path.name + ".dead"))
    since = lock.get("started_at")
    return [f"moved dead round lock aside (holder {agent_id[:8]} {status}, since {since})"]


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    cal = sub.add_parser("calibrate")
    cal.add_argument("--at", required=True, help="UTC time of the first weekly rejection")
    args = parser.parse_args(argv)
    cfg = load_config()
    now = datetime.now(UTC)
    if args.command == "status":
        print(json.dumps(_load(STATUS_PATH, {}), indent=1, ensure_ascii=False))
        return 0
    if args.command == "calibrate":
        at = _ts(args.at)
        anchor = _ts(cfg["week_anchor_utc"])
        assert at is not None and anchor is not None
        ledger = update_ledger({}, PROJECTS_DIR, at, anchor=anchor, weights=cfg["weights"])
        units = {k: round(v, 1) for k, v in sorted(ledger["units"].items())}
        total = round(ledger["total"], 1)
        print(
            json.dumps(
                {
                    "at": _iso(at),
                    "week_start": ledger["week_start"],
                    "total_units": total,
                    "by_kind": units,
                }
            )
        )
        return 0
    summary = run_once(now, cfg, PaseoCli(), dry_run=args.dry_run)
    if summary["actions"] or args.dry_run:
        print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
