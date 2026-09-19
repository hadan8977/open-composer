#!/usr/bin/env python3
"""Build and verify the interactive code map under ``docs/codemap/``.

Outputs
-------
``docs/codemap/codemap.json``  the graph: 20 first-screen nodes, edges with
                               import / store / API / library evidence, five
                               end-to-end flows, per-node tests and files.
``docs/codemap/codemap.html``  self-contained viewer (no network access needed).
``docs/codemap/codemap.lock``  fingerprints of every input file per node plus
                               output hashes, so staleness is detectable.

Everything in the JSON is derived from the working tree by ``ast`` parsing and
regex scans; hand-written parts (node purposes, flow step wording) are bound to
``file`` + ``symbol`` anchors that are resolved to line numbers at build time
and re-checked by ``--verify``.

Usage
-----
    uv run python scripts/build_codemap.py            # build all three files
    uv run python scripts/build_codemap.py --verify   # re-derive and compare
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "codemap"
TEMPLATE_PATH = Path(__file__).resolve().parent / "codemap_template.html"
MAX_FIRST_SCREEN_NODES = 20
CHURN_SINCE = "2026-08-01"

# --------------------------------------------------------------------------- #
# Node catalogue (first screen). Category ids: product / domain / research /
# store / external. Column = layered layout position (0 = left).
# --------------------------------------------------------------------------- #
NODES: list[dict[str, Any]] = [
    {
        "id": "cli",
        "label": "CLI 与产品工具链",
        "category": "product",
        "col": 0,
        "row": 0,
        "purpose": (
            "Typer 入口 `oc`（28 个命令组、8.7k 行单文件）、Strategy Project 文件、"
            "repo check、部署与就绪度检查。所有产品动作从这里分发到领域与研究模块。"
        ),
        "configs": ["Makefile", "pyproject.toml"],
    },
    {
        "id": "scripts",
        "label": "脚本与定时任务",
        "category": "product",
        "col": 0,
        "row": 2,
        "purpose": (
            "数据归档、特征构建、因子筛选、网格评估、每日观察周期等命令行脚本；"
            "crontab 每个交易日调用其中三条。它们是研究内核最主要的实际调用方。"
        ),
        "configs": ["scripts/install_daily_cron.sh", "scripts/run_capped.sh"],
    },
    {
        "id": "spec",
        "label": "StrategySpec 与数据模型",
        "category": "domain",
        "col": 1,
        "row": 0,
        "purpose": (
            "策略行为唯一事实来源：pydantic 严格模型（extra=forbid）、九种组合模式、"
            "执行/成本/数据假设、版本快照与生命周期状态机。"
        ),
        "configs": ["schemas/backtest_run.schema.json"],
    },
    {
        "id": "dsl",
        "label": "表达式 DSL、指标与编译器",
        "category": "domain",
        "col": 1,
        "row": 1,
        "purpose": (
            "入场/出场规则的受限 AST 表达式求值、约二十个指标函数、美股交易日历，"
            "以及 Spec 到 Pine / Python 的编译导出。"
        ),
        "configs": [],
    },
    {
        "id": "governance",
        "label": "研究治理与证据",
        "category": "research",
        "col": 1,
        "row": 2,
        "purpose": (
            "campaign 合同、迭代档案、知识记忆、晋级报告、研究简报、证据托管与 harness "
            "策略。决定一轮研究能否开始、能否晋级；本身不产生收益证据。"
        ),
        "configs": [
            "harness/risk_domains.yaml",
            "harness/skill_manifest.yaml",
            "harness/artifact_contracts.yaml",
            "harness/source_policy.yaml",
        ],
    },
    {
        "id": "autollm",
        "label": "自动研究、LLM 与新闻",
        "category": "research",
        "col": 1,
        "row": 3,
        "purpose": (
            "`oc research auto` 的论点到草稿 Spec 流程、LLM 评审卡、新闻 PIT 包采集与"
            "LLM 事件抽取、点时特征包。LLM 输出只能经结构化包影响策略。"
        ),
        "configs": ["prompts/README.md", "knowledge/quant_capability_knowledge_base.yaml"],
    },
    {
        "id": "engines",
        "label": "回测/信号引擎、分析与报告",
        "category": "domain",
        "col": 2,
        "row": 0,
        "purpose": (
            "确定性 Python 参考回测（逐 bar 撮合、成本、风控）、信号与扫描引擎、"
            "绩效/执行现实/数据健全性分析、Markdown+JSON 报告写入。"
        ),
        "configs": [],
    },
    {
        "id": "kernel",
        "label": "研究内核（实验循环、门槛合同）",
        "category": "research",
        "col": 2,
        "row": 1,
        "purpose": (
            "当前一代评估路径：PIT 宇宙、逐年扩展窗口前推、成本后收益、DSR 自动试验计数、"
            "git 封印的门槛合同、机制评估与近期窗口 v2 门槛，写实验账本。"
        ),
        "configs": [
            "config/promotion/kernel-paper-tier-gates.json",
            "config/promotion/unlevered-family-paper-tier-gates.json",
            "config/promotion/recent-regime-high-return-gates-v2.json",
            "config/promotion/recent-regime-high-hit-rate-gates.json",
        ],
    },
    {
        "id": "features",
        "label": "特征管线与因子库",
        "category": "research",
        "col": 2,
        "row": 2,
        "purpose": (
            "日频/日内特征表、Alpha158/101/191、OSAP、Reversal Trend 特征定义，PIT 宇宙"
            "与标签构建，注册因子库与 Factor Lab（IC 诊断）、因子谱系。"
        ),
        "configs": [],
    },
    {
        "id": "ml",
        "label": "ML 训练后端",
        "category": "research",
        "col": 2,
        "row": 3,
        "purpose": (
            "LightGBM/sklearn 训练、时序窗口、预测与评估的通用后端，以及路由 ML 门、"
            "动量 ML 挑战者等模型研究模块。"
        ),
        "configs": [],
    },
    {
        "id": "routers",
        "label": "路由与动量策略族",
        "category": "research",
        "col": 2,
        "row": 4,
        "purpose": (
            "2026-05 至 08 的产品内置策略族：混合/贝塔/核心卫星路由、暴露开关、"
            "择时、杠杆、动量组合与其晋级/回放审计。`research/__init__.py` 门面在此。"
        ),
        "configs": [],
    },
    {
        "id": "rounds",
        "label": "按轮次一次性研究模块",
        "category": "research",
        "col": 2,
        "row": 5,
        "texture": "hatch",
        "purpose": (
            "以轮次命名的模块（pit_semantic_theme r11-r24、multiasset r1-r7、"
            "breadth/high-beta/VIX r1 等）及其 prepare 脚本。每轮复制一份而非参数化；"
            "只被自身测试与少数脚本引用。"
        ),
        "configs": [],
    },
    {
        "id": "data",
        "label": "数据适配与能力注册",
        "category": "product",
        "col": 3,
        "row": 0,
        "purpose": (
            "样例/Alpaca/Longbridge/SIP parquet 行情加载与回退清单、CBOE/SEC/CFTC "
            "事件与宏观抓取、`capabilities/registry.yaml` 能力评估与缓存管理。"
        ),
        "configs": ["capabilities/registry.yaml"],
    },
    {
        "id": "execution",
        "label": "执行适配（目标权重、Nautilus）",
        "category": "product",
        "col": 3,
        "row": 1,
        "purpose": (
            "各组合模式的目标权重计算（单标的、路由、模型排序）、整股规模化、"
            "执行策略、NautilusTrader 回测/执行运行时与平价，以及 Step 14 通用 "
            "BarCycleRunner（open_composer/execution/，进行中）。"
        ),
        "configs": [],
    },
    {
        "id": "paper",
        "label": "模拟盘、券商与安全控制",
        "category": "product",
        "col": 3,
        "row": 2,
        "purpose": (
            "Alpaca Paper 唯一写入路径：授权、就绪度、kill switch、订单窗口、新鲜度、"
            "TCA、状态漂移、锁；paper runner、Telegram 通知与日志。"
        ),
        "configs": [],
    },
    {
        "id": "store_data",
        "label": "数据湖（parquet/DuckDB）",
        "category": "store",
        "col": 4,
        "row": 0,
        "purpose": (
            "本地文件数据：data/sip 与 data/sip-hist（SIP 日线/分钟 2016 起，约 60GB）、"
            "data/features（约 12GB 特征表）、缓存与研究快照。没有数据库服务，DuckDB 内嵌查询。"
        ),
        "paths": [
            "data/sip",
            "data/sip-hist",
            "data/sip-delisted",
            "data/features",
            "data/cache",
            "data/research",
            "data/bars",
            "data/forward",
            "data/sample",
            "data/fixtures",
        ],
    },
    {
        "id": "store_artifacts",
        "label": "产物与状态文件",
        "category": "store",
        "col": 4,
        "row": 1,
        "purpose": (
            "reports/（回测、研究、账本、模拟盘状态）、signal_logs/、strategy_specs/、"
            "strategy_versions/、config/promotion 门槛合同、journal 等。全部是 git 可审计文件。"
        ),
        "paths": [
            "reports",
            "signal_logs",
            "strategy_specs",
            "strategy_versions",
            "config/promotion",
            "capabilities/registry.yaml",
            "journal",
            "event_logs",
            "feature_logs",
            "watchlists",
            "harness",
            "schemas",
            "prompts",
        ],
    },
    {
        "id": "shared",
        "label": "共享基础（配置、存储、工具）",
        "category": "product",
        "col": 3,
        "row": 3,
        "purpose": (
            ".env/配置读取、项目根路径与运行 ID、JSON/JSONL/YAML 读写、时间周期。"
            "几乎所有模块都依赖它，它不依赖任何内部模块，是唯一的公共叶子。"
        ),
        "configs": [".env.example"],
    },
    {
        "id": "external",
        "label": "外部服务与第三方库",
        "category": "external",
        "col": 4,
        "row": 2,
        "purpose": (
            "服务：Alpaca Market Data 与 Paper Trading、Longbridge OpenAPI、SEC EDGAR、FRED、"
            "CFTC、CBOE、Alpha Vantage、OpenAI 兼容网关、Telegram Bot、Cloudflare Access。"
            "库：pandas/numpy、DuckDB/pyarrow、LightGBM/scikit-learn、NautilusTrader、"
            "pydantic/typer，mlflow/quantstats 可选。"
        ),
        "paths": [],
    },
]

CATEGORIES = {
    "product": "产品与运行面",
    "domain": "核心领域",
    "research": "研究面",
    "store": "数据存储",
    "external": "外部服务与库",
}

COLUMNS = [
    "入口与运行面",
    "领域模型与治理",
    "引擎与研究",
    "适配层与共享基础",
    "存储与外部",
]

# Ordered assignment rules: first match wins. ``__init__`` of the research
# package is a facade that re-exports router modules, so it lives with them.
RULES: list[tuple[str, str]] = [
    (r"^open_composer/research/pit_semantic_theme_\w+\.py$", "rounds"),
    (r"^open_composer/research/\w+_r\d+(?:_\w+)?\.py$", "rounds"),
    (r"^scripts/prepare_\w+\.py$", "rounds"),
    (r"^open_composer/adapters/data/multiasset_paper_control_r7_snapshot\.py$", "rounds"),
    (r"^open_composer/adapters/execution/multiasset_\w+_r\d+_target_weights\.py$", "rounds"),
    (r"^open_composer/research/(kernel|regime|optimizers)/", "kernel"),
    (r"^open_composer/research/parameter_sweep\.py$", "kernel"),
    (r"^open_composer/research/(features|bars|pine_port)/", "features"),
    (
        r"^open_composer/research/(factor_library|factor_lab|factor_lineage|factor_propose"
        r"|factor_decay|geometry_features|universe_audit|stock_momentum_data_feasibility"
        r"|minute_momentum_feasibility|momentum_data_refresh|corporate_action_reconciliation"
        r"|price_adjustment_quality)\.py$",
        "features",
    ),
    (r"^open_composer/research/ml_backend/", "ml"),
    (
        r"^open_composer/research/(momentum_ml_research|momentum_ml_challenger"
        r"|multiasset_momentum_ml|pdr_ml_gate|pdr_ml_gate_evaluation)\.py$",
        "ml",
    ),
    (r"^open_composer/research/news/", "autollm"),
    (
        r"^open_composer/research/(auto_research|auto_compare|drafter|llm_\w+"
        r"|hybrid_news_evidence|momentum_multimodal|multiasset_momentum_multimodal"
        r"|regime_retrieval)\.py$",
        "autollm",
    ),
    (r"^open_composer/(review|agent_backend)/", "autollm"),
    (r"^open_composer/feature_packets\.py$", "autollm"),
    (
        r"^open_composer/research/(campaign|iteration_dossier|iteration_controller"
        r"|knowledge_memory|promotion|research_brief|evidence|evidence_custody|contracts"
        r"|design_contract|artifact_state|control|research_report|alt_data_quality"
        r"|alternative_data_evidence|metadata|research_cache_manifest|skill_attribution"
        r"|campaign_statistics|quality_diversity|pbo|blind_test|cost_sensitivity"
        r"|strategy_dag|router_promotion|router_replay_audit)\.py$",
        "governance",
    ),
    (r"^open_composer/harness/", "governance"),
    (r"^open_composer/research/", "routers"),
    (r"^open_composer/models/", "spec"),
    (r"^open_composer/(strategy_versions|strategy_lifecycle)\.py$", "spec"),
    (r"^open_composer/(expressions|market_calendar)\.py$", "dsl"),
    (r"^open_composer/(indicators|compiler)/", "dsl"),
    (r"^open_composer/(engines|analytics|reports)/", "engines"),
    (r"^open_composer/adapters/(data|events)/", "data"),
    (r"^open_composer/capabilities/", "data"),
    (r"^open_composer/(strategy_capabilities|cache)\.py$", "data"),
    (r"^open_composer/adapters/execution/", "execution"),
    (r"^open_composer/execution/", "execution"),
    (r"^open_composer/execution_policy\.py$", "execution"),
    (r"^open_composer/adapters/broker/", "paper"),
    (r"^open_composer/(paper_\w+|router_authorization)\.py$", "paper"),
    (r"^open_composer/(runner|notifications|journal)/", "paper"),
    (r"^open_composer/(config|storage|json_utils|yaml_utils|timeframes|__init__)\.py$", "shared"),
    (r"^open_composer/context\.py$", "autollm"),
    (r"^open_composer/", "cli"),
    (r"^scripts/", "scripts"),
]
COMPILED_RULES = [(re.compile(pattern), node_id) for pattern, node_id in RULES]

SCRIPT_ROLES: list[tuple[str, str]] = [
    (
        r"^scripts/(update_sip_archive|fetch_sip_universe|check_sip_freshness|fetch_symbol_list"
        r"|fetch_watchdog|materialize_longbridge_adjusted_history|collect_alpaca_news_packets)",
        "数据归档与抓取",
    ),
    (r"^scripts/build_", "特征构建"),
    (
        r"^scripts/(screen_factors|run_step13_m_grid|run_b3_grid|run_baseline_chain|evaluate_"
        r"|search_|event_study|reversal_trend_parity|diagnose_|duckdb_|train_pdr|research_"
        r"|export_candidate_artifact|extract_news_events_llm|new_lightweight_iteration)",
        "评估与研究",
    ),
    (
        r"^scripts/(run_daily_paper_cycle|run_bar_cycle|run_momentum_shadow_cycle"
        r"|run_r7_forward_observation|install_daily_cron|momentum-shadow-cron)",
        "模拟盘/观察周期",
    ),
    (r"^scripts/", "运维与安装"),
]

STORE_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "store_data": [
        (
            r'"data"\s*/\s*"(sip|sip-hist|sip-delisted|features|cache|research|bars|forward'
            r'|raw|sample|fixtures|_duckdb_tmp)"',
            "data/{1}",
        ),
        (
            r"\bdata/(sip|sip-hist|sip-delisted|features|cache|research|bars|forward|raw"
            r"|sample|fixtures|_duckdb_tmp)\b",
            "data/{1}",
        ),
    ],
    "store_artifacts": [
        (r'"reports"\s*/\s*"(\w+)"', "reports/{1}"),
        (r"\breports/(\w+)", "reports/{1}"),
        (
            r'"(signal_logs|strategy_specs|strategy_versions|journal|event_logs|feature_logs'
            r'|watchlists|projects|knowledge)"',
            "{1}/",
        ),
        (r'"config"\s*/\s*"promotion"|config/promotion', "config/promotion/"),
        (
            r'"capabilities"\s*/\s*"registry\.yaml"|capabilities/registry\.yaml',
            "capabilities/registry.yaml",
        ),
        (r'"harness"\s*/\s*"|\bharness/\w', "harness/"),
        (r'"schemas"\s*/\s*"|\bschemas/\w', "schemas/"),
        (r'"prompts"\s*/\s*"|\bprompts/\w', "prompts/"),
    ],
}

API_PATTERNS: list[tuple[str, str, str]] = [
    (
        "alpaca",
        r"alpaca\.markets|^\s*from alpaca\.|^\s*import alpaca\b",
        "Alpaca Market Data / Paper Trading",
    ),
    (
        "longbridge",
        r"^\s*from longbridge|^\s*import longbridge|LONGBRIDGE_APP_KEY",
        "Longbridge OpenAPI",
    ),
    ("sec", r"sec\.gov", "SEC EDGAR"),
    ("fred", r"stlouisfed\.org|\bFRED_API_KEY\b", "FRED"),
    ("cftc", r"cftc\.gov", "CFTC"),
    ("cboe", r"cboe\.com", "CBOE"),
    ("alphavantage", r"alphavantage\.co|ALPHA_VANTAGE_API_KEY", "Alpha Vantage"),
    (
        "openai",
        r"^\s*from openai|^\s*import openai|api\.openai\.com|OPENAI_BASE_URL",
        "OpenAI 兼容网关",
    ),
    ("telegram", r"api\.telegram\.org|TELEGRAM_BOT_TOKEN", "Telegram Bot"),
    ("cloudflare", r"cloudflareaccess\.com|CLOUDFLARE_ACCESS_", "Cloudflare Access"),
    ("github", r"raw\.githubusercontent\.com|github\.com/", "GitHub 托管数据集"),
    ("nasdaqtrader", r"nasdaqtrader\.com", "Nasdaq Trader 符号目录"),
    ("proshares", r"proshares\.com", "ProShares 基金页面"),
]

LIBRARIES = {
    "pandas",
    "numpy",
    "duckdb",
    "pyarrow",
    "lightgbm",
    "sklearn",
    "scipy",
    "joblib",
    "nautilus_trader",
    "pydantic",
    "typer",
    "rich",
    "yaml",
    "httpx",
    "jwt",
    "dotenv",
    "mlflow",
    "quantstats",
    "matplotlib",
}

# --------------------------------------------------------------------------- #
# End-to-end flows. Every step binds a node and a (file, symbol) anchor that is
# resolved to a line at build time and re-checked by --verify.
# --------------------------------------------------------------------------- #
FLOWS: list[dict[str, Any]] = [
    {
        "id": "F1",
        "title": "策略回测主路径：Spec 到报告与信号日志",
        "summary": (
            "用户或 agent 运行 `oc backtest <spec>`；Spec 校验后由确定性引擎回测，"
            "写回测报告、信号日志与策略版本快照。可选 NautilusTrader 后端并出平价报告。"
        ),
        "steps": [
            (
                "cli",
                "命令入口 `oc backtest`",
                "open_composer/cli.py",
                "def backtest(spec: Path)",
                "Typer 命令，解析 spec 路径后交给引擎。",
            ),
            (
                "spec",
                "加载并校验 StrategySpec",
                "open_composer/models/strategy_spec.py",
                "def load_strategy_spec(",
                "pydantic 严格模型加载，再校验入场/出场表达式。",
            ),
            (
                "governance",
                "迭代执行闸门",
                "open_composer/research/iteration_dossier.py",
                "def require_iteration_execution_gate(",
                "绑定到新迭代的 spec 必须先通过 iteration validate，否则拒绝回测。",
            ),
            (
                "engines",
                "回测编排 run_backtest",
                "open_composer/engines/backtest_engine.py",
                "def run_backtest(",
                "注册版本、选择后端、加载数据、写报告。",
            ),
            (
                "data",
                "按能力注册表加载 OHLCV",
                "open_composer/adapters/data/__init__.py",
                "def load_ohlcv_for_spec(",
                "样例 / Alpaca / Longbridge / SIP parquet，缺凭证时走 fixture 回退并写清单。",
            ),
            (
                "dsl",
                "表达式求值",
                "open_composer/expressions.py",
                "def evaluate_raw_expression(",
                "受限 AST 白名单内计算指标与布尔规则。",
            ),
            (
                "engines",
                "逐 bar 回测 backtest_frame",
                "open_composer/engines/backtest_engine.py",
                "def backtest_frame(",
                "撮合、成本、风控，产出 Trade 与 Signal。",
            ),
            (
                "execution",
                "可选 Nautilus 后端",
                "open_composer/adapters/execution/nautilus_runtime.py",
                "def run_nautilus_backtest(",
                "单标的 spec 可用事件驱动后端并生成平价报告。",
            ),
            (
                "store_artifacts",
                "写报告与信号日志",
                "open_composer/storage.py",
                "def append_jsonl(",
                "reports/backtests/<run>.md 与 signal_logs/<run>.jsonl。",
            ),
            (
                "spec",
                "注册策略版本",
                "open_composer/strategy_versions.py",
                "def register_strategy_version(",
                "内容哈希写入 strategy_versions/。",
            ),
        ],
    },
    {
        "id": "F2",
        "title": "研究内核实验：预注册门槛下的前推评估",
        "summary": (
            "以 Step 13 网格脚本为例：读取 SIP 价格与特征表，逐月重建 PIT 宇宙，"
            "逐年扩展窗口前推，成本后收益经 git 封印的门槛合同判定，追加实验账本。"
        ),
        "steps": [
            (
                "scripts",
                "网格脚本入口",
                "scripts/run_step13_m_grid.py",
                "def stage_m0(",
                "按配置哈希在账本去重，只跑未评估的单元。",
            ),
            (
                "store_data",
                "读取价格面板与特征表",
                "open_composer/research/features/panel.py",
                "def load_feature_panel(",
                "DuckDB 按年份读取 data/features 与 data/sip parquet。",
            ),
            (
                "features",
                "逐月 PIT 宇宙",
                "open_composer/research/features/universe.py",
                "def load_universe_panel(",
                "每个再平衡日只允许当时可见的成员。",
            ),
            (
                "kernel",
                "PIT 宇宙切片",
                "open_composer/research/kernel/loop.py",
                "def universe_as_of_calendar_month(",
                "评分与持有只用当月 cohort。",
            ),
            (
                "kernel",
                "逐年扩展窗口前推",
                "open_composer/research/kernel/loop.py",
                "def build_weight_schedule(",
                "每个测试年在带 embargo 的训练窗重训或重应用。",
            ),
            (
                "kernel",
                "成本后收益流",
                "open_composer/research/kernel/loop.py",
                "def returns_from_weight_schedule(",
                "按 bps/边扣成本，得到日频收益。",
            ),
            (
                "kernel",
                "加载预注册门槛",
                "open_composer/research/regime/gates.py",
                "def load_recent_high_return_gates(",
                "合同必须 git 跟踪且无未提交修改，记录 blob SHA。",
            ),
            (
                "kernel",
                "候选判定",
                "open_composer/research/regime/gates.py",
                "def evaluate_recent_high_return_candidate(",
                "近期窗口 CAGR、波动匹配 SPY 超额、DSR、安慰剂、ML 须胜规则基线。",
            ),
            (
                "store_artifacts",
                "追加实验账本",
                "open_composer/research/regime/gates.py",
                "def append_ledger(",
                "reports/research/ledger/experiments.jsonl 一行一单元。",
            ),
            (
                "scripts",
                "导出候选 artifact",
                "scripts/export_candidate_artifact.py",
                "def main(",
                "供观察模式目标权重读取的冻结候选。",
            ),
        ],
    },
    {
        "id": "F3",
        "title": "自动研究：一句话论点到草稿 Spec 与证据报告",
        "summary": (
            '`oc research auto "<thesis>"` 从注册因子库选因子、做单因子 IC 诊断，'
            "起草 StrategySpec 到 drafts/，运行证据工作流并写研究报告。"
        ),
        "steps": [
            (
                "cli",
                "命令入口 `oc research auto`",
                "open_composer/cli.py",
                "def research_auto_command(",
                "接收论点、宇宙、周期参数。",
            ),
            (
                "autollm",
                "论点解析与因子选择",
                "open_composer/research/auto_research.py",
                "def run_auto_research(",
                "从目录挑候选因子，串起整个流程。",
            ),
            (
                "features",
                "注册因子库",
                "open_composer/research/factor_library.py",
                "def list_factors(",
                "带来源谱系的因子定义与表达式物化。",
            ),
            (
                "features",
                "单因子 IC 诊断",
                "open_composer/research/factor_lab.py",
                "def run_factor_lab(",
                "rank IC、衰减与稳定性。",
            ),
            (
                "autollm",
                "起草 StrategySpec",
                "open_composer/research/auto_research.py",
                "def _draft_spec(",
                "写入 strategy_specs/drafts/，source=factor_library。",
            ),
            (
                "governance",
                "晋级报告",
                "open_composer/research/promotion.py",
                "def build_promotion_report(",
                "基准族、样本外、成本、数据敏感性检查。",
            ),
            (
                "store_artifacts",
                "写最终报告",
                "open_composer/research/auto_research.py",
                "def _write_final_report(",
                "reports/research/auto/<run>/ 下 JSON 与 Markdown。",
            ),
        ],
    },
    {
        "id": "F4",
        "title": "每日观察 / 模拟盘周期（cron 驱动）",
        "summary": (
            "crontab 每个交易日调用 run_daily_paper_cycle.py：同步 Alpaca Paper 账户、"
            "计算目标权重并记信号日志；只有显式允许且通过授权、kill switch、"
            "订单窗口与新鲜度检查时才会提交模拟盘订单。"
        ),
        "steps": [
            (
                "scripts",
                "周期脚本入口",
                "scripts/run_daily_paper_cycle.py",
                "def main(",
                "非交易日自行跳过；按 spec 组合模式选择分支。",
            ),
            (
                "scripts",
                "观察模式分支",
                "scripts/run_daily_paper_cycle.py",
                "def run_model_ranking_observation_cycle(",
                "model_ranking_portfolio 只做账户同步 + 目标权重，不下单。",
            ),
            (
                "paper",
                "同步模拟盘账户",
                "open_composer/adapters/broker/alpaca_paper.py",
                "def sync_paper_account(",
                "写 reports/paper/account.json 与 positions.json。",
            ),
            (
                "external",
                "Alpaca Paper API",
                "open_composer/adapters/broker/alpaca_paper.py",
                "ALPACA_PAPER_ORIGIN =",
                "只允许 paper-api.alpaca.markets 源。",
            ),
            (
                "cli",
                "命令 `oc strategy target-weights`",
                "open_composer/cli.py",
                "def strategy_target_weights(",
                "按组合模式分发到执行适配。",
            ),
            (
                "execution",
                "模型排序目标权重",
                "open_composer/adapters/execution/model_ranking_target_weights.py",
                "def score_and_select(",
                "读候选 artifact、最新特征行与趋势门，选前 K。",
            ),
            (
                "paper",
                "受控下单（仅显式允许时）",
                "open_composer/adapters/broker/alpaca_paper.py",
                "def submit_paper_order(",
                "授权、kill switch、订单窗口、新鲜度、锁，全部通过才提交。",
            ),
            (
                "store_artifacts",
                "评审卡与通知",
                "scripts/run_daily_paper_cycle.py",
                "def write_review_card(",
                "reports/paper/daily_cycle/ 与 Telegram 摘要。",
            ),
        ],
    },
    {
        "id": "F5",
        "title": "数据归档与特征构建（cron 22:00 UTC）",
        "summary": (
            "增量更新 SIP 日线/分钟 parquet 归档并做新鲜度告警；特征脚本用 DuckDB "
            "按年构建特征表，供研究内核与目标权重读取。"
        ),
        "steps": [
            (
                "scripts",
                "增量归档更新",
                "scripts/update_sip_archive.py",
                "def _merge_and_write(",
                "文件锁、原子写、与全量抓取互斥。",
            ),
            (
                "external",
                "Alpaca Market Data（SIP）",
                "scripts/fetch_sip_universe.py",
                "def _fetch_batch(",
                "按批拉取日线与分钟 bar。",
            ),
            (
                "store_data",
                "SIP parquet 分片",
                "open_composer/adapters/data/sip_parquet.py",
                "def load_sip_bars(",
                "data/sip/{daily,minute}/<year>/ 分片读取。",
            ),
            (
                "scripts",
                "新鲜度检查",
                "scripts/check_sip_freshness.py",
                "def main(",
                "落后交易日数超阈值时 Telegram 告警。",
            ),
            (
                "scripts",
                "构建日频特征表",
                "scripts/build_daily_features.py",
                "def main(",
                "DuckDB 按年份计算并写 data/features/daily。",
            ),
            (
                "features",
                "特征定义",
                "open_composer/research/features/daily_features.py",
                "def build_daily_features(",
                "27 列日频特征，跨截面中位数去均值。",
            ),
            (
                "store_data",
                "特征表供下游读取",
                "open_composer/research/features/panel.py",
                "def load_price_panel(",
                "内核实验与观察模式目标权重共用同一张表。",
            ),
        ],
    },
]

CRON_FALLBACK_SCRIPTS = (
    "scripts/update_sip_archive.py",
    "scripts/check_sip_freshness.py",
    "scripts/run_daily_paper_cycle.py",
)

CLI_GROUP_NAMES = {
    "app": "(root)",
    "research_brief_app": "strategy research-brief",
    "research_campaign_app": "research campaign",
    "research_iteration_app": "research iteration",
    "research_knowledge_app": "research knowledge",
}


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class SourceFile:
    path: str
    loc: int
    node: str
    sha256: str
    is_python: bool
    imports: list[tuple[str, int, str]] = field(default_factory=list)  # target, line, stmt
    lib_imports: Counter = field(default_factory=Counter)
    stores: list[tuple[str, str, int]] = field(default_factory=list)  # node, key, line
    apis: list[tuple[str, int]] = field(default_factory=list)  # api id, line
    test_count: int = 0


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assign_node(path: str) -> str | None:
    for pattern, node_id in COMPILED_RULES:
        if pattern.search(path):
            return node_id
    return None


def script_role(path: str) -> str:
    for pattern, role in SCRIPT_ROLES:
        if re.search(pattern, path):
            return role
    return "其他"


def collect_source_paths() -> list[Path]:
    paths: list[Path] = []
    paths.extend(sorted((ROOT / "open_composer").rglob("*.py")))
    paths.extend(sorted((ROOT / "scripts").glob("*.py")))
    paths.extend(sorted((ROOT / "scripts").glob("*.sh")))
    return [p for p in paths if "__pycache__" not in p.parts and "node_modules" not in p.parts]


def collect_test_paths() -> list[Path]:
    return sorted(p for p in (ROOT / "tests").rglob("*.py") if "__pycache__" not in p.parts)


def module_to_path(module: str, known: set[str]) -> str | None:
    parts = module.split(".")
    if not parts or not parts[0]:
        return None
    if parts[0] in {"open_composer", "scripts", "tests"}:
        candidate = "/".join(parts) + ".py"
        if candidate in known:
            return candidate
        candidate = "/".join(parts) + "/__init__.py"
        if candidate in known:
            return candidate
        return None
    candidate = f"scripts/{parts[0]}.py"
    if candidate in known:
        return candidate
    return None


def resolve_relative(module: str | None, level: int, file_path: str) -> str:
    base = file_path.split("/")[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    prefix = ".".join(base)
    if module:
        return f"{prefix}.{module}" if prefix else module
    return prefix


def docstring_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    end = getattr(value, "end_lineno", value.lineno)
                    lines.update(range(value.lineno, end + 1))
    return lines


_FACADE_EXPORTS: dict[str, dict[str, str] | None] = {}


def facade_exports(package_init: str) -> dict[str, str] | None:
    """Return the ``_EXPORTS`` name -> module map of a lazy (PEP 562) package
    facade such as ``open_composer/research/__init__.py``, or None. Without
    this, ``from open_composer.research import run_factor_lab`` would resolve
    to the package init only and every facade-exported module would look
    unreachable in the map."""
    if package_init not in _FACADE_EXPORTS:
        result: dict[str, str] | None = None
        path = ROOT / package_init
        if path.name == "__init__.py" and path.exists():
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:  # pragma: no cover - defensive
                tree = None
            for node in getattr(tree, "body", []):
                targets = node.targets if isinstance(node, ast.Assign) else []
                if isinstance(node, ast.AnnAssign):
                    targets = [node.target]
                if not any(isinstance(t, ast.Name) and t.id == "_EXPORTS" for t in targets):
                    continue
                value = node.value
                if isinstance(value, ast.Dict):
                    result = {
                        k.value: v.value
                        for k, v in zip(value.keys, value.values, strict=True)
                        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
                    }
        _FACADE_EXPORTS[package_init] = result
    return _FACADE_EXPORTS[package_init]


def parse_python(source_file: SourceFile, text: str, known: set[str]) -> None:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:  # pragma: no cover - defensive
        print(f"warning: cannot parse {source_file.path}: {exc}", file=sys.stderr)
        return
    lines = text.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                if root_name in LIBRARIES:
                    source_file.lib_imports[root_name] += 1
                target = module_to_path(alias.name, known)
                if target:
                    source_file.imports.append(
                        (target, node.lineno, lines[node.lineno - 1].strip())
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = resolve_relative(node.module, node.level, source_file.path)
            root_name = module.split(".")[0]
            if root_name in LIBRARIES:
                source_file.lib_imports[root_name] += 1
            stmt = lines[node.lineno - 1].strip()
            base_target = module_to_path(module, known)
            for alias in node.names:
                sub_target = module_to_path(f"{module}.{alias.name}", known) if module else None
                target = sub_target or base_target
                if sub_target is None and base_target and base_target.endswith("__init__.py"):
                    exports = facade_exports(base_target)
                    owner = exports.get(alias.name) if exports else None
                    if owner:
                        target = module_to_path(owner, known) or target
                if target:
                    source_file.imports.append((target, node.lineno, stmt))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name.startswith("test_"):
                source_file.test_count += 1
    skip = docstring_lines(tree)
    for lineno, raw in enumerate(lines, start=1):
        if lineno in skip:
            continue
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for store_node, patterns in STORE_PATTERNS.items():
            for pattern, template in patterns:
                match = re.search(pattern, raw)
                if match:
                    key = template
                    if "{1}" in template and match.lastindex:
                        key = template.replace("{1}", match.group(1))
                    source_file.stores.append((store_node, key, lineno))
        for api_id, pattern, _label in API_PATTERNS:
            if re.search(pattern, raw):
                source_file.apis.append((api_id, lineno))


def scan_text_file(source_file: SourceFile, text: str) -> None:
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        for store_node, patterns in STORE_PATTERNS.items():
            for pattern, template in patterns:
                match = re.search(pattern, raw)
                if match:
                    key = template
                    if "{1}" in template and match.lastindex:
                        key = template.replace("{1}", match.group(1))
                    source_file.stores.append((store_node, key, lineno))
        for api_id, pattern, _label in API_PATTERNS:
            if re.search(pattern, raw):
                source_file.apis.append((api_id, lineno))


def git_output(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout if result.returncode == 0 else ""


def git_history() -> tuple[dict[str, str], Counter]:
    """Return last-commit-date per file and commit-touch counts since CHURN_SINCE."""
    last_date: dict[str, str] = {}
    churn: Counter = Counter()
    output = git_output(["log", "--name-only", "--pretty=format:@@%cs"])
    current_date = ""
    for line in output.splitlines():
        if line.startswith("@@"):
            current_date = line[2:]
            continue
        if not line.strip():
            continue
        path = line.strip()
        if path not in last_date:
            last_date[path] = current_date
        if current_date >= CHURN_SINCE:
            churn[path] += 1
    return last_date, churn


def cli_command_map(cli_path: Path, known: set[str], node_of: dict[str, str]) -> dict[str, Any]:
    text = cli_path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    module_level_names: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                module_level_names[alias.asname or alias.name] = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module_level_names[alias.asname or alias.name.split(".")[0]] = alias.name
    commands: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not (isinstance(func, ast.Attribute) and func.attr == "command"):
                continue
            if not isinstance(func.value, ast.Name):
                continue
            group_var = func.value.id
            group = CLI_GROUP_NAMES.get(group_var)
            if group is None:
                group = (
                    group_var[:-4].replace("_", " ") if group_var.endswith("_app") else group_var
                )
            name = None
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                name = str(decorator.args[0].value)
            for keyword in decorator.keywords:
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                    name = str(keyword.value.value)
            if name is None:
                name = node.name.replace("_", "-")
            modules: set[str] = set()
            for inner in ast.walk(node):
                if isinstance(inner, ast.ImportFrom) and inner.module:
                    modules.add(inner.module)
                    for alias in inner.names:
                        modules.add(f"{inner.module}.{alias.name}")
                elif isinstance(inner, ast.Import):
                    for alias in inner.names:
                        modules.add(alias.name)
                elif isinstance(inner, ast.Name) and inner.id in module_level_names:
                    modules.add(module_level_names[inner.id])
            touched: Counter = Counter()
            for module in modules:
                target = module_to_path(module, known)
                if target and target != "open_composer/cli.py":
                    touched[node_of.get(target, "?")] += 1
            commands.append(
                {
                    "group": group,
                    "name": name,
                    "line": node.lineno,
                    "nodes": sorted(k for k in touched if k != "?"),
                }
            )
    groups: dict[str, dict[str, Any]] = {}
    for command in commands:
        entry = groups.setdefault(
            command["group"], {"group": command["group"], "commands": 0, "nodes": Counter()}
        )
        entry["commands"] += 1
        for node_id in command["nodes"]:
            entry["nodes"][node_id] += 1
    group_rows = [
        {
            "group": g["group"],
            "commands": g["commands"],
            "nodes": dict(sorted(g["nodes"].items(), key=lambda kv: -kv[1])),
        }
        for g in sorted(groups.values(), key=lambda g: -g["commands"])
    ]
    return {"total_commands": len(commands), "groups": group_rows, "commands": commands}


def resolve_symbol(file_path: str, symbol: str) -> int:
    text = (ROOT / file_path).read_text(encoding="utf-8", errors="replace")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if symbol in line:
            return lineno
    raise SystemExit(f"flow anchor not found: {file_path} :: {symbol!r}")


def crontab_lines() -> list[str]:
    try:
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, check=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    rows = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        schedule = " ".join(parts[:5])
        script = next((p for p in parts if p.startswith("scripts/")), "")
        rows.append(f"{schedule}  {script}".strip())
    return rows


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build_model() -> dict[str, Any]:
    source_paths = collect_source_paths()
    test_paths = collect_test_paths()
    known = {rel(p) for p in source_paths} | {rel(p) for p in test_paths}
    files: dict[str, SourceFile] = {}
    for path in source_paths + test_paths:
        rel_path = rel(path)
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        node_id = assign_node(rel_path) if not rel_path.startswith("tests/") else "tests"
        if node_id is None:
            raise SystemExit(f"no node rule matched {rel_path}")
        source_file = SourceFile(
            path=rel_path,
            loc=text.count("\n") + (1 if text and not text.endswith("\n") else 0),
            node=node_id,
            sha256=sha256_bytes(raw),
            is_python=path.suffix == ".py",
        )
        if source_file.is_python:
            parse_python(source_file, text, known)
        else:
            scan_text_file(source_file, text)
        files[rel_path] = source_file
    node_of = {p: f.node for p, f in files.items()}
    last_date, churn = git_history()

    # ---- file-level import graph -------------------------------------------------
    file_in: Counter = Counter()
    file_out: Counter = Counter()
    for source_file in files.values():
        targets = {t for t, _, _ in source_file.imports if t != source_file.path}
        file_out[source_file.path] = len(targets)
        for target in targets:
            file_in[target] += 1

    # ---- node-level edges ----------------------------------------------------------
    edge_weight: Counter = Counter()
    edge_evidence: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    intra_node_imports: Counter = Counter()
    for source_file in files.values():
        if source_file.node == "tests":
            continue
        for target, lineno, stmt in source_file.imports:
            target_node = node_of[target]
            if target_node == source_file.node:
                intra_node_imports[source_file.node] += 1
                continue
            key = (source_file.node, target_node, "import")
            edge_weight[key] += 1
            if len(edge_evidence[key]) < 8:
                edge_evidence[key].append(
                    {
                        "file": source_file.path,
                        "line": lineno,
                        "statement": stmt[:160],
                        "target": target,
                    }
                )
        seen_store: set[tuple[str, str]] = set()
        for store_node, store_key, lineno in source_file.stores:
            key = (source_file.node, store_node, "store")
            edge_weight[key] += 1
            if (store_node, store_key) not in seen_store and len(edge_evidence[key]) < 12:
                seen_store.add((store_node, store_key))
                edge_evidence[key].append(
                    {"file": source_file.path, "line": lineno, "statement": store_key}
                )
        seen_api: set[str] = set()
        for api_id, lineno in source_file.apis:
            key = (source_file.node, "external", "api")
            edge_weight[key] += 1
            if api_id not in seen_api and len(edge_evidence[key]) < 14:
                seen_api.add(api_id)
                label = next(lbl for aid, _p, lbl in API_PATTERNS if aid == api_id)
                edge_evidence[key].append(
                    {"file": source_file.path, "line": lineno, "statement": label}
                )
        for lib, count in source_file.lib_imports.items():
            key = (source_file.node, "external", "lib")
            edge_weight[key] += count
            if len(edge_evidence[key]) < 20 and all(
                e["statement"] != lib for e in edge_evidence[key]
            ):
                edge_evidence[key].append({"file": source_file.path, "line": 0, "statement": lib})

    edges = [
        {
            "id": f"{s}->{t}:{k}",
            "source": s,
            "target": t,
            "kind": k,
            "weight": w,
            "evidence": edge_evidence[(s, t, k)],
        }
        for (s, t, k), w in sorted(edge_weight.items())
    ]

    # ---- tests per node --------------------------------------------------------------
    tests_by_node: dict[str, dict[str, int]] = defaultdict(dict)
    test_totals = {"files": 0, "functions": 0, "loc": 0}
    for source_file in files.values():
        if source_file.node != "tests":
            continue
        test_totals["files"] += 1
        test_totals["functions"] += source_file.test_count
        test_totals["loc"] += source_file.loc
        covered = {node_of[t] for t, _, _ in source_file.imports if node_of[t] != "tests"}
        if not covered:
            covered = (
                {"cli"}
                if "CliRunner"
                in (ROOT / source_file.path).read_text(encoding="utf-8", errors="replace")
                else set()
            )
        for node_id in covered:
            tests_by_node[node_id][source_file.path] = source_file.test_count

    # ---- reachability from entrypoints ---------------------------------------------
    entrypoints = [
        p
        for p in files
        if p == "open_composer/cli.py" or (p.startswith("scripts/") and p.endswith(".py"))
    ]
    adjacency: dict[str, set[str]] = defaultdict(set)
    for source_file in files.values():
        for target, _, _ in source_file.imports:
            adjacency[source_file.path].add(target)

    def bfs(starts: list[str]) -> set[str]:
        seen: set[str] = set()
        stack = list(starts)
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(adjacency.get(current, ()))
        return seen

    cron_scripts = [
        f"scripts/{line.split('scripts/')[-1].split()[0]}"
        for line in crontab_lines()
        if "scripts/" in line
    ]
    cron_scripts = sorted({c for c in cron_scripts if c in files}) or [
        c for c in CRON_FALLBACK_SCRIPTS if c in files
    ]
    entry_classes: dict[str, list[str]] = {
        "cron": cron_scripts,
        "scripts": [p for p in entrypoints if p.startswith("scripts/")],
        "cli": ["open_composer/cli.py"],
    }
    reach_by_class = {cls: bfs(starts) for cls, starts in entry_classes.items()}
    reachable = set().union(*reach_by_class.values())

    def entries_for(path: str) -> list[str]:
        return [cls for cls in ("cron", "scripts", "cli") if path in reach_by_class[cls]]

    # ---- transitive dependents / dependencies at FILE level -------------------------
    # Node-level closure would manufacture paths (file A in X imports B in Y, and an
    # unrelated file C in Y imports D in Z does not make A depend on Z), so impact is
    # computed on the file graph and only then aggregated per node.
    reverse_adjacency: dict[str, set[str]] = defaultdict(set)
    for src, targets in adjacency.items():
        for target in targets:
            reverse_adjacency[target].add(src)

    def file_closure(paths: list[str], graph: dict[str, set[str]]) -> set[str]:
        start = set(paths)
        seen: set[str] = set()
        stack = list(paths)
        while stack:
            current = stack.pop()
            for nxt in graph.get(current, ()):
                if nxt not in seen and nxt not in start:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    def aggregate(paths: set[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
        per_node: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        tests = {"files": 0, "functions": 0}
        for path in paths:
            source_file = files[path]
            if source_file.node == "tests":
                tests["files"] += 1
                tests["functions"] += source_file.test_count
            else:
                per_node[source_file.node][0] += 1
                per_node[source_file.node][1] += source_file.loc
        rows = [
            {"id": node_id, "files": counts[0], "loc": counts[1]}
            for node_id, counts in sorted(per_node.items(), key=lambda kv: -kv[1][0])
        ]
        return rows, tests

    # ---- facade metric ----------------------------------------------------------------
    facade = "open_composer/research/__init__.py"
    facade_targets = {t for t, _, _ in files[facade].imports} if facade in files else set()
    facade_loaders = sorted(
        f.path
        for f in files.values()
        if f.node != "tests"
        and any(t.startswith("open_composer/research/") for t, _, _ in f.imports)
    )

    # ---- assemble nodes ---------------------------------------------------------------
    cli_map = cli_command_map(ROOT / "open_composer" / "cli.py", known, node_of)
    node_rows: list[dict[str, Any]] = []
    for spec in NODES:
        node_id = spec["id"]
        node_files = sorted((f for f in files.values() if f.node == node_id), key=lambda f: -f.loc)
        loc = sum(f.loc for f in node_files)
        upstream = Counter()
        dependencies = Counter()
        externals: dict[str, Counter] = {"store": Counter(), "api": Counter(), "lib": Counter()}
        for edge in edges:
            if edge["target"] == node_id and edge["kind"] == "import":
                upstream[edge["source"]] += edge["weight"]
            if edge["source"] == node_id:
                if edge["kind"] == "import":
                    dependencies[edge["target"]] += edge["weight"]
                else:
                    for ev in edge["evidence"]:
                        externals[edge["kind"]][ev["statement"]] += 1
        if node_id in {"store_data", "store_artifacts", "external"}:
            for edge in edges:
                if edge["target"] == node_id:
                    upstream[edge["source"]] += edge["weight"]
        tests = tests_by_node.get(node_id, {})
        churn_touches = sum(churn.get(f.path, 0) for f in node_files)
        last_dates = [last_date.get(f.path, "") for f in node_files]
        last_dates = [d for d in last_dates if d]
        unreachable = [
            f.path
            for f in node_files
            if f.is_python and f.path not in reachable and f.node not in {"tests"}
        ]
        node_paths = [f.path for f in node_files]
        impact_rows, impact_tests = aggregate(file_closure(node_paths, reverse_adjacency))
        pulls_rows, _unused = aggregate(file_closure(node_paths, adjacency))
        row = {
            "id": node_id,
            "label": spec["label"],
            "category": spec["category"],
            "category_label": CATEGORIES[spec["category"]],
            "layout": {"col": spec["col"], "row": spec["row"]},
            "texture": spec.get("texture"),
            "purpose": spec["purpose"],
            "configs": [c for c in spec.get("configs", []) if (ROOT / c).exists()],
            "paths": [p for p in spec.get("paths", []) if (ROOT / p).exists()],
            "file_count": len(node_files),
            "loc": loc,
            "python_loc": sum(f.loc for f in node_files if f.is_python),
            "test_files": len(tests),
            "test_count": sum(tests.values()),
            "churn_touches_since": churn_touches,
            "last_commit": max(last_dates) if last_dates else None,
            "upstream": [{"id": k, "weight": v} for k, v in upstream.most_common()],
            "dependencies": [{"id": k, "weight": v} for k, v in dependencies.most_common()],
            "impact": impact_rows,
            "impact_tests": impact_tests,
            "pulls_in": pulls_rows,
            "externals": {k: dict(v.most_common()) for k, v in externals.items()},
            "intra_node_imports": intra_node_imports.get(node_id, 0),
            "unreachable_from_entrypoints": {
                "files": len(unreachable),
                "loc": sum(files[p].loc for p in unreachable),
                "paths": unreachable[:60],
            },
            "reach": {
                "cron_loc": sum(
                    f.loc for f in node_files if f.is_python and "cron" in entries_for(f.path)
                ),
                "scripts_loc": sum(
                    f.loc for f in node_files if f.is_python and "scripts" in entries_for(f.path)
                ),
                "cli_loc": sum(
                    f.loc for f in node_files if f.is_python and "cli" in entries_for(f.path)
                ),
                "cli_only_loc": sum(
                    f.loc for f in node_files if f.is_python and entries_for(f.path) == ["cli"]
                ),
                "unreachable_loc": sum(files[p].loc for p in unreachable),
            },
            "tests": [
                {"path": p, "test_count": c}
                for p, c in sorted(tests.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
            "files": [
                {
                    "path": f.path,
                    "loc": f.loc,
                    "in": file_in.get(f.path, 0),
                    "out": file_out.get(f.path, 0),
                    "last_commit": last_date.get(f.path),
                    "reachable": (f.path in reachable) if f.is_python else None,
                    "entries": entries_for(f.path) if f.is_python else None,
                    "role": script_role(f.path) if node_id == "scripts" else None,
                }
                for f in node_files
            ],
            "flows": sorted(
                {fl["id"] for fl in FLOWS if any(s[0] == node_id for s in fl["steps"])}
            ),
        }
        if node_id == "cli":
            row["cli"] = cli_map
        if node_id == "scripts":
            roles = Counter(script_role(f.path) for f in node_files)
            row["script_roles"] = dict(roles.most_common())
            row["crontab"] = crontab_lines()
        if node_id == "routers":
            row["facade"] = {
                "path": facade,
                "imports": len(facade_targets),
                "loaded_by_files": len(facade_loaders),
                "note": (
                    "任何 `import open_composer.research.<x>` 都会先执行该门面，"
                    "从而加载它再导出的全部路由模块。"
                ),
            }
        node_rows.append(row)

    for row in node_rows:
        impact_ids = {entry["id"] for entry in row["impact"]}
        row["impact_labels"] = [n["label"] for n in node_rows if n["id"] in impact_ids]

    # ---- flows with resolved anchors -------------------------------------------------
    flow_rows = []
    for flow in FLOWS:
        steps = []
        for index, (node_id, title, file_path, symbol, detail) in enumerate(flow["steps"], 1):
            steps.append(
                {
                    "index": index,
                    "node": node_id,
                    "title": title,
                    "detail": detail,
                    "evidence": {
                        "file": file_path,
                        "line": resolve_symbol(file_path, symbol),
                        "expect": symbol,
                    },
                }
            )
        flow_rows.append(
            {"id": flow["id"], "title": flow["title"], "summary": flow["summary"], "steps": steps}
        )

    # ---- layout -------------------------------------------------------------------------
    width, height = 1500, 900
    col_x = [36, 336, 636, 936, 1236]
    node_w, node_h = 236, 74
    rows_per_col: Counter = Counter(n["layout"]["col"] for n in node_rows)
    for row in node_rows:
        col = row["layout"]["col"]
        count = rows_per_col[col]
        usable = height - 120
        gap = usable / count
        y = 90 + gap * row["layout"]["row"] + (gap - node_h) / 2
        row["pos"] = {"x": col_x[col], "y": round(y, 1), "w": node_w, "h": node_h}

    python_files = [f for f in files.values() if f.is_python and f.node != "tests"]
    summary = {
        "repo": "open-composer",
        "python_files": len(python_files),
        "python_loc": sum(f.loc for f in python_files),
        "frontend_files": sum(
            1 for f in files.values() if f.node == "dashboard" and not f.is_python
        ),
        "frontend_loc": sum(
            f.loc for f in files.values() if f.node == "dashboard" and not f.is_python
        ),
        "test_files": test_totals["files"],
        "test_functions": test_totals["functions"],
        "test_loc": test_totals["loc"],
        "first_screen_nodes": len(node_rows),
        "edges": len(edges),
        "import_edges": sum(1 for e in edges if e["kind"] == "import"),
        "flows": len(flow_rows),
        "entrypoints": len(entrypoints),
        "unreachable_python_files": sum(1 for f in python_files if f.path not in reachable),
        "unreachable_python_loc": sum(f.loc for f in python_files if f.path not in reachable),
        "cron_reachable_python_loc": sum(
            f.loc for f in python_files if "cron" in entries_for(f.path)
        ),
        "cli_only_python_loc": sum(f.loc for f in python_files if entries_for(f.path) == ["cli"]),
        "cron_entry_scripts": cron_scripts,
        "churn_since": CHURN_SINCE,
        "facade_loaded_by_files": len(facade_loaders),
        "facade_imports": len(facade_targets),
    }
    git_head = git_output(["rev-parse", "HEAD"]).strip()
    git_branch = git_output(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    model = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "git": {"head": git_head, "branch": git_branch},
        "generator": "scripts/build_codemap.py",
        "categories": CATEGORIES,
        "layout": {"width": width, "height": height, "columns": COLUMNS, "col_x": col_x},
        "summary": summary,
        "nodes": node_rows,
        "edges": edges,
        "flows": flow_rows,
        "_files": files,
    }
    return model


def node_fingerprints(files: dict[str, SourceFile]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[SourceFile]] = defaultdict(list)
    for source_file in files.values():
        grouped[source_file.node].append(source_file)
    out: dict[str, dict[str, Any]] = {}
    for node_id, node_files in sorted(grouped.items()):
        digest = hashlib.sha256()
        for f in sorted(node_files, key=lambda f: f.path):
            digest.update(f"{f.path}:{f.sha256}\n".encode())
        out[node_id] = {
            "files": len(node_files),
            "loc": sum(f.loc for f in node_files),
            "fingerprint": digest.hexdigest(),
        }
    return out


def render_html(model_json: str) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    safe_json = model_json.replace("</", "<\\/")
    return template.replace("__CODEMAP_JSON__", safe_json)


def public_model(model: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in model.items() if not k.startswith("_")}


def write_outputs(model: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = public_model(model)
    model_json = json.dumps(payload, ensure_ascii=False, indent=1)
    (OUT_DIR / "codemap.json").write_text(model_json + "\n", encoding="utf-8")
    html = render_html(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    (OUT_DIR / "codemap.html").write_text(html, encoding="utf-8")
    fingerprints = node_fingerprints(model["_files"])
    tree = hashlib.sha256()
    for f in sorted(model["_files"].values(), key=lambda f: f.path):
        tree.update(f"{f.path}:{f.sha256}\n".encode())
    lock = {
        "lock_version": 1,
        "generated_at": model["generated_at"],
        "git": model["git"],
        "generator": {
            "path": "scripts/build_codemap.py",
            "sha256": sha256_bytes(Path(__file__).read_bytes()),
            "template_sha256": sha256_bytes(TEMPLATE_PATH.read_bytes()),
        },
        "outputs": {
            "codemap.json": sha256_bytes((OUT_DIR / "codemap.json").read_bytes()),
            "codemap.html": sha256_bytes((OUT_DIR / "codemap.html").read_bytes()),
        },
        "inputs": {
            "file_count": len(model["_files"]),
            "total_loc": sum(f.loc for f in model["_files"].values()),
            "tree_sha256": tree.hexdigest(),
        },
        "counts": {
            "nodes": len(model["nodes"]),
            "edges": len(model["edges"]),
            "flows": len(model["flows"]),
            "test_functions": model["summary"]["test_functions"],
        },
        "nodes": fingerprints,
    }
    (OUT_DIR / "codemap.lock").write_text(
        json.dumps(lock, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# Verify
# --------------------------------------------------------------------------- #
def verify() -> int:
    problems: list[str] = []
    notes: list[str] = []
    json_path, lock_path, html_path = (
        OUT_DIR / "codemap.json",
        OUT_DIR / "codemap.lock",
        OUT_DIR / "codemap.html",
    )
    for path in (json_path, lock_path, html_path):
        if not path.exists():
            problems.append(f"missing output: {rel(path)}")
    if problems:
        print("\n".join(problems))
        return 1
    data = json.loads(json_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    node_ids = {n["id"] for n in data["nodes"]}
    if len(data["nodes"]) > MAX_FIRST_SCREEN_NODES:
        problems.append(f"first screen has {len(data['nodes'])} nodes (> {MAX_FIRST_SCREEN_NODES})")
    notes.append(f"nodes: {len(data['nodes'])} (limit {MAX_FIRST_SCREEN_NODES})")
    # every file path in nodes exists and is assigned to exactly one node
    seen_paths: dict[str, str] = {}
    for node in data["nodes"]:
        for entry in node["files"]:
            path = entry["path"]
            if not (ROOT / path).is_file():
                problems.append(f"{node['id']}: file missing {path}")
            if path in seen_paths:
                problems.append(f"{path} assigned to both {seen_paths[path]} and {node['id']}")
            seen_paths[path] = node["id"]
        for entry in node["tests"]:
            if not (ROOT / entry["path"]).is_file():
                problems.append(f"{node['id']}: test file missing {entry['path']}")
        for cfg in node.get("configs", []) + node.get("paths", []):
            if not (ROOT / cfg).exists():
                problems.append(f"{node['id']}: config/path missing {cfg}")
        for dep in node["upstream"] + node["dependencies"] + node["impact"] + node["pulls_in"]:
            if dep["id"] not in node_ids:
                problems.append(f"{node['id']}: unknown neighbour {dep['id']}")
    notes.append(f"files checked: {len(seen_paths)}")
    # edges
    for edge in data["edges"]:
        if edge["source"] not in node_ids or edge["target"] not in node_ids:
            problems.append(f"edge with unknown endpoint: {edge['id']}")
        for ev in edge["evidence"]:
            file_path = ROOT / ev["file"]
            if not file_path.is_file():
                problems.append(f"edge {edge['id']}: evidence file missing {ev['file']}")
                continue
            if ev["line"]:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                if ev["line"] > len(lines):
                    problems.append(f"edge {edge['id']}: {ev['file']}:{ev['line']} beyond EOF")
                elif edge["kind"] == "import" and ev["statement"] not in lines[ev["line"] - 1]:
                    problems.append(
                        f"edge {edge['id']}: {ev['file']}:{ev['line']} does not contain "
                        f"{ev['statement']!r}"
                    )
    notes.append(f"edges checked: {len(data['edges'])}")
    # flows
    for flow in data["flows"]:
        if len(flow["steps"]) < 3:
            problems.append(f"flow {flow['id']} has fewer than 3 steps")
        for step in flow["steps"]:
            if step["node"] not in node_ids:
                problems.append(f"flow {flow['id']} step {step['index']}: unknown node")
            ev = step["evidence"]
            file_path = ROOT / ev["file"]
            if not file_path.is_file():
                problems.append(f"flow {flow['id']} step {step['index']}: missing {ev['file']}")
                continue
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if ev["line"] > len(lines) or ev["expect"] not in lines[ev["line"] - 1]:
                problems.append(
                    f"flow {flow['id']} step {step['index']}: {ev['file']}:{ev['line']} "
                    f"does not contain {ev['expect']!r}"
                )
    notes.append(
        f"flows checked: {len(data['flows'])} ({sum(len(f['steps']) for f in data['flows'])} steps)"
    )
    # lock consistency against the current tree
    model = build_model()
    current = node_fingerprints(model["_files"])
    changed = [
        node_id
        for node_id, entry in lock["nodes"].items()
        if current.get(node_id, {}).get("fingerprint") != entry["fingerprint"]
    ]
    new_nodes = sorted(set(current) - set(lock["nodes"]))
    if changed or new_nodes:
        problems.append(
            "lock is stale for nodes: "
            + ", ".join(changed + new_nodes)
            + " (re-run scripts/build_codemap.py)"
        )
    for name in ("codemap.json", "codemap.html"):
        actual = sha256_bytes((OUT_DIR / name).read_bytes())
        if actual != lock["outputs"][name]:
            problems.append(f"lock output hash mismatch for {name}")
    if lock["generator"]["sha256"] != sha256_bytes(Path(__file__).read_bytes()):
        problems.append("lock generator hash differs from scripts/build_codemap.py")
    if lock["generator"]["template_sha256"] != sha256_bytes(TEMPLATE_PATH.read_bytes()):
        problems.append("lock template hash differs from scripts/codemap_template.html")
    notes.append(f"lock nodes: {len(lock['nodes'])}, tree sha {lock['inputs']['tree_sha256'][:12]}")
    print("codemap verify")
    for note in notes:
        print(f"  ok   {note}")
    for problem in problems:
        print(f"  FAIL {problem}")
    print("result:", "PASS" if not problems else f"FAIL ({len(problems)} problems)")
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="re-derive and compare with lock")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="output directory (default docs/codemap); use a sub-directory when several agents"
        " publish maps side by side",
    )
    args = parser.parse_args(argv)
    global OUT_DIR
    if args.out_dir:
        OUT_DIR = (ROOT / args.out_dir).resolve()
    if args.verify:
        return verify()
    model = build_model()
    if len(model["nodes"]) > MAX_FIRST_SCREEN_NODES:
        raise SystemExit(f"too many first-screen nodes: {len(model['nodes'])}")
    write_outputs(model)
    summary = model["summary"]
    print(
        f"codemap: {summary['first_screen_nodes']} nodes, {summary['edges']} edges, "
        f"{summary['flows']} flows, {summary['python_files']} python files / "
        f"{summary['python_loc']} loc, {summary['test_functions']} tests -> {rel(OUT_DIR)}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
