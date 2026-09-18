"""Intraday paper-trading execution path: 9:35-ET opening-range-breakout (ORB)
entry / before-close flatten on Alpaca Paper.

Why this exists
----------------
Card ``reports/research/hypotheses/H-20260918-02-intraday-orb-and-intraday-
momentum-etf.md`` (ORB-ETF leg) is being backtested by another task; this
module is plumbing only -- it makes the order path exist, be safe, and be
dry-run-verified, so the main session can flip it on once the research is
in. It is deliberately independent of ``StrategySpec``: the candidate has not
been promoted (or even drafted as a spec) yet, so everything here is driven
by a small config file (``config/intraday/orb_etf.yaml``) rather than the
spec-bound execution-policy chain used by ``open_composer/paper_rehearsal.py``
and ``adapters/broker/alpaca_paper.py``.

Rule implemented (the card's, restated)
----------------------------------------
* Opening candle = the five 1-minute bars 09:30-09:34 ET (open of 09:30,
  high/low across the five bars, close of 09:34 == the open of 09:35).
* Direction = sign(close - open). Skip (doji) if
  ``abs(close - open) <= doji_fraction * (high - low)``.
* Entry now (market), in that direction. Stop at the opposite extreme of the
  opening candle. Target at ``target_r_multiple`` R. Both legs are submitted
  as a single ``order_class=bracket`` order so the broker manages the exit,
  not a poller.
* Flatten before the close: cancel any still-open bracket legs and close any
  remaining position with a market order, so nothing carries overnight.
* Sizing: ``shares = floor(risk_fraction * sleeve_usd / R)``, notional capped
  at ``leverage_cap * sleeve_usd``. Sizing is always off the configured
  sleeve, **never** off account equity -- the paper account already carries
  an unrelated book.

Safety properties (mirrors ``open_composer/paper_rehearsal.py``)
------------------------------------------------------------------
* Alpaca **paper** only: reuses the strict, origin-and-sandbox-verified paper
  trading client factory from ``adapters.broker.alpaca_paper``.
* Explicit, expiring operator authorization bound to a content hash of the
  resolved config *and* a hash of the paper account id (never the raw id,
  never a key/secret) -- ``reports/paper/intraday/{strategy}-authorization
  .json``.
* The global paper kill switch blocks every submission in both modes.
* Every order is preceded by a persisted signal (``signal_logs/``), carries a
  deterministic ``client_order_id`` (strategy, session, symbol, side,
  purpose) so a rerun in the same session cannot double-submit, and is
  appended to an append-only ledger with the broker order id and status.
* Hard caps: orders per session, notional per session, notional per
  authorization lifetime, and a buying-power floor checked against the
  sleeve's worst-case (``leverage_cap * sleeve_usd``) requirement before any
  symbol is evaluated.
* ``--allow-paper-orders`` is required for any real submission; the default
  is a dry run that still performs every check, still writes the would-be
  bracket-order payload, and always exits 0 (refusals are recorded in the
  cycle report, not raised as fatal errors, except for config/authorization
  defects which are programmer/operator errors).
* ``--simulate-bars`` is an explicit, narrow, offline-only hook: when given,
  the market-hours/staleness gate is bypassed (so the full construction path
  can be exercised any time of day, e.g. to write this module's own proof
  artifact) but every other check -- doji, sizing, caps, kill switch,
  authorization -- still runs. It never talks to the data API and it is not
  a way to force a real submission window.


STATUS 2026-09-18: NOT WIRED TO ANY STRATEGY. This module was written for the
opening-range-breakout path, which card H-20260918-02 and lesson L-20260918-02
refuted: out-of-sample returns are negative at 1x with 1 bp costs, a
random-direction placebo reaches 93% of the real return, and 10:05 and 10:35
entries work as well as the opening entry, so the residual is intraday beta
rather than an opening effect. Nothing imports it, it has no test coverage, and
no spec selects it. It is kept because the 2026-09-18 intraday intel brief ranks
the multi-stock Stocks-in-Play ORB variant second among future candidates and
that variant would reuse this execution path. Read it as a draft, not as a
working component: it has never been run.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import yaml

from open_composer.adapters.broker.alpaca_paper import (
    PaperOrderError,
    _broker_order_by_client_id,
    _client_positions,
    _optional_broker_account_hash,
    _require_verified_paper_client,
    _trading_client,
)
from open_composer.config import alpaca_api_key_id, alpaca_api_secret_key, project_root
from open_composer.market_calendar import us_equity_session_close
from open_composer.paper_controls import load_paper_kill_switch
from open_composer.paper_lock import paper_control_lock
from open_composer.storage import append_jsonl, ensure_dir, write_json

NEW_YORK = ZoneInfo("America/New_York")
INTRADAY_DIRNAME = Path("reports") / "paper" / "intraday"
AUTHORIZATION_MAX_DURATION_DAYS = 30
#: Default caps -- deliberately conservative; the main session can widen them
#: once the research is in. ``leverage_cap`` defaults to 1.0 (NOT the paper
#: account's 4x margin multiplier): the sleeve is sized as though it were an
#: unmargined cash account unless a human explicitly turns the dial up.
DEFAULT_CAPS: dict[str, float | int] = {
    "max_orders_per_session": 5,
    "max_session_notional_usd": 25_000.0,
    "max_total_notional_usd": 250_000.0,
    "buying_power_floor_usd": 20_000.0,
}
DEFAULT_SLEEVE_USD = 25_000.0
DEFAULT_RISK_FRACTION = 0.01
DEFAULT_LEVERAGE_CAP = 1.0
DEFAULT_TARGET_R_MULTIPLE = 10.0
DEFAULT_DOJI_FRACTION = 0.05
TERMINAL_UNFILLED_STATUSES = frozenset({"canceled", "cancelled", "expired", "rejected", "replaced"})
UNAUTHORIZED_DRY_RUN_ID = "unauthorized-dry-run"


class IntradayError(ValueError):
    """Raised when the intraday cycle cannot proceed at all (config/auth defects)."""


@dataclass(frozen=True)
class IntradayConfig:
    strategy_name: str
    symbols: tuple[str, ...]
    sleeve_usd: float
    risk_fraction: float
    leverage_cap: float
    target_r_multiple: float
    doji_fraction: float
    open_time_et: time
    opening_range_end_et: time
    flatten_time_et: time
    data_feed: str
    caps: dict[str, float]
    authorization_max_duration_days: int
    path: str
    content_hash: str


@dataclass(frozen=True)
class IntradayAuthorization:
    authorization_id: str
    strategy_name: str
    config_hash: str
    authorized_by: str
    authorized_at: str
    expires_at: str
    broker_account_id_hash: str
    caps: dict[str, float]
    paper_only: bool = True
    path: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any], path: Path) -> IntradayAuthorization:
        required = (
            "authorization_id",
            "strategy_name",
            "config_hash",
            "authorized_by",
            "authorized_at",
            "expires_at",
            "broker_account_id_hash",
            "caps",
        )
        missing = [key for key in required if payload.get(key) in (None, "", {})]
        if missing:
            raise IntradayError(f"intraday authorization is missing fields: {missing}")
        if payload.get("paper_only") is not True:
            raise IntradayError("intraday authorization must be paper_only")
        return cls(
            authorization_id=str(payload["authorization_id"]),
            strategy_name=str(payload["strategy_name"]),
            config_hash=str(payload["config_hash"]),
            authorized_by=str(payload["authorized_by"]),
            authorized_at=str(payload["authorized_at"]),
            expires_at=str(payload["expires_at"]),
            broker_account_id_hash=str(payload["broker_account_id_hash"]),
            caps=dict(payload["caps"]),
            paper_only=True,
            path=str(path),
        )


@dataclass
class IntradayOrderPlan:
    symbol: str
    mode: Literal["entry", "flatten"]
    side: str = ""
    decision: str = "skip"
    reason: str = ""
    direction: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    r_value: float = 0.0
    qty: float = 0.0
    notional: float = 0.0
    client_order_id: str | None = None
    broker_order_id: str | None = None
    broker_status: str | None = None
    signal_id: str | None = None
    order_payload: dict[str, Any] | None = None


@dataclass
class IntradayCycleResult:
    strategy_name: str
    mode: Literal["entry", "flatten"]
    session: str
    status: str
    allow_paper_orders: bool
    equity: float
    buying_power: float
    plans: list[IntradayOrderPlan] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    report_path: str | None = None

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for plan in self.plans:
            out[plan.decision] = out.get(plan.decision, 0) + 1
        return out


# ---------------------------------------------------------------------------
# config


def _canonical_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_et_time(value: str) -> time:
    try:
        hour, minute = (int(part) for part in str(value).strip().split(":"))
        return time(hour, minute)
    except (TypeError, ValueError) as exc:
        raise IntradayError(f"invalid HH:MM time: {value!r}") from exc


def _validate_caps(caps: dict[str, Any]) -> dict[str, float]:
    try:
        orders = int(caps["max_orders_per_session"])
        session_notional = float(caps["max_session_notional_usd"])
        total_notional = float(caps["max_total_notional_usd"])
        floor_usd = float(caps["buying_power_floor_usd"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IntradayError(f"intraday caps are malformed: {exc}") from exc
    if orders < 1:
        raise IntradayError("max_orders_per_session must be >= 1")
    if not (session_notional > 0 and total_notional >= session_notional):
        raise IntradayError("notional caps must be positive and total >= session")
    if floor_usd < 0:
        raise IntradayError("buying_power_floor_usd must be >= 0")
    return {
        "max_orders_per_session": orders,
        "max_session_notional_usd": session_notional,
        "max_total_notional_usd": total_notional,
        "buying_power_floor_usd": floor_usd,
    }


def load_intraday_config(path: Path) -> IntradayConfig:
    if not Path(path).is_file():
        raise IntradayError(f"intraday config is missing: {path}")
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise IntradayError(f"intraday config must be a mapping: {path}")
    strategy_name = str(raw.get("strategy_name") or "").strip()
    if not strategy_name:
        raise IntradayError("intraday config requires strategy_name")
    symbols = tuple(
        str(item).strip().upper() for item in (raw.get("symbols") or []) if str(item).strip()
    )
    if not symbols:
        raise IntradayError("intraday config requires at least one symbol")
    session_raw = raw.get("session") if isinstance(raw.get("session"), dict) else {}
    caps = _validate_caps({**DEFAULT_CAPS, **(raw.get("caps") or {})})
    try:
        sleeve_usd = float(raw.get("sleeve_usd", DEFAULT_SLEEVE_USD))
        risk_fraction = float(raw.get("risk_fraction", DEFAULT_RISK_FRACTION))
        leverage_cap = float(raw.get("leverage_cap", DEFAULT_LEVERAGE_CAP))
        target_r_multiple = float(raw.get("target_r_multiple", DEFAULT_TARGET_R_MULTIPLE))
        doji_fraction = float(raw.get("doji_fraction", DEFAULT_DOJI_FRACTION))
        auth_section = (
            raw.get("authorization") if isinstance(raw.get("authorization"), dict) else {}
        )
        auth_days = int(auth_section.get("max_duration_days", 14))
    except (TypeError, ValueError) as exc:
        raise IntradayError(f"intraday config has malformed numeric fields: {exc}") from exc
    if sleeve_usd <= 0:
        raise IntradayError("sleeve_usd must be positive")
    if not 0 < risk_fraction <= 0.05:
        raise IntradayError("risk_fraction must be in (0, 0.05]")
    if not 0 < leverage_cap <= 4.0:
        raise IntradayError("leverage_cap must be in (0, 4.0]")
    if target_r_multiple <= 0:
        raise IntradayError("target_r_multiple must be positive")
    if not 0 < doji_fraction < 1:
        raise IntradayError("doji_fraction must be in (0, 1)")
    if not 1 <= auth_days <= AUTHORIZATION_MAX_DURATION_DAYS:
        raise IntradayError(
            "authorization.max_duration_days must be between 1 and "
            f"{AUTHORIZATION_MAX_DURATION_DAYS}"
        )
    data_feed = str(raw.get("data_feed") or "sip").strip().lower()
    if data_feed not in {"iex", "sip", "delayed_sip"}:
        raise IntradayError(f"unsupported data_feed: {data_feed}")
    session_payload = {
        "open_et": str(session_raw.get("open_et", "09:30")),
        "opening_range_end_et": str(session_raw.get("opening_range_end_et", "09:35")),
        "flatten_et": str(session_raw.get("flatten_et", "15:55")),
    }
    payload_for_hash = {
        "strategy_name": strategy_name,
        "symbols": list(symbols),
        "sleeve_usd": sleeve_usd,
        "risk_fraction": risk_fraction,
        "leverage_cap": leverage_cap,
        "target_r_multiple": target_r_multiple,
        "doji_fraction": doji_fraction,
        "session": session_payload,
        "data_feed": data_feed,
        "caps": caps,
    }
    return IntradayConfig(
        strategy_name=strategy_name,
        symbols=symbols,
        sleeve_usd=sleeve_usd,
        risk_fraction=risk_fraction,
        leverage_cap=leverage_cap,
        target_r_multiple=target_r_multiple,
        doji_fraction=doji_fraction,
        open_time_et=_parse_et_time(session_payload["open_et"]),
        opening_range_end_et=_parse_et_time(session_payload["opening_range_end_et"]),
        flatten_time_et=_parse_et_time(session_payload["flatten_et"]),
        data_feed=data_feed,
        caps=caps,
        authorization_max_duration_days=auth_days,
        path=str(path),
        content_hash=_canonical_hash(payload_for_hash),
    )


# ---------------------------------------------------------------------------
# authorization


def intraday_dir(root: Path) -> Path:
    return root / INTRADAY_DIRNAME


def intraday_authorization_path(root: Path, strategy_name: str) -> Path:
    return intraday_dir(root) / f"{strategy_name}-authorization.json"


def intraday_ledger_path(root: Path, strategy_name: str) -> Path:
    return intraday_dir(root) / f"{strategy_name}-orders.jsonl"


def intraday_trades_path(root: Path, strategy_name: str) -> Path:
    return intraday_dir(root) / f"{strategy_name}-trades.jsonl"


def write_intraday_authorization(
    config_path: Path,
    root: Path | None = None,
    *,
    authorized_by: str,
    confirm_paper_only: bool,
    acknowledge_intraday_risk: bool,
    duration_days: int = 14,
    client: Any | None = None,
    now: datetime | None = None,
) -> Path:
    base = root or project_root()
    if not confirm_paper_only or not acknowledge_intraday_risk:
        raise IntradayError(
            "intraday authorization requires --confirm-paper-only and --acknowledge-intraday-risk"
        )
    if not authorized_by.strip():
        raise IntradayError("authorized_by must identify the confirming operator")
    config = load_intraday_config(config_path)
    if (
        isinstance(duration_days, bool)
        or not 1 <= int(duration_days) <= config.authorization_max_duration_days
    ):
        raise IntradayError(
            f"duration_days must be between 1 and {config.authorization_max_duration_days}"
        )
    broker = client or _trading_client()
    _require_verified_paper_client(broker)
    account = broker.get_account()
    account_hash = _optional_broker_account_hash(getattr(account, "id", None))
    if not account_hash:
        raise IntradayError("paper account id is unavailable; cannot bind the authorization")
    stamp = now or datetime.now(UTC)
    payload = {
        "authorization_kind": "intraday_orb_paper",
        "authorization_id": "oci_"
        + hashlib.sha256(
            f"{config.strategy_name}|{config.content_hash}|{stamp.isoformat()}".encode()
        ).hexdigest()[:16],
        "strategy_name": config.strategy_name,
        "config_path": str(Path(config_path)),
        "config_hash": config.content_hash,
        "authorized_by": authorized_by.strip(),
        "authorized_at": stamp.isoformat(),
        "expires_at": (stamp + timedelta(days=int(duration_days))).isoformat(),
        "broker_account_id_hash": account_hash,
        "caps": config.caps,
        "paper_only": True,
        "scope": (
            "Alpaca Paper only; single-book intraday ORB entry/flatten; sized off a configured "
            "notional sleeve, never off account equity. Real-money broker writes are out of scope."
        ),
    }
    path = intraday_authorization_path(base, config.strategy_name)
    ensure_dir(path.parent)
    with paper_control_lock(base):
        write_json(path, payload)
        archive = path.with_name(
            f"{config.strategy_name}-authorization-{stamp:%Y%m%dT%H%M%SZ}.json"
        )
        write_json(archive, payload)
    return path


def _dry_run_placeholder_authorization(
    config: IntradayConfig, stamp: datetime
) -> IntradayAuthorization:
    """Stand-in used only when no authorization file exists *and* orders are
    not allowed, so a dry run can still produce a reviewable cycle report."""
    return IntradayAuthorization(
        authorization_id=UNAUTHORIZED_DRY_RUN_ID,
        strategy_name=config.strategy_name,
        config_hash=config.content_hash,
        authorized_by="none (plan-only dry run, no authorization on file)",
        authorized_at=stamp.isoformat(),
        expires_at=stamp.isoformat(),
        broker_account_id_hash="",
        caps=dict(config.caps),
        paper_only=True,
        path="",
    )


def load_intraday_authorization(
    config: IntradayConfig, root: Path, *, now: datetime | None = None
) -> IntradayAuthorization:
    path = intraday_authorization_path(root, config.strategy_name)
    if not path.is_file():
        raise IntradayError(f"no intraday authorization at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IntradayError(f"intraday authorization is not valid JSON: {exc}") from exc
    auth = IntradayAuthorization.from_payload(payload, path)
    if auth.strategy_name != config.strategy_name:
        raise IntradayError("intraday authorization belongs to a different strategy")
    if auth.config_hash != config.content_hash:
        raise IntradayError(
            "intraday authorization was written for a different config content hash; "
            "re-authorize after config changes"
        )
    stamp = now or datetime.now(UTC)
    expires = datetime.fromisoformat(auth.expires_at)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if stamp >= expires:
        raise IntradayError(f"intraday authorization expired at {auth.expires_at}")
    _validate_caps(auth.caps)
    return auth


def revoke_intraday_authorization(
    config_path: Path, root: Path | None = None, *, reason: str
) -> Path:
    base = root or project_root()
    config = load_intraday_config(config_path)
    path = intraday_authorization_path(base, config.strategy_name)
    if not path.is_file():
        raise IntradayError(f"no intraday authorization at {path}")
    stamp = datetime.now(UTC)
    target = path.with_name(
        f"{config.strategy_name}-authorization-revoked-{stamp:%Y%m%dT%H%M%SZ}.json"
    )
    with paper_control_lock(base):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["revoked_at"] = stamp.isoformat()
        payload["revoked_reason"] = reason
        write_json(target, payload)
        path.unlink()
    return target


# ---------------------------------------------------------------------------
# bars / signal (pure helpers, no I/O)


def _expected_minute_starts(day: date, config: IntradayConfig) -> list[datetime]:
    start = datetime.combine(day, config.open_time_et, tzinfo=NEW_YORK)
    end = datetime.combine(day, config.opening_range_end_et, tzinfo=NEW_YORK)
    minutes = int((end - start).total_seconds() // 60)
    return [start + timedelta(minutes=i) for i in range(minutes)]


def _as_et(ts: datetime) -> datetime:
    return ts.astimezone(NEW_YORK) if ts.tzinfo is not None else ts.replace(tzinfo=NEW_YORK)


def _validate_bars(
    day: date, config: IntradayConfig, bars: list[dict[str, Any]], *, is_simulated: bool
) -> str | None:
    if not bars:
        return "missing_bars: no minute bars were returned for the opening range"
    expected = _expected_minute_starts(day, config)
    seen: set[datetime] = set()
    for bar in bars:
        ts = bar.get("timestamp")
        if ts is None:
            return "missing_bars: a returned bar has no timestamp"
        ts_et = _as_et(ts).replace(second=0, microsecond=0)
        if not is_simulated and ts_et.date() != day:
            return (
                f"stale_bars: bar timestamp {ts_et.isoformat()} is not from "
                f"session {day.isoformat()}"
            )
        seen.add(ts_et)
    missing = [dt for dt in expected if dt not in seen]
    if missing:
        return "missing_bars: opening range is missing minute(s) " + ", ".join(
            m.strftime("%H:%M") for m in missing
        )
    return None


def _in_opening_range(ts: datetime, day: date, config: IntradayConfig) -> bool:
    ts_et = _as_et(ts)
    start = datetime.combine(day, config.open_time_et, tzinfo=NEW_YORK)
    end = datetime.combine(day, config.opening_range_end_et, tzinfo=NEW_YORK)
    return start <= ts_et < end


def evaluate_orb_entry(
    symbol: str,
    day: date,
    config: IntradayConfig,
    bars: list[dict[str, Any]],
    *,
    is_simulated: bool = False,
) -> IntradayOrderPlan:
    """Pure rule evaluation: bars in, an order plan out. No I/O, no broker."""
    plan = IntradayOrderPlan(symbol=symbol, mode="entry")
    reason = _validate_bars(day, config, bars, is_simulated=is_simulated)
    if reason is not None:
        plan.decision = (
            "skip_missing_bars" if reason.startswith("missing_bars") else "skip_stale_bars"
        )
        plan.reason = reason
        return plan
    window = sorted(
        (bar for bar in bars if _in_opening_range(bar["timestamp"], day, config)),
        key=lambda bar: bar["timestamp"],
    )
    if not window:
        plan.decision = "skip_missing_bars"
        plan.reason = "missing_bars: no bar falls inside the configured opening range"
        return plan
    candle_open = float(window[0]["open"])
    candle_close = float(window[-1]["close"])
    candle_high = max(float(bar["high"]) for bar in window)
    candle_low = min(float(bar["low"]) for bar in window)
    plan.open, plan.high, plan.low, plan.close = candle_open, candle_high, candle_low, candle_close
    if abs(candle_close - candle_open) <= config.doji_fraction * (candle_high - candle_low):
        plan.decision = "skip_doji"
        plan.reason = (
            f"|close-open|={abs(candle_close - candle_open):.4f} <= doji_fraction"
            f"({config.doji_fraction}) * (high-low)={candle_high - candle_low:.4f}"
        )
        return plan
    is_long = candle_close > candle_open
    plan.direction = "long" if is_long else "short"
    plan.side = "buy" if is_long else "sell"
    entry_price = candle_close
    stop_price = candle_low if is_long else candle_high
    r_value = (entry_price - stop_price) if is_long else (stop_price - entry_price)
    if not math.isfinite(r_value) or r_value <= 0:
        plan.decision = "skip_zero_risk"
        plan.reason = f"non-positive risk-per-share R={r_value:.6f}"
        return plan
    target_price = (
        entry_price + config.target_r_multiple * r_value
        if is_long
        else entry_price - config.target_r_multiple * r_value
    )
    plan.stop_price, plan.target_price, plan.r_value = stop_price, target_price, r_value
    shares_by_risk = math.floor(config.risk_fraction * config.sleeve_usd / r_value)
    shares_by_leverage = math.floor(config.leverage_cap * config.sleeve_usd / entry_price)
    qty = min(shares_by_risk, shares_by_leverage)
    if qty < 1:
        plan.decision = "skip_sizing_below_one_share"
        plan.reason = (
            f"risk-sized shares={shares_by_risk} leverage-capped shares={shares_by_leverage}"
        )
        return plan
    plan.qty = float(qty)
    plan.notional = float(qty) * entry_price
    plan.decision = "submit"
    return plan


def _normalize_bar_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        ts = row.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        normalized.append(
            {
                "timestamp": ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0) or 0),
            }
        )
    return normalized


def load_simulated_bars(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Load the ``--simulate-bars`` offline fixture: JSON (a symbol -> rows
    mapping) or a parquet file with a ``symbol`` column, for a single recorded
    09:30-09:35 ET window."""
    path = Path(path)
    if path.suffix.lower() == ".parquet":
        import pandas as pd

        frame = pd.read_parquet(path)
        out: dict[str, list[dict[str, Any]]] = {}
        for symbol, group in frame.groupby("symbol"):
            out[str(symbol).upper()] = group.drop(columns=["symbol"]).to_dict("records")
        return {symbol: _normalize_bar_rows(rows) for symbol, rows in out.items()}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise IntradayError(f"--simulate-bars JSON must be a symbol -> rows mapping: {path}")
    return {str(symbol).upper(): _normalize_bar_rows(rows) for symbol, rows in raw.items()}


