# ruff: noqa: E501
"""T-20261007-06 cost lookup built on the frozen cost-table.json (measured NBBO half spreads)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "reports/research/iterations/t20261007_06_intraday_batch2/cost-table.json"
STOCK_SLIP_BP = 0.5
ETF_SLIP_BP = 0.02
SEC_FEE_BP = 0.206
MIN_DAYS = 8


class CostModel:
    def __init__(self, path: Path = TABLE):
        t = json.loads(Path(path).read_text())
        self.per_symbol = t["per_symbol_median_hs_bp"]
        self.bucket = t["bucket_median_hs_bp"]

    def hs(self, symbol: str, snap: str, bucket: str) -> float:
        """Half spread (bp): symbol median if >= MIN_DAYS sampled days, else the bucket median."""
        r = self.per_symbol.get(symbol, {}).get(snap)
        if r and r["n"] >= MIN_DAYS:
            return float(r["med"])
        b = self.bucket.get(bucket, {}).get(snap)
        if b is None:  # unsampled bucket: fall back to the widest sampled one
            b = max(self.bucket[k][snap]["med"] for k in self.bucket if snap in self.bucket[k])
            return float(b)
        return float(b["med"])

    @staticmethod
    def rank_bucket(rank_dedup: float, rank_pool: float) -> str:
        if rank_dedup == rank_dedup and rank_dedup <= 20:
            return "top20"
        if rank_pool <= 100:
            return "r21_100"
        if rank_pool <= 250:
            return "r101_250"
        return "r251_500"
