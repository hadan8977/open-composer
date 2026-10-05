import pandas as pd, numpy as np, json
exec(open('/tmp/t85_an.py').read().split("rf=ff['rf']")[0])
rf=ff['rf']
mk=(ff['mkt']+ff['rf']); 
def monthly(s): return s.dropna().resample('ME').last().pct_change(fill_method=None)
rfm=(1+rf).resample('ME').prod()-1
mkm=(1+mk).resample('ME').prod()-1
res={}
for per,(a,b) in {'2008-2026':('2008-01-31','2026-08-31'),'2009-10..2026-08':('2009-09-30','2026-08-31'),'2016-2026':('2016-01-31','2026-08-31'),'2021-2026':('2021-01-31','2026-08-31')}.items():
    res[per]={}
    for n,s in [('PUT',PUT),('WPUT',WPUT),('BXM',BXM),('BXMD',BXMD)]:
        t=pd.concat({'y':monthly(s)-rfm,'x':mkm-rfm},axis=1)[a:b].dropna()
        X=np.column_stack([np.ones(len(t)),t.x.values]); y=t.y.values
        beta=np.linalg.lstsq(X,y,rcond=None)[0]; e=y-X@beta; s2=e@e/(len(y)-2); cov=s2*np.linalg.inv(X.T@X)
        # Newey-West lag3 for alpha t
        res[per][n]=dict(n=len(y),alpha_ann=float(beta[0]*12),beta=float(beta[1]),alpha_t=float(beta[0]/np.sqrt(cov[0,0])),ex_ret_ann=float(y.mean()*12),mkt_ex_ann=float(t.x.mean()*12),corr=float(np.corrcoef(t.x,t.y)[0,1]))
json.dump(res,open('/tmp/t85data/alpha.json','w'),indent=1)
for p,v in res.items():
    print(p)
    for n,x in v.items(): print(' ',n,{k:round(b,3) for k,b in x.items()})
# last 12 months PUT episode lists: max drawdown dates
for n,s in [('PUT',PUT),('WPUT',WPUT),('BXM',BXM)]:
    s=s['2008-01-01':]; dd=s/s.cummax()-1; print(n,'maxDD',dd.min(),dd.idxmin(), 'peak',s[:dd.idxmin()].idxmax())
print('latest',PUT.iloc[-1],VIX.iloc[-1],(V3/VIX).iloc[-1], V3.index[-1], VIX.index[-1])