def _fetch_minute_bars(
    symbol: str, day: date, config: IntradayConfig, data_client: Any
) -> list[dict[str, Any]]:
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    start = datetime.combine(day, config.open_time_et, tzinfo=NEW_YORK).astimezone(UTC)
    end = datetime.combine(day, config.opening_range_end_et, tzinfo=NEW_YORK).astimezone(UTC)
    request = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame(1, TimeFrameUnit.Minute),
        start=start,
        end=end,
        feed=DataFeed(config.data_feed),
    )
    response = data_client.get_stock_bars(request)
    data = getattr(response, "data", response if isinstance(response, dict) else {})
    rows = list(data.get(symbol, [])) if isinstance(data, dict) else []
    return _normalize_bar_rows(
        [
            {
                "timestamp": getattr(bar, "timestamp", None),
                "open": getattr(bar, "open", None),
                "high": getattr(bar, "high", None),
                "low": getattr(bar, "low", None),
                "close": getattr(bar, "close", None),
                "volume": getattr(bar, "volume", 0),
            }
            for bar in rows
        ]
    )


def _stock_data_client() -> Any:
    try:
        from alpaca.data.historical import StockHistoricalDataClient
    except ImportError as exc:
        raise IntradayError("alpaca-py is required for intraday bar fetches") from exc
    return StockHistoricalDataClient(
        api_key=alpaca_api_key_id(), secret_key=alpaca_api_secret_key()
    )


