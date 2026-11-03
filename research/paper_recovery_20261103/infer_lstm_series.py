"""Historical inference with the accepted Oct30 input sequence and frozen models.

Only save an independent all-dates forecast artifact; never train or publish targets.
"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from open_composer.market_sessions import us_equity_session_dates
from open_composer.paper_runtime.source_loader import load_source

OUT=ROOT/'reports/owner/paper-recovery-20261103'
DAY=ROOT/'reports/paper/diagnostics/dated-target-refresh/2026-11-02'
T=ROOT/'reports/research/program/owner-profit-delivery-plan-20261017/current-paper-science-20261020'


def main():
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True);torch.backends.mkldnn.enabled=False
    method_path=T.parent.parent/'return-line-replenishment-20261016/direct-position-learning-20261016/torch_method.py'
    method=load_source('paper_recovery_frozen_lstm',method_path,root=ROOT)
    old=json.loads((T/'input/LSTM/output.json').read_text())
    z=np.load(DAY/'current-lstm-sequence.npz',allow_pickle=False)
    x,vol=z['features'],z['vol'];qa=json.loads((DAY/'lstm-input-QA.json').read_text())
    assert hashlib.sha256((DAY/'current-lstm-sequence.npz').read_bytes()).hexdigest()==qa['sequence']['sha256']
    assert qa['old2701_prefix_bitexact'] and qa['previous_current_sequence']['features_bitexact'] and qa['previous_current_sequence']['vol_bitexact']
    dates=us_equity_session_dates(date(2026,1,2),date(2026,10,30))
    assert len(dates)==len(x)-63==qa['annual_sessions']
    predictions=[];errors=[]
    for context in old['model_context']:
        checkpoint=Path(context['checkpoint']['path']);assert hashlib.sha256(checkpoint.read_bytes()).hexdigest()==context['checkpoint']['sha256']
        ckpt=torch.load(checkpoint,map_location='cpu',weights_only=True)
        prep=context['preprocessing'];full=np.clip(x,prep['low'],prep['high']);full=np.where(np.isfinite(full),full,prep['median'])
        xt=torch.from_numpy(((full-prep['mean'])/prep['std']).astype(np.float32))
        model=method.PositionLSTM();model.load_state_dict(ckpt['state'],strict=True);model.eval()
        with torch.no_grad():
            _,hidden=model(xt[:63]);logits=[]
            for i in range(63,len(xt),63):
                q,hidden=model(xt[i:i+63],hidden);logits.append(q);hidden=tuple(z.detach()for z in hidden)
            scores=torch.cat(logits);weights=method.weights(scores,torch.from_numpy(vol[63:]),'MEANNET')
        original=np.load(context['saved_forecast']['path'],allow_pickle=False)
        err=float(np.max(np.abs(scores[:185].numpy()-original['raw_scores'])));assert err<=2e-6
        errors.append(err);predictions.append(weights.numpy())
    mean=np.mean(predictions,axis=0)
    last=json.loads((DAY/'current-lstm-inference.json').read_text())
    error=float(np.max(np.abs(mean[-1]-last['weights'])));assert error<=2e-6
    output={'reference_dates':[str(d)for d in dates],'symbols':['SPY','QQQ','IWM','EFA','EEM','IEF','TLT','GLD','DBC','UUP'],'weights':mean.tolist(),'original_score_prefix_errors':errors,'last_forecast_max_error':error,'input_sequence':qa['sequence'],'models':old['model_context'],'new_fits':0,'historical_inference_count':2,'input_cutoff':'2026-10-30','input_uses_future_rows':False}
    (OUT/'lstm-frozen-series.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({k:output[k]for k in ['new_fits','historical_inference_count','original_score_prefix_errors','last_forecast_max_error','input_cutoff']}))


if __name__=='__main__':main()
