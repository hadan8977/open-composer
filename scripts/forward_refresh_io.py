"""Bounded disk admission and isolated reader publication for the existing refresh."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from forward_feature_epoch import publish_forward_table
from forward_publication import atomic_json
from prepare_host_forward_version import sha256

READER_OUTPUTS = {
    "panel": [("panel/{year}.parquet", ["symbol", "trade_date"])],
    "prices": [("prices/{year}.parquet", ["symbol", "trade_date"])],
    "etf": [("etf_daily.parquet", ["symbol", "trade_date"])],
    "risk": [
        ("risk/factor_returns_{year}.parquet", ["factor", "trade_date"]),
        ("risk/residuals_{year}.parquet", ["symbol", "trade_date"]),
        ("risk/exposures_{year}.parquet", ["symbol", "trade_date"]),
        ("risk/cov_{year}.parquet", ["factor_i", "factor_j", "trade_date"]),
    ],
    "signals": [("signals/{year}.parquet", ["symbol", "trade_date"])],
    "alpha": [("alpha/book_v1/themes_{year}.parquet", ["symbol", "trade_date"])],
}


def reader_name(relative: str) -> str:
    return "reader-" + relative.replace("/", "-").replace(".parquet", "")


def live_view_plan(live: Path, year: int) -> list[dict]:
    """Stat-only inventory of exactly what live_view will copy or reference."""
    partitions = re.compile(
        r"(?:panel|prices|signals)/(\d{4})\.parquet|"
        r"risk/(?:factor_returns|residuals|exposures|cov)_(\d{4})\.parquet|"
        r"alpha/book_v1/themes_(\d{4})\.parquet"
    )
    entries = []
    for source in sorted(live.rglob("*")):
        if not source.is_file() or "duck_tmp" in source.parts:
            continue
        relative = source.relative_to(live).as_posix()
        match = partitions.fullmatch(relative)
        partition_year = int(next(v for v in match.groups() if v)) if match else None
        reference = partition_year is not None and partition_year <= year
        entries.append(
            {
                "relative_path": relative,
                "bytes": source.stat().st_size,
                "mode": "readonly_reference" if reference else "copy",
            }
        )
    return entries


def prior_year_copy_plan(features: Path, tables: list, year: int) -> list[dict]:
    entries = []
    for table in tables:
        if not table.enabled or not table.link_prior_years or table.in_place:
            continue
        parent = (features / table.output.format(year=year)).parent
        for path in sorted(parent.glob("[0-9][0-9][0-9][0-9].parquet")):
            if int(path.stem) < year:
                entries.append(
                    {"table": table.name, "path": str(path), "bytes": path.stat().st_size}
                )
    return entries


def largest_live_output(live: Path, year: int) -> int:
    paths = [
        live / relative.format(year=year)
        for products in READER_OUTPUTS.values()
        for relative, _ in products
    ]
    return max((p.stat().st_size for p in paths if p.exists()), default=0)


def bind_consumer(root: Path, config: dict, name: str, dependencies: list[Path]) -> Path:
    context = Path(
        config.get("runtime_context_manifest", config.get("runtime_source_manifest", ""))
    )
    source = json.loads(context.read_text())
    bindings = []
    frozen_directory = context.parent / "producer-frozen"
    for p in sorted(set(dependencies)):
        if not p.exists():
            continue
        before = sha256(p)
        frozen = frozen_directory / (before + p.suffix)
        frozen.parent.mkdir(parents=True, exist_ok=True)
        if not frozen.exists():
            # Universe builders use copy2, so these snapshots must be independent.
            if (
                "universe" in p.parts
                or "universe_broad" in p.parts
                or p.suffix == ".py"
                or p.name == "facts.parquet"
            ):
                shutil.copyfile(p, frozen)
            else:
                # Accepted pre-2026 inputs are immutable; forward price/readers
                # are replaced atomically. The producer never writes these inputs.
                os.link(p, frozen)
        if sha256(frozen) != before or sha256(p) != before:
            raise ValueError("dependency changed while freezing: " + str(p))
        bindings.append(
            {
                "path": str(frozen),
                "source_path": str(p),
                "bytes": frozen.stat().st_size,
                "sha256": before,
            }
        )
    source["producer_dependencies"] = bindings
    target = context.parent / (
        "consumer-" + name + "-" + datetime.now(UTC).strftime("%H%M%S%f") + ".json"
    )
    atomic_json(target, source)
    config["runtime_source_manifest"] = str(target)
    return target


def disk_admission(
    root: Path,
    config: dict,
    *,
    source_root: Path,
    tables: list,
    live: Path,
    stages: list[str],
    year: int,
    fetch: bool,
) -> dict:
    # This is a conservative declared bound, not an assertion that file growth
    # cannot occur. Per-stage rechecks and subprocess spill limits remain required.
    tables = [table for table in tables if table.enabled]
    raw = sum(
        p.stat().st_size
        for group in ("data/sip/daily", "data/sip-delisted/by_year")
        for y in (year - 1, year)
        for p in (source_root / group / str(y)).glob("*.parquet")
    )
    outputs = [root / "data/features" / t.output.format(year=year) for t in tables if not t.monthly]
    outputs += [
        live / relative.format(year=year)
        for stage in stages
        for relative, _ in READER_OUTPUTS.get(stage, [])
    ]
    current = sum(p.stat().st_size for p in outputs if p.exists())
    view_plan = live_view_plan(live, year) if stages else []
    prior_plan = prior_year_copy_plan(root / "data/features", tables, year)
    growth = max(current // 4, 64 * 1024 * 1024)
    archive = source_root / "data/raw/sec_xbrl/companyfacts.zip"
    fetch_bound = (
        max(archive.stat().st_size * 5 // 4 if archive.exists() else 0, 2 * 1024**3)
        if fetch and any(t.name == "sec_fundamentals_facts" for t in tables)
        else 0
    )
    spill = int(config.get("disk_spill_bound_bytes", 2 * 1024**3))
    # Backups, retained natural products, composed replacement, monthly outputs,
    # current-bulk download, fixed spill, and owner-service reserve all counted.
    terms = {
        "fresh_context_bytes": raw,
        "backups_bytes": current,
        "natural_and_composed_bytes": 2 * (current + growth),
        "live_view_physical_copies_bytes": sum(
            v["bytes"] for v in view_plan if v["mode"] == "copy"
        ),
        "link_prior_years_physical_copies_bytes": sum(v["bytes"] for v in prior_plan),
        "atomic_rollback_temporary_bytes": max(
            (p.stat().st_size for p in outputs if p.exists()), default=0
        ),
        "monthly_and_metadata_bytes": 256 * 1024 * 1024,
        "source_fetch_bytes": fetch_bound,
        "spill_bytes": spill,
        "service_disk_reserve_bytes": 512 * 1024 * 1024,
    }
    required = sum(terms.values())
    st = os.statvfs(root)
    available = st.f_bavail * st.f_frsize
    result = {
        "at_UTC": datetime.now(UTC).isoformat(),
        "terms": terms,
        "required_available_bytes": required,
        "actual_available_bytes": available,
        "admitted": available >= required,
        "headroom_bytes": available - required,
        "scope": "before any fetch, snapshot, backup, candidate or publication write",
        "retention_not_deleted_on_failure": True,
        "live_view_inventory": view_plan,
        "link_prior_years_inventory": prior_plan,
    }
    path = (
        root
        / config["version_directory"]
        / "admissions"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".json")
    )
    atomic_json(path, result)
    if not result["admitted"]:
        raise OSError(
            f"forward refresh disk admission failed: available={available}, required={required}; "
            f"receipt={path}"
        )
    config["runtime_disk_admission"] = str(path)
    return result


def stage_admission(root: Path, config: dict, output_bytes: int, copy_bytes: int = 0) -> None:
    stat = os.statvfs(root)
    available = stat.f_bavail * stat.f_frsize
    required = (
        512 * 1024**2
        + int(config.get("disk_spill_bound_bytes", 2 * 1024**3))
        + 4 * output_bytes
        + copy_bytes
    )
    if available < required:
        raise OSError(
            f"forward stage disk reserve lost: available={available}, required={required}"
        )


def already_published(
    root: Path, config: dict, day: date, tables: list, live: Path, stages: list[str]
) -> bool:
    products = [
        (t.name, root / "data/features" / t.output.format(year=day.year))
        for t in tables
        if t.name in config["tables"]
    ]
    products += [
        (reader_name(relative.format(year=day.year)), live / relative.format(year=day.year))
        for stage in stages
        for relative, _ in READER_OUTPUTS.get(stage, [])
    ]
    if not products:
        return False
    for name, output in products:
        head = root / config["version_directory"] / "latest" / (name + ".json")
        if not head.exists() or not output.exists():
            return False
        value = json.loads(head.read_text())
        if value["version_id"] != config["version_id"] or value["suffix_end"] != day.isoformat():
            return False
        if value["output"]["sha256"] != sha256(output):
            raise ValueError("same-day publication head/output mismatch: " + name)
    return True


def live_view(root: Path, config: dict, live: Path) -> Path:
    inventory = live_view_plan(live, config.get("year", 2026))
    stage_admission(
        root,
        config,
        largest_live_output(live, config.get("year", 2026)),
        sum(v["bytes"] for v in inventory if v["mode"] == "copy"),
    )
    path = (
        root
        / config["version_directory"]
        / "live-attempts"
        / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    )
    path.mkdir(parents=True)
    for item in inventory:
        source = live / item["relative_path"]
        if source.stat().st_size != item["bytes"]:
            raise ValueError("live view input grew after admission; retain attempt and retry")
        target = path / item["relative_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if item["mode"] == "readonly_reference":
            target.symlink_to(source.resolve())  # immutable input; writable products unlinked below
        else:
            shutil.copyfile(source, target)
            if target.stat().st_size != item["bytes"] or source.stat().st_size != item["bytes"]:
                raise ValueError("live view copy grew beyond its admission")
    config["runtime_live_root"] = str(path)
    return path


def recover_metadata(version_root: Path) -> None:
    for journal in sorted((version_root / "transactions").glob("metadata-*.json")):
        value = json.loads(journal.read_text())
        if value["status"] != "staged":
            continue
        ready = True
        for item in value["required_heads"]:
            head = Path(item["path"])
            if not head.exists():
                ready = False
                break
            got = json.loads(head.read_text())
            output = Path(item["output"])
            if not output.exists() or sha256(output) != got["output"]["sha256"]:
                raise ValueError("metadata recovery publication head/output mismatch")
            if got["suffix_end"] != value["day"] or got["version_id"] != value["version_id"]:
                ready = False
                break
        if not ready:
            continue
        for item in value["files"]:
            source, target = Path(item["source"]), Path(item["target"])
            if sha256(source) != item["sha256"]:
                raise ValueError("retained stage metadata changed")
            current = sha256(target) if target.exists() else None
            if current not in {item["old_sha256"], item["sha256"]}:
                raise ValueError("stage metadata changed independently")
            if current != item["sha256"]:
                temporary = target.with_suffix(target.suffix + ".forward.tmp")
                shutil.copyfile(source, temporary)
                temporary.replace(target)
        value["status"] = "committed"
        atomic_json(journal, value)


def run_live_stage(
    root: Path,
    config: dict,
    live: Path,
    day: date,
    stage: str,
    steps: list,
    execute,
    runner,
    merge_ic=None,
) -> int:
    if config.get("runtime_live_root"):
        stage_admission(root, config, largest_live_output(live, day.year))
    view = Path(config.get("runtime_live_root") or live_view(root, config, live))
    outputs = READER_OUTPUTS.get(stage, [])
    backups = {}
    for template, _ in outputs:
        relative = template.format(year=day.year)
        output, candidate = live / relative, view / relative
        name = reader_name(relative)
        head = root / config["version_directory"] / "latest" / (name + ".json")
        if head.exists() and json.loads(head.read_text())["suffix_end"] == day.isoformat():
            if sha256(output) != json.loads(head.read_text())["output"]["sha256"]:
                raise ValueError("reader head/output mismatch")
            backups[relative] = None
            continue
        if candidate.exists() or candidate.is_symlink():
            candidate.unlink()
        candidate.parent.mkdir(parents=True, exist_ok=True)
        backup = view / "before" / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        os.link(output, backup)  # producer writes only the separate view, never this inode
        backups[relative] = backup
    if outputs and all(v is None for v in backups.values()):
        return 0
    stage_admission(root, config, largest_live_output(live, day.year))
    # A partly completed multi-output stage rebuilds only in the private view;
    # even products already committed today must never remain writable symlinks.
    for template, _ in outputs:
        candidate = view / template.format(year=day.year)
        if candidate.exists() or candidate.is_symlink():
            candidate.unlink()
    own_outputs = {live / relative.format(year=day.year) for relative, _ in outputs}
    dependencies = [
        p for p in live.rglob("*.parquet") if "duck_tmp" not in p.parts and p not in own_outputs
    ]
    dependencies += [live / "risk/meta.json", live / "panel/_hygiene_manifest.json"]
    dependencies += [
        root / "scripts" / Path(s.argv[s.argv.index("python") + 1]).name
        for s in steps
        if "python" in s.argv
    ]
    bind_consumer(root, config, "live-" + stage, dependencies)
    for step in steps:
        if step.kind == "merge":
            continue  # merge once after the staged formation IC is installed below
        step.env = {**step.env, "OC_EQUITY_BOOK_DIR": str(view)}
        if stage == "risk" and "--out" in step.argv:
            step.argv[step.argv.index("--out") + 1] = str(view / "risk")
        if execute(step, runner) != 0:
            return 4
    if (
        stage == "alpha"
        and (view / "alpha/book_v1/formation_ic.parquet").exists()
        and merge_ic is not None
    ):
        merge_ic(view)
    metadata = {
        "hygiene": [
            "panel/_hygiene.parquet",
            "panel/_calendar.parquet",
            "panel/_hygiene_manifest.json",
        ],
        "alpha": [
            "alpha/book_v1/formation_ic.parquet",
            "alpha/book_v1/formation_ic_live_only.parquet",
            "alpha/book_v1/formation_ic_merge.json",
            "alpha/book_v1/build_meta.json",
        ],
        "risk": ["risk/meta.json"],
    }.get(stage, [])
    files = []
    for relative in metadata:
        source, target = view / relative, live / relative
        if not source.exists():
            continue
        old_sha = sha256(target) if target.exists() else None
        if target.exists():
            old = view / "before" / relative
            old.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, old)
        files.append(
            {
                "source": str(source),
                "target": str(target),
                "sha256": sha256(source),
                "old_sha256": old_sha,
            }
        )
    version_root = root / config["version_directory"]
    if files:
        journal = version_root / "transactions" / ("metadata-" + stage + "-" + view.name + ".json")
        atomic_json(
            journal,
            {
                "status": "staged",
                "files": files,
                "day": day.isoformat(),
                "version_id": config["version_id"],
                "required_heads": [
                    {
                        "output": str(live / template.format(year=day.year)),
                        "path": str(
                            version_root
                            / "latest"
                            / (reader_name(template.format(year=day.year)) + ".json")
                        ),
                    }
                    for template, _ in outputs
                ],
            },
        )
    for template, keys in outputs:
        relative = template.format(year=day.year)
        old = backups[relative]
        if old is None:
            candidate = view / relative
            if candidate.exists() or candidate.is_symlink():
                candidate.unlink()
            candidate.symlink_to((live / relative).resolve())
            continue
        name = reader_name(relative)
        definition = config["readers"][name]
        local = {**config, "tables": {name: {**definition, "keys": keys}}}
        candidate = view / relative
        publish_forward_table(root, name, old, candidate, live / relative, day, local)
        candidate.unlink()
        candidate.symlink_to((live / relative).resolve())
    recover_metadata(version_root)
    return 0
