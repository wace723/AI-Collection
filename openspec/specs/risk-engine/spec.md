## MODIFIED Requirements

### Requirement: 风险概率来源改为 CSV 导入

风险概率不再由系统内置 Provider 计算，改为从待支付订单 CSV「风险概率」列导入写入 Order.risk_prob。RiskProvider 抽象与 tier_mapper 阈值映射保留（供未来算法接入），但跑批不再调用 recalculate_risks。

#### Scenario: 风险概率从 CSV 导入
- **WHEN** 待支付订单导入
- **THEN** Order.risk_prob 取自 CSV「风险概率」列，Order.risk_tier 由 tier_mapper.map_tier(prob, active_thresholds) 映射

#### Scenario: 跑批不再重算风险
- **WHEN** 每日跑批生成任务
- **THEN** 直接使用导入时写入的 Order.risk_prob/risk_tier，不调用 recalculate_risks

#### Scenario: 阈值配置仍生效
- **WHEN** 管理员在配置后台修改风险档阈值（risk-002）
- **THEN** 后续导入的订单按新阈值映射档位；已导入订单档位不变（除非重新导入）

### Requirement: 移除 recalc-risk API

系统不再提供 POST /api/data/orders/recalc-risk 接口（风险概率由 CSV 导入，不需系统重算）。
