# task-engine Specification

## Purpose
TBD - created by archiving change collection-state-machine. Update Purpose after archive.
## Requirements
### Requirement: Order 催收状态机

系统 SHALL 在 Order 维护显式催收状态 `collection_state`，枚举四值：NO_NEED（无需催收，未到首轮时点）/ PENDING_COLLECTION（待催收，已到当轮时点尚未接通）/ COLLECTED（已催收，当轮已接通等下一轮）/ FINALIZED（终态，轮次耗尽或已支付停催）。催收状态对催收员与监督员直观可读，可索引、可过滤、可统计。

#### Scenario: 导入预设初始催收状态
- **WHEN** 待支付订单导入，订单 win_bid_date + 首轮 day_offset <= today 且 pay_status 非 PAID
- **THEN** Order.collection_state 设为 PENDING_COLLECTION（已到首轮时点）

#### Scenario: 导入预设无需催收
- **WHEN** 待支付订单导入，订单 win_bid_date + 首轮 day_offset > today
- **THEN** Order.collection_state 设为 NO_NEED（未到首轮时点）

#### Scenario: 导入无 risk_tier 或无配置回退无需催收
- **WHEN** 待支付订单导入，订单无 risk_tier 或当前无生效风险档配置
- **THEN** Order.collection_state 设为 NO_NEED，等配置就绪后跑批推进

#### Scenario: 重复导入不改催收状态
- **WHEN** 待支付 CSV 重复导入已存在订单
- **THEN** 更新风险概率与特征字段，Order.collection_state 不变（状态由跑批/回填/已支付导入驱动）

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


### Requirement: 任务分配档内负载均衡且保留未完成任务 assignee

系统 SHALL 将 PENDING_ASSIGN 任务按风险档 HIGH>MEDIUM>LOW + 账龄倒序排序，档内按当前最低负载轮询分配给活跃催收员。昨天未完成的 IN_PROGRESS 任务 MUST 保留原 assignee，不回分配池。

#### Scenario: 档内负载均衡分配
- **WHEN** 跑批生成若干 PENDING_ASSIGN 任务，活跃催收员 N 名
- **THEN** 每个风险档的任务在该档内按最低负载轮询分配，同档各催收员任务数差 <= 1

#### Scenario: 未完成任务保留 assignee
- **WHEN** 跑批时某任务为 IN_PROGRESS（昨天未完成）
- **THEN** 该任务保留原 assignee，不重新分配，不进入新任务分配池

#### Scenario: 无活跃催收员跳过
- **WHEN** 没有活跃催收员（role=COLLECTOR 且 is_active）
- **THEN** PENDING_ASSIGN 任务不被分配，记录 skipped，等待有活跃催收员后下次跑批分配

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

### Requirement: 监督员催收状态过滤与完成进度

监督员 SHALL 可按 collection_state 过滤任务列表，MUST 可查看各催收员当天完成进度（已接通/未接通/待处理计数）。

#### Scenario: 按 collection_state 过滤任务
- **WHEN** 监督员在任务列表按 collection_state=PENDING_COLLECTION 过滤
- **THEN** 仅返回 collection_state=PENDING_COLLECTION 的订单关联的任务

#### Scenario: 查看各催收员当天完成进度
- **WHEN** 监督员请求各催收员完成进度
- **THEN** 返回每名催收员当天的「已接通数 / 未接通数 / 待处理数」计数，按催收员列出

#### Scenario: 改派保留催收状态
- **WHEN** 监督员改派某 IN_PROGRESS 任务给另一催收员
- **THEN** Task.assignee 变更，Task.status 保持 IN_PROGRESS，Order.collection_state 不变（改派不改催收状态）

