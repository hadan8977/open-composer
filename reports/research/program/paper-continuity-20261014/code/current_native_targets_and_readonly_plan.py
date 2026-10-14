"""Actual native target and paper-client plan only. Never submit or backfill orders."""
import importlib.util
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT))
from open_composer.cli import _load_env

saved = os.environ.get('OPEN_COMPOSER_ROOT')
os.environ['OPEN_COMPOSER_ROOT'] = str(ROOT)
try:
    _load_env()
finally:
    os.environ['OPEN_COMPOSER_ROOT'] = str(WT)
os.environ['OC_EQUITY_BOOK_DIR'] = str(WT / 'data/live/equity_book')
spec = importlib.util.spec_from_file_location('current_daily', WT / 'scripts/run_book_v12_daily.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
m.setup_logging(P / 'current-native-readonly-plan-detail.log')
m.oc_command = lambda: [str(ROOT / '.venv/bin/python'), '-c', 'from open_composer.cli import app; app()']
targets = m.run_targets(WT, WT / 'data/live/equity_book', date(2026, 10, 13), None)
plan = None
if targets == 0:
    plan = m.run_plans(WT, date(2026, 10, 13), submit=False, accounts=('quant1',), execution_date=date(2026, 10, 14))
r = {'native_targets_exit': targets, 'readonly_plan_exit': plan, 'decision_date': '2026-10-13', 'execution_date': '2026-10-14', 'account_alias': 'quant1', 'submit': False, 'cancel': False, 'missed_historical_orders_generated': 0, 'production_writes': 0, 'strategy_parameters_changed': False, 'model_tranche_target_is_not_a_claim_of_actual_historical_fills': True}
(P / 'actual-current-native-readonly-plan-result.json').write_text(json.dumps(r, indent=2) + '\n')
print(json.dumps(r), flush=True)
raise SystemExit(targets if targets else plan)
