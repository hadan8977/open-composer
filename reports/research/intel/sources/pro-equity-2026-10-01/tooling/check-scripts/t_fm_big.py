import time,resource,numpy as np
from skfolio.datasets import make_synthetic_characteristics
from skfolio.prior import CharacteristicsFactorModel
from skfolio.factor_exposure import GlobalFactor, OneHotCategoricalFactors, FixedWeightedFactor
from skfolio.descriptor import EWMarketBeta, LogMarketCap
import skfolio.descriptor as d
t=time.time()
ch=make_synthetic_characteristics(n_assets=1000,n_observations=1500,random_state=0)
print(type(ch), "gen",round(time.time()-t,1))
try: print(ch.info())
except Exception as e: print("info err",e)
model=CharacteristicsFactorModel(
  factors=[("market",GlobalFactor(family="market")),
           ("industry",OneHotCategoricalFactors(category="industry",family="industry")),
           ("size",FixedWeightedFactor(descriptors=[("log_market_cap",LogMarketCap())],transform_by_group="industry"))],
  constrained_families=[("industry",None)],exposure_lag=1,n_jobs=1)
t=time.time(); model.fit(characteristics=ch); print("fit s",round(time.time()-t,1))
fm=model.factor_model_; print(type(fm)); s=fm.summary(); print(str(s)[:600])
rd=model.return_distribution_; print("cov shape",np.asarray(rd.covariance).shape)
print("rss MB",resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
