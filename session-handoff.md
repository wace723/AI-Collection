# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。
> 本仓库由 Claude Code（`CLAUDE.md`）与 CodeBuddy（`CODEBUDDY.md`）共用同一套 harness 工件开发。

## 当前已验证

- 现在明确可用的部分：infra-001/002、data-001、risk-001/002、task-001/002、wb-001、**talk-001 基础话术模板匹配**
- 这轮实际跑过的验证（Session 010 / CodeBuddy）：
  - 后端 pytest 全量 **119 passed**（…+ 21 talk）
  - 真实数据 E2E：dev.db seed 6 模板 → task1（HIGH/FIRST/账龄>90）回退 ANY×ANY×ANY×ANY 兜底，变量已填充无残留
  - 前端 Workbench 详情抽屉接入「推荐话术」区（主推+候选折叠）；npm run build 通过

## 本轮改动（talk-001）

- 后端：
  - `services/talk_engine/matcher.py`：`map_age_bucket`（5 段边界）+ `derive_user_tag`（MEMBER）+ `match_templates`（4 维打分，ANY 兜底，总分降序）
  - `services/talk_engine/renderer.py`：`render`（7 占位符替换）
  - `services/talk_engine/recommend.py`：`recommend_talks` 编排
  - `api/talk.py`：GET `/api/talk/recommend?task_id=`（COLLECTOR 仅自己任务）
  - `schemas/talk.py`：TalkTemplateOut / TalkRecommendOut
  - `seed.py`：`seed_default_talk_templates`（6 条，幂等按 name）
- 前端：`api/talk.ts` + `types/api.ts`（TalkRecommend）+ Workbench 详情话术区
- 测试 `tests/test_talk.py` 21 用例

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：talk-002 及之后功能均 not_started
- 下一轮会话需要注意的风险：
  - SQLite BigInteger 自增 / StaticPool / vite IPv6 localhost（沿用记录）
  - 后端默认端口 8000
  - 真实历史订单账龄普遍 >90 天（90_PLUS），默认模板对 HIGH/MEDIUM 90_PLUS 无精确匹配会回退 ANY 兜底（符合设计，可后续补精确模板）
  - user_feature_tag 仅 MEMBER 一种；SMALL_FUND/VIP 等后续扩展
  - 工作台话术区只展示模板话术，AI 生成（talk-002）未做
  - 话术模板管理 UI 未做（仅 seed 默认）
  - dev.db 现 seed 了 6 条话术模板 + 30 条已分配任务（本地数据，不影响仓库）
  - 若用户在浏览器测试话术，需重启后端（旧 uvicorn 未加载 talk 路由）

## 下一步最佳动作

- 最高优先级未完成功能：`talk-002` AI 话术生成（LLM Provider 抽象 + mock + 降级）
- 为什么它是下一步：talk-001 已提供模板话术，但催收员需要 AI 个性化增强话术；talk-002 补齐 LLM 抽象（mock/claude/openai）+ 生成接口 + 失败降级到模板，闭环里"话术辅助"完整
- 什么结果才算 passing（对应 docs/03 TC-TALK-05~10）：
  - AI 话术生成 mock 返回非空（TC-TALK-05）
  - 真实 LLM 可选（TC-TALK-06，需 key）
  - ai_talk_enabled 开关（TC-TALK-07）
  - LLM 失败降级模板（TC-TALK-08，不阻断催收）
  - 话术反馈 useful/useless 记录（TC-TALK-09）
  - 合规无违规（TC-TALK-10）
- 这一步中哪些东西不要动：
  - talk-001 的 match_templates/render/recommend_talks 契约
  - TalkTemplate/AIConversation 模型
  - task_engine 全套 + wb-001 前端
  - RiskProvider/config_service 等 risk 部分
  - CLAUDE.md / CODEBUDDY.md 的设计约束（AI 话术失败必须降级模板）

## talk-002 实现要点（给新会话的提示）

- 复用：
  - `AIConversation` 模型（task_id/order_id/prompt/response/provider/feedback，infra-001 已建表）
  - `recommend_talks`（talk-001，作模板兜底）
  - `Task`/`Order`/`OrderFeature`
- 新建：
  - `services/talk_engine/llm_provider.py`：`LLMProvider` 抽象 + `MockLLMProvider` + `ClaudeProvider`/`OpenAIProvider` 占位（按 settings 注入）
  - `services/talk_engine/generator.py`：`generate_talk(db, task, template_hint)` → 调 provider + 写 AIConversation + 失败降级
  - `api/talk.py`：追加 POST `/api/talk/generate`（task_id）、POST `/api/talk/feedback`
  - `core/config.py`：`AI_TALK_ENABLED` 开关、`LLM_PROVIDER`（mock/claude/openai）
  - 前端 Workbench 详情加「AI 生成」按钮 + 反馈
- 参考 docs/02 §4.3.3 LLM Provider 抽象、docs/03 TC-TALK-05~10
- 设计约束 #2：AI 话术失败必须回退模板，不阻断催收

## 命令

- 启动命令：`./init.sh`（bash；PowerShell 下 `bash ./init.sh` 或按 CODEBUDDY.md 分步命令）
- 验证命令：后端 `cd backend && .venv\Scripts\python.exe -m pytest -q`；前端 `cd frontend && npm run build`
- 种子数据：`cd backend && .\.venv\Scripts\Activate.ps1 && python seed.py`（用户 + 风险档配置 v1 + 6 条话术模板）
- 启动后端：`uvicorn app.main:app --reload --port 8000`（localhost 访问）
- 启动前端：`npm run dev`（5173，localhost 访问）
- 默认账号：admin/supervisor/collector1-3，密码 admin123
- 关键接口：
  - 任务列表/详情/领取/回填：`GET/POST /api/tasks...`
  - 手动跑批/分配：`POST /api/tasks/batch/run`、`POST /api/tasks/assign/run`（ADMIN）
  - 推荐话术：`GET /api/talk/recommend?task_id=`（登录，COLLECTOR 仅自己任务）
  - （AI 待建）`POST /api/talk/generate`、`POST /api/talk/feedback`
