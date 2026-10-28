"""Actual-native-only fixed10 local projection; no decoder work on import."""
import ast
import json
import math
from zoneinfo import ZoneInfo
import stat
from datetime import date
from pathlib import Path

import next_source_common as c

SYMBOLS='SPY QQQ IWM EFA EEM IEF TLT GLD DBC UUP'.split()
IDENTITY=['device','inode','bytes','mtime_ns','sha256','file_type','nlink_at_bind','bound_at','path']


def sessions(first,last):
    from open_composer.market_sessions import us_equity_session_dates
    return [d.isoformat() for d in us_equity_session_dates(date.fromisoformat(first),date.fromisoformat(last))]


def read_pinned(path,reader,on_bound,guard=None):
    """Choose one exclusive regular FD, durably bind before decoding it."""
    path=c.canonical(path);started=c.now()
    fd=c.os.open(path,c.os.O_RDONLY|c.os.O_NOFOLLOW)
    try:
        before=c.os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_nlink==1
        def identity(s):return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
        with c.os.fdopen(fd,'rb',closefd=False) as stream:
            def digest():
                stream.seek(0);h=c.hashlib.sha256()
                for block in iter(lambda:stream.read(1048576),b''):h.update(block)
                stream.seek(0);return h.hexdigest()
            checksum=digest()
            frozen=dict(path=str(path),device=before.st_dev,inode=before.st_ino,bytes=before.st_size,
                mtime_ns=before.st_mtime_ns,sha256=checksum,file_type='regular',nlink_at_bind=1,bound_at=c.now())
            if guard is not None:
                assert all(frozen[k]==guard[k] for k in ['path','device','inode','bytes','mtime_ns','sha256'])
            chosen=on_bound(dict(frozen))  # fsynced descriptor receipt BEFORE decode
            check=c.os.fstat(fd)
            assert identity(check)==identity(before) and check.st_nlink in [0,1]
            assert digest()==checksum
            data=reader(stream)
            after=c.os.fstat(fd)
            assert identity(after)==identity(before) and after.st_nlink in [0,1]
            assert digest()==checksum, 'Chosen inode changed in place during decode'
            try:
                current=path.lstat();replaced=(current.st_dev,current.st_ino)!=(before.st_dev,before.st_ino)
            except FileNotFoundError:replaced=True
    finally:c.os.close(fd)
    return data,dict(frozen,chosen_descriptor=chosen,read_started_at=started,read_completed_at=c.now(),
        pinned_inode_stable=True,pathname_replaced_after_open=replaced,future_publication_requires_live_path_hash=False)


def receive_origin(expected,origin,native,claim,p):
        assert expected['path']==origin['path'] and expected['symbols']==origin['symbols']
        assert type(origin['sha256']) is str and len(origin['sha256'])==64
        assert all(v in '0123456789abcdef' for v in origin['sha256'])
        assert all(type(origin[k]) is int and origin[k]>=0 for k in ['device','inode','bytes','mtime_ns']) and origin['inode']>0
        assert origin['file_type']=='regular' and origin['nlink_at_bind']==1
        assert origin['pinned_inode_stable'] is True and origin['future_publication_requires_live_path_hash'] is False
        assert type(origin['pathname_replaced_after_open']) is bool
        chosen=c.load(c.checked(origin['chosen_descriptor'],c.ROOT/'core-source-02/local-origins'/(Path(origin['path']).name+'.json')))
        assert chosen['task_id']==c.TASK and chosen['session_id']==c.SESSION
        assert chosen['invocation']==native['invocation'] and chosen['worker']==p['worker']
        assert chosen['native']==c.binding(c.ROOT/'core-source-02/native-go.json') and chosen['source_plan']==native['source_plan']
        assert chosen['frozen']=={k:origin[k] for k in IDENTITY}
        assert chosen['before_decode'] is True
        assert c.clock(claim['claimed_at'])<=c.clock(origin['read_started_at'])<=c.clock(origin['bound_at'])<=c.clock(chosen['published_at'])<=c.clock(origin['read_completed_at'])<=c.clock(p['created_at'])
        return chosen


