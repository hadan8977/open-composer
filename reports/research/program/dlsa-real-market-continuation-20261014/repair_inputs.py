"""Isolated source-led repairs of the received cohort. No economic computation."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, default=str) + "\n")


def main():
    layout = json.loads((ROOT / "data/sip/daily/_LAYOUT.json").read_text())
    mapping = {s: k for k, values in layout["shard_symbols"].items() for s in values}
    targets = ["EG", "MTB", "SPY", "BIL", "XLF", "XLI"]
    records, receipt = [], []
    for year in range(2018, 2027):
        for shard in sorted({mapping[s] for s in targets}):
            p = ROOT / f"data/sip/daily/{year}/shard-{shard}.parquet"
            frame = pq.read_table(
                p,
                columns=["symbol", "timestamp", "open", "close", "volume", "trade_count"],
                filters=[("symbol", "in", targets)],
                use_threads=False,
            ).to_pandas()
            records.append(frame)
            receipt.append(
                {
                    "path": str(p.relative_to(ROOT)),
                    "bytes": p.stat().st_size,
                    "selected_rows": len(frame),
                    "selected_record_sha256": hashlib.sha256(
                        pd.util.hash_pandas_object(frame, index=False).values.tobytes()
                    ).hexdigest(),
                }
            )
    extra = pd.concat(records, ignore_index=True)
    extra["session"] = (
        pd.to_datetime(extra.timestamp, utc=True)
        .dt.tz_convert("America/New_York")
        .dt.strftime("%Y-%m-%d")
    )
    extra = extra[(extra.session >= "2018-01-02") & (extra.session <= "2026-09-30")]
    extra = extra.drop_duplicates(["symbol", "session"])
    extra.to_parquet(OUT / "inputs/repair-and-benchmark-source-bars.parquet", index=False)
    bars = pd.read_parquet(OUT / "inputs/selected-bars.parquet")
    replacement = extra[extra.symbol == "EG"].copy()
    replacement["source_symbol"] = "EG"
    replacement["symbol"] = "RE"
    replacement["historical_ticker"] = np.where(replacement.session < "2023-07-10", "RE", "EG")
    replacement["security_episode"] = "EP_EVEREST_CONTINUING_COMMON"
    replacement["source_file"] = "exact-index EG source; see repair-read-receipt.json"
    replacement["source_rank"] = 0
    replacement["ghost"] = (replacement.volume == 0) & (replacement.trade_count.fillna(0) == 0)
    # Whole-episode replacement in ONE data vintage, not two-level stitching.
    revised = pd.concat([bars[bars.symbol != "RE"], replacement], ignore_index=True)
    revised["security_episode"] = revised.security_episode.fillna(
        revised.symbol.map(lambda s: "EP_" + s + "_20210104_CANDIDATE")
    )
    revised.loc[revised.symbol == "FOX", "security_episode"] = np.where(
        revised.loc[revised.symbol == "FOX", "session"] < "2019-03-19",
        "EP_21CF_OLD_CLASS_B_EXCLUDED_FROM_NEW_FOX_HISTORY",
        "CUSIP35137L204_FOX_CLASS_B",
    )
    revised["episode_history_candidate"] = True
    revised.loc[
        (revised.symbol == "FOX") & (revised.session < "2019-03-19"), "episode_history_candidate"
    ] = False
    revised.to_parquet(OUT / "inputs/reconstructed-episode-bars.parquet", index=False)
    write("inputs/repair-read-receipt.json", receipt)
    write(
        "inputs/detailed-episode-repairs.json",
        {
            "source_snapshot": "sources/lifecycle-repair-web.json",
            "repairs": [
                {
                    "cohort_id": "RE",
                    "source_ticker": "EG",
                    "episode": "EP_EVEREST_CONTINUING_COMMON",
                    "class": "common stock",
                    "rename_effective": "2023-07-10",
                    "action": "whole-episode same-vintage EG source",
                    "source": (
                        "https://investors.everestglobal.com/new"
                        "s/news-details/2023/Everest-to-Rebrand-"
                        "Company-Name-and-NYSE-Ticker-to-Reflect"
                        "-its-Evolution-Global-Growth-and-Divers"
                        "ification-Strategy/default.aspx"
                    ),
                    "rows_before": int((bars.symbol == "RE").sum()),
                    "rows_after": len(replacement),
                    "original_source_preserved": True,
                    "economic_adjustment_basis": "vendor all proxy",
                },
                {
                    "cohort_id": "FOX",
                    "episode": "CUSIP35137L204_FOX_CLASS_B",
                    "historical_class_B": "new Fox Corporation",
                    "earliest_regular_session": "2019-03-19",
                    "excluded_history_rows": int(
                        ((revised.symbol == "FOX") & (~revised.episode_history_candidate)).sum()
                    ),
                    "old_class_B_cusip": "90130A200 then 90130A408 / TFCF",
                    "not_cohort_removal": True,
                    "source": "https://www.nasdaqtrader.com/TraderNews.aspx?id=dtn2019-05",
                },
                {
                    "cohort_id": "PBCT",
                    "episode": "PBCT_COMMON_TERMINATING_20220401",
                    "old_class": "common par USD0.01",
                    "successor_class": "MTB common par USD0.50",
                    "terminal_effective_date": "2022-04-01",
                    "shares_per_eligible_old_common": 0.118,
                    "new_asset": "MTB_common_receivable",
                    "cash_in_lieu_fractional_shares": True,
                    "actual_delivery_at": None,
                    "spendable_at": None,
                    "terminal_value_return": None,
                    "unresolved_return_is_not_zero": True,
                    "retained_in_original_cohort": True,
                    "raw_endpoint_needed": "PBCT final raw close and first subsequent MTB raw mark",
                    "all_adjusted_successor_not_multiplied_by_raw_exchange_ratio": True,
                    "source": (
                        "https://www.sec.gov/Archives/edgar/data"
                        "/36270/000119312522094296/d349120d8k.ht"
                        "m"
                    ),
                },
            ],
            "benchmarks_read": ["SPY", "BIL", "XLF", "XLI"],
            "new_market_requests": 0,
            "model_fits": 0,
            "updates": 0,
            "independent_input_acceptance": False,
        },
    )
    print(
        json.dumps(
            {
                "RE_old_rows": int((bars.symbol == "RE").sum()),
                "RE_connected_rows": len(replacement),
                "extra_local_files": len(receipt),
                "FOX_before_reuse_retained_separate": True,
                "PBCT_actual_stock_right": 0.118,
                "economic_ready": False,
            }
        )
    )


if __name__ == "__main__":
    main()
