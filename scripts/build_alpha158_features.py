"""Step 13-F 3.1: build ``data/features/alpha158/{year}.parquet``.

docs/plan-step-13f-open-factor-library-import-and-screening-2026-09-09.zh.md
section 3.1. One row per (symbol, trade_date), 154 Alpha158 columns (see
``open_composer/research/features/alpha158.py`` for the "154, not 158"
scope note), restricted to the PIT universe's full-history symbol union.

Per-year, per-symbol-batch, resumable -- same shape as
``build_intraday_daily_features.py``: each (year, symbol-batch) is written
to a scratch parquet first, so a killed/OOM'd run resumes from the last
finished batch instead of recomputing the whole year. ``[year-1, year]`` is
scanned per target year (same reasoning as ``build_daily_features.py``: the
longest window here is 60 days, comfortably inside one prior year of
history) and only the target year's rows are kept before writing.

Usage (foreground, one year, small batch for a smoke test)::

    uv run python scripts/build_alpha158_features.py --years 2026 --symbol-batch-size 50

Usage (the real multi-year backfill; intended to run capped + backgrounded)::

    ./scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/build_alpha158_features.py > /tmp/build_alpha158.log 2>&1 &

**2026-09-18 broad-universe rerun**: ``--universe-root``/``--out-dir``/
``--extra-daily-root`` (same names, same defaults-unchanged contract as
``build_daily_features.py``) let this same builder target
``data/features/alpha158_broad`` off ``data/features/universe_broad`` (9,191
symbols) with ``data/sip-delisted/by_year`` folded in so backfilled delisted
names are included::

    nohup setsid ./scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/build_alpha158_features.py \
        --universe-root data/features/universe_broad \
        --out-dir data/features/alpha158_broad \
        --extra-daily-root data/sip-delisted/by_year \
        --symbol-batch-size 100 --memory-limit 600MB > logs/alpha158_broad.log 2>&1 &
"""

from __future__ import annotations

import argparse
import fcntl
import gc
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.research.features.alpha158 import (  # noqa: E402
    DEFAULT_WINDOWS,
    alpha158_columns,
    build_alpha158_features,
)
from open_composer.research.features.manifest import write_feature_table_manifest  # noqa: E402
from open_composer.research.features.universe import universe_union_symbols  # noqa: E402

DAILY_ROOT = ROOT / "data" / "sip" / "daily"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
OUT_DIR = ROOT / "data" / "features" / "alpha158"
DUCKDB_TMP = ROOT / "data" / "_duckdb_tmp"
ALL_YEARS = list(range(2016, 2027))
LOOKBACK_YEARS = 1
DEFAULT_SYMBOL_BATCH_SIZE = 100
SOURCE_LIBRARY = (
    "microsoft/qlib (MIT) -- qlib/contrib/data/loader.py Alpha158DL "
    "(reports/harness/source_cards/step13f_open_factor_libraries.jsonl: "
    "qlib_alpha158_definition_2026-09-09)"
)
FORMULA_VERSION = "step13f-2026-09-09-v1"


def _available_archive_years() -> list[int]:
    return sorted(int(p.name) for p in DAILY_ROOT.iterdir() if p.is_dir() and p.name.isdigit())


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _write_json_atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _build_identity(
    year: int, symbols: list[str], batch_size: int, source_paths: list[Path]
) -> dict[str, object]:
    # Hash bytes, not just timestamps: changed archives must not reuse old features.
    return {
        "schema_version": 1,
        "year": year,
        "symbols": symbols,
        "symbol_batch_size": batch_size,
        "windows": list(DEFAULT_WINDOWS),
        "lookback_years": LOOKBACK_YEARS,
        "formula_version": FORMULA_VERSION,
        "formula_sha256": _file_sha256(ROOT / "open_composer/research/features/alpha158.py"),
        "builder_sha256": _file_sha256(Path(__file__)),
        "sources": [
            {"path": str(path.resolve()), "sha256": _file_sha256(path)}
            for path in sorted(source_paths)
        ],
    }


def _checkpoint_valid(path: Path, identity_sha: str, symbols: list[str]) -> bool:
    marker = path.with_suffix(".json")
    if not path.exists() or not marker.exists():
        return False
    record = json.loads(marker.read_text())
    expected = {"identity_sha256": identity_sha, "symbols_sha256": _json_digest(symbols)}
    if any(record.get(key) != value for key, value in expected.items()):
        raise ValueError(f"checkpoint identity mismatch: {path}; use --force to rebuild")
    if record.get("parquet_sha256") != _file_sha256(path):
        raise ValueError(f"checkpoint checksum mismatch: {path}; use --force to rebuild")
    return True


