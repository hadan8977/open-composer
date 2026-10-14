"""Every command this repo builds for scripts/run_capped.sh must fit the memory budget.

On 2026-10-07 the nightly paper-data refresh (scripts/refresh_equity_book_live.py) built
``run_capped.sh --mem 1.8G`` without ``--class paper``. Since the owner's memory budget
(docs/runbook-memory.zh.md) the research class refuses more than ``job_max_mb`` (then
1.2G, 2.4G since 2026-10-08), so the 22:45 refresh stopped at its first step and the next
day's paper targets were not written. This test reads the commands the code actually
builds -- Python via ``ast`` (docstrings and comments excluded), shell scripts and the
Makefile line by line -- and requires: research class at most ``job_max_mb``, anything
bigger ``--class paper``.

Usage examples in docstrings are not checked: copied by hand they fail at once with
"run it on Modal or shrink the job", which is the intended signal for research jobs.
"""

from __future__ import annotations

import ast
import functools
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB_MAX_MB = int(json.loads((ROOT / "config" / "memory-budget.json").read_text())["job_max_mb"])

# Callers that feed paper orders: they must say --class paper whatever their size.
PAPER_CALLERS = {
    "scripts/refresh_equity_book_live.py",
    "scripts/install_rotation_sleeve_cron.sh",
    "scripts/refresh_insider_features_for_paper.sh",
    "open_composer/execution/schedule.py",
}
_STRIP = "\"')(\\`;"


def mem_mb(value: str) -> int | None:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([KMG]?)", value.strip().upper())
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2)
    if unit == "G":
        n *= 1024
    elif unit == "K":
        n /= 1024
    elif unit == "":
        n /= 1 << 20
    return int(n)


def parse_invocation(tokens: list[str]) -> tuple[str | None, str] | None:
    """(--mem, --class) of a full run_capped command; None without the ``--`` separator."""
    tokens = [t.strip(_STRIP) for t in tokens]
    if "--" not in tokens:
        return None
    head = tokens[: tokens.index("--")]
    mem, klass = None, "research"
    for flag, value in zip(head, head[1:], strict=False):
        if flag == "--mem":
            mem = value
        elif flag == "--class":
            klass = value
    return mem, klass


def _after_wrapper(text: str) -> list[str]:
    _, _, rest = text.partition("run_capped.sh")
    return rest.split()


def _commands_in(text: str) -> list[list[str]]:
    """Token lists after each run_capped.sh in a string (one string may hold several)."""
    return [chunk.split() for chunk in text.split("run_capped.sh")[1:]]


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def _module_strings(tree: ast.Module) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            out[node.targets[0].id] = node.value.value
    return out


def _mentions_wrapper(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Constant) and isinstance(n.value, str) and "run_capped" in n.value
        for n in ast.walk(node)
    )


