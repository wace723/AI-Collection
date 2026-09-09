# CODEBUDDY.md

你正在用 **CodeBuddy** 为「平台使用费 AI 辅助催收系统」做长时实现工作。优先保证可靠完成、跨会话连续性和显式验证，而不是表面上的速度。

> 本文件是 harness 在 **CodeBuddy** 下的路由层。项目此前由 **Claude Code** 开发（其路由层是 `CLAUDE.md`，保留不动）。两个工具**共享同一套**文档与状态工件：`docs/`（唯一事实来源）、`feature_list.json`、`claude-progress.md`、`session-handoff.md`、`clean-state-checklist.md`、`init.sh`。**禁止创建平行的状态/进度文件**。先读本文件，再按指引读具体文档与状态文件。所有设计/需求细节以 `docs/` 为唯一事实来源。

## 项目一句话

从真实业务平台获取中标订单及特征 → 算欠费风险概率（MVP mock）→ 按风险档生成催收任务并分配给 3 名催收员 → 话术辅助（模板+AI）→ 数据大盘。

## 技术栈

- 后端：Python 3.11 + FastAPI + SQLAlchemy 2.0 + Alembic + APScheduler
- 前端：React 18 + TypeScript + Vite + Ant Design 5
- 数据库：PostgreSQL 15（开发期可 SQLite）
- LLM：Provider 抽象层（Claude / OpenAI / mock，可开关）

## 双工具协作约定

- `CLAUDE.md`：Claude Code 的路由层（已存在，勿改）。
- `CODEBUDDY.md`（本文件）：CodeBuddy 的路由层。两者指向同一套 `docs/` 与状态文件，约束保持一致。
- 状态单一事实源：`feature_list.json`（功能状态）+ `claude-progress.md`（会话连续性日志），两个工具**串行共用**。同一时间只能有一个 active feature，彼此通过这两个文件接力。
- 出现分歧时：以 `docs/`、`feature_list.json` 的实际状态为准，并同步修正两个路由层文件。

## 固定工作循环

每轮会话开始：

1. 确认在仓库根目录（必要时 `cd e:/my-projects/平台使用费ai辅助催收系统`）
2. 读取 `claude-progress.md`（会话连续性日志，含最近会话与运行工具）
3. 读取 `feature_list.json`（功能状态追踪：当前 active / passing / blocked）
4. 按需读取 `docs/`：
   - 整体需求 → `docs/01-产品需求文档.md`
   - 架构/数据模型/API → `docs/02-技术架构设计.md`
   - 测试范围/用例 → `docs/03-测试用例.md`
5. 运行仓库验证（见下文「验证与命令（CodeBuddy 环境）」）
6. 检查最近会话记录的关键路径是否仍可通过

然后**只选择一个未完成功能**，围绕它工作，直到它被验证通过，或被明确记录为 blocked。

## 规则（与 CLAUDE.md 一致）

- 同一时间只能有一个 active feature
- 没有可运行证据时，不要声称完成
- 不要通过重写功能清单来隐藏未完成工作
- 不要为了"看起来完成"而删除或削弱测试
- 以仓库内文件作为唯一事实来源
- **不可变数据**：创建新对象而非原地修改
- **小文件优先**：单文件 200~400 行典型，800 行上限
- **错误处理**：每一层显式处理，UI 层给友好提示，服务端记详细上下文
- **输入校验**：在系统边界（API/CSV 解析）校验所有外部输入

## 目录约定

```
平台使用费ai辅助催收系统/
├── docs/                  # 需求/架构/测试文档（事实来源）
├── backend/               # FastAPI 后端
│   ├── app/
│   │   ├── core/          # config, security, database
│   │   ├── models/        # ORM 模型
│   │   ├── schemas/        # Pydantic 模型
│   │   ├── api/            # 路由
│   │   ├── services/       # 业务逻辑（按模块组织）
│   │   │   ├── data_ingestion/
│   │   │   ├── risk_engine/
│   │   │   ├── task_engine/
│   │   │   ├── talk_engine/
│   │   │   └── dashboard/
│   │   └── scheduler/      # 跑批调度
│   ├── alembic/            # 迁移
│   └── tests/
├── frontend/               # React 前端
│   └── src/
│       ├── pages/          # Workbench/Supervisor/Config/Dashboard
│       ├── components/
│       └── api/
├── feature_list.json       # 功能状态追踪
├── claude-progress.md      # 会话进度日志（两工具共用）
├── CODEBUDDY.md            # CodeBuddy 路由层（本文件）
├── CLAUDE.md               # Claude Code 路由层（勿改）
├── init.sh                 # 标准启动与验证
└── session-handoff.md      # 会话交接（需要时）
```

