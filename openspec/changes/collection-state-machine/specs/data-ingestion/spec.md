## ADDED Requirements

### Requirement: 导入预设 Order 催收状态初始值

待支付订单导入时，系统按订单 win_bid_date 与其 risk_tier 首轮催收 day_offset 预设 Order.collection_state 初始值，使催收状态在导入时即对业务可读，无需等待首次跑批推导。

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

## MODIFIED Requirements

### Requirement: 已支付导入回写支付状态与催收终态

已支付订单导入按 service_fee_order_no 匹配待支付订单回写支付状态，并同步推进 Order.collection_state 为终态 FINALIZED，停催该订单所有未完成催收任务。

#### Scenario: 已支付导入回写支付状态与终态
- **WHEN** 已支付 CSV 导入，某行 service_fee_order_no 匹配到待支付订单
- **THEN** Order.pay_status=PAID、Order.pay_time=支付日期、Order.actual_pay_duration_days=实际支付时长、Order.collection_state=FINALIZED，该订单所有非终态 Task → CANCELLED（result_note 标注「已支付停催」），计入 updated

#### Scenario: 已支付导入无匹配跳过
- **WHEN** 已支付 CSV 某行 service_fee_order_no 无匹配待支付订单
- **THEN** 该行跳过，不计入 updated

#### Scenario: 已支付订单匹配但已 PAID 跳过
- **WHEN** 已支付 CSV 某行匹配的订单 pay_status 已为 PAID
- **THEN** 该行跳过（不重复回写），不计入 updated
