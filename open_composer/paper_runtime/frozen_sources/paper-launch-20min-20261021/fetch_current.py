"""Dated maintenance of the existing six-policy historical data menu only."""
import argparse,copy,hashlib,json,os,sys,time
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
import requests
from paper_target_input_controls import receive_current_paper_maintenance
from formation_continuity import source_contract, request_menu
from open_composer.book_paper.accounts import load_account_credentials
from open_composer.market_sessions import us_equity_session_dates
REPO=Path('/root/codex-test/open-composer')
BASE=REPO/'reports/research/program/paper-launch-20min-20261021'
PLAN=REPO/'reports/research/program/owner-profit-delivery-plan-20261017/current-paper-science-20261020/next-session-20261021/next-session-source-plan-M1.json'
def bind(p):
 b=Path(p).read_bytes();return dict(path=str(Path(p).resolve()),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def now():return datetime.now(timezone.utc).isoformat()
def write(p,b):
 p=Path(p);p.parent.mkdir(exist_ok=True,parents=True)
 with p.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
 fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
 return bind(p)
def save(p,v):return write(p,(json.dumps(v,indent=2,allow_nan=False)+'\n').encode())
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--application-day',required=True);args=parser.parse_args()
 app=date.fromisoformat(args.application_day);today=datetime.now(timezone.utc).date();assert app==today
 sessions=us_equity_session_dates(app-timedelta(days=15),app);assert sessions[-1]==app
 ref,prev=sessions[-2:][0],sessions[-3];assert ref<today
 root=args.output.resolve();assert root.is_relative_to(REPO/'reports/paper/diagnostics')
 assert not(root/'current-source.json').exists() and not(root/'source').exists(),'Retain prior capture; no overwrite/replay'
 receive_current_paper_maintenance()
 plan=json.loads(PLAN.read_text());contract=source_contract(ref.isoformat(),app.isoformat());menu=request_menu(plan,contract)
 receive_current_paper_maintenance()
 creds=load_account_credentials('quant2',Path('/root/.config/open-composer/paper-validation-20261019.env'))
 session=requests.Session();session.headers.update({'APCA-API-KEY-ID':creds.key_id,'APCA-API-SECRET-KEY':creds.secret_key})
 fs=os.statvfs(REPO);free=fs.f_bavail*fs.f_frsize;assert free>64*1024*1024
 save(root/'source-start.json',dict(at=now(),pid=os.getpid(),application_day=app.isoformat(),reference_day=ref.isoformat(),prior_reference_day=prev.isoformat(),source_plan=bind(PLAN),formation_request_contract=contract,producer=bind(__file__),authorization=bind(BASE/'owner-authorization.json'),original_source=bind(BASE/'current-source.json'),requests=[dict(group=g,**r)for g,r in menu],physical_free_bytes=free,model_or_account_calls=0))
 count=0;index=[];start=time.monotonic()
 try:
  for g,r in menu:
   cursor=None;seen=set();pages=[]
   while True:
    assert time.monotonic()-start<1200,'Finite source wall guard; preserve partials'
    params=copy.deepcopy(r['params'])
    if cursor:params['page_token']=cursor
    stem=root/'source'/f'{g}-{r["key"]}-{len(pages):03}'
    assert not stem.with_suffix('.json').exists() and not stem.with_suffix('.raw').exists()
    intent=save(stem.with_suffix('.started.json'),dict(endpoint=r['endpoint'],params=params,at=now(),retry=0))
    actual_authority=receive_current_paper_maintenance()
    reply=session.get(r['endpoint'],params=params,timeout=20);count+=1
    raw=write(stem.with_suffix('.raw'),reply.content)
    meta=save(stem.with_suffix('.json'),dict(endpoint=r['endpoint'],params=params,intent=intent,received_at=now(),status_code=reply.status_code,response=raw,authority_before_request=actual_authority,headers={k:v for k,v in reply.headers.items()if k.lower()in ['date','x-request-id','content-type']}))
    assert reply.status_code==200,f'HTTP{reply.status_code}; retain response, no retry/fallback'
    value=reply.json();assert isinstance(value,dict);pages.append(dict(metadata=meta,response=raw));cursor=value.get('next_page_token')
    if not cursor:break
    assert type(cursor)is str and cursor not in seen,'Repeated/invalid cursor'
    seen.add(cursor)
   index.append(dict(group=g,key=r['key'],pages=pages));print(json.dumps(dict(group=g,key=r['key'],pages=len(pages),GETs=count)),flush=True)
  save(root/'current-source.json',dict(captured_at=now(),reference_day=ref.isoformat(),application_day=app.isoformat(),prior_reference_day=prev.isoformat(),source_plan=bind(PLAN),formation_request_contract=contract,physical_GETs=count,data=index,full_pagination=True,source_only=True,new_fit_count=0,model_or_account_calls=0))
 finally:session.close()
if __name__=='__main__':main()
