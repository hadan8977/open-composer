# Paper Strategy Readiness: us_core_satellite_momentum_r7

- Generated at: `2026-07-19T09:29:14.373955+00:00`
- Strategy path: `strategy_specs/drafts/us_core_satellite_momentum_r7.yaml`
- Status: `blocked`
- Ready: `no`
- Execution substate: `blocked`
- Gate taxonomy: workflow_pass, research_pass, llm_contribution_pass, paper_ready_pass.
- Gate summary: `{'workflow_pass': False, 'research_pass': False, 'llm_contribution_pass': None, 'paper_ready_pass': False, 'execution_substate': 'blocked', 'blocked_checks': ['lifecycle', 'execution', 'universe_audit', 'alpaca_env', 'feature_packets', 'promotion_report', 'capability_report'], 'warning_checks': ['router_order_authorization'], 'paper_change_cadence': {'status': 'manual_review_required', 'policy': 'paper-stage spec changes require a linked decision record and at least 10 trading days since the prior paper-stage change unless the change is a documented risk-reduction kill-rule exception', 'automation_limit': 'current StrategyVersion metadata does not yet prove iteration_id, decision_record_path, change_reason, or risk_reduction_only'}}`
- Paper change cadence: paper-stage spec changes require a linked decision record and >=10 trading days unless a documented de-risk exception applies.
- Safety note: paper readiness is a control gate for Alpaca Paper only, not live trading.

## Checks

### lifecycle

- Status: `blocked`
- Message: Paper automation requires lifecycle=active.
- Details: `{'lifecycle': 'draft'}`
- Suggested actions:
  - `uv run oc strategy approve us_core_satellite_momentum_r7`
  - `uv run oc strategy activate us_core_satellite_momentum_r7 --paper-auto --allow-paper-auto --data-source alpaca --enforce-paper-readiness`

### execution

- Status: `blocked`
- Message: execution.mode must be paper_auto; execution.broker must be alpaca_paper
- Details: `{'mode': 'manual_signal', 'broker': 'none', 'backend': 'python_reference'}`
- Suggested actions:
  - `uv run oc strategy activate us_core_satellite_momentum_r7 --paper-auto --allow-paper-auto --data-source alpaca --enforce-paper-readiness`

### data_source

- Status: `ok`
- Message: Paper automation uses a live/cache market data source.
- Details: `{'source': 'alpaca', 'symbol': 'SPY', 'timeframe': 'daily', 'data_mode': 'paper_ready'}`

### universe_audit

- Status: `blocked`
- Message: Paper automation requires point-in-time universe membership or explicit fixed-universe evidence.
- Details: `{'status': 'blocked', 'json_path': 'reports/research/us_core_satellite_momentum_r7-universe-audit.json', 'report_path': 'reports/research/us_core_satellite_momentum_r7-universe-audit.md', 'findings': [{'code': 'current_symbol_universe_bias', 'severity': 'blocked', 'message': 'Multi-symbol universes need point-in-time membership evidence before research_pass; a static current-symbol list can leak survivorship.', 'evidence': {'symbols': ['BIL', 'QQQ', 'SPY', 'XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY'], 'metadata': {}}}, {'code': 'missing_universe_selection_timestamp', 'severity': 'warning', 'message': 'Universe selection should record when the symbol list became known to avoid current-list backfills.', 'evidence': {'symbols': ['BIL', 'QQQ', 'SPY', 'XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY'], 'metadata': {}}}, {'code': 'missing_delisting_policy', 'severity': 'warning', 'message': 'Universe audit did not find a delisting policy; scans may overstate historical opportunity if failed or delisted names are absent.', 'evidence': {'symbols': ['BIL', 'QQQ', 'SPY', 'XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY'], 'metadata': {}}}]}`
- Suggested actions:
  - `Add notes.universe_audit point_in_time_membership evidence, or reduce the strategy to an explicitly fixed instrument universe before paper_auto.`

### alpaca_env

- Status: `blocked`
- Message: Paper readiness currently targets broker=alpaca_paper.
- Details: `{'broker': 'none'}`
- Suggested actions:
  - `uv run oc strategy activate us_core_satellite_momentum_r7 --paper-auto --allow-paper-auto --data-source alpaca --enforce-paper-readiness`

### kill_switch

- Status: `ok`
- Message: Paper kill switch is clear.

### account_snapshot

- Status: `ok`
- Message: Paper account snapshot is available.
- Details: `{'generated_at': '2026-07-09T23:07:39.301258+00:00', 'equity': 1015713.28, 'cash': 235472.62, 'buying_power': 1722131.14}`

### nautilus_backend

