# Open Composer 结构、效率与冗余审查

日期：2026-05-17

## 审查方法

本次审查参考三类成熟标准：

- ISO/IEC 25010：以功能适合性、性能效率、可维护性、可靠性、安全性、可移植性作为产品质量维度。
- NIST SSDF：以安全开发、依赖与配置、可审计变更、默认安全门禁作为补充视角。
- Google Engineering Practices：以可读性、局部性、测试覆盖、可回滚和变更最小化作为代码审查原则。

结合 Open Composer 的产品定位，本次增加四个本项目专属检查维度：

- `StrategySpec` 是否仍是策略行为源头。
- CLI plus files 是否仍是第一产品表面。
- LLM、新闻、事件、宏观数据是否通过可回放 packet 和显式 evidence 进入交易逻辑。
- Codex/Cloud Code 是否通过技能、repo check、capability registry 和报告工件放大优势，而不是制造不可审计状态。

## README 参考项目

本轮 README 重构参考了高质量金融、量化和 AI 工具仓库的共同结构：

- OpenBB：README 先讲产品定位、核心能力、安装入口和文档导航，复杂用法进入文档站。
- Freqtrade：README 用少量命令展示 Docker/安装入口，把策略配置、风险和高级参数放入 docs。
- QuantConnect Lean：README 强调引擎定位、核心能力、安装/运行入口、文档和许可，而不是塞满每个命令。
- NautilusTrader：README 先给系统定位、安装方式、文档入口和社区/贡献路径，详细 API 在 docs。
- Jesse：README 强调产品价值、安装入口、文档和风险边界。

参考链接：

- https://github.com/OpenBB-finance/OpenBB
- https://github.com/freqtrade/freqtrade
- https://github.com/QuantConnect/Lean
- https://github.com/nautechsystems/nautilus_trader
- https://github.com/jesse-ai/jesse

提炼出的规则：

- README 只做“入口页”：定位、为什么存在、5 分钟启动、能力地图、风险边界、文档索引、License。
- 命令级细节进入 `docs/user-guide.md`、本地部署细节进入 `docs/setup-local.zh.md`、远程部署进入 `docs/remote-dashboard-deploy.zh.md`。
- 产品体验要能兑现 README 的承诺：新增 `make start`，让本地启动可以是一个稳定入口，而不是让用户复制长串命令。
- repo check 应保护 README 的入口质量、License、当前文档集合和用户指南里的研究控制，而不是逼 README 重新变长。

## Checklist

### 结构与文档

- 根目录是否只保留必要入口：README、AGENTS、Makefile、pyproject、脚本、配置模板。
- `docs/` 是否只保留当前产品文档，历史过程文档不再混入当前路线。
- `reports/` 是否只保留必要示例报告，运行产物默认被 ignore。
- `.agents/skills` 与 `.claude/skills` 是否一致。
- Dashboard 是否保持为读模型和受控操作面，而不是第二真相源。

### 代码与架构

- `StrategySpec`、capability registry、feature packet、promotion/readiness 是否构成单一主链路。
- 研究模块是否按职责拆分，避免把一个入口变成不可维护的大模块。
- Python reference engine 与 NautilusTrader adapter 是否保持参考路径/事件驱动路径分工。
- Vercel BFF、VPS daemon、local CLI 是否分工清楚，避免远程层执行长任务。

### 效率与轻量化

- 大体积本地目录是否被 ignore：`.venv`、`dashboard/node_modules`、`data/cache`、运行报告。
- 默认样本 workflow 是否无需外部凭证即可跑通。
- 重型研究命令是否有 bounded search、top-k、报告工件和成本字段。
- 重复检查是否能通过 `oc repo check`、`oc capability test`、pytest 聚合，而不是人工重复确认。

### 安全与质量

- `.env`、`.codex/config.toml`、真实数据 cache 是否不进入 Git。
- paper 自动化是否默认被 readiness、kill switch、显式确认阻断。
- LLM/另类数据是否检查 visible_at、published_at/fetched_at、input_hash、prompt_hash 和 evidence。
- 样本、fixture、fallback 是否不能升级为 paper-ready 市场证据。

