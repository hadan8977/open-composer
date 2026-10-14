"""Research-gate additions (T-20261005-34): trial totals, semantic duplicates,
family quotas, break-even costs and evaluation-standard change logging.

Earlier verified, unchanged dossiers keep their original contract. A dossier's
self-declared date alone cannot opt out of the configured additions. Nothing
here calls an external service or a model: similarity is a local TF-IDF cosine.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("config/research-gate-additions.json")
TRIALS_PATH = Path("reports/research/trials.jsonl")
DIRECTIONS_PATH = Path("reports/research/harvest/directions.jsonl")
ITERATION_ROOT = Path("reports/research/iterations")
FREEZE_FILENAME = "evaluation-standard-freeze.json"
BREAKEVEN_FILENAME = "breakeven-costs.json"
UNCLASSIFIED = "unclassified"
FAMILY_RE = re.compile(r"^[a-z0-9_]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ITER_DATE_RE = re.compile(r"^[a-z]?(\d{4})(\d{2})(\d{2})_")
PROGRAM_RE = re.compile(r"^t\d{8}_(p\d+)_")

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "effective_from": "2026-10-06",
    "grandfathered_iterations": [],
    "family_monthly_candidate_quota": 30,
    "similarity": {"threshold": 0.55, "min_difference_chars": 40, "max_refs_reported": 10},
    "evaluation_standard_path": "config/evaluation-standard-v2.json",
    "evaluation_standard_changelog_path": "config/evaluation-standard-changelog.jsonl",
    "quota_exception_signer_pattern": "主审|lead",
}


# ---------------------------------------------------------------- config / dates


def load_gate_config(root: Path) -> dict[str, Any] | None:
    """Return the gate config, or None when the workspace has no config (inactive)."""
    path = root / CONFIG_PATH
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    cfg = {**DEFAULT_CONFIG, **payload}
    cfg["similarity"] = {**DEFAULT_CONFIG["similarity"], **(payload.get("similarity") or {})}
    return cfg


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def iteration_registered_date(iter_dir: Path) -> date | None:
    """Latest available registration/version date, or None if undated.

    Sources: ``registered_at`` in external-brief.json (written by ``iteration init``),
    the candidate manifest's ``generated_at``/``frozen_at``, the direction review's
    ``reviewed_at`` and the date embedded in the iteration id (``t20261006_...``).
    These editable dates are accounting hints, never proof of grandfathering.
    """
    dates: list[date] = []
    external = _read_json(iter_dir / "external-brief.json")
    if isinstance(external, dict):
        explicit = _parse_date(external.get("registered_at"))
        if explicit is not None:
            dates.append(explicit)
    match = ITER_DATE_RE.match(iter_dir.name)
    if match:
        try:
            dates.append(date(int(match[1]), int(match[2]), int(match[3])))
        except ValueError:
            pass
    for name, keys in (
        ("candidate-manifest.json", ("generated_at", "frozen_at")),
        ("direction-review.json", ("reviewed_at",)),
    ):
        payload = _read_json(iter_dir / name)
        if isinstance(payload, dict):
            for key in keys:
                parsed = _parse_date(payload.get(key))
                if parsed is not None:
                    dates.append(parsed)
    return max(dates) if dates else None


def _unchanged_legacy_contract(
    iter_dir: Path, cfg: dict[str, Any], *, grandfathered: bool = False
) -> bool:
    """Verify an existing frozen inventory entry, not a date asserted by a brief.

    The config is the same trusted control surface as grandfathered_iterations.
    Inventory bindings preserve old scientific definitions; changed versions
    follow the applicable current gate without rewriting the historical result.
    """
    effective = _parse_date(cfg.get("effective_from"))
    if effective is None:
        return False
    inventories = cfg.get("legacy_contracts")
    record = inventories.get(iter_dir.name) if isinstance(inventories, dict) else None
    if not isinstance(record, dict):
        return False
    frozen = _parse_date(record.get("frozen_at"))
    artifacts = record.get("artifacts")
    if (
        frozen is None
        or (not grandfathered and frozen >= effective)
        or not isinstance(artifacts, dict)
        or not artifacts
    ):
        return False
    for raw, digest in artifacts.items():
        path = iter_dir / str(raw)
        if (
            path.parent != iter_dir
            or not SHA256_RE.fullmatch(str(digest))
            or not path.is_file()
            or file_sha256(path) != digest
        ):
            return False
    # A newly added scientific identity file is a new version, too. Inventory
    # entries must describe presence as well as bytes of these original files.
    identity_files = {"external-brief.json", "search-space.json", "candidate-manifest.json"}
    return not any((iter_dir / name).exists() and name not in artifacts for name in identity_files)


def is_new_iteration(iter_dir: Path, cfg: dict[str, Any] | None) -> bool:
    if cfg is None:
        return False
    if iter_dir.name in set(cfg.get("grandfathered_iterations") or []):
        records = cfg.get("legacy_contracts")
        # Preserve the original explicit config exception when migrating older
        # configs; once bound, the exception belongs to that recorded version.
        if not isinstance(records, dict) or iter_dir.name not in records:
            return False
        return not _unchanged_legacy_contract(iter_dir, cfg, grandfathered=True)
    return not _unchanged_legacy_contract(iter_dir, cfg)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- trials ledger


def iteration_program(iter_id: str, external: dict[str, Any] | None = None) -> str:
    if isinstance(external, dict) and str(external.get("program") or "").strip():
        return str(external["program"]).strip()
    match = PROGRAM_RE.match(iter_id)
    if match:
        return match[1].upper()
    if iter_id.startswith("mom_"):
        return "momentum-legacy"
    if re.match(r"^h\d{8}_", iter_id):
        return "hypothesis-batch"
    if re.match(r"^t\d{8}_book_", iter_id):
        return "book"
    return "unassigned"


def manifest_candidates(iter_dir: Path) -> list[dict[str, Any]]:
    """Candidate rows of an iteration's manifest: id, optional family/mechanism/scale flag."""
    manifest = _read_json(iter_dir / "candidate-manifest.json")
    if not isinstance(manifest, dict):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key, id_key in (("candidates", "candidate_id"), ("cells", "cell_id")):
        items = manifest.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = str(item.get(id_key) or item.get("candidate_id") or item.get("id") or "").strip()
            if not cid or cid in seen:
                continue
            seen.add(cid)
            rows.append(
                {
                    "candidate_id": cid,
                    "family": str(item.get("mechanism_family") or ""),
                    "mechanism": str(item.get("mechanism") or item.get("description") or ""),
                    "scale_curve_point": bool(
                        item.get("scale_curve_point") or item.get("scale_point")
                    ),
                    "method": str(item.get("method") or ""),
                    "role": str(item.get("role") or ""),
                }
            )
    return rows


