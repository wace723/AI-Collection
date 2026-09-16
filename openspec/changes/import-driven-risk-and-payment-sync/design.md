## Context

当前系统 CSV 导入为单一接口（37 列旧表头），风险概率由 MockRiskProvider 在跑批时计算。业务现在改为：线下模型离线算好风险概率，随 CSV「风险概率」列导入；且需区分「待支付订单导入」与「已支付订单导入」两类场景。新 CSV 表头与旧表头差异显著（新增标的名称/概算金额/订单生成日期等，待支付 CSV 移除了标签列）。

## Goals / Non-Goals

**Goals:**
- 风险概率从 CSV「风险概率」列导入，系统不再预测；经 risk-002 阈值映射档位
- 待支付订单导入（全量/增量共用）：入库未支付订单+特征+风险概率，重复订单更新概率/特征
- 已支付订单导入：按服务费订单号匹配待支付订单，回写支付状态
- CSV 列映射重构为新表头（标的名称等新字段）
- 跑批生成任务直接用导入的 risk_prob/risk_tier，不再 recalc

**Non-Goals:**
- 不做真实风险算法（线下做）
- 不改任务状态机/分配逻辑（已在上轮简化）
- 不改话术/大盘/主管视图
- 不处理「已支付订单导入时数据库无匹配」的自动建单（无匹配跳过）

## Decisions

### D1：模型字段重构（Order + OrderFeature）
- **Order 新增**：`subject_name`(标的名称 String 255)、`subject_estimate_amount`(标的概算金额 Decimal)、`order_generated_date`(订单生成日期 Date)、`bid_category`(中标品类 String)、`contract_type`(合同类型 String)、`register_province`(注册省份 String)
- **Order 保留**：risk_prob、risk_tier、pay_status、pay_time（已支付导入回写）
- **OrderFeature 移除**：label_30/90/180/365（待支付 CSV 已无；已支付 CSV 也无）、actual_pay_duration_days（待支付 CSV 无；已支付 CSV 有，移到 Order 体现支付状态更合理）
- **OrderFeature 新增**：无（新字段都是订单级标识/状态，放 Order）
- actual_pay_duration_days 移到 Order（因已支付导入时回写它，与 pay_status 同属支付状态）。OrderFeature 不再持有它。

### D2：两套 CSV 列映射常量
- `columns.py` 重写 `PENDING_ORDER_COLUMNS`（38列：37 + 风险概率）和 `PAID_ORDER_COLUMNS`（39列：38 + 风险概率，含支付日期+实际支付时长）。两者共享订单标识+特征列，差异在支付相关列。
- 必填列：服务费订单号（两者）、风险概率（待支付必填，已支付可选）

### D3：导入端点拆分
- `POST /api/data/upload-pending`：待支付订单导入（全量/增量共用）。新订单入库 risk_prob+映射档位；重复订单更新 risk_prob+特征。
- `POST /api/data/upload-paid`：已支付订单导入。按 service_fee_order_no 匹配；命中→回写 pay_status=PAID/pay_time/actual_pay_duration_days；未命中→skipped。
- 旧 `POST /api/data/upload` 废弃删除（BREAKING）。
- 旧 `POST /api/data/orders/recalc-risk` 删除（不再预测）。

### D4：风险概率→档位映射
- 导入待支付时：读取「风险概率」列→`Order.risk_prob`→调用 `tier_mapper.map_tier(prob, get_active_thresholds(db))`→`Order.risk_tier`。
- 沿用 risk-002 阈值配置（70/30 默认），不改 risk_config_service。

### D5：跑批去 recalc
- `batch.run_batch` 默认 recalc_risk=False；`scheduler/jobs.py` 跑批不再调 recalculate_risks。
- `calculator.recalculate_risks` 保留函数（供未来算法接入）但跑批不再调用。

### D6：已支付导入回写语义
- 已支付 CSV 每行含 service_fee_order_no + 支付日期 + 实际支付时长。
- 匹配到待支付订单：设 pay_status='PAID'、pay_time=支付日期、Order.actual_pay_duration_days=实际支付时长。
- 不更新特征字段（支付状态回写只动支付相关）。
- 无匹配（订单不存在或已 PAID）：skipped。

## Risks / Trade-offs

- **BREAKING 旧 CSV 不兼容**：旧 37 列表头无法导入。需用户用新格式 CSV。
- actual_pay_duration_days 从 OrderFeature 移到 Order，需迁移脚本搬移现有数据（dev.db 可重建）。
- 移除标签列后，risk-001 的「防泄漏测试」(test_mock_provider_ignores_label_fields) 失去意义——随 MockRiskProvider 废弃一起处理。
- 「风险概率」列缺失/非数字时的容错：默认风险概率 NULL→risk_tier NULL→跑批跳过（不生成任务），记录 errors。