## 审查发现

### 已清理或已修正

- 删除旧过程文档 `docs/quant-product-hardening-plan-2026-05-16.zh.md`。该文档的有效内容已被 `docs/research-contract-p0-p2-plan-2026-05-17.zh.md` 和当前代码实现取代。
- 更新 `open_composer/repo_check.py` 的当前文档白名单，避免把 P0-P2 研究合约计划误判为历史文档。
- 更新 README Project Docs，把 P0-P2 研究合约计划纳入当前文档集合。
- 更新 repo check 测试夹具，确保文档边界变更可被测试覆盖。
- 重构 README 为产品入口页，并把命令级流程沉到 `docs/user-guide.md`。
- 新增 `make start`，把本地启动路径收敛为一个命令。
- 新增 MIT `LICENSE`，并把 license 存在性纳入 repo check。

### 保留但需要继续关注

- `.agents/skills` 与 `.claude/skills` 内容重复，但这是 Codex 与 Claude Code 双入口兼容要求；目前由 `scripts/sync-agent-skills.py` 和 `scripts/check-agent-parity.py` 管理，不建议删除。
- `dashboard/` 与 `open_composer/dashboard/` 看似重复，但前者是 Vercel/React BFF UI，后者是本地 Python catalog/server/read model；职责不同，不建议合并。
- `reports/research/` 中保留少量示例报告，是 Dashboard catalog 和产品审查的样例证据。新运行产物仍应被 ignore。
- 本地 `.venv`、`dashboard/node_modules`、`data/cache` 占用空间大，但均未跟踪，属于工作环境和缓存，不应作为代码清理提交的一部分。

### 当前主要问题

- `open_composer/research/` 中部分研究模块较长，例如 intraday rotation、promotion、rotation、exposure switch。短期不建议机械拆分；中期应抽出共享的 scoring、walk-forward、report rendering 和 data profile 工具，减少重复实现。
- Dashboard catalog 与 HTML 渲染模块较长。下一阶段可以把 model extraction、classification、HTML rendering 分层，降低单文件维护成本。
- repo check 之前只识别旧文档边界，说明“治理文档白名单”需要随关键产品计划同步更新。
- `data/cache` 已达到约 146M；本轮已新增显式 `oc cache status` /
  `oc cache clean` 管理入口，后续可继续细化到按 provider/symbol/timeframe
  清理。

## 建议计划

### P0：保持当前文档和自检门干净

- 当前已执行：删除过时过程文档，更新 README 与 repo check 白名单。
- 后续规则：新增当前路线文档时，必须同步 README Project Docs 和 repo check。

### P1：轻量化运行产物管理（基础入口已完成）

- 已增加 `oc cache status` / `oc cache clean`，用于展示和清理 `data/cache`
  与 generated reports，并用 `--apply` 显式确认真实删除。
- 保留 `data/sample` 与 capability fixtures，不清理可复现样本。
- 后续可扩展 provider/symbol/timeframe 级别筛选。

### P2：研究模块去重复

- 提取通用 walk-forward split、cost sweep、candidate scoring、research manifest 写入工具。
- 先从 promotion、exposure_switch、llm_exposure_switch、rotation 中抽取重复逻辑，避免大规模重构。

### P3：Dashboard 模块降复杂度

- 将 `dashboard/catalog.py` 拆成 file readers、classifiers、view model builders。
- 将 `dashboard/html.py` 的渲染片段组件化，保持 Python fallback dashboard 可读。

## 本轮结论

Open Composer 当前结构仍符合产品定位：文件优先、StrategySpec 为源头、CLI 为第一界面、Dashboard 为读模型、远程模式为 BFF/daemon 分离。最值得立即清理的是过时文档和自检白名单漂移；最值得后续优化的是研究模块重复和缓存管理，而不是删除功能模块。
