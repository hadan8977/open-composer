#!/usr/bin/env python3
"""Turn a rotation sleeve's latest paper targets into a manual order ticket for
the owner's own brokerage account. Read-only: it reads the target-weights file
the nightly paper cycle writes and never talks to a broker.

    uv run python scripts/live_ticket.py --equity 10000
    uv run python scripts/live_ticket.py --spec strategy_specs/drafts/<name>.yaml \\
        --equity 10000 --peak 11200 --now 9800

Share counts follow the paper sleeve: the same target weights and the same
reference closes (the anchor session's), floored to whole shares, so they stay
constant until the paper cycle issues a new rebalance id. Trade only when the
rebalance id differs from the last ticket you acted on. With ``--peak`` and
``--now`` (your account's high-water mark and current value) the ticket also
checks the spec's drawdown exit.

Writes ``reports/live-ticket/<rebalance session>-<strategy>.md``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "strategy_specs" / "drafts" / "us_etf_levered_rotation_63_top2_monthly.yaml"


def load_targets(name: str) -> dict:
    path = ROOT / "reports" / "execution" / f"{name}-target-weights.json"
    if not path.is_file():
        raise SystemExit(f"no target-weights file at {path}; the nightly paper cycle writes it")
    return json.loads(path.read_text(encoding="utf-8"))


def ticket(spec_path: Path, equity: float, peak: float | None, now: float | None) -> str:
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    name = spec["name"]
    rotation = (spec.get("portfolio") or {}).get("etf_rotation") or {}
    exit_pct = rotation.get("drawdown_exit_pct")
    data = load_targets(name)
    summary = data["summary"]
    rows = [r for r in data["target_weights"] if float(r.get("target_weight") or 0) > 0]
    lines = [
        f"# Live ticket: {name}",
        "",
        f"- Rebalance id: `{rows[0]['rebalance_id'] if rows else 'none'}` "
        "(act only if it differs from your last ticket)",
        f"- Targets decided on the close of {summary.get('anchor_session')}. To start, buy "
        "them at the next open; after that, trade only when the rebalance id changes",
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
    vt = summary.get("vol_target") or {}
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
        "Orders: place them for the open of the rebalance session (the paper sleeve uses "
        "opening limit orders). This file places no orders.",
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