def _ledger_candidate_ids(iter_dir: Path) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for name in ("trial-ledger.jsonl", "trial-ledger.json", "stage-d-trial-ledger.jsonl"):
        path = iter_dir / name
        if not path.is_file():
            continue
        rows: list[Any] = []
        if name.endswith(".jsonl"):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        else:
            payload = _read_json(path)
            if isinstance(payload, list):
                rows = payload
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("candidate_id", "cell_id"):
                value = row.get(key)
                if value and str(value) not in seen:
                    seen.add(str(value))
                    ids.append(str(value))
                    break
    return ids


def load_trials(root: Path) -> list[dict[str, Any]]:
    path = root / TRIALS_PATH
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def append_trials(root: Path, rows: list[dict[str, Any]]) -> int:
    """Append rows whose (iter_id, candidate_id) is not yet recorded. Append-only."""
    existing = {(r.get("iter_id"), r.get("candidate_id")) for r in load_trials(root)}
    fresh: list[dict[str, Any]] = []
    for row in rows:
        key = (row.get("iter_id"), row.get("candidate_id"))
        if key in existing:
            continue
        existing.add(key)
        fresh.append(row)
    if fresh:
        path = root / TRIALS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for row in fresh:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return len(fresh)


def count_trials(
    root: Path, *, family: str | None = None, program: str | None = None
) -> dict[str, Any]:
    rows = load_trials(root)
    if family:
        rows = [r for r in rows if r.get("family") == family]
    if program:
        rows = [r for r in rows if str(r.get("project", "")).lower() == program.lower()]
    return {
        "family": family,
        "program": program,
        "trials": len(rows),
        "scale_curve_points": sum(1 for r in rows if r.get("scale_curve_point")),
        "iterations": len({r.get("iter_id") for r in rows}),
    }


def family_cumulative_trials(root: Path, family: str) -> int:
    """Total registered trials in a mechanism family across all projects (for DSR)."""
    return sum(1 for r in load_trials(root) if r.get("family") == family)


