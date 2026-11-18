"""Fixed Oct21 source capture/receiver; imports never authorize or fetch data."""
import ast
import copy
import json
from pathlib import Path

import next_source_common as c
import next_source_local as local

D21=c.REPO/'reports/research/program/owner-profit-delivery-plan-20261017/paper-delivery/preopen-20261021'
D20=D21.parent/'preopen-20261020'
TRANSPORT=D21/'next-session-source-transport-manifest.json'
TRANSPORT_REVIEW=D21/'independent-next-session-source-transport-review-66ad.json'
TRANSPORT_MODULE=D21/'next_session_source_transport.py'
OPERATING_PEER='66ad4b54-ec62-400b-9a03-a29682cf58e6'
FUTURE=c.REPO/'reports/research/program/owner-profit-delivery-plan-20261017/candidate-contribution/future-input-receiver'


def receive_transport(proof=None):
    """Metadata only, before transport import, lazy factory or constructor."""
    proof=proof or dict(manifest=c.binding(TRANSPORT),review=c.binding(TRANSPORT_REVIEW))
    manifest=c.load(c.checked(proof['manifest'],TRANSPORT))
    review=c.load(c.checked(proof['review'],TRANSPORT_REVIEW))
    scientific=c.code()
    assert manifest['task_id']==review['task_id']==c.TASK and manifest['session_id']==review['session_id']==c.SESSION
    assert review['reviewer']==OPERATING_PEER and review['independent'] is True
    assert review['verdict']=='approve_implementation' and review['accepted_for_source_transport'] is True
    assert review['target']==proof['manifest']
    assert review['source_plan']==manifest['source_plan']==c.binding(c.ROOT/'next-session-source-plan-M1.json')
    assert review['bindings']['scientific_manifest']==manifest['scientific_manifest']==scientific['manifest']
    assert review['bindings']['manifest']==proof['manifest']
    assert manifest['scientific_review']==scientific['review']
    assert manifest['hook']==c.binding(__file__) and manifest['hook_api']=='source_fetch_guard(expected_context)'
    assert manifest['class_name']=='NextSessionSourceTransport'
    assert manifest['constructor_api']=='NextSessionSourceTransport(expected_context=<exact binding>)'
    assert manifest['source_window']==['2026-10-21T00:00:00Z','2026-10-21T12:45:00Z']
    assert manifest['context_paths']==[str(c.ROOT/c.STAGES[g]/'context.json') for g in ['core','ETF']]
    assert manifest['source_only'] is True and manifest['source_go'] is False
    rows=manifest['bindings'];assert type(rows) is dict
    files=manifest['files'];assert files and len({x['path'] for x in files})==len(files)
    for row in files:c.checked(row)
    c.checked(manifest['module'],TRANSPORT_MODULE)
    assert all(row in files for row in [manifest['module'],manifest['scope'],manifest['source_plan'],manifest['scientific_manifest'],manifest['scientific_review'],manifest['hook']])
    c.checked(manifest['scope'])
    receive_child_plan_identity(manifest['child_plan_identity'])
    return dict(proof, module=manifest['module'],scope=manifest['scope'],child_plan_identity=manifest['child_plan_identity'])


def receive_child_plan_identity(identity):
    """Explicit current PLAN adoption only; never funding/book acceptance."""
    assert identity['task_id']==c.TASK and identity['session_id']==c.SESSION
    assert identity['current_source_plan']==c.binding(c.ROOT/'next-session-source-plan-M1.json')
    assert identity['accepted_for_source_plan_identity'] is True
    assert identity['actual_runtime_funding_books_accepted'] is False
    plan=c.checked(identity['plan'],D20/'current-session-composite-child-implementation-plan-M2.json')
    review=c.load(c.checked(identity['review'],D20/'independent-current-session-composite-child-plan-review-66ad.json'))
    assert identity['plan']['sha256']=='3fc1be845264a36ec9af1d123916cfdcaca95f47e9cc393396a22164130382c8'
    assert identity['review']['sha256']=='d2f80ddef0539508fd4f816f383d0a22b36d28d4f5e2e12c2e670ee2fdfd9a5b'
    assert review['reviewer']==OPERATING_PEER and review['independent'] is True
    assert review['accepted_for_source_plan_identity'] is True
    # Original review remains its real dated plan receipt. The NEW transport
    # manifest/review above explicitly adopts this unchanged identity for Oct21.
    assert plan.is_file()
    return copy.deepcopy(identity)