def receive_projection(row):
    p=c.load(c.checked(row,c.ROOT/'core-source-02/local-projection.json'))
    native,claim=c.receive_native('core')
    assert p['task_id']==c.TASK and p['session_id']==c.SESSION
    assert p['invocation']==native['invocation'] and p['worker']==c.binding(c.ROOT/'core-source-02/worker-started.json')
    _,plan=c.receive_definition();inventory=plan['core']['local_file_inventory']
    assert len(inventory)==len(p['origins'])==9
    for expected,origin in zip(inventory,p['origins'],strict=True):receive_origin(expected,origin,native,claim,p)
    old=c.load(c.T/'source/local.json')
    _,history=accepted_prior_tail(old)
    exact=[*old['consumed'][:2],c.binding(c.T/'source/local.json'),old['projection'],*history]
    assert p['accepted_references']==exact
    mf=c.load(c.checked(native['code']['manifest']))
    for reference in p['accepted_references']:
        c.checked(reference)
        assert reference in mf['files']
    prefix=sessions('2026-01-02','2026-09-30');tail=sessions('2026-10-01','2026-10-20')
    required={s+':'+d for s in SYMBOLS for d in prefix}
    allowed={s+':'+d for s in SYMBOLS for d in prefix+tail}
    assert required<=set(p['rows'])<=allowed
    assert p['symbols']==SYMBOLS and p['tail_sessions']==tail
    assert p['missing']==[s+':'+d for d in tail for s in SYMBOLS if s+':'+d not in p['rows']]
    assert set(p['adjustment_factors'])==set(SYMBOLS)
    assert c.clock(p['created_at'])<=c.clock(c.now())
    for key,row in p['rows'].items():
        assert set(row)=={'symbol','day','open','close'} and key==row['symbol']+':'+row['day']
        assert row['symbol'] in SYMBOLS
        assert all(type(row[v]) in [int,float] and math.isfinite(row[v]) and row[v]>0 for v in ['open','close'])
    for symbol,factor in p['adjustment_factors'].items():
        assert type(factor['multiplier']) in [int,float] and math.isfinite(factor['multiplier']) and factor['multiplier']>0
        assert factor['selected_day']=='2026-01-02' and factor['overlap']==187
        missing=[symbol+':'+d for d in sessions('2026-10-01','2026-10-19') if symbol+':'+d not in p['rows']]
        assert factor['missing_prior_October']==missing and factor['prior_October_overlap']==13-len(missing)
        for key in ['max_ratio_deviation','max_open_ratio_deviation','max_prior_October_relative_deviation']:
            assert type(factor[key]) in [int,float] and math.isfinite(factor[key]) and factor[key]>=0
    # Origins are received historical versions. Do not re-hash mutable paths.
    return p


