"""Add omitted original ETF rows; preserve all original artifacts and account attempts."""
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from open_composer.research.equity_book.panel import PricePanel,DEFAULT_DIR
from open_composer.research.features.price_hygiene import sanitize_price_matrices
from prepare import OUT,save
c=pd.read_parquet(OUT/'close.parquet');o=pd.read_parquet(OUT/'open.parquet')
f=pd.read_parquet(DEFAULT_DIR/'etf_daily.parquet',filters=[('symbol','==','SPY'),('trade_date','<=',pd.Timestamp('2026-09-15')),('trade_date','>=',pd.Timestamp('2016-01-04'))],columns=['trade_date','symbol','open','close'])
assert not f.trade_date.duplicated().any();f=f.set_index('trade_date').reindex(c.index)
assert f.loc['2024-01-05':,['open','close']].notna().all().all()
c['SPY']=f.close;o['SPY']=f.open
cc,oo,h=sanitize_price_matrices(c,o)
assert cc.drop(columns='SPY').equals(c.drop(columns='SPY'))
assert oo.drop(columns='SPY').equals(o.drop(columns='SPY'))
cc.to_parquet(OUT/'close-with-spy.parquet');oo.to_parquet(OUT/'open-with-spy.parquet')
save('spy-input-addendum.json',{'source':str((DEFAULT_DIR/'etf_daily.parquet').relative_to(ROOT)),'SPY_rows':len(f),'recent_support_complete':True,'stock_prices_unchanged':True,'cash_accounts_unchanged':True,'affected_account':'Original SPY-c1 zero-fill account invalid, retained; corrected account id suffix prices-r1. Original interrupted stock attempt retained and explicitly repaired; complete stock account dollars reused.','hygiene':h.manifest()})
print('SPY REPAIR',len(f),flush=True)