def requests_for(group,projection=None):
    _,plan=c.receive_definition()
    requests=copy.deepcopy(plan[group]['requests'])
    if group=='core':
        assert projection is not None
        received=local.receive_projection(projection)
        if received['missing']:
            conditional=copy.deepcopy(plan['core']['conditional_request'])
            conditional.pop('condition')
            requests.append(conditional)
    else:
        assert group=='ETF' and projection is None
    return requests


def receive_context(expected_context,output=None):
    path=c.checked(expected_context)
    groups=[g for g,d in c.STAGES.items() if path==c.ROOT/d/'context.json']
    assert len(groups)==1
    group=groups[0];context=c.load(path);native,claim=c.receive_native(group)
    assert context['task_id']==c.TASK and context['session_id']==c.SESSION and context['group']==group
    assert context['contract']==native['contract'] and context['source_plan']==native['source_plan']
    assert context['code']==native['code'] and context['invocation']==native['invocation']
    assert context['started']==c.binding(path.parent/'started.json') and context['worker']==c.binding(path.parent/'worker-started.json')
    assert context['capacity']=={k:native['capacity'][k] for k in ['context','review']}
    assert context['transport']==receive_transport({k:context['transport'][k] for k in ['manifest','review']})
    assert context['child_plan_identity']==receive_child_plan_identity(context['transport']['child_plan_identity'])
    assert context['requests']==requests_for(group,context['local_projection'])
    assert context['source_start']=='2026-10-21T00:00:00Z' and context['source_cutoff']=='2026-10-21T12:45:00Z'
    assert c.clock(context['source_start'])<=c.clock(claim['claimed_at'])<=c.clock(context['created_at'])<=c.clock(c.now())
    if output is not None:
        c.same_group(group,output,native,claim)
        assert output['context']==expected_context and output['group']==group
        assert output['source_plan']==context['source_plan'] and output['code']==context['code']
        assert output['local_projection']==context['local_projection']
        assert c.clock(context['created_at'])<=c.clock(output['computed_started_at'])<=c.clock(output['computed_completed_at'])<=c.clock(context['source_cutoff'])
    return context


def source_fetch_guard(expected_context):
    context=receive_context(expected_context)
    c.computing(context['group'])
    assert c.clock(c.now())<c.clock(context['source_cutoff'])
    # Fresh context and code are rechecked by the external adapter immediately
    # before factory/request and after pacing, never cached as authorization.
    assert c.binding(c.checked(expected_context))==expected_context
    return None


def next_cursor(value):
    assert value is None or (type(value) is str and 0<len(value)<=8192)
    return value


