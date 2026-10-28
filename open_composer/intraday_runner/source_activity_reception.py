"""Authenticated one-shot own FILL reception; never submit, infer fees or retry.

Saved bodies are exact SDK-decoded JSON values, not claimed original wire bytes.
Pagination completeness is scoped to the requested FILL stream. All non-FILL
rights, cash settlement and fee classification remain separate obligations.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from open_composer.adapters.broker.alpaca_paper import (
    _atomic_write_text,
    _optional_broker_account_hash,
)
from open_composer.intraday_runner.source_bounded_gateway import plain
from open_composer.intraday_runner.source_dispatch_journal import (
    _ensure_durable_directory,
    _hash,
    classify_own_order,
)
from open_composer.intraday_runner.source_state_checkpoint import restore, snapshot
from open_composer.intraday_runner.source_terminal_holds import retain_terminal_liability


def bind(path):
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def save(path, value):
    if path.exists():
        raise ValueError("immutable reception path already exists")
    _atomic_write_text(path, json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
    return bind(path)


def receive_actual(runtime, directory: Path, *, clock=lambda: datetime.now(UTC)):
    if not runtime._operation_held:
        raise ValueError("own account operation lock required")
    runtime.connect()
    client = runtime.gateway.client
    account = client.get_account()
    aid = account.get("id") if isinstance(account, dict) else account.id
    if _optional_broker_account_hash(aid) != runtime.auth["account_hash"]:
        raise ValueError("actual authenticated account changed")
    _ensure_durable_directory(directory.parent.absolute())
    directory.mkdir(exist_ok=False)
    current = runtime.store.load()
    if current is None:
        raise ValueError("initial own checkpoint absent")
    state, _, _, evidence = restore(runtime.root, current["snapshot"])
    cids = sorted(cid for cid in state.consumed_ids if cid.startswith("dia-base-"))
    order_ids, orders, order_bindings = {}, {}, {}
    for cid in cids:
        if not runtime.journal._path(cid).exists():
            continue  # Reserved but no durable send attempt. Never resubmit here.
        saved = runtime.journal.receive(cid)
        observed = plain(client.get_order_by_client_id(cid))
        binding = save(
            directory / (cid + ".order.json"),
            dict(
                received_at=clock().isoformat(),
                account_hash=runtime.auth["account_hash"],
                method="GET",
                endpoint_kind="own_order_by_client_id",
                order=observed,
            ),
        )
        classified = classify_own_order(saved["request"], observed)
        bid = classified["broker_order_id"]
        if bid in order_ids or any(o["id"] != bid for o in saved["observations"]):
            raise ValueError("actual own order identity changed/duplicated")
        order_ids[bid], orders[cid], order_bindings[cid] = cid, observed, binding
        saved["observations"].append(copy.deepcopy(observed))
        saved.setdefault("reconciliation_captures", []).append(binding)
        _atomic_write_text(runtime.journal._path(cid), json.dumps(saved, sort_keys=True) + "\n")
    token, seen_tokens, captured, applied = None, set(), [], []
    while True:
        if clock() >= datetime.fromisoformat(runtime.auth["expires_at"]):
            raise ValueError("reception authority expired; retain completed prefixes")
        params = dict(after=runtime.auth["authorized_at"], direction="asc", page_size=100)
        if token:
            params["page_token"] = token
        prefix = directory / f"activities-{len(captured):04d}"
        save(prefix.with_suffix(".started.json"), dict(params=params, at=clock().isoformat()))
        payload = client.get("/account/activities/FILL", params)
        received_at = clock().isoformat()
        if not isinstance(payload, list) or runtime.gateway.last_read_status != 200:
            raise ValueError("unknown actual FILL response/status")
        body = save(prefix.with_suffix(".body.json"), payload)
        receipt = save(
            prefix.with_suffix(".capture.json"),
            dict(
                method="GET",
                endpoint_kind="account_activities",
                status=200,
                account_hash=runtime.auth["account_hash"],
                received_at=received_at,
                body=body,
                capture_basis="SDK-decoded JSON list; not original HTTP bytes",
            ),
        )
        captured.append(receipt)
        for ordinal, item in enumerate(payload):
            if not isinstance(item, dict) or item.get("activity_type") != "FILL":
                raise ValueError("unexpected activity schema")
            cid = order_ids.get(item.get("order_id"))
            if cid is not None:
                applied.append(
                    runtime.receive_fill(capture_binding=receipt, ordinal=ordinal, cid=cid)
                )
        if len(payload) < 100:
            break
        token = payload[-1].get("id")
        if not token or token in seen_tokens:
            raise ValueError("incomplete/nonprogressing activity pagination")
        seen_tokens.add(token)
    # Only a terminal observation whose complete cumulative prefix is applied
    # may drop its remaining QUANTITY lock. Every money/fee hold stays intact.
    for cid, order in orders.items():
        journal = runtime.journal.receive(cid)
        if not classify_own_order(journal["request"], order)["terminal_observed"]:
            continue
        current = runtime.store.load()
        state, fills, fees, evidence = restore(runtime.root, current["snapshot"])
        if cid not in state.pending:
            continue
        state, evidence = retain_terminal_liability(
            state,
            evidence,
            journal=journal,
            observed_order=order,
            capture_binding=order_bindings[cid],
        )
        runtime.store.commit(
            snapshot(state, fills, fees, evidence=evidence), expected_head_sha256=_hash(current)
        )
    result = dict(
        status="actual_owned_fill_prefix_received",
        capture_pages=captured,
        transitions=applied,
        own_orders=len(orders),
        fees_reconciled=False,
        settlement_inferred=False,
        full_account_reconciliation=False,
        order_writes=0,
    )
    save(directory / "result.json", result)
    return result
