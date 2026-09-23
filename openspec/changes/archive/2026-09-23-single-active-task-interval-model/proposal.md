## Why

当前任务模型是「多轮并存」：一个订单可同时有多个 Task（如 HIGH 档 7/15/30 天三轮任务并存），跑批一次只推进一轮，导致旧订单（多轮都到期）需要多次跑批才生成所有轮次任务。实际使用发现：同一订单同一天跑了 4 次跑批（导入后/启动时/定时/手动自动触发叠加），HIGH 档生成了 7/15/30 三个并存任务，且都 PENDING_ASSIGN 未分配，MEDIUM/LOW 只 1 轮配置一次生成完——催收员看到的是"只有 HIGH 任务"的错觉，且同订单多任务并存语义混乱。

业务真实意图：**一个订单同一时间只有一个活跃任务**（当前催收区间的任务），跨区间时旧任务删除、生成新区间任务，不管旧任务是否完成。这更符合催收实际（每个时间段催一次，跨段重新催）。

## What Changes

- **单活跃任务模型**：一个订单同一时间只有一个活跃 Task（当前区间的），不再多轮并存 **BREAKING**
- **区间划分**：按各档配置的所有 day_offset 升序划区间，每个区间对应一个 day_offset 任务
  - `[中标日, 中标日+d1)` → 无任务（未到首轮区间）
  - `[中标日+d1, 中标日+d2)` → d1 任务
  - `[中标日+d2, 中标日+d3)` → d2 任务（d1 删除）
  - 最后 day_offset 之后 → 最后轮任务（除非轮次耗尽终态）
- **跨区间处理**：跑批时若订单已进入新区间，**删除旧区间任务**（不管旧任务 DONE/IN_PROGRESS），生成新区间任务
- **通用多轮适配**：所有风险档按各自配置的 day_offset 划区间（HIGH/MEDIUM/LOW 都可能多轮，不再固定 HIGH 3 轮、MEDIUM/LOW 1 轮）
- **回填语义不变**：REACHED → Task DONE + Order COLLECTED；UNREACHED → 保持 IN_PROGRESS
- **状态机保留 COLLECTED**：回填 REACHED 转 COLLECTED；跨区间时 COLLECTED 回 PENDING_COLLECTION + 生成新区间任务
- **已支付导入**：FINALIZED + 删除活跃任务
- **多次跑批幂等**：同一区间不重复生成，跨区间才替换

## Capabilities

### New Capabilities
（无新 capability，全部基于现有 capability 改）

### Modified Capabilities
- `task-engine`: 跑批重构为单活跃任务区间模型（每订单同时一任务，跨区间删旧生新）；状态机保留 COLLECTED；通用多轮适配各档配置
- `data-ingestion`: 已支付导入删除活跃任务（替代当前 CANCELLED 未完成任务）
- `import-payment-sync`: 已支付导入回写终态时删除活跃任务

## Impact

- **后端服务**：`batch.py`（跑批逻辑重写为区间模型）、`state.py`（回填后跨区间由跑批处理）、`assignment.py`（只分配活跃 PENDING_ASSIGN，无变化）、`parser.py`（已支付导入删除活跃任务）
- **后端模型**：Task 表无结构变化（仍是 order_id+day_offset），但语义变化（一个订单同时一个活跃任务，靠跑批删旧生新维持）
- **数据迁移**：现有并存的多轮任务需清理（保留每个订单最近区间的一个，删除其余）—— 或清空重建
- **前端**：任务列表/详情展示无大变化（本来一个订单同时看到的就是当前任务）；可能需调整批量操作预期
- **测试**：test_task_generation/test_workbench/test_e2e/test_reassign 重写适配单活跃任务模型
- **BREAKING**：任务模型语义变化（多轮并存→单活跃替换），现有数据需清理
