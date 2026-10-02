"""``oc book-paper``: plan, submit, reconcile and status for the book paper accounts."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import typer
from rich.console import Console

from open_composer.book_paper.accounts import (
    BookAccountError,
    credential_variable_names,
    make_trading_client,
    present_variables,
)
from open_composer.config import project_root
from open_composer.market_sessions import NEW_YORK

book_paper_app = typer.Typer(
    no_args_is_help=True, help="Short-capable book orders on Alpaca Paper."
)
console = Console()

ACCOUNT_OPTION = typer.Option(..., "--account", help="quant1 or quant2")
PRICES_FILE_OPTION = typer.Option(
    ..., "--prices-file", help='JSON {"official_close": {sym: px}, "snapshot_1545": {sym: px}}'
)


def _fail(exc: Exception) -> typer.BadParameter:
    return typer.BadParameter(str(exc))


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _kill_switch_check(root: Path):
    from open_composer.adapters.broker.alpaca_paper import _require_kill_switch_clear

    return lambda: _require_kill_switch_clear(root)


def _build(account: str, decision_date: str | None, as_of: str | None, min_notional: float):
    from open_composer.book_paper.plan import (
        OrderLookup,
        build_plan,
        make_asset_lookup,
        read_account_state,
    )
    from open_composer.book_paper.targets import latest_target_path, load_target_file, target_path

    root = project_root()
    decision = _parse_date(decision_date)
    path = target_path(root, account, decision) if decision else latest_target_path(root, account)
    if path is None or not path.is_file():
        raise typer.BadParameter("no target file for this account and decision date")
    target = load_target_file(path)
    if target.account != account:
        raise typer.BadParameter("target file belongs to a different account")
    client = make_trading_client(account)
    state = read_account_state(client)
    now = datetime.now(UTC)
    as_of_date = _parse_date(as_of) or now.astimezone(NEW_YORK).date()
    existing = OrderLookup(client, target.execution_date).ids()
    plan = build_plan(
        target,
        state,
        as_of=as_of_date,
        now=now,
        asset_lookup=make_asset_lookup(client),
        existing_client_order_ids=existing,
        min_notional=min_notional,
        kill_switch_check=_kill_switch_check(root),
    )
    return root, client, target, plan


def _print_plan(plan, path: Path) -> None:
    p = plan.payload
    s = p["summary"]
    console.print(
        f"plan status={p['status']} account={p['account']} form={p['form']} "
        f"execution_date={p['execution_date']} orders={s['n_orders']} "
        f"(buy {s['n_buy']}, sell {s['n_sell']}) etb_rejections={s['n_etb_rejections']} "
        f"dropped_min_notional={s['n_dropped_min_notional']}"
    )
    console.print(
        f"post-trade long={s['post_trade_long_notional']:.0f} "
        f"short={s['post_trade_short_notional']:.0f} "
        f"rounding_drift={s['rounding_drift_one_sided']:.6f} "
        f"final_drift={s['final_drift_one_sided']:.6f}"
    )
    for check in p["checks"]:
        console.print(
            f"  {'PASS' if check['passed'] else 'FAIL'} {check['name']} "
            f"value={check['value']} limit={check['limit']} {check['detail'][:80]}"
        )
    console.print(f"plan file: {path}")


@book_paper_app.command("plan")
def book_paper_plan(
    account: str = ACCOUNT_OPTION,
    decision_date: str | None = typer.Option(
        None, "--decision-date", help="default: latest target"
    ),
    as_of: str | None = typer.Option(
        None, "--as-of", help="calendar date to evaluate freshness on"
    ),
    min_notional: float = typer.Option(100.0, "--min-notional"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run"),
) -> None:
    """Dry-run plan from the target file: reads account, positions, orders and assets only."""
    from open_composer.book_paper.plan import write_plan_file

    if not dry_run:
        raise typer.BadParameter("plan never sends orders; use `submit --submit`")
    try:
        root, _client, _target, plan = _build(account, decision_date, as_of, min_notional)
    except BookAccountError as exc:
        raise _fail(exc) from exc
    _print_plan(plan, write_plan_file(root, plan))


@book_paper_app.command("submit")
def book_paper_submit(
    account: str = ACCOUNT_OPTION,
    decision_date: str | None = typer.Option(None, "--decision-date"),
    min_notional: float = typer.Option(100.0, "--min-notional"),
    submit: bool = typer.Option(False, "--submit", help="required to send CLS orders"),
) -> None:
    """Send the plan as market-on-close orders (requires --submit and the CLS window)."""
    from open_composer.book_paper.plan import (
        BookEngineError,
        orders_receipt_path,
        submit_plan,
        write_json_atomic,
        write_plan_file,
    )

    if not submit:
        raise typer.BadParameter("pass --submit to send orders; `plan` is the dry-run")
    try:
        root, client, _target, plan = _build(account, decision_date, None, min_notional)
        write_plan_file(root, plan)
        report = submit_plan(
            client, plan, now=datetime.now(UTC), kill_switch_check=_kill_switch_check(root)
        )
    except (BookAccountError, BookEngineError) as exc:
        raise _fail(exc) from exc
    path = write_json_atomic(orders_receipt_path(root, account, plan.execution_date), report)
    console.print(
        f"sent={len(report['sent'])} skipped_existing={len(report['skipped_existing'])} "
        f"failed={len(report['failed'])} receipt={path}"
    )


@book_paper_app.command("reconcile")
def book_paper_reconcile(
    account: str = ACCOUNT_OPTION,
    date_: str = typer.Option(..., "--date", help="execution date"),
    prices_file: Path = PRICES_FILE_OPTION,
) -> None:
    """After the close: orders -> fills -> positions, TCA, shadow costs and daily P&L."""
    from open_composer.book_paper.plan import load_plan_file, plan_path, read_account_state
    from open_composer.book_paper.post_close import (
        build_daily_record,
        fetch_broker_orders,
        write_daily_file,
    )
    from open_composer.book_paper.targets import load_target_file, target_path

    root = project_root()
    try:
        plan = load_plan_file(plan_path(root, account, date.fromisoformat(date_)))
        target = load_target_file(
            target_path(root, account, date.fromisoformat(plan.payload["decision_date"]))
        )
        prices = json.loads(prices_file.read_text(encoding="utf-8"))
        client = make_trading_client(account)
        state = read_account_state(client)
        record = build_daily_record(
            plan,
            target,
            broker_orders=fetch_broker_orders(client, plan),
            positions=state.positions,
            equity=state.equity,
            last_equity=state.last_equity or state.equity,
            official_close=prices["official_close"],
            snapshot_1545=prices.get("snapshot_1545", {}),
            generated_at_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    except (BookAccountError, ValueError, KeyError) as exc:
        raise _fail(exc) from exc
    path = write_daily_file(root, record)
    rec, pnl = record["reconciliation"], record["pnl"]
    console.print(
        f"filled={rec['n_filled']} partial={rec['n_partial']} unfilled={rec['n_unfilled']} "
        f"missing={rec['n_missing']} gross_pnl={pnl['gross_pnl_broker']:.2f} "
        f"net_pnl={pnl['net_pnl']:.2f}"
    )
    console.print(f"daily file: {path}")


@book_paper_app.command("status")
def book_paper_status(account: str = ACCOUNT_OPTION) -> None:
    """Read-only account summary (no account number, no keys)."""
    from open_composer.book_paper.plan import read_account_state

    try:
        present = present_variables(account)
        console.print("env variables present: " + ", ".join(f"{k}={v}" for k, v in present.items()))
        state = read_account_state(make_trading_client(account))
    except BookAccountError as exc:
        raise _fail(exc) from exc
    console.print(
        f"{account}: status={state.status} equity={state.equity:.2f} "
        f"buying_power={state.buying_power} shorting_enabled={state.shorting_enabled} "
        f"positions={len(state.positions)} open_orders={len(state.open_orders)}"
    )


__all__ = ["book_paper_app", "credential_variable_names"]
