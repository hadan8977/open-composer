"""Sleeve registry (``config/portfolio-layer/sleeves.json``) and its daily return series."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config/portfolio-layer/sleeves.json"
LIMITS_PATH = ROOT / "config/portfolio-layer/limits.json"
ACTIVE_STATUSES = ("P1", "P0", "observation")
OBSERVATION = "observation"


@dataclass(frozen=True)
class Sleeve:
    id: str
    account: str
    status: str
    capital_usd: float
    raw: dict

    @property
    def has_series(self) -> bool:
        return bool(self.raw.get("returns"))


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    return json.loads(Path(path).read_text())


def sleeves(registry: dict | None = None) -> list[Sleeve]:
    reg = registry or load_registry()
    return [
        Sleeve(s["id"], s["account"], s["status"], float(s.get("capital_usd") or 0.0), s)
        for s in reg["sleeves"]
    ]


def evaluable(registry: dict | None = None) -> list[Sleeve]:
    """Sleeves with a status that carries risk and a stored return series."""
    return [s for s in sleeves(registry) if s.status in ACTIVE_STATUSES and s.has_series]


def load_returns(sleeve: Sleeve, root: Path = ROOT) -> pd.Series:
    spec = sleeve.raw["returns"]
    df = pd.read_parquet(root / spec["path"])
    s = df[spec["column"]].astype(float)
    s.index = pd.to_datetime(s.index)
    return s.dropna().rename(sleeve.id)


def return_frame(registry: dict | None = None, root: Path = ROOT) -> pd.DataFrame:
    """Daily returns of the evaluable sleeves on their common dates (inner join)."""
    cols = [load_returns(s, root) for s in evaluable(registry)]
    return pd.concat(cols, axis=1, join="inner").sort_index()
