"""One ordinary current SEC bulk request; fixed entity and disk bounds."""
import hashlib
import json
import shutil
import sys
from datetime import UTC,datetime
from pathlib import Path

ROOT=Path.cwd();P=ROOT/'reports/research/program/paper-continuity-20261014';OUT=P/'current-companyfacts-bulk';OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'scripts'))
from build_sec_xbrl_fundamentals import SecClient,COMPANYFACTS_ZIP_URL,_zip_is_readable
from open_composer.cli import _load_env

ledger=OUT/'ledger.json';assert not ledger.exists(),'consumed one-request ledger'
head=json.loads((P/'SEC-bulk-metadata.json').read_text());assert head['http_status']==200
expected=int(head['response_metadata']['content-length']);cap=1717986918;reserve=402653184
assert 0<expected<cap
free=shutil.disk_usage(ROOT).free
r={'method':'GET','url':COMPANYFACTS_ZIP_URL,'max_requests':1,'entity_byte_cap':cap,'prior_HEAD':head,'fresh_free_disk_bytes':free,'minimum_remaining_disk_bytes':reserve,'status':'local_disk_gate','request_headers_recorded':False,'broker_writes':0,'wire_bytes':None}
ledger.write_text(json.dumps(r,indent=2)+'\n')
assert free>expected+reserve,'disk upper bound cannot admit current archive'
_load_env();client=SecClient();r.update(status='attempted_unknown',attempted_at=datetime.now(UTC).isoformat());ledger.write_text(json.dumps(r,indent=2)+'\n')
tmp=OUT/'companyfacts.zip.part';digest=hashlib.sha256();received=0
try:
    client._throttle()
    with client._client.stream('GET',COMPANYFACTS_ZIP_URL,follow_redirects=False,timeout=180) as response:
        r['http_status']=response.status_code
        r['response_metadata']={k:response.headers[k]for k in('date','last-modified','content-type','content-length')if k in response.headers}
        ledger.write_text(json.dumps(r,indent=2)+'\n')
        with tmp.open('wb')as handle:
            for chunk in response.iter_bytes(1048576):
                if received+len(chunk)>cap or shutil.disk_usage(ROOT).free<reserve:
                    raise RuntimeError('entity_or_disk_bound_stop')
                handle.write(chunk);digest.update(chunk);received+=len(chunk)
        r.update(entity_bytes=received,entity_sha256=digest.hexdigest(),entity_path=str(tmp),complete=True)
        if response.status_code==200:
            assert received==int(response.headers.get('content-length',expected))
            assert _zip_is_readable(tmp)
            target=tmp.with_suffix('');tmp.replace(target);r.update(status='complete_current_bulk',entity_path=str(target))
        else:r['status']='non200_response_retained'
except Exception as error:
    r.update(status='failure_or_incomplete_retained',error_type=type(error).__name__,entity_bytes=received,entity_sha256=digest.hexdigest(),entity_path=str(tmp),complete=False)
finally:
    client.close();r['finished_at']=datetime.now(UTC).isoformat();ledger.write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r),flush=True)
