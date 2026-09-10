# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。
> 本仓库由 Claude Code（`CLAUDE.md`）与 CodeBuddy（`CODEBUDDY.md`）共用同一套 harness 工件开发。
> AI 功能参考 agent-app-builder 技能方法论（控制权光谱→代码为主 LLM 辅助；纵深安全多道防线）。

## 当前已验证

- **MVP 验收完成**：全部 12 个功能 passing（infra-001/002、data-001、risk-001/002、task-001/002、wb-001、talk-001、talk-002、dash-001、**e2e-001**）
- 这轮实际跑过的验证（Session 013 / Claude Code）：
  - 后端 pytest 全量 **152 passed**（149 旧 + 3 e2e 新，无回归）
  - 真实数据 E2E 联调（/e/tmp/verify_e2e.py，dev.db+真实uvicorn）：上传→算风险→跑批→分配→工作台→详情→推荐话术→AI生成(mock)→回填PAID→大盘paid+1 ✅ 全流程贯通

## 本轮改动（e2e-001）

- `tests/test_e2e.py`（新）：3 用例（TC-E2E-01/02/03），TestClient 串真实 API 端到端验证
  - TC-E2E-01 完整催收闭环（9 步：上传20条→recalc→配置→跑批20→分配20→工作台→详情→推荐话术→AI生成→回填PAID→大盘paid+1）
  - TC-E2E-02 高风险多轮（service层run_batch注入today：第7天FIRST→PROMISE改期→第15天SECOND→DISPUTE）
  - TC-E2E-03 已支付订单不催收（PAID→跑批generated=0→多日跑批始终0任务）
- `e:/tmp/verify_e2e.py`（新）：真实数据 E2E 联调脚本（dev.db+真实uvicorn）

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：无（全部功能 passing，MVP 验收完成）
- 下一轮会话需要注意的风险：
  - SQLite BigInteger 自增 / StaticPool / vite IPv6 localhost（沿用记录）
  - 后端默认端口 8000
  - **真实 LLM 调 tianqu.yzw.cn 超时**（疑似内部服务需内网/VPN）→ 降级模板工作；用户需确认 base_url 可达性，可在前端「配置后台 → AI 话术配置」改 base_url/model/provider 或切 mock
  - TC-E2E-01 测试构造特征使 mock 概率≥70→HIGH 档（特征值精确控制）；真实 CSV 档位分布由 mock 公式决定（混合）
  - TC-E2E-02 用 service 层 run_batch(db,today=...) 注入时间推进（API 不接受 today 注入）
  - dev.db 现有多笔测试回填 PAID + 35 未支付订单 + 多轮任务（本地数据，不影响仓库）

## 下一步最佳动作

- **MVP 验收完成**，无必须功能待开发
- 后续可选增强（非 MVP，按需）：
  - 真实 LLM 调通（用户确认 tianqu.yzw.cn base_url 可达性 / 内网）
  - PG 时区统一（dash-001 review 记录的 H-2，MVP 用 SQLite naive UTC 语义一致）
  - 前端主 chunk code-split 优化（antd 整包 1.36MB）
  - 真实算法替换 MockRiskProvider（需时间切割防数据泄漏，docs/02 §3.2.2）
  - 主管手动改派（F-TASK-04 P1，wb-001 记录未实现）
  - 话术模板管理 UI（talk-001 记录未做）
  - 跑批性能/工作台列表性能（TC-NF-01/02 非功能测试）

## 命令

- 启动命令：`./init.sh`（bash；PowerShell 下 `bash ./init.sh` 或按 CODEBUDDY.md 分步命令）
- 验证命令：后端 `cd backend && .venv\Scripts\python.exe -m pytest -q`；前端 `cd frontend && npm run build`
- 种子数据：`cd backend && .\.venv\Scripts\Activate.ps1 && python seed.py`（用户 + 风险档配置 + 6 话术模板 + AI 配置）
- 启动后端：`uvicorn app.main:app --reload --port 8000`（localhost 访问）
- 启动前端：`npm run dev`（5173，localhost 访问）
- E2E 真实联调：`cd backend && E2E_BASE_URL=http://127.0.0.1:8000 python /e/tmp/verify_e2e.py`（需先启动后端）
- 默认账号：admin/supervisor/collector1-3，密码 admin123
- 关键接口：
  - 任务：`GET /api/tasks`、`POST /api/tasks/{id}/claim`、`POST /api/tasks/{id}/result`
  - 话术：`GET /api/talk/recommend?task_id=`、`POST /api/talk/generate?task_id=`、`POST /api/talk/feedback`
  - AI 配置：`GET/PUT /api/config/ai`（SUPERVISOR/ADMIN）
  - 风险配置：`GET/PUT /api/config/risk/...`
  - 跑批/分配：`POST /api/tasks/batch/run`、`POST /api/tasks/assign/run`（ADMIN）
  - 大盘：`GET /api/dashboard/daily`、`/weekly`、`/monthly`（SUPERVISOR/ADMIN）
  - 数据：`POST /api/data/upload`、`POST /api/data/orders/recalc-risk`（ADMIN）
