"""Seal source/input/resource evidence; never fit or compute a trading return."""

import datetime
import hashlib
import json
import pathlib
import re

P = pathlib.Path(__file__).resolve().parent
ROOT = P.parents[4]
PREVIOUS = P.parent / "primary-return-breadth"
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()
if (P / "source-input-resource-accounting.json").exists():
    NOW = json.loads((P / "source-input-resource-accounting.json").read_text())["as_of_utc"]


def binding(path):
    path = pathlib.Path(path)
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def write(name, value):
    path = P / name
    raw = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text() == raw:
            return binding(path)
        raise FileExistsError(f"Preserve the existing artifact before changing: {name}")
    path.write_text(raw)
    return binding(path)


ledger = json.loads((P / "source-request-ledger.json").read_text())
assert [x["unit"] for x in ledger] == list(range(1, 33))
assert sum(x.get("bytes", 0) for x in ledger) == 37_252_859
for row in ledger:
    if "path" in row:
        actual = binding(row["path"])
        assert actual["sha256"] == row["sha256"]
        assert actual["bytes"] == row["bytes"]

qa = json.loads((P / "actual-one-month-input-QA.json").read_text())
assert qa["rows"] == 8494 and qa["columns"] == 272
assert qa["model_fits"] == 0 and qa["economic_runs"] == 0
assert binding(P / "inputs/199601.parquet")["sha256"] == qa["SHA256"]
sizes = json.loads((P / "raw-input-size-evidence.json").read_text())
projection = json.loads((P / "input-projection-resource-options.json").read_text())
resource_rows = []
for path in sorted(P.glob("*resource.txt")):
    raw = path.read_text()
    user = re.search(r"User time \(seconds\): ([0-9.]+)", raw)
    system = re.search(r"System time \(seconds\): ([0-9.]+)", raw)
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", raw)
    exit_code = re.search(r"Exit status: (\d+)", raw)
    resource_rows.append({
        **binding(path),
        "CPU_coreseconds": round(float(user[1]) + float(system[1]), 6),
        "peak_RSS_KiB": int(rss[1]),
        "exit_code": int(exit_code[1]),
    })
known_cpu = round(sum(r["CPU_coreseconds"] for r in resource_rows), 6)
assert known_cpu == 24.94

resources = write("source-input-resource-accounting.json", {
    "schema_version": 1, "task_id": "DAY3-HF-FACTOR-RETURN", "as_of_utc": NOW,
    "source_units_used": 32, "source_unit_cap": 32,
    "source_known_direct_response_bytes": 37_252_859,
    "source_direct_response_byte_cap": 67_108_864,
    "source_known_byte_headroom": 29_856_005,
    "web_transfer_bytes": "unknown; no zero-byte assumption",
    "byte_headroom_does_not_create_request_authorization": True,
    "actual_complete_month_download_bytes": 22_194_147,
    "actual_range_reads_bytes": 206_877,
    "known_HF_source_input_preparation_CPU_coreseconds": known_cpu,
    "known_HF_source_input_preparation_peak_RSS_KiB": max(r["peak_RSS_KiB"] for r in resource_rows),
    "resource_receipts": resource_rows,
    "failed_preparation_included": [r["path"] for r in resource_rows if r["exit_code"] != 0],
    "additional_preparation_CPU": "nonzero unmetered: PDF conversions, source reading/parsing/hash/setup and packet creation; not included in the measured subtotal; original preparation reservation retained",
    "inherited": {
        "old_source_scopes_used_sealed": [40, 40],
        "market_requests_already_used": 9, "market_bytes_already_used": 4_120_032,
        "unique_market_requests_remaining": 15, "unique_market_bytes_remaining": 12_657_184,
        "economic_initial_cap_coreseconds": 7200,
        "old_author_economic_measured_coreseconds": 163.31,
        "old_result_review_reserved_coreseconds": 30,
        "old_known_measurement_including_peer": 186.164505,
        "unique_economic_remaining_coreseconds": 7006.69,
        "old_preparation_reservation_coreseconds_retained": 500,
        "no_reservation_release_or_reset": True,
    },
    "new_HF_market_requests": 0, "new_HF_market_bytes": 0,
    "new_HF_economic_coreseconds": 0, "new_HF_model_fits": 0,
    "new_HF_economic_runs": 0, "new_paid_USD": 0,
    "Hadan_or_cloud_used": False,
})

