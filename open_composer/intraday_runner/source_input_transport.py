"""Existing configured data/SEC factories, one bounded GET, no alternate keys.

This is only constructed by an admitted source invocation. It never upgrades
entitlements or retries failures. Source_writer owns exact raw/page evidence.
"""

from __future__ import annotations

import ast
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from open_composer.intraday_runner.source_method_bindings import bound_bytes


@dataclass(frozen=True)
class SourceResponse:
    entity_bytes: bytes
    status_code: int
    headers: dict


def _class(root, binding, name, namespace):
    data = bound_bytes(root, binding)
    tree = ast.parse(data)
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
    if len(nodes) != 1:
        raise ValueError("exact existing factory class absent")
    # Compile only the bound original class, not the old financial study entry.
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
            binding["path"],
            "exec",
        ),
        namespace,
    )
    return namespace[name]


class ExistingSourceTransport:
    def __init__(
        self, root: Path, bindings: dict, *, allowed_ciks: set[int], read_guard, expires_at
    ):
        self.read_guard = read_guard
        self.expires_at = expires_at
        self.root = root
        self.bindings = bindings
        self.allowed_ciks = allowed_ciks
        self.data = None
        self.sec = None
        self.last = 0.0

    def _read_scope(self):
        if self.read_guard() is not None:
            raise ValueError("source guard must raise or return None")
        if self.expires_at.tzinfo is None or datetime.now(UTC) >= self.expires_at:
            raise ValueError("actual source grant expired")

    def fetch(self, endpoint, params, timeout_seconds):
        timeout = min(15.0, float(timeout_seconds))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("source deadline elapsed")
        deadline = time.monotonic() + timeout
        self._read_scope()
        u = urlparse(endpoint)
        if u.scheme != "https" or u.query or u.fragment or u.username or u.password:
            raise ValueError("unaccepted source URL")
        if u.netloc == "data.alpaca.markets":
            if u.path not in {
                "/v2/stocks/bars",
                "/v1/corporate-actions",
                "/v2/stocks/quotes/latest",
                "/v2/stocks/quotes",
            }:
                raise ValueError("outside accepted market endpoint scope")
            if self.data is None:
                factory = _class(
                    self.root,
                    self.bindings["market_factory"],
                    "DataSession",
                    {"ROOT": self.root, "Any": Any, "time": time},
                )
                self.data = factory()
                from requests.adapters import HTTPAdapter

                self.data.session.mount("https://", HTTPAdapter(max_retries=0))
            session = self.data.session
            mode = "requests"
        elif u.netloc in {"data.sec.gov", "www.sec.gov"}:
            import re

            digits = re.search(r"CIK(\d+)\.json$", u.path) or re.search(
                r"/Archives/edgar/data/(\d+)/", u.path
            )
            if digits is None or int(digits.group(1)) not in self.allowed_ciks or params:
                raise ValueError("SEC request outside exact fixed issuer identities")
            if self.sec is None:
                from dotenv import load_dotenv

                load_dotenv(self.root / ".env")
                factory = _class(
                    self.root,
                    self.bindings["sec_factory"],
                    "SecClient",
                    {
                        "MIN_REQUEST_INTERVAL_SECONDS": 0.15,
                        "HTTP_TIMEOUT_SECONDS": 180,
                        "time": time,
                    },
                )
                self.sec = factory()
            session = self.sec._client
            mode = "httpx"
        else:
            raise ValueError("unaccepted source host")
        delay = 0.35 - (time.monotonic() - self.last)
        if delay > 0:
            time.sleep(delay)
        self._read_scope()
        self.last = time.monotonic()
        timeout = deadline - self.last
        if timeout <= 0:
            raise ValueError("source deadline elapsed")
        timeout = min(timeout, (self.expires_at - datetime.now(UTC)).total_seconds())
        if timeout <= 0:
            raise ValueError("source grant expired after pacing")
        # Existing factories provide credentials/contact only; their retrying
        # convenience methods are deliberately not called.
        if mode == "requests":
            response = session.get(endpoint, params=params, timeout=timeout, allow_redirects=False)
            raw = response.content
        else:
            response = session.get(endpoint, params=params, timeout=timeout, follow_redirects=False)
            raw = response.content
        return SourceResponse(
            raw,
            int(response.status_code),
            {
                k: v
                for k, v in response.headers.items()
                if k.lower()
                in {
                    "date",
                    "content-type",
                    "content-length",
                    "x-request-id",
                    "etag",
                    "last-modified",
                }
            },
        )

    def close(self):
        if self.data is not None:
            self.data.session.close()
        if self.sec is not None:
            self.sec._client.close()