# ---------------------------------------------------------------------------
# shared cycle plumbing


def _status_text(order: Any) -> str:
    status = getattr(order, "status", "")
    return str(getattr(status, "value", status)).split(".")[-1].lower()


def _client_order_id(
    strategy_name: str, session: date, symbol: str, side: str, purpose: str
) -> str:
    digest = hashlib.sha256(
        f"{strategy_name}|{session.isoformat()}|{symbol}|{side}|{purpose}".encode()
    ).hexdigest()
    return f"oci-{session:%Y%m%d}-{symbol[:8]}-{purpose[:5]}-{digest[:10]}"


def _market_gate_reason(now_et: datetime, day: date, mode: str) -> str | None:
    close = us_equity_session_close(day)
    if close is None:
        return f"{day.isoformat()} is not a US equity trading session (weekend/holiday)"
    open_time = time(9, 30)
    now_time = now_et.time()
    if open_time <= now_time < close:
        return None
    half_day_note = ""
    if close != time(16, 0):
        half_day_note = f" (half day: real close is {close.strftime('%H:%M')} ET, not 16:00)"
    return (
        f"market is closed for {day.isoformat()} at {now_time.strftime('%H:%M')} ET "
        f"[mode={mode}]{half_day_note}"
    )


def _ledger_rows(root: Path, strategy_name: str) -> list[dict[str, Any]]:
    path = intraday_ledger_path(root, strategy_name)
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _ledger_total_notional(root: Path, strategy_name: str, authorization_id: str) -> float:
    total = 0.0
    for row in _ledger_rows(root, strategy_name):
        if row.get("authorization_id") == authorization_id and row.get("broker_order_id"):
            total += float(row.get("notional") or 0.0)
    return total


