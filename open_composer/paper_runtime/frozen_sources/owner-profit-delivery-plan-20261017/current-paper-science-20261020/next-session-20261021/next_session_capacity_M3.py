"""Actual internal science40 reception, whole1280 unchanged; no entry grant."""
import os
import next_session_capacity_M2 as prior
from next_session_capacity_M2 import (REPO,P,SCIENCE,ROOT,OPS,TASK,SESSION,AGGREGATE_TASK,EPISODE,PEER,now,clock,canonical,binding,checked,load,allocated,check_room)
RECEIPT=OPS/'capacity-science40-within-whole1280-internal-admission-20261021.json'
RECEIPT_SHA='d6dd9de3e80c8e4727a3fc602cfd762b08b0d190a4c4c22df37fb6cba825c256'
POINTER=ROOT/'capacity-pointer-next-session-science40.json'

def read_capacity_context(context_row):
    path=checked(context_row)
    assert path.parent==ROOT and path.name=='capacity-context-next-session-science40-M3.json'
    c=load(path)
    assert c['task_id']==TASK and c['session_id']==SESSION and c['aggregate_task_id']==AGGREGATE_TASK and c['episode_id']==EPISODE
    assert c['guard_code']==binding(__file__)
    old,old_normal=prior.read_capacity_context(c['preserved_source32_context'])
    rr=load(checked(c['preserved_source32_review']))
    assert rr['task_id']==TASK and rr['session_id']==SESSION and rr['reviewer']==PEER and rr['independent'] is True
    assert rr['accepted'] is rr['capacity_guard_implementation_accepted'] is True
    assert rr['target']==c['preserved_source32_context'] and rr['guard_code']==old['guard_code']
    receipt=load(checked(c['receipt'],RECEIPT));assert c['receipt']['sha256']==RECEIPT_SHA
    assert receipt['task_id']==AGGREGATE_TASK and receipt['episode_id']==EPISODE
    assert receipt['admitted'] is receipt['capacity_only'] is True and receipt['decision']=='admitted_capacity_only'
    assert receipt['accepted_whole_route_peak_bytes']==c['whole_cap_bytes']==old['whole_cap_bytes']==1342177280
    assert receipt['replaces_previous_capacity_receipt']==old['receipt']
    assert c['proposal']==old['proposal']==receipt['request_bindings']['actual_six_route_current_session_whole_route_proposal']
    assert c['owned_roots']==old['owned_roots']==receipt['owned_roots']==receipt['guard_contract']['required_roots'] and len(c['owned_roots'])==17
    assert c['scientific_owned_roots']==old['scientific_owned_roots']==[str(SCIENCE)]
    guard=receipt['guard_contract'];component=receipt['accepted_scientific_component']
    assert component['task_id']==TASK and component['replaces32_inside_whole_not_extra40_plus32'] is True
    assert c['scientific_cap_bytes']==component['accepted_whole_route_peak_bytes']==receipt['accepted_scientific_subcap_bytes']==guard['scientific_peak_bytes']==41943040
    assert component['previous_whole_route_peak_bytes']==old['scientific_cap_bytes']==33554432
    assert c['selection']==receipt['request_bindings']['actual_internal_scientific_suballocation_selection']==component['reallocation_selection']
    assert c['selection']['sha256']=='7bec3df22e488218c3de9446849c762847e9ffd0e229e22767df40bc4f6af4cd';checked(c['selection'])
    assert c['remaining_worksheet']==receipt['request_bindings']['actual_complete_scientific_remaining_worksheet']==component['proposal']==component['complete_remaining_worksheet']
    assert c['remaining_worksheet']['sha256']=='f3ae07b0a3006a1a22ad03066bcf42149d8af84029e07306c5bdad56e751ffbc';checked(c['remaining_worksheet'])
    assert component['original_scientific_definition']==old['scientific_proposal']
    assert c['scientific_outside_once_bytes']==old['scientific_outside_once_bytes']==1048576
    assert c['aggregate_outside_once_bytes']==old['aggregate_outside_once_bytes']==3145728
    assert guard['scientific_outside1MiB_inside_component_once'] is guard['aggregate_outside3MiB_inside_aggregate_once'] is True
    assert c['normal_forecast']==receipt['request_bindings']['current_complete_normal_forecast']==receipt['request_bindings']['postpublication_complete_normal']==receipt['complete_paper_forecast']['receipt']
    assert c['normal_forecast']['sha256']=='85390f4c9d969d0f6b56f772851751cc88f73658165b7c2b2306b534283594f3'
    normal=load(checked(c['normal_forecast']))
    assert normal['required_available_bytes']==receipt['complete_paper_forecast']['required_available_bytes']==10919282270
    assert len(normal['enabled_upstream_tables'])==11 and len(normal['live_stages'])==7
    assert normal['enabled_upstream_tables']==old_normal['enabled_upstream_tables'] and normal['live_stages']==old_normal['live_stages']
    assert normal['spill_and_service_already_included_once'] is receipt['complete_paper_forecast']['fetch_true_complete_route'] is True
    assert c['postpublication_normal_context']==receipt['request_bindings']['postpublication_normal_context']==old['postpublication_normal_context'];checked(c['postpublication_normal_context'])
    for row in c['tracked_normal_source_completions']:
        d=load(checked(row));assert d['status']=='source_stage_complete' and d['exit']==0 and clock(d['at'])<=clock(normal['at_utc'])
    for key in ['CASH_full_bytes','SIP_full_bytes','terminal_once_bytes','Astra_once_bytes','physical_credit_bytes','tracked_normal_source_completions']:
        assert c[key]==old[key]
    floor=normal['required_available_bytes']+c['whole_cap_bytes']+c['CASH_full_bytes']+c['SIP_full_bytes']+c['terminal_once_bytes']+c['Astra_once_bytes']
    assert c['physical_floor_bytes']==receipt['current_physical_fact']['required_available_bytes']==floor==13347862110 and c['physical_credit_bytes']==0
    assert c['next_date_SIP_bulk_status']==old['next_date_SIP_bulk_status']==receipt['current_physical_fact']['new_next_date_SIP_bulk_status']=='UNADMITTED_UNKNOWN_NOT_ZERO_NOT_BORROWED'
    clarification=load(checked(c['field_clarification']))
    assert c['field_clarification']['sha256']=='5eac5495b0b5623a93d893e26be7d7a0fad2acb5ed93657ade87a953cded544e'
    assert c['capture_contract_historical_only']==old['accepted_capture_contract']
    # Capacity never chooses 15/60 financial freshness. Main/actual operating review do.
    assert c['financial_policy_granted'] is c['source_native_account_or_order_go'] is False
    assert clock(old_normal['at_utc'])<=clock(normal['at_utc'])<=clock(receipt['at_utc'])<=clock(c['created_at'])<=clock(now())
    return c,normal

