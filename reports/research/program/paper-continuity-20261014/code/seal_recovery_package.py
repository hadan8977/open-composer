"""Seal the actual isolated maintenance result; no production integration or self approval."""
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]


def binding(path):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest}


def main():
    plan_path = WT / 'reports/paper/book/quant1/plans/2026-10-14.json'
    plan = json.loads(plan_path.read_text())
    assert plan['status'] == 'ok' and not plan['blocked_by']
    assert all(c['passed'] for c in plan['checks']) and plan['dry_run']
    fresh = json.loads((P / 'actual-current-native-freshness.json').read_text())
    assert fresh['fresh'] and not fresh['lagging_stages']
    parity = json.loads((P / 'actual-target-parity-and-held-coverage.json').read_text())
    assert parity['max_abs_weight_difference'] == 0
    assert not parity['held_price_coverage']['missing_names']
    baseline = json.loads((P / 'isolation-baseline-manifest.json').read_text())
    unchanged = []
    for old in baseline['actual_shared_baseline_files']:
        actual = binding(ROOT / old['path'])
        assert actual['sha256'] == old['sha256'], old['path']
        unchanged.append(actual)
    (P / 'shared-production-isolation-verification.json').write_text(json.dumps({'files': unchanged, 'all_baseline_shared_bytes_unchanged': True, 'Root_owned_owner_digest_and_lifecycle_not_modified_by_author': True}, indent=2) + '\n')
    code_paths = subprocess.check_output(['git', 'diff', '--name-only', '4ae010a..HEAD'], cwd=WT, text=True).splitlines()
    code = [binding(WT / name) for name in code_paths]
    data_paths = [WT / f'data/features/{name}/2026.parquet' for name in ['daily', 'daily_broad', 'sec_fundamentals_daily', 'insider_broad', 'short_volume_broad', 'short_interest', 'news_attention']]
    data_paths += [WT / 'data/features/nsi/nsi.parquet', WT / 'data/features/sec_fundamentals/facts.parquet', WT / 'data/features/news_packets/2026.parquet']
    data_paths += [WT / f'data/live/equity_book/{name}' for name in ['panel/2026.parquet', 'panel/_calendar.parquet', 'panel/_hygiene.parquet', 'prices/2026.parquet', 'etf_daily.parquet', 'signals/2026.parquet', 'signals/_meta_2026.json', 'risk/meta.json', 'alpha/book_v1/themes_2026.parquet', 'alpha/book_v1/formation_ic.parquet', 'alpha/book_v1/formation_ic_merge.json', '_freshness.json']]
    data_paths += list((WT / 'data/live/equity_book/risk').glob('*_2026.parquet'))
    data_paths += list((WT / 'data/features/_forward_v1/latest').glob('*.json'))
    data = [binding(path) for path in data_paths if path.exists()]
    (P / 'reviewable-data-installation-manifest.json').write_text(json.dumps({'entries': [{**x, 'proposed_shared_relative_path': str(Path(x['path']).relative_to(WT))} for x in data], 'production_copy_requires_Root_independent_acceptance': True, 'book_targets_plans_not_to_be_copied_as_executed_receipts': True, 'source_raw_normalized_paths_retained_separately': True}, indent=2) + '\n')
    nav = json.loads((P / 'account-snapshot-current.json').read_text())
    resource = json.loads((P / 'resource-ledger.json').read_text())
    result = {'task_id': 'PAPER-CONTINUITY-20261014', 'owner': 'f9add224-744b-471c-b812-c43cc179fa38', 'status': 'complete_isolated_recovery_and_current_readonly_acceptance_package', 'created_at_UTC': datetime.now(UTC).isoformat(), 'branch': 'fix/paper-continuity-20261014', 'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=WT, text=True).strip(), 'worktree': str(WT), 'production_integration_accepted': False, 'broker_orders_submitted_canceled_or_backfilled': 0, 'intraday_activated': False, 'ETF_configuration_changed': False, 'current_native_freshness': fresh, 'current_target': {'decision_date': '2026-10-13', 'execution_date': '2026-10-14', 'names': 1702, 'active_account_plan': 'quant1', 'quant2_target_only_not_activated': True}, 'actual_readonly_plan': {'status': plan['status'], 'checks_passed': len(plan['checks']), 'checks_total': len(plan['checks']), 'potential_orders': len(plan['orders']), 'etb_rejections_retained': len(plan['etb_rejections']), 'created_at_UTC': plan['created_at_utc'], 'equity_live_at_plan': plan['equity_live']}, 'account_observed': {'NAV': nav['account']['equity'], 'asof': nav['clock']['timestamp'], 'positions': nav['position_count'], 'strategy_current_day_attribution': None}, 'historical_target_parity': parity, 'source_calls_current_maintenance_only': 620, 'source_wire_bytes_total': None, 'new_paid_USD': 0, 'resources': {'cap_CPU_seconds': 24000, 'charged_or_reserved_CPU_seconds': resource['charged_or_reserved_CPU_seconds'], 'measured_CPU_seconds': resource['measured_CPU_seconds'], 'all_old_failures_unknown_and_reserves_retained': True, 'Hadan_scientific_compute_started': False}, 'limits': ['No claim of deployed/running recovery before Root integration and scheduled receipts.', 'Same original strategy/factor/risk/sizing/cost formulas; current-vintage data epoch does not certify historical PIT/security lifetime or total-return cash rights.', 'Current NAV is a broker mark, with no invented missing-day strategy P/L or fills.', 'Old published prefixes/69 unequal duplicate occurrences and failed whole-panel checks remain evidence; a versioned prefix pass is not the old whole-panel predicate.', 'Eight real current not-shortable rejections and ordinary minimum-notional drift remain in the actual plan.', 'Generic ETF legacy sync warning comes from two canceled zero-filled multileg parent objects; verified sleeve fills continue, no full broker-history reconstruction.'], 'next_authority_action': 'Root independently review exact patch/data/source and activation/rollback instructions, then integrate accepted files. Verify only normal scheduled current-day cycles after integration; no historical catch-up/manual duplicate orders.'}
    (P / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    proof_names = ['task.json', 'resource-ledger.json', 'result.json', 'isolated-recovery.patch', 'forward-config-candidate.json', 'current-forward-heads-bootstrap.json', 'reviewable-data-installation-manifest.json', 'shared-production-isolation-verification.json', 'account-snapshot-current.json', 'actual-target-parity-and-held-coverage.json', 'actual-current-native-freshness.json', 'actual-current-native-readonly-plan-result.json', 'legacy-sync-boundary.json', 'legacy-sync-readonly.json', 'hygiene-exact-fields-and-holdings.json', 'readonly-control-exact-copy.json', 'native-formation-ic-merge.json', 'final-focused-tests-log.txt', 'final-ruff-log.txt', 'plan-refresh-safety-tests-log.txt', 'current-source-request-manifest.json', 'current-source-continuation-request-manifest.json', 'current-insider-request-manifest.json', 'current-insider-continuation-request-manifest.json', 'current-source-intake/ledger.json', 'current-source-continuation/ledger.json', 'current-companyfacts-bulk/ledger.json', 'current-insider-tail-recovery/ledger.json', 'current-insider-tail-continuation/ledger.json', 'own-transport-archive-verification.json', 'released-reconstructible-short-interest-copy.json']
    proofs = [binding(P / name) for name in proof_names]
    proofs += [binding(path) for path in sorted(P.glob('compose-current-*.json'))]
    proofs += [binding(WT / 'reports/paper/book/quant1/targets/2026-10-13.json'), binding(plan_path)]
    manifest = {'schema_version': 1, 'task_id': result['task_id'], 'author': result['owner'], 'author_self_approval': False, 'code': code, 'data': data, 'proofs': proofs, 'production_integration': False}
    (P / 'result-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print({'result_manifest': binding(P / 'result-manifest.json'), 'code_bindings': len(code), 'data_bindings': len(data), 'proof_bindings': len(proofs), 'production_integration': False}, flush=True)


if __name__ == '__main__':
    main()
