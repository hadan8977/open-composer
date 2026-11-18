"""Rebuildable, occurrence-level local text view; original files remain authoritative.

Design reads require explicit visibility. Task recovery additionally permits its own
small text artifacts, never their use as cross-task candidate design evidence.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import yaml

from open_composer.research.knowledge_memory import canonical_source_url
from open_composer.research.tool_output import page

SCHEMA = 2
ALLOWED = {
    "public_literature",
    "train_only_empirical",
    "internal_record",
    "owner_record",
}
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
    "reports/research/trials.jsonl",
    "reports/research/archive/batches/*.json",
    "reports/research/intel/*.md",
    "reports/research/intel/*.json",
    "reports/research/intel/**/*.md",
    "reports/research/intel/**/*.json",
    "reports/owner/verdicts.jsonl",
    "capabilities/registry.yaml",
    "research/*/brief.md",
    "research/*/decisions.tsv",
    "research/*/results.json",
    "research/*/scope.json",
    "research/*/scope.md",
    "research/**/trials.jsonl",
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
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Unavailable document")
    raw = path.read_bytes()
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
            "policy_visibility": visibility,
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
    if relative.endswith("trials.jsonl"):
        rows = []
        for number, line in enumerate(text.splitlines()):
            if not line.strip() or line.startswith("#"):
                continue
            trial = json.loads(line)
            rows.append(
                record(
                    number,
                    json.dumps(trial, ensure_ascii=False),
                    "internal_record",
                    str(trial.get("status") or trial.get("event") or "trial"),
                    supersedes=trial.get("supersedes"),
                )
            )
        return version, rows
    if relative == "reports/owner/verdicts.jsonl":
        rows = []
        for number, line in enumerate(text.splitlines()):
            if not line.strip() or line.startswith("#"):
                continue
            verdict = json.loads(line)
            rows.append(
                record(
                    number,
                    json.dumps(verdict, ensure_ascii=False),
                    "owner_record",
                    "owner_verdict",
                    supersedes=verdict.get("supersedes"),
                )
            )
        return version, rows
    if relative.endswith("decisions.tsv"):
        rows = []
        for number, row in enumerate(csv.DictReader(text.splitlines(), delimiter="\t")):
            rows.append(
                record(
                    number,
                    json.dumps(row, ensure_ascii=False),
                    "internal_record",
                    str(row.get("decision") or "decision"),
                    supersedes=row.get("supersedes"),
                )
            )
        return version, rows
    if relative == "capabilities/registry.yaml":
        payload = yaml.safe_load(text) or {}
        rows = []
        for number, capability in enumerate(payload.get("capabilities", [])):
            rows.append(
                record(
                    number,
                    json.dumps(capability, ensure_ascii=False),
                    "internal_record",
                    str(capability.get("status") or "capability"),
                    f"capability:{capability.get('id', number)}",
                )
            )
        return version, rows
    if relative.startswith("reports/research/archive/batches/"):
        payload = json.loads(text)
        visibility = "restricted" if restricted_payload(payload) else "internal_record"
        return version, [record("document", text, visibility, "archive")]
    if relative.startswith("reports/research/intel/"):
        payload = json.loads(text) if relative.endswith(".json") else {}
        visibility = "restricted" if restricted_payload(payload) else "internal_record"
        return version, [record("document", text, visibility, "intel")]
    if relative.startswith("reports/harness/source_cards/"):
        rows = []
        for number, line in enumerate(text.splitlines()):
            if not line.strip() or line.startswith("#"):
                continue
            source = json.loads(line)
            # External source cards default to public literature unless they carry
            # an explicit restricted marker. Missing metadata no longer hides the
            # whole external corpus; restricted payloads are still filtered first.
            visibility = source.get("visibility_partition") or "public_literature"
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
        if version == 1:
            # The derived database is rebuildable; migrate by dropping the old view.
            self.db.executescript(
                "DROP TABLE IF EXISTS search; DROP TABLE IF EXISTS docs;"
                "DROP TABLE IF EXISTS files; DROP TABLE IF EXISTS quarantine;"
                "DROP TABLE IF EXISTS meta;"
            )
            version = 0
        if version not in (0, SCHEMA):
            self.db.close()
            raise KnowledgeSchemaError(
                "Unsupported knowledge schema; rebuild derived runtime database"
            )
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS files(
                path TEXT PRIMARY KEY, version TEXT, available INTEGER NOT NULL DEFAULT 1,
                mtime_ns INTEGER, size INTEGER);
            CREATE TABLE IF NOT EXISTS docs(
                id TEXT PRIMARY KEY, path TEXT, version TEXT, text TEXT,
                visibility TEXT, policy_visibility TEXT, task TEXT, state TEXT,
                canonical_url TEXT, supersedes TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS quarantine(
                path TEXT, line INTEGER, error TEXT, PRIMARY KEY(path, line));
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS canonical_docs(
                doc_id TEXT PRIMARY KEY, canonical_id TEXT, usage_count INTEGER);
            CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED, words);
        """)
        self.db.execute(f"PRAGMA user_version={SCHEMA}")
        self.db.commit()

    def close(self):
        self.db.close()

    def _meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def index(self, prefixes: list[str] | None = None) -> dict:
        prefixes = prefixes or [
            "research",
            "reports/harness/source_cards",
            "reports/research",
            "reports/owner",
            "capabilities",
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
                p.relative_to(self.root).as_posix()
                for pattern in PATTERNS
                for p in self.root.glob(pattern)
                if scoped(p.relative_to(self.root).as_posix())
            }
        )
        changed = 0
        valid_cards = 0
        invalid_cards = 0
        with self.db:
            old = {
                r["path"]: r for r in self.db.execute("SELECT * FROM files") if scoped(r["path"])
            }
            for relative in sorted(set(paths) | set(old)):
                try:
                    version, rows = occurrences(self.root, relative)
                except json.JSONDecodeError as exc:
                    # A broken line must not leave old bytes searchable. Quarantine it
                    # and make the file unavailable until it is fixed and reindexed.
                    self.db.execute(
                        "DELETE FROM search WHERE id IN (SELECT id FROM docs WHERE path=?)",
                        (relative,),
                    )
                    self.db.execute("DELETE FROM docs WHERE path=?", (relative,))
                    self.db.execute("DELETE FROM quarantine WHERE path=?", (relative,))
                    self.db.execute(
                        "INSERT INTO quarantine(path,line,error) VALUES (?,?,?)",
                        (relative, 0, str(exc)[:500]),
                    )
                    self.db.execute("UPDATE files SET available=0 WHERE path=?", (relative,))
                    continue
                except (OSError, ValueError, TypeError):
                    if relative in old:
                        # Preserve cached bytes for diagnosis, but never expose stale text.
                        self.db.execute("UPDATE files SET available=0 WHERE path=?", (relative,))
                    continue
                stat = safe_path(self.root, relative).stat()
                if (
                    relative in old
                    and old[relative]["version"] == version
                    and old[relative]["mtime_ns"] == stat.st_mtime_ns
                    and old[relative]["size"] == stat.st_size
                ):
                    self.db.execute("UPDATE files SET available=1 WHERE path=?", (relative,))
                    continue
                self.db.execute(
                    "DELETE FROM search WHERE id IN (SELECT id FROM docs WHERE path=?)", (relative,)
                )
                self.db.execute("DELETE FROM docs WHERE path=?", (relative,))
                self.db.execute("DELETE FROM quarantine WHERE path=?", (relative,))
                for row in rows:
                    self.db.execute(
                        "INSERT INTO docs VALUES (:id,:path,:version,:text,:visibility,"
                        ":policy_visibility,:task,:state,:canonical_url,:supersedes,:updated_at)",
                        row,
                    )
                    self.db.execute(
                        "INSERT INTO search(id,words) VALUES (?,?)",
                        (row["id"], tokens(relative + " " + row["text"])),
                    )
                    if relative.startswith("reports/harness/source_cards/"):
                        try:
                            from open_composer.models.source_card import SourceCard

                            SourceCard.model_validate(json.loads(row["text"]))
                            valid_cards += 1
                        except Exception:
                            invalid_cards += 1
                self.db.execute(
                    "INSERT OR REPLACE INTO files(path,version,available,mtime_ns,size) "
                    "VALUES (?,?,1,?,?)",
                    (relative, version, stat.st_mtime_ns, stat.st_size),
                )
                changed += 1
            self.db.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES ('indexed_at',?)",
                (datetime.now(UTC).isoformat(),),
            )
            self._rebuild_canonical()
            # Report conformance from the whole stored corpus, not only changed files.
            valid_cards = 0
            invalid_cards = 0
            for row in self.db.execute(
                "SELECT text FROM docs WHERE path LIKE 'reports/harness/source_cards/%'"
            ):
                try:
                    from open_composer.models.source_card import SourceCard

                    SourceCard.model_validate(json.loads(row["text"]))
                    valid_cards += 1
                except Exception:
                    invalid_cards += 1
        return {
            "schema_version": SCHEMA,
            "state": "indexed",
            "derived": True,
            "changed_files": changed,
            "documents": self.db.execute("SELECT count(*) FROM docs").fetchone()[0],
            "quarantined": self.db.execute("SELECT count(*) FROM quarantine").fetchone()[0],
            "source_cards": {"valid": valid_cards, "invalid": invalid_cards},
            "canonical_source_cards": self.db.execute(
                "SELECT count(DISTINCT canonical_id) FROM canonical_docs"
            ).fetchone()[0],
            "duplicate_source_rows": self.db.execute(
                "SELECT count(*) - count(DISTINCT canonical_id) FROM canonical_docs"
            ).fetchone()[0],
            "indexed_at": self.db.execute(
                "SELECT value FROM meta WHERE key='indexed_at'"
            ).fetchone()[0],
        }

    def _rebuild_canonical(self) -> None:
        """Collapse exact source-card duplicates in the derived read view.

        Raw rows remain indexed for audit; search/get returns one canonical row
        with usage_count so repeated citations are not mistaken for independent
        evidence.
        """
        self.db.execute("DELETE FROM canonical_docs")
        rows = self.db.execute(
            "SELECT id,path,text,canonical_url FROM docs "
            "WHERE path LIKE 'reports/harness/source_cards/%'"
        ).fetchall()
        groups = {}
        for row in rows:
            try:
                source = json.loads(row["text"])
            except (TypeError, json.JSONDecodeError):
                continue
            claim = re.sub(r"\s+", " ", str(source.get("claim") or "")).strip()
            key = (row["canonical_url"], claim)
            groups.setdefault(key, []).append(row)
        for group in groups.values():
            canonical = min(group, key=lambda row: (row["path"], row["id"]))
            count = len(group)
            self.db.executemany(
                "INSERT OR REPLACE INTO canonical_docs(doc_id,canonical_id,usage_count) "
                "VALUES (?,?,?)",
                [(row["id"], canonical["id"], count) for row in group],
            )

    def task_names(self, limit: int = 500) -> list[str]:
        rows = self.db.execute(
            "SELECT task, max(updated_at) AS latest FROM docs "
            "WHERE task IS NOT NULL AND task != '' GROUP BY task "
            "ORDER BY latest DESC, task LIMIT ?",
            (limit,),
        ).fetchall()
        return [row[0] for row in rows]

    def _validate_task(self, task: str | None) -> None:
        if task is not None and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,59}", task):
            examples = ", ".join(self.task_names(8))
            raise ValueError(
                "Invalid --task. Use the research direction directory name"
                + (f", e.g. {examples}" if examples else "")
            )

    def tasks(self, *, offset=0, budget=2400) -> dict:
        names = self.task_names()
        return {
            "tasks": names,
            "count": len(names),
            **page("\n".join(names), offset=offset, budget=budget),
        }

    def visible(self, task: str | None = None) -> list[dict]:
        self._validate_task(task)
        placeholders = ",".join("?" for _ in ALLOWED)
        rows = self.db.execute(
            "SELECT d.*, f.mtime_ns, f.size FROM docs d JOIN files f ON f.path=d.path "
            f"WHERE f.available=1 AND (d.visibility IN ({placeholders}) OR "
            "(d.task=? AND d.visibility IN ('unknown','task_log')))",
            (*sorted(ALLOWED), task),
        ).fetchall()
        # Trust the index only while the source file is unchanged and the stored
        # policy visibility has not been edited. This is O(files), not O(bytes).
        admitted = []
        checked = {}
        for row in rows:
            if row["visibility"] != row["policy_visibility"]:
                continue
            relative = row["path"]
            if relative not in checked:
                try:
                    stat = safe_path(self.root, relative).stat()
                    checked[relative] = (
                        stat.st_mtime_ns == row["mtime_ns"] and stat.st_size == row["size"]
                    )
                except (OSError, ValueError, TypeError):
                    checked[relative] = False
            if checked[relative]:
                admitted.append(dict(row))
        return admitted

    def _source_quality(self, row) -> dict:
        if not row["path"].startswith("reports/harness/source_cards/"):
            return {}
        source = {}
        schema_valid = False
        try:
            from open_composer.models.source_card import SourceCard

            source = json.loads(row["text"])
            SourceCard.model_validate(source)
            schema_valid = True
        except Exception:
            schema_valid = False
        return {
            "schema_valid": schema_valid,
            "quote": bool(source.get("quote")),
            "locator": bool(source.get("locator") or source.get("evidence_locator")),
        }

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
        # Score the FTS matches once, then filter through the visible set. Hidden
        # text is never returned; only hidden rows may influence corpus statistics.
        visible = {r["id"]: r for r in self.visible(task)}
        scores = {
            row["id"]: row["score"]
            for row in self.db.execute(
                "SELECT id, bm25(search) AS score FROM search WHERE search MATCH ? ORDER BY score",
                (match,),
            )
            if row["id"] in visible
        }
        candidates = [r for key, r in visible.items() if key in scores]
        if candidates:
            ids = [row["id"] for row in candidates]
            canonical = {}
            for start in range(0, len(ids), 500):
                batch = ids[start : start + 500]
                placeholders = ",".join("?" for _ in batch)
                for row in self.db.execute(
                    f"SELECT doc_id, canonical_id, usage_count FROM canonical_docs "
                    f"WHERE doc_id IN ({placeholders})",
                    batch,
                ):
                    canonical[row["doc_id"]] = (row["canonical_id"], row["usage_count"])
            deduped = []
            seen = set()
            for row in candidates:
                canonical_id, usage_count = canonical.get(row["id"], (row["id"], 1))
                if canonical_id in seen:
                    continue
                seen.add(canonical_id)
                row["canonical_id"] = canonical_id
                row["usage_count"] = usage_count
                deduped.append(row)
            candidates = deduped

        def kind_of(row):
            path = row["path"]
            if path.endswith("decisions.tsv"):
                return "decision"
            if path == "capabilities/registry.yaml":
                return "capability"
            if path == "reports/owner/verdicts.jsonl":
                return "owner_verdict"
            if path.startswith("reports/harness/source_cards/"):
                return "source_card"
            if path.endswith("trials.jsonl"):
                return "trial"
            if path.startswith("reports/research/archive/"):
                return "archive"
            if path.startswith("reports/research/intel/"):
                return "intel"
            return "task"

        if task is None:
            priority = {
                "decision": 0,
                "capability": 1,
                "owner_verdict": 2,
                "source_card": 3,
                "trial": 4,
                "archive": 5,
                "task": 6,
                "intel": 9,
            }
        else:
            priority = {
                "task": 0,
                "decision": 1,
                "capability": 2,
                "owner_verdict": 3,
                "source_card": 4,
                "trial": 5,
                "archive": 6,
                "intel": 9,
            }
        groups = {}
        for row in candidates:
            groups.setdefault(kind_of(row), []).append(row)
        lines = []
        for kind in sorted(groups, key=lambda name: priority.get(name, 7)):
            group = sorted(
                groups[kind],
                key=lambda r: (
                    0 if task is not None and r["task"] == task else 1,
                    scores[r["id"]],
                    r["path"],
                    r["id"],
                ),
            )
            lines.append(f"## {kind} ({len(group)} matches)")
            for row in group[:3]:
                body = row["text"]
                pos = min(
                    (body.lower().find(w) for w in words if w in body.lower()),
                    default=0,
                )
                lines.append(
                    json.dumps(
                        {
                            **{
                                k: row[k]
                                for k in ("id", "path", "version", "state", "canonical_url")
                            },
                            "canonical_id": row.get("canonical_id", row["id"]),
                            "usage_count": row.get("usage_count", 1),
                            **self._source_quality(row),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                    + body[max(0, pos - 50) : pos + 350]
                )
        return {
            "query": query,
            "visible_matches": len(candidates),
            "canonical_matches": len(candidates),
            "visible_documents": len(visible),
            "hidden_by_policy": max(
                0,
                self.db.execute(
                    "SELECT count(*) FROM docs d JOIN files f ON f.path=d.path WHERE f.available=1"
                ).fetchone()[0]
                - len(visible),
            ),
            "index_built_at": self._meta("indexed_at"),
            "zero_result_reason": (
                None if candidates else "no_visible_documents" if not visible else "no_match"
            ),
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
            # visible() already admitted only an unchanged file of row["size"] bytes.
            with safe_path(self.root, row["path"]).open("rb") as stream:
                stream.seek(start)
                raw = stream.read(budget)
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
                "omitted": end < row["size"],
                "next_offset": end if end < row["size"] else None,
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
            **self._source_quality(row),
            **page(row["text"], offset=offset, budget=budget),
        }

    def status(self, *, task=None, offset=0, budget=2400) -> dict:
        rows = self.visible(task)
        total = self.db.execute(
            "SELECT count(*) FROM docs d JOIN files f ON f.path=d.path WHERE f.available=1"
        ).fetchone()[0]
        quarantine = self.db.execute("SELECT count(*) FROM quarantine").fetchone()[0]
        return {
            "schema_version": SCHEMA,
            "derived": True,
            "visible_documents": len(rows),
            "documents": total,
            "quarantined": quarantine,
            "hidden_by_policy": max(0, total - len(rows)),
            "canonical_source_cards": self.db.execute(
                "SELECT count(DISTINCT canonical_id) FROM canonical_docs"
            ).fetchone()[0],
            "duplicate_source_rows": self.db.execute(
                "SELECT count(*) - count(DISTINCT canonical_id) FROM canonical_docs"
            ).fetchone()[0],
            "index_built_at": self._meta("indexed_at"),
            **page(
                "\n".join(r["id"] + " " + r["path"] for r in rows), offset=offset, budget=budget
            ),
        }

    def failures(self, query: str | None = None, *, task=None, offset=0, budget=2400) -> dict:
        """Failed/interrupted trials and branch/park/revise decisions over the index."""
        rows = self.visible(task)
        items = []
        for row in rows:
            path = row["path"]
            if task is not None and row.get("task") not in (None, task):
                continue
            if path.endswith("trials.jsonl"):
                try:
                    trial = json.loads(row["text"])
                except (TypeError, json.JSONDecodeError):
                    continue
                status = str(trial.get("status") or "")
                event = str(trial.get("event") or "")
                if status not in {"failed", "interrupted"} and not (
                    event == "finished" and status in {"failed", "interrupted"}
                ):
                    continue
                body = json.dumps(trial, ensure_ascii=False)
                if query and query.lower() not in (body + " " + path).lower():
                    continue
                items.append(
                    (
                        str(trial.get("trial_id") or row["id"]),
                        status or event,
                        path,
                        str(trial.get("note") or trial.get("evidence") or ""),
                    )
                )
            elif path.endswith("decisions.tsv"):
                try:
                    decision_row = json.loads(row["text"])
                except (TypeError, json.JSONDecodeError):
                    continue
                decision = str(decision_row.get("decision") or "")
                body = json.dumps(decision_row, ensure_ascii=False)
                if not decision.lower().startswith(("branch", "park", "revise")):
                    continue
                if query and query.lower() not in (body + " " + path).lower():
                    continue
                items.append(
                    (
                        str(
                            decision_row.get("variant")
                            or decision_row.get("stage")
                            or decision_row.get("at_utc")
                            or row["id"]
                        ),
                        decision or "decision",
                        path,
                        str(decision_row.get("note") or decision_row.get("result") or ""),
                    )
                )
        seen = set()
        unique = []
        for item in items:
            key = (item[0], item[1], item[2])
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        lines = [
            f"{trial_id} {status} {path}\n{note}"[:800]
            for trial_id, status, path, note in unique[:100]
        ]
        available = None
        if query and not unique:
            available = self.failures(None, task=task, budget=128)["failed"]
        return {
            "query": query,
            "task": task,
            "failed": len(unique),
            "available_failures": available,
            **page("\n\n".join(lines), offset=offset, budget=budget),
        }

    def map(self, query: str | None = None, *, task=None, offset=0, budget=2400) -> dict:
        """Query/ direction-scoped map; no project-wide static truth."""
        if not query and not task:
            return {"state": "need_query_or_task", **page("", offset=offset, budget=budget)}
        rows = self.visible(task)
        if query:
            words = set(tokens(query).split())

            def score(row):
                body = (row["path"] + " " + row["text"]).lower()
                return -sum(body.count(word) for word in words)

            selected = sorted(rows, key=lambda row: (score(row), row["path"]))[:30]
            label = f"query={query}"
        else:
            prefix = f"research/{task}/"
            selected = [row for row in rows if row["path"].startswith(prefix)]

            def rank(row):
                path = row["path"]
                return (
                    0
                    if path == prefix + "brief.md"
                    else 1
                    if path.endswith("decisions.tsv")
                    else 2
                    if path.endswith("run.json")
                    else 3
                    if path.endswith("trials.jsonl")
                    else 4,
                    path,
                )

            selected = sorted(selected, key=rank)[:30]
            label = f"task={task}"
        lines = []
        for row in selected:
            body = row["text"].replace("\n", " ")[:180]
            lines.append(
                json.dumps(
                    {
                        "id": row["id"],
                        "path": row["path"],
                        "state": row["state"],
                        "task": row["task"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + body
            )
        return {
            "map": label,
            "documents": len(selected),
            **page("\n\n".join(lines), offset=offset, budget=budget),
        }

    def context(self, task: str, *, offset=0, budget=2400) -> dict:
        self._validate_task(task)
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
            latest_reply = (
                Path(current).parent / (phase.get("folder") or name) / "reply.json"
            ).as_posix()

        def order(row):
            # Lexical order put old zero-result checkpoints ahead of the live run.
            rank = (
                0
                if row["path"] == current
                else 1
                if row["path"] == f"research/{task}/brief.md"
                else 2
                if row["path"] == latest_reply
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
