"""Exact next-eligible1280MiB/science32 capacity reception, not entry permission."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat

REPO = Path('/root/codex-test/open-composer')
P = REPO/'reports/research/program/owner-profit-delivery-plan-20261017'
SCIENCE = P/'current-paper-science-20261020'
ROOT = Path(__file__).resolve().parent
OPS = REPO/'reports/ops/disk-audit-20261015'
TASK = 'CURRENT-PAPER-SCIENCE-20261020'
SESSION = 'SIX-NEXT-ELIGIBLE-SESSION-20261021'
AGGREGATE_TASK = 'SIX-PAPER-CURRENT-SESSION-COMPLETION-20261020'
EPISODE = 'SIX-PAPER-NEXT-ELIGIBLE-SESSION-20261021'
PEER = '93af0483-230a-4632-8b48-c63cd53a01f7'
RECEIPT = OPS/'capacity-six-next-session-whole1280MiB-M2-admission-20261020.json'
RECEIPT_SHA = 'bab36a7c236f215e2cc024873a37178b2819e779accbfaac81f4000535162a6a'
PROPOSAL_SHA = '04e0f725743f0d6af1b28ca3fa5441b9d68b3b1760c7eef884ca88d9ef1ebd8e'
NORMAL_SHA = 'c14dd1dad10295e0aae485175dc8ca3e8937c8761844208d089b4920c253c187'


def now():
    return datetime.now(timezone.utc).isoformat()


def clock(value):
    d = datetime.fromisoformat(value.replace('Z','+00:00'))
    assert d.tzinfo is not None
    return d.astimezone(timezone.utc)


def canonical(value):
    p = Path(value)
    assert p.is_absolute() and p.resolve() == p and not p.is_symlink(), 'Noncanonical root/path'
    return p


def binding(path):
    p = canonical(path)
    b = p.read_bytes()
    return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def checked(row, expected=None):
    assert type(row) is dict and set(row)=={'path','bytes','sha256'}
    p = canonical(row['path'])
    assert expected is None or p == canonical(expected)
    assert binding(p)==row
    return p


def load(path):
    return json.loads(canonical(path).read_text())


def read_capacity_context(context_row):
    """Exact immutable schema checks only; NOT independent acceptance."""
    path = checked(context_row)
    assert path.parent==ROOT and path.name.startswith('capacity-context-next-session-')
    c = load(path)
    assert c['task_id']==TASK and c['session_id']==SESSION and c['aggregate_task_id']==AGGREGATE_TASK and c['episode_id']==EPISODE
    assert c['guard_code']==binding(__file__)
    receipt = load(checked(c['receipt'],RECEIPT))
    assert c['receipt']['sha256']==RECEIPT_SHA
    assert receipt['task_id']==AGGREGATE_TASK and receipt['episode_id']==EPISODE
    assert receipt['admitted'] is receipt['capacity_only'] is True
    assert receipt['decision']=='admitted_capacity_only' and receipt['replaces_instead_of_adding'] is True
    assert receipt['accepted_whole_route_peak_bytes']==c['whole_cap_bytes']==1342177280
    assert receipt['request_bindings']['actual_six_route_current_session_whole_route_proposal']==c['proposal']
    assert c['proposal']['sha256']==PROPOSAL_SHA
    proposal = load(checked(c['proposal'],P/'paper-delivery/preopen-20261020/next-session-complete-whole-storage-proposal-M2-aggregate-capture.json'))
    assert proposal['task_id']==AGGREGATE_TASK and proposal['episode_id']==EPISODE
    assert proposal['total_whole_route_peak_bytes']==c['whole_cap_bytes']
    guard = receipt['guard_contract']
    assert guard['receipt_task_id']==AGGREGATE_TASK
    assert guard['proposal_binding_field']=='request_bindings.actual_six_route_current_session_whole_route_proposal'
    assert guard['accepted_peak_field']=='accepted_whole_route_peak_bytes'
    roots = c['owned_roots']
    assert roots==receipt['owned_roots']==guard['required_roots']==proposal['owned_roots']
    assert roots==[v['path'] for v in proposal['current_root_allocation']]
    assert roots==[v['root'] for v in receipt['current_root_allocation']]
    paths = [canonical(x) for x in roots]
    assert len(set(paths))==17 and SCIENCE in paths
    assert all(not a.is_relative_to(b) for a in paths for b in paths if a!=b)
    previous = load(checked(c['preserved_previous384']))
    assert c['preserved_previous384']==receipt['request_bindings']['preserved_previous384']
    assert previous['accepted_whole_route_peak_bytes']==402653184 and roots[:16]==previous['owned_roots']
    assert paths[-1]==P/'paper-delivery/preopen-20261021'
    prior1 = load(checked(c['preserved_previous1GiB']))
    assert c['preserved_previous1GiB']==receipt['replaces_previous_capacity_receipt']==receipt['request_bindings']['preserved_previous1GiB']
    assert prior1['accepted_whole_route_peak_bytes']==1073741824 and prior1['owned_roots']==roots
    assert c['previous_current1GiB_normal']==receipt['request_bindings']['previous_current1GiB_complete_normal']
    checked(c['previous_current1GiB_normal'])
    assert c['accepted_capture_contract']==receipt['accepted_capture_contract']
    capture=c['accepted_capture_contract']
    assert capture['max_initial_slot_payload_bytes']==1441792 and capture['max_initial_target_assets']==32
    assert capture['financial_freshness_seconds']==15
    assert capture['no_captured_financial_state_reuse'] is True
    assert capture['unknown_page_asset_or_large_body_uses_original_fresh_full_guard'] is True
    component = receipt['accepted_scientific_component']
    assert component['task_id']==TASK and component['replaces20_not_independent32_plus20'] is True
    assert c['scientific_owned_roots']==component['scientific_owned_roots']==[str(SCIENCE)]
    assert c['scientific_cap_bytes']==component['accepted_whole_route_peak_bytes']==guard['scientific_peak_bytes']==33554432
    assert component['proposal']==c['scientific_proposal']==receipt['request_bindings']['actual_next_session_science_definition_and_storage']
    assert c['scientific_proposal']['sha256']=='89bcf5a2653ad85fa4547b88c526df1c4e131b8b5adc6654b9bf5e03f29ea89a'
    checked(c['scientific_proposal'],ROOT/'next-session-contract-and-storage-M1.json')
    assert c['scientific_outside_once_bytes']==1048576 and c['aggregate_outside_once_bytes']==3145728
    assert guard['scientific_outside1MiB_inside_component_once'] is guard['aggregate_outside3MiB_inside_aggregate_once'] is True
    assert receipt['whole_route_accounting']['outside_uncredited_future_reserve_inside_whole_once_bytes']==c['aggregate_outside_once_bytes']
    assert c['normal_forecast']==receipt['request_bindings']['current_complete_normal_forecast']==receipt['request_bindings']['postpublication_complete_normal']==receipt['complete_paper_forecast']['receipt']
    assert c['normal_forecast']['sha256']==NORMAL_SHA
    normal = load(checked(c['normal_forecast']))
    assert normal['required_available_bytes']==receipt['complete_paper_forecast']['required_available_bytes']==10919282270
    assert normal['enabled_upstream_tables']==receipt['complete_paper_forecast']['enabled_upstream_tables'] and len(normal['enabled_upstream_tables'])==11
    assert normal['live_stages']==receipt['complete_paper_forecast']['live_stages'] and len(normal['live_stages'])==7
    assert normal['spill_and_service_already_included_once'] is receipt['complete_paper_forecast']['fetch_true_complete_route'] is True
    assert receipt['complete_paper_forecast']['normal_source_fetch2GiB_spill2GiB_service512MiB_included_once'] is True
    assert c['postpublication_normal_context']==receipt['request_bindings']['postpublication_normal_context']
    checked(c['postpublication_normal_context'])
    assert c['previous_normal']==receipt['request_bindings']['previous_postpublication_normal']==receipt['complete_paper_forecast']['previous_d289_retained']
    checked(c['previous_normal'])
    assert c['Main']==receipt['request_bindings']['Main_next_eligible_session']
    checked(c['Main'])
    assert c['operating_coordination']==receipt['request_bindings']['actual_next_session_operating_coordination']
    op = load(checked(c['operating_coordination']))
    assert op['independent'] is True and op['reviewer']=='66ad4b54-ec62-400b-9a03-a29682cf58e6'
    assert op['accepted_operating_clock_coordination'] is op['accepted_continued_H5_actual_episode_linkage'] is True
    facts = receipt['current_physical_fact']
    for key,task,cap,field in [('CASH','CASH-BACKED-EARNINGS-INFORMATION-20261019',12582912,'accepted_whole_route_peak_bytes'),('SIP','QUANT1-SIP-CURRENT-DAILY-RECOVERY-20261020',1073741824,'accepted_incremental_stage_peak_bytes')]:
        other = load(checked(c[key+'_receipt']))
        assert other['task_id']==task and other['admitted'] is other['capacity_only'] is True
        assert c[key+'_full_bytes']==other[field]==cap
    checked(c['Astra_receipt'])
    assert c['terminal_once_bytes']==facts['terminal_once_bytes']==65536
    assert c['Astra_once_bytes']==facts['Astra_once_bytes']==12288
    assert c['CASH_full_bytes']==facts['CASH_FULL_future12MiB_bytes']
    assert c['SIP_full_bytes']==facts['old_SIP_FULL_future1GiB_bytes']
    assert c['whole_cap_bytes']==facts['paper_FULL_future1280MiB_bytes']
    assert c['physical_credit_bytes']==facts['physical_credits_used_bytes']==0
    required = normal['required_available_bytes']+c['whole_cap_bytes']+c['CASH_full_bytes']+c['SIP_full_bytes']+c['terminal_once_bytes']+c['Astra_once_bytes']
    assert c['physical_floor_bytes']==facts['required_available_bytes']==required==13347862110
    assert c['next_date_SIP_bulk_status']==facts['new_next_date_SIP_bulk_status']=='UNADMITTED_UNKNOWN_NOT_ZERO_NOT_BORROWED'
    for row in c['tracked_normal_source_completions']:
        complete = load(checked(row))
        assert complete['task_id']=='QUANT1-SIP-CURRENT-DAILY-RECOVERY-20261020'
        assert complete['status']=='source_stage_complete' and complete['exit']==0
        assert clock(complete['at'])<=clock(normal['at_utc']), 'Receive genuinely later full normal after source publication'
    assert clock(normal['at_utc'])<=clock(receipt['at_utc'])<=clock(c['created_at'])<=clock(now())
    return c, normal


def receive_capacity_context(context_row=None, review_row=None):
    pointer = load(ROOT/'capacity-pointer-next-session.json')
    assert pointer['task_id']==TASK and pointer['session_id']==SESSION
    if context_row is None:
        context_row,review_row=pointer['context'],pointer['review']
    c, normal = read_capacity_context(context_row)
    review_path = checked(review_row)
    assert review_path.parent==ROOT and review_path.name.startswith('independent-next-session-capacity-reception-')
    review = load(review_path)
    assert review['task_id']==TASK and review['session_id']==SESSION and review['reviewer']==PEER
    assert review['independent'] is True and review['accepted'] is True and review['capacity_guard_implementation_accepted'] is True
    assert review['target']==context_row and review['guard_code']==c['guard_code']
    return c,normal,context_row,review_row


def allocated(roots):
    paths = [canonical(v) for v in roots]
    assert len(set(paths))==len(paths)
    assert all(not a.is_relative_to(b) for a in paths for b in paths if a!=b)
    seen,total=set(),0
    def error(value):
        raise value
    for root in paths:
        if not root.exists():
            continue
        before=root.lstat()
        assert stat.S_ISDIR(before.st_mode)
        for folder,dirs,files in os.walk(root,followlinks=False,onerror=error):
            folder=canonical(folder)
            dirs[:]=[v for v in dirs if not (folder/v).is_symlink()]
            for path in [folder,*[folder/v for v in files]]:
                s=path.lstat();key=(s.st_dev,s.st_ino)
                if stat.S_ISLNK(s.st_mode) or key in seen:
                    continue
                seen.add(key)
                if stat.S_ISDIR(s.st_mode) or (stat.S_ISREG(s.st_mode) and s.st_nlink==1):
                    assert s.st_blocks>=0
                    total+=s.st_blocks*512
        after=root.lstat()
        assert (before.st_dev,before.st_ino)==(after.st_dev,after.st_ino) and not stat.S_ISLNK(after.st_mode)
    return total


def check_room(c, normal_bytes, route_bytes, science_bytes, free_bytes, required_inside_bytes=0, required_science_bytes=0):
    values=[normal_bytes,route_bytes,science_bytes,free_bytes,required_inside_bytes,required_science_bytes]
    assert all(type(x) is int and x>=0 for x in values)
    assert required_science_bytes<=required_inside_bytes and science_bytes<=route_bytes
    assert route_bytes+c['aggregate_outside_once_bytes']+required_inside_bytes<=c['whole_cap_bytes'], 'Whole route overflow; preserve partials'
    assert science_bytes+c['scientific_outside_once_bytes']+required_science_bytes<=c['scientific_cap_bytes'], 'Science overflow; preserve partials'
    floor=normal_bytes+c['whole_cap_bytes']+c['CASH_full_bytes']+c['SIP_full_bytes']+c['terminal_once_bytes']+c['Astra_once_bytes']
    assert free_bytes>=floor+required_inside_bytes, 'Full concurrent floor would be lost; preserve partials'
    return floor


def guard_write(required_inside_bytes=0, required_science_bytes=None, *, context_row=None, review_row=None):
    """Fresh full uncredited guard; callers include complete atomic/partial bytes.

    Scientific bytes are a subset of route bytes, never a second reservation.
    This does not check a source clock or grant native/account permission.
    """
    c,normal,context_row,review_row=receive_capacity_context(context_row,review_row)
    pointer=load(ROOT/'capacity-pointer-next-session.json')
    assert pointer['context']==context_row and pointer['review']==review_row, 'Active capacity context changed during invocation'
    if required_science_bytes is None:
        required_science_bytes=required_inside_bytes
    own=allocated(c['scientific_owned_roots']);route=allocated(c['owned_roots'])
    fs=os.statvfs(REPO);free=fs.f_bavail*fs.f_frsize
    floor=check_room(c,normal['required_available_bytes'],route,own,free,required_inside_bytes,required_science_bytes)
    return dict(context=context_row,review=review_row,receipt=c['receipt'],actual_at=now(),
                free_bytes=free,required_available_bytes=floor,normal_bytes=normal['required_available_bytes'],
                route_allocated_bytes=route,scientific_allocated_bytes=own,
                next_inside_allocation_bound_bytes=required_inside_bytes,next_science_allocation_bound_bytes=required_science_bytes,
                aggregate_outside_uncredited_once_bytes=c['aggregate_outside_once_bytes'],
                scientific_outside_subset_once_bytes=c['scientific_outside_once_bytes'],
                physical_credit_or_release_bytes=0,margin_bytes=free-floor,
                next_date_normal_bulk_granted=False,source_native_account_or_order_go=False)
