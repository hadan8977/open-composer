"""Dated scientific input lifecycle; imports never enter a source or model."""
import json
import uuid
import next_source_common as c
import next_session_source as source

ROOT, TASK, SESSION, PEER = c.ROOT, c.TASK, c.SESSION, c.PEER
STAGES = {'CURRENT_CONTROLS': 'controls', 'BASE': 'input/BASE',
          'H5': 'input/H5', 'LSTM': 'input/LSTM', 'ETF-input': 'input/ETF'}


def output_path(policy):
    return ROOT / STAGES[policy] / ('current-unit-action-controls.json' if policy == 'CURRENT_CONTROLS' else 'output.json')


def code(proof=None):
    if proof is None:
        pointer = c.load(ROOT / 'input-implementation-pointer.json')
        assert pointer['task_id'] == TASK and pointer['session_id'] == SESSION
        proof = {k: pointer[k] for k in ['manifest', 'review']}
    mf = c.load(c.checked(proof['manifest']))
    review = c.load(c.checked(proof['review']))
    assert all(v['task_id'] == TASK and v['session_id'] == SESSION for v in [mf, review])
    assert c.checked(proof['manifest']).parent == c.checked(proof['review']).parent == ROOT
    assert review['reviewer'] == PEER and review['independent'] is True
    assert review['verdict'] == 'approve_implementation'
    assert review['current_input_implementation_accepted'] is review['native_launcher_accepted'] is True
    assert review['target'] == proof['manifest'] and mf['source_plan'] == c.binding(ROOT / 'next-session-source-plan-M1.json')
    assert mf['contract'] == c.binding(ROOT / 'next-session-contract-and-storage-M1.json')
    assert len({r['path'] for r in mf['files']}) == len(mf['files'])
    for row in mf['files']: c.checked(row)
    assert c.binding(__file__) in mf['files']
    assert mf['source_implementation'] == c.code()
    return proof


def authority():
    contract, _ = c.receive_definition()
    assert c.load(c.REPO / 'reports/research/control/owner-compute-hold.json')['paper_deployment_allowed'] is True
    assert c.clock('2026-10-21T00:00:00Z') <= c.clock(c.now()) < c.clock(contract['calendar']['latest_current_input_complete'])
    return contract


def sources(policy):
    groups = ['core', 'ETF'] if policy == 'CURRENT_CONTROLS' else ['ETF' if policy == 'ETF-input' else 'core']
    result = {}
    for group in groups:
        obj = source.receive_sources(group)
        folder = ROOT / c.STAGES[group]
        result[group] = dict(output=c.binding(folder / 'output.json'), completed=c.binding(folder / 'completed.json'),
                             context=obj['context'], consumed=obj['consumed'])
    return result


def start(policy):
    assert policy in STAGES
    contract = authority(); c.kernel(); c.reserve(); proof = code()
    folder = ROOT / STAGES[policy]
    assert not folder.exists(), 'Retained completed/partial input is not a replay permission'
    inputs = sources(policy)
    controls = None
    if policy != 'CURRENT_CONTROLS':
        receive_stage('CURRENT_CONTROLS')
        controls = dict(output=c.binding(output_path('CURRENT_CONTROLS')),
                        completed=c.binding(ROOT / 'controls/completed.json'))
    reg = c.registry(); authority(); k = c.kernel(); c.reserve()
    cap = c.capacity.guard_write(); caprows = {k: cap[k] for k in ['context', 'review']}
    native = dict(task_id=TASK, session_id=SESSION, stage=STAGES[policy], policy=policy,
                  invocation=uuid.uuid4().hex, process=c.process_identity(), at=c.now(), kernel=k,
                  registry=reg, code=proof, source_inputs=inputs, input=next(iter(inputs.values()))['output'],
                  current_controls=controls,
                  capacity=cap, contract=c.binding(ROOT / 'next-session-contract-and-storage-M1.json'),
                  input_only=True, source_model_fit_account_or_operating_go=False)
    for item in inputs.values(): assert c.clock(c.load(item['completed']['path'])['completed_at']) <= c.clock(native['at'])
    if controls is not None: assert c.clock(c.load(controls['completed']['path'])['completed_at']) <= c.clock(native['at'])
    c.save(folder / 'native-go.json', native, capacity_rows=caprows)
    c.save(folder / 'started.json', dict(task_id=TASK, session_id=SESSION, stage=STAGES[policy],
           native=c.binding(folder / 'native-go.json'), started_at=c.now()), capacity_rows=caprows)
    claim = dict(task_id=TASK, session_id=SESSION, stage=STAGES[policy], invocation=native['invocation'],
                 process=native['process'], native=c.binding(folder / 'native-go.json'),
                 started=c.binding(folder / 'started.json'), claimed_at=c.now())
    c.save(folder / 'worker-started.json', claim, capacity_rows=caprows)
    return native, claim