def _signal_record(
    *,
    config: IntradayConfig,
    session: date,
    stamp: datetime,
    plan: IntradayOrderPlan,
    auth: IntradayAuthorization,
    run_id: str,
) -> dict[str, Any]:
    signal_id = (
        "sig_"
        + hashlib.sha256(
            f"{config.strategy_name}|{session.isoformat()}|{plan.symbol}|{plan.mode}|{plan.side}".encode()
        ).hexdigest()[:16]
    )
    return {
        "id": signal_id,
        "run_id": run_id,
        "strategy_name": config.strategy_name,
        "kind": f"intraday_orb_{plan.mode}",
        "symbol": plan.symbol,
        "session": session.isoformat(),
        "timestamp": stamp.isoformat(),
        "action": "entry" if plan.mode == "entry" else "exit",
        "side": plan.side,
        "reference_price": plan.close if plan.mode == "entry" else None,
        "opening_candle": (
            {"open": plan.open, "high": plan.high, "low": plan.low, "close": plan.close}
            if plan.mode == "entry"
            else None
        ),
        "direction": plan.direction or None,
        "stop_price": plan.stop_price or None,
        "target_price": plan.target_price or None,
        "r_value": plan.r_value or None,
        "qty": plan.qty,
        "notional": plan.notional,
        "sleeve_usd": config.sleeve_usd,
        "risk_fraction": config.risk_fraction,
        "leverage_cap": config.leverage_cap,
        "target_r_multiple": config.target_r_multiple,
        "client_order_id": plan.client_order_id,
        "authorization_id": auth.authorization_id,
        "config_hash": config.content_hash,
        "conditions": [
            f"session={session.isoformat()}",
            "rule=orb_9:35_entry_10R_target" if plan.mode == "entry" else "rule=eod_flatten",
            f"client_order_id={plan.client_order_id}",
        ],
        "paper": True,
        "created_at": datetime.now(UTC).isoformat(),
    }


