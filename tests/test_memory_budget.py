"""scripts/memory_budget.py: control law, admission, launcher decisions, governor ticks.

Everything runs on fake /proc and cgroup trees under tmp_path; nothing touches systemd.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import memory_budget as M

ROOT = Path(__file__).resolve().parents[1]
CFG: dict[str, Any] = json.loads((ROOT / "config" / "memory-budget.json").read_text())
MB = 1 << 20


def _meminfo(tmp_path: Path, available_mb: int, total_mb: int = 3914) -> Path:
    path = tmp_path / "meminfo"
    path.write_text(
        f"MemTotal:       {total_mb * 1024} kB\n"
        f"MemFree:        100000 kB\n"
        f"MemAvailable:   {available_mb * 1024} kB\n"
        f"SwapFree:       {2048 * 1024} kB\n"
    )
    return path


def _cgroup(
    path: Path,
    current_mb: int,
    *,
    inactive_file_mb: int = 0,
    high: str = "max",
    pids: tuple[int, ...] = (),
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "memory.current").write_text(str(current_mb * MB))
    (path / "memory.stat").write_text(f"anon 1\ninactive_file {inactive_file_mb * MB}\n")
    (path / "memory.high").write_text(high)
    (path / "memory.max").write_text("max")
    (path / "cgroup.procs").write_text("".join(f"{p}\n" for p in pids))


def _proc(tmp_path: Path, comms: dict[int, str]) -> Path:
    proc = tmp_path / "proc"
    for pid, comm in comms.items():
        (proc / str(pid)).mkdir(parents=True, exist_ok=True)
        (proc / str(pid) / "comm").write_text(comm + "\n")
    return proc


def _tree(
    tmp_path: Path, *, oc_mb: int = 1000, background: int = 0, interactive: int = 1, jobs: int = 0
) -> tuple[Path, Path]:
    root = tmp_path / "cg"
    oc = M.slice_path("oc.slice", root)
    _cgroup(oc, oc_mb, inactive_file_mb=100, high=str(2000 * MB))
    comms: dict[int, str] = {}
    bg_pids = tuple(range(100, 100 + background))
    it_pids = tuple(range(200, 200 + interactive))
    for pid in bg_pids + it_pids:
        comms[pid] = "claude"
    comms[999] = "python3"  # an MCP server inside an agent scope is not an agent
    _cgroup(M.slice_path("oc-agents.slice", root) / "a.scope", 300, pids=bg_pids + (999,))
    _cgroup(M.slice_path("oc-interactive.slice", root) / "b.scope", 300, pids=it_pids)
    research = M.slice_path("oc-research-capped.slice", root)
    _cgroup(research, 0)
    for i in range(jobs):
        _cgroup(research / f"run-{i}.scope", 100)
    return root, _proc(tmp_path, comms)


# ----------------------------------------------------------------------------- readers
def test_slice_path_follows_systemd_nesting() -> None:
    root = Path("/sys/fs/cgroup")
    assert M.slice_path("oc.slice") == root / "oc.slice"
    assert M.slice_path("oc-research-capped.slice") == (
        root / "oc.slice" / "oc-research.slice" / "oc-research-capped.slice"
    )


def test_snapshot_counts_agents_jobs_and_headroom(tmp_path: Path) -> None:
    root, proc = _tree(tmp_path, oc_mb=1000, background=2, interactive=1, jobs=1)
    snap = M.snapshot(CFG, root=root, meminfo=_meminfo(tmp_path, 1500), proc=proc)
    assert snap["oc_present"] is True
    assert snap["background_agents"] == 2
    assert snap["interactive_agents"] == 1
    assert snap["research_jobs"] == 1
    assert snap["oc"]["used_mb"] == 900  # page cache that is easy to drop is not counted
    # only the box counts (1500 - 500): inside the slice the kernel compresses idle memory
    assert snap["headroom_mb"] == 1000


# ----------------------------------------------------------------------------- policy
@pytest.mark.parametrize(
    ("avail", "used", "high", "want"),
    [
        (500, 1800, 2000, 1650),  # 150 MB short of the 650 target: squeeze by it
        (300, 1000, 2000, 900),  # never below the floor
        (600, 1500, 1200, 1150),  # squeeze from the current limit when usage is above it
        (1200, 1000, 1500, 1600),  # plenty free: relax one step
        (1200, 1000, 1950, 2000),  # ... but never above the ceiling
        (800, 1000, 1500, 1500),  # between target and relax threshold: hold
    ],
)
def test_next_high(avail: int, used: int, high: int, want: int) -> None:
    assert M.next_high(avail, used, high, CFG) == want


def test_should_apply_skips_small_moves_but_not_bounds() -> None:
    assert M.should_apply(1500, None, CFG)
    assert not M.should_apply(1500, 1500, CFG)
    assert not M.should_apply(1540, 1500, CFG)
    assert M.should_apply(1600, 1500, CFG)
    assert M.should_apply(900, 920, CFG)  # reaching the floor always applies


def _snap(**kw: Any) -> dict[str, Any]:
    base = {"headroom_mb": 1000, "background_agents": 0}
    return {**base, **kw}


def test_admit_agent_cap_and_headroom() -> None:
    cap = int(CFG["background_agents_max"])
    need = int(CFG["agent_admit_headroom_mb"])
    assert M.admit("agent", 0, _snap(), CFG)[0]
    assert M.admit("agent", 0, _snap(background_agents=cap - 1), CFG)[0]
    ok, reason = M.admit("agent", 0, _snap(background_agents=cap), CFG)
    assert not ok and f"background agents {cap}" in reason
    assert not M.admit("agent", 0, _snap(headroom_mb=need - 1), CFG)[0]


def test_admit_job_limit_and_paper_exemption() -> None:
    over = int(CFG["job_max_mb"]) + 1
    ok, reason = M.admit("job", over, _snap(), CFG)
    assert not ok and "Modal" in reason
    assert M.admit("job", over, _snap(headroom_mb=0), CFG, job_class="paper")[0]
    need = int(CFG["heavy_job_mb"])  # a job starts with min(--mem, heavy_job_mb) free
    assert M.admit("job", 900, _snap(headroom_mb=need), CFG)[0]
    assert not M.admit("job", 900, _snap(headroom_mb=need - 1), CFG)[0]
    assert M.admit("job", 100, _snap(headroom_mb=100), CFG)[0]


# ----------------------------------------------------------------------------- launcher
def _agents_dir(tmp_path: Path, agent_id: str, labels: dict[str, str]) -> Path:
    agents = tmp_path / "agents"
    (agents / "root-codex-test-open-composer").mkdir(parents=True, exist_ok=True)
    (agents / "root-codex-test-open-composer" / f"{agent_id}.json").write_text(
        json.dumps({"id": agent_id, "labels": labels})
    )
    return agents


def _cfg(agents: Path) -> dict[str, Any]:
    return {**CFG, "paseo_agents_dir": str(agents)}


def test_launch_decision_classes(tmp_path: Path) -> None:
    agents = _agents_dir(tmp_path, "top", {})
    _agents_dir(tmp_path, "child", {"paseo.parent-agent-id": "top"})
    _agents_dir(tmp_path, "round", {"paseo.schedule-id": "38928f29"})
    cfg = _cfg(agents)
    snap = {"oc_present": True, "background_agents": 0}
    repo = CFG["project_root"]
    assert M.launch_decision("/root/finance", "top", cfg, snap) == "plain"
    assert M.launch_decision(repo + "-other", "top", cfg, snap) == "plain"
    assert M.launch_decision(repo, None, cfg, snap) == "plain"
    assert M.launch_decision(repo, "top", cfg, snap) == "oc-interactive.slice"
    assert M.launch_decision(repo + "/scripts", "unknown", cfg, snap) == "oc-interactive.slice"
    assert M.launch_decision(repo, "child", cfg, snap) == "oc-agents.slice"
    assert M.launch_decision(repo, "round", cfg, snap) == "oc-agents.slice"


def test_launch_decision_refuses_a_background_agent_over_the_cap(tmp_path: Path) -> None:
    agents = _agents_dir(tmp_path, "child", {"paseo.parent-agent-id": "top"})
    _agents_dir(tmp_path, "top", {})
    cfg = _cfg(agents)
    repo = CFG["project_root"]
    full = {"oc_present": True, "background_agents": int(CFG["background_agents_max"])}
    assert M.launch_decision(repo, "child", cfg, full).startswith("refuse:")
    assert M.launch_decision(repo, "top", cfg, full) == "oc-interactive.slice"
    absent = {"oc_present": False, "background_agents": 0}
    assert M.launch_decision(repo, "child", cfg, absent) == "plain"


# ----------------------------------------------------------------------------- governor
def test_governor_squeezes_then_escalates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Any]] = []
    monkeypatch.setattr(M, "set_high", lambda name, mb: calls.append(("high", mb)))
    monkeypatch.setattr(
        M, "stop_newest_research_job", lambda cfg: calls.append(("stop", 1)) or "run-1.scope"
    )
    monkeypatch.setattr(M, "log_event", lambda message: calls.append(("log", message)))
    root, proc = _tree(tmp_path, oc_mb=1900, jobs=1)
    gov = M.Governor(CFG)

    snap = gov.tick(M.snapshot(CFG, root=root, meminfo=_meminfo(tmp_path, 450), proc=proc), 0.0)
    assert ("high", 1600) in calls  # used 1800 - (650 - 450)
    assert snap["below_reserve_s"] == 0
    assert not any(c[0] == "stop" for c in calls)

    snap = gov.tick(M.snapshot(CFG, root=root, meminfo=_meminfo(tmp_path, 450), proc=proc), 31.0)
    assert ("stop", 1) in calls
    assert "stopped run-1.scope" in snap["last_action"]


def test_governor_dry_run_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError("dry run must not act")

    monkeypatch.setattr(M, "set_high", boom)
    monkeypatch.setattr(M, "stop_newest_research_job", boom)
    monkeypatch.setattr(M, "log_event", boom)
    root, proc = _tree(tmp_path, oc_mb=1900, jobs=1)
    gov = M.Governor(CFG, dry_run=True)
    for t in (0.0, 40.0):
        snap = gov.tick(M.snapshot(CFG, root=root, meminfo=_meminfo(tmp_path, 300), proc=proc), t)
    assert "MemoryHigh" in snap["last_action"] or "stopped" in snap["last_action"]


def test_governor_tracks_low_headroom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(M, "set_high", lambda name, mb: None)
    monkeypatch.setattr(M, "log_event", lambda message: None)
    root, proc = _tree(tmp_path, oc_mb=1000)
    gov = M.Governor(CFG)
    low = int(CFG["reserve_mb"]) + int(CFG["agent_admit_headroom_mb"]) - 50
    snap = gov.tick(M.snapshot(CFG, root=root, meminfo=_meminfo(tmp_path, low), proc=proc), 0.0)
    assert snap["low_headroom_s"] == 0 and snap["admit_agent"]["ok"] is False
    snap = gov.tick(M.snapshot(CFG, root=root, meminfo=_meminfo(tmp_path, low), proc=proc), 400.0)
    assert snap["low_headroom_s"] == 400
    snap = gov.tick(M.snapshot(CFG, root=root, meminfo=_meminfo(tmp_path, 2000), proc=proc), 410.0)
    assert snap["low_headroom_s"] == 0 and snap["admit_agent"]["ok"] is True


# ----------------------------------------------------------------------------- shell side
def test_run_capped_refuses_over_limit_and_bad_class() -> None:
    script = str(ROOT / "scripts" / "run_capped.sh")
    too_big = f"{int(CFG['job_max_mb']) + 100}M"
    over = subprocess.run([script, "--mem", too_big, "--", "true"], capture_output=True, text=True)
    assert over.returncode == 2 and "Modal" in over.stderr
    bad = subprocess.run([script, "--class", "fast", "--", "true"], capture_output=True, text=True)
    assert bad.returncode == 2


def test_this_pytest_run_holds_the_repo_lock() -> None:
    if os.environ.get("OC_PYTEST_LOCK_HELD") != str(os.getpid()):
        pytest.skip("lock bypassed by hand or held by a parent pytest")
    probe = subprocess.run(["flock", "-n", "/tmp/open-composer-pytest.lock", "true"])
    assert probe.returncode != 0


def test_hourly_minimum_rolls_over(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[dict[str, Any]] = []
    monkeypatch.setattr(M, "append_hourly", written.append)
    monkeypatch.setattr(M, "set_high", lambda name, mb: None)
    monkeypatch.setattr(M, "log_event", lambda message: None)
    root, proc = _tree(tmp_path, oc_mb=1000)
    gov = M.Governor(CFG)
    for at, avail in (
        ("2026-10-07T18:01:00Z", 900),
        ("2026-10-07T18:30:00Z", 480),
        ("2026-10-07T18:59:00Z", 1200),
        ("2026-10-07T19:00:05Z", 1000),
    ):
        snap = M.snapshot(CFG, root=root, meminfo=_meminfo(tmp_path, avail), proc=proc)
        snap["checked_at"] = at
        gov.tick(snap, 0.0)
    assert len(written) == 1
    hour = written[0]
    assert hour["hour"] == "2026-10-07T18" and hour["ticks"] == 3
    assert hour["min_available_mb"] == 480 and hour["min_at"] == "2026-10-07T18:30:00Z"
    assert hour["ticks_below_reserve"] == 1
    assert gov.hour is not None and gov.hour["hour"] == "2026-10-07T19"


def test_admit_job_waits_for_research_room_by_actual_use() -> None:
    need = int(CFG["heavy_job_mb"])
    used = int(CFG["research_max_mb"]) - need + 1  # one MB short of a start
    held = {"oc-research-capped.slice": {"used_mb": used}}
    ok, reason = M.admit("job", 900, _snap(children=held), CFG)
    assert not ok and f"research jobs already hold {used} MB" in reason
    small = {"oc-research-capped.slice": {"used_mb": 100}}  # a big cap that uses little
    assert M.admit("job", 900, _snap(children=small), CFG)[0]
    assert M.admit("job", need - 2, _snap(children=held), CFG)[0]  # a smaller job still fits


def test_wrapper_configured_reads_paseo_config(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"agents": {"providers": {"claude": {"enabled": True}}}}))
    assert M.wrapper_configured(cfg) is False
    command = {"mode": "replace", "argv": [M.WRAPPER]}
    cfg.write_text(json.dumps({"agents": {"providers": {"claude": {"command": command}}}}))
    assert M.wrapper_configured(cfg) is True
    assert M.wrapper_configured(tmp_path / "missing.json") is None


def test_uncapped_project_agents_counts_only_repo_claude(tmp_path: Path) -> None:
    proc = _proc(tmp_path, {11: "claude", 12: "claude", 13: "python3"})
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    os.symlink(repo / "sub", proc / "11" / "cwd")
    os.symlink(tmp_path, proc / "12" / "cwd")
    os.symlink(repo, proc / "13" / "cwd")
    service = tmp_path / "paseo-daemon.service"
    _cgroup(service, 100, pids=(11, 12, 13))
    assert M.uncapped_project_agents({"project_root": str(repo)}, service, proc) == 1
