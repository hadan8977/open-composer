# ruff: noqa: E402, E501
"""T-20261004-56: compare sue_8k_visible old (backup) vs new, and a controlled join (same left, old vs new right). Read-only; writes sue_compare.json next to this file."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import build_sue_8k_visible as b
import pandas as pd

OUT = Path(__file__).parent / "sue_compare.json"
old = pd.concat(
    pd.read_parquet(p)
    for p in sorted((ROOT / "data/live/backup-features-20261004/sue_8k_visible").glob("*.parquet"))
)
new = pd.concat(
    pd.read_parquet(p) for p in sorted((ROOT / "data/features/sue_8k_visible").glob("*.parquet"))
)


def rank(df):
    df = df.sort_values(["symbol", "value", "trade_date"]).copy()
    df["k"] = df.groupby(["symbol", "value"]).cumcount()
    return df


m = rank(old).merge(
    rank(new), on=["symbol", "value", "k"], how="outer", suffixes=("_old", "_new"), indicator=True
)
both = m[m._merge == "both"]
chg = both[both.trade_date_old != both.trade_date_new]
res = {
    "old_rows": len(old),
    "new_rows": len(new),
    "paired_rows": len(both),
    "only_old": int((m._merge == "left_only").sum()),
    "only_new": int((m._merge == "right_only").sum()),
    "paired_trade_date_changed": len(chg),
}
# controlled: same left, old backup earnings table as right
left = b.load_left("1000MB")
bk = ROOT / "data/live/backup-features-20261004/earnings_events/*.parquet"
import duckdb

con = duckdb.connect()
con.execute("SET memory_limit='600MB'")
r = con.execute(
    f"SELECT CAST(cik AS BIGINT) cik, acceptance_utc FROM read_parquet('{bk}', union_by_name=true) WHERE items LIKE '%2.02%' AND acceptance_utc IS NOT NULL"
).df()
r["acceptance_utc"] = pd.to_datetime(r["acceptance_utc"], utc=True)
r["usable_session"] = pd.to_datetime(
    r["acceptance_utc"].map(b.usable_session_for_acceptance)
).astype("datetime64[ns]")
old_join = b.build_join(left, r[["cik", "usable_session"]].dropna())
new_join = b.build_join(left, b.load_right("600MB"))
mm = rank(old_join).merge(
    rank(new_join),
    on=["symbol", "value", "k"],
    how="outer",
    suffixes=("_old", "_new"),
    indicator=True,
)
bo = mm[mm._merge == "both"]
res["controlled_old_join_rows"] = len(old_join)
res["controlled_new_join_rows"] = len(new_join)
res["controlled_paired"] = len(bo)
res["controlled_only_old"] = int((mm._merge == "left_only").sum())
res["controlled_only_new"] = int((mm._merge == "right_only").sum())
res["controlled_trade_date_changed"] = int((bo.trade_date_old != bo.trade_date_new).sum())
res["old_join_equals_stored_old_table"] = bool(
    rank(old_join)[["symbol", "value", "trade_date"]]
    .reset_index(drop=True)
    .equals(rank(old).reset_index(drop=True)[["symbol", "value", "trade_date"]])
)
OUT.write_text(json.dumps(res, indent=1, default=str))
print(json.dumps(res, indent=1, default=str))
