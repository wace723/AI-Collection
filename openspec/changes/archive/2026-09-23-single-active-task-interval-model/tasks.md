## 1. 跑批逻辑重写为单活跃任务区间模型

- [x] 1.1 `batch.py` 重写 `generate_tasks`：扫描所有待支付订单（不限 collection_state），按各档 day_offset 升序算当前区间 day_offset
- [x] 1.2 区间算法：`current_offset = 最大的 day_offset 使 win_bid_date + day_offset <= today`；无则 NO_NEED
- [x] 1.3 查每单现有活跃任务（PENDING_ASSIGN/IN_PROGRESS/DONE）：day_offset==current_offset 则幂等不重复；否则删除旧任务+生成新任务
- [x] 1.4 跨区间删旧生新：删除旧活跃任务（不管 DONE/IN_PROGRESS），生成新区间任务（PENDING_ASSIGN），collection_state→PENDING_COLLECTION
- [x] 1.5 通用多轮适配：按各档配置的所有 day_offset 划区间（不再依赖 ADVANCEABLE_STATES 区分档位）
- [x] 1.6 已支付订单跳过（不推进不生成不删除）
- [x] 1.7 未到首轮区间 NO_NEED 不生成
- [x] 1.8 多次跑批幂等（同区间不重复生成/删除）
- [x] 1.9 单元测试：单活跃/同区间幂等/跨区间删旧生新/已接通跨区间仍生成/未到首轮/通用多轮/已支付跳过/幂等（35 passed）

## 2. 状态机调整（保留 COLLECTED）

- [x] 2.1 `states.py` ADVANCEABLE_STATES 调整：跑批扫描所有待支付订单（不再按 ADVANCEABLE_STATES 过滤），保留 NO_NEED/PENDING_COLLECTION/COLLECTED/FINALIZED 四态
- [x] 2.2 `state.py` 回填 REACHED → Task DONE + Order COLLECTED（不变）；跨区间由跑批处理（COLLECTED→PENDING_COLLECTION 删旧生新）
- [x] 2.3 单元测试：回填推进 COLLECTED/跨区间由跑批删旧生新

## 3. 已支付导入删除活跃任务

- [x] 3.1 `parser.py::ingest_paid_rows` 回写 pay_status=PAID 时：collection_state→FINALIZED + 删除该订单所有活跃任务（PENDING_ASSIGN/IN_PROGRESS/DONE 全部删除，替代 CANCELLED）
- [x] 3.2 单元测试：已支付导入终态+删除活跃任务/无匹配跳过/已PAID跳过

## 4. 数据迁移

- [x] 4.1 清空 tasks 表（dev.db 手动 DELETE，开发期数据可重建）
- [x] 4.2 首次跑批自动规整（每订单生成单活跃任务）

## 5. 测试重写

- [x] 5.1 重写 test_task_generation 适配单活跃任务区间模型（35 passed）
- [x] 5.2 重写 test_workbench 适配（一个订单同时一个任务）
- [x] 5.3 重写 test_e2e 适配单活跃任务全流程（3 passed）
- [x] 5.4 重写 test_reassign 适配（改派活跃任务）
- [x] 5.5 重写 test_data_upload 已支付导入删除活跃任务 + batch_result 新字段（11 passed）
- [x] 5.6 pytest -q 全量通过（198 passed，无回归）

## 6. 验证

- [x] 6.1 真实联调：导入测试数据待支付 CSV → 跑批生成单活跃任务（每订单一个）→ 分配 → 回填 → 跨区间跑批删旧生新 → 已支付导入删活跃任务
- [x] 6.2 验证：一个订单同时只有一个活跃任务（查 DB 确认，有多活跃任务的订单数=0）
- [x] 6.3 npm run build 通过