## 关键设计约束（不可违反）

1. **风险算法可替换**：风险概率必须经 `RiskProvider` 抽象接口，MVP 用 `MockRiskProvider`，后续替换无感知。
2. **LLM 可降级**：AI 话术失败必须回退模板话术，不阻断催收。
3. **任务幂等**：`batch_id + order_id + day_offset` 三元组唯一，不重复生成催收任务。
4. **催收触发条件**：到达催收时点**且届时仍未支付**才生成任务。
5. **数据泄漏**：C 类标签表特征无时间维度，上线真实算法前必须做时间切割。
6. **平台阻断不在本系统**：本系统"阻断"语义=催收节点强提醒+人工介入，非交易阻断。

## 完成门槛（Definition of Done）

功能状态切到 `passing` 前，必须：

- [ ] 实现完成
- [ ] 对应验证命令通过（见 `init.sh` 或下文命令节）
- [ ] 证据记录到 `feature_list.json` 的 `evidence` 字段
- [ ] 仓库可重启（验证脚本通过，无残留脏状态）
- [ ] 单元测试覆盖核心逻辑（≥ 80%）

## 验证与命令（CodeBuddy 环境 = Windows + PowerShell）

环境差异：本机为 **Windows + PowerShell (Core)**，`init.sh` 是 bash 脚本。执行命令前先设编码，避免中文路径/GBK 终端报错：

```powershell
$env:PYTHONUTF8=1
$env:PYTHONIOENCODING="utf-8"
```

一键全流程（需 Git Bash；无 bash 时用下方分步命令）：

```powershell
bash ./init.sh     # 依赖 + 迁移 + pytest + npm run build
```

后端分步：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
pytest -q
```

前端分步：

```powershell
cd frontend
npm install
npm run build
```

运行与种子：

```powershell
cd backend; .\.venv\Scripts\Activate.ps1
python seed.py                                    # 用户 + 风险档配置 v1
uvicorn app.main:app --reload --port 8000         # 启动后端
```

```powershell
cd frontend; npm run dev                          # 启动前端（5173）
```

要点：
- 访问用 `http://localhost:8000`、`http://localhost:5173`（Vite 监听 IPv6，勿用 127.0.0.1）
- 默认账号：admin / supervisor / collector1-3，密码 `admin123`
- 常用接口：`POST /api/auth/login`、`POST /api/data/upload`、`POST /api/data/orders/recalc-risk`、`GET/PUT /api/config/risk`、`GET /api/config/risk/history`、`POST /api/config/risk/rollback/{version}`
- 数据库：SQLite `backend/dev.db`（被 .gitignore 覆盖）

探索与审查（CodeBuddy 可用 subagent）：

- 跨文件/大范围探索：**code-explorer**（只读，结果不入主上下文）
- 功能完成后质量审查：**code-review**
- 高复杂度/难维护代码简化：**code-simplifier**
- 串行使用，subagent 内不再嵌套其他 subagent

## 结束前（收尾清单）

1. 更新 `claude-progress.md`：追加新 Session（编号延续，标注工具 = CodeBuddy），记录完成内容、验证证据、已知风险
2. 更新 `feature_list.json`：状态真实反映 passing / in_progress / blocked 边界，`last_updated` 与 `evidence` 同步
3. 记录仍然损坏或未验证的内容
4. 勾选 `clean-state-checklist.md`
5. 需要简短交接时更新 `session-handoff.md`
6. 提交（描述性 commit message），给下一轮会话留下干净的重启路径

## Git 约定

- commit 格式：`<type>: <description>`，type ∈ feat/fix/refactor/docs/test/chore/perf/ci
- Attribution 已全局关闭，不要加 AI 署名
