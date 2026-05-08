# Open Composer Build Handoff

Date: 2026-05-08

## 1. Purpose

This is the canonical implementation brief for Open Composer.

A new Codex session should read this document first and start building the project skeleton. The document is self-contained and carries the product context, technical route, directory structure, task order, and acceptance criteria needed for implementation.

## 2. Product Definition

Open Composer is a personal, repo-native, conversation-first AI strategy workbench.

The product converts natural-language trading ideas into:

- `StrategySpec` YAML files;
- Python signal, backtest, and scanner code;
- TradingView Pine Script;
- signal parity reports;
- signal logs;
- Markdown backtest/review reports;
- optional structured LLM review cards;
- manual trade journal entries;
- weekly review summaries.

The first implementation helps one user create, test, monitor, review, and improve 15m/1h/daily/weekly trading strategies for manual execution.

## 3. Technical Route

```text
StrategySpec-first
  -> Codex AGENTS.md + repo skills
  -> Python signal/backtest/scanner engine
  -> Pine Script export
  -> signal parity report
  -> reports + signal logs + journal
  -> optional LLM review cards
  -> later data, paper-tracking, execution, and research adapters
```

### 3.1 Route Rationale

The core product asset is a structured strategy definition. That definition can generate multiple artifacts:

- Python for research, backtesting, scanning, reports, and journal links;
- Pine for TradingView chart observation and alerts;
- LLM review cards for structured event and risk review;
- later Lumibot adapter for paper execution;
- later vectorbt and Qlib adapters for advanced research.

This route gives the first version a small, testable local loop and gives later versions clean extension points.

## 4. Core Architecture

### 4.1 Codex Workspace

Codex is the strategy engineering layer.

It reads project rules from `AGENTS.md`, loads task-specific repo skills, edits files, runs tests, produces reports, and keeps strategy assets consistent.

### 4.2 StrategySpec

`StrategySpec` is the strategy source of truth.

Every strategy starts as YAML under `strategy_specs/drafts/`. Python and Pine artifacts are generated from, or checked against, the same spec.

### 4.3 Deterministic Runner

The runner is a local Python package.

It validates specs, calculates indicators, generates signals, runs a simple backtest, writes logs, exports Pine, writes reports, and records journal entries.

### 4.4 Optional Intelligence Layer

LLM API calls generate structured review cards for candidate signals, event summaries, risk explanations, and weekly review input.

### 4.5 Optional Tool Layer

MCP connects Codex to external docs, data sources, market research tools, browser tooling, GitHub, and future Alpaca/OpenBB/Polygon integrations.

## 5. First Build Slice

Build this first:

```text
StrategySpec schema
  -> sample StrategySpec
  -> sample OHLCV data
  -> Python indicator functions
  -> Python backtest/scanner
  -> Pine export
  -> Markdown report
  -> signal log
  -> journal entry
  -> tests
```

This slice must work in a fresh clone without external market-data credentials.

## 6. Later Build Slices

Add later:

```text
LLM review card
  -> real data adapters
  -> VPS scanner
  -> TradingView webhook logs
  -> Alpaca paper tracking
  -> Lumibot paper execution adapter
  -> vectorbt parameter research
  -> Qlib ML/factor research adapter
```

## 7. Dependency Baseline

Use this starting stack:

- Python 3.11+
- `typer` for CLI
- `pydantic` or `jsonschema` for schema validation
- `PyYAML` for spec loading
- `pandas` and `numpy` for OHLCV, indicators, and signal calculations
- `rich` for readable CLI output
- `pytest` for tests
- `ruff` for lint/format

Initial engine design:

- bar-close signal generation;
- next-bar-open fill assumption;
- long-only MVP examples;
- fixed-size or risk-limited position examples;
- deterministic sample-data path;
- explicit report of assumptions and limits.

## 8. Repository Structure

Create this structure:

```text
open-composer/
  README.md
  AGENTS.md
  CLAUDE.md
  pyproject.toml
  Makefile
  .env.example

  .agents/
    skills/
      strategy-designer/SKILL.md
      python-backtest-writer/SKILL.md
      pine-exporter/SKILL.md
      signal-parity-reviewer/SKILL.md
      risk-reviewer/SKILL.md
      weekly-reviewer/SKILL.md

  .codex/
    config.example.toml
    hooks.example.json

  strategy_specs/
    drafts/
    approved/
    active/
    retired/

  schemas/
    strategy_spec.schema.json
    signal.schema.json
    review_card.schema.json
    trade_journal.schema.json
    event_feature.schema.json

  open_composer/
    __init__.py
    cli.py
    config.py
    models/
      strategy_spec.py
      signal.py
      review_card.py
      journal.py
    indicators/
      trend.py
      momentum.py
      volume.py
    compiler/
      spec_to_python.py
      spec_to_pine.py
    engines/
      signal_engine.py
      backtest_engine.py
      scanner_engine.py
    adapters/
      data/
        sample.py
      notify/
        console.py
    review/
    risk/
    journal/
    reports/

  strategies_python/
    generated/
    custom/

  strategies_pine/
    generated/

  data/
    sample/
    cache/

  reports/
    backtests/
    parity/
    scans/
    reviews/
    weekly/

  signal_logs/
  journal/
  tests/
```