main = binding(PREVIOUS / "sources/hf_zoo.pdf")
appendix = binding(P / "sources/hf-zoo-appendix.pdf")
construction = binding(P / "sources/factor-construction-paper.pdf")
primary = {
    "main_paper": main, "main_text": binding(P / "hf-zoo-read.txt"),
    "author_appendix": appendix, "appendix_text": binding(P / "sources/hf-zoo-appendix.txt"),
    "construction_paper": construction,
    "construction_text": binding(P / "sources/factor-construction-paper.txt"),
    "author_data_page": binding(P / "sources/author-data-page.html"),
    "author_data_links": binding(P / "sources/author-data-page.links.json"),
    "public_file_inventory": binding(P / "sources/factor-by-date-folder.inventory.json"),
    "actual_complete_month": binding(P / "inputs/199601.parquet"),
    "actual_complete_month_QA": binding(P / "actual-one-month-input-QA.json"),
    "actual_clock_QA": binding(P / "actual-clock-QA.json"),
    "metadata_QA": binding(P / "parquet-metadata-QA.json"),
    "size_evidence": binding(P / "raw-input-size-evidence.json"),
    "projection_evidence": binding(P / "input-projection-resource-options.json"),
    "printed_equations_image": binding(P / "source-equations-6-7.png"),
    "publisher_actual_response": binding(P / "sources/publisher-supplements.html"),
    "official_linked_GitHub_inventory": binding(P / "sources/author-github-repos.json"),
    "source_request_ledger": binding(P / "source-request-ledger.json"),
    "resource_accounting": resources,
    "brief": binding(P / "brief.md"),
}

