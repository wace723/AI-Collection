## Purpose

定义平台使用费订单的 CSV 导入能力：待支付订单导入（含风险概率）与已支付订单导入（回写支付状态）。支持 GBK/UTF-8 自动识别、列校验、去重/更新语义。
## Requirements
### Requirement: 待支付订单导入入口

系统 SHALL 提供独立的待支付订单导入入口（全量基础导入与增量导入共用同一接口），入库未支付订单+特征+风险概率。

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

待支付 CSV SHALL 为 38 列（含风险概率）、已支付 CSV 39 列（含支付日期+实际支付时长+风险概率）。列映射 MUST 按新表头，新增标的名称、标的概算金额、订单生成日期、中标品类、合同类型、注册省份字段。

#### Scenario: 待支付 CSV 列映射
- **WHEN** 上传待支付 CSV
- **THEN** 按新 38 列表头解析，标的名称→Order.subject_name、标的概算金额→Order.subject_estimate_amount、订单生成日期→Order.order_generated_date、中标品类→Order.bid_category、合同类型→Order.contract_type、注册省份→Order.register_province、风险概率→Order.risk_prob

#### Scenario: 旧 37 列 CSV 无法导入
- **WHEN** 上传旧格式 CSV（无风险概率列、表头不符）
- **THEN** 返回 400 缺失必填列错误

### Requirement: 导入响应统计

待支付/已支付导入 SHALL 均 返回 inserted/skipped/updated/errors 四项统计。

#### Scenario: 导入响应字段
- **WHEN** 待支付或已支付 CSV 导入完成
- **THEN** 响应包含 inserted/skipped/updated/errors 四项统计

### Requirement: 移除旧单接口与风险重算接口

系统 SHALL 不再提供 POST /api/data/upload（旧单接口）和 POST /api/data/orders/recalc-risk；MUST 改为 POST /api/data/upload-pending 和 POST /api/data/upload-paid。

#### Scenario: 旧接口已移除
- **WHEN** 系统运行
- **THEN** 不再提供 POST /api/data/upload（旧单接口）和 POST /api/data/orders/recalc-risk；改为 POST /api/data/upload-pending 和 POST /api/data/upload-paid

### Requirement: 导入预设 Order 催收状态初始值

待支付订单导入时，系统 SHALL 按订单 win_bid_date 与其 risk_tier 首轮催收 day_offset 预设 Order.collection_state 初始值，使催收状态在导入时即对业务可读，无需等待首次跑批推导。

#### Scenario: 已到首轮时点预设待催收
- **WHEN** 待支付订单导入，订单有 risk_tier 且有生效配置，win_bid_date + 首轮 day_offset <= today，pay_status 非 PAID
- **THEN** Order.collection_state = PENDING_COLLECTION

#### Scenario: 未到首轮时点预设无需催收
- **WHEN** 待支付订单导入，订单有 risk_tier 且有生效配置，win_bid_date + 首轮 day_offset > today
- **THEN** Order.collection_state = NO_NEED

#### Scenario: 无 risk_tier 或无配置回退无需催收
- **WHEN** 待支付订单导入，订单无 risk_tier 或当前无生效风险档配置
- **THEN** Order.collection_state = NO_NEED（等配置就绪后跑批推进）

#### Scenario: 重复导入不改催收状态
- **WHEN** 待支付 CSV 重复导入已存在订单（updated）
- **THEN** 更新风险概率与特征字段，Order.collection_state 保持不变