def collect_projection():
    native,claim=c.computing('core')
    import numpy as np
    import pandas as pd
    c.reserve();c.computing('core')
    _,plan=c.receive_definition()
    old_local_path=c.T/'source/local.json'
    old_projection_row=c.load(old_local_path)['projection']
    old_projection=c.load(c.checked(old_projection_row,c.T/'source/local-projection.json'))
    accepted_local_binding=c.binding(old_local_path)
    # The original two immutable accepted price tables are received by exact
    # bindings; this is necessary normalization support, no old decision math.
    previous=c.load(old_local_path)
    prior_tail,prior_support=accepted_prior_tail(previous)
    close_row,open_row=previous['consumed'][:2]
    assert Path(close_row['path']).name=='ETF-sanitized-close.parquet' and Path(open_row['path']).name=='ETF-sanitized-open.parquet'
    close=pd.read_parquet(c.checked(close_row))[SYMBOLS]
    opening=pd.read_parquet(c.checked(open_row))[SYMBOLS]
    prefix=sessions('2026-01-02','2026-09-30')
    old_tail=sessions('2026-10-01','2026-10-19');tail=sessions('2026-10-01','2026-10-20')
    assert len(prefix)==187 and len(old_tail)==13 and len(tail)==14
    rows,origins,factors={},{},{}
    for item in plan['core']['local_file_inventory']:
        c.computing('core')
        path=c.canonical(item['path'])
        def on_bound(frozen):
            rows_cap={k:native['capacity'][k] for k in ['context','review']}
            return c.save(c.ROOT/'core-source-02/local-origins'/(path.name+'.json'),dict(task_id=c.TASK,session_id=c.SESSION,
                invocation=native['invocation'],worker=c.binding(c.ROOT/'core-source-02/worker-started.json'),
                native=c.binding(c.ROOT/'core-source-02/native-go.json'),source_plan=native['source_plan'],
                frozen=frozen,published_at=c.now(),before_decode=True),capacity_rows=rows_cap)
        frame,origin=read_pinned(path,lambda f:pd.read_parquet(f,columns=['symbol','timestamp','open','close'],filters=[('symbol','in',item['symbols'])]),on_bound)
        origin['symbols']=item['symbols'];origins[item['path']]=origin
        frame['day']=pd.to_datetime(frame.timestamp,utc=True).dt.strftime('%Y-%m-%d')
        assert not frame.duplicated(['symbol','day']).any()
        for symbol in item['symbols']:
            data=frame[frame.symbol==symbol].set_index('day').sort_index()
            assert set(prefix)<=set(data.index), 'Indispensable Jan2..Sep30 basis support missing'
            ratio=data.loc[prefix,'close'].to_numpy(dtype=float)/close.loc[pd.to_datetime(prefix),symbol].to_numpy(dtype=float)
            k=float(ratio[0])
            assert np.isfinite(ratio).all() and k>0 and np.allclose(ratio,k,rtol=1e-7,atol=1e-8), 'Nonuniform current CLOSE revision'
            opening_ratio=data.loc[prefix,'open'].to_numpy(dtype=float)/opening.loc[pd.to_datetime(prefix),symbol].to_numpy(dtype=float)
            assert np.isfinite(opening_ratio).all() and np.allclose(opening_ratio,k,rtol=1e-7,atol=1e-8), 'Current OPEN basis differs'
            old_k=old_projection['adjustment_factors'][symbol]['multiplier']
            missing_old=[];maximum=0.
            for day in old_tail:
                key=symbol+':'+day
                assert key in prior_tail, 'Accepted combined prior support missing'
                if day not in data.index:
                    missing_old.append(key);continue
                for field in ['open','close']:
                    current=float(data.loc[day,field])/k
                    accepted=prior_tail[key][field]/old_k
                    assert np.isclose(current/accepted,1,rtol=1e-7,atol=1e-8), 'Nonuniform previously accepted Oct1..19 revision'
                    maximum=max(maximum,abs(current/accepted-1))
            # Genuine missing cells can be supplied only by the frozen fixed10
            # conditional request; revised cells already refused above.
            factors[symbol]=dict(multiplier=k,selected_day='2026-01-02',overlap=187,
                max_ratio_deviation=float(np.max(np.abs(ratio-k))),max_open_ratio_deviation=float(np.max(np.abs(opening_ratio-k))),
                prior_October_overlap=13-len(missing_old),missing_prior_October=missing_old,max_prior_October_relative_deviation=maximum)
            for day in prefix+tail:
                if day in data.index:
                    row=data.loc[day];o,v=float(row.open),float(row.close)
                    assert np.isfinite([o,v]).all() and min(o,v)>0
                    rows[symbol+':'+day]=dict(symbol=symbol,day=day,open=o,close=v)
    missing=[s+':'+d for d in tail for s in SYMBOLS if s+':'+d not in rows]
    value=dict(task_id=c.TASK,session_id=c.SESSION,invocation=native['invocation'],worker=c.binding(c.ROOT/'core-source-02/worker-started.json'),
        symbols=SYMBOLS,rows=rows,origins=[origins[x['path']] for x in plan['core']['local_file_inventory']],adjustment_factors=factors,
        tail_sessions=tail,missing=missing,accepted_references=[close_row,open_row,accepted_local_binding,old_projection_row,*prior_support],created_at=c.now())
    rows_cap={k:native['capacity'][k] for k in ['context','review']}
    result=c.save(c.ROOT/'core-source-02/local-projection.json',value,capacity_rows=rows_cap)
    receive_projection(result)
    return result


