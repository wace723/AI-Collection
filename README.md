# 平台使用费 AI 辅助催收系统

从真实业务平台获取中标订单及特征 → 算欠费风险概率（MVP mock）→ 按风险档生成催收任务并分配给催收员 → 话术辅助（模板+AI）→ 数据大盘。

详细文档见 [docs/](./docs/)。

## 技术栈

- 后端：Python 3.11+ / FastAPI / SQLAlchemy 2.0 / Alembic / APScheduler
- 前端：React 18 / TypeScript / Vite / Ant Design 5
- 数据库：PostgreSQL 15（开发期 SQLite）

## 快速开始（本地开发）

### 一、后端

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate    # Git Bash / Windows
# source .venv/bin/activate      # Unix
pip install -r requirements.txt

# 数据库迁移（开发期 SQLite，dev.db 落在 backend/ 下）
alembic upgrade head

# 启动
uvicorn app.main:app --reload
# 健康检查：curl http://localhost:8000/health
```

### 二、前端

```bash
cd frontend
npm install
npm run dev
# 浏览器打开 http://localhost:5173
```

### 三、一键脚本

```bash
./init.sh                           # 装依赖 + 迁移 + 测试 + 构建
RUN_START_COMMAND=1 ./init.sh        # 同上并启动前后端
```

## 环境变量

复制 `backend/.env.example` 为 `backend/.env` 后按需修改：

| 变量 | 默认 | 说明 |
|------|------|------|
| DATABASE_URL | sqlite:///./dev.db | 开发期 SQLite，生产用 postgresql+psycopg:// |
| JWT_SECRET | change-me | JWT 密钥（infra-002 用） |
| LLM_PROVIDER | mock | mock / claude / openai（talk-002 用） |
| AI_TALK_ENABLED | false | AI 话术开关 |
| CORS_ORIGINS | ["http://localhost:5173"] | 允许的前端来源 |

## Docker（可选生产自检）

本地未安装 Docker 时可跳过，开发用 SQLite + uvicorn 即可。

```bash
docker compose --profile pg up --build   # 启动 postgres + backend + frontend
```

## 验证（infra-001）

- [x] `./init.sh` 全流程退出码 0
- [x] `curl http://localhost:8000/health` → 200 `{"status":"ok"}`
- [x] `cd frontend && npm run dev` → Vite 启动
- [x] `alembic upgrade head` → 9 张业务表建表成功

## 项目结构

```
docs/          需求/架构/测试文档（事实来源）
backend/       FastAPI 后端
frontend/      React 前端
CLAUDE.md      harness 路由层（开始工作前先读）
feature_list.json   功能状态追踪
claude-progress.md  会话进度日志
init.sh        标准启动与验证
```
