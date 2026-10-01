import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, time, resource
import alphalens as al
rng=np.random.default_rng(0); T,N=500,500
idx=pd.bdate_range("2022-01-03",periods=T,tz="UTC"); names=[f"S{i}" for i in range(N)]
ret=rng.standard_normal((T,N))*0.015
prices=pd.DataFrame(50*np.exp(np.cumsum(ret,0)),index=idx,columns=names)
sig=pd.DataFrame(ret,index=idx,columns=names).rolling(5).sum().shift(1)*(-1)  # a weak reversal-like factor
fac=sig.stack().dropna(); fac.index.names=["date","asset"]
sectors={n:i%11 for i,n in enumerate(names)}
t=time.time()
fd=al.utils.get_clean_factor_and_forward_returns(fac,prices,quantiles=5,periods=(1,5,10,21),groupby=sectors,max_loss=0.35)
print("clean s",round(time.time()-t,1),fd.shape)
ic=al.performance.factor_information_coefficient(fd); print(ic.mean().round(4).to_dict()); print("ICIR1",round(float(ic.iloc[:,0].mean()/ic.iloc[:,0].std()),3))
mq,_=al.performance.mean_return_by_quantile(fd); print(mq.round(5).iloc[:,0].to_dict())
ac=al.performance.factor_rank_autocorrelation(fd,period=1); print("rank autocorr 1d",round(float(ac.mean()),3))
print("quantile turnover:", [round(float(al.performance.quantile_turnover(fd["factor_quantile"],q,period=1).mean()),3) for q in (1,5)])
print("rss MB",resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
