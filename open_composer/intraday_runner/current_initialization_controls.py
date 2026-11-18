"""Paper account identity, session clock and limit-price rule for the six-policy service."""

from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation

from open_composer.market_sessions import NEW_YORK, us_equity_session_close

CENT = Decimal(".01")
ENV_PATH = "/root/.config/open-composer/paper-validation-20261019.env"
ACCOUNT = "fa6147de4f85f4f14f225c59eebb9ecc4c764e87571f413afebcb63aa76c81d4"


def number(value, *, nonnegative=True):
    if isinstance(value, bool):
        raise ValueError("boolean is not an amount")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid amount") from exc
    if not result.is_finite() or (nonnegative and result < 0):
        raise ValueError("nonfinite/negative amount")
    return result


def session(day):
    close = us_equity_session_close(day)
    if close is None:
        raise ValueError("not an equity session")
    return (
        datetime.combine(day, time(9, 30), NEW_YORK).astimezone(UTC),
        datetime.combine(day, close, NEW_YORK).astimezone(UTC),
    )


def limit_price(reference, *, exit_order=False):
    p = number(reference)
    if p < 1:
        raise ValueError("this scoped tick rule requires USD price >=1")
    return (p * (Decimal(".995") if exit_order else 1)).quantize(
        CENT, rounding=ROUND_CEILING if exit_order else ROUND_FLOOR
    )