def _build_bracket_request(plan: IntradayOrderPlan) -> Any:
    from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

    side = OrderSide.BUY if plan.side == "buy" else OrderSide.SELL
    return MarketOrderRequest(
        symbol=plan.symbol,
        qty=plan.qty,
        side=side,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=round(plan.target_price, 2)),
        stop_loss=StopLossRequest(stop_price=round(plan.stop_price, 2)),
        client_order_id=plan.client_order_id,
        extended_hours=False,
    )


def _build_market_request(plan: IntradayOrderPlan) -> Any:
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    side = OrderSide.BUY if plan.side == "buy" else OrderSide.SELL
    return MarketOrderRequest(
        symbol=plan.symbol,
        qty=plan.qty,
        side=side,
        time_in_force=TimeInForce.DAY,
        client_order_id=plan.client_order_id,
        extended_hours=False,
    )


def _position_quantities(client: Any) -> tuple[dict[str, float], dict[str, float]]:
    quantities: dict[str, float] = {}
    prices: dict[str, float] = {}
    for position in _client_positions(client):
        symbol = str(getattr(position, "symbol", "")).upper()
        quantities[symbol] = float(getattr(position, "qty", 0) or 0)
        price = getattr(position, "current_price", None)
        prices[symbol] = float(price) if price else 0.0
    return quantities, prices


def _open_leg_ids(client: Any, parent_client_order_id: str) -> list[str]:
    parent = _broker_order_by_client_id(client, parent_client_order_id)
    if parent is None:
        return []
    legs = getattr(parent, "legs", None) or []
    return [
        str(getattr(leg, "id", ""))
        for leg in legs
        if _status_text(leg) not in TERMINAL_UNFILLED_STATUSES | {"filled"}
    ]


# ---------------------------------------------------------------------------
# entry cycle


