"""Portfolio paper rehearsal: bounded Alpaca Paper execution for a multi-name
candidate that has NOT passed the promotion gates (Step 17, 2026-09-15).

Why this exists
---------------
The order path that already exists (``oc run paper`` -> readiness -> canary
authorization -> ``submit_paper_order``) was built for one- or two-symbol ETF
router strategies: its canary caps are $1,000 per order and 4 orders per
session, its readiness chain requires a passing promotion report, and its
runner does not know ``portfolio.mode=model_ranking_portfolio`` at all. The
user's 2026-09-15 instruction is that a paper run must be live again this
week, and the best candidate on file (rule momentum top-50, 33%/-28% since
2024) fails gate v2. A *rehearsal* is therefore an explicitly acknowledged,
bounded, expiring, paper-only execution of a below-contract book whose purpose
is to exercise and measure the whole chain (targets -> orders -> fills ->
TCA), not to claim promotion.

Safety properties kept (in code, not paperwork)
------------------------------------------------
* Alpaca **paper** only: the verified paper client from
  ``adapters.broker.alpaca_paper`` (origin + credential checks) is reused; the
  authorization is bound to the paper account id hash and to the spec hash.
* Explicit, expiring operator authorization with limits: max gross exposure,
  max per-name weight, max orders / notional per session, max total notional.
* The global paper kill switch blocks every submission.
* Every order is preceded by a persisted signal (``signal_logs/``), carries a
  deterministic ``client_order_id`` (strategy, session, symbol, side) so a rerun
  in the same session cannot double-submit, and is appended to an append-only
  rehearsal ledger with the broker order id and status.
* Orders are opening-auction orders only (``moo_market`` or ``opg_limit``,
  time-in-force ``opg``), submitted only inside Alpaca's acceptance window
  (after 19:00 ET for the next open, before 09:28 ET the same morning).
* Every artifact is labelled ``rehearsal=below_contract`` with the gate status
  note verbatim. This module never touches ``strategy_specs/active`` or the
  router-era readiness/canary files.
* ``execution_policy.position_scope`` (2026-09-18) controls which positions a
  strategy is planned against when more than one strategy shares the same
  paper account. ``broker_account`` (the default, unchanged behaviour) plans
  against every position in the whole account. ``strategy_ledger`` plans
  against only this strategy's own recorded fills
  (``reports/paper/rehearsal/{name}-fills.jsonl``) so that one strategy's
  ``rehearsal-run`` never liquidates -- or double-counts -- another
  strategy's book, even when they hold the same symbol. The key is part of
  the execution-policy content hash, so it is covered by the rehearsal
  authorization like every other policy field.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from open_composer.adapters.broker.alpaca_paper import (
    PaperOrderError,
    _broker_order_by_client_id,
    _client_positions,
    _get_broker_orders,
    _optional_broker_account_hash,
    _require_verified_paper_client,
    _trading_client,
    sync_paper_account,
    sync_paper_orders,
)
from open_composer.config import project_root
from open_composer.engines.signal_engine import build_signal
from open_composer.execution_policy import require_orderable_execution_policy
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.paper_controls import load_paper_kill_switch
from open_composer.paper_lock import paper_control_lock
from open_composer.storage import append_jsonl, ensure_dir, write_json
from open_composer.strategy_versions import strategy_content_hash, strategy_version_id

REHEARSAL_DIRNAME = Path("reports") / "paper" / "rehearsal"
AUTHORIZATION_MAX_DURATION_DAYS = 45
SUPPORTED_PORTFOLIO_MODES = frozenset(
    {"model_ranking_portfolio", "insider_buy_portfolio", "etf_rotation_portfolio"}
)
#: Authorization id / status used when ``rehearsal-run`` is invoked as a dry run
#: before any authorization exists: the plan is produced with DEFAULT_LIMITS so
#: the operator can review it, and nothing can be submitted on that path.
UNAUTHORIZED_DRY_RUN_ID = "unauthorized-dry-run"
#: Opening-auction styles plus ``day_market``: Alpaca Paper's auction simulation
#: filled only 5 of 50 ``opg`` market orders on 2026-09-15 (45 expired at the
#: open, several partially), so a plain market order queued after the close and
#: executed at the 09:30 open is the reliable paper path. TCA still measures the
#: fill against the reference price and the official open.
ALLOWED_ORDER_STYLES = frozenset({"moo_market", "opg_limit", "loo_limit", "day_market"})
STYLE_TIME_IN_FORCE = {
    "moo_market": "opg",
    "opg_limit": "opg",
    "loo_limit": "opg",
    "day_market": "day",
}
#: Whole-share drift below this notional (and below the fraction of the target
#: value) is not worth an order; it only creates churn when reference prices move.
#: 2026-09-18: raised from 50 USD / 5% after the 2026-09-17 cycle sent 23 one-
#: to-two-share drift orders (100-400 USD each, median slippage -240 bp) on a
#: hold day simply because equity had grown ~1.5%. A 25% drift of a 2% position
#: is still corrected; weekly membership changes are unaffected (they compare
#: against a zero target/current side).
MIN_TRADE_NOTIONAL_USD = 100.0
CHURN_TOLERANCE_FRACTION = 0.25
#: Broker statuses that mean "this client_order_id never became a position";
#: a rerun may submit a fresh order for the same session.
TERMINAL_UNFILLED_STATUSES = frozenset({"canceled", "cancelled", "expired", "rejected", "replaced"})
TARGET_WEIGHTS_MAX_AGE_HOURS = 30
OPEN_ORDER_STATUSES = frozenset(
    {"accepted", "new", "partially_filled", "pending_cancel", "pending_new", "submitted", "held"}
)
DEFAULT_LIMITS: dict[str, float | int] = {
    "max_gross_exposure": 1.0,
    "max_symbol_weight": 0.05,
    "max_orders_per_session": 150,
    "max_session_notional_usd": 150_000.0,
    "max_total_notional_usd": 750_000.0,
}
#: Alpaca accepts opening-auction (``opg``) orders from 19:00 ET for the next
#: session until 09:28 ET on the session itself; anything in between is rejected.
OPG_ACCEPT_AFTER = time(19, 0)
OPG_ACCEPT_UNTIL = time(9, 28)


class RehearsalError(ValueError):
    """Raised when the rehearsal cannot proceed safely."""


@dataclass(frozen=True)
class RehearsalAuthorization:
    authorization_id: str
    strategy_name: str
    spec_hash: str
    version_id: str
    authorized_by: str
    authorized_at: str
    expires_at: str
    broker_account_id_hash: str
    limits: dict[str, float | int]
    below_contract_acknowledged: bool
    gate_status_note: str
    paper_only: bool = True
    path: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any], path: Path) -> RehearsalAuthorization:
        required = (
            "authorization_id",
            "strategy_name",
            "spec_hash",
            "version_id",
            "authorized_by",
            "authorized_at",
            "expires_at",
            "broker_account_id_hash",
            "limits",
            "below_contract_acknowledged",
            "gate_status_note",
        )
        missing = [key for key in required if payload.get(key) in (None, "", {})]
        if missing:
            raise RehearsalError(f"rehearsal authorization is missing fields: {missing}")
        if payload.get("paper_only") is not True:
            raise RehearsalError("rehearsal authorization must be paper_only")
        if payload.get("below_contract_acknowledged") is not True:
            raise RehearsalError("rehearsal authorization requires below_contract_acknowledged")
        return cls(
            authorization_id=str(payload["authorization_id"]),
            strategy_name=str(payload["strategy_name"]),
            spec_hash=str(payload["spec_hash"]),
            version_id=str(payload["version_id"]),
            authorized_by=str(payload["authorized_by"]),
            authorized_at=str(payload["authorized_at"]),
            expires_at=str(payload["expires_at"]),
            broker_account_id_hash=str(payload["broker_account_id_hash"]),
            limits=dict(payload["limits"]),
            below_contract_acknowledged=True,
            gate_status_note=str(payload["gate_status_note"]),
            paper_only=True,
            path=str(path),
        )


@dataclass
class RehearsalOrderPlan:
    symbol: str
    side: str
    action: str
    qty: float
    reference_price: float
    target_weight: float
    current_qty: float
    target_qty: float
    notional: float
    decision: str
    reason: str = ""
    signal_id: str | None = None
    client_order_id: str | None = None
    broker_order_id: str | None = None
    broker_status: str | None = None
    limit_price: float | None = None
    rebalance_id: str | None = None


@dataclass
class RehearsalCycleResult:
    strategy_name: str
    session: str
    status: str
    allow_paper_orders: bool
    equity: float
    plans: list[RehearsalOrderPlan] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    report_path: str | None = None
    #: ``execution_policy.position_scope`` resolved for this cycle; see the
    #: module docstring. Always set, even for ``broker_account``, so a report
    #: reader never has to guess which accounting the plan used.
    position_scope: str = "broker_account"
    #: Populated only when ``position_scope == "strategy_ledger"``: the
    #: ledger-derived positions the plan was built from, so an operator can
    #: see that other strategies' broker positions were deliberately ignored.
    scoped_positions: dict[str, float] = field(default_factory=dict)
    #: Populated only when ``position_scope == "strategy_ledger"``: the
    #: strategy's own sizing equity used for target quantities and the gross-
    #: exposure budget, in place of the whole account's equity.
    sizing_equity: float | None = None

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for plan in self.plans:
            out[plan.decision] = out.get(plan.decision, 0) + 1
        return out


# ---------------------------------------------------------------------------
# authorization


def rehearsal_dir(root: Path) -> Path:
    return root / REHEARSAL_DIRNAME


def rehearsal_authorization_path(root: Path, strategy_name: str) -> Path:
    return rehearsal_dir(root) / f"{strategy_name}-authorization.json"


def rehearsal_ledger_path(root: Path, strategy_name: str) -> Path:
    return rehearsal_dir(root) / f"{strategy_name}-orders.jsonl"


def rehearsal_fills_path(root: Path, strategy_name: str) -> Path:
    return rehearsal_dir(root) / f"{strategy_name}-fills.jsonl"


def _validate_limits(limits: dict[str, Any]) -> dict[str, float | int]:
    out: dict[str, float | int] = {}
    try:
        gross = float(limits["max_gross_exposure"])
        symbol_weight = float(limits["max_symbol_weight"])
        orders = int(limits["max_orders_per_session"])
        session_notional = float(limits["max_session_notional_usd"])
        total_notional = float(limits["max_total_notional_usd"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RehearsalError(f"rehearsal limits are malformed: {exc}") from exc
    if not 0 < gross <= 1.0:
        raise RehearsalError("max_gross_exposure must be in (0, 1]; leverage is out of scope")
    if not 0 < symbol_weight <= gross:
        raise RehearsalError("max_symbol_weight must be in (0, max_gross_exposure]")
    if orders < 1:
        raise RehearsalError("max_orders_per_session must be >= 1")
    if not (session_notional > 0 and total_notional >= session_notional):
        raise RehearsalError("notional limits must be positive and total >= session")
    out.update(
        max_gross_exposure=gross,
        max_symbol_weight=symbol_weight,
        max_orders_per_session=orders,
        max_session_notional_usd=session_notional,
        max_total_notional_usd=total_notional,
    )
    return out


def validate_rehearsal_spec(spec: StrategySpec, root: Path) -> dict[str, Any]:
    """Return the execution policy payload after checking the spec shape."""
    if spec.portfolio.mode not in SUPPORTED_PORTFOLIO_MODES:
        raise RehearsalError(
            f"paper rehearsal supports portfolio.mode in {sorted(SUPPORTED_PORTFOLIO_MODES)}, "
            f"got {spec.portfolio.mode!r}"
        )
    if spec.position_direction != "long_only":
        raise RehearsalError("paper rehearsal is long-only")
    try:
        binding = require_orderable_execution_policy(spec, root)
    except ValueError as exc:
        raise RehearsalError(str(exc)) from exc
    style = str(binding.payload.get("order_style") or "").lower()
    tif = str(binding.payload.get("time_in_force") or "").lower()
    if style not in ALLOWED_ORDER_STYLES or tif != STYLE_TIME_IN_FORCE.get(style):
        raise RehearsalError(
            "paper rehearsal requires an open-of-session execution policy "
            f"(order_style in {sorted(ALLOWED_ORDER_STYLES)} with its matching "
            f"time_in_force); got {style!r}/{tif!r}"
        )
    return {"policy_id": binding.policy_id, "policy_hash": binding.content_hash, **binding.payload}


def write_rehearsal_authorization(
    spec_path: Path,
    root: Path | None = None,
    *,
    authorized_by: str,
    confirm_paper_only: bool,
    acknowledge_below_contract: bool,
    gate_status_note: str,
    duration_days: int = 14,
    limits: dict[str, Any] | None = None,
    client: Any | None = None,
    now: datetime | None = None,
) -> Path:
    base = root or project_root()
    if not confirm_paper_only or not acknowledge_below_contract:
        raise RehearsalError(
            "rehearsal authorization requires --confirm-paper-only and --acknowledge-below-contract"
        )
    if not authorized_by.strip():
        raise RehearsalError("authorized_by must identify the confirming operator")
    if not gate_status_note.strip():
        raise RehearsalError("gate_status_note must state the candidate's gate result verbatim")
    if (
        isinstance(duration_days, bool)
        or not 1 <= int(duration_days) <= AUTHORIZATION_MAX_DURATION_DAYS
    ):
        raise RehearsalError(
            f"duration_days must be between 1 and {AUTHORIZATION_MAX_DURATION_DAYS}"
        )
    spec = load_strategy_spec(spec_path)
    validate_rehearsal_spec(spec, base)
    effective_limits = _validate_limits({**DEFAULT_LIMITS, **(limits or {})})
    if effective_limits["max_symbol_weight"] < float(spec.portfolio.max_symbol_weight or 0):
        raise RehearsalError(
            "max_symbol_weight limit is below the spec's own portfolio.max_symbol_weight"
        )
    broker = client or _trading_client()
    _require_verified_paper_client(broker)
    account = broker.get_account()
    account_hash = _optional_broker_account_hash(getattr(account, "id", None))
    if not account_hash:
        raise RehearsalError("paper account id is unavailable; cannot bind the authorization")
    sync_paper_account(base, broker)
    stamp = now or datetime.now(UTC)
    payload = {
        "authorization_kind": "portfolio_paper_rehearsal",
        "authorization_id": "reh_"
        + hashlib.sha256(
            f"{spec.name}|{strategy_content_hash(spec)}|{stamp.isoformat()}".encode()
        ).hexdigest()[:16],
        "strategy_name": spec.name,
        "spec_path": str(Path(spec_path)),
        "spec_hash": strategy_content_hash(spec),
        "version_id": strategy_version_id(spec),
        "authorized_by": authorized_by.strip(),
        "authorized_at": stamp.isoformat(),
        "expires_at": (stamp + timedelta(days=int(duration_days))).isoformat(),
        "broker_account_id_hash": account_hash,
        "limits": effective_limits,
        "below_contract_acknowledged": True,
        "gate_status_note": gate_status_note.strip(),
        "paper_only": True,
        "scope": (
            "Alpaca Paper only; opening-auction orders only; long-only; below-contract "
            "execution rehearsal, not a promotion. Real-money broker writes are out of scope."
        ),
    }
    path = rehearsal_authorization_path(base, spec.name)
    ensure_dir(path.parent)
    with paper_control_lock(base):
        write_json(path, payload)
        archive = path.with_name(f"{spec.name}-authorization-{stamp:%Y%m%dT%H%M%SZ}.json")
        write_json(archive, payload)
    return path


def _dry_run_placeholder_authorization(
    spec: StrategySpec, stamp: datetime
) -> RehearsalAuthorization:
    """Stand-in used only when no authorization file exists *and* orders are
    not allowed: lets ``rehearsal-run`` produce a reviewable plan report. It
    is never persisted, carries no account binding, and the cycle status is
    ``dry_run_unauthorized`` so it cannot be mistaken for an authorized run."""
    notes = spec.notes.model_dump(mode="json")
    rehearsal_notes = notes.get("paper_rehearsal") if isinstance(notes, dict) else None
    status = (
        rehearsal_notes.get("status") if isinstance(rehearsal_notes, dict) else None
    ) or "unknown"
    return RehearsalAuthorization(
        authorization_id=UNAUTHORIZED_DRY_RUN_ID,
        strategy_name=spec.name,
        spec_hash=strategy_content_hash(spec),
        version_id=strategy_version_id(spec),
        authorized_by="none (plan-only dry run, no authorization on file)",
        authorized_at=stamp.isoformat(),
        expires_at=stamp.isoformat(),
        broker_account_id_hash="",
        limits=dict(DEFAULT_LIMITS),
        below_contract_acknowledged=True,
        gate_status_note=(
            "UNAUTHORIZED DRY RUN: no rehearsal authorization on file; "
            f"notes.paper_rehearsal.status={status}; default limits; nothing can be submitted"
        ),
        paper_only=True,
        path="",
    )


def load_rehearsal_authorization(
    spec: StrategySpec, root: Path, *, now: datetime | None = None
) -> RehearsalAuthorization:
    path = rehearsal_authorization_path(root, spec.name)
    if not path.is_file():
        raise RehearsalError(f"no rehearsal authorization at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RehearsalError(f"rehearsal authorization is not valid JSON: {exc}") from exc
    auth = RehearsalAuthorization.from_payload(payload, path)
    if auth.strategy_name != spec.name:
        raise RehearsalError("rehearsal authorization belongs to a different strategy")
    if auth.spec_hash != strategy_content_hash(spec):
        raise RehearsalError(
            "rehearsal authorization was written for a different StrategySpec content hash; "
            "re-authorize after spec changes"
        )
    stamp = now or datetime.now(UTC)
    expires = datetime.fromisoformat(auth.expires_at)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if stamp >= expires:
        raise RehearsalError(f"rehearsal authorization expired at {auth.expires_at}")
    _validate_limits(auth.limits)
    return auth


def revoke_rehearsal_authorization(
    spec_path: Path, root: Path | None = None, *, reason: str
) -> Path:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    path = rehearsal_authorization_path(base, spec.name)
    if not path.is_file():
        raise RehearsalError(f"no rehearsal authorization at {path}")
    stamp = datetime.now(UTC)
    target = path.with_name(f"{spec.name}-authorization-revoked-{stamp:%Y%m%dT%H%M%SZ}.json")
    with paper_control_lock(base):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["revoked_at"] = stamp.isoformat()
        payload["revoked_reason"] = reason
        write_json(target, payload)
        path.unlink()
    return target


# ---------------------------------------------------------------------------
# planning (pure)


def load_target_rows(
    spec: StrategySpec, root: Path, *, now: datetime | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = root / "reports" / "execution" / f"{spec.name}-target-weights.json"
    if not path.is_file():
        raise RehearsalError(f"target weights artifact is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("strategy_name") != spec.name:
        raise RehearsalError("target weights artifact belongs to a different strategy")
    generated = payload.get("generated_at")
    if not generated:
        raise RehearsalError("target weights artifact has no generated_at")
    generated_at = datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    stamp = now or datetime.now(UTC)
    age_hours = (stamp - generated_at).total_seconds() / 3600
    if age_hours > TARGET_WEIGHTS_MAX_AGE_HOURS:
        raise RehearsalError(
            f"target weights artifact is {age_hours:.1f}h old (> {TARGET_WEIGHTS_MAX_AGE_HOURS}h); "
            "run oc strategy target-weights first"
        )
    rows = payload.get("target_weights")
    if not isinstance(rows, list) or not rows:
        raise RehearsalError("target weights artifact has no rows")
    return rows, payload


def _reference_price(row: dict[str, Any], equity_hint: float | None) -> float | None:
    price = row.get("reference_price")
    if price is not None:
        try:
            value = float(price)
            return value if value > 0 else None
        except (TypeError, ValueError):
            return None
    shares = float(row.get("shares") or 0)
    realized = float(row.get("realized_weight") or 0)
    sizing_equity = row.get("sizing_equity") or equity_hint
    if shares > 0 and realized > 0 and sizing_equity:
        return float(sizing_equity) * realized / shares
    return None


def plan_rehearsal_orders(
    *,
    target_rows: list[dict[str, Any]],
    positions: dict[str, float],
    position_prices: dict[str, float],
    open_order_symbols: set[str],
    equity: float,
    limits: dict[str, float | int],
    sizing_equity_hint: float | None = None,
) -> list[RehearsalOrderPlan]:
    """Turn target rows + broker state into per-symbol order plans (no I/O).

    Sells (risk reducing) are planned before buys; buys are cut off once the
    per-session order count, per-session notional, or gross-exposure limit
    would be exceeded, and the cut-off ones are marked ``deferred_*`` so the
    next session picks them up.
    """
    if not (math.isfinite(equity) and equity > 0):
        raise RehearsalError("paper account equity must be finite and positive")
    max_symbol_weight = float(limits["max_symbol_weight"])
    max_gross = float(limits["max_gross_exposure"])
    max_orders = int(limits["max_orders_per_session"])
    max_session_notional = float(limits["max_session_notional_usd"])

    targets: dict[str, dict[str, Any]] = {}
    for row in target_rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol or not row.get("selected"):
            continue
        targets[symbol] = row
    plans: list[RehearsalOrderPlan] = []
    projected_value = 0.0
    for symbol, current_qty in positions.items():
        if symbol in targets:
            continue
        price = position_prices.get(symbol) or 0.0
        if current_qty <= 0 or price <= 0:
            continue
        plans.append(
            RehearsalOrderPlan(
                symbol=symbol,
                side="sell",
                action="exit",
                qty=float(current_qty),
                reference_price=float(price),
                target_weight=0.0,
                current_qty=float(current_qty),
                target_qty=0.0,
                notional=float(current_qty) * float(price),
                decision="submit",
                reason="held but not in current targets",
            )
        )
    buys: list[RehearsalOrderPlan] = []
    for symbol, row in targets.items():
        weight = min(float(row.get("target_weight") or 0.0), max_symbol_weight)
        price = _reference_price(row, sizing_equity_hint)
        current_qty = float(positions.get(symbol, 0.0))
        if price is None:
            plans.append(
                RehearsalOrderPlan(
                    symbol=symbol,
                    side="buy",
                    action="entry",
                    qty=0.0,
                    reference_price=0.0,
                    target_weight=weight,
                    current_qty=current_qty,
                    target_qty=0.0,
                    notional=0.0,
                    decision="skip_no_reference_price",
                    rebalance_id=row.get("rebalance_id"),
                )
            )
            continue
        target_qty = float(math.floor(weight * equity / price)) if weight > 0 else 0.0
        projected_value += target_qty * price
        delta = target_qty - current_qty
        common = dict(
            symbol=symbol,
            reference_price=price,
            target_weight=weight,
            current_qty=current_qty,
            target_qty=target_qty,
            rebalance_id=row.get("rebalance_id"),
        )
        tolerance = max(
            MIN_TRADE_NOTIONAL_USD,
            CHURN_TOLERANCE_FRACTION * max(target_qty * price, current_qty * price),
        )
        if abs(delta) < 1 or (current_qty > 0 and abs(delta) * price <= tolerance):
            plans.append(
                RehearsalOrderPlan(
                    side="buy" if delta >= 0 else "sell",
                    action="hold",
                    qty=0.0,
                    notional=0.0,
                    decision="skip_no_change" if abs(delta) < 1 else "skip_below_tolerance",
                    reason=""
                    if abs(delta) < 1
                    else f"drift {abs(delta):.0f} sh < tolerance {tolerance:.0f} USD",
                    **common,
                )
            )
            continue
        plan = RehearsalOrderPlan(
            side="buy" if delta > 0 else "sell",
            action="entry" if delta > 0 else "exit",
            qty=abs(delta),
            notional=abs(delta) * price,
            decision="submit",
            **common,
        )
        if plan.side == "sell":
            plans.append(plan)
        else:
            buys.append(plan)
    for plan in plans + buys:
        if plan.decision == "submit" and plan.symbol in open_order_symbols:
            plan.decision = "skip_open_order"
            plan.reason = "an open broker order already exists for this symbol"
    # budgets: sells first (already in `plans`), then buys in target order
    session_orders = sum(1 for p in plans if p.decision == "submit")
    session_notional = sum(p.notional for p in plans if p.decision == "submit")
    held_value = sum(
        float(positions.get(s, 0.0)) * float(position_prices.get(s, 0.0)) for s in positions
    )
    gross_after = held_value
    for plan in buys:
        if plan.decision != "submit":
            continue
        if session_orders + 1 > max_orders:
            plan.decision, plan.reason = (
                "deferred_order_budget",
                f"max_orders_per_session={max_orders}",
            )
            continue
        if session_notional + plan.notional > max_session_notional + 1e-6:
            plan.decision, plan.reason = (
                "deferred_notional_budget",
                f"max_session_notional_usd={max_session_notional}",
            )
            continue
        if gross_after + plan.notional > max_gross * equity + 1e-6:
            plan.decision, plan.reason = (
                "deferred_gross_exposure",
                f"max_gross_exposure={max_gross}",
            )
            continue
        session_orders += 1
        session_notional += plan.notional
        gross_after += plan.notional
    plans.extend(buys)
    return plans


def _in_opg_acceptance_window(now: datetime, timezone: str) -> bool:
    local = now.astimezone(ZoneInfo(timezone))
    clock = local.time()
    if clock >= OPG_ACCEPT_AFTER:
        # evening: queued for the next session (a Friday evening queues for Monday)
        return True
    # early morning of a weekday: still accepted for today's open
    return clock <= OPG_ACCEPT_UNTIL and local.weekday() < 5


def _next_session(now: datetime, timezone: str) -> date:
    from open_composer.market_calendar import next_us_equity_session

    local = now.astimezone(ZoneInfo(timezone))
    if local.time() >= OPG_ACCEPT_AFTER:
        return next_us_equity_session(local.date())
    return next_us_equity_session(local.date() - timedelta(days=1))


def _client_order_id(
    strategy_name: str, session: date, symbol: str, side: str, style: str = ""
) -> str:
    digest = hashlib.sha256(
        f"{strategy_name}|{session.isoformat()}|{symbol}|{side}|{style}".encode()
    ).hexdigest()
    return f"reh-{session:%Y%m%d}-{symbol[:8]}-{digest[:12]}"


def _status_text(order: Any) -> str:
    status = getattr(order, "status", "")
    return str(getattr(status, "value", status)).split(".")[-1].lower()


def _ledger_rows(root: Path, strategy_name: str) -> list[dict[str, Any]]:
    path = rehearsal_ledger_path(root, strategy_name)
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# ---------------------------------------------------------------------------
# position_scope=strategy_ledger: per-strategy position accounting


def _fills_ledger_rows(root: Path, strategy_name: str) -> list[dict[str, Any]]:
    """Rows from ``reports/paper/rehearsal/{strategy_name}-fills.jsonl``, the
    artifact ``reconcile_rehearsal_fills`` writes. A missing file is legal --
    it means the strategy has never had a rehearsal order reconciled -- and is
    returned as an empty list, not an error."""
    path = rehearsal_fills_path(root, strategy_name)
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _require_ledger_reconciled(
    rows: list[dict[str, Any]], session: date, strategy_name: str
) -> None:
    """Fail closed when a ``position_scope=strategy_ledger`` position would be
    computed from a fill that has not been reconciled against the broker yet.

    ``reports/paper/rehearsal/{strategy}-fills.jsonl`` only reflects broker
    reality right after ``oc paper rehearsal-reconcile`` has run for this
    strategy; between a submission and the next reconcile, a row still shows
    whatever status it had when it was last written (or is simply absent). A
    row from a session strictly before the one being planned that is still
    non-terminal -- or was never resolved to a status at all -- means this
    module does not actually know whether those shares exist. Silently
    treating it as flat would understate the true position and could make the
    planner buy the same book a second time. Never guess: refuse, and name
    the unreconciled session so the operator can reconcile first.
    """
    terminal = TERMINAL_UNFILLED_STATUSES | {"filled"}
    for row in rows:
        raw_session = row.get("session")
        if not raw_session:
            continue
        try:
            row_session = date.fromisoformat(str(raw_session))
        except ValueError:
            continue
        if row_session >= session:
            continue
        status = str(row.get("status") or "").strip().lower()
        if status in terminal:
            continue
        raise RehearsalError(
            f"strategy ledger for {strategy_name!r} is unreconciled as of session "
            f"{row_session.isoformat()} (status={status or 'none'}); run "
            f"`oc paper rehearsal-reconcile <spec path for {strategy_name}>` before planning "
            "with position_scope=strategy_ledger"
        )


def _positions_from_fills_ledger(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Net filled quantity per symbol from this strategy's own fills ledger:
    a ``buy`` fill adds shares, a ``sell`` fill subtracts them. Symbols whose
    net rounds to zero (fully round-tripped) are dropped -- they are not a
    position to plan against."""
    net: dict[str, float] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        filled_qty = float(row.get("filled_qty") or 0.0)
        if filled_qty == 0:
            continue
        side = str(row.get("side") or "").lower()
        signed = filled_qty if side == "buy" else -filled_qty
        net[symbol] = net.get(symbol, 0.0) + signed
    return {symbol: qty for symbol, qty in net.items() if round(qty) != 0}