def _external(iter_dir: Path) -> dict[str, Any]:
    payload = _read_json(iter_dir / "external-brief.json")
    return payload if isinstance(payload, dict) else {}


def declared_family(iter_dir: Path) -> str:
    return str(_external(iter_dir).get("mechanism_family") or "").strip()


def build_trial_rows(
    iter_dir: Path,
    *,
    family_lookup: Any = None,
    source: str = "registered",
) -> list[dict[str, Any]]:
    """Trial rows for one iteration (manifest first, trial-ledger ids as fallback)."""
    iter_id = iter_dir.name
    external = _external(iter_dir)
    program = iteration_program(iter_id, external)
    registered = iteration_registered_date(iter_dir)
    manifest = _read_json(iter_dir / "candidate-manifest.json")
    stamp = None
    if isinstance(manifest, dict):
        stamp = str(manifest.get("generated_at") or manifest.get("frozen_at") or "") or None
    if stamp is None and registered is not None:
        stamp = registered.isoformat()
    declared = declared_family(iter_dir)
    iter_family, family_source = declared, "declared" if declared else ""
    if not iter_family and family_lookup is not None:
        guess = family_lookup(iter_dir)
        if guess:
            iter_family, family_source = guess, "nearest_direction"
    if not iter_family:
        iter_family, family_source = UNCLASSIFIED, "none"
    candidates = manifest_candidates(iter_dir)
    origin = f"{source}:candidate-manifest"
    if not candidates:
        candidates = [
            {"candidate_id": cid, "family": "", "scale_curve_point": False}
            for cid in _ledger_candidate_ids(iter_dir)
        ]
        origin = f"{source}:trial-ledger"
    rows = []
    for cand in candidates:
        cand_family = cand.get("family") or ""
        rows.append(
            {
                "project": program,
                "iter_id": iter_id,
                "candidate_id": cand["candidate_id"],
                "family": cand_family or iter_family,
                "family_source": "manifest_candidate" if cand_family else family_source,
                "registered_at": stamp,
                "scale_curve_point": bool(cand.get("scale_curve_point")),
                "source": origin,
            }
        )
    return rows


def backfill_trials(root: Path) -> dict[str, Any]:
    """Backfill trials.jsonl from every iteration's manifest / trial ledger. Counts only."""
    base = root / ITERATION_ROOT
    corpus = _DirectionIndex.load(root)
    rows: list[dict[str, Any]] = []
    uncounted: list[str] = []
    for iter_dir in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        built = build_trial_rows(iter_dir, family_lookup=corpus.nearest_family, source="backfill")
        if not built:
            uncounted.append(iter_dir.name)
        rows.extend(built)
    added = append_trials(root, rows)
    return {
        "candidate_rows": len(rows),
        "added": added,
        "iterations_without_countable_trials": uncounted,
    }


# ---------------------------------------------------------------- similarity

_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")
_STOP = frozenset(
    "the a an of and or to in on for with by from is are be as at this that it its into over "
    "under vs via per not no new test strategy candidate iteration research".split()
)


def tokenize(text: str) -> list[str]:
    tokens = []
    for tok in _TOKEN_RE.findall(text.lower()):
        if len(tok) > 3 and tok.endswith("s") and tok.isascii():
            tok = tok[:-1]
        if tok in _STOP or (tok.isascii() and len(tok) < 2):
            continue
        tokens.append(tok)
    return tokens


class TfidfCorpus:
    """Small TF-IDF cosine index over (ref, text) pairs. Local and deterministic."""

    def __init__(self, docs: list[tuple[str, str]]) -> None:
        self.refs = [ref for ref, _ in docs]
        self._tokens = [Counter(tokenize(text)) for _, text in docs]
        df: Counter[str] = Counter()
        for counts in self._tokens:
            df.update(counts.keys())
        n = max(len(docs), 1)
        self._idf = {tok: math.log((1 + n) / (1 + c)) + 1.0 for tok, c in df.items()}
        self._vecs = [self._vector(c) for c in self._tokens]

    def _vector(self, counts: Counter[str]) -> dict[str, float]:
        vec = {t: (1 + math.log(c)) * self._idf.get(t, 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values()))
        return {t: v / norm for t, v in vec.items()} if norm else {}

    def similarities(self, text: str) -> list[tuple[str, float]]:
        query = self._vector(Counter(tokenize(text)))
        if not query:
            return []
        out = []
        for ref, vec in zip(self.refs, self._vecs, strict=True):
            score = sum(w * vec.get(t, 0.0) for t, w in query.items())
            if score > 0:
                out.append((ref, score))
        out.sort(key=lambda item: -item[1])
        return out


