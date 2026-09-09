# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。
> 本仓库由 Claude Code（`CLAUDE.md`）与 CodeBuddy（`CODEBUDDY.md`）共用同一套 harness 工件开发。

## 当前已验证

- 现在明确可用的部分：infra-001 骨架、infra-002 鉴权、data-001 CSV 上传解析、risk-001 Mock 风险计算、risk-002 风险档配置、**task-001 催收任务生成（跑批+幂等+定时调度）**
- 这轮实际跑过的验证（Session 007 / CodeBuddy）：
  - 后端 pytest 全量 **74 passed**（3 health + 9 auth + 9 data + 16 risk + 17 risk_config + 20 task_generation）
  - alembic 增量迁移 `c4a2b9d1e0f1` 应用成功：tasks 唯一约束 `uq_tasks_batch_order_day`（batch_id+order_id+day_offset）生效
  - 端到端真实数据：dev.db 20 条未支付订单跑批 → 30 任务（HIGH 15/MEDIUM 12/LOW 3，batch=2026-09-09）；同日重跑 → generated=0 / idempotent_skipped=30
  - 前端 npm run build 通过（无改动，回归确认）

## 本轮改动（task-001 + 双工具 harness）

- 后端新增/变更：
  - `services/task_engine/batch.py`（新）：`generate_tasks` 核心逻辑 + `run_batch`（recalc_risk 编排）+ `BatchResult` + `BatchNotReadyError`
  - `services/task_engine/__init__.py`：导出 generate_tasks/run_batch/BatchResult
  - `scheduler/`（新）：`jobs.py` run_daily_batch_job + build_scheduler（cron `0 0 * * *`，settings.BATCH_RUN_CRON 可配）
  - `api/tasks.py`（新）：POST `/api/tasks/batch/run`（ADMIN，`?recalc=true`）、GET `/api/tasks/batch/status/{batch_id}`（登录）
  - `schemas/task.py`（新）：BatchRunOut/BatchStatusOut
  - `models/task.py`：加复合唯一约束；`main.py`：lifespan 启动/关闭 APScheduler；`core/config.py`：BATCH_RUN_CRON；`requirements.txt`：APScheduler==3.10.4
- 新增 harness：`CODEBUDDY.md`（CodeBuddy 路由层，与 CLAUDE.md 平行、共享状态文件）
- 测试 `tests/test_task_generation.py` 20 用例

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：task-002 及之后功能均 not_started
- 下一轮会话需要注意的风险：
  - SQLite BigInteger 自增问题已修复，勿重新引入裸 `BigInteger()` 主键（沿用记录）
  - 测试内存 SQLite 必须用 StaticPool（沿用记录）
  - vite 监听 IPv6，前端访问用 `localhost` 不是 `127.0.0.1`（沿用记录）
  - 后端默认端口 8000
  - **APScheduler 3.10.4** 在 Python 3.13 可用（已验证 import + lifespan 启动路径）；真实 0 点触发行为待长期运行观察
  - scheduler job 异常 logger.exception 后抛出由 APScheduler 捕获（失败可观察）
  - run_batch recalc=True 会对整库订单重算风险（复用 risk-001 编排器，幂等无害）；无特征订单 mock=50 → MEDIUM
  - 幂等语义：业务去重键是 `(order_id, day_offset)` 且排除 CANCELLED（跨日补跑不重复）；DB 约束仍是 batch+order+offset 三元组
  - 坑点：config_service 变更后需 `db.expire_all()`（沿用 Session 006 记录）
  - dev.db 现含 30 条本地演示任务（2026-09-09 batch），属本地数据不影响仓库

## 下一步最佳动作

- 最高优先级未完成功能：`task-002` 任务分配（将 PENDING_ASSIGN 任务分给 3 名催收员）
- 为什么它是下一步：task-001 已生成 30 条真实任务（PENDING_ASSIGN），task-002 在此基础上实现分配闭环，之后 wb-001 工作台才有数据可看
- 什么结果才算 passing（对应 docs/03 TC-TASK-09~12 与 docs/02 §4.3）：
  - 未分配任务批量分配给催收员（对应 TC-TASK-09）
  - 分配后任务 status PENDING（对应 TC-TASK-10）
  - 已分配/已处理任务不重复分配（对应 TC-TASK-11）
  - 全部任务都有 assignee（对应 TC-TASK-12，含按规则轮询/负载均衡）
  - 支持手动触发分配
- 这一步中哪些东西不要动：
  - docs/ 下需求架构（已是基线）
  - `generate_tasks`/`run_batch`/BatchResult 契约（task-001 已落地）
  - `Task` 模型 status 枚举与 batch 幂等约束
  - RiskProvider/config_service 等 risk 部分
  - CLAUDE.md / CODEBUDDY.md 的设计约束

## task-002 实现要点（给新会话的提示）

- 复用：`Task`（status=PENDING_ASSIGN/batch_id）、`User`（role=COLLECTOR 3 名）、`APIResponse[T]`、`require_role`
- 新建（建议）：
  - `services/task_engine/assignment.py`：`assign_pending_tasks`（规则：按轮询 round-robin 或按现有负载最少的催收员；从 db 取 PENDING_ASSIGN → 分配 → status=PENDING + assignee_id + assigned_at）
  - `api/tasks.py`：追加 POST `/api/tasks/assign/run`（ADMIN）或并入 batch/run 编排
- 核心语义（docs/02 §4.3）：已分配/已完成不重复分配；每名催收员负载均衡
- 参考 docs/02 §4.3、docs/03 TC-TASK-09~12/14
- 分配后 run_batch 的幂等跳过逻辑（(order_id, day_offset) 非 CANCELLED）不会影响已分配任务——task-002 需注意不能重复生成已分配任务对应时点

## 命令

- 启动命令：`./init.sh`（bash；PowerShell 下 `bash ./init.sh` 或按 CODEBUDDY.md 分步命令）
- 验证命令：后端 `cd backend && .venv\Scripts\python.exe -m pytest -q`；前端 `cd frontend && npm run build`
- 种子数据：`cd backend && .\.venv\Scripts\Activate.ps1 && python seed.py`（用户 + 风险档配置 v1）
- 启动后端：`uvicorn app.main:app --reload --port 8000`（localhost 访问）
- 启动前端：`npm run dev`（5173，localhost 访问）
- 默认账号：admin/supervisor/collector1-3，密码 admin123
- 关键接口：
  - 上传 CSV：`POST /api/data/upload`
  - 风险重算：`POST /api/data/orders/recalc-risk`
  - 风险配置：`GET/PUT /api/config/risk/current`、`POST /api/config/risk/rollback/{version}`
  - 手动跑批：`POST /api/tasks/batch/run?recalc=true`（ADMIN）
  - 批次状态：`GET /api/tasks/batch/status/{batch_id}`（登录）
