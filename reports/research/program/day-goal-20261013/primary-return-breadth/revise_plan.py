from pathlib import Path
from datetime import datetime,UTC,timedelta
from zoneinfo import ZoneInfo
import json,hashlib,shutil,inspect
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from open_composer.market_sessions import us_equity_session_close,next_us_equity_session,us_equity_session_dates

P=Path(__file__).parent;ROOT=Path.cwd();NOW=datetime.now(UTC).isoformat()
def bind(p):
 p=Path(p);return {'path':str(p.resolve().relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def write(name,x):(P/name).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
for name in ['scientific-plan','execution-contract','calendar-packet','early-input-evidence','independent-plan-review']:
 dst=P/(name+'-v1.json')
 if not dst.exists():shutil.copyfile(P/(name+'.json'),dst)
old=json.loads((P/'scientific-plan-v1.json').read_text());plan=json.loads(json.dumps(old))
f=Path('reports/research/program/regime-french-source-20261010-1917')
french={'public_aggregate_available':True,'bindings':{n:bind(f/n) for n in ['official-daily.zip','receipt.json','schema-evidence.json','official-definition.html','official-library.html']},'source_mapping':'OriginalSection2footnote4 explicitly French marketreturns/Tbill; Mkt-RF+RF isaggregateMkt, Mkt-RF isdailyexcess, fields percent require/100. Cachedcurrent202608CRSPvintage has1970..202608dates; dates/schema checked, economicpayload notdecoded here.','still_missing':'Calendar1994-2014 andoriginalpublication-vintage/exactTable7input/config acceptance. Publicaggregate primitives areavailable; proprietaryindividualstockCRSP isnot established asblocker foraggregate source.','fixed_admitted_diagnostic':'Afterallgates one current-vintage nontrading source-form diagnostic on2015-01-01..2026-08-31 calendaroverlap. Mkt=Mkt-RF+RF; lag5/21/63weekday excesswealth=prod(1+Mkt)-prod(1+RF), holidayszero; eachhorizon full-overlapglobal20%quintile;3nestedstates asTable7depth. Comparelatephase9..13,19..23,29..33 vsoddphase4..8,14..18,24..28, conditionalcurrent-dayMkt-RF OLS contrast/HAC5. Fullsamplebuckets intentionallydescriptive andnotcausalforecasts. Excludeweek0 andtailbeyond33; no oldpre-FOMC simulation. Diagnostic calendarusesactualpastmeetingdates; notAPP activation. No portfolio/selection or original1994-2016replicationclaim.','vintage_limits':'Knowncurrent-vintage source; source RF switchesIbbotson throughMay2024 toICEBofA fromJune2024 perbounddefinition. Original2018data vintage notverified. Doesnotreplace frozen causalSPY/BIL APPfeatures or cashyield.'}
write('french-source-availability.json',french)

ledger=json.loads((P/'sources/download-ledger.json').read_text())
calendar=json.loads((P/'calendar-packet-v1.json').read_text())
for e in calendar['events']+calendar['excluded']:
 receipt=next(x for x in ledger if Path(x.get('path','')).name==Path(e['source']['path']).name)
 e['published_date']=e.pop('published_at');e['publication_date_precision']='day'
 e['published_at']=None;e['observed_publication_timestamp']=None;e['visible_at']=None
 e['fetched_at']=receipt.get('fetched_at_utc',receipt.get('fetched_at'));e['first_seen_at']=e['fetched_at']
 e['publication_evidence']='Datedofficial historicalmeetingheading/statementlink; intradaytimestampnotobserved.'
 e['replay_availability_rule']='Conservative researchactivation atfirstnativeUS-equitysessionclose strictlyaftermeetingdate, notobservedPITpublication.'
 activate=next_us_equity_session(datetime.fromisoformat(e['date']).date());cl=us_equity_session_close(activate)
 e['replay_activation_at']=datetime.combine(activate,cl,tzinfo=ZoneInfo('America/New_York')).astimezone(UTC).isoformat()
 e['actual_meeting_date_phase_anchor']=e['date'];e['prompt_hash']=None;e['input_hash']=e['source']['sha256']
calendar.update(scope='93past scheduledstatements withactualmeetingdate; dateprecisionpublicationevidence andconservative nextsession-close activation explicitlyseparate. No actualpublicationtimestamp/firstseen/PIT certification.',activation_calendar=bind('open_composer/market_sessions.py'))
write('calendar-packet.json',calendar)

fed=USFederalHolidayCalendar().holidays(start='2014-01-01',end='2027-12-31')
holiday_dates={d.date() for d in fed};sessions=us_equity_session_dates(datetime(2014,1,1).date(),datetime(2027,12,31).date())
cashcal={'schema_version':1,'status':'explicit_unverified_research_cash_availability_proxy','trading_calendar':bind('open_composer/market_sessions.py'),'federal_holiday_rules':bind(inspect.getfile(USFederalHolidayCalendar)),'pandas_version':pd.__version__,'eligible_dates':[d.isoformat() for d in sessions if d not in holiday_dates],'excluded_federal_dates':[d.isoformat() for d in sorted(holiday_dates)],'phase':'AllMonday-Fridaydays via numpy.busday_count, exchangeholidaysincluded. Distinctfromtrading/cash calendars.','sale_cash_rule':'Counteligible datesstrictlyafter saledate:4dates for2015-2017,3dates from2018-01-01..2024-05-27,2dates from2024-05-28. Oneextraeligible-daybuffer relative nominalnormalT3/T2/T1, withT3 conservativelyretainedthrough2017yearend becauseprecise2017transitiondate isnotverifiedhere. ThisisnotactualDTC settlement orbrokercredit.','dividend_cash_rule':'Actualbound payabledate remainsmandatory; receivable untilfirsteligibleproxydate strictlyafter payabledate. No inferredpaydate and no exdatecash.','transition_evidence':bind(P/'sources/settlement-transition.txt'),'limits':'SEC binds2017T3->T2year and2024-05-28T2->T1, notcompleteDTCcalendar. Unionclosure plusbuffer isdeclared researchconvention, notguaranteeagainstfails/brokerdelay. Actualsettledcash/PITexecution/paperready gatesremainfalse.'}
write('cash-calendar.json',cashcal)
plan['source_fidelity']['definitions']=plan['source_fidelity']['definitions'].replace('Source CRSP aggregate and Tbill1994-2016 not available: no faithful complete original replication/global refutation promised.','Originalfootnote4 publicFrench aggregate Mkt-RF/RF primitives AREavailable in boundexisting officialZIP; originalvintage/calendar1994-2014 andpreciseoriginalinput acceptance remainunready. No faithful complete source/globalrefutation claim.')
plan['source_fidelity']['available_aggregate_and_diagnostic']=bind(P/'french-source-availability.json')
plan['information_clock']['calendar']=bind(P/'calendar-packet.json')
plan['information_clock']['event_asof']='Sourcecalendar establishesactualmeeting/publicationDATES, notobservedintradaypublicationtimes. published_at/visible_at remainnull, actualsourceHTTP fetched_at retained. Conservative replayactivation atnativeexchangeclose offirstsession strictlyafter actualscheduledmeetingdate. Atclose t use latestanchor whose replay_activation_at<=that actualsessionclose; phase remains measuredfromactualmeetingdate, notactivationdate. No futuremeetingdate, canceledorunscheduledanchor, same-dayassumedtimestamp orPITcertificate.'
plan['funded_execution']['settlement']='Threeclocks: weekdayphase countsallMonday-Friday inclmarket holidays; trading/close fromboundnativeUS-equitycalendar; eligibleproxycashdays=tradingdates minusboundpandasUSFederalHolidayCalendar. Salesavailable on4th eligible date strictlyaftertrade for2015-2017,3rd for2018-01-01..2024-05-27,2nd from2024-05-28. Extra1daybuffer,2017T3retainedthroughyearend; SECtransitionbound butactualsettlementcalendar/brokercreditUNVERIFIED. Cashbudgetisconditionalfundedresearchproxy, neververifiedactualcash. Dividendex-date entitledpriorholdings createNAVreceivable; actualpayable_date required, cash firsteligibleproxyday strictlyafterit. No borrowing/futuresalecredit/inferredpaydate.'
plan['funded_execution']['cash_calendar']=bind(P/'cash-calendar.json')
plan['funded_execution']['cash_clock_diagnostic']='One immediate-salecredit sensitivity withsamefixedpolicy/risk/cost definitions, explicitlyunqualified/unfundedcashclockdiagnostic; notactualcash-account result, selectablecandidate ordeployableevidence. Itisolateseconomicpenalty fromcashavailability proxy ratherthan silentlyloosening itafterweakreturns.'
plan['funded_execution']['nav']=plan['funded_execution']['nav'].replace('settledcash','proxy-availablecash')
plan['funded_execution']['verified_actual_settled_cash_claim']=False
plan['resources']['source_used']=40
plan['resources']['source_addendum']='Final1publicunit SEC2024-62 consumed; new40/40 exhausted. Directmeteredbodies7448389 bytesunchanged; web/HTTP-error unreadtransferunknown. ExistingFrench reused,no re-download ornewmarketrequest.'
plan['resources']['request_scope']=plan['resources']['request_scope'].replace('samefixed3symbols','samefixed3symbols')
plan['created_at']=NOW;plan['revision']='R1/R2/R3 independentreview corrections only; candidate/risk/cost/seen/caps preserved.'
write('scientific-plan.json',plan)
write('execution-contract.json',{k:plan[k] for k in ['schema_version','author','information_clock','funded_execution','host','resources','promotion_eligible','paper_trading_allowed','broker_activity_allowed']})
early=json.loads((P/'early-input-evidence-v1.json').read_text());early.update(calendar=bind(P/'calendar-packet.json'),available_french_source=bind(P/'french-source-availability.json'),cash_proxy=bind(P/'cash-calendar.json'),gate='Sourceprimitive availability isnot inputacceptance; actualmarketactions/continuity/source vintage/PIT/verifiedsettlement remainconditional/unready asdeclared.');write('early-input-evidence.json',early)
plan['early_input']=bind(P/'early-input-evidence.json');write('scientific-plan.json',plan)
revision={'schema_version':1,'author':plan['author'],'as_of':NOW,'old_plan':bind(P/'scientific-plan-v1.json'),'old_contract':bind(P/'execution-contract-v1.json'),'old_review':bind(P/'independent-plan-review-v1.json'),'new_plan':bind(P/'scientific-plan.json'),'new_contract':bind(P/'execution-contract.json'),'diffs':{'R1':bind(P/'french-source-availability.json'),'R2':bind(P/'calendar-packet.json'),'R3':bind(P/'cash-calendar.json')},'preserved':['same6primary source nestedstate/actualSPYSSO','same14controls','20/40bp and20000/4000 capital','allseen/noOOS/nomodel','40newsource/24market/16MiB/7200CPU caps','allreadinessfalse'],'added_diagnostics':'R1 onecurrentvintageFrench latecycle contrast, noportfolio/sourceglobalreplication; R3 immediate-salecredit diagnosticunqualified, notfundedstresspass.'}
write('scientific-plan-revision.json',revision)
state=json.loads((P/'current-state.json').read_text());state.update(scientific_plan=bind(P/'scientific-plan.json'),status='R1_R2_R3_difference_review_pending',new_source_request_units_used=40,new_economic_CPU_coreseconds=0,next_action='Independent scientificdelta acceptance; source/input andimplementationpreparationcontinues; no economics.');write('current-state.json',state)
print('newplan',bind(P/'scientific-plan.json'));print('cashcal',len(cashcal['eligible_dates']));print('publication precision',calendar['events'][0]['published_at'],calendar['events'][0]['replay_activation_at'])
