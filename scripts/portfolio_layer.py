#!/usr/bin/env python3
"""Portfolio layer CLI (T-20261006-24): allocate | check | report.  Read-only; advice only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def cmd_check(args: argparse.Namespace) -> int:
    from open_composer.portfolio_layer.check import exit_code, format_checks, run_check

    checks = run_check(args.account)
    print(format_checks(args.account, checks))
    return exit_code(checks)


def cmd_report(args: argparse.Namespace) -> int:
    from open_composer.portfolio_layer import report

    path = report.save(report.build())
    print(f"wrote {path}")
    return 0


def cmd_allocate(args: argparse.Namespace) -> int:
    """Recommended sleeve weights from the latest 252 days with the chosen rule (results.json)."""
    import numpy as np

    from open_composer.portfolio_layer import evaluate as V
    from open_composer.portfolio_layer import registry as G
    from open_composer.portfolio_layer.report import OUT

    res_path = OUT / "results.json"
    chosen = json.loads(res_path.read_text())["selection"]["chosen"] if res_path.exists() else "A1"
    reg = G.load_registry()
    ev = [s for s in G.evaluable(reg) if args.account in (None, s.account)]
    if not ev:
        print("no evaluable sleeves")
        return 2
    r = G.return_frame(reg)[[s.id for s in ev]].iloc[-V.WINDOW :]
    kind = chosen if chosen in ("A0", "A1", "A2") else "A2"
    spec = V.RuleSpec(chosen, kind)
    w = V.target_weights(
        spec, r.to_numpy(), [s.status for s in ev], np.array([s.capital_usd for s in ev])
    )
    print(f"rule {chosen}; window ends {r.index[-1].date()}")
    for s, x in zip(ev, w, strict=True):
        print(
            f"{s.account:7} {s.id:20} {s.status:12} weight {x:.3f}  "
            f"current capital {s.capital_usd:,.0f}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="read-only limit check; exit 1 on breach")
    c.add_argument("--account", required=True, choices=["quant1", "quant2", "main"])
    c.set_defaults(fn=cmd_check)
    a = sub.add_parser("allocate", help="recommended weights (advice)")
    a.add_argument("--account", choices=["quant1", "quant2", "main"], default=None)
    a.set_defaults(fn=cmd_allocate)
    rp = sub.add_parser("report", help="run the preregistered evaluation, write results.json")
    rp.set_defaults(fn=cmd_report)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
