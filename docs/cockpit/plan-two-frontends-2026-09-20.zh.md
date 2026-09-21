# 两版前端：A 原生服务端渲染 / B Figma Make React — 2026-09-20

> 机主 2026-09-20：Figma Make 做到一半没额度，导出了代码（`Liquid Glass Material Editor _1_.zip`）；要求最终**两版都能看**：一版以 Figma 代码为底继续，一版我自己做、不参考它。
> 前提：`docs/plan-step-18-readonly-cockpit-2026-09-19.zh.md`（只读、无命令入口、全英文、§3.5 文字规则）与 `docs/cockpit/design-path-mvp-to-workbench-2026-09-20.zh.md`（苹果设计语言规则、每屏目标形态）全部继续有效。

## 1. Figma 导出物盘点

| 有 | 缺（App.tsx 引用但 zip 里没有） |
|---|---|
| `src/index.css`：系统色 token（浅/深）、`.glass`、`.num`（等宽数字）、`.section-cap`、两段动效 | `src/components/Shared`（`StatusDot` `MetricCard` `Row` `SectionCap` `QuotaBar` `fmtK`） |
| `src/App.tsx`：壳——44px 玻璃工具栏、256px 侧栏、340px 检视器、手机 Sheet + 浮动标签栏、⌘1–6 / ⌘F / Esc | `src/components/StatusStrip` |
| `src/screens/{Agents,Paper,Quota,Health,Lineage}.tsx`：主指标带 + 列表/表格 + 检视器 | `src/data/mock`（全部假数据） |
| Vite 8 + React 19 + Tailwind 4，`package.json` 无锁定的 npm 锁（只有 pnpm-lock） | `src/screens/Hypotheses.tsx`（默认屏） |

结论：不能直接构建；缺件都是可以按现有用法补写的小件。它的数据形状是编的，**只借结构和视觉，不借数据**。

## 2. 决定

| 版 | 路径 | 做法 | 服务端依赖 |
|---|---|---|---|
| **A · Native** | `/` | 现有 Jinja 模板 + 一套新 CSS 设计系统（design-path 路径 A），不看 Figma 代码 | 无变化 |
| **B · Figma** | `/v2/` | 以 Figma 代码为底：补齐缺件、删 `mock`、改读 JSON API；`vite build --base=/v2/` 一次性构建，产物提交进 `open_composer/cockpit/static/v2/` | 零 node（构建产物是静态文件） |
| 共用 | `/api/*.json` | 只读 JSON API，数据层不动，只加序列化；也是将来 SwiftUI（路径 C）的契约 | 无 |

两版并存到机主比较完为止；选定后另一版删除或降级为参考，不长期双维护。

## 3. 任务

### T11 · JSON API（先做，A/B 都不依赖它以外的东西）

- `open_composer/cockpit/api.py`：`to_jsonable(obj)`（dataclass → dict、`datetime` → ISO-8601 UTC、`Path` → 相对 repo 的字符串、tuple → list、`Enum` → value）。数据层已经过 `secret_scrub`，序列化层不再碰文本，但测试要用 token 形状正则扫一遍每个端点的输出。
- 端点（全部 GET，`Cache-Control: no-store`，`application/json`）：
  `/api/status.json`（顶栏：Claude 5h/7d 或原因、fresh 估算、agent 点、数据新鲜度、最近授权到期）· `/api/hypotheses.json` · `/api/hypotheses/{card_id}.json` · `/api/lineage.json` · `/api/agents.json` · `/api/agents/{agent_id}.json` · `/api/paper.json` · `/api/paper/{strategy}.json` · `/api/quota.json` · `/api/health.json`。
  参数校验与 HTML 路由完全相同（同一个校验函数），404 不 500。
- `app.py`：若 `static/v2/index.html` 存在则 `app.mount("/v2", StaticFiles(directory=..., html=True))`（T12 的产物落地后自动生效；T12 不改 `app.py`）。
- 测试：路由遍历仍只有 GET；每个端点 200 且可 `json.loads`；`datetime` 无 naive；输出无 token 形状字符串；`/api/agents/{bad}` 404。
- 验收：`curl -s 127.0.0.1:8770/api/status.json | python -m json.tool | head`，其余端点 200。

