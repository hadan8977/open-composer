"""Execution-day refresh of the original $300k M0 book inputs, using native code.

Cron modes (no scheduler is installed here and no order is sent):

* ``--prepare-only``: receive the daily SIP source and finish pending full-history rewrites.
* default: also update the working view (raw stage, known actions, incremental daily features,
  monthly universe, dependency tables, panel, risk/signals/themes, VIX), write the targets with
  ``run_book_v12_daily.py --targets`` and mark the input pointer ready.
* ``--check-ready``: fail unless the pointer is ready for today's execution day.

A failed refresh leaves the pointer ``updating`` and later runs refuse; once inspected, rerun with
``--recover-incomplete``, which restarts from the last ready inputs when the failed attempt never
reached the view-writing stage.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import os
import shutil
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

# Written when the known-action repair completes; the incremental stage then writes into the
# accepted view, so an attempt that got this far cannot restart from the old pointer.
VIEW_WRITES_MARKER = "source-next/current-units-known-actions-repair.json"


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


def declare(source, frozen, view):
    """Every name the stages may need, including actual broker holdings (read-only)."""
    import duckdb

    from open_composer.book_paper.accounts import make_trading_client
    from open_composer.book_paper.plan import read_account_state

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
    account = read_account_state(make_trading_client("quant1"))
    names.update(account.positions)
    names.update(["SPY", "SGOV", "BIL"])
    path = view / "declared-symbols.json"
    atomic_json(
        path,
        {
            "declared_at_utc": datetime.now(UTC).isoformat(),
            "symbols": sorted(names),
            "actual_owned_symbols": sorted(account.positions),
        },
    )
    return path


def publish_targets(view, day, equity):
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


def isolated_stage(stage, view, source, day, execution, declared=None, extra=()):
    """Keep native allocator state inside one stage under the inherited cap."""
    argv = [
        sys.executable,
        str(ROOT / "scripts/build_book_v12_current_units.py"),
        "--stage",
        stage,
        "--view-root",
        str(view),
        "--source-root",
        str(source),
        "--credentials-root",
        str(ROOT),
        "--day",
        str(day),
        "--application-day",
        str(execution),
    ]
    if declared is not None:
        argv += ["--declared-symbols", str(declared)]
    subprocess.run([*argv, *extra], cwd=ROOT, check=True)


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


def check_disk(view, config, paths):
    """Keep the service disk reserve before a stage rewrites outputs of these sizes."""
    from forward_refresh_io import stage_admission

    stage_admission(view, config, max((p.stat().st_size for p in paths if p.is_file()), default=0))


def last_panel_day(view, year):
    import pyarrow.parquet as pq

    panel = view / f"data/live/equity_book/panel/{year}.parquet"
    return pq.read_table(panel, columns=["trade_date"]).column(0).to_pandas().max().date()


def run(args):
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    os.environ["OC_BOOK_SOURCE_CACHE_ROOT"] = str(ROOT)
    decision, execution = clock()
    source = args.source_root.resolve()
    pointer = args.input_pointer
    if args.check_ready:
        previous = json.loads(pointer.read_text()) if pointer.exists() else {}
        if previous.get("status") != "ready" or previous.get("execution_day") != str(execution):
            raise ValueError(f"no ready book input for execution day {execution}")
        return
    # Original process lock: the two slots cannot launch duplicate refreshes.
    with original.FileLock(ROOT / "data/live/.refresh.lock"):
        previous = json.loads(pointer.read_text()) if pointer.exists() else None
        config = json.loads((ROOT / "config/equity-book-forward.json").read_text())
        os.environ["OC_FORWARD_SPILL_BYTES"] = str(
            config.get("disk_spill_bound_bytes", 2 * 1024**3)
        )
        if previous and not args.prepare_only:
            if previous.get("status") != "ready":
                failed = previous.get("active_refresh_run")
                if not args.recover_incomplete:
                    raise ValueError(
                        f"previous refresh {failed} did not finish; inspect it, then rerun with "
                        "--recover-incomplete"
                    )
                if failed and (Path(failed) / VIEW_WRITES_MARKER).exists():
                    raise ValueError(f"failed refresh {failed} already wrote the view; repair it")
                operational = {"next_execution_day", "active_refresh_run"}
                previous = {k: v for k, v in previous.items() if k not in operational}
                previous["status"] = "ready"
            if previous["execution_day"] == str(execution):
                print(f"book inputs for {execution} are already ready", flush=True)
                return
            from forward_refresh_io import disk_admission

            frozen = Path(previous["view_root"])
            disk_admission(
                frozen,
                {**config, "version_directory": "current-unit-admissions"},
                source_root=source,
                tables=[next(t for t in original.UPSTREAM if t.name == "daily_broad")],
                live=frozen / "data/live/equity_book",
                stages=[],
                year=decision.year,
                fetch=False,
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
            # The 00:30 UTC winter slot is still NY 19:30: receive the source only.
            return
        from prepare_forward_source_context import prepare_context

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        frozen = Path(previous["view_root"]) if previous else source
        if previous:
            view = Path(previous["view_root"])
            run_dir = view / "refresh-runs" / str(execution)
            if run_dir.exists():
                run_dir = run_dir.with_name(f"{execution}-recovery-{stamp}")
            run_dir.mkdir(parents=True)
            atomic_json(
                pointer,
                {
                    **previous,
                    "status": "updating",
                    "next_execution_day": str(execution),
                    "active_refresh_run": str(run_dir),
                },
            )
            old_context = Path(
                json.loads((view / "current-units-source.json").read_text())[
                    "corrected_two_year_context"
                ]
            )
            context_next = args.view_parent / ("source-next-" + stamp)
            prepare_context(source, config, context_next, decision.year, previous=old_context)
            context = args.view_parent / "source-working"
            retired = args.view_parent / ("source-retired-" + stamp)
            if context.exists():
                os.replace(context, retired)
            os.replace(context_next, context)
            shutil.rmtree(retired, ignore_errors=True)
            raw_next = run_dir / "source-next"
            units.stage_raw_only(source, context, raw_next)
            declared = declare(source, view, raw_next)
            units.repair_known_execution_actions(raw_next, declared, decision)
            isolated_stage(
                "incremental-daily",
                view,
                raw_next,
                decision,
                execution,
                declared,
                ("--previous-declared-symbols", str(previous["declared_symbols"])),
            )
            # The raw stage files now have their reader links in the view.
            shutil.rmtree(raw_next / "data")
            frozen = view
            cut = last_panel_day(view, decision.year)
            units.physical_sources(
                view, decision, execution, declared, min(cut, decision) - timedelta(days=3)
            )
        else:
            context = args.view_parent / ("source-initial-" + stamp)
            prepare_context(source, config, context, decision.year)
            view = args.view_parent / "current-working"
            units.bootstrap(source, view, context, frozen)
            declared = declare(source, frozen, view)
            cut = last_panel_day(frozen, decision.year)
            units.physical_sources(
                view, decision, execution, declared, min(cut, decision) - timedelta(days=3)
            )
            units.repair_known_execution_actions(view, declared, decision)
            units.daily(view, declared, list(range(2016, decision.year + 1)))
        last = original.last_universe_month_end(view / "data/features")
        sessions = us_equity_session_dates(last or decision, decision)
        for end in original.new_month_ends(last, sessions):
            units.monthly(view, ROOT, end, execution)
        units.execution_consumer_scope(view, frozen, declared, decision)
        units.endpoint_bridge(view, decision, execution)
        check_disk(view, config, (view / "data/features/daily").glob("20*.parquet"))
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
                output = view / "data/features" / spec.output.format(year=decision.year)
                check_disk(view, config, [output])
            isolated_stage(
                "dependency", view, frozen, decision, execution, extra=("--table", table)
            )
        book = view / "data/live/equity_book"
        check_disk(
            view,
            config,
            [
                *(book / "panel").glob("20*.parquet"),
                *(book / "prices").glob("20*.parquet"),
                book / "etf_daily.parquet",
            ],
        )
        isolated_stage("panel", view, frozen, decision, execution, declared)
        isolated_stage("identity-consumer", view, frozen, decision, execution)
        consumer = view
        policy_path = view / "current-units-identity-quarantine-policy.json"
        if policy_path.exists():
            first = json.loads(policy_path.read_text())["first_decision_day"]
            if str(decision) >= first:
                consumer = view / "identity-consumers" / first
        book = consumer / "data/live/equity_book"
        check_disk(
            view,
            config,
            [
                *(book / "risk").glob("*.parquet"),
                *(book / "signals").glob("20*.parquet"),
                *(book / "alpha/book_v1").glob("themes_20*.parquet"),
            ],
        )
        isolated_stage("risk-signals", consumer, consumer, decision, execution)
        units.native_run(consumer, ["scripts/fetch_vix_live.py"])
        ready = {
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "decision_day": str(decision),
            "execution_day": str(execution),
            "equity_basis_usd": args.equity_basis,
            "code_root": str(ROOT),
            "view_root": str(view),
            "consumer_view_root": str(consumer),
            "declared_symbols": str(declared),
        }
        atomic_json(view / "current-units-ready.json", ready)
        publish_targets(consumer, decision, args.equity_basis)
        atomic_json(pointer, {**ready, "status": "ready"})


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
    p.add_argument(
        "--recover-incomplete",
        action="store_true",
        help="restart from the last ready inputs after a failure before the view-writing stage",
    )
    args = p.parse_args()
    args.view_parent.mkdir(parents=True, exist_ok=True)
    run(args)


if __name__ == "__main__":
    main()
