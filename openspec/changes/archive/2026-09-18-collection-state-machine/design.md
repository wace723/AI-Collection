## Context

当前系统（data-002 收尾后）的催收状态是**隐式**的：

- Order 只有 `pay_status`（待支付/已支付），**无催收状态字段**。催收到第几轮隐含在 Task.day_offset 里，需查询该订单的 Task 才能推导。
- 跑批逻辑（`batch.py::generate_tasks`）扫描未支付订单，命中 `win_bid_date + day_offset <= today` 生成 Task（幂等键 order_id+day_offset），但 Order 本身没有「现在催到第几轮」的显式状态。
- 回填结果分五类（PAID/PROMISE/DISPUTE/LOST_CONTACT/OTHER），语义含糊，无法表达「该轮是否真正接通」这一催收核心事实。PROMISE 还涉及改期回 PENDING 的复杂分支。
- 状态机现状（`state.py`）：PENDING_ASSIGN → 分配 → IN_PROGRESS → 回填 → DONE（或 PROMISE→改期→IN_PROGRESS）。task-002 已去掉领取步骤。

业务方希望催收状态对催收员/监督员**直观可读**：每天登录看到「今天该催哪些、催到第几轮、接通没有」，回填只关心「接通没接通」，监督员能看到每个催收员的当天完成进度。

约束（CLAUDE.md 关键设计约束不可违反）：
1. 风险概率来源是 CSV 导入（非系统预测），本改造不动风险概率来源
2. 任务幂等：batch_id + order_id + day_offset 三元组唯一（保留）
3. 催收触发：到达催收时点**且届时仍未支付**才生成任务（保留，状态机推进同样受 pay_status 门控）
4. 分配后直接 IN_PROGRESS（无领取步骤），PROMISE 改期回 IN_PROGRESS（保留 assignee）

## Goals / Non-Goals

**Goals:**
- Order 新增显式 `collection_state` 状态机字段，催收状态对业务可读
- 跑批按状态机推进：到达下一轮 day_offset 且仍待支付 → 推进状态 + 生成/激活当轮 Task
- 回填结果收敛为「未接通/已接通」两分类，已接通推进该轮 collection_state→已催收
- 导入时按中标日 + 首轮 day_offset 预设 collection_state 初始值
- 已支付导入 → collection_state 终态 + 停催未完成任务
- 轮次耗尽 → 终态
- 监督员视图补：按 collection_state 过滤 + 各催收员当天完成进度计数

**Non-Goals:**
- 不改风险概率来源（仍是 CSV 导入）
- 不改风险档阈值/催收时点配置（risk-002 表结构不动，仅作为状态机推进时点来源）
- 不改话术引擎（talk-001/002）
- 不改大盘聚合口径（dash-001 回款率语义不变，回款仍由已支付导入驱动）
- 不引入按档隔离催收员（保持档内负载均衡）
- 不改 CSV 列映射（待支付 38 列/已支付 39 列不变）
- 不做催收员手动标记已支付（支付状态仅导入更新）

## Decisions

### D1: Order.collection_state 状态机字段 + 四值枚举

新增字段，枚举四值：
- `NO_NEED`（无需催收）：未到首轮催收时点
- `PENDING_COLLECTION`（待催收）：已到当轮时点、尚未接通
- `COLLECTED`（已催收）：当轮已接通，等下一轮时点
- `FINALIZED`（终态）：轮次耗尽 或 已支付停催

状态流转：
```
导入 → NO_NEED 或 PENDING_COLLECTION（按 win_bid_date + 首轮 day_offset 预设）
NO_NEED ──到达首轮时点且待支付──▶ PENDING_COLLECTION（生成首轮 Task）
PENDING_COLLECTION ──回填已接通──▶ COLLECTED（当轮 Task DONE）
COLLECTED ──到达下一轮时点且待支付──▶ PENDING_COLLECTION（生成下一轮 Task）
COLLECTED ──轮次耗尽且待支付──▶ FINALIZED
任意态 ──已支付导入──▶ FINALIZED（停催，未完成任务 CANCELLED）
```

**为什么不用推导**：业务方明确要求催收状态对催收员/监督员直观可读，落库字段可索引、可过滤、可统计，无需每次推导。推导还需 join Task 表，性能与可读性都差。

**替代方案考虑**：纯推导（不加字段，从 Task 现状算）——被否，原因如上。

### D2: 回填结果两分类（UNREACHED/REACHED），Task 状态机简化

Task.result 枚举从 `{PAID, PROMISE, DISPUTE, LOST_CONTACT, OTHER}` 改为 `{UNREACHED, REACHED}`。**BREAKING**。

- `UNREACHED`（未接通）：该轮仍算待催收，Task 保持 IN_PROGRESS（同日可反复回填，每次写一条 TaskResult 明细），Order.collection_state 保持 PENDING_COLLECTION
- `REACHED`（已接通）：填自由文本反馈 note，该轮算已催收，Task.status → DONE，Order.collection_state → COLLECTED

去掉 PROMISE 改期分支（业务方确认回填只分接通/未接通，不再有 PROMISE 改期语义）。

**Task 状态机简化后**：
```
PENDING_ASSIGN ──分配──▶ IN_PROGRESS ──回填REACHED──▶ DONE(终态)
                                    └─ 回填UNREACHED ──▶ 仍 IN_PROGRESS（同日可再回填）
```

