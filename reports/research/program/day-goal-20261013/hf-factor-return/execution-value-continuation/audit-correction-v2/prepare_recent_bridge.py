"""Selected existing recent SPY OHLCV bridge; input QA only, no strategy returns."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pyarrow.parquet as pq

ROOT=Path.cwd();Q=Path(__file__).resolve().parent
TZ=ZoneInfo('America/New_York')
paths=[ROOT/'data/sip/minute/2026/09/shard-0927.parquet',ROOT/'data/sip/minute/2026/10/shard-0927.parquet']
rows={};bindings=[];overlap=0;conflicts=0;conflict_examples=[];max_relative_price_difference=0.0
selected_rows={};session_counts={}
for path in paths:
    before=(path.stat().st_size,path.stat().st_mtime_ns)
    body=path.read_bytes();digest=hashlib.sha256(body).hexdigest()
    table=pq.read_table(path,filters=[('symbol','=','SPY')],use_threads=False)
    for row in table.to_pylist():
        stamp=row['timestamp'].astimezone(TZ);minute=stamp.hour*60+stamp.minute
        if not 570<=minute<960 or str(stamp.date())<'2026-09-01' or str(stamp.date())>'2026-10-13':continue
        key=stamp.isoformat();values=(row['open'],row['high'],row['low'],row['close'],row['volume'])
        if key in rows:
            overlap+=1
            if rows[key]!=values:
                conflicts+=1
                max_relative_price_difference=max(max_relative_price_difference,
                    max(abs(a-b)/abs(a) for a,b in zip(rows[key][:4],values[:4]) if a))
                if len(conflict_examples)<3:
                    conflict_examples.append({'timestamp':key,'earlier_archive':rows[key],'later_archive':values})
        rows[key]=values
        # Freeze file selection by calendar month, before economic evaluation.
        # No choice by return, price, revised freshness, or preferred execution.
        if stamp.strftime('%m')==path.parent.name:
            assert key not in selected_rows, 'Duplicate timestamp within selected calendar-month archive'
            selected_rows[key]=values
    after=(path.stat().st_size,path.stat().st_mtime_ns)
    assert before==after and hashlib.sha256(path.read_bytes()).hexdigest()==digest
    bindings.append({'path':str(path.relative_to(ROOT)),'sha256':digest,'bytes':len(body),'mtime_ns':after[1]})
ordered=sorted(selected_rows)
for key in ordered:
    values=selected_rows[key]
    assert all(np.isfinite(values)) and min(values[:4])>0 and values[4]>=0
    assert values[2]<=min(values[0],values[3])<=max(values[0],values[3])<=values[1]
    session_counts[key[:10]]=session_counts.get(key[:10],0)+1
np.savez_compressed(Q/'recent-SPY-adjusted-minute-input.npz',
 timestamp=np.array(ordered),OHLCV=np.array([selected_rows[key] for key in ordered],dtype='float64'))
dates=sorted({key[:10] for key in ordered})
result={'scope':'Recent SPY information/normalized economic input bridge; not272factor panel or raw cashbook',
 'actual_selected_inputs':bindings,'regular_minutes':len(ordered),'sessions':len(dates),
 'first':ordered[0],'last':ordered[-1],'overlap_regular_minutes_deduplicated':overlap,
 'overlap_value_conflicts':conflicts,'input_stable_during_read':True,
 'vintage_selection':'Calendar month of timestamp selects same-month archive; frozen before outcomes; proposed input requires independent acceptance',
 'overlap_conflict_examples':conflict_examples,'max_relative_overlap_price_difference':max_relative_price_difference,
 'regular_session_rows':session_counts,'missing_bar_rule':'Missing is unavailable, never a zero trade or nearest-minute fill',
 'adjustment':'all','same_day_ratio_use':'common multiplicative adjustment cancels within a session; no raw share fill claim',
 'historical_overnight_TR_and_actions':'Separate current-vintage adjusted-return diagnostic only; no double dividend cash credit',
 'physical_share_cash_ready':False,'full272factor_ready':False,
 'new_market_requests':0,'models_trained_or_inferred':0,'financial_runs':0,
 'output':{'path':str((Q/'recent-SPY-adjusted-minute-input.npz').relative_to(ROOT)),
           'sha256':hashlib.sha256((Q/'recent-SPY-adjusted-minute-input.npz').read_bytes()).hexdigest()}}
(Q/'recent-bridge-readiness.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