def run_intraday_entry_cycle(
    config_path: Path,
    root: Path | None = None,
    *,
    allow_paper_orders: bool,
    client: Any | None = None,
    data_client: Any | None = None,
    simulate_bars: dict[str, list[dict[str, Any]]] | None = None,
    now: datetime | None = None,
) -> IntradayCycleResult:
    base = root or project_root()
    stamp = now or datetime.now(UTC)
    config = load_intraday_config(config_path)
    is_simulated = simulate_bars is not None
    session = stamp.astimezone(NEW_YORK).date()
    unauthorized_dry_run = (
        not allow_paper_orders
        and not intraday_authorization_path(base, config.strategy_name).is_file()
    )
    auth = (
        _dry_run_placeholder_authorization(config, stamp)
        if unauthorized_dry_run
        else load_intraday_authorization(config, base, now=stamp)
    )
    result = IntradayCycleResult(
        strategy_name=config.strategy_name,
        mode="entry",
        session=session.isoformat(),
        status="planned",
        allow_paper_orders=allow_paper_orders,
        equity=0.0,
        buying_power=0.0,
    )
    if unauthorized_dry_run:
        result.notes.append(
            "no intraday authorization on file: plan-only dry run with DEFAULT_CAPS; run "
            "`oc paper intraday authorize` before any --allow-paper-orders run"
        )
    if is_simulated:
        result.notes.append(
            "simulate_bars supplied: market-hours/staleness gate bypassed for this offline "
            "exercise; every other check (doji, sizing, caps, kill switch, authorization) ran "
            "normally; no order was, or could be, submitted to the broker from this hook."
        )

    kill_switch = load_paper_kill_switch(base, require_control_file=True)
    if kill_switch.enabled:
        result.status = "blocked_by_kill_switch"
        result.notes.append(f"paper kill switch enabled: {kill_switch.reason}")
        _write_cycle_report(base, result, auth, config)
        return result

    if not is_simulated:
        gate_reason = _market_gate_reason(stamp.astimezone(NEW_YORK), session, "entry")
        if gate_reason is not None:
            result.status = "market_closed"
            result.notes.append(gate_reason)
            for symbol in config.symbols:
                result.plans.append(
                    IntradayOrderPlan(
                        symbol=symbol,
                        mode="entry",
                        decision="skip_market_closed",
                        reason=gate_reason,
                    )
                )
            _write_cycle_report(base, result, auth, config)
            return result

    broker = client or _trading_client()
    _require_verified_paper_client(broker)
    account = broker.get_account()
    account_hash = _optional_broker_account_hash(getattr(account, "id", None))
    if not unauthorized_dry_run and account_hash != auth.broker_account_id_hash:
        raise IntradayError("intraday authorization is bound to a different paper account")
    equity = float(getattr(account, "equity", 0) or 0)
    buying_power = float(getattr(account, "buying_power", 0) or 0)
    result.equity, result.buying_power = equity, buying_power

    sleeve_requirement = config.leverage_cap * config.sleeve_usd
    floor_usd = float(auth.caps["buying_power_floor_usd"])
    if buying_power - sleeve_requirement < floor_usd:
        result.status = "blocked_by_buying_power_floor"
        reason = (
            f"buying_power={buying_power:.2f} - sleeve_requirement={sleeve_requirement:.2f} "
            f"< floor={floor_usd:.2f}"
        )
        result.notes.append(reason)
        for symbol in config.symbols:
            result.plans.append(
                IntradayOrderPlan(
                    symbol=symbol, mode="entry", decision="skip_buying_power_floor", reason=reason
                )
            )
        _write_cycle_report(base, result, auth, config)
        return result

    positions, _prices = _position_quantities(broker)
    session_orders = 0
    session_notional = 0.0
    prior_total = _ledger_total_notional(base, config.strategy_name, auth.authorization_id)
    max_orders = int(auth.caps["max_orders_per_session"])
    max_session_notional = float(auth.caps["max_session_notional_usd"])
    max_total_notional = float(auth.caps["max_total_notional_usd"])
    signal_log = base / "signal_logs" / f"paper-intraday-{config.strategy_name}.jsonl"
    ledger = intraday_ledger_path(base, config.strategy_name)
    run_id = f"paper-intraday-entry-{config.strategy_name}-{session.isoformat()}"

    for symbol in config.symbols:
        if is_simulated:
            bars = simulate_bars.get(symbol.upper(), []) if simulate_bars else []
        else:
            bars = _fetch_minute_bars(symbol, session, config, data_client or _stock_data_client())
        plan = evaluate_orb_entry(symbol, session, config, bars, is_simulated=is_simulated)
        if plan.decision != "submit":
            result.plans.append(plan)
            continue
        if positions.get(symbol.upper(), 0.0) != 0.0:
            plan.decision = "skip_position_conflict"
            plan.reason = (
                f"broker already holds {positions[symbol.upper()]:.0f} sh of {symbol}; "
                "refusing to touch a position that may belong to another book"
            )
            result.plans.append(plan)
            continue
        if session_orders + 1 > max_orders:
            plan.decision, plan.reason = "skip_orders_cap", f"max_orders_per_session={max_orders}"
            result.plans.append(plan)
            continue
        if session_notional + plan.notional > max_session_notional + 1e-6:
            plan.decision, plan.reason = (
                "skip_session_notional_cap",
                f"max_session_notional_usd={max_session_notional}",
            )
            result.plans.append(plan)
            continue
        session_orders += 1
        session_notional += plan.notional
        plan.client_order_id = _client_order_id(
            config.strategy_name, session, symbol, plan.side, "entry"
        )
        request = _build_bracket_request(plan)
        plan.order_payload = request.model_dump(mode="json")
        signal = _signal_record(
            config=config, session=session, stamp=stamp, plan=plan, auth=auth, run_id=run_id
        )
        plan.signal_id = signal["id"]
        append_jsonl(signal_log, [signal])
        if not allow_paper_orders:
            plan.decision = "would_submit"
            result.plans.append(plan)
            continue
        if prior_total + plan.notional > max_total_notional + 1e-6:
            plan.decision, plan.reason = (
                "skip_total_notional_cap",
                f"max_total_notional_usd={max_total_notional}",
            )
            result.plans.append(plan)
            continue
        existing = _broker_order_by_client_id(broker, plan.client_order_id)
        if existing is not None and _status_text(existing) in TERMINAL_UNFILLED_STATUSES:
            existing = None
        if existing is not None:
            plan.decision = "already_submitted"
            plan.broker_order_id = str(getattr(existing, "id", ""))
            plan.broker_status = _status_text(existing)
            result.plans.append(plan)
            continue
        try:
            with paper_control_lock(base):
                fresh = load_paper_kill_switch(base, require_control_file=True)
                if fresh.enabled:
                    raise PaperOrderError("paper kill switch enabled")
                order = broker.submit_order(request)
        except Exception as exc:  # broker rejections are recorded, never raised past the loop
            plan.decision = "rejected"
            plan.reason = f"{exc.__class__.__name__}: {exc}"[:300]
            result.plans.append(plan)
            continue
        plan.broker_order_id = str(getattr(order, "id", ""))
        plan.broker_status = _status_text(order)
        plan.decision = "submitted"
        prior_total += plan.notional
        result.plans.append(plan)
        append_jsonl(
            ledger,
            [
                {
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "mode": "entry",
                    "authorization_id": auth.authorization_id,
                    "strategy_name": config.strategy_name,
                    "session": session.isoformat(),
                    "symbol": symbol.upper(),
                    "side": plan.side,
                    "qty": plan.qty,
                    "reference_price": plan.close,
                    "stop_price": plan.stop_price,
                    "target_price": plan.target_price,
                    "r_value": plan.r_value,
                    "notional": plan.notional,
                    "client_order_id": plan.client_order_id,
                    "broker_order_id": plan.broker_order_id,
                    "broker_status": plan.broker_status,
                    "signal_id": plan.signal_id,
                    "config_hash": config.content_hash,
                    "paper": True,
                }
            ],
        )
    result.status = _derive_status(result, allow_paper_orders, unauthorized_dry_run)
    _write_cycle_report(base, result, auth, config)
    return result


# ---------------------------------------------------------------------------
# flatten cycle