## 9. StrategySpec Contract

Minimum example:

```yaml
name: qqq_pullback_15m
description: QQQ pullback strategy with SPY market filter.
timeframe: 15m
universe: [QQQ, SPY]
lifecycle: draft

entry:
  all:
    - "close > ema(close, 200)"
    - "rsi(close, 14) < 35"
    - "volume > sma(volume, 20)"

exit:
  any:
    - "rsi(close, 14) > 55"
    - "close < ema(close, 50)"

risk:
  max_trades_per_day: 3
  max_position_weight: 0.5
  stop_loss_pct: 1.2
  take_profit_pct: 2.0

execution:
  mode: manual_signal
  signal_on: bar_close
  fill_assumption: next_bar_open

data_assumptions:
  source: sample
  adjusted: true
  timezone: America/New_York

notes:
  intent: Buy pullbacks during a positive trend and exit on recovery or trend damage.
  open_questions:
    - Should SPY trend be a separate market filter?
```

The schema should validate:

- `name`;
- `description`;
- `timeframe`;
- `universe`;
- `lifecycle`;
- `entry`;
- `exit`;
- `risk`;
- `execution`;
- `data_assumptions`;
- `notes`.

Supported MVP expression functions:

- `sma(series, window)`
- `ema(series, window)`
- `rsi(series, window)`
- `close`
- `open`
- `high`
- `low`
- `volume`

Expression parser approach:

- Start with a constrained parser or explicit expression whitelist.
- Generate clear validation errors for unsupported expressions.
- Preserve exact expression strings in reports.

## 10. CLI Contract

Create an `oc` CLI.

Initial commands:

```text
oc doctor
oc spec validate <path>
oc compile pine <spec>
oc backtest <spec>
oc scan <spec>
oc journal add --signal <id>
```

Later commands:

```text
oc compile python <spec>
oc parity <spec>
oc review-signal <signal-id>
oc weekly-review
oc spec promote <draft> --to approved
```

Command behavior:

- `oc doctor`: prints Python version, package status, writable folders, sample data status, optional key status.
- `oc spec validate`: validates schema and supported expressions.
- `oc backtest`: writes `reports/backtests/<run-id>.md` and `signal_logs/<run-id>.jsonl`.
- `oc scan`: writes latest scan signals to `signal_logs/`.
- `oc compile pine`: writes `strategies_pine/generated/<strategy>.pine`.
- `oc journal add`: writes a journal entry linked to a signal ID.

## 11. Skill Contracts

### 11.1 strategy-designer

Input: natural-language idea.
Output: draft `StrategySpec`.

The skill should:

- capture timeframe, universe, entry, exit, risk, execution, and assumptions;
- choose conservative defaults;
- write draft specs under `strategy_specs/drafts/`;
- include open questions in `notes.open_questions`;
- run `oc spec validate`.

### 11.2 python-backtest-writer

Input: `StrategySpec`.
Output: Python strategy artifacts and tests.

The skill should:

- use bar-close signal confirmation;
- use next-bar-open fill assumption;
- output signal logs;
- check lookahead bias;
- run relevant tests.

### 11.3 pine-exporter

Input: `StrategySpec`.
Output: Pine Script.

The skill should:

- generate alert conditions;
- preserve entry/exit semantics;
- document repaint and bar-close assumptions;
- produce a parity checklist.

### 11.4 signal-parity-reviewer

Input: Python signal log, Pine export, webhook logs when available.
Output: parity report.

The skill should:

- compare signal timing;
- report mismatches;
- flag Pine-specific behavior risks;
- write `reports/parity/<strategy>-<run-id>.md`.

### 11.5 risk-reviewer

Input: strategy, backtest report, signal.
Output: risk review.

The skill should:

- assess manual execution fit;
- check event and macro risks;
- check overtrading;
- summarize invalidation rules;
- write a structured review card.

### 11.6 weekly-reviewer

Input: reports, signal logs, journal.
Output: weekly review.

The skill should:

- summarize strong signals;
- summarize false positives;
- compare user actions against signal outcomes;
- propose draft improvements;
- write `reports/weekly/<week>.md`.

## 12. AGENTS.md Requirements

Create `AGENTS.md` with these rules:

