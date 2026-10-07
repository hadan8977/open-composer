# ruff: noqa: E501
"""T-20261006-18 data adapter: extra us-gaap concepts from the local ``companyfacts.zip``.

Not a new download: the zip was fetched on 2026-10-05 by ``scripts/build_sec_xbrl_fundamentals.py``.
This pass parses the same members for the CIKs already in ``sec_fundamentals/facts.parquet`` and
keeps the extra concepts the library batch-1 factors need, with the builder's own cleaning
(``rows_to_frame``, ``select_first_filed``, ``apply_concept_fallback``, ``attach_usable_session``,
``derive_q4``), so visibility is "first session after the filing" exactly as for the nine
existing concepts.

    scripts/run_capped.sh --mem 1.2G -- uv run python scripts/t18_extra_xbrl.py
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_sec_xbrl_fundamentals as bx  # noqa: E402

OUT = ROOT / "data/research/t18_library"
EXTRA_CONCEPTS: dict[str, list[tuple[str, str, str]]] = {
    "cash_sti": [
        ("us-gaap", "CashCashEquivalentsAndShortTermInvestments", "USD"),
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD"),
    ],
    "inventory": [("us-gaap", "InventoryNet", "USD")],
    "cogs": [
        ("us-gaap", "CostOfRevenue", "USD"),
        ("us-gaap", "CostOfGoodsAndServicesSold", "USD"),
        ("us-gaap", "CostOfGoodsSold", "USD"),
    ],
    "sga": [("us-gaap", "SellingGeneralAndAdministrativeExpense", "USD")],
    "rd": [("us-gaap", "ResearchAndDevelopmentExpense", "USD")],
    "adv": [("us-gaap", "AdvertisingExpense", "USD")],
    "tax": [("us-gaap", "IncomeTaxExpenseBenefit", "USD")],
    "ib_cont": [("us-gaap", "IncomeLossFromContinuingOperations", "USD")],
    "ltd_nc": [
        ("us-gaap", "LongTermDebtNoncurrent", "USD"),
        ("us-gaap", "LongTermDebt", "USD"),
    ],
    "debt_cur": [
        ("us-gaap", "LongTermDebtCurrent", "USD"),
        ("us-gaap", "DebtCurrent", "USD"),
    ],
    "pref": [("us-gaap", "PreferredStockValue", "USD")],
    "ppent": [("us-gaap", "PropertyPlantAndEquipmentNet", "USD")],
}
FLOW = ("cogs", "sga", "rd", "adv", "tax", "ib_cont")
BATCH = 300


def main() -> int:
    bx.CONCEPTS = EXTRA_CONCEPTS  # fact_rows_from_payload reads the module global
    base = pd.read_parquet(bx.FACTS_PATH, columns=["cik"])
    ciks = sorted(set(int(c) for c in base["cik"].unique()))
    del base
    OUT.mkdir(parents=True, exist_ok=True)
    parts = []
    with zipfile.ZipFile(bx.ZIP_PATH) as zf:
        names = set(zf.namelist())
        for b0 in range(0, len(ciks), BATCH):
            rows: list[dict] = []
            for cik in ciks[b0 : b0 + BATCH]:
                m = f"CIK{cik:010d}.json"
                if m not in names:
                    continue
                import json

                with zf.open(m) as h:
                    try:
                        payload = json.load(h)
                    except json.JSONDecodeError:
                        continue
                rows.extend(bx.fact_rows_from_payload(cik, payload, "companyfacts_bulk"))
                del payload
            fr = bx.rows_to_frame(rows)
            del rows
            if fr.empty:
                continue
            fr = bx.select_first_filed(fr)
            fr = bx.apply_concept_fallback(fr)
            fr = bx.attach_usable_session(fr)
            flow = fr["concept"].isin(FLOW)
            d = bx.derive_q4(fr.loc[flow])
            fr = pd.concat([fr.loc[~flow].assign(derived_q4=False), d], ignore_index=True)
            fr = fr[fr["period_kind"].isin(["Q", "FY", "instant"])]
            keep = [
                "cik", "concept", "tag", "period_kind", "period_start", "period_end", "fy", "fp",
                "val", "filed", "usable_session", "restated", "derived_q4",
            ]  # fmt: skip
            parts.append(fr[keep])
            print(
                f"batch {b0 // BATCH + 1}/{-(-len(ciks) // BATCH)} rows {sum(len(p) for p in parts)}",
                flush=True,
            )
    out = pd.concat(parts, ignore_index=True)
    out["fp"] = out["fp"].astype("string")
    out.to_parquet(OUT / "facts_extra.parquet", index=False)
    summ = out.groupby("concept").agg(rows=("val", "size"), ciks=("cik", "nunique"))
    print(summ.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