### T9 · A 版设计系统 pass（T11 之后，与 T12 并行；只改 `templates/`、`static/css/`、`app.py` 的模板上下文）

按 design-path §1–3 逐条落地，不参考 Figma 代码：

1. **Token 层**（`cockpit.css` 重写）：系统语义色（label/secondary/tertiary、grouped background、separator）浅深自动；四个状态色只用于圆点；一个 tint 只用于选中与链接；SF 字体栈；`font-variant-numeric: tabular-nums`；字号阶梯 Large Title 28 / Title 20 / Headline 15 / Body 14 / Footnote 12 / Caption 11；同心圆角：容器 16、内部 10；`prefers-reduced-transparency` 时 `.glass` 退化为不透明。
2. **两种壳**（容器查询 / 断点 768）：桌面 = 玻璃侧栏 + 内容 + 右侧检视器；手机 = 浮动玻璃标签栏（Hypotheses · Agents · Paper · Quota · More）+ 底部 Sheet。玻璃只在壳上；内容层永远不透明；不许玻璃叠玻璃。
3. **状态带**：单行，Claude 5h/7d 两条细条或一个原因芯片、fresh 估算、agent 圆点、数据新鲜度圆点、最近到期倒计时。现有两行文字删掉。
4. **每屏 = 主指标带 + 一张列表/表格 + 检视器**：检视器由 HTMX 请求同一路由加 `?partial=1` 返回片段（桌面塞右栏、手机塞 Sheet），不跳页；`/card/{id}`、`/paper/{s}`、`/agents/{id}` 三个详情路由都支持 `partial`。
5. **文字**：删所有说明段落与 join 警告面板（警告进 Health）；标签是名词；空即 `None` / `No data yet`；时间一律相对（`2m ago`）+ `title` 属性放绝对值；窄列只放状态词；kill switch 原因截 1 行。
6. **动效只有三种**：标签栏滚动收缩、检视器滑入、实时行淡入。
7. 验收：`tests/test_cockpit_app.py` 的 GET-only、英文 chrome 测试通过；headless Chrome 截 12 张（1440 / 390 × 六屏）到 `docs/cockpit-screens/a/`；手机 390 宽首屏不横向滚动、第一眼是数字。

### T12 · B 版（T11 之后，与 T9 并行；只碰 `frontend/cockpit-v2/**` 与 `open_composer/cockpit/static/v2/**`）

1. 源码已在 `frontend/cockpit-v2/`（2026-09-20 从 zip 导入，去掉了 `.figma/`、`src/assets/`、`src/imports/`、Figma 自带的 `AGENTS.md`/`CLAUDE.md`）；`vite.config.ts` 11.7 KB 是 Figma 预览环境的配置，精简到 react + tailwind 两个插件。
2. 补 `components/Shared.tsx`（按五屏的用法反推 props）、`components/StatusStrip.tsx`（读 `/api/status.json`）、`screens/Hypotheses.tsx`（泳道列表 + 检视器：卡片正文、criteria vs result、有则画安慰剂直方图、血统邻居）。
3. 删 `data/mock`，新建 `api.ts`：`useJson(url, refreshMs)`（`fetch` + `AbortController` + 30 s 轮询；agent 详情用 `EventSource('/agents/{id}/stream')` 追加行）。每屏的数据形状以 T11 的真实输出为准，**不保留任何编造字段**（如 `freshTokensToday` 若 API 没有就删，不造）。
4. 文字规则同 §3.5：全英文、名词、四个状态词、空即 `None`；把 Figma 代码里的句子式文案删掉。
5. 构建：`pnpm install --frozen-lockfile`（机上有 pnpm 11，按 zip 自带的 `pnpm-lock.yaml`，网络一次）→ `scripts/run_capped.sh --mem 1.8G -- npx vite build --base=/v2/ --outDir ../../open_composer/cockpit/static/v2 --emptyOutDir`；产物提交；`node_modules/` 进 `.gitignore`；`Makefile` 加 `cockpit-v2` 目标。
6. 验收：`curl -s 127.0.0.1:8770/v2/ | head -3` 为构建后的 `index.html`；六屏在 1440 / 390 各截一张到 `docs/cockpit-screens/b/`；页面无 `mock`、无假数字；构建产物 < 400 KB gzip 前。

