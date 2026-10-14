"""Final independent receipt; all actual reviewer failures remain charged."""
import hashlib
import json
import math
import os
import re
import resource
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

resource.setrlimit(resource.RLIMIT_CPU, (12, 15))
assert os.sched_getaffinity(0) == {0}
P = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text())


def bind(path):
    path = Path(path)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


for f in ("independent-final-hash-verification.json", "independent-final-accounts-verification.json", "independent-final-statistics-verification.json"):
    assert read(P / f)["status"] == "pass"
matrix = pd.read_parquet(P / "economic/results/continuous-funded-NAV.parquet")
dsr = read(P / "economic/results/descriptive-DSR.json")
assert dsr["effective_trials"] == 4453
for name in matrix:
    v = matrix[name].to_numpy()
    given = dsr["results"][name]
    if not np.isfinite(v).all() or (v <= 0).any():
        assert given["probability"] is None
        continue
    ret = v[1:] / v[:-1] - 1
    sd = np.std(ret, ddof=1)
    if sd == 0:
        assert given["probability"] is None
        continue
    sr = ret.mean() / sd
    z = (ret - ret.mean()) / sd
    skew, kurt = np.mean(z**3), np.mean(z**4)
    normal = NormalDist()
    n = 4453
    hurdle = (.5772156649015329 * normal.inv_cdf(1 - 1/n) + (1-.5772156649015329) * normal.inv_cdf(1 - 1/(n*math.e))) / math.sqrt(len(ret)-1)
    denominator = math.sqrt(max(1-skew*sr+(kurt-1)/4*sr**2, np.finfo(float).eps))
    value = normal.cdf((sr-hurdle)*math.sqrt(len(ret)-1)/denominator)
    assert abs(value-given["probability"]) < 1e-12, name

profiles = ["independent-final-hash-resource.txt", "independent-final-accounts-resource-attempt1.txt", "independent-final-accounts-resource.txt", "independent-final-statistics-resource-attempt1.txt", "independent-final-statistics-resource.txt", "independent-final-metadata-resource-attempt1.txt", "independent-final-metadata-resource.txt", "independent-final-seal-resource-attempt1.txt"]
jobs = []
for name in profiles:
    text = (P / name).read_text()
    used = sum(float(re.search(k + r": ([0-9.]+)", text)[1]) for k in [r"User time \(seconds\)", r"System time \(seconds\)"])
    jobs.append({"profile": bind(P / name), "actual_inclusive_CPU": round(used, 2), "RSS_KiB": int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)[1])})
