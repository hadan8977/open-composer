"""Rebuildable, occurrence-level local text view; original files remain authoritative.

Design reads require explicit visibility. Task recovery additionally permits its own
small text artifacts, never their use as cross-task candidate design evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from open_composer.research.knowledge_memory import canonical_source_url
from open_composer.research.tool_output import page

SCHEMA = 1
ALLOWED = {"public_literature", "train_only_empirical"}
MAX_BYTES = 512_000
ALIASES = {
    "回撤": ("drawdown", "underwater"),
    "同风险": ("risk-matched", "same-risk"),
    "费用": ("cost", "fees"),
    "现金": ("cash",),
    "收益": ("profit", "return"),
    "因子": ("factor",),
    "退出": ("exit",),
}
PATTERNS = (
    "reports/harness/source_cards/*.jsonl",
    "reports/research/iterations/*/external-brief.json",
    "reports/research/iterations/*/decision-record.md",
    "reports/research/iterations/*/evaluation-report.json",
    "research/*/brief.md",
    "research/*/decisions.tsv",
    "research/*/results.json",
    "research/*/scope.json",
    "research/*/scope.md",
    "research/*/runs/*/run.json",
    "research/*/runs/*/brief.md",
    "research/*/runs/*/scope.md",
    "research/*/runs/*/*/reply.json",
    "research/*/runs/*/*/checkpoint.json",
    "research/*/runs/*/*/engine.log",
    "research/*/runs/*/*/stderr.log",
)


def safe_path(root: Path, relative: str) -> Path:
    root = root.resolve()
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Unavailable document")
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Unavailable document")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Unavailable document")
    return path


def read_text(root: Path, relative: str) -> tuple[str, str]:
    path = safe_path(root, relative)
    before = path.stat()
    if not path.is_file() or before.st_size > MAX_BYTES:
        raise ValueError("Unavailable document")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    after = path.stat()
    if (before.st_ino, before.st_mtime_ns, before.st_size) != (
        after.st_ino,
        after.st_mtime_ns,
        after.st_size,
    ) or len(raw) > MAX_BYTES:
        raise ValueError("Document changed while reading")
    return raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()


def tokens(text: str) -> str:
    words = re.findall(r"[a-z0-9_-]+|[\u3400-\u9fff]+", text.lower())
    parts = []
    for word in words:
        parts.append(word)
        if re.fullmatch(r"[\u3400-\u9fff]+", word):
            parts.extend(word[i : i + 2] for i in range(len(word) - 1))
            parts.extend(word)
    return " ".join(parts)


def task_of(relative: str) -> str | None:
    parts = Path(relative).parts
    return parts[1] if len(parts) > 2 and parts[0] == "research" else None


def restricted_payload(value) -> bool:
    """A mixed occurrence is restricted before any text or metadata is admitted."""
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {
                "historical_challenge",
                "lockbox",
                "challenge_result",
                "forward_observation",
            }:
                return True
            if (
                str(key).lower() == "visibility_partition"
                and isinstance(item, str)
                and item in {"restricted", "challenge_result", "forward_observation"}
            ):
                return True
            if restricted_payload(item):
                return True
    elif isinstance(value, list):
        return any(restricted_payload(item) for item in value)
    return False


def occurrences(root: Path, relative: str) -> tuple[str, list[dict]]:
    task = task_of(relative)
    is_log = relative.endswith(".log") and task is not None
    if is_log:
        path = safe_path(root, relative)
        stat = path.stat()
        if not path.is_file():
            raise ValueError("Unavailable document")
        version = hashlib.sha256(
            f"{relative}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}".encode()
        ).hexdigest()
        text = "Task log; get reads a bounded byte range, never default design evidence."
    else:
        text, version = read_text(root, relative)

    def record(key, body, visibility, state, canonical="", supersedes=None):
        return {
            "id": hashlib.sha256(f"{relative}#{key}".encode()).hexdigest()[:24],
            "path": relative,
            "version": version,
            "text": body,
            "visibility": visibility,
            "task": task,
            "state": state,
            "canonical_url": canonical,
            "supersedes": supersedes,
            "updated_at": datetime.fromtimestamp(
                safe_path(root, relative).stat().st_mtime, UTC
            ).isoformat(),
        }

    if is_log:
        return version, [record("document", text, "task_log", "task_log")]
    if relative.startswith("reports/harness/source_cards/"):
        rows = []
        for number, line in enumerate(text.splitlines()):
            if not line.strip() or line.startswith("#"):
                continue
            source = json.loads(line)
            # Filter each occurrence BEFORE canonical grouping/search/counts. No legacy
            # grouped index is consumed, since it has already merged restricted claims.
            visibility = source.get("visibility_partition", "unknown")
            if restricted_payload(source):
                visibility = "restricted"
            canonical = canonical_source_url(str(source.get("source_url", "")))
            rows.append(
                record(
                    number,
                    json.dumps(source, ensure_ascii=False),
                    visibility,
                    source.get("verification_status", "unverified"),
                    canonical,
                    source.get("supersedes"),
                )
            )
        return version, rows
    payload = json.loads(text) if relative.endswith(".json") else {}
    visibility = payload.get("visibility_partition", "unknown")
    if relative.endswith("external-brief.json"):
        # Sources are independent occurrences. Restrict a mixed source, or all
        # sources when the surrounding parent itself carries restricted material.
        parent = {key: value for key, value in payload.items() if key != "sources"}
        parent_restricted = restricted_payload(parent)
        rows = []
        for number, source in enumerate(payload.get("sources", [])):
            part = source.get("visibility_partition", visibility)
            if parent_restricted or restricted_payload(source):
                part = "restricted"
            rows.append(
                record(
                    number,
                    json.dumps(source, ensure_ascii=False),
                    part,
                    "legacy_source",
                    canonical_source_url(source.get("url", "")),
                )
            )
        return version, rows
    # Whole ordinary task/legacy documents have no independently admitted parts.
    if restricted_payload(payload):
        visibility = "restricted"
    return version, [
        record(
            "document",
            text,
            visibility,
            payload.get("status", "task_artifact" if task else "unknown"),
            supersedes=payload.get("supersedes"),
        )
    ]


class KnowledgeSchemaError(ValueError):
    """Unsupported derived schema; safe to report without source details."""


class Knowledge:
    def __init__(self, root: Path):
        self.root = root.resolve()
        path = safe_path(self.root, "runtime/research-tools/knowledge.sqlite3")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA):
            self.db.close()
            raise KnowledgeSchemaError(
                "Unsupported knowledge schema; rebuild derived runtime database"
            )
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, version TEXT,
                available INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS docs(id TEXT PRIMARY KEY, path TEXT, version TEXT,
                text TEXT, visibility TEXT, task TEXT, state TEXT, canonical_url TEXT,
                supersedes TEXT, updated_at TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED, words);
        """)
        self.db.execute(f"PRAGMA user_version={SCHEMA}")
        self.db.commit()

    def close(self):
        self.db.close()

    def index(self, prefixes: list[str] | None = None) -> dict:
        prefixes = prefixes or [
            "research",
            "reports/harness/source_cards",
            "reports/research/iterations",
        ]
        for prefix in prefixes:
            safe_path(self.root, prefix)
            if not any(
                prefix == p.split("/*")[0]
                or prefix.startswith(p.split("/*")[0] + "/")
                or p.startswith(prefix + "/")
                for p in PATTERNS
            ):
                raise ValueError("Index scope is outside text allowlist")

        def scoped(path):
            return any(path == p or path.startswith(p.rstrip("/") + "/") for p in prefixes)

        paths = sorted(
            {
                str(p.relative_to(self.root))
                for pattern in PATTERNS
                for p in self.root.glob(pattern)
                if scoped(str(p.relative_to(self.root)))
            }
        )
        changed = 0
        with self.db:
            old = {
                r["path"]: r for r in self.db.execute("SELECT * FROM files") if scoped(r["path"])
            }
            for relative in sorted(set(paths) | set(old)):
                try:
                    version, rows = occurrences(self.root, relative)
                except (OSError, ValueError, TypeError):
                    if relative in old:
                        # Preserve cached bytes for diagnosis, but never expose stale text.
                        self.db.execute("UPDATE files SET available=0 WHERE path=?", (relative,))
                    continue
                if relative in old and old[relative]["version"] == version:
                    self.db.execute("UPDATE files SET available=1 WHERE path=?", (relative,))
                    continue
                self.db.execute(
                    "DELETE FROM search WHERE id IN (SELECT id FROM docs WHERE path=?)", (relative,)
                )
                self.db.execute("DELETE FROM docs WHERE path=?", (relative,))
                for row in rows:
                    self.db.execute(
                        "INSERT INTO docs VALUES (:id,:path,:version,:text,:visibility,"
                        ":task,:state,:canonical_url,:supersedes,:updated_at)",
                        row,
                    )
                    self.db.execute(
                        "INSERT INTO search(id,words) VALUES (?,?)",
                        (row["id"], tokens(relative + " " + row["text"])),
                    )
                self.db.execute("INSERT OR REPLACE INTO files VALUES (?,?,1)", (relative, version))
                changed += 1
        # Never expose aggregate counts of hidden documents, even in index status.
        return {"schema_version": SCHEMA, "state": "indexed", "derived": True}

    def visible(self, task: str | None = None) -> list[dict]:
        if task is not None and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,59}", task):
            raise ValueError("Invalid task binding")
        rows = self.db.execute(
            "SELECT d.* FROM docs d JOIN files f ON f.path=d.path "
            "WHERE f.available=1 AND (d.visibility IN (?,?) OR "
            "(d.task=? AND d.visibility IN ('unknown','task_log')))",
            (*sorted(ALLOWED), task),
        ).fetchall()
        result = []
        for row in rows:
            try:
                version, current = occurrences(self.root, row["path"])
            except (OSError, ValueError, TypeError):
                continue
            admitted = next((r for r in current if r["id"] == row["id"]), None)
            if (
                version == row["version"]
                and admitted is not None
                and (
                    admitted["visibility"] in ALLOWED
                    or (
                        task is not None
                        and admitted["task"] == task
                        and admitted["visibility"] in {"unknown", "task_log"}
                    )
                )
            ):
                # Re-evaluate policy even when bytes are unchanged and an older
                # derived database previously admitted this occurrence.
                result.append(admitted)
        return result

    def search(self, query: str, *, task: str | None = None, offset=0, budget=2400) -> dict:
        if len(query) > 512:
            raise ValueError("Query exceeds 512 characters")
        expanded = query
        for chinese, english in ALIASES.items():
            if chinese in query or any(term in query.lower().split() for term in english):
                expanded += " " + chinese + " " + " ".join(english)
        words = tokens(expanded).split()
        if not words:
            return {"results": [], **page("", offset=offset, budget=budget)}
        match = " OR ".join('"' + w.replace('"', '""') + '"' for w in dict.fromkeys(words))
        # Visibility determines candidates BEFORE scores and totals; hidden rows
        # cannot affect rank via global FTS bm25 statistics.
        visible = {r["id"]: r for r in self.visible(task)}
        hits = set()
        admitted_ids = list(visible)
        for start in range(0, len(admitted_ids), 500):
            batch = admitted_ids[start : start + 500]
            placeholders = ",".join("?" for _ in batch)
            hits.update(
                r[0]
                for r in self.db.execute(
                    f"SELECT id FROM search WHERE search MATCH ? AND id IN ({placeholders})",
                    (match, *batch),
                )
            )
        candidates = [r for key, r in visible.items() if key in hits]
        candidates.sort(
            key=lambda r: (
                -sum(w in tokens(r["path"] + " " + r["text"]).split() for w in words),
                r["path"],
                r["id"],
            )
        )
        lines = []
        for row in candidates:
            body = row["text"]
            pos = min((body.lower().find(w) for w in words if w in body.lower()), default=0)
            lines.append(
                json.dumps(
                    {k: row[k] for k in ("id", "path", "version", "state", "canonical_url")},
                    ensure_ascii=False,
                )
                + "\n"
                + body[max(0, pos - 50) : pos + 350]
            )
        return {
            "query": query,
            "visible_matches": len(candidates),
            **page("\n\n".join(lines), offset=offset, budget=budget),
        }

    def get(
        self, document_id: str, *, task=None, offset=0, budget=2400, byte_offset: int | None = None
    ) -> dict:
        row = next((r for r in self.visible(task) if r["id"] == document_id), None)
        if row is None:
            return {"state": "unavailable", **page("", offset=0, budget=budget)}
        if row["state"] == "task_log":
            start = byte_offset if byte_offset is not None else offset
            if start < 0 or not 128 <= budget <= 16000:
                raise ValueError("offset >= 0 and byte budget 128..16000 required")
            path = safe_path(self.root, row["path"])
            before = path.stat()
            current_version = hashlib.sha256(
                f"{row['path']}:{before.st_ino}:{before.st_size}:{before.st_mtime_ns}".encode()
            ).hexdigest()
            if current_version != row["version"]:
                return {"state": "unavailable", **page("", budget=budget)}
            with path.open("rb") as stream:
                stream.seek(start)
                raw = stream.read(budget)
            after = path.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                return {"state": "unavailable", **page("", budget=budget)}
            end = start + len(raw)
            return {
                "id": row["id"],
                "path": row["path"],
                "version": row["version"],
                "state": "task_log",
                "text": raw.decode("utf-8", errors="replace"),
                "budget_unit": "bytes",
                "offset_unit": "bytes",
                "budget": budget,
                "omitted": end < after.st_size,
                "next_offset": end if end < after.st_size else None,
            }
        if byte_offset is not None:
            raise ValueError("byte-offset is only for task log documents")
        return {
            "id": row["id"],
            "path": row["path"],
            "version": row["version"],
            "state": row["state"],
            "canonical_url": row["canonical_url"],
            "supersedes": row["supersedes"],
            "updated_at": row["updated_at"],
            **page(row["text"], offset=offset, budget=budget),
        }

    def status(self, *, task=None, offset=0, budget=2400) -> dict:
        rows = self.visible(task)
        return {
            "schema_version": SCHEMA,
            "derived": True,
            "visible_documents": len(rows),
            **page(
                "\n".join(r["id"] + " " + r["path"] for r in rows), offset=offset, budget=budget
            ),
        }

    def context(self, task: str, *, offset=0, budget=2400) -> dict:
        rows = [r for r in self.visible(task) if r["task"] == task]
        # A task view contains only its own admitted artifacts. A run summary uses
        # explicit fields instead of copying entire events/model logs.
        runs = {}
        for row in rows:
            if row["path"].endswith("/run.json"):
                data = json.loads(row["text"])
                phases = data.get("phases", {})
                latest = max(
                    ((name, phase) for name, phase in phases.items() if isinstance(phase, dict)),
                    key=lambda item: (item[1].get("started") or "", item[0]),
                    default=(None, {}),
                )
                runs[row["path"]] = (data, latest)
        ordered_runs = sorted(
            runs,
            key=lambda path: (
                runs[path][0].get("status") in {"running", "starting", "blocked"},
                runs[path][0].get("started") or "",
                path,
            ),
            reverse=True,
        )
        current = ordered_runs[0] if ordered_runs else None
        latest_reply = None
        if current and runs[current][1][0]:
            name, phase = runs[current][1]
            latest_reply = str(Path(current).parent / (phase.get("folder") or name) / "reply.json")

        def order(row):
            # Lexical order put old zero-result checkpoints ahead of the live run.
            rank = (
                0 if row["path"] == current
                else 1 if row["path"] == f"research/{task}/brief.md"
                else 2 if row["path"] == latest_reply
                else 3
            )
            return rank, row["path"]

        lines = []
        for row in sorted(rows, key=order):
            text = row["text"]
            if row["path"] in runs:
                data, (name, phase) = runs[row["path"]]
                summary = {k: data.get(k) for k in ("direction", "run_id", "status")}
                summary["latest_phase"] = {
                    "name": name,
                    **{k: phase.get(k) for k in ("status", "session", "summary", "checkpoint")},
                    "wait_state": (phase.get("wait_state") or {}).get("state"),
                }
                text = json.dumps(summary, ensure_ascii=False)
            lines.append(row["id"] + " " + row["path"] + "\n" + text)
        return {"task": task, **page("\n\n".join(lines), offset=offset, budget=budget)}
