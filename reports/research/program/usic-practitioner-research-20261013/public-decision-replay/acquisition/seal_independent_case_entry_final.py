import json,hashlib,re
from pathlib import Path
from datetime import datetime,timezone
P=Path(__file__).resolve().parent;ROOT=Path.cwd()
def bind(p):
 p=Path(p);return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
oldpath=P/'independent-entry-acceptance.json';old=oldpath.read_bytes();assert hashlib.sha256(old).hexdigest()=='b7d1fec83dcbe3a74b7a895b3131d69f31d86e328443ee10eaa95fc7eb87ad79'
archive=P/'independent-entry-acceptance-attempt1.json';assert not archive.exists();archive.write_bytes(old)
m=json.loads((P/'request-manifest.json').read_text());v=json.loads((P/'independent-entry-repair-verification.json').read_text());assert v['status']=='pass'
for b in m['entry_bindings']:assert bind(ROOT/b['path'])==b
t=(P/'independent-entry-repair-resource.txt').read_text();actual=round(sum(float(re.search(k+r' time \(seconds\): ([\d.]+)',t)[1]) for k in ['User','System']),2);assert actual==1.35
charge=round(actual+2,2);used=round(288.15+charge,2)
r=json.loads(old)
r.update(as_of_utc=datetime.now(timezone.utc).isoformat(),verdict='approve_bounded_case_input_acquisition',accepted_for_execution=True,request_manifest=bind(P/'request-manifest.json'),entry_bindings=m['entry_bindings'],allocation_status='admitted_for_exact_bound_market_inputs_only',prior_entry_review=bind(archive),prior_request_manifest=bind(P/'request-manifest-attempt1.json'),required_corrections=[],economic_execution_admitted=False)
r['scope_judgment']='Same exact7objects/4frozencases approved foractualintake underexistingRoot authority. Enable originalreservationUSIC-PUBLIC-DECISION-REPLAY-exact-case-input-01,19calls/39845888B only; nosecondreservation orallocation. Alloriginal dates/params/pagecaps/reuse/unknownhandling unchanged.'
r['resolved_E1']=dict(status='accepted_same_semantics_path_binding_repair',actual_diff='Resolve repository-relative orabsolute paths to sameboundplan; exactSHA equality retained. Inversepatch reconstructsoldcodebytes exactly.',positive_guard=True,rejected=v['negative_guards_rejected'],current_request_manifest=bind(P/'request-manifest.json'),current_code=v['entry_code'],all11bindings_verified=True)
r['accepted_checks']['bindings']='Current11entrybindings pass; manifestf32512978ed96228bc240672fe2098310791890f660ed3aadc707a3cc25629aa changesonlyentrycodebinding fromprior3738. Prior63actualcalls/44065545B andcaseclocks/reuse/inertcollectorchecks inherited fromsameattemptverification.'
r['continuation']='Originalowner maynow execute theexactboundcaseinputwrapper afterfreshmemory/CPU0/currentowner/hold checks. Retainallentities/tokens/failures/unknownbytecharges anddo notredistributeunusedslots. Continueactualinputacceptance,minimalreplayimplementation/native andseparatebounded economicadmission; marketentrydoesnotgrantstrategyreturns or7200CPU.'
r['resource']=dict(pool='Originalcomparison1000',prior_scope_review_start_CPU=283.01,prior_completed_attempt_charge_CPU=5.14,prior_cumulative_CPU=288.15,current_repair_inclusive_actual_CPU=actual,current_smallread_setup_archive_seal_handoff_unknown_CPU=2,current_repair_total_charge_CPU=charge,combined_scope_and_repair_charge_CPU=8.49,cumulative_CPU=used,remaining_CPU=round(1000-used,2),settlement='If5.14alreadyrecorded, addonly3.35; otherwiseentireentryreviewdeltafrom283.01is8.49. Do notchargereceiptarchiveorinnerCPUagain.',fresh_memory_MiB=400,CPU_affinity=[0],RSS_KiB=25980,exit=0,inner0_580331_notaddedtwice=True,real_HTTP_credentials_fits_economics=0,author_HFpools_notused=True)
r['repair_verification']=bind(P/'independent-entry-repair-verification.json');r['repair_check_code']=bind(P/'independent_verify_entry_repair.py');r['repair_resource']=bind(P/'independent-entry-repair-resource.txt')
oldpath.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(receipt=bind(oldpath),current_delta_charge=charge,whole_entry_review_charge=8.49,comparison_cumulative=used,comparison_remaining=round(1000-used,2))))
