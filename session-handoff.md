# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。

## 当前已验证

- 现在明确可用的部分：infra-001 骨架、infra-002 鉴权、data-001 CSV 上传与解析、risk-001 Mock 风险概率计算+RiskProvider 抽象、**risk-002 风险档配置（阈值+催收时点，版本化）**
- 这轮实际跑过的验证：
  - 后端 pytest 54 passed（3 health + 9 auth + 9 data + 16 risk + 17 risk_config）
  - 端到端真实联调：seed v1(70/30)+5 schedules → 上传CSV 20条 → recalc HIGH=5/MEDIUM=12/LOW=3 → PUT(60/30)→v2 → recalc HIGH=8/MEDIUM=9/LOW=3（3笔M升H）→ rollback/1 → v3(=70/30) active → history=[v3 active, v2/v1 inactive]
  - 前端 npm run build 通过；Config 页风险档配置面板（当前配置+编辑表单+历史回滚）
  - init.sh 退出码 0

## 本轮改动（risk-002）

- 新增了哪些代码或行为：
  - 后端 `schemas/config.py`：RiskTierEnum/SceneEnum + ScheduleOut/RiskConfigOut + ScheduleIn/RiskConfigUpdateIn（model_validator 校验 high>medium、day_offset 正整数、枚举）
  - 后端 `services/risk_engine/config_service.py`：ConfigSnapshot(frozen) + DEFAULT_SCHEDULES(5条) + get_current_config/get_config_history/update_config/rollback_to_version/seed_default_config
  - 后端 `api/config.py`：GET /risk/current（登录可见）、PUT /risk（ADMIN）、GET /risk/history（ADMIN）、POST /risk/rollback/{version}（ADMIN）
  - 后端 `api/router.py`：挂载 /config；`risk_engine/__init__.py`：导出 config_service；`seed.py`：加 seed_default_config 幂等种子
  - 前端 `types/api.ts`：追加 RiskTier/Scene/CollectionSchedule/RiskConfig/RiskConfigUpdate；`api/config.ts`：4 函数
  - 前端 `pages/Config/RiskConfigPanel.tsx`（新）：当前配置展示+编辑表单（阈值+可增删催收时点+恢复默认）+历史回滚
  - 前端 `pages/Config/index.tsx`：引入 RiskConfigPanel
  - 测试 `tests/test_risk_config.py` 17 用例
- 基础设施或 harness 发生了哪些变化：
  - 无表结构变更（RiskConfig/CollectionSchedule 表 infra-001 已建好）
  - seed.py 现在同时 seed 用户 + 风险档配置

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：task-001 及之后功能均 not_started
- 下一轮会话需要注意的风险：
  - SQLite BigInteger 自增问题已彻底修复，勿重新引入裸 `BigInteger()` 作主键（沿用记录）
  - 测试内存 SQLite 必须用 StaticPool（沿用记录）
  - vite 监听 IPv6，前端访问用 `localhost` 不是 `127.0.0.1`（沿用记录）
  - 后端默认端口 8000
  - **坑点**：`config_service._deactivate_all` 用 `synchronize_session=False` 后**必须 `db.expire_all()`**，否则 identity map 缓存旧 is_active，后续 query 返回错误值
  - 回滚=方案B（复制为新版本），历史表会增长
  - `_load_schedules` 按 Python 端业务序排序（HIGH<MEDIUM<LOW），勿用 DB `func.case(else_=)`（此 SQLAlchemy 版本不支持 else_ 关键字）

## 下一步最佳动作

- 最高优先级未完成功能：`task-001` 催收任务生成（跑批核心逻辑）
- 为什么它是下一步：risk-002 已提供催收时点配置（collection_schedules 表：HIGH 7/15/30、MEDIUM 30、LOW 90），task-001 在此基础上跑批——扫描未支付订单，命中催收时点且未支付→生成任务，幂等控制
- 什么结果才算 passing：
  - 高风险多轮任务按时点生成（TC-TASK-01）
  - 未到时点不生成（TC-TASK-02）
  - 已支付订单不生成（TC-TASK-03）
  - 到时点但已支付跳过（TC-TASK-04）
  - 重复跑批幂等（TC-TASK-05）
  - 中/低风险时点正确（TC-TASK-06/07/08）
  - 支持手动触发跑批
- 这一步中哪些东西不要动：
  - docs/ 下需求架构（已是基线）
  - RiskProvider 抽象 + MockRiskProvider 公式（risk-001 已落地）
  - tier_mapper 的 get_active_thresholds/map_tier 纯函数（risk-001 已落地）
  - config_service 的版本化/回滚逻辑（risk-002 已落地）
  - RiskConfig/CollectionSchedule 模型字段
  - CLAUDE.md 的设计约束

## task-001 实现要点（给新会话的提示）

- 复用：
  - `RiskConfig`/`CollectionSchedule` 模型（risk.py 已建好）
  - `config_service.get_current_config(db)` 取当前生效配置 + schedules（risk-002）
  - `Order` 模型（pay_status/win_bid_date/risk_tier 字段）
  - `Task` 模型（task.py 已建好：order_id/service_fee_order_no/risk_tier/scene/day_offset/due_date/status/batch_id 等）
  - `APIResponse[T]`、`require_role("ADMIN")`、`get_db`
- 新建：
  - `app/scheduler/` 或 `app/services/task_engine/scheduler.py`（APScheduler 跑批，cron 0 0 * * *）
  - `app/services/task_engine/batch.py`（跑批核心逻辑 generate_tasks）
  - `app/api/tasks.py`（POST /api/tasks/batch/run 手动触发，ADMIN）
  - `app/schemas/task.py`（TaskOut/BatchResult 等）
- 核心逻辑（docs/02 §4.2.2）：
  - 取 active config + schedules
  - 查所有未支付订单（pay_status != 'PAID'）
  - 对每订单每个 schedule：due_date = win_bid_date + day_offset；若 due_date <= today 且 pay_status != 'PAID' 且 task_exists(order_id, day_offset, batch_id) 为假 → 生成 task
  - 幂等：batch_id（当日日期）+ order_id + day_offset 三元组唯一
  - batch_id 用当日日期（TC-TASK-13）
- 种子数据：可能需补未支付订单种子（或直接用 data-001 上传的真实订单）
- 参考 docs/02 §4.2、docs/03 TC-TASK-01~08/13

## 命令

- 启动命令：`./init.sh`（骨架就绪后 `RUN_START_COMMAND=1 ./init.sh`）
- 验证命令：后端 `cd backend && pytest -q`；前端 `cd frontend && npm run build`
- 种子数据：`cd backend && source .venv/Scripts/activate && python seed.py`（用户 + 风险档配置 v1）
- 启动后端：`cd backend && uvicorn app.main:app --reload --port 8000`（用 localhost 访问）
- 启动前端：`cd frontend && npm run dev`（5173，用 localhost 访问）
- 默认账号：admin/supervisor/collector1-3，密码 admin123
- 风险重算：`POST /api/data/orders/recalc-risk`（需先上传 CSV）
- 风险配置：`GET /api/config/risk/current`、`PUT /api/config/risk`、`GET /api/config/risk/history`、`POST /api/config/risk/rollback/{version}`