def _write_checkpoint(
    frame: pd.DataFrame, path: Path, identity_sha: str, symbols: list[str]
) -> None:
    temporary = path.with_suffix(".parquet.tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)
    _write_json_atomic(
        path.with_suffix(".json"),
        {
            "identity_sha256": identity_sha,
            "symbols_sha256": _json_digest(symbols),
            "parquet_sha256": _file_sha256(path),
            "rows": len(frame),
        },
    )


def _consolidate_batches(
    batch_paths: list[Path], out_path: Path, *, memory_limit: str, temp_directory: Path
) -> int:
    """Spill the global sort to disk and COPY directly; never fetch the year into pandas."""
    temp_directory.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_suffix(".parquet.tmp")
    with duckdb.connect() as connection:
        connection.execute("SET memory_limit = ?", [memory_limit])
        connection.execute("SET threads = 1")
        connection.execute("SET temp_directory = ?", [str(temp_directory)])
        connection.execute("SET preserve_insertion_order = false")
        paths = [str(path) for path in batch_paths]
        connection.read_parquet(paths, union_by_name=True).create_view("feature_batches")
        duplicates = connection.execute(
            "SELECT 1 FROM feature_batches GROUP BY symbol, trade_date HAVING count(*) > 1 LIMIT 1"
        ).fetchone()
        if duplicates:
            raise ValueError("duplicate (symbol, trade_date) in Alpha158 checkpoints")
        # A small row group also bounds the writer buffers across 156 columns.
        destination = "'" + str(temporary).replace("'", "''") + "'"
        connection.execute(
            "COPY (SELECT * FROM feature_batches ORDER BY symbol, trade_date) TO "
            + destination
            + " (FORMAT PARQUET, COMPRESSION SNAPPY, ROW_GROUP_SIZE 4096)"
        )
        rows = connection.execute(
            "SELECT count(*) FROM read_parquet(?)", [str(temporary)]
        ).fetchone()[0]
    temporary.replace(out_path)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years", type=int, nargs="*", default=None, help="default: every archive year"
    )
    parser.add_argument("--memory-limit", default="600MB")
    parser.add_argument("--force", action="store_true", help="recompute even if output exists")
    parser.add_argument("--symbol-batch-size", type=int, default=DEFAULT_SYMBOL_BATCH_SIZE)
    parser.add_argument(
        "--universe-root",
        type=Path,
        default=UNIVERSE_ROOT,
        help="PIT universe panel dir whose symbol union bounds the feature set",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help="where {year}.parquet feature files go (default data/features/alpha158)",
    )
    parser.add_argument(
        "--extra-daily-root",
        type=Path,
        default=None,
        help=(
            "second bars root in {root}/{year}/*.parquet layout scanned next to "
            "data/sip/daily (e.g. data/sip-delisted/by_year for backfilled delisted names)"
        ),
    )
    args = parser.parse_args()

    if not 1 <= args.symbol_batch_size <= 100:
        parser.error("--symbol-batch-size must be between 1 and 100")

    out_dir = Path(args.out_dir)
    universe_root = Path(args.universe_root)
    extra_root = Path(args.extra_daily_root) if args.extra_daily_root is not None else None
    if extra_root is not None and not any(extra_root.glob("*/*.parquet")):
        raise SystemExit(f"no parquet files under {extra_root}")

    out_dir.mkdir(parents=True, exist_ok=True)
    build_lock = (out_dir / ".build.lock").open("a")
    try:
        fcntl.flock(build_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise SystemExit(f"another builder is active for {out_dir}") from error
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] loading universe union symbols ...", flush=True)
    universe_symbols = sorted(universe_union_symbols(universe_root))
    print(f"universe union: {len(universe_symbols)} symbols", flush=True)

    archive_years = _available_archive_years()
    if not archive_years:
        raise SystemExit(f"no archive years under {DAILY_ROOT}")
    if not universe_symbols:
        raise SystemExit(f"empty universe under {universe_root}")
    first_archive_year = archive_years[0]
    target_years = args.years or ALL_YEARS
    target_years = [y for y in target_years if y in archive_years]
    print(f"archive years available: {archive_years}", flush=True)
    print(f"target years this run: {target_years}", flush=True)

    columns = alpha158_columns(DEFAULT_WINDOWS)
    summary: dict[str, object] = {}
    for year in target_years:
        out_path = out_dir / f"{year}.parquet"
        window_years = sorted({y for y in (year - LOOKBACK_YEARS, year) if y >= first_archive_year})
        glob_paths = [str(DAILY_ROOT / str(y) / "*.parquet") for y in window_years]
        if extra_root is not None:
            glob_paths += [
                str(extra_root / str(y) / "*.parquet")
                for y in window_years
                if (extra_root / str(y)).is_dir()
            ]

        source_paths = sorted(
            {path for pattern in glob_paths for path in Path(pattern).parent.glob("*.parquet")}
        )
        if not source_paths:
            raise SystemExit(f"no input parquet files for {year}")
        identity = _build_identity(year, universe_symbols, args.symbol_batch_size, source_paths)
        identity_sha = _json_digest(identity)
        completion_path = out_dir / f"{year}.complete.json"
        if out_path.exists() and completion_path.exists() and not args.force:
            completion = json.loads(completion_path.read_text())
            if completion.get("identity_sha256") != identity_sha:
                raise SystemExit(f"{year}: existing output has different inputs; use --force")
            if completion.get("parquet_sha256") != _file_sha256(out_path):
                raise SystemExit(f"{year}: output checksum mismatch; use --force")
            print(f"{year}: verified complete, skipping", flush=True)
            summary[str(year)] = "skipped_verified"
            continue

        symbol_batches = [
            universe_symbols[i : i + args.symbol_batch_size]
            for i in range(0, len(universe_symbols), args.symbol_batch_size)
        ]
        started = time.monotonic()
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: scanning {window_years}, "
            f"{len(symbol_batches)} symbol batches ...",
            flush=True,
        )

        # Legacy unbound batches remain untouched; only matching identities can resume.
        scratch_dir = out_dir / "_scratch" / str(year) / identity_sha
        scratch_dir.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(scratch_dir / "identity.json", identity)
        batch_paths: list[Path] = []
        for batch_index, batch_symbols in enumerate(symbol_batches):
            batch_path = scratch_dir / f"batch-{batch_index:03d}.parquet"
            batch_paths.append(batch_path)
            if not args.force and _checkpoint_valid(batch_path, identity_sha, batch_symbols):
                continue
            batch_started = time.monotonic()
            batch_frame = build_alpha158_features(
                [str(path) for path in source_paths],
                batch_symbols,
                memory_limit=args.memory_limit,
                temp_directory=str(DUCKDB_TMP),
            )
            # Empty universes in a historical batch must still produce the same typed schema.
            batch_frame["trade_date"] = pd.to_datetime(batch_frame["trade_date"])
            batch_frame = batch_frame.loc[batch_frame["trade_date"].dt.year == year].copy()
            batch_frame["symbol"] = batch_frame["symbol"].astype("string")
            for column in columns:
                batch_frame[column] = batch_frame[column].astype("float64")
            _write_checkpoint(batch_frame, batch_path, identity_sha, batch_symbols)
            del batch_frame
            gc.collect()
            print(
                f"  [{time.strftime('%Y-%m-%d %H:%M:%S')}] {year} batch "
                f"{batch_index + 1}/{len(symbol_batches)}: "
                f"{time.monotonic() - batch_started:.0f}s",
                flush=True,
            )

        # If archive updates raced the build, do not publish features bound to stale hashes.
        if (
            _build_identity(year, universe_symbols, args.symbol_batch_size, source_paths)
            != identity
        ):
            raise RuntimeError(f"{year}: input sources changed during build; rerun")
        row_count = _consolidate_batches(
            batch_paths,
            out_path,
            memory_limit=args.memory_limit,
            temp_directory=DUCKDB_TMP / identity_sha,
        )
        elapsed = time.monotonic() - started

        manifest_stage = scratch_dir / "manifest-stage"
        manifest_stage.mkdir(exist_ok=True)
        manifest_path = out_dir / "MANIFEST.json"
        if manifest_path.exists():
            (manifest_stage / "MANIFEST.json").write_bytes(manifest_path.read_bytes())
        write_feature_table_manifest(
            manifest_stage,
            table="alpha158",
            source_library=SOURCE_LIBRARY,
            formula_version=FORMULA_VERSION,
            columns=["symbol", "trade_date"] + columns,
            skipped=[],
            rows_by_year={str(year): row_count},
            build_seconds_by_year={str(year): round(elapsed, 1)},
            notes=(
                "154 feature columns (9 K-bar + 29 rolling groups x windows "
                "{5,10,20,30,60}); Qlib's nominal 158 also includes 4 non-rolling "
                "PRICE features (OPEN0/HIGH0/LOW0/VWAP0) not in the plan's "
                "section 3.1 formula list -- omitted, see module docstring."
            ),
        )
        (manifest_stage / "MANIFEST.json").replace(manifest_path)
        _write_json_atomic(
            completion_path,
            {
                "identity_sha256": identity_sha,
                "parquet_sha256": _file_sha256(out_path),
                "rows": row_count,
                "identity": identity,
            },
        )
        # Retain validated checkpoints: a stop during publication can restart without recomputing.
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: done -- {row_count} rows, "
            f"{len(columns)} feature columns, {elapsed / 60:.1f}min",
            flush=True,
        )
        summary[str(year)] = {"rows": row_count, "elapsed_minutes": round(elapsed / 60, 1)}

    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
