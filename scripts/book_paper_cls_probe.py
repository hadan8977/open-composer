"""One-share auction-order probe (time_in_force=cls, or opg/day) on a v1.2 book paper account.

T-20261005-02 / data pitfall #55: the v1.2 engine submits ``MarketOrderRequest(...,
time_in_force=TimeInForce.CLS)`` (``open_composer/book_paper/plan.py``), and Alpaca's order docs
mark CLS "Yes* -- contact sales".  This probe uses the same client factory
(``accounts.make_trading_client``, strict paper verification) and the same request type for a
single share, then records what the broker does with it.

Modes (one per call; every call appends one JSON line to
``reports/paper/book/<account>/probes/<execution date>-cls-probe.jsonl``):

* ``account``: read-only account and asset facts (status, shorting, multiplier, ETB flags).
* ``submit --execute``: one market order of ``--qty`` (must be 1) shares with ``--tif``
  (default ``cls``); with ``--require-position Q`` only when the account holds exactly Q shares
  (closing a probe).  Refused outside the New York weekday window for that time in force:
  ``cls`` 09:30-15:45 (Alpaca rejects CLS 15:50-19:00 ET); ``opg`` 04:00-09:25 (Alpaca rejects
  OPG 09:28-19:00 ET); ``day`` 09:35-15:45 (used to close an ``opg`` probe the same morning).
* ``status``: the broker's view of the probe order (status, fill, timestamps).

T-20261005-30 added ``--tif opg|day``: the opening-auction probe runs on 10-06, before the v1.2
books hold positions.  ``cls`` probe ids and log names are unchanged.

No secrets are printed: only the broker's order/account fields listed below.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NEW_YORK = ZoneInfo("America/New_York")
WINDOWS_ET = {
    "cls": (time(9, 30), time(15, 45)),
    "opg": (time(4, 0), time(9, 25)),
    "day": (time(9, 35), time(15, 45)),
}
ACCOUNT_FIELDS = (
    "status",
    "trading_blocked",
    "account_blocked",
    "shorting_enabled",
    "multiplier",
    "pattern_day_trader",
    "equity",
    "buying_power",
)
ASSET_FIELDS = ("tradable", "shortable", "easy_to_borrow", "marginable", "exchange")
ORDER_FIELDS = (
    "id",
    "client_order_id",
    "status",
    "symbol",
    "side",
    "qty",
    "filled_qty",
    "filled_avg_price",
    "time_in_force",
    "order_type",
    "created_at",
    "submitted_at",
    "filled_at",
    "canceled_at",
    "expired_at",
    "failed_at",
)


def _text(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float)):
        return v
    return str(getattr(v, "value", v))


def _fields(obj: Any, names: tuple[str, ...]) -> dict[str, Any]:
    return {n: _text(getattr(obj, n, None)) for n in names}


def probe_id(account: str, day: str, side: str, symbol: str, tif: str = "cls") -> str:
    return f"probe-{tif}-{account}-{day}-{side}-{symbol}".lower()


def in_window(now: datetime, tif: str = "cls") -> bool:
    et = now.astimezone(NEW_YORK)
    first, last = WINDOWS_ET[tif]
    return et.weekday() < 5 and first <= et.time() <= last


def log_path(root: Path, account: str, day: str, tif: str = "cls") -> Path:
    return root / "reports/paper/book" / account / "probes" / f"{day}-{tif}-probe.jsonl"


def append(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def run(
    args: argparse.Namespace,
    *,
    client_factory: Callable[[str], Any],
    now: datetime,
    root: Path = ROOT,
) -> int:
    day = now.astimezone(NEW_YORK).date().isoformat()
    tif = getattr(args, "tif", "cls")
    cid = probe_id(args.account, args.day or day, args.side, args.symbol, tif)
    rec: dict[str, Any] = {
        "logged_at_utc": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": args.mode,
        "account": args.account,
        "symbol": args.symbol,
        "side": args.side,
        "time_in_force": tif,
        "client_order_id": cid,
    }
    path = log_path(root, args.account, args.day or day, tif)
    if args.mode == "submit":
        if not args.execute:
            rec["result"] = "dry: pass --execute to send"
            append(path, rec)
            print(json.dumps(rec))
            return 0
        if args.qty != 1:
            raise SystemExit("probe qty must be 1")
        if not in_window(now, tif):
            first, last = WINDOWS_ET[tif]
            rec["result"] = (
                f"refused: outside {first:%H:%M}-{last:%H:%M} New York on a weekday for {tif}"
            )
            append(path, rec)
            print(json.dumps(rec))
            return 2
    client = client_factory(args.account)
    if args.mode == "account":
        rec["account_fields"] = _fields(client.get_account(), ACCOUNT_FIELDS)
        rec["asset_fields"] = _fields(client.get_asset(args.symbol), ASSET_FIELDS)
    elif args.mode == "submit":
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        from open_composer.adapters.broker.alpaca_paper import _require_verified_paper_client

        _require_verified_paper_client(client)
        if args.require_position is not None:
            try:
                held = float(getattr(client.get_open_position(args.symbol), "qty", 0) or 0)
            except Exception:  # noqa: BLE001 (no position raises)
                held = 0.0
            rec["held_qty"] = held
            if abs(held - args.require_position) > 1e-9:
                rec["result"] = f"refused: holds {held}, required {args.require_position}"
                append(path, rec)
                print(json.dumps(rec))
                return 4
        request = MarketOrderRequest(
            symbol=args.symbol,
            qty=args.qty,
            side=OrderSide.BUY if args.side == "buy" else OrderSide.SELL,
            time_in_force={"cls": TimeInForce.CLS, "opg": TimeInForce.OPG, "day": TimeInForce.DAY}[
                tif
            ],
            client_order_id=cid,
        )
        try:
            rec["order"] = _fields(client.submit_order(request), ORDER_FIELDS)
            rec["result"] = "submitted"
        except Exception as exc:  # noqa: BLE001 (the broker's refusal is the measurement)
            rec["result"] = "submit_error"
            rec["error_class"] = exc.__class__.__name__
            rec["error"] = str(exc)[:500]
    else:
        try:
            rec["order"] = _fields(client.get_order_by_client_id(cid), ORDER_FIELDS)
            rec["result"] = "found"
        except Exception as exc:  # noqa: BLE001
            rec["result"] = "lookup_error"
            rec["error_class"] = exc.__class__.__name__
            rec["error"] = str(exc)[:500]
    append(path, rec)
    print(json.dumps(rec, default=str))
    return 0 if rec.get("result") in (None, "submitted", "found") else 3


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=["account", "submit", "status"])
    ap.add_argument("--account", required=True, choices=["quant1", "quant2"])
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--side", choices=["buy", "sell"], default="buy")
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--tif", choices=sorted(WINDOWS_ET), default="cls")
    ap.add_argument("--day", default=None, help="probe day (New York) for status lookups")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument(
        "--require-position",
        type=float,
        default=None,
        help="submit only if the account holds exactly this many shares (closing a probe)",
    )
    args = ap.parse_args(argv)
    from open_composer.book_paper.accounts import make_trading_client

    return run(args, client_factory=make_trading_client, now=datetime.now(UTC))


if __name__ == "__main__":
    raise SystemExit(main())