- Status: `ok`
- Message: NautilusTrader package is available.
- Details: `{'backend': 'python_reference', 'nautilus_installed': True}`

### portfolio_routing

- Status: `ok`
- Message: cross_sectional_momentum portfolio routing is declared inside StrategySpec.
- Details: `{'mode': 'cross_sectional_momentum', 'max_symbols_per_day': 4, 'gross_exposure_limit': 1.0, 'max_symbol_weight': 0.4, 'same_day_flatten': False, 'duplicate_signal_policy': 'stable_signal_id', 'selected_route_label': 'core-satellite-r7:family-preregistered', 'universe': ['SPY', 'XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY', 'QQQ', 'BIL']}`

### portfolio_risk

- Status: `ok`
- Message: cross_sectional_momentum gross exposure and concentration limits are explicit.
- Details: `{'universe': ['SPY', 'XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY', 'QQQ', 'BIL'], 'mode': 'cross_sectional_momentum', 'gross_exposure_limit_pct': 100.0, 'single_name_weight_limit_pct': 40.0, 'max_symbols_per_day': 4, 'same_day_flatten': False, 'duplicate_signal_policy': 'stable_signal_id', 'sector_concentration': 'bounded_by_max_symbols_and_weight; sector map not registered', 'borrow_short_caveat': 'long-only paper routing; borrow is out of scope', 'effective_weight_note': 'gross limit is tighter than max_symbols_per_day * max_symbol_weight; scanner will equalize down to the gross limit'}`

### feature_packets

- Status: `blocked`
- Message: Paper feature factors require saved replay packets: filing_catalyst_score: packet not found at reports/features/us_core_satellite_momentum_r7/filing_catalyst_score/packets.jsonl; news_earnings_score: packet not found at reports/features/us_core_satellite_momentum_r7/news_earnings_score/packets.jsonl
- Details: `{'missing': ['filing_catalyst_score: packet not found at reports/features/us_core_satellite_momentum_r7/filing_catalyst_score/packets.jsonl', 'news_earnings_score: packet not found at reports/features/us_core_satellite_momentum_r7/news_earnings_score/packets.jsonl'], 'inspected': [{'factor': 'filing_catalyst_score', 'path': 'reports/features/us_core_satellite_momentum_r7/filing_catalyst_score/packets.jsonl', 'field': 'catalyst_strength', 'status': 'missing', 'warnings': ['feature packet is missing on disk'], 'evidence_count': 0, 'missing_evidence_count': 0}, {'factor': 'news_earnings_score', 'path': 'reports/features/us_core_satellite_momentum_r7/news_earnings_score/packets.jsonl', 'field': 'catalyst_strength', 'status': 'missing', 'warnings': ['feature packet is missing on disk'], 'evidence_count': 0, 'missing_evidence_count': 0}]}`
- Suggested actions:
  - `Write point-in-time packets with uv run oc feature write or uv run oc feature from-context.`

### promotion_report

- Status: `blocked`
- Message: Paper automation requires a promotion report before activation.
- Details: `{'path': '/root/codex-test/open-composer/reports/research/us_core_satellite_momentum_r7-promotion.json'}`
- Suggested actions:
  - `uv run oc strategy promotion-report strategy_specs/drafts/us_core_satellite_momentum_r7.yaml --oos-ratio 0.3 --walk-forward-folds 3`

### harness_artifacts

- Status: `ok`
- Message: All 8 harness artifacts present for domains ['daily_open_execution', 'llm_or_news_signal'].
- Details: `{'risk_domains': ['daily_open_execution', 'llm_or_news_signal'], 'required_artifacts': ['capability_review', 'execution_policy', 'execution_reality_report', 'feature_packet_schema', 'marginal_lift_report', 'missing_modality_robustness_report', 'pit_replay_evidence', 'source_cards']}`

### router_order_authorization

- Status: `warning`
- Message: Router order authorization artifact is missing. Router remains observation_only.
- Details: `{'path': 'reports/harness/paper/us_core_satellite_momentum_r7-router-order-authorization.json', 'portfolio_mode': 'cross_sectional_momentum'}`
- Suggested actions:
  - `Write reports/harness/paper/us_core_satellite_momentum_r7-router-order-authorization.json after PIT, promotion, harness verify, and paper safety review pass.`

### capability_report

- Status: `blocked`
- Message: strategy must be promoted to lifecycle=active; execution.mode must be paper_auto; execution.broker must be alpaca_paper
- Details: `{'capability': 'alpaca_paper_execution', 'status': 'blocked'}`
- Suggested actions:
  - `uv run oc spec capabilities strategy_specs/drafts/us_core_satellite_momentum_r7.yaml`
