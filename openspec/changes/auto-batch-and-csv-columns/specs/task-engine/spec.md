## MODIFIED Requirements

### Requirement: 跑批按状态机推进催收状态

每日跑批 SHALL 扫描 collection_state 为 NO_NEED 或 COLLECTED 且 pay_status 非 PAID 的订单，按各轮催收时点（win_bid_date + day_offset）推进状态并生成当轮任务。跑批 MUST 在每日凌晨定时、待支付导入成功后、系统启动时三个时机触发。

#### Scenario: 到达首轮时点推进待催收
- **WHEN** 跑批时订单 collection_state=NO_NEED，且 win_bid_date + 首轮 day_offset <= today，且 pay_status 非 PAID
- **THEN** Order.collection_state 推进为 PENDING_COLLECTION，生成首轮 Task（day_offset=首轮值，status=PENDING_ASSIGN）

#### Scenario: 待支付导入后自动跑批
- **WHEN** 管理员上传待支付 CSV 导入成功
- **THEN** 系统自动触发跑批（推进状态机+生成任务），导入响应返回跑批结果（generated/finalized/by_tier）

#### Scenario: 系统启动时自动跑批
- **WHEN** 系统启动（main.py lifespan 启动调度器后）
- **THEN** 自动触发一次跑批，同步停机期间到期的催收时点；跑批失败不阻断启动（记录日志）

#### Scenario: 已支付订单不推进不生成
- **WHEN** 跑批时订单 pay_status=PAID
- **THEN** 不推进 collection_state，不生成催收任务（无论当前状态与时点）

#### Scenario: 轮次耗尽进入终态
- **WHEN** 跑批时订单所有配置的催收轮次都已催过，且仍待支付
- **THEN** Order.collection_state 推进为 FINALIZED，不再生成新催收任务

#### Scenario: 跑批幂等
- **WHEN** 同日重复跑批同一订单（含导入后跑批+启动跑批+定时跑批）
- **THEN** 状态推进与任务生成只生效一次（batch_id + order_id + day_offset 唯一约束兜底），重复跑批 generated=0