def _direction_text(row: dict[str, Any]) -> str:
    parts = [row.get("name", ""), row.get("family_key", ""), row.get("claim", "")]
    parts.extend(row.get("aliases") or [])
    return " ".join(str(p).replace("_", " ") for p in parts if p)


def iteration_mechanism_text(iter_dir: Path) -> str:
    """Mechanism description of an iteration: declared text, else objectives, else hypotheses."""
    external = _external(iter_dir)
    text = str(external.get("mechanism_description") or "").strip()
    if text:
        return text
    parts = [str(external.get("objective") or "")]
    for name in ("direction-review.json", "search-space.json"):
        payload = _read_json(iter_dir / name)
        if isinstance(payload, dict):
            parts.append(str(payload.get("objective") or ""))
    parts = [p for p in parts if p.strip()]
    if not parts:
        try:
            parts = [(iter_dir / "hypotheses.md").read_text(encoding="utf-8")[:800]]
        except OSError:
            parts = []
    parts.append(str(external.get("strategy_name") or ""))
    parts.append(str(external.get("mechanism_family") or ""))
    return " ".join(p for p in parts if p.strip()).strip()


class _DirectionIndex:
    def __init__(self, directions: list[dict[str, Any]]) -> None:
        self.directions = directions
        self.corpus = TfidfCorpus([(d["id"], _direction_text(d)) for d in directions])
        self.family = {d["id"]: str(d.get("family_key") or "") for d in directions}

    @classmethod
    def load(cls, root: Path) -> _DirectionIndex:
        path = root / DIRECTIONS_PATH
        rows: list[dict[str, Any]] = []
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("id"):
                    rows.append(row)
        return cls(rows)

    def nearest_family(self, iter_dir: Path, minimum: float = 0.25) -> str:
        text = iteration_mechanism_text(iter_dir)
        hits = self.corpus.similarities(text) if text else []
        if hits and hits[0][1] >= minimum:
            return self.family.get(hits[0][0], "")
        return ""


def semantic_similarity_matches(
    iter_dir: Path, root: Path, cfg: dict[str, Any]
) -> list[tuple[str, float]]:
    """Existing directions / other iterations whose mechanism text is similar to this one."""
    iter_id = iter_dir.name
    docs: list[tuple[str, str]] = []
    directions = _DirectionIndex.load(root).directions
    for row in directions:
        blob = json.dumps(row, ensure_ascii=False)
        if iter_id in blob:
            continue
        docs.append((f"direction:{row['id']}", _direction_text(row)))
    base = root / ITERATION_ROOT
    for other in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        if other.name == iter_id:
            continue
        text = iteration_mechanism_text(other)
        if text:
            docs.append((f"iteration:{other.name}", text))
        for cand in manifest_candidates(other):
            if cand["mechanism"]:
                docs.append((f"candidate:{other.name}/{cand['candidate_id']}", cand["mechanism"]))
    corpus = TfidfCorpus(docs)
    queries = [iteration_mechanism_text(iter_dir)]
    queries.extend(c["mechanism"] for c in manifest_candidates(iter_dir) if c["mechanism"])
    best: dict[str, float] = {}
    for query in queries:
        for ref, score in corpus.similarities(query):
            best[ref] = max(best.get(ref, 0.0), score)
    threshold = float(cfg["similarity"]["threshold"])
    limit = int(cfg["similarity"]["max_refs_reported"])
    matches = sorted(((r, s) for r, s in best.items() if s >= threshold), key=lambda i: -i[1])
    return matches[:limit]


def _similarity_blockers(iter_dir: Path, root: Path, cfg: dict[str, Any]) -> list[str]:
    external = _external(iter_dir)
    if not iteration_mechanism_text(iter_dir):
        return ["mechanism_description_missing"]
    minimum = int(cfg["similarity"]["min_difference_chars"])
    declared = external.get("difference_from_existing")
    explained: dict[str, str] = {}
    if isinstance(declared, list):
        for item in declared:
            if isinstance(item, dict) and str(item.get("difference") or "").strip():
                explained[str(item.get("ref") or "")] = str(item["difference"]).strip()
    elif isinstance(declared, dict):
        explained = {str(k): str(v).strip() for k, v in declared.items()}
    blocked = []
    for ref, score in semantic_similarity_matches(iter_dir, root, cfg):
        if len(explained.get(ref, "")) < minimum:
            blocked.append(f"semantic_duplicate_difference_missing:{ref}:{score:.2f}")
    return blocked


