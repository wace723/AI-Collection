## 1. 模型与迁移

- [ ] 1.1 Order 模型新增 `engineering_bureau`（工程局单位）、`subsidiary`（下属单位）字段（String(255)，nullable）
- [ ] 1.2 Alembic 迁移：Order 加 engineering_bureau/subsidiary 字段

## 2. CSV 列映射适配 40 列

- [ ] 2.1 `columns.py` PENDING_ORDER_COLUMNS 加「工程局单位」「下属单位」（标的概算金额后、中标日期前，40 列）
- [ ] 2.2 `columns.py` PAID_ORDER_COLUMNS 加「工程局单位」「下属单位」（标的概算金额后、中标日期前，40 列）
- [ ] 2.3 `columns.py` ORDER_FIELD_MAP 加「工程局单位」→engineering_bureau、「下属单位」→subsidiary 映射
- [ ] 2.4 单元测试：40 列 CSV 导入成功 + 旧 38/39 列 CSV 400

## 3. 待支付导入后自动跑批

- [ ] 3.1 `api/data.py::upload_pending` 导入成功后调用 `run_batch(db, today=date.today(), recalc_risk=False)`
- [ ] 3.2 `schemas/data.py` UploadSummary 加可选 `batch_result` 字段（generated/finalized/by_tier）
- [ ] 3.3 upload_pending 响应填充 batch_result，upload_paid 响应 batch_result=None
- [ ] 3.4 单元测试：待支付导入后自动跑批生成任务 + 响应含 batch_result

## 4. 系统启动时自动跑批

- [ ] 4.1 `main.py::lifespan` scheduler.start() 后调用 run_batch（try/except 不阻断启动）
- [ ] 4.2 单元测试：lifespan 启动触发跑批（或集成测试验证启动后任务同步）

## 5. 前端导入结果 Modal

- [ ] 5.1 `types/api.ts` Order 加 engineering_bureau/subsidiary；UploadSummary 加 batch_result 类型（可选）
- [ ] 5.2 Config 页新增导入结果 Modal 组件（展示 inserted/updated/skipped/errors + 错误明细列表 + 跑批统计）
- [ ] 5.3 待支付 Dragger 上传后弹 Modal（含跑批统计），已支付 Dragger 上传后弹 Modal（无跑批统计）
- [ ] 5.4 npm run build 通过

## 6. 测试与验证

- [ ] 6.1 重写 test_data_upload 适配 40 列 CSV + 自动跑批
- [ ] 6.2 新增测试：系统启动跑批（lifespan）
- [ ] 6.3 pytest -q 全量通过（无回归）
- [ ] 6.4 真实联调：导入测试数据/待支付 CSV → 自动跑批 → 任务生成 → 导入已支付 CSV → 终态停催；前端导入结果 Modal 展示
