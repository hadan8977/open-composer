#!/usr/bin/env python3
"""Turn a rotation sleeve's latest paper targets into a manual order ticket for
the owner's own brokerage account. Read-only: it reads the target-weights file
the nightly paper cycle writes and never talks to a broker.

    uv run python scripts/live_ticket.py --equity 10000
    uv run python scripts/live_ticket.py --spec strategy_specs/drafts/<name>.yaml \\
        --equity 10000 --peak 11200 --now 9800

Share counts follow the paper sleeve: the same target weights and reference
prices, floored to whole shares. Trade only when the ticket's targets
fingerprint differs from the last ticket you acted on. The fingerprint changes
at each monthly rebalance and also when the dip boost switches the volatility
overlay's target inside a month (the multiplier is otherwise constant between
updates). Keying on the rebalance id alone would miss those in-month changes;
the rebalance id also stayed the same on 2026-09-24, when the renewed rules
first applied the overlay and the paper sleeve sold UPRO for SHY. With
``--peak`` and ``--now`` (your account's high-water mark and current value)
the ticket also checks the spec's drawdown exit.

Writes ``reports/live-ticket/<rebalance session>-<strategy>.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "strategy_specs" / "drafts" / "us_etf_levered_rotation_63_top2_monthly.yaml"
# How the paper sleeve sends orders, by the spec's execution_policy.order_style
# (open_composer/paper_rehearsal.py); anything else is an opening limit order.
ORDER_STYLE_TEXT = {
    "day_market": "market orders sent after the prior close, which fill at the open",
    "moo_market": "market-on-open orders",
}


def load_targets(name: str) -> dict:
    path = ROOT / "reports" / "execution" / f"{name}-target-weights.json"
    if not path.is_file():
        raise SystemExit(f"no target-weights file at {path}; the nightly paper cycle writes it")
    return json.loads(path.read_text(encoding="utf-8"))


def targets_fingerprint(rows: list[dict], multiplier: object) -> str:
    """Short hash of what the owner would trade: rebalance id, overlay multiplier,
    and each leg's rounded weight and reference price."""
    legs = sorted(
        (
            str(r.get("symbol")),
            round(float(r["target_weight"]), 4),
            round(float(r["reference_price"]), 2),
        )
        for r in rows
    )
    rebalance = rows[0].get("rebalance_id") if rows else None
    if isinstance(multiplier, int | float):
        multiplier = round(float(multiplier), 4)
    payload = json.dumps([rebalance, multiplier, legs], sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


def ticket(spec_path: Path, equity: float, peak: float | None, now: float | None) -> str:
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    name = spec["name"]
    rotation = (spec.get("portfolio") or {}).get("etf_rotation") or {}
    exit_pct = rotation.get("drawdown_exit_pct")
    style = str((spec.get("execution_policy") or {}).get("order_style") or "").lower()
    order_text = ORDER_STYLE_TEXT.get(style, "opening limit orders")
    data = load_targets(name)
    summary = data["summary"]
    rows = [r for r in data["target_weights"] if float(r.get("target_weight") or 0) > 0]
    vt = summary.get("vol_target") or {}
    fingerprint = targets_fingerprint(rows, vt.get("multiplier"))
    lines = [
        f"# Live ticket: {name}",
        "",
        f"- Targets fingerprint: `{fingerprint}` (act only if it differs from the last "
        "ticket you acted on; it changes at the monthly rebalance and whenever the "
        "volatility overlay moves the weights)",
        f"- Rebalance id: `{rows[0]['rebalance_id'] if rows else 'none'}`",
        f"- Targets decided on the close of {summary.get('anchor_session')}. To start, buy "
        "them at the next open; after that, trade whenever the fingerprint changes",
        f"- Paper data through {summary.get('latest_session')}; "
        f"generated {data.get('generated_at')}",
        f"- Your equity for sizing: ${equity:,.0f}",
        "",
        "| symbol | target weight | reference close | shares | notional |",
        "|---|---|---|---|---|",
    ]
    total = 0.0
    for r in sorted(rows, key=lambda r: -float(r["target_weight"])):
        price = float(r["reference_price"])
        shares = math.floor(equity * float(r["target_weight"]) / price)
        total += shares * price
        lines.append(
            f"| {r['symbol']} | {float(r['target_weight']):.1%} | {price:,.2f} | {shares} | "
            f"${shares * price:,.0f} |"
        )
    lines += [
        "",
        f"Invested ${total:,.0f} of ${equity:,.0f}; the rest stays in cash.",
    ]
    if vt:
        lines.append(
            f"Volatility target multiplier {vt.get('multiplier')} "
            f"(boost active: {vt.get('boost_active')})."
        )
    if exit_pct:
        lines += [
            "",
            f"Drawdown exit: sell everything to cash if your account falls {exit_pct:.0%} "
            "below its highest value since you started, and stop following the ticket.",
        ]
        if peak and now:
            dd = 1.0 - now / peak
            state = "BREACHED: sell everything" if dd >= exit_pct else "not breached"
            lines.append(f"Your drawdown now: {dd:.1%} from ${peak:,.0f} ({state}).")
    lines += [
        "",
        f"Orders: the paper sleeve trades these at the open of {summary.get('rebalance_session')} "
        f"with {order_text}; if that open has passed, use the next open. This file places "
        "no orders.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    ap.add_argument("--equity", type=float, required=True, help="your account value in USD")
    ap.add_argument("--peak", type=float, help="your account's highest value since you started")
    ap.add_argument("--now", type=float, help="your account's value now")
    args = ap.parse_args(argv)
    text = ticket(args.spec, args.equity, args.peak, args.now)
    data = load_targets(yaml.safe_load(args.spec.read_text(encoding="utf-8"))["name"])
    session = data["summary"].get("rebalance_session") or "unknown"
    out = ROOT / "reports" / "live-ticket" / f"{session}-{data['strategy_name']}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    print(f"\nwritten {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