# ---------------------------------------------------------------- family quota


def _quota_exception_ok(external: dict[str, Any], cfg: dict[str, Any]) -> bool:
    record = external.get("family_quota_exception")
    if not isinstance(record, dict):
        return False
    signer = str(record.get("signed_by") or "")
    pattern = str(cfg.get("quota_exception_signer_pattern") or "主审|lead")
    return bool(
        re.search(pattern, signer, flags=re.IGNORECASE)
        and len(str(record.get("reason") or "").strip()) >= 20
        and _parse_date(record.get("signed_at"))
    )


def _family_quota_blockers(iter_dir: Path, root: Path, cfg: dict[str, Any]) -> list[str]:
    family = declared_family(iter_dir)
    if not family:
        return ["mechanism_family_missing"]
    if not FAMILY_RE.match(family):
        return [f"mechanism_family_invalid:{family}"]
    registered = iteration_registered_date(iter_dir)
    if registered is None:
        return []
    month = registered.strftime("%Y-%m")
    own = {c["candidate_id"] for c in manifest_candidates(iter_dir)}
    prior = sum(
        1
        for row in load_trials(root)
        if row.get("family") == family
        and str(row.get("registered_at") or "")[:7] == month
        and row.get("iter_id") != iter_dir.name
    )
    total = prior + len(own)
    quota = int(cfg["family_monthly_candidate_quota"])
    if total > quota and not _quota_exception_ok(_external(iter_dir), cfg):
        return [f"family_monthly_quota_exceeded:{family}:{month}:{total}>{quota}"]
    return []


# ---------------------------------------------------------------- break-even cost


def breakeven_cost_bps(gross_return: float, one_way_turnover: float) -> float | None:
    """One-sided cost (bp) at which net return (equivalently net Sharpe or net excess,
    when ``gross_return`` is the gross excess) is zero: gross = turnover * cost.

    ``gross_return`` and ``one_way_turnover`` share a period (e.g. per year, with turnover
    as one-way traded notional / equity). Returns None when turnover is zero.
    """
    if not one_way_turnover or one_way_turnover <= 0 or not math.isfinite(one_way_turnover):
        return None
    return gross_return / one_way_turnover * 1e4


def _breakeven_blockers(iter_dir: Path) -> list[str]:
    path = iter_dir / BREAKEVEN_FILENAME
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return ["breakeven_costs_missing"]
    entries = payload.get("candidates")
    if not isinstance(entries, dict):
        return ["breakeven_costs_candidates_missing"]
    blocked = []
    for cand in manifest_candidates(iter_dir):
        cid = cand["candidate_id"]
        entry = entries.get(cid)
        if not isinstance(entry, dict):
            blocked.append(f"breakeven_cost_missing:{cid}")
            continue
        value = entry.get("breakeven_cost_bps_per_side")
        reason = str(entry.get("not_applicable_reason") or "").strip()
        if value is None:
            if len(reason) < 10:
                blocked.append(f"breakeven_cost_missing:{cid}")
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            blocked.append(f"breakeven_cost_not_numeric:{cid}")
            continue
        gross = entry.get("gross_return")
        turnover = entry.get("one_way_turnover")
        if isinstance(gross, (int, float)) and isinstance(turnover, (int, float)):
            expected = breakeven_cost_bps(float(gross), float(turnover))
            if expected is not None and abs(expected - value) > max(0.05, 0.01 * abs(expected)):
                blocked.append(f"breakeven_cost_inconsistent:{cid}:{value:.3f}!={expected:.3f}")
    return blocked


# ---------------------------------------------------------------- standard changelog


