# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。
> 本仓库由 Claude Code（`CLAUDE.md`）与 CodeBuddy（`CODEBUDDY.md`）共用同一套 harness 工件开发。
> AI 功能参考 agent-app-builder 技能方法论（控制权光谱→代码为主 LLM 辅助；纵深安全多道防线）。

## 当前已验证

- 现在明确可用的部分：infra-001/002、data-001、risk-001/002、task-001/002、wb-001、talk-001、**talk-002 AI 话术生成**
- 这轮实际跑过的验证（Session 011 / CodeBuddy）：
  - 后端 pytest 全量 **137 passed**（…+ 18 talk_ai）
  - 修复 BACKEND_DIR bug：.env 现正确加载（LLM_API_KEY/BASE_URL/MODEL 入 settings）
  - 真实 LLM 配置已注入 ai_config DB（provider=openai_compatible, enabled=True, key/base/model 齐全）；调 tianqu.yzw.cn ReadTimeout → 降级模板正常（设计约束#2）
  - 前端 AIConfigPanel（配置后台）+ Workbench 详情 AI 生成/反馈按钮；npm run build 通过

## 本轮改动（talk-002）

- 后端：
  - **修复 config.py BACKEND_DIR**（.parent.parent→三层）——infra-001 起的遗留 bug，.env 从未加载
  - `models/ai_config.py`（新）+ 迁移 `d5e3a1b2c4f6`：AI 配置单行表
  - `services/talk_engine/ai_config_service.py`：DB 优先 / .env 回退 + 脱敏 + 空 key 保留旧
  - `services/talk_engine/llm_provider.py`：LLMProvider ABC + Mock + OpenAICompatible（httpx）
  - `services/talk_engine/generator.py`：generate_talk（生成→**合规校验**→写 AIConversation→降级）+ feedback
  - `api/config.py`：GET/PUT `/api/config/ai`（SUPERVISOR/ADMIN）；`api/talk.py`：POST `/api/talk/generate`、`/api/talk/feedback`
  - `seed.py`：seed_ai_config（有 key→真实 LLM 启用）
- 前端：`AIConfigPanel.tsx` + `api/config.ts`/`api/talk.ts` + Workbench AI 生成/反馈
- 测试 `tests/test_talk_ai.py` 18 用例（含 monkeypatch 合规校验）

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：dash-001 及之后功能均 not_started
- 下一轮会话需要注意的风险：
  - SQLite BigInteger 自增 / StaticPool / vite IPv6 localhost（沿用记录）
  - 后端默认端口 8000
  - **真实 LLM 调 tianqu.yzw.cn 超时**（疑似内部服务需内网/VPN）→ 降级模板工作；用户需确认 base_url 可达性，可在前端「配置后台 → AI 话术配置」改 base_url/model/provider 或切 mock
  - api_key 明文存 DB（MVP，生产应加密）
  - 合规校验为关键词法（可误杀/漏判，生产可换分类模型）
  - dev.db 现 ai_config 启用真实 LLM（但调用超时降级）+ 30 已分配任务 + 6 话术模板（本地数据，不影响仓库）
  - 若在浏览器测试 AI 生成，需重启后端（旧 uvicorn 未加载 talk-002 路由 + BACKEND_DIR 修复）

## 下一步最佳动作

- 最高优先级未完成功能：`dash-001` 数据大盘（日/周/月指标聚合）
- 为什么它是下一步：催收闭环（生成→分配→催收→回填→话术）已全通，数据大盘是最后一环，让主管看整体态势（欠费率/回款率/任务完成率/风险档分布）
- 什么结果才算 passing（对应 docs/03 TC-DASH 系列）：
  - 日大盘核心指标聚合（欠费金额/回款数/任务完成率/在催任务数）
  - 风险档分布（HIGH/MEDIUM/LOW 任务数）
  - 催收员负载分布
  - 周/月趋势
- 这一步中哪些东西不要动：
  - task_engine/talk_engine 全套契约
  - Order/Task/TaskResult/AIConversation 模型
  - CLAUDE.md / CODEBUDDY.md 的设计约束

## dash-001 实现要点（给新会话的提示）

- 复用：
  - `Order`（pay_status/risk_tier/win_bid_date）、`Task`（status/assignee_id/result）、`TaskResult`（result/collector_id）
  - `require_role`、`APIResponse[T]`
- 新建：
  - `services/dashboard/metrics.py`：`daily_metrics(db, date)` / `weekly` / `monthly` 聚合查询
  - `api/dashboard.py`：GET `/api/dashboard/daily`、`/weekly`、`/monthly`（SUPERVISOR/ADMIN）
  - `schemas/dashboard.py`：DashboardOut（核心指标 + 分布）
  - 前端 `pages/Dashboard/index.tsx`（替换占位）：卡片指标 + 风险档饼图 + 催收员负载柱图（@ant-design/charts 或简单 Table）
- 参考 docs/02 §5.6 大盘 API、docs/03 TC-DASH 系列、docs/01 §4.7 大盘指标

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
  - （大盘待建）`GET /api/dashboard/daily` 等
