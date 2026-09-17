## ADDED Requirements

### Requirement: 待支付订单导入入口

系统提供独立的待支付订单导入入口（全量基础导入与增量导入共用同一接口），入库未支付订单+特征+风险概率。

#### Scenario: 全量导入新订单
- **WHEN** 管理员上传待支付 CSV，所有行 service_fee_order_no 在数据库不存在
- **THEN** 每行入库为未支付订单（pay_status=NULL），写入特征与风险概率，计入 inserted

#### Scenario: 增量导入重复订单更新风险概率
- **WHEN** 待支付 CSV 某行 service_fee_order_no 已存在
- **THEN** 更新该订单的风险概率与特征字段，计入 updated，不跳过

#### Scenario: 风险概率经阈值映射档位
- **WHEN** 待支付导入某行风险概率为 75
- **THEN** Order.risk_prob=75，经 risk-002 阈值配置（默认 70/30）映射 risk_tier=HIGH

#### Scenario: 风险概率缺失或非数字
- **WHEN** 待支付 CSV 某行「风险概率」为空或非数字
- **THEN** risk_prob=NULL、risk_tier=NULL，订单仍入库，记录到 errors，跑批时不为其生成任务

### Requirement: CSV 列映射重构

待支付 CSV 38 列（含风险概率）、已支付 CSV 39 列（含支付日期+实际支付时长+风险概率）。列映射按新表头，新增标的名称、标的概算金额、订单生成日期、中标品类、合同类型、注册省份字段。

#### Scenario: 待支付 CSV 列映射
- **WHEN** 上传待支付 CSV
- **THEN** 按新 38 列表头解析，标的名称→Order.subject_name、标的概算金额→Order.subject_estimate_amount、订单生成日期→Order.order_generated_date、中标品类→Order.bid_category、合同类型→Order.contract_type、注册省份→Order.register_province、风险概率→Order.risk_prob

#### Scenario: 旧 37 列 CSV 无法导入
- **WHEN** 上传旧格式 CSV（无风险概率列、表头不符）
- **THEN** 返回 400 缺失必填列错误

### Requirement: 导入响应统计

待支付/已支付导入均返回 inserted/skipped/updated/errors 四项统计。

## MODIFIED Requirements

### Requirement: 移除旧单接口与风险重算接口
- **WHEN** 系统运行
- **THEN** 不再提供 POST /api/data/upload（旧单接口）和 POST /api/data/orders/recalc-risk；改为 POST /api/data/upload-pending 和 POST /api/data/upload-paid
