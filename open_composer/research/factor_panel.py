from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import ensure_dir, project_root
from open_composer.expressions import prepare_factor_frame
from open_composer.models.strategy_spec import load_strategy_spec

FactorPanelFormat = Literal["csv", "jsonl"]

FACTOR_PANEL_COLUMNS = [
    "timestamp",
    "symbol",
    "factor_name",
    "factor_value",
    "forward_return",
    "horizon",
    "group",
    "market_cap_bucket",
    "source",
    "visible_at",
]


@dataclass(frozen=True)
class FactorPanelBuildResult:
    strategy_name: str
    path: Path
    rows: int
    factor_names: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_factor_panel(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".jsonl":
        records: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
        frame = pd.DataFrame.from_records(records)
    else:
        frame = pd.read_csv(path)
    return normalize_factor_panel(frame)


def normalize_factor_panel(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [
        column
        for column in [
            "timestamp",
            "symbol",
            "factor_name",
            "factor_value",
            "forward_return",
        ]
        if column not in frame.columns
    ]
    if missing:
        raise ValueError("factor panel missing required columns: " + ", ".join(missing))
    panel = frame.copy()
    panel["timestamp"] = pd.to_datetime(panel["timestamp"], utc=True, errors="coerce")
    panel["symbol"] = panel["symbol"].astype(str)
    panel["factor_name"] = panel["factor_name"].astype(str)
    panel["factor_value"] = pd.to_numeric(panel["factor_value"], errors="coerce")
    panel["forward_return"] = pd.to_numeric(panel["forward_return"], errors="coerce")
    panel["horizon"] = pd.to_numeric(panel.get("horizon", 1), errors="coerce").fillna(1).astype(int)
    for column in ["group", "market_cap_bucket", "source", "visible_at"]:
        if column not in panel.columns:
            panel[column] = None
    panel["visible_at"] = pd.to_datetime(panel["visible_at"], utc=True, errors="coerce")
    panel = panel.sort_values(["timestamp", "factor_name", "symbol"]).reset_index(drop=True)
    if panel["timestamp"].isna().any():
        raise ValueError("factor panel contains invalid timestamp values")
    return panel


def build_factor_panel_from_spec(
    spec_path: Path,
    root: Path | None = None,
    *,
    forward_bars: int = 1,
    output_path: Path | None = None,
    output_format: FactorPanelFormat = "csv",
) -> FactorPanelBuildResult:
    if forward_bars < 1:
        raise ValueError("--forward-bars must be at least 1")
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    if not spec.factors:
        raise ValueError("StrategySpec has no factors to materialize")
    frame = load_ohlcv_for_spec(spec, base)
    prepared = prepare_factor_frame(
        frame,
        spec.factors,
        root=base,
        symbol=spec.primary_symbol,
        require_feature_symbol=False,
    )
    forward_return = pd.to_numeric(prepared["close"], errors="coerce").shift(-forward_bars)
    forward_return = forward_return / pd.to_numeric(prepared["close"], errors="coerce") - 1
    records: list[dict[str, object]] = []
    for factor_name, factor in spec.factors.items():
        values = pd.to_numeric(prepared[factor_name], errors="coerce")
        for timestamp, factor_value, return_value in zip(
            prepared["timestamp"],
            values,
            forward_return,
            strict=False,
        ):
            records.append(
                {
                    "timestamp": pd.Timestamp(timestamp).tz_convert("UTC").isoformat()
                    if pd.Timestamp(timestamp).tzinfo
                    else pd.Timestamp(timestamp).tz_localize("UTC").isoformat(),
                    "symbol": spec.primary_symbol,
                    "factor_name": factor_name,
                    "factor_value": None if pd.isna(factor_value) else float(factor_value),
                    "forward_return": None if pd.isna(return_value) else float(return_value),
                    "horizon": forward_bars,
                    "group": None,
                    "market_cap_bucket": None,
                    "source": factor.source,
                    "visible_at": pd.Timestamp(timestamp).tz_convert("UTC").isoformat()
                    if pd.Timestamp(timestamp).tzinfo
                    else pd.Timestamp(timestamp).tz_localize("UTC").isoformat(),
                }
            )
    path = output_path or (
        base / "reports" / "research" / f"{spec.name}-factor-panel.{output_format}"
    )
    ensure_dir(path.parent)
    panel = pd.DataFrame.from_records(records, columns=FACTOR_PANEL_COLUMNS)
    if output_format == "jsonl" or path.suffix.lower() == ".jsonl":
        with path.open("w", encoding="utf-8") as handle:
            for record in panel.to_dict(orient="records"):
                handle.write(json.dumps(record, sort_keys=True) + "\n")
    else:
        panel.to_csv(path, index=False)
    warnings = []
    if len(spec.universe) < 2:
        warnings.append("single_symbol_panel_limits_cross_sectional_power")
    return FactorPanelBuildResult(
        strategy_name=spec.name,
        path=path,
        rows=len(panel),
        factor_names=sorted(spec.factors),
        warnings=warnings,
    )
