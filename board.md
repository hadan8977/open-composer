# Research decisions

| Round | Direction | Decision | Evidence |
|---|---|---|---|
| codex-integration-20261028 | martin_research_restart_20261028 | continue | research/martin_research_restart_20261028/runs/codex-integration-20261028/run.json |
| opportunity-audit-retry-20261028 | martin_research_restart_20261028 | branch | research/martin_research_restart_20261028/runs/opportunity-audit-retry-20261028/run.json |
| allocation-plan-20261028 | martin_causal_allocation_20261028 | continue | research/martin_causal_allocation_20261028/runs/allocation-plan-20261028/run.json |
| allocation-implementation-20261028-1 | martin_causal_allocation_20261028 | continue | research/martin_causal_allocation_20261028/runs/allocation-implementation-20261028-1/run.json |
| allocation-implementation-20261028-2 | martin_causal_allocation_20261028 | park | research/martin_causal_allocation_20261028/runs/allocation-implementation-20261028-2/run.json |
| 2026-10-28 restructure | project | 既有改造已核实接收；研究进展见各轮，BASE仍待11月输入，A/B关闭 | docs/restructure-progress.zh.md |
| mechanisms-20261102-2 | cross_asset_mechanisms_20261102 | park executed E/A/F/V/P/D=46/40/0/2/0/46 tok=5896119 s=997 | research/cross_asset_mechanisms_20261102/runs/mechanisms-20261102-2/run.json |
| mechanisms-20261102-1 | cross_asset_mechanisms_20261102 | 1个条件结论，23机制；同风险增量 $7557/$7376，区间含零；paper=0；tok≥18.36M；约63分钟；已续接归因 | research/cross_asset_mechanisms_20261102/runs/mechanisms-20261102-1/run.json |
| mechanisms-20261102-3 | cross_asset_mechanisms_20261102 | park executed E/A/F/V/P/D=128/170/0/0/0/128 tok=12668809 s=1991 | research/cross_asset_mechanisms_20261102/runs/mechanisms-20261102-3/run.json |
| mechanisms-20261102-4 | cross_asset_mechanisms_20261102 | park executed E/A/F/V/P/D=16/50/0/0/0/16 tok=6955989 s=1092 | research/cross_asset_mechanisms_20261102/runs/mechanisms-20261102-4/run.json |
| mechanisms-20261102-5 | residual_momentum_attribution_20261102 | park executed E/A/F/V/P/D=16/8/0/4/0/? tok=10379817 s=1453 | research/residual_momentum_attribution_20261102/runs/mechanisms-20261102-5/run.json |
| model-completion-20261102-1 | martin_model_completion_20261102 | branch executed E/A/F/V/P/D=1/4/2/4/0/65 tok=100940055+? active_s=24785 wall_s=58594 | research/martin_model_completion_20261102/runs/model-completion-20261102-1/run.json |
| mechanisms-20261102-6 | reversal_long_side_20261102 | park executed E/A/F/V/P/D=12/86/0/4/0/20 tok=34474928+? active_s=4350 wall_s=21092 | research/reversal_long_side_20261102/runs/mechanisms-20261102-6/run.json |
| mechanisms-20261102-7 | peer_earnings_increment_20261103 | park 接收恢复；ME−MP同风险−$4819/−$4079/−$3551/−$3824；E/A/F/V/P=20/141/0/14/0；tok≥1645291+?；原CLI失败保留；下一题已派未启动 | research/peer_earnings_increment_20261103/runs/mechanisms-20261102-7/lead_recovery/decision.json |
| model-completion-20261102-2 | martin_tail_targets_20261103 | park executed E/A/F/V/P/D=1/4/4/4/0/? tok=14183158+? active_s=2454 wall_s=23928 | research/martin_tail_targets_20261103/runs/model-completion-20261102-2/run.json |
| momentum-attribution-20261103-1 | momentum_benchmark_attribution_20261103 | interrupted_or_failed executed E/A/F/V/P/D=?/?/?/?/?/? tok=? active_s=1 wall_s=? | research/momentum_benchmark_attribution_20261103/runs/momentum-attribution-20261103-1/run.json |
| momentum-attribution-20261103-2 | momentum_benchmark_attribution_20261103 | park executed E/A/F/V/P/D=4/16/0/0/0/18 tok=5744363 active_s=2106 wall_s=2105 | research/momentum_benchmark_attribution_20261103/runs/momentum-attribution-20261103-2/run.json |
| model-completion-20261102-3 | martin_funded_continuation_20261103 | park executed E/A/F/V/P/D=1/10/40/10/0/? tok=92148400+? active_s=39784 wall_s=104611 | research/martin_funded_continuation_20261103/runs/model-completion-20261102-3/run.json |
| state-exit-20261104-1 | martin_state_exit_20261103 | owner_paused 状态16504/训练16354/空150；fits3，187日账户4；本地全停、无自动续跑；最终解释/Lead未接收；paper未动 | research/martin_state_exit_20261103/runs/state-exit-20261104-1/owner-pause-checkpoint.json |
| paper-restore-20261109 | paper_ops_restore | 六策略挂死修复+重启(2/6策略当日成交)、ETF提交DST窗口修复(00:0x UTC)、网站投影 10-26→11-06 连续、H5契约拒绝4条已记录 | reports/ops/paper-restore-20261109.zh.md |
| backtest-running-20261109 | running_paper_sleeves_backtest | ETF四sleeve回测: 2026YTD S1+26.1%/S2+20.1%/S3+63.2%/C2+23.4%, 9/1起 -2.8/-7.5/-16.7/+1.9%；C2复算卡片1.61 vs 1.60；六策略无合法YTD回放(仅当期模型) | reports/backtests/running-sleeves-20261109.zh.md |
| h5-symlink-fix-20261110 | paper_ops_h5_repair | H5拒单真因=disk-half-recovery符号链接破坏绑定(非10-16网格)；回填1文件后支撑可算至11-09；checked()给出可读原因；在用147条绑定100%通过；H5链11-11恢复 | reports/ops/h5-symlink-diagnosis-20261110.zh.md |
| h5-formation-gap-20261110 | paper_ops_h5_gap | H5阻塞=漏掉2026-11-06形成(网格每5交易日,只能在当天构建)；漏掉的组合为XYL/URI/IDXX/FISV/OKE,机会成本约+$390~590；链条预检通过,11-16恢复 | reports/ops/h5-formation-gap-20261110.zh.md |
| ytd-splice-20261110 | paper_perf_splice | 接着归档算: S1+26.1/S2+20.1/S3+63.2/C2+22.8(YTD); 六策略拼接 +33.9/+26.2/+45.0/+46.7/+38.3(缺14日); lane与引擎9月前逐日一致 | reports/backtests/paper-ytd-splice-20261110.zh.md |
| h5-recovered-20261110 | paper_ops_h5_recover | 开盘前恢复: 按11-06原始vintage补算漏掉形成(IDXX/OKE/XYL/URI/FISV,K=5)→装为held指令→回滚LSTM基线重跑当日报文(六目标全出,blocked={})→修正hold不收敛(BASE/H5/12子账本翻rebalance,服务自验16本通过) | reports/ops/h5-recovered-20261110.zh.md |
| gap-closure-20261110 | paper_ops_gap_record | 缺口界定: 数据/估值不缺,缺 11-05/06/09 执行与三份报文；生成 reconstruction.json 标注 not_a_dated_packet；11-09 反事实 +1.95%(+$390) | reports/ops/six-continuity-gap-explained-20261110.zh.md |
| paper-continuity-20261110 | paper_ops_guards | 装2条守护: --health每10分钟(心跳>900s或单元非active则重启,≤3次/时,告警) + --refresh每日00:25 UTC用官方启动器补跑当日报文;演练:stop→拉起、SIGSTOP→重启均恢复 | reports/ops/paper-continuity-guards-20261110.zh.md |
| automation-20261110 | paper_ops_automation | 网站发布改自动(2条cron,幂等重算,发布券商最新已发布日;Alpaca权益滞后1日) + 告警接邮件(去重6h,测试已发) + hold不收敛根治评估(B→A两步灰度,未实施) | reports/ops/paper-automation-20261110.zh.md |
| repo-audit-20261110 | project_repo_audit | 代码地图重建PASS(19节点195边5流程) + 体检:研究产物1.80M行占77%/未推送896/未跟踪12GB/56符号链接/oc冷启5.7s;与09-14评估对照:结构问题未动 | reports/harness/repo-audit-20261110.zh.md |
