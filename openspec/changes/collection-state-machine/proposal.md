## Why

当前系统没有 Order 维度的催收状态：轮次隐含在 Task.day_offset 里，催收员和监督员无法直观看到「这笔订单现在催到第几轮、是否已催通」。回填结果分五类（PAID/PROMISE/DISPUTE/LOST_CONTACT/OTHER）语义含糊，无法表达「该轮是否真正接通」这一催收核心事实。本改造引入 Order 维度的催收状态机（无需催收/待催收/已催收/终态），把回填结果收敛为「未接通/已接通」两分类，让任务生成、分配、监督都围绕「订单当前催到哪一轮、接通没有」这一事实驱动，使每天的任务清单与催收进度对业务真正可读、可追踪。

## What Changes

- **Order 新增 `collection_state` 催收状态机字段**：无需催收（NO_NEED）/ 待催收（PENDING_COLLECTION）/ 已催收（COLLECTED，按轮次）/ 终态（FINALIZED，轮次耗尽或已支付停催）
- **导入时按中标日预设 collection_state**：导入待支付订单时，若 `win_bid_date + 首轮 day_offset <= today` 则预设「待催收」，否则预设「无需催收」
- **跑批按状态机推进**：扫描待催收/已催收且仍待支付的订单，命中下一轮 day_offset → 推进 collection_state、生成/激活当轮 Task；未完成任务保留原 assignee
- **回填结果改为两分类**：未接通（UNREACHED，该轮仍待催收，同日可反复重试）/ 已接通（REACHED，填自由文本反馈，该轮算已催收，collection_state→已催收）**BREAKING**
- **已支付导入回写**：pay_status=PAID 时同步 collection_state→终态 FINALIZED，未完成待催收任务标记 CANCELLED
- **轮次耗尽终态**：配置的所有催收轮次都催完且仍待支付 → collection_state→终态 FINALIZED，等支付或人工介入
- **监督员视图增强**：按 collection_state 过滤 + 各催收员当天完成进度（已接通/未接通/待处理计数）
- **任务分配保持档内负载均衡**（现状），跑批对昨天未完成的 IN_PROGRESS 任务保留 assignee 不重分

## Capabilities

### New Capabilities
- `task-engine`: 催收任务引擎——Order 催收状态机推进、按轮次生成/激活任务、档内负载均衡分配、两分类回填推进状态、跑批保留未完成任务 assignee

### Modified Capabilities
- `data-ingestion`: 待支付订单导入时按中标日 + 首轮 day_offset 预设 Order.collection_state 初始值
- `risk-engine`: 催收轮次配置（collection_schedules）作为状态机推进时点的来源，跑批按各轮 day_offset 推进 collection_state

## Impact

- **后端模型**：Order 新增 collection_state 字段 + Alembic 迁移；Task.result 枚举值重定义（BREAKING）；TaskResult.result 枚举值重定义
- **后端服务**：`services/task_engine/batch.py`（状态机推进+任务生成）、`assignment.py`（保留未完成 assignee）、`state.py`（回填两分类推进状态）、`reassign.py`（改派边界）
- **后端 API**：`/api/tasks` 回填端点入参改变（BREAKING）；监督员进度端点新增/扩展
- **前端**：Workbench 任务列表/详情展示 collection_state 与轮次；回填表单改为「未接通/已接通 + 反馈文本」；Supervisor 加催收状态过滤与完成进度
- **测试**：test_task_generation / test_workbench / test_e2e / test_reassign / test_supervisor 重写适配新状态机与两分类回填
- **数据迁移**：现有 Order 补 collection_state 初始值（按 win_bid_date + 首轮 day_offset 回填），现有 Task.result 旧值映射到新两分类（PAID/OTHER→REACHED，其余→UNREACHED，仅历史数据兼容，非业务精确）
