## ADDED Requirements

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

每日跑批 SHALL 扫描 collection_state 为 NO_NEED 或 COLLECTED 且 pay_status 非 PAID 的订单，按各轮催收时点（win_bid_date + day_offset）推进状态并生成当轮任务。

#### Scenario: 到达首轮时点推进待催收
- **WHEN** 跑批时订单 collection_state=NO_NEED，且 win_bid_date + 首轮 day_offset <= today，且 pay_status 非 PAID
- **THEN** Order.collection_state 推进为 PENDING_COLLECTION，生成首轮 Task（day_offset=首轮值，status=PENDING_ASSIGN）

#### Scenario: 到达下一轮时点推进待催收
- **WHEN** 跑批时订单 collection_state=COLLECTED，且 win_bid_date + 下一轮 day_offset <= today（该轮无非 CANCELLED Task），且 pay_status 非 PAID
- **THEN** Order.collection_state 推进为 PENDING_COLLECTION，生成下一轮 Task（day_offset=下一轮值，status=PENDING_ASSIGN）

#### Scenario: 已支付订单不推进不生成
- **WHEN** 跑批时订单 pay_status=PAID
- **THEN** 不推进 collection_state，不生成催收任务（无论当前状态与时点）

#### Scenario: 未到时点不推进
- **WHEN** 跑批时订单 collection_state=NO_NEED，但 win_bid_date + 首轮 day_offset > today
- **THEN** collection_state 保持 NO_NEED，不生成任务

#### Scenario: 轮次耗尽进入终态
- **WHEN** 跑批时订单所有配置的催收轮次都已催过，且仍待支付
- **THEN** Order.collection_state 推进为 FINALIZED，不再生成新催收任务

#### Scenario: 跑批幂等
- **WHEN** 同日重复跑批同一订单
- **THEN** 状态推进与任务生成只生效一次（batch_id + order_id + day_offset 唯一约束兜底），重复跑批 generated=0

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

催收员回填任务结果 SHALL 只分两类：UNREACHED（未接通）/ REACHED（已接通）。已接通 MUST 可填自由文本反馈内容。

#### Scenario: 回填已接通推进已催收
- **WHEN** 催收员对 IN_PROGRESS 任务回填 result=REACHED，附自由文本反馈 note
- **THEN** Task.status → DONE（终态），Task.result=REACHED，Order.collection_state → COLLECTED，写一条 TaskResult 明细

#### Scenario: 回填未接通保持待催收
- **WHEN** 催收员对 IN_PROGRESS 任务回填 result=UNREACHED
- **THEN** Task.status 保持 IN_PROGRESS，Order.collection_state 保持 PENDING_COLLECTION，写一条 TaskResult 明细

#### Scenario: 同日反复回填未接通
- **WHEN** 同一任务同日多次回填 result=UNREACHED
- **THEN** 每次写一条 TaskResult 明细，Task 保持 IN_PROGRESS，直到回填 REACHED 或进入下一轮

#### Scenario: 终态任务不可回填
- **WHEN** 催收员对 DONE 或 CANCELLED 任务回填
- **THEN** 返回 409 状态机错误，不可再变更

#### Scenario: 催收员只能回填自己任务
- **WHEN** COLLECTOR 回填非自己 assignee 的任务
- **THEN** 返回 403 无权操作他人任务（SUPERVISOR/ADMIN 可代理）

### Requirement: 已支付导入回写终态停催

已支付订单导入回写 pay_status=PAID 时，系统 SHALL 同步推进 collection_state 为终态并停催未完成任务。

#### Scenario: 已支付导入推进终态
- **WHEN** 已支付 CSV 导入匹配到待支付订单，回写 pay_status=PAID
- **THEN** Order.collection_state → FINALIZED，该订单所有非终态 Task（PENDING_ASSIGN/IN_PROGRESS）→ CANCELLED，result_note 标注「已支付停催」

#### Scenario: 已支付导入无匹配跳过
- **WHEN** 已支付 CSV 某行 service_fee_order_no 在数据库无匹配待支付订单
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
