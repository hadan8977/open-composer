import polars as pl, numpy as np, json
q=pl.scan_parquet('data/sip/daily/*/*.parquet').filter(pl.col('symbol')=='QQQ').select(pl.col('timestamp').dt.date().alias('d'),pl.col('close').alias('qqq')).collect().unique('d').sort('d')
c=pl.read_parquet('data/research/crypto/session_prices.parquet').filter(pl.col('symbol').is_in(['BTCUSD','ETHUSD'])&pl.col('close').is_not_null()).with_columns(pl.col('date').dt.date().alias('d'))
out={}
for sym in ['BTCUSD','ETHUSD']:
    x=c.filter(pl.col('symbol')==sym).select('d',pl.col('close').alias('c')).join(q,on='d',how='inner').sort('d')
    x=x.with_columns((pl.col('c')/pl.col('c').shift(1)-1).alias('rc'),(pl.col('qqq')/pl.col('qqq').shift(1)-1).alias('rq')).drop_nulls()
    # note: gaps in dates (join) -> only consecutive rows; fine for approximate daily
    def corr(df,col='rc'): 
        return float(np.corrcoef(df['rc'].to_numpy(),df['rq'].to_numpy())[0,1]) if len(df)>20 else None
    res={}
    for name,(a,b) in {'full':('2016-05-01','2026-09-01'),'2016-2019':('2016-05-01','2019-12-31'),'2020-2022':('2020-01-01','2022-12-31'),'2023':('2023-01-01','2023-12-31'),'2024':('2024-01-01','2024-12-31'),'2025':('2025-01-01','2025-12-31'),'2026':('2026-01-01','2026-09-01'),'anchor_2024-01-08..2026-08-31':('2024-01-08','2026-08-31')}.items():
        df=x.filter((pl.col('d')>=pl.lit(a).str.to_date())&(pl.col('d')<=pl.lit(b).str.to_date()))
        beta=float(np.cov(df['rc'].to_numpy(),df['rq'].to_numpy())[0,1]/np.var(df['rq'].to_numpy(),ddof=1)) if len(df)>20 else None
        res[name]={'n':len(df),'corr_daily':corr(df),'beta_to_qqq':beta,'btc_ann_vol':float(df['rc'].std()*np.sqrt(252))}
    # weekly (every 5th obs)
    w=x.with_columns((pl.int_range(pl.len())//5).alias('g')).group_by('g').agg(pl.col('d').last(),(1+pl.col('rc')).product().alias('a'),(1+pl.col('rq')).product().alias('b'))
    w=w.sort('d')
    for name,(a,b) in {'anchor_weekly':('2024-01-08','2026-08-31'),'full_weekly':('2016-05-01','2026-09-01')}.items():
        df=w.filter((pl.col('d')>=pl.lit(a).str.to_date())&(pl.col('d')<=pl.lit(b).str.to_date()))
        res[name]={'n':len(df),'corr':float(np.corrcoef(df['a'].to_numpy(),df['b'].to_numpy())[0,1])}
    # rolling 60d corr distribution in anchor
    df=x.filter(pl.col('d')>=pl.lit('2024-01-08').str.to_date())
    r=df['rc'].to_numpy(); m=df['rq'].to_numpy(); roll=[float(np.corrcoef(r[i-60:i],m[i-60:i])[0,1]) for i in range(60,len(r))]
    res['roll60_anchor']={'min':min(roll),'p10':float(np.percentile(roll,10)),'median':float(np.median(roll)),'p90':float(np.percentile(roll,90)),'max':max(roll),'share_above_0.5':float(np.mean(np.array(roll)>0.5))}
    out[sym]=res
json.dump(out,open('/tmp/r36d_corr.json','w'),indent=1)
print(json.dumps(out,indent=1))
