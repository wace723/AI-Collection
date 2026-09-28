## MODIFIED Requirements

### Requirement: 跑批按状态机推进催收状态

每日跑批 SHALL 扫描所有待支付订单（pay_status 非 PAID），按各档配置的 day_offset 升序划分区间，为每个订单维护**唯一一个活跃任务**（当前区间对应的任务）。跑批 MUST 在每日凌晨定时、待支付导入成功后、系统启动时三个时机触发。任务的 `scene` 取值 SHALL 为 `ROUND_N`（N 为该档 schedules 中该 day_offset 对应的 seq），不再使用固定枚举 FIRST/SECOND/THIRD。

#### Scenario: 单活跃任务模型
- **WHEN** 跑批时一个订单有多个活跃任务（旧多轮并存数据）
- **THEN** 保留当前区间对应的任务，删除其他活跃任务，一个订单同时只有一个活跃 Task

#### Scenario: 到达首轮区间生成任务且 scene 为 ROUND_1
- **WHEN** 跑批时订单 age_days（today - win_bid_date）>= 首轮 day_offset（d1），且该区间无活跃任务
- **THEN** collection_state 推进为 PENDING_COLLECTION，生成当前区间任务（day_offset=当前区间 d1，scene=ROUND_1，status=PENDING_ASSIGN）

#### Scenario: 跨区间生成任务 scene 按 seq 递增
- **WHEN** 跑批时订单从第 1 区间进入第 2 区间（HIGH 档 schedules seq=2 对应的 day_offset）
- **THEN** 删除旧区间任务，生成新区间任务，scene=ROUND_2（N 对应该档 schedules 的 seq）

#### Scenario: 同区间幂等不重复生成
- **WHEN** 跑批时订单当前区间已有活跃任务（day_offset == 当前区间 day_offset）
- **THEN** 不重复生成任务，不删除现有任务，collection_state 保持

#### Scenario: 跨区间删旧生新
- **WHEN** 跑批时订单已进入新区间（当前区间 day_offset 变化），旧区间活跃任务存在
- **THEN** 删除旧区间活跃任务（不管 DONE/IN_PROGRESS），生成新区间任务（day_offset=新区间，scene=该区间 seq 对应的 ROUND_N，PENDING_ASSIGN），collection_state 推进为 PENDING_COLLECTION

#### Scenario: 已接通跨区间仍生成新区间任务
- **WHEN** 上一轮任务已接通（DONE），跑批时订单已进入新区间
- **THEN** 删除已接通的旧任务，生成新区间任务（每轮独立催收，上一轮接通不影响这轮），scene 为新区间对应 seq 的 ROUND_N

#### Scenario: 未到首轮区间无任务
- **WHEN** 跑批时订单 age_days < 首轮 day_offset
- **THEN** collection_state 保持 NO_NEED，不生成任务

#### Scenario: 通用多轮适配各档配置
- **WHEN** 某风险档配置多个 day_offset（如 HIGH [7,15,30]，或 MEDIUM [15,30,60]）
- **THEN** 按该档所有 day_offset 升序划区间，每个区间一个任务，scene 按 seq 依次为 ROUND_1/ROUND_2/ROUND_3，跨区间删旧生新

#### Scenario: 已支付订单不推进不生成
- **WHEN** 跑批时订单 pay_status=PAID
- **THEN** 不推进 collection_state，不生成任务，不删除任务

#### Scenario: 跑批幂等
- **WHEN** 同日重复跑批同一订单（含导入后跑批+启动跑批+定时跑批）
- **THEN** 同区间不重复生成，不重复删除，状态与任务只生效一次

## ADDED Requirements

### Requirement: 风险档催收时点 scene 由 seq 自动生成 ROUND_N

系统 SHALL 在保存风险档配置时，按每档 schedules 的 seq 自动生成 `scene=ROUND_{seq}` 写入 `CollectionSchedule.scene`，不再接受外部传入固定枚举值（FIRST/SECOND/THIRD）。`SceneEnum` SHALL 移除或改为仅接受 ROUND_N 格式校验。

#### Scenario: 保存配置自动生成 ROUND_N scene
- **WHEN** 管理员保存风险档配置，HIGH 档 schedules 含 3 条（seq=1,2,3）
- **THEN** 3 条 CollectionSchedule 的 scene 分别为 ROUND_1/ROUND_2/ROUND_3（由 seq 自动生成，非前端传入）

#### Scenario: 支持 4 轮及以上
- **WHEN** 管理员配置 HIGH 档 4 条 schedules（seq=1,2,3,4）
- **THEN** scene 依次为 ROUND_1/ROUND_2/ROUND_3/ROUND_4，无枚举上限

#### Scenario: 数据迁移映射旧 scene 值
- **WHEN** 升级时现有 collection_schedules/tasks 含 FIRST/SECOND/THIRD
- **THEN** 迁移映射 FIRST→ROUND_1、SECOND→ROUND_2、THIRD→ROUND_3
