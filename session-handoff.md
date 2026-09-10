# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。
> 本仓库由 Claude Code（`CLAUDE.md`）与 CodeBuddy（`CODEBUDDY.md`）共用同一套 harness 工件开发。
> AI 功能参考 agent-app-builder 技能方法论（控制权光谱→代码为主 LLM 辅助；纵深安全多道防线）。

## 当前已验证

- 现在明确可用的部分：infra-001/002、data-001、risk-001/002、task-001/002、wb-001、talk-001、talk-002、**dash-001 数据大盘**
- 这轮实际跑过的验证（Session 012 / Claude Code）：
  - 后端 pytest 全量 **149 passed**（137 旧 + 12 dashboard 新，无回归）
  - 前端 `npm run build` 通过（tsc + vite build，5375 modules）；@ant-design/charts lazy 代码分割，图表库单独成 chunk 未恶化首屏
  - 真实数据 E2E（dev.db 20 条未支付订单）：daily 指标与库一致（unpaid=20、risk HIGH=5/MEDIUM=12/LOW=3、age 90_PLUS=20）；回填 PAID 后大盘回款+1；权限 collector1→403

## 本轮改动（dash-001）

- 后端：
  - `services/dashboard/metrics.py`（新）：frozen dataclass + 三聚合函数（daily/weekly/monthly）；未支付订单 or_ 含 NULL；回款用 TaskResult.result='PAID'+created_at 时间戳（非 Order.pay_status）；回款率分母=当日已处理 distinct task_id，分母0→0.0；风险档 NULL→NONE、账龄 NULL→UNKNOWN；账龄段复用 talk_engine.matcher.map_age_bucket
  - `schemas/dashboard.py`（新）+ `api/dashboard.py`（新）：GET /api/dashboard/daily、/weekly、/monthly（SUPERVISOR/ADMIN）；router 挂载 /dashboard
  - `tests/test_dashboard.py`（新）：9 用例（TC-DASH-01/02/03 + 空库 + 月大盘冒烟 + 权限 + 周排名）
- 前端：
  - `npm install @ant-design/charts` v2.6.7；`components/Charts.tsx`（lazy Pie/Column/Line + Suspense）
  - `api/dashboard.ts` + types/api.ts 追加类型
  - `pages/Dashboard/`：index.tsx（角色判断+Tabs，均 lazy）+ DailyTab（4卡片+风险档/账龄 Pie）+ WeeklyTab（双折线趋势+催收员排名表）+ MonthlyTab（3卡片+各档催收效果柱图+明细表）

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：**仅剩 `e2e-001` 端到端完整闭环验证**（not_started），这是 MVP 验收最后关卡
- 下一轮会话需要注意的风险：
  - SQLite BigInteger 自增 / StaticPool / vite IPv6 localhost（沿用记录）
  - 后端默认端口 8000
  - **真实 LLM 调 tianqu.yzw.cn 超时**（疑似内部服务需内网/VPN）→ 降级模板工作；用户需确认 base_url 可达性，可在前端「配置后台 → AI 话术配置」改 base_url/model/provider 或切 mock
  - 回款语义：TaskResult.collector_id 记录的是回填操作者（含 ADMIN/SUPERVISOR 代理），非 task.assignee_id；「催收员绩效排名」按操作者统计，生产可按需调整
  - 回款率口径=当日回款数/当日已处理任务数（非新增任务数）；周完成率=当日 DONE/当日新增（跨日完成可能>100%）
  - 真实数据账龄普遍 90_PLUS（历史订单，沿用 talk-001 记录）
  - 图表库新增 chunk（es-*.js 2.2MB/gzip 659KB），但 lazy 代码分割未进首屏主 chunk
  - dev.db 现有 1 笔测试回填 PAID（task5，本地数据，不影响仓库）+ 20 未支付订单 + 30 已分配任务 + ai_config 启用真实 LLM（但调用超时降级）
  - 若在浏览器测试大盘，需重启后端（旧 uvicorn 未加载 dashboard 路由）

## 下一步最佳动作

- 最高优先级未完成功能：`e2e-001` 端到端完整闭环验证
- 为什么它是下一步：催收闭环（生成→分配→催收→回填→话术）+ 数据大盘（dash-001）已全通，e2e-001 是 MVP 验收最后关卡，验证「上传→算风险→跑批→分配→催收→话术→回填→大盘」全流程贯通
- 什么结果才算 passing（对应 docs/03 TC-E2E 系列）：
  - TC-E2E-01 完整催收闭环通过（上传20条→recalc→跑批→分配→工作台→AI话术→回填PAID→大盘回款+1）
  - TC-E2E-02 高风险多轮催收闭环通过
  - TC-E2E-03 已支付订单全程不催收通过
- 这一步中哪些东西不要动：
  - task_engine/talk_engine/dashboard 全套契约
  - Order/Task/TaskResult/AIConversation 模型
  - CLAUDE.md / CODEBUDDY.md 的设计约束

## e2e-001 实现要点（给新会话的提示）

- 复用：现有所有 API 已就绪（data/risk/task/talk/dashboard/config），可写一个 Python 脚本或 pytest 用例串完整流程
- 参考 docs/03 §8 TC-E2E-01~03 的步骤
- 已验证的衔接点：回填 PAID → 大盘 daily paid_count +1（Session 012 已联调）
- TC-E2E-03（已支付订单不催收）：上传含 pay_status=PAID 订单 → 跑批不应为其生成任务（task-001 已覆盖语义）

## 命令

- 启动命令：`./init.sh`（bash；PowerShell 下 `bash ./init.sh` 或按 CODEBUDDY.md 分步命令）
- 验证命令：后端 `cd backend && .venv\Scripts\python.exe -m pytest -q`；前端 `cd frontend && npm run build`
- 种子数据：`cd backend && .\.venv\Scripts\Activate.ps1 && python seed.py`（用户 + 风险档配置 + 6 话术模板 + AI 配置）
- 启动后端：`uvicorn app.main:app --reload --port 8000`（localhost 访问）
- 启动前端：`npm run dev`（5173，localhost 访问）
- 默认账号：admin/supervisor/collector1-3，密码 admin123
- 关键接口：
  - 任务：`GET /api/tasks`、`POST /api/tasks/{id}/claim`、`POST /api/tasks/{id}/result`
  - 话术：`GET /api/talk/recommend?task_id=`、`POST /api/talk/generate?task_id=`、`POST /api/talk/feedback`
  - AI 配置：`GET/PUT /api/config/ai`（SUPERVISOR/ADMIN）
  - 风险配置：`GET/PUT /api/config/risk/...`
  - 跑批/分配：`POST /api/tasks/batch/run`、`POST /api/tasks/assign/run`（ADMIN）
  - 大盘：`GET /api/dashboard/daily`、`/weekly`、`/monthly`（SUPERVISOR/ADMIN）
