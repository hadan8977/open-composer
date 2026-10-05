import polars as pl, numpy as np, json
d=pl.scan_parquet('data/sip/daily/*/*.parquet').filter(pl.col('symbol').is_in(['SPY','QQQ','IWM'])).select('symbol',pl.col('timestamp').dt.date().alias('d'),'open','close').collect().unique(['symbol','d']).sort(['symbol','d'])
out={}
for s in ['SPY','QQQ','IWM']:
    x=d.filter(pl.col('symbol')==s).with_columns((pl.col('open')/pl.col('close').shift(1)-1).alias('on'),(pl.col('close')/pl.col('close').shift(1)-1).alias('cc')).drop_nulls()
    y=x.filter(pl.col('d')>=pl.lit('2024-01-08').str.to_date())
    out[s]={'corr_on_vs_closeclose_anchor':float(np.corrcoef(y['on'].to_numpy(),y['cc'].to_numpy())[0,1]),'corr_on_vs_closeclose_full':float(np.corrcoef(x['on'].to_numpy(),x['cc'].to_numpy())[0,1]),'nights_per_year':len(x)/ ((x['d'].max()-x['d'].min()).days/365.25)}
print(json.dumps(out)); json.dump(out,open('/tmp/r36d_on_corr.json','w'))
r=json.load(open('reports/research/iterations/h20260929_33_crypto_trend/results.json'))['candidates']
print({k:round(v['correlation_with_s3_anchor'],2) for k,v in r.items() if 'correlation_with_s3_anchor' in v})