def capture_request(folder,request,context_binding,fetch):
    """One intent per page; retain every complete/partial artifact, no retry."""
    folder=c.canonical(folder);context=receive_context(context_binding)
    assert folder==c.ROOT/c.STAGES[context['group']]/'captures'/request['key']
    assert request in context['requests'] and not folder.exists(), 'Never replay a complete/partial capture'
    cursor=None;seen=set();received=[]
    while True:
        source_fetch_guard(context_binding)
        name=f'GET{len(received)+1:03}'
        params=dict(request['params'])
        if cursor is not None:params['page_token']=cursor
        started=c.now()
        c.save(folder/(name+'.started.json'),dict(endpoint=request['endpoint'],params=params,requested_at=started,capture_context=context_binding),capacity_rows=context['capacity'])
        source_fetch_guard(context_binding)
        seconds=min(15.,(c.clock(context['source_cutoff'])-c.clock(c.now())).total_seconds())
        assert seconds>0
        response=fetch(request['endpoint'],params,seconds)
        received_at=c.now()
        assert type(response.entity_bytes) is bytes and type(response.status_code) is int
        raw=c.save_bytes(folder/(name+'.raw'),response.entity_bytes,capacity_rows=context['capacity'])
        obj=None
        if response.status_code==200:
            try:
                obj=json.loads(response.entity_bytes)
                assert type(obj) is dict
            except (ValueError,AssertionError,UnicodeDecodeError):
                obj=None
        cursor=obj.get('next_page_token') if obj is not None else None
        meta=dict(endpoint=request['endpoint'],params=params,requested_at=started,received_at=received_at,
            status_code=response.status_code,response=raw,next_page_token=cursor,capture_context=context_binding,
            response_json_object=obj is not None,
            headers={k:v for k,v in response.headers.items() if k.lower() in ['date','content-type','x-request-id','x-ratelimit-remaining','x-ratelimit-reset']})
        received.append(c.save(folder/(name+'.json'),meta,capacity_rows=context['capacity']))
        assert response.status_code==200 and obj is not None, 'Failed or malformed source retained; no retry/fallback'
        assert c.clock(received_at)<=c.clock(context['source_cutoff']), 'Late bytes retained, not admitted'
        cursor=next_cursor(cursor)
        if cursor is None:break
        assert cursor not in seen, 'Repeated cursor retained; no retry'
        seen.add(cursor)
    assert c.clock(c.now())<=c.clock(context['source_cutoff'])
    return c.save(folder/'complete.json',dict(status='completed',request=request,pages=received,
        completed_at=c.now(),capture_context=context_binding),capacity_rows=context['capacity'])


def page_receiver():
    path=FUTURE/'source_contract.py'
    assert c.binding(path)['sha256']=='dfb8f40753d38fe3fe8892b472eb0eba2faf2a3c53924b0850b0cf90ff73e721'
    mf=c.load(c.checked(c.code()['manifest']));assert c.binding(path) in mf['files']
    nodes=[v for v in ast.parse(path.read_text()).body if isinstance(v,ast.FunctionDef) and v.name=='pages']
    assert len(nodes)==1
    def payload(path):
        p=c.canonical(path)
        assert any(p.is_relative_to(c.ROOT/d/'captures') for d in c.STAGES.values())
        return json.loads(p.read_text())
    namespace=dict(canonical=c.canonical,binding=c.binding,checked=c.checked,load=payload,clock=c.clock,now=c.now)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(path),'exec'),namespace)
    return namespace['pages']


def receive_capture(context_binding,request,row):
    context=receive_context(context_binding)
    folder=c.ROOT/c.STAGES[context['group']]/'captures'/request['key']
    complete=c.load(c.checked(row,folder/'complete.json'))
    assert complete['capture_context']==context_binding, 'Internally consistent foreign context is not THIS source'
    objects,bindings,latest=page_receiver()(folder,request,context['source_cutoff'],c.clock(context['created_at']))
    seen=set()
    for index,obj in enumerate(objects):
        cursor=next_cursor(obj.get('next_page_token'))
        if cursor is not None:
            assert index<len(objects)-1 and cursor not in seen
            seen.add(cursor)
    assert c.clock(complete['completed_at'])<=c.clock(c.now())
    return objects,bindings,latest


