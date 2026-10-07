#!/usr/bin/env python3
"""Options multi-leg (mleg) order probe for the main Alpaca Paper account.

Questions (T-20261007-05): can the main paper account trade options and at which level; are
2-leg put spreads and 4-leg iron condors accepted as ``order_class=mleg``; why are they
rejected when they are; does cancel work; how do the probe orders look to reconciliation.

    uv run python scripts/options_mleg_probe.py check
    uv run python scripts/options_mleg_probe.py submit-test            # plan only, no order
    uv run python scripts/options_mleg_probe.py submit-test --submit   # coordinator, market hours

Safety design
* ``check`` and the default ``submit-test`` are read-only (account, contracts, quotes).
* Orders need the explicit ``--submit`` flag, an open-circuit global paper kill switch, and a
  client from the strict paper factory (``alpaca_paper._trading_client``; the paper origin is
  verified there, this script never builds an address).
* Every order: 1 contract per leg, DAY, a limit credit far above the mid (unfillable, capped at
  90% of the width), client order id ``probe-mleg-<YYYYMMDD>-<2leg|4leg>``.  Each is polled to
  accepted/rejected, cancelled, and polled to a confirmed cancel.  Any failure cancels every
  order this script placed before exiting.
* Credentials are read by the project's existing loaders (variable names only); nothing is
  printed except account option fields and order fields.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROBE_PREFIX = "probe-mleg"
OPTION_FIELDS = (
    "options_trading_level",
    "options_approved_level",
    "options_buying_power",
    "status",
    "trading_blocked",
    "account_blocked",
    "multiplier",
    "buying_power",
)
OPEN_OK = {"new", "accepted", "pending_new", "accepted_for_bidding"}
TERMINAL = {"canceled", "cancelled", "expired", "rejected", "filled", "replaced"}
WIDTH = 5.0
OTM_FRACTION = 0.05
FALLBACK_CREDIT = {2: 4.00, 4: 4.00}  # unfillable on a 5-wide structure; used when no quote
CREDIT_CAP = 0.9 * WIDTH
MULTIPLE = 3.0


class ProbeError(RuntimeError):
    pass


def _text(value: Any) -> str:
    text = str(getattr(value, "value", value))
    if text.startswith(("OrderStatus.", "OrderClass.", "OrderSide.", "PositionIntent.")):
        text = text.split(".", 1)[1]  # str(enum) on older SDKs; numbers keep their decimals
    return text.lower()


def account_options(trading: Any) -> dict[str, Any]:
    account = trading.get_account()
    return {name: _text(getattr(account, name, None)) for name in OPTION_FIELDS}


def list_contracts(
    trading: Any, underlying: str, today: date, *, min_days: int = 7, max_days: int = 21
) -> list[dict[str, Any]]:
    from alpaca.trading.enums import AssetStatus
    from alpaca.trading.requests import GetOptionContractsRequest

    request = GetOptionContractsRequest(
        underlying_symbols=[underlying],
        status=AssetStatus.ACTIVE,
        expiration_date_gte=today + timedelta(days=min_days),
        expiration_date_lte=today + timedelta(days=max_days),
        limit=1000,
    )
    out: list[dict[str, Any]] = []
    for _ in range(10):  # page guard
        response = trading.get_option_contracts(request)
        for item in getattr(response, "option_contracts", None) or []:
            out.append(
                {
                    "symbol": str(item.symbol),
                    "expiration": str(item.expiration_date),
                    "strike": float(item.strike_price),
                    "type": _text(item.type),
                    "tradable": bool(getattr(item, "tradable", True)),
                }
            )
        token = getattr(response, "next_page_token", None)
        if not token:
            break
        request.page_token = token
    return out


def pick_expiry(contracts: list[dict[str, Any]], today: date, target_days: int = 14) -> str:
    expiries = sorted({c["expiration"] for c in contracts})
    if not expiries:
        raise ProbeError("no SPY contracts expire in the 7-21 day window")
    return min(expiries, key=lambda e: abs((date.fromisoformat(e) - today).days - target_days))


def _nearest(strikes: dict[float, str], target: float) -> float:
    return min(strikes, key=lambda k: abs(k - target))


def select_legs(contracts: list[dict[str, Any]], expiry: str, spot: float) -> dict[str, Any]:
    """Short ~5% OTM put + long put 5 below (2-leg), plus short ~5% OTM call + long call 5 above."""
    puts = {
        c["strike"]: c["symbol"]
        for c in contracts
        if c["expiration"] == expiry and c["type"] == "put" and c["tradable"]
    }
    calls = {
        c["strike"]: c["symbol"]
        for c in contracts
        if c["expiration"] == expiry and c["type"] == "call" and c["tradable"]
    }
    short_put = _nearest(puts, spot * (1 - OTM_FRACTION))
    short_call = _nearest(calls, spot * (1 + OTM_FRACTION))
    if short_put - WIDTH not in puts or short_call + WIDTH not in calls:
        raise ProbeError("no strikes exactly 5 dollars away from the chosen short strikes")
    return {
        "expiry": expiry,
        "spot": spot,
        "short_put": (short_put, puts[short_put]),
        "long_put": (short_put - WIDTH, puts[short_put - WIDTH]),
        "short_call": (short_call, calls[short_call]),
        "long_call": (short_call + WIDTH, calls[short_call + WIDTH]),
    }


def quote_mids(option_data: Any, symbols: list[str]) -> dict[str, float | None]:
    """Mid of the latest quote per option symbol; ``None`` when the free feed has nothing."""
    try:
        from alpaca.data.enums import OptionsFeed
        from alpaca.data.requests import OptionLatestQuoteRequest

        response = option_data.get_option_latest_quote(
            OptionLatestQuoteRequest(symbol_or_symbols=symbols, feed=OptionsFeed.INDICATIVE)
        )
    except Exception:
        return {s: None for s in symbols}
    mids: dict[str, float | None] = {}
    for symbol in symbols:
        quote = response.get(symbol) if hasattr(response, "get") else None
        bid, ask = getattr(quote, "bid_price", 0) or 0, getattr(quote, "ask_price", 0) or 0
        mids[symbol] = (bid + ask) / 2 if bid > 0 and ask > 0 else None
    return mids


def credit_limit(
    structure: str, legs: dict[str, Any], mids: dict[str, float | None]
) -> tuple[float, str]:
    """Unfillable limit credit: 3x the mid credit (capped at 90% of the width), else a fixed one."""
    short_put, long_put = legs["short_put"][1], legs["long_put"][1]
    if structure == "2leg":
        names = [short_put, long_put]
        parts = [mids.get(short_put), mids.get(long_put)]
        mid = None if None in parts else parts[0] - parts[1]
    else:
        names = [short_put, long_put, legs["short_call"][1], legs["long_call"][1]]
        parts = [mids.get(n) for n in names]
        mid = None if None in parts else parts[0] - parts[1] + parts[2] - parts[3]
    n = 2 if structure == "2leg" else 4
    if mid is None or mid <= 0:
        return FALLBACK_CREDIT[n], f"no usable quote for {names}: fixed fallback credit"
    return round(min(MULTIPLE * mid, CREDIT_CAP), 2), f"{MULTIPLE}x mid credit {mid:.4f}"


def build_request(structure: str, legs: dict[str, Any], credit: float, cid: str) -> Any:
    from alpaca.trading.enums import OrderClass, OrderSide, PositionIntent, TimeInForce
    from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest

    def leg(symbol: str, side: OrderSide, intent: PositionIntent) -> Any:
        return OptionLegRequest(symbol=symbol, ratio_qty=1, side=side, position_intent=intent)

    sell, buy = OrderSide.SELL, OrderSide.BUY
    request_legs = [
        leg(legs["short_put"][1], sell, PositionIntent.SELL_TO_OPEN),
        leg(legs["long_put"][1], buy, PositionIntent.BUY_TO_OPEN),
    ]
    if structure == "4leg":
        request_legs += [
            leg(legs["short_call"][1], sell, PositionIntent.SELL_TO_OPEN),
            leg(legs["long_call"][1], buy, PositionIntent.BUY_TO_OPEN),
        ]
    # Alpaca net price convention for mleg: a credit is a negative limit price.
    return LimitOrderRequest(
        qty=1,
        order_class=OrderClass.MLEG,
        time_in_force=TimeInForce.DAY,
        limit_price=-abs(credit),
        legs=request_legs,
        client_order_id=cid,
    )


class Probe:
    def __init__(
        self,
        trading: Any,
        out_dir: Path,
        *,
        sleep: Callable[[float], None] = time.sleep,
        polls: int = 15,
        interval: float = 1.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.trading, self.out_dir = trading, out_dir
        self.sleep, self.polls, self.interval, self.clock = sleep, polls, interval, clock
        self.placed: list[tuple[str, str | None]] = []  # (client order id, broker id)
        self.rows: list[dict[str, Any]] = []
        out_dir.mkdir(parents=True, exist_ok=True)
        self.path = out_dir / "probe.jsonl"

    def log(self, step: str, **fields: Any) -> dict[str, Any]:
        row = {"ts": self.clock().isoformat(), "step": step, **fields}
        self.rows.append(row)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        return row

    @staticmethod
    def order_fields(order: Any) -> dict[str, Any]:
        return {
            "id": str(getattr(order, "id", "")),
            "client_order_id": getattr(order, "client_order_id", None),
            "status": _text(getattr(order, "status", "")),
            "order_class": _text(getattr(order, "order_class", "")),
            "limit_price": str(getattr(order, "limit_price", "")),
            "qty": str(getattr(order, "qty", "")),
            "legs": [
                {
                    "symbol": getattr(x, "symbol", None),
                    "side": _text(getattr(x, "side", "")),
                    "status": _text(getattr(x, "status", "")),
                }
                for x in getattr(order, "legs", None) or []
            ],
        }

    def poll(self, cid: str, wanted: set[str], step: str) -> dict[str, Any] | None:
        last: dict[str, Any] | None = None
        for _ in range(self.polls):
            order = self.trading.get_order_by_client_id(cid)
            last = self.order_fields(order)
            self.log(step, **last)
            if last["status"] in wanted:
                return last
            self.sleep(self.interval)
        return last

    def probe_one(self, structure: str, request: Any, note: str) -> dict[str, Any]:
        cid = request.client_order_id
        result: dict[str, Any] = {"structure": structure, "cid": cid, "note": note}
        self.log(
            "submit",
            structure=structure,
            cid=cid,
            limit_price=request.limit_price,
            legs=[(x.symbol, _text(x.side), _text(x.position_intent)) for x in request.legs],
        )
        try:
            order = self.trading.submit_order(request)
        except Exception as exc:  # the rejection reason is the answer
            result.update(accepted=False, rejection=_error_fields(exc))
            self.log("rejected", structure=structure, cid=cid, **result["rejection"])
            return result
        self.placed.append((cid, str(getattr(order, "id", ""))))
        first = self.order_fields(order)
        self.log("submit_response", structure=structure, **first)
        seen = self.poll(cid, OPEN_OK | TERMINAL, "poll_accept")
        result["accepted"] = bool(seen and seen["status"] in OPEN_OK)
        result["status_after_submit"] = seen["status"] if seen else None
        if seen and seen["status"] not in TERMINAL:
            self.cancel(cid, str(first["id"]), result)
        else:
            result["cancel"] = "not needed (already terminal)"
        return result

    def cancel(self, cid: str, broker_id: str, result: dict[str, Any] | None = None) -> bool:
        try:
            self.trading.cancel_order_by_id(broker_id)
            self.log("cancel_requested", cid=cid, id=broker_id)
        except Exception as exc:
            self.log("cancel_error", cid=cid, **_error_fields(exc))
        done = self.poll(cid, TERMINAL, "poll_cancel")
        ok = bool(done and done["status"] in {"canceled", "cancelled", "expired"})
        if result is not None:
            result["cancel_confirmed"] = ok
            result["status_after_cancel"] = done["status"] if done else None
        return ok

    def cancel_all_placed(self) -> None:
        for cid, _broker_id in self.placed:
            try:
                order = self.trading.get_order_by_client_id(cid)
                if _text(order.status) not in TERMINAL:
                    self.cancel(cid, str(order.id))
            except Exception as exc:
                self.log("cleanup_error", cid=cid, **_error_fields(exc))


def _error_fields(exc: Exception) -> dict[str, Any]:
    return {
        "error_type": exc.__class__.__name__,
        "status_code": getattr(exc, "status_code", None),
        "message": str(exc)[:500],
    }


def plan(
    trading: Any, option_data: Any, stock_spot: Callable[[str], float], underlying: str, today: date
) -> dict[str, Any]:
    contracts = list_contracts(trading, underlying, today)
    expiry = pick_expiry(contracts, today)
    spot = stock_spot(underlying)
    legs = select_legs(contracts, expiry, spot)
    symbols = [legs[k][1] for k in ("short_put", "long_put", "short_call", "long_call")]
    mids = quote_mids(option_data, symbols)
    return {"contracts": len(contracts), "legs": legs, "mids": mids}


def run_submit_test(
    trading: Any,
    option_data: Any,
    stock_spot: Callable[[str], float],
    root: Path,
    *,
    underlying: str = "SPY",
    submit: bool = False,
    kill_check: Callable[[], str | None],
    today: date | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    day = today or datetime.now(UTC).date()
    out_dir = root / "reports" / "paper" / "options-probe" / day.isoformat()
    probe = Probe(trading, out_dir, sleep=sleep)
    fields = account_options(trading)
    probe.log("account_options", **fields)
    p = plan(trading, option_data, stock_spot, underlying, day)
    probe.log(
        "plan",
        expiry=p["legs"]["expiry"],
        spot=p["legs"]["spot"],
        legs={k: v for k, v in p["legs"].items() if isinstance(v, tuple)},
        mids=p["mids"],
    )
    requests = []
    for structure in ("2leg", "4leg"):
        credit, note = credit_limit(structure, p["legs"], p["mids"])
        cid = f"{PROBE_PREFIX}-{day:%Y%m%d}-{structure}"
        requests.append((structure, build_request(structure, p["legs"], credit, cid), note))
    summary: dict[str, Any] = {
        "day": day.isoformat(),
        "account": fields,
        "plan": p["legs"],
        "submitted": submit,
        "results": [],
    }
    if not submit:
        for structure, request, note in requests:
            probe.log(
                "plan_only", structure=structure, payload=request.model_dump(mode="json"), note=note
            )
        write_summary(out_dir, summary)
        return summary
    blocked = kill_check()
    if blocked:
        probe.log("refused", reason=blocked)
        raise ProbeError(f"refusing to submit: {blocked}")
    try:
        for structure, request, note in requests:
            summary["results"].append(probe.probe_one(structure, request, note))
    except BaseException as exc:
        probe.log("aborted", **_error_fields(exc) if isinstance(exc, Exception) else {})
        probe.cancel_all_placed()
        write_summary(out_dir, summary)
        raise
    probe.cancel_all_placed()  # belt and braces: nothing of ours stays open
    write_summary(out_dir, summary)
    return summary


def write_summary(out_dir: Path, summary: dict[str, Any]) -> None:
    lines = [
        f"# Options mleg probe {summary['day']}",
        "",
        f"- account fields: {summary['account']}",
        f"- submitted: {summary['submitted']}",
        "",
    ]
    legs = summary["plan"]
    lines.append(
        f"- expiry {legs['expiry']}, spot {legs['spot']}: "
        + ", ".join(
            f"{k}={legs[k][1]}" for k in ("short_put", "long_put", "short_call", "long_call")
        )
    )
    for r in summary["results"]:
        lines += [
            "",
            f"## {r['structure']} `{r['cid']}`",
            f"- limit: {r['note']}",
            f"- accepted: {r.get('accepted')}; status after submit: {r.get('status_after_submit')}",
        ]
        if r.get("rejection"):
            lines.append(f"- rejection: {r['rejection']}")
        lines.append(
            f"- cancel confirmed: {r.get('cancel_confirmed', r.get('cancel'))}; "
            f"status after cancel: {r.get('status_after_cancel')}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _real_clients() -> tuple[Any, Any, Callable[[str], float]]:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import StockLatestTradeRequest
    from dotenv import load_dotenv

    from open_composer.adapters.broker.alpaca_paper import _trading_client
    from open_composer.config import alpaca_api_key_id, alpaca_api_secret_key

    load_dotenv(ROOT / ".env")  # into os.environ only; nothing is printed
    trading = _trading_client()  # strict paper factory: verifies the paper origin
    key, secret = alpaca_api_key_id(), alpaca_api_secret_key()
    option_data = OptionHistoricalDataClient(api_key=key, secret_key=secret)
    stock_data = StockHistoricalDataClient(api_key=key, secret_key=secret)

    def spot(symbol: str) -> float:
        trade = stock_data.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
        return float(trade[symbol].price)

    return trading, option_data, spot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "submit-test"):
        p = sub.add_parser(name)
        p.add_argument("--underlying", default="SPY")
        if name == "submit-test":
            p.add_argument(
                "--submit", action="store_true", help="really place and cancel the orders"
            )
    args = parser.parse_args(argv)
    trading, option_data, spot = _real_clients()
    today = datetime.now(UTC).date()
    if args.command == "check":
        fields = account_options(trading)
        print(json.dumps({"account_options": fields}, indent=2))
        contracts = list_contracts(trading, args.underlying, today)
        expiry = pick_expiry(contracts, today)
        legs = select_legs(contracts, expiry, spot(args.underlying))
        symbols = [legs[k][1] for k in ("short_put", "long_put", "short_call", "long_call")]
        print(
            json.dumps(
                {
                    "contracts_in_window": len(contracts),
                    "expiry": expiry,
                    "spot": legs["spot"],
                    "legs": {k: v for k, v in legs.items() if isinstance(v, tuple)},
                    "quote_mids": quote_mids(option_data, symbols),
                },
                indent=2,
                default=str,
            )
        )
        return 0
    from open_composer.intraday_runner.engine import default_kill_check

    summary = run_submit_test(
        trading,
        option_data,
        spot,
        ROOT,
        underlying=args.underlying,
        submit=args.submit,
        kill_check=default_kill_check(ROOT),
    )
    print(
        json.dumps(
            {
                "submitted": summary["submitted"],
                "results": [
                    {
                        k: r.get(k)
                        for k in ("structure", "accepted", "cancel_confirmed", "rejection")
                    }
                    for r in summary["results"]
                ],
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
