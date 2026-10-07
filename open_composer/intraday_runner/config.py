"""Runner configuration and authorization (paper only, bound to the config hash)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

import yaml

from open_composer.paper_intraday import (
    IntradayAuthorization,
    IntradayError,
    _canonical_hash,
    _parse_et_time,
    intraday_dir,
)
from open_composer.paper_lock import paper_control_lock
from open_composer.storage import ensure_dir, write_json

TIMEFRAMES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30}
MAX_AUTH_DAYS = 30
AUTH_KIND = "intraday_runner_paper"


class RunnerConfigError(IntradayError):
    pass


@dataclass(frozen=True)
class StrategyCaps:
    max_notional_usd: float
    max_symbol_notional_usd: float
    max_daily_loss_usd: float
    max_orders_per_day: int


@dataclass(frozen=True)
class FeeModel:
    """Estimated regulatory costs.  Alpaca commission is zero; the defaults are zero too and the
    real SEC/TAF rates are still to be verified (待核对), so reports show them as ``fees``."""

    commission_per_share: float = 0.0
    sec_fee_per_million_sold: float = 0.0
    taf_per_share_sold: float = 0.0

    def fee(self, qty: float, price: float) -> float:
        shares = abs(qty)
        fee = self.commission_per_share * shares
        if qty < 0:
            fee += self.sec_fee_per_million_sold * shares * price / 1e6
            fee += self.taf_per_share_sold * shares
        return fee


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    plugin: str
    params: dict[str, Any]
    symbols: tuple[str, ...]
    timeframe: str
    capital_usd: float
    caps: StrategyCaps
    allow_overnight: bool = False
    assumed_cost_bps: float = 0.0
    # same-side resizes smaller than this fraction of the position are skipped
    resize_band: float = 0.05
    # client-side stop on 1-minute closes vs the average cost (0 = off); no broker-side stops
    stop_loss_pct: float = 0.0
    stop_cooldown_minutes: int = 30
    # per-strategy flatten time (ET); None = the session default.  15:45-15:59, same number of
    # minutes before the close on half days
    flatten_et: time | None = None

    @property
    def minutes(self) -> int:
        return TIMEFRAMES[self.timeframe]


@dataclass(frozen=True)
class AccountCaps:
    max_gross_notional_usd: float
    max_daily_loss_usd: float
    max_orders_per_day: int = 5000


@dataclass(frozen=True)
class RunnerConfig:
    runner_name: str
    account: str
    live_feed: str
    flatten_et: time
    bar_delay_seconds: float
    max_tick_staleness_seconds: float
    order_ttl_seconds: float
    max_resubmit_age_seconds: float
    account_caps: AccountCaps
    strategies: tuple[StrategyConfig, ...]
    fees: FeeModel = field(default_factory=FeeModel)
    shadow_slippage_bps: float = 1.0  # fill model of the no-order shadow mode
    api_calls_per_minute: int = 180  # Alpaca allows 200 for orders and market data together
    path: str = ""
    content_hash: str = ""

    def strategy(self, name: str) -> StrategyConfig:
        for item in self.strategies:
            if item.name == name:
                return item
        raise KeyError(name)

    @property
    def all_symbols(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(s for item in self.strategies for s in item.symbols))


def _positive(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RunnerConfigError(f"{label} must be a number") from exc
    if number <= 0:
        raise RunnerConfigError(f"{label} must be positive")
    return number


FLATTEN_EARLIEST = time(15, 45)
FLATTEN_LATEST = time(15, 59)


def _flatten_time(value: Any, label: str) -> time:
    parsed = _parse_et_time(str(value))
    if not FLATTEN_EARLIEST <= parsed <= FLATTEN_LATEST:
        raise RunnerConfigError(f"{label} must be between 15:45 and 15:59 ET")
    return parsed


def _strategy_from_raw(raw: dict[str, Any]) -> StrategyConfig:
    name = str(raw.get("name") or "").strip()
    if not name or "/" in name or "|" in name:
        raise RunnerConfigError(f"invalid strategy name: {name!r}")
    symbols = tuple(str(s).strip().upper() for s in raw.get("symbols") or [] if str(s).strip())
    if not symbols:
        raise RunnerConfigError(f"strategy {name} needs at least one symbol")
    timeframe = str(raw.get("timeframe") or "")
    if timeframe not in TIMEFRAMES:
        raise RunnerConfigError(f"strategy {name}: timeframe must be one of {sorted(TIMEFRAMES)}")
    caps_raw = raw.get("caps") or {}
    capital = _positive(raw.get("capital_usd"), f"{name}.capital_usd")
    caps = StrategyCaps(
        max_notional_usd=_positive(
            caps_raw.get("max_notional_usd", capital), f"{name}.max_notional_usd"
        ),
        max_symbol_notional_usd=_positive(
            caps_raw.get("max_symbol_notional_usd", capital), f"{name}.max_symbol_notional_usd"
        ),
        max_daily_loss_usd=_positive(
            caps_raw.get("max_daily_loss_usd"), f"{name}.max_daily_loss_usd"
        ),
        max_orders_per_day=int(_positive(caps_raw.get("max_orders_per_day"), f"{name}.orders")),
    )
    if caps.max_symbol_notional_usd > caps.max_notional_usd:
        raise RunnerConfigError(f"{name}: max_symbol_notional_usd exceeds max_notional_usd")
    return StrategyConfig(
        name=name,
        plugin=str(raw.get("plugin") or ""),
        params=dict(raw.get("params") or {}),
        symbols=symbols,
        timeframe=timeframe,
        capital_usd=capital,
        caps=caps,
        allow_overnight=bool(raw.get("allow_overnight", False)),
        assumed_cost_bps=float(raw.get("assumed_cost_bps", 0.0)),
        resize_band=float(raw.get("resize_band", 0.05)),
        stop_loss_pct=float(raw.get("stop_loss_pct", 0.0)),
        stop_cooldown_minutes=int(raw.get("stop_cooldown_minutes", 30)),
        flatten_et=_flatten_time(raw["flatten_et"], f"{name}.flatten_et")
        if raw.get("flatten_et")
        else None,
    )


def load_runner_config(path: Path) -> RunnerConfig:
    path = Path(path)
    if not path.is_file():
        raise RunnerConfigError(f"runner config is missing: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise RunnerConfigError("runner config must be a mapping")
    name = str(raw.get("runner_name") or "").strip()
    account = str(raw.get("account") or "").strip()
    if not name or not account:
        raise RunnerConfigError("runner config needs runner_name and account")
    strategies = tuple(_strategy_from_raw(item) for item in raw.get("strategies") or [])
    if not strategies:
        raise RunnerConfigError("runner config needs at least one strategy")
    if len({s.name for s in strategies}) != len(strategies):
        raise RunnerConfigError("strategy names must be unique")
    caps_raw = raw.get("account_caps") or {}
    account_caps = AccountCaps(
        max_gross_notional_usd=_positive(caps_raw.get("max_gross_notional_usd"), "gross cap"),
        max_daily_loss_usd=_positive(caps_raw.get("max_daily_loss_usd"), "account daily loss"),
        max_orders_per_day=int(caps_raw.get("max_orders_per_day", 5000)),
    )
    session = raw.get("session") or {}
    live_feed = str(raw.get("live_feed") or "iex").lower()
    if live_feed not in {"iex", "sip"}:
        raise RunnerConfigError("live_feed must be iex or sip")
    fees_raw = raw.get("fees") or {}
    fees = FeeModel(
        commission_per_share=float(fees_raw.get("commission_per_share", 0.0)),
        sec_fee_per_million_sold=float(fees_raw.get("sec_fee_per_million_sold", 0.0)),
        taf_per_share_sold=float(fees_raw.get("taf_per_share_sold", 0.0)),
    )
    config = RunnerConfig(
        runner_name=name,
        account=account,
        live_feed=live_feed,
        flatten_et=_flatten_time(session.get("flatten_et", "15:55"), "session.flatten_et"),
        bar_delay_seconds=float(session.get("bar_delay_seconds", 5)),
        max_tick_staleness_seconds=float(session.get("max_tick_staleness_seconds", 90)),
        order_ttl_seconds=float(session.get("order_ttl_seconds", 60)),
        max_resubmit_age_seconds=float(session.get("max_resubmit_age_seconds", 120)),
        account_caps=account_caps,
        strategies=strategies,
        fees=fees,
        shadow_slippage_bps=float(raw.get("shadow_slippage_bps", 1.0)),
        api_calls_per_minute=int(raw.get("api_calls_per_minute", 180)),
        path=str(path),
    )
    payload = json.loads(json.dumps(raw, sort_keys=True, default=str))
    return RunnerConfig(**{**config.__dict__, "content_hash": _canonical_hash(payload)})


# ---------------------------------------------------------------------------
# authorization (paper only; written by the coordinator, never by research code)


def runner_authorization_path(root: Path, runner_name: str) -> Path:
    return intraday_dir(root) / f"runner-{runner_name}-authorization.json"


def write_runner_authorization(
    config: RunnerConfig,
    root: Path,
    *,
    authorized_by: str,
    basis: str,
    account_id_hash: str,
    duration_days: int,
    now: datetime | None = None,
) -> Path:
    if not authorized_by.strip() or not basis.strip():
        raise RunnerConfigError("authorized_by and basis (the owner's words) are required")
    if not 1 <= duration_days <= MAX_AUTH_DAYS:
        raise RunnerConfigError(f"duration_days must be 1..{MAX_AUTH_DAYS}")
    if not account_id_hash:
        raise RunnerConfigError("account_id_hash is required")
    stamp = now or datetime.now(UTC)
    payload = {
        "authorization_kind": AUTH_KIND,
        "authorization_id": "ocr_"
        + hashlib.sha256(
            f"{config.runner_name}|{config.content_hash}|{stamp.isoformat()}".encode()
        ).hexdigest()[:16],
        "strategy_name": config.runner_name,
        "config_path": config.path,
        "config_hash": config.content_hash,
        "authorized_by": authorized_by.strip(),
        "authorization_basis": basis.strip(),
        "authorized_at": stamp.isoformat(),
        "expires_at": (stamp + timedelta(days=duration_days)).isoformat(),
        "broker_account_id_hash": account_id_hash,
        "caps": {
            "max_gross_notional_usd": config.account_caps.max_gross_notional_usd,
            "max_daily_loss_usd": config.account_caps.max_daily_loss_usd,
        },
        "account": config.account,
        "paper_only": True,
        "scope": "Alpaca Paper only; intraday market orders from registered plugins; "
        "flat before the close unless a strategy allows overnight. No real-money writes.",
    }
    path = runner_authorization_path(root, config.runner_name)
    ensure_dir(path.parent)
    with paper_control_lock(root):
        write_json(path, payload)
    return path


def load_runner_authorization(
    config: RunnerConfig, root: Path, *, account_id_hash: str, now: datetime | None = None
) -> IntradayAuthorization:
    path = runner_authorization_path(root, config.runner_name)
    if not path.is_file():
        raise RunnerConfigError(f"no runner authorization at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RunnerConfigError(f"runner authorization is not valid JSON: {exc}") from exc
    auth = IntradayAuthorization.from_payload(payload, path)
    if payload.get("authorization_kind") != AUTH_KIND:
        raise RunnerConfigError("authorization is not an intraday runner authorization")
    if auth.strategy_name != config.runner_name or payload.get("account") != config.account:
        raise RunnerConfigError("authorization belongs to a different runner or account")
    if auth.config_hash != config.content_hash:
        raise RunnerConfigError("authorization was written for a different config; re-authorize")
    if auth.broker_account_id_hash != account_id_hash:
        raise RunnerConfigError("authorization is bound to a different paper account")
    stamp = now or datetime.now(UTC)
    expires = datetime.fromisoformat(auth.expires_at)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if stamp >= expires:
        raise RunnerConfigError(f"runner authorization expired at {auth.expires_at}")
    caps = auth.caps
    if (
        float(caps.get("max_gross_notional_usd", 0)) < config.account_caps.max_gross_notional_usd
        or float(caps.get("max_daily_loss_usd", 0)) < config.account_caps.max_daily_loss_usd
    ):
        raise RunnerConfigError("config account caps exceed the authorized caps")
    return auth