actual = round(sum(j["actual_inclusive_CPU"] for j in jobs), 2)
charge = round(actual + 10, 2)
assert charge < 300
resource_receipt = {"pool": "Original unique HF cumulative36000 completion envelope", "job_id": "independent-complete-result-review-01", "reserved_CPU": 300, "measured_inclusive_CPU_before_successful_seal": actual, "nonzero_small_reads_writes_successful_seal_handoff_allowance_CPU": 10, "successful_seal_profile_included_in_allowance_not_added_twice": True, "charge_CPU": charge, "unused_reservation_CPU": round(300-charge, 2), "fresh_memory_MiB": 400, "CPU_affinity": [0], "max_RSS_KiB": max(j["RSS_KiB"] for j in jobs), "profiles": jobs, "reviewer_failures": ["Controlled first scalar-comparison audit interruption,117.36CPU retained.", "Optimized audit completed all159ledger/800diagnostic loops then failed on reviewer profitable-ID-list versus count metadata assumption; metadata-only recovery, no repeat numeric scan.", "Metadata category fallback corrected: linear validation rows do not contain explicit state/status.", "R2 zero-cancellation absolute tolerance changed to2e-13; loss/SE checks unchanged.", "Reviewer DSR checker initially omitted kurtosis coefficient1/4; corrected here to exact approved equation. No author output changed."], "settlement_owner": "7b109880 serially settles existing unique reservation; reviewer did not change ledger", "base_author_closed_CPU": 12103.56, "projected_cumulative_after_review_CPU": round(12103.56+charge, 2), "new_source_market_fit_prediction_order_paid_calls": 0, "Martin_or_old500_pool_used": False}
(P / "independent-complete-result-resource-accounting.json").write_text(json.dumps(resource_receipt, indent=2) + "\n")
files = ["complete-result-review-request.json", "complete-costed-final-manifest.json", "complete-costed-result.json", "complete-costed-result.md", "implementation-manifest.json", "independent-implementation-review.json", "independent-host-clock-diff-review.json", "independent-plan-review.json", "independent-final-hash-verification.json", "independent-final-accounts-verification.json", "independent-final-statistics-verification.json", "independent_verify_final_accounts.py", "independent_verify_final_accounts-attempt1.py", "independent_verify_final_statistics.py", "independent_verify_final_statistics-attempt1.py", "independent_seal_final_review.py", "complete-costed-author-report-QA.json", "completion-resource-ledger.json", "independent-complete-result-resource-accounting.json"]
bindings = {f: bind(P/f) for f in files}
assert bindings["complete-costed-final-manifest.json"]["sha256"] == "9333c0439f0dffaf29698ef703bc46e0be463d4f225f292a8ef9131cc641b258"
review = {
    "schema_version": 1, "task_id": "DAY3-HF-FACTOR-RETURN", "author": "7b109880-ac40-447e-b2a6-f0ed1266ebac", "reviewer": "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3", "at_utc": datetime.now(timezone.utc).isoformat(),
    "verdict": "accept_complete_conditional_result", "required_corrections": [],
    "scope": "Complete original20 forecasts/800fractional diagnostics/100independent20k model books/40independent4k host model books plus controls; interpretation, multiplicity and resource acceptance, no new plan or economic allocation.",
    "bindings": bindings,
    "verification": {
        "fresh_final_output_and_model_hashes": {"files": 1477, "unique_paths": 1477, "bytes": 1580204115, "mismatches": 0},
        "source300_HAR_and_market361": "Prior independent acceptance inherited; no new large input hash or value scan.",
        "physical": "All159persisted ledgers: daily cash/unsettled/dividend receivable balances, split share/fractional rights, orderq-before/after, fees, affordability/no-fill and raw-closeNAV equation independently checked. No author run_funded or model calls.",
        "matrices": "1259x120 standalone and817x92host paths checked; terminal/CAGR/netstdSharpe/maxDD/underwater/exBIL availability verified. All standalone/host SPYbetas recomputed; drifting16k plus independent4k identity checked.",
        "fractional": "All800npz metrics, gross/net fee+borrow and samebook overnight/intraday identities, event/no-fill counts and totalfees checked; no night-off strategy invented.",
        "forecast_and_inference": "Stored20predictions + small acceptedlabels/clock: full/17yearAll/CtsR2/RMSE, common6contrasts93297windows4280days, HAC5/MDE and all2000block20bootstraps/jointmaxT recomputed for both targets. No fit or fresh model inference.",
        "multiplicity": "3513unique logical modelconfigs/3610rows;96HGBcompletedprefixes/96started+1continuation;272linear+17mean+96pickle=385files.3417linear rows labelled by their record role, not claimed explicitstate.120DSRdescriptive calculations verified at4453declared model+economic exposures; not an empirically independent-trial estimate.",
        "verification_recovery": "All physical/diagnostic numerical loops completed before reviewer metadata exception. Exact failure/profile preserved, metadata-only recovery passed without a third full numerical run. Neither failed jobs nor partial outputs are relabelled successful. See detailed receipt and resource explanations."
    },
    "decisive_findings": [
        "All20 primary20bp physical accounts lose capital and trail matchedSPY/BIL20/cash. Best observedHGB_IDX terminal8853.082298400008 from20000, CAGR approximately-15.065%; this is retrospective description, not selection.",
        "0/1bp positive diagnostic and somephysical returns remain real conditional outputs.1bp best physicalSTALE control about5.31%CAGR does not establish substantial deployable broad-information alpha. Thresholds and funded orders change with cost, so cost sensitivity is not fixed-order fee subtraction.",
        "All80model/host/cost comparisons have lower terminal andnetSharpe than cash/SPY. Versusmarketonly20 preserve2terminalup/36equal/2down and3SRup/36equal/1down;40all40equal. Small exceptions do not demonstrate useful net contribution.",
        "Allhost4kBIL20/40 and20kBIL0/1/5/40 CIL-dependent metrics remainNA;20kBIL20 is valid.40bpSPY initialcash-gap buy neverfilled, so20000terminal is cash, not successful buyhold. No lot adjustment to avoid unknownrights.",
        "PLSwidth andfullHGB algorithm do not passjointmaxT. INV deterioration andstale significance are measurement/timeliness evidence in this conditionalsource, not proof of all upstream contamination or failure of the original mechanism. HGBmarket-only attribution was not tested.",
        "Some cost-panel maxima are ties to numericalprecision; different deterministic listings can name different tiedmodels. This doesnotchange economic conclusions or allocate a winner."
    ],
    "forensics": {"lookahead_check": "warning", "future_leak_check": "warning", "overfit_risk": "high", "reason": "Upstream full-day cleaning/interpolation/futurefactor screening andcurrentvintage/PIT unresolved. Causal reviewedtraining/labels/consumer cannot certify upstreamPIT. Allhistoryseen; no2026/OOS/privateaccount/source-native15m replication claim.", "DSR": "Verified descriptive IID-null with skew/kurtosis; dependence not adjusted. PBO/SPA N/A, notzero; no promotion evidence.", "existing_artifacts": [bind(Path("reports/harness/forensics/conditional_hf_factor_method-backtest-forensics.json")), bind(Path("reports/harness/forensics/conditional_hf_factor_method-backtest-forensics.md"))], "reference_fill_and_cash_proxy_not_broker_proof": True},
    "investment_judgment": {"decision": "stop_current_application_defer_deployment", "accepted": True, "source_full_mechanism_refuted": False, "reason": "Complete after-cost funded and matchedhost evidence doesnotjustify currentpublic-input reconstruction/cash-proxy deployment. Do not rescue by choosinglowcost/seenwindow/parameters afterresults. Native15m/PITformation and credible lowfriction/funding evidence could motivate a separately defined futuretest, not additional work authorizedhere.", "workflow_pass": "complete_conditional_research_only", "research_pass": False, "ml_contribution_pass": False, "paper_ready_pass": False, "promotion_eligible": False, "new_allocation": 0},
    "native_resource_limits": "Originalaccounts750.98 andsamePID700-to1200reservation preserved; M3failednative147.73+1 andhostcompletion199.69+1 retained. Accepted prebacktest hostguard andcompleteoutputs do not claim post-acceptance finalnative sealing already occurred; originalowner completes that route once.",
    "resource": resource_receipt, "delivery": "Direct originalowner; noRootintermediate notification."
}
(P / "independent-result-review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"review": bind(P / "independent-result-review.json"), "actual_CPU": actual, "charge_CPU": charge, "unused_review_reservation": 300-charge}))
