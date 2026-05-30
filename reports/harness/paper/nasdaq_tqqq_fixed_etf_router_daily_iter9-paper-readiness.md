# Paper Strategy Readiness: nasdaq_tqqq_fixed_etf_router_daily_iter9

- Generated at: `2026-05-30T19:57:16.230953+00:00`
- Strategy path: `strategy_specs/active/nasdaq_tqqq_fixed_etf_router_daily_iter9.yaml`
- Status: `ok`
- Ready: `yes`
- Execution substate: `order_authorized`
- Gate taxonomy: workflow_pass, research_pass, llm_contribution_pass, paper_ready_pass.
- Gate summary: `{'workflow_pass': True, 'research_pass': True, 'llm_contribution_pass': None, 'paper_ready_pass': True, 'execution_substate': 'order_authorized', 'blocked_checks': [], 'warning_checks': []}`
- Safety note: paper readiness is a control gate for Alpaca Paper only, not live trading.

## Checks

### lifecycle

- Status: `ok`
- Message: Strategy is active.
- Details: `{'lifecycle': 'active'}`

### execution

- Status: `ok`
- Message: Execution mode, broker, and backend are paper-ready.
- Details: `{'mode': 'paper_auto', 'broker': 'alpaca_paper', 'backend': 'nautilus_trader'}`

### data_source

- Status: `ok`
- Message: Paper automation uses a live/cache market data source.
- Details: `{'source': 'alpaca', 'symbol': 'QQQ', 'timeframe': 'daily', 'data_mode': 'paper_ready'}`

### universe_audit

- Status: `ok`
- Message: Universe audit passed.
- Details: `{'status': 'ok', 'json_path': 'reports/research/nasdaq_tqqq_fixed_etf_router_daily_iter9-universe-audit.json', 'report_path': 'reports/research/nasdaq_tqqq_fixed_etf_router_daily_iter9-universe-audit.md', 'findings': [{'code': 'fixed_universe_documented', 'severity': 'ok', 'message': 'Universe is documented as a fixed tradable-instrument set; historical index-membership PIT evidence is not required.', 'evidence': {'symbols': ['BIL', 'GLD', 'IGV', 'PSQ', 'QLD', 'QQQ', 'ROM', 'SMH', 'SOXL', 'SOXS', 'SOXX', 'SPY', 'SQQQ', 'TECL', 'TECS', 'TQQQ', 'USD', 'XLK'], 'metadata': {'point_in_time_membership': True, 'explicit_fixed_universe': True, 'selection_timestamp': '2026-05-30T00:00:00Z', 'delisting_policy': 'Fixed ETF instrument set; no current equity-index membership backfill is used.'}}}]}`

### alpaca_env

- Status: `ok`
- Message: Alpaca Paper environment is configured.
- Details: `{'paper_enabled': True, 'base_url': 'https://paper-api.alpaca.markets/v2'}`

### kill_switch

- Status: `ok`
- Message: Paper kill switch is clear.

### account_snapshot

- Status: `ok`
- Message: Paper account snapshot is available.
- Details: `{'generated_at': '2026-05-30T19:50:40.716856+00:00', 'equity': 1100944.22, 'cash': 235472.62, 'buying_power': 1336416.84}`

### nautilus_backend

- Status: `ok`
- Message: NautilusTrader package is available.
- Details: `{'backend': 'nautilus_trader', 'nautilus_installed': True}`

### portfolio_routing

- Status: `ok`
- Message: hybrid_adaptive_router portfolio routing is declared inside StrategySpec.
- Details: `{'mode': 'hybrid_adaptive_router', 'max_symbols_per_day': 1, 'gross_exposure_limit': 0.8, 'max_symbol_weight': 0.8, 'same_day_flatten': False, 'duplicate_signal_policy': 'stable_signal_id', 'selected_route_label': 'beta_override:baseiter2_lb20_min5_adv0_sma200_exTQQQ_mdd20p6_ov120t105_g0.55_bearGLDlb60min0sma50w0.8_tqqq_cycle', 'universe': ['QQQ', 'TQQQ', 'SQQQ', 'QLD', 'PSQ', 'SMH', 'SOXL', 'SOXS', 'TECL', 'TECS', 'ROM', 'USD', 'SPY', 'XLK', 'SOXX', 'IGV', 'GLD', 'BIL']}`

