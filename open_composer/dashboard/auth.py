from __future__ import annotations

import secrets
from collections.abc import Mapping
from functools import lru_cache
from urllib.parse import parse_qs

import jwt

from open_composer.config import (
    cloudflare_access_audience,
    cloudflare_access_team_domain,
    dashboard_allowed_emails,
    dashboard_auth_mode,
)


def dashboard_auth_required(
    api_token: str | None,
    *,
    auth_mode: str | None = None,
) -> bool:
    mode = normalize_dashboard_auth_mode(auth_mode)
    if mode == "disabled":
        return False
    if mode == "token":
        return bool(api_token)
    return True


def dashboard_request_authorized(
    headers: Mapping[str, str],
    api_token: str | None,
    *,
    query: str = "",
    auth_mode: str | None = None,
) -> bool:
    mode = normalize_dashboard_auth_mode(auth_mode)
    if mode == "disabled":
        return True
    if mode == "cloudflare_access":
        return cloudflare_access_request_authorized(headers)
    if mode == "cloudflare_access_or_token":
        return cloudflare_access_request_authorized(headers) or token_request_authorized(
            headers, api_token, query=query
        )
    return token_request_authorized(headers, api_token, query=query)


def normalize_dashboard_auth_mode(auth_mode: str | None = None) -> str:
    mode = (auth_mode or dashboard_auth_mode()).strip().lower()
    if mode in {"token", "cloudflare_access", "cloudflare_access_or_token", "disabled"}:
        return mode
    return "token"


def token_request_authorized(
    headers: Mapping[str, str],
    api_token: str | None,
    *,
    query: str = "",
) -> bool:
    if not api_token:
        return True
    provided = str(headers.get("X-Open-Composer-Token", "")).strip()
    authorization = str(headers.get("Authorization", "")).strip()
    if not provided and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if not provided and query:
        values = parse_qs(query)
        provided = str((values.get("token") or values.get("dashboard_token") or [""])[0]).strip()
    return secrets.compare_digest(provided, api_token)


def cloudflare_access_request_authorized(headers: Mapping[str, str]) -> bool:
    assertion = str(headers.get("Cf-Access-Jwt-Assertion", "")).strip()
    if not assertion:
        return False
    try:
        claims = decode_cloudflare_access_jwt(assertion)
    except (jwt.PyJWTError, OSError, ValueError):
        return False
    allowed_emails = dashboard_allowed_emails()
    if not allowed_emails:
        return False
    email = str(claims.get("email", "")).strip().lower()
    return bool(email and email in allowed_emails)


def decode_cloudflare_access_jwt(assertion: str) -> dict[str, object]:
    team_domain = cloudflare_access_team_domain()
    audience = cloudflare_access_audience()
    if not team_domain or not audience:
        raise ValueError("Cloudflare Access team domain and AUD are required.")
    jwks_client = _cloudflare_jwks_client(team_domain)
    signing_key = jwks_client.get_signing_key_from_jwt(assertion)
    claims = jwt.decode(
        assertion,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=team_domain,
    )
    if not isinstance(claims, dict):
        raise ValueError("Cloudflare Access claims must be an object.")
    return claims


@lru_cache(maxsize=8)
def _cloudflare_jwks_client(team_domain: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{team_domain.rstrip('/')}/cdn-cgi/access/certs")