def accepted_prior_tail(previous):
    """Receive the accepted local+conditional-request vintage, not local alone.

    Historical saved page reception only. No feature/model computation, source
    constructor or request. Called by the actual new native before current decode.
    """
    mf=c.load(c.checked(c.code()['manifest']));allowed={r['path']:r for r in mf['files']}
    paths=[c.T/'input/LSTM/output.json',c.T/'independent-current-input-review-LSTM.json',
        c.T/'source/output.json',c.T/'source/context.json',c.T/'source/completed.json',c.T/'source/seal.json',
        c.T/'source/started.json',c.T/'source/worker-started.json']
    refs=[]
    for path in paths:
        row=c.binding(path);assert allowed[str(path)]==row;refs.append(row)
    prior=c.load(paths[0]);review=c.load(paths[1]);output=c.load(paths[2]);context=c.load(paths[3])
    assert review['task_id']==c.TASK and review['reviewer']==c.PEER and review['independent'] is True
    assert review['verdict']=='accept_complete_current_input' and review['source_linked_controls_accepted'] is True
    assert review['target']==review['derived_control_witness']==refs[0]
    assert prior['source']==refs[2] and output['context']==refs[3] and output['local']==c.binding(c.T/'source/local.json')
    assert c.load(c.checked(output['local']))==previous
    complete=c.load(paths[4]);seal=c.load(paths[5])
    assert complete['seal']==refs[5] and seal['output']==refs[2]
    assert c.clock(output['computed_completed_at'])<=c.clock(complete['completed_at'])<=c.clock(prior['computed_started_at'])
    request=next(x for x in context['requests'] if x['key']=='adjusted-tail')
    assert request==next(x for x in output['requests'] if x['key']=='adjusted-tail')
    assert request['params']['end']=='2026-10-20T00:00:00Z' and request['params']['feed']=='sip' and request['params']['adjustment']=='all'
    completepath=c.T/'source/adjusted-tail/complete.json';row=c.binding(completepath);assert allowed[str(completepath)]==row;refs.append(row)
    assert c.load(completepath)['capture_context']==refs[3]
    path=c.T.parent/'candidate-contribution/future-input-receiver/source_contract.py';assert allowed[str(path)]==c.binding(path)
    ns=dict(canonical=c.canonical,binding=c.binding,checked=c.checked,load=lambda p:json.loads(c.canonical(p).read_text()),clock=c.clock,now=c.now)
    fn=next(x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name=='pages')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(path),'exec'),ns)
    objects,received,latest=ns['pages'](completepath.parent,request,'2026-10-20T12:45:00Z',c.clock(c.load(c.T/'source/started.json')['started_at']))
    assert latest<=c.clock(output['computed_completed_at'])
    for item in received:assert allowed[item['path']]==item
    refs+=received
    path=c.T/'current_input.py';assert allowed[str(path)]==c.binding(path)
    ns=dict(HERE=c.T,load=c.load,clock=c.clock,ZoneInfo=ZoneInfo,math=math)
    fn=next(x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name=='raw_rows')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(path),'exec'),ns)
    fetched=ns['raw_rows'](objects,SYMBOLS,sessions('2026-09-28','2026-10-19'))
    result=dict(previous['rows'])
    for key,old in {**previous['request_overlap_rows'],**previous['rows']}.items():
        v=fetched[(old['symbol'],old['day'])]
        for field,rawkey in [('open','o'),('close','c')]:
            assert math.isclose(v[rawkey]/old[field],1,rel_tol=1e-7,abs_tol=1e-8), 'Accepted prior combined source drift'
    for (s,d),v in fetched.items():
        if d>='2026-10-01':result[s+':'+d]=dict(symbol=s,day=d,open=v['o'],close=v['c'])
    assert set(result)=={s+':'+d for s in SYMBOLS for d in sessions('2026-10-01','2026-10-19')}
    refs=list({r['path']:r for r in refs}.values())
    return result,refs
