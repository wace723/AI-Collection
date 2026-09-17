## 1. 模型与迁移

- [ ] 1.1 Order 模型新增 `collection_state` 字段（String(24)，默认 NO_NEED，非空，index）
- [ ] 1.2 定义 collection_state 枚举常量（NO_NEED / PENDING_COLLECTION / COLLECTED / FINALIZED）
- [ ] 1.3 Task.result 枚举常量重定义为 {UNREACHED, REACHED}（BREAKING，移除 PAID/PROMISE/DISPUTE/LOST_CONTACT/OTHER）
- [ ] 1.4 Alembic 迁移：加 Order.collection_state 字段
- [ ] 1.5 迁移内数据回填：现有 Order 按 win_bid_date + 首轮 day_offset 回填 collection_state（已过首轮→PENDING_COLLECTION，未到→NO_NEED，已支付→FINALIZED）
- [ ] 1.6 迁移内数据回填：现有 Task.result 旧值映射（PAID/DISPUTE/LOST_CONTACT/OTHER→REACHED，PROMISE→UNREACHED）
- [ ] 1.7 迁移内数据回填：现有 Task.status=PROMISE 改期的 PENDING 任务 → IN_PROGRESS

## 2. 导入预设 collection_state

- [ ] 2.1 `parser.py::ingest_pending_rows` 新订单入库时按 win_bid_date + 首轮 day_offset 预设 collection_state（已到→PENDING_COLLECTION，未到→NO_NEED，无 risk_tier/无配置→NO_NEED）
- [ ] 2.2 重复导入（updated）不改 collection_state（仅更新风险概率与特征）
- [ ] 2.3 单元测试：导入预设状态（已到首轮/未到首轮/无配置/重复导入不改）

## 3. 跑批按状态机推进

- [ ] 3.1 重构 `batch.py::generate_tasks`：扫描 collection_state IN (NO_NEED, COLLECTED) 且 pay_status 非 PAID 的订单
- [ ] 3.2 按各轮 day_offset 判断到达下一轮时点，推进 collection_state → PENDING_COLLECTION，生成当轮 Task（PENDING_ASSIGN，幂等键 order_id+day_offset）
- [ ] 3.3 轮次耗尽判定：所有 day_offset 都已催过且仍待支付 → collection_state → FINALIZED
- [ ] 3.4 已支付订单跳过（不推进不生成）
- [ ] 3.5 未到时点不推进
- [ ] 3.6 跑批幂等（同日重跑 generated=0，唯一约束兜底）
- [ ] 3.7 单元测试：首轮推进/下一轮推进/轮次耗尽终态/已支付跳过/未到时点/幂等

## 4. 分配保留未完成任务 assignee

- [ ] 4.1 `assignment.py` 保持档内负载均衡（HIGH>MEDIUM>LOW + 账龄倒序 + 最低负载轮询）
- [ ] 4.2 确认 IN_PROGRESS 任务保留原 assignee 不回分配池（现有逻辑本就如此，加测试固化）
- [ ] 4.3 无活跃催收员时 skipped
- [ ] 4.4 单元测试：档内负载均衡差<=1/未完成任务保留 assignee/无催收员 skipped

## 5. 回填两分类推进状态

- [ ] 5.1 重构 `state.py::submit_result`：result 入参改为 {UNREACHED, REACHED}（移除 PROMISE 改期分支）
- [ ] 5.2 REACHED → Task.status=DONE，Order.collection_state=COLLECTED，写 TaskResult 明细
- [ ] 5.3 UNREACHED → Task.status 保持 IN_PROGRESS，Order.collection_state 保持 PENDING_COLLECTION，写 TaskResult 明细（同日可反复）
- [ ] 5.4 终态任务不可回填（409），COLLECTOR 只能回填自己任务（403）
- [ ] 5.5 移除 claim_task 调用路径（保留函数兼容历史，分配后直接 IN_PROGRESS）
- [ ] 5.6 单元测试：REACHED 推进 COLLECTED/UNREACHED 保持待催收/同日反复/终态 409/越权 403

## 6. 已支付导入回写终态停催

- [ ] 6.1 `parser.py::ingest_paid_rows` 回写 pay_status=PAID 时同步 collection_state=FINALIZED
- [ ] 6.2 该订单所有非终态 Task（PENDING_ASSIGN/IN_PROGRESS）→ CANCELLED，result_note 标注「已支付停催」
- [ ] 6.3 无匹配/已 PAID 跳过
- [ ] 6.4 单元测试：已支付导入终态停催/无匹配跳过/已 PAID 跳过

## 7. 监督员视图增强

- [ ] 7.1 `api/tasks.py` 任务列表加 collection_state 过滤参数
- [ ] 7.2 `supervisor_service.py::get_staff_performance` 扩展返回各催收员当天「已接通数/未接通数/待处理数」计数
- [ ] 7.3 `api/supervisor.py` 员工绩效端点返回扩展计数
- [ ] 7.4 改派（reassign）保持 collection_state 不变（加测试固化）
- [ ] 7.5 单元测试：collection_state 过滤/当天完成进度计数/改派不改状态

## 8. 前端

- [ ] 8.1 Workbench 任务列表展示 collection_state 与轮次（day_offset/scene）
- [ ] 8.2 Workbench 回填表单改为「未接通/已接通」两选项 + 已接通显示自由文本反馈框（移除旧五分类与 PROMISE 改期日）
- [ ] 8.3 Workbench 详情展示 collection_state 与当前轮次
- [ ] 8.4 Supervisor 任务列表加 collection_state 过滤
- [ ] 8.5 Supervisor 员工绩效展示当天「已接通/未接通/待处理」计数
- [ ] 8.6 types/api.ts 更新 Task.result 枚举与 Order.collection_state 类型
- [ ] 8.7 npm run build 通过

## 9. 测试与验证

- [ ] 9.1 重写 test_task_generation 适配状态机推进（首轮/下一轮/轮次耗尽/已支付跳过/幂等）
- [ ] 9.2 重写 test_workbench 适配两分类回填与 collection_state 展示
- [ ] 9.3 重写 test_e2e 适配新状态机与两分类回填全流程
- [ ] 9.4 重写 test_reassign 适配改派保持 collection_state
- [ ] 9.5 重写 test_supervisor 适配完成进度计数
- [ ] 9.6 pytest -q 全量通过（无回归）
- [ ] 9.7 真实联调：导入待支付（预设状态）→跑批推进→分配→回填REACHED→COLLECTED→已支付导入→FINALIZED停催