fidelity = write("source-fidelity-map.json", {
    "schema_version": 1, "task_id": "DAY3-HF-FACTOR-RETURN", "as_of_utc": NOW,
    "bindings": primary,
    "source_identity": "Aleti/Bollerslev/Siggaard, Management Science 2025, Intraday Market Return Predictability Culled from the Factor Zoo",
    "source_url": "https://public.econ.duke.edu/~boller/Papers/MS_2025.pdf",
    "decisive_findings": [
        {"id": "F1", "location": "Main Sections2/3/5; construction paper data/portfolio appendix", "source_fact": "272 published portfolios consist of218 characteristic factors,48industry portfolios and6FF factors. Target is broad FF value-weighted common-stock market; SPY is the traded proxy. Direct ETF refitting is a different experiment and underperforms in OA.5.1.", "actual_input_fact": "Public199601 has65CZ+153JKP+6FF+48industry=272float64 return columns. Counts and named source keys agree; definitions, units, original vintage, leg aggregation and then-visible weights are not certified.", "claim_limit": "Presence of the full column count proves useful actual author data, not original15min source/PIT admission."},
        {"id": "F2", "location": "Main3.2/AppendixA; OA.2", "source_fact": "Exante jump threshold(alpha,varpi)=(3.5,.49), variance=(pi/2)*26*EWMA(abs(r[i-1]*r[i-2]),halflife26)*past-only time-of-day term. Same-day end-of-day BV is explicitly rejected for downstream prediction. Regime/jump classification of a return becomes available after that return, never before.", "open_point": "Exact time-of-day history/init, irregular sessions and continuous-target zeroing versus deletion need code/verified original packet. Main footnote10 indicator weighting and illustrative AR deletion cannot be silently conflated.", "claim_limit": "No future hold-window/jump filter; all realized OOS returns must remain in account evidence."},
        {"id": "F3", "location": "Main3.2/3.4; OA.3/OA.7.2", "source_fact": "HAR predictors use lagged15min,1h and1day factor information; standardization is train-only. Expanding80/20 train/validation, annual2004–2020test. Forecasting data begins2000 in appendix; nonlinear FNN/RF/GBRT refit every5years, linear models annually. Ensemble equally averages9models excludingOLS.", "open_point": "Original pre2000 warmup, label maturity and daily/overnight feature assembly must be dereferenced, not inferred from calendar years. No new model has been fitted.", "claim_limit": "All published/test dates are seen research evidence; no untouched OOS claim."},
        {"id": "F4", "location": "Main printed equations6/7 page7739; OA.5.2", "source_fact": "The retained PDF image prints a positive half-spread threshold in both greater-than and less-than branches. Prose describes a sufficient-signal hold region.", "open_point": "Actual author implementation must resolve the apparent mismatch. A symmetric plus/minus deadband may be a declared future application convention; it cannot be silently called exact source.", "claim_limit": "No sufficient-strategy source replication or frozen orders until this ambiguity is resolved."},
        {"id": "F5", "location": "Main5.2 equations9/11/12 andTable4/5; OA.7", "source_fact": "Source quoted-cost uses TAQ time-weighted quoted spreads, lagged halfspread for signals and current halfspread times turnover for cost;2%annual borrow modeled. Cash earns zero in portfolio weights. Overnight target+1 and opening/eod rebalances affect turnover. Published adjusted SR uses original gross second moment volatility, not netreturn standard deviation.", "claim_limit": "Published19.89%intraday annual arithmetic mean/1.37sourceSR and26.73%overnight-inclusive arithmetic mean are not CAGR or verified20k funded return. Frozen20bp account gate stays distinct; no20bp-only mechanism rejection."},
        {"id": "F6", "location": "Main6/7 andTable5; OA.6", "source_fact": "Risk/liquidity key factors include JKPturnover126d,zero-trades21d/252d,ivolCAPM252d andCZtailrisk. Their selection is ex post. Simple single-leg timing sourceSR0.50 remains much below fullensemble1.37. PLS sourceSSign1.21 versus ensemble1.36(Table5), while SPositivePLS0.93; no estimator is predetermined to win.", "claim_limit": "Five keys plus market offer a source-supported adaptation hypothesis, not a faithful replacement for fullzoo information/model. Do not use it merely to fit transfer caps."},
        {"id": "F7", "location": "Construction paper data/portfolio appendices and actual199601 clock", "source_fact": "Construction uses CRSP sharecodes10/11, PERMNO/TAQ mapping, characteristic portfolios, lagged value weights, CRSP opening/closing and delisting conventions. Some TAQ cleaning uses full-day statistics and factor availability screening is retrospective.", "actual_input_fact": "Datetime timezone is absent. Jan8 has283 rows through14:12 rather than391 nominal labels;108later labels unobserved. Cause not independently verified, no filling/deleting. Public1min file lastmodified2024Feb6.", "claim_limit": "Source current-vintage mathematical research can remain useful; exact then-known/production availability is unproved. Long-minus-short1min returns cannot in general be compounded to original15min leg-return spreads without construction evidence."},
    ],
    "economics_computed": False,
})

