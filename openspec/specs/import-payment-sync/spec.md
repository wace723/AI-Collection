## Purpose

定义已支付订单导入与支付状态回写能力：按服务费订单号匹配待支付订单，回写支付状态（pay_status/pay_time/actual_pay_duration_days），不新建订单。
## Requirements
### Requirement: 已支付订单导入与支付状态回写

系统 SHALL 提供独立的已支付订单导入入口，按服务费订单号匹配数据库中现有的待支付订单，回写支付状态。MUST 不自动新建订单。回写 pay_status=PAID 时 MUST 同步推进 Order.collection_state 为终态 FINALIZED，停催该订单所有未完成催收任务（PENDING_ASSIGN/IN_PROGRESS → CANCELLED，标注「已支付停催」）。

#### Scenario: 匹配到待支付订单则回写支付状态与终态
- **WHEN** 管理员上传已支付订单 CSV，某行 service_fee_order_no 在数据库存在且 pay_status 非 PAID
- **THEN** 该订单 pay_status 置为 PAID，pay_time 置为 CSV 的「支付日期」，actual_pay_duration_days 置为 CSV 的「实际支付时长_天」，collection_state 置为 FINALIZED，该订单所有非终态 Task → CANCELLED（result_note 标注「已支付停催」），计入 updated

#### Scenario: 无匹配订单则跳过
- **WHEN** 已支付 CSV 某行 service_fee_order_no 在数据库不存在
- **THEN** 该行跳过，计入 skipped，不新建订单

#### Scenario: 已支付订单再次导入跳过
- **WHEN** 已支付 CSV 某行匹配到的订单已是 PAID
- **THEN** 该行跳过，计入 skipped

#### Scenario: 已支付导入只更新支付相关字段
- **WHEN** 已支付导入匹配到订单并回写
- **THEN** 仅更新 pay_status/pay_time/actual_pay_duration_days/collection_state，不改动风险概率、特征、档位等字段

#### Scenario: 已支付导入需 ADMIN 权限
- **WHEN** 非 ADMIN 角色调用已支付导入
- **THEN** 返回 403

### Requirement: 已支付导入响应统计

已支付导入 SHALL 返回 inserted/skipped/updated/errors 统计，其中 inserted 恒为 0（不新建），updated 为回写支付状态的订单数。

#### Scenario: 已支付导入响应字段
- **WHEN** 已支付 CSV 导入完成
- **THEN** 响应包含 inserted（恒 0）/skipped/updated/errors 统计

