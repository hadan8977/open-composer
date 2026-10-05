import polars as pl, numpy as np, json
syms=['SPY','QQQ','IWM']
d=pl.scan_parquet('data/sip/daily/*/*.parquet').filter(pl.col('symbol').is_in(syms)).select('symbol',pl.col('timestamp').dt.date().alias('d'),'open','close').collect().unique(['symbol','d']).sort(['symbol','d'])
out={}
for s in syms:
    x=d.filter(pl.col('symbol')==s).with_columns((pl.col('open')/pl.col('close').shift(1)-1).alias('on'),(pl.col('close')/pl.col('open')-1).alias('id')).drop_nulls()
    res={}
    for name,(a,b) in {'full_2016-2026':('2016-01-01','2026-09-29'),'2016-2019':('2016-01-01','2019-12-31'),'2020-2022':('2020-01-01','2022-12-31'),'2023-2026':('2023-01-01','2026-09-29'),'anchor_2024-01-08..':('2024-01-08','2026-09-29')}.items():
        y=x.filter((pl.col('d')>=pl.lit(a).str.to_date())&(pl.col('d')<=pl.lit(b).str.to_date()))
        on=y['on'].to_numpy(); idr=y['id'].to_numpy(); n=len(on)
        res[name]={'n':n,'on_mean_bp':float(on.mean()*1e4),'on_t':float(on.mean()/on.std(ddof=1)*np.sqrt(n)),'id_mean_bp':float(idr.mean()*1e4),'id_t':float(idr.mean()/idr.std(ddof=1)*np.sqrt(n)),'on_ann_sharpe_gross':float(on.mean()/on.std(ddof=1)*np.sqrt(252)),'on_cumulative_pct':float((np.prod(1+on)-1)*100),'id_cumulative_pct':float((np.prod(1+idr)-1)*100)}
    out[s]=res
# break-even: per-night cost bp for two crossings
json.dump(out,open('/tmp/r36d_on.json','w'),indent=1); print(json.dumps(out,indent=1))

# net-of-cost and buy-and-hold comparison
net={}
for s in syms:
    x=d.filter(pl.col('symbol')==s).with_columns((pl.col('open')/pl.col('close').shift(1)-1).alias('on'),(pl.col('close')/pl.col('close').shift(1)-1).alias('cc')).drop_nulls()
    for name,(a,b) in {'full':('2016-01-01','2026-09-29'),'anchor':('2024-01-08','2026-09-29')}.items():
        y=x.filter((pl.col('d')>=pl.lit(a).str.to_date())&(pl.col('d')<=pl.lit(b).str.to_date()))
        on=y['on'].to_numpy(); cc=y['cc'].to_numpy()
        row={'bh_sharpe':float(cc.mean()/cc.std(ddof=1)*np.sqrt(252)),'bh_ann_vol':float(cc.std(ddof=1)*np.sqrt(252)),'on_ann_vol':float(on.std(ddof=1)*np.sqrt(252))}
        for c in [0,0.5,1,2,3,5]:
            r=on-2*c*1e-4
            row[f'on_net_sharpe_{c}bp_per_side']=float(r.mean()/r.std(ddof=1)*np.sqrt(252))
        row['breakeven_bp_per_side']=float(on.mean()*1e4/2)
        net[f'{s}_{name}']=row
json.dump(net,open('/tmp/r36d_on_net.json','w'),indent=1)
for k,v in net.items(): print(k,{a:round(b,2) for a,b in v.items()})
