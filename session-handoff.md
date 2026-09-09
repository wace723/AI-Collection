# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。
> 本仓库由 Claude Code（`CLAUDE.md`）与 CodeBuddy（`CODEBUDDY.md`）共用同一套 harness 工件开发。

## 当前已验证

- 现在明确可用的部分：infra-001 骨架、infra-002 鉴权、data-001 CSV 上传解析、risk-001 Mock 风险计算、risk-002 风险档配置、task-001 催收任务生成、**task-002 任务分配 + 状态机**
- 这轮实际跑过的验证（Session 008 / CodeBuddy）：
  - 后端 pytest 全量 **87 passed**（…+ 13 task_assignment）
  - 端到端真实数据：dev.db 30 条 PENDING_ASSIGN → 分给 collector1/2/3 各 10 个（负载均衡差=0）
  - 状态机 API：claim（PENDING→IN_PROGRESS）、result（DONE 终态 / PROMISE 改期回 PENDING），终态 409 保护，TaskResult 明细写入
  - 前端 npm run build 通过（无改动，回归确认）

## 本轮改动（task-002）

- 后端新增/变更：
  - `services/task_engine/assignment.py`（新）：`assign_pending_tasks`（风险档排序 + 账龄倒序 + 当前最低负载者轮询）+ `AssignmentResult`
  - `services/task_engine/state.py`（新）：`claim_task` / `submit_result`（PENDING→IN_PROGRESS→DONE/PROMISE 改期）+ `TaskNotFoundError`/`TaskStateError` + 终态保护 + 权限校验
  - `api/tasks.py`：追加 POST `/api/tasks/assign/run`（ADMIN）、POST `/api/tasks/{id}/claim`、POST `/api/tasks/{id}/result`
  - `schemas/task.py`：`AssignmentRunOut`/`TaskOut`/`TaskResultIn`
  - `scheduler/jobs.py`：每日 job = generate + assign 完整跑批
- 测试 `tests/test_task_assignment.py` 13 用例（含覆盖 `seed_users` 建 3 名催收员的 fixture）

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：wb-001 及之后功能均 not_started
- 下一轮会话需要注意的风险：
  - SQLite BigInteger 自增 / StaticPool / vite IPv6 localhost（沿用记录）
  - 后端默认端口 8000
  - 分配负载统计 = 催收员 PENDING + IN_PROGRESS 任务数（PROMISE 改期回 PENDING 的也算待处理，已计入）
  - 状态机 `talk_used` 仅写 TaskResult 明细，Task 模型无该字段（符合设计）
  - 主管手动改派（F-TASK-04 P1）未实现，task-002 仅系统自动分配
  - dev.db 现含 30 条已分配任务（collector1/2/3 各 10，PENDING），属本地数据不影响仓库

## 下一步最佳动作

- 最高优先级未完成功能：`wb-001` 催收工作台（任务列表 / 详情 / 领取 / 回填 前端 UI）
- 为什么它是下一步：task-002 后端分配与状态机已就绪，催收员需要前端界面查看分配给自己的任务并执行催收；这是闭环里第一个面向催收员视角的功能
- 什么结果才算 passing（对应 docs/03 TC-WB-01~05）：
  - 催收员登录看到分配给自己的任务（TC-WB-01）
  - 任务列表按风险与账龄排序（TC-WB-02）
  - 任务详情展示订单信息 + 用户特征 + 推荐话术占位（TC-WB-03，话术 talk-001 后补真实）
  - 领取任务（claim）后状态变 IN_PROGRESS（TC-WB-04）
  - 回填结果（PAID/PROMISE/...）后状态正确流转（TC-WB-05）
- 这一步中哪些东西不要动：
  - docs/ 下需求架构（已是基线）
  - task_engine 的 generate_tasks/assign_pending_tasks/claim_task/submit_result 契约（task-001/002 已落地）
  - Task 模型与状态机枚举
  - RiskProvider/config_service 等 risk 部分
  - CLAUDE.md / CODEBUDDY.md 的设计约束

## wb-001 实现要点（给新会话的提示）

- 后端可能需补（task-002 未做列表/详情查询）：
  - GET `/api/tasks?assignee=&status=&page=&size=`（按风险+账龄排序，催收员只看自己的）
  - GET `/api/tasks/{id}`（订单信息 + 特征 + 任务状态）
- 复用：`TaskOut`（task-002 已建）、`claim_task`/`submit_result`、`require_role("COLLECTOR")`、`get_current_user`
- 前端：
  - `pages/Workbench/`（新）：待办列表 + 详情抽屉 + 领取/回填表单
  - `api/tasks.ts`：list/get/claim/submitResult
  - 路由守卫已就绪（infra-002）
- 参考 docs/02 §5.4 任务 API、docs/03 TC-WB-01~05

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
  - 手动分配：`POST /api/tasks/assign/run`（ADMIN）
  - 领取任务：`POST /api/tasks/{id}/claim`（COLLECTOR/SUPERVISOR/ADMIN）
  - 回填结果：`POST /api/tasks/{id}/result`（同上）