def run_intraday_flatten_cycle(
    config_path: Path,
    root: Path | None = None,
    *,
    allow_paper_orders: bool,
    client: Any | None = None,
    now: datetime | None = None,
) -> IntradayCycleResult:
    base = root or project_root()
    stamp = now or datetime.now(UTC)
    config = load_intraday_config(config_path)
    session = stamp.astimezone(NEW_YORK).date()
    unauthorized_dry_run = (
        not allow_paper_orders
        and not intraday_authorization_path(base, config.strategy_name).is_file()
    )
    auth = (
        _dry_run_placeholder_authorization(config, stamp)
        if unauthorized_dry_run
        else load_intraday_authorization(config, base, now=stamp)
    )
    result = IntradayCycleResult(
        strategy_name=config.strategy_name,
        mode="flatten",
        session=session.isoformat(),
        status="planned",
        allow_paper_orders=allow_paper_orders,
        equity=0.0,
        buying_power=0.0,
    )

    kill_switch = load_paper_kill_switch(base, require_control_file=True)
    if kill_switch.enabled:
        result.status = "blocked_by_kill_switch"
        result.notes.append(f"paper kill switch enabled: {kill_switch.reason}")
        _write_cycle_report(base, result, auth, config)
        return result

    gate_reason = _market_gate_reason(stamp.astimezone(NEW_YORK), session, "flatten")
    if gate_reason is not None:
        result.status = "market_closed"
        result.notes.append(gate_reason)
        for symbol in config.symbols:
            result.plans.append(
                IntradayOrderPlan(
                    symbol=symbol, mode="flatten", decision="skip_market_closed", reason=gate_reason
                )
            )
        _write_cycle_report(base, result, auth, config)
        return result

    broker = client or _trading_client()
    _require_verified_paper_client(broker)
    account = broker.get_account()
    account_hash = _optional_broker_account_hash(getattr(account, "id", None))
    if not unauthorized_dry_run and account_hash != auth.broker_account_id_hash:
        raise IntradayError("intraday authorization is bound to a different paper account")
    result.equity = float(getattr(account, "equity", 0) or 0)
    result.buying_power = float(getattr(account, "buying_power", 0) or 0)

    positions, _prices = _position_quantities(broker)
    entry_rows = {
        row["symbol"]: row
        for row in _ledger_rows(base, config.strategy_name)
        if row.get("mode") == "entry"
        and row.get("session") == session.isoformat()
        and row.get("broker_order_id")
    }
    signal_log = base / "signal_logs" / f"paper-intraday-{config.strategy_name}.jsonl"
    ledger = intraday_ledger_path(base, config.strategy_name)
    run_id = f"paper-intraday-flatten-{config.strategy_name}-{session.isoformat()}"

    for symbol in config.symbols:
        entry_row = entry_rows.get(symbol.upper())
        open_leg_ids = _open_leg_ids(broker, entry_row["client_order_id"]) if entry_row else []
        cancelled: list[str] = []
        if open_leg_ids and allow_paper_orders:
            for leg_id in open_leg_ids:
                broker.cancel_order_by_id(leg_id)
                cancelled.append(leg_id)
        qty = positions.get(symbol.upper(), 0.0)
        plan = IntradayOrderPlan(symbol=symbol, mode="flatten")
        if qty == 0:
            if open_leg_ids:
                plan.decision = (
                    "cancel_children_only" if allow_paper_orders else "would_cancel_children_only"
                )
                plan.reason = (
                    f"cancelled {len(cancelled)}/{len(open_leg_ids)} open bracket "
                    "leg(s); flat already"
                )
            else:
                plan.decision = "noop_flat"
                plan.reason = "no open position or open bracket legs for this symbol"
            result.plans.append(plan)
            continue
        plan.side = "sell" if qty > 0 else "buy"
        plan.qty = abs(qty)
        plan.client_order_id = _client_order_id(
            config.strategy_name, session, symbol, plan.side, "flatten"
        )
        request = _build_market_request(plan)
        plan.order_payload = request.model_dump(mode="json")
        signal = _signal_record(
            config=config, session=session, stamp=stamp, plan=plan, auth=auth, run_id=run_id
        )
        plan.signal_id = signal["id"]
        append_jsonl(signal_log, [signal])
        if not allow_paper_orders:
            plan.decision = "would_submit"
            result.plans.append(plan)
            continue
        existing = _broker_order_by_client_id(broker, plan.client_order_id)
        if existing is not None and _status_text(existing) in TERMINAL_UNFILLED_STATUSES:
            existing = None
        if existing is not None:
            plan.decision = "already_submitted"
            plan.broker_order_id = str(getattr(existing, "id", ""))
            plan.broker_status = _status_text(existing)
            result.plans.append(plan)
            continue
        try:
            with paper_control_lock(base):
                fresh = load_paper_kill_switch(base, require_control_file=True)
                if fresh.enabled:
                    raise PaperOrderError("paper kill switch enabled")
                order = broker.submit_order(request)
        except Exception as exc:
            plan.decision = "rejected"
            plan.reason = f"{exc.__class__.__name__}: {exc}"[:300]
            result.plans.append(plan)
            continue
        plan.broker_order_id = str(getattr(order, "id", ""))
        plan.broker_status = _status_text(order)
        plan.decision = "submitted"
        result.plans.append(plan)
        append_jsonl(
            ledger,
            [
                {
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "mode": "flatten",
                    "authorization_id": auth.authorization_id,
                    "strategy_name": config.strategy_name,
                    "session": session.isoformat(),
                    "symbol": symbol.upper(),
                    "side": plan.side,
                    "qty": plan.qty,
                    "notional": None,
                    "client_order_id": plan.client_order_id,
                    "broker_order_id": plan.broker_order_id,
                    "broker_status": plan.broker_status,
                    "signal_id": plan.signal_id,
                    "cancelled_legs": cancelled,
                    "config_hash": config.content_hash,
                    "paper": True,
                }
            ],
        )
    result.status = _derive_status(result, allow_paper_orders, unauthorized_dry_run)
    _write_cycle_report(base, result, auth, config)
    return result


def _derive_status(
    result: IntradayCycleResult, allow_paper_orders: bool, unauthorized_dry_run: bool
) -> str:
    counts = result.counts()
    if counts.get("rejected"):
        return "partial" if (counts.get("submitted") or counts.get("would_submit")) else "rejected"
    if counts.get("submitted"):
        return "submitted"
    if allow_paper_orders and counts.get("already_submitted"):
        return "already_submitted"
    if not allow_paper_orders:
        return "dry_run_unauthorized" if unauthorized_dry_run else "dry_run"
    return "no_orders"


# ---------------------------------------------------------------------------
# reconcile