def receive_native(policy):
    folder = ROOT / STAGES[policy]
    started = c.load(folder / 'started.json')
    native = c.load(c.checked(started['native'], folder / 'native-go.json'))
    claim = c.load(folder / 'worker-started.json')
    assert all(v['task_id'] == TASK and v['session_id'] == SESSION and v['stage'] == STAGES[policy]
               for v in [started, native, claim])
    assert native['policy'] == policy and native['input_only'] is True
    assert native['source_model_fit_account_or_operating_go'] is False
    assert claim['started'] == c.binding(folder / 'started.json') and claim['native'] == started['native']
    assert claim['invocation'] == native['invocation'] and claim['process'] == native['process']
    assert len(native['invocation']) == 32 and all(v in '0123456789abcdef' for v in native['invocation'])
    assert all(type(native['process'][v]) is int and native['process'][v] > 0 for v in ['pid', 'start_ticks'])
    code(native['code'])
    assert native['contract'] == c.binding(ROOT / 'next-session-contract-and-storage-M1.json')
    assert native['source_inputs'] == sources(policy) and native['input'] == next(iter(native['source_inputs'].values()))['output']
    if policy == 'CURRENT_CONTROLS':
        assert native['current_controls'] is None
    else:
        receive_stage('CURRENT_CONTROLS')
        assert native['current_controls'] == dict(output=c.binding(output_path('CURRENT_CONTROLS')),
                      completed=c.binding(ROOT / 'controls/completed.json'))
        assert c.clock(c.load(native['current_controls']['completed']['path'])['completed_at']) <= c.clock(native['at'])
    c.capacity.receive_capacity_context(native['capacity']['context'], native['capacity']['review'])
    assert native['capacity']['receipt']['sha256'] == c.capacity.RECEIPT_SHA
    c.checked(native['registry']['registry'], c.REPO / 'capabilities/registry.yaml')
    assert native['registry']['actual_capability'] == c.load(c.T / 'capability-snapshot.json')['capability']
    assert native['registry']['unmodified_registered_receiver'] is True and native['registry']['provider_calls'] == 0
    assert native['registry']['argv'] == [str(c.REPO / '.venv/bin/python'), '-c',
        'import json; from pathlib import Path; from open_composer.capabilities.registry import get_capability; print(json.dumps(get_capability("market.alpaca_bars",Path.cwd()).model_dump(mode="json")))']
    k = native['kernel']
    assert k['memory.max'] == '419430400' and k['memory.swap.max'] == '0'
    assert k['cpu.max'].split()[0] == 'max' and k['cpu_affinity'] == [0]
    assert k['threads'] == {v: '1' for v in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'PYTHONDONTWRITEBYTECODE']}
    contract, _ = c.receive_definition()
    assert c.clock('2026-10-21T00:00:00Z') <= c.clock(native['at']) <= c.clock(started['started_at']) <= c.clock(claim['claimed_at']) <= c.clock(c.now())
    assert c.clock(claim['claimed_at']) < c.clock(contract['calendar']['latest_current_input_complete'])
    assert c.clock(native['registry']['received_at']) <= c.clock(native['at'])
    for item in native['source_inputs'].values():
        assert c.clock(c.load(item['completed']['path'])['completed_at']) <= c.clock(native['at'])
    return native, claim


def computing(policy):
    authority(); c.kernel(); c.reserve()
    native, claim = receive_native(policy)
    assert native['process'] == c.process_identity()
    folder = ROOT / STAGES[policy]
    assert not any(p.exists() for p in [output_path(policy), folder / 'seal.json', folder / 'completed.json'])
    c.capacity.guard_write(context_row=native['capacity']['context'], review_row=native['capacity']['review'])
    return native, claim


