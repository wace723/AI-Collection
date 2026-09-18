## ADDED Requirements

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
