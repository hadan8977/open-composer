import polars as pl
lf=pl.scan_parquet('data/sip/minute/2026/09/*.parquet').filter((pl.col('symbol')=='SPY')&(pl.col('timestamp')>=pl.datetime(2026,9,15,time_zone='UTC'))&(pl.col('timestamp')<pl.datetime(2026,9,16,time_zone='UTC')))
df=lf.collect(engine='streaming')
print(df.shape)
et=df.with_columns(pl.col('timestamp').dt.convert_time_zone('America/New_York').alias('et'))
print(et['et'].min(), et['et'].max())
import json; t=et.group_by(pl.col('et').dt.hour().alias('h')).agg(pl.len().alias('bars'),pl.col('volume').sum().alias('vol')).sort('h'); print(json.dumps({int(h):[int(b),float(v)] for h,b,v in t.iter_rows()}))
