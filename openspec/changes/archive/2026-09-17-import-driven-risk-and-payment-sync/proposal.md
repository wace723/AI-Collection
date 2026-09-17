## Why

当前系统内置 MockRiskProvider 做风险预测，但现阶段风险算法由线下模型离线跑好，线上系统应直接消费「风险概率」指标而非自己预测。同时业务有三类导入场景（全量基础、增量待支付、增量已支付更新），现有单接口无法覆盖「已支付订单回写支付状态」的匹配更新流程。

## What Changes

- **BREAKING**：移除系统内的风险预测能力（MockRiskProvider / recalculate_risks / recalc-risk API）。风险概率改为从导入 CSV 的「风险概率」列直接读取写入 `Order.risk_prob`，再经 risk-002 阈值配置映射 HIGH/MEDIUM/LOW。
- **BREAKING**：CSV 列映射重构。现有 37 列映射（含标签_30/90/180/365天是否欠费、实际支付时长_天 在待支付 CSV 已移除）替换为按新 CSV 表头的新映射。新增字段：标的名称、标的概算金额、订单生成日期、中标品类、合同类型、注册省份。
- 新增「待支付订单导入」与「已支付订单导入」两个独立入口，共享同一套 Order/OrderFeature 模型与列映射，但语义不同：
  - 待支付导入（全量/增量）：入库未支付订单 + 特征 + 风险概率，重复订单更新风险概率/特征。
  - 已支付导入：按服务费订单号匹配数据库现有待支付订单，回写 pay_status=PAID + pay_time + 实际支付时长。无匹配则跳过。
- 跑批生成任务时不再 recalc_risk，直接用导入时写入的 risk_prob/risk_tier。

## Capabilities

### New Capabilities
- `import-payment-sync`：已支付订单导入与支付状态回写（按服务费订单号匹配待支付订单，更新 pay_status/pay_time/actual_pay_duration_days）

### Modified Capabilities
- `data-ingestion`：CSV 列映射重构为新表头（37/38 列）；待支付 CSV 新增「风险概率」列直接写入 Order.risk_prob；重复订单更新风险概率与特征（非跳过）；新增标的名称等字段
- `risk-engine`：移除预测能力（MockRiskProvider/recalculate_risks/recalc-risk API 保留抽象但默认不再调用）；风险概率来源从「系统计算」改为「CSV 导入」；阈值映射保留

## Impact

- 后端：`services/data_ingestion/columns.py`（列映射重构）、`parser.py`（待支付/已支付两条导入路径）、`api/data.py`（拆分 upload 端点 + 新增已支付导入）、`models/order.py` + `models/order_features.py`（新字段 + 移除标签字段）、`services/risk_engine/calculator.py`（recalculate_risks 废弃/保留）、`scheduler/jobs.py`（跑批去 recalc）、`schemas/data.py`
- 数据库迁移：新增标的名称/概算金额/订单生成日期/中标品类/合同类型/注册省份列；移除标签_30/90/180/365、actual_pay_duration_days（待支付 CSV 已无，但已支付 CSV 有，移到 Order 或保留 OrderFeature 待设计定）
- 前端：`pages/Config/`（CSV 上传拆分为待支付/已支付两个入口）、任务详情特征画像展示新字段
- 测试：test_data_upload 重构、test_risk 调整、test_e2e 调整
- 向后不兼容：旧 37 列 CSV 无法导入（表头变了）