def required_consumed(policy, native):
    folder = ROOT / STAGES[policy]
    rows = [c.binding(folder / name) for name in ['native-go.json', 'started.json', 'worker-started.json']]
    rows += [native['code']['manifest'], native['code']['review'], native['contract'],
             c.binding(ROOT / 'next-session-source-plan-M1.json'),
             native['capacity']['context'], native['capacity']['review']]
    for item in native['source_inputs'].values(): rows += [item['output'], item['completed'], *item['consumed']]
    if native['current_controls'] is not None: rows += list(native['current_controls'].values())
    return rows


def finish(policy, value):
    native, claim = computing(policy); folder = ROOT / STAGES[policy]
    rows = {k: native['capacity'][k] for k in ['context', 'review']}
    assert c.clock(claim['claimed_at']) <= c.clock(value['computed_started_at']) <= c.clock(value['computed_completed_at']) <= c.clock(c.now())
    consumed = value['consumed'] + required_consumed(policy, native)
    unique = {r['path']: r for r in consumed}; assert all(unique[r['path']] == r for r in consumed)
    value = dict(value, task_id=TASK, session_id=SESSION, stage=STAGES[policy], policy=policy,
                 reference_day='2026-10-20', application_day='2026-10-21', implementation=native['code']['manifest'],
                 native=c.binding(folder / 'native-go.json'), worker=c.binding(folder / 'worker-started.json'),
                 current_controls=native['current_controls'],
                 contract=native['contract'], source_groups=native['source_inputs'],
                 consumed=list(unique.values()), published_at=c.now())
    c.save(output_path(policy), value, capacity_rows=rows)
    authority(); c.kernel(); assert native['process'] == c.process_identity()
    c.save(folder / 'seal.json', dict(started=claim['started'], worker=value['worker'],
           output=c.binding(output_path(policy)), sealed_at=c.now()), capacity_rows=rows)
    authority(); c.kernel()
    c.save(folder / 'completed.json', dict(started=claim['started'], worker=value['worker'],
           seal=c.binding(folder / 'seal.json'), completed_at=c.now()), capacity_rows=rows)
    return receive_stage(policy)


def receive_stage(policy, require_peer=False):
    native, claim = receive_native(policy); folder = ROOT / STAGES[policy]
    seal, done = c.load(folder / 'seal.json'), c.load(folder / 'completed.json')
    assert seal['started'] == done['started'] == claim['started'] == c.binding(folder / 'started.json')
    assert seal['worker'] == done['worker'] == c.binding(folder / 'worker-started.json')
    assert done['seal'] == c.binding(folder / 'seal.json')
    value = c.load(c.checked(seal['output'], output_path(policy)))
    assert value['task_id'] == TASK and value['session_id'] == SESSION and value['policy'] == policy and value['stage'] == STAGES[policy]
    assert value['reference_day'] == '2026-10-20' and value['application_day'] == '2026-10-21'
    assert value['implementation'] == native['code']['manifest'] and value['contract'] == native['contract']
    assert value['source_groups'] == native['source_inputs']
    assert value['current_controls'] == native['current_controls']
    assert value['native'] == claim['native'] and value['worker'] == seal['worker']
    contract, _ = c.receive_definition()
    assert c.clock(claim['claimed_at']) <= c.clock(value['computed_started_at']) <= c.clock(value['computed_completed_at']) <= c.clock(value['published_at']) <= c.clock(seal['sealed_at']) <= c.clock(done['completed_at']) <= c.clock(contract['calendar']['latest_current_input_complete'])
    assert c.clock(done['completed_at']) <= c.clock(c.now())
    assert len({v['path'] for v in value['consumed']}) == len(value['consumed'])
    for row in value['consumed']: c.checked(row)
    assert all(row in value['consumed'] for row in required_consumed(policy, native))
    if require_peer:
        name = 'independent-current-controls-input-review.json' if policy == 'CURRENT_CONTROLS' else f'independent-current-input-review-{policy}.json'
        review = c.load(ROOT / name)
        assert review['task_id'] == TASK and review['session_id'] == SESSION and review['policy'] == policy
        assert review['reviewer'] == PEER and review['independent'] is True
        assert review['verdict'] == 'accept_complete_current_input' and review['source_linked_controls_accepted'] is True
        assert review['target'] == review['derived_control_witness'] == c.binding(output_path(policy))
    return value