def python_invocations(path: Path) -> list[tuple[int, list[str]]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstring_ids(tree)
    names = _module_strings(tree)
    found: list[tuple[int, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.List | ast.Tuple):
            for i, elt in enumerate(node.elts):
                if not _mentions_wrapper(elt):
                    continue
                if (
                    isinstance(elt, ast.Constant)
                    and isinstance(elt.value, str)
                    and _after_wrapper(elt.value)
                ):
                    continue  # a whole command in one string: read below as a string
                tokens = []
                for e in node.elts[i + 1 :]:
                    if isinstance(e, ast.Constant) and isinstance(e.value, str):
                        tokens.append(e.value)
                    elif isinstance(e, ast.Name) and e.id in names:
                        tokens.append(names[e.id])
                    else:
                        tokens.append("<expr>")
                found.append((node.lineno, tokens))
                skip.update(id(n) for n in ast.walk(node))
                break
        elif isinstance(node, ast.JoinedStr):
            text = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
            if "run_capped" in text:
                found.extend((node.lineno, tokens) for tokens in _commands_in(text))
                skip.update(id(n) for n in ast.walk(node))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "run_capped.sh" in node.value
            and id(node) not in skip
        ):
            found.extend((node.lineno, tokens) for tokens in _commands_in(node.value))
    return found


def line_invocations(path: Path) -> list[tuple[int, list[str]]]:
    found = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or "run_capped.sh" not in stripped:
            continue
        found.extend((lineno, tokens) for tokens in _commands_in(stripped))
    return found


@functools.cache
def all_invocations() -> list[tuple[str, int, str | None, str]]:
    files = [
        *sorted((ROOT / "scripts").rglob("*.py")),
        *sorted((ROOT / "open_composer").rglob("*.py")),
        *sorted((ROOT / "scripts").rglob("*.sh")),
        *sorted((ROOT / "deploy").rglob("*.sh")),
        ROOT / "Makefile",
    ]
    rows = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if rel == "scripts/run_capped.sh" or "/." in rel:
            continue
        if "run_capped" not in path.read_text(encoding="utf-8", errors="replace"):
            continue
        reader = python_invocations if path.suffix == ".py" else line_invocations
        for lineno, tokens in reader(path):
            parsed = parse_invocation(tokens)
            if parsed is not None:
                rows.append((rel, lineno, *parsed))
    return rows


def test_parse_invocation_shapes() -> None:
    assert parse_invocation(["--class", "paper", "--mem", "1.8G", "--", "uv"]) == ("1.8G", "paper")
    assert parse_invocation(["--mem", "1.8G", '--"']) == ("1.8G", "research")
    assert parse_invocation(["--mem", "1.8G", "--)"]) == ("1.8G", "research")
    assert parse_invocation(["`--mem", "1.8G`)"]) is None  # prose, not a command
    assert mem_mb("1.2G") == 1228 and mem_mb("1200M") == 1200 and mem_mb("$MEM") is None


def test_scanner_sees_built_commands_but_not_docstrings(tmp_path: Path) -> None:
    src = tmp_path / "x.py"
    src.write_text(
        '"""Run: scripts/run_capped.sh --mem 1.8G -- uv run python x.py"""\n'
        'CAPPED = ["scripts/run_capped.sh", "--mem", "1.8G", "--"]\n'
        "def f(root, a):\n"
        '    """scripts/run_capped.sh --mem 9G -- doc only"""\n'
        '    return [str(root / "scripts/run_capped.sh"), "--mem", MEM, "--", *a]\n'
        'MEM = "1.8G"\n'
        'LINE = f"cd {1} && ./scripts/run_capped.sh --class paper --mem 2G -- run"\n'
        'BOTH = ("scripts/run_capped.sh --mem 1G -- a "\n'
        '        "scripts/run_capped.sh --mem 3G -- b")\n'
        "HOWTO = [\n"
        '    "scripts/run_capped.sh --mem 1.0G -- uv run python a.py",\n'
        '    "scripts/run_capped.sh --mem 1.5G -- uv run python b.py",\n'
        "]\n"
    )
    got = sorted((n, parse_invocation(t)) for n, t in python_invocations(src))
    assert got == [
        (2, ("1.8G", "research")),
        (5, ("1.8G", "research")),
        (7, ("2G", "paper")),
        (8, ("1G", "research")),
        (8, ("3G", "research")),
        (11, ("1.0G", "research")),
        (12, ("1.5G", "research")),
    ]


def test_autonomy_jobs_use_the_budget_job_limit(tmp_path: Path) -> None:
    from open_composer.research.autonomy import research_job_mem

    assert research_job_mem(ROOT) == f"{JOB_MAX_MB}M"
    assert research_job_mem(tmp_path) == "2.4G"  # budget file missing: the documented limit


def test_no_built_command_exceeds_the_research_job_limit() -> None:
    rows = all_invocations()
    assert rows, "scanner found no run_capped commands at all"
    over = [
        f"{rel}:{lineno} --mem {mem} (class {klass})"
        for rel, lineno, mem, klass in rows
        if klass != "paper" and (mb := mem_mb(mem or "")) is not None and mb > JOB_MAX_MB
    ]
    assert not over, (
        f"research-class run_capped commands over the {JOB_MAX_MB} MB job limit would be "
        f"refused at run time; use --class paper for paper jobs, else <={JOB_MAX_MB}M "
        f"or Modal: {over}"
    )


def test_paper_callers_say_class_paper() -> None:
    rows = all_invocations()
    for rel in sorted(PAPER_CALLERS):
        mine = [r for r in rows if r[0] == rel]
        assert mine, f"{rel}: no run_capped command found (moved? update PAPER_CALLERS)"
        assert all(klass == "paper" for _, _, _, klass in mine), (rel, mine)