def _resolve_strategy_sizing_equity(summary: dict[str, Any]) -> float | None:
    """Equity to size and gross-cap a ``strategy_ledger`` plan against.

    Prefers the target-weights artifact's ``sizing_equity`` -- the capped
    equity an adapter records when a per-strategy budget (e.g.
    ``etf_rotation.notional_budget_usd``) binds below the account -- and
    falls back to the artifact's ``account_equity`` when no such cap applies
    (e.g. a model-ranking strategy sized against the whole account). Returns
    ``None`` when neither is a usable positive number; the caller must fail
    closed rather than guess an equity to size against.
    """
    for key in ("sizing_equity", "account_equity"):
        value = summary.get(key) if summary else None
        if value in (None, ""):
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


def cancel_open_rehearsal_orders(
    spec_path: Path, root: Path | None = None, *, reason: str, client: Any | None = None
) -> list[dict[str, Any]]:
    """Cancel this strategy's still-open rehearsal orders at the paper broker.

    Only orders whose client_order_id appears in this strategy's rehearsal
    ledger are touched; everything else on the account is left alone.
    """
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    ours = {
        row["client_order_id"]
        for row in _ledger_rows(base, spec.name)
        if row.get("client_order_id")
    }
    broker = client or _trading_client()
    _require_verified_paper_client(broker)
    cancelled: list[dict[str, Any]] = []
    for order in _get_broker_orders(broker, include_closed=False):
        coid = str(getattr(order, "client_order_id", ""))
        if coid not in ours or _status_text(order) in TERMINAL_UNFILLED_STATUSES | {"filled"}:
            continue
        broker.cancel_order_by_id(str(getattr(order, "id", "")))
        cancelled.append(
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                "strategy_name": spec.name,
                "client_order_id": coid,
                "broker_order_id": str(getattr(order, "id", "")),
                "symbol": str(getattr(order, "symbol", "")).upper(),
                "status_before": _status_text(order),
                "reason": reason,
            }
        )
    if cancelled:
        append_jsonl(rehearsal_dir(base) / f"{spec.name}-cancellations.jsonl", cancelled)
    return cancelled


