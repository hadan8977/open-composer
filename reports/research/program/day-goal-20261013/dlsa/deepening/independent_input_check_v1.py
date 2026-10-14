import hashlib
import json
import resource
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path("/root/codex-test/open-composer")
sys.path.insert(0, str(ROOT))

from open_composer.market_sessions import us_equity_session_dates  # noqa: E402
from open_composer.research.features.price_hygiene import (  # noqa: E402
    is_ghost_bar,
    sanitize_price_matrices,
)

P = ROOT / "reports/research/program/day-goal-20261013/real-market-input-bridge/v1"
D = ROOT / "reports/research/program/day-goal-20261013/dlsa/deepening"
start = time.process_time()


def sha(p):
    with p.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


m = json.loads((P / "package-manifest.json").read_text())
assert (
    sha(P / "package-manifest.json")
    == "3282cbd39ebb8480b9a8b1119c37329d711ab9a05d9a298462922088a266fb03"
)
for r in m["files"]:
    p = (P / r["path"]).resolve()
    assert p.is_relative_to(P)
    assert p.stat().st_size == r["bytes"] and sha(p) == r["sha256"], p
for r in json.loads((P / "inherited-binding-verification.json").read_text())["bindings"]:
    assert sha(ROOT / r["path"]) == r["sha256"], r["path"]
raw = pd.read_parquet(P / "selected-bars.parquet")
obs = pd.read_parquet(P / "observations.parquet")
assert len(raw) == len(obs) == 254
cols = ["symbol", "timestamp", "open", "high", "low", "close", "volume", "trade_count", "vwap"]
for _, r in raw.iterrows():
    assert (
        hashlib.sha256(
            json.dumps({k: r[k] for k in cols}, sort_keys=True, default=str).encode()
        ).hexdigest()
        == r.source_row_sha256
    )
assert is_ghost_bar(raw).to_numpy().tolist() == obs.ghost_bar.to_numpy().tolist()
assert int(obs.ghost_bar.sum()) == 43
assert not obs.raw_price_semantics_accepted.any()
assert obs.episode_id.nunique() == 7
atvi = obs[obs.case_id.eq("terminal_ATVI_2023")].set_index("bar_session")
assert atvi.loc["2023-10-12", "close"] == 94.42 and not atvi.loc["2023-10-12", "ghost_bar"]
assert atvi.loc["2023-10-13", "ghost_bar"]
elv = obs[obs.case_id.eq("rename_ELV_2022") & obs.bar_session.eq("2022-06-27")].set_index("symbol")
assert elv.loc["ANTM", "close"] == 482.58 and elv.loc["ELV", "close"] == 452.24
assert elv.volume.nunique() == 1
ww = obs[obs.case_id.eq("cancel_reissue_WW_2025") & ~obs.ghost_bar].copy()
ww.index = pd.to_datetime(ww.bar_session)
idx = pd.DatetimeIndex(us_equity_session_dates(date(2025, 5, 1), date(2025, 7, 11)))
c = ww[["close"]].reindex(idx)
o = ww[["open"]].reindex(idx).rename(columns={"open": "close"})
pre, _, _ = sanitize_price_matrices(c.loc[:"2025-05-09"], o.loc[:"2025-05-09"])
full, _, _ = sanitize_price_matrices(c, o)
assert pre.loc["2025-05-09", "close"] == 0.37 and pd.isna(full.loc["2025-05-09", "close"])
feat = [json.loads(x) for x in (P / "eligibility-feature-clock.jsonl").read_text().splitlines()]
lab = [json.loads(x) for x in (P / "label-clock-requests.jsonl").read_text().splitlines()]
assert len(feat) == len(lab) == 241
assert all(
    not r["eligible_under_APP"]
    and r["Ret_D1"] is None
    and r["Rf"] is None
    and r["raw_dollar_ADV20"] is None
    for r in feat
)
assert all(
    r["gross_mid_mid_label"] is None
    and not r["label_matured"]
    and r["mature_residual_count"] == r["mature_PCA_count"] == 0
    for r in lab
)
h = [r for r in lab if r["decision_session"] == "2025-07-03"][0]
assert (
    h["decision_cutoff_utc"] == "2025-07-03T17:00:00+00:00"
    and h["entry_window_start_utc"] == "2025-07-07T13:45:00+00:00"
)
a = {r["id"]: r for r in json.loads((P / "lifecycle-contract.json").read_text())["actions"]}
assert (
    a["WW_CANCEL_AND_DISTRIBUTE"]["new_shares_to_existing_equity_interests_total"] == 900000
    and a["WW_CANCEL_AND_DISTRIBUTE"]["old_to_new_individual_ratio"] is None
)
assert a["AAPL_DIVIDEND"]["ex_date"] is None and a["AAPL_DIVIDEND"]["cash_per_old_share"] == 0.82
text = json.loads((P / "terminal-web-snapshots.json").read_text())
assert "$95.00" in text and "900,000" in text and "10,000,000" in text
text = json.loads((P / "primary-web-snapshots.json").read_text())
assert "$23.75" in text
v = {
    "original_manifest_sha256": sha(P / "package-manifest.json"),
    "package_files_checked": len(m["files"]),
    "inherited_bindings_checked": 11,
    "source_row_hashes_recomputed": 254,
    "episodes": 7,
    "ghosts_preserved": 43,
    "clock_rows": 241,
    "accepted_APP_features": 0,
    "mature_labels": 0,
    "WW_prefix_counterexample_independently_recomputed": True,
    "ATVI_ELV_case_values_checked": True,
    "WW_rights_and_primary_cash_snapshots_checked": True,
    "economic_computations": 0,
    "source_downloads": 0,
    "CPU_seconds": time.process_time() - start,
    "max_RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    "pending_ordinary_fix": "AAPL payable!=economicrightsexdate "
    "and known0.82oldsharebasis in derivedactionledger",
}

print(json.dumps(v))