### portfolio_risk

- Status: `ok`
- Message: hybrid_adaptive_router gross exposure and concentration limits are explicit.
- Details: `{'universe': ['QQQ', 'TQQQ', 'SQQQ', 'QLD', 'PSQ', 'SMH', 'SOXL', 'SOXS', 'TECL', 'TECS', 'ROM', 'USD', 'SPY', 'XLK', 'SOXX', 'IGV', 'GLD', 'BIL'], 'mode': 'hybrid_adaptive_router', 'gross_exposure_limit_pct': 80.0, 'single_name_weight_limit_pct': 80.0, 'max_symbols_per_day': 1, 'same_day_flatten': False, 'duplicate_signal_policy': 'stable_signal_id', 'sector_concentration': 'bounded_by_max_symbols_and_weight; sector map not registered', 'borrow_short_caveat': 'long-only paper routing; borrow is out of scope'}`

### feature_packets

- Status: `ok`
- Message: Feature packet bindings are point-in-time complete.
- Details: `{'inspected': []}`

### promotion_report

- Status: `ok`
- Message: Promotion report is present and ready for paper review.
- Details: `{'path': '/root/codex-test/open-composer/reports/research/nasdaq_tqqq_fixed_etf_router_daily_iter9-promotion.json', 'status': 'ok', 'ready': True, 'check_count': 13, 'gate_summary': {'benchmark_family_complete': True, 'blocked_checks': [], 'llm_contribution_pass': None, 'paper_ready_pass': True, 'research_pass': True, 'warning_checks': [], 'workflow_pass': True}, 'benchmark_family_complete': True}`

### harness_artifacts

- Status: `ok`
- Message: All 12 harness artifacts present for domains ['daily_open_execution', 'leveraged_etf', 'paper_auto', 'broker_specific', 'router_strategy'].
- Details: `{'risk_domains': ['daily_open_execution', 'leveraged_etf', 'paper_auto', 'broker_specific', 'router_strategy'], 'required_artifacts': ['execution_policy', 'execution_reality_report', 'gap_stress_report', 'leveraged_etf_risk_note', 'paper_safety_review', 'router_cost_stress', 'router_data_evidence', 'router_execution_observation', 'router_rebalance_intents', 'router_target_weights', 'router_validation', 'source_cards']}`

### router_order_authorization

- Status: `ok`
- Message: Router order authorization is valid.
- Details: `{'path': 'reports/harness/paper/nasdaq_tqqq_fixed_etf_router_daily_iter9-router-order-authorization.json', 'execution_policy_id': 'loo_limit_nasdaq_tqqq_fixed_etf_router_daily_iter9_v1', 'target_weights_path': 'reports/execution/nasdaq_tqqq_fixed_etf_router_daily_iter9-target-weights.json', 'rebalance_intents_path': 'reports/execution/nasdaq_tqqq_fixed_etf_router_daily_iter9-rebalance-intents.json', 'paper_safety_review_path': 'reports/harness/paper/nasdaq_tqqq_fixed_etf_router_daily_iter9-paper-safety-review.json'}`

### capability_report

- Status: `ok`
- Message: active paper_auto Alpaca strategy can submit paper orders with explicit allow flag
- Details: `{'capability': 'alpaca_paper_execution', 'status': 'supported'}`
- Suggested actions:
  - `uv run oc spec capabilities /root/codex-test/open-composer/strategy_specs/active/nasdaq_tqqq_fixed_etf_router_daily_iter9.yaml`
