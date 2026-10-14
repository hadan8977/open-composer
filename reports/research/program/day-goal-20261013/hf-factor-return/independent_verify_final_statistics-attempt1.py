"""Independent persisted-forecast inference audit; no fit, prediction or economics."""
import json
import math
import os
import resource
from pathlib import Path

import numpy as np

resource.setrlimit(resource.RLIMIT_CPU, (55, 60))
assert os.sched_getaffinity(0) == {0}
P = Path(__file__).resolve().parent
E = P / "economic"
O = E / "results"
checks = 0


def read(p):
    return json.loads(Path(p).read_text())


def eq(x, y, message, atol=1e-16):
    global checks
    checks += 1
    assert np.allclose(x, y, rtol=1e-8, atol=atol, equal_nan=True), message


lm, hm = read(E / "linear-model-manifest.json"), read(E / "HGB-model-manifest.json")
ids = lm["candidate_ids"] + hm["candidate_ids"]
pred = np.column_stack([np.load(E / "linear-predictions.npy"), np.load(E / "HGB-predictions.npy")])
rows = read(P / "features/packet-row-clock.json")
dates = np.array([x["date"] for x in rows])
years = np.array([int(x[:4]) for x in dates])
y = np.load(P / "features/labels.npy", mmap_mode="r")[:len(rows)]
assert pred.shape == (136597, 20) and y.shape[1] == 2
stats = read(O / "statistical-results.json")
for j, name in enumerate(ids):
    for col, label in enumerate(("All", "Cts")):
        for yr in [None] + list(range(2004, 2021)):
            mask = np.isfinite(pred[:, j]) & np.isfinite(y[:, col])
            if yr is not None:
                mask &= years == yr
            truth, forecast = y[mask, col], pred[mask, j]
            reported = stats[name][label][str(yr) if yr else "full"]
            assert reported["n"] == len(truth)
            eq(reported["uncentered_R2"], 1-np.sum((forecast-truth)**2)/np.sum(truth**2), "R2")
            eq(reported["RMSE"], np.sqrt(np.mean((forecast-truth)**2)), "RMSE")
for f in lm["folds"]:
    if "validation_last_row" in f:
        assert years[f["train_last_row"]] <= years[f["validation_last_row"]] < f["year"]
paired = read(O / "paired-results.json")
ix = {v:i for i,v in enumerate(ids)}
contrasts = read(P / "scientific-plan.json")["inference_and_contribution"]["primary_contrasts"]
needed = sorted({ix[x[k]] for x in contrasts for k in ("treatment_id", "control_id")})
summaries = {}
for col, target in enumerate(("All_primary", "Cts_descriptive")):
    mask = np.isfinite(pred[:,needed]).all(axis=1) & np.isfinite(y[:,col])
    unique, group = np.unique(dates[mask],return_inverse=True)
    count = np.bincount(group)
    sums = np.column_stack([np.bincount(group,weights=(pred[mask,ix[c["control_id"]]]-y[mask,col])**2-(pred[mask,ix[c["treatment_id"]]]-y[mask,col])**2) for c in contrasts])
    saved = np.load(O / f"paired-{target}.npz")
    assert np.array_equal(unique,saved['dates']) and np.array_equal(count,saved['counts'])
    eq(sums,saved['day_sums'],"day loss sums")
    est = sums.sum(0)/count.sum()
    residual = sums-count[:,None]*est
    T=len(count)
    variance=(residual*residual).sum(0)/T
    for lag in range(1,6):
        variance += 2*(1-lag/6)*(residual[lag:]*residual[:-lag]).sum(0)/T
    se=np.sqrt(np.maximum(variance,0)*T)/count.sum()
    rng=np.random.default_rng(20261013)
    starts=rng.integers(0,T,size=(2000,math.ceil(T/20)))
    boots=np.empty((2000,6))
    for first in range(0,2000,20):
        indices=((starts[first:first+20,:,None]+np.arange(20))%T).reshape(20,-1)[:,:T]
        boots[first:first+20]=sums[indices].sum(1)/count[indices].sum(1)[:,None]
    eq(boots,saved['bootstrap_estimates'],"2000 fixed-seed bootstrap estimates")
    maxima=np.abs((boots-est)/se).max(1)
    record=paired[target]
    assert record['common_windows']==int(count.sum()) and record['common_days']==T
    results=[]
    for j,c in enumerate(contrasts):
        r=record['paired'][j]
        z=est[j]/se[j]
        eq(r['loss_control_minus_treatment'],est[j],'paired loss')
        eq(r['SE'],se[j],'HAC SE')
        eq(r['MDE80_two_sided_normal'],(1.959963984540054+.8416212335729143)*se[j],'MDE')
        eq(r['p_two_sided'],math.erfc(abs(z)/np.sqrt(2)),'nominal p')
        eq(r['block20_bootstrap_95'],np.quantile(boots[:,j],[.025,.975]),'bootstrap interval')
        pvalue=(1+(maxima>=abs(z)).sum())/2001
        eq(r['joint_two_sided_maxT_p'],pvalue,'joint maxT')
        results.append({'id':c['contrast_id'],'loss_difference':float(est[j]),'SE':float(se[j]),'joint_maxT_p':float(pvalue)})
    summaries[target]={'windows':int(count.sum()),'days':T,'first':unique[0],'last':unique[-1],'results':results}
out={'status':'pass','numeric_assertions':checks,'all20_forecast_pipelines':True,'full_and17year_R2_RMSE_all_and_cts':True,'common_six_contrasts_both_targets':summaries,'all2000_bootstrap_rows_recomputed':True,'large_HAR_or_source_values_read':False,'only_stored_predictions_small_labels_clock_used':True,'model_fit_or_inference_calls':0,'CPU_affinity':list(os.sched_getaffinity(0))}
(P/'independent-final-statistics-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
