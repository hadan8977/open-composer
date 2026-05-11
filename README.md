# Open Composer

Open Composer is a file-first strategy workbench for drafting, testing, reviewing,
and paper-monitoring trading ideas with Codex.

`StrategySpec` is the source of truth. Python is the deterministic reference.
NautilusTrader is the event-driven execution path. TradingView Pine is a
compatibility export, not the main runtime.

## Setup

```bash
cp .env.example .env
cp .codex/config.example.toml .codex/config.toml
uv sync
uv run oc doctor
```

`.env` holds API keys and broker settings. `.codex/config.toml` holds non-secret
Codex model and MCP settings. The project also reads `AGENTS.md` and repo skills
under `.agents/skills/`.

## Core Workflow

```bash
uv run oc capability test
uv run oc spec validate strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc spec capabilities strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc backtest strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc scan strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc compile pine-strategy strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc dashboard html
uv run ruff check .
uv run pytest
```

TradingView export:

```bash
uv run oc compile pine strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc compile pine-strategy strategy_specs/drafts/qqq_pullback_15m.yaml
```

Only deterministic OHLCV-compatible rules are exported. Pine is for charting and
Strategy Tester compatibility, not full strategy execution.

## Control Surface

Codex follows this repo in a fixed order:

1. `AGENTS.md`
2. the relevant skill in `.agents/skills/`
3. `capabilities/registry.yaml`
4. the strategy spec and generated artifacts

The important local gates are:

- `uv run oc capability test` before adding a new required capability
- `uv run oc spec validate <spec>` before code or Pine generation
- `uv run oc backtest <spec>` before promotion
- `uv run oc dashboard html` after new artifacts land

Generated reports, signal logs, cache files, strategy versions, and paper state
are local runtime outputs. They are intentionally ignored by git; checked-in
files are limited to source code, docs, fixtures, and a small example set.

## Data

Open Composer records provenance in manifests and reports. When live data is
available, use it. When not, the workflow falls back to local cache, sample, or
fixture data and labels that clearly.

Useful commands:

```bash
uv run oc data fetch --source alpaca --symbol MU --timeframe 15m --feed iex
uv run oc data fetch --source longbridge --symbol QQQ --timeframe 15m
uv run oc data compare --symbol QQQ --timeframe 15m --left alpaca --right longbridge
```

Current data sources:

- Alpaca IEX: implemented for bars and Alpaca Paper context.
- Longbridge: trial market-data adapter and comparison reports.
- SEC, FRED, Alpha Vantage, GDELT: registered context sources for review and replay.

Reports marked `sample fallback` or fixture replay are workflow evidence, not
market evidence.

## Paper Safety

Alpaca Paper is the only automated order path in the MVP. A paper order requires:

- a spec under `strategy_specs/active/`
- `lifecycle=active`
- `execution.mode=paper_auto`
- `execution.broker=alpaca_paper`
- paper environment variables
- an explicit command flag such as `--allow-paper-orders`

Example:

```bash
uv run oc strategy approve strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc strategy activate qqq_pullback_15m --paper-auto --allow-paper-auto
uv run oc run paper qqq_pullback_15m --max-cycles 1 --no-review
uv run oc paper submit <signal-id> --allow-paper-orders
uv run oc strategy disable qqq_pullback_15m
```

Real-money broker writes are out of scope for this MVP.

## Example Benchmark

- `mu_breakout_volume_15m_optimized_volume_plus`
  - sample data, 52 bars
  - annualized return `1089.90%`
  - Sharpe `45.78`
  - research-only, not production evidence

The current research audit is documented in [docs/review-optimization-completion-audit.zh.md](docs/review-optimization-completion-audit.zh.md).

## Project Docs

- [AGENTS.md](AGENTS.md)
- [OPEN-COMPOSER-BUILD-HANDOFF.md](OPEN-COMPOSER-BUILD-HANDOFF.md)
- [OPEN-COMPOSER-PRODUCT-MVP.md](OPEN-COMPOSER-PRODUCT-MVP.md)
- [docs/quant-capability-expansion-plan.zh.md](docs/quant-capability-expansion-plan.zh.md)
- [docs/quant-capability-expansion-review.zh.md](docs/quant-capability-expansion-review.zh.md)
- [docs/review-methodology.zh.md](docs/review-methodology.zh.md)
