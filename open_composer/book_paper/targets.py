"""Target files: the signal log of the book, written before any order.

``reports/paper/book/<account>/targets/<decision-date>.json`` holds the book id, the form (F1
neutral with a T-bill leg, F2 index enhancement with SPY 1.0), the decision date t and execution
date (the close of t+1), the equity basis, target weights as a fraction of equity, the reference
prices used to size them, the per-name risk-model exposures (beta, industry, size) and cost inputs
used by the pre-trade checks and the shadow costs, and a SHA-256 of the payload.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from open_composer.book_paper.accounts import BOOK_ACCOUNTS
from open_composer.market_sessions import next_us_equity_session

TBILL_SYMBOLS = ("SGOV", "BIL")
F2_CORE_SYMBOL = "SPY"
SCHEMA_VERSION = 1
CORE_WEIGHT_TOLERANCE = 1e-9


class BookTargetError(ValueError):
    """Malformed, altered or conflicting target file."""


class NameExposure(BaseModel):
    """Risk-model exposures and cost inputs of one name, as of the decision date."""

    model_config = ConfigDict(extra="forbid")

    beta: float
    industry: str
    size: float
    dollar_adv_21: float | None = None
    vol_21: float | None = None


class BookTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    book_id: str = Field(min_length=1)
    account: str
    form: Literal["F1", "F2"]
    decision_date: date
    execution_date: date
    equity_basis: float = Field(gt=0)
    core_symbol: str
    weights: dict[str, float]
    reference_prices: dict[str, float]
    exposures: dict[str, NameExposure]
    logged_at_utc: str
    payload_sha256: str = ""

    @model_validator(mode="after")
    def _check(self) -> BookTarget:
        if self.account not in BOOK_ACCOUNTS:
            raise ValueError(f"unknown book account {self.account!r}")
        if self.execution_date <= self.decision_date:
            raise ValueError("execution_date must be after decision_date")
        if self.form == "F1" and self.core_symbol not in TBILL_SYMBOLS:
            raise ValueError("F1 core leg must be SGOV or BIL")
        if self.form == "F2" and self.core_symbol != F2_CORE_SYMBOL:
            raise ValueError("F2 core leg must be SPY")
        core_weight = self.weights.get(self.core_symbol)
        if core_weight is None or abs(core_weight - 1.0) > CORE_WEIGHT_TOLERANCE:
            raise ValueError("the core leg must be present with weight 1.0")
        for symbol, weight in self.weights.items():
            if not math.isfinite(weight):
                raise ValueError(f"non-finite weight for {symbol}")
            price = self.reference_prices.get(symbol)
            if price is None or not math.isfinite(price) or price <= 0:
                raise ValueError(f"missing or invalid reference price for {symbol}")
        return self

    @property
    def stock_weights(self) -> dict[str, float]:
        return {s: w for s, w in self.weights.items() if s != self.core_symbol}

    @property
    def target_gross(self) -> float:
        return sum(abs(w) for w in self.stock_weights.values())


def payload_sha256(target: BookTarget) -> str:
    body = target.model_dump(mode="json", exclude={"payload_sha256"})
    return hashlib.sha256(_canonical(body).encode()).hexdigest()


def seal_target(target: BookTarget) -> BookTarget:
    return target.model_copy(update={"payload_sha256": payload_sha256(target)})


def book_dir(root: Path, account: str) -> Path:
    if account not in BOOK_ACCOUNTS:
        raise BookTargetError(f"unknown book account {account!r}")
    return Path(root) / "reports" / "paper" / "book" / account


def target_path(root: Path, account: str, decision_date: date) -> Path:
    return book_dir(root, account) / "targets" / f"{decision_date.isoformat()}.json"


def write_target_file(root: Path, target: BookTarget) -> Path:
    """Seal and write the target file (the signal log, before any order).

    Refuses to overwrite a file whose payload differs: a logged target is never silently rewritten.
    ``logged_at_utc`` must be set by the caller (``date -u`` at writing)."""
    sealed = seal_target(target)
    path = target_path(root, sealed.account, sealed.decision_date)
    if path.exists():
        existing = load_target_file(path)
        if existing.payload_sha256 == sealed.payload_sha256:
            return path
        raise BookTargetError(f"target file already logged with a different payload: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(sealed.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def load_target_file(path: Path) -> BookTarget:
    try:
        target = BookTarget.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except ValueError as exc:
        raise BookTargetError(f"invalid target file {Path(path).name}: {exc}") from exc
    if target.payload_sha256 != payload_sha256(target):
        raise BookTargetError(f"target file payload hash mismatch: {Path(path).name}")
    return target


def latest_target_path(root: Path, account: str) -> Path | None:
    folder = book_dir(root, account) / "targets"
    files = sorted(folder.glob("20??-??-??.json")) if folder.is_dir() else []
    return files[-1] if files else None


def now_utc_text(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_execution_date(decision_date: date) -> date:
    return next_us_equity_session(decision_date)


# --------------------------------------------------------------------------------------
# F1 -> F2
# --------------------------------------------------------------------------------------


def f1_to_f2_weights(
    weights: dict[str, float], *, spy_symbol: str = F2_CORE_SYMBOL
) -> dict[str, float]:
    """F2 weights = F1 stock overlay weights + SPY 1.0 in place of the T-bill leg (pure)."""
    tbills = [s for s in weights if s in TBILL_SYMBOLS]
    if len(tbills) != 1:
        raise BookTargetError("F1 weights must contain exactly one T-bill leg (SGOV or BIL)")
    if spy_symbol in weights:
        raise BookTargetError("F1 weights must not already contain SPY")
    out = {s: w for s, w in weights.items() if s not in TBILL_SYMBOLS}
    out[spy_symbol] = 1.0
    return out


def convert_f1_target_to_f2(
    target: BookTarget,
    *,
    spy_price: float,
    account: str = "quant2",
    spy_beta: float = 1.0,
    logged_at_utc: str | None = None,
) -> BookTarget:
    """Same overlay, SPY 1.0 instead of the T-bill leg, for the F2 account."""
    if target.form != "F1":
        raise BookTargetError("only an F1 target can be converted to F2")
    book_id = target.book_id
    exposures = {s: e for s, e in target.exposures.items() if s != target.core_symbol}
    exposures[F2_CORE_SYMBOL] = NameExposure(beta=spy_beta, industry="index", size=0.0)
    prices = {s: p for s, p in target.reference_prices.items() if s != target.core_symbol}
    prices[F2_CORE_SYMBOL] = spy_price
    return seal_target(
        BookTarget(
            book_id=book_id,
            account=account,
            form="F2",
            decision_date=target.decision_date,
            execution_date=target.execution_date,
            equity_basis=target.equity_basis,
            core_symbol=F2_CORE_SYMBOL,
            weights=f1_to_f2_weights(target.weights),
            reference_prices=prices,
            exposures=exposures,
            logged_at_utc=logged_at_utc or target.logged_at_utc,
        )
    )


def _canonical(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