def reconcile_rehearsal_fills(
    spec_path: Path, root: Path | None = None, *, client: Any | None = None
) -> dict[str, Any]:
    """Pull broker status for every ledgered rehearsal order and write a fills
    snapshot plus a per-session summary (fill rate, slippage vs reference)."""
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    rows = _ledger_rows(base, spec.name)
    broker = client or _trading_client()
    _require_verified_paper_client(broker)
    by_coid = {
        str(getattr(o, "client_order_id", "")): o
        for o in _get_broker_orders(broker, include_closed=True)
    }
    fills: list[dict[str, Any]] = []
    for row in rows:
        order = by_coid.get(str(row.get("client_order_id")))
        status = _status_text(order) if order is not None else "unknown"
        filled_qty = float(getattr(order, "filled_qty", 0) or 0) if order is not None else 0.0
        raw_price = getattr(order, "filled_avg_price", None) if order is not None else None
        fill_price = float(raw_price) if raw_price not in (None, "") else None
        ref = float(row.get("reference_price") or 0) or None
        slippage_bps = None
        if fill_price and ref:
            sign = 1.0 if row.get("side") == "buy" else -1.0
            slippage_bps = sign * (fill_price / ref - 1.0) * 10_000
        qty = float(row.get("qty") or 0)
        fills.append(
            {
                "session": row.get("session"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "qty": qty,
                "reference_price": ref,
                "order_style": row.get("order_style"),
                "client_order_id": row.get("client_order_id"),
                "broker_order_id": row.get("broker_order_id"),
                "status": status,
                "filled_qty": filled_qty,
                "filled_avg_price": fill_price,
                "filled_at": str(getattr(order, "filled_at", "") or "")[:19]
                if order is not None
                else None,
                "fill_fraction": (filled_qty / qty) if qty else None,
                "slippage_vs_reference_bps": slippage_bps,
            }
        )
    directory = rehearsal_dir(base)
    ensure_dir(directory)
    fills_path = rehearsal_fills_path(base, spec.name)
    fills_path.write_text(
        "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in fills), encoding="utf-8"
    )
    summary: dict[str, Any] = {
        "strategy_name": spec.name,
        "generated_at": datetime.now(UTC).isoformat(),
        "sessions": {},
    }
    for session in sorted({f["session"] for f in fills if f.get("session")}):
        all_part = [f for f in fills if f["session"] == session]
        cancelled = [f for f in all_part if f["status"] in {"canceled", "cancelled", "replaced"}]
        part = [f for f in all_part if f not in cancelled]
        notional = sum(f["qty"] * (f["reference_price"] or 0) for f in part)
        filled_notional = sum(f["filled_qty"] * (f["reference_price"] or 0) for f in part)
        slips = sorted(
            f["slippage_vs_reference_bps"]
            for f in part
            if f["slippage_vs_reference_bps"] is not None
        )
        summary["sessions"][session] = {
            "orders": len(part),
            "cancelled_before_open": len(cancelled),
            "filled_full": sum(1 for f in part if f["status"] == "filled"),
            "filled_partial": sum(
                1 for f in part if f["status"] != "filled" and f["filled_qty"] > 0
            ),
            "unfilled": sum(1 for f in part if f["filled_qty"] == 0),
            "fill_rate_by_notional": (filled_notional / notional) if notional else None,
            "median_slippage_vs_reference_bps": slips[len(slips) // 2] if slips else None,
            "order_styles": sorted({str(f.get("order_style")) for f in part}),
        }
    write_json(directory / f"{spec.name}-fills-summary.json", summary)
    lines = [
        f"# 成交对账 {spec.name}",
        "",
        "| 交易日 | 有效下单 | 开盘前撤单 | 全部成交 | 部分成交 | 未成交 | 按金额成交率 "
        "| 相对参考价滑点中位数(bp) | 单类型 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for session, v in summary["sessions"].items():
        rate = (
            f"{v['fill_rate_by_notional']:.0%}" if v["fill_rate_by_notional"] is not None else "-"
        )
        slip = (
            f"{v['median_slippage_vs_reference_bps']:.1f}"
            if v["median_slippage_vs_reference_bps"] is not None
            else "-"
        )
        lines.append(
            f"| {session} | {v['orders']} | {v['cancelled_before_open']} | {v['filled_full']} | "
            f"{v['filled_partial']} | "
            f"{v['unfilled']} | {rate} | {slip} | {', '.join(v['order_styles'])} |"
        )
    (directory / f"{spec.name}-fills-summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return summary


def _open_order_symbols(client: Any, *, own_client_order_ids: set[str] | None = None) -> set[str]:
    """Symbols with an open order at the broker.

    ``own_client_order_ids`` scopes the answer to one strategy. It must be
    supplied whenever ``position_scope == "strategy_ledger"``, because the check
    exists to stop a strategy double-submitting its own order, not to stop two
    sleeves from both holding a symbol.

    This was a real defect, found from a live fill: on 2026-09-18 the sector
    sleeve submitted XLK at 23:35 UTC and the growth sleeve's own XLK leg was
    then skipped at 23:40 with "an open broker order already exists for this
    symbol", leaving that sleeve half invested. Scoping positions per strategy
    was not enough; open orders need the same scoping.
    """
    symbols: set[str] = set()
    for order in _get_broker_orders(client, include_closed=False):
        status = str(
            getattr(getattr(order, "status", ""), "value", getattr(order, "status", ""))
        ).lower()
        if status not in OPEN_ORDER_STATUSES and status:
            continue
        if own_client_order_ids is not None:
            coid = str(getattr(order, "client_order_id", ""))
            if coid not in own_client_order_ids:
                continue
        symbols.add(str(getattr(order, "symbol", "")).upper())
    return symbols


def _ledger_total_notional(root: Path, strategy_name: str, authorization_id: str) -> float:
    path = rehearsal_ledger_path(root, strategy_name)
    if not path.is_file():
        return 0.0
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("authorization_id") == authorization_id and record.get("broker_order_id"):
            total += float(record.get("notional") or 0.0)
    return total


def _submit(client: Any, plan: RehearsalOrderPlan, policy: dict[str, Any]) -> Any:
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

    side = OrderSide.BUY if plan.side == "buy" else OrderSide.SELL
    style = str(policy.get("order_style") or "").lower()
    tif = TimeInForce.DAY if style == "day_market" else TimeInForce.OPG
    if style in {"moo_market", "day_market"}:
        request = MarketOrderRequest(
            symbol=plan.symbol,
            qty=plan.qty,
            side=side,
            time_in_force=tif,
            client_order_id=plan.client_order_id,
        )
    else:
        protection = policy.get("price_protection") or {}
        offset = float(protection.get("limit_offset_bps") or 0.0) / 10_000.0
        multiplier = 1 + offset if plan.side == "buy" else 1 - offset
        plan.limit_price = round(plan.reference_price * multiplier, 2)
        request = LimitOrderRequest(
            symbol=plan.symbol,
            qty=plan.qty,
            side=side,
            time_in_force=TimeInForce.OPG,
            limit_price=plan.limit_price,
            client_order_id=plan.client_order_id,
        )
    return client.submit_order(request)


def run_portfolio_paper_rehearsal(
    spec_path: Path,
    root: Path | None = None,
    *,
    allow_paper_orders: bool,
    client: Any | None = None,
    now: datetime | None = None,
    liquidate: bool = False,
    liquidation_reason: str | None = None,
) -> RehearsalCycleResult:
    """Plan (and optionally submit) one session of a rehearsal book.

    ``liquidate=True`` winds a strategy down on a shared account: it plans
    against an empty target book, so every position in this strategy's own
    fills ledger is sold and nothing is bought. It is refused unless the spec
    declares ``position_scope: strategy_ledger`` (a ``broker_account``
    liquidation would sell every other strategy's positions too) and needs a
    reason, which is copied into the cycle report. The target weights artifact
    is not read. Authorization, kill switch, submission window, open-order and
    ledger-reconciliation checks all still apply.
    """
    base = root or project_root()
    stamp = now or datetime.now(UTC)
    spec = load_strategy_spec(spec_path)
    policy = validate_rehearsal_spec(spec, base)
    reason_text = (liquidation_reason or "").strip()
    if liquidate:
        if str(policy.get("position_scope") or "broker_account") != "strategy_ledger":
            raise RehearsalError(
                "liquidate requires execution_policy.position_scope=strategy_ledger; a "
                "broker_account liquidation would sell every strategy's positions on the account"
            )
        if not reason_text:
            raise RehearsalError("liquidate requires a reason; it is copied into the cycle report")
    unauthorized_dry_run = (
        not allow_paper_orders and not rehearsal_authorization_path(base, spec.name).is_file()
    )
    if unauthorized_dry_run:
        auth = _dry_run_placeholder_authorization(spec, stamp)
    else:
        auth = load_rehearsal_authorization(spec, base, now=stamp)
    timezone = spec.data_assumptions.timezone
    session = _next_session(stamp, timezone)
    result = RehearsalCycleResult(
        strategy_name=spec.name,
        session=session.isoformat(),
        status="planned",
        allow_paper_orders=allow_paper_orders,
        equity=0.0,
        # Resolved up front (even on an early kill-switch return) so a report
        # never shows the "broker_account" default for a spec that actually
        # declares strategy_ledger.
        position_scope=str(policy.get("position_scope") or "broker_account"),
    )
    result.notes.append(f"rehearsal=below_contract; {auth.gate_status_note}")
    if liquidate:
        result.notes.append(
            f"liquidation: sell this strategy's whole ledger; reason: {reason_text}"
        )
    if unauthorized_dry_run:
        result.notes.append(
            "no rehearsal authorization on file: plan-only dry run with DEFAULT_LIMITS; run "
            "`oc paper authorize-rehearsal` before any --allow-paper-orders run"
        )

    kill_switch = load_paper_kill_switch(base, require_control_file=True)
    if kill_switch.enabled:
        result.status = "blocked_by_kill_switch"
        result.notes.append(f"paper kill switch enabled: {kill_switch.reason}")
        _write_cycle_report(base, result, auth, policy)
        return result

    broker = client or _trading_client()
    _require_verified_paper_client(broker)
    sync_paper_account(base, broker)
    try:
        sync_paper_orders(base, broker)
    except PaperOrderError as exc:
        # The router-era ledger (reports/paper/orders.jsonl) may reference orders
        # from a paper account that has since been reset; that reconciliation is
        # not this path's job. Open orders are still read directly from the broker.
        result.notes.append(f"legacy order sync skipped: {exc}"[:300])
    account = broker.get_account()
    account_hash = _optional_broker_account_hash(getattr(account, "id", None))
    if not unauthorized_dry_run and account_hash != auth.broker_account_id_hash:
        raise RehearsalError("rehearsal authorization is bound to a different paper account")
    equity = float(getattr(account, "equity", 0) or 0)
    result.equity = equity
    broker_positions: dict[str, float] = {}
    broker_position_prices: dict[str, float] = {}
    for position in _client_positions(broker):
        symbol = str(getattr(position, "symbol", "")).upper()
        broker_positions[symbol] = float(getattr(position, "qty", 0) or 0)
        price = getattr(position, "current_price", None)
        broker_position_prices[symbol] = float(price) if price else 0.0
    scope_for_open_orders = str(policy.get("position_scope") or "broker_account")
    own_coids: set[str] | None = None
    if scope_for_open_orders == "strategy_ledger":
        own_coids = {
            str(row["client_order_id"])
            for row in _ledger_rows(base, spec.name)
            if row.get("client_order_id")
        }
    open_symbols = _open_order_symbols(broker, own_client_order_ids=own_coids)
    if liquidate:
        rows, artifact = [], {}
    else:
        rows, artifact = load_target_rows(spec, base, now=stamp)
    sizing_hint = None
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    if summary and summary.get("account_equity"):
        sizing_hint = float(summary["account_equity"])
    manifest = summary.get("selection_manifest") if summary else None
    if isinstance(manifest, dict):
        # Adapters that publish a selection manifest (feature dates, cohort,
        # fallbacks, skips) get its audit keys copied into the cycle report.
        audit_keys = (
            "insider_feature_date",
            "feature_date_bound_last_completed_session",
            "insider_feature_root",
            "insider_root_fallback_used",
            "universe_root",
            "universe_root_fallback_used",
            "universe_month_end",
            "eligible_after_thresholds",
            "skipped_stale_count",
            "selected_count",
            "gross_effective",
            "gross_scaled_down",
            "is_new_signal",
            "warnings",
        )
        audit = {key: manifest.get(key) for key in audit_keys if key in manifest}
        result.notes.append(
            "target_weights_manifest=" + json.dumps(audit, ensure_ascii=False, default=str)[:1500]
        )

    # position_scope: broker_account (default, unchanged) plans against every
    # broker position; strategy_ledger plans against only this strategy's own
    # recorded fills, and sizes/gross-caps against its own sizing equity
    # instead of the whole account. See the module docstring. Already
    # resolved onto `result` above so an early kill-switch return reports it
    # too.
    position_scope = result.position_scope
    plan_equity = equity
    if position_scope == "strategy_ledger":
        fills_rows = _fills_ledger_rows(base, spec.name)
        _require_ledger_reconciled(fills_rows, session, spec.name)
        positions = _positions_from_fills_ledger(fills_rows)
        artifact_prices: dict[str, float] = {}
        for row in rows:
            row_symbol = str(row.get("symbol") or "").upper()
            row_price = row.get("reference_price")
            if row_symbol and row_price not in (None, "") and float(row_price) > 0:
                artifact_prices[row_symbol] = float(row_price)
        position_prices = {
            symbol: (
                broker_position_prices[symbol]
                if symbol in broker_positions
                else artifact_prices.get(symbol, 0.0)
            )
            for symbol in positions
        }
        # A liquidation places no buys, so its sizing equity only feeds the
        # gross-exposure cap on buys; the account equity is a safe stand-in.
        plan_equity = equity if liquidate else _resolve_strategy_sizing_equity(summary)
        if plan_equity is None:
            raise RehearsalError(
                "position_scope=strategy_ledger requires the target weights artifact's "
                "summary to record a positive sizing_equity or account_equity; found neither"
            )
        result.scoped_positions = dict(positions)
        result.sizing_equity = plan_equity
        result.notes.append(
            "position_scope=strategy_ledger: planned against this strategy's own ledger "
            f"positions ({positions}), ignoring any other strategy's broker positions; "
            f"sizing_equity={plan_equity:.2f}"
        )
    else:
        positions = broker_positions
        position_prices = broker_position_prices

    plans = plan_rehearsal_orders(
        target_rows=rows,
        positions=positions,
        position_prices=position_prices,
        open_order_symbols=open_symbols,
        equity=plan_equity,
        limits=auth.limits,
        sizing_equity_hint=sizing_hint,
    )
    result.plans = plans
    if liquidate:
        planned_sells = {plan.symbol for plan in plans if plan.side == "sell"}
        not_sold = sorted(symbol for symbol in positions if symbol not in planned_sells)
        if not_sold:
            result.notes.append(
                "liquidation did NOT sell (no broker price or non-positive ledger qty): "
                + ", ".join(not_sold)
            )
        for plan in plans:
            plan.rebalance_id = f"{spec.name}:liquidation:{session.isoformat()}"
            if plan.decision == "submit":
                plan.reason = f"liquidation: {reason_text}"

    prior_total = _ledger_total_notional(base, spec.name, auth.authorization_id)
    max_total = float(auth.limits["max_total_notional_usd"])
    window_ok = _in_opg_acceptance_window(stamp, timezone)
    if allow_paper_orders and not window_ok:
        for plan in plans:
            if plan.decision == "submit":
                plan.decision, plan.reason = (
                    "blocked_by_submission_window",
                    ("opening-auction orders are accepted only after 19:00 ET or before 09:28 ET"),
                )
    spec_hash = strategy_content_hash(spec)
    version_id = strategy_version_id(spec)
    signal_log = base / "signal_logs" / f"paper-rehearsal-{spec.name}.jsonl"
    ledger = rehearsal_ledger_path(base, spec.name)
    ensure_dir(ledger.parent)
    run_id = f"paper-rehearsal-{spec.name}-{session.isoformat()}"
    for plan in plans:
        if plan.decision != "submit":
            continue
        plan.client_order_id = _client_order_id(
            spec.name, session, plan.symbol, plan.side, str(policy.get("order_style") or "")
        )
        signal = build_signal(
            spec,
            run_id,
            stamp,
            plan.action if plan.action != "hold" else "entry",
            "paper_rehearsal",
            plan.reference_price,
            version_id=version_id,
            spec_hash=spec_hash,
            symbol=plan.symbol,
            qty=plan.qty,
            target_weight=plan.target_weight,
            conditions=[
                "rehearsal=below_contract",
                f"session={session.isoformat()}",
                f"rebalance_id={plan.rebalance_id}",
                f"target_qty={plan.target_qty:.0f}",
                f"current_qty={plan.current_qty:.0f}",
                f"client_order_id={plan.client_order_id}",
                f"authorization_id={auth.authorization_id}",
            ],
            side_override=plan.side,  # type: ignore[arg-type]
        )
        plan.signal_id = signal.id
        append_jsonl(signal_log, [signal])
        if not allow_paper_orders:
            plan.decision = "would_submit"
            continue
        existing = _broker_order_by_client_id(broker, plan.client_order_id)
        if existing is not None and _status_text(existing) in TERMINAL_UNFILLED_STATUSES:
            existing = None  # canceled/expired: nothing became a position, submit afresh
        if existing is not None:
            plan.decision = "already_submitted"
            plan.broker_order_id = str(getattr(existing, "id", ""))
            plan.broker_status = str(
                getattr(getattr(existing, "status", ""), "value", getattr(existing, "status", ""))
            )
            continue
        if prior_total + plan.notional > max_total + 1e-6:
            plan.decision, plan.reason = (
                "deferred_total_budget",
                f"max_total_notional_usd={max_total}",
            )
            continue
        try:
            with paper_control_lock(base):
                fresh = load_paper_kill_switch(base, require_control_file=True)
                if fresh.enabled:
                    raise PaperOrderError("paper kill switch enabled")
                order = _submit(broker, plan, policy)
        except Exception as exc:  # broker rejections are recorded, never raised past the loop
            plan.decision = "rejected"
            plan.reason = f"{exc.__class__.__name__}: {exc}"[:300]
            continue
        plan.broker_order_id = str(getattr(order, "id", ""))
        plan.broker_status = str(
            getattr(getattr(order, "status", ""), "value", getattr(order, "status", ""))
        )
        plan.decision = "submitted"
        prior_total += plan.notional
        append_jsonl(
            ledger,
            [
                {
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "authorization_id": auth.authorization_id,
                    "strategy_name": spec.name,
                    "session": session.isoformat(),
                    "rebalance_id": plan.rebalance_id,
                    "symbol": plan.symbol,
                    "side": plan.side,
                    "qty": plan.qty,
                    "order_style": policy.get("order_style"),
                    "time_in_force": STYLE_TIME_IN_FORCE.get(
                        str(policy.get("order_style") or ""), "opg"
                    ),
                    "limit_price": plan.limit_price,
                    "reference_price": plan.reference_price,
                    "notional": plan.notional,
                    "client_order_id": plan.client_order_id,
                    "broker_order_id": plan.broker_order_id,
                    "broker_status": plan.broker_status,
                    "signal_id": plan.signal_id,
                    "spec_hash": spec_hash,
                    "paper": True,
                    "rehearsal": "below_contract",
                }
            ],
        )
    counts = result.counts()
    if counts.get("rejected"):
        result.status = "partial" if counts.get("submitted") else "rejected"
    elif counts.get("submitted"):
        result.status = "submitted"
    elif allow_paper_orders and counts.get("already_submitted"):
        result.status = "already_submitted"
    elif allow_paper_orders and counts.get("blocked_by_submission_window"):
        result.status = "blocked_by_submission_window"
    elif not allow_paper_orders:
        result.status = "dry_run_unauthorized" if unauthorized_dry_run else "dry_run"
    else:
        result.status = "no_orders"
    _write_cycle_report(base, result, auth, policy)
    return result


def _write_cycle_report(
    root: Path, result: RehearsalCycleResult, auth: RehearsalAuthorization, policy: dict[str, Any]
) -> None:
    directory = rehearsal_dir(root)
    ensure_dir(directory)
    stamp = datetime.now(UTC)
    payload = {
        "report_type": "portfolio_paper_rehearsal_cycle",
        "rehearsal": "below_contract",
        "gate_status_note": auth.gate_status_note,
        "strategy_name": result.strategy_name,
        "session": result.session,
        "generated_at": stamp.isoformat(),
        "status": result.status,
        "allow_paper_orders": result.allow_paper_orders,
        "equity": result.equity,
        "position_scope": result.position_scope,
        "strategy_ledger_positions": result.scoped_positions
        if result.position_scope == "strategy_ledger"
        else None,
        "strategy_ledger_sizing_equity": result.sizing_equity
        if result.position_scope == "strategy_ledger"
        else None,
        "authorization_id": auth.authorization_id,
        "authorization_expires_at": auth.expires_at,
        "limits": auth.limits,
        "execution_policy_id": policy.get("policy_id"),
        "order_style": policy.get("order_style"),
        "counts": result.counts(),
        "submitted_notional": sum(p.notional for p in result.plans if p.decision == "submitted"),
        "notes": result.notes,
        "orders": [asdict(plan) for plan in result.plans],
        "paper": True,
        "broker_writes": any(p.decision == "submitted" for p in result.plans),
    }
    json_path = directory / f"{result.strategy_name}-{result.session}-{stamp:%H%M%S}.json"
    write_json(json_path, payload)
    latest = directory / f"{result.strategy_name}-latest.json"
    write_json(latest, payload)
    md_path = latest.with_suffix(".md")
    lines = [
        f"# 模拟盘彩排 {result.strategy_name} — 目标交易日 {result.session}",
        "",
        f"- 状态：{result.status}（允许下单：{result.allow_paper_orders}）",
        f"- 定位：低于合同的执行彩排；{auth.gate_status_note}",
        f"- 账户权益：{result.equity:,.2f} 美元；"
        f"本次提交名义金额：{payload['submitted_notional']:,.2f}",
        f"- 持仓口径 position_scope：{result.position_scope}"
        + (
            f"（仅本策略账本持仓 {result.scoped_positions}；"
            f"用于定位与总敞口预算的策略自身权益 sizing_equity="
            f"{result.sizing_equity:,.2f}，忽略其他策略在同一账户的持仓）"
            if result.position_scope == "strategy_ledger" and result.sizing_equity is not None
            else "（该策略与账户其他持仓共用同一口径，或本轮在计算持仓前已终止）"
        ),
        f"- 各决策计数：{payload['counts']}",
        f"- 授权 {auth.authorization_id} 到期 {auth.expires_at}；限额 {auth.limits}",
        "",
        "| 代码 | 方向 | 股数 | 参考价 | 目标权重 | 决策 | 说明 |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for plan in result.plans:
        lines.append(
            f"| {plan.symbol} | {plan.side} | {plan.qty:.0f} | {plan.reference_price:.2f} | "
            f"{plan.target_weight:.3f} | {plan.decision} | "
            f"{plan.reason or plan.broker_status or ''} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    append_jsonl(directory / "cycles.jsonl", [{k: v for k, v in payload.items() if k != "orders"}])
    result.report_path = str(json_path)
    try:
        from open_composer.notifications import safe_dispatch_notification

        severity = (
            "info"
            if result.status in {"submitted", "dry_run", "dry_run_unauthorized", "no_orders"}
            else "warn"
        )
        safe_dispatch_notification(
            kind="signal_paper_only",
            severity=severity,
            title=f"paper rehearsal {result.strategy_name} {result.session}: {result.status}",
            body=f"counts={payload['counts']} equity={result.equity:,.0f} below_contract",
            metadata={"report": str(json_path)},
            root=root,
        )
    except Exception:  # notifications must never break the cycle
        pass
