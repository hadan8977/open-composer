"""Bound/source/causal-clock checks on the actual packet, never an acceptance review."""

import hashlib
import json
import resource
import time
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]


def read(name):
    return json.loads((OUT / name).read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    started = time.monotonic()
    checks = []
    for record in read("inherited-binding-verification.json")["bindings"]:
        assert sha(ROOT / record["path"]) == record["sha256"], record["path"]
    checks.append("all11 inherited source bindings unchanged")
    for record in read("price-intake.json")["inputs"]:
        assert sha(ROOT / record["path"]) == record["sha256"]
    checks.append("all12 selected price-value files match SHA")
    for record in read("records/submission-evidence.json")["members"]:
        member = record["source"].split("::")[1]
        assert sha(OUT / "records" / member) == record["member_sha256"]
    checks.append("six exact SEC member payload hashes match")
    for record in read("public-source-ledger.json")["direct_requests"]:
        if "snapshot" in record:
            assert sha(OUT / record["snapshot"]) == record["sha256"]
            assert record["usable_snapshot"] == (record["http_status"] == 200)
    checks.append("HTTP403 snapshots retained and never claimed successful")
    source_cols = [
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trade_count",
        "vwap",
    ]
    bars = pd.read_parquet(OUT / "selected-bars.parquet")
    for _, row in bars.iterrows():
        payload = {k: row[k] for k in source_cols}
        assert (
            hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
            == row.source_row_sha256
        )
    checks.append("all254 row hashes recomputed from immutable source columns")
    observations = pd.read_parquet(OUT / "observations.parquet")
    assert len(observations) == len(bars) == 254
    assert not observations.raw_price_semantics_accepted.any()
    assert int(observations.ghost_bar.sum()) == 43
    old = observations.loc[observations.case_id == "reused_SNOW_old_2017"]
    new = observations.loc[observations.case_id == "reused_SNOW_new_2020"]
    assert old.episode_id.nunique() == new.episode_id.nunique() == 1
    assert old.episode_id.iloc[0] != new.episode_id.iloc[0]
    ww = observations.loc[observations.case_id == "cancel_reissue_WW_2025"]
    assert ww.episode_id.nunique() == 2
    assert ww.loc[ww.ghost_bar, "episode_id"].eq("EP105319_OLD_COMMON").all()
    checks.append("reuse/reissue episodes split;43 ghost records retained but unpriced")
    rows = [
        json.loads(x) for x in (OUT / "eligibility-feature-clock.jsonl").read_text().splitlines()
    ]
    labels = [json.loads(x) for x in (OUT / "label-clock-requests.jsonl").read_text().splitlines()]
    assert len(rows) == len(labels) == 241
    columns = ["Ret_D1", "Ret_W1", "STD_W1", "z_D1", "z_W1", "z_STD", "m_D1", "m_W1", "m_STD", "Rf"]
    assert all(not r["eligible_under_APP"] and all(r[k] is None for k in columns) for r in rows)
    assert all(r["gross_mid_mid_label"] is None and not r["label_matured"] for r in labels)
    holiday = next(
        r
        for r in labels
        if r["case_id"] == "cancel_reissue_WW_2025" and r["decision_session"] == "2025-07-03"
    )
    assert holiday["decision_cutoff_utc"] == "2025-07-03T17:00:00+00:00"
    assert holiday["entry_window_start_utc"] == "2025-07-07T13:45:00+00:00"
    assert holiday["exit_window_end_utc"] == "2025-07-08T13:45:05+00:00"
    split = next(
        r
        for r in labels
        if r["case_id"] == "split_AAPL_2020" and r["decision_session"] == "2020-08-31"
    )
    assert split["split_like_trigger_excluded"]
    assert all(
        r["required_residual_history"] == 30
        and r["required_PCA_history"] == 252
        and r["policy_window_calendar_years"] == 8
        for r in labels
    )
    checks.append(
        "holiday/early-close/DST quote windows and30/252/8year clocks; no invented labels"
    )
    key = read("key-case-evidence.json")
    assert key["WW_future_erasure"]["same_day_prefix_sanitized_close"] is not None
    assert key["WW_future_erasure"]["full_future_history_sanitized_close"] is None
    actions = {x["id"]: x for x in read("lifecycle-contract.json")["actions"]}
    assert actions["ATVI_CASH_CONVERSION"]["cash_entitlement_per_eligible_share"] == 95
    assert (
        actions["WW_CANCEL_AND_DISTRIBUTE"]["new_shares_to_existing_equity_interests_total"]
        == 900000
    )
    assert actions["WW_CANCEL_AND_DISTRIBUTE"]["old_to_new_individual_ratio"] is None
    assert all(
        not x["terminal_claim_removed"] and x["actually_spendable_at"] is None
        for x in read("held-asset-action-ledger.json")["entries"]
    )
    checks.append(
        "terminal claims stay pending; no zeroing, last-price payoff or automatic cash settlement"
    )
    receipt = read("intake-receipt.json")
    assert receipt["max_rss_kib"] < 900 * 1024
    assert receipt["child_max_rss_kib"] < 900 * 1024
    public = read("public-source-ledger.json")
    assert public["request_units_counted"] <= 24
    assert public["byte_budget_charge"] <= 16 * 1024 * 1024
    checks.append("low-memory repair receipt and cumulative new-source allowance checked")
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result = {
        "verification_pass": True,
        "independent_input_acceptance": False,
        "APP_input_ready": False,
        "economic_execution_admitted": False,
        "checks": checks,
        "cpu_seconds": usage.ru_utime + usage.ru_stime,
        "wall_seconds": time.monotonic() - started,
        "max_rss_kib": usage.ru_maxrss,
    }
    (OUT / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
