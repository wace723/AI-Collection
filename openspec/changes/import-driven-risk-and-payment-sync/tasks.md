## 1. 模型与迁移

- [ ] 1.1 Order 模型新增字段：subject_name、subject_estimate_amount(Decimal)、order_generated_date(Date)、bid_category、contract_type、register_province；actual_pay_duration_days 从 OrderFeature 移到 Order
- [ ] 1.2 OrderFeature 移除 label_30/90/180/365、actual_pay_duration_days 列
- [ ] 1.3 新建 Alembic 迁移：新增列 + 移除列（dev.db 可重建，生产需数据搬移 actual_pay_duration_days）
- [ ] 1.4 验证 alembic upgrade head 成功

## 2. CSV 列映射重构

- [ ] 2.1 columns.py 重写：PENDING_ORDER_COLUMNS（38列含风险概率）+ PAID_ORDER_COLUMNS（39列含支付日期+实际支付时长+风险概率）+ 必填列 + 字段映射 + 类型分类
- [ ] 2.2 新增「风险概率」列解析（float，空/非数字→NULL）
- [ ] 2.3 新增标的名称/概算金额/订单生成日期/中标品类/合同类型/注册省份解析
- [ ] 2.4 移除旧标签列解析（label_30 等）

## 3. 待支付订单导入

- [ ] 3.1 parser.py 新增 ingest_pending_rows：按 PENDING_ORDER_COLUMNS 解析，新订单入库 risk_prob+map_tier 映射档位+特征，重复订单更新风险概率/特征
- [ ] 3.2 导入时调 tier_mapper.map_tier(prob, get_active_thresholds(db)) 写 risk_tier
- [ ] 3.3 风险概率缺失/非数字→risk_prob=NULL、risk_tier=NULL、记录 errors
- [ ] 3.4 UploadResult 保留 inserted/skipped/updated/errors

## 4. 已支付订单导入

- [ ] 4.1 parser.py 新增 ingest_paid_rows：按 PAID_ORDER_COLUMNS 解析，按 service_fee_order_no 匹配待支付订单，命中→回写 pay_status=PAID/pay_time/actual_pay_duration_days，未命中/已PAID→skipped
- [ ] 4.2 已支付导入不更新特征/风险字段
- [ ] 4.3 返回统计 inserted=0/updated=回写数/skipped/$errors

## 5. API 路由

- [ ] 5.1 api/data.py：删 POST /upload 和 POST /orders/recalc-risk；新增 POST /upload-pending + POST /upload-paid（均 ADMIN）
- [ ] 5.2 router 挂载确认（/data 前缀不变）
- [ ] 5.3 schemas/data.py：UploadSummary 保留 inserted/skipped/updated/errors

## 6. 跑批去 recalc

- [ ] 6.1 batch.run_batch 默认 recalc_risk=False；scheduler/jobs.py 跑批不调 recalculate_risks
- [ ] 6.2 calculator.recalculate_risks 保留函数但跑批不再调用；移除 api/data.py 的 recalc-risk 端点引用

## 7. 前端

- [ ] 7.1 Config 页 CSV 上传拆分为「待支付订单导入」「已支付订单导入」两个 Dragger + 统计展示
- [ ] 7.2 移除「重新计算风险」按钮（若有）
- [ ] 7.3 任务详情特征画像展示新字段（标的名称等，可选）
- [ ] 7.4 api/data.ts 拆分为 uploadPendingCsv/uploadPaidCsv

## 8. 测试

- [ ] 8.1 test_data_upload.py 重构：待支付导入（新订单+重复更新风险概率+档位映射+缺失概率容错）、已支付导入（匹配回写+无匹配跳过+已PAID跳过）、旧表头 400
- [ ] 8.2 test_risk.py 调整：移除 MockRiskProvider 预测测试；保留 tier_mapper 阈值映射测试
- [ ] 8.3 test_e2e.py 调整：上传改为 upload-pending（含风险概率），去 recalc 步骤
- [ ] 8.4 test_task_generation.py 调整：跑批不 recalc，订单 risk_tier 由导入写入

## 9. 验证

- [ ] 9.1 pytest -q 全量通过
- [ ] 9.2 npm run build 通过
- [ ] 9.3 真实联调：用工作区两个 CSV 样本导入待支付/已支付，跑批生成任务，工作台展示
- [ ] 9.4 更新 feature_list.json/claude-progress.md/session-handoff.md + 提交
