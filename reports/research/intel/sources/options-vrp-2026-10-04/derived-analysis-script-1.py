import pandas as pd, numpy as np, json
d='/tmp/t85data/'
def rd(n):
    s=pd.read_csv(d+n+'.csv'); s['DATE']=pd.to_datetime(s['DATE'],format='%m/%d/%Y'); return s.set_index('DATE')
PUT=rd('PUT')['PUT'];BXM=rd('BXM')['BXM'];WPUT=rd('WPUT')['WPUT'];BXMD=rd('BXMD')['BXMD'];SPX=rd('SPX')['SPX']
VIX=rd('VIX')['CLOSE'];V3=rd('VIX3M')['CLOSE'];V9=rd('VIX9D')['CLOSE']
ff=pd.read_csv(d+'F-F_Research_Data_Factors_daily.csv',skiprows=4,names=['d','mkt','smb','hml','rf'])
ff=ff[pd.to_numeric(ff['d'],errors='coerce').notna()]; ff['d']=pd.to_datetime(ff['d'].astype(int).astype(str),format='%Y%m%d'); ff=ff.set_index('d').astype(float)/100
print('ff end',ff.index[-1], 'PUT start', PUT.index[0], PUT.index[:5].tolist(), 'WPUT end',WPUT.index[-1])
mkt_tr=(1+ff['mkt']+ff['rf']).cumprod()
df=pd.concat({'PUT':PUT,'WPUT':WPUT,'BXM':BXM,'BXMD':BXMD,'SPX':SPX,'MKT':mkt_tr},axis=1)
def stats(r,rf):
    r=r.dropna(); n=len(r)
    if n<50: return None
    ex=r-rf.reindex(r.index).fillna(0)
    yrs=n/252
    cum=(1+r).cumprod()
    dd=(cum/cum.cummax()-1)
    m=(1+r).resample('ME').prod()-1
    return dict(start=str(r.index[0].date()),end=str(r.index[-1].date()),n=n,cagr=float(cum.iloc[-1]**(1/yrs)-1),vol=float(r.std()*np.sqrt(252)),
        sharpe=float(ex.mean()/ex.std()*np.sqrt(252)),maxdd=float(dd.min()),daily_skew=float(r.skew()),monthly_skew=float(m.skew()),worst_month=float(m.min()),worst_day=float(r.min()))
rf=ff['rf']
out={}
wins={'full':None,'2007-2026(post PUT launch Nov2007 ->2008)':('2008-01-01','2026-10-02'),'2016-2026':('2016-01-01','2026-10-02'),'2021-2026':('2021-01-01','2026-10-02'),'2006-2007 pre':('2006-02-01','2007-12-31')}
for w,rng in wins.items():
    out[w]={}
    for c in df.columns:
        s=df[c].dropna()
        if rng: s=s[rng[0]:rng[1]]
        if c=='MKT': s=s[:ff.index[-1]]
        r=s.pct_change().dropna()
        # drop stale/gap days >5 calendar days (early sparse PUT)
        gap=pd.Series(r.index,index=r.index).diff().dt.days.fillna(1)
        r=r[gap<=5]
        out[w][c]=stats(r,rf)
episodes={'2018-02 XIV/Volmageddon':('2018-01-26','2018-02-08'),'2020-03 COVID':('2020-02-19','2020-03-23'),'2024-08 yen unwind':('2024-07-16','2024-08-05'),'2025-04 tariff':('2025-02-19','2025-04-08'),'2008-09..10 GFC':('2008-09-12','2008-11-20'),'2022 bear (full yr)':('2021-12-31','2022-12-30')}
ep={}
for k,(a,b) in episodes.items():
    ep[k]={}
    for c in df.columns:
        s=df[c].dropna()
        try:
            va=s[:a].iloc[-1]; vb=s[:b].iloc[-1]; seg=s[a:b]
            if c=='MKT' and pd.Timestamp(b)>ff.index[-1]: continue
            ep[k][c]=dict(ret=float(vb/va-1),trough=float(seg.min()/va-1) if len(seg) else None)
        except Exception as e: pass
    # VIX move
    ep[k]['VIX']=dict(start=float(VIX[:a].iloc[-1]),peak=float(VIX[a:b].max()),end=float(VIX[:b].iloc[-1]))
out['episodes']=ep
# term structure timing on monthly horizon: signal at month-end t (VIX3M/VIX ratio, VIX - 21d realized vol of SPX), return next month of PUT & WPUT & BXM vs SPX
spx_ret=SPX.pct_change()
rv=spx_ret.rolling(21).std()*np.sqrt(252)*100
me=PUT['2007-12-01':].resample('ME').last().index  # month-ends
def nextmonth(series):
    s=series.dropna(); m=s.resample('ME').last(); return m.pct_change().shift(-1)
sig=pd.DataFrame({'ratio':(V3/VIX).resample('ME').last(),'vrp':(VIX-rv).resample('ME').last(),'vix':VIX.resample('ME').last()})
res={}
for name,ser in [('PUT',PUT),('WPUT',WPUT),('BXM',BXM)]:
    nm=nextmonth(ser); rfm=(1+rf).resample('ME').prod()-1
    t=sig.join(nm.rename('ret')).join(rfm.rename('rf')).dropna(); t=t['2009-09-30':] if True else t
    t['ex']=t['ret']-t['rf']
    r={}
    for lab,mask in [('all',t.ratio>0),('contango(ratio>1)',t.ratio>1),('backwardation(ratio<=1)',t.ratio<=1),('vrp>0',t.vrp>0),('vrp<=0',t.vrp<=0)]:
        if lab.startswith('all'): x=t
        elif 'ratio' in lab: x=t[t.ratio>1] if 'contango' in lab else t[t.ratio<=1]
        else: x=t[t.vrp>0] if lab=='vrp>0' else t[t.vrp<=0]
        r[lab]=dict(n=int(len(x)),mean_ex_month=float(x.ex.mean()),vol_month=float(x.ex.std()),sharpe_ann=float(x.ex.mean()/x.ex.std()*np.sqrt(12)) if len(x)>2 and x.ex.std()>0 else None,worst=float(x.ex.min()),skew=float(x.ex.skew()) if len(x)>3 else None)
    # timing rule: hold only when ratio>1 else cash(rf)
    t['timed']=np.where(t.ratio>1,t.ex,0.0)
    r['timed(contango only, else cash)']=dict(n=int(len(t)),mean_ex_month=float(t.timed.mean()),sharpe_ann=float(t.timed.mean()/t.timed.std()*np.sqrt(12)),worst=float(t.timed.min()))
    r['span']=[str(t.index[0].date()),str(t.index[-1].date())]
    res[name]=r
out['timing_monthly_descriptive_insample']=res
json.dump(out,open('/tmp/t85data/stats.json','w'),indent=1)
for w in out:
    if w in('episodes','timing_monthly_descriptive_insample'):continue
    print('==',w)
    for c,v in out[w].items():
        if v: print(c,{k:(round(x,3) if isinstance(x,float) else x) for k,x in v.items()})
print(json.dumps(ep,indent=0)[:3500])
print(json.dumps(res,indent=0)[:3500])
