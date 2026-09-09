# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。
> 本仓库由 Claude Code（`CLAUDE.md`）与 CodeBuddy（`CODEBUDDY.md`）共用同一套 harness 工件开发。

## 当前已验证

- 现在明确可用的部分：infra-001/002、data-001、risk-001/002、task-001/002、**wb-001 催收工作台（前后端闭环）**
- 这轮实际跑过的验证（Session 009 / CodeBuddy）：
  - 后端 pytest 全量 **98 passed**（…+ 11 workbench）
  - 前端 npm run build 通过（tsc -b + vite build，3051 modules）
  - 后端 GET /api/tasks（COLLECTOR 只看自己 + 风险/账龄排序 + 分页/状态过滤）、GET /api/tasks/{id}（订单+特征摘要）
  - 前端 Workbench：待办列表 + 详情抽屉（订单/任务/特征画像）+ 领取 + 回填（PROMISE 改期）

## 本轮改动（wb-001）

- 后端新增/变更：
  - `api/tasks.py`：GET `/api/tasks`（分页+过滤+排序，COLLECTOR 强制只看自己）+ GET `/api/tasks/{id}`（详情含 OrderBrief/FeatureBrief）
  - `schemas/common.py`：`PagedResponse[T]`；`schemas/task.py`：`OrderBriefOut`/`FeatureBriefOut`/`TaskDetailOut`
  - 排序 `sqlalchemy.case`（HIGH<MEDIUM<LOW + due_date 升序），规避 func.case else_ 坑
- 前端：
  - `api/tasks.ts`（新）：listTasks/getTask/claimTask/submitTaskResult/runBatch/runAssign/getBatchStatus
  - `types/api.ts`：Task/TaskList/TaskDetail/TaskResultInput/BatchRunOut/AssignmentRunOut/BatchStatusOut
  - `pages/Workbench/index.tsx`：真实工作台（替换占位页）
- 测试 `tests/test_workbench.py` 11 用例（TC-WB-01~06 + 边界）

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：talk-001 及之后功能均 not_started
- 下一轮会话需要注意的风险：
  - SQLite BigInteger 自增 / StaticPool / vite IPv6 localhost（沿用记录）
  - 后端默认端口 8000
  - 列表排序用 `sqlalchemy.case`（非 `func.case`，else_ 在本版本有坑，沿用 risk-002 记录）
  - 前端 chunk 1.35MB（antd 整包），后续按需 code-split
  - 工作台话术区为占位，talk-001 后接入 GET /api/talk/recommend
  - 主管手动改派（F-TASK-04 P1）未实现
  - dev.db 现含 30 条已分配任务（collector1/2/3 各 10，PENDING），属本地数据

## 下一步最佳动作

- 最高优先级未完成功能：`talk-001` 基础话术模板匹配
- 为什么它是下一步：催收员工作台已能看任务+领取+回填，但话术区是占位；talk-001 提供模板匹配+变量填充，让催收员拿到规范话术，闭环里"话术辅助"环节补齐
- 什么结果才算 passing（对应 docs/03 TC-TALK-01~05）：
  - 精确模板命中（TC-TALK-01）
  - ANY 兜底回退匹配（TC-TALK-02）
  - 变量占位符填充（{供应商名称} 等）（TC-TALK-03）
  - 会员/非会员分支（TC-TALK-04）
  - 多模板按优先级返回（TC-TALK-05）
- 这一步中哪些东西不要动：
  - docs/ 下需求架构（已是基线）
  - task_engine 全套契约（task-001/002）+ wb-001 前端
  - RiskProvider/config_service 等 risk 部分
  - CLAUDE.md / CODEBUDDY.md 的设计约束

## talk-001 实现要点（给新会话的提示）

- 复用：
  - `TalkTemplate`/`AIConversation` 模型（infra-001 已建表，字段含 risk_tier/age_range/scene/member/template_text/priority 等，见 docs/02 §3.2）
  - `Task`/`Order`/`OrderFeature`（详情已有 feature）
  - `require_role`、`APIResponse[T]`
- 新建：
  - `services/talk_engine/matcher.py`：`match_templates(task, order, feature)` → 按优先级返回 TalkTemplate 列表（精确→ANY 回退）
  - `services/talk_engine/renderer.py`：变量填充（{供应商名称}/{订单号}/{应催日} 等）
  - `api/talk.py`：GET `/api/talk/recommend?task_id=`（登录可见）
  - `seed.py`：加默认话术模板种子（HIGH×8_15×SECOND×MEMBER 等几条 + ANY 兜底）
- 参考 docs/02 §4.3 话术架构、docs/03 TC-TALK-01~05
- 工作台详情抽屉话术区当前占位，talk-001 后接入推荐话术展示

## 命令

- 启动命令：`./init.sh`（bash；PowerShell 下 `bash ./init.sh` 或按 CODEBUDDY.md 分步命令）
- 验证命令：后端 `cd backend && .venv\Scripts\python.exe -m pytest -q`；前端 `cd frontend && npm run build`
- 种子数据：`cd backend && .\.venv\Scripts\Activate.ps1 && python seed.py`（用户 + 风险档配置 v1）
- 启动后端：`uvicorn app.main:app --reload --port 8000`（localhost 访问）
- 启动前端：`npm run dev`（5173，localhost 访问）
- 默认账号：admin/supervisor/collector1-3，密码 admin123
- 关键接口：
  - 任务列表：`GET /api/tasks?status=&page=&size=`（COLLECTOR 只看自己）
  - 任务详情：`GET /api/tasks/{id}`
  - 领取：`POST /api/tasks/{id}/claim`（COLLECTOR/SUPERVISOR/ADMIN）
  - 回填：`POST /api/tasks/{id}/result`
  - 手动跑批/分配：`POST /api/tasks/batch/run?recalc=true`、`POST /api/tasks/assign/run`（ADMIN）
  - 批次状态：`GET /api/tasks/batch/status/{batch_id}`
  - （话术待建）`GET /api/talk/recommend?task_id=`
