"""Seal the accepted capacity decision using small evidence only; never fit/infer."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import resource
import sys
from datetime import datetime, timezone

ROOT = Path('/root/codex-test/open-composer')
P = ROOT / 'reports/research/program/day-goal-20261013/hf-factor-return'
D = ROOT / 'reports/research/iterations/t20261013_hf_factor_conditional_method'
E = P / 'economic'
A = P / 'economic-resource-decision-archive'
OWNER = '7b109880-ac40-447e-b2a6-f0ed1266ebac'
PEER = 'ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3'
TASK = 'DAY3-HF-FACTOR-RETURN'
CAP = 7006.69
REVIEW_SHA = '37f8faf467ce0f81f2fb4c7da2c9dc3432cf9154f6aa11cefc4a866d7a455c2c'
OLD = {
    'result.json': 'da1997b57ea5149e0cd09735d7f9166dff2ab4e113ae6b76b1488aa71279fd07',
    'final-manifest.json': '4207c2821cf6631a62d4d1c30fe21ee3544bfec074cde4bd829a397d3ab4514c',
    'continuation-resource-result.json': 'e281bbbd62e8e0953ba14dda07da83d36d2a1206069256b38f1b266028cc3bac',
    'continuation-resource-final-manifest.json': '099ebaa8e434e3cce6c37e211fad7a1a7bf33f79636b749744de6797898f8d58',
}


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def binding(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    # Only the two small persisted checkpoints may exceed this limit.
    size = path.stat().st_size
    assert size <= 1_000_000 or (
        path.parent == E / 'models' and size < 3_000_000
    ), f'Unapproved large read: {path} ({size})'
    h = hashlib.sha256()
    with path.open('rb') as f:
        while block := f.read(1 << 20):
            h.update(block)
    return {'path': str(path.relative_to(ROOT)), 'sha256': h.hexdigest(), 'bytes': size}


def verify(record):
    actual = binding(record['path'])
    assert actual['sha256'] == record['sha256'], record['path']
    assert actual['bytes'] == record['bytes'], record['path']
    return actual


def write(path, value):
    path = Path(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def snapshot(src, target):
    src, target = Path(src), Path(target)
    original = src.read_bytes()
    if target.exists():
        assert target.read_bytes() == original, str(target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original)
    return binding(target)


def build():
    assert read(ROOT / 'reports/research/control/owner-compute-hold.json')['research_paused'] is False
    review = read(P / 'independent-economic-capacity-decision-review.json')
    assert binding(P / 'independent-economic-capacity-decision-review.json')['sha256'] == REVIEW_SHA
    assert review['verdict'] == 'accept_resource_decision'
    assert review['author'] == OWNER and review['reviewer'] == PEER
    decision = read(P / 'economic-capacity-decision.json')
    for r in review['bindings'].values():
        verify(r)
    for name, sha in OLD.items():
        assert binding(P / name)['sha256'] == sha, name
    for checkpoint in decision['checkpoints']:
        verify(checkpoint['checkpoint'])
    assert not (E / 'models/HGB-IDX-2019-depth6-lr0.1-trees350.pkl').exists()
    assert not (E / 'full-resource-projection.json').exists()
    assert read(P / 'extension-native-gate.json')['status'] == 'ok'
    assert read(P / 'independent-implementation-review.json')['verdict'] == 'approve_implementation'
    assert read(P / 'independent-feature-input-acceptance.json')['verdict'] == 'accept_complete_conditional_feature_input'
    inflight = read(E / 'calibrate-inflight.json')
    process = Path(f"/proc/{inflight['pid']}")
    if process.exists():
        command = (process / 'cmdline').read_bytes()
        assert b'hf_run_models' not in command, 'An old calibration process is still active'
    A.mkdir(exist_ok=True)
    snapshot(P / 'current-state.json', A / 'current-state-before-closeout.json')
    snapshot(D / 'decision-record.md', A / 'native-decision-record-before-closeout.md')
    paths = [
        'economic-capacity-decision.json', 'economic-capacity-decision.md',
        'economic-capacity-kernel-observation.json',
        'independent-economic-capacity-decision-review.json',
        'independent-economic-capacity-verification.json',
        'independent_verify_economic_capacity.py',
        'scientific-plan.json', 'execution-contract.json', 'scientific-plan-revision.json',
        'independent-plan-review.json', 'implementation-manifest.json',
        'independent-implementation-review.json', 'independent-feature-input-acceptance.json',
        'independent-complete-source-input-acceptance.json',
        'complete-source-input-manifest.json', 'continuation-source-request-ledger.json',
        'independent-market-cache-bridge-acceptance.json',
        'independent-market-resource-decision-review.json', 'market-cache-bridge-manifest.json',
        'root-preparation-native-extension.json', 'root-source-continuation-decision.json',
        'preparation-resource-continuation-11.json', 'extension-native-gate.json',
        'extension-knowledge-native-receipt.json', 'resource-admission.json',
        'economic/calibration-progress.json', 'economic/calibrate-inflight.json',
        'economic/model-trial-ledger.jsonl', 'economic/HGB-input-IDX-2019.json',
        'economic/calibrate-resource-001.txt', 'economic/calibrate-resource-002.txt',
        'economic/capacity-analysis-resource-001.txt',
        'economic/independent-capacity-review-resource-001.txt',
        *OLD.keys(),
    ]
    files, archives = [], []
    for name in paths:
        files.append(binding(P / name))
        archives.append(snapshot(P / name, A / name))
    for name in ['hf_features.py', 'hf_models.py', 'hf_accounts.py', 'hf_diagnostics.py',
                 'hf_run_models.py', 'hf_evaluate.py', 'hf_native_policy_batch.py']:
        files.append(binding(P / name))
    for path in sorted(D.iterdir()):
        if path.is_file():
            files.append(binding(path))
            archives.append(snapshot(path, A / 'native-at-calibration' / path.name))
    files.extend(binding(Path(c['checkpoint']['path'])) for c in decision['checkpoints'])
    files.append(binding(Path(__file__)))
    write(P / 'economic-closeout-evidence-index.json', {
        'schema_version': 1, 'task_id': TASK, 'as_of_utc': now(),
        'scope': 'Small evidence and two checkpoint hashes only; no large input rehash, deserialization, prediction, fit, return computation or source request.',
        'files': files, 'immutable_archives': archives,
        'input_and_implementation_71_of71_already_accepted_not_rehashed': True,
        'source300_and_market361_guards_reused_not_rehashed': True,
        'former_inflight_PID': inflight['pid'], 'former_inflight_process_active': False,
        'old_results_and_manifests_exact_bytes_preserved': True,
    })
    print(json.dumps({'status': 'built', 'direct_files': len(files), 'archives': len(archives),
                      'fits': 0, 'large_input_reads': 0}))


def measured_cpu(path):
    text = Path(path).read_text()
    user = float(re.search(r'User time \(seconds\): ([0-9.]+)', text).group(1))
    system = float(re.search(r'System time \(seconds\): ([0-9.]+)', text).group(1))
    return round(user + system, 2)


def seal():
    stamp = now()
    review = read(P / 'independent-economic-capacity-decision-review.json')
    decision = read(P / 'economic-capacity-decision.json')
    index = read(P / 'economic-closeout-evidence-index.json')
    prep = read(P / 'preparation-resource-continuation-11.json')
    closeout_cpu = measured_cpu(E / 'capacity-closeout-resource-001.txt')
    author_cpu = round(sum(r['inclusive_CPU'] for r in decision['economic_receipts']), 2)
    assert author_cpu == 453.67 and review['resource']['review_total_charge'] == 4.22
    # Includes earlier final small reads, admission/setup, this seal and its final checks.
    # Unknown costs are explicit rather than omitted from /time-only accounting.
    closeout_unknown = 2.0
    total = round(author_cpu + 4.22 + closeout_cpu + closeout_unknown, 2)
    remaining = round(CAP - total, 2)
    assert remaining > 0
    ledger = {
        'schema_version': 1, 'task_id': TASK, 'as_of_utc': stamp,
        'pool': 'Unique original HF economic7006.69; no added budget',
        'economic_CPU_cap': CAP, 'author_closed_jobs': decision['economic_receipts'],
        'author_closed_job_CPU': author_cpu,
        'independent_review': {
            'review': binding(P / 'independent-economic-capacity-decision-review.json'),
            'receipt': binding(E / 'independent-capacity-review-resource-001.txt'),
            'actual_measured_CPU': 1.22, 'nonzero_small_read_setup_seal_allowance_CPU': 3.0,
            'total_charge_CPU': 4.22, 'charged_once_to_original_review300_reservation': True,
        },
        'closeout': {
            'receipt': binding(E / 'capacity-closeout-resource-001.txt'),
            'actual_inclusive_CPU': closeout_cpu,
            'small_reads_admission_setup_final_seal_and_checks_nonzero_allowance_CPU': closeout_unknown,
            'charge_CPU': round(closeout_cpu + closeout_unknown, 2),
            'scope': 'Only evidence hashes, preservation, ordinary status/report/ledger closeout.',
            'no_fit_inference_or_financial_evaluation': True,
        },
        'cumulative_measured_CPU': round(author_cpu + 1.22 + closeout_cpu, 2),
        'explicit_nonzero_unknown_allowance_CPU': 5.0,
        'cumulative_conservative_CPU': total,
        'remaining_economic_CPU': remaining,
        'remaining_is_not_fullstudy_or_retry_admission': True,
        'calibration450_actual_inclusive452_21_excess2_21_retained': True,
        'old_163_31_plus30_and_old500_reservations_not_reset_borrowed_or_released': True,
        'preparation2300': {
            'ledger': binding(P / 'preparation-resource-continuation-11.json'),
            'cumulative_CPU': prep['cumulative_conservative_CPU'],
            'remaining_CPU': prep['remaining_of2300'], 'closeout_charged_here': False,
        },
        'new_source_market_fit_inference_cloud_paid_orders': 0,
    }
    write(P / 'economic-resource-ledger.json', ledger)
    result = {
        'schema_version': 1, 'task_id': TASK, 'author': OWNER, 'reviewer': PEER,
        'as_of_utc': stamp, 'decision': 'stop_unadmitted_full_package_pending_material_resource_allocation',
        'resource_decision_complete': True, 'independent_verdict': 'accept_resource_decision',
        'independent_review': binding(P / 'independent-economic-capacity-decision-review.json'),
        'immutable_author_capacity_decision': binding(P / 'economic-capacity-decision.json'),
        'actual_input': {
            'source_monthly_files': 300, 'source_factor_columns': 272,
            'source_rows': 2454420, 'source_bytes': 6515013371, 'source_days': 6295,
            'conditional_valid_prediction_rows': 136597,
            'HAR_columns': 816, 'implementation_bindings_accepted': '71/71',
            'raw_SPY_cache_bridge': '32601/32602 nominal windows;1259 raw-close days;5096 native OHLCV overlaps exact',
            'four_delayed_first_prices': 'Single scheduled attempt no-fill/expire; no price backdating',
            'PIT_original15min_legs_verified_venue_fill_settlement_certified': False,
        },
        'gates_actually_passed_before_calibration': {
            'scientific_plan': True, 'conditional_source_market_features': True,
            'independent_implementation': True, 'direction': True, 'knowledge': True,
            'native_pre_backtest': True, 'native_hash_calls': 153,
            'native_hash_bytes': 10668285053,
            'fullstudy_resource_gate': False, 'native_final_financial_result_gate': False,
        },
        'fixed_complete_scope_not_reduced': {
            'pipelines': 20, 'diagnostic_rule_cost_lag_books': 800,
            'funded20k_accounts': 100, 'matched4k_host_books': 40,
            'four_exact_rules': ['Sign', 'Positive', 'SSign', 'SPositive'],
            'source_transformations': ['IDX', 'SUM', 'INV'],
            'HGB_capacities': [50, 150, 350], 'cost_bps': [0, 1, 5, 20, 40],
        },
        'actual_calibration': {
            'year': 2019, 'view': 'IDX', 'depth': 6, 'learning_rate': 0.1,
            'n_train': 96451, 'n_validation': 24113,
            'warm_start_chains': 1, 'unique_logical_configs_started': 3,
            'completed_persisted_prefixes': 2,
            'completed_trees': [50, 150], 'checkpoints': decision['checkpoints'],
            'final350_started': True, 'final350_completed': False,
            'unpersisted_additional350_training_exposure': 'Unknown; retained as nonzero possible exposure',
            'job_exit_status': 137, 'exact_kernel_stop_cause': 'Unresolved',
            'inclusive_CPU': 452.21, 'nominal_CPU_slot': 450, 'inclusive_excess_CPU': 2.21,
            'max_RSS_KiB': 925484, 'RSS_le900MiB_claim': False,
            'metrics_read': False, 'active_training_processes': 0,
        },
        'frozen_resource_gate': {
            'formula': review['projection_verification']['formula'],
            'actual_refit_train_n_ratios': decision['full_refit_train_n_ratios'],
            'remaining_equivalents': 20.07855802428176,
            'completed150_intrinsic_CPU_used_as_same_trajectory_gate_bound': 314.817376,
            'conservative_gate_bound': 11416.16606483516, 'original_cap': CAP,
            'gate_admits_unchanged_full_package': False,
            'actual350_measurement': False, 'all_implementations_runtime_lower_bound': False,
            'explanation': 'Same unchanged cumulative trajectory and frozen conservative formula only. Not a measurement of complete350 or proof actual complete runtime must exceed this value.',
        },
        'capital_and_returns': {
            'strategy_account_runs': 0, 'complete_costed_packages': 0,
            'net_absolute_return_USD': None, 'CAGR': None, 'net_account_Sharpe': None,
            'beta': None, 'portfolio_marginal_contribution': None,
            'performance_status': 'N/A; no forecasts, validation/test scores, account returns or selection evaluated',
        },
        'resources': {
            'economic_ledger': binding(P / 'economic-resource-ledger.json'),
            'economic_cap_CPU': CAP, 'economic_cumulative_conservative_CPU': total,
            'economic_remaining_CPU': remaining, 'preparation_cumulative_CPU': prep['cumulative_conservative_CPU'],
            'preparation_remaining_CPU': prep['remaining_of2300'],
            'cumulative_HF_known_public_source_units': 359,
            'continuation_known_public_source_units': 327,
            'continuation_direct_source_request_units': 321,
            'continuation_known_direct_source_bytes': 6494626426,
            'raw_web_bytes_unknown_preserved': True,
            'global_market_used_units': 24, 'global_market_used_bytes': 5434959,
            'global_market_remaining_units': 0, 'global_market_remaining_bytes': 11342257,
            'closeout_source_market_cloud_paid_orders': 0,
        },
        'next_material_decision': {
            'recommended_first_candidate': 'Bounded semantics-preserving computation-efficiency investigation and fresh complete-cost projection',
            'concrete_candidate': 'Repeated warm-start training binning/raw prediction; reuse of identical fold/view binning or bounded-memory layout',
            'required_parity': ['input', 'scaler', 'bin thresholds', 'random state', 'trees', 'predictions', 'validation and choice rules'],
            'alternative': 'Explicit additional complete economic resource allocation, or defer for opportunity cost',
            'no_new_fit_budget_or_model_change_authorized': True,
            'no_ordinary_cheap_path_proven_to_fit_remainder': True,
            'preserve': 'Full20/800/100/40; original candidates/costs/clock/data/model depth; all failed/partial/unknown costs and checkpoints',
        },
        'workflow_pass': False, 'research_pass': False, 'ml_contribution_pass': False,
        'paper_ready_pass': False, 'mechanism_refuted': False, 'promotion_eligible': False,
        'source_input_native_pass_is_not_Alpha': True, 'owner_released_for_material_resource_decision': True,
        'finish_route': 'One native final; no explicit duplicate Root notification.',
    }
    write(P / 'continuation-economic-resource-result.json', result)
    report = f'''HF 本轮完整容量决定已获独立接受；暂停当前未准入的完整经济运行，等待具体资源分配决定。收益、CAGR、账户净 Sharpe、beta及组合美元贡献均为 N/A，research_pass／paper_ready_pass仍为 false。未否定模型或因子机制。

已实际取得并核验作者300个月、272因子、2,454,420行、6,515,013,371字节的当前版本原始输入；形成136,597个条件有效预测位置及816列HAR。原生方向、knowledge、pre-backtest与完整71/71实施绑定通过。SPY使用真实raw缓存桥及行动表，保留缺窗、四次延迟首价no-fill、现金代理和BIL碎股限制。当前版本、分钟净零收益变换、条件历史时钟与FF→SPY应用的区别均保留；没有原15分钟腿收益、PIT、真实fill或实际结算证明。

按批准的固定2019容量校准实际训练，一条warm-start链完成50／150树两个持久化prefix；350树已启动但未完成，未持久化的额外训练暴露未知。训练96,451行、验证24,113行，未读取验证、test、预测或策略收益。450秒slot实际inclusive452.21CPU秒，超出的2.21完整入账；exit137的精确kernel原因未证实。峰值RSS925,484KiB高于900MiB，不能以wrapper设置声称RSS合规。

完成150树的固有累计CPU为314.817376秒。同一未改变轨迹下，350树累计成本不能低于已经完成150树的成本；代入原冻结资源公式及四fold实际比例，保守准入门值的下界为11,416.166065秒，超过原7,006.69秒上限。此数不是350树实测，也不是所有实现或完整研究真实耗时的下界。未生成完整350投影；不删减20条模型管线、800诊断账、100资金账和40个匹配host账来制造完整结果。

作者已结束作业实测453.67CPU秒，独立容量审查实测1.22加非零读写／封包保守3，合4.22；本次收尾实测{closeout_cpu:.2f}加非零读写／最终封包保守2。经济累计保守{total:.2f}／7,006.69CPU秒，余{remaining:.2f}；余额不是完整运行或重试准入。准备累计2,281.64992391／2,300，余18.35007609；旧500预约与旧失败／未知／163.31+30均保留、不借用、不清零。未新增来源、市场请求、付费、云、订单或拟合。

最具体的下一候选是同语义效率改进：当前HGB每次warm fit重新分箱、重建raw prediction，可能复用相同fold/view的分箱或改善有界内存布局。但尚无证明可在余额内完成全包；需要输入／scaler／分箱阈值／随机状态／树／预测／选择规则parity与fresh完整成本投影，并由实际资源决定准入。另一选择是明确增加完整经济预算；机会成本不值得则暂缓此条件应用。未授权新fit或数学变更，原检查点和全部失败成本保留。

本包为完整重大资源决定，不是成本后市场收益结果。已清除旧运行状态，原source/market/M1封包及旧结果原字节保留；通过单次native final返回，不另通知Root。
'''
    (P / 'continuation-economic-resource-result.md').write_text(report)
    (D / 'decision-record.md').write_text(
        'Path: conditional_hf_factor_method.\n'
        'Decision: Stop the unadmitted complete20/800/100/40 run pending a material resource allocation decision.\n'
        'Reason: Actual input, independent implementation, direction, knowledge and pre-backtest gates passed; fixed2019 calibration completed50/150 and stopped before350 with exit137/inclusive452.21CPU. The same-trajectory frozen conservative gate bound11416.16606483516 exceeds7006.69; it is not measured350 or an all-implementations runtime lower bound. Independent resource decision accepted; no financial metrics read.\n'
        'Next iteration suggestion: Explicitly admit bounded semantics-preserving binning/runtime efficiency with full parity and fresh full-cost projection, allocate sufficient complete economics, or defer. Preserve all costs/checkpoints and full depth. No new fit is authorized.\n'
    )
    state = read(P / 'current-state.json')
    historical_keys = [
        'completed_economic_job_inclusive_CPU', 'current_economic_CPU_nonzero_running_is_not_reset',
        'economic_original7006_69_remaining_before_running', 'registered_capacity_calibration_in_progress',
        'continuation_preparation_CPU_cap', 'continuation_preparation_known_CPU_coreseconds',
        'continuation_preparation_known_plus_allowance', 'continuation_preparation_conservative_CPU',
        'continuation_preparation_resources_current', 'continuation_preparation_resources',
        'source_preparation_conservative_cpu', 'owner_remaining_after_peer_reservation',
        'peer_final_guard_upper_CPU_reserved', 'residual_peer_guard_upper_CPU',
        'HF_cumulative_source_units', 'market_capture_complete', 'scientific_open_points',
    ]
    state['superseded_historical_fields_at_capacity_closeout'] = {
        'as_of_utc': stamp, 'meaning': 'Historical observations before completed137 stop; not current running jobs, ready status or remaining budget.',
        'fields': {key: state.pop(key) for key in historical_keys if key in state},
        'exact_pre_closeout_state_archive': binding(A / 'current-state-before-closeout.json'),
    }
    state.update({
        'updated_at_utc': stamp, 'status': 'complete_independently_accepted_major_economic_resource_decision',
        'active_owner': None, 'owner_released': True, 'actual_process': None,
        'actual_exec_session': None, 'current_process_pid': None, 'actual_process_exit_status': 137,
        'current_process_exit_status': 137, 'registered_capacity_calibration_in_progress': False,
        'source_preparation_running': False, 'source_feature_preparation_running': False,
        'new_economic_runs': 1,
        'new_economic_runs_identity': 'One actual capacity-calibration training job; one failed pre-fit launcher separate; account studies0',
        'new_model_fits': 2, 'new_model_fits_identity': 'Two persisted logical prefixes50/150 of one warm-start chain, not two independent full fits',
        'registered_unique_logical_configs_started': 3, 'calibration350_completed': False,
        'current_training_processes': 0, 'completed_economic_job_inclusive_CPU': total,
        'calibrate_inflight_json_historical_receipt_only': True,
        'completed_economic_job_inclusive_CPU_identity': 'All current economic measured jobs plus explicit nonzero unknown allowances in ledger',
        'new_economic_CPU_coreseconds': total, 'economic_original7006_69_remaining': remaining,
        'economic_execution_admitted': False, 'economic_admission_scope': 'Historical fixed calibration is closed; no further training or complete study admitted',
        'resource_ready_for_full_input': True, 'full_study_resource_ready': False,
        'input_ready': True, 'implementation_ready': True, 'native_gate_ready': True,
        'knowledge_gate_ready': True, 'market_input_scope_complete': True,
        'original_15page_SPY_capture_complete': False,
        'source_preparation_current_ledger': binding(P / 'preparation-resource-continuation-11.json'),
        'continuation_preparation_resources_current': str((P / 'preparation-resource-continuation-11.json').relative_to(ROOT)),
        'combined_preparation_CPU_cap': 2300, 'combined_preparation_current_conservative_CPU': prep['cumulative_conservative_CPU'],
        'combined_preparation_remaining_CPU': prep['remaining_of2300'],
        'HF_cumulative_source_units': 359, 'HF_cumulative_source_units_identity': 'Known327 continuation units plus original32; raw web response byte unknowns retained',
        'independent_economic_capacity_review': binding(P / 'independent-economic-capacity-decision-review.json'),
        'economic_resource_ledger': binding(P / 'economic-resource-ledger.json'),
        'continuation_economic_resource_result': binding(P / 'continuation-economic-resource-result.json'),
        'continuation_economic_resource_final_manifest_path': str((P / 'continuation-economic-resource-final-manifest.json').relative_to(ROOT)),
        'continuation_economic_resource_completion_receipt_path': str((P / 'continuation-economic-resource-completion-receipt.json').relative_to(ROOT)),
        'validation_test_or_economic_metrics_read': False, 'costed_account_performance': None,
        'complete_costed_HF_result': False, 'research_pass': False, 'paper_ready_pass': False,
        'next_action': 'Root material allocation choice: bounded same-semantics efficiency/parity and fresh complete-cost projection, sufficient complete economic budget, or defer. No further fit/resource retry/partial-depth substitute authorized.',
        'finish_route': 'Single native final now; no separate Root message.',
    })
    write(P / 'current-state.json', state)
    write(P / 'continuation-economic-resource-state-at-finish.json', state)
    # The pre-calibration decision record remains in the immutable archive;
    # current native report changes only its closeout decision.
    decision_path = str((D / 'decision-record.md').relative_to(ROOT))
    script_path = str(Path(__file__).relative_to(ROOT))
    index['files'] = [item for item in index['files']
                      if item['path'] not in [decision_path, script_path]]
    index['files'].append(binding(Path(__file__)))
    index['build_code_at_measured_launch'] = binding(
        A / 'seal_economic_resource_closeout-at-measured-build.py'
    )
    index['immutable_archives'].append(index['build_code_at_measured_launch'])
    index['closeout_index_note'] = 'Current native decision record is sealed in finalmanifest; pre-calibration bytes remain archived. Current seal helper has only this index-binding/status closeout correction after the measured build, whose exact helper bytes are archived.'
    write(P / 'economic-closeout-evidence-index.json', index)
    files = index['files'] + index['immutable_archives']
    extras = [
        P / 'economic-closeout-evidence-index.json', P / 'economic-resource-ledger.json',
        P / 'continuation-economic-resource-result.json', P / 'continuation-economic-resource-result.md',
        P / 'continuation-economic-resource-state-at-finish.json',
        A / 'current-state-before-closeout.json', A / 'native-decision-record-before-closeout.md',
        E / 'capacity-closeout-resource-001.txt', E / 'capacity-closeout-launch.log',
        D / 'decision-record.md',
    ]
    files.extend(binding(f) for f in extras)
    unique = {item['path']: item for item in files}
    for item in unique.values():
        verify(item)
    manifest = {
        'schema_version': 1, 'task_id': TASK, 'author': OWNER, 'reviewer': PEER, 'as_of_utc': stamp,
        'scope': 'Complete independently accepted major economic capacity/resource decision; not costed market performance',
        'files': list(unique.values()), 'file_count': len(unique),
        'result': binding(P / 'continuation-economic-resource-result.json'),
        'independent_resource_acceptance': binding(P / 'independent-economic-capacity-decision-review.json'),
        'economic_ledger': binding(P / 'economic-resource-ledger.json'),
        'source300_market361_M1_71_guards_reused_without_large_hash': True,
        'small_direct_file_guards_freshly_verified': True,
        'old_packets_original_bytes_preserved': True, 'mutable_original_records_also_archived': True,
        'full_account_research_complete': False, 'research_pass': False, 'paper_ready_pass': False,
    }
    write(P / 'continuation-economic-resource-final-manifest.json', manifest)
    write(P / 'continuation-economic-resource-completion-receipt.json', {
        'schema_version': 1, 'task_id': TASK, 'owner': OWNER, 'recorded_at_utc': stamp,
        'scope': 'Independently accepted genuine economic capacity decision; no strategy profitability claim',
        'result': manifest['result'], 'final_manifest': binding(P / 'continuation-economic-resource-final-manifest.json'),
        'state': binding(P / 'continuation-economic-resource-state-at-finish.json'),
        'independent_resource_acceptance': manifest['independent_resource_acceptance'],
        'economic_ledger': manifest['economic_ledger'],
        'economic_cumulative_CPU': total, 'remaining_economic_CPU': remaining,
        'owner_active_processes': 0, 'owner_released_for_material_resource_decision': True,
        'finish_route': 'Single native final, no explicit duplicate Root notification',
        'research_pass': False, 'paper_ready_pass': False,
        'closeout_checks': {'small_bindings_and_checkpoint_SHA': 'pass', 'all_old_immutable_packets': 'pass',
                            'no_large_source_feature_rehash': True, 'no_fit_inference_account_evaluation': True},
    })
    print(json.dumps({'status': 'sealed', 'file_count': len(unique), 'economic_CPU': total,
                      'remaining_CPU': remaining, 'manifest': binding(P / 'continuation-economic-resource-final-manifest.json')}))


if __name__ == '__main__':
    os.sched_setaffinity(0, {0})
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    {'build': build, 'seal': seal}[sys.argv[1]]()