decision = {
    "schema_version": 1, "task_id": "DAY3-HF-FACTOR-RETURN", "as_of_utc": NOW,
    "author": "7b109880-ac40-447e-b2a6-f0ed1266ebac",
    "independent_reviewer": "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3",
    "review_classification": "Complete primary-source/input/material-resource decision; not an executable economic plan approval",
    "decision_proposed": "preserve_HF_factor_information_mechanism_require_original15m_code_or_complete_forecast_packet_before_further_resource_allocation",
    "bindings": {**primary, "source_fidelity_map": fidelity},
    "scientific_question": "Can lagged high-frequency cross-sectional factor information predict the broadmarket sufficiently to generate substantial absolute20k account return after actual timing, spread, short/funding and overnight costs, beyond matched market-only and same-information simple models?",
    "why_direction_is_still_worthwhile": "A distinct cross-sectional lead/lag information mechanism with published large model/cost gains. Lowrisk/liquidity/tail-risk information is economically specified. Fullensemble information and execution depth remain unresolved here; source figures are neither our performance nor high absolute account return proved.",
    "actual_work_completed": {
        "main_paper_reused_no_request": True,
        "author_appendix_actual_complete_bytes": 2_715_010,
        "construction_paper_actual_complete_bytes": 9_002_174,
        "official_author_domain_and_public_folder_verified": True,
        "source_request_units": 32,
        "actual_complete_month": {"bytes": 22_194_147, "rows": 8494, "factor_columns": 272, "sessions_observed": 22, "missing_numeric_values": 0, "duplicate_timestamps": 0},
        "full_input_or_trading_admitted": False,
        "original13publisher_archive_specific_URLs_and_sizes": "N/A not recovered from retained local summaries; current actual403/renderer-timeouts do not establish those file sizes or licensing",
        "old_forward_paths_retried_bounded_not_blind": "Switched to actual official Duke appendix and firstauthor publicDrive path; response200/fullbody+206metadata evidence retained.",
    },
    "resource_routes_compared": [
        {"id": "R_RAW", "route": "Download public1min272matrix for entire1996–2020 and reconstruct15m", "exact_observed_files": 50, "exact_observed_bytes_lower_bound": 1_073_163_374, "exact_observed_span": ["199601", "200002"], "full_file_count_if_all_months_present": 300, "full_exact_bytes": None, "extrapolation_not_actual_bytes": 6_658_244_100, "scientific_loss_or_dependency": "Large transfer alone still does not recover original15m leg-return construction, sourcecode or SPY quotes; currentvintage/pastvisibility claims remain distinct.", "choice": "not_selected_under_current_cap"},
        {"id": "R_KEYS", "route": "HTTPRange only five ex-post published keys plusmarket", "first_month_column_payload_bytes": 563_793, "first_month_footer_bytes": 141_341, "first_month_minimum_separate_projection_bytes": 705_134, "full_exact_bytes": None, "projection300months_extrapolation_not_actual_bytes": 211_540_200, "request_count": "ExactN/A; even one monthly objectper300months exceeds remaining0units, scatteredcolumns needadditionalRange requests", "scientific_loss_or_dependency": "Drops266columns and changes the claim to ex-post low-dimensional adaptation, still needs correct15mconstruction/code/quotes. No evidence this reproduces fullzoo19.89%arithmeticmean; cannot silently substitute.", "choice": "not_selected_as_budget_workaround"},
        {"id": "R_ORIGINAL", "route": "Recover actual13publisher archive links/access and inventory original15m/code/completemodel forecast+SPY/RF/clock packet before choosing a download", "actual_archive_sizes": None, "actual_complete_forecasts_obtained": False, "scientific_benefit": "Can clarify source equations/target and avoid unnecessary public1min gigabytes or blind nonlinear refits. Allnineconstituentforecasts can verify ensemble; sameinformationPLS/Ridge andmarketAR controloutputs may permit numerical cost replication withzero new fits.", "compact_representation_example_not_actual_delivery": {"intraday_rows_source_OOS": 111280, "float64_fields_assumed": 20, "dense_numeric_bytes": 17_804_800, "assumed_fields": "14forecastfields(nineCtsAllmembers, theirensemble,AllAllensemble,AR1/4/26) plus six timestamp/return/quote/spread/RF numericfields", "provenance_actions_overnight_extra_bytes": "N/A", "archives_may_be_much_larger": True, "new_fits_for_forecast_replay": 0}, "scientific_loss_or_dependency": "Forecast replay tests the supplied models/costs, not independently reconstructed training or new missing-factor/model ablations. Fullcausalinput/coefficients or separate approvedrefits requiredfor those. Forecastmetadata/tableconsistency is not proof of historical availability.", "choice": "preferred_next_input_resource_path_not_ready"},
    ],
    "cheapest_decisive_complete_study_outline_not_admitted": {
        "stage1_original_cost_numerical_replay": "Only after actual full source/code/forecast+SPY/TWspread/RF/session inputs and independent implementation/native/resource acceptance: reconstruct entire source2004–2020 continuous returns, originalfourstrategy styles, reportedintraday/overnight-inclusive mean/grossvolSR, daily netstdSR and drawdown/CAGR. Match baseline andallsourceconstituents, verifytarget/deadband and sourceclock. No one-month smoke as economics.",
        "stage2_information_and_model_contribution": "Sameinformation PLS/Ridge versus ensemble plus price-onlyAR1/4/26 andno-forecastSPY/cash. Missingfactor andcausalstale-information placebo must have actualsupplied outputs or exactverifiedfullfeature inputs; cannot fabricate controls or substitute sourceSHAP. Anynewrefit requires complete model/grid/fold candidateinventory and separatelyboundfullscience approval within remaining7006.69; do not precommit anonymousfit counts.",
        "stage3_actual_account_and_host": "Original fractionalsignedsource returnindex kept separate from20k fundedaccount. Bind bid/askarrival/size/conditions/latency, integercash/margin/borrow/settlement/daytrade eligibility, issuerpayableactions anddailyNAV withhostnet10closing clock. Missingfunding/quotes means accountN/A, not unstatedfictionalshorts orsame-index datejoin. Compute originalquotedcost, separatelyverifiedactualcost,20bp/40bp matchedcoststress; maintainreal fundedstress versus diagnostic sameorders. Host comparison commoncapital/date/cashclock andsource/newaccount attribution, no highSR-only admission.",
        "depth_and_power": "Full17years expected >111k intraday sourceobservations plus multiple calendar/regime annualpaths, dependence-aware daily inference/multiplicity, turnover/liquidity/short/funding/overnight attribution. Complete sameinformation controls and capacity/resource measurement needed; a narrowedwindow cannot refute the fullmechanism.",
        "claim_layers": ["Faithful source-costnumerical reproduction only with actualauthorcode/inputidentities", "Currentvintage explicitly changed-method diagnostics require a complete newdefinition", "Funded20k/executablePIT account andSchwabmigration need actualquoting/funding/broker support evidence", "All currentlyread sourceyearsseen; no untouchedOOS/paper promotion"],
        "full_scientific_plan_executable": False,
        "why_not_freeze_uncertain_details_as_source": "Original15maggregation, target/deadband andclock unresolved. A guessed fullscientific definition would prejudge a materiallydifferentapplication; this packet requests a realinput/resource decision, not approval of guesses.",
    },
    "exact_missing_inputs": [
        "Actual publisher13archive URLs/fileinventory andperfile sizes or an equivalent originalauthoredcode/matrix/forecast packet, not inferredfrom oldlinkcount.",
        "Original15min factors/legs or verified reconstruction method; retained1min199601 alone insufficient.",
        "Complete2000–2020forecast-feature/training metadata including2004–2020test and causaljump construction; code toresolve sufficientstrategy threshold andtarget conventions.",
        "SPY fullperiod rawprice/TWquotedspread/RF/overnight/sourcecalendar input; actualaccount furtherneedsarrivalquotes/actions/payable/borrow/funding. Existingmarket15request/12.657MB pool not certified tocover2004–2020.",
        "Currentbroker/Schwab admissibility sourceevidence for repeated20k intraday longs/shorts, no inferredlegal/fill readiness.",
    ],
    "material_external_decision_requested": {
        "preferred": "Deliver alreadyobserved13archiveactualURLs/retainedinventory or an actualcompleteauthor sourcepacket, and permit bounded officialinventory inspection tochoose original15m/fullforecast subset. No license/cloudpurchase requested.",
        "bounded_public_inventory_extension_proposed_not_authorized": {"additional_request_units_max": 16, "direct_response_bytes_max": 1_048_576, "charge_bytes_to_existing29_856_005_known_headroom": True, "purpose": "ActualofficialURL HEAD/Range/centraldirectory/codeinventory only; no bulk returnpayload, no challengebypass/undocumentedendpoint. Only with a usableofficialpath; same403/timeouts triggersstop, no requestcount-drivenblindretry.", "not_a_complete_input_budget": True},
        "if_usable_original_input_not_found": "DeferHFmechanism withoutrefutation or deployment; choosea different complete authorizeddirection ratherthan fitone month, savea nearbysourcewindow or spendremainingeconomicpool on priceproxy.",
        "bulk_download_or_compute_extension": "Notrequestedatthisstage; exactsubset size/rights andcomplete approvedscience first. Full1min lowerbound demonstrated; no7GB authorization presumed.",
        "new_paid_spending": False,
    },
    "native_and_economic_boundaries": {
        "independent_science_full_economic_plan_approval": False,
        "input_ready": False, "implementation_ready": False, "native_gate_ready": False,
        "resource_ready_for_full_study": False, "economic_execution_admitted": False,
        "no_native_economic_gate_bypass": True, "model_fits": 0, "economic_runs": 0,
        "workflow_pass_actual_source_input_QA_only": True,
        "research_pass": False, "ml_contribution_pass": False, "paper_ready_pass": False,
        "qualified_alpha_count": 0, "NIXT_Fedput_reopened": False,
    },
    "independent_review_request": "Independently challenge this complete source/input/materialresource judgment and claim boundaries from actual boundprimary evidence. Accept/revise resource_decision only, not approve_deep_plan or economicinput/compute. No new11table, no Rootintermediate message; read/hash/metadata only, no tradingreturns/fits. Complete conditional execution definition follows only an actual usable sourcepacket. Existing peer remains independent of HF author.",
    "next_action": "One full independent resource/fidelity decision review, then resolve ordinarydiffs andseal resource-blocked finalresult if noauthorizedpath remains; onlyone nativefinish, no separateRootnotification.",
}
decision_binding = write("scientific-input-resource-decision.json", decision)

