"""Book account credentials and the Alpaca Paper client factory.

The two book accounts live in a 600 env file outside the repository (default
``/root/.config/open-composer/paper-book-accounts.env``, override with ``OC_BOOK_ACCOUNTS_ENV``).
Values are read with ``dotenv_values`` by variable name only; nothing here prints, logs or persists
a credential value, and error messages name variables, never values.  This module never loads the
repository ``.env`` (that file belongs to the ETF-sleeve paper account).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

BOOK_ACCOUNTS = ("quant1", "quant2")
DEFAULT_BOOK_ACCOUNTS_ENV = "/root/.config/open-composer/paper-book-accounts.env"
BOOK_ACCOUNTS_ENV_VAR = "OC_BOOK_ACCOUNTS_ENV"
BASE_URL_VAR = "ALPACA_BOOK_BASE_URL"
PAPER_HOST = "paper-api.alpaca.markets"
PAPER_ORIGIN = f"https://{PAPER_HOST}"


class BookAccountError(RuntimeError):
    """Account selection, credential loading or paper-origin guard failure."""


@dataclass(frozen=True)
class BookCredentials:
    """Credentials of one book account.  The secret fields are excluded from ``repr``."""

    account: str
    base_url: str
    key_id: str = field(repr=False)
    secret_key: str = field(repr=False)


def credential_variable_names(account: str) -> tuple[str, str, str]:
    name = _require_account(account).upper()
    return BASE_URL_VAR, f"ALPACA_{name}_API_KEY_ID", f"ALPACA_{name}_API_SECRET_KEY"


def book_accounts_env_path() -> Path:
    return Path(os.environ.get(BOOK_ACCOUNTS_ENV_VAR) or DEFAULT_BOOK_ACCOUNTS_ENV)


def require_paper_origin(base_url: str) -> str:
    """Return the canonical paper origin or raise.  Accepts an optional trailing ``/v2``."""
    value = (base_url or "").strip().rstrip("/")
    if value.endswith("/v2"):
        value = value[: -len("/v2")]
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        port = -1
    valid = (
        PAPER_HOST in value
        and parsed.scheme == "https"
        and parsed.hostname == PAPER_HOST
        and port in {None, 443}
        and parsed.path in {"", "/"}
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )
    if not valid:
        raise BookAccountError(f"book accounts require the Alpaca Paper origin {PAPER_ORIGIN}")
    return PAPER_ORIGIN


def present_variables(account: str, env_path: Path | str | None = None) -> dict[str, bool]:
    """Which expected variable names exist (and are non-empty) in the env file.  Booleans only."""
    path = Path(env_path) if env_path else book_accounts_env_path()
    values = dotenv_values(path) if path.is_file() else {}
    return {name: bool(values.get(name)) for name in credential_variable_names(account)}


def load_account_credentials(account: str, env_path: Path | str | None = None) -> BookCredentials:
    path = Path(env_path) if env_path else book_accounts_env_path()
    base_var, key_var, secret_var = credential_variable_names(account)
    if not path.is_file():
        raise BookAccountError("book accounts env file is missing")
    values = dotenv_values(path)
    missing = [name for name in (base_var, key_var, secret_var) if not values.get(name)]
    if missing:
        raise BookAccountError("book accounts env file lacks variables: " + ", ".join(missing))
    origin = require_paper_origin(str(values[base_var]))
    return BookCredentials(
        account=account,
        base_url=origin,
        key_id=str(values[key_var]),
        secret_key=str(values[secret_var]),
    )


def make_trading_client(account: str, env_path: Path | str | None = None):
    """Alpaca Paper ``TradingClient`` for a book account, marked as a verified paper client.

    Reuses the existing paper-origin verification of the ETF-sleeve adapter
    (``_mark_verified_paper_client``) so that client carries the same marker; the URL is checked by
    :func:`require_paper_origin` first because the adapter's own origin check reads the other
    account's configuration."""
    creds = load_account_credentials(account, env_path)
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:  # pragma: no cover - alpaca-py is a project dependency
        raise BookAccountError("alpaca-py is required for book accounts") from exc
    from open_composer.adapters.broker.alpaca_paper import (
        PaperOrderError,
        _mark_verified_paper_client,
    )

    client = TradingClient(
        api_key=creds.key_id,
        secret_key=creds.secret_key,
        paper=True,
        url_override=creds.base_url,
    )
    try:
        return _mark_verified_paper_client(client, origin=creds.base_url)
    except PaperOrderError as exc:
        raise BookAccountError(str(exc)) from exc


def _require_account(account: str) -> str:
    if account not in BOOK_ACCOUNTS:
        raise BookAccountError(f"unknown book account {account!r}; expected one of {BOOK_ACCOUNTS}")
    return account
