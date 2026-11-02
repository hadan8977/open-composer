"""Request actual independent native reception; never grant stage authority."""
import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent / 'runs/model-completion-20261102-1'
OUT = ROOT / 'reports/research/program/martin-decision-loop-model-continuation-20261026'


def main(stage):
    definitions = {
        'training': ('training-v3-review.json', 'fit_go', [
            'training-v3/summary.json', 'training-v3/standardized.npz',
            'training-v3/scalers.json', 'training-v3/pairs-all-statuses.json',
            'training-v3/training-rows.json', 'training_data.py', '../martin-learned-payoff-state-20261026/training_scale_v3.py',
            'peer-review/label-output-v3-review.json']),
        'model': ('model-output-v3-review.json', 'calibration_go', [
            'summary-v3-fit01/result.json', 'summary-v3-fit01/model.pkl',
            'summary-v3-fit01/training-prediction.npy', 'tcn-v3-fit01/model.json',
            'tcn-v3-fit01/encoder-training-contract.json', 'tcn-v3-fit01/parity.npz',
            'tcn-v3-fit01/optimizer-checkpoint.pt', 'train_summary.py', 'train_tcn.py',
            '../martin-learned-payoff-state-20261026/learned_model_v3.py', 'scoring.py', 'peer-review/training-v3-review.json']),
        'account': ('account-review.json', 'financial_go', [
            'calibration-v3.json', 'calibration-v3-current-decisions.jsonl',
            'native_accounts.py', 'scoring.py', 'peer-review/model-output-v3-review.json']),
        'final': ('economic-output-v3-review.json', 'economic_result_accepted', [
            'economic-comparison.json', 'economic-flow-decomposition.json',
            'peer-review/account-review.json']),
    }
    name, field, files = definitions[stage]
    paths = [(OUT / f).resolve() for f in files]
    if stage=='final':
        request['assigned_reviewer']='fresh Lead of the existing research_round series'
        request['worker_state']='return completed economic evidence to fresh Lead; no additional peer wait'
        paths += [RUN/n for n in ['results.json','counts.json','economic-decision.json','economic-decision.zh.md']]
        paths += [ROOT/'reports/harness/forensics/martin_observed_attempt_value_20261026-backtest-forensics.json']
        paths += [RUN/'worker/resume-3/lab-import.json']
    assert all(p.is_file() for p in paths), 'Request actual completed evidence only'
    now = datetime.now(UTC)
    event = RUN / 'worker/resume-3'
    event.mkdir(exist_ok=True)
    target = RUN / 'review-request.json'
    suffix = now.strftime('%Y%m%dT%H%M%S%fZ')
    if target.exists():
        (event / ('review-request-before-' + suffix + '.json')).write_bytes(target.read_bytes())
    request = dict(at_utc=now.isoformat(), status='actual_' + stage + '_output_ready',
        assigned_reviewer='/root/claude_plan_review', stage=stage,
        requested_output=str((OUT / 'peer-review' / name).relative_to(ROOT)),
        requested_go_field=field,
        decision_needed='Independently receive the completed original frozen stage and write the actual native reception if accepted. Continue the same economic task; no new tests, native replay, scope change or owner per-step confirmation.',
        available_artifacts=[str(p.relative_to(ROOT)) for p in paths],
        bindings=[dict(path=str(p.relative_to(ROOT)), bytes=p.stat().st_size,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths],
        all_history_seen=True, native_gates_preserved=True,
        continuity_owner=str((RUN/'independent-reception-owner.json').relative_to(ROOT)),
        worker_state='continuing_same_task_with_dependent_stage_awaiting_actual_reception',
        all_label_remote_jobs_terminal=True, label_replay_requested=False)
    if stage=='final':
        request['raw_account_directories']=[str((OUT/'runs'/('2026-'+a)).relative_to(ROOT)) for a in 'RSTH']
        request['import_is_not_a_new_experiment']=True
        request['decision_needed']='Worker: after the actual four accounts and readback finish, return the complete Reply with results.json and this request; do not wait for the retired per-stage peer or self-accept the result. The existing fresh Lead independently receives R/S/T/H cash, fees, freshness, funding/tails, model increments and all attempts/costs, writes the native decisive reception if accepted, then dispatches the next economic brief. The Lead is the final independent receiver; no extra approval layer. No replay, retraining or scope change is authorized by this routing correction.'
    temporary=target.with_suffix('.json.resume3.tmp')
    assert not temporary.exists()
    temporary.write_text(json.dumps(request, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(target)
    (event/('review-request-'+stage+'-'+suffix+'.json')).write_bytes(target.read_bytes())
    print('MARTIN_CURRENT_RUN_EVENT '+json.dumps(dict(stage=stage, request=str(target.relative_to(ROOT)), requested_output=request['requested_output'])), flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('stage', choices=['training','model','account','final'])
    main(parser.parse_args().stage)
