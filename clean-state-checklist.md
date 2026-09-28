# 干净状态检查清单

> 每轮会话结束前逐项勾选。任一项未完成，视为仓库处于不干净状态，需在 session-handoff.md 中显式记录。

## 代码与测试

- [x] 标准启动路径 `./init.sh` 仍可运行
- [x] 标准验证路径（后端 `pytest`、前端 `npm run build`）仍可运行
- [x] 没有半成品功能处于未记录状态（未完成的功能已在 feature_list.json 标注）
- [x] 没有为"看起来完成"而删除或削弱测试

## 状态同步

- [x] 当前进度已记录到 `claude-progress.md`（新增 Session 026 记录）
- [x] `feature_list.json` 的功能状态真实反映了 passing / in_progress / not_started 边界
- [x] `feature_list.json` 的 `last_updated` 已更新
- [x] 已完成功能的 `evidence` 字段已填证据（验证命令 + 结果）

## 设计约束未违反

- [x] 风险概率经 RiskProvider 抽象（未直接 hardcode）
- [x] AI 话术失败有降级到模板（未裸抛异常阻断催收）
- [x] 任务生成有幂等控制（batch_id+order_id+day_offset；task-003 单活跃任务同区间幂等）
- [x] 催收触发条件=到达时点且仍未支付（未对已支付生成任务）
- [x] 无可推导内容被存入 memory（架构/代码模式已在仓库中）

## 交接就绪

- [x] 需要简短交接时 `session-handoff.md` 已更新
- [x] 下一轮会话无需人工修复即可继续（git 状态干净 / 脏状态已记录）