def changelog_rows(root: Path, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = cfg or load_gate_config(root) or DEFAULT_CONFIG
    path = root / str(cfg["evaluation_standard_changelog_path"])
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def changelog_row_problems(row: dict[str, Any]) -> list[str]:
    problems = []
    if not SHA256_RE.match(str(row.get("sha256") or "")):
        problems.append("sha256")
    if _parse_date(row.get("date")) is None:
        problems.append("date")
    for key in ("changed_by", "reason", "signed_by"):
        if not str(row.get(key) or "").strip():
            problems.append(key)
    return problems


def changelog_covers(root: Path, sha256: str, cfg: dict[str, Any] | None = None) -> bool:
    return any(
        row.get("sha256") == sha256 and not changelog_row_problems(row)
        for row in changelog_rows(root, cfg)
    )


def evaluation_standard_status(root: Path, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Current standard hash and whether the changelog covers it (for repo check)."""
    cfg = cfg or load_gate_config(root) or DEFAULT_CONFIG
    path = root / str(cfg["evaluation_standard_path"])
    if not path.is_file():
        return {"present": False}
    sha = file_sha256(path)
    rows = changelog_rows(root, cfg)
    return {
        "present": True,
        "sha256": sha,
        "covered": changelog_covers(root, sha, cfg),
        "entries": len(rows),
        "invalid_entries": [i for i, r in enumerate(rows) if changelog_row_problems(r)],
    }


def _standard_final_blockers(iter_dir: Path, root: Path, cfg: dict[str, Any]) -> list[str]:
    freeze = _read_json(iter_dir / FREEZE_FILENAME)
    if not isinstance(freeze, dict) or not SHA256_RE.match(str(freeze.get("sha256") or "")):
        return ["evaluation_standard_freeze_missing"]
    standard = root / str(cfg["evaluation_standard_path"])
    if not standard.is_file():
        return ["evaluation_standard_file_missing"]
    current = file_sha256(standard)
    if current != freeze["sha256"] and not changelog_covers(root, current, cfg):
        return [f"evaluation_standard_changed_without_changelog:{current[:12]}"]
    return []


def record_prebacktest_gate(iter_id: str, root: Path) -> dict[str, Any]:
    """Freeze the standard hash and register trials for a new iteration (create-only).

    Called after a successful pre-backtest validation. No-op for legacy dossiers.
    """
    cfg = load_gate_config(root)
    iter_dir = root / ITERATION_ROOT / iter_id
    if cfg is None or not iter_dir.is_dir() or not is_new_iteration(iter_dir, cfg):
        return {"active": False}
    result: dict[str, Any] = {"active": True}
    standard = root / str(cfg["evaluation_standard_path"])
    freeze_path = iter_dir / FREEZE_FILENAME
    if standard.is_file() and not freeze_path.exists():
        payload = {
            "iter_id": iter_id,
            "frozen_at": datetime.now(UTC).isoformat(),
            "evaluation_standard_path": str(cfg["evaluation_standard_path"]),
            "sha256": file_sha256(standard),
        }
        freeze_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result["freeze_written"] = True
    result["trials_added"] = append_trials(root, build_trial_rows(iter_dir))
    return result


# ---------------------------------------------------------------- entry point


def gate_additions_blockers(
    iter_id: str, root: Path, *, stage: str
) -> tuple[list[str], dict[str, Any]]:
    """(blockers, info) for the four additions; empty for legacy dossiers or no config."""
    cfg = load_gate_config(root)
    iter_dir = root / ITERATION_ROOT / iter_id
    info: dict[str, Any] = {}
    if stage in {"final", "q2-final"}:
        family = declared_family(iter_dir)
        if not family:
            rows = [r for r in load_trials(root) if r.get("iter_id") == iter_id]
            family = rows[0].get("family", "") if rows else ""
        if family and family != UNCLASSIFIED:
            info = {
                "family": family,
                "family_cumulative_trials": family_cumulative_trials(root, family),
                "note": "use family_cumulative_trials as n_trials in the DSR",
            }
    if cfg is None or not iter_dir.is_dir() or not is_new_iteration(iter_dir, cfg):
        return [], info
    blocked: list[str] = []
    if stage == "pre-backtest":
        blocked.extend(_family_quota_blockers(iter_dir, root, cfg))
        blocked.extend(_similarity_blockers(iter_dir, root, cfg))
    elif stage in {"final", "q2-final"}:
        blocked.extend(_standard_final_blockers(iter_dir, root, cfg))
        blocked.extend(_breakeven_blockers(iter_dir))
        registered = {
            r.get("candidate_id") for r in load_trials(root) if r.get("iter_id") == iter_id
        }
        missing = [c["candidate_id"] for c in manifest_candidates(iter_dir)]
        missing = [c for c in missing if c not in registered]
        if missing:
            blocked.append(f"trials_not_registered:{len(missing)}")
    return blocked, info


def trials_summary_by_family(root: Path) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for row in load_trials(root):
        out[str(row.get("family") or UNCLASSIFIED)] += 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
