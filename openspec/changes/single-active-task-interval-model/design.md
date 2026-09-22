## Context

当前任务模型是「多轮并存」：一个订单可同时有多个 Task（HIGH 档 7/15/30 天三轮任务并存）。跑批（`generate_tasks`）扫描 ADVANCEABLE_STATES（NO_NEED/PENDING_COLLECTION/COLLECTED）订单，找到「下一个未催轮次」（第一个到期且无 Task 的 day_offset）生成一个 Task。旧订单多轮都到期时，需要多次跑批逐轮生成（因每次只生成一轮，下一轮该轮已有 Task 跳过看下轮）。

实际使用问题：导入 8348 条待支付 CSV 后，同一天触发 4 次跑批（导入后自动跑批 + 启动时自动跑批 + 定时 + 手动），HIGH 档 3 轮都到期，4 次跑批生成了 7/15/30 三个并存任务（共 7542 个 PENDING_ASSIGN），而 MEDIUM/LOW 只有 1 轮配置一次生成完。催收员/主管看到"只有 HIGH 任务"且大量未分配，语义混乱。

业务真实意图：一个订单同一时间只有一个活跃任务（当前催收区间的），跨区间时旧任务删除、生成新区间任务，不管旧任务是否完成。

## Goals / Non-Goals

**Goals:**
- 单活跃任务模型：一个订单同一时间只有一个活跃 Task
- 区间划分：按各档 day_offset 升序划区间，每个区间一个任务
- 跨区间删旧生新：进入新区间时删除旧任务，生成新区间任务
- 通用多轮适配：所有风险档按各自配置的 day_offset 划区间
- 多次跑批幂等：同一区间不重复生成

**Non-Goals:**
- 不改回填两分类（REACHED/UNREACHED 不变）
- 不改分配算法（档内负载均衡不变）
- 不改改派（保持 IN_PROGRESS 改派不变）
- 不改风险概率来源/风险档配置
- 不改 CSV 列映射
- 不做任务历史保留（旧任务直接删除，不归档）

## Decisions

### D1: 区间划分算法

按各档配置的所有 day_offset 升序 `[d1, d2, ..., dn]`，结合 `win_bid_date` 和 `today` 算「当前区间对应的 day_offset」：

```
age_days = (today - win_bid_date).days

if age_days < d1:  → 无任务（未到首轮区间），collection_state=NO_NEED
elif age_days < d2: → 当前区间 d1（任务 day_offset=d1）
elif age_days < d3: → 当前区间 d2（任务 day_offset=d2，d1 任务应删除）
...
elif age_days < dn: → 当前区间 d(n-1)
else (age_days >= dn): → 当前区间 dn（最后一轮）
```

即「当前区间 day_offset = 最大的那个 day_offset 使得 win_bid_date + day_offset <= today」。

**边界**：若只有 1 个 day_offset（如 MEDIUM=[30], LOW=[90]），则 age>=30 → d1 任务，只有一轮。

### D2: 跑批逻辑重写（单活跃任务）

`generate_tasks` 重写为：
1. 扫描所有待支付订单（pay_status 非 PAID，不限 collection_state，因为跨区间需处理所有订单）
2. 对每单，按 D1 算当前区间 day_offset（`current_offset`）
3. 若无当前区间（age < d1，未到首轮）→ collection_state=NO_NEED，跳过
4. 若有当前区间：
   - 查该订单现有的**活跃任务**（非 CANCELLED，即 PENDING_ASSIGN/IN_PROGRESS/DONE）
   - 若活跃任务的 day_offset == current_offset → 同区间，不重复生成（幂等），collection_state=PENDING_COLLECTION（若已是 COLLECTED 保持）
   - 若活跃任务的 day_offset != current_offset（或无活跃任务但应有）→ **删除旧活跃任务**，生成新 Task（day_offset=current_offset, PENDING_ASSIGN），collection_state=PENDING_COLLECTION
   - 若所有轮次都过期（age >= dn 但已过最后轮次且配置无更多）→ 保持最后轮任务（或 FINALIZED？见 D3）

