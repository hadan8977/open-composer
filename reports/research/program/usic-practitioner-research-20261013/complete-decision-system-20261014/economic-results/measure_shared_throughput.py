"""Bounded instrumentation of approved APIs; no selectable/economic result."""
import sys,json,gzip,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'code'))
from consumer_admission import P,ROOT,bind,claim_launch,native_admission,verified_frames,phase_admission,empirical_limit,empirical_remaining,settle
from native_engine import make_engine
from native_events import source_intervals
from native_shared_feed import feed
from profile_native_feed import normalized_policy
from verify_shared_feed import snapshot
from decision_system import read_parameters
import msgspec
job=sys.argv[1]
row=claim_launch(job,'consumer');outcome='failed'
try:
    native_admission(job);frames=verified_frames();phase_admission(job,'empirical');empirical_limit(job)
    previous=P/'economic-results/technical-feed-martin-march-recovery-20261014/2024-03-optimized-interpreted.json.gz'
    old=json.loads(gzip.decompress(previous.read_bytes()));assert old['full_month_clock_executed'] and old['first_unknown'] is None
    b=next(b for b in frames['outputs'] if Path(b['path']).name.startswith('2024-03'))
    assert bind(ROOT/b['path'])==b
    t=time.process_time()
    with gzip.open(ROOT/b['path'],'rb') as f:packets=[msgspec.json.decode(line) for line in f]
    read_cpu=time.process_time()-t
    folder=P/'economic-results'/('shared-workload-'+job);folder.mkdir(exist_ok=False)
    params=read_parameters(ROOT/'strategy_specs/drafts/martin_complete_system_20261014.yaml')
    bindings=dict(spec=bind(ROOT/'strategy_specs/drafts/martin_complete_system_20261014.yaml')['sha256'],input=bind(P/'frame-preparation-result.json')['sha256'],contract=bind(P/'revisions/r1/event-book-contract.json')['sha256'])
    results={};metrics=[]
    for candidates in [('P_EMA',),('P_SYSTEM','P_EMA')]:
        accounts=[make_engine(params,c,'market',20,bindings,{'SMCI':.1}) for c in candidates]
        factors={'SMCI':.1};total_events={};started=time.process_time();max_interval=0;complete=True
        try:
            for interval,afternoon in source_intervals(packets,120):
                if empirical_remaining(job)<max(25,2*max_interval+10):complete=False;break
                t=time.process_time()
                factors,events=feed(accounts,interval,'O-H-L-C',factors,frames['trigger_masks'],afternoon=afternoon)
                max_interval=max(max_interval,time.process_time()-t)
                for k,v in events.items():total_events[k]=total_events.get(k,0)+v
            for (engine,strategy),candidate in zip(accounts,candidates):
                engine.end();r=snapshot(strategy);r['first_unknown']=r.pop('unknown');r['cash']=None if strategy.book.path_unknown else r['cash'];r['policy']=normalized_policy(strategy);r['component_clock_complete']=complete;r['full_month_clock_executed']=complete and not strategy.book.path_unknown
                label='+'.join(candidates)+'__'+candidate
                t=time.process_time()
                with gzip.open(folder/(label+'.json.gz'),'wb',compresslevel=1) as f:f.write(msgspec.json.encode(r))
                results[label]=r
            cpu=time.process_time()-started
            metrics.append(dict(candidates=candidates,CPU=cpu,complete=complete,full_known_month=all(not s.book.path_unknown for e,s in accounts),events=total_events,max_interval_CPU=max_interval))
            (folder/'metrics.json').write_text(json.dumps(dict(source=b,source_read_CPU=read_cpu,metrics=metrics,full_strategy_results=0,profit_selection=False),indent=2)+'\n')
            if not complete:raise RuntimeError('throughput component incomplete; no favorable extrapolation')
        finally:
            for e,s in accounts:e.dispose()
    # Roundtrip canonicalization preserves economic values, removes irrelevant
    # tuple/list JSON container differences; native UUIDs were already excluded.
    canon=lambda r:msgspec.json.decode(msgspec.json.encode(r))
    assert canon(results['P_SYSTEM+P_EMA__P_SYSTEM'])==old
    assert canon(results['P_EMA__P_EMA'])==canon(results['P_SYSTEM+P_EMA__P_EMA'])
    (folder/'acceptance.json').write_text(json.dumps(dict(actual_single_and_shared_equality=True,source_read_CPU=read_cpu,metrics=metrics,full_known_month=all(m['full_known_month'] for m in metrics),full_strategy_results=0,not_economic_estimate=True,prior_system_witness=bind(previous),implementation=bind(P/'consumer-implementation-manifest.json')),indent=2)+'\n')
    outcome='technical_shared_workload_complete'
    print(json.dumps(dict(status=outcome,metrics=metrics)),flush=True)
finally:
    settle(job,outcome)
