"""Project pages for the six flagship programs (`docs/plan-v2-2026-10-05.zh.md` sections 2 and 3).

Each program lives in `reports/research/programs/<program>/` with four files:
`notebook.md`, `experiments.json`, `depth_curve.jsonl`, `progress.md`.

    uv run python scripts/program_pages.py render            # rewrite the two generated sections
    uv run python scripts/program_pages.py check             # validate fields, queue ids, staleness
    uv run python scripts/program_pages.py next p1-midfreq   # next ready experiment of a program

`render` only replaces the text between the fixed markers in `notebook.md`; everything else in
the notebook is hand-written excerpts of the plan.  The experiment list and the depth-curve
ledger are the source of truth.  No model call, no market data, no broker call.
Exit codes: 0 ok, 1 check failed or nothing to do (`next` without a ready experiment).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS_DIR = ROOT / "reports" / "research" / "programs"
QUEUE_PATH = ROOT / "reports" / "research" / "control" / "autonomous-queue.md"
BRIEFS_DIR = ROOT / "reports" / "research" / "control" / "briefs"

PROGRAMS = (
    "p1-midfreq",
    "p2-regime-theme",
    "p3-complex-models",
    "p4-live-path",
    "p5-research-factory",
    "p6-options",
)
FILES = ("notebook.md", "experiments.json", "depth_curve.jsonl", "progress.md")
STATUSES = ("planned", "ready", "running", "done", "blocked")
EXPERIMENT_FIELDS = (
    "id",
    "stage",
    "title",
    "status",
    "depth_points",
    "queue_task",
    "due_utc",
    "stop_rule",
    "artifacts",
)
CURVE_FIELDS = (
    "experiment_id",
    "depth_point",
    "metric",
    "value",
    "cumulative_trials",
    "recorded_utc",
    "artifact",
)
MARKERS = {
    "experiments": ("<!-- BEGIN:experiments -->", "<!-- END:experiments -->"),
    "depth_curve": ("<!-- BEGIN:depth_curve -->", "<!-- END:depth_curve -->"),
}
QUEUE_ID = re.compile(r"^T-\d{8}-\d+$")
DUE = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?$")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")
QUEUE_STATUS_MAP = {
    "ready": "ready",
    "running": "running",
    "partial": "running",
    "done": "done",
    "blocked": "blocked",
}


def read_queue(path: Path = QUEUE_PATH) -> dict[str, str]:
    """Map queue task id to its status keyword (first word after `- status:`; "" if absent)."""
    tasks: dict[str, str] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        header = re.match(r"^### (T-\d{8}-\d+)\b", line)
        if header:
            current = header.group(1)
            tasks[current] = ""
            continue
        if current and line.startswith("- status:") and not tasks[current]:
            match = re.match(r"- status:\s*([a-z]+)", line)
            tasks[current] = match.group(1) if match else ""
    return tasks


def load_experiments(program_dir: Path) -> dict:
    return json.loads((program_dir / "experiments.json").read_text(encoding="utf-8"))


def load_curve(program_dir: Path) -> list[dict]:
    path = program_dir / "depth_curve.jsonl"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _fmt_value(value: object) -> str:
    return "-" if value is None else str(value)


def render_experiments(data: dict) -> str:
    experiments = data["experiments"]
    lines = [
        "| id | 阶段 | 标题 | 状态 | 队列任务 | 截止 UTC |",
        "|---|---|---|---|---|---|",
    ]
    for exp in experiments:
        lines.append(
            f"| {exp['id']} | {exp['stage']} | {exp['title']} | {exp['status']} "
            f"| {_fmt_value(exp['queue_task'])} | {_fmt_value(exp['due_utc'])} |"
        )
    lines.append("")
    lines.append("各实验的深度点、停止条件和产物：")
    lines.append("")
    for exp in experiments:
        depth = "；".join(exp["depth_points"]) if exp["depth_points"] else "无（测量或工程项）"
        artifacts = "；".join(exp["artifacts"]) if exp["artifacts"] else "待定"
        lines.append(f"- **{exp['id']}**")
        lines.append(f"  - 深度点：{depth}")
        lines.append(f"  - 停止条件：{exp['stop_rule']}")
        lines.append(f"  - 产物：{artifacts}")
        if exp.get("depends_on"):
            lines.append(f"  - 依赖：{'、'.join(exp['depends_on'])}")
        if exp.get("notes"):
            lines.append(f"  - 备注：{exp['notes']}")
    return "\n".join(lines)


def render_curve(rows: list[dict]) -> str:
    if not rows:
        return "（尚无记录。每行写入 `depth_curve.jsonl` 后运行 `render`。）"
    lines = [
        "| 实验 | 深度点 | 指标 | 数值 | 累计试验数 | 时间 | 产物 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['experiment_id']} | {row['depth_point']} | {row['metric']} "
            f"| {row['value']} | {row['cumulative_trials']} | {row['recorded_utc']} "
            f"| {row['artifact']} |"
        )
    return "\n".join(lines)


def replace_between(text: str, start: str, end: str, body: str) -> str:
    """Replace the text between two markers; raise if a marker is missing or misordered."""
    i = text.find(start)
    j = text.find(end)
    if i == -1 or j == -1 or j < i:
        raise ValueError(f"markers {start} / {end} missing or out of order")
    return text[: i + len(start)] + "\n" + body + "\n" + text[j:]


def rendered_notebook(program_dir: Path) -> str:
    text = (program_dir / "notebook.md").read_text(encoding="utf-8")
    text = replace_between(
        text, *MARKERS["experiments"], render_experiments(load_experiments(program_dir))
    )
    return replace_between(text, *MARKERS["depth_curve"], render_curve(load_curve(program_dir)))


def render_program(program_dir: Path) -> bool:
    """Rewrite the generated sections; return True if the file changed."""
    path = program_dir / "notebook.md"
    old = path.read_text(encoding="utf-8")
    new = rendered_notebook(program_dir)
    if new != old:
        path.write_text(new, encoding="utf-8")
    return new != old


def validate_program(
    program_dir: Path,
    queue: dict[str, str],
    all_ids: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for one program directory."""
    errors: list[str] = []
    warnings: list[str] = []
    name = program_dir.name
    for filename in FILES:
        if not (program_dir / filename).is_file():
            errors.append(f"{name}: missing {filename}")
    if errors:
        return errors, warnings
    try:
        data = load_experiments(program_dir)
    except json.JSONDecodeError as exc:
        return [f"{name}: experiments.json is not valid JSON ({exc})"], warnings
    if data.get("program") != name:
        errors.append(f"{name}: experiments.json program is {data.get('program')!r}")
    experiments = data.get("experiments")
    if not isinstance(experiments, list) or not experiments:
        return [*errors, f"{name}: experiments must be a non-empty list"], warnings
    ids: set[str] = set()
    for index, exp in enumerate(experiments):
        label = f"{name}[{index}]"
        if not isinstance(exp, dict):
            errors.append(f"{label}: not an object")
            continue
        missing = [f for f in EXPERIMENT_FIELDS if f not in exp]
        if missing:
            errors.append(f"{label}: missing fields {missing}")
            continue
        label = f"{name}:{exp['id']}"
        if exp["id"] in ids:
            errors.append(f"{label}: duplicate id")
        ids.add(exp["id"])
        for field in ("id", "stage", "title", "stop_rule"):
            if not isinstance(exp[field], str) or not exp[field].strip():
                errors.append(f"{label}: {field} must be a non-empty string")
        if exp["status"] not in STATUSES:
            errors.append(f"{label}: status {exp['status']!r} not in {STATUSES}")
        for field in ("depth_points", "artifacts"):
            value = exp[field]
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                errors.append(f"{label}: {field} must be a list of strings")
        due = exp["due_utc"]
        if due is not None and (not isinstance(due, str) or not DUE.match(due)):
            errors.append(f"{label}: due_utc {due!r} is not YYYY-MM-DD[ HH:MM] or null")
        task = exp["queue_task"]
        if task is not None:
            if not isinstance(task, str) or not QUEUE_ID.match(task):
                errors.append(f"{label}: queue_task {task!r} is not a task id or null")
            elif task not in queue:
                errors.append(f"{label}: queue_task {task} not found in autonomous-queue.md")
            else:
                mapped = QUEUE_STATUS_MAP.get(queue[task])
                if exp["status"] != "planned" and mapped and mapped != exp["status"]:
                    warnings.append(
                        f"{label}: status {exp['status']} but queue {task} says {queue[task]}"
                    )
        if exp["status"] == "ready" and task is None:
            warnings.append(f"{label}: ready without a queue task")
        depends = exp.get("depends_on", [])
        if not isinstance(depends, list):
            errors.append(f"{label}: depends_on must be a list")
        elif all_ids is not None:
            for dep in depends:
                if dep not in all_ids:
                    errors.append(f"{label}: depends_on {dep} is not a known experiment id")
    errors.extend(_validate_curve(program_dir, ids))
    if errors:
        return errors, warnings  # staleness is only meaningful for well-formed inputs
    try:
        if rendered_notebook(program_dir) != (program_dir / "notebook.md").read_text(
            encoding="utf-8"
        ):
            errors.append(f"{name}: notebook.md generated sections are stale; run render")
    except ValueError as exc:
        errors.append(f"{name}: notebook.md {exc}")
    return errors, warnings


