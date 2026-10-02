"""Target files: the signal log of the book, written before any order.

``reports/paper/book/<account>/targets/<decision-date>.json`` holds the book id, the form (F1
neutral with a T-bill leg, F2 index enhancement with SPY 1.0), the decision date t and execution
date (the close of t+1), the equity basis, target weights as a fraction of equity, the reference
prices used to size them, the per-name risk-model exposures (beta, industry, size) and cost inputs
used by the pre-trade checks and the shadow costs, and a SHA-256 of the payload.

Schema version 2 (book v1.2) adds ``core_weight`` (F1 T-bill leg in [0, 1]; F2 exactly 1.0) and a
SPY beta hedge (``hedge_symbol``, ``hedge_weight``).  ``weights`` stays one merged position per
symbol: core entry = ``core_weight`` (+ ``hedge_weight`` when the hedge is the core symbol, F2) and
the F1 hedge entry = ``hedge_weight``.  A version-1 target carries none of the new fields in its
payload, so its hash and file layout are unchanged.
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
SCHEMA_VERSION = 1  # default: legacy targets (core weight 1.0, no hedge)
SCHEMA_VERSION_V2 = 2
SUPPORTED_SCHEMA_VERSIONS = (SCHEMA_VERSION, SCHEMA_VERSION_V2)
CORE_WEIGHT_TOLERANCE = 1e-9
HEDGE_SYMBOLS = ("SPY",)
MAX_ABS_HEDGE_WEIGHT = 1.5
# fields added in schema 2; omitted from the payload of a version-1 target
_V2_FIELDS = ("core_weight", "hedge_symbol", "hedge_weight")


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
    core_weight: float = 1.0
    hedge_symbol: str | None = None
    hedge_weight: float = 0.0
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
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported target schema_version {self.schema_version}")
        if not math.isfinite(self.core_weight) or not math.isfinite(self.hedge_weight):
            raise ValueError("core_weight and hedge_weight must be finite")
        if self.schema_version == SCHEMA_VERSION and (
            self.core_weight != 1.0 or self.hedge_symbol is not None or self.hedge_weight != 0.0
        ):
            raise ValueError("core_weight, hedge_symbol and hedge_weight need schema_version 2")
        if self.form == "F2":
            if abs(self.core_weight - 1.0) > CORE_WEIGHT_TOLERANCE:
                raise ValueError("F2 core_weight must be exactly 1.0")
        elif not 0.0 <= self.core_weight <= 1.0:
            raise ValueError("F1 core_weight must be in [0, 1]")
        if self.hedge_symbol is not None and self.hedge_symbol not in HEDGE_SYMBOLS:
            raise ValueError(f"hedge_symbol must be one of {HEDGE_SYMBOLS}")
        if abs(self.hedge_weight) > MAX_ABS_HEDGE_WEIGHT:
            raise ValueError(f"|hedge_weight| must be <= {MAX_ABS_HEDGE_WEIGHT}")
        if self.hedge_symbol is None and self.hedge_weight != 0.0:
            raise ValueError("a non-zero hedge_weight needs hedge_symbol")
        hedge_in_core = self.hedge_symbol == self.core_symbol
        if self.form == "F1" and hedge_in_core:
            raise ValueError("F1 hedge symbol cannot be the T-bill core symbol")
        expected_core = self.core_weight + (self.hedge_weight if hedge_in_core else 0.0)
        core_entry = self.weights.get(self.core_symbol)
        if core_entry is None:
            if abs(expected_core) > CORE_WEIGHT_TOLERANCE:
                raise ValueError("the core leg must be present in weights")
        elif abs(core_entry - expected_core) > CORE_WEIGHT_TOLERANCE:
            raise ValueError(
                f"core leg weight {core_entry} must equal core_weight"
                f"{' + hedge_weight' if hedge_in_core else ''} = {expected_core}"
            )
        if self.hedge_symbol is not None and not hedge_in_core:
            hedge_entry = self.weights.get(self.hedge_symbol, 0.0)
            if abs(hedge_entry - self.hedge_weight) > CORE_WEIGHT_TOLERANCE:
                raise ValueError(
                    f"hedge leg weight {hedge_entry} must equal hedge_weight {self.hedge_weight}"
                )
        for symbol, weight in self.weights.items():
            if not math.isfinite(weight):
                raise ValueError(f"non-finite weight for {symbol}")
            price = self.reference_prices.get(symbol)
            if price is None or not math.isfinite(price) or price <= 0:
                raise ValueError(f"missing or invalid reference price for {symbol}")
        return self

    @property
    def non_stock_symbols(self) -> frozenset[str]:
        """The core leg and the hedge leg; everything else is the stock overlay."""
        return frozenset({self.core_symbol} | ({self.hedge_symbol} if self.hedge_symbol else set()))

    @property
    def stock_weights(self) -> dict[str, float]:
        skip = self.non_stock_symbols
        return {s: w for s, w in self.weights.items() if s not in skip}

    @property
    def target_gross(self) -> float:
        return sum(abs(w) for w in self.stock_weights.values())


def _dump(target: BookTarget) -> dict[str, object]:
    """Serialisable body; a version-1 target omits the schema-2 fields (hash and file unchanged)."""
    exclude = {"payload_sha256"}
    if target.schema_version == SCHEMA_VERSION:
        exclude |= set(_V2_FIELDS)
    return target.model_dump(mode="json", exclude=exclude)


def payload_sha256(target: BookTarget) -> str:
    return hashlib.sha256(_canonical(_dump(target)).encode()).hexdigest()


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
        json.dumps(
            {**_dump(sealed), "payload_sha256": sealed.payload_sha256}, indent=2, sort_keys=True
        )
        + "\n",
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
    if target.hedge_symbol is not None or target.hedge_weight != 0.0 or target.core_weight != 1.0:
        raise BookTargetError(
            "a target with a hedge or a core weight other than 1.0 cannot be converted; "
            "generate the F2 target directly"
        )
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