def receive_capacity_context(context_row=None,review_row=None):
    if context_row is None:
        pointer=load(POINTER);assert pointer['task_id']==TASK and pointer['session_id']==SESSION
        context_row,review_row=pointer['context'],pointer['review']
    c,normal=read_capacity_context(context_row);p=checked(review_row)
    assert p.parent==ROOT and p.name.startswith('independent-next-session-capacity-reception-')
    rr=load(p)
    assert rr['task_id']==TASK and rr['session_id']==SESSION and rr['reviewer']==PEER and rr['independent'] is True
    assert rr['accepted'] is rr['capacity_guard_implementation_accepted'] is True
    assert rr['target']==context_row and rr['guard_code']==c['guard_code']
    return c,normal,context_row,review_row

def guard_write(required_inside_bytes=0,required_science_bytes=None,*,context_row=None,review_row=None):
    c,normal,context_row,review_row=receive_capacity_context(context_row,review_row)
    pointer=load(POINTER);assert pointer['context']==context_row and pointer['review']==review_row
    if required_science_bytes is None:required_science_bytes=required_inside_bytes
    own=allocated(c['scientific_owned_roots']);route=allocated(c['owned_roots']);fs=os.statvfs(REPO);free=fs.f_bavail*fs.f_frsize
    floor=check_room(c,normal['required_available_bytes'],route,own,free,required_inside_bytes,required_science_bytes)
    return dict(context=context_row,review=review_row,receipt=c['receipt'],actual_at=now(),free_bytes=free,required_available_bytes=floor,
        normal_bytes=normal['required_available_bytes'],route_allocated_bytes=route,scientific_allocated_bytes=own,
        next_inside_allocation_bound_bytes=required_inside_bytes,next_science_allocation_bound_bytes=required_science_bytes,
        aggregate_outside_uncredited_once_bytes=c['aggregate_outside_once_bytes'],scientific_outside_subset_once_bytes=c['scientific_outside_once_bytes'],
        physical_credit_or_release_bytes=0,margin_bytes=free-floor,next_date_normal_bulk_granted=False,source_native_account_or_order_go=False)