def _validate_curve(program_dir: Path, ids: set[str]) -> list[str]:
    errors: list[str] = []
    name = program_dir.name
    lines = (program_dir / "depth_curve.jsonl").read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        label = f"{name}/depth_curve.jsonl:{number}"
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"{label}: not valid JSON")
            continue
        missing = [f for f in CURVE_FIELDS if f not in row]
        if missing:
            errors.append(f"{label}: missing fields {missing}")
            continue
        if row["experiment_id"] not in ids:
            errors.append(f"{label}: unknown experiment_id {row['experiment_id']!r}")
        trials = row["cumulative_trials"]
        if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
            errors.append(f"{label}: cumulative_trials must be an integer >= 1")
        if not isinstance(row["recorded_utc"], str) or not STAMP.match(row["recorded_utc"]):
            errors.append(f"{label}: recorded_utc must start with YYYY-MM-DD HH:MM")
    return errors


def program_dirs(root: Path) -> list[Path]:
    return [root / name for name in PROGRAMS]


def all_experiment_ids(root: Path) -> dict[str, str]:
    """Map experiment id to status over every readable program."""
    found: dict[str, str] = {}
    for directory in program_dirs(root):
        try:
            for exp in load_experiments(directory)["experiments"]:
                found[exp["id"]] = exp["status"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return found


def next_experiment(program_dir: Path, statuses: dict[str, str]) -> dict | None:
    """First `ready` experiment whose dependencies are all done."""
    for exp in load_experiments(program_dir)["experiments"]:
        if exp["status"] != "ready":
            continue
        if all(statuses.get(dep) == "done" for dep in exp.get("depends_on", [])):
            return exp
    return None


def format_next(program: str, exp: dict) -> str:
    lines = [
        f"program: {program}",
        f"id: {exp['id']}",
        f"stage: {exp['stage']}",
        f"title: {exp['title']}",
        f"queue_task: {_fmt_value(exp['queue_task'])}",
    ]
    task = exp["queue_task"]
    if task and (BRIEFS_DIR / f"{task}.md").is_file():
        lines.append(f"brief: reports/research/control/briefs/{task}.md")
    lines.append(f"due_utc: {_fmt_value(exp['due_utc'])}")
    lines.append(f"depth_points: {'; '.join(exp['depth_points']) or '-'}")
    lines.append(f"stop_rule: {exp['stop_rule']}")
    lines.append(f"artifacts: {'; '.join(exp['artifacts']) or '-'}")
    return "\n".join(lines)


def cmd_render(args: argparse.Namespace) -> int:
    for directory in program_dirs(args.root):
        if args.program and directory.name != args.program:
            continue
        changed = render_program(directory)
        print(f"{directory.name}: {'updated' if changed else 'unchanged'}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    queue = read_queue(args.queue)
    known = set(all_experiment_ids(args.root))
    failed = False
    for directory in program_dirs(args.root):
        errors, warnings = validate_program(directory, queue, known)
        for warning in warnings:
            print(f"warning: {warning}")
        for error in errors:
            print(f"error: {error}")
        failed = failed or bool(errors)
        if not errors:
            print(f"ok: {directory.name}")
    return 1 if failed else 0


def cmd_next(args: argparse.Namespace) -> int:
    if args.program not in PROGRAMS:
        print(f"unknown program {args.program!r}; choose from {', '.join(PROGRAMS)}")
        return 1
    exp = next_experiment(args.root / args.program, all_experiment_ids(args.root))
    if exp is None:
        print(f"{args.program}: no ready experiment")
        return 1
    print(format_next(args.program, exp))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=PROGRAMS_DIR, help="programs directory")
    sub = parser.add_subparsers(dest="command", required=True)
    render = sub.add_parser("render", help="regenerate the experiment and curve sections")
    render.add_argument("--program", choices=PROGRAMS, default=None)
    render.set_defaults(func=cmd_render)
    check = sub.add_parser("check", help="validate every program directory")
    check.add_argument("--queue", type=Path, default=QUEUE_PATH)
    check.set_defaults(func=cmd_check)
    nxt = sub.add_parser("next", help="print the next ready experiment of a program")
    nxt.add_argument("program")
    nxt.set_defaults(func=cmd_next)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
