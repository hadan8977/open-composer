# OpenCode Step5：安装、兼容验收与T03原断点恢复

机主明确授权（2026-10-13）：“我发现opencode可以免费用step5，性能还是可以的，你可以装上这个，继续跑之前ds不够的任务”。本授权允许新免费Step5通道用于原任务，优先于旧“DS parked不换provider”对本次替代通道的限制；旧DS接口本身继续parked，不读取新token、不重试其耗尽额度。不得启用付费、自动充值或自动换付费模型。

这是完整执行任务：安装→核实真免费模型→接入原公开文本抽取→真实小批质量验收→继续有界未完成工作→可接续结果。Root/Astra最后核对质量与结论。由一个Sol/xhigh owner负责常规实施/修复，勿派子代理/新平台/新定时研究轮。6.1 Sol正容量错误，执行使用机主已同意的gpt-6-sol/xhigh/full-access。

## 来源与实际入口

- 官方已实际打开 https://opencode.ai/v2/docs/console/models/：Step 5 Preview Free，model id `step-5-preview-free`，列为限时免费，chat-completions兼容入口。该页面同时有付费账户流程；免费模型是否免登录必须用官方CLI/源码和实际无害调用核实，不能据“Free”推断无需认证。
- 安装/CLI文档 https://opencode.ai/docs/ 和 /docs/cli/ 已打开。只从官方发行或官方包安装；查当前可用版本与机器架构，保留版本/来源/校验。优先用户本地bin，禁止远程脚本不看就pipe到shell，不修改系统代理/其他运行session。
- 任务是 `scripts/t03_llm_extract.py` 年报客户关系抽取（不是GRPO或收益回测），及后续明确依赖它的关系输入工作。查看 `scripts/t03_retry.py`、`scripts/score_earnings_text.py` 的接口和原恢复/失败证据；不要读印密钥。原880calls/rolling5h、flock、done-accession、请求ledger与原failure_state均有既有实现。
- 当前原始片段在 `data/features/economic_links/_snippets`，已抽取在 `_llm`。新旧同accession/多CIK与收入分母问题参照 `reports/research/program/entity-denominator-repair-20261011/current-state.json` 与其实际证据；不可把LLM判断当永久证券身份或集团收入分母认证。

## 实施和权限

1. 检查是否已装OpenCode，安装官方CLI并验证版本和实际模型ID。先验证免费通道的真实请求。若必须用户登录/现有账号授权，准备好其余可验收工作，回报精确阻塞；不创建账户、输入支付信息、自动充值、读取其他凭证来绕过。
2. 只向新provider发送这个任务所需的公开SEC片段和固定抽取指令。若使用OpenCode run，放在隔离的公共输入scratch中，禁用工具/仓库探索/任意命令，避免默认读取项目AGENTS、源码、私有配置和凭证；不要在repo cwd把它当全能coding agent开跑。若官方免费API路径可合法直接调用，可用最薄适配避免每篇启动完整agent，但仍完成用户要求的CLI安装。不改现有付费scorer全局配置，不把DS额度错误伪装为恢复成功。
3. 保持原抽取问题和输出字段；新provider/model/模型实际返回名/版本可核边界、prompt/hash、原snippet/input哈希、调用时间/token、终态和费用必须分开记录。`preview`无法核成不可变版本时如实标记。原DS文件、failure_state和全部ledger不清零，不把新输出伪装成旧DS。共享锁与跨旧/新已完成accession去重继续有效。新输出隔离research lane，未经正确下游适配和验收不混入既有交易特征。
4. 有限兼容/质量小批：最多20实际免费请求（含最多2次无害格式探针；失败亦计），以现有公开片段中的命名客户、匿名/否定、政府、分部/集团收入、应收账款和年度混杂等情况选固定样本；先冻结样本与原文。检查schema、精确quote/实体身份、客户方向、pct与basis/年、lower_bound/否定、无依据不猜。旧DS输出不是金标准；以原文判。用少量真正能改变接续判断的离线测试，禁止镜像实现堆测试。
5. 质量通过且请求为0费用、没有鉴权/限流/条款阻塞后，按同一逻辑接续最多100条原本未完成记录，保持单进程、原共享880/5h上限（本任务各阶段全计入，不给每阶段重置）。本批源/格式验证与实际结果交Root；这100条不是新经济trial/Alpha，也不是自动接收公司身份。Root验收后可复用实现继续清理剩余backlog，无需重新装或另造恢复平台。若试批出现实质错误先定位/隔离并交决定，不蒙混 bulk。
6. 对免费服务429/容量/认证失败保留类型与已有retry-after，最多一次有依据的短暂重试；额度/权限耗尽不循环、不自动换模型/provider。保留部分输出、已用调用与断点。不得继续旧DS探测、改其他科学包、broker/生产/订单、付费或Hadan。

## 资源与交付

Linux留约500MiB，执行前用现有memory admission；安装/CLI和批次用原capped工具，按实际测量选择900MiB或更小，不能占全机。初始安装/适配与验证推进到决定性结果为止；本次实际provider调用最多120，累计原rolling880保持，单批实际调用墙钟上限45分钟，失败/重启累计不清零。公网只取官方软件/文档与该免费推理，不额外SEC续采。原source2210封存、FNSPID耗尽及Modal$25均不动。

只在需要的非生产代码上窄改，注意当前工作树有他人改动；不得git add -A或push。必要时隔离worktree，保留最小diff、实际定向测试与lint。不调用不相关全仓重计算/模型。

目录 `reports/research/program/day-goal-20261013/opencode-step5-recovery/`：一个current-state.json，安装/来源与免费模型实证、小批原文质量结果、实际恢复计数/失败/命令/费用与续跑入口。记录已安装与已接入与已成功抽取三种不同状态。报告provider免费有时限，调用成功不证明Alpha/PIT。普通修补你做到底；遇真正身份验证/付费或改变科学问题才回Root。只发一次完整结果或重大阻塞，不heartbeat/LLM轮询。
