## Purpose

定义风险概率来源与催收轮次配置：风险概率从待支付 CSV 导入（非系统预测），经阈值映射档位；催收轮次配置作为 Order 催收状态机推进的时点来源。RiskProvider 抽象保留供未来算法接入。
## Requirements
### Requirement: 风险概率来源改为 CSV 导入

风险概率 SHALL 不再由系统内置 Provider 计算，改为从待支付订单 CSV「风险概率」列导入写入 Order.risk_prob。RiskProvider 抽象与 tier_mapper 阈值映射 MUST 保留（供未来算法接入），但跑批不再调用 recalculate_risks。

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

系统 SHALL 不再提供 POST /api/data/orders/recalc-risk 接口（风险概率由 CSV 导入，不需系统重算）。

#### Scenario: recalc-risk 接口已移除
- **WHEN** 客户端调用 POST /api/data/orders/recalc-risk
- **THEN** 接口不存在（404 或未注册），风险概率由 CSV 导入写入

### Requirement: 催收轮次配置作为状态机推进时点来源

风险档配置中的催收轮次（collection_schedules，含 risk_tier + day_offset + scene）SHALL 作为 Order 催收状态机推进的时点来源。跑批 MUST 按各轮 day_offset 判断「是否到达下一轮催收时点」并推进 collection_state，轮次配置本身的结构与配置 CRUD 不变。

#### Scenario: 跑批按 day_offset 推进状态
- **WHEN** 跑批推进某订单催收状态时
- **THEN** 取该订单 risk_tier 对应配置的所有 day_offset 排序，按 win_bid_date + day_offset <= today 判断是否到达下一轮时点

#### Scenario: 轮次耗尽判定
- **WHEN** 跑批判断某订单是否轮次耗尽
- **THEN** 若该订单 risk_tier 配置的所有 day_offset 对应轮次都已催过（均有非 CANCELLED Task）且仍待支付，collection_state → FINALIZED

#### Scenario: 配置变更不影响已催轮次
- **WHEN** 管理员修改风险档催收轮次配置（增删 day_offset）
- **THEN** 已催过的轮次（已有非 CANCELLED Task）不变；新配置仅影响后续跑批的状态推进判断