**为什么去掉 PROMISE**：业务方把回填收敛为「接通没接通」事实，承诺还款属于「已接通后的反馈内容」（自由文本），不再是独立状态分支。简化状态机，减少边界。

**风险**：现有 Task.result 旧值需迁移映射（见 Migration Plan）。

### D3: 跑批按状态机推进，保留未完成任务 assignee

`batch.py::generate_tasks` 重构为「状态机推进 + 任务生成」：

1. 扫描 `collection_state IN (NO_NEED, COLLECTED)` 且 `pay_status != PAID` 的订单
2. 对每单，取其 risk_tier 配置的所有 day_offset 排序，找出「下一个应催轮次」= 第一个 day_offset 使 `win_bid_date + day_offset <= today` 且该 (order_id, day_offset) 无非 CANCELLED Task
3. 若找到：
   - NO_NEED/COLLECTED → PENDING_COLLECTION
   - 生成/激活当轮 Task（PENDING_ASSIGN）
4. 若该单所有 day_offset 都已催过且仍待支付 → PENDING_COLLECTION → FINALIZED（轮次耗尽）

**分配阶段**（`assignment.py`）：
- 仅分配 PENDING_ASSIGN 任务（现状不变）
- IN_PROGRESS 任务（含昨天未完成的）**保留原 assignee**，不回分配池（业务方确认：隔天还分给他）
- 分配算法保持档内负载均衡（HIGH>MEDIUM>LOW + 账龄倒序 + 最低负载轮询）

**为什么保留 assignee**：业务方明确「当天没完成，隔天还分给他」。IN_PROGRESS 任务已是某人名下，重分会丢失跟进连续性。

### D4: 导入预设 collection_state 初始值

`parser.py::ingest_pending_rows`：新订单入库时按中标日预设：
- `win_bid_date + 首轮 day_offset <= today` → `PENDING_COLLECTION`
- 否则 → `NO_NEED`

首轮 day_offset 取该订单 risk_tier 对应配置中 day_offset 最小的 schedule。若无 risk_tier 或无配置 → `NO_NEED`（跑批时再推进）。

重复订单（updated）不改 collection_state（状态由跑批/回填/已支付导入驱动，导入只更新风险概率/特征/支付状态）。

### D5: 已支付导入回写 → 终态 + 停催

`parser.py::ingest_paid_rows`：匹配订单回写 pay_status=PAID 时：
- `Order.collection_state → FINALIZED`
- 该订单所有非终态 Task（PENDING_ASSIGN/IN_PROGRESS）→ `CANCELLED`，result_note 标注「已支付停催」

### D6: 监督员视图增强

现有 supervisor 已能看所有任务 + 改派 + 绩效（Session 014）。本轮补：
- 任务列表加 `collection_state` 过滤
- 各催收员当天完成进度：`GET /api/supervisor/staff-progress` 扩展返回每人的「当天已接通数 / 当天未接通数 / 待处理数」计数

## Risks / Trade-offs

- **[BREAKING 回填枚举] → 旧 Task.result 值迁移**：PAID/DISPUTE/LOST_CONTACT/OTHER 映射为 REACHED（历史已处理视为已接通），PROMISE 映射为 UNREACHED（未接通的改期）。仅历史数据兼容，非业务精确。迁移脚本在 Alembic 中执行。
- **[状态机与跑批耦合] → 跑批复杂度上升**：跑批从「纯生成」变为「推进状态+生成」，需保证状态推进与 Task 生成的原子性（同一事务）。风险=部分推进导致状态与 Task 不一致。缓解：单事务内推进+生成，失败整体回滚；幂等键保证重跑安全。
- **[轮次耗尽终态] → 漏催风险**：轮次耗尽进入 FINALIZED 后不再自动催，若客户仍未支付可能漏催。缓解：FINALIZED 订单在大盘/监督员视图单独标注「待人工介入」，业务方人工跟进。
- **[同日反复回填 UNREACHED] → TaskResult 膨胀**：未接通可同日多次回填，TaskResult 明细增长。缓解：明细表设计本支持多次跟进，大盘/进度按 distinct task 计数（现状已如此），不因明细数膨胀失真。
- **[collection_state 预设依赖首轮 day_offset] → 无配置时回退 NO_NEED**：导入时若无 risk_tier 或无配置，预设 NO_NEED，等配置就绪后跑批推进。无静默错误。

## Migration Plan

1. Alembic 迁移：Order 加 `collection_state` 字段（默认 NO_NEED，非空）
2. 数据回填脚本（迁移内）：
   - 现有 Order 按 `win_bid_date + 首轮 day_offset` 回填 collection_state（已过首轮→PENDING_COLLECTION，未到→NO_NEED，已支付→FINALIZED）
   - 现有 Task.result 旧值映射：PAID/DISPUTE/LOST_CONTACT/OTHER → REACHED；PROMISE → UNREACHED
   - 现有 Task.status：PROMISE 改期的 PENDING 任务 → IN_PROGRESS（去掉 PENDING 改期态）
3. 部署后首日跑批：推进所有 NO_NEED/COLLECTED 中已到时点的订单
4. 回滚：若状态机有问题，回滚代码即可（collection_state 字段保留无害，旧代码不读它）；Task.result 旧值已映射不可逆，回滚需接受历史回填按新枚举

## Open Questions

无（需求已通过 4 轮 AskUserQuestion 充分澄清）。
