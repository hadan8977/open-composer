"""Finite execution-day refresh of the original $300k M0 book, using native code.

This replaces the two existing nightly target slots. It installs no scheduler
and submits no orders. A ready input pointer is published only after native
prices, risk, themes and execution-unit checks finish.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import build_book_v12_current_units as units
import refresh_equity_book_live as original
import update_sip_archive as archive

from open_composer.market_sessions import (
    next_us_equity_session,
    us_equity_session_close,
    us_equity_session_dates,
)
from open_composer.paper_freshness import latest_completed_us_equity_session


def clock(now=None):
    now = now or datetime.now(UTC)
    execution = now.astimezone(UTC).date()
    decision = latest_completed_us_equity_session(now)
    if us_equity_session_close(execution) is None or next_us_equity_session(decision) != execution:
        raise ValueError(
            "UTC run day must be the next exchange session after the actual last close"
        )
    return decision, execution


def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n")
    os.replace(tmp, path)


def source_unchanged(view, source):
    meta = json.loads((view / "current-units-source.json").read_text())
    for item in meta["source_bindings"]:
        # The corrected two-year context has explicit quarantined/canonical
        # files. Compare current uncorrected input bindings for those years.
        if "/2025/" in item["path"] or "/2026/" in item["path"]:
            continue
        current = source / item["path"]
        expected = item.get("upstream_sha256_before_action_repairs", item["sha256"])
        if not current.exists() or units.digest(current) != expected:
            return False
    context = json.loads(
        (Path(meta["corrected_two_year_context"]) / "source-manifest.json").read_text()
    )
    overlays = {
        row["path"]: row["archive_sha256"] for row in meta.get("source_overlay_bindings", [])
    }
    for item in context["original_bindings"]:
        current = source / item["path"]
        expected = overlays.get(item["path"], item["sha256"])
        if not current.exists() or units.digest(current) != expected:
            return False
    return True


def declare(source, frozen, view):
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='250MB'")
    con.execute("SET threads=1")
    names = set()
    for root in (source, frozen):
        for glob in (
            "data/features/universe_broad/*.parquet",
            "data/live/equity_book/prices/20*.parquet",
        ):
            if list((root / Path(glob).parent).glob(Path(glob).name)):
                names.update(
                    x[0]
                    for x in con.execute(
                        f"SELECT DISTINCT symbol FROM read_parquet('{root / glob}')"
                    ).fetchall()
                )
    names.update(
        x[0]
        for x in con.execute(
            f"SELECT DISTINCT symbol FROM read_parquet('{source}/data/sip/daily/2026/*.parquet')"
        ).fetchall()
    )
    # Existing read-only broker access declares every actual holding before
    # selection; it never normalizes or rewrites broker quantities or cash.
    from open_composer.book_paper.accounts import make_trading_client
    from open_composer.book_paper.plan import read_account_state

    account = read_account_state(make_trading_client("quant1"))
    names.update(account.positions)
    names.update(["SPY", "SGOV", "BIL"])
    path = view / "declared-symbols.json"
    atomic_json(
        path,
        {
            "declared_at_utc": datetime.now(UTC).isoformat(),
            "before_target_selection": True,
            "symbols": sorted(names),
            "actual_owned_symbols": sorted(account.positions),
            "count": len(names),
        },
    )
    return path


def publish_targets(view, day, equity):
    # The original driver preserves authorization, immutable targets, capital
    # checks, paper credentials and all plan/submit risk and duplicate guards.
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_book_v12_daily.py"),
            "--targets",
            "--decision-date",
            str(day),
            "--data-root",
            str(view / "data/live/equity_book"),
            "--variant",
            "M0_U3000",
            "--equity-basis",
            str(equity),
        ],
        cwd=ROOT,
        check=True,
    )


def completed_bindings(view, day):
    """Bind the actual native reader outputs, not just a completion flag."""
    book = view / "data/live/equity_book"
    paths = [
        book / "panel/_calendar.parquet",
        book / "etf_daily.parquet",
        view / "data/live/vix/VIXCLS.csv",
        view / "current-units-source.json",
        view / "current-units-execution-bridge.json",
    ]
    for kind in ("prices", "panel"):
        paths.extend(sorted((book / kind).glob("20*.parquet")))
    for year in range(2024, day.year + 1):
        for kind in ("factor_returns", "residuals", "exposures", "cov"):
            paths.append(book / "risk" / f"{kind}_{year}.parquet")
    paths.extend(
        [
            book / "signals" / f"{day.year}.parquet",
            book / "alpha/book_v1" / f"themes_{day.year}.parquet",
            book / "alpha/book_v1/formation_ic.parquet",
        ]
    )
    return [{"path": str(p.resolve()), "sha256": units.digest(p)} for p in paths]


def target_bindings(day):
    from open_composer.book_paper.targets import target_path

    return [
        {"path": str(p), "sha256": units.digest(p)}
        for p in [target_path(ROOT, "quant1", day), target_path(ROOT, "quant2", day)]
    ]


def verify_bindings(bindings):
    for item in bindings:
        path = Path(item["path"])
        if not path.is_file() or units.digest(path) != item["sha256"]:
            raise ValueError("accepted native reader/target changed: " + str(path))


def finish_pending_source(source):
    """Read, complete and drain only the actual obligations protected by one lock."""
    with archive._exclusive_lock(source / "data/sip"):
        pending = archive._read_pending(source / "data/sip")
        if not pending:
            return
        _, client = archive._clients()
        records = archive.rewrite_full_history(
            client,
            source / "data/sip",
            sorted(pending),
            now=datetime.now(UTC),
            mode="current_book_risk_2017_dependency",
            max_rel_diff=pending,
        )
        processed = {row["symbol"] for row in records}
        if processed != set(pending):
            raise ValueError("native full-history source completion is incomplete")
        actual = archive._read_pending(source / "data/sip")
        remaining = {
            symbol: diff
            for symbol, diff in actual.items()
            if symbol not in processed or diff != pending[symbol]
        }
        archive._write_pending(source / "data/sip", remaining, now=datetime.now(UTC))


def check_working_stage(view, config, name, paths):
    """Use the original per-stage admission for sequential mutable-cache writers."""
    from forward_refresh_io import stage_admission

    files = [{"path": str(p), "bytes": p.stat().st_size} for p in paths if p.is_file()]
    largest = max((r["bytes"] for r in files), default=0)
    st = os.statvfs(view)
    available = st.f_bavail * st.f_frsize
    receipt = {
        "at_utc": datetime.now(UTC).isoformat(),
        "stage": name,
        "actual_outputs": files,
        "largest_sequential_output_bytes": largest,
        "actual_available_bytes": available,
        "required_available_bytes": 512 * 1024**2
        + int(config.get("disk_spill_bound_bytes", 2 * 1024**3))
        + 4 * largest,
        "retained_working_views": 1,
        "native_check": "forward_refresh_io.stage_admission",
        "new_full_feature_or_risk_tree_copies": 0,
    }
    receipt["admitted"] = available >= receipt["required_available_bytes"]
    with (view / "working-stage-resource.jsonl").open("a") as stream:
        stream.write(json.dumps(receipt) + "\n")
    stage_admission(view, config, largest)


def run(args):
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    os.environ["OC_BOOK_SOURCE_CACHE_ROOT"] = str(ROOT)
    decision, execution = clock()
    if args.equity_basis != 300000:
        raise ValueError("existing recovery scope is exactly $300000")
    if execution.isoformat() > "2026-12-31":
        raise ValueError("existing authorization ends 2026-12-31")
    source = args.source_root.resolve()
    pointer = args.input_pointer
    previous = json.loads(pointer.read_text()) if pointer.exists() else None
    frozen = Path(previous["view_root"]) if previous else source
    if args.check_ready:
        if (
            previous is None
            or previous["decision_day"] != str(decision)
            or previous["execution_day"] != str(execution)
            or previous["equity_basis_usd"] != args.equity_basis
            or previous.get("status") != "ready"
        ):
            raise ValueError("no accepted current execution-day input")
        ready = Path(previous["view_root"]) / "current-units-ready.json"
        if units.digest(ready) != previous["ready_sha256"]:
            raise ValueError("accepted input completion changed")
        completion = json.loads(ready.read_text())
        verify_bindings(completion["consumer_bindings"])
        verify_bindings(previous["target_bindings"])
        return
    # Original process lock: the two slots cannot launch duplicate refreshes.
    with original.FileLock(ROOT / "data/live/.refresh.lock"):
        from forward_refresh_io import disk_admission

        resource_config = json.loads((ROOT / "config/equity-book-forward.json").read_text())
        os.environ["OC_FORWARD_SPILL_BYTES"] = str(
            resource_config.get("disk_spill_bound_bytes", 2 * 1024**3)
        )
        # Source preparation writes Parquet via pandas, with no DuckDB query.
        # Preserve the original reserve and charge actual fetch/rewrite space;
        # do not count an unrelated feature tree as a second new copy.
        source_config = {
            **resource_config,
            "disk_spill_bound_bytes": 0,
            "version_directory": "source-resource-receipts",
        }
        source_admission = disk_admission(
            args.view_parent,
            source_config,
            source_root=source,
            tables=[],
            live=frozen / "data/live/equity_book",
            stages=[],
            year=decision.year,
            fetch=True,
            source_fetch_bound_bytes=2 * 1024**3,
        )
        atomic_json(
            args.view_parent / "latest-source-resource.json",
            {
                "stage_config": source_config,
                "admission": source_admission,
                "native_source_writer": (
                    "update_sip_archive: pandas Parquet, atomic shard replacement"
                ),
                "duckdb_consumers": 0,
            },
        )
        if previous and not args.prepare_only:
            resource_config["version_directory"] = "current-unit-admissions"
            admission = disk_admission(
                frozen,
                resource_config,
                source_root=source,
                tables=[next(t for t in original.UPSTREAM if t.name == "daily_broad")],
                live=frozen / "data/live/equity_book",
                stages=[],
                year=decision.year,
                fetch=False,
            )
            atomic_json(
                args.view_parent / "latest-source-feature-resource.json",
                {
                    "stage_config": resource_config,
                    "admission": admission,
                    "step_env": {"OC_FORWARD_SPILL_BYTES": os.environ["OC_FORWARD_SPILL_BYTES"]},
                    "working_view_count": 1,
                },
            )
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/update_sip_archive.py"),
                "--kind",
                "daily",
                "--out",
                str(source / "data/sip"),
            ],
            cwd=ROOT,
            check=True,
        )
        finish_pending_source(source)
        if args.prepare_only:
            # The 00:30 UTC winter slot is still NY 19:30. Receive the source,
            # but never seal a target or mutate an accepted working view here.
            return
        if (
            previous
            and previous["decision_day"] == str(decision)
            and previous["execution_day"] == str(execution)
        ):
            if source_unchanged(frozen, source):
                # Read current actions and raw endpoint again; reuse only when
                # the received execution-day source still closes in old units.
                verification = args.view_parent / (
                    "verify-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
                )
                verification.mkdir(parents=True)
                os.symlink(frozen / "data", verification / "data", target_is_directory=True)
                os.symlink(
                    frozen / "current-units-known-actions-repair.json",
                    verification / "current-units-known-actions-repair.json",
                )
                os.symlink(
                    frozen / "current-units-execution-consumers.json",
                    verification / "current-units-execution-consumers.json",
                )
                try:
                    completion = json.loads((frozen / "current-units-ready.json").read_text())
                    verify_bindings(completion["consumer_bindings"])
                    verify_bindings(previous["target_bindings"])
                    units.physical_sources(
                        verification,
                        decision,
                        execution,
                        Path(previous["declared_symbols"]),
                        decision,
                    )
                    units.endpoint_bridge(verification, decision, execution)
                    publish_targets(frozen, decision, args.equity_basis)
                except Exception:
                    atomic_json(
                        pointer, {**previous, "status": "current_unit_revalidation_refused"}
                    )
                    raise
                return
            atomic_json(pointer, {**previous, "status": "source_changed_after_seal_refused"})
            raise ValueError(
                "received source changed after same-day target acceptance; immutable target "
                "retained"
            )
        import shutil

        import pyarrow.parquet as pq
        from prepare_forward_source_context import prepare_context

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        config = json.loads((ROOT / "config/equity-book-forward.json").read_text())
        if previous:
            if previous.get("status") != "ready":
                raise ValueError(
                    "prior incomplete refresh retained; reconcile its explicit outputs before "
                    "replay"
                )
            view = Path(previous["view_root"])
            run_dir = view / "refresh-runs" / str(execution)
            run_dir.mkdir(parents=True, exist_ok=False)
            atomic_json(run_dir / "previous-completion.json", previous)
            old_declared = Path(previous["declared_symbols"])
            atomic_json(
                pointer, {**previous, "status": "updating", "next_execution_day": str(execution)}
            )
            context_next = args.view_parent / ("source-next-" + stamp)
            old_context = Path(
                json.loads((view / "current-units-source.json").read_text())[
                    "corrected_two_year_context"
                ]
            )
            prepare_context(source, config, context_next, decision.year, previous=old_context)
            # This cache is distinct from BASE's accepted immutable context.
            context = args.view_parent / "source-working"
            if context.exists():
                if old_context.resolve() != context.resolve():
                    raise ValueError("unexpected runtime context owner")
                retired = args.view_parent / ("source-retired-" + stamp)
                os.replace(context, retired)
                os.replace(context_next, context)
                shutil.rmtree(retired)
            else:
                os.replace(context_next, context)
            raw_next = run_dir / "source-next"
            units.stage_raw_only(source, context, raw_next)
            declared = declare(source, view, raw_next)
            units.repair_known_execution_actions(raw_next, declared, decision)
            units.incremental_daily(
                view, raw_next, declared, old_declared, decision, resource_config=resource_config
            )
            # Raw stage files now have their actual reader links in view; keep
            # source/action proofs, not a second entire market cache per day.
            shutil.rmtree(raw_next / "data")
            frozen = view
            cut = (
                pq.read_table(
                    view / f"data/live/equity_book/panel/{decision.year}.parquet",
                    columns=["trade_date"],
                )
                .column(0)
                .to_pandas()
                .max()
                .date()
            )
            units.physical_sources(
                view, decision, execution, declared, min(cut, decision) - timedelta(days=3)
            )
        else:
            context = args.view_parent / ("source-initial-" + stamp)
            prepare_context(source, config, context, decision.year)
            view = args.view_parent / "current-working"
            units.bootstrap(source, view, context, frozen)
            declared = declare(source, frozen, view)
            panel = frozen / f"data/live/equity_book/panel/{decision.year}.parquet"
            cut = pq.read_table(panel, columns=["trade_date"]).column(0).to_pandas().max().date()
            units.physical_sources(
                view, decision, execution, declared, min(cut, decision) - timedelta(days=3)
            )
            units.repair_known_execution_actions(view, declared, decision)
            units.daily(view, declared, list(range(2016, decision.year + 1)))
        last = original.last_universe_month_end(view / "data/features")
        ends = original.new_month_ends(last, us_equity_session_dates(last or decision, decision))
        for end in ends:
            units.monthly(view, ROOT, end, execution)
        units.execution_consumer_scope(view, frozen, declared, decision)
        units.endpoint_bridge(view, decision, execution)
        check_working_stage(
            view,
            resource_config,
            "narrow-daily",
            (view / "data/features/daily").glob("20*.parquet"),
        )
        units.narrow_daily(view)
        for table in (
            "sec_fundamentals_facts",
            "sec_fundamentals_daily",
            "nsi",
            "insider_broad",
            "short_volume_broad",
            "short_interest",
            "news_attention",
        ):
            if table != "sec_fundamentals_facts":
                spec = next(t for t in original.UPSTREAM if t.name == table)
                check_working_stage(
                    view,
                    resource_config,
                    table,
                    [view / "data/features" / spec.output.format(year=decision.year)],
                )
            units.dependencies(view, frozen, table, decision)
        book = view / "data/live/equity_book"
        check_working_stage(
            view,
            resource_config,
            "panel-prices-etf",
            [
                *(book / "panel").glob("20*.parquet"),
                *(book / "prices").glob("20*.parquet"),
                book / "etf_daily.parquet",
            ],
        )
        units.panel(view, frozen, declared, day=decision)
        check_working_stage(
            view,
            resource_config,
            "risk-signals-themes",
            [
                *(book / "risk").glob("*.parquet"),
                *(book / "signals").glob("20*.parquet"),
                *(book / "alpha/book_v1").glob("themes_20*.parquet"),
            ],
        )
        units.risk_signals_themes(view, decision)
        units.native_run(view, ["scripts/fetch_vix_live.py"])
        ready = {
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "decision_day": str(decision),
            "execution_day": str(execution),
            "equity_basis_usd": args.equity_basis,
            "code_root": str(ROOT),
            "view_root": str(view),
            "declared_symbols": str(declared),
            "execution_bridge_sha256": units.digest(view / "current-units-execution-bridge.json"),
            "risk_initialized_from": "2017-01-01",
            "training_runs": 0,
            "broker_writes": 0,
            "consumer_bindings": completed_bindings(view, decision),
        }
        atomic_json(view / "current-units-ready.json", ready)
        publish_targets(view, decision, args.equity_basis)
        atomic_json(
            pointer,
            {
                **ready,
                "status": "ready",
                "ready_sha256": units.digest(view / "current-units-ready.json"),
                "target_bindings": target_bindings(decision),
            },
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--equity-basis", type=float, required=True)
    p.add_argument("--source-root", type=Path, default=ROOT)
    p.add_argument(
        "--input-pointer", type=Path, default=ROOT / "data/live/equity_book_current.json"
    )
    p.add_argument("--view-parent", type=Path, default=ROOT / "data/live/equity_book_current_views")
    p.add_argument("--check-ready", action="store_true")
    p.add_argument("--prepare-only", action="store_true")
    args = p.parse_args()
    args.view_parent.mkdir(parents=True, exist_ok=True)
    run(args)


if __name__ == "__main__":
    main()
