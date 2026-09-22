## Context

data-003 催收状态机已上线，跑批负责推进 Order.collection_state 并生成 Task。但跑批只在每日凌晨（APScheduler cron `0 0 * * *`）或手动 POST /batch/run 触发，业务方导入 CSV 后看不到任务，体验割裂。同时真实业务 CSV 新增「工程局单位」「下属单位」两列（待支付 40 列 / 已支付 40 列），现有 38/39 列映射不支持，导入会因表头不符 400。

现状：
- `api/data.py::upload_pending` 导入后只返回 UploadSummary（inserted/updated/skipped/errors），不跑批
- `main.py::lifespan` 启动调度器但不跑批
- `columns.py` 待支付 38 列 / 已支付 39 列，无「工程局单位」「下属单位」
- 前端 Config 页导入后只有 message.success，无明细展示

## Goals / Non-Goals

**Goals:**
- CSV 列映射支持 40 列（加工程局单位/下属单位）
- 待支付导入成功后自动跑批，响应返回跑批结果
- 系统启动时自动跑批
- 前端导入后弹 Modal 展示明细 + 跑批结果

**Non-Goals:**
- 不改跑批状态机推进逻辑（复用 generate_tasks，全量跑批幂等）
- 不改已支付导入触发跑批（已支付只回写支付状态+终态停催，不生成新任务）
- 不做两步式确认入库（用户选了结果展示 Modal，非阻断）
- 不改风险概率来源/风险档配置
- 不改前端 Workbench/Supervisor（只改 Config 页导入交互）

## Decisions

### D1: 新列存 Order 表，订单级标识字段
「工程局单位」「下属单位」是中标项目归属信息（订单级，非供应商特征），存 Order 表而非 OrderFeature。字段 `engineering_bureau`、`subsidiary`（String(255)，nullable）。两套 CSV 表头都加这两列（在「标的概算金额」后、「中标日期」前，与新 CSV 位置一致）。

**为什么不存 OrderFeature**：这两列是订单/项目标识（类似标的名称、中标品类），不是供应商历史特征（如历史中标率、缴费历时）。OrderFeature 存的是供应商画像特征。

### D2: 待支付导入后自动全量跑批
`api/data.py::upload_pending` 导入成功后调用 `run_batch(db, today=date.today(), recalc_risk=False)`，全量跑批。全量跑批幂等（已有订单状态机已推进的不会重复，唯一约束兜底），不会因重复跑批产生重复任务。导入响应扩展为 UploadSummary + batch_result（generated/finalized/by_tier）。

**为什么不全量跑批**：备选「只对新导入订单跑批」需改 generate_tasks 接受 order_ids 过滤，复杂且状态机推进逻辑需遍历所有相关订单（新导入订单可能影响档位配置判断）。全量跑批简单、幂等、数据量小（MVP 级别），性能可接受。

**已支付导入不跑批**：已支付导入只回写支付状态+终态停催，不生成新任务，跑批无意义。

### D3: 系统启动时自动跑批
`main.py::lifespan` 在 `scheduler.start()` 后调用 `run_batch(db, today=date.today(), recalc_risk=False)`。启动跑批确保系统重启后立即同步任务状态（如停机期间到期的催收时点）。包在 try/except 中，跑批失败不阻断启动（记录日志）。

**为什么启动跑批**：系统可能停机跨日，重启后若不跑批，当日到期的催收时点要等到次日凌晨才处理，延迟一天。启动跑批消除这个延迟。

### D4: 导入响应扩展跑批结果
UploadSummary 加可选字段 `batch_result`（BatchRunOut 结构：generated/finalized/by_tier），待支付导入后填充，已支付导入为 None。前端据 batch_result 展示跑批统计。

### D5: 前端导入结果 Modal
Config 页两个 Dragger 上传后，弹 Modal 展示：
- 导入统计：inserted/updated/skipped/errors（错误明细列表，逐行展示 errors）
- 跑批统计（仅待支付）：generated/finalized/by_tier
- 「关闭」按钮完成

用 antd Modal + Statistic/List 组件，非阻断（用户可查看后关闭）。

### D6: PENDING_COLLECTION 纳入跑批推进范围（实施中发现的设计修正）
实施真实联调时发现 data-003 遗留缺陷：导入预设 PENDING_COLLECTION 的订单（已到首轮时点），跑批只推进 NO_NEED/COLLECTED，不推进 PENDING_COLLECTION，导致这些订单卡在「待催收但无 Task」状态。

修正：ADVANCEABLE_STATES 加 PENDING_COLLECTION。跑批对 PENDING_COLLECTION 订单：若当轮无 Task 则生成当轮 Task（状态不变，已是 PENDING_COLLECTION）；若所有轮次都有 Task 且仍待支付 → FINALIZED。幂等保证（当轮有 Task 不重复生成）。

这是对 data-003 状态机语义的修正，使「待催收 = 应有当轮 Task」语义自洽。

## Risks / Trade-offs

- **[BREAKING CSV 列数] → 旧 38/39 列 CSV 不兼容**：表头缺「工程局单位」「下属单位」会 400。缓解：业务方用新 40 列 CSV（测试数据已是 40 列）。
- **[全量跑批性能] → 大数据量导入后跑批慢**：全量跑批扫描所有 NO_NEED/COLLECTED 订单。MVP 数据量小可接受；生产大数据量可优化为增量跑批（Non-Goal，后续优化）。
- **[启动跑批失败] → 不阻断启动**：try/except 包裹，失败记日志，系统正常启动。跑批幂等，下次启动或定时会再跑。
- **[导入自动跑批事务] → 导入与跑批同事务**：导入 commit 后跑批再 commit，两步独立事务，跑批失败不影响已导入数据。

## Migration Plan

1. Alembic 迁移：Order 加 engineering_bureau/subsidiary（nullable，无默认值，历史数据为 NULL）
2. columns.py 两套表头加两列（位置：标的概算金额后、中标日期前）
3. 部署后首次导入用新 40 列 CSV
4. 回滚：回滚代码即可（新字段保留无害，旧代码不读）；旧 38 列 CSV 不可逆（需用新 40 列）

## Open Questions

无（需求已通过 3 轮 AskUserQuestion 澄清）。
