# ruff: noqa: E501
"""Freeze the complete conditional question, without fitting or economic runs."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

P = Path(__file__).parent
ROOT = Path.cwd()


def bind(path):
    path = Path(path)
    return {
        "path": str(path.resolve().relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    snapshot = P / "complete-input-progress-at-plan-freeze.json"
    if not snapshot.exists():
        snapshot.write_bytes((P / "complete-input-progress.json").read_bytes())
    candidates = []
    configurations = [
        ("PLS_IDX_CTS", "PLS", "IDX", "Cts", "ALL"),
        ("PLS_IDX_ALL", "PLS", "IDX", "All", "ALL"),
        ("RIDGE_IDX_CTS", "Ridge", "IDX", "Cts", "ALL"),
        ("HGB_IDX_CTS", "HGB", "IDX", "Cts", "ALL"),
        ("PLS_SUM_CTS", "PLS", "SUM", "Cts", "ALL"),
        ("PLS_INV_CTS", "PLS", "INV", "Cts", "ALL"),
        ("HGB_INV_CTS", "HGB", "INV", "Cts", "ALL"),
        ("PLS_IDX_MKT", "PLS", "IDX", "Cts", "MKT"),
        ("PLS_IDX_KEY6", "PLS", "IDX", "Cts", "KEY6"),
        ("PLS_IDX_MINUS5", "PLS", "IDX", "Cts", "MINUS5"),
        ("PLS_IDX_STALE", "PLS", "IDX", "Cts", "STALE"),
        ("PLS_INV_MKT", "PLS", "INV", "Cts", "MKT"),
        ("PLS_INV_MINUS5", "PLS", "INV", "Cts", "MINUS5"),
        ("PLS_INV_STALE", "PLS", "INV", "Cts", "STALE"),
        ("OLS_IDX_CTS", "OLS", "IDX", "Cts", "ALL"),
    ]
    for ident, model, measurement, label, features in configurations:
        candidates.append(
            {
                "candidate_id": ident,
                "model": model,
                "measurement": measurement,
                "label": label,
                "feature_set": features,
                "promotion_eligible": False,
            }
        )
    for lag in (1, 4, 26):
        candidates.append(
            {
                "candidate_id": f"AR{lag}_CTS",
                "model": "OLS",
                "measurement": "MARKET_LAGS",
                "label": "Cts",
                "lags": lag,
                "promotion_eligible": False,
            }
        )
    candidates.append(
        {
            "candidate_id": "PAST_MEAN_CTS",
            "model": "historical_training_mean",
            "label": "Cts",
            "promotion_eligible": False,
        }
    )
    candidates.append(
        {"candidate_id": "ZERO_FORECAST", "model": "zero", "promotion_eligible": False}
    )

    feature = {
        "author_input": "All300actual monthly272-factor current-vintage files,1996-01..2020-12; first reused,299new; raw snapshots/SHA and full QA must be independently accepted. Not original15minlegs, historical constituents/weights or PIT certification.",
        "public_units": "Observed public values are simple fractions, not percent points: expm1(officialFFlogCSV)==publicparquet for618 observations. Never divideby100. General269dictionaryrows and full272columns preserved; unit/formation provenance remains currentversion conditional.",
        "timestamp_contract": "Explicit APP wallclock America/New_York: row09:30 is overnight close-to-open and is separate; rows09:31..16:00 are one-minute returns ending at their timestamp. Source construction and391rowdays support this convention, but public metadata has no timezone/explicit endtick field. It is a declared reconstruction assumption, not verified timestamp/fill/PIT proof.",
        "calendar": "Use existing open_composer.market_sessions tradingcalendar including earlycloses; verify observations against actual close. No bar filling, no return-based exclusion, no treating missing13:00/16:00 as complete. Unexpected partialdays retained with exact missingclock reason; all policy accounts still run on actual ETF NAV dates.",
        "windows": "Fixed15minute grids09:30+15*k minutes, k=1..26, using exactly15 minute rows ending at k. Earlyclose permits only true complete windows through actualclose. 09:30 never enters intraday windows. Hour requires four complete same-day windows. Prior-day channel requires every expected previoussession intradaywindow and observed overnight row; no future-day completeness filter.",
        "IDX": "For each complete15minute window define L[j,k]=SUM(log1p(simple_minute_return)); hourly channel is mean of last4L; previousday channel is SUM(all observed minute log1p including separate09:30), only when previousactualsession complete. This is a synthetic net-factor index, not source15m long-minus-shortleg logreturn. Return<=-1/nonfinite makes that cell invalid, never clipped.",
        "SUM": "Simple15window SUM, same last4window mean and previouscomplete day SUM; measures additive rather than synthetic index accumulation. Fulltarget remains the same observed FFmarket IDX logwindow.",
        "INV": "For all272columns B[j,k]=SUM15[j,k]-SUM15[j,1]; use Bcurrent, mean of four completed Bwindows, and SUM of all previouscomplete-session Bwindows. No overnight in this invariant daily channel. Firstbaselinewindow must already be mature. Equal15 observations mean exact cancellation of a same-day constant additive c_j,d, if that adjustment really applies. It does not cancel log1p adjustments, full-day cleaning/interpolation, future composition or all PIT risks. Nonzero FFmarket is not assumed adjusted; subtracting its anchor is an explicit information view, and target is never transformed with this anchor.",
        "common_prediction_clock": "Every predictive pipeline uses the same signal times: completed window k=4..n_d-1, forecasting target window k+1, normally10:30..15:45. Firsthour has fixed noforecast fallback, never model-specific advantage. With no valid commonfeature packet, intraday fallback is0risk, overnight target+1; common missing packets logged. INV baseline noise and changes in previousday information are tested with matched INV marketonly/simple/nonlinear/stale controls. Published full26interval coverage is not claimed.",
        "HAR": "Three channels per retained factor,816full predictors; train-only scaling. Sourcehour SUM versus our mean differ only by fixed scaling. No contemporaneous target return or future exit/whole-day checks affect a current signal.",
        "key5": [
            "cz__betatailrisk",
            "jkp__turnover_126d",
            "jkp__zero_trades_21d",
            "jkp__zero_trades_252d",
            "jkp__ivol_capm_252d",
        ],
        "key_name_gate": "Dereference exact269catalogue coordinates and272schema before implementation; if spelling differs, only actual corresponding source identifiers may be corrected, with diff provenance. Never substitute an unrelated factor.",
        "feature_sets": "ALL272; MKT only ff__mkt; KEY6=ff__mkt+published5, a diagnostic not presumed sufficient; MINUS5=all except those5; STALE leaves marketHAR current and uses other factors' alreadyformed sameclock features from20 completed prior observed sessions. No permutations reading future labels. Same fixed stale transformation for IDX/INV.",
        "target": "The observed public ff__mkt synthetic15min logwindow, identical across measurement/model controls. Gross-versus-excess exact mapping to original target is not certified. Never claim currentffindex is actualSPY return. ETF trading uses forecasts of this broadmarket variable; no directETF refitting or target switching.",
        "jump": "Source-derived exante alpha3.5,varpi.49,n26: sigma2=(pi/2)*26*EWMA(abs(r[i-1]*r[i-2]),halflife26)*tau[d,k]. EWMA excludes overnight, uses only alreadycompleted intraday marketwindows, adjust=False recursion with alpha=1-exp(-log2/26). tau is sameclock mean squaredreturn dividedby mean across26clocks, estimated from last252 complete prior regularsessions, min52, frozen withincurrentday. k=252/min52/EWMA init are APP conventions because exactsource k/init not published. Threshold=3.5*sqrt(sigma2)*(1/26)^.49. Shortsession windows use their actual k and same26nominalgrid, no missingwindow filling. Cts traininglabel is r*1(abs(r)<=threshold), zeroing not retrospectively removing jump samples; All usesr. Labels mature at windowend; jump filtering never screens realised trade returns.",
        "maturity": "1996 is input/volatility warmup; eligible training1997..endpriorcalendar year with actual commonfeature maturity. Firsttest2004; no 1996 economics and no in-sample predictions passed as forecasts.",
    }
    validation = {
        "windows": "Expanding eligible1997..year-1; first80% chronological observations train, latter20% validate, floor(.8*N). Linear models annual2004..2020. HGB train/validate only at2004,2009,2014,2019 and frozen predictions for subsequent5years through2020; same cadence on both informationviews. This follows OA3, not an annual nonlinear refit.",
        "fit_selection": "Trainingfeature means/std only, populationstd; zero-std columns setscale1 and coefficients0. Target train-only mean/std restored in forecasts. Hyperparameters minimize validationMSE on the same label/rows; tie chooses smaller K/lambda-grid index/HGB trees then depth then learningrate. Reuse winning trainingfit parameters for tests, per mainSection3.4; no refit on validation or selection by strategy profits. No model-level winner selected after seen tests.",
        "PLS": "Source-supported K1..10 (MKT max3); PLS1 prefix solutions may share moment algebra if tested numerically against installed sklearn.PLSRegression on genuine synthetic fixtures. Prefix paths count all logical K trials; solver optimization does not erase trials. Not PCA or unsupervised factors.",
        "Ridge": "100 equally spaced natural loglambda -1..8, penalty ||y-Xb||^2+lambda||b||^2; shared eigensolution allowed with numeric equivalence tests. OLS exact train-only pinv, not ridge disguised as simplebenchmark.",
        "HGB": "Explicit APP sklearn HistGradientBoostingRegressor, not sourceXGBoost2.0.3. NoXGBoost installed/no package or cloud download in thisscope. Nonlinear source-supported capacity scales: depth4/6 x learning_rate.01/.1 x max_iter50/150/350=12 validation configurations per4cadence dates perview. max_leaf_nodes=None, min_samples_leaf20, max_bins255,l2_regularization0,loss squared_error,early_stopping=False,random_state20261013. Remaining installedimplementation defaults snapshotted. Depth/eta/tree sets are source-supported subset, minleaf/hist/defaults are APP conventions, not published min_child_weight equivalents. Warmstart50->150->350 may share fixed trees if tested; still48logicalvalidated configs/view and all fit/update exposures retained.",
        "AR": "Source-inspired AR1/4/26 uses prior completed intraday marketwindow returns including prior sessions only; overnight excluded. OLS train-only same splits/commontargetclock; no hyperparameter search. Historicalmean training only. Expostmean may be reported solely as untradable statistical diagnostic, never used by any account.",
        "exposure": "All original2004..2020 and publiccurrentvintage history are alreadyseen/development. Yearly heldout chronology measures method generalization conditional on knownvintage, not new untouched OOS/promotion. Future2021..2026 inputs absent, no extrapolation of near-term profitability.",
    }
    execution = {
        "layers": "A statistical FFindex forecasts/R2/DM; B stylized actualSPY historicalprice exposure diagnostics; C funded20k long-only integer cashproxy account underfixed20bp/40bp. All three separate. OriginalTAQ timeweightedquotedspread/sourcecost reproduction and actualquote fills N/A unless actualfull boundinputs exist, no quote-average substitution.",
        "market_intake": "After completeplanapproval, at most15 remainingmarketrequests/12,657,184actualresponsebytes (9old/4,120,032 preserved): documentedAlpaca SIP raw15Min SPY2016-01-01..2021-01-01,limit10000,asc,asof='-',completepagination inclextendedhours thenfilter actualregularcalendar. Reuse boundraw/all SPY/BIL daily2015..2026, normalizedactual issueractions and actual4quoteaudits; reused5sec2020-03-16 quotes do not establish completecosts. No undocumentedendpoint/TAQ/paid data. Request count cap and streaming body cap enforced, failures retained; cannot use incompletepagination as completeinput.",
        "market_input_gate": "Require complete relevant2016..2020 rawSPY15Min pages, strictUTC-to-NY clock, regularbar starts/open/end/close, positiveOHLC/volume and same-session validation; actualdailyclose reconciliation, splits and every2016..2020SPY/BIL distribution ex/record/pay/amount fromalreadyboundissuerworkbooks. Missingdailyheldmark makes full continuousNAV metricsN/A, never silently forwardfilled; missingexecutionbar means nofill. Field-driven commonstart frozen before any account calculation; nominal2016-01-04close initialization if actual input proves coverage. If actualcoverage/fields are insufficient, affectedaccountN/A with a targeted inputdecision, not substituteFFprofits.",
        "signal_rules": "Sourceconsistent reconstruction from OA5.2: with frozenforecast m and halfcost h, SSign target+1 ifm>h,-1 ifm<-h,otherwise retainpreviousdesiredposition; SPositive target+1 ifm>h,0 ifm<-h,otherwise retain. This solves max(m*w-h*abs(w-v)); printedEq6/7 ambiguousnegative sign is not evidence of actualauthorcode correction. PlainSign/Positive also fixed diagnostics, no threshold optimization.",
        "cost_views": "0/1/5/20/40bp perunit tradednotional, charged each entry/exit includingopening/night target changes. 1/5 are explicit hypothetical lowfriction diagnostics, not actualTWspread. Decisionthreshold uses eachfixedhalftransactioncost separately; these distinctorderpaths counteconomicpolicies. 20bp primary remains frozen;40stress repeatsfundedaccount withits own affordability, never unfunded sameorders called fundedstress. Same20bp orders at40bp may additionally be shown only as unfunded costdiagnostic. Borrow2% annual sourceconvention only for fractional SSign diagnostic, not certifiedETB/brokerborrowing. Cashzero interest; transactioncharges include a stipulated all-in cost, no claims of calibratedimpact/capacity.",
        "overnight": "Sourcecomparative diagnostic fixes overnightposition+1 and reports intraday-only and overnight-inclusive separately, withopening/closingturnover charged. Fundedlong account schedules target+1 atactualclosingbell referenceprice wherecash allows; inability to buy is actualproxyaccountno-fill, not forcednegativecash. Source's overnightreturn is not model Alpha.",
        "diagnostic_clock": "Fractional diagnostic immediateboundary uses observedETFbaropen at nextintervalstart after completedfeatures, declared zero-latency boundaryresearchproxy. Explicit onefull15minute latency diagnostic shifts desiredexposure oneinterval; never retime targetlabel to earn the predicted interval. Dividendtotalreturns requireboundexdateactions; sourcegrossvolSR and usualdaily netstdSR distinctlynamed. No diagnostic may claim actualfills, fundedcapitalor deployability.",
        "funded_clock": "20k startsallcash at firstcommondailyclose, initializer removedonlyfrom that comparison inference. Firstactualscheduledposition atnextsession09:30 usingpriorclose. Intradaysignal afterkthwindow frozen at its end, submittedfornextfullbaropen15minuteslater; report this onebarstale exposure relative to forecasttarget, no future features/order resizing. Lastsignalwhosefill wouldbe closingbell is discarded; fixednight+1 order takes precedence atbell. Actualrawbaropen/lastregularbarclose are researchexecutionreferences, notask/bid/fill proofs. Eachsignal uses currentposition to freeze desired0/1; ifdesiredmatchesheldstate,no dailyrebalance ordividendtopup.",
        "integer_gap_cash": "At signalclose freeze wholelot floor(availablecash/(knownreferenceprice*(1+cost))); execute nextfullbaropen onlyif fixedwholelot+cost<=actualavailablecash; otherwise skipentirebuy, never assume sameprice/downsize withfutureask. Sell only heldshares; immediately booknet sale as unsettled receivable, not spendablecash. No leverage/shorting/fractionalstocks in20k ledger. Track requested/filled/skipped lots and cash lock, fees, prices, liabilityand orderID. Stress reruns own fundedledger with fixedpolicy, no futurecash borrow.",
        "settlement": "Explicit inherited cashavailabilityproxy only: weekday/exchangecalendar intersection with USFederalholiday union, sale proceeds available4eligible dates strictlyafter saledate through2017-12-31,3from2018through2020; original2017transition notpreciselyverified,extraeligible-datebuffer. Dividends booked receivable on actualexdate for priorclose heldshares, move tocash firsteligible date strictlyafter actualboundpayabledate. Proxy is neither verifiedDTC/brokercash nor lowerbound. No inferrednextbusinessdaypaydate, no exdate reinvestment. Required cashcalendar exact binding is reused, not passed off as verifiedrealsettlement.",
        "NAV": "Every actualregularclosingbell, rawheldSPYshares*actualdailyclose + availablecash + pendingnetsale + dividendreceivables; paiddividendscash, zerointerest. No postterminal forcedliquidation. Benchmark same initialdate/cost/whole-share/proxyclock: SPYBH,BILBH,zeroCash,SPYovernightonly; fixedpositions/funding shown. Daily BH costincludesactualentry, no daily charges onno-trade days. Accounttests require rawaction recomputation, no multiplying theoreticalfractionalexposureinto20k.",
        "host": "Existing F1__net10 and5componentEW samefirstcommonclose/net10/drifting16khost+independent4k fundedproxy sleeve, compare4kwithsame-clockSPY/BIL/cash/marketonlyforecast. Exactclosingclock mustoverlapactual2016..2020quotes/bar/actions. If no valid overlap, hostincrement/beta matching N/A withactualdates; do not invent hostbackhistory or scale20kby.2. Sourcecostexcess/cashRF and storedhostnet10 not relabelled20bp.",
        "broker_boundary": "No paper/liveorders or brokerreadiness. 20k fundedresearchproxy is longcash only; source short/highfrequency margin trades have unverifiedcurrentPDT/borrow/funding eligibility, N/A for20kdeployment. Actualquote/arrival/latency/ETB/capacity absent; broker-specific changes require officialsource verification before laterdeployment, not thisresearch model's approval.",
    }
    inference = {
        "statistical": "UncenteredR2 vszero onAll andCts labels, RMSE, directional coverage, yearlyMSE/meanprediction, OLS/AR/pastmean andmarketonlyinformation parity. Dailyaggregatepaired loss differences, HAC lag5,20-session blockbootstrap2000 seed20261013; jointmaxT sixpreregistered contrasts PLSfull-vsMKT,HGBfull-vsPLS,PLSINV-vsIDX,MINUS5-vsALL,STALE-vsALL,CTS-vsALL. No successfulwindow/modelchosenpost-test.",
        "economic": "For everyactualfundedcontinuousaccount: dollars/terminalNAV/CAGR,annualusualnetstdSRexdailyBILbuyholdreturn,DD/recovery/underwater,5/21/63sessiontail losses,beta toSPY daily andmeanexposure, fees/ordercounts/cashwaiting/no-fills andturnover. Full2016..2020,eachyear,fixed2016..2018vs2019..2020,currentlast252/126/63 sessionswithin2020, nevercalled2026recent. Publishedquotedcost/yearmean/grossvolSR distinct fromactualconditionalCAGR/netSR.",
        "uncertainty_and_trials": "20predictionpipelines, allK100ridge/HGBvalidated configurations/year/refit, all5feeorders/4signalrules/2latencyviews and failureexposures retained as distinct logical trials. Trial counts logged withdata/feature/label/model/cost/evaluation hashes, physicalreuse doesnoterase candidateexposure. Broadseenfamily uncertainty usesdailyblockbootstrap/HAC/maxT andDSR descriptiveeffectivecount no less than all affectedprediction/economicviews; PBO/SPA/promotioncohortN/A because no selection oruntouchedOOS. MDE/pairedvariance/power reported; a null currentapplication is not generalmechanism refutation.",
        "benchmarks": "Same-symbolSPYBH,BILcashproxy,zero cash,source-likeovernightonly,marketonly forecast/simpleOLS/AR,KEY6/removed5/stale andsameINVcontrols. Equalweight/sector/expostbest stock benchmarks notapplicable tosinglefixedETFforecastquestion; no changingassetuniverse. Expostbestpipeline only clearlynonpromotable diagnostic. Hostactualclockoverlap is agate, notgenericcorrelation substitute.",
    }
    resources = {
        "source": "Old32/37,252,859B sealed pluscurrentcontinuationinclusive400requests/8GiB,approved299monthlyfiles. Source/inputQA new2000coresec1CPU<=900MiB; earlymulti-threadtimepreserved andcurrent14threadspinnedoneCPU. All actualbytes/redirects/failures count. Old40+40/old500prepreservation retained. No source allowance automatically expands to data/code not in its independentlyaccepted scope.",
        "market": "Old24/16MiB pool9used4,120,032B; exclusive15requests/12,657,184B left for documentedSPYbars. No duplicateold9,newquotesfishing, extraquota, paidarchive orexistingotherowner resources.",
        "economic": "Unique7006.69coreseconds left from7200 after163.31 actual+30resultreservation; oldknown186.164505/otherunknownretained. All training/CV/prediction/economiccompute/failures counted, not sourceQA. No newcloud/USD/Hadan. LocaloneCPU freshmemory<=900MiB/500MBownerreserve, explicitaffinity/threadlimits.",
        "planned_upper_allocation": {
            "input_feature_implementation_preparation_from_new2000_only": 650,
            "linear_moments_PLS_Ridge_OLS_AR_economic": 1700,
            "two_HGB_views_all_registered_refits_economic": 4200,
            "accounts_inference_reports_economic": 700,
            "independent_result_reservation_economic": 300,
            "economic_contingency": 106.69,
        },
        "estimate_not_actual_admission": "6600author+300review+106.69contingency allocation is a planning ceiling, not measuredproof. Need completeinput size/rowcount then bound peakresidentmem and actual firstdevelopment HGB resourcecalibration afterallscience/input/implementation/native gates. Run fixed2019 largesttrain 350trees/depth6 first asregisteredmodel fit; suppress economic/testmetrics until calibration admitsremainingworstcase. Charge itsactualfit exposure. Conservativeestimationuses actualCPU multipliedbyremaining tree/depth/data workloads, adds500margin; ifremainingfullpackage doesnotfit7006.69, stopfor specificresource/scientificchoice ratherthan silently omit nonlinear/depth or runpartialnegativeconclusion.",
        "memory": "Streammonth sourceQA; immutablecompact15min arrays andHARfloat64memmap ondisc. No full1min concatenation. Fitonefold/view atatime, avoidfloat32->float64 duplication; sourcePLS equivalentmomentalgebra verifiedagainstsklearn. HGB inputC-contiguousfloat64 memmap+binneduint8; actualfresh900MiBadmissionand caprequired, no promisedmemory basedonlyfilelength. RLIMIT_CPUremaining andprocessreceipts/foldcheckpoints; failures/oldreservationsneverreset.",
        "gates": "Full independentapprove_deep_plan->actualinputQAacceptance->implementationmanifestindependentacceptance->actualnativeiteration/knowledge/candidate/data gates->freshresourceadmit. No fit/calibration/forecast/economicreturns beforeall gates. Planapprovalallows declared read-onlyinput intake and implementationpreparation, not economicgo. Existingmarket_component_method route, no unrelatedStrategySpec/engine/production edits.",
    }
    plan = {
        "schema_version": 3,
        "task_id": "DAY3-HF-FACTOR-RETURN",
        "author": "7b109880-ac40-447e-b2a6-f0ed1266ebac",
        "reviewer": "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "research_role": "market_component_method",
        "question": "Does the full published cross-factor lagged-information mechanism survive matched simple/nonlinear capacity, fixed current-vintage measurement/adjustment controls and realistic friction/cash/latency well enough to justify primary-return investment? Source-method reconstruction, conditionalactualSPY research anddeployability are differentclaims.",
        "bindings": {
            k: bind(v)
            for k, v in {
                "main_pdf": P.parent / "primary-return-breadth/sources/hf_zoo.pdf",
                "main_text": P / "hf-zoo-read.txt",
                "appendix_pdf": P / "sources/hf-zoo-appendix.pdf",
                "appendix_text": P / "sources/hf-zoo-appendix.txt",
                "construction_pdf": P / "sources/factor-construction-paper.pdf",
                "construction_text": P / "sources/factor-construction-paper.txt",
                "source_equations_image": P / "source-equations-6-7.png",
                "source_data_page": P / "sources/author-data-page.html",
                "root_authority": P / "root-source-continuation-decision.json",
                "root_continuation": P / "input-resolution-continuation.md",
                "source_request_manifest": P / "complete-input-request-manifest.json",
                "complete_input_scope_review": P / "independent-complete-input-scope-review.json",
                "purpose": P / "scientific-complete-input-purpose.json",
                "input_progress_immutable_at_freeze": snapshot,
                "unit_reconciliation": P / "resolution-sources/unit-convention-reconciliation.json",
                "factor_dictionary": P / "resolution-sources/factor_cite_info_fmt.xlsx",
                "factor_catalogue_QA": P / "resolution-sources/unit-catalog-QA.json",
                "cash_calendar": P.parent / "primary-return-breadth/cash-calendar.json",
                "existing_actions": P.parent
                / "primary-return-breadth/inputs/normalized-actions.json",
                "action_completeness_limits": P.parent
                / "primary-return-breadth/inputs/action-completeness.json",
                "market_old_ledger": P.parent
                / "primary-return-breadth/inputs/market-request-ledger.json",
                "host_clock": P.parent / "primary-return-next/host-close-clock-binding.json",
                "sourceQA_affinity_receipt": P / "source-QA-oneCPU-affinity-receipt.json",
            }.items()
        },
        "source_and_difference": {
            "source_claim": "2025author272fullfactors, source15minutelegreturns, expanding80/20 andnonlinear5y refits, FFmarket forecasts appliedtoactualSPY, exantejumpfilter, TAQquotedspread+2%borrow, sourceSRgrosssecondmoment denominator. Source19.89/26.73annualarithmeticmeans are not ournetCAGR. PublishedAll+Cts andfull9modelensemble are not allreproducedhere.",
            "new_application": "Currentpublic1minnet-factor aggregation has no originallegs/code/formation snapshots. FixedIDX/SUM/INV source-led views, sameobservedmarket target, pairedsource-stylePLS/Ridge/OLS andclearlynewhistnonlinearcapacity. Commonfirsthourmaturity differssourcefull26returns. Allseen; no faithful numericalsourceSR assertion, no PITable guarantee, no selectablecandidate.",
            "counterevidence": "OA5directETFrefits weaker thanbroadFFtarget; full-dayadjustment/cleaningandfuturefactorselection may contaminatepublicinput. Mainfivekeyfactors alone .50SR vsfull1.37 is not enough toassume5sufficient. PlainSign/Positive turnover and overnightmarketreturns materially drive economicheadline. SmallR2/highgrossSR canlose withcashconstraint/latency/20bp. Sourcefulldata isnowreal, notglobal inputabsence.",
            "prior_experiments": "Fedput/NIXT acceptedconditionalstops retained, no oldwindow/parameterrescue; no Chinco/NEWS/Step5/DLSA/Attention ownership. This question is broadfactorinformation, notsingleETFtechnicals or datareadycounts.",
        },
        "feature_and_label": feature,
        "validation_and_models": validation,
        "execution_and_capital": execution,
        "inference_and_contribution": inference,
        "resources_and_gates": resources,
        "candidates": candidates,
        "depth": [
            {
                "id": "INFORMATION_MEASUREMENT",
                "test": "Complete272/25years vsmarket-only/key6/remove5/stale; IDX/SUM/exactconstant-invariant under same target/clock and matchedINVcontrols expose publishedinfo vsmeasurement/anchor dependence.",
            },
            {
                "id": "CAPACITY_JUMP",
                "test": "SourcePLS latent1..10, sourceRidge100penalties, sameinfoOLS andhistnonlinear50/150/350trees/depth4/6/eta; targetAllvsCts withstrictlylaggedvol, full17yearchrono tests nottwo cases.",
            },
            {
                "id": "FRICTION_CAPITAL_LATENCY",
                "test": "PublishedquotedcostN/A ifmissing; actualSPY exposure0/1/5/20/40hypotheticalbps, sourceSign/Sufficient/Positive, onebarlatency, 20kwholelotsettlementproxy NAV; overnight attribution andsame-clockbenchmarks/hostwhereactualoverlap.",
            },
        ],
        "model_roles": {
            "return_forecast": "PLS/Ridge/HGB/OLS matchedsameinformation",
            "factor_generation": "N/A usesauthorfactorreturns",
            "asset_selection": "N/A fixedSPY",
            "risk_and_uncertainty": "Exantejumpthreshold andpairedinference, noAIriskoverlay",
            "sizing": "Frozenunitrisk andintegercashrules",
            "LLM_signal": False,
            "missing_modality": "MKT/KEY6/MINUS5 andINVmatches",
            "placebo": "20sessioncausalstaleotherfactors",
            "fallback": "Fixedintradayzero/overnightlong conditionaloncash, never futurefill",
        },
        "decision_rule": "Complete measuredcomparisons first. If conditional20bp dollar/CAGR failsmatchedSPY/BIL orcross-factorvalue/cash/latency disappears, stopthiscurrentapplication/deferdeployment; sourcequoted-cost or lowerfriction mechanism notrefuted. If gains onlyIDX notINV, retain contamination/measurement ambiguity andrequire causalraw-leg/forward evidence beforenewallocation. If invariantmatchedinfo/nonlinear economicincrement survives, preserve specificnextinput/forwardcandidate withactualcost/identity/PIT/marketclock requirements; no profits presumed,no modelfavored. HighSRlowreturn onlyeligibleasrole afteractualmatchedhostincrement; absenthostoverlaproleunproven. Full source/mechanism refutation and2026near-termAlpha notwithinthisseenconditionalstudy. Realfullcompute/input insufficiency yields specificscientific/resource decision, not a table/partialsmoke.",
        "status": "complete_scientific_plan_proposed_economic_closed",
        "scientific_plan_approved": False,
        "input_ready": False,
        "implementation_ready": False,
        "native_ready": False,
        "economic_execution_admitted": False,
        "research_pass": False,
        "ml_contribution_pass": False,
        "paper_ready_pass": False,
        "promotion_eligible": False,
        "paper_trading_allowed": False,
        "broker_activity_allowed": False,
        "pit_universe_certified": False,
        "deployment_readiness_claim": False,
    }
    save(P / "scientific-plan.json", plan)
    contract = {
        "schema_version": 1,
        "task_id": plan["task_id"],
        "author": plan["author"],
        "scientific_plan": bind(P / "scientific-plan.json"),
        "feature_and_label": feature,
        "validation_and_models": validation,
        "execution_and_capital": execution,
        "inference_and_contribution": inference,
        "resources_and_gates": resources,
        "status": "proposed_full_contract_economic_closed",
    }
    save(P / "execution-contract.json", contract)
    print(
        json.dumps(
            {
                "plan": bind(P / "scientific-plan.json"),
                "contract": bind(P / "execution-contract.json"),
                "prediction_pipelines": len(candidates),
            }
        )
    )


if __name__ == "__main__":
    main()
