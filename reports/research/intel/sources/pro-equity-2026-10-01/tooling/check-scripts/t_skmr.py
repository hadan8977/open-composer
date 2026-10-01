import time,resource,numpy as np,cvxpy as cp, warnings
warnings.filterwarnings("ignore")
from sklearn import set_config
set_config(enable_metadata_routing=True)
from skfolio import RiskMeasure
from skfolio.optimization import MeanRisk, ObjectiveFunction
from skfolio.datasets import make_synthetic_characteristics
from skfolio.prior import CharacteristicsFactorModel
from skfolio.factor_exposure import GlobalFactor, OneHotCategoricalFactors, FixedWeightedFactor
from skfolio.descriptor import LogMarketCap
ch=make_synthetic_characteristics(n_assets=500,n_observations=500,random_state=0)
model=CharacteristicsFactorModel(
  factors=[("market",GlobalFactor(family="market")),("industry",OneHotCategoricalFactors(category="industry",family="industry")),
           ("size",FixedWeightedFactor(descriptors=[("log_market_cap",LogMarketCap())],transform_by_group="industry"))],
  constrained_families=[("industry",None)],exposure_lag=1,n_jobs=1)
X=ch.to_dataframe(fields="returns"); inds=ch.fields["industry"].levels
N=X.shape[1]; rng=np.random.default_rng(0)
adv=rng.uniform(5e6,2e8,N); sig=np.full(N,0.015); book=2e7
c_imp=sig*book**0.5/np.sqrt(adv)
def impact(w,m=None):
    z=w-(m.previous_weights if (m is not None and m.previous_weights is not None) else 0)
    return cp.sum(cp.multiply(c_imp,cp.power(cp.abs(z),1.5)))
alpha=rng.standard_normal(N)*1.5e-3
def sub(m,v):
    mask=getattr(m,"investable_mask_",None); return v if mask is None else v[mask]
w0=np.zeros(N)
for pen in [None,"impact"]:
    kw={}
    if pen: kw=dict(add_objective=lambda w,m: -1.0*cp.sum(cp.multiply(sub(m,c_imp),cp.power(cp.abs(w-sub(m,w0)),1.5))))
    mr=MeanRisk(objective_function=ObjectiveFunction.MAXIMIZE_UTILITY,risk_measure=RiskMeasure.VARIANCE,risk_aversion=1.0,prior_estimator=model,
        max_weights=0.03,min_weights=-0.03,budget=0.0,max_long=1.0,transaction_costs=0.0005,previous_weights=w0,
        overwrite_expected_return=lambda w,m: sub(m,alpha)@w,
        linear_constraints=["size == 0"]+[f"{n} == 0.0" for n in inds], solver="CLARABEL", **kw)
    t=time.time(); mr.fit(X,characteristics=ch)
    w=mr.weights_; print(pen,"fit s",round(time.time()-t,1),"gross",round(np.abs(w).sum(),3),"net",round(w.sum(),6),"maxabs",round(np.abs(w).max(),4),"n_investable",int(mr.investable_mask_.sum()) if getattr(mr,"investable_mask_",None) is not None else N)
print("rss MB",resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