cards = [
    {"claim_id": "HF_SOURCE_MECHANISM", "source_url": "https://public.econ.duke.edu/~boller/Papers/MS_2025.pdf", "snapshot": main, "locations": ["Sections3/5/6", "Tables4/5"], "claim": "Broadmarket factor forecasting traded viaSPY; allpublishedmetrics sourceclaims only, cost andovernight definitions differ fromfundednetstd account.", "verified_by": "author fullPDFreading", "seen": True},
    {"claim_id": "HF_CAUSAL_JUMP_AND_CADENCE", "source_url": "https://public.econ.duke.edu/~boller/Papers/HFML_Sup_App.pdf", "snapshot": appendix, "locations": ["OA.2", "OA.3", "OA.7"], "claim": "Past-onlyEWMA jumpthreshold; train-onlyscaling, nonlinear5yearrefit andlinearannual; sourceSR grosssecondmoment denominator.", "verified_by": "author fullappendixreading", "seen": True},
    {"claim_id": "HF_ACTUAL_PUBLIC_INPUT", "source_url": "https://www.sakethaleti.com/data", "snapshot": primary["author_data_page"], "actual_file": primary["actual_complete_month"], "claim": "Actualone complete1min272factor month obtained; counts/keycolumns verified,15m/PIT/sessionclock unadmitted.", "verified_by": "publicfolder+HTTP200/206+actualparquetQA", "seen": True},
    {"claim_id": "HF_INPUT_SIZE_LOWER_BOUND", "source_url": "https://drive.google.com/drive/folders/1nlwZF18V8x8pTcmnH9S0nZCmdruFLniE", "snapshot": primary["public_file_inventory"], "claim": "First50publicmonthlyfile metadata exactsubtotal1,073,163,374B; partiallisting, exactfullsample sizeN/A.", "verified_by": "retained_DRIVE_ivd JSONparse; firstfilepreview+HTTPContentRange+wholebody match", "seen": True},
    {"claim_id": "HF_SOURCE_CONSTRUCTION_LIMIT", "source_url": "https://drive.usercontent.google.com/download?id=13i37t75e0tVz1hh7FASWbw8coQnQmI4k&export=download", "snapshot": construction, "locations": ["Data", "Portfolio construction appendices"], "claim": "CRSP/TAQ securityidentity, factorlegweight andterminal conventions necessary; currentpublic1minL-H compounding notverifiedoriginal15m.", "verified_by": "actualfullauthorPDFreading", "seen": True},
]
cardpath = P / "sourcecards.jsonl"
assert not cardpath.exists()
cardpath.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards))

files = [binding(p) for p in sorted(P.rglob("*")) if p.is_file() and p.name != "current-state.json" and "__pycache__" not in p.parts]
external = [main, binding(PREVIOUS / "root-result-acceptance.json")]
manifest = write("source-input-decision-manifest.json", {
    "schema_version": 1, "task_id": "DAY3-HF-FACTOR-RETURN", "as_of_utc": NOW,
    "author": decision["author"], "purpose": "Complete boundsource/input/materialresource decision review, no economicimplementation",
    "decision": decision_binding, "files": files, "external_bindings": external,
    "file_count": len(files), "strategy_or_model_implementation_manifest": False,
    "economic_runs": 0, "model_fits": 0,
})
print(json.dumps({"decision": decision_binding, "manifest": manifest, "source_input_known_CPU": known_cpu, "files": len(files)}, ensure_ascii=False))
