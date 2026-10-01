import numpy as np, cvxpy as cp, time, resource, sys
rng=np.random.default_rng(0)
def run(N,K=15,S=11,solver="CLARABEL"):
    F=rng.standard_normal((N,K))*0.01      # style+PCA exposures (N,K)
    Sig=np.diag(rng.uniform(0.5,2,K))*1e-4 # factor cov
    L=np.linalg.cholesky(Sig)
    d=rng.uniform(1e-4,4e-4,N)             # idio var (daily)
    sec=rng.integers(0,S,N); Sx=np.eye(S)[sec]  # sector one-hot (N,S)
    beta=rng.uniform(0.6,1.5,N)
    alpha=rng.standard_normal(N)*5e-4      # daily expected return
    w0=np.zeros(N); w0[rng.choice(N,N//4,replace=False)]=rng.standard_normal(N//4)*0.003
    adv=rng.uniform(5e6,2e8,N); sigd=rng.uniform(0.01,0.03,N); book=2e7
    a=5e-4/2; b=1.0
    w=cp.Variable(N)
    z=w-w0
    # costs in return units per unit weight: half-spread + 3/2 impact: b*sigma*(|z|*book)^1.5/sqrt(ADV) /book
    c_imp=b*sigd*book**0.5/np.sqrt(adv)
    cost=a*cp.norm1(z)+cp.sum(cp.multiply(c_imp,cp.power(cp.abs(z),1.5)))
    borrow=cp.sum(cp.multiply(0.03/252*np.ones(N),cp.neg(w)))   # 3% annual borrow on shorts
    risk=cp.sum_squares(L.T@(F.T@w))+cp.sum_squares(cp.multiply(np.sqrt(d),w))
    obj=cp.Maximize(alpha@w-5.0*risk-cost-borrow-1e-3*cp.norm1(z))
    cons=[cp.sum(w)==0, beta@w==0, Sx.T@w==0, cp.abs(w)<=0.02, cp.norm1(w)<=2.0, cp.norm1(z)<=0.25]
    # easy-to-borrow only: names not ETB cannot be short
    hard=rng.random(N)<0.1; cons.append(w[np.where(hard)[0]]>=0)
    p=cp.Problem(obj,cons); t=time.time()
    p.solve(solver=solver)
    print(f"N={N} solver={solver} status={p.status} t={time.time()-t:.1f}s val={p.value:.6f} gross={np.abs(w.value).sum():.2f} net={w.value.sum():.1e} beta={beta@w.value:.1e} maxsecdev={np.abs(Sx.T@w.value).max():.1e} turnover={np.abs(w.value-w0).sum():.3f} rss={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f}MB",flush=True)
for N in [int(x) for x in sys.argv[1:]]: run(N)