def collect(group):
    assert group in c.STAGES
    c.authority();c.kernel();c.reserve();proof=c.code()
    transport=receive_transport()
    identity=receive_child_plan_identity(transport['child_plan_identity'])
    c.start(group)
    projection=local.collect_projection() if group=='core' else None
    native,claim=c.computing(group);d=c.ROOT/c.STAGES[group]
    requests=requests_for(group,projection)
    context=dict(task_id=c.TASK,session_id=c.SESSION,group=group,source_plan=native['source_plan'],contract=native['contract'],
        transport=transport,child_plan_identity=identity,requests=requests,local_projection=projection,
        code=proof,invocation=claim['invocation'],started=c.binding(d/'started.json'),worker=c.binding(d/'worker-started.json'),
        capacity={k:native['capacity'][k] for k in ['context','review']},created_at=c.now(),
        source_start='2026-10-21T00:00:00Z',source_cutoff='2026-10-21T12:45:00Z')
    context_binding=c.save(d/'context.json',context,capacity_rows=context['capacity'])
    source_fetch_guard(context_binding)
    # Only the independently received, actually present canonical counterpart
    # is imported. No template/candidate/expired old context is executable here.
    module=c.module('actual_oct21_source_transport',c.checked(transport['module']))
    adapter=module.NextSessionSourceTransport(expected_context=context_binding)
    begin=c.now()
    try:
        captures={request['key']:capture_request(d/'captures'/request['key'],request,context_binding,adapter.fetch) for request in requests}
    finally:
        adapter.close()
    source_fetch_guard(context_binding)
    consumed=[context_binding,c.binding(d/'native-go.json'),c.binding(d/'started.json'),c.binding(d/'worker-started.json'),
        transport['manifest'],transport['review'],transport['module'],transport['scope'],identity['plan'],identity['review']]
    if projection is not None:
        received=local.receive_projection(projection)
        consumed += [projection,*received['accepted_references'],*[o['chosen_descriptor'] for o in received['origins']]]
    for request in requests:
        _,rows,_=receive_capture(context_binding,request,captures[request['key']]);consumed+=rows
    for row in [proof['manifest'],proof['review'],native['contract'],native['source_plan'],*context['capacity'].values()]:consumed.append(row)
    unique={row['path']:row for row in consumed}
    assert all(unique[row['path']]==row for row in consumed)
    output=dict(group=group,source_plan=native['source_plan'],context=context_binding,code=proof,local_projection=projection,
        captures=captures,consumed=list(unique.values()),source_only=True,new_fit_count=0,new_label_count=0,
        computed_started_at=begin,computed_completed_at=c.now())
    c.finish(group,output)
    return receive_sources(group)


def receive_sources(group):
    output=c.receive_stage(group)
    assert output['group']==group and output['stage']==c.STAGES[group]
    c.checked(output['context'],c.ROOT/c.STAGES[group]/'context.json')
    context=receive_context(output['context'],output)
    assert context['group']==group
    assert output['source_only'] is True and output['new_fit_count']==output['new_label_count']==0
    assert set(output['captures'])=={request['key'] for request in context['requests']}
    consumed=output['consumed'];assert len({row['path'] for row in consumed})==len(consumed)
    for row in consumed:c.checked(row)
    expected=[output['context'],c.binding(c.ROOT/c.STAGES[group]/'native-go.json'),context['started'],context['worker'],
        context['transport']['manifest'],context['transport']['review'],context['transport']['module'],context['transport']['scope'],
        context['child_plan_identity']['plan'],context['child_plan_identity']['review']]
    if context['local_projection'] is not None:
        p=local.receive_projection(context['local_projection']);expected += [context['local_projection'],*p['accepted_references'],*[o['chosen_descriptor'] for o in p['origins']]]
    latest=None
    for request in context['requests']:
        _,rows,t=receive_capture(output['context'],request,output['captures'][request['key']]);expected+=rows
        latest=t if latest is None else max(latest,t)
    expected += [context['code']['manifest'],context['code']['review'],context['contract'],context['source_plan'],*context['capacity'].values()]
    assert {r['path']:r for r in consumed}=={r['path']:r for r in expected}
    assert latest<=c.clock(output['computed_completed_at'])
    return output


if __name__=='__main__':
    import sys
    assert len(sys.argv)==2 and sys.argv[1] in c.STAGES
    collect(sys.argv[1])
