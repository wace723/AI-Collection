## MODIFIED Requirements

### Requirement: 跑批按状态机推进催收状态

每日跑批 SHALL 扫描所有待支付订单（pay_status 非 PAID），按各档配置的 day_offset 升序划分区间，为每个订单维护**唯一一个活跃任务**（当前区间对应的任务）。跑批 MUST 在每日凌晨定时、待支付导入成功后、系统启动时三个时机触发。

#### Scenario: 单活跃任务模型
- **WHEN** 跑批时一个订单有多个活跃任务（旧多轮并存数据）
- **THEN** 保留当前区间对应的任务，删除其他活跃任务，一个订单同时只有一个活跃 Task

#### Scenario: 到达首轮区间生成任务
- **WHEN** 跑批时订单 age_days（today - win_bid_date）>= 首轮 day_offset（d1），且该区间无活跃任务
- **THEN** collection_state 推进为 PENDING_COLLECTION，生成当前区间任务（day_offset=当前区间 d1，status=PENDING_ASSIGN）

#### Scenario: 同区间幂等不重复生成
- **WHEN** 跑批时订单当前区间已有活跃任务（day_offset == 当前区间 day_offset）
- **THEN** 不重复生成任务，不删除现有任务，collection_state 保持

#### Scenario: 跨区间删旧生新
- **WHEN** 跑批时订单已进入新区间（当前区间 day_offset 变化），旧区间活跃任务存在
- **THEN** 删除旧区间活跃任务（不管 DONE/IN_PROGRESS），生成新区间任务（day_offset=新区间，PENDING_ASSIGN），collection_state 推进为 PENDING_COLLECTION

#### Scenario: 已接通跨区间仍生成新区间任务
- **WHEN** 上一轮任务已接通（DONE），跑批时订单已进入新区间
- **THEN** 删除已接通的旧任务，生成新区间任务（每轮独立催收，上一轮接通不影响这轮）

#### Scenario: 未到首轮区间无任务
- **WHEN** 跑批时订单 age_days < 首轮 day_offset
- **THEN** collection_state 保持 NO_NEED，不生成任务

#### Scenario: 通用多轮适配各档配置
- **WHEN** 某风险档配置多个 day_offset（如 HIGH [7,15,30]，或 MEDIUM [15,30,60]）
- **THEN** 按该档所有 day_offset 升序划区间，每个区间一个任务，跨区间删旧生新

#### Scenario: 已支付订单不推进不生成
- **WHEN** 跑批时订单 pay_status=PAID
- **THEN** 不推进 collection_state，不生成任务，不删除任务

#### Scenario: 跑批幂等
- **WHEN** 同日重复跑批同一订单（含导入后跑批+启动跑批+定时跑批）
- **THEN** 同区间不重复生成，不重复删除，状态与任务只生效一次

### Requirement: 回填结果两分类推进催收状态

催收员回填任务结果 SHALL 只分两类：UNREACHED（未接通）/ REACHED（已接通）。已接通可填自由文本反馈内容。回填不影响跨区间任务替换（跨区间由跑批处理）。

#### Scenario: 回填已接通推进已催收
- **WHEN** 催收员对当前区间活跃任务（IN_PROGRESS）回填 result=REACHED，附自由文本反馈 note
- **THEN** Task.status → DONE（终态），Task.result=REACHED，Order.collection_state → COLLECTED，写一条 TaskResult 明细

#### Scenario: 回填未接通保持待催收
- **WHEN** 催收员对当前区间活跃任务回填 result=UNREACHED
- **THEN** Task.status 保持 IN_PROGRESS，Order.collection_state 保持 PENDING_COLLECTION，写一条 TaskResult 明细

#### Scenario: 同日反复回填未接通
- **WHEN** 同一任务同日多次回填 result=UNREACHED
- **THEN** 每次写一条 TaskResult 明细，Task 保持 IN_PROGRESS，直到回填 REACHED 或跨区间删旧生新

#### Scenario: 终态任务不可回填
- **WHEN** 催收员对 DONE 任务回填
- **THEN** 返回 409 状态机错误

#### Scenario: 跨区间后旧任务已删除不可回填
- **WHEN** 订单跨区间后旧任务被删除，催收员回填旧任务 ID
- **THEN** 返回 404 任务不存在（旧任务已删）

### Requirement: 已支付导入回写终态停催

已支付订单导入回写 pay_status=PAID 时，系统 SHALL 同步推进 collection_state 为终态 FINALIZED 并删除该订单所有活跃任务。

#### Scenario: 已支付导入推进终态并删除活跃任务
- **WHEN** 已支付 CSV 导入匹配到待支付订单，回写 pay_status=PAID
- **THEN** Order.collection_state → FINALIZED，该订单所有活跃任务（PENDING_ASSIGN/IN_PROGRESS/DONE）被删除，计入 updated

#### Scenario: 已支付导入无匹配跳过
- **WHEN** 已支付 CSV 某行 service_fee_order_no 无匹配待支付订单
- **THEN** 该行跳过，不计入 updated

#### Scenario: 已支付订单匹配但已 PAID 跳过
- **WHEN** 已支付 CSV 某行匹配的订单 pay_status 已为 PAID
- **THEN** 该行跳过，不计入 updated
