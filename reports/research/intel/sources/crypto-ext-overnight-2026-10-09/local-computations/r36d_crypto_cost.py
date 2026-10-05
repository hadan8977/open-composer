import polars as pl, numpy as np, json
c=pl.read_parquet('data/research/crypto/session_prices.parquet').filter((pl.col('symbol')=='BTCUSD')&pl.col('close').is_not_null()).sort('date')
cl=c['close'].to_numpy(); dt=c['date'].to_numpy()
def rule_sma(n):
    s=np.full(len(cl),np.nan)
    for i in range(n,len(cl)): s[i]=cl[i-n:i].mean()   # uses prior n closes; signal at close i uses up to i-1 -> conservative lag
    return (cl>s).astype(float)
def rule_tsmom(n): 
    p=np.zeros(len(cl)); 
    for i in range(n,len(cl)): p[i]=1.0 if cl[i]/cl[i-n]>1 else 0.0
    return p
res={}
r=np.r_[0,cl[1:]/cl[:-1]-1]
start=np.searchsorted(dt,np.datetime64('2021-01-01'))
yrs=float((dt[-1]-dt[start])/np.timedelta64(1,'D'))/365.25
for name,pos in {'SMA200':rule_sma(200),'SMA50':rule_sma(50),'TSMOM_21d':rule_tsmom(21),'TSMOM_63d':rule_tsmom(63),'TSMOM_126d':rule_tsmom(126)}.items():
    p=np.nan_to_num(pos)[:-1]; rr=r[1:]   # position decided at close t earns return t+1
    # restrict from 2021-01-01 (Alpaca crypto history start)
    p=p[start:]; rr=rr[start:]
    turn=np.abs(np.diff(np.r_[0,p])); sides_per_year=turn.sum()/yrs
    row={'sides_per_year':float(sides_per_year)}
    for cost in [0,10,30,50]:
        net=p*rr-turn*cost*1e-4
        row[f'sharpe_{cost}bp_side']=float(net.mean()/net.std(ddof=1)*np.sqrt(len(net)/yrs))
        row[f'cagr_pct_{cost}bp_side']=float((np.prod(1+net)**(1/yrs)-1)*100)
    res[name]=row
bh=rr
res['BUYHOLD']={'sharpe_0bp_side':float(rr.mean()/rr.std(ddof=1)*np.sqrt(len(rr)/yrs)),'cagr_pct_0bp_side':float((np.prod(1+rr)**(1/yrs)-1)*100)}
res['_window']=[str(dt[start])[:10],str(dt[-1])[:10],float(yrs)]
json.dump(res,open('/tmp/r36d_crypto_cost.json','w'),indent=1)
for k,v in res.items(): print(k,{a:(round(b,2) if isinstance(b,float) else b) for a,b in v.items()} if isinstance(v,dict) else v)
