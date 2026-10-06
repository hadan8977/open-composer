from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "program_pages", ROOT / "scripts" / "program_pages.py"
)
assert _spec and _spec.loader
pp = importlib.util.module_from_spec(_spec)
sys.modules["program_pages"] = pp
_spec.loader.exec_module(pp)

NOTEBOOK = """# 笔记

## 实验清单

<!-- BEGIN:experiments -->
old
<!-- END:experiments -->

## 规模曲线

<!-- BEGIN:depth_curve -->
old
<!-- END:depth_curve -->
"""


def experiment(**overrides: object) -> dict:
    base = {
        "id": "X-E1",
        "stage": "0",
        "title": "测量",
        "status": "ready",
        "depth_points": ["a", "b", "c"],
        "queue_task": "T-20260101-01",
        "due_utc": "2026-10-10",
        "stop_rule": "不设",
        "artifacts": ["x/y.json"],
    }
    base.update(overrides)
    return base


def make_root(tmp_path: Path, experiments: list[dict] | None = None) -> Path:
    root = tmp_path / "programs"
    for name in pp.PROGRAMS:
        directory = root / name
        directory.mkdir(parents=True)
        exps = experiments if experiments is not None else [experiment()]
        data = {"program": name, "experiments": exps}
        (directory / "experiments.json").write_text(json.dumps(data), encoding="utf-8")
        (directory / "notebook.md").write_text(NOTEBOOK, encoding="utf-8")
        (directory / "depth_curve.jsonl").write_text("", encoding="utf-8")
        (directory / "progress.md").write_text("建立\n", encoding="utf-8")
    return root


def make_queue(tmp_path: Path, status: str = "ready") -> Path:
    queue = tmp_path / "queue.md"
    queue.write_text(
        f"# queue\n\n### T-20260101-01 task\n- status: {status}（备注）\n- goal: x\n",
        encoding="utf-8",
    )
    return queue


def run(root: Path, *args: str) -> int:
    return pp.main(["--root", str(root), *args])


def test_render_replaces_only_between_markers(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)
    program = root / "p1-midfreq"
    row = {
        "experiment_id": "X-E1",
        "depth_point": "a",
        "metric": "net_sharpe",
        "value": 0.31,
        "cumulative_trials": 3,
        "recorded_utc": "2026-10-06 12:00",
        "artifact": "x/y.json",
    }
    (program / "depth_curve.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert run(root, "render", "--program", "p1-midfreq") == 0
    text = (program / "notebook.md").read_text(encoding="utf-8")
    assert "| X-E1 | 0 | 测量 | ready | T-20260101-01 | 2026-10-10 |" in text
    assert "| X-E1 | a | net_sharpe | 0.31 | 3 | 2026-10-06 12:00 | x/y.json |" in text
    assert "old" not in text
    assert text.startswith("# 笔记\n\n## 实验清单")
    assert "## 规模曲线" in text
    # other programs stay untouched, a second render is a no-op
    assert (root / "p2-regime-theme" / "notebook.md").read_text(encoding="utf-8") == NOTEBOOK
    assert run(root, "render", "--program", "p1-midfreq") == 0
    assert "p1-midfreq: unchanged" in capsys.readouterr().out


def test_check_passes_and_flags_stale_notebook(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)
    queue = make_queue(tmp_path)
    assert run(root, "check", "--queue", str(queue)) == 1  # generated sections are stale
    assert "stale" in capsys.readouterr().out
    assert run(root, "render") == 0
    capsys.readouterr()
    assert run(root, "check", "--queue", str(queue)) == 0
    assert "ok: p6-options" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ({"queue_task": "T-20260101-99"}, "not found in autonomous-queue.md"),
        ({"status": "waiting"}, "not in"),
        ({"due_utc": "10-10"}, "due_utc"),
        ({"depth_points": "a"}, "list of strings"),
    ],
)
def test_check_rejects_bad_fields(tmp_path: Path, capsys, bad: dict, message: str) -> None:
    root = make_root(tmp_path, [experiment(**bad)])
    queue = make_queue(tmp_path)
    run(root, "render")
    capsys.readouterr()
    assert run(root, "check", "--queue", str(queue)) == 1
    assert message in capsys.readouterr().out


def test_check_rejects_missing_file_and_curve_row(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)
    queue = make_queue(tmp_path)
    run(root, "render")
    (root / "p3-complex-models" / "progress.md").unlink()
    bad_row = {"experiment_id": "NOPE", "depth_point": "a"}
    (root / "p2-regime-theme" / "depth_curve.jsonl").write_text(
        json.dumps(bad_row) + "\n", encoding="utf-8"
    )
    capsys.readouterr()
    assert run(root, "check", "--queue", str(queue)) == 1
    out = capsys.readouterr().out
    assert "p3-complex-models: missing progress.md" in out
    assert "p2-regime-theme/depth_curve.jsonl:1: missing fields" in out


def test_check_warns_on_queue_status_mismatch(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path)
    queue = make_queue(tmp_path, status="done")
    run(root, "render")
    capsys.readouterr()
    assert run(root, "check", "--queue", str(queue)) == 0
    assert "warning: p1-midfreq:X-E1: status ready but queue T-20260101-01 says done" in (
        capsys.readouterr().out
    )


def test_next_prints_first_ready_and_respects_depends_on(tmp_path: Path, capsys) -> None:
    experiments = [
        experiment(id="X-E0", status="done"),
        experiment(id="X-E1", status="ready", depends_on=["X-E9"]),
        experiment(id="X-E2", status="ready", title="第二个"),
        experiment(id="X-E3", status="ready"),
    ]
    root = make_root(tmp_path, experiments)
    # X-E1 depends on an experiment that is not done, so X-E2 is next
    for name in pp.PROGRAMS:
        data = json.loads((root / name / "experiments.json").read_text(encoding="utf-8"))
        data["experiments"].append(experiment(id="X-E9", status="planned"))
        (root / name / "experiments.json").write_text(json.dumps(data), encoding="utf-8")
    assert run(root, "next", "p1-midfreq") == 0
    out = capsys.readouterr().out
    assert "id: X-E2" in out
    assert "title: 第二个" in out
    assert "stop_rule: 不设" in out


def test_next_without_ready_experiment_exits_nonzero(tmp_path: Path, capsys) -> None:
    root = make_root(tmp_path, [experiment(status="blocked")])
    assert run(root, "next", "p3-complex-models") == 1
    assert "no ready experiment" in capsys.readouterr().out
    assert run(root, "next", "not-a-program") == 1


def test_read_queue_extracts_status_keyword(tmp_path: Path) -> None:
    queue = make_queue(tmp_path, status="running")
    assert pp.read_queue(queue) == {"T-20260101-01": "running"}


def test_repository_program_pages_are_valid() -> None:
    if not (pp.PROGRAMS_DIR / pp.PROGRAMS[0]).is_dir():
        pytest.skip("program pages are not present in this checkout")
    errors: list[str] = []
    queue = pp.read_queue()
    known = set(pp.all_experiment_ids(pp.PROGRAMS_DIR))
    for directory in pp.program_dirs(pp.PROGRAMS_DIR):
        found, _ = pp.validate_program(directory, queue, known)
        errors.extend(found)
    assert errors == []
