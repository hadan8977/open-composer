from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data.alpaca import AlpacaDataError
from open_composer.adapters.data.alpaca_snapshot import (
    load_immutable_alpaca_snapshot,
    verify_alpaca_contract_snapshot,
)
from open_composer.models.strategy_spec import StrategySpec


def load_immutable_alpaca_snapshot_bundle(spec: StrategySpec, root: Path) -> pd.DataFrame:
    """Resolve one StrategySpec data identity from a verified snapshot bundle."""
    relative = spec.data.path
    if not relative:
        raise AlpacaDataError("immutable Alpaca StrategySpec requires data.path")
    manifest_path = Path(relative)
    manifest = verify_alpaca_contract_snapshot(root, manifest_path)
    assumptions = spec.data_assumptions.model_dump(mode="json")
    expected_adjustment = _expected_adjustment(assumptions)
    expected = {
        "symbol": spec.primary_symbol,
        "timeframe": spec.timeframe,
        "feed": spec.data.feed,
        "adjustment": expected_adjustment,
        "session_scope": assumptions.get("session_scope"),
    }
    matches = [
        item
        for item in manifest["items"]
        if isinstance(item, dict)
        and all(item.get(field) == value for field, value in expected.items())
    ]
    if len(matches) != 1:
        identity = ", ".join(f"{key}={value}" for key, value in expected.items())
        raise AlpacaDataError(
            "immutable Alpaca snapshot bundle must contain exactly one matching item: " + identity
        )

    base = root.resolve()
    manifest_file = manifest_path if manifest_path.is_absolute() else base / manifest_path
    output_path = manifest_file.resolve().parent / str(matches[0]["output_path"])
    try:
        output_relative = output_path.relative_to(base).as_posix()
    except ValueError as exc:
        raise AlpacaDataError(
            "immutable Alpaca snapshot bundle item escapes repository root"
        ) from exc

    spec_payload: dict[str, Any] = spec.model_dump(mode="python")
    spec_payload["data"]["path"] = output_relative
    spec_payload["data_assumptions"]["adjustment"] = expected_adjustment
    selected_spec = StrategySpec.model_validate(spec_payload)
    frame = load_immutable_alpaca_snapshot(selected_spec, base)
    frame.attrs.update(
        {
            "data_source_mode": "immutable_research_snapshot_bundle",
            "data_bundle_manifest_path": str(manifest_file.resolve()),
            "data_bundle_manifest_sha256": hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
            "data_bundle_item_identity": expected,
        }
    )
    return frame


def _expected_adjustment(assumptions: dict[str, Any]) -> str:
    adjustment = assumptions.get("price_adjustment") or assumptions.get("adjustment")
    if adjustment is None:
        adjustment = "all" if assumptions.get("adjusted") is True else "raw"
    value = str(adjustment)
    if value not in {"raw", "split", "dividend", "all"}:
        raise AlpacaDataError(f"unsupported immutable Alpaca adjustment: {value}")
    return value