## 4. 分工（2026-09-20 机主定）

前端设计与实现——设计系统、模板、组件、屏——由主会话（Fable）亲自做；Sonnet 只接与模型无关的机械活：T11 JSON 序列化、pnpm/vite 构建管线、截图、测试脚手架、数据层性能修补。理由：上一版由执行器按简报做出来的是"功能 MVP"，机主看重前端质量。

## 5. 顺序与并发

T10（Sonnet，进行中，改 `app.py`/`quota.py`/`agents.py`/模板）→ **T11**（Sonnet）→ **T9 与 T12 由我在独立 worktree 里做**（先 A 后 B；预览实例跑在 8781，不动主 checkout 的服务）→ 机主在手机和电脑上比较 `/` 与 `/v2/` → 选定后合并（保留另一版里更好的局部想法，删代码）。

## 6. 不做的事

- 不在服务端引入 node 运行时；B 版只是静态产物。
- 不为 B 版新增任何写接口；`/api/*` 与 HTML 路由共用同一套只读数据层和校验。
- 不把 Figma 的假数据形状反向塞进数据层。

## 7. 状态（2026-09-21）

| 任务 | 状态 | 落点 |
|---|---|---|
| T11 JSON API | 完成 | `open_composer/cockpit/api.py`，十个 `/api/*.json`，`tests/test_cockpit_api.py`；`/v2/` 在构建产物存在时自动挂载 |
| T9 A 版 | 完成，已上线 `/` | `open_composer/cockpit/{templates,static/css,static/js}`；截图 `docs/cockpit-screens/a/` |
| T12 B 版 | 完成，`/v2/` | `frontend/cockpit-v2/src/**`（补齐 `components/Shared.tsx`、`components/StatusStrip.tsx`、`screens/Hypotheses.tsx`、`api.ts`，删 mock，五屏全部改读真实形状）；产物 `open_composer/cockpit/static/v2/`（js 258 KB / gzip 77 KB，css 17 KB）；`make cockpit-v2` 重建；截图 `docs/cockpit-screens/b/` |
| 顺手修的 | 完成 | Claude 用量探测：过期/无权限的 token 记住指纹不再重发（6h 或 token 变更），429 按 `Retry-After` 退避且一个 429 结束整轮（之前每分钟 2 个 401 换来 429）；agent 时间线里 base64 截图块改显示 `[image]` |

### 怎么比

同一台机、同一份数据：`https://dsh.hadan.blog/`（A）与 `https://dsh.hadan.blog/v2/`（B），手机和电脑各看一遍；A 右下角有 `v2` 链接，B 侧栏底部有 `Native view` 链接。

| | A · Native | B · Figma 续作 |
|---|---|---|
| 壳 | 玻璃侧栏 216 + 内容 + 检视器 392；手机浮动标签栏 + `<dialog>` 抽屉 | 玻璃工具栏（标签在栏内）+ 侧栏 240 + 检视器 372；手机浮动标签栏 + 底部 sheet |
| 渲染 | 服务端 Jinja，一个 12 KB 脚本；无 JS 也能看 | React 单页，首屏 77 KB gzip；必须有 JS |
| 刷新 | 整页刷新 + agent SSE | 每屏 20–60 s 轮询 JSON + agent SSE；相对时间每 30 s 重算 |
| 过滤 | 当前屏文本过滤 | 当前屏文本过滤；血统图里不匹配的节点淡出 |
| 深链 | `/card/<id>`、`/agents/<id>`；检视器用 `#/path` | `#/hypotheses/<id>`、`#/agents/<id>`、`#/paper/<s>`、`#/health/<job>` |
| 改一处要动什么 | Python + 模板 + CSS | TypeScript + 重新 `make cockpit-v2`（node 22 + pnpm） |

我的倾向：**A 做主版本**——一套工具链、无构建步骤、首屏快、无 JS 也可读，长期只维护一份；把 B 里更好的两处搬回 A：主指标卡可点击跳到对应分组，血统图按过滤词淡出不相关节点。若机主更喜欢 B 的观感，则反过来：B 做主，A 保留为无 JS 后备。定下来之前两版并存，数据层与 API 不变。
