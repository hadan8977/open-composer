"""Bind fixed saved inputs without fitting or opening the held reference window."""
from pathlib import Path
import sys, json, hashlib, re
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from scripts import t22_run as R
from open_composer.research.equity_book.panel import PricePanel
from open_composer.research.features.price_hygiene import sanitize_price_matrices
BASE=ROOT/'research/reversal_long_side_20261102'
OUT=BASE/'runs/mechanisms-20261102-6/worker/evidence'
END='2026-09-15'
def save(name, value):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False))
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 if (OUT/'inputs.json').exists():raise RuntimeError('Use completed input receipt; no overwrite')
 s=R.Store();a=s.pos(pd.Timestamp('2024-01-05'));b=s.pos(pd.Timestamp(END));recent=s.dates[a+1:b+1]
 scores={}
 for kind in ['ridge','lgbm']:
  p=ROOT/f'data/research/t22_ml_scores/{kind}_U500_H5.npy'
  source=ROOT/f'data/research/t22_results2/ml/{p.name}'
  assert digest(p)==digest(source),'Saved score source mismatch'
  m=np.load(p,mmap_mode='r');assert m.shape==s.shape
  scored=np.isfinite(m[a:b]).sum(axis=1)
  log=(ROOT/f'data/research/t22_results2/log_{kind}.txt').read_text()
  years=[]
  for year in [2024,2025,2026]:
   first=int(np.flatnonzero(s.dates.year==year)[0]);cut=first-1-5
   lines=[x for x in log.splitlines() if f'{kind} {year}: fit on' in x]
   assert len(lines)==1
   years.append({'year':year,'last_training_feature_date':str(s.dates[cut].date()),'last_label_end_open':str(s.dates[cut+6].date()),'first_prediction_decision_close':str(s.dates[first].date()),'log':lines[0]})
  scores[kind]={'sha256':digest(p),'source':str(source.relative_to(ROOT)),'shape':list(m.shape),'finite_daily_min':int(scored.min()),'finite_daily_max':int(scored.max()),'years':years,'provenance':'Original phase2 score bytes, sorted Store dates/symbols and native builder plus annual logs; fitted weights not archived; historical fit is simulated at annual first-open cutoff, not an actual historical live fit'}
 # Eligibility uses only contemporaneous attributes, never future holding returns.
 union=set()
 for t in range(a-4,b+1):
  ok=R.candidates(s,t,500,'none',np.ones(s.shape[1]))
  union.update(s.symbols[ok])
 union.add('SPY')
 p=PricePanel.from_dir(symbols=sorted(union),start='2016-01-04',end=END,include_etfs=False)
 c,o=p.frame('close'),p.frame('open')
 cc,oo,h=sanitize_price_matrices(c,o)
 j=s.symbols.get_indexer(cc.columns);ii=s.dates.get_indexer(cc.index)
 original=np.asarray(s.m('close')[np.ix_(ii,j)])
 finite=np.isfinite(original)&np.isfinite(c.to_numpy())
 assert np.allclose(original[finite],c.to_numpy()[finite],rtol=1e-6,atol=1e-5),'Price/store basis mismatch'
 mismatch=np.isfinite(original)!=np.isfinite(c.to_numpy())
 extra=np.isfinite(c.to_numpy())&~np.isfinite(cc.to_numpy())
 eligible_masked=[]
 for t in range(a-4,b+1):
  row=cc.index.get_indexer([s.dates[t]])[0]
  ok=R.candidates(s,t,500,'none',np.ones(s.shape[1]))[j]
  if (extra[row]&ok).any():eligible_masked.append(str(s.dates[t].date()))
 save('hygiene.json',{'native_hygiene':h.manifest(),'store_price_missing_mask_mismatches':int(mismatch.sum()),'additional_masked_cells':int(extra.sum()),'eligible_affected_dates':eligible_masked})
 assert not eligible_masked,'Sanitizer changes eligible saved-score support; preserve checkpoint'
 assert not mismatch.any(),'Store/native price support mismatch'
 # Save only histories through the frozen end; no unseen 09-16+ prices are opened.
 cc.to_parquet(OUT/'close.parquet');oo.to_parquet(OUT/'open.parquet')
 news=[]
 for year in [2024,2025,2026]:
  f=pd.read_parquet(ROOT/f'data/features/news_attention/{year}.parquet',columns=['symbol','trade_date','visible_at','news_count_1d','attention_surge_5d'],filters=[('trade_date','<=',pd.Timestamp(END))])
  close=pd.DatetimeIndex(f.trade_date).tz_localize('America/New_York')+pd.Timedelta(hours=16)
  visible=pd.DatetimeIndex(f.visible_at)<=close.tz_convert('UTC')
  f=f.loc[visible];rr=s.dates.get_indexer(pd.DatetimeIndex(f.trade_date));jj=s.symbols.get_indexer(f.symbol.astype(str));ok=(rr>=0)&(jj>=0);rr,jj=rr[ok],jj[ok]
  for col,arr in [('news_count_1d','news_1d'),('attention_surge_5d','news_surge')]:
   assert np.allclose(s.m(arr)[rr,jj],f[col].to_numpy('float32')[ok],equal_nan=True),'Saved news mismatch'
  assert s.m('news_row')[rr,jj].all()
  present=int(s.m('news_row')[s.dates.year==year][:int((s.dates[s.dates.year==year]<=pd.Timestamp(END)).sum())].sum())
  assert present==len(rr),'Saved news-row coverage mismatch'
  news.append({'year':year,'source_rows':len(f),'visible_by_close_rows':int(visible.sum()),'store_rows':present})
 sel=json.loads((ROOT/'reports/research/iterations/t20261006_22_st_reversal/artifacts/selected.json').read_text())
 save('inputs.json',{'recent_start':str(recent[0].date()),'recent_end':str(recent[-1].date()),'sessions':len(recent),'old_685_claim':'incorrect: actual frozen calendar is 674, no model-missing dates removed','symbols_loaded':len(cc.columns),'date_symbol_order':'meta.json, original sorted order; price panel mapped by labels','saved_scores':scores,'news':news,'selected':sel,'rights':'Conditional native adjusted economic units; permanent identity, entitlement cash and PIT corporate-action certification unavailable; no broker share or realized slippage claim','cash_credit':'Native unswept cash earns zero; no TBILL ETF target','hygiene':'hygiene.json','causal_limitations':['Labels cross-sectionally clipped on completed forward outcomes before annual fitting; inherited convention unchanged','Feature definitions and annual rows inherited, no refit or single-feature algorithm/news attribution','Panel snapshot already used historical hygiene; membership/identity not independently certified']})
 print('INPUTS',len(recent),len(cc.columns),news,flush=True)
if __name__=='__main__':main()
