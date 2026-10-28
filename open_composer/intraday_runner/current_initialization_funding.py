"""One prospective BASE funding flow; no source, model, or order implementation."""

from __future__ import annotations

import copy

from open_composer.intraday_runner.current_initialization_controls import (
    number,
    receive_observation,
)
from open_composer.intraday_runner.source_dispatch_journal import _hash

MAIN_SHA = "8ed43c3947f1c0a6139cbb2714d00a0443f063c510589f35442b23f53fcb73b9"


def funding_snapshot(current, observed, *, now, monotonic, account_hash, main, capture_binding):
    """Preserve original generation; explicitly account for one external virtual flow."""
    obs = receive_observation(
        observed,
        now=now,
        now_monotonic=monotonic,
        account_hash=account_hash,
        checkpoint_hash=_hash(current),
    )
    value = copy.deepcopy(current["snapshot"])
    evidence = value["evidence"]
    if (
        main.get("sha256") != MAIN_SHA
        or current["generation"] != 0
        or value["cashbook"]
        != dict(cash=10000, sales=[], purchases=[], dividends=[], lots={}, next_id=0)
        or any(value[k] for k in ("pending", "consumed_ids", "applied_fill_ids", "fills", "fees"))
        or evidence.get("unresolved_actual_liabilities") is not False
        or evidence.get("allocation_flows")
        or number(evidence["allocated_capital"]) != 10000
        or number(obs["verified_nav"]) != 10000
        or number(obs["account_unborrowed_available"]) < 120000
        or obs["holdings"]
        or obs["other_checkpoint_hashes"]
        or number(obs["account_marked_value"]) != 0
    ):
        raise ValueError("funding requires exact empty predecessor and current selected funds")
    risk = evidence["risk"]
    if (
        number(risk["initial_capital"]) != 10000
        or number(risk.get("net_allocation_flows", 0)) != 0
        or any(type(risk.get(k)) is not bool for k in ("halted", "killed"))
        or number(risk["high_water"]) <= 0
    ):
        raise ValueError("unreceived prior risk state")
    old_risk = copy.deepcopy(risk)
    # Maintain the same pre-flow drawdown ratio. Neither latch may be cleared.
    for key in ("high_water", "day_open_nav", "last_nav"):
        if risk.get(key) is not None:
            risk[key] = str(number(risk[key]) * 2)
    risk["net_allocation_flows"] = "10000"
    evidence["allocated_capital"] = "20000"
    value["cashbook"]["cash"] = 20000
    evidence["allocation_flows"] = [
        dict(
            event_id="BASE-prospective-allocation-20261020-20k",
            amount_USD="10000",
            main=main,
            predecessor_sha256=_hash(current),
            capture=capture_binding,
            observed_at=now.isoformat(),
            previous_risk=old_risk,
            resulting_risk=copy.deepcopy(risk),
            profit_USD="0",
            broker_deposit=False,
            original_initial_capital_USD="10000",
        )
    ]
    return value
