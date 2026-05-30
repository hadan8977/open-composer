# Paper Strategy Readiness: nasdaq_tqqq_fixed_etf_router_daily_iter9

- Generated at: `2026-05-30T16:28:26.506791+00:00`
- Strategy path: `strategy_specs/drafts/nasdaq_tqqq_fixed_etf_router_daily_iter9.yaml`
- Status: `blocked`
- Ready: `no`
- Execution substate: `blocked`
- Gate taxonomy: workflow_pass, research_pass, llm_contribution_pass, paper_ready_pass.
- Gate summary: `{'workflow_pass': False, 'research_pass': True, 'llm_contribution_pass': None, 'paper_ready_pass': False, 'execution_substate': 'blocked', 'blocked_checks': ['lifecycle', 'execution', 'alpaca_env', 'capability_report'], 'warning_checks': ['router_order_authorization']}`
- Safety note: paper readiness is a control gate for Alpaca Paper only, not live trading.

## Checks

### lifecycle

- Status: `blocked`
- Message: Paper automation requires lifecycle=active.
- Details: `{'lifecycle': 'draft'}`
- Suggested actions:
  - `uv run oc strategy approve nasdaq_tqqq_fixed_etf_router_daily_iter9`
  - `uv run oc strategy activate nasdaq_tqqq_fixed_etf_router_daily_iter9 --paper-auto --allow-paper-auto --data-source alpaca --enforce-paper-readiness`

### execution

- Status: `blocked`
- Message: execution.mode must be paper_auto; execution.broker must be alpaca_paper
- Details: `{'mode': 'manual_signal', 'broker': 'none', 'backend': 'nautilus_trader'}`
- Suggested actions:
  - `uv run oc strategy activate nasdaq_tqqq_fixed_etf_router_daily_iter9 --paper-auto --allow-paper-auto --data-source alpaca --enforce-paper-readiness`

### data_source

- Status: `ok`
- Message: Paper automation uses a live/cache market data source.
- Details: `{'source': 'alpaca', 'symbol': 'QQQ', 'timeframe': 'daily', 'data_mode': 'paper_ready'}`

### universe_audit

- Status: `ok`
- Message: Universe audit passed.
- Details: `{'status': 'ok', 'json_path': 'reports/research/nasdaq_tqqq_fixed_etf_router_daily_iter9-universe-audit.json', 'report_path': 'reports/research/nasdaq_tqqq_fixed_etf_router_daily_iter9-universe-audit.md', 'findings': [{'code': 'fixed_universe_documented', 'severity': 'ok', 'message': 'Universe is documented as a fixed tradable-instrument set; historical index-membership PIT evidence is not required.', 'evidence': {'symbols': ['BIL', 'GLD', 'IGV', 'PSQ', 'QLD', 'QQQ', 'ROM', 'SMH', 'SOXL', 'SOXS', 'SOXX', 'SPY', 'SQQQ', 'TECL', 'TECS', 'TQQQ', 'USD', 'XLK'], 'metadata': {'point_in_time_membership': True, 'explicit_fixed_universe': True, 'selection_timestamp': '2026-05-30T00:00:00Z', 'delisting_policy': 'Fixed ETF instrument set; no current equity-index membership backfill is used.'}}}]}`

### alpaca_env

- Status: `blocked`
- Message: Paper readiness currently targets broker=alpaca_paper.
- Details: `{'broker': 'none'}`
- Suggested actions:
  - `uv run oc strategy activate nasdaq_tqqq_fixed_etf_router_daily_iter9 --paper-auto --allow-paper-auto --data-source alpaca --enforce-paper-readiness`

### kill_switch

- Status: `ok`
- Message: Paper kill switch is clear.

### account_snapshot

- Status: `ok`
- Message: Paper account snapshot is available.
- Details: `{'generated_at': '2026-05-26T18:01:08.927968+00:00', 'equity': 1066810.5, 'cash': 235472.62, 'buying_power': 1302283.12}`

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
- Message: All 11 harness artifacts present for domains ['daily_open_execution', 'leveraged_etf', 'router_strategy'].
- Details: `{'risk_domains': ['daily_open_execution', 'leveraged_etf', 'router_strategy'], 'required_artifacts': ['execution_policy', 'execution_reality_report', 'gap_stress_report', 'leveraged_etf_risk_note', 'router_cost_stress', 'router_data_evidence', 'router_execution_observation', 'router_rebalance_intents', 'router_target_weights', 'router_validation', 'source_cards']}`

### router_order_authorization

- Status: `warning`
- Message: Router order authorization artifact is missing. Router remains observation_only.
- Details: `{'path': 'reports/harness/paper/nasdaq_tqqq_fixed_etf_router_daily_iter9-router-order-authorization.json', 'portfolio_mode': 'hybrid_adaptive_router'}`
- Suggested actions:
  - `Write reports/harness/paper/nasdaq_tqqq_fixed_etf_router_daily_iter9-router-order-authorization.json after PIT, promotion, harness verify, and paper safety review pass.`

### capability_report

- Status: `blocked`
- Message: strategy must be promoted to lifecycle=active; execution.mode must be paper_auto; execution.broker must be alpaca_paper
- Details: `{'capability': 'alpaca_paper_execution', 'status': 'blocked'}`
- Suggested actions:
  - `uv run oc spec capabilities /root/codex-test/open-composer/strategy_specs/drafts/nasdaq_tqqq_fixed_etf_router_daily_iter9.yaml`
