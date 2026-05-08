# Open Composer

Open Composer 是一个面向个人交易学习者的对话式 AI 策略工作台。

第一版用文件仓库作为产品界面：用户用自然语言描述交易想法，Codex 在仓库约束下生成 `StrategySpec`、Python 回测/扫描、TradingView Pine Script、信号日志、报告和交易复盘材料。用户先通过 TradingView/本地扫描获得 15m、1h、daily、weekly 级别的信号，再手动决定交易动作。

## 当前状态

这个仓库已经包含增强版 MVP 的可运行骨架：

- `StrategySpec` YAML schema/model；
- sample OHLCV 数据；
- `oc` CLI；
- spec validation；
- deterministic signal/backtest/scanner engine；
- TradingView Pine v6 export；
- Markdown reports、JSONL signal logs、journal；
- OpenAI structured review card adapter；
- Alpaca data 和 Alpaca Paper adapter；
- capability registry、event/news/macro context builder；
- pytest/ruff 验证。

实盘真钱交易仍然保持手动决策。MVP 只允许 Alpaca Paper 模拟盘自动下单，并要求 active `paper_auto` 策略、paper 环境变量和显式 `--allow-paper-orders`。

## Quick Start

```bash
uv run oc doctor
uv run oc spec validate strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc backtest strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc scan strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc capability test
uv run oc events fetch --source sec --symbols QQQ
uv run oc macro fetch --source fred
uv run oc compile pine strategy_specs/drafts/qqq_pullback_15m.yaml
uv run pytest
```

可选环境变量见 `.env.example`：

- `OPENAI_API_KEY` + `OPENAI_MODEL` 用于 `oc review-signal <signal-id>`；
- `OPENAI_BASE_URL` 可沿用当前 OpenAI 兼容网关配置；未设置时会尝试读取本机 Codex `~/.codex/config.toml` 的 responses provider；
- `ALPACA_API_KEY_ID`、`ALPACA_API_SECRET_KEY`、`ALPACA_PAPER=true`、`ALPACA_DATA_FEED=iex` 用于 Alpaca 数据和模拟盘。
- `ALPHA_VANTAGE_API_KEY`、`FRED_API_KEY` 用于后续 live 新闻/宏观适配器；MVP 测试默认使用离线 fixture。

Alpaca Paper 下单示例：

```bash
uv run oc paper submit <signal-id> --allow-paper-orders
```

该命令只接受 `strategy_specs/active/` 中 lifecycle 为 `active`、`execution.mode=paper_auto`、`broker=alpaca_paper` 的策略。

## 阅读顺序

1. [OPEN-COMPOSER-BUILD-HANDOFF.md](OPEN-COMPOSER-BUILD-HANDOFF.md)
   - 新实现会话的唯一开工入口。包含产品定义、技术路线、目录结构、CLI 合同、Skill 合同、任务顺序和验收标准。

2. [OPEN-COMPOSER-PRODUCT-MVP.md](OPEN-COMPOSER-PRODUCT-MVP.md)
   - 正式 MVP 文档。说明用户、问题、范围、技术架构、核心流程、成功标准和阶段路线。

3. [OPEN-COMPOSER-CONTEXT-SUMMARY.md](OPEN-COMPOSER-CONTEXT-SUMMARY.md)
   - 背景研究总结。说明产品方向、市场参考、工具选型、LLM/Codex 分工和文档设计依据。

## 实现路线

```text
StrategySpec-first
  -> Codex AGENTS.md + repo skills
  -> Python signal/backtest/scanner engine
  -> TradingView Pine export
  -> signal parity report
  -> reports + signal logs + journal
  -> optional LLM review cards
  -> later data, paper-tracking, execution, and research adapters
```

`OPEN-COMPOSER-BUILD-HANDOFF.md` 是当前实现依据。其他文档用于补充产品判断和研究背景。
