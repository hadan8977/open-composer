import numpy as np, pandas as pd, time, resource, warnings
warnings.filterwarnings("ignore")
import cvxportfolio as cvx
rng=np.random.default_rng(1)
T,N=700,80
idx=pd.bdate_range("2021-01-04",periods=T,tz="UTC")+pd.Timedelta(hours=14,minutes=30)
names=[f"S{i:03d}" for i in range(N)]
mkt=rng.standard_normal(T)*0.01
beta=rng.uniform(0.5,1.5,N)
sig=rng.uniform(0.01,0.02,N)
ret=pd.DataFrame(np.outer(mkt,beta)+rng.standard_normal((T,N))*sig,index=idx,columns=names)
prices=pd.DataFrame(50*np.exp(np.cumsum(ret.values,0)),index=idx,columns=names)
vol=pd.DataFrame(rng.uniform(2e6,5e7,(T,N)),index=idx,columns=names)
# a toy signal: next-period return + noise (cheating on purpose; this is an API/timing test, not research)
alpha=ret.shift(-1)*0.05
md=cvx.UserProvidedMarketData(returns=ret,volumes=vol,prices=prices,cash_key="cash",min_history=pd.Timedelta("90d"))
gamma,kappa=5.0,1.0
obj=cvx.ReturnsForecast(alpha.fillna(0))-gamma*cvx.FactorModelCovariance(num_factors=5)-kappa*cvx.StocksTransactionCost(a=2.5e-4,b=1.0,exponent=1.5)-cvx.StocksHoldingCost(short_fees=3)
cons=[cvx.DollarNeutral(),cvx.MarketNeutral() if hasattr(cvx,"MarketNeutral") else cvx.DollarNeutral(),cvx.MaxWeights(0.05),cvx.MinWeights(-0.05),cvx.LeverageLimit(2),cvx.TurnoverLimit(0.25)]
pol=cvx.SinglePeriodOptimization(obj,cons,solver="CLARABEL")
sim=cvx.MarketSimulator(market_data=md,costs=[cvx.StocksTransactionCost(a=2.5e-4),cvx.StocksHoldingCost(short_fees=3)])
t=time.time()
res=sim.backtest(pol,start_time=idx[400],end_time=idx[460],initial_value=1e7)
print("backtest 60 days N=80 s",round(time.time()-t,1))
print(res.sharpe_ratio if hasattr(res,"sharpe_ratio") else "no sharpe", "turnover",res.turnover, "leverage",res.leverage)
print("rss MB",resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