```text
Product:
- Open Composer is a personal AI strategy workbench.
- StrategySpec is the source of truth.
- Codex creates specs, Python, Pine, reports, tests, and reviews.

Workflow:
- Create draft strategies first.
- Validate specs before generating code.
- Generate reports for every backtest.
- Log every signal.
- Link journal entries to signal IDs.

Safety:
- Active strategies use lifecycle controls.
- LLM review is advisory and structured.
- Broker write access belongs to a later approval-gated adapter.
- MCP tools are research tools.

Implementation:
- Start with sample data.
- Implement Python/Pine strategy artifacts before real broker integrations.
- Keep the first UI as CLI and files.
```

## 13. Initial Implementation Tasks

Execute these tasks in order:

1. Create Python package structure.
2. Add `pyproject.toml`.
3. Add `Makefile`.
4. Add `AGENTS.md`.
5. Add `.agents/skills/*/SKILL.md` skeletons.
6. Add `schemas/strategy_spec.schema.json`.
7. Add `strategy_specs/drafts/qqq_pullback_15m.yaml`.
8. Add `data/sample/qqq_15m.csv`.
9. Implement `oc doctor`.
10. Implement `oc spec validate`.
11. Implement SMA, EMA, RSI indicator helpers.
12. Implement constrained expression evaluation.
13. Implement minimal backtest/scanner.
14. Implement Pine export.
15. Write Markdown backtest report.
16. Write JSONL signal log.
17. Implement journal entry command.
18. Add tests for schema validation, indicators, expression validation, backtest output, and Pine export.
19. Run `ruff format`, `ruff check`, and `pytest`.

## 14. MVP Acceptance Criteria

The first implementation is complete when:

1. A fresh clone can run `oc doctor`.
2. The sample strategy validates.
3. The sample backtest runs from CLI.
4. A Markdown report is created.
5. A signal log is created.
6. Pine Script is generated from the same spec.
7. A journal entry can be recorded against a signal.
8. Tests pass.
9. README explains the local quick start.
10. `AGENTS.md` and repo skills guide Codex without chat history.

## 15. Future Adapter Sequence

Use this sequence after the MVP works:

1. Alpaca / Polygon / OpenBB data adapters.
2. VPS scheduler and notification.
3. LLM review card.
4. TradingView webhook log ingestion.
5. Alpaca paper account tracking.
6. Lumibot paper execution adapter.
7. vectorbt parameter research.
8. Qlib factor/ML research adapter.
9. LEAN mature deployment export.

## 16. Documentation Operating Rules

Use these rules when updating docs:

- Start with what the product is.
- Keep background separate from implementation instructions.
- Put implementation steps in this handoff.
- Put product scope in the MVP document.
- Put research context in the context summary.
- Prefer direct definitions over corrective language.
- Keep every requirement testable.
- Update README when the local quick start changes.

## 17. New Session Start Prompt

Use this prompt in a fresh Codex session:

```text
Read README.md, OPEN-COMPOSER-BUILD-HANDOFF.md, OPEN-COMPOSER-PRODUCT-MVP.md, and OPEN-COMPOSER-CONTEXT-SUMMARY.md.

Then implement the first build slice from OPEN-COMPOSER-BUILD-HANDOFF.md:
StrategySpec schema, sample strategy, sample OHLCV data, CLI, validation, indicators, minimal backtest/scanner, Pine export, report writer, signal log, journal entry, AGENTS.md, repo skills, and tests.

Keep the first version file/CLI-first and sample-data runnable. Run ruff and pytest before finishing.
```

## 18. Sources Used

- Atlassian PRD guidance: https://www.atlassian.com/agile/product-management/requirements
- Diátaxis documentation framework: https://diataxis.fr/
- OpenAI Codex AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- OpenAI Codex Skills: https://developers.openai.com/codex/skills
- OpenAI Codex MCP: https://developers.openai.com/codex/mcp
- OpenAI Skills catalog: https://github.com/openai/skills
- Composer Create with AI: https://help.composer.trade/article/108-create-with-ai
- Composer product site: https://www.composer.trade/
- Capitalise.ai Smart Notifications: https://support.capitalise.ai/en/articles/3339296-smart-notifications
- TradingView Strategy Alerts: https://www.tradingview.com/support/solutions/43000481368-strategy-alerts/
- TradingView Webhook Alerts: https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/
- Alpaca Paper Trading: https://docs.alpaca.markets/docs/trading/paper-trading/
- Lumibot Backtesting: https://lumibot.lumiwealth.com/backtesting.html
- vectorbt: https://vectorbt.dev/
- Microsoft Qlib: https://github.com/microsoft/qlib
- Qlib paper: https://arxiv.org/abs/2009.11189