**关键**：DONE 任务跨区间也删除（每轮独立催收，上一轮接通不代表这轮不催）。

### D3: 轮次耗尽终态

最后一个 day_offset dn 之后，age >= dn 永远成立，任务停留在 dn 这轮（不删除不替换，因为没有更后的区间）。collection_state 保持 PENDING_COLLECTION/COLLECTED。

是否要 FINALIZED？业务意图：所有轮次都催完仍待支付，进入终态等人工介入。但「最后一个区间之后」没有更后区间，任务停在 dn 轮反复催。

决策：**最后区间任务保持**，不进 FINALIZED（除非已支付）。FINALIZED 只由「已支付导入」触发。轮次耗尽不自动终态（避免漏催）。collection_state 保持 PENDING_COLLECTION（或 COLLECTED 若已接通）。后续可加「最后轮重复催收间隔」配置，本轮 Non-Goal。

### D4: 状态机（保留 COLLECTED）

```
NO_NEED ──到首轮区间──▶ PENDING_COLLECTION（生成首轮任务）
PENDING_COLLECTION ──回填REACHED──▶ COLLECTED（当前区间已催收）
COLLECTED ──到下一区间（跑批）──▶ PENDING_COLLECTION（删旧生新）
PENDING_COLLECTION/COLLECTED ──已支付──▶ FINALIZED（删活跃任务）
```

跨区间时 COLLECTED 回 PENDING_COLLECTION（旧任务删除，新区间任务生成）。

### D5: 已支付导入删除活跃任务

`ingest_paid_rows` 回写 pay_status=PAID 时：
- collection_state → FINALIZED
- **删除该订单所有活跃任务**（PENDING_ASSIGN/IN_PROGRESS/DONE 全部删除，替代当前的 CANCELLED）

删除而非 CANCELLED：简化模型（活跃任务要么存在要么不存在，无 CANCELLED 中间态）。历史在 TaskResult 表（回填明细）保留。

### D6: 数据迁移

现有 dev.db 有并存多轮任务，需清理。迁移策略：**清空 tasks 表**（开发期数据可重建），跑批重新生成。生产环境首次部署跑批自动规整。

不写 Alembic 数据迁移（tasks 表结构不变），清空由部署脚本/手动处理。

## Risks / Trade-offs

- **[BREAKING 任务模型] → 现有数据需清理**：tasks 表清空重建，开发期可接受。生产环境首次跑批自动规整。
- **[删除旧任务] → 历史丢失**：旧任务直接删除，TaskResult 明细成为孤儿（task_id 指向已删任务）。缓解：TaskResult 保留（外键 ondelete CASCADE 会删明细？需检查）。决策：TaskResult 跟随 Task 删除（CASCADE），历史不保留（业务接受，每轮独立催收不需历史关联）。
- **[跑批扫描全量] → 性能**：跑批不再只扫 ADVANCEABLE_STATES，扫描所有待支付订单算区间。8348 订单可接受。生产大数据量可加索引/优化（Non-Goal）。
- **[跨区间删旧生新] → 已分配任务被删**：IN_PROGRESS 任务跨区间被删，催收员工作台看不到。但新区间任务重新分配，催收连续性由 assignee 保留（分配算法保留 IN_PROGRESS assignee——但任务删了重建，assignee 重置）。决策：新区间任务重新分配（PENDING_ASSIGN），不保留旧 assignee（因是新任务）。

## Migration Plan

1. 代码改造（batch.py/state.py/parser.py）
2. 清空 tasks 表（dev.db 手动 DELETE，生产部署脚本）
3. 首次跑批自动规整（每订单生成单活跃任务）
4. 回滚：代码回滚即可（任务模型语义回退，但已删任务不恢复）

## Open Questions

无（需求已通过 5 轮 AskUserQuestion 澄清）。
