#!/usr/bin/env python3
"""Keep open-composer inside its memory budget so the owner always has >=500 MB free.

Why (owner 2026-10-07): the box has 3.9 GB and also runs the owner's other projects
(Hermes), their own conversations and the proxy (xray/hysteria). On 2026-10-07 16:46 UTC
this project held 16 Claude agents, two pytest runs, a Modal client and research jobs;
available memory was 761 MB, 8 GB of swap was 98% used, load was 31 and the box was
rebooted at 17:27. Every budget so far assumed the whole box. Numbers live in
config/memory-budget.json; the rules are in docs/runbook-memory.zh.md.

How: everything this project runs sits under ``oc.slice`` (agents through
/usr/local/sbin/paseo-claude-launch, research jobs through scripts/run_capped.sh, the
cockpit through a drop-in). The kernel enforces the slice's MemoryMax; this governor
lowers the slice's MemoryHigh whenever the rest of the box needs memory, so the project
yields first, and raises it again when memory frees up.

Standard library only: it runs from the system python3 as oc-memory-governor.service.

    python3 scripts/memory_budget.py governor            # loop (systemd service)
    python3 scripts/memory_budget.py governor --once [--dry-run]
    python3 scripts/memory_budget.py status              # live JSON
    python3 scripts/memory_budget.py admit --kind job --mem 900     # exit 2 = refuse
    python3 scripts/memory_budget.py admit --kind agent
    python3 scripts/memory_budget.py launch-decision     # used by paseo-claude-launch
    python3 scripts/memory_budget.py config job_max_mb   # one value, for shell callers
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "memory-budget.json"
STATE_DIR = ROOT / "logs" / "memory"
STATUS_PATH = STATE_DIR / "governor-status.json"
LOG_PATH = STATE_DIR / "governor.log"
HOURLY_PATH = STATE_DIR / "hourly.jsonl"
CGROUP_ROOT = Path("/sys/fs/cgroup")
MEMINFO = Path("/proc/meminfo")
PROC = Path("/proc")
MB = 1 << 20
BACKGROUND_LABELS = ("paseo.parent-agent-id", "paseo.schedule-id")
AGENT_SLICES = {"background": "oc-agents.slice", "interactive": "oc-interactive.slice"}
STATUS_MAX_AGE_S = 120
PASEO_CONFIG = Path("/root/.paseo/config.json")
PASEO_SERVICE_CGROUP = CGROUP_ROOT / "system.slice" / "paseo-daemon.service"
WRAPPER = "/usr/local/sbin/paseo-claude-launch"


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text())


# ----------------------------------------------------------------------------- readers
def read_meminfo(path: Path = MEMINFO) -> dict[str, int]:
    """/proc/meminfo in MB."""
    out: dict[str, int] = {}
    for line in path.read_text().splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            out[key] = int(parts[0]) // 1024
    return out


def slice_path(name: str, root: Path = CGROUP_ROOT) -> Path:
    """systemd maps ``a-b-c.slice`` to ``a.slice/a-b.slice/a-b-c.slice``."""
    stem = name.removesuffix(".slice")
    parts = stem.split("-")
    path = root
    for i in range(1, len(parts) + 1):
        path = path / ("-".join(parts[:i]) + ".slice")
    return path


def _read_int(path: Path) -> int | None:
    try:
        raw = path.read_text().strip()
    except OSError:
        return None
    if raw == "max":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def cgroup_usage(path: Path) -> dict[str, int | None]:
    """current / used (current minus inactive page cache) / high / max, in MB."""
    current = _read_int(path / "memory.current")
    inactive_file = 0
    try:
        for line in (path / "memory.stat").read_text().splitlines():
            key, _, value = line.partition(" ")
            if key == "inactive_file":
                inactive_file = int(value)
                break
    except OSError:
        pass
    high = _read_int(path / "memory.high")
    mx = _read_int(path / "memory.max")
    return {
        "current_mb": None if current is None else current // MB,
        "used_mb": None if current is None else max(0, current - inactive_file) // MB,
        "high_mb": None if high is None else high // MB,
        "max_mb": None if mx is None else mx // MB,
    }


def cgroup_pids(path: Path) -> list[int]:
    pids: list[int] = []
    if not path.is_dir():
        return pids
    for procs in path.rglob("cgroup.procs"):
        try:
            pids.extend(int(x) for x in procs.read_text().split())
        except (OSError, ValueError):
            continue
    return pids


def count_comm(path: Path, comm: str = "claude", proc: Path = PROC) -> int:
    n = 0
    for pid in cgroup_pids(path):
        try:
            if (proc / str(pid) / "comm").read_text().strip() == comm:
                n += 1
        except OSError:
            continue
    return n


def research_scopes(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return [p for p in path.iterdir() if p.is_dir() and p.name.endswith(".scope")]


def wrapper_configured(path: Path = PASEO_CONFIG) -> bool | None:
    """Whether Paseo still launches Claude through the budget wrapper (None: unreadable)."""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    command = ((data.get("agents") or {}).get("providers") or {}).get("claude", {}).get("command")
    return isinstance(command, dict) and WRAPPER in (command.get("argv") or [])


def uncapped_project_agents(
    cfg: dict[str, Any], service: Path = PASEO_SERVICE_CGROUP, proc: Path = PROC
) -> int:
    """open-composer claude processes still directly in the Paseo service (outside oc.slice)."""
    root = str(cfg["project_root"]).rstrip("/")
    n = 0
    for pid in cgroup_pids(service):
        try:
            if (proc / str(pid) / "comm").read_text().strip() != "claude":
                continue
            cwd = os.readlink(proc / str(pid) / "cwd")
        except OSError:
            continue
        if cwd == root or cwd.startswith(root + "/"):
            n += 1
    return n


# ----------------------------------------------------------------------------- policy
def next_high(avail_mb: int, used_mb: int, high_mb: int, cfg: dict[str, Any]) -> int:
    """Control law: keep MemAvailable >= target by squeezing oc.slice, relax slowly."""
    floor, ceiling = int(cfg["oc_high_floor_mb"]), int(cfg["oc_high_ceiling_mb"])
    target = int(cfg["target_available_mb"])
    high_mb = min(max(high_mb, floor), ceiling)
    if avail_mb < target:
        want = min(high_mb, used_mb) - (target - avail_mb)
        return max(floor, min(ceiling, want))
    if avail_mb > int(cfg["relax_above_mb"]):
        return min(ceiling, high_mb + int(cfg["relax_step_mb"]))
    return high_mb


def should_apply(new_mb: int, old_mb: int | None, cfg: dict[str, Any]) -> bool:
    if old_mb is None:
        return True
    if new_mb == old_mb:
        return False
    at_bound = new_mb in (int(cfg["oc_high_floor_mb"]), int(cfg["oc_high_ceiling_mb"]))
    return at_bound or abs(new_mb - old_mb) >= int(cfg["apply_min_change_mb"])


def headroom_mb(avail_mb: int, cfg: dict[str, Any]) -> int:
    """Memory a new agent or job can take without breaking the owner's reserve.

    Only the box counts. Inside the project's own limit the kernel makes room by
    compressing idle memory (zswap, owner 2026-10-08), so a project slice that sits at
    its MemoryHigh is no reason to refuse a start; the governor still keeps the reserve.
    """
    return avail_mb - int(cfg["reserve_mb"])


def snapshot(
    cfg: dict[str, Any], *, root: Path = CGROUP_ROOT, meminfo: Path = MEMINFO, proc: Path = PROC
) -> dict[str, Any]:
    mem = read_meminfo(meminfo)
    oc_path = slice_path(cfg["oc_slice"], root)
    oc = cgroup_usage(oc_path)
    children = {
        name: cgroup_usage(slice_path(name, root))
        for name in (*AGENT_SLICES.values(), cfg["research_slice"])
    }
    background = count_comm(slice_path(AGENT_SLICES["background"], root), proc=proc)
    interactive = count_comm(slice_path(AGENT_SLICES["interactive"], root), proc=proc)
    avail = mem.get("MemAvailable", 0)
    room = headroom_mb(avail, cfg)
    return {
        "checked_at": now_iso(),
        "mem_total_mb": mem.get("MemTotal", 0),
        "available_mb": avail,
        "swap_free_mb": mem.get("SwapFree", 0),
        "zswap_pool_mb": mem.get("Zswap", 0),
        "zswapped_mb": mem.get("Zswapped", 0),
        "reserve_mb": int(cfg["reserve_mb"]),
        "oc_present": oc_path.is_dir(),
        "oc": oc,
        "children": children,
        "background_agents": background,
        "interactive_agents": interactive,
        "research_jobs": len(research_scopes(slice_path(cfg["research_slice"], root))),
        "headroom_mb": room,
        "paseo_wrapper_configured": wrapper_configured(),
        "uncapped_project_agents": uncapped_project_agents(cfg, proc=proc),
    }


def admit(
    kind: str,
    mem_mb: int,
    snap: dict[str, Any],
    cfg: dict[str, Any],
    *,
    job_class: str = "research",
) -> tuple[bool, str]:
    room = int(snap["headroom_mb"])
    if kind == "agent":
        if int(snap["background_agents"]) >= int(cfg["background_agents_max"]):
            return False, (
                f"background agents {snap['background_agents']} >= "
                f"{cfg['background_agents_max']} (archive an idle one first)"
            )
        need = int(cfg["agent_admit_headroom_mb"])
        if room < need:
            return False, f"headroom {room} MB < {need} MB for a new agent"
        return True, f"ok, headroom {room} MB"
    if job_class != "paper" and mem_mb > int(cfg["job_max_mb"]):
        return False, (
            f"--mem {mem_mb} MB > local job limit {cfg['job_max_mb']} MB; run it on Modal "
            "(docs/runbook-autonomous-round.zh.md section 5) or shrink the job"
        )
    if job_class == "paper":
        return True, f"ok (paper), headroom {room} MB"
    need = min(mem_mb, int(cfg["heavy_job_mb"]))
    research = (snap.get("children") or {}).get(cfg["research_slice"]) or {}
    research_room = int(cfg["research_max_mb"]) - int(research.get("used_mb") or 0)
    if research_room < need:
        return False, (
            f"research jobs already hold {research.get('used_mb')} MB of "
            f"{cfg['research_max_mb']} MB; need {need} MB free"
        )
    if room < need:
        return False, f"headroom {room} MB < {need} MB"
    return True, f"ok, headroom {room} MB, research room {research_room} MB"


# ----------------------------------------------------------------------------- launcher
def agent_record(agent_id: str, agents_dir: Path) -> dict[str, Any] | None:
    best: tuple[float, dict[str, Any]] | None = None
    for path in agents_dir.glob(f"*/{agent_id}.json"):
        try:
            record = json.loads(path.read_text())
            mtime = path.stat().st_mtime
        except (OSError, json.JSONDecodeError):
            continue
        if best is None or mtime > best[0]:
            best = (mtime, record)
    return None if best is None else best[1]


def agent_class(agent_id: str | None, agents_dir: Path) -> str:
    if not agent_id:
        return "interactive"
    record = agent_record(agent_id, agents_dir) or {}
    labels = record.get("labels") or {}
    if isinstance(labels, dict) and any(k in labels for k in BACKGROUND_LABELS):
        return "background"
    return "interactive"


def launch_decision(
    cwd: str, agent_id: str | None, cfg: dict[str, Any], snap: dict[str, Any] | None = None
) -> str:
    """``plain`` | ``<slice>`` | ``refuse:<reason>`` for the Paseo claude wrapper."""
    root = str(cfg["project_root"]).rstrip("/")
    if not agent_id or not (cwd == root or cwd.startswith(root + "/")):
        return "plain"
    klass = agent_class(agent_id, Path(cfg["paseo_agents_dir"]))
    if klass == "background":
        snap = snap if snap is not None else snapshot(cfg)
        if not snap["oc_present"]:
            return "plain"
        if int(snap["background_agents"]) >= int(cfg["background_agents_max"]):
            return (
                f"refuse:background agents {snap['background_agents']} >= "
                f"{cfg['background_agents_max']}; archive an idle agent or wait"
            )
    return AGENT_SLICES[klass]


# ----------------------------------------------------------------------------- governor
def log_event(message: str, path: Path = LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(f"{now_iso()} {message}\n")


def append_hourly(record: dict[str, Any], path: Path = HOURLY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def write_status(data: dict[str, Any], path: Path = STATUS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
    tmp.replace(path)


def set_high(slice_name: str, mb: int) -> None:
    subprocess.run(
        ["systemctl", "set-property", "--runtime", slice_name, f"MemoryHigh={mb}M"],
        check=True,
        timeout=30,
        capture_output=True,
    )


def stop_newest_research_job(cfg: dict[str, Any], root: Path = CGROUP_ROOT) -> str | None:
    scopes = research_scopes(slice_path(cfg["research_slice"], root))
    if not scopes:
        return None
    newest = max(scopes, key=lambda p: p.stat().st_mtime)
    subprocess.run(["systemctl", "stop", newest.name], check=False, timeout=60, capture_output=True)
    return newest.name


class Governor:
    def __init__(self, cfg: dict[str, Any], *, dry_run: bool = False) -> None:
        self.cfg = cfg
        self.dry_run = dry_run
        self.below_reserve_since: float | None = None
        self.low_headroom_since: float | None = None
        self.last_action: str | None = None
        self.hour: dict[str, Any] | None = None

    def record_hour(self, snap: dict[str, Any]) -> dict[str, Any] | None:
        """Per-UTC-hour lowest available memory (every tick, not sar's 10-minute average).

        Returns the finished hour when a new one starts; the governor appends it to
        logs/memory/hourly.jsonl, which is the record for "the owner always had 500 MB".
        """
        key = str(snap["checked_at"])[:13]
        avail = int(snap["available_mb"])
        finished = None
        if self.hour is not None and self.hour["hour"] != key:
            finished, self.hour = self.hour, None
        if self.hour is None:
            self.hour = {
                "hour": key,
                "min_available_mb": avail,
                "min_at": snap["checked_at"],
                "max_oc_used_mb": 0,
                "ticks": 0,
                "ticks_below_reserve": 0,
            }
        hour = self.hour
        hour["ticks"] += 1
        if avail < hour["min_available_mb"]:
            hour["min_available_mb"] = avail
            hour["min_at"] = snap["checked_at"]
        if avail < int(self.cfg["reserve_mb"]):
            hour["ticks_below_reserve"] += 1
        used = int((snap.get("oc") or {}).get("used_mb") or 0)
        hour["max_oc_used_mb"] = max(hour["max_oc_used_mb"], used)
        return finished

    def tick(self, snap: dict[str, Any], now: float) -> dict[str, Any]:
        cfg = self.cfg
        avail = int(snap["available_mb"])
        actions: list[str] = []
        if snap["oc_present"]:
            oc = snap["oc"]
            old = oc.get("high_mb")
            base = old if old is not None else int(cfg["oc_high_ceiling_mb"])
            new = next_high(avail, int(oc.get("used_mb") or 0), base, cfg)
            if should_apply(new, old, cfg):
                if not self.dry_run:
                    set_high(cfg["oc_slice"], new)
                actions.append(f"MemoryHigh {old} -> {new} MB (available {avail} MB)")
                snap["oc"]["high_mb"] = new
        if avail < int(cfg["reserve_mb"]):
            if self.below_reserve_since is None:
                self.below_reserve_since = now
            if now - self.below_reserve_since >= float(cfg["escalate_after_s"]):
                stopped = None if self.dry_run else stop_newest_research_job(cfg)
                actions.append(
                    f"available {avail} MB < reserve {cfg['reserve_mb']} MB for "
                    f"{now - self.below_reserve_since:.0f}s: stopped "
                    f"{stopped or 'nothing (no research job)'}"
                )
                self.below_reserve_since = now
        else:
            self.below_reserve_since = None
        if int(snap["headroom_mb"]) < int(cfg["agent_admit_headroom_mb"]):
            if self.low_headroom_since is None:
                self.low_headroom_since = now
        else:
            self.low_headroom_since = None
        ok, reason = admit("agent", 0, snap, cfg)
        snap["admit_agent"] = {"ok": ok, "reason": reason}
        snap["low_headroom_s"] = (
            0 if self.low_headroom_since is None else round(now - self.low_headroom_since)
        )
        snap["below_reserve_s"] = (
            0 if self.below_reserve_since is None else round(now - self.below_reserve_since)
        )
        for action in actions:
            self.last_action = f"{snap['checked_at']} {action}"
            if not self.dry_run:
                log_event(action)
        snap["last_action"] = self.last_action
        finished = self.record_hour(snap)
        if finished is not None and not self.dry_run:
            append_hourly(finished)
        snap["hour"] = self.hour
        return snap


def governor(cfg_path: Path, *, once: bool, dry_run: bool) -> int:
    cfg = load_config(cfg_path)
    gov = Governor(cfg, dry_run=dry_run)
    while True:
        try:
            cfg = load_config(cfg_path)
            gov.cfg = cfg
        except (OSError, json.JSONDecodeError) as exc:
            log_event(f"config unreadable, keeping previous: {exc}")
        try:
            snap = gov.tick(snapshot(cfg), time.monotonic())
            if dry_run:
                print(json.dumps(snap, indent=1, sort_keys=True))
            else:
                write_status(snap)
        except Exception as exc:  # the loop must survive anything
            log_event(f"tick failed: {exc!r}")
        if once:
            return 0
        time.sleep(float(cfg.get("interval_s", 10)))


def read_status(path: Path = STATUS_PATH) -> dict[str, Any] | None:
    """Governor status if fresh, else None (callers then take a live snapshot)."""
    try:
        data = json.loads(path.read_text())
        age = time.time() - path.stat().st_mtime
    except (OSError, json.JSONDecodeError):
        return None
    return data if age <= STATUS_MAX_AGE_S else None


# ----------------------------------------------------------------------------- cli
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("governor")
    g.add_argument("--once", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    a = sub.add_parser("admit")
    a.add_argument("--kind", choices=("agent", "job"), required=True)
    a.add_argument("--mem", type=int, default=0, help="job memory cap in MB")
    a.add_argument("--class", dest="job_class", choices=("research", "paper"), default="research")
    d = sub.add_parser("launch-decision")
    d.add_argument("--cwd", default=None)
    d.add_argument("--agent-id", default=None)
    c = sub.add_parser("config")
    c.add_argument("key")
    ns = parser.parse_args(argv)
    cfg = load_config(ns.config)

    if ns.cmd == "governor":
        return governor(ns.config, once=ns.once, dry_run=ns.dry_run)
    if ns.cmd == "status":
        snap = snapshot(cfg)
        status = read_status()
        if status:
            snap["governor"] = {
                k: status.get(k)
                for k in ("checked_at", "last_action", "low_headroom_s", "below_reserve_s")
            }
        print(json.dumps(snap, indent=1, sort_keys=True))
        return 0
    if ns.cmd == "admit":
        ok, reason = admit(ns.kind, ns.mem, snapshot(cfg), cfg, job_class=ns.job_class)
        print(("admit: " if ok else "refuse: ") + reason, file=sys.stderr)
        return 0 if ok else 2
    if ns.cmd == "config":
        if ns.key not in cfg:
            print(f"unknown key {ns.key}", file=sys.stderr)
            return 2
        print(cfg[ns.key])
        return 0
    if ns.cmd == "launch-decision":
        cwd = ns.cwd if ns.cwd is not None else os.getcwd()
        agent_id = ns.agent_id if ns.agent_id is not None else os.environ.get("PASEO_AGENT_ID")
        print(launch_decision(cwd, agent_id, cfg))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