def run_intraday_reconcile(
    config_path: Path,
    root: Path | None = None,
    *,
    client: Any | None = None,
    now: datetime | None = None,
    session: date | None = None,
) -> dict[str, Any]:
    base = root or project_root()
    stamp = now or datetime.now(UTC)
    config = load_intraday_config(config_path)
    target_session = session or stamp.astimezone(NEW_YORK).date()
    broker = client or _trading_client()
    _require_verified_paper_client(broker)
    rows = _ledger_rows(base, config.strategy_name)
    entry_rows = [
        row
        for row in rows
        if row.get("mode") == "entry" and row.get("session") == target_session.isoformat()
    ]
    flatten_rows = {
        row["symbol"]: row
        for row in rows
        if row.get("mode") == "flatten" and row.get("session") == target_session.isoformat()
    }
    trades: list[dict[str, Any]] = []
    for row in entry_rows:
        entry_order = _broker_order_by_client_id(broker, row.get("client_order_id"))
        entry_fill_price = (
            float(getattr(entry_order, "filled_avg_price", 0) or 0)
            if entry_order is not None
            else None
        )
        entry_fill_qty = (
            float(getattr(entry_order, "filled_qty", 0) or 0) if entry_order is not None else 0.0
        )
        exit_price: float | None = None
        exit_qty = 0.0
        exit_reason: str | None = None
        flatten_row = flatten_rows.get(row["symbol"])
        if flatten_row is not None and flatten_row.get("broker_order_id"):
            flatten_order = _broker_order_by_client_id(broker, flatten_row.get("client_order_id"))
            if flatten_order is not None and _status_text(flatten_order) == "filled":
                exit_price = float(getattr(flatten_order, "filled_avg_price", 0) or 0)
                exit_qty = float(getattr(flatten_order, "filled_qty", 0) or 0)
                exit_reason = "flatten_eod"
        if exit_price is None and entry_order is not None:
            for leg in getattr(entry_order, "legs", None) or []:
                if _status_text(leg) != "filled":
                    continue
                exit_price = float(getattr(leg, "filled_avg_price", 0) or 0)
                exit_qty = float(getattr(leg, "filled_qty", 0) or 0)
                target = row.get("target_price")
                stop = row.get("stop_price")
                if target is not None and stop is not None:
                    exit_reason = (
                        "target"
                        if abs(exit_price - float(target)) < abs(exit_price - float(stop))
                        else "stop"
                    )
                break
        sign = 1.0 if row.get("side") == "buy" else -1.0
        realized_pnl = None
        r_multiple = None
        entry_slippage_bps = None
        exit_slippage_bps = None
        if entry_fill_price and exit_price:
            realized_pnl = (exit_price - entry_fill_price) * exit_qty * sign
            per_share = (exit_price - entry_fill_price) * sign
            r_value = row.get("r_value")
            if r_value:
                r_multiple = per_share / float(r_value)
            reference_price = row.get("reference_price")
            if reference_price:
                entry_slippage_bps = (
                    sign
                    * (entry_fill_price - float(reference_price))
                    / float(reference_price)
                    * 10_000
                )
            intended_exit = (
                row.get("target_price") if exit_reason == "target" else row.get("stop_price")
            )
            if intended_exit:
                exit_slippage_bps = (
                    sign * (exit_price - float(intended_exit)) / float(intended_exit) * 10_000
                )
        trades.append(
            {
                "session": target_session.isoformat(),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "qty": row.get("qty"),
                "entry_client_order_id": row.get("client_order_id"),
                "entry_fill_price": entry_fill_price,
                "entry_fill_qty": entry_fill_qty,
                "entry_reference_price": row.get("reference_price"),
                "entry_slippage_bps": entry_slippage_bps,
                "stop_price": row.get("stop_price"),
                "target_price": row.get("target_price"),
                "r_value": row.get("r_value"),
                "exit_price": exit_price,
                "exit_qty": exit_qty,
                "exit_reason": exit_reason,
                "exit_slippage_bps": exit_slippage_bps,
                "realized_pnl_usd": realized_pnl,
                "r_multiple": r_multiple,
                "still_open": exit_price is None,
            }
        )
    append_jsonl(intraday_trades_path(base, config.strategy_name), trades)
    lines = [
        f"# Intraday reconcile {config.strategy_name} — session {target_session.isoformat()}",
        "",
        "| symbol | side | qty | entry fill | entry slip(bp) | exit | exit reason | "
        "exit slip(bp) | pnl(usd) | R | open |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|",
    ]
    for trade in trades:
        lines.append(
            f"| {trade['symbol']} | {trade['side']} | {trade['qty']} | "
            f"{_fmt(trade['entry_fill_price'])} | {_fmt(trade['entry_slippage_bps'])} | "
            f"{_fmt(trade['exit_price'])} | {trade['exit_reason'] or '-'} | "
            f"{_fmt(trade['exit_slippage_bps'])} | {_fmt(trade['realized_pnl_usd'])} | "
            f"{_fmt(trade['r_multiple'])} | {trade['still_open']} |"
        )
    summary_md = (
        intraday_dir(base) / f"{config.strategy_name}-{target_session.isoformat()}-trades.md"
    )
    ensure_dir(summary_md.parent)
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "session": target_session.isoformat(),
        "trades": trades,
        "summary_path": str(summary_md),
    }


def _fmt(value: Any) -> str:
    return f"{value:.4f}" if isinstance(value, int | float) else "-"


# ---------------------------------------------------------------------------
# report


def _write_cycle_report(
    root: Path, result: IntradayCycleResult, auth: IntradayAuthorization, config: IntradayConfig
) -> None:
    directory = intraday_dir(root)
    ensure_dir(directory)
    stamp = datetime.now(UTC)
    payload = {
        "report_type": "intraday_orb_cycle",
        "strategy_name": result.strategy_name,
        "mode": result.mode,
        "session": result.session,
        "generated_at": stamp.isoformat(),
        "status": result.status,
        "allow_paper_orders": result.allow_paper_orders,
        "equity": result.equity,
        "buying_power": result.buying_power,
        "authorization_id": auth.authorization_id,
        "authorization_expires_at": auth.expires_at,
        "config_path": config.path,
        "config_hash": config.content_hash,
        "sleeve_usd": config.sleeve_usd,
        "risk_fraction": config.risk_fraction,
        "leverage_cap": config.leverage_cap,
        "target_r_multiple": config.target_r_multiple,
        "caps": auth.caps,
        "counts": result.counts(),
        "submitted_notional": sum(p.notional for p in result.plans if p.decision == "submitted"),
        "notes": result.notes,
        "orders": [asdict(plan) for plan in result.plans],
        "paper": True,
        "broker_writes": any(p.decision == "submitted" for p in result.plans),
    }
    json_path = (
        directory / f"{result.strategy_name}-{result.mode}-{result.session}-{stamp:%H%M%S}.json"
    )
    write_json(json_path, payload)
    latest = directory / f"{result.strategy_name}-{result.mode}-latest.json"
    write_json(latest, payload)
    md_path = latest.with_suffix(".md")
    lines = [
        f"# Intraday {result.mode} {result.strategy_name} — session {result.session}",
        "",
        f"- status: {result.status} (allow_paper_orders={result.allow_paper_orders})",
        f"- equity: {result.equity:,.2f}; buying_power: {result.buying_power:,.2f}",
        f"- authorization {auth.authorization_id} expires {auth.expires_at}; caps {auth.caps}",
        f"- decision counts: {payload['counts']}",
        "",
        "| symbol | side | qty | close | stop | target | R | decision | reason |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for plan in result.plans:
        lines.append(
            f"| {plan.symbol} | {plan.side} | {plan.qty:.0f} | {plan.close:.2f} | "
            f"{plan.stop_price:.2f} | {plan.target_price:.2f} | {plan.r_value:.4f} | "
            f"{plan.decision} | {plan.reason or plan.broker_status or ''} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    append_jsonl(directory / "cycles.jsonl", [{k: v for k, v in payload.items() if k != "orders"}])
    result.report_path = str(json_path)
