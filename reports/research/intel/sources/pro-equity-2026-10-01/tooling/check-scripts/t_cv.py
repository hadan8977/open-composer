import numpy as np, pandas as pd, resource, time
from skfolio.model_selection import CombinatorialPurgedCV
n=1000
X=pd.DataFrame(np.random.default_rng(0).standard_normal((n,3)),index=pd.bdate_range("2020-01-01",periods=n))
cv=CombinatorialPurgedCV(n_folds=10,n_test_folds=2,purged_size=5,embargo_size=5)
print("n_splits",cv.get_n_splits(X))
tr,te=next(iter(cv.split(X))); print("test is list of",len(te),"folds"); te=np.concatenate([np.asarray(a) for a in te]); tr=np.asarray(tr)
print("split0 train n",len(tr),"test n",len(te),"test idx range",te.min(),te.max())
gap=[i for i in range(len(X)) if i not in set(tr) and i not in set(te)]
print("purged/embargoed obs (neither train nor test) in split0:",len(gap))
print("n paths",cv.n_test_paths if hasattr(cv,"n_test_paths") else "attr?"); print("path ids shape",np.asarray(cv.get_path_ids()).shape)
# use with a sklearn estimator-agnostic loop (LightGBM-style): ok because it is an index splitter
from sklearn.linear_model import Ridge
y=X.iloc[:,0].shift(-5)
s=0
for tr,te in cv.split(X):
    tr=np.asarray(tr); m=Ridge().fit(X.iloc[tr].fillna(0),y.iloc[tr].fillna(0)); s+=1
print("ridge folds",s)
# purgedcv package
import purgedcv; print([a for a in dir(purgedcv) if not a.startswith("_")])
print("rss MB",resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
